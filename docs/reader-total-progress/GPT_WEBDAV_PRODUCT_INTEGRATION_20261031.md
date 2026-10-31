# GPT WebDAV 产品接入：入场核查与实现合同

日期：2026-10-31（America/New_York）；远端核查时间约 2026-10-31 05:40 UTC。
状态：实施已获授权；生产实现被 G1/G2 上游证据依赖阻塞。
本提交只增加本文件，未接入生产代码，未运行或调度构建、测试、fixture、benchmark 或 ZIP 解析。

## 授权与交付范围

本聊天用户已明确：“我授权接下来你所有需要授权的东西，你全权接管此任务”。
该授权覆盖本包文件修改、新增 public module API、独占功能分支、Git/gh、
提交/推送及约定的 GitHub Actions 验证。已批准事项不再重复申请。
上游证据是否完整、独立审计是否接受仍须以实际结果填写，授权不能代替证据。

目标仅为 Linux GTK 的 session → sync → WebDAV managed transport staging/alias。
高层 sync private_file、上传 snapshot、GTK import snapshot、永久根退休、
其他宿主、断电语义以及完整 F10 不由本包授予。
正式计分沿用总验收 owner 的 95/108；本包不改正式台账。

功能分支：`codex/gpt-webdav-product-integration-20261031`。
产品固定基线：`8232e91cd7b9296dfcdd3096b96317eb3fa1008a`。
拟用源码工作目录：
`/data/workspace/exreader-gpt-webdav-product-integration-20261031`。
在 G1/G2 完成前不物化生产 worktree；本次文档使用已连接 GitHub 工具写入独占分支。

## G0–G5 实测记录

| Gate | 状态 | 本次证据与剩余条件 |
|---|---|---|
| G0 实施授权 | satisfied | 本聊天上述用户授权；文件范围包含下列两个经源码核查确认的补充路径。 |
| G1 上游原始证据补齐 | blocked | 远端 core 仍为 dba079b5，tests 分支仍为 d69bae31；12da717c→d69bae31 只修改封存文档，未补 run.py/worker.c 的原始观测字段。 |
| G2 独立审计接受 | blocked | 远端 matching refs/ls-remote 均未发现审计分支；gh run list 对该分支返回 []。本地审计 HEAD deec5642 的文档明确 prepared、no audit result claimed。不存在可引用的已接受 run/artifact。 |
| G3 路径占用 | partial | H03/J03 相对其固定基线的完整远端 diff 无生产路径改动。Claude 状态查询显示原 WebDAV 会话 idle，同时“EXReader 三包收尾任务”busy；这不能证明后者没有未提交的共享路径写入，生产写入前仍须消歧实际 writer。 |
| G4 合同与组合 | prepared | 下文固定根池、注册表、线程、状态与新 API 方案；core 接受身份尚待 G2，最终组合 SHA 尚不存在。 |
| G5 环境与验证入口 | partial | 指定 DC/Instabox Git/gh 通路可读；已有 GTK 安装构建 recipe。VM 尚有 91,212 个 inode、3,556,748 KiB 可用；新 worktree 未创建。最终 SDK pin、候选 source guard 和已审计组合绑定须随生产入场完成。 |

只读执行路径：Desktop Commander `lap25002` /
`d55d0477-84bb-4425-8708-5a3ecacce78b` →
`npx --yes instabox@0.8.52 exec m_agqxv2s72g5vwdtsifu5cnmml4 --json` →
`/data/workspace/exreader-dot-integration-candidate-20261031`。
该现有树仅作读取来源；未切分支、改 index 或写入。
构建与运行验证全部留在 Actions。

### 上游固定身份

- core：`dba079b550f9ec83054e6b7b0b7475f43bc1739f`。
- 受测 tests：`12da717cef38c90ae2097e52d33f7b3682aef043`。
- tests 远端封存 HEAD：`d69bae312fd0791dac119509437fb29abc92a25c`。
- producer：run `41170057297` / attempt `1`。
- Linux job `124445872128`、macOS job `124445872050`，均 completed/success。
- audit 本地 HEAD：`deec56424e494848a17c799a357525f0852fed62`；
  分支 `codex/dot-webdav-managed-cleanup-audit-20261031`；
  worktree `/data/workspace/exreader-dot-webdav-managed-cleanup-audit-20261031`。
  本地存在不代表已发布或已通过。

