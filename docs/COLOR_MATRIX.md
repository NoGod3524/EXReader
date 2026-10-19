# PDF 色彩与图像支持矩阵（工作包 4）

本表是 WP4 的验收底稿：每一项都必须有代码位置、正例与反例、以及独立参考的比对方式。
状态只有三种：**支持**（有正例与反例）、**部分**（能解析但结果与参考有已知差异）、**未支持**（明确拒绝或忽略）。

## 当前状态（2026-10-18，逐项按代码核对）

| 项 | 状态 | 代码位置 | 缺口 |
| --- | --- | --- | --- |
| 设备色空间 DeviceGray/RGB/CMYK | 支持 | `pdf_colorspace.c` | — |
| Indexed / Separation / DeviceN / All / None | 支持 | `pdf_colorspace.c` | 渐变色（Pattern）不支持 |
| CalGray / CalRGB / Lab | 支持 | `pdf_colorspace.c` | — |
| ICCBased v2/v4 → sRGB | 支持 | `icc.c:87` | **固定 RelativeColorimetric**，忽略 `/RI` 与图像 `/Intent` |
| 渲染意图 `/RI`（ExtGState） | **未支持** | 无解析 | 直接按相对比色处理，属静默近似 |
| 图像 `/Intent` | **未支持** | 无解析 | 同上 |
| 文档 `/OutputIntents` | **未支持** | 无解析 | 印刷文件不会使用其输出意图的 ICC |
| 图像 `/Matte` | 部分 | `pdf_image.c:99-113` | 仅灰度/RGB；CMYK matte 明确拒绝 |
| 透明组 `/Group /CS` | 部分 | `pdf_content.c:169` | 只接受 DeviceRGB，其余 `EXR_UNSUPPORTED` |
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
