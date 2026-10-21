# 当前支持矩阵

本表是**单一入口的当前状态**：只列现在能做什么、边界在哪、由哪套回归守着。
历史批次叙述、逐次验证记录与像素参考仍见 [NATIVE_VALIDATION.md](NATIVE_VALIDATION.md)、
[NATIVE_API.md](NATIVE_API.md) 与 [PERFORMANCE.md](PERFORMANCE.md)；本表随每批交付更新，
发行时以本表为准。

- 版本：**3.40.0 开发版**，ABI epoch **1**，书库 schema **6**（三者独立管理）
- 标记：**支持** = 有公开接口、边界与回归；**部分** = 有实现但覆盖/兼容未完整；**未支持** = 明确拒绝或不存在接口
- 回归：`ctest` 名称，本机完整配置含 fuzz 当前163项；测试数随组件、fuzz和参考工具配置变化，以对应验证记录为准

本轮平台应用、真实语料和性能结果见 `docs/validation/2026-10-20-native-hosts.json`、
`docs/validation/2026-10-20-corpus-performance.json`。Windows/macOS/iPhone模拟器/iPad模拟器
已有原生参考阅读应用；应用自动自检与完整生命周期、无障碍和真机验收分别记录。
整本检查范围及拒绝条件见 `docs/CORPUS_VALIDATION.md`。
普通水平Latin表格单TEXT内容在无OpenType塑形/位图字体等条件下复用一次有界宽度扫描；
其余内容保留通用算法。本批对照与分类见 `docs/validation/2026-10-20-wp6-compatibility.json`。

3.38.3章输入采用ZIP回调和每次最多32KiB的XML输入，仍创建完整DOM和正文投影。
32MiB单成员、128MiB累计展开上限及公开快照生命周期不变；这是原完整快照路径的限制。
分块不变性、取消/CRC清理、加载内存和失败复核见 `docs/validation/2026-10-20-wp6-input-stream.json`。

3.39.0集成WP7的八个声明脚本及固定800例口径；主线Linux sanitizer与Windows结果分别记录于
`docs/validation/2026-10-20-wp7-integration.json`，原分支Windows证据保留于 `docs/validation/wp7-windows.json`。

3.40.0独立章阅读的预算、查询、正文输出与验收入口见 `docs/WP6-BOUNDED-READER.md`。

## 输入格式

| 能力 | 状态 | 边界 | 回归 |
| --- | --- | --- | --- |
| TXT | 支持 | 编码探测、行/段落切分 | `native-text` |
| 严格 XHTML / HTML | 支持 | 只接受良构标记；**不做** HTML5 错误恢复 | `native-html-raw` |
| FB2 | 支持 | 命名空间、注释、内嵌图片 | `native-fb2` |
| EPUB 2/3 | 支持 | OPF/NCX/nav、资源、CFI；完整快照或独立有界章分页；CSS 为子集（见下） | `native-navigation`、`native-cfi`、`native-xml-input` |
| DOCX | 支持 | 段落/样式/表格/图片/关系；**不覆盖**完整 Word 打印版面 | `native-docx` |
| RTF | 支持 | 表格、列表、脚注、编号、fallback 字体 | `native-rtf`、`native-rtf-table`、`native-rtf-note` |
| MOBI / KF8 | 支持 | PalmDOC/Huff 解码、KF8 结构与资源 | `native-mobi`、`native-kf8` |
| CBZ | 支持 | PNG/JPEG/GIF/BMP 内置；WebP/TIFF/AVIF 为默认开启的构建选项。GIF/WebP/AVIF动画与多目录TIFF按原始页序展开（ID 为原名或原名`#N`），单图≤4096帧、整包≤10000页，不静默丢页；自然排序、ComicInfo、单页PNG/JPEG像素不变。编码/展开/页数预算见 [WP12A-FORMATS.md](WP12A-FORMATS.md) | `native-cbz`、`native-cbz-formats`、`native-image-formats` |
| PDF | 支持 | 见 PDF 各节；不支持的特性明确返回 `EXR_UNSUPPORTED`/`EXR_FORMAT` | `native-pdf-*` |

## 文本与字体

