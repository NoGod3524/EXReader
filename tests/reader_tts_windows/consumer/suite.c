/* SPDX-License-Identifier: MIT */
/* Installed-consumer acceptance suite. Every phase drives the real SAPI backend
   through the public C ABI plus the package's own Windows extras header; nothing
   is mocked and no expected value is adjusted to make a failure look like a pass.

   Phases: basic, speak, unicode, limits, control, chunks, overflow, service,
   memory, close. Each phase owns its handle and ends by proving that every
   internal allocation was released. */
#include "suite.h"
#include "reader_tts.h"
#include "reader_tts_windows.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <windows.h>

#define TEXT_CAP 16640u
#define PATH_CAP 1024u

struct suite {
  char wav_dir[PATH_CAP];
  char wav[PATH_CAP];
  char text[TEXT_CAP];
  char detail[384];
  int passed, total, failed;
};

typedef struct {
  uint64_t id;
  const char *text;
  size_t bytes;
  int started, finished, stopped, failed, ranges, events;
  int first_kind, last_kind, bad_range;
  size_t last_start, max_end;
} tally;

static const char FILLER[] =
  "The quick brown fox jumps over the lazy dog while the reader listens carefully. ";
static const char UNICODE_TEXT[] =
  "Han \xE6\xB1\x89\xE5\xAD\x97 (CJK) emoji \xF0\x9F\x98\x80 combining e\xCC\x81"
  " RTL \xD9\x85\xD8\xB1\xD8\xAD\xD8\xA8\xD8\xA7 end.";

/* ---- reporting ---- */

static const char *status_name(reader_tts_status status) {
  switch (status) {
    case READER_TTS_OK: return "OK";
    case READER_TTS_ARGUMENT: return "ARGUMENT";
    case READER_TTS_OWNER: return "OWNER";
    case READER_TTS_BUSY: return "BUSY";
    case READER_TTS_UNAVAILABLE: return "UNAVAILABLE";
    case READER_TTS_UNSUPPORTED: return "UNSUPPORTED";
    case READER_TTS_IO: return "IO";
    case READER_TTS_MEMORY: return "MEMORY";
    case READER_TTS_LIMIT: return "LIMIT";
  }
  return "UNKNOWN";
}

static const char *state_name(reader_tts_state state) {
  switch (state) {
    case READER_TTS_INITIALIZING: return "INITIALIZING";
    case READER_TTS_READY: return "READY";
    case READER_TTS_SPEAKING: return "SPEAKING";
    case READER_TTS_PAUSED: return "PAUSED";
    case READER_TTS_STOPPING: return "STOPPING";
    case READER_TTS_CLOSING: return "CLOSING";
    case READER_TTS_CLOSED: return "CLOSED";
    case READER_TTS_SERVICE_UNAVAILABLE: return "SERVICE_UNAVAILABLE";
  }
  return "UNKNOWN";
}

static void check(suite *s, const char *id, int ok, const char *detail) {
  s->total++;
  if (ok) s->passed++;
  else s->failed++;
  printf("check %s %s %s\n", id, ok ? "pass" : "fail", detail && detail[0] ? detail : "-");
  fflush(stdout);
}

static void check_status(suite *s, const char *id, reader_tts_status actual, reader_tts_status expected) {
  snprintf(s->detail, sizeof s->detail, "expected=%s actual=%s", status_name(expected), status_name(actual));
  check(s, id, actual == expected, s->detail);
}

static void check_state(suite *s, const char *id, reader_tts_state actual, reader_tts_state expected) {
  snprintf(s->detail, sizeof s->detail, "expected=%s actual=%s", state_name(expected), state_name(actual));
  check(s, id, actual == expected, s->detail);
}

static void check_count(suite *s, const char *id, unsigned long long actual,
                        unsigned long long minimum, int at_least) {
  snprintf(s->detail, sizeof s->detail, "%s=%llu actual=%llu", at_least ? "minimum" : "expected", minimum, actual);
  check(s, id, at_least ? actual >= minimum : actual == minimum, s->detail);
}

static int phase_end(suite *s, const char *name) {
  printf("phase %s %d %d\n", name, s->passed, s->total);
  fflush(stdout);
  return s->failed == 0 ? 0 : 1;
}

/* ---- fixture helpers ---- */

suite *suite_create(const char *wav_dir) {
  suite *s = (suite *)calloc(1, sizeof *s);
  if (!s) return NULL;
  if (!wav_dir || strlen(wav_dir) >= sizeof s->wav_dir) {
    free(s);
    return NULL;
  }
  {
    size_t length = strlen(wav_dir);
    memcpy(s->wav_dir, wav_dir, length + 1);
  }
  return s;
}

void suite_destroy(suite *state) {
  free(state);
}

static size_t fill_text(suite *s, size_t bytes, char marker) {
  size_t offset = 0;
  while (offset < bytes) {
    size_t chunk = sizeof FILLER - 1;
    if (chunk > bytes - offset) chunk = bytes - offset;
    memcpy(s->text + offset, FILLER, chunk);
    offset += chunk;
  }
  if (bytes > 0) s->text[0] = marker;
  s->text[offset] = '\0';
  return offset;
}

static const char *wav_name(suite *s, const char *name) {
  snprintf(s->wav, sizeof s->wav, "%s\\%s.wav", s->wav_dir, name);
  return s->wav;
}

static reader_tts_status set_wav(suite *s, reader_tts *handle, const char *name) {
  wchar_t wide[PATH_CAP];
  const char *path = wav_name(s, name);
  if (MultiByteToWideChar(CP_UTF8, 0, path, -1, wide, PATH_CAP) <= 0) return READER_TTS_ARGUMENT;
  return reader_tts_windows_set_wav_output(handle, wide, NULL);
}

static void announce_wav(suite *s, const char *name, unsigned long long minimum_ms) {
  printf("wavfile %s %llu\n", wav_name(s, name), minimum_ms);
  fflush(stdout);
}

static void info(suite *s, const char *key, unsigned long long value) {
  (void)s;
  printf("info %s %llu\n", key, value);
  fflush(stdout);
}

