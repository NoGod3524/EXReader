# Gate split status — static verification complete; first real PR pending

Policy: docs/validation/PERF-BASELINE-POLICY.md; index: evidence/INDEX.md; tracking issue #32. SDK stays 3.42.0.

Prepared workflows: .github/workflows/reading-required-core.yml (protocol/native/profiles/platforms/corpus; no performance) and reading-required.yml (original logic and branch filters retained, comments only). Neither workflow is in the eight protected trees; native.yml is already part of P.

Applied original ruleset 25700819: [reading-required/app15368] → [reading-required-core/app15368], enforcement active. All other fields compare identical, including strict, PR/deletion/non-fast-forward, ~DEFAULT_BRANCH condition and empty bypass. Current default remains codex/framework; ledger/base is not matched by this rule.

Owner authorized a dedicated ledger/base evaluate ruleset. Creation was attempted exactly with enforcement=evaluate, ref refs/heads/ledger/base-20261103, only reading-required-core plus deletion/non-fast-forward, bypass empty. GitHub returned HTTP 422: Enforcement evaluate option is not supported on this plan. Please upgrade to Enterprise to enable it. No staging id was issued, no active fallback was attempted.


C #31 merged into ledger/base (head d0c95336, merge68cc0ec5); the late handoff receipt and R-entry records merged through follow-up #34 (merge071c7914). Actual C workflow run list is empty ([skip ci]); both added ledger workflows pass narrowed hygiene. P #30 remains draft. No catalog/assertion/SDK version change, default branch switch, force push or full native matrix run.
