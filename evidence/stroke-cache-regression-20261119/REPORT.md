# B 线描边/路径覆盖缓存回归报告（合并前置条件）

- **日期 / 机器**：2026-11-19，LAP25002，MinGW GCC 16.2.0 Release（`build/perf`）
- **工作树 / 分支**：`C:\Users\Oscar\Documents\Codex\EXReader-dvpath`，分支 `perf/dense-vector-path-residual`
- **对照基线**：
  - 分支分叉点：`2c27a907a`
  - Arm C（当前 `main`）：`9c2443edf`（`libexreader.dll` SHA-256 `8BE84D818FA15D6A96D2C1C2F07E28276CE629E873D5D4D23717C08A6AEB77AA`）
  - 未修复 B（`1beab649c` / `386462755` 的 `src/canvas.c`）：`unfixed/bin-B/libexreader.dll` SHA-256 `5048067849241F7981C9C595D1B87AF7AD8BC572AD0591BED72FEE01DC17E557`
  - 修复后 B（`0eff5b3dd`，含 `fix-cache-key.patch`）：`fixed/bin-B/libexreader.dll` SHA-256 `2C938804C6E922F559D909D26EA59B7EA7A0CB6CE4ABFF5D1CBF569FEF9A5C27`
- **互斥与测量纪律**：所有编译及全量 `ctest` 均通过 `ops\build-gate.ps1`（先 `opus-Breg`，接续 `agy-Breg`）排队拿锁并释放；本任务为逐像素与功能验证，无计时采样，不占 `bench-lock`。

---

## 一、B 线的缓存键字段清单 + 命中后跳过代码段

代码位置：`src/canvas.c:287-472`（数据结构、`build_path_key`、`path_key_matches`、`path_cache_insert`）、`src/canvas.c:581-623`（查表命中返回）、`src/canvas.c:648-706`（二次命中入表）。

### 1.1 缓存键字段清单（`path_cache_key` / `exr_path_cache_entry`）

| # | 字段 | 生效条件 | 哈希方式（`build_path_key`） | 精确比对（`path_key_matches`） |
|---|---|---|---|---|
| 1 | `flags`（`style->flags`） | 始终 | `fnv_u64` 精确 | `e->flags != k->flags` |
| 2 | `rule`（`style->rule`） | `EXR_DRAW_FILL` | `fnv_u64` 精确 | `(e->flags & EXR_DRAW_FILL) && e->rule != k->rule` |
| 3 | `seg_count`（`count`） | 始终（`2..64`，纯 fill 需 `>5`） | `fnv_u64` 精确 | `e->seg_count != k->seg_count` |
| 4 | `pt_count` | 始终（`<=192`） | 由 `verbs` 隐含 | `e->pt_count != k->pt_count`（由 `seg_count`+`verbs` 唯一决定） |
| 5 | `verbs[0..seg_count-1]` | 始终 | 逐段 `fnv_u64` 精确 | `memcmp(e->verbs, k->verbs, e->seg_count)` |
| 6 | `pts[0..pt_count-1]` | 始终（`transform` 变换后减 `(ox, oy)`） | 逐坐标 `hash_q6`（`1e-6` 量化） | `fabs(e->pts[i].x - k->pts[i].x) > 1e-9 \|\| ...` |
| 7–10 | `stroke_linear[0..3]`（`sm[0..3]`） | `EXR_DRAW_STROKE` | 逐项 `hash_q6` | 修复后：**精确 `!=`**（修复前：`> 1e-12`） |
| 11 | `line.width` | `EXR_DRAW_STROKE` | `hash_q6` | 修复后：**精确 `!=`**（修复前：`> 1e-12`） |
| 12 | `line.miter_limit` | `EXR_DRAW_STROKE` | `hash_q6` | 修复后：**精确 `!=`**（修复前：`> 1e-12`） |
| 13 | `line.cap` | `EXR_DRAW_STROKE` | `fnv_u64` 精确 | `e->line.cap != k->line.cap` |
| 14 | `line.join` | `EXR_DRAW_STROKE` | `fnv_u64` 精确 | `e->line.join != k->line.join` |
| 15 | `dash_count`（`<=16`） | `EXR_DRAW_STROKE` | `fnv_u64` 精确 | `e->dash_count != k->dash_count` |
| 16 | `dash_phase` | `EXR_DRAW_STROKE` | `hash_q6` | 修复后：**精确 `!=`**（修复前：`> 1e-12`） |
| 17 | `dashes[0..dash_count-1]` | `EXR_DRAW_STROKE` | 逐项 `hash_q6` | 修复后：**精确 `!=`**（修复前：`> 1e-12`） |

