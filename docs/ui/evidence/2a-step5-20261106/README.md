# 2a step 5 evidence

**Overall FAIL: the nonzero page-head anchor moves when stepping font size.**

See [acceptance report](../../2A-STEP5-ACCEPTANCE.md) for the eight numbered measurements, all 30 control state colour comparisons, INI before/after and the failing first-line offsets.

- [Machine-readable result](record/result.json)
- [Original phase-a/b/c comparison](record/phase-regression/comparison.txt)
- [Baseline-repeat and changed failure sets](record/phase-regression/result.json)
- [RGB-only negative test](record/regression/negative.txt)
- [Light screenshot](record/settings/light.png), [dark screenshot](record/settings/dark.png)
- [Token authority snapshot](record/DECKMARK-TOKENS.md), [build and input hashes](record/metadata.json)

Every GUI process stayed at (-32000,-32000); foreground observations = 0. All captures use PrintWindow, including a separate PrintWindow of the overlapping child panel. Focus colour states are drawing-state injection. No workflow run was canceled or manually started.