| 能力 | 状态 | 边界 | 回归 |
| --- | --- | --- | --- |
| Unicode 17 字素/断行 | 支持 | UAX #29 / UAX #14 默认规则，官方测试全量回归 | `native-line-boundary`、`native-case-reference` |
| 双向文字 | 支持 | UAX #9 段落分析 + L1/L2 重排；公开 `exr_bidi_*` 查询（含镜像与基级） | `native-bidi` |
| OpenType 塑形 | 支持 | GSUB/GPOS、连字、标记、字距、可变轴；阿拉伯预处理；Devanagari deva/dev2；Bengali/Tamil/Telugu/Kannada/Malayalam/Thai/Khmer/Myanmar 专用塑形 | `native-shaping`、`native-ot-variation`、`native-wp7` |
| 其他 Indic / 东南亚脚本 | 支持 | Bengali、Tamil、Telugu、Kannada、Malayalam、Thai、Khmer、Myanmar；每脚本 50 序列、真实+合成字体、HarfBuzz 14.6.0 对照；边界/已知差异见 [WP7-SCRIPTS.md](WP7-SCRIPTS.md) | `native-wp7` |
| 竖排 / 混轴 | 支持 | 统一页面竖排 + 横竖混排块续排 | `native-vertical`、`native-orthogonal` |
| Ruby | 支持 | 注音不参与 AUTO 方向快速判定 | `native-ruby` |
| 断词 | 支持 | C provider、词典可选、复合词、NOHYPHEN、大小写条件、拼写替换后再匹配、检查点 | `native-hyphen*`（6 项） |
| COLR v0/CPAL、sbix、CBDT/CBLC、cmap 14 | 支持 | 层数/调色板/回退与位图 strike 规则保持；字形图像与调色板查询见 [text.h](../include/exr/text.h) | `native-font-color` |
| COLR v1 | 部分 | Paint 1–32 全部实现；paint 深度 64、节点 4096、stop 256、嵌套颜色字形 16 且拒绝环；单字形 8192 px/8 Mi 像素、共享工作预算与取消。复合仅支持 SRC_OVER 与 16 种混合模式，12 种 Porter-Duff 明确 `EXR_UNSUPPORTED`；可变 `PaintVar*` 由 FreeType 按当前设计坐标解析。矩阵与差异见 [WP8_COLR_V1.md](WP8_COLR_V1.md) | `native-font-color-v1` |
| SVG 字体 | 部分 | 冻结子集：`svg/g/defs/path/rect/circle/ellipse/line/polyline/polygon`、solid fill/stroke、transform、viewBox、组透明度、`currentColor`、gzip，以及 `id="glyph<gid>"` 选择；明确拒绝外部引用、脚本、image/use/text、渐变/pattern、mask/clipPath/filter、DTD/实体与 style 属性。边界见 [WP8_SVG_FONTS.md](WP8_SVG_FONTS.md) | `native-font-svg` |
| 宿主字体集 | 支持 | 1–32 个内存字体、整簇覆盖优先、逐标量回退；系统字体发现由宿主负责 | `native-font`、`native-book-font` |

## EPUB / 流式文档排版

| 能力 | 状态 | 边界 | 回归 |
| --- | --- | --- | --- |
| CSS 子集 | 部分 | 块/行内、字体、颜色、边距、对齐；完整 CSS 未冻结 | `native-complex-layout` |
| 表格 | 支持 | 指定/auto/fixed/百分比 列宽、top/middle/bottom/baseline、border-collapse（solid/dashed/dotted/double 线型）、rowspan、跨页续排、分页时重复 `<thead>` | `native-table-*`（6 项）、`native-table-dashed`、`native-table-header` |
| 边框 | 支持 | 四边独立 width/style/color；`border` 与 `border-top` 等简写、1–4 值 `border-width`/`border-color`/`border-style`；块级、separate 单元格与 collapse 网格 | `native-border-edges` |
| 表格间距 | **不支持** | `border-spacing` 尚未实现：`border-collapse: separate` 的单元格按 0 间距排列；显式指定间距的表格会比参考实现更紧凑 | — |
| 浮动与绕排 | 支持 | float/clear、逐行绕排、长浮动/嵌套续排 | `native-float`、`native-table-fragments` |
| 分页与检查点 | 支持 | 页级续排、LRU 1–64 段、缓存字节/页预算、checkpoint 恢复 | `native-pager`、`native-page-cache`、`native-checkpoints` |
| 定位与命中 | 支持 | UTF-8 源偏移、CFI、TextQuote 锚点、改版后重定位 | `native-cfi-text`、`native-anchor` |
| 章内有界阅读 | EPUB 独立入口 | 紧凑全局索引 + 字符串窗口；原子单元超预算拒绝；快照语义不变 | `native-chapter-index/window/source/reader`、`native-style-budget` |

