# 书内搜索（F1）：`EXReaderSearch 0.1.0`

独立可选安装包，公开头 `reader_search.h`，仅依赖冻结 SDK（3.40.0、ABI1）的 `core` 组件。
不读 SDK 私有 SQL，不依赖产品目录、修订或阅读状态模块，默认 reading 构建不含它。
源码在 `apps/reader/search/`，测试在 `tests/reader_search/`，工作流为
`.github/workflows/reader-search.yml`。本文件说明契约；**验收状态见末节，当前未获云端授予。**

## 范围

- 首版是对 SDK 规范化 UTF-8 文本的字面量、区分大小写字节比较。
  不做正则、大小写折叠、OCR、TTS，也不建立持久化全文索引。
- 查询长度 1..4096 字节，必须是良构 UTF-8（拒绝过长编码、代理项、超过 U+10FFFF、
  孤立续字节）且不含 NUL；否则返回 `READER_SEARCH_QUERY`，不调用 SDK。

## 三个显式来源

| 来源 | 打开函数 | 单元 | 实现 |
| --- | --- | --- | --- |
| 重排 | `reader_search_open_reflow(exr_document*)` | 整份文本 | 公开 `exr_document_find` + `exr_anchor_create` |
| 有界 EPUB | `reader_search_open_epub(exr_publication*, exr_font*, …)` | spine 序号 | 每章创建并释放一个公开 pager，`exr_pager_read_text` 流式扫描，`exr_pager_anchor_create` 捕获 |
| 固定页 | `reader_search_open_fixed(exr_fixed_document*)` | 页 | `exr_fixed_load_text` + `exr_fixed_text_find` + `exr_fixed_anchor_create`，一次只保留当前页文本 |

EPUB 流式扫描用一个 KMP 自动机跨 SDK 的 32 KiB 文本块保留匹配状态，既不拼接整章也不拼整块
缓冲区；章外辅助项（不在阅读顺序内）被跳过。sink 回调内**不**调用 pager：先把本批
命中位置记入预留好的小数组，SDK 流式调用返回之后才捕获锚点。固定页文档若没有文字提供者，
得到 SDK 错误（FORMAT），而不是看起来为空。

## 所有权与重入

传入的 `exr_document`、`exr_publication`、`exr_font`、`exr_fixed_document` 及布局配置内的指针
都是借用，须在 `reader_search_close` 之前保持有效。搜索句柄、`next`、游标/统计读取和
`close` 都在宿主同一个 owner 上调用；模块不创建线程。`exr_control` 回调里再调用同一句柄的任何函数
返回 `READER_SEARCH_BUSY`，状态不变；`close` 在调用中同样返回 BUSY 并保留句柄。
句柄记录创建线程；其他线程调用 `next`、游标/统计读取或 `close` 返回 `ARGUMENT`，
不调用 SDK、不推进游标，也不改变统计或销毁句柄。
并发使用属宿主错误。模块只调用公开 SDK，不写 SDK 库、产品历史、笔记、阅读进度或原文件。

## 命中、批次与游标

- **重叠**：最左、不重叠。命中后下一次从该命中结束处开始，`aa` 在 `aaaa` 里是 `[0,2)`、`[2,4)`。
  命中不跨单元（章或页）。顺序为单元序、再起点序。
- **批次**：`reader_search_next(search, max_hits, &result, &error)`，`max_hits` 为 1..100。
  `result.count` 最多 `max_hits`；`count==0` 仅在 `complete==1` 时出现。
- **终止**：只有每个单元都扫描到末尾才置 `complete`。恰好在最后一个命中处装满的批次不是 complete，
  下一次调用返回 `count==0, complete==1`。
- **游标**：版本 2 的 `reader_search_cursor` 是可复制的纯值，含来源模式、绑定值（模式+查询字节+单元数）、
  原样复制的 `source_key`、单元序号、单元内字节偏移与 complete 标志。宿主通过
  `reader_search_options.source_key` 提供已核验的原件身份及解析/投影版本（1..255 UTF-8 字节、非秘密）；
  不得用 SDK 本地行号或对象地址。模块不在打开时遍历或哈希全书。
  `resume` 要求同一身份、查询、模式与单元数；更换原件、解析版本或无效游标均得到 `ARGUMENT`。
  未提供身份的临时搜索可在当前句柄推进，但其游标不能跨打开恢复；缺少身份绑定的版本 1 游标同样拒绝。
  同一核验原件可在独立 SDK 实例重开续扫。偏移只是续扫起点，不用来定位命中。
