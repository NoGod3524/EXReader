/* SPDX-License-Identifier: MIT */
/* Independent installed-package consumer for the J19 Linux reader TTS backend.
   Built only against the installed CMake package (EXReaderTTSLinux::reader_tts),
   it drives the real system Speech Dispatcher and emits one named result per
   case as JSON. No library test hook is used here. */
#include "reader_tts.h"
#include "result_writer.h"
#include <dirent.h>
#include <errno.h>
#include <math.h>
#include <pthread.h>
#include <signal.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>
#include <time.h>
#include <unistd.h>

#define DETAIL 512
#define CASE_TIMEOUT_MS 30000
#define LONG_BYTES 12288u
#define TEXT_CAP 20000

typedef struct {
  FILE *f;
  int first;
  int fails;
} suite;

typedef struct {
  int started, finished, stopped, failed, range, other, foreign;
} counts;

typedef struct {
  counts c;
  int have_terminal;
  int term_status;
} runstate;

static void rs_init(runstate *rs) {
  memset(rs, 0, sizeof *rs);
  rs->term_status = READER_TTS_OK;
}

static void sleep_ms(int ms) {
  struct timespec ts;
  ts.tv_sec = ms / 1000;
  ts.tv_nsec = (long)(ms % 1000) * 1000000L;
  nanosleep(&ts, NULL);
}
static const char *state_name(int s) {
  switch (s) {
  case READER_TTS_INITIALIZING: return "INITIALIZING";
  case READER_TTS_READY: return "READY";
  case READER_TTS_SPEAKING: return "SPEAKING";
  case READER_TTS_PAUSED: return "PAUSED";
  case READER_TTS_STOPPING: return "STOPPING";
  case READER_TTS_CLOSING: return "CLOSING";
  case READER_TTS_CLOSED: return "CLOSED";
  case READER_TTS_SERVICE_UNAVAILABLE: return "SERVICE_UNAVAILABLE";
  default: return "?";
  }
}
static const char *status_name(int s) {
  switch (s) {
  case READER_TTS_OK: return "OK";
  case READER_TTS_ARGUMENT: return "ARGUMENT";
  case READER_TTS_OWNER: return "OWNER";
  case READER_TTS_BUSY: return "BUSY";
  case READER_TTS_UNAVAILABLE: return "UNAVAILABLE";
  case READER_TTS_UNSUPPORTED: return "UNSUPPORTED";
  case READER_TTS_IO: return "IO";
  case READER_TTS_MEMORY: return "MEMORY";
  case READER_TTS_LIMIT: return "LIMIT";
  default: return "?";
  }
}
static void report(suite *s, const char *name, int ok, const char *fmt, ...) {
  char detail[DETAIL];
  va_list ap;
  va_start(ap, fmt);
  vsnprintf(detail, sizeof detail, fmt, ap);
  va_end(ap);
  rw_case(s->f, &s->first, name, ok, detail);
  if (!ok) ++s->fails;
  fprintf(stdout, "%s %s: %s\n", ok ? "pass" : "FAIL", name, detail);
  fflush(stdout);
}

static void note_event(runstate *rs, const reader_tts_event *ev) {
  switch (ev->kind) {
  case READER_TTS_STARTED: ++rs->c.started; break;
  case READER_TTS_FINISHED:
    ++rs->c.finished;
    rs->have_terminal = 1;
    rs->term_status = ev->status;
    break;
  case READER_TTS_STOPPED:
    ++rs->c.stopped;
    rs->have_terminal = 1;
    rs->term_status = ev->status;
    break;
  case READER_TTS_FAILED:
    ++rs->c.failed;
    rs->have_terminal = 1;
    rs->term_status = ev->status;
    break;
  case READER_TTS_RANGE: ++rs->c.range; break;
  default: ++rs->c.other; break;
  }
}

/* Polls until the request's STARTED event arrived (a terminal implies it was
   queued first, so nothing is lost). Returns 0 when the timeout elapsed. */
static int await_started(reader_tts *h, uint64_t id, int timeout_ms, runstate *rs) {
  int waited = 0, av = 0;
  reader_tts_event ev;
  reader_tts_error err;
  while (waited < timeout_ms) {
    if (reader_tts_poll(h, &ev, &av, &err) != READER_TTS_OK) return 0;
    if (av && ev.request_id == id) {
      note_event(rs, &ev);
      if (ev.kind == READER_TTS_STARTED || rs->have_terminal) return 1;
    }
    sleep_ms(5);
    waited += 5;
  }
  return 0;
}
static int await_terminal(reader_tts *h, uint64_t id, int timeout_ms, runstate *rs) {
  int waited = 0, av = 0;
  reader_tts_event ev;
  reader_tts_error err;
  if (rs->have_terminal) return 1;
  while (waited < timeout_ms) {
    if (reader_tts_poll(h, &ev, &av, &err) != READER_TTS_OK) return 0;
    if (av && ev.request_id == id) {
      note_event(rs, &ev);
      if (rs->have_terminal) return 1;
    }
    sleep_ms(5);
    waited += 5;
  }
  return 0;
}
/* Drains everything the queue already holds for this request without waiting. */
static void drain(reader_tts *h, uint64_t id, runstate *rs) {
  int av = 0;
  reader_tts_event ev;
  reader_tts_error err;
  while (reader_tts_poll(h, &ev, &av, &err) == READER_TTS_OK && av) {
    if (ev.request_id == id || id == 0) note_event(rs, &ev);
  }
}
static int run_request(reader_tts *h, uint64_t id, const char *text, size_t n, const char *voice,
                       double rate, int timeout_ms, runstate *rs) {
  reader_tts_error err;
  rs_init(rs);
  if (reader_tts_speak(h, id, text, n, voice, rate, &err) != READER_TTS_OK) return 0;
  if (!await_started(h, id, timeout_ms, rs)) return 0;
  return await_terminal(h, id, timeout_ms, rs);
}
static int wait_closed(reader_tts *h, int timeout_ms, reader_tts_state *state_out) {
  int waited = 0;
  reader_tts_error err;
  reader_tts_snapshot snap;
  memset(&snap, 0, sizeof snap);
  while (waited <= timeout_ms) {
    if (reader_tts_observe(h, &snap, &err) != READER_TTS_OK) break;
    if (snap.state == READER_TTS_CLOSED) break;
    sleep_ms(5);
    waited += 5;
  }
  if (state_out) *state_out = snap.state;
  return snap.state == READER_TTS_CLOSED;
}

