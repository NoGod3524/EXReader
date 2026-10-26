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

## 2026-10-26 当前组合 GTK 观测

源码 `c11b8cfc7d8872db22f967b919cf650f58efbb2a`，Actions [40381215897](https://github.com/NoGod3524/EXReader/actions/runs/40381215897)，attempt 1：Linux `ubuntu-22.04`、Xvfb，32 次启动、520/520 样本，11 项观测完整性检查与独立工件身份核验通过。包中程序 SHA-256 `a31ca88780befa05fe06ef267dff0c7062b3c821f409f287fdc22a0989207aca`，归档 SHA-256 `10fc2387ec67e056a798c5fac0ff807526b83bbb6428b7c728cd37cc2bd11335`，27 文件共 25,873,656 字节。工件 `reader-perf-gtk-40381215897-1`，ID `12678228026`，SHA-256 `01907e96ac668d8d71fe3371c03051644fd39951eb0de1910c35ba7b663e4985`，有效期至 2027-01-24。

首个 50 行书架从启动到观测 p50/p95/max 为 147.066/247.908/3492.426 ms（24 次）；下一页输入至首次绘制 p50/p95/max 为 33.807/36.480/40.829 ms（112 次）；进程 RSS 高水位最大 208,604 KiB。完整原始样本、环境、冷/热策略和包配置在工件中；这些是端到端观测，不是逐帧时间，且未冻结 UI 数值预算。早期失败 [40380951236](https://github.com/NoGod3524/EXReader/actions/runs/40380951236) 保留：打包工具当时仍默认 3.40，后续显式传入 3.41。
