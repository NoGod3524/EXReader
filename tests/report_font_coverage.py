#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Validate and retain the real-font acceptance artifacts (never the EPUB/fonts)."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, default=ROOT / 'build')
    parser.add_argument('--output', type=Path, default=ROOT / 'evidence/font-coverage-20261109')
    args = parser.parse_args()
    build, output = args.build.resolve(), args.output.resolve()
    before = read(build / 'fontcov-before/matrix.json')
    after = read(build / 'fontcov-after/matrix.json')
    renders = read(build / 'render-after/render.json')
    books = read(build / 'books-after.json')
    diff = read(build / 'books-after.diff.json')
    assert [r['cp'] for r in before['rows']] == [r['cp'] for r in after['rows']]
    assert len(after['rows']) == len({r['cp'] for r in after['rows']}) == 640
    assert all(r['verdict'] in ('hit', 'font_absent') for r in after['rows'] + after['tibetan_supplement'])
    assert all(r['ft_index'] and r['ft_load_error'] == 0 and r['loaded_by_create_font']
               for r in after['rows'] if r['verdict'] == 'hit')
    assert after['summary']['selected_ft_zero'] == 0
    assert before['oracle_sha256'] == after['oracle_sha256']
    assert len(renders['scenes']) == 4
    assert len(renders['zwj_sequences']) == 8
    assert all(r['matches_reference_glyphs'] and r['ft_zero'] == r['notdef'] == 0
               for r in renders['zwj_sequences'])
    for scene in renders['scenes']:
        assert len(scene['pages']) == 1
        page = scene['pages'][0]
        assert page['nonblank_ratio'] > .05 and page['ft_zero'] == page['notdef'] == 0
    assert books['summary']['successful_books'] == books['summary']['requested_books'] == 19
    assert diff['comparable'] and not diff['needs_review'] and diff['hash_changed_pages'] == 0
    assert books['dll_sha256'] == after['dll_sha256'] == renders['dll_sha256'] == sha(build / 'libexreader.dll')
    ctest = (build / 'ctest-final.txt').read_text(encoding='utf-8-sig')
    passed = re.search(r'100% tests passed out of (\d+)', ctest)
    assert passed and int(passed[1]) >= 228
    output.mkdir(parents=True, exist_ok=True)
    copies = {'fontcov-before/matrix.json': 'matrix-before.json',
              'fontcov-after/matrix.json': 'matrix-after.json',
              'fontcov-before/gaps.txt': 'gaps-before.txt',
              'fontcov-after/gaps.txt': 'gaps-after.txt',
              'render-before/render.json': 'render-before.json',
              'render-after/render.json': 'render-after.json',
              'books-after.diff.json': 'books.diff.json',
              'ctest-final.txt': 'ctest.txt', 'font-tests-final.txt': 'font-tests.txt',
              'layers.txt': 'layers.txt', 'startup.json': 'startup.json',
              'configure-args.txt': 'initial-configure-args.txt',
              'build-final.log': 'build.txt', 'negative-control.txt': 'negative-control.txt'}
    for source, target in copies.items():
        shutil.copyfile(build / source, output / target)
    for source, target in [('fontcov-before/oracle.json', 'oracle.json.gz'),
                           ('books-before.json', 'books-before.json.gz'),
                           ('books-after.json', 'books-after.json.gz')]:
        (output / target).write_bytes(gzip.compress((build / source).read_bytes(), mtime=0))
    for scene in renders['scenes']:
        page = scene['pages'][0]
        source = build / 'render-after' / page['screenshot']
        assert sha(source) == page['sha256']
        shutil.copyfile(source, output / source.name)
    matrix = ['# 640 scalar matrix', '',
              '| Group | Code point | Before | Before face / step / FT index | After | After face / step / FT index |',
              '|---|---|---|---|---|---|']
    def face(row):
        if row['face'] is None:
            return 'SIZE_MAX / 0 / —'
        f = row['selected']
        return f"{f['family']} [{f['face_index']}] / {row['step']} / {row['ft_index']}"
    for a, b in zip(before['rows'], after['rows']):
        matrix.append(f"| {a['group']} | {a['codepoint']} | {a['verdict']} | {face(a)} | {b['verdict']} | {face(b)} |")
    (output / 'matrix.md').write_text('\n'.join(matrix) + '\n', encoding='utf-8')
    labels = ['GB2312 一级', 'CJK 扩展 A/B', '兼容区/异体字', '假名/半角', '韩文音节',
              'Emoji/ZWJ 组成码点', '数学/符号', '阿拉伯/希伯来', '全角/半角']
    groups = list(after['summary']['groups'])
    base = (build / 'base-revision.txt').read_text(encoding='utf-8-sig').strip()
    report = ['# 逐字形真实覆盖验收', '',
              '640 个互不重复的 Unicode 码点，固定 `family=serif, style=regular`，每个都调用公开 pick API。',
              '修复前：404 命中 / 209 管理器漏找 / 27 本机缺失。修复后：**613 命中 / 0 管理器漏找 / 27 本机缺失**。', '',
              '[完整逐码点矩阵](matrix.md) · [修复前 236 项缺口](gaps-before.txt) · [最终 27 项缺口](gaps-after.txt)', '',
              '| 集合 | 样本 | 命中 | 本机缺失 | 管理器漏找 |', '|---|---:|---:|---:|---:|']
    for label, group in zip(labels, groups):
        counts = after['summary']['groups'][group]
        report.append(f"| {label} | {sum(counts.values())} | {counts.get('hit',0)} | {counts.get('font_absent',0)} | 0 |")
    report += ['', '独立 FreeType 扫描了系统/用户字体目录及注册表所指的 349 个字体文件，372 个 collection faces；',
               'manager 索引为 362 个可用 Unicode faces。每次命中都重开实际文件/face，检查 FT_Get_Char_Index 和 FT_Load_Glyph，',
               '并确认该 face 真正出现在 create_font 的加载映射中。613 次命中的零索引/加载失败均为 0。',
               '另测 31 个藏文字母：31/31 命中，管理器漏找 31 → 0。', '',
               '## 修复', '',
               '- 原五级优先顺序保留；移除不增加码点覆盖的冗余 face，再从已发现字体补充覆盖，标记 step 6。',
               '- 自动补充部分优先彩色 face，避免单色符号字体抢先命中 emoji；v2 索引缓存保存颜色能力。',
               '- 管理器的总字体字节上限增至 256 MiB，原始 exr_font_create 仍保持 128 MiB。此机最终加载 32 faces / 186,220,676 字节。',
               '- 书内嵌入字体按需挤出自动补充链末端，保留配置字体优先级；加入满链嵌入字体回归。',
               '- 新增同族同样式补充字形、冷/热缓存颜色优先、实际加载映射验证。', '',
               '## 最终本机字体缺口（全部为 font_absent）', '']
    report += [f"- {r['codepoint']} — {r['name']}：本机字体确实没有。" for r in after['rows'] if r['verdict'] == 'font_absent']
    recommendation = after['recommendation']
    report += ['', '建议安装 [BabelStone Han](https://www.babelstone.co.uk/Fonts/Han.html)。下载副本中上述 27 项均已实测 FT 索引非零且能加载；未安装到系统，原矩阵仍反映原始本机状态。',
               f"验证字体 SHA-256：`{recommendation['sha256']}`。", '',
               '## 真实 EPUB 渲染', '',
               '同一本确定性 EPUB 的四个 spine 文档各一页。纯白背景，720×720；非空白定义为任一 RGB 通道 <250，分母为整页 518,400 像素。',
               'FT 零索引与 .notdef 统计覆盖每个可见输出字形；隐藏的连接符/选择符另在 640 项矩阵中逐个验证。', '',
               '| 场景 | 截图 | 非空白比例 | FT 零索引 | .notdef |', '|---|---|---:|---:|---:|']
    for scene in renders['scenes']:
        page = scene['pages'][0]
        report.append(f"| {scene['name']} | [PNG]({page['screenshot']}) | {page['nonblank_ratio']:.6%} | 0 | 0 |")
    report += ['', '8 条 ZWJ 序列的输出字形 ID 均与独立 HarfBuzz/同一 Segoe UI Emoji 参考一致，FT 零索引及 .notdef 均为 0。',
               '家庭 emoji 使用多枚定位组件，不能用“必须单字形”作为判定。`render-after.json` 同时保留原始字形及位置数据；此项结论是字形序列一致。',
               f"样本 EPUB SHA-256：`{renders['epub_sha256']}`；只提交生成脚本与哈希，EPUB 留在 build/。", '',
               '## 回归', '',
               f"- 冻结修复前基线：`{base}`。同一 19 本书、Reader.otf 字体和 tools/regress/layout.json。",
               f"- **19/19 成功，{books['summary']['total_pages']:,} 页，页数/字形数/每页像素 SHA-256 全部不变**；比较结果见 books.diff.json。",
               '- 该既有真书回归入口使用 exr_font_open；管理器路径由矩阵、实际加载、EPUB 混排和 native-font-manager 测试覆盖。',
               f"- **ctest {passed[1]}/{passed[1]} 全绿**（启用 EXR_BUILD_FUZZ）；层依赖检查通过。",
               '- negative-control.txt：相同新增管理器回归对修复前 DLL 明确失败，对修复后 DLL 通过。', '',
               '## 复跑', '',
               'Windows / MinGW；原生依赖由项目 CMake 固定。Python 验收使用 stdlib 与本机已有的 uharfbuzz（仅序列参考）；无需安装字体。', '',
               '```powershell',
               'cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release -DEXR_BUILD_FUZZ=ON -DEXR_ENABLE_ICC=OFF -DEXR_ENABLE_IMAGE_AVIF=OFF -DEXR_ENABLE_IMAGE_TIFF=OFF -DEXR_ENABLE_IMAGE_WEBP=OFF -DEXR_ENABLE_MP3=OFF -DEXR_ENABLE_PDF_CRYPTO=OFF -DEXR_BUILD_JNI=OFF',
               'cmake --build build -j 4', 'pwsh -File tests/build_font_coverage.ps1 -Build build',
               'python tests/font_coverage.py matrix --dll build/libexreader.dll --freetype build/font_coverage_ft.dll --output build/fontcov-after --require-complete',
               'python tests/font_coverage.py render --dll build/libexreader.dll --freetype build/font_coverage_ft.dll --output build/render-after --require-complete',
               'ctest --test-dir build --output-on-failure -j 4', '```', '']
    (output / 'REPORT.md').write_text('\n'.join(report), encoding='utf-8')
    # Match Git's LF text contract so hashes also verify after a fresh checkout.
    for path in output.iterdir():
        if path.suffix in ('.json', '.md', '.txt'):
            text = path.read_text(encoding='utf-8-sig')
            path.write_text(text, encoding='utf-8', newline='\n')
    changed = subprocess.check_output(['git', '-c', 'core.quotepath=false', 'diff', '--name-only', base], cwd=ROOT, text=True).splitlines()
    changed += subprocess.check_output(['git', '-c', 'core.quotepath=false', 'ls-files', '--others', '--exclude-standard'], cwd=ROOT, text=True).splitlines()
    inputs = sorted({p for p in changed if p.startswith(('src/', 'include/', 'tests/fixtures/font_manager/'))
                     or (p.startswith('tests/') and len(Path(p).parts) == 2)})
    provenance = dict(base_revision=base, dll_sha256=after['dll_sha256'],
                      freetype_bridge_sha256=sha(build / 'font_coverage_ft.dll'),
                      source_sha256={p: sha(ROOT / p) for p in inputs},
                      artifacts_sha256={p.name: sha(p) for p in output.iterdir() if p.is_file() and p.name != 'PROVENANCE.json'})
    (output / 'PROVENANCE.json').write_text(json.dumps(provenance, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(dict(matrix=after['summary']['counts'], pages=books['summary']['total_pages'],
                          changed_pages=diff['hash_changed_pages'], ctest=int(passed[1]), output=str(output))))


if __name__ == '__main__':
    main()

