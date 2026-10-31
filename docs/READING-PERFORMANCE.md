# 阅读核心初始测量（R3）

目标是为轻量原生阅读构建建立可复查的数据，再制定体积、首屏、翻页和内存预算。
当前测量不授予性能达标结论。

## 云端命令

先从已安装的阅读配置 SDK 静态链接 `tools/benchmark.c`，得到独立消费者。
在干净的受测源码检出中运行：

```sh
python tests/check_reading_measurements.py
python tools/measure_reading_core.py build/reading-consumer/reading-benchmark FONT.ttf build/reading-measurements --source-sha SOURCE_SHA --compiler cc
```

`SOURCE_SHA` 必须是受测完整提交；`--compiler` 填该消费者的实际编译器可执行文件。
输出目录必须不存在，默认每次进程最多 300 秒，默认采样三次。
构建和上述命令均只在 GitHub Actions 执行。

## 采样与身份

每次启动独立进程，执行现有原生 benchmark 的
`--text-bytes 1048576 FONT.ttf --paging --max-pages 32`。
这是一份 1 MiB 合成 TXT，包含首屏和后续 32 次分页/渲染，生产 33 页。
沿用 `run_benchmarks.py` 的 monotonic 时钟、nearest-rank 分位数与进程 RSS 高水位口径。
进程内分开记录字体打开、publication 打开、首屏排版、首屏绘制、后续排版/绘制/总耗时。
汇总取三次独立进程对应指标的中位数，不拼接逐页样本。
首次显示总耗时来自引擎测量，不包含进程启动。
生成文本和字体成本均计入进程高水位；增量高水位不等同于引擎分配总量。

`summary.json` 记录完整源码 SHA/tree、干净状态、消费者体积与 SHA-256、字体体积与 SHA-256、
runner/共享校验器/benchmark 源码散列、OS/CPU/Python、编译器 `--version` 和相关构建环境。
进程前后重新检查源码、二进制、字体和工具身份。
每次 stdout/stderr 原件、散列、退出码、超时或解析失败均保留；失败不筛掉，发生任何失败时不出成功中位数。
校验重新读取原件，检查有限非负字段、样本数、分位数及固定工作负载。
编译器身份、源码清洁度或前后身份不满足条件时汇总失败。

## 当前边界

- 磁盘缓存未控制；三次均无丢弃的 warmup，不能称为磁盘冷启动。
- GitHub 共享 runner 的结果是环境相关初始观测，不能直接用作跨机器绝对性能承诺。
- 当前仅测合成重排文本，尚未覆盖 EPUB/PDF 代表性文件、PDF 打开/渲染、随机跳页、长章与恶意输入。
- 消费者可执行文件体积已记录；完整安装 SDK/发布包体积由构建证据另外登记。
- 尚未设硬预算、对照成熟引擎或宣布性能优化完成。

云端自验包含正常报告以及负数/非有限值、错误场景/页数/分位数、进程失败、超时、
身份变化、缺样本、原件修改与伪造成功标志的拒绝。
