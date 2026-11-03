# 六端阅读器门禁移交
目的地：独立六端阅读器项目。仓库URL、接收人和排期尚未指定，握手状态为待接收；不声称已经移植代码或完成验收。
来源：audit/f07-authoritative-symbols-20261103 @ 95100501eeef9c6325be8b3882aa400c99cf000f 的 docs/reader-total-progress/catalog.json。v1 state 原样保留。

| 项 | 移交的六端产品范围 | 依赖与保留边界 |
|---|---|---|
| F01 | 六目标同源完整产品功能 | 独立产品任务书、应用和统一验收图 |
| F03 | 六目标书架/分类/系列/删除恢复一致 | 完整接收投影；Windows/GTK SDK示例另验，不转授旧F03 |
| F05 | 完整客户端离线重连、多头/墓碑、取消/崩溃 | 原失败与not-run保留；SDK示例恢复面独立验 |
| F08 | 产品帧时间、内存、可交互预算 | 固定产品书库与平台；SDK基准仍留本仓库 |
| F09 | 六端UI可达、键盘、可访问性和读屏 | 实际辅助技术与原生操作证据 |
| F10 | 应用隐私/凭据/文件/临时清理出口 | 真实产品场景；SDK所有权及安全边界仍保留 |
| F11 | 移动部署和真机能力 | 真机、签名与部署权限；build-only不等真机通过 |
| F12 | 产品升级、旧库、安装/导入/同步说明 | 产品用户流程；SDK ABI/schema与许可证仍保留 |

F02/F04/F06/F07 的历史记录不改变；F07 Windows/GTK archive-level provider缺口不能据此删除。旧证据不等当前候选树通过。
[唯一证据索引](https://github.com/NoGod3524/EXReader/blob/de0832112e92c47bc1a47969236dd2376a0ed55f/evidence/INDEX.md)列出F05 acceptance、F03 sdk-examples和四份custody patch。补丁保管不等于在新基线可应用或通过；不挪用旧R3预算。