**未进入缓存键、而是在回放阶段消费或通过门控绕过的状态：**
- **Clip（`c->clip`）**：缓存存的是未裁剪覆盖掩码（coverage mask），回放时经 `blit_coverage_mask` / `exr_composite_compound[_cmyk]_at` 与当前 `c->clip` 相乘。
- **Alpha / 颜色（`style->fill`, `style->stroke`, CMYK）**：覆盖掩码与颜色无关，回放时以当前颜色与 alpha 合成。
- **Blend mode（`c->blend`）**：单描边/单填充在非 `EXR_BLEND_NORMAL`（或 CMYK / soft mask / composite state）下由 `standalone_cache_ok` 直接绕过缓存；复合路径（`EXR_DRAW_FILL|EXR_DRAW_STROKE`）在回放时将缓存的 fill/stroke 掩码交由 `exr_composite_compound[_cmyk]_at(..., c->blend, ...)` 混合。
- **整像素平移 `(ox, oy)`**：从控制点中扣除 `ox = floor(x0 + 1e-9), oy = floor(y0 + 1e-9)`，命中后按 `dx0 = key.ox + entry->rel_x0, dy0 = key.oy + entry->rel_y0` 平移回放（且检查完全落在画布内）。

### 1.2 命中后跳过哪段代码 & 审计风险证伪结果

`path_impl`（`src/canvas.c:588-617`）在缓存命中后直接回放覆盖掩码并 `return finish(c, ..., e)`，**整段跳过 `src/canvas.c:624-711`**：
1. `exr_vector_flatten(segments, count, transform, .125, &flat, ...)`（填充展平与坐标校验）
2. `inverse(stroke, inv)`（`src/canvas.c:629`：校验 6 项 `stroke[0..5]` 有限且 `<=1e7`、行列式非零、逆矩阵 `inv[0..5]` 有限且 `<=1e7`，失败返回 `"Invalid or singular canvas stroke matrix"`）
3. `multiply(inv, transform, matrix)` 与 `exr_vector_flatten(..., matrix, .125/fmax(1,scale), &local, ...)`（`src/curves.c:64,25-29`：校验 `matrix[0..5]` 有限且 `<=1e7` 返回 `"Invalid vector path transform"`，以及每个局部坐标 `(qx, qy)` 有限且 `<=1e7`）
4. `exr_vector_dash(&local, ...)`（`src/dash.c:78-83`：校验非负虚线长度且总周期 `period > 0`，全零返回 `"Vector dash pattern has no positive lengths"`）
5. `exr_vector_stroke(...)`（`src/stroke.c:82-102`：校验线型与变换，且对 `width == 0` 细线校验设备空间点 `(dx, dy)` 有限且 `<=1e7`）
6. 边表构建与扫描线光栅化。