/* Counts running speech-dispatcher processes through /proc/<pid>/comm. */
static int daemon_processes(void) {
  DIR *d = opendir("/proc");
  struct dirent *e;
  int n = 0;
  if (!d) return -1;
  while ((e = readdir(d)) != NULL) {
    char path[256], comm[64];
    FILE *f;
    size_t len;
    if (e->d_name[0] < '0' || e->d_name[0] > '9') continue;
    snprintf(path, sizeof path, "/proc/%s/comm", e->d_name);
    f = fopen(path, "r");
    if (!f) continue;
    if (fgets(comm, sizeof comm, f)) {
      len = strlen(comm);
      while (len && (comm[len - 1] == '\n' || comm[len - 1] == '\r')) comm[--len] = 0;
      if (strncmp(comm, "speech-dispat", 13) == 0) ++n;
    }
    fclose(f);
  }
  closedir(d);
  return n;
}

static void fill_ascii(char *buf, size_t n, char ch) { memset(buf, ch, n); }
static size_t fill_repeat(char *buf, size_t bytes, const char *unit) {
  size_t u = strlen(unit), i = 0;
  while (i + u <= bytes) {
    memcpy(buf + i, unit, u);
    i += u;
  }
  while (i < bytes) buf[i++] = ' ';
  return bytes;
}

typedef struct {
  reader_tts *h;
  reader_tts_status observe_status;
  reader_tts_status speak_status;
  reader_tts_snapshot snap;
} foreign_call;
static void *foreign_thread(void *arg) {
  foreign_call *c = (foreign_call *)arg;
  reader_tts_error err;
  memset(&c->snap, 0, sizeof c->snap);
  c->observe_status = reader_tts_observe(c->h, &c->snap, &err);
  c->speak_status = reader_tts_speak(c->h, 999000, "x", 1, NULL, 1.0, &err);
  return NULL;
}

