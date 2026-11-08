# E1 local capture

Source: `2f288e15066d616972d312e638b5d9dd04d6e786`; comparison key: `57f7fa41a364bcea394d36d93330f31c250fbac12964dc4f4b839e8ec8a87895`.

advisory: true; accepted: false. Local strict numeric verification does not restore the required check.

Nearest-rank percentiles. Dispersion = 100*(max-min)/p50 across fresh processes; CV uses population SD.
First visible = font open + publication/pager open + first layout/render. First render excludes layout.
R3 native plan: first RGBA frame, 32 sequential pages, 16 fixed-seed random requests; hashes outside timed rendering.
OS cache is primed before each process; no discarded warmup. Peak RSS includes signature hashing.

| Configuration / batch | Metric | p50 | p95 | max | range/p50 % | CV % |
|---|---|---:|---:|---:|---:|---:|
| default-release / 1 | open_ms | 35.039400 | 36.274500 | 36.274500 | 5.249 | 1.720 |
| default-release / 1 | first_visible_ms | 78.181600 | 84.842200 | 84.842200 | 9.471 | 3.497 |
| default-release / 1 | first_render_ms | 8.006900 | 8.264200 | 8.264200 | 8.345 | 2.889 |
| default-release / 1 | turn_p50_ms | 12.308200 | 13.044500 | 13.044500 | 7.987 | 2.931 |
| default-release / 1 | turn_p95_ms | 18.465700 | 18.868900 | 18.868900 | 4.638 | 1.505 |
| default-release / 1 | turn_max_ms | 18.905400 | 19.692000 | 19.692000 | 5.303 | 2.082 |
| default-release / 1 | random_p95_ms | 157.012200 | 161.720000 | 161.720000 | 4.674 | 1.963 |
| default-release / 1 | peak_rss_bytes | 38645760.000000 | 38653952.000000 | 38653952.000000 | 0.085 | 0.028 |
| 1280x800 / 1 | open_ms | 34.000100 | 35.349700 | 35.349700 | 4.098 | 1.615 |
| 1280x800 / 1 | first_visible_ms | 81.799400 | 84.970400 | 84.970400 | 4.167 | 1.700 |
| 1280x800 / 1 | first_render_ms | 10.374200 | 10.548100 | 10.548100 | 3.784 | 1.280 |
| 1280x800 / 1 | turn_p50_ms | 15.319100 | 15.579400 | 15.579400 | 3.413 | 1.154 |
| 1280x800 / 1 | turn_p95_ms | 21.579800 | 21.938500 | 21.938500 | 2.341 | 0.886 |
| 1280x800 / 1 | turn_max_ms | 22.236300 | 23.353300 | 23.353300 | 6.516 | 2.314 |
| 1280x800 / 1 | random_p95_ms | 186.120100 | 188.324000 | 188.324000 | 5.060 | 2.246 |
| 1280x800 / 1 | peak_rss_bytes | 38645760.000000 | 38653952.000000 | 38653952.000000 | 0.074 | 0.026 |
| 2560x1440 / 1 | open_ms | 34.458900 | 37.410900 | 37.410900 | 9.898 | 3.600 |
| 2560x1440 / 1 | first_visible_ms | 124.243000 | 128.871400 | 128.871400 | 5.327 | 1.767 |
| 2560x1440 / 1 | first_render_ms | 33.500200 | 35.449400 | 35.449400 | 7.995 | 2.934 |
| 2560x1440 / 1 | turn_p50_ms | 55.682600 | 56.090800 | 56.090800 | 2.854 | 1.087 |
| 2560x1440 / 1 | turn_p95_ms | 62.332300 | 64.324000 | 64.324000 | 7.112 | 2.396 |
| 2560x1440 / 1 | turn_max_ms | 66.574500 | 74.764100 | 74.764100 | 22.080 | 7.042 |
| 2560x1440 / 1 | random_p95_ms | 557.495100 | 563.988700 | 563.988700 | 1.619 | 0.655 |
| 2560x1440 / 1 | peak_rss_bytes | 41701376.000000 | 41713664.000000 | 41713664.000000 | 0.088 | 0.031 |

## Every retained process

