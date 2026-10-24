# G11：GTK 产品性能观测

先读[共同约束](README.md)，接受其中全部不变项与云端执行限制。
固定实现起点：`f43baf9182d75907c0cb5d6f77048f27bca8c950`。新建独立工作树和分支 `codex/reader-perf-gtk`。
类型：性能采样；优先级：P1；分发：DeepSeek Harness。

## 文件归属

- `tests/reader_perf_gtk/**`
- `.github/workflows/reader-perf-gtk.yml`
- `docs/READER-PERF-GTK.md`
- `docs/validation/reader-perf-gtk.json`

除此之外的目录只读。不要修改共享构建、已有工作流或本交接目录。

## 实现与边界

与G10分别独立，从固定基线构建真实GTK产品宿主，在固定2202本书库测首屏可交互、分页/搜索/继续阅读、导入时输入响应、RSS/高水位和包体。
至少30次独立启动；固定Xvfb/窗口管理器/分辨率，记录CPU、系统、二进制/语料SHA、冷热策略和全部原始样本。
截图或AT-SPI轮询间隔不能冒充frame-clock；没有真实frame数据就只交端到端响应。不修改SDK冻结预算或创建新的通过阈值。

## 云端出口

Linux Actions实际窗口与输入操作；采样器失败、timeout、缺样如实失败，不筛掉慢样本。保留原始CSV/JSON和环境。
不改GTK宿主、accounts.inc或接收owner文件；测量脚本以后可由root在新共同源码重跑。
同一source/run/attempt逐项验收；参考通过记录不转移到本包源码。任何未覆盖能力继续保持未授予。

## 先读的实际代码

- `tests/linux_host/check_shelf_ui.py`
- `docs/READER-DESKTOP-SHELF.md`
- `docs/PERFORMANCE.md`

## 交回

推送功能分支；完整受测SHA、最终纯文档HEAD/差异、run/attempt/job、具名结果、工件ID/字节/digest/有效期、原失败及剩余工作。不要替root合入。

