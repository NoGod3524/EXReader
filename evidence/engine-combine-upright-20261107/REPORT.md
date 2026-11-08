# 竖排合字 `text-combine-upright` 验收 · 2026-11-07

基于 main `3aa9af50`（含已合入的 #72）。只改 `src/`、`include/`、`tests/`、`tools/`、`CMakeLists.txt`；未碰 `examples/`、`.github/`。

## 实现（规格 1–7）

| 规格 | 实现 |
| --- | --- |
| 解析 | `src/style.c` 新属性 `text-combine-upright`：`none` / `all` / `digits [2-4]`；旧 EPUB 值 `horizontal` 按 `all`；别名 `-epub-text-combine`、`-webkit-text-combine` 早已映射。可继承。非法值整条忽略。 |
| 1 合成范围 | `src/inline.c: combine_mark`：喂入第一个标量时在**同一文本节点内**前瞻。`digits N`：连续 ASCII 数字 2..N 个（缺省 N=2）；`all`：整个文本节点 1–4 个字符（含标点）。块内后续标量被并入首个标量的字素与行段（清除 GRAPHEME/LINE/AUTO_HYPHEN 边界），所以断行、连字符、应急拆分都落不进块中。 |
| 2 宽度 | 整形后 `combine_groups`：块内按横排 advance 求和 W；缩放 `s=min(1, size/W)`；成员字号 = `size·s`；整块 advance = 1em，由**最后一个**成员携带（其余为 0，这样各成员的 pen 都在格首）。`offset_x = s·(累计+自身偏移) − s·W/2`，即水平居中。 |
| 3 基线 | 用 FreeType 无 hint 的真实字形上下沿 (top, bottom)：`offset_y = −(size/2 + (top+bottom)/2)`，墨迹中心落在字身中点。`project_line` 对合成成员跳过竖排字形的 vert bearing 修正，只投影列中心。 |
| 4 不可拆分 | 同 1：块内无断点；放不下时整块进下一列（见验收 4）。 |
| 5 对齐 | 块只有一个 1em advance；`exr_inline_cjk_gap`、标点压缩、尾部标点规则都排除合成字形，所以两端对齐只在块与块之间分配，块内不拉伸。 |
| 6 不合成 | 横排不进入该路径；`none`（含初始值）、数字超过 N、`digits` 遇非数字、`all` 超过 4 字符或含空白都不合成。 |
| 7 回退 | 不依赖 vert/vrt2：合成成员本来就用**横排整形与横排度量**（`vertical=0`、`exr_measure`），再缩放居中。没有 OT 的字体走原样横排度量。 |

公共面：`EXR_GLYPH_COMBINED = 16384`（`include/exr/text.h`）。合成字形是 `VERTICAL` 且非 `SIDEWAYS`，所以 `exr_glyph_matrix` 与光栅层**无需改动**——就是未旋转的、已缩放的字形按存好的偏移绘制。`layout.c`、`positioned.c` 的合法 flag 掩码加入该位。

**开关**：初始值按 CSS 为 `none`，只有书内/用户 CSS 声明才合成；因此“默认开启”落实为：书里写了 `-epub-text-combine: horizontal`（草枕就是）即合成，用户 CSS `text-combine-upright:none` 可关。没有新增布局配置字段，避免改 ABI。

## 七项验收

测量对象：草枕 `kusamakura-japanese-vertical-writing.epub`，720×1040、margin36、字号28、Reader.otf（`tools/regress/layout.json`）。探针 `probe_combine.py`，数据 [blocks.json](blocks.json)。

### 1. 真书合成块（改前/改后并排图）

全书 **25** 个合成块，分布在 4 页（全书页 2、459、462、463）。书内用 `<span class="tcy">` 的是封面与后付的编号/年月。**与任务描述不符之处**：书里没有 `10`；`。` 不在任何 tcy 里（正文没有被声明合成的标点）；两位数合成块共 8 个：`12`（封面）、`22`、`62`、`12`、`46`、`47`、`17`、`28`。其余 17 个是单个数字（`all` 下也成块，从横躺变为直立）。

| 块 | 页 | 字号 px | 合成块 advance px | 墨迹宽 px（像素实测） | 改前列向占位 px |
| --- | ---: | ---: | ---: | ---: | ---: |
| 12 | 2 | 14.93 | 14.93 | 13 | 16.0 |
| 22 | 459 | 16.80 | 16.80 | 16 | 18.0 |
| 62 | 463 | 13.44 | 13.44 | 13 | 14.0 |

