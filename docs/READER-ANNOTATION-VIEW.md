# 按书书签与标注列表快照（EXReaderAnnotationView 0.1.0）

可选 C ABI 包，位于 `apps/reader/annotation-view`，不加入默认 reading 构建。它只复用
`reader_revision_annotations_page` 与 `reader_rs_decode`，把一本书的全部 annotation 实体
整理成可翻页、可长期持有的列表快照。不依赖本轮其他新包，只用安装后的公共 API，不读 SDK 私有 SQL。

## 严格只读

模块不导航、不解析 SDK selector、不改变页面、阅读进度、产品 history、outbox 或 SDK 笔记。
安全 head 也不授权导航：宿主仍须自行调用公开 SDK resolve，并只在 FOUND 时跳转。

## 接口

- `reader_av_open(store, book_key, options, &view, &err)`：绑定一本书（全局 `format:sha256`）。
  `store` 是借用的 `reader_revisions`，其寿命必须覆盖对该 view 的每次调用。
- `reader_av_cursor_start(view, ±1, &cursor)` 与 `reader_av_page_get(view, &cursor, limit 1..100, &page, &err)`：
  按稳定全局 `annotation_id` 字节序 keyset 翻页（无 OFFSET）。每页是一次读快照。
  `page.next` 同方向续页，`page.reverse` 反向读取首项之前的内容；空页时 `reverse` 为输入游标翻转方向。
  `complete` 仅在返回行数少于 limit 且非预算截停时为真；刚好满页之后会有一页空的 complete 页。
- `reader_av_page_free`：释放页的唯一一次分配。`reader_av_close`：释放 view，不触碰 store。
- `reader_av_page_set_resolution`：宿主在自己的公开 SDK resolve 之后记录 FOUND/MISSING/AMBIGUOUS/LEGACY，
  只改快照里的一个字段；模块自己永远不写（初始为 `NOT_ATTEMPTED`）。

## 条目语义

| 字段 | 含义 |
| --- | --- |
| `state` | SAFE / CONCURRENT / PENDING_PARENTS / BLOCKED_RESTORE / MISSING，直接来自 store 的选择结果 |
| `kind` | SAFE 时：BOOKMARK（空点 selector）、HIGHLIGHT（范围引文无批注）、NOTE（范围引文带非空批注）、TOMBSTONE（delete）；非 SAFE 一律 UNAVAILABLE |
| 图计数 | `revisions/heads/missing_parents/foreign_parents/deleted/requires_restore`，任何状态都如实给出 |
| 正文 | 仅 SAFE 且非墓碑：`revision_id`、`sha256`、`wire_bytes`、模式、偏移提示、路径/页 ID、引文、前后文、章作用域、批注文本 |
| 旧版本 | `legacy_anchor`（anchor v1）；v1 EPUB 没有 spine 序号（`has_part=0`），重复 spine 路径只有 v2 的 `part` 能区分 |

冲突不会自动挑一个 head；非 SAFE 项不含任何正文、引文或位置，不会伪造。
墓碑（SAFE 的 delete）只显示为删除，没有正文。偏移只是提示，模块不以它兜底。

## 所有权、取消、重入、预算

- 所有者：view、`page_get`、`close` 只能在创建它的线程调用，别的线程得到 `OWNER` 且句柄保留。
- 重入：取消回调内再用同一 view 调用 `page_get/close` 得到 `BUSY`，不改变任何状态。
- 取消：`options.cancel` 在入口、调 store 前、store 回调的每一行、每次 decode 前后、返回前轮询；
  `page.polls` 报告该次调用的轮询数。任一非 OK 状态都完整丢弃页，调用者的游标可原样重试。
- 释放：页的全部字符串与条目在一次分配里，与 view、store、SDK 的寿命无关，三者关闭后仍可读。
- 预算：limit 1..100；单条受 1 MiB 修订上限约束（所有解码字符串都是该修订字节的子串）；
  页总预算 `max_page_bytes`（2 MiB..64 MiB，默认 16 MiB）计入每行 512 字节加保留的 wire 字节，
  超出时在该行之前停止并报告 `budget_stopped`，游标指向已含的最后一行，不跳行。

## 云端验收

`.github/workflows/reader-annotation-view.yml` 在 Ubuntu 22.04、Windows 2022、macOS 15 上构建并安装
产品 SQLite、revisions、reading-state、冻结 SDK 与本包，再编译只依赖安装包的 C11 与 C++17 消费者。
C++ 探针经公共 API 生成 1203 条主书（含 v1/v2、书签/高亮/批注、墓碑、restore、并发 head、缺 parent、
BLOCKED_RESTORE、多字节与最大合法字段）、恰 100 条副书、120 条大批注书、重复 spine 的 EPUB、固定页 PDF 与空书，
并用对公共 `reader_revision_annotations_page`/`heads`/`get` 的直接扫描独立建立预期：无重复、无遗漏、逐项一致。
还覆盖 limit 1/7/33/100 与反向、删除（墓碑）与并发插入、跨书游标拒绝、取消每一个轮询点后重试结果逐字相同、
重入、跨线程、预算停页续读、关闭 view/store/SDK 之后快照仍可读，并在全部读取前后逐字比较产品 history、
outbox、数据库文件、SDK 进度与笔记。独立 C11 消费者另行读取最终产品库做总数核对。
验收结论与工件身份只以同一 source/run/attempt 的实际记录为准，见
[reader-annotation-view.json](validation/reader-annotation-view.json)。

## 未授予

macOS 以外的 Apple 平台、iOS、Android；宿主 UI 与导航；读屏；真机；WebDAV 传输与跨设备标注同步；
性能基线。本包不修改冻结 SDK、产品 schema1、既有 wire 与预算。
