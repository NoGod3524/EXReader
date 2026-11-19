# unfixed

| case | A status | B status | C status | A vs A2 (null) | A vs B (cache) | B vs C (baseline) | A vs C |
|---|---|---|---|---|---|---|---|
| 01_clip | OK | OK | OK | identical | identical | identical | identical |
| 02_alpha | OK | OK | OK | identical | identical | identical | identical |
| 03_width | OK | OK | OK | identical | identical | identical | identical |
| 04_blend | OK | OK | OK | identical | identical | identical | identical |
| 05_matrix_epsilon | OK | OK | OK | identical | identical | identical | identical |
| 06_clip_change | OK | OK | OK | identical | identical | identical | identical |
| 07_matrix_validation | 1 (Invalid or singular canvas stroke matrix) | OK | 1 (Invalid or singular canvas stroke matrix) | both failed identically | STATUS 1 vs 0 | STATUS 0 vs 1 | both failed identically |
| 08_hairline | OK | OK | OK | identical | DIFFER 7944 px, max channel delta 216, bbox x39-1138 y49-790 | DIFFER 7944 px, max channel delta 216, bbox x39-1138 y49-790 | identical |
