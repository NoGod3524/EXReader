/* SPDX-License-Identifier: MIT */
/* Installed-package consumer for EXReaderTTSAndroid::reader_tts.
 *
 * The probe app compiles this file against the installed prefix only and runs
 * one named case per JNI call, so every case reports an independent outcome.
 * Nothing here reimplements the library: it drives the public C ABI and checks
 * the observed status, state, events and ownership rules.
 */
#include "reader_tts.h"

#include "consumer.h"

#include <math.h>
#include <pthread.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#define DETAIL_BYTES 8192
#define COMPLETED_IDS 16

static reader_tts *g_main;
static reader_tts *g_limited;
static int g_engine_mode;
static int g_case_failed;
static char g_detail[DETAIL_BYTES];
static size_t g_detail_length;
static uint64_t g_next_id;
static uint64_t g_last_accepted;
static uint64_t g_completed[COMPLETED_IDS];
static size_t g_completed_count;

static const char *const SAMPLE = "Reader text";
#define SAMPLE_BYTES (sizeof(SAMPLE) - 1)
/* 中文 = 6 bytes, " reader " = 8, U+1F600 = 4, " text" = 5 */
static const char *const RICH =
  "\xE4\xB8\xAD\xE6\x96\x87" " reader " "\xF0\x9F\x98\x80" " text";
#define RICH_BYTES (sizeof(RICH) - 1)

static void note(const char *format, ...) {
  va_list args;
  int written = 0;
  size_t room = DETAIL_BYTES - g_detail_length;
  if (room < 8) return;
  va_start(args, format);
  written = vsnprintf(g_detail + g_detail_length, room, format, args);
  va_end(args);
  if (written <= 0) return;
  g_detail_length += (size_t)written < room ? (size_t)written : room - 1;
}

static void fail_note(const char *what) {
  g_case_failed = 1;
  note("%s failed; ", what);
}

static void expect_status(reader_tts_status got, reader_tts_status want, const char *what) {
  if (got != want) {
    g_case_failed = 1;
    note("%s: status %d want %d; ", what, (int)got, (int)want);
  }
}

static void expect_true(int condition, const char *what) {
  if (!condition) fail_note(what);
}

static void expect_uint(unsigned long got, unsigned long want, const char *what) {
  if (got != want) {
    g_case_failed = 1;
    note("%s: %lu want %lu; ", what, got, want);
  }
}

static void sleep_ms(int milliseconds) {
  struct timespec delay;
  delay.tv_sec = milliseconds / 1000;
  delay.tv_nsec = (long)(milliseconds % 1000) * 1000000L;
  nanosleep(&delay, NULL);
}

static uint64_t next_id(void) {
  g_next_id += 1;
  return g_next_id;
}

static void remember_completed(uint64_t request) {
  if (g_completed_count < COMPLETED_IDS) {
    g_completed[g_completed_count] = request;
    g_completed_count += 1;
  }
}

static int was_completed(uint64_t request) {
  for (size_t index = 0; index < g_completed_count; index++) {
    if (g_completed[index] == request) return 1;
  }
  return 0;
}

static int utf8_boundary(const char *text, size_t bytes, size_t offset) {
  if (offset > bytes) return 0;
  if (offset == bytes) return 1;
  return ((unsigned char)text[offset] & 0xC0) != 0x80;
}

struct ledger {
  unsigned total;
  unsigned started;
  unsigned ranges;
  unsigned finished;
  unsigned stopped;
  unsigned failed;
  unsigned late_known;
  unsigned foreign_unknown;
  unsigned misordered;
  int boundaries_ok;
  size_t last_end;
};

/* Drains events for one request until a terminal event arrives. Late events of
 * earlier, already completed requests are counted as late_known; any other
 * request id is a cross-request contamination and fails the case. */
static int collect(reader_tts *tts, uint64_t request, int timeout_ms, const char *text,
  size_t bytes, struct ledger *out) {
  int iterations = timeout_ms / 5;
  memset(out, 0, sizeof(*out));
  out->boundaries_ok = 1;
  for (int step = 0; step < iterations; step++) {
    reader_tts_event event;
    int available = 0;
    reader_tts_status status = reader_tts_poll(tts, &event, &available, NULL);
    if (status != READER_TTS_OK) {
      note("poll returned %d; ", (int)status);
      return 2;
    }
    if (!available) {
      sleep_ms(5);
      continue;
    }
    out->total += 1;
    if (event.request_id != request) {
      if (was_completed(event.request_id)) {
        out->late_known += 1;
      } else {
        out->foreign_unknown += 1;
        note("event id %llu outside request %llu; ",
          (unsigned long long)event.request_id, (unsigned long long)request);
      }
      continue;
    }
    switch (event.kind) {
      case READER_TTS_STARTED:
        out->started += 1;
        break;
      case READER_TTS_RANGE:
        if (out->started == 0) out->misordered += 1;
        if (!event.has_range || !utf8_boundary(text, bytes, event.start) ||
            !utf8_boundary(text, bytes, event.end) || event.end < event.start ||
            event.end > bytes) {
          out->boundaries_ok = 0;
        }
        if (event.start < out->last_end) out->misordered += 1;
        out->last_end = event.end;
        out->ranges += 1;
        break;
      case READER_TTS_FINISHED:
        out->finished += 1;
        break;
      case READER_TTS_STOPPED:
        out->stopped += 1;
        break;
      case READER_TTS_FAILED:
        out->failed += 1;
        break;
      default:
        out->misordered += 1;
        break;
    }
    if (event.kind == READER_TTS_FINISHED || event.kind == READER_TTS_STOPPED ||
        event.kind == READER_TTS_FAILED) {
      return 0;
    }
  }
  return 1;
}

