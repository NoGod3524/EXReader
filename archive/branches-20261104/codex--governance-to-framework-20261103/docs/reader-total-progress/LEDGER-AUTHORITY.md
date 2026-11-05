# Ledger authority
## 当前规则
v1 catalog.json冻结只读，任何会话和自动化不得修改state。实际归档改名和archived标记待owner另行“执行”。不得删除条目、改108分母、group或就地缩窄范围。
v2独立84项，全部初始pending；旧verified不自动转授。两个ledger workflow **待 R 后启用**，本包不带入。
PR#28历史“审计反写”设计不覆盖当前v1冻结指令，不是写入授权。

## 历史 Exceptions
转录自[PR#28 @7108a166](https://github.com/NoGod3524/EXReader/blob/7108a1662484b95f8e205795e2cc601acbe6aec9/docs/reader-total-progress/LEDGER-AUTHORITY.md)；“无”指该次总台账审计run缺失，不抹除专项原证据。

| # | 项 | commit | UTC | 总台账审计run | 状态 |
|---|---|---|---|---|---|
| 1 | 96/108 iPhone annotation | 5db41cb1 | 2026-10-31T22:45:07Z | 无 | 未审计记账 |
| 2 | 97/108 F04 | 4d85994b | 2026-11-01T12:57:48Z | 无 | 未审计记账 |
| 3 | 98/108 F02 | 255ec557 | 2026-11-01T13:11:40Z | 无 | 未审计记账 |
| 4 | 99/108 F07 | 95100501 | 2026-11-03T16:30:11Z | 无 | 未审计记账 |

未追加“祖先从未成功”例外，因为native/acroform/wp5已找到祖先成功记录；仍不得把祖先绿称当前树通过。
引用须给branch、commit、catalog blob及run/受测树。原失败、scope_excludes、部分结果和过期状态保留；本包未运行总台账审计、不改变分数。
