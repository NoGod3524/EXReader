# 六端运行时验证命令

源码快照为 `ed252fb6e483192ec0553a936e341f49c144b824`，开始时等于 `origin/main`。新增验证代码只使用公开 C API；Android 另外调用原有 `EXReader.version()` JNI。产品源码、头文件、示例和 workflow 均未改动。

## 统一五项的定义

同一份 `tools/abi/prepare_smoke.py` 生成的 EPUB 与固定字体，布局为 360×480、18px。

1. **加载**：Windows/Linux/macOS consumer 显式加载目标库并调用 `exr_version()`；Android 由 `System.loadLibrary` 加载打包的 `.so`，调用原有 JNI version 和 C version。
2. **打开**：`exr_publication_open`、加载第一章、建立分页，页数 > 0。
3. **渲染**：实际 RGBA 页，暗像素数 > 0 且不是整页暗色；对可见像素计算 FNV-1a 64 位校验和，保存 PNG。
4. **搜索**：通过引擎搜索 `deliveryneedle`，要求至少一个命中，并记录 part、UTF-8 offset、length。
5. **标注**：引擎创建/导出高亮锚点到 W3C JSON sidecar；终止 create 进程后，由新进程重新打开 EPUB、读取 JSON、解析锚点，核对文本范围、页码、x、baseline 和原页像素校验和，再按引擎 glyph 坐标绘制高亮。

这是 SDK 与最小宿主验证。五项中“标注”使用可移植 JSON 持久化，不把结果扩展为完整产品菜单或 SQLite 书库 UI 验收。

## Windows

真实 Windows 11 x86_64，MinGW GCC 16.2。配置采用仓库已有回归配置：保留 audio/library/text index/PDF/PDF edit/JPX，关闭 AAC、ICC、MP3、PDF crypto、WebP、TIFF、AVIF 和 JNI。完整参数及本地依赖路径在 [windows-main-configure.txt](../../evidence/platforms2-20261109/windows-main-configure.txt)。

```powershell
cmake --build evidence/platforms2-20261109/work/windows-main --parallel 6
ctest --test-dir evidence/platforms2-20261109/work/windows-main --output-on-failure -j 6
python -B tools/platforms/run_native.py --library evidence/platforms2-20261109/work/windows-main/libexreader.dll --smoke evidence/platforms2-20261109/work/smoke --out evidence/platforms2-20261109/windows-new-run
```

实际结果：`PASS platform checks=5/5`；`100% tests passed out of 234`。复用的 `run_native.py` 还执行故意改错标注页码的负向控制，必须返回非零。

19 本逐页回归使用 `tools/regress/run_realbooks.py`，原清单、`tools/regress/layout.json` 和 `C:/Windows/Fonts/NotoSerifSC-VF.ttf`（SHA-256 `a4aed9985a5916fbf6690456f8732a9fccd517938e353165d4142b4f11a39280`）。完整命令及输出见 [windows-realbooks-original-font.txt](../../evidence/platforms2-20261109/windows-realbooks-original-font.txt)，比较结果见 [books.diff.json](../../evidence/platforms2-20261109/books.diff.json)。

## Linux

本机 `wsl -l -v` 返回未安装子系统，Docker 未安装。实际采用 **QEMU 11.1 / WHPX → Linux 6.12.115 → Debian 12 glibc 2.36 chroot**；以 `uid=1000(probe)` 构建和执行，GCC 12.2、CMake 3.25.1。该 chroot 共享 QEMU 中真实 Linux 内核，不是在 Windows 上解析 ELF 冒充运行。

启动参数见 [linux-boot-command.txt](../../evidence/platforms2-20261109/linux-boot-command.txt)，内核、发行版、用户及动态依赖输出见 [linux-runtime-environment.txt](../../evidence/platforms2-20261109/linux-runtime-environment.txt)。`P:` 仅是本任务 `evidence/platforms2-20261109/work` 的短路径映射；虚拟磁盘、SDK、下载和构建缓存均保存在该目录。