static int wait_state(reader_tts *tts, int timeout_ms, reader_tts_state *observed) {
  int iterations = timeout_ms / 10;
  for (int step = 0; step < iterations; step++) {
    reader_tts_snapshot snapshot;
    if (reader_tts_observe(tts, &snapshot, NULL) != READER_TTS_OK) return -1;
    if (snapshot.state == READER_TTS_READY || snapshot.state == READER_TTS_SPEAKING ||
        snapshot.state == READER_TTS_SERVICE_UNAVAILABLE || snapshot.state == READER_TTS_CLOSED) {
      *observed = snapshot.state;
      return 0;
    }
    sleep_ms(10);
  }
  return 1;
}

static int wait_closed(reader_tts *tts, int timeout_ms, reader_tts_state *observed) {
  int iterations = timeout_ms / 10;
  for (int step = 0; step < iterations; step++) {
    reader_tts_snapshot snapshot;
    if (reader_tts_observe(tts, &snapshot, NULL) != READER_TTS_OK) return -1;
    if (snapshot.state == READER_TTS_CLOSED) {
      *observed = snapshot.state;
      return 0;
    }
    sleep_ms(10);
  }
  return 1;
}

struct owner_args {
  reader_tts *tts;
  reader_tts_status status;
  int value;
};

static void *observe_thread(void *raw) {
  struct owner_args *args = (struct owner_args *)raw;
  reader_tts_snapshot snapshot;
  args->status = reader_tts_observe(args->tts, &snapshot, NULL);
  return NULL;
}

static void *destroy_thread(void *raw) {
  struct owner_args *args = (struct owner_args *)raw;
  reader_tts *copy = args->tts;
  args->status = reader_tts_destroy(&copy, NULL);
  args->value = copy == args->tts;
  return NULL;
}

static char *make_ascii(size_t length) {
  char *text = (char *)malloc(length + 1);
  if (!text) return NULL;
  for (size_t index = 0; index < length; index++) {
    text[index] = (index % 7 == 6) ? ' ' : (char)('a' + (int)(index % 26));
  }
  text[length] = 0;
  return text;
}

/* ---------------------------------------------------------------- cases */

static int case_initialize_null_argument(void) {
  expect_status((reader_tts_status)exr_tts_platform_bind_null(), READER_TTS_ARGUMENT,
    "initialize with NULL env and context");
  return g_case_failed ? 1 : 0;
}

static int case_create_before_bind_unavailable(void) {
  reader_tts *tts = NULL;
  reader_tts_error error;
  memset(&error, 0, sizeof(error));
  expect_status(reader_tts_create(NULL, &tts, &error), READER_TTS_UNAVAILABLE,
    "create before initialize");
  expect_true(tts == NULL, "create before initialize must not publish a handle");
  expect_status(error.code, READER_TTS_UNAVAILABLE, "create before initialize error code");
  return g_case_failed ? 1 : 0;
}

static int case_initialize_binds(void) {
  expect_status((reader_tts_status)exr_tts_platform_bind(), READER_TTS_OK, "initialize");
  return g_case_failed ? 1 : 0;
}

static int case_initialize_idempotent(void) {
  expect_status((reader_tts_status)exr_tts_platform_bind(), READER_TTS_OK,
    "second initialize");
  return g_case_failed ? 1 : 0;
}

static int case_create_null_out_argument(void) {
  expect_status(reader_tts_create(NULL, NULL, NULL), READER_TTS_ARGUMENT, "create with NULL out");
  return g_case_failed ? 1 : 0;
}

static int case_create_struct_size_mismatch_argument(void) {
  reader_tts_config config;
  reader_tts *tts = NULL;
  memset(&config, 0, sizeof(config));
  config.struct_size = sizeof(reader_tts_config) - 1;
  expect_status(reader_tts_create(&config, &tts, NULL), READER_TTS_ARGUMENT,
    "create with a foreign struct_size");
  expect_true(tts == NULL, "mis-sized config must not publish a handle");
  return g_case_failed ? 1 : 0;
}

static int case_create_limit_above_hard_cap_argument(void) {
  reader_tts_config config;
  reader_tts *tts = NULL;
  memset(&config, 0, sizeof(config));
  config.struct_size = sizeof(reader_tts_config);
  config.max_utf8_bytes = READER_TTS_DEFAULT_MAX_UTF8_BYTES + 1;
  expect_status(reader_tts_create(&config, &tts, NULL), READER_TTS_ARGUMENT,
    "create above the 16 KiB hard cap");
  expect_true(tts == NULL, "over-cap config must not publish a handle");
  return g_case_failed ? 1 : 0;
}

