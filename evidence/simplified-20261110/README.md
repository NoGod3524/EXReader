# A4 简体中文语料验收 · 2026-11-10

本任务只增加语料准备、验证、合成测试与证据；未修改排版或字体引擎、原有断言、`.github/`。基线源码为 `03ccf53e`。

7 本书均已进入本机 `tests/corpus/simplified/`（git 忽略目录）：5 本古腾堡完整书经固定 OpenCC t2s 0.1.7 转为简体，另有 2 本原生简体技术书。古腾堡原件仍是繁体，未把原件冒充简体版。《Python HOWTO》保留完整 HOWTO 分册的 31 个 spine 文档（含版权/许可）；《简明 Python 教程》保留 SUMMARY 的全部 26 章、全部插图。

## 语料与原件指纹

| 书籍 | 页数 | 字形计数 | 来源/覆盖 |
| --- | ---: | ---: | --- |
| 呐喊 | 500 | 98,552 | [fiction/dialogue](https://www.gutenberg.org/ebooks/27166) |
| 彷徨 | 168 | 78,598 | [fiction/dialogue](https://www.gutenberg.org/ebooks/24042) |
| 朝花夕拾 | 98 | 54,237 | [prose](https://www.gutenberg.org/ebooks/25271) |
| 野草 | 76 | 37,378 | [prose-poetry/short-lines](https://www.gutenberg.org/ebooks/25242) |
| 唐诗三百首 | 77 | 46,670 | [poetry/short-lines](https://www.gutenberg.org/ebooks/52323) |
| Python 3.14 HOWTO 中文完整册 | 924 | 436,654 | [native-simplified/tables/code/mixed-numerals](https://docs.python.org/zh-cn/3.14/howto/index.html) |
| 简明 Python 教程 4.08c | 357 | 116,938 | [native-simplified/images/dialogue/code/mixed-numerals](https://github.com/LenKiMo/byte-of-python/tree/e5dbfee7e5ccb63d980743dfdc0ba2b181dc9630) |

**合计：2,200 页 / 869,027 字形。** 页数来自全书全部 part，字形数为 SDK layout_glyphs 数量（含布局保留的空白等）。

| 语料 ID | 简体入库 EPUB SHA-256 | 原始下载 SHA-256 |
| --- | --- | --- |
| pg27166-hans | `cd54011000139a0b6081cfc5e1f6e83c43d095df13a5186ea3e2a8ea80e735f1` | `f953cde7e07fbfef77ff4a9147339dd233e1e6a1aa011195438f245db0626ecf` |
| pg24042-hans | `67f495d27ed857e44d4ade5d3a576d792cd1a56a4dafdc600fd5277861b9d8f8` | `959cfd19c8a1431784d46e7b73f7f8685dbc971b9ab8fa41e8cdfa5f8170b53e` |
| pg25271-hans | `57f1b410c112194f87eabfeb0178d94eaf935d849f45624cf57ca76d219e3fe3` | `4db0969f6be9a53a70f41ecdfa0ad11394c167c12ff935abefe731ec4e86b502` |
| pg25242-hans | `8a458bd96462cb4a2897657ecc62922a2f5ab7a20dce748263f4ead5741c633c` | `a5a20f29b7dbc0a49a3275555acf7f492742bfe30ebf2e743bc14ca1eb29712c` |
| pg52323-hans | `796127b5c8cf0ccc9b4281fdcedd9f19bc85f360eb5662d62065dd2e4534f446` | `cb78d59ad6846a4e0102a935dc63fd5bdc76c52966e76558f0451e6df73655f6` |
| python-howto-hans | `9a94735a17d733493bd90fffd2b68415783efa23b212a2e080744e7277df655a` | `8899607340bd1df2941e73a6cd7e4acc3d8c532f5c21d886a49e16e7129f1347` |
| byte-of-python-hans | `342de6c1a25ccc40ee97a01a7d706eb2ef4b7f0ae2aeb47675cfed960b522892` | `e809e371c1bc59c822e644be05732f710f6fdd0fb83d1a296f2a1211541dff04` |

下载地址、许可、转换方式与转换字数在 [`simplified.json`](../../tools/regress/simplified.json)。鲁迅及唐诗为古腾堡美国公版语料；Python HOWTO 按 PSF License 2 使用；《简明 Python 教程》为 Swaroop C H 著、漠伦译，CC BY-SA 4.0。原始下载和转换结果全部保留本地，重新下载若遇远端版本变化，准备工具会因哈希不符停止，不自动接受新版本。

## 五项验证

1. **标点/挤压：0 违规。** 43,376 次符合等宽条件的标点观测，5,843 个已挤压字形、3,558 对相邻标点；另计 31,389 个 ASCII 标点。核对半 em 下限、终端标点串总占一 em、相邻挤压上限及中日韩上下文中 ASCII 的原始 advance。比例字形、合成粗体和上下文 GSUB 使用实际字形的度量，不套用等宽规则。
2. **字形：串字形 0/20。** 发/髮、后/後、里/裏、台/臺、干/乾、云/雲、面/麵、只/隻、钟/鐘、国/國、汉/漢、书/書、门/門、风/風、东/東、车/車、马/馬、鱼/魚、龙/龍、鸟/鳥。每组两字各自源 Unicode、输出 Unicode、独立 fontTools cmap glyph ID 一致，无缺字标志；两字 glyph ID 与单字页面像素哈希不同。
3. **断行：自动折行禁则 0 违规，行尾禁则 0 违规。** 全书使用既有 CJK 观测器的行首/行尾集合；另外的混排段落用真实字体测 140/220/360/720 px 页宽。新增 native 测试覆盖 4 段 × 3 宽度 × 横/竖排 = 24 种版面，逐一比较整文、pager 与 session 的字形/像素结果，并检查全角和 ASCII 行首。两处原文 `<br/>` 强制在句号/逗号前换行，单列 `head_source_br=2`；保留原文，自动折行违规计数为 0。
4. **数字：14,595 个阿拉伯数字字形、9,693 个中文数字字形。** 对照段落与窄宽控制包含年份、时间、百分数、小数、中文数量和阿拉伯数量。
5. **稳定性：7/7 本两次独立打开并全书分页/渲染，2,200/2,200 页一致。** 页数、逐页字形数、逐页 RGBA 哈希、完整 glyph/line 布局哈希变化均为 0；详见 [`simplified.diff.json`](simplified.diff.json)。

全书另有 **249 个缺字标记**：原件私用区字符 232 次、扩展区汉字 2 次、附加拉丁字母 10 次、棋子 3 次、emoji 2 次。它们与指定 20 组简繁异体的串字形检查分别计数，未把缺字说成覆盖成功；逐码点频次见 [`missing-source-codepoints.json`](missing-source-codepoints.json)。

## 简繁对照

3 段为本任务自写的同内容简繁对照，文本见 [`simplified-comparison.json`](../../tests/fixtures/simplified-comparison.json)。共用 Noto Sans CJK SC、28 px 字号及同一页宽/标点。下表差值 = 繁体 − 简体。

| 段落 | 页宽 | 行数 简/繁 | 可见字数 简/繁 | 行数差 | 字数差 | 每行字数不同的行 | 标点位置不同的行 | 像素不同页 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| dialogue | 360 | 10/10 | 105/105 | 0 | 0 | 0 | 0 | 1 |
| dialogue | 720 | 5/5 | 105/105 | 0 | 0 | 0 | 0 | 1 |
| numbers | 360 | 9/9 | 101/101 | 0 | 0 | 0 | 0 | 1 |
| numbers | 720 | 4/4 | 101/101 | 0 | 0 | 0 | 0 | 1 |
| mixed | 360 | 10/10 | 99/99 | 0 | 0 | 0 | 0 | 1 |
| mixed | 720 | 5/5 | 99/99 | 0 | 0 | 0 | 0 | 1 |

每行字数数组（简繁两版结果相同）：

- dialogue / 360：`[8, 10, 11, 11, 10, 11, 11, 11, 11, 11]`。
- dialogue / 720：`[21, 24, 24, 24, 12]`。
- numbers / 360：`[11, 12, 10, 16, 12, 8, 12, 11, 9]`。
- numbers / 720：`[25, 27, 26, 23]`。
- mixed / 360：`[11, 12, 11, 11, 11, 10, 11, 10, 10, 2]`。
- mixed / 720：`[26, 23, 24, 24, 2]`。

**实测没有行数、字数或标点位置差异，6/6 对照的字形像素均不同。** 等宽汉字逐字替换且标点未变时，固定字体下可得到完全相同的断行；不能预设必须出现非零差值。原始每行字数与每个标点的行内索引/x 坐标保存在两轮 JSON 和 `summary.json`。

## 图片、表格与首屏

实际渲染 335 个表格单元格框、15 个图片框，其中教程内插图 10 个、古腾堡封面 5 个，图片占位框 0。已人工查看简体正文、真实表格及教程图片页面。每本均有首屏和首个中文正文屏；带图表者另有首个图/表屏。

截图不入 git。完整路径与 SHA-256 见 [`screenshots.json`](screenshots.json)；本机可打开 `tests/corpus/simplified/SCREENSHOTS.md` 浏览全部首屏。对应 PNG 位于同目录 `screenshots/<id>/`。

## 19 本回归与 ctest

- 同一原始字体及既有 `layout.json`，before/after 均 19/19，11,318 页、8,648,571 字形；页数、逐页字形数、所有页像素 SHA-256 变化均为 0。原始 19 本布局配置未改，见 [`realbooks.diff.json`](realbooks.diff.json)。
- 最终全量 **MSVC Release ctest 258/258 全绿，49.13 秒**；包含 sdk-release、旧测试、新增混排断言及 observer 自检。MinGW 的新增 native-line-boundary/observer 亦 2/2 全绿。见 [`ctest.txt`](ctest.txt)。
- 层检查：119 objects，0 inverse references，0 inverse includes；没有新增 src/*.h。
- 正反对照自检会检出错误压缩下限、未挤压相邻对、被改写的 ASCII advance，并验证终端三标点串及结构强制换行分类。既有测试断言未改。

## 配置与复跑

为隔离文字规则，简体语料使用 [`simplified-layout.json`](../../tools/regress/simplified-layout.json)：720×1040、边距 36、字号 28、行高 1.5、段距 10、document_css=0，保留结构、文字、表格和图片。最初 CSS-on 试跑记录在 `SIMP-OUT.txt`：PG24042 源 CSS 留下零宽正文，整套 Python 文档触及布局限额；无文档 CSS 的整套 Python 文档另已完整渲染通过 18,666 页，但最终固定七本验收使用完整 HOWTO 分册。未把 CSS-on 失败抹掉，也未改引擎。

字体为仓库 `tools/host_font.py` 固定的 NotoSansCJKsc-Regular.otf，SHA-256 `2c76254f6fc379fddfce0a7e84fb5385bb135d3e399294f6eeb6680d0365b74b`。完整构建配置、源码哈希、before/after SDK 哈希和 MSVC 测试 SDK 哈希见 [`provenance.json`](provenance.json)。

```powershell
python -m pip install opencc-python-reimplemented==0.1.7 Markdown==3.10.2 Pillow fontTools
python tools/regress/prepare_simplified.py
python tools/regress/check_simplified.py --dll build/a4/libexreader.dll --font <Reader.otf> --output build/simplified-first.json
python tools/regress/check_simplified.py --dll build/a4/libexreader.dll --font <Reader.otf> --baseline build/simplified-first.json --output build/simplified-second.json
ctest --test-dir build/msvc-a4 --output-on-failure -j 4
```

两轮完整的简体与 19 本逐页记录以 `.json.gz` 保存，仅含数字/哈希/源偏移等元数据。原书、正文、原件插图、首屏 PNG 均未加入版本控制。