/* ------------------------------------------------------------- live phase -- */
static void phase_live(suite *s) {
  reader_tts_error err;
  reader_tts *h = NULL, *h2 = NULL, *h3 = NULL;
  reader_tts_config cfg;
  reader_tts_snapshot snap;
  reader_tts_voice_list list;
  reader_tts_voice_list scratch;
  reader_tts_status st;
  runstate rs;
  char text[TEXT_CAP];
  uint64_t id = 1, first_id;
  int ok;

  memset(&err, 0, sizeof err);
  memset(&snap, 0, sizeof snap);
  memset(&cfg, 0, sizeof cfg);
  cfg.struct_size = sizeof cfg;
  st = reader_tts_create(&cfg, &h, &err);
  if (h) reader_tts_observe(h, &snap, &err);
  report(s, "create_default_config_ready",
         st == READER_TTS_OK && h != NULL && err.code == READER_TTS_OK && snap.state == READER_TTS_READY,
         "status=%s state=%s", status_name(st), h ? state_name(snap.state) : "-");
  if (!h) return;

  st = reader_tts_observe(h, &snap, &err);
  report(s, "observe_initial_snapshot",
         st == READER_TTS_OK && snap.state == READER_TTS_READY &&
             (snap.capabilities & READER_TTS_CAN_PAUSE) != 0 &&
             (snap.capabilities & READER_TTS_CAN_REPORT_RANGE) == 0 && snap.request_id == 0,
         "state=%s caps=%u id=%llu last=%s", state_name(snap.state), snap.capabilities,
         (unsigned long long)snap.request_id, status_name(snap.last_status));

  memset(&list, 0, sizeof list);
  st = reader_tts_voices(h, &list, &err);
  report(s, "voices_list_nonempty",
         st == READER_TTS_OK && list.count >= 1 && list.voices != NULL &&
             list.voices[0].id != NULL && list.voices[0].id[0] != 0,
         "status=%s count=%zu first=%s", status_name(st), list.count,
         (list.count && list.voices[0].id) ? list.voices[0].id : "-");
  {
    int bounded = (st == READER_TTS_OK), i;
    for (i = 0; bounded && (size_t)i < list.count; ++i)
      bounded = list.voices[i].id != NULL &&
                strlen(list.voices[i].id) < READER_TTS_MAX_VOICE_FIELD &&
                list.voices[i].name != NULL && list.voices[i].language != NULL;
    report(s, "voices_fields_bounded", bounded, "count=%zu limit=%u", list.count,
           (unsigned)READER_TTS_MAX_VOICE_FIELD);
  }

  first_id = id;
  fill_ascii(text, 24, 'a');
  ok = run_request(h, id, text, 24, NULL, 1.0, CASE_TIMEOUT_MS, &rs);
  report(s, "speak_started_event", ok && rs.c.started == 1, "started=%d finished=%d failed=%d",
         rs.c.started, rs.c.finished, rs.c.failed);
  report(s, "speak_finished_event",
         ok && rs.c.finished == 1 && rs.c.failed == 0 && rs.c.stopped == 0 &&
             rs.term_status == READER_TTS_OK,
         "finished=%d status=%s", rs.c.finished, status_name(rs.term_status));
  st = reader_tts_observe(h, &snap, &err);
  report(s, "speak_state_ready_after_finish", st == READER_TTS_OK && snap.state == READER_TTS_READY,
         "state=%s", state_name(snap.state));
  report(s, "observe_reports_last_request_id", snap.request_id == id, "id=%llu want=%llu",
         (unsigned long long)snap.request_id, (unsigned long long)id);

  /* a long utterance stays active: BUSY, pause, resume, stop */
  id = 2;
  fill_repeat(text, LONG_BYTES, "\xE6\x9C\x97\xE8\xAF\xBB\xE6\xB5\x8B\xE8\xAF\x95\xE3\x80\x82");
  rs_init(&rs);
  st = reader_tts_speak(h, id, text, LONG_BYTES, NULL, 0.5, &err);
  ok = (st == READER_TTS_OK) && await_started(h, id, CASE_TIMEOUT_MS, &rs);
  reader_tts_observe(h, &snap, &err);
  report(s, "speak_long_utterance_started", ok && snap.state == READER_TTS_SPEAKING,
         "status=%s state=%s", status_name(st), state_name(snap.state));
  st = reader_tts_speak(h, id + 100, "b", 1, NULL, 1.0, &err);
  report(s, "speak_busy_second_request", st == READER_TTS_BUSY, "status=%s", status_name(st));
  reader_tts_observe(h, &snap, &err);
  report(s, "speak_busy_state_unchanged",
         snap.state == READER_TTS_SPEAKING && snap.request_id == id, "state=%s id=%llu",
         state_name(snap.state), (unsigned long long)snap.request_id);

  st = reader_tts_pause(h, id, &err);
  reader_tts_observe(h, &snap, &err);
  report(s, "pause_transitions_to_paused", st == READER_TTS_OK && snap.state == READER_TTS_PAUSED,
         "status=%s state=%s", status_name(st), state_name(snap.state));
  st = reader_tts_pause(h, id, &err);
  report(s, "pause_idempotent_ok", st == READER_TTS_OK, "status=%s", status_name(st));
  st = reader_tts_pause(h, id + 7, &err);
  report(s, "pause_wrong_request_id_rejected", st == READER_TTS_ARGUMENT, "status=%s",
         status_name(st));
  st = reader_tts_resume(h, id, &err);
  reader_tts_observe(h, &snap, &err);
  report(s, "resume_transitions_to_speaking",
         st == READER_TTS_OK && snap.state == READER_TTS_SPEAKING, "status=%s state=%s",
         status_name(st), state_name(snap.state));
  st = reader_tts_resume(h, id, &err);
  report(s, "resume_idempotent_ok", st == READER_TTS_OK, "status=%s", status_name(st));
  st = reader_tts_stop(h, id, &err);
  await_terminal(h, id, 5000, &rs);
  drain(h, id, &rs);
  report(s, "stop_emits_stopped_once",
         st == READER_TTS_OK && rs.c.stopped == 1 && rs.c.finished == 0,
         "status=%s stopped=%d finished=%d failed=%d", status_name(st), rs.c.stopped, rs.c.finished,
         rs.c.failed);
  st = reader_tts_observe(h, &snap, &err);
  report(s, "stop_state_ready", st == READER_TTS_OK && snap.state == READER_TTS_READY, "state=%s",
         state_name(snap.state));
  st = reader_tts_stop(h, id, &err);
  report(s, "stop_after_finish_is_ok", st == READER_TTS_OK, "status=%s", status_name(st));
  st = reader_tts_stop(h, id + 999, &err);
  report(s, "stop_unknown_id_rejected", st == READER_TTS_ARGUMENT, "status=%s", status_name(st));

  /* input validation and limits */
  st = reader_tts_speak(h, first_id, "a", 1, NULL, 1.0, &err);
  report(s, "speak_request_id_reuse_rejected", st == READER_TTS_ARGUMENT, "status=%s",
         status_name(st));
  st = reader_tts_speak(h, 0, "a", 1, NULL, 1.0, &err);
  report(s, "speak_zero_id_rejected", st == READER_TTS_ARGUMENT, "status=%s", status_name(st));
  st = reader_tts_speak(h, ++id, NULL, 4, NULL, 1.0, &err);
  report(s, "speak_null_text_rejected", st == READER_TTS_ARGUMENT, "status=%s", status_name(st));
  st = reader_tts_speak(h, ++id, "abcd", 0, NULL, 1.0, &err);
  report(s, "speak_zero_bytes_rejected", st == READER_TTS_ARGUMENT, "status=%s", status_name(st));
  st = reader_tts_speak(h, ++id, "\xE6\x9C", 2, NULL, 1.0, &err);
  report(s, "speak_truncated_utf8_rejected", st == READER_TTS_ARGUMENT, "status=%s",
         status_name(st));
  st = reader_tts_speak(h, ++id, "\xED\xA0\x80", 3, NULL, 1.0, &err);
  report(s, "speak_lone_surrogate_rejected", st == READER_TTS_ARGUMENT, "status=%s",
         status_name(st));
  st = reader_tts_speak(h, ++id, "\xC0\x80", 2, NULL, 1.0, &err);
  report(s, "speak_overlong_utf8_rejected", st == READER_TTS_ARGUMENT, "status=%s",
         status_name(st));
  st = reader_tts_speak(h, ++id, "\xF5\x80\x80\x80", 4, NULL, 1.0, &err);
  report(s, "speak_out_of_range_scalar_rejected", st == READER_TTS_ARGUMENT, "status=%s",
         status_name(st));
  st = reader_tts_speak(h, ++id, "ab\0cd", 5, NULL, 1.0, &err);
  report(s, "speak_embedded_nul_rejected", st == READER_TTS_ARGUMENT, "status=%s", status_name(st));
  st = reader_tts_observe(h, &snap, &err);
  report(s, "speak_invalid_input_leaves_ready", st == READER_TTS_OK && snap.state == READER_TTS_READY,
         "state=%s", state_name(snap.state));

  fill_ascii(text, READER_TTS_DEFAULT_MAX_UTF8 + 1, 'a');
  st = reader_tts_speak(h, ++id, text, READER_TTS_DEFAULT_MAX_UTF8 + 1, NULL, 1.0, &err);
  report(s, "speak_over_max_bytes_limit", st == READER_TTS_LIMIT, "status=%s", status_name(st));
  rs_init(&rs);
  st = reader_tts_speak(h, ++id, text, READER_TTS_DEFAULT_MAX_UTF8, NULL, 2.0, &err);
  ok = (st == READER_TTS_OK) && await_started(h, id, CASE_TIMEOUT_MS, &rs);
  report(s, "speak_max_bytes_accepted", ok, "status=%s bytes=%u", status_name(st),
         (unsigned)READER_TTS_DEFAULT_MAX_UTF8);
  reader_tts_stop(h, id, &err);
  await_terminal(h, id, 5000, &rs);
  drain(h, id, &rs);

  fill_ascii(text, 30, 'b');
  {
    double rates[2] = {0.5, 2.0};
    const char *names[2] = {"speak_rate_low_accepted", "speak_rate_high_accepted"};
    int k;
    for (k = 0; k < 2; ++k) {
      ok = run_request(h, ++id, text, 30, NULL, rates[k], CASE_TIMEOUT_MS, &rs);
      report(s, names[k], ok && rs.c.finished == 1, "rate=%.1f finished=%d status=%s", rates[k],
             rs.c.finished, status_name(rs.term_status));
    }
  }
  st = reader_tts_speak(h, ++id, text, 30, NULL, 2.01, &err);
  report(s, "speak_rate_above_range_rejected", st == READER_TTS_ARGUMENT, "status=%s",
         status_name(st));
  st = reader_tts_speak(h, ++id, text, 30, NULL, 0.49, &err);
  report(s, "speak_rate_below_range_rejected", st == READER_TTS_ARGUMENT, "status=%s",
         status_name(st));
  st = reader_tts_speak(h, ++id, text, 30, NULL, (double)NAN, &err);
  report(s, "speak_rate_nan_rejected", st == READER_TTS_ARGUMENT, "status=%s", status_name(st));
  st = reader_tts_speak(h, ++id, text, 30, NULL, (double)INFINITY, &err);
  report(s, "speak_rate_inf_rejected", st == READER_TTS_ARGUMENT, "status=%s", status_name(st));
  st = reader_tts_speak(h, ++id, text, 30, "exreader-voice-that-does-not-exist", 1.0, &err);
  report(s, "speak_unknown_voice_rejected", st == READER_TTS_ARGUMENT, "status=%s",
         status_name(st));
  if (list.count) {
    ok = run_request(h, ++id, text, 30, list.voices[0].id, 1.0, CASE_TIMEOUT_MS, &rs);
    report(s, "speak_known_voice_accepted", ok && rs.c.finished == 1, "voice=%s finished=%d",
           list.voices[0].id, rs.c.finished);
    ok = run_request(h, ++id, text, 30, NULL, 1.0, CASE_TIMEOUT_MS, &rs);
    report(s, "voice_reset_after_custom", ok && rs.c.finished == 1, "finished=%d status=%s",
           rs.c.finished, status_name(rs.term_status));
  } else {
    report(s, "speak_known_voice_accepted", 0, "daemon listed no voice to select");
    report(s, "voice_reset_after_custom", 0, "daemon listed no voice to select");
  }

  fill_repeat(text, 36, "\xE6\x9C\x97\xE8\xAF\xBB\xE6\xB5\x8B\xE8\xAF\x95\xE3\x80\x82");
  ok = run_request(h, ++id, text, 36, NULL, 2.0, CASE_TIMEOUT_MS, &rs);
  report(s, "speak_cjk_text_finished", ok && rs.c.finished == 1 && rs.c.started == 1, "finished=%d",
         rs.c.finished);
  {
    size_t n = fill_repeat(text, 32, "\xF0\x9F\x93\x96");
    ok = run_request(h, ++id, text, n, NULL, 2.0, CASE_TIMEOUT_MS, &rs);
    report(s, "speak_emoji_finished", ok && rs.c.finished == 1, "bytes=%zu finished=%d", n,
           rs.c.finished);
  }
  {
    size_t n = fill_repeat(text, 24, "e\xCC\x81");
    ok = run_request(h, ++id, text, n, NULL, 2.0, CASE_TIMEOUT_MS, &rs);
    report(s, "speak_combining_marks_finished", ok && rs.c.finished == 1, "bytes=%zu finished=%d", n,
           rs.c.finished);
  }

  {
    int av = 7;
    reader_tts_event ev;
    st = reader_tts_poll(h, NULL, &av, &err);
    report(s, "poll_null_arguments_rejected", st == READER_TTS_ARGUMENT, "status=%s",
           status_name(st));
    st = reader_tts_observe(h, NULL, &err);
    report(s, "observe_null_snapshot_rejected", st == READER_TTS_ARGUMENT, "status=%s",
           status_name(st));
    st = reader_tts_speak(NULL, ++id, "a", 1, NULL, 1.0, &err);
    report(s, "speak_null_handle_rejected", st == READER_TTS_ARGUMENT, "status=%s",
           status_name(st));
    st = reader_tts_voices(NULL, &list, &err);
    report(s, "voices_null_handle_rejected", st == READER_TTS_ARGUMENT, "status=%s",
           status_name(st));
    st = reader_tts_create(&cfg, NULL, &err);
    report(s, "create_null_out_rejected", st == READER_TTS_ARGUMENT, "status=%s", status_name(st));
    drain(h, 0, &rs);
    rs_init(&rs);
    st = reader_tts_poll(h, &ev, &av, &err);
    report(s, "poll_empty_clears_event",
           st == READER_TTS_OK && av == 0 && ev.request_id == 0 && ev.kind == READER_TTS_STARTED &&
               ev.start == 0 && ev.end == 0 && ev.has_range == 0,
           "status=%s available=%d", status_name(st), av);
  }

  {
    pthread_t t;
    foreign_call fc;
    memset(&fc, 0, sizeof fc);
    fc.h = h;
    if (pthread_create(&t, NULL, foreign_thread, &fc) == 0) {
      pthread_join(t, NULL);
      report(s, "foreign_thread_observe_owner", fc.observe_status == READER_TTS_OWNER, "status=%s",
             status_name(fc.observe_status));
      report(s, "foreign_thread_speak_owner", fc.speak_status == READER_TTS_OWNER, "status=%s",
             status_name(fc.speak_status));
      st = reader_tts_observe(h, &snap, &err);
      report(s, "foreign_thread_state_unchanged", st == READER_TTS_OK && snap.state == READER_TTS_READY,
             "state=%s", state_name(snap.state));
    } else {
      report(s, "foreign_thread_observe_owner", 0, "pthread_create failed");
      report(s, "foreign_thread_speak_owner", 0, "pthread_create failed");
      report(s, "foreign_thread_state_unchanged", 0, "pthread_create failed");
    }
  }

  /* libspeechd keeps one process connection: a second handle stays unavailable */
  st = reader_tts_create(&cfg, &h2, &err);
  {
    reader_tts_snapshot s2;
    int good = (st == READER_TTS_OK && h2 != NULL);
    memset(&s2, 0, sizeof s2);
    if (good) reader_tts_observe(h2, &s2, &err);
    report(s, "second_handle_connection_unavailable",
           good && s2.state == READER_TTS_SERVICE_UNAVAILABLE &&
               s2.last_status == READER_TTS_UNAVAILABLE,
           "status=%s state=%s native=%d", status_name(st), good ? state_name(s2.state) : "-",
           err.native_code);
  }
  if (h2) {
    reader_tts_state end = READER_TTS_INITIALIZING;
    int closed;
    reader_tts_request_close(h2, &err);
    closed = wait_closed(h2, 5000, &end);
    report(s, "second_handle_close_clean", closed, "state=%s", state_name(end));
    st = reader_tts_destroy(&h2, &err);
    report(s, "second_handle_destroyed", st == READER_TTS_OK && h2 == NULL, "status=%s",
           status_name(st));
  } else {
    report(s, "second_handle_close_clean", 0, "second handle missing");
    report(s, "second_handle_destroyed", 0, "second handle missing");
  }

  /* lifecycle of the first handle */
  st = reader_tts_destroy(&h, &err);
  report(s, "destroy_before_closed_busy", st == READER_TTS_BUSY && h != NULL, "status=%s",
         status_name(st));
  st = reader_tts_request_close(h, &err);
  reader_tts_observe(h, &snap, &err);
  report(s, "close_reports_closing_or_closed",
         st == READER_TTS_OK && (snap.state == READER_TTS_CLOSING || snap.state == READER_TTS_CLOSED),
         "status=%s state=%s", status_name(st), state_name(snap.state));
  st = reader_tts_request_close(h, &err);
  report(s, "close_idempotent", st == READER_TTS_OK, "status=%s", status_name(st));
  {
    reader_tts_state end = READER_TTS_INITIALIZING;
    int closed = wait_closed(h, 5000, &end);
    report(s, "close_reaches_closed", closed, "state=%s", state_name(end));
  }
  st = reader_tts_speak(h, ++id, "a", 1, NULL, 1.0, &err);
  report(s, "operations_after_closed_unavailable", st == READER_TTS_UNAVAILABLE, "status=%s",
         status_name(st));
  memset(&scratch, 0, sizeof scratch);
  st = reader_tts_voices(h, &scratch, &err);
  report(s, "voices_after_closed_unavailable",
         st == READER_TTS_UNAVAILABLE && scratch.voices == NULL && scratch.count == 0, "status=%s",
         status_name(st));
  st = reader_tts_observe(h, &snap, &err);
  report(s, "observe_after_closed_state", st == READER_TTS_OK && snap.state == READER_TTS_CLOSED,
         "state=%s", state_name(snap.state));
  {
    reader_tts_event ev;
    int av = 7;
    st = reader_tts_poll(h, &ev, &av, &err);
    report(s, "poll_after_closed_ok", st == READER_TTS_OK && av == 0, "status=%s available=%d",
           status_name(st), av);
  }
  st = reader_tts_destroy(&h, &err);
  report(s, "destroy_after_closed_nulls_pointer", st == READER_TTS_OK && h == NULL, "status=%s",
         status_name(st));
  st = reader_tts_destroy(&h, &err);
  report(s, "destroy_null_handle_rejected", st == READER_TTS_ARGUMENT, "status=%s",
         status_name(st));

  {
    size_t before = list.count;
    char keep[64] = {0};
    if (before && list.voices && list.voices[0].id) snprintf(keep, sizeof keep, "%s", list.voices[0].id);
    reader_tts_voice_list_free(&list);
    report(s, "voice_list_freed_after_destroy",
           before > 0 && list.voices == NULL && list.count == 0, "freed=%zu first=%s", before, keep);
  }

  /* a fresh handle after destroy, with a lowered input ceiling */
  memset(&cfg, 0, sizeof cfg);
  cfg.struct_size = sizeof cfg;
  cfg.max_utf8_bytes = 16;
  st = reader_tts_create(&cfg, &h3, &err);
  memset(&snap, 0, sizeof snap);
  if (h3) reader_tts_observe(h3, &snap, &err);
  report(s, "create_after_destroy_ready",
         st == READER_TTS_OK && h3 != NULL && snap.state == READER_TTS_READY, "status=%s state=%s",
         status_name(st), h3 ? state_name(snap.state) : "-");
  if (h3) {
    st = reader_tts_speak(h3, ++id, "abcdefghijklmnop", 16, NULL, 1.0, &err);
    report(s, "config_lowered_limit_accepts", st == READER_TTS_OK, "status=%s", status_name(st));
    reader_tts_stop(h3, id, &err);
    {
      reader_tts_event ev;
      int av = 0;
      while (reader_tts_poll(h3, &ev, &av, &err) == READER_TTS_OK && av) { /* drain */ }
    }
    st = reader_tts_speak(h3, ++id, "abcdefghijklmnopq", 17, NULL, 1.0, &err);
    report(s, "config_lowered_limit_rejects", st == READER_TTS_LIMIT, "status=%s", status_name(st));
    {
      reader_tts_config bad;
      reader_tts *hb = NULL;
      memset(&bad, 0, sizeof bad);
      bad.struct_size = 4;
      st = reader_tts_create(&bad, &hb, &err);
      report(s, "config_short_struct_rejected", st == READER_TTS_ARGUMENT && hb == NULL,
             "status=%s", status_name(st));
      bad.struct_size = sizeof bad;
      bad.max_utf8_bytes = READER_TTS_DEFAULT_MAX_UTF8 + 1;
      st = reader_tts_create(&bad, &hb, &err);
      report(s, "config_oversized_limit_rejected", st == READER_TTS_ARGUMENT && hb == NULL,
             "status=%s", status_name(st));
    }
    reader_tts_request_close(h3, &err);
    {
      reader_tts_state end = READER_TTS_INITIALIZING;
      int closed = wait_closed(h3, 5000, &end);
      report(s, "second_cycle_closed", closed, "state=%s", state_name(end));
    }
    st = reader_tts_destroy(&h3, &err);
    report(s, "second_cycle_destroyed", st == READER_TTS_OK && h3 == NULL, "status=%s",
           status_name(st));
  } else {
    report(s, "config_lowered_limit_accepts", 0, "handle missing");
    report(s, "config_lowered_limit_rejects", 0, "handle missing");
    report(s, "config_short_struct_rejected", 0, "handle missing");
    report(s, "config_oversized_limit_rejected", 0, "handle missing");
    report(s, "second_cycle_closed", 0, "handle missing");
    report(s, "second_cycle_destroyed", 0, "handle missing");
  }
}