static int case_create_initializing_or_unavailable(void) {
  reader_tts_state state = READER_TTS_INITIALIZING;
  reader_tts_snapshot snapshot;
  expect_status(reader_tts_create(NULL, &g_main, NULL), READER_TTS_OK, "create the main handle");
  if (!g_main) return 1;
  if (wait_state(g_main, 30000, &state) != 0) {
    note("engine reached neither READY nor SERVICE_UNAVAILABLE in 30s; ");
    return 1;
  }
  if (g_engine_mode) {
    expect_true(state == READER_TTS_READY, "an installed engine must reach READY");
  } else {
    expect_true(state == READER_TTS_SERVICE_UNAVAILABLE,
      "a removed engine must report SERVICE_UNAVAILABLE");
  }
  expect_status(reader_tts_observe(g_main, &snapshot, NULL), READER_TTS_OK, "observe main");
  note("state=%d last_status=%d capabilities=%u; ", (int)snapshot.state,
    (int)snapshot.last_status, snapshot.capabilities);
  return g_case_failed ? 1 : 0;
}

static int case_create_lowered_limit_handle(void) {
  reader_tts_config config;
  memset(&config, 0, sizeof(config));
  config.struct_size = sizeof(reader_tts_config);
  config.max_utf8_bytes = 64;
  expect_status(reader_tts_create(&config, &g_limited, NULL), READER_TTS_OK,
    "create a handle with a lowered byte limit");
  expect_true(g_limited != NULL, "lowered-limit handle");
  return g_case_failed ? 1 : 0;
}

static int case_observe_wrong_owner_rejected(void) {
  struct owner_args args;
  pthread_t worker;
  reader_tts_snapshot before;
  reader_tts_snapshot after;
  if (!g_main) return 1;
  memset(&args, 0, sizeof(args));
  args.tts = g_main;
  args.status = READER_TTS_OK;
  expect_status(reader_tts_observe(g_main, &before, NULL), READER_TTS_OK, "owner observe");
  if (pthread_create(&worker, NULL, observe_thread, &args) != 0) {
    note("pthread_create failed; ");
    return 1;
  }
  pthread_join(worker, NULL);
  expect_status(args.status, READER_TTS_OWNER, "observe from a foreign thread");
  expect_status(reader_tts_observe(g_main, &after, NULL), READER_TTS_OK, "owner observe again");
  expect_uint((unsigned long)after.state, (unsigned long)before.state, "state after foreign call");
  return g_case_failed ? 1 : 0;
}

static int case_speak_null_text_argument(void) {
  expect_status(reader_tts_speak(g_main, next_id(), NULL, SAMPLE_BYTES, NULL, 1.0, NULL),
    READER_TTS_ARGUMENT, "speak with NULL text");
  return g_case_failed ? 1 : 0;
}

static int case_speak_zero_request_id_argument(void) {
  expect_status(reader_tts_speak(g_main, 0, SAMPLE, SAMPLE_BYTES, NULL, 1.0, NULL),
    READER_TTS_ARGUMENT, "speak with request id 0");
  return g_case_failed ? 1 : 0;
}

static int case_speak_empty_text_argument(void) {
  expect_status(reader_tts_speak(g_main, next_id(), SAMPLE, 0, NULL, 1.0, NULL),
    READER_TTS_ARGUMENT, "speak with zero bytes");
  return g_case_failed ? 1 : 0;
}

static int case_speak_invalid_utf8_argument(void) {
  expect_status(reader_tts_speak(g_main, next_id(), "\xC0\xAF", 2, NULL, 1.0, NULL),
    READER_TTS_ARGUMENT, "speak with an overlong two-byte form");
  return g_case_failed ? 1 : 0;
}

static int case_speak_incomplete_scalar_argument(void) {
  expect_status(reader_tts_speak(g_main, next_id(), "\xE4\xB8", 2, NULL, 1.0, NULL),
    READER_TTS_ARGUMENT, "speak with an incomplete three-byte sequence");
  return g_case_failed ? 1 : 0;
}

static int case_speak_embedded_nul_argument(void) {
  expect_status(reader_tts_speak(g_main, next_id(), "a\0b", 3, NULL, 1.0, NULL),
    READER_TTS_ARGUMENT, "speak with an embedded NUL");
  return g_case_failed ? 1 : 0;
}

static int case_speak_surrogate_scalar_argument(void) {
  expect_status(reader_tts_speak(g_main, next_id(), "\xED\xA0\x80", 3, NULL, 1.0, NULL),
    READER_TTS_ARGUMENT, "speak with an encoded surrogate");
  return g_case_failed ? 1 : 0;
}

static int case_speak_rate_out_of_range_argument(void) {
  static const double rates[] = { 0.49, 2.01, (double)NAN, (double)INFINITY };
  for (size_t index = 0; index < sizeof(rates) / sizeof(rates[0]); index++) {
    expect_status(reader_tts_speak(g_main, next_id(), SAMPLE, SAMPLE_BYTES, NULL,
      rates[index], NULL), READER_TTS_ARGUMENT, "speak with an out-of-range rate");
  }
  return g_case_failed ? 1 : 0;
}

