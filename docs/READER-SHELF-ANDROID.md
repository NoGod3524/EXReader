# Android 本机产品目录分页书架

从已验收导入映射源码 `19128dc5f5e4a3164416ffa17e63937a3894989b` 建立独立分支
`codex/reader-android-shelf`。SDK 八条保护树保持冻结 K
`9854061be331fe603a1822d9b2b36ee357154927`；产品库继续使用 EXRP/schema 1，SDK
书库继续使用 schema 7。本包不改 SDK、bindings、产品 schema、导入发布/回滚或映射修复协议。

## 生产路径

- `CatalogStore.shelfPage` 在既有宿主 owner worker 查询产品目录；只连接有
  `reader_local_books` 的本机记录，并要求 `reader_books.deleted=0`。
- 使用 `(sort_title, book_key)` SQLite BINARY 顺序及双向 keyset；每条 SQL 固定
  `LIMIT 50`。同标题由源身份主键打破平局，无 OFFSET 扫描或全目录 UI 列表。
- 标题/作者搜索使用 NFC 输入和参数化 LIKE，转义用户输入中的 `%`、`_`、反斜线。
  输入最多 256 个 UTF-16 code units。大小写行为沿用 SQLite 默认 LIKE：ASCII
  大小写不敏感，不授完整 Unicode case folding 声明。
- `CatalogShelf` 只保留最多三页、150 条 immutable 目录快照；Android 原生 ListView
  回收书行 View。加载下一页时淘汰另一端；先记录当前顶行源身份与像素偏移，再恢复视口。
  快速反向滚动使淘汰可能伤及当前视口时，丢弃待入页，等后续边界滚动重新查询。
- 搜索文字变更立即取消旧 CancellationSignal 并提升 generation，180 ms 后读取新页；
  旧结果、取消结果和已销毁 Activity 的结果均不能更新书架。
- prefs 只保存查询、顶行 `(sort_title,book_key)` 与像素偏移。刷新、Activity 重建和
  重启从该 keyset 恢复；选书使用稳定 SDK ID，不要求恢复中的书位于当前 150 条窗口。
  同查询刷新前先保存当前视口，启动/查询尚未完成时保留已有锚点；换查询立即清除旧查询锚点。
- 书行保留原先的“标题 + 换行 + 简介”无障碍文本契约，原 45/10/11 测试源码和断言不改。

这只把**书架展示与目录读取**改为有界。冻结 SDK 目前只有全量 books metadata API；
现有启动映射修复仍枚举一次 SDK 元数据，选书的既有 `store.find` 也仍枚举一次。
本包不把整个启动、映射修复或 SDK 选书恢复称为常量内存。

## 云端出口

工作流 `.github/workflows/reader-shelf-android.yml` 使用 API34/default/x86_64、pixel_6、
4 cores、4096 MiB 和固定 Android 工具链。在同一源码、同一运行中依次要求：

1. 公共 SDK 实际导入 2,201 份不同短 TXT 和 1 份有作者元数据的 PDF，再调用
   生产 `BookStore.repairMissingMappings()` 建目录。目录 12 项检查包括正/反向全量 keyset、
   130 份同标题、作者/字面搜索、取消、owner 限制、隐藏未映射/已删除记录、实际新导入刷新。
   第 9 项控制异步调度顺序但使用真实产品 SQL，证明被取消旧查询不能覆盖新结果；
   第 10 项证明尾部失效锚点只在同一搜索条件内做反向回退。
   第 11 项控制真实请求的调度，证明 SDK 尚未打开/查询尚未返回时销毁不丢原查询锚点，
   切换查询后销毁则不复用旧查询锚点。
   第 12 项用真实 SDK 的 NFD 书名和 PDF UTF-16BE 作者，验证 NFC/NFD 查询命中同一源，
   且目录保留原始 display title/author UTF-8。标题查询复用 NFC `sort_title`，作者绑定
   NFC/NFD 两个有界字面 pattern；不改变 schema，也不宣称任意混合正规化或 Unicode casefold。
