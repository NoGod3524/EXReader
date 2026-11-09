# 六端运行时验证矩阵 · 2026-11-09

**两端新增运行时通过：Linux、Android。** Windows 补齐当前 main 实测，合计三端 5/5。

本轮源码基线：`ed252fb6e483192ec0553a936e341f49c144b824`，开始时与 `origin/main` 一致。macOS/iOS 与旧 Linux/ARM64 Android artifact 来源为 `bd15cddb4d0928abde07c90e34b52f567a169d2d`，单独保留来源，不混作当前 main。

| 平台 | 实际执行方式 | 加载/version | 打开 EPUB | 非空白渲染 | 搜索 | 标注重开 | 结论 | 依据 |
|---|---|---|---|---|---|---|---|---|
| Windows x86_64 | 真实 Windows 11 / MinGW，新构建 main | PASS | PASS | PASS | PASS | PASS | **已跑通 5/5** | [运行日志](../../evidence/platforms2-20261109/windows-probe-gate.txt)、[结构化结果](../../evidence/platforms2-20261109/windows-gated/result.json) |
| Linux x86_64 | QEMU/WHPX 真实 Linux 内核 + Debian/glibc，非 root；旧 CI 库和新构建 main 分别执行 | PASS | PASS | PASS | PASS | PASS | **已跑通 5/5 · 新增** | [main 运行](../../evidence/platforms2-20261109/linux-current-runtime.txt)、[旧库运行](../../evidence/platforms2-20261109/linux-ci-artifact-runtime.txt)、[结构化结果](../../evidence/platforms2-20261109/linux/result.json) |
| Android x86_64 | AOSP API30 模拟器；安装最小 APK，ADB 触发原有 JNI 与 C 探针 | PASS | PASS | PASS | PASS | PASS | **已跑通 5/5 · 新增** | [运行日志](../../evidence/platforms2-20261109/android-runtime.txt)、[logcat](../../evidence/platforms2-20261109/android/logcat.txt)、[结构化结果](../../evidence/platforms2-20261109/android/result.json) |
| macOS arm64 | Windows 上检查实际 Mach-O，下载入口已核实 | 未跑 | 未跑 | 未跑 | 未跑 | 未跑 | **只能静态校验** | [Mach-O 检查](../../evidence/platforms2-20261109/apple-macho-headers.txt)、[artifact API 记录](../../evidence/platforms2-20261109/ci-artifacts.json)、[三条复验命令](APPLE-VERIFICATION.md#macos三条命令) |
| iOS arm64 device / simulator | 两种 dylib 分别检查平台标识与符号；本机无 Xcode/Simulator | 未跑 | 未跑 | 未跑 | 未跑 | 未跑 | **只能静态校验** | [Mach-O 检查](../../evidence/platforms2-20261109/apple-macho-headers.txt)、[三条 Simulator 复验命令](APPLE-VERIFICATION.md#ios-simulator三条命令) |
| WASM | 不支持；无 Emscripten 目标、JS/浏览器宿主及平台适配 | N/A | N/A | N/A | N/A | N/A | **无法验证（不支持）** | [既有原因](wasm-ACCEPTANCE.md)、[状态输出](../../evidence/platforms2-20261109/wasm-status.txt) |

Android **arm64-v8a 旧 `.so`/JNI/AAR 仍仅静态校验**。本轮运行时结论对应 x86_64，不扩展到 ARM64 真机。macOS Intel、iOS Intel simulator、WASM 没有可用产物，SHA-256 和导出数为 N/A。

## 五项实际返回值

Windows、Linux 两份库、Android 四次运行均得到：

| 条目 | 实测值 |
|---|---|
| 加载 | `version=3.42.0`、`abi=1`；Windows/Linux 显式加载成功；Android 原 JNI version 同样成功 |
| 打开 | `pages=215` |
| 渲染 | `360×480 RGBA`，`ink_pixels=20543`，`pixel_fnv1a64=08df71efa5a325a2` |
| 搜索 | `hits_at_least=1 part=0 offset=0 length=14` |
| 标注 | 新进程恢复 `part=0 start=0 end=14 page=0 x=24 baseline=45`，高亮改变 `2553` 个像素 |

Android create/reopen 的 PID 为 **2429 / 2477**。Windows/Linux 的 create/reopen 由两个独立 subprocess 执行；额外将已存页码改错后，负向测试返回非零。标注经公开 API 导出为 JSON sidecar，关闭进程后重新打开书籍、导入并定位；不是在同一个 document 指针上假装重开。

[跨平台字节核对](../../evidence/platforms2-20261109/cross-platform-pixels.json) 中，四次运行的原页 PNG、高亮 PNG、标注 JSON 均完全一致。原页 PNG SHA-256 为 `0ede4b1e517d2d86b0333f3c36a4e316aa15479d6cea95845c2c5062252958fa`，高亮 PNG 为 `2428bb1a1799f9c6b43cb0f1f37516636f51ac5fafe2a38435b94a675d984bae`。

## 全量测试与回归

- Windows：**234/234**，[完整输出](../../evidence/platforms2-20261109/windows-ctest.txt)。
- Linux：**234/234**，[安装缺失的 DejaVu 字体后全量重跑的输出](../../evidence/platforms2-20261109/linux-test-font.txt)。默认功能完整启用，仅关 JNI/AAC；未将此结果称为 sanitizer/覆盖率通过。
- 19 本真书：**19/19，11,426 页，8,648,571 字形**；与既有当前 main 集成基线相比，页数、字形、逐页像素哈希变化均 **0**。[比较结果](../../evidence/platforms2-20261109/books.diff.json)、[原始逐页记录](../../evidence/platforms2-20261109/books.json.gz)。
- `src/`、`include/`、`examples/`、`.github/`、根 CMake、既有测试和工具均零修改。新增内容仅位于约定三个目录，另有用户明确要求的根目录 `PLATFORMS2-OUT.txt`。

## 产物与复现

所有实际交付库、JNI、AAR、测试 APK 都重新计算 SHA-256 和实际导出数：见 [ARTIFACTS.md](ARTIFACTS.md)、[artifacts.json](../../evidence/platforms2-20261109/artifacts.json)、[SHA256SUMS.txt](../../evidence/platforms2-20261109/SHA256SUMS.txt)。AAR/APK 是 ZIP 容器，本身没有动态导出表；JSON 中逐个记录内含 `.so` 的导出数和哈希。

命令、工具链和环境故障处理见 [RUNTIME-COMMANDS.md](RUNTIME-COMMANDS.md)；完整成功/失败证据索引见 [README](../../evidence/platforms2-20261109/README.md)。
