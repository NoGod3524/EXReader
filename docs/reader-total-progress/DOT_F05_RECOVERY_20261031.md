# F05 native dot handoff — 2026-10-31 23:16 UTC / 19:16 America/New_York

Status: **not accepted; production capability blocker; 0 CI runs consumed**.
Formal catalog stays 96/108. This handoff is continuity evidence, not completion.

Preparation branch: dot/f05-client-recovery-20261031
Preparation baseline: 94fb236a4a2da87dfbaf4f1dd2a47885d615a230
Frozen SDK reference: 8357eafa28423a7ab93ba08b823af80f01ad1505
Current test-contract commit before this document:
272caf87711c2594e64be90c1d03b1612754e057

Added manifest.json, README.md and verify.py in
tests/product/f05_recovery_20261031/. These define six real-host scenarios and a
fail-closed receipt contract. No producer drivers or workflow have been installed.
The verifier is unexecuted, including syntax; all such execution remains Actions-only.
The contract never independently grants F05 acceptance.

## New finding
The fixed product scope requires explicit conflict UI and resolving revisions
with all observed competing parents. On the preparation baseline, metadata.cpp
lines 229/260/364 identifies multiple heads and refuses edit staging/preparation.
Windows/GTK metadata views refuse unresolved edits; Apple HostOrganization requires
the same OK status; Android OrganizationPanel rejects non-editable selections.
A test calling lower reader_command_apply_* directly is not actual host resolution.
An explicit conflict-review/resolve route is therefore a prerequisite, not something
a tests-only work package can silently add or skip.

## Existing evidence, not transferred acceptance
* Linux joint 41223341504 A1 b5e7fea87174f5e0baabfad97cf5cf7082f2d85e:
  cross6, migrationcuts56, 11 WebDAV process deaths, 18 negative controls.
  It uses a different composed SDK lineage; no production delta applied here.
* Android 41240919804 A1 98d2542f3d9849bbcb81f134c6327b59240043b3:
  20 host checks, 3 PIDs, 12 original controls and cold-cache recomputation.
  Its sender is not same-source Windows; not whole F05.
* Windows account driver on preparation base preserves 32 checks but explicitly
  plants conflicts into receiver storage and excludes receive/import cancellation.
* Existing resilience 21+20 suite excludes host UI projection/other hosts.

## Ownership and next action
Parent coordinates one explicit owner assignment for metadata product resolution
and native UI routing. F10 alone may receive sync.cpp production authorization;
this F05 branch does not touch it. Apple/UI external ownership is preserved.
F03 provides genuine UI-created revision/head/parent receipts; F05 owns protocol
recovery assertions. No SDK or old tests are changed.

After owner-delivered production capability exists, fix one final composed SHA,
implement the remaining fixture and four platform driver files in the approved
allowlist, independently review the complete source, then dispatch exactly one
Actions workflow. Approved hard cap265 runner-minutes; used0. No automatic reruns.
Do not spend that full run merely to rediscover this static capability blocker.

GitHub direct source/Git route was approved at23:08 UTC. No Desktop Commander
call, Codex task, local source execution, credential read, artifact ZIP operation,
default/shared branch push, PR, tag, or release occurred. InstaBox handshake is
not checked by this package.
