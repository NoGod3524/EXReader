# 交接单（2026-10-19 晚，WP5 收尾后交给下一个会话）

## 仓库状态

| 项 | 值 |
| --- | --- |
| 分支 | `codex/framework` |
| 基点 | `2a897d1`（本次 WP5 收尾提交） |
| 工作区 | 干净（本文档是随后的文档提交） |
| 回归 | **128 / 128**（新增 `native-border-edges`、`native-table-header`） |
| CI | 未推送，未跑 |

## 这一阶段交付了什么

| 文件 | 内容 |
| --- | --- |
| `src/internal.h` | `exr_style` 的边框字段改成四边数组（物理顺序 T/R/B/L），新增 `exr_border_extent/any/uniform` |
| `src/style.c` | `border-top/right/bottom/left` 简写、`border-width/color/style` 1–4 值展开；`border` 简写展开成 12 条逐边声明 |
| `src/flow.c` | 写模式映射（边界数组随 margin/padding 一起映射）；`exr_flow_edge`/`exr_flow_borders`；统一四边仍走旧紧凑路径 |
| `src/pager.c` | 四边内缩、`decorate()` 在块级生成逐边边框盒（含分页 `seal` 路径） |
| `src/pager_table.c` | collapse 冲突按边取值；separate 单元格逐边绘制；重复 `<thead>`（`repeat_header`、`header_rows/header_cells`、页面预算扣除） |
| `tests/test_border_edges.c` | 184 项：块、简写、1–4 值展开、separate/collapse 单元格、rowspan 合并格、两竖排、跨页（含 checkpoint 与整本一致）、嵌套格、半透明、positioned 回读 |
| `tests/test_table_header.c` | 139 项：每页重复、无 thead 不重复、页面预算、两行表头 + colspan、collapse/separate 表头边框、分页与整本一致、高表头 |
| docs | `SUPPORT_MATRIX`、`HANDOFF`、`VERSIONING`、`README`、`NATIVE_VALIDATION` 已更新；`AUDIT-2026-10-19.md` 加时点提示 |

设计要点（细节见 `HANDOFF.md` 的「已知坑」6–9）：

- 公共 `exr_box` **没有加字段**（ABI epoch 1 不允许数组元素加字段）。统一四边仍用
  `border_width` + DASHED/DOTTED/DOUBLE；四边不一致时每边一个 `EXR_BOX_BORDER` 盒。
- 单元格的四边在表格层画（`paint_cell_sides` / `split_borders`），不放进 cell layout。
- 重复表头每页用 `exr_flow_unit` 重排 thead 单元格；高度从 `measure` 与 `split_row`
  的页面预算里扣除，只在页顶重复。

## 下一步（按依赖排序）

### 1. WP4：CMYK 透明组

结构性改动：组缓冲扩成 CMYK 或并行维护，合成回 RGB 时走同一色彩转换。它是两个真实
`/ShadingType 7` 样本的最后一道墙，必须先做。

### 2. WP4：网格渐变类型 6/7

`flag 0` 的单个面片先做，再加 `flag 1/2` 的共享边。**续接与类型 5 顶点顺序至今没有
像素对照**，不要再用自造夹具自我验证（MuPDF 不渲染它们）。

### 3. WP4a

证书加密（PubSec）、EFOpen、JBIG2、JPX。

### 4. WP6–WP16

按原顺序。WP5 只剩 `border-spacing` 不支持（矩阵里明确标注，非阻塞）。

## 已知坑（务必先读）

1. 网格续接（类型 4 `flag 1/2`）、类型 5 顶点顺序**都没有像素对照**；
2. 自造网格夹具 MuPDF 有时**不渲染**，不能拿自己的输出当标准；
3. CMYK 组一律返回 `EXR_UNSUPPORTED`——这是**有意**的，不是 bug；
4. 所有未实现路径都返回 `EXR_UNSUPPORTED`，没有静默错误输出；
5. **本仓库路径含中文**：`Ninja` 在 `文档` 路径下 `chdir` 失败，CTest 传 fixture 路径时
   argv 走 ANSI 代码页也会打不开文件。构建时用 ASCII junction：
   `mklink /J C:\Users\Oscar\exr "C:\Users\Oscar\OneDrive\文档\ChatGPT\EXReader"`，
   在 `C:\Users\Oscar\exr-build` 里 configure（Visual Studio 17 2022 生成器）。
6. **依赖下载走不了 schannel**：CMake `FetchContent` 的下载在本机失败。用 Python
   `urllib` 把 `cmake/deps.cmake` 里的 8 个包下到本地，再传
   `-DFETCHCONTENT_SOURCE_DIR_<NAME>=<path>`。依赖缓存现在在 `C:\Users\Oscar\exr-deps`。
7. `border-style: hidden` 非 collapse 时不占布局空间；`solid/dashed/dotted/double` 占宽。
8. 判断块有无边框别只看 `box.border_width==0`：逐边边框是单独的 BORDER 盒。

## 文档入口

1. `docs/HANDOFF.md` ——「工作包现状与已知坑」「交接：下一步顺序」；
2. `docs/SUPPORT_MATRIX.md` —— 支持矩阵（含 `border-spacing` 不支持一行）；
3. `docs/NATIVE_VALIDATION.md` —— 末尾「WP5 independent border sides and repeated table headers」；
4. `docs/AUDIT-2026-10-19.md` —— 12 条显式缺口与测试薄弱处（`50c0eeb` 时点快照）。
