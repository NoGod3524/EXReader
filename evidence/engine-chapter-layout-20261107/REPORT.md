# 引擎章节结构排版验收 · 2026-11-07

A–C 三项完成。代码基于 main `c9dfc6c14a0c3d2372da4e8a6f02dc348309610f`，已接入 #69 的 U+3000／NBSP 投影规则。不改 `examples/`、`.github/`；未手动触发 CI，未取消 workflow run。

## 实现

- **A 章首分页**：`src/pager.c` 在进入 spine 章节、HTML 标题和原文标题时结束当前行并强制分页；页尾余量保留。`src/source_structure.h` 扫描原文逻辑行，共用 `exr_projection_space` 映射到标准化 UTF-8 偏移；不修改正文或树。空行不能把标题后的正文继续标成标题，CRLF 用例已覆盖。
- **B 标题与装饰线**：`src/style.c` 识别 h1–h6、role=heading 和完整 class token `title`、`chapter-title`、`chapter_title`、`chaptertitle`；`src/flow.c` 对标题／装饰线关闭空格及 CJK 字间 justify。`include/exr/layout.h` 新增 `exr_layout_blocks`、`exr_layout_page_structure`，输出块类型、源范围、行范围、章首标记和当前 pager 的章节序号。宿主可按装饰块行范围选择绘制。既有 `exr_page`、`exr_line` 和配置记录 ABI 不变。
- **C 缩进**：`src/flow_internal.h` 集中计算首行偏移，发射、断行和 intrinsic 测量共用。普通 CJK `<p>` 无声明时默认 2em；书内／用户 CSS（含继承的 0）覆盖该默认值。源内双全角空格在 #69 投影中被折叠后，以 2em 几何偏移恢复其排版意图；CSS text-indent 只作用于实际 HTML 段落首行，后续源内逻辑段不重复叠加 HTML 首行缩进。

## 六项验收

### 1. 紅樓夢章首分页

原书 `hongloumeng-24264.epub`，Reader.otf，1552×928、margin=0、font=18、line-height=1.6、paragraph-spacing=14.4。

- 第二十六回末页：全书第 **69** 页，part=6（零起始）内第 **4** 页，31 行，末行底部 **837px**，余白 **91px**。
- 第二十七回首页：全书第 **70** 页，同 part 内第 **5** 页；标题 `line_start=0`、`line_count=1`，即第 **1** 行。
- `starts_chapter=1`、`contains_title=1`；当前 part/pager 的 `chapter_index=3`。
- 源偏移 **27088–27151**，与上一页结束偏移 **27088** 相接。
- 普通与 bounded 探针均得到 **399 页**，逐条输出一致。

证据：[probe-final.jsonl](probe-final.jsonl)、[probe-bounded-final.jsonl](probe-bounded-final.jsonl)。全部页码均从 1 开始；part 和 API 行索引按其原始零起始值记录。

### 2. 标题字距

第二十七回标题有 **20** 组相邻字形。实测相邻 x 差 min=max=**18.000000px**；字体默认 advance 为 **18.000000px**；相对 advance 的最大偏差 **0.000000px = 0em**，小于允许的 **0.01em = 0.18px**。#69 已折叠源标题中的全角空格，标题文字本身保持该投影结果。

### 3. 段首缩进与原始原因

目标正文“紫鵑雪雁素日知道”位于全书第 **70** 页第 **5** 行：首字 x=**45.000000px**，续行起点 x=**9.000000px**，差 **36.000000px = 2em**。

原 EPUB 的 `OEBPS/2878037014660817796_24264-0-6.txt.html` 将目标正文与前面的正文写在同一个 `<p id="id00035">`，仅用原始换行和两个 U+3000 表示新段。该 part 有 **113** 处这样的行首双全角空格。`0.css` 的 `body > p {text-indent:1em}` 只作用于 HTML `<p>` 第一行，不能给它内部的新逻辑段缩进；`h2 + p, h3 + p, h4 + p {text-indent:0}` 也不是目标段顶格的原因。原先折叠换行后，目标逻辑段直接接在前段中。

新默认值／CSS 覆盖专项实测（18px 字，最后一例为 20px）：无声明 **36px**；`p{text-indent:0}` **0px**；`1em` **18px**；父元素继承 `0` **0px**；20px 字的 `2em` **40px**；五例再加用户 CSS `0` 均为 **0px**。源内双全角空格单独验证为 **36px**，没有重复叠加默认值。

### 4. 19 本逐页回归

最终完整对照与逐本原因见下节。固定 **720×1040、margin36、font28、line-height1.5、paragraph10**，同一 Reader.otf、原书 SHA-256、方向及嵌入字体设置。使用 `tools/regress/run_realbooks.py` 逐页栅格化并保存 RGBA 有效行字节 SHA-256。

### 5. 全量 ctest

最终合并 main 后 **172/172 通过，0 失败，155.28 秒**。原基线 169 项，新增 3 组。见 [ctest-merged-main.log](ctest-merged-main.log)。构建日志为本机 `build/compile-merged-main.log`、`build/compile-verified.log`。

### 6. 三组新增测试

| 组 | checks | 覆盖 |
| --- | ---: | --- |
| native-chapter-layout-chapter | 54 | 强制分页、页尾留白、原文标题与装饰线、页面／块语义、逐页／缓存重放、CRLF 和空行后的正文恢复 |
| native-chapter-layout-title | 308 | h1–h6、role、四种 class、精确 token 反例、多行标题不拉伸 |
| native-chapter-layout-indent | 41 | 2em 默认、作者／用户／继承覆盖、字号换算、原文缩进不重复 |
| 合计 | **403** | **3/3 组通过** |

