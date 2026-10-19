# 交接单（2026-10-19 交给下一个会话）

## 仓库状态

| 项 | 值 |
| --- | --- |
| 分支 | `codex/framework` @ `444424c` |
| 工作区 | 干净，已推送 |
| 回归 | **127 / 127** |
| CI | 代码基线 `8f3fbc8` 七作业全绿（后续为文档提交，走 `[skip ci]`） |
| 语料 | pdf.js 120 份中 47 份可比对，平均差 0.513 |

## 这一阶段交付了什么

| 提交 | 内容 |
| --- | --- |
| `d715fb9` | 按要求回退语料兼容工作，只保留 handoff 项（CCITT 重挂） |
| `dbb9d16` `cbe4d3d` `8f3fbc8` `f4cee53` | **WP5 边框线型**：dashed / dotted / double，块级 + 合并表格两条路径都有像素断言 |
| `360b081` | **WP4 网格渐变类型 4/5**，与 MuPDF 像素对照一致 |
| `db70495` | **WP4a CCITT**：缺 `/Rows` 时取图像 `/Height` |
| `50c0eeb` | **WP4a `/Extends`**：对象流扩展 |
| `47a7ed1` … `444424c` | 检查点、已知坑、审计、语料基线、矩阵更新 |

## 下一步（按依赖排序）

### 1. WP4 收尾：网格渐变类型 6/7

- 结构已知：类型 6 是 12 个控制点（Coons），类型 7 是 16 个（张量积），
  边标志 0 表示完整面片，1/2/3 复用上一面片的部分控制点（隐式点表见 PDF 参考表 4.35）；
- **我尝试过两次都回退了**：第一次把 Coons 公式写错（自相矛盾的两行），第二次写完没来得及做像素对照。
  已写好并验证可编译的两个辅助函数思路保留在下面，供直接取用：

```c
/* 四条边都是三次 Bezier：上 p0-p3，右 p3-p6，下 p9-p6（反向），左 p0-p9 */
/* Coons: S = (1-v)*top(u) + v*bottom(u) + (1-u)*left(v) + u*right(v) - 双线性角点 */
/* 张量积: S = Σ_i Σ_j B_i(v) B_j(u) P[i*4+j] */
```

- 验收样本：`tests/corpus/pdfjs/bug1703683_page2_reduced.pdf`（`/Extends` 已修好，
  现在卡在 CMYK 组）与 `issue13520.pdf`（卡在 CMYK 组）。
  **这两个样本都先被 CMYK 组挡住**，所以先做第 2 项更省事。

### 2. WP4：CMYK 默认换算

实测（`tests/fixtures/pdf-color/cmyk-fill.pdf`，`0 1 1 0 k`）：

| 来源 | 像素 |
| --- | --- |
| 本实现（朴素公式） | (255, 0, 0) |
| Argyll public domain profile（9⁴ LUT 采样） | (232, 0, 0) |
| MuPDF（SWOP 系） | (237, 28, 36) |

- 可用的公开授权 profile：`https://raw.githubusercontent.com/imbo/imbo/main/data/profiles/argyllcms_cmyk.icm`
  （961,644 字节，ICC v2，同目录有 LICENSE）；
- 三个打包选项：直接内嵌（~1 MB）、zlib 压缩内嵌（~415 KB）、9⁴ LUT（~20 KB，已实测生成可用）；
- **需要用户决定**：接受 Argyll profile（有据可依但仍有色差），还是保持朴素公式。

### 3. WP5 剩余

- **逐边边框**：`exr_style` 只有单一 `border_width/color/style`，需加四边字段并接到块级与表格两条路径；
- **重复表头**：分页时把 `thead` 行重新铺到新页顶部，需要保留表头单元格布局；
- **`border-spacing`**：已在矩阵里标为不支持（`separate` 表格按 0 间距排列）。

## 已知坑（务必先读）

1. 网格续接（类型 4 的 `flag 1/2`）、类型 5 的顶点顺序**都没有像素对照**；
2. 自造网格夹具 MuPDF 有时**不渲染**，不能拿自己的输出当标准；
3. CMYK 组一律返回 `EXR_UNSUPPORTED`——这是**有意**的，不是 bug；
4. 所有未实现路径都返回 `EXR_UNSUPPORTED`，没有静默错误输出（审计 `docs/AUDIT-2026-10-19.md`）。

## 文档入口

1. `docs/AUDIT-2026-10-19.md` —— 12 条显式缺口与测试薄弱处；
2. `docs/HANDOFF.md` ——「工作包现状与已知坑」「交接：下一步顺序」；
3. `docs/SUPPORT_MATRIX.md` —— 支持矩阵（含 `border-spacing` 不支持一行）。
