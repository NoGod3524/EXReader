# S04 Android 交付 APK 核验（契约）

固定实现起点 `0889f7d1e9a537c6c1b05456547e016b26e1cd85`，分支 `codex/reader-fw-s04`。只新增
`tests/reader_final_s04/`、`.github/workflows/reader-final-s04.yml`、`docs/reader-final-s04/`、`HANDOFF-RESULT.md`；
`guard.py` 逐路径校验，并对 8 类越界路径做负向自检。

## 被消费的 producer（两种 source 分开记录）

| 角色 | source |
| --- | --- |
| 本包 verifier | 本分支受测 commit（见 `validation.json`） |
| 原 producer | `4a04a9cc74dde67f755c87e87b278d63a254a3ac`（`codex/reader-android-raw3-candidate`），run `40207467982` / attempt 1 / job `121211376063` |
| 原 ZIP | `reader-android-raw3-40207467982-1`（id 12604412854, 113970957 B, sha256 `c3db2ad1…9052805`）、`reader-android-page-theme-40207467982-1`（id 12604537792, 133598571 B, sha256 `9ea28581…156bf06`），均 2027-01-23T15:33:00Z 到期 |
| 原 SDK | 同一 run/attempt 的 `build/session-android/sdk-stage`（3.41.0 头 + `libexreader_jni.so`），不重建 APK |

APK 字节来自上述已认证 ZIP 的 `build/android-raw3/apks/host-debug.apk`；不替换成当前分支 HEAD 的重建产物。

## 抽取方式（为什么不是手填期望值）

`expectations.py` 用 `git show 4a04:<path>` 从 producer 源码重新推导期望：applicationId/versionCode/versionName/minSdk/targetSdk/compileSdk/abi
（`examples/android/app/build.gradle`）、权限与组件（4 份 manifest 合并）、`EXR_VERSION`（`include/exr/base.h`）、字体 pin（`tools/host_font.py`）、
JNI 导出符号名（`examples/android/app/src/main/cpp/*`）。契约只 pin 这些文件的 git blob id 与 APK/SDK 摘要：
producer 源码一变就是**拒绝**（`producer_source_sealed` / `documented_expectations_match_source`），不是静默重定基线。

## 静态验收（认证工件，不重建）

| 区域 | 检查 |
| --- | --- |
| 工件认证 | run/attempt head_sha、conclusion、job id/conclusion、artifact id/name/bytes/digest/expired/expires_at/workflow_run、下载 ZIP 字节与 sha256、安全解压（拒绝绝对路径/`..`/反斜杠/冒号/符号链接/超量条目） |
| 版本 | package、versionCode=1、versionName=0.1.0、sdkVersion=26、targetSdkVersion=35、compileSdkVersion=35 与源码逐一相等 |
| ABI | `lib/` 只有 x86_64；每个 .so 是 ELF64 x86-64 DYN；runtime ABI 由设备 `ro.product.cpu.abi` 复核 |
| 权限 | 合并后 uses-permission **恰好** `android.permission.INTERNET`；任何增删即拒绝（不重定基线） |
| 组件 | 只有 1 个 activity、exported=true、allowBackup=false、debug manifest 的 networkSecurityConfig 在位 |
| SDK/JNI 身份 | APK 内 `lib/x86_64/libexreader_jni.so` 字节 == 同 run sdk-stage 的同一文件；C 源码里每个 `Java_org_exreader_*` 符号在出货 .so 中导出；`JNI_OnLoad` 存在；`3.41.0` 字符串在出货库里 |
| 资源 | resources.arsc、`res/layout/activity_main.xml` 存在；`assets/reader-catalog-v1.json` == 用 `tools/reader_catalog_assets.py` 从 `apps/reader/store/001_catalog.sql`（pin 的 blob）重生成的结果；`assets/Reader.otf` == `tools/host_font.py` 的 pin |
| 签名 | apksigner 验签通过、单签名者、v2/v3 之一在场、证书 DN 含 `Android Debug`（release/商店签名不在范围） |
| 对照 APK | default-OFF 的 `baseline/host-debug.apk` 与候选字节不同、包名/versionCode/权限相同（证明候选确实来自 raw3 family 而非默认 OFF） |

## 云端实机（新模拟器）

API 34 / x86_64 / pixel_6 / `-no-snapshot`（每次新 AVD，干净 profile）：安装前 `pm list packages` 无该包且 `run-as` 无数据目录；安装后
`pm path` 的 base.apk 字节 sha256 == 认证 APK；`dumpsys package` 版本/minSdk/targetSdk 与源码一致；
冷启动后 `sdk_label` 文案 `EXReader 3.41.0/<abi> · x86_64`（运行期真实 native 版本）、`/proc/<pid>/maps` 显示
`libexreader_host.so` 与 `libexreader_jni.so` 从安装包加载；用 `ImportEntry` 的崩溃恢复暂存路径导入原件
（`files/incoming/exr-import/ready/<sha256>.txt` + `.title`，由 owner 代码自己在下次启动接管），私人副本 sha256 == 原件；
打开后写出阅读记录（`book_progress`），翻页后**断网**（airplane+wifi+data+ping 失败）冷启动重开，页码与记录一致且原文字节不变。

## 明确不在本包范围（accepted 不得外推）

商店/签名与公证、真机（USB/读屏/TalkBack）、性能预算、Android 生产/Gradle/现有 tests 的修改、其它平台的互通、
对 APK 内 dex 的逐方法语义审计、native 错误路径分析。