## PDF 阅读与绘制

| 能力 | 状态 | 边界 | 回归 |
| --- | --- | --- | --- |
| 对象与流解码 | 支持 | 交叉引用/对象流/压缩流，嵌套与长度上限 | `native-pdf-objects` |
| 字体 | 支持 | Type1/TrueType/Type0/Type3、CID、编码表、字形名 | `native-pdf-font`、`native-pdf-type3` |
| 路径/图像/内联图 | 支持 | 常见图像过滤器；Pattern 未支持 | `native-pdf-graphics`、`native-pdf-image`、`native-pdf-inline` |
| 渐变与网格 | 部分 | 二维函数/轴向/径向及Domain映射、网格类型 **4/5/6/7**（Gouraud 三角/晶格、Coons、张量积），32 位坐标与最多 4 个颜色分量；采样计入共享工作预算。支持临时BBox裁剪和径向有效最大根；各分量函数数组共用1MiB/16层/1024节点限界；原生轴向/径向按实际裁剪区四点采样，使用512项色表并支持完整Extend；旧宿主未提供paint时仍走有限位图外推；Type1使用512×512采样，自适应采样待实现；sh按规范忽略Background | `native-pdf-shading`、`native-pdf-shading-mesh`、`native-pdf-shading-mesh7`、`native-pdf-raster` |
| 文字几何/搜索/选择 | 支持 | 文字位置、搜索、选择、命中 | `native-pdf-text` |
| 元数据 | 支持 | Info/XMP 读取与增量写回 | `native-pdf-metadata-write`、`native-metadata` |
| 认证 | 部分 | Standard R2–R6、RC4/AES、Crypt filter；**证书 PubSec、EFOpen、加密写回未支持** | `native-pdf-crypto` |
| 色彩 | 部分 | Device/Indexed/CalGray/CalRGB/Lab、ICCBased v2/v4→sRGB、Separation/All/None/DeviceN、Type 0 函数；支持匹配尺寸软遮罩的原生分量Matte还原（先于ICC）；**OutputIntent 未支持**；默认DeviceCMYK完整Argyll ICC按zlib内嵌（414,609字节），不同于SWOP；关闭ICC时使用朴素换算 | `native-pdf-color`、`native-pdf-calculator`、`native-render-audit` |
| 合成 | 部分 | 16种混合、RGB/Gray/CMYK、隔离/非隔离/挖空及区域缓冲；128个嵌套探针、24组整图对照。DeviceCMYK路径/图像/1–7型渐变保留原生墨色；零opacity保留shape，64个PDF与192个画布组合覆盖。ICCBased/DeviceN到组空间及其他边界仍待扩展 | `native-blend`、`native-zero-opacity`、`native-nested-groups`、`native-inks` |
| 图形状态软遮罩 | 部分 | Alpha/Luminosity、BC、Identity及Type 0/2/3/4 TR、精确变换BBox、K/I、q/Q/None和单次整组提交；活跃mask聚合64MiB，嵌套共享工作预算。原41场景+8拒绝、作用域27+3、新函数/图像/几何72+8。AIS及图片内在shape/opacity已接入，新增166场景+4拒绝值与192个画布组合；外部参考差异逐项记录 | `native-mask-scope`、`native-mask-functions`、`native-pdf-raster`；[对照口径](MASK_SEMANTICS.md) |
| 标注 | 部分 | Text/Highlight/Underline/StrikeOut/Squiggly 增删改与外观；**其余类型与 AcroForm 未支持** | `native-pdf-markup`、`native-pdf-appearance`、`native-pdf-write` |
| 安全 redaction | 未支持 | 现有增量删除保留历史原文，不能充当擦除 | — |
| OCR | 未支持 | 无后端、无文字层 | — |

