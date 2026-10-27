# D21 Apple explicit receive — final Actions evidence

## Identity and result

- Tested product/test source: `0b464821b864ef3c7e8f18ed4a8aecc31b00ee1e`.
- Base: `2f215f5793a7344d22db350276ba9f8a07abe86f`.
- Branch: `codex/dot-d21-apple-receive`.
- [Actions run 40473702681](https://github.com/NoGod3524/EXReader/actions/runs/40473702681), attempt **1**, `completed / success`.
- All nine jobs succeeded. Original same-run authentication and D21 raw ZIP authentication both report `accepted: true`, matching source/run/attempt, actual native binaries, source plist, original resource/test identities, SDK family and artifact digests.
- This document is a subsequent **documentation-only** commit. Its commit is not the tested source above, and no CI pass is attributed to that documentation commit. No product/test change follows the tested source.

## Delivered product

Reuses existing public account session/WebDAV v1, raw revision projection, product catalog, private immutable import copy, and SDK import/mapping. No separate sync protocol or SDK candidate is introduced. Explicit sync projects safe remote books to the existing shelf. Explicit cloud-book open validates/caches the original, imports/maps through the existing owner, and opens reading. Existing local metadata and reading position are preserved; duplicate, conflict, deleted history, missing/corrupt originals, interruptions and cancellations do not silently select a winner or replace local metadata.

Verified local originals reopen without authentication. Invalid cache is retained in private quarantine before a verified replacement. Cancellation immediately publishes a clear state, does not release the owner early, refreshes committed shelf changes, and rejects stale/closed-account callbacks.

## Native verification

| Job | ID | Actual scope | Result |
|---|---:|---|---|
| installed macOS SDK/products | 122086660771 | Frozen SDK and exact installed module family; original terminal consumer | success |
| installed simulator SDK/products | 122086661314 | Same source, original frozen dependency identity | success |
| receive macOS | 122088613327 | Real native macOS host, HTTPS, actual SDK owner | success |
| receive iPhone | 122088613198 | Actual native iPhone **simulator** app, HTTPS | success |
| receive iPad | 122088613356 | Actual native iPad **simulator** app, HTTPS | success |
| original macOS | 122088613207 | Unchanged 39 cases | 39/39 |
| original iPhone | 122088613994 | Unchanged 39 cases | 39/39 |
| original iPad | 122088613256 | Unchanged 39 cases | 39/39 |
| authenticate | 122120860894 | Original and D21 raw same-run ZIP identity | both accepted |

Each original 39-case set retains wave3 5, base 13, reading/navigation control 13, search 4 and theme 4: **117 unchanged original cases total**. Each receive job also runs the real model's ten deterministic main-queue publication assertions, native owner HTTPS tests and one end-to-end UI case. The publication assertions run as a native macOS helper; they are not misrepresented as ten iOS UI cases.

Receive coverage: remote existing book; no-cache first open; actual SDK import/read; old independent local book; duplicate and conflicting remote roots; wrong hash; corrupt local cache; truncated HTTPS; cancellation during delayed download; restored-source retry; app termination/restart with remote objects unavailable; verified nonzero reading position restored exactly. One continuous authenticated HTTPS fixture is used across seed, owner receive and UI. The fixture control modifies only its CI service and test app cache, not product UI or SDK identity.

## Raw artifacts (all from run 40473702681 / attempt 1)

| Artifact | ID | Raw ZIP SHA-256 |
|---|---:|---|
| receive macOS | 12720613058 | `67baf880863cc73e3c29bdd95752d0626d02ecc3f5a5318b2455ee6b6e0b0d0d` |
| receive iPhone | 12721070120 | `89826acd6c3fc07720473c6df6e82638c522fd532b1934344fb39efe1fd5d892` |
| receive iPad | 12721815487 | `25af4f78eb22820cbc2bcfb5aa3cdba7d3f50b7a55475b8900fdc89f57de12b3` |
| original macOS | 12720502517 | `3b87c6525cbd223d4a510a2e698bca8aa9d6463222675d275002dc6e0ca0aa38` |
| original iPhone | 12724705453 | `b3490cdaa487901aea8474acd029b2d36a6f22701b3ff571f9c274cb365a2467` |
| original iPad | 12722249515 | `7dba6dff261a104630cbbef781fcec342332ba7583a5cf000f959c840e190ebf` |
| receive authentication | 12723643342 | `df50358ce4953689d0e2b15d340bf41f6d15ed53d1e4f9b6f759030a4fa0dba8` |
| original authentication | 12724112510 | `eca8c1252a4beef3aa9fa6b014c1924a2486241ca9c9b49e978f14ba8e456bc1` |
| installed macOS | 12718903911 | `893cff838d4ad7fc2b1d5da4ef1874a3f8c3759b1bae38052a211ca462e37661` |
| installed simulator | 12719263851 | `fc2b3e74c0def2d4b074964e8053178d914bf0def56231ca629f27e06547e1f3` |

Receive ZIPs retain real application ZIP/binary identity, xcresult, native compilation/run logs, publication result, HTTPS request/control evidence and individual owner results. Artifact retrieval and parsing occurred only in Actions; this report reads connector job logs and their authenticated summaries.

## Paths and integration

Product changes: `examples/apple/HostAccount.swift` (verified original receiver), `HostCatalog.swift` (safe cloud shelf projection), `HostModel.swift` (receive/open owner and publication), `HostViews.swift` (**LibraryScreen only**). CI: `.github/workflows/reader-d21-apple-receive.yml`; independent tests: `tests/reader_d21_apple_receive/{ReceivePublicationReview.swift,ReceiveReview.swift,ReceiveUITests.swift,guard.py,run_receive.py,verify.py}`. Evidence: this file and `docs/handoffs/d21-receive-evidence.md`.

Ordered commits from the common base:

1. `d2a9bb78ed3afe8f75dd473d08481e1277fa614f`
2. `5fe9a9d7a23a1e70cbd0d4270b520f61f7523466`
3. `f9a2e5e7c2ecef9d8eb7ab5f08163d756782b1af`
4. `b649a9d90451d3df9c798618daa8d71f52a74140`
5. `e1b206bdefb10c05abdbb5cd2f191d4e6fcd9a71` — isolated cancellation product repair
6. `0b464821b864ef3c7e8f18ed4a8aecc31b00ee1e` — targeted publication verification

The coordinator can normally merge this task branch into a new authorized integration candidate or apply these ordered commits; no directory replacement. D24 shares `HostViews.swift` but owns HostRootView/ReaderScreen, whereas D21 edits only original-base LibraryScreen lines 322–454 (cloud row open/icon/identifier, receive status/cancel controls, shelf publication subscription). D21 does not touch `HostAccountViews.swift`; D24 does not touch the D21 account/model/catalog owner. Preserve both sets of hunks if Git reports a textual conflict. No D24 dependency is required by D21. Any combined candidate needs its own same-source Actions verification; neither task's standalone green proves the combined candidate.

No mainline merge, PR, tag, release, default-branch change or automatic install was performed.

## Remaining boundaries and retained failures

Physical iPhone/iPad devices, device signing/distribution and actual VoiceOver speech were not available or executed. These remain unverified, not passed by simulator evidence. There is no remaining failed gate in the executed scope.

The first three iterations' raw failure evidence and actual driver corrections remain documented in `d21-receive-evidence.md`; no old test, SDK identity or budget was loosened. Fourth source `b649a9d90451d3df9c798618daa8d71f52a74140`, run `40466429222`, attempt 1 subsequently passed all jobs and authentication, but is not mixed into final-source acceptance. The final run independently passed after the cancellation repair.
