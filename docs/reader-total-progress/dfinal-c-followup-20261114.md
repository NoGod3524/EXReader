# D-FINAL-C · 2026-11-14 接续证据审计

本次从 `origin/main@38a70318` 新建 `codex/dfinal-c-followup-20261114`，PR base 为 `main`。
该 main 已含上一轮 D-FINAL-C：实际起点为 verified 99 / partial 0 / pending 9，三项均 pending。
用户给出的 99/1/8 是前一状态，不能覆盖已合入记录。固定分母仍为108，分组12/84/12。
本次用户明确要求本机编译、Actions 和三项台账更新，覆盖 SESSION-CONTRACT 的历史只读/仅 Actions 限制。
旧记录及失败留在 [上一轮报告](dfinal-c-audit.md)；本次不重新授予其余105项的证据分数。

## 逐字原文与 verified 门槛

v1 catalog **没有 `acceptance` 字段**。以下逐字引用实际 `title`，不伪造字段；门槛是结合 scope_document 与现有证据边界的审计结论。

| 项目 | catalog 原文及行号 | 产品要求及一句话结论 |
|---|---|---|
| F11 | [catalog.json:1728](catalog.json#L1728)：「移动端可用部署架构与真机能力，未测项目逐项登记并补足交付缺口」 | [产品计划:153](../READER-PRODUCT-PLAN.md#L153)–157、168–169、185–187、195–196：移动架构的构建、可部署宿主、真机能力须分别有源绑定实测，未测项逐条登记且交付缺口补齐，才可 verified。 |
| F12 | [catalog.json:1738](catalog.json#L1738)：「最终版本升级/旧库兼容、许可/依赖与用户安装/导入/同步说明完备」 | [产品计划:153](../READER-PRODUCT-PLAN.md#L153)–157、173–187：最终六目标版本须有旧库/原件/记录及同步状态保留、升级复开和恢复证据，并随实际分发包交付许可依赖及用户说明，才可 verified。 |
| H.ipad.annotation_exchange | [catalog.json:1599](catalog.json#L1599)：「iPad：宿主标注文件导入/导出、预览确认及错误拒绝」 | [产品计划:156](../READER-PRODUCT-PLAN.md#L156)–157、168、177–178、192–193；[既有 Apple 核查:15](apple-14-item-review-20261029.md#L15)–17、26：须有 iPad 宿主实际保存/选择、JSONL 导入预览/取消/确认及错误拒绝且原数据不变的证据；本轮按用户要求将预览确认登记需真机，模型通过不足以 verified。 |

## 已有证据 / 缺失产物

| 项目 | 文件、测试及最近已记录的真实结果 | 仍缺的具体产物 |
|---|---|---|
| F11 | [F06记录:7](f06-sdk342-six-packages.md#L7)–26、31–38：40678657371 / 8f8acf32，12 jobs成功，Android API34 x86_64 debug APK 和两个 Apple arm64 simulator app 的安装/启动及身份。上一轮43648272236 / c0b07a69：Android arm64静态SDK473文件、iOS device arm64静态SDK472文件逐一核验通过。 | Android arm64 宿主实际安装/启动、完整功能及设备能力；iPhone和iPad各自的签名宿主/provisioning、安装启动；三个真机的权限、生命周期、凭据、同步、读屏及性能原始记录。 |
| F12 | [迁移summary:12](../validation/wp12-migration-run39709534123-a1/summary.json#L12)–29：Linux/Windows各65场景、135检查，37–46仍列真实用户库/macOS/Tauri壳缺口。[Apple记录:9](../READER-APPLE-RECORD-COMPATIBILITY.md#L9)、27–38：40176647484的18进程阶段、两个SDK各19 owner检查、20+6策略/拒绝检查，仅macOS owner3.40→3.41。上一轮 `native-library-epub-storage` schema1–6→7、2765检查通过。[分发库存:15](../READER-DISTRIBUTION-INVENTORY.md#L15)–20：生成材料通过，60处构建路径使发布就绪未授予。 | 六目标最终宿主实际旧包生成数据→新包升级→重开，包括凭据/账号、产品库/outbox及中断恢复；最终包许可/SBOM/字体/系统依赖与用户说明随包核对。 |
| H.ipad | [Apple核查:15](apple-14-item-review-20261029.md#L15)–17、26：最近宿主候选40923468266 / 622b9558，iPad job123625260444失败；macOS独立39/39不转授iPad。上一轮 `dfinal-c-annotation-exchange-model` 164检查成功、`dfinal-c-installed-sdk-version-guard`5检查成功，见 `evidence/dfinal-c/actions-43648272236/`。 | iPad系统选择/保存JSONL与Markdown、预览/取消/确认、坏文件错误UI及旧库不变、原始导出字节、xcresult/截图和受测程序身份；预览确认需真机。 |

历史结果为固定源码的已记录结果。本次核验新运行及新工件，不声称重做历史宿主测试。

## 可实施部分

- 新增 `dfinal-c-product-catalog-upgrade`：以仓库历史001/002 SQL建立product v1/v2，注入真实DDL冲突，核对迁移失败回滚；移除冲突后用**已安装**catalog API升级到3、读取并二次重开。保留书籍metadata、SDK映射、书架/标签/系列及顺序、revision/tombstone、outbox队列ID/重试次数/错误，v2原件相对引用。这是模型层布局回归，不是旧宿主安装包生成的数据或断电测试。
- 加强 `dfinal-c-annotation-exchange-model`：在已有旧标注的接收库上，10类非法文件各走preview/正确文件SHA的commit拒绝，核对零提交、无validated摘要及全部reader表不变；另有中文/emoji标题合法预览。覆盖空文件、缺LF、未完成footer、重复键/记录、坏UTF-8、原始/转义NUL、孤立surrogate和Markdown误导入。
- 新增 `dfinal-c-android-abi-inspection`：两个ABI的正确/错machine/混入ABI/缺库共8检查。合成文件只验证检查器；真实APK另核4个ELF、LOAD对齐、build ID、散列和签名日志。
- `build_android_host.py`复用原流程，ABI参数默认x86_64；Gradle显式支持arm64-v8a。宿主继续exact SDK版本匹配，增加当前3.42。新入口 `tools/build_android_arm64_host.py` 构建基础debug宿主，未启用可选sync/reading/wave3，记录 `host_deployed=false`、`physical_device_verified=false`。
- Actions移动SDK产生实际安装内容的 `licenses.json`；分别记录材料检查、pending和release_ready，不以清单生成替代最终包发布就绪。APK内加入当前安装的SDK许可、字体OFL、第一方LICENSE、第三方notices与用户说明。
- [用户安装/升级/导入/同步说明](../READER-INSTALL-UPGRADE-IMPORT-SYNC.md)补充arm64入口、功能范围、debug签名更换时的旧数据处理；卸载重装不计升级保留数据。

测试diff入口：[产品库升级C探针](../../tests/dfinal_c/check_catalog_upgrade.c)、
[标注文件回归](../../tests/dfinal_c/check_exchange.py)、[ABI检查](../../tests/dfinal_c/check_android_abi.py)、
[CTest注册](../../tests/dfinal_c/CMakeLists.txt)；新增构建入口为 [arm64宿主脚本](../../tools/build_android_arm64_host.py)。

## 三档部署与未测登记

| 平台/架构 | 能构建 | 能部署 | 真机验证 |
|---|---|---|---|
| Android x86_64/API34 | 历史SDK+debug APK | 历史模拟器安装/启动通过 | 未测；不能转授arm64。 |
| Android arm64-v8a/API26+ | 本轮静态SDK与基础debug APK分别构建，真实结果见下文 | 本轮只有签名/ABI检查；缺实际安装和启动 | 需真机。完整sync/reading/wave3宿主另缺构建及实测。 |
| iPhone/iPad arm64 simulator | F06分别有app | 历史模拟器安装/启动通过；iPad标注专项仍失败 | 需真机，simulator arm64不等于device arm64。 |
| iPhone/iPad device arm64/iOS15+ | 本轮iphoneos SDK | 缺两目标签名宿主、证书/profile和安装启动；静态库不可安装 | 两类设备分别需真机。 |

沿用原登记ID，不把旧缺口因新增构建而消除：

| ID | 平台及待测内容 | 必交产物与状态 |
|---|---|---|
| F11-A01 | Android arm64宿主 | 基础APK、ABI/签名/散列由本轮构建补；仍缺设备/OS身份、实际安装和启动日志，**需真机**。 |
| F11-A02 | Android SAF授权/撤销、原件导入回读、终止/后台恢复 | 实际操作日志与截图、原件比较，**需真机**。 |
| F11-A03 | Android Keystore故障、TLS/401/取消重试、离线与第二端四类同步 | 两设备原件/进度/标注/分类及outbox原始记录，**需真机**；完整功能宿主仍待构建。 |
| F11-A04 | Android TalkBack、固定书库帧时/峰值内存/首次交互 | 原始采样、同机相对比值，**需真机**。 |
| F11-I01 / F11-P01 | iPhone / iPad分别签名部署 | 证书/profile、签名宿主、设备/OS、安装启动日志，**需签名runner与真机**。 |
| F11-I02 / P02 | iPhone / iPad分别Files/文件共享/安全作用域、取消/失败、回读、后台/旋转/重启 | 原件比较、日志与截图，**需真机**。 |
| F11-I03 / P03 | iPhone / iPad分别Keychain锁屏、TLS/401/取消重试、离线与第二端同步 | 原始设备记录，**需真机**。 |
| F11-I04 / P04 | iPhone / iPad分别VoiceOver及固定规模性能 | 原始采样及同机相对比值，**需真机**。 |
| H-P01 | iPad系统标注文件保存/选择、预览/取消/确认、非法拒绝 | 原始JSONL/Markdown、xcresult、截图、程序身份及旧库不变，**需真机**。 |
| F12-M01 | Android/iPhone/iPad分别实际旧包升级 | 旧包生成库→最终包升级→复开、原件/记录/分类/outbox/凭据/账号保留及恢复，**需真机及最终签名包**。桌面三端最终宿主同样仍缺完整升级出口。 |

本次在PATH及标准/已配置SDK位置未找到adb，未取得本机Android运行证据，盘点输出为 `evidence/dfinal-c-followup-20261114/local-mobile-capability.txt`。
本轮Android构建脚本需Linux+NDK/JDK/Gradle runner；iOS构建需macOS+Xcode runner；签名部署需owner签名身份及设备。真机记录不能由模型/模拟器替代。

## 本轮真实输出与台账

### Windows 完整编译、全量与专项

本机GNU/MinGW16.2 Release完整构建成功，保留配置和编译输出；安装到 `build/dfinal-c-stage` 后清单记录495导出符号。
SDK源码在本lane无改动，模型使用本轮安装SDK和当前产品模块；全量命令仅排除用户指定两项：

```powershell
ctest --test-dir build/dfinal-c -E '^(sdk-release|sdk-doc-coverage)$' --output-on-failure --parallel 4 --no-tests=error --output-junit .../ctest-full-windows.xml
```

```text
100% tests passed out of 581
Total Test time (real) = 240.75 sec
ctest exit=0
```

原始XML为581 tests / failures0 / skipped0 / disabled0。
[完整CTest输出](../../evidence/dfinal-c-followup-20261114/ctest-full-windows.txt) ·
[XML](../../evidence/dfinal-c-followup-20261114/ctest-full-windows.xml) ·
[完整编译](../../evidence/dfinal-c-followup-20261114/build-windows.txt) ·
[最终安装](../../evidence/dfinal-c-followup-20261114/install-windows.txt)。

新增/加强工程的本机真实输出（最终产品代码 `cdf0204d`，`actions=false`）：

```text
DFINAL-C annotation model: 185 checks, passed=True
8 Android APK ABI checks passed (synthetic files; no device execution)
5 installed SDK version guard checks passed
product schema 1 -> 3: failure rollback, metadata/mappings/organization/revisions/outbox, installed API and reopen passed
product schema 2 -> 3: failure rollback, metadata/mappings/organization/revisions/outbox/original reference, installed API and reopen passed
541 product catalog upgrade checks passed
100% tests passed out of 4
Total Test time (real) = 20.42 sec
models exit=0
```

[完整专项编译/安装/CTest输出](../../evidence/dfinal-c-followup-20261114/models-windows.txt) ·
[4项XML](../../evidence/dfinal-c-followup-20261114/model-tests-windows.xml) ·
[185项逐项结果](../../evidence/dfinal-c-followup-20261114/model-result-windows.json)。
独立安装product探针也真实通过541检查，[命令和安装文件散列](../../evidence/dfinal-c-followup-20261114/product-upgrade-provenance-windows.json)保留。
185/541/8/5为各套件检查数，不是新增CTest数量；本lane新增21条标注模型检查、产品升级和ABI两项CTest，原版本守卫保留。

许可检查器自检真实exit0：

```json
{"license_checker_self_check": true, "negative_cases": 31, "mandatory_missing_cases": 1, "source_material_positive_cases": 3, "manifest_components": 22}
```

[输出](../../evidence/dfinal-c-followup-20261114/license-checker-windows.txt)。工件XML检查器另接受真实历史2/2和本机4/4，并拒绝10个缺项/失败/跳过/重复/模式错误负例，
[可复现自检及输出](../../evidence/dfinal-c-followup-20261114/artifact-checker-selftest.txt)。

### 失败与重试保留

- 首轮Actions43669123748 / 9c38f335：models job真实成功（全量580/580、专项4/4）；Android host job因 `libreader_original_import.a` 未构建导致安装失败。修复共享helper为完整build再install，保留[失败原始日志](../../evidence/dfinal-c-followup-20261114/android-host-initial-failure.txt)。该旧运行在已有作业结束后取消排队的旧iOS作业，整体为cancelled，不能称整轮通过。手动重复的43669141954也已取消，不计通过。
- 本机最初安装因配置后HEAD改变被源码身份守卫拒绝；重新配置、构建、安装成功。[原失败](../../evidence/dfinal-c-followup-20261114/install-windows-initial-failure.txt)保留，未放宽守卫。
- 本机标注模块最初因MinGW头已定义 `NOMINMAX`、代码又重复定义而触发 `-Werror`。为两个模块的Windows宏增加 `#ifndef` 保护后，完整重跑构建和4项模型通过；[原失败](../../evidence/dfinal-c-followup-20261114/models-windows-initial-failure.txt)保留，没有关闭警告或降低断言。
- 9806922b的Actions43669452548四job全部success；最终cdf0204d仅新增上述Windows宏保护，仍另跑完整同源Actions，以下以最终运行作交付依据。

### 最终 Actions 真编译、全量与专项

[43669902467 / attempt1](https://github.com/NoGod3524/EXReader/actions/runs/43669902467)，受测源码
`cdf0204dd6ef5a4e9c558921213621680cfd54cd`，**四个jobs全部success**：Ubuntu22.04完整SDK/模型、Android arm64 SDK、Android arm64基础宿主，以及macOS15的iOS device arm64 SDK。
模型job132677423240从配置、完整编译、安装到全部测试均成功，完整命令仍仅排除 `^(sdk-release|sdk-doc-coverage)$`：

```text
100% tests passed, 0 tests failed out of 580
Total Test time (real) = 107.29 sec
```

[全量580项原始输出](../../evidence/dfinal-c-followup-20261114/actions-43669902467/ctest-full.txt) ·
[全量XML](../../evidence/dfinal-c-followup-20261114/actions-43669902467/ctest-full.xml) ·
[完整编译](../../evidence/dfinal-c-followup-20261114/actions-43669902467/build.txt) ·
[完整原始job日志](../../evidence/dfinal-c-followup-20261114/models-actions.txt)。
本机581与Linux580均无失败或跳过；逐项XML比较见 [ctest-summary.json](../../evidence/dfinal-c-followup-20261114/ctest-summary.json)。

保留的SDK旧库/标注专项真实输出：

```text
473 annotation exchange checks passed
schema 1 -> 7: rollback, metadata/source/notes/progress, reopen and document open passed
schema 2 -> 7: rollback, metadata/source/notes/progress, reopen and document open passed
schema 3 -> 7: rollback, metadata/source/notes/progress, reopen and document open passed
schema 4 -> 7: rollback, metadata/source/notes/progress, reopen and document open passed
schema 5 -> 7: rollback, metadata/source/notes/progress, reopen and document open passed
schema 6 -> 7: rollback, metadata/source/notes/progress, reopen and document open passed
2765 independent EPUB storage checks passed
100% tests passed, 0 tests failed out of 2
```

[专项原始输出](../../evidence/dfinal-c-followup-20261114/actions-43669902467/regressions.txt)。新增/加强工程同一job真实通过：

```text
DFINAL-C annotation model: 185 checks, passed=True
8 Android APK ABI checks passed (synthetic files; no device execution)
5 installed SDK version guard checks passed
product schema 1 -> 3: failure rollback, metadata/mappings/organization/revisions/outbox, installed API and reopen passed
product schema 2 -> 3: failure rollback, metadata/mappings/organization/revisions/outbox/original reference, installed API and reopen passed
541 product catalog upgrade checks passed
100% tests passed, 0 tests failed out of 4
Total Test time (real) = 2.03 sec
```

[新增工程真实构建/安装/运行输出](../../evidence/dfinal-c-followup-20261114/actions-43669902467/models.txt) ·
[4项原始XML](../../evidence/dfinal-c-followup-20261114/actions-43669902467/model-tests.xml)。

### 四个原始 ZIP 与移动产物

原始ZIP下载到 `build/dfinal-c-followup-actions-43669902467/`，不提交二进制包。
API的source/run/未过期状态、ZIP大小和SHA逐一核对，再重算两套SDK清单内 **475/475、474/474文件** 和APK原始字节散列；模型result185项和4项CTest XML均核对通过。
命令及完整真实stdout：

```powershell
python tools/check_dfinal_c_artifacts.py --run 43669902467 --android-host --output build/dfinal-c-followup-actions-43669902467
```

[核验输出](../../evidence/dfinal-c-followup-20261114/artifact-verification.txt) ·
[verified.json](../../evidence/dfinal-c-followup-20261114/actions-43669902467/verified.json)：`passed=true`、exit0。

| 工件 | artifact ID | ZIP字节 | ZIP SHA-256 |
|---|---:|---:|---|
| Android arm64 SDK | 14143777006 | 25133721 | `b8a7b2d1f0cc5d9b36fe1f27d4f023f3931e0b2a4cdf973ed8ca054bef43ed0f` |
| iOS device arm64 SDK | 14143443880 | 8971893 | `9f5f76fcabc62abf52691d8b00ee246abf6c21c5541c60a7f893ec9c05c850fd` |
| Android arm64基础debug宿主 | 14143154386 | 19521873 | `7fd320d179122072d9c09cc80ae61752f84145bb92ef1a2367f8fb06b250bf58` |
| 模型/旧库/全量原始输出 | 14143667948 | 278905 | `f27c5e2d61d1be8c7327ab593cc20dcf2003b6bad91aa5c96857b5e6a28f2b7b` |

真实APK为 **26126725字节**，SHA-256 `287a55ffd902df3b6d500174ceb5e633f3080fb717af8157c5aff400bdcc7e74`。
构建器实际检查四个arm64 ELF、16KiB LOAD对齐、build ID及apksigner；独立审计重读原ZIP/ELF字节散列和原始检查日志，未在本机重新验签或重解析ELF对齐。
[APK构建清单](../../evidence/dfinal-c-followup-20261114/actions-43669902467/android-arm64-host-build.json)与
[签名原始输出](../../evidence/dfinal-c-followup-20261114/actions-43669902467/android-host-signature.txt)均保留。
`host_deployed=false`、`physical_device_verified=false`；仍缺安装、启动、完整功能和实机能力。

本轮两套SDK的实际许可/依赖核查均为 `materials_check_passed=true, pending=[], release_ready=true`：
[Android清单](../../evidence/dfinal-c-followup-20261114/actions-43669902467/android-arm64-v8a-licenses.json)、
[iOS清单](../../evidence/dfinal-c-followup-20261114/actions-43669902467/iphoneos-arm64-licenses.json)。
这是reading-library SDK材料检查的出口，最终宿主包、字体、组合模块、平台依赖及完整SBOM仍属于F12缺口。

### 台账与最终判定

| 项目 | 最终state | 理由 |
|---|---|---|
| F11 | pending | 基础APK和SDK构建补齐部分产物，仍缺实际部署、完整功能宿主、三个真机的能力/读屏/同机性能及两设备闭环。 |
| F12 | pending | SDK与product布局升级回归通过，仍缺最终六端旧宿主数据/凭据/账号升级和恢复、完整分发包许可/SBOM/字体/系统依赖核对。 |
| H.ipad.annotation_exchange | pending | 模型读写/摘要确认/拒绝通过，仍缺iPad系统文件交换与预览确认等真机宿主证据。 |

`evidence` 是顶层注册表的键数组，不能填任意文件路径或“缺”文字。
本轮没有取得满足这三项完整目标的新授予证据，因此保留原state/evidence，仅更新这三条note中的原始结果入口及明确缺口；
F11保留F06的有限历史引用，不把模拟器/构建计为真机验收，不新增顶层注册项。

[catalog完整diff](../../evidence/dfinal-c-followup-20261114/catalog.diff)只有三条note改变；
[可运行范围检查](../../evidence/dfinal-c-followup-20261114/check_scope.py)的真实输出为：

```text
catalog changed only: F11, F12, H.ipad.annotation_exchange
registered evidence references valid; titles/IDs/top-level catalog unchanged
denominator=108; groups= {'foundation': 12, 'host': 84, 'final': 12}
states= {'verified': 99, 'pending': 9}
tests/check_reading_release.py unchanged
```

状态计数仍为99 verified / 0 partial / 9 pending，没有加分。
[源码范围核对](../../evidence/dfinal-c-followup-20261114/source-scope-check.txt)确认SDK源树未改，产品/测试/工具/宿主/工作流代码与受测cdf0204d一致；其后提交只补文档、台账说明、原始证据和本目录的证据字节保留规则。
沿用仓库既有 `.gitattributes` 规则，为本证据目录设置 `-text -whitespace`；真实逐文件核对60份证据与暂存区字节完全一致，保留CRLF和原始行尾空格。源码空白检查继续启用，完整diff检查exit0。

### prepush

本机实际执行外部harness，未跳过文档门禁：

```powershell
& C:/Users/Oscar/OneDrive/Desktop/deepseekHarness/ops/prepush-check.ps1 -Worktree C:/Users/Oscar/Documents/Codex/EXReader-dfinal-c
```

[完整真实输出](../../evidence/dfinal-c-followup-20261114/prepush-final.txt)：

```text
ok    无冲突标记残留
ok    code/docs 结构扫描
ok    check_sdk_docs.py

全部通过 —— 可以推
prepush exit=0
```
