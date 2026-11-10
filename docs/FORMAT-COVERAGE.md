# 格式覆盖实测 · 2026-11-07

PDF 后续深化实测见 [PDF 深化报告](../evidence/pdf-deepening-20261107/REPORT.md)：新增跨页搜索、字符坐标入口和无文字层状态；4 类 × 2 个受控样本及本页真实 PDF 的补测结果分别列出。下文保留 #73 当时的观察值。

本批覆盖 **29 个文件 / 4 类格式**。SDK Release 源码为
`000caeef67f52498b05c437384efcd3bfdb1b5d1`（本分支开始时的 HEAD），Windows AMD64、SDK 3.42.0 / ABI 1。
通过公开 C API 真正打开、分页、绘制、查找、选择/命中，再换视口重复；不是根据解析器分支推断支持。
证据与完整逐页数据见 [formats-20261107](../evidence/formats-20261107/)。

主布局为 720×1040、28px、边距 36、行高 1.5；替代布局为 480×800、36px。
PDF/CBZ 最大边 720，另绘第一页的 2× 缩放。字体、DLL、输入文件和驱动均记录 SHA-256。
本构建启用 PDF、JPX、PDF crypto、音频基本模块；关闭 MP3/AAC、ICC、WebP/TIFF/AVIF。
精确配置在 [build.json](../evidence/formats-20261107/build.json)，ctypes 与原生结构尺寸/关键偏移核对见
[abi.json](../evidence/formats-20261107/abi.json)。

“能打开”只指 open API 成功；“页数”对固定格式指目录页数，对流式格式指完整分页数。
“首屏”给出实际像素尺寸与非白 RGBA 分量数；它证明产生画面，不是排版保真评分。
文字版 PDF 使用真实 find/select；流式文档使用 find 与布局 hit-test，验证源偏移，不是 GUI 拖动选文。
图片格区分源文件含图和 SDK 绘制/图片框，PDF 的图像存在性由独立 PyMuPDF 读取，不由非白像素反推。
无文字层的扫描图与漫画没有 OCR；空文本上的查找虽返回 OK，但没有命中，选择非空范围返回 ARGUMENT。

错误码：`0=EXR_OK`、`1=EXR_ARGUMENT`、`4=EXR_ENCODING`、`5=EXR_FORMAT`、
`10=EXR_PASSWORD`、`11=EXR_UNSUPPORTED`。驱动超时/崩溃分别记 `RUNNER_TIMEOUT` / `RUNNER_EXIT`，
与 SDK 错误分开。矩阵页码从 1 起叙述，JSON 的页索引从 0 起。