/* ------------------------------------------------------------- down phase -- */
static void phase_down(suite *s) {
  reader_tts_error err;
  reader_tts *h = NULL;
  reader_tts_config cfg;
  reader_tts_snapshot snap;
  reader_tts_voice_list list;
  reader_tts_status st;
  reader_tts_state end = READER_TTS_INITIALIZING;
  int closed;
  memset(&err, 0, sizeof err);
  memset(&snap, 0, sizeof snap);
  memset(&cfg, 0, sizeof cfg);
  cfg.struct_size = sizeof cfg;
  st = reader_tts_create(&cfg, &h, &err);
  if (h) reader_tts_observe(h, &snap, &err);
  report(s, "create_without_daemon_ok",
         st == READER_TTS_OK && h != NULL && snap.state == READER_TTS_SERVICE_UNAVAILABLE &&
             snap.last_status == READER_TTS_UNAVAILABLE,
         "status=%s state=%s last=%s", status_name(st), state_name(snap.state),
         status_name(snap.last_status));
  if (!h) return;
  memset(&list, 0, sizeof list);
  st = reader_tts_voices(h, &list, &err);
  report(s, "voices_without_daemon_unavailable",
         st == READER_TTS_UNAVAILABLE && list.count == 0 && list.voices == NULL &&
             err.native_code != 0,
         "status=%s native=%d", status_name(st), err.native_code);
  st = reader_tts_speak(h, 1, "hello", 5, NULL, 1.0, &err);
  report(s, "speak_without_daemon_unavailable", st == READER_TTS_UNAVAILABLE, "status=%s native=%d",
         status_name(st), err.native_code);
  st = reader_tts_observe(h, &snap, &err);
  report(s, "observe_without_daemon_state",
         st == READER_TTS_OK && snap.state == READER_TTS_SERVICE_UNAVAILABLE &&
             snap.capabilities == READER_TTS_CAN_PAUSE,
         "state=%s caps=%u", state_name(snap.state), snap.capabilities);
  {
    int n = daemon_processes();
    report(s, "no_daemon_no_autospawn", n == 0, "daemons=%d", n);
  }
  st = reader_tts_request_close(h, &err);
  closed = wait_closed(h, 5000, &end);
  report(s, "down_close_clean", st == READER_TTS_OK && closed, "status=%s state=%s",
         status_name(st), state_name(end));
  st = reader_tts_destroy(&h, &err);
  report(s, "down_destroy_ok", st == READER_TTS_OK && h == NULL, "status=%s", status_name(st));
}

