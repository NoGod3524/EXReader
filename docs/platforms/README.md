# 六端交付矩阵 — 2026-11-08

本轮新增交付元数据、ABI 工具和可运行验收探针；引擎不变。Windows 功能探针已跑通，其他原生端保留 CI 构建证据和未执行的装机清单。WASM 不支持。

## 一条命令看全貌

```sh
python tools/abi/platform_status.py
python tools/abi/platform_status.py --root /path/to/delivery
python tools/abi/platform_status.py --json
```

Python 3.11+，仅标准库；无需安装 PE/ELF/Mach-O 工具。默认产物根目录为仓库同级 `tmp/platform-delivery-20261108/delivery`，也可用 `EXREADER_PLATFORM_ARTIFACTS` 指定。默认矩阵重新读取实际文件、算 SHA/符号；缺失项不会继承历史通过状态。历史测量保存在 [artifacts.json](../../evidence/platforms-20261108/artifacts.json)。此命令是盘点，不把 pending 或 complete+extra 当作发布通过；文件损坏、SHA 漂移或已有核心库缺失入口返回非零。

## 实测产物

下表 SHA 为本轮已获取文件的历史测量；完整构建命令逐条保存在 [artifacts.json](../../evidence/platforms-20261108/artifacts.json)。所有二进制在仓库外，不提交 `.dll/.exe/.so/.dylib/.a/.aar`。静态库符号数为全局已定义入口，AAR/EXE 没有核心动态导出表。

| 平台/架构 | 文件 | 状态 | bytes | SHA-256 | 导出符号数 |
|---|---|---|---:|---|---:|
| Windows/x86_64 | `windows/x86_64/exreader.dll` | 已产出 | 6102526 | 49344b73f2a875b0f5d05cf9c1ca589a46295410290235600a7566cc3d65950f | 389 |
| Windows/x86_64 | `windows/x86_64/EXReader.exe` | 已产出 | 1272371 | 9e3fa3baa07245897334d0d3db2dc9709e58085fa08f14086ccb46aa144999b8 | 0 |
| Windows/x86_64 | `windows/x86_64/libexreader.dll` | 已产出 | 6102526 | 49344b73f2a875b0f5d05cf9c1ca589a46295410290235600a7566cc3d65950f | 389 |
| Android/arm64-v8a | `android/arm64-v8a/libexreader.so` | 已产出 | 35581040 | 4853cbbd81d3c51b63de3e5aa6c83f4cece58dd6f79bd39acb1aa9c3032adafa | 2800 |
| Android/arm64-v8a | `android/arm64-v8a/libexreader_jni.so` | 已产出 | 182248 | 7c48f1f2fc790962dea15d81d95bce20b80dae44a9710875888dd63295a21dbc | 38 |
| Android/arm64-v8a | `android/arm64-v8a/exreader-arm64-v8a.aar` | 已产出 | 12155275 | fd25507dff5fa52aabf60b924aa1c1bae7cc10c0c9fd7726cc8c92913001549e | N/A（内含核心 2800，JNI 38） |
| Android/x86_64 | `android/x86_64/libexreader.so` | 仅 CI 可产 | — | — | — |
| Android/x86_64 | `android/x86_64/exreader-x86_64.aar` | 仅 CI 可产 | — | — | — |
| macOS/arm64 | `macos/arm64/libexreader.dylib` | 已产出 | 8149888 | 5597c718986b20640f2144eb11cad7ce3104a6de188eb65cee0a72c850f9685d | 2799 |
| macOS/x86_64 | `macos/x86_64/libexreader.dylib` | 仅 CI 可产 | — | — | — |
| iOS/arm64-device | `ios/arm64-device/libexreader.a` | 仅 CI 可产 | — | — | — |
| iOS/arm64-device | `ios/arm64-device/libexreader.dylib` | 已产出（替代动态库） | 8053800 | 882a23f3a05cc9893062568e6d7df3d3cf03fc567bb4c772c0e4e9574f6b7719 | 2799 |
| iOS/arm64-simulator | `ios/arm64-simulator/libexreader.a` | 仅 CI 可产 | — | — | — |
| iOS/arm64-simulator | `ios/arm64-simulator/libexreader.dylib` | 已产出（替代动态库） | 8136288 | 320f6810c1caee0d8f34891b06b3f99e4b67a238e3e4a73c69982289c72bd151 | 2799 |
| Linux/x86_64 | `linux/x86_64/libexreader.so` | 已产出 | 10121688 | be2e9d6b675d92e3719f8149dfc5cac4552333385a0a3c1394f926765afa1d13 | 2799 |
| WASM/wasm32 | `无目标` | 当前无法产 | — | — | — |

Windows DLL **389** 个符号严格通过；Android/macOS/iOS/Linux 现有动态库公共入口 **389/389**，但还暴露内部/第三方符号（2,410；Android 2,411），严格同集合未通过。必须保留这一差异，不能用 `--allow-extra` 冒充严格通过。详见 [ABI.md](../ABI.md)。

