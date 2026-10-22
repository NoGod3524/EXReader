# R5：有界 EPUB 书库最小存储契约草案

这是后续实现设计，未实现、未通过云端验证。本轮仅核对源码；当前分支新增的
`exr_library_source` 解决存储原件随机读取，尚未解决 EPUB 有界导入与位置存储。
首个目标是“导入 EPUB → 书架 → 有界阅读 → 保存章内进度 → 重开”，随后补同章选文标注。

## 已有实现与边界

- `src/library.c:exr_library_import` 对重排格式调用 `exr_document_open_memory`，保存全文 normalized
  UTF-8 字节数到 `books.text_size`；`position`、`book_progress`、`notes.start/end` 均为全书坐标。
- `stream_metadata` 仅处理 CBZ；`import_file_pdf` 单独提供文件 PDF 路径。
  `exr_library_import_source[_unique]` 当前不支持 EPUB，不能仅在分支表增加格式后继续把 extent 填成源字节数。
- `src/formats.c:exr_epub_index_source` 只建立 ZIP、container、OPF、manifest/spine 元数据，
  通过 `epub_metadata` 登记章节与资源；没有解压 XHTML。原 ZIP 上限是 **128 MiB**，不是 SQLite 的近 2 GiB blob 上限。
  一个压缩后小于该上限、解压单章 100 MiB 的 EPUB 可以与这个限制同时成立。
- `src/chapter_reader.c:exr_publication_pager_create` 会扫描当前章建立有界 chapter index 和样式，
  才得到 `exr_chapter_index_text_size` / `projection_bytes`。打开 publication 并不等于已有所有章的文本长度。
- `src/publication.c:publication_index` 暴露 title、parts；当前没有 public author 查询。
  OPF 元数据扫描也未收集 creator。首版可保存空作者，不能为取作者而打开全文快照。
- schema 6 使用 `application_id=1163416131`，旧 schema 1–5 都升级到 6，其他版本拒绝。
  `books` 有 `position<=text_size` 约束；`exr_library_progress`、`exr_library_note`、
  `exr_library_reanchor` 还检查全书 extent 及 `EXR_MAX_TEXT`。不能让章内数字悄悄通过这些接口。

## 取舍：导入不计算全书文本长度

首版推迟全书 normalized extent。ZIP 的 uncompressed size、XML 字节数和文字投影长度不同，不能互代。
若在导入时求精确全书长度，即使不保留 DOM，也须扫描所有正文并使用与投影一致的规则；
这会增加导入延迟，重复当前章 reader 的工作。把各章长度直接相加能否完全复现旧全书投影及分隔符，
也尚未验证，不能用该算术迁移旧偏移。

因此新模式只需要稳定 part 路由和章内 selector。UI 显示“第几章/当前页”，全书精确百分比暂缺省。
不新增后台全书预扫描器、持久化 DOM、章节全文缓存或全书位置转换表。
未来确有进度百分比需求时，再添加独立、可取消的 extent 计算；不阻塞首屏。

## 最小 schema 7

保持既有表和字段含义，第一阶段只新增两个小表；不修改 `exr_book`、`exr_note` 的 ABI 布局。
下面是数据契约，最终 SQL 由实现包补齐类型、范围与外键检查。

| 新表 | 最小内容 |
| --- | --- |
| `epub_bounded_books` | `book_id` 主键/外键，标记通过新有界导入路径创建、全书 extent 未知的 EPUB |
| `epub_progress` | `book_id` 主键/外键；`part`、规范 `path`、章内 `start` 点、`prefix/suffix` |

两表均随 book 删除级联清理。`epub_notes` 留到笔记单包实施时随独立 schema 增量加入，
不在第一阶段预建空表或提前固定笔记 ABI。不要新增一份持久章节目录；每次开书复用已有 OPF 索引。
`part` 和 `path` 一起校验：OPF spine 可能重复引用同一资源，路径本身不能唯一标识阅读顺序中的一次出现。
原件在 SDK 内不可变，因此同一 book 的 part 序号可稳定复用；不支持在 SQL 外部替换原件后继续沿用旧位置。

