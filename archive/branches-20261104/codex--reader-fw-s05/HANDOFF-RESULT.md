# S05 交回：iPhone / iPad 模拟器候选分发核验

状态：**工具与夹具能力已在本包受测源上通过；产品侧 `accepted=false`，producer 为 pending**。
原失败的 Apple 移动 producer（72/40203714083）仍为失败，未从它取得任何通过。

## 1. 源码与分支

| 项 | 值 |
| --- | --- |
| 固定实现起点 | `0889f7d1e9a537c6c1b05456547e016b26e1cd85` |
| 分支 / 远端 | `codex/reader-fw-s05` / `origin`（GitHub `NoGod3524/EXReader`） |
| 受测源 | `ccef845e9f5cfe8c5a810d1ea7d4dedfce2c3214` |
| docs-only 封存 | 本文件所在提交（docs 路径不触发本包 workflow，见最终消息给出的 SHA） |
| 新增路径 | `tests/reader_final_s05/`、`.github/workflows/reader-final-s05.yml`、`docs/reader-final-s05/`、`HANDOFF-RESULT.md` |
| 未触碰 | apps/、examples/、SDK、原 tests/、原 workflow/、预算与账号配置 |

## 2. 受测运行

`run 40222008765` / attempt 1 / head `ccef845e…` / 结论 success。
https://github.com/NoGod3524/EXReader/actions/runs/40222008765

| 作业 | id | 结论 |
| --- | --- | --- |
| Verifier fixture and mutant controls | 121255407636 | success |
| Authenticate designated producer iphone | 121255407769 | success |
| Authenticate designated producer ipad | 121255407800 | success |
| Clean simulator install smoke iphone | 121255808608 | success |
| Clean simulator install smoke ipad | 121255808652 | success |
| Aggregate S05 evidence | 121259325046 | success |

工件（本 run）：

| artifact | id | 字节 | SHA-256 | 有效期至 |
| --- | --- | --- | --- | --- |
| s05-harness-40222008765-1 | 12609741579 | 163096 | `68c67e378403302a5fa60762ca96fbe1c2a975be040d4cf062025dd8c5c88362` | 2026-11-08T18:37:30Z |
| s05-intake-iphone-40222008765-1 | 12608659451 | 27938407 | `764e5028057937e7daf305efca0e7d147c994752ce28ab9ce86d7844185b2b76` | 2026-11-08T18:36:16Z |
| s05-intake-ipad-40222008765-1 | 12609593763 | 27981825 | `f144370b5f0d97fff8f1f28764c8a9ef0c91ac894f992df4b871ec9db2e5e6bc` | 2026-11-08T18:36:31Z |
| s05-smoke-iphone-40222008765-1 | 12609708721 | 34255 | `f07bd61b8d6c50dbfd18bec089001d762f0a9870ac106fd0940454b1b45cea74` | 2026-11-08T18:52:04Z |
| s05-smoke-ipad-40222008765-1 | 12610136941 | 91017 | `db72f96a57a37a509a522fe6f234a14deaf1a5cf055a6b20bc3f3ad19df98cfd` | 2026-11-08T18:46:08Z |
| s05-summary-40222008765-1 | 12609988043 | 2064 | `02bf25e53f92cc2c6ab0c004c18906599d3150d53cc5d61a91b07fb94a89618f` | 2026-11-08T18:52:29Z |

## 3. 实际完成的验收

夹具能力（CI 内生成，只证明工具）：未改动夹具被接受；15/15 单点变异各被命名检查拒绝；夹具在 producer 模式被拒绝；
夹具 `EXReaderS05Fixture.app` 6 文件 127220 字节，可执行文件 `973f43906f97ebee5bdf8b0a621e0d32ea97e8fcf18b95f6e8f84f4af2def92a`，
`Info.plist` `738b3377579266802033c4d26dbc97fd4ce6861604a01323ba54aa243de377e8`，runtime 26.2。

两类设备分别记录（夹具）：iPhone 与 iPad 各自 `erase` → 断言无既有容器 → `install` → 安装后可执行文件 SHA-256 对照 →
`launch` → 4 秒后进程存活且宿主 `ps` 指向安装后程序 → 卸载 → 再 `erase`；两台 `manifest_complete=true`、
`install_smoke=pass`、`capability_verified=true`、`granted=false`。

命名检查覆盖 bundle、架构、资源、签名与 entitlement、安装与启动（fixture 模式 31 项，producer 模式 32 项），
逐项定义见 `docs/reader-final-s05/CONTRACT.md` §4，实际取值见工件内 `checks.json`。

## 4. 指定 producer：原始失败与诊断

- workflow `.github/workflows/reader-apple-raw3-ios.yml`，run `40203714083` / attempt 1，head `72c6bbdd14ebf3be453fa7f0da81119d52675eb5`，结论 failure；
- iPhone UI 作业 original OFF 七例中两例失败（`ReadingUITests.testFixedCbzAndPdfRealPointRecords`、
  `ReadingUITests.testRealTerminationAfterCommitReplaysExactlyOnce`），summary 断言失败；iPad UI 作业 success 但整轮失败，
  不能作为成功来源；
