/* SPDX-License-Identifier: MIT */
/* EXReader TTS 0.1.0 C ABI: argument/state validation, the serial owner rule, the
   bounded event queue and strict UTF-8 handling. Every SAPI/COM call happens on the
   worker thread in sapi_worker.c; this file never touches COM. */
#include "internal.h"
#include <stdlib.h>
#include <string.h>

#define EXR_TTS_ACK_TIMEOUT_MS 20000u

static volatile LONG g_live_allocations;
static volatile LONG g_fail_after;
static volatile LONG g_simulate_no_service;
static volatile LONG g_init_delay_ms;

/* ---- accounting and fault injection (process-wide, any thread) ---- */

/* True exactly once, for the n-th allocation after the debug hook was set. */
static int allocation_must_fail(void) {
  LONG value = InterlockedCompareExchange(&g_fail_after, 0, 0);
  for (;;) {
    LONG next;
    if (value <= 0) return 0;
    next = value - 1;
    if (InterlockedCompareExchange(&g_fail_after, next, value) == value) return next == 0;
    value = InterlockedCompareExchange(&g_fail_after, 0, 0);
  }
}

void *exr_tts_alloc(size_t bytes) {
  void *block;
  if (allocation_must_fail()) return NULL;
  block = calloc(1, bytes ? bytes : 1);
  if (block) InterlockedIncrement(&g_live_allocations);
  return block;
}

void exr_tts_release(void *block) {
  if (!block) return;
  free(block);
  InterlockedDecrement(&g_live_allocations);
}

void reader_tts_windows_debug_fail_allocation_after(unsigned n) {
  InterlockedExchange(&g_fail_after, (LONG)n);
}

long reader_tts_windows_debug_live_allocations(void) {
  return (long)InterlockedCompareExchange(&g_live_allocations, 0, 0);
}

void reader_tts_windows_debug_simulate_no_service(int enabled) {
  InterlockedExchange(&g_simulate_no_service, enabled ? 1 : 0);
}

void reader_tts_windows_debug_init_delay_ms(unsigned ms) {
  InterlockedExchange(&g_init_delay_ms, (LONG)ms);
}

long exr_tts_debug_no_service(void) {
  return (long)InterlockedCompareExchange(&g_simulate_no_service, 0, 0);
}

long exr_tts_debug_init_delay(void) {
  return (long)InterlockedCompareExchange(&g_init_delay_ms, 0, 0);
}

wchar_t *exr_tts_wcsdup(const wchar_t *source) {
  size_t units = 0;
  wchar_t *copy;
  if (!source) return NULL;
  while (source[units]) units++;
  copy = (wchar_t *)exr_tts_alloc((units + 1) * sizeof(wchar_t));
  if (!copy) return NULL;
  memcpy(copy, source, (units + 1) * sizeof(wchar_t));
  return copy;
}

/* ---- shared state helpers ---- */

void exr_tts_publish(reader_tts *handle, reader_tts_state state, reader_tts_status last,
                     unsigned capabilities, uint64_t active_request) {
  EnterCriticalSection(&handle->lock);
  handle->state = state;
  handle->last_status = last;
  handle->capabilities = capabilities;
  handle->active_request = active_request;
  LeaveCriticalSection(&handle->lock);
}

void exr_tts_remember(reader_tts *handle, reader_tts_status status) {
  EnterCriticalSection(&handle->lock);
  handle->last_status = status;
  LeaveCriticalSection(&handle->lock);
}

uint64_t exr_tts_active(reader_tts *handle) {
  uint64_t value;
  EnterCriticalSection(&handle->lock);
  value = handle->active_request;
  LeaveCriticalSection(&handle->lock);
  return value;
}

int exr_tts_closing(reader_tts *handle) {
  return InterlockedCompareExchange(&handle->close_requested, 0, 0) != 0;
}

wchar_t *exr_tts_copy_wav_path(reader_tts *handle) {
  wchar_t *copy = NULL;
  EnterCriticalSection(&handle->lock);
  if (handle->wav_path) copy = exr_tts_wcsdup(handle->wav_path);
  LeaveCriticalSection(&handle->lock);
  return copy;
}