**实测证实：六路审计提出的风险在未修复 B（`1beab649c`）上完全为真，且暴露出两类实锤缺陷：**
1. **缺陷 1（命中跳过校验）**：未修复的 `build_path_key` 只检查了 `sm[0..3]` 有限且 `<=1e7`，**漏检了 `sm[4..5]` 平移项、`inverse(sm, inv)` 可逆性与范围、`local = inv * transform` 范围、描边局部点 `(qx, qy)` 与细线设备点 `(dx, dy)` 范围，以及全零虚线周期**。结果：一旦合法描边写入缓存，后续携带 `sm[4]=NaN` / `sm[5]=-Inf` / `sm[4]=2e7` / `inv[4]=-1.2e7` / `inverse(stroke)*path > 1e7` / 病态矩阵 `1/(a-5e-13)>1e7` / 全零虚线 `{0}` 的非法绘制全部错误命中缓存并返回 `EXR_OK`（`0`），而关缓存 A 与基线 C 均返回错误码 `1`。
2. **缺陷 2（`1e-12` 容差导致细线别名错误渲染）**：未修复的 `path_key_matches` 用 `fabs(e->line.width - k->line.width) > 1e-12` 比较线宽，导致 PDF `0 w`（1 设备像素细线）与 `1e-13 w`（近不可见描边）互相命中：`08_hairline.pdf` 上 B 与 A/C 相差 **7,944 像素（最大通道差 216）**，`test_stroke_cache_key_hairline` 相差 **338 像素**。

**`fix-cache-key.patch`（已合入 `0eff5b3dd` 的 `src/canvas.c`）修复内容：**
- 在 `build_path_key` 查表前补齐与 `path_impl` 一致的描边预校验：`inverse(sm, inv)`、`local = inv * transform` 6 项范围校验、全部描边局部点 `(qx, qy)` 与细线设备点 `(dx, dy)` 范围校验、非零虚线周期 `period` 校验；任一不满足则 `return 0`（回退常规路径正常报错）。
- 在 `path_key_matches` 中将 `line.width`、`line.miter_limit`、`dash_phase`、`stroke_linear[0..3]`、`dashes[i]` 从 `1e-12` 容差改为**精确相等 `!=`**。

---

## 二、对抗 PDF 夹具三路逐像素对照（A / A2 / B / C）

夹具生成脚本：`evidence/stroke-cache-regression-20261119/gen_fixtures.py`（单页 `1200 x 900 pt`，scale 1 -> `1200 x 900 px`），覆盖任务书要求的全部 6 种情形 + 2 个针对两类真实缺陷的专项 PDF 夹具（`07_matrix_validation.pdf`、`08_hairline.pdf`）。
渲染工具：`render_abc.c`（A = B DLL 关缓存，通过永不取消的 `control.cancelled` 回调使 `build_path_key` 直接返回 0；A2 = 同 DLL 再次渲染的空对照；B = B DLL 开缓存；C = `main 9c2443edf` DLL）。

### 2.1 修复前（`unfixed/compare-unfixed.md`，B = `1beab649c`，SHA-256 `50480678...`）

| case | A status | B status | C status | A vs A2 (null) | A vs B (cache) | B vs C (baseline) | A vs C |
|---|---|---|---|---|---|---|---|
| 01_clip | OK | OK | OK | identical | identical | identical | identical |
| 02_alpha | OK | OK | OK | identical | identical | identical | identical |
| 03_width | OK | OK | OK | identical | identical | identical | identical |
| 04_blend | OK | OK | OK | identical | identical | identical | identical |
| 05_matrix_epsilon | OK | OK | OK | identical | identical | identical | identical |
| 06_clip_change | OK | OK | OK | identical | identical | identical | identical |
| **07_matrix_validation** | 1 (`Invalid or singular canvas stroke matrix`) | **OK** | 1 (`Invalid or singular canvas stroke matrix`) | both failed identically | **STATUS 1 vs 0** | **STATUS 0 vs 1** | both failed identically |
| **08_hairline** | OK | OK | OK | identical | **DIFFER 7944 px, max channel delta 216, bbox x39-1138 y49-790** | **DIFFER 7944 px, max channel delta 216, bbox x39-1138 y49-790** | identical |

