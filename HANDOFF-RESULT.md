# C02 交回结果

- 分支 `codex/reader-fw-c02`，起点 `0889f7d1e9a537c6c1b05456547e016b26e1cd85`；受测实现 `8796812478b01cb965338103260a19d143463010`（docs 封存提交见 git log，仅改 docs/HANDOFF）
- **accepted=false**：三轮 CI 用尽，无一轮得到完整无问题汇总。工具已在真实简洁版宿主上端到端运行。
- Windows 简洁版 = 起点源码 `EXR_READER_WINDOWS_COMPACT=ON`；GTK 简洁版 = 二次 checkout `57203a52…`，SDK 源 `edddc463…`（3.41.0）。consumer/producer/SDK/verifier 分开记录。

## Runs（均 attempt 1，仓库 NoGod3524/EXReader）
| run | source | 结果 |
| --- | --- | --- |
| 40214285241 | 169b0be3 | 失败：Windows warm 复用 profile 恢复阅读视图→首屏等待 3600s，作业超时取消；汇总因缺 bundle 崩溃。GTK 两 round 各 384 样本 0 不通过 |
| 40228584162 | fd95c5de | 失败：Windows n500 resume 恢复位置不一致（r1 3 次、r2 2 次）；GTK r1 launch 05 导入线程未启动（2 样本失败） |
| 40230206029 | 87968124 | 失败：Windows r2 n5000 resume-02/03 失败；GTK r2 launch g2-n5000-05 被启动记录标记失败（其 384 样本均 ok）。Windows r1、GTK r1 无问题 |

最新 run 作业：预检 121280093680、win-build 121280133727、gtk-build 121280133723、Windows r1/r2 121281076768/121281076711、GTK r1/r2 121281852128/121281852220、verify 121283017714。
工件 ID/字节/SHA-256/有效期（2027-01-23T20:19:16Z）见 `docs/reader-final-c02/validation.json`。
程序 SHA-256：Windows `72e39bf5…aea18`，GTK `2b2208d6…bdf22b`（全文在 validation.json）。

## 已测 / 未测 / 缺口
- 已测：500 与 5000 本原件、两个独立 round（各自独立 runner）、冷启动/首屏/搜索/开书/翻页/书架滚动/返回/导入/内存 RSS，样本原样保留，逐样本身份断言、分层(stratum)统计与预算建议（approved=false）均已实现并在 CI 运行。
- 未完成：没有一轮完整 `measurement_complete=true`，故不能给出可引用的 p50/p95/最大值或新 CPU 分层基线；summary.json 在工件 12612926140（仅 Actions 内可解析，本地未下载）。
- 疑似 owner/时序缺陷（待 root 诊断，工具未改断言）：Windows 简洁版重开后恢复阅读位置有时与上次保存页不一致或根本不恢复（resume 组，r1/r2 随机出现，仅在结束前保存的竞态下复现）；GTK 导入对话框后导入线程偶发不启动（原 G11 采样器路径）。第三项（g2-n5000-05 observation 失败原因）需在工件 `c02-gtk-round2` 内查看 launches.json，本地未解析。
- 建议下一步：root 判断是否接受上述两个现象为产品缺陷；若为工具问题，再批准额外 CI 轮次。
- 不覆盖：帧时间、物理机、读屏、其他平台；Windows 导入走展开面板路径，GTK 简洁宿主无自动续读。
- 约束偏差（如实）：本地曾两次用 python 做文本编辑替换（非构建/测试/解析工件），其余全部在 Actions。未开 PR、未推默认分支、未发布。
