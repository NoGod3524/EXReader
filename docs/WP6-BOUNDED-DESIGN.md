# WP6 有界章内解析：现状依赖、逐出状态与设计

更新：2026-10-20。分支 `codex/wp6-bounded-chapters`，基线 `07c6910`。
本文是包 B 的第一步交付：把章内解析、DOM/投影、分页、检索/选择/CFI/导出以及
借用指针生命周期梳理清楚，给出可逐项验证的有界阅读设计，并把本批实测结果写进
`docs/validation/wp6-bounded-chapters.json`。

**状态：固定验收出口未满足。** 10→100 MiB 单章解析驻留增量、50/100 MiB 单章打开、
窗口逐出后的 checkpoint/随机回读都还没有实现；本批只完成了依赖梳理、固定语料、
分类计量、一条精确尺寸驻留修正及其回归。未满足项在第 9 节逐条列出。

## 1. 当前数据流

### 1.1 索引与共享归档

- `exr_epub_index()`（`src/formats.c:803`）只读取 `META-INF/container.xml`、
  package OPF 与资源清单，**不解析任何 XHTML**；`exr_epub_index_source()`
  （`src/formats.c:834`）保留宿主 `exr_source` 的随机读取，不复制整本书。
- 内存输入走 `archive_copy()`：一份压缩包字节进 `exr_archive_store`，索引与每个
  章快照通过引用计数共享它（`src/document_internal.h:10`）。
- 字节上限：单成员 32 MiB、累计展开 128 MiB（`src/formats.c:270` 的
  `member_info`），整书输入 128 MiB（`EXR_MAX_INPUT`），模型文本 64 MiB
  （`EXR_MAX_TEXT`），节点 262144（`EXR_MAX_NODES`，见
  `src/base_internal.h:11`）。这些上限**保持不变**；本包不通过抬高限制让 50/100
  MiB 单章“通过”。

### 1.2 单章装载

`exr_epub_load()`（`src/formats.c:861`）为每次请求建立**独立拥有的快照**：

1. `archive_backing()` 用 `mz_zip` 的随机读取回调打开共享源；
2. 复制资源元数据、语言、标题，`shared_archive->refs++`；
3. `epub_parse_chapter()`（`src/formats.c:782`）用 `mz_zip_reader_extract_to_callback`
   流式解压，`chapter_feed`（`src/formats.c:763`）按 32 KiB 交给
   `exr_xml_tree_feed()`；**没有整章解压临时副本**，但 DOM 与正文投影仍整章驻留；
4. `exr_model_finish()`（`src/document.c:475`）做正文投影、块切分与节点 range 回填。

### 1.3 DOM 与正文投影

- 节点数组是**密集全局数组**，`exr_node` 公开结构含 `parent/first_child/next_sibling`、
  `start/end`（投影偏移）以及借用的 `name/text` 指针（`include/exr/document.h:31`）。
- 解析期每个元素/文本段各一个节点；文本按**原始解码文本**复制进 `node->text`
  （`exr_model_copy`，计入 `model_bytes`），投影再把折叠空白后的正文复制到
  `d->text`（`exr_model_finish`）。同一段正文因此存两份。
- `exr_model_finish()` 结束时的数组容量按几何倍增（`exr_grow`，`src/common.c:27`），
  完成前可达 2 倍。本批新增 `model_shrink()`（`src/document.c:466`）在 finish 时
  把文本/节点/块/章/资源数组收缩到精确大小，节点区间与投影字节完全不变。

### 1.4 快照所有权与生命周期

- `exr_document_free()` 释放文本、节点、名字/文本/属性字符串、资源元数据；
  共享归档按引用计数释放（`src/document.c` 的 `exr_model_free`）。
- 公开快照的借用指针（`exr_document_text/nodes/chapters/resources`）在
  `document_free` 前一直有效。**任何窗口化方案都不能在快照存活期间移动或释放
  这些数组**，否则 `exr_pager`、`exr_layout`、CFI/锚点/导出的借用指针会悬空。
- 全量 CFI（`exr_document_cfi_create/resolve`）需要原始 package：只有
  `load_package` 存在时才能路由到包树（`exr_document_package_tree`，
  `src/document.c` 末尾）。

### 1.5 分页

