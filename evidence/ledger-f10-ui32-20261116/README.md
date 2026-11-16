# F10 Windows UI migration

Branch: `codex/ledger-f10-ui32`. Draft PR: https://github.com/NoGod3524/EXReader/pull/228.

The account workflow builds `apps/reader/windows-account` without the shell profile. Its real HWND inventory contains IDs 118–128, 137, 150 and 151. Controls 101/102/117 are absent; the shelf list, shelf search, notes list and comment editor exist but are hidden. See the [captured inventory](43868930952/account/account-a11y/control-inventory.json).

| Old observation/action | Current native observation/action |
| --- | --- |
| Path edit 101 and import button 102 | Ctrl+I on page 123 opens the system picker; locate its actual filename Edit through edt1/cmb13 or Edit 1001 / ComboBox / FloatNotifySink; accept with a real keyboard event on Open (IDOK 1). |
| Import/cancel enabled state used as worker readiness | Refresh 127 is enabled after the worker/pending chain completes. |
| Worker cancel button 117 | Request native window Close with the worker gate still armed; require exit 0, restart, and verify the accepted book ID/session ID and reconstructed shelf. Verify cache eviction before requesting Close. |
| Open 103, selection 107, copy 108, previous/next 105/106 | Ctrl+O, Ctrl+A, Ctrl+C, Page Up/Page Down on page 123. |
| Background import accessibility state | Assert the page shortcut target and Refresh both report disabled under the modal details dialog. |
| Tab-cycle start at path 101 | Start at visible page 123; require exact coverage of the live visible/enabled WS_TABSTOP set, each visited once, and a closed cycle. |
| Metadata assertion requiring every ID 100–127 | Assert the exact live 14-control ID set and resolve every HWND, retaining an 18-check suite. The inventory check is renamed to describe the current contract. |
| Mapping fault recovery wait | After releasing the injected writer lock and closing the account dialog, press real Refresh 127 before waiting for all five repaired mappings. |
| Cloud-only fixture setup | Wait for incomplete reception and require “等待原件 1” when the deliberately planted metadata has no original. Retain the exact projected title/deleted-state assertion. |
| Planted-conflict scan completion wait | Wait for the current “接收尚未完成” state, then retain the exact conflict/pending/tombstone counters and all data/head/page assertions. |
| Pending-parent counter | Read “缺祖先” for the planted missing-parent head; additionally require the distinct “待依赖” counter to remain zero. Concurrent and tombstone counts still must each equal one. |

The current cancellation test follows the native Close path, which sets the worker's cancellation flag, then verifies accepted state after restart. The bookshelf deletion invariant remains required and fails because this profile exposes no current delete action. The accessibility suite retains its comment Tab/Shift+Tab, open/delete mnemonic and full tab-cycle requirements.

The workflow now attempts independent retained suites after a packaged build even if an earlier suite fails. The strict summary still requires every retained report, 32 account checks and 24 accessibility checks. Failed account/accessibility reports retain their completed checks and source/run/attempt; control inventories contain IDs, classes and visibility/enabled state.

Final run [43868930952](https://github.com/NoGod3524/EXReader/actions/runs/43868930952), source `ff9c470b9d3325f5ba99dc728549f43e6bf2038c`, completed with **failure**. The actual host and SDK compiled successfully. The [strict summary](43868930952/summary/verified.json) recomputed the artifact digest and rejected incomplete acceptance.

| Suite | Final result |
| --- | --- |
| Original UI158 | 158/158 passed. |
| Product regression | 10/10 passed. |
| Native metadata | 18/18 passed. |
| Account UI | [29/32 completed](43868930952/account/account-ui/account-ui.json). The corrected conflict counters pass; check 30 fails the unchanged tombstone row expectation. Checks 31–32 are not reached. |
| Accessibility | [2/24 completed](43868930952/account/account-a11y/a11y-ui.json). Comment Shift+Tab does not return focus to control 122. The remaining checks are not reached. |
| Worker regression | Native Close cancels the gated candidate and accepted state survives restart. The fifth interrupted-filter/open assertion fails; no complete worker report is written. |
| Bookshelf regression | The final delete action has no current native UI equivalent in this profile; no complete shelf report is written. |

Remaining account check: `planted_concurrent_pending_and_tombstone_heads_stay_explicit_without_projection` requires the planted book's `(title, deleted)` row to remain `('Cloud Only Conflict', 0)`. That data assertion fails after the current UI correctly reports one concurrent head, one missing-parent head, one tombstone and zero dependencies. Its expectation is retained. [Final tracebacks](43868930952/failures.txt) identify all four failing suites. Completing F10 requires resolving this tombstone expectation/behavior and the retained filter/open, delete and comment-focus requirements, then passing the full 32/24 suites and strict summary.

Downloaded artifact ZIP byte lengths and SHA-256 digests match the GitHub artifact metadata. The [audit](../../_audit/43868930952.json) binds retained files to their actual source and records failed acceptance separately from verified artifact integrity.

Local validation: MSVC `cmake --build --preset reading-library` completed with exit 0; the required prepush code/docs checks pass; CI hygiene reports `violations=0`; three standard-library transport/locator tests pass. SDK version consistency and its rejection self-test pass after remapping the unchanged historical literal's live line from 544 to 543 in `tools/version_literal_exceptions.json`.

Final F10 state: **partial**. The ledger denominator remains 108 with foundation 12 / host 84 / final 12; other requirement records and F10's existing verified evidence references are unchanged.
