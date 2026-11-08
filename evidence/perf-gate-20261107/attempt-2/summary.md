# E1 local capture

Source: `2f288e15066d616972d312e638b5d9dd04d6e786`; comparison key: `f7ff46c6a81b5cc9a2fa2722a776e8f5c79c565bcaf917fff77f70be70391623`.

advisory: true; accepted: false. Local strict numeric verification does not restore the required check.

Nearest-rank percentiles. Dispersion = 100*(max-min)/p50 across fresh processes; CV uses population SD.
First visible = font open + publication/pager open + first layout/render. First render excludes layout.
R3 native plan: first RGBA frame, 32 sequential pages, 16 fixed-seed random requests; hashes outside timed rendering.
OS cache is primed before each process; no discarded warmup. Peak RSS includes signature hashing.

| Configuration / batch | Metric | p50 | p95 | max | range/p50 % | CV % |
|---|---|---:|---:|---:|---:|---:|
| default-release / 1 | open_ms | 38.712500 | 41.553100 | 41.553100 | 7.954 | 2.962 |
| default-release / 1 | first_visible_ms | 73.842100 | 78.195200 | 78.195200 | 6.638 | 2.413 |
| default-release / 1 | first_render_ms | 7.710100 | 7.778800 | 7.778800 | 4.844 | 1.872 |
| default-release / 1 | turn_p50_ms | 11.922500 | 12.486600 | 12.486600 | 5.434 | 1.976 |
| default-release / 1 | turn_p95_ms | 18.888400 | 19.132900 | 19.132900 | 1.969 | 0.687 |
| default-release / 1 | turn_max_ms | 19.135000 | 19.812500 | 19.812500 | 4.268 | 1.670 |
| default-release / 1 | random_p95_ms | 174.101500 | 180.312900 | 180.312900 | 15.615 | 6.290 |
| default-release / 1 | peak_rss_bytes | 38629376.000000 | 38641664.000000 | 38641664.000000 | 0.074 | 0.028 |
| 1280x800 / 1 | open_ms | 39.005000 | 40.180900 | 40.180900 | 4.283 | 1.500 |
| 1280x800 / 1 | first_visible_ms | 77.414100 | 77.996700 | 77.996700 | 1.564 | 0.496 |
| 1280x800 / 1 | first_render_ms | 10.369900 | 10.639000 | 10.639000 | 4.443 | 1.759 |
| 1280x800 / 1 | turn_p50_ms | 15.253600 | 15.395200 | 15.395200 | 2.605 | 0.859 |
| 1280x800 / 1 | turn_p95_ms | 22.876800 | 23.379500 | 23.379500 | 3.431 | 1.113 |
| 1280x800 / 1 | turn_max_ms | 23.434700 | 24.371300 | 24.371300 | 5.991 | 1.949 |
| 1280x800 / 1 | random_p95_ms | 198.302500 | 207.505200 | 207.505200 | 14.050 | 5.080 |
| 1280x800 / 1 | peak_rss_bytes | 38629376.000000 | 38641664.000000 | 38641664.000000 | 0.042 | 0.014 |
| 2560x1440 / 1 | open_ms | 38.396700 | 39.430000 | 39.430000 | 3.540 | 1.267 |
| 2560x1440 / 1 | first_visible_ms | 117.747500 | 119.526200 | 119.526200 | 1.935 | 0.718 |
| 2560x1440 / 1 | first_render_ms | 33.661800 | 34.611500 | 34.611500 | 5.663 | 1.882 |
| 2560x1440 / 1 | turn_p50_ms | 57.190000 | 58.871600 | 58.871600 | 3.797 | 1.388 |
| 2560x1440 / 1 | turn_p95_ms | 64.124200 | 64.450400 | 64.450400 | 2.046 | 0.717 |
| 2560x1440 / 1 | turn_max_ms | 64.397200 | 64.689600 | 64.689600 | 1.421 | 0.502 |
| 2560x1440 / 1 | random_p95_ms | 577.339500 | 585.311100 | 585.311100 | 2.870 | 1.068 |
| 2560x1440 / 1 | peak_rss_bytes | 41746432.000000 | 41787392.000000 | 41787392.000000 | 0.343 | 0.114 |

## Every retained process

