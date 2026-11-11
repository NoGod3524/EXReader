# 仓库冗余清理台账（CLEANUP-LEDGER）

> 目的：把「为什么不删」逐条写清，附数字与判据，免得下一个人（或下一个 agent）从零再查一遍、再删错一次。
> 口径：**所有体积用 `git ls-tree -r -l <ref>` 量 git 对象，不用工作树。** 工作树停在哪个分支会给出完全不同的数字（本文件第一版就栽在这里）。

## 基线

`origin/main` @ `aaf8aecc`：树内 blob **11,470 个 / 449.8 MB** 未压缩；`size-pack` **≈76 MB**。

| 区 | 文件数 | 未压缩 | 说明 |
|---|---:|---:|---|
| `evidence/` | 3,861 | **213.0 MB** | 各轮证据，溯源链 |
| `docs/` | 2,672 | 146.8 MB | 其中 `docs/ui` 1072 个 / 132.3 MB |
| `tests/` | 3,598 | 72.9 MB | 其中 `tests/fixtures` ≈36 MB 是夹具 |
| `docs/ui/evidence/2a-step6*` 四个压缩包 | 4 | **54.3 MB** | 已压缩，几乎不能再压 |

## 已处置

| 项 | 动作 | 判据 |
|---|---|---|
| 133 个失效 workflow | **删除**（PR #121） | 只绑定已从远端删除的分支，零引用 |
| 版本例外登记 | 587 → 552 | 只去掉指向被删 workflow 的 35 条 |
| 远端分支 | **删除 59 个** | `merge-base --is-ancestor` 判定为 main 祖先（109 → 50） |
| `tests/` 五个带日期验收目录（91 文件） | **移动到 `evidence/`** | 无构建入口；两个生成脚本的默认路径已同步 |

## 明确不动的六项（附判据）

### 1. 四个测量压缩包（54.3 MB）

- `docs/ui/evidence/2a-step6/record/measurements.zip`（20,968 KB）—— 零引用
- `docs/ui/evidence/2a-step6-fix/record/real-measurements.tar.gz`（13,115 KB）—— 零引用
- `docs/ui/evidence/2a-step6-fix/record/measurements.tar.gz`（12,923 KB）—— 零引用
- `docs/ui/evidence/2a-step6-fix/record/real-exe-regression-measurements.tar.gz`（8,446 KB）—— 被 `docs/ui/2A-STEP6-FIX.md:89` 引用

**不动的理由**：
1. 从 tip 删除**不会**让 clone 变小 —— blob 留在历史里，只有重写历史才减体积
2. 占 `size-pack` 约七成（54.3 / 76 MB），而它们是原始测量数据，属证据
3. 有一个被文档当证据引用
4. 重写历史的代价：全体 SHA 失效、50 个远端分支强推、所有 PR 引用失效、每个人重新 clone

**唯一例外收益**：CI 浅克隆每次少下载约 54 MB。收益不大且与「证据不删」冲突，不做。

### 2. `evidence/` 213 MB

溯源链，多轮之间互相引用（gate3 → gate2 → gate1 → e1）。没有文件声明某轮作废，因此不是重复数据。

### 3. 剩余 111 个绑定已删分支的 workflow

```
当前 workflow = 123 个
绑定已删分支的 = 111 个
  其中被 py 脚本按名引用 = 98 个
  其中被其它 workflow 引用 = 15 个
```

**判据失效的原因**：引用链的根不在仓库里 —— 是「谁会手动跑这个脚本」。名字匹配回答不了这个问题，98/111 的高命中率说明按名字匹配必然误判。

### 4. `reader.c` 的 409 处产品开关

需要 MSVC 与已安装的产品模块才能验证；且把代码挪到别的文件不减少代码量。

### 5. `git worktree prune` 清不掉的 221 条登记

```
.git/worktrees 登记 441 条，失效 221 条
git worktree prune --expire=now → 清掉 0
error: failed to delete '.git/worktrees/EXReader': Permission denied
ACL: Everyone : DeleteSubdirectoriesAndFiles : Deny（从上层目录继承）
```

**已实测**：清掉 40 个条目的 Deny ACE 与只读位后仍失败 ⇒ Deny 来自上层，不动。

### 6. 根目录 26 个 `*-OUT.txt`

工具按固定路径读写，动它们要先改工具。

## 反例：不要把这些当冗余

- `tools/generate_*.py`、`tests/make_*_fixture.py`（约 60 个）：可达性分析判它们「没人引用」，但它们是**手动运行的夹具生成器**
- `evidence/platforms-20261108/provenance.json` 里记录的旧路径：那是**历史快照**，文件移动后**不应改写**
- `tests/fixtures`（约 36 MB）：测试夹具，删了测试跑不了

## 操作纪律（血泪）

1. **量体积用 git 对象，不用磁盘**：`git ls-tree -r -l <ref>`，否则量到的是某个工作树所在分支的意外状态
2. **删除前先做对照实验**：例如「这个测试在纯净 main 上是不是本来就失败」——`sdk-release` 就是这样确认与本批改动无关的
3. **被 sha256 绑定的文件不要顺手改格式**：`tools/version_literal_exceptions.json` 重排一次就产生 +21,753 / −755 的不可 review 差异；只删条目时是 +36 / −701
4. **改被 sha256 绑定的文件 = 改契约**：改前先查登记表（`version_literal_exceptions.json`、证据基线、ABI 清单）
