# H10：Android 有界 EPUB 接入计划

状态：源码接入计划，尚未实施或验收。前置为 R5 SDK 同源冻结与 H8 Windows pilot 通过；Android 接入只跟随固定 SDK 提交，不追踪活动中的核心分支。

目标：新导入 EPUB 使用 SQLite 原件和有界章节分页，保留现有书架、选择、复制、标注和生命周期能力。其余重排格式与 PDF/CBZ 沿用各自路径；所有画面继续使用原生 `ReaderView`，无 WebView。

本文依据当前 Android 源码及 `include/exr/library.h`、`include/exr/layout.h`、`docs/R5-BOUNDED-STORAGE-CONTRACT.md` 编写。schema 7 同次包含 `epub_bounded_books`、`epub_progress`、`epub_notes`，标注属于首次接入范围。

## 1. 已确认的实际入口

| 文件／方法 | 当前行为 | 接入点 |
| --- | --- | --- |
| `MainActivity.startImport` 的 worker | URI 分块复制后，以 `new EXReader.Document(path)` 预读全部重排正文 | EPUB 改为 package-only 检查；不得在导入前另跑全文 Document 预检 |
| `exreader_host_jni.c:nativeImportFile` | 只有 PDF/CBZ 使用 file import；EPUB 经过 `read_entire_file` 和 memory import | EPUB 加入 `exr_library_import_file_unique`；如需 SDK 内部取消，使用带 control 的 seekable source import，不能把 file 接口误写成已有 control 参数 |
| `NativeLibrary`／`BookStore` | Book 只有 format 和 global position；进度返回 `{state, offset}` | 增加模式、章内位置与笔记对象；去重得到 ID 后查询 `exr_library_epub_info_get` |
| `MainActivity.openBook` | 所有书先要求 `prefs.path_<id>` 文件存在 | bounded EPUB 从同一书库 owner 打开原件，不受 sidecar 路径是否存在限制 |
| `ReflowSession` 构造／`prepare` | `Document(path)`、`document.utf8()`、整书 pager；seek 从开头回放 | bounded EPUB 新会话使用 publication + chapter pager；原 legacy 会话保留 |
| `PageSnapshot`／`Selection` | 全局 UTF-8 offsets；快照携带整书 `byte[] text` | bounded 快照携带 part/path 与当前页的文本窗口、窗口起点及章内 geometry offsets |
| `ReaderView.updateSelection` | `ReflowSession.slice(page.text, start, end)` | 先按文本窗口起点换算数组下标；持久化位置仍保持章内 normalized UTF-8 |
| `MainActivity.saveProgressLocked` | 非固定页统一 `store.saveProgress(book, snapshot.start)` | 按 storage mode 分流；bounded 保存章节位置，不写 `books.position` |
| JNI `nativeProgress`／`nativeSaveProgress` | `library_document` + document anchor 解析／创建 | bounded 使用 `epub_progress_get` + pager resolve／capture + `epub_progress` |
| JNI `nativeNotes`／`nativeSaveNote`／`nativeUpdateNoteText`／`nativeRemoveNote` | 旧 notes、全文锚点解析、旧 ID 域 | bounded 使用新四个 EPUB note API；保留 legacy 与 fixed note 域 |

这些入口须作为一个闭环实施；只替换阅读构造器，仍会在导入、进度或标注时读入全文。

## 2. 最小接入边界

在 Android 局部桥接 `examples/android/app/src/main/cpp/exreader_host_jni.c` 和 `host/NativeLibrary.java` 内增加有界会话句柄及数据对象。现有 app-local `EXReader.Publication` 只有路径／内存打开、parts 和整章 load，没有 source、bounded pager、pager anchor/read_text；不能借它的 `load()` 完成有界接入。

最小新增能力：mode 查询、source/publication/session 打开关闭、part 列表、chapter pager、next、页渲染及 geometry、按范围读文字、pager anchor 创建／解析、章节进度及 note CRUD。复用已有 `PageLoad` 和 `PageSnapshot` 的发布方式；不建立第二套 UI 或通用阅读框架，不修改共享 `bindings/jni`。