| Configuration / batch / run | open ms | visible ms | first render ms | turn p50 ms | turn p95 ms | peak bytes |
|---|---:|---:|---:|---:|---:|---:|
| default-release/1/1 | 34.435400 | 84.842200 | 7.922500 | 12.061400 | 18.012500 | 38621184.000000 |
| default-release/1/2 | 35.366800 | 77.549400 | 8.264200 | 12.308200 | 18.868900 | 38653952.000000 |
| default-release/1/3 | 36.274500 | 80.251300 | 7.596000 | 13.044500 | 18.607300 | 38641664.000000 |
| default-release/1/4 | 35.039400 | 77.437600 | 8.006900 | 12.156100 | 18.450700 | 38645760.000000 |
| default-release/1/5 | 34.987300 | 78.181600 | 8.167000 | 12.684200 | 18.465700 | 38645760.000000 |
| 1280x800/1/1 | 35.349700 | 81.561700 | 10.548100 | 15.443400 | 21.938500 | 38649856.000000 |
| 1280x800/1/2 | 33.992600 | 81.655000 | 10.155500 | 15.249900 | 21.435500 | 38653952.000000 |
| 1280x800/1/3 | 34.000100 | 83.962500 | 10.319200 | 15.056600 | 21.433400 | 38625280.000000 |
| 1280x800/1/4 | 33.956400 | 84.970400 | 10.458400 | 15.579400 | 21.579800 | 38645760.000000 |
| 1280x800/1/5 | 34.746400 | 81.799400 | 10.374200 | 15.319100 | 21.728500 | 38645760.000000 |
| 2560x1440/1/1 | 34.000000 | 123.998300 | 33.109600 | 56.090800 | 59.891100 | 41709568.000000 |
| 2560x1440/1/2 | 37.410900 | 128.871400 | 34.596600 | 54.501700 | 63.247200 | 41713664.000000 |
| 2560x1440/1/3 | 34.103600 | 124.245900 | 35.449400 | 55.709000 | 64.324000 | 41701376.000000 |
| 2560x1440/1/4 | 34.858800 | 122.253500 | 32.771100 | 55.682600 | 62.332300 | 41693184.000000 |
| 2560x1440/1/5 | 34.458900 | 124.243000 | 33.500200 | 54.799400 | 61.710500 | 41676800.000000 |

## Pairwise differences

Median difference is resolved only if it exceeds both complete-batch observed ranges.

| Pair | Metric | median difference % | exceeds both noise ranges |
|---|---|---:|---|
| default-release vs 1280x800 | open_ms | 2.966 | False |
| default-release vs 1280x800 | first_visible_ms | 4.627 | False |
| default-release vs 1280x800 | first_render_ms | 29.566 | True |
| default-release vs 1280x800 | turn_p50_ms | 24.463 | True |
| default-release vs 1280x800 | turn_p95_ms | 16.864 | True |
| default-release vs 1280x800 | turn_max_ms | 17.619 | True |
| default-release vs 1280x800 | random_p95_ms | 18.539 | True |
| default-release vs 1280x800 | peak_rss_bytes | 0.000 | False |
| default-release vs 2560x1440 | open_ms | 1.657 | False |
| default-release vs 2560x1440 | first_visible_ms | 58.916 | True |
| default-release vs 2560x1440 | first_render_ms | 318.392 | True |
| default-release vs 2560x1440 | turn_p50_ms | 352.402 | True |
| default-release vs 2560x1440 | turn_p95_ms | 237.557 | True |
| default-release vs 2560x1440 | turn_max_ms | 252.145 | True |
| default-release vs 2560x1440 | random_p95_ms | 255.065 | True |
| default-release vs 2560x1440 | peak_rss_bytes | 7.907 | True |
| 1280x800 vs 2560x1440 | open_ms | 1.349 | False |
| 1280x800 vs 2560x1440 | first_visible_ms | 51.887 | True |
| 1280x800 vs 2560x1440 | first_render_ms | 222.918 | True |
| 1280x800 vs 2560x1440 | turn_p50_ms | 263.485 | True |
| 1280x800 vs 2560x1440 | turn_p95_ms | 188.846 | True |
| 1280x800 vs 2560x1440 | turn_max_ms | 199.396 | True |
| 1280x800 vs 2560x1440 | random_p95_ms | 199.535 | True |
| 1280x800 vs 2560x1440 | peak_rss_bytes | 7.907 | True |

Measurement valid: True; stable budget eligible: False.

Budget limits are script-derived in proposed-budgets.json; all earlier noisy batches remain in samples.json and raw/.
