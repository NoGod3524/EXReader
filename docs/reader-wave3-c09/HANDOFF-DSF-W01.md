# DSF Windows W01 handoff

Package: Windows mainline real-UI close-out. No new features, no SDK, no protected module, no
legacy driver and no budget was changed. Everything below was produced only by GitHub Actions;
nothing was built, run, screenshotted, unzipped or parsed on a developer machine.

## Source

| Item | Value |
| --- | --- |
| Branch | `codex/dsf-windows-ui-close` (this package; origin has no other copy) |
| Package start | `683d5524575fd00b3e5e4d447e730fb3ba76fd75` (last original-team driver commit, never run: its message carries `[skip ci]`) |
| Tested source | `d7d5ed98cd11e6c5dee4bb9f58ffc7bdccb265fd` |
| Round | run `40353197461`, attempt `1`, workflow `Team24 Windows native integration` |
| Jobs | `guard` success, `windows` failure, `authenticate` success |

The workflow `reader-team24-windows.yml` gained this branch in its `push` list; its original
`codex/team24-windows` trigger, the guard, the seed, the frozen C09 guard and both budget numbers
(`240` minute job, `2400` s native UI step) are untouched. Before the push, no run existed for this
branch and no other run was in progress for the same source (the previous `codex/team24-windows`
run `40350379758` on `08e1edf7` had already completed as a failure).

## This round: every suite, measured in Actions

| Suite | Result |
| --- | --- |
| `sdk-and-product` (raw SDK, product catalog) | passed |
| `raw-modules` (19 modules incl. the six wave-3 modules) | passed |
| `wave3-host` (`EXReaderWave3.exe`, real host compile) | passed |
| `ui-dependency`, `ui-font`, `ui-fixtures` | passed |
| `native-desktop-geometry` | passed, 1024x768 -> 1280x800 (single request, test 0 / change 0) |
| `retained-compact22` (unchanged compact judge) | passed, **22** checks, `compact22_accepted: true` |
| `retained-raw-owner-suite` (owner probe `suite` + `fresh`) | passed |
| `zip-roundtrip` | **failed** |
| `authenticate` (artifact/report/ZIP/EXE binding) | passed, `verified: true`, `problems: []` |

`zip-roundtrip` did everything except the last step: the ZIP was built, unpacked, every payload file
was checked against the package manifest, the extracted EXE/font/books ran the retained
`--self-test` (**26** checks) and then the five-feature native UI suite from the unpacked
directory. That last suite is the only thing that failed.

### Identity of the packaged original and of the actual program (Actions only)

