# Consolidated Mutation Failure Outputs (Stroke/Path Coverage Cache Key)

Target: `src/canvas.c` (fixed, commit `0eff5b3dd` + `fix-cache-key.patch`), test binary `exreader-stroke-cache-key-test` (`tests/test_stroke_cache_key.c`).
Driver: `evidence/stroke-cache-regression-20261119/mutate_key.py`. Every mutant was built under `ops/build-gate.ps1` and restored byte-for-byte (SHA-256 verified) afterward; `restore-build.log` confirms the final unmutated rebuild.

## Mutation Categories
- `F-*`: Full removal of a key field from both `build_path_key` hashing and `path_key_matches` exact comparison.
- `C-*`: Compare-only removal from `path_key_matches` (hash left intact; tests `1e-7` sub-quantum / `0` vs `1e-13` hairline aliasing).
- `H-*`: Hash-collision comparator isolation (`e->hash!=k->hash || ` removed in `path_key_matches`, `path_seen_check` intact) + one discrete field check removed; `H-hash-only` is the control (0 failures, proving the exact comparator alone is complete).
- `V-*`: Removal of one hit-path pre-validation guard added by `fix-cache-key.patch`.

## Summary: 28 KILLED / 14 SURVIVED (total 42 mutants, 0 BUILD-FAILED)

## Verbatim Failure Outputs (KILLED Mutants)

### `F-rule` (`mutations/F-rule.test.txt`)
- Summary: `1 failure(s), 218 lockstep draws` (`exit=1`)
```text
FAIL test_stroke_cache_key_fill_rule: nonzero fill of the same star: expected a cache miss but the cache hit
1 failure(s), 218 lockstep draws
exit=1
```

### `F-verbs` (`mutations/F-verbs.test.txt`)
- Summary: `1 failure(s), 219 lockstep draws` (`exit=1`)
```text
FAIL test_stroke_cache_key_verbs: line+quad after cached quad+line: expected a cache miss but the cache hit
1 failure(s), 219 lockstep draws
exit=1
```

### `F-points` (`mutations/F-points.test.txt`)
- Summary: `2 failure(s), 217 lockstep draws` (`exit=1`)
```text
FAIL test_stroke_cache_key_matrix_epsilon: path matrix +1e-6: expected a cache miss but the cache hit
FAIL test_stroke_cache_key_sub_quantum: one control point +1e-7: expected a cache miss but the cache hit
2 failure(s), 217 lockstep draws
exit=1
```

### `F-stroke_linear[0]` (`mutations/F-stroke_linear[0].test.txt`)
- Summary: `2 failure(s), 183 lockstep draws` (`exit=1`)
```text
FAIL test_stroke_cache_key_matrix_epsilon: stroke matrix +1e-6: expected a cache miss but the cache hit
FAIL test_stroke_cache_key_sub_quantum: stroke matrix term +1e-7: expected a cache miss but the cache hit
2 failure(s), 183 lockstep draws
exit=1
```

### `F-stroke_linear[1]` (`mutations/F-stroke_linear[1].test.txt`)
- Summary: `2 failure(s), 191 lockstep draws` (`exit=1`)
```text
FAIL test_stroke_cache_key_matrix_epsilon: stroke matrix +1e-6: expected a cache miss but the cache hit
FAIL test_stroke_cache_key_sub_quantum: stroke matrix term +1e-7: expected a cache miss but the cache hit
2 failure(s), 191 lockstep draws
exit=1
```

### `F-stroke_linear[2]` (`mutations/F-stroke_linear[2].test.txt`)
- Summary: `2 failure(s), 199 lockstep draws` (`exit=1`)
```text
FAIL test_stroke_cache_key_matrix_epsilon: stroke matrix +1e-6: expected a cache miss but the cache hit
FAIL test_stroke_cache_key_sub_quantum: stroke matrix term +1e-7: expected a cache miss but the cache hit
2 failure(s), 199 lockstep draws
exit=1
```