| 平台 | artifact | 名称 | bytes | API digest SHA-256 |
|---|---|---|---:|---|
| Linux | 13030965993 | webdav-managed-cleanup-Linux-41170057297-1 | 86807 | 25b95345c6607c6fc0fadd54c95bdd62c515bcc460498664bddabdf88c88b442 |
| macOS | 13030352879 | webdav-managed-cleanup-macOS-41170057297-1 | 74101 | 72ac0c1e56854a06669e01b7e9714605562c03275e482853d0088901f8d566fe |

本次重核了 GitHub artifact 元数据和 job 终态；未下载或解包 ZIP。
以上不是独立重算结论。

### H03/J03 的已提交路径

两包共同输入为 `7f15fe49374cd9389e2106837351d4bbd5e56113`。

- H03 HEAD `22e84472ae684c901ab20a1f52c8601568ef7e0c`：
  完整差异仅 `docs/CLAUDE-H03-ORIGINAL-RETRY.md`。
- J03 HEAD `8b1328f105b25c46711a11348f2ca313874947e4`：
  完整差异为自己的 workflow、`tools/validation/claude-j03-gtk-removed-ui-20261031/`
  和 `docs/validation/claude-j03-gtk-removed-ui-20261031/`，无生产文件。
- 不把这些专项结果转授本包，也不修改其测试、报告或 workflow。
- 原 WebDAV 会话 `5ca9ca31-721a-4130-8579-afc8f7116d92` 查询为 idle。
  未启动或恢复 Claude/Codex worker。
- `claude logs` 对当前交互会话名返回 “No job matching”；
  未据此声称已检查其最近写入，也未改用其他入口启动该会话。

### 台账身份差异

handoff 指定的正式 catalog blob 为
`e0c52bf139da2374cf58dbce40ae6c093a59f39d`。
产品基线 `8232e91c` 内同路径实际 blob 为
`c5d38ca7545c1fa0d2b03d1846ba010cea196f13`。

只读 blob diff 显示两者的宿主/F06 证据及 verified/partial 状态不同。
因此本包以 handoff 的正式台账作为计分引用，以固定产品基线作为实现输入；
不声称产品树已经携带正式台账，不通过复制 catalog 来消除差异。

## 已确认的两个接入冲突

### sync 目标名称与 core leaf 合同

产品基线 `apps/reader/sync/src/sync.cpp:117` 创建
`.reader-sync-<id>.tmp`，第 153 行把该名字交给
`exr_webdav_download_file`。

core `extras/webdav-cleanup/src/cleanup_posix.c:261–270` 的
`wc_leaf` 只允许首字符为 ASCII 字母、数字、下划线或连字符；
第 592 行的 `exr_wc_publish_at` 使用该检查。
因此仅在 DAV 内切换 staging 会让真实 sync 下载在发布时被拒绝。

最小修正：只在显式 managed client 的下载路径中选择
`reader-sync-<id>.tmp`。高层 private_file 的所有权、hash 验证、
原始 wire 与清理生命周期不变；未启用 managed 的调用保持原命名。
不新增未记账中转目标，不修改 core 的 leaf 合同。

新增写权：`apps/reader/sync/src/sync.cpp`。
使用新 managed 查询能力辨别 client，不改旧 sync config 结构体。

### 安装包的静态依赖

`apps/reader/sync/CMakeLists.txt` 通过
`find_package(EXReaderWebDAV 0.2.0 EXACT)` 导入旧基础 target。
managed 实现仍由同一 client 的实现承载，静态库新增 cleanup 依赖后，
基础 package config 必须在载入导出 target 前条件解析该依赖。

新增写权：`extras/webdav/EXReaderWebDAVConfig.cmake.in`。
仅 managed 构建启用该依赖；单独安装的旧构建继续保持原依赖图。
新增 Managed config 负责能力及同安装来源检查，不能用源码直链代替安装包。

## 文件与 owner 清单

