# D-FINAL-C：三项证据审计与可实施补项（2026-11-14）

本轮从 `origin/main` 的 `3be9038853a2e3444c3efdfe2f0027b7493482c1` 建立
`codex/dfinal-c-audit-20261114` 独立工作树，PR base 为 `main`。原工作树和未跟踪文件保留。
工作期间 main 接纳 PR #213 后，已通过 merge f6f6f885 纳入 `38a7031827d5664fd4dd6e8166c9135a7d829355`；
最终受测源码是 `17e0d988ac5d8c9db62402be9d7dfb2b51b745c5`。PR diff不含该main更新本身。
用户本轮明确授权 Windows 本机检查、Actions 构建、三项台账更新；历史 SESSION-CONTRACT 的只读/仅 Actions 约束不覆盖本轮授权。
不修改 `tests/check_reading_release.py`，不变更分母、分组或其他105项。

## 1. 原文与 verified 需要的证据

v1 三条均**没有 `acceptance` 字段**，目标原文保存在 `title`；以下逐字引用该实际字段。
引用行号基于本轮起点，条目未增加行，不另造 acceptance。

| 项目 | catalog 原文及行号 | 产品要求及既有范围记录 | 一句话 verified 门槛 |
|---|---|---|---|
| F11 | `docs/reader-total-progress/catalog.json:1728`：「移动端可用部署架构与真机能力，未测项目逐项登记并补足交付缺口」 | `docs/READER-PRODUCT-PLAN.md:5–6,156–157,168–169,185–187,195–196`；`f06-sdk342-six-packages.md:31–38` 明确历史模拟器不授予真机/部署。 | 同一最终源码的移动架构构建、可安装宿主及实际设备能力有逐项原始产物，真机/读屏/性能独立登记，所有未测项和交付缺口有对应记录与补齐证据，才可 verified。 |
| F12 | `docs/reader-total-progress/catalog.json:1738`：「最终版本升级/旧库兼容、许可/依赖与用户安装/导入/同步说明完备」 | 产品计划 `:19–20,153–157,173–187`：独立产品库、修订/outbox、原件身份、安全凭据及六端同源；`READER-DISTRIBUTION-INVENTORY.md:15–20` 区分材料生成与发布就绪。 | 最终六端共同源码宿主能升级并复开旧库/原件/记录/产品数据/待同步状态，完成平台恢复核查，并随实际分发包交付完整依赖许可及可操作的安装/导入/同步说明，才可 verified。 |
| H.ipad.annotation_exchange | `docs/reader-total-progress/catalog.json:1599`：「iPad：宿主标注文件导入/导出、预览确认及错误拒绝」 | 产品计划 `:156–157,168,177–178,192–193`；`apple-annotation-macos-audited.md:9,23` 区分真实系统文件交换与平台范围；raw3格式契约 `docs/reader-next-c06/RAW3-PORTABLE-ANNOTATIONS.md:34,63–66,86,96–97`。 | iPad 宿主实际系统保存 JSONL/Markdown、选择合法/非法文件、预览/取消/确认、错误拒绝与旧库不变有源绑定日志、原件及程序身份；预览确认按本轮要求需真机，模型通过不足以 verified。 |

起点实读为 **99 verified、0 partial、9 pending**，不是提示中的旧99/1/8：上一轮 PR #211 已将本 iPad 项改为 pending。
该差异不涉及本轮扣分或新授分；分母108，foundation12、host84、final12保留。

## 2. 已有证据、最近真实运行与具体缺口

以下历史结果分别限定到受测源码。本轮重新回读 GitHub API 的原始结果在
`evidence/dfinal-c-20261114/baseline-latest-jobs.json`、`baseline-latest-artifacts.json`、`historical-ipad-jobs.json`，
最新基线输出摘录为 `baseline-latest-output.txt`。API成功不等于本轮重新核验全部历史ZIP。

