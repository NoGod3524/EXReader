# Windows host render diagnostic

Build the console target with `examples/windows/selection_tests.cmake` included
through `CMAKE_PROJECT_EXReader_INCLUDE` (see the exact configure command in
`evidence/dfinal-b-followup-20261114/configure-exit.json`). Then run:

```powershell
cmake --build build/audit-msvc --target exreader-shell-selection-test
python tests/reader_perf_windows/render_budget.py --binary build/audit-msvc/exreader-shell-selection-test.exe --font C:/Windows/Fonts/segoeui.ttf --manifest tests/reader_perf_windows/render-corpus.json --corpus C:/path/to/frozen/books --out render-realbooks.json --repeats 3
```

Use the three originals listed in `render-corpus.json`. Their source URLs are
provenance; Gutenberg may regenerate EPUB files. A changed SHA-256 must fail,
not silently replace the frozen original. For a new runner, fetch the frozen
corpus with `python tests/reader_perf_windows/render_budget.py --fetch-corpus
--manifest tests/reader_perf_windows/render-corpus.json --corpus build/frozen-books`.
A regenerated upstream book fails the hash check; no alternate URL or replacement
book is silently accepted.

The real-book path now uses the production `import_bounded_epub`, SDK source,
`shell_epub_source` presentation wrapper and `bounded_pager`. Each book's fixed
spine path is part of the manifest and is checked against the process output.
The previous whole-document `exr_document_open` path rejected pg10 with
`EXR_LIMIT`; those archived failures remain valid for that older load path.
The bounded-part workload is different and must not be compared numerically to
the archived whole-document baseline. Import and first bounded bitmap are included
in setup time; only alternating pages 0/1 of the fixed spine part are sampled.

The supplied font is hashed. Use an installed host font for the real-book run;
the tiny SDK fixture font is suitable for the CTest pipeline check only. The
English corpus does not establish CJK font/fallback performance.

Each of three baseline/candidate pairs uses separate processes (AB/BA order
alternates), 8 warmups and 64 alternating page 0/1 renders. Raw timings are
retained, p50/p95 independently recomputed, and every process's peak working set
recorded. Relative ratios compare medians of the per-process measurements:
render p50/p95 and setup-render-ready must stay below 2.5; peak below 1.25.
No absolute time threshold is used. Run without other benchmark/test jobs.

Default baseline and candidate are the same executable: this measures
repeatability. To compare revisions, supply `--baseline-binary` and
`--baseline-source`, and retain both builds' configure/compiler logs. Each
executable must have its own matching SDK runtime. Binary hashes alone do not
prove which source produced a build.

`setup_render_ready_ms` ends at a prepared bitmap; it is not first interactive.
`render_p50_ms`/`render_p95_ms` do not measure display presentation or a populated
product shelf. Reports are advisory and `accepted=false`; F08 still needs the
complete product/platform measurements. The parser and negative threshold
checks can be run with `python tests/reader_perf_windows/render_budget.py --self-check`.
