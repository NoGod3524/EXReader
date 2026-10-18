# EXReader 原生框架交接

交接日期：2026 年 10 月 18 日。当前交付为无 UI 的 C11 电子书 SDK，GPL-3.0-only，0.18.0 开发版，ABI epoch 1，书库 schema 6。本次停止点是非隔离 RGB PDF 透明组这一可独立验收批次；完整 PDF、EPUB 排版及阅读 SDK 的目标仍有后续工作。用户要求本批完成后暂停，当前已暂停，未经后续继续指令不启动下一批。

版本号已在本记录之后提升为 **0.19.0 开发版**（ABI epoch 1、书库 schema 6 不变）；下文所有运行库哈希、CI 运行与采样仍对应 0.18.0 的已验证代码提交 `ec8d4a98`。

## 代码与交付位置

| 项目 | 当前值 |
| --- | --- |
| 仓库 | https://github.com/NoGod3524/EXReader |
| 开发分支 | `codex/framework` |
| 本批代码提交 | `ec8d4a98cdd6e63fa10a67e9a8521dfac743dd3e` |
| 本批 CI | https://github.com/NoGod3524/EXReader/actions/runs/39148719500 |
| 代码提交前基线 | `2fe46c6c288c3691ca0bf4caedaac90f87300b68`，其中原生实现为 `a1411afc9547c61950ecb424049a8f7be43b0d11` |
| 原生公开入口 | `include/exreader.h` |
| 能力细节 | [NATIVE_API.md](NATIVE_API.md) |
| 兼容与迁移 | [SDK_COMPATIBILITY.md](SDK_COMPATIBILITY.md) |
| 验证记录 | [NATIVE_VALIDATION.md](NATIVE_VALIDATION.md) |
| 性能口径与历史 | [PERFORMANCE.md](PERFORMANCE.md) |
| 版本映射与长期目标 | [VERSIONING.md](VERSIONING.md) |
| 本批原始数据与来源 | [metadata.json](benchmarks/0.18.0-pdf-nonisolated-windows/metadata.json)、[summary.json](benchmarks/0.18.0-pdf-nonisolated-windows/summary.json) |

代码提交和后续交接记录提交分开；最终记录提交只更新文档及采样，使用 `[skip ci]`；可用 `git log -1` 读取记录提交，不将其混作运行库构建提交。运行库对应代码提交以 metadata 的 `validated_code_commit` 为准。0.13–0.100 的旧内部步骤已归并为 0.13–0.18 功能里程碑；本批沿用 0.18.0，没有新增发行标签。

旧 UI 阅读器保留在 `codex/reader-app`，旧 MIT 版保留在 `codex/reader-0.1.1`，历史 preview-0.1.0/0.1.1 下载仍是旧阅读器。原生 C 核心与旧 UI、IndexedDB 数据及旧标注尚未连通。工作区中残留的 `dist/`、`src-tauri/`、`node_modules/` 等忽略目录不属于当前原生验收产物，恢复工作时不依赖它们。

## 产品目标与完成定义

目标是开放、可嵌入、尽量不绑定宿主或特定格式的 C 框架，覆盖 Windows、Linux、macOS、iOS/iPadOS、Android。文档树、文字位置、分页、固定页、资源、绘制和播放后端保持开放；UI、网络、系统语音、OCR 模型和受保护出版物适配按需接入。书库具有导入、编辑书名/封面、组织、阅读进度、标注和备份能力。

整体完成需要同时满足：

1. 每项支持能力都有公开接口、支持边界、可复现输入和对应回归；未支持特性返回明确结果。
2. EPUB 完整布局与页级续排在页数、源范围、命中、选择及 checkpoint 恢复上保持一致；缓存计费有上限。
3. PDF 透明、颜色、表单、安全擦除和 OCR 分别完成以下工作包的验收，不能用打开成功代替正确绘制或保存。
4. 三桌面通过测试与安装后 SDK 消费；手机库交叉编译之外还需要设备/模拟器运行、阅读视图与无障碍验证。
5. 发行附版本化接口、迁移说明、示例、许可、二进制和性能记录。当前仍是开发 SDK，未完成整体发行验收。

不以单一百分比表示总体进度：尚未冻结完整 CSS、PDF 扩展和脚本语言的兼容矩阵。下面按已交付能力和具有明确出口的工作包跟踪。

## 当前功能与边界

