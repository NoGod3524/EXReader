# 产品性能同源观测入口

产品计划的 F08 仍待验收：产品 UI 的帧时间、内存和首次可交互预算须在固定设备及书库规模下测量并经批准冻结。SDK 已有预算和真实文档引擎基线见 `docs/READING-REAL-PERFORMANCE.md`、`docs/READING-CPU-BASELINES.md`；它们不替代 UI 预算。这里不新增阈值。

## 可复用测量与边界

原始 `reader-perf-windows.yml`、`reader-perf-gtk.yml` 及其原验证器、GTK 3.40 探针保留原有固定起点、冻结树和文件白名单检查。下列独立组合入口以当前实际源码和组件身份为依据，观测完整性检查不证明旧冻结门禁通过，也不覆盖原门禁。路径拆分后的入口已进行轻量协议校验，下一次需要组合测量时再执行完整采样；下列历史结果仍属于当时运行的源码和原工作流路径。

- Windows：`.github/workflows/reader-composition-perf-windows.yml` 支持手动触发和 `workflow_call`，以调用者源码构建 3.41 SDK 和实际桌面宿主，使用 `tests/windows_host/seed_shelf.c` 生成的 2202 本 SDK 原件，测量首屏、分页、搜索、翻页、恢复、导入响应和进程工作集。它记录源码、组件树、可执行文件、字体、语料、环境、逐进程结果和打包清单；不是帧时间。历史实测及 16 MiB TXT 拒绝见 `docs/READER-PERF-WINDOWS.md`。
- Linux GTK：`.github/workflows/reader-composition-perf-gtk.yml` 支持手动触发和 `workflow_call`，使用 2202 本 SDK 原件、真实 X11 输入及宿主观测；汇总所有计划样本、RSS、包身份和环境，并以独立作业核对同次工件。没有帧时钟数据；旧实测见 `docs/READER-PERF-GTK.md`。
- Android：`tools/run_reader_shelf_ui.py` 和 `.github/workflows/reader-shelf-android.yml` 已有 2202 本真实 SDK 原件与模拟器进程 PSS 原始采样；`tools/check_reader_shelf_android.py` 明确 `performance_accepted=false`、`physical_device_execution=false`。原工作流固定旧 SDK 和宿主树，不能直接将历史结果视作当前源码的性能结果。
- Apple：`tests/apple_host/shelf/collect_shelf_evidence.py` 和 `.github/workflows/reader-apple-shelf.yml` 已记录 2202 本原件、原生布局观测、进程峰值 RSS、程序文件散列和运行目标；报告明确无硬性能预算或真机授予。原工作流按分支选择旧 SDK/检查，需适配最终源码后再运行。

两个桌面入口当前构建的宿主功能选项以各自构建日志和 CMakeCache 为准；这不是最终全部功能配置的包。汇总者必须核对所测程序与最终交付包的散列、源码 SHA、运行和 attempt，再将其与目标设备、书库、可交互定义及获批准预算逐项关联。不同 runner 的绝对数值不可直接当作同设备对比。保留失败、原始记录及日志，不从观测完整性推导性能达标，也不从模拟器推导真机达标。

调用示例（在最终源码的工作流中调用对应文件）：

```yaml
jobs:
  windows-observation:
    uses: ./.github/workflows/reader-composition-perf-windows.yml
  gtk-observation:
    uses: ./.github/workflows/reader-composition-perf-gtk.yml
```

这两个入口分别构建程序，并非接收外部已发布包；若最终交付包由其他构建产生，必须核对实际包身份，不能仅凭源码相同授予同一包。Android、Apple 和帧级采样仍需要在最终源码与实际目标上完成；不能以这些桌面结果标记 F08 或六平台通过。

## 2026-10-26 当前组合 GTK 观测