## 书库、转换与音频

| 能力 | 状态 | 边界 | 回归 |
| --- | --- | --- | --- |
| 书库 | 支持 | SQLite、元数据/封面、标签/收藏/已读、文本与固定页进度、标注、音频书签、精确去重、事务备份；CBZ 原书支持 64 KiB 分块流式导入/去重与 blob 随机读取；PDF 通过只读文件映射解析元数据、匿名映射回读存储原书（单条≤2 GiB）。1 GiB 实测新增缓冲峰值 64 KiB | `native-library-unique`、`native-library-stream`、`native-progress-library`、`native-page-annotations` |
| 旧 UI 数据迁移 | 未支持 | 旧 IndexedDB/Tauri 数据未接入 | — |
| 转换/导出 | 部分 | 六种正文格式 36 向互转及 MOBI/KF8 输入→六目标（text profile，仅声明正文/段落/顺序/Unicode，非无损）；EPUB/XHTML→EPUB/HTML 资源包 preserve profile；**完整 WP12 高保真全格式往返、批注/复杂样式和旧 UI 迁移未覆盖**；MOBI/KF8/PDF/CBZ 写回未支持。契约见 [CONVERSION.md](CONVERSION.md) | `native-export-epub`、`native-export-html`、`native-export-xml`、`native-convert`、`native-convert-cli`、`native-convert-benchmark` |
| 音频 | 支持 | WAV/FLAC、可选 MP3/AAC/M4A/M4B、PCM、WSOLA 变速、六平台输出；随机读取源在 1 GiB WAV 上验证，WAV 读取使用 4 KiB 栈缓冲且不整文件驻留 | `native-audio`、`native-wave`、`native-flac`、`native-mp3`、`native-aac`、`native-stretch` |
| 移动音频会话 | 未支持 | 打断/后台/真机未验收 | — |

## SDK 与平台

| 能力 | 状态 | 边界 | 回归 |
| --- | --- | --- | --- |
| C SDK | 支持 | 316 个公开函数导出、`struct_size` 前缀兼容 | `native-abi`、`native-core` |
| C++ / Swift / JNI 适配 | 支持 | 安装后消费示例与 `-Xcheck:jni` | `native-fixed-example`、`native-wave-example` |
| 安装与包配置 | 支持 | `find_package(EXReader 3.40.0 EXACT CONFIG REQUIRED)` | CI 安装作业 |
| 桌面三平台 | 支持 | Windows/Linux/macOS 全量 CTest + 安装消费 | CI `desktop` |
| Android / iOS / iPadOS | 部分 | 库交叉编译、Swift适配、iPhone/iPad模拟器阅读自检；真机安装暂缓 | CI `android`、`apple-mobile` |
| 嵌入阅读视图 / 示例 App / TTS / 无障碍 / OPDS / LCP | 未支持 | 目标见 [VERSIONING.md](VERSIONING.md) | — |

## 质量口径

| 项 | 当前值 |
| --- | --- |
| 桌面 CTest | 主线联合测试与各分支原始验收分开记录，见 `validation/2026-10-20-parallel-integration.json` |
| Sanitizer | 当前源码的ASan/UBSan结果独立记录于 `validation/2026-10-20-parallel-integration.json` |
| 编译器门槛 | `-Wall -Wextra -Wpedantic -Werror` |
| Fuzz | 确定性种子变异驱动，CI 每推送 20 万次迭代；24 CPU 小时为目标，见 [FUZZING.md](FUZZING.md) |
| 依赖 | 14 个第三方组件，全部 SHA-256 固定；WebP/TIFF/AVIF 为默认开启的可选构建项 |

## 更新规则

- 本表每交付一批更新一次；**状态变更必须同时有接口、文档与回归**，否则只记录为「部分」。
- 新增「支持」条目需给出边界与拒绝行为；删除条目需保留历史记录链接。
- 版本号按 [VERSIONING.md](VERSIONING.md) 分配：功能批升次版本，缺陷修复升补丁版本，ABI/schema 变更单独声明。
