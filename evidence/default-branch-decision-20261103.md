# 默认分支决策预演 · 2026-11-03

本版是在 owner 确认后继续的**只读 C1 决策记录**。B（把 95100501 并进 codex/framework，走 PR）改判为**规则上可行，但需解语义冲突**。发现冲突与四方案通过验收是不同事实；本段没有解决冲突或运行 reading-required。

**本段未改任何 ref、未改 Settings，C2 未执行。** 仅读取 Git 对象与 API 并更新本地 evidence 文档；未修改产品代码、catalog、workflow 或 PR #28。本文命令均为拟议 C2 步骤，未执行，不构成执行授权。

## A. 三层事实与差异

### 1. 当前对象

| 对象/候选 | 当前 tip/状态 | 与基线差异 | 含 catalog | 含 reader-total-progress.yml | 含 ledger 两个 workflow | 保护规则继承性 |
|---|---|---|---|---|---|---|
| 当前默认 codex/framework | 8ca964fc4adc572cf2da303f5d88100a5e844ccb | 独有 4 commits；基线独有 2101 commits | 否 | 否 | 否 | 当前匹配 ~DEFAULT_BRANCH |
| 基线 95100501 / audit/f07-authoritative-symbols-20261103 | 95100501eeef9c6325be8b3882aa400c99cf000f | 基线 | 是 | 是 | 否 | 当前非默认；设默认才匹配同一个 ruleset |
| 拟建 main | 远端查询无此 ref | 未建；拟从基线整合 framework | 拟有，未验证整合树 | 拟有，未验证整合树 | 不随基线自动获得；须另行提升 PR #28 内容 | 仅命名 main 不会命中现有默认分支条件；切默认后同规则集跟随 |
| ledger-guard PR #28 | a212dd59975d5aa4256af7cc37d1bddd6b242dd1 | 相对基线 9 个新增文件 | 继承基线，未改动 | 继承基线 | 是 | 当前 base=ledger/base-20261103，不是默认分支 |

基线与 framework 的存在性使用 `git cat-file -e <ref>:<path>` 核对。所有“拟有”均是方案预期，不表示已有可验收的合并树。

### 2. 提交与树差异

```text
$ git rev-list --count 95100501..origin/codex/framework
4
$ git rev-list --count origin/codex/framework..95100501
2101
$ git log --oneline 95100501..origin/codex/framework
8ca964fc Merge pull request #27 from NoGod3524/codex/reliability-convert-memory
f732c8b0 fix(ci): retain exact corpus inputs after publisher changes
12b98ea1 merge: integrate audit fixes with current framework
096663da fix: address October 31 audit findings and add regression coverage
```

`git diff --name-only 95100501 origin/codex/framework` 已只读执行，返回 2052 个路径；这是两个 tip 的完整快照差异，**不是四个独有提交各自修改路径的并集**。按顶层路径汇总：

| 顶层 | 路径数 |
|---|---:|
| `.github` | 210 |
| `CHANGELOG.md` | 1 |
| `CMakeLists.txt` | 1 |
| `HANDOFF-RESULT-C11.md` | 1 |
| `HANDOFF-RESULT-S14.md` | 1 |
| `HANDOFF-RESULT-S15.md` | 1 |
| `HANDOFF-RESULT-S16.md` | 1 |
| `HANDOFF-RESULT-S17.md` | 1 |
| `README.md` | 1 |
| `apps` | 187 |
| `cmake` | 1 |
| `docs` | 356 |
| `examples` | 128 |
| `extras` | 69 |
| `include` | 4 |
| `src` | 8 |
| `tests` | 1025 |
| `tools` | 56 |

独有的两个非 merge 提交：

- `096663da`：CHANGELOG、10 月 31 日审计及转换/流式文档，`src/library.c`、`tests/check_convert_cli.py`、`tests/test_library_stream.c`、`tools/convert.c`、`tools/convert_io.c`。
- `f732c8b0`：`docs/R2-REAL-CORPUS.md`、`tests/reading_corpus/check_collect.py`、`tools/reading_corpus/collect.py`、冻结输入 README 与两份 EPUB。
- `12b98ea1` 与 `8ca964fc` 是 merge commits。它们的父提交边界不同，不能把“独有 4 commits”解释成只新增四个小补丁。复核使用 `git diff --name-only <merge>^1 <merge>`；完整 tip 差异使用上方原始命令。

