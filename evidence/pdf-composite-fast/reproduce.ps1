# Requires the handoff's Release Ninja build/perf (PDF and PDF editing enabled).
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true
$compositeRepo = (Resolve-Path -LiteralPath "$PSScriptRoot/../..").Path
Set-Location -LiteralPath $compositeRepo
$compositeBaseline = 'b9f4d5c9b0aef7ed5798b594beaa8450969219c7'
$compositeInput = 'tests/fixtures/pdf-hybrid-real/pptx-20.pdf'
$compositeEvidence = 'evidence/pdf-composite-fast'
$compositeProfiler = "$compositeEvidence/profile_composite.py"

cmake --build build/perf --parallel 6
# Only blend.c/vector.c differ in production. Restore baseline source copies and
# relink them with the unchanged objects and identical Ninja compiler/link flags.
python $compositeProfiler --revision $compositeBaseline --plain --output build/pdf-composite-fast/head-baseline
python tools/benchmark_pdf_rect.py capture --library build/pdf-composite-fast/head-baseline/libexreader.dll --input $compositeInput --expect-pages 20 --runs 9 --output "$compositeEvidence/head-before"
python tools/benchmark_pdf_rect.py capture --library build/perf/libexreader.dll --input $compositeInput --expect-pages 20 --runs 9 --output "$compositeEvidence/after"
python tools/benchmark_pdf_rect.py compare --before "$compositeEvidence/head-before" --after "$compositeEvidence/after" --output "$compositeEvidence/head-diff"
python tools/benchmark_pdf_composite.py --before build/pdf-composite-fast/head-baseline/libexreader.dll --after build/perf/libexreader.dll --input $compositeInput --runs 20 --output "$compositeEvidence/fresh-process.json"

python $compositeProfiler --revision $compositeBaseline --output build/pdf-composite-fast/profile-head-before
python $compositeProfiler --output build/pdf-composite-fast/profile-after
foreach ($compositeWidth in @(1200,2400)) {
    python $compositeProfiler --library build/pdf-composite-fast/profile-head-before/libexreader.dll --width $compositeWidth --output "$compositeEvidence/profile-head-before-$compositeWidth.json"
    python $compositeProfiler --library build/pdf-composite-fast/profile-after/libexreader.dll --width $compositeWidth --output "$compositeEvidence/profile-after-$compositeWidth.json"
}
python tools/generate_package_sbom.py
ctest --test-dir build/perf --output-on-failure --parallel 6 --output-junit ../../evidence/pdf-composite-fast/ctest-final.xml
