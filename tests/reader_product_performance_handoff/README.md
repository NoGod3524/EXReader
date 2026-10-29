# Product performance handoff (F08, SDK 3.42)

Actions-only wiring. Reuses the existing real-host drivers unchanged
(`tests/reader_perf_windows/`, `tests/reader_perf_gtk/`) and rebinds them to the
installed SDK 3.42.0 common source:

* `gtk_probe/CMakeLists.txt` – corpus seeding probe pinned to 3.42.0 (original pins 3.41.0).
* `verify_gtk_artifact.py` – copy of the GTK same-run artifact verifier bound to this workflow and artifact names.
* `gate.py` – combines the Windows and Linux summaries into `handoff-report.json/md`;
  fails only on identity/coverage problems. `f08_accepted` is always false: no numeric
  product budget has been ratified, so no threshold is applied or invented.

Workflow: `.github/workflows/reader-product-performance-handoff.yml`.
