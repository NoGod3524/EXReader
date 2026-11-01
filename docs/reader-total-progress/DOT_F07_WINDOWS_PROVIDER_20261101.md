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

## Result sealed from the one approved run, 2026-11-01

- Actual source: 24b85a76555593598a25f228b757f8b018e83c5c; tree 688e8813c9974481c977f6b4340547c9a0d879ef, byte-identical to independently reviewed preparation 91752e86eda4072674b46603abb336d280ca4d7a.
- [Run 41312188612/A1](https://github.com/NoGod3524/EXReader/actions/runs/41312188612), [job 124864692357](https://github.com/NoGod3524/EXReader/actions/runs/41312188612/job/124864692357): success, 13:37:51 to 13:42:24 UTC, 4m33s. The Windows 15 single-run allowance is consumed 1/1; no retry or additional CI was started.
- Original job-text summary: diagnostic_completed=true, errors=[], F07_accepted=false, host_runtime_provider_observed=false. Classification is **missing_sqlite_loaded_rows**, not provider acceptance.
- SDK build archive: D:\a\EXReader\EXReader\build\windows-sdk342\sdk-build\exr_sqlite.lib; installed archive: D:\a\EXReader\EXReader\build\windows-sdk342\sdk\lib\exreader\exr_vendor_exr_sqlite.lib. Both 3,242,564 bytes, SHA256 f2e4dc21a4c9f40bb6f1fe4d35cbc513e852377ffc652929fcc52719e240792e; complete bytes equal.
- Installed product archive: D:\a\EXReader\EXReader\build\windows-sdk342\product\lib\reader_catalog_sqlite.lib; 3,242,632 bytes, SHA256 b33969efbbf25ea5de34d85d55eeedd4cce005cc84d03d642c0e629436d9d87a.
- Built and packaged host bytes equal. The collected imports contain no matching system SQLite DLL import. One retained actual response file: CMakeFiles\EXReaderWave3.rsp; the rules also declare response-file use.
- The original host-build.log was observed as strict UTF-8, SHA256 484bc42c009f6eb3ac34e2144b1f15b0b9fea25a8ed1bb0b42faeb78c2e3144b. There are 686 retained Searching blocks, including 18 SQLite archive search blocks. The collector's complete all_loaded_lines list and sqlite_loaded list are empty. All 18 SQLite blocks were additionally read from the original job-text summary and contain only the Searching line; no ANSI escapes appear in the retained contexts. This establishes missing matching Loaded evidence in this observation, not a duplicate-provider defect or a proven parser/toolchain cause.
- [Artifact 13085877416](https://github.com/NoGod3524/EXReader/actions/runs/41312188612/artifacts/13085877416): f07-windows-provider-41312188612-1, 13,597,328 bytes, SHA256 ebac63bf89f2df44abffcfb998920b00afdb1d81fe2c09cb0cbfbaaad88c8613; API reports not expired, expiration 2026-12-01T13:42:19Z. Producer/source/run identity was checked against the API. The archive was not downloaded or parsed outside Actions; no later independent ZIP-content authentication is claimed.
- F12 independently checked the final four-new-file tree before launch, and the run/job/API/summary after completion. SDK/F05/F03/product/original recipe/verifier files remain unchanged.
- Next gap: actual loaded archive/member binding is still absent. Preserve this result and the old failures. Review existing raw MAP/rsp/log evidence before proposing any further diagnostic; a new build, artifact-processing CI, parser change or certification needs its own explicit scope/budget. Formal count is unchanged by this run.
