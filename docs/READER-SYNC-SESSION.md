# 原生账号同步会话

`apps/reader/session` 是可选安装包 `EXReaderSession 0.1.0`，复用
`EXReaderSync 0.1.0`。默认 reading 构建不加入它。

一个后台线程独占创建、调用与关闭 WebDAV、修订库及同步句柄。界面通过线程安全的
start、cancel、observe、request_close 控制任务，不接触网络句柄或数据库连接。
每轮覆盖全部 256 分片，每步最多 100 项；失败或取消保留上次成功游标，显式 retry
继续该轮，完成后再次 start 从零开始发现并发插入。没有常驻轮询或自动重试。

FINISHED 表示一次扫描结束。它不代表整个远端永远不变、所有本地原件都可用或所有
冲突已解决。`full_library_complete` 始终为零；pending 计数是各步观测之和，不是
去重后的剩余书数。错误后的部分历史和 outbox 提交继续保留，重试按既有幂等协议处理。

账号由稳定小写 UUID 和精确 HTTPS 根地址标识。产品数据库旁的 `.sync-account`
私有文件仅保存账号及地址并持有操作系统独占锁；再次使用不同账号或地址会在网络前
拒绝。进程退出释放锁，同账号可以重开。首版没有隐式“换账号迁移书库”操作。
Authorization 仅保存在会话内存，由宿主从安全凭据模块或当前会话获得，不写入该文件。

原书先在 SDK owner 上经公开 source 分块导出，结束借用后，才交给网络 worker。
导出文件放在稳定私有 original_directory，以 `<sha256>.<format>` 命名，启动网络前
完成写入且保持不可变。既有 sync 再核对长度与散列、复制私有快照、条件发布及 GET
验证，随后才 ack。缺少本机原件时沿用既有远端核验/pending 规则。
此模块不拿 SDK 句柄，不导入远端原书，不投影 metadata，也不修改当前阅读位置。
宿主接入仍需实现公开 SDK 导出、下载导入、投影调度和真实 UI 验收。

关闭分两步：request_close 只请求取消及退出，界面继续观察；CLOSED 后 destroy。
提前 destroy 返回 BUSY 且保留句柄，不在界面析构中等待网络。取消按原生请求边界
及配置 timeout 生效，不能把它描述成即时中断系统调用。

云端出口为 `reader-session.yml`：Windows/Linux 的安装后 C/C++ 消费者、真实原生
HTTPS、完整 256 分片与续页、两产品库、取消/重试、跨进程独占与账号隔离；保留既有
source/protocol/sync/projection/commands/metadata 检查。平台和宿主 UI、六目标同步、
凭据持久化按实际出口分别验收。

## 保留的候选与失败

| 源码 | 云端运行 | 结果及接续 |
| --- | --- | --- |
| `3bf062890da6fea8ecf79461b95af98c0f0bc895` | `40054436597` | 两平台停止在取消断言。夹具返回404，空分片已记为成功，下一步才观察到取消；不能要求该已成功步骤计数为零。改用成功应答在传输边界验证取消，断言保留。 |
| `ac49238770555ea82a1ad424032fa947b41f0c81` | `40054927743` | Linux20项成功；Windows读取100条记录时90秒出口超时，当时仍在分片16运行。整包未验收。 |
| `45dbb92827161e7942291af68a6e739009068a7c` | `40055415890` | Windows/Linux均20/20，2/2成功。夹具按实际IPv4监听地址连接，证书IP SAN和原生TLS验证保持；105条续页样本、256分片及90秒等待均保持，并保存实际消费者程序。 |

以上失败与工件保留，前轮通过项不授予后轮源码。仅授予本机账号后台会话的上述原生
Windows/Linux声明范围；仍无宿主同步UI、SDK真实原件导出、metadata投影和移动验收。
两份工件非空、未过期，API digest与实际上传日志一致，原source/protocol/sync/
projection/commands/metadata检查同次保留。完整身份见
[会话验收](validation/reader-sync-session.json)。