源码 `c11b8cfc7d8872db22f967b919cf650f58efbb2a`，Actions [40381215897](https://github.com/NoGod3524/EXReader/actions/runs/40381215897)，attempt 1：Linux `ubuntu-22.04`、Xvfb，32 次启动、520/520 样本，11 项观测完整性检查与独立工件身份核验通过。包中程序 SHA-256 `a31ca88780befa05fe06ef267dff0c7062b3c821f409f287fdc22a0989207aca`，归档 SHA-256 `10fc2387ec67e056a798c5fac0ff807526b83bbb6428b7c728cd37cc2bd11335`，27 文件共 25,873,656 字节。工件 `reader-perf-gtk-40381215897-1`，ID `12678228026`，SHA-256 `01907e96ac668d8d71fe3371c03051644fd39951eb0de1910c35ba7b663e4985`，有效期至 2027-01-24。

首个 50 行书架从启动到观测 p50/p95/max 为 147.066/247.908/3492.426 ms（24 次）；下一页输入至首次绘制 p50/p95/max 为 33.807/36.480/40.829 ms（112 次）；进程 RSS 高水位最大 208,604 KiB。完整原始样本、环境、冷/热策略和包配置在工件中；这些是端到端观测，不是逐帧时间，且未冻结 UI 数值预算。早期失败 [40380951236](https://github.com/NoGod3524/EXReader/actions/runs/40380951236) 保留：打包工具当时仍默认 3.40，后续显式传入 3.41。

## 2026-10-26 当前组合 Windows 观测

源码 `c11b8cfc7d8872db22f967b919cf650f58efbb2a`，Actions [40381230058](https://github.com/NoGod3524/EXReader/actions/runs/40381230058)，attempt 1：Windows Server 2022、AMD EPYC 9V74、4 逻辑处理器。实际打包程序 SDK 3.41/ABI 1，自检 26 项；EXE 为 7,224,832 字节，SHA-256 `28533c0bc7573c3b78a054fc30cff1d93f0270b931518194ce850643fee93ccb`。48 次测量启动，冷书架、热书架、阅读、EPUB 导入各 12 次，同源完整性门通过；`performance_accepted=false`。

热书架首屏可交互 p50/p95/max 为 136.961/151.575/151.575 ms（12 次）；书内翻页 p50/p95/max 为 24.644/33.212/34.582 ms（96 次）；阅读组进程工作集峰值 p50/p95/max 为 48,179,200/48,340,992/48,340,992 字节。测量是控件状态的端到端延迟，不是帧时间。原 16 MiB TXT 输入诊断依旧为 `import_rejected`，该 TXT 测量组跳过；EPUB 是单独组，不能代替 TXT 结论。

原始工件 `reader-perf-windows-40381230058-1`，ID `12677938567`，SHA-256 `9eb4492cd034423a034406afc3f4c98433c1bbf8cbb60ba6d7753eda9e477c88`，有效期至 2027-01-24；原始工件经 Actions [40382511094](https://github.com/NoGod3524/EXReader/actions/runs/40382511094) 下载解析。旧版运行 [40380841008](https://github.com/NoGod3524/EXReader/actions/runs/40380841008) 在宿主构建阶段失败，保留其日志；后续运行显式选择 3.41。

## 组合入口轻量校验

源码 `be53824393b3621a233181dfe01d7094dd20ed65`，[Actions 40383580356](https://github.com/NoGod3524/EXReader/actions/runs/40383580356) attempt 1 成功：actionlint 解析两个入口；Python 编译检查、引用文件和 CMake 种子路径检查通过；GTK 采样计划和百分位计算、直接运行及可复用调用的模拟身份检查通过，并拒绝跨 attempt 或被修改的工件；Windows 缺失或跨源码证据被拒绝。原冻结工作流、验证器和探针与起点 `11042994` 完全一致。记录工件 `reader-composition-perf-protocol-40383580356-1`，ID `12678184505`，SHA-256 `b954d55f4bd7b8927a7fcb92625a1a8f26ef18431df09a106ba977ce4d540ed6`。

这些是合成证据协议检查，没有构建产品、运行实际可复用调用或重新采样；真实宿主及产物身份仍须由下次组合测量核验。
## 2026-10-26 完整桌面配置性能推进

独立分支以共同源码 `a19fef7d7cdb0be90b0e54b92910502016c33df9` 为起点。新增完整产品性能工作流和采样工具，未修改原始 SDK 冻结门禁。Windows 复用 C09 的 wave-3、原生模块和内容绑定构建，测量 ZIP 解压后的程序；GTK 复用 C10 的非紧凑 wave-3 构建，包含账号、设置、搜索、导航、阅读记录、批量导入、拖入、页面背景和五个工具，测量 tar.gz 解压后的程序。两者使用各自既有的 2202 本公共 SDK 原件，记录实际程序、包和构建配置身份。

### Windows 首轮完整配置

源码 `77a54227a78b0160e98609032e7ceef87fb29d00`，[Actions 40397287811](https://github.com/NoGod3524/EXReader/actions/runs/40397287811)，attempt 1：Windows Server 2022，AMD EPYC 7763，4 逻辑处理器。C09 完整构建、原生回归、解压运行、48 次性能启动与同源/包身份核对成功；冷、热书架、阅读、EPUB 导入各 12 次。程序 SHA-256 `1866af855e2264986ccf74f4d1f4ee1b62d3f3e9e206f3fbc84346ce5d8606cd`；ZIP 17,503,178 字节，SHA-256 `ce3d9424136b68e5e9ebfc9eb2acd47fe5cdbf26d30193108d3ef73c956f1009`；工件 ID `12687463168`，digest `sha256:3c9213a918b14332ce362ceb956d5595d75905c95ff20d34ccae35c047e10843`。原始工件由 [Actions 40399155792](https://github.com/NoGod3524/EXReader/actions/runs/40399155792) 验证并解析。

冷书架首屏可交互 p50/p95 5089.170/5156.590 ms；热书架 169.021/179.770 ms；书内翻页 96 次 p50/p95 33.367/44.238 ms；阅读组峰值工作集 p95 50,102,272 字节。冷/热只描述 profile 策略，非受控磁盘缓存。原 16 MiB TXT 仍被诊断为导入拒绝，故该测量组保留跳过；EPUB 为独立组。完整宿主的导入使用原生文件选择器，复用既有驱动；IDOK 到观察空闲的时间包含驱动至少 0.4 秒等待，不能解释为纯解析耗时。`performance_accepted=false`；没有实际逐帧数据。

旧驱动失败 [40395267422](https://github.com/NoGod3524/EXReader/actions/runs/40395267422) 和 [40395861060](https://github.com/NoGod3524/EXReader/actions/runs/40395861060) 已保留：完整宿主走系统文件选择器，而旧工具写隐藏路径框。补充的空库诊断 [40396805624](https://github.com/NoGod3524/EXReader/actions/runs/40396805624) 仅用于检查窗口树，不能作为 2202 本测量。

### GTK 首轮和帧时钟探针

源码 `4087049ece56c94317d779b612360c58aec2eee6`，[Actions 40395860891](https://github.com/NoGod3524/EXReader/actions/runs/40395860891) 完成 32 启动和全部 520 个计划样本，但汇总拒绝：实际完整宿主窗口为 1088×820，而旧裁剪宿主口径要求 1040×820。原失败工件 ID `12686294663`、digest `sha256:402308b441aa8e65f1de76325f4c801c83d2ef7f4f0faba2e845383451d1c334`，仍保留；不能称该轮完整性通过。完整宿主独立入口现改为固定 1088×820，不改原冻结门禁。

性能测试专用 GDK 探针通过 [Actions 40397480865](https://github.com/NoGod3524/EXReader/actions/runs/40397480865) 的独立 GTK workload 检查，采集到 20 条 `after-paint` 时钟记录。新完整包入口使用外部预加载探针记录每进程原始时钟和单调时间，存在测量开销；它测的是 GTK 工具包绘制节拍，不是帧渲染耗时或物理屏幕呈现。探针与完整包同源运行结果须以相应 Actions 原始记录为准，不能由合成 workload 转授。

### Windows 冷启动分段观测

原始程序仍是上述源码 `77a54227a78b0160e98609032e7ceef87fb29d00`、构建 run `40397287811` 的完整 ZIP 和 EXE；新观测脚本源码 `9c386e0533cd6ded8699eec7f72d46a88642ce9c`，[Actions 40399615507](https://github.com/NoGod3524/EXReader/actions/runs/40399615507)，attempt 1。该次先核验原工件与 EXE、ZIP 散列，再用同一 2202 本 SDK 种子分别创建 8 份新 profile；4 次只观测窗口和控件，另外 4 次每约 100 ms 以零等待只读查询本机目录映射数量。原始证据工件 ID `12688386499`，digest `sha256:a98b0160d27bf6820931f20ed4206bb00b0c5c29fe21484ba7aef324fa27158d`；由 [Actions 40399864380](https://github.com/NoGod3524/EXReader/actions/runs/40399864380) 校验并汇总。环境为 Windows Server 2022、4 逻辑处理器、1024×768、96 DPI；不同于原测量的 runner，磁盘缓存和同宿负载未受控。

未查询目录的 4 次：窗口出现中位 24.704 ms（范围 24.072–69.824），首个 UI 往返中位 33.993 ms（32.814–461.754），首屏可交互中位 5215.902 ms（5142.401–5685.260）。窗口创建前的过程包含 SDK 书库与字体打开，因此窗口时间是这两项及进程启动的合计上界，不能分出各自耗时。查询目录的 4 次首屏可交互中位 5420.428 ms（5275.499–5476.137）；只读查询可能与写入竞争，这个小样本不能归因于查询本身。

4 次目录轮询中有 3 次在首屏前观测到映射数达到 2202，查询结束距首屏可交互分别约 10.6、15.2、43.3 ms；第 4 次未在采样间隔内读到 2202。窗口创建到可交互的间隔占主导，目录映射填充与它高度重合，值得优先分析，但本观测不能把时间分配给 SDK 全量枚举、逐条 `has_local`、插入事务、UI 调度或其他操作。源码中的 `EXReaderShelfSnapshot` 也用于最初 SDK 列表，早期 `first_product_snapshot` 字段并非产品分页完成；metadata 控件最初可能短暂启用，也不是修复完成时刻。下一步应通过精确分段跟踪验证，再评估批量查询/事务等优化，并保留映射修复、取消和崩溃恢复语义；不据这组数据冻结预算。

**两种 profile 状态须分开解释。** 上述冷书架及 8 次分段观测均复制只有 SDK 原件的种子，并删除产品目录；它们覆盖首次创建产品目录和建立 2202 本映射，不能外推为已有目录的每次启动。原 `40397287811` 的热书架组先运行一次目录准备，核对产品目录中 2202 本标题与源字节，再复用该目录进行 12 次新进程启动；首屏可交互 p50/p95 为 169.021/179.770 ms。该旧轮没有独立统计 `reader_local_books` 全量映射数，且操作系统缓存仍未受控，因此不把它称为磁盘冷态复启基线。后续测量入口在准备阶段额外要求 2202 条不同 SDK ID 的本地映射均关联未删除产品书目，失败即拒绝样本；这不改变宿主的修复、取消或崩溃恢复实现，也不替代崩溃恢复专项验证。