| 领域 | 已有实现 | 仍需完成 |
| --- | --- | --- |
| 流式文档格式 | TXT、严格 XHTML/HTML、FB2、EPUB、DOCX、RTF、MOBI/KF8；章节、树、资源、导航及各格式支持的样式/图片/链接 | HTML5 错误恢复、完整 Word 样式/打印版面、更多现实文件兼容；内置解析仍有整章/整文件路径 |
| 开放模型 | 通用文档构造、宿主分段 loader、随机读取源、布局输出、字体/图片/固定页绘制接入 | 章内增量解析；更完整的能力发现和面向应用的接口文档 |
| 字体与文字 | 宿主字体集、书内 @font-face、FreeType 栅格；OpenType、阿拉伯预处理、双向文字、Devanagari deva/dev2、竖排/混轴、ruby、可变轴 | 其他 Indic/东南亚脚本专用处理；跨字号附标等细节；系统字体发现由宿主处理 |
| Unicode 与断词 | Unicode 17 默认断行/字素、软连字符、语言模式/provider、NFC 与源字节映射、复合词、NOHYPHEN、拼写替换、改写后再匹配、WORD/LITERAL 大小写策略及检查点 | 更广语言词典实测和额外语言特例；不自动下载或内置所有词典 |
| 彩色字体 | COLR v0/CPAL、sbix PNG/JPEG、CBDT/CBLC PNG、cmap 14 变体 | COLR v1、SVG 字体，其他位图图像格式 |
| EPUB 布局 | CSS 子集、图片、指定/自动/fixed 列宽、top/middle/bottom/baseline、共享 solid/hidden 边框、合并格；float/clear、逐行绕排、长浮动与嵌套续排；高行/rowspan 单元格独立续排 | 完整 CSS；逐边/更多边框线型、重复表头、复杂百分比与溢出行为；auto 列宽和对齐测量首屏成本 |
| 页与位置 | 页级续排、缓存页数/字节预算、检查点、随机回读、命中/选择、EPUB CFI、TextQuote 锚点、书库重定位、全文索引 | 章内解析内存与时间；更广真实书籍定位回归；复杂转换后标注迁移 |
| PDF 阅读 | 固定页 API、对象/流解码、字体/Type3、路径/图像/内联图、文字几何/搜索/选择、Info/XMP、原生标注读取 | 更多 PDF 图像过滤器、Pattern/其他绘制特性；完整现实文档兼容语料与持续模糊测试 |
| PDF 认证 | Standard R2–R6 用户/所有者/空密码、RC4/AES、Crypt filter、对象流/元数据解密、可重试密码、权限快照 | 证书 PubSec、EFOpen 专用附件认证、加密写回；当前编辑入口拒绝加密输入 |
| PDF 色彩 | Device/Indexed/CalGray/CalRGB/Lab、ICCBased v2/v4 至 sRGB、Separation/All/None/DeviceN、Type 0 多输入线性/三次采样和 2/3/4 函数；CMYK/YCCK JPEG | 非 RGB 透明组色空间、OutputIntent、动态渲染意图、Matte 扩展、Pattern/套印等；完整印刷色彩 |
| PDF 合成 | 16 种 RGB 模式、页面隔离组、隔离和非隔离 Form/AP 组、填充/描边单一透明元素、通用扩展 sink、取消/预算/清理 | 挖空组、图形状态 Alpha/Luminosity SMask、组区域裁小、联合子像素覆盖 |
| PDF 编辑 | Text/Highlight/Underline/StrikeOut/Squiggly 新增/修改/删除与外观；元数据增量写回 | 其余标注编辑、AcroForm；增量删除保留历史原文，安全 redaction 尚未实现 |
| CBZ | PNG/JPEG、自然排序、ComicInfo、按页读取/解码、固定页/书库书签 | WebP/GIF/BMP/AVIF/TIFF 等页图，不支持时明确拒绝 |
| 书库 | SQLite 原书、元数据/封面、标签/收藏/已读、文本和固定页进度/标注、音频书签、精确去重、事务备份 | 旧 UI 数据迁移、流式大媒体导入、应用级同步/冲突和多设备体验 |
| 格式转换 | 六种正文格式；树和资源保真的 EPUB 导出、HTML 资源 ZIP；PDF/EPUB 原书元数据编辑 | 更多格式高保真往返、跨格式图片/复杂样式/批注保留；完整阅读格式与完整转换格式不是同一集合 |
| 音频 | 时间线/同步/后端、WAV/FLAC、可选 MP3/AAC/M4A/M4B、PCM、WSOLA 变速、六平台输出适配 | 移动音频会话、打断/后台行为及真机验收；EPUB 系统 TTS 尚未实现 |
| 应用 SDK | C/C++ 安装消费示例、Swift/JNI 基础适配、桌面运行及移动编译 | 可嵌入阅读视图、完整示例 App、TTS、无障碍、OPDS、授权 LCP；手机库可编译不等于手机阅读器可用 |
| OCR | 尚未实现 | 可选后端、语言模型、文字/字格位置、置信度、预算/取消、搜索选择和文本层 |

接口文档按历史开发顺序累积；早期 S 节中的限制可能由后文更新覆盖。当前表格跨页和断词替换现状以本表及 API 最后的补充节为准，后续应整理成统一版本化矩阵。

