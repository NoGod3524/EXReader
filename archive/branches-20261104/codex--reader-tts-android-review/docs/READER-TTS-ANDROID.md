# J18: Android system TextToSpeech backend

Status: accepted by the independent package review on an API 34 emulator with a real
engine, run 40171693275 at source `8db7d57a28530dfdeea763ef2c34a1343283714c` (branch
`codex/reader-tts-android-review`). Two earlier acceptances are retained in the same evidence
record and superseded: the first review acceptance (run 40170544552 at `8ada0511`, 52 named
cases) and the original delivery acceptance (run 40126240859 at `fe1eb58e`, head
`5993381e4507cffb7c63465642c2052f5760deb3`, 46 named cases); the root review found the uint64
request id truncation and the unbound callback identity in the first one. The evidence record is
`docs/validation/reader-tts-android.json`; this document commit changes documentation only.

* Fixed start: `f43baf9182d75907c0cb5d6f77048f27bca8c950`
* Branch: `codex/reader-tts-android-review` (review), delivery branch `codex/reader-tts-android`
  (unchanged, no merge, no tag, no release, no default branch)
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
  Engine creation, the init handshake and shutdown run on the library's private
  `HandlerThread`; the framework delivers the engine init callback on the process
  main thread and every utterance callback on an engine binder thread, so a
  blocked main thread blocks readiness. The request entry points (`speak`,
  `stop`, `voices`) are synchronous engine calls on the owner thread, which
  therefore needs no `Looper`.
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
  engine download. A voice reported by `reader_tts_voices` carries the engine
  identifier in `id` (the value a host passes back), the engine's localized
  display name in `name` and a BCP 47 tag in `language`.
* Voice selection is engine state: an explicit `voice_id` stays selected for
  this handle until another `voice_id` is given, and a request with an empty `voice_id`
  re-selects the engine default voice instead of inheriting the previous one.
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
* `stop` ends the active request itself: once the platform accepted the stop the
  request is no longer active, its single `STOPPED` event is queued immediately and
  the handle is READY for the next request. `request_close` does the same for a
  request that is still active before the handle becomes CLOSED. A second terminal
  callback for a request that already ended (an engine that reports both `onDone`
  and `onStop`, or one that reports late) is dropped, so a host can never see two
  terminals for one request. Stopping an id that is not active is OK when it is at
  or below the last accepted id (it ended earlier) and ARGUMENT when it is above
  every accepted id.
* Request ids cross the JNI boundary as unsigned decimal, so the whole uint64 range is
  usable: an id at or above 2^63 becomes a negative Java long inside the library and comes
  back as the identical unsigned id in `observe` and in every event. An engine callback
  whose id is not decimal, longer than 20 digits or larger than `UINT64_MAX` is ignored
  instead of being wrapped onto a different request.
* An engine callback is consumed only while its id is the active accepted request. Unknown
  (never accepted), future (not used yet) and stale (already ended) ids leave the state and
  the terminal mark untouched, so a fabricated or late callback can neither end a request
  that is still speaking nor advance the handle past it; `stop` and `request_close` end the
  active request themselves, and a repeated terminal for an ended request is refused too.
  Callback entries pin the handle, so a `destroy` that runs while a late callback is in
  flight cannot free the ring or the lock under it; a callback that arrives after `destroy`
  is refused because the cookie is no longer registered.
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

## Review findings and fixes

The independent review audited the native adapter, the Android library and the evidence logic
against the frozen contract. These concrete package defects were fixed and are covered by the
named cases below:

| Finding | Fix | Case |
| --- | --- | --- |
| `Backend.speak` formatted the request id with `Long.toString` although the C ABI accepts `uint64_t`: an id at or above 2^63 became a negative utterance id that the callback parser rejects, so the request lost every real callback and the handle stayed SPEAKING | the utterance id is the unsigned decimal form of the same bits, so the whole uint64 range round trips | `speak_high_bit_request_id`, `speak_max_request_id` |
| the native callback entry accepted STARTED, RANGE and terminal events for any well formed decimal id, so a terminal for an id the host had not used yet advanced the terminal mark above a real request and suppressed its terminal | an utterance callback is consumed only while its id is the active accepted request; unknown, future and stale ids move nothing | `future_callback_ignored_while_active`, `future_callback_ignored_while_idle` |
| `stop` left the handle in `STOPPING` until the engine reported the interrupted utterance; an engine that never reports left the request active forever, so every later `speak` returned BUSY | the platform-accepted stop ends the request itself with its one `STOPPED` event and returns the handle to READY | `stop_and_close_single_terminal`, `stop_single_stopped` |
| `request_close` while a request was speaking could leave that accepted request without any terminal event, because the release callback can win the race with the engine's own stop callback | close ends the active request with exactly one `STOPPED` before CLOSED | `stop_and_close_single_terminal` |
| a second terminal callback for one request (`onDone` then `onStop`, or a late callback) was queued as a second terminal | one terminal per request id; later ones are dropped | `duplicate_terminal_dropped`, `stop_single_stopped` |
| an engine utterance id above `UINT64_MAX` wrapped onto a different request id | non-decimal and overflowing ids are ignored | `overflow_utterance_id_ignored` |
| a late callback could run concurrently with `destroy`, which freed the lock and the ring under it | callback entries pin the handle, the last unpin frees it, a destroyed cookie is refused | `stale_callback_after_destroy_ignored` |
| `reader_tts_voices` wrote the engine voice id into both `id` and `name`, so a host could only show internal ids | `name` is the localized locale name of the voice | `voice_names_match_engine` |
| an explicit `voice_id` stayed selected for the handle, so a later request with an empty `voice_id` spoke with the stale voice instead of the engine default | an empty `voice_id` re-selects the engine default voice | `voice_selection_returns_to_default` |
| the text kept for UTF-16 to UTF-8 range conversion stayed resident when a request ended without a terminal callback | it is released when a request ends or the next one starts | `range_utf8_boundaries`, `voice_selection_returns_to_default` |
| the class documentation claimed every engine mutation runs on the private `HandlerThread` | documented the real split: framework init on the process main thread, utterance callbacks on engine binder threads, request calls synchronous on the owner thread | documentation only |

