# Windows team24 integration

- Team branch: `codex/team24-windows`.
- Incremental seed: `310b4223a3d119555f1d04384af7f5b16b7b582f`.
- Workflow: `.github/workflows/reader-team24-windows.yml`.
- Preserved original C09 guard and frozen SDK, original acceptance suites, 1710 and CPU budgets.
- Initial allowance: two new runs/attempts. The cancellation and coordinator-authorized additional combined round are recorded separately below; no further run is authorized.

## Preserved failures

| Source | Run | Attempt | Result |
| --- | --- | --- | --- |
| `310b4223a3d119555f1d04384af7f5b16b7b582f` | 40274692199 | 1 | Failed: compact22 16 checks before minimum window geometry refusal; wave3 UI stopped on records location driver before back/forward. |
| `1bfd12e27e96549f7e60850bc1cce1f61a47e97b` | 40273584160 | 1 | Failed; retained without recycling its evidence. |
| `e8ee47a2fef83b54d3f6da760c19f417abf1f75f` | 40246233974 | 1 | Failed; retained without recycling its evidence. |

## Integration

The existing Win32 host and five native More features remain. History capture runs after frame acceptance and before another save worker starts. Font lease completion similarly precedes the next SDK worker; a failed worker launch restores pending owner state. Original export rows retain stable book IDs after result replacement. Markdown replacement requires explicit confirmation. Sync displays unread queue/conflict values as unknown; opening the raw revision store must succeed for a full snapshot. Font commit uncertainty blocks further library mutations until restart.

The unchanged compact22 suite is a required gate. The Actions driver requests a supported desktop mode of at least 1280x800; unavailable geometry remains a failure. The packaged original 26 checks are retained. The exact delivery ZIP is unpacked in Actions, every payload file is checked against the package manifest, then its bundled EXE/font execute the original 26 and the five-feature native UI suite. No local builds, tests, syntax checks, fixtures, screenshots or artifact processing are used.

## Public capture dependency

The inherited private retained encoder declaration and wrapper were removed. The Windows history path now includes the installed candidate header and calls public `reader_rs_encode_capture_raw_candidate` with actual anchor version 2. The core-owned dependency is exactly `a911cd0e8405a362dae1bb489190de02c4c81d51`, admitted as three fixed Git blobs in the incremental guard. Its separate installed C/C++ acceptance passed at source `347165fe601f1bdb0cd3bb1da4c672f696195a4e`, run `40348964690`, attempt 1. This focused dependency acceptance is separate from the Windows combined run.

## Scope

Windows Actions native controls and screenshots do not establish physical-device usability or screen-reader verification. This is the Windows workstream of the six-platform reader, not whole-product completion.

## Team24 run ledger

| Added run | Source | Run / attempt | Outcome |
| --- | --- | --- | --- |
| Complete round 1 | `1ed34cbbf24b5923fe5705c7c7d6042fdbb1fea1` | [40276275043 / 1](https://github.com/NoGod3524/EXReader/actions/runs/40276275043) | Failed. Guard, native build, packaged original26, compact22 (22/22), raw owner suite/fresh and unpacked original26 passed. Unpacked native UI passed menu and actual highlight-location history back/forward, then failed because the save-dialog driver found no filename edit. Other five-feature checks were not reached. |
| Cancelled preflight | `6ccfce60c4a6d7f8e610e001db827e83834f5347` | [40277257970 / 1](https://github.com/NoGod3524/EXReader/actions/runs/40277257970) | Cancelled during SDK build when the coordinator requested preserving the next complete round for the public codec. Guard passed; no complete native acceptance. The always authentication job failed because no delivery package existed. This record is retained. The coordinator subsequently authorized one additional complete combined round after the public dependency passed. |

Round 1 identity was read from its own Actions authentication log, without downloading or parsing artifacts locally:

- Artifact: [c09-windows-wave3-40276275043-1](https://github.com/NoGod3524/EXReader/actions/runs/40276275043/artifacts/12629923603), 19,106,707 bytes; digest `sha256:a6ab4094a29aaca3c22bcb0919c4fbe5d3092d74d16a2835b18cc17bf720aee9`; expiry `2027-01-24T05:49:02Z`.
- Original inner delivery ZIP `EXReader-wave3-windows.zip`: 17,500,504 bytes; SHA-256 `78f7722ecae0681522517c9aef36f512ec23b2472cbeffd057587ae61c72181b`.
- Actual `EXReader/EXReader.exe`: SHA-256 `052fbba8c490acda0581e82c1c448a297ef10ae2d7643237f7e658b72aca1b7e`.
- Authentication `verified=true` binds identity only; the Windows acceptance remains failed.

The driver-only repair waits for an identified editable filename field instead of scanning the file dialog once immediately after its owner appears. It is included in the combined source `08e1edf7ee37770c7ce210ab85a2ed4a122045f2`, together with SQLite identity/version fail-closed validation and 16 native business checks. No original1710 or CPU-budget acceptance is inferred from these narrower native host checks.

## Final combined round

The coordinator-authorized combined run is [40350379758 / 1](https://github.com/NoGod3524/EXReader/actions/runs/40350379758), source `08e1edf7ee37770c7ce210ab85a2ed4a122045f2`: failed. The public dependency pinned guard, build, original26, compact22 (22), raw owner suite/fresh, ZIP payload identity and extracted original26 passed. Only native-menu and actual located-history UI checks passed; the save dialog exposed a modern Edit 1001 / ComboBox / FloatNotifySink instead of the old filename control IDs, so the remaining 14 UI checks were not reached. Exact observed structure is repaired in unverified source `683d5524575fd00b3e5e4d447e730fb3ba76fd75` with no automatic rerun.

Final original artifact: [12663945607](https://github.com/NoGod3524/EXReader/actions/runs/40350379758/artifacts/12663945607), 19,105,651 bytes, digest `sha256:c528306681a1f0fc6352b3b860501e8a39e6394b4970c1ea80e69b36d50cf9c6`, expires `2027-01-24T15:32:49Z`. Inner ZIP: 17,500,770 bytes, SHA-256 `8f245e154df69fc5218307bea76de214e1bcfe0ecb96f4c10a5bcc823be163f4`. Actual EXE SHA-256: `dc2671bf103abc22008110c9b1efb3ec3aa75582f0c30004d122ca100d549b3b`. Identity verified, acceptance failed. See `HANDOFF-RESULT-C09.md` for the Chinese handoff and remaining scope.