## 本批透明组的实现与验收

### 可使用的行为

- `exr_canvas_begin_group(..., flags=0, ...)` 从父背景开始；`EXR_GROUP_ISOLATED` 从透明背景开始。原 `begin_layer` 仍表示隔离层，两者用 `end_layer` 结束。
- `exr_draw_sink_ex` 在大小标记尾部增加 `begin_group`，优先调用新回调；隔离请求可回退旧 begin_layer，非隔离请求遇到旧消费者返回 `EXR_UNSUPPORTED`。任何 begin 都要求 end_layer。旧尺寸输入/输出和原无标记 sink 保持兼容。
- PDF Form/AP 的 I 缺省 false；非隔离 Form 继承色彩空间，显式 CS 拒绝为 `EXR_FORMAT`。页面总是隔离。调用者 opacity/blend 和继承 clip 在提交时各用一次。
- 非隔离组独立累计组 alpha，以浮点预乘 RGB/完整 alpha/组 alpha 计算背景移除；公开 bitmap 仍即时更新为 RGBA8。背景精度延迟读取，提交遍历脏区域。
- 状态单独堆分配，避免层数组扩容使父状态指针失效。abort/失败/取消释放工作区并恢复父作用域；失败不会返回部分渲染图。

### 已跑通的量化检查

| 检查 | 当前结果 |
| --- | --- |
| 本地 Windows CTest | 119/119 通过 |
| 原生混合断言 | 842,005 项通过 |
| 新非隔离 Form/AP 对参考像素最大差 | 1/255，预乘通道 |
| 八个场景参考掩码内最大差 | 2/255；测试容差保持 3/255 |
| 独立 Decimal 40 位规范参考 | 208 个 flat 样本与原始 PDFium 最大差 2；160 个 group 样本精确重现 |
| 低 alpha 累积 | 1/255 连续绘制 1,000 次，以及 1,000 次组提交，结果 alpha 250 |
| 深度与状态 | 32 层链、扩容、嵌套隔离/非隔离、fractional clip、父状态、空组、取消、abort 通过 |
| 安装消费 | C 渲染实际非隔离 PDF；C++ 新 API/回调与分页示例；JNI `-Xcheck:jni` 通过 |
| 历史输入不变 | 57 个旧混合参考文件、891 个旧 fixture 文件哈希一致 |
| 来源核验 | 1,237 个代码/输入 Git blob 哈希；75 个 manifest 文件；4 份运行库拷贝一致 |

原始 MuPDF/PDFium 输出与规范期望分开保存。PDFium 在这些 Form 场景隐式隔离；MuPDF 的半透明非分离混合和 masked image alpha 存在差异，后者为 204，规范/PDFium 为 200。参考实现使用 ISO 32000-1 11.4.4 的独立 Decimal 算法，不把外部程序的所有像素自动当作正确答案。

CI 已完成，准确代码 SHA 的六个作业全部成功：

| 作业 | 最终结果 |
| --- | --- |
| Windows / Linux / macOS | 各119项CTest通过；安装后C/C++/JNI、系统字体表格、表格内存与新增PDF性能采样通过；macOS另通过Swift |
| ASan / UBSan / leak | 116项CTest通过，无本次运行报告的sanitizer错误 |
| Android | ARM64共享引擎库构建与安装通过 |
| iOS / iPadOS | arm64设备与模拟器引擎库、对应Swift适配检查通过 |

ASan 的 116 项比桌面的 119 项少 3 项：`native-hyphen-compound-oracle`、`native-hyphen-replacement-oracle` 与 `native-hyphen-conditional-oracle` 通过 ctypes 把运行库载入未插桩的 Python，ASan 运行库无法这样装载（`CMakeLists.txt` 中的 `if(NOT EXR_SANITIZE)` 分支）；对应的原生 C 复合词、队列与预算回归仍在 ASan 下运行。

作业ID、起止时间和实际CTest汇总见 [ci.json](benchmarks/0.18.0-pdf-nonisolated-windows/ci.json)。当前无失败测试待修。

### 性能与轻量化现状

本地 Windows 11、GCC 16.2 Release、JNI ON、AAC OFF，DLL **5,662,055 bytes**，比前一批增加 **10,319 bytes**，约 **0.183%**。SHA-256：`6126a892cb2c579b6da79845596adac4019503ea053eff7cd9ba27303a182fc4`。本批无新增运行时依赖。

| scale 4 测试场景 | 打开 ms | 首画 ms | 重画 p50 ms | 重画 p95 ms | 进程峰值 bytes |
| --- | ---: | ---: | ---: | ---: | ---: |
| nonisolated | 0.5438 | 548.0304 | 582.2979 | 655.6072 | 40,259,584 |
| ap-nonisolated | 0.4595 | 23.8825 | 23.3268 | 27.0374 | 27,643,904 |
| flat | 0.3328 | 76.9589 | 77.0822 | 85.7585 | 34,193,408 |

