# H8：Windows 有界书库阅读首个 pilot

执行 [共同约束](reading-extra-index.md#全部包共同约束)及其平台开工信号。
准备期可立即阅读 B=`b529513b7e8e8992786f8c679c0ec6c92110b035`；正式实现必须从主代理
另行交付的固定 SDK SHA 新建 `handoff/reading-h8-windows`。当前没有这个冻结交付。

## 边界与接入点

拥有 `examples/reader.c`、`examples/windows/`、`tests/windows_host/`、
`tools/build_windows_host.py`、`tools/check_windows_host.py`、
`.github/workflows/wp13-windows.yml`、`docs/WP13-WINDOWS.md` 与本包证据。
参考 [实际函数地图](../R5-NATIVE-HOST-ADOPTION.md)中的 Windows 小节。
不改公共头、library/layout 引擎、共享 CMake、其他平台或数据库 schema。

1. `host_session/job_open` 接入 source→publication→part bounded pager，
   EPUB 有界导入使用冻结 SDK；其他重排格式保留明确快照上限。
2. `render_reflow`、hit-test、选文读取改为当页有限数据；借用 layout 不跨缓存逐出。
   不向需要 document 的旧函数传空指针。
3. `reflow_restore/save_progress/add_note/jump_selected_note/copy_quote`
   统一新章内位置契约；重启、字号改变与跨章恢复不能用页码猜测。
4. PDF/CBZ 采用现有 fixed-source 路径，保留 worker、取消和旧书/generation 守卫。
   旧记录迁移和歧义处理按冻结 SDK，不做平台私有数据库转换。

## 云端出口

保留原 Windows 自检及 UI/lifecycle 验收；新增多 part 双向跨章、可逐出长章、
换书/取消/关闭、字号后定位、进程重开、选文复制、标注增改删跳转、旧记录恢复。
观察原件读取、parse/page/checkpoint/bitmap 及进程峰值内存，分别报告，不凭页缓存宣布低内存。
每个新增检查必须证明实际进入 bounded 路径，全文回退不得算通过。

交付同源 run、逐例记录、程序/字体/夹具散列、工件及完整 SHA。
该 pilot 由主代理复核后作为其他平台示例；需要变更 SDK 时先回报，不能自行分叉契约。
准备期交付接入点与验收计划即可，正式 SDK 到位前不宣称完成。
