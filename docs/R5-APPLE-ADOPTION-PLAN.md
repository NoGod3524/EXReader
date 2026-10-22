# H9：Apple 有界 EPUB 接入准备

本文件只读核对 `examples/apple/`、`tests/apple_host/evidence_contract.py` 及 Apple 工作流。
检查基准为 `2bece1b7a04b6ceb4542711f4a6c85f202e6fd0d`。
未修改宿主、共享 Swift binding、SDK 或验收脚本，未执行本地构建/脚本/测试。
H9 正式实施须等固定 SDK（含导入、章内进度与同章 notes）及 H8 Windows pilot 交付。

## 最小目标与固定接口

新 EPUB 默认采用书库有界路径：导入→书架→多章阅读→当页选文/复制→同章标注增改删/跳转→
字号/窗口变化→后台/进程重开恢复。macOS、iPhone、iPad 保留原生 SwiftUI/AppKit/UIKit 展示，不引入 WebView。
其他重排格式继续既有快照和明确容量限制；固定页 PDF/CBZ 保留独立页坐标。

公共入口以固定时的 `include/exr/library.h` 为准，当前八个候选符号为：

| 符号 | 本地 Swift 桥接所需含义 |
| --- | --- |
| `exr_library_epub_info_get` | 设置 `struct_size`，区分 bounded_storage / global_extent_known；错误不能当作旧模式 |
| `exr_epub_location_free` | 深度释放 path 和嵌套 selector，清零后才能重用 |
| `exr_library_epub_progress` | 保存 part/path/章内 point；只表示存储合法，不声明已解析匹配 |
| `exr_library_epub_progress_get` | `present=0` 是无记录；拥有字符串的输出由 location_free 释放 |
| `exr_library_epub_note` | 新建/改范围必须显式 quote；已有 ID 且 exact=NULL 只改评论，并核对 book ID |
| `exr_library_epub_notes` | 返回自有数组与嵌套 location/评论；列表不是已解析定位结果 |
| `exr_epub_notes_free` | 深度释放整组查询结果，不能只 free 顶层或把嵌套 selector 再交另一 owner 释放 |
| `exr_library_remove_epub_note` | 独立 note ID 命名域；不能调旧 note 或 fixed-note 删除入口 |

再复用已有 `exr_library_source`、`exr_publication_open_source/parts`、`exr_publication_pager_create`、
`exr_pager_anchor_create/resolve/read_text`、get/cache/checkpoint/render/statistics。
不发明新的数据库字段含义或宿主版 schema，不改 `bindings/swift/EXReader.swift`。

## HostSDK.swift：包装和所有权

| 当前对象/方法 | 最小接入点 |
| --- | --- |
| `HostDocument.init`（约180行） | 当前 library_document 后复制全文到 Data。只留给 legacy/其他格式；bounded EPUB 不构造它 |
| `HostPager.init`（约237行） | 当前持有 HostDocument 并用 exr_pager_create。增加明确的 publication+part bounded 构造路径，保留原 snapshot 路径 |
| `HostPager.pageRange/render`（约276、300行） | 每次绑定当前取消令牌，get 后在借用有效期内读取范围/绘制并复制位图；不返回 layout 或有效字体指针到主线程 |
| `HostPager.makeAnchor/resolve`（约322行） | 当前注释明确为 snapshot pager，调用 document API。bounded 分支须用 pager anchor API，不能只替换构造函数 |
| `HostPager.pageIndex`（约334行） | 当前以 document.text.count 校验终点。bounded 分支只用该章 normalized projection extent，不用源字节数/旧全书 text_size |
| `HostLibrary.importUnique`（约575行） | 当前最多32 MiB但累计整份 Data，再 memory import。仅 EPUB 改 borrowed seekable source 导入，不通过分块append伪装有界 |
| `HostLibrary.progress/setProgress` | 保留旧global方法；添加新章内包装，不能把新数字传入旧接口 |
| `HostLibrary.addNote/reflowNotes`（约696、724行） | 当前未给selector时旧SDK会重开全文；列表逐条对完整document resolve。bounded改新notes API，捕获/定位仅用所需part pager |
| `HostFixed.init`（约401行） | 现用library_fixed；按独立提交改fixed_source并保留取消、固定页文字/标注验收，不参与EPUB offset转换 |

局部新增 publication owner 和 chapter location 包装即可，不构造通用阅读后端框架。
publication owner 持有强引用的字体/稳定取消上下文及自己的 opaque handle；pager 持有 publication owner，
释放先 pager、再 publication/所拥有 source，最后 library/font。source 成功传入 public open 后才转移 context 所有权，
失败路径必须显式调用 source.release；不能依赖 Swift 初始化失败时未完成对象的 deinit。

