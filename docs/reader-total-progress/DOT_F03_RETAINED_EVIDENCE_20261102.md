# F03 retained original-artifact diagnostic
Authorization: user 2026-11-02T00:03:13Z approved one Ubuntu read-only diagnostic at most 10 minutes, fixed original 234.8MB artifact only, no build/emulator/test replay.
Parent seal 12b981608c699f29a2b377eba978c89fb45de271. Production tested source ce45497953e4f54cc253842a153f72f9f00a28bb remains unchanged.
Fixed producer run41360729084 attempt1; fixed artifact13104954654, 234819553 bytes, SHA256 09d290caa818a4679587df4f117d26fc4be6182bf6c877295b49497de3a4904b.
Purpose: identify the earliest original walkthrough failed/skipped item and distinguish it from downstream strict-gate cascade. Original Organization 8 and new recovery12 pass; original overall failure remains.
Only Actions downloads/verifies/opens ZIP. Standard-library parser rejects traversal, duplicate paths, symlinks; selects only JSON/TXT/LOG under original android-host/evidence plus exact retained/strict summary paths, maximum24MiB per file and80MiB total. No payload execution, fixture mutation, build, emulator, tests or acceptance rerun. A host-changing redirect removes Authorization.
Raw selected text is preserved with hashes; missing evidence fails explicitly. Diagnostic metadata keeps producer source/run/artifact separate from diagnostic source/run. Original results/catalog untouched.
Budget 0/1 at preparation; independent fixed-tree review precedes one workflow_dispatch. No retry. A successful extraction is not product acceptance.

Review hardening: also pin producer job125010333139 and exact artifact name, reject encrypted/special/noncanonical/normalized-duplicate paths, preserve missing/parse errors in result before failing, and restrict printed findings to bounded redacted test identifiers/status/errors. Raw selected evidence stays unchanged.
