# Final round — complete evidence audit, failed acceptance

Harness `e0e898e1df372fa3b3de4145cf2f1f4ddec01eb4`; run `40229380899`, attempt 1. All jobs terminal. Verifier `121284450082` authenticated all seven original target/source ZIPs and all six programs; `audit_completed=true`, `accepted=false`. No fourth round.

| Target | Native job | Final result |
|---|---:|---|
| Windows |121277857729|17/17 semantic rows pass, modal-descendant focus checked; independent catalog revision/outbox and source bytes unchanged|
| GTK |121277857711|17/17 semantic rows pass; More-menu modal path only, not Ctrl+Shift+R; post-X11 byte sealing passes|
| Android |121277857692|4 rows pass: cancel/import/next/previous. New independent observer fails because expected `files/reader-catalog.db` was not found; remaining 13 rows pending, not product failures|
| macOS |121277857684|15 rows pass including disabled Find no-op; reading XCTest passes. Picker Cancel test fails its unique enabled/hittable native-window descendant precondition at line 68 after 45-second wait. Catalog mutation remains unverified|
| iPhone |121277857658|16 rows pass and both XCTest cases pass, including real picker Cancel and disabled Find no-op; catalog mutation unverified|
| iPad |121277857702|16 rows pass and both XCTest cases pass, including real picker Cancel and disabled Find no-op; catalog mutation unverified|

Guard `121277618988` passed syntax, exact target/SDK scope audit, ten negative controls, prior-round ZIP diagnosis and original D06 log retention. Verification fails only the Android and macOS native-execution errors, not ZIP/program authenticity. Original ZIP identities, actual program hashes/attributes/configuration, complete named raw action rows and cases are in `round3.json`; raw screenshots/AX/XML/native logs and programs remain inside authenticated original Actions artifacts.

## Boundaries and next diagnostic work

- Android final catalog assertion is a harness precondition failure, not demonstrated history mutation. Listing contents were not printed, so exact actual database path is unresolved. Future separately authorized work should record real package storage layout before choosing a catalog path, and separate observation failure from later independent UI cases. Round 2's 15 recorded rows are retained only as round-2 evidence; final actual search submission/disabled checks were not reached and are not granted.
- macOS global Cancel originally matched window and Touch Bar. Final window-descendant restriction still did not prove a unique enabled/hittable target. Current console identifies the exact precondition, not which subcondition failed. Raw native logs and XCTest attachment preserve its tree. Future work should inspect that original tree and select the actual picker sheet, not weaken the assertion or assume the cancel path worked.
- Apple modal keyboard focus, all Apple catalog/source mutation checks, physical keyboards, screen readers, physical devices and complete product are unverified. Native fixture import and page-theme-only settings are explicitly limited. Dedicated Continue is absent in Apple/Android paths; actual book reopen is recorded instead.
- Desktop passed paths do not override D08/D09 independent negative scopes. GTK Ctrl+Shift+R is outside this run; Windows here opens a book before modal paths and does not claim D08 shelf-search restoration fixed.
- Original executable modes/link facts were recorded in the producing jobs before original ZIP upload (desktop attribute JSON; Apple program records and tar). ZIP loss is not repaired by chmod or signing. Android original executable permission metadata beyond APK bytes remains ungranted.

All three complete rounds and D06 failures remain preserved. No implementation changes after this tested harness; final seal changes evidence documentation only with `[skip ci]`.