/* ---------------------------------------------------------- recover phase -- */
static void phase_recover(suite *s) {
  reader_tts_error err;
  reader_tts *h = NULL;
  reader_tts_config cfg;
  reader_tts_snapshot snap;
  reader_tts_status st;
  reader_tts_state end = READER_TTS_INITIALIZING;
  runstate rs;
  char text[64];
  int ok, closed;
  memset(&err, 0, sizeof err);
  memset(&snap, 0, sizeof snap);
  memset(&cfg, 0, sizeof cfg);
  cfg.struct_size = sizeof cfg;
  st = reader_tts_create(&cfg, &h, &err);
  if (h) reader_tts_observe(h, &snap, &err);
  report(s, "recover_create_ready",
         st == READER_TTS_OK && h != NULL && snap.state == READER_TTS_READY, "status=%s state=%s",
         status_name(st), h ? state_name(snap.state) : "-");
  if (!h) return;
  fill_ascii(text, 20, 'r');
  ok = run_request(h, 1, text, 20, NULL, 1.0, CASE_TIMEOUT_MS, &rs);
  report(s, "recover_speak_finished", ok && rs.c.finished == 1, "finished=%d status=%s",
         rs.c.finished, status_name(rs.term_status));
  st = reader_tts_request_close(h, &err);
  closed = wait_closed(h, 5000, &end);
  report(s, "recover_close_clean", st == READER_TTS_OK && closed, "state=%s", state_name(end));
  st = reader_tts_destroy(&h, &err);
  report(s, "recover_destroy_ok", st == READER_TTS_OK && h == NULL, "status=%s", status_name(st));
}

