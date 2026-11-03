# F05 acceptance custody — 2026-11-03

本目录记录用户已接受的 SDK / GTK native recovery 验收。验收 source 为 `8a268b8582903926dfa7198a07fabacb2cacd6fd`，run `41693082728`，attempt `1`。六项均为 `passed`；状态枚举保留 `passed / partial / failed / not-run`。本轮没有 `not-run`；未重跑 dry-run，未修改 catalog 的 state。

artifact 90 天后失效，本目录为长期副本

本目录保存完整 native 证据子树、独立审计结果及关键阶段日志；不是完整 SDK 构建目录的镜像。原始文件按字节复制，下载时已核对两个 ZIP 的完整 SHA-256，并逐件核对 producer inventory。文件来源、原成员名和文件 SHA-256 见 [KEY_EVIDENCE_FILES.json](KEY_EVIDENCE_FILES.json)。本目录全部文件（除校验表自身）的校验值见 [SHA256SUMS](SHA256SUMS)。

## Artifact custody

| 类型 | run id | artifact id | 原始 ZIP SHA-256 |
|---|---|---|---|
| producer | 41693082728 | 13259880666 | `647d2bd6f6af6331cbd57ac30ed160de23e4134a77a8fed10ab1505c3d82440f` |
| independent audit | 41693082728 | 13260346480 | `953409408a75b083485779f870745a98b3b1526be3b32e12abf054b28a3fa6db` |

## native-close-2 判定

`0.000002173999973820173 s` 是最终清理分支确认进程已先行退出的耗时，**未实际执行清理**，不作为实际 close 操作耗时或单独的“cleanup 通过”证据。

判断位置为 [source/gtk.py](source/gtk.py) 第 572 行：`if host.process.poll() is None:`；仅当该子进程仍运行时才在下一行调用 `host.close()`。`devices[2]` 是崩溃恢复后重新启动的 first 实例；其后在同文件第 531 行显式调用 `first.close()`，然后才启动离线读取实例。该调用成功返回，[source/native_runtime.py](source/native_runtime.py) 第 89 行执行 `self.process.wait(...)`，第 90–91 行拒绝非零退出码；最终 cleanup 再检查该已退出实例。

原始数值保留在 [coverage.json](producer/build/f05-gtk-native/coverage.json) 的 `cleanup_timings`，原始审计结论不改写。此前显式 close 的实际耗时没有单独记录，不能用 2.174µs 代替。`native-close-0` 与 `native-close-3` 也属于最终已退出检查；最终仍存活实例的 `native-close-1` 记录为 `0.0781546130000379 s`。

## 会话统计

**restart_offline_read：该 case 无 Sync 会话，不计入 17 次分母。** 其 session/generation 为不适用，不填 0，也不填 not-run。

17 次指五个有 Sync 场景中的 session 启动尝试（包含取消与 kill 边界的两次启动），不是原始采样行数；普通 Sync/Receive trace 为 15 次。17/17 次均最终观察到 `session_present=1` 且 generation 非零；原始瞬态零值仍完整保留。统计及各 case 分母见 [session-sampling-summary.json](session-sampling-summary.json)。

## 关键材料

- [F05_native_final_receipt_20261103.json](F05_native_final_receipt_20261103.json)：原收尾 receipt 原样副本；cleanup 解释以本清单上述澄清为准。
- [coverage.json](producer/build/f05-gtk-native/coverage.json)：六个 case 的逐项结果、断言、请求、session 启动采样和 cleanup 数值。
- [receipt.json](producer/build/f05-gtk-native/receipt.json)：按 case ID 的声明与证据绑定。
- [receive-observations.json](producer/build/f05-gtk-native/receive-observations.json)：15 次 Sync/Receive 的完整相位采样。
- [case-results.json](audit/case-results.json)、[accepted.json](audit/accepted.json)、[audit-result.json](audit/audit-result.json)：独立审计结果。
- [KEY_EVIDENCE_FILES.json](KEY_EVIDENCE_FILES.json)：截图、离线原文、SDK 读回、native wire 与 checkpoint 清单，均附文件 SHA-256。
- [source/accepted.patch](source/accepted.patch)：验收 source 补丁；SHA-256 `dd25d7d76964baabef20f18171640892cba964efd1941494bbcb0c0d463e14a4`。

