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
| `tests/reader_tts_linux/expected_cases.json` | the 138 named cases, fixed before any result is read |
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
* **Stop, then speak.** The espeak-ng module keeps tearing a cancelled message
  down after SPEAK is cancelled; a message submitted inside that window is
  cancelled by the daemon before it begins (measured: a 0.5-rate request issued
  ~200 ms after a cancel came back as an immediate CANCEL). stop therefore waits
  for the daemon's own cancel notification, bounded at 500 ms, so "stop, then read
  the next paragraph" is deterministic.
* **Refusal vs stop.** A message the daemon cancels before BEGIN is reported as
  FAILED/IO, because nobody asked to stop it; an explicit stop always yields
  STOPPED.
* **Liveness.** While a request is active the library only peeks the socket for
  EOF; it never sends a setting command during speech (a rate round trip both
  disturbs playback and can block forever on a dead daemon).
* **Submission boundary.** `speak` copies the text, applies voice and rate, then
  submits with `spd_say`; a callback that races in before the daemon's message id
  is known is buffered and replayed, a callback for an older message is dropped.
* **Limits.** 16 KiB per request (default = ceiling), 128 queued events, 65536
  voices (the espeak-ng module lists thousands), 256 bytes per voice field, 256
  remembered request ids. `speak` reserves
  room for two events or fails with `LIMIT` and changes nothing.
* **Capabilities.** `CAN_PAUSE` is reported (the backend implements it);
  `CAN_REPORT_RANGE` is never reported because Speech Dispatcher only reports
  message-level events and no UTF-16 progress is invented.
* **Rate.** 0.5 .. 2.0 mapped linearly to Speech Dispatcher's percentage rate
  offset `round(100 * (rate - 1))` (0.5 -> -50, 1.0 -> 0, 2.0 -> +100). -100 is
  never sent: on speech-dispatcher 0.11.1 with espeak-ng it asks for zero speed
  and the daemon answers SPEAK with an immediate CANCEL instead of a message.
  Relative, not a duration ratio; no exact timing is claimed.

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
6. runs `run_scenarios.py`, which starts and kills the real daemon, runs seven
   phases (live, pause, cpp, hook, kill/restart, down, recover) with a fresh
   daemon per phase, merges the named cases
   and rejects any missing, duplicate, unexpected, failing or skipped case;
7. uploads evidence, logs and the installed prefix as one artifact whose name
   carries run id, attempt and source SHA.

The report job re-runs `check_scope.sh`, runs the aggregation rejection
regressions, then downloads this run's artifacts through the REST API, checks the
artifact id/name tokens/byte size/sha256 digest/expiry, recomputes the ZIP digest,
verifies the archived `files.sha256` against the archive contents, and re-validates
all 138 named cases against `expected_cases.json`. Any mismatch is a rejection.

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
  library peeks the SSIP socket every 500 ms (no command is sent while speaking),
  so a *dead* daemon is detected, a *hung* one is not.
* `SIGPIPE` must be ignored by the host (documented in the header); the CI
  consumers install that disposition themselves.
* After a named voice, a default-voice request reconnects the client, because
  libspeechd exposes no way back to the daemon default.
* No `RANGE` events and no UTF-16 offset conversion: the daemon does not report
  progress, so no byte range is produced.

## 6. Evidence

Everything below belongs to one run. The artifacts were downloaded back through the
Actions REST API by the report job, their ZIP digests were recomputed, and all 138
named cases were re-validated against `expected_cases.json` before the run was
marked accepted.

### 6.1 Tested source