/* Bounded queue: 112 slots for RANGE (contiguous ranges merge into one entry) and
   the full 128 for control events. Exhaustion is reported, never dropped silently. */
reader_tts_status exr_tts_push(reader_tts *handle, const exr_tts_queue_event *event) {
  reader_tts_status status = READER_TTS_OK;
  EnterCriticalSection(&handle->lock);
  if (handle->overflow) {
    status = READER_TTS_LIMIT;
  } else if (event->kind == READER_TTS_RANGE && handle->count >= EXR_TTS_RANGE_CAPACITY) {
    size_t i;
    int merged = 0;
    for (i = handle->count; i > 0; i--) {
      exr_tts_queue_event *slot = &handle->events[(handle->head + i - 1) % EXR_TTS_QUEUE_CAPACITY];
      if (slot->kind != READER_TTS_RANGE || slot->request_id != event->request_id) continue;
      /* Adjacent words are separated by one byte of whitespace; a wider gap is a
         real discontinuity and must not be hidden by merging. */
      if (event->start <= slot->end + 1) {
        if (event->end > slot->end) slot->end = event->end;
        merged = 1;
      }
      break;
    }
    if (!merged) {
      handle->overflow = 1;
      status = READER_TTS_LIMIT;
    }
  } else if (handle->count >= EXR_TTS_QUEUE_CAPACITY) {
    handle->overflow = 1;
    status = READER_TTS_LIMIT;
  } else {
    handle->events[(handle->head + handle->count) % EXR_TTS_QUEUE_CAPACITY] = *event;
    handle->count++;
  }
  LeaveCriticalSection(&handle->lock);
  return status;
}

reader_tts_status exr_tts_send(reader_tts *handle, exr_tts_command *command, int wait) {
  DWORD waited;
  reader_tts_status status;
  EnterCriticalSection(&handle->lock);
  if (handle->worker_exited) {
    LeaveCriticalSection(&handle->lock);
    return READER_TTS_IO;
  }
  if (handle->cmd_pending) {
    LeaveCriticalSection(&handle->lock);
    return READER_TTS_BUSY;
  }
  handle->cmd = *command;
  handle->cmd_pending = 1;
  handle->ack_result = READER_TTS_OK;
  handle->ack_native = 0;
  LeaveCriticalSection(&handle->lock);
  SetEvent(handle->cmd_event);
  if (!wait) return READER_TTS_OK;
  waited = WaitForSingleObject(handle->ack_event, EXR_TTS_ACK_TIMEOUT_MS);
  EnterCriticalSection(&handle->lock);
  status = handle->ack_result;
  LeaveCriticalSection(&handle->lock);
  if (waited != WAIT_OBJECT_0) return READER_TTS_IO;
  return status;
}

/* ---- strict UTF-8 ---- */

static reader_tts_status validate_utf8(const char *text, size_t bytes) {
  size_t i = 0;
  while (i < bytes) {
    unsigned char lead = (unsigned char)text[i];
    size_t extra, k;
    unsigned long code;
    if (lead == 0) return READER_TTS_ARGUMENT;
    if (lead < 0x80) { i++; continue; }
    if ((lead & 0xE0) == 0xC0) { extra = 1; code = lead & 0x1Fu; if (code < 2) return READER_TTS_ARGUMENT; }
    else if ((lead & 0xF0) == 0xE0) { extra = 2; code = lead & 0x0Fu; }
    else if ((lead & 0xF8) == 0xF0) { extra = 3; code = lead & 0x07u; }
    else return READER_TTS_ARGUMENT;
    if (bytes - i <= extra) return READER_TTS_ARGUMENT;
    for (k = 1; k <= extra; k++) {
      unsigned char cont = (unsigned char)text[i + k];
      if ((cont & 0xC0) != 0x80) return READER_TTS_ARGUMENT;
      code = (code << 6) | (cont & 0x3Fu);
    }
    if (extra == 2 && code < 0x800UL) return READER_TTS_ARGUMENT;
    if (extra == 3 && code < 0x10000UL) return READER_TTS_ARGUMENT;
    if (code > 0x10FFFFUL) return READER_TTS_ARGUMENT;
    if (code >= 0xD800UL && code <= 0xDFFFUL) return READER_TTS_ARGUMENT;
    i += extra + 1;
  }
  return READER_TTS_OK;
}

