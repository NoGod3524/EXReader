param(
    [Parameter(Mandatory)] [string] $Output,
    [string] $Dependencies = 'C:/Users/Oscar/exr-deps-cache'
)
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true
$repo = (Resolve-Path "$PSScriptRoot/../..").Path
$baseline = '8c603624f157a53f1d61c6eabaaf211195c89914'
$candidate = git -C $repo rev-parse HEAD
$output = [IO.Path]::GetFullPath($Output)
$source = Join-Path $output 'source'
$build = Join-Path $output 'perf'
New-Item -ItemType Directory -Path $output,"$output/A","$output/B" | Out-Null
git -C $repo worktree add --detach $source $baseline
$components = @('EXPAT','FREETYPE','LCMS','LIBTIFF','LIBWEBP','MBEDTLS','MINIMP3','MINIZ',
                'OPENJPEG','SQLITE','STB','ZLIB')
$flags = $components | ForEach-Object {
    "-DFETCHCONTENT_SOURCE_DIR_${_}=$Dependencies/$($_.ToLower())-src"
}
cmake -S $source -B $build -G Ninja -DCMAKE_BUILD_TYPE=Release -DEXR_ENABLE_IMAGE_AVIF=OFF @flags
cmake --build $build --parallel 6 --target exreader
Copy-Item "$build/libexreader.dll" "$output/A/"
git -C $source restore --source $candidate -- src/vector.c tests/test_vector.c
cmake --build $build --parallel 6
Copy-Item "$build/libexreader.dll" "$output/B/"
python -X utf8 "$PSScriptRoot/run_ab.py" "$output/A/libexreader.dll" "$output/B/libexreader.dll" --output "$output/measure"
git -C $source restore --source $baseline -- src/vector.c tests/test_vector.c
python -X utf8 "$PSScriptRoot/profile.py" $source $build --output "$output/profile"
git -C $source restore --source $candidate -- src/vector.c tests/test_vector.c
ctest --test-dir $build --parallel 4 --output-on-failure --output-junit "$output/ctest.xml"

$vectorSources = @('blend','vector','affine_image','curves','stroke','dash','common','icc') |
    ForEach-Object { "$source/src/$($_).c" }
gcc -O3 -DNDEBUG -DEXR_STATIC -U__SSE2__ -std=c11 "-I$build/generated/include" "-I$source/include" `
    "$source/tests/test_vector.c" @vectorSources -lm -o "$output/vector-scalar.exe"
& "$output/vector-scalar.exe"
