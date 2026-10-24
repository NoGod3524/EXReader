# 原生宿主共同源码候选

候选分支 `codex/reader-hosts-integration`；当前未验收，不能拼接原分支绿灯。直接普通merge保留以下来源及其失败历史：

| 来源 | 固定交回HEAD | 原范围 |
| --- | --- | --- |
| G1 | `3bcc6511c928665c0889a33bc98cf5e1bfadaccc` | 三桌面18包组合及原Windows账号 |
| Windows搜索 | `12f4f06cae2115fba90d3d43ebb0c291ea11e99a` | TXT13、多格式/生命周期25、键盘17及全部保留套件 |
| GTK阅读记录 | `401729ba9537b58c8566372fb953384ce61381d7` | 阅读30/后端261、Nav/Search及保留套件；真实页面配色2项失败 |
| Android阅读记录 | `5d7da81495e545901f7fc802af00e0b779d1d8c4` | API34 default x86_64模拟器，阅读16及保留套件 |

合并基点 `33167f2faa6cabae6656b8c1089a799dc7e5549e`。唯一冲突是codec安装消费者的Apple链接map参数，保留G1已有 `elseif(APPLE)`。Android来源带来原样已验的sideload导出分支：Android用 `renameat2(..., RENAME_NOREPLACE)` 发布原件，其余平台行为不变。SDK仍冻结 `9854061be331fe603a1822d9b2b36ee357154927`，3.40.0/ABI1，schema/wire/anchor不改。

新流程复用原workflow作业内容及原消费者，在同一run/attempt执行三桌面组合、Windows搜索及原回归、GTK全部原回归、Android原全套。原始检查不删断言。GTK设置仍按实际35项报告登记，不把两项失败变成预期拒绝；整体accepted保持false，只有各自真实通过的声明范围可独立登记。Apple宿主原回归、Android后续Preferences和GTK新批量导入尚由各自owner推进，不在本候选中预先授予。

源码 `927201157d045f7ff994a1241a7e7703bc360fa3` 的 [run 40138835223](https://github.com/NoGod3524/EXReader/actions/runs/40138835223) / attempt1已实际启动。当前已确认源码/语法门禁、三桌面组合、组合严格汇总、Windows搜索及严格汇总success；GTK与Android仍运行，最终共同汇总尚待执行。这份状态记录不把运行中的作业当作通过。

原严格Windows与三桌面组合验证器只显式改调用workflow身份，保留原全部工件认证；最终读取真实GTK/Android报告，核同源/同轮/逐项结果与实际二进制。工作流、语法、负例、构建、测试及所有工件处理仅Actions。
