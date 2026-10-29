# Apple OPDSHash continuation — final handoff

All seven listed runs are terminal. This record supersedes the earlier pending snapshot in this file. Capture: 2026-10-29 23:51:01 UTC (America/New_York is UTC−04 on 2026-10-29).

## Delivered change and actual shared integration

The original common candidate `bd28d4946f17a184dd3cd47a584cf49fce34e973`, run 40937997549, failed because product CMake received no installed OPDSHash prefix. Source `329d676880c9c5f653b48f2ed6179bd1d7f97b28` builds the existing hash-only package first into the independent canonical `<product>/opds-hash` prefix, then passes `READER_ORIGINAL_HASH_PREFIX` to every product configuration and exact-family check. Original target/deployment options, package ownership checks, core source pin, tests, assertions and budgets remain intact.

The shared branch `codex/public-product-resume-20261029`, tested source `343bb94eb6513beaf5b344e7828342f6602a3b7b`, contains the exact same `tools/build_apple_product.py` blob `ee4b55320176df25ac23a04c65c95d2240f7eed1`. Shared source 343 has its own run 40946894035 and its own artifacts below. Its results are recorded separately from 329d.

## Actual results by source

| Scope | 329d / 40946118946 | Shared 343 / 40946894035 |
| --- | --- | --- |
| SDK and installed public modules | Both targets passed | Both targets passed |
| macOS original native cases | 39/39 | 39/39 |
| iPad original native cases | 38/39; annotation preview case failed at fixed 4m | 38/39; annotation preview case failed at fixed 4m |
| iPhone original native cases | 38/39; annotation preview case failed at fixed 4m | **37/39**; annotation preview 4m plus borrowed-font/original-export/snapshot case 3m43s failed |
| Font supplemental | All three platforms passed original 1 case | All three platform jobs passed |
| Original save supplemental | All three platforms passed system save plus byte readback | All three platform jobs passed |
| Organization supplemental | macOS 6/6; iPhone and iPad each 5/6 | macOS job passed; iPhone and iPad each 5/6 |
| Sync supplemental | All three platforms passed original TLS account 3 cases and 401/retry case; pending=1 retained, 256 recovery shards, outbox=0 | All three platform jobs passed their unchanged producer assertions |
| ZIP authentication / full summary | Both failed | Both failed |

Both full runs finished with 13 successful jobs and 6 failed jobs, including their rejecting authentication/summary jobs. Full Apple admission remains failed. Fixed catalog remains 95/108; no catalog entry was changed by this work. All mobile execution here used simulators.

## Organization failure and rejected candidate

Original mobile organization failures are `testGroupLifecycleAndProcessRestart()`. The original iPhone ZIP was authenticated and parsed only inside Actions by runs 40949691344, 40950604140 and 40950854581. Its 375×667 failure tree shows the composite removed-groups Switch at `(16,127,343,31)`, native switch at `(310,127,51,31)`, value 0, and `Missing group Renamed Shelf` at original line 96.

Candidate `9019f94c56245043d68422e6a70948f8fd227e8b` added only `.fixedSize(horizontal: true, vertical: false)` to the product Toggle, with a focused same-source SDK/original-six workflow. Original test files and guards were unchanged. Both SDK jobs passed; the six original iPhone organization tests again finished 5/6, with the same lifecycle failure. Read-only diagnostic run 40958847757 authenticated the candidate's original failed ZIP and found composite frame `(16,127,141.5,31)`, native switch frame `(108.5,127,51,31)`, still value 0. The composite center remained outside the actual native switch. This candidate failed and was **not integrated** into shared 343; shared HostViews blob remains `60c3c11721a915635531a3092fc04f7e1c915edd`, whereas the rejected candidate is `34bdea709423151319de843dd03969a48f1ab4ec`.

## Remaining gaps and evidence limits

- Mobile annotation preview remains failed on both full sources. No helper change was made by this agent.
- Shared 343 iPhone has an additional borrowed-font/original-export/snapshot failure. Its first assertion/xcresult root cause was not parsed here; exact original artifact is 12941146187, 476424539 bytes, SHA-256 `b5037093b8da93b3ff779bead2a0dcc21971f18221f64f7326f236ed80a94b9c`.
- Mobile organization lifecycle remains failed. The compact Toggle hypothesis was disproved by actual execution and frame evidence; no next candidate or new probe was launched.
- Original authentication jobs read and rehashed the five original SDK/native ZIPs, then rejected failed mobile UI scopes. Full-summary jobs rejected failed producers before accepting supplemental ZIPs; this is not a completed independent supplemental audit.
- The failed 9019 supplemental receipt has an empty program receipt set. Its original ZIP retains derived output, but no accepted program identity or successful six-case receipt is claimed.
- Final product gates, physical-device admission and formal catalog adaptation remain unfinished.

