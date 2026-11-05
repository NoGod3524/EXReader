# EXReaderTTSLinux::reader_tts

Optional, independent Linux reader TTS backend for EXReader. It speaks through
the **system Speech Dispatcher** over its local SSIP socket (`libspeechd`) and
implements the frozen J16-J19 `reader_tts.h` C ABI (`READER_TTS_VERSION "0.1.0"`).

* Ships **no** engine, daemon or server. The daemon is an OS service; this module
  only connects to it (`spd_open2(..., autospawn = 0)`) and never spawns,
  restarts or supervises it.
* One handle per process owns the daemon connection (libspeechd keeps
  process-global state). A second `reader_tts_create` still returns a valid
  handle whose state is `READER_TTS_SERVICE_UNAVAILABLE`; it recovers if the
  first handle is closed.
* Not part of the default reading build and not linked by any host yet; root
  wires it into the GTK host later.

## System dependency vs bundled material

| kind | item |
| --- | --- |
| system dependency (not bundled) | `libspeechd` + a running `speech-dispatcher` with an output module (espeak-ng on the CI runners) |
| bundled | `include/reader_tts.h` (frozen ABI), this package's CMake package files, `LICENSE.txt` |
| not bundled | speech engine, voices, audio server, daemon configuration |

## Build and install

```sh
cmake -S extras/reader-tts-linux -B build/tts-linux -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=$PWD/build/tts-stage
cmake --build build/tts-linux
cmake --install build/tts-linux
```

Consumers use the installed package only:

```cmake
find_package(EXReaderTTSLinux 0.1 REQUIRED)
target_link_libraries(app PRIVATE EXReaderTTSLinux::reader_tts)
```

The installed package exports `EXReaderTTSLinux::reader_tts` (static library),
`EXReaderTTSLinux::speechd` (the system `-lspeechd` link), the frozen header and
`share/exreader-tts-linux/LICENSE.txt`. `-DREADER_TTS_BUILD_TEST_HOOKS=ON` adds
`include/reader_tts_test.h` and the fault-injection symbols; it is for the test
suite only and never installed by the default build.

## Contract essentials

Full text: `include/reader_tts.h`. Owner thread only; errors carry a status and
a platform code and never text. Summary of the parts a host must respect:

| topic | behaviour |
| --- | --- |
| input | `speak` takes strict UTF-8, no NUL, 1 .. `max_utf8_bytes` (default and ceiling 16 KiB); text is copied, never borrowed; longer text is split by the host into new request ids |
| rate | finite 0.5 .. 2.0, mapped linearly to Speech Dispatcher's percentage rate offset `round(100 * (rate - 1))` (`0.5 -> -50`, `1.0 -> 0`, `2.0 -> +100`); -100 is never sent because the daemon cancels a zero-speed message; a relative setting, not a duration ratio |
| voice | `NULL`/`""` = daemon default; an id the daemon does not list is `ARGUMENT`; after a named voice the next default request reconnects (libspeechd has no "restore default") |
| requests | one active request; a second `speak` is `BUSY` and never interrupts; ids are remembered for the last `READER_TTS_ID_MEMORY` (256) requests |
| events | bounded queue (`READER_TTS_EVENT_CAPACITY` = 128), one `STARTED` and exactly one of `FINISHED`/`STOPPED`/`FAILED` per started request; `RANGE` is never emitted (`CAN_REPORT_RANGE` unset, no UTF-16 progress is faked) |
| daemon loss | while a request is active the library probes the daemon; a vanished daemon ends the request with `FAILED`/`UNAVAILABLE`, the state becomes `SERVICE_UNAVAILABLE`, and the next call reconnects |
| close | `request_close` is non-blocking and idempotent; queued events stay readable in `CLOSING` and `CLOSED` so the terminal event is not lost; `destroy` is `BUSY` until `CLOSED` |
| SIGPIPE | the process must ignore `SIGPIPE` (a vanished daemon turns a socket write into `EPIPE`) |

## Limits (enforced, not advisory)

`READER_TTS_DEFAULT_MAX_UTF8` 16384 bytes, `READER_TTS_EVENT_CAPACITY` 128
events, `READER_TTS_MAX_VOICES` 65536 (the espeak-ng module lists several
thousand synthesis voices), `READER_TTS_MAX_VOICE_FIELD` 256 bytes,
`READER_TTS_ID_MEMORY` 256 ids. A request needs room for two events before it
starts, otherwise `speak` returns `LIMIT` and changes nothing.

## Verification

All builds, tests, sanitizer runs and the real-daemon scenarios run in GitHub
Actions (`.github/workflows/reader-tts-linux.yml`) on ubuntu-22.04 and
ubuntu-24.04, in release and ASan/UBSan variants. Evidence:
`docs/READER-TTS-LINUX.md` and `docs/validation/reader-tts-linux.json`.