| 格式 | 样本 | 能打开 | 页数 | 首屏 | 缩放/重排 | 文字可选 | 图片 | 备注 |
|---|---|---|---|---|---|---|---|---|
| EPUB-fixed | page-blanche | 是(0) | 11 | 720×1040；非白分量 1580349 | 480×800/36px：11页(ok) | 查找0；匹配1/命中1 | 源9图；SDK图片框9 | count；固定入口5 |
| EPUB-fixed | haruko-html-jpeg | 是(0) | 14 | 720×1040；非白分量 988404 | 480×800/36px：15页(ok) | 查找0；匹配1/命中1 | 源12图；SDK图片框12 | count；固定入口5 |
| EPUB-audio | moby-dick-mo | 是(0) | 1026 | 720×1040；非白分量 1561425 | 480×800/36px：3432页(ok) | 查找0；匹配1/命中1 | 源2图；SDK图片框2 | count；固定入口5；EPUB→PCM 5；.mp4→PCM 5 |
| EPUB-audio-video | cc-shared-culture | 是(0) | 22 | 720×1040；非白分量 572383 | 480×800/36px：111页(ok) | 查找0；匹配1/命中1 | 源2图；SDK图片框3 | count；固定入口5；EPUB→PCM 5；.mp3→PCM 5 |
| EPUB-reflow | between-the-world-and-me | 是(0) | 228 | 720×1040；非白分量 1623283 | 480×800/36px：813页(ok) | 查找0；匹配1/命中1 | 源9图；SDK图片框9 | hash；固定入口5 |
| EPUB-reflow | the-house-on-mango-street | 是(0) | 181 | 720×1040；非白分量 477674 | 480×800/36px：522页(ok) | 查找0；匹配1/命中1 | 源1图；SDK图片框1 | hash；固定入口5 |
| PDF-text | pdf-text-malcolm | 是(0) | 279；参考 279 | 427×720；非白分量 914396 | 2×→854×1440；无重排 | 查找0/选择0；1区域 | 参考1页有图；SDK已绘279页 | hash |
| PDF-text | pdf-text-statistics | 不支持(5) | 0；参考 1 | 不支持(5) | 不支持(5) | 不支持(5) | 不支持(5)；参考0页有图；SDK已绘0页 | count；fixed_open:5 |
| PDF-scan | pdf-scan-malcolm | 是(0) | 20；参考 20 | 427×720；非白分量 914510 | 2×→854×1440；无重排 | 不支持；无文字层/字形(0字节)；查找0/命中0；选择1 | 参考20页有图；SDK已绘20页 | hash |
| PDF-scan | pdf-scan-upstream | 是(0) | 1；参考 1 | 不支持(11) | 不支持(11) | 不支持(11) | 不支持(11)；参考1页有图；SDK已绘0页 | count；fixed_render:11 |
| PDF-stress | sample-text | 是(0) | 4；参考 4 | 720×720；非白分量 1566 | 2×→1440×1440；无重排 | 查找0/选择0；1区域 | 参考4页有图；SDK已绘1页 | count；仅尝试前1页 |
| PDF-stress | sample | 是(0) | 5；参考 5 | 12×12；非白分量 48 | 2×→24×24；无重排 | 查找0/选择0；1区域 | 参考5页有图；SDK已绘1页 | count；仅尝试前1页 |
| PDF-encrypted | pdf-encrypted-r4 | 是(0) | 1；参考 1 | 不支持(5) | 不支持(5) | 不支持(5) | 不支持(5)；参考0页有图；SDK已绘0页 | count；无/错密码 10/10；fixed_render:5 |
| PDF-encrypted | pdf-encrypted-r6 | 不支持(5) | 0；参考 279 | 不支持(5) | 不支持(5) | 不支持(5) | 不支持(5)；参考1页有图；SDK已绘0页 | count；无/错密码 5/5；fixed_open:5 |
| CBZ | page-blanche-cbz | 是(0) | 9 | 548×720；非白分量 1133538 | 2×→1096×1440；无重排 | 不支持；无文字层/字形(0字节)；查找0/命中0；选择1 | 9图；SDK已绘9页 | hash |
| CBZ | haruko-html-jpeg-cbz | 是(0) | 12 | 517×720；非白分量 845919 | 2×→1033×1440；无重排 | 不支持；无文字层/字形(0字节)；查找0/命中0；选择1 | 12图；SDK已绘12页 | hash |
| CBZ-fixture | comic-fixture | 是(0) | 4 | 2×2；非白分量 6 | 2×→4×4；无重排 | 不支持；无文字层/字形(0字节)；查找0/命中0；选择1 | 4图；SDK已绘4页 | hash |
| TXT-utf8 | pg52323-utf8 | 是(0) | 81 | 720×1040；非白分量 193467 | 480×800/36px：135页(ok) | 查找0；匹配1/命中1 | 源无图(0) | hash；文本一致1 |
| TXT-gbk | pg52323-gbk | 不支持(4) | 0 | 不支持(4) | 不支持(4) | 不支持(4) | 源无图(0) | count；document_open:4 |
| TXT-utf8-bom | pg52323-utf8-bom | 是(0) | 81 | 720×1040；非白分量 193467 | 480×800/36px：135页(ok) | 查找0；匹配1/命中1 | 源无图(0) | hash；文本一致1 |
| TXT-utf16-bom | pg52323-utf16-bom | 是(0) | 81 | 720×1040；非白分量 193467 | 480×800/36px：135页(ok) | 查找0；匹配1/命中1 | 源无图(0) | hash；文本一致1 |
| TXT-utf8 | pg24239-utf8 | 是(0) | 25 | 720×1040；非白分量 378117 | 480×800/36px：86页(ok) | 查找0；匹配1/命中1 | 源无图(0) | hash；文本一致1 |
| TXT-gbk | pg24239-gbk | 不支持(4) | 0 | 不支持(4) | 不支持(4) | 不支持(4) | 源无图(0) | count；document_open:4 |
| TXT-utf8-bom | pg24239-utf8-bom | 是(0) | 25 | 720×1040；非白分量 378117 | 480×800/36px：86页(ok) | 查找0；匹配1/命中1 | 源无图(0) | hash；文本一致1 |
| TXT-utf16-bom | pg24239-utf16-bom | 是(0) | 25 | 720×1040；非白分量 378117 | 480×800/36px：86页(ok) | 查找0；匹配1/命中1 | 源无图(0) | hash；文本一致1 |
| PDF-text | pdf-text-syllabus-math | 不支持(5) | 0；参考 7 | 不支持(5) | 不支持(5) | 不支持(5) | 不支持(5)；参考1页有图；SDK已绘0页 | count；fixed_open:5 |
| PDF-text | pdf-text-syllabus-stat | 不支持(5) | 0；参考 7 | 不支持(5) | 不支持(5) | 不支持(5) | 不支持(5)；参考0页有图；SDK已绘0页 | count；fixed_open:5 |
| EPUB-DRM | drm-the-waste-land | 是(0) | 0 | 不支持(5) | 不支持(5) | 不支持(5) | 不支持(5)；源1图；SDK图片框0 | count；固定入口5；publication_load:5 |
| EPUB-DRM | drm-accessible-epub-3 | 是(0) | 0 | 不支持(5) | 不支持(5) | 不支持(5) | 不支持(5)；源3图；SDK图片框0 | count；固定入口5；publication_load:5 |