static int case_speak_over_configured_limit(void) {
  char text[65];
  memset(text, 'a', sizeof(text));
  expect_status(reader_tts_speak(g_limited, next_id(), text, sizeof(text), NULL, 1.0, NULL),
    READER_TTS_LIMIT, "speak above the lowered 64 byte limit");
  return g_case_failed ? 1 : 0;
}

static int case_voices_listing(void) {
  reader_tts_voice_list list;
  memset(&list, 0, sizeof(list));
  if (g_engine_mode) {
    expect_status(reader_tts_voices(g_main, &list, NULL), READER_TTS_OK, "voices with an engine");
    expect_true(list.count > 0, "an installed engine must list at least one voice");
    if (list.count > 0) {
      expect_true(list.voices[0].id && list.voices[0].id[0] != 0, "first voice id");
      expect_true(list.voices[0].name && list.voices[0].name[0] != 0, "first voice name");
      expect_true(list.voices[0].language && list.voices[0].language[0] != 0, "first voice language");
      note("voices=%lu first=%s/%s; ", (unsigned long)list.count, list.voices[0].id,
        list.voices[0].language);
    }
  } else {
    expect_status(reader_tts_voices(g_main, &list, NULL), READER_TTS_UNAVAILABLE,
      "voices without an engine");
    expect_true(list.count == 0 && list.voices == NULL, "refused voice list stays empty");
  }
  reader_tts_voice_list_free(&list);
  return g_case_failed ? 1 : 0;
}

static int case_voices_free_null_safe(void) {
  reader_tts_voice_list list;
  reader_tts_voice_list_free(NULL);
  memset(&list, 0, sizeof(list));
  reader_tts_voice_list_free(&list);
  reader_tts_voice_list_free(&list);
  expect_true(list.count == 0 && list.voices == NULL, "freed list is zeroed");
  return g_case_failed ? 1 : 0;
}

static int case_speak_started_and_finished(void) {
  struct ledger log;
  uint64_t request = next_id();
  int outcome = 0;
  if (!g_engine_mode) return 2;
  expect_status(reader_tts_speak(g_main, request, SAMPLE, SAMPLE_BYTES, NULL, 1.0, NULL),
    READER_TTS_OK, "speak a short sample");
  if (g_case_failed) return 1;
  outcome = collect(g_main, request, 45000, SAMPLE, SAMPLE_BYTES, &log);
  expect_true(outcome == 0, "terminal event for the short sample");
  expect_uint(log.started, 1, "exactly one STARTED");
  expect_uint(log.finished + log.stopped + log.failed, 1, "exactly one terminal event");
  expect_uint(log.misordered, 0, "range ordering");
  expect_uint(log.foreign_unknown, 0, "no foreign request ids");
  expect_true(log.boundaries_ok, "range byte boundaries");
  note("started=%u ranges=%u finished=%u stopped=%u failed=%u late=%u; ", log.started,
    log.ranges, log.finished, log.stopped, log.failed, log.late_known);
  g_last_accepted = request;
  remember_completed(request);
  return g_case_failed ? 1 : 0;
}

static int case_speak_request_id_reuse_argument(void) {
  if (!g_engine_mode) return 2;
  expect_status(reader_tts_speak(g_main, g_last_accepted, SAMPLE, SAMPLE_BYTES, NULL, 1.0, NULL),
    READER_TTS_ARGUMENT, "speak with an already used request id");
  expect_status(reader_tts_speak(g_main, g_last_accepted - 1, SAMPLE, SAMPLE_BYTES, NULL, 1.0,
    NULL), READER_TTS_ARGUMENT, "speak with an older request id");
  return g_case_failed ? 1 : 0;
}

static int case_single_terminal_per_request(void) {
  reader_tts_event event;
  int available = 1;
  if (!g_engine_mode) return 2;
  expect_status(reader_tts_poll(g_main, &event, &available, NULL), READER_TTS_OK, "poll after terminal");
  expect_uint((unsigned long)available, 0, "no duplicate terminal event is queued");
  return g_case_failed ? 1 : 0;
}

static int case_range_utf8_boundaries(void) {
  struct ledger log;
  uint64_t request = next_id();
  reader_tts_snapshot snapshot;
  int outcome = 0;
  if (!g_engine_mode) return 2;
  expect_status(reader_tts_speak(g_main, request, RICH, RICH_BYTES, NULL, 1.0, NULL),
    READER_TTS_OK, "speak multi-byte text");
  if (g_case_failed) return 1;
  outcome = collect(g_main, request, 45000, RICH, RICH_BYTES, &log);
  expect_true(outcome == 0, "terminal event for multi-byte text");
  expect_uint(log.started, 1, "multi-byte STARTED");
  expect_uint(log.finished + log.stopped + log.failed, 1, "multi-byte terminal");
  expect_uint(log.misordered, 0, "multi-byte range ordering");
  expect_true(log.boundaries_ok, "multi-byte range boundaries are UTF-8 offsets");
  expect_status(reader_tts_observe(g_main, &snapshot, NULL), READER_TTS_OK, "observe capabilities");
  if (log.ranges == 0) {
    expect_uint(snapshot.capabilities & READER_TTS_CAN_REPORT_RANGE, 0,
      "no range callback means the capability bit stays clear");
    note("range_not_reported ranges=0 capabilities=%u; ", snapshot.capabilities);
  } else {
    expect_uint(snapshot.capabilities & READER_TTS_CAN_REPORT_RANGE, READER_TTS_CAN_REPORT_RANGE,
      "range callbacks must publish the capability bit");
    note("ranges=%lu last_end=%lu capabilities=%u; ", (unsigned long)log.ranges,
      (unsigned long)log.last_end, snapshot.capabilities);
  }
  g_last_accepted = request;
  remember_completed(request);
  return g_case_failed ? 1 : 0;
}

