| mutation | result | failing cases (first line of each) |
|---|---|---|
| F-flags | SURVIVED |  |
| F-rule | KILLED | `FAIL test_stroke_cache_key_fill_rule: nonzero fill of the same star: expected a cache miss but the cache hit` |
| F-seg_count | SURVIVED |  |
| F-pt_count | SURVIVED |  |
| F-verbs | KILLED | `FAIL test_stroke_cache_key_verbs: line+quad after cached quad+line: expected a cache miss but the cache hit` |
| F-points | KILLED | `FAIL test_stroke_cache_key_matrix_epsilon: path matrix +1e-6: expected a cache miss but the cache hit`<br>`FAIL test_stroke_cache_key_sub_quantum: one control point +1e-7: expected a cache miss but the cache hit` |
| F-stroke_linear[0] | KILLED | `FAIL test_stroke_cache_key_matrix_epsilon: stroke matrix +1e-6: expected a cache miss but the cache hit`<br>`FAIL test_stroke_cache_key_sub_quantum: stroke matrix term +1e-7: expected a cache miss but the cache hit` |
| F-stroke_linear[1] | KILLED | `FAIL test_stroke_cache_key_matrix_epsilon: stroke matrix +1e-6: expected a cache miss but the cache hit`<br>`FAIL test_stroke_cache_key_sub_quantum: stroke matrix term +1e-7: expected a cache miss but the cache hit` |
| F-stroke_linear[2] | KILLED | `FAIL test_stroke_cache_key_matrix_epsilon: stroke matrix +1e-6: expected a cache miss but the cache hit`<br>`FAIL test_stroke_cache_key_sub_quantum: stroke matrix term +1e-7: expected a cache miss but the cache hit` |
| F-stroke_linear[3] | KILLED | `FAIL test_stroke_cache_key_matrix_epsilon: stroke matrix +1e-6: expected a cache miss but the cache hit`<br>`FAIL test_stroke_cache_key_sub_quantum: stroke matrix term +1e-7: expected a cache miss but the cache hit` |
| F-width | KILLED | `FAIL test_stroke_cache_key_width: stroke with another width: expected a cache miss but the cache hit`<br>`FAIL test_stroke_cache_key_hairline: hairline after cached width 1e-13: cached and uncached RGBA differ in 338 px; first (12,13) cached=162,133,128,255 uncached`<br>`FAIL test_stroke_cache_key_sub_quantum: width +1e-7: expected a cache miss but the cache hit` |
| F-miter_limit | KILLED | `FAIL test_stroke_cache_key_miter: miter limit 1.5 (bevels the corner): expected a cache miss but the cache hit` |
| F-cap | KILLED | `FAIL test_stroke_cache_key_width: cap change: expected a cache miss but the cache hit` |
| F-join | KILLED | `FAIL test_stroke_cache_key_width: join change: expected a cache miss but the cache hit` |
| F-dash_count | SURVIVED |  |
| F-dash_phase | KILLED | `FAIL test_stroke_cache_key_width: dash phase change: expected a cache miss but the cache hit`<br>`FAIL test_stroke_cache_key_dash_pattern: dash phase 1e-7 (sub-quantum): expected a cache miss but the cache hit` |
| F-dashes | KILLED | `FAIL test_stroke_cache_key_dash_pattern: dash 3 7: expected a cache miss but the cache hit` |
| C-flags | SURVIVED |  |
| C-rule | SURVIVED |  |
| C-seg_count | SURVIVED |  |
| C-verbs | SURVIVED |  |
| C-points | KILLED | `FAIL test_stroke_cache_key_sub_quantum: one control point +1e-7: expected a cache miss but the cache hit` |
| C-stroke_linear | KILLED | `FAIL test_stroke_cache_key_sub_quantum: stroke matrix term +1e-7: expected a cache miss but the cache hit` |
| C-width | KILLED | `FAIL test_stroke_cache_key_hairline: hairline after cached width 1e-13: cached and uncached RGBA differ in 338 px; first (12,13) cached=162,133,128,255 uncached`<br>`FAIL test_stroke_cache_key_sub_quantum: width +1e-7: expected a cache miss but the cache hit` |
| C-miter_limit | KILLED | `FAIL test_stroke_cache_key_miter: miter limit +1e-7 (sub-quantum): expected a cache miss but the cache hit` |
| C-cap | SURVIVED |  |
| C-join | SURVIVED |  |
| C-dash_count | SURVIVED |  |
| C-dash_phase | KILLED | `FAIL test_stroke_cache_key_dash_pattern: dash phase 1e-7 (sub-quantum): expected a cache miss but the cache hit` |
| C-dashes | KILLED | `FAIL test_stroke_cache_key_dash_pattern: dash 7 3+1e-7 (sub-quantum): expected a cache miss but the cache hit` |
| H-hash-only | SURVIVED |  |
| H-flags | KILLED | `FAIL test_stroke_cache_key_flags: stroke after cached fill: expected a cache miss but the cache hit` |
| H-rule | KILLED | `FAIL test_stroke_cache_key_fill_rule: nonzero fill of the same star: expected a cache miss but the cache hit` |
| H-seg_count | KILLED | `FAIL test_stroke_cache_key_seg_count: closed triangle after cached open triangle: expected a cache miss but the cache hit` |
| H-pt_count | SURVIVED |  |
| H-verbs | KILLED | `FAIL test_stroke_cache_key_verbs: line+quad after cached quad+line: expected a cache miss but the cache hit` |
| H-cap | KILLED | `FAIL test_stroke_cache_key_width: cap change: expected a cache miss but the cache hit` |
| H-join | KILLED | `FAIL test_stroke_cache_key_width: join change: expected a cache miss but the cache hit` |
| H-dash_count | KILLED | `FAIL test_stroke_cache_key_width: dash change: expected a cache miss but the cache hit`<br>`FAIL test_stroke_cache_key_dash_pattern: dash 7 3 3: expected a cache miss but the cache hit` |
| V-inverse | KILLED | `FAIL test_stroke_cache_matrix_translation: stroke matrix e=NaN (stroke): cached draw returned 0 "" (cache HIT) but uncached draw returned 1 "Invalid or singular` |
| V-local-range | KILLED | `FAIL test_stroke_cache_matrix_product: inverse(stroke) x path matrix > 1e7 (stroke): cached draw returned 0 "" (cache HIT) but uncached draw returned 1 "Invalid` |
| V-dash-period | SURVIVED |  |
