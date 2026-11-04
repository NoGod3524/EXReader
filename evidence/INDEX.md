# Evidence index

- 2026-11-03 — [E1/E3 performance baseline policy](../docs/validation/PERF-BASELINE-POLICY.md): environment-bound raw-sample budgets, advisory until strict re-verification; hard expiry 2026-12-15 America/New_York; [tracking #32](https://github.com/NoGod3524/EXReader/issues/32). P evidence: [ci-packaging-20261103](ci-packaging-20261103/RESULT.md).

- E1/E3 deployment verification status: [SPLIT-STATUS.md](ci-packaging-20261103/SPLIT-STATUS.md). Required context changed; evaluate limitation accepted; static core branch/job checks complete, live verification deferred to the first real PR.

- 2026-11-03 — [Final gate probe and P self-defect repairs](final-gate-probe-20261103/README.md): native run41726208700 job conclusions/first errors, producer passed/advisory separation, and [533-binding content-identity remap](final-gate-probe-20261103/baseline-remap.json). Subsequent native/core results are recorded in the same directory; core runs only after native succeeds.

- 2026-11-03 — [P self-defect rerun](final-gate-probe-20261103/README.md#repair-verification-native-rerun-41732293021): native run41732293021 passes on f19788b7; one conditional core dispatch returns HTTP404, no core run created. No retry or default-branch change.

- 2026-11-03 — **Milestone: first end-to-end validated ledger/base native**, [run41732293021 and per-job conclusions](final-gate-probe-20261103/README.md#milestone-accepted-by-owner): seven native jobs + four hygiene checks pass on f19788b7, accepted by owner.

- 2026-11-03 — [One-time core PR probe #36](final-gate-probe-20261103/README.md#one-time-pr-core-probe-registered-failed-cleaned-up): Required native reading SDK core registered, run41774219995; protocol/native/profiles/platforms pass, corpus exact-version mismatch fails, final reading-required-core fails. PR closed without merge; temporary branch deleted.

- 2026-11-04 — [Corpus consumer version repair](corpus-version-20261104/README.md): unpin active corpus/OCR consumers; scan CMake package version literals; consumer downgrade negative exits 1 with file:line and source-version guidance.