static int case_poll_empty_available_zero(void) {
  reader_tts_event event;
  int available = 1;
  int drained = 0;
  /* A late advisory RANGE for the previous request may still arrive; drain for
     a bounded window and then require a truly empty queue. */
  for (int step = 0; step < 100; step++) {
    expect_status(reader_tts_poll(g_main, &event, &available, NULL), READER_TTS_OK, "poll while draining");
    if (!available) break;
    drained += 1;
    sleep_ms(5);
  }
  memset(&event, 0xFF, sizeof(event));
  expect_status(reader_tts_poll(g_main, &event, &available, NULL), READER_TTS_OK, "poll on an empty queue");
  note("drained=%d; ", drained);
  expect_uint((unsigned long)available, 0, "empty queue reports available=0");
  expect_uint((unsigned long)event.request_id, 0, "empty queue zeroes the request id");
  expect_uint((unsigned long)event.start, 0, "empty queue zeroes the range start");
  expect_uint((unsigned long)event.end, 0, "empty queue zeroes the range end");
  expect_uint((unsigned long)event.has_range, 0, "empty queue clears has_range");
  return g_case_failed ? 1 : 0;
}

static int case_speak_unknown_voice_argument(void) {
  if (!g_engine_mode) return 2;
  expect_status(reader_tts_speak(g_main, next_id(), SAMPLE, SAMPLE_BYTES,
    "no-such-voice-in-this-engine", 1.0, NULL), READER_TTS_ARGUMENT, "speak with an unknown voice id");
  return g_case_failed ? 1 : 0;
}

static int case_speak_over_engine_limit(void) {
  char *text = make_ascii(5000);
  if (!g_engine_mode) {
    free(text);
    return 2;
  }
  if (!text) {
    note("allocation failed; ");
    return 1;
  }
  expect_status(reader_tts_speak(g_main, next_id(), text, 5000, NULL, 1.0, NULL),
    READER_TTS_LIMIT, "speak above the engine text ceiling");
  free(text);
  return g_case_failed ? 1 : 0;
}

static int case_busy_while_active(void) {
  char *text = make_ascii(2000);
  reader_tts_snapshot snapshot;
  uint64_t request = next_id();
  if (!g_engine_mode) {
    free(text);
    return 2;
  }
  if (!text) {
    note("allocation failed; ");
    return 1;
  }
  expect_status(reader_tts_speak(g_main, request, text, 2000, NULL, 1.0, NULL),
    READER_TTS_OK, "speak a long sample");
  free(text);
  if (g_case_failed) return 1;
  sleep_ms(120);
  expect_status(reader_tts_speak(g_main, next_id(), SAMPLE, SAMPLE_BYTES, NULL, 1.0, NULL),
    READER_TTS_BUSY, "replacing an active request");
  expect_status(reader_tts_observe(g_main, &snapshot, NULL), READER_TTS_OK, "observe while speaking");
  expect_uint((unsigned long)snapshot.request_id, (unsigned long)request,
    "the active request id is unchanged");
  expect_status(reader_tts_stop(g_main, request, NULL), READER_TTS_OK, "stop the active request");
  g_last_accepted = request;
  return g_case_failed ? 1 : 0;
}

static int case_stop_single_stopped(void) {
  struct ledger log;
  int outcome = 0;
  if (!g_engine_mode) return 2;
  outcome = collect(g_main, g_last_accepted, 45000, SAMPLE, SAMPLE_BYTES, &log);
  expect_true(outcome == 0, "stopped request reaches a terminal event");
  expect_uint(log.stopped, 1, "exactly one STOPPED");
  expect_uint(log.finished, 0, "a stopped request does not also finish");
  expect_uint(log.failed, 0, "a stopped request does not fail");
  note("stopped=%u late=%u; ", log.stopped, log.late_known);
  remember_completed(g_last_accepted);
  return g_case_failed ? 1 : 0;
}

static int case_stop_completed_request_ok(void) {
  if (!g_engine_mode) return 2;
  expect_status(reader_tts_stop(g_main, g_last_accepted, NULL), READER_TTS_OK,
    "stop an already ended request");
  return g_case_failed ? 1 : 0;
}

static int case_stop_unknown_id_argument(void) {
  expect_status(reader_tts_stop(g_main, (uint64_t)1 << 40, NULL), READER_TTS_ARGUMENT,
    "stop a request id that was never issued");
  return g_case_failed ? 1 : 0;
}

