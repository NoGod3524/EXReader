# API34 draw-boundary diagnostic (not an acceptance change)
Base: 0480954fa803ff75765d2611f3721eeb60d4a018. Original measured failures remain immutable.
This round observes Canvas/View hardware acceleration, main-thread identities and onDraw entry/exit around unchanged drawing.
The primary callback stream retains every callback and adds public command/swap durations only.
No nearest-frame binding, duplicate suppression, first-frame removal, threshold or timeout changes.
Three product paths are explicitly SHA256-bound in contract.json, producer admission and native preparation.
The original reviewed_source and old contracts/fixtures retain their restrictive meaning.
Diagnostic side stream: 20,000 total records, 8 MiB, 256 pending writes, original handler, nonblocking enqueue.
Queue/event/byte/write failure preserves first diagnostic error in EXRReaderDiagnostics logcat and makes completion false;
unavailable/unfinished stream is incomplete, never a successful substitute. Observation overhead stays included.
Original native 1200 seconds, reader 180 + cleanup 10, old tests and all assertions remain.
One control <=20 minutes + Android build <=20 minutes; other platforms skipped; one native <=1200 seconds, no automatic retry.
18 additive controls; actual totals and outcomes must be recorded from Actions, not predicted from project scoring.
If hardware/main-thread/fences are valid but strict association fails, stop this diagnostic direction and retain failure.
API34 public FrameMetrics does not expose full raw flags or the API36 frame timeline metric.
The 120-frame gfxinfo tail is not used as a substitute for the complete primary stream.
Validation: pending independent review, producer and native execution. F08 remains unaccepted.

## Executed round and retained outcome (2026-11-02 UTC)

Measured source: `c3739ec6cb8ae8d1b65bb734aac883079b83b5b9`, tree `8438aa6eb7559fd6dafc3a8ae29630a425701a3b`, parent `0480954fa803ff75765d2611f3721eeb60d4a018`.
This documentation-only seal does not change the measured package/source identity.

Producer: https://github.com/NoGod3524/EXReader/actions/runs/41381529021 (attempt 1).
Control job 125073199311 and Android build 125073455032 succeeded; six other jobs skipped.
All 18 new diagnostic controls individually passed. The reader unittest group reported 116 tests;
these are test counts, not project acceptance item counts.
Android artifact 13113349591, `f08-final-android-build-41381529021-1`, 23008145 bytes,
SHA256 `d2d91d9857685b88c039b7c71b32d8311e3e7ebb8f28c71b924d3e3257c3f2a6`.
The actual API receipt, complete 84-payload inventory, 18-file source bundle and original native preparation authentication were retained.

Native exclusive root: `C:\Users\Oscar\exreader-f08-native-c3739ec-20261102T0316Z`.
Identity: `native-lap25002-20261102T031755Z` / attempt 1.
Sample started 03:17:54.834899Z, wrapper recorded sample terminal at 03:23:54.804346Z;
native result elapsed 358.6198910999992 seconds, sample exit 1.
Wrapper exit 0 records successful wrapper completion, not native test acceptance.
Original 1200-second cap was not extended; no retry occurred.
Owned emulator PID 3196 exited 0, package cleanup recorded empty final PIDs,
and physical display remained 1920x1200@60.

Original Shelf phase exit 0. Reader actions: seven pass plus one not-applicable.
Primary association still failed: duplicate native VSYNC keys at sequences
94/95, 148/149, 183/184, 190/191, 235/239, 251/252 and missing exact DRAW containment for draws 1/7.
The later missing reader/Window trace replay error is secondary, not substituted as the first cause.
No ACK or successful closure was fabricated.

Diagnostic side stream: 11 onDraw pairs / 22 enter-exit events, 11 bitmap draws.
Every event reported Canvas hardware=false, View hardware=true, main-thread=true,
Linux TID=main PID=4188. There were no reported fence/owner/generation/thread violations.
The side stream has no successful stop footer; diagnostic_complete=false.
ReaderView.init retains its pre-existing LAYER_TYPE_SOFTWARE setting, with the original
deterministic bitmap-resampling rationale. The diagnostic round did not introduce/change that setting.
The helper's screenshot path uses UiDevice.takeScreenshot, not a direct test View.draw(new Canvas(...)) path.
This proves a software Canvas inside a hardware-attached View; it does NOT prove that
removing the software layer would eliminate every duplicate native VSYNC or make F08 pass.
No layer/renderer/SDK/old-test change or new native round is authorized by this finding.

