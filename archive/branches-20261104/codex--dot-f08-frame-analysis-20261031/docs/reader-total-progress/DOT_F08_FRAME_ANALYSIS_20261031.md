# F08 original-frame evidence analysis

Base/source cfdaf6a4531548be63b4dd0c2bccd6b050a93124, producer run41155753132 attempt1.
Exclusive branch codex/dot-f08-frame-analysis-20261031. Three new files only.
Approved one Ubuntu22.04 Actions job, at most20minutes; no new product execution, compilation or sampling.

The four original archives are fixed by ID, bytes and SHA256 in analyze.py and checked against GitHub API before download and actual bytes afterwards.
Original ZIPs are retained unchanged. ZIP member count10000, expanded total256MiB, individual32MiB limits reject dangerous paths, canonical/case-fold collisions, symlinks, encryption and special files before reading entries. No extraction to filesystem.
All ZIP parsing and controls run only in Actions. No credentials are recorded.

The unmodified original frame validator is re-executed: original2positive+24negative controls remain unchanged.
Each original raw frame JSON is bound to producer/source/attempt/PID/hash and recomputed against its existing summary.
Original44launches and760samples (32/520 +12/240) must remain complete.
Three additional positive controls check long-tail percentile preservation, empty distributions and union overlap; four negatives reject negative/bool/NaN values and duplicate JSON keys.

Per-launch and pooled per-cohort counts/min/p50/p95/max use nearest-rank percentiles.
All adjacent-counter intervals remain, regardless of length; counter gaps and incomplete records remain separately counted, idle attribution unknown.
State write overlap is the union of intervals intersecting each observed frame phase, not a sum that double-counts concurrent writes.
Multiple clocks may represent simultaneous surfaces. Neither pooled events nor cross-clock duration sums are physical-display or CPU-utilization estimates.
RSS is from instrumented runs; probe memory/time overhead is explicitly not subtracted or claimed absent.
No cause, avoidable-time estimate, numerical pass threshold or final six-platform acceptance is inferred.

Expected output: source-bound original archives/metadata, controls, per-launch overlap rows and numerical summary.
Result pending. budget_ratified=false, F08_accepted=false, fixed formal95/108 unchanged.
This is evidence for a future explicit product budget decision, not that decision.

## Sole-run actual result

Analysis source1f9540c7e362c0a75d0bb863d385aaf25e62e084.
Run https://github.com/NoGod3524/EXReader/actions/runs/41161801430 attempt1,
job124420751243 SUCCESS completed2026-10-31T02:51:11Z.
The actual Actions F08_ANALYSIS line reports analysis_completed=true,
original44launches/760samples, original2positive+24negative and new3positive+4negative controls.
All four original archives passed pinned metadata and downloaded-byte checks in Actions.
No product execution or additional sampling occurred.

Nearest-rank pooled event measurements, converted from raw microseconds to milliseconds:

| Metric | Main32 launches: count / p50 / p95 / max(ms) | Interactions12 launches: count / p50 / p95 / max(ms) |
|---|---|---|
| GDK before-to-after phase | 3132 / 0.586 / 4.123 / 86.998 | 1064 / 0.332 / 3.951 / 36.751 |
| Continuous-counter interval | 3076 / 17.093 / 33.249 / 1748.218 | 1052 / 17.170 / 652.456 / 1541.720 |
| State-file write | 2073 / 0.606 / 2.430 / 87.955 | 1375 / 0.574 / 0.917 / 36.343 |
| Frame-phase union overlap with writes | 3132 / 0 / 1.168 / 86.245 | 1064 / 0 / 1.296 / 36.343 |

430 main frames and234 interaction frames overlap writes. This is temporal correlation,
not proof that writes caused the long phase or that removing them saves that duration.
Long adjacent-counter intervals remain even when over a second; idle versus active
attribution is unknown, so these are NOT asserted dropped frames or UI stalls.
Both cohorts have zero counter-gap pairs and zero incomplete frames, but actual
presentation timestamp sample count is ZERO in each. Presentation latency is null,
not zero; no physical-display latency claim is supported.

Instrumented RSS KiB: main count32 p50=70064/p95=206060/max=206140;
interaction count12 p50=63360/p95=63744/max=63744.
These values include probe influence and do not establish an uninstrumented product budget.
Per-launch metrics/overlap rows and raw original archives are preserved in the artifact.

Artifact13026904647,3081191 bytes,
SHA2561891e213aa47d71b732942b4fc875dc14b7113e0d40db3fcdb46dc0b32237276.
Artifact metadata and actual Actions log were read via the authorized route;
no ZIP was downloaded/parsed on the connected computer or InstaBox.
budget_ratified=false, F08_accepted=false; formal95/108 unchanged.
One of one authorized analysis runs used. This result is a budget-decision input,
not a product performance acceptance. Documentation sealing does not launch another run.
