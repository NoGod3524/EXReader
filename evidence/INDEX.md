# Evidence index

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

## 已知在 main 上失败

以下失败在 main 上原本就存在，与 2a 系列 PR 无关，不要当作新问题。

- 2026-11-05 — `wp13-windows.yml` [run 42071165411](https://github.com/NoGod3524/EXReader/actions/runs/42071165411)，main `f22a7649`：
  - **H8**（“Require H8 default bounded long-chapter and cross-part UI acceptance”）失败：`{"accepted": false, "checks": 2, "failures": ["ValueError: unchanged-SDK-tree/src"]}`。门禁要求 SDK 树与固定提交相同，而 main 的 `src/` 已变化。
  - **worker 检查**（“Preserve worker ownership, SQL-failure and reverse-verification gates”）失败：`fixed-note-cancel`、`fixed-note-update-cancel`、`rollback-sql-busy` 三项 `TimeoutError: Expected host transition did not complete`；汇总 `candidate_passed 8`、`baseline_rejected 11`。
  - 同一 run 的 UI 验收三个 phase 通过（158/158，失败 0），自检 26 项通过。

## 已知问题

- 2026-11-05 — **MinGW 链接缺 UIA 库**：用 MinGW 构建 `examples/` 的 reader 时缺 `UiaRaiseAutomationEvent` 等符号，开不开 `EXR_READER_WINDOWS_SHELL` 都一样。原因是 `apps/reader/desktop/windows_accessibility.inc` 用 MSVC 专用的 `#pragma comment(lib, ...)` 声明 `uiautomationcore`、`oleacc`、`oleaut32`、`usp10`，MinGW 不处理这个指令。MSVC 构建不受影响。暂不修；本地验证时在命令行补 `-luiautomationcore -loleacc -loleaut32 -lusp10 -lole32 -luuid`。
- 2026-11-05 — **本机 MinGW 的 phase 失败 2 个**：phase-a 第 115 步、phase-b 第 5 步，CI（MSVC）上未复现。见 [issue #45](https://github.com/NoGod3524/EXReader/issues/45)，根因未查明。
