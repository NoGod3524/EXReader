# Team24 delivery 续接记录

分支 `codex/team24-delivery`，起点 `c228c51b`；保留原 S20 代码与全部旧结果。

## 旧轮次

原受测 source `63d0c8d2f032f5c78c77c9f407b17185412e991f`，run `40248648454`，attempt `1`：Windows、Linux、macOS、iPhone 通过，Android、iPad 未通过。更早失败 run `40245971457`、`40245894358`、`40245766789` 仍保留。旧轮不计入本队新增最多两轮完整验收。

## 本队接入

- 桌面：组装前添加 Linux 零参数启动器；解包后检查实际程序、平台生产清单与运行依赖，再运行原 GUI 驱动。
- Android：保留原构建器，通过专用 Gradle 适配入口，在 SDK/product 安装后安装 reading-state、reading-commands、annotation-view、search、navigation、preferences，显式启用四个功能。45 项走查仍逐项判定。
- Apple：XCTest 报告保留具名失败、首次断言与相邻日志；重试通过不能抹去先前失败。
- 候选：所有平台使用 workflow 当前 source。`candidate_sha` 只能填写该 source 的完整 SHA；不能在另一 workflow source 上贴候选标签。平台 build.json 的 source/SDK 必须一致，汇总要求六包 source/run/attempt/ZIP/实际程序身份一致。
- GTK 辅助脚本从当前候选源码导入，不从历史提交提取。

## 新增验收账本

轻量协议检查：待 Actions 执行，仅验证交付协议，不授予 GUI 或产品通过。

新增完整轮次 1：尚未启动。
新增完整轮次 2：尚未启动。

## 跨队待修

Android `HostWalkthroughTest` 的标题期望含扩展名，而 `ImportEntry.titleFrom` 去扩展名；同名 Sample 的 EPUB/TXT/PDF 应按公开标题加格式唯一选行，不能只改成模糊 Sample 匹配。picker 返回 wait 布尔值也必须断言。由 Android owner 修改，本队不越界。

iPad 原失败 `test01ImportDeduplicateAndErrors`；`test13` 明示通过。首次断言以原始日志/新轮具名诊断为准。

## 运行和范围

原 ZIP、SHA256SUMS、manifest.json 和中文安装说明随每个目标同轮工件上传；六目标汇总另列实际程序 SHA、SDK 和生产 source。Windows 解压启动 EXReader.exe；Linux 启动 Start-EXReader.sh；macOS 打开 EXReader.app；Android 仅 API34 x86_64 模拟器 APK；iPhone/iPad 仅模拟器 .app。真机、屏幕阅读器人工体验与商店发布未测。尚未组合其他五团队的新 UI，不声称整个六平台产品完成。