每场景 3 个新进程，各首画后重画 8 次，表中为进程指标的中位数。RSS 包含 Python/ctypes 及运行库；这是同页重画，不是翻页。背景负载和磁盘缓存未控制。若干旧场景比历史样本慢，归因前需相同负载下新旧版本交替测量。该项属于未关闭的性能调查，不能将本批描述为所有既有路径性能已无回退。

非隔离组按整画布保留 **24 bytes/pixel**，隔离组为 **4 bytes/pixel**；活动子组工作像素合计和单组各限 64 MiB，另计基础页图、遮罩和状态。1000×1500 的单个非隔离组预留 36,000,000 bytes；2000×3000 需 144,000,000 bytes，将触及当前单组上限。脏区域提交尚未解决完整预留带来的高分辨率限制。缓存预算也不等于全进程内存上限。

内部比较过拆分和交错浮点缓冲，像素相同，拆分没有稳定时间收益且首画/峰值更差，最终保留一次分配的五 float 交错实现。实验数据位于 `interleaved-prototype/` 与 `buffer-comparison.json`，不能混作最终提交的基准。

最近 EPUB 大表格基线为 OpenType 优化批次的 1 MiB 单格、Arial、前 65 页、3 新进程中位数：fixed 首屏 40.75 ms、峰值 14,442,496 bytes、翻页 p50/p95 23.46/27.60 ms；auto 首屏 4434.30 ms、峰值 14,700,544 bytes；middle/bottom 首屏约 2.4 s。自动列宽和完整高度测量仍扫描输入。本批没有改动 EPUB 排版；这些是既有基线，不是本批重新采样结果。

## 后续工作包与量化出口

以下数字是接手后的验收目标。每包先做输入矩阵，再实现、验证、记录并提交；不按新增函数数量升级版本。保持现有 119 项桌面测试全绿，并将新增测试加入相应矩阵。

