# R 环境阻塞更正
结论：**未知**。阻塞从“成本高”更正为“既定环境当前不可保证复现”，不是已证明环境不存在。

来源树：95100501eeef9c6325be8b3882aa400c99cf000f。
- [environments.json](https://github.com/NoGod3524/EXReader/blob/95100501/tests/reading_real/environments.json)中的 amd-epyc-7763 / amd-epyc-9v45 / intel-xeon-8573c 是CPU环境ID，不是可指定runner调度label。
- [reading-real.yml](https://github.com/NoGod3524/EXReader/blob/95100501/.github/workflows/reading-real.yml)只有 runs-on: ubuntu-22.04，不保证分配指定CPU。
- 2026-11-03 19:22 UTC的只读 actions/runners 查询total_count=0，仅表示self-hosted库存，不能证明GitHub托管CPU不可用。

| 环境ID | 当前可用性 | 已证基准使用run | UTC区间（不是全仓最后使用时间） |
|---|---|---|---|
| amd-epyc-7763 | 未知 | [39899829270](https://github.com/NoGod3524/EXReader/actions/runs/39899829270) | 2026-10-23 04:20:51–04:28:03 |
| amd-epyc-9v45 | 未知 | [40010390609](https://github.com/NoGod3524/EXReader/actions/runs/40010390609) | 2026-10-23 19:18:42–19:23:00 |
| intel-xeon-8573c | 未知 | [40010395155](https://github.com/NoGod3524/EXReader/actions/runs/40010395155) | 2026-10-23 19:18:44–19:25:01 |

2026-11-03 19:58 UTC只读回读run身份：39899829270 attempt1 success，head=887e1bb59ef6f28c15824cb7593654f3610f3cef，branch=codex/r3-frozen-baseline；40010390609及40010395155均attempt1 success，head=9442e84d60469de5551de7ce7e62191a0059d9d1，branch=codex/reading-cpu-baselines。它们是95100501配置引用的历史基准，不运行于95100501，不授当前树通过。

R已停止，等待owner E1/E2/E3策略。未创建V之后候选，未重算八项protected_trees，未refreeze，未触发新run。若策略需要重建环境，它是独立前置；不得用hosted偶然分配冒充可复现环境。
