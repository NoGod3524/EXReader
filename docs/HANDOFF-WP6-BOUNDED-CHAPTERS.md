# 包 B：WP6 有界章内解析

先读 `docs/RELIABILITY-SPLIT-HANDOFF.md`，遵守其基线、保护文件、分工与证据约束。建议分支 `codex/wp6-bounded-chapters`，尚未创建。

## 当前已做与缺口

EPUB ZIP→XML 输入已经使用32 KiB分块，消除了整章解压临时副本。完整 DOM、文本投影仍驻留，公开快照生命周期没变。这不满足有界章内解析。

原32 MiB成员/128 MiB累计限界保持有效；不能通过直接提高限制让50/100 MiB单章通过。需要设计有界阅读路径，并区分显式全量快照与分页工作区，保持既有接口语义和所有权。

普通Latin auto表格首屏优化已达到既有五轮交替、降低至少50%的子目标；不要重做该优化或放宽其口径。

首读：`docs/HANDOFF.md` WP6行、`docs/validation/2026-10-20-wp6-input-stream.json`、`docs/validation/2026-10-20-wp6-compatibility.json`、`docs/CORPUS_VALIDATION.md`。

## 重点路径

- `src/formats.c`：ZIP限界、publication/chapter装载和共享归档。
- `src/document.c`、`src/document_internal.h`：增量XML输入、DOM、正文投影、快照所有权。
- `src/pager.c`、`src/pager_table.c`：分页状态、缓存逐出和checkpoint恢复。
- `include/exr/document.h`、`include/exr/formats.h`、`include/exr/text.h`：稳定公开接口。
- `tests/test_pager.c` 和既有格式/CSS/CFI/选择回归。
- `tools/check_document.c`、`tools/check_corpus.py`、`tools/triage_corpus.py`：整本遍历及原失败分类。

不要碰未跟踪的 `src/internal.h`；实际实现使用各模块的内部头。

## 实施要求

1. 先梳理chapter载入、DOM/投影、分页、搜索/选择/CFI、导出依赖和借用指针生命周期。列出窗口逐出时必须保存的状态，避免用滑动缓冲破坏公开快照。
2. 实现有界解析/正文窗口及可恢复读取。缓存、取消和超限应沿用现有控制机制；不引入未要求的通用框架。
3. 保持跨窗口CSS继承、段落、双向/字素、表格/float/ruby、源位置及CFI连续性。窗口/缓存逐出后checkpoint和随机回读须与既有稳定路径一致。
4. 使用固定10/50/100 MiB单章及分段章语料，记录散列、缓存配置、首屏、峰值、顺序翻页与固定随机计划。
5. 解析工作区单独计量，分离原始/映射书字节、索引、缓存及显式快照；不能通过把DOM换成整章落盘/映射且不计量来规避预算。
6. 使用本包独立构建和证据目录，针对性通过后跑完整回归、安装消费以及Linux ASan/UBSan。与包A重叠的文件通过最小补丁协调。

## 固定验收出口

- 缓存相同，10→100 MiB解析驻留增量≤32 MiB，单章与分段、顺序与随机分别有量化结果。
- 首屏及翻页实测，不用打开成功或返回EXR_LIMIT替代性能出口。
- 与稳定全量/参考路径核对页数、源范围、CFI、检查点恢复及固定字体渲染；沿用既有精度口径，不新增宽容误差。
- 取消、限界、重复恢复、逐出后的所有权、失败清理有回归；ABI1/schema6和既有快照生命周期保持。
- 已集成WP7/WP8的脚本塑形、颜色绘制、选择与随机恢复回归保持通过；WP12-lite转换/导出不退化。

## 兼容分类基线

最新分类在 `build/wp7-integration-20261020/epub-classification/classification.json` 和 `build/wp7-integration-20261020/pdf-classification-r2/classification.json`。原500本EPUB仍有未完成项，整批accepted=false；不得改预期或覆盖原120秒超时结果。源码变化后的重放写新目录，并交包C更新分类总账。

## 交付

提交SHA、窗口/恢复设计与接口兼容说明、固定语料散列和逐项JSON、解析驻留计算方法、完整回归/安装/ASan结果、未满足项。使用本包证据文件，例如 `docs/validation/wp6-bounded-chapters.json`。不要独自宣布WP16完成或启动最终长测；合并后由集成人冻结验收源码。
