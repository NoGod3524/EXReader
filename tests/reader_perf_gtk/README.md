# GTK 产品性能采样（G11）

云端专用。本目录只包含测量探针、采样器、汇总门禁与工件核验脚本，不含产品代码。
GitHub Actions 之外不编译、不解析、不运行任何内容。

## 组成

| 文件 | 作用 |
| --- | --- |
| `seed_library.c` / `CMakeLists.txt` | 只用安装后公共 SDK（`exr_library_*`）建立固定 2202 本原始语料，并写出 `corpus.json` |
| `observe.py` | 冻结 GTK 宿主的事件观测：inotify 目录监视、状态解析、真实 X11 输入、进程指标 |
| `sample.py` | 32 次独立启动的采样驱动，输出原始 `samples.json` / `samples.csv` / `launches.json` |
| `summarize.py` | 汇总与门禁：同一 source/run/attempt、固定环境、计划样本全覆盖、不过滤样本 |
| `verify.py` | 在本 run 的 Actions 内下载自己的工件 ZIP，重算 ZIP 与每个成员摘要并复核报告 |

## 测量口径

* 起点：真实 X11 按键注入之前（`xdotool key` 进程启动前）或进程启动前。
* 终点：冻结宿主自己的同步观测写入。`g_file_set_contents` 用临时文件 + 改名落盘，
  因此监视的是目录，事件时间戳由 inotify 监视线程在 `select` 唤醒时取
  `CLOCK_MONOTONIC`；没有任何对观测文件的轮询，也没有截图或 AT-SPI。
* 真实画面证据：宿主的 `draw` 回调把 `painted_generation` 设为当前
  `frame_generation`，每次真实重绘产生一次可观测写入。采样器记录这些写入的时刻与
  增量，作为"真实重绘"证据；宿主不暴露每帧 frame-clock 时间戳，因此不报告帧间隔、
  帧时间百分位或丢帧数。
* 注入开销：`xdotool` 每条命令的启动开销单独标定（`calibration.json`），并且已经
  包含在每个端到端样本内。

## 固定条件

* Xvfb `:99`、`1440x900x24`，openbox 为唯一窗口管理器，宿主窗口 `1040x820`。
* 宿主环境变量白名单固定（`environment.json` 的 `host_environment`）。
* 语料：2202 本 TXT 原件，`Shelf 0000` 为约 340 KiB 的多段长书（分页样本来源），
  其余为短书；书库与语料清单的 SHA-256 同时记录。
* 冷热策略：启动序号 `0,8,16,24` 尝试 `sync; echo 3 > /proc/sys/vm/drop_caches`，
  记录返回码与实际生效值；其余样本标记为 warm（继承上一轮页缓存）。

## 场景

| 场景 | 启动数 | 样本 |
| --- | --- | --- |
| `shelf_search_open_turn` | 8 | 首屏 50 行、首个按键响应、键盘选择移动、标题搜索、开书、6 次翻页、2 次回翻 |
| `shelf_search_variants` | 8 | 作者字面搜索、空结果、清空过滤、标题搜索、开书、2 次翻页、1 次回翻 |
| `resume_turn` | 8 | 继续阅读恢复帧与首画、4 次翻页、1 次回翻 |
| `import_probe` | 8 | 首屏、3 次 6 MiB 导入（每次 8 个"忙碌期按键"样本、2 次导入期真实缩放与主循环应答）、2 次翻页 |

导入场景使用书库副本，固定 2202 本基线不被导入改动。

## 门禁

`summarize.py` 不设任何性能阈值：只判定同一 source/run/attempt、实现起点与冻结树、
固定屏幕/窗口、2202 本语料、事件驱动观测、计划样本 100% 覆盖（失败/超时/缺失即失败）、
包体与 RSS 高水位已记录、以及原始样本未被过滤。任一项不通过，run 失败且证据照常上传。

`verify.py` 在本 run 内通过 API 取 job 与工件清单，用 `gh api` 下载 ZIP，重算 ZIP 与
成员 SHA-256，并复核报告身份与逐项覆盖；缺项、过期、跨源码、跨 attempt、摘要不符或
覆盖不足一律拒绝。
