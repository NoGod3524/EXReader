# Gate split status — BLOCKED by GitHub plan

Policy: docs/validation/PERF-BASELINE-POLICY.md; index: evidence/INDEX.md; tracking issue #32. SDK stays 3.42.0.

Prepared workflows: .github/workflows/reading-required-core.yml (protocol/native/profiles/platforms/corpus; no performance) and reading-required.yml (original logic and branch filters retained, comments only). Neither workflow is in the eight protected trees; native.yml is already part of P.

Applied original ruleset 25700819: [reading-required/app15368] → [reading-required-core/app15368], enforcement active. All other fields compare identical, including strict, PR/deletion/non-fast-forward, ~DEFAULT_BRANCH condition and empty bypass. Current default remains codex/framework; ledger/base is not matched by this rule.

Owner authorized a dedicated ledger/base evaluate ruleset. Creation was attempted exactly with enforcement=evaluate, ref refs/heads/ledger/base-20261103, only reading-required-core plus deletion/non-fast-forward, bypass empty. GitHub returned HTTP 422: Enforcement evaluate option is not supported on this plan. Please upgrade to Enterprise to enable it. No staging id was issued, no active fallback was attempted.

Temporary comment-only PR was NOT opened; registration/evaluate acceptance was NOT verified. Split is NOT successful yet. No red/green routing is claimed without the PR. Legacy workflow dynamic verification was replaced by static five-group verification per owner; its branch filters remain unchanged. Plan upgrade or revised owner constraints are required to continue.

C draft #31 targets ledger/base containing V 34278023. Actual C workflow run list is empty ([skip ci]); both added ledger workflows pass narrowed hygiene. P #30 remains draft. No catalog/assertion/SDK version change, default branch switch, force push or full native matrix run.
