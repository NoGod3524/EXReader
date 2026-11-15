# D-FINAL-B 台账与 F08 独立复核

基线：`origin/main` / `38a7031827d5664fd4dd6e8166c9135a7d829355`，catalog blob `bedefd210b8d174c7726827cba3fbde1e006b7c7`。本复核只读取代码与历史存档；没有重新授予历史运行或性能验收。

## 当前实测基线

`catalog.json` 当前为 **verified 99 / partial 0 / pending 9**，108 项；group 为 foundation 12 / host 84 / final 12。用户给出的 99 / 1 / 8 是此前 D-FINAL-B 合并 `64a671d9` 的状态；后续 D-FINAL-C 把 `H.ipad.annotation_exchange` 从 partial 改为 pending，见 `docs/reader-total-progress/dfinal-c-audit.md:66`、`:67`。本 lane 不应回改该条目以凑回旧计数。

## 验收定义

v1 中无 `acceptance` 字段，实际固定定义是 `title`，不应补造原文字段。

| 项 | 原文（逐字） | verified 所需证据 |
| --- | --- | --- |
| F08 | `catalog.json:1704`「固定书库/平台的产品帧时间、内存及可交互预算获真实验收」 | 同源六目标完整产品在固定设备或 runner、固定规模书库与负载上，真实记录呈现帧 p50/p95、峰值内存、首次可交互及预算验收；渲染函数计时或 SDK 结果不替代产品 UI（产品计划 `:156,195–196`）。 |
| F09 | `catalog.json:1712`「默认简洁且完整功能可达，六端完整键盘/可访问性与读屏证据分列」 | 六目标分别保留简洁默认入口及所有功能真实可达、全部交互控件名字/角色/焦点顺序，并独立登记真实读屏输出（产品计划 `:157,191–193`）。 |
| F10 | `catalog.json:1720`「全链路隐私/凭据/文件稳定性/临时文件清理的真实安全出口」 | 六目标宿主全链路记录安全存储与会话回退、凭据不落日志/书库/同步载荷、HTTPS/证书/跨源隔离、文件稳定性、原子发布以及正常/失败/崩溃后的清理（产品计划 `:165,168,185–187`）。 |

路径前缀分别为 `docs/reader-total-progress/catalog.json` 和 `docs/READER-PRODUCT-PLAN.md`。当前任务明确授权本 lane 本机编译/测试、三项 state/evidence 审计及 main-base 新分支；沿用历史只读规则不应成为重复请求许可的理由。

## evidence 字段约束与建议

`tools/reader_composition/total_progress.py:620–635` 固定 108 项身份、分组、产品计划 blob、合法 state，并要求 evidence 数组元素均为 catalog 顶层注册的键。`:631` 只要求 verified 条目非空，pending 可为空；`:642` 只有 state=verified 且所有引用证据核对通过才计分。

因此不能把本地报告路径或「缺什么」文字直接放进 evidence 数组。当前顶层没有本轮或历史 perf/a11y 的注册键；不应使用无关通用宿主 run 充作 F08/F09 的性能或 a11y 证据。保持这两项 evidence=[]、在 note 明确补充报告和缺口是诚实且兼容验证器的选择。若确需新报告直接进 evidence，需要修改顶层注册（超出“只动三项”）或扩展 schema/验证器，均不属于本 lane 必要改动。

F10 已有真实的组件证据键 `credentials` / `sideload` / `batch` / `sync`，可在该项 evidence 直接引用，并在 note 清楚限定为历史组件证据，state 保持 pending：

| 键 | 已登记源码 / run | 实际范围与缺口 |
| --- | --- | --- |
| credentials | e2247deb / 40057087875 | 独立凭据模块。`docs/validation/reader-credentials.json` 记录 Windows 24、Linux 34、macOS 29、iOS simulator 23、Android emulator 46 checks；Windows unavailable、iOS lock、Android service failure 与实际宿主全链路缺。 |
| sideload | c2c75f99 / 39980923147 | 独立导入模块；不能转授六端系统选择器/URI/安全作用域和实际宿主文件稳定性。 |
| batch | 67cee469 / 40068645513 | 三平台目录预算/链接替换/并行与文件观测回归，产品计划 `:137–140` 保留 668+4 项及 Linux TSan；不能转授移动入口和实际 UI。 |
| sync | a32602be / 40065344267 | macOS/Linux/Windows 原生 HTTPS/同步组件，产品计划 `:121–124`；不含完整 iOS/Android 会话、宿主凭据 UI 或六端安全出口。 |

这些是仓库已存档历史结果，此复核未下载原 ZIP 重新认证；`evidence/dfinal-b-20261114/historical-run-api.json` 保留上一轮 API 核查。不能写成当前树刚跑过。

## 现有 F08 基准复核

读取 `examples/windows/check_shell_budget.inc` 和 `tests/reader_perf_windows/render_budget.py`：

- 64 样本 nearest-rank p95 取下标 60 正确，p50 取第 32/33 样本均值正确。
- 两个 cohort 使用同一进程的 `PeakWorkingSetSize`（C 文件 `:22–24`），第二值是累计 high-water mark。比值只检查后半程是否继续增长，无法比较两个独立生命周期内存峰值，也不是跨 revision 性能预算。
- 原始 64 个逐次样本未输出，只保留 p50/p95。`docs/validation/PERF-BASELINE-POLICY.md:7–10` 要求原始样本、环境、源码、二进制/导出器散列与统计导出链。
- 测量对象是生产宿主 load_frame/render 路径；没有真实 present、没有首次可交互、没有导入后固定规模完整书架。三本真实原件的 pg10 在上一轮返回 EXR_LIMIT，没有它的有效采样。以上均不能写为 F08 通过。
- 现有 policy `:14` 要求性能产物 `advisory=true / accepted=false`；命令执行成功与产品预算获准应分列。

本机可实施的最小升级是保留逐次样本、由脚本重算统计；对固定原件/字体分别启动独立进程，记录每进程峰值并与同机基线二进制做相对比较；记录两个二进制与字体散列、源码、编译环境和命令。完整产品帧与交互仍需当前产品的真实桌面呈现采样；Linux/Apple 需对应 runner，iPhone/iPad/Android 真机必须另列。

## 历史记录交叉核对

- F08 Windows 最新存档为 `docs/validation/reader-perf-windows.json` round2 / run40086319655 success；GTK 存档 `reader-perf-gtk.json` / run40086971620 cloud-verified。它们的范围不等于当前共同源码性能预算。
- F09 Windows / run40084309431 job success 但 accessibility_accepted=false；GTK / run40082300842 refusal gate failure；Apple / run40096206815 accessibility_accepted=false；Android / run40082957400 success 但 accessibility_accepted=false、physical_device_execution=false、talkback_speech_verified=false。
- 三项最终应保持 pending；本轮能补足的子证据不得覆盖六端完整范围或真实辅助技术缺口。

补充 schema 检查：`.github/workflows/ledger-authority.yml` 的 R1–R6 与 `total_progress.py:620–645` 都没有 exact-key / additionalProperties 约束；新增每条 `evidence_details` 字段技术上会被接受，`dict(row)` 还会将其原样带入报告，但没有验证、没有计分含义。建议不扩展：使用现有 note 放本轮报告与缺口，evidence 只放已注册且范围真实的键，避免第二条未经验证的证据通道。
