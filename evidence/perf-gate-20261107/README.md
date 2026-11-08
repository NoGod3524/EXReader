# Performance gate evidence

Status: advisory=true, accepted=false. No qualifying clean baseline; required gating cannot be restored.

- `attempt-1`: one partial process, stopped for persistent idle-target failure; not used for thresholds.
- `attempt-2`, `attempt-3`, `candidate`: 5 fresh processes/configuration, 3 configurations each; all raw samples retained. Candidate is independent and started after `three-tier-policy.json` was frozen.
- `three-tier-policy.json`: script-derived diagnostic tiers 1.10/1.25/1.50, eligible=false. `strict-check.json` returns rejection for stability/qualification despite numeric values being below gate/hard limits.
- `*-preflight.json`, `*-postflight.json`, `*-power-*.json`: power, virtualization, background CPU deltas, nominal/effective-performance counters and inaccessible temperature evidence. Complete sessions restored their original AC settings exactly.
- `e1-load-analysis.json`: original E1 background-load analysis. `collector-versions/` preserves exact SHA-verified early wrappers; current wrapper is in tools/perf/.
- `build-command.json`, `configure.txt`, `build.txt`, `build-identity/`: fresh build from source 2f288e15066d616972d312e638b5d9dd04d6e786. Binary/build directory is ignored; generated consumer, compiler commands, cache and hashes are retained.
- `realbooks.json`, `realbooks-repeat.json`: 19/19 books, 11296 pages each; repeat diff has zero changes. Historical c665 baseline diff (`realbooks.diff.json`) has 8604 changed common pages and remains a review result, not a historical pass.
- `proposed-workflows.patch`: proposal only; git apply --check passes; no .github files changed.

Details, executable commands and restoration prerequisites: [PERF-GATE-PROPOSAL.md](../../docs/validation/PERF-GATE-PROPOSAL.md).
