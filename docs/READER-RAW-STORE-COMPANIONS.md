# 原始选择器存储伴随模块候选

状态：Windows/Linux 同源码独立候选验收通过，`accepted=true`、`adopted=false`。

固定起点：`0737d03c1316295a210aa527833c05054d29c1d4`。原始选择器 core 候选此前独立通过；该通过记录不授予本包。

## 显式契约

`EXR_READER_SELECTOR_BYTES_CANDIDATE` 默认为 OFF。ON 时 Commands/Sync/Session 为 0.2.0，依赖 Revisions 0.4.0；OFF 保持原 0.1.0 / Revisions 0.3.0 链。所有安装消费者使用真实安装包。

- Commands 增加三个 `*_raw_v3` 入口，复用原校验、事务和生成器；旧入口不接收 raw store。
- Sync 的能力在创建时固定，`reader_sync_create_raw_v3` / `reader_sync_step_raw_v3` 必须成对；所有 revision 操作沿同一能力分派。借入错误 store 的创建仍沿原契约延后验证，在首次 step 无写入拒绝。
- Session 增加 `reader_session_create_raw_v3`；现有单一 worker 在所属线程打开/调用/关闭 raw revisions 与 raw sync。生命周期、账号绑定、取消、观察和重试流程共用原实现。
- SDK、schema1、默认 wire、旧 pending 字段、主线宿主及导出/历史/状态等可选模块不变。

## 安装来源守卫

四个 core 模块仅在八个 CMake/Config 文件末尾追加候选 ON 守卫，源码边界逐字核对原文件与追加内容。公开实现和原测试保持固定起点。

候选 Config 使用生成时固定的开关，核对实际导入目标的能力标签、公开头版本/真实安装位置、真实归档位置；不改写现有目标。SDK 检查真实 core/library 头和归档，防止缓存的真实 3.40 目标被 3.41 配置文件的版本判断掩盖。默认 OFF 可消费原始未加标签的 0.3 包。

已在云端验证真实 SDK3.40 源 `9854061be331fe603a1822d9b2b36ee357154927` 独立构建及运行版本、三种缓存混用拒绝、调用者关闭开关无法绕过、完整搬迁和规范化目录别名可用。

## 云端出口

`reader-raw-store-companions.yml` 在 Windows/Linux 同源码运行原 core 全套检查、原 Commands/Sync/Session 检查的 OFF/raw 两份，以及 OFF ReadingCommands 联合消费者。另跑真实 HTTPS 传送：

1. 使用真实 PDF 的公开 SDK 捕获（含 NUL），typed book 引导字节与已封存 core 的书籍 wire 一致，再发送完整 graph 与标签/成员命令。
2. 条件 PUT 后真实 GET 认证再 ack，含远端已提交但响应丢失；另一进程接收后逐字节核对。
3. 对实际下载原件进行公开 SDK FOUND 与重捕获；Session 取消/恢复、256 shard、关闭及第二进程重开。
4. raw 客户端传送旧1/2 wire 不改字节；旧客户端继续接受1/2并拒绝3。
5. strict 作业认证同次 producer、source、attempt、原始 ZIP digest/大小/有效期及两平台 wire 一致；私钥不上传。

## 授予边界

仅独立 Commands/Sync/Session raw-store 候选。Android/Apple 真实宿主接入、macOS、本包 SDK3.40 正向 raw3 使用、六平台互通及完整产品仍待后续独立验收。SDK3.40 在本包是缓存负例与旧行为证明。

## 已封存的同源码验收

