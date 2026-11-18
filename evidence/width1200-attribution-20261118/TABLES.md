## Original-DLL throughput

| Fixture | Width | Pages | Active pixels/round | Warm round median (ms) | Three repeat medians (ms) | Pages/s |
| --- | --- | --- | --- | --- | --- | --- |
| real-mixed-120 | 600 | 120 | 32,859,000 | 652.166 | 612.918 / 658.756 / 652.166 | 184.00 |
| real-mixed-120 | 1200 | 120 | 131,317,200 | 1696.526 | 1681.380 / 1696.526 / 1719.088 | 70.73 |
| image-heavy-100 | 600 | 100 | 28,236,000 | 1228.920 | 1228.920 / 1227.450 / 1285.221 | 81.37 |
| image-heavy-100 | 1200 | 100 | 112,872,000 | 3893.964 | 3893.964 / 3867.865 / 4469.274 | 25.68 |
| vector-heavy-100 | 600 | 100 | 27,255,000 | 511.619 | 527.895 / 503.830 / 511.619 | 195.46 |
| vector-heavy-100 | 1200 | 100 | 108,954,000 | 1463.064 | 1463.064 / 1488.402 / 1391.713 | 68.35 |

## Native per-page time by cohort (sum of cross-repeat page p50s)

| Fixture | Cohort | Pages | @600 ms | @1200 ms | Difference ms | Ratio |
| --- | --- | --- | --- | --- | --- | --- |
| real-mixed-120 | gradient + soft mask | 21 | 324.346 | 1031.120 | +706.774 | 3.179× |
| real-mixed-120 | other | 99 | 301.432 | 659.964 | +358.532 | 2.189× |
| image-heavy-100 | gradient + soft mask | 10 | 208.255 | 585.247 | +376.992 | 2.810× |
| image-heavy-100 | other | 60 | 270.682 | 645.229 | +374.547 | 2.384× |
| image-heavy-100 | synthetic multi-image | 30 | 752.228 | 2681.779 | +1929.550 | 3.565× |
| vector-heavy-100 | gradient + soft mask | 10 | 157.184 | 485.418 | +328.234 | 3.088× |
| vector-heavy-100 | other | 55 | 116.662 | 244.605 | +127.943 | 2.097× |
| vector-heavy-100 | synthetic dense vector | 35 | 234.850 | 707.247 | +472.398 | 3.011× |

## real-mixed-120: full vs class disabled

| Disabled | @600 ms | @1200 ms | Disabled-render ratio | Saving @600 ms | Saving @1200 ms | Saving ratio (compare 4×) | Changed pages 600/1200 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| full | 607.679 | 1656.224 | 2.725× | +0.000 | +0.000 | — | 0 / 0 |
| path | 575.366 | 1624.723 | 2.824× | +32.313 | +35.140 | 1.087× (<=4) | 120 / 120 |
| glyph | 492.065 | 1436.604 | 2.920× | +119.880 | +214.432 | 1.789× (<=4) | 119 / 119 |
| image | 400.925 | 1028.394 | 2.565× | +208.324 | +622.642 | 2.989× (<=4) | 76 / 76 |
| shading | 508.156 | 1249.192 | 2.458× | +103.789 | +402.105 | 3.874× (<=4) | 21 / 21 |
| group | 816.099 | 1800.221 | 2.206× | -204.154 | -143.997 | undefined (signed/noise) | 30 / 0 |

## image-heavy-100: full vs class disabled

| Disabled | @600 ms | @1200 ms | Disabled-render ratio | Saving @600 ms | Saving @1200 ms | Saving ratio (compare 4×) | Changed pages 600/1200 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| full | 1251.828 | 3849.117 | 3.075× | +0.000 | +0.000 | — | 0 / 0 |
| path | 1187.968 | 3755.968 | 3.162× | +60.038 | +59.746 | 0.995× (<=4) | 90 / 90 |
| glyph | 1178.424 | 3942.160 | 3.345× | +54.636 | -93.043 | undefined (signed/noise) | 58 / 58 |
| image | 272.806 | 699.564 | 2.564× | +979.022 | +3149.553 | 3.217× (<=4) | 100 / 100 |
| shading | 1202.867 | 3669.880 | 3.051× | +67.094 | +145.834 | 2.174× (<=4) | 10 / 10 |
| group | 1427.684 | 4004.058 | 2.805× | -164.575 | -188.344 | undefined (signed/noise) | 30 / 0 |

