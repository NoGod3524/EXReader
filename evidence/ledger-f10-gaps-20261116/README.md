# F10 product gaps closed

PR: https://github.com/NoGod3524/EXReader/pull/229. Branch: `codex/ledger-f10-gaps`. Do not merge.

Final run [43889788329](https://github.com/NoGod3524/EXReader/actions/runs/43889788329), source `443fbcd7879aeec6bbf05c2961487f25ab909c30`, passed both the Windows account job and its strict same-source summary. [Verified summary](43889788329/summary/verified.json); [artifact custody audit](../../_audit/43889788329.json).

| Gap | Product change | Final result |
| --- | --- | --- |
| Comment Shift+Tab | In this non-shell profile, control 122 existed but was hidden. Restore the native shelf, search, notes and comment surfaces with actual layout. The existing edit subclass already releases Tab; visible control 122 now participates in native reverse traversal. | Accessibility **24/24**, including the complete enabled-stop Tab cycle. |
| Native removal | Restore native Open 103 and local-copy removal 104 with Alt mnemonics and Tab stops. Removal confirms with No selected by default, then uses the existing `JOB_PRODUCT_DELETE` catalog/SDK operation. | Bookshelf **13/13**, including removal after opening the imported original outside the cached first page. |
| Planted heads | Count received book tombstones explicitly without projecting them into retained book rows. Recheck revision selection before importing an original, so deleted or unresolved history cannot cause an implicit re-import. Concurrent and missing-parent heads remain untouched. | Account **32/32**, including exact title/deleted rows, head sets, revision counts and unchanged active page/offline readability. |
| Interrupted filter/open | Handle Ctrl+O before the page's busy-key guard and keep native Open operable during shelf queries. Both enter the existing superseding worker queue, which cancels the filter and retries it after the accepted book opens. | Worker **5/5**, including the original fifth assertion. |

Product files: `examples/reader.c` and `apps/reader/desktop/windows_accounts.inc`.

Removal has the existing local-copy semantics: the local mapping and SDK copy are removed while global metadata and revision history remain. It does not publish a global book tombstone. This matches the original shelf contract, which requires the metadata row to remain and the local mapping count to return to 2202. Received global tombstones stay explicit in revision history and account status; receiving one does not remove the retained local copy.

## Test contract changes

The metadata inventory originally required exactly 14 IDs. Adding real buttons 103/104 changes that product contract to exactly 16 IDs. The expectation now includes both new buttons, preserves every original ID, and retains exact set equality and all 18 named metadata checks. This is an inventory update for added product controls, not a relaxed behavior assertion.

The retained worker helper activates the actual removal button, waits for its native Yes/No dialog, and answers Yes. All original shelf/worker data assertions remain. The account suite adds the stronger requirement that the tombstoned book no longer appears as waiting for an original.

Run [43887968876](https://github.com/NoGod3524/EXReader/actions/runs/43887968876), source `d856cb1d985a812d1440ad93d3e7d620cf4da701`, already passed all four gap suites. Its metadata suite stopped at the old inventory, so the strict summary correctly rejected the run. Its original failed summary, exact inventory traceback and verified artifact hashes are retained in [that run directory](43887968876/) and [audit](../../_audit/43887968876.json).

## Final validation

| Suite | Passed |
| --- | ---: |
| Original Windows UI | 158/158 |
| Product regression | 10/10 |
| Worker regression | 5/5 |
| 2202-book native bookshelf | 13/13 |
| Typed metadata and recovery | 18/18 |
| Account UI | 32/32 |
| Keyboard/UI Automation | 24/24 |
| Strict same-source summary | accepted, zero problems |

Both final artifact ZIP byte lengths and SHA-256 hashes match GitHub metadata. Audit records contain `evidence_ok: true`, the actual source SHA, and per-file hashes. [Native screenshot](43889788329/account/account-ui158/A/01-epub-page1.png) and [resized screenshot](43889788329/account/account-ui158/A/02-resized.png) are retained from the same run.

Local MSVC `cmake --build build/account-host --parallel 6` compiled and linked both hosts with exit 0. The required prepush script passes; CI hygiene reports `violations=0`; the fixed catalog has 108 requirements and groups 12/84/12. Three standard-library keyboard transport tests, SDK version consistency, and its rejection tests pass. See [local validation](local-validation.json) and the adjacent command outputs.

F10 is verified using this run together with its existing privacy/identity/TLS/GTK evidence. The catalog is **verified 106 / partial 0 / pending 2**; all other requirement records remain unchanged. The existing account report's uncovered scope and six-platform product scope remain as recorded; UI Automation is not a screen-reader narration test.

A separate PR check, [R2 corpus job 133377610342](https://github.com/NoGod3524/EXReader/actions/runs/43889800377/job/133377610342), failed while collecting four Gutenberg assets with HTTP 503 responses. It is outside this F10 run. A job retry was requested but GitHub rejected it while the parent workflow was still running.