Nothing outside the package changed: the production reader host, the shared TTS contract, the
other platform adapters, the SDK tree and the product schema are untouched, and the original
delivery branch `codex/reader-tts-android` was not written to.

## Acceptance record

* Tested source: `8db7d57a28530dfdeea763ef2c34a1343283714c`; run 40171693275, attempt 1, both
  jobs success (`tts-android-device` 121103681289, `tts-artifact-summary` 121104804947).
* Artifact `reader-tts-android-40171693275-1` id 12591135384, 370952 bytes,
  sha256 `8acf989ecdde16fa897bd83bb5f44ec726f6176e53feb18f67dc40f2df1141df`,
  expires 2027-01-23T07:09:01Z; the summary artifact
  `reader-tts-android-summary-40171693275-1` id 12591070445, 1982 bytes, sha256
  `ac726773ec93af28e6fc4fd6896b93e3fa0da99642c9a60a49cc6da6f5c1c07a`. The summary job
  re-downloaded the device ZIP through the API, recomputed its digest and compared this run's
  source, run, attempt, name, bytes and expiry.
* Named outcomes: 56 cases per run (50 installed-ABI cases and 6 probe-side checks). With
  `com.google.android.tts` installed 55 pass and one skips (the missing-engine case); after every
  engine package was removed 32 pass and 24 skip (the engine-dependent cases), including a real
  `service_unavailable_when_engine_missing` pass. The cases added by this review are
  `duplicate_terminal_dropped`, `overflow_utterance_id_ignored`,
  `stale_callback_after_destroy_ignored`, `stop_and_close_single_terminal`,
  `speak_high_bit_request_id`, `speak_max_request_id`, `future_callback_ignored_while_active`,
  `future_callback_ignored_while_idle`, `voice_names_match_engine` and
  `voice_selection_returns_to_default`; every original case is kept with its original
  assertions.
* Audio: `files/audio/tts-sample.wav`, 91244 bytes, RIFF/WAVE, sha256
  `83f66b0e6de2231a14b994c4d21260ac5d5d773d376274d6546e5582e6164987`, produced by
  `synthesizeToFile` with the local voice `en-AU-language` while the engine default voice is
  `en-US-language`; the digest computed on the device and the digest of the published file match.
* Packages: AAR 11148 bytes (no native libraries), probe debug APK 91150 bytes with
  `lib/x86_64/libtts-consumer.so` 69288 bytes, baseline APK 8580 bytes, delta 82570 bytes,
  no Maven runtime dependencies.
* Retained failures (not deleted): runs 40123986906 (JNI environment argument missing),
  40124242333 (androidTest APK path) and 40124745606 (summary job demanded an already completed
  run) from the original delivery; 40169096857, 40169276410, 40169702520 and 40170099201 from
  this review (`android.speech.tts.Voice` has no display-name accessor; a wrong assumption about
  the engine voice state before the first explicit voice; a missing diagnostic detail; and a
  rotation wait shorter than the headless emulator's real synthesis). The superseded acceptances
  40170544552 (52 cases, first review acceptance), 40126240859 (46 cases, original delivery) and
  40125579469 remain recorded.
* Not covered: host product wiring, background playback, audio focus, media session, haptics,
  spoken quality on a handset, a genuine engine-level FAILED terminal event and the release
  failure path, other engines, voice timbre (only the engine's reported voice state and the
  rendered bytes are observed), a deterministic reproduction of the destroy-versus-callback
  window without an ASAN build, and long-session thermal behaviour.

## Scope boundaries

* Not accepted by this package: Android host product wiring, background playback,
  audio focus, media session integration, haptics, or any spoken-output quality
  judgement.
* The removed-engine run is a negative path: it grants the refusal behaviour, not
  real reading.
* No emulator audio output is judged; only engine callbacks and the rendered file
  bytes are evidence.
