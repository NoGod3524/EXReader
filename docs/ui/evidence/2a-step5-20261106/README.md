# 2a step 5 evidence

**Current PASS: font reflow preserves the exact visible content head. Final check exit=0; 12/12 stepped transitions, 8/8 requested cycle transitions; all eight existing checks green; fixed-font Latin Sample 12 images, 0 differing client pixels.**

See [anchor fix report](../../2A-STEP5-ANCHOR-FIX.md) and [current evidence](anchor-fix/README.md). The record/ links below retain the previous 3096ca7f run, including its historical failure.

See [acceptance report](../../2A-STEP5-ACCEPTANCE.md) for the eight numbered measurements, all 30 control state colour comparisons, INI before/after and the failing first-line offsets.

- [Machine-readable result](record/result.json)
- [Original phase-a/b/c comparison](record/phase-regression/comparison.txt)
- [Baseline-repeat and changed failure sets](record/phase-regression/result.json)
- [RGB-only negative test](record/regression/negative.txt)
- [Light screenshot](record/settings/light.png), [dark screenshot](record/settings/dark.png)
- [Token authority snapshot](record/DECKMARK-TOKENS.md), [build and input hashes](record/metadata.json)

Every GUI process stayed at (-32000,-32000); foreground observations = 0. All captures use PrintWindow, including a separate PrintWindow of the overlapping child panel. Focus colour states are drawing-state injection. No workflow run was canceled or manually started.