修复前单元测试（`unfixed/unit-test.txt`）：**6 failure(s)**（`exit=1`）：
```text
FAIL test_stroke_cache_matrix_translation: stroke matrix e=NaN (stroke): cached draw returned 0 "" (cache HIT) but uncached draw returned 1 "Invalid or singular canvas stroke matrix"
FAIL test_stroke_cache_matrix_conditioning: stroke matrix inverse 1/(a-5e-13) > 1e7 (stroke): cached draw returned 0 "" (cache HIT) but uncached draw returned 1 "Invalid or singular canvas stroke matrix"
FAIL test_stroke_cache_matrix_product: inverse(stroke) x path matrix > 1e7 (stroke): cached draw returned 0 "" (cache HIT) but uncached draw returned 1 "Invalid vector path transform"
FAIL test_stroke_cache_dash_validation: all-zero dash pattern (stroke): cached draw returned 0 "" (cache HIT) but uncached draw returned 1 "Vector dash pattern has no positive lengths"
FAIL test_stroke_cache_key_hairline: hairline after cached width 1e-13: cached and uncached RGBA differ in 338 px; first (12,13) cached=162,133,128,255 uncached=139,123,135,255
FAIL test_stroke_cache_key_sub_quantum: original still hits: expected a cache hit (tick 14->15)
```

### 2.2 修复后（`fixed/compare-fixed.md`，B = `0eff5b3dd`，SHA-256 `2C938804...`）

| case | Fixture SHA-256 (前12位) | A / A2 / B / C FNV64 或状态 | A vs A2 (null) | A vs B (cache) | B vs C (baseline) | A vs C |
|---|---|---|---|---|---|---|
| 01_clip | `4668E3E4F501` | OK / `51487b5017577f42` (4/4 一致) | identical | identical | identical | identical |
| 02_alpha | `0333C6D08749` | OK / `cfab40893f8a29a6` (4/4 一致) | identical | identical | identical | identical |
| 03_width | `C1942AE6E1FF` | OK / `00e30f35e0bc325e` (4/4 一致) | identical | identical | identical | identical |
| 04_blend | `14C0BB72246C` | OK / `3bf616b9f379c408` (4/4 一致) | identical | identical | identical | identical |
| 05_matrix_epsilon | `A183699D645C` | OK / `c4819c5143eeb80e` (4/4 一致) | identical | identical | identical | identical |
| 06_clip_change | `68A585B922B3` | OK / `e2d5e83624ecfaf9` (4/4 一致) | identical | identical | identical | identical |
| 07_matrix_validation | `81FD2FF492E7` | status=1 `Invalid or singular canvas stroke matrix` (4/4 一致) | both failed identically | both failed identically | both failed identically | both failed identically |
| 08_hairline | `EEFAA132A578` | OK / `ff1ae6650b764bc7` (4/4 一致) | identical | identical | identical | identical |

修复后结果：**全部 8/8 个对抗夹具满足 A = A2 = B = C（逐像素与错误状态完全一致）**。

---

## 三、删掉每个缓存键字段时的变异失败输出汇总

测试套件：`tests/test_stroke_cache_key.c`（CTest 目标 `native-stroke-cache-key`，共 18 组用例、224 次 lockstep 对比绘制，每次绘制同时断言状态、逐像素 RGBA 及真实的缓存命中/未命中）。
变异驱动：`evidence/stroke-cache-regression-20261119/mutate_key.py`，共运行 **42 个变异体**（`0 BUILD-FAILED`，**28 KILLED / 14 预期 SURVIVED**），完整原始输出汇总见 [`mutations/failures-consolidated.md`](mutations/failures-consolidated.md)，恢复编译日志见 [`mutations/restore-build.log`](mutations/restore-build.log)（源码恢复经 SHA-256 校验与 `git diff 0eff5b3dd -- src/` 零差异双重确认）。

四种变异类型：
- **`F-*`（全删除）**：同时从 `build_path_key` 哈希与 `path_key_matches` 精确比对中删除该字段。
- **`C-*`（仅删精确比对）**：保留 `build_path_key` 哈希（浮点字段以 `1e-6` 量化），仅删 `path_key_matches` 精确比对，检验 `1e-7` 次量化差值与 `0` vs `1e-13` 细线别名是否仍能抓到。
- **`H-*`（哈希碰撞隔离）**：在 `path_key_matches` 中移除 `e->hash!=k->hash || `（保留 `path_seen_check`），单独移除某一离散字段的精确比对；对照变异体 `H-hash-only` 仅删 `e->hash!=k->hash || `，**18/18 全过（0 failures）**，证明即使 100% 哈希碰撞，精确比对本身也完备。
- **`V-*`（删命中前校验）**：移除 `fix-cache-key.patch` 新增的命中前校验守卫。