| 顺序 | 工作包 | 可量化验收条件 |
| --- | --- | --- |
| 1 | PDF 挖空透明组 | 至少 32 个原创组合场景，覆盖隔离/非隔离、16 模式、路径/文字/图像/嵌套与形状/透明度区别；内部实色探针预乘通道差不超过 3/255，边缘另定采样口径；取消/abort/深度/预算和旧 sink 行为各有回归 |
| 2 | 图形状态软遮罩 | Alpha、Luminosity 各至少 16 个场景，含 G/BC/TR、矩阵/BBox、嵌套和 q/Q/None 恢复；至少 8 个损坏/超限输入；与现有图像 SMask 分开验证，保存正确源坐标与组色空间 |
| 3 | 组区域裁小与内存 | 至少 12 个区域/变换/跨边界用例；小组面积≤画布 10% 时工作像素预留较整画布减少≥80%；所有既有探针像素一致。连续 1,000 次创建/提交/丢弃无泄漏；同机交替≥5 轮，普通六场景首画/重画 p95 回退>10% 必须调查。保留单独高分辨率成功/超限测试 |
| 4 | PDF 色彩和图像兼容 | 冻结包含 ICC 输入类、Intent、OutputIntent、Matte、group CS、ColorTransform 的支持矩阵；每个新增矩阵项≥3 正例、2 反例。至少 40 个新色彩/图像文件与独立参考；既有 CMYK/DeviceN/函数样本不退化。印刷套印另设明确子包 |
| 4a | PDF 认证与其他绘制兼容 | Standard R2–R6 保持已有全部回归；PubSec 证书、EFOpen、加密写回各自独立冻结范围，每项≥10个成功/错误凭据/损坏/权限/取消样本；密码/密钥无落库。另建立 Pattern/shading、图像过滤器和特殊字体待支持矩阵，每项≥3正例/2反例并记录外部绘制差异；不以现有 RGB 透明组完成替代整体 PDF 兼容 |
| 5 | EPUB CSS 与表格细节 | 从支持矩阵逐项补逐边/线型边框、重复表头、百分比与溢出等；每项≥8 个结构场景，横排/两竖排、合并格、分页/回读/检查点交叉覆盖；完整/分页的页数和源范围一致，坐标在同一计算路径下误差≤0.01 px，固定字体像素一致 |
| 6 | EPUB 性能和章内增量解析 | 对固定 10/50/100 MiB 单章语料记录首屏、峰值、翻页；分段/单章同时测顺序和随机。目标：缓存相同且数据体积从 10→100 MiB 时，解析驻留增量≤32 MiB；不能把映射/原始书字节混作解析工作区。对于 1 MiB auto 表格，先做≥5 轮交替测量，以首屏较当前基线降低≥50% 为优化出口；若保留全量测量算法则明确独立策略 |
| 7 | 其他文字脚本 | 逐脚本验收，优先 Bengali/Tamil/Telugu/Kannada/Malayalam/Thai/Khmer/Myanmar；每脚本≥50 个序列、实际字体与固定合成字体各一组，和固定版本 HarfBuzz 对照 glyph/cluster/advance；差异有规范依据，不能只比较截图；联动双向、断词、回退、选择与随机恢复 |
| 8 | COLR v1 与 SVG 字体 | COLR v1 按 paint 类型矩阵实现并覆盖每种类型正/反例、循环、深度/内存上限；SVG 明确安全元素/资源子集与禁外部访问；至少 30 个渲染场景并与独立参考比较，横竖排/透明度/命中不退化 |
| 9 | PDF AcroForm | 先冻结字段类型/继承/校验范围；至少 30 个字段/嵌套/widget/选项/多页文件；编辑→保存→重开后值和外观一致，取消/失败不覆盖原文件。动作/JS 另列能力，不默认执行 |
| 10 | 安全 redaction | 预览和应用分离；应用重写并清除历史修订，至少 30 个含文字/图像/Form/标注/表单/元数据的敏感样本。重开、文本提取、对象图和解压流/原始字节检查均找不到埋入标记；所有引用副本/元数据有处理策略，不能以覆盖黑框或增量删标注通过 |
| 11 | OCR | 可选后端与语言模型，不进入默认轻量包；至少 30 页中英文/旋转/混合原生文字语料，报告 CER/WER 与字格定位误差；在声明的300dpi清晰印刷测试集上，英文CER≤3%、中文CER≤5%，其余扫描条件独立报告；取消/预算各有测试；坐标往返、搜索、选文/标注无重复层 |
| 12 | 高保真转换和数据迁移 | 每个声明支持的来源→目标组合≥10 个含图片/表格/链接/字体/脚注样本，报告保留/降级/拒绝项目；回读比对语义树、资源哈希、源链接与图片；旧 UI 数据迁移独立做版本/回滚与重复导入测试 |
| 12a | CBZ 更多图像格式和大媒体 | 按 WebP/GIF/BMP/AVIF/TIFF 逐格式交付；每项≥10个颜色/透明/尺寸/损坏样本，帧/页选择有明确规则，不静默丢页。大音频/原书的流式导入需以1 GiB媒体验证，新增缓冲峰值≤32 MiB，事务失败与重复导入不留半条书籍 |
| 13 | 嵌入视图和应用 | 各平台最小应用可导入/书架/阅读/选择/标注/回读；桌面3平台运行，Android 至少1模拟器+1真机，iPhone/iPad 各1设备或明确区分模拟器验收；旋转/缩放/触摸/后台/生命周期≥20条手工步骤可复现 |
| 14 | TTS 和无障碍 | EPUB 稳定文本位置→朗读片段→高亮→续播闭环；至少20段含链接/ruby/双向/注释用例。VoiceOver、TalkBack 和桌面至少一屏幕阅读器逐项验证书架、导航、选文、阅读顺序；系统语音通过宿主适配 |
| 15 | OPDS 与 LCP | OPDS1/2 各≥10个分页/搜索/认证/获取/坏数据样本；网络与凭据由宿主控制。LCP 使用授权测试出版物完成打开/失效/续期/错误密码等路径，明确官方实现许可与分发条件；不把未授权 DRM 解密纳入核心 |
| 16 | 发行 SDK 和可靠性 | 统一当前支持矩阵、版本化文档和迁移实例，全部六个 CI 作业通过；增加解析/字体/布局的 sanitizer fuzz 目标，每目标固定种子持续≥24 CPU 小时且所有 crash 入回归。发布前验证默认及裁剪配置符号/安装消费，并附6平台产物、依赖许可和基准 |

工作包 3 是轻量化优先项，可在 1/2 的架构需要时提前，但一次只交付一包并保留可复现对照。执行前先做两项纯重构并保持 119 项全绿：拆分 `src/pager.c` 的 `advance`（339 行单函数）与把 108 份自带 `main`/`CHECK` 的测试脚手架收敛为共享头文件。发行支持以冻结的矩阵条目为单位。

## 总体验收的语料与标准目标

在功能包之外，建立固定、许可可分发的至少1,000份PDF、500本EPUB及每种其他声明格式至少30份文件的兼容语料。逐份记录来源、散列、预期能力、打开/渲染/提取/保存结果和失败类别；声明支持范围内的样本应100%通过，保留全部失败回归，不能剔除困难样本来提高通过率。渲染差异以固定字体、版本和采样口径比较，边缘抗锯齿与正文/颜色语义分别统计。

