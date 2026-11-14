# SPDX-License-Identifier: MIT
# From the repository root: pwsh -File examples/windows/run_editor_e2e.ps1
param([string]$BuildDirectory = 'build/l12')
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
Push-Location $root
try {
    & cmake -S . -B $BuildDirectory -G Ninja -DCMAKE_BUILD_TYPE=Release `
        -DEXR_BUILD_TESTS=ON -DEXR_BUILD_TOOLS=OFF `
        -DEXR_ENABLE_PDF=ON -DEXR_ENABLE_AUDIO=OFF -DEXR_ENABLE_LIBRARY=ON `
        -DEXR_ENABLE_PDF_CRYPTO=OFF -DEXR_ENABLE_PDF_JPX=OFF -DEXR_ENABLE_LCP=OFF `
        -DEXR_ENABLE_ICC=OFF -DEXR_ENABLE_MP3=OFF -DEXR_ENABLE_TEXT_INDEX=OFF -DEXR_BUILD_TEXT_INDEX=OFF `
        -DEXR_ENABLE_IMAGE_AVIF=OFF -DEXR_ENABLE_IMAGE_WEBP=OFF -DEXR_ENABLE_IMAGE_TIFF=OFF `
        "-DCMAKE_PROJECT_EXReader_INCLUDE=$PSScriptRoot/editor_e2e_tests.cmake"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & cmake --build $BuildDirectory --target check_shell_editor_e2e --parallel 4
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & ctest --test-dir $BuildDirectory -R '^native-shell-editor-e2e$' --no-tests=error -V
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
