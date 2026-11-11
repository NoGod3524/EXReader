# Y1 API compatibility acceptance

Main: `6000a89d373db03c3414f13a5ab10eb3d6819ad6`; #112 branch:
`d3119f0e132d7a412e0542f393f876d96c298c97`. Remote heads were checked on
2026-11-10. Implementation is the saved `923f1c6e` commit on
`codex/api-compat-20261110`; this follow-up completes its interrupted validation.
Machine-readable results: [acceptance.json](acceptance.json).

## Public API and shared counters

The original `exr_pager_cache_stats` remains exactly `{ size_t hits, misses; }`.
`exr_pager_cache_stats_legacy` is an alias, so existing source and compiled
callers keep their original return layout and symbol. The extended output is
named **`exr_pager_cache_stats_v1`**, avoiding the occupied main-side type name:

```c
exr_pager_cache_stats old = exr_pager_cache_statistics(pager);
exr_pager_cache_stats_v1 extended = {0};
extended.struct_size = sizeof(extended);
exr_pager_cache_stats_get(pager, &extended, &error);
```

Both getters read `pager->cache_hits` / `pager->cache_misses`. There is no
second set of hit/miss counters. The internal counters are `uint64_t`; the
legacy getter converts to its existing `size_t` fields. `get()` counts all
lookups after argument/mode validation, including a miss that reaches EOF.
Sequential `next()` preserves main's zero hit/miss behavior and increments
only the new requests field for each delivered page. Consequently, requests
equals hits + misses in cached mode, but not in sequential mode.

Both new getters validate the object, output pointer and `struct_size`;
undersized buffers return `EXR_ARGUMENT`. Larger buffers are accepted, the
known prefix is written, `struct_size` reports the written version, and tail
bytes are preserved. No getter resets the counters.

`exr_font_cache_stats_get` is implemented in `src/fonts.c`, backed by
`exr_font::cache_stats` in `src/font_internal.h`. Glyph and shaping lookups,
hits, misses, evictions and shaping bypasses update that instance's counters.

## Every main-side legacy occurrence

Command: `git grep -n exr_pager_cache_statistics 6000a89d -- src examples tests tools include`.
Raw output: [legacy-calls.txt](legacy-calls.txt).

| Main file:line | Role | Validation |
| --- | --- | --- |
| `include/exr/layout.h:506` | Public `EXR_API` declaration: part of public ABI | Original declaration and return type retained |
| `src/pager.c:1796` | Implementation, now line 1800 | Old symbol retained; common counters |
| `tests/test_docx_reflow.c:69` | Actual call in `basic` | Existing reflow test |
| `tests/test_docx_reflow.c:216` | Actual call in `long` | Existing reflow test |
| `tests/test_docx_reflow.c:223` | Actual call in `long` | Existing reflow test |
| `tools/reflow_baseline.py:38` | String in export filtering, not a call | No source modification |

There are no legacy occurrences in `examples/`. No `src/docx_*.c` files were
modified. All twelve existing `native-reflow-*` scenarios are retained.
An additional consumer was rebuilt against **unchanged main headers** and
linked/run against the candidate DLL: [legacy_consumer.c](legacy_consumer.c),
[legacy-consumer.txt](legacy-consumer.txt). Header identity is recorded in
[verification-context.json](verification-context.json).

## Performance extraction review

Seven review units cover #112's OpenType changes; some were already in main:

| Area in `src/opentype.c` | Classification | Integrated result |
| --- | --- | --- |
| `ot_shape_key` and `ot_cached_shape` | Performance | Retain main's existing context-aware key and exact UTF-8 comparison |
| `exr_ot_state::shapes` and cache bounds | Performance | 1024 direct slots → 8192 entries, four ways per set |
| `shape_key` / `shape_hash` | Performance / correctness | Retain eligibility limits and Arabic joining equivalence classes; feature/progress paths bypass |
| `shape_cached` | Performance | Search four ways and move hits to MRU position |
| `shape_remember` | Performance plus telemetry | Bounded MRU insertion; shared font counter records eviction; font argument remains internal |
| `exr_ot_free` | Lifetime / correctness | Retain main's existing release of every cached shape |
| `shape()` entry and success exit | Performance plus telemetry | Retain fast path and result ownership; add font hit/miss/request/bypass accounting and updated internal remember call |

