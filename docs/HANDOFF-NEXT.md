# 交接单：EXReader WP4（网格 6/7 + DeviceCMYK 透明组端到端）

> 给下一位 AI：先读完这一页，再按「快速验证」跑一遍回归，确认基线后再动代码。
> 本文件是自包含的；更长的历史在 `docs/HANDOFF.md`，验证细节在 `docs/NATIVE_VALIDATION.md`。

## 0. 一句话状态

WP4 的**网格渐变类型 6/7** 与 **DeviceCMYK 透明组（四分量缓冲、PDF 源色接入）** 已完成，
MSVC 与 GCC 都是 **130/130** 回归全绿；工作区干净，**9 个提交未推送（含本文档）**。
下一步是 **DeviceCMYK ICC profile 打包方案**（待用户选），然后 WP4a、WP6–WP16。

## 1. 仓库与环境

| 项 | 值 |
| --- | --- |
| 仓库 | `C:\Users\Oscar\OneDrive\文档\ChatGPT\EXReader`（GPL-3.0-only） |
| 分支 | `codex/framework` |
| HEAD | `f9a4491`（docs）；功能提交 `1d24bf7` |
| 工作区 | 干净 |
| 回归 | **130/130**（MSVC Release、GCC 16 `-Werror`） |
| 推送 | **未推送**，origin 落后 9 个提交（含本文档） |
| CI | 未跑 |

### 构建陷阱（必读）

仓库路径含中文 `文档`，**Ninja 在该路径下 `chdir` 会失败，CTest 的 argv 也会因 ANSI
代码页打不开 fixture**。已有 ASCII junction：

```bat
mklink /J C:\Users\Oscar\exr "C:\Users\Oscar\OneDrive\文档\ChatGPT\EXReader"
```

| 用途 | 目录 | 生成器 |
| --- | --- | --- |
| MSVC 构建 | `C:\Users\Oscar\exr-build` | Visual Studio 17 2022，Release |
| GCC 构建 | `C:\Users\Oscar\exr-gcc` | Ninja，GCC 16.2 |
| 第三方依赖 | `C:\Users\Oscar\exr-deps` | configure 时用 `-DFETCHCONTENT_SOURCE_DIR_<NAME>=<path>` |

依赖下载在此环境走不通 schannel；需要补依赖时用 Python `urllib` 下载到 `exr-deps`，
再用上面的 `FETCHCONTENT_SOURCE_DIR_*`。两个构建目录已经配置好，通常**直接 build** 即可。

### 快速验证（先跑，别跳过）

```powershell
cmake --build C:/Users/Oscar/exr-build --config Release --parallel 8
ctest --test-dir C:/Users/Oscar/exr-build -C Release --output-on-failure

cmake --build C:/Users/Oscar/exr-gcc --parallel 8
ctest --test-dir C:/Users/Oscar/exr-gcc --output-on-failure
```

预期两边都是 `100% tests passed, 0 tests failed out of 130`。

单页渲染 / 与 MuPDF 对照：

```powershell
& 'C:\Users\Oscar\exr-build\Release\exreader-fixed-example.exe' <in.pdf> <out.png>
python -X utf8 tools\compare_reference.py 'C:\Users\Oscar\exr-build\Release\exreader.dll' <dir> --scale 1 --json <report.json>
```

## 2. 这一批做了什么

### 2.1 网格渐变类型 6/7（`src/pdf_shading_mesh.c`）

- 类型 6 = Coons patch：12 个边界控制点 + 4 个角颜色；没有内部极点。
- 类型 7 = 张量积 patch：12 个边界控制点 + **4 个内部极点（在边界之后）** + 4 个角颜色。
- 控制点**只有 x、y**；颜色是**全部控制点之后**的独立记录（flag 0 时 4 条，flag 1/2/3 时 2 条）。
  **不要用读顶点的函数读 patch 点**——会把颜色位一起吃掉（此前踩过）。
- flag 1/2/3 的共享边查表逻辑（`edge_points`/`edge_colors`）；颜色按角点双线性插值；
  每个 patch 按屏幕尺寸自适应细分（`MESH_PATCH_SUBDIV`/`MESH_MAX_TRIANGLES`）。
- `Decode` 数组扩到 12 个值，支持 4 个颜色分量（CMYK 网格因此正确）。

### 2.2 DeviceCMYK 透明组（端到端）

链路：

```
PDF /Group /CS /DeviceCMYK
  → exr_pdf_group_rgb 标记 EXR_PDF_GROUP_CMYK
  → 内容层 begin_group 映射为 EXR_GROUP_CMYK
  → 填充/描边/文字/复合路径经 sink 的 path_cmyk 回调
  → exr_canvas_path_cmyk → 画布四分量缓冲
  → end_layer / frame_cmyk 用页面同一公式转回 device RGB
```