受测 source **`56793e7ca4f8ecdc5f2d9c3394fce4e201aca275`**；[run 40192929457](https://github.com/NoGod3524/EXReader/actions/runs/40192929457)，attempt 1。Linux `121167606543`、Windows `121167606664`、strict `121170438510` 全部 success。

每个平台原 Commands OFF/raw 各 33、原 Sync OFF/raw 各 33、原 Session OFF/raw 各 20；原 core 全套回归与新 OFF Commands 联合 ReadingCommands 消费者均通过。真实 TLS 检查 9/9，来源/兼容 profile 8/8，另有三种新旧包混用拒绝。

真实 HTTPS 传送了 11 条完整 wire：9 条真实 SDK PDF graph，加两个 typed 标签/成员命令；两平台全部 wire 摘要一致。实际下载 PDF 的 SHA-256 为 `5627a430fa04cbe11d38eb2682e336ef21e147d445753ed46ed11a7d5e3167cc`，重开后公开 SDK FOUND 与重捕获通过。旧1/2 wire 逐字节不变，旧消费者接受1/2并拒绝3。

SDK3.40 证明来自真正独立构建的 `9854061be331fe603a1822d9b2b36ee357154927`，版本程序实际输出 `3.40.0`。已验证缓存旧 Revision、缓存真实旧 SDK、同时缓存二者、调用者关闭开关不能绕过；搬迁、真实 symlink/junction 别名及重复 find 可用。新 OFF Commands 也实际链接原始无能力标签的 Revision 0.3 并执行安装 C ABI 消费者。

| 工件 | ID | 字节 | 原始 ZIP SHA-256 |
| --- | --- | ---: | --- |
| reader-selector-bytes-Windows | `12599261570` | 55358531 | `sha256:e301dffd0b74a9839f2e77709117451ebd05cb9c390de65a3a4d88c37d0b663f` |
| reader-raw-store-companions-Linux | `12599236409` | 30471463 | `sha256:1517edc360ed5ef3916af24e50c6cb6ab36a656e99890b2c9f48f47954f453a5` |
| reader-selector-bytes-Linux | `12599081639` | 51305849 | `sha256:5d9bc2c1c49ec3a2b1db6313e2e21617784aae44d0834d4ec38821e820f89e15` |
| reader-raw-store-companions-Windows | `12599007043` | 40843614 | `sha256:56f0128943b64e13ca82143aa750618281a0dd161f29b1606b73e35a2f0e58e0` |
| reader-raw-store-companions-summary | `12598633775` | 1676 | `sha256:f30e93ac7b7f5095158e0cd74337eb5e205e4f4b09378046cab8063d3485dbcc` |

全部工件有效期 `2027-01-23T12:24:02Z`。strict 在 Actions 下载原始 ZIP，核对 digest/大小/有效期/source/attempt/producer、真实捕获字节与两平台一致性；本地仅编辑、Git 和读取日志/元数据。

## 历次尝试

- `40190661899`：主动取消；静态复核发现 SDK core 是接口目标。
- `40190906663`：新守卫未覆盖 shared=OFF 的 exreader 聚合接口。
- `40191315854`：新 Sync 头缺版本宏；Windows 动态读原脚本使用系统编码，破坏 emoji 夹具。修复仅在新包和 runner。
- `40191789670`：Windows 全绿；Linux 的新七程序构建日志向旧单程序检查器提供七条 trace。限制 trace 到该程序后原检查器不变。
- `40192474330`：7-profile 中间候选已同源全绿；最终源码增加第八项原始无标签 0.3 正例。全部历史保留。

## 给宿主接入的固定依赖

采用本包时显式开启 `EXR_READER_SELECTOR_BYTES_CANDIDATE=ON`，使用 SDK3.41 候选、ProductCatalog0.1、WebDAV0.2、Revisions0.4、ReadingState/ReadingCommands/AnnotationView/Commands/Sync/Session0.2 的完整链。State 显式设置 `EXR_SDK_VERSION=3.41.0` 与真实安装 `EXR_SDK`。使用独立构建目录和安装前缀，来源守卫会拒绝已缓存的旧目标。导出、历史、状态等其他可选模块仍需各自接入；本封存只授予本包 Windows/Linux 接口，`adopted=false`。

