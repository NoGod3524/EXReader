# Dot 第二批：七个新增独立包

本批已由外部会话实际执行，七条指定远端分支均存在，最近源码运行均success；root正在复核，不能重复派发。上一批T01已在run40167556466通过46项新UI及全部保留回归，并普通合入共同候选；其余T包继续按原writer与证据范围接续。

## 远端执行核对

| 包 | 远端HEAD | 最新源码运行 | 结果 |
| --- | --- | --- | --- |
| D01 | `69d8f789e68141a4b9c26219ff3a4f43f3d355e3` | [40171441924](https://github.com/NoGod3524/EXReader/actions/runs/40171441924) | success；verification=true，migration=false |
| D02 | `1563f4abb85ccd28c3a0aae3e9913f4330536215` | [40171829885](https://github.com/NoGod3524/EXReader/actions/runs/40171829885) | success，待root复核 |
| D03 | `25cd7b4b15d952e3f7a10e39ed80ae16a3d9a3ee` | [40171470925](https://github.com/NoGod3524/EXReader/actions/runs/40171470925) | success，受测source `9fdcb28d`，待root复核 |
| D04 | `9c7e276f13f42cb61a32507c36d1c22c4489bd01` | [40171486469](https://github.com/NoGod3524/EXReader/actions/runs/40171486469) | success，待root复核 |
| D05 | `0fcbb9578a6b2a5a5e53c0968241ebcdf5b69ba5` | [40171106759](https://github.com/NoGod3524/EXReader/actions/runs/40171106759) | success，受测source `bb6442cd`，待root复核 |
| D06 | `bcffd40517f8fd3abbb8495f39acd54b4d0fbc6b` | [40171836777](https://github.com/NoGod3524/EXReader/actions/runs/40171836777) | success，待root复核 |
| D07 | `c2109bbbbe2fb874ee2b02563099ab4d0f6bbec7` | [40171982938](https://github.com/NoGod3524/EXReader/actions/runs/40171982938) | success，待root复核 |

D01严格汇总原始日志明确记录 `verification_accepted=true`、`migration_accepted=false`：旧wire的公开解析与真正parser-qualified来源接纳分开，仍需root制定并实测明确的兼容策略；不能据作业绿灯称升级迁移已通过。表中源码运行与后续证据HEAD分开，尚不转授共同源码。

先读[共同约束](README.md)，每包另开独立工作树/会话，严格使用任务书固定起点和唯一分支。

| 包 | 任务 | 优先级 | 完整任务书 |
| --- | --- | --- | --- |
| D01 | SDK3.40→3.41旧阅读记录、锚点与跨版本互通兼容验证 | P0 | [D01-sdk-record-migration.md](D01-sdk-record-migration.md) |
| D02 | 用户自定义字体导入、校验与本机管理模块 | P1 | [D02-font-library.md](D02-font-library.md) |
| D03 | 选中原书的有界批量导出与分享准备模块 | P1 | [D03-original-export.md](D03-original-export.md) |
| D04 | 自有JSONL标注备份的严格导入模块 | P1 | [D04-annotation-import.md](D04-annotation-import.md) |
| D05 | Android阅读窗口常亮与临时亮度适配 | P1 | [D05-android-display.md](D05-android-display.md) |
| D06 | Apple阅读窗口常亮与临时亮度适配 | P1 | [D06-apple-display.md](D06-apple-display.md) |
| D07 | Windows/Linux阅读窗口常亮与抑制休眠适配 | P1 | [D07-desktop-display.md](D07-desktop-display.md) |

D01只读验证旧记录迁移，不修改SDK或当前reading wire/source规则。D02–D04是默认不启用、可独立安装的静态模块；D05–D07是独立原生组件与真实probe。本轮都不接现有正式宿主，接线由root统一安排。不存在D包之间的必需依赖；不要等待其它D包或使用它们的移动HEAD。

当前Sonnet独占J15 OCR/J23边界fuzz复核；DeepSeek独占J16/J17/J18朗读、J20本地化、J24 Unix分发复核；root与三个owner负责共同线、SDK和Android/Apple/GTK正式宿主。D包不能写入这些工作范围。旧T包继续保留原writer。

给Dot的总指令：

> 接手本目录D01–D07七包，先读README及七份完整任务书，在七个独立会话/工作树并行实施。按任务书固定SHA和路径边界，不重做T01–T07或J包复核，不动root/三个平台owner文件。所有构建、语法检查、测试、夹具、服务、benchmark和工件处理仅GitHub Actions。可自行提交/push本包功能分支并修复CI，不需询问是否push；不推默认、不合PR、不创建tag/Release。逐包交回完整tested SHA、证据HEAD、真实运行/工件/失败/缺口；由root审查接入。不能把模拟器、命令入队或报告生成授予为真机、实际亮度或完整产品通过。

发送本INDEX的固定提交URL，避免后续说明变化。七个新包已按远端执行证据登记，不再作为空闲任务重复分发。