### 3. 预演与保护

```text
$ git merge-tree --write-tree --name-only 95100501 origin/codex/framework
c35cf69f692cf3e8170ca5a946ddd9f767bf5996
tools/reading_corpus/collect.py

Auto-merging tests/reading_corpus/check_collect.py
Auto-merging tools/reading_corpus/collect.py
CONFLICT (content): Merge conflict in tools/reading_corpus/collect.py
exit 1
```

该 oid 是有冲突的预演树，不能作为可合入树使用。反方向的 B 尚未另行生成预演树，不把 A 方向的 oid 冒充 B 的最终树。

现有规则集为 `~DEFAULT_BRANCH`、bypass_actors=[]、current_user_can_bypass=never。**四方案均没有 admin 覆盖出口。** 有 admin Settings 权限不等于有绕过规则的权限；任何规则配置变更都需另行明确授权。

## B. 四方案对比

本版方案编号：A=新建 main 整合；B=把基线并进现有 framework；C=只提升治理文档与 workflow；D=保持现状。原“直接默认指向 audit/f07-*”不进入候选：明确排除把仍在被推送的 agent 分支设为默认分支。

| 方案 | 改哪些基础设施 | 语义冲突代价 | 合并树能否过 reading-required | blast radius | 回滚路径 |
|---|---|---|---|---|---|
| A main=95100501，再整合 framework | 新 main、整合 PR、workflow main 触发列表、默认分支切换；ruleset 自动跟随；ledger 内容另行提升 | 已发现 collect.py 冲突；还需确认自动合并的测试保留两条取证路径 | 未知，当前预演树有冲突；现有 reading-required 不触发 main PR | 切默认影响默认 PR base、默认源码/文档入口、规则约束对象、默认分支 workflow 可见性及 Actions 负载；framework 将失去此默认分支匹配 | 先切默认回 framework；代码需 revert PR；不承诺删除 main |
| **B 把 95100501 并进 codex/framework（PR）** | 独立整合分支与 PR；默认名称、现有触发列表和 ruleset 不迁移；ledger PR 后续单独提升 | **可行但需解语义冲突**；保留 frozen 和 artifact 两条路径，不能任选一侧 | 未知；必须对解冲突后的 PR head/合并树运行 strict reading-required | 不改 Settings，但会把基线独有 2101 commits 所代表的历史及其合并结果带入当前默认；引入大量源码、测试、文档和 workflow，含现有 push 触发器；不是“小型基础设施 PR” | 对该 merge commit 做 `git revert -m 1`，经另一个受保护 PR 合入 |
| C 仅提升治理文档、ledger workflow 与保管补丁 | 从 PR #28 选择 9 个新增文件，独立 PR 到 framework；不提升 catalog/审计脚本，不切默认 | 不解 collect.py 冲突；却留下治理 workflow 与缺失台账/审计依赖的功能断层 | 未知；产品树不变不代表必需检查已通过；新增 guard 不会在这个无 catalog 修改的 PR 自测 | 直接树改动限于治理与 custody；不会使 framework 获得 108 项台账，也不能保证审计可 dispatch；PR 仍可能触发现有检查 | 对治理 merge commit 做 `git revert -m 1`，经 PR 合入 |
| D 保持现状 | 无新增 ref、workflow、默认分支或规则变更 | 不处理冲突；两条历史继续分歧 | 未知，无新合并树；未在本段运行当前树的检查 | 无本次远端变动；台账与审计仍不在默认分支，PR #28 仍为 draft | 无需回滚；只读复核默认分支与 tip |

所有方案在受保护目标上合入均须满足 PR、必需检查、strict 最新性、会话解决要求，不能用 `--admin`、直接推受保护 tip 或 force-push 代替。

### 拟议命令与回滚（仅记录，未执行）

以下命令使用 Bash。涉及新建分支、提交、push、PR、merge、Settings 的每一步均属于 C2，须 owner 明确说“执行”后逐条确认。`<...>` 为执行当时必须核实的实际值，特别是解冲突后的 commit 与检查结果，本段不伪造这些值。

