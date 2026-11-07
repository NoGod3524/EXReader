# E1 local capture

Source: `c665d1cb1c0b681d4365f732acf775167bfa6d33`; comparison key: `d4ff747fd93ce55fe7800683cf0cd46f5d2eb29d01428d29cfac17f2ad0ab5ad`.

advisory: true; accepted: false. Local strict numeric verification does not restore the required check.

Nearest-rank percentiles. Dispersion = 100*(max-min)/p50 across fresh processes; CV uses population SD.
First visible = font open + publication/pager open + first layout/render. First render excludes layout.
R3 native plan: first RGBA frame, 32 sequential pages, 16 fixed-seed random requests; hashes outside timed rendering.
OS cache is primed before each process; no discarded warmup. Peak RSS includes signature hashing.

| Configuration / batch | Metric | p50 | p95 | max | range/p50 % | CV % |
|---|---|---:|---:|---:|---:|---:|
| default-release / 1 | open_ms | 13.958400 | 14.426200 | 14.426200 | 4.276 | 1.822 |
| default-release / 1 | first_visible_ms | 36.792500 | 38.391500 | 38.391500 | 11.307 | 4.698 |
| default-release / 1 | first_render_ms | 3.564200 | 3.938100 | 3.938100 | 12.491 | 5.327 |
| default-release / 1 | turn_p50_ms | 5.501400 | 5.599400 | 5.599400 | 3.290 | 1.343 |
| default-release / 1 | turn_p95_ms | 8.312900 | 8.360300 | 8.360300 | 2.295 | 0.980 |
| default-release / 1 | turn_max_ms | 8.583200 | 8.824500 | 8.824500 | 5.780 | 2.361 |
| default-release / 1 | random_p95_ms | 67.753300 | 68.017200 | 68.017200 | 0.769 | 0.314 |
| default-release / 1 | peak_rss_bytes | 38645760.000000 | 38645760.000000 | 38645760.000000 | 0.021 | 0.010 |
| default-release / 2 | open_ms | 14.278500 | 15.256600 | 15.256600 | 9.074 | 3.803 |
| default-release / 2 | first_visible_ms | 36.329600 | 36.471000 | 36.471000 | 5.252 | 2.425 |
| default-release / 2 | first_render_ms | 3.565600 | 3.623800 | 3.623800 | 3.380 | 1.380 |
| default-release / 2 | turn_p50_ms | 5.617800 | 5.835700 | 5.835700 | 4.559 | 1.987 |
| default-release / 2 | turn_p95_ms | 8.279700 | 8.586700 | 8.586700 | 4.968 | 2.091 |
| default-release / 2 | turn_max_ms | 8.662800 | 10.342000 | 10.342000 | 22.231 | 9.361 |
| default-release / 2 | random_p95_ms | 69.279900 | 70.764500 | 70.764500 | 2.581 | 1.121 |
| default-release / 2 | peak_rss_bytes | 38670336.000000 | 38682624.000000 | 38682624.000000 | 0.127 | 0.054 |
| default-release / 3 | open_ms | 14.094300 | 14.622800 | 14.622800 | 4.950 | 2.090 |
| default-release / 3 | first_visible_ms | 37.368800 | 45.065300 | 45.065300 | 29.507 | 11.894 |
| default-release / 3 | first_render_ms | 3.989600 | 4.269800 | 4.269800 | 18.924 | 7.940 |
| default-release / 3 | turn_p50_ms | 5.528000 | 5.742500 | 5.742500 | 5.421 | 2.263 |
| default-release / 3 | turn_p95_ms | 8.314300 | 8.340000 | 8.340000 | 2.348 | 1.048 |
| default-release / 3 | turn_max_ms | 8.875100 | 8.907000 | 8.907000 | 4.785 | 2.206 |
| default-release / 3 | random_p95_ms | 68.207700 | 68.336900 | 68.336900 | 1.380 | 0.613 |
| default-release / 3 | peak_rss_bytes | 38645760.000000 | 38645760.000000 | 38645760.000000 | 0.064 | 0.030 |
| 1280x800 / 1 | open_ms | 13.828800 | 13.851600 | 13.851600 | 0.917 | 0.400 |
| 1280x800 / 1 | first_visible_ms | 35.621100 | 35.807600 | 35.807600 | 1.185 | 0.485 |
| 1280x800 / 1 | first_render_ms | 4.660800 | 4.671700 | 4.671700 | 1.993 | 0.894 |
| 1280x800 / 1 | turn_p50_ms | 6.897100 | 6.928500 | 6.928500 | 1.127 | 0.463 |
| 1280x800 / 1 | turn_p95_ms | 9.962600 | 9.991900 | 9.991900 | 1.842 | 0.811 |
| 1280x800 / 1 | turn_max_ms | 10.173900 | 10.723500 | 10.723500 | 8.675 | 3.552 |
| 1280x800 / 1 | random_p95_ms | 79.994700 | 82.008500 | 82.008500 | 3.091 | 1.334 |
| 1280x800 / 1 | peak_rss_bytes | 38666240.000000 | 38670336.000000 | 38670336.000000 | 0.074 | 0.033 |
| 2560x1440 / 1 | open_ms | 14.364700 | 14.858200 | 14.858200 | 7.154 | 2.924 |
| 2560x1440 / 1 | first_visible_ms | 55.373800 | 55.445500 | 55.445500 | 3.868 | 1.815 |
| 2560x1440 / 1 | first_render_ms | 15.003600 | 15.164400 | 15.164400 | 1.960 | 0.801 |
| 2560x1440 / 1 | turn_p50_ms | 25.027700 | 26.015100 | 26.015100 | 6.806 | 2.780 |
| 2560x1440 / 1 | turn_p95_ms | 27.311800 | 27.967200 | 27.967200 | 3.410 | 1.424 |
| 2560x1440 / 1 | turn_max_ms | 28.357000 | 29.807600 | 29.807600 | 9.629 | 3.926 |
| 2560x1440 / 1 | random_p95_ms | 252.752300 | 261.190900 | 261.190900 | 3.398 | 1.571 |
| 2560x1440 / 1 | peak_rss_bytes | 41644032.000000 | 41684992.000000 | 41684992.000000 | 0.098 | 0.046 |

