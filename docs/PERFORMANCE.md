# 性能基准

基准分别测量打开、首章解析排版、首画、后续页面的续排与实际渲染、进程峰值内存。`exreader-benchmark` 是无 UI 的 C11 命令行程序，随 `EXR_BUILD_TOOLS=ON` 构建，直接运行不需要 Python。Python 3 只用于生成固定场景、重复启动进程和汇总 JSON。

## 构建与运行

```sh
cmake -S . -B build/native -DCMAKE_BUILD_TYPE=Release
cmake --build build/native --config Release --parallel 4
cmake --install build/native --config Release --prefix stage

stage/bin/exreader-benchmark book.epub /path/to/font.ttf --max-pages 64
stage/bin/exreader-benchmark book.epub /path/to/font.ttf --max-pages 64 --paging
stage/bin/exreader-benchmark --text-bytes 1048576 /path/to/font.ttf --max-pages 64
python tools/run_benchmarks.py stage/bin/exreader-benchmark /path/to/font.ttf build/benchmarks-eager --runs 3
python tools/run_benchmarks.py stage/bin/exreader-benchmark /path/to/font.ttf build/benchmarks-paged --runs 3 --paging
```

Windows 对应可执行文件为 `stage/bin/exreader-benchmark.exe`。字体由调用方提供；测试不扫描系统字体。默认 `layout_mode: eager`，先完整排版首章；`--paging` 使用真实 `exr_pager_next()` 逐页续排。`--max-pages` 默认 64 个后续页样本，`0` 表示测到首章 EOF；单页文档重绘第 0 页，并输出 `single_page_repaint: true`。

页级模式到达采样上限后立即停止，不继续排版来计算总页数。`page_count` / `glyph_count` 只统计已产出的页和 glyph 记录；仅实际遇到 EOF 才设置 `total_pages_known: true`，此处总数属于首章。完整排版模式的计数始终为首章全量，`total_pages_known` 始终为 true。

runner 只使用 Python 标准库，生成短书、单段长章和多章 EPUB。输入 ZIP 时间戳和内容固定，可用输出的 SHA-256 核对复现。每轮启动一个新进程，保存原始 JSON 和 `summary.json`；汇总值为各轮指标的中位数。

## 测量口径

| 字段 | 测量范围 |
| --- | --- |
| `font_open_ms` | 字体文件读取、复制与 FreeType 字体创建 |
| `publication_open_ms` | EPUB 文件读取、ZIP / OPF 索引；不解析章节 XHTML |
| `first_layout_ms` | 首个 reading-order 分段的加载与完整 XHTML 解析，以及完整排版（eager）或 pager 创建与首个单页布局（paged）；生成 TXT 模式先解析 TXT |
| `first_paint_ms` | 第 0 页灰度栅格渲染及释放返回的 bitmap |
| `first_visible_total_ms` | 从字体打开开始，到首画与 bitmap 释放结束的整段 wall time，包含 session 创建 |
| `turn_render_ms_samples` | 已完成排版的第 1 页起逐页调用 `exr_render_page()` 和 `exr_bitmap_free()` 的 wall time；单页文档重绘第 0 页 |
| `turn_render_p50_ms` / `turn_render_p95_ms` | 单轮实际渲染样本的 nearest-rank 百分位 |
| `turn_layout_ms_samples` | paged 模式逐次 `exr_pager_next()` 的耗时；eager 模式固定为 0，因为所有页已在首画前排完 |
| `turn_total_ms_samples` | 从页面请求到渲染及 bitmap 释放的完整样本；paged 包含续排和释放上一页布局 |
| `turn_layout_p50_ms` / `turn_layout_p95_ms` | 单轮续排样本的 nearest-rank 百分位 |
| `turn_total_p50_ms` / `turn_total_p95_ms` | 单轮完整翻页样本的 nearest-rank 百分位 |
| `baseline_peak_rss_bytes` | 输入生成、字体打开和 EPUB 打开前，进程已达到的 RSS 高水位 |
| `peak_rss_bytes` | 全进程 RSS 高水位，包含字体、文档、布局、输入和渲染 bitmap |
| `incremental_peak_rss_bytes` | 最终高水位减去基线高水位 |

时钟使用 Windows `QueryPerformanceCounter` 或 POSIX `CLOCK_MONOTONIC`。峰值内存来自 Windows `PeakWorkingSetSize`、macOS `getrusage` 字节值或 Linux `getrusage` KiB 转字节。RSS 是操作系统观察到的进程驻留内存，不等于引擎缓存对象的字节计数。

每轮使用新进程，操作系统磁盘缓存不受控，因此这些结果不是磁盘冷缓存测试。`turn_render` 只包含已排版页的渲染和 bitmap 释放，不包含 UI 合成、显示刷新或首次到达该章时的解析排版。所有 EPUB 只索引整书并加载第一个阅读分段；页面、字形和正文计数属于该分段。