`src/opentype.c` contains no new public API declaration. The public getter is
implemented in `src/fonts.c`. The glyph cache retains main's existing raster
path with #112's 2 MiB budget and telemetry. No new internal header was added,
so `tools/layers.json` needs no new entry; the compiled layer check is in
[layers.txt](layers.txt).

`bench_batch` is built and installed by the root CMake project. The standalone
SDK examples project also includes it. Its warmup helper uses existing public
APIs inside the example, keeping new engine exports limited to the two getters.
See [bench_batch.md](../../examples/bench_batch.md).

## Acceptance evidence

| Requirement | Result | Evidence |
| --- | --- | --- |
| Frozen documentation ABI | **389 → 456; missing 0** | [docs-389-exports.json](docs-389-exports.json) |
| Current machine-readable ABI contract | **394/394 retained**, missing 0 | [candidate-exports.json](candidate-exports.json) |
| Every current main export | **454 → 456; missing 0**, only two getters added | [main-export-diff.json](main-export-diff.json) |
| Pager / font API checks | Pager compatibility 187 checks; full shaping suite 297,036 checks; both API test executables pass | [cache-stats-test.txt](cache-stats-test.txt), [shaping-test.txt](shaping-test.txt) |
| Same-source counters | 10 pages, two passes: **requests=20; legacy/new hits=10, misses=10** | [cache-stats-test.txt](cache-stats-test.txt) |
| Unchanged-header consumer | Cached 10/10; sequential 0/0; NULL 0/0 | [legacy-consumer.txt](legacy-consumer.txt) |
| Real books | **19/19**, **11,318 pages**; changed page counts 0, changed pixel hashes 0 | [after-realbooks.diff.json](after-realbooks.diff.json), [after-realbooks.json](after-realbooks.json) |
| Benchmark | Compiled and executed, **5 runs × 20 turns**, warmup 21; glyph hits 100%, shaping hits 99.6646% | [bench-batch-final.txt](bench-batch-final.txt), [bench-batch-final.json](bench-batch-final.json), [bench-command.json](bench-command.json) |
| Installed SDK benchmark consumer | CMake install completed with provenance manifest; separate `exreader-bench_batch-example` target compiled and linked; `--self-test` passed, DLL identical to candidate | [sdk-consumer.json](sdk-consumer.json), [sdk-consumer.txt](sdk-consumer.txt) |
| Test inventory | Actual main build **275**, candidate **277**, removed **0**, added **2** | [test-inventory-diff.json](test-inventory-diff.json) |
| Final single full CTest | **277/277 passed**, failures **0**, **83.78 s**; original test limits and assertions retained | [candidate-ctest-priority.txt](candidate-ctest-priority.txt) |
| Full CTest plus isolated retry | 276 passed in the concurrent full run; `sdk-release` timed out, then passed alone in 111.88 s; all 277 have passing results | [candidate-ctest-final.txt](candidate-ctest-final.txt), [candidate-ctest-retry.txt](candidate-ctest-retry.txt) |

The five benchmark p95 values were 40.7809, 305.9087, 183.1783, 87.2594 and
545.5203 ms. Exit status was 0; the benchmark's own 16 ms / dispersion gate
reports `passes=false`. This verifies compilation, execution and telemetry;
these measurements do not establish that performance gate as passed.