新有界书的 `books.text_size=0, position=0` 仅是旧列占位，**不是声明空书**。
新存储模式查询返回 `global_extent_known=false`；`exr_library_books` 的旧 `position` 在此模式固定为 0。
宿主必须读取新 progress API。旧 metadata 更新仍可用，但在该模式尝试写非零 `position` 返回 `EXR_UNSUPPORTED`。

新有界书通过旧全书 `progress[_get]`、`note/notes`、`reanchor` 入口时返回 `EXR_UNSUPPORTED`，
明确要求新位置接口。`exr_library_document` 仍可作为显式快照读取：小书可成功，大书按原快照上限返回错误，
不能因为这个显式读取就补写旧 extent 或改变模式。原始 source、cover、删除、备份接口继续可用。

schema 6 升级只创建空表，不扫描原书、不改旧字段、不把旧进度默认归到第 0 章。
旧 schema 1–5 可复用现有升级逻辑到 6 后再执行 6→7；先完成同一事务，再发布升级成功。
旧 SDK 看到 schema 7 会明确拒绝打开；不能把新增表藏在 schema 6 下让旧写入者忽略模式。

## 导入路径

建议复用现有 `exr_library_import_source[_unique]`、`exr_library_import_file[_unique]` 的 EPUB 分支，
因为它们此前对 EPUB 返回 unsupported。这是新的显式 source/file 用法；既有 memory import 保留全文快照语义。
无需再加一套含义相同的 EPUB import 函数。

1. 校验不可变 seekable source，按 publication 的 128 MiB 原 ZIP 上限检查。
   通过内部 `exr_epub_index_source` / `epub_metadata` 做 package、路径、manifest/spine 验证，
   不调用 `exr_epub_load`、`epub_parse_chapter` 或 `exr_document_open_memory`。
   原导入借用 source 的所有权不变，内部索引不得释放调用者 context。
2. 取 title；调用者 title 仍优先，作者首版为空。封面先不提取，原件中的封面保留；
   避免为兼容旧 `import_cover` 的 DOM 输入而加载全文。这个行为差异写入支持说明。
3. 复用 `stream_compare` 的同格式、同长度逐块精确去重；不先建立 digest 索引。
   找到既有全文导入的同字节 EPUB 时返回原 ID，保留全部旧 progress/notes，不给它添加“未知 extent”标记。
4. 新行使用 `stream_insert` 的 64 KiB blob 写入，但 book 行、原件及 `epub_bounded_books` 标记必须处于同一事务。
   让调用者统一管理事务，不能先提交 `stream_insert` 再补标记。失败清零 `id/created` 并回滚所有行。
5. 在解析元数据、比较、复制块、最终提交前轮询取消；提交之后返回已提交结果。
   短读/源读失败、只读/锁/磁盘写失败均不留下书架半成品；unique 比较失败也不能退化为新增一行。

索引成功只说明书目结构可读取，不能声明所有章可绘制。损坏、缺失或预算超限章节仍在实际访问时明确失败。
源在调用期间被外部修改违反不可变 source 契约；文件 helper 应复用一个已打开文件句柄，避免分别打开路径取元数据/复制。

## 公共接口草案

名称与尺寸待实现时定稿；以下不是已存在接口。

```c
typedef struct {
  size_t size;
  int bounded_storage, global_extent_known;
} exr_library_epub_info;

typedef struct {
  size_t part;
  char *path;
  exr_anchor selector; /* normalized UTF-8 offsets within this part */
} exr_epub_location;

exr_status exr_library_epub_info_get(exr_library *, int64_t,
  exr_library_epub_info *, exr_error *);
void exr_epub_location_free(exr_epub_location *);
exr_status exr_library_epub_progress(exr_library *, int64_t,
  const exr_epub_location *, exr_error *);
exr_status exr_library_epub_progress_get(exr_library *, int64_t,
  exr_epub_location *, int *present, exr_error *);
```

