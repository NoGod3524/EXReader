# S05 模拟器分发核验证据

本文件只记录一次受测运行的原始事实。测试源 `ccef845e9f5cfe8c5a810d1ea7d4dedfce2c3214`（分支 `codex/reader-fw-s05`），
实现起点 `0889f7d1e9a537c6c1b05456547e016b26e1cd85`。所有构建、夹具生成、模拟器安装与工件下载都发生在 GitHub Actions。

## 1. 受测运行

| 项 | 值 |
| --- | --- |
| workflow | `.github/workflows/reader-final-s05.yml` |
| run / attempt | `40222008765` / 1 |
| head | `ccef845e9f5cfe8c5a810d1ea7d4dedfce2c3214` |
| 结论 | success（六作业全绿） |
| run URL | https://github.com/NoGod3524/EXReader/actions/runs/40222008765 |

| 作业 | id | 结论 |
| --- | --- | --- |
| Verifier fixture and mutant controls | 121255407636 | success |
| Authenticate designated producer iphone | 121255407769 | success |
| Authenticate designated producer ipad | 121255407800 | success |
| Clean simulator install smoke iphone | 121255808608 | success |
| Clean simulator install smoke ipad | 121255808652 | success |
| Aggregate S05 evidence | 121259325046 | success |

### 本次运行工件

| artifact | id | 字节 | SHA-256 | 有效期至 |
| --- | --- | --- | --- | --- |
| s05-harness-40222008765-1 | 12609741579 | 163096 | `68c67e378403302a5fa60762ca96fbe1c2a975be040d4cf062025dd8c5c88362` | 2026-11-08T18:37:30Z |
| s05-intake-iphone-40222008765-1 | 12608659451 | 27938407 | `764e5028057937e7daf305efca0e7d147c994752ce28ab9ce86d7844185b2b76` | 2026-11-08T18:36:16Z |
| s05-intake-ipad-40222008765-1 | 12609593763 | 27981825 | `f144370b5f0d97fff8f1f28764c8a9ef0c91ac894f992df4b871ec9db2e5e6bc` | 2026-11-08T18:36:31Z |
| s05-smoke-iphone-40222008765-1 | 12609708721 | 34255 | `f07bd61b8d6c50dbfd18bec089001d762f0a9870ac106fd0940454b1b45cea74` | 2026-11-08T18:52:04Z |
| s05-smoke-ipad-40222008765-1 | 12610136941 | 91017 | `db72f96a57a37a509a522fe6f234a14deaf1a5cf055a6b20bc3f3ad19df98cfd` | 2026-11-08T18:46:08Z |
| s05-summary-40222008765-1 | 12609988043 | 2064 | `02bf25e53f92cc2c6ab0c004c18906599d3150d53cc5d61a91b07fb94a89618f` | 2026-11-08T18:52:29Z |

每个工件内部是 `install-manifest.json`（逐文件 SHA-256、Info.plist、签名与 entitlement 事实）、
`bundle-manifest.json`、`checks.json`、`simulator/simulator.json`（逐条命令、退出码、安装容器、pid、
宿主 `ps` 与崩溃日志扫描）和 `result.json`。

## 2. 工具能力证明（CI 生成夹具，不是产品）

- 未改动的夹具被接受：`valid_accepted=true`；
- 15 个单点变异全部被命名检查拒绝：`rejected=15/15`，`mismatches=[]`；
- 夹具在 producer 模式下被拒绝：`fixture_cannot_be_producer=true`；
- 夹具身份：`EXReaderS05Fixture.app`，6 文件 127220 字节，可执行文件 `973f43906f97ebee5bdf8b0a621e0d32ea97e8fcf18b95f6e8f84f4af2def92a`，
  `Info.plist` `738b3377579266802033c4d26dbc97fd4ce6861604a01323ba54aa243de377e8`，`EXRSourceSHA=ccef845e…`，
  签名 ad-hoc / `bundle_sealed=true` / `verify=true`；
- 模拟器 runtime：`26.2`。

## 3. 两类设备分别记录（夹具能力）

| 设备类 | manifest_complete | 干净安装+启动 | capability_verified | granted |
| --- | --- | --- | --- | --- |
| iPhone | true | pass | true | false |
| iPad | true | pass | true | false |

两次运行都在安装前 `erase` 并断言无既有容器，安装后对照可执行文件 SHA-256，`simctl launch` 后 4 秒进程仍存活且宿主
`ps` 指向安装后的程序，随后卸载并再次 `erase`。

## 4. 指定 producer（原始失败保留）

- workflow `.github/workflows/reader-apple-raw3-ios.yml`，run `40203714083` / attempt 1，head `72c6bbdd14ebf3be453fa7f0da81119d52675eb5`，结论 **failure**；
- iPhone UI 作业在 original OFF 七例中失败两例（`ReadingUITests.testFixedCbzAndPdfRealPointRecords`、
  `ReadingUITests.testRealTerminationAfterCommitReplaysExactlyOnce`），summary 作业随后断言失败；
- 该 run 的工件被下载、二次哈希并与 artifact API digest 逐字节比对通过后才使用；`blocked_by` 仅含
  `producer_run_conclusion_failure`，未出现 digest/字节数不匹配码；
- 因为 run 未成功，`eligible=false`，两台设备均为 **diagnostic**，`granted=false`。

