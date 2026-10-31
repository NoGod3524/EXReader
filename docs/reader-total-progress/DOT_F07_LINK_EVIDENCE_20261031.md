# F07 full retained link evidence — bounded diagnosis

User approval Sentinel_fc3b96714a2881919371f608d38907d2 (2026-10-31 23:13:25 UTC) authorizes exactly these four new files, exclusive branch dot/f07-link-evidence-20261031 and one Ubuntu 22.04 job capped at 15 minutes. No automatic retry. Base 7131426ba6a4a0ff7782e4cafd0ff908b9a88a9b. Prepared commits skip CI; one same-tree trigger commit will identify the actual verifier source.

Input: run41186261435/A1, Windows job124493687007, producer01ab528888f5c5be97e5824d69e2908e31e68e24; artifact13036129037,31654088 bytes,SHA256 c71801182be4188ad1fea84d2b5b2691e50735fbfa8763acbb7c1fe8d5efd9e4. Product044824f91ddae2ea49994350d308d079a69048ab and SDK7271829a829bfa6aaa47b73077c493f71af27ad3 remain historical inputs, not the frozen8357 six-platform source.

Only Actions downloads and parses the original ZIP. Original checker source remains byte-identical; its safe ZIP reader, full internal manifest/hash contract, original loaded-member parser and evaluator are reused without gate changes. All Searching/Loaded contexts in host-build.log are retained with original line numbers before SQLite filtering. MAP basename observations are not substituted for complete archive-path proof. Command/log hashes and original refusal are recorded. No downloaded executable or script is executed. No SDK/product build, new runtime observation, old-test edit or prior negative-control reclassification occurs.

A successful diagnosis means the fixed input and full log were authenticated and the original parser outcome was reproduced/classified. Zero matching evidence remains evidence_missing; a green diagnostic is not a provider certification. F07_accepted=false, audit_passed=false and formal count unchanged. Existing audit41188947889 remains failed; diagnostic41189550943 only proved its selected projection empty. Original full-log content is not assumed empty.

Exact new paths:
- tests/reader_f07_link_evidence_20261031/verify.py
- tests/reader_f07_link_evidence_20261031/source_lock.json
- .github/workflows/dot-f07-link-evidence-20261031.yml
- docs/reader-total-progress/DOT_F07_LINK_EVIDENCE_20261031.md

At preparation: not run. Further certification, six-platform integration or correction requires its own approved scope/budget.
