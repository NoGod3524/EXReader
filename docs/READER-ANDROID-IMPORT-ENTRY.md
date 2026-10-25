# Android 分享、打开与 SAF 文件入口

## Root复审候选

独立分支 `codex/reader-android-import-entry-review` 从原交回HEAD `635ddcb3f865059fd481f8deb9f7927e75743c6d` 开始；未修改原外部工作树或宿主。最终受测源码 `f5046e1fbe2cc91d2ec71a51d2020c1c38e4d969` / [run 40161341409](https://github.com/NoGod3524/EXReader/actions/runs/40161341409) attempt1 三作业success：设备95/95（原78项保留）、42项具名必需检查齐全，严格汇总problems=[]。仅授予该独立组件的API34 default x86_64模拟器范围；真实宿主接线另验。

作业：guards `121073369421`、android `121073369108`、summary `121074094360`。工件有效期均为 `2027-01-23T04:17:26Z`：guards `12585809111` /1129B /SHA-256 `eea8299b045ec55b8cf07fcd4f48ece3935e6d9adf327301ecf155d8090b37d5`；android `12586462366` /11536095B /`9ef65c6ee43a0f65fb64b0a2d865f68631ab906f375655aafd5b606cfdba60ac`；summary `12586089149` /1281B /`0642b799166386aaef52796032cf48e47302d87f9cd1f9abfc8fc2ebdb45d5f0`。汇总实际认证当前attempt上游作业、两原ZIP完整字节/散列/有效期后读取报告。32次真实可靠pipe错误前后FD均108；direct Executor抛出后共两票各一次Ready、零Failed、首票COMMITTED，两lease可清理。

修复四个实际问题：ticket取消与提交共用同一短锁，防止cancel返回true后仍发布；每个ReadyRequest是独立entry-owned lease，重复内容共享单一私有文件且仅最后lease删除，foreign/stale/repeated release无效；可靠pipe的checkError异常也必须关闭描述符；query.SIZE小报不得把未知长度pipe前缀当完整原件。保留原78项断言，新增20,000次真实双线程竞争、积压重复回调/跨entry/跨close代际lease、32次真实可靠pipe错误FD计数，以及小报长度拒绝。汇总另认证当前attempt的上游作业和原ZIP id/字节/digest/有效期，在Actions内重算散列后读取报告。

review首轮 source `206f89045a9c64c5f6188643f8e2117320a1a346` / run `40160142660` 的guards与编译通过，设备92项通过、1项失败：原78项、20k竞争、全部lease反例、小报长度和32次可靠pipe IO均通过；新增FD总量检查107→118，超出原定baseline+4。失败及工件保留，阈值不变。回归现先做一次真实分享取得grant及IO预热，再在同一Activity/已授予URI上直接提交32次真实provider复制，避免把反复创建分享窗口的资源混进pipe比较；两端FD清单用`/proc/self/fd`真实readlink留存。此调整尚待云端，不把107→118解释为已排除泄漏。

source `36021cce35f90b8439f85967075bd34c7d867306` / run `40160762696` 的guards、android、summary三作业均success；94/94设备检查，41项具名必需项齐全、problems=[]。summary在Actions内实际核对两个上游job身份与ZIP完整字节/SHA/有效期。该源的通过数不覆盖接下来的callback修复。

同轮复审确认：direct Executor下onReady抛RuntimeException原本会被复制catch误当IO，再通知onFailed。现把copy/发布异常和finish/deliver分开；回调RuntimeException在一次通知后被包含，COMMITTED不撤回、未释放ready lease仍供显式清理/恢复，不再伪造第二次失败。新增真实provider两请求/direct Executor负例：第一onReady主动抛出，第二请求是串行worker排空屏障，严格核两个票据各一次Ready、零Failed、首票COMMITTED及两lease最终清理。该路径已在最终95项完整源码轮通过。

`extras/android-import-entry`是可选独立模块，不进入默认SDK构建，不改变SDK3.40.0／ABI1／schema7，
不修改`examples/android`、现有Android owner或`extras/sideload`。它由两部分组成：

- Java库`org.exreader.importentry`（Gradle `:importentry`，API26，AAR不含权限、组件或原生库）：
  接收`ACTION_VIEW`、`ACTION_SEND`、`ACTION_SEND_MULTIPLE`和文档选择器结果，把每个`content:` URI
  复制到应用私有staging，交给宿主owner。
- 原生静态库`exr_android_import_entry`（C11）：`exr_android_import_commit`校验就绪文件后调用已发布的
  `exr_sideload_import_file`。安装目录附带可编译的JNI桥接范例`share/exreader-android-import-entry/sample`。

## 接口契约

**输入。** `ImportEntry.submit(Intent)`取intent的`getData`、`EXTRA_STREAM`（单个或列表）和`ClipData`中的全部
`content:` URI，去重后最多64个；超出的票据以`BACKLOG`结束。`file:`等非content scheme以`ARGUMENT`结束。
`submit(Uri, mimeHint)`提交单个URI。MIME和显示名只是类型提示；格式最终由首块魔数确认并必须一致：
`%PDF-`、ZIP首项`mimetype`＝`application/epub+zip`、`{\rtf`、`BOOKMOBI`；ZIP容器只有在提示为EPUB／CBZ／DOCX时接受；
其余为文本（含NUL且无UTF-16 BOM者拒绝）。模块不解析书籍内容。

**输出。** 每张`ImportTicket`恰好得到一次回调：`onReady(ticket, ReadyRequest)`或`onFailed(ticket, ImportError)`。
`ReadyRequest`含内容身份`id`＝`<SHA-256>.<扩展名>`、私有文件、`ImportFormat`（`exrCode()`即原生`exr_format`）、
字节数、清洗后的标题提示（至多256字节UTF-8，无分隔符与控制字符）和`alreadyStaged`。
文件名只由内容决定，provider给的名字从不进入路径。每次交付取得不同ReadyRequest lease；相同id共用文件，release只消耗传入的本entry lease，最后一个lease释放才删除。`pendingReady()`列出所有未释放lease，同内容可能重复出现；重复读取该列表不增加lease。32个就绪请求上限按lease数计。

**内存。** 复制缓冲固定64 KiB，每次复制恰好一块；不做整文件分配；SHA-256流式计算。staging为
`<filesDir>/exr-import/{tmp,ready,lock}`。就绪文件归entry所有，直到宿主调用`release(request)`；
宿主在SDK调用返回前不得释放。原生`exr_android_import_request`中的字符串仅在调用期间借用。

**线程与重入。** 所有`ImportEntry`方法可从任意线程调用。`create`／`release`执行私有文件系统I/O，宿主应在UI线程之外调用；其余方法不直接执行provider I/O，但可能等待内部发布锁。复制在一个私有线程进行（一次一个文件）。
回调运行在宿主提供的`Executor`（缺省主线程），不持有内部锁，可重入调用`release`／`submit`。
宿主回调抛出的RuntimeException不会变成provider IO或第二次终态通知；已交付ready lease保留，宿主通过pendingReady/release处理。宿主应在回调中自行记录和展示自己的SDK错误。
复制线程不运行任何宿主SDK代码；宿主应把owner executor设为其唯一SDK线程。`exr_android_import_commit`同步执行，
只能在拥有该`exr_library`的线程调用；范例桥接用`pthread_equal`拒绝其他线程（返回`EXR_ARGUMENT`）。
同一staging目录同时只能有一个存活entry（进程内登记＋跨进程文件锁）。

**错误。** `ImportError.Code`：`ARGUMENT`、`PERMISSION`（授权被拒或在打开前撤销）、`NOT_FOUND`、`IO`（读取失败、
provider中途报错、停滞超过30秒、早于声明长度结束）、`EMPTY`、`LIMIT`、`UNSUPPORTED_FORMAT`、`BACKLOG`、`STAGING`、`CANCELLED`。
失败时不留任何临时或就绪文件。

**取消与提交边界。** `ticket.cancel()`在原子发布前有效，即使provider停滞也在约250 ms内生效并删除临时文件。
取消与`ticket.commit()`的进入共用同一短锁；commit进入后开始不可撤回的发布阶段（`fsync`后`ATOMIC_MOVE`到`ready/<id>`），之后`cancel()`返回false，
已发布文件不会被撤回，宿主改为`release`。`close()`取消全部未提交票据（各得一次`CANCELLED`），可重复调用，
异步释放staging锁。锁移交前清除旧entry的lease表，之后旧ReadyRequest不能删除新entry恢复的文件；已发布文件仍供新entry恢复。宿主须先排空/停止旧owner的SDK工作再切换entry。`exr_android_import_commit`在SDK提交后不会伪报取消。

250ms取消切片与30秒停滞检测覆盖已经打开描述符后的poll/read复制；当前同步ContentResolver.query/getType/open Binder调用没有内部超时或取消信号，不保证恶意/无响应provider在这些阶段的取消时限。现有停滞取消用例不覆盖该缺口。

**生命周期。** 票据不绑定Activity：旋转或关闭界面不会中断复制。重建的Activity不得重新提交已提交的intent
（范例以`savedInstanceState != null`判断）。进程被终止后，下次`create`删除所有`tmp/`残留；已发布但未交付的文件由
`pendingReady()`列出，宿主据此重投；SDK按格式与原字节精确去重，重复导入返回`created=0`。
Intent授权覆盖接收任务：须在finish接收Activity之前调用`submit`。打开之后撤销授权不会关闭已打开的描述符（Android语义），
复制照常完成；打开之前撤销则得到`PERMISSION`。

**硬上限。** 64 KiB缓冲；TXT／HTML／FB2／DOCX／RTF／MOBI 32 MiB，EPUB／CBZ／PDF 128 MiB
（与`exr_sideload.h`的`EXR_SIDELOAD_MEMORY_LIMIT`／`STREAM_LIMIT`一致，原生组件再次校验）；声明长度超限在读取前即拒绝，
未知长度在流中超限即拒绝；query.SIZE只用于限额及最终长度核对，只有AssetFileDescriptor实际子区间长度可以截定读取边界；每个intent 64个URI；未完成票据64个；未释放就绪lease32个；已打开描述符的停滞超时30秒。

## 宿主接入

见`extras/android-import-entry/sample/README.md`。安装后消费：`find_package(EXReaderAndroidImportEntry CONFIG REQUIRED)`，
把`${EXR_ANDROID_IMPORT_ENTRY_SAMPLE_DIR}/host_bridge.c`编入宿主JNI库并链接
`EXReaderAndroidImportEntry::exr_android_import_entry`；Java侧把安装的`sample/java`加入源码集并依赖`:importentry`。
构建顺序：冻结SDK → `extras/sideload` → `extras/android-import-entry`，用`tests/reader_android_import_entry/stage_sdk.py`可复现。

## 验收

`.github/workflows/reader-android-import-entry.yml`在同一提交上运行三个作业：
`guards`（路径白名单、受保护树与固定起点逐字节相同、源码守卫，每条守卫先以具名正反例自测）、
`android`（API26 Debug／Release编译；API34 x86_64模拟器上以自建`DocumentsProvider`和真实分享Intent执行场景，
再由已安装SDK导入并回读）、`summary`（`check_evidence.py`要求所有工件同一commit／run／attempt，三十一项必需检查（模拟器共78项检查）
全部存在且通过，否则失败）。生成报告本身不构成通过。

模拟器场景包括：非seekable管道短读（1～37字节写入）、未知长度、声明长度、声明与实际不符、provider中途报错、
恰为32 MiB与超出32／128 MiB、拒绝在读取前打开的超限声明、打开前撤销授权与从未授权、`file:` URI、
停滞时取消、`close()`中途取消并可重建、返回键关闭界面后复制完成、横屏旋转后恰好交付一次、
复制中途`force-stop`后临时文件被清除、发布后`force-stop`再启动由`pendingReady`恢复并导入、
重投去重（已暂存的相同内容只留一个文件；EPUB重投时SDK精确重复返回`created=0`，TXT的SDK去重未单独验收）、provider名字只是提示、64 KiB读取上限。

范围：仅API34 x86_64模拟器；未在真机、其他API级别或其他ABI上运行；不涉及音频或朗读；
`DocumentsProvider`为本包自建，未接触第三方云盘提供器；未验证`ACTION_OPEN_DOCUMENT`的系统文档选择器界面
（以本包自建的选择器Activity返回含授权的结果代替）；未进行带外部存储权限的旧式文件路径访问（刻意不支持）。

已知SDK行为：恰为32 MiB的TXT可完整暂存，但SDK内存导入返回`EXR_LIMIT`（状态6）；入口不改写该结论，文件保留给宿主决定释放。
模拟器验收记录见[validation/reader-android-import-entry.json](validation/reader-android-import-entry.json)。
