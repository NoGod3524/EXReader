# C06 raw3 可移植标注导入导出（0.2.0，显式候选）

固定起点 `e67d87cbeabb2457e0852f681ef0b27b2c0da4d8`；既有导入源码取自固定提交 `9c7e276f13f42cb61a32507c36d1c22c4489bd01`
（只复制 `apps/reader/annotation-import/`，不合入其宿主修改）。本包同时拥有 `annotation-export` 与 `annotation-import`，避免跨包接口竞态。
范围外：宿主 UI、raw 七模块、冻结 SDK、产品 schema1 与 wire envelope1。批准 SDK 3.41 `edddc463…`，旧 3.40 冻结。

## 1. 为什么需要新入口

旧 portable JSONL（`exreader-annotation-export` 版本 1，模块 0.1.0）把每个头的**精确 wire 字节**当 JSON 字符串携带，
所以 anchor3 的 wire 字节本身可以无损放进去。但旧文件缺少下列东西，旧导入器也只用旧公开 API（`reader_revision_validate`
拒绝 anchor3、拒绝 raw store）：

* 没有原件字节长度，导入端无法核对“这是同一原件”；
* 选择器的 `NULL`／已分配空值／含 NUL 字节、字节长度没有独立可核对的声明；
* 没有 parser／路由／anchor 版本的独立摘要，只能信 wire。

因此**只新增**显式版本与入口，旧格式、旧头文件、旧默认构建一字节不变：

| | 旧（默认，不变） | 新（显式 raw3） |
|---|---|---|
| 构建开关 | 无 | `-DEXR_READER_SELECTOR_BYTES_CANDIDATE=ON` |
| 包版本 | Export/Import 0.1.0（依赖 Revisions 0.3.0、ReadingState 0.1.0） | Export/Import **0.2.0**（依赖 Revisions **0.4.0**、ReadingState **0.2.0**，EXACT） |
| 头文件 | `reader_annotation_export.h`／`reader_annotation_import.h` | 新增 `reader_annotation_export_raw3.h`／`reader_annotation_import_raw3.h`（旧头文件不改） |
| 入口 | `reader_annotation_export_run`／`reader_annotation_import_run` | `reader_annotation_export_raw3_run`／`reader_annotation_import_raw3_run` |
| 文件格式 | `format=exreader-annotation-export`，版本 1 | `format=exreader-annotation-export-raw3`，版本 1，模块 0.2.0 |
| store | `reader_revisions_open` | `reader_revisions_open_raw_v3` |

互斥矩阵（云端测试必须全量覆盖，失败时零写入、零输出文件）：旧导出遇 raw store→`ARGUMENT`（旧导出把修订库 ARGUMENT 原样映射，`revision_code=1`）；raw 导出遇旧 store→`REVISION`（`revision_code=1`，与新增公开头的原契约一致；JSON、Markdown 与双输出均在创建临时文件之前统一检查）；
旧导入遇 raw 文件→`FORMAT`（格式名不同）；raw 导入遇旧文件→`FORMAT`；旧导入遇 raw store→`REVISION`；raw 导入遇旧 store→`REVISION`；
CMake `find_package(... EXACT)` 使 0.1.0/0.2.0 与 0.3.0/0.4.0 的混装在配置期失败。

## 2. raw3 JSONL 格式（format_version 1）

UTF-8、LF、每行一个 JSON 对象，三类行；键序固定。`location` 的字节为**规范形式**，导入器逐字节与由 wire 重算的文本比较，不接受空白或键序变体；其余结构按键序严格解析。

```
{"type":"header","format":"exreader-annotation-export-raw3","format_version":1,"module_version":"0.2.0","book_key":"<fmt>:<64hex>","source_bytes":<n|null>,"book_title":<s|null>,"order":"annotation_id_ascending","wire_encoding":"json_string_utf8"}
{"type":"annotation","annotation_id":"<32hex>","entity_key":"<book_key>:<id>","selection":"safe|pending_parents|concurrent|blocked_restore|missing","tombstone":false,"graph":{…同旧格式…},"heads":[
  {"revision_id":"<32hex>","operation":"put|delete|restore","sha256":"<64hex>","bytes":<n>,"location":<null|LOCATION>,"wire":"<exact retained wire>"}]}
{"type":"footer","annotations":…,"current":…,"tombstones":…,"pending_parents":…,"concurrent":…,"blocked_restore":…,"head_wires":…,"complete":true}
```

