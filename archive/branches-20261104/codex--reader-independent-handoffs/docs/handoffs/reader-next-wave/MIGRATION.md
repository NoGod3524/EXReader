# 非 P0 Claude → DeepSeek 接续状态

用户要求只保留 Claude 的六个 P0：**J01、J04、J05、J10、J11、J22**；其余19个包转 DeepSeek-V4.1-Flash 1017 High / PTC。已实际观察新会话为该模型、High、PTC、完全权限，未改权限设置。

## 已保存的材料

root读取真实Git工作树。18个已有非P0工作树HEAD均为固定起点 f43baf9182d75907c0cb5d6f77048f27bca8c950；45份未提交源码已另存副本，保留原件且未在原工作树提交、重置、清理或执行测试。记录位于：

`C:/Users/Oscar/exreader-agents/transfer-checkpoints/2026-10-24-J-nonP0/checkpoints.json`

各包子目录含 checkpoint.json、tracked.patch 及 files/ 源码副本与摘要。实际Claude“分发功能 Unix 实现”会话同时收到了J24和J25。删除J12时应用另行提示会清除临时工作树，root确认后从备份逐文件恢复四份源码并核对摘要；新目录为 `C:/Users/Oscar/exreader-agents/j12-sync-status-view`，沿用原分支。J24已从固定起点建立独立分支及目录 `C:/Users/Oscar/exreader-agents/j24-distribution-unix`。

## 当前停止/接续边界

- 迁移前观察到Claude五小时100%、周74%，usage credits余额$0；另有$55仅云会话优惠额，不能当作本机Code余额或本轮已花费用。
- 用户明确确认批量删除后，19个非P0包对应的18个Claude会话已全部删除。六个P0会话保留。应用提示删除范围为此电脑，服务端副本按Anthropic数据政策保留。
- DeepSeek已分别收到全部19包的实现指令：J02、J03、J06、J07、J08、J09、J12、J13、J14、J15、J16、J17、J18、J19、J20、J21、J23、J24、J25，一包一会话。每会话实际核对 Flash1017 / High / PTC / 完全权限。J02原只读预检已收到明确“开始实现”后续消息。
- 当前无待派发包。19个release文件均已写入checkpoint目录；实际派发与唯一writer状态见 `migration-state.json`。收到实施指令不表示实现或验收已完成。
- 期间电脑操作遇到状态查询超时和 GetCursorPos / 0x80070005；按恢复流程停止旧输入，用户回普通桌面后重新定位窗口，逐项继续，没有在未知状态重复发送任务。
- 接续者必须复用本包已有绝对工作树及未提交代码；先读固定任务页及共同约束，不reset/clean/rebase、不覆盖半成品、不在其它任务目录新开writer。
- 原owner停止核实后，再由root记录释放、更新writer并发送开始实施。所有构建/测试/语法检查/夹具/benchmark/工件解析继续仅Actions。

任务逐项路径和真实派发状态见[migration-state.json](migration-state.json)，功能与验收仍以[25包完整任务页](INDEX.md)为准。

## Credits预算估计

官方当前Sonnet5.5 API价：输入$2/百万token，输出$10/百万token；付费usage credits按标准API价。套餐百分比不能反推本次已扣美元。

| 后续范围 | 估算USD credits |
| --- | --- |
| 六个P0 | 40–120 |
| 其余19包 | 60–180 |
| 全25包实现与首轮CI收口 | 100–300 |

这是按任务规模、上下文读取、实现及调试轮数作的预算范围；没有各会话实际token与缓存账单，不能写成已发生消费或精确报价。

官方资料：[模型价格](https://platform.claude.com/docs/en/about-claude/pricing)、[付费usage credits](https://support.claude.com/en/articles/12429409-extra-usage-for-paid-claude-plans)。
