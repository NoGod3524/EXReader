# 已预载 SDK target 的补充审查

此前的四组合验收覆盖新进程的 EXACT 版本选择，未覆盖宿主已经加载另一个 SDK 前缀的
target 后再切换 EXReader_DIR。S15 的真实 3.40/3.41 预载复现已证明 EXACT 元数据不足。

本次仅修正可选字体库的 CMake 接口，原公共头、实现、SHA 实现及原测试保持固定。
源码构建及安装 Config 均核对 exr_core 的实际导入头、版本、归档和 SDK 组件/vendor
依赖闭包。窄 helper 原样复用 S15 的 EXReaderSdkTargetGuard.cmake，不修改 SDK 或已有 target。

每个既有系统/SDK 组合增加四个真实 CMake 进程：源码/安装入口各测试同前缀成功、
已预载外部前缀拒绝。外部前缀是同一真实 SDK 安装的完整复制；不是伪造一个不存在的包。
严格汇总重新认证日志字节和源码身份，并将每个成功位翻转后验证拒绝。

既有两轮 root 历史保留。本补充为该审查的第三轮，尚未启动；所有验证仅在 Actions。
先等待 S15 的共用 helper 云端验证，再发布本修正。不授宿主字体选择 UI 或产品性能。
