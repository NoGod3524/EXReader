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
