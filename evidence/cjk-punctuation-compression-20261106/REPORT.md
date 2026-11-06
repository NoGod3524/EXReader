# 中文相邻全角标点压缩 — 2026-11-06

基线为合入 #57 的 main：`2c0407dc40ca63cb5aea0e5983f71d469d4ece4b`。最终本地全量 **ctest 169/169 通过**。Pachinko **1,194→1,194 页，逐页像素 SHA-256 差异 0/1,194**。所有进程以 `CREATE_NO_WINDOW` 启动；未打开窗口，未手动触发 CI。

## 实现及改动范围

`src/inline.c` 增加标点集合和共用 `punctuation_compression()`：两个相邻字形均为集合中的标点，实际 advance 均为 1em（容差 0.01px），非 HIDDEN/RUBY、非同一 cluster、非强制换行且 bidi level 一致时，每处相邻边界从左字形 advance 扣 0.5em。Unicode 模糊宽度的引号、破折号、省略号还要求对应 face 覆盖中文句号，避免把拉丁字体中恰好 1em 的破折号当中文处理。ASCII 标点不在集合内；空格、图片／公式对象不能构成标点对。

普通预断行、max-content intrinsic 和 pending 测宽都计入同一压缩量。最终行重新 shape 后，`line_geometry()` 只修改该行内左字形的 advance；provisional run、raw source 和下一行 carry 不修改。没有改字形尺寸、offset、行高、页边距、缩进或分行边界规则；其余 src 文件未改。

三标点的 advances 为 `[0.5em, 0.5em, 1em]`，总宽 2em。每个字形只承担右侧一个相邻边界，最低 0.5em。三连时，重叠的首对 extent 因中间字形还承担下一处压缩而为 1em；这不表示同一字形被扣了两次。一般 n 连总宽为 `(n+1)/2 em`。

`tests/test_line_boundary.c` 新增两连、三连、软／硬跨行、空格／文字／ASCII 排除测试，以及拉丁字体 em-wide 引号／破折号不变测试；复用整文档、逐页 pager、缓存和像素一致性检查。`tools/generate_test_fonts.py` 与两个新夹具提供原创、1000 units/em 的矩形字形；`tests/fixtures/fonts/README.md` 说明覆盖范围。受保护的 src/ 与 tests/fixtures/ 已登记在 [R-PROTECTED-TREES.md](../ci-packaging-20261103/R-PROTECTED-TREES.md)。

最终文件及行号（新文件从第 1 行起）：

| 文件 | 改动位置 |
|---|---|
| `src/inline.c` | 466–495：集合／判定；1050–1051：最终 advance；1439–1440：max-content；1480–1481：预断行；1598：pending |
| `tests/test_line_boundary.c` | 301、315、327、352：四组测试；369–382：新字体及拉丁排除测试调用 |
| `tools/generate_test_fonts.py` | 70–79、88：两字体生成及输出 |
| `tests/fixtures/fonts/README.md` | 8–12：夹具说明 |
| `tests/fixtures/fonts/cjk-punctuation.ttf` | 新增二进制 |
| `tests/fixtures/fonts/latin-punctuation.ttf` | 新增二进制 |
| `evidence/ci-packaging-20261103/R-PROTECTED-TREES.md` | 26：受保护树登记 |
| `evidence/cjk-punctuation-compression-20261106/` | 新增本 REPORT.md、RESULTS.csv、EXTENTS.csv、UNCHANGED-PAIRS.csv、EDGES.csv、PACHINKO-PAGES.csv、PROVENANCE.json、CTEST.txt、CTEST-JPX-OFF.txt |

## 相邻标点对和 extent 分布

使用未修改的 `tools/probes/cjk_measure.c`，Reader.otf，参数 `0`；配置 `{720,1040,36,28,1.5f,10}`，CSS `html,body{writing-mode:horizontal-tb!important}`。reference 全为 **28px=1em**。探针要求同行、相邻源 cluster、同字体／字号且同行有汉字参照。

| 书 | 改前 pairs / 压缩数 | 改后 pairs | 改后压缩数 | 42px≈1.5em | 28px≈1em（三连重叠对） | 75px（未压缩） |
|---|---:|---:|---:|---:|---:|---:|
| 紅樓夢 | 15,170 / 0 | 15,378 | **15,363** | 15,355 | 8 | 15 |
| 醒世恆言 | 11,352 / 0 | 11,472 | **11,472** | 11,456 | 16 | 0 |
| 唐詩 | 0 / 0 | 0 | 0 | 0 | 0 | 0 |

表格按 0.01px 容差聚合；坐标浮点舍入最大约 0.000031px。未经聚合的具体 extent 值和频数见 [EXTENTS.csv](EXTENTS.csv)。改前全角对为约 56px=2em；紅樓夢另外 15 对一直为 75px。

压缩通过 advance 实现，因此改后 `extent` 仍等于 **改后** `advance_a+advance_b`；不能继续用 `extent<sum` 判断是否压缩。本次计数按 `extent < 2*reference-0.01px`，并核对实际 advances：一般为 14+28px，三连重叠对为 14+14px。

