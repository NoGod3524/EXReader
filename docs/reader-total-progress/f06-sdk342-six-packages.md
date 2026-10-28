# F06: same-source six development packages

Coordinator scope review, 2026-10-28. This document proposes one fixed-catalog
outcome; it becomes counted only when the fixed 108 audit authenticates all
referenced evidence. It does not change the last accepted 81/108 snapshot by itself.

[Run 40678657371, attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/40678657371)
completed all 12 jobs on source
`8f8acf3234cba747165f001c0c96efe1b911e6ad`.
The [pinned handoff](https://github.com/NoGod3524/EXReader/blob/f623a07f9034cb70e3429ecb235a52009ea2acc3/docs/validation/sdk342-six-platform-handoff-40678657371.md)
records the exact six packages, actual program hashes, configuration and entry
report hashes and platform limitations.

The audit's narrowly pinned adapter independently downloads the original F06
summary (12812316729, 2,793 bytes,
`89cda12bf715d4e8227ecc60b118a8c959452a6e51b51bf4897dddb0cf12a039`)
and aggregate (12812487269, 1,239 bytes,
`123f4e5617268a7f50ce01bd8fc97e02cd3024a5a4a663789c458813fb0a76af`).
It then authenticates all six original outer ZIPs against pinned GitHub
ID/bytes/digest and source/run/attempt, rereads each package manifest and inner
archive, hashes the actual entry program, and checks the original configuration
and entry reports. Android installed APK identity, both Apple simulator installed
executable identities and launches, and the additional extracted macOS launch
are bound to those program hashes. Nothing is rebuilt or launched by this audit.

All six manifests and producers must identify SDK 3.42.0 and this one source.
The original failed predecessor 40676455610 remains failed and supplies no credit.

## Exact fixed-item scope

Only **F06** is proposed: six packages from one source, actual extraction/install
and program identity. Windows/Linux are development ZIPs; macOS is an ad-hoc
development application; Android is API34 x86_64 emulator/debug APK; iPhone and
iPad are separately installed arm64 simulator applications.

This does not grant F01 complete behavioral regression, F07 single provider and
private-entry dependency acceptance, F09 screen-reader coverage, F11 physical
device/signing/deployment, F12 full upgrade acceptance or a release. Independent
relay and Apple large-type successes do not add duplicate host points.