## 各格式支持到什么程度

| 格式/形态 | 当前实测边界 |
|---|---|
| 流式 EPUB | 两书完整排版与图片可用，文字查找/命中可用；换宽度/字号重新分页。固定配置下可做像素回归。 |
| 固定版式 EPUB | 两本 `rendition:layout=pre-paginated` 真书能经 publication/pager 读取，图片可见；固定页入口返回 FORMAT(5)。Haruko 从 14 页变成 15 页，未保持固定版式语义，只能按流式降级读取。**2026-11-10 更新（D1）**：pager 已按原生视口一页排版并统一缩放，支持 item 级 rendition、page-spread 展开与固定页 `position:absolute`；8 本扩充语料六项 6/6，见 [FIXED-LAYOUT.md](FIXED-LAYOUT.md)。本表其余数字仍为 2026-11-07 当时的测量。 |
| 含音频/视频 EPUB | Moby Dick 和 Creative Commons 样本的静态正文/图片可读。EPUB 交给 PCM 入口返回 FORMAT(5)；提取的 MP4/MP3 单独交给 PCM 入口也返回 FORMAT(5)。本构建未启用 MP3/AAC，不能把此结果推广为启用解码器后的结果；本轮未验证 SMIL 同步朗读或视频播放。 |
| 文字 PDF | 固定页绘制、2× 缩放和文本查找/选择在 Malcolm X 279 页上可用。Binomial Distribution 及两份课程 syllabus 打开即 FORMAT(5)，不能概括为任意文字 PDF 均可读。 |
| 扫描 PDF | Malcolm X 的 20 页图像版可完整绘制和缩放，文字字节/区域为 0，无法搜索选中。另一真实上游图像 PDF 能打开、列出 1 页，但绘制 UNSUPPORTED(11)；不是所有扫描 PDF 都可读。 |
| 加密 PDF | AES-128/R4 派生件：无/错密码 PASSWORD(10)，正确密码可打开，但绘制 FORMAT(5)。AES-256/R6 派生件：无/错/正确密码均在打开时 FORMAT(5)。这里只确认 R4 的认证分支，没有一个本批加密样本实现完整阅读；不据此否定其他 Standard R2–R6 输入。 |
| CBZ | 两本真实图文出版物的原图转封装及现有 fixture，分别 9/12/4 页，完整绘制、2× 缩放可用；只能固定页，图片内文字不可搜索/选择。本批是 PNG/JPEG，不覆盖扩展图像或动画。 |
| UTF-8 TXT | 两段真实中文原文可排版，解码后规范化文本哈希与源文本相同，文字查找/命中可用；改布局重新分页。 |
| 带 BOM TXT | UTF-8 BOM、UTF-16 BOM 各两份，正文哈希与无 BOM UTF-8 一致，可排版/查找/命中。 |
| GBK TXT | 同两段中文严格转码，没有替换字符；两份均在 document_open 返回 ENCODING(4)，本构建不能直接读 GBK。 |
| DRM EPUB | EDRLab 官方公开 LCP 测试书 The Waste Land、Accessible EPUB 3，保留加密资源并附官方测试 license。两份 publication_open 均成功，但 publication_load 均 FORMAT(5)，0 页，不能阅读正文。本批未建立 LCP 阅读能力；不将结果推广为其他 DRM 方案的实测结论。 |

