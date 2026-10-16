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
| 短书 | 2.223 | 12.708 | 9.522 / 11.314 | 9.934 |
| 1 MiB 单段长章 | 16.407 | 29.903 | 10.461 / 14.794 | 12.152 |
| 32 章书 | 2.239 | 12.995 | 9.444 / 11.953 | 10.184 |

以上是各项三轮中位数，包含实际字体表加载、塑形和绘制成本。长章仍在首画前只生成一页，采样累计 65 页；与 0.11 保持相同的源文件 SHA、产出页数和本测试的 glyph 数。该书是英文正文，不能代表阿拉伯文或复杂双向段落的峰值：UAX #9 会为整个当前可见段落保存标量及级别，属于页缓存预算以外的工作区。

本轮基准程序 SHA-256：`5b5fea96c54d0079e59c57992a2640d970a0f861d7b087fc95b53d6e79a39c1f`。

## 验证

```sh
python tests/check_benchmark.py stage/bin/exreader-benchmark /path/to/font.ttf
```

验证覆盖有效 JSON、非负计时、样本数、百分位、输入大小、Unicode 文件路径、固定 EPUB 生成、两模式三场景 runner、达到页级采样上限后停止、EOF 后与 eager 的页数 / glyph 总数一致，以及坏参数失败。验证不设机器相关的耗时阈值。