`BookStore` 所持 `NativeLibrary` 是读取原件和保存 metadata/progress/notes 的同一个 SDK owner。句柄只在原 worker 上串行使用，Java UI 不接触 C borrowed memory。清理按 page/layout → pager → publication → font／remaining source → library 的依赖顺序执行；保留原 worker shutdown 证据。

source 打开失败由调用者释放；publication 成功接管 source 后，只让 publication 按公共契约释放一次。JNI 异常、取消、候选丢弃均覆盖同一路径。外部连接提交可能使 source 失效，届时从已接受的位置重开 source/publication；不对失效 pager 反复 next。

## 3. 导入、旧库与模式分流

1. 保留系统 picker、URI 分块复制、32 MiB 宿主上限与原取消发布点。SDK 的 EPUB ZIP 上限为 128 MiB；首次接入不提升宿主上限，因此现有 `too_large` 仍须拒绝 33 MiB 输入。
2. bounded EPUB 使用 file/source import 的 package-only 路径，禁止 `read_entire_file`、memory import 或全文 `Document` 预检。ZIP/package 损坏仍是导入错误；后续章正文损坏可在打开／翻页时报可恢复错误，增加对应独立用例。
3. import unique 返回 ID 后查询模式。精确去重可能复用 schema 6 迁移来的 legacy EPUB；不得把该 ID 改成 bounded、重置进度、移动原笔记或假定所有 EPUB 均为新模式。
4. bounded 中 `text_size=0`、`position=0` 是未知全书 extent 的占位，不代表空书或未读。书架和打开入口不得据此隐藏书或拒绝阅读。
5. 首次接入保留现有 app-owned copy／取消清理语义，避免同时改写原 10 项所有权测试。bounded 会话必须从 DB 读取；增加删除 EPUB sidecar 后仍可重启阅读的独立证明。去除冗余磁盘副本另行评估。
6. 现有 `created` 决定取消后是否删除书行，重复导入不能删除复用行。保留 `import-copied`／`import-inserted`／`import-committed` 的提交前后区别；需要 SDK 复制中的取消时，将现有 HostTask 状态接到 source control，并证明事务回滚。

## 4. 章节、位置与翻页

会话由 `exr_library_source` → `exr_publication_open_source` → `exr_publication_parts` → `exr_publication_pager_create` 建立。选原 publication 目录中的主阅读 spine part，不把目录过滤后的行号当 part；相同 path 重复出现在 spine 时保留不同 part index。

持久化和会话传递统一为：`part + exact package path + exr_anchor selector`。path 使用 SDK 返回的规范包路径，不再 URI decode；UTF-16 下标、XML 原字节、UI 页码和整书拼接偏移均不进入该结构。

- 顺序 next 沿用一个已接受 pager；章结束后按阅读顺序切换下一 spine part。空章、末章、辅助资源和错误分别处理，不能因 EOF 换章悄悄重播前章。
- previous、跨章跳转和字号变化建立独立候选，保留当前已接受章内位置；只在进度写成功后接受候选并替换旧会话。字号改变定位当前 selector，不按旧页码推算。
- `exr_library_epub_progress_get` 的 `present` 只表示记录存在。打开目标 part 后用 `exr_pager_anchor_resolve`，只有 `EXR_ANCHOR_FOUND` 才执行精确恢复；歧义／缺失明确提示并采用已声明的章首回退，不把存储成功当解析成功。
- 保存前用 `exr_pager_anchor_create(start,start)` 捕获点 selector，`exact` 必须为非 NULL 空字符串。通过 `exr_library_epub_progress` 保存，不调用旧 global progress/get/clear 或非零 metadata position。
- 全书页数／百分比在未知时显示未知。为了保留原 49 页及 page-50 重启用例，可把已有 UI 页号作为宿主显示计数保存，并关联 source/part/location/layout 身份；它不参与 SDK 定位或全书百分比，失配时重置显示计数。
- 页提交日志新增 part/path/local-start，保留原 `book/index/native_next_calls/recovery_calls` 字段。所有真实 next（包含候选回放、EOF 探测）都计数，不能由显示页号推算或在换章时清零。

`Large.epub` 在 `tools/build_android_host.py:write_fixtures` 由一个 spine 章生成，前 49 页不存在跨章 EOF 探测借口。该原 fixture 上仍要求 49 页、49 次实际 native next、0 recovery；多章新用例另记真实调用数，不套用单章的 49 条件。