The requested baseline number 281 does not match the 275 tests registered by
this main revision and build configuration. The complete name comparison
shows no test removed. Optional WebP/TIFF/AVIF codecs and JNI are disabled in
both builds; exact configuration is in [build-options.txt](build-options.txt).
The existing editing tests use the configured external X1 model source without
modifying or copying its source into this branch.

The frozen 389-symbol list is extracted from `docs/ABI.md`; today's
`tools/abi/contract.json` contains 394 symbols. Both sets were checked. Extra
symbols are allowed for this additive compatibility check; the count does not
claim equality with the old set.

The first full CTest runs failed only `sdk-release`: its Windows README uses
`cl ... lib/exreader.lib`, while the MinGW build generated only
`libexreader.dll.a`. [prepare-msvc-import.ps1](prepare-msvc-import.ps1) uses
MSVC `lib.exe` and the build's real export definition to produce an import
library for the **same** `libexreader.dll` under `build/y1/*/Release/`.
The package collector already searches that directory. This is a local build
preparation step; release scripts and product sources are unchanged. The
release test then compiles and executes the original README commands.
Initial failures are preserved in [candidate-ctest.txt](candidate-ctest.txt)
and [baseline-ctest.txt](baseline-ctest.txt); the isolated retry is in
[release-retest.txt](release-retest.txt).
The concurrent intermediate run hit the same test's unchanged 180 s timeout; an
isolated retry passed in 111.88 s. A subsequent serial full run keeps that
timeout unchanged and avoids overlap between the release smoke and other
tests; its release smoke passed in 158.74 s. That serial run later hit the
existing 60 s corpus-triage and 30 s fuzz-pipeline subprocess timeouts; its
complete log remains in [candidate-ctest-serial.txt](candidate-ctest-serial.txt).

The final full run used [run-ctest.ps1](run-ctest.ps1) to give only this CTest
process tree **AboveNormal** Windows scheduling priority. The helper exits
when CTest exits; it changes no machine-wide setting, test command, assertion,
CPU budget or wall-clock timeout. This final run passed **277/277 in 83.78 s**,
including release smoke (19.12 s), corpus triage and fuzz pipelines. It used
the same DLL as the earlier runs and real-book comparison.

## Reproduce in the prepared checkout

```powershell
cmake -S . -B build/y1/candidate
cmake --build build/y1/candidate --target bench_batch exreader-cache-stats-test exreader-shaping-test -j 4
./evidence/y1-api-20261110/prepare-msvc-import.ps1
./evidence/y1-api-20261110/run-ctest.ps1
python tools/abi/check_exports.py build/y1/candidate/libexreader.dll --contract evidence/y1-api-20261110/docs-389-contract.json --allow-extra
python tools/abi/check_exports.py build/y1/candidate/libexreader.dll --allow-extra
python tools/check_layers.py build/y1/candidate
gcc -std=c11 -Wall -Wextra -Wpedantic -Werror -I build/y1/baseline-source/include -I build/y1/baseline/generated/include evidence/y1-api-20261110/legacy_consumer.c -L build/y1/candidate -lexreader -o build/y1/candidate/legacy_consumer.exe
build/y1/candidate/legacy_consumer.exe tests/fixtures/shaping/shaping.ttf
python tools/regress/run_realbooks.py --manifest tools/regress/corpus.json --dll build/y1/candidate/libexreader.dll --font C:/Users/Oscar/exr-deps/reader-font/Reader.otf --layout tools/regress/layout.json --source-revision 923f1c6eaa1a18bb6bc4bdd05cc3ca6ca2d31efe --output build/y1/realbooks-repeat.json --baseline evidence/y1-api-20261110/before-realbooks.json --workers 4
```

The before-book DLL is `build/y1/main-readonly.dll` (SHA-256
`6cca81e687713a4b3fb7e3b97812d41793aeaa2e8348580a3b5501a8791818c2`),
matching [before-realbooks.json](before-realbooks.json). Source, font and
candidate DLL identities are recorded in
[verification-context.json](verification-context.json).