static reader_tts_state wait_state(reader_tts *handle, reader_tts_state target, int timeout_ms,
                                   reader_tts_snapshot *out) {
  int waited = 0;
  reader_tts_snapshot snap;
  memset(&snap, 0, sizeof snap);
  for (;;) {
    if (reader_tts_observe(handle, &snap, NULL) == READER_TTS_OK) {
      if (out) *out = snap;
      if (snap.state == target) return target;
    }
    if (waited >= timeout_ms) break;
    Sleep(10);
    waited += 10;
  }
  if (out) *out = snap;
  return snap.state;
}

static reader_tts *open_ready(suite *s, const reader_tts_config *config, const char *prefix) {
  reader_tts *handle = NULL;
  reader_tts_snapshot snap;
  reader_tts_status status = reader_tts_create(config, &handle, NULL);
  snprintf(s->detail, sizeof s->detail, "create=%s", status_name(status));
  check(s, prefix, status == READER_TTS_OK && handle != NULL, s->detail);
  if (status != READER_TTS_OK || !handle) return NULL;
  wait_state(handle, READER_TTS_READY, 30000, &snap);
  return handle;
}

static int close_and_destroy(suite *s, reader_tts **handle, const char *prefix) {
  reader_tts_snapshot snap;
  reader_tts_status status;
  int ok = 1;
  if (!*handle) return 0;
  status = reader_tts_request_close(*handle, NULL);
  if (status != READER_TTS_OK) ok = 0;
  if (wait_state(*handle, READER_TTS_CLOSED, 30000, &snap) != READER_TTS_CLOSED) ok = 0;
  status = reader_tts_destroy(handle, NULL);
  if (status != READER_TTS_OK || *handle != NULL) ok = 0;
  snprintf(s->detail, sizeof s->detail, "closed_and_destroyed=%d", ok);
  check(s, prefix, ok, s->detail);
  return ok;
}

/* ---- event tallies ---- */

static void tally_init(tally *t, uint64_t id, const char *text, size_t bytes) {
  memset(t, 0, sizeof *t);
  t->id = id;
  t->text = text;
  t->bytes = bytes;
  t->first_kind = -1;
  t->last_kind = -1;
}

static int offsets_match(const size_t *actual, const size_t *expected, size_t count) {
  size_t i;
  for (i = 0; i < count; i++) {
    if (actual[i] != expected[i]) return 0;
  }
  return 1;
}

static int utf8_boundary(const char *text, size_t bytes, size_t offset) {
  if (offset >= bytes) return 1;
  return ((unsigned char)text[offset] & 0xC0) != 0x80;
}

static void tally_event(tally *t, const reader_tts_event *event) {
  t->events++;
  if (t->first_kind < 0) t->first_kind = (int)event->kind;
  t->last_kind = (int)event->kind;
  switch (event->kind) {
    case READER_TTS_STARTED: t->started++; break;
    case READER_TTS_FINISHED: t->finished++; break;
    case READER_TTS_STOPPED: t->stopped++; break;
    case READER_TTS_FAILED: t->failed++; break;
    case READER_TTS_RANGE:
      t->ranges++;
      if (!event->has_range || event->start >= event->end || event->end > t->bytes
          || event->start < t->last_start
          || !utf8_boundary(t->text, t->bytes, event->start)
          || !utf8_boundary(t->text, t->bytes, event->end)) {
        t->bad_range = 1;
      }
      t->last_start = event->start;
      if (event->end > t->max_end) t->max_end = event->end;
      break;
    default:
      t->bad_range = 1;
      break;
  }
}

static int poll_events(reader_tts *handle, tally *t, int *foreign) {
  reader_tts_event event;
  int available = 0;
  if (reader_tts_poll(handle, &event, &available, NULL) != READER_TTS_OK) return -1;
  while (available) {
    if (event.request_id == t->id) tally_event(t, &event);
    else if (foreign) (*foreign)++;
    if (reader_tts_poll(handle, &event, &available, NULL) != READER_TTS_OK) return -1;
  }
  return 0;
}

/* 0: terminal event reached; 1: timeout; -1: poll failure. */
static int pump_until_terminal(reader_tts *handle, tally *t, int timeout_ms, int *foreign) {
  int waited = 0;
  for (;;) {
    if (poll_events(handle, t, foreign) != 0) return -1;
    if (t->finished || t->stopped || t->failed) return 0;
    if (waited >= timeout_ms) return 1;
    Sleep(5);
    waited += 5;
  }
}

/* 0: enough ranges seen; 1: request ended first; 2: timeout; -1: poll failure. */
static int pump_until_ranges(reader_tts *handle, tally *t, int want, int timeout_ms, int *foreign) {
  int waited = 0;
  for (;;) {
    if (poll_events(handle, t, foreign) != 0) return -1;
    if (t->ranges >= want) return 0;
    if (t->finished || t->stopped || t->failed) return 1;
    if (waited >= timeout_ms) return 2;
    Sleep(5);
    waited += 5;
  }
}

/* ---- phases ---- */

typedef struct {
  reader_tts *handle;
  reader_tts_status observe, speak, pause, resume, stop, voices, close, destroy_status;
} owner_probe;

static DWORD WINAPI owner_probe_thread(LPVOID parameter) {
  owner_probe *probe = (owner_probe *)parameter;
  reader_tts *same = probe->handle;
  reader_tts_snapshot snap;
  reader_tts_voice_list list;
  memset(&snap, 0, sizeof snap);
  memset(&list, 0, sizeof list);
  probe->observe = reader_tts_observe(probe->handle, &snap, NULL);
  probe->speak = reader_tts_speak(probe->handle, 4294967295ULL, "x", 1, NULL, 1.0, NULL);
  probe->pause = reader_tts_pause(probe->handle, 4294967295ULL, NULL);
  probe->resume = reader_tts_resume(probe->handle, 4294967295ULL, NULL);
  probe->stop = reader_tts_stop(probe->handle, 4294967295ULL, NULL);
  probe->voices = reader_tts_voices(probe->handle, &list, NULL);
  probe->close = reader_tts_request_close(probe->handle, NULL);
  probe->destroy_status = reader_tts_destroy(&same, NULL);
  return 0;
}