| field | value |
| --- | --- |
| tested source SHA | `2f4304c0a037e8f20b064bbfa248ea2e9371d436` (branch `codex/reader-tts-linux`) |
| fixed start | `f43baf9182d75907c0cb5d6f77048f27bca8c950` |
| frozen SDK | `9854061be331fe603a1822d9b2b36ee357154927` (3.40.0 / ABI 1) |
| workflow run / attempt | [40138462305](https://github.com/NoGod3524/EXReader/actions/runs/40138462305) / 1, conclusion `success` |
| guard job | `121004930945` success (fixed start, protected trees, product SQL blob, whitelist, source invariants) |
| report job | `121010696804` success, aggregation `accepted=true`, 552 case executions |

This evidence file is committed on top of the tested SHA; that commit changes
documentation only (`docs/`), so the tested source stays
`2f4304c0a037e8f20b064bbfa248ea2e9371d436`.

### 6.2 Platform jobs (each 138/138 named cases, 0 fail, 0 skip)

| job | job id | image | Speech Dispatcher | libspeechd-dev |
| --- | --- | --- | --- | --- |
| ubuntu-2404-release | `121004951274` | Ubuntu 24.04.5 LTS | speech-dispatcher 0.12.0-rc2 | see artifact `pkg-logs/libspeechd-version.log` |
| ubuntu-2404-asan | `121004951352` | Ubuntu 24.04.5 LTS | speech-dispatcher 0.12.0-rc2 | same |
| ubuntu-2204-release | `121004951325` | Ubuntu 22.04.5 LTS | speech-dispatcher 0.11.1 | same |
| ubuntu-2204-asan | `121004951356` | Ubuntu 22.04.5 LTS | speech-dispatcher 0.11.1 | same |

ASan (leak detection with the documented suppressions) and UBSan with
`-fno-sanitize-recover=all` are enabled in the two `*-asan` jobs for the library,
both consumers and the fault-injection suite.

### 6.3 Artifacts of this run

| job | artifact id | bytes | sha256 (recomputed ZIP) | expires |
| --- | --- | --- | --- | --- |
| ubuntu-2204-release | `12577903441` | 51120 | `5df3e0a9c4e45b8b49dbcbd68c7df85a399f6783eaef3b7865d5ddad61682c38` | 2027-01-22T22:25:03Z |
| ubuntu-2204-asan | `12579025224` | 137394 | `b715770a3bdeeb6eca22ffa7ad51f6482b7fa51d2cfe8baf50e44af42d7de555` | 2027-01-22T22:25:03Z |
| ubuntu-2404-release | `12577197975` | 50821 | `1fde0746d651668a6b638e06c92a5b5189272a73cdaffd971ac71c203731ea71` | 2027-01-22T22:25:03Z |
| ubuntu-2404-asan | `12577038289` | 125856 | `99669f69437221aa184f8ae17f10bb63049ecd3ebb2775dc39478af4b7eed8d5` | 2027-01-22T22:25:03Z |
| report (summary + rejections + downloaded ZIPs) | `12579130182` | 344822 | `b8e31aaeaff3a3a851d97e557d354197964bae5cdbac23c98e7ff1cec5211388` | 2027-01-22T22:25:03Z |

Each platform artifact carries `evidence/results.json` (named cases, environment,
consumer digests), `evidence/files.sha256`, the six per-phase JSON files and logs,
`pkg-logs/` (configure/build/install/consumer logs, CMake caches, libspeechd header
digest) and the installed prefix `stage/` (header, `libreader_tts.a`, CMake package
files, `LICENSE.txt`).

The report job's rejection regressions ran 39 offline fixtures (sound and mutated:
wrong source/run/attempt, expired or zero-byte artifact, malformed digest,
tampered ZIP, tampered and unpacked manifests, missing/duplicate/unexpected cases,
missing detail, flat and prefixed layouts) and every mutation was rejected.

### 6.4 Named results

138 cases per platform, 552 executions in total, all `pass`:

| phase | cases | what it proves |
| --- | --- | --- |
| live | 70 | create/observe/voices, request lifecycle, UTF-8/limit/rate/voice validation, owner-thread rejection, second handle, close/destroy, voice-list lifetime, config ceilings |
| pause | 12 | pause/resume transitions and idempotence, two cycles, stop after resume, close |
| cpp | 11 | the same ABI from C++ (owner thread from std::thread, voice list outliving the handle, full cycle) |
| hook | 22 | early-callback buffering, late-callback filtering, queue ceiling, allocation failures, measured voice count |
| kill | 12 | daemon SIGKILLed mid-utterance: FAILED/UNAVAILABLE, no autospawn, restart and same-handle recovery |
| down | 7 | no daemon: CREATE OK with SERVICE_UNAVAILABLE, voices/speak UNAVAILABLE, no autospawn, clean close |
| recover | 4 | daemon back: a fresh process connects, speaks, closes |

### 6.5 Failing runs and what each one fixed

Every failure is preserved in its own run; nothing was deleted, widened or turned
into an expected rejection.