EPUB以EPUB3.3阅读链路、CSS2.2布局与所声明的CSS Text/Writing Modes/Ruby/Fonts模块为支持矩阵基准，列出每条规范行为的用例与实现状态。完整CSS目标通过扩展此矩阵推进，不能用一个总开关宣告完成。发行前给出矩阵条目总数/通过数及真实书籍失败表。PDF以ISO32000条目矩阵及上述四个对标项目的固定版本行为作对照，规范差异单独记录。

## 未来各批共同验收

- 代码、当前 API、迁移、支持范围、回归和性能记录同时提交。源码 SHA、运行库 SHA、输入/字体 SHA、工具版本和原始样本必须能对应同一代码提交。
- 保持 ABI 1 的既有符号、枚举值和无大小标记记录的大小/偏移；仅向大小标记输入/输出增加可选尾部。关闭可选组件仍保留符号并报告不可用。
- Windows/Linux/macOS 各通过完整 CTest 和安装后 C/C++/JNI；macOS Swift；ASan/UBSan/leaks；Android ARM64、iOS/iPadOS device/simulator 库及 Swift 检查。新增测试数不同于本次计数时列明原因。
- EPUB 对比完整/续排、缓存驱逐、随机回读、checkpoint、源区间/CFI、选择/命中、横竖排，禁止只验顺序第一页。
- 每个新分配路径计费、检查溢出，测试超限/取消/失败清理；记录预算是否包含字体、原书、解析树、临时工作区和宿主。核心同步调用，无后台工作线程；同一可变句柄及共享 archive 图由宿主串行，回调不得释放/重入当前对象。借用视图和返回独立对象按 API 的所有权规则释放。
- 时间使用同机、同输入/字体/配置、交替新旧版本≥5轮，给出中位数/p95及所有样本；峰值与常驻内存分开，重绘与真正翻页分开；体积给出依赖开关。

## 源码定位

| 路径 | 接手用途 |
| --- | --- |
| `src/canvas.c`、`canvas_internal.h`、`blend.c` | 组生命周期、计费、背景移除、组 alpha、脏区域、失败清理 |
| `src/vector.c`、`affine_image.c`、`pixels_internal.h` | 路径/字形/图像的紧凑与精度像素路径，裁剪/覆盖率 |
| `src/pdf_content.c`、`pdf_internal.h` | Group/BM 解析、Form 作用域、图形状态和预算 |
| `src/pdf_paint.c`、`pdf_annotation_paint.c` | PDF→扩展 sink、页面隔离、原生标注 AP 与回调转发 |
| `tests/test_blend.c`、`test_abi.c`、`test_pdf_appearance.c` | 本批像素/解析/预算/接口回归 |
| `tests/fixtures/pdf-blend/` | 原创 PDF、mask、预期 RGBA、外部原始像素、manifest/oracle |
| `tools/pdf_group_reference.py` | 独立 Decimal 规范参考及可运行核验 |
| `tools/generate_pdf_blend_fixtures.py` | 原创场景及开发期参考生成；外部工具仅用于此流程 |
| `tools/generate_knockout_fixtures.py` | 42 个挖空场景与 Decimal(40) 独立参考，`--check` 可重现 |
| `tools/benchmark_pdf_blend.py` | 单页打开/首画/重画/峰值，支持 --case 与新进程重复 |
| `tests/fuzz_parse.c`、`docs/FUZZING.md` | 确定性解析器 fuzz 驱动（种子变异、崩溃输入落盘、CI `fuzz` 作业） |
| `src/flow.c`、`pager.c`、`pager_table.c`、`floats.c`、`layout.c` | EPUB 行排版、检查点、表格/浮动续排与布局 |
| `src/hyphen.c`、`display_bidi.c`、`opentype.c` | 断词/改写/显示方向、字体 lookup |
| `bindings/swift/`、`bindings/jni/`、`examples/`、`tests/sdk_cpp/` | 安装后宿主和语言适配 |
| `cmake/deps.cmake`、`.github/workflows/native.yml` | 固定依赖、安装/跨平台/性能与 sanitizer 流程 |

## 构建与测试复现

### 通用干净环境

需要 C11 编译器与 CMake≥3.24；首次配置会按固定 URL/SHA 下载组件。SDK 默认不开 AAC；CI 开 AAC，测试数量和 DLL 体积可能不同。字体由宿主提供；不要提交系统字体。

```sh
cmake -S . -B build/native -DCMAKE_BUILD_TYPE=Release -DEXR_BUILD_JNI=ON
cmake --build build/native --config Release --parallel 4
ctest --test-dir build/native -C Release --output-on-failure
cmake --install build/native --config Release --prefix stage
cmake -S stage/examples -B build/sdk-example -DEXR_SDK=/absolute/path/to/stage -DCMAKE_BUILD_TYPE=Release
cmake --build build/sdk-example --config Release --parallel 4
cmake -S tests/sdk_cpp -B build/sdk-cpp -DEXR_SDK=/absolute/path/to/stage -DCMAKE_BUILD_TYPE=Release
cmake --build build/sdk-cpp --config Release --parallel 4
python tools/pdf_group_reference.py tests/fixtures/pdf-blend
```