2. 在真实 app 主书库重新导入并映射 2,202 本，由独立 UI Automator helper 操作生产
   MainActivity：全库正/反滚动、所有可见源身份、View 回收、搜索、快速查询、刷新锚点、
   旋转/后台/不同 PID 重启、离线打开 TXT/返回、系统文件选择器新增导入，共 10 项。
   全库遍历使用真实 ListView 无障碍分页滚动，逐视口采集可见 key；快速换向另注入触摸滚动。
   每次读取的 debug observation 最多包含 150 个缓存 key，另列真实可见 key；不返回全目录。
3. 原 catalog 8、导入映射 14 和 2 次独立杀进程恢复，原检查器原样使用。
4. 原 45 + review 10 + bounded 11、49 页/49 native next/0 recovery，原证据门禁 48 和
   bounded 20，原严格检查器原样使用。同源码缺项、跳过或任一失败均不授联合通过。
5. 本包严格汇总重新核对原 UI/帧/PSS 证据，要求目录、UI、映射与原宿主出口均为同 source/run；
   再运行 17 个拒绝探针以及前后两个正例，拒绝旧源码、失败、缺截图、截断回调、采样错误、
   PSS 原文缺失/汇总不符、缺进程恢复或缺原门禁。

## 观测口径

`shelf_metrics=true` 显式启动参数只在 debug 构建启用观测，普通启动没有文件采集器。

- 首个可交互：从 `MainActivity.onCreate` 开始计时，到真实目录页已应用、ListView 可见且
  已启用的首次 pre-draw；包含现有 SDK 打开/映射修复。helper 晚读观测值不充当起点或终点。
- `Window.OnFrameMetricsAvailableListener` 逐回调复制系统 FrameMetrics，在独立
  HandlerThread 写 JSONL；每个真实 Window 实例、PID、递增 callback sequence 独立记录。
  保留系统 dropCount，丢失、错误或截断则拒绝本轮观测。单 Window 最多 20,000 帧/32 MiB。
  同一显式 debug 开关下，pre-draw 核对真实书行 tag 与目录快照，再标记已布局 revision；
  helper 要求该 revision 与应用 revision 相同，且两次新读的视口一致，才比较恢复/滚动。
- UI helper 用同一设备 elapsedRealtimeNanos 标记正/反向滚动区间。汇总按完成回调时间
  归入区间，报告普通帧 TOTAL p50/p95/p99/max；不是屏幕呈现时间或隔离 ListView 的耗时。
- 云端外部约每秒按 PID 读取全进程 TOTAL PSS，保留原文。报告采样次数、中位和采样峰值；
  不是连续峰值，也不据此推导单模块分配或“零分配”。进程切换期间无稳定 PID 的样本单列。
  严格汇总逐个 slot 重读稳定 PID 的 dumpsys 原文，核 PID/TOTAL PSS 后重新计算分位与峰值，
  同时记录原文大小与 SHA-256，拒绝缺失原文和不符的采样 JSON。
- 回调复制/文件写入、PSS 采样和 UI helper 都会增加开销。强制结束进程可能留下换行完整但
  无 stop 的文件，不能据此声称整个会话的所有显示帧均已穷尽。

本轮先建立功能出口和观测，不设置新性能/大小预算，不引用旧 NONE/SOFTWARE ABBA 数据。
真机、签名、TalkBack、网络同步、云端冲突和其他平台 UI 保持独立验收。

## 运行记录

- `84633b5278ba0062e055852551553f0e22cd94d4` / run `40021039897`：下载固定 NDK
  时 archive 错误，未进入编译，无工件；保留失败。
- 同源码新 dispatch `40021673050`：Javac 拒绝 TextWatcher 的参数/字段遮蔽；已修正，
  未改断言。此轮未授任何测试通过。
