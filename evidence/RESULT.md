# Unknown-item probe · 2026-11-03

## 三态判据

| 状态 | 判据 |
|---|---|
| 通过 | 对应 Ubuntu 验收项通过；不将 protocol 通过等同于完整 reading-required 通过 |
| 失败且可归因 | Ubuntu 目标环境拒绝当前树，记录具体门槛与证据 |
| 不确定 | 环境与代码效应未分离，或目标结果未取得 |

此前“B 被证伪”结论撤回。首次本机结果应为：**不确定（本机 Windows 文件锁）**。

## 三方对照

三方分别使用独立 worktree、独立干净的非 OneDrive TMP/TEMP/TMPDIR，均为 Windows / Python 3.14；未修改被测 check_reading_release.py。

| 树 | check_reading_release.py exit | 首条异常 |
|---|---:|---|
| baseline | 1 | PermissionError: [WinError 32]，TemporaryDirectory 清理 library.sqlite 被文件锁阻塞 |
| framework | 1 | PermissionError: [WinError 32]，TemporaryDirectory 清理 library.sqlite 被文件锁阻塞 |
| preview | 1 | PermissionError: [WinError 32]，TemporaryDirectory 清理 library.sqlite 被文件锁阻塞 |

归因：**同因、环境；不是本次合并独有**。换到非 OneDrive 临时目录后三方仍同因失败；不据此判断 Linux gate。

## Ubuntu 目标验证

- preview commit: `769e509566204f53c0020ddbdb94d568bb571efe`（95100501 + framework 8ca964fc 合并预演，保留 collect/cached/fetch 三路径）。
- check_collect.py：22 tests PASS（上一轮已执行，重建使用原样保留文件）。
- run: https://github.com/NoGod3524/EXReader/actions/runs/41691589828 ，event=workflow_dispatch。
- protocol job `126111282429`：labels=ubuntu-22.04，conclusion=success。

| Script | Ubuntu result |
|---|---|
| check_reading_release.py | PASS |
| check_reading_required.py | PASS |
| check_reading_real_environments.py | PASS |
| check_reading_cpu_export.py | PASS |
| check_reading_release_plan.py | PASS |

Ubuntu performance job `126111282946`：failure；labels=ubuntu-22.04；`measurement_valid: false`；首个拒绝原因 **SDK protected tree changed**。

该门槛在 tools/measure_reading_real.py:544–545 比较 HEAD 的受保护 Git 对象与固定 SDK `9854061be331fe603a1822d9b2b36ee357154927`。只读对象比对结果：

| 树 | 与固定 SDK 不同的受保护对象 |
|---|---|
| 95100501 | src / include / cmake / CMakeLists.txt |
| origin/codex/framework @ 8ca964fc | 无 |
| preview @ 769e5095 | src / include / cmake / CMakeLists.txt |

preview 的四个对象逐一与 95100501 完全相同；性能拒绝反映**基线与继承的固定 SDK 门槛不相容**，不是这次 collect.py 取证分支处理新增了受保护目录差异。未运行 Ubuntu 基线完整 workflow，不将此对象证据扩大为所有失败的三方云端对照。

其它云端失败：Apple mobile 与 macOS desktop 报 Installed SDK version differs from the explicitly selected version；这些不是 Ubuntu 主判据。

完整 run 已结束：status=completed，conclusion=failure。最终 reading-required job 126118983938 失败，accepted=false，problems=["upstream job failed, was skipped or did not finish"]。详见 cloud-run.json、cloud-jobs.json、ubuntu-reading-required.log。

T1 改判：**B 待 refreeze**。Ubuntu 五项 protocol 全通过；性能拒绝发生在采样前的 SDK protected-tree 身份检查，不是性能退化的测量结论，也不证明 Git/PR 路径不可行。docs/validation/sdk-baseline.json 的 refreeze_trigger 规定受保护树变化须新 candidate 与新证据。

该断言对方案 A（另建 main 整合同一产品树）同样成立：分支选择不能绕过基线登记。其它平台失败保留独立原因，不把 refreeze 当作它们已经通过。

一句话：**B 待 refreeze，A 同样须重新登记该产品树；分支选择不能绕过基线登记。** 本轮未实施基线变更。

## 隔离范围

PR #28 仍为 draft，head=7108a166，11 个新增文件；预演代码未进入该分支。默认分支仍为 codex/framework @ 8ca964fc，ruleset 未改动；未开 PR，未推送默认分支。preview 远端与本地分支均已在 run 结束后删除；独立工作目录停在 detached preview commit，日志保存在本结果目录。

## 完整云端 job 结果

| Job | Conclusion |
|---|---|
| protocol | success |
| performance / reading-performance | failure |
| profiles / reading (reading-core) | success |
| native / fuzz | success |
| profiles / reading (reading-library) | success |
| platforms / reading windows-2022 (reading-library) | success |
| native / android | success |
| native / apple-mobile | failure |
| native / sanitizers | success |
| platforms / reading macos-15 (reading-core) | success |
| platforms / reading macos-15 (reading-library) | success |
| native / desktop (windows-latest) | failure |
| native / desktop (macos-15) | failure |
| platforms / reading windows-2022 (reading-core) | success |
| native / desktop (ubuntu-22.04) | success |
| corpus / R2 real document acceptance | success |
| reading-required | failure |
