# Ledger authority

## 写入规则

`state` 的唯一写入者是 `reader-total-progress.yml` 的只读审计产物反写。人工提交只能修改 `note`、`evidence` 引用与文档，不得修改 `state`。

不得删除已计分项，不得改变 108 分母，不得改变 `group` 归属，不得就地修改范围。修改范围必须新建 `catalog-v2.json` 并保留本文件。

未附审计 run 的加分必须在 Exceptions 登记 commit sha、加分项、加分时间、缺失的审计 run 及复验命令。下表四项共同使用文末复验命令，将 `<sha>` 替换为该行 commit。

## Exceptions

| # | 加分项 | commit | 时间(UTC) | 审计 run | 状态 |
|---|---|---|---|---:|---|
| 1 | 96/108（iPhone annotation） | `5db41cb1` | 2026-10-31T22:45:07Z | 无 | 未审计记账 |
| 2 | 97/108（F04 scope） | `4d85994b` | 2026-11-01T12:57:48Z | 无 | 未审计记账 |
| 3 | 98/108（F02 transfer） | `255ec557` | 2026-11-01T13:11:40Z | 无 | 未审计记账 |
| 4 | 99/108（F07 symbols） | `95100501` | 2026-11-03T16:30:11Z | 无 | 未审计记账 |

## 引用纪律

引用必须写成 `99/108 @ <branch> @ <commit> @ <blob sha>`；只写“99/108”视为无效引用。历史同时存在 78/18/12 的 `c5d38ca7` 与 99 的现行 blob。

## 复验命令

```bash
git -C . log --all --date=iso-strict --format='%cI %h %s' -3
git -C . cat-file -t <sha>            # commit / blob / tree
git -C . show <sha>:docs/reader-total-progress/catalog.json | python -c \
  "import json,sys,collections;d=json.load(sys.stdin);print(collections.Counter(i['state'] for i in d['requirements']))"
```
