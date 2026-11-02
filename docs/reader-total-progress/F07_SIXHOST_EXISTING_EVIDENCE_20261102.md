# F07 existing six-host evidence audit — 2026-11-02

## Authorized scope
User approved package B at 15:51:27 UTC (Sentinel_c7991d0d383c8191bd0bd674b18cb295).
Branch audit/f07-sixhost-existing-evidence-20261102; base ec11cf862ca3b44483d7e8c4726ae748ab438337.
Exactly three new files; one commit/push; one Ubuntu job <=10 minutes. No retry, rebuild, relink, payload execution, product/SDK/old acceptance changes.
Producer run41306566948 attempt1; eleven fixed artifacts,219686970 bytes. Locks embedded from previously retrieved API cache.
Related successful job IDs establish run/target context; artifact API itself binds artifact to run/source, not an unexposed exact upload-step job relation.

## Observational contract
Authenticate source/run/attempt/success, related successful jobs, artifact name/ID/size/SHA256; safe archive member inventory and bounded text inspection.
Only program.bin hashes, identity/receipt/report JSON, and existing link/module text are read. No payload execution or filesystem extraction.
Per archive <=20000 members, <=256MiB/member, <=2GiB declared total. Per text <=8MiB, all selected text <=64MiB; deadline540s/job10min.
Six parser-safety controls run only in Actions; not new product controls or replacements for old controls.
Missing/skipped/undecodable files are explicit gaps, not proof no evidence exists elsewhere.
Apple build contains SDK/raw products with program=None; final hosts come from mac/iPhone/iPad peer artifacts. Android explicitly packages APK/testAPK/program/receipt without standalone link MAP. Windows/GTK packages and Apple raw-products may contain links; inspect instead of rebuilding.
Neither archive success nor audit accepted=false decides product acceptance. Final F07 still requires six-target actual-provider and module-private-entry dependency evidence mapping.
SDK8357 historical byte identity is not substituted for final host ec11.

## Retained history and results
Windows24b85 original audit41357347494 verified112 entries/12 controls/80 SQLite MAP symbols uniquely SDK-bound, seal11c395d6fc7c5e5764377d801ea71f10ec05f4ba; not rerun or automatically transferred.
Legacy Linux consumer archive is excluded; it cannot substitute for GTK final host.
The only authorized audit retains summary.json plus per-artifact JSON inventory/text, including on failure. Bounded JSON observations are also in plain job logs. Final run/artifact identity is reported without a second source commit or CI retry.

## Preflight scope and output safety
Consumer HEAD equals GITHUB_SHA, descends from ec11, and adds exactly three authorized paths; dedicated marker and attempt1 gate. Consumer identity is separate from historical producer. ZIP rejects control/NUL, canonical aliases, nonregular types and directory-mode mismatch. Stdout exposes only bounded approved identity scalars and SQLite identifiers, not arbitrary report strings. Full authorized observations remain in evidence artifact.
