# E1 local capture

Source: `c665d1cb1c0b681d4365f732acf775167bfa6d33`; comparison key: `d4ff747fd93ce55fe7800683cf0cd46f5d2eb29d01428d29cfac17f2ad0ab5ad`.

advisory: true; accepted: false. Local strict numeric verification does not restore the required check.

Nearest-rank percentiles. Dispersion = 100*(max-min)/p50 across fresh processes; CV uses population SD.
First visible = font open + publication/pager open + first layout/render. First render excludes layout.
R3 native plan: first RGBA frame, 32 sequential pages, 16 fixed-seed random requests; hashes outside timed rendering.
OS cache is primed before each process; no discarded warmup. Peak RSS includes signature hashing.

| Configuration / batch | Metric | p50 | p95 | max | range/p50 % | CV % |
|---|---|---:|---:|---:|---:|---:|
| default-release / 1 | open_ms | 14.702000 | 14.753800 | 14.753800 | 0.631 | 0.258 |
| default-release / 1 | first_visible_ms | 38.384400 | 40.138700 | 40.138700 | 10.962 | 4.523 |
| default-release / 1 | first_render_ms | 3.682600 | 4.198600 | 4.198600 | 14.419 | 6.413 |
| default-release / 1 | turn_p50_ms | 5.822800 | 5.943100 | 5.943100 | 3.332 | 1.370 |
| default-release / 1 | turn_p95_ms | 8.736000 | 9.227400 | 9.227400 | 6.063 | 2.714 |
| default-release / 1 | turn_max_ms | 9.347100 | 11.757800 | 11.757800 | 28.742 | 11.996 |
| default-release / 1 | random_p95_ms | 70.879000 | 71.052000 | 71.052000 | 2.586 | 1.174 |
| default-release / 1 | peak_rss_bytes | 38666240.000000 | 38666240.000000 | 38666240.000000 | 0.000 | 0.000 |
| default-release / 2 | open_ms | 14.233400 | 15.448900 | 15.448900 | 8.611 | 3.932 |
| default-release / 2 | first_visible_ms | 36.881100 | 37.360500 | 37.360500 | 7.769 | 3.457 |
| default-release / 2 | first_render_ms | 3.654400 | 3.929600 | 3.929600 | 11.293 | 4.637 |
| default-release / 2 | turn_p50_ms | 5.686400 | 5.950000 | 5.950000 | 6.605 | 2.744 |
| default-release / 2 | turn_p95_ms | 8.534900 | 9.011900 | 9.011900 | 9.387 | 3.833 |
| default-release / 2 | turn_max_ms | 8.744000 | 9.218600 | 9.218600 | 5.761 | 2.596 |
| default-release / 2 | random_p95_ms | 70.411300 | 86.948600 | 86.948600 | 25.747 | 10.872 |
| default-release / 2 | peak_rss_bytes | 38662144.000000 | 38670336.000000 | 38670336.000000 | 0.064 | 0.026 |
| default-release / 3 | open_ms | 14.575000 | 14.911600 | 14.911600 | 4.731 | 1.932 |
| default-release / 3 | first_visible_ms | 39.961400 | 40.220300 | 40.220300 | 13.160 | 6.306 |
| default-release / 3 | first_render_ms | 3.500100 | 3.679400 | 3.679400 | 5.491 | 2.467 |
| default-release / 3 | turn_p50_ms | 5.605400 | 5.761100 | 5.761100 | 4.301 | 1.773 |
| default-release / 3 | turn_p95_ms | 8.450700 | 8.466000 | 8.466000 | 3.501 | 1.627 |
| default-release / 3 | turn_max_ms | 8.918100 | 9.470800 | 9.470800 | 9.871 | 4.039 |
| default-release / 3 | random_p95_ms | 72.392300 | 75.739400 | 75.739400 | 7.039 | 2.899 |
| default-release / 3 | peak_rss_bytes | 38645760.000000 | 38666240.000000 | 38666240.000000 | 0.064 | 0.028 |
| 1280x800 / 1 | open_ms | 14.864900 | 14.906800 | 14.906800 | 6.228 | 2.927 |
| 1280x800 / 1 | first_visible_ms | 37.531400 | 38.358500 | 38.358500 | 7.442 | 3.153 |
| 1280x800 / 1 | first_render_ms | 4.722200 | 4.884500 | 4.884500 | 5.413 | 2.226 |
| 1280x800 / 1 | turn_p50_ms | 7.215000 | 7.374000 | 7.374000 | 7.623 | 3.238 |
| 1280x800 / 1 | turn_p95_ms | 10.174500 | 10.492300 | 10.492300 | 5.852 | 2.388 |
| 1280x800 / 1 | turn_max_ms | 10.298200 | 10.663900 | 10.663900 | 7.235 | 2.955 |
| 1280x800 / 1 | random_p95_ms | 81.731600 | 84.164900 | 84.164900 | 6.246 | 2.553 |
| 1280x800 / 1 | peak_rss_bytes | 38662144.000000 | 38662144.000000 | 38662144.000000 | 0.064 | 0.030 |
| 2560x1440 / 1 | open_ms | 13.760500 | 14.195200 | 14.195200 | 3.212 | 1.486 |
| 2560x1440 / 1 | first_visible_ms | 57.259400 | 57.536900 | 57.536900 | 5.374 | 2.463 |
| 2560x1440 / 1 | first_render_ms | 15.673900 | 16.651700 | 16.651700 | 11.281 | 4.596 |
| 2560x1440 / 1 | turn_p50_ms | 25.968000 | 26.209700 | 26.209700 | 1.764 | 0.720 |
| 2560x1440 / 1 | turn_p95_ms | 29.087000 | 29.373500 | 29.373500 | 4.968 | 2.170 |
| 2560x1440 / 1 | turn_max_ms | 29.616600 | 29.947400 | 29.947400 | 5.164 | 2.240 |
| 2560x1440 / 1 | random_p95_ms | 258.105400 | 258.215900 | 258.215900 | 1.531 | 0.715 |
| 2560x1440 / 1 | peak_rss_bytes | 41684992.000000 | 41705472.000000 | 41705472.000000 | 0.177 | 0.075 |
| 2560x1440 / 2 | open_ms | 14.451000 | 15.036000 | 15.036000 | 7.517 | 3.066 |
| 2560x1440 / 2 | first_visible_ms | 54.448900 | 57.301200 | 57.301200 | 6.679 | 2.834 |
| 2560x1440 / 2 | first_render_ms | 14.984400 | 15.024300 | 15.024300 | 2.306 | 1.036 |
| 2560x1440 / 2 | turn_p50_ms | 26.211100 | 26.923000 | 26.923000 | 8.253 | 3.467 |
| 2560x1440 / 2 | turn_p95_ms | 28.388100 | 30.990400 | 30.990400 | 10.147 | 4.448 |
| 2560x1440 / 2 | turn_max_ms | 29.171700 | 31.968800 | 31.968800 | 9.868 | 4.449 |
| 2560x1440 / 2 | random_p95_ms | 270.112500 | 273.374300 | 273.374300 | 6.350 | 2.790 |
| 2560x1440 / 2 | peak_rss_bytes | 41631744.000000 | 41664512.000000 | 41664512.000000 | 0.207 | 0.085 |
| 2560x1440 / 3 | open_ms | 13.946900 | 14.046700 | 14.046700 | 2.061 | 0.856 |
| 2560x1440 / 3 | first_visible_ms | 55.385700 | 57.563100 | 57.563100 | 7.398 | 3.018 |
| 2560x1440 / 3 | first_render_ms | 15.001000 | 15.058400 | 15.058400 | 1.290 | 0.542 |
| 2560x1440 / 3 | turn_p50_ms | 25.065700 | 25.533200 | 25.533200 | 5.225 | 2.173 |
| 2560x1440 / 3 | turn_p95_ms | 28.429500 | 28.541300 | 28.541300 | 4.154 | 1.894 |
| 2560x1440 / 3 | turn_max_ms | 28.628000 | 28.763900 | 28.763900 | 3.969 | 1.788 |
| 2560x1440 / 3 | random_p95_ms | 255.155300 | 255.486100 | 255.486100 | 0.625 | 0.270 |
| 2560x1440 / 3 | peak_rss_bytes | 41705472.000000 | 41742336.000000 | 41742336.000000 | 0.196 | 0.080 |

