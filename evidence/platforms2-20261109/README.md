# 运行时证据索引

基线 `ed252fb6e483192ec0553a936e341f49c144b824`。日志由 `tools/platforms/record.py` 记录 UTC、工作目录、argv、完整输出、退出码，并追加根目录 `PLATFORMS2-OUT.txt`。构建缓存和大二进制位于被忽略的 `work/`；`P:` 映射到该目录。保留失败尝试，最终结论以以下成功记录为准。

| 验证 | 成功记录 |
|---|---|
| Windows main 动态加载及 5/5 + 错页码负向控制 | [windows-probe-gate.txt](windows-probe-gate.txt)、[windows-gated/result.json](windows-gated/result.json) |
| Windows 全量测试 | [windows-ctest.txt](windows-ctest.txt)：234/234 |
| 原 CI Linux `.so` 的实际运行 | [linux-ci-artifact-runtime.txt](linux-ci-artifact-runtime.txt)、[linux-ci/result.json](linux-ci/result.json) |
| 当前 main Linux 全功能构建 | [linux-debian-configure.txt](linux-debian-configure.txt)、[linux-debian-build.txt](linux-debian-build.txt) |
| 当前 main Linux 5/5 + 错页码负向控制 | [linux-current-runtime.txt](linux-current-runtime.txt)、[linux/result.json](linux/result.json) |
| Linux 全量测试最终结果 | [linux-test-font.txt](linux-test-font.txt)：234/234 |
| Linux 内核、glibc、编译器、uid 与依赖 | [linux-runtime-environment.txt](linux-runtime-environment.txt)、[linux-symbols.txt](linux-symbols.txt) |
| Android 当前 main 交叉构建 | [android-configure.txt](android-configure.txt)、[android-build.txt](android-build.txt)、[android-readelf.txt](android-readelf.txt) |
| Android APK/AAR | [android-apk-build35.txt](android-apk-build35.txt)、[android-aar.txt](android-aar.txt)、[包内库与独立库一致](android-package-parity.json) |
| Android 模拟器真实 JNI 5/5 | [android-runtime.txt](android-runtime.txt)、[android/logcat.txt](android/logcat.txt)、[android/result.json](android/result.json)、[模拟器画面](android/emulator.png) |
| Apple 静态校验与可下载 artifact | [apple-macho-headers.txt](apple-macho-headers.txt)、[ci-artifacts.json](ci-artifacts.json) |
| 所有产物的 SHA-256 与导出数 | [inventory.txt](inventory.txt)、[artifacts.json](artifacts.json)、[SHA256SUMS.txt](SHA256SUMS.txt) |
| 19 本逐页回归 | [windows-realbooks-original-font.txt](windows-realbooks-original-font.txt)、[books.diff.json](books.diff.json)、[books.json.gz](books.json.gz) |
| 跨平台像素/标注文件相等 | [cross-platform-pixels.json](cross-platform-pixels.json) |

五项的逐步日志、page/reopen/highlight PNG、落盘 JSON 与锚点坐标都在 `windows-gated/`、`linux/`、`linux-ci/`、`android/` 中。`windows/` 是首次同探针实测；`windows-gated/` 追加了负向控制。

## 失败尝试如何处理

- `windows-configure.txt`：PowerShell 将未引用的 `-D...=C:/...` 拆参，误配置了 OpenJPEG；改为引用参数，在新的 `windows-main` 目录正确构建。
- `windows-realbooks.txt`：第一次选用了另一字体，与基线不可比。找到 SHA-256 与旧记录完全一致的 NotoSerifSC-VF.ttf 后全量重跑，最终零差异；原失败记录仍在。
- `linux-bootstrap*.txt`：串口登录时序、网卡未 up、Windows 输出编码问题；已修正探针编排，成功环境记录独立保存。
- `linux-build.txt`、`linux-posix-build.txt`：Alpine/GCC 14 下原有转换工具的声明与类型诊断，未改产品文件。转为 Debian/GCC 12 独立构建成功。
- `linux-ctest.txt`：精简 Debian 未带 DejaVu，7 项测试无法打开系统字体；`linux-test-font.txt` 安装字体后 **全量** 234/234 通过。
- `android-sdk-list.txt`、`android-avd-create.txt`：SDK 长路径、空代理变量、非标准 cmdline-tools 路径导致的准备问题；短路径映射、进程环境修正及本任务 AVD 路径修正后模拟器实际启动。
- `android-apk-build.txt`：引擎还在链接时过早尝试打 APK；构建完成后再执行。
- `android-apk-build-complete.txt`：Build Tools 34 的 D8/JDK21 内部错误；改用 Build Tools 35 后完成打包、签名核验、安装和运行。

没有把失败日志删除、改写为成功，也没有借用其它平台的运行结果。Apple 操作脚本仅提供后续复验入口，本轮没有 Apple 运行证据。