static int case_late_events_keep_request_id(void) {
  struct ledger log;
  uint64_t request = next_id();
  int outcome = 0;
  if (!g_engine_mode) return 2;
  expect_status(reader_tts_speak(g_main, request, SAMPLE, SAMPLE_BYTES, NULL, 1.0, NULL),
    READER_TTS_OK, "speak after a stop");
  if (g_case_failed) return 1;
  outcome = collect(g_main, request, 45000, SAMPLE, SAMPLE_BYTES, &log);
  expect_true(outcome == 0, "terminal event after a stop");
  expect_uint(log.foreign_unknown, 0, "a late callback keeps its original request id");
  expect_uint(log.started, 1, "new request STARTED once");
  expect_uint(log.misordered, 0, "new request ordering");
  note("late_known=%u started=%u; ", log.late_known, log.started);
  g_last_accepted = request;
  remember_completed(request);
  return g_case_failed ? 1 : 0;
}

static int case_pause_unsupported_state_unchanged(void) {
  reader_tts_snapshot before;
  reader_tts_snapshot after;
  expect_status(reader_tts_observe(g_main, &before, NULL), READER_TTS_OK, "observe before pause");
  expect_status(reader_tts_pause(g_main, g_last_accepted ? g_last_accepted : 1, NULL),
    READER_TTS_UNSUPPORTED, "pause without a native pause capability");
  expect_status(reader_tts_observe(g_main, &after, NULL), READER_TTS_OK, "observe after pause");
  expect_uint((unsigned long)after.state, (unsigned long)before.state, "pause leaves the state unchanged");
  expect_uint((unsigned long)after.request_id, (unsigned long)before.request_id,
    "pause leaves the request id unchanged");
  return g_case_failed ? 1 : 0;
}

static int case_resume_unsupported_state_unchanged(void) {
  reader_tts_snapshot before;
  reader_tts_snapshot after;
  expect_status(reader_tts_observe(g_main, &before, NULL), READER_TTS_OK, "observe before resume");
  expect_status(reader_tts_resume(g_main, g_last_accepted ? g_last_accepted : 1, NULL),
    READER_TTS_UNSUPPORTED, "resume without a native pause capability");
  expect_status(reader_tts_observe(g_main, &after, NULL), READER_TTS_OK, "observe after resume");
  expect_uint((unsigned long)after.state, (unsigned long)before.state, "resume leaves the state unchanged");
  return g_case_failed ? 1 : 0;
}

static int case_service_unavailable_when_engine_missing(void) {
  reader_tts *tts = NULL;
  reader_tts_voice_list list;
  reader_tts_snapshot snapshot;
  reader_tts_state state = READER_TTS_INITIALIZING;
  reader_tts_error error;
  if (g_engine_mode) return 2;
  memset(&error, 0, sizeof(error));
  memset(&list, 0, sizeof(list));
  expect_status(reader_tts_create(NULL, &tts, &error), READER_TTS_OK, "create without an engine");
  if (!tts) return 1;
  expect_true(wait_state(tts, 30000, &state) == 0, "the missing engine settles");
  expect_true(state == READER_TTS_SERVICE_UNAVAILABLE, "missing engine reports SERVICE_UNAVAILABLE");
  expect_status(reader_tts_observe(tts, &snapshot, NULL), READER_TTS_OK, "observe missing engine");
  expect_true(snapshot.state == READER_TTS_SERVICE_UNAVAILABLE, "snapshot state");
  expect_status(reader_tts_speak(tts, next_id(), SAMPLE, SAMPLE_BYTES, NULL, 1.0, &error),
    READER_TTS_UNAVAILABLE, "speak without an engine");
  expect_status(reader_tts_voices(tts, &list, NULL), READER_TTS_UNAVAILABLE, "voices without an engine");
  note("init_status=%d native=%d; ", (int)snapshot.last_status, error.native_code);
  expect_status(reader_tts_request_close(tts, NULL), READER_TTS_OK, "close a missing-engine handle");
  expect_true(wait_closed(tts, 20000, &state) == 0, "missing-engine handle reaches CLOSED");
  expect_status(reader_tts_destroy(&tts, NULL), READER_TTS_OK, "destroy a missing-engine handle");
  expect_true(tts == NULL, "destroyed missing-engine handle is cleared");
  return g_case_failed ? 1 : 0;
}

static int case_voices_lifetime_after_destroy(void) {
  reader_tts *tts = NULL;
  reader_tts_voice_list list;
  reader_tts_state state = READER_TTS_INITIALIZING;
  size_t count = 0;
  if (!g_engine_mode) return 2;
  memset(&list, 0, sizeof(list));
  expect_status(reader_tts_create(NULL, &tts, NULL), READER_TTS_OK, "create a throwaway handle");
  if (!tts) return 1;
  expect_true(wait_state(tts, 30000, &state) == 0 && state == READER_TTS_READY,
    "throwaway handle reaches READY");
  expect_status(reader_tts_voices(tts, &list, NULL), READER_TTS_OK, "voices before destroy");
  count = list.count;
  expect_status(reader_tts_request_close(tts, NULL), READER_TTS_OK, "close the throwaway handle");
  expect_true(wait_closed(tts, 20000, &state) == 0, "throwaway handle reaches CLOSED");
  expect_status(reader_tts_destroy(&tts, NULL), READER_TTS_OK, "destroy the throwaway handle");
  expect_true(tts == NULL, "throwaway handle is cleared");
  expect_true(count > 0 && list.count == count, "the voice list keeps its count after destroy");
  expect_true(list.voices && list.voices[0].id && list.voices[0].id[0] != 0,
    "voice strings stay readable after destroy");
  reader_tts_voice_list_free(&list);
  return g_case_failed ? 1 : 0;
}

