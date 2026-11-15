# D-FINAL-C：F11 / F12 / H.ipad.annotation_exchange

2026-11-14 接续审计、新增产品库升级/非法标注回归及 Android arm64 宿主构建见
[接续报告](dfinal-c-followup-20261114.md)。下文保留上一轮固定源码的原始结果。

本轮从 `origin/main` 的 `df8e60313e8107ce083572039460de3a0149845e` 建立
`codex/dfinal-c-evidence`；PR base 为 `main`。当前用户明确授权三项台账更新、本地构建与 Actions，
取代 SESSION-CONTRACT.md:6 和产品计划:160 的历史只读/仅 Actions 限制。
分母固定 108，不接管其他 105 项；本地日志标记为本地，不能转授 Actions 或真机。

## 逐字验收文本与 verified 门槛

v1 这三条记录**没有 `acceptance` 字段**，实际目标文本在 `title`；不另造 acceptance。
以下行号以本轮开始的 catalog 为准，新增 evidence 数组可能使后续行号移动。

| ID | catalog 原文 | 对应产品要求 | 一句话 verified 门槛 |
|---|---|---|---|
| F11 | `docs/reader-total-progress/catalog.json:1728`：「移动端可用部署架构与真机能力，未测项目逐项登记并补足交付缺口」 | `docs/READER-PRODUCT-PLAN.md:5–6,42–43,156–157,168–169,185–187,195–196` | 同一最终源码有移动架构构建、实际可安装宿主和逐项能力实测证据，真机/读屏/性能及所有未测项有明确登记，交付缺口有对应产物，才可 verified。 |
| F12 | `docs/reader-total-progress/catalog.json:1736`：「最终版本升级/旧库兼容、许可/依赖与用户安装/导入/同步说明完备」 | 产品计划 `:19–20,76–78,153–157,173–187`；catalog `:1739` 要求全目标共同源码 | 最终版本在各目标上保留旧库/原件/记录并完成升级复开，随实际分发包交付完整依赖许可与用户安装、导入、同步说明，且证据同源齐全才可 verified。 |
| H.ipad.annotation_exchange | `docs/reader-total-progress/catalog.json:1599`：「iPad：宿主标注文件导入/导出、预览确认及错误拒绝」 | 产品计划 `:154,156–157,168,177–178,192–193`；`apple-annotation-macos-audited.md:9,23` 区分系统选择器和跨平台授予 | 必须有 iPad 宿主实际选择/保存 JSONL 与 Markdown、合法导入预览/取消/确认、坏文件拒绝且旧数据不变的源绑定证据；本轮预览确认 UI 按用户要求登记需真机，模型通过不够 verified。 |

## 已有证据、最近真实结果与缺口

| 项目 | 已有证据：路径 / 测试 / 最近真实结果 | 缺失的具体产物 |
|---|---|---|
| F11 | `f06-sdk342-six-packages.md:7–26,30–39`：run 40678657371，源码 8f8acf32，12 jobs 全部成功，六包身份和实际安装/启动核查；Android API34 x86_64 debug 模拟器 APK，iPhone/iPad arm64 模拟器 app；本轮 API 回读见 `evidence/dfinal-c/historical-packages-api.json` | 当前最终源码 Android arm64 可安装宿主 APK（当前 Gradle `abiFilters 'x86_64'`）；iPhone/iPad 签名、profile、实际安装包与设备启动日志；三个移动目标的实机能力矩阵及两设备同步；模拟器不可补齐这些证据。 |
| F12 | `docs/validation/wp12-migration-run39709534123-a1/summary.json`：旧库导出/迁移，Linux、Windows 各 65/65 场景、135/135 检查及真实浏览器 e2e 成功。`docs/READER-APPLE-RECORD-COMPATIBILITY.md:9,27–40`：40176647484 的 18 进程阶段、各 SDK 19 owner 检查及 20+6 正反例成功，范围是 3.40→3.41 macOS owner。`docs/READER-DISTRIBUTION-INVENTORY.md:14–20`：历史生成材料通过，但严格 release-ready 未授予（60 处绝对构建路径）。`tests/test_library_epub_storage.c` 原覆盖 schema1/6→7。 | 当前最终包跨六目标升级复开、product catalog/离线 outbox/凭据与账号设置迁移、旧宿主进程产生的数据回读及中断恢复；最终包完整 SBOM/许可材料与安装说明随包交付；旧原生测试不等于最终宿主 UI 兼容。 |
| H.ipad | `apple-14-item-review-20261029.md:15–17,26` 与 `apple-continuation-20261029.md` 保留失败。最近候选 40923468266 / 622b9558，iPad native job 123625260444 **failure**，严格汇总亦 failure；本轮实际 API 查询保存在 `historical-apple-annotations-api.json`。macOS 39/39 独立成功见 `apple-annotation-macos-audited.md:3–9`，明确不授予 iPad（:23）。代码 `examples/apple/HostWave3.swift:116–178` 已调用 raw3 预览/确认及导出。 | iPad 新源码完整宿主标注交换 XCTest/xcresult、系统选择器截图、原始导出字节、程序哈希及独立审计；预览/确认/取消/拒绝、旋转与生命周期的实际 iPad 真机结果。 |

