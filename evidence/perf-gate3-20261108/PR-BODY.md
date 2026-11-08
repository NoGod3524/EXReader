# Correct performance measurement under same-core load

#87 的长整数参照与翻页在同核争用下分别取墙钟 p95，不能消除时间片偏差。新增只改测量的 Windows 探针，记录一致边界的墙钟/TSC/线程周期及上下文切换，完整覆盖 EOF、跨章节建 pager、排版和渲染；以 `p95(target cycles) / p95(sqrt(before cycles × after cycles))` 归一化。

长参照诊断中，中/高压参照墙钟增加 102%/310%，线程周期只增 0.06%/0.10%；调度等待是主因，降频不是主要解释。目标执行成本残差及 PMU 不可用的边界均有数据记录。正式参照固定为 12M 步，预算在受压候选前冻结，没有拟合参数或删点。

| 额外压力 | 五轮 ratio 中位数 | 漂移 | 离散度 |
|---|---:|---:|---:|
| 无：0 worker | 3.564776718 | 0% | 1.434026% |
| 中：1 worker | 3.570532444 | +0.161461% | 2.195308% |
| 高：3 workers | 3.468411452 | −2.703262% | 3.796614% |

受压 19 本书的漂移和离散度全部 <10%，两档均无单书 gate 超限。全页回归前后及相对 #87 均为 19/19 本、11,296 页、8,648,640 glyph，页数/glyph/像素哈希变化 0；正式 4,560 个顺序样本的签名也匹配 #87。

**不能恢复 required。** 无压 Black Boy 离散度仍为 10.125412%；墙钟三明治高压漂移仍为 −50.625709%。线程周期指标不覆盖阻塞等待，需独占 runner 的墙钟检查、重新取得逐书稳定基线及 E3 strict 生产者。报告保持 advisory/accepted=false。

验证：`check_load.py final`（计量边界、非法计数、原始 SHA、SDK 兼容与单书 +60% CPU 工作量注入拒绝）、原 `check_ratio.py`、全页前后比较及范围检查通过。两个仪表失败试跑原样保留；全部自建压力进程停止，四次 session 的电源策略均已恢复。

公式、三档阈值与全部 15 轮/19 本结果见 [提案](https://github.com/NoGod3524/EXReader/blob/codex/perf-gate-load-20261108/docs/validation/PERF-GATE-PROPOSAL.md)；根因与原始证据见 [证据目录](https://github.com/NoGod3524/EXReader/tree/codex/perf-gate-load-20261108/evidence/perf-gate3-20261108)。改动限于 tools/perf、docs/validation 和本次证据目录；没有修改产品目录或 .github，也没有取消 workflow run。