static int case_destroy_wrong_owner_rejected(void) {
  struct owner_args args;
  pthread_t worker;
  if (!g_main) return 1;
  memset(&args, 0, sizeof(args));
  args.tts = g_main;
  args.status = READER_TTS_OK;
  args.value = 0;
  if (pthread_create(&worker, NULL, destroy_thread, &args) != 0) {
    note("pthread_create failed; ");
    return 1;
  }
  pthread_join(worker, NULL);
  expect_status(args.status, READER_TTS_OWNER, "destroy from a foreign thread");
  expect_true(args.value == 1, "a refused destroy keeps the handle pointer");
  return g_case_failed ? 1 : 0;
}

static int case_close_idempotent_and_refuses_new_requests(void) {
  reader_tts_state state = READER_TTS_INITIALIZING;
  if (!g_main) return 1;
  expect_status(reader_tts_request_close(g_main, NULL), READER_TTS_OK, "request_close");
  expect_status(reader_tts_request_close(g_main, NULL), READER_TTS_OK, "second request_close");
  expect_status(reader_tts_speak(g_main, next_id(), SAMPLE, SAMPLE_BYTES, NULL, 1.0, NULL),
    READER_TTS_UNAVAILABLE, "speak after close");
  expect_status(reader_tts_stop(g_main, g_last_accepted ? g_last_accepted : 1, NULL),
    READER_TTS_UNAVAILABLE, "stop after close");
  expect_true(wait_closed(g_main, 20000, &state) == 0, "close reaches CLOSED");
  expect_uint((unsigned long)state, (unsigned long)READER_TTS_CLOSED, "final state is CLOSED");
  return g_case_failed ? 1 : 0;
}

static int case_no_events_after_closed(void) {
  reader_tts_event event;
  int available = 1;
  int drained = 0;
  if (!g_main) return 1;
  for (int step = 0; step < 400; step++) {
    expect_status(reader_tts_poll(g_main, &event, &available, NULL), READER_TTS_OK, "poll after close");
    if (!available) break;
    drained += 1;
    sleep_ms(5);
  }
  expect_uint((unsigned long)available, 0, "no events remain after CLOSED");
  note("drained=%d; ", drained);
  return g_case_failed ? 1 : 0;
}

static int case_destroy_until_closed_and_null(void) {
  reader_tts *extra = NULL;
  reader_tts *copy = NULL;
  reader_tts_state state = READER_TTS_INITIALIZING;
  reader_tts_status first = READER_TTS_OK;
  if (!g_main) return 1;
  expect_status(reader_tts_destroy(&g_main, NULL), READER_TTS_OK, "destroy a CLOSED handle");
  expect_true(g_main == NULL, "destroyed handle is cleared");
  expect_status(reader_tts_destroy(&g_main, NULL), READER_TTS_ARGUMENT, "destroy with a NULL handle");
  expect_status(reader_tts_create(NULL, &extra, NULL), READER_TTS_OK, "create a handle for the closing branch");
  if (!extra) return 1;
  expect_true(wait_state(extra, 30000, &state) == 0, "closing-branch handle settles");
  expect_status(reader_tts_request_close(extra, NULL), READER_TTS_OK, "close the closing-branch handle");
  copy = extra;
  first = reader_tts_destroy(&copy, NULL);
  if (first == READER_TTS_BUSY) {
    expect_true(copy == extra, "BUSY destroy keeps the pointer");
    expect_true(wait_closed(extra, 20000, &state) == 0, "closing-branch handle reaches CLOSED");
    expect_status(reader_tts_destroy(&copy, NULL), READER_TTS_OK, "destroy after the close completed");
  } else {
    expect_status(first, READER_TTS_OK, "destroy after an immediate close");
  }
  expect_true(copy == NULL, "closing-branch pointer is cleared");
  note("first_destroy=%d; ", (int)first);
  return g_case_failed ? 1 : 0;
}

/* Three bounded chunks at double speed: enough to prove that a text above the
   host chunk size is spoken chunk by chunk with one terminal event each, while
   keeping real playback time short enough for a timed wait. */