| 原始 artifact | id | 字节 | SHA-256 | 有效期至 |
| --- | --- | --- | --- | --- |
| apple-raw3-ios-iphone-40203714083-1 | 12602953966 | 182452877 | `3675f79031dc88ec8abf5217cf70a856a967c74812cd8a8030410bbbf7a48ad3` | 2027-01-23T14:45:16Z |
| apple-raw3-ios-ipad-40203714083-1 | 12603109164 | 186160503 | `ea028247733536a7864f133b446cd54b41f0aecc76db51befaafaf2f117e61af` | 2027-01-23T14:45:16Z |
| raw3-ios-sdk-iphonesimulator-40203714083-1（只读记录，未下载） | 12603156296 | 21891156 | `538d6c2888505d6398e1ce7294f8178de0008d0ddee119d969025cb278845cc1` | 2027-01-23T14:45:16Z |
| raw3-ios-sdk-macos-40203714083-1（只读记录，未下载） | 12603310238 | 21887403 | `9d454bb6a9ba9d354562dc5316059b1857277b45ffbf69b74a576fe040dc2150` | 2027-01-23T14:45:16Z |

### 实际程序与安装清单事实

| 设备类 | 选中 bundle | 文件/字节 | 可执行文件 SHA-256 | Info.plist SHA-256 |
| --- | --- | --- | --- | --- |
| iPhone | `EXReaderHost.app`（该失败工件只含控制模式程序，来自失败路径保存的 `failed-program-original-OFF-seven-cases`） | 24 / 48567768 | `533f8b475f7c661674e07464d5718c93683267f49eeac491cdc91f31cc52f6d7` | `75e80d5c61d562249235e2a1df39077e88666d9c736de77f013b3b275493c989` |
| iPad | `EXReaderHost.app`（`program-raw`） | 24 / 48675508 | `056d8f96ceddeff9c3ca0517b2f36f73d642eb8c974cb179ec37c614dd315abd` | `8e4bb33f9a9be7c84e13a315da691174cb8b8bd3bcb5f12075ff6d3193ab2406` |

两者 `Info.plist`：`CFBundleIdentifier=org.exreader.host`、`CFBundleSupportedPlatforms=['iPhoneSimulator']`、
`UIDeviceFamily=[1,2]`、`MinimumOSVersion=15.0`、`EXRSourceSHA=72c6bbdd…`、`EXRSDKVersion=3.41.0`。
签名：只有可执行文件的 linker ad-hoc 签名，`bundle_sealed=false`、`verify=false`，故 `signature.verify` 记 pending、
`signing.established=false`，不授予设备签名。文件共享只按实际 plist 的 `UIFileSharingEnabled` /
`LSSupportsOpeningDocumentsInPlace` 写入安装清单，不据此授予任何设备侧能力。

### 诊断结果（永不授予）

| 设备类 | manifest_complete | 干净安装+启动 | granted | blocked_by |
| --- | --- | --- | --- | --- |
| iPad | true | **pass**（真实安装并启动） | false | `producer_run_conclusion_failure` |
| iPhone | false | **fail**：`install.installed` 失败，随后 `launch.*` 全部未成立 | false | `install.identity`, `install.installed`, `install_smoke_incomplete`, `launch.alive`, `launch.program`, `launch.started`, `producer_run_conclusion_failure` |

iPhone 侧的原始 `simctl install` stderr、容器与启动日志保留在工件 `12609708721` 的
`producer/simulator/simulator.json` 与 `producer/result.json`（按共同约束，工件解析只在 Actions 内进行，
这里不复述未读取的字节）。该工件内的程序来自失败作业的失败路径快照，不是 raw 候选，因此这一项本身也说明
失败的 72 轮无法提供成对的设备候选。

## 5. 汇总判定

`summary.json`（工件 `12609988043`）：

- `accepted=false`；
- `problems=[]`（工具与夹具能力无缺陷）；
- `pending`：iPhone 为 `install.identity,install.installed,install_smoke_incomplete,launch.alive,launch.program,launch.started,producer_run_conclusion_failure`，
  iPad 为 `producer_run_conclusion_failure`。

## 6. 过程记录（含失败轮）

| run | head | 结果 | 原因 |
| --- | --- | --- | --- |
| 40214824109 | `3aaa8ea156af9b4c70772570cfba037b8c38570b` | failure | 夹具链接缺 CoreGraphics（`_CGRectInset` 未定义），工具缺陷，已修 |
| 40215501623 | `e5810a158383ff7dd030930aeaf93826e2edace5` | success | 六作业全绿；随后发现未封装签名的语义需要区分，已被替换 |
| 40218485390 | `f18f63cd74185565482d3514cc83fc113a046a08` | failure | 新增签名控制预期 pending 实得 fail（权威标签使分支走 else），控制夹具缺陷 |
| 40220736608 | `298bb9d269de1c74b904414049bd8e06cc8147bb` | failure | codesign 重新生成封装，控制实测 pass，控制夹具缺陷 |
| 40222008765 | `ccef845e9f5cfe8c5a810d1ea7d4dedfce2c3214` | success | 最终受测运行 |

三轮失败后仍追加了一轮（见 `HANDOFF-RESULT.md` 的“过程偏差”）。
