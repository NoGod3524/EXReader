# C02 产品级性能测量工具契约

状态：工具已提交，真实证据见 `validation.json` / `HANDOFF-RESULT.md`；未执行或未完整即 `accepted=false`。

## 范围

实际 Windows 简洁版（`EXR_READER_WINDOWS_COMPACT=ON` 的 `EXReaderProduct.exe`）与 GTK 简洁版
（`EXR_READER_GTK_COMPACT=ON` 的 `exreader-linux`）。全部构建、测试、语法检查、夹具生成、工件下载/解析只在
GitHub Actions；本分支不修改任何既有文件，只新增本包白名单路径。

## 四类 source（分开记录，不合并）

| 角色 | Windows | GTK |
| --- | --- | --- |
| consumer（本工具、workflow） | `GITHUB_SHA`（本分支 HEAD） | 同左 |
| producer（被测宿主源码） | 固定起点 `0889f7d1…`（`guard.py` 证明起点后只改白名单路径） | 二次 checkout `57203a52…`（GTK 简洁 UI 受测提交，`guard.py` 核对 HEAD） |
| SDK | 起点内 SDK 3.41.0（`reading-library` 预设，宿主 `find_package(... EXACT)`） | producer 内同一预设，3.41.0；记录 `exreader-linux --version`；GTK_SDK_SOURCE=`edddc463…` |
| verifier | `verify.py`，同 run 内通过 API 重新下载本 run 的 ZIP | 同左 |

被测程序只构建一次（`windows-build`、`gtk-build`），两个独立 round 的作业各自下载该构建工件并重算程序/字体/seed 的 SHA-256；
`verify.py` 再要求每个 round 身份里的 `program_sha256` 等于构建工件的 `build-identity.json`。

## 复用与新增

* 复用（只读 import）：`tests/reader_perf_windows/perf_windows.py` 的 `Host` 与 `op_*` 原语；
  `tests/reader_perf_gtk/sample.py` / `observe.py` 的事件驱动采样器（inotify + 真实 X11 按键）。
* 新增：`seed_library.c`（可参数化 500/5000 本原件，公共 SDK 种入）、`win_perf.py`、`gtk_perf.py`、
  `common.py`（样本 schema、最近秩统计、CPU 分层）、`aggregate.py`（读取时断言 + 分层汇总 + 预算建议）、
  `verify.py`（工件认证）、`guard.py`（白名单/起点/producer 固定）。

## 场景与指标

规模：500 与 5000 本原件，各自独立种库、独立 round 内互不混合。每个 round 在独立 runner 上执行（两 round 顺序相反）。

Windows（控制级端到端延迟，`SendMessageTimeout`/`BM_CLICK`/`WM_SETTEXT`/`WM_MOUSEWHEEL`/`WM_COMMAND` 作用于真实控件）：
`cold`（新进程，目录库副本，产品目录重建）、`warm`（共享已建目录）、`resume`（重开恢复阅读位置并翻页）、
`import`（4 MiB TXT 经紧凑界面“更多操作”展开面板的原导入路径，含导入期主线程往返）。
指标：`start_window`、`start_first_rows`、`start_interactive`、`resume_restored`、`shelf_scroll_page`、
`search_author`/`search_clear`/`search_title`、`open_book`、`page_turn`、`back_to_library`、`import_complete`、
`post_import_search`、`ui_roundtrip_idle`/`reading`/`import_busy`（`WM_NULL` 往返作为主线程响应）。

GTK（真实 X11 按键 → 宿主同步观测写入，由 inotify 取时）：
`shelf_search_open_turn`、`shelf_search_variants`、`import_probe`；指标沿用 G11 词汇
（首屏、首键响应、选择移动、各搜索、开书应用/首绘、前后翻页、导入完成、导入期按键/缩放响应）。
作者字面搜索的期望行数按语料 `min(50, ceil(N/17))` 设定。

## 统计与内存定义

* p50/p95：最近秩，`rank = ceil(p*n/100)`，取排序后第 rank 个样本；另报 min、max、n。
* Windows RSS：`WorkingSetSize`，观测进程每 20 ms 采样；`rss_peak_bytes = max(PeakWorkingSetSize)`，
  `rss_final_bytes` 为关闭前最后样本，`private_peak_bytes = max PrivateUsage`。
* GTK RSS：`/proc/<pid>/status` 的 `VmRSS`（final）与 `VmHWM`（peak），关闭前同一时刻读取，kB×1024。
* 原始样本全部保留：`samples.json`、`launches.json`、`memory.json`、Windows `raw/memory/*.json`、GTK `raw/n*/`。

## CPU 分层基线

`stratum = <platform>/<cpu model slug>/<逻辑核数>c`。统计只在同一 stratum 内合并，不跨 stratum 池化；
一个 stratum 只有单个 round 时标记 `baseline_scope = single round only`。基线是“该 stratum 的新独立基线”，
不继承其他 CPU 或旧 2202 书架数据。

## 读取时断言（`aggregate.py` / `common.py`）

* 每个 round 的 `bundle.json` 与解压文件逐一核对；身份含 consumer SHA、run、attempt、job、程序 SHA-256、producer、SDK、stratum。
* 每行样本：platform、round、shelf_size、metric、unit 必须与 round 身份一致；`ok` 必须是有限非负数；未知 metric/status 拒绝；`sample_id` 不得重复。
* 失败、缺失（计划未观测）、未知样本不被排除：它们使 `measurement_complete=false`（仅导入期按键/缩放响应的 `not_observed` 因竞态允许）。
* 计划启动数、每启动一条内存记录、每个规模每个必需指标至少一次 `ok`。
* 两个独立 round 缺一即不完整。

## 新产品预算

`summary.json` 的 `proposal` 只含“建议值”（`approved=false`，`ceil(1.25 × 各 round p95 最大值)`，样本<8 时留空）。
没有任何预算被批准；旧 SDK 预算、1710 计数、schema1、wire 未改。

## 明确不覆盖

* 无帧时间：Windows 无帧信号；GTK 只有 `painted_generation` 重绘证据。不报告帧间隔/丢帧。
* Windows 导入使用展开面板的导入路径（紧凑“导入”按钮是系统选择器，已由既有紧凑套件独立验证）；选择器自身延迟不测。
* GTK 简洁宿主不自动续读，故不含 `resume_turn`；“继续阅读”按钮未被驱动。
* 磁盘缓存/后台负载不受控（GTK 冷启动仅尝试 `drop_caches`，实际生效值入记录）。
* 云端虚拟 runner：不代表物理机、读屏、USB 或其他平台性能。
