# E1 local capture

Source: `2f288e15066d616972d312e638b5d9dd04d6e786`; comparison key: `57f7fa41a364bcea394d36d93330f31c250fbac12964dc4f4b839e8ec8a87895`.

advisory: true; accepted: false. Local strict numeric verification does not restore the required check.

Nearest-rank percentiles. Dispersion = 100*(max-min)/p50 across fresh processes; CV uses population SD.
First visible = font open + publication/pager open + first layout/render. First render excludes layout.
R3 native plan: first RGBA frame, 32 sequential pages, 16 fixed-seed random requests; hashes outside timed rendering.
OS cache is primed before each process; no discarded warmup. Peak RSS includes signature hashing.

| Configuration / batch | Metric | p50 | p95 | max | range/p50 % | CV % |
|---|---|---:|---:|---:|---:|---:|
| default-release / 1 | open_ms | 34.659500 | 35.249800 | 35.249800 | 2.425 | 0.901 |
| default-release / 1 | first_visible_ms | 77.263700 | 78.073900 | 78.073900 | 2.944 | 0.960 |
| default-release / 1 | first_render_ms | 7.934200 | 7.992300 | 7.992300 | 3.922 | 1.418 |
| default-release / 1 | turn_p50_ms | 12.182900 | 12.404100 | 12.404100 | 2.731 | 0.913 |
| default-release / 1 | turn_p95_ms | 18.298000 | 18.472700 | 18.472700 | 2.664 | 0.969 |
| default-release / 1 | turn_max_ms | 18.503500 | 18.949000 | 18.949000 | 3.871 | 1.376 |
| default-release / 1 | random_p95_ms | 154.353200 | 155.141600 | 155.141600 | 2.918 | 1.030 |
| default-release / 1 | peak_rss_bytes | 38641664.000000 | 38658048.000000 | 38658048.000000 | 0.085 | 0.027 |
| 1280x800 / 1 | open_ms | 34.656300 | 34.934400 | 34.934400 | 1.256 | 0.411 |
| 1280x800 / 1 | first_visible_ms | 80.380700 | 83.506000 | 83.506000 | 4.203 | 1.583 |
| 1280x800 / 1 | first_render_ms | 10.247500 | 12.287300 | 12.287300 | 20.593 | 7.558 |
| 1280x800 / 1 | turn_p50_ms | 15.262100 | 15.296100 | 15.296100 | 0.626 | 0.210 |
| 1280x800 / 1 | turn_p95_ms | 21.844400 | 22.118700 | 22.118700 | 2.526 | 0.837 |
| 1280x800 / 1 | turn_max_ms | 22.224000 | 22.396200 | 22.396200 | 2.832 | 0.998 |
| 1280x800 / 1 | random_p95_ms | 178.272500 | 181.135200 | 181.135200 | 2.638 | 0.979 |
| 1280x800 / 1 | peak_rss_bytes | 38637568.000000 | 38649856.000000 | 38649856.000000 | 0.127 | 0.046 |
| 2560x1440 / 1 | open_ms | 35.271600 | 35.535400 | 35.535400 | 3.856 | 1.716 |
| 2560x1440 / 1 | first_visible_ms | 120.690600 | 125.721500 | 125.721500 | 6.254 | 2.031 |
| 2560x1440 / 1 | first_render_ms | 33.070000 | 33.658700 | 33.658700 | 2.714 | 0.930 |
| 2560x1440 / 1 | turn_p50_ms | 53.952900 | 54.512200 | 54.512200 | 1.365 | 0.517 |
| 2560x1440 / 1 | turn_p95_ms | 60.267700 | 60.404600 | 60.404600 | 0.557 | 0.221 |
| 2560x1440 / 1 | turn_max_ms | 60.768500 | 61.161000 | 61.161000 | 1.242 | 0.417 |
| 2560x1440 / 1 | random_p95_ms | 567.104200 | 568.929800 | 568.929800 | 1.695 | 0.604 |
| 2560x1440 / 1 | peak_rss_bytes | 41721856.000000 | 41771008.000000 | 41771008.000000 | 0.285 | 0.099 |

## Every retained process

