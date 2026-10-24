# 产品模块预集成

本候选将已独立通过的桌面书架、Android 书架、Apple 导入映射和共享同步模块
按普通 merge 纳入 `codex/reader-product-integration`，保留各自历史。
SDK 固定 `9854061be331fe603a1822d9b2b36ee357154927`，八条受保护路径与之相同；
产品 SQL schema1 保持不变。

## 纳入的交付

| 模块 | 交付 HEAD | 独立受测 run |
| --- | --- | --- |
| Windows 有界书架，含 GTK 书架 | `3be2473e27faca4d2ebb1ac6d528ffbbfbb97846` | Windows `40043264202`；GTK `40040335713` |
| Android 有界书架 | `e4600abd4b75d22f117483673cba2898e3ae628a` | `40037805014` |
| Apple 导入映射 | `a6d7dd81eef36e83e004fdc381a565a2ffee5462` | 见 [映射记录](READER-IMPORT-MAPPING-APPLE.md) |
| 原生命令，含投影、修订与 WebDAV 模块 | `d064b5bcf5ed91e9718204cb3d448d7f0807454a` | `40042300722` |

以上是来源记录。预集成须在新的共同源码实际运行，不继承旧 run 的通过结论。
Apple 有界书架和 Android 新的原生目录／命令桥接尚未纳入。

## 本轮云端出口

`reader-product-integration.yml` 用本地 reusable workflow 复用既有测试，
四个上游作业在同一源码、run、attempt 执行：

- Windows 与 Linux：公开 SDK／产品目录、进程终止恢复、原阅读 UI、固定页与有界书架回归。
- Windows 与 Linux：WebDAV 76／77、修订 59、同步 33、原子投影 32、具型命令 33。

严格汇总核对四作业全部成功、四份同源工件未过期且非空，下载 ZIP 后验证实际大小和
SHA-256，再核对报告身份、具名通过项和产品／原始 UI 报告的散列绑定。
报告中的 `accepted=true` 仅指本轮预集成范围。

所有构建、测试、门禁拒绝回归和工件读取均在 GitHub Actions。
`complete_product=false`、`six_platform_accepted=false`、`performance_accepted=false`。
Android／Apple 原有独立通过记录不授予本次源码的移动验收；六目标闭环、凭据 UI、
真机与产品性能预算由后续出口验证。

## 当前状态

共同候选正在准备首次云端运行，尚无同源预集成通过结论。
默认分支和所有 PR 均未合并，未创建 tag 或 Release。