### 3.1 按缓存键字段与守卫汇总的实测失败输出（全部 16 个非冗余键字段 + 2 个独立前校验守卫 = 18/18 均被 KILLED）

| 缓存键字段 / 守卫 | 触发变异体 | 实测失败输出（原文逐字摘录） |
|---|---|---|
| `flags` | `H-flags` | `FAIL test_stroke_cache_key_flags: stroke after cached fill: expected a cache miss but the cache hit` (`exit=1`) |
| `rule` | `F-rule`, `H-rule` | `FAIL test_stroke_cache_key_fill_rule: nonzero fill of the same star: expected a cache miss but the cache hit` (`exit=1`) |
| `seg_count` | `H-seg_count` | `FAIL test_stroke_cache_key_seg_count: closed triangle after cached open triangle: expected a cache miss but the cache hit` (`exit=1`) |
| `verbs` | `F-verbs`, `H-verbs` | `FAIL test_stroke_cache_key_verbs: line+quad after cached quad+line: expected a cache miss but the cache hit` (`exit=1`) |
| `pts` | `F-points` | `FAIL test_stroke_cache_key_matrix_epsilon: path matrix +1e-6: expected a cache miss but the cache hit`<br>`FAIL test_stroke_cache_key_sub_quantum: one control point +1e-7: expected a cache miss but the cache hit` (`exit=1`) |
| `pts`（仅删比对） | `C-points` | `FAIL test_stroke_cache_key_sub_quantum: one control point +1e-7: expected a cache miss but the cache hit` (`exit=1`) |
| `stroke_linear[0]` | `F-stroke_linear[0]` | `FAIL test_stroke_cache_key_matrix_epsilon: stroke matrix +1e-6: expected a cache miss but the cache hit`<br>`FAIL test_stroke_cache_key_sub_quantum: stroke matrix term +1e-7: expected a cache miss but the cache hit` (`exit=1`) |
| `stroke_linear[1]` | `F-stroke_linear[1]` | `FAIL test_stroke_cache_key_matrix_epsilon: stroke matrix +1e-6: expected a cache miss but the cache hit`<br>`FAIL test_stroke_cache_key_sub_quantum: stroke matrix term +1e-7: expected a cache miss but the cache hit` (`exit=1`) |
| `stroke_linear[2]` | `F-stroke_linear[2]` | `FAIL test_stroke_cache_key_matrix_epsilon: stroke matrix +1e-6: expected a cache miss but the cache hit`<br>`FAIL test_stroke_cache_key_sub_quantum: stroke matrix term +1e-7: expected a cache miss but the cache hit` (`exit=1`) |
| `stroke_linear[3]` | `F-stroke_linear[3]` | `FAIL test_stroke_cache_key_matrix_epsilon: stroke matrix +1e-6: expected a cache miss but the cache hit`<br>`FAIL test_stroke_cache_key_sub_quantum: stroke matrix term +1e-7: expected a cache miss but the cache hit` (`exit=1`) |
| `stroke_linear[0..3]`（仅删比对） | `C-stroke_linear` | `FAIL test_stroke_cache_key_sub_quantum: stroke matrix term +1e-7: expected a cache miss but the cache hit` (`exit=1`) |
| `line.width` | `F-width` | `FAIL test_stroke_cache_key_width: stroke with another width: expected a cache miss but the cache hit`<br>`FAIL test_stroke_cache_key_hairline: hairline after cached width 1e-13: cached and uncached RGBA differ in 338 px; first (12,13) cached=162,133,128,255 uncached=139,123,135,255`<br>`FAIL test_stroke_cache_key_sub_quantum: width +1e-7: expected a cache miss but the cache hit` (`exit=1`) |
| `line.width`（仅删比对） | `C-width` | `FAIL test_stroke_cache_key_hairline: hairline after cached width 1e-13: cached and uncached RGBA differ in 338 px; first (12,13) cached=162,133,128,255 uncached=139,123,135,255`<br>`FAIL test_stroke_cache_key_sub_quantum: width +1e-7: expected a cache miss but the cache hit` (`exit=1`) |
| `line.miter_limit` | `F-miter_limit` | `FAIL test_stroke_cache_key_miter: miter limit 1.5 (bevels the corner): expected a cache miss but the cache hit` (`exit=1`) |
| `line.miter_limit`（仅删比对） | `C-miter_limit` | `FAIL test_stroke_cache_key_miter: miter limit +1e-7 (sub-quantum): expected a cache miss but the cache hit` (`exit=1`) |
| `line.cap` | `F-cap`, `H-cap` | `FAIL test_stroke_cache_key_width: cap change: expected a cache miss but the cache hit` (`exit=1`) |
| `line.join` | `F-join`, `H-join` | `FAIL test_stroke_cache_key_width: join change: expected a cache miss but the cache hit` (`exit=1`) |
| `dash_count` | `H-dash_count` | `FAIL test_stroke_cache_key_width: dash change: expected a cache miss but the cache hit`<br>`FAIL test_stroke_cache_key_dash_pattern: dash 7 3 3: expected a cache miss but the cache hit` (`exit=1`) |
| `dash_phase` | `F-dash_phase` | `FAIL test_stroke_cache_key_width: dash phase change: expected a cache miss but the cache hit`<br>`FAIL test_stroke_cache_key_dash_pattern: dash phase 1e-7 (sub-quantum): expected a cache miss but the cache hit` (`exit=1`) |
| `dash_phase`（仅删比对） | `C-dash_phase` | `FAIL test_stroke_cache_key_dash_pattern: dash phase 1e-7 (sub-quantum): expected a cache miss but the cache hit` (`exit=1`) |
| `dashes` | `F-dashes` | `FAIL test_stroke_cache_key_dash_pattern: dash 3 7: expected a cache miss but the cache hit` (`exit=1`) |
| `dashes`（仅删比对） | `C-dashes` | `FAIL test_stroke_cache_key_dash_pattern: dash 7 3+1e-7 (sub-quantum): expected a cache miss but the cache hit` (`exit=1`) |
| 守卫 `V-inverse` | `V-inverse` | `FAIL test_stroke_cache_matrix_translation: stroke matrix e=NaN (stroke): cached draw returned 0 "" (cache HIT) but uncached draw returned 1 "Invalid or singular canvas stroke matrix"` (`exit=1`) |
| 守卫 `V-local-range` | `V-local-range` | `FAIL test_stroke_cache_matrix_product: inverse(stroke) x path matrix > 1e7 (stroke): cached draw returned 0 "" (cache HIT) but uncached draw returned 1 "Invalid vector path transform"` (`exit=1`) |

