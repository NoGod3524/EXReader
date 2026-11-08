# PDF 深化实测 · 2026-11-08

起点 `7dc3ca0c3d0277f50949cffc95c0e9f9fa1de408`，Windows AMD64 / MinGW Release，PDF crypto / JPX 开启。
本轮只增加固定页文字入口、跨页搜索和字符命中，EPUB 排版源码未改。

## A：4 类 × 2 样本

下表八个文件为**原创受控样本**：文字含 WinAnsi 重音字符，图像页为无文字操作符的棋盘图，混合文件交替放置文字和图像页。
密码文件由 text-a 经 pypdf AES-128 派生；权限文件由 text-b 经 AES-256 派生，空 user 密码，`/P=4`。
全部 PDF 留在库外；生成器 [pdf_deepening_inputs.py](../../tests/pdf_deepening_inputs.py) 入库，输入哈希和逐页实测在 [matrix.json](matrix.json)。
字符数按 Unicode scalar 计数；页数是固定页目录。搜索列是所测 query 的首次命中数（0 或 1），全局位置与页内位置在 JSON。
可选页列是在该页实际调用 select 并得到区域的页数；未模拟宿主 GUI 拖动。

| 类别 | 样本 | 打开 | 页数 | Unicode字符 | 搜索命中 / 状态 | 可选页 | 正确渲染页 | 错误码 |
|---|---|---:|---:|---:|---|---:|---:|---|
| text | text-a | 0 | 3 | 63 | 1 / 0 | 3/3 | 3/3 | 0 |
| text | text-b | 0 | 2 | 34 | 1 / 0 | 2/2 | 2/2 | 0 |
| scan | scan-a | 0 | 10 | 0 | 0 / 12 | 0/10 | 10/10 | 0,12 |
| scan | scan-b | 0 | 2 | 0 | 0 / 12 | 0/2 | 2/2 | 0,12 |
| mixed | mixed-a | 0 | 4 | 9 | 1 / 0 | 2/4 | 4/4 | 0,12 |
| mixed | mixed-b | 0 | 3 | 5 | 1 / 0 | 1/3 | 3/3 | 0,12 |
| encrypted | encrypted-password | 0 | 3 | 63 | 1 / 0 | 3/3 | 3/3 | 0,10 |
| encrypted | encrypted-permissions | 0 | 2 | 34 | 1 / 0 | 2/2 | 2/2 | 0 |

`0=EXR_OK`，`10=EXR_PASSWORD`，`12=EXR_NO_TEXT_LAYER`，`13=EXR_NO_TEXT_AT_POINT`。
有密码样本无密码 / 错密码均为 10；`reader` 密码打开为 0。权限样本空密码打开为 0，返回 security revision=6、permissions=4；操作权限由宿主依据返回位决定。
扫描页的文字、坐标、全书搜索都明确返回 12，文字输出指针为空；混合文档搜索跳过无文字页，仍能找到后续文字。

29/29 页逐页与 PyMuPDF 1.28.2 核对：文字与独立提取的文本一致；尺寸相同，RGB 平均绝对误差最大 **0.503/255**，非白像素数量比处于 (0.5,2)，墨迹边界误差 ≤2px。
这些条件一起判定受控页面渲染正确，避免空白页凭白背景通过。另目视核验了八个首屏的 SDK / 参考图对照；预览仅存 build/，不入库。

## 真实 PDF 补测

沿用 #73 的八个 PDF，全部可打开文件都逐页提取、选择、渲染，完整原始值见 [existing-pdfs.json](existing-pdfs.json)。
本表的渲染列是实际 API 错误码；真实出版物未做逐页参考像素保真评分。搜索统一使用 `the`。

| #73 样本 | 打开 / 无密码 | 页数 | 字符数 | 无文字页 | 搜索命中 / 状态 | 可选页 | 渲染状态 |
|---|---|---:|---:|---:|---|---:|---|
| pdf-text-malcolm | 0 / 0 | 279 | 1084554 | 1 | 1 / 0 | 278 | 0 |
| pdf-text-statistics | 5 / 5 | — | — | — | — / — | — | 未到达 |
| pdf-scan-malcolm | 0 / 0 | 20 | 0 | 20 | 0 / 12 | 0 | 0 |
| pdf-scan-upstream | 0 / 0 | 1 | 0 | 1 | 0 / 12 | 0 | 11 |
| pdf-encrypted-r4 | 0 / 10 | 1 | 229 | 0 | 0 / 0 | 1 | 5 |
| pdf-encrypted-r6 | 5 / 5 | — | — | — | — / — | — | 未到达 |
| pdf-text-syllabus-math | 5 / 5 | — | — | — | — / — | — | 未到达 |
| pdf-text-syllabus-stat | 5 / 5 | — | — | — | — / — | — | 未到达 |

Malcolm X 文字版 279 页中 278 页有文字、1 页无文字，共 1,084,554 字符；扫描版 20/20 页明确返回 12，20/20 页绘制成功。
上游扫描件的文字状态为 12，绘制为 UNSUPPORTED(11)。旧 R4 派生件可认证、提取 229 字符并选择，绘制仍为 FORMAT(5)。
旧 R6 派生件打开报 “Invalid PDF cross-reference table or trailer”；统计讲义及两份 syllabus 报 “Invalid PDF cross-reference stream”，均为 FORMAT(5)。本轮未修改交叉引用解析或这些输入。

