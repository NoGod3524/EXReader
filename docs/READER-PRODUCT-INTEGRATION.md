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

原 Windows UI JSON 没有 run／attempt，原 GTK UI JSON 没有 attempt；这两份保留的
报告通过同次工件 ZIP 身份及新产品报告的 `original_report_sha256` 绑定。
汇总不会把这些旧格式 JSON 描述为自身携带完整运行身份。

所有构建、测试、门禁拒绝回归和工件读取均在 GitHub Actions。
`complete_product=false`、`six_platform_accepted=false`、`performance_accepted=false`。
Android／Apple 原有独立通过记录不授予本次源码的移动验收；六目标闭环、凭据 UI、
真机与产品性能预算由后续出口验证。

## 当前状态

受测源码 `bad72dd68602e2e80177de7fefd7a92ddeb4cae0` 的
[run 40045484528](https://github.com/NoGod3524/EXReader/actions/runs/40045484528)，
attempt1，四个上游与严格汇总共 **5/5 成功**；云端 `accepted=true`、`problems=[]`。

| 作业 | ID | 本次同源结果 |
| --- | --- | --- |
| GTK 桌面 | `120726103432` | SDK9、目录12、书架后端10、kill2、原UI20、产品5、固定页24、书架UI14及保留拒绝回归 |
| Windows 桌面 | `120726103493` | SDK9、目录12、书架后端10、kill2、原UI158／截图8、产品10、worker5、书架UI13及原门禁 |
| Windows 同步模块 | `120726103508` | WebDAV76、修订59、同步33、投影32、具型命令33 |
| Linux 同步模块 | `120726103530` | WebDAV77、修订59、同步33、投影32、具型命令33 |
| 严格汇总 | `120727675306` | 六组拒绝回归、四份工件实际 ZIP 散列／大小及报告身份核对 |

四份上游工件和汇总工件的 ID、大小、digest 与报告散列见
[验收 JSON](validation/reader-product-preintegration.json)。所有工件同 source/run/attempt，
未过期，云端校验了实际 ZIP 字节；本机没有下载工件。

为释放 macOS 云端额度，旧 PR20 的重复功能分支门禁 run `40042809585` 剩余两项已取消：
受测源码 `d064b5bcf5ed91e9718204cb3d448d7f0807454a`，目标分支
`codex/reader-metadata-projection`；已完成的十四项成功原样保留，该 run 不算通过。

默认分支和所有 PR 均未合并，未创建 tag 或 Release。
