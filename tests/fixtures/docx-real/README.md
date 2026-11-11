# Real-World DOCX Structural Fixture Suites (`argon` & `codex`)

This directory contains two complementary, independently authored 30-document DOCX structural fixture suites (60 `.docx` fixtures total, all original and MIT-licensed, each `< 60 KB`):

- **`argon/`** (PR #132): 30 structural `.docx` fixtures (`01-table-merged-grid-vmerge.docx` .. `30-other-header-table-chinese-fields.docx`) generated deterministically by `argon/make_fixtures.py` and verified by `tests/docx/check_realworld_matrix.py` (`Matrix A-argon`: read → model → write; `Matrix B-argon`: read → paragraph/table edit + undo/redo → write).
- **`codex/`** (PR #126): 30 mixed `.docx` fixtures (`01-table-horizontal.docx` .. `30-chinese-field-code.docx`) generated deterministically by `codex/generate.py` and verified by `codex/run_matrix.py` (`Matrix A-codex`: `noop` round-trip; `Matrix B-codex`: `edited` single-run replacement via `exr_edit_set_run_text`), `codex/regressions.py`, `codex/oracle_mutations.py`, and `codex/test_text_alloc.c`.

## Reproducibility & Verification Commands

```powershell
# Verify deterministic fixture generation for both suites
python tests/fixtures/docx-real/argon/make_fixtures.py --check
python tests/fixtures/docx-real/codex/generate.py --check

# Run Matrix A-argon & Matrix B-argon (540/540 each)
python tests/docx/check_realworld_matrix.py --library C:/Users/Oscar/Documents/Codex/exr-build-argon/libexreader.dll --strict

# Run Matrix A-codex & Matrix B-codex (540/540 each)
python tests/fixtures/docx-real/codex/run_matrix.py --library C:/Users/Oscar/Documents/Codex/exr-build-argon/libexreader.dll
```

Full results for all four matrices (`Matrix A-argon`, `Matrix B-argon`, `Matrix A-codex`, `Matrix B-codex`) are documented in [docs/DOCX-REAL-RESULTS.md](../../../docs/DOCX-REAL-RESULTS.md), and explicit unsupported structure boundaries are documented in [docs/DOCX-LIMITS.md](../../../docs/DOCX-LIMITS.md).
