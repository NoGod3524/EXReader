# Windows sync/account handoff

Status: **partial; not accepted**. Branch `codex/terra-wave-windows-sync` starts at
`f34a4f27`. The host change in `fcbdf05c` makes cancelled staging retryable,
handles cancellation arriving between worker completion and its UI callback,
and limits the Cancel button to account work or a live session. This staging
cancellation path still needs a targeted native UI test, including cancellation
at that callback boundary. Receive/import cancellation and retry also remain
uncovered by the retained account suite.

Actions run [40627051775](https://github.com/NoGod3524/EXReader/actions/runs/40627051775)
on `fcbdf05cbbf9b838d297aef7b377560aaeb7282a` passed the composed Wave3 host
step but failed preparing the historical capture consumer: it requested exact
reading-state 0.1.0 while the composed host installs 0.2.0. `ad1b6f53` adds a
separate 0.2.0 build definition for the unchanged consumer.

Actions run [40628028500](https://github.com/NoGod3524/EXReader/actions/runs/40628028500)
on `ad1b6f5359607a57b302966bf9a6e4105e144cee` passed the composed host and
consumer build, but the legacy import helper timed out because the compact host
opens a native file picker. The subsequent commits adapt that interaction; the
32 named assertions and their timeouts remain intact. Superseded runs
[40628978147](https://github.com/NoGod3524/EXReader/actions/runs/40628978147)
and [40629000463](https://github.com/NoGod3524/EXReader/actions/runs/40629000463)
were cancelled while correcting the adapter.

Actions run [40629033536](https://github.com/NoGod3524/EXReader/actions/runs/40629033536)
on `86f6db1f806f1fb85e8892baccfb4be43c706361` passed the composed Wave3 host
and consumer preparation, and the account replay recorded 29 of 32 named checks,
including actual network failure/retry, network cancellation/retry, close during
scan, credential handling and secret scanning. It failed at the retained
`run_sync` completion wait after planting a metadata-only book with no original:
the host reported FINISHED network state but receive incomplete with one original
waiting and Retry available. The expected completion assertion was not changed.
The failure log and screenshots are retained by that run. Determine how this
expected missing-original condition should interact with the retained test and
product completion semantics, then run the complete suite against one source.
Do not count the 29 recorded observations as a passing 32-case suite.

The current Wave3 status view evidence covers a real failed session and read-only
capture, not every state transition. Complete native acceptance must also observe
stage and receive/import cancellation and retry, read-only status across the
relevant transitions, and verify secrets and retained data. Credential Manager
unavailability and physical remote HTTPS remain outside the historical suite's
scope. No shared sync module was changed; coordinate integration with the other
platform branches before changing shared files. The blocked D13 experiment was
not run or altered.

## Continuation: missing originals and exact-source replay

On `bf6d3765b36688b00235f9edfaa1d78b03d0c69e`, the Windows account
receiver can fetch a missing original for already-retained metadata on retry.
It downloads to a unique private name, verifies the expected byte count and hash,
and publishes without replacing an existing cached original. A 404 remains
waiting; transfer/verification failures are reported separately. The account
message and read-only status now expose incomplete local receive. The fixture
uses actual bytes and their real hash instead of the impossible all-`e` digest;
it first observes the absent original, checks the read-only status without
changing either database, publishes those bytes, retries, and verifies the mapped
original. The original 32 named checks and 240-second completion wait remain.

[Actions run 40630766485/1](https://github.com/NoGod3524/EXReader/actions/runs/40630766485)
passed the composed Wave3 host and consumer builds. The account test observed
staging cancellation followed by retry and progressed through the new absent
original/status/retry assertions and 29 original named checks. The separate
organization suite passed, including cancellation during original import,
retry without a duplicate, and exact original readback hashes. These observations
are on the same source and executable; the overall run **failed** and the full
32-case account suite is **not accepted**.

The retained suite subsequently plants a concurrent book head, a book with a
missing parent, and a tombstone. Its `RB.run_sync` still requires the literal
completion message before inspecting those deliberately unresolved heads. The
host instead reports receive incomplete, with one concurrent version and one
missing parent; after the unchanged 240-second wait, the test fails. The next
retained assertion also expects the missing book parent under `待依赖`, whereas
the current host classifies it as `缺祖先`. Neither assertion was changed or
satisfied through a false completion message. The product/test contract for
this conflict fixture must be reconciled before granting acceptance; replaying
the same test without that reconciliation will repeat the mismatch. Status
across every cancellation and retry transition remains incomplete; the retained
Wave3 checks cover unknown and failed sessions, and this continuation covers the
missing-original receive state.

No shared sync module or parallel worktree was edited. Android, Apple, and Linux
sync branches progressed independently from the original base and must be
integrated by their owners; this branch has not merged their changes.
