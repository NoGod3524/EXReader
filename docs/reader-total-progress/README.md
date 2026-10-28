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

## 2026-10-26 latest audited snapshot

The fixed catalog was re-audited in [40417554862/1](https://github.com/NoGod3524/EXReader/actions/runs/40417554862)
at source `311d938e53c8a0bc2fc546c08780ec4abcd33af9`. The audit completed
at 23:07:58 UTC, with `evidence_ok=true` and no reported problems. It recorded
**66/108 (61.1%)**: foundation 12/12, platform host 54/84 and final combined
delivery 0/12. The October 25 New York cutoff remains 58/108 (53.7%), a gain
of eight outcomes and 7.4 percentage points. The audit artifact is `12695854108`,
11,526 bytes, SHA-256 `2452960f873a13546455b85428b7352e044630194ff2f3be574a0ee3f81513b4`.

This records the audited evidence at that source and time; it does not grant
the still-running composition candidates or imply that six-platform delivery
has passed. The remaining 42 outcomes do not have equal estimated effort.

## 2026-10-27 D21 receive evidence

[Actions audit 40545409342, attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/40545409342)
audited source `3fd35c03dac8e987b633b576157860e2c8c40891`. It reported
`evidence_ok=true`, no problems, and **69/108 (63.9%)**: foundation 12/12,
platform host 57/84, final delivery 0/12. The fixed historical October 25
cutoff remains 58/108 (53.7%). The previously audited current count was 66/108
(61.1%); the three added items are D21 cloud-original receive on macOS,
iPhone simulator and iPad simulator. Each uses the exact independent D21
source and run recorded in the catalog; physical-device and combined-source
delivery remain separately assessed.

Audit artifact `12751913273`, 11,787 bytes, SHA-256
`44130afd04d613eb32159b04bafa2b9d25275ba7f83e99e0097363d05d055794`;
expires 2027-01-25T16:54:01Z. This documentation commit is not the audited
source and does not alter the 108-item denominator.

## 2026-10-27 Android search jump history

The fixed-catalog audit [40577799778/1](https://github.com/NoGod3524/EXReader/actions/runs/40577799778)
at source `412419efbbadbec761bf6cded43d7ca36f4a6dac` completed with
`evidence_ok=true` and **70/108 (64.8%)**: foundation 12/12, hosts 58/84,
final delivery 0/12. The October 25 cutoff stays 58/108 (53.7%).

The added outcome is Android actual-reader search jump back/forward on the
API 34 emulator. Its exact-source D22 retained report and original artifact
were verified in the audit; the scope and original run are described in
[android-jump-d22.md](android-jump-d22.md). Physical-device and final unified
product acceptance are separate.

Audit artifact `12768660772`, 12,085 bytes, SHA-256
`0f64f81a1bce34c7e850bac4033ab309a95ad3fff0cd2748dc789eb575ccfdd7`,
expires 2027-01-25T20:24:44Z. This documentation commit is not the audited
source and does not change the fixed 108-outcome denominator.

## 2026-10-27 Android annotation exchange

The fixed-catalog audit [40578168891/1](https://github.com/NoGod3524/EXReader/actions/runs/40578168891)
at source `3ca92aee66109eac224d91082fdb08eef7419fed` completed with
`evidence_ok=true` and **71/108 (65.7%)**: foundation 12/12, hosts 59/84,
final delivery 0/12. The October 25 cutoff stays 58/108 (53.7%).

The added outcome is Android annotation exchange, including real host export,
preview, confirmation, duplicate and malformed-input refusal on an API 34
emulator. Picker and destination intents use test stubs. See
[android-annotations-d22.md](android-annotations-d22.md) for the actual
source, original report and authenticated artifact.

Audit artifact `12768097289`, 12,414 bytes, SHA-256
`6a4ae8db2e93e7335c740a3cb84460944275e2c4bd3585786a27591b0e4728be`,
expires 2027-01-25T20:27:11Z. This documentation commit is not the audited
source and does not change the fixed 108-outcome denominator.


## GTK candidate follow-up: visible search and account status

On source `00e370a28ed4b25718154ff68d914cbecb51fdb8`,
[run 40587741187/1](https://github.com/NoGod3524/EXReader/actions/runs/40587741187)
passed the current five-tool flow and the account status event checks. The
search result had a real visible 480 by 55 pixel rectangle after the driver
moved the native dialog; the observed history landing and back/forward steps
passed. The account label retained its semantic description in this observation.

The original [run 40585712410/1](https://github.com/NoGod3524/EXReader/actions/runs/40585712410)
failed both checks: its result rectangle was off-screen and its account label
could not be reacquired by description. No GTK product change was made and the
account result does not establish the cause of the earlier failure. Original
assertions remain. The same-run retained historical jobs and any final combined
candidate remain separately pending; this note does not increment the catalog.

## 2026-10-27 Android reader font library

The fixed-catalog audit [40590527294/1](https://github.com/NoGod3524/EXReader/actions/runs/40590527294)
at source `c2650f4ad535618da357160222c8253ee7df96b3` completed with
`evidence_ok=true`: **72/108 (66.7%)**, comprising 12/12 foundation, 60/84
host, and 0/12 final delivery outcomes. The October 25 historical cutoff remains
58/108 (53.7%). This adds the independently verified Android font-reader outcome
to the previous 71/108; its API34 emulator scope is documented in
[android-font-reader.md](android-font-reader.md).

Audit artifact `12774156023`, 12729 bytes, SHA-256
`212448a451b3d3693ba77c3d5d7039e658230fd1c774852fca9fe7856cadbe83`,
expires 2027-01-25T21:53:52Z. Unified-source Android validation remains separate.

## 2026-10-27 Linux GTK annotation exchange

[Actions audit 40600064302/1](https://github.com/NoGod3524/EXReader/actions/runs/40600064302)
at source `17b90f128bef72b44225f4acf5b1df81b04c8f19` completed with
`evidence_ok=true` and **73/108 (67.6%)**: foundation 12/12, host 61/84,
final delivery 0/12. The historical October 25 cutoff remains 58/108 (53.7%).
The added Linux host outcome is backed by the original same-run GTK UI report
and authenticated artifact recorded in [linux-annotation-export.md](linux-annotation-export.md).

Audit artifact `12779195101`, 13087 bytes, SHA-256
`326a2f200e904460ae0abc4d094541908e85f441694c4a7629e879db0ff7fdcc`,
expires 2027-01-25T23:08:52Z. The evidence-only documentation commit is not
the audited source.

## 2026-10-27 Android system original save

[Actions audit 40603619237/1](https://github.com/NoGod3524/EXReader/actions/runs/40603619237)
at source `d65c8a810426beeb727dfdeff61b85e611997257` completed with
`evidence_ok=true`: **74/108 (68.5%)**, foundation 12/12, host 62/84 and
final delivery 0/12. The added Android outcome is documented in
[android-original-save.md](android-original-save.md).

Audit artifact `12780100757`, 13375 bytes, SHA-256
`b02568010c5b36a1a8c387c6b874b2bb3ae8a23c85ff6bc4d869a8bcf2417fa0`,
expires 2027-01-25T23:39:31Z. The evidence-only documentation commit is not
the audited source.

## 2026-10-28 Apple native jump history

[Actions audit 40608384508/1](https://github.com/NoGod3524/EXReader/actions/runs/40608384508)
at source `94624bdc9535a5d5860150a4e1fae4e73740e0c7` completed with
`evidence_ok=true`: **77/108 (71.3%)**, foundation 12/12, host 65/84 and
final delivery 0/12. The three added outcomes are the independently audited
macOS, iPhone simulator and iPad simulator history flows documented in
[apple-history.md](apple-history.md).

Audit artifact `12781232403`, 13824 bytes, SHA-256
`f9c4e16feda52bb33d3929c2691a90bf08b57dab9e50db3006329a9c2aff2ba8`,
expires 2027-01-26T00:22:50Z. This evidence-only documentation commit is not
the audited source.

## 2026-10-28 Windows account and sync

[Actions audit 40645543804/1](https://github.com/NoGod3524/EXReader/actions/runs/40645543804)
at source `1adeabf2a672ddc0c200631e29897cfe76106afd` completed with
`evidence_ok=true`: **81/108 (75.0%)**, foundation 12/12, host 69/84,
final delivery 0/12. The historical October 25 cutoff remains 58/108 (53.7%).
The added Windows account/sync outcome and its scoped real-host evidence are
recorded in [windows-sync-account.md](windows-sync-account.md).

Audit artifact 12796749815, 16,175 bytes, SHA-256
`3a20669cd8886dd430777b47dc96547cd535360cfcdaf505c84c544552aba54c`,
expires 2027-01-26T06:43:01Z. This documentation-only commit is not the
audited source.