| 缺项 | 当前原因和下一步 |
|---|---|
| Android x86_64 `.so` / AAR | 本机无 NDK；本轮 native CI 只归档 ARM64。需在 NDK runner 执行元数据中的 x86_64 命令并归档。 |
| macOS x86_64 dylib | 本机无 Apple SDK；macos-15 已下载库实际为 arm64。需 macOS runner 交叉到 x86_64，不能复制/改名 ARM64 库。 |
| iOS device / simulator `libexreader.a` | 现有 CI 上传组件 `.a` 和聚合 `.dylib`，未产聚合静态库。新增 `merge_ios.py` 使用 Apple libtool 合并；本轮尚未执行。 |
| Web/WASM | 当前无 Emscripten 构建、浏览器桥与验收环境；本轮不移植。 |

这些缺项列为“仅 CI 可产”表示具备构建/聚合方法，并不表示现有 workflow 已自动执行这些新增步骤；本轮按约束未修改 `.github/`。无需为盘点修改或取消任何 workflow。

## 取回 CI 产物

CI 使用已成功的 native run [42474080320](https://github.com/NoGod3524/EXReader/actions/runs/42474080320)；其源 Git tree 与本轮基线完全一致。完整 stage 含头文件、私有依赖归档、CMake 包和许可证，须一起保存。

```sh
gh run download 42474080320 -R NoGod3524/EXReader \
  -n EXReader-C-Android-arm64 -n EXReader-C-macOS \
  -n EXReader-C-iOS-iPadOS-arm64 -n EXReader-C-Linux -D downloads
```

Android AAR 可在任意装有 JDK 的主机重新打包，不需要 NDK；库来自上述 CI，Java 源来自同一 tree：

```sh
python tools/abi/package_android.py --sdk downloads/EXReader-C-Android-arm64 \
  --abi arm64-v8a --output delivery/android/arm64-v8a/exreader-arm64-v8a.aar
```

本轮 JDK 21.0.13，`javac --release 8`，打包包含 32 个 Java class、38 个 JNI native 入口、两份共享库和 SDK 许可证。重复构建字节一致；它不是 APK，装机需接入应用。

## 构建命令

以下为干净构建入口；复现时保留 CMakeCache、工具链版本和源 SHA。版本/编译器差异可能改变二进制 SHA，必须重新测量。Windows 本轮复用了已有相同源输入的 Release SDK/EXE，并重新安装 SDK、编译本轮 consumer 和复跑测试；没有声称执行了下面的全量引擎重编。其原始配置见 [build-config.txt](../ui/evidence/annotations/build-config.txt)。

### Windows / x86_64

```powershell
New-Item -ItemType Directory -Force delivery/windows/x86_64 | Out-Null
cmake -S . -B build/platform-windows -G Ninja -DCMAKE_BUILD_TYPE=Release -DEXR_BUILD_JNI=OFF -DEXR_BUILD_FUZZ=OFF -DEXR_ENABLE_AAC=OFF -DEXR_ENABLE_ICC=OFF -DEXR_ENABLE_MP3=OFF -DEXR_ENABLE_PDF_CRYPTO=OFF -DEXR_ENABLE_IMAGE_WEBP=OFF -DEXR_ENABLE_IMAGE_TIFF=OFF -DEXR_ENABLE_IMAGE_AVIF=OFF
cmake --build build/platform-windows --parallel 6
cmake --install build/platform-windows --prefix stage/windows
pwsh -File docs/ui/acceptance/build_real_exe.ps1 -SdkBuild build/platform-windows -Out build/platform-windows-host
Copy-Item build/platform-windows-host/EXReader-fix.exe delivery/windows/x86_64/EXReader.exe
Copy-Item build/platform-windows/libexreader.dll delivery/windows/x86_64/exreader.dll
Copy-Item build/platform-windows/libexreader.dll delivery/windows/x86_64/libexreader.dll
```

### Android / arm64-v8a

```sh
cmake -S . -B build/android-arm64 -DCMAKE_TOOLCHAIN_FILE="$ANDROID_NDK_HOME/build/cmake/android.toolchain.cmake" -DANDROID_ABI=arm64-v8a -DANDROID_PLATFORM=android-24 -DCMAKE_BUILD_TYPE=Release -DEXR_BUILD_TOOLS=OFF -DEXR_BUILD_TESTS=OFF -DEXR_ENABLE_AAC=OFF
cmake --build build/android-arm64 --parallel 4
cmake --install build/android-arm64 --prefix stage/android-arm64
python tools/abi/package_android.py --sdk stage/android-arm64 --abi arm64-v8a --output delivery/android/arm64-v8a/exreader-arm64-v8a.aar
```

### Android / x86_64

```sh
cmake -S . -B build/android-x86_64 -DCMAKE_TOOLCHAIN_FILE="$ANDROID_NDK_HOME/build/cmake/android.toolchain.cmake" -DANDROID_ABI=x86_64 -DANDROID_PLATFORM=android-24 -DCMAKE_BUILD_TYPE=Release -DEXR_BUILD_TOOLS=OFF -DEXR_BUILD_TESTS=OFF -DEXR_ENABLE_AAC=OFF
cmake --build build/android-x86_64 --parallel 4
cmake --install build/android-x86_64 --prefix stage/android-x86_64
python tools/abi/package_android.py --sdk stage/android-x86_64 --abi x86_64 --output delivery/android/x86_64/exreader-x86_64.aar
```

### macOS / arm64

```sh
cmake -S . -B build/macos-arm64 -DCMAKE_OSX_ARCHITECTURES=arm64 -DCMAKE_BUILD_TYPE=Release -DEXR_ENABLE_AAC=OFF
cmake --build build/macos-arm64 --parallel 4
cmake --install build/macos-arm64 --prefix stage/macos-arm64
```

### macOS / x86_64

```sh
cmake -S . -B build/macos-x86_64 -DCMAKE_OSX_ARCHITECTURES=x86_64 -DCMAKE_BUILD_TYPE=Release -DEXR_ENABLE_AAC=OFF
cmake --build build/macos-x86_64 --parallel 4
cmake --install build/macos-x86_64 --prefix stage/macos-x86_64
```

### iOS / arm64-device

```sh
cmake -S . -B build/iphoneos -DCMAKE_SYSTEM_NAME=iOS -DCMAKE_OSX_SYSROOT=iphoneos -DCMAKE_OSX_ARCHITECTURES=arm64 -DCMAKE_OSX_DEPLOYMENT_TARGET=14.0 -DCMAKE_BUILD_TYPE=Release -DEXR_BUILD_TOOLS=OFF -DEXR_BUILD_TESTS=OFF -DCMAKE_XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED=NO -DEXR_ENABLE_AAC=OFF
cmake --build build/iphoneos --parallel 4
cmake --install build/iphoneos --prefix stage/iphoneos
python tools/abi/merge_ios.py --sdk stage/iphoneos --output delivery/ios/arm64-device/libexreader.a
```

### iOS / arm64-simulator

```sh
cmake -S . -B build/iphonesimulator -DCMAKE_SYSTEM_NAME=iOS -DCMAKE_OSX_SYSROOT=iphonesimulator -DCMAKE_OSX_ARCHITECTURES=arm64 -DCMAKE_OSX_DEPLOYMENT_TARGET=14.0 -DCMAKE_BUILD_TYPE=Release -DEXR_BUILD_TOOLS=OFF -DEXR_BUILD_TESTS=OFF -DCMAKE_XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED=NO -DEXR_ENABLE_AAC=OFF
cmake --build build/iphonesimulator --parallel 4
cmake --install build/iphonesimulator --prefix stage/iphonesimulator
python tools/abi/merge_ios.py --sdk stage/iphonesimulator --output delivery/ios/arm64-simulator/libexreader.a
```

### Linux / x86_64

```sh
cmake -S . -B build/linux -DCMAKE_BUILD_TYPE=Release -DEXR_ENABLE_AAC=OFF
cmake --build build/linux --parallel 4
cmake --install build/linux --prefix stage/linux
```

## 六份验收清单

- [Windows](windows-ACCEPTANCE.md)：DLL/宿主布局、CMake consumer、实际 5/5 探针记录。
- [Android](android-ACCEPTANCE.md)：AAR 接入、JNI 加载日志、NDK consumer、adb 推送/运行/回收。
- [macOS](macos-ACCEPTANCE.md)：架构确认、dyld 路径、五项探针与原生 bundle。
- [iOS](ios-ACCEPTANCE.md)：device/simulator 分别聚合 `.a`，UIKit 验收 app、Simulator container、真机签名/安装路径。
- [Linux](linux-ACCEPTANCE.md)：ldd、进程级库路径、无显示服务器探针与 GTK 限制。
- [WASM](wasm-ACCEPTANCE.md)：不支持原因、可执行支持状态检查与五项 N/A 判定。

五项为打开 EPUB、连续渲染 20 页、搜索 `deliveryneedle`、18→24 字号、高亮标注落盘/恢复/绘制。它们有明确日志/返回值/输出图像；此 SDK 级探针不代替各产品原生交互验收。新增 iOS app/聚合脚本等待 Apple runner；其余非 Windows 运行同样待设备/runner。

## 本轮验证

Windows 核心符号 389/389 严格通过；五项探针 **5/5**；ctest **211/211**；19 本真书 **11,484 页 / 8,648,640 字形**，页数、字形数、逐页像素哈希变化均 **0**。跨格式解析器拒绝缺失入口、多余入口（严格模式）、损坏文件以及任一 fat 切片不匹配；Linux GNU nm 读数独立匹配。证据索引见 [evidence README](../../evidence/platforms-20261108/README.md)。