static void phase_basic(suite *s) {
  reader_tts *handle = NULL, *other = NULL;
  reader_tts_snapshot snap;
  reader_tts_voice_list voices;
  reader_tts_config config;
  reader_tts_status status;
  owner_probe probe;
  HANDLE thread;
  DWORD waited;

  reader_tts_windows_debug_init_delay_ms(500);
  status = reader_tts_create(NULL, &handle, NULL);
  check_status(s, "basic.create.status", status, READER_TTS_OK);
  check(s, "basic.create.handle", handle != NULL, "-");
  memset(&snap, 0, sizeof snap);
  reader_tts_observe(handle, &snap, NULL);
  check_state(s, "basic.create.initializing", snap.state, READER_TTS_INITIALIZING);
  check_status(s, "basic.speak.before_ready", reader_tts_speak(handle, 1, "x", 1, NULL, 1.0, NULL),
               READER_TTS_UNAVAILABLE);
  memset(&voices, 0, sizeof voices);
  check_status(s, "basic.voices.before_ready", reader_tts_voices(handle, &voices, NULL),
               READER_TTS_UNAVAILABLE);
  reader_tts_windows_debug_init_delay_ms(0);
  wait_state(handle, READER_TTS_READY, 30000, &snap);
  check_state(s, "basic.ready", snap.state, READER_TTS_READY);
  check_count(s, "basic.ready.request_id", snap.request_id, 0, 0);
  check(s, "basic.ready.capabilities", (snap.capabilities & READER_TTS_CAN_PAUSE) == READER_TTS_CAN_PAUSE,
        "pause capability advertised before the first request");

  memset(&voices, 0, sizeof voices);
  status = reader_tts_voices(handle, &voices, NULL);
  check_status(s, "basic.voices.status", status, READER_TTS_OK);
  check_count(s, "basic.voices.count", voices.count, 1, 1);
  {
    int complete = voices.count > 0, unique = 1, empty_id = 0, empty_name = 0, empty_language = 0;
    int with_language = 0;
    size_t i, j;
    unsigned long long id_length = 0, name_length = 0, language_length = 0;
    for (i = 0; i < voices.count; i++) {
      if (!voices.voices[i].id || !voices.voices[i].id[0]) { complete = 0; empty_id++; }
      if (!voices.voices[i].name || !voices.voices[i].name[0]) { complete = 0; empty_name++; }
      if (!voices.voices[i].language || !voices.voices[i].language[0]) empty_language++;
      else with_language++;
      if (!i) {
        if (voices.voices[i].id) id_length = (unsigned long long)strlen(voices.voices[i].id);
        if (voices.voices[i].name) name_length = (unsigned long long)strlen(voices.voices[i].name);
        if (voices.voices[i].language) language_length = (unsigned long long)strlen(voices.voices[i].language);
      }
      for (j = 0; j < i; j++) {
        if (voices.voices[i].id && voices.voices[j].id && strcmp(voices.voices[i].id, voices.voices[j].id) == 0) {
          unique = 0;
        }
      }
    }
    snprintf(s->detail, sizeof s->detail,
             "empty_id=%d empty_name=%d empty_language=%d first_len=%llu/%llu/%llu",
             empty_id, empty_name, empty_language, id_length, name_length, language_length);
    check(s, "basic.voices.fields_complete", complete, s->detail);
    snprintf(s->detail, sizeof s->detail, "voices_with_language=%d empty=%d", with_language, empty_language);
    check(s, "basic.voices.language_present", with_language >= 1, s->detail);
    check(s, "basic.voices.ids_unique", unique, "-");
    info(s, "voices", (unsigned long long)voices.count);
    info(s, "voices_without_language", (unsigned long long)empty_language);
  }
  reader_tts_voice_list_free(&voices);
  check(s, "basic.voices.freed", voices.count == 0 && voices.voices == NULL, "-");
  reader_tts_voice_list_free(&voices);
  check(s, "basic.voices.free_twice", 1, "second free is a no-op");
  reader_tts_voice_list_free(NULL);
  check(s, "basic.voices.free_null", 1, "NULL list accepted");
  check_status(s, "basic.voices.null_list", reader_tts_voices(handle, NULL, NULL), READER_TTS_ARGUMENT);
  {
    reader_tts_event event;
    int available = 1;
    memset(&event, 0, sizeof event);
    status = reader_tts_poll(handle, &event, &available, NULL);
    check(s, "basic.poll.empty", status == READER_TTS_OK && available == 0 && event.request_id == 0,
          status_name(status));
    check_status(s, "basic.poll.null_event", reader_tts_poll(handle, NULL, &available, NULL),
                 READER_TTS_ARGUMENT);
  }

  memset(&probe, 0, sizeof probe);
  probe.handle = handle;
  thread = CreateThread(NULL, 0, owner_probe_thread, &probe, 0, NULL);
  check(s, "basic.owner.thread_created", thread != NULL, "-");
  if (thread) {
    waited = WaitForSingleObject(thread, 60000);
    CloseHandle(thread);
    check(s, "basic.owner.thread_joined", waited == WAIT_OBJECT_0, "foreign thread finished");
  }
  check_status(s, "basic.owner.observe", probe.observe, READER_TTS_OWNER);
  check_status(s, "basic.owner.speak", probe.speak, READER_TTS_OWNER);
  check_status(s, "basic.owner.pause", probe.pause, READER_TTS_OWNER);
  check_status(s, "basic.owner.resume", probe.resume, READER_TTS_OWNER);
  check_status(s, "basic.owner.stop", probe.stop, READER_TTS_OWNER);
  check_status(s, "basic.owner.voices", probe.voices, READER_TTS_OWNER);
  check_status(s, "basic.owner.close", probe.close, READER_TTS_OWNER);
  check_status(s, "basic.owner.destroy", probe.destroy_status, READER_TTS_OWNER);
  reader_tts_observe(handle, &snap, NULL);
  check_state(s, "basic.owner.state_unchanged", snap.state, READER_TTS_READY);

  {
    reader_tts *same = handle;
    check_status(s, "basic.destroy.before_close", reader_tts_destroy(&same, NULL), READER_TTS_BUSY);
    check(s, "basic.destroy.keeps_pointer", same == handle, "-");
  }
  check_status(s, "basic.close.status", reader_tts_request_close(handle, NULL), READER_TTS_OK);
  wait_state(handle, READER_TTS_CLOSED, 30000, &snap);
  check_state(s, "basic.closed", snap.state, READER_TTS_CLOSED);
  check_status(s, "basic.close.idempotent", reader_tts_request_close(handle, NULL), READER_TTS_OK);
  check_status(s, "basic.speak.after_close", reader_tts_speak(handle, 2, "x", 1, NULL, 1.0, NULL),
               READER_TTS_ARGUMENT);
  {
    reader_tts_event event;
    int available = 1;
    status = reader_tts_poll(handle, &event, &available, NULL);
    check(s, "basic.poll.closed_empty", status == READER_TTS_OK && available == 0, status_name(status));
  }
  check_status(s, "basic.destroy.status", reader_tts_destroy(&handle, NULL), READER_TTS_OK);
  check(s, "basic.destroy.null", handle == NULL, "-");
  check_status(s, "basic.destroy.twice", reader_tts_destroy(&handle, NULL), READER_TTS_ARGUMENT);

  memset(&config, 0, sizeof config);
  check_status(s, "basic.create.null_out", reader_tts_create(NULL, NULL, NULL), READER_TTS_ARGUMENT);
  config.struct_size = 0;
  check_status(s, "basic.create.bad_struct_size", reader_tts_create(&config, &other, NULL),
               READER_TTS_ARGUMENT);
  config.struct_size = sizeof config;
  config.max_utf8_bytes = 20000;
  check_status(s, "basic.create.over_hard_limit", reader_tts_create(&config, &other, NULL),
               READER_TTS_ARGUMENT);
  check(s, "basic.create.no_handle_on_failure", other == NULL, "-");
  check_count(s, "basic.allocations.released",
              (unsigned long long)reader_tts_windows_debug_live_allocations(), 0, 0);
}