/* Converts validated UTF-8 to UTF-16 and records, for every UTF-16 code unit, the
   UTF-8 byte offset where that unit's code point starts (plus one trailing entry).
   A position inside a surrogate pair therefore still maps to a byte boundary. */
reader_tts_status exr_tts_utf8_to_utf16(const char *utf8, size_t bytes, wchar_t **text,
                                        size_t *units, size_t **unit_map) {
  size_t i = 0, index = 0, count = 0;
  wchar_t *wide;
  size_t *map;
  /* First pass: count UTF-16 code units. */
  while (i < bytes) {
    unsigned char lead = (unsigned char)utf8[i];
    if (lead < 0x80) { i += 1; count += 1; }
    else if ((lead & 0xE0) == 0xC0) { i += 2; count += 1; }
    else if ((lead & 0xF0) == 0xE0) { i += 3; count += 1; }
    else { i += 4; count += 2; }
  }
  wide = (wchar_t *)exr_tts_alloc((count + 1) * sizeof(wchar_t));
  if (!wide) return READER_TTS_MEMORY;
  map = (size_t *)exr_tts_alloc((count + 1) * sizeof(size_t));
  if (!map) { exr_tts_release(wide); return READER_TTS_MEMORY; }
  i = 0;
  while (i < bytes) {
    unsigned char lead = (unsigned char)utf8[i];
    if (lead < 0x80) {
      map[index] = i;
      wide[index++] = (wchar_t)lead;
      i += 1;
    } else if ((lead & 0xE0) == 0xC0) {
      map[index] = i;
      wide[index++] = (wchar_t)(((lead & 0x1Fu) << 6) | ((unsigned char)utf8[i + 1] & 0x3Fu));
      i += 2;
    } else if ((lead & 0xF0) == 0xE0) {
      map[index] = i;
      wide[index++] = (wchar_t)(((lead & 0x0Fu) << 12) | (((unsigned char)utf8[i + 1] & 0x3Fu) << 6)
                                | ((unsigned char)utf8[i + 2] & 0x3Fu));
      i += 3;
    } else {
      unsigned long code = ((unsigned long)(lead & 0x07u) << 18)
        | ((unsigned long)((unsigned char)utf8[i + 1] & 0x3Fu) << 12)
        | ((unsigned long)((unsigned char)utf8[i + 2] & 0x3Fu) << 6)
        | (unsigned long)((unsigned char)utf8[i + 3] & 0x3Fu);
      code -= 0x10000UL;
      map[index] = i;
      wide[index++] = (wchar_t)(0xD800u + (code >> 10));
      map[index] = i;
      wide[index++] = (wchar_t)(0xDC00u + (code & 0x3FFu));
      i += 4;
    }
  }
  map[index] = bytes;
  wide[index] = 0;
  *text = wide;
  *units = index;
  *unit_map = map;
  return READER_TTS_OK;
}

/* ---- plumbing ---- */

static reader_tts_status fail(reader_tts *handle, reader_tts_error *error, reader_tts_status status,
                              int native_code) {
  if (error) { error->code = status; error->native_code = native_code; }
  if (handle) exr_tts_remember(handle, status);
  return status;
}

static reader_tts_status succeed(reader_tts *handle, reader_tts_error *error) {
  if (error) { error->code = READER_TTS_OK; error->native_code = 0; }
  if (handle) exr_tts_remember(handle, READER_TTS_OK);
  return READER_TTS_OK;
}

static void reap_worker(reader_tts *handle) {
  int exited;
  EnterCriticalSection(&handle->lock);
  exited = handle->worker_exited;
  LeaveCriticalSection(&handle->lock);
  if (exited || !handle->worker_started) return;
  if (WaitForSingleObject(handle->worker, 0) != WAIT_OBJECT_0) return;
  CloseHandle(handle->worker);
  handle->worker = NULL;
  EnterCriticalSection(&handle->lock);
  handle->worker_exited = 1;
  if (handle->state == READER_TTS_CLOSING) handle->state = READER_TTS_CLOSED;
  LeaveCriticalSection(&handle->lock);
}

