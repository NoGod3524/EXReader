#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Archive machine-readable T1 evidence and render its acceptance tables."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import shutil
from zipfile import ZipFile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def zip_audit(work, manifest):
    fields = ('date_time', 'create_system', 'create_version', 'extract_version',
              'external_attr', 'internal_attr', 'flag_bits', 'compress_type', 'extra', 'comment')
    result = {}
    for stage, folder in (('before', 'before-control'), ('after', 'after')):
        result[stage] = {}
        for mode in ('noop', 'edited'):
            rows = []
            for item in manifest['documents']:
                actual = work / folder / item['id'] / mode / 'actual.docx'
                with ZipFile(HERE / item['path']) as a, ZipFile(actual) as b:
                    left, right = {n.filename: n for n in a.infolist()}, {n.filename: n for n in b.infolist()}
                    assert left.keys() == right.keys()
                    rows.append(dict(id=item['id'], entries=len(left),
                        archive_sha256_changed=hashlib.sha256((HERE / item['path']).read_bytes()).digest() != hashlib.sha256(actual.read_bytes()).digest(),
                        entry_order_changed=a.namelist() != b.namelist(), archive_comment_changed=a.comment != b.comment,
                        changed_entries={field: [name for name in left if getattr(left[name], field) != getattr(right[name], field)] for field in fields}))
            result[stage][mode] = rows
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, default=ROOT / 'build/t1')
    args = parser.parse_args()
    work, evidence = args.work.resolve(), ROOT / 'docs/docx-real'
    before = read(work / 'before-control/report.json')
    text = read(work / 'stage-text-matrix/report.json')
    paragraph = read(work / 'stage-paragraph-matrix/report.json')
    after = read(work / 'after/report.json')
    manifest = read(HERE / 'manifest.json')
    containers = zip_audit(work, manifest)
    for report in (before, text, paragraph, after):
        for rows in report['matrices'].values():
            assert len(rows) == 30
            assert [(row['id'], row['source_sha256']) for row in rows] == [(item['id'], item['sha256']) for item in manifest['documents']]
    ctest = (work / 'ctest.txt').read_text(encoding='utf-8')
    total = re.search(r'100% tests passed(?:, 0 tests failed)? out of (\d+)', ctest)
    assert total and int(total[1]) >= 391, 'full CTest suite must pass, including baseline and 70 new cases'
    books, diff = read(work / 'realbooks.json'), read(work / 'realbooks.diff.json')
    assert books['summary']['successful_books'] == 19 and not diff['needs_review'] and diff['hash_changed_pages'] == 0
    for mode in ('noop', 'edited'):
        assert before['summary'][mode]['passed'] == 531 and text['summary'][mode]['passed'] == 531
        assert paragraph['summary'][mode]['passed'] == 537
        assert after['summary'][mode]['passed'] == 540 and after['summary'][mode]['payload_exact'] == 30
    assert all(not row['additional_main_changes'] and not row['additional_failed_metrics'] for row in after['edit_side_effects'])
    evidence.mkdir(parents=True, exist_ok=True)
    for name, report in (('before', before), ('text', text), ('paragraph', paragraph), ('after', after), ('realbooks', books)):
        payload = (json.dumps(report, ensure_ascii=False, indent=2) + '\n').encode()
        (evidence / (name + '.json.gz')).write_bytes(gzip.compress(payload, mtime=0))
    (evidence / 'zip-container.json').write_text(json.dumps(containers, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    for name in ('ctest.txt', 'build-final.txt', 'configure-final.txt', 'red-text-command.txt',
                 'red-paragraph-markers.txt', 'red-section-tail.txt', 'green-regressions.txt',
                 'realbooks.diff.json', 'layers.txt'):
        shutil.copyfile(work / name, evidence / name)
    for stage in ('control', 'stage-text', 'stage-paragraph'):
        shutil.copyfile(work / stage / 'build.json', evidence / (stage + '-build.json'))
    assert all('AssertionError:' in (evidence / ('red-' + name + '.txt')).read_text(encoding='utf-8')
               for name in ('text-command', 'paragraph-markers', 'section-tail'))
    lines = ['# T1：真实 DOCX 结构往返验收', '',
        '基线：PR #125 `c04560b784bda182b350b9f6faac33a10ed60509`。30 个原创混合夹具；无修改与只改正文一处分别测量。', '',
        '**结果：两套矩阵均由 531/540（98.33%）升至 540/540（100%）。无修改 30/30 份所有 OPC 部件字节相同；改字 30/30 份严格等于“只替换目标文字”的独立预期。编辑额外损失 0。**', '',
        f'完整 CTest **{total[1]}/{total[1]}**，其中原 #125 当前基线 321 项，新增 70 项；无排除项。19/19 真书、{books["summary"]["total_pages"]:,} 页、{books["summary"]["total_glyphs"]:,} 字形，页数和逐页 RGBA SHA-256 变化均为 0。', '',
        '## 指标口径', '',
        '#117 实际提供 6 项结构指标；旧报告的 18/18 是 6×3 文档。本任务直接调用原函数，保留原六项，再加入原有文本／图片哈希和十项严格检查，组成每份文档 18 项。原校验器及其断言未修改。', '',
        '改字路径先独立生成 expected.docx：仅将唯一目标 run 的文字替换并进行 XML 转义。记录 source／expected／actual 三组数值，字符数和文本哈希的有意变化逐项列出；其余部件和目标段落内的结构仍全部比较。每格增加、减少、同数量内容替换都判失败。', '',
        '## 30 份夹具', '',
        '| 夹具／结构 | 字节 | 修前 无改／改字 | 修后 无改／改字 | 改字额外损失 |',
        '| --- | ---: | ---: | ---: | ---: |']
    for i, item in enumerate(manifest['documents']):
        row = [before['matrices'][mode][i]['passed'] for mode in ('noop', 'edited')]
        final = [after['matrices'][mode][i]['passed'] for mode in ('noop', 'edited')]
        extra = after['edit_side_effects'][i]
        assert extra['id'] == item['id']
        lines.append(f'| [{item["id"]} · {item["label"]}](../tests/fixtures/docx-real/codex/{item["path"]}) | {item["bytes"]:,} | {row[0]}/18 · {row[1]}/18 | {final[0]}/18 · {final[1]}/18 | {len(extra["additional_main_changes"])} |')
    lines += ['', '全部小于 60 KiB；最小／最大分别为 ' + str(min(v['bytes'] for v in manifest['documents'])) + '／' + str(max(v['bytes'] for v in manifest['documents'])) + ' 字节。每份都混合正文、表格、图片、脚注、页眉页脚、域、编号、样式和主题。重复表头夹具有 89 行；每页重编号脚注夹具含两个脚注和显式换页；PNG 为原创 160×96 三条形图。', '',
        '## ZIP 容器仍有变化', '',
        'OOXML 部件字节保留与 ZIP 容器原样复制分开统计。[逐夹具 ZIP 审计](docx-real/zip-container.json) 同时记录修前、修后两条路径的容器哈希、条目顺序、时间戳、属性和其它元数据变化。此项保留在明确放弃清单，未计入 18 项通过率。', '',
        '| 修后路径 | 整包哈希变化 | 条目顺序变化 | 时间戳变化条目 | 文件属性变化条目 |', '| --- | ---: | ---: | ---: | ---: |']
    for mode in ('noop', 'edited'):
        rows = containers['after'][mode]
        lines.append('| ' + mode + ' | ' + str(sum(r['archive_sha256_changed'] for r in rows)) + '/30 | ' +
            str(sum(r['entry_order_changed'] for r in rows)) + '/30 | ' + str(sum(len(r['changed_entries']['date_time']) for r in rows)) + ' | ' +
            str(sum(len(r['changed_entries']['external_attr']) for r in rows)) + ' |')
    lines += ['', '## 18 项 × 30 份总通过率', '',
        '| 指标 | 修前无改 | 修前改字 | 修后无改 | 修后改字 |', '| --- | ---: | ---: | ---: | ---: |']
    for metric in after['metrics']:
        scores = [sum(row.get('metrics', {}).get(metric, {}).get('status') == 'PASS' for row in report['matrices'][mode])
                  for report in (before, after) for mode in ('noop', 'edited')]
        lines.append('| ' + metric + ' | ' + ' | '.join(str(n) + '/30' for n in scores) + ' |')
    lines += ['| **合计** | **531/540** | **531/540** | **540/540** | **540/540** |', '',
        '原 #117 六项在修前、修后各路径均为 180/180。缺陷集中在主文档树／标记顺序，计数相等不能证明无损。额外还逐部件比较原始字节；完整 XML 树保留注释、处理指令、属性、text 与 tail，并验证第二次保存稳定。', '',
        '## 每项修复：先失败，再修复，转绿', '',
        '| 步骤 | 失败断言／根因 | 同一断言转绿与指标 |', '| --- | --- | --- |',
        '| 文字命令（矩阵前提） | `text-command`：原 DLL 没有 `exr_edit_set_run_text`。旧模型无法通过公开命令替换正文文字。 | 新命令保留 ID、格式、模板及相邻 opaque run；历史、事务、别名、非法输入和逐分配点失败检查通过。结构分数 531→531，没有把新增 API 记为保真分数提升。 |',
        '| T1-01：段落属性前标记，6 份 | `paragraph-markers`：`pPr` 前的注释／PI 被当作 opaque run，却在写出时统一移到属性后。原树位置不等，主部件字节变化。 | 原位置输出前导 opaque run；同一断言通过。两套矩阵 531→537，原始部件精确相等 21→27。 |',
        '| T1-02：最终节尾，3 份 | `section-tail`：body 最后的 `sectPr` 在所有块之后追加，导致原本位于它后面的注释／PI 移到前面；原位节还无故增加命名空间声明。 | 先输出最终节再输出其原 trailer；原段落仍提供命名空间时保持节原字节，移位节继续补足绑定。同一断言通过。两套矩阵 537→540，原始部件精确相等 27→30。 |', '',
        '修前正文改字使用公开 seed API 深拷贝模型快照，仅改目标 run；原 #125 没有文字命令。补命令阶段改用新公开 API，结果仍为 531/540，证明两种表达方式产生同样的原始损失。中间阶段的 DLL 与报告单独保存，断言未放宽。', '',
        '| 逐步重放 | 无修改 | 改字 | 精确部件（无改／改字） |', '| --- | ---: | ---: | ---: |']
    for label, report in (('Git 原始 #125', before), ('只加文字命令', text), ('再修段落标记', paragraph), ('再修节尾／最终', after)):
        a, b = report['summary']['noop'], report['summary']['edited']
        lines.append(f'| {label} | {a["passed"]}/540 | {b["passed"]}/540 | {a["payload_exact"]}/30 · {b["payload_exact"]}/30 |')
    lines += ['', '## 原始证据与复现', '',
        '- [修前矩阵](docx-real/before.json.gz)、[文字命令阶段](docx-real/text.json.gz)、[段落修复阶段](docx-real/paragraph.json.gz)、[最终两套矩阵](docx-real/after.json.gz)：每格 source／expected／actual、失败路径、部件哈希与编辑额外损失。',
        '- 三个原始失败断言：[文字命令](docx-real/red-text-command.txt)、[段落标记](docx-real/red-paragraph-markers.txt)、[节尾](docx-real/red-section-tail.txt)；[同一断言及新增检查转绿](docx-real/green-regressions.txt)。',
        '- [精确 #125 对照构建](docx-real/control-build.json)、[文字阶段构建](docx-real/stage-text-build.json)、[段落阶段构建](docx-real/stage-paragraph-build.json)：122 个复用产品源文件均核对 Git 原文字节，模型和 IO 重编译，使用原公开头及相同依赖。',
        '- [完整 CTest](docx-real/ctest.txt)、[最终构建](docx-real/build-final.txt)、[配置及测试登记](docx-real/configure-final.txt)、[分层检查](docx-real/layers.txt)。',
        '- [19 本逐页哈希](docx-real/realbooks.json.gz)、[冻结基线差异](docx-real/realbooks.diff.json)。每本输入先核对 manifest SHA-256，再完整渲染各页；原书不入库。',
        '- [生成、矩阵、CTest、对照构建命令](../tests/fixtures/docx-real/codex/README.md)；[明确放弃与保守行为](DOCX-LIMITS.md)。', '',
        '字节相同指解压后的 OPC 部件。写出会重建 ZIP 容器，其整体 SHA-256 不作为相等条件。保留域、浮动图和组合图形的源数据不代表 core 能重新求值或排版这些 Word 结构。', '']
    (ROOT / 'docs/DOCX-REAL-RESULTS.md').write_text('\n'.join(lines), encoding='utf-8')
    summary = dict(matrices_before=before['summary'], matrices_after=after['summary'], ctest=int(total[1]),
        new_ctest=70, books=books['summary'], final_dll_sha256=after['library_sha256'],
        manifest_sha256=hashlib.sha256((HERE / 'manifest.json').read_bytes()).hexdigest())
    (evidence / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Archived T1 evidence and 30-row/18-metric acceptance report')


if __name__ == '__main__':
    main()
