# WebDAV Activity exit instrumentation projection（候选）

9a source `9a432d865a89c47201314ce54fb719e75d079676` 的共同 run `40235643574/1` 在原 Activity exit cleanup 断言失败。原 last-result 的传输与 native 清理成功，但没有 done/destroyed/worker异常证据，不能把本次失败直接归因生命周期竞态。

源码中 worker 的 finally 设置 done，Activity.onDestroy 异步设置 destroyed；原 while 仅等 done，随后同时检查两者。投影保持原 BackendProbe、ExitActivity、runner Git bytes，保留全部最终断言和原 10,000ms / 20ms poll，仅改为等待 done 与 destroyed 共同完成。新增状态只有 source/run/attempt、投影ID、阶段、两个布尔值、异常类名、单调时间和PID，无异常 message、URL、凭据或书库内容。

复用现有 navigation adapter 的身份/散列/写证据/APK证书 helper 和编译输入模式，不改原 owner/原断言或加新框架。原 WebDAV runner 先完整执行；wrapper 在其失败时只收集安全状态并返回原失败码，在其成功后核对实际安装 test APK、原两个设备报告和联合完成事件。额外 strict 在两个原判定与 navigation strict 均成功后认证同一已封存 ZIP，核对生成源码、实际 javac 输入、APK/证书和运行报告链。

root 新增精确路径只有 `tests/reader_android_webdav_exit/{adapter.py,init.gradle,README.md}`。共同 workflow 五处：prepare；原 WebDAV Gradle 加仅作用于 backend androidTest 的 init；原 audit 后 build；原 backend runner 入口改为调用原 runner 的 wrapper；最后附加 strict。common projection 对五处精确逆投影。

当前只交候选源码，没有本地或新增云端构建/测试；由 root 登记精确路径并统一共同 source 后验证。
