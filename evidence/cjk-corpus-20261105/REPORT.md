# CJK 语料排版测量 — 2026-11-05

只读测量。没有改产品代码，没有跑 CI，没有开窗口。书籍、解包内容、原始输出都不入库。

- 工具：`css-alias-20261105/after/exreader-cjk-measure.exe`（源码 `css-alias-20261105/cjk_measure.c`）
- 字体：`EXReader-Windows-delivery-20261104/payload/Reader.otf`
- 页面配置（源码写死）：`exr_layout_options{720,1040,36,28,1.5f,10}`，字号 28 px
- 原始输出（仓库外）：`%TEMP%\cjk-Ft0T\<book>.out`（参数 0）、`<book>.v1.out`（参数 1）

## 0. 参数更正（先读这一节）

第三个参数**不是** `max_pages`。源码是 `vertical=atoi(argv[3])`：

- `0`：横排测量。注入 `user_css="html,body{writing-mode:horizontal-tb!important}"`，按行 `y` 分组，沿 `x` 排序。
- `1`：竖排测量。不注入 CSS，按行 `x` 分组（每组当作一列），沿 `baseline` 排序。

**有效数据是参数 0 的三行**（RESULTS.csv 前 3 行）。参数 1 的三行用来复现任务给的唐詩样例（`columns:119, wrong_mode_pages:86`，逐字段一致），但这组数据是测量假象（见 §c），不能拿来下结论。

## 1. 三本 CJK_SUMMARY（参数 0，有效）

```
紅樓夢   {"vertical":false,"parts":31,"pages":1652,"columns":37154,"head_violations":4,"tail_violations":0,"punctuation_pairs":54,"glyphs":821108,"excluded_ruby_glyphs":0,"wrong_mode_pages":0,"status":0}
醒世恆言 {"vertical":false,"parts":21,"pages":1170,"columns":26510,"head_violations":0,"tail_violations":0,"punctuation_pairs":11352,"glyphs":562814,"excluded_ruby_glyphs":0,"wrong_mode_pages":0,"status":0}
唐詩     {"vertical":false,"parts":3,"pages":86,"columns":1786,"head_violations":0,"tail_violations":0,"punctuation_pairs":0,"glyphs":50095,"excluded_ruby_glyphs":0,"wrong_mode_pages":0,"status":0}
```

参数 1（仅供对照，无效）：紅樓夢 columns 1909 / pairs 1353 / wrong 1652；醒世恆言 1250 / 11872 / 1170；唐詩 119 / 0 / 86。三本的 head 和 tail 违规都是 0。

## 2. 四问

### a) 行首/行尾禁则违规是否为 0

- 行尾（tail）：三本都是 **0**。
- 行首（head）：醒世恆言、唐詩为 0；**紅樓夢 4 处**：

| page | part | codepoint | 字符 | along |
|---|---|---|---|---|
| 83 | 2 | U+FF1A | ： | 50.0 |
| 203 | 4 | U+FF1A | ： | 50.0 |
| 1033 | 20 | U+FF0C | ， | 50.0 |
| 1148 | 22 | U+FF1A | ： | 50.0 |

（`along` = 50.0 表示该字形在行首位置。）

工具检查的字符集是有限的：行首禁止 `。、，．）」』！？：；`，行尾禁止 `（「『`。`》〉】”’` 和 `《〈【“‘` 不在检查范围内。所以 0 只代表这个子集内没有违规。

### b) punctuation_pairs / PAIR 能得出的挤压结论

PAIR 记录的是同一行内两个相邻标点（同字体、同字号），字段有 `advance_a/b`、`extent`（两字形实际占位），以及 `reference`（同行汉字的 advance，这里是 28 px = 1em）。

- 醒世恆言 11352 对：全部 `advance_a = advance_b = 1em`，`extent = sum = 2em`。**挤压率 0/11352**。主要组合是 `：「` 5191、`。」` 3585、`？」` 1478、`！」` 739。
- 紅樓夢 54 对：40 对 `extent = 2em`（`……` 30 对、`：：` 2 对等），**全部无挤压**（extent 和 sum 的差都 < 0.5 px）。另有 14 对 `，—`、`．—` 的 extent 为 2.68em，原因是 **U+2014 的 advance = 47 px = 1.68em**，不是 1em。
- 唐詩：0 对，**无法测量**。

