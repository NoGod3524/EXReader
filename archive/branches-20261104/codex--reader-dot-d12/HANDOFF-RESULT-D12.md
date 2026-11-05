# D12 — genuine Mac wire receive and Windows record navigation

## Result boundary

**Product acceptance remains false.** This package changes only new D12 tests, workflow and evidence documents. It does not repair or reclassify the target, SDK, old tests, or prior failures. Iteration 2, not the final failed harness, exercised all 11 original record IDs in two independent actual native GUI processes. Successful independent SDK READ/FOUND is not substituted for the GUI.

## Immutable identities

- Harness base: `0889f7d1e9a537c6c1b05456547e016b26e1cd85`.
- Final attempted harness: `a3a53c0fb2e83afdf49f7332e82e9b5d97e513f6`; tree `7c4b2198f3eafae67d08f3aa0aa135e21d7f7fbe`.
- Last complete runtime/evidence harness: `db6c726c2f5bcee03d697e90b4865e7874e6b2a0` (iteration 2); do not attribute its results to iteration 3.
- Actual Windows target: `9321de84eb9c8d3d57cafbeaa8b0a28fe2a26a08`, original run `40221234665` / attempt `1` / job `121253049387`.
- Approved SDK source: `edddc463c06ed5731195cdb8f06b2df6dff7699e`; actual installed 3.41.0 raw candidate, not frozen 3.40.0.
- Actual Mac source: `15dab6b2270dc296ed6239db67ced2e22d255e65`, run `40196978163` / attempt `1`, original jobs `121179826434`, `121186031984`.
- Feature branch: `codex/reader-dot-d12`. Final docs-only seal is the commit containing this completed page, after the tested harness; it is not another tested implementation.

### Original ZIPs reauthenticated in Actions

| Producer | Artifact ID | ZIP bytes | SHA-256 | Expiry UTC |
|---|---:|---:|---|---|
| Windows | 12610050539 | 234847679 | `1271a76418ead98675e24f3406f3240614003c10c15385a3c74867c05e0401a1` | 2027-01-23 18:26:13 |
| Mac | 12600789926 | 77056135 | `92be56ffa04d7c334d4811a42821a314089b4f8ae01746f0dfdf456b5eab9bd5` | 2027-01-23 13:18:06 |

Windows original product SHA-256: `81b767b9a4742a92d80315cf6e08a601f2959d2d01135ad340a4d47928967208`.
Windows original ShelfReview SHA-256: `eb3734065e6e36951b5d483c8746ff6e26cf1c1d6a3340e4c35bbb597e324bfa`.
Mac original raw program SHA-256: `5f59e17cf48e77b1ef8766695bf109895feac5e628bc18d9804ee625a2749913`.

The unchanged peer-owner C++ consumer is rebuilt under the harness identity against authenticated original installed packages and fixed target owner. Its `source_sha` is the harness, not the target executable checkout. The target owner source hash and actual consumer program hash are retained independently. Iteration-2 consumer SHA-256 is `cf91aa4c312f6ef247a992857f8f3e95f2eeebc125f5dd2667f2c928c8ed1164`. No GitHub identity environment variable is forged. Original Mac program and dylib bytes are rechecked by the unchanged target loader; original sender manifest retains their exact hashes.

## Full 11-record set

All rows below are iteration-2 observations using authenticated original captures, selected native rows and visible native Open controls; screenshots and before/after frame/page values are retained for each process.

| Role/kind | Original revision | Exact-target boundary |
|---|---|---|
| TXT progress | `80dd37afff374127b98bbaf0a592ba6c` | Reflow frame range not exposed; unverified |
| TXT bookmark | `f4c4ac2d285f46c8972740f3190b80fe` | Reflow frame range not exposed; unverified |
| TXT highlight | `6d2c05e674524adc87268baaf3a27443` | Observed selection 0, expected 1 byte; failed |
| EPUB progress | `67634848ed7648d29c4d26cc9b350095` | Frame part/range not exposed; unverified |
| EPUB bookmark | `114fec2bbfd34eb3a7180826143f9a55` | Frame part/range not exposed; unverified |
| EPUB highlight | `4a641da657bf49d3a090f1e7b3ba0813` | Observed selection 0, expected 1 byte; failed |
| PDF progress | `9116d0e884d14a4898dd5af833cc82b5` | Actual fixed page 0 and zero selection match |
| PDF bookmark | `9ee7bd937e2c44c39011fbee5113e67e` | Actual fixed page 0 and zero selection match |
| PDF highlight | `305036fb05e84074959bd35b74d5ee8a` | Observed selection 0, expected 14 bytes; failed |
| CBZ progress | `0d346406998445ccad90adbac5f566f3` | Actual fixed page 0 and zero selection match |
| CBZ bookmark | `b4db44a7693046a5b87c545500858416` | Actual fixed page 0 and zero selection match |

The four fixed point matches are a narrow actual-page/selection observation, not a universal byte-offset, screen-reader, visual-quality or complete-product grant. In particular a native success message alone does not close the four reflow point gaps. EPUB `transport.chapter` is original NULL; independent host recapture reconstructs chapter scope from `part_path=OPS/c0.xhtml`. These are deliberately not called identical original transport bytes.

## Genuine NULL graph and findings

The NULL bytes are read directly from the authenticated Mac operations DB (`4731ac025a34c435b8b7cc50ba128e0c484c736c2fde6d3ae5658593ed9f3389`), never re-encoded or replaced with empty strings. A separate new profile receives the original ancestor closure and original same-book metadata through the actual account HTTPS UI and all 256 shards.

