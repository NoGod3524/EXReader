# Dropping #267 mask-row reuse: stopped, removal is slower beyond noise

**Result: do not merge the removal. Keep #267 as merged.** Removing the soft-mask row reuse from `src/pdf_softmask.c` (keeping the RGB group commit) made pages 1–21 of `real-mixed-120.pdf` at 1200 px slower by a median **+15.61 ms (+1.78%)**. The branch was slower in **13/16** rounds. In the same rounds, the same-DLL main/main control had a median paired difference of only **+1.50 ms**, with a median absolute difference of **7.66 ms (0.93%)**. That fails the rule fixed before the capture: cost ≤ +9 ms and ≤ +2% ([CRITERIA.md](CRITERIA.md)). Following the task's stop rule, the remaining gates were not run and nothing was forced.

The instrumented build explains the cost directly. Without row reuse, the mask conversion loop does **+14.63 ms** more work per p1–21 sweep (12/12 rounds, range +13.71 to +16.69 ms). That is a separate measurement from the timed A/B, and it matches the timed cost.

## Primary A/B, p1–21 @1200

Main `5580d505b` (D, #267 as merged) vs branch `9ade3a83a` (C, mask-row reuse removed). Positive cost means the branch is slower. [Raw samples](raw/primary-p1-21.json)

| Build | Median sweep (ms) |
| --- | ---: |
| D, main | 878.06 |
| C, branch | 890.98 |
| X, main (control) | 899.91 |
| Y, main (control) | 898.82 |

| Comparison | Median paired | Range | Rounds |
| --- | ---: | --- | ---: |
| **Removal cost, C − D** | **+15.61 ms** | −222.26 to +57.67 ms | **13/16 slower** |
| Removal cost, % of D | **+1.78%** | −19.98% to +5.44% | 13/16 slower |
| **Same-DLL control, X → Y saving** | **+1.50 ms** | −76.19 to +126.42 ms | 9/16 |
| Same-DLL median absolute difference | 7.66 ms (0.93%) | | |
| Cost minus the same round's control | +15.04 ms | −134.50 to +72.62 ms | 12/16 |

- Removal cost was positive on 19 of 21 pages by per-page median (typically +0.5 to +1.3 ms per page). The control's per-page medians were scattered around zero, from −1.55 to +1.28 ms.
- The range is wide because of two drifting rounds (rounds 3–4, D ≈ 1112–1137 ms) and one slow round (16, all builds ≈ 1000–1380 ms). The median, the win count and the per-page pattern do not depend on them.
- 16/16 rounds admitted, 0 rejected. Gate CPU at round start was 3.52–14.89%.
- Pixel parity on p1–21: 22,680,000 active RGBA pixels per build, **0 differences** for C, X and Y against D.

## Instrumentation

Diagnostic DLLs (`probe-C`, `probe-D`) add counters and a `timespec_get` timer around the RGBA-to-mask loop in `build_mask`. They matched main on every p1–21 pixel. Each round ran one child per arm in alternating order (warm sweep, then measured sweep). [Raw probe](raw/probe.json) · [Instrumentation](build_arms.py)

| | D, with row reuse | C, branch |
| --- | ---: | ---: |
| Masks / rows | 21 / 18,900 | 21 / 18,900 |
| Rows reused whole | 13,503 (71.44%) | 0 |
| Pixels copied by in-row reuse | 6,471,003 | 22,661,100 |
| Pixels reaching the sample calculation | 5,397 | 18,900 |
| Mask loop, median per sweep (12 rounds) | 14.89 ms (14.50–15.28) | 29.29 ms (28.42–31.60) |

Each mask has 900 rows. 643 of them repeat the row above, and without row reuse each repeated row goes back through a 1,200-pixel in-row compare loop. That roughly doubles this loop's time on these 21 pages.

## Four-arm comparison, before and after

**Before (verify267, page-matched, 12 rounds, on `d8148bbd2`).** Reproduced from [verify-267-20261118](../verify-267-20261118/REPORT.md), not re-run:

| A, pre-#267 | B, mask rows | C, RGB commit | D, both |
| ---: | ---: | ---: | ---: |
| 990.00 | 977.28 | 970.22 | 948.08 |

| Comparison | Median paired saving | Range | Faster rounds |
| --- | ---: | --- | ---: |
| A → B | +10.91 | −17.55 to +24.11 | 11/12 |
| A → C | +48.66 | +1.99 to +94.67 | 12/12 |
| A → D | +51.96 | +25.69 to +101.82 | 12/12 |
| B → D | +38.86 | +19.01 to +100.60 | 12/12 |
| C → D | +9.45 | −25.05 to +54.13 | 9/12 |
| Interaction | −4.01 | −35.62 to +43.87 | 6/12 |
| Same-DLL control | +8.88 (median absolute difference 21.60) | −56.11 to +43.95 | 8/12 |

**After (this branch on main `5580d505b`).** The removal is the D → C step, with a cost of +15.61 ms (13/16), measured above.

The four-arm repeat on current main captured **only 1 of 12 rounds** before the stop rule ended the run. The values from that round were A 939.20, B 930.15, C 908.35, D 881.77, X 876.76 and Y 872.08 ms. One round has no spread, so the current-main four-arm comparison and the interaction term are **not measured (未测出)**. [Partial capture](raw/four-arm-page-matched.json)

### Reading against verify267

verify267 showed that mask-row reuse **alone** (A → B) is not distinguishable from noise. It did not show that row reuse is free **once the RGB commit is in place**. That marginal step (C → D) was already +9.45 ms there, 9/12 rounds, and it was the quantity this removal depends on. With a quieter same-DLL control in this session (median +1.50 ms, median absolute 7.66 ms, compared with 8.88 and 21.60 ms), the step measures +15.61 ms. The probe independently gives +14.63 ms. So the conclusion "B contributes nothing, so removal can't be slower" does not hold for removal from D. This is not evidence of synergy, because the interaction term is still unmeasured. A roughly constant ~15 ms of mask-loop work saved fits both verify267's A → B and this D → C.

## Gates not run (stopped by the task's stop rule)

| Gate | Status |
| --- | --- |
| p1–21 not slower beyond noise | **Failed** (+15.61 ms, 13/16) |
| CTest | **577/577 passed** in 153.86 s on the branch build. [Output](raw/ctest.txt) |
| Pixel parity, p1–21 | 0 differences / 22,680,000 pixels |
| Pixel parity, full 353,143,200 + 111,897,000 | Not run (未测出) |
| Deck / Word / PPTX / Excel / Chinese ±3% | Not run (未测出) |
| Small-fixture ceilings | Not run (未测出) |
| Peak RSS | Not run (未测出) |

## Protocol

- Four builds from one Release MinGW/Ninja tree (GCC 16.2.0), varying only `src/pdf_softmask.c` and `src/blend.c` taken from `d704cdacc^` / `d704cdacc`. C is byte-identical in source to the branch. Main's renderer sources equal `d704cdacc`. [Build script](build_arms.py)
- Each primary round runs one D/C sweep and one X/Y sweep (X and Y are both main's DLL, each with its own document) under the same idle gate. Which sweep goes first alternates by round. Within each sweep, the AB/BA order alternates per page and the first page's order reverses each round. Only `exr_fixed_render` is timed. [Runner](measure.py) · [Summary](summarize.py)
- Idle gate: no competing build or benchmark process, and a valid 0.5 s sample at ≤15% system CPU before each round. It fails closed by waiting, and a round is re-run if a competitor appears during it. The threshold was not changed. Another session's benchmark held the gate closed from about 21:00 to 22:00 EST. No round was timed during that period.
- Tests used Windows 11 and an Intel Core Ultra 7 256V in Balanced power mode.

## Reproduction

```powershell
$e = 'evidence/drop-mask-row-20261118'; $b = 'build/dropmask'
cmake -S . -B $b -G Ninja -DCMAKE_BUILD_TYPE=Release -DEXR_BUILD_TESTS=ON -DEXR_BUILD_TOOLS=OFF -DEXR_ENABLE_IMAGE_AVIF=OFF
python -B -u "$e/build_arms.py" $b            # A, B, C, D
python -B -u "$e/build_arms.py" $b --probe    # probe-C, probe-D
python -B -u "$e/build_arms.py" $b --ctest
python -B -u "$e/run_all.py" "$b/arms"        # probe, primary, four-arm, parity, validate (resumable)
python -B "$e/summarize.py"
```
