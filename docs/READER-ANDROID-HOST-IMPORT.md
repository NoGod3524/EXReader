# Android 宿主导入入口

固定共同起点 `e4356a6e13223469fdf3b2f3d5171a6e99ab10a6`，普通合并 J04 最终 `e4f20df783872dd536f40a7431b200352aa2da17` 后接线。SDK 3.40.0 / ABI 1、产品 schema 1 保持原样。

## 接线

真实宿主 `MainActivity` 接收 content VIEW、SEND、SEND_MULTIPLE；Import 按钮打开系统 ACTION_OPEN_DOCUMENT，允许多选。所有入口统一使用 J04 的私有 staging，不在 UI 线程查询或复制 Provider。应用级 `ImportController` 保留 staging、票据与 Ready leases，Activity 旋转只更换 SDK owner 附着对象。

Ready 请求交给现有单一 host worker 和 BookStore；不使用 J04 示例中的第二个 NativeBridge/SDK 连接。共享导入路径依次：复制、SHA/长度核对、稳定 `files/books/<sha>.<format>` 原件、SDK import、公开 SDK source 回读、原 prefs publication barrier、产品 `finalizeImport`，完成后才释放 staging lease。已存在私有原件先核对实际字节，不能仅凭文件名复用。

生命周期取消在旧 worker 完成回报后把 Ready 请求交给新 owner；旧 Activity 的 UI 过滤器不会吞掉这个回报。用户明确取消则撤销未发布 SDK 插入，清理本次拥有的稳定副本和对应 lease。产品映射失败保留 Ready 与已发布原件；Refresh 或重新附着 owner 可重试。

复制期间复用同一个 Import 按钮显示 `Cancel import`，旋转后从进程 controller 恢复可见状态；复制终止后恢复 Import。票据若刚好已提交、Ready 回调尚未送达，用户取消会释放那个 Ready lease，不撤回模块的 staging 提交，也不启动 SDK 导入。Ready 已交给 SDK worker 后，沿用原有 Cancel overlay 与 host publication 边界。

进程终止后，J04 清理未发布临时文件；未完成 URI 复制需要真实重投，不能恢复失效 URI grant。已发布 Ready 使用私有字节恢复，SDK 精确去重后补齐路径和产品映射。产品键仍为格式与原件散列。

宿主启动在原有 IMPORT_LOCK 下清理自己尚未完成的 `books/import-<数字>.part`；不触碰已发布 SHA 原件或其他文件。新 owner 先等旧 Activity 的 SDK 导入补偿完成，避免删除活跃复制。

## 上限

当前宿主所有阅读输入仍限制 32 MiB。J04 对 EPUB/PDF/CBZ 的 128 MiB 仅为暂存上限，宿主在 SDK 导入前明确拒绝超过 32 MiB 的书。没有扩大整文件读入内存的上限。

Provider 的同步 Binder query/getType/open 阶段仍没有内部超时；复制描述符打开后的取消/无进展规则沿用 J04。实际第三方云盘、真机、TalkBack 语音、性能与完整产品不在本次验收范围。

## 云端验收

通过。受测源码 `a7b2cb391c24a8ca0db3ff1472e3bfed84248be6`，[run 40173100103 / attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/40173100103) 的 android（`121107925953`）与 strict summary（`121111566027`）均 success。同一源码和同一个宿主 APK 先执行新入口 20 项，再执行完整旧 100 项，全部通过：

| 组 | 通过 |
| --- | ---: |
| Host session | 16 |
| Search | 15 |
| Navigation | 18 |
| Reading | 16 |
| Preferences | 17 |
| CBZ reading | 10 |
| Fixed pan | 8 |
| 新宿主导入 | 20 |
| 合计 | 120 |

新增套件使用独立真实 DocumentsProvider、外部授予的 VIEW/SEND/MULTIPLE、真实系统 DocumentsUI、实际旋转、用户取消、Provider 错误、小报长度与 33 MiB 暂存上限负例。另在复制中、稳定原件副本尚未完成、Ready 发布后和 host 路径 publication 后保持真实边界，由 Actions 外部终止活 PID，再在新 PID 上恢复/重投。

严格汇总先认证本 run/attempt 的 producer job 与原 ZIP digest、大小、有效期，再读取八组报告。任何一组未通过，都不授予本宿主接线。

本轮真实系统 picker 回调为 `request=1001/result=-1/data=true/flags=67/clips=0`；所选 TXT 的 70,000 原始字节从公开 SDK 回读并核对散列。正向导入夹具覆盖 EPUB、PDF、TXT；PDF 在 staging 释放后从实际书架打开并取得已绘制帧。

四处终止均在持有真实边界的活 PID 上由 Actions 外部执行 force-stop，九个阶段使用九个不同 PID。报告和完整 ready 元数据均经同目录 fsync + ATOMIC_MOVE 发布；ready 绑定 source/run/attempt/phase/pid、报告大小及 SHA-256，驱动验证完整内容后才终止。远程存在性协议实际为 present=0、absent=1。strict 再认证四份 ready 与九份 raw，及宿主、消费者、Provider 三个实际安装 APK 与上传字节一致。

宿主 APK SHA-256：`50394bd5c87f22918ad556037e61059f28b05c6fde3762a52ec6980124381a7f`。

| 工件 | ID | ZIP 字节 | SHA-256 | 到期 |
| --- | ---: | ---: | --- | --- |
| android | 12590858970 | 149,268,971 | `d439fe82ce0369dad8c77e9411e3dfe0e3a5a8cdb57f2d7841e3cdd7ebd4515d` | 2027-01-23T07:31:38Z |
| summary | 12591098215 | 1,045 | `664761a917ea272b1c19645e500557841ac55471571e4d35e475e6e394e526fc` | 2027-01-23T07:31:38Z |

早期失败及被替代的取消轮全部保留在 [验证记录](validation/reader-android-host-import.json)。它们包括 Activity 等待、按钮大小写、跨 UID/工具类型/实际列表滚动与文件激活，以及报告完成屏障错误；首次真实系统结果和后续恢复以本次完整 120 项为准。

原始报告：`build/android-host-import/ui/<phase>-raw-report.json`；四份 ready：同目录 `<kill-phase>-boundary-marker.json`。具名清单在 `tests/reader_android_host_import/run_ui.py` 的 `expected`，认证入口为 `tests/reader_android_host_import/check_evidence.py`，完整 producer 为 `.github/workflows/reader-android-host-import.yml` 的 `android` job。

共同合流轮复用 producer 时，需要用共同线所有权核对替换该分支的 `96623448..HEAD` 路径归属检查；构建、设备 120 项与认证不减。授予仍限 API34 default x86_64 模拟器，真实第三方云盘、真机、TalkBack 语音、性能与完整产品保持未授予。
