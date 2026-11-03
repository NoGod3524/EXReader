# Performance baseline policy — E1 + E3

Owner 决定日期：2026-11-03（America/New_York）。跟踪：[issue #32](https://github.com/NoGod3524/EXReader/issues/32)。当前 SDK 真源 **3.42.0**、ABI epoch 1；同号不同源见 [VERSION-LINES](../VERSION-LINES.md)，refreeze 完成后统一升 3.43.0。

## E1: four switches

1. **Environment recording ON**：逐次采样记录 CPU 型号、核数、内存、OS、内核、实际编译器及编译 flags、runner label；保留源码 SHA、run/attempt、二进制及原始样本散列。缺失项明确记 unknown，不猜测或借用另一环境。
2. **Per-environment budgets ON**：预算按实测环境登记，不能把 EPYC 7763 / EPYC 9V45 / Xeon 8573C 视作同一环境或最近邻替代。
3. **Cross-environment hard gate OFF**：跨环境只作弱约束和诊断；同环境历史 p95 超过 1.5× 必须人工复核，不自动解释成通过或性能退化。复核记录环境、样本与判断依据。
4. **Raw-sample derivation ONLY**：预算必须由保管的原始样本经脚本导出，登记样本/导出器散列、命令、环境、统计方法和 run；禁止手填。沿用现有 export_reading_real_budgets.py / export_reading_cpu_baseline.py 的原始证据链，不改历史冻结对象。

## E3: advisory time box

performance 照跑照记，保留失败与原始样本；所有结果加 `advisory: true`、`accepted: false`，不得引用为“通过”、不得用于授予性能验收或发布信用。运行成功只证明采集/诊断命令完成，不代表预算获准。

非性能的 protocol / native / profiles / platforms / corpus 继续是硬门禁，由 reading-required-core 聚合。原 reading-required.yml 保留原逻辑，仅增加 advisory/不再必需的注释；它仍运行，其失败不阻塞合并。不能把协议、构建或产品失败改成 advisory。native 中的性能测量由显式 advisory 包裹记录真实退出码，其余命令仍 fail-fast。

恢复严格性能门禁必须同时满足：E1 四开关落地、P 与 F07 provider 后的实际候选完成一次严格复验、所有原始样本/环境/导出预算/源码/run 绑定完整，并由 owner 记录恢复决定。不得复用 95100501 或 21add50a 的证据冒充新树。

最长六周；硬截止 **2026-12-15 00:00 America/New_York**。到期未完成恢复条件，默认分支回退为只读发布：保留读取与证据归档，停止可写发布，不延长 advisory、不宣称通过。此处不切换默认分支；到期处置与严格复验由 issue #32 跟踪。

## Gate deployment and protected trees

新 `.github/workflows/reading-required-core.yml` 不包含 performance；必需检查由 reading-required 改为 reading-required-core（GitHub Actions app 15368），规则集的删除、非快进、PR、strict、bypass 等其余字段保持不变。

必须用仅加一行注释的一次性 PR 验证“core 为必需、legacy 仍运行但不阻塞”，然后关闭并删除临时分支。仅改检查名不算完成；分支监听、规则匹配或部署不足必须如实记为未完成。禁止为验证提前跑完整 native 矩阵。

reading-required.yml 与 reading-required-core.yml **均不在八项受保护树内**，native.yml 才在。因此门禁拆分本身不扩大 R 候选；native 的既有 P 变更已要求 R 候选在 P 之后。SDK 基线、预算数值和原有断言均不在此处修改。