## 5. 文字选择、标注与虚拟无障碍节点

bounded 页不保留整章／整书 UTF-8。布局产生章内 glyph/line 范围后，通过 `exr_pager_read_text` 读取当前页所需区间；快照拥有文字窗口及其章内起点。`ReaderView` 的触摸 hit-test 和几何坐标保持原逻辑，只有字符串切片减去窗口起点。选择对象同时关联 book、session/frame、part/path，跨页／换章／忙态即失效。

若选择需要 worker 补读，由已有 worker 完成并核对 frame token 后发布。read_text sink 在成功前只写临时有界缓冲；失败或取消不发布前缀到剪贴板。UTF-8 多字节边界及 emoji／组合字符与旧用例共同覆盖，不能拿 Java char index 写回 selector。

`ReaderView` 继续每行一个 virtual node，`lineText` 来自该页的 bounded read_text，`lineBounds` 来自同页引擎 geometry。保留控件资源 ID、可访问名称、节点查询、焦点事件和屏幕坐标换算。换页重建节点并清除旧虚拟焦点，防止旧章同 ID 节点读出新章之外的文字。

新 note 从当前 pager 捕获非空 exact 的范围 selector，保存到 `exr_library_epub_note`；查询 `exr_library_epub_notes` 不解析整书。导航时打开该 part 并 resolve，FOUND 才跳转和绘制高亮；歧义／缺失保留 note 并禁用精确跳转。评论更新使用 `id>0, exact=NULL`，不从当前页面重造旧选区。删除调用 `exr_library_remove_epub_note`，先按 book 核实所有权；新 note ID 不能进入旧或 fixed 删除接口。

`MainActivity.refreshNotesCount/showNotes/navigateTo/saveNote/deleteNote` 必须按三类域分流。新 Java note 对象应携带 part/path/selector 和解析状态，不能继续只传 `start/end`。旧 notes 与 fixed notes 行为保持原契约。

## 6. 进程恢复、取消与失败发布

保留 `HostTask.commit`、`PageLoad.accept/discard`、`OWNER_EPOCH`、`PROGRESS_LOCK`、generation 和 book/frame 守卫。顺序为候选渲染 → 核对 owner → 捕获／写入章节进度 → 接受 cursor → 发布 UI；写失败不能推进已接受 cursor 或替换画面。

当前 `review_fail_progress` 在另一个 Android SQLite 连接上给 `book_progress` 装 trigger。bounded 必须对真正写入的 `epub_progress` 注入拒绝，保留 legacy 的旧表分支。CREATE/DROP TRIGGER 自身会造成外部 commit，可能使 source 失效：测试 setup 后先重建 source／候选，再验证实际 INSERT 拒绝及数据库错误；清理后重开 source 再 retry，不能让提前的 source I/O 失败冒充进度拒绝。

进程终止／重启及 Activity 重建从同一 DB 的模式和章节位置重建会话，不依赖内存 pager、sidecar 或旧整书 offset。保留旧 owner 在 `progress-before-write` 暂停、新 owner 等锁、旧 owner 释放后新页才能发布、page 50 重启恢复的完整竞态断言。外部连接失效与候选恢复分别计日志，恢复回放增加真实 recovery 计数。

## 7. 与冻结 SDK 一起更新的身份守卫

