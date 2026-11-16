# Real-World DOCX Structural Fixture Suites (`argon` & `synthetic`)

This directory contains two complementary, independently authored 30-document DOCX structural fixture suites (60 `.docx` fixtures total, all original and MIT-licensed, each `< 60 KB`):

- **`argon/`** (PR #132): 30 structural `.docx` fixtures (`01-table-merged-grid-vmerge.docx` .. `30-other-header-table-chinese-fields.docx`) generated deterministically by `argon/make_fixtures.py` and verified by `tests/docx/check_realworld_matrix.py` (`Matrix A-argon`: read → model → write; `Matrix B-argon`: read → paragraph/table edit + undo/redo → write).
- **`synthetic/`** (PR #126): 30 mixed `.docx` fixtures (`01-table-horizontal.docx` .. `30-chinese-field-code.docx`) generated deterministically by `synthetic/generate.py` and verified by `synthetic/run_matrix.py` (`Matrix A-synthetic`: `noop` round-trip; `Matrix B-synthetic`: `edited` single-run replacement via `exr_edit_set_run_text`), `synthetic/regressions.py`, `synthetic/oracle_mutations.py`, and `synthetic/test_text_alloc.c`.

## Reproducibility & Verification Commands

```powershell
# Verify deterministic fixture generation for both suites
python tests/fixtures/docx-real/argon/make_fixtures.py --check
python tests/fixtures/docx-real/synthetic/generate.py --check

# Run Matrix A-argon & Matrix B-argon (540/540 each)
python tests/docx/check_realworld_matrix.py --library <workspaces>/exr-build-argon/libexreader.dll --strict

# Run Matrix A-synthetic & Matrix B-synthetic (540/540 each)
python tests/fixtures/docx-real/synthetic/run_matrix.py --library <workspaces>/exr-build-argon/libexreader.dll
```

Full results for all four matrices (`Matrix A-argon`, `Matrix B-argon`, `Matrix A-synthetic`, `Matrix B-synthetic`) are documented in [docs/DOCX-REAL-RESULTS.md](../../../docs/DOCX-REAL-RESULTS.md), and explicit unsupported structure boundaries are documented in [docs/DOCX-LIMITS.md](../../../docs/DOCX-LIMITS.md).