- **失败**：取消（`READER_SEARCH_CANCELLED`）或 SDK 错误（`READER_SEARCH_SDK`，含 `sdk_code`）
  丢弃整批，`result` 为空，句柄游标保持上一次成功批次之后的位置，再次调用重试同一批。
  失败批次不当作完整结果。取消在单元之间、每次查找以及每个 32 KiB 文本块处轮询；
  重排的公开 `exr_document_find` 不带 control，所以单次重排查找内部没有更细的取消点。
- **内存**：一次调用最多持有 100 个命中，不保存整书命中；每命中含 `exact`（≤64 KiB）以及
  各 32 标量上下文。

## 命中内容与导航

`reader_search_hit` 带：模式、`unit`（EPUB spine 序号 / 固定页序号 / 重排为 0）、
`part_path`（EPUB，原样复制）、`page_id` 与可空 `page_label`（固定页）、规范化 UTF-8 字节范围
`start/end`，以及公开捕获的 `exr_anchor`（重排与 EPUB，含 SDK 附带的章节作用域）或
`exr_fixed_anchor`（固定页）。这些捕获与直接调用公开捕获接口的结果逐字节相同，因此
和固定起点的 `reader_rs_encode`（v1）与 `reader_rs_encode_v2` 兼容：

- 重排：`reader_rs_capture{REFLOW_GLOBAL, anchor}`；
- EPUB：`reader_rs_capture{EPUB_CHAPTER, anchor, part_path}`，`unit` 作为 `reader_rs_encode_v2` 的 `part`；
- 固定页：`reader_rs_capture{FIXED_PAGE, fixed, page = unit}`，页以 `page_id` 为路由。

页码与偏移不是失败后的兜底定位。导航须在另一个独立 SDK 实例上经公开 resolve：只有 `FOUND`
可导航；`MISSING`、`AMBIGUOUS`、`LEGACY` 逐项保留状态。本模块不插入修订、不保存笔记、不改变当前进度；
这些由宿主决定。

## 释放

`reader_search_result_free` 释放一批结果（命中数组、复制的字符串及 SDK 锚点），可重复调用；
`reader_search_close` 释放句柄并置空。借用的 SDK 句柄不由本模块释放。

## 验证出口（工作流 `reader-search.yml`）

固定受测 source，检查共同起点 `c3511a011eefbf1fba1d20908f000cef22b1ced2` 为祖先、SDK 保护树与产品
schema 未变、改动路径只在 F1 归属内。Windows 与 Linux 各自安装 SDK、产品提供者、未改的
reading-state 适配器和搜索包，再从安装位置编译 C 与 C++ 消费者，并用生成的原件运行。
每项预期来自对 SDK 自己的规范化文本做独立整段扫描，而不是模块的流式路径。覆盖：
中文/emoji/UTF-8 边界、跨 32 KiB 块的命中、重复文本、开头与结尾、无命中、空页、多页 PDF、
跨章 EPUB、重复 spine 路径、100 项续页（重排与固定页，含页中续扫）、每个轮询点上的取消与重试、
错误注入、重入与释放、同长度换书拒绝、独立 SDK 重开、解析版本变更、临时游标拒绝恢复及错线程拒绝，
并验证源文件字节、SDK 笔记、阅读进度和产品修订队列不变，且搜索命中的
v1/v2 编码字节与直接公开捕获的编码一致。

对 1500 段、约 1.5 MiB 的固定长章记录原始计数：SDK 自身的块数、`peak_parse_workspace_bytes`、
模块统计的扫描字节数与自估内存，以及进程峰值 RSS 的三个读数（运行前、仅 SDK 流式读取后、搜索后）。
RSS 是进程级单调高水位，所以“新增搜索内存”只能由模块自估与前后读数一起判断；这是单次观测，
**不据此宣称性能达标**。

## 验收状态

首轮源码 `db3d574798518f8b91339148a78d02620e8c993b`，运行 `40062703988`：Windows/Linux
均编译成功且 C 消费者通过，C++ 探针初始化将进度偏移设在 UTF-8 字符内部，两个平台均失败，
严格汇总拒绝。原运行及工件保留。审查分支改为从 SDK 规范化文本查找合法进度位置，
同时补充上述游标身份与线程约束；复验通过之前仍不授予平台。

`docs/validation/reader-search.json` 记录实际云端运行。
即使通过也只授予所列平台上的本包接口，不含 macOS（除非同源实际运行）、宿主 UI、
产品性能或六平台互通。
