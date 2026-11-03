# Ledger authority

## 当前收口规则（owner 最新指令）

v1 `catalog.json` 按归档只读管理，任何会话或自动化均不得修改 state；实际改名及 archived 标记仍待另行执行，本次不实施。v2 为独立 84 项，初始全部 pending，不继承 v1 verified。

当前 C 由 PR #31 统一接管并获 owner 授权合并；P #30 保持 draft。两份 ledger workflow 文件保留在 #31，启用时机仍待 R 后 owner 确认，不因文件入库产生触发授权。下文“本包不带入”特指 #33 原始九文档包；旧 #31 的“等待 P”和五文档风险表述保留为接管前记录，不覆盖本次授权及扩展后的 PR 范围。

版本真源为 3.42.0，ABI epoch 1；同号不同源依 [VERSION-LINES](../VERSION-LINES.md) 登记。E1/E3 已确定，政策为 `docs/validation/PERF-BASELINE-POLICY.md`（当前随 [P #30](https://github.com/NoGod3524/EXReader/pull/30) 落盘），跟踪 [issue #32](https://github.com/NoGod3524/EXReader/issues/32)。#33 文档中“等待策略”的叙述保留为其来源时点记录；R 仍需另行明确执行，候选必须在 P 与 provider 最终落地后。


## 历史审计反写设计（v1 冻结前，当前不构成写入授权）

`state` 的唯一写入者是 `reader-total-progress.yml` 的只读审计产物反写。人工提交只能修改 `note`、`evidence` 引用与文档，不得修改 `state`。

不得删除已计分项，不得改变 108 分母，不得改变 `group` 归属，不得就地修改范围。修改范围必须新建 `catalog-v2.json` 并保留本文件。

未附审计 run 的加分必须在 Exceptions 登记 commit sha、加分项、加分时间、缺失的审计 run 及复验命令。下表四项共同使用文末复验命令，将 `<sha>` 替换为该行 commit。

## Exceptions

转录自[PR#28 @7108a166](https://github.com/NoGod3524/EXReader/blob/7108a1662484b95f8e205795e2cc601acbe6aec9/docs/reader-total-progress/LEDGER-AUTHORITY.md)；“无”指该次总台账审计run缺失，不抹除专项原证据。

| # | 加分项 | commit | 时间(UTC) | 审计 run | 状态 |
|---|---|---|---|---:|---|
| 1 | 96/108（iPhone annotation） | `5db41cb1` | 2026-10-31T22:45:07Z | 无 | 未审计记账 |
| 2 | 97/108（F04 scope） | `4d85994b` | 2026-11-01T12:57:48Z | 无 | 未审计记账 |
| 3 | 98/108（F02 transfer） | `255ec557` | 2026-11-01T13:11:40Z | 无 | 未审计记账 |
| 4 | 99/108（F07 symbols） | `95100501` | 2026-11-03T16:30:11Z | 无 | 未审计记账 |

## 引用纪律

未追加“祖先从未成功”例外，因为native/acroform/wp5已找到祖先成功记录；仍不得把祖先绿称当前树通过。

引用须给branch、commit、catalog blob及run/受测树。原失败、scope_excludes、部分结果和过期状态保留；本包未运行总台账审计、不改变分数。


引用必须写成 `99/108 @ <branch> @ <commit> @ <blob sha>`；只写“99/108”视为无效引用。历史同时存在 78/18/12 的 `c5d38ca7` 与 99 的现行 blob。

## 复验命令

```bash
git -C . log --all --date=iso-strict --format='%cI %h %s' -3
git -C . cat-file -t <sha>            # commit / blob / tree
git -C . show <sha>:docs/reader-total-progress/catalog.json | python -c \
  "import json,sys,collections;d=json.load(sys.stdin);print(collections.Counter(i['state'] for i in d['requirements']))"
```


## Current integration identity (2026-11-03)

当前 SDK 真源为 **3.42.0**，ABI epoch 1，基线 ledger/base-20261103 已含 V 合并提交 34278023。F06 交付与本线同号不同源，见 [VERSION-LINES](../VERSION-LINES.md)；refreeze 完成后统一升 3.43.0。历史审计/补丁中的旧版本和散列保留其取证含义，不是当前版本声明。

### 接管前阶段记录（已由本页当前收口规则替代）

顺序 V → P → C；本 C PR 现在仅开 draft，合并等待 P。R 候选必须取 P 和 F07 provider 最终落地后的提交，不能使用 21add50a。

两个新 ledger workflow 从第一天满足收窄后的 CI hygiene：多命令 Bash 首行 set -euo pipefail，无裸 test -n，无隐式预期失败。authority 仅在目标分支 catalog 变化时触发；custody 仅手动触发；两者均无 push 事件。仓库存储的补丁保管不依赖 Actions。


C 属未经 CI 的纯文档合并，风险限于 5 个新文档 + 2 个 workflow 文件。

这里的五份治理文档为 LEDGER-AUTHORITY、EVIDENCE-CUSTODY、默认分支决策、保护盘点和 refreeze-scope；其余六份是既有 RESULT 与 custody 的原样归档快照。当前仍为 draft；实际 workflow 触发清单为空，没有把静态核对当作 CI 通过。

## #33 原始包边界补充

以下“本包”指 #33 的九文档包；两份 workflow 已由 #31 原包携入，最终包按上文当前收口规则解释。

v1 catalog.json冻结只读，任何会话和自动化不得修改state。实际归档改名和archived标记待owner另行“执行”。不得删除条目、改108分母、group或就地缩窄范围。
v2独立84项，全部初始pending；旧verified不自动转授。两个ledger workflow **待 R 后启用**，本包不带入。
PR#28历史“审计反写”设计不覆盖当前v1冻结指令，不是写入授权。