/* ------------------------------------------------------------- kill phase -- */
static void phase_kill(suite *s, int spd_pid, const char *restart_cmd) {
  reader_tts_error err;
  reader_tts *h = NULL;
  reader_tts_config cfg;
  reader_tts_snapshot snap;
  reader_tts_voice_list list;
  reader_tts_status st;
  reader_tts_state end = READER_TTS_INITIALIZING;
  runstate rs;
  char text[TEXT_CAP];
  uint64_t id = 77;
  int ok, closed;
  memset(&err, 0, sizeof err);
  memset(&snap, 0, sizeof snap);
  memset(&cfg, 0, sizeof cfg);
  cfg.struct_size = sizeof cfg;
  st = reader_tts_create(&cfg, &h, &err);
  report(s, "kill_create_ready", st == READER_TTS_OK && h != NULL, "status=%s", status_name(st));
  if (!h) return;
  fill_repeat(text, LONG_BYTES, "\xE6\x9C\x97\xE8\xAF\xBB\xE6\xB5\x8B\xE8\xAF\x95\xE3\x80\x82");
  rs_init(&rs);
  st = reader_tts_speak(h, id, text, LONG_BYTES, NULL, 0.5, &err);
  ok = (st == READER_TTS_OK) && await_started(h, id, CASE_TIMEOUT_MS, &rs);
  report(s, "kill_speaking_started", ok, "status=%s started=%d", status_name(st), rs.c.started);
  if (!ok) {
    reader_tts_request_close(h, &err);
    return;
  }
  if (spd_pid > 0 && kill(spd_pid, SIGKILL) == 0)
    report(s, "kill_daemon_signal_sent", 1, "SIGKILL sent to pid %d", spd_pid);
  else
    report(s, "kill_daemon_signal_sent", 0, "kill(%d) failed (errno=%d)", spd_pid, errno);
  ok = await_terminal(h, id, 10000, &rs);
  drain(h, id, &rs);
  report(s, "kill_daemon_failed_event", ok && rs.c.failed == 1 && rs.term_status == READER_TTS_UNAVAILABLE,
         "failed=%d stopped=%d finished=%d status=%s", rs.c.failed, rs.c.stopped, rs.c.finished,
         status_name(rs.term_status));
  st = reader_tts_observe(h, &snap, &err);
  report(s, "kill_daemon_state_unavailable",
         st == READER_TTS_OK && snap.state == READER_TTS_SERVICE_UNAVAILABLE, "state=%s last=%s",
         state_name(snap.state), status_name(snap.last_status));
  st = reader_tts_speak(h, ++id, "after", 5, NULL, 1.0, &err);
  report(s, "kill_daemon_speak_unavailable", st == READER_TTS_UNAVAILABLE, "status=%s",
         status_name(st));
  memset(&list, 0, sizeof list);
  st = reader_tts_voices(h, &list, &err);
  report(s, "kill_daemon_voices_unavailable",
         st == READER_TTS_UNAVAILABLE && list.voices == NULL && list.count == 0, "status=%s",
         status_name(st));
  {
    int n = daemon_processes();
    report(s, "kill_daemon_no_autospawn", n == 0, "daemons=%d", n);
  }
  if (restart_cmd && restart_cmd[0]) {
    int rc = system(restart_cmd);
    report(s, "kill_daemon_restart_command", rc == 0, "rc=%d", rc);
  } else {
    report(s, "kill_daemon_restart_command", 0, "no restart command supplied");
  }
  ok = run_request(h, ++id, "recovered", 9, NULL, 1.0, CASE_TIMEOUT_MS, &rs);
  report(s, "kill_daemon_same_handle_recovers", ok && rs.c.finished == 1, "finished=%d status=%s",
         rs.c.finished, status_name(rs.term_status));
  st = reader_tts_request_close(h, &err);
  closed = wait_closed(h, 10000, &end);
  report(s, "kill_daemon_close_clean", st == READER_TTS_OK && closed, "state=%s", state_name(end));
  st = reader_tts_destroy(&h, &err);
  report(s, "kill_daemon_destroy_ok", st == READER_TTS_OK && h == NULL, "status=%s",
         status_name(st));
}

