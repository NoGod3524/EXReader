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
Not yet run. Results are appended below after each Actions run (failures retained).