SDK 消费使用 `find_package(EXReader 0.19.0 EXACT CONFIG REQUIRED)`，防止选到旧编号更大的开发包。Windows MSVC 是 CI 路径；本地 MinGW 通过 ASCII junction 避开中文路径。动态库分别为 MSVC `exreader.dll`、MinGW `libexreader.dll`、Linux `libexreader.so`、macOS `libexreader.dylib`。

### 本机已验证环境

| 位置 | 路径 |
| --- | --- |
| 工作区 | `C:/Users/Oscar/OneDrive/文档/ChatGPT/EXReader` |
| ASCII 源码 junction | `C:/Users/Oscar/.codex/build-links/exreader-c` |
| Release 构建 | `C:/Users/Oscar/.codex/build/exreader-c` |
| 安装 SDK | `C:/Users/Oscar/.codex/build/exreader-crypto-stage` |
| 安装 C / C++ 宿主 | `C:/Users/Oscar/.codex/build/exreader-hyphen-host` / `exreader-hyphen-cpp` |
| JDK | `C:/Users/Oscar/.codex/build/exreader-jdk/jdk-21.0.12.1+1` |
| JNI classes | `C:/Users/Oscar/.codex/build/exreader-jni-java` |
| 可选开发参考模块 | `C:/Users/Oscar/.codex/tmp/exreader-pdf-blend-oracle` |