本包 writer 为本聊天 GPT。下列是获准的最大清单，实际只改所需项；
最终证据必须列出实际 diff，不把未改文件计为实现。

| 分组 | 路径 | 所有权/用法 |
|---|---|---|
| DAV | extras/webdav/src/webdav.cpp | GPT；显式 managed client 与原下载公共入口 |
| DAV | extras/webdav/CMakeLists.txt | GPT；默认关闭的能力及安装依赖 |
| DAV | extras/webdav/EXReaderWebDAVConfig.cmake.in | GPT；本次补充，条件加载 cleanup 静态依赖 |
| DAV 新增 | extras/webdav/include/exr_webdav_managed.h | GPT；新公共接口与独立结构体 |
| DAV 新增 | extras/webdav/src/webdav_managed_posix.inc | GPT；有界根池、注册表、managed staging |
| DAV 新增 | extras/webdav/EXReaderWebDAVManagedConfig.cmake.in | GPT；安装能力包 |
| Session | apps/reader/session/src/session.cpp | GPT；worker 内启用与状态复制 |
| Session | apps/reader/session/CMakeLists.txt | GPT；显式 managed 能力构建 |
| Session 新增 | apps/reader/session/include/reader_session_managed.h | GPT；新创建/观察接口，不改旧结构体 |
| Session 新增 | apps/reader/session/EXReaderSessionManagedConfig.cmake.in | GPT；安装能力包 |
| Sync 补充 | apps/reader/sync/src/sync.cpp | GPT；仅 managed 下载目标 leaf 适配 |
| GTK | examples/linux/accounts_ui.inc | GPT；网络入口、状态/Retry/关闭接线；写前核实际占用 |
| GTK | examples/linux/reader.c | GPT；启动恢复和主窗口关闭接线；写前核实际占用 |
| GTK | examples/linux/accounts.inc | 仅必要时使用 handoff 已授权范围；当前设计无需改 |
| GTK | examples/linux/reading.c | 仅必要时使用 handoff 已授权范围；当前设计无需改 |
| GTK | examples/linux/reading.h | 仅必要时使用 handoff 已授权范围；当前设计无需改 |
| GTK 构建 | apps/reader/desktop/CMakeLists.txt | GPT；单宿主显式开关、公共安装包 |
| GTK 新增 | examples/linux/webdav_managed_owner.inc | GPT；异步启动恢复与 UI 状态持有 |
| 产品验证新增 | tests/gtk_managed_webdav_20261031/ | GPT；本包矩阵、组合身份检查、原始证据与包检查 |
| Workflow 新增 | .github/workflows/gpt-webdav-product-integration-20261031.yml | GPT；固定组合 SHA、约定预算 |
| 记录新增 | docs/reader-total-progress/GPT_WEBDAV_PRODUCT_INTEGRATION_20261031.md | 本文件 |

core 原 owner 的四文件只在 G2 接受后按精确字节引入：
`extras/webdav-cleanup/CMakeLists.txt`、
`extras/webdav-cleanup/EXReaderWebDAVCleanupConfig.cmake.in`、
`extras/webdav-cleanup/include/exr_webdav_cleanup.h`、
`extras/webdav-cleanup/src/cleanup_posix.c`。
本包不改原 tests/core/audit 分支，不代推本地审计候选。

`received.inc`、SDK、旧测试和 J02 delivery.py 不在本次实现写入范围。
当前没有通过新增 package 名称复制原 30-case 或原 audit。

## 根池与注册表合同

这是实现前固定的设计，尚无运行验证。

1. 每个私有 profile 一个 managed namespace；路径必须位于原 private sync
   工作目录所在本地文件系统，以满足 no-replace hard-link 发布。
   拒绝 symlink、错误权限、错误 profile binding 和跨设备发布。
2. 最多 16 个登记根，每根最多 64 个 lifetime slots，总上限 1024。
   这是事务次数上限，不是书籍数；失败的分配也可能消耗容量。
   16 份固定 receipt 合计 66,560 字节；注册表限制 16 KiB，
   profile 规范路径输入限制 8192 字节，登记项数量固定有界。
3. 不预建 16 根；需要新容量时才登记。恢复只遍历已登记的最多 16 项，
   每根最多检查 64 slots，总检查上限 1024；不按目录前缀认领。