**A：main 整合。**

```bash
# 仅在远端 main 不存在且 owner 确认后：
git push origin 95100501:refs/heads/main
# 独立工作目录，保留两侧历史：
git worktree add -b codex/main-integration-20261103 ../EXReader-main-integration 95100501
git -C ../EXReader-main-integration merge --no-ff --no-commit origin/codex/framework
# 当前预演已知此处有冲突；必须停。不得继续提交，除非独立语料修复获批且验证完成。
# 解冲突后的整合树必须包含 main 触发列表，再经 PR 合入 main。
git -C ../EXReader-main-integration push -u origin codex/main-integration-20261103
gh pr create --repo NoGod3524/EXReader --base main --head codex/main-integration-20261103 --draft --title 'integrate framework history into main'
# main 内容与触发列表就绪并获 owner 确认后，才切默认：
gh api -X PATCH /repos/NoGod3524/EXReader -f default_branch=main
```

回滚默认分支：

```bash
gh api -X PATCH /repos/NoGod3524/EXReader -f default_branch=codex/framework
```

这条命令只还原默认分支设置，不撤销 main 的代码、Actions run 或其它 Settings。保留 main，不把删除已受保护或已有依赖的分支作为回滚前提；需要撤销 main 合并内容时，按 B 的 revert PR 流程，以实际 merge SHA 为准。

**B：现有默认分支整合。**

```bash
git worktree add -b codex/framework-integration-20261103 ../EXReader-framework-integration origin/codex/framework
git -C ../EXReader-framework-integration merge --no-ff --no-commit 95100501
# 若出现冲突即停；D 项的语义修复属于独立任务，不能用 ours/theirs 跳过。
# 仅在独立冲突修复与检查获确认、并生成实际整合提交后：
git -C ../EXReader-framework-integration push -u origin codex/framework-integration-20261103
gh pr create --repo NoGod3524/EXReader --base codex/framework --head codex/framework-integration-20261103 --draft --title 'integrate ledger baseline and preserve corpus evidence paths'
# 合并动作仅在实际 PR 满足 strict reading-required 且 owner 逐条确认后：
gh pr merge <integration-pr-number> --repo NoGod3524/EXReader --merge
```

B 不切默认、不需要为了目标分支更名而追加 main。ledger PR #28 不自动随基线进入 framework；待框架已包含 95100501 后，应另行确认其提升路径，不能把本 C1 当作批准合并 #28。

B 回滚命令模板：先核对 `<merge-sha>^1` 是被整合前的 framework tip，再生成逆向提交，经受保护 PR 合入：

```bash
git worktree add -b codex/framework-integration-revert-20261103 ../EXReader-framework-revert origin/codex/framework
git -C ../EXReader-framework-revert show --no-patch --format='%H %P' <merge-sha>
git -C ../EXReader-framework-revert revert -m 1 <merge-sha>
git -C ../EXReader-framework-revert push -u origin codex/framework-integration-revert-20261103
gh pr create --repo NoGod3524/EXReader --base codex/framework --head codex/framework-integration-revert-20261103 --draft --title 'revert framework baseline integration'
gh pr merge <revert-pr-number> --repo NoGod3524/EXReader --merge
```

若 revert 出现冲突或检查失败，停下；无 admin 绕过、force/reset 远端的替代出口。

**C：有限治理提升。** 只选 PR #28 的四个治理文件与 custody 目录；不 cherry-pick 95100501 的产品历史。

```bash
git worktree add -b codex/ledger-infra-promotion-20261103 ../EXReader-ledger-infra origin/codex/framework
git -C ../EXReader-ledger-infra restore --source=a212dd59975d5aa4256af7cc37d1bddd6b242dd1 --staged --worktree -- .github/workflows/ledger-authority.yml .github/workflows/ledger-evidence-custody.yml docs/reader-total-progress/LEDGER-AUTHORITY.md docs/reader-total-progress/EVIDENCE-CUSTODY-20261103.md evidence/custody-20261103/
git -C ../EXReader-ledger-infra diff --cached --name-status
git -C ../EXReader-ledger-infra commit -m 'docs(ci): promote ledger governance and custody snapshot'
git -C ../EXReader-ledger-infra push -u origin codex/ledger-infra-promotion-20261103
gh pr create --repo NoGod3524/EXReader --base codex/framework --head codex/ledger-infra-promotion-20261103 --draft --title 'promote ledger governance and custody snapshot'
```