- `exr_pager` 持有 `flow f`（`f->doc` 借用整章快照）、`frames[258]`（节点游标栈）、
  行缓冲、浮动状态、样式数组、页面缓存和 checkpoint 缓存（`src/pager.c:43`）。
- 页面按需生成：`exr_pager_next()` 顺序推进；`exr_pager_get()` 用
  `exr_pager_set_cache()` 的容量/字节预算做 LRU 逐出，并用
  `exr_pager_set_checkpoints()` 的 checkpoint 恢复（`save_checkpoint`
  `src/pager.c:245`，`restore_checkpoint()` `src/pager.c:295`）。
- checkpoint 里保存的是**节点下标 + 投影偏移 + 行/浮动/表格/嵌套 cursor 状态**，
  没有任何可序列化的外部形式；它依赖同一份 `doc` 的节点与文本数组。

### 1.6 检索、选择、CFI、导出

- 文本检索 `exr_document_find()`、锚点 `exr_anchor_create/resolve`、
  `exr_document_cfi_path_*`/`exr_document_cfi_*`、`exr_document_export*` 与
  `exr_document_export_epub/html_bundle` 都直接读 `d->text`/`d->nodes`；
  CFI 路径需要元素在父元素子节点中的序号、`id` 属性、文本 UTF-16 偏移与上下文
  断言，因此需要**整章节点结构**的随机访问。
- 会话/书库（`src/library.c`）以 `exr_publication_load()` 的完整文档为单位缓存，
  不是窗口。

## 2. 实测驻留构成

固定语料取自 `tools/generate_bounded_chapter_corpus.py`（散列见证据 JSON）：
单章为一份 10/50/100 MiB 的 XHTML 成员，分段章为每章恰好 1 MiB 的 10/50/100 章。
`document_owned_bytes` 是 `exr_document_memory_size()` 的确定性解析工作区
（文本/节点/块/章/资源数组 + 模型字符串），不含共享压缩包、页面缓存与 checkpoint。

| 语料 | 章字节 | 基线 owned | 候选 owned（含精确尺寸修正） |
| --- | --- | --- | --- |
| single-10MiB | 10 MiB | 34,557,680 | 27,351,824 |
| segmented-10MiB（10×1 MiB） | 1 MiB | 2,995,365 | 2,735,751 |
| segmented-50MiB（50×1 MiB） | 1 MiB | 2,997,205 | 2,738,871 |
| segmented-100MiB（100×1 MiB） | 1 MiB | 3,001,553 | 2,742,771 |
| single-50MiB / single-100MiB | 50/100 MiB | `EXR_LIMIT` | `EXR_LIMIT` |

- 单章 10 MiB：驻留 = 投影 10,263,615 + 节点数组 5,218,664 + 块数组 647,184 +
  模型字符串（节点原文 10.29 MB、元素名 0.90 MB）≈ **2.66 倍**投影（修正前 3.37 倍）。
- 分段章 10→100 MiB：**增量 7,020 字节**（基线 6,188），即每章 1 MiB 的解析驻留与
  书体积无关；增长来自出版索引/资源元数据。
- 单章 50/100 MiB 仍在 `member_info` 处以 `EXR_LIMIT` 拒绝
  （"ZIP member is encrypted or exceeds extraction limit"）：**出口未满足**。

## 3. 为什么不能用滑动缓冲“就地”改造 `exr_document`

1. 公开 `exr_document_text()` 返回**整章连续指针 + 长度**，调用方按任意偏移切片；
   滑动缓冲会让 `text + offset` 越界或指向别的窗口。
2. `exr_node.text/name` 是借用指针；逐出或重解析会移动字符串，破坏公开快照语义。
3. 节点数组是密集全局数组，`exr_pager` 的 frame/checkpoint 和 `exr_layout` 的
   `exr_box.node`、`exr_glyph.node` 都存**全局节点下标**。
4. checkpoint 依赖同一 `doc` 的节点/文本内容；换窗口后必须保持同一坐标。

因此设计必须区分**显式全量快照**（今天的 `exr_document`，语义/所有权不变）与
**分页工作区**（窗口 + 索引，不对外暴露整章借用指针）。

## 4. 有界阅读设计

### 4.1 两个产品，而不是一个被改写的结构

