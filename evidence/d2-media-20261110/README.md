# D2 EPUB media acceptance — 2026-11-10

Candidate source: `c60951f0`; baseline source: `6000a89d`. The candidate DLL was rebuilt from the saved source, rather than reusing Claude's older DLL. DLL, font, layout, source and protected-file hashes are in [inputs-sha256.csv](inputs-sha256.csv).

## Reproduction

From the repository root, using the existing sibling build directory:

```powershell
cmake --build ../d2m-build -j 4
ctest --test-dir ../d2m-build --output-on-failure -j 2
ctest --test-dir ../d2m-build -R '^native-media-epub-' -V
python tools/regress/run_realbooks.py --manifest tools/regress/corpus.json --dll ../d2m-build/libexreader.dll --font C:/Windows/Fonts/NotoSerifSC-VF.ttf --layout tools/regress/layout.json --output evidence/d2-media-20261110/real-final.json --baseline evidence/d2-media-20261110/real-before.json --workers 3 --source-revision c60951f0
python tools/regress/run_realbooks.py --baseline evidence/d2-media-20261110/real-before.json --candidate evidence/d2-media-20261110/real-final.json --output evidence/d2-media-20261110/real-final-verified.diff.json
python tests/media_corpus/media_report.py ../d2m-build/libexreader.dll C:/Windows/Fonts/NotoSerifSC-VF.ttf tools/regress/layout.json evidence/d2-media-20261110/media-final evidence/d2-media-20261110/corpus/media-av.epub evidence/d2-media-20261110/corpus/media-cover-bgm.epub evidence/d2-media-20261110/corpus/media-legacy.epub evidence/d2-media-20261110/corpus/media-smil.epub
python tools/check_layers.py ../d2m-build
```

The four synthetic EPUBs are included under [corpus](corpus/); their generator remains [build_corpus.py](../../tests/media_corpus/build_corpus.py). Recreating them requires ffmpeg and Pillow. Real books and fonts remain at their original locations and are not bundled.

## Final evidence

| Sample | Parts | Pages | Media items | SMIL overlays / clips |
| --- | ---: | ---: | ---: | ---: |
| media-av.epub | 1 | 1 | 3 | 0 / 0 |
| media-cover-bgm.epub | 2 | 2 | 2 | 0 / 0 |
| media-legacy.epub | 1 | 2 | 6 | 0 / 0 |
| media-smil.epub | 2 | 2 | 0 | 2 / 6 |
| 草枕 (real book) | 16 | 464 | 0 | 2 / 439 |

- [Build transcript](build-final.txt), [full ctest transcript](ctest-final.txt), [four media tests](media-ctest.txt), [chapter-index regression](chapter-index.txt), [layer audit](layers.txt).
- Full ctest initially passed 257/260. The two silent failures (`native-library-stream`, `native-publication-index-boundaries`) passed a [serial retry](ctest-rerun-failed.txt); their initial root cause remains unresolved. `sdk-release` then passed its [final retry](ctest-sdk-final.txt) after generating the MSVC import library described below. Every test has a passing result; this was not a single 260/260 full-suite run.
- [Synthetic recognition and mapping report](media-final/media-report.json); [seven rendered screenshots](media-final/), including [audio/video](media-final/media-av-part0-p0.png), [cover video](media-final/media-cover-bgm-part0-p0.png), [background music](media-final/media-cover-bgm-part1-p0.png), and [legacy/missing media](media-final/media-legacy-part0-p0.png).
- [草枕 SMIL report](kusamakura/media-report.json), [overlay totals](kusamakura-overlays.csv). Both SMILs resolve all 439 text fragments and audio resources; `missing_audio=0`, `unresolved_text=0`. The report contains individual UTF-8 text ranges and millisecond audio intervals.
- [19-book baseline](real-before.json), [final render](real-final.json), [comparison](real-final-verified.diff.json), [comparison stdout](real-compare.txt), [per-book table](books-table.csv). All 11,426 pages retain their page counts and pixel hashes; 8,648,571 glyphs are unchanged.
- [Configuration and original missing-header diagnostic](configuration.txt); MP3 and AAC decoding remain OFF in both builds. The media metadata probes work independently of those decoders.
- [Frozen checker SHA-256](release-checker-sha256.txt): `6eb22a304686b2160d1f283a709936bfdfd65c3b0f5e10bb060f457c4faffb2b`.

## Windows SDK environment preparation

The original MinGW package contained `libexreader.dll.a`; the README's MSVC example requires `exreader.lib`. No packaging source was changed. We generated an MSVC import library from the current DLL's generated export list, prepending `LIBRARY libexreader.dll`; the exact input is [msvc-compat.def](msvc-compat.def) and the tool transcript is [msvc-import.txt](msvc-import.txt).

```powershell
New-Item -ItemType Directory -Force ../d2m-build/Release
& 'C:/Program Files (x86)/Microsoft Visual Studio/2022/BuildTools/VC/Tools/MSVC/14.44.35207/bin/Hostx64/x64/lib.exe' /nologo /def:evidence/d2-media-20261110/msvc-compat.def /machine:x64 /out:../d2m-build/Release/exreader.lib
ctest --test-dir ../d2m-build -R '^sdk-release$' --output-on-failure
```

This step is required to reproduce the successful SDK smoke with this MinGW build. Regenerate the definition and import library if exports change. [Final smoke report](sdk-smoke/smoke.json) records all three README commands exiting 0, a nonblank 720×1040 render, and matching CLI/version results. [Full smoke transcript](sdk-smoke/smoke.txt) and [package checker report](sdk-smoke/check-release.json) are retained.

## Historical evidence and scope

[Claude's original full ctest transcript](claude-ctest.txt) records 258/260, with `sdk-release` and `native-chapter-index` failing. Its DLL preceded the final saved source. Current conclusions use the final files listed above. Intermediate Codex runs and a baseline packaging attempt are retained outside the repository at `C:/Users/Oscar/Documents/Codex/d2m-intermediate-evidence`; they are not the final acceptance evidence.

This is an identification, placeholder and SMIL mapping implementation. Host playback, page-level player rectangles, streaming member reads and bounded chapter-window media support remain outside the implemented behavior; see [MEDIA-EPUB.md](../../docs/MEDIA-EPUB.md). Timing fields in the raw render reports are recorded observations, not a performance comparison.
