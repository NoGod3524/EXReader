"""Regenerate this campaign's report/index from retained JSON; never changes budgets."""
import json
from pathlib import Path
import shutil
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'tools/perf'))
from e1_capture import sha, write


def read(path):
    return json.loads(path.read_bytes())


def main():
    primary = read(HERE / 'normalized/samples.json')
    environment = read(HERE / 'normalized/env.json')
    budgets = read(HERE / 'normalized/proposed-budgets.json')
    verification = read(HERE / 'strict-verification.json')
    cpu = environment['cpu'][0]
    lines = ['## 实测结论：暂不恢复必需检查', '',
        f"环境：{cpu['Name']}，{cpu['NumberOfCores']} 物理核 / {cpu['NumberOfLogicalProcessors']} 逻辑核，RAM {environment['system']['memory_bytes']} bytes；",
        f"{environment['os']['caption']} / build {environment['os']['build']} / AMD64；{environment['compiler']['version'].splitlines()[0]}，Release `-O3 -DNDEBUG`。",
        '电源为 Balanced、AC 供电，节电关闭；OS 报告 2200 MHz。Lenovo 83JT 无 SMBIOS 虚拟机签名，HypervisorPresent=true，二者分开留证。',
        f"环境比较键：`{environment['comparison_key']}`。完整动态负载和频率见 env.json 与各 trial 的 load_before/load_after。", '',
        '普通优先级 27 次、归一化轮 21 次、独立候选 15 次全部保留。',
        '1280×800 与 2560×1440 各取得一组三次全部指标极差比 <10% 的完整批次；',
        '默认组最终首屏总耗时极差比为 **13.16%**，独立候选默认组为 **29.51%**，未满足稳定性验收。', '',
        '**严格本地验证失败**：预算先导出，随后才启动独立候选。15 个新进程均在原数值上界内，',
        '环境/源码/二进制/字体/输入与 RGBA/文本/位置签名匹配；基线资格与候选稳定性仍失败。',
        '结果见 [strict-verification.json](../../evidence/perf-e1-20261107/strict-verification.json)。', '',
        '主表使用归一化轮每组最后完整三次；全部历史批次在各次 summary.md、samples.json 与 raw/。', '',
        '| 配置 | 次数 | 打开 ms | 首屏总耗时 ms | 首屏绘制 ms | 翻页 p50 ms | 翻页 p95 ms | 峰值 bytes |',
        '|---|---:|---:|---:|---:|---:|---:|---:|']
    selected = []
    for name, group in primary['groups'].items():
        for index, trial in enumerate(group['batches'][-1]['trials'], 1):
            m = trial['metrics']
            values = ' | '.join(f'{m[k]:.4f}' for k in ('open_ms', 'first_visible_ms', 'first_render_ms', 'turn_p50_ms', 'turn_p95_ms'))
            lines.append(f"| {name} | {index} | {values} | {m['peak_rss_bytes']} |")
            selected.append({'configuration': name, 'run': index, 'metrics': m,
                             'raw': 'normalized/' + trial['stdout'], 'sha256': trial['stdout_sha256']})
    lines += ['', '### 三次的 p50 / p95 / max 与离散度', '',
              '| 配置 | 指标 | p50 | p95 (=max) | CV % | 极差/p50 % |', '|---|---|---:|---:|---:|---:|']
    for name, group in primary['groups'].items():
        for key, s in group['final']['metrics'].items():
            lines.append(f"| {name} | {key} | {s['p50']:.6f} | {s['p95']:.6f} | {s['cv_pct']:.3f} | {s['range_over_median_pct']:.3f} |")
    lines += ['', '### 配置差异是否超出噪声', '',
        '- 默认 → 1280×800：首屏绘制中位数 +34.92%、翻页 p95 中位数 +20.40%，均超过双方观测极差；打开、首屏总耗时、RSS 差异未被分辨。',
        '- 默认 → 2560×1440：首屏绘制 +328.59%、翻页 p95 +236.42%、首屏总耗时 +38.60%、RSS +7.92%，均超过双方观测极差；打开差异未被分辨。',
        '- 1280×800 → 2560×1440：首屏绘制 +217.67%、翻页 p95 +179.42%、首屏总耗时 +47.57%、RSS +7.87%，均超过双方观测极差；打开差异未被分辨。', '',
        '这些判定只覆盖本机固定语料/字体及观测噪声范围。完整逐指标结果在 normalized/samples.json 的 comparisons。', '',
        '### 可执行的本机阈值提案', '',
        '以下值原样来自 normalized/proposed-budgets.json；**整体 eligible=false，仅供审议，当前禁止用于恢复。**',
        '默认组噪声不是扩大预算的理由；先取得稳定基线，再预冻结并完成独立严格复验。', '',
        '| 配置 | 打开 ms | 首屏总耗时 ms | 首屏绘制 ms | 翻页 p50 ms | 翻页 p95 ms | 峰值 bytes |',
        '|---|---:|---:|---:|---:|---:|---:|']
    for name, limits in budgets['limits'].items():
        values = ' | '.join(f'{limits[k]:.3f}' for k in ('open_ms', 'first_visible_ms', 'first_render_ms', 'turn_p50_ms', 'turn_p95_ms'))
        lines.append(f"| {name} | {values} | {limits['peak_rss_bytes']} |")
    lines += ['', f"原始样本 SHA-256：`{budgets['samples_sha256']}`。",
        f"导出器 SHA-256：`{budgets['exporter_sha256']}`。",
        f"提案预算文件 SHA-256：`{sha(HERE / 'normalized/proposed-budgets.json')}`。", '',
        '25% 延迟和 5% + 1 MiB 内存余量覆盖了本次独立候选全部 15 个进程，但不能替代 <10% 的稳定性前提。',
        '后续保持 AC、CPU 0、高优先级、相同电源和编译配置，在安静或专用宿主取得稳定基线；再使用其预导出预算启动独立采样。',
        '同环境历史 p95 >1.5× 人工复核仍开启；本机 Windows 预算不替代三个现有 Linux 预算。', '',
        '```powershell',
        'python tools/perf/check_e1.py evidence/perf-e1-20261107/baseline evidence/perf-e1-20261107/normalized evidence/perf-e1-20261107/candidate',
        'python tools/perf/e1_verify.py evidence/perf-e1-20261107/normalized evidence/perf-e1-20261107/candidate NEW-verification.json',
        '```', '', '严格验证在本次数据上返回 1；失败项为基线资格与默认组稳定性，数值超限项为零。', '']
    advisory_path = HERE / 'advisory-check/samples.json'
    if (HERE / 'advisory-check/summary.md').exists():
        advisory = read(advisory_path)
        lines += ['### 现有 advisory 阈值在本机是否可达', '',
            '八份冻结原件、相同 Noto 字体、800×1000/margin32、32 顺序页与 16 随机请求，每份五个新进程。',
            '输入 ZIP 的 source/run/attempt/digest、八份输入与许可证散列已核；没有启动 CI。',
            '以下为数值诊断，不把跨 OS/CPU/编译器比较解释为预算接受。未运行最终参考 PPM/Poppler 审阅阶段；RSS 覆盖计时计划及签名。', '',
            (HERE / 'advisory-check/summary.md').read_text(encoding='utf-8').split('advisory: true; accepted: false.', 1)[1].split('| Budget environment')[0].strip(), '']
        failures = {name: [] for name in next(iter(advisory['cases'].values()))['numeric_comparison']}
        for case, result in advisory['cases'].items():
            for env, metrics in result['numeric_comparison'].items():
                failures[env] += [case + '/' + key for key, value in metrics.items() if not value['within']]
        lines += ['| 旧预算环境 | 超限指标数 / 80 | 主要超限项 |', '|---|---:|---|']
        for env, items in failures.items():
            detail = '6 份文档 open_ms' if env == 'amd-epyc-7763' else '7 份文档 open_ms' if env == 'intel-xeon-8573c' else '8 份文档 open_ms；部分字体打开、Moby/NASA 首屏与翻页'
            lines.append(f'| {env} | {len(items)} / 80 | {detail} |')
        lines += ['', '逐文档逐指标的原数值、原预算与 within 布尔值见 advisory-check/samples.json 的 numeric_comparison；超限完整列表见 advisory-check/summary.md。',
            'EPYC 7763 与 Xeon 的首屏/翻页/RSS 均在其原数值上界内，但打开指标超限；CPU、OS、编译器和 SDK 源码身份也与旧冻结对象不同，不能把差异直接认定为同环境回归。', '']
        lines += ['结论：' + ('三套现有数值预算均存在超限，不能声称本机达到完整现有阈值。' if all(failures.values()) else '各环境的超限项见上表；环境匹配条件仍全部不符，不能授予现有预算通过。'),
            '即使数值可达，也须登记独立 Windows 环境与真实语料预算，并在实际候选上完成政策规定的完整严格复验和 owner 恢复记录。', '']
    proposal = ROOT / 'docs/validation/PERF-E1-PROPOSAL.md'
    prefix = proposal.read_text(encoding='utf-8').split('<!-- E1_RESULTS -->')[0].split('## 实测结论：暂不恢复必需检查')[0]
    conclusion = '**结论：已完成采集和独立严格本地审计；默认组稳定性未达标，暂不恢复 performance 必需检查。**'
    if conclusion not in prefix:
        first, rest = prefix.split('\n', 1)
        prefix = first + '\n\n' + conclusion + '\n' + rest
    proposal.write_text(prefix.rstrip() + '\n\n' + '\n'.join(lines), encoding='utf-8')
    shutil.copyfile(HERE / 'normalized/env.json', HERE / 'env.json')
    index = {'schema': 1, 'kind': 'campaign_index', 'advisory': True, 'accepted': False,
        'primary': 'normalized/samples.json', 'selected_three_per_configuration': selected,
        'captures': {name: {'samples': name + '/samples.json', 'sha256': sha(HERE / name / 'samples.json'),
                           'processes': sum(len(b['trials']) for g in read(HERE / name / 'samples.json')['groups'].values() for b in g['batches'])}
                     for name in ('baseline', 'normalized', 'candidate')},
        'strict_verification': verification, 'proposed_budget_sha256': sha(HERE / 'normalized/proposed-budgets.json')}
    if (HERE / 'advisory-check/summary.md').exists():
        index['advisory'] = True
        index['advisory_capture'] = {'samples': 'advisory-check/samples.json', 'sha256': sha(advisory_path), 'processes': 40}
    write(HERE / 'samples.json', index)
    (HERE / 'summary.md').write_text('# E1 campaign summary\n\n' + '\n'.join(lines).replace('../../evidence/perf-e1-20261107/', '') + '\n', encoding='utf-8')
    print('Regenerated proposal, root env.json, samples.json index and summary.md')


if __name__ == '__main__':
    main()
