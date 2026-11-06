# 测量工具（probes）

这些是 `evidence/` 下各项测量结果的**实际测量程序**。收进仓库的原因很简单：
一份说"11,406 对相邻标点里 0 次挤压"的报告，如果没人能用同一段程序重跑，它就只是一段文字。

这些程序**只用公开 SDK 接口**（`exreader.h`），不读内部结构、不写文档正文、不修改任何状态：
它们打开文档 → 布局 → 读字形/行盒坐标 → 打印 JSON 行。输出里没有正文字符串，只有码点与几何。

## 程序清单

| 文件 | 用途 | 产出证据 |
|---|---|---|
| `cjk_measure.c` | CJK 行首/行尾禁则违规计数、相邻标点对（PAIR）的 advance/extent/reference、竖排与横排模式核对 | `evidence/cjk-corpus-20261105/RESULTS.csv`、`evidence/real-books-20261105/CJK-PUNCTUATION.csv`、`CJK-LINEBREAK.md` |
| `alias_page_probe.c` | 逐页读取写作模式，核对 `-epub-writing-mode` 别名是否生效 | `evidence/real-books-20261105/CSS-ALIAS-RESULTS.csv`、`CSS-ALIASES.md` |
| `alias_column_probe.c` | 逐列坐标，判竖排列序 | `KUSAMAKURA-PAGES.csv` |
| `alias_consistency_probe.c` | 同一文档在别名修复前后的布局一致性 | `CSS-ALIASES.md` |
| `inspect_indent_layout.c` | 段首缩进：同段首行与续行的原点差 | `TEXT-INDENT.csv`、`TEXT-INDENT-PIXELS.md` |
| `sample_pages.c` | 按比例抽样位置渲染整页（第 1 / 25% / 50% / 75% / 末页） | `RESULTS-PAGES.csv`、`PAGES-SUMMARY.md` |
| `render_visual.c` | 单页渲染成 PNG，供视觉评审 | `VISUAL-REVIEW.md` 中引用的截图 |
| `render_neighbors.c` | 相邻页渲染，用于定性"空白页是章末还是分页缺陷" | `PACHINKO-PAGINATION.csv` |

## 构建

这些程序用公开头文件编译，链接 SDK：

```
cc -O2 -I <repo>/include cjk_measure.c \
   -L <sdk-build-dir> -l exreader -lm -o cjk_measure
```

Windows / MSVC：

```
cl /O2 /W4 /I <repo>\include cjk_measure.c /link /LIBPATH:<sdk-build-dir> exreader.lib
```

`<sdk-build-dir>` 指 SDK 构建产物目录（含 `exreader.lib` / `libexreader.a`）。
头文件与库来自同一个 commit 才有意义——**跨版本混用会得到无法解释的数字**。

## 调用约定

```
cjk_measure <book.epub> <font.otf> <vertical>
```

第三个参数是**模式**，不是页数上限：

- `0` = 按横排测量（注入 `html,body{writing-mode:horizontal-tb!important}`，按行 y 分组、沿 x 排序）
- `1` = 按竖排测量（不注入 CSS，按 x 分列、沿 baseline 排序）

⚠️ **对本就用横排排版的书写 `1`，得到的是测量假象**（一行被当成一列）。
`evidence/cjk-corpus-20261105/RESULTS.csv` 中后 3 行就是这种情形，已在 `REPORT.md` 与 INDEX 条目标注作废。
要判断某本书实际怎么排，看 `CJK_SUMMARY` 的 `wrong_mode_pages`：它统计的是"测量假设与引擎实际布局不一致的页数"。

## 已知限制

- 禁则字符集是**子集**：行首禁 `。、，．）」』！？：；`，行尾禁 `（「『`。`》〉】”’` `《〈【“‘` 不在检查范围。
  所以"违规 0"只代表这个子集内为 0。
- 不输出**逐行汉字数**（只有总字形数与总行数），因此"每行 28–34 字"这类判据无法由本工具验证。
- 不输出字形在 em 框内的位置，所以"句读居中 / 靠左下"这类规范无法测量。
- 不报缺字与字体回退。

## 这些数字对应的版本

测量时的引擎版本为 `3.42.0`。证据文件里记录了各自的运行时间与参数；
本目录只保证**程序与记录一致**，不保证在新版本上得到同样的数字——重跑后如有差异，以新数字为准并记录差异。