要点：

- `exr_canvas_begin_group`：`cmyk = (flags & EXR_GROUP_CMYK) || c->cmyk_groups`，即
  **嵌套组自动继承** CMYK 混合空间；混用 DeviceGray 组会明确拒绝。
- 缓冲是 `[C M Y K A object]` 预乘浮点，另有 RGBA 预览维持旧提交路径与内存统计。
- 组提交 `frame_cmyk` 处理隔离/非隔离、opacity、可分离混合模式、clip 与挖空；
  嵌套组初始化直接**拷贝父组的真实 CMYK**，不经过 RGB 往返。
- 复合填充+描边走 `exr_composite_compound_cmyk`（一个 CMYK 元素）。
- 组内图像/着色以 RGBA 到达，写入时按同一设备模型转 CMYK。
- **非可分离混合模式**（Hue/Saturation/Color/Luminosity）在 CMYK 组内返回
  `EXR_UNSUPPORTED`（ISO 32000 只对 RGB 定义这些函数），不静默近似。
- PDF 侧源值来自 `exr_pdf_color.values`，没有新增公开颜色字段。

### 2.3 顺带修复

- 径向渐变 `Extend`：位图 256→512 采样，四周各扩一个梯度跨度；轴向沿用既有的一跨度外推。修复
  `issue13520.pdf` 两端缺失的光泽。
- Form `/BBox` 反向角点归一化（真实文件常见）。
- `Tf`/`Tc`/`Tw`/`Tz`/`TL`/`Ts`/`Tr` 允许出现在 BT/ET 之外（仍是文本状态操作）。
- PDF 操作符错误信息带上具体操作符名。
- `pdf_annotation_paint.c` 的 `paint_scope` 包装器转发 `path_cmyk`——**任何包装 sink
  并替换 context 的地方都必须转发新回调**，否则会把 scope 指针当画布。

## 3. 验证证据

| 项 | 结果 |
| --- | --- |
| 全量回归 | MSVC 130/130，GCC 130/130，零警告 |
| `native-pdf-shading-mesh7` | 4 个夹具：平面 Coons / 平面张量 / 凸起张量 / CMYK；平面 6 与 7 **逐字节相同**；RGB 与 MuPDF 1.28.2 误差 ≤4/255；CMYK 中心 = 朴素模型值 |
| `native-canvas-cmyk` | 富黑 C=M=Y=1,K=1 与白各 50%：CMYK 空间 = (128,128,191)，RGB 合成会是 (191,191,191)；组外 CMYK 转 RGB、嵌套/复合成功、非可分离拒绝 |
| `native-pdf-groupcs` | `groupcmyk.pdf` 朴素红 (255,0,0)（MuPDF SWOP 为 (237,28,36)）；`groupcmyk-blend.pdf` 断言中心 (128,128,191)±3 且蓝通道显著高于红 |
| 网格夹具与 MuPDF 平均差 | mesh6 1.114、mesh7 1.114、bulge 0.912、cmyk 8.327（色差来自 profile，不是几何） |
| `issue13520.pdf` | 可渲染，与 MuPDF 平均差 **3.394**、37.5% 像素不同；残差来自朴素 CMYK 换算 + 该文件的 Screen/组叠加 |
| `bug1703683_page2_reduced.pdf` | 仍卡在 **ToUnicode** 严格校验（语料宽容此前按要求回退），与网格无关 |

夹具生成器（可重跑）：

- `tools/generate_pdf_shading_mesh7_fixture.py <tests/fixtures/pdf-color>`
- `tools/generate_groupcmyk_blend_fixture.py <tests/fixtures/pdf-color>`

## 4. 剩余工作与边界

| 项 | 说明 |
| --- | --- |
| **DeviceCMYK ICC profile** | 当前用朴素 `1-min(1,c+k)`；Argyll public-domain profile 的三个打包方案（内嵌 ~1 MB / zlib ~415 KB / 9⁴ LUT ~20 KB）**待用户选**。这是 CMYK 色差主因（单色块就差 ~8/255）。选定后页面、网格、组共用同一转换，并同步改 `groupcmyk`、`groupcmyk-blend`、`shading-mesh7-cmyk` 的断言 |
| 非可分离混合模式 × CMYK 组 | 明确 `EXR_UNSUPPORTED`；要支持需定义 4 分量上的语义 |
| 网格 4 的 flag 1/2、网格 5 顶点顺序 | 仍**未像素验证**（类型 6/7 已验证） |
| 径向/轴向 Extend | 有限外推（各方向一个跨度），超大裁剪区仍会截断 |
| `border-spacing` | WP5 唯一剩余项，矩阵已标不支持 |
| 语料 | 47/120 可比对，平均差 0.513，最差 `issue11144_reduced.pdf` 6.052；格式错误 64、显式不支持 8、参考失败 1 |