| run (tested SHA) | failure | fix |
| --- | --- | --- |
| [40124635826](https://github.com/NoGod3524/EXReader/actions/runs/40124635826) (`b191e57f`) | `-Werror=format-truncation` on the installed C consumer's `/proc` path buffer | buffer sized (`2d6239b5`) |
| [40125071124](https://github.com/NoGod3524/EXReader/actions/runs/40125071124) (`2d6239b5`) | the driver exported `SPEECHD_ADDRESS=unix_socket=...`, which libspeechd 0.11.1 rejects, so the library never connected | default address, preflight gate, address probes recorded (`ca2f9307`) |
| [40125748485](https://github.com/NoGod3524/EXReader/actions/runs/40125748485) (`ca2f9307`) | `voices` returned LIMIT (the module lists 13362 voices), hook queue order, long-utterance backlog | ceiling 65536 + measured count, hook order, boundary case last (`b9c03ce5`) |
| [40126679643](https://github.com/NoGod3524/EXReader/actions/runs/40126679643) (`b9c03ce5`) | the rate round-trip probe blocked forever after SIGKILL and disturbed playback | liveness by socket peek (`5550a575`) |
| [40127692686](https://github.com/NoGod3524/EXReader/actions/runs/40127692686) (`5550a575`) | one audio case failed without saying why | submission status, terminal kinds and elapsed time reported (`431e9bbd`) |
| [40128347109](https://github.com/NoGod3524/EXReader/actions/runs/40128347109) (`431e9bbd`) | rate 0.5 cancelled by the daemon at the -100 endpoint | mapping on the daemon's percentage scale (`c51c9cf1`) |
| [40129061386](https://github.com/NoGod3524/EXReader/actions/runs/40129061386) (`c51c9cf1`) | still cancelled; the same rate works before a stop and fails after one | bisect cases added (`b32cebac`) |
| [40129612797](https://github.com/NoGod3524/EXReader/actions/runs/40129612797) (`b32cebac`) | bisect proved the cancel, not the rate; also an id-reuse bug in the test | stop waits for the daemon's cancel, refusal is FAILED/IO, id fixed (`18eb191c`) |
| [40130205438](https://github.com/NoGod3524/EXReader/actions/runs/40130205438) (`18eb191c`) | an explicit stop ended with FINISHED because espeak-ng reports a cancelled message as END | intent decides the terminal event (`98672235`) |
| [40130822607](https://github.com/NoGod3524/EXReader/actions/runs/40130822607) (`98672235`) | ubuntu-24.04 green; on 22.04 a cancelled message wedges the module and every later request of the client is silent | Latin long text, per-case reset, fresh daemon per phase (`ca330266`) |
| [40132122033](https://github.com/NoGod3524/EXReader/actions/runs/40132122033) (`ca330266`) | the wedge survived CANCEL+STOP | pause/resume moved to their own phase (`27e5ca03`) |
| [40132713831](https://github.com/NoGod3524/EXReader/actions/runs/40132713831) (`27e5ca03`) | three of four jobs green; 22.04 ASan hung in a voice query after a cancel and reported a libspeechd `getline` leak | voice queries before any cancel, `leak:__getdelim` with that evidence (`4262dfcd`) |
| [40135611342](https://github.com/NoGod3524/EXReader/actions/runs/40135611342) (`4262dfcd`) | all four platform jobs passed, but the aggregation looked for `results.json` at the archive root | evidence directory located inside the artifact, manifest scoped, both layouts in the rejection tests (`2f4304c0`) |
| [40138462305](https://github.com/NoGod3524/EXReader/actions/runs/40138462305) (`2f4304c0`) | — | accepted: 4 jobs × 138 cases, 0 fail, 0 skip |

### 6.6 Platform defect on speech-dispatcher 0.11.1 (recorded, not worked around)

On Ubuntu 22.04 (speech-dispatcher 0.11.1) a cancelled message can leave the
espeak-ng module wedged: the daemon keeps accepting SPEAK (the client gets no
event at all afterwards) and never answers LIST SYNTHESIS VOICES. A fresh daemon
clears it. The package handles this the only honest way - the pause/resume
scenario runs on its own daemon, the driver restarts the daemon between phases,
and voice queries run before any cancel - and the behaviour is registered here as a
platform defect rather than hidden behind a changed expectation. The library's own
behaviour (stop, refusal classification, cancellation bookkeeping) is verified on
both versions.

### 6.7 What is still not covered

* Audible output, voice quality and listening tests: the runner has a null audio
  sink; only the daemon's begin/end/cancel handling is observed.
* A daemon that accepts the connection and then stops answering: no client-side
  timeout exists (documented), so such a call can block inside libspeechd.
* Distributions other than Ubuntu 22.04/24.04, and non-x86_64 hosts.
* GTK host wiring and the default reading configuration (root's work).
* Two handles using the daemon at the same time (one connection per process, by
  design).