重新分行会改变哪些源相邻对恰好同行：紅樓夢改前／改后共有 14,598 对，改前独有 572，改后独有 780；醒世恆言共有 11,045，改前独有 307，改后独有 427。完整汇总见 [RESULTS.csv](RESULTS.csv)，源对交集计数见 [PROVENANCE.json](PROVENANCE.json)。

## 未压缩对象保持不变

紅樓夢的 15 个未压缩源对，包含 U+2014 破折号，其 advance 实际为 **47px**，不是 28px 全角。按 `(part, source_start, a, b)` 在改前／改后匹配，15 对的 advances 全部仍为 **28+47px**，extent 全部仍为 **75px**；逐对证据见 [UNCHANGED-PAIRS.csv](UNCHANGED-PAIRS.csv)。

单测字号 20px：两标点在 30px 行中 advances 为 **10、20px**；三标点在 40px 行中为 **10、10、20px**。宽 20px 的软换行及显式 `<br/>` 两种跨行情形，两侧标点均保持 **20px**，两条行盒宽度均为 **20px**。ASCII、间隔空格／文字和拉丁 em-wide 标点的 advances 也保持 **20px**。整文档／逐页／缓存输出一致。

## 页数、字形数及禁则变化

| 书 | 页数改前→改后 | 减少 | 行数改前→改后 | 字形数改前＝改后 |
|---|---:|---:|---:|---:|
| 紅樓夢 | 1,652→1,632 | 20 | 37,155→36,707 | 821,108 |
| 醒世恆言 | 1,170→1,167 | 3 | 26,510→26,357 | 562,814 |
| 唐詩 | 86→86 | 0 | 1,786→1,786 | 50,095 |

唐詩没有可测相邻标点对，页数及行数不变。三本 status 和 wrong_mode_pages 均为 0。

紅樓夢重新分行后，探针 **soft_wrap 行首异常 0→1，行尾左引号 2→7**；forced_break 仍为 1。已通过公开 `exr_document_text()` 核查：7 处行尾左引号均紧跟源码折叠空格；新增行首右引号在 part=27/source_start=3170，前面为 `。 SP ”`。这些空格处的原有软断点在重排后落到行边界。本次未扩展禁则 tailoring；因此不能将本结果表述为全部中文禁则达标。逐项 page/part/source_start 见 [EDGES.csv](EDGES.csv)。醒世恆言、唐詩的行首／行尾异常仍全为 0。

## Pachinko 逐页像素回归

葡萄牙语 Pachinko、`C:/Windows/Fonts/arial.ttf`、既有 `tools/probes/alias_page_probe.c`：**1,194→1,194 页；0/1,194 个 SHA-256 不同**，逐页 JSON 记录也完全相同。该探针沿用 check_document 的参数和调用路径，按小端 width/height/channels DWORD 加每行有效 RGBA 字节计算 SHA-256，不含 stride padding。[PACHINKO-PAGES.csv](PACHINKO-PAGES.csv) 保留改前／改后全部页面哈希。

## 测试与复现

最终本地全量 `ctest --test-dir <build> --output-on-failure -j 4`：**169/169，通过，33.36 秒**。日志见 [CTEST.txt](CTEST.txt)。没有既有测试断言“标点不压缩”而失败，没有修改或删除既有断言。新增 line-boundary 测试在旧 main DLL 上先因两标点不能装入 30px 行而失败；最终 DLL 上 **36,577 checks passed**。

初次沿用上一轮关闭 JPX 的配置时，167/168 通过，`native-fixed-pdf` 期待 EXR_FORMAT 却收到“JPX image decoder is disabled”；原始记录保留在 [CTEST-JPX-OFF.txt](CTEST-JPX-OFF.txt)。补齐仓库固定版本 OpenJPEG 2.5.4 并启用 JPX 后重新构建，最终全量通过。没有为通过测试修改 PDF 源码或测试断言。最终改前／改后测量 DLL 都用相同的 JPX 开启配置重新构建。

完整 CMake 参数、输入书籍／字体、探针、最终源文件、DLL、原始输出及构建／测试日志 SHA-256 见 [PROVENANCE.json](PROVENANCE.json)。OpenJPEG 下载包按仓库固定 SHA-256 校验；源码及依赖缓存在仓库外。复现测量：

```text
gcc -O2 -Wall -Wextra -Werror -I include tools/probes/cjk_measure.c -L <sdk> -lexreader -lm -o <sdk>/cjk_measure.exe
<sdk>/cjk_measure.exe <book.epub> <Reader.otf> 0
<sdk>/exreader-check-document-alias.exe <Pachinko.epub> C:/Windows/Fonts/arial.ttf
ctest --test-dir <build> --output-on-failure -j 4
```

原始 PAIR/EDGE 输出、逐页 JSON、进程脚本和完整构建日志位于 `C:/Users/Oscar/Documents/Codex/cjk-punctuation-compression-20261106/`。本报告的输入和证据不包含正文书籍或商业字体。