| 项目 | 已有证据：路径 / 测试名 / 最近真实结果 | 缺失证据：平台与产物 |
|---|---|---|
| F11 | `f06-sdk342-six-packages.md:7–38`：源码8f8acf32 / run40678657371，12 jobs成功；Android API34 x86_64 debug APK、iPhone/iPad arm64模拟器app分别安装启动。上轮核验 `evidence/dfinal-c/actions-43648272236/verified.json`：arm64 Android/iOS device SDK各473/472文件散列一致。最新基线源码33f413cc / run43660231848 三jobs成功、三个工件未过期；本轮API回读成功。 | 当前最终功能 Android arm64 宿主及实际安装启动、iPhone和iPad分别签名包/profile/安装启动；三移动目标设备身份、系统权限/生命周期/凭据故障、读屏、同机性能与双设备同步。SDK `.a` 不充当宿主APK/IPA。 |
| F12 | `tests/test_library_epub_storage.c` 的 `native-library-epub-storage`：最新基线run43660231848，schema1–6→7的回滚/保留/复开/旧TXT打开通过，完整2765检查；`native-annotation` 473检查保留；全量580/580。`docs/validation/wp12-migration-run39709534123-a1/summary.json` 的旧Web格式迁移 Linux/Windows各65场景、135检查及浏览器e2e成功。`READER-APPLE-RECORD-COMPATIBILITY.md:9,27–40` 的40176647484仅macOS owner兼容。许可自检 `tests/check_reading_licenses.py` 本轮Windows实际exit0：22组件、31负例、3正例、1必需材料缺失拦截。 | Windows/macOS/Linux分别旧宿主实际产生的数据→最终宿主升级复开及中断恢复；Android arm64/iPhone/iPad分别安装升级、系统权限与凭据保留或重认证；最终六包实际许可/字体/平台组件SBOM及说明随包交付。已有历史分发材料成功，release-ready未授予。 |
| H.ipad | `apple-14-item-review-20261029.md:17,26`、`apple-continuation-20261029.md:11–15`保留失败。最新已记录候选622b9558 / run40923468266 的 iPad native job123625260444仍为failure，本轮API复核一致。macOS同run39/39和独立核查仅授予macOS，见 `apple-annotation-macos-audited.md:3–9,23`。当前共享 `dfinal-c-annotation-exchange-model` 在基线run43660231848真实164检查通过，安装版本守卫5检查通过。 | iPad当前源码宿主成功的XCTest/xcresult、实际选择/保存截图、导出原始字节及程序hash；合法导入预览/取消/确认、非法输入旧库不变、旋转/后台复开。预览确认UI需真机；共享模型不能替代。 |

## 3. 本轮代码、测试与说明补项

| 改动 | 实际验证目标 |
|---|---|
| `examples/android/app/build.gradle`、宿主CMake、`tools/build_android_host.py`、新 `tools/build_dfinal_c_android_host.py` | 可选arm64-v8a，默认x86_64；消费同job安装SDK构建基础debug APK，检查四个native ELF架构、16KiB LOAD对齐、SONAME/NEEDED；保存APK、摘要和debug签名验证输出。可选sync/reading/wave3集成关闭，产物不代表完整功能宿主。 |
| `tests/dfinal_c/check_exchange.py` | 12类非法原始文件分别预览/提交；使用各自真实摘要仍拒绝、无确认指纹、零提交、产品表内容不变；输入预算len−1/len及续传越界/恰好末尾。原有导出、合法导入、FOUND、取消/续传、NULL和并发保留检查继续执行。 |
| `tests/dfinal_c/catalog_upgrade.c`、`check_catalog_upgrade.py`、CTest注册 | 用历史SQL布局生成v1/v2产品库，当前安装后的公开C provider真实升级到3并由新进程复开；元数据/分类/SDK映射/修订原字节/墓碑/outbox重试字段/原件三状态不变；逐段事务失败回滚与重试；未来schema拒绝且文件字节不变。夹具不是旧宿主运行产生的库，SQL冲突注入不是kill/断电。 |
| `tools/check_dfinal_c_artifacts.py`、`tests/test_dfinal_c_artifacts.py` | 下载原ZIP核对GitHub digest/大小/source/run，再重算SDK文件与APK；把全量CTest XML与排除规则产生的实际测试清单逐项比对，拒绝遗漏、重复、失败和跳过；模型/宿主证据不授予真机。 |
| `.github/workflows/dfinal-c-evidence.yml` | 同一源码Linux完整构建/安装/全量CTest及独立模型、Android arm64 SDK+APK、macos-15上的iphoneos arm64 SDK；记录工具链与原件。 |
| `docs/READER-INSTALL-UPGRADE-IMPORT-SYNC.md` | 补产品库逐段事务失败可能保留中间版本、完整数据备份与安全凭据的边界；安装/导入/同步按实际包入口说明。 |

更详细的两项实现说明见 [移动部署补项](dfinal-c-mobile-followup.md)、[产品旧库回归](dfinal-c-compat-followup.md)。

## 4. 构建 / 部署 / 真机三档及逐项未测登记

