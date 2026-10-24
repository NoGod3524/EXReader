# 16包分发索引

先读[共同约束](README.md)。固定实现起点：`f43baf9182d75907c0cb5d6f77048f27bca8c950`。
各包有独占路径，能同时开工；没有要求16包彼此互等。

| 包 | 任务 | 类型 | 优先级 | 分发 |
| --- | --- | --- | --- | --- |
| G01 | [Windows 账号、同步与收取界面](windows-account.md) | 功能 | P0 | Claude Code |
| G02 | [封面、首屏预览与有界缩略图缓存](thumbnails.md) | 功能 | P0 | Claude Code |
| G03 | [进度、书签、标注的产品具型命令](reading-commands.md) | 功能 | P0 | Claude Code |
| G04 | [按书书签与标注列表快照](annotation-view.md) | 功能 | P0 | Claude Code |
| G05 | [标注 Markdown／JSONL 导出](annotation-export.md) | 功能 | P1 | Claude Code |
| G06 | [仅移除本机下载与中断恢复](local-downloads.md) | 功能 | P0 | Claude Code |
| G07 | [账号同步故障一致性专项](sync-resilience.md) | 测试 | P0 | DeepSeek Harness |
| G08 | [可选模块同前缀安装与组成验证](module-composition.md) | 测试 | P0 | DeepSeek Harness |
| G09 | [产品依赖、许可证与离线分发清单](distribution-inventory.md) | 发布准备 | P1 | DeepSeek Harness |
| G10 | [Windows 产品性能观测](perf-windows.md) | 性能采样 | P1 | DeepSeek Harness |
| G11 | [GTK 产品性能观测](perf-gtk.md) | 性能采样 | P1 | DeepSeek Harness |
| G12 | [Windows 键盘与无障碍审计](a11y-windows.md) | 审计 | P1 | DeepSeek Harness |
| G13 | [GTK 键盘与无障碍审计](a11y-gtk.md) | 审计 | P1 | DeepSeek Harness |
| G14 | [Unicode 路径、名称与跨平台产品回归](unicode-interop.md) | 测试 | P1 | DeepSeek Harness |
| G15 | [Android 可访问性与大字体审计](a11y-android.md) | 审计 | P1 | DeepSeek Harness |
| G16 | [macOS／iPhone／iPad 可访问性审计](a11y-apple.md) | 审计 | P1 | DeepSeek Harness |

优先投放G01-G04/G06-G08：直接减少宿主接入与数据一致性工作；其余提前发现体验、移植和分发缺口。
G09-G16含发布准备、测量和审计，不应把它们的报告完成计成8项用户功能完成。
Windows/GTK性能与无障碍各自分包，移动无障碍按Android与Apple分包；这些包不能修生产代码，与功能owner互不写冲突。
本批不再重复拆原书导出、F1搜索、F3设置或F4目录扫描；Android/Apple生产导入入口继续由现有宿主owner接续。