## Every retained process

| Configuration / batch / run | open ms | visible ms | first render ms | turn p50 ms | turn p95 ms | peak bytes |
|---|---:|---:|---:|---:|---:|---:|
| default-release/1/1 | 14.661100 | 38.384400 | 3.682600 | 5.822800 | 8.697700 | 38666240.000000 |
| default-release/1/2 | 14.753800 | 40.138700 | 4.198600 | 5.943100 | 9.227400 | 38666240.000000 |
| default-release/1/3 | 14.702000 | 35.930900 | 3.667600 | 5.749100 | 8.736000 | 38666240.000000 |
| default-release/2/1 | 14.223300 | 34.495200 | 3.654400 | 5.686400 | 8.534900 | 38645760.000000 |
| default-release/2/2 | 14.233400 | 36.881100 | 3.516900 | 5.574400 | 8.210700 | 38670336.000000 |
| default-release/2/3 | 15.448900 | 37.360500 | 3.929600 | 5.950000 | 9.011900 | 38662144.000000 |
| default-release/3/1 | 14.222000 | 34.961300 | 3.500100 | 5.520000 | 8.170100 | 38645760.000000 |
| default-release/3/2 | 14.575000 | 39.961400 | 3.679400 | 5.761100 | 8.450700 | 38641664.000000 |
| default-release/3/3 | 14.911600 | 40.220300 | 3.487200 | 5.605400 | 8.466000 | 38666240.000000 |
| 1280x800/1/1 | 14.906800 | 37.531400 | 4.628900 | 7.215000 | 10.174500 | 38662144.000000 |
| 1280x800/1/2 | 14.864900 | 38.358500 | 4.884500 | 7.374000 | 10.492300 | 38637568.000000 |
| 1280x800/1/3 | 13.981000 | 35.565300 | 4.722200 | 6.824000 | 9.896900 | 38662144.000000 |
| 2560x1440/1/1 | 14.195200 | 57.259400 | 14.883600 | 25.968000 | 27.928400 | 41705472.000000 |
| 2560x1440/1/2 | 13.760500 | 57.536900 | 16.651700 | 26.209700 | 29.373500 | 41684992.000000 |
| 2560x1440/1/3 | 13.753200 | 54.459600 | 15.673900 | 25.751700 | 29.087000 | 41631744.000000 |
| 2560x1440/2/1 | 13.949700 | 53.664700 | 14.678700 | 26.211100 | 28.388100 | 41664512.000000 |
| 2560x1440/2/2 | 15.036000 | 57.301200 | 15.024300 | 24.759800 | 28.110000 | 41578496.000000 |
| 2560x1440/2/3 | 14.451000 | 54.448900 | 14.984400 | 26.923000 | 30.990400 | 41631744.000000 |
| 2560x1440/3/1 | 14.046700 | 55.385700 | 15.058400 | 24.223400 | 27.360400 | 41705472.000000 |
| 2560x1440/3/2 | 13.946900 | 57.563100 | 15.001000 | 25.533200 | 28.541300 | 41660416.000000 |
| 2560x1440/3/3 | 13.759200 | 53.465400 | 14.864900 | 25.065700 | 28.429500 | 41742336.000000 |

