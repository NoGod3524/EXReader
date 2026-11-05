# Claude local background handoff — 2026-10-29

The user's corrected requirement is **local Claude CLI background sessions using their own logged-in subscription usage**, Sonnet 5.5, Medium. Do not create Claude cloud tasks. Do not use computer/browser automation or export credentials.

The official CLI actually started three isolated local sessions from exact baseline `bd28d4946f17a184dd3cd47a584cf49fce34e973`:

| Task | Background ID | Dedicated local/remote branch |
| --- | --- | --- |
| C1 installed Android Sync | `73f87c47` | `claude/local-c1-android-sync-20261029` |
| C2 actual product performance | `4e0c44a1` | `claude/local-c2-product-performance-20261029` |
| C3 delivery/licenses | `c0da3128` | `claude/local-c3-delivery-licenses-20261029` |

Each actual startup log reports `Sonnet 5.5 with medium effort · Claude Pro`; `claude agents --json` confirms local processes working under `C:/Users/Oscar/exreader-local-usage-20261029/c1`, `c2`, and `c3`. Normal auth is `claude.ai` / firstParty / Pro; no API-key, auth-token or custom-base-URL environment override is present. Dispatch does not grant acceptance.

Use `claude agents --json`, `claude logs <id>`, and `claude attach <id>` to inspect existing sessions. `Start-Claude-Handoff.ps1 -Task C1` (C2/C3) uses `--bg`, the full model ID and `medium`. It reuses an active task in the expected worktree instead of duplicating it, refuses disabled network/API overrides, and requires an isolated task branch. It does not create worktrees. Never remove its guard to bypass environment policy.

Three cloud sessions were mistakenly created before the correction. Stop-work messages were delivered to all three. Their historical IDs are retained in `docs/reader-total-progress/handoff-resume-20261029.md`; they are not the local sessions above.

All prompts preserve Actions-only build/test/fixture/benchmark/artifact analysis, independent branches, frozen assertions and budgets, and prohibit PR/default-branch merge/tag/Release. The built-in agents retain separate Apple and Windows migration ownership. The fixed catalog remains 95/108.