info 使用尺寸前缀；location 为独立新类型，不向旧数组记录尾部加字段。
写入接受宿主从 `exr_pager_anchor_create` 捕获的点 selector，要求 `exact` 非 NULL 且为空、`start==end`；
验证 EPUB 类型、part/path 与当前 OPF 路由一致、数字和字符串上限、UTF-8/selector 结构。
`selector.chapter` 若非空必须与 `path` 相同。不要为每次保存进度建立字体或重新解析正文。
成功存储只表示位置记录合法；不声称已在原文中解析为 FOUND。

读取只返回拥有字符串的 selector 和记录存在性，不分页、不重锚。
宿主用 path/part 开 bounded pager 后调用 `exr_pager_anchor_resolve`；仅 FOUND 可定位，
MISSING/AMBIGUOUS/LEGACY 明确显示并保留旧记录。选择 fallback 首章或用户指定位置时，不能标为精确恢复。
所有失败输出清零；`present=false` 与数据库/不支持错误分开。

第二个实现步骤增加 `exr_epub_note` 新类型及 `exr_library_epub_note/notes/remove_epub_note`、数组释放函数：
note 包含自己的 ID、book ID、上述 location 与评论。显式 selector 必填，支持同章非空范围，
沿用现有字符串/评论上限、所有权检查与事务；评论修改不重抓 selector。
届时增加 `epub_notes` 表：独立 `id`、book 外键、part/path、章内范围、quote/context 与评论；
使用下一个明确的 schema 增量，不往 schema 7 数据库静默加表。
新旧 note ID 分属不同接口域，宿主列表须带类型，不能用新 ID 调旧删除接口。
首版不加入跨章单条标注、CFI/quote 双重真值、全文导出或修订重定位系统。

## 旧数据兼容

旧 EPUB 的 memory import、`books.text_size/position`、`book_progress`、`notes` 完全保持全书含义。
新章内 progress/notes 可用于旧 EPUB，但不覆写旧表；新宿主优先读新位置，没有时再显式进入旧位置恢复流程。

首个 pilot 可继续用既有快照路径处理旧进度/标注，同时对“新有界导入书”使用新链路。
不能为了旧大书无快照能力而把全部 EPUB 强制退回快照。
后续单独提供可取消的旧 selector 转换：已有唯一 chapter 路径与 quote 时，仅在对应章解析并重新捕获章内位置；
旧 selector 的 global 数字偏移不当成本章数字提示使用。重复路径或 quote 歧义保留为未转换。
仅有 global 数字的 legacy 记录需要兼容旧投影的专用扫描；未验证前保持旧记录、明确无法精确迁移。
转换成功在新表追加记录，原记录保留，不以 schema 升级自动消耗这个工作。

`exr_library_backup` 当前使用 `VACUUM INTO`，可自然包含新增表；恢复用 schema 7 SDK 重新打开并核对位置、评论和原件。
不序列化 chapter index、pager checkpoint、字体或进程句柄。
备份前释放临时 blob 写句柄并保持事务完整，沿用新 source 的单 owner 写入与跨连接提交失效契约。

## 后续实现拆分与云端出口

| 单包 | 最小修改边界 | 必须交付 |
| --- | --- | --- |
| 存储闭环 | `src/library.c`、`include/exr/library.h`、版本/schema 契约与专用测试；必要时给 package 索引加内部读取助手 | schema 7、source/file EPUB 导入、info、新点进度；不做宿主或自动旧记录迁移 |
| Windows pilot | `examples/reader.c` 与其专用验收 | 同一固定 SDK 的新导入→书架→bounded 多章→保存/重启恢复；旧路径保留 |
| 同章笔记 | 新 note API/表实现与 Windows 专用用例 | 选文→quote→写入→重开解析→跳转→改评论/删除；无全文快照回退 |
| 后续平台 | Apple/Android/Linux 各自宿主和验收 | 接收同一固定 SDK 后并行，不各自定义数据库格式 |

