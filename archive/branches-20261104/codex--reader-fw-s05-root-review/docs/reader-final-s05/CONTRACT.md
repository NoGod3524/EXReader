# S05 iPhone/iPad 模拟器分发核验契约

## root审查后的独立修订与实际结果

独立分支 `codex/reader-fw-s05-root-review` 从S05已提交 `ccef845e9f5cfe8c5a810d1ea7d4dedfce2c3214` 建立；原DS工作树未改。下面§6保留的是旧72失败历史；当前默认producer是成功source `5ac5e1fa4cf6dcbfe81ea14b9f64b6288470164a` / run `40217963443` / attempt1 / `.github/workflows/reader-apple-raw3-ios-ready.yml`。iPhone工件12608976777（152515213B、`06cf2e467ce225e927b32f36dccf7febe93fc15bc60fc0d5450cfc56b068f49f`），iPad12608483488（186145203B、`2a37546c8d0bbcb8f171e6f2292bb3d2a94fa24e2ea07d4dcdd12ffe07fd7ead`），有效期均 `2027-01-23T17:45:06Z`。该producer身份与下述S05工具受测身份分开记录。

本修订只加强本包证据链：

1. 指定producer的attempt API、完整五作业ID/状态/source、唯一精确工件ID/名称/大小/digest/归属/未来有效期全部闭合；只选择 `program-raw/EXReaderHost.app`，核对原 `result.json/files` 全目录字节及各成功raw phase的实际程序hash，不按任意名字排名授予。
2. 原report只记录文件bytes/SHA，未记录原chmod和symlink元信息。故只授可证明的全部文件字节；`original_modes_links_accepted=false/status=pending`。解包后的观察模式仅用于ditto副本、已认证tar和恢复之间的比较，不提升为原producer模式证明；不重设权限、不重签原包。若原包执行权限缺失，保留真实安装/检查失败，不修成“原模式已保留”。
3. 安装后核全部文件集/字节/hash和安全链接，对比源与安装后观察模式并记录事实；源模式与链接原始保真仍pending。真实launch PID和ps返回的canonical程序路径必须等于实际安装的可执行文件，不再做名字substring匹配。
4. 所有结果记录implementation SHA/run/attempt。summary重新认证本轮五个上游成功作业及五份原ZIP；核对API digest、大小、未来有效期、唯一名称/source/run，下载重算ZIP，拒绝重复/缺失/跨轮JSON；完整检查两份producer intake、四份fixture结果与两份producer结果及bundle/install事实。汇总不再从目录任意取第一份或覆盖重复设备结果；只有实际producer授予成立才exit0。
5. 新增最小纯证据负例（只在Actions）：跨attempt、工件归属/大小/digest/有效期、资源/模式变更、错误PID/程序路径、未密封authority签名不能established、重复/缺失结果。原fixture、15个分类mutant、模拟器预算与原签名事实保留。

