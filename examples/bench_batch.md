# SDK batch benchmark

`bench_batch.c` is a standalone C11 SDK consumer for EPUB, MOBI/KF8 and FB2
publications. It uses public SDK headers and synchronous `exr_pager_next()` plus
`exr_render_page_color()` calls.

## Build

From a configured repository build with `EXR_BUILD_TOOLS=ON`:

```powershell
cmake --build build/s1-after --target bench_batch
```

To compile the example independently against an existing MinGW shared SDK build:

```powershell
gcc -std=c11 -O3 -Wall -Wextra -Wpedantic -Werror `
  -I include -I build/s1-after/generated/include examples/bench_batch.c `
  -L build/s1-after -lexreader -lshell32 -o build/s1-after/bench_batch.exe
```

Keep `libexreader.dll` beside the executable. `entry.h`, beside the source,
converts Windows arguments to UTF-8, including Chinese book paths. Define
`EXR_BENCH_BASELINE` when compiling against an older SDK without the new telemetry
and warmup APIs; the timed calls stay identical, cache output becomes `null`, and
nonzero `--warmup` is rejected.

For an installed SDK, build the supplied examples as a separate CMake project:

```powershell
cmake -S C:/path/to/sdk/examples -B build/consumer -G Ninja `
  -DEXR_SDK=C:/path/to/sdk -DCMAKE_BUILD_TYPE=Release
cmake --build build/consumer --target exreader-bench_batch-example
```

The target produces `bench_batch` (`bench_batch.exe` on Windows). CMake copies the
Windows SDK DLL beside the executable. The repository target also installs the
program to the SDK's `bin` directory.

## Run

```powershell
build/s1-after/bench_batch.exe BOOK.epub FONT.otf --runs 5 --turns 20 `
  --cpu 3 --high-priority --json cold.json
build/s1-after/bench_batch.exe BOOK.epub FONT.otf --runs 5 --turns 20 `
  --warmup 21 --cpu 3 --high-priority --json warm.json
```

Use identical book, font, layout and scheduling options for the two commands.
`--cpu` and `--high-priority` are optional Windows process-local controls; the
default leaves scheduling unchanged. On other systems use platform controls
such as `taskset` externally if needed. `--json -` emits only JSON to stdout.

Defaults are width **1552**, height **928**, margin **48**, font size **24**, line
height **1.5**, paragraph spacing **10**, **5 runs**, **20 turns**, and **0 warmup
pages**. Layout overrides are `--width`, `--height`, `--margin`, `--font-size`,
`--line-height`, and `--paragraph-spacing`.

Each run opens a fresh font and publication. It renders the first page and
reports it separately, then measures all 20 consecutive turns across publication
parts. No turns or runs are retried or removed. Each sample includes part/page
indices, layout time, render time, their total, and glyph/shaping/layout cache
counts. The terminal prints all 20 totals; JSON retains every sample and the
first page. Publication/font opening, part loading and pager creation are
reported as `setup_ms` and `part_setup_ms` outside the page-call timer. Warmup is
reported separately as `warmup_ms`.

Percentiles use nearest rank: sort the 20 total times and take item 10 for p50
and item 19 for p95 (one-based). Across five run p95 values, dispersion is
`100 * (maximum - minimum) / mean`. JSON `passes` requires at least 5 runs and 20
turns, every run p95 at most 16 ms, and dispersion strictly below 10%. The program
returns nonzero for execution or output errors; timing failure is reported in
the output, not its exit code.

## Warmup and cache counts

```c
exr_publication_warmup(publication, font, &config, pages, &error);
```

Reuse the same font and configuration afterward. Warmup shapes and rasterizes
the first N pages synchronously; it does not retain page bitmaps or change a
reading cursor. Twenty turns follow one initial page, so `--warmup 21` covers
that full prefix. Caches remain bounded and can evict entries. Embedded CSS
font sets belong to temporary pagers and are released afterward; the supplied
font stays warm only where it is the effective layout font. Retain a pager and
use its cached `get()` mode when preparing pages that use embedded fonts.

Cache results are per-page counter differences, aggregated over the measured
turns. Shaping bypasses are reported separately from eligible cache lookups.
The sequential `next()` path does not reuse cached layouts, so successful pages
count as layout misses; a zero layout hit rate is expected for this benchmark.
`--self-test` checks the percentile calculation and integer argument validation.

## Controlled Windows session

The optional wrapper temporarily sets the active scheme's AC processor minimum
and maximum to 100% and disables boost, following `tools/perf/fixed_clock.ps1`.
It requires AC power, saves the original scheme GUID and settings, and restores
and verifies them in `finally`, including when a benchmark fails.

```powershell
pwsh -File tools/perf/batch_session.ps1 `
  -Binary build/s1-after/bench_batch.exe -Reference build/s1-before/bench_batch.exe `
  -Book BOOK.epub -Font FONT.otf -Output evidence/sdk-batch-20261109/session-1 `
  -Cpu 3 -Runs 5 -Turns 20 -Warmup 21
```

The output directory must be new. The optional reference runs first, followed
by the candidate's cold and warm batches, each with exactly five runs and no
retries. The directory retains their JSON/text outputs, three-sample preflight
and postflight measurements, requested/applied/original/restored power settings,
and every `powercfg` command. The telemetry includes observed CPU-frequency
counters alongside the timing sequences. Power settings are restored before
postflight telemetry, whose system queries can take longer than the sample interval.
