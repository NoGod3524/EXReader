# 交接单（2026-10-19，WP4 着色批次后交给下一个会话）

## 仓库状态

| 项 | 值 |
| --- | --- |
| 分支 | `codex/framework` |
| 基点 | `f0fd4b5`（网格 6/7 + DeviceCMYK 组批次） |
| 工作区 | 干净（本文档是随后的文档提交） |
| 回归 | **129 / 129**（新增 `native-pdf-shading-mesh7`） |
| CI | 未推送，未跑 |

## 这一阶段交付了什么

| 文件 | 内容 |
| --- | --- |
| `src/pdf_shading_mesh.c` | **网格类型 6（Coons）/ 7（张量积）**：12 个边界控制点 + 类型 7 的 4 个内部极点 + 4 个角颜色；flag 1/2/3 共享上一条边；按每个 patch 的屏幕尺寸自适应细分；`Decode` 数组扩到 12 个值（四颜色分量） |
| `src/pdf_content.c` | 接受 `DeviceCMYK`/`CMYK` 透明组（按 RGB 合成，见下）；Form BBox 反向角点归一化；`Tf`/文本状态操作允许出现在 BT/ET 之外；操作符错误信息带上名字 |
| `src/pdf_shading.c` | 径向渐变 `Extend` 外推：位图 256→512，四周各扩一个梯度跨度 |
| `tests/test_pdf_shading_mesh7.c` | 4 个生成夹具：平面 Coons、平面张量、凸起张量、CMYK；平面 6/7 必须逐字节相同；RGB 与 MuPDF 误差 ≤4/255 |
| `tests/test_pdf_groupcs.c` / `tests/test_blend.c` | 不再把 CMYK 组当 `EXR_UNSUPPORTED`；断言朴素换算下的像素 |
| `tools/generate_pdf_shading_mesh7_fixture.py` | 重新生成 4 个夹具 |

设计要点（细节见 `HANDOFF.md` 的已知坑 3–9）：

- **网格 patch 的控制点只有 x、y**，颜色是**全部控制点之后**的 4 条角颜色记录（类型 6：12 点；类型 7：16 点）。用读顶点的函数读 patch 点会把颜色位吃掉——这个坑已经踩过一次。
- 类型 6 与类型 7 的平面正方形必须输出相同像素；这条断言能抓住控制点顺序错误。
- DeviceCMYK 组**接受但按 RGB 合成**：颜色在 PDF 层按朴素公式转 RGB，透明混合发生在 RGB。不透明内容正确，半透明重叠是近似。
- 径向/轴向 `Extend` 是**有限外推**（各方向一个跨度），不是无限平面。

## 下一步（按依赖排序）

### 1. 原生 CMYK 组缓冲（WP4 剩余）

画布/组缓冲目前是 RGB。要真正在 DeviceCMYK 空间混合，需要四分量缓冲，并把源 CMYK 值
带过绘制接口（`exr_draw_style.fill/stroke` 只有 RGB）——这是结构性改动，做完才能声称
CMYK 组“完整”。在此之前保持现在的 RGB 合成 + 文档标注。

### 2. DeviceCMYK profile 决定

`HANDOFF.md` 里 Argyll public-domain CMYK profile 的三个打包方案（内嵌 ~1 MB / zlib ~415 KB /
9⁴ LUT ~20 KB）仍待用户选择。选定后页面、网格、组共用同一转换，并同步改
`groupcmyk`、`shading-mesh7-cmyk` 的断言。

### 3. WP4a

证书加密（PubSec）、EFOpen、JBIG2、JPX。

### 4. WP6–WP16

按原顺序。WP5 只剩 `border-spacing` 不支持（矩阵已标）。

## 已知坑（务必先读）

1. 网格类型 4 的 `flag 1/2` 续接、类型 5 的顶点顺序**仍未像素验证**（类型 6/7 已用夹具验证）。
2. `issue13520.pdf` 现在能渲染，与 MuPDF 平均差 **3.39**（37% 像素不同）；差异来自
   DeviceCMYK 朴素换算 + RGB 组合成，**不是网格几何**。`bug1703683_page2_reduced.pdf`
   仍卡在 **ToUnicode** 严格校验（语料宽容此前按要求回退），与网格无关。
3. 半透明 CMYK 组内容会与 CMYK 空间渲染器不同——不要把它当 bug 修，先做第 1 项。
4. 径向/轴向 Extend 的外推范围有限；裁剪区远超一个跨度时仍会截断。
5. `border-style: hidden` 非 collapse 时不占布局空间；逐边边框是独立的 BORDER 盒
   （判断有无边框用 `exr_border_any()`，不要只看 `box.border_width`）。
6. **仓库路径含中文**：Ninja 在 `文档` 路径下 `chdir` 失败，CTest 的 argv 也会因 ANSI
   代码页打不开 fixture。用 ASCII junction 构建：
   `mklink /J C:\Users\Oscar\exr "C:\Users\Oscar\OneDrive\文档\ChatGPT\EXReader"`，
   构建目录 `C:\Users\Oscar\exr-build`（MSVC）/ `C:\Users\Oscar\exr-gcc`（GCC, Ninja）。
7. **依赖下载走不了 schannel**：用 Python `urllib` 下到 `C:\Users\Oscar\exr-deps`，再传
   `-DFETCHCONTENT_SOURCE_DIR_<NAME>=<path>`。

## 文档入口

1. `docs/HANDOFF.md` ——「工作包现状与已知坑」「交接：下一步顺序」；
2. `docs/SUPPORT_MATRIX.md` —— 支持矩阵（渐变/网格、合成、CMYK 边界）；
3. `docs/NATIVE_VALIDATION.md` —— 末尾两节：WP5 边框/表头、本批网格 6/7；
4. `docs/SDK_COMPATIBILITY.md` —— 「Mesh shadings 6/7 and DeviceCMYK groups」。