### 3.2 其余 14 个 `SURVIVED` 变异体说明（均为结构性必然，非测试漏洞）

1. **`F-flags` / `F-seg_count` / `F-dash_count`（3 项）**：即使删除这三个显式哈希行，其控制的分支/循环（`rule` vs 描边字段、`for(i<count) verb`、`for(i<dash_count) dashes[i]`）仍会执行不同次数的 FNV-1a 迭代，因此 64-bit 哈希本身依然不同；在移除哈希比对的 `H-flags`、`H-seg_count`、`H-dash_count` 下三者均立即 `KILLED`。
2. **`C-flags` / `C-rule` / `C-seg_count` / `C-verbs` / `C-cap` / `C-join` / `C-dash_count`（7 项）**：均为无量化的离散整数，64-bit FNV-1a 哈希直接区分非碰撞输入；移除哈希比对后在 `H-*` 中 7/7 全部 `KILLED`。
3. **`H-hash-only`（1 项）**：对照变异体，预期通过（`0 failure(s)`），证明 `path_key_matches` 脱离哈希也能独立拦截全部失配。
4. **`F-pt_count` / `H-pt_count`（2 项）**：数学冗余不变量——每个 `verb` 对应固定点数（`CLOSE=0`, `MOVE/LINE=1`, `QUAD=2`, `CUBIC=3`），只要 `seg_count` 与 `verbs[0..seg_count-1]` 相等，`pt_count` 必然相等。
5. **`V-dash-period`（1 项）**：`build_path_key` 中的纵深防御早退——在 `fix-cache-key.patch` 将 `dashes[i]` 比对改为精确 `!=` 后，全零虚线 `{0}` 永远无法匹配缓存中任何合法虚线（合法项必有至少一个 `>0` 元素），因此会安全 miss 并交由 `exr_vector_dash` 正常报错（修复前在 `1e-12` 容差下 `{0}` 曾误命中 `{1e-13}` 并导致 `test_stroke_cache_dash_validation` 失败）。