目录名称中的 crypto/hyphen 仅为历史沿用。工具版本：本地 GCC 16.2、Python 3.14.7、JDK21；参考生成使用 PyMuPDF/MuPDF 1.28.2、pypdfium2 5.14.0/PDFium 156.0.8076.0。ISO 参考为 [PDF32000_2008.pdf](https://opensource.adobe.com/dc-acrobat-sdk-docs/pdfstandards/PDF32000_2008.pdf)，透明组背景移除/隔离/挖空/页面分别见 11.4.4–11.4.7。

```powershell
cmake --build C:/Users/Oscar/.codex/build/exreader-c --parallel 4
ctest --test-dir C:/Users/Oscar/.codex/build/exreader-c --output-on-failure --parallel 4
cmake --install C:/Users/Oscar/.codex/build/exreader-c --prefix C:/Users/Oscar/.codex/build/exreader-crypto-stage
cmake --build C:/Users/Oscar/.codex/build/exreader-hyphen-host --parallel 4
cmake --build C:/Users/Oscar/.codex/build/exreader-hyphen-cpp --parallel 4
& C:/Users/Oscar/.codex/build/exreader-c/exreader-blend-test.exe C:/Users/Oscar/.codex/build-links/exreader-c/tests/fixtures/pdf-blend
& C:/Users/Oscar/.codex/build/exreader-hyphen-cpp/exreader-cpp-test.exe C:/Users/Oscar/.codex/build/exreader-crypto-stage/examples/fonts/primary.ttf C:/Users/Oscar/.codex/build/exreader-crypto-stage/examples/books/table-fragments-12.epub
& C:/Users/Oscar/.codex/build/exreader-hyphen-host/exreader-fixed-example.exe C:/Users/Oscar/.codex/build-links/exreader-c/tests/fixtures/pdf-blend/nonisolated.pdf C:/Users/Oscar/.codex/tmp/exreader-nonisolated-installed.png
```

每条构建/测试命令成功后再执行依赖它的下一步。编译时不修改源码、头文件、fixture、构建脚本等输入。性能采样时不并行跑编译和测试。

```powershell
$env:PATH='C:/Users/Oscar/.codex/build/exreader-crypto-stage/bin;'+$env:PATH
& 'C:/Users/Oscar/.codex/build/exreader-jdk/jdk-21.0.12.1+1/bin/java.exe' -Xcheck:jni '-Djava.library.path=C:/Users/Oscar/.codex/build/exreader-crypto-stage/bin' -cp C:/Users/Oscar/.codex/build/exreader-jni-java org.exreader.Smoke C:/Users/Oscar/.codex/build/exreader-crypto-stage/examples C:/Users/Oscar/.codex/tmp/exreader-nonisolated-jni
python tools/benchmark_pdf_blend.py C:/Users/Oscar/.codex/build/exreader-c/libexreader.dll tests/fixtures/pdf-blend C:/Users/Oscar/.codex/tmp/exreader-next-pdf-benchmark --runs 3 --scale 4
```

正常 CTest 无需安装外部 PDF 参考程序；Decimal reference 只用标准库。只有重新生成原始外部参考时才使用：

```powershell
python tools/generate_pdf_blend_fixtures.py --oracle-module-dir C:/Users/Oscar/.codex/tmp/exreader-pdf-blend-oracle
```

生成后核对 manifest 与历史未改输入，不能无差别接受外部参考变动。来源哈希从提交的 Git blob 读取，不能将 CRLF 工作区字节和 Git LF 字节混用。四份本地 DLL 必须与 benchmark/runtime hash 一致；避免 C++/JNI 从旧目录装入旧 DLL。

## CI 产物与保存

本次 workflow 上传三桌面安装包、Android ARM64、iOS/iPadOS device/simulator 库和三桌面性能记录。workflow 现共七个作业：上面六个之外新增 `fuzz`（ASan/UBSan + `EXR_BUILD_FUZZ=ON`，每次推送 20 万次种子迭代，失败时上传触发输入）；开启 `EXR_BUILD_FUZZ=ON` 的构建本地 CTest 为 120 项（新增 `native-fuzz-smoke`）。可用 `gh run download 39148719500 --dir <本地目录>` 获取全部产物，或按 artifact 名称筛选。CI 产物有平台保留期，不代替正式 release；已提交的原始性能和来源记录长期随 Git 保留。提交/发布时不要将本地 AAC OFF 的5.66 MB库体积当作所有 CI 配置的体积。

## 依赖与许可

核心沿用固定版本 C 组件：FreeType 2.14.1、Expat 2.9.0、miniz 3.1.2、SQLite 3.54.0、固定 stb 提交。可选 minimp3、FAAD2、LittleCMS 2.19.1、Mbed TLS 3.6.7 的最小算法子集。下载 URL/哈希以 `cmake/deps.cmake` 为准；许可见 [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md) 和 `licenses/`。FreeType、CMS、密码学和可选音频解码并非全部从零自研。MuPDF/PDFium 仅作为开发参考，不链接/打包，不复制其实现。

默认 FTS/MP3/ICC/PDF_CRYPTO 开，AAC 关；JNI 默认随 Android 开，其他平台可显式启用。裁剪开关不是全模块微内核分拆，减少默认依赖仍可另做体积目标。OCR/词典模型/网络/TTS/LCP 不应无条件进入核心分发。

## 恢复工作与停止规则

1. 用户要求继续后，先读取本文件、API 最后透明组节、VERSIONING 后续目标，以及当前 `git status`/HEAD。核对新的交接记录是否改变代码基线。
2. 第一包默认为挖空组：先建立 shape/alpha 与初始 backdrop 的规范参考，再选最小通用内部表示；不得把现有非隔离组简单清空背景当作挖空。
3. 保留 24 bytes/pixel、整画布分配和 64 MiB 上限的约束，评估是否需要先做裁小；同一批只验收一个完整行为。
4. 完成共同验收后提交、推送、等准确 SHA 的六个 CI 作业结束，再记来源与 handoff。若 CI 失败，修复并重跑相关验证；保留失败原因与最终结果。
5. 不自动添加 UI、切换许可证、提升版本、创建新分支/任务或引入新后端。新增依赖按许可、体积与是否可选决定。按现有指示不派生子代理。
6. 本批结束后停止编码与自动续做，现有全局目标保持暂停。下一次从单个工作包继续。停止时没有本批仍在运行的编译、测试或CI任务，也没有活动子代理；工作区应为干净状态。

## 当前未关闭问题

1. 非隔离主场景首画约548 ms，部分旧场景比历史采样慢，缺少受控交替归因。下一轮优化从此处保留对照数据。
2. 整画布24字节预留导致大页面单组超过64 MiB时拒绝渲染，不能仅提高预算后宣称轻量化完成。
3. auto表格和middle/bottom精确高度测量需扫描完整输入，存在秒级首屏成本；解析和双向数据也不由页面缓存上限包住。
4. 当前公开文档含历史步骤叙述；已新增 [SUPPORT_MATRIX.md](SUPPORT_MATRIX.md) 作为单一当前状态入口，发行前仍需把早期“未支持”段落并入该表并删除重复叙述。
5. iOS/iPadOS和Android当前验证层级仍是库编译/适配检查；移动视图、后台音频、手势、无障碍和真机运行尚未交付。
6. CI目前提示checkout/upload-artifact v4使用的Node20已退役并强制在Node24运行；当前任务成功，后续可单独升级actions并跑相同矩阵。
7. 本批验证集中于透明组及完整现有回归；安全redaction、OCR、完整CSS与全部PDF文件兼容仍按上面的独立目标推进。

## 工作量估计

单人或单模型持续工作量估计：挖空组、两种软遮罩、区域裁小各约数天，互相耦合时需合并评估；将 PDF/EPUB 常用路径推进到较完整的可用水平通常仍需数周到数月。完整多平台应用、广泛现实文件兼容与长期稳定性按月计。每完成一个包，用实际失败样本和 CI/采样耗时重新估算，不把生成 token 速度直接换算成完工速度。
