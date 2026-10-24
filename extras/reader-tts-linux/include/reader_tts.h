/* SPDX-License-Identifier: MIT */
/* EXReader reader TTS C ABI, Linux backend (system Speech Dispatcher).
   This is the frozen J16-J19 interface; only comments and limits are local. */
#ifndef READER_TTS_H
#define READER_TTS_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
#define READER_TTS_VERSION "0.1.0"

/* ---------------------------------------------------------------- backend --
   System Speech Dispatcher (libspeechd) over its local UNIX socket. The package
   ships no speech engine, no daemon and no server: it never spawns or restarts
   speech-dispatcher (spd_open2 autospawn is 0). The daemon is a system service
   owned by the OS; its absence is reported, never repaired here.

   ---------------------------------------------------------------- threads --
   Every entry point except reader_tts_voice_list_free must be called on the
   thread that called reader_tts_create ("the owner"). A call from any other
   thread returns READER_TTS_OWNER and changes no state; it is safe to make such
   a call at any time because the check reads no mutable shared field outside
   the handle mutex. No host event loop is required and no host callback is ever
   invoked: libspeechd's own event thread only appends to a bounded internal
   queue under a private mutex. The library therefore never re-enters the host.
   Only one handle may hold the daemon connection at a time (libspeechd keeps
   process-global state); a second reader_tts_create while another handle owns
   the connection yields a usable handle whose state is SERVICE_UNAVAILABLE.

   ---------------------------------------------------------------- blocking --
   create, voices, speak, pause, resume, stop, observe and poll perform one or a
   few local socket round trips (typically well under a millisecond on a healthy
   daemon) and never sleep. They may block if the daemon accepts a connection but
   stops answering; that is a broken system service, not a library wait. The only
   unbounded wait in the library is inside libspeechd itself.
   request_close never blocks: a library thread releases the connection and the
   state becomes CLOSED when the release finished. SIGPIPE must be ignored by the
   process (a vanished daemon turns a socket write into EPIPE).

   ------------------------------------------------------------------ memory --
   All inputs are copied before use; the caller keeps ownership of its buffers
   and may free them as soon as the call returns. Voice strings and the voice
   array are allocated by the library and released only by
   reader_tts_voice_list_free (which may be called after the handle is gone).
   reader_tts_destroy frees the handle. reader_tts_error carries a status code
   and a platform code only: never message text, and never a byte of the input
   text or a voice selection.

   ------------------------------------------------------------------ errors --
   READER_TTS_ARGUMENT  bad pointer/size/UTF-8/id/rate/voice, or wrong request
   READER_TTS_OWNER     call from a thread that does not own the handle
   READER_TTS_BUSY      another request is active, or destroy before CLOSED
   READER_TTS_UNAVAILABLE  daemon missing, gone, or handle closed
   READER_TTS_UNSUPPORTED  the daemon rejected a native capability
   READER_TTS_IO        the daemon answered with an error
   READER_TTS_MEMORY    allocation failure
   READER_TTS_LIMIT     a documented hard limit would be exceeded
   native_code is the libspeechd/errno value when there is one, else 0. */

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

/* ---------------------------------------------------------- hard limits ----
   READER_TTS_DEFAULT_MAX_UTF8  input ceiling per request; also the default.
   READER_TTS_EVENT_CAPACITY    queue ceiling; a request needs room for two
                                events (STARTED plus one terminal) or speak
                                fails with LIMIT and changes nothing.
   READER_TTS_MAX_VOICES        voice count ceiling (LIMIT above this). The
                                espeak-ng module lists several thousand voices, so
                                the ceiling is high; only the pointer array and the
                                bounded strings are allocated.
   READER_TTS_MAX_VOICE_FIELD   bytes per id/name/language (LIMIT above this).
   READER_TTS_ID_MEMORY         request ids remembered per handle for reuse
                                detection; an id reused after this many later
                                requests is no longer detected. */
#define READER_TTS_DEFAULT_MAX_UTF8 16384u
#define READER_TTS_EVENT_CAPACITY 128u
#define READER_TTS_MAX_VOICES 65536u
#define READER_TTS_MAX_VOICE_FIELD 256u
#define READER_TTS_ID_MEMORY 256u

