# GTK 产品性能观测

状态：云端 Linux Actions 同源同 attempt 通过。受测完整源码
`553d1a5e2aa27b8625930900f592d78d11e2378e`，run `40086971620`、attempt 1；
采样作业 `120851788112` 与工件核验作业 `120852600194` 均成功，11 项门禁全部通过，
计划的 520 个样本全部实测、零失败、零缺失。

本包只交观测值，不新建性能预算，也不改 SDK 冻结预算、产品 schema1 或既有 wire：
`accepted=true` 只表示"同源同 attempt 的观测完整且未过滤"，不表示性能达标。
frame-clock 帧间隔、帧时间百分位、丢帧、真机流畅性、读屏与整体产品完成均**未授予**。

## 边界

- 被测宿主是固定起点 `f43baf91` 上的真实 GTK 产品宿主（`apps/reader/desktop` +
  `examples/linux`，`EXR_READER_BUILD_GTK=ON`、`EXR_READER_PRODUCT_CATALOG=1`），
  本包没有改动宿主、`accounts.inc` 或任何接收 owner 文件。
- 与 G10 相互独立：本包自建 2202 本语料、自有采样器、汇总门禁与工件核验，
  不引用 G10 的文件、证据或阈值。
- SDK 保护树（`src`、`include`、`cmake`、顶层 `CMakeLists.txt`、`tests/fixtures`、
  `bindings`、`native.yml`、`reliability.yml`）与 `9854061b` 逐字相等；
  `apps`/`extras`/`tools`/`examples`/`docs/handoffs` 与固定起点相等；本包变更仅
  `tests/reader_perf_gtk/**`、`.github/workflows/reader-perf-gtk.yml`、
  `docs/READER-PERF-GTK.md`、`docs/validation/reader-perf-gtk.json`（由同 run 的
  `guards.json` 记录，`outside_whitelist=[]`）。

## 固定条件

- 托管 runner `ubuntu-22.04`；Xvfb `:99`、屏幕 `1440x900x24`；openbox 是唯一窗口
  管理器；宿主窗口 `1040x820`。32 次启动实测几何全部为 `(1040, 820)`。
- 宿主进程环境是固定白名单（见工件 `environment.json` 的 `host_environment`）：
  `DISPLAY=:99`、`GDK_BACKEND=x11`、`LANG/LC_ALL=C.UTF-8`、显式 `HOME`/
  `XDG_RUNTIME_DIR`/`XDG_CACHE_HOME`/`XDG_CONFIG_HOME`（全部位于证据目录之外）。
- 安装后公共 SDK 3.40.0 / ABI 1（`exreader-linux --version` 输出 `3.40.0 1`）；
  `runtime-dependencies.txt` 不含 webkit/webview/libcef/electron，无 WebView。
- GTK 3.24.33（runner 自带，32 次启动同一条）。

## 语料

2202 本 TXT 原件由 `tests/reader_perf_gtk/seed_library.c` 只用安装后公共 SDK
（`exr_library_import_unique`/`exr_library_update`）生成：`Shelf 0000` 是 312,000 字节
的 2000 段长书（分页样本来源），其余 2201 本为短书，作者按下标每 17 本取 `Author %_!`。
语料清单 `corpus.json` 的 SHA-256 为 `f992e58badb1fc2df0b1cdb4aaa6f30cf43133d9b0c7afecc35aad3bc5721fdf`，
原件总量 477,075 字节，种子程序 SHA-256
`3f3191bbed629f4483924ced0316263047d1ba6f8cfe0e5d87fc5c7367dcf11d`，固定。

导入场景在书库**副本**上进行（`profile-import`，每次导入前重建），固定 2202 本基线
不被导入改动；导入对象是 4 个 6 MiB 确定性 TXT（每个 6,291,456 字节）。

## 采样计划

32 次独立启动（每次新进程、新观测目录），四场景各 8 次：

| 场景 | 启动 | 计划样本 |
| --- | ---: | --- |
| `shelf_search_open_turn` | 8 | 首屏 50 行、首个按键应答、键盘选择移动、标题搜索、开书（应用/首画）、6 次翻页、2 次回翻 |
| `shelf_search_variants` | 8 | 首屏、按键应答、选择移动、作者字面搜索、空结果、清空过滤、标题搜索、开书、2 次翻页、1 次回翻 |
| `resume_turn` | 8 | 继续阅读恢复帧（应用/首画）、4 次翻页、1 次回翻 |
| `import_probe` | 8 | 首屏、3 次 6 MiB 导入（每次 8 个忙碌期按键、2 次忙碌期缩放应答、1 次完成）、2 次翻页 |