- 候选 `5cf5ba8b757502930c3c79ae60894f299414e068` / run `40022562607`：编译成功，
  catalog 9 项为 8 过/1 失败/0 跳过。作者断言失败后核对冻结 SDK：legacy/bounded EPUB
  导入均不提取 dc:creator，PDF/CBZ 导入会提取作者。后继用真正含 `/Author` 的 PDF 检查
  作者搜索，不写 SDK 私有表，也不把 EPUB 作者提取纳入本包声明。原映射 14 项的
  legacy/bounded EPUB 模式覆盖保持完整。此轮未进入 UI 或完整回归，不授书架验收。
- `f24eeebf220b4ac9add5b6d3668e909ca9cc50f3` / run `40023575299`：catalog 10/10、
  UI 8/10，0 跳过。全 2,202 源的可见正向遍历、反向/回收、同标题、搜索、旋转/后台/重启、
  离线阅读返回均通过；刷新用例在搜索 debounce 完成前滚动，系统 picker 遇到节点陈旧，
  两项失败保留。后继增加真实页就绪等待及重新取节点/有界重试，不放宽断言。
  此轮未执行其后的原 mapping/完整 UI/门禁，不能拼接前轮通过项。
- 保留工件纯云端回读 `40032623602` / 源码 `4c65e057a4a5b4f927bbd31ead8baefc6de7c348`
  成功，固定核验上述工件 `12532665458`、55,648,465 B、
  `sha256:470aa20d11c3353980db6f251f0bc39520c251cec6462473b4d36fbf461da00d`。
  回读只定位原失败，`diagnostic_only=true, accepted=false`，不授产品验收。
- `82a4c4c474eb754975e13294e4a45c5e9f73d4ec` / run `40032860158`：目录 10/10、
  实际 UI 10/10、原 catalog 8/8 与 mapping 14/14 均通过。随后 kill 探针启动被拒：
  connected tests 会卸载目标 app，组合工作流只重装了 instrumentation APK。后继按原导入
  工作流同时重装 app 与 instrumentation，再执行原样 kill/recovery 探针。此轮未执行原 66
  和门禁，严格汇总拒绝，保留 failure；首屏/窗口/PSS 结果只属于本轮观测，不转授后继。
- `334e3f16d63cc53c9356f8a3147b8e43fcc823d5` / run `40033393345`：生命周期与真实布局修复后，
  目录 11/11、UI 10/10、原 catalog 8/8 与 mapping 14/14 均通过；仍因上一项已修的 target
  app 重装问题停止于 kill 阶段，保留 failure。
- `23e5133fcf06a327605d00b893072ff36d39e0e1` / run `40034076410`：目录 11/11、UI 10/10、
  原 catalog 8/8、mapping 14/14、kill/recovery 2/2 同次成功；原宿主 45/45、review 9/10、
  bounded 11/11，49 页/49 native next/0 recovery。唯一原回归失败为
  `destroyed_activity_releases_worker`：新 Activity 尚未加载书架窗口，临时 loading 文案使用
  “book”，没有显示实际书名；后继从 worker 的单条本机目录查询取真实书名，按 generation
  更新 loading/错误文案，保持原进度锁与旧断言。原严格汇总拒绝，未授联合验收。
- 上一工件云端回读 `40036326340` 成功，固定核验 `12536608131`、106,901,651 B、
  `sha256:b5024d1d8006c6076ac660073cacab012571afe38781cd03ccee42caeb79e34b`；
  只定位原失败，`diagnostic_only=true, accepted=false`。
- `d448e5e91fe323057ca2fc8f82b69bd933b6d4c8` / run `40036544464`：修复恢复书籍的
  loading 标题，云端完整回归仍运行；尚未授联合验收。
- 后继修复 NFC 查询原始 NFD display title 漏项，增加第 12 个目录专项，并在真实 UI 的
  既有搜索用例中验证 NFC 书名和作者；所有出口仍须新源码同轮云端完成。

本地仅源码/文档编辑和 Git；编译、语法检查、夹具生成、SQL、仪器化、工件读取/解析均在
GitHub Actions。最终验收以同源完成日志、工件身份和严格汇总为准。