## 5. 下一步顺序（按依赖）

1. **profile 打包方案**：等用户拍板；实现后统一 CMYK 转换。
2. **WP4a**：证书加密（PubSec）、EFOpen、JBIG2、JPX。
3. **WP6–WP16**：按原顺序。
4. 想继续网格：先补类型 4 的 flag 1/2 与类型 5 的像素夹具（不要再自造未经参考实现确认的夹具）。

## 6. 已知坑（务必先读）

1. **不要给公开结构体加字段**（`exr_draw_style`、`exr_image_layer` 等）；能加的只有带
   `struct_size` 的版本化结构（如 `exr_draw_sink_ex`）或新函数。ABI epoch 1 不能动。
2. **包装 sink 必须转发所有可选回调**；`path_cmyk` 已经踩过一次（annotation `paint_scope`）。
3. **patch 控制点只有 x/y**，颜色在全部点之后；类型 7 的内部极点在边界之后。
4. **不要放宽验收标准**；不可达就明说；不支持路径必须返回 `EXR_UNSUPPORTED`，不能静默错。
5. **中文路径**：构建/CTest 必须走 `C:\Users\Oscar\exr` junction。
6. **依赖下载**：schannel 走不通，用 Python `urllib` + `FETCHCONTENT_SOURCE_DIR_*`。
7. `issue13520.pdf` 的残差不要误判成网格 bug；对照 `form32-only.pdf` 等隔离夹具可快速定位。
8. ToUnicode 严格校验是用户要求回退后的现状，不要为了语料通过率擅自放宽。

## 7. 提交列表（本轮，未推送）

| 提交 | 内容 |
| --- | --- |
| `f0fd4b5` | feat: render Coons and tensor mesh shadings and accept CMYK groups |
| `cbf7804` | docs: WP4 shading checkpoint |
| `a959d79` | feat: blend DeviceCMYK transparency groups in a four-component canvas buffer |
| `8feb927` | docs: canvas CMYK checkpoint |
| `1d24bf7` | feat: feed PDF DeviceCMYK groups through the four-component buffer |
| `f9a4491` | docs: end-to-end CMYK group checkpoint |

此前还有 WP5 收尾：`2a897d1`（feat）与 `db0ebae`（docs）。

## 8. 关键文件地图

| 文件 | 作用 |
| --- | --- |
| `src/pdf_shading_mesh.c` | 网格类型 4/5/6/7 解码与光栅化 |
| `src/pdf_shading.c` | 轴向/径向（含 Extend 外推）、类型分发 |
| `src/blend.c` | 合成核心：RGBA 路径 + CMYK 缓冲、`frame_cmyk`、CMYK 复合 |
| `src/canvas.c` | 画布 API、组/图层、clip、CMYK 组语义、sink 实现与快照 |
| `src/pdf_paint.c` | PDF 绘制层：`rgba()`/`cmyk_color()`、`geometry()`、sink 调用 |
| `src/pdf_content.c` | 内容解释器：颜色操作、组标记、路径/裁剪事件 |
| `src/pdf_annotation_paint.c` | 注解外观的 sink 包装器（`paint_scope`，必须转发 `path_cmyk`） |
| `include/exreader.h` | 公开 API：`EXR_GROUP_CMYK`、`exr_canvas_path_cmyk`、`exr_draw_sink_ex.path_cmyk` |
| `tests/test_pdf_shading_mesh7.c` | 网格 6/7 像素回归 |
| `tests/test_canvas_cmyk.c` | 画布 CMYK 组回归 |
| `tests/test_pdf_groupcs.c` | PDF 组色彩空间回归（含 `groupcmyk-blend.pdf`） |
| `docs/HANDOFF.md` | 工作包现状、已知坑、下一步 |
| `docs/NATIVE_VALIDATION.md` | 逐批验证记录（末尾三节） |
| `docs/SUPPORT_MATRIX.md` | 能力矩阵与边界 |
| `docs/SDK_COMPATIBILITY.md` | ABI/行为兼容说明 |

---

**接手时的第一件事**：在 `codex/framework` 上跑上面两条 `ctest`，确认 130/130；然后读
`docs/HANDOFF.md` 的「已知坑 1–3」和本文第 4 节，再决定是等 profile 决定还是先做 WP4a。
