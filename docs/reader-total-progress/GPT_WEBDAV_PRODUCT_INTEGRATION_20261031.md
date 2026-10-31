# Linux GTK WebDAV managed staging 产品接入

本聊天用户已授权实施，并进一步明确接管上游补证、独立审计、产品接入和 CI，持续到完成。
当前状态：上游补证、独立审计、Linux GTK 产品接入及三平台 CI 均已完成；最终独立产品重算 accepted=true、errors=[]。正式台账保持 95/108，不改 catalog.json。

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

## 产品 CI 验证范围

本 workflow 仅本分支 push：Linux 上限 120 分钟，Windows/macOS 兼容各 30 分钟，独立证据 job 15 分钟。
Linux 构建完整安装依赖和实际 GTK、原 77 项 TLS 回归，25 项本包传输/故障矩阵，真实 GTK HTTPS 同步/打开/重开/pending/清理重试/强杀/关闭/有界根池/离线读取。
Windows/macOS 默认关闭 managed，原 installed TLS 用例分别 76/77 项及原异步 session 20 项保持原断言。
独立 evidence job 认证本次原始 ZIP，重算原始 receipt CRC/身份、目标保留、死亡退出码、恢复幂等和容量界限，核对实际 GTK 二进制、截图与网络记录，并运行篡改负控。
首轮失败 artifacts 保留；最终完整 SHA、run/attempt、各 artifact digest 与边界见下文。

## 首轮产品运行及修复

