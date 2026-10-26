# 完整首版总进度：固定口径 v1

依据 `docs/READER-PRODUCT-PLAN.md` 的既定首版范围及用户已要求接入的阅读功能，
按可验收结果固定为 **108 项**：共用底层 12 项、六目标各 14 项用户功能共 84 项、
最终互通与交付 12 项。完整明细在 `catalog.json`，不使用 agent 数、工作包数或测试条数。
OCR、TTS、商业获取仍按原范围作为可选模块，不加入本分母。

每项同为 1 分。只有覆盖该目标的真实证据获核对才计分；有代码、部分通过、
未测和缺少证据均不计分。独立已验收的底层/宿主功能计入其限定目标，最终同源码、
六平台双向互通、性能和实际可用交付另列 F01–F12，不能由独立结果替代。
这里衡量完整范围内已经验收的工程目标比例，不衡量剩余工时，也不宣称最终产品已通过。

108 项 ID 和描述作为本口径的固定分母。后续拆包、换模型、返修和新增测试不改变分母；
若用户明确改变产品范围，另开版本并同时保留旧版本，不能用改分母制造进度。
发现已计分功能回归时须重开该项并解释，不能永久保留旧分数。

从头回查两个时间点：

- 昨日：2026-10-25 23:59:59 America/New_York，即 2026-10-26 03:59:59 UTC。
- 当前：本次 Actions 审计时刻。

每个目标引用来源文档与真实 Actions run。审计读取实际 run/attempt/source、作业完成时间
及结论；失败运行中仅有限功能通过的两处证据，额外在 Actions 下载原 ZIP、核对摘要/字节，
重新读取指定的真实成功项。原完整失败仍保持失败。历史完成数只使用在昨日截止前
已经完成的证据；不能把今天补出的通过反写到昨天。

`reader-total-progress.yml` 仅执行这项只读审计，不构建或重跑产品。
审计产生逐项 JSON/Markdown 和汇总；任一证据身份失败都使审计失败，比例只能作为
待核实值，不发布为正式总进度。所有工件读取与计算在 Actions 完成。

首个完整证据核对通过的审计：
[40362836777 / attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/40362836777)，
source `a42ec29b`，2026-10-26 16:49:56 UTC。

| 时间 | 已验收目标 | 固定目标完成率 |
|---|---:|---:|
| 2026-10-25 结束（纽约时间） | 58/108 | 53.7% |
| 本次审计 | 61/108 | 56.5% |

增加 3 项、2.8 个百分点。当前基础目标 12/12、平台宿主目标 49/84、
最终联合交付目标 0/12；还剩 47 项未验收，不能将其按同等工时换算 ETA。

先前审计 `40357448866`、`40362503897`、`40362668848` 均保留失败。
Windows 工件外层 ZIP 与内层产品 ZIP 身份曾被混用，随后又误读了检查结果字段及
UI 报告所在层；当前分别严格核对两层身份，并读取外层所附 UI 报告中的 `passed`。
第三轮另有一次 GitHub API 502。没有改动 108 项分母或失败运行的授予范围。

原 14/17 交回率和 4/10 本轮门禁率保留其历史用途，不再作为完整阅读器总进度。

## Windows full-UI evidence admitted

Audit [40377996619 / attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/40377996619),
source `cf35f796`, completed its evidence audit at 2026-10-26 18:28:41 UTC.
Historical cutoff remains unchanged: 58/108 (53.7%). Current accepted outcomes
are 63/108 (58.3%): foundation 12/12, host 51/84, final 0/12.

The two additional outcomes are Windows annotation exchange and original export,
backed by run `40375338225/1` and the pinned reviewed evidence document.
The full Windows UI round passed, but font lease lifecycle measurement and the
complete sync-account cancel/retry matrix remain separate unmet outcomes.
Relative to yesterday this is five additional outcomes, 4.6 percentage points;
45 fixed outcomes remain unaccepted. This replaces the earlier current snapshot,
without changing its historical result or the fixed denominator.

## GTK export and search-history evidence admitted

Audit [40388795034 / attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/40388795034),
source `e3f9b773`, checked the original artifacts and reported 65/108 (60.2%).
The historical cutoff remains 58/108 (53.7%): an increase of seven outcomes,
or 6.5 percentage points. Foundation is 12/12, hosts 53/84, and final delivery
0/12; 43 outcomes remain unaccepted.

The two additional outcomes are Linux original export and search jump history,
supported by GTK GUI run `40385948659/1`. That run did not execute the original
navigation and batch-import retained suites. Annotation export and the full sync
failure/cancellation/retry matrix are also not granted by this evidence.

## 2026-10-24 historical reconstruction

For the user's three-day comparison, independent Actions audit
[40409045230/1](https://github.com/NoGod3524/EXReader/actions/runs/40409045230),
source `3d40db4badeacaf3d04e76f3d7fd1c8dc2938c36`, reused the same fixed 108
requirements and evidence and moved the historical cutoff to 2026-10-25
03:59:59 UTC (2026-10-24 23:59:59 New York). It verified the evidence and
reported 12/108 (11.1%) at that cutoff and 65/108 (60.2%) at the audit time.
This is a retrospective count of presently catalogued, currently verified
requirements whose cited runs had completed by the cutoff, not an independently
recorded historical snapshot. It may omit work whose earlier evidence is no
longer represented by a currently verified item. The standard October 25
cutoff and catalog on the composition branch remain unchanged.
