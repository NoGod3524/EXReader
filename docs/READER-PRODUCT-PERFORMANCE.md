# 产品性能同源观测入口

产品计划的 F08 仍待验收：产品 UI 的帧时间、内存和首次可交互预算须在固定设备及书库规模下测量并经批准冻结。SDK 已有预算和真实文档引擎基线见 `docs/READING-REAL-PERFORMANCE.md`、`docs/READING-CPU-BASELINES.md`；它们不替代 UI 预算。这里不新增阈值。

## 可复用测量与边界

- Windows：`.github/workflows/reader-perf-windows.yml` 支持手动触发和 `workflow_call`，以调用者源码构建 3.41 SDK 和实际桌面宿主，使用 `tests/windows_host/seed_shelf.c` 生成的 2202 本 SDK 原件，测量首屏、分页、搜索、翻页、恢复、导入响应和进程工作集。它记录源码、组件树、可执行文件、字体、语料、环境、逐进程结果和打包清单；不是帧时间。历史实测及 16 MiB TXT 拒绝见 `docs/READER-PERF-WINDOWS.md`。
- Linux GTK：`.github/workflows/reader-perf-gtk.yml` 支持手动触发和 `workflow_call`，使用 2202 本 SDK 原件、真实 X11 输入及宿主观测；汇总所有计划样本、RSS、包身份和环境，并以独立作业核对同次工件。没有帧时钟数据；旧实测见 `docs/READER-PERF-GTK.md`。
- Android：`tools/run_reader_shelf_ui.py` 和 `.github/workflows/reader-shelf-android.yml` 已有 2202 本真实 SDK 原件与模拟器进程 PSS 原始采样；`tools/check_reader_shelf_android.py` 明确 `performance_accepted=false`、`physical_device_execution=false`。原工作流固定旧 SDK 和宿主树，不能直接将历史结果视作当前源码的性能结果。
- Apple：`tests/apple_host/shelf/collect_shelf_evidence.py` 和 `.github/workflows/reader-apple-shelf.yml` 已记录 2202 本原件、原生布局观测、进程峰值 RSS、程序文件散列和运行目标；报告明确无硬性能预算或真机授予。原工作流按分支选择旧 SDK/检查，需适配最终源码后再运行。

两个桌面入口当前构建的宿主功能选项以各自构建日志和 CMakeCache 为准；这不是最终全部功能配置的包。汇总者必须核对所测程序与最终交付包的散列、源码 SHA、运行和 attempt，再将其与目标设备、书库、可交互定义及获批准预算逐项关联。不同 runner 的绝对数值不可直接当作同设备对比。保留失败、原始记录及日志，不从观测完整性推导性能达标，也不从模拟器推导真机达标。

调用示例（在最终源码的工作流中调用对应文件）：

```yaml
jobs:
  windows-observation:
    uses: ./.github/workflows/reader-perf-windows.yml
  gtk-observation:
    uses: ./.github/workflows/reader-perf-gtk.yml
```

这两个入口分别构建程序，并非接收外部已发布包；若最终交付包由其他构建产生，必须核对实际包身份，不能仅凭源码相同授予同一包。Android、Apple 和帧级采样仍需要在最终源码与实际目标上完成；不能以这些桌面结果标记 F08 或六平台通过。