## B：公开 API 与实现

声明在 [document.h](../../include/exr/document.h)，实现集中在 [fixed.c](../../src/fixed.c)。

```c
exr_document_search(fixed, offset, needle, control, &match, &error);
exr_fixed_page_text(fixed, page, control, &text, &error);
exr_fixed_character_at(fixed, page, x, y, control, &region, &scalar, &error);
```

- `exr_document_search` 的 document 是 `exr_fixed_document*`。offset 为按页序连接的 UTF-8 字节偏移（含起点）；命中返回全局 `[start,end)` 和起止页/页内字节位置，页索引从 0 起。下一次可从 `match.end` 继续；要找重叠命中则从 start 后一个 scalar 继续。
- 页间不插入空白或分隔符；保留 PDF content provider 的顺序，不推测阅读顺序、词间空格或断行。KMP 逐页扫描，内存为一个页快照、query 前缀表和页偏移表；query 上限 1 MiB，支持取消与错误清理。普通未命中是 OK + 全部字段 SIZE_MAX；整本文字为空则为 12。
- `exr_fixed_page_text` 对无文字页返回 12 和 NULL，缺失 provider 返回 UNSUPPORTED(11)。原 `exr_fixed_load_text` 保持兼容；宿主使用新入口取得明确状态。
- `exr_fixed_character_at` 对原生 PDF 坐标做可见文字 quad 的精确包含判断。成功返回 Unicode scalar、UTF-8 范围及 quad；有文字但点在空白处返回 13。屏幕坐标先用 viewport 逆变换。ligature 保留完整映射范围/单个 quad，并返回映射的第一个 scalar；不编造字母拆分几何。
- 选区沿用 `exr_fixed_text_select` 与 `exr_fixed_text_regions`，可由字节范围取实际文字坐标。密码沿用 `exr_fixed_open_options.pdf_password`；无/错密码为 PASSWORD(10)，未编译密码模块时为 UNSUPPORTED(11)。无 OCR、无密码破解。

新枚举追加在旧值之后，新结构和符号均为加法，ABI epoch 仍为 1。Windows 公共符号由现有头扫描自动导出，无需改导出脚本。

## 七项验收

| 项目 | 本轮数字 | 证据 |
|---|---|---|
| 1. 能力矩阵 | 4×2=8 个受控 PDF，29/29 页；另补测 8 个真实 PDF | matrix.json / existing-pdfs.json |
| 2. 搜索 | 10/10 词位置正确；跨页 epsilonzeta `[23,34)`，(页0,23)→(页1,4)；另跨扫描页命中一例 | targeted-tests.txt |
| 3. 字符坐标 | 20/20 预置点，100%；空白点状态13；另过 ligature/Form/竖排/非BMP | targeted-tests.txt |
| 4. 扫描 | 10/10 页文字和坐标返回12；真实扫描另20/20页返回12 | targeted-tests.txt / existing-pdfs.json |
| 5. 加密 | R4/R6 的有密码/空密码4件通过；矩阵 AES-128无/错密码10、有密码0，AES-256权限件空密码0 | targeted-tests.txt / matrix.json |
| 6. EPUB | 19/19 本；11,296页、8,648,640字形；页数变化0本、哈希变化0页 | epub-before.json / epub-after.json / epub-after.diff.json |
| 7. ctest | 本配置起点198项，新增5组，最终203/203 | ctest.txt |

任务书中的 191 为先前基线；相同起点源码在本次完整配置中实际注册198项。五组检查数分别为43 / 85 / 64 / 26 / 17。
EPUB 比较使用本轮编译的改动前 DLL 与改动后 DLL、同一字体和布局，不拿历史排版漂移替代本轮对照。
严格警告构建 `-Wall -Wextra -Wpedantic -Werror` 通过；层依赖检查110对象、1249符号引用、0逆向引用、0逆向include，见 [layers.txt](layers.txt)。

## 复跑

```powershell
python tests/pdf_deepening_inputs.py --output ../pdf-deepening-new-samples
python tests/measure_pdf_deepening.py --manifest ../pdf-deepening-new-samples/manifest.json --dll build/pdf/libexreader.dll --font C:/Windows/Fonts/cour.ttf --output build/matrix.json --previews build/previews
python tests/measure_existing_pdfs.py --manifest tools/regress/corpus-formats.json --dll build/pdf/libexreader.dll --font C:/Users/Oscar/Documents/Codex/EXReader-Windows-delivery-20261104/payload/Reader.otf --output build/existing-pdfs.json
ctest --test-dir build/pdf -R pdf-deepening -V
ctest --test-dir build/pdf --output-on-failure --parallel 3
```

首条命令生成新输入；加密含随机盐/IV，须用新 manifest 的哈希，不能套用本次旧哈希。原始八件及对应 manifest 位于库外 `../pdf-deepening-samples-20261107/`。
完整构建配置、二进制和实现/驱动 SHA-256 在 [provenance.json](provenance.json)；EPUB 复跑驱动、清单和布局沿用 tools/regress/。
受保护树登记已追加。未改 examples/ 或 .github/，未取消 workflow run；PDF 文件及预览图不入库。
