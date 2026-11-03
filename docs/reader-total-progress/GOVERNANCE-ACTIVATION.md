# 治理启用状态
结论：**待 R 后启用**。

| workflow | C包处理 | 前置 |
|---|---|---|
| ledger-authority.yml | 不复制、不修改、不启用 | R后owner批准，台账/审计依赖和v1冻结规则明确 |
| ledger-evidence-custody.yml | 不复制、不修改、不触发 | R后owner批准，输入提交/retention及范围明确 |

本包采用owner允许的文档标注方案，不声称workflow已有开关。v1归档仍需owner明确执行，state不变。
v1的99/108是历史条目记账，不是95100501整树通过。T1 preview [41697028437](https://github.com/NoGod3524/EXReader/actions/runs/41697028437)出现protected tree及Apple版本错误，结论“不确定”，不意味着B已可行。
native [40081814926](https://github.com/NoGod3524/EXReader/actions/runs/40081814926) @ d66ffa4a、acroform [39844617258](https://github.com/NoGod3524/EXReader/actions/runs/39844617258)与wp5 [39844627315](https://github.com/NoGod3524/EXReader/actions/runs/39844627315) @ 686ce2fe是95100501祖先成功记录，不是当前树通过；“祖先从未绿过”的例外条件未触发。

## 当前落点与授权
C从ledger/base-20261103 @342780237eb013350bff20c21bc92c335422526a建立独占分支codex/governance-to-ledger-20261103，只重放九份治理文档，不合入旧framework源码。旧C @aa753fb9与新base的collect.py冲突通过换基线纯文档重放规避，不修改该源码。
V经PR29于2026-11-03 20:13:53 UTC合入上述base。owner已撤销保持3.41.0，确认总SDK3.42.0，组件独立。
版本身份见 [VERSION-LINES](https://github.com/NoGod3524/EXReader/blob/342780237eb013350bff20c21bc92c335422526a/docs/VERSION-LINES.md)：历史8357eafa与本次V同号不同源；取得源码不等于重验历史F06工件。未来refreeze完成后统一升3.43.0、ABI epoch1，候选需包含P落地后实际变更。

C获准一次四条自动PRworkflow作为framework基线测量（本次实际PR base为ledger/base）；红绿均记录，不作为C文档验收，不重跑、不改断言。不merge、不改Settings、不切默认。
[自动触发清单](../../evidence/C-PR-TRIGGERS-20261103.md)列明四条及过滤差异。开PR后固定head，结果写独立证据分支，避免synchronize额外触发。
R环境可复现性与当时观测见[记录](../../evidence/R-ENVIRONMENT-BLOCKER-20261103.md)。该历史阻塞记录不代表新的环境策略已执行；R须另获owner明确执行。
