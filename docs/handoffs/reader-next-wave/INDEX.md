# 可手动 handoff 的25个独立包

**全部已准备，尚未由root派发。** 固定实现起点 `f43baf9182d75907c0cb5d6f77048f27bca8c950`。25包可分别交给25个会话；同一包只能有一个writer。

每个接收者先读[共同约束](README.md)和自己的任务页。每页含完整目标、真实公共依赖、独占路径、验收及排除项。请按优先级投放；P2是常见阅读器的可选增强，不阻塞核心书库/同步先行。

## 先投放：导入、整理、冲突和跨平台互通

| 包 | 完整交接文档 | 优先级 |
| --- | --- | --- |
| J01 | [WebDAV 选书下载与侧载导入](webdav-import.md) | P0 |
| J04 | [Android 分享、打开与 SAF 文件入口](android-import-entry.md) | P0 |
| J05 | [Apple 文件选择、文件共享与安全作用域入口](apple-file-entry.md) | P0 |
| J10 | [书架批量整理命令](bulk-organization.md) | P0 |
| J11 | [显式冲突选择与合并命令](explicit-conflict-actions.md) | P0 |
| J22 | [真实跨操作系统修订与原书往返验收](cross-os-relay.md) | P0 |

## 其余现在可独立开工

| 包 | 完整交接文档 | 优先级 |
| --- | --- | --- |
| J02 | [OPDS 浏览、搜索与获取适配](opds-browser.md) | P1 |
| J03 | [桌面文件拖放与粘贴入口适配](desktop-drop.md) | P1 |
| J06 | [书内外链与打开动作策略](external-link-policy.md) | P1 |
| J07 | [阅读跳转历史与前进后退](jump-history.md) | P1 |
| J08 | [原生快捷键与输入焦点动作映射](keyboard-actions.md) | P1 |
| J09 | [原书与产品元数据只读信息快照](book-information.md) | P1 |
| J12 | [同步、待处理与错误状态只读模型](sync-status-view.md) | P1 |
| J13 | [不含秘密的账号配置与隔离目录](account-profiles.md) | P1 |
| J14 | [原书与本机映射健康检查](library-health.md) | P1 |
| J15 | [扫描页 OCR 临时文字覆盖层](ocr-overlay.md) | P2 |
| J16 | [Windows 原生朗读适配](tts-windows.md) | P2 |
| J17 | [macOS／iPhone／iPad 原生朗读适配](tts-apple.md) | P2 |
| J18 | [Android 系统 TextToSpeech 适配](tts-android.md) | P2 |
| J19 | [Linux 原生 Speech Dispatcher 朗读适配](tts-linux.md) | P2 |
| J20 | [中英文界面资源与格式化](localization.md) | P1 |
| J21 | [隐私保护的用户诊断导出](diagnostic-report.md) | P2 |
| J23 | [应用模块公开边界故障与模糊回归](app-boundary-fuzz.md) | P1 |
| J24 | [Unix 可重定位分发准备](distribution-unix.md) | P1 |
| J25 | [Windows 无构建路径的分发准备](distribution-windows.md) | P1 |

## 手动发送方法

每个会话发以下一句，并附上表里该包的任务页URL即可：

> 请按这份任务页及它链接的共同约束，完整实现、推送你自己的功能分支并完成GitHub Actions验收。实现从任务页指定的完整SHA开始，独立工作树，不能改其它owner路径。失败自行查根因修复并保留记录，不要停在询问是否push；不要合并PR、推默认分支或发布Release。最后交回固定受测SHA、文档HEAD、真实run/工件和剩余缺口。

任务说明的文档提交与实现起点不同；不要把文档分支HEAD当代码起点。J16–J19还须遵守[冻结TTS接口](tts-contract.md)。用户决定各会话模型和权限，本批不自动操作Claude/DeepSeek或修改其设置。

## 目前保留给主线的工作

Windows原生UIA与账号收口、GTK原生书内搜索/页面主题缺口、Android搜索UI、Apple正式书架/账号/语义检查由现有owner继续。四套宿主的接线和默认界面简化、G包/新包的共同源码集成由root协调，不再交给第二个writer。

[ownership.json](ownership.json)登记全部分支与白名单。单包交回后可继续准备下一包；只有完成共同源码验证的集成轮次才计数，五轮审计保持。

