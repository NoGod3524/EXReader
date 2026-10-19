# 交接单（2026-10-19，WP4 着色批次后交给下一个会话）

## 仓库状态

| 项 | 值 |
| --- | --- |
| 分支 | `codex/framework` |
| 基点 | `a959d79`（画布 CMYK 组缓冲批次） |
| 工作区 | 干净（本文档是随后的文档提交） |
| 回归 | **130 / 130**（新增 `native-pdf-shading-mesh7`、`native-canvas-cmyk`） |
| CI | 未推送，未跑 |

## 这一阶段交付了什么

| 文件 | 内容 |
| --- | --- |
| `src/pdf_shading_mesh.c` | **网格类型 6（Coons）/ 7（张量积）**：12 个边界控制点 + 类型 7 的 4 个内部极点 + 4 个角颜色；flag 1/2/3 共享上一条边；按每个 patch 的屏幕尺寸自适应细分；`Decode` 数组扩到 12 个值（四颜色分量） |
| `src/pdf_content.c` | 接受 `DeviceCMYK`/`CMYK` 透明组（按 RGB 合成，见下）；Form BBox 反向角点归一化；`Tf`/文本状态操作允许出现在 BT/ET 之外；操作符错误信息带上名字 |
| `src/pdf_shading.c` | 径向渐变 `Extend` 外推：位图 256→512，四周各扩一个梯度跨度 |
| `tests/test_pdf_shading_mesh7.c` | 4 个生成夹具：平面 Coons、平面张量、凸起张量、CMYK；平面 6/7 必须逐字节相同；RGB 与 MuPDF 误差 ≤4/255 |
| `tests/test_pdf_groupcs.c` / `tests/test_blend.c` | 不再把 CMYK 组当 `EXR_UNSUPPORTED`；断言朴素换算下的像素 |
| `src/blend.c` / `src/canvas.c` / `src/vector.c` | **画布四分量 CMYK 组缓冲**：`EXR_GROUP_CMYK`、`exr_canvas_path_cmyk`，可分离混合模式、软遮罩、挖空；嵌套/复合/非可分离模式明确拒绝 |\n| `tests/test_canvas_cmyk.c` | 富黑 + 白各 50%：CMYK 空间得 (128,128,191)，RGB 合成会是 (191,191,191)；组外 CMYK 转 RGB；四类拒绝 |\n| `tools/generate_pdf_shading_mesh7_fixture.py` | 重新生成 4 个夹具 |

设计要点（细节见 `HANDOFF.md` 的已知坑 3–9）：

- **网格 patch 的控制点只有 x、y**，颜色是**全部控制点之后**的 4 条角颜色记录（类型 6：12 点；类型 7：16 点）。用读顶点的函数读 patch 点会把颜色位吃掉——这个坑已经踩过一次。
- 类型 6 与类型 7 的平面正方形必须输出相同像素；这条断言能抓住控制点顺序错误。
- **画布已能真 CMYK 混合**（四分量缓冲 + `exr_canvas_path_cmyk`）；**PDF 还没接**：内容仍以 RGB 绘制，PDF 组内半透明重叠仍是近似。不透明内容一致。
- 径向/轴向 `Extend` 是**有限外推**（各方向一个跨度），不是无限平面。

## 下一步（按依赖排序）

### 1. 把 PDF 源 CMYK 接进画布缓冲（WP4 剩余）

画布缓冲已经就绪（`EXR_GROUP_CMYK` + `exr_canvas_path_cmyk`）。缺的是 PDF 侧：
`exr_pdf_group_rgb` 识别出 `/CS /DeviceCMYK` 后，需要给 `exr_draw_sink_ex` **追加**
一个 CMYK path 回调（`exr_draw_style` 不能加字段，但 sink 有 `struct_size` 可追加），
内容层把 `exr_pdf_color.values` 里的源 CMYK 传下来，画布 sink 转发到
`exr_canvas_path_cmyk`，并把组标志设为 `EXR_GROUP_CMYK`。注意 PDF 里 CMYK 组常嵌套
（`issue13520` 的页面组 + 多个 Form 组），当前画布拒绝嵌套 CMYK 组，接线时要一并
处理嵌套（子组继承 CMYK 或提交时做 CMYK→CMYK 合成）。

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
3. 画布 CMYK 组已能真混合；**PDF 组仍未接线**，所以 PDF 的半透明 CMYK 重叠仍与 CMYK 空间渲染器不同。不要只改画布就宣称 PDF 组完整——先做第 1 项。
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
3. `docs/NATIVE_VALIDATION.md` —— 末尾三节：WP5 边框/表头、网格 6/7、画布 CMYK 组；
4. `docs/SDK_COMPATIBILITY.md` —— 「Canvas DeviceCMYK groups」与「Mesh shadings 6/7」。