/* create: cfg may be NULL (16 KiB input ceiling). cfg->struct_size must be at
   least sizeof(reader_tts_config); max_utf8_bytes 0 selects the ceiling and a
   larger value is ARGUMENT (a config may only lower the limit). Opens the local
   socket synchronously, without spawning anything. Returns OK and a usable
   handle in both cases: when the daemon is absent (or another handle owns the
   process connection) the state is SERVICE_UNAVAILABLE and the first speak that
   finds a daemon reconnects. The handle must be closed with request_close,
   driven to CLOSED, then destroyed. */
reader_tts_status reader_tts_create(const reader_tts_config *, reader_tts **, reader_tts_error *);
/* voices: fills *out on OK (count may be 0 when the daemon lists nothing). id is
   the Speech Dispatcher synthesis voice name and is what speak accepts; name
   repeats it, language is the daemon's language tag. Output strings are library
   owned; release with reader_tts_voice_list_free. On failure *out is emptied. */
reader_tts_status reader_tts_voices(reader_tts *, reader_tts_voice_list *, reader_tts_error *);
void reader_tts_voice_list_free(reader_tts_voice_list *);
/* speak: request_id must be non-zero and not reused on this handle. text is
   bytes long, strict UTF-8, free of NUL, 1..max_utf8_bytes; the library copies
   it and never borrows the caller's buffer. voice_id NULL or "" selects the
   daemon's current default; an id the daemon does not list is ARGUMENT. rate is
   finite in 0.5..2.0 and maps piecewise-linearly onto Speech Dispatcher's
   -100..100 relative rate (0.5 -> -100, 1.0 -> 0, 2.0 -> 100); it is a relative
   speaking-rate setting, not an exact duration ratio. One request may be active
   at a time: a second speak returns BUSY and does not interrupt. The text is one
   chunk; longer text is split by the host into requests with new ids. */
reader_tts_status reader_tts_speak(reader_tts *, uint64_t request_id,
  const char *utf8, size_t bytes, const char *voice_id, double rate, reader_tts_error *);
/* pause/resume: act on the active request named by request_id. A wrong id is
   ARGUMENT, already-paused/already-resumed is OK without a daemon round trip.
   When the daemon refuses the native pause it is UNSUPPORTED and the state is
   unchanged. */
reader_tts_status reader_tts_pause(reader_tts *, uint64_t request_id, reader_tts_error *);
reader_tts_status reader_tts_resume(reader_tts *, uint64_t request_id, reader_tts_error *);
/* stop: ends the active request with exactly one STOPPED event; a request that
   already ended is OK and adds no second event; an id that was never started is
   ARGUMENT. */
reader_tts_status reader_tts_stop(reader_tts *, uint64_t request_id, reader_tts_error *);
/* observe: snapshot of state, last_status, the active (else most recent) request
   id and the backend capability bits. CAN_PAUSE is reported because the backend
   implements pause, independently of whether a daemon is reachable right now;
   CAN_REPORT_RANGE is never set (Speech Dispatcher reports message-level events
   and no UTF-16 progress, so no byte range is ever invented). */
reader_tts_status reader_tts_observe(reader_tts *, reader_tts_snapshot *, reader_tts_error *);
/* poll: pops one event (available=1) or clears the event (available=0). Events
   keep request order; a late daemon callback for an earlier request never alters
   a newer request. Queued events stay readable in CLOSING and CLOSED so the
   terminal event of an interrupted request is not lost. While a request is
   active, poll also notices a daemon that stopped answering and then queues
   FAILED/UNAVAILABLE. STARTED means the daemon reported the message started;
   RANGE is never emitted. */
reader_tts_status reader_tts_poll(reader_tts *, reader_tts_event *, int *available, reader_tts_error *);
/* request_close: non-blocking and idempotent. Moves to CLOSING, stops the active
   request with one STOPPED event, and releases the connection from a library
   thread; the state becomes CLOSED only after the daemon connection and its
   event thread are gone. */
reader_tts_status reader_tts_request_close(reader_tts *, reader_tts_error *);
/* destroy: BUSY (pointer kept, nothing changed) until the state is CLOSED; then
   frees the handle and sets *handle to NULL. */
reader_tts_status reader_tts_destroy(reader_tts **, reader_tts_error *);
#ifdef __cplusplus
}
#endif
#endif
