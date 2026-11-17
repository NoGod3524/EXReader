$ErrorActionPreference = 'Stop'
$simdRepo = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../..')).Path
Set-Location -LiteralPath $simdRepo
New-Item -ItemType Directory -Path build -Force | Out-Null
python -c "from pathlib import Path; import ssl; Path('build/pdf-simd-ca.pem').write_text(''.join(ssl.DER_cert_to_PEM_cert(x) for x in ssl.create_default_context().get_ca_certs(binary_form=True)),encoding='ascii')"
$simdArgs = @('-S', '.', '-B', 'build/perf', '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release', '-DEXR_ENABLE_PDF=ON', '-DEXR_ENABLE_PDF_EDIT=ON')
$simdArgs += "-DCMAKE_TLS_CAINFO=$simdRepo/build/pdf-simd-ca.pem"
foreach ($simdDep in @('freetype','expat','miniz','sqlite','stb','libwebp','zlib','libtiff','libaom','libavif','openjpeg','mbedtls','lcms','minimp3')) {
    $simdSource = "$simdRepo/build/deps/$simdDep-src"
    if (!(Test-Path -LiteralPath $simdSource) -and $simdDep -ne 'openjpeg') {
        $simdSource = "$env:USERPROFILE/exr-deps-cache/$simdDep-src"
    }
    if (Test-Path -LiteralPath $simdSource) {
        $simdArgs += "-DFETCHCONTENT_SOURCE_DIR_$($simdDep.ToUpper())=$simdSource"
    }
}
function Run-SimdChecked([string]$Program, [string[]]$Arguments) {
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program exited with $LASTEXITCODE" }
}
Run-SimdChecked cmake $simdArgs
Run-SimdChecked cmake @('--build', 'build/perf', '--parallel', '6')
Run-SimdChecked ctest @('--test-dir','build/perf','--output-on-failure','-j','4','--output-junit',"$PSScriptRoot/ctest.xml")
# Only four implementation files are needed for the ablations. All variants use
# the current private headers and identical remaining objects/dependencies.
$simdBaseline = 'build/pdf-simd-baseline-src/src'
New-Item -ItemType Directory -Path $simdBaseline -Force | Out-Null
foreach ($simdName in @('vector.c','blend.c','canvas.c','affine_image.c')) {
    $simdText = git show "2b24c3ea8:src/$simdName"
    if ($LASTEXITCODE -ne 0) { throw 'Cannot read baseline commit' }
    [IO.File]::WriteAllText("$simdRepo/$simdBaseline/$simdName", ($simdText -join "`n") + "`n")
}
$simdInput = 'tests/fixtures/pdf-hybrid-real/pptx-20.pdf'
foreach ($simdVariant in @('baseline','simd','region')) {
    Run-SimdChecked python @('-X','utf8','tools/profile_pdf_spans.py','--build','build/perf','--baseline-source','build/pdf-simd-baseline-src','--variant',$simdVariant,'--build-only','--input',$simdInput,'--output',"build/pdf-simd-$simdVariant")
}
# Keep this lane's builds and CTest separate from captures. Pin each capture
# process to logical CPU 0 at High priority to reduce competing-lane noise.
foreach ($simdVariant in @('baseline','simd','region','all')) {
    $simdLibrary = if ($simdVariant -eq 'all') { 'build/perf/libexreader.dll' } else { "build/pdf-simd-$simdVariant/variant.dll" }
    Run-SimdChecked python @('-X','utf8','tools/benchmark_pdf_rect.py','capture','--library',$simdLibrary,'--input',$simdInput,'--expect-pages','20','--output',"$PSScriptRoot/$simdVariant",'--widths','600','1200','2400','--runs','5','--cpu-affinity','1','--priority','high')
    if ($simdVariant -ne 'baseline') {
        Run-SimdChecked python @('-X','utf8','tools/benchmark_pdf_rect.py','compare','--before',"$PSScriptRoot/baseline",'--after',"$PSScriptRoot/$simdVariant",'--output',"$PSScriptRoot/diff-$simdVariant")
    }
}
foreach ($simdVariant in @('baseline','all')) {
    Run-SimdChecked python @('-X','utf8','tools/profile_pdf_spans.py','--build','build/perf','--baseline-source','build/pdf-simd-baseline-src','--variant',$simdVariant,'--input',$simdInput,'--output',"build/pdf-simd-profile-$simdVariant",'--cpu-affinity','1','--priority','high')
    Copy-Item -LiteralPath "build/pdf-simd-profile-$simdVariant/profile.json" -Destination "$PSScriptRoot/profile-$simdVariant.json"
}
Run-SimdChecked python @('tools/benchmark_pdf_span_kernels.py','--baseline-source','build/pdf-simd-baseline-src','--output','build/pdf-simd-kernels','--cpu-affinity','1','--priority','high')
Copy-Item -LiteralPath 'build/pdf-simd-kernels/kernels.json' -Destination "$PSScriptRoot/kernels.json"
Run-SimdChecked python @("$PSScriptRoot/summarize.py")
