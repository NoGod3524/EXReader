# C PR33 baseline measurement
结论：**3 条 workflow 成功，1 条失败**；仅基线测量，不作为 C 文档验收，不授予 v1/v2 分数。

## Identity
- PR: https://github.com/NoGod3524/EXReader/pull/33 ，2026-11-03 21:05 UTC 查询为 open / draft / unmerged。
- PR head/source: 1761386d966ffdcbbeccaf25e68b184706cf9b8f，codex/governance-to-ledger-20261103。
- Base: ledger/base-20261103 @342780237eb013350bff20c21bc92c335422526a。
- C 仅新增9个文档/证据文件，1400行，无源码或workflow变更。总SDK3.42.0，版本同号不同源见该base的docs/VERSION-LINES.md。
- 本证据位于独立分支 codex/c-pr33-baseline-evidence-20261103，不追加到PRhead，避免synchronize再触发。
- 以下4次均event=pull_request，attempt=1，created_at=2026-11-03T20:41:32Z。21:05 UTC只读查询均completed，未重跑。

| workflow | run | conclusion | terminal updated_at UTC |
|---|---|---|---|
| bounded-library.yml | [41714890432](https://github.com/NoGod3524/EXReader/actions/runs/41714890432) | success | 20:48:08 |
| native.yml | [41714890473](https://github.com/NoGod3524/EXReader/actions/runs/41714890473) | failure | 20:53:21 |
| reading-core.yml | [41714890813](https://github.com/NoGod3524/EXReader/actions/runs/41714890813) | success | 20:43:57 |
| sdk-version-consistency.yml | [41714890397](https://github.com/NoGod3524/EXReader/actions/runs/41714890397) | success | 20:42:49 |

reading-required.yml的PR过滤仅codex/framework，不响应本次ledger/base目标。不能把这些结果写成reading-required通过。
本次按owner授权称framework基线测量，实际测试的source与base以上述SHA为准，不是当前默认分支整树验收。

## Native jobs
| job | ID | result |
|---|---|---|
| android | 126192203526 | success |
| fuzz | 126192203640 | success |
| sanitizers | 126192203706 | success |
| desktop windows-latest | 126192203761 | failure |
| desktop macos-15 | 126192203882 | failure |
| desktop ubuntu-22.04 | 126192203992 | success |
| apple-mobile | 126192204206 | failure |

失败step与GitHub annotation原文：
- Windows step17: Package and check the Windows reference reader。Process completed with exit code 1. 警告列出build/windows-host下ZIP/report/build/page/application.log未找到。
- macOS step22: Build and run Swift host against installed SDK。Process completed with exit code 1. 警告列出EXReader-macOS.zip/apple-host build.json/apple-host-evidence未找到。
- apple-mobile step4: Build and run the iPhone and iPad reference host。Process completed with exit code 1. 警告列出iOS ipa/device+simulator build.json/iphone+ipad evidence未找到。
上述是步骤与注释证据，不据此推断完整根因。没有下载/解包工件或运行本地测试；红保留，不弱化断言，不修改P或其他writer。

## Native artifact identity
21:05 UTC API观测以下13件均expired=false，expires_at均2027-02-01T20:41:33Z。这里只记录身份与保留期，不代表内容复验或失败host完整交付。

| artifact | id |
|---|---|
| diagnostics-Windows | 13270695733 |
| sanitizer-native-tests | 13270685605 |
| EXReader-WP6-Windows | 13270545233 |
| EXReader-conversion-Windows | 13270491171 |
| EXReader-conversion-macOS | 13270312269 |
| diagnostics-macOS | 13270267340 |
| reliability-native-smoke | 13269881963 |
| EXReader-WP6-Linux | 13269737210 |
| EXReader-conversion-Linux | 13269094251 |
| EXReader-WP6-macOS | 13268933998 |
| EXReader-C-Linux | 13268859714 |
| EXReader-performance-Linux | 13268824667 |
| EXReader-C-Android-arm64 | 13268483897 |

## Boundary
未merge PR、未改默认分支/Settings/catalog状态、未触他人分支、未重跑。此记录只涉及PR33，不替代或断言PR31的事实。
