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
source/protocol/sync/projection/commands/metadata 检查。首次候选尚无结果；平台和
宿主 UI、六目标同步、凭据持久化均不授予验收。
