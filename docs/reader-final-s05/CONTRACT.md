# S05 iPhone/iPad 模拟器分发核验契约

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

签名与 entitlement：`signature.verify`（已签名必须 `codesign --verify --deep --strict` 通过；
未签名记为 pending，模拟器安装不需要签名，且不授予签名）、`entitlements.parse`、
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

## 7. 重跑

`workflow_dispatch` 输入：`producer_run_id`、`producer_sha`、`producer_artifact_iphone`、
`producer_artifact_ipad`、`producer_workflow`。指定一个成功 run 的原 artifact 后，
同一 workflow 会重新认证 ZIP 字节并走 `producer` 模式；只有两类设备的安装清单与真实启动都通过才可能授予。

外部 ZIP 消费者：`producer_source.py --zip <path> --expect-digest sha256:... --expect-bytes N`，
无 run 认证时 `blocked_by=['producer_run_not_authenticated']`，只能是 diagnostic。