`Sample-Text.pdf` / `Sample.pdf` 是额外压力控制，不充当正常真书样本。
它们能打开，分别列出 4/5 页，首屏及首屏 2× 可绘制；完整逐页探测分别在
**第 2/3 页**返回 FORMAT(5)，此前成功绘制 1/2 页。
完整探测见 [stress-full-pages.json](../evidence/formats-20261107/stress-full-pages.json)。
正式基线对两文件只尝试第一页，并记录 `max_render_pages=1`；不能把它们的 `status=ok` 解读为整份 PDF 通过。

## 样本来源与计数

29 行 = EPUB 8（流式 2、固定版式 2、多媒体 2、DRM 2）+ PDF 10
（文字 4、扫描 2、加密 2、压力控制 2）+ CBZ 3 + TXT 8
（UTF-8 / GBK / UTF-8 BOM / UTF-16 BOM 各 2）。

样本清单为 [corpus-formats.json](../tools/regress/corpus-formats.json)：

- EPUB 流式两书来自已有 19 本语料；固定版式和多媒体样本来自 IDPF/DAISY 的
  [EPUB 3 Samples 固定 release](https://github.com/IDPF/epub3-samples/releases/tag/20230704)。
- DRM 为 [EDRLab 官方 LCP 测试书](https://www.edrlab.org/readium-lcp/testing-readium-lcp-compliant-devices/)。
  下载官方加密出版物和配套公开测试 license，将 license 附入 `META-INF/license.lcpl`，加密资源字节未改；
  清单记录出版物原件哈希、license 哈希、URL 和转封装说明。独立检查确认 AES 加密声明、加密资源数量及内置 license。
- 文字 PDF 是本地实际书籍、课程材料及两份课程大纲；扫描图像 PDF 是既有真实书籍的图像版和已有 pdf.js 上游语料。
- 加密样本是前述真实文字 PDF 经 PyMuPDF 1.28.2 另存为 AES-128 / AES-256 的派生文件；保留内容，PDF 结构会重写。
  它们不是商业加密出版物。密码通过 `EXR_FORMAT_PDF_PASSWORD` 提供。
- 两本真实图文 EPUB 的 PNG/JPEG 原字节转封装为 CBZ，未另画测试图；不是独立获取的发行版 CBZ。
  `comic.cbz` 作为第 3 个合成控制，不计作第 2 本真实图文内容。
- TXT 取自 Gutenberg [唐诗三百首](https://www.gutenberg.org/ebooks/52323) 和
  [醒世恒言](https://www.gutenberg.org/ebooks/24239) 的各 12,000 字符连续原文，严格转码为四种编码。
  清单记录原件哈希、连续区间、编码、规范化文本哈希，不以八个编码变体充当八本独立作品。

样本及首屏 PNG 保存在库外；仓库只提交元数据、源/正文/像素哈希与日志。
[source-inspection.json](../evidence/formats-20261107/source-inspection.json) 独立核对
真实扫描件的零文字层、PDF 页数/含图页数、EPUB 固定版式声明、音视频成员和 TXT 中文/编码。
加密另存具有随机性；复现相同源哈希需要保留库外原件，重新生成时应审阅新清单，不能静默替换旧输入。

## 回归政策与复跑

**baseline-formats.json：29 个样本，13 个全页哈希样本 / 1,051 页，16 个观察样本。**
两轮 29 样本对照：**0 页哈希变化、0 个状态/能力差异**。记录的页数合计 2,135，
其中包含失败样本能列出的页目录，不能解读为 2,135 页均绘制通过。
19 个样本完成声明的绘制范围，其中两份 Sample PDF 只绘第一页；另 10 个样本记录真实失败。
见 [verification.json](../evidence/formats-20261107/verification.json) 和
[idempotence.diff.json](../evidence/formats-20261107/idempotence.diff.json)。

哈希清单：两本流式 EPUB（409 页）、Malcolm X 文字/扫描 PDF（299 页）、三份 CBZ（25 页）、
六份可解码 TXT（318 页），合计 13 个 / 1,051 页。
观察清单：固定 EPUB 2、多媒体 EPUB 2、DRM EPUB 2、失败文字 PDF 3、失败扫描 PDF 1、
加密 PDF 2、Sample PDF 2、GBK TXT 2，合计 16 个。

哈希模式对所有页面的可见 RGBA 行字节计算 SHA-256，排除行 padding；对照还检查尺寸、源哈希、状态、页数、字形与能力探测。
`count` 模式不存像素哈希：记录页数和能力观察，页数/首屏等观察变化不使对照失败；但源文件、政策、打开/失败状态及错误码变化仍必须审阅。
它不是“成功支持”的标记。

- 固定版式 EPUB 页数受视口影响（Haruko 14→15），不进像素哈希回归。
- 含音频 EPUB 只验证静态降级，Moby Dick 1026→3432 页、Shared Culture 22→111 页；保留页数，避免将静态像素相同当作多媒体通过。
- 失败的 PDF/GBK/DRM EPUB 保留错误与能取得的页目录；Sample PDF 只保留页目录/首屏观察，均不进哈希。
- 流式 EPUB/TXT 的页数也受布局影响；它们在冻结字体和布局的条件下可做哈希回归，不是跨视口的固定页数。
- 成功的 PDF/CBZ 本批 A/B 布局页目录不变；缩放只改变位图尺寸。

```powershell
$formatBuild = 'C:/Users/Oscar/Documents/Codex/formats-build-20261107'
$formatFont = 'C:/Users/Oscar/Documents/Codex/EXReader-Windows-delivery-20261104/payload/Reader.otf'
$env:EXR_FORMAT_PDF_PASSWORD = 'format-test' # 本批自行加密测试副本的测试口令
python -X utf8 tools/regress/run_formats.py --manifest tools/regress/corpus-formats.json --dll "$formatBuild/libexreader.dll" --font $formatFont --layout tools/regress/layout.json --source-revision 000caeef67f52498b05c437384efcd3bfdb1b5d1 --timeout 600 --output evidence/formats-20261107/repeat-formats.json --baseline evidence/formats-20261107/baseline-formats.json
python -X utf8 tools/regress/check_formats.py --baseline evidence/formats-20261107/baseline-formats.json --repeat evidence/formats-20261107/repeat-formats.json --output evidence/formats-20261107/verification.json
python -X utf8 tools/regress/inspect_formats.py --manifest tools/regress/corpus-formats.json --output evidence/formats-20261107/source-inspection.json --run evidence/formats-20261107/baseline-formats.json --matrix evidence/formats-20261107/matrix.md
ctest --test-dir $formatBuild --output-on-failure --parallel 2
```

`run_formats.py` 只依赖 Python 标准库，复用旧 SDK 包装和像素契约；每个样本由有超时的独立子进程运行。
`prepare_formats.py --help` 提供下载、编码/容器派生入口；`inspect_formats.py` 的独立 PDF 参照额外需要 PyMuPDF。
改机器时修改外部样本路径和 DLL/字体路径，保留源 SHA-256；相对路径按清单目录解析。
`--preview-dir` 可生成库外首屏，用于人工查看；仓库不保留出版物截图。

本轮首个 27 样本运行中 Moby Dick 的替代布局触及 240 秒限时；完整主布局 1,026 页已生成。
随后用相同 DLL/驱动/布局/输入单独重跑该书（600 秒限时），完整得到替代布局 3,432 页；
第二轮 27 样本不需重试。两份 DRM 在之后分别独立运行两轮。
`merge_format_runs.py` 只组装实际运行结果，校验 DLL、驱动、字体、布局、源码和输入哈希/政策一致，
拒绝缺样本或混合条件，保留每个原始运行文件的哈希和样本清单。
最终基线的 `assembled_from` 指向 `formats-initial.json`、`retry-moby.json`、`drm-formats.json`；
独立复跑指向 `formats-repeat-27.json`、`drm-repeat.json`。原超时和重试证据均保留。

## 19 本 EPUB 与已有基线

原 [baseline.json](../evidence/realbooks-baseline-20261107/baseline.json)、旧 `run_realbooks.py`、
`corpus.json`、`layout.json` 均未改动。
用原 `c665d1cb…` DLL（SHA-256 与历史基线完全相同）复跑：
**19/19 本、11,128 页、8,694,817 字形、0 页哈希变化、页数变化 0 本**。
见 [epub-historical.diff.json](../evidence/formats-20261107/epub-historical.diff.json)。

任务起点 `000caeef…` 相对历史源码已有排版修改，不能冒称它与历史基线一致：
**19/19 本、11,083 页、8,660,230 字形，14 本有像素变化、5 本页数变化，共 5,446 个公共页哈希变化**；
另外少了 45 页，比较器另记 removed_pages。
见 [epub-current.diff.json](../evidence/formats-20261107/epub-current.diff.json)。
本次没有改引擎，也没有覆盖历史基线。当前源码的这些差异作为已有漂移暴露，后续应由排版变更独立审阅。

同一当前 DLL 在本任务前后各跑完整 19 本：**11,083 页、页数变化 0 本、0 页哈希变化**。
见 [epub-after.diff.json](../evidence/formats-20261107/epub-after.diff.json)。
因此本次格式覆盖扩展没有造成 EPUB 排版变化；历史基线与后续源码之间的已有漂移仍需独立处理。

## README / 支持矩阵核对

行号绑定本次受测的 `000caeef…`：

1. **支持矩阵边界遗漏**：[SUPPORT_MATRIX.md:38](SUPPORT_MATRIX.md#输入格式) 的 TXT “支持 / 编码探测”
   没有写明编码范围；两份中文 GBK 实测均为 ENCODING(4)。应明确 UTF-8、带 BOM UTF-16 等已验证编码，不把“探测”读成 GBK 可用。
   README **第 91 行**的“TXT（UTF-8、带 BOM 的 UTF-16）”与本批结果一致。
2. **支持矩阵边界遗漏**：同表 **第 41 行** EPUB 2/3 “支持”，列有 CSS 子集，却没有固定版式和多媒体降级限制。
   本批两本声明 `pre-paginated` 的书经流式路径读取，其中一书页数随视口变化；音视频包只有静态内容得到验收。
   这不是对 EPUB 普遍不可读的判断，应在支持项旁补足形态边界。
3. **README 第 150 行的事实表述不符**：“所有构建、测试及证据汇总在 GitHub Actions 执行。”
   历史真书基线和本批 29 格式样本、176 项 ctest 均有本地运行证据，该句不适用于这些验证。

README 关于 PDF 自有固定页、可选密码学、TXT UTF 编码及可选音频组件的说明与本批观察没有直接冲突。
按任务边界，本次只在此指出具体位置，不修改 README 或原支持矩阵。

## ctest 与变更边界

本地相同源码、crypto 开启的完整构建：**176/176 通过，0 失败**，耗时 363.18 秒。
见 [ctest.log](../evidence/formats-20261107/ctest.log)。这是本配置的实际当前测试数，不把历史 169 项当作固定常数。
没有调用 CI、取消 workflow 或修改 workflow。
变更仅增加 `tools/regress/`、本文和 `evidence/formats-20261107/`；没有修改 `src/`、`include/` 或宿主示例。
