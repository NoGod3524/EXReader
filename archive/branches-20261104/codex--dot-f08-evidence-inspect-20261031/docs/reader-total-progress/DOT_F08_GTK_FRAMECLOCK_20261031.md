# F08 GTK frame-clock evidence (candidate only)

Base: c1de24844830e5f389c37a4cfe744ed60e2d0b51, whose original scroll repair run 40980931719 succeeded.
This five-file exclusive branch adds a test-only GTK module, build file, environment wrapper/verifier, workflow, and this record. Product source, SDK, all old sampler/observer/assertion files remain byte-identical. One Actions run only: sampling 90 min and existing independent verification 20 min.

## What the probe measures

The module observes actual GdkFrameClock before-paint/after-paint signals and retains refcounted GdkFrameTimings until process exit, so completion/presentation availability is recorded honestly. It does not infer frame time from state-file publication intervals. Complete and incomplete records are both retained. A null presentation timestamp means unavailable, not zero delay; Xvfb timing is never physical monitor scanout or mobile fluency.

A narrowly filtered g_file_set_contents observer times only host state.ini writes whose contents begin with the host observation header. The original function executes once with unchanged arguments/result. No content is logged. This measures the synchronous state-file call, not preceding state assembly, SDK render duration, or causality. The host draw callback invokes state(), which constructs full observation text and synchronously writes it; this is a hypothesis to quantify, not an established dominant bottleneck.

Static bounded buffers hold at most 65536 frame rows and 65536 write rows per process, 64 clocks. Overflow invalidates evidence. No per-frame probe disk writes. A single per-process JSON is written at normal exit. Missing/partial output fails the verifier; killed processes do not masquerade as complete. Memory and timing are instrumented: report probe static bytes and never compare these RSS figures to uninstrumented baselines as product regression evidence.

## Existing coverage and budgets

Unchanged 2202-original corpus; 32 original launches / 520 samples; 12 interaction launches / 240 samples; six measured batches per direction with four physical wheel events, three font steps, 20 page turns. Original 180-second scroll operation (including preparation), 300-second repaint and 600-second initial startup bounds remain unchanged. The wrapper alters only per-host environment for the module; original input and assertion paths execute unmodified.

Validation binds each raw file to the original launch PID, exact source/run/attempt and executable path, then hashes the measured executable and module. No missing old sample is accepted. Two positive and 24 negative protocol controls retain individual expected/actual rules. Synthetic controls are not frame performance.

## Interpretation and limitations

before/after paint phase duration and state-write duration are separate metrics. Presentation latency is reported only for complete records with a real timestamp. Every consecutive-counter interval is retained, including arbitrarily long slow intervals and incomplete timing records. Nonconsecutive counter pairs are separately counted and never joined. Idle attribution remains unknown: duration or refresh interval cannot classify an interval as idle, and no slow sample is censored. Neither interval category is called CPU render time. No numeric product budgets have been ratified, none are invented or raised. F08 remains pending and fixed formal score stays 95/108. Android/Apple/Windows frames and physical devices are not covered.

The GTK module is instrumentation loaded into an otherwise unchanged program, not the shipped product configuration. A causal optimization would need separately authorized controlled evidence; this package does not change state() or its write semantics. All builds, syntax checks, controls, sampling and artifact validation execute only in Actions. This document records design; results must be bound to the sole run before making execution claims.

Textual exit-path review: the unchanged Host.close sends Alt+F4 then waits 60 seconds; only timeout invokes kill and records timeout. The verifier requires process_exit == 0 and the raw PID file. Forced termination does not run normal C destructors and is a failed/missing-evidence path, never an accepted empty trace. This is source review; Actions must demonstrate actual output.
