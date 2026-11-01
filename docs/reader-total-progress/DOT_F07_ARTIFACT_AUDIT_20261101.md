# F07 fixed original-artifact audit
Authorization: user Sentinel_485e3a27d608819194919d718aa56f25 at 2026-11-01 21:39:21 UTC approved the proposed one Actions artifact audit, maximum 5 minutes, without rebuilding or relinking the product. This does not reuse the consumed prior Windows 15-minute allowance.
Exclusive branch: dot/f07-artifact-audit-20261101.
Base: cf02a46e2756c917b4ee13f8d99d85ff8b40bfc2.
Only four new files: audit.py and contract.json under tests/reader_f07_artifact_audit_20261101, .github/workflows/dot-f07-artifact-audit-20261101.yml, and this document.
Fixed producer: NoGod3524/EXReader, run41312188612 attempt1, source24b85a76555593598a25f228b757f8b018e83c5c.
Fixed artifact:13085877416, f07-windows-provider-41312188612-1, 13597328B, SHA256 ebac63bf89f2df44abffcfb998920b00afdb1d81fe2c09cb0cbfbaaad88c8613.
The API, ZIP digest, safe member names, complete original manifest, every payload hash and producer source/run/attempt are authenticated before observations. ZIP download and parsing occur only inside Actions. No archive payload is executed. Original source, SDK, tests, manifests, historical failures and prior diagnostic result remain unchanged.
Actual producer collection paths confirmed from the frozen collector: manifest.json, summary.json, commands.json, host/windows-host.map, host-build/CMakeFiles/EXReaderWave3.rsp, logs/host-build.log, archives/sdk-build.lib, archives/sdk-installed.lib, archives/product-installed.lib, host/EXReaderWave3.exe, host/EXReader.exe, logs/host-imports.log.
The original contract does not prescribe a public SQLite symbol list. This audit therefore reports every actual public sqlite3_ MAP row instead of inventing a new acceptance threshold. It correlates final MAP archive/member labels with the actual response-file library paths, normalizes against the producer-recorded build directory, and binds only exact recorded SDK/product archive paths and fixed hashes. Unknown, missing, duplicate-basename and multiple-role observations remain explicit.
The parser controls include a true binding, comment/missing/foreign/ambiguous/non-SQLite-member/bare-object negatives, ZIP traversal and duplicate-entry rejection. They are parser controls, never substitute product evidence.
Microsoft documents /VERBOSE:LIB library/object/symbol resolution and /MAP public symbol/object information; it does not require a literal Loaded label:
https://learn.microsoft.com/en-us/cpp/build/reference/verbose-print-progress-messages?view=msvc-170
https://learn.microsoft.com/en-us/cpp/build/reference/map-generate-mapfile?view=msvc-170
https://learn.microsoft.com/en-us/cpp/build/reference/at-specify-a-linker-response-file?view=msvc-170
No DLL import is not a runtime LoadLibrary exclusion. MAP observation is static-link evidence, not a runtime module trace. F07_accepted=false and formal_count_changed=false throughout this diagnostic. The original full F07 clauses still require separate evidence review.
Budget: one ubuntu-24.04 job, timeout5min, script monotonic240s (no automatic network retries), leaves job allowance for artifact upload. It is a fixed 13.6MB existing-artifact text/hash audit, not another build. Failure, insufficient MAP identity or deadline exhaustion does not authorize a subsequent build or rerun.
Preparation status: not dispatched; budget0/1. Candidate will be independently read before a single same-tree trigger. Outcome and run/artifact identities will be appended after that run. Current formal project count98/108 is unchanged.

Independent preparation review confirms producer copy() paths are retained in manifest.files by seal(). Fixed producer job124864692357 is additionally checked via API. MAP absolute archive paths must exactly match the unique response-file path; an unrelated absolute path with the same basename is rejected. The original 11 parser controls remain, with one extra foreign-absolute-MAP negative (12 total). No controls have run outside Actions.