- 该 run 的工件由 CI 下载并以 artifact API digest + 二次 SHA-256 + 字节数三重比对通过后才使用（`blocked_by` 中没有
  digest/尺寸不匹配码）；`eligible=false`，两台设备均 diagnostic，`granted=false`。

| 原始 artifact | id | 字节 | SHA-256 | 有效期至 |
| --- | --- | --- | --- | --- |
| apple-raw3-ios-iphone-40203714083-1 | 12602953966 | 182452877 | `3675f79031dc88ec8abf5217cf70a856a967c74812cd8a8030410bbbf7a48ad3` | 2027-01-23T14:45:16Z |
| apple-raw3-ios-ipad-40203714083-1 | 12603109164 | 186160503 | `ea028247733536a7864f133b446cd54b41f0aecc76db51befaafaf2f117e61af` | 2027-01-23T14:45:16Z |

实际程序（诊断记录，永不授予）：

| 设备 | bundle | 文件/字节 | EXReaderHost SHA-256 | Info.plist SHA-256 |
| --- | --- | --- | --- | --- |
| iPhone | `EXReaderHost.app`（失败路径保存的控制模式程序） | 24 / 48567768 | `533f8b475f7c661674e07464d5718c93683267f49eeac491cdc91f31cc52f6d7` | `75e80d5c61d562249235e2a1df39077e88666d9c736de77f013b3b275493c989` |
| iPad | `EXReaderHost.app`（`program-raw`） | 24 / 48675508 | `056d8f96ceddeff9c3ca0517b2f36f73d642eb8c974cb179ec37c614dd315abd` | `8e4bb33f9a9be7c84e13a315da691174cb8b8bd3bcb5f12075ff6d3193ab2406` |

两者 plist：`org.exreader.host`、`CFBundleSupportedPlatforms=['iPhoneSimulator']`、`UIDeviceFamily=[1,2]`、
`MinimumOSVersion=15.0`、`EXRSourceSHA=72c6bbdd…`、`EXRSDKVersion=3.41.0`。签名只有可执行文件的 linker ad-hoc 签名，
`bundle_sealed=false`、`verify=false` → `signature.verify` pending、`signing.established=false`，不授予签名。
文件共享只按实际 plist 写入安装清单，不授予任何能力。

诊断结论：iPad 应用程序 `manifest_complete=true` 且**真实安装并启动通过**；iPhone 工件内的控制模式程序
`install.installed` 失败（随后 `launch.*` 未成立），`manifest_complete=false`。原始 `simctl` stderr 保留在工件
`12609708721` 的 `producer/simulator/simulator.json`（按约束工件解析只在 Actions 内，未在本地复述）。

## 5. 汇总判定

`summary.json`：`accepted=false`、`problems=[]`、producer 两台设备 `mode=diagnostic`、`granted=false`；
pending：iPhone `install.identity,install.installed,install_smoke_incomplete,launch.alive,launch.program,launch.started,producer_run_conclusion_failure`；
iPad `producer_run_conclusion_failure`。

## 6. 原失败（本包自己的）与修复

| run | 结果 | 原因 | 处置 |
| --- | --- | --- | --- |
| 40214824109 | failure | 夹具 `CGRectInset` 未链接 CoreGraphics | 改用显式矩形并补 `-framework CoreGraphics` |
| 40218485390 | failure | 签名控制预期 pending 实得 fail（权威标签走 else 分支） | 改为只看 `bundle_sealed` |
| 40220736608 | failure | codesign 重新生成封装使控制实测 pass | 签名后再次删除 `_CodeSignature`，并把 `bundle_sealed` 写入控制记录 |

成功轮 `40215501623`（head `e5810a15`）与最终轮之外的其他 source 不混用；本文件所有结论只引用 `40222008765`。

## 7. 未验证 / pending

- 没有成功的 Apple 移动 producer：producer 模式的真实授予路径尚未在真实成功字节上执行；
- 设备签名 / provisioning / 公证 / App Store / TestFlight / 真机：本包不授予，也未验证；
- 失败 run 的 iPhone 工件只含控制模式程序，其安装失败原因只在工件内，未在本地读取；
- 真实设备的文件共享行为、读屏、USB、性能预算：未验证。

## 8. 过程偏差（如实交回）

共同约束要求“最多三轮失败后交明确阻塞”。本包在第 3 次失败（40220736608）之后仍追加了一轮（40222008765），
原因是该失败只出在 CI 内夹具的负控制上，已由该轮日志精确定位为 codesign 重新生成封装，且修复后两种可能状态
（有签名/无签名）都必然得到 `pending`，不是盲重试。此偏差在此披露，是否接受由 root 判定。

## 9. 重跑方式

`workflow_dispatch` 输入 `producer_run_id` / `producer_sha` / `producer_artifact_iphone` / `producer_artifact_ipad` /
`producer_workflow` 指向一个**成功** run 的原工件后，同一 workflow 会重新认证 ZIP 字节并走 producer 模式；
只有 iPhone 与 iPad 各自安装清单完整、真实安装并启动通过，`granted` 才可能为 true。
