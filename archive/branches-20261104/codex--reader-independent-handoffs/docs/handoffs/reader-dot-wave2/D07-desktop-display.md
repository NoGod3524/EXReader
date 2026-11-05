# D07：Windows/Linux阅读窗口常亮适配

先读[共同约束](README.md)。固定起点a826a65c9c66e43620eff61b49cb79f941a3c953；唯一分支 **codex/dot-reader-desktop-display**。

## 目标

独立可安装原生组件/C ABI和实际probe，给Windows与Linux宿主提供显示休眠抑制。Windows复用公开电源请求API，Linux复用GTK/桌面portal或已有Session D-Bus能力；不写全局电源配置、不做常驻守护、不改现有Windows/GTK宿主。

## 合同与行为

- 宿主提供当前原生窗口/显示句柄与active状态，明确lease创建、启用/撤销、observe、close。只有当前可见active阅读场景的请求生效；最小化/失活/关闭主动释放。不得把显示常亮升级成阻止所有系统睡眠。
- Windows每个实例只释放自己持有的真实power request句柄，正确处理线程/窗口销毁、两窗口/双lease、原生API失败及真实进程结束；不覆盖其他进程的电源请求。
- Linux真实桌面服务分配inhibitor/cookie/FD由本lease管理，异步回复绑定原窗口代际。取消/窗口销毁时到达的旧回复必须被释放，不可泄漏或重新启用；桌面服务缺失/拒绝/断线/重连明确UNAVAILABLE，不悄悄改用全局xset。若用GTK/GApplication必须沿原owner约定。
- 不用mock服务的成功回复冒充真实portal可用；可用故障fixture覆盖确定性竞态，但实际服务可用性另登记。无亮度控制（此包不跨平台发明同等能力）、无设置持久化/SDK/产品schema变化。

## 范围

extras/desktop-reader-display/**；tests/reader_desktop_display/**；.github/workflows/reader-desktop-display.yml；docs/READER-DESKTOP-DISPLAY.md；docs/validation/reader-desktop-display.json。

Actions Windows/Linux实际编译安装C/C++消费者，原生请求身份/释放、可见/最小化/切换窗口、双lease、取消/错线程/迟回调、服务断线、真实进程终止。Linux可在Xvfb+实际桌面会话运行，Wayland若未测则单列；远端runner的句柄成功不证明真实笔记本屏幕未熄灭或耗电通过。各平台按真实证据分别授予。