| 产品 | 入口 | 驻留 | 用途 |
| --- | --- | --- | --- |
| 全量快照 | `exr_publication_load()` / `exr_document_*` | 整章（现状，≤32 MiB 成员） | CFI 全量、导出、书库、宿主自有 API |
| 分页工作区 | 新增内部 `exr_chapter_workspace` + 分页驱动器 | 窗口 + 索引，独立计量 | 首屏、顺序/随机翻页、跨窗口 checkpoint |

分页工作区**不返回** `exr_document` 借用数组；它产出 `exr_layout` 页面与源范围，
并可在需要时**显式**物化一份全量快照（物化字节单独记为 `explicit_snapshot_bytes`）。

### 4.2 章索引（一次流式扫描，常驻很小）

流式解析整章，建立以下**全局坐标**（只保留与窗口恢复有关的字段）：

- 每个窗口边界：源字节偏移、全局节点序号、投影字节偏移、块序号；
- 边界处的**祖先链**：元素名、命名空间、属性表、在该父元素内的元素序号
  （CFI step）、`id`/`xml:id`、以及 CSS 级联需要的声明（style/class/lang/dir）；
- 每个块的节点区间与投影区间（用于定位随机目标页所属窗口）；
- 每章的总节点数/总投影字节/块数（只计数，不驻留内容）。

索引按块/边界记录，10 MiB 章约几千条，100 MiB 章约几万条；其字节数单独记为
`index_bytes`，不计入原书字节或缓存。

### 4.3 窗口规则

- 窗口边界只落在**块边界**（`p`、`h1..h6`、`div`、`table`、`figure` 等块级元素的
  开始处；段落、表格、float、ruby、bidi 段落本身绝不切开），因此跨窗口的 CSS 继承
  由**合成祖先链**恢复：窗口按索引记录的祖先链前缀建立同样的元素节点（不含内容），
  级联结果与全量路径一致。
- 窗口内节点使用**局部下标**，并带全局 `node_base`；`exr_node.parent/first_child/
  next_sibling` 在边界处指向合成祖先或哨兵，所有读取经访问器换算成全局下标。
- 窗口内文本使用局部缓冲，带全局 `text_base`；所有投影偏移在窗口内先按局部切片，
  输出到 `exr_layout`/checkpoint 时加上 `text_base`。
- 窗口大小按**计量字节**（节点数组 + 文本 + 属性）而非固定块数，默认目标
  ≤4 MiB，硬上限沿用既有 64 MiB 文本/262144 节点。

### 4.4 分页与 checkpoint 连续性

- 访问器层：`exr_doc_node(doc, global)` 与 `exr_doc_text(doc, offset, length)`
  是布局/分页代码唯一的节点/文本入口（本批已列出需要替换的调用点：
  `pager.c` 18 处、`pager_table.c` 27 处、`inline.c` 18 处、`flow.c` 9 处、
  `style.c` 9 处、`ruby.c` 17 处、`hyphen.c` 20 处、`display_bidi.c` 文本 25 处）。
- 窗口切换发生在**页面封口之后**：此时 frame 栈只指向下一块及其祖先，切换时把
  frame 的 `node/child`、table cursor、嵌套 context、bidi `first_node`、行缓冲的
  `start/end/until` 统一做“全局↔局部”换算；已输出的 glyph/line/box 偏移在封口时
  加 `text_base`，与全量路径逐字节一致。
- checkpoint 序列化为全局形式：`(global_node, projection_offset, block_index,
  float state, line carry)`；随机回读时用索引按 `projection_offset` 选中窗口，
  重新走同一段布局。checkpoint 与页面缓存的预算沿用既有
  `exr_pager_set_checkpoints/set_cache` 语义，不新增框架。
- 取消/限界：窗口解析沿用 `exr_control_poll(EXR_STAGE_READ/LAYOUT)` 与
  `EXR_LIMIT`；失败清理保证不留下半窗口、半索引、半页面。

### 4.5 逐出时必须保存的状态（清单）

窗口逐出/切换前必须保存并可恢复：

1. `exr_pager.frames[]`：`node, child, position, phase, entered, sized_inline,
   float_long, float_fixed, block_consumed, bfc_*`、`old_paragraph` 指向的样式
   索引、`table`（行/列/单元格 cursor）、嵌套 `context`、`fragment`；
