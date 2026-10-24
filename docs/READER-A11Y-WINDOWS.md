# READER-A11Y-WINDOWS: Windows keyboard and accessibility audit

Status: audit package. Tests, workflow and documentation only; the product host,
the SDK and the product database are unchanged. Nothing here is a production fix.

- Source under test: the fixed handoff start `f43baf9182d75907c0cb5d6f77048f27bca8c950` and
  every commit of branch `codex/reader-a11y-windows` above it.
- Build under test: the packaged product host `EXReaderProduct.exe` (product catalog +
  desktop metadata) assembled exactly like `.github/workflows/reader-desktop-sdk.yml`.
- SDK identity: `9854061be331fe603a1822d9b2b36ee357154927`, product schema
  `f32bb8aa18ed3de286900f19ce4230fd93435dd0`. The workflow fails if either tree moves.
- Cloud exit: `.github/workflows/reader-a11y-windows.yml` runs on `windows-2022`, launches the
  real host, and uploads the raw UIA trees, the key trace and the screenshots.

## Method

1. Build the unchanged reading SDK, the product catalog provider, the native metadata
   commands, and the product host; package the payload with its preserved 26-check
   self-test.
2. Launch `EXReader.exe --data <private directory>` with no driver script. From here
   every state change comes from a key event, not from `WM_COMMAND`, not from
   `BM_CLICK`.
3. Preferred transport is `SendInput`: hardware-level input to the focused window, so the
   host's own message loop and `IsDialogMessage` do the work. If the runner session cannot
   deliver injected input, the audit records the `postmessage` fallback in every trace
   line and refuses to claim modifier-chord checks.
4. Controls are identified by `IDC_*` dialog control id plus window class, the identity
   `examples/reader.c` assigns; `host.verified_controls()` fails the run if the binary
   does not create the expected control set.
5. Each claim is one named check with element locator, reproduction steps, expected
   and actual value, severity, evidence reference and a minimal fix suggestion.
6. Visible focus is measured, not assumed: the audited window is captured with
   `PrintWindow(PW_RENDERFULLCONTENT)` while a control has focus and again after focus
   moves, and the pixels inside that control's rectangle are compared.

`audit_completed` (was the evidence collected on this source) and
`accessibility_accepted` (was no blocking finding measured) are separate fields. A
blocking finding forces `accessibility_accepted: false`; the workflow still succeeds when the
evidence is valid, and the job summary lists every blocking finding.

## Check registry

| scope | ids | flow |
| --- | --- | --- |
| shelf | SH-01..SH-07 | main window name, book list, item names, search field, search filtering, refresh/details state, empty-shelf state |
| import | IM-01..IM-06 | path field, import command, keyboard-only import, result text, announcement, focus after import |
| organize | OR-01..OR-11 | details dialog: open, name, title/author fields, favourite checkbox, button keys, Tab cycle, Escape, focus return, owner state, default button |
| reading | RD-01..RD-07 | page element, page text exposure, keyboard reach, visible focus, page turning, position text, select/copy |
| annotation | AN-01..AN-06 | annotation list, comment field, keyboard add, row text, keyboard jump, keyboard delete |
| settings | ST-01..ST-05 | font commands, persistence, per-book-kind state, missing settings surface, access keys |
| keyboard | KB-01..KB-05 | Tab cycle, reverse cycle, command coverage, UIA focus coherence, provider presence |

Severities are `blocking`, `serious`, `moderate` and `info`. Statuses are `pass`,
`fail`, `gap` (capability absent, recorded not invented), `not_verified` (not
measurable with the available transport) and `error` (the audit step itself failed).

## Evidence contract

`verify_report.py` recomputes the verdict instead of trusting the report:

- report `source_sha` equals the checked out commit, `run_id` and `attempt` equal the
  current run;
- every check id is unique, every status and severity is known, every check carries
  steps, expected and actual text, and every scope has at least one check;
- `counts` matches the enumerated checks, the blocking list matches the
  recomputed blocking set, and `accessibility_accepted` matches
  `audit_completed and not blocking`;
- every artifact exists, is non-empty and matches its recorded SHA-256, including at
  least four UIA trees, four screenshots, one focus capture pair and the key trace;
- the required UIA trees contain the expected control ids, and every key event in the
  trace carries a transport and was delivered;
- `screen_reader_verified` must stay `false`.

## What is not verified

- **Screen-reader acceptance.** No NVDA, Narrator or human reading pass is run.
  `screen_reader_verified` stays `false` and the report lists the human review still owed.
- Speech quality, verbosity and reading order inside a page cannot be judged by UIA.
- iOS, Android, GTK, sync, OPDS and network features are out of scope.
- Findings are reported as measurements on this source; the minimal fixes are
  suggestions for the owners of those files (G01/root), not edits made here.

## Reproduce locally (same steps the workflow runs)

    cmake --preset reading-library
    cmake --build --preset reading-library
    cmake --install build/reading-library
    cmake -S apps/reader/desktop -B build/desktop-sdk -DEXR_SDK=build/reading-library/stage \
      -DREADER_METADATA_PREFIX=build/product-stage -DCMAKE_BUILD_TYPE=Release
    cmake --build build/desktop-sdk --config Release
    python tools/build_windows_host.py --sdk build/reading-library/stage \
      --binary build/desktop-sdk/EXReaderProduct.exe --output build/a11y-package --static-reading
    python tests/windows_host/make_fixtures.py --output build/a11y-fixtures
    python -m pip install "uiautomation==2.0.29"
    python tests/reader_a11y_windows/run_audit.py --payload build/a11y-package/EXReader \
      --fixtures build/a11y-fixtures --output build/a11y-evidence
    python tests/reader_a11y_windows/verify_report.py --report build/a11y-evidence/report.json \
      --output build/a11y-evidence/verification.json
