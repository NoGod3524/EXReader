# 交给 Dot 的七个独立包

本批七包已有远端工作，不能再次从头分发。2026-10-25核对：T02/run40164827613、T03/40164760850、T04/40164811197、T05/40166639576、T06/40164861121、T07/40165618848最近轮次success；T01/run40167556466当时仍在进行。这里只登记运行事实，root尚需读取原证据并完成共同接入。此前“未派发”台账已过时；本会话没有通过接口向Dot发送消息。

用户本次需要的七个**新增**手动交接包见 [Dot第二批D01–D07](../reader-dot-wave2/INDEX.md)，不要把下面旧总指令重复发到新会话。

| 包 | 工作 | 固定任务书 |
| --- | --- | --- |
| T01 | Windows 云盘导入与书架批量整理实际界面 | [T01-windows-import-organize.md](T01-windows-import-organize.md) |
| T02 | 显式冲突处理复审与修复 | [T02-conflict-actions-review.md](T02-conflict-actions-review.md) |
| T03 | 跨操作系统原书与修订往返复审 | [T03-cross-os-relay-review.md](T03-cross-os-relay-review.md) |
| T04 | Apple 文件入口复审与修复 | [T04-apple-file-entry-review.md](T04-apple-file-entry-review.md) |
| T05 | 八个已复审可移植模块共同安装与实际组合 | [T05-reviewed-composition.md](T05-reviewed-composition.md) |
| T06 | 用户诊断导出隐私与故障复审 | [T06-diagnostic-report-review.md](T06-diagnostic-report-review.md) |
| T07 | OPDS 浏览与获取适配复审 | [T07-opds-browser-review.md](T07-opds-browser-review.md) |

T01是Windows实际产品接线；T05是共同模块组合；其余是已有完整交付的定向复审和必要修复。七个写入范围互不相交，均不占用当前Android/GTK/Apple主线owner路径。T01与T05可只读合并同样的固定依赖，不修改依赖实现，因此不互相等待。

## 发给 Dot 的总指令

请接手本目录T01–T07七个工作包，先读README.md和每个完整任务书，创建七个互不共用工作树的独立任务并协调并行。只派这七包，不给Claude或DeepSeek重复派同包；不要使用电脑操作。按照各自完整固定SHA、新分支和独占路径执行，不改原外部交付树或root/三个主线owner文件。所有构建/测试/语法检查/夹具/服务/benchmark/工件处理仅Actions；可以push各任务功能分支并自行修复CI，不停在询问是否push；不推默认、不合PR、不发布。每包完成后在你这里汇总tested SHA、证据HEAD、真实run/工件与缺口，等待root接入共同主线。若环境无法访问仓库或相应runner，报告具体缺失能力，不把任务标成完成。工作完成只代表本包范围，不授予完整六平台产品。按照任务书逐个推进，无需再次征求启动同意。

把这份INDEX的固定提交URL一并发给Dot，避免读取之后被修改的任务说明。