块 advance = 字号，偏差 0.00 px；墨迹宽小于等于字号（字面侧距），最大差 1.93 px（封面 `12`，字号 14.93，墨迹 13）。没有“± 1px”意义上的墨迹宽等于字号，因为数字自带左右侧距，不应撑满。

并排图（左=改前，右=改后）：[block-04-12.png](block-04-12.png)、[block-06-22.png](block-06-22.png)、[block-13-62.png](block-13-62.png)、[block-14-12.png](block-14-12.png)；整页 [page-before-463.png](page-before-463.png) / [page-after-463.png](page-after-463.png)。改前数字横躺成 2 个字宽，改后一格内横排。

### 2. 缩放与垂直居中偏移

8 个两位数块：缩放 0.9333（封面 `12`、`22`）与 0.9600（463 页六块）；`offset_y` −12.66、−14.25、−11.45…−11.53 px；
墨迹中心相对字身中心的像素实测：沿列向 −0.43…−1.21 px（平均绝对 0.98，最大 1.21），横向 0.17…0.62 px。残差来自光栅整数对齐与阈值取点，未做额外补偿。

### 3. 连续 4 位数字

合成数据（`probe_synthetic.c`，Reader.otf 28px，`令和2026年の春`，`digits 4`）：缩放 0.4375，成员字号 12.25 px，数字间距 7.0 px；4 个数字的墨迹整体宽 **26 px**、高 9 px，位于 28 px 字身内，列中心偏差 x 0.4、y −0.5 px。图 [synthetic-a-before-after.png](synthetic-a-before-after.png)（左=改前，右=改后）。真书里没有 4 位数字的 tcy。

### 4. 放不下时整块换行

页高留出 5.5em（154 px）的列，放 `春夏秋冬春12月`：5 个表意字占 140 px，行末剩 14 px = 0.5em。结果：`1`、`2` 两个成员的 baseline 都是 28.00、同属第二列（x 64.80），整块 28 px，**没有拆开**；第一列 5 个字的余量被摊到 4 个字间隙（base 28→154，末字贴列尾 182），块没有被拉伸。改前 `1`、`2` 横躺各占 16 px，共 32 px。图 [synthetic-b-before-after.png](synthetic-b-before-after.png)。单测 `native-combine-upright-wrap` 用 20px 字体做同样断言。

### 5. 横排与其他书回归

同一固定参数、同一 Reader.otf，改前/改后各渲染 19 本（`tools/regress/run_realbooks.py`）：**18 本页数、字形数、每页像素 SHA-256 全部不变**（含 紅樓夢 1686、醒世恆言 1202、唐诗 83 三本横排 CJK）。草枕 **4 页**哈希变化（2、459、462、463，正是 tcy 所在页），其余 460 页不变。改前 DLL 的 19 本逐页哈希也与上一轮 main 证据 `engine-chapter-layout-20261107/after-final.json` 完全一致，说明基线可靠。数据：[realbooks-compare.json](realbooks-compare.json)。

### 6. 竖排书页数

草枕 **464 → 464**，不变。该书正文没有被声明合成的数字，tcy 只出现在封面和后付，且合成块只有 25 个、各占一格，没有改变任何一页的行装填；只有 4 页像素变化。任务预期的“每行多装字”在这本书上没有机会发生。全 19 本总页数 11,296 → 11,296。

### 7. ctest

**191/191 通过**，0 失败（39.2 秒，[ctest.log](ctest.log)）。新增 **3 组**，即改动前为 188 项（191−3 推算，未单独重跑改前 ctest）：

| 组 | checks | 覆盖 |
| --- | ---: | --- |
| native-combine-upright-geometry | 38 | 1em 宽、缩放、居中偏移、4 位数字入格、`exr_glyph_matrix` |
| native-combine-upright-modes | 58 | 14 个模式/拒绝/别名/覆盖用例；横排逐字段不变 |
| native-combine-upright-wrap | 13 | 行末 0.5em 整块换行、两端对齐不拉伸块、不合成时数字仍横躺 |

合计 109 条断言（其中 modes 含 14 个表驱动用例）。夹具字体 `tests/fixtures/fonts/combine.ttf`（`tools/generate_combine_test_font.py` 生成，MIT）。`tests/test_vertical.c` 里“text-combine-upright 尚无实现”的注释已更新，其别名等价用例仍通过。

## 限制

- 只在同一文本节点内合成；跨 `<span>` 的数字不会合成。
- `all` 只接受整个文本节点 ≤4 字符且无空白；超过时不合成（不做 CSS 允许的更宽压缩）。
- 数字块内部用 `FT_LOAD_NO_HINTING` 度量；在 13px 左右光栅整数对齐会带来约 1px 的居中残差（见验收 2）。
