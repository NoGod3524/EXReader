# C10 desktop accessibility (GTK + Windows) — 2026-10-30

Worker: EXReader C10 (Sonnet 5.5 medium). Branch `claude/dot-c10-a11y-desktop-20261030`, base `343bb94eb6513beaf5b344e7828342f6602a3b7b`.
Owned paths only: `tests/reader_final_a11y_desktop_20261030/**`, `.github/workflows/claude_c10_a11y_desktop_20261030.yml`, `scripts/audit/claude_c10_a11y_desktop_20261030.py`, this file.

## What is run (GitHub Actions only)
- GTK (ubuntu-22.04, Xvfb + openbox + D-Bus AT-SPI): existing `tests/reader_a11y_gtk` audit, xdotool keystrokes, AT-SPI tree dumps and screenshots, then the new exit probe.
- Windows (windows-2022): existing `tests/reader_a11y_windows` audit (SendInput keyboard, UI Automation trees, screenshots, key trace), then the new exit probe.
- Aggregate job maps checks onto bookshelf / import / reading / annotation / settings / exit and records focus order, accessible name/role/state, interaction logs and screenshots by sha256.

## Verdict rules
- `tree` (name/role/state/focus order), `operable` (a keyboard action performed with its effect observed) and `screen_reader` are separate.
- A surface passes only if tree and operable both pass. Existence of controls alone yields `operable: unproven`.
- `not_verified`, `gap`, `error`, missing check → never a pass.
- `screen_reader` is always **pending**: no Orca/NVDA/Narrator runs here and it is never claimed.

## Status
No GTK/Windows accessibility audit has executed on this source yet. **Screen reader: pending. No accessibility pass is claimed.**

### Run 41087134763 / attempt 1 / SHA 77a03979 (initial) - failed
Self-test asserted all-pass for every GTK surface, but GTK reading/annotation have no keyboard-action check (correctly `unproven`). Build/audit steps were skipped; exit probe failed (no package).

### Run 41087404539 / attempt 1 / SHA 79cb52ea (fix 1) - failed
Second wrong self-test expectation (reading verdict). Same skip/exit failure.

### Run 41087627767 / attempt 1 / SHA c27091bb (fix 2) - failed
Self-test and owner guard passed. GTK job 124172846726 and Windows job 124172846316 failed at product-host CMake configure (`apps/reader/desktop/CMakeLists.txt:91`): "Set READER_ORIGINAL_HASH_PREFIX or EXREADER_ORIGINAL_HASH_PREFIX to the installed OPDSHash prefix". The old a11y recipe lacks the original-hash package; audits and exit probes did not run. Final aggregate job succeeded with no evidence (all surfaces incomplete).

### Blocker for coordinator
Both host builds need the OPDSHash/original-hash prefix (and likely other newer packages: raw3, preferences, batch import). Use the producer build recipe from `tests/gtk_sdk342_package/run.py build` (GTK) and `tests/reader_wave3_c09/build.py` (Windows), or supply the prefix. Diagnostic budget (initial + 2 fixes) is spent.

