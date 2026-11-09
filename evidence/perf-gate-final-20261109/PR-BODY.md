当前冻结周期方案不能设为 required：最终采样器的同代码五次复验仅 **2/5 pass**，第 1、2、5 次误报；Ubuntu CI 基线与复验分别为 **0/19、0/5**。本 PR 保留可执行门禁、两批全部原始证据及明确拒绝结论。

新增 `gate-probe`、`sample.py`、`refresh_baseline.py`、`gate.py` 与完整资格测试。每本 3 个新进程 × 16 个顺序页，线程周期 nearest-rank p95；CPU warning/gate/hard 为 10%/20%/35%，墙钟看门狗 3×。Windows 使用 QueryThreadCycleTime，Linux 实现硬件 perf cycles 并在无 PMU/权限或 multiplex 时拒绝；Linux 后端尚未运行验证。

| 最终同代码测试 | 最大周期比 | 最大墙钟比 | 结果 |
|---|---:|---:|---|
| 1 | 1.479537676 | 4.540956000 | fail |
| 2 | 1.393197363 | 1.365710264 | fail |
| 3 | 1.162792306 | 1.159963760 | pass |
| 4 | 1.046193992 | 1.053646681 | pass |
| 5 | 1.409418850 | 1.414315884 | fail |

真实 +25% 注入只使 `black-boy` 失败：基线 91,359,405 → 113,268,185 cycles，ratio 1.239808698，实际额外 CPU 工作 25.006892%，exit 1。没有修改 JSON 模拟退化、删点或调宽阈值。初版的 5/5 pass 和最终的失败证据均保留。

验证结果：

- 独立重算 399 份最终原始 JSON、6,384 个翻页样本，19 个基线 p95 和全部判定一致；源码、SDK/探针字节相同且冻结早于候选。
- 19 本真书全页回归：11,426 页、8,648,571 字形，页数/字形/逐页哈希变化均为 0。
- 门禁阈值边界、NaN/缺失/篡改/签名和伪 CI 基线拒绝测试通过；19 个输入归档哈希回环和非法归档拒绝通过。
- `docs/validation/performance-required.patch` 通过 `git apply --check` 与 actionlint 1.7.12。`.github/`、`src/`、`include/`、`examples/` 未修改。

当前 256 个 workflow 无 `tools/perf/` 或 `tools/regress/` 入口；旧性能 workflow 跑 Ubuntu 22.04 和另一套 8 本书。19 本原文只有本地路径，未发布到公共仓库。`perf-baseline-ci.json` 明确为 blocked/null 拒绝记录，不能冒充冻结 CI 基线；`gate.py` 以 exit 2 拒绝。

完整 19 本数值表、#97 阈值推导、恢复条件、patch 部署与回滚：[PERF-GATE-FINAL.md](https://github.com/NoGod3524/EXReader/blob/codex/perf-gate-final-20261109/docs/validation/PERF-GATE-FINAL.md)。证据位于 `evidence/perf-gate-final-20261109/`，逐步日志为 `PERFGATE-FINAL-OUT.txt`。

仍需合法的 CI 书籍供给、获准部署 workflow、可用 PMU 和同构 runner，以及该 CI 环境真正取得 19/19 基线、5/5 同代码 pass 和 +25% 真阳性 fail，才能增加 required context。当前规则集未改动。