### `F-stroke_linear[3]` (`mutations/F-stroke_linear[3].test.txt`)
- Summary: `2 failure(s), 207 lockstep draws` (`exit=1`)
```text
FAIL test_stroke_cache_key_matrix_epsilon: stroke matrix +1e-6: expected a cache miss but the cache hit
FAIL test_stroke_cache_key_sub_quantum: stroke matrix term +1e-7: expected a cache miss but the cache hit
2 failure(s), 207 lockstep draws
exit=1
```

### `F-width` (`mutations/F-width.test.txt`)
- Summary: `3 failure(s), 195 lockstep draws` (`exit=1`)
```text
FAIL test_stroke_cache_key_width: stroke with another width: expected a cache miss but the cache hit
FAIL test_stroke_cache_key_hairline: hairline after cached width 1e-13: cached and uncached RGBA differ in 338 px; first (12,13) cached=162,133,128,255 uncached=139,123,135,255
FAIL test_stroke_cache_key_sub_quantum: width +1e-7: expected a cache miss but the cache hit
3 failure(s), 195 lockstep draws
exit=1
```

### `F-miter_limit` (`mutations/F-miter_limit.test.txt`)
- Summary: `1 failure(s), 218 lockstep draws` (`exit=1`)
```text
FAIL test_stroke_cache_key_miter: miter limit 1.5 (bevels the corner): expected a cache miss but the cache hit
1 failure(s), 218 lockstep draws
exit=1
```

### `F-cap` (`mutations/F-cap.test.txt`)
- Summary: `1 failure(s), 215 lockstep draws` (`exit=1`)
```text
FAIL test_stroke_cache_key_width: cap change: expected a cache miss but the cache hit
1 failure(s), 215 lockstep draws
exit=1
```

### `F-join` (`mutations/F-join.test.txt`)
- Summary: `1 failure(s), 216 lockstep draws` (`exit=1`)
```text
FAIL test_stroke_cache_key_width: join change: expected a cache miss but the cache hit
1 failure(s), 216 lockstep draws
exit=1
```

### `F-dash_phase` (`mutations/F-dash_phase.test.txt`)
- Summary: `2 failure(s), 219 lockstep draws` (`exit=1`)
```text
FAIL test_stroke_cache_key_width: dash phase change: expected a cache miss but the cache hit
FAIL test_stroke_cache_key_dash_pattern: dash phase 1e-7 (sub-quantum): expected a cache miss but the cache hit
2 failure(s), 219 lockstep draws
exit=1
```

### `F-dashes` (`mutations/F-dashes.test.txt`)
- Summary: `1 failure(s), 216 lockstep draws` (`exit=1`)
```text
FAIL test_stroke_cache_key_dash_pattern: dash 3 7: expected a cache miss but the cache hit
1 failure(s), 216 lockstep draws
exit=1
```

### `C-points` (`mutations/C-points.test.txt`)
- Summary: `1 failure(s), 218 lockstep draws` (`exit=1`)
```text
FAIL test_stroke_cache_key_sub_quantum: one control point +1e-7: expected a cache miss but the cache hit
1 failure(s), 218 lockstep draws
exit=1
```

### `C-stroke_linear` (`mutations/C-stroke_linear.test.txt`)
- Summary: `1 failure(s), 200 lockstep draws` (`exit=1`)
```text
FAIL test_stroke_cache_key_sub_quantum: stroke matrix term +1e-7: expected a cache miss but the cache hit
1 failure(s), 200 lockstep draws
exit=1
```

### `C-width` (`mutations/C-width.test.txt`)
- Summary: `2 failure(s), 212 lockstep draws` (`exit=1`)
```text
FAIL test_stroke_cache_key_hairline: hairline after cached width 1e-13: cached and uncached RGBA differ in 338 px; first (12,13) cached=162,133,128,255 uncached=139,123,135,255
FAIL test_stroke_cache_key_sub_quantum: width +1e-7: expected a cache miss but the cache hit
2 failure(s), 212 lockstep draws
exit=1
```

### `C-miter_limit` (`mutations/C-miter_limit.test.txt`)
- Summary: `1 failure(s), 219 lockstep draws` (`exit=1`)
```text
FAIL test_stroke_cache_key_miter: miter limit +1e-7 (sub-quantum): expected a cache miss but the cache hit
1 failure(s), 219 lockstep draws
exit=1
```

