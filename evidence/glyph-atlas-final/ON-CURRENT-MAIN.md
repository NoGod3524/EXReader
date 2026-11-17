# Glyph coverage atlas: measured on current main, no net gain

The atlas was implemented and measured against an older main (before the whole-canvas
clip early-out in #234). On that base it looked like a 1200 px win (16.09 -> 11.88 ms),
because masked draws were still paying for a full-page clip mask.

On current main (`baf348d2d`) the same code measures:

| Width | main p50 | atlas p50 | delta |
| ---: | ---: | ---: | ---: |
| 600 | 2.049 | 2.178 | +6.3% |
| 1200 | 3.583 | 3.562 | -0.6% (noise) |
| 2400 | 11.921 | 12.038 | +1.0% |

Mixed text/graphics deck (`tests/fixtures/pdf-ppt/deck.pdf`, 15 pages, 1200 px):

| Variant | p50 |
| --- | ---: |
| main | 246.603 ms |
| atlas | 245.902 ms |

So the atlas is not on the critical path any more: glyph coverage rasterisation was
never the bottle neck, the masked draw was. Correctness holds (60 page/width
combinations, 85,056,000 active RGBA pixels, zero differences, CTest green), but the
change adds an LRU and atlas memory for no measurable time.

Kept on this branch as a record so the experiment is not repeated. Do not merge.

Incidental finding while measuring: `deck.pdf` renders at ~246 ms per page, roughly
70x the slide deck. That document is the real long tail (shading/gradient heavy), and
it is untouched by every vector-fill optimisation landed so far.
