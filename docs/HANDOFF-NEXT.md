# 交接单（2026-10-19，WP4 CMYK 组端到端后交给下一个会话）

## 仓库状态

| 项 | 值 |
| --- | --- |
| 分支 | `codex/framework` |
| 基点 | `1d24bf7`（PDF DeviceCMYK 组接入四分量缓冲） |
| 工作区 | 干净（本文档是随后的文档提交） |
| 回归 | **130 / 130**（`native-pdf-shading-mesh7`、`native-canvas-cmyk`） |
| CI | 未推送，未跑 |

## 这一阶段交付了什么

| 文件 | 内容 |
| --- | --- |
| `src/pdf_shading_mesh.c` | **网格类型 6（Coons）/ 7（张量积）**：12 边界控制点 + 类型 7 的 4 内部极点 + 4 角颜色；flag 1/2/3 共享边；自适应细分；`Decode` 扩到 12 个值 |
| `include/exreader.h` | `EXR_GROUP_CMYK`、`exr_canvas_path_cmyk`，以及 `exr_draw_sink_ex.path_cmyk`（追加字段，`struct_size` 版本化） |
| `src/blend.c` | 画布四分量缓冲：CMYK 像素合成、软遮罩、挖空、`frame_cmyk`（组提交）、`exr_composite_compound_cmyk`（复合填充+描边）、嵌套组 CMYK→CMYK 初始化 |
| `src/canvas.c` | `EXR_GROUP_CMYK` 语义：嵌套组继承 CMYK；复合路径走 CMYK 合成；非可分离混合模式拒绝 |
| `src/pdf_paint.c` / `src/pdf_content.c` | PDF 把 `exr_pdf_color.values` 的源 CMYK 经 sink 传入；`/Group /CS /DeviceCMYK` 映射为 `EXR_GROUP_CMYK` |
| `src/pdf_annotation_paint.c` | `paint_scope` 包装器转发 `path_cmyk`（否则会把 scope 指针当画布） |
| `tests/test_pdf_groupcs.c` | `groupcmyk-blend.pdf`：富黑 + 白各 50% 必须得到 (128,128,191)，而不是 RGB 合成的 (191,191,191) |
| `tests/test_canvas_cmyk.c` | 画布层同一用例；嵌套组/复合路径成功；非可分离模式拒绝 |
| `tools/generate_groupcmyk_blend_fixture.py` | 重新生成上面的夹具 |

## 下一步（按依赖排序）

### 1. DeviceCMYK ICC profile（WP4 剩余）

Argyll public-domain CMYK profile 的三个打包方案仍待用户选择：内嵌 ~1 MB / zlib ~415 KB /
9⁴ LUT ~20 KB。选定后页面、网格、组共用同一转换，并同步改 `groupcmyk`、
`groupcmyk-blend`、`shading-mesh7-cmyk` 的断言。**这是当前 CMYK 色差的主因**（单个纯色块
与 MuPDF 就差 ~8/255）。

### 2. WP4a

证书加密（PubSec）、EFOpen、JBIG2、JPX。

### 3. WP6–WP16

按原顺序。WP5 只剩 `border-spacing` 不支持（矩阵已标）。

## 已知坑（务必先读）

1. **CMYK 组已端到端，但仍有边界**：非可分离混合模式（Hue/Saturation/Color/Luminosity）在
   CMYK 组内返回 `EXR_UNSUPPORTED`；组内图像/着色以 RGBA 到达，按设备模型转 CMYK（与
   MuPDF 的 profile 渲染仍有色差）。
2. **sink 追加字段**：`exr_draw_sink_ex` 的 `path_cmyk` 在末尾，靠 `struct_size` 截断；任何
   **包装 sink 并替换 context 的地方都必须转发它**（`pdf_annotation_paint.c` 的
   `paint_scope` 是第一个踩坑点）。
3. 网格类型 4 的 `flag 1/2` 续接、类型 5 的顶点顺序**仍未像素验证**（类型 6/7 已验证）。
4. `issue13520.pdf` 与 MuPDF 平均差 **3.39**（37% 像素不同）；差异来自 DeviceCMYK 朴素换算
   + 该文件自身的 Screen/组叠加，不是网格几何。`bug1703683_page2_reduced.pdf` 仍卡在
   **ToUnicode** 严格校验（语料宽容此前按要求回退）。
5. 径向/轴向 Extend 的外推范围有限（各方向一个跨度），裁剪区远超一个跨度时仍会截断。
6. `border-style: hidden` 非 collapse 时不占布局空间；逐边边框是独立的 BORDER 盒
   （判断有无边框用 `exr_border_any()`，不要只看 `box.border_width`）。
7. **仓库路径含中文**：Ninja 在 `文档` 路径下 `chdir` 失败，CTest 的 argv 也会因 ANSI
   代码页打不开 fixture。用 ASCII junction 构建：
   `mklink /J C:\Users\Oscar\exr "C:\Users\Oscar\OneDrive\文档\ChatGPT\EXReader"`，
   构建目录 `C:\Users\Oscar\exr-build`（MSVC）/ `C:\Users\Oscar\exr-gcc`（GCC, Ninja）。
8. **依赖下载走不了 schannel**：用 Python `urllib` 下到 `C:\Users\Oscar\exr-deps`，再传
   `-DFETCHCONTENT_SOURCE_DIR_<NAME>=<path>`。

## 文档入口

1. `docs/HANDOFF.md` ——「工作包现状与已知坑」「交接：下一步顺序」；
2. `docs/SUPPORT_MATRIX.md` —— 支持矩阵（渐变/网格、合成、CMYK 边界）；
3. `docs/NATIVE_VALIDATION.md` —— 末尾三节：WP5 边框/表头、网格 6/7、画布与 PDF CMYK 组；
4. `docs/SDK_COMPATIBILITY.md` —— 「Canvas DeviceCMYK groups」与「Mesh shadings 6/7」。
