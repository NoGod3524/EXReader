# C lane (p1-21 gradient + soft mask) acceptance - opus-Cacc

**Verdict: FAIL / incomplete: fixture gates : Frozen fixture gate(s) missed**

Run directory: `evidence/realmixed-gradient-mask-20261119/opus-Cacc-20261119-155040`

- Control: fresh build of main `9c2443edfaaa1fde34993cb481ae047c3641a443`, SHA-256 `384B2098F283F8599418DAC5CB84CCFA2CC95A5150BDD46FD3A60FA3DC8B1051` (same toolchain and EXR_* options as the candidate tree).
- Candidate: `D733D2FB4BFE98B1C0BD67F9CFA6754087BEE709DF8690837418C64D47C4F490` (not rebuilt). Note: candidate branch base is 2c27a907a, so it does **not** contain #271 (affine_image.c); control does.
- PASS pixels: large 353,143,200 px / 0 differing; small 111,897,000 px / 0 differing.
  - pdf-large/image-heavy-100.pdf@1200: 100 pages, 112,872,000 px, 0 differing, mismatched pages []
  - pdf-large/real-mixed-120.pdf@1200: 120 pages, 131,317,200 px, 0 differing, mismatched pages []
  - pdf-large/vector-heavy-100.pdf@1200: 100 pages, 108,954,000 px, 0 differing, mismatched pages []
  - pdf-hybrid-real/pptx-20.pdf@600: 20 pages, 4,056,000 px, 0 differing, mismatched pages []
  - pdf-hybrid-real/pptx-20.pdf@1200: 20 pages, 16,200,000 px, 0 differing, mismatched pages []
  - pdf-hybrid-real/pptx-20.pdf@2400: 20 pages, 64,800,000 px, 0 differing, mismatched pages []
  - pdf-ppt/deck.pdf@600: 15 pages, 3,042,000 px, 0 differing, mismatched pages []
  - pdf-ppt/deck.pdf@1200: 15 pages, 12,150,000 px, 0 differing, mismatched pages []
  - pdf-hybrid-real/word-5.pdf@600: 5 pages, 2,331,000 px, 0 differing, mismatched pages []
  - pdf-hybrid-real/word-5.pdf@1200: 5 pages, 9,318,000 px, 0 differing, mismatched pages []
- PASS CTest re-run: 100% tests passed out of 577; Total Test time (real) = 129.16 sec
- PASS RSS image-heavy-100: control 146.5 MiB, candidate 125.9 MiB, -14.07% (cap +10%).
- PASS RSS real-mixed-120: control 107.2 MiB, candidate 93.1 MiB, -13.18% (cap +10%).
- PASS RSS vector-heavy-100: control 78.4 MiB, candidate 60.6 MiB, -22.69% (cap +10%).
- PASS p1-21 (real-mixed-120@1200, 15 rounds): candidate median saving +321.672 ms (A 851.2 -> B 489.5 ms/round), range [276.963, 415.233], 15/15 faster; null median -3.879 ms, range [-42.008, 24.819].
  - null pre-CPU %: min 19.5 / median 29.4 / max 54.5; per round [19.5, 28.1, 35.8, 54.5, 29.4, 32.5, 24.5, 25.3, 24.0, 25.3, 29.4, 28.4, 40.8, 47.4, 36.6]
  - null per-round A-B ms: [-23.21, -18.66, -26.46, -42.01, +24.38, +4.44, -3.88, +14.54, +6.55, +12.29, +24.82, +3.12, -14.81, -7.94, -25.03]
  - candidate pre-CPU %: min 21.8 / median 34.8 / max 55.5; per round [23.2, 23.3, 33.1, 21.8, 25.3, 22.7, 36.7, 37.9, 39.7, 34.9, 34.8, 39.4, 55.5, 31.2, 34.8]
  - candidate per-round A-B ms: [+276.96, +291.11, +293.68, +277.89, +302.49, +290.59, +277.51, +324.68, +393.74, +321.67, +415.23, +413.23, +378.31, +406.01, +383.45]
  - attribution-vs-2c27a907a pre-CPU %: min 24.5 / median 44.7 / max 65.8; per round [65.8, 56.6, 44.7, 49.1, 25.8, 39.0, 33.0, 33.2, 29.8, 40.5, 54.4, 62.0, 53.2, 24.5, 47.5]
  - attribution-vs-2c27a907a per-round A-B ms: [+436.24, +367.97, +376.36, +431.64, +379.63, +459.16, +421.78, +429.03, +429.70, +495.23, +513.79, +387.02, +353.91, +385.22, +452.42]
  - Supplementary attribution vs old base 2c27a907a (C change alone, no #271): median saving +429.025 ms, 15/15 faster. Not used for verdict.
- FAIL pptx-20-600: candidate p50 1.14660 ms/page vs limit 0.8324975 (baseline 0.80825); control 1.11175, cand/ctrl 1.0313; pre-CPU min/med/max 19.9/32.1/69.3%.
- FAIL pptx-20-1200: candidate p50 1.94275 ms/page vs limit 1.6756555 (baseline 1.62685); control 1.95560, cand/ctrl 0.9934; pre-CPU min/med/max 14.1/27.3/56.7%.
- FAIL word-5-600: candidate p50 2.48400 ms/page vs limit 2.2197015 (baseline 2.15505); control 2.45450, cand/ctrl 1.0120; pre-CPU min/med/max 16.1/22.9/64.9%.
- FAIL word-5-1200: candidate p50 9.57280 ms/page vs limit 6.9460625 (baseline 6.74375); control 9.47500, cand/ctrl 1.0103; pre-CPU min/med/max 18.3/40.5/69.7%.
- FAIL deck-1200: candidate p50 12.53690 ms/page vs limit 9.2558375 (baseline 8.98625); control 12.58000, cand/ctrl 0.9966; pre-CPU min/med/max 23.1/39.2/73.7%.
