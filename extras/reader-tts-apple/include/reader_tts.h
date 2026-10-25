/* SPDX-License-Identifier: MIT */
/*
 * reader_tts.h - EXReaderTTSApple 0.1.0: native speech for macOS, iPhone, iPad.
 *
 * Frozen common ABI (docs/handoffs/reader-next-wave/tts-contract.md); only
 * comments are added here. Backend: AVFoundation AVSpeechSynthesizer with the
 * voices already installed on the device. Nothing is downloaded, no cloud TTS,
 * no book access, no SDK handle.
 *
 * THREADING / OWNER
 *  - reader_tts_create must run on the process MAIN thread (AVSpeechSynthesizer
 *    is driven by the main run loop). That thread is the handle's owner.
 *  - Every other call (including observe, poll, destroy) must come from the
 *    owner; any other thread gets READER_TTS_OWNER and the handle is untouched.
 *    reader_tts_voice_list_free may run on any thread.
 *  - The host runs the main CFRunLoop/NSRunLoop (UIApplication/NSApplication do
 *    this). System callbacks only append to an internal queue of at most 128
 *    plain-value events; the library never calls into the host. Calls never
 *    block waiting for the run loop; the host pumps the run loop and calls
 *    reader_tts_poll until it reports no event.
 *  - Every system delivery is handled on the owner thread: the backend already
 *    receives AVSpeechSynthesizer delegate calls there, and a delivery offered on
 *    any other thread is re-queued to the main queue before it can touch the
 *    internal queue. So no library state is ever mutated off the owner thread,
 *    and no callback can reach the handle after reader_tts_destroy.
 *  - The queue is reserved for the active request: speak needs three free slots
 *    (STARTED, at most one coalesced RANGE, one terminal) and returns LIMIT
 *    otherwise. A host that never polls therefore sees LIMIT, never a lost
 *    terminal event.
 *
 * AUDIO SESSION / BACKGROUND
 *  - The library never configures AVAudioSession and never opens one; on iOS the
 *    host chooses category and background audio policy and should call
 *    reader_tts_stop (or request_close) when it loses the right to speak. The
 *    host also decides whether speaking continues in the background.
 *
 * MEMORY
 *  - speak copies its input (<= max_utf8_bytes). Voice lists are owned by the
 *    caller until reader_tts_voice_list_free (independent of the handle).
 *    Events and snapshots are plain values. Nothing is borrowed from the caller.
 *
 * RATE MAPPING (approximate, not an exact duration ratio)
 *  - rate 1.0 -> AVSpeechUtteranceDefaultSpeechRate (0.5); 0.5 -> 0.25;
 *    2.0 -> 0.75; piecewise linear in between. AVFoundation treats utterance
 *    rate as a speech-rate hint, so wall-clock duration is not 1/rate.
 *
 * REQUEST IDS
 *  - Non-zero, host allocated, and (stricter than "never reused", so the
 *    library needs no unbounded history) strictly increasing per handle among
 *    ACCEPTED requests. Reusing an accepted id, or passing 0, is ARGUMENT.
 *
 * TIMERS WITHOUT A HOST CALLBACK
 *  - A request that was told to stop and a request_close that the system never
 *    confirms are both resolved by a 2 s steady-clock deadline that is evaluated
 *    on the next owner call (observe/poll/speak/stop/request_close/destroy).
 *    The host is expected to call observe or poll regularly anyway.
 *
 * NATIVE ERROR CODES (reader_tts_error.native_code, AVFoundation backend)
 *  - 1001 wrong thread, 1002 unknown/unavailable voice, 1003 unusable text or
 *    backend, 1004 the system refused the control call. 0 means "no code".
 *
 * ERRORS
 *  - ARGUMENT bad pointer/value/unknown voice/stale, reused or unknown request
 *    id; OWNER wrong thread; BUSY a request is active (or pause/resume not yet
 *    possible); UNAVAILABLE service down/closing/closed; UNSUPPORTED missing
 *    native capability; IO the engine refused; MEMORY allocation failed; LIMIT
 *    text over the cap or no room to reserve the next request's events (poll,
 *    then retry). State is unchanged by every non-OK return.
 */