static reader_tts_state current_state(reader_tts *handle) {
  reader_tts_state state;
  EnterCriticalSection(&handle->lock);
  state = handle->state;
  LeaveCriticalSection(&handle->lock);
  return state;
}

static int owner_violation(reader_tts *handle, reader_tts_error *error) {
  if (GetCurrentThreadId() == handle->owner_thread) return 0;
  /* A foreign thread changes nothing, including last_status. */
  if (error) { error->code = READER_TTS_OWNER; error->native_code = 0; }
  return 1;
}

/* ---- public API ---- */

reader_tts_status reader_tts_create(const reader_tts_config *config, reader_tts **out,
                                    reader_tts_error *error) {
  reader_tts *handle;
  size_t limit = EXR_TTS_DEFAULT_MAX_UTF8;
  if (error) { error->code = READER_TTS_OK; error->native_code = 0; }
  if (!out) return fail(NULL, error, READER_TTS_ARGUMENT, 0);
  *out = NULL;
  if (config) {
    if (config->struct_size != sizeof(reader_tts_config)) return fail(NULL, error, READER_TTS_ARGUMENT, 0);
    if (config->max_utf8_bytes > EXR_TTS_HARD_MAX_UTF8) return fail(NULL, error, READER_TTS_ARGUMENT, 0);
    if (config->max_utf8_bytes) limit = config->max_utf8_bytes;
  }
  handle = (reader_tts *)exr_tts_alloc(sizeof *handle);
  if (!handle) return fail(NULL, error, READER_TTS_MEMORY, 0);
  handle->owner_thread = GetCurrentThreadId();
  handle->max_utf8_bytes = limit;
  handle->state = READER_TTS_INITIALIZING;
  handle->last_status = READER_TTS_OK;
  InitializeCriticalSection(&handle->lock);
  handle->cmd_event = CreateEventW(NULL, FALSE, FALSE, NULL);
  handle->ack_event = CreateEventW(NULL, FALSE, FALSE, NULL);
  if (!handle->cmd_event || !handle->ack_event) {
    int code = (int)GetLastError();
    if (handle->cmd_event) CloseHandle(handle->cmd_event);
    if (handle->ack_event) CloseHandle(handle->ack_event);
    DeleteCriticalSection(&handle->lock);
    exr_tts_release(handle);
    return fail(NULL, error, READER_TTS_IO, code);
  }
  handle->worker = CreateThread(NULL, 0, exr_tts_worker_main, handle, 0, NULL);
  if (!handle->worker) {
    int code = (int)GetLastError();
    CloseHandle(handle->cmd_event);
    CloseHandle(handle->ack_event);
    DeleteCriticalSection(&handle->lock);
    exr_tts_release(handle);
    return fail(NULL, error, READER_TTS_IO, code);
  }
  handle->worker_started = 1;
  *out = handle;
  return READER_TTS_OK;
}

reader_tts_status reader_tts_voices(reader_tts *handle, reader_tts_voice_list *list,
                                    reader_tts_error *error) {
  reader_tts_status status;
  reader_tts_state state;
  exr_tts_command command;
  if (error) { error->code = READER_TTS_OK; error->native_code = 0; }
  if (!handle || !list) return fail(handle, error, READER_TTS_ARGUMENT, 0);
  list->voices = NULL;
  list->count = 0;
  if (owner_violation(handle, error)) return READER_TTS_OWNER;
  state = current_state(handle);
  if (state == READER_TTS_CLOSED || state == READER_TTS_CLOSING) {
    return fail(handle, error, READER_TTS_ARGUMENT, 0);
  }
  if (state == READER_TTS_INITIALIZING || state == READER_TTS_SERVICE_UNAVAILABLE) {
    return fail(handle, error, READER_TTS_UNAVAILABLE, 0);
  }
  memset(&command, 0, sizeof command);
  command.kind = EXR_TTS_CMD_VOICES;
  status = exr_tts_send(handle, &command, 1);
  if (status != READER_TTS_OK) return fail(handle, error, status, 0);
  EnterCriticalSection(&handle->lock);
  *list = handle->ack_voices;
  handle->ack_voices.voices = NULL;
  handle->ack_voices.count = 0;
  LeaveCriticalSection(&handle->lock);
  return succeed(handle, error);
}

