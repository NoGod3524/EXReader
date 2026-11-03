# F03 SDK example verification — 2026-11-03

## Scope and stopping rule

The task holder changed the scope in this conversation to: “同一份 SDK 源码在 GTK + Windows 两个示例上正确接收组织数据”. This replaces the earlier six-host acceptance objective for this work.

- GTK and Windows must build the same SDK source and actually receive organization data in native examples.
- macOS, iPhone and iPad compile/package only. No Apple acceptance runs, XCTest execution or simulator launches.
- Windows uses [the SDK342 builder](../../tests/windows_sdk342/build.py) with `--organization-only`, rather than the C09 frozen builder. The three formerly frozen production blobs are unlocked; their current Git IDs are recorded, not compared against the historical freeze.
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
- Run: `41694251471`, attempt 1; [per-job and per-checkpoint results](round-1-items.json).
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

| Artifact | ID | Bytes | ZIP SHA-256 | 过期日期（UTC） |
| --- | --- | --- | --- | --- |
| GTK | 13261840048 | 23504349 | `a0a83d893d3d3a989f6b4c8140affd1488ea9e868cd883173afa78471a62a163` | 2027-02-01 |
| Windows | 13261900834 | 36084253 | `1482558adf35c4843ad2ced65098333ed6b90716c6808817057156bc0c34a5ef` | 2027-02-01 |
| Audit result | 13261530995 | 1261 | `e3cb5f5f435026368892cac90b34e9d3c3218c8b494c992f1bcad957c36cd15b` | 2027-02-01 |
| macOS build-only | 13258946647 | 2970 | `1859797869448050c5a2068ccbf2cd8856db3c1cd0b3f95abea6e6a5868c09c1` | 2027-02-01 |
| iPhone build-only | 13260756424 | 2940 | `381e059049e0f1ce729b420695e3340715165a3a0be960d80eb6025e26791004` | 2027-02-01 |
| iPad build-only | 13260396683 | 2928 | `d144f5461c1eef11dacd3071a936b5c6d1eb07a19c4b15379071a5ebacb52c6c` | 2027-02-01 |

Expiration is 90 days after run creation (`2026-11-03T18:29:08Z`), giving `2027-02-01T18:29:08Z`; all six GitHub API `expires_at` values confirm this. See [archive-manifest.json](archive-manifest.json).

artifact 失效后本目录仅保留身份与哈希，不保留原件。

This retention statement applies to artifacts not copied into the repository. The decisive small files listed below remain available here after expiry; the complete GTK and Windows archives and Apple build artifacts are not copied here.

The audit authenticated both producer archives using the GitHub artifact API, source/run/attempt and archive byte count/digest. GTK, Windows and audit ZIPs were independently downloaded and their bytes/digests verified before extracting the small files below. Complete databases and packages remain in the expiring artifacts.

## Repository-retained small evidence

This update adds 40 files (under 1 MB total for this directory):

- [audit-result.zip](audit-result.zip): the exact 1261-byte audit artifact; [audit-result.json](audit-result.json): its exact 2820-byte JSON member. The existing [round-1-result.json](round-1-result.json) is the formatted equivalent.
- [round-1-items.json](round-1-items.json): six job results, original step conclusions and twelve checkpoint results with relative references.
- [receipts/gtk/](receipts/gtk/) and [receipts/windows/](receipts/windows/): twelve original `projection.json` receipts and twelve original `requests.json` logs. Each phase records native receive, process restart and the full organization snapshot; each request log records authenticated revision downloads.
- [screenshots/gtk/](screenshots/gtk/): twelve original PNGs, one after receive and one after restart for each of the six phases. These show the native windows; the receipts and logs establish the per-phase data checks.
- [archive-manifest.json](archive-manifest.json): artifact identity, expiry timestamps, exact ZIP-member origins and SHA-256/byte counts for the 38 copied files.

All twelve GTK/Windows receipt snapshots were compared again during archival and match phase by phase. No CI was run for this archival update.

## Disposition

The revised SDK/GTK/Windows scope is accepted on round 1. Apple results are build-only. Catalog state and historical formal counts remain unchanged. No six-host acceptance is claimed; no additional acceptance round is planned.
