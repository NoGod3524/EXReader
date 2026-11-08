"""Recompute and audit the 54 runs, then generate the typography report.

python -X utf8 tools/perf/typography_report.py
"""
import csv
import itertools
import json
from pathlib import Path
import statistics as stats
import subprocess

from typography_bench import ROOT, FONTS, LINE_HEIGHTS, VIEWPORTS, metrics, percentile, sha, trace, write_csv, write_json

OUT = ROOT / 'evidence/typography-bench-20261107'
NAMES = {'serif': 'Noto Serif SC', 'sans': 'Noto Sans CJK SC', 'simsun': '宋体'}


def table(headers, rows):
    return '\n'.join(['| ' + ' | '.join(headers) + ' |',
                      '| ' + ' | '.join(['---'] * len(headers)) + ' |'] +
                     ['| ' + ' | '.join(map(str, row)) + ' |' for row in rows])


def main():
    protocol = json.loads((OUT/'protocol.json').read_text(encoding='utf-8'))
    assert sha(ROOT/'tools/perf/typography_bench.py') == protocol['collector']['sha256']
    for value in [*protocol['fonts'].values(), protocol['book'], protocol['build']['exe'],
                  protocol['build']['dll'], protocol['capture']]:
        assert sha(value['path']) == value['sha256'], value['path']
    for path, digest in protocol['build']['input_files'].items():
        assert sha(ROOT/path) == digest, path
    protected = subprocess.check_output(['git', 'diff', protocol['build']['source_revision'], '--',
                                         'src', 'include', 'examples', '.github'], cwd=ROOT)
    assert not protected
    records = list(csv.DictReader((OUT/'runs.csv').open(encoding='utf-8')))
    assert len(records) == 54
    assert len({r['run'] for r in records}) == 54
    groups = {}
    stages = []
    stage_runs = []
    captures = []
    sdk_work = []
    for entry in records:
        folder = OUT/'raw'/entry['run']
        record = json.loads((folder/'result.json').read_text(encoding='utf-8'))
        assert set(record) == set(entry)
        assert all(entry[k] == str(v) for k,v in record.items()), entry['run']
        rows = trace(folder/'paint.csv')
        recomputed, samples = metrics(rows)
        assert all(record[k] == v for k, v in recomputed.items())
        turns = list(csv.DictReader((folder/'turns.csv').open()))
        assert [int(t['turn']) for t in turns] == list(range(1,21))
        assert [float(t['input_to_present_ms']) for t in turns] == samples
        process = json.loads((folder/'process.json').read_text(encoding='utf-8'))
        layout = json.loads((folder/'layout.json').read_text(encoding='utf-8'))
        assert process['exit_code'] == 0
        assert '--offscreen' in process['command']
        font_path = process['command'][process['command'].index('--font')+1]
        assert Path(font_path) == Path(protocol['fonts'][record['font']]['path'])
        assert all(line.split('\t')[3] == 'PASS' for line in
                   (folder/'drive.txt').read_text(encoding='utf-8').splitlines() if line.startswith('STEP\t'))
        assert layout['client'] == [record['client_width'], record['client_height']]
        assert layout['font'] == 18 and abs(layout['line_height']-record['line_height']) < .00001
        assert layout['epoch'] == layout['frame_epoch'] and layout['scale'] == 1
        if record['repeat'] == 1:
            capture = json.loads((folder/'capture.json').read_text())
            assert capture['client'] == layout['client'] and capture['position'] == [-32000,-32000]
            assert (folder/'window.png').exists()
            captures.append(dict(run=record['run'], **capture))
        key = (record['font'], record['line_height'], record['client_width'])
        groups.setdefault(key, []).append(record | {'cpu_pct': process['system_cpu_busy_pct']})
        begin = next(t for n,t,v in rows if n=='keys_begin')
        end = next(t for n,t,v in rows if n=='keys_end')
        # Existing check_step4.py miss accounting: uncached pager + raster work.
        work_samples=[]
        work_stage=None
        hit=False
        for name,t,value in rows:
            if not begin<t<end:
                continue
            if name=='sdk_job_begin':
                work_stage,hit={},False
            elif name=='cache_hit':
                hit=True
            elif work_stage is not None and name.startswith('stage_'):
                work_stage[name]=value
            elif name=='sdk_job_end' and work_stage is not None:
                if not hit and work_stage.get('stage_raster_ms',0)>0:
                    work_samples.append(work_stage['stage_anchor_pager_ms']+work_stage['stage_raster_ms'])
                work_stage=None
        assert work_samples
        sdk_work.append(dict(run=record['run'],font=record['font'],line_height=record['line_height'],
            client_width=record['client_width'],repeat=record['repeat'],samples=len(work_samples),
            no_cache_sdk_p50_ms=percentile(work_samples,.5),no_cache_sdk_p95_ms=percentile(work_samples,.95)))
        inputs = [r for r in rows if r[0]=='input_gen' and begin<r[1]<end]
        assert len(inputs) == 20
        current_stages = []
        for i, inp in enumerate(inputs):
            bound = inputs[i+1][1] if i+1<len(inputs) else end
            present = next(r for r in rows if r[0]=='present_gen' and inp[1]<r[1]<bound and r[2]!=inp[2])
            assert present[2] > inp[2]
            ready = [r for r in rows if r[0]=='sdk_ready_gen' and inp[1]<r[1]<present[1] and r[2]==present[2]]
            stage = dict(run=record['run'], turn=i+1, input_generation=int(inp[2]),
                               present_generation=int(present[2]), input_to_present_ms=present[1]-inp[1],
                               input_to_sdk_ready_ms=ready[-1][1]-inp[1] if ready else '',
                               sdk_ready_to_present_ms=present[1]-ready[-1][1] if ready else '')
            stages.append(stage)
            current_stages.append(stage)
        stage_run = dict(run=record['run'], system_cpu_busy_pct=process['system_cpu_busy_pct'],
                         cache_hits=record['cache_hits'])
        for metric in ('input_to_sdk_ready_ms', 'sdk_ready_to_present_ms'):
            values = [s[metric] for s in current_stages if s[metric] != '']
            assert len(values) == 20, record['run']
            stage_run[metric+'_p50'] = percentile(values, .5)
            stage_run[metric+'_p95'] = percentile(values, .95)
        stage_runs.append(stage_run)
    assert len(groups)==18 and all(len(g)==3 for g in groups.values())
    expected = set(itertools.product(FONTS, LINE_HEIGHTS, [w for w,h in VIEWPORTS]))
    assert set(groups) == expected
    assert all({r['repeat'] for r in g} == {1,2,3} for g in groups.values())
    assert all(len({r['total_pages'] for r in g}) == 1 for g in groups.values())
    write_csv(OUT/'stages.csv', stages)
    write_csv(OUT/'stage-runs.csv', stage_runs)
    write_csv(OUT/'sdk-work.csv', sdk_work)
    write_json(OUT/'captures.json', captures)

    def med(key, metric):
        return stats.median(r[metric] for r in groups[key])

    def span(key, metric):
        values = [r[metric] for r in groups[key]]
        return max(values)-min(values)

    def dispersion(key, metric):
        return 100*span(key, metric)/med(key, metric)

    def f(number):
        return f'{number:.2f}'

    comparisons=[]
    for height, (width, _) in itertools.product(LINE_HEIGHTS, VIEWPORTS):
        a, b = ('serif',height,width), ('sans',height,width)
        delta = med(a,'page_turn_p95_ms')-med(b,'page_turn_p95_ms')
        noise = max(span(a,'page_turn_p95_ms'), span(b,'page_turn_p95_ms'))
        comparisons.append(dict(line_height=height, client_width=width,
            serif_p95_ms=med(a,'page_turn_p95_ms'), sans_p95_ms=med(b,'page_turn_p95_ms'),
            delta_ms=delta, delta_pct=100*delta/med(b,'page_turn_p95_ms'),
            serif_p95_range_ms=span(a,'page_turn_p95_ms'), sans_p95_range_ms=span(b,'page_turn_p95_ms'),
            delta_exceeds_both_ranges=abs(delta)>noise,
            serif_font_load_ms=med(a,'font_load_ms'), sans_font_load_ms=med(b,'font_load_ms'),
            first_screen_delta_ms=med(a,'first_screen_render_ms')-med(b,'first_screen_render_ms'),
            open_including_font_delta_ms=med(a,'open_including_font_ms')-med(b,'open_including_font_ms')))
    write_csv(OUT/'font-comparisons.csv', comparisons)

    measured = ['open_including_font_ms','font_load_ms','first_screen_render_ms','page_turn_p50_ms',
                'page_turn_p95_ms','turn_raster_p95_ms','peak_working_set_mib','peak_commit_mib','total_pages']
    dispersion_rows=[]
    for key, group in groups.items():
        for metric in measured:
            dispersion_rows.append(dict(font=key[0],line_height=key[1],client_width=key[2],metric=metric,
                repeat_1=next(r[metric] for r in group if r['repeat']==1),
                repeat_2=next(r[metric] for r in group if r['repeat']==2),
                repeat_3=next(r[metric] for r in group if r['repeat']==3),
                range=span(key,metric),dispersion_pct=dispersion(key,metric),
                over_10pct=dispersion(key,metric)>10,
                cpu_busy_min_pct=min(r['cpu_pct'] for r in group),
                cpu_busy_max_pct=max(r['cpu_pct'] for r in group)))
    write_csv(OUT/'dispersion.csv', dispersion_rows)
    regression = json.loads((OUT/'regression.diff.json').read_text())
    actual = json.loads((OUT/'regression.json').read_text())
    assert len(actual['books'])==19 and not actual['summary']['failed_books']
    assert actual['dll_sha256'] == protocol['build']['dll']['sha256']
    assert regression['comparable']
    repeat_actual = json.loads((OUT/'regression-repeat.json').read_text())
    repeat_diff = json.loads((OUT/'regression-repeat.diff.json').read_text())
    assert repeat_actual['dll_sha256'] == actual['dll_sha256']
    assert repeat_actual['summary']['successful_books'] == 19
    assert repeat_diff['comparable'] and not repeat_diff['needs_review']
    assert repeat_actual['content_fingerprint'] == actual['content_fingerprint']
    assert all(not b['page_count_changed'] and not b['glyph_count_changed'] and
               not b['hash_changed_pages'] and not b['source_changed'] for b in repeat_diff['books'])
    baseline_actual = json.loads((OUT/'baseline-regression.json').read_text())
    baseline_diff = json.loads((OUT/'baseline-regression.diff.json').read_text())
    baseline_reference = json.loads((ROOT/'evidence/realbooks-baseline-20261107/baseline.json').read_text())
    assert baseline_actual['dll_sha256'] == baseline_reference['dll_sha256']
    assert baseline_actual['summary']['successful_books'] == 19 and not baseline_diff['needs_review']
    flagged = sum(dispersion(k,'page_turn_p95_ms')>10 for k in groups)
    unacceptable = sum(med(k,'page_turn_p95_ms')>protocol['unacceptable_p95_ms'] for k in groups)
    severe = sum(med(k,'page_turn_p95_ms')>protocol['severe_p95_ms'] for k in groups)
    serif=('serif',1.75,1552); sans=('sans',1.75,1552); high=('serif',1.9,1552)
    default_comparison = next(c for c in comparisons if c['client_width']==1552 and c['line_height']==1.75)
    delta=100*(med(serif,'page_turn_p95_ms')/med(sans,'page_turn_p95_ms')-1)
    lines = ['# 字体与排版性能基准 · 2026-11-07', '',
        '18 组 × 3 个独立进程，共 54 次、1,080 次翻页。每格取三次中位数；完整单次数据在 '
        '[runs.csv](../../evidence/typography-bench-20261107/runs.csv)，逐次原始 paint.csv 和截图在同目录 raw/。', '',
        '## 三个数字结论', '',
        f"1. **字体**：1552×928、行高 1.75，衬线 p95 {f(med(serif,'page_turn_p95_ms'))} ms，"
        f"无衬线 {f(med(sans,'page_turn_p95_ms'))} ms，差 {f(default_comparison['delta_ms'])} ms（{delta:+.2f}%）。"
        f"三次范围分别为 {f(span(serif,'page_turn_p95_ms'))} / {f(span(sans,'page_turn_p95_ms'))} ms；"
        f"差值{'同时超过' if default_comparison['delta_exceeds_both_ranges'] else '未同时超过'}两组各自的离散范围。",
        '2. **行高**：1552×928 衬线，1.60→1.75→1.90 的 p95 为 '+
        '→'.join(f(med(('serif',h,1552),'page_turn_p95_ms')) for h in LINE_HEIGHTS)+' ms，页数为 '+
        '→'.join(str(int(med(('serif',h,1552),'total_pages'))) for h in LINE_HEIGHTS)+'。',
        f"3. **文件与首屏**：衬线 {f(protocol['fonts']['serif']['bytes']/1048576)} MiB，"
        f"无衬线 {f(protocol['fonts']['sans']['bytes']/1048576)} MiB；1552×928、1.75 的字体加载分别为 "
        f"{f(med(serif,'font_load_ms'))} / {f(med(sans,'font_load_ms'))} ms，首屏渲染分别为 "
        f"{f(med(serif,'first_screen_render_ms'))} / {f(med(sans,'first_screen_render_ms'))} ms。", '',
        '## 固定条件与口径', '',
        f"- 同一本《紅樓夢》、同一 DLL `{protocol['build']['dll']['sha256']}`、同一宿主 EXE `{protocol['build']['exe']['sha256']}`。",
        '- 字号 18 px，注入排版 DPI 96；两种客户区分别精确为 1242×711、1552×928。正文宽均为 612 px，高分别为 551、768 px。系统实际窗口 DPI 为 120，含边框整窗实测 1260×758、1570×975，与任务给出的整窗 1242×742、1552×955 不同；矩阵严格固定的是所要求的客户区。',
        '- 每次从干净书库副本启动，字体在启动时加载，导入不计入打开。字体/书/EXE/DLL/构建命令和哈希在 protocol.json；字体文件不入库。OS 文件缓存未清空，属于暖缓存、独立进程测量。',
        '- 排版注入 96 DPI 后 18 px 不随系统缩放增大。沿用宿主整数像素舍入，正文行距 1.60/1.75/1.90 对应 29/32/34 px；标题等仍服从原书 CSS。',
        '- 打开含字体 = font_load_ms + book_open_begin 到首个非零 present_gen。另存不含字体的 book_open_to_present_ms 和完整进程启动到首屏 startup_to_first_present_ms。首屏渲染 = 第一个 render_ms。该书首屏为封面，不能将首屏差异全部归因于字形或文件大小。',
        '- 翻页 = paint.csv 中 input_gen 到下一个不同 generation 的 present_gen；在下一输入前配对，20 次 PageDown。p50/p95 用 nearest-rank（第 10/19 个有序样本）。保留原有追踪事件；另列栅格化 p95，避免混淆端到端延迟与 SDK 渲染成本。',
        '- 内存为 Windows 进程 PeakWorkingSetSize / PeakPagefileUsage（MiB），在第 20 次翻页后、全书页数遍历前采集；每次独立遍历全书，页数必须三次一致。',
        '- present_gen 位于 GdiFlush 后，表示 GDI 提交完成，不包含显示器扫描或 DWM 可见帧确认。顺序翻页保留宿主预取缓存；turn_raster_p95_ms 统计翻页区间内所有 render_ms，包含预取绘制。',
        '- 按种子 20261107+轮次打乱顺序，三轮串行。离散度 = (最大值−最小值)/中位数×100%，不是置信区间。',
        '- 测量前预设：端到端翻页 p95 >100 ms 为未达目标，>200 ms 为严重慢档。这是本轮响应目标，不是 FPS；不将 1000/p95 冒充帧率。',
        '- 由现有 examples/reader.c 生成仓库外宿主副本，仅注入可变行高、字体计时和数页命令；产品源码未改。所有窗口 --offscreen，位置 (-32000,-32000)，使用既有 ops\\capture_window.py 截图。', '',
        '## 18 组中位数', '']
    for width, view_height in VIEWPORTS:
        lines += [f'### {width}×{view_height}', '']
        rows=[]
        for font,height in itertools.product(FONTS, LINE_HEIGHTS):
            key=(font,height,width)
            rows.append([NAMES[font],f'{height:.2f}',*[f(med(key,m)) for m in
                ['open_including_font_ms','first_screen_render_ms','page_turn_p50_ms','page_turn_p95_ms','turn_raster_p95_ms',
                 'peak_working_set_mib']],int(med(key,'total_pages')),
                f(dispersion(key,'page_turn_p95_ms'))+('% ⚑' if dispersion(key,'page_turn_p95_ms')>10 else '%')])
        lines += [table(['字体','行高','打开含字体 ms','首屏渲染 ms','翻页 p50 ms','翻页 p95 ms',
                         '栅格 p95 ms','峰值工作集 MiB','页数','p95 离散度'],rows), '']
    lines += ['## 衬线与无衬线', '',
        table(['客户区宽','行高','衬线 p95 ms','无衬线 p95 ms','差值 ms / %','两组范围 ms','差值超过两组离散范围'],
            [[c['client_width'],c['line_height'],f(c['serif_p95_ms']),f(c['sans_p95_ms']),
              f(c['delta_ms'])+' / '+f(c['delta_pct'])+'%',
              f(c['serif_p95_range_ms'])+' / '+f(c['sans_p95_range_ms']),
              '是' if c['delta_exceeds_both_ranges'] else '否'] for c in comparisons]), '',
        '判定口径：绝对差值大于两组各自的最大值−最小值。逐组原值和比较在 font-comparisons.csv。', '',
        '## 行高对 p95 和页数的影响', '',
        table(['客户区宽','字体','p95 ms：1.60 → 1.75 → 1.90','页数：1.60 → 1.75 → 1.90','页数 1.60→1.90'],
              [[width,NAMES[font], ' → '.join(f(med((font,h,width),'page_turn_p95_ms')) for h in LINE_HEIGHTS),
                ' → '.join(str(int(med((font,h,width),'total_pages'))) for h in LINE_HEIGHTS),
                f(100*(med((font,1.9,width),'total_pages')/med((font,1.6,width),'total_pages')-1))+'%']
               for width,_ in VIEWPORTS for font in FONTS]), '',
        '## 字体文件大小与首屏', '',
        table(['字体','字节数','MiB'],[[NAMES[k],v['bytes'],f(v['bytes']/1048576)] for k,v in protocol['fonts'].items()]), '',
        table(['客户区宽','行高','衬线加载 ms','无衬线加载 ms','首屏渲染差 ms','含字体打开差 ms'],
              [[c['client_width'],c['line_height'],f(c['serif_font_load_ms']),f(c['sans_font_load_ms']),
                f(c['first_screen_delta_ms']),f(c['open_including_font_delta_ms'])] for c in comparisons]), '',
        '正差值表示衬线更慢。字体文件相差 '+f((protocol['fonts']['serif']['bytes']-protocol['fonts']['sans']['bytes'])/1048576)+
        ' MiB；本实验同时改变格式、字形和字体内容，不能分离“每 MB 的加载成本”。', '',
        '## 离散度及原因', '',
        f'翻页 p95 超过 10% 的配置 {flagged}/18。全部指标、三次原值、CPU 忙碌度及 >10% 标记在 dispersion.csv；页数离散度均为 0%。', '',
        table(['配置','p95 三次 ms','p95 离散度','其余 >10% 指标','系统 CPU 忙碌度范围'],
              [[f'{k[0]} / {k[1]:.2f} / {k[2]}',
                ' / '.join(f(next(r['page_turn_p95_ms'] for r in g if r['repeat']==i)) for i in (1,2,3)),
                f(dispersion(k,'page_turn_p95_ms'))+'%',
                ', '.join(m for m in measured if m!='page_turn_p95_ms' and dispersion(k,m)>10) or '无',
                f(min(r['cpu_pct'] for r in g))+'–'+f(max(r['cpu_pct'] for r in g))+'%']
               for k,g in sorted(groups.items())]), '',
        '原因判读：environment.json 记录测量开始时其他回归/编译进程，process.json 记录每次系统 CPU 忙碌度。'
        '这些后台任务及消息调度是干扰来源；没有独占 CPU 或频率/温度追踪，不能把每个异常值精确归因。'
        '首屏与加载计时样本很短，绝对值的少量波动也会超过 10%。按预定顺序保留全部 54 次，不按速度删点。', '']
    valid = [s for s in stages if s['sdk_ready_to_present_ms']!='']
    lines += [f"逐翻页阶段诊断（stages.csv）：{len(valid)}/1080 次有匹配 SDK ready；"
        f"input→ready 中位 {f(stats.median(s['input_to_sdk_ready_ms'] for s in valid))} ms，"
        f"ready→present 中位 {f(stats.median(s['sdk_ready_to_present_ms'] for s in valid))} ms。"
        '因此端到端 p95 不能直接当作字体光栅化耗时。', '',
        '既有 paint.csv 验收的 miss_p95_ms 是无缓存 SDK pager+render；下表复用该计算，包含翻页间的预取工作。'
        '逐次值在 sdk-work.csv。原验收宽度 1280/2560 的 25/35 ms 门槛与本轮客户区不同，不直接套用。', '',
        table(['字体','行高','1242 无缓存 SDK p95 ms','1552 无缓存 SDK p95 ms'],
            [[NAMES[font],height,*[f(stats.median(r['no_cache_sdk_p95_ms'] for r in sdk_work
                if (r['font'],r['line_height'],r['client_width'])==(font,height,width))) for width,_ in VIEWPORTS]]
             for font,height in itertools.product(FONTS,LINE_HEIGHTS)]), '',
        '## 默认值建议', '',
        f'按预设门槛，{unacceptable}/18 组超过 100 ms，{severe}/18 组超过 200 ms。',
        '超过 200 ms 的配置：'+('; '.join(f'{k[0]} / {k[1]:.2f} / {k[2]}' for k in sorted(groups)
            if med(k,'page_turn_p95_ms')>protocol['severe_p95_ms']) or '无')+'。', '']
    serif=('serif',1.75,1552); sans=('sans',1.75,1552); high=('serif',1.9,1552)
    delta=100*(med(serif,'page_turn_p95_ms')/med(sans,'page_turn_p95_ms')-1)
    lines += [f"1552 视口默认衬线 1.75：p95 = {f(med(serif,'page_turn_p95_ms'))} ms；"
        f"无衬线 1.75 = {f(med(sans,'page_turn_p95_ms'))} ms，相对变化 {delta:+.2f}%。"
        f"衬线 1.90 = {f(med(high,'page_turn_p95_ms'))} ms，页数 {int(med(high,'total_pages'))}。", '',
        '建议保持衬线 1.75 的当前默认值：本轮在共享机器上的三次重复不足以支持为性能下调行高或改回无衬线。'
        '超过门槛的配置应保留为性能问题；先复测/定位端到端呈现路径，再决定默认值。'
        '本轮没有修改产品默认值。', '',
        '## 19 本真书回归与范围', '',
        f"**矩阵指定 DLL 的两次独立全量运行**：均为 {repeat_actual['summary']['successful_books']}/19 本成功、"
        f"{repeat_actual['summary']['total_pages']:,} 页、{repeat_actual['summary']['total_glyphs']:,} 字形；"
        f"页数变化 0，逐页像素哈希变化 {repeat_diff['hash_changed_pages']}，内容指纹一致。"
        'regression-repeat.json / regression-repeat.diff.json 保存独立复跑及比较；命令在 regression-repeat-command.json。', '',
        f"使用既有基线的原 DLL 重跑：{baseline_actual['summary']['successful_books']}/19 本成功，"
        f"{baseline_actual['summary']['total_pages']:,} 页，{baseline_actual['summary']['total_glyphs']:,} 字形；"
        f"变化页数 {baseline_diff['hash_changed_pages']}，needs_review={baseline_diff['needs_review']}。"
        'baseline-regression.json / baseline-regression.diff.json 保存逐页结果，命令在 baseline-regression-command.json。', '',
        f"另以矩阵指定 DLL 全量运行：{actual['summary']['successful_books']}/19 本成功，"
        f"{actual['summary']['total_pages']:,} 页，{actual['summary']['total_glyphs']:,} 字形；"
        f"与既有基线有 {regression['hash_changed_pages']} 个共同序号页的像素哈希差异，"
        f"总页数变化 {actual['summary']['total_pages']-baseline_reference['summary']['total_pages']:+d} 页，"
        f"needs_review={regression['needs_review']}。"
        'regression.json / regression.diff.json 保留完整跨 DLL 比较，不将其标为零差异通过。', '',
        f"基线 DLL SHA-256 `{baseline_reference['dll_sha256']}`，矩阵 DLL SHA-256 `{actual['dll_sha256']}`。"
        '两个 DLL 的输出差异需另行审计；本次提交没有改动引擎、头文件、宿主或 workflow。'
        '相对 protocol.json 中构建源码 revision 的受保护目录 diff 为空，未手动触发 CI、未取消 workflow。', '',
        '## 复现', '', '```powershell',
        'python -X utf8 tools/perf/typography_bench.py selfcheck',
        'python -X utf8 tools/perf/typography_bench.py build --work C:/Users/Oscar/Documents/Codex/typo-bench-work-20261107 --sdk-build C:/Users/Oscar/Documents/Codex/cjk-justify-20261106/build',
        'python -X utf8 tools/perf/typography_bench.py run --work C:/Users/Oscar/Documents/Codex/typo-bench-work-20261107 --output evidence/typography-bench-20261107 --capture C:/Users/Oscar/Documents/Codex/EXReader-typo-20261106/ops/capture_window.py',
        'python -X utf8 tools/perf/typography_report.py', '```', '',
        '重测使用新的 work/output 目录；已有 result.json 的轮次会续跑，未完成目录需先归档。'
        'excluded-attempt.json 记录最初中断轮次；该轮全部排除，不参与上述统计。', '']
    document=ROOT/'docs/validation/TYPOGRAPHY-BENCH.md'
    document.write_text('\n'.join(lines),encoding='utf-8')
    write_json(OUT/'audit.json',dict(runs=54,configs=18,turns=1080,captures=18,
        hashes_verified=True,raw_metrics_recomputed=True,product_sources_unchanged=True,
        p95_dispersion_over_10pct_groups=flagged,unacceptable_groups=unacceptable,severe_groups=severe,
        regression_successful_books=actual['summary']['successful_books'],
        regression_changed_pages=regression['hash_changed_pages'],
        same_dll_repeat_successful_books=repeat_actual['summary']['successful_books'],
        same_dll_repeat_changed_pages=repeat_diff['hash_changed_pages'],
        same_dll_repeat_passed=not repeat_diff['needs_review'],
        baseline_regression_successful_books=baseline_actual['summary']['successful_books'],
        baseline_regression_changed_pages=baseline_diff['hash_changed_pages'],
        baseline_regression_passed=not baseline_diff['needs_review'],report=str(document.relative_to(ROOT))))
    print((OUT/'audit.json').read_text())


if __name__ == '__main__':
    main()