static void phase_speak(suite *s) {
  reader_tts *handle = open_ready(s, NULL, "speak.create");
  reader_tts_snapshot snap;
  tally t;
  size_t bytes;
  int foreign = 0, outcome;

  if (!handle) return;
  bytes = fill_text(s, 400, 'S');
  check_status(s, "speak.wav_output", set_wav(s, handle, "speak"), READER_TTS_OK);
  check_status(s, "speak.start", reader_tts_speak(handle, 1, s->text, bytes, NULL, 1.0, NULL),
               READER_TTS_OK);
  reader_tts_observe(handle, &snap, NULL);
  check_state(s, "speak.state_speaking", snap.state, READER_TTS_SPEAKING);
  check_count(s, "speak.snapshot_request_id", snap.request_id, 1, 0);
  check_status(s, "speak.second_busy", reader_tts_speak(handle, 2, "x", 1, NULL, 1.0, NULL),
               READER_TTS_BUSY);
  check_status(s, "speak.restart_busy", reader_tts_speak(handle, 1, "x", 1, NULL, 1.0, NULL),
               READER_TTS_BUSY);
  tally_init(&t, 1, s->text, bytes);
  outcome = pump_until_terminal(handle, &t, 180000, &foreign);
  check(s, "speak.terminal_reached", outcome == 0,
        outcome == 0 ? "terminal event received" : outcome == 1 ? "timeout" : "poll failure");
  check_count(s, "speak.started_events", t.started, 1, 0);
  check_count(s, "speak.finished_events", t.finished, 1, 0);
  check_count(s, "speak.failed_events", t.failed, 0, 0);
  check_count(s, "speak.stopped_events", t.stopped, 0, 0);
  {
    int caps_range = (snap.capabilities & READER_TTS_CAN_REPORT_RANGE) ? 1 : 0;
    info(s, "range_events", (unsigned long long)t.ranges);
    info(s, "range_capability", (unsigned long long)caps_range);
    snprintf(s->detail, sizeof s->detail, "ranges=%d capability=%d", t.ranges, caps_range);
    check(s, "speak.range_capability", (t.ranges > 0) == caps_range, s->detail);
    snprintf(s->detail, sizeof s->detail, "ranges=%d (min 8 when the engine reports positions)", t.ranges);
    check(s, "speak.range_events", t.ranges > 0 ? t.ranges >= 8 : 1, s->detail);
  }
  check(s, "speak.range_bounds", t.bad_range == 0, "ranges monotonic, in bounds, on UTF-8 boundaries");
  check_count(s, "speak.first_event_started", (unsigned long long)t.first_kind, READER_TTS_STARTED, 0);
  check_count(s, "speak.last_event_finished", (unsigned long long)t.last_kind, READER_TTS_FINISHED, 0);
  check_count(s, "speak.foreign_events", (unsigned long long)foreign, 0, 0);
  {
    reader_tts_windows_engine_probe probe;
    memset(&probe, 0, sizeof probe);
    reader_tts_windows_debug_engine_probe(handle, &probe);
    info(s, "engine_samples", (unsigned long long)probe.samples);
    info(s, "engine_hresult", (unsigned long long)(uint32_t)probe.hresult);
    info(s, "engine_running_state", (unsigned long long)probe.running_state);
    info(s, "engine_word_pos", (unsigned long long)probe.word_position);
    info(s, "engine_word_len", (unsigned long long)probe.word_length);
    info(s, "engine_current_stream", (unsigned long long)probe.current_stream);
    info(s, "engine_last_queued", (unsigned long long)probe.last_queued);
    info(s, "engine_event_hresult", (unsigned long long)(uint32_t)probe.event_hresult);
    info(s, "engine_event_calls", (unsigned long long)probe.event_calls);
    info(s, "engine_event_total", (unsigned long long)probe.event_total);
    info(s, "engine_last_event_id", (unsigned long long)probe.last_event_id);
  }
  reader_tts_observe(handle, &snap, NULL);
  check_state(s, "speak.state_ready", snap.state, READER_TTS_READY);
  check_count(s, "speak.idle_request_id", snap.request_id, 0, 0);
  announce_wav(s, "speak", 1500);
  close_and_destroy(s, &handle, "speak.closed");
  check_count(s, "speak.allocations.released",
              (unsigned long long)reader_tts_windows_debug_live_allocations(), 0, 0);
}

