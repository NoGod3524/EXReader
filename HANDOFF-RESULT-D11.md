# D11 — authorized, first CI pending

Validation **accepted=false**. Neither six-target execution nor focus/keyboard consistency has been established. No build, syntax check, fixture generation, native test, screenshot, artifact download or artifact parsing was run locally. No CI round consumed.

## Identities
- Implementation/base HEAD: `0889f7d1e9a537c6c1b05456547e016b26e1cd85`.
- Branch intended: `codex/reader-dot-d11`; remote branch not published.
- Prepared initial tree: `9a6dcaed7f7154c8523aac249f3e5c939aeffa9b` (GitHub create_tree succeeded; matches initial local index tree).
- Tested harness SHA / final document commit SHA / run / attempt / jobs / ZIP / program hashes: **none**. Tree creation is not a commit, branch publication or execution.
- Windows target `9321de84eb9c8d3d57cafbeaa8b0a28fe2a26a08`.
- GTK target `803098e9df1a365a9b8e206805c2d179aca8501f`.
- Android target `4a04a9cc74dde67f755c87e87b278d63a254a3ac`.
- macOS target `15dab6b2270dc296ed6239db67ced2e22d255e65`.
- iPhone/iPad target `5ac5e1fa4cf6dcbfe81ea14b9f64b6288470164a`.
- Approved SDK source `edddc463c06ed5731195cdb8f06b2df6dff7699e`.

## Retained publication blocker (resolved by fresh approval)
`github.create_commit` to `NoGod3524/EXReader`, parent base above and prepared tree above, was rejected twice, both known not executed. First reason: implementation authorization did not explicitly authorize committing/publishing. Before the sole retry, directly read authenticated owner message `Sentinel_b2607938a984819183c98467ba3faaf5`, plus its frozen GitHub README and D11 page, including “无需再问是否push：自行推功能分支触发Actions”. The second denial still required explicit user approval of the concrete external Git commit. No alternative route or further retry was used.

**Required approval:** create the D11 external Git commit in NoGod3524/EXReader, publish only `codex/reader-dot-d11`, and trigger its maximum three complete Actions iterations. No PR, merge, default-branch write, tag or release.

## Prepared owned source (unvalidated)
- `.github/workflows/reader-dot-d11.yml`: six exact target jobs, max-parallel 2; native builds/tests and original ZIP authentication only in Actions.
- `tests/reader_dot_wave2/d11/`: fresh Windows/GTK builds; Win32, AT-SPI/X11, Android adb and Apple XCTest action drivers; separate source routing index; same-attempt evidence consumer; strict negative controls.
- Complete named action set: back, resume, import, cancel, next, previous, search, directory, records, settings, close.search, close.directory, close.records, close.settings, disabled_noop, continue_after_return, no_unexpected_revision.
- Independent keyboard, screen-reader, physical-device and complete-product grants remain false. Unobserved mobile modal focus / disabled behavior / revision evidence stays pending, never inferred from touch.
- Known D06 failures retained in `docs/reader-dot-wave2/d11/PRIOR-D06.md`; Actions script authenticates round2 and final original failure logs. New driver waits for sheet disappearance, re-queries native trees, uses measured UIKit Menu activation, observes DocumentsUI provider state before Back, preserves UTF-8/POSIX paths and avoids hashing live logs. No GITHUB_SHA override or product edits.
- Windows build is compact ON/raw3 OFF/review OFF; GTK compact ON/raw3 ON; Apple PAGE_THEME ON/raw3 OFF/review OFF; not same-source or same-config six-end acceptance.

## Root continuation
Obtain concrete approval, re-review current owned source (local documentation/prior-log preservation advanced after initial prepared tree), publish through reviewed Git Data route, verify commit/branch identity, then execute at most three complete CI rounds. Do not represent current source as syntax-tested. Seal final evidence documents with `[skip ci]` only after actual terminal results; no docs seal has occurred.

## Fresh approval
Authenticated user approval `Sentinel_3f7a7f4cfa648191a35b1bc973b55f74` at 2026-10-25 19:20:18 UTC explicitly approves D11 commits/push and maximum three Actions iterations. Remote branch absence was rechecked before resuming. Earlier denials remain historical, not bypassed.