仅供边界比较：framework 缺少 catalog，guard 的 base catalog 读取依赖也不完整；本方案不能宣称已把可运行审计迁入默认分支。回滚使用 B 同一流程，将实际治理 merge SHA 传给 `git revert -m 1 <governance-merge-sha>` 并经 PR 合入，分支名另取专用值；不直接推默认分支。

**D：保持现状。**

```bash
gh api /repos/NoGod3524/EXReader --jq .default_branch
git ls-remote origin refs/heads/codex/framework refs/heads/audit/f07-authoritative-symbols-20261103 refs/heads/main
```

没有写操作，无回滚命令。

## C. 推荐与 C2 前置条件

**推荐 B：通过独立 PR 将 95100501 整合进 codex/framework，先解决语料取证语义冲突并验证完整 reading-required。** 本轮执行范围仍为只读，推荐不是批准实施。

在“B 现在可行”的前提下，方案排序调整为 B 优先于 A：保留现有默认分支、检查触发目标和规则匹配对象，减少默认分支迁移的基础设施改动。上一版只写了停点、尚未给出最终推荐，因此本版是首次正式推荐 B，并非替换一条已经发布的最终推荐。B 的源码与 workflow 影响仍很大，需用最终 PR diff、整合树和实际检查结果评估，不能因不用改 Settings 就称为低影响。

明确排除“默认直接指向仍在被推送的 audit/f07-* agent 分支”。

若 owner 改选 A，C2 必须先修改并落入 main 的触发配置：reading-required.yml 的 push/pull_request branches 追加 main，native.yml 的 push branches 追加 main，均保留 codex/framework；native.yml 的 pull_request 不需要新增过滤。**改完触发分支再切默认**，然后用一个一次性 PR（base=main）验证 reading-required 真正在跑，核对 run ID、head SHA、事件及 check 名称/来源。只看到 native run 不算该验证。

若选择 B，不切默认，仍用一次性 PR（base=codex/framework）验证 reading-required 的真实触发与 check 来源。没有 bypass，不能用 admin 代替检查。

任一路径最终都须独立确认 ledger 内容确实在默认分支后，才能期望 Actions workflow 列表出现 ledger 两项。单独创建 main=95100501 或整合基线不含 PR #28 新增的 workflow。reader-total-progress.yml 的默认分支可见性、dispatch 启动与审计结果属于后续不同验证点，本段未触发。

C2 继续等待 owner 明确说“执行”，并按选定方案逐条确认；本段未修改 ruleset、未创建 main、未打开一次性 PR、未解决冲突。

## D. 合并前阻塞项

### tools/reading_corpus/collect.py：两条取证路径须同时保留

| 一侧 | 已核实实现 | 取证能力 |
|---|---|---|
| framework @ 8ca964fc | `source_bytes(entry, mode)`；collect 模式在 `FROZEN_DIRECTORY / entry['path']` 存在时读取本地冻结文件，否则 fetch；collect 校验 sha256 与 size | 发布者内容漂移时仍可读取本地固定输入；缺本地文件时有网络回退 |
| 95100501 | cached 模式先 `recover(manifest_bytes)`；读取 `inputs[entry['path']]`；记录 `input_origin` 与 `artifact_id`，retrieved URL 含 artifact 地址；非 cached 模式 fetch；非 discover 模式校验 sha256 与 size | 从历史 artifact 恢复原始输入并保留 artifact 溯源 |

**断言：任取一边都会丢一条取证路径。** 整份取 framework 会丢掉 artifact 输入及溯源；整份取 95100501 会丢掉本地冻结目录回退。这里记录两条能力，不给来源优先级选边。