| Configuration / batch / run | open ms | visible ms | first render ms | turn p50 ms | turn p95 ms | peak bytes |
|---|---:|---:|---:|---:|---:|---:|
| default-release/1/1 | 39.643100 | 73.602500 | 7.511200 | 11.900700 | 19.132900 | 38641664.000000 |
| default-release/1/2 | 38.473800 | 73.293700 | 7.710100 | 11.932400 | 18.888400 | 38641664.000000 |
| default-release/1/3 | 38.517100 | 73.842100 | 7.405300 | 11.922500 | 18.760900 | 38612992.000000 |
| default-release/1/4 | 38.712500 | 74.378100 | 7.778800 | 11.838700 | 18.827900 | 38625280.000000 |
| default-release/1/5 | 41.553100 | 78.195200 | 7.723800 | 12.486600 | 18.986600 | 38629376.000000 |
| 1280x800/1/1 | 39.005000 | 77.414100 | 10.369900 | 15.395200 | 22.849300 | 38629376.000000 |
| 1280x800/1/2 | 40.180900 | 77.996700 | 10.178300 | 14.997900 | 23.379500 | 38625280.000000 |
| 1280x800/1/3 | 38.992300 | 76.786200 | 10.639000 | 15.253600 | 22.976000 | 38629376.000000 |
| 1280x800/1/4 | 39.694700 | 77.445200 | 10.268400 | 15.258100 | 22.594500 | 38633472.000000 |
| 1280x800/1/5 | 38.510300 | 77.360700 | 10.610000 | 15.165100 | 22.876800 | 38641664.000000 |
| 2560x1440/1/1 | 38.876900 | 117.248300 | 34.611500 | 58.871600 | 63.138400 | 41787392.000000 |
| 2560x1440/1/2 | 39.430000 | 117.633200 | 33.775400 | 56.700000 | 64.124200 | 41644032.000000 |
| 2560x1440/1/3 | 38.396700 | 117.747500 | 33.661800 | 57.992400 | 64.302000 | 41746432.000000 |
| 2560x1440/1/4 | 38.269100 | 118.842700 | 33.224400 | 57.190000 | 63.977800 | 41738240.000000 |
| 2560x1440/1/5 | 38.070800 | 119.526200 | 32.705400 | 56.920300 | 64.450400 | 41746432.000000 |

## Pairwise differences

Median difference is resolved only if it exceeds both complete-batch observed ranges.

| Pair | Metric | median difference % | exceeds both noise ranges |
|---|---|---:|---|
| default-release vs 1280x800 | open_ms | 0.756 | False |
| default-release vs 1280x800 | first_visible_ms | 4.837 | False |
| default-release vs 1280x800 | first_render_ms | 34.498 | True |
| default-release vs 1280x800 | turn_p50_ms | 27.940 | True |
| default-release vs 1280x800 | turn_p95_ms | 21.116 | True |
| default-release vs 1280x800 | turn_max_ms | 22.470 | True |
| default-release vs 1280x800 | random_p95_ms | 13.901 | False |
| default-release vs 1280x800 | peak_rss_bytes | 0.000 | False |
| default-release vs 2560x1440 | open_ms | 0.816 | False |
| default-release vs 2560x1440 | first_visible_ms | 59.458 | True |
| default-release vs 2560x1440 | first_render_ms | 336.594 | True |
| default-release vs 2560x1440 | turn_p50_ms | 379.681 | True |
| default-release vs 2560x1440 | turn_p95_ms | 239.490 | True |
| default-release vs 2560x1440 | turn_max_ms | 236.541 | True |
| default-release vs 2560x1440 | random_p95_ms | 231.611 | True |
| default-release vs 2560x1440 | peak_rss_bytes | 8.069 | True |
| 1280x800 vs 2560x1440 | open_ms | 1.560 | False |
| 1280x800 vs 2560x1440 | first_visible_ms | 52.101 | True |
| 1280x800 vs 2560x1440 | first_render_ms | 224.611 | True |
| 1280x800 vs 2560x1440 | turn_p50_ms | 274.928 | True |
| 1280x800 vs 2560x1440 | turn_p95_ms | 180.302 | True |
| 1280x800 vs 2560x1440 | turn_max_ms | 174.794 | True |
| 1280x800 vs 2560x1440 | random_p95_ms | 191.141 | True |
| 1280x800 vs 2560x1440 | peak_rss_bytes | 8.069 | True |

Measurement valid: True; stable budget eligible: False.

Budget limits are script-derived in proposed-budgets.json; all earlier noisy batches remain in samples.json and raw/.