Retained file SHA256:
- baseline/native-result.json: `a2bc923a18270a37e94a6bfe8f2494d4b734b666d61d0d908b0572a019df88ea`
- baseline/phase-results.json: `e146c3dd169d7bf13986d1a24bd59f988dfbbc9009ab9bbe648f5ca33a165b5d`
- baseline/reader/result.json: `29ef5224a3dc1fdbbded44188c9c8b0ef71d9377fb2882080e2a268849af89ac`
- baseline/reader/draw-diagnostics.json: `c166d9f8a5d2d339429f65d7e63be7d3e25327b4e41bd2b883c5bbb2bd55da38`
- Original diagnostic JSONL: `d397fb61d3443f91d6f3c41bac33feafa43a655db3d00072e2f0d0aa8bc638a1` (8673 bytes)

Reusable VM evidence caches:
`/tmp/f08-c3739ec-ci-0315.json` (actual producer APIs and logs),
`/tmp/f08-c3739ec-native-evidence-0339.json` (native results/raw diagnostic and source evidence).
F12 independently reviewed both candidate and native findings.
F08 collection_complete, shelf_budget_accepted, reader_budget_accepted and f08_accepted remain false.
Next step is static visual-determinism review and a separately scoped experiment proposal,
not automatically relaxing uniqueness, excluding frames, changing acceptance or rerunning.


## Authorized B: default layer comparison (2026-11-02)

- Baseline A remains measured source c3739ec6cb8ae8d1b65bb734aac883079b83b5b9 and its retained failed sample; documentation-only base is 472702f4651c66972495ac81bca72f970c8d31f9. A is not rerun.
- B changes only ReaderView init layer SOFTWARE to NONE, its exact contract content binding, and this document. The adjacent historical software-layer rationale remains as baseline context; B deliberately tests that mechanism, without changing paint or drawing behavior otherwise.
- FILTER_BITMAP_FLAG and DITHER_FLAG, all pixel restoration assertions, original tests, 18 diagnostic controls, SDK, workflow, unique-vsync and DRAW association gates are unchanged.
- New approval: 2026-11-02 03:58:44 UTC. One control <=20 minutes plus Android build <=20 minutes, other platforms skipped; one authenticated new package and native sample <=1200 seconds using the existing AVD. No automatic retry; existing 180+10, 20k-record/8MiB/queue256 limits remain.
- Hypothesis: NONE may yield a hardware Canvas in the hardware-attached View. It may instead break deterministic pixel restoration and does not guarantee frame association. All failures remain failures; no tolerance or deduplication is introduced.
- If Canvas becomes hardware but strict association still fails, stop this layer direction. If Canvas stays software, record the hypothesis as not established; do not blindly tune.
- Candidate prepared only: no B execution result is claimed here. Measurement source and authenticated run/artifact/native identities will be appended after the authorized round.


## B terminal evidence: setup isolation failed (2026-11-02 04:35 UTC)