最小云端验收覆盖：

1. 旧 schema 6→7 的原件、书目、global 进度和笔记逐项不变；迁移失败整体回滚；旧 schema 1–5 路径仍可升级。
2. 小 EPUB 的 source/file 导入、精确去重与旧 memory 导入互认；旧评论/进度不变；新增记录标记、原件和 ID 原子提交。
3. 单章 50/100 MiB 的可压缩 EPUB 导入不构建全文 DOM，随后从书库原件创建 bounded pager 并读到后段；
   提供峰值内存与解析工作区数据，不能只凭 import 成功或 ZIP 小就宣布内存有界。
4. 源 ZIP 超 128 MiB、过大/非法 OPF、坏路径/ZIP、首次/中途源读失败、取消、锁和只读库都按预声明分类；无半行。
5. 多章且各章相同 local offset；跨章翻页后字号/窗口变更、重启定位正确；重复 spine 路径由 part+path 区分。
6. 新 bounded 模式走旧 global API 返回 unsupported，metadata/cover/source/backup 可用；旧普通 EPUB 完整回归保持。
7. 新 point 的 FOUND/MISSING/AMBIGUOUS、非法 part/path、越界数值、无记录与 I/O 错误分开；
   正常保存进度不读取整章正文，恢复才执行 bounded query。
8. 备份恢复新/旧两类书与进度；同 owner 写进度后的 source 仍可读，跨连接提交后按已公开契约失效并重开。
9. 第二步笔记覆盖 UTF-8/组合字符、同引文歧义、ID/书所有权、评论修改保留 quote、删除与恢复；不串入旧 note 命名域。

上述方案仍需实现验证，尤其是旧全书投影的逐章转换、重复 spine 路由和导入中 source 身份稳定性。
首个闭环不依赖这些自动转换能力，不扩大到全格式流式解析或新的兼容语料总数目标。

## 第一阶段实施顺序与实际接入点

第一阶段新增公共符号仅四个：`exr_library_epub_info_get`、`exr_epub_location_free`、
`exr_library_epub_progress`、`exr_library_epub_progress_get`。继续使用原 source/file import 和
`exr_library_source` → `exr_publication_open_source`，不增加 publication 快捷包装、全书 extent 查询、
作者/封面新接口、笔记接口或自动旧坐标转换接口。

| 顺序 | 当前实际代码/SQL | 最小改动与提交出口 |
| --- | --- | --- |
| 1. 固定 schema 和模式 | `exr_library_open` 中新库 SQL 及版本 1–6 分支 | 加两个表及 6→7 路径；每个版本分支当前成功即提前 `return`，须统一进入新终点，不能仅修改新库 `user_version` |
| 2. 守住旧入口 | `exr_library_update` 的 `UPDATE books ... position=?6 ... ?6<=text_size`；`progress/get/clear_progress`、`note/notes`、`reanchor` | 新模式先查 marker；拒绝旧位置操作，保留 metadata 更新位置为 0 的路径；新 progress 不写旧 `books.position`，避免触发 `books_progress_changed` |
| 3. 最小导入 | `stream_metadata`、`stream_import`、`stream_import_values`、`stream_insert`；`import_file`/`import_file_unique` | EPUB 使用 package 索引而非 XHTML；沿用 64 KiB source 复制和 exact compare；marker 与新 row 一次提交 |
| 4. 位置存取 | `store_progress` 仅作现有事务/字符串绑定范例，不改变其 global 含义 | 在新表单独 INSERT/UPSERT 和 SELECT；验证 part/path 只访问 package，不建正文 DOM；getter 不重锚 |
| 5. 删除/备份 | `remove_id` 的 `DELETE FROM books`、`exr_library_delete` 的 source invalidation；`exr_library_backup` 的 `VACUUM INTO ?1` | 新表外键级联，SDK delete 仍在成功后作废现存 source；备份保持当前实现，增加新表还原用例 |
| 6. 冻结交接 | `include/exr/library.h`、schema/version 文档、公开消费者、云端回归 | 一个固定源码/SDK/API/schema 契约后才给平台包；先跑存储闭环，再做 Windows pilot |