void reader_tts_voice_list_free(reader_tts_voice_list *list) {
  size_t i;
  if (!list || !list->voices) {
    if (list) list->count = 0;
    return;
  }
  for (i = 0; i < list->count; i++) {
    exr_tts_release(list->voices[i].id);
    exr_tts_release(list->voices[i].name);
    exr_tts_release(list->voices[i].language);
  }
  exr_tts_release(list->voices);
  list->voices = NULL;
  list->count = 0;
}

reader_tts_status reader_tts_speak(reader_tts *handle, uint64_t request_id, const char *utf8,
                                   size_t bytes, const char *voice_id, double rate,
                                   reader_tts_error *error) {
  reader_tts_status status;
  reader_tts_state state;
  exr_tts_command command;
  wchar_t *text = NULL, *wide_voice = NULL;
  size_t units = 0;
  size_t *unit_map = NULL;
  if (error) { error->code = READER_TTS_OK; error->native_code = 0; }
  if (!handle || !utf8 || bytes == 0) return fail(handle, error, READER_TTS_ARGUMENT, 0);
  if (owner_violation(handle, error)) return READER_TTS_OWNER;
  state = current_state(handle);
  if (state == READER_TTS_CLOSED || state == READER_TTS_CLOSING) {
    return fail(handle, error, READER_TTS_ARGUMENT, 0);
  }
  if (state == READER_TTS_INITIALIZING || state == READER_TTS_SERVICE_UNAVAILABLE) {
    return fail(handle, error, READER_TTS_UNAVAILABLE, 0);
  }
  {
    int overflow;
    EnterCriticalSection(&handle->lock);
    overflow = handle->overflow;
    LeaveCriticalSection(&handle->lock);
    if (overflow) return fail(handle, error, READER_TTS_LIMIT, 0);
  }
  if (exr_tts_active(handle) != 0) return fail(handle, error, READER_TTS_BUSY, 0);
  if (request_id == 0 || request_id <= handle->last_request_id) {
    return fail(handle, error, READER_TTS_ARGUMENT, 0);
  }
  if (bytes > handle->max_utf8_bytes) return fail(handle, error, READER_TTS_LIMIT, 0);
  status = validate_utf8(utf8, bytes);
  if (status != READER_TTS_OK) return fail(handle, error, status, 0);
  if (!(rate >= 0.5 && rate <= 2.0)) return fail(handle, error, READER_TTS_ARGUMENT, 0);
  status = exr_tts_utf8_to_utf16(utf8, bytes, &text, &units, &unit_map);
  if (status != READER_TTS_OK) return fail(handle, error, status, 0);
  if (voice_id && voice_id[0]) {
    size_t length = 0, voice_units = 0;
    size_t *voice_map = NULL;
    while (voice_id[length]) length++;
    status = validate_utf8(voice_id, length);
    if (status == READER_TTS_OK) {
      status = exr_tts_utf8_to_utf16(voice_id, length, &wide_voice, &voice_units, &voice_map);
      exr_tts_release(voice_map);
    }
    if (status != READER_TTS_OK) {
      exr_tts_release(text);
      exr_tts_release(unit_map);
      return fail(handle, error, status, 0);
    }
  }
  memset(&command, 0, sizeof command);
  command.kind = EXR_TTS_CMD_SPEAK;
  command.request_id = request_id;
  command.rate = rate;
  command.text = text;
  command.text_units = units;
  command.unit_map = unit_map;
  command.text_bytes = bytes;
  command.voice_id = wide_voice;
  status = exr_tts_send(handle, &command, 1);
  if (status == READER_TTS_OK) {
    handle->last_request_id = request_id;
    return succeed(handle, error);
  }
  return fail(handle, error, status, handle->ack_native);
}