---

## 四、测试套件与全量 CTest 验证

- **新增单元测试**（`fixed/unit-test.txt`）：`exreader-stroke-cache-key-test.exe` — **18/18 PASS，0 failure(s)，224 lockstep draws，`exit=0`**。
- **全量 CTest**（`fixed/ctest.txt`，在 `build-gate -Holder agy-Breg` 保护下于 `build/perf` 运行）：
  - **`100% tests passed out of 578`**（原 577/577 + 新增 `#319 native-stroke-cache-key` 0.18 sec，总耗时 `116.47 sec`，`exit=0`）。

---

## 五、最终结论

1. **未修复的原始 B（`1beab649c`）：不可合并（FAIL）**。六路审计指出的「缓存命中跳过描边矩阵校验」风险已被对抗 PDF（`07_matrix_validation.pdf`：`STATUS 1 vs 0`）与单元测试实锤复现，同时暴露出 `1e-12` 线宽容差引起的细线渲染错误（`08_hairline.pdf`：`7,944 px` 差异）。
2. **应用 `fix-cache-key.patch` 后的 B（`0eff5b3dd` 起）：描边缓存回归门槛通过（PASS — 缓存键与命中校验阻塞已解除）**。
   - 8/8 对抗 PDF 夹具在 A / A2 / B / C 四路逐像素与错误码完全一致；
   - 18/18 锁步回归用例与 578/578 全量 CTest 全过；
   - 全部 16 个非冗余缓存键字段及 2 个独立命中前校验守卫在删字段/删守卫变异测试中均 100% 触发测试失败。
3. **合并 `perf/dense-vector-path-residual` 到 `main` 前仍需注意的独立前置项（本任务范围外，如实列出）**：
   - **重测性能与五项冻结小夹具门槛**：`fix-cache-key.patch` 在 `build_path_key` 中增加了 `inverse(sm)`、`multiply(inv, transform)` 及局部点范围校验，修改了 `src/canvas.c`；`evidence/dense-vector-path-residual-20261119/REPORT.md` 中 `1beab649c` 的旧性能数据已过期，且五项冻结小夹具门槛尚未在新 DLL 哈希上重跑通过，合并前需按测量政策重测验收。
   - **审读附带发现的非键加固项**：
     - `src/canvas.c:592`：`entry->work<(size_t)256*1024*1024 && c->work<=(size_t)256*1024*1024-entry->work-4096` 在 `entry->work` 落于 `(256 MiB - 4096, 256 MiB)` 时存在无符号减法下溢风险，建议改为 `entry->work<=(size_t)256*1024*1024-4096 && c->work<=(size_t)256*1024*1024-4096-entry->work`（与 S6 审计意见一致）。
     - `src/canvas.c:354,433`：路径相对控制点 `pts[i]` 仍保留 `1e-9` px 容差（与 `floor(x0+1e-9)` 偏置），用于吸收整像素平移的浮点舍入误差；若要求严格零容差几何键，需另行评估。