冷热策略：启动序号 `0/8/16/24` 先执行 `sync; echo 3 > /proc/sys/vm/drop_caches`，
返回码 0、`effective=cold`（4 次）；其余 28 次标记 warm（继承上一轮页缓存）。
OS 页缓存与后台负载仍未受控。

## 观测口径

- 起点：真实 X11 输入注入之前（`xdotool` 进程启动前），或进程启动前。
- 终点：冻结宿主自己的同步观测写入。`g_file_set_contents` 用临时文件 + 改名落盘，
  因此监视的是目录；事件时间戳由 inotify 监视线程在 `select` 唤醒时取
  `CLOCK_MONOTONIC`。**没有**轮询观测文件，**没有** AT-SPI，**没有**截图。
- 注入开销单列：20 次 `xdotool getmouselocation` 标定中位 2.72ms
  （min 2.545 / max 3.100），已包含在每个端到端样本内。
- 注入前观测不计入：输入命令启动前送达的写入可能不是该命令的应答，采样器会跳过并计数
  （`pre_injection_skips`），不会把负延迟当作样本。
- 真实重绘：宿主 `draw` 回调把 `painted_generation` 设为当前 `frame_generation`，每次
  真实重绘产生一次可观测写入；本 run 记录 192 次真实重绘、2,133 次状态写入。
  宿主不暴露每帧 frame-clock 时间戳，因此**不报告**帧间隔、帧时间百分位或丢帧数；
  需要帧级数据的结论继续保持未授予。

## 逐项结果

单位 ms，p95 为 nearest-rank，全部原始样本（含慢样本）都保留在工件
`samples.json` / `samples.csv` 中。

| 指标 | 计划/实测 | min | p50 | p95 | max |
| --- | ---: | ---: | ---: | ---: | ---: |
| `startup_shelf_rows`（进程启动→首个 50 行有界书架） | 24 / 24 | 140.907 | 144.835 | 252.278 | 3312.444 |
| `startup_key_response`（进程启动→首个真实按键应答） | 16 / 16 | 192.888 | 197.924 | 3373.077 | 3373.077 |
| `shelf_selection_move`（按键→键盘选择移动） | 16 / 16 | 3.730 | 3.961 | 5.849 | 5.849 |
| `search_title_unique`（查询→单行结果） | 16 / 16 | 244.022 | 245.338 | 275.799 | 275.799 |
| `search_author_literal`（查询→字面作者结果页） | 8 / 8 | 210.590 | 211.449 | 213.556 | 213.556 |
| `search_empty`（查询→空结果） | 8 / 8 | 244.038 | 244.731 | 248.961 | 248.961 |
| `search_clear`（清空→首批 50 行） | 8 / 8 | 236.945 | 237.289 | 238.650 | 238.650 |
| `open_book_applied`（Return→应用阅读帧） | 16 / 16 | 77.597 | 278.532 | 512.343 | 512.343 |
| `open_book_painted`（Return→阅读帧首次真实重绘） | 16 / 16 | 76.666 | 277.631 | 511.486 | 511.486 |
| `page_turn_forward`（F4→下一页首次真实重绘） | 112 / 112 | 21.906 | 33.417 | 35.912 | 39.052 |
| `page_turn_backward`（F3→上一页首次真实重绘） | 32 / 32 | 14.529 | 17.115 | 21.757 | 27.621 |
| `resume_frame_applied`（进程启动→恢复的阅读帧） | 8 / 8 | 180.647 | 345.872 | 595.040 | 595.040 |
| `resume_frame_painted`（进程启动→恢复帧首次真实重绘） | 8 / 8 | 179.803 | 359.942 | 594.276 | 594.276 |
| `import_complete`（F1→导入完成并打开原件） | 24 / 24 | 1944.482 | 1957.519 | 1967.638 | 1969.596 |
| `import_input_response`（忙碌期按键→宿主应答） | 192 / 192 | 1.246 | 3.613 | 4.509 | 6.059 |
| `import_resize_response`（忙碌期缩放→主循环应答） | 16 / 16 | 7.480 | 11.703 | 18.017 | 18.017 |

读法提示：

- `startup_shelf_rows`/`startup_key_response` 的 max 都来自 `launch 00`：该次启动首次把
  2202 本原件发布进产品目录（`first_publication`），耗时 3312.4/3373.1ms；
  其余 23 次书架首屏为 140.9–252.3ms 区间，中位 144.8ms。
- 搜索类样本都包含宿主自身的 200ms 防抖（`shelf_search_due`），因此 p50 集中在
  211–245ms；这是产品行为，不是测量开销。
