# Acceptance rule (fixed 2026-11-18 before any timed capture)

Comparison: main `5580d505b` (D, #267 as merged) vs this branch (C, mask-row reuse removed, RGB group commit kept).
Cost = branch minus main, per round, p1–21 of `real-mixed-120.pdf` at 1200 px. Positive cost = branch slower.

1. **Primary (p1–21).** ≥12 admitted rounds, AB/BA alternating per page, first-page order reversed each round,
   with a same-DLL main/main control sweep in every round under the same idle gate.
   - PASS if the median paired cost is ≤ +9 ms **and** ≤ +2% of main's median sweep
     (the stricter of the two bounds in the task, plus the 2% bound).
   - Also reported, not loosened: the cost against the contemporaneous same-DLL control
     (median of the control's paired differences, and its median absolute difference), range and win count.
   - If the median cost exceeds the bound: stop, keep #267 as merged, hand back the data.
2. Page types (full 120-page sweep, 12 rounds): Deck 22–51, Word 52–76, PPTX 77–116, Excel 117/119 and
   Chinese 118/120 (separate 24-round capture) each within ±3% median paired change.
3. Pixel parity: 353,143,200 large + 111,897,000 small active RGBA pixels, zero differences against main.
4. CTest 577/577.
5. Small fixtures p50: pptx@600 ≤ 0.844, pptx@1200 ≤ 1.729, deck@1200 ≤ 15.4, word-5@1200 ≤ 5.75 ms
   (absolute ceilings; main's own p50 is reported alongside, since earlier reports show main itself can exceed some).
6. Peak RSS: no matched-pair increase above 10%.

Idle gate: CPU ≤ 15% from a valid 0.5 s sample and no competing build/benchmark process; fail closed (retry, never time a round otherwise). Threshold is not changed.
