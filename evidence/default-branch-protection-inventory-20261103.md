# 默认分支保护盘点 · 2026-11-03

## 查询范围与返回

仓库：`NoGod3524/EXReader`。以下均为只读 GET 查询。

| 命令 | 返回 |
|---|---|
| `gh api /repos/NoGod3524/EXReader` | `default_branch: codex/framework`；当前凭据 `admin: true` |
| `gh api /repos/NoGod3524/EXReader/rulesets` | 1 个规则集：`25700819`，`EXReader native reading delivery`，target=`branch`，enforcement=`active`，source_type=`Repository` |
| `gh api /repos/NoGod3524/EXReader/branches/codex/framework/protection` | HTTP 404，`Branch not protected`；gh exit 1 |
| `gh api /repos/NoGod3524/EXReader/branches/codex/framework/protection/required_status_checks` | HTTP 404，`Branch not protected`；gh exit 1 |
| `gh api /repos/NoGod3524/EXReader/rulesets/25700819` | 规则集详情，见下表 |
| `gh api /repos/NoGod3524/EXReader/rules/branches/codex/framework` | 返回该规则集的 deletion、non_fast_forward、pull_request、required_status_checks 四项生效规则 |
| `gh api /repos/NoGod3524/EXReader/branches/main` | HTTP 404，`Branch not found`；gh exit 1 |

传统 branch protection 两个接口返回 404；ruleset 生效接口返回四项规则。404 不表示当前默认分支没有 ruleset 约束。

## 当前默认分支生效规则

规则集名称：**EXReader native reading delivery**（ID `25700819`）。

- target：`branch`；enforcement：`active`。
- 条件：`ref_name.include = ["~DEFAULT_BRANCH"]`；`ref_name.exclude = []`。
- bypass：`bypass_actors = []`；`current_user_can_bypass = "never"`。当前凭据虽有 admin 权限，规则集仍明确返回不能 bypass。

| 名称 | 规则类型 | 生效参数 | 必需检查 | 是否允许 bypass |
|---|---|---|---|---|
| EXReader native reading delivery | `deletion` | 限制删除 | — | 列表为空；当前用户 never |
| EXReader native reading delivery | `non_fast_forward` | 限制非快进更新 | — | 列表为空；当前用户 never |
| EXReader native reading delivery | `pull_request` | 必须经 PR；批准数 0；要求会话解决；只允许 merge 方法 | — | 列表为空；当前用户 never |
| EXReader native reading delivery | `required_status_checks` | strict=true；do_not_enforce_on_create=false | `reading-required`，integration_id=`15368` | 列表为空；当前用户 never |

PR 规则完整参数：

```json
{
  "required_approving_review_count": 0,
  "dismiss_stale_reviews_on_push": false,
  "required_reviewers": [],
  "require_code_owner_review": false,
  "require_last_push_approval": false,
  "required_review_thread_resolution": true,
  "require_extra_approval_for_unattributed_changes": true,
  "allowed_merge_methods": ["merge"]
}
```

必需检查规则完整参数：

```json
{
  "strict_required_status_checks_policy": true,
  "do_not_enforce_on_create": false,
  "required_status_checks": [
    {"context": "reading-required", "integration_id": 15368}
  ]
}
```

## 默认分支换成 main 后的匹配判断

当前规则集按 `~DEFAULT_BRANCH` 匹配，未按 `codex/framework` 字面名称匹配，且无排除项。若默认分支改为 `main` 且规则集配置不变，同一个规则集（相同 ID、名称、四项规则、必需检查与 bypass 配置）将匹配新的默认分支 `main`。这是同一规则集的默认分支匹配条件随设置变化，不是自动创建同名规则集。

当前传统 branch protection 接口没有返回可供继承的配置。当前 `main` 分支接口返回 `Branch not found`，因此本次未观察到 main 上的实际生效状态；上述 main 匹配判断基于返回的 `~DEFAULT_BRANCH` 条件。该条件不证明 main 会产出或通过 `reading-required` 检查。

## 本段执行边界

本段只执行以上 GET 查询并生成本清单。未改任何远端 ref，未改 Settings，未创建 main，未修改保护规则，未触发 workflow。C1、C2 未执行。