- `open_book_applied`/`resume_frame_applied` 包含被测宿主当前的按书打开路径
  （打开时会枚举公开 SDK 全书库并复用有界产品查询），属于宿主既有边界，本包不做解释性扣除。
- 导入场景每个 6 MiB 导入在 worker 忙碌期间仍以 1.2–6.1ms 应答真实按键，
  缩放则以 7.5–18.0ms 得到主循环应答；`paint_delta` 如实记录缩放是否顺带产生重绘，
  冻结宿主不保证 resize 重绘，因此该指标只声明"主循环应答"。

## RSS 与包体

- 32 次启动的进程 RSS 高水位（`/proc/<pid>/status` 的 `VmHWM`）：中位 69,008 KiB，
  最大 237,288 KiB（`launch 19`，3 次 6 MiB 导入）；首次发布那次 120,964 KiB；
  书架/恢复场景 62.7–69.3 MiB；导入场景 208.9–237.3 MiB。RSS 是内核观测的进程驻留
  高水位，不等于引擎对象计量，也不构成硬预算。
- 包体：payload 25,869,184 字节（27 个文件）；`bin/exreader-linux` 9,305,864 字节，
  SHA-256 `ab9e0df18c4b48804a4d6ca3280e7c32a475e52cc6fe0e763fdd8524e221807b`；
  `Reader.otf` 16,437,364 字节，SHA-256
  `2c76254f6fc379fddfce0a7e84fb5385bb135d3e399294f6eeb6680d0365b74b`；
  `EXReader-Linux.tar.gz` 17,879,982 字节，SHA-256
  `785b1b82738ad21cdc707e25c32f503dff9f7e3e978191cc043f558e43c3662e`。

## 门禁结果（11 项，全部通过）

| 门禁 | 实测 |
| --- | --- |
| `same-source-run-attempt-identity` | 源码/run/attempt 三处一致（`553d1a5e`/`40086971620`/1） |
| `fixed-start-sdk-tree-and-package-file-set` | 固定起点为祖先、SDK 冻结树与产品 SQL 相等、变更全在白名单（`outside_whitelist=[]`） |
| `independent-launch-count` | 32/32（四场景各 8），≥30 |
| `every-launch-clean-exit-and-no-observation-failure` | 32 次退出码全 0，无启动失败、无观测失败 |
| `fixed-screen-window-and-border` | `1440x900x24`，窗口实测仅 `(1040, 820)` |
| `fixed-2202-original-corpus` | 2202 本、长书 312,000 字节、语料摘要与种子摘要已记录 |
| `event-driven-observation-not-polling` | 2,133 次状态写入、192 次真实重绘、标定中位 2.72ms |
| `complete-planned-sample-coverage` | 16 个指标 520/520，重复 0、越界 0、未记录 0、额外指标 0 |
| `package-identity-and-size` | payload/二进制/字体/归档四者字节与 SHA-256 齐全 |
| `rss-high-water-recorded` | 32/32 有 `VmHWM` |
| `all-samples-retained-without-filtering` | CSV 520 行 = 结果 520 = 聚合 520 |

## 工件与作业身份

| 项目 | 值 |
| --- | --- |
| run / attempt | `40086971620` / 1 |
| 采样作业 | `120851788112`（10:42:25→10:46:39Z，success） |
| 核验作业 | `120852600194`（10:46:41→10:46:56Z，success） |
| 工件名 | `reader-perf-gtk-40086971620-1` |
| 工件 ID | 12557169378 |
| 工件字节 | 2,511,534 |
| 工件 digest | `sha256:e55046651afb3ef664c5488589b670a531db936cd1f558d368660b5e3d1217c7` |
| 下载后实算 ZIP SHA-256 | `e55046651afb3ef664c5488589b670a531db936cd1f558d368660b5e3d1217c7`（与 API digest 一致） |
| 成员数 / 清单数 | 138 / 137（另加 `bundle.json` 自身） |
| 有效期 | 2027-01-22T10:42:22Z（未过期） |

核验作业在本 run 内用 `gh api` 下载自己的工件 ZIP，重算 ZIP 摘要与全部成员摘要，
并复核报告身份、计划覆盖、未过滤与冻结树；缺项、过期、跨源码、跨 attempt、摘要不符
一律拒绝。原始 CSV/JSON、逐次启动日志、`xwininfo` 窗口树、环境与包体清单都在工件内。

## 保留的失败尝试

