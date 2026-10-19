# EXReader 开发状态与路线

更新日期：2026-10-19。当前为无 UI 的 C11 SDK，MIT，版本 **3.33.0**、ABI epoch **1**、书库 schema **6**。

仓库：https://github.com/NoGod3524/EXReader 。开发分支：`codex/framework`。本次修复与验证入口见 [HANDOFF-NEXT.md](HANDOFF-NEXT.md)，审计发现见 [AUDIT-2026-10-19.md](AUDIT-2026-10-19.md)。

旧阅读器保留于 `codex/reader-app`，旧 MIT 版保留于 `codex/reader-0.1.1`。其 UI、IndexedDB 数据与旧标注尚未接入 C SDK。

## 目标与完成定义

提供开放、可嵌入、尽量不绑定宿主和格式的 C 框架，面向 Windows、Linux、macOS、iOS/iPadOS 和 Android。文档树、位置、分页、资源和绘制后端向宿主开放；网络、系统字体、语音及应用界面由适配层提供。

每项能力以接口、支持矩阵、可复现输入和回归结果验收；打开成功不能代替正确绘制、保存或定位。手机交叉编译与设备运行分别记录。当前仍是开发 SDK，后续目标没有全部完成。

## 当前能力

| 领域 | 已有实现 | 主要缺口 |
| --- | --- | --- |
| 文档与模型 | TXT、XHTML/HTML、FB2、EPUB、DOCX、RTF、MOBI/KF8；通用构造、分段 loader、随机读取源、树与资源 | HTML5 错误恢复、完整 Word 版面、章内增量解析 |
| 排版与位置 | CSS 子集、float/clear 和逐行绕排、表格列宽/合并/垂直对齐/逐边边框/重复表头；页级续排、缓存字节预算、检查点、CFI、TextQuote、命中选择 | 完整 CSS、border-spacing、复杂百分比与溢出、大章解析成本 |
| 文字与字体 | Unicode17、双向、OpenType、阿拉伯、Devanagari、竖排、ruby、可变轴、词典/provider 断词；COLRv0、sbix、CBDT、cmap14 | 更多 Indic/东南亚脚本、COLRv1、SVG 字体、更多语言实测 |
| PDF | 固定页与文字几何、搜索选择、字体/Type3、图像与 CMYK/YCCK JPEG、渐变2–7、ICC v2/v4、16种混合、隔离/非隔离/挖空组、软遮罩 | 审计列出的组合错误和限界；Pattern、JPX/JBIG2、OutputIntent、完整印刷色彩 |
| PDF 认证与编辑 | Standard R2–R6、RC4/AES、可重试认证、权限快照；基础标注与元数据增量保存 | PubSec、EFOpen、加密写回、AcroForm、安全 redaction；增量删除保留历史原文 |
| 色彩修复批次 | 完整默认 CMYK ICC 压缩内嵌；修正减色混合、网格记录/插值、Matte 处理顺序、透明度与遮罩传递 | 图像/渐变仍经 RGBA 进入 CMYK 组，墨色分离不保真；显式 RGB 子组切换未完成 |
| 书库与转换 | SQLite 原书/封面/元数据/标签/收藏/进度/标注/音频书签/备份；六种正文转换，EPUB和HTML资源导出 | 大媒体流式导入、同步、旧 UI 迁移、更多高保真往返 |
| CBZ与音频 | CBZ PNG/JPEG、自然排序、ComicInfo；WAV/FLAC、可选MP3/AAC/M4B、时间线、WSOLA、输出适配 | 更多CBZ图像、移动音频会话/后台/真机验收 |
| 应用 SDK | C/C++消费示例、Swift/JNI基础适配；三桌面历史CI与移动库交叉编译 | 嵌入视图、完整应用、TTS、无障碍、OPDS、LCP、OCR |

精确支持范围见 [SUPPORT_MATRIX.md](SUPPORT_MATRIX.md)。历史性能和验证记录保留于 [PERFORMANCE.md](PERFORMANCE.md) 与 [NATIVE_VALIDATION.md](NATIVE_VALIDATION.md)，历史结果以对应代码 SHA 和运行库哈希为准。

## 后续工作包与量化出口

下表为目标清单；已有部分实现不等于整包完成。WP1–WP5 的现状以支持矩阵和审计记录为准。优先关闭已复现错误，再继续 WP4a。保持现有全量测试并增加针对性回归。

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


## 总体验收的语料与标准目标

在功能包之外，建立固定、许可可分发的至少1,000份PDF、500本EPUB及每种其他声明格式至少30份文件的兼容语料。逐份记录来源、散列、预期能力、打开/渲染/提取/保存结果和失败类别；声明支持范围内的样本应100%通过，保留全部失败回归，不能剔除困难样本来提高通过率。渲染差异以固定字体、版本和采样口径比较，边缘抗锯齿与正文/颜色语义分别统计。

EPUB以EPUB3.3阅读链路、CSS2.2布局与所声明的CSS Text/Writing Modes/Ruby/Fonts模块为支持矩阵基准，列出每条规范行为的用例与实现状态。完整CSS目标通过扩展此矩阵推进，不能用一个总开关宣告完成。发行前给出矩阵条目总数/通过数及真实书籍失败表。PDF以ISO32000条目矩阵及上述四个对标项目的固定版本行为作对照，规范差异单独记录。

## 构建、兼容与数据口径

快速验证见 [HANDOFF-NEXT.md](HANDOFF-NEXT.md)。通用新构建：

```sh
cmake -S . -B build/native -DCMAKE_BUILD_TYPE=Release
cmake --build build/native --config Release --parallel 4
ctest --test-dir build/native -C Release --output-on-failure
cmake --install build/native --config Release --prefix stage
cmake -S stage/examples -B build/sdk-example -DEXR_SDK=/absolute/path/to/stage
cmake --build build/sdk-example --config Release --parallel 4
```

公开无大小标记结构体维持原大小/偏移。扩展回调使用 `struct_size`，包装 sink 逐项转发可选回调。取消、预算和失败清理纳入回归。ToUnicode 保持严格校验。

历史基准中的本机目录已归一化为 `${WORKSPACE}` 和 `${LOCAL_BUILD}` 标签；它们表示原记录路径的角色，不是新的实际测量位置。测量值、输入/字体/运行库哈希及原代码 SHA 保持原值。旧源码清单中的 Git blob 哈希仍指向当时提交，不能用来验证本次文档改动。

## 源码地图

| 路径 | 用途 |
| --- | --- |
| `src/canvas.c`、`blend.c`、`vector.c`、`affine_image.c` | 画布、组、合成、路径和图像 |
| `src/pdf_content.c`、`pdf_paint.c`、`pdf_annotation_paint.c`、`pdf_softmask.c` | PDF解释、绘制、外观和遮罩 |
| `src/pdf_color.c`、`icc.c`、`pdf_shading_mesh.c` | 色彩转换与网格 |
| `src/flow.c`、`pager.c`、`pager_table.c`、`floats.c` | EPUB排版、表格、浮动和续排 |
| `tests/test_render_audit.c`、`tools/generate_render_audit_fixtures.py` | 本次审计回归及原创输入 |
| `bindings/`、`examples/`、`tests/sdk_cpp/` | 语言适配与安装消费 |
| `.github/workflows/native.yml` | 桌面、sanitizer、fuzz、移动构建 |
