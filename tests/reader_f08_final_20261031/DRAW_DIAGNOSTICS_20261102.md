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
