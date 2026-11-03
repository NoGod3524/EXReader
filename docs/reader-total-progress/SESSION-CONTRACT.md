# EXReader 会话契约
本文件传播 human owner 于2026-11-03确定的范围，不扩大任何工作包权限。其他会话须各自记录已读版本与分支，不能据本文件存在假称全部已握手。

1. 定位 SDK；受支持示例 = Windows + GTK；其余四目标 build-only，不做产品验收、不进入示例分母。
2. 顺序 3 → 1 → 2；六端阅读器独立项目；F01、F03、F05、F08–F12 的六端产品部分移交，见 deferred 清单。
3. v1 台账只读；任何会话/自动化不得改 catalog.json 的 state。归档已定，但实际改名与 archived 标记仍待单独“执行”，本包不实施。v2 不继承 v1 分数。
4. 进展写 evidence/；本地通过必须标注“Actions 未验”。原失败、断言、预算、not-run 和范围限制不删改。
5. 一个会话一条工作分支；产物写明哪条线、基于哪个 commit、是否需重放。同文件一个 writer，不接管他人树。
6. 默认分支冻结中；无对应授权不得改 Settings / ruleset / codex/framework。C 仅可独立文档分支与 draft PR；合并另需 owner 放行及真实 required checks。

## 当前包及依赖
- V：codex/sdk-version-single-source-20261103，基线95100501；总SDK3.42.0、组件独立版本；3.42历史交付证据尚未完成复验；未来refreeze候选3.43、ABI epoch 1，V已通过PR29合入ledger/base-20261103 @ 342780237eb013350bff20c21bc92c335422526a；受保护树变化不等于refreeze完成。
- C：codex/governance-to-ledger-20261103，基线342780237eb013350bff20c21bc92c335422526a，PR目标ledger/base-20261103；仅新增治理文档，不复制/启用ledger workflow，不merge。
- R：已暂停，等待 owner 的 E1/E2/E3 环境策略。三CPU环境ID不是可指定runner label，当前可用性未知。不得refreeze或新run，详见 evidence/R-ENVIRONMENT-BLOCKER-20261103.md。
- 新的P诊断为owner另定前置；不以本文擅自执行P或重跑V/R。

唯一证据索引：[INDEX固定版本](https://github.com/NoGod3524/EXReader/blob/de0832112e92c47bc1a47969236dd2376a0ed55f/evidence/INDEX.md)。本包不复制或修改该索引。新增证据须与该writer协调登记。
禁止force、admin bypass、改v1 state、把断言改成允许差异；不写F03/F05/F07或dot/f0*其他会话分支。

版本身份以 [VERSION-LINES](https://github.com/NoGod3524/EXReader/blob/342780237eb013350bff20c21bc92c335422526a/docs/VERSION-LINES.md) 区分同号不同源。当前总SDK3.42.0，先前保持3.41.0指令已由owner撤销。C只新增文档，PR目标ledger/base-20261103；一次四条自动workflow用于基线测量，不作C验收。R候选须包含P落地后实际提交，不提前refreeze。
