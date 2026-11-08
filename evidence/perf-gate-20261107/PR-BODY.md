## 结果

当前不能恢复 performance required。提案和可复现工具已提交，E3 advisory/accepted=false 保持，未改 src/include/examples/.github。

- 三轮完整采集共 45 个新进程（每配置 5 次），另保留一次预检中止的部分样本。独立候选最大离散度：9.471% / 6.516% / 22.080%，未达到全部指标 <5%。温度不可读，后台负载仍存在；没有宣称取得干净基线。
- 提议警告 1.10×、门禁 1.25×、硬上限 1.50×，从冻结原始样本 p95 脚本导出绝对值，当前 eligible=false。独立候选最差 1.2224×，只越警告；稳定性失败仍拒绝整轮。
- PERF-GATE-PROPOSAL.md 包含前置检查、实测对比、机器归一化、完整可套用 workflow patch、恢复/回滚及 E3 尚缺条件。现有报告生产者强制 accepted=false，当前本地原型的环境键还绑定被测 SDK，恢复前需拆分产品身份与机器环境、实现显式 strict 模式和实际候选完整 real-v1 严格复验，最后由 owner 在 #32 决定恢复。
- 19 本同 HEAD 全页回归两轮：每轮 19/19、11296 页，重复逐页差异 0。历史 c665 基线有 8604 个共有页变化，保留历史比较失败结果；没有将历史比较记为通过。

## 验证

- 5% 边界、少样本/空闲失败、原始样本篡改拒绝、阈值重算检查通过。
- tests/check_perf_policy.py 通过。
- git apply --check、嵌入 patch 一致性、YAML 结构及 git diff --cached --check 通过。
- 全部完整采集轮次的原电源策略读回一致；只新增允许路径及要求的 PERFGATE-OUT.txt。
- 没有手动启动或取消 workflow run。

跟踪 #32。完整证据：evidence/perf-gate-20261107/；结论：docs/validation/PERF-GATE-PROPOSAL.md。