源码 fef8bf9fd9b7c68228705cd6e20d6f56031897ab；[41176047061](https://github.com/NoGod3524/EXReader/actions/runs/41176047061) / attempt 1。
Linux job 124463711948 success：完整 GTK 构建、旧 77 项 TLS、25 项故障矩阵和真实 GTK 21 条记录通过。macOS job 124463712158 success：旧 77 项 TLS 和 20 项 session 通过。
Windows job 124463712157 失败于旧 product 的 canonical hash prefix guard：脚本传入 Windows 反斜杠，而 CMake REALPATH 为正斜杠。仅将脚本前缀转为 as_posix()，不改原断言。
独立 evidence job 124464715649 拒绝：member build.json。打包器也产出 package/build.json；后缀模糊查找冲突。改为要求 artifact 根目录下的精确成员路径，保留两份不同用途的 build.json。
修复同批补上：UTF-8 日志、隐藏 receipt/lock 文件上传、三个跨安装前缀拒绝控制、实际包版本 3.42.0 核对，以及 idle cleanup 期间 Cancel 不改变为悬空 CANCELLING 状态。四项产品篡改控制须按指定语义原因拒绝。
- gtk-managed-Windows-41176047061-1：artifact 13033750401，187149 bytes，sha256:fd10a2ebb9e1bfe9ecca6cfe30bb9d1a5a6af6d33fa29e26d411d3d44569d77b。
- gtk-managed-macOS-41176047061-1：artifact 13033127154，1340193 bytes，sha256:c4b0cc6f2ad78a0207c0d372acd597fa083ab0a74c18ceaf5e6e83b7419639a4。
- gtk-managed-Linux-41176047061-1：artifact 13033037169，44484192 bytes，sha256:598781a635214e94ac373a9352134044555835af8988f0aa32eb8e90c7dab773。
- gtk-managed-verification-41176047061-1：artifact 13032831514，44010334 bytes，sha256:bf9e0d1450036eaeaaa8095f242b551d3f6151da3a56147d4cb7ba7820044062。

## 最终受测组合与终态

受测完整源码 SHA：**044824f91ddae2ea49994350d308d079a69048ab**。
[最终 CI 41176687170](https://github.com/NoGod3524/EXReader/actions/runs/41176687170) / attempt 1；四个 job 均 completed/success。
本封存是文档提交，生产代码、验证程序和 workflow 与此受测 SHA 相同。最终文档 HEAD 以本文件所属提交为准，不能替换上面的受测源码身份。

| Job | ID | 结果 |
|---|---:|---|
| Linux GTK managed WebDAV | 124465594563 | success；原 TLS 77/77、故障矩阵 25/25、真实 GTK 21 条记录、三项跨安装前缀拒绝 |
| Legacy Windows | 124465594509 | success；默认旧 TLS 76/76、原 session 20/20 |
| Legacy macOS | 124465594472 | success；默认旧 TLS 77/77、原 session 20/20 |
| Independent product evidence verification | 124466368909 | success；accepted=true、errors=[]，四个负控按指定语义拒绝 |

Linux 记录了 11 次实际子进程死亡；真实无 hook GTK 另实测 SIGKILL=-9、恢复与离线阅读。
真实 GTK 完成 570 次经 fixture 认证的 HTTPS 请求记录；包括原始 revision 与 object GET、已下载书籍打开及正常重开。
清理专用 Retry 前后网络请求计数相同，目标 dev/ino/size/hash 保持；界面仍可离线读书。
独立 job 从 GitHub API 获取本次三份原 ZIP，核对 source/run/attempt、ID、长度和 SHA-256 后重算原始观察，原 ZIP 随验证结果保留。
四个负控实际拒绝原因为：signal → actual SIGKILL；target → published target preserved；capacity → capacity refusal；gtk → cleanup retry only。

### 最终 artifacts

以下均绑定受测源码 044824f91ddae2ea49994350d308d079a69048ab、run 41176687170 / attempt 1。

| 名称 | ID | ZIP bytes | SHA-256 |
|---|---:|---:|---|
| gtk-managed-verification-41176687170-1 | 13033108235 | 47565339 | b4ac0501c60878f14c57b10ca3f1f32ac702f89e399086f141e66ae25cb5695b |
| gtk-managed-Windows-41176687170-1 | 13032843544 | 2358868 | 957c707820335a19e36f50ae6601b460dd24bb8347b44aa14e8891d1d611da72 |
| gtk-managed-Linux-41176687170-1 | 13032843468 | 44542391 | 70e270bc70d424052ebe0b8eb60f4cecc4a21598ff22bb877719c924dbce4990 |
| gtk-managed-macOS-41176687170-1 | 13032777124 | 1339913 | 9223cf8ee905828179550a0f49336d5c9de47d55f6d65635c0fa806117e3b9f8 |

Linux artifact 内：
- `package/EXReader-Linux/` 是实际 GTK 包；`package/EXReader-Linux.tar.gz` 是可交付归档；`package/build.json` 含 SDK 3.42.0、ABI 1 与包内文件摘要。
- `build.json` 记录本次产品/SDK source 与二进制身份；`admission.json` 记录 30 路径 source blob 和上游审计准入；`accepted-upstream-audit.zip` 是固定上游原审计 ZIP。
- `prefix/` 保留已安装模块的 archive、public headers、CMake capability configs；`host/gtk-account-host.map`、`probes/*.map` 与构建/nm 日志区分 installed 产品和 direct-source 故障构建。
- `matrix/results.json`、各 case 日志与 fixture 目录保留 PID/argv/退出码、errno、dev/ino/nlink/size/hash、receipt 原始字节和恢复前后快照；隐藏 receipt/lock 也在 ZIP 中。
- `ui/results.json`、状态文件、截图与 HTTPS 记录绑定实际 GTK；`capability-refusals.json` 与 `mixed-*.log` 保存三个混用安装前缀的拒绝。
- TLS/fixture 私钥不上传。认证值只在 fixture 内存中使用；网络证据仅记录认证是否成立及请求方法/路径。

验证 artifact 内 `Linux.zip`、`Windows.zip`、`macOS.zip` 是上述原始生产者 ZIP，`summary.json` 是独立重算终态。

### 安装与运行身份

固定 SDK source 7271829a829bfa6aaa47b73077c493f71af27ad3；安装包实际执行 `--version` 返回 **3.42.0 1**。
实际 GTK 执行文件与包内 `bin/exreader-linux` 字节相同，独立检查又将 UI 报告的二进制摘要与构建记录绑定。

| 类别 / artifact 成员 | Bytes | SHA-256 |
|---|---:|---|
| prefix/lib/libexr_webdav.a | 159776 | 691dac483ca9b5ab5a986c30333c0f44b01f35eb888624b48bff04b8bb2bb52c |
| prefix/lib/libexr_webdav_cleanup.a | 22330 | 276bb6c488e6ed916e87d77a3e062e1e1f650d89cb1a12229ac75cf0a20bfdd3 |
| prefix/lib/libreader_session.a | 40592 | 34fc20b98b46649496ce9a67ba9fd563aac33b68ab8ca88aa2cbf4a838bc2b46 |
| host/gtk-host/exreader-linux | 10158144 | e6553ff51512d6803db11ca68cdcd8c7adb3d7eb9312d80315001ab9dab10aba |
| package/EXReader-Linux/bin/exreader-linux | 10158144 | e6553ff51512d6803db11ca68cdcd8c7adb3d7eb9312d80315001ab9dab10aba |
| probes/managed-consumer | 151304 | 1090738729dfed6fe47c4143db1cc6a0f4c633400adb34f67bcb0354ae842e62 |
| probes/managed-fault-worker | 165096 | ae7663e6208c052bf83444789f29b7d6c57c8cf9bab500f2bfee4c35dc1f8e9f |

安装头使用独立 public API，不修改旧头或结构布局。对应固定 source blob 如下，安装日志及头文件字节在同一 Linux artifact 的 `prefix/include/` 中：

| Public header | 固定 Git blob |
|---|---|
| apps/reader/session/include/reader_session_managed.h | 94757f36833c8c12332e5639719fe7ee754ab80a |
| extras/webdav-cleanup/include/exr_webdav_cleanup.h | 47d2d4fa2ac066b21ad644479a84cf541b7f310e |
| extras/webdav/include/exr_webdav_managed.h | b9888404c34308209ebdd1cfe781e058abb1b703 |

EXReaderWebDAVCleanup 0.1.0 提供独立 target；WebDAVManaged 0.1.0 与 SessionManaged 0.1.0 capability configs 验证原 0.2.0 base packages 的显式编译能力及相同安装来源。
`nm` 证明已安装 archive 与普通 consumer 无 hook；故障 worker 才含两组 hook 符号。

### 逐场景结果

所有下列 case 均为最终 run 的 passed；本矩阵无 failed、blocked 或 not-run 条目。

| Case | 状态 |
|---|---|
| 01-installed-normal-and-reopen | passed |
| 02-existing-target | passed |
| 03-unpublished-cancel | passed |
| 04-unpublished-http | passed |
| 05-unpublished-disconnect | passed |
| 06-real-eacces-and-two-recoveries | passed |
| 07-process-lock | passed |
| 08-refuse-corrupt | passed |
| 09-refuse-next | passed |
| 10-refuse-unknown | passed |
| 11-refuse-missing | passed |
| 12-refuse-uuid | passed |
| 13-refuse-symlink | passed |
| 14-kill-directory_created | passed |
| 15-kill-owned | passed |
| 16-kill-sealed | passed |
| 17-kill-publish_intent | passed |
| 18-kill-linked | passed |
| 19-kill-published | passed |
| 20-kill-alias_unlinked | passed |
| 21-registry-next-kill | passed |
| 22-root-created-unbound-kill | passed |
| 23-published-receipt-uncertain | passed |
| 24-root-rotation-and-mixed-restart | passed |
| 25-pool-exhaustion | passed |

真实 GTK 的 21 条记录覆盖以下用户场景及其关闭记录：

| 场景 | 状态 / 原始观察 |
|---|---|
| HTTPS 同步与打开下载书籍 | passed；session → raw sync → 公共 DAV、receipt、原件 hash、raw wire 与阅读界面 |
| 正常退出重开 | passed；UUID/receipt 与已发布目标身份保持 |
| 发布后真实 EACCES | passed；非 root canary errno=13、0500、界面 pending |
| 单独清理重试 | passed；不新增网络请求、不重复导入、不改变目标 |
| GTK 在 OWNED 阶段 SIGKILL 后重开 | passed；实际 -9、receipt 保留、pending 可见、离线读书 |
| 连续 Cancel → Disconnect → Close | passed；关闭代次一致、正常退出 |
| 传输中关闭主窗口 | passed；异步释放后 exit=0 |
| pending/full/available 混合根重启 | passed；旧根保留，状态可见 |
| 16 根耗尽 | passed；容量提示明确，离线阅读继续 |
| 损坏注册表 | passed；拒绝 managed 同步，已有书仍能打开 |

## 有界性、崩溃残留与关闭合同

上限 16 根使 registry、打开的 root handles 和单轮扫描固定有界；总共最多 1024 个 lifetime transaction slots。
这个上限按事务计数，不按书籍计数；失败事务也可能消耗 slot。它为首阶段容量拒绝提供确定边界，不包含根退休。

| 持久状态 / 残留 | 下次行为 |
|---|---|
| 新命名空间仅部分建立，缺 registry 或永久锁 | 拒绝并保留，不补造身份 |
| registry.next 残留 | uncertain，保留原物，不猜测/重放注册表发布 |
| registry 的 ALLOCATING / UUID 未绑定 | 保留并计 pending，不从 receipt 反推 UUID；可在剩余额度另登记新根 |
| READY + 预期 UUID 匹配 | 按固定 core 合同恢复，旧 pending 根始终登记 |
| READY 的 UUID 错误、root 缺失或损坏 | 拒绝新的 managed 下载，保留原物 |
| 未登记条目或 symlink | 拒绝，不按目录前缀认领 |
| core 的有效同 root、generation+1 .receipt.next | 维持已审计 amendment：丢弃有效 successor，继续使用旧 receipt |
| 16 根无可用 slot | EXR_DAV_LIMIT，容量耗尽可见，无旧临时路径回退 |

线程所有权：GTK/SDK owner 只持有 profile 文本与值快照；启动 worker 独立创建、恢复并关闭 root。
启动 worker 被回收后，session 网络 worker 自行 enable、使用与关闭 DAV/root/tx。
清理 Retry 在该 session worker 关闭空闲连接后离线执行；请求关闭可与之并发，但必须等有界恢复结束。
`request_close → worker 释放 connection/root → CLOSED → join/destroy` 保持；启动恢复中的主窗口关闭由计时器异步等候回收。

| 观察 | 用户状态 |
|---|---|
| status=0、pending=0 | 临时下载正常 |
| pending>0 | 待清理及数量，保留已保存书籍 |
| busy | 清理正被占用，离线阅读可用 |
| receipt uncertain | 清理记录需要处理，保留文件 |
| refused / 其他错误 | 清理无法启动，保留书库 |
| capacity_exhausted / LIMIT | 临时下载容量耗尽，离线阅读可用 |

## 所有权、封存与结论上限

H03 已核 HEAD 22e84472ae684c901ab20a1f52c8601568ef7e0c；J03 已核 HEAD 8b1328f105b25c46711a11348f2ca313874947e4。其已提交 diff 不含本包生产路径。
本包所有新写入只到三条已接管的功能分支，不更改其他 owner 分支、共享 Windows 脏树或已有 VM worktree。
产品精确清单为 9 个既有生产文件、6 个新增生产文件、4 个原字节 core 文件、9 个新测试文件、1 个 workflow 和本文件，共 30 路径；[manifest.json](../../tests/gtk_managed_webdav_20261031/manifest.json) 与 CI guard 逐项固定。
最终已核 base→受测 SHA 的完整 diff 恰为该清单；旧 tests、SDK、旧 public ABI、其他 host、received.inc 和正式 catalog 均无 diff。

上游 tests 封存文档 HEAD：2a6bada9b391e741425556e5ac67c6191a1f145a；其受测 tests 仍为 711e1fc8a8c5b86f210bcddc934c479599387582。
上游 audit 封存文档 HEAD：5f05c86f4f9b36579539279a000d695ad7af5454；其受测 verifier 仍为 ea54eb95eafc62a2db8fec4547eab142856f9351。

本次完成并验证的是 **Linux GTK managed WebDAV transport staging/alias 闭环**。
高层 sync private_file / upload snapshot / GTK import snapshot、永久根退休、其他宿主的 managed 接入、断电一致性和完整 F10 仍属另验范围。
本包代码和验证已完成；候选证据交总验收 owner 入账审核，正式 95/108 保持，不开合 PR、不合主线、不打 tag、不发布版本。
