/* SPDX-License-Identifier: MIT */
/*
 * reader_tts.h - EXReader text-to-speech C ABI 0.1.0, Windows SAPI 5 backend.
 *
 * The types and functions below are the frozen common contract
 * (docs/handoffs/reader-next-wave/tts-contract.md); only this comment may differ
 * between the four platform packages.
 *
 * Ownership, memory and threads
 *  - Every function except reader_tts_voice_list_free() must run on the thread that
 *    called reader_tts_create() (the owner); any other thread gets READER_TTS_OWNER
 *    and the handle is left exactly as it was. Windows needs no message loop on the
 *    owner: SAPI runs on a package-owned worker thread that never calls the host.
 *  - Nothing is ever delivered by callback: the worker polls the engine and converts
 *    progress into pure values in a bounded internal queue that the host drains with
 *    reader_tts_poll().
 *  - Text passed to reader_tts_speak() is copied; the caller's buffer is free on
 *    return. The copy lives until that request's terminal event.
 *  - Strings in a reader_tts_voice_list belong to the list until
 *    reader_tts_voice_list_free(); that call needs no live handle and is idempotent
 *    (a second call on the emptied list, or on NULL, is a no-op).
 *  - Every function accepts error == NULL. When non-NULL, *error is written on every
 *    return, including on success (code OK, native_code 0). native_code carries the
 *    raw SAPI/COM HRESULT when the failure came from SAPI, and 0 otherwise.
 *  - Reentrancy: the API never calls the host, so no host callback can re-enter it.
 *
 * State machine
 *  - create() returns OK and the handle starts INITIALIZING; the worker then publishes
 *    READY or SERVICE_UNAVAILABLE (no speech service, no voice token). INITIALIZING is
 *    not ready: reader_tts_speak()/reader_tts_voices() answer READER_TTS_UNAVAILABLE.
 *  - READY -> SPEAKING on an accepted speak; SPEAKING <-> PAUSED; SPEAKING/PAUSED ->
 *    READY on the request's terminal event; any state -> CLOSING on
 *    reader_tts_request_close(); CLOSING -> CLOSED once the backend is torn down.
 *  - A per-state summary: observe() and poll() work in every state (poll reports
 *    available == 0 when nothing is queued, including after CLOSED); voices() answers
 *    UNAVAILABLE while INITIALIZING/SERVICE_UNAVAILABLE and ARGUMENT after CLOSING;
 *    speak()/pause()/resume()/stop() answer ARGUMENT after CLOSING; request_close() is
 *    idempotent; destroy() answers BUSY (and keeps the pointer) before CLOSED.
 *
 * Requests, ids and cancellation
 *  - request_id must be nonzero and strictly greater than the last accepted id on that
 *    handle (a repeated or smaller id is ARGUMENT; a rejected call does not consume an
 *    id). One request is active at a time: speak() while one is active is READER_TTS_BUSY
 *    and never interrupts it.
 *  - Each accepted request produces exactly one STARTED and exactly one terminal event
 *    (FINISHED, STOPPED or FAILED). After reader_tts_stop() is accepted, the queue
 *    receives that single STOPPED for the old request and nothing else for it; late
 *    backend events keep no route into a newer request.
 *  - reader_tts_session close (request_close) stops the active request the same way and
 *    then releases the voice; CLOSED is reported only after that is complete.
 *  - speak() returning an error means no request started and therefore no event.
 *
 * Text, ranges and limits
 *  - max_utf8_bytes 0 means 16384; the hard ceiling is 16384 and values above it are
 *    ARGUMENT, smaller values lower this handle's limit. Over-long text is
 *    READER_TTS_LIMIT: the host splits it and uses a new request id per chunk.
 *  - Text must be strict UTF-8 (no embedded NUL, no truncated scalar, no overlong form,
 *    no surrogate, nothing above U+10FFFF); anything else is ARGUMENT.
 *  - RANGE events carry UTF-8 byte offsets into the text that was passed in: the
 *    engine's current-word position (ISpVoice::GetStatus ulInputWordPos/Len, UTF-16
 *    code units of the text that was spoken) is converted through a per-request map, so
 *    start/end always fall on a byte boundary even inside a surrogate pair. The
 *    position is sampled, not predicted from a clock: a word shorter than the poll
 *    interval can be skipped, and neighbours may arrive merged. Ranges are monotonic
 *    and inside [0, bytes); a reported position outside the text is FAILED with
 *    READER_TTS_IO, never clamped into a plausible value.
 *  - The queue holds at most 128 events; at most 112 of them may be RANGE, and
 *    neighbours separated by at most one byte of whitespace are merged instead of
 *    growing the queue. Exhaustion is reported: poll()/speak() then answer
 *    READER_TTS_LIMIT and the handle must be closed.
 *
 * Rate and voices
 *  - rate is finite in 0.5..2.0 (NaN and infinities are ARGUMENT). Windows maps it to
 *    the SAPI -10..10 rate scale logarithmically: round(log2(rate) * 10). That is an
 *    engine preference, not a duration ratio, and this header does not promise one.
 *  - voice_id NULL or "" selects the system default. A non-empty id must be one of the
 *    ids returned by reader_tts_voices(); any other value is ARGUMENT.
 *
 * Capabilities reported on Windows once READY: READER_TTS_CAN_PAUSE |
 * READER_TTS_CAN_REPORT_RANGE. Synthesis succeeds only if the machine has at least one
 * SAPI voice token; without one the handle stays SERVICE_UNAVAILABLE and no mock stands
 * in for speech.
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
reader_tts_status reader_tts_create(const reader_tts_config *, reader_tts **, reader_tts_error *);
reader_tts_status reader_tts_voices(reader_tts *, reader_tts_voice_list *, reader_tts_error *);
void reader_tts_voice_list_free(reader_tts_voice_list *);
reader_tts_status reader_tts_speak(reader_tts *, uint64_t request_id,
  const char *utf8, size_t bytes, const char *voice_id, double rate, reader_tts_error *);
reader_tts_status reader_tts_pause(reader_tts *, uint64_t request_id, reader_tts_error *);
reader_tts_status reader_tts_resume(reader_tts *, uint64_t request_id, reader_tts_error *);
reader_tts_status reader_tts_stop(reader_tts *, uint64_t request_id, reader_tts_error *);
reader_tts_status reader_tts_observe(reader_tts *, reader_tts_snapshot *, reader_tts_error *);
reader_tts_status reader_tts_poll(reader_tts *, reader_tts_event *, int *available, reader_tts_error *);
reader_tts_status reader_tts_request_close(reader_tts *, reader_tts_error *);
reader_tts_status reader_tts_destroy(reader_tts **, reader_tts_error *);
#ifdef __cplusplus
}
#endif
#endif