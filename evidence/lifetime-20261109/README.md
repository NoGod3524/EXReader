# S6 lifecycle evidence

Frozen-source Windows MSVC Debug baseline. Each of the 19 SHA-256-verified books is opened once, enumerated, its first part/page loaded and rendered, then all objects are released. `exr_debug_cleanup()` releases the diagnostic quarantine between books.

| Check | Result | Evidence |
|---|---|---|
| Latest MSVC ASan contracts | 50/50; 34 assertion aborts + 16 valid cases | [raw per-case results](asan-contract/summary.json), [console](asan-final-contract.txt) |
| Latest MSVC ASan focused regression | 6/6: lifetime fixtures, hyphen, audio-player, canvas, control, library-source | [log](asan-final-focused.txt), [JUnit](asan-final-focused.xml) |
| MSVC AddressSanitizer | 19/19 books; 0 address diagnostics; 0 live objects | [log](asan-19-books.txt), [summary + source hashes](asan-19-books-summary.json) |
| Independent static MSVC Debug CRT heap | 19/19 books; 0 leaked blocks / 0 leaked bytes after every book | [log](crt-19-books.txt), [summary + source hashes](crt-19-books-summary.json) |
| ASan positive control | Intentional heap-buffer-overflow detected, process exit 1 | [log](asan-control.txt), [result](asan-control.json) |
| CRT positive control | Intentional allocation detected: 1 block / 17 bytes; 0 after free | [log](crt-19-books.txt) |

MSVC ASan does not implement leak detection and disables the debug CRT heap counters. These are two separate builds of the same source. The CRT executable links the SDK components and dependencies statically into the same debug heap. Native PR CI runs the fixture lifecycle test under Linux ASan/LSan using the existing `detect_leaks=1` configuration.

## Object counts

The ASan and CRT runs produced identical counts. Zero rows identify object types not created by this 19-book workload.

| Type | Created | Freed | Live |
|---|---:|---:|---:|
| `exr_aac` | 0 | 0 | 0 |
| `exr_audio` | 0 | 0 | 0 |
| `exr_audio_output` | 0 | 0 | 0 |
| `exr_audio_player` | 0 | 0 | 0 |
| `exr_bidi` | 0 | 0 | 0 |
| `exr_canvas` | 1 | 1 | 0 |
| `exr_cfi` | 0 | 0 | 0 |
| `exr_dictionary` | 0 | 0 | 0 |
| `exr_document` | 38 | 38 | 0 |
| `exr_fixed_document` | 1 | 1 | 0 |
| `exr_fixed_text` | 1 | 1 | 0 |
| `exr_flac` | 0 | 0 | 0 |
| `exr_font` | 23 | 23 | 0 |
| `exr_font_manager` | 0 | 0 | 0 |
| `exr_hyphenation` | 0 | 0 | 0 |
| `exr_hyphenator` | 0 | 0 | 0 |
| `exr_layout` | 36 | 36 | 0 |
| `exr_library` | 0 | 0 | 0 |
| `exr_m4b` | 0 | 0 | 0 |
| `exr_m4b_inspection` | 0 | 0 | 0 |
| `exr_mp3` | 0 | 0 | 0 |
| `exr_pager` | 18 | 18 | 0 |
| `exr_pcm` | 0 | 0 | 0 |
| `exr_publication` | 18 | 18 | 0 |
| `exr_session` | 0 | 0 | 0 |
| `exr_sevenz` | 0 | 0 | 0 |
| `exr_stretch` | 0 | 0 | 0 |
| `exr_text_index` | 0 | 0 | 0 |
| `exr_text_query` | 0 | 0 | 0 |
| `exr_txt_cursor` | 0 | 0 | 0 |
| `exr_wave` | 0 | 0 | 0 |
| `sdk_buffer` | 47933 | 47933 | 0 |

## Reproduce

```powershell
python tools/lifetime_leaks.py asan build
python tools/lifetime_leaks.py asan run
python tools/lifetime_leaks.py crt build
python tools/lifetime_leaks.py crt run
```

The runner requires 19 corpus entries and verifies every book hash before and after execution. Source hashes must match before compilation, after compilation, before measurement, and after measurement. The native executable is `exreader-lifetime-leaks-test FONT [--crt] BOOK...`; CTest supplies repository EPUB/PDF fixtures for portable sanitizer CI.

## Earlier diagnostic runs

`asan-ctest.txt` and `asan-interrupted.json` preserve the earlier 42-case snapshot. That local regression completed 20 tests (19 passing, one stale hyphenator reentry failure); its hyphen-layout/float processes were stopped during memory pressure after newer source fixes were available. This incomplete run is separate from the frozen-source 19-book baseline and the final 50-case contract evidence.