| 平台/架构 | 能构建的证据 | 能部署的证据 | 真机能力 |
|---|---|---|---|
| Android x86_64/API34 | 历史F06 SDK+APK | 历史模拟器安装启动；当前源码完整功能待复验 | 缺，不由模拟器转授。 |
| Android arm64-v8a/API26+ | 本轮Actions SDK及基础debug APK实际构建成功，原件散列/ABI复核通过 | 构建APK不等于已安装；缺设备安装/启动 | 需真机。 |
| iPhone arm64 simulator | 历史F06 app | 历史独立模拟器安装启动 | 需iPhone真机。 |
| iPad arm64 simulator | 历史F06 app | 历史独立模拟器安装启动，标注专项失败保留 | 标注预览确认等需iPad真机。 |
| iPhone/iPad device arm64/iOS15+ | 本轮Actions仅iphoneos SDK | 缺两类设备分别签名宿主、profile、安装启动 | 需签名账户及两种真机。 |

沿用前轮登记ID，不改写历史记录：

| ID | 平台 | 缺什么原始产物 / 如何补 |
|---|---|---|
| F11-A01 | Android arm64 | 本轮补基础APK构建；仍需完整功能APK、设备/OS身份、实际安装启动与包签名身份。 |
| F11-A02 | Android | 需真机：SAF授权/撤销、导入和原件回读、后台/进程终止恢复日志与截图。 |
| F11-A03 | Android | 需真机：Keystore故障、HTTPS/401/取消重试、离线重连及第二设备四类数据同步。 |
| F11-A04 | Android | 需真机：TalkBack及固定书库帧时/峰值内存/首次交互原始采样；门槛用同机相对比值。 |
| F11-I01 / F11-P01 | iPhone / iPad分别 | 需Apple打包runner与签名账户：certificate/profile、签名宿主包、真机安装启动及设备/OS身份。 |
| F11-I02 / P02 | iPhone / iPad分别 | 需真机：Files/文件共享/安全作用域授权、取消失败、逐字节回读、后台/旋转/重启。 |
| F11-I03 / P03 | iPhone / iPad分别 | 需真机：Keychain锁屏、TLS/401/取消重试、离线恢复、第二设备四类同步。 |
| F11-I04 / P04 | iPhone / iPad分别 | 需真机：VoiceOver与同机固定规模性能采样及相对比值。 |
| H-P01 | iPad | 需真机：系统JSONL/Markdown保存、合法/非法选择、预览/取消/确认、错误拒绝且旧库不变，原始文件/截图/xcresult/程序hash。 |
| F12-M01 | 三移动目标分别 | 需真机/对应runner：旧包生成真实数据→最终包升级复开、原件/记录/分类/outbox/账号及凭据恢复、进程中断恢复；说明及完整许可SBOM随包。 |
| F12-D01 | 三桌面目标分别 | 需对应Windows/macOS/Linux宿主：旧程序和真实数据、最终新程序升级重开/中断恢复/凭据结果；本轮模块库测试仅补部分模型证据。 |

## 5. 本轮真实运行与原件核查