* `source_bytes`：原件不可变字节长度（`reader_revision_book_identity_raw_v3`）；该书没有保留的非删除 book 历史时为 `null`。
* `wire`：与旧格式相同的编码（只转义 `"` `\` `\b\f\n\r\t` 与其他 C0 的 `\u00xx`，其余 UTF-8 原样；wire 为无 NUL 良构 UTF-8，因此 anchor3 的
  base64 选择器、`NULL`、含 NUL 的字节都在 wire 里无损存在）。`sha256`／`bytes` 是 wire 的校验。
* `LOCATION`（删除头为 `null`；其余由 `reader_rs_decode_raw_v3` 解码结果**独立重算**，不是复制 wire 的另一份来源）：

```
{"mode":"reflow_global|epub_chapter|fixed_page","parser_version":"…","anchor_version":1|2|3,
 "page_id":<s|null>,"page":<n|null>,"part_path":<s|null>,"part":<n|null>,"chapter":<s|null>,"start":<n>,"end":<n>,
 "exact":{"size":<n>,"base64":<null|"…">},"prefix":{…},"suffix":{…}}
```

  `base64:null` 表示 **NULL**（无值，size 必为 0）；`base64:""` 表示**已分配的空值**；非空为标准带填充 Base64。`size` 是字节数，
  含 NUL 字节原样计数。`page`／`part` 只在对应模式／版本出现。源 anchor1/2/3 版本、parser_version、`page_id`／`part_path` 路由原样保留，
  导入器要求 `LOCATION` 与由 wire 解码出的值**逐字节一致**，否则整个文件拒绝。
* 其余约束沿用旧格式：升序、footer 存在才完整、只导出头（不导出非头祖先 wire）。

## 3. 导入：预览与显式提交

入口 `reader_annotation_import_raw3_run(options, stats, error)`，`options.mode`：

* `READER_AI3_PREVIEW`：只读。文件被拷入私有匿名 spool，逐头验证时产生回调，完整校验通过后 `validated=1`，返回最终统计与 `stats.fingerprint`；不调用任何写 API。
  指纹是**完整输入字节流 SHA-256**，包含标题、图元数据、位置、wire 和 footer，以 64 个小写十六进制字符和结尾 NUL 存入 `char[65]`。未完整验证、取消或预览失败不返回有效指纹。
  使用现有 thumbnails 实现的原字节副本作 64 KiB 增量摘要，没有新增加密依赖、整文件聚合或解析器；云端逐字固定来源，并独立用 Python `hashlib.sha256` 比对实际输入。
* `READER_AI3_COMMIT`：必须带完整 `confirm_fingerprint`==预览返回值（缺少或不等 → `UNCONFIRMED`，零写入）。提交前再次对**本次** spool 做完整校验并重算完整摘要，合法的标题或其他元数据变化也必须重新预览。

校验顺序（任何一步失败都发生在第一次 receive 之前）：

1. store 必须是 raw store；`reader_revision_book_identity_raw_v3(target_book_key)` 必须成功（目标已保留原件身份），否则 `IDENTITY`／`REVISION`。
2. 头 `book_key` 必须等于 `target_book_key`；`source_bytes` 必须非 null 且等于目标库保留的原件字节数，否则 `IDENTITY`。
3. 逐头：wire 经 `reader_revision_validate_raw_v3`（含 SHA-256）；revision_id／operation／entity_key／entity_kind／book_key 与 wire 一致；
   `LOCATION` 与 `reader_rs_decode_raw_v3` 一致；已存在同 ID 不同字节 → `REVISION(COLLISION)`。
4. **真实 public FOUND**：每个非删除、`exact` 非 NULL 的头交给宿主 `resolve` 回调（宿主用 `reader_rs_resolve_*`／`reader_rs_resolve_fixed_v3`
   等公开 API，旧偏移不参与消歧）；回调返回 1 才算 FOUND。`exact==NULL` 的类型化 NULL 记录按定义不可导航：不调用回调、保留原字节、不授予 FOUND。
   任何头 NOT FOUND（MISSING／AMBIGUOUS／LEGACY／NULL 之外的失败）→ 预览计入 `unresolved`；提交返回 `UNRESOLVED` 且零写入。
   默认策略 `READER_AI3_RESOLVE_REQUIRED` 要求提供回调；宿主若已用公开 API 自行核对，必须显式选 `READER_AI3_RESOLVE_ALREADY_VERIFIED`，
   统计中 `found_checked` 为 0（结果不得声称 FOUND 已由本模块核实）。

提交：每个头一次独立的 `reader_revision_receive_raw_v3`（唯一变更 API，不用私有 SQL、不改产品 schema1、不写 SDK 笔记／进度、不按时钟选择）。
**不伪造历史**：只导入文件里的头，保留其 revision_id 与父 ID；缺失祖先不重建，回报真实接收图（`MISSING_PARENT`／`CONFLICT`／`BLOCKED_RESTORE`）与
`omitted_history`；重复导入是 exact duplicate，不重复入历史、不重复入 outbox；`complete_product_accepted` 永远为 0。

取消与失败事务语义（与旧导入一致，写在这里是契约）：

* 校验阶段的任何失败／取消：零写入。
* 提交阶段取消或某项被公开 API 拒绝：之前已提交的项**保留**（每项独立事务，不回滚）；`stats.next_index` 给出下一个头序号，
  可用 `resume_index` 在**同一输入、同一 store**上继续；`resume_index` 不认证另一份文件（所以仍要求 `confirm_fingerprint` 并全文重新校验）。
* 提交后图读取失败：该项仍记为已提交，游标前进。回调抛出异常被捕获为 `CALLBACK`，已报告的提交不撤销。提交回调保留预检的逐头 FOUND／NULL／显式未核验分类；结果向量受 65536 头上限限制，随本次调用成功、取消或失败一起销毁，不跨调用缓存。

所有权与资源：store、选项、字符串、回调借用到调用返回；须在 store 创建线程调用、不可重入（重入返回 `ARGUMENT` 且不重置外层 stats）；
spool 为私有匿名（POSIX `tmpfile`；Windows `CREATE_NEW`＋`DELETE_ON_CLOSE`）；源文件必须是常规非链接文件，只读一次；成功、取消、异常都关闭句柄。

## 4. 上限

输入默认 16 MiB／硬上限 64 MiB；每个头最多 65536 个；单 wire ≤ 1 MiB（修订库公开上限）；选择器 exact ≤ 65536 字节，prefix／suffix ≤ 128 字节且 ≤ 32 标量
（沿用 raw 编码器限制，由修订库校验）；路径 ≤ 4096 UTF-8 字节。导出输出默认 64 MiB／硬上限 1 GiB，沿用旧导出（临时文件→刷盘→原子替换；失败／取消／超预算删除临时文件）。

## 5. 导出

`reader_annotation_export_raw3_run` 复用旧导出的选项／统计／错误类型、流式分页、单实体单快照、路径别名拒绝、取消和原子发布；仅把调用换成
`*_raw_v3` 公开 API，并额外写 `source_bytes`、每头 `location`；Markdown 另列三种选择器的“NULL／已分配空值／字节数”，NUL 在围栏内显示为 U+2400。
旧入口输出字节不变。

## 6. 未授予

宿主 UI 接线；移动端／Apple 端构建；对 Mac 来源记录的 FOUND（Mac 数据缺少对应的 SDK 文档句柄，使用显式 ALREADY_VERIFIED 并如实标注）；
性能；真机；最终 root 对新 portable 契约的审查与接纳（由 root 负责）。

## 7. Root 审查修复（尚待云端验证）

独立分支 `codex/reader-next-c06-root-review` 从原第三轮受测 `1015f2ca397c6411e6f67fc061ce64ee2e57384c` 建立，不修改原 Claude worktree。原三轮失败 `40227792202`、`40228225687`、`40228668273` 均保留，不能视为导入器已运行。

源码审查修复三个问题：raw 导出 Markdown-only capability 状态不一致；预览指纹没有覆盖完整输入；提交回调丢失预检 FOUND 分类。新 raw ABI 尚未授予，确认字段明确改为完整 `char[65]` SHA-256；旧接口、旧头、旧导入源码前缀、默认格式与默认行为保持。

根审查 CI 将完整重跑全部原阶段和新增拒绝例，最多三轮；本地未执行语法、构建、测试或工件处理。此节当前仅记录源码准备，不授予任何平台。

根审查第一轮 `24f151847a01ff9422859b537c78dfcf42c44290` / run `40230274472` / attempt 1：Linux、Windows 各 213 项完整通过；最终证据作业拒绝平台检查名不一致。原因是原探针将 `.a`／`.lib` 实际文件名写进逻辑检查 ID；第二轮改为固定模块身份，并新增两库完整唯一清单检查，实际文件名仍保留诊断。保留原整轮失败，不跨轮拼证据。