| 位置 | 当前值／规则 | 接入提交要求 |
| --- | --- | --- |
| `tools/build_android_host.py` build provenance | `library_schema: 6` | 与固定 SDK 的真实 schema 查询一致，升级为 7；不能只改摘要 |
| `tools/android_host_evidence.py:check_evidence` | schema 必须等于 6、SDK 树必须等于 `SDK_BASE` | schema 7，逐文件 SDK/source/APK/runtime 证据仍校验 |
| 同文件 `SDK_BASE` | `d46ff370cb3c5ce9a0ceb4dc1f8b099209149280` | 由集成人登记已同源验收的新 SDK 完整 SHA，不由 Android 包自行选择活动 HEAD |
| 同文件 `REVIEW_BASE`／`ownership()` | 旧交付祖先与路径 allowlist；SDK protected trees 不变 | 登记 R5 接入的 SDK/Android 所有权起点，允许 SDK 基线祖先变化而不把核心改动归给 Android；保留完整祖先及路径约束 |
| `.github/workflows/wp13-android.yml` | `ANDROID_OWNERSHIP_HEAD=8a6636ed8ac6db06ab84e174f5a01c49d12511dc` | 固定实际受测 Android 完整 SHA，且是最终集成源码祖先 |
| `tools/check_android_host.py` 静态符号 | 旧 note/progress/document anchor 符号与原 45 IDs | legacy 所需符号保留，并新增 bounded 必需符号／禁止全文绕路检查；不能删除原 case 合约 |
| `sdk-baseline.json`／联合汇总契约 | OPDS BASELINE、Android SDK_BASE 和 SDK candidate 相互匹配 | 由集成人同步提升契约并重跑相应同源门槛，不能给旧 baseline 检查加豁免 |

schema 版本、JSON 报告自身的 `schema` 和 ABI epoch 是不同字段。报告 schema 1/2 不因 SQLite 升到 7 而机械改号；ABI／SDK 版本使用冻结交付的实际值。

## 8. 云端验收出口

原 `HostWalkthroughTest` 的 45 个有序 ID、`HostReviewTest` 的 10 个有序 ID全部保留，同次云端零失败、零跳过。45 中的 EPUB 导入、翻页、字号、触摸选择／复制、笔记增改删／导航、旋转、Activity／后台／进程恢复、歧义与取消都必须走新 bounded 模式；TXT 与 PDF 原路径继续覆盖。

原 `tests/android_host/check_evidence_gate.py` 的 48 项必须全部继续执行：1 个正例、两套各 12 个变异、19 个其他变异、4 个上游变异。保持 ID／顺序／计数／截图／原始仪器化／APK、SDK、font、fixture、source/run/attempt 散列和失败上游拒绝。新增检查可独立增加；不能用新 case 替换旧 case、用缺证据 skip 或降低拒绝条件。

新增 bounded 专项证据至少覆盖：

1. schema 6 库打开升级、legacy EPUB 的原进度和 notes 不变；同字节 legacy/bounded 去重后的模式查询与正确分流。
2. package-only 导入、当前章有界读取、跨章前进／后退／字号重定位、重复 spine path 的不同 part，以及字面 `%`／`#` 路径。
3. 当前页文字和 virtual nodes、真实拖选／复制、章内 note CRUD／跳转、跨章不串 note ID 域、非 ASCII 引文与评论重启恢复。
4. 删除 EPUB sidecar 后继续／重启阅读；外部连接提交导致 source 失效后从已接受位置重建；旧 owner 不覆盖新 owner。
5. bounded 真实进度 INSERT 拒绝、取消前／后提交、损坏的后续章节、预算不足显式错误、失效／歧义 selector 不伪报 FOUND。
6. 原 Large.epub 的 49/49/0 和 page-50 重启恢复；新大章报告 `exr_pager_chapter_statistics`、JNI 文字窗口／位图 bytes 和进程 RSS 峰值，分别列预算与观测值，不能拿 parse workspace 冒充总内存。

构建、模拟器、全部测试、门禁正反例和证据汇总仅在 GitHub Actions。最终候选须在同一个 source/run/attempt 上完成 SDK/APK 构建、原 45+10、49/49/0、原 48 门禁及新增专项，严格 `accepted=true` 才交付 H10。证据仍限定 API 34 x86_64 模拟器；后续真机／签名／TalkBack 采用独立验收出口。

## 9. 开工顺序

1. SDK 负责人交付固定 SHA、schema 7 头文件、安装消费者及同源存储证据；H8 完成 Windows pilot 的进度／标注／恢复闭环。
2. Android 包固定 SDK 与所有权边界，先实现 JNI 会话和模式分流，再连页快照／选择／节点及进度／note CRUD。
3. 保留原两套 UI 用例，增加 bounded 专项及故障观测，协调 schema／基线／构建／门禁身份。
4. 云端完整运行，失败留存后修复并整轮复验；通过后交给集成人重新冻结共同源码和联合验收。

本计划没有修改 Android 宿主、共享绑定、数据库 schema、工作流或验收工具，也没有运行本地测试。
