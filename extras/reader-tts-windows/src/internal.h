/* SPDX-License-Identifier: MIT */
/* Internal state shared by the C ABI layer (reader_tts.c) and the SAPI worker
   (sapi_worker.c). Nothing here is installed or visible to callers.

   Threads: only the owner thread (the one that called reader_tts_create) runs the
   functions in reader_tts.c. The worker is a single thread that owns every SAPI/COM
   object; it never calls back into the API layer, the host or any allocator the host
   controls. Both sides share this structure through one critical section and two
   auto-reset events (a command slot and its acknowledgement).

   Command ownership: the owner fills h->cmd and signals cmd_event; the worker copies
   the command out, clears the slot, and then owns every payload pointer in it
   (text, unit_map, voice_id, wav_path) until it frees them. The worker writes
   ack_result/ack_native/ack_voices under the lock and signals ack_event. */
#ifndef EXR_TTS_INTERNAL_H
#define EXR_TTS_INTERNAL_H

#include "reader_tts.h"
#include "reader_tts_windows.h"
#include <wchar.h>
#include <windows.h>

/* Contract limits (tts-contract.md): default and hard maximum are 16 KiB. */
#define EXR_TTS_DEFAULT_MAX_UTF8 16384u
#define EXR_TTS_HARD_MAX_UTF8 16384u
/* Bounded event queue. Control events (STARTED/terminal) can use the whole queue;
   RANGE events may occupy at most the first 112 slots, so 16 slots always remain
   for STARTED plus one terminal event per queued request. Beyond that the queue
   reports READER_TTS_LIMIT instead of growing. */
#define EXR_TTS_QUEUE_CAPACITY 128u
#define EXR_TTS_RANGE_CAPACITY 112u
#define EXR_TTS_WAV_PATH_MAX 1024u

typedef struct {
  uint64_t request_id;
  reader_tts_event_kind kind;
  reader_tts_status status;
  size_t start, end;
  int has_range;
} exr_tts_queue_event;

typedef enum {
  EXR_TTS_CMD_NONE = 0,
  EXR_TTS_CMD_SPEAK,
  EXR_TTS_CMD_PAUSE,
  EXR_TTS_CMD_RESUME,
  EXR_TTS_CMD_STOP,
  EXR_TTS_CMD_VOICES,
  EXR_TTS_CMD_SET_WAV,
  EXR_TTS_CMD_CLOSE
} exr_tts_cmd_kind;

typedef struct {
  exr_tts_cmd_kind kind;
  uint64_t request_id;
  double rate;
  wchar_t *text;          /* worker-owned after the command is taken */
  size_t text_units;
  size_t *unit_map;       /* text_units + 1 UTF-16 unit -> UTF-8 byte offsets */
  size_t text_bytes;
  wchar_t *voice_id;      /* NULL: system default voice */
  wchar_t *wav_path;      /* NULL: default audio device */
  reader_tts_status result;
  int native_code;
  reader_tts_voice_list voices;
} exr_tts_command;

struct reader_tts {
  DWORD owner_thread;
  size_t max_utf8_bytes;
  CRITICAL_SECTION lock;
  HANDLE cmd_event;
  HANDLE ack_event;
  HANDLE worker;
  int worker_started;
  int worker_exited;
  int cmd_pending;
  exr_tts_command cmd;
  reader_tts_status ack_result;
  int ack_native;
  reader_tts_voice_list ack_voices;
  reader_tts_state state;
  reader_tts_status last_status;
  unsigned capabilities;
  uint64_t active_request;
  uint64_t last_request_id;
  int overflow;
  exr_tts_queue_event events[EXR_TTS_QUEUE_CAPACITY];
  size_t head, count;
  wchar_t *wav_path;
  volatile LONG close_requested;
  /* Engine status of the last query, published for the package's acceptance probe. */
  int probe_hresult;
  unsigned probe_running, probe_word_pos, probe_word_len, probe_stream, probe_last_queued;
  unsigned probe_samples;
  int probe_event_hresult;
  unsigned probe_event_calls, probe_event_total, probe_last_event_id;
  /* Set once the engine reports a word position or a word-boundary event, i.e. only
     then can this handle advertise READER_TTS_CAN_REPORT_RANGE. */
  int position_seen;
};

/* reader_tts.c: accounting, validation, queue and owner-side plumbing. */
void *exr_tts_alloc(size_t bytes);
void exr_tts_release(void *block);
wchar_t *exr_tts_wcsdup(const wchar_t *source);
void exr_tts_publish(reader_tts *handle, reader_tts_state state, reader_tts_status last,
                     unsigned capabilities, uint64_t active_request);
reader_tts_status exr_tts_push(reader_tts *handle, const exr_tts_queue_event *event);
reader_tts_status exr_tts_send(reader_tts *handle, exr_tts_command *command, int wait);
void exr_tts_remember(reader_tts *handle, reader_tts_status status);
uint64_t exr_tts_active(reader_tts *handle);
wchar_t *exr_tts_copy_wav_path(reader_tts *handle);
int exr_tts_closing(reader_tts *handle);
reader_tts_status exr_tts_utf8_to_utf16(const char *utf8, size_t bytes, wchar_t **text,
                                        size_t *units, size_t **unit_map);
unsigned exr_tts_capabilities(reader_tts *handle);

/* Process-wide debug hooks (declared in reader_tts_windows.h). */
long exr_tts_debug_no_service(void);
long exr_tts_debug_init_delay(void);

/* sapi_worker.c */
DWORD WINAPI exr_tts_worker_main(LPVOID parameter);

#endif
