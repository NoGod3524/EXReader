# G10：Windows 产品性能观测

先读[共同约束](README.md)，接受其中全部不变项与云端执行限制。
固定实现起点：`f43baf9182d75907c0cb5d6f77048f27bca8c950`。新建独立工作树和分支 `codex/reader-perf-windows`。
类型：性能采样；优先级：P1；分发：DeepSeek Harness。

## 文件归属

- `tests/reader_perf_windows/**`
- `.github/workflows/reader-perf-windows.yml`
- `docs/READER-PERF-WINDOWS.md`
- `docs/validation/reader-perf-windows.json`

除此之外的目录只读。不要修改共享构建、已有工作流或本交接目录。

## 实现与边界

构建固定源码的真实Windows产品宿主，用固定2202本书库观测首屏可交互、分页/搜索/继续阅读、导入期间输入响应、工作集峰值与产物大小。
至少30次独立进程启动，记录原始样本、CPU/系统/显示参数、冷热策略、二进制与语料SHA。操作由真实原生UI触发。
外部UI端到端延迟不能称应用帧时间；没有真实帧信号时明确未测帧时间。原SDK数值预算及CPU基线不改，本包只交测量与预算建议，不自授“丝滑”。

## 云端出口

独立Windows Actions workflow，缺样/失败/timeout如实保留，不删除慢样本。测量器故障退出非零，性能无预算时不以“采样成功”冒充达标。
输出逐次CSV/JSON、环境身份、实际EXE和测量过程；读取基线宿主，不修改生产代码。
同一source/run/attempt逐项验收；参考通过记录不转移到本包源码。任何未覆盖能力继续保持未授予。

## 先读的实际代码

- `tests/windows_host/check_shelf_ui.py`
- `docs/READER-WINDOWS-SHELF.md`
- `docs/PERFORMANCE.md`

## 交回

推送功能分支；完整受测SHA、最终纯文档HEAD/差异、run/attempt/job、具名结果、工件ID/字节/digest/有效期、原失败及剩余工作。不要替root合入。