| Original operation | Bytes | SHA-256 | Parents |
|---|---:|---|---|
| NULL `2a490dc51d514032a2815e802c8b3f48` | 1017 | `a4d655ded931966dc268f01ab4ffb2717e7c31fb98b3823ad277ef4c2d0c1dbc` | `beb9ceb26d004f74a9ed5dfe1208837e` |
| Ancestor `beb9ceb26d004f74a9ed5dfe1208837e` | 675 | `9285472d256a5238b71c85d678a52fefca7b4dffd125a342142b7b04b8ed5c88` | none |
| Book metadata `3111089a73994e6a9323ea984abc2f01` | 392 | `159c69ce78ccdb01ff318b8e09674db48e5ad415baabc5c3982fde695de2f9fa` | none |

NULL UI defect: Open and Edit are enabled while Restore is disabled. Actual Open is refused without frame or history/outbox changes, including after reopening. The final harness added actual Edit exercise, but setup failed before execution. Edit backend refusal and unchanged state after Edit remain unverified. Disabled Restore is not bypassed with an injected command.

Source-reading diagnosis, not a product fix: `windows_records.inc::winrecords_controls` uses SAFE/nondeleted without requiring a usable location. For highlights, record routing sets `job->resolved_selection`, whereas `apply_pending_selection()` requires `g.pending_selection`; the latter is not armed on this path. Runtime observations, not this explanation, determine failure.

## Retained complete CI iterations

1. `bba0fe12d28f1996764eb20aca971302c6af16da`, run `40225059154` / 1, job `121264564040`: failure. Original positive account load timed out; no positive GUI result. Real NULL ingress and two-process UI findings retained. ZIP `12611470429`, 11952632 bytes, SHA-256 `26afe8e99c90b4b57462d5d561c624a3036c737893dab26c0903b1be1e0971ad`, expires 2027-01-23T19:14:13Z.
2. `db6c726c2f5bcee03d697e90b4865e7874e6b2a0`, run `40225581164` / 1: Windows `121266108707` failure; evidence authentication `121266585174` success with product false. All 22 native Open actions completed, PIDs 1112/3048; NULL PIDs 1140/5832. ZIP `12610882911`, 13057721 bytes, SHA-256 `3c02037dc478d8dcf6602a1f12a42419cb708c139e37bbc66455c6317743fda7`, expiry 2027-01-23T19:20:40Z. Authentication ZIP `12611296950`, 1107 bytes, SHA-256 `38399668d921cf816cbbd9605117e46e6684e61661303d7a85f216ab995c0952`. Its original classifier put observed highlight mismatches under missing observation; the table above corrects this classification from retained raw values without rewriting the original report. The new final-run GUI classifier did not execute.
3. Final harness `a3a53c0fb2e83afdf49f7332e82e9b5d97e513f6`, run `40226191674` / 1: **failure**, Windows job `121267962974`, authentication job `121268252434`, both failed. ZIP `12610918670`, 819426 bytes, SHA-256 `42cf191aebe9321eb60e3cac6c4dc69927386bb5c5ff4705f07e77feff395c93`, expiry 2027-01-23T19:28:25Z. Authentication ZIP `12610768942`, 981 bytes, SHA-256 `0bfc29294881b5242365e976abbf2ba1b3b497c5178a4cedaa3f0dd3403f816e`, same expiry. No fourth functional iteration is authorized.

### Final-run harness failure, not a new product observation

`prepare.py:35` failed at `require(len(blocks)==1,'unique actual program compile edge')` while inspecting the original `build.ninja`. The matcher assumption did not identify exactly one compile edge; original configuration files were retained, but package/program extraction and `target-auth.json` completion were not reached. The PowerShell multiline step masked the Python nonzero exit because later pip installation succeeded without checking `$LASTEXITCODE`. The following consumer CMake step failed to find EXReader 3.41 package configuration. GUI and actual NULL Edit were skipped. Authentication verified ZIP transport but failed completeness because `result.json` was absent; this is not an authentication pass.

The final run independently reauthenticated and printed both earlier failed-run artifacts before this setup failure. It did not reproduce their product observations. New installed-package/compiler-definition checks, the fifth wrong-actual-page negative control, new GUI mismatch classification, and actual NULL Edit remain unexecuted. Future minimal harness work requires new authorization beyond the exhausted three-run cap: inspect the retained original build configuration in Actions, correct the compile-edge matcher to its actual format, and make PowerShell fail immediately on each failed native command. Then rerun the missing scopes; no product repair is included.

## Root integration and ungranted scope

Use `.github/workflows/reader-dot-d12.yml` and `tests/reader_dot_wave2/d12/`. Download and parse original artifacts only in Actions. Use iteration-2 `result.json` for per-record raw captures/native observations and its `evidence/` for actual wire/database/profile/HTTPS/screenshots. Its independent authentication artifact records source/run/attempt, original ZIP digest, exact record sets, and four rejected negative controls: missing-record, wrong-target, duplicate-PID and false-total. Final-run installed compiler/package identity refinements and wrong-actual-page rejection were not completed; do not claim them from iteration 2 or the final failure artifacts.

No production edits, SQL injection, manual receive API replacement, real credentials/books, TLS disabling, PR, merge, default branch push, tag or Release. No physical-device, screen-reader, keyboard, contrast, performance, common-source bidirectional or complete-product acceptance. Publication blockers and fresh approvals were recorded; denied operations were not bypassed. Author is Yinuo Xu. Documentation-only sealing uses `[skip ci]` and is distinct from the tested harness.
