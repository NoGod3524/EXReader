# Android 阅读记录：进度、书签与标注

宿主固定起点 `d68d8e388730f0fbd9e86c70a422388be406391d`；分支 `codex/reader-android-reading-ui`。从 root 共同源码 `ba25961961ae69222bfed4f7a98cb02bb1dc6847` 只原样引入 G03 `apps/reader/reading-commands/`（树 `cf067b8be378d4195817d1106b81f358579e2280`）和 G04 `apps/reader/annotation-view/`（树 `9d30b6c54f61496010f647695dedd7ea7ab0c7c1`）；不合整支历史。现有 reading-state codec 源码/构建树 `60127ae75fbac918237b1c8584e0f7ac2e6130a4` 与该 root 完全相同，保留旧 v2/NUL/chapter/spine 支持。此轮不需要 G05 导出模块。

Android API34 `default` x86_64 模拟器范围验收通过。受测源码 `047648865e509d5835b7d6e1389681e314d94e28`；[run 40131364703](https://github.com/NoGod3524/EXReader/actions/runs/40131364703) attempt 1，job `120983574659` success。所有构建、语法检查、测试、夹具和工件解析均在 Actions；本地仅编辑与 Git。

## 路径与所有权

写入限于 Android 宿主、`tests/reader_android_reading/`、独立工作流 `reader-android-reading.yml`、本文件/验收JSON，以及上述两个固定模块子树。SDK、既有 codec、产品 schema1、其他平台、25个J包与原回归工作流保持原样。

SDK调用继续在原SDK worker与`exreader_host` DSO；产品命令/快照借用现有`product_jni` owner的`reader_revisions`，在原`exreader_product` DSO及唯一产品SQLite provider内执行。G04视图只在一次页请求内借用该store，输出复制后释放；不新增owner registry、SQLite、SDK副本或线程池。

## 记录与跳转

低频“阅读记录”面板默认隐藏。显式保存当前进度、当前页点书签或真实选区标注时，先核对当前帧绑定的原件身份，再由公开SDK作真实capture，将完全复制的selector交G03。固定页保留字节长度/NUL；EPUB保留part/path；reflow保留nullable chapter。G03只写产品history/outbox。原SDK Notes及自动阅读进度仍沿用原路径，不把产品修订复制进SDK数据库。

G04以32项keyset页显示书签/高亮/笔记及tombstone。非SAFE状态只显示真实图计数，不选head、不伪造body/位置。独立SDK对象只在用户明确选择后解析，只有FOUND才走原renderer；MISSING/AMBIGUOUS/LEGACY不以偏移、百分比或页号兜底。实际导航仍由原宿主保存实际显示页的阅读位置。

删除写明确delete修订。恢复不从SAFE tombstone猜位置：通过公开`reader_revision_get`返回的已校验wire沿parents有界读取保留版本，用户明确选择版本；独立FOUND后重新真实capture，再以当前完整观察head集合调用G03 restore。旧wire不改写，父历史不删除，过期head拒绝并要求刷新。编辑正文由G03 NOTE_TEXT保持原selector/parser，不改其位置。

写请求在产品提交前把稳定revision ID、完整观察head集合和完全复制的capture存入宿主私有原子请求文件。响应不确定时仅重试同一份已保存请求，不重新捕获或分配实体；模块exact-retry不会重复排outbox。首次缺少书籍产品历史时，仅通过现有已验证原件的typed bootstrap建立事实，不直接写SQL。

关闭、换书、旋转、后台和销毁取消尚未提交的请求、拒绝旧epoch的列表/定位回调。已经开始的事务按原HostTask提交边界完成，重新打开面板观察实际保留结果。

## 同源码验收出口

私有请求文件的读写在进程内跨 Activity owner 串行；旧 owner 的自动清理必须匹配自己提交的 revision ID，避免旋转后的新请求被迟到的清理删除。显式“结束确认”才允许丢弃当前待确认请求。

CBZ 在冻结 SDK 中没有 text provider，不能通过公开 fixed anchor 接口产生真实捕获；本面板明确报告不支持，不以空白捕获替代。空白 PDF 有公开空文本快照，其真实点捕获单独验证。固定 selector 中的 NUL 会原长传给 SDK；产品 wire 的现有限制仍由 G03/codec 明确拒绝，不截断后保存。

旧导入 EPUB 的 global renderer 与现代 bounded chapter renderer 使用不同坐标。收到另一投影模式的产品 selector 时明确拒绝导航/恢复，不把章节字节偏移当作全书偏移；保留原修订和当前画面。专用夹具通过真实 legacy 导入及独立公开 pager 捕获第二章位置，再经 G03/G04 验证拒绝路径。

新测试 **16/16**：首进程 14 组、真实提交后杀进程再精确重试 1 组、再次重开 1 组，全部实际通过。三个有报告的进程 PID 为 `7211 / 7600 / 7709`；原 SDK 导出、公开捕获/回读、WebDAV 实际 backend `91+4`、正式宿主 16、搜索 15、导航 18 及全部安装/provider 检查在同一源码保留并通过。

七份合成原件在三个阶段共 21 次 SHA/字节核对均一致；保存 15 份真实语义树/PNG。覆盖 TXT 真实选区与点、EPUB 28pt/part/path、PDF 和空白 PDF 实际 page ID、NULL/空值/NUL 拒绝边界、真实 legacy EPUB 坐标投影拒绝、跨 owner 请求文件、conflict/pending/blocked 只显示图计数、过期 head、NOTE_TEXT selector 不变、delete/明确历史版本 restore、取消、关闭、实际旋转、后台与32行 keyset前后翻页。

真实 postcommit gate 上 PID `7461` 被 `force-stop`，停止后无 PID。已持久请求 606 B，SHA-256 `e9324ebb2b56c61cfcc115e9f053d03464e5d6bb756a164f1b6b0cddc581941e`，revision `b18fa79129854b8496d9606b5b88c312`、annotation `05d2db1b883c476198b04fea34cdd36d`。新进程明确确认原请求后仍为该 ID/head，完整 history/outbox/SDK 快照相同，没有重复或重新排队；私有待确认文件仅在确认后清除，再次新进程重开通过。

主工件 `reader-android-reading-40131364703-1`：ID `12575367601`，**136,598,458 B**，SHA-256 `9519c0c26d219322cbd95d3914733661aaff40df6c0c2d7214969a72fa81cbd2`，有效至 `2027-01-22T20:47:29Z`。包含 Debug/Release APK、全部原回归/新 UI 原始记录、所有安装包/映射/符号材料和源码身份。

独立只读诊断 [40132592232](https://github.com/NoGod3524/EXReader/actions/runs/40132592232)（job `120987289869`，源码 `ef9433153dc04cb5846946fbf5dcbddaf8f6d967`）在 Actions 下载该原 ZIP，核对原 run/source/job、ID、字节、完整 digest、未过期状态，再解析其中三阶段报告、15图/21原件身份和原请求字节，全部通过。诊断自身保持 `diagnostic_only=true, accepted=false`，不重新授予运行；诊断分支不合入产品。

安装的 G03 archive 700,790 B、SHA-256 `f738a24885d9a5252c3824a3ad61b6c47fe9dc47857ca030f7068bc6986e6682`；G04 420,506 B、SHA-256 `09e6c530dfca81714977c0bbd5fbe1169b4b30f01770a52c278252126adde5a6`。Debug/Release 都只在原 product DSO 定义命令、快照与 codec；仅一个产品 SQLite，产品 DSO 无 SDK 依赖/静态 SDK，SDK host 继续由原 `libexreader.so` 提供 SDK。Release 不包含 debug probe/测试入口。

实际共享 SDK 配置保留 AUDIO/MP3/JNI/SHARED ON、AAC OFF；这是原正式 Android profile。SDK cache SHA `e597e6f5e1c0512fbff2be9c761a32c2a579d43db07d7c2d3abb7100b852366b`；安装 SDK `libexreader.so` 22,258,128 B / `42bb8b94f1226f7a0d446c0c996762379d18a1e42abb03e4a0e08423947f80c2`；两个 APK 的 SDK/JNI 同为 5,545,208 B / `041ba9141a4b0c655545349ee61be8bc36abccfca872cb852a8677f6753dee8b` 与 40,392 B / `182ee0175ca883aa5a3cc5d985b215cba2808df508ab7381cb341423909981f2`。

此前失败与取消均保留在验收 JSON：缺 SDK package prefix、fixed `page_id` 的 C++ const 类型、误用未启用的 shelf 绘制计数、同名筛选框误当书行、fixture 缺 transport SHA，以及 Instrumentation 结束后的正常进程退出假设。修复未修改 G03/G04/codec/SDK 保护树或放宽数据断言；早期已有通过的新 UI 组数及每次原工件身份逐项保留。纯证据提交仅改本文件与验收 JSON。

真机、TalkBack语音、产品性能和六平台完整产品仍单列。