### `C-dash_phase` (`mutations/C-dash_phase.test.txt`)
- Summary: `1 failure(s), 219 lockstep draws` (`exit=1`)
```text
FAIL test_stroke_cache_key_dash_pattern: dash phase 1e-7 (sub-quantum): expected a cache miss but the cache hit
1 failure(s), 219 lockstep draws
exit=1
```

### `C-dashes` (`mutations/C-dashes.test.txt`)
- Summary: `1 failure(s), 218 lockstep draws` (`exit=1`)
```text
FAIL test_stroke_cache_key_dash_pattern: dash 7 3+1e-7 (sub-quantum): expected a cache miss but the cache hit
1 failure(s), 218 lockstep draws
exit=1
```

### `H-flags` (`mutations/H-flags.test.txt`)
- Summary: `1 failure(s), 223 lockstep draws` (`exit=1`)
```text
FAIL test_stroke_cache_key_flags: stroke after cached fill: expected a cache miss but the cache hit
1 failure(s), 223 lockstep draws
exit=1
```

### `H-rule` (`mutations/H-rule.test.txt`)
- Summary: `1 failure(s), 223 lockstep draws` (`exit=1`)
```text
FAIL test_stroke_cache_key_fill_rule: nonzero fill of the same star: expected a cache miss but the cache hit
1 failure(s), 223 lockstep draws
exit=1
```

### `H-seg_count` (`mutations/H-seg_count.test.txt`)
- Summary: `1 failure(s), 224 lockstep draws` (`exit=1`)
```text
FAIL test_stroke_cache_key_seg_count: closed triangle after cached open triangle: expected a cache miss but the cache hit
1 failure(s), 224 lockstep draws
exit=1
```

### `H-verbs` (`mutations/H-verbs.test.txt`)
- Summary: `1 failure(s), 224 lockstep draws` (`exit=1`)
```text
FAIL test_stroke_cache_key_verbs: line+quad after cached quad+line: expected a cache miss but the cache hit
1 failure(s), 224 lockstep draws
exit=1
```

### `H-cap` (`mutations/H-cap.test.txt`)
- Summary: `1 failure(s), 220 lockstep draws` (`exit=1`)
```text
FAIL test_stroke_cache_key_width: cap change: expected a cache miss but the cache hit
1 failure(s), 220 lockstep draws
exit=1
```

### `H-join` (`mutations/H-join.test.txt`)
- Summary: `1 failure(s), 221 lockstep draws` (`exit=1`)
```text
FAIL test_stroke_cache_key_width: join change: expected a cache miss but the cache hit
1 failure(s), 221 lockstep draws
exit=1
```

### `H-dash_count` (`mutations/H-dash_count.test.txt`)
- Summary: `2 failure(s), 220 lockstep draws` (`exit=1`)
```text
FAIL test_stroke_cache_key_width: dash change: expected a cache miss but the cache hit
FAIL test_stroke_cache_key_dash_pattern: dash 7 3 3: expected a cache miss but the cache hit
2 failure(s), 220 lockstep draws
exit=1
```

### `V-inverse` (`mutations/V-inverse.test.txt`)
- Summary: `1 failure(s), 191 lockstep draws` (`exit=1`)
```text
FAIL test_stroke_cache_matrix_translation: stroke matrix e=NaN (stroke): cached draw returned 0 "" (cache HIT) but uncached draw returned 1 "Invalid or singular canvas stroke matrix"
1 failure(s), 191 lockstep draws
exit=1
```

### `V-local-range` (`mutations/V-local-range.test.txt`)
- Summary: `1 failure(s), 215 lockstep draws` (`exit=1`)
```text
FAIL test_stroke_cache_matrix_product: inverse(stroke) x path matrix > 1e7 (stroke): cached draw returned 0 "" (cache HIT) but uncached draw returned 1 "Invalid vector path transform"
1 failure(s), 215 lockstep draws
exit=1
```

## Survived Mutants (Expected by Construction)

