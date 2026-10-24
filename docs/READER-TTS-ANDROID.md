# J18: Android system TextToSpeech backend

Status: accepted on an API 34 emulator with a real engine, run 40126240859 at source
`fe1eb58e2737aeeefbcdfe68e9ef6cff4db164f6`. The evidence record is
`docs/validation/reader-tts-android.json`; this document commit changes documentation only.

* Fixed start: `f43baf9182d75907c0cb5d6f77048f27bca8c950`
* Branch: `codex/reader-tts-android` (no merge, no tag, no release, no default branch)
* Frozen interface: `docs/handoffs/reader-next-wave/tts-contract.md` (`READER_TTS_VERSION "0.1.0"`)
* Protected SDK `9854061be331fe603a1822d9b2b36ee357154927` (3.40.0 / ABI 1) and product
  schema 1 are unchanged; this package links no SDK component.

## What is delivered

| Path | Content |
| --- | --- |
| `extras/reader-tts-android/include/reader_tts.h` | frozen C ABI, implementation constants and limits |
| `extras/reader-tts-android/include/reader_tts_android.h` | Android bind entry, callback vocabulary and the host deliver entry |
| `extras/reader-tts-android/src/reader_tts_android.c` | state machine, bounded event ring, UTF-8 validation, JNI calls |
| `extras/reader-tts-android/android/tts` | `org.exreader.tts.Backend` + `Chunker` Android library (no Maven dependencies) |
| `tests/reader_tts_android/consumer` | installed-package C11 consumer, JNI bridge and the named case table |
| `tests/reader_tts_android/android` | instrumentation probe app, baseline app and Gradle wiring |
| `tests/reader_tts_android/run_device.py` | two real engine states on the emulator, audio pull and digest check |
| `tests/reader_tts_android/verify_evidence.py` | same-run artifact authentication and named-case comparison |
| `.github/workflows/reader-tts-android.yml` | guards, NDK API 26 build, Gradle packages, emulator acceptance, summary |

## Behaviour contract (implementation specifics)

* Owner thread: the creating thread; `reader_tts_voice_list_free` needs no handle.
  The library owns a private `HandlerThread`, so no host `Looper` is required and
  the process main thread is never blocked by the library.
* Limits: `max_utf8_bytes` defaults to 16384 and can only be lowered. Text above
  the configured limit, above the engine ceiling
  (`TextToSpeech.getMaxSpeechInputLength()`, 4000 UTF-16 units on the reference
  engine) or into a queue with fewer than three free slots fails with
  `READER_TTS_LIMIT`; nothing is truncated. Hosts chunk with
  `org.exreader.tts.Chunker` and give every chunk a new, increasing request id.
* Validation order: null/zero/UTF-8/rate/voice-length arguments and the byte limit
  are checked before engine state, so error classes stay deterministic while the
  engine initialises. Then `INITIALIZING` gives BUSY, `SERVICE_UNAVAILABLE`/CLOSING/
  CLOSED give UNAVAILABLE, an active request gives BUSY, and an already used
  request id gives ARGUMENT.
* Text must be strict UTF-8: overlong forms, encoded surrogates, code points past
  U+10FFFF, incomplete sequences and embedded NUL are refused.
* Rate is a finite 0.5..2.0 relative speed mapped 1:1 onto
  `TextToSpeech.setSpeechRate`; engines may clamp it and no exact duration ratio
  is promised.
* `voice_id` NULL or empty selects the engine default; an identifier the engine
  does not list is refused with ARGUMENT. `reader_tts_voices` never triggers an
  engine download.
* RANGE events carry UTF-8 byte offsets of the submitted text. Android reports
  UTF-16 offsets, which the library converts per request; a range that would
  split a surrogate pair is dropped instead of being invented.
  `READER_TTS_CAN_REPORT_RANGE` is published only after the engine actually
  reported a range. `READER_TTS_CAN_PAUSE` is never published:
  `reader_tts_pause`/`reader_tts_resume` return `READER_TTS_UNSUPPORTED` and leave the
  state untouched.
* Events: 128 entries, one active request, `STARTED` and exactly one terminal
  (`FINISHED`/`STOPPED`/`FAILED`) per accepted request. STARTED and terminal events
  are never dropped; when the ring is full the oldest RANGE is retired (ranges are
  advisory) and a RANGE that would still overflow is dropped while `last_status`
  becomes `READER_TTS_LIMIT`. An utterance failure returns the state to
  READY/`SERVICE_UNAVAILABLE` and reports the event; `last_status` then records the
  backend error class (`READER_TTS_IO`).
