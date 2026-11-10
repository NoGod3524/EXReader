# Local sanitizer audit

The wrapper includes the existing `tools/check_document.c` probe and builds the
unchanged engine, dependencies, and four existing fuzz drivers. Every book page
is paginated and rendered at 720 × 1040; fixed pages use the probe's maximum
dimension of 720. No page limit is set. Diagnostic context records the zero-based
spine part and page within the part, plus the number of completed renders.

## Windows reproduction

Requirements: Python 3.11+, CMake, Ninja, LLVM (clang-cl, lld-link, compiler-rt,
llvm-cov, llvm-profdata, llvm-symbolizer), Visual Studio Build Tools and Windows
SDK. `build.py` defaults match the measured machine. Override `LLVM_ROOT`,
`EXR_MSVC`, `EXR_WINSDK`, `EXR_WINSDK_VERSION`, `EXR_DEPS`, and `EXR_OPENJPEG`
for another machine. Dependencies must match `cmake/deps.cmake`.

```powershell
$auditBuild = 'C:/Users/Oscar/Documents/Codex/sanitize-current-build-20261108'
$auditWork = 'C:/Users/Oscar/Documents/Codex/sanitize-current-work-20261108'
python tools/sanitize/build.py $auditBuild
python tools/sanitize/run.py controls --build $auditBuild --work $auditWork
python tools/sanitize/run.py books --build $auditBuild --work $auditWork --workers 4
python tools/sanitize/run.py malformed --build $auditBuild --work $auditWork --workers 4
python tools/sanitize/run.py seeds --build $auditBuild --work $auditWork --workers 4
python tools/sanitize/collect.py --build $auditBuild --work $auditWork
python tools/sanitize/check.py evidence/sanitize-20261107
```

Choose fresh build/work directories and use `--output` for a new campaign;
existing evidence is never overwritten by `run.py`. Raw output, temporary book
variants, and coverage profiles stay outside the repository. Book SHA-256 hashes
are verified before and after reading. The font defaults to
`C:/Windows/Fonts/msyh.ttc`; override with `--font`.

Instrumentation:

```text
-fsanitize=address,undefined /clang:-fno-omit-frame-pointer
/clang:-fno-optimize-sibling-calls -fprofile-instr-generate -fcoverage-mapping
/clang:-fno-sanitize-ignorelist
```

`clang-cl` requires `/clang:` for these frame/stack options; the bare
`-fno-omit-frame-pointer` is ignored by this driver. Release CRT and
`CMAKE_TRY_COMPILE_CONFIGURATION=RelWithDebInfo` are used for dependency probes.
Both intentional-fault controls must report symbolized stacks before the scan.
ASan stops at its first error. UBSan uses recovery so subsequent pages can run.
No sanitizer suppressions or ignorelists are applied. The flag above also removes
LLVM's default Windows C++ `_Find_elem` exclusion. Optional AVIF, TIFF, and
WebP decoders are disabled in this build; PNG, JPEG, JPX, ICC and PDF crypto are
enabled. Windows LeakSanitizer is outside the measured coverage.

## Inputs and findings

The 19 original inputs and hashes come from `tools/regress/corpus.json`.
The malformed group calls `tools/compat/malformed_corpus.py` unchanged: 25 evenly
spaced indices across 1–128 in each of eight categories, 200 unique variants.
The original body-containing variants are not checked in.

`tools/` has no standalone crash-input binaries. The seed group replays the
24 entries in the existing `tools/run_reliability_campaign.py` four-pipeline
`CORPUS`, plus `tests/fixtures/fuzz-cbz-truncated.bin`. Repeated fixture bytes
across different pipelines count as separate seed executions.

Replay one reported input using its ID:

```powershell
python tools/sanitize/run.py books --case BOOK_ID --build $auditBuild --work $auditWork --output "$auditWork/replay-book"
python tools/sanitize/run.py malformed --case CATEGORY-NNN --build $auditBuild --work $auditWork --output "$auditWork/replay-variant"
python tools/sanitize/run.py seeds --case SEED_ID --build $auditBuild --work $auditWork --output "$auditWork/replay-seed"
```

Diagnostic records retain the location, stack, and last numeric page context.
They exclude engine error text and memory dumps. Reports group diagnostics by
root cause and distinguish engine defects, library defects, and false positives.
Controls and replays are excluded from the three-group coverage merge. Crashes
and timeouts are accounted for separately from successful page completion.

`collect.py` exports only numeric file coverage and provenance. The denominator
is executable source lines in linked instrumentation, with separate `src/`
totals and vendor-inclusive totals. Disabled code is not in that denominator;
this is measured path coverage, not a claim about every build configuration.

References: [Clang ASan](https://clang.llvm.org/docs/AddressSanitizer.html),
[UBSan](https://clang.llvm.org/docs/UndefinedBehaviorSanitizer.html),
[LLVM source coverage](https://clang.llvm.org/docs/SourceBasedCodeCoverage.html).
