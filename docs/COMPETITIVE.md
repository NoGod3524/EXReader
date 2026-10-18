# 竞争目标与度量

**硬目标：全面领先 MuPDF、CREngine、Readium、foliate-js。** 不以「轻量」「范围外」作为回避理由。

领先与否不接受口头判断，只用同一语料下的可复现数据。本文件定义度量口径与当前基线，每次对照后更新。

## 四条线与判定

| 对手 | 领先的判定 | 当前工具 |
| --- | --- | --- |
| MuPDF | 同一批 PDF 上打开成功率更高、逐页像素差异更小、表单/redaction/加密覆盖更全 | `tools/compare_reference.py` |
| CREngine | 同一本书、同字体、同页宽下排版指标更好（断词、表格列宽、浮动绕排、分页一致） | 待建 |
| Readium | 宿主接入路径更多（C/C++/Swift/JNI/移动端）、示例与文档更完整、TTS/无障碍/OPDS/LCP 可用 | 待建 |
| foliate-js | 同页面 HTML/CSS 覆盖更广、SSML/词典等阅读模块可用、有可运行的应用证据 | 待建 |

## MuPDF 对照口径

`python tools/compare_reference.py <libexreader.dll> <目录> [--scale 1] [--json out]`

- 两侧都渲染第 1 页，同尺寸（scale=1 即 1 点 = 1 像素）；
- 输出每文件的 `mean_abs`（RGB 平均绝对差）、`max_abs`、`percent_differing`（单通道差 >8 的像素占比）；
- 打开或渲染失败记 `exreader-format` / `exreader-unsupported` / `size-mismatch` 等原因；
- **已知应失败**的故意损坏夹具（`*-bad-*`、`group-malformed`）在统计时单独计，不算作兼容失败。

## 基线（2026-10-18，本机 Windows，scale 1）

语料：`tests/fixtures/pdf-blend`（42 个文件，其中 16 个是故意的畸形样本）。

| 结果 | 数量 |
| --- | ---: |
| 正常比对（compared） | 26 |
| ExReader 拒绝（format） | 14（含全部畸形样本） |
| ExReader 拒绝（unsupported） | 2（CMYK 组色空间、非指数 TR） |
| 平均 RGB 绝对差 | 7.175 |
| 最差文件 | `knockout-elements.pdf`（52.7） |

这组数字不是「兼容性结论」：夹具本身是极端合成场景（挖空、软遮罩、混合模式），
与 MuPDF 的已知差异记录在 `NATIVE_VALIDATION.md`。真实书籍语料尚未接入，
**在跑真实语料之前，不得引用本表宣称领先或落后。**

## 下一步

1. 接入真实 PDF 语料（至少 200 份，来源与许可记录在案），跑出打开失败率与像素差异分布；
2. 按「打不开 > 画不对 > 不支持」排序补功能，每批一个可验收出口；
3. EPUB 侧建 CREngine 对照（同书同字体同页宽）；
4. SDK 侧建 Readium/foliate-js 能力对照表。