2. `floats`（x/y/width/height/side，≤128）与 `streams[]`（浮动 cursor）；
3. `exr_line_buffer`：`run/raw/line` 三段 glyph、`text` 状态、`display` 状态、
   `auto_bases`、`plan`/`plan_pending/prefix/suffix`、断词 word/edits、`before/after`、
   `scan/soft/emergency/line_end/raw_end`、`measure_*`；
4. `bidi`（`first_node`、offsets、`window_safe` 缓存）；
5. 输出计数：`position, chapter, emitted, auto_stable_end, work_glyphs, shape_work`；
6. 样式级联状态：当前元素链上的 computed style（或可重算的声明链 + 祖先索引）；
7. 页面范围与源范围：`exr_page.start/end`、`exr_line/glyph/box.node`；
8. checkpoint 元数据与缓存预算。

第 1/3/4 项都含全局下标或投影偏移，**必须**在窗口切换时换算；这是本设计最易错的
部分，需要逐项等价测试（见第 6 节）。

## 5. 计量口径

分页工作区单独计量，禁止用“整章落盘/映射且不计量”规避预算：

| 类别 | 计算方式 |
| --- | --- |
| `book_bytes` | 输入文件字节（映射/随机读取的源），不计入解析工作区 |
| `index_bytes` | 索引条目与祖先链快照的实际分配字节 |
| `parse_workspace_bytes` | 窗口节点数组 + 文本缓冲 + 属性 + 合成祖先 + 块表（逐窗口求和/峰值） |
| `page_cache_bytes` | `exr_pager_cached_bytes()` |
| `checkpoint_bytes` | `exr_pager_statistics().checkpoint_bytes` |
| `explicit_snapshot_bytes` | 只在宿主显式要求全量快照时计入 |

本批的量测工具 `tools/wp6_chapter_probe.c` 已按这些类别输出
（`parse_workspace` 分解、`categories`、`memory`），并对顺序页与固定随机计划
逐页做 0.01 px 量化哈希比对；`tools/run_wp6_bounded_probe.py` 负责固定语料、
重复次数、散列与中位数。

## 6. 等价性验收（计划）

同一章、同一字体、同一版面参数下，分页工作区必须与全量快照逐项相等：

- 页数、每页 `start/end`、`line/glyph/box` 数量与 0.01 px 量化坐标；
- 每页 CFI（含 quoted 上下文）与 anchor 解析结果；
- 顺序翻页与固定随机计划（seed 20261020）逐页哈希；
- 窗口大小改变（如 2/4/8 MiB）不改变输出；
- 逐出/恢复后 `restored_checkpoints` > 0 且哈希不变；
- 取消、`EXR_LIMIT`、失败清理与重复恢复各有回归。

## 7. 分阶段计划

- **S1（本批）**：依赖梳理、固定语料、分类计量、精确尺寸驻留修正与回归。
- **S2**：`exr_chapter_index`（流式扫描、全局坐标、祖先链）+ 与全量解析的索引
  一致性测试。
- **S3**：`exr_doc_node/exr_doc_text` 访问器与窗口装载；先覆盖纯文本/段落，
  其他结构回退全量路径并显式报告。
- **S4**：分页驱动器跨窗口续排、checkpoint 全局化、随机回读。
- **S5**：CFI/检索/选择的窗口路径或显式物化；导出仍走全量快照。
- **S6**：等价矩阵、`EXR_LIMIT`/取消/所有权回归、Linux ASan/UBSan 与完整 CI。

## 8. 声明的边界

- 本批不改变 32 MiB 成员/128 MiB 累计/64 MiB 文本/262144 节点上限；
- 分页工作区未实现前，50/100 MiB 单章仍以 `EXR_LIMIT` 拒绝，证据 JSON 记录
  原始错误与阶段；
- 不重做普通 Latin 表格首屏优化，不放宽其五轮交替口径；
- 不把 `exr_document` 改成窗口对象，不改变 ABI1/schema6 或既有快照生命周期。

## 9. 未满足项

1. 10→100 MiB 单章解析驻留增量 ≤32 MiB：**未满足**（100 MiB 单章无法打开）。
2. 50/100 MiB 单章打开：**未满足**（`EXR_LIMIT`，32 MiB 成员上限）。
3. 窗口/逐出后的 checkpoint 与随机回读：**未实现**（当前 checkpoint 仅在全量
   快照内有效）。
