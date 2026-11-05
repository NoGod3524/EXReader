# 治理启用状态
结论：**待 R 后启用**。

| workflow | C包处理 | 前置 |
|---|---|---|
| ledger-authority.yml | 不复制、不修改、不启用 | R后owner批准，台账/审计依赖和v1冻结规则明确 |
| ledger-evidence-custody.yml | 不复制、不修改、不触发 | R后owner批准，输入提交/retention及范围明确 |

本包采用owner允许的文档标注方案，不声称workflow已有开关。framework缺少原台账/审计依赖，不能将PR#28 workflow直接带入而假称可用。

v1的99/108是历史条目记账，不是95100501整树通过。T1 preview [41697028437](https://github.com/NoGod3524/EXReader/actions/runs/41697028437)出现protected tree及Apple版本错误，结论“不确定”，不意味着B已可行。
native [40081814926](https://github.com/NoGod3524/EXReader/actions/runs/40081814926) @ d66ffa4a、acroform [39844617258](https://github.com/NoGod3524/EXReader/actions/runs/39844617258)与wp5 [39844627315](https://github.com/NoGod3524/EXReader/actions/runs/39844627315) @ 686ce2fe是95100501祖先成功记录，不是当前树通过；“祖先从未绿过”的例外条件未触发。

C的draft PR仅在自动触发范围核清且不超过owner批准的一次native矩阵时创建。该矩阵用于测量framework当前基线，红绿都记证据，不作C文档验收门禁；其它自动workflow不默认为获批。不merge，不改Settings，不切默认。
R阻塞已更正为环境不可复现，详见新增evidence文档。V后候选仍未建立，不用C的docs-only commit代替V候选。

## owner 最新版本边界
总 SDK 为3.41.0，组件版本独立；3.42历史交付证据尚未完成复验，不挪作当前验收。未来refreeze候选为3.43、ABI epoch 1。V仍在独立分支，C不修改其源码。C与V各自仅获批一次native矩阵，不包含其它自动workflow或重复运行。

当前PR受阻：[自动触发只读清单](../../evidence/C-PR-TRIGGERS-20261103.md)确认至少4条无过滤PR workflow，不符合仅一次native预算。C仅提交独立分支，不创建PR。没有新CI结果可记录。

8357eafa28423a7ab93ba08b823af80f01ad1505已由GitHub API核得源码总SDK3.42、core3.40、library3.35；95100501的library为3.34。本地partial缺对象不是全局不存在。源码版本可复核不等于原工件已复验，也不改变owner当前总SDK3.41及组件独立决定。
