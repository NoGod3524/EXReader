# F03 retained original-artifact diagnostic
Authorization: user 2026-11-02T00:03:13Z approved one Ubuntu read-only diagnostic at most 10 minutes, fixed original 234.8MB artifact only, no build/emulator/test replay.
Parent seal 12b981608c699f29a2b377eba978c89fb45de271. Production tested source ce45497953e4f54cc253842a153f72f9f00a28bb remains unchanged.
Fixed producer run41360729084 attempt1; fixed artifact13104954654, 234819553 bytes, SHA256 09d290caa818a4679587df4f117d26fc4be6182bf6c877295b49497de3a4904b.
Purpose: identify the earliest original walkthrough failed/skipped item and distinguish it from downstream strict-gate cascade. Original Organization 8 and new recovery12 pass; original overall failure remains.
Only Actions downloads/verifies/opens ZIP. Standard-library parser rejects traversal, duplicate paths, symlinks; selects only JSON/TXT/LOG under original android-host/evidence plus exact retained/strict summary paths, maximum24MiB per file and80MiB total. No payload execution, fixture mutation, build, emulator, tests or acceptance rerun. A host-changing redirect removes Authorization.
Raw selected text is preserved with hashes; missing evidence fails explicitly. Diagnostic metadata keeps producer source/run/artifact separate from diagnostic source/run. Original results/catalog untouched.
Budget 0/1 at preparation; independent fixed-tree review precedes one workflow_dispatch. No retry. A successful extraction is not product acceptance.

Review hardening: also pin producer job125010333139 and exact artifact name, reject encrypted/special/noncanonical/normalized-duplicate paths, preserve missing/parse errors in result before failing, and restrict printed findings to bounded redacted test identifiers/status/errors. Raw selected evidence stays unchanged.

## Fixed-artifact diagnostic result
Diagnostic run https://github.com/NoGod3524/EXReader/actions/runs/41365671003 attempt1, source d03b51f6c330076ef632ce7f5684469e529be809, job125025210452: SUCCESS at 2026-11-02T00:10:31Z. Budget1/1 consumed; no rebuild, emulator or test execution. Original producer41360729084A1 remains FAILURE.
Original archive identity and SHA256 were verified. Selected original text had no missing requirements or inspection parse errors.
The original walkthrough summary is passed44/failed1/skipped0. Its single failing case is too_large, "AssertionError: limit status missing", corroborated by original instrumentation lines14/20/31 and original logcat at23:26:22.402Z. Exact case path android-host/evidence/device/cases/41-too_large.json, 364 bytes, SHA256 5e88cf6a381dfde31eeb4f56ebf831081995c0f6d77d229303022d38903a25aa. Device validation SHA256 8ba19205bce4a01635fadddc04966ee3c6726a799105b748c24a693be8b4cd55. Walkthrough instrumentation SHA256 6993b1fcb1220b200024de7bcd0e15eae0ae9e91f45031864785f6ac19115564.
This locates the failing assertion, not its root cause. Downstream 48/20 strict-gate and shelf acceptance failures must not be interpreted as independent bootstrap regression failures. Organization8 and recovery12 passing evidence remains bounded; fullF03 acceptance unchanged.
Diagnostic artifact13106594372, f03-retained-evidence-41365671003-1, 780930 bytes, SHA256 53ba417b815d9cb4a78ebcb093ba6d963f4e75011291954a6339f66578ba8b5b; contains selected raw text plus its manifest and diagnostic result. No ZIP was downloaded or parsed outside Actions.
Next authorized action is static inspection of the exact too_large assertion and production status path only. Any new production repair or test execution requires its own scope and budget.