- Measured source: e8332e88e9565122ae56dc9ed988a6b00106ee92. Documentation seal is not a new measured source.
- CI: https://github.com/NoGod3524/EXReader/actions/runs/41386208377, attempt 1, completed success 04:06:37Z. Control 125087502337 and Android build 125087720070 succeeded; other six jobs skipped. All 18 diagnostic controls passed, with original reader control group reporting 116 tests.
- Android artifact 13115119310, f08-final-android-build-41386208377-1, 23008205 bytes, SHA256 42887d4fde626eedc156824c3eefc3c1519605e854a52a5b298fd25785090bae. Real API receipt, 84 payloads and 18 bundled source files authenticated before execution.
- Exclusive LAP directory: C:\Users\Oscar\exreader-f08-native-e8332e88-20261102T0408Z. Native identity native-lap25002-20261102T041007Z/A1.
- Sample PID 23576 started 04:10:07.062222Z, ended 04:17:55.481978Z, exit 1; native measured elapsed 467.7371757999972 seconds. Wrapper 24688 exited 0 only as the wrapper, not sample success. Original 1200-second total cap was not exhausted or increased.
- Shelf instrumentation failed in setup at ShelfWalkthroughTest.java:46 after 0.065 seconds: earlier shelf evidence must not be reused. No new B ten-case result was established.
- Collected Shelf validation is explicitly old A: source c3739ec6cb8ae8d1b65bb734aac883079b83b5b9, native-lap25002-20261102T031755Z/A1, all ten cases carry that same old identity. Its SHA256 bf684164ca691b14d6173a7e057e9960ce0f919238a85c69571d58e9a53493fb matches the retained B manifest entry: that proves preserved stale bytes, not B execution.
- Reader instrumentation similarly failed at ReaderF08UiTest.java:64 after 0.157 seconds: earlier reader evidence must not be reused. The original guard correctly rejected reuse before reader actions.
- Reader orchestration then recorded JSONDecodeError and adb pidof/pull/logcat timeouts. No raw reader diagnostic stream was retrieved. Canvas hardware state, pixel restoration and strict frame association for B are UNASSESSED, not passed or disproven.
- native_android.py line 710 creates a 20-second post-worker terminal collection deadline. Subsequent dumpsys calls exhausted that smaller collection window, producing the line 712 deadline/reserve error; do not label this the 1200-second total deadline failure.
- Original result remains collection_complete=false, shelf_budget_accepted=false, reader_budget_accepted=false, f08_accepted=false. Physical display remained 1920x1200 at 60Hz.
- Original wrapper shutdown failed because adb AVD-name query timed out. Under the separate 04:32:09 explicit owned-cleanup approval, PID 10996 and its child 23516 were checked against exact process names, AVD/port command, parent linkage and 04:09:31 launch times, then only those two owned processes were stopped. At 04:32:58.4826776Z remaining count was zero. This later cleanup does not retroactively make the original sample cleanup complete.
- Static fresh_owned_packages code queries pm path and conditionally uninstalls four owned packages, requiring Success; it has no separate evidence-directory absence check. Actual fresh-owned operation records have not yet been read, so no claim is made that uninstall succeeded yet left files. Setup isolation failure is established; the exact persistence mechanism is not.
- No A rerun, no B retry, no AVD wipe, no pixel tolerance change, no uniqueness relaxation. This round does not resolve F08 or add a formal completion item.

### B retained evidence hashes

| File | SHA256 |
| --- | --- |
| launch-record.json | 0960e7dd567e626d2c6dee457a6c3fd06ae4c31da49e222c93f74353490c33ac |
| baseline/native-result.json | 25a0a360c792b6780b6265ee3c096c3876f6c7e252d410b6d3e6e70dbec27c58 |
| baseline/reader/result.json | 4bd52846cef12ce71bc3e2915969dfc224e30f071a62aafebe7663be5573b159 |
| baseline/reader/draw-diagnostics.json | b262ea0cdfd16f9a089aa02d05fa8e84b255b72de978be4815e6d0764bc798e3 |
| baseline/execution/ui-instrumentation.txt | 5aa229b3540703110a941a83b0e56e271e27ab66d915321ac8c63ac47b8dd7c2 |
| baseline/reader/reader-ui.stdout.txt | ba09b740aa89064f8295f2047b6c8e7d927f82b5dc802ee1470fe55c74f5f168 |
| owned-emulator-cleanup-0433.json | 1a385e5f72e6f07b961129fa541a34db4e551adfc80feb862362cfe52db27e43 |

Independent review caches on existing VM: /tmp/f08-e8332e88-ci-0407.json, /tmp/f08-e8332e88-native-evidence-0431.json, /tmp/f08-e8332e88-failure-0433.json, /tmp/f08-e8332e88-stale-0435.json. Original samples and logs remain unchanged.


### 04:38 UTC isolation receipt addendum

The earlier 04:35 note accurately described the then-unread receipt; it is now inspected and independently reviewed. baseline/fresh-owned-packages.json SHA256 is 6b7bb194c7d539ed960d7372355002f235fa82704f69a405de735ec6db80cfa2. All four owned packages (org.exreader.host.test, org.exreader.host.uitest.test, org.exreader.host.uitest, org.exreader.host) had nonempty previous_path and each uninstall returned code 0, stdout Success, empty stderr. The empty pm-path branch was NOT taken in this run and cannot explain this result.