4. 跨窗口 CSS 继承、段落、双向/字素、表格/float/ruby、源位置与 CFI 连续性：
   **未实现**（设计见第 4 节，需要 S2–S5）。
5. Linux ASan/UBSan 与七作业 CI 未在本批运行；本批只有 Windows 本机构建与完整
   `ctest`。
## 10. 本批交付与复现

交付内容：

| 文件 | 说明 |
| --- | --- |
| `docs/WP6-BOUNDED-DESIGN.md` | 本文（依赖、逐出状态、设计、计量、计划、边界） |
| `docs/validation/wp6-bounded-chapters.json` | 证据：语料散列、逐项量测、等价性、回归、未满足项 |
| `src/document.c` | `model_shrink()`：finish 时把解析数组收缩到精确大小 |
| `tests/test_budget.c` | `retained_workspace()`：精确尺寸回归（关闭 shrink 时失败） |
| `tests/test_chapter_bounds.c` | 32 MiB 成员上限必须以 `EXR_LIMIT` 拒绝；1 MiB 章驻留 ≤3×投影 |
| `tools/generate_bounded_chapter_corpus.py` | 固定 10/50/100 MiB 单章与 1 MiB 定长分段章语料 |
| `tools/wp6_chapter_probe.c` | 解析工作区分项计量、首屏、顺序/固定随机逐页哈希 |
| `tools/run_wp6_bounded_probe.py` | 固定计划运行器（重复、散列、中位数、整章枚举） |
| `tools/record_wp6_bounded_evidence.py` | 从原始记录汇总证据 JSON 并校验受保护文件 |
| `CMakeLists.txt` | 新增 `exreader-wp6-chapter-probe` 与 `native-chapter-bounds`（不安装） |

复现（Windows，MinGW-w64 GCC，Ninja，Release；可选 WebP/TIFF/AVIF 关闭）：

```sh
python -X utf8 tools/generate_bounded_chapter_corpus.py <corpus-dir> --sizes 10,50,100
python -X utf8 tools/run_wp6_bounded_probe.py <probe.exe> <font> <corpus-dir> <out-dir> \
  --repeats 3 --enumerate 20000
python -X utf8 tools/record_wp6_bounded_evidence.py --baseline <base>/summary.json \
  --candidate <cand>/summary.json --corpus <corpus-dir> --ctest-log <log> \
  --source-sha <sha> --base-sha 07c6910c12dab572771440c7ce34157f079f80d9 \
  --main-repo <checkout> --out docs/validation/wp6-bounded-chapters.json
```

基线量测使用同一 `tools/wp6_chapter_probe.c` 源码、只链接基线库的探针，避免工具差异。

### 10.1 本批结果

| 项目 | 结果 |
| --- | --- |
| 完整回归 | `ctest` 157/157 通过（156 项原有用例 + `native-chapter-bounds`），日志见证据 |
| 精确尺寸回归 | `native-budget` 121 项；新增 `retained_workspace` 在关闭 shrink 时第 168 行失败 |
| 章边界回归 | `native-chapter-bounds` 27 项：33 MiB 成员 `EXR_LIMIT`、失败清理、1 MiB 章 owned ≤3×投影 |
| 层依赖 | `check_layers.py`：0 remaining inverse references、0 new、0 inverse includes |
| 公开符号 | 导出表 632 = 632（候选/基线相同），未新增公开符号 |
| 安装消费 | install + examples 29/29 + C++ consumer（"3.39.0 ABI 1"，exit 0）+ 组件消费 3/3 |
| 页数/源范围 | 单章 5,488 页；每 1 MiB 分段 1,341 页；每个用例前 256 页哈希与基线逐项相等 |
| 顺序翻页 | 单章每页布局 16.6–23.3 ms、渲染 2.7–5.8 ms；分段每页 17.3–25.3 ms |
| 首屏 | 单章 first_visible_total 中位 229.7 ms（装载 128.1 ms）；分段 66.0–78.1 ms |
| 固定随机计划 | seed 20261020、1 页缓存、4 checkpoint/2 MiB/8 页：0 处哈希不符，恢复 3 次 |
| 工作集（交叉核对） | 分段 10/50/100 MiB 的 `working_set_growth` 4.34/4.36/4.37 MB（常数） |

Linux ASan/UBSan、七作业 CI 和安装工件的许可审计未在本批执行（见未满足项）。