static int case_long_text_chunked_requests(void) {
  size_t total = 900;
  size_t offset = 0;
  unsigned chunks = 0;
  char *text = make_ascii(total);
  if (!g_engine_mode) {
    free(text);
    return 2;
  }
  if (!text) {
    note("allocation failed; ");
    return 1;
  }
  while (offset < total) {
    size_t end = offset + 300 < total ? offset + 300 : total;
    struct ledger log;
    uint64_t request = 0;
    if (end < total) {
      size_t scan = end;
      while (scan > offset && text[scan] != ' ') scan -= 1;
      if (scan > offset) end = scan + 1;
    }
    request = next_id();
    expect_status(reader_tts_speak(g_main, request, text + offset, end - offset, NULL, 2.0, NULL),
      READER_TTS_OK, "speak a bounded chunk");
    if (g_case_failed) break;
    if (collect(g_main, request, 45000, text + offset, end - offset, &log) != 0) {
      note("chunk %u did not terminate; ", chunks);
      g_case_failed = 1;
      break;
    }
    expect_uint(log.started, 1, "chunk STARTED");
    expect_uint(log.finished + log.stopped + log.failed, 1, "chunk terminal");
    remember_completed(request);
    offset = end;
    chunks += 1;
  }
  expect_uint((unsigned long)offset, (unsigned long)total, "every byte is spoken exactly once");
  expect_true(chunks >= 2, "long text needs more than one chunk");
  note("chunks=%u bytes=%lu; ", chunks, (unsigned long)total);
  free(text);
  return g_case_failed ? 1 : 0;
}

struct named_case {
  const char *name;
  int (*run)(void);
};

static const struct named_case g_cases[] = {
  { "initialize_null_argument", case_initialize_null_argument },
  { "create_before_bind_unavailable", case_create_before_bind_unavailable },
  { "initialize_binds", case_initialize_binds },
  { "initialize_idempotent", case_initialize_idempotent },
  { "create_null_out_argument", case_create_null_out_argument },
  { "create_struct_size_mismatch_argument", case_create_struct_size_mismatch_argument },
  { "create_limit_above_hard_cap_argument", case_create_limit_above_hard_cap_argument },
  { "create_initializing_or_unavailable", case_create_initializing_or_unavailable },
  { "create_lowered_limit_handle", case_create_lowered_limit_handle },
  { "observe_wrong_owner_rejected", case_observe_wrong_owner_rejected },
  { "speak_null_text_argument", case_speak_null_text_argument },
  { "speak_zero_request_id_argument", case_speak_zero_request_id_argument },
  { "speak_empty_text_argument", case_speak_empty_text_argument },
  { "speak_invalid_utf8_argument", case_speak_invalid_utf8_argument },
  { "speak_incomplete_scalar_argument", case_speak_incomplete_scalar_argument },
  { "speak_embedded_nul_argument", case_speak_embedded_nul_argument },
  { "speak_surrogate_scalar_argument", case_speak_surrogate_scalar_argument },
  { "speak_rate_out_of_range_argument", case_speak_rate_out_of_range_argument },
  { "speak_over_configured_limit", case_speak_over_configured_limit },
  { "voices_listing", case_voices_listing },
  { "voices_free_null_safe", case_voices_free_null_safe },
  { "speak_started_and_finished", case_speak_started_and_finished },
  { "speak_request_id_reuse_argument", case_speak_request_id_reuse_argument },
  { "single_terminal_per_request", case_single_terminal_per_request },
  { "range_utf8_boundaries", case_range_utf8_boundaries },
  { "poll_empty_available_zero", case_poll_empty_available_zero },
  { "speak_unknown_voice_argument", case_speak_unknown_voice_argument },
  { "speak_over_engine_limit", case_speak_over_engine_limit },
  { "busy_while_active", case_busy_while_active },
  { "stop_single_stopped", case_stop_single_stopped },
  { "stop_completed_request_ok", case_stop_completed_request_ok },
  { "stop_unknown_id_argument", case_stop_unknown_id_argument },
  { "late_events_keep_request_id", case_late_events_keep_request_id },
  { "pause_unsupported_state_unchanged", case_pause_unsupported_state_unchanged },
  { "resume_unsupported_state_unchanged", case_resume_unsupported_state_unchanged },
  { "service_unavailable_when_engine_missing", case_service_unavailable_when_engine_missing },
  { "voices_lifetime_after_destroy", case_voices_lifetime_after_destroy },
  { "destroy_wrong_owner_rejected", case_destroy_wrong_owner_rejected },
  { "long_text_chunked_requests", case_long_text_chunked_requests },
  { "close_idempotent_and_refuses_new_requests", case_close_idempotent_and_refuses_new_requests },
  { "no_events_after_closed", case_no_events_after_closed },
  { "destroy_until_closed_and_null", case_destroy_until_closed_and_null }
};

void exr_tts_consumer_set_mode(int engine_expected) {
  g_engine_mode = engine_expected ? 1 : 0;
  g_next_id = 0;
  g_last_accepted = 0;
  g_completed_count = 0;
  g_case_failed = 0;
  g_detail_length = 0;
  g_detail[0] = 0;
}

int exr_tts_consumer_case_count(void) {
  return (int)(sizeof(g_cases) / sizeof(g_cases[0]));
}

const char *exr_tts_consumer_case_name(int id) {
  if (id < 0 || (size_t)id >= sizeof(g_cases) / sizeof(g_cases[0])) return "";
  return g_cases[id].name;
}

int exr_tts_consumer_case(int id) {
  if (id < 0 || (size_t)id >= sizeof(g_cases) / sizeof(g_cases[0])) return 1;
  g_case_failed = 0;
  g_detail_length = 0;
  g_detail[0] = 0;
  return g_cases[id].run();
}

const char *exr_tts_consumer_detail(void) {
  return g_detail;
}