static void phase_unicode(suite *s) {
  reader_tts *handle = open_ready(s, NULL, "unicode.create");
  tally t;
  size_t bytes;
  int foreign = 0, outcome, multibyte = 0;
  size_t i;

  if (!handle) return;
  bytes = strlen(UNICODE_TEXT);
  check_status(s, "unicode.wav_output", set_wav(s, handle, "unicode"), READER_TTS_OK);
  check_status(s, "unicode.start", reader_tts_speak(handle, 1, UNICODE_TEXT, bytes, NULL, 1.0, NULL),
               READER_TTS_OK);
  tally_init(&t, 1, UNICODE_TEXT, bytes);
  outcome = pump_until_terminal(handle, &t, 120000, &foreign);
  check(s, "unicode.terminal_reached", outcome == 0,
        outcome == 0 ? "terminal event received" : outcome == 1 ? "timeout" : "poll failure");
  check_count(s, "unicode.started_events", t.started, 1, 0);
  check_count(s, "unicode.finished_events", t.finished, 1, 0);
  check_count(s, "unicode.range_events", t.ranges, 4, 1);
  check(s, "unicode.range_bounds", t.bad_range == 0, "UTF-8 byte boundaries only");
  check(s, "unicode.range_offsets_converted", t.max_end > 0 && t.max_end <= bytes,
        "ranges are byte offsets, not UTF-16 units");
  for (i = 0; i < bytes; i++) {
    if ((unsigned char)UNICODE_TEXT[i] >= 0x80) multibyte = 1;
  }
  check(s, "unicode.input_non_ascii", multibyte, "-");
  {
    size_t offsets[16];
    size_t units;
    static const char ASCII3[] = "abc";
    static const char ACUTE[] = "\xC3\xA9";
    static const char CJK[] = "\xE6\xB1\x89\xE5\xAD\x97";
    static const char EMOJI[] = "\xF0\x9F\x98\x80";
    static const char MIXED[] = "a\xF0\x9F\x98\x80b";
    static const char BAD[] = "\x80";
    static const size_t ASCII_EXPECT[4] = { 0, 1, 2, 3 };
    static const size_t ACUTE_EXPECT[2] = { 0, 2 };
    static const size_t CJK_EXPECT[3] = { 0, 3, 6 };
    static const size_t EMOJI_EXPECT[3] = { 0, 0, 4 };
    static const size_t MIXED_EXPECT[5] = { 0, 1, 1, 5, 6 };
    units = reader_tts_windows_debug_map_utf16(ASCII3, 3, offsets, 16);
    snprintf(s->detail, sizeof s->detail, "units=%llu", (unsigned long long)units);
    check(s, "unicode.map.ascii", units == 3 && offsets_match(offsets, ASCII_EXPECT, 4), s->detail);
    units = reader_tts_windows_debug_map_utf16(ACUTE, 2, offsets, 16);
    snprintf(s->detail, sizeof s->detail, "units=%llu", (unsigned long long)units);
    check(s, "unicode.map.two_byte", units == 1 && offsets_match(offsets, ACUTE_EXPECT, 2), s->detail);
    units = reader_tts_windows_debug_map_utf16(CJK, 6, offsets, 16);
    snprintf(s->detail, sizeof s->detail, "units=%llu", (unsigned long long)units);
    check(s, "unicode.map.cjk", units == 2 && offsets_match(offsets, CJK_EXPECT, 3), s->detail);
    units = reader_tts_windows_debug_map_utf16(EMOJI, 4, offsets, 16);
    snprintf(s->detail, sizeof s->detail, "units=%llu offsets=%llu,%llu,%llu",
             (unsigned long long)units, (unsigned long long)offsets[0],
             (unsigned long long)offsets[1], (unsigned long long)offsets[2]);
    check(s, "unicode.map.surrogate_pair", units == 2 && offsets_match(offsets, EMOJI_EXPECT, 3), s->detail);
    units = reader_tts_windows_debug_map_utf16(MIXED, 6, offsets, 16);
    snprintf(s->detail, sizeof s->detail, "units=%llu", (unsigned long long)units);
    check(s, "unicode.map.mixed", units == 4 && offsets_match(offsets, MIXED_EXPECT, 5), s->detail);
    units = reader_tts_windows_debug_map_utf16(BAD, 1, offsets, 16);
    snprintf(s->detail, sizeof s->detail, "units=%llu", (unsigned long long)units);
    check(s, "unicode.map.invalid_rejected", units == 0, s->detail);
  }
  announce_wav(s, "unicode", 1500);
  close_and_destroy(s, &handle, "unicode.closed");
  check_count(s, "unicode.allocations.released",
              (unsigned long long)reader_tts_windows_debug_live_allocations(), 0, 0);
}