#ifndef READER_TTS_H
#define READER_TTS_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
#define READER_TTS_VERSION "0.1.0"
typedef struct reader_tts reader_tts;
typedef enum {
  READER_TTS_OK=0, READER_TTS_ARGUMENT, READER_TTS_OWNER,
  READER_TTS_BUSY, READER_TTS_UNAVAILABLE, READER_TTS_UNSUPPORTED,
  READER_TTS_IO, READER_TTS_MEMORY, READER_TTS_LIMIT
} reader_tts_status;
typedef enum {
  READER_TTS_INITIALIZING=0, READER_TTS_READY, READER_TTS_SPEAKING,
  READER_TTS_PAUSED, READER_TTS_STOPPING, READER_TTS_CLOSING,
  READER_TTS_CLOSED, READER_TTS_SERVICE_UNAVAILABLE
} reader_tts_state;
typedef struct { size_t struct_size, max_utf8_bytes; } reader_tts_config;
typedef struct { reader_tts_status code; int native_code; } reader_tts_error;
typedef struct { char *id, *name, *language; } reader_tts_voice;
typedef struct { reader_tts_voice *voices; size_t count; } reader_tts_voice_list;
enum { READER_TTS_CAN_PAUSE=1, READER_TTS_CAN_REPORT_RANGE=2 };
typedef struct {
  reader_tts_state state;
  reader_tts_status last_status;
  uint64_t request_id;
  unsigned capabilities;
} reader_tts_snapshot;
typedef enum {
  READER_TTS_STARTED=0, READER_TTS_RANGE, READER_TTS_FINISHED,
  READER_TTS_STOPPED, READER_TTS_FAILED
} reader_tts_event_kind;
typedef struct {
  uint64_t request_id;
  reader_tts_event_kind kind;
  reader_tts_status status;
  size_t start, end;
  int has_range;
} reader_tts_event;

/* Hard limits. Voices above READER_TTS_MAX_VOICES are not reported (the list is
 * truncated in system order, never reordered or synthesized). */
#define READER_TTS_MAX_UTF8_BYTES 16384u
#define READER_TTS_MAX_EVENTS 128u
#define READER_TTS_MAX_VOICES 1024u
#define READER_TTS_CLOSE_DEADLINE_MS 2000u

/* config may be NULL (defaults). struct_size >= sizeof(reader_tts_config);
 * max_utf8_bytes 0 -> 16 KiB, > 16 KiB -> LIMIT (the cap can only be lowered).
 * Must run on the main thread (else OWNER). Returns OK with the handle in READY,
 * or in SERVICE_UNAVAILABLE when the system has no installed voice (speak then
 * returns UNAVAILABLE). Initialization never returns INITIALIZING for this
 * backend. On any non-OK return *handle is NULL and nothing is allocated. */
reader_tts_status reader_tts_create(const reader_tts_config *, reader_tts **, reader_tts_error *);
/* Installed voices only, never downloads. On failure the list is empty. */
reader_tts_status reader_tts_voices(reader_tts *, reader_tts_voice_list *, reader_tts_error *);
void reader_tts_voice_list_free(reader_tts_voice_list *);
/* Starts one request. voice_id NULL/"" = system default voice. */
reader_tts_status reader_tts_speak(reader_tts *, uint64_t request_id,
  const char *utf8, size_t bytes, const char *voice_id, double rate, reader_tts_error *);
/* pause/resume are idempotent for the active request id. */
reader_tts_status reader_tts_pause(reader_tts *, uint64_t request_id, reader_tts_error *);
reader_tts_status reader_tts_resume(reader_tts *, uint64_t request_id, reader_tts_error *);
/* Asks the active request to stop; its STOPPED event arrives via poll. Repeating
 * stop for a request already STOPPING is OK. */
reader_tts_status reader_tts_stop(reader_tts *, uint64_t request_id, reader_tts_error *);
reader_tts_status reader_tts_observe(reader_tts *, reader_tts_snapshot *, reader_tts_error *);
/* Pops one event. *available=0 and event zeroed when none. Allowed after close
 * until destroy so terminal events are never lost. */
reader_tts_status reader_tts_poll(reader_tts *, reader_tts_event *, int *available, reader_tts_error *);
/* Non-blocking, idempotent. CLOSED is reached from the run loop (or, if the
 * system never confirms within 2 s, from the next observe/poll/destroy call). */
reader_tts_status reader_tts_request_close(reader_tts *, reader_tts_error *);
/* BUSY and pointer kept until state is CLOSED; success sets *handle = NULL. */
reader_tts_status reader_tts_destroy(reader_tts **, reader_tts_error *);
#ifdef __cplusplus
}
#endif
#endif