reader_tts_status reader_tts_pause(reader_tts *handle, uint64_t request_id, reader_tts_error *error) {
  exr_tts_command command;
  reader_tts_status status;
  if (error) { error->code = READER_TTS_OK; error->native_code = 0; }
  if (!handle) return fail(NULL, error, READER_TTS_ARGUMENT, 0);
  if (owner_violation(handle, error)) return READER_TTS_OWNER;
  if (current_state(handle) != READER_TTS_SPEAKING || exr_tts_active(handle) != request_id
      || request_id == 0) {
    return fail(handle, error, READER_TTS_ARGUMENT, 0);
  }
  memset(&command, 0, sizeof command);
  command.kind = EXR_TTS_CMD_PAUSE;
  command.request_id = request_id;
  status = exr_tts_send(handle, &command, 1);
  if (status == READER_TTS_OK) return succeed(handle, error);
  return fail(handle, error, status, handle->ack_native);
}

reader_tts_status reader_tts_resume(reader_tts *handle, uint64_t request_id, reader_tts_error *error) {
  exr_tts_command command;
  reader_tts_status status;
  if (error) { error->code = READER_TTS_OK; error->native_code = 0; }
  if (!handle) return fail(NULL, error, READER_TTS_ARGUMENT, 0);
  if (owner_violation(handle, error)) return READER_TTS_OWNER;
  if (current_state(handle) != READER_TTS_PAUSED || exr_tts_active(handle) != request_id
      || request_id == 0) {
    return fail(handle, error, READER_TTS_ARGUMENT, 0);
  }
  memset(&command, 0, sizeof command);
  command.kind = EXR_TTS_CMD_RESUME;
  command.request_id = request_id;
  status = exr_tts_send(handle, &command, 1);
  if (status == READER_TTS_OK) return succeed(handle, error);
  return fail(handle, error, status, handle->ack_native);
}

reader_tts_status reader_tts_stop(reader_tts *handle, uint64_t request_id, reader_tts_error *error) {
  exr_tts_command command;
  reader_tts_status status;
  if (error) { error->code = READER_TTS_OK; error->native_code = 0; }
  if (!handle) return fail(NULL, error, READER_TTS_ARGUMENT, 0);
  if (owner_violation(handle, error)) return READER_TTS_OWNER;
  if (request_id == 0 || exr_tts_active(handle) != request_id
      || (current_state(handle) != READER_TTS_SPEAKING && current_state(handle) != READER_TTS_PAUSED)) {
    return fail(handle, error, READER_TTS_ARGUMENT, 0);
  }
  memset(&command, 0, sizeof command);
  command.kind = EXR_TTS_CMD_STOP;
  command.request_id = request_id;
  status = exr_tts_send(handle, &command, 1);
  if (status == READER_TTS_OK) return succeed(handle, error);
  return fail(handle, error, status, handle->ack_native);
}

reader_tts_status reader_tts_observe(reader_tts *handle, reader_tts_snapshot *snapshot,
                                     reader_tts_error *error) {
  if (error) { error->code = READER_TTS_OK; error->native_code = 0; }
  if (!handle || !snapshot) return fail(NULL, error, READER_TTS_ARGUMENT, 0);
  if (owner_violation(handle, error)) return READER_TTS_OWNER;
  reap_worker(handle);
  EnterCriticalSection(&handle->lock);
  snapshot->state = handle->state;
  snapshot->last_status = handle->last_status;
  snapshot->request_id = handle->active_request;
  snapshot->capabilities = handle->capabilities;
  LeaveCriticalSection(&handle->lock);
  return succeed(handle, error);
}

reader_tts_status reader_tts_poll(reader_tts *handle, reader_tts_event *event, int *available,
                                  reader_tts_error *error) {
  if (error) { error->code = READER_TTS_OK; error->native_code = 0; }
  if (!handle || !event || !available) return fail(handle, error, READER_TTS_ARGUMENT, 0);
  if (owner_violation(handle, error)) return READER_TTS_OWNER;
  reap_worker(handle);
  EnterCriticalSection(&handle->lock);
  if (handle->overflow) {
    LeaveCriticalSection(&handle->lock);
    return fail(handle, error, READER_TTS_LIMIT, 0);
  }
  if (handle->count == 0) {
    LeaveCriticalSection(&handle->lock);
    memset(event, 0, sizeof *event);
    *available = 0;
    return succeed(handle, error);
  }
  {
    const exr_tts_queue_event *slot = &handle->events[handle->head];
    event->request_id = slot->request_id;
    event->kind = slot->kind;
    event->status = slot->status;
    event->start = slot->start;
    event->end = slot->end;
    event->has_range = slot->has_range;
    handle->head = (handle->head + 1) % EXR_TTS_QUEUE_CAPACITY;
    handle->count--;
  }
  LeaveCriticalSection(&handle->lock);
  *available = 1;
  return succeed(handle, error);
}

