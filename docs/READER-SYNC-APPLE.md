# macOS 原生同步接入

本轮将既有原生同步模块扩展到 macOS；不修改冻结 SDK、产品 schema 或修订 wire。
起点为阅读器组合源码 `8476d6b94ffff1fc7df04abacd9f2f9651a486df`。
验收记录在 `docs/validation/reader-sync-apple.json`，当前尚未通过云端运行。

## 实现

- Apple 与 Android 修订 ID 使用公开系统 `arc4random_buf`，保留原 UUID v4 位规则；
  Linux 的 `getrandom` 与 Windows 的 BCrypt 路径不变。
- Apple 原件文件 SHA-256 使用系统 CommonCrypto，保留每次 64 KiB 分块与所有长度/取消检查。
  Android 分支复用修订包已编译的 OPDS 流式 SHA-256，不要求系统 OpenSSL；该分支本轮尚未授予。
  Windows/Linux 原有散列实现不变。
- 不修改 WebDAV 后端源码。macOS 云端构建用 Apple SDK 自带 libcurl/libxml2，
  运行时验证实际消费者链接 `/usr/lib/libcurl.4.dylib`。CommonCrypto 来自 libSystem，
  安装后的同步包不再要求额外 OpenSSL Crypto。
- 云端 OpenSSL 命令只负责生成短期测试证书；测试信任只在临时 Actions runner 上安装。
  不受信任证书、主机名不符与跨源凭据隔离的原检查全部保留。

## 云端出口

`reader-sync-apple.yml` 调用既有原生工作流，对 macOS ARM64、Windows、Linux 同源构建、
安装与运行真实 C/C++ 消费者。默认原生工作流仍使用 Windows/Linux 两平台；现有阅读状态 v2
工作流的旧端拒收测试不变。本轮增加的 macOS 出口覆盖：

| 套件 | 检查数 |
| --- | ---: |
| HTTPS/WebDAV 原来源 | macOS/Linux 77，Windows 76 |
| 修订、outbox、真实进程终止与恢复 | 59 |
| 双端不可变发布与有界发现 | 33 |
| expected-head metadata 投影 | 32 |
| 类型化产品命令 | 33 |
| 桌面 metadata owner、pending 与崩溃恢复 | 29 |
| 异步账号会话、取消、重试与隔离 | 20 |

Apple 链接映射必须将唯一 `_sqlite3_open_v2` 定义指向安装后的产品 SQLite 静态库，
不能退回系统 SQLite 或 SDK 私有提供者。严格汇总重新核对三个 ZIP 的大小、digest、
run/source/attempt、全部七套报告、命名检查一致性及实际消费者哈希。

本轮不授予 iPhone/iPad、Android 原生同步、宿主账号 UI 或六平台联合验收；这些继续由
实际平台接入与同源运行证明。既有失败和先前源码的证据继续独立保留。