| run | 源码 | 结论 | 根因与处置 |
| --- | --- | --- | --- |
| 40076732656 | `e282039f` | 取消（不作证据） | 导入完成判定误用"有界书架行数"（恒为 50）→ 每次导入等满 300s；12 次启动后为取日志取消。改为按"已应用的新书 ID + 非 busy/saving"判定。 |
| 40079933810 | `1c4b45a9` | 取消（不作证据） | 修复后 32 次启动与 520 样本已完成，取消落在"保留原始日志"步骤；未作为证据。 |
| 40081042286 | `e54e2dbc` | 取消（不作证据） | 导入期"缩放→重绘"探针每次等满 60s：冻结宿主不保证 resize 重绘。改为"缩放→主循环观测应答"并记录 `paint_delta`。 |
| 40083621487 | `b0b6b998` | 失败 | 清理命令 `pkill -f xclip` 误杀承载脚本的 bash（命令行含该串）→ 采样步骤 143；改为 `pkill -x xclip`。同 run 汇总脚本 `sorted(coverage)` 解包错误。 |
| 40084494437 | `355a7a21` | 失败 | 核验拒绝：证据目录内的宿主 `HOME` 隐藏文件（`.dbus/`、`.local/`）被上传动作丢弃，与清单不一致。把宿主 `HOME`/`XDG` 移出证据目录。 |
| 40085263230 | `a30e014e` | 失败 | 核验拒绝：`report.metrics` 的 `expected` 误写为整条覆盖记录。改为计划条数并加形状断言。 |
| 40085328680 | `b10ecdcf` | 失败 | 同上（该 run 早于修复）。 |
| 40086173841 | `7d74faf3` | 成功但被取代 | 11 项门禁通过，但 `import_input_response` 出现 −0.325ms 的注入前观测归因；加入"注入前观测不计入该键"保护后以 `553d1a5e` 复跑。 |

上述 run 的工件与日志保留在 Actions 中，不作为本包通过证据；只有
`553d1a5e` / run `40086971620` / attempt 1 被登记为实现证据。

## 声明范围

已授予（同 run 实测）：

- 2202 本书库上的 GTK 产品首屏数据到达（50 行有界书架）、首个按键应答与键盘选择移动；
- 标题/作者/空结果/清空四类搜索的端到端响应；
- 从书架打开长书、连续翻页/回翻的端到端响应，并附真实重绘时刻；
- 继续阅读（进程重启恢复阅读帧）的端到端响应与首画；
- 导入期间的按键与缩放主循环应答（worker 忙碌期）；
- 进程 RSS 高水位观测值与包体字节/摘要；
- 事件驱动的真实重绘计数（192 次），以及"注入前观测不计入"的归因规则。

未授予：

- frame-clock 帧间隔、帧时间百分位、丢帧/掉帧统计（冻结宿主不暴露逐帧时钟）；
- 任何新的 CPU/RSS/延迟通过阈值、SDK 冻结预算或产品硬预算；
- 真机（真实显示器/合成器）流畅性、不同 GTK 主题或其它 runner 的可比性；
- 读屏/无障碍验收、内存恒定、整体产品完成；
- 其它 15 路或既有 owner 的能力背书。

## 重跑方式

本包脚本与宿主解耦，root 可在新的共同源码上重跑：

```sh
cmake --preset reading-library && cmake --build --preset reading-library && cmake --install build/reading-library
cmake -S apps/reader/desktop -B build/perf-desktop -G Ninja -DCMAKE_BUILD_TYPE=Release \
  -DEXR_SDK="$PWD/build/reading-library/stage" -DEXR_READER_BUILD_GTK=ON \
  -DEXR_READER_FIXTURES="$PWD/tests/fixtures"
cmake --build build/perf-desktop --parallel 4
python3 tools/build_linux_host.py --sdk build/reading-library/stage \
  --binary build/perf-desktop/gtk-host/exreader-linux --output build/perf-package
cmake -S tests/reader_perf_gtk -B build/perf-probe -G Ninja -DCMAKE_BUILD_TYPE=Release \
  -DEXR_SDK="$PWD/build/reading-library/stage"
cmake --build build/perf-probe --parallel 4
# Xvfb :99 -screen 0 1440x900x24 + openbox 之后：
python3 tests/reader_perf_gtk/sample.py --payload build/perf-package/EXReader-Linux \
  --tarball "$PWD/build/perf-package/EXReader-Linux.tar.gz" --seed build/perf-probe/seed_library \
  --output build/perf-evidence --launches 32
python3 tests/reader_perf_gtk/summarize.py --output build/perf-evidence --guards <guards.json>
python3 tests/reader_perf_gtk/verify.py --output build/perf-verify
```

采样器只要求安装后公共 SDK 与真实 X 服务器；失败、超时与缺样一律如实失败并保留原始样本。