static void phase_limits(suite *s) {
  reader_tts_config config;
  reader_tts *handle;
  reader_tts_snapshot snap;
  tally t;
  double nan_value, inf_value;
  static const char LONE_CONTINUATION[] = "\x80";
  static const char TRUNCATED[] = "\xE4\xB8";
  static const char OVERLONG[] = "\xC0\xAF";
  static const char SURROGATE[] = "\xED\xA0\x80";
  static const char OUT_OF_RANGE[] = "\xF4\x90\x80\x80";
  static const char EMBEDDED_NUL[] = "a\0b";
  size_t i;
  int foreign = 0;

  memset(&config, 0, sizeof config);
  config.struct_size = sizeof config;
  config.max_utf8_bytes = 64;
  handle = open_ready(s, &config, "limits.create");
  if (!handle) return;
  check_status(s, "limits.wav_output", set_wav(s, handle, "limits"), READER_TTS_OK);
  for (i = 0; i < 65; i++) s->text[i] = (char)('a' + (int)(i % 26));
  s->text[65] = '\0';
  check_status(s, "limits.config_limit_enforced",
               reader_tts_speak(handle, 1, s->text, 65, NULL, 1.0, NULL), READER_TTS_LIMIT);
  for (i = 0; i < 64; i++) s->text[i] = (char)('a' + (int)(i % 26));
  s->text[64] = '\0';
  check_status(s, "limits.config_limit_boundary",
               reader_tts_speak(handle, 1, s->text, 64, NULL, 1.0, NULL), READER_TTS_OK);
  tally_init(&t, 1, s->text, 64);
  check(s, "limits.config_limit_terminal", pump_until_terminal(handle, &t, 60000, &foreign) == 0, "-");

  check_status(s, "limits.utf8.lone_continuation",
               reader_tts_speak(handle, 2, LONE_CONTINUATION, 1, NULL, 1.0, NULL), READER_TTS_ARGUMENT);
  check_status(s, "limits.utf8.truncated",
               reader_tts_speak(handle, 2, TRUNCATED, 2, NULL, 1.0, NULL), READER_TTS_ARGUMENT);
  check_status(s, "limits.utf8.overlong",
               reader_tts_speak(handle, 2, OVERLONG, 2, NULL, 1.0, NULL), READER_TTS_ARGUMENT);
  check_status(s, "limits.utf8.surrogate",
               reader_tts_speak(handle, 2, SURROGATE, 3, NULL, 1.0, NULL), READER_TTS_ARGUMENT);
  check_status(s, "limits.utf8.out_of_range",
               reader_tts_speak(handle, 2, OUT_OF_RANGE, 4, NULL, 1.0, NULL), READER_TTS_ARGUMENT);
  check_status(s, "limits.utf8.embedded_nul",
               reader_tts_speak(handle, 2, EMBEDDED_NUL, 3, NULL, 1.0, NULL), READER_TTS_ARGUMENT);
  check_status(s, "limits.empty_text", reader_tts_speak(handle, 2, "x", 0, NULL, 1.0, NULL),
               READER_TTS_ARGUMENT);
  nan_value = strtod("nan", NULL);
  inf_value = strtod("inf", NULL);
  check_status(s, "limits.rate.too_slow", reader_tts_speak(handle, 2, "x", 1, NULL, 0.4, NULL),
               READER_TTS_ARGUMENT);
  check_status(s, "limits.rate.too_fast", reader_tts_speak(handle, 2, "x", 1, NULL, 2.1, NULL),
               READER_TTS_ARGUMENT);
  check_status(s, "limits.rate.nan", reader_tts_speak(handle, 2, "x", 1, NULL, nan_value, NULL),
               READER_TTS_ARGUMENT);
  check_status(s, "limits.rate.inf", reader_tts_speak(handle, 2, "x", 1, NULL, inf_value, NULL),
               READER_TTS_ARGUMENT);
  check_status(s, "limits.voice.unknown",
               reader_tts_speak(handle, 2, "x", 1, "no-such-voice-token", 1.0, NULL),
               READER_TTS_ARGUMENT);
  check_status(s, "limits.request_id.zero", reader_tts_speak(handle, 0, "x", 1, NULL, 1.0, NULL),
               READER_TTS_ARGUMENT);
  check_status(s, "limits.accepted", reader_tts_speak(handle, 2, "short text", 10, NULL, 2.0, NULL),
               READER_TTS_OK);
  check_status(s, "limits.wav_output.busy", set_wav(s, handle, "limits-busy"), READER_TTS_BUSY);
  tally_init(&t, 2, "short text", 10);
  check(s, "limits.accepted_terminal", pump_until_terminal(handle, &t, 60000, &foreign) == 0, "-");
  check_count(s, "limits.accepted_finished", t.finished, 1, 0);
  check_status(s, "limits.request_id.reused", reader_tts_speak(handle, 2, "x", 1, NULL, 1.0, NULL),
               READER_TTS_ARGUMENT);
  check_status(s, "limits.request_id.decreases", reader_tts_speak(handle, 1, "x", 1, NULL, 1.0, NULL),
               READER_TTS_ARGUMENT);
  reader_tts_observe(handle, &snap, NULL);
  check_state(s, "limits.state_intact", snap.state, READER_TTS_READY);
  close_and_destroy(s, &handle, "limits.closed");
  check_count(s, "limits.allocations.released",
              (unsigned long long)reader_tts_windows_debug_live_allocations(), 0, 0);
}

static void phase_control(suite *s) {
  reader_tts *handle = open_ready(s, NULL, "control.create");
  reader_tts_snapshot snap;
  tally t, second;
  size_t bytes;
  int foreign = 0, outcome, ranges_at_pause;
  reader_tts_event event;
  int available;

  if (!handle) return;
  bytes = fill_text(s, 16000, 'C');
  check_status(s, "control.wav_output", set_wav(s, handle, "control"), READER_TTS_OK);
  check_status(s, "control.start", reader_tts_speak(handle, 1, s->text, bytes, NULL, 1.0, NULL),
               READER_TTS_OK);
  tally_init(&t, 1, s->text, bytes);
  outcome = pump_until_ranges(handle, &t, 1, 20000, &foreign);
  check(s, "control.first_range", outcome == 0 && t.ranges >= 1, "SAPI reported a word boundary");
  check_status(s, "control.pause", reader_tts_pause(handle, 1, NULL), READER_TTS_OK);
  reader_tts_observe(handle, &snap, NULL);
  check_state(s, "control.state_paused", snap.state, READER_TTS_PAUSED);
  check_status(s, "control.pause_twice", reader_tts_pause(handle, 1, NULL), READER_TTS_ARGUMENT);
  check_status(s, "control.resume_wrong_id", reader_tts_resume(handle, 3, NULL), READER_TTS_ARGUMENT);
  Sleep(200);
  {
    int drained = poll_events(handle, &t, &foreign) == 0;
    check(s, "control.pause.drain", drained, "queued events read before the idle probe");
  }
  Sleep(250);
  available = 1;
  memset(&event, 0, sizeof event);
  reader_tts_poll(handle, &event, &available, NULL);
  check(s, "control.pause.progress_stopped", available == 0, "no word boundary while paused");
  ranges_at_pause = t.ranges;
  check_status(s, "control.resume", reader_tts_resume(handle, 1, NULL), READER_TTS_OK);
  reader_tts_observe(handle, &snap, NULL);
  check_state(s, "control.state_resumed", snap.state, READER_TTS_SPEAKING);
  outcome = pump_until_ranges(handle, &t, ranges_at_pause + 1, 20000, &foreign);
  check(s, "control.resume_progress", outcome == 0 && t.ranges > ranges_at_pause,
        "speech continued after resume");
  check_status(s, "control.stop", reader_tts_stop(handle, 1, NULL), READER_TTS_OK);
  reader_tts_observe(handle, &snap, NULL);
  check_state(s, "control.state_ready_after_stop", snap.state, READER_TTS_READY);
  check_count(s, "control.idle_request_id", snap.request_id, 0, 0);
  check(s, "control.stop_terminal", pump_until_terminal(handle, &t, 20000, &foreign) == 0, "-");
  check_count(s, "control.stopped_events", t.stopped, 1, 0);
  check_count(s, "control.finished_after_stop", t.finished, 0, 0);
  check_count(s, "control.failed_events", t.failed, 0, 0);
  check_status(s, "control.stop_twice", reader_tts_stop(handle, 1, NULL), READER_TTS_ARGUMENT);

  check_status(s, "control.second_start", reader_tts_speak(handle, 2, "Second request after a stop.", 28,
                                                           NULL, 1.5, NULL), READER_TTS_OK);
  tally_init(&second, 2, "Second request after a stop.", 28);
  foreign = 0;
  outcome = pump_until_terminal(handle, &second, 60000, &foreign);
  check(s, "control.second_terminal", outcome == 0, "-");
  check_count(s, "control.second_finished", second.finished, 1, 0);
  check(s, "control.no_late_events", foreign == 0, "no event kept the stopped request id");
  check(s, "control.range_bounds", t.bad_range == 0 && second.bad_range == 0, "all ranges valid");
  close_and_destroy(s, &handle, "control.closed");
  check_count(s, "control.allocations.released",
              (unsigned long long)reader_tts_windows_debug_live_allocations(), 0, 0);
}