步骤 1 的最小实现可以把旧版本升级的终点一次改为 7，在原事务 COMMIT 前创建新表并设置版本；
避免嵌套 `BEGIN`，也避免先提交到 6 后再升级 7 导致“升级失败却部分改变原库”。
新库、旧库、已是 7 的库分别有用例；失败保持原 `user_version` 与原数据。
创建新表不扫描文档、设置默认当前位置或补写旧位置，因此升级耗时与正文大小无关。

步骤 3 当前两条提交分支必须一起改：unique 在 `stream_import_values` 外层事务调用
`stream_insert(...own_transaction=0...)` 后提交；普通 import 则由 `stream_insert(...own_transaction=1...)`
自己提交。第一阶段应让 EPUB 两条路径都由一层外事务持有，插完 marker 才提交；
不能只修 unique，把普通 import 留成“有 book 无 marker”的窗口。

## 兼容风险清单

- **去重遇到另一存储模式**：`exr_library_import_unique` 直接用 `source=?3` 找最早 ID；
  `stream_import_values` 按同格式/长度枚举后精确比较。两者都可能找到另一模式的同字节 EPUB。
  均返回原 ID，不自动升降模式、不重置进度、不为补全 global extent 重新解析全文。
  新 SDK 的调用者在拿到 ID 后用 info 查询模式；legacy SDK 因 schema 7 拒绝打开，不能写坏新库。
- **“旧 clear”误删新进度**：旧 `clear_progress` 是 `DELETE FROM book_progress`，不会影响新表。
  在 bounded 模式必须显式 unsupported，不能返回成功让宿主误以为清掉新位置。
  第一阶段不新增清除功能；后续需要时单独明确新进度的清除语义。
- **旧笔记跨接口误写**：新书模式不能因旧 `notes` 表为空就返回成功且空列表，掩盖“接口不适用”；
  旧 note 评论更新/删除只作用于旧域，不能接受未来新 note ID。第一阶段不修改旧书既有笔记。
- **标记遗漏与不一致**：写入失败不能留下 row；读取 marker 指向非 EPUB、占位列非 0 或外键无效时，
  返回数据库错误，不静默回退成全文路径。不能把检测到非法存储当作“无进度”。
- **查询创建读入全文**：info/progress 路径不得使用 `SELECT source`、`exr_library_blob` 或
  `exr_library_document`；验证路由采用新随机 source 和 package 索引，开 source 失败须释放 context。
- **源与提交失效**：四平台所有书库进度/metadata 写入沿用同一个 SDK owner。其他连接提交使 source 失效是
  新原件 API 已公开的保守策略；遇到它重开 source/publication，不能对旧 pager 继续重试并假称恢复成功。
- **升级器/备份漏表**：现有升级函数有多个提前返回，现有测试也固定 schema 6；同步更新测试预期与版本查询，
  不只改文档常量。备份恢复核对 marker、新进度、原件与旧 global 记录，禁止降版本恢复到旧写入器。
- **没有范围验证却标 FOUND**：持久化只校验结构与 package 路由；只有调用
  `exr_pager_anchor_resolve` 才有正文位置结论。first-write API 不宣称正文已匹配，测试把记录存在性和解析状态分开。

平台交接只认同一 `exr_epub_location`：part 为原 publication 目录索引，path 为同项规范路径，
selector 为该章 normalized UTF-8 坐标。平台不得自行换成页码、UTF-16 位置、原 XML 字节数、偏移拼接或私有 SQL。
Swift/Java/GTK/Win32 的显示索引转换止于 UI 边界；进入公共 API 前必须回到上述统一坐标。
首阶段验收通过后提交 API 头、固定源码 SHA、schema 和云端证据作为 H5–H11 对接依据，
不让四个平台分别追踪活动中的核心分支。