| Configuration / batch / run | open ms | visible ms | first render ms | turn p50 ms | turn p95 ms | peak bytes |
|---|---:|---:|---:|---:|---:|---:|
| default-release/1/1 | 35.249800 | 78.073900 | 7.861200 | 12.071400 | 17.985300 | 38658048.000000 |
| default-release/1/2 | 34.659500 | 77.085000 | 7.934200 | 12.182900 | 18.298000 | 38641664.000000 |
| default-release/1/3 | 35.076200 | 77.377700 | 7.992300 | 12.404100 | 18.455200 | 38641664.000000 |
| default-release/1/4 | 34.599100 | 77.263700 | 7.965700 | 12.264900 | 18.231600 | 38641664.000000 |
| default-release/1/5 | 34.409300 | 75.799300 | 7.681100 | 12.166300 | 18.472700 | 38625280.000000 |
| 1280x800/1/1 | 34.698900 | 80.216100 | 10.184200 | 15.200600 | 21.868300 | 38600704.000000 |
| 1280x800/1/2 | 34.934400 | 83.506000 | 12.287300 | 15.296100 | 21.567000 | 38649856.000000 |
| 1280x800/1/3 | 34.499000 | 81.595100 | 10.986900 | 15.267000 | 21.716000 | 38637568.000000 |
| 1280x800/1/4 | 34.625000 | 80.127600 | 10.177000 | 15.262100 | 22.118700 | 38645760.000000 |
| 1280x800/1/5 | 34.656300 | 80.380700 | 10.247500 | 15.236900 | 21.844400 | 38625280.000000 |
| 2560x1440/1/1 | 35.482400 | 121.362100 | 33.070000 | 54.218500 | 60.404600 | 41680896.000000 |
| 2560x1440/1/2 | 35.535400 | 125.721500 | 33.148100 | 53.796900 | 60.148500 | 41734144.000000 |
| 2560x1440/1/3 | 34.175500 | 118.174000 | 32.761100 | 53.775800 | 60.396600 | 41721856.000000 |
| 2560x1440/1/4 | 35.271600 | 120.490500 | 32.889700 | 53.952900 | 60.267700 | 41771008.000000 |
| 2560x1440/1/5 | 34.266000 | 120.690600 | 33.658700 | 54.512200 | 60.068700 | 41652224.000000 |

## Pairwise differences

Median difference is resolved only if it exceeds both complete-batch observed ranges.

| Pair | Metric | median difference % | exceeds both noise ranges |
|---|---|---:|---|
| default-release vs 1280x800 | open_ms | 0.009 | False |
| default-release vs 1280x800 | first_visible_ms | 4.034 | False |
| default-release vs 1280x800 | first_render_ms | 29.156 | True |
| default-release vs 1280x800 | turn_p50_ms | 25.275 | True |
| default-release vs 1280x800 | turn_p95_ms | 19.381 | True |
| default-release vs 1280x800 | turn_max_ms | 20.107 | True |
| default-release vs 1280x800 | random_p95_ms | 15.496 | True |
| default-release vs 1280x800 | peak_rss_bytes | 0.011 | False |
| default-release vs 2560x1440 | open_ms | 1.766 | False |
| default-release vs 2560x1440 | first_visible_ms | 56.206 | True |
| default-release vs 2560x1440 | first_render_ms | 316.803 | True |
| default-release vs 2560x1440 | turn_p50_ms | 342.858 | True |
| default-release vs 2560x1440 | turn_p95_ms | 229.368 | True |
| default-release vs 2560x1440 | turn_max_ms | 228.416 | True |
| default-release vs 2560x1440 | random_p95_ms | 267.407 | True |
| default-release vs 2560x1440 | peak_rss_bytes | 7.971 | True |
| 1280x800 vs 2560x1440 | open_ms | 1.775 | False |
| 1280x800 vs 2560x1440 | first_visible_ms | 50.149 | True |
| 1280x800 vs 2560x1440 | first_render_ms | 222.713 | True |
| 1280x800 vs 2560x1440 | turn_p50_ms | 253.509 | True |
| 1280x800 vs 2560x1440 | turn_p95_ms | 175.895 | True |
| 1280x800 vs 2560x1440 | turn_max_ms | 173.436 | True |
| 1280x800 vs 2560x1440 | random_p95_ms | 218.111 | True |
| 1280x800 vs 2560x1440 | peak_rss_bytes | 7.983 | True |

Measurement valid: True; stable budget eligible: False.

Budget limits are script-derived in proposed-budgets.json; all earlier noisy batches remain in samples.json and raw/.
