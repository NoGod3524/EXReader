# D-FINAL-C F11 移动部署补项（2026-11-14）

本轮基线是 `origin/main`；具体源码 SHA、Actions run、job、ZIP 原件散列和实际通过状态以本轮总报告及下载核查结果为准。

F11 原文在 `catalog.json:1728`：「移动端可用部署架构与真机能力，未测项目逐项登记并补足交付缺口」。
记录没有单独的 `acceptance` 字段。产品要求见 `READER-PRODUCT-PLAN.md:156–157`（六目标实际流程、生命周期、两设备闭环，真机/读屏单列）、`:168–169`（系统选择器/URI/文件共享）和 `:185–196`（安全凭据与固定规模性能）。
verified 门槛：同一产品源码的移动端构建、可安装宿主与实际设备能力有逐项产物和实测，未测项逐条登记并补齐交付缺口。

| 平台/档位 | 基线已有证据 | 本轮补项 | 仍缺的产物 |
|---|---|---|---|
| Android x86_64 模拟器 | `f06-sdk342-six-packages.md:7–34`：run40678657371 的六包/12 jobs 成功，Android debug APK 安装启动；不授予真机（:36–38）。 | Gradle 默认 `x86_64` 保留。 | 当前最终产品源码模拟器完整复验；不能由 arm64 构建或历史包代替。 |
| Android arm64-v8a 构建 | `evidence/dfinal-c/actions-43648272236/verified.json` 与原报告：SDK 安装文件473项散列一致，只有 SDK 包。 | 本 lane workflow 增加 JNI/shared，消费同 job 安装包构建**基础宿主 debug APK**；构建产品库/revisions/commands，核对四个 native ELF 的 AArch64 machine183、16KiB LOAD 对齐及 SONAME/NEEDED，保留 APK/SHA-256/debug 签名验证输出。Actions 状态见本轮总报告。 | **需真机**：APK 实际安装/启动日志、设备/OS、SAF权限/撤销、后台/杀进程恢复、Keystore故障、TLS/取消/离线重连、双设备原件/进度/标注/分类、TalkBack、同机相对性能。当前 APK 的可选 sync/reading/wave3 integrations 关闭，不构成完整产品交付。 |
| iPhone/iPad arm64 simulator | 历史 F06 分别实际安装启动，`f06-sdk342-six-packages.md:34`。 | 本轮不增加模拟器验收。 | **需对应 Apple runner** 重建/宿主实际流程；iPad 标注专项仍需真机。 |
| iPhone/iPad device arm64 | 原 run43648272236 的 iphoneos SDK 文件472项散列一致。 | 本轮继续构建 iphoneos arm64 SDK，不签名宿主。 | **需签名账户和真机**：分别的 certificate/profile/签名包、安装启动、Files/安全作用域、Keychain锁屏、后台/旋转/重开、VoiceOver、同步与同机相对性能。 |

`tools/build_dfinal_c_android_host.py` 用 `sdk_version.installed_version()` 解析旧字面量及当前 `EXR_VERSION → EXR_SDK_VERSION` 版本别名，并强制与源码 `cmake/versions.cmake` 一致，再显式传给 Gradle 的 EXACT SDK 查找；基础宿主 CMake 明确补入当前3.42，历史默认仍3.41。
`tools/build_android_host.py` 的产品构建、复制和 ELF/APK 检查新增可选 ABI 参数，默认仍 x86_64；APK 解包检查使用独立临时目录。

本轮本机真实轻量结果：

```text
python tests/test_dfinal_c_android_abi.py -v
test_machine_and_load_alignment (__main__.AndroidAbiChecks.test_machine_and_load_alignment) ... ok
Ran 1 test in 0.043s
OK
```

该测试逐个验证 x86_64/arm64 ELF 接受、错误 ABI 拒绝、低于16KiB对齐拒绝，共6次断言；使用构造的 ELF header，不声称运行过 APK。
`python -m py_compile tools/build_android_host.py tools/build_dfinal_c_android_host.py` 和 `git diff --check` 本机 exit0。
完整 APK 构建、签名验证与 SDK artifact 核查结果须引用本轮真实 Actions，不由本机语法检查推定。

交付分档：**能构建**由 APK/SDK 原件、工具链、源 SHA 和散列支持；**能部署**需实际安装/启动记录；**真机验证**需设备身份和逐项原始日志。
新 APK manifest 明确 `tier=host-apk-build-only`、`host_deployed=false`、`physical_device_verified=false`，F11 保持 pending。