## vector-heavy-100: full vs class disabled

| Disabled | @600 ms | @1200 ms | Disabled-render ratio | Saving @600 ms | Saving @1200 ms | Saving ratio (compare 4×) | Changed pages 600/1200 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| full | 512.690 | 1424.681 | 2.779× | +0.000 | +0.000 | — | 0 / 0 |
| path | 303.531 | 896.570 | 2.954× | +209.159 | +607.295 | 2.904× (<=4) | 100 / 100 |
| glyph | 423.443 | 1231.158 | 2.907× | +99.765 | +170.215 | 1.706× (<=4) | 65 / 65 |
| image | 447.057 | 1197.736 | 2.679× | +65.633 | +226.945 | 3.458× (<=4) | 10 / 10 |
| shading | 461.380 | 1201.908 | 2.605× | +62.341 | +222.799 | 3.574× (<=4) | 10 / 10 |
| group | 526.205 | 1627.643 | 3.093× | -8.520 | +26.969 | undefined (signed/noise) | 0 / 0 |

## Image cache counters per complete sweep

| Fixture | Width | Sweep | Hits | Misses | Evictions | Decode ms | Maximum resident MiB | Maximum entries |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| real-mixed-120 | 600 | cold | 322 | 19 | 0 | 65.894 | 35.238 | 19 |
| real-mixed-120 | 600 | warm | 341 | 0 | 0 | 0.000 | 35.238 | 19 |
| real-mixed-120 | 1200 | cold | 322 | 19 | 0 | 65.981 | 35.238 | 19 |
| real-mixed-120 | 1200 | warm | 341 | 0 | 0 | 0.000 | 35.238 | 19 |
| image-heavy-100 | 600 | cold | 308 | 110 | 63 | 178.871 | 63.918 | 49 |
| image-heavy-100 | 600 | warm | 308 | 110 | 110 | 175.455 | 63.995 | 49 |
| image-heavy-100 | 1200 | cold | 308 | 110 | 63 | 177.170 | 63.918 | 49 |
| image-heavy-100 | 1200 | warm | 308 | 110 | 110 | 184.458 | 63.995 | 49 |
| vector-heavy-100 | 600 | cold | 17 | 3 | 0 | 23.652 | 8.693 | 3 |
| vector-heavy-100 | 600 | warm | 20 | 0 | 0 | 0.000 | 8.693 | 3 |
| vector-heavy-100 | 1200 | cold | 17 | 3 | 0 | 23.605 | 8.693 | 3 |
| vector-heavy-100 | 1200 | warm | 20 | 0 | 0 | 0.000 | 8.693 | 3 |

## real-mixed-120: instrumented warm sweep times

| Scope | @600 ms | @1200 ms | Difference ms | Ratio |
| --- | --- | --- | --- | --- |
| ms | 655.657 | 1802.785 | +1147.129 | 2.750× |
| allocator_ms | 68.402 | 68.249 | -0.152 | 0.998× |
| canvas_create_ms | 2.969 | 17.864 | +14.895 | 6.017× |
| canvas_image_ms | 225.695 | 687.619 | +461.924 | 3.047× |
| mask_ms | 79.468 | 325.905 | +246.437 | 4.101× |
| canvas_paint_ms | 24.440 | 101.696 | +77.256 | 4.161× |
| mask_canvas_paint_ms | 34.887 | 143.149 | +108.262 | 4.103× |
| decode_ms | 0.000 | 0.000 | +0.000 | — |
| other_ms | 323.085 | 669.702 | +346.617 | 2.073× |

## image-heavy-100: instrumented warm sweep times

| Scope | @600 ms | @1200 ms | Difference ms | Ratio |
| --- | --- | --- | --- | --- |
| ms | 1296.657 | 3998.935 | +2702.278 | 3.084× |
| allocator_ms | 83.882 | 86.169 | +2.288 | 1.027× |
| canvas_create_ms | 2.505 | 14.924 | +12.419 | 5.959× |
| canvas_image_ms | 820.639 | 3054.411 | +2233.772 | 3.722× |
| mask_ms | 36.255 | 152.646 | +116.391 | 4.210× |
| canvas_paint_ms | 11.447 | 49.306 | +37.859 | 4.307× |
| mask_canvas_paint_ms | 16.170 | 66.936 | +50.766 | 4.139× |
| decode_ms | 175.455 | 184.458 | +9.003 | 1.051× |
| other_ms | 425.811 | 727.648 | +301.836 | 1.709× |