static void phase_chunks(suite *s) {
  reader_tts *handle = open_ready(s, NULL, "chunks.create");
  tally t;
  size_t bytes;
  int foreign = 0, outcome;
  int chunk;
  static const char *names[3] = { "chunk0", "chunk1", "chunk2" };

  if (!handle) return;
  for (chunk = 0; chunk < 3; chunk++) {
    char id[64];
    bytes = fill_text(s, 1000, (char)('A' + chunk));
    snprintf(id, sizeof id, "chunks.%d.wav_output", chunk);
    check_status(s, id, set_wav(s, handle, names[chunk]), READER_TTS_OK);
    snprintf(id, sizeof id, "chunks.%d.start", chunk);
    check_status(s, id, reader_tts_speak(handle, (uint64_t)(chunk + 1), s->text, bytes, NULL, 1.5, NULL),
                 READER_TTS_OK);
    tally_init(&t, (uint64_t)(chunk + 1), s->text, bytes);
    outcome = pump_until_terminal(handle, &t, 180000, &foreign);
    snprintf(id, sizeof id, "chunks.%d.terminal", chunk);
    check(s, id, outcome == 0, outcome == 0 ? "terminal event received" : outcome == 1 ? "timeout" : "poll failure");
    snprintf(id, sizeof id, "chunks.%d.finished", chunk);
    check_count(s, id, t.finished, 1, 0);
    snprintf(id, sizeof id, "chunks.%d.started", chunk);
    check_count(s, id, t.started, 1, 0);
    snprintf(id, sizeof id, "chunks.%d.range_bounds", chunk);
    check(s, id, t.bad_range == 0, "chunk ranges inside this chunk");
    snprintf(id, sizeof id, "chunks.%d.byte_window", chunk);
    check(s, id, t.max_end > 0 && t.max_end <= bytes, "ranges bound to this chunk");
    announce_wav(s, names[chunk], 1000);
  }
  fill_text(s, 16385, 'Z');
  check_status(s, "chunks.over_hard_limit",
               reader_tts_speak(handle, 4, s->text, 16385, NULL, 1.0, NULL), READER_TTS_LIMIT);
  close_and_destroy(s, &handle, "chunks.closed");
  check_count(s, "chunks.allocations.released",
              (unsigned long long)reader_tts_windows_debug_live_allocations(), 0, 0);
}

static void phase_overflow(suite *s) {
  reader_tts *handle = open_ready(s, NULL, "overflow.create");
  reader_tts_event event;
  uint64_t next_id = 1;
  int ok_count = 0, limit_count = 0, unexpected = 0, spins = 0;
  int available = 0;
  reader_tts_status poll_status;
  reader_tts_error error;

  if (!handle) return;
  check_status(s, "overflow.wav_output", set_wav(s, handle, "overflow"), READER_TTS_OK);
  while (next_id <= 70 && spins < 20000) {
    reader_tts_snapshot snap;
    reader_tts_status status;
    spins++;
    if (wait_state(handle, READER_TTS_READY, 5000, &snap) != READER_TTS_READY) {
      Sleep(5);
      continue;
    }
    status = reader_tts_speak(handle, next_id, "x", 1, NULL, 1.0, NULL);
    if (status == READER_TTS_BUSY) {
      Sleep(5);
      continue;
    }
    if (status == READER_TTS_OK) ok_count++;
    else if (status == READER_TTS_LIMIT) limit_count++;
    else unexpected++;
    next_id++;
  }
  check_count(s, "overflow.accepted_before_limit", (unsigned long long)ok_count, 30, 1);
  check_count(s, "overflow.limit_reported", (unsigned long long)limit_count, 1, 1);
  check_count(s, "overflow.unexpected_status", (unsigned long long)unexpected, 0, 0);
  memset(&error, 0, sizeof error);
  memset(&event, 0, sizeof event);
  poll_status = reader_tts_poll(handle, &event, &available, &error);
  check_status(s, "overflow.poll_limit", poll_status, READER_TTS_LIMIT);
  check(s, "overflow.poll_error_code", error.code == READER_TTS_LIMIT, status_name(error.code));
  info(s, "overflow.accepted", (unsigned long long)ok_count);
  close_and_destroy(s, &handle, "overflow.closed");
  check_count(s, "overflow.allocations.released",
              (unsigned long long)reader_tts_windows_debug_live_allocations(), 0, 0);
}

static void phase_service(suite *s) {
  reader_tts *handle = NULL;
  reader_tts_snapshot snap;
  reader_tts_voice_list voices;
  reader_tts_status status;

  reader_tts_windows_debug_simulate_no_service(1);
  status = reader_tts_create(NULL, &handle, NULL);
  check_status(s, "service.create.status", status, READER_TTS_OK);
  if (!handle) {
    reader_tts_windows_debug_simulate_no_service(0);
    return;
  }
  wait_state(handle, READER_TTS_SERVICE_UNAVAILABLE, 30000, &snap);
  check_state(s, "service.unavailable_state", snap.state, READER_TTS_SERVICE_UNAVAILABLE);
  check_count(s, "service.capabilities_zero", snap.capabilities, 0, 0);
  check_status(s, "service.speak", reader_tts_speak(handle, 1, "x", 1, NULL, 1.0, NULL),
               READER_TTS_UNAVAILABLE);
  memset(&voices, 0, sizeof voices);
  check_status(s, "service.voices", reader_tts_voices(handle, &voices, NULL), READER_TTS_UNAVAILABLE);
  reader_tts_windows_debug_simulate_no_service(0);
  close_and_destroy(s, &handle, "service.closed");
  check_count(s, "service.allocations.released",
              (unsigned long long)reader_tts_windows_debug_live_allocations(), 0, 0);
}

