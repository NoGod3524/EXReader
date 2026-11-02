# F08 frame identity diagnostic (2026-11-02)

This independent package classifies preserved observations; it is NOT the official
F08 association or a replacement acceptance protocol. The official F08 failure is
retained, and this package neither imports nor executes the official associate
function. It does not change SDK, product code, old tests, pixels, or thresholds.

## Authorization and scope

Base: 6f60057deaae4dc123209b974c08de6d246a2f70.
Branch: codex/f08-frame-identity-diagnostic-20261102.
Exactly seven new files, one workflow_dispatch Ubuntu job, <=10 minutes total;
zero APK builds, zero native samples, no automatic retry. The user approved this
specific package on 2026-11-02 at 07:42:17 UTC (message
Sentinel_5970c1d1fde481919bf90cb461d6a5dd). Runtime outcome must be reported
separately from static review; six controls have not run at candidate preparation.

## Inputs and limitations

INPUTS.json binds two immutable original byte streams to source
1c4eac3eb5e2da98d535585f80fc3aba437661bd and native-lap25002-20261102T055639Z/A1.
The native stream is the retained attempt-19 prefix, 284 callbacks, no footer.
The draw stream likewise is not a completed capture. No complete stream or
capture pass is inferred. The original evidence directories remain unchanged.

Original formal rejection combined duplicate native (PID, window, vsync) keys
and duplicate callback sequences into one error label. Read-only review found
sequence 1..284 unique, two shared-vsync groups (176/177 and 207/208), and draw 9
inside callback 177's DRAW interval but not 176's. This diagnostic preserves
every row and labels that observation, without removing the formal uniqueness
requirement or declaring F08 accepted.

## Six fixed control groups

1. Shared vsync, distinct sequence, unique containing interval: diagnostic
   unique_interval_candidate only; acceptance_override remains false.
2. Same sequence / identical records: reject.
3. Same sequence / conflicting records: reject.
4. Two containing intervals: reject.
5. Wrong owner, window, accept identity or generation: reject (subcases).
6. Invalid clocks/durations or dropped callbacks: reject (subcases).

No frame is deduplicated or filtered to obtain a successful result. Invalid
observations make classification_valid false. Generation comes from actual
accept/draw linkage, not an invented native FrameMetrics generation field.
No performance percentile, benchmark, or completion-time result is computed.

## Execution and stop conditions

The workflow runs only on this exact branch and only on manual dispatch.
Six control methods run first; if any fails, the classification step does not run.
The classifier verifies exact seven-file added scope relative to the fixed base,
input bytes, hashes, source/run identity, owner, and absent completion footer.
It writes classification.json; any invalid/ambiguous/unmatched observations
make the job fail. Reports are retained even on failure. Successful diagnostic
classification does not alter official_f08_result=unchanged_failure.

If input identity is wrong, any negative control is admitted, or the retained
observations remain ambiguous, stop without retries or a new sample. Any formal
protocol migration requires a separately defined and approved scope.
