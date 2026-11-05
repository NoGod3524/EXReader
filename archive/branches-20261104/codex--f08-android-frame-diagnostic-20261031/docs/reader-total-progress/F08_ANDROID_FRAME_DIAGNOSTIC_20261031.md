# F08 Android same-process frame diagnostic — 2026-10-31

Base: `03ecfa21f6cd8d8e354145d56ffdf24244ecbe61`. This lane is diagnostic; `f08_accepted` is always false.

The original SDK 3.42 complete-feature optimized, non-debuggable Release build and seed-ui importer are reused. App and instrumentation are rebuilt together with one ephemeral CI certificate. The unchanged seed creates 2,201 real TXT imports and one real PDF, then runs the production mapping repair. No private fixture JNI is invoked or exported by Release.

One `MainActivity`, its original `R.id.book_list` ListView, one Window and one PID run NONE → SOFTWARE → SOFTWARE → NONE. Each interval includes its layer transition and two actual 1,000ms smoothScrollBy movements of twice the native view height. Forward and reverse positions must differ. The runner retains initial, first-draw, outside, unavailable and all completed callbacks, callback losses and overflow counts. It restores the original layer. Canvas hardware state remains unknown because the production draw path is not intercepted. View hardware state and exact identities are observed on the main thread.

FrameMetrics is registered before MainActivity.onCreate. The reusable object is copied immediately; samples stay in a bounded in-memory list until the listener is detached and its Handler drained. Segments use System.nanoTime and INTENDED_VSYNC_TIMESTAMP, both CLOCK_MONOTONIC. Clock bracketing against elapsedRealtimeNanos is retained. Java TOTAL_DURATION is not replaced by native gfxinfo's stall-adjusted summary.

A fixed 20-second official Perfetto capture records FrameTimeline and gfx/view/wm/input plus sched and CPU frequency/idle. Per-interval raw gfxinfo framestats snapshots retain the bounded ring; intended-vsync joins to FrameMetrics and FrameTimelineVsyncId joins to native app tokens, then to SurfaceFlinger display tokens. Unmatched or ambiguous joins remain visible. Raw trace, SQL, CSV, callback rows and all failures are authenticated in a same-run ZIP and independently replayed.

Budgets remain P95 16.67ms, P99 33.34ms, first interactive 2,000ms and memory 512MiB. No display size or density is changed. This experiment does not promote a layer type to production or establish global F08 acceptance. Sample and independent audit jobs each have a 20-minute cap.

Production scope is exactly four additional read-only fields in the already opt-in ShelfWindowMetrics capture: UNKNOWN_DELAY, ANIMATION, COMMAND_ISSUE and SWAP_BUFFERS. SDK, frontend defaults, owners, transactions and original tests are unchanged.

Sources: [API34 FrameMetrics](https://github.com/aosp-mirror/platform_frameworks_base/blob/android-14.0.0_r1/core/java/android/view/FrameMetrics.java#L253-L281), [native completion](https://github.com/aosp-mirror/platform_frameworks_base/blob/android-14.0.0_r1/libs/hwui/renderthread/CanvasContext.cpp#L753-L773), [layer semantics](https://developer.android.com/develop/ui/views/graphics/hardware-accel), [official FrameTimeline configuration](https://perfetto.dev/docs/data-sources/frametimeline).