static void phase_memory(suite *s) {
  reader_tts *handle = NULL;
  reader_tts_snapshot snap;
  reader_tts_voice_list voices;
  long baseline;

  check_count(s, "memory.baseline",
              (unsigned long long)reader_tts_windows_debug_live_allocations(), 0, 0);
  reader_tts_windows_debug_fail_allocation_after(1);
  check_status(s, "memory.create", reader_tts_create(NULL, &handle, NULL), READER_TTS_MEMORY);
  check(s, "memory.create.no_handle", handle == NULL, "-");
  check_count(s, "memory.create.no_leak",
              (unsigned long long)reader_tts_windows_debug_live_allocations(), 0, 0);
  reader_tts_windows_debug_fail_allocation_after(0);

  handle = open_ready(s, NULL, "memory.open");
  if (!handle) return;
  check_status(s, "memory.wav_output", set_wav(s, handle, "memory"), READER_TTS_OK);
  baseline = reader_tts_windows_debug_live_allocations();
  reader_tts_windows_debug_fail_allocation_after(2);
  memset(&voices, 0, sizeof voices);
  check_status(s, "memory.voices", reader_tts_voices(handle, &voices, NULL), READER_TTS_MEMORY);
  reader_tts_windows_debug_fail_allocation_after(0);
  check(s, "memory.voices.no_list", voices.voices == NULL && voices.count == 0, "-");
  check_count(s, "memory.voices.no_leak",
              (unsigned long long)reader_tts_windows_debug_live_allocations(),
              (unsigned long long)baseline, 0);
  reader_tts_windows_debug_fail_allocation_after(1);
  check_status(s, "memory.speak.text", reader_tts_speak(handle, 1, "allocation", 10, NULL, 1.0, NULL),
               READER_TTS_MEMORY);
  reader_tts_windows_debug_fail_allocation_after(2);
  check_status(s, "memory.speak.map", reader_tts_speak(handle, 1, "allocation", 10, NULL, 1.0, NULL),
               READER_TTS_MEMORY);
  reader_tts_windows_debug_fail_allocation_after(0);
  check_count(s, "memory.speak.no_leak",
              (unsigned long long)reader_tts_windows_debug_live_allocations(),
              (unsigned long long)baseline, 0);
  reader_tts_observe(handle, &snap, NULL);
  check_state(s, "memory.state_intact", snap.state, READER_TTS_READY);
  check_status(s, "memory.speak.recovered",
               reader_tts_speak(handle, 2, "allocation", 10, NULL, 1.0, NULL), READER_TTS_OK);
  {
    tally t;
    int foreign = 0;
    tally_init(&t, 2, "allocation", 10);
    check(s, "memory.recovered_terminal", pump_until_terminal(handle, &t, 60000, &foreign) == 0, "-");
  }
  close_and_destroy(s, &handle, "memory.closed");
  check_count(s, "memory.allocations.released",
              (unsigned long long)reader_tts_windows_debug_live_allocations(), 0, 0);
}

static void phase_close(suite *s) {
  reader_tts *handle = NULL;
  reader_tts_snapshot snap;
  reader_tts_status status;
  reader_tts *same;

  reader_tts_windows_debug_init_delay_ms(2500);
  check_status(s, "close.create", reader_tts_create(NULL, &handle, NULL), READER_TTS_OK);
  if (!handle) {
    reader_tts_windows_debug_init_delay_ms(0);
    return;
  }
  reader_tts_observe(handle, &snap, NULL);
  check_state(s, "close.initializing", snap.state, READER_TTS_INITIALIZING);
  check_status(s, "close.request", reader_tts_request_close(handle, NULL), READER_TTS_OK);
  reader_tts_observe(handle, &snap, NULL);
  check_state(s, "close.closing", snap.state, READER_TTS_CLOSING);
  same = handle;
  check_status(s, "close.destroy_busy", reader_tts_destroy(&same, NULL), READER_TTS_BUSY);
  check(s, "close.destroy_keeps_pointer", same == handle, "-");
  reader_tts_windows_debug_init_delay_ms(0);
  wait_state(handle, READER_TTS_CLOSED, 40000, &snap);
  check_state(s, "close.closed", snap.state, READER_TTS_CLOSED);
  {
    reader_tts_voice_list voices;
    memset(&voices, 0, sizeof voices);
    check_status(s, "close.voices_after_close", reader_tts_voices(handle, &voices, NULL),
                 READER_TTS_ARGUMENT);
  }
  status = reader_tts_destroy(&handle, NULL);
  check_status(s, "close.destroy", status, READER_TTS_OK);
  check(s, "close.destroy.null", handle == NULL, "-");
  check_count(s, "close.allocations.released",
              (unsigned long long)reader_tts_windows_debug_live_allocations(), 0, 0);
}

int suite_run(suite *state, const char *phase) {
  if (!state || !phase) return 1;
  if (strcmp(phase, "basic") == 0) phase_basic(state);
  else if (strcmp(phase, "speak") == 0) phase_speak(state);
  else if (strcmp(phase, "unicode") == 0) phase_unicode(state);
  else if (strcmp(phase, "limits") == 0) phase_limits(state);
  else if (strcmp(phase, "control") == 0) phase_control(state);
  else if (strcmp(phase, "chunks") == 0) phase_chunks(state);
  else if (strcmp(phase, "overflow") == 0) phase_overflow(state);
  else if (strcmp(phase, "service") == 0) phase_service(state);
  else if (strcmp(phase, "memory") == 0) phase_memory(state);
  else if (strcmp(phase, "close") == 0) phase_close(state);
  else {
    printf("check harness.phase fail unknown=%s\n", phase);
    printf("phase %s 0 1\n", phase);
    fflush(stdout);
    return 1;
  }
  return phase_end(state, phase);
}