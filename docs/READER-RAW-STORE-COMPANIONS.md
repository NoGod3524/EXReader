# 原始选择器存储伴随模块候选

状态：开发中，尚无本包云端验收；`adopted=false`。

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

计划验证真实 SDK3.40 源 `9854061be331fe603a1822d9b2b36ee357154927` 独立构建及运行版本、三种缓存混用拒绝、调用者关闭开关无法绕过、完整搬迁和规范化目录别名可用。

## 云端出口

`reader-raw-store-companions.yml` 在 Windows/Linux 同源码运行原 core 全套检查、原 Commands/Sync/Session 检查的 OFF/raw 两份，以及 OFF ReadingCommands 联合消费者。另跑真实 HTTPS 传送：

1. 使用真实 PDF 的公开 SDK 捕获（含 NUL），typed book 引导字节与已封存 core 的书籍 wire 一致，再发送完整 graph 与标签/成员命令。
2. 条件 PUT 后真实 GET 认证再 ack，含远端已提交但响应丢失；另一进程接收后逐字节核对。
3. 对实际下载原件进行公开 SDK FOUND 与重捕获；Session 取消/恢复、256 shard、关闭及第二进程重开。
4. raw 客户端传送旧1/2 wire 不改字节；旧客户端继续接受1/2并拒绝3。
5. strict 作业认证同次 producer、source、attempt、原始 ZIP digest/大小/有效期及两平台 wire 一致；私钥不上传。

## 授予边界

仅独立 Commands/Sync/Session raw-store 候选。Android/Apple 真实宿主接入、macOS、本包 SDK3.40 正向 raw3 使用、六平台互通及完整产品仍待后续独立验收。SDK3.40 在本包是缓存负例与旧行为证明。

