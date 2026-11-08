# Same-process reference ratio experiment

The complete qualification batch is `final/`: five normal runs, a frozen
`ratio-policy.json`, then five independent loaded runs. Each run uses the same
19 books (17 EPUB, 1 PDF, 1 MOBI), 16 sequential page samples per book. First-page
samples are retained but excluded from the gate. `experiment.json` and
`measured-results.md` are recomputed by `tools/perf/ratio_report.py`.

`capture.json` binds every retained native stdout to SHA-256 and records the
compiler/flags, reference/probe/SDK identities, original input hashes, operation
plan, CPU affinity, and priority. `normal/raw/` and `loaded/raw/` contain all
observations, including reference-only warmup + 31 measurements per run. The
summary rejects raw tampering and changed pixel/text/position signatures.

The loaded batch starts one equal HIGH-priority busy worker on the same logical
CPU. Its PID and successful termination are recorded. `power-original.json`
and `power-restored.json` prove temporary AC policy restoration. Pre/postflight
contains system, processor, competing-process and thermal-access telemetry.

The root `normal/`, `high-priority/`, `paired-v1/`, `paired-v2/` and `smoke-all/`
directories are retained incomplete diagnostic attempts, **not baseline
samples**. They exposed normal-priority scheduling interference, incorrect PDF
mode selection, and MOBI API/signature adaptation. `smoke-all-v2/` passed the
whole corpus before `final/`. `PERF2-OUT.txt` records the corrections, including
the initially incorrect Unicode-path diagnosis for the PDF failure.

All actual books and compiled binaries stay under the ignored `build/` tree.
The existing all-page regression emits counts and pixel hashes only; its before
and after results and diff are retained separately from performance sampling.
No source book text or images are committed.

`proposed-workflows.patch` is an unapplied proposal. No `.github/`, `src/`,
`include/`, or `examples/` files are modified. E3 remains advisory.
