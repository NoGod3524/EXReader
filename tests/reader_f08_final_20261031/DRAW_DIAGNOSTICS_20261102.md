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
