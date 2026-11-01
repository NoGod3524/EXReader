# F07 Windows actual provider evidence ? one bounded collection
User approval Sentinel_fa1a930de67881919a66a6651809e144 at 2026-11-01 13:28:43 UTC authorizes these four new exclusive files, branch dot/f07-windows-provider-20261101, commits/push and one windows-2022 job capped at 15 runner-min. No automatic retry. Base ec11cf862ca3b44483d7e8c4726ae748ab438337; frozen SDK 8357eafa28423a7ab93ba08b823af80f01ad1505 (3.42.0). F07 owns these files; F05, F03, production, SDK and original recipes/verifiers remain unchanged.

Paths:
- tests/reader_f07_windows_provider_20261101/collect.py
- tests/reader_f07_windows_provider_20261101/contract.json
- .github/workflows/dot-f07-windows-provider-20261101.yml
- docs/reader-total-progress/DOT_F07_WINDOWS_PROVIDER_20261101.md

The collector performs the original Windows SDK 3.42 build after the existing public OPDS hash-only dependency installation. Only an in-memory host_build.run wrapper adds /VERBOSE:LIB and Ninja -d keeprsp, retains full output and command/cwd identity, and leaves original source files untouched. It records actual build and installed SDK archive paths, bytes and SHA256, reports exact byte identity, and correlates complete original Searching/Loaded contexts with the actual installed SDK or product archive. It preserves host/package identity, MAP, response files, cache/rules, imports and library member/symbol records.

The evidence directory contains only explicit generated logs/metadata and selected native build artifacts; its file inventory excludes only the manifest itself. Artifact upload includes hidden files to preserve that exact closure. The build and every syntax check run only in GitHub Actions; no ZIP is downloaded or executed locally. No private runtime entry, modified SDK, weakened old test, prior-negative reclassification, system setting change, new UI run or shared budget is introduced.

Historical failure remains: run41251856370 authenticated the complete old retained log, but found no matching provider evidence; old audit remained rejected. That diagnostic used a historical source/SDK and is not rewritten by this fresh collection.

Budget basis: run41295456077/A1 Windows seed job124815265992 took 5m05s, with actual same-source build4m07s. This collection is estimated6?10min at medium confidence, bounded15min once. Additional logs/checks may fail or exhaust the budget; no retry follows without approval.

At preparation: not run. A reviewer must inspect the actual four-file tree before the sole same-tree trigger. Diagnostic success collects evidence only: F07_accepted=false, formal count unchanged, host_runtime_provider_observed=false. Full F07 acceptance still needs original clause review including auxiliary consumers, installed headers, public dependencies, packaging and preserved negative controls. Any later certification/integration has its own scope and budget.

Independent preparation review: collection reports missing, unknown or multiple Loaded identities, archive mismatch, imports and response-file presence as observations, preserving every original byte. These are not new certification gates. Only fixed known output paths are read; unknown log paths are never followed. UTF-8 observation decoding may use replacement while the original log bytes/hash remain intact. Only the top-level manifest excludes itself from its own inventory.