| Item | Value |
| --- | --- |
| Artifact | `c09-windows-wave3-40353197461-1`, id `12664473529` |
| Artifact upload digest | `d78579c0e37aa056ef090e00550b0585ec23fe66c9bacbed53e0187d5accfc71` (19,109,848 bytes) |
| ZIP | `EXReader-wave3-windows.zip`, 17,500,770 bytes, sha256 `0d088296745bbc5e57e94286938e8a98906428db51cb9dd86e5a5d289ebab1fe` |
| Program (packaged and, byte-identical, extracted `EXReader.exe`) | sha256 `fba0ae7006153a189b59cd738a3e67d602009061c0867d502b436f267bb0d4c6` |
| Retained checks in the package / in the extracted program | 26 / 26 |
| Package manifest | sha256 `ef8b3220a80c9aabba66b0a64c4a15a76314372c46d0ecbf256d7da27c16c491` |
| Public codec | the three blobs of `a911cd0e8405a362dae1bb489190de02c4c81d51` admitted by the guard, unchanged; no independent three-platform codec re-acceptance was run (`40348964690` already passed, not recycled as this package's evidence) |

## Five-feature native UI on the unpacked program: 4 of 16

Passed, in order (real menu ids, real common dialogs, real message boxes on the extracted EXE):

1. `native-menu-entries`
2. `history-back-forward-after-real-location`
3. `annotation-export-cancel-then-real-files`
4. `originals-directory-cancel-then-per-item-results`

Not executed (the run stopped before them): `originals-rerun-reports-existing`,
`font-import-failure-keeps-library-and-frame`, `font-import-and-switch-changes-page`,
`font-restore-builtin`, `sync-status-read-only-unknown`, `sync-status-read-only-failed-session`,
`font-choice-survives-restart`, `annotation-preview-writes-nothing`,
`annotation-confirm-cancel-writes-nothing`, `annotation-confirmed-commit-writes-records`,
`annotation-repeat-is-duplicate`, `annotation-tampered-file-refused`.

A green overall exit or a green non-UI suite is not a success of these five features: 12 of the 16
observations simply did not happen.

### First error, verbatim

```
File "D:\a\EXReader\EXReader\tests\reader_wave3_c09\check_ui.py", line 375, in main
  fill_system_dialog(app, originals)
File "D:\a\EXReader\EXReader\tests\reader_wave3_c09\check_ui.py", line 209, in fill_system_dialog
  app.wait(lambda: not U.IsWindow(dialog), timeout=30)
TimeoutError: Expected host transition did not complete
```

`consumer_sha256 = fba0ae70…`, `count = 4`, `accepted = false`, no `native-file-dialog-controls`
dump was printed, so the filename control was identified, the requested path was written into it
(`set_text` asserts the round-trip), the accept button was enabled, and the dialog still refused to
close during the second `originals` directory pick.

### What this round did prove about the driver fix

`683d5524` identifies the Windows-2022 DirectUI filename control (`Edit` 1001 under `ComboBox` 0
under `FloatNotifySink`) and keeps the unique-candidate assertion and the classic `edt1`/`cmb13`
path. That identification is now exercised for real, twice:

* the annotation **Save** dialog (first accept of the DUI family in this pipeline) wrote
  `a.jsonl` + `a.md` and the export assertions passed, and
* the **folder** picker of the original-export dialog exported the book into the chosen directory
  (64-hex `.txt`, bytes and sha equal to the imported original).

The address bar (`ToolbarWindow32` 1001 under `Breadcrumb Parent`) and the search box were never
selected: the class plus the two exact parent links, plus the single-candidate rule, decided it.

The remaining failure is in the *repeat* pick of the *same* directory. The first pick of that
directory started from a different location and completed; the second opens already positioned at the
requested directory, and typing that same directory into the name field is then not a completion the
dialog accepts. That is an inference from the two runs, not an observation: the round has no dump for
this dialog, so this package does not claim the cause as proven.

## Minimal diff of this package (vs `683d5524`)

```
 .github/workflows/reader-team24-windows.yml | 2 +-
 tests/reader_wave3_c09/check_ui.py          | 13 ++++++++++++-
 2 files changed, 14 insertions(+), 2 deletions(-)
```

* workflow: `branches: [codex/team24-windows, codex/dsf-windows-ui-close]` (only addition).
* `check_ui.py`: after two accepts that did not close the dialog, repeat exactly the `EN_CHANGE`
  notification a real edit sends to that already identified owner (`WM_COMMAND`,
  `MAKEWPARAM(id,0x300)`, `lParam = edit`, sent to the edit's own parent) and accept again. The
  dialog still has to close and the requested file still has to appear; nothing is taken from the
  notification itself, and the unique-candidate assertion is unchanged.

That `EN_CHANGE` repetition is the one unverified piece of this package: it fired only if a dialog
survived two accepts, and in this round no dialog in the `Save`/`folder` family needed it before the
failure. It influences nothing that passed.

## Preserved earlier failures (not recycled)

| Source | Run | Attempt | Result |
| --- | --- | --- | --- |
| `310b4223a3d119555f1d04384af7f5b16b7b582f` | 40274692199 | 1 | failed: compact22 refused on minimum window geometry; wave3 UI stopped at the records location step |
| `1bfd12e27e96549f7e60850bc1cce1f61a47e97b` | 40273584160 | 1 | failed |
| `e8ee47a2fef83b54d3f6da760c19f417abf1f75f` | 40246233974 | 1 | failed |
| `08e1edf7ee37770c7ce210ab85a2ed4a122045f2` | 40350379758 | 1 | failed: 2/16, Save filename identification (see below) |
| `08e1edf7` predecessor run | 40277257970 | 1 | cancelled by its owner |

Run `40350379758` also produced the control dump this package relies on: 47 children of the
`#32770`, exactly one `Edit` (id 1001, parent `ComboBox` 0, grandparent `FloatNotifySink`), the
address band as `ToolbarWindow32` 1001 under `Breadcrumb Parent`, and the search box as
`SearchEditBoxWrapperClass` + `DirectUIHWND` with no `Edit` child. Its artifact is
`12663945607` (ZIP 17,500,770 B, sha256 `8f245e154df69fc5218307bea76de214e1bcfe0ecb96f4c10a5bcc823be163f4`,
EXE `dc2671bf103abc22008110c9b1efb3ec3aa75582f0c30004d122ca100d549b3b`).

The original team's final document is still readable at
`d9c4c20f751f5f277e5ab89c2b111b794b80e551` (`git show`, read-only). Its artifact `12663945607` is
identity-verified and business-acceptance false, exactly as it left it; this package neither
overwrites that record nor reuses it as evidence for the five features.

## Boundaries kept

* No new feature, no coordinate matching, no fuzzy control search, no deleted business rule, no
  removed or relaxed assertion.
* Only `examples/reader.c`, `examples/windows/`, `apps/reader/desktop/windows_*`,
  `tests/reader_wave3_c09/`, `docs/reader-wave3-c09/` and this workflow were touched. The SDK, the
  frozen C09 guard, `apps/reader/windows-account`, the compact/records/raw judges and both budgets
  are byte-identical to the package start.
* Public codec only through the installed
  `reader_reading_state_capture_raw_candidate.h` / `reader_rs_encode_capture_raw_candidate`; no new
  private `extern` was added (the inherited handwritten declaration is gone since `08e1edf7`).
* Artifact identity: verified. Business acceptance of the five features: **false** (4/16).
* This package has spent its one new complete Windows combination round. It does not dispatch
  another one and does not open a diagnostic workflow; the next decision belongs to root.

## One candidate next step, not dispatched, not claimed as verified

Make the folder pick reach the directory from its parent instead of typing the directory the dialog
already shows: for `IFileOpenDialog` + `FOS_PICKFOLDERS`, accept the parent path once (that always
differs from the displayed folder), then accept the requested path, then accept once more. The two
`w3_choose_directory` call sites in `check_ui.py` would pass a folder flag, the file dialogs stay on
the current recipe, and every assertion of `originals-rerun-reports-existing` stays as it is. If root
prefers, the same check can instead be arranged on a second, empty directory that receives a copy of
the file the program itself exported; that also leaves the assertions unchanged but changes the shape
of the check, so it is offered only as the alternative.

## Root follow-up: native common-dialog button
The retained helper filled the exact native filename edit, then sent WM_COMMAND/IDOK with no originating button HWND. Root changed acceptance to the same real BM_CLICK path already used by the rest of this UI driver. All 16 business assertions, cancellation checks, file-byte checks, old suites, ownership checks and budgets remain unchanged. This is a driver candidate, not a verified product correction; the next cloud round determines whether the folder rerun proceeds. Prior 4/16 remains the accepted observation of the earlier failed run.


Root round 40364954464 advanced beyond originals, fonts and the actual failed-account read-only view. The secret scan then attempted to read the live exclusively-held empty library.sqlite.product.lock and failed with PermissionError; report printing also hit cp1252 on Chinese UI evidence. The next candidate asserts the live lock is empty, scans every other live file, closes normally and scans every remaining profile file without exclusions, before the existing process-restart/font check. Console output is explicitly UTF-8. No secret check, business assertion or test budget is removed.


Run 40367648443 reached the second documented exclusive owner file: library.sqlite.product.sqlite.sync-account (account-profiles README contract), before shutdown. The live scan now defers that exact persistent binding as well as the verified-empty product lock; the subsequent post-exit pass still reads every remaining file with no exclusions and checks both UTF-8 and UTF-16 secret bytes. Unknown inaccessible files still fail. Earlier failure and its source/run identity remain retained.


Run 40369325127 stopped at the other exclusive empty product profile lock. Root reviewed the actual CreateFileW ownership sites in examples/reader.c: the profile holds product.profile.lock and library.sqlite.product.lock, both without sharing; the persistent session binding is separate. Both empty lock files now receive the same live-size assertion and mandatory post-exit scan; the binding remains deferred to the full post-exit scan. All other read errors still fail. This correction covers the source ownership contract rather than adding an arbitrary catch-all scan bypass.

