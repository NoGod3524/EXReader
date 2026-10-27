# D25 handoff — current-source nine-format compatibility

## Identity and scope
- Branch: `codex/dot-d25-real-formats`
- Base: `2f215f5793a7344d22db350276ba9f8a07abe86f`
- Tested full source: `3f9cf32d9860e4c97a790899ae45b1e2da240030`
- [Run 40447164094, attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/40447164094), push-triggered, completed SUCCESS 2026-10-27 04:07:35 UTC.
- Windows job 122001073349; Linux job 122001073489; strict job 122003622987: all success.
- This handoff is a documentation-only descendant, not a separately tested source.

## Raw outcomes
| Panel | Windows | Linux | Failed IDs |
|---|---:|---:|---|
| Original F5 v1 consumer and manifest | 15/18 | 17/18 | Windows: fb2-breter, fb2-portraits, rtf-crowley-policy. Linux: rtf-crowley-policy |
| Existing UTF-8 consumer adapter, original v1 manifest | 17/18 | 17/18 | rtf-crowley-policy |
| Existing separately declared v2 | 18/18 | 18/18 | None |

Both current-source native CTest invocations returned 0. The entry adapter checks returned 0.
No additional SDK defect was established by this fixed sample set.
The current candidate already contains the exact reviewed RTF/CBZ fixes, so no SDK mutation or duplicate patch was made.

The original failures remain failures in raw per-file process JSON and summaries. The Windows FB2 failure is demonstrated at the consumer entry encoding boundary by the original/UTF-8 pair; the SDK and input bytes are identical. The Crowley v1 query mismatch remains in both original/UTF-8 panels. Its already-delivered v2 query correction is independently labelled, not silently applied to v1.

## Original artifacts (30-day retention)
| Platform | Artifact ID | ZIP SHA-256 | Bytes |
|---|---|---|---:|
| Windows | 12709490499 | 50f3cd89329c153331c03c79fed69f0ffe5857f45c170eff99d858436547e184 | 341796397 |
| Linux | 12709330932 | d8aa67ebd0341733d1147e628d2563c3482529a7cf1333feda3b61adb292aa61 | 330179693 |
| Strict | 12709435849 | a61d4c1c37c9756ceca32af4d741d440a146defb7393051403a23ba0c617b204 | 388 |

Artifacts retain current SDK build/install programs, native JUnit/logs, exact materialized dependency source identities, corpus bytes/licence snapshots, raw per-file outputs for all three panels, and summaries. Strict downloaded both same-run producer artifacts in Actions; its log records matching ZIP digests and checks source/run/attempt, Windows/Linux identity, all original input hashes and both manifest hashes. No artifacts were downloaded or parsed in the Dot workspace.

## Changed files and integration
1. `.github/workflows/reader-d25-real-formats.yml`
2. `tests/reader_d25_real_formats/run.py`
3. `docs/reader-d25-real-formats/README.md`
4. This handoff.

No host owner, SDK, ABI, budget, historical test or old failure file was changed. No conflict with D21–D24/D26 paths.
Coordinator may integrate the source commit above and this documentation descendant after review; no merge has been performed. Keep both exact Git dependencies reachable: F5 `278d63691a4c73e7aa932d71a40a5938c5427514` and adapter/v2 `8015c576822d5284dedfea17428ecf1a240befd0`.
The workflow supports manual dispatch on an integrated ref; the push filter is intentionally D25-only. The source guard intentionally refuses unrelated deltas from the fixed base; a future integration must explicitly review and version that guard rather than remove it. Run again on the actual new integration source; do not reuse this SHA's green result as its acceptance.

## Remaining boundaries
Original F5 v1 is NOT fully accepted. The pre-existing v2 is accepted on these 18 immutable samples only. 1710 historical completion remains 0/1710. Save fidelity, rendering fidelity, full-format compatibility, native GUI workflows and physical-device acceptance are not established by this task. D13's stopped experiment was not executed or rewritten.
