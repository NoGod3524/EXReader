# PDF 色彩与图像支持矩阵（工作包 4）

本表是 WP4 的验收底稿：每一项都必须有代码位置、正例与反例、以及独立参考的比对方式。
状态只有三种：**支持**（有正例与反例）、**部分**（能解析但结果与参考有已知差异）、**未支持**（明确拒绝或忽略）。

## 当前状态（2026-10-18，逐项按代码核对）

| 项 | 状态 | 代码位置 | 缺口 |
| --- | --- | --- | --- |
| 设备色空间 DeviceGray/RGB/CMYK | 支持 | `pdf_colorspace.c` | — |
| Indexed / Separation / DeviceN / All / None | 支持 | `pdf_colorspace.c` | 渐变色（Pattern）不支持 |
| CalGray / CalRGB / Lab | 支持 | `pdf_colorspace.c` | — |
| ICCBased v2/v4 → sRGB | 支持 | `icc.c` | 每种渲染意图一个 littleCMS 变换 |
| 渲染意图 `/RI`（ExtGState） | **支持** | `pdf_content.c` `apply_ext_state` | 四种意图与 MuPDF 差 ≤1/255；未知名字 `EXR_FORMAT` |
| 图像 `/Intent` | **支持** | `pdf_image.c` | 单图覆盖图形状态意图；未知名字/非名字 `EXR_FORMAT` |
| 文档 `/OutputIntents` | **未支持** | 无解析 | 见下文调查：缺独立参考，暂缓 |
| 图像 `/Matte` | **支持** | `pdf_image.c` | 灰度/RGB/CMYK 四分量；分量数或取值不符仍 `EXR_FORMAT` |
| 透明组 `/Group /CS` | 部分 | `pdf_content.c`、`canvas.c` | DeviceRGB、DeviceGray 支持；**DeviceCMYK 与 ICCBased 组仍 `EXR_UNSUPPORTED`** |
| Pattern / shading（`sh`） | **未支持** | `pdf_content.c` | 有效操作符但未实现，报 `EXR_UNSUPPORTED`（不再误报 `EXR_FORMAT`） |
| 图像过滤器 | 部分 | `pdf_objects.c` | Flate/LZW/DCT + PNG 预测器；**JBIG2/JPX/CCITT 未支持** |
| JPEG `ColorTransform` | 部分 | `pdf_image.c:152` | 只接受 YCbCr 默认；模板/索引覆盖明确拒绝 |
| 套印（Overprint） | 未支持 | — | 另立子包 |

## 语料证据（2026-10-18，pdf.js 样本 120 份）

| 次数 | 现象 |
| ---: | --- |
| 7 | `PDF group blending space requires DeviceRGB` |
| 2 | `PDF image dictionary, samples or Decode array` 拒绝 |

## 验收节奏（每项都要 3 正例 + 2 反例）

1. **渲染意图**：解析 `/RI`（ExtGState）与图像 `/Intent`，把意图传进 ICC 变换；正例＝同一 CMYK 图在四种意图下的输出与 littleCMS 参考一致，反例＝未知意图名拒绝、坏名字长度拒绝。
2. **OutputIntent**：无 `DefaultRGB` 时按文档输出意图的 ICC 解释 DeviceCMYK；反例＝意图流损坏、`/S` 不是 `GTS_PDFA1` 等。
3. **CMYK matte**：`/Matte` 四分量，反例＝分量数不符、值越界。
4. **透明组色空间**：DeviceGray 先做（可分离混合模式等价），CMYK 需要真正的组空间混合；非可分离模式（Hue/Saturation/Color/Luminosity）在灰度组下要单独给结论。
5. **图像过滤器**：JBIG2 与 JPX 各自独立子包，先出待支持矩阵再实现。

## 原则

- 不允许“能画但画错”静默通过：解析到但无法正确渲染的参数，要么实现，要么显式 `EXR_UNSUPPORTED`；
- 每个新矩阵项都必须能在 `tests/fixtures/pdf-color/` 找到正例与反例，并与 littleCMS / PyMuPDF 的独立输出比对；
- 既有 CMYK/DeviceN/函数样本的像素结果不得退化。

## 已完成项：渲染意图（2026-10-18）

`/RI` 现由 ExtGState 解析进绘制状态，ICC 转换按意图选择变换；相对比色启用黑点补偿（与 MuPDF 一致）。

| 意图 | EXReader | MuPDF 1.28.2 | 差 |
| --- | --- | --- | ---: |
| RelativeColorimetric | (175,74,53) | (174,74,53) | 1 |
| Perceptual | (176,81,63) | (175,80,63) | 1 |
| Saturation | (176,81,63) | (175,80,63) | 1 |
| AbsoluteColorimetric | (168,77,61) | (167,76,60) | 1 |

反例：`/RI /Bogus` 与 `/RI 42` 均在渲染时报 `EXR_FORMAT`（打开时不读，因为 ExtGState 只在应用时求值）。
测试：`native-pdf-intent`，夹具 `tests/fixtures/pdf-color/intent-*.pdf`（内嵌 SWOP CMYK ICC）。

## 已完成项：CMYK 图像 matte（2026-10-18）

`/Matte` 之前只接受灰度与 RGB，CMYK 基图直接拒绝。现在四分量 matte 会走与采样相同的色空间
转换路径得到 RGB，再交给仿射图像的反预乘。