历史 JSON 和文档给出的是各自固定源码的最近已记录结果；本轮 API 仅复查运行状态，没有重验历史 ZIP，不能冒称已重验旧产物。

## F11 三档部署矩阵与未测登记

| 平台 / 架构 | 能构建 | 能部署 | 真机验证及缺口 |
|---|---|---|---|
| Android x86_64 / API34 | 历史 F06 SDK + debug APK | 历史模拟器安装启动通过 | 需真机；x86_64 模拟器不代表 arm64 实机。 |
| Android arm64-v8a / API26+ | 本轮 Actions SDK 构建，结果及产物见本报告后续运行记录 | 缺 arm64 宿主 APK；Gradle 现只打包 x86_64，不能将 SDK `.a` 当可安装 APK | 需 Android arm64 真机：SAF 权限、重启/后台、Keystore 故障、TLS/取消重试、离线/两端同步、标注往返、读屏和同机性能测量。 |
| iPhone arm64 simulator | 历史 F06 已构建 | 历史模拟器安装启动通过 | 需 iPhone 真机，不是 device arm64。 |
| iPad arm64 simulator | 历史 F06 已构建 | 历史模拟器安装启动通过；标注专项失败 | 需 iPad 真机，尤其本项标注预览确认。 |
| iPhone + iPad device arm64 / iOS15+ | 本轮 Actions `iphoneos` SDK 构建，结果见后续运行记录 | 缺 owner 证书、provisioning、签名宿主包、安装/启动回读；`tools/build_apple_host.py` 的 ad-hoc/unsigned IPA 不能安装到普通真机 | 两种设备分别需文件共享/安全作用域、标注系统保存、确认 UI、后台/重开、Keychain 锁屏、TLS/同步、VoiceOver、固定规模书架性能。 |

未测项逐条登记，状态均为 **需真机**：

| ID | 平台 | 必交产物 |
|---|---|---|
| F11-A01 | Android arm64 | 实际宿主 APK、签名摘要、ABI 检查、安装/启动日志、设备/OS 身份。 |
| F11-A02 | Android | 系统选择器授权/撤销、原件导入与回读、进程终止/后台恢复日志及截图。 |
| F11-A03 | Android | Keystore 故障、HTTPS/401/取消重试、离线重连、第二设备原件/进度/标注/分类同步记录。 |
| F11-A04 | Android | TalkBack 与固定规模书架帧时/峰值内存/首次交互原始采样；性能门槛用同机相对比值。 |
| F11-I01 | iPhone | 签名及 provisioning 身份、安装/启动日志、设备/OS 身份。 |
| F11-P01 | iPad | 签名及 provisioning 身份、安装/启动日志、设备/OS 身份。 |
| F11-I02 / P02 | iPhone / iPad 分别 | Files/文件共享/安全作用域授权、取消与失败、原件逐字节回读、后台/旋转/重启截图和日志。 |
| F11-I03 / P03 | iPhone / iPad 分别 | Keychain 锁屏、TLS/401/取消重试、离线恢复、第二设备四类同步原始记录。 |
| F11-I04 / P04 | iPhone / iPad 分别 | VoiceOver 与同机固定规模性能原始采样及相对比值。 |
| H-P01 | iPad | 实际系统 JSONL/Markdown 保存、合法/非法导入、预览/取消/确认、不变数据库及原始导出文件。 |
| F12-M01 | 三个移动目标分别 | 旧包实际生成库→最终包升级→重开，原件/标注/进度/分类/outbox/账号及凭据保留、中断恢复、安装/导入/同步说明随包交付。 |

## 本轮可自动验证的改动

