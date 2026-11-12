# Evidence index

## 台账计数口径（v1 108 项）

| 口径 | 数值 | 依据 |
| --- | --- | --- |
| 名义（catalog 记账） | 99/108（verified 99、partial 1、pending 8） | [catalog.json](../docs/reader-total-progress/catalog.json) |
| 有总台账审计支撑 | **99/108** | [run 43295866204](https://github.com/NoGod3524/EXReader/actions/runs/43295866204)（绑定 main `ca9e9f6b`，2026-11-12T20:01Z）`report.json`：current_done=99、evidence_ok=true、problems={} |
| 当前树可复现 | **是** | 同一 run 43295866204 在 `ca9e9f6b` 上跑完，evidence_ok=true；99/108 与 catalog 记账一致 |
| 产品级 final 组（F 项） | 名义 4/12（F02/F04/F06/F07）；当前树审计同为 **4/12** | 审计 run 43295866204 的 by_group.final.done=4 |

99/108 是历史记账，不能当作当前整树通过。


- 2026-11-05 — [Pachinko首行缩进像素复核：A](real-books-20261105/TEXT-INDENT-PIXELS.md)：原PNG同段首行/续行66/44px（差22px），另一段65/44px（差21px），匹配1.2em×18px；布局原点差21.600002px。撤回“首行齐平／缩进缺失”观察，不登记为引擎缺陷；未指定作者样式的宿主CJK默认2em需求仍归第5步。

- 2026-11-05 — [CJK验收范围与责任分流](real-books-20261105/CJK-READABILITY-CHECKLIST.md)：原15本中文样本0；草枕日文结果不能替代中文验证。已查 [text-indent](real-books-20261105/TEXT-INDENT.md)：草枕普通段1em，葡语Pachinko普通段1.2em，均有显式零缩进；缺省2em策略归第5步。行宽/上边距归宿主第3步；hyphenation归后续引擎版本，不在2a范围。

- 2026-11-05 — [视觉评审落盘及相邻页定性](real-books-20261105/VISUAL-REVIEW.md)：owner确认草枕竖排列序/图文位置正确；Pachinko第257页为第10章末页，文本范围耗尽20145/20145，第258页为独立装饰图，第259页开始第11章。仅登记 [SDK max_measure 缺口](real-books-20261105/SDK-GAPS.md)及后续排版验收项。原始15本语言为英文13、葡语1、意语1、日文0；草枕日文另列补充样本。

- 2026-11-05 — **构造型扫描件已通过，owner 授权记账**：[来源与验收范围](real-books-20261105/SOURCES.md#1-构造型扫描件)。Malcolm X 前 20 页以 200 dpi 构造成 image-only PDF；20 页解析/渲染成功、文字层为 0。标注“构造型扫描件，结构等价，非扫描噪点样本”；不计 OCR 或真实扫描噪点覆盖，文件不入库。

- 2026-11-05 — [真实竖排 EPUB 的 CSS 前缀别名修复](real-books-20261105/CSS-ALIASES.md)：《草枕》竖排字形 0→107609、462/462 页 vertical-rl、空白页 0；标准对照保持 199；Pachinko 1194/1194 页像素哈希一致。横排 314 页与竖排 462 页不可比；输入/字体/字号/视口不变。本轮 src/style.c 触及受保护树，已登记 [R 候选变更清单](ci-packaging-20261103/R-PROTECTED-TREES.md#2026-11-05--css-竖排属性别名修复)。未实现 text-combine-upright 合字排版。

- **已知失败（已修复）**：版本扫描曾将归档历史消费方计入当前源码，产生27条错版本诊断；`tools/check_version_consistency.py` 已按 `archive/**` 排除历史快照，验证结果见 [PR #46](https://github.com/NoGod3524/EXReader/pull/46)。

- **已知问题／损失**：本轮分支清理 recoverable=no 共 86 条，内容不可恢复；清单见 [DELETED-BRANCHES.csv](../archive/DELETED-BRANCHES.csv)。297条分支的归档实物仅保存在标签 `refs/tags/archive/branches-20261104`（`56c6ccfc`），[查看快照](https://github.com/NoGod3524/EXReader/tree/56c6ccfcb8b3662a976f7c4e5f704ae2f6f766f1/archive/branches-20261104)；main 保留登记，不包含归档实物目录。

- 2026-11-03 — [E1/E3 performance baseline policy](../docs/validation/PERF-BASELINE-POLICY.md): environment-bound raw-sample budgets, advisory until strict re-verification; hard expiry 2026-12-15 America/New_York; [tracking #32](https://github.com/NoGod3524/EXReader/issues/32). P evidence: [ci-packaging-20261103](ci-packaging-20261103/RESULT.md).

- E1/E3 deployment verification status: [SPLIT-STATUS.md](ci-packaging-20261103/SPLIT-STATUS.md). Required context changed; evaluate limitation accepted; static core branch/job checks complete, live verification deferred to the first real PR.

- 2026-11-03 — [Final gate probe and P self-defect repairs](final-gate-probe-20261103/README.md): native run41726208700 job conclusions/first errors, producer passed/advisory separation, and [533-binding content-identity remap](final-gate-probe-20261103/baseline-remap.json). Subsequent native/core results are recorded in the same directory; core runs only after native succeeds.

- 2026-11-03 — [P self-defect rerun](final-gate-probe-20261103/README.md#repair-verification-native-rerun-41732293021): native run41732293021 passes on f19788b7; one conditional core dispatch returns HTTP404, no core run created. No retry or default-branch change.

- 2026-11-03 — **Milestone: first end-to-end validated ledger/base native**, [run41732293021 and per-job conclusions](final-gate-probe-20261103/README.md#milestone-accepted-by-owner): seven native jobs + four hygiene checks pass on f19788b7, accepted by owner.

- 2026-11-03 — [One-time core PR probe #36](final-gate-probe-20261103/README.md#one-time-pr-core-probe-registered-failed-cleaned-up): Required native reading SDK core registered, run41774219995; protocol/native/profiles/platforms pass, corpus exact-version mismatch fails, final reading-required-core fails. PR closed without merge; temporary branch deleted.

- 2026-11-04 — [Corpus consumer version repair](corpus-version-20261104/README.md): unpin active corpus/OCR consumers; scan CMake package version literals; consumer downgrade negative exits 1 with file:line and source-version guidance.

- 2026-11-04 — **Core passes on ledger/base**, [run41782427456 / PR #38](corpus-version-20261104/README.md#single-pr-core-rerun-pass): protocol/native/profiles/platforms/corpus and reading-required-core pass on repaired base1e709837; one round only. PR closed without merge, temporary branch deleted; default-branch transition awaits owner.

- 2026-11-04 — [Main transition S1–S3](main-transition-20261104/README.md): main created equal to ledger/base1e709837; single trigger-line commit682e1ab5; PR #39 core run41786091768 registered and passed. PR closed, temporary branch deleted. S4/S5 not executed; default remains codex/framework pending separate owner authorization.

- 2026-11-04 — **默认分支切换与 S5 门禁拦截验证**：[完整记录](main-transition-20261104/README.md#s4-owner-confirmed-switch-and-s5-closure)。S1 main 初始 sha `1e709837cb8a50816e94bf611ca4404f19f80abf`；S2 `682e1ab5`；S3 run `41786091768` 通过；S4 `default_branch: codex/framework → main`（PATCH502，回读 main，owner 确认成功）；S5 tag `archive/codex-framework-20261031 → 8ca964fc`、`archive/ledger-base-20261103 → 1e709837`。S5.5 [PR #40 / run41902048351](main-transition-20261104/s5-guard-negative/README.md)：`reading-required-core` **required=true、红**，`mergeable=true` 且 `mergeable_state=blocked` / `mergeStateStatus=BLOCKED`；负例已恢复，PR 已关闭、临时分支已删除。两条原分支保留。

- 2026-11-05 — [中文语料禁则与标点测量](cjk-corpus-20261105/REPORT.md)：3本公版繁体书 紅樓夢/醒世恆言/唐詩 1652/1170/86 页，横排 37154/26510/1786 行（[RESULTS.csv](cjk-corpus-20261105/RESULTS.csv) 前3行有效，后3行 vertical=1 为测量假象、作废）。行尾违规 0/0/0；行首违规 4/0/0（紅樓夢 p83/203/1148 `：`、p1033 `，`）。有效 PAIR 11406 对（54+11352，唐詩 0 对无法测）挤压 0 对；U+2014 advance 47px=1.68em。最小清单5项：达标1、未达标3、无法测量1。

- 2026-11-05 — [15本×5位置抽样渲染](real-books-20261105/PAGES-SUMMARY.md)：[RESULTS-PAGES.csv](real-books-20261105/RESULTS-PAGES.csv) 75 次栅格化，75 成功/0 失败，未重试；最慢 Malcolm X PDF 50% 位置 page_index=139，53.741800ms；7 本同书最慢/最快 >10 倍（最大 76.588 倍）。计时只覆盖渲染 API；未跑 CI。

- 2026-11-05 — [草枕 CJK 禁则与标点挤压测量](real-books-20261105/CJK-LINEBREAK.md)：462 页、6857 正文列，指定避头尾字符集行首/行尾违规 0/0；74 组连续标点两字总占位÷单字均为 2.000（每标点 1.000），横排控制 74/74 一致，挤压 0 对；登记 [SDK-CJK-003](real-books-20261105/SDK-GAPS.md)，坐标见 [CJK-PUNCTUATION.csv](real-books-20261105/CJK-PUNCTUATION.csv)（148 条）。日文样本，不能替代中文验证。

## 已知在 main 上失败

以下失败在 main 上原本就存在，与 2a 系列 PR 无关，不要当作新问题。

- 2026-11-05 — `wp13-windows.yml` [run 42071165411](https://github.com/NoGod3524/EXReader/actions/runs/42071165411)，main `f22a7649`：
  - **H8**（“Require H8 default bounded long-chapter and cross-part UI acceptance”）失败：`{"accepted": false, "checks": 2, "failures": ["ValueError: unchanged-SDK-tree/src"]}`。门禁要求 SDK 树与固定提交相同，而 main 的 `src/` 已变化。
  - **worker 检查**（“Preserve worker ownership, SQL-failure and reverse-verification gates”）失败：`fixed-note-cancel`、`fixed-note-update-cancel`、`rollback-sql-busy` 三项 `TimeoutError: Expected host transition did not complete`；汇总 `candidate_passed 8`、`baseline_rejected 11`。
  - 同一 run 的 UI 验收三个 phase 通过（158/158，失败 0），自检 26 项通过。

## 已知问题

- 2026-11-05 — **MinGW 链接缺 UIA 库**：用 MinGW 构建 `examples/` 的 reader 时缺 `UiaRaiseAutomationEvent` 等符号，开不开 `EXR_READER_WINDOWS_SHELL` 都一样。原因是 `apps/reader/desktop/windows_accessibility.inc` 用 MSVC 专用的 `#pragma comment(lib, ...)` 声明 `uiautomationcore`、`oleacc`、`oleaut32`、`usp10`，MinGW 不处理这个指令。MSVC 构建不受影响。暂不修；本地验证时在命令行补 `-luiautomationcore -loleacc -loleaut32 -lusp10 -lole32 -luuid`。
- 2026-11-05 — **本机 MinGW 的 phase 失败 2 个**：phase-a 第 115 步、phase-b 第 5 步，CI（MSVC）上未复现。见 [issue #45](https://github.com/NoGod3524/EXReader/issues/45)，根因未查明。