建议解（只写，不实施）：在 `source_bytes()` 内加入 cached 分支，保留 collect 读取冻结目录与缺失时 fetch 的路径；让 collect/cached/fetch 三条输入路径统一执行 identity 校验（SHA-256、size 与下载边界），并继续保留 cached 的 input_origin + artifact_id。函数签名、输入上下文和返回溯源结构应由独立修复任务确定。本版不编造函数实现。

“fetch”在此指网络输入路径；当前命令行枚举是 framework 的 discover/collect 与基线的 discover/collect/cached，并没有名为 fetch 的 CLI 模式。若仍保留 discover 作为候选发现机制，应明确其可观察新 identity 的职责，不能因统一采集 identity 校验而无意取消发现能力。

用 `tests/reading_corpus/check_collect.py` 覆盖 collect/cached/fetch 三条路径，包括：冻结文件存在与缺失回退、artifact 恢复及来源字段、网络路径、identity 不匹配拒绝、失败信息保留。现有测试两边分别覆盖冻结目录与 artifact，自动合并无文本冲突不等于语义覆盖完整。测试方案只记录，未编辑或运行。

**该改动属语料取证代码，不由 ledger-guard PR #28 承担。** 必须由独立产品/取证修复任务处理并验收；本轮不解决冲突、不选 ours/theirs、不合并。

## 同批已返回的 ruleset 完整 JSON

命令：`gh api /repos/NoGod3524/EXReader/rulesets/25700819`。

```json
{
  "id": 25700819,
  "name": "EXReader native reading delivery",
  "target": "branch",
  "source_type": "Repository",
  "source": "NoGod3524/EXReader",
  "enforcement": "active",
  "conditions": {
    "ref_name": {
      "exclude": [],
      "include": [
        "~DEFAULT_BRANCH"
      ]
    }
  },
  "rules": [
    {
      "type": "deletion"
    },
    {
      "type": "non_fast_forward"
    },
    {
      "type": "pull_request",
      "parameters": {
        "required_approving_review_count": 0,
        "dismiss_stale_reviews_on_push": false,
        "required_reviewers": [],
        "require_code_owner_review": false,
        "require_last_push_approval": false,
        "required_review_thread_resolution": true,
        "require_extra_approval_for_unattributed_changes": true,
        "allowed_merge_methods": [
          "merge"
        ]
      }
    },
    {
      "type": "required_status_checks",
      "parameters": {
        "strict_required_status_checks_policy": true,
        "do_not_enforce_on_create": false,
        "required_status_checks": [
          {
            "context": "reading-required",
            "integration_id": 15368
          }
        ]
      }
    }
  ],
  "node_id": "RRS_lACqUmVwb3NpdG9yec5UuX3azgGIKdM",
  "created_at": "2026-10-23T01:55:16.162-04:00",
  "updated_at": "2026-10-23T01:55:16.283-04:00",
  "bypass_actors": [],
  "current_user_can_bypass": "never",
  "_links": {
    "self": {
      "href": "https://api.github.com/repos/NoGod3524/EXReader/rulesets/25700819"
    },
    "html": {
      "href": "https://github.com/NoGod3524/EXReader/rules/25700819"
    }
  }
}
```

### 四项限制的配置与含义

- `deletion`：限制删除匹配分支；当前没有可 bypass 的 actor。
- `non_fast_forward`：限制把 ref 更新到不包含原 tip 的历史。它不等于 linear history，也不是禁止 merge commit。若合并提交以当前目标分支 tip 为父提交，目标 tip 是新提交的祖先，因此该 ref 更新是快进；来源历史分歧本身不违反这一规则。实际合入仍须满足 PR 与必需检查。当前预演因内容冲突停下，不能作为可合入结论。
- `pull_request`：要求通过 PR 合入；批准数为 0；要求会话解决；允许的合并方法只有 merge。批准数 0 不等于允许绕过 PR。其余字段原样保存在上方 JSON。
- `required_status_checks`：必需检查是 `reading-required`，来源 integration_id=15368；strict=true，合入前要求相对目标分支最新；do_not_enforce_on_create=false，不启用“创建时不执行”的豁免。检查是否真实产生需要一次性 PR 验证。

规则语义参考：[GitHub 官方 ruleset 规则说明](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets)。配置事实来自本次 API 返回；非快进与合并提交的区别是基于 Git 祖先关系的判断。