Exact Shelf source examples/android/uitest/src/androidTest/java/org/exreader/host/uitest/ShelfWalkthroughTest.java lines 43?46 uses the instrumentation target context, then getExternalFilesDir(null)/shelf-evidence and asserts the directory absent. Successful uninstall receipts followed by an old A evidence directory visible to setup are established facts. The underlying persistence or restoration mechanism remains unproven. No old guard, tests, directory, AVD data, source or native result was modified by this investigation. Canvas/pixel/frame results remain unassessed.

Additional original cache: /tmp/f08-e8332e88-isolation-0438.json. No new execution or retry was performed.


## B evidence-directory isolation receipts (2026-11-02 05:04 UTC)

These are bounded maintenance operations, not UI, reader, performance or CI tests. Measured B source remains e8332e88e9565122ae56dc9ed988a6b00106ee92; its failed result is unchanged. A and B original evidence directories remain preserved.

1. First approved <=300-second operation, script v3 SHA256 5ec391165f427a846ccbb2aa7accbb27f5eaf3b8a7d7e9f22446962d3e1fa761, ran 04:46:33.031403Z to 04:46:39.663848Z (6.632933 seconds), exit 1. The first getprop queried immediately after launch and returned device emulator-5554 not found. No directory was inspected, backed up or deleted. Owned PIDs 27876/4080 were subsequently identified, normally shut down and independently observed absent. Receipt C:\Users\Oscar\exreader-f08-isolation-20261102T0445Z\receipt.json SHA256 7b9c9550a6d91399ab1184155fed57ed0120385acd70c431288ca6f4f745c678 is retained.
2. Following explicit 04:53:13 approval for one corrected operation, v4 changed only the exclusive destination and inserted wait-for-device within the same absolute boot deadline. Script SHA256 8be49e276d7b025d9a3bca42003367de18a26df726181dd9b093204fbdb8eee0. Total <=300 seconds, boot <=180, processing <=90, shutdown <=30; no clock reset, retry or budget increase.
3. V4 ran 04:57:24.398817Z to 04:58:33.551120Z, elapsed 69.15282989999832 seconds, exit 0. Both fixed directories existed. Full directory/file inventories and every remote/local SHA256 and size matched; a second remote inventory/hash comparison completed for both before any deletion.
4. Shelf backup contains 21 files / 22 entries / 1224554 bytes; reader backup contains 40 files / 42 entries / 145606 bytes. Backup root: C:\Users\Oscar\exreader-f08-isolation-20261102T0455Z\backup, with shelf-evidence and reader-evidence subdirectories. No original A/B archive was changed.
5. all_backups_verified was recorded at 04:58:29.235568Z, preceding both exact directory removals. Only /sdcard/Android/data/org.exreader.host.uitest/files/shelf-evidence and /sdcard/Android/data/org.exreader.host.uitest/files/reader-evidence were removed. Both were subsequently observed absent.
6. Owned emulator PID 16272 and child 2816 were normally shut down; two final process queries returned empty. No APK installation, UI test, new CI, AVD wipe or other user-data cleanup occurred.
7. Original v4 receipt C:\Users\Oscar\exreader-f08-isolation-20261102T0455Z\receipt.json SHA256 798e98d592a6d80176dd007074e47888ed85f3c6638d25a287df42f3f5bb053b contains 30 command receipts. Independently audited VM copies: /tmp/f08-isolation-receipt-0452.json and /tmp/f08-isolation-receipt-0503.json.
8. Canonical JSON manifest hashes (sorted keys, compact separators) for the saved directory records: shelf 5621eaf3ccffab37e6b62a7157272ea92921f1db94aa70b79a190d4661bd28f6; reader bff13e8fc5f2ee0c2a3580a850100497c13dadebdfa0fe76bac6eb75ace46256.

The setup evidence directories were absent at the end of this operation. Their state after any future installation is not yet observed. B Canvas hardware status, pixel restoration and strict frame association remain unassessed; this maintenance result adds no formal F08 completion point and authorizes no further sample.

## B resume and pre-instrument isolation mitigation (2026-11-02)

