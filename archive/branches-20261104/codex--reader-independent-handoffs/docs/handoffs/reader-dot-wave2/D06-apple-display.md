# D06：Apple阅读场景常亮与临时亮度

先读[共同约束](README.md)。固定起点a826a65c9c66e43620eff61b49cb79f941a3c953；唯一分支 **codex/dot-reader-apple-display**。

## 目标

独立原生组件与macOS/iPhone/iPad probe，提供阅读场景显示休眠抑制；iOS可选临时UIScreen亮度，macOS若无同等受支持公共API应明确UNSUPPORTED，不用私有API。不得改examples/apple、共享Apple构建器或root的3.41主题/阅读记录候选。

## 合同与行为

- iOS主线程/scene-scoped lease；仅在目标scene可见active且宿主显式开启时拥有idleTimer/亮度请求。明确应用级isIdleTimerDisabled和屏幕级brightness并非单窗口属性，采用进程内引用计数或独占lease，不能用一个窗口关闭另一个窗口的请求。
- scene失活/断连、close、错误和取消释放自己持有的请求。保存接管前状态；对外部亮度修改先核当前是否仍为自己设置值，不能盲目恢复覆盖用户控制中心/其它owner的后续修改。外接屏幕/多scene冲突处理写清。
- macOS使用公开IOPM显示休眠assertion，持有并释放自己的assertion ID；前后台策略由宿主显式输入，不擅自阻止系统睡眠。无长驻服务、无屏幕录制或辅助功能授权需求。
- 拒绝坏数值/NaN/Inf、错线程、已关闭/错误scene。无偏好持久化、产品schema、SDK或主题变化，原生系统失败返回实际UNAVAILABLE/IO与固定非敏感错误。

## 范围

extras/apple-reader-display/**；tests/reader_apple_display/**；.github/workflows/reader-apple-display.yml；docs/READER-APPLE-DISPLAY.md；docs/validation/reader-apple-display.json。

Actions macOS真实assertion持有/释放查询、独立原生消费者；iPhone/iPad模拟器真实app状态、窗口/scene生命周期、双lease、错线程、外部属性变化和真实终止。另行编译iphoneos分发目标。模拟器不支持某属性时如实未覆盖，不能用mock授予物理背光或实际休眠效果；不发布签名包。
