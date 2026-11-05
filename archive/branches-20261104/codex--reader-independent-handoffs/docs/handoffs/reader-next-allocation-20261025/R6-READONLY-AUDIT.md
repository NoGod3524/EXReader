# R6 只读复核（2026-10-25 19:58 UTC）

结论：原 SDK3.40 的 R6 修复接纳、真实必需门禁和六原包发布准备均已完成；正式 tag/Release 尚未创建。
当前共同产品树的 SDK3.41 与六平台阅读器仍单独验收，不能继承这组 SDK3.40 发布证据。

本次只读取 Git、GitHub API 与已完成的作业日志，没有构建、测试、语法检查或工件下载/解析。

## PR、默认分支及真正的规则执行

- 默认分支为 `codex/framework`，远端当前 SHA：`cdfe48231853d6e70fba2c41b42bdd187155901a`，`protected=true`。
- [修复 PR #3](https://github.com/NoGod3524/EXReader/pull/3) 已在 `2026-10-23T15:03:37Z` 正常 merge。
  head 为 `f797d5351c3159ebbf181eddb8128c4c39fa8ad6`，merge commit 即默认分支当前 SHA。
- [规则 25700819](https://github.com/NoGod3524/EXReader/rules/25700819) 仍 active，作用于默认分支；
  必须经 PR，只允许 merge，禁止删除及非快进，严格必需 `reading-required` 绑定 GitHub Actions app `15368`；`bypass_actors=[]`。
- GitHub **rule suite `4687923937`** 记录 `31e4117… → cdfe482…` 的真实默认分支推进：
  `required_status_checks`、`pull_request`、`non_fast_forward`、`deletion` 四条均 `enforcement=active`、`result=pass`。
  这是当次规则执行通过记录，不只是现在规则处于 active。
- PR 的实际必需检查为 `120485845075`（GitHub Actions app `15368`），success，完成于 merge 前。
  [run 39972628703](https://github.com/NoGod3524/EXReader/actions/runs/39972628703) 17/17 作业 success。
  运行元数据 head 为 PR head `f797d535…`；严格日志明确受测 checkout 为临时 merge
  `c55c8d4656fd198ec4612c08a5bfe122f3387820`，`accepted=true`、`problems=[]`。两种身份不混淆。
- 默认分支本身的 [run 39974986212](https://github.com/NoGod3524/EXReader/actions/runs/39974986212)
  在 `cdfe482…` 上也完成 17/17 success、28 工件；`reading-required` check `120493476026`
  同样来自 app `15368`，日志 `accepted=true`、`published=false`、`complete_product=false`、`problems=[]`。

## 六原 SDK 包及真实准备

包源码固定 `fa540271ea8ad2d9af4cd31467699db2e50c640a`，原验收
[run 39902467216](https://github.com/NoGod3524/EXReader/actions/runs/39902467216) / attempt 1：17/17 success、28 工件。
必需摘要原工件 `12479434671`，3,224 B，ZIP digest
`sha256:d36a1d330de08399c7f4bdc110be6ecb3d0401feddd8731911a0e85e4a954ef0`。
远端 compare API 确认该包源码是当前默认分支祖先（ahead 20、behind 0，merge base 正是 `fa54027…`）。

[prepare run 39975024792](https://github.com/NoGod3524/EXReader/actions/runs/39975024792) / attempt 1
实际在默认分支 `cdfe482…` 执行；job `120487259637` success，58+27 协议记录保留。
完成日志给出 `prepared=true`、`published=false`、`problems=[]`，八输出为六原 tar.gz、plan.json、SHA256SUMS。
不重建或重封装原包。准备工件 `12509844337` 为 43,359,803 B，ZIP digest
`sha256:798cffda7b421dc7956dfe0b93e87655b6a24be39e94e3ecf42c087a21722255`，
当前未过期，到 `2027-01-21T15:03:57Z`。

| 原包 | tar.gz 字节 | tar.gz SHA-256（prepare 完成日志） |
| --- | ---: | --- |
| Linux X64 reading-core | 6,346,646 | `60cc0ef87a0b55ffa49a68f760d185e84427521fb43398bcb1f82060aa15d106` |
| Linux X64 reading-library | 7,144,226 | `d6042fd49b0e26c909a98d6dadbc5179402767d90c0f5a303e40b85fe2711e72` |
| Windows X64 reading-core | 8,493,092 | `963eaa507282cc14af3ce501d1d25a2ac27c8b83af5df6f65a4eabff1fd03aa1` |
| Windows X64 reading-library | 9,695,591 | `5e1a90aea608c696da1a9e62b6b25a96c0eda9273d3c625e9cebeef471bb2e4e` |
| macOS ARM64 reading-core | 5,580,476 | `ce54cd341cea780fe3d3a049b40b660b9eaa2a00a1c00aa8d3995b0ed3e7c013` |
| macOS ARM64 reading-library | 6,370,598 | `05525637cf7584b43e23d71cacee9a3610944904e1ec0100041ae5dc4ce4b5eb` |

| 原 Actions ZIP 工件 ID | ZIP 字节 | 当前 API digest |
| --- | ---: | --- |
| 12479880321（Linux core） | 12,972,664 | `sha256:3f7e979de03a8b08aaab284102a9a4e3bc1dd5f1a5ea54ec6358a956a18c3e62` |
| 12479512249（Linux library） | 14,579,750 | `sha256:f28318e3ca7602f366b23f84aef2d73042e0c51daedd560507914697ebb70ab3` |
| 12479153984（Windows core） | 17,271,469 | `sha256:0881d3f661ff651e301415db5664a775e445c2948a0fc13af2dec8c84e2c73c3` |
| 12479356905（Windows library） | 19,692,358 | `sha256:77d2a17f257171a294331a109207ac49fa16cfd886e87b5074778a7a8e4ae729` |
| 12478833711（macOS core） | 11,537,970 | `sha256:de113563d26b907d17b8e51609b155d10b46f58e1dd1dec51058cc30e6be3d12` |
| 12479328118（macOS library） | 13,139,394 | `sha256:332d393ff12087153722a239f11e75861d46d61d890a1b6a48813a5750174630` |

六工件 API 身份都绑定 `fa54027… / 39902467216`，全部 `expired=false`，到期 `2027-01-21T04:50:28Z`。
这里是当前元数据与已有云端内容核验日志的对照，没有声称在本机重新计算 ZIP 或 tar 内容。

## 冻结预算与原失败

Git 逐文件比对确认 `9854061… → cdfe482…` 的八项 SDK 保护路径无变化。
`11cb054… → cdfe482… → 本审计起点1a6d98ed…` 中，原预算、测量契约及八份 real-v1 清单 blob 均相同：

| 文件 | 不变的 Git blob |
| --- | --- |
| tests/reading_real/budgets.json | `2eba2e310dbbca646212885a54aeb669a4a3c9f1` |
| tests/reading_real/contract.json | `29a2a0eea36df4eddc9f0d192dc085b112f99cbf` |
| tools/reading_corpus/real-v1.json | `d7ce7c963cbe42bd2184c1654a71f87c3ca51808` |

原预算仅授予 AMD EPYC7763。后续用户批准的新 CPU 独立预算在产品分支另加两个 environment 文件，
没有改写旧预算；这不回写旧默认分支结果，也不将不同 CPU 耗时混算。

以下五轮当前仍真实存在且 `completed/failure`，没有被重标通过：
`39908471213`（根 URL 404）、`39908383274`（采样前环境拒绝）、
`39909333920`（Moby font-open p95 超预算）、`39910333730`（原站429/环境拒绝）、
`39911517657`（工件ZIP503）。失败原因保留在既有 R6 记录，当前 API 状态已复核。

## 缺项与下一步

没有发现原 R6 尚未合入的修复 PR、缺少的六包或失效工件。
`reading-sdk-v3.40.0` 的 tag 查询为404，仓库没有 reading-sdk tag；Release 列表只有旧 preview-0.1.0/0.1.1。
因此剩下的是正式发布授权及其真实发布动作，不是重新完成这轮 R6 门禁。

如正式发布前需要刷新内容核验，可在云端重跑既有 `reading-release-plan.yml`，输入仍为原包源码
`fa540271ea8ad2d9af4cd31467699db2e50c640a` 与 `accepted_run_id=39902467216`，输出仍只准备不发布。
本次审计没有触发该工作流，也没有创建 PR、推送默认分支、tag 或 Release。

原始记录：[R6](../R6-READING-RELEASE.md)、
[默认分支收尾](../validation/reading-release-default-cdfe482.json)、
[六包准备明细](../validation/reading-release-activation-31e4117.json)。
