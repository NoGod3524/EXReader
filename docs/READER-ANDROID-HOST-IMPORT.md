# Android 宿主导入入口

固定共同起点 `e4356a6e13223469fdf3b2f3d5171a6e99ab10a6`，普通合并 J04 最终 `e4f20df783872dd536f40a7431b200352aa2da17` 后接线。SDK 3.40.0 / ABI 1、产品 schema 1 保持原样。

## 接线

真实宿主 `MainActivity` 接收 content VIEW、SEND、SEND_MULTIPLE；Import 按钮打开系统 ACTION_OPEN_DOCUMENT，允许多选。所有入口统一使用 J04 的私有 staging，不在 UI 线程查询或复制 Provider。应用级 `ImportController` 保留 staging、票据与 Ready leases，Activity 旋转只更换 SDK owner 附着对象。

Ready 请求交给现有单一 host worker 和 BookStore；不使用 J04 示例中的第二个 NativeBridge/SDK 连接。共享导入路径依次：复制、SHA/长度核对、稳定 `files/books/<sha>.<format>` 原件、SDK import、公开 SDK source 回读、原 prefs publication barrier、产品 `finalizeImport`，完成后才释放 staging lease。已存在私有原件先核对实际字节，不能仅凭文件名复用。

生命周期取消在旧 worker 完成回报后把 Ready 请求交给新 owner；旧 Activity 的 UI 过滤器不会吞掉这个回报。用户明确取消则撤销未发布 SDK 插入，清理本次拥有的稳定副本和对应 lease。产品映射失败保留 Ready 与已发布原件；Refresh 或重新附着 owner 可重试。

进程终止后，J04 清理未发布临时文件；未完成 URI 复制需要真实重投，不能恢复失效 URI grant。已发布 Ready 使用私有字节恢复，SDK 精确去重后补齐路径和产品映射。产品键仍为格式与原件散列。

宿主启动在原有 IMPORT_LOCK 下清理自己尚未完成的 `books/import-<数字>.part`；不触碰已发布 SHA 原件或其他文件。新 owner 先等旧 Activity 的 SDK 导入补偿完成，避免删除活跃复制。

## 上限

当前宿主所有阅读输入仍限制 32 MiB。J04 对 EPUB/PDF/CBZ 的 128 MiB 仅为暂存上限，宿主在 SDK 导入前明确拒绝超过 32 MiB 的书。没有扩大整文件读入内存的上限。

Provider 的同步 Binder query/getType/open 阶段仍没有内部超时；复制描述符打开后的取消/无进展规则沿用 J04。实际第三方云盘、真机、TalkBack 语音、性能与完整产品不在本次验收范围。

## 云端验收

当前尚未验收。新工作流在同一源码和同一个宿主 APK 上运行旧 Host16/Search15/Navigation18/Reading16/Preferences17/CBZ10/Pan8，共 100 项，再运行新入口 19 项。

新增套件使用独立真实 DocumentsProvider、外部授予的 VIEW/SEND/MULTIPLE、真实系统 DocumentsUI、实际旋转、用户取消、Provider 错误、小报长度与 33 MiB 暂存上限负例。另在复制中、稳定原件副本尚未完成、Ready 发布后和 host 路径 publication 后保持真实边界，由 Actions 外部终止活 PID，再在新 PID 上恢复/重投。

严格汇总先认证本 run/attempt 的 producer job 与原 ZIP digest、大小、有效期，再读取八组报告。任何一组未通过，都不授予本宿主接线。
