# 格式组合任务暂停检查点

恢复结果：用户重连后已明确继续。第 1 轮 `40240804927/1` 保留 failure；Windows 缺 SDK DLL 的部署问题已用原 S13 程序在 Actions 做无 DLL/补 DLL 正反验证。修复源码 `8015c576822d5284dedfea17428ecf1a240befd0` 的第 2 轮完整验收 `40244430230/1` 已 success：双 OS 各原 169×2、RTF100、CBZ103、F5 v2 18/18，strict 实际认证同轮原 ZIP 并重算通过。未启动第 3 轮。SDK 采用仍待 root 审查；完整身份见 [RESULTS.md](RESULTS.md) 和 [acceptance.json](acceptance.json)。

以下是断网前保留的历史暂停记录，不能用其“运行中”状态覆盖上面的真实终态。

用户要求暂停并准备断网；已停止新增派修、推送和 Actions。已在云端执行的完整 run 不取消，也不等待终态。恢复须等用户明确继续。

## 当前身份

- 独立 worktree：`C:/Users/Oscar/.codex/worktrees/reader-format-combination/EXReader`。
- 分支：`codex/reader-format-combination`。
- 当前已推送完整受测源码：`03530b6a4c97275432dffdcab80c39486475645a`。
- 完整 run：`40240804927` / attempt 1；这是已授权上限三轮中的第 1 轮，尚未授予通过。
- 最近一次已知状态：preflight、corpus 成功；producer-windows `121312197355` 与 producer-linux `121312197422` 执行中，strict 尚未终态。此后因暂停未再查询。
- 同源码轻量 run `40240701702` 成功；122 项协议拒绝、两平台 argv 向量与 Windows 5 项 UTF16 检查、两补丁交换顺序得到同一 tree 均已过。

本检查点仅本地提交，不推送；云端 source 和 origin 仍为上面的 `03530b6a…`。实现代码均已在该 source 内，无待保存的源码修改。

## 已实施

仅在隔离 SDK 副本应用登记的 RTF/CBZ 两补丁；冻结 SDK、旧 F5、宿主未改。v2 manifest 仅 dataset 标识与 Crowley query 改动，原 18 输入/许可/预期不变，1710 仍为 0。

`common.py` 固定来源/深比较/安全原 ZIP 与实际程序认证；`argv_utf8.c` 薄包装原 F5 main，严格宽参数→UTF8，原业务主体不改；`driver.py` 共用两套 SDK 安装前缀，运行两边原 native 169、RTF100、S13 CBZ103、原 v1 失败对照与 v2 实际 18 文件；`strict.py` 下载同 attempt 原 ZIP，核实际程序/DSO/输入及完整原始结果。完整结果必须等该 run 实际终态和严格汇总。

## 恢复后

1. 先只读检查 `40240804927/1` 终态与实际 job 日志，不凭本检查点预判成功。
2. 若成功，在 Actions/只读日志中核 baseline/candidate 各169、RTF100、CBZ103、v1失败保留、v2两平台18/18与原 ZIP/程序身份，再封存真实结果。
3. 若失败，保留本轮，按实际错误修正；最多还可使用两轮完整组合 CI。所有语法、构建、测试、输入与工件下载/解压/解析继续仅 Actions，不在本机验证。
4. 不直接采用 SDK、修改冻结记录、发布或接入宿主；root 审查后才处理新的 SDK 候选。