## vector-heavy-100: instrumented warm sweep times

| Scope | @600 ms | @1200 ms | Difference ms | Ratio |
| --- | --- | --- | --- | --- |
| ms | 539.785 | 1499.006 | +959.221 | 2.777× |
| allocator_ms | 53.413 | 45.795 | -7.618 | 0.857× |
| canvas_create_ms | 2.441 | 13.996 | +11.555 | 5.734× |
| canvas_image_ms | 78.237 | 234.628 | +156.391 | 2.999× |
| mask_ms | 37.466 | 151.749 | +114.283 | 4.050× |
| canvas_paint_ms | 11.838 | 48.109 | +36.271 | 4.064× |
| mask_canvas_paint_ms | 16.555 | 65.651 | +49.096 | 3.966× |
| decode_ms | 0.000 | 0.000 | +0.000 | — |
| other_ms | 409.804 | 1050.524 | +640.720 | 2.563× |

## Link-visible allocation calls per warm page and observed retained pools

| Fixture | Width | malloc/page | calloc/page | realloc/page | free(non-null)/page | Requested MiB/page | Allocator ms/page | Max PDF pool MiB | Max fixed pool MiB |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| real-mixed-120 | 600 | 470.17 | 193.55 | 797.66 | 1445.27 | 4.794 | 0.5700 | 7.467 | 3.582 |
| real-mixed-120 | 1200 | 458.17 | 191.65 | 821.29 | 1431.37 | 13.240 | 0.5687 | 29.869 | 14.319 |
| image-heavy-100 | 600 | 400.56 | 152.36 | 644.07 | 1170.44 | 8.181 | 0.8388 | 7.467 | 3.582 |
| image-heavy-100 | 1200 | 388.06 | 151.56 | 658.79 | 1157.14 | 15.180 | 0.8617 | 29.869 | 14.319 |
| vector-heavy-100 | 600 | 504.23 | 233.61 | 1051.14 | 1683.88 | 5.270 | 0.5341 | 7.467 | 3.582 |
| vector-heavy-100 | 1200 | 502.23 | 232.01 | 1096.90 | 1680.28 | 12.359 | 0.4579 | 29.869 | 14.319 |

## Peak working-set growth by phase (mean of three processes, MiB)

| Fixture | Width | Process-start RSS | Open growth | Cold-sweep peak growth | Further warm peak growth | Final peak |
| --- | --- | --- | --- | --- | --- | --- |
| real-mixed-120 | 600 | 24.694 | 0.792 | 47.491 | 3.350 | 76.327 |
| real-mixed-120 | 1200 | 24.771 | 0.812 | 67.560 | 14.639 | 107.783 |
| image-heavy-100 | 600 | 24.616 | 0.845 | 82.777 | 8.572 | 116.810 |
| image-heavy-100 | 1200 | 24.758 | 0.794 | 97.490 | 24.056 | 147.098 |
| vector-heavy-100 | 600 | 24.542 | 0.749 | 19.398 | 2.850 | 47.539 |
| vector-heavy-100 | 1200 | 24.870 | 0.818 | 42.456 | 10.889 | 79.033 |

## Image-heavy: alternating 64/256 MiB cache intervention

| Width | Paired 64 MiB native ms | 256 MiB native ms | Observed reduction ms | 256 MiB pages/s | Warm hits | Warm misses | Warm evictions | Warm decode ms | Resident MiB | Native mean peak RSS MiB |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 600 | 1248.250 | 1072.946 | 175.304 | 93.20 | 418 | 0 | 0 | 0.000 | 161.532 | 205.212 |
| 1200 | 3866.008 | 3691.297 | 195.369 | 27.09 | 418 | 0 | 0 | 0.000 | 161.532 | 237.026 |

## Unified fresh first page (bench_firstscreen, three processes)

| Fixture | Width | Open median ms | Render median ms |
| --- | --- | --- | --- |
| real-mixed-120 | 600 | 0.766 | 31.981 |
| real-mixed-120 | 1200 | 0.835 | 62.230 |
| image-heavy-100 | 600 | 0.681 | 31.564 |
| image-heavy-100 | 1200 | 0.734 | 62.850 |
| vector-heavy-100 | 600 | 0.580 | 33.384 |
| vector-heavy-100 | 1200 | 0.659 | 67.600 |
