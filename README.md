# EXReader — native C reading engine & SDK

EXReader 是面向桌面和移动阅读应用的 **C11 原生阅读引擎与可嵌入 SDK**，当前为 **3.40.0 开发版**，ABI epoch 1、书库 schema 7。核心自有代码使用 MIT 协议，可构建静态组件或 DLL / SO / dylib，以 C 接口供 C/C++、Swift 和 JNI 宿主调用。

项目以**多格式阅读、自有 PDF 渲染核心、轻量与高性能**为主线：优先做好常用文档的可靠打开、正确显示、快速首屏/翻页和有界内存。成熟引擎用于差分与性能参照，撤销“全面领先 MuPDF 等引擎”的总目标。可选编辑、OCR、网络和平台服务按实际需求独立推进；性能按固定设备、语料与构建的实测预算验收，具体取舍见 [项目定位与优先级](docs/PROJECT_OVERVIEW.md#项目定位与优先级)。

**不依赖 WebView 或浏览器运行时。** HTML/EPUB 由 C 核解析、排版和绘制，PDF 使用自有原生渲染核心；参考宿主通过原生控件与绘图接口接入 SDK。

原生参考宿主覆盖 Windows（`examples/reader.c`）、Linux GTK（`examples/linux/`）与
macOS/iPhone/iPad（`examples/apple/`），提供各自声明范围内的书架、导入、阅读、选文标注和进度恢复。
Android 宿主已在共同源码 S 完成 API34 x86_64 模拟器联合验收。各宿主的格式、文件大小、生命周期与设备限制分别记录，
不使用统一的“32 MiB”口径。iPhone/iPad 和 Android 的模拟器结果与真机验收分开登记。

项目定位、当前交付状态与质量目标见 [项目概述](docs/PROJECT_OVERVIEW.md)。格式和功能的详细边界见
[支持矩阵](docs/SUPPORT_MATRIX.md)；新增独立包的验收与待集成状态另见项目概述，不将单包通过视为产品整体完成。
下一版的六个工作包与并行边界见 [原生阅读核心路线](docs/CORE-ROADMAP.md)；历史能力积压见 [版本路线记录](docs/VERSIONING.md#后续兼容目标与验收顺序)。
轻量阅读 SDK 的构建命令见 [阅读 SDK preset](#阅读-sdk-preset)。

版本按更新规模递增：超大更新升主版本，中等更新升次版本，小 bug 修复升补丁版本；升级前两段时，后续段归零。全部历史已按此规则重编，见 [完整更新日志](CHANGELOG.md)；编号口径见 [版本规则](docs/VERSIONING.md)。

2.4.1（原编号0.12.1）修复全库审计确认的七项缺陷，覆盖长附标塑形、重复章节标注、备注长度、XML 导出、跨行塑形、RTF fallback 和 HTML script/style。每项有独立回归测试与提交；[验证记录](docs/NATIVE_VALIDATION.md#0121-audit-fixes) 列出覆盖范围与资源上限。

文本解码、格式解析、文档模型、CSS 子集、字素边界、双向文字、OpenType 替换与定位、换行、分页、文字位置、命中测试和页面合成都由项目的 C 代码实现。底层使用 FreeType、Expat、miniz 等组件；SQLite 书库、扩展图像解码、音频和 PDF 密码学按组件与构建开关选择。PDF 密码认证不为默认 SDK 引入网络运行时；OPDS 与 OCR 作为独立可选模块提供。第三方组件、字体及可选 GPL 依赖的许可分别记录。

框架面向通用宿主：宿主可以直接构造文档树和资源，将自己的解析结果交给引擎；文档树、资源、字形、行、图片和单元格坐标均可读取。宿主可以覆盖样式、关闭书内 CSS、替换图片解码器，或直接使用布局数据自行绘制。文档构造、解析和排版可独立于 SQLite 书库使用，UI、账号、同步和平台事件由宿主决定。

## 组件选择

核心接入使用 `#include <exr/core.h>` 和 `EXReader::exr_core`，包含文档模型、文字分析、排版分页、坐标/命中与绘制接口。需要单独模型或文字分析时，也可直接链接 `exr_doc`、`exr_text`。`exreader.h` 和默认总库继续兼容原入口。

| 可选组件 | CMake 目标 | 构建开关 |
| --- | --- | --- |
| PDF/CBZ 固定格式读取 | `exr_pdf` | `EXR_ENABLE_PDF` |
| PDF 标注、元数据与基础 AcroForm 编辑 | `exr_pdf_edit` | `EXR_ENABLE_PDF_EDIT` |
| 有声书、PCM、AAC/M4B 与设备输出 | `exr_audio` | `EXR_ENABLE_AUDIO` |
| SQLite 书库、进度和笔记存储 | `exr_library` | `EXR_ENABLE_LIBRARY` |
| 独立全文索引 | `exr_textindex` | `EXR_BUILD_TEXT_INDEX` |

各组件有独立版本字段，核心为3.39.0，PDF读取为3.38.3，书库为3.34.0，其余组件为3.33.0；总SDK版本为3.40.0。关闭PDF后书库仍支持重排文档；固定格式导入明确返回不可用。关闭音频不影响书库保存宿主提供的续播数据。关闭书库和全文索引后不下载或链接SQLite。AAC默认关闭；启用FAAD2只影响链接音频组件的组合产物，核心代码仍是MIT，包含FAAD2的最终二进制需要遵守GPL。

纯核心静态构建：

```sh
cmake -S . -B build/core -DEXR_ENABLE_AUDIO=OFF -DEXR_ENABLE_LIBRARY=OFF -DEXR_BUILD_TEXT_INDEX=OFF -DEXR_ENABLE_PDF=OFF -DEXR_ENABLE_PDF_EDIT=OFF -DEXR_BUILD_SHARED_COMPAT=OFF -DEXR_BUILD_TOOLS=OFF -DEXR_BUILD_JNI=OFF
cmake --build build/core --parallel 4
ctest --test-dir build/core --output-on-failure
```

`EXR_BUILD_SHARED_COMPAT=OFF`关闭旧总DLL；静态组件按调用需求由链接器选取。ICC转换另有`EXR_ENABLE_ICC`开关，关闭时采用已声明的朴素设备色转换。组件依赖与安装示例见 [架构说明](docs/ARCHITECTURE.md)。

### 阅读 SDK preset

`CMakePresets.json` 提供两个 Release 静态阅读 SDK 配置：

| preset | 用途 | 组件 |
| --- | --- | --- |
| `reading-core` | 多格式重排阅读与自有 PDF/CBZ 固定页，不带书库 | 保留 PDF、PDF 密码认证、ICC 及 WebP/TIFF/AVIF 图像开关；关闭音频（含 MP3/AAC）、书库、全文索引、PDF 编辑、旧共享总库、工具、测试、fuzz 和 JNI |
| `reading-library` | 需要 SQLite 书架、进度与笔记的宿主 | 继承 `reading-core`，只增加 `EXR_ENABLE_LIBRARY=ON` |

```sh
cmake --preset reading-core
cmake --build --preset reading-core
cmake --install build/reading-core
```

安装前缀为 `build/<preset>/stage`；`reading-library` 将命令中的名称替换即可。前置条件：CMake 3.24+、Ninja、C11 编译器在 `PATH` 中可用（preset 固定 Ninja 生成器，Windows 需在已加载 MSVC 环境的命令行中运行），AVIF 开启时还需 Perl；首次配置需联网下载固定散列的依赖。
这两个配置只是组件裁剪，不增加 PDF 或图像能力，也不表示性能已达标；PDF 编辑、音频和全文索引仍可用默认构建或单独开关启用。GitHub Linux（ubuntu-22.04）已完成验证；Windows（windows-2022/MSVC）与 macOS（macos-15/ARM64）在受测源码 `9b968a16` 的 run [39854485070](https://github.com/NoGod3524/EXReader/actions/runs/39854485070) 中两 preset 共 4/4 作业完成构建、安装、安装后消费者与九格式合成 smoke，见 [H1 平台记录](https://github.com/NoGod3524/EXReader/blob/2e8e981b6dd44d855a23931480fe5e0d5c791762/docs/READING-PLATFORMS.md)。该结果不含性能或体积预算，证据门禁加固另由 [H6](https://github.com/NoGod3524/EXReader/blob/62ab38e8223e42f1562fda7137cd41b4d87620f1/docs/handoffs/reading-H6-platform-gate.md) 跟踪。

## 当前实现

| 模块 | 当前能力 |
| --- | --- |
| 固定版面构造 | `exr_layout_create_positioned()` 保留定位字形、图片/色块和源范围；`exr_fixed_create()` 接收任意格式的页目录和按需绘制提供者 |
| C 原生 PDF | `exr_fixed_open()` / `exr_fixed_open_memory(EXR_PDF,...)` 打开页目录，`exr_fixed_render()` 按页绘制，`exr_fixed_load_text()` 返回语义文字与源坐标字格；对象/流、字体、文字、路径、Form、JPEG、调色板、图像遮罩、轴向/径向渐变与网格着色（类型 4–7）由 C 核处理；支持 CMYK/YCCK JPEG 的四分量 Decode/ICC 转换，以及可选 R2–R6 密码认证与 RC4/AES 读取 |
| SDK 兼容 | ABI epoch 1 运行时查询；安装后可通过 CMake `EXReader::exreader` 接入，含独立宿主示例与明确的布局/所有权约定 |
| JNI 接入 | 可选 Java/Android 桥接库，提供串行 AutoCloseable 重排文档、EPUB 分章加载、分页、PDF/WAV/PCM 句柄；开放节点、字形/行/框、字体与图片快照 |
| Swift 接入 | SDK 内置 C 模块映射，提供 ARC 通用文档、EPUB 分章加载、分页、字体、PDF 和 WAV/PCM 封装；布局记录、字体与图片可独立复制 |
| 有声书模型 | 宿主轨道、毫秒时间线、嵌套章节、双向图文同步；可接宿主播放/倍速/跨轨后端并按稳定 ID 续播，WAV/FLAC/MP3 按需解码，开放 PCM 提供者；原生 waveOut/AudioQueue/OpenSL ES/ALSA 声音输出，续播与时间书签可保存、备份 |
| M4B 容器信息 | 无需 AAC 解码器即可按需读取 iTunes/freeform/mdta 文本元数据、PNG/JPEG 封面、Nero chpl 与 QuickTime 文本章节；保留未知文本键，返回独立快照，可接通用有声书时间线，附 Swift/Java 包装 |
| PDF 书库 | 保存原书、Info/XMP 标题/作者、页进度与固定页备注，支持 NUL 引用、稳定锚点、备份恢复和旧库事务迁移 |
| 固定页交互 | 语义文字快照、线性精确搜索、字格选择、源坐标命中、PDF 原生标注数据读取、页 ID 与引用/上下文稳定标注锚点，支持宿主固定格式 |
| PDF 标注编辑 | 按页和 NM 新增、更新 Text/Highlight/Underline/StrikeOut/Squiggly，删除标注及同页 Popup；追加修订并返回完整 PDF，保留原字节；绘制已有与新写入的 normal Form 外观，SDK 书库备注由宿主显式同步 |
| 基础 AcroForm | 字段继承、值/默认值、选项与 widget 快照；声明范围内文本、checkbox/radio/choice 的增量值与外观写回；独立交付新增 75 份语料通过，至少 30 文件出口满足，完整 WP9 仍有未覆盖项，见 [最新交付与边界](https://github.com/NoGod3524/EXReader/blob/8c25d2f67c5846b548a2aafa0060f06036c1d364/docs/handoffs/2026-10-22-AB-delivered.md) |
| 通用绘制接口 | 开放 Bézier 字形轮廓、路径/描边、分层图片、裁切、正逆视口矩阵和流式绘制回调；可用内置 C 画布或宿主绘制后端 |
| 文档输入 | TXT（UTF-8、带 BOM 的 UTF-16）、HTML、FB2、EPUB spine、DOCX 结构、RTF 正文、MOBI / PalmDOC / HUFF-CDIC、KF8 章节、CSS、图片与字体 |
| 宿主文档构造 | `exr_document_create()` 接收通用节点、章节和资源字节，复制输入并生成规范化正文；宿主解析器无需注册，可直接接入现有搜索、布局、渲染和正文导出 |
| 操作控制 | 随机读取、样式、分页、OpenType 塑形和绘制的协作取消与进度回调；取消未命中页面时保留已有缓存，可清除取消后恢复 |
| 随机读取源 | 文件或宿主 read_at 回调按需读取 EPUB 目录、章节和资源，不常驻复制整个压缩文件；共享源保持到最后一个章节释放 |
| 分段按需加载 | 通用 publication / loader 接口；内置 EPUB 打开时只索引，访问某章时才解析和排版；session 以 LRU 保留 1–64 个分段 |
| 有界 EPUB 章阅读 | `exr_publication_pager_create()` 使用章索引、窗口与可恢复分页状态；50/100 MiB 单章、内存增量和随机恢复已在固定源码验收，完整文档快照 API 保留原语义，见 [有界阅读契约](docs/WP6-BOUNDED-READER.md) |
| 分页检查点 | 借用页模式按间隔保存有数量/字节预算的恢复点，支持原始行、双向段落和表格组；未命中旧页从最近检查点续排，可关闭并查询统计 |
| 页级续排 | `exr_pager` 在页边界暂停；长段落逐字素推进，表格逐 rowspan 连通组测量；输出独立单页布局 |
| 缓存字节预算 | 页缓存与章节 session 均支持 LRU 数量/载荷字节双限制；超限的新页或章节保留旧缓存；可查询计量值 |
| 通用导航目录 | 可复制宿主目录；EPUB 3 nav / EPUB 2 NCX 按需解析、缓存，保留父子关系、目标分段、相对 URI 和开放 role；重复路径不猜测目标 |
| EPUB 文档结构 | XHTML 文档树保留章节、标题、内联元素、嵌套列表、图片、表格、脚注、全部属性与原始解码文本；保留 EPUB 3 导航树、非线性章节和辅助 XHTML |
| EPUB 资源与链接 | manifest 资源清单、图片 / CSS / 字体等资源按需解压；支持章节相对路径、Unicode / 百分号转义与片段 ID 定位 |
| 自有排版 | 字体实际 advance / kerning、段落、标题字号、自动换行、Unicode 字素簇保护、中文标点与不换行空格约束、分页；页面宽高、字号、行距、段间距、页边距可调 |
| 开放文字边界 | `exr_text_analyze()` 输出按 UTF-8 字节索引的 Unicode 17.0 扩展字素边界、Unicode 17 默认 UAX #14 换行机会、强制换行和禁止紧急换行标志；无需文档、字体或书库 |
| 双向文字 | 原生 Unicode 17 UAX #9 分析与逐行视觉重排，支持嵌入、隔离、括号配对和镜像；完整 861,948 个官方方向用例回归；提供独立 bidi API |
| OpenType 塑形 | 原生 GSUB 1–8 / GPOS 1–9 lookup 引擎，拉丁连字、阿拉伯连接形与 lam-alef、字偶距、附标与连写定位；开放 script / language / feature 和字形偏移 |
| 竖排 | 统一页面 vertical-rl / vertical-lr、Unicode 17 字形朝向、vert / vrt2 / vkrn 与 vmtx、混合直立/侧排、横竖/反向列块上下文、物理命中、分页和检查点 |
| 可变字体 | 只读轴查询、按 tag/face 创建独立坐标实例；gvar/HVAR/VVAR、avar、原生 GDEF VariationIndex 与 GSUB/GPOS 条件特征替换 |
| CSS 子集 | 章节样式表、内嵌和内联样式；元素 / 类 / ID / 后代 / 子选择器，优先级和继承；混合字号、粗斜体、颜色、段落方向、对齐、缩进、边距、背景、实线边框和强制分页 |
| 图片与表格 | PNG/JPEG 解码、透明合成和等比缩放；按内容自动列宽或 CSS 固定列宽、单元格垂直对齐/基线、逐边边框（solid/dashed/dotted/double，collapse 与 separate）、分页重复 `<thead>`、float/clear 与逐行绕排、换行、colspan / rowspan、按行组跨页 |
| 字体回退 | 宿主提供有序字体字节和集合 face index；优先整字素簇覆盖，必要时逐标量回退；可查询 cmap 覆盖，布局输出字体索引与缺字标记 |
| 书内字体与匹配 | 本地 `@font-face` TTF/OTF、CSS `font-family` 列表与转义、粗斜体选脸、章节作用域与宿主禁用开关；布局保留有效字体集，可读取编码字节自行绘制 |
| 原生渲染 | FreeType 字形栅格化，C 合成灰度或 RGBA 像素；BMP / PNG 输出，无图形界面依赖 |
| 文字定位 | UTF-8 字节位置、全文查找、按字素簇命中测试、按位置查页；字形输出保留簇范围；改变页宽和字号后可重新定位 |
| EPUB CFI | 按原始 OPF spine 和章节 XML 树生成/解析整书位置与跨章范围，按需入口只加载目标章，保留重复 spine、ID 修正、UTF-16 偏移、前后文断言与 side bias；也可独立使用章节内容路径 |
| 稳定文本锚点 | 保存选文、前后文和可选章节路径；正文前方增删后可重新查找范围，重复或失配明确报告；支持点书签，可独立于书库使用 |
| 全文索引 | 可选 SQLite FTS5 trigram 候选索引与 C 精确匹配；按宿主 source/part 接入，支持中文短查询、NUL、重叠命中、流式结果与按来源原子分段重建，不自动绑定书库格式 |
| 原生书库 | SQLite 单文件保存原书、书名、作者、标签、收藏、已读状态、阅读位置、封面和笔记、带上下文的阅读进度与事务式标注/进度重定位；可选择按格式与原文件字节精确去重导入；删除书籍时级联删除标注；事务备份 |
| 结构导出 | 新接口输出 EPUB 或带目录入口的 HTML 资源 ZIP，保留章节树、属性、图片、CSS、字体、链接、嵌套目录及资源原字节；校验路径、缺失资源和 XML 合法性 |
| 原文件元数据 | PDF Info/XMP 同步增量写回；EPUB 书名等 DC 元数据及 PNG/JPEG 封面写回，保留未改章节与资源的压缩字节 |
| 文字转换 | C 输出 TXT、HTML、FB2、RTF、EPUB、DOCX；覆盖 Unicode 与文本转义往返，不保留复杂排版和图片 |
| 工具与可选模块 | `exreader-convert` 提供轻量正文转换和声明范围的资源包 preserve；旧 UI 迁移、OPDS1/2、Tesseract OCR 分别提供独立工具或模块，完整高保真转换、OCR 文字层闭环及宿主服务接入仍待推进 |

文字与字体覆盖 Unicode 17 字素/断行/双向分析、拉丁/中日韩/阿拉伯/希伯来及声明的 Indic/东南亚脚本，支持竖排、ruby、字体回退和可变字体。新增脚本见 [WP7](docs/WP7-SCRIPTS.md)，COLR v1 和 SVG 字体按 [WP8 声明子集](docs/WP8-HANDOFF.md) 验收；完整 CSS 和所有文字脚本仍有未覆盖项。

PDF 已有固定页绘制、文字几何、搜索选择、标准密码认证、标注/元数据与基础表单编辑。颜色、透明组合、图像过滤器和编辑类型各有明确边界；增量删除保留历史原文，不能当作安全 redaction。CBZ 的扩展图像和原书流式/映射口径见 [WP12A](docs/WP12A-FORMATS.md) 与 [存储专项](docs/WP12A-STREAMING.md)。

轻量转换只承诺正文与声明范围的 EPUB/HTML 资源 preserve；OCR 为独立可选适配器，PDF 文字层写回与完整交互闭环仍待完成。完整文档快照和有界 EPUB 章阅读使用不同入口，宿主接入与内存预算见各包契约。接口、所有权与限界见 [NATIVE_API.md](docs/NATIVE_API.md)；接口演进历史保留于 [更新日志](CHANGELOG.md)。

## 工程质量与当前进展

当前质量目标是：默认分支强制 CI 与可信构建基线、EPUB 超时/PDF 打开绘制失败闭环、成熟引擎差分与像素/性能回归、内存/长章节/恶意输入专项，以及许可证和版本发布流程统一。已有专项结果，但默认分支必需检查和整条发布门槛尚未闭合，真实兼容语料验收仍有缺口；逐项现状与证据见 [项目概述](docs/PROJECT_OVERVIEW.md#五项工程质量目标)。

冻结 SDK 源码的四目标各 24 CPU 小时长测与严格云端汇总已通过，该结果只绑定其源码。A/B/C 已联合收口：共同源码 S=`686ce2fe`，12 组 35 个上游作业同源成功，严格汇总 run [39850404743](https://github.com/NoGod3524/EXReader/actions/runs/39850404743) 确认 accepted；SDK 基线 K2=`d46ff370`，详见 [联合验收登记](https://github.com/NoGod3524/EXReader/blob/8c25d2f67c5846b548a2aafa0060f06036c1d364/docs/handoffs/2026-10-22-ABC-accepted.md)。验收只覆盖各包声明范围，真实语料与核心性能预算仍待完成。

原生阅读核心路线已在 `codex/r1-reading-core` 启动，状态按受测源码分开登记：

| 状态 | 范围 |
| --- | --- |
| 已完成 | 受测源码 `54d8c592`，run [39853356309](https://github.com/NoGod3524/EXReader/actions/runs/39853356309) 2/2 作业成功：Linux 上 `reading-core`、`reading-library` 的构建、安装、安装后消费者、九格式合成 smoke、组成判定与 1 MiB TXT/32 次翻页初始采样。前一源码 `61aa183` 的 run `39852907619` 因测量自验 mock 失败，记录保留 |
| 已完成 | H1：Windows/macOS 两 preset，受测源码 `9b968a16`，run [39854485070](https://github.com/NoGod3524/EXReader/actions/runs/39854485070) 4/4 作业成功（构建、安装、消费者 3/3 或 4/4、smoke 9/9）；门禁加固由 H6 另行跟踪 |
| 已完成 | R3 初始 PDF/CBZ 测量（合成）：源码 `3cd7bdf1` 的 run [39855093753](https://github.com/NoGod3524/EXReader/actions/runs/39855093753) 测 1 页 PDF 与 4 页 CBZ 极小 fixture；可区分页面候选 `4b6f562c` 的 run [39856195765](https://github.com/NoGod3524/EXReader/actions/runs/39856195765) 加入 3 页 PDF/4 页 CBZ 合成文档，12 进程/240 次绘制，2026-10-22 只读核对为 success，见 [R3 记录](https://github.com/NoGod3524/EXReader/blob/ea3d4d1a24c0febd8d14f110594b7226e2527c82/docs/READING-PDF-PERFORMANCE.md) |
| 已验证 | 阅读SDK固定`9854061`：六组18执行作业/30工件同源通过，含缓存、CMap/anchor、PDF绘制和受限JPX修复。见[SDK冻结记录](docs/R5-SDK-FREEZE.md) |
| 已验证 | R2固定八份真实文档与JPX专项：源码`da1c183`、run [39899523839](https://github.com/NoGod3524/EXReader/actions/runs/39899523839)三作业成功，整本8/8、重开定位8/8、ON/ASan/OFF各24项通过。见[语料记录](docs/R2-REAL-CORPUS.md)及[R4修复](docs/R4-CORE-HOTSPOTS.md) |
| 复验中 | H8–H11在新SDK共同源码`da1c183`重新执行；原`e25959e`四组11作业结果保留为历史，见[共同验收记录](docs/R5-SDK-FREEZE.md) |
| 收口中 | R3正式40进程基线与12页审阅、冻结硬预算；R6六平台候选封装和17作业总门禁。默认分支必需检查及发布尚未启用 |
| 后续范围 | 历史1710份库存仍未恢复，本批八份独立计数；跨平台性能、真机与读屏仍待各自验收 |

初始 TXT 与 PDF/CBZ 采样只针对极小合成工作负载，证明测量流程可运行，不是成熟性能基线，也不代表真实语料或任何性能预算已达标；RSS 增量为 0 只表示未超过进程先前高水位，不表示没有分配。新 profile 也不继承 S 的联合验收或旧源码长测。详见 [首轮启动记录](docs/READING-CORE-START.md) 与 [发布门槛映射](docs/READING-CORE-GATE.md)。所有构建、测试及证据汇总在 GitHub Actions 执行。

## 构建

需要 C11 编译器与 CMake 3.24+。首次配置联网下载启用组件的固定版本原生依赖，并验证 SHA-256；后续复用构建缓存。

Unicode 属性表已编入 C，普通构建无需 Python，也不下载 Unicode 数据。表和官方测试的固定来源、SHA-256、重现命令与 Unicode-3.0 数据许可见 [第三方许可](THIRD_PARTY_NOTICES.md)；SDK 同时附带许可文本。

```sh
cmake -S . -B build/native -DCMAKE_BUILD_TYPE=Release
cmake --build build/native --config Release --parallel 4
ctest --test-dir build/native -C Release --output-on-failure
cmake --install build/native --config Release --prefix stage
```

Windows 推荐 Visual Studio C 工具链；MinGW 的部分 Ninja 发行版无法处理中文构建路径，需要通过 ASCII 路径的目录联接配置工程。MSVC 使用静态 CRT；所有库分配的内存由对应的 `exr_*_free()` 释放。

配置 `-DEXR_BUILD_TOOLS=OFF -DEXR_BUILD_TESTS=OFF` 只构建库。Linux 可用 `-DEXR_SANITIZE=ON` 启用 AddressSanitizer / UndefinedBehaviorSanitizer。Android、iOS 和 iPadOS 使用 CMake 对应工具链编译；该工程输出引擎库，不输出手机阅读器安装包。跨平台验证状态见 [验证记录](docs/NATIVE_VALIDATION.md)。

## 直接运行

```sh
exreader-render book.epub /path/to/font.ttf page.png 0 720 1040
```

Windows 的示例：

```powershell
.\stage\bin\exreader-render.exe tests/fixtures/sample.txt C:/Windows/Fonts/msyh.ttc page.png
```

字体由宿主或用户提供，系统字体文件不随项目分发。命令行可使用 UTF-8 / Unicode 路径；Windows 参数通过宽字符入口转换。

这是 C 引擎实际生成的页面：

![Native C styles, images and table rendering](docs/styled-page.png)

## 性能基准

默认工具构建同时生成 `exreader-benchmark`，输出打开、首章解析排版、首画、逐页续排 / 渲染 / 完整翻页 p50 / p95 和进程峰值 RSS 的 JSON；直接运行不需要 Python。

```sh
stage/bin/exreader-benchmark book.epub /path/to/font.ttf --max-pages 64
stage/bin/exreader-benchmark book.epub /path/to/font.ttf --max-pages 64 --paging
python tools/run_benchmarks.py stage/bin/exreader-benchmark /path/to/font.ttf build/benchmarks --runs 3
```

Windows 使用 `stage/bin/exreader-benchmark.exe`。Python runner 生成固定的短书、单段长章和多章 EPUB，每轮启动新进程并保存明细与汇总。测量口径、复现方法和已归档的 0.10 / 0.11 / 0.12 实测结果见 [性能记录](docs/PERFORMANCE.md)。

整本兼容检查使用安装包中的 `exreader-check-document`，逐部分、逐页绘制和提取；
`tools/check_corpus.py`隔离进程并保存成功、错误及超时证据。输入清单、完整/受限覆盖和拒绝条件见
[整本兼容验证](docs/CORPUS_VALIDATION.md)。

## C 接入

```c
#include <exreader.h>

exr_document *doc = NULL;
exr_font *font = NULL;
exr_layout *layout = NULL;
exr_bitmap image = {0};
exr_error error = {0};
exr_status status;

status = exr_document_open("book.epub", &doc, &error);
if (status == EXR_OK) status = exr_font_open("font.ttf", &font, &error);
if (status == EXR_OK) status = exr_layout_create(doc, font, NULL, &layout, &error);
if (status == EXR_OK) status = exr_render_page_color(layout, font, 0, &image, &error);
if (status == EXR_OK) status = exr_bitmap_write_png(&image, "page.png", &error);

exr_bitmap_free(&image);
exr_layout_free(layout);
exr_font_free(font);
exr_document_free(doc);
```

接入自己的解析器时，将解析结果写入前序节点数组，再调用构造入口：

```c
exr_node_input nodes[] = {
    {EXR_NODE_DOCUMENT, SIZE_MAX, NULL, NULL, NULL, 0},
    {EXR_NODE_CHAPTER, 0, NULL, NULL, NULL, 0},
    {EXR_NODE_PARAGRAPH, 1, NULL, NULL, NULL, 0},
    {EXR_NODE_TEXT, 2, NULL, "Hello from a host parser.", NULL, 0}
};
exr_chapter_input chapter = {"main", "chapters/main", 1, 1};
exr_document_input input = {"Host document", nodes, 4, &chapter, 1, NULL, 0};
exr_document *doc = NULL;
exr_error error = {0};
exr_status status = exr_document_create(&input, &doc, &error);
/* On success, doc owns copies; pass it to the same layout/search/export APIs. */
exr_document_free(doc);
```

创建后的文档格式为 `EXR_CUSTOM`，输入数组、字符串和资源字节可在调用返回后释放。此入口不需要全局解析器注册表。自定义文档尚未提供结构化持久化；SQLite 书库仍按原文件字节导入。

SDK 附带完整宿主示例，可只使用安装后的头文件和库编译：

```sh
cmake -S stage/examples -B build/host -DEXR_SDK=/absolute/path/to/stage -DCMAKE_BUILD_TYPE=Release
cmake --build build/host --config Release
```

运行生成的 `exreader-construct-example`，传入字体文件和输出 PNG 路径，即可将自建文档排版为页面。`exreader-anchor-example` 无需字体和参数，演示保存选文并在正文插入内容后重新定位。构造接口的节点命名与 XHTML 行为约定见 [接口文档](docs/NATIVE_API.md)。

`exreader-lazy-example` 演示分段加载；默认创建三个宿主分段，只请求索引 1。提供 EPUB 和从 0 开始的分段索引时，改用内置 EPUB 索引：

```sh
exreader-lazy-example font.ttf host-part.png
exreader-lazy-example font.ttf epub-part.png book.epub 0
```

`exreader-text-example` 无需参数或字体，演示独立文字边界 API。示例验证 25 字节的组合字符、emoji ZWJ、旗帜和中文输入，输出 4 个字素簇及其 UTF-8 范围。

`exreader-font-example primary.ttf fallback.ttf output.png` 演示从宿主字节创建字体集、打印每个字符所选字体并输出页面。SDK 的 `examples/fonts` 附带小型测试字体，使用矩形字形验证回退；实际阅读字体由宿主提供。

`exreader-page-example book.epub font.ttf output.png [page] [part]` 演示按章节索引加载、页级续排、三页 / 8 MiB 载荷预算以及独立绘制；页和章节索引从 0 开始。

[公开头文件](include/exreader.h) · [接口与内存约定](docs/NATIVE_API.md) · [第三方许可](THIRD_PARTY_NOTICES.md)

## 版本保留

当前开发线使用 C 工程，阅读路径不依赖 WebView 或浏览器运行时。此前基于 JavaScript/WebView 的方案仅作历史保留，不再作为当前架构或发布目标： [JavaScript 框架](https://github.com/NoGod3524/EXReader/commit/4533185)、[带 UI 的阅读器](https://github.com/NoGod3524/EXReader/tree/codex/reader-app) 和 [MIT 版 0.1.1](https://github.com/NoGod3524/EXReader/tree/codex/reader-0.1.1) 保留为历史版本。旧 IndexedDB/备份到原生书库已有 [独立迁移工具](docs/WP12-MIGRATION-REVIEW.md)，新宿主的一键迁移入口仍待接入。历史发行附件不代表当前原生 SDK 的发布状态。

Copyright (c) 2026 EXReader contributors. 自有代码和原创测试资源使用 [MIT 协议](LICENSE)，允许商用、修改和再分发；第三方组件保留原许可。默认构建与 CI 关闭 GPL 依赖 FAAD2；手动启用 `EXR_ENABLE_AAC=ON` 的链接产物需遵守 GPL。


固定页面宿主示例（仅使用公开 SDK）：

```sh
exreader-fixed-example book.pdf page.png 0
# 未嵌入字体的 PDF 可显式提供宿主字体：
exreader-fixed-example book.pdf page.png 0 fallback.ttf
```

该入口使用固定页面模型；重排文档仍使用 `exr_document_open` 和 layout/pager 接口。

当前进度、量化验收目标、构建复现和待办顺序见 [交接文档](docs/HANDOFF.md)。