reader_tts_status reader_tts_request_close(reader_tts *handle, reader_tts_error *error) {
  exr_tts_command command;
  if (error) { error->code = READER_TTS_OK; error->native_code = 0; }
  if (!handle) return fail(NULL, error, READER_TTS_ARGUMENT, 0);
  if (owner_violation(handle, error)) return READER_TTS_OWNER;
  reap_worker(handle);
  if (current_state(handle) == READER_TTS_CLOSED || current_state(handle) == READER_TTS_CLOSING) {
    return succeed(handle, error);
  }
  EnterCriticalSection(&handle->lock);
  handle->state = READER_TTS_CLOSING;
  LeaveCriticalSection(&handle->lock);
  InterlockedExchange(&handle->close_requested, 1);
  memset(&command, 0, sizeof command);
  command.kind = EXR_TTS_CMD_CLOSE;
  /* Non-blocking: the worker tears the backend down and exits; reader_tts_observe
     reports CLOSED once that is complete. */
  exr_tts_send(handle, &command, 0);
  return succeed(handle, error);
}

reader_tts_status reader_tts_windows_set_wav_output(reader_tts *handle, const wchar_t *path,
                                                    reader_tts_error *error) {
  exr_tts_command command;
  reader_tts_status status;
  wchar_t *copy = NULL;
  if (error) { error->code = READER_TTS_OK; error->native_code = 0; }
  if (!handle) return fail(NULL, error, READER_TTS_ARGUMENT, 0);
  if (owner_violation(handle, error)) return READER_TTS_OWNER;
  {
    reader_tts_state state = current_state(handle);
    if (state == READER_TTS_CLOSED || state == READER_TTS_CLOSING) {
      return fail(handle, error, READER_TTS_ARGUMENT, 0);
    }
    if (state == READER_TTS_INITIALIZING || state == READER_TTS_SERVICE_UNAVAILABLE) {
      return fail(handle, error, READER_TTS_UNAVAILABLE, 0);
    }
    if (state != READER_TTS_READY) return fail(handle, error, READER_TTS_BUSY, 0);
  }
  if (path) {
    size_t units = 0;
    while (path[units]) units++;
    if (units == 0) return fail(handle, error, READER_TTS_ARGUMENT, 0);
    copy = (wchar_t *)exr_tts_alloc((units + 1) * sizeof(wchar_t));
    if (!copy) return fail(handle, error, READER_TTS_MEMORY, 0);
    memcpy(copy, path, (units + 1) * sizeof(wchar_t));
  }
  memset(&command, 0, sizeof command);
  command.kind = EXR_TTS_CMD_SET_WAV;
  command.wav_path = copy;
  status = exr_tts_send(handle, &command, 1);
  if (status == READER_TTS_OK) return succeed(handle, error);
  return fail(handle, error, status, handle->ack_native);
}

reader_tts_status reader_tts_destroy(reader_tts **handle_pointer, reader_tts_error *error) {
  reader_tts *handle;
  if (error) { error->code = READER_TTS_OK; error->native_code = 0; }
  if (!handle_pointer || !*handle_pointer) return fail(NULL, error, READER_TTS_ARGUMENT, 0);
  handle = *handle_pointer;
  if (owner_violation(handle, error)) return READER_TTS_OWNER;
  reap_worker(handle);
  if (current_state(handle) != READER_TTS_CLOSED) return fail(handle, error, READER_TTS_BUSY, 0);
  CloseHandle(handle->cmd_event);
  CloseHandle(handle->ack_event);
  if (handle->worker) CloseHandle(handle->worker);
  handle->worker = NULL;
  DeleteCriticalSection(&handle->lock);
  exr_tts_release(handle->wav_path);
  handle->wav_path = NULL;
  exr_tts_release(handle);
  *handle_pointer = NULL;
  return READER_TTS_OK;
}
