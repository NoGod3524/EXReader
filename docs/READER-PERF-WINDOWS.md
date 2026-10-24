# Windows 产品性能观测

状态：本轮为 G10「Windows 产品性能观测」。实现起点固定为
`f43baf9182d75907c0cb5d6f77048f27bca8c950`，分支 `codex/reader-perf-windows`。
本包只新增 `tests/reader_perf_windows/**`、`.github/workflows/reader-perf-windows.yml`、
本文档与 `docs/validation/reader-perf-windows.json`；不修改生产代码、SDK 保护树、
产品 schema 1、既有 wire/RFC 预算或 CPU 基线。

云端工作流：`.github/workflows/reader-perf-windows.yml`（`windows-2022`，独立运行）。

## 测量对象

- 实际打包产品宿主：`apps/reader/desktop` 用安装后的公共 SDK 编译出的
  `EXReaderProduct.exe`，经 `tools/build_windows_host.py` 打成
  `EXReader/EXReader.exe`（静态阅读 SDK，无共享运行库）。产品宿主源码为未修改的
  `examples/reader.c` 加产品目录与桌面元数据模块。
- 固定语料：`tests/windows_host/seed_shelf.c` 生成的 2202 本 SDK 原件（该文件逐字不改），
  以及打包固定的多页书 `Sample-positive.epub`（用于书内翻页与继续阅读）。
  多页书放在单独的阅读 profile 中，因此 2202 本原件的书架语料本身不被改动。
- 固定字体：打包的 `Reader.otf`（由 `tools/host_font.py` 固定来源取得）。
- 语料身份：种子程序输出的 2202 条身份，加上从产品目录库读回的逐本标题与
  `source_bytes` 全量核对；EXE、字体、多页书的 SHA-256 记录在
  `environment.json`。本包不读 SDK 私有 SQL。

## 测量口径

每次样本都是一个**独立的新进程**：`EXReader.exe --font Reader.otf --data <profile>`。
所有操作由外部观测者投递到该进程**真实存在的 Win32 控件**上，并从同一控件读回结果：

| 操作 | 原生输入 | 观测点 |
| --- | --- | --- |
| 首屏可交互 | `SendMessageTimeoutW(WM_NULL)` 到主窗口 | 首批 50 行已交付 **且** UI 线程完成一次同步消息往返 |
| 打开书籍 | `LB_SETCURSEL` + 打开按钮 `BM_CLICK` | 页码标签首次出现合法页号 |
| 书内翻页 | 下一页按钮 `BM_CLICK`（8 次） | 页码标签页号/章号发生变化 |
| 继续阅读 | 新进程启动（宿主自动恢复上次书与页） | 页码标签恢复到上次页号，并与上一进程记录比对 |
| 书架分页 | 列表 `WM_MOUSEWHEEL` 滚到底部 | 列表由 50 行增至 100 行（keyset 下一批） |
| 搜索 | 搜索框 `WM_SETTEXT` | 列表内容变为该过滤条件的 50 行结果 |
| 导入期间输入响应 | 导入按钮 `BM_CLICK` 后持续采样 | 导入忙窗口内 `WM_NULL` 往返与路径框回显 |
| 工作集峰值 | 观测进程每 20 ms 读一次 `GetProcessMemoryInfo` | `PeakWorkingSetSize` / `PrivateUsage` |

这些消息投递到真实原生控件并由产品 UI 线程处理；它们**不是** `SendInput` 级别的硬件注入。
上报值是**外部端到端 UI 延迟**：从提交原生输入消息到控件状态可被外部观测为止。

**帧时间未测。** 该路径没有暴露应用内帧或 present 信号，因此本包不产出、也不推断
帧时间；任何数值都不能称为应用帧时间，也不代表「丝滑」。离散度包含观测轮询粒度
（一次 `WM_NULL` 往返 + 3 ms sleep）与云端共享 runner 的负载。

策略与限制：

- 冷启动组每次都从种子库文件复制一份全新 profile（无产品目录库、无 `host.ini`），
  因此每次冷启动都重建产品目录；热启动组复用已建好的 profile。
- 操作系统磁盘缓存与同宿负载**不受控**；冷/热只描述 profile 策略。
- 导入组每次导入一份固定 16 MiB 生成文本，其工作集峰值包含宿主导入缓冲，
  不与书架组直接比较。
- 失败、超时与慢样本原样保留在 `per-launch.json` / `samples.csv` /
  `memory.csv`；测量器自身故障（控件面缺失、书架未交付首批、进程提前退出）
  使驱动以非零码退出。

## 样本矩阵

四组，每组 12 次实测进程启动（共 48 次），另有 2 次准备启动（建目录库、建阅读 profile，
也记录但单独计数）：

| 组 | profile | 采集 |
| --- | --- | --- |
| `cold_shelf` | 每次全新复制 SDK 库文件 | 首屏、书架分页、搜索、清空、峰值 |
| `warm_shelf` | 共享已建 profile | 首屏、书架分页、搜索、清空、峰值 |
| `reading` | 共享阅读 profile（2202 + 固定多页书） | 打开/继续阅读、8 次书内翻页、峰值 |
| `import` | 每次全新复制 SDK 库文件 | 首屏、导入期间输入响应、导入后可见性、峰值 |

首批 50 行与搜索过滤结果在每次样本内都会被核对（`Shelf 0000..0049`、
`Author %_!` 的 17 倍数行）；任何不符即记为测量失败而不是静默通过。

## 预算建议（不执行）

本包**不设**数值预算，`performance_accepted` 恒为 `false`，
`budget_enforced` 恒为 `false`。`summary.json` 的 `proposed_budgets` 只把同批 p95
换算成候选阈值（多数为 p95 乘 1.5～4 倍留余量），每条都带来源与「仅供参考」，
需要产品负责人另行批准后才能成为预算。原 SDK 数值预算与 CPU 基线保持不变。

## 云端出口

工作流按顺序执行：源码身份门（`HEAD == GITHUB_SHA`、实现起点为祖先、SDK 保护树与
产品 SQL 未改、`git diff --name-only <start> HEAD` 全在本包白名单）→ Python 解析与
自检 → 构建安装后的阅读 SDK 与产品目录栈 → 编译真实产品宿主并跑其既有目录测试 →
打包产品并跑宿主原有 26 项自检 → 运行观测 → 严格汇总门 → 上传工件 → 通过 API 记录
工件身份（id/字节/digest/有效期）。

工件名带 run/attempt：`reader-perf-windows-<run>-<attempt>`（证据）与
`reader-perf-windows-identity-<run>-<attempt>`（身份记录）。
严格汇总门拒绝缺项、失败、跨源码/attempt、摘要错误与身份不符；**性能是否「达标」不在
本包的授予范围**。

## 结果

见下文各轮记录与 `docs/validation/reader-perf-windows.json`。首轮云端运行结果在
实现提交推送后补记；未完成的验证项保持未授予。