root随后授权本分支云端运行。受测实现 `d0a3971d0ee1254b24e4f5f9bc4503ebff3844ab`，[run40226594342](https://github.com/NoGod3524/EXReader/actions/runs/40226594342) / attempt1，首轮6作业全部success：fixture/classification121269154902、intake iPhone121269155000 / iPad121269155217、实际干净安装 iPhone121269891867 / iPad121269891846、严格汇总121273193815。原15项分类符合各自明确预期，新增10项具名拒绝与PID/路径/签名断言通过。

两个实际producer均 `manifest_complete=true`、安装烟测pass、`granted=true/blocked_by=[]`；严格汇总重新认证5份同轮上游ZIP、唯一6结果/两份intake及全目录安装证据，输出 `accepted=true/problems=[]`。iPhone实际24文件48,675,556B，程序SHA `d1dac59d708f2f09cd3d125912d114f125327746eafaa957f5374ae30a3a0a01`；iPad24文件48,675,508B，程序SHA `056d8f96ceddeff9c3ca0517b2f36f73d642eb8c974cb179ec37c614dd315abd`；各自绑定各自原ZIP，Info.plist共同SHA `91ad4be23fba41b207cda38b7976c2a91fa7ae60ece3c8d4593f320efa00c344`。全部原bundle文件（含实际SDK动态库）身份和安装后清单保存在认证工件内。

原包真实签名事实为ad-hoc、`verify=false/bundle_sealed=false/established=false`；两项pending为 `signature.verify` 与 `producer.original_modes_links_preservation`，未重签/改权限。汇总的accepted仅授全部原bundle字节、副本、干净模拟器安装与实际程序启动，不授原权限/链接保真、设备签名、读屏、真机、性能或完整产品。

| 本轮工件 | ID | 字节 | SHA256 | 有效期 |
| --- | ---: | ---: | --- | --- |
| harness | 12611273821 | 163376 | `ad0de45ba8290ec06b50d3cda97ef946a385ede9d0aa5adc2174f0b91c8790e6` | 2026-11-08T19:35:31Z |
| intake iPhone | 12611765260 | 27985656 | `93d68984b1e7e979945ea7bbe7e50e3fcb695ad4ee4785f23a3114f989a53a10` | 2026-11-08T19:36:04Z |
| intake iPad | 12610884735 | 27985664 | `f9d7a456a355f8686d5040a38097b32b76938fb440edb7e3de7ac89fd700b0da` | 2026-11-08T19:36:30Z |
| smoke iPhone | 12612550491 | 83618 | `8dd3e4ee38630d17a59073dbffe4cffe2a404a91b4719d607ef4db230d75c703` | 2026-11-08T19:50:15Z |
| smoke iPad | 12611671612 | 97714 | `ea60689acbc5578648f69648d7c6f3302ca60d26bf5d85b87fe8a90dabbc8f79` | 2026-11-08T19:47:53Z |
| summary | 12611776623 | 12764 | `26a0a5c115784ab4e427292f155eaab5cd3386cc6b27de6400f607a018710fa5` | 2026-11-08T19:50:30Z |

封存仅更新本契约、验收JSON和测试目录README，运行源码仍为d0a3971d。原host、SDK、原producer的测试/裁判/预算未改，所有执行与工件下载解析均在Actions。

固定实现起点 `0889f7d1e9a537c6c1b05456547e016b26e1cd85`，分支 `codex/reader-fw-s05`。
本包只新增 `tests/reader_final_s05/`、`.github/workflows/reader-final-s05.yml`、`docs/reader-final-s05/` 与
`HANDOFF-RESULT.md`；现有 apps/examples/SDK/tests/workflow 全部只读。

## 0. 已有实现盘点与复用

先查出与本包相邻的检查，未重复实现：

- `tools/build_apple_host.py`：既有模拟器 `.app` 布局（`Info.plist`、`Frameworks/`、ad-hoc 签名、`CFBundleSupportedPlatforms`、
  `UIFileSharingEnabled`），本包只读引用其布局约定，不修改；
- `tools/check_apple_host.py`：既有的模拟器选择 / boot / bootstatus / install / 容器读取 / 关闭模式，本包复用同一
  simctl 流程，但额外要求安装前无容器、安装后可执行文件 hash 对照、宿主进程存活与程序路径；
- `tests/apple_host/evidence_contract.py`：已有对 `CFBundleSupportedPlatforms == ['iPhoneOS']` 的设备包判定与 Mach-O
  UUID 读取，本包按相反方向（模拟器）判定并自行解析 Mach-O 头与 `LC_BUILD_VERSION`；
- `tests/reader_distribution_inventory/`：明确声明 mobile packaging / host bundles / signing 不在其范围，本包不与其重叠；
- producer 侧 `tests/apple_host/raw3/ios/reading/`（`driver.py`、`verify.py`）只读引用其 artifact 名称、Info.plist 键
  （`EXRSourceSHA`、`EXRSDKVersion`、`EXRRawSelectorEnabled`）与失败事实，不复制其 UI 用例，也不修改它。

## 1. 范围

为 root 指定的 Apple 移动 producer 增加模拟器 `.app` 分发核验：

1. 安装清单：bundle 标识、可执行文件、Info.plist、逐文件字节数与 SHA-256、嵌套代码、签名与 entitlement 事实；
2. bundle / 资源 / 架构 / entitlement 核验（命名检查，见 §4）；
3. 干净设备安装烟测：iPhone 与 iPad 分别 erase → install → 安装后可执行文件 hash 对照 → launch → 进程存活与真实程序路径 → 卸载 → 再 erase。

不做、也不声称：真机安装、读屏、USB、设备签名 / provisioning / 公证、App Store / TestFlight、性能预算。
文件共享只按实际 Info.plist 的 `UIFileSharingEnabled` / `LSSupportsOpeningDocumentsInPlace` 记录，
不据此授予设备侧文件共享能力。

## 2. 两种 source 必须分开记录

| 角色 | 内容 |
| --- | --- |
| implementation source | 核验工具自身的提交（`sources.implementation.sha/branch`） |
| producer source | 被核验 app 的 run / attempt / workflow / head commit / artifact id / 字节数 / artifact API digest / 二次 SHA-256 / 有效期 |
| fixture source | CI 内生成的夹具 app（`S05Fixture=true`、`EXRSourceSHA` = 本提交），只证明工具 |

`producer_source.py` 下载原工件 ZIP 后必须同时满足：ZIP 字节数等于 artifact `size_in_bytes`、
SHA-256 等于 artifact API 的 `digest`、等于指定 digest。抽出后每个 `.app` 记录可执行文件与 Info.plist 的
SHA-256；`verify.py` 再对实际安装路径重算并与认证值比对，确保安装的字节就是被认证的字节。
staged app 以 tar 传输，保留 mode 与符号链接，避免二次 artifact 上传丢权限位。

## 3. 三种模式

| 模式 | 触发 | 含义 |
| --- | --- | --- |
| `fixture` | `--app` 且无 `--producer-source` | 只证明工具：未被改动的夹具必须被接受，每个 mutant 必须被命名检查拒绝 |
| `diagnostic` | producer 记录 `eligible=false` | 记录真实 producer app 的 bundle/架构/entitlement 安装清单与安装烟测事实，**永不授予** |
| `producer` | producer 记录 `eligible=true` | 只有 run `conclusion=success`、head commit 匹配、artifact digest 匹配、未过期时才可能授予 |

`eligible` 由 `producer_source.py` 计算：run 失败、commit 不符、workflow 不符、artifact 缺失/过期、
ZIP 与 digest 不符、缺 `.app` 均写入 `blocked_by`。`verify.py` 对 `producer` 模式要求 `eligible=true`，
对 `diagnostic` 模式要求 `eligible=false`，两者不能互换。

## 4. 命名检查

bundle：`bundle.info_plist`、`bundle.identifier`、`bundle.package_type`、`bundle.version`、
`bundle.executable`（存在且可执行且为 Mach-O）、`bundle.platform`（`CFBundleSupportedPlatforms == ['iPhoneSimulator']`）、
`bundle.family`（iPhone 需 1，iPad 需 2）、`bundle.minimum_os`（≤ 实际模拟器 runtime）、
`bundle.source_binding`（`EXRSourceSHA` = 指定 source）、`bundle.sdk_version`（producer 需 3.40.0/3.41.0）、
`bundle.not_fixture`（producer 模式拒绝夹具）、`bundle.fixture_marked`（fixture 模式要求夹具标记）。

架构：`arch.main_arm64`、`arch.simulator_platform`（全部 Mach-O 的每个 slice 的 `LC_BUILD_VERSION`
platform = iossimulator）、`arch.device_slice_absent`（无 ios slice）、`arch.consistent_arm64`、
`arch.nested_code`（Frameworks/PlugIns 内的嵌套代码必须是 Mach-O，framework 必须有 Info.plist 与可执行文件）。

资源：`resources.inventory`（逐文件 SHA-256）、`resources.symlink`（拒绝绝对/越界符号链接）、
`resources.special`（拒绝 FIFO/设备等非普通文件）、`resources.case_collision`（大小写碰撞）。

签名与 entitlement：`signature.verify` 分三种：未签名 → pending；只有可执行文件被签名、
没有 `_CodeSignature/CodeResources`（`bundle_sealed=false`，例如 `CODE_SIGNING_ALLOWED=NO` 的 linker
ad-hoc 签名）→ pending（记录 `state`、`verify` 与原始 log，不得据此声称已签名）；bundle 已封装签名 →
必须 `codesign --verify --deep --strict` 通过，否则 fail（被改动的密封资源属于这一类）。
`result.signing.established` 只有“带 authority 的 bundle 签名且校验通过”才为 true，且始终不授予设备签名。
`entitlements.parse`、
`entitlements.no_private`（拒绝 `com.apple.private.*`）、`entitlements.application_identifier`、
`entitlements.debug_marker`（`get-task-allow=true` 记 pending，不授予设备签名）。

安装烟测：`install.clean_device`（先 erase 且安装前无容器）、`install.installed`、
`install.identity`（安装后可执行文件 SHA-256 等于源）、`launch.started`、`launch.alive`（4 秒后仍存活）、
`launch.program`（宿主 `ps` 指向安装后的可执行文件）。

## 5. 判定

- `manifest_complete` = 无 `fail` 检查；
- `install_manifest_complete` = `manifest_complete` 且安装烟测通过；
- `capability_verified` 只用于 fixture 模式；
- `granted` 只在 `producer` 模式、producer `eligible`、安装清单完整时成立，否则 false 并写入 `blocked_by`；
- `summary.py` 的 `accepted` 还需要 iPhone 与 iPad 两类设备各自 `granted`。fixture 结果不进入 `accepted`。

## 6. 当前 producer 指定与现态

- producer workflow：`.github/workflows/reader-apple-raw3-ios.yml`
- run `40203714083` / attempt 1，head `72c6bbdd14ebf3be453fa7f0da81119d52675eb5`，结论 **failure**
- 失败点：iPhone UI 作业的 original OFF 七例中 `ReadingUITests.testFixedCbzAndPdfRealPointRecords`、
  `ReadingUITests.testRealTerminationAfterCommitReplaysExactlyOnce` 失败（7 例 2 失败），随后 summary 作业断言
  “两个 producer 作业都 success” 失败；iPad 作业本身 success，但整轮失败，**不能作为成功来源**。
- 因此本包 `accepted=false`，producer 侧为 pending；工具以 CI 生成夹具完成全部能力证明，
  并对该失败 run 的原始 artifact 做 diagnostic 记录（只记录事实，不授予）。
- 该失败 run 的 app 由 `CODE_SIGNING_ALLOWED=NO` 构建：`Info.plist` 有 `EXRSourceSHA=72c6bbdd`、
  `EXRSDKVersion=3.41.0`、`CFBundleSupportedPlatforms=['iPhoneSimulator']`、`UIDeviceFamily=[1,2]`、
  `MinimumOSVersion=15.0`；但只有可执行文件的 linker ad-hoc 签名，没有 `_CodeSignature/CodeResources`，
  故 `bundle_sealed=false`、`signature.verify` 记 pending，`signing.established=false`。

## 7. 重跑

`workflow_dispatch` 输入：`producer_run_id`、`producer_sha`、`producer_artifact_iphone`、
`producer_artifact_ipad`、`producer_workflow`。指定一个成功 run 的原 artifact 后，
同一 workflow 会重新认证 ZIP 字节并走 `producer` 模式；只有两类设备的安装清单与真实启动都通过才可能授予。

外部 ZIP 消费者：`producer_source.py --zip <path> --expect-digest sha256:... --expect-bytes N`，
无 run 认证时 `blocked_by=['producer_run_not_authenticated']`，只能是 diagnostic。