| 用例 | 期望 | 结果 |
| --- | --- | --- |
| `matte-gray.pdf` | (128,128,128) 不透明 | 通过 |
| `matte-rgb.pdf` | (200,60,40) | 通过 |
| `matte-cmyk.pdf` | (205,45,65)（CMYK 20/180/160/30） | 通过 |
| `matte-bad-count.pdf`（两分量 matte） | `EXR_FORMAT` | 通过 |
| `matte-bad-range.pdf`（1.5 越界） | `EXR_FORMAT` | 通过 |

测试：`native-pdf-matte`。**未覆盖**：半透明边缘上 matte 反预乘的数值（由既有 RGB matte 场景覆盖），
以及 matte 与渲染意图的交叉。

## 已完成项：DeviceGray 透明组（2026-10-18）

组内绘制颜色先按线性光 Rec.709 权重降到亮度、再经 sRGB 传输函数编码；图像同样逐像素降为灰度。
灰度值因此与 MuPDF 对齐：纯红在灰度组里 EXReader 输出 (127,127,127)，MuPDF 为 (129,129,129)。

| 用例 | 期望 | 结果 |
| --- | --- | --- |
| `groupgray.pdf`（DeviceGray 组，红填充） | 输出为灰，且 ≈129 | 通过（127） |
| `grouprgb.pdf`（DeviceRGB 组，红填充） | 仍是 (255,0,0) | 通过 |
| `groupcmyk.pdf`（DeviceCMYK 组） | `EXR_UNSUPPORTED` | 通过 |

**语料影响**：pdf.js 120 份样本里仍有 7 份因组色空间失败，但核对后它们用的是
`/DeviceCMYK` 或间接 `ICCBased`，不是灰度——所以本次改动没有让语料通过率变化（45/120）。
CMYK 与 ICC 组空间需要真正的组内色彩混合，列入后续子包。

## 已完成项：图像 `/Intent`（2026-10-18）

图像字典的 `/Intent` 会覆盖图形状态的意图，只作用于该图。与 MuPDF 1.28.2 完全一致：

| 用例 | EXReader | MuPDF |
| --- | --- | --- |
| 无 `/Intent`（默认相对比色） | (175,74,53) | (175,74,53) |
| `/Intent /Perceptual` | (175,81,63) | (175,81,63) |
| `/Intent /Saturation` | (175,81,63) | (175,81,63) |
| `/Intent /Bogus`、`/Intent 42` | `EXR_FORMAT` | — |

顺带修掉一个自己引入的缺陷：加入 `intent` 字段时绘制状态是 `calloc` 出来的，默认值成了 0（感知），
而 PDF 的默认是相对比色（1）。这个偏差是**与 MuPDF 对照时才暴露的**——默认路径的像素从
(175,81,63) 变回 (175,74,53)。

## 调查记录：`/OutputIntents`（2026-10-18，未交付）

目标：当文档带 CMYK 输出意图时，用它的 ICC 解释 DeviceCMYK，而不是 `1-min(1,c+k)`。

实现到一半发现两个问题，回退后记录：

1. **缺少独立参考**：用 SWOP ICC 构造带 `/OutputIntents` 与不带的两份 PDF，MuPDF 1.28.2 的渲染
   结果是**完全相同的 (184,79,61)**——它并没有用输出意图解释 DeviceCMYK。没有参考结果，就无法
   验证我们做得对不对。
2. **对象链解析**：`root` 与 `/OutputIntents` 数组都能取到，但数组首元素的 `exr_pdf_resolve` 返回
   `EXR_PDF_NONE`。这需要在解析器层面查清，而不是在色彩代码里绕过。

另外，`k` 运算符的颜色在内容解释器里以 CMYK 原值保存、到绘制时才转 RGB；接入文档 ICC 会改变
**所有** DeviceCMYK 的输出，属于全局行为变更，必须有独立参考才能做。

结论：暂缓，直到找到会对输出意图做出反应的参考实现，并把对象链解析的返回 `NONE` 查清。


## 已完成项：轴向渐变（type 2，2026-10-18）

`sh` 从“直接报错”改为渲染：把 `/Function` 在 0..1 上采样成 512×1 的 RGBA 位图，
按 `/Coords` 建立仿射矩阵画进画布，`/Extend` 为真时两端各延伸一个轴长的常量色。
裁剪、alpha、混合模式、软遮罩都走既有绘制路径，没有新增旁路。

| 用例 | EXReader（像素中心采样） | MuPDF 1.28.2（像素角采样） |
| --- | --- | --- |
| `shading-axial` x=0 | (247,0,8) | (255,0,0) |
| x=8 | (120,0,135) | (127,0,127) |
| x=15 | (8,0,247) | (0,0,255) |
| `shading-axial-noextend` 段外 | 白 | 白 |
| 径向 type 3 | `EXR_UNSUPPORTED` | 渲染 |
| `/Coords` 只有两个数 | `EXR_FORMAT` | — |
| 退化坐标（起止相同） | `EXR_FORMAT` | — |

**已知差异**：MuPDF 在像素角落采样，我们在像素中心采样，因此整条渐变相差半个像素（端点最大 8/255）。
这是光栅化约定的差异，不是实现错误；测试按解析值（±3）断言，不按 MuPDF 像素断言。

**踩过的坑（值得记住）**：`sh` 之前一直失败，根因不是阴影代码，而是 `pdf_annotation_paint.c` 的 scope 包装层
把 `shading` 回调直接拷了过去、上下文却换成了 scope，于是画布指针被当成栈对象解引用。
凡是新增 sink 回调，**必须同时加 scope 转发函数**——这已经是同一类问题的第二次（上次是 `soft_mask`/`extent`）。

