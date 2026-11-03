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

Round 1: prepared; not dispatched at this record's initial commit. Its exact source and run ID will be recorded after dispatch.
