# Android 分享、打开与 SAF 文件入口

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
文件名只由内容决定，provider给的名字从不进入路径。

**内存。** 复制缓冲固定64 KiB，每次复制恰好一块；不做整文件分配；SHA-256流式计算。staging为
`<filesDir>/exr-import/{tmp,ready,lock}`。就绪文件归entry所有，直到宿主调用`release(request)`；
宿主在SDK调用返回前不得释放。原生`exr_android_import_request`中的字符串仅在调用期间借用。

**线程与重入。** 所有`ImportEntry`方法可从任意线程调用且不做阻塞I/O。复制在一个私有线程进行（一次一个文件）。
回调运行在宿主提供的`Executor`（缺省主线程），不持有内部锁，可重入调用`release`／`submit`。
复制线程不运行任何宿主SDK代码；宿主应把owner executor设为其唯一SDK线程。`exr_android_import_commit`同步执行，
只能在拥有该`exr_library`的线程调用；范例桥接用`pthread_equal`拒绝其他线程（返回`EXR_ARGUMENT`）。
同一staging目录同时只能有一个存活entry（进程内登记＋跨进程文件锁）。

**错误。** `ImportError.Code`：`ARGUMENT`、`PERMISSION`（授权被拒或在打开前撤销）、`NOT_FOUND`、`IO`（读取失败、
provider中途报错、停滞超过30秒、早于声明长度结束）、`EMPTY`、`LIMIT`、`UNSUPPORTED_FORMAT`、`BACKLOG`、`STAGING`、`CANCELLED`。
失败时不留任何临时或就绪文件。

**取消与提交边界。** `ticket.cancel()`在原子发布前有效，即使provider停滞也在约250 ms内生效并删除临时文件。
提交边界是`ticket.commit()`：发布（`fsync`后`ATOMIC_MOVE`到`ready/<id>`）之前取消成功，之后`cancel()`返回false，
已发布文件不会被撤回，宿主改为`release`。`close()`取消全部未提交票据（各得一次`CANCELLED`），可重复调用，
异步释放staging锁。`exr_android_import_commit`在SDK提交后不会伪报取消。

**生命周期。** 票据不绑定Activity：旋转或关闭界面不会中断复制。重建的Activity不得重新提交已提交的intent
（范例以`savedInstanceState != null`判断）。进程被终止后，下次`create`删除所有`tmp/`残留；已发布但未交付的文件由
`pendingReady()`列出，宿主据此重投；SDK按格式与原字节精确去重，重复导入返回`created=0`。
Intent授权覆盖接收任务：须在finish接收Activity之前调用`submit`。打开之后撤销授权不会关闭已打开的描述符（Android语义），
复制照常完成；打开之前撤销则得到`PERMISSION`。

**硬上限。** 64 KiB缓冲；TXT／HTML／FB2／DOCX／RTF／MOBI 32 MiB，EPUB／CBZ／PDF 128 MiB
（与`exr_sideload.h`的`EXR_SIDELOAD_MEMORY_LIMIT`／`STREAM_LIMIT`一致，原生组件再次校验）；声明长度超限在读取前即拒绝，
未知长度在流中超限即拒绝；每个intent 64个URI；未完成票据64个；未释放就绪请求32个；停滞超时30秒。

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