本次 custody 只追加证据；不修改已验收运行、SDK、catalog state 或测试断言，不触发 CI。F05 会话结束，保存本目录后不再改动该分支。

## 文件 SHA-256

下表覆盖原始与派生文件；MANIFEST.md 自身由 SHA256SUMS 校验，SHA256SUMS 不自校验。

| 仓库目录内相对文件名 | SHA-256 |
|---|---|
| `.gitattributes` | `705fd4d6451a31d36b3df7de96f83f30ac976c9b4a6d1e51671d8e2f33e2d0da` |
| `audit/accepted.json` | `95b059e43fa3f81e6555a21c7bdd4d67de3ab739aa6f868482c57d798afc11e2` |
| `audit/artifacts.json` | `1f3e7f4f5509b6bd3dfc4acae9f0be7ccbcaa5d233c1720b0499d2cf308a1218` |
| `audit/audit-result.json` | `6a1c658662f3d22cc4a526edaae6b9114f70f4cafdc312cc95a970e0553eb8b2` |
| `audit/case-results.json` | `348a1038d079c6863f9731b8cc95c6cb86aaf62a6d81f739e101a2697c449a0b` |
| `audit/jobs.json` | `1414e9031da70af255bf9bdcb08e71a7075a9c2245bb931ac739b2f3e2b27ac2` |
| `audit/receive-observation-accepted.json` | `e03e60f8829de1f446759c80dd738fe09ad25c192f8e6e2566ba29790e94d378` |
| `audit/run.json` | `7096cf957324e382ec38e29722ee99e4beb2bc90e6d7d4fc09d8b7f9c2ac486e` |
| `F05_native_final_receipt_20261103.json` | `dd3a435b678660777b6a18fbbf9c24de0ebc94d2f8ca0ad0a371f0fc4127a815` |
| `KEY_EVIDENCE_FILES.json` | `c75152a279621bd92fcced118f20c1131b8b526828a129a799b8545851048569` |
| `producer/build/f05-gtk/native6.json` | `380189847774db354646875e0ea832b02450096ab4e321a64fb3f9d36f1c66be` |
| `producer/build/f05-gtk/native6.stderr.log` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `producer/build/f05-gtk/native6.stdout.log` | `d494ca7813f806ec643675de492fa6d8c53521b50949b9adf6a703854df82312` |
| `producer/build/f05-gtk/observation-controls.json` | `de862290a57e01fe49b723d7f326732b20d945b92ae7c65988e00edec18ddcf7` |
| `producer/build/f05-gtk-native/cancel_sync_retry.png` | `917f116f428638f2e11c5a6fb08aa8f12efccadf67c320f6ece5dcbbbdaee738` |
| `producer/build/f05-gtk-native/concurrent_heads_preserved.png` | `902fe347cdad4729f0edda6f97192bcc2e5926bcf6b8c09f3785d87dab7b08f4` |
| `producer/build/f05-gtk-native/coverage.json` | `5fa7429b050f4772597eda72375030d471151d72f7d3be81fea8b8618c649c1a` |
| `producer/build/f05-gtk-native/delete-detail-first.png` | `5de503f937c96f708fb1f47d34b41bead1194364117729a1c22928ad36740fe0` |
| `producer/build/f05-gtk-native/delete-detail-second.png` | `740dfc0fb4602361fc79328dccdc76f1007b41f485f132849e751f462674ec34` |
| `producer/build/f05-gtk-native/delete_put_tombstone_preserved.png` | `f8a71b5cd976651e32ae4d15198ff40f7e06ea8c03fc666b3bca3fa9c301f9ee` |
| `producer/build/f05-gtk-native/F05.txt` | `e84518a2213f85c2062fdad4033a44e05834f46ca4b518aa82ce804cdbc65436` |
| `producer/build/f05-gtk-native/kill_commit_ack_replay.png` | `b5dd5ea1c9f198dbf5582d742743140b4be2bb7a2ed04c2ba616f04f77d73c6b` |
| `producer/build/f05-gtk-native/offline-reader.png` | `7b04b35f8a1506b10ba18a71fc9fde173bdcf83278e820e2a952ca33af30634b` |
| `producer/build/f05-gtk-native/offline-sdk-original.bin` | `e84518a2213f85c2062fdad4033a44e05834f46ca4b518aa82ce804cdbc65436` |
| `producer/build/f05-gtk-native/offline-sdk-readback.log` | `8703e14fee94d047434be4d09cc84b9016a793191121ce4670109f9ae88eef42` |
| `producer/build/f05-gtk-native/offline_reconnect.png` | `a0cda3664b5b0f58a8c4bca472007c21bdbedec29abc30acd880867b66c2463c` |
| `producer/build/f05-gtk-native/peer-baseline/0.body` | `e84518a2213f85c2062fdad4033a44e05834f46ca4b518aa82ce804cdbc65436` |
| `producer/build/f05-gtk-native/peer-baseline/1.body` | `42bd13c9c9e99d55d0057264a5d104eed36809002418fcecf2f03259609e3697` |
| `producer/build/f05-gtk-native/peer-baseline/2.body` | `924f8f8e4061ef36d6150e5af1ea4e2f36a4b513df2ecaad771ac60f30573be8` |
| `producer/build/f05-gtk-native/peer-baseline/3.body` | `834026505da8c39661965faddb7a8f434346bae5562f624c8f171a9da541fc70` |
| `producer/build/f05-gtk-native/peer-baseline/4.body` | `799473381faa748a37937cac4462d44809325a201d51d6282b04d03189a628f6` |
| `producer/build/f05-gtk-native/peer-baseline/manifest.json` | `52c2154b22e7a5ee276d400c29236758397cc53f4e1d27a6143b88e52603041d` |
| `producer/build/f05-gtk-native/peer-contract.json` | `eaf05de74a160830b3f15f94ecdd6c8acaa18266523e63b3ae996cca48a72e18` |
| `producer/build/f05-gtk-native/peer-delete/0.body` | `e84518a2213f85c2062fdad4033a44e05834f46ca4b518aa82ce804cdbc65436` |
| `producer/build/f05-gtk-native/peer-delete/1.body` | `42bd13c9c9e99d55d0057264a5d104eed36809002418fcecf2f03259609e3697` |
| `producer/build/f05-gtk-native/peer-delete/2.body` | `924f8f8e4061ef36d6150e5af1ea4e2f36a4b513df2ecaad771ac60f30573be8` |
| `producer/build/f05-gtk-native/peer-delete/3.body` | `834026505da8c39661965faddb7a8f434346bae5562f624c8f171a9da541fc70` |
| `producer/build/f05-gtk-native/peer-delete/4.body` | `799473381faa748a37937cac4462d44809325a201d51d6282b04d03189a628f6` |
| `producer/build/f05-gtk-native/peer-delete/5.body` | `ef071cdacf10e9c152b1ef6165c88a83e648f067eba1ad50d9923e5be3b2ded3` |
| `producer/build/f05-gtk-native/peer-delete/manifest.json` | `757ccd0109bd6cc0b6982052e0f6f71b91a7e56031c5b118c329b28c150e5c35` |
| `producer/build/f05-gtk-native/peer-delete-put/0.body` | `e84518a2213f85c2062fdad4033a44e05834f46ca4b518aa82ce804cdbc65436` |
| `producer/build/f05-gtk-native/peer-delete-put/1.body` | `42bd13c9c9e99d55d0057264a5d104eed36809002418fcecf2f03259609e3697` |
| `producer/build/f05-gtk-native/peer-delete-put/2.body` | `924f8f8e4061ef36d6150e5af1ea4e2f36a4b513df2ecaad771ac60f30573be8` |
| `producer/build/f05-gtk-native/peer-delete-put/3.body` | `834026505da8c39661965faddb7a8f434346bae5562f624c8f171a9da541fc70` |
| `producer/build/f05-gtk-native/peer-delete-put/4.body` | `799473381faa748a37937cac4462d44809325a201d51d6282b04d03189a628f6` |
| `producer/build/f05-gtk-native/peer-delete-put/5.body` | `2d58a6de8a94ca647c7d1dbeb8fd62445c27a73bbbb7393abb4ae895bb9f2856` |
| `producer/build/f05-gtk-native/peer-delete-put/6.body` | `ef071cdacf10e9c152b1ef6165c88a83e648f067eba1ad50d9923e5be3b2ded3` |
| `producer/build/f05-gtk-native/peer-delete-put/manifest.json` | `59cd03c79552a07e09b391748c2ba7a80ac8c4f1d45af39cab958e69a3ad4be2` |
| `producer/build/f05-gtk-native/program.bin` | `3a357139a7782dcda9bb8b38f455cbb77b5605066de578bcb1aaf3f6c848dd2e` |
| `producer/build/f05-gtk-native/receipt.json` | `ac6461ce659d5480f11d2b2f11945f11c193731ddca9640e3a0e0739abe9a2b4` |
| `producer/build/f05-gtk-native/receive-observations.json` | `976c9a7d2cb643ed2cc1031e1c6e6312f4804e1e0c6feaa1499fea846f12ad52` |
| `producer/build/f05-gtk-native/sync-first-1432.png` | `494d9c22528daf46b2db242ecf7072a6357f431e83a78b9977ff8027baa86791` |
| `producer/build/f05-gtk-native/sync-first-1959.png` | `fe5d3b6ef4d027d02ccc5de9cf324ebc58b8e11e69a9b9ad036013f1e5a93095` |
| `producer/build/f05-gtk-native/sync-first-272.png` | `4f6c03a28c2425701acf0b749186d899dbd1fe349b8717da61f5e7c49b437600` |
| `producer/build/f05-gtk-native/sync-first-2758.png` | `633401c7b02b16bd4f47b7301aba5b098720fe8bac1c05602cc1fe3bbd6e0ff3` |
| `producer/build/f05-gtk-native/sync-first-3282.png` | `244fc0b32f415d2c202cec34774adda3194ba31b172f7f26e91e02ed3f3beae0` |
| `producer/build/f05-gtk-native/sync-first-3559.png` | `26825c67335f8e1b3d2df7fd7eb20c37d31f8098a754deae76f41bb51bc15f94` |
| `producer/build/f05-gtk-native/sync-first-4101.png` | `43108e81ed132d5baed6a8da6c296c464eb884b06a93ad41408677f1b19cfac3` |
| `producer/build/f05-gtk-native/sync-first-888.png` | `990644a27ebb3bd1b6194f3041fceb9401e31e738afb517340315edcec6dee94` |
| `producer/build/f05-gtk-native/sync-second-1146.png` | `9e6fef68a13174ad2fbaa404eab3757d2e07176b8852882bc3f8b2bf3cac5a6c` |
| `producer/build/f05-gtk-native/sync-second-1691.png` | `e05bcd798f6f8b8ad8e8bfb9d51c80295688c162130b088b062f98e323528222` |
| `producer/build/f05-gtk-native/sync-second-2219.png` | `80f5eb89ea68dad312c24330e5e4b028146992b2fca3101afe33c7ffbd50368d` |
| `producer/build/f05-gtk-native/sync-second-2488.png` | `f49b628e997692e36bfefec99dab8dd1607f06862cfcd1487af84307b360520b` |
| `producer/build/f05-gtk-native/sync-second-3020.png` | `7a14c6a8b00b75e283c75ac8164b90dad5942928d9188de815897ca5975cff89` |
| `producer/build/f05-gtk-native/sync-second-3837.png` | `9cdc2559e6376d7b00c89285b3713657ca6db8b103f0858e375b0af2e4c7fa12` |
| `producer/build/f05-gtk-native/sync-second-616.png` | `87713148958aca1273c735c71851202817f769b2dc2f33bf0ebcf0cfccf2cc09` |
| `producer/inventory.json` | `e5950507c370f569c6659f340c99d53c8a7b14fbfc0a75bdb41ce60a860e4e58` |
| `session-sampling-summary.json` | `16bf95bbb4a959edd80b29f9507ca7c4aa2843b63144ef4ebfd2644b6aa95e66` |
| `source/accepted.patch` | `dd25d7d76964baabef20f18171640892cba964efd1941494bbcb0c0d463e14a4` |
| `source/gtk.py` | `4ece1464470ec35a1694b1985f8d2ec5c7cec318477d23d7be606aae85f72585` |
| `source/native_runtime.py` | `993405ce44f6fd1e41aaed6c2e7dd0ce50c490d34b7bb76685f90326b20ca58b` |
