# SDK 格式能力矩阵

本表对应当前源码的公开 C SDK，按**格式及影响调用路径的编码、容器或保护 profile**计 41 行；不是 41 种文件扩展名，也不是一次执行了 41 种真实出版物验收。接口见 [API.md](API.md)，宿主流程见 [INTEGRATION.md](INTEGRATION.md)。

**支持**表示该列有实现与对应回归，范围以备注为准；**部分**表示只有列出的子集；**不支持**表示没有该能力或入口明确拒绝。流式“排版”是重新分页，PDF/CBZ“固定绘制”只缩放原页面。搜索指 SDK 正文搜索；标注区分宿主书库保存的选择器与写回原文件。未加密格式的 DRM 列写“不支持”，不把能读明文算 DRM 支持。

默认构建启用 PDF、PDF_EDIT、LIBRARY、TEXT_INDEX、MP3、LCP、PDF_CRYPTO、JPX、WebP/TIFF/AVIF；AAC 默认关闭。可选功能关闭后，以本表的开关说明为准；组件整体关闭时其实现不在组件包内。S4 示例编译配置关闭可选图像解码器和 JPX，仅验证示例的编译/链接，不据此宣称对应 codec 已运行通过。开关来源：[CMakeLists.txt](../CMakeLists.txt)。