已下载的原 CI Linux 库先实际跑过一次，证据在 [linux-ci-artifact-runtime.txt](../../evidence/platforms2-20261109/linux-ci-artifact-runtime.txt)。随后对上述 main 快照执行默认功能配置（仅关 JNI 和默认不启用的 AAC）：

```sh
cmake -S . -B out -G Ninja -DCMAKE_BUILD_TYPE=Release -DEXR_BUILD_JNI=OFF -DEXR_ENABLE_AAC=OFF && cmake --build out --parallel 4
ctest --test-dir out --output-on-failure --no-tests=error -j 4
python3 -B tools/platforms/run_native.py --library out/libexreader.so --smoke smoke --out evidence/platforms2-20261109/linux-new-run
```

`smoke` 为同一份固定测试 EPUB/字体；没有现成目录时省略 `--smoke smoke`，脚本自行调用原有准备工具。

Alpine/musl/GCC 14 的尝试保留在 `linux-build.txt`、`linux-posix-build.txt`：先遇到 `tools/convert_report.c` 的 `gmtime_r` 声明问题，补 POSIX 编译宏后又遇到 `tools/convert.c:1038` 的 `unsigned long long *` / `uint64_t *` 类型诊断。没有修改这些产品工具，也没有降低诊断级别；最终使用 Debian/GCC 12 的独立构建。不能将 Debian 通过写成 Alpine 默认构建通过。

## Android

实际环境为 AOSP Android 11/API30 x86_64 模拟器，WHPX 硬件加速；NDK `27.2.12479018`，native min API24，Build Tools `35.0.0`，JDK21。完整构建参数在 [android-configure.txt](../../evidence/platforms2-20261109/android-configure.txt)，`llvm-readelf` 的 ABI、依赖和导出表在 [android-readelf.txt](../../evidence/platforms2-20261109/android-readelf.txt)。

SDK/AVD 准备好后，三个步骤即可复跑（按本地安装位置设置 `ANDROID_HOME`、`ANDROID_NDK_HOME`）：

```sh
emulator -avd exreader30 -no-window -no-audio -no-boot-anim -no-snapshot -gpu swiftshader_indirect -memory 2048 -cores 2
python tools/platforms/build_apk.py --sdk "$ANDROID_HOME" --ndk "$ANDROID_NDK_HOME" --build evidence/platforms2-20261109/work/android-build --smoke evidence/platforms2-20261109/work/smoke --out evidence/platforms2-20261109/work/apk-new
python tools/platforms/run_android.py --serial emulator-5554 --apk evidence/platforms2-20261109/work/apk-new/platform-probe.apk --out evidence/platforms2-20261109/android-new-run
```

第一条在单独终端保持运行，等 `adb shell getprop sys.boot_completed` 为 `1`。第二条需要先按 `android-configure.txt` 编译 `.so`。第三条会安装 APK，只清理专用测试 app 的数据，通过 `adb shell am start` 触发 JNI；两次进程之间 `am force-stop`，最后通过 `run-as` 收集文件。

实际两个 PID 为 **2429、2477**，原有 JNI 与 C API 都返回 `3.42.0`。日志及每条 ADB 命令在 [android/result.json](../../evidence/platforms2-20261109/android/result.json) 和 [android/logcat.txt](../../evidence/platforms2-20261109/android/logcat.txt)。本轮 ARM64 既有产物只做静态校验，不能把 x86_64 模拟器结果当作 ARM64 已执行。

最小 APK 与 AAR 内的引擎/JNI 字节 SHA-256 和本轮独立 `.so` 相同。AAR 使用原有 `tools/abi/package_android.py` 打包。Build Tools 34 的 D8 与本机 JDK21 组合曾发生内部 NPE，升级到 35 后构建、v2/v3 签名核验和安装通过，失败日志保留。

## Apple 与 WASM

macOS/iOS 的 artifact 下载入口及各自三条复验命令见 [APPLE-VERIFICATION.md](APPLE-VERIFICATION.md)。

WASM **不支持**：仓库没有 Emscripten 目标、JS 绑定、浏览器宿主与文件/存储/音频适配。本轮没有移植或 `.wasm` 产物，五项均为 N/A；现有原因见 [wasm-ACCEPTANCE.md](wasm-ACCEPTANCE.md)。