## Pairwise differences

Median difference is resolved only if it exceeds both complete-batch observed ranges.

| Pair | Metric | median difference % | exceeds both noise ranges |
|---|---|---:|---|
| default-release vs 1280x800 | open_ms | 1.989 | False |
| default-release vs 1280x800 | first_visible_ms | 6.081 | False |
| default-release vs 1280x800 | first_render_ms | 34.916 | True |
| default-release vs 1280x800 | turn_p50_ms | 28.715 | True |
| default-release vs 1280x800 | turn_p95_ms | 20.398 | True |
| default-release vs 1280x800 | turn_max_ms | 15.475 | True |
| default-release vs 1280x800 | random_p95_ms | 12.901 | True |
| default-release vs 1280x800 | peak_rss_bytes | 0.042 | False |
| default-release vs 2560x1440 | open_ms | 4.309 | False |
| default-release vs 2560x1440 | first_visible_ms | 38.598 | True |
| default-release vs 2560x1440 | first_render_ms | 328.588 | True |
| default-release vs 2560x1440 | turn_p50_ms | 347.171 | True |
| default-release vs 2560x1440 | turn_p95_ms | 236.416 | True |
| default-release vs 2560x1440 | turn_max_ms | 221.010 | True |
| default-release vs 2560x1440 | random_p95_ms | 252.462 | True |
| default-release vs 2560x1440 | peak_rss_bytes | 7.917 | True |
| 1280x800 vs 2560x1440 | open_ms | 6.176 | False |
| 1280x800 vs 2560x1440 | first_visible_ms | 47.572 | True |
| 1280x800 vs 2560x1440 | first_render_ms | 217.670 | True |
| 1280x800 vs 2560x1440 | turn_p50_ms | 247.411 | True |
| 1280x800 vs 2560x1440 | turn_p95_ms | 179.419 | True |
| 1280x800 vs 2560x1440 | turn_max_ms | 177.990 | True |
| 1280x800 vs 2560x1440 | random_p95_ms | 212.187 | True |
| 1280x800 vs 2560x1440 | peak_rss_bytes | 7.872 | True |

Measurement valid: True; stable budget eligible: False.

Budget limits are script-derived in proposed-budgets.json; all earlier noisy batches remain in samples.json and raw/.