| 格式 / profile | 解析 | 排版 / 固定绘制 | 搜索 | 标注 | DRM | 边界与证据 |
|---|---|---|---|---|---|---|
| 01 TXT UTF-8（可带 BOM） | 支持 | 支持：流式 | 支持：规范化 UTF-8 | 支持：TextQuote/书库 | 不支持 | 段落去首尾空白，投影段间 LF；有界扫描单段≤64 KiB。[formats.c](../src/formats.c)、[test_text.c](../tests/test_text.c)、[test_source.c](../tests/test_source.c) |
| 02 TXT UTF-16 LE/BE（BOM） | 支持 | 支持：流式 | 支持：转成 UTF-8 后查找 | 支持：规范化文本锚点 | 不支持 | 需要 BOM；拒绝未配对代理项，偏移不是原始 UTF-16 文件偏移。[formats.c](../src/formats.c)、[test_source.c](../tests/test_source.c) |
| 03 TXT GBK/GB18030 | 不支持 | 不支持 | 不支持 | 不支持 | 不支持 | 先由宿主转 UTF-8；真实 GBK 样本返回 ENCODING。[FORMAT-COVERAGE.md](FORMAT-COVERAGE.md) |
| 04 良构 XHTML / 静态 HTML | 部分 | 部分：CSS/布局子集 | 支持：正文投影 | 支持：TextQuote/书库 | 不支持 | 结构化路径要求良构；不是完整浏览器。[test_html_raw.c](../tests/test_html_raw.c)、[test_xml_input.c](../tests/test_xml_input.c)、[SUPPORT_MATRIX.md](SUPPORT_MATRIX.md#epub--流式文档排版) |
| 05 HTML5 错误恢复 / JavaScript 页面 | 部分：旧入口可提取静态文字 | 不支持动态页面排版 | 部分：仅提取出的静态文字 | 部分：仅静态投影 | 不支持 | 不执行脚本，不构建浏览器动态 DOM，不提供 HTML5 纠错排版。[formats.c](../src/formats.c)、[test_html_raw.c](../tests/test_html_raw.c) |
| 06 FB2 XML | 支持 | 部分：受支持的段落/样式/图片 | 支持：正文 | 支持：TextQuote/书库 | 不支持 | 支持命名空间、注释与内嵌图片；非完整印刷排版保真。[fb2.c](../src/fb2.c)、[test_fb2.c](../tests/test_fb2.c) |
| 07 ZIP 封装 FB2（FBZ） | 支持 | 部分：按 FB2 重排 | 支持：解包后正文 | 支持：TextQuote/书库 | 不支持 | ZIP 是 FB2 输入容器，不是任意多文档合集阅读器。[fb2.c](../src/fb2.c)、[test_fb2.c](../tests/test_fb2.c) |
| 08 DOCX（OOXML） | 部分 | 部分：段落/样式/表格/图片 | 支持：正文投影 | 支持：外部 TextQuote；不支持 Word 批注写回 | 不支持 | 不复现全部 Word 打印版面；不支持加密 Office 包。[docx.c](../src/docx.c)、[test_docx.c](../tests/test_docx.c) |
| 09 RTF | 部分 | 部分：表格/列表/脚注/字体回退 | 支持：正文投影 | 支持：外部 TextQuote；不支持 RTF 批注写回 | 不支持 | 受控语法子集，非任意 Word RTF 往返。[test_rtf.c](../tests/test_rtf.c)、[test_rtf_table.c](../tests/test_rtf_table.c)、[test_rtf_note.c](../tests/test_rtf_note.c) |
| 10 MOBI 7 / PalmDOC | 部分 | 部分：转换后的流式结构 | 支持：正文 | 支持：外部 TextQuote | 不支持 Kindle DRM | PalmDOC/Huff 解码；不支持 MOBI 原格式写回。[formats.c](../src/formats.c)、[test_mobi.c](../tests/test_mobi.c) |
| 11 KF8（AZW3 容器） | 部分 | 部分：KF8 结构/资源与布局子集 | 支持：正文 | 支持：外部 TextQuote | 不支持 Kindle DRM | AZW3 后缀不表示全部 Amazon 格式兼容；拒绝受保护内容。[kf8.c](../src/kf8.c)、[test_kf8.c](../tests/test_kf8.c) |
| 12 Kindle KFX | 不支持 | 不支持 | 不支持 | 不支持 | 不支持 | 公开格式枚举与解析分派没有 KFX reader。[document.h](../include/exr/document.h)、[formats.c](../src/formats.c) |
| 13 EPUB 2 流式 | 支持 | 部分：CSS 子集，支持分页 | 支持：跨章正文 | 支持：TextQuote/CFI/书库 | 不支持通用 DRM | OPF/spine/NCX、资源与字体；严格 OCF 验证另调 epub_validate。[test_epub_strict.c](../tests/test_epub_strict.c)、[test_navigation.c](../tests/test_navigation.c)、[test_cfi.c](../tests/test_cfi.c) |
| 14 EPUB 3 流式 | 支持 | 部分：CSS 子集，支持分页 | 支持：跨章正文 | 支持：TextQuote/CFI/书库 | 不支持通用 DRM | nav、spine、章加载与有界阅读；不执行脚本。[test_chapter_reader.c](../tests/test_chapter_reader.c)、[test_document_search.c](../tests/test_document_search.c) |
| 15 EPUB 3 pre-paginated | 部分：可读静态资源 | 部分：走流式路径；不支持原固定版面语义 | 部分：能提取的正文 | 部分：流式锚点 | 不支持通用 DRM | 真实样本页数会随视口改变，不能按 PDF/CBZ 固定页承诺。[FORMAT-COVERAGE.md](FORMAT-COVERAGE.md) |
| 16 EPUB 3 音视频 / Media Overlays | 部分：静态正文与资源 | 部分：静态降级；不支持自动多媒体播放 | 部分：静态正文 | 部分：静态正文锚点 | 不支持通用 DRM | 音频 API 需宿主提供时间线/同步数据，未自动将 EPUB 媒体绑定到播放器。[FORMAT-COVERAGE.md](FORMAT-COVERAGE.md)、[audio.h](../include/exr/audio.h) |
| 17 EPUB Readium LCP Basic Profile 1.0 | 部分：启用 LCP 并提供口令 | 部分：解密后按 EPUB 子集 | 支持：成功解密后的正文 | 支持：成功解密后的外部锚点；不支持加密包写回 | 部分：只读资源解码 | 默认 EXR_ENABLE_LCP=ON；不验签/证书链，不支持 LSD 撤销、登记、续借或阅读中回收。关闭时 DRM_UNSUPPORTED。[DRM.md](DRM.md)、[test_lcp.c](../tests/test_lcp.c) |
| 18 EPUB LCP 生产 profile 1.0 / 2.x | 不支持受保护正文 | 不支持 | 不支持 | 不支持 | 不支持 | 非 Basic profile 返回 DRM_UNSUPPORTED，不能用 Basic 解码器冒充认证客户端。[DRM.md](DRM.md)、[test_lcp.c](../tests/test_lcp.c) |
| 19 EPUB Adobe ADEPT | 不支持受保护正文 | 不支持 | 不支持 | 不支持 | 不支持 | 无 ADEPT 解密/设备激活；rights.xml 或不支持算法明确拒绝。[DRM.md](DRM.md)、[test_lcp.c](../tests/test_lcp.c) |
| 20 PDF 含可提取文字 | 部分 | 部分：固定绘制；不支持流式重排 | 支持：文字层/跨页 | 部分：固定坐标与支持的 PDF 标注类型 | 不支持通用 DRM | 支持的文字/字体/图形子集；真实语料仍有打开或后续页失败。[test_pdf_deepening.c](../tests/test_pdf_deepening.c)、[FORMAT-COVERAGE.md](FORMAT-COVERAGE.md) |
| 21 PDF 无文字层扫描件 | 部分 | 部分：支持的图像可固定绘制 | 不支持：默认 SDK 无 OCR 正文 | 部分：固定页坐标笔记；不支持基于不存在文字层的选文 | 不支持通用 DRM | 可选 OCR 适配器不进入默认 SDK，未接通搜索/标注闭环。[test_pdf_deepening.c](../tests/test_pdf_deepening.c)、[SUPPORT_MATRIX.md](SUPPORT_MATRIX.md#pdf-阅读与绘制) |
| 22 PDF Standard Security R2–R6 | 部分：正确口令及密码学开关 | 部分：解密后仍受绘制子集限制 | 部分：成功解密且含文字层 | 部分：外部笔记；不支持加密 PDF 增量写回 | 部分：RC4/AES Standard | EXR_ENABLE_PDF_CRYPTO=ON；查询 /P 权限供宿主决策，SDK 不把其视为安全边界。认证成功不保证整书渲染。[pdf.h](../include/exr/pdf.h)、[test_pdf_crypto.c](../tests/test_pdf_crypto.c)、[FORMAT-COVERAGE.md](FORMAT-COVERAGE.md) |
| 23 PDF PubSec / 证书 / EFOpen | 不支持受保护正文 | 不支持 | 不支持 | 不支持 | 不支持 | 不支持证书安全处理器和 EFOpen；不是缺口令重试可解决。[test_pdf_crypto.c](../tests/test_pdf_crypto.c)、[SUPPORT_MATRIX.md](SUPPORT_MATRIX.md#pdf-阅读与绘制) |
| 24 PDF AcroForm（无加密） | 部分：字段树快照 | 部分：受支持 widget 外观 | 部分：页面文字，不提供字段全文搜索接口 | 部分：Tx/checkbox/radio/Ch 值及外观增量写回 | 不支持 | 不支持 XFA、JS/actions、签名写入、password/multiline/comb 等字段编辑；不是安全 redaction。[pdf_edit.h](../include/exr/pdf_edit.h)、[test_pdf_form.c](../tests/test_pdf_form.c) |
| 25 CBZ PNG/JPEG/BMP | 支持 | 支持：图像固定页 | 不支持图片内正文 | 支持：外部页 ID/坐标笔记；不支持改写 CBZ | 不支持 | 自然排序与 ComicInfo；无 OCR。图像尺寸/展开字节受预算限制。[test_cbz.c](../tests/test_cbz.c)、[test_cbz_formats.c](../tests/test_cbz_formats.c) |
| 26 CBZ GIF 动画 | 支持 | 支持：按帧展开固定页 | 不支持图片内正文 | 支持：外部帧页笔记 | 不支持 | 非定时动画播放器；单图≤4096 帧、整包≤10000 页。[image_formats.c](../src/image_formats.c)、[test_cbz_formats.c](../tests/test_cbz_formats.c) |
| 27 CBZ WebP（含动画） | 支持：需 WebP 开关 | 支持：按帧固定绘制 | 不支持图片内正文 | 支持：外部帧页笔记 | 不支持 | EXR_ENABLE_IMAGE_WEBP 默认 ON；关闭为 UNSUPPORTED。[image_formats.c](../src/image_formats.c)、[test_image_formats.c](../tests/test_image_formats.c) |
| 28 CBZ TIFF 多目录 | 部分：受支持 TIFF 编码 | 支持：目录展开固定页 | 不支持图片内正文 | 支持：外部目录页笔记 | 不支持 | EXR_ENABLE_IMAGE_TIFF 默认 ON；受固定 codec 子集/预算约束，关闭为 UNSUPPORTED。[image_formats.c](../src/image_formats.c)、[test_image_formats.c](../tests/test_image_formats.c) |
| 29 CBZ AVIF（含多帧） | 部分：受支持 AVIF profile | 支持：按帧固定绘制 | 不支持图片内正文 | 支持：外部帧页笔记 | 不支持 | EXR_ENABLE_IMAGE_AVIF 默认 ON；关闭为 UNSUPPORTED，不能保证全部 AV1/HEIF 变体。[image_formats.c](../src/image_formats.c)、[test_image_formats.c](../tests/test_image_formats.c) |
| 30 CBR / RAR 漫画 | 不支持 | 不支持 | 不支持 | 不支持 | 不支持 | 没有 RAR reader；改扩展名不构成支持。[pdf_document.c](../src/pdf_document.c)、[document.h](../include/exr/document.h) |
| 31 7Z Copy/LZMA/LZMA2/Delta | 支持：容器清单/解包 | 不支持：容器不生成页面 | 不支持容器正文 | 不支持容器锚点 | 不支持 | 新实验归档 API；支持固实块/压缩头，不自动作为 CB7 或图书打开；宿主可另将成员送入 reader。[formats.h](../include/exr/formats.h)、[test_sevenz.c](../tests/test_sevenz.c) |
| 32 7Z 加密 / 多输入编码器 | 不支持 | 不支持 | 不支持 | 不支持 | 不支持 | 加密、多输入编码器、外部名称/文件夹表、anti-items 返回 UNSUPPORTED。[formats.h](../include/exr/formats.h)、[test_sevenz.c](../tests/test_sevenz.c) |
| 33 RIFF/WAVE PCM | 支持：整数/浮点 PCM | 不支持页面；支持 PCM 解码 | 不支持音频正文 | 部分：宿主时间线书签 | 不支持 | 随机帧读取；不表示支持所有 WAVE 压缩 codec。[audio.h](../include/exr/audio.h)、[test_wave.c](../tests/test_wave.c)、[test_audio_library.c](../tests/test_audio_library.c) |
| 34 原始 FLAC | 支持 | 不支持页面；支持 PCM 解码 | 不支持音频正文 | 部分：宿主时间线书签 | 不支持 | 检查逐帧 CRC8/CRC16；不校验全流 MD5；未知时长可到 EOF 才确定。[test_flac.c](../tests/test_flac.c)、[audio.h](../include/exr/audio.h) |
| 35 MP3 Layer III | 部分：普通码率 MPEG-1/2/2.5 | 不支持页面；支持启用后的 PCM 解码 | 不支持音频正文 | 部分：宿主时间线书签 | 不支持 | EXR_ENABLE_MP3 默认 ON；不支持 free-format；关闭时 available=0、open=FORMAT。[test_mp3.c](../tests/test_mp3.c)、[audio.h](../include/exr/audio.h) |
| 36 ADTS AAC | 部分：可选 FAAD2 | 不支持页面；启用后支持 PCM 解码 | 不支持音频正文 | 部分：宿主时间线书签 | 不支持 | EXR_ENABLE_AAC 默认 OFF；单 raw block、声道配置 1..7；不支持 ADIF/LATM，不检查 ADTS CRC。关闭 open=FORMAT。[test_aac.c](../tests/test_aac.c)、[audio.h](../include/exr/audio.h) |
| 37 M4A/M4B 非分片 mp4a AAC | 部分：元数据独立，解码需 AAC | 不支持页面；启用后支持 PCM 解码 | 不支持音频正文 | 部分：宿主时间线书签/章节 | 不支持 | 元数据检查不依赖 AAC；不支持外部 data ref、多 sample description、不连续/变速 edit。[test_m4b.c](../tests/test_m4b.c)、[test_m4b_metadata.c](../tests/test_m4b_metadata.c) |
| 38 M4B 加密媒体 / 分片 MP4 | 不支持音频解码 | 不支持 | 不支持 | 不支持自动媒体绑定 | 不支持 | 不支持受保护音轨与分片媒体；元数据可读不等于可播放。[m4b.c](../src/m4b.c)、[audio.h](../include/exr/audio.h) |
| 39 Ogg Vorbis / Opus | 不支持 | 不支持 | 不支持 | 不支持自动媒体绑定 | 不支持 | PCM 自动探测无 Ogg/Vorbis/Opus decoder；宿主可自供解码后的 PCM provider。[pcm.c](../src/pcm.c)、[audio.h](../include/exr/audio.h) |
| 40 ODT（OpenDocument Text） | 不支持 | 不支持 | 不支持 | 不支持 | 不支持 | 无 ODT reader/枚举；ZIP 容器支持不等于 ODT 语义支持。[document.h](../include/exr/document.h)、[formats.c](../src/formats.c) |
| 41 DjVu | 不支持 | 不支持 | 不支持 | 不支持 | 不支持 | 无 DjVu 固定页 reader。[document.h](../include/exr/document.h)、[pdf_document.c](../src/pdf_document.c) |

标注持久化由 [library.h](../include/exr/library.h) 提供；流式 TextQuote/CFI 不是向每一种原始文件写批注。PDF 原文件标注写回仅覆盖 Text、Highlight、Underline、StrikeOut、Squiggly，要求 PDF≥1.4、无加密及受支持的权限状态。音频书签须由宿主将原文件与稳定 track ID/时间线绑定，SDK 不会自动给所有音频文件建立书库关系。

矩阵以当前实现为准；[FORMAT-COVERAGE.md](FORMAT-COVERAGE.md) 保留 2026-11-07 的真实文件失败记录，[DRM.md](DRM.md) 记录后续加入的 LCP Basic 实现。旧批次 LCP 失败不能覆盖新实现，同样，新的 Basic 合成/公开样本通过不能推导成商用 LCP、ADEPT 或所有 EPUB 兼容。
