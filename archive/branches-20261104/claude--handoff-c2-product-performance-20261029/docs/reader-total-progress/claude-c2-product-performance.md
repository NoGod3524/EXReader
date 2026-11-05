# Claude C2 产品性能与交互预算门禁 (F08 候选，未验收)

分支 `claude/handoff-c2-product-performance-20261029`，基线 `bd28d4946f17a184dd3cd47a584cf49fce34e973`。
当前固定 108 项已验收 95；本文件不加分，不修改清单。

## 内容

- `.github/workflows/reader-c2-product-performance-20261029.yml`：在同一源码上以 SDK 3.42.0 构建
  GTK 与 Windows 实际桌面宿主并打包，复用原有采样器（`tests/reader_perf_gtk/*`、
  `tests/reader_perf_windows/*`，未改动）在固定 2202 本 SDK 原件书库上采样；`aggregate` 作业记录各平台
  job 结果、工件 id 与摘要。
- `tests/reader_product_performance_handoff/gate.py` + `budgets.json`：同源 run/attempt、包为 3.42、
  原采样器覆盖完整，再对候选 p95/RSS/工作集上限逐项判定。上限来自 `docs/READER-PERF-WINDOWS.md`
  和 GTK 既有观测（取较严者），在 3.42 测量前固定，门禁不放宽。
- 无产品负责人批准的预算：门禁通过也不授予 F08（`f08_granted` 恒为 false）。

## 未覆盖（如实登记）

既有宿主驱动不含：切字号延迟、逐帧帧时间/滚动、定位跳转延迟、长会话稳态内存；两宿主均无帧时钟信号。
Android、Apple 未测。Windows 16 MiB TXT 导入此前为 `import_rejected`，保留。

## 实测结果

（待 Actions 结果填写）
