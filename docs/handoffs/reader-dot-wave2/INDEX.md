# Dot 第二批：七个新增独立包

本批由用户手动交给Dot，尚未派发。不要重做上一批T01–T07：截至本次核对，其七条远端分支均存在，T02–T07最近一次云端运行success，T01运行40167556466仍在进行；各包仍需root读取证据后接入。

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

发送本INDEX的固定提交URL，避免后续说明变化。七个新包均为prepared，用户实际发送后才登记为dispatched。
