# Android 验收

当前：ARM64 `libexreader.so`、JNI `.so`、包含 Java/JNI 的 AAR 已产出；核心 ABI 389/389，另有 2,411 个额外导出，严格同集合未通过。x86_64 **待 CI 产物**；本机无 Android NDK/adb/设备，以下运行步骤尚未执行。

## AAR 接入

AAR 是应用依赖，不能直接 `adb install`。将 `exreader-arm64-v8a.aar` 放进 Android 应用 `app/libs/`，Gradle Kotlin DSL：

```kotlin
dependencies { implementation(files("libs/exreader-arm64-v8a.aar")) }
// Activity 中验证 Java -> JNI -> 核心库加载：
// android.util.Log.i("EXReaderABI", org.exreader.EXReader.version())
```

AAR minSdk=24，仅 arm64-v8a。加载判定：`adb logcat -d -s EXReaderABI:I` 出现 `3.42.0` 且没有 `UnsatisfiedLinkError`。JNI 入口不属于 389 个核心 C 入口；当前 Java 桥未覆盖全部搜索/标注 API，五项验收直接调用 C SDK。

## NDK 探针安装与运行（有 SDK 的主机，Bash）

先解压完整 `EXReader-C-Android-arm64` SDK，保留 include/lib/CMake 元数据。NDK、adb、可访问的 API24+ ARM64 设备必需；x86_64 模拟器必须改用匹配 x86_64 SDK 和 `-DANDROID_ABI=x86_64`，不能拿 ARM64 产物冒充。

```sh
set -e
export SDK="$PWD/downloads/EXReader-C-Android-arm64"
export ANDROID_NDK_HOME="$ANDROID_HOME/ndk/27.0.12077973"
python tools/abi/check_exports.py "$SDK/lib/libexreader.so" --allow-extra
python tools/abi/prepare_smoke.py build/smoke
cmake -S tools/abi -B build/probe-android -G Ninja \
  -DCMAKE_TOOLCHAIN_FILE="$ANDROID_NDK_HOME/build/cmake/android.toolchain.cmake" \
  -DANDROID_ABI=arm64-v8a -DANDROID_PLATFORM=android-24 \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_FIND_ROOT_PATH_MODE_PACKAGE=BOTH -DEXR_SDK="$SDK"
cmake --build build/probe-android --parallel 4
adb devices
adb shell getprop ro.product.cpu.abilist
adb shell 'mkdir -p /data/local/tmp/exreader/out'
adb push build/probe-android/exreader-acceptance "$SDK/lib/libexreader.so" \
  build/smoke/smoke.epub build/smoke/font.otf /data/local/tmp/exreader/
adb shell 'cd /data/local/tmp/exreader && chmod 755 exreader-acceptance && LD_LIBRARY_PATH=. ./exreader-acceptance smoke.epub font.otf out > acceptance.log 2>&1; code=$?; cat acceptance.log; exit "$code"'
adb pull /data/local/tmp/exreader/out build/android-acceptance
adb pull /data/local/tmp/exreader/acceptance.log build/android-acceptance/acceptance.log
```

失败时也单独执行最后两条 `adb pull` 留证。JNI AAR 接入是另外一项装机检查，不能由 C 探针通过自动推定。若需在已有宿主内交互，使用 `examples/android` 的独立构建说明；该宿主 Gradle 当前固定 x86_64，不能在本轮禁止改 examples 的边界内直接打成 ARM64 APK。

## 五项最小功能验收

以下五项均由同一次 `exreader-acceptance` 执行；任何条件不满足返回非零。PNG 是实际引擎渲染产物，不是界面示意图。各端使用相同 EPUB 和固定字体；探针验证 SDK 功能，原生阅读器的触控、菜单、无障碍和平台持久化仍需另做装机验收。

1. [ ] **打开一本书**：`acceptance.log` 必须出现 `PASS open status=0 pages=`，页数至少 20；打开 `page-01.png` 可见英文正文。这里使用生成的一章 EPUB，避免封面/版权页不足 20 页影响验证；19 本真书属于独立回归。
2. [ ] **连续翻 20 页**：必须出现 `PASS turn status=0 rendered=20 last=page-20.png`；`page-01.png` 至 `page-20.png` 共 20 个文件，均可打开。它验证连续页渲染和读取；触控翻页与应用帧率不在此探针范围内。
3. [ ] **搜索一个词**：查询 `deliveryneedle`，必须出现 `PASS search status=0 found=1 part=0 offset=0 length=14`；这是 `exr_publication_search` 的实际返回值，不是用字符串查找模拟。
4. [ ] **修改字号**：必须出现 `PASS fontsize status=0 from=18 to=24 pages_before=... pages_after=...`，after 大于 before；`font-24.png` 字号大于 `page-01.png`，首页结束偏移减少。探针会同时断言这些值。
5. [ ] **添加一个高亮**：必须出现 `PASS highlight status=0 stored=1 resolved=FOUND changed_pixels=` 且值大于 0；`highlight.json` 为导出的 W3C 标注，探针写入、关闭、重新读入并解析；锚点恢复到相同 UTF-8 范围。`highlight.png` 的第一个 `deliveryneedle` 有黄色背景。绘制由参考宿主按引擎字形坐标完成，不能据此宣称产品菜单已验收。

最后必须出现 `PASS acceptance checks=5`。保留完整日志、22 张 PNG（20 页 + 字号 + 高亮）、标注 JSON、设备/模拟器型号、OS 版本、实际库 SHA-256 和命令；失败时保留输出，不能把本页勾选项当成已通过记录。

## 已知限制

- AAR 的压缩结构、Java 类、核心符号已检查，尚无 Android 上实际加载记录；NDK 取自 CI 的库不能在 Windows 进程加载。
- ARM64 CI 产物使用 API24，动态依赖为系统 `libOpenSLES.so/libm.so/libdl.so/libc.so`；使用已有构建时仍应保存目标设备 loader 日志。
- x86_64 构建/AAR 命令已列入 [artifacts.json](../../evidence/platforms-20261108/artifacts.json)，当前 native CI 只归档 ARM64；不得把“可编译”填成“已归档”。
- 不在此清单中宣称触屏菜单、系统文档选择器、旋转或字体安装已经通过。
