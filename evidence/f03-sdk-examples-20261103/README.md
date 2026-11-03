# F03 SDK example verification — 2026-11-03

## Scope and stopping rule

The task holder changed the scope in this conversation to: “同一份 SDK 源码在 GTK + Windows 两个示例上正确接收组织数据”. This replaces the earlier six-host acceptance objective for this work.

- GTK and Windows must build the same SDK source and actually receive organization data in native examples.
- macOS, iPhone and iPad compile/package only. No Apple acceptance runs, XCTest execution or simulator launches.
- Windows uses `tests/windows_sdk342/build.py --organization-only`, rather than the C09 frozen builder. The three formerly frozen production blobs are unlocked; their current Git IDs are recorded, not compared against the historical freeze.
- At most two new rounds: `[F03-SDK-R1]` and, only if needed, `[F03-SDK-R2]`, attempt 1 each. No reruns. Stop after a passing round; after two failures record `known-issue` and stop.
- Progress and disposition live in `evidence/`. `docs/reader-total-progress/catalog.json` remains unchanged.

## Round contract

Each round checks out one exact commit on `codex/f03-six-host-20261103`. SDK 3.42.0 source identities cover `src`, `include`, `cmake`, `CMakeLists.txt` and `bindings`.

The GTK example authors nested shelves, tags, series and memberships through its real UI. Fresh GTK and Windows profiles receive authentic WebDAV revisions at six checkpoints: create, delete, restore, member-remove, member-restore and restart. Each receipt retains the actual product database, exact revision bodies, authenticated request trace, executable hash and process restart result. The audit checks all six organization tables against the native author, source/run/attempt identity, artifact digest and SDK source IDs.

The GTK original 27 organization checks remain in the GTK job. Apple build conclusions are reported separately and do not grant organization acceptance credit.

Per-round job timeout budget: GTK 60 + Windows 60 + Apple 3×25 + audit 10 = 205 runner-minutes maximum; two rounds at most 410 runner-minutes. Windows runs after GTK; the audit preserves failures. No automatic retries.

## Starting point

Integration starting commit: `232341db418ecd47c3b98216a3802c5ef565faf1`. Earlier six-host runs remain historical evidence and are not counted as new SDK rounds. Obsolete Apple diagnostics `41689770177` and `41691780081` are completed/cancelled. The earlier six-host workflow no longer has a push trigger.

## Round 1

- Source: `c583ebe7dadf971eed680fea60ab850bbb7a41ce`.
- Run: https://github.com/NoGod3524/EXReader/actions/runs/41694251471, attempt 1.
- Status: accepted. The exact archived audit result is [round-1-result.json](round-1-result.json): `accepted=true`, `problems=[]`.
- New-scope rounds consumed: **1 of 2**. Verification stopped after success; round 2 was not dispatched.

| Job | ID | Result |
| --- | --- | --- |
| GTK actual organization receive | 126120492531 | success |
| Windows actual organization receive, unlocked SDK342 builder | 126124038150 | success |
| macOS build-only | 126120491776 | success |
| iPhone build-only | 126120492125 | success |
| iPad build-only | 126120492259 | success |
| Artifact/source/database audit | 126127326225 | success |

Both examples have twelve accepted observations in total: six checkpoints each. Their complete organization snapshots, including retained revision bodies, have identical SHA-256 at every checkpoint. The audit read each archived actual product database and required it to match its receipt. Each checkpoint includes a real authenticated revision download and an actual process restart. GTK's original 27 organization UI checks also passed.

Artifact identities:

| Artifact | ID | Bytes | ZIP SHA-256 |
| --- | --- | --- | --- |
| GTK | 13261840048 | 23504349 | `a0a83d893d3d3a989f6b4c8140affd1488ea9e868cd883173afa78471a62a163` |
| Windows | 13261900834 | 36084253 | `1482558adf35c4843ad2ced65098333ed6b90716c6808817057156bc0c34a5ef` |
| Audit result | 13261530995 | 1261 | `e3cb5f5f435026368892cac90b34e9d3c3218c8b494c992f1bcad957c36cd15b` |

The audit authenticated both producer archives using the GitHub artifact API, source/run/attempt and archive byte count/digest. The archived result ZIP was independently downloaded and its bytes/digest verified before copying the result into this directory. The GTK ZIP was also independently downloaded and its six receipts inspected. Complete logs, screenshots, retained databases and packages remain attached to the run.

## Disposition

The revised SDK/GTK/Windows scope is accepted on round 1. Apple results are build-only. Catalog state and historical formal counts remain unchanged. No six-host acceptance is claimed; no additional acceptance round is planned.
