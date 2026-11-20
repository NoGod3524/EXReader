# pptx-20 at 600 px: rectangular clip fix

Status: **in progress** (skeleton written 2026-11-20 before any code change).

Input: `evidence/pptx600-attribution-20261120/REPORT.md`. Dominant draw class named there:
five near-full rectangular clips (fixed viewport clip + four `re W* n` page clips) that
miss the identity shortcut at 600 px because the viewport is 337.5 rows on a 338-row
bitmap, so each builds a dense 600x338 A8 mask and every later draw and the page group
take masked paths.

## Targets

| Gate | Target | Result |
| --- | --- | --- |
| pptx-20@600 vs PDF.js (same session) | <= 1.00x | pending |
| word-5@600 vs PDF.js | <= 0.70x | pending |
| deck@600 candidate vs baseline | unchanged (inside null floor) | pending |
| Small-fixture pixels (pptx-20 600/1200/2400, deck 600/1200, word-5 600/1200) | 111,897,000 px, 0 differences | pending |
| CTest | 577/577 | pending |
| Peak RSS | <= +10% | pending |

## Change

pending

## Measurement method

- Bench lock `ops\bench-lock.ps1 -Holder codex-P600f` held for every timed sweep; sweeps start
  only after in-flight build slots drain. Every compile inside `ops\build-gate.ps1` slot.
- `EXR_IDLE_GATE=off`, >= 11 rounds, all rounds retained, pre-CPU recorded not filtered.
- Same-DLL byte-identical null control in every timed sweep.

## Results

pending

## Verdict

pending