* `request_close` is non-blocking and idempotent: it stops the active request and
  asks the Java layer to shut the engine down. The handle reaches CLOSED only
  after the release callback arrived, which is also when the global reference is
  dropped and the cookie is unregistered; later engine callbacks are ignored.
  `destroy` returns BUSY with the pointer intact until CLOSED.
* At most 8 handles per process (further `create` calls return
  `READER_TTS_LIMIT`). This package never installs or downloads a voice engine.

## Cloud acceptance

`.github/workflows/reader-tts-android.yml`, job `tts-android-device`:

1. Guard: `HEAD == GITHUB_SHA`, the fixed start is an ancestor, the SDK protected
   tree and product schema equal the pinned baselines, and
   `git diff --name-only <fixed start> HEAD` stays inside the J18 ownership list.
2. NDK build/install of the C archive for `android-26` in Debug and Release with
   `-Wall -Wextra -Werror`, plus refusals: a host target must fail and
   `ANDROID_PLATFORM=android-25` must fail.
3. Gradle: support AAR, `lintRelease`, the probe app (debug/release/androidTest) and
   a baseline app that carries the same library without the consumer.
4. Emulator API 34 `google_apis_playstore` x86_64: one run with a real engine (real
   `speak` callbacks, a real `synthesizeToFile` WAV, and a real Activity recreation
   while one request is speaking), then every engine package is removed and the
   probe runs again, so the missing-engine path is observed rather than simulated.
5. Artifact upload of evidence, packages and logs; the `tts-artifact-summary` job
   downloads this run's ZIP through the API, recomputes its digest, checks
   source/run/attempt/name/bytes/expiry and compares the named case sets of the two
   real engine states.

Local runs are deliberately impossible: `run_device.py` and `verify_evidence.py` both
require `GITHUB_ACTIONS=true`, and the CMake package refuses non-Android targets.

## Acceptance record

* Tested source: `fe1eb58e2737aeeefbcdfe68e9ef6cff4db164f6`; run 40126240859, attempt 1, both
  jobs success (`tts-android-device` 120968163321, `tts-artifact-summary` 120969585448).
* Artifact `reader-tts-android-40126240859-1` id 12573062623, 346395 bytes,
  sha256 `2224a5404b8df6c089422ae7948ac2830ac3b2637c061be11cf071984b2d09a2`,
  expires 2027-01-22T19:38:45Z; the summary job re-downloaded it through the API, recomputed
  the digest and compared this run's identity.
* Named outcomes: 46 cases per run. With `com.google.android.tts` installed 45 pass and one
  skips (the missing-engine case); after every engine package was removed 32 pass and 14 skip
  (the engine-dependent cases), including a real `service_unavailable_when_engine_missing` pass.
* Audio: `files/audio/tts-sample.wav`, 91244 bytes, RIFF/WAVE, sha256
  `83f66b0e6de2231a14b994c4d21260ac5d5d773d376274d6546e5582e6164987`, produced by
  `synthesizeToFile` with the local voice `en-AU-language`; the digest computed on the device and
  the digest of the published file match.
* Packages: AAR 10740 bytes (no native libraries), probe debug APK 74142 bytes with
  `lib/x86_64/libtts-consumer.so` 52280 bytes, baseline APK 8372 bytes, delta 65770 bytes,
  no Maven runtime dependencies.
* Retained failures (not deleted): run 40123986906 (JNI environment argument missing),
  run 40124242333 (androidTest APK path), run 40124745606 (summary job demanded an already
  completed run), and the earlier success run 40125579469 which covers the same cases without
  the rotation case.
* Not covered: host product wiring, background playback, audio focus, media session, haptics,
  spoken quality on a handset, a genuine engine-level FAILED terminal event and the release
  failure path, other engines, and long-session thermal behaviour.

## Scope boundaries

* Not accepted by this package: Android host product wiring, background playback,
  audio focus, media session integration, haptics, or any spoken-output quality
  judgement.
* The removed-engine run is a negative path: it grants the refusal behaviour, not
  real reading.
* No emulator audio output is judged; only engine callbacks and the rendered file
  bytes are evidence.
