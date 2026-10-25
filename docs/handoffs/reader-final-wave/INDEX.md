# 最终阅读器并行交接：22包

实现固定从 `0889f7d1e9a537c6c1b05456547e016b26e1cd85` 起；文档HEAD不是实现起点。先读[共同约束](README.md)。

Claude恰好3包（Sonnet5.5/medium，后台完全权限），Dot7包由用户手动发送，其余12包给DeepSeek（V4.1 Flash1017/high/PTC，后台完全权限）。本批独立于旧J/G包；旧模块先复用，不重复实现。
已实际确认Claude3个后台会话busy，以及DeepSeek12个持久session/进程均存活并执行PTC工具，实际模型selection为deepseek-account/deepseek-flash/high。Dot7包等用户手动投放。状态和日志见root本机dispatch ledger；开工不代表验收通过。

## Dot：请分别发给七个会话

每个会话发送：

> 请完整执行此任务页及它链接的共同约束。从指定完整SHA创建独立worktree/功能分支，只写独占新增路径，自行push并完成GitHub Actions。全部构建/测试/语法/夹具/截图/工件解析只在Actions，禁cpuse；不改原owner/裁判/SDK/预算，不推默认/开合PR/发布。不要再询问是否push；最后交完整受测与文档SHA、run/attempt、真实工件和失败/未验证项。

| 包 | 任务 |
| --- | --- |
| D01 | [D01：六平台首版需求、实际入口与验收追踪](D01.md) |
| D02 | [D02：Windows compact 高DPI、对比度与UIA键盘审查](D02.md) |
| D03 | [D03：GTK compact 缩放、对比度与AT-SPI键盘审查](D03.md) |
| D04 | [D04：Apple三目标默认界面、动态字体与AX语义审查](D04.md) |
| D05 | [D05：Android默认界面、字体缩放、旋转与TalkBack语义审查](D05.md) |
| D06 | [D06：四宿主动作、快捷键与焦点一致性审查](D06.md) |
| D07 | [D07：首版中文用户指南与恢复指引](D07.md) |

## Claude：三个后台包

| 包 | 任务 |
| --- | --- |
| C01 | [C01 最终产品证据门禁](C01.md) |
| C02 | [C02 产品级性能测量工具](C02.md) |
| C03 | [C03 账号、导入与同步故障边界复核](C03.md) |

## DeepSeek：其余十二个后台包

| 包 | 任务 |
| --- | --- |
| S01 | [S01 Windows最终可迁移包核验](S01.md) |
| S02 | [S02 Linux可迁移候选包核验](S02.md) |
| S03 | [S03 macOS应用包搬移核验](S03.md) |
| S04 | [S04 Android交付APK核验](S04.md) |
| S05 | [S05 iPhone与iPad模拟器候选分发核验](S05.md) |
| S06 | [S06 六目标导入入口真实回归矩阵](S06.md) |
| S07 | [S07 raw同步多peer故障与幂等回归](S07.md) |
| S08 | [S08 诊断输出与账号信息泄漏验收](S08.md) |
| S09 | [S09 最终分发许可证与SBOM闭包](S09.md) |
| S10 | [S10 电脑传书入口与能力证据](S10.md) |
| S11 | [S11 原件导入持久化故障回归](S11.md) |
| S12 | [S12 Unicode路径与书库状态跨配置回归](S12.md) |

主线保留现有实际宿主接入、Apple失败根因、共同源码整合。新包失败定位可独立提交，生产修复由root协调；不让第二个writer抢同一文件。跨source的平台测量/审查不能代替共同源码产品通过。