| mutation | result | summary | reason |
|---|---|---|---|
| `F-flags` | SURVIVED | `0 failure(s), 219 lockstep draws` (`exit=0`) | Even with explicit `flags` hashing and comparison removed, `EXR_DRAW_FILL` hashes `rule` only, `EXR_DRAW_STROKE` hashes stroke fields only, and `EXR_DRAW_FILL|EXR_DRAW_STROKE` hashes both, so their 64-bit FNV-1a hashes remain distinct; killed under hash-collision isolation (`H-flags`). |
| `F-seg_count` | SURVIVED | `0 failure(s), 224 lockstep draws` (`exit=0`) | Even with `h=fnv_u64(h,count)` and `e->seg_count!=k->seg_count` removed, the segment loop hashes each verb (`h=fnv_u64(h,verb)`), so differing segment counts still hash differently; killed under hash-collision isolation (`H-seg_count`). |
| `F-pt_count` | SURVIVED | `0 failure(s), 219 lockstep draws` (`exit=0`) | Strictly redundant invariant: each verb (`CLOSE=0`, `MOVE/LINE=1`, `QUAD=2`, `CUBIC=3`) fixes point count, so `e->seg_count==k->seg_count && memcmp(e->verbs,k->verbs,e->seg_count)==0` mathematically forces `e->pt_count==k->pt_count`. |
| `F-dash_count` | SURVIVED | `0 failure(s), 219 lockstep draws` (`exit=0`) | Even with `h=fnv_u64(h,style->dash_count)` and `e->dash_count!=k->dash_count` removed, the dash loop hashes `dash_count` values into the 64-bit FNV-1a hash; killed under hash-collision isolation (`H-dash_count`). |
| `C-flags` | SURVIVED | `0 failure(s), 219 lockstep draws` (`exit=0`) | Discrete field hashed exact (unquantized) into 64-bit FNV-1a; rejected by `e->hash!=k->hash` absent a 64-bit collision; killed by `H-flags`. |
| `C-rule` | SURVIVED | `0 failure(s), 219 lockstep draws` (`exit=0`) | Discrete field hashed exact into 64-bit FNV-1a; killed by `F-rule` and `H-rule`. |
| `C-seg_count` | SURVIVED | `0 failure(s), 219 lockstep draws` (`exit=0`) | Discrete field hashed exact into 64-bit FNV-1a; killed by `H-seg_count`. |
| `C-verbs` | SURVIVED | `0 failure(s), 219 lockstep draws` (`exit=0`) | Discrete field hashed exact into 64-bit FNV-1a; killed by `F-verbs` and `H-verbs`. |
| `C-cap` | SURVIVED | `0 failure(s), 219 lockstep draws` (`exit=0`) | Discrete field hashed exact into 64-bit FNV-1a; killed by `F-cap` and `H-cap`. |
| `C-join` | SURVIVED | `0 failure(s), 219 lockstep draws` (`exit=0`) | Discrete field hashed exact into 64-bit FNV-1a; killed by `F-join` and `H-join`. |
| `C-dash_count` | SURVIVED | `0 failure(s), 219 lockstep draws` (`exit=0`) | Discrete field hashed exact into 64-bit FNV-1a; killed by `H-dash_count`. |
| `H-hash-only` | SURVIVED | `0 failure(s), 224 lockstep draws` (`exit=0`) | Control mutant: removing only `e->hash!=k->hash || ` passes 18/18 tests (0 failures), confirming `path_key_matches` alone is complete without relying on hash uniqueness. |
| `H-pt_count` | SURVIVED | `0 failure(s), 224 lockstep draws` (`exit=0`) | Strictly redundant invariant implied by `seg_count` + `verbs` (see `F-pt_count`). |
| `V-dash-period` | SURVIVED | `0 failure(s), 224 lockstep draws` (`exit=0`) | Defense-in-depth early reject in `build_path_key`: once `path_key_matches` switched `dashes[i]` from `1e-12` tolerance to exact equality (`!=`), an all-zero dash pattern `{0}` can never match any cached valid pattern (which has at least one `dashes[i] > 0`), so it misses and falls through to `exr_vector_dash`, which rejects it identically. (Before `fix-cache-key.patch`, `{0}` aliased `{1e-13}` under `1e-12` tolerance and failed `test_stroke_cache_dash_validation`.) |
