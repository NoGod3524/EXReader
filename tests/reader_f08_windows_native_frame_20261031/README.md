# Windows native full entry

`native_full.py` runs the original sampler bodies through the native Win32 host.
It does not import `desktop.py`, change display settings, run local source Git,
or set Actions variables. The producer is the authenticated hosted build.

The default plan has 78 EXReader starts: three original 16 MiB TXT diagnoses,
one extra launch with all 12 original size-bisect imports, five main cohorts
with 12 launches each, two interaction cohorts with five launches each, and
four preparation launches. The original TXT rejection rule can skip its 12 main
launches, leaving 66 starts; the audit reports those 12 as missing from the
default plan. The diagnosis and rejection samples remain in the run.

## Collection

Use the artifact's `native-source/native_full.py` with Python on LAP25002:

```powershell
python native_full.py --zip BUILD.zip --metadata BUILD-metadata.json `
  --expected-source PRODUCER_SHA --helper-root NATIVE_RUNTIME `
  --output C:\Users\Oscar\.codex\f08-device-runs\FRESH_RUN `
  --observer observer.exe --observer-source OBSERVER_SHA `
  --observer-sha256 OBSERVER_EXE_SHA256 --observer-bytes OBSERVER_EXE_BYTES
```

The initial `F08_NATIVE_FULL_CONTROL` line names a fresh sibling `.control`
directory and the live harness PID. Controller writes and controller stdout/stderr
logs stay outside raw. Every `F08_NATIVE_FULL_PICKER` line names one fixed file, its digest, the owned
product PID and a fresh completion path. The controller selects that file in the
real owned Windows file dialog using computer-use. After the computer-use action
and its required post-action refresh return, it atomically writes this JSON to
`complete_file` (QPC is read with `QueryPerformanceCounter` on the same host):

```json
{"pid": 123, "request": 0, "qpc": 456, "computer_use_returned": true, "post_action_refresh_returned": true}
```

The sampler observes the actual dialog opening and closing. Its original import
body resumes at dialog close to sample real busy-window input. The completion
marker must be present before product close and the next launch. The live
harness validates and copies it into raw; the controller never writes raw. Fast preparation
imports can finish before sampling; their state is recorded as observed.

Shelf and restore TTI retain their original observation points before observer
readiness waits. The complete native trace starts at product launch. First open,
all eight page turns, font attempts, failures and later completion tails remain.
The original font fallback can remove partial values from its own aggregate;
raw input/native/WGC records and stage logs retain those attempts.

The observer must support `--check-limits` and the optional fifth capture
argument `capture_limit_ms`. Its default remains 120 seconds/7200 frames; this
entry passes the remaining stage time (at most 90 minutes) and records it. The
longer frame-count safety cap follows 60 Hz plus the eight-frame pool, with a
7200-frame minimum; the existing 1 GiB image cap still fails explicitly.

The full collection cap is 90 minutes. The controller checks the harness PID/command and writes `STOP` atomically in
the external `.control` directory while the harness is live. This stops further
case work and closes owned processes; the run remains incomplete.
A physical computer-use stop must stop the controller and collection. It does
not authorize a retry. The harness waits for all owned processes before sealing
raw last and writes an external `SEALED.json` receipt with its manifest digest.
If cleanup cannot complete, it withholds the manifest and writes `UNSEALED.json`.
Late STOP/CUA writes and post-seal cleanup notes stay external and are separately
authenticated; sealed raw is never rewritten. Original cleanup retains profiles inside the run, and
shared profiles are snapshotted after each product close.

## Independent audit

Pin `manifest.json` immediately after collection. Supply the separately
received GitHub artifact metadata, original ZIP and observer identity:

```powershell
python native_audit.py --run RAW_RUN --output FRESH_AUDIT_OUTSIDE_RAW `
  --manifest-sha256 RAW_MANIFEST_SHA256 --helper-root NATIVE_RUNTIME `
  --zip BUILD.zip --metadata BUILD-metadata.json --expected-source PRODUCER_SHA `
  --observer observer.exe --observer-source OBSERVER_SHA `
  --observer-sha256 OBSERVER_EXE_SHA256
```

The audit has a separate 20-minute cap. It checks the original verifier's full
20-assertion inventory, original 30/10 lower bounds, exact requested case counts,
all 12 bisect inputs, all interaction samples, package/corpus identity, every
native launch and real picker marker, and every sealed file. Reader content is
`present`, `missing`, or `not_applicable`: shelf/import launches with no reader
request or production do not require reader pixels. An applicable reader with
no bound nonuniform content is missing. Uniform observations stay cause unknown.

The audit always leaves F08 acceptance false. Same-generation native UI frame
candidates and all paint/tail rows are retained, but the complete all-UI/LISTBOX
frame census is still missing. WGC timestamps are not physical scanout evidence.