0.10.0 归档使用 schema 1，只报告 `turn_render`。0.11.0 使用 schema 2，分别报告续排、渲染和完整翻页；跨版本比较渲染应使用 `turn_render`，旧版渲染数值与新版 `turn_total` 的测量范围不同。

生成 TXT 的输入缓冲在计时前创建，其内存仍计入进程峰值。固定 EPUB 使用重复的 ASCII 文本，默认页面为 720 × 1040、页边距 48、字号 24、行距 1.6、段间距 12；图片、复杂文字和真实书籍需要单独提供输入测量。

## 0.10.0 Windows 基线

2026-10-16，被测引擎源码为 [`d41055d46b63a28358e86f8a59ccb21dc0f9f095`](https://github.com/NoGod3524/EXReader/commit/d41055d46b63a28358e86f8a59ccb21dc0f9f095)。使用 Windows Release 引擎和独立基准程序，每个场景运行三次，每轮最多测 64 个后续页。

- 系统：Windows 11，10.0.26200，AMD64。
- CPU：Intel Core Ultra 7 256V，8 核 / 8 线程；系统报告物理内存 16,693,911,552 字节。
- 字体：`C:/Windows/Fonts/arial.ttf`，SHA-256 `b3658eadae55e682b5f69eb64c439c1ecc8f196c0bb8d4756d145d13bc86476a`。
- [汇总 JSON](benchmarks/0.10.0-windows/summary.json) 和同目录九份明细保留原始采样值、输入 SHA-256、程序 SHA-256 与计数。

| 场景 | 正文规模 | EPUB 文件字节 | 首章页数 | 首章字形数 | 每轮渲染样本 |
| --- | --- | ---: | ---: | ---: | ---: |
| 短书 | 1 章，16 KiB | 1,302 | 14 | 16,373 | 13 |
| 单段长章 | 1 章，1 MiB，一个 `<p>` | 4,638 | 836 | 1,048,576 | 64 |
| 多章书 | 32 章，每章 32 KiB | 25,134 | 28 | 32,746 | 27 |

下表为三轮各项指标的中位数，单位 ms；分项中位数相加不一定等于总耗时中位数。

| 场景 | 字体打开 | EPUB 索引 | 首章解析排版 | 首画 | 首画总耗时 | 渲染 p50 | 渲染 p95 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 短书 | 1.594 | 4.361 | 6.382 | 10.467 | 23.192 | 11.247 | 19.260 |
| 单段长章 | 1.713 | 4.769 | 518.195 | 18.112 | 544.584 | 12.445 | 24.298 |
| 多章书 | 1.618 | 4.944 | 13.660 | 8.510 | 27.884 | 11.509 | 17.839 |

| 场景 | 峰值 RSS 字节，中位数 | 峰值 RSS MiB | 相对基线峰值增量字节，中位数 |
| --- | ---: | ---: | ---: |
| 短书 | 12,341,248 | 11.770 | 6,475,776 |
| 单段长章 | 131,346,432 | 125.262 | 125,472,768 |
| 多章书 | 14,319,616 | 13.656 | 8,458,240 |

长单段在首画前完成 836 页排版，峰值 RSS 为 125.262 MiB；多章书只加载首章，首画前排版 28 页。这组结果用于检查页级续排能否减少首画前工作量，以及缓存预算是否限制了驻留对象。

## 0.11.0 页级续排对比

2026-10-16，同一 Windows 主机、Arial 字体、页面参数与三个 EPUB 的 SHA-256 均与 0.10.0 基线一致。0.11.0 同一构建分别运行 eager 和 paged 模式，每个场景三轮独立进程，最多 64 个后续页样本。基准程序 SHA-256 为 `a5ed1dfb20a553db44760e974fab87c31598542a19e8f88950c72d5495fcf7d3`。

[paged 汇总与九份明细](benchmarks/0.11.0-windows-paged/summary.json) · [eager 汇总与九份明细](benchmarks/0.11.0-windows-eager/summary.json)。以下各项均为三轮中位数，时间单位 ms。

| 场景 | 模式 | 首次解析排版 | 首画 | 首画总耗时 | 峰值 RSS MiB |
| --- | --- | ---: | ---: | ---: | ---: |
| 短书 | eager | 4.797 | 6.822 | 14.525 | 11.039 |
| 短书 | paged | 0.984 | 5.143 | 9.273 | 9.633 |
| 单段长章 | eager | 310.151 | 5.144 | 319.186 | 124.594 |
| 单段长章 | paged | 8.701 | 6.299 | 17.577 | 12.129 |
| 多章书 | eager | 9.607 | 6.272 | 19.066 | 12.859 |
| 多章书 | paged | 0.878 | 4.779 | 8.497 | 9.660 |

| 场景 | 模式 | 续排 p50 / p95 | 渲染 p50 / p95 | 完整翻页 p50 / p95 |
| --- | --- | ---: | ---: | ---: |
| 短书 | eager | 0 / 0 | 4.686 / 6.388 | 4.686 / 6.388 |
| 短书 | paged | 0.293 / 0.454 | 4.833 / 5.977 | 5.145 / 6.216 |
| 单段长章 | eager | 0 / 0 | 5.121 / 8.094 | 5.121 / 8.094 |
| 单段长章 | paged | 0.348 / 0.480 | 5.263 / 7.447 | 5.660 / 7.750 |
| 多章书 | eager | 0 / 0 | 4.649 / 7.920 | 4.649 / 7.921 |
| 多章书 | paged | 0.328 / 0.508 | 4.774 / 7.927 | 5.163 / 8.407 |

| 场景 | 模式 | 采样结束时已产页数 | 已产 glyph 记录 | 首章总页数已知 |
| --- | --- | ---: | ---: | --- |
| 短书 | eager / paged | 14 | 16,373 | 是 |
| 单段长章 | eager | 836 | 1,048,576 | 是 |
| 单段长章 | paged | 65 | 81,545 | 否，达到 64 个后续页样本上限 |
| 多章书 | eager / paged | 28 | 32,746 | 是 |

1 MiB 单段长章在 paged 模式首画前只产出一页；采样结束时累计 65 页，释放已翻过的页面。相对同构建 eager 模式，首画总耗时从 319.186 ms 降到 17.577 ms，峰值 RSS 从 124.594 MiB 降到 12.129 MiB，减少约 90.3%。文档本身仍完整解析；这次峰值覆盖前 65 页的运行过程。

完整排版路径同样保留：0.11.0 eager 产出 836 页、1,048,576 个 glyph 记录，与 0.10.0 一致。本轮完整首章解析排版为 310.151 ms，旧基线为 518.195 ms；原始记录保留各轮耗时，后续回归继续使用同一固定输入。

## 0.12.0 原生塑形接入后的复测

同一主机、Arial、固定 EPUB 和分页参数；每个场景三轮独立进程，最多 64 个后续页样本，操作系统磁盘缓存不受控。本轮启用 OpenType 塑形，普通 LTR 段落只扫描源文字，不保留全段字形。原始数据见 [汇总与九份明细](benchmarks/0.12.0-windows-paged/summary.json)。

| 场景 | 首次解析排版 ms | 首画总耗时 ms | 完整翻页 p50 / p95 ms | 峰值 RSS MiB |
| --- | ---: | ---: | ---: | ---: |
| 短书 | 2.857 | 15.438 | 10.378 / 15.449 | 9.930 |
| 1 MiB 单段长章 | 18.564 | 36.947 | 12.434 / 19.831 | 12.137 |
| 32 章书 | 3.227 | 17.146 | 12.108 / 20.650 | 10.113 |

以上是各项三轮中位数，包含实际字体表加载、塑形和绘制成本。长章仍在首画前只生成一页，采样累计 65 页；与 0.11 保持相同的源文件 SHA、产出页数和本测试的 glyph 数。该书是英文正文，不能代表阿拉伯文或复杂双向段落的峰值：UAX #9 会为整个当前可见段落保存标量及级别，属于页缓存预算以外的工作区。

测量对应引擎源码 `01beb5554f6b53f8d60bd1e011d997c09725c576`。本轮基准程序 SHA-256：`0fd87436bb54b41bbe82bf4fea73e3290ca7db422d01211849535dd82d933ccb`。

## 0.12.1 审计修复后的复测

Windows、Arial、相同固定 EPUB，三轮独立进程，每轮最多 64 个后续页；先测 0.12.1，再用保留的 0.12.0 SDK 在同一会话复测。字体与输入 SHA-256 全部一致，磁盘缓存不受控。结果为三轮中位数。

| 场景 | 版本 | 首次解析排版 ms | 首画总耗时 ms | 完整翻页 p50 / p95 ms | 峰值 RSS MiB |
| --- | --- | ---: | ---: | ---: | ---: |
| 短书 | 0.12.0 | 1.357 | 7.825 | 5.012 / 8.245 | 9.949 |
| 短书 | 0.12.1 | 2.273 | 10.368 | 5.998 / 10.717 | 10.102 |
| 1 MiB 单段长章 | 0.12.0 | 10.174 | 17.541 | 5.426 / 7.731 | 12.160 |
| 1 MiB 单段长章 | 0.12.1 | 10.188 | 18.493 | 6.137 / 9.054 | 12.238 |
| 32 章书 | 0.12.0 | 1.530 | 9.579 | 4.992 / 8.150 | 10.105 |
| 32 章书 | 0.12.1 | 2.477 | 10.409 | 6.136 / 9.408 | 10.344 |

真实行边界重塑需要额外工作。本轮三个场景完整翻页 p50 增加约 0.7–1.1 ms，峰值增加约 0.08–0.24 MiB；长章仍在首画前仅产一页，采样累计 65 页、81,545 个字形记录，与基线一致。这些英文场景覆盖正常分页开销，长附标与不可拆队列另由回归测试验证；不能据此推算所有文字和字体的峰值。

0.12.1 被测源码为 `5eb289fb112c553017c2b3fe0b8821673c5868cb`，基准程序 SHA-256 为 `21be2895a5273a52c249a6f12b23c97eb5820ee3c65013b68af8348845f35dda`。保留的 0.12.0 SDK 对应源码 `ada8f090a38d9449d3c88be0eda26f9dfef56feb`，基准程序 SHA-256 为 `27bc47475a4470f6c1847e0cc11cd631180ae01810a2d42a061dffe75a245196`。原始数据：[0.12.1 九份明细与汇总](benchmarks/0.12.1-windows-paged/summary.json)、[同会话 0.12.0 基线](benchmarks/0.12.1-audit-baseline-windows-paged/summary.json)。

原始、暂定、最终行三个驻留队列按容量合计限制为 16 MiB；塑形临时结果、字体、段落双向元数据与位图另计。工作量和重试上限见 [API 文档](NATIVE_API.md#独立双向分析与段落方向)。

## 验证

```sh
python tests/check_benchmark.py stage/bin/exreader-benchmark /path/to/font.ttf
```

验证覆盖有效 JSON、非负计时、样本数、百分位、输入大小、Unicode 文件路径、固定 EPUB 生成、两模式三场景 runner、达到页级采样上限后停止、EOF 后与 eager 的页数 / glyph 总数一致，以及坏参数失败。验证不设机器相关的耗时阈值。

## 0.18 自动表格列宽

Windows x64 / GCC 16.2 Release，用原生 benchmark 对 1000 行、2000 个单元格、4000 个正文 A 字符的 EPUB 做每模式 3 次独立进程测量。基线为 65c32d9 的等分布局；新实现测量 min/max-content 后按内容分配。表格均产出 18 页，包含完整 EOF 计数。字体是仓库原始测试字体，磁盘缓存未控制。

| 页级模式，3 轮中位数 | 等分基线 | 自动内容列宽 |
| --- | ---: | ---: |
| EPUB 索引打开 | 2.10 ms | 2.11 ms |
| 章节解析、建表与首屏排版 | 5.12 ms | 11.58 ms |
| 含字体/打开/首画的首屏总耗时 | 7.99 ms | 15.09 ms |
| 全进程峰值 RSS | 12,513,280 bytes | 12,509,184 bytes |
| 后续完整翻页 p50 | 0.67 ms | 0.66 ms |
| 后续完整翻页 p95 | 1.02 ms | 0.78 ms |

自动列宽需要先读取表格内容，首屏多约 6.5 ms 的测量工作；后续翻页复用列边界。这个小样本用于记录成本，微小翻页差异不作为性能提升结论。MIN/MAX 测量不保留整份字形副本；max-content 按已塑形段流式累计。显式 fixed 布局可以避开内容测量。

输入 EPUB、原始各轮 JSON、摘要与 SHA-256 位于 [0.18 表格基准](benchmarks/0.18.0-table-auto-windows/metadata.json)。复测：

```sh
exreader-benchmark docs/benchmarks/0.18.0-table-auto-windows/table-auto-1000-rows.epub tests/fixtures/fonts/primary.ttf --max-pages 0 --paging
```


## 0.18 共享实线边框

同一 Windows x64 / GCC 16.2 Release、原始测试字体，用 1000 行、2000 单元格、4000 个 A 的同内容 EPUB，每模式各跑 3 个独立进程。输入只改变 border-collapse，均声明 2px 半透明黑色边框；表格按内容收缩，属于窄表格负载。磁盘缓存不受控，下面是三轮中位数。两种边框模型占用的几何不同，分别产出 23 / 20 页。

| 页级模式 | separate | collapse |
| --- | ---: | ---: |
| EPUB 索引打开 | 1.68 ms | 2.01 ms |
| 章节解析、建表与首屏排版 | 9.25 ms | 9.89 ms |
| 首屏绘制 | 0.30 ms | 0.42 ms |
| 含字体/打开/首画的首屏总耗时 | 11.50 ms | 12.16 ms |
| 全进程峰值 RSS | 12,652,544 bytes | 12,447,744 bytes |
| 后续完整翻页 p50 | 0.27 ms | 0.67 ms |
| 后续完整翻页 p95 | 0.46 ms | 0.96 ms |

边框图层增加绘制成本；页数和单元格留白不同，首屏与 RSS 的小幅差异不能作为速度或内存优化结论。原生布局数据可交给宿主绘制，内置 RGBA 图层只在绘制共享边框时临时创建。其包围盒上限为 16M 像素 / 64 MiB，另受总工作量限制；上述窄表格测量不代表满页/多层表格的最大开销。

输入 EPUB、eager/paged 各三轮原始 JSON、摘要及程序/字体 SHA-256 见 [共享边框基准](benchmarks/0.18.0-table-borders-windows/metadata.json)。复测：

```sh
exreader-benchmark docs/benchmarks/0.18.0-table-borders-windows/table-collapse-1000-rows.epub tests/fixtures/fonts/primary.ttf --max-pages 0 --paging
```


## 0.18 浮动与逐行绕排

Windows x64 / GCC 16.2 Release、仓库 primary.ttf，每模式 3 轮独立进程，磁盘缓存不受控。纯文本用相同的 1 MiB 生成内容，对照 57c9f17 与本次构建，页级采样前 65 页；完整模式均为 1126 页。无浮动时不测量避让区域，也不在每次塑形中复制整张浮动表。

| 1 MiB 纯文本，paged 中位数 | 上一构建 | 浮动构建 |
| --- | ---: | ---: |
| 首屏总耗时 | 10.00 ms | 11.26 ms |
| 全进程峰值 RSS | 17,731,584 bytes | 17,911,808 bytes |
| 完整翻页 p50 | 1.20 ms | 1.55 ms |
| 完整翻页 p95 | 2.49 ms | 1.83 ms |

图文负载为同内容的 600 个段落、600 次共享 PNG 引用、24,000 个 A；block 对照仅用 CSS 禁用 float，均使用本次构建，测到 EOF。浮动后行宽和页数不同，数据用于记录实际代价，不能据此声称排版更快。

| 图文负载，paged 中位数 | 块图片 | 浮动图片 |
| --- | ---: | ---: |
| 首屏总耗时 | 7.07 ms | 9.60 ms |
| 全进程峰值 RSS | 11,476,992 bytes | 11,968,512 bytes |
| 完整翻页 p50 | 2.13 ms | 3.54 ms |
| 完整翻页 p95 | 2.54 ms | 4.44 ms |
| 总页数 | 40 | 23 |

浮动复用原有字体、图片缓存与页级队列。每个排版上下文保留最多 128 个避让矩形，当前 64 位构建约 2.6 KiB，并计入上下文及 checkpoint 大小；临时 flow 副本只借用它。跨页重排待提交的行会有额外塑形工作，已落到上述实际翻页计时。字号、脚本、图片尺寸和长浮动块会改变成本；该组历史基准对应 7abacb9，当时超过整页高度的浮动块返回 EXR_LIMIT。后续续排实现的独立数据见下文。

输入文件、eager/paged 原始三轮 JSON 与程序/字体 SHA-256 见 [浮动基准](benchmarks/0.18.0-floats-windows/metadata.json)。复测：

```sh
exreader-benchmark --text-bytes 1048576 tests/fixtures/fonts/primary.ttf --max-pages 64 --paging
exreader-benchmark docs/benchmarks/0.18.0-floats-windows/floats.epub tests/fixtures/fonts/primary.ttf --max-pages 0 --paging
```


## 长浮动块页级续排（0.18.0 开发中）

Windows / GCC 16.2 Release，原始 primary.ttf，每场景 3 个全新进程，磁盘缓存未控制。
下表为三轮中位数；内存是整个进程的峰值工作集，含文档、字体和页面绘制。
压力 EPUB 中长侧栏宽 160px，每段 128 字节，另有 1,000 个 A 的正文。
基准默认页面尺寸，测首个 reading-order part；不是整个 spine 的总耗时。

| 场景 | 输出页数 | 首屏 ms | 峰值 bytes | 翻页 p50/p95 ms |
| --- | ---: | ---: | ---: | ---: |
| 64 KiB 侧栏，逐页至 EOF | 66 | 5.48 | 11,268,096 | 0.99 / 1.32 |
| 同一侧栏，完整布局 | 66 | 37.63 | 26,910,720 | 0.47 / 0.63 |
| 1 MiB 侧栏，前两页 | 2（未到 EOF） | 20.82 | 18,825,216 | 1.31 / 1.31（单次翻页） |
| 同一侧栏，逐页至 EOF | 1,046 | 20.68 | 18,804,736 | 0.93 / 2.18 |
| 1 MiB 普通文本，前 65 页 | 65（未到 EOF） | 10.58 | 17,838,080 | 1.13 / 2.52 |

完整布局的翻页只绘制已有页面；逐页计时包含续排和绘制。1 MiB 侧栏全程
与前两页的峰值接近，支持布局片段未随已读页数积存；文档解析、节点和样式
仍随输入增长。自动宽度会先测 min/max-content，超长单段的双向分析也保留
段落级数据，因此不宣称所有排版内存都与源大小无关。

原始三轮 JSON、输入 EPUB、程序/字体 SHA-256 和 Git blob 来源清单见
[续排基准](benchmarks/0.18.0-float-stream-windows/metadata.json)。复测：

```text
exreader-benchmark docs/benchmarks/0.18.0-float-stream-windows/float-1048576.epub tests/fixtures/fonts/primary.ttf --paging --max-pages 0
exreader-benchmark docs/benchmarks/0.18.0-float-stream-windows/float-1048576.epub tests/fixtures/fonts/primary.ttf --paging --max-pages 1
```

每个格式的 `--max-pages` 为首屏之后的翻页数。字典、OCR、平台视图和网络组件
未包含在这次负载中。该步骤没有新依赖，DLL 字节数见同一 metadata 文件。


## 普通表格与浮动并排（0.18.0 开发中）

Windows / GCC 16.2 Release，primary.ttf，默认基准页面，三次新进程中位数，磁盘
缓存未控制。小样本来自安装示例及边距回归 EPUB。压力样本包含 1 MiB、每段
128 字节的长侧栏，1,800 行/3,600 个单元格的 300px 普通表格和 1,000 个正文 A；
表格在正文之前，从首屏开始与侧栏并排。

| 场景 | 输出页数 | 首屏 ms | 峰值 bytes | 翻页 p50/p95 ms |
| --- | ---: | ---: | ---: | ---: |
| 长侧栏与 250 行普通表格 | 11 | 14.17 | 11,075,584 | 0.76 / 1.02 |
| 图片与带边距/边框表格 | 6 | 5.60 | 10,829,824 | 0.58 / 0.65 |
| 压力样本前两页 | 2（未到 EOF） | 31.79 | 21,880,832 | 1.96 / 1.96（单次翻页） |
| 压力样本逐页至 EOF | 1,046 | 33.86 | 22,544,384 | 0.72 / 2.36 |
| 1 MiB 普通文本前 65 页 | 65（未到 EOF） | 10.94 | 17,821,696 | 1.06 / 2.21 |

峰值是整个进程的工作集，包含原文、解析节点、字体、表格目录及绘制。自动列宽
仍测量全部相关单元格；上下文预览会临时克隆当前表格状态，不是整表像素或整本
布局。压力样本全程峰值比前两页增加约 0.66 MB，记录了并排续排的实际代价。
普通文本未触发 BFC 路径。历史样本使用不同负载，不能直接当作本步的性能对照。

输入、原始 JSON、Git blob 源码清单和程序/字体哈希见
[表格并排基准](benchmarks/0.18.0-table-floats-windows/metadata.json)。复测：

```text
exreader-benchmark docs/benchmarks/0.18.0-table-floats-windows/bfc-1048576.epub tests/fixtures/fonts/primary.ttf --paging --max-pages 0
```


## 可选断词词典模块（0.18.0 开发中）

模块尚未接入自动排版，因此下表不是自动断词性能。当前 Windows/GCC 16.2 Release
DLL 为 5,287,931 bytes，比表格 BFC 步骤增加 56,731 bytes，无新增链接依赖，且不携带
语言词典。原生词典对象按需分配；外部参考文件仅用于开发验证，不打包进 SDK。

| 参考词典 | 原生 payload bytes | 核对词条数 |
| --- | ---: | ---: |
| English US portable 模式 | 519,072 | 3,106 |
| Español | 28,768 | 3,996 |
| Italiano | 24,980 | 3,934 |
| Русский | 218,828 | 4,010 |

payload 包含对象、语言目录、trie/weight 数组容量及 packed edges，不包括借入源文件、
分配器开销或临时栈。英文移除了复合词最小值配置，此处不验证复合词算法。原始文件
哈希、输入投影和 Pyphen 版本记录在 reference.json，词典各自的许可仍须单独处理。

未创建词典对象的 1 MiB 普通文本、逐页前 65 页，三次新进程中位数：首屏 9.83 ms，
峰值进程内存 17,911,808 bytes，翻页 p50/p95 1.31/1.67 ms；磁盘缓存未控制。该数据
只记录未启用模块的普通阅读成本。源码和字体/程序哈希、原始结果见
[词典模块记录](benchmarks/0.18.0-hyphen-dictionaries-windows/metadata.json)。

## 排版器自动断词（0.18.0 开发中）

同一份 1 MiB、单段落英文 EPUB（段宽 360px，正文 hyphens:auto）、Windows 11、
GCC 16.2 Release、Arial；各模式三次新进程，逐页生成并绘制前 65 页。词典为开发
环境中的 English US portable 模式，显式去掉 COMPOUND 最小值元数据，不验证复合词。
输入、词典投影及字体/可执行文件哈希见
[原始记录](benchmarks/0.18.0-hyphen-layout-windows/summary.json)。

| 场景 | 首屏 ms | 进程峰值 bytes | 翻页 p50/p95 ms |
| --- | ---: | ---: | ---: |
| 不配置词典 | 16.27 | 13,795,328 | 4.15 / 6.13 |
| 配置英文词典 | 20.47 | 17,817,600 | 4.49 / 7.73 |

表中各指标为三次测量中位数；磁盘缓存未控制。启用词典的前 65 页共生成 775 个
连字符，编译词典中位数 2.95ms、常驻 payload 519,072 bytes。首屏包括构造词典，
不包括将模式文件读入 stdin；进程峰值包含解析时的临时分配和分配器保留内存，
不能用常驻 trie 大小代替。新 DLL 为 5,297,555 bytes，比查询模块增加 9,624 bytes，
无新增链接依赖或随包语言词典。此处输入与上一节普通文本基准不同，应比较本表两行。

复测工具为 `tools/benchmark_hyphen_layout.py`，它复用现有 benchmark 的时钟、绘制、
峰值与分页采样；词典保持在调用者的外部目录。`--hyphens language` 也可直接用于
exreader-benchmark 的 EPUB eager/paged 模式，从 stdin 接收 UTF-8 模式；文档仍须
声明 hyphens:auto 与匹配语言，工具不偷偷覆盖 CSS。

## NFC 匹配与输入缓冲区修正（0.18.0 开发中）

Unicode 17 NFC/原文映射接入后，DLL 为 5,368,883 bytes，比上一接入步骤增加
71,328 bytes，无新增链接依赖。规范化数据直接编译进 C，词典仍按需提供。

此前 benchmark 对词典 stdin 一次请求 8 MiB，在 Windows 的管道读取中会影响进程
峰值，即使词典只有几十字节。现改为按实际输入扩容；首屏仍包含编译词典，不包含
读 stdin，峰值包含整个进程。旧记录保留当时测量方法，下面用修正后的工具重测。

Windows 11/GCC 16.2 Release/Arial，同一 EPUB 每种模式三次新进程，段宽 360px，
逐页生成并绘制前 65 页。英文案例使用同一 portable English US 模式；组合文字案例
是 1 MiB 的 `E + U+0301 + T + E + U+0301` 重复文本，用原创 `é1té` 演示模式，最小
字素数 1/1；它衡量规范化路径，不代表完整法语词典。两组均由同一份输入比较开/关。

| 输入 / 词典 | 首屏 ms | 进程峰值 bytes | 翻页 p50/p95 ms |
| --- | ---: | ---: | ---: |
| 英文 / 关闭 | 15.52 | 13,824,000 | 4.31 / 5.56 |
| 英文 / 开启 | 21.17 | 14,442,496 | 4.82 / 7.20 |
| 组合重音 / 关闭 | 19.17 | 13,791,232 | 3.35 / 4.92 |
| 组合重音 / 开启 | 20.26 | 13,910,016 | 4.14 / 5.12 |

表中为实测中位数，磁盘缓存未控制。英文词典 payload 为 519,072 bytes，前 65 页生成
775 个连字符；原创模式 payload 为 1,756 bytes，组合文字前 65 页生成 1,560 个。
完整输入、字典投影、程序/字体哈希和各次样本见
[NFC 基准记录](benchmarks/0.18.0-hyphen-nfc-windows/metadata.json)。复测工具沿用
benchmark_hyphen_layout.py，组合文字通过 `--text 'ÉTÉ '` 指定重复片段；原文不会被
NFC 改写。此前固定缓冲区结果不能用来推算运行时词典的常驻内存。


## 原生复合词词典（0.18.0 开发中）

双层复合词规则接入后，Windows/GCC 16.2 Release DLL 为 5,373,693 bytes，比 NFC
步骤增加 4,810 bytes，无新增链接依赖。普通单词跳过隐式分隔层；带连字符/撇号的
复合词走分段和词段最小值路径。语言词典继续由宿主按需提供。

同一份 1 MiB EPUB、段宽 360px、Arial、前 65 页，每模式三次新进程中位数，磁盘缓存
未控制。本次直接使用未修改的 English US UTF-8 词典，保留 COMPOUND 元数据。
首屏包含词典编译，不包含 stdin 读取；峰值为整个进程的峰值。

| 输入 / 词典 | 首屏 ms | 进程峰值 bytes | 翻页 p50/p95 ms |
| --- | ---: | ---: | ---: |
| 英文 / 关闭 | 18.44 | 13,799,424 | 6.00 / 7.00 |
| 英文 / 开启 | 24.16 | 14,479,360 | 6.56 / 9.41 |
| 复合词 / 关闭 | 21.02 | 13,848,576 | 4.39 / 6.98 |
| 复合词 / 开启 | 31.24 | 14,495,744 | 7.65 / 9.02 |

复合词文本重复 `international-compatibility typography–university `。
英文词典常驻 payload 521,616 bytes，编译中位数分别为 4.02/5.96 ms；前 65 页分别
生成 775/1,560 个连字符。五份原始参考词典的 payload：英文 521,616，法语 215,128，
西语 31,312，意大利语 27,524，俄语 221,372 bytes。payload 包括两层 trie 和拥有的
NOHYPHEN 数据，不包括分配器开销和临时栈。

输入、原始样本、程序/字体/词典哈希和源码来源见
[复合词基准记录](benchmarks/0.18.0-hyphen-compounds-windows/metadata.json)。两组均使用
benchmark_hyphen_layout.py，第二组传入上述 `--text`；无需移除 COMPOUND 字段。


## 拼写替换查询的数据成本（0.18.0 开发中）

新增拥有结果的替换查询后，Windows/GCC 16.2 Release DLL 为 5,384,456 bytes，比
复合词步骤增加 10,763 bytes。无新增链接依赖。普通词典没有替换索引/文字分配，
语言目录和提供器字段增加 112 bytes：英文 payload 521,728，法语 215,240，西语
31,424，意大利语 27,636，俄语 221,484 bytes。含两条替换规则的完整加泰罗尼亚语
词典 payload 为 256,801 bytes。原生查询结果自有记录/文字，单次 payload 限制
256 KiB；普通位图查询不分配结果对象，也不初始化 emit 缓冲区。

下面仅测现有普通自动断词的阅读成本，尚未测替换文字排版。Windows 11、Arial、
同一 1 MiB EPUB、段宽 360px、前 65 页，每模式三次新进程中位数，词典为未修改的
English US。首屏含词典编译，不含 stdin 读取，峰值覆盖整个进程。

| 输入 / 词典 | 首屏 ms | 进程峰值 bytes | 翻页 p50/p95 ms |
| --- | ---: | ---: | ---: |
| 英文 / 关闭 | 35.05 | 13,844,480 | 10.37 / 13.43 |
| 英文 / 开启 | 37.07 | 14,454,784 | 10.37 / 13.84 |
| 复合词 / 关闭 | 44.69 | 13,766,656 | 13.34 / 31.92 |
| 复合词 / 开启 | 45.12 | 14,503,936 | 11.39 / 17.26 |

词典编译中位数分别为 6.64/9.24 ms，生成连字符仍为 775/1,560 个。当前采样中
不开词典也有明显延迟波动，复合词关闭模式 p95 高于开启模式；这些样本不用于
证明新增查询会改善翻页速度。磁盘缓存和系统背景负载未控制。完整输入、各次
原始样本及程序/字体/词典/源码哈希见
[替换查询记录](benchmarks/0.18.0-hyphen-replacements-windows/metadata.json)。


## 拼写替换进入实际排版（0.18.0 开发中）

实际替换测量/重塑形、页级 carry 与检查点接入后，Windows/GCC 16.2 Release DLL 为
5,390,932 bytes，比独立查询步骤增加 6,476 bytes。无新增依赖，语言词典 payload
保持不变。纯普通词典继续走位图路径；有替换时才拥有复制的候选记录。词缓存、
记录数组容量和三份行 glyph 缓冲合计限制为 16 MiB，检查点计入紧凑副本的实际字节。

以下均为 1 MiB EPUB、Arial、默认 24px、段宽 360px、逐页生成并绘制前 65 页，
每种模式三次新进程中位数；首屏含词典编译，不含 stdin 读取。

| 输入 / 词典 | 首屏 ms | 进程峰值 bytes | 翻页 p50/p95 ms |
| --- | ---: | ---: | ---: |
| 英文 / 关闭 | 35.33 | 13,869,056 | 10.12 / 12.79 |
| 英文 / 开启 | 41.32 | 14,589,952 | 10.10 / 12.60 |
| 原创替换 / 关闭 | 43.71 | 13,881,344 | 9.55 / 16.16 |
| 原创替换 / 开启 | 50.29 | 14,061,568 | 13.26 / 21.86 |
| 加泰罗尼亚语 / 关闭 | 31.51 | 13,885,440 | 7.46 / 9.31 |
| 加泰罗尼亚语 / 开启 | 48.69 | 14,450,688 | 13.91 / 17.16 |

英文使用未修改的 English US 文件，生成 775 个字形；原创案例重复 `a aaaaaaaa `，
使用随记录保存的原创模式，生成 4,680 个字形，包含 before/after 与显示连字符。
真实案例重复 `paral·lel col·lecció `，直接使用未修改的加泰罗尼亚语词典，生成
780 个字形（含普通连字符）。生成计数不是断词事件数。三种词典 payload 分别为
521,728 / 8,799 / 256,801 bytes，编译中位数 6.35 / 0.30 / 2.74 ms。

各组只在同一份输入中比较开启/关闭；词典、文本、分页变化会影响每页内容量。
磁盘缓存和系统背景负载未控制，数据不证明某个模式的普遍延迟上限。输入与所有
原始样本、词典哈希及源码/程序/字体来源见
[实际替换排版记录](benchmarks/0.18.0-hyphen-reflow-windows/metadata.json)。语言词典
不随 SDK 打包；当前的字面值/原子簇及剩余词不再自动断词的边界见接口文档。