Full run/job/artifact identities, byte sizes, SHA-256 values, source identities and native case/program receipts are also in [the machine-readable evidence record](apple-opdshash-resume-20261029-evidence.json). No artifact was downloaded or parsed locally. Local operations were source/Git/documentation/lightweight status only.

## Run register

| Run | Exact source | Terminal result | Jobs | Artifacts |
| --- | --- | --- | --- | --- |
| [40946118946](https://github.com/NoGod3524/EXReader/actions/runs/40946118946) | `329d676880c9c5f653b48f2ed6179bd1d7f97b28` | failure | 19 | 19 |
| [40946894035](https://github.com/NoGod3524/EXReader/actions/runs/40946894035) | `343bb94eb6513beaf5b344e7828342f6602a3b7b` | failure | 19 | 19 |
| [40949691344](https://github.com/NoGod3524/EXReader/actions/runs/40949691344) | `8260439a74d88dd3c05619d1ba09d0d5fe2d0606` | success | 1 | 1 |
| [40950604140](https://github.com/NoGod3524/EXReader/actions/runs/40950604140) | `f545db4955dd5e86445bbe635ca7cb634794af44` | success | 1 | 1 |
| [40950854581](https://github.com/NoGod3524/EXReader/actions/runs/40950854581) | `5b854ea6730526ea18090dee2f4c69de0b1d649e` | success | 1 | 1 |
| [40951570390](https://github.com/NoGod3524/EXReader/actions/runs/40951570390) | `9019f94c56245043d68422e6a70948f8fd227e8b` | failure | 3 | 3 |
| [40958847757](https://github.com/NoGod3524/EXReader/actions/runs/40958847757) | `24646208394d6d4e9ce47457e67c4a2154d6782d` | success | 1 | 1 |

## Run 40946118946

Source `329d676880c9c5f653b48f2ed6179bd1d7f97b28`; attempt 1; branch `codex/apple-opdshash-resume-20261029`.

| Job | Name | Result | Artifact |
| --- | --- | --- | --- |
| 123701801944 | Team24 Apple installed macos | success | 12929766799 |
| 123701802742 | Team24 Apple installed iphonesimulator | success | 12930305403 |
| 123704030848 | Team24 Apple native ipad | failure | 12932122681 |
| 123704030910 | Team24 Apple native iphone | failure | 12933038930 |
| 123704030914 | Team24 Apple native macos | success | 12931448659 |
| 123704030996 | Apple 3.42 font macos | success | 12930580527 |
| 123704031017 | Apple 3.42 original macos | success | 12930278563 |
| 123704031049 | Apple 3.42 organization macos | success | 12928978859 |
| 123704031062 | Apple 3.42 original ipad | success | 12929078862 |
| 123704031082 | Apple 3.42 font iphone | success | 12929909052 |
| 123704031086 | Apple 3.42 organization iphone | failure | 12930980669 |
| 123704031104 | Apple 3.42 original iphone | success | 12930876182 |
| 123704031141 | Apple 3.42 organization ipad | failure | 12936086332 |
| 123704031153 | Apple 3.42 font ipad | success | 12934631632 |
| 123704031158 | Apple 3.42 sync macos | success | 12932622635 |
| 123704031175 | Apple 3.42 sync ipad | success | 12933143717 |
| 123704031240 | Apple 3.42 sync iphone | success | 12936135879 |
| 123735897608 | Team24 Apple original ZIP authentication | failure | 12934210773 |
| 123753169778 | full-host-summary | failure | 12935561654 |

| Artifact | Bytes | SHA-256 |
| --- | --- | --- |
| 12936135879 | 76057018 | `9f462962c5517764ee8eb38c6b71a3339fd6b4c8b188b8b146d7c4b85746fa74` |
| 12936086332 | 169275207 | `75e78580eaecef5a3ad7aa27cffe65b831b28fcf41b67289f7f9530e9eeb7133` |
| 12935561654 | 668 | `4fbed7a9ffd8163fe5a51478522097ee94ac00f183499475ba3b4cda3f7248d3` |
| 12934631632 | 60331415 | `ffc2260d78b86c5e9dba22addf548fc080bf181da3900d52b372858ca4d34880` |
| 12934210773 | 7929 | `f4750502f165d8edc9a784632fa1bb09f359f2f6d25f5bf045719d68c1270b85` |
| 12933143717 | 76850852 | `f14c421f5f6123c404a81755c3a4021c8f7e3a8a45510b05555e11f3c39c1438` |
| 12933038930 | 469110942 | `c317fd0d715cae699efce154a4be1c1fa1571b65b8a2a24802e586b6c7386583` |
| 12932622635 | 73116779 | `79c5565a9373d969a85cdeee45171d254dfdb0d8c266785ac335f151d8e6eba6` |
| 12932122681 | 484871118 | `ec779f4ea022b7c5be247d37ddf2602afb26e7ba4f6b2aa1751bfcb6bff34fea` |
| 12931448659 | 316199083 | `16304575980583922538d255030ce6d837c882f05505dd58319e91698ecd1912` |
| 12930980669 | 121621011 | `6270282a97f22a832e39813a041b931e3c08b8300ff3b77625b374ece35fd84a` |
| 12930876182 | 29154343 | `ad6632b2b2e963aa8576b3a8101487a687b286c864953ebc60a21a231036f340` |
| 12930580527 | 57033144 | `5547e40be2432740b9bae24b39ae15819e278a76e3227bb821fa1d539077b463` |
| 12930305403 | 22469892 | `7928274505e0e9d21e3fe02bc58560afdb4095ddc26e8c42d653b89406be8a26` |
| 12930278563 | 28378209 | `bcfa3f3792ba9ccd3ec69935bc0f78faed41eed14e43720fcabd3dceefef20b3` |
| 12929909052 | 59863193 | `958266fb575c00b97d6c68c4db401c2cb33833ba72501c9e5d8c93e8918ddd12` |
| 12929766799 | 22477134 | `f9669fc902877cc39c3c2f49499ee9b4b16679709dcc885d92f4c14f11228193` |
| 12929078862 | 29365258 | `52be7985a258735cc57841b9a9273d654323f315f4112d50517823a085f834f0` |
| 12928978859 | 47606228 | `d61e5400f985cc48f3be57d1d7447fb945542f11c215b46760efd0a13a8ddfd9` |

## Run 40946894035

Source `343bb94eb6513beaf5b344e7828342f6602a3b7b`; attempt 1; branch `codex/public-product-resume-20261029`.

| Job | Name | Result | Artifact |
| --- | --- | --- | --- |
| 123704514516 | Team24 Apple installed macos | success | 12928954979 |
| 123704514963 | Team24 Apple installed iphonesimulator | success | 12931324076 |
| 123726898120 | Team24 Apple native ipad | failure | 12936482023 |
| 123726898125 | Team24 Apple native macos | success | 12937050856 |
| 123726898296 | Apple 3.42 original iphone | success | 12934479630 |
| 123726898312 | Apple 3.42 organization macos | success | 12937440212 |
| 123726898313 | Apple 3.42 original macos | success | 12935218242 |
| 123726898317 | Apple 3.42 organization iphone | failure | 12937590705 |
| 123726898334 | Apple 3.42 original ipad | success | 12938510021 |
| 123726898357 | Team24 Apple native iphone | failure | 12941146187 |
| 123726898359 | Apple 3.42 font ipad | success | 12936847712 |
| 123726898374 | Apple 3.42 font macos | success | 12937635946 |
| 123726898443 | Apple 3.42 organization ipad | failure | 12938512488 |
| 123726898447 | Apple 3.42 font iphone | success | 12937566633 |
| 123726898550 | Apple 3.42 sync iphone | success | 12937508577 |
| 123726898590 | Apple 3.42 sync ipad | success | 12938900876 |
| 123726898683 | Apple 3.42 sync macos | success | 12939305015 |
| 123791690885 | Team24 Apple original ZIP authentication | failure | 12940917316 |
| 123791980454 | full-host-summary | failure | 12940452865 |

| Artifact | Bytes | SHA-256 |
| --- | --- | --- |
| 12941146187 | 476424539 | `b5037093b8da93b3ff779bead2a0dcc21971f18221f64f7326f236ed80a94b9c` |
| 12940917316 | 8023 | `578b95dc6874636bf9299c419219c669a71bae222eb083f01cd1989f5a3a53a3` |
| 12940452865 | 667 | `8d5612e912d063f26330b94d85030d00c127b24b370ff3a0aa9d0dfeaa582e12` |
| 12939305015 | 73103954 | `7548821ff0cc2ed99e667e73c4067a1a8a53f2b70355938078632eabc4a74579` |
| 12938900876 | 76772545 | `973d1a90d69613eb8ecd3a9f16f0bff6ae507f0625f72c4e954314d0ad386c5e` |
| 12938512488 | 136211180 | `05724fff0dad6b5f1dc6434e4d5762c8393c0c21a2194c8a7df4e882db63509c` |
| 12938510021 | 29522995 | `54650360310d218f605d04b936ab3da31f48ef1e610d029ab66894162e4fb6c2` |
| 12937635946 | 57041770 | `75263c2bd971389e5be92e83c3a5c6a28e827ccb326ac87b761a7c83c873410c` |
| 12937590705 | 119337763 | `50eeb2474c4266008a0cdcc6ee5cdcb67e468010ff4bba674d7d37d26493deff` |
| 12937566633 | 59535676 | `47a13c2358ce76fbf9c780bb31688cb74a85fa7cf878d7b9e52619eeb8925cc5` |
| 12937508577 | 76050719 | `188a4ca818cea34a8c4b15786af3960fac4b673b51ccf711d3d20c49bb224dff` |
| 12937440212 | 47611424 | `f48053a1e272af2cff2e6edc9a34bb0bbd117c2fe9d06020c9d2c07e2512ff50` |
| 12937050856 | 315736669 | `e0298e1b761bfa3a5554af9cbbe10dcdba737557ae61e0196ed32dd9e39fe703` |
| 12936847712 | 60325629 | `aef6dbf53ca06eacae699d695ff9c5d807d3963ba26beed9594605b3542ce249` |
| 12936482023 | 468806185 | `9023080f3de0a0c5838f7337d9ec3cc18fcc751dc49be7d5c01fde2607e823f7` |
| 12935218242 | 28377361 | `443cd07de39967a16f9bdadb89aa35d98cd2a9bfaf9805517953d64fdd7a54d5` |
| 12934479630 | 29183737 | `41211060037055343a8a747a6ceecaebfb82d05deeefd58deeecf86395509e73` |
| 12931324076 | 22470151 | `6ed7e8e80d580867b409d6ba9d5b5a6d22c90060106ecb36e553ecc5cb6e0f63` |
| 12928954979 | 22477614 | `e067f8d81dcd7752a32628f443b92f83c37f791feaf965b0e29573be655f530b` |

## Run 40949691344

Source `8260439a74d88dd3c05619d1ba09d0d5fe2d0606`; attempt 1; branch `codex/apple-organization-diagnose-20261029`.

| Job | Name | Result | Artifact |
| --- | --- | --- | --- |
| 123714206458 | inspect | success | 12933945388 |

| Artifact | Bytes | SHA-256 |
| --- | --- | --- |
| 12933945388 | 114967511 | `71e2857d4253bac79662aa458499a54d05517cf95c64f563f0e5d082eee94ef1` |

## Run 40950604140

Source `f545db4955dd5e86445bbe635ca7cb634794af44`; attempt 1; branch `codex/apple-organization-diagnose-20261029`.

| Job | Name | Result | Artifact |
| --- | --- | --- | --- |
| 123717401251 | inspect | success | 12931835951 |

| Artifact | Bytes | SHA-256 |
| --- | --- | --- |
| 12931835951 | 107807957 | `f191ad0de7525200857235f8db106ef9c4ef52ab13b5cc4b056da775693f5fc3` |

## Run 40950854581

Source `5b854ea6730526ea18090dee2f4c69de0b1d649e`; attempt 1; branch `codex/apple-organization-diagnose-20261029`.

| Job | Name | Result | Artifact |
| --- | --- | --- | --- |
| 123718268256 | inspect | success | 12931361376 |

| Artifact | Bytes | SHA-256 |
| --- | --- | --- |
| 12931361376 | 107807957 | `9a95c133918eb397979ed27f319d694529bf58067e1674c79819812f46af8c20` |

## Run 40951570390

Source `9019f94c56245043d68422e6a70948f8fd227e8b`; attempt 1; branch `codex/apple-organization-toggle-hitarea-20261029`.

| Job | Name | Result | Artifact |
| --- | --- | --- | --- |
| 123720757271 | sdk (macos) | success | see JSON |
| 123720757637 | sdk (iphonesimulator) | success | see JSON |
| 123734021433 | original-six | failure | see JSON |

| Artifact | Bytes | SHA-256 |
| --- | --- | --- |
| 12933684799 | 240212146 | `8dbabafab0f5a1693323d1342ecc2c251131d6eab69db55a047f6260dd0fbb85` |
| 12932882109 | 22476284 | `bad5cbed7517c1cb64d5163598330b170c35d026fef4d3d368d6770b93d7fa8b` |
| 12932354529 | 22468869 | `1dde840a036ddd9a3783111ad7f830dcad26ef2f3e0a902dd73ba391d1112c39` |

## Run 40958847757

Source `24646208394d6d4e9ce47457e67c4a2154d6782d`; attempt 1; branch `codex/apple-organization-diagnose-20261029`.

| Job | Name | Result | Artifact |
| --- | --- | --- | --- |
| 123745998942 | inspect | success | 12935550123 |

| Artifact | Bytes | SHA-256 |
| --- | --- | --- |
| 12935550123 | 118306244 | `b4dd01443a49ec832b8eb496fd1ee13defc4c171bbe737fe9cdb212b8dc5e414` |

## Stop state

All six runs launched by this agent and the separately observed shared 343 run are terminal. This agent stops after the documentation-only `[skip ci]` commit. No new feature, product candidate, probe, default-branch merge, PR, tag or release is started by this handoff.
