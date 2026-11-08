# Pressure correction experiment

`diagnostic/` is an **invalid, incomplete instrumentation pilot**. Its first
implementation omitted the chapter-transition work that R3 already includes
in wall time. Raw files and the failure are retained, and the power policy was
restored. It cannot contribute to a baseline, a five-run batch or a conclusion.

`diagnostic-corrected/` is a second pilot. Chapter transitions are covered, but
two medium-load samples exposed a roughly 15.9 ms scheduling quantum between
separate QPC and TSC measurement boundaries. Its validation failed; both full
raw runs are retained and no high-load run was started. It does not qualify.

`diagnosis/` measures the original 120,000,000-step reference and the
complete R3 operation in three load conditions, once each. It retains the v1
reference order, including repeated references on chapter transitions. This
batch diagnoses the cause; it is not the five-run qualification batch.

`final/` is the qualification batch: five consecutive runs at each of 0/1/3
workers, with the reference fixed to 12,000,000 iterations. Each page is bracketed
by before/after references. The gate ratio is `p95(target thread cycles) /
p95(sqrt(before thread cycles * after thread cycles))`. The v1 wall ratio and the
wall sandwich are retained as ablations, not substituted for this metric.
Raw `samples[].ratio` remains the v1 wall ratio for the reused integrity checker;
the schema-2 summary's `ratio` is the cycle formula. No target operation is retried.
`policy.json` is frozen after the five no-added-pressure runs and before starting
either pressure candidate. No outliers are dropped. "None" means no injected
worker; other applications on the host remain running.

The CPU-work counter excludes descheduled/blocked time. Raw wall time remains
available; a required user-latency gate also needs an isolated-runner wall check.
See [ROOT-CAUSE.md](ROOT-CAUSE.md) for the measured hypothesis assessment.

The native adapter adds thread-cycle, elapsed TSC, coarse OS CPU-time and
context-switch observations. Coherent snapshots use the same QPC/TSC/cycle
boundaries. A context switch during a clock snapshot retries only that snapshot,
never target work. Layout includes EOF probes and chapter creation;
render includes the RGBA render call. Hashing and freeing remain outside target
timing. Counter phase sums and TSC/wall coverage are checked independently.
The same page, pixel, text and position signatures are checked across runs.

`pmu-read.json` records zero configured hardware counters. No retired-instruction
or IPC measurement is claimed. The frozen reference loop has six instructions
per iteration in `reference-disassembly.txt`; target instruction mix is not
inferred from that loop. TSC is elapsed invariant ticks, not unhalted core
cycles. QueryThreadCycleTime counts time attributed to this thread in a
CPU-dependent cycle unit, and is never converted to milliseconds. The
`cycles/tsc` fractions are scheduling diagnostics for this observed host only.

`counter-self-check.json` independently contrasts a 100 ms sleep with busy work.
`during-load.json` records actual per-core frequency/performance observations
while each load condition is active. The pressure workers are the original
register-only reference loop: 0 / 1 / 3 HIGH-priority workers pinned to CPU 3,
competing with the HIGH-priority benchmark on CPU 3. Only workers created by
the capture are stopped. AC policy is set to min=max=100, boost=0, then restored
and read back in `finally`.

The first full `powercfg /qh` dump stalled. Only that owned dump process was
stopped (see `preflight-power-dump-timeout.json`); the three settings had already
been saved individually. Subsequent telemetry skips the redundant full dump.

All books and binaries stay in ignored `build/`. The fixed #87 SDK DLL is reused
after checking that its `src`, `include` and R3 operation source match this
checkout. `regression-versus-87.json` compares the new all-page rendering to #87
using the identical DLL, font, layout and corpus. No book contents are committed.

Reproduction (Windows x64, GCC/MinGW, the corpus and font from #87):

```powershell
cmake -S tools/perf -B evidence/perf-gate3-20261108/build -G Ninja `
  -DCMAKE_BUILD_TYPE=Release `
  -DEXR_PERF_REFERENCE_STEPS=12000000 `
  -DEXR_PERF_SDK_DLL=C:/path/to/frozen/libexreader.dll `
  -DEXR_PERF_SDK_INCLUDE=C:/path/to/frozen/sdk/generated/include
cmake --build evidence/perf-gate3-20261108/build --target load-probe load-reference perf-reference --parallel 2
pwsh -NoProfile -File tools/perf/load_session.ps1 -Output evidence/perf-gate3-20261108/NEW `
  -Build evidence/perf-gate3-20261108/build -Font C:/path/to/Reader.otf -Mode sandwich -Runs 5
python tools/perf/load_report.py evidence/perf-gate3-20261108/NEW
python tools/perf/check_load.py evidence/perf-gate3-20261108/NEW
```

Without `EXR_PERF_SDK_DLL`, CMake builds the SDK from this checkout as usual.
The reference iteration count is a fixed build-time constant, included in the
capture plan and frozen policy, never calibrated from candidate results.
`PERF3-OUT.txt` is the append-only step record.

This directory's `.gitattributes` preserves native CRLF bytes so raw SHA-256
digests survive Git checkout. Compiler/disassembler logs retain their original
whitespace. `manifest.json` binds immutable evidence; the append-only progress
log and publication receipt are explicitly excluded.
