# Android 原生同步会话接续

受测源码 `506fd1ee70a196ebb1beeba7a33b13b4c953a8c1`，
[运行 40079492588](https://github.com/NoGod3524/EXReader/actions/runs/40079492588) attempt 1，Android 作业 `120829870812` 全部通过。

本轮在 API34 default x86_64 模拟器中执行：SDK 公开原件导出 8 项、实际 TLS DAV 会话 11 组、原宿主 17 项 native owner 检查与 2 个真实进程中断恢复边界、既有 Android DAV 91 项及重启 4 项。
四份 Debug/Release 产品共享库的实际链接 map、未剥离符号、打包 build ID 与动态依赖均通过检查；SDK SQLite 与产品 SQLite 保持隔离。产品 map 排除 SDK vendor SQLite archive，符号表分别检查 SDK API 和产品 SQLite 的唯一性。

真实往返涵盖公开 SDK EPUB 原件导出、条件发布、服务端已提交后 force-stop、412 重试后 GET 核验、远端安全唯一 metadata 显式投影、已核验原件导入和本机映射、并发 heads 保留、账号及根地址隔离、401 后重建会话、取消/重试/两步关闭。网络 worker 不借用 SDK 文档、pager 或 source。

工件 `12554443962`，44,473,586 字节，ZIP SHA-256 `c64fef521eb7a09dac6cb6cdf6dafce309dc3adf09673d56792955142cf8ec53`，到期 `2027-01-22T08:48:46Z`。API 元数据与实际上传日志一致；完整报告身份见 [验收记录](validation/reader-session-android.json)。

前轮 `ca318e79` / `40072691890` 因原宿主测试 APK 未登记 ProductOwnerTest runner 而拒绝。新轮显式选择该 runner，并在命令失败时先保存原始 instrumentation 输出。失败运行与工件保留。

这份记录只授予 Android 原生会话、原书及产品 metadata 往返范围。18 个真实捕获跨 DAV 的阅读状态互通、宿主同步 UI、安全凭据接入和真机均待后续验收。