int main(int argc, char **argv) {
  const char *phase = NULL;
  const char *out = NULL;
  const char *restart_cmd = NULL;
  int spd_pid = 0;
  int i;
  suite s;
  FILE *out_file;
  signal(SIGPIPE, SIG_IGN);
  for (i = 1; i < argc; ++i) {
    if (strcmp(argv[i], "--phase") == 0 && i + 1 < argc) phase = argv[++i];
    else if (strcmp(argv[i], "--output") == 0 && i + 1 < argc) out = argv[++i];
    else if (strcmp(argv[i], "--spd-pid") == 0 && i + 1 < argc) spd_pid = atoi(argv[++i]);
    else if (strcmp(argv[i], "--restart-cmd") == 0 && i + 1 < argc) restart_cmd = argv[++i];
  }
  if (!phase || !out) {
    fprintf(stderr,
            "usage: %s --phase live|kill|down|recover --output FILE [--spd-pid PID] "
            "[--restart-cmd CMD]\n",
            argv[0]);
    return 2;
  }
  out_file = fopen(out, "w");
  if (!out_file) {
    fprintf(stderr, "cannot write %s\n", out);
    return 2;
  }
  s.f = out_file;
  s.first = 1;
  s.fails = 0;
  rw_begin(out_file, argv[0], phase);
  if (strcmp(phase, "live") == 0) phase_live(&s);
  else if (strcmp(phase, "down") == 0) phase_down(&s);
  else if (strcmp(phase, "recover") == 0) phase_recover(&s);
  else if (strcmp(phase, "kill") == 0) phase_kill(&s, spd_pid, restart_cmd);
  else {
    fprintf(stderr, "unknown phase %s\n", phase);
    fclose(out_file);
    return 2;
  }
  rw_end(out_file, s.fails);
  fclose(out_file);
  fprintf(stdout, "phase %s finished with %d failing case(s)\n", phase, s.fails);
  fflush(stdout);
  return s.fails == 0 ? 0 : 1;
}
