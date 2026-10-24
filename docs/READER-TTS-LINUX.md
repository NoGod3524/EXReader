# READER-TTS-LINUX: Linux native Speech Dispatcher speech backend

Package J19. Branch `codex/reader-tts-linux`. Fixed source start
`f43baf9182d75907c0cb5d6f77048f27bca8c950`, frozen SDK
`9854061be331fe603a1822d9b2b36ee357154927` (3.40.0, ABI 1), product schema 1,
wire v1 and reading anchor v1/v2 untouched.

Status: implementation and test harness complete in source; the acceptance
evidence below is filled from the actual GitHub Actions runs (see
[evidence](#evidence)). Until those runs exist this package claims nothing.

## 1. What this package is

An optional, independently installed C library (`EXReaderTTSLinux::reader_tts`)
that implements the frozen J16-J19 `reader_tts.h` ABI on top of the **system**
Speech Dispatcher:

* list voices, speak one request at a time, pause, resume, stop, observe, poll;
* explicit `UNAVAILABLE` when the system service is missing, and recovery when it
  comes back;
* no engine, no daemon, no server, no WebView, no plugin framework, no second
  text parser; the only dependency is the read-only system `libspeechd`.

It is **not** wired into the GTK host and is not part of the default reading
build. Root owns host wiring; this package only proves the module.

### Files

| path | role |
| --- | --- |
| `extras/reader-tts-linux/include/reader_tts.h` | frozen ABI plus the Linux contract comments and hard limits |
| `extras/reader-tts-linux/include/reader_tts_test.h` | fault-injection surface, built only with `READER_TTS_BUILD_TEST_HOOKS=ON` |
| `extras/reader-tts-linux/src/reader_tts_linux.c` | the backend |
| `extras/reader-tts-linux/CMakeLists.txt`, `EXReaderTTSLinuxConfig.cmake.in` | independent CMake package (`EXReaderTTSLinux::reader_tts`, `EXReaderTTSLinux::speechd`) |
| `extras/reader-tts-linux/README.md` | contract summary and install usage |
| `tests/reader_tts_linux/consumer/` | installed-package C consumer, real daemon scenarios |
| `tests/reader_tts_linux/consumer_cpp/` | installed-package C++ consumer (C ABI from C++, std::thread ownership, voice-list lifetime, unique_ptr deleter) |
| `tests/reader_tts_linux/tts_hook_suite.c` | source-built fault-injection suite |
| `tests/reader_tts_linux/expected_cases.json` | the 127 named cases, fixed before any result is read |
| `tests/reader_tts_linux/run_scenarios.py` | owns the daemon lifecycle, merges and validates results |
| `tests/reader_tts_linux/aggregate.py`, `check_aggregate.py` | strict same-run aggregation and its rejection regressions |
| `tests/reader_tts_linux/check_scope.sh` | fixed start, frozen SDK, product SQL, whitelist and source invariants |
| `.github/workflows/reader-tts-linux.yml` | the only place anything is built or run |

## 2. Contract (authoritative text in the installed header)

* **Threading.** Everything except `reader_tts_voice_list_free` runs on the
  creating (owner) thread; any other thread gets `READER_TTS_OWNER` and no state
  change. No host callback is ever invoked: libspeechd's event thread only
  appends to a bounded queue under a private mutex. No host event loop needed.
* **Blocking.** All calls are local socket round trips; `request_close` never
  blocks (a library thread releases the connection and moves the state to
  `CLOSED`).
* **Memory.** Inputs are copied; voices are library-owned and released by
  `reader_tts_voice_list_free` (which may be called after the handle is gone);
  errors carry a status plus a platform code, never message text or input bytes.
* **Submission boundary.** `speak` copies the text, applies voice and rate, then
  submits with `spd_say`; a callback that races in before the daemon's message id
  is known is buffered and replayed, a callback for an older message is dropped.
* **Limits.** 16 KiB per request (default = ceiling), 128 queued events, 4096
  voices, 256 bytes per voice field, 256 remembered request ids. `speak` reserves
  room for two events or fails with `LIMIT` and changes nothing.
* **Capabilities.** `CAN_PAUSE` is reported (the backend implements it);
  `CAN_REPORT_RANGE` is never reported because Speech Dispatcher only reports
  message-level events and no UTF-16 progress is invented.
* **Rate.** 0.5 .. 2.0 mapped piecewise-linearly to -100 .. 100. Relative, not a
  duration ratio; no exact timing is claimed.

## 3. Reproduction (Actions only)

```
workflow: .github/workflows/reader-tts-linux.yml
matrix:   ubuntu-22.04 x {release, ASan+UBSan}  and  ubuntu-24.04 x {release, ASan+UBSan}
```

Each job:

1. `check_scope.sh`: `HEAD == GITHUB_SHA`, fixed start is an ancestor, the
   protected SDK tree equals the fixed start **and** the frozen SDK commit, product
   SQL `apps/reader/store/001_catalog.sql` blob-identical, every changed path in
   the J19 whitelist, library formats no text, spawns no process, calls
   `spd_open2(..., NULL, 0, ...)`, implements all 11 frozen entry points.
2. installs `speech-dispatcher`, `speech-dispatcher-espeak-ng`, `libspeechd-dev`,
   `espeak-ng`, PulseAudio with a null sink, and an ALSA null default device;
3. builds and installs the package, then verifies the installed prefix (header,
   static library, CMake package files, `LICENSE.txt`, and that the test hooks are
   **not** installed);
4. compiles the C and the C++ consumer **from the installed prefix only**;
5. builds the fault-injection suite from the package source;
6. runs `run_scenarios.py`, which starts and kills the real daemon, runs six
   phases (live, cpp, hook, kill/restart, down, recover), merges the named cases
   and rejects any missing, duplicate, unexpected, failing or skipped case;
7. uploads evidence, logs and the installed prefix as one artifact whose name
   carries run id, attempt and source SHA.

The report job re-runs `check_scope.sh`, runs the aggregation rejection
regressions, then downloads this run's artifacts through the REST API, checks the
artifact id/name tokens/byte size/sha256 digest/expiry, recomputes the ZIP digest,
verifies the archived `files.sha256` against the archive contents, and re-validates
all 127 named cases against `expected_cases.json`. Any mismatch is a rejection.

## 4. Scope of what may be claimed

Separately granted, never merged into one "TTS works" statement:

| aspect | how it is granted |
| --- | --- |
| module behaviour | the named cases in `expected_cases.json` on the real system daemon |
| actual audio | **not granted**: the runner has a null audio sink; only the daemon's
  begin/end/cancel handling is observed, no listening test is possible |
| pause/resume | granted as daemon state transitions (`SPEAKING <-> PAUSED`) and
  event/state bookkeeping, not as audible playback behaviour |
| host integration | **not granted**: root wires the GTK host later |
| platform breadth | Ubuntu 22.04 and 24.04 x86_64 only (the matrix); no other
  distribution, no aarch64, no real desktop |
| performance | nothing claimed: no benchmark is run for this package |
| accessibility | nothing claimed by this package |

## 5. Known limitations and failure modes

* One daemon connection per process; a second handle reports
  `SERVICE_UNAVAILABLE` until the first closes.
* Request-id reuse is detected for the last 256 ids only.
* A daemon that accepts the socket but stops answering can block a call inside
  libspeechd; there is no client-side timeout. While a request is active the
  library probes every 500 ms, so a *dead* daemon is detected, a *hung* one is not.
* `SIGPIPE` must be ignored by the host (documented in the header); the CI
  consumers install that disposition themselves.
* After a named voice, a default-voice request reconnects the client, because
  libspeechd exposes no way back to the daemon default.
* No `RANGE` events and no UTF-16 offset conversion: the daemon does not report
  progress, so no byte range is produced.

## 6. Evidence

Filled from the real runs below.

| field | value |
| --- | --- |
| tested source SHA | pending |
| workflow run / attempt | pending |
| jobs | pending |
| artifacts (id, bytes, sha256, expires) | pending |
| named cases | pending |
| first failing run and fix | pending |
