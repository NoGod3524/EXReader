/* SPDX-License-Identifier: MIT */
/* EXReader text-to-speech C ABI, Android backend (frozen interface 0.1.0).
 *
 * Contract summary (see docs/READER-TTS-ANDROID.md for the full text):
 *  - Owner: every call except the voice-list free must run on the thread that
 *    called reader_tts_create; other threads get READER_TTS_OWNER and no state
 *    changes. Android needs no particular looper on the owner thread, but the
 *    host must not block the process main thread while waiting for READY
 *    (TextToSpeech delivers its init callback there).
 *  - Memory: the input text is copied by reader_tts_speak. Voice lists own
 *    their strings until reader_tts_voice_list_free. Events are plain values.
 *  - Threads/reentrancy: system callbacks never call the host; they only write
 *    a bounded queue (128 events) that reader_tts_poll drains. No function
 *    may be called from inside another's callback because there are none.
 *  - Limits: max_utf8_bytes 0 means 16 KiB and can only be lowered; the Android
 *    engine additionally refuses text longer than
 *    TextToSpeech.getMaxSpeechInputLength() UTF-16 units (READER_TTS_LIMIT,
 *    never truncated). Hosts chunk with org.exreader.tts.Chunker and give each
 *    chunk a new, strictly increasing request id.
 *  - Request ids: non-zero, strictly increasing per handle (a stronger form of
 *    "never reused"). The whole uint64 range is usable: the id crosses the JNI
 *    boundary as unsigned decimal, so values at or above 2^63 are preserved.
 *    One active request at a time. An engine callback is consumed only while
 *    its id is the active accepted request; an id that is not a decimal
 *    uint64, was never accepted, is still unused or already ended is ignored
 *    and never reaches the queue.
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
/* Compile-time constants of this implementation. */
enum {
  READER_TTS_DEFAULT_MAX_UTF8_BYTES = 16384, /* also the hard upper bound */
  READER_TTS_EVENT_CAPACITY = 128,
  READER_TTS_MAX_VOICES = 1024,
  READER_TTS_MAX_VOICE_FIELD_BYTES = 255
};

/* create: struct_size must equal sizeof(reader_tts_config) (NULL config means
   defaults). Returns OK with state INITIALIZING (or already SERVICE_UNAVAILABLE
   when the engine could not be reached); the handle exists in both cases. On
   any failure *out is NULL. UNAVAILABLE if the Android layer was not bound by
   reader_tts_android_initialize. */
reader_tts_status reader_tts_create(const reader_tts_config *, reader_tts **, reader_tts_error *);
/* voices: installed voices only (never triggers a download). BUSY while
   INITIALIZING; UNAVAILABLE when SERVICE_UNAVAILABLE/CLOSING/CLOSED; LIMIT if
   more than READER_TTS_MAX_VOICES or an over-long field. Empty list is OK. */
reader_tts_status reader_tts_voices(reader_tts *, reader_tts_voice_list *, reader_tts_error *);
void reader_tts_voice_list_free(reader_tts_voice_list *);
/* speak: copies the text. ARGUMENT for id 0 / not greater than every earlier
   id / NULL / empty text / invalid UTF-8 / embedded NUL / unknown voice id /
   rate not finite in 0.5..2.0; LIMIT over the byte limit, over the engine
   limit or event queue without room; BUSY while INITIALIZING or while another
   request is active; UNAVAILABLE in SERVICE_UNAVAILABLE/CLOSING/CLOSED.
   rate maps 1:1 to TextToSpeech.setSpeechRate (engines may clamp; no exact
   duration ratio is promised). Every accepted request yields exactly one
   FINISHED/STOPPED/FAILED event. */
reader_tts_status reader_tts_speak(reader_tts *, uint64_t request_id,
  const char *utf8, size_t bytes, const char *voice_id, double rate, reader_tts_error *);
/* Android TextToSpeech has no pause: UNSUPPORTED, state unchanged. */
reader_tts_status reader_tts_pause(reader_tts *, uint64_t request_id, reader_tts_error *);
reader_tts_status reader_tts_resume(reader_tts *, uint64_t request_id, reader_tts_error *);
/* stop: the active request ends with exactly one STOPPED event, queued by this
   call once the platform accepted the stop, and the handle is READY again. A
   later engine callback for the same request is a duplicate and is dropped.
   Stopping an id at or below the last accepted id that is not active is OK (it
   ended earlier); an id above every accepted id, or zero, is ARGUMENT. */
reader_tts_status reader_tts_stop(reader_tts *, uint64_t request_id, reader_tts_error *);
reader_tts_status reader_tts_observe(reader_tts *, reader_tts_snapshot *, reader_tts_error *);
/* poll: *available=0 and a zeroed event when empty. */
reader_tts_status reader_tts_poll(reader_tts *, reader_tts_event *, int *available, reader_tts_error *);
/* request_close: non-blocking, idempotent; ends an active request with its one
   STOPPED event and releases the engine. The handle is CLOSED only after the
   system resources are released and no callback can arrive any more. */
reader_tts_status reader_tts_request_close(reader_tts *, reader_tts_error *);
/* destroy: BUSY (pointer kept) until CLOSED; then frees and sets *handle NULL. */
reader_tts_status reader_tts_destroy(reader_tts **, reader_tts_error *);
#ifdef __cplusplus
}
#endif
#endif