getter 的 `exr_epub_location` 由一个 Swift owner 深度释放一次。
不能把其嵌套 selector 浅拷贝给 `HostAnchor(adopting:)` 后再 location_free，造成双重释放。
notes 查询映射为 Swift 自有字符串/数字后再调用 notes_free；不得让 row 保存数组内的 UnsafePointer。
写入借用 Swift `withCString` 构造的字符串时，所有嵌套 closure 和 anchor owner 必须覆盖整个同步 SDK 调用。

### 导入与取消

file helper 当前没有公开 control 参数。需要可中断导入时，采用公开 `exr_source` + `exr_library_import_source_unique`，
用一个 FileHandle/seekable owner 逐块 read_at；不先读成 Data。源大小只声明原件字节数，不能当文本 extent。
源在调用期间保持不可变，callback 不跨 C ABI 抛 Swift Error；保存首个底层错误并返回短读/0，由 SDK 明确失败。
source import 借用调用者 context，Swift 用明确强引用/withExtendedLifetime 保证它覆盖调用及回调。

保留 SDK 交付的 EPUB ZIP 上限；非 EPUB 仍保留既有32 MiB宿主快照限制。
提交前取消由 SDK 清理；提交后的晚到取消只撤销本作业 created=true 的新 ID，不删去重返回的旧书。
保留当前回滚失败可见状态和 reused-row 保护。

publication 中 source.control 可能比创建作业活得更久。
只更新 `HostPager.bind` 的控制器不足以修复 source 层持有的旧取消 context；publication 的 source control
必须指向 owner 保持的稳定桥接对象，由它查询当前作业 token。不能一直引用创建时的短命/已取消 box。
每次 get、命中缓存、render、query 前后继续检查当前 token，保留原缓存命中取消回归。

## 借用页和有限文本

增加一个合成当前 frame 的桥接方法，单次串行作业完成 page range、图像和有限 UTF-8 文本收集。
先消耗 borrowed layout 的范围/渲染数据，再调用可能逐出窗口的 pager 查询；UI 不保存 borrowed layout、字体视图或窗口文本。
`exr_pager_read_text(range)` 的 sink 只追加当前页、受明确容量限制的临时 Data；超限明确失败，不截断并声称复制成功。
sink 不重入 pager，任一失败丢弃候选前缀。成功后才发布 pageText、CGImage 和页面身份。

`HostBitmap.pixels`、`CGDataProvider`、UI 的当页 String 都拥有数据；不保留章全文 Data。
跨页/跨章选择不是首版扩展。复制仍由现有原生选文控件操作有限 pageText，无须新建像素命中引擎。
统计分别列出章索引/parse workspace、page cache、checkpoint、bitmap 和 Swift frame 的文本/像素副本。
ARC 引用保留的 accepted/candidate 两帧也要计入峰值，不能只报告 cache 数字。

## HostModel.swift：路由、候选状态与持久化

`HostSession` 增加存储模式、publication、part/path、章内 page 和 readingOffset。
`changing` 的旧状态 tuple 必须覆盖这些新字段及 accepted frame 身份；解析、渲染、notes 或保存失败时恢复整个旧组合。
跨章创建候选 pager，只有完整渲染/必要位置存储成功且当前token可接受时才发布。

- `open/rebuildPager`：先 mode query，bounded book从source重开。新progress的present/存储错误分开；
  part/path校验后才建对应章pager，仅FOUND允许精确恢复。MISSING/AMBIGUOUS不能写回为精确位置。
- `turn/firstPage`：part+page是显示坐标，不能把本章EOF当全书结束。跳过非reading-order part，重复path由part区分；
  向前跨章到前章末页使用可取消的get/checkpoint重放，不预排整书求总页数。
- `renderSnapshot`（约244行）：去掉 `slice(document.text, range)` 和全书字节百分比。
  bounded页面显示章/当前页及已知的本章统计，不虚构全书精确百分比。
  `cancel.commit` 内写新point并更新accepted章内位置；保持原保存失败回滚页面/字号/viewport的边界。
- `persistCurrent`、后台/退出及 `backToLibrary`：沿新模式保存part/path/selector，不重新打开全文，也不覆盖旧global位置。
- `stateHash/writeState`（约370行）：bounded book 的旧books.position固定0，不能把它当实际位置。
  状态需包含模式、part/path/章内offset、accepted frame generation与notes类型，hash应覆盖这些字段。
  host-state payload若新增必需契约，应明确升级其schema并严格验证；它不同于SQLite user_version或platform evidence schema。

同 owner 的进度/评论更新不使源失效；其他数据库连接提交会按SDK契约令旧source失效。
显式重开source/publication并重新解析位置，不能把读失败当EOF或无记录。

### 同章 notes 与 UI 选择

`HostNoteRow` 不能继续只用 `page >= 0` 区分fixed/其他。
增加明确存储类型及part/path，保留自己的ID命名域和Swift自有selector。
评论更新按book+note ID调用新notes的comment-only语义；删除按记录类型路由，不能串入旧notes/fixed_notes。

列表刷新不应为每条异章标注都解析整章。复制存储quote和路由后，对当前章必要条目解析，
异章条目保留“待定位”状态；允许发起候选章定位，只有实际FOUND才接受跳转/高亮。
不能把“存储成功”或“路由存在”当成精确匹配，也不能因未提前解析而永久禁用异章跳转。
歧义/丢失保留评论，不能以start=0伪造正常范围。

`HostSelectionContext`、`HostSession.matches`、`HostSnapshot` 加入part/path与frame generation。
当前session匹配只核book/text/baseOffset，跨章相同文字和相同local offset不足以防旧选择复用。
`HostViews.SelectionSheet.byteRange/annotateSelection` 的NSRange→UTF-8转换仍使用
`hostSelectionUTF8Range`；它只在当前页String上计算，再叠加本章baseOffset并携带part。
保留 `SelectableText.swift` 的原生 echo/request 区分、revision、事件序号、旧frame选择失效，
以及UI屏幕阅读名称/稳定ID。字号、旋转、窗口、换章、换书后必须重新选择。

## 旧记录兼容

默认新EPUB source导入；去重得到旧memory模式ID时保留原模式和全部global进度/笔记。
旧书继续明确snapshot兼容分支；不把旧global数字直接当part0/local，也不自动执行全文偏移转换。
新mode不能在预算/读取失败时悄悄降成library_document/blob快照。
新SQLite schema的旧数据迁移由SDK负责，Swift不自行建表或更改user_version。

## evidence_contract.py：必须同步改的强校验

当前 `database_state`（约245行）硬要求SQLite schema6，并要求旧 `notes/fixed_notes/book_progress` 都非空。
新EPUB路径的有效记录位于新表，旧列position=0；只把版本数字改成7会继续误判或漏判。

1. 新run绑定固定SDK的schema7，严格核application_id、quick_check、foreign_key_check及所需表/列。
   不改成宽松接受“6或7”；schema6只作为独立迁移输入，实际采集的升级后库必须为固定schema。
2. 按每本书模式核对 `epub_bounded_books`、`epub_progress`、`epub_notes` 或旧global表。
   新导入的验收EPUB必须有新mode、章内point与同章note；PDF必须有fixed note。
   不用“新旧任意notes有一条”这种OR替代逐书契约。
3. `host-state.json` 的模式/part/path/章内范围/selector/评论与SQL逐项对应；book集合、source hash、
   current frame文本hash、SDK/font、状态hash仍全部核对，新增类型域防note ID碰撞。
4. 旧schema6迁移的原件、metadata、global进度和notes另用冻结输入回归，升级后保留旧意义。
   不能把新表有数据当作旧记录已自动转换的证据。
5. 新增拒绝反例：schema7缺新表/marker、global列冒充章内进度、错误part/path、缺point、错note类型/书所有权、
   host-state与SQL章内坐标不一致、缺SOURCE/SDK身份、被拼接的旧run或旧attempt。
   继续保留所有既有伪造、缺原件、程序/运行库变更及summary拒绝回归。

SDK身份继续由三个target的安装树hash、Mach-O UUID、程序Info.plist的EXRSourceSHA及嵌入库验证。
八个候选新符号必须在固定SDK的公开头/可消费运行库中同源可用，不能只换Swift声明或沿用旧缓存SDK。
版本与ABI从固定头读取，ABI1不等于schema6；cache key仍包含完整source SHA。

## 云端出口与不降级原则

- 三平台原12个UI用例、61具名步骤、46份附件各自保留：现有CASES/ATTACHMENTS的身份、次序、像素与原件绑定不减。
  原7基础＋5修复回归都在正常新EPUB路径上执行，不能只跑legacy兼容路径交差。
- 原21项legacy self-test、SDK桥接21项、Model会话18项与既有证据拒绝回归继续保留。
  snapshot专用检查继续验证snapshot API；旧32MiB非EPUB上限及global numeric回滚不能因新EPUB position恒0而变成空断言。
  需要新入口的镜像检查时追加具名用例，不删除旧义务或把旧失败改标跳过。
- 新增独立、预声明的bounded suite：有界导入/取消、重复path、跨章同local offset、长章后段选文、
  章内notes CRUD/跨章跳转、字号/旋转/窗口逐出、重启恢复和歧义拒绝。
  提取器与summary必须严格核对新suite完整身份，不能把未知新case静默丢掉维持旧12的形式成功。
- workflow保持三SDK + 三UI + package + summary共八作业、八份必需工件的同run/source/attempt关系；
  实际新增作业/工件时明确更新声明集合，不能复用上轮SDK、程序、xcresult或数据库。
- 普通宿主程序、SDK/Model消费者、xcresult、原始日志、46份基础附件、新suite原件、host-state/SQLite、
  fixture/font/binary/runtime/source身份及严格summary同次齐全，才授予Apple新路径声明范围。

H9开始前只保留这份准备；实现时只改Apple局部桥接/宿主及专用验收。
真机安装/签名和VoiceOver真人验收继续独立跟踪，不以模拟器或可访问名称验收替代。
