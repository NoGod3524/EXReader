# Local memory and undefined-behavior audit

This wrapper builds the unchanged engine and its C dependencies with Clang ASan,
UBSan and LLVM source coverage. `driver.c` includes the existing
`tools/check_document.c` all-page probe, adding numeric stage/page context and
successful render counts by writing mode. It uses the probe's 720 × 1040 layout,
CSS, embedded fonts, and fixed-page maximum dimension 720.

## Windows prerequisites and reproduction

Python 3.11+, CMake, Ninja, LLVM with clang-cl/lld-link/compiler-rt/coverage tools,
Visual Studio Build Tools and Windows SDK are required. The defaults in
`build.py` match the measured host. Override `LLVM_ROOT`, `EXR_MSVC`,
`EXR_WINSDK`, `EXR_WINSDK_VERSION`, `EXR_DEPS`, `EXR_OPENJPEG` as necessary.
The dependency directories must contain the versions pinned in `cmake/deps.cmake`.
Use a fresh build directory: stale CMake probe results from Debug CRT builds
are incompatible with ASan. `CMAKE_TRY_COMPILE_CONFIGURATION=RelWithDebInfo`
keeps dependency feature probes on the supported release CRT.

```powershell
$auditBuild = 'C:/Users/Oscar/Documents/Codex/sanitize-measured-build-20261107'
$auditWork = 'C:/Users/Oscar/Documents/Codex/sanitize-measured-work-20261107'
python tools/sanitize/build.py $auditBuild
python tools/sanitize/run.py controls --build $auditBuild --work $auditWork
python tools/sanitize/run.py books --build $auditBuild --work $auditWork --workers 4
python tools/sanitize/run.py malformed --build $auditBuild --work $auditWork --workers 4
python tools/sanitize/run.py seeds --build $auditBuild --work $auditWork --workers 4
python tools/sanitize/collect.py --build $auditBuild --work $auditWork
```

The font defaults to `C:/Windows/Fonts/msyh.ttc`; use `--font` to override it.
Book paths and expected SHA-256 values come from `tools/regress/corpus.json`.
Books are opened read-only and hashes are verified before and after the run.
Raw stdout/stderr and `.profraw`/`.profdata` remain in the external work directory.
Malformed EPUBs are generated temporarily from the original baseline using
`tools/compat/malformed_corpus.py`, then deleted. The 200 cases use 25 evenly
spaced original indices (1 through 128) in each of its eight categories.

The seed group replays the existing four-pipeline `CORPUS` list from
`tools/run_reliability_campaign.py`, plus `tests/fixtures/fuzz-cbz-truncated.bin`.
It does not generate random mutations. These are checked-in synthetic fixtures;
there are no standalone crash-input binaries under `tools/`.

To reproduce one finding, select the reported input ID; use a separate output
directory to preserve the original campaign evidence:

```powershell
python tools/sanitize/run.py books --case BOOK_ID --build $auditBuild --work $auditWork --output "$auditWork/replay"
python tools/sanitize/run.py malformed --case CATEGORY-NNN --build $auditBuild --work $auditWork --output "$auditWork/replay"
python tools/sanitize/run.py seeds --case SEED_ID --build $auditBuild --work $auditWork --output "$auditWork/replay"
```

ASan stops the affected process at its first error; UBSan retains the compiler's
default recovery behavior so later pages can be measured. The runner records
aborts, timeouts, completion, and successful page totals separately. Positive
controls and reproduction runs are excluded from the three-group coverage merge.
`collect.py` merges only profiles in `books/`, `malformed/`, and `seeds/`; use a
fresh work directory for a new campaign. Summary-only coverage exports contain
file paths and counters, no book text or source text.

No suppressions or sanitizer ignorelists are installed. Windows ASan does not
provide LeakSanitizer; this audit measures ASan address errors and UBSan findings,
not leak coverage. See [Clang ASan documentation](https://clang.llvm.org/docs/AddressSanitizer.html)
and [LLVM source coverage](https://clang.llvm.org/docs/SourceBasedCodeCoverage.html).
