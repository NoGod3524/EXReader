# Android 阅读记录：进度、书签与标注

宿主固定起点 `d68d8e388730f0fbd9e86c70a422388be406391d`；分支 `codex/reader-android-reading-ui`。从 root 共同源码 `ba25961961ae69222bfed4f7a98cb02bb1dc6847` 只原样引入 G03 `apps/reader/reading-commands/`（树 `cf067b8be378d4195817d1106b81f358579e2280`）和 G04 `apps/reader/annotation-view/`（树 `9d30b6c54f61496010f647695dedd7ea7ab0c7c1`）；不合整支历史。现有 reading-state codec 源码/构建树 `60127ae75fbac918237b1c8584e0f7ac2e6130a4` 与该 root 完全相同，保留旧 v2/NUL/chapter/spine 支持。此轮不需要 G05 导出模块。

当前未验收，所有构建、语法检查、测试、夹具和工件解析只在 Actions。结果只按实际同源码新运行登记，不继承模块或此前移动 UI 的通过。

## 路径与所有权

写入限于 Android 宿主、`tests/reader_android_reading/`、独立工作流 `reader-android-reading.yml`、本文件/验收JSON，以及上述两个固定模块子树。SDK、既有 codec、产品 schema1、其他平台、25个J包与原回归工作流保持原样。

SDK调用继续在原SDK worker与`exreader_host` DSO；产品命令/快照借用现有`product_jni` owner的`reader_revisions`，在原`exreader_product` DSO及唯一产品SQLite provider内执行。G04视图只在一次页请求内借用该store，输出复制后释放；不新增owner registry、SQLite、SDK副本或线程池。

## 记录与跳转

低频“阅读记录”面板默认隐藏。显式保存当前进度、当前页点书签或真实选区标注时，先核对当前帧绑定的原件身份，再由公开SDK作真实capture，将完全复制的selector交G03。固定页保留字节长度/NUL；EPUB保留part/path；reflow保留nullable chapter。G03只写产品history/outbox。原SDK Notes及自动阅读进度仍沿用原路径，不把产品修订复制进SDK数据库。

G04以32项keyset页显示书签/高亮/笔记及tombstone。非SAFE状态只显示真实图计数，不选head、不伪造body/位置。独立SDK对象只在用户明确选择后解析，只有FOUND才走原renderer；MISSING/AMBIGUOUS/LEGACY不以偏移、百分比或页号兜底。实际导航仍由原宿主保存实际显示页的阅读位置。

删除写明确delete修订。恢复不从SAFE tombstone猜位置：通过公开`reader_revision_get`返回的已校验wire沿parents有界读取保留版本，用户明确选择版本；独立FOUND后重新真实capture，再以当前完整观察head集合调用G03 restore。旧wire不改写，父历史不删除，过期head拒绝并要求刷新。编辑正文由G03 NOTE_TEXT保持原selector/parser，不改其位置。

写请求在产品提交前把稳定revision ID、完整观察head集合和完全复制的capture存入宿主私有原子请求文件。响应不确定时仅重试同一份已保存请求，不重新捕获或分配实体；模块exact-retry不会重复排outbox。首次缺少书籍产品历史时，仅通过现有已验证原件的typed bootstrap建立事实，不直接写SQL。

关闭、换书、旋转、后台和销毁取消尚未提交的请求、拒绝旧epoch的列表/定位回调。已经开始的事务按原HostTask提交边界完成，重新打开面板观察实际保留结果。

## 待执行的同源出口

私有请求文件的读写在进程内跨 Activity owner 串行；旧 owner 的自动清理必须匹配自己提交的 revision ID，避免旋转后的新请求被迟到的清理删除。显式“结束确认”才允许丢弃当前待确认请求。

CBZ 在冻结 SDK 中没有 text provider，不能通过公开 fixed anchor 接口产生真实捕获；本面板明确报告不支持，不以空白捕获替代。空白 PDF 有公开空文本快照，其真实点捕获单独验证。固定 selector 中的 NUL 会原长传给 SDK；产品 wire 的现有限制仍由 G03/codec 明确拒绝，不截断后保存。

新测试包含 14 组首进程检查、1 组真实提交后杀进程再精确重试、1 组再次重开检查。全部仍待 Actions 首轮运行；源码中写出的断言不算通过证据。

保留原件导出、18捕获/原宿主17+2/DAV、正式16、搜索15及导航18，随后执行新阅读记录真实UI正反例。覆盖SDK capture→G03→G04→独立FOUND、三种mode及v2字节、非SAFE状态、旧selector/body编辑、delete/明确restore、过期观察head、取消/生命周期与提交响应不确定后的进程重开exact-retry；核对SDK notes/旧progress与产品修订的写入边界及Debug/Release provider/依赖材料。

真机、TalkBack语音、产品性能和六平台完整产品仍单列。