4. registry 由永久、私有的 registry lock 保证单 writer；
   原 core root 的 .lock 永不删除或替换。
   full、pending、uncertain、unbound 的登记项永不从池中遗忘。
5. 先持久发布 ALLOCATING(leaf) 登记，再调用 core create；
   成功得到 UUID 后持久发布 READY(leaf, UUID)，然后才允许 begin。
   跨进程看到 ALLOCATING 时不从磁盘反推 UUID、不收养该目录；
   标为 unbound/pending 并保留其容量占位。
6. registry 更新采用独占创建 next、写全、fsync 文件、原子 rename、
   fsync 父目录。任一步不确定即停止当前写入流程，不把错误当成 ENOENT。
   当前进程不得在未确认 READY 发布成功时开始事务。
7. registry 的残留规则独立于 core receipt 的已批准 amendment：
   registry next 只要存在就拒绝自动选择/删除任一版本；
   current 损坏、超限、重复 leaf/UUID、绑定不符均 fail closed。
   新进程只在有效 current 且无 next 时按登记 UUID 打开根。
8. pristine 首次创建和未知残留分开处理。已有 namespace 却没有可验证
   registry 的情况拒绝初始化覆盖；不自动清理未知文件。
9. full 或隔离根可以保留后转向另一个已登记可用根；
   有界登记仍有空位时按第 5 条创建新根。
   池耗尽明确拒绝新 managed 下载，保留书库和 pending 信息。
10. 不删除全 CLEANED 根、不复用 slot、不永久退休根；
    没有无限期回收承诺。registry 的 CRC 只检测损坏，不提供同 UID 认证。

| 崩溃窗口 | 新进程行为 |
|---|---|
| 初始 namespace 尚未形成有效 registry | 拒绝自动初始化覆盖，保留原物 |
| ALLOCATING 已发布，core create 未确认 | 保留登记和 leaf，显示 unbound/pending |
| core 已创建，UUID 尚未确认入 registry | 同上，不读取 receipt 冒充预期 UUID |
| READY 有效且无 registry next | 用登记 UUID 调 core open，再有界 recover |
| 任意 registry next 残留或 registry 损坏 | 拒绝 managed 写入，保留两份记录 |
| core receipt uncertain / PUBLISH_INTENT | 按原合同隔离/保留，不重新发布该事务 |
| 已发布但 alias 清理失败 | 保留 published 事实；恢复只触及受控 alias |

## 线程、关闭与 public module API

- GTK 主线程只持有配置、复制后的快照和异步生命周期状态。
- 启动恢复在独立后台 owner 中调用 installed managed API；
  root 在该 worker 内创建/打开/恢复/关闭，不跨线程传 handle。
  启动恢复不需要网络凭据、不持有 SDK handle。
- 启动恢复 owner 完成关闭后，session 网络 worker 才能取得同一根池。
  session 的 DAV/root/tx 由同一网络 worker 创建、使用、销毁。
- SDK owner 保留现有书库职责；managed 清理失败不阻塞离线阅读。
- Close/Cancel/Disconnect 使用现有 request_close → worker 释放 →
  CLOSED → destroy/join 顺序。启动恢复 owner 也需关闭确认；
  回调使用现有 generation 检查，不能在 worker 仍使用状态时销毁 UI 数据。
- 新 DAV public module 提供显式启用、能力查询、只读快照和恢复能力；
  新 session module 提供 managed raw-v3 创建和线程安全快照观察。
  所有扩展结构单独定义，不改变旧结构布局、旧默认行为或冻结 ABI。
- 使用 EXReaderWebDAVCleanup 0.1.0 的 installed header/target。
  Managed capability 的安装来源必须与基础 DAV/session 一致，
  并拒绝混用不同安装前缀。测试 hook 不进入安装包。

## 发布、清理与 UI 映射

