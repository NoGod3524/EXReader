# Main workflow cost and version scan scope

Measured on 2026-11-05 America/New_York against main `f22a764979ff14b23b407a438a4387c5eeae6434`.

## Main trigger count

**11 workflows can automatically trigger on main / 256 workflow files.** Count push and pull_request only when branches is absent or admits main; honor branches-ignore. Path filters are preserved and do not remove a workflow from this branch-level potential count. Ten are unfiltered by branch, one explicitly includes main. No workflow trigger or file changes are needed to meet the <=15 criterion. The <=40 file-count criterion was withdrawn.

| Workflow | Event / branch reason |
|---|---|
| `.github/workflows/bounded-library.yml` | pull_request: unfiltered |
| `.github/workflows/f07-authoritative-symbols-20261103.yml` | push: unfiltered |
| `.github/workflows/native.yml` | pull_request: unfiltered |
| `.github/workflows/reader-catalog-android.yml` | pull_request: unfiltered |
| `.github/workflows/reader-catalog-apple.yml` | pull_request: unfiltered |
| `.github/workflows/reader-catalog-native.yml` | pull_request: unfiltered |
| `.github/workflows/reader-modules.yml` | pull_request: unfiltered |
| `.github/workflows/reading-core.yml` | pull_request: unfiltered |
| `.github/workflows/reading-licenses.yml` | pull_request: unfiltered |
| `.github/workflows/reading-required-core.yml` | pull_request: main matches branch filter |
| `.github/workflows/sdk-version-consistency.yml` | pull_request: unfiltered |

## Assertion-bound workflows kept byte-identical

Seven assertion groups cover 13 current workflow targets. Each complete workflow blob and on block matches main; all 256 workflow blobs match main. native.yml, reliability.yml and reusable workflow definitions are unchanged.

| Assertion source | Workflow | on unchanged |
|---|---|---|
| `tests/reader_next_s14/guard.py:79` | `.github/workflows/reader-next-s14.yml` | yes |
| `tests/reader_apple_records_ready/guard.py:37` | `.github/workflows/reader-apple-records-ready.yml` | yes |
| `tests/reader_perf_protocol/check.py:44` | `.github/workflows/reader-composition-perf-gtk.yml` | yes |
| `tests/reader_perf_protocol/check.py:44` | `.github/workflows/reader-composition-perf-windows.yml` | yes |
| `tests/apple_host/page_theme/guard.py:81` | `.github/workflows/reader-apple-navigation.yml` | yes |
| `tests/apple_host/page_theme/guard.py:81` | `.github/workflows/reader-apple-search.yml` | yes |
| `tests/apple_host/page_theme/guard.py:81` | `.github/workflows/reader-apple-reading-records.yml` | yes |
| `tests/apple_host/page_theme/guard.py:81` | `.github/workflows/reader-apple-shelf.yml` | yes |
| `tests/apple_host/page_theme/guard.py:81` | `.github/workflows/reader-apple-import-mapping.yml` | yes |
| `tests/apple_host/page_theme/guard.py:81` | `.github/workflows/wp13-apple.yml` | yes |
| `tests/apple_host/page_theme/simulator_ready.py:28` | `.github/workflows/reader-apple-simulator-ready.yml` | yes |
| `tests/reader_apple_records_ready/raw3_guard.py:54` | `.github/workflows/reader-apple-raw3-ios-ready.yml` | yes |
| `tools/check_version_consistency.py:56` | `.github/workflows/reader-apple-record-compatibility.yml` | yes |

Complete blob IDs and on-block SHA256 values are recorded in RESULT.json.

## Scanner scope

`tools/check_version_consistency.py` excludes `archive/**` by path: historical snapshots are evidence, not current SDK consumers. Current source scanning and the existing literal/evidence rules remain enforced. No per-file or literal waiver was added; tools/version_literal_exceptions.json is byte-identical.

| Distribution | Count |
|---|---:|
| Historical archive files excluded | 34655 |
| Archive CMake consumer files formerly considered | 4208 |
| Current files scanned | 1605 |
| Current CMake consumer files | 191 |
| Current workflow files | 256 |
| Current test files | 1158 |
| Historical mismatches removed from the active scan | 27 |
| Current scan errors | 0 |
| New literal waivers | 0 |

The 27 historical mismatches consist of 14 at 3.41.0 and 13 at 3.40.0. Existing exact registrations remain 587: frozen_baseline 530, migration_compat 7, negative_case 50.

## Local validation

- --sync-generated passes; generated header and README are byte-identical. SDK 3.42.0 and ABI 1 are unchanged.
- Existing stale-line, changed-literal, frozen-object, migration-reference/removal, rejection-assertion and duplicate controls all reject invalid evidence.
- A historical CMake consumer placed under archive is excluded; the identical bytes under tests are rejected.
- --self-test still rejects root project-version drift and current corpus-consumer drift.
- Full output is in VERSION-VALIDATION.txt. Current-head CI is recorded in PR #46; the preceding custody head passed core run 42125571749.