见 [chapter-groups.txt](chapter-groups.txt)、`tests/test_chapter_layout.c`。`tests/fixtures/pager-golden.txt` 的 layout-epub 从一个跨 spine 页改为两个独立页，其余 **88 页**金样保持；两个既有窄行测试显式设零缩进以继续验证原来的几何条件。

## 19 本页数与逐本原因

**19/19 成功，0 缺书／失败**；最终渲染 **236.513630 秒**。相对 #69 后 main：**11,061→11,296 页（+235）**，总字形数 **8,648,640→8,648,640**，每一本字形数均不变。比较条件一致（`comparable=true`），原书哈希全部不变；同页序号下 **6,082** 页像素哈希变化，符合分页／重排行为。

相对接手时原基线：**11,083→11,296 页（+213）**；中间 #69 自身减少 **22 页、11,590 个空白字形**，故表中保留两种“改前”列。章首分页和段落恢复改变页数是预期结果；净增页数由后续正文重排决定，不等于强制分页事件的数量。

| 书 | 接手原基线 | #69 main | 最终 | Δ vs main | 原因 |
| --- | ---: | ---: | ---: | ---: | --- |
| A Raisin in the Sun | 354 | 354 | 356 | +2 | 5 个 h2（SCENE 标题）从页中移至页首 |
| Between the World and Me | 228 | 228 | 228 | +0 | 净页数不变 |
| Black Boy | 1011 | 1011 | 1016 | +5 | 3 个 h2、2 个 h3 从页中移至页首 |
| Born a Crime | 501 | 501 | 502 | +1 | 1 个 h2 从页中移至页首 |
| Crying in H Mart | 506 | 506 | 524 | +18 | 21 个 h1 从页中移至页首 |
| How Does It Feel to Be a Problem | 492 | 492 | 493 | +1 | 宣传页 logo 后的 h1 移到本 part 第 2 页（原在第 1 页首个文本行） |
| I Know Why the Caged Bird Sings | 625 | 625 | 625 | +0 | 净页数不变 |
| Pachinko | 1214 | 1214 | 1248 | +34 | 3 个 h1、36 个 h2 从页中移至页首 |
| The Absolutely True Diary of a Part-Time Indian | 560 | 560 | 560 | +0 | 净页数不变 |
| The Autobiography of Malcolm X | 279 | 279 | 279 | +0 | PDF 固定版式 |
| The Distance Between Us | 702 | 702 | 702 | +0 | 净页数不变 |
| The Fire Next Time | 187 | 187 | 189 | +2 | 2 个 h1 从页中移至页首 |
| The Fire This Time | 314 | 314 | 333 | +19 | 3 个 h1、19 个 h2、5 个 h3 从页中移至页首 |
| The House on Mango Street | 181 | 181 | 182 | +1 | 1 个 h3 从页中移至页首 |
| Zami | 624 | 624 | 624 | +0 | PDF 固定版式 |
| 紅樓夢 | 1594 | 1586 | 1686 | +100 | 原文回目分页、逻辑段恢复及缩进 |
| 醒世恆言 | 1166 | 1152 | 1202 | +50 | 原文回目分页、逻辑段恢复及缩进 |
| 唐詩三百首 | 83 | 83 | 83 | +0 | 净页数不变 |
| 草枕 | 462 | 462 | 464 | +2 | h1/h2 标题在竖排中另起页 |
| 合计 | 11083 | 11061 | 11296 | +235 | 19/19 成功 |

最终逐页哈希与身份：[before-main.json](before-main.json)、[after-final.json](after-final.json)、[after-final.diff.json](after-final.diff.json)。接手时对照为 [before.json](before.json)。中断前候选、恢复时重复运行及其日志也保留。

9 本变化的拉丁书均用旧／新 DLL 的公开 SDK 遍历标题源范围和分页坐标，逐个对应；详见 [latin-title-moves-final.json](latin-title-moves-final.json) 和 `tests/probe_chapter_titles.py`。How Does It Feel 的宣传 h1 本身已是第一页首个文本行，前面还有 logo 图片，所以仅统计“页中行移至第 1 行”的计数为 0；其实际变化是 part=27 的第 1→2 页，文本标题为“What’s next on / your reading list?”，见 [how-title-positions.json](how-title-positions.json) 的直接坐标对照。

## 运行身份与复现

[PROVENANCE.json](PROVENANCE.json) 保存源码与 DLL 哈希。接手时的原始基线是 `000caeef`；本次又单独渲染 #69 后 main 基线，`d834a3bd` 与 `c9dfc6c1` 的 src/include/CMakeLists.txt 完全相同，基线 DLL 使用 #69 已构建产物。这样可以分别核对接手以来总变化和本 PR 的变化。

```powershell
cmake --build build --parallel 6
ctest --test-dir build --output-on-failure --parallel 6
build/exreader-chapter-layout-probe.exe <hongloumeng.epub> <Reader.otf>
$env:BOUNDED='1'
build/exreader-chapter-layout-probe.exe <hongloumeng.epub> <Reader.otf>
Remove-Item Env:BOUNDED
python tools/regress/run_realbooks.py --manifest tools/regress/corpus.json --dll build/libexreader.dll --font <Reader.otf> --layout tools/regress/layout.json --output <after.json> --baseline <before-main.json> --source-revision <revision-and-worktree-hashes> --workers 4
python tests/probe_chapter_titles.py --before <main.dll> --after build/libexreader.dll --font <Reader.otf> --manifest tools/regress/corpus.json --layout tools/regress/layout.json --diff <after-final.diff.json> --output <latin-title-moves.json>
```

回归比较器在检测到预期分页／像素变化时退出 **1**；成功渲染的数量与 `failed_books` 单独核验。
