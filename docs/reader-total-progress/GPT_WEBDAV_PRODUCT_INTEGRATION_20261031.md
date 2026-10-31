# Linux GTK WebDAV managed staging 产品接入

本聊天用户已授权实施，并进一步明确接管上游补证、独立审计、产品接入和 CI，持续到完成。
当前状态：G0–G5 已核定；生产实现及验证脚本已准备，尚待本组合的 Actions 结果。正式台账保持 95/108，不改 catalog.json。

## 上游阻塞已解决

- core 固定 dba079b550f9ec83054e6b7b0b7475f43bc1739f，四个文件逐字节引入，不改 core。
- 原 tests 分支补证 commit 711e1fc8a8c5b86f210bcddc934c479599387582，原 30 用例、断言、超时和 installed/hook 分离保留。
- producer [41174402876](https://github.com/NoGod3524/EXReader/actions/runs/41174402876) / attempt 1：Linux、macOS 各 30/30。
- Linux artifact 13031778309，114285 bytes，SHA-256 4520aae748dff728019ce865116685930cd887a3783c827c2ac3bf4422554946。
- macOS artifact 13031863107，101735 bytes，SHA-256 3c8533a40556485d8818821068fe6cceef67e83e94cd15d26d59ba431abfe2ec。
- audit source ea54eb95eafc62a2db8fec4547eab142856f9351；[41174612650](https://github.com/NoGod3524/EXReader/actions/runs/41174612650) / attempt 1；job 124459479516 success。
- audit artifact 13031974546，232564 bytes，SHA-256 88b3580ea082c941c6286dc6bb542683cc2bf75675944981b415b27462579efa。
- 实测 audit_passed=true、critical_evidence_complete=true、errors=[]；两平台各 30 项原始重算、各 8 个原控制加 10 个 raw 篡改控制，36 个负控全部拒绝。原 ZIP、逐文件 hash、固定源码和重算输出在审计 artifact 中。
- 延续原独立验证程序；原 prepared 字节保存在 a788f82b9c84ea6fab1f5e8e3f3e928b1b3be98e。新增重算由本次接手者实现，独立性为与 producer 分离的实现与 Actions 执行。
- 旧失败 41169665419、41169795520 和旧绿 41170057297 均保留，没有覆盖或转称本产品已通过。

## 入场和精确范围

G0：本聊天授权覆盖接管和完成。G1/G2：上列真实补证及审计已通过。
G3：写入只发生在本包独占 GitHub 分支 codex/gpt-webdav-product-integration-20261031；不写 Windows 共享脏树，不修改已有 VM worktree，不启动其它 writer。H03/J03 已核提交 diff 均无本包生产路径。固定基线的候选不覆盖其它 owner 的分支。
G4：固定产品基线 8232e91cd7b9296dfcdd3096b96317eb3fa1008a；已接受 core 精确四文件；16 根合同如下。
G5：GitHub API 写独占分支，指定 DC/Instabox 通路只读 Git/gh 元数据；无需新 VM worktree，不新增 inode 压力。编译、语法检查、fixture、测试和 ZIP 处理全部在 Actions。
SDK 使用独立 checkout 7271829a829bfa6aaa47b73077c493f71af27ad3，显式 3.42.0。产品代码不修改 SDK/旧 ABI/旧结构体。

准确文件清单见 tests/gtk_managed_webdav_20261031/manifest.json，共 30 个路径。
新增必要生产路径为 sync.cpp 的 managed 下载 leaf 适配，以及基础 WebDAV config 的条件静态依赖；只显式 managed 的 client 使用 reader-sync-*.tmp 目标名。
不改 received.inc、旧 tests、SDK、其他宿主、J02 delivery.py、正式 catalog。
原正式 catalog blob e0c52bf139da2374cf58dbce40ae6c093a59f39d 与产品基线旧 catalog blob c5d38ca7545c1fa0d2b03d1846ba010cea196f13 不同；本包不把旧基线视为最新正式台账。

## 实现合同

显式 Linux managed WebDAV / raw session / GTK 三层开关默认关闭。新增独立头和 capability config，不改变旧结构布局。
真实 GTK accounts_start_network → reader_session_create_managed_raw_v3 → worker → reader_sync_step_raw_v3 → 公共 WebDAV 下载入口。
已安装的 WebDAVCleanup、WebDAVManaged、SessionManaged package 参与构建。普通 consumer 与 GTK 无测试 hook；唯一故障 worker 直接编译固定同源文件，未安装，不链接产品 archive 冒充 installed consumer。

私有 canonical profile 下 webdav-managed-v1 的 registry.lock 永久持有 flock。registry 限 16 KiB；最多 16 登记根，每根 64 lifetime slots，总 1024 事务上限，失败也可能消耗 slots。
registry 持久绑定 canonical profile，先发布 ALLOCATING(leaf)，core create 后发布 READY(leaf,expected UUID)，再 begin。未知 UUID 不从 receipt 反推；未绑定项永久保留并计 pending。
注册表使用独占 next、写全、fsync、rename、目录 fsync；任何 registry.next 残留拒绝自动写入且保留。CRC 检测损坏。core 的 valid successor .receipt.next 修订保持原样，两者规则不同。
仅扫描最多 16 个已登记根，每根最多 64 slots；保留 full/pending/refused/uncertain/unbound 根，不复用 slot、不删锁、不退休根。耗尽明确拒绝，无旧临时文件回退。
发布 link 已成功时 out.published=1 和传输成功保留，cleanup EACCES/pending/receipt uncertain 单独报告。未知发布状态不重发。
HTTPS、origin、大小/时间上限、流式传输、完整 hash、raw wire、取消和 no-replace 仍走既有链。

GTK 只接收值快照；启动恢复在独立 worker 创建/恢复/关闭所有 root。网络 session 等启动恢复完成再自行取得根池。
单独 Retry cleanup 仅关闭空闲网络连接并在原 worker 离线恢复，不触发下载、导入或 PUT。UI 显示 pending、uncertain、busy、refused 和容量耗尽；离线阅读保留。
关闭走 request_close → worker 释放 → CLOSED → join/destroy；启动恢复有独立非阻塞关闭等待。
本范围只有 transport staging/alias；高层 sync private_file/snapshot、永久根退休、断电与全 F10 不由此验收。

## 产品 CI 验证计划及证据

本 workflow 仅本分支 push：Linux 上限 120 分钟，Windows/macOS 兼容各 30 分钟，独立证据 job 15 分钟。
Linux 构建完整安装依赖和实际 GTK、原 77 项 TLS 回归，25 项本包传输/故障矩阵，真实 GTK HTTPS 同步/打开/重开/pending/清理重试/强杀/关闭/有界根池/离线读取。
Windows/macOS 默认关闭 managed，原 installed TLS 用例分别 76/77 项及原异步 session 20 项保持原断言。
独立 evidence job 认证本次原始 ZIP，重算原始 receipt CRC/身份、目标保留、死亡退出码、恢复幂等和容量界限，核对实际 GTK 二进制、截图与网络记录，并运行篡改负控。
每次失败 artifacts 保留，最终完整 SHA、run/attempt、各 artifact digest 和尚存边界在实际结果后补录。

## 首轮产品运行及修复

源码 fef8bf9fd9b7c68228705cd6e20d6f56031897ab；[41176047061](https://github.com/NoGod3524/EXReader/actions/runs/41176047061) / attempt 1。
Linux job 124463711948 success：完整 GTK 构建、旧 77 项 TLS、25 项故障矩阵和真实 GTK 21 条记录通过。macOS job 124463712158 success：旧 77 项 TLS 和 20 项 session 通过。
Windows job 124463712157 失败于旧 product 的 canonical hash prefix guard：脚本传入 Windows 反斜杠，而 CMake REALPATH 为正斜杠。仅将脚本前缀转为 as_posix()，不改原断言。
独立 evidence job 124464715649 拒绝：member build.json。打包器也产出 package/EXReader-Linux/build.json；后缀模糊查找冲突。改为要求 artifact 根目录下的精确成员路径，保留两份不同用途的 build.json。
修复同批补上：UTF-8 日志、隐藏 receipt/lock 文件上传、三个跨安装前缀拒绝控制、实际包版本 3.42.0 核对，以及 idle cleanup 期间 Cancel 不改变为悬空 CANCELLING 状态。四项产品篡改控制须按指定语义原因拒绝。
- gtk-managed-Windows-41176047061-1：artifact 13033750401，187149 bytes，sha256:fd10a2ebb9e1bfe9ecca6cfe30bb9d1a5a6af6d33fa29e26d411d3d44569d77b。
- gtk-managed-macOS-41176047061-1：artifact 13033127154，1340193 bytes，sha256:c4b0cc6f2ad78a0207c0d372acd597fa083ab0a74c18ceaf5e6e83b7419639a4。
- gtk-managed-Linux-41176047061-1：artifact 13033037169，44484192 bytes，sha256:598781a635214e94ac373a9352134044555835af8988f0aa32eb8e90c7dab773。
- gtk-managed-verification-41176047061-1：artifact 13032831514，44010334 bytes，sha256:bf9e0d1450036eaeaaa8095f242b551d3f6151da3a56147d4cb7ba7820044062。