- `tests/test_library_epub_storage.c`：独立构造 schema1–6 历史布局，逐个注入迁移冲突并验证回滚，移除冲突后升级到7、核查 metadata/原件/笔记/进度、重开并实际打开旧 TXT 内容。没有改 SDK 数据库实现。
- `tests/dfinal_c` + `tools/run_dfinal_c_models.py`：构建安装产品 SQLite、revisions、reading-state、annotation export/import 后，用已有 C/C++ consumer 和独立 Python judge 检查当前源码 raw3；保留生成文件、数据库、负例及进程日志。
- raw3 模型覆盖 JSONL/Markdown 导出、legacy/raw 互拒、NULL/空/NUL 及锚点版本保留、预览零写、完整输入摘要、错误确认、取消/续传、重复不写 outbox、非法格式/hash/身份/预算/未定位拒绝。实际 FOUND 调用公开 SDK；明确 `ALREADY_VERIFIED` 的个案保留 `found_checked=0`，不计为实际定位。
- `.github/workflows/dfinal-c-evidence.yml`：当前源码 Linux 模型回归、Android arm64 与 iOS device arm64 SDK 构建；artifact 附 source、工具链、安装包文件散列。没有替代签名宿主或真机。
- 实测修复 `apps/reader/revisions/EXReaderRevisionsConfig.cmake.in`：raw 包旧守卫不识别当前 SDK 的 `EXR_VERSION → EXR_SDK_VERSION` 单一版本头；接受明确别名时仍验证 `version.h` 与静态库都来自同一安装 prefix。新增五项实际 CMake 正反例，未删除版本拒绝。
- 用户说明见 `docs/READER-INSTALL-UPGRADE-IMPORT-SYNC.md`，说明现有开发包安装、备份升级、导入、标注与同步的实际边界。

## 台账处理

三项均不授予 verified。F11/F12 保持 pending；H.ipad 按本轮「不可 verified 的保持 pending」要求从 partial 改 pending。
verified 仍为99/108，partial0、pending9；这只是状态计数，未重新授予历史证据分数。

v1 `evidence` 是顶层注册表的键数组（`tools/reader_composition/total_progress.py:632–633`），不能填任意路径或“缺”文字，否则现有审计会失败。
只更新这三条的 state/evidence/note：F11 引用已注册的 F06 有限构建/部署证据；新日志路径与明确缺口写在各项 note 和本报告，
F12/iPad 没有已注册且符合目标的完整证据，evidence 保持空。不添加顶层注册项，不改审计器。

## 本轮真实运行结果

### 完整构建、全量及专项 CTest