结论：相邻标点一律按全角加全角排，**没有任何标点挤压**（没有半角化，也没有 kerning）。U+2014 破折号在这款字体或引擎下宽度是 1.68em，不是全角。

### c) wrong_mode_pages 的含义

源码：`wrong_mode += exr_layout_writing_mode(page) != (vertical ? VERTICAL_RL : HORIZONTAL_TB)`。它统计的是**工具的测量假设（argv[3]）与引擎实际布局方向不一致的页数**。

唐詩 86/86 的依据：

1. 样例中的 `"vertical":true` 来自参数 `1`，是工具自己的假设，不是书的声明。用参数 1 重跑，得到的 `columns:119, wrong_mode_pages:86` 与样例完全一致。
2. 三本 epub 解包后全文 grep，没有任何 `writing-mode`。OPF `<spine toc="ncx">` 也没有 `page-progression-direction`。只有 `xml:lang="zh"`。书本身**没有声明竖排**。
3. 参数 1 不注入 CSS，引擎给出的布局不是 `vertical-rl`，所以 86 页全部计入。参数 0 强制 horizontal-tb 后，wrong_mode = 0，说明引擎确实排成横排。
4. 旁证：参数 1 把行 `x` 当作列坐标。横排时所有行的 `x` 相同，一页被并成约 1 "列"，所以 86 页只有 119 列（参数 0 是 1786 行）。

判定：**不是"应横排却排成竖排"**，实际布局就是横排。也不是书内声明与布局冲突，因为书没有声明。准确说法是"**测量声明（vertical=1）与实际布局（非 vertical-rl）不一致**"，在两个选项中属于后者，但"声明"一方是测量工具，不是书。参数 1 下的 columns 和 PAIR 数据（例如紅樓夢 `——` 的 extent 为 2.46em）是跨行合并造成的假象，作废。

### d) 每行/每列汉字数

工具**不提供**。CJK_SUMMARY 只有总 `glyphs` 和总 `columns`（行数）；glyphs 含标点、空白、隐藏字形和标题，没有逐行汉字计数字段。**无法测量。**

## 3. 繁体/简体差异要点

| 要点 | 本语料（繁体） | 简体通行 | 本次可测？ |
|---|---|---|---|
| 引号 | `「」『』`（PAIR 中 `：「`、`。」` 占绝大多数） | `“”‘’` | 已观测到繁体引号；工具的禁则集不含 `“”‘’`，测简体书时行首/尾检查会漏 |
| 句读位置 | 台湾规范：`，。` 居中 | 大陆规范：靠左下 | **无法测量**（工具不输出字形在 em 框内的位置） |
| 全角冒号/感叹 | `：！？` 全角 | 同 | 已测，advance 均为 1em |
| 字形覆盖 | 需覆盖繁体字（紅、樓、恆、詩） | 简体字 | **无法测量**（工具不报缺字或回退） |
| 竖排习惯 | 繁体古籍常见竖排 | 以横排为主 | 本语料没有声明竖排，所以竖排表现**未被测到** |

## 4. 中文可读性最小清单（5 项）

| # | 项目 | 判定 | 依据 |
|---|---|---|---|
| 1 | 行首禁则（`。，：` 等不出现在行首） | **未达标** | 紅樓夢 4 处（p83/203/1148 `：`，p1033 `，`）；另两本 0 |
| 2 | 行尾禁则（`（「『` 不出现在行尾） | **达标** | 三本 0（仅限工具检查的子集） |
| 3 | 相邻标点挤压（如 `。」` 不占 2 个全角） | **未达标** | 11406 对有效 PAIR 中 0 对挤压，extent = sum |
| 4 | 破折号/省略号按全角占位（`——`=2em、`……`=2em） | **未达标** | `…` = 1em 达标；U+2014 advance = 1.68em，不是 1em |
| 5 | 每行汉字数在合理范围 | **无法测量** | 工具无逐行汉字计数 |
