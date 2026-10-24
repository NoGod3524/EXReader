# 非 P0 Claude → DeepSeek 接续准备

用户要求只保留 Claude 的六个 P0：**J01、J04、J05、J10、J11、J22**；其余19个包转 DeepSeek-V4.1-Flash 1017 High / PTC。已实际观察新会话为该模型、High、PTC、完全权限，未改权限设置。

## 已保存的材料

root读取真实Git工作树。18个已有非P0工作树HEAD均为固定起点 f43baf9182d75907c0cb5d6f77048f27bca8c950；45份未提交源码已另存副本，保留原件且未在原工作树提交、重置、清理或执行测试。记录位于：

`C:/Users/Oscar/exreader-agents/transfer-checkpoints/2026-10-24-J-nonP0/checkpoints.json`

各包子目录含 checkpoint.json、tracked.patch 及 files/ 源码副本与摘要。J24未找到独立分支/工作树；实际Claude“分发功能 Unix 实现”会话同时收到了J24和J25，不把两个包误当两个独立对话。

## 当前停止/接续边界

- Claude当前五小时100%、周74%，usage credits余额$0；另有$55仅云会话优惠额，不能当作本机Code余额或本轮已花费用。
- root已关闭Unix/Windows分发共用会话的“额度重置后自动继续”。其它会话需逐项核对；额度错误不被写成root已完成全部暂停/删除。
- 用户已恢复Windows桌面。删除操作的单次批量确认仍在等待，未执行删除；六个P0保留。
- J02已发一次**只读预检**，在root明确释放且对应release-J02.json存在前禁止修改。其它18包尚未发送，不能说已全部开工。
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