完整构建与测试在 **GitHub Actions ubuntu-22.04** 完成，源码
`c0b07a699b4a829d310782f0297099a98d5b0519`，
[run 43648272236 / job 132610822654](https://github.com/NoGod3524/EXReader/actions/runs/43648272236/job/132610822654)。
配置、完整编译、安装、专项、全量及模型测试步骤均 success。
全量只排除 `^(sdk-release|sdk-doc-coverage)$`，无其他过滤：

```text
ctest --test-dir build/dfinal-sdk -E '^(sdk-release|sdk-doc-coverage)$' --output-on-failure --parallel 4 --no-tests=error --output-junit .../ctest-full.xml
100% tests passed, 0 tests failed out of 580
Total Test time (real) =  80.52 sec
```

[完整 580 项输出](../../evidence/dfinal-c/ctest-full-actions.txt)，
[含完整编译/安装/专项/全量/模型的原始 job 日志](../../evidence/dfinal-c/actions-model-full-success-43648272236.txt)。

新增/加强测试的真实输出（同一 job）：

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
DFINAL-C annotation model: 164 checks, passed=True
old-literal: accepted
current-alias: accepted
wrong-version: rejected at version guard
missing-version: rejected at version guard
missing-include: rejected at version guard
5 installed SDK version guard checks passed
100% tests passed, 0 tests failed out of 2
```

473 是已有 SDK annotation 套件的保留检查数；2765 是加强后的完整 EPUB storage 套件检查数，
不是新增用例数。模型及版本守卫为独立 CTest 工程的两个测试，与主工程全量580分别列出。

### 移动构建与 ZIP 原件核查

[run 43648272236](https://github.com/NoGod3524/EXReader/actions/runs/43648272236)，
源码 `c0b07a699b4a829d310782f0297099a98d5b0519`，与上面的完整 CTest 同一次运行，三个 jobs 全部 success。
下载三个原始 ZIP 后，核对 API 的 source/run/未过期状态、ZIP 大小及 SHA-256，
再逐文件重算 manifest 所列散列；两套 SDK 分别 **473/473、472/472** 文件一致。
模型原始报告 `passed=true`、164项、无 failed 项。

| 产物 | artifact ID | ZIP 字节数 | ZIP SHA-256 |
|---|---:|---:|---|
| Android arm64 SDK | 14135196050 | 25119092 | `439dcb6262108e3ebdc87960d57dafb30201bb9142e73e3da56a50d9ebaee6d0` |
| iOS device arm64 SDK | 14134883004 | 8957291 | `0c284017b5ebdf04c6d710a5dbef59abd1f0bb75e9a102db277844c621b5e5ff` |
| 模型、文件/数据库及完整 CTest 日志/XML | 14134917078 | 249132 | `1c3b03825f0ca14f5677d80cbe583018927d3fe70c5127944e2859c0a3ec52cf` |

原件与 manifest 核查结果：[verified.json](../../evidence/dfinal-c/actions-43648272236/verified.json)；
同目录保存 API 元数据、逐文件 manifest、模型 result、专项和模型运行输出。
原始 ZIP 保存在本机 `build/dfinal-actions-auth-43648272236-cmd/`，不将大二进制加入源码库。
这些 SDK 包不是 APK/签名 IPA，部署与真机档仍缺，不授予最终六端产品验收。
此前 43646613944 / 34e4b090 的三作业成功及原件核查另保留于 `actions-43646613944/`，不重复计分。

### 本机结果与保留的失败

Windows 的干净配置初次因 CMake TLS 证书链下载失败，改用已有依赖源码缓存后配置成功。
本机存在多组并行编译，本 lane 在 178/1282 阶段中止自己的 Ninja，转由 Actions 提供完整编译与全量验收；
**没有 Windows 完整编译或本机全量 CTest 通过的声明**。
日志 `configure.txt`、`configure-cached.txt`、`configure-final.txt`、`build.txt`、`local-build-status.txt` 均在 `evidence/dfinal-c/`。

原失败保留：

- 43645895705：两移动 SDK 构建成功，模型配置因 raw 守卫未识别新版本头失败；修复共享守卫后重新构建并通过。
- 首轮工件上传漏隐藏文件，Windows 解包中还缺一个长路径 Java 源文件，旧 manifest 检查失败；
  改 `include-hidden-files: true` 并直接读取原 ZIP 核验，在 43646613944 及最终 43648272236 全部核对通过。
- 43647209121：全量579/580，唯一失败 `native-pptx-real-matrix` 的 Calibri 字体回退页面覆盖检查。
  沿用 `native.yml` 同一固定 Carlito 字体及 SHA-256 后，从配置到全量完整重跑580/580；未修改测试断言。
  [失败原始日志](../../evidence/dfinal-c/actions-full-first.txt) 保留。
- 本机 GitHub API 曾有 TLS handshake timeout，`actions-auth-first.txt` 保留失败；重试核验成功输出见 `actions-auth-retry.txt`。

许可检查器本机真实自检：

```json
{"license_checker_self_check": true, "negative_cases": 31, "mandatory_missing_cases": 1, "source_material_positive_cases": 3, "manifest_components": 22}
```

exit0，输出 `evidence/dfinal-c/license-checker-tests.txt`。这是材料检查器自检，不能替代最终六端分发包的 release-ready 核查。

### 台账 diff 与推送门禁

[catalog 完整 diff](../../evidence/dfinal-c/catalog.diff)，
[三条范围/引用/108 分母检查输出](../../evidence/dfinal-c/catalog-scope-check.txt)：

```text
catalog scope: only F11/F12/H.ipad.annotation_exchange state/evidence/note changed; registered evidence references valid
denominator=108; group totals= {'foundation': 12, 'host': 84, 'final': 12}
state counts= {'verified': 99, 'pending': 9}
```

prepush 使用实际外部 harness（仓库 ops 中没有这个脚本）：

```powershell
& C:/Users/Oscar/OneDrive/Desktop/deepseekHarness/ops/prepush-check.ps1 -Worktree C:/Users/Oscar/Documents/Codex/EXReader-dfinal-c
```

首轮及最终均 exit0，冲突标记、code/docs 结构、SDK 文档检查全部通过；
[最终输出](../../evidence/dfinal-c/prepush-final.txt)：

```text
ok    无冲突标记残留
ok    code/docs 结构扫描
ok    check_sdk_docs.py

全部通过 —— 可以推
prepush exit=0
```

`tests/check_reading_release.py` 未修改；[源码范围检查](../../evidence/dfinal-c/source-scope-check.txt)
确认交付的 SDK/app/test/workflow 源码与已实测 c0b07a69 一致。

本轮最终三项均为 pending：F11 缺可部署真机宿主与设备能力证据；F12 缺最终六端升级和随包完整分发材料；
iPad 标注交换缺实际宿主成功证据，预览确认 UI 需真机。具体待测 ID 和必交产物见上表。