The authorized same-source B resume reused e8332e88e9565122ae56dc9ed988a6b00106ee92, CI 41386208377/A1 and artifact 13115119310 after archive/receipt/18-source hash revalidation. No new CI or A run was performed. New output C:\Users\Oscar\exreader-f08-native-e8332e88-resume-20261102T0510Z, native identity native-lap25002-20261102T050903Z/A1, sample 05:09:03.031549Z to 05:14:27.137322Z, elapsed 323.4935641999982 seconds, sample exit 1 (wrapper exit 0). Owned emulator 25744 shut down normally and the subsequent host query found no remaining launcher/children.

Shelf now genuinely passed all ten UI cases under the new e833/current-native identity; validation SHA256 bfb8bcdb2b7e74f1486a26f3c6916307069cfbe513db4e26225d4f278e6e8c30. Reader stopped at setup line 64 after 0.063 seconds, rejecting earlier reader evidence before any of its eight actions. Pulled reader validation SHA256 09eb6c03c57f558a8ea63dbad8d1ea166b55f3f26265d9f0abe6ecec31c6f33b is byte-identical to retained old A validation (c373/native031755), not a new passing result. Reader diagnostics contain only a 187-byte start header, zero onDraw fences and zero bitmap draws. Canvas hardware behavior, pixel restoration and strict association remain unassessed. Original overall acceptance flags remain false.

Native result SHA256 a6210cfe86e65bef7c9276a50ea8288069256e3074ba3b967caed74548e88c34; reader result a6fb44c8d95bba64d6324f58beefd77a82b3ee40cbc6e650e0294395d38235e6; raw diagnostics 583c18c3a2e64b645112739fdee18210e00d46bf6ffec6add73e833254f801f1. Independently reviewed caches: /tmp/f08-e8332e88-resume-evidence-0531.json and /tmp/f08-resume-installation-0533.json. No automatic further directory cleanup or sample followed this failure.

Static and retained command evidence: all four initial package uninstalls returned Success. Reader instrumentation APK installation (-r -t) succeeded and its pulled installed SHA matched the producer. Subsequent pm clear targets the product APP, not the helper. Both product and helper source manifests explicitly set allowBackup=false. The reviewed setup code contains no copy/push of old reader-evidence; only fixtures and later stop ACK are pushed. These facts do not identify the exact persistence/restoration mechanism, and this document does not claim AutoBackup as a proven cause.

### Explicitly authorized mitigation candidate, 05:35:47 UTC

Only reader_android.py, new test_reader_preinstrument_isolation.py and this document change. After reader-helper installation/hash verification and product seed/fixture setup, but before starting PSS sampling or the reader UI process, an independent pre-instrument gate handles only /sdcard/Android/data/org.exreader.host.uitest/files/reader-evidence. Absent is a no-op. Present requires complete local preservation, every remote/local SHA256 and complete inventory equality, then a second unchanged remote census before the exact directory may be removed and verified absent. Every command, retained file and receipt remains in the new output/isolation-prereader tree; prior A/B samples are untouched.

The gate has at most 20 seconds clipped to the original absolute worker deadline; at most 10000 entries / 256 MiB are admitted. The bounds are rejection limits, not a promise that copying finishes in 20 seconds. Any failure stops entry to the reader cohort and preserves the first failure; attempted removal without confirmed outcome is explicitly marked unconfirmed. No broad helper pm clear, APK manifest/AutoBackup change, SDK change, old-test edit or acceptance override is made. The original helper assertAbsent and pixel/frame/identity assertions remain unchanged.

Fourteen new Actions control methods comprise two positive and twelve negative cases, covering no-op, complete preservation, wrong/escaping paths and symlinks, failed or timed-out queries, bounds, incomplete or corrupted copies, changing remote data, failed removal, remaining directory, and absolute deadlines. All existing tests, including the 18 diagnostics controls, remain unchanged. The approved verification budget is one control <=20 minutes plus Android build <=20 minutes (other platforms skipped), then one authenticated new-package native sample <=1200 seconds with original 180+10 cohort limits, no automatic retry. This is a corrective isolation mitigation, not proof of the underlying persistence cause or F08 completion. Actual candidate test/native results are pending.