## Every retained process

| Configuration / batch / run | open ms | visible ms | first render ms | turn p50 ms | turn p95 ms | peak bytes |
|---|---:|---:|---:|---:|---:|---:|
| default-release/1/1 | 13.958400 | 36.792500 | 3.492900 | 5.418400 | 8.312900 | 38637568.000000 |
| default-release/1/2 | 14.426200 | 38.391500 | 3.938100 | 5.599400 | 8.360300 | 38645760.000000 |
| default-release/1/3 | 13.829300 | 34.231300 | 3.564200 | 5.501400 | 8.169500 | 38645760.000000 |
| default-release/2/1 | 14.278500 | 34.563000 | 3.565600 | 5.579600 | 8.279700 | 38682624.000000 |
| default-release/2/2 | 15.256600 | 36.329600 | 3.503300 | 5.835700 | 8.586700 | 38670336.000000 |
| default-release/2/3 | 13.960900 | 36.471000 | 3.623800 | 5.617800 | 8.175400 | 38633472.000000 |
| default-release/3/1 | 14.094300 | 45.065300 | 4.269800 | 5.528000 | 8.314300 | 38621184.000000 |
| default-release/3/2 | 14.622800 | 37.368800 | 3.989600 | 5.742500 | 8.340000 | 38645760.000000 |
| default-release/3/3 | 13.925200 | 34.038900 | 3.514800 | 5.442800 | 8.144800 | 38645760.000000 |
| 1280x800/1/1 | 13.724800 | 35.385500 | 4.578800 | 6.928500 | 9.962600 | 38666240.000000 |
| 1280x800/1/2 | 13.851600 | 35.807600 | 4.671700 | 6.897100 | 9.808400 | 38670336.000000 |
| 1280x800/1/3 | 13.828800 | 35.621100 | 4.660800 | 6.850800 | 9.991900 | 38641664.000000 |
| 2560x1440/1/1 | 14.364700 | 55.445500 | 15.003600 | 25.027700 | 27.967200 | 41644032.000000 |
| 2560x1440/1/2 | 13.830500 | 53.303900 | 14.870300 | 24.311800 | 27.311800 | 41644032.000000 |
| 2560x1440/1/3 | 14.858200 | 55.373800 | 15.164400 | 26.015100 | 27.035800 | 41684992.000000 |

## Pairwise differences

Median difference is resolved only if it exceeds both complete-batch observed ranges.

| Pair | Metric | median difference % | exceeds both noise ranges |
|---|---|---:|---|
| default-release vs 1280x800 | open_ms | 1.884 | False |
| default-release vs 1280x800 | first_visible_ms | 4.677 | False |
| default-release vs 1280x800 | first_render_ms | 16.824 | False |
| default-release vs 1280x800 | turn_p50_ms | 24.767 | True |
| default-release vs 1280x800 | turn_p95_ms | 19.825 | True |
| default-release vs 1280x800 | turn_max_ms | 14.634 | True |
| default-release vs 1280x800 | random_p95_ms | 17.281 | True |
| default-release vs 1280x800 | peak_rss_bytes | 0.053 | False |
| default-release vs 2560x1440 | open_ms | 1.919 | False |
| default-release vs 2560x1440 | first_visible_ms | 48.182 | True |
| default-release vs 2560x1440 | first_render_ms | 276.068 | True |
| default-release vs 2560x1440 | turn_p50_ms | 352.744 | True |
| default-release vs 2560x1440 | turn_p95_ms | 228.492 | True |
| default-release vs 2560x1440 | turn_max_ms | 219.512 | True |
| default-release vs 2560x1440 | random_p95_ms | 270.563 | True |
| default-release vs 2560x1440 | peak_rss_bytes | 7.758 | True |
| 1280x800 vs 2560x1440 | open_ms | 3.875 | False |
| 1280x800 vs 2560x1440 | first_visible_ms | 55.452 | True |
| 1280x800 vs 2560x1440 | first_render_ms | 221.910 | True |
| 1280x800 vs 2560x1440 | turn_p50_ms | 262.873 | True |
| 1280x800 vs 2560x1440 | turn_p95_ms | 174.143 | True |
| 1280x800 vs 2560x1440 | turn_max_ms | 178.723 | True |
| 1280x800 vs 2560x1440 | random_p95_ms | 215.961 | True |
| 1280x800 vs 2560x1440 | peak_rss_bytes | 7.701 | True |

Measurement valid: True; stable budget eligible: False.

Budget limits are script-derived in proposed-budgets.json; all earlier noisy batches remain in samples.json and raw/.