最终 [Actions43667039578](https://github.com/NoGod3524/EXReader/actions/runs/43667039578)，
源码 `17e0d988ac5d8c9db62402be9d7dfb2b51b745c5`，三个jobs全部success：
Linux模型/完整构建 `132668619747`、Android arm64 `132668619498`、iphoneos arm64 `132668619699`。
下列最终结果全来自这一轮，没有拼接其他源码的成功结果。

### 完整编译和全量CTest

在 **GitHub Actions ubuntu-22.04** 从配置开始真实完整编译、安装；[原始完整job日志](../../evidence/dfinal-c-20261114/actions-model-full.txt)，
[配置](../../evidence/dfinal-c-20261114/actions-43667039578/configure.txt)、[完整编译](../../evidence/dfinal-c-20261114/actions-43667039578/build.txt)、
[安装](../../evidence/dfinal-c-20261114/actions-43667039578/install.txt)。本轮没有Windows完整编译/全量CTest通过的声明。

```text
ctest --test-dir build/dfinal-sdk -E '^(sdk-release|sdk-doc-coverage)$' --output-on-failure --parallel 4 --no-tests=error --output-junit .../ctest-full.xml
100% tests passed, 0 tests failed out of 580
Total Test time (real) =  84.03 sec
```

[580项完整原始输出](../../evidence/dfinal-c-20261114/actions-43667039578/ctest-full.txt)、
[实际CTest清单](../../evidence/dfinal-c-20261114/actions-43667039578/ctest-inventory.json)、
[JUnit](../../evidence/dfinal-c-20261114/actions-43667039578/ctest-full.xml)。下载后逐项比对580个唯一名称与清单一致，
无failure/error/skipped/disabled；只排除用户指定的两项。

### 新增/加强测试的真实输出

统一命令 `python tools/run_dfinal_c_models.py --sdk build/dfinal-stage --build build/dfinal-models`，
消费这次安装的SDK，逐模块编译安装后再编译C/C++消费者，运行独立CTest工程：

```text
1: DFINAL-C annotation model: 206 checks, passed=True
1/3 Test #1: dfinal-c-annotation-exchange-model .....   Passed    1.08 sec
2: 5 installed SDK version guard checks passed
2/3 Test #2: dfinal-c-installed-sdk-version-guard ...   Passed    1.08 sec
3: PASS v1: upgrade metadata, organization, mappings, revisions/outbox retained
3: PASS v1: reopen metadata, organization, mappings, revisions/outbox retained
3: PASS v2: upgrade metadata, organization, mappings, revisions/outbox retained
3: PASS v2: reopen metadata, organization, mappings, revisions/outbox retained
3: PASS future schema rejected with byte-identical database
3: DFINAL-C product catalog upgrade: 33 checks passed
3/3 Test #3: dfinal-c-product-catalog-upgrade .......   Passed    0.14 sec
100% tests passed, 0 tests failed out of 3
Total Test time (real) =   2.29 sec
```

[三项模型完整输出](../../evidence/dfinal-c-20261114/actions-43667039578/models.txt)、
[模型JUnit](../../evidence/dfinal-c-20261114/actions-43667039578/model-tests.xml)、
[标注206项逐项结果](../../evidence/dfinal-c-20261114/actions-43667039578/model-result.json)、
[产品33项结果](../../evidence/dfinal-c-20261114/actions-43667039578/catalog-upgrade-result.json)、
[实际C消费者各进程输出](../../evidence/dfinal-c-20261114/actions-43667039578/catalog-native-processes.txt)。
标注206 = 原164 + 本轮42；产品33是新增；5个安装守卫是保留回归。它们是主工程580之外的独立工程，不把检查数混成CTest数。

保留的SDK旧库专项与SDK标注专项也在本次真实运行：

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

[专项原始输出](../../evidence/dfinal-c-20261114/actions-43667039578/regressions.txt)。2765/473是完整保留套件检查数，不称为本轮新增。

构建前的独立检查真实输出：

```text
DFINAL-C evidence checker: 2 positive, 17 negative checks passed
test_machine_and_load_alignment (__main__.AndroidAbiChecks.test_machine_and_load_alignment) ... ok
Ran 1 test in 0.002s
OK
{"license_checker_self_check": true, "negative_cases": 31, "mandatory_missing_cases": 1, "source_material_positive_cases": 3, "manifest_components": 22}
```

原始输出在同目录 `artifact-checker-tests.txt`、`android-abi-tests.txt`、`license-checker-tests.txt`。
ABI的一个测试对两种架构分别检查正确接受、错误ABI拒绝、低对齐拒绝，共6次断言；不是设备运行。
许可检查是固定材料检查器自检，不能替代最终包SBOM验收。

### 移动产物与原件核查

```text
BUILD SUCCESSFUL in 46s
Verifies
Verified using v2 scheme (APK Signature Scheme v2): true
Number of signers: 1
```

[Android完整job日志](../../evidence/dfinal-c-20261114/android-latest-output.txt)、
[原始签名输出](../../evidence/dfinal-c-20261114/actions-43667039578/android-signature.txt)、
[宿主manifest](../../evidence/dfinal-c-20261114/actions-43667039578/android-host-manifest.json)。
APK为28,317,594字节，SHA-256 `90f93eba01cddf00f72a633d2e1c872f8e6a3b2c24c7d19114f36f2a62cb5cdf`；
debug certificate SHA-256 `d28e33bf727af4f0d11f273e75413ce13a15acbd2df27e91e9b6375bdce9e1e6`。
生产者检查SONAME/NEEDED及签名；本机下载后独立核对整个APK摘要、四个实际ELF的machine183和LOAD对齐16384。
未在本机重复调用apksigner/readelf，不冒称独立复验动态依赖或签名。

| 原始工件 | artifact ID | ZIP字节 | ZIP SHA-256 | 原件核对 |
|---|---:|---:|---|---|
| 模型与完整构建/CTest日志 | 14143400161 | 343821 | `63af79d806bb208ae7e1d285c1d3754374118eee08bd61dda043483006e3e77c` | 标注206、产品33；580+3个CTest名称与通过状态 |
| Android arm64 SDK+基础APK | 14143305427 | 81658455 | `41d47296c94fa6986953d6b65f0d063a90d41c94fdda5dbb1c617bc9e09fa7ce` | SDK515/515文件散列；APK摘要、ABI、4 ELF/16KiB |
| iphoneos device arm64 SDK | 14143305220 | 8960673 | `0144ea4381f42ef95b4dfcfb04d9bc41be6a9ef408c0db352d6173d1f5056742` | SDK474/474文件散列；未签名宿主/未部署 |

本机真实执行并exit0：

```text
python tools/check_dfinal_c_artifacts.py --run 43667039578 --output build/dfinal-actions-43667039578 --require-current-evidence
"jobs_passed": 3
"passed": true
```

[原始核查输出](../../evidence/dfinal-c-20261114/artifact-verification-output.txt)、
[verified.json](../../evidence/dfinal-c-20261114/actions-43667039578/verified.json)、
[CTest核查明细](../../evidence/dfinal-c-20261114/actions-43667039578/ctest-evidence.json)。
同目录保存API元数据和逐文件manifest。三个ZIP及提取的APK保存在本机 `build/dfinal-actions-43667039578/`，不提交大二进制。
Android SDK因现有JNI适配器依赖而开启audio core/PDF，明确MP3/AAC=OFF；iphoneos保留reading-library配置。
基础APK可选sync/reading/wave3关闭，`host_deployed=false`、`physical_device_verified=false`；没有普通设备签名IPA或真机结果。

### 原失败与被替代的运行

| run / 源码 | 真实结果 | 记录及处理 |
|---|---|---|
| 43666459523 / de65ecdf | failure；主工程580通过，但Android配置和独立模型配置失败 | JNI要求audio/PDF；父CMake缺少显式catalog包导入。原失败分别保留 `first-android-failure.txt`、`first-model-configure-failure.txt`，修调用配置与目标作用域后完整重跑。 |
| 43666630014 / ad22339a | cancelled | 已被后续修复替代，主动取消节省runner；不作通过证据。 |
| 43666694203 / 84cedaf5 | failure | SDK成功；宿主构建脚本只编catalog，安装缺original-import库。`android-host-first-failure.txt`保留；改显式构建完整依赖闭包，不删除安装步骤。 |
| 43666798806 / f6f6f885 | cancelled | 吸收最新main后又补父CMake修复，该中间运行主动取消；不作通过证据。 |
| 43666851827 / 7777e48f | failure；模型580+3通过、Android仍缺archive | 完整模型原日志 `pre-final-models-output.txt`保留；不拼其模型和其他源码的APK为最终通过。 |
| 43667039578 / 17e0d988 | success，3/3 jobs | 本报告最终构建、全量CTest、模型与移动产物全部来自此轮。 |

## 6. 台账判定与范围

三项继续 **pending**：F11缺真机可部署的完整功能宿主与能力证据；F12缺最终六端实际升级与随包完整分发材料；
H.ipad缺成功宿主证据，预览确认需真机。本轮不授予verified，不变108分母。

catalog的 `evidence` 是顶层注册键数组（`tools/reader_composition/total_progress.py:632–633`），不能塞路径或“缺”文字。
三项state按实际保留pending；F11的evidence保留已有F06限定范围引用，F12/iPad仍为空，未造完整验收的注册键。
新增具体证据路径和缺口写入三项note；实际catalog diff只有这三处note，不增删注册表或改其他105项。

[catalog完整diff](../../evidence/dfinal-c-20261114/catalog.diff)、[实际范围及源码一致性检查](../../evidence/dfinal-c-20261114/catalog-scope-check.json)：

```text
denominator: 108
groups: foundation12 / host84 / final12
states: verified99 / partial0 / pending9
changed_requirements: H.ipad.annotation_exchange.note / F11.note / F12.note
top_level_unchanged: true
other_105_unchanged: true
registered_evidence_references_valid: true
protected_test_unchanged: true
source_identical_to_actions: true
```

最终catalog blob为 `83b6a7c1e9406981c453878c2fdcfb14b0ead9ad`。99/108为既有状态计数，不是本轮重授旧证据的分数。
文档/证据提交的编译、测试、工具与workflow源码保持与已实测17e0d988一致。
`.gitattributes`只对本轮证据目录保留CRLF/尾随空格原字节；不改变源码检查。

最终使用真实外部harness：

```powershell
pwsh -NoProfile -File <verification-workspace>/ops/prepush-check.ps1 -Worktree <workspaces>/EXReader-dfinal-c-audit-20261114
```

[prepush真实完整输出](../../evidence/dfinal-c-20261114/prepush-final.txt)：

```text
ok    无冲突标记残留
ok    code/docs 结构扫描
ok    check_sdk_docs.py

全部通过 —— 可以推
prepush exit=0
```

`tests/check_reading_release.py`与起点逐字节一致；所有新增模型/构建检查保留拒绝路径、预算和旧失败。
