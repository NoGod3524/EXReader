# Team24 delivery 阶段封存

本阶段已封存。完整业务候选为 `5527e604d681afd28858c93c3ba19c9f3a569f94`，run [40275945447](https://github.com/NoGod3524/EXReader/actions/runs/40275945447)，attempt `1`，最终 **failure**：五目标在原 S20 范围内通过，Android 3/45；汇总仅报告 `android: target report is not accepted`。不再新增独立包或完整验收。

| 目标 | 本轮结果 | 实际范围 | 同轮原始工件 |
|---|---|---|---|
| Windows | 通过 | fresh 程序/生产清单/依赖校验，原158动作、搜索、目录 | [12630511408](https://github.com/NoGod3524/EXReader/actions/runs/40275945447/artifacts/12630511408) |
| Linux | 通过 | fresh 程序/生产清单/依赖校验，原20项X11与搜索；辅助脚本来自当前候选 | [12629673723](https://github.com/NoGod3524/EXReader/actions/runs/40275945447/artifacts/12629673723) |
| macOS | 通过 | fresh 程序/依赖校验，包体启动自检，同源XCTest broad/search | [12630473564](https://github.com/NoGod3524/EXReader/actions/runs/40275945447/artifacts/12630473564) |
| iPhone | 通过 | 包体真实安装启动自检；同源 broad 13/13、search 4/4 | [12631984572](https://github.com/NoGod3524/EXReader/actions/runs/40275945447/artifacts/12631984572) |
| iPad | 通过 | 包体真实安装启动自检；同源 broad 13/13、search 4/4 | [12631884927](https://github.com/NoGod3524/EXReader/actions/runs/40275945447/artifacts/12631884927) |
| Android | 未通过 | 四feature APK构建、解包、安装成功；原45走查为3 passed/42 failed/0 skipped | [12630259597](https://github.com/NoGod3524/EXReader/actions/runs/40275945447/artifacts/12630259597) |

[同轮汇总索引 12632335985](https://github.com/NoGod3524/EXReader/actions/runs/40275945447/artifacts/12632335985) 内的 `delivery-index.json` 分列六目标 source/run/attempt、SDK、原 ZIP、实际入口及 `entry_sha256`、原始工件 ID/digest 和验收结果。每个目标另保存 `delivery/manifest.json`、`unpack.json`、`target.json`、原 ZIP 与失败证据。GitHub 外层工件 ZIP 摘要不代替原 delivery ZIP 或实际程序摘要。

## 原 ZIP 与程序身份

以下均为 source `5527e604d681afd28858c93c3ba19c9f3a569f94` / run `40275945447` / attempt `1`，SDK `3.41.0`；原 ZIP 字节与摘要取自本轮实际组装日志。

| 原 ZIP | 字节数 | SHA-256 |
|---|---:|---|
| EXReader-windows-5527e604d681.zip | 17372247 | `39b00c087502840ecbad350fee9dc7c6759df440f767c3a09cd27b7551099972` |
| EXReader-linux-5527e604d681.zip | 18265202 | `e0eb089779c2020c1d774d7bd0fe146000474c7bf99e2fed071796604fa84aba` |
| EXReader-macos-5527e604d681.zip | 27005442 | `de7b05845f39ed348a56135e67226d5d2657eb2cc70ee5142102fbe6bf39baaf` |
| EXReader-android-5527e604d681.zip | 72036129 | `65eb0bd43e5cdc283cc89a883331605aab03dbdd879ae4df1db3a97fb061daf2` |
| EXReader-iphone-5527e604d681.zip | 27018569 | `25ad1e9f50c5926d4488474b772901a251c435bf056d51ba93d9bc0de9fd089e` |
| EXReader-ipad-5527e604d681.zip | 27018567 | `498b4c167e5766d145a03bd49cacc7ef3c39438a46f040f66ebbf5c6166ec03f` |

实际程序摘要完整记录在索引 `targets.<target>.entry_sha256`，并与 manifest、unpack、目标报告交叉核验。Android 实际 `artifacts/app-debug.apk` 为 26434070 bytes，SHA-256 `4ec240b971849b3fd8245a724ad6f97b3a996ca9d03d4a67b3947b0b7e68e17e`；其外层工件 digest 为 `e424ca3b9829074d820c9dccf9c475708cacd272f02aa90148b23b3c0d933fe0`，两者分列。

## 失败与尚未授予的范围

Android 首失败 `import_epub`：`AssertionError: import status missing`（36485ms）；随后 `open_epub` 为 `book row not found: Sample.epub`。instrumentation 步骤退出成功没有被当成45项成功；矩阵按逐case结果严格拒绝。该候选保留原标题driver，不包含Android团队后续stem+FORMAT修复或尚未通过的新UI HEAD，本队不越界修改。

Apple 原 `check_apple_host.py` 真实安装/启动解压 ZIP 内的 `EXReader.app` 并自检。原 `make_xcodeproj.rb` 与 XCTest broad/search 另构建同一候选 source 的测试 host，带补充测试资源；XCTest业务结果未绑定为 ZIP 内同一程序摘要。最终组合须保留这个 same-source / same-binary 缺口。

真机、屏幕阅读器人工体验与商店发布未测。尚未组合其他团队的新UI，未授予整个六平台产品完成。

## 来源账本

| 来源 | run / attempt | 授予范围 |
|---|---|---|
| `5527e604d681afd28858c93c3ba19c9f3a569f94` | `40275823343 / 1` | 轻量交付协议通过，业务平台skip |
| 同上 | `40275945447 / 1` | 本队唯一新增完整业务轮，最终failure，结果如上 |
| 同上，错误candidate参数派发 | `40275914140 / 1` | 已取消，guard及业务平台cancelled；保留记录 |
| `680d58156b796f47e71e45878c3cc4d423901005` | `40276021294 / 1` | 仅认证并提取旧63d0c8d2原失败；业务平台skip |
| `685aa1c4c28047e38970c05608ef7a39f18852cf` | `40276629900 / 1` | 轻量协议通过并读取前述现存摘要；未重跑旧GUI |
| `a41bcf2f5ab3a47a079d0f76d238352e3a6e4174` | `40278164857 / 1` | 仅轻量通过；修正ZIP hash/size不符时仍误标verified=true；业务平台skip |

后续报告修正源码不能贴上5527的完整业务通过。新增完整轮只执行1轮，未启动第二轮；本阶段到此封存。

原受测 source `63d0c8d2f032f5c78c77c9f407b17185412e991f` / run `40248648454` / attempt `1` 保留：Windows、Linux、macOS、iPhone过，Android、iPad未过。更早失败 `40245971457`、`40245894358`、`40245766789` 及原 validation 全部保留。

旧iPad `test01ImportDeduplicateAndErrors` 首次断言为 `tests/apple_host/EXReaderHostUITests.swift:390`：`import result must arrive within its original budget`；期望“已导入”，实际“就绪”、book_count=0，trace仅startup/token=0，没有import-start。旧test13通过。原失败细节见 `team24-diagnostics.md` 和 [已认证摘要12630102397](https://github.com/NoGod3524/EXReader/actions/runs/40276021294/artifacts/12630102397)。本轮iPad通过没有删除旧失败，也不代表其根因已修复。

## 复用接口与原独占入口

| 接口 | 已接入用途 | 最终组合条件 |
|---|---|---|
| `assemble.py` / `unpack.py` / `delivery.py` | 真实平台产出、producer build.json source/SDK绑定、manifest/原ZIP/每文件摘要和短安装说明 | root composition guard先登记唯一组合source及SDK/profile依赖 |
| `desktop.py` | Linux零参数启动器，fresh程序/生产清单/运行依赖核验 | 在真实平台Actions执行，再跑业务驱动 |
| `mobile.py` Android adapter | 原builder安装SDK/product后安装六模块，显式启用search/navigation/reading/preferences，保留原build身份 | 保持冻结SDK/NDK，登记extra prefix/profile来源；不代表新UI已过 |
| `diagnostics.py` / `report.py` / `summary.py` | 具名失败、首次断言、45项逐case、严格source/run/attempt/ZIP/程序矩阵 | 使用同轮真实结果；不代替业务验收 |
| 原S20 workflow / `guard.py` | d263固定seed、exclusive write set与冻结SDK/platform判据 | 只授予S20独占来源，未放宽为六队组合入口 |

起点 `c228c51b`，分支 `codex/team24-delivery`。最小合入diff为该起点至本分支：仅 `tools/reader_wave3_package/`、`tests/reader_wave3_s20/`、本队workflow和docs；没有SDK、平台owner、C01策略或其他团队改动。业务接入提交 `5527e604`，旧失败提取 `680d5815`，诊断输出 `685aa1c4`，报告标记修正 `a41bcf2f`，其余为阶段文档。

后续真实产品修复与六队组合交root独立composition；本队不新增独立包、不启动其他模型进程，不创建PR/tag/Release，不写默认分支。