| 事实 | 下载/会话处理 | 用户可见状态 |
|---|---|---|
| 未发布且失败/取消 | 保留原失败/取消语义；活动 OWNED/SEALED 按合同 abandon | 未完成/已取消 |
| 已发布且清理完成 | published=1，传输成功 | 正常同步状态 |
| 已发布且清理 pending | 仍为传输成功；单独累计 pending | 已下载，临时文件待清理 |
| 已发布且 receipt uncertain | published=1 不被改写；停止对该根的后续 mutation | 清理记录需处理 |
| 未确定发布结果/PUBLISH_INTENT | 不猜测结果，不重发该事务 | 状态未确定，保留文件 |
| root busy/refused | 明确原因；不得落回旧临时文件实现 | 清理目录忙/无法使用 |
| 根池耗尽 | 明确容量拒绝，保持书库可读 | 临时下载容量已用完 |

快照按根保存 pending/uncertain/refused/capacity，不能用最后一次成功覆盖旧根告警。
清理重试与网络同步重试分开：清理失败不触发重复下载、重复导入或远端写入。
HTTPS、origin 绑定、重定向拒绝、deadline、大小上限、流式传输、
no-replace、完整 hash 与原始 wire 仍走原链路。

## 验证安排与当前执行状态

预算每轮：Linux 产品构建与矩阵 120 分钟，Windows/macOS 旧 API
兼容各 30 分钟，证据检查 15 分钟；初始一轮加最多一次定点修正。
本包当前已用 0 轮，未 dispatch。

原 source guard 绑定自己的 allowed_paths 与生产字节；
本包必须提交独立、精确的组合清单并保留旧门，不修改旧断言来放行新候选。
完整产品、core、tests、SDK、安装包和实际 GTK 二进制身份分列。

| 本包 case | 当前状态 |
|---|---|
| GTK 发起真实 HTTPS session→sync→DAV 下载并打开书籍 | blocked: G1/G2 |
| 正常退出重开，UUID/目标/书库保持 | blocked: G1/G2 |
| 发布前取消、断网、HTTP 失败 | blocked: G1/G2 |
| 发布后真实非 root cleanup EACCES | blocked: G1/G2 |
| 新进程恢复两次，第二次幂等 | blocked: G1/G2 |
| PUBLISH_INTENT / receipt uncertain | blocked: G1/G2 |
| Close/Cancel/Disconnect 连续操作与关窗 | blocked: G1/G2 |
| 错 UUID、坏 registry、symlink、未知残留 | blocked: G1/G2 |
| 第 64/65 slot、跨根继续、16 根池耗尽 | blocked: G1/G2 |
| 一个根 pending、一个满、一个可用的重启调度 | blocked: G1/G2 |
| 重复/已存在目标不替换、不重复导入 | blocked: G1/G2 |
| 清理阻塞期间 GTK 离线阅读 | blocked: G1/G2 |
| 无 hook 的 installed GTK 入口、取消、重开、身份绑定 | blocked: G1/G2 |
| Windows/macOS 未启用 managed 的旧 API 构建/consumer | not-run |

证据必须保存每 case 的进程 exit/signal、非 root errno/身份/权限、
目标前后 dev/ino/nlink/size/hash、原始 receipt/next、
恢复报告、HTTPS 请求、真实调用链和 UI/AT-SPI 观测。
故障构建、installed consumer、direct-source hookworker、
无 hook 安装产品分别标识，不互相代替。

## 解除上游阻塞所需的具体交付

1. 原 tests owner 在原 30-case 包补齐并保留原始数值：
   - SIGKILL 子进程 PID、wait/returncode；
   - published target 恢复前后的 dev/ino/size/sha256/nlink；
   - EACCES 的实际 errno、euid、目录权限、canary 观测；
   - 原始 receipt/next 字节及恢复前后状态。
   原名称、断言、超时、installed consumer/hookworker 分离和失败历史保持。
2. 固定补证后的完整 tests/core/doc SHA 和 producer run/attempt/artifacts。
3. 原独立审计 owner 交付实际远端 audit SHA、run/attempt、
   artifact ID/bytes/digest、可重算输出及 accepted/refused/pending 结论。
   本地 prepared commit 或 producer 30/30 不满足此项。
4. 更新本文件 G1/G2；核定当时的共享路径 writer 和 SDK/source guard；
   仅随后进入生产 plumbing、GTK 接线与产品矩阵。

当前结论：授权和接入设计已记录，生产闭环尚未实现或验收。
