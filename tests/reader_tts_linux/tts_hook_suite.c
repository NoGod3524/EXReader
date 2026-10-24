/* SPDX-License-Identifier: MIT */
/* Fault-injection suite for the J19 Linux reader TTS backend. Built from source
   with READER_TTS_BUILD_TEST_HOOKS=ON so callback buffering, late-callback
   filtering, the queue ceiling and allocation failures can be driven
   deterministically while the real daemon is connected.

   Cases that leave the daemon playing a message the library no longer tracks
   (synthetic END) settle before the next case asks the daemon for audio. */
#include "reader_tts.h"
#include "reader_tts_test.h"
#include "result_writer.h"
#include <signal.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

typedef struct {
  FILE *f;
  int first;
  int fails;
} suite;

static void sleep_ms(int ms) {
  struct timespec ts;
  ts.tv_sec = ms / 1000;
  ts.tv_nsec = (long)(ms % 1000) * 1000000L;
  nanosleep(&ts, NULL);
}
static void report(suite *s, const char *name, int ok, const char *fmt, ...) {
  char detail[512];
  va_list ap;
  va_start(ap, fmt);
  vsnprintf(detail, sizeof detail, fmt, ap);
  va_end(ap);
  rw_case(s->f, &s->first, name, ok, detail);
  if (!ok) ++s->fails;
  fprintf(stdout, "%s %s: %s\n", ok ? "pass" : "FAIL", name, detail);
  fflush(stdout);
}
/* Pops one event, waiting up to timeout_ms. 1 event, 0 none, -1 poll error. */
static int next_event(reader_tts *h, int timeout_ms, reader_tts_event *out) {
  int waited = 0, av = 0;
  reader_tts_error err;
  while (waited <= timeout_ms) {
    if (reader_tts_poll(h, out, &av, &err) != READER_TTS_OK) return -1;
    if (av) return 1;
    sleep_ms(5);
    waited += 5;
  }
  return 0;
}
static void drain_all(reader_tts *h) {
  reader_tts_event ev;
  reader_tts_error err;
  int av = 0;
  while (reader_tts_poll(h, &ev, &av, &err) == READER_TTS_OK && av) { /* discard */ }
}
static int state_of(reader_tts *h) {
  reader_tts_snapshot snap;
  reader_tts_error err;
  if (reader_tts_observe(h, &snap, &err) != READER_TTS_OK) return -1;
  return (int)snap.state;
}
/* Waits for the daemon to go quiet again after a state-diverging fault case. */
static void settle(reader_tts *h, int ms) {
  int waited = 0;
  while (waited < ms && state_of(h) != READER_TTS_READY) {
    sleep_ms(20);
    waited += 20;
  }
  sleep_ms(ms);
  drain_all(h);
}
/* Waits for STARTED and then a terminal event of this request. */
static int run_request(reader_tts *h, uint64_t id, const char *text, size_t n, double rate,
                       int timeout_ms, int *started, int *terminal) {
  reader_tts_error err;
  reader_tts_event ev;
  int got, waited = 0;
  *started = 0;
  *terminal = -1;
  if (reader_tts_speak(h, id, text, n, NULL, rate, &err) != READER_TTS_OK) return 0;
  while (waited < timeout_ms) {
    got = next_event(h, 50, &ev);
    if (got < 0) return 0;
    if (got == 1 && ev.request_id == id) {
      if (ev.kind == READER_TTS_STARTED) *started = 1;
      else if (ev.kind == READER_TTS_FINISHED || ev.kind == READER_TTS_STOPPED ||
               ev.kind == READER_TTS_FAILED) {
        *terminal = (int)ev.kind;
        return 1;
      }
    }
    waited += 50;
  }
  return 0;
}

int main(int argc, char **argv) {
  const char *phase = "hook";
  const char *out = NULL;
  int i;
  suite s;
  FILE *f;
  reader_tts_error err;
  reader_tts_config cfg;
  reader_tts *h = NULL;
  reader_tts_status st;
  reader_tts_event ev;
  char text[4096];
  int started, terminal, got, state_before;
  signal(SIGPIPE, SIG_IGN);
  for (i = 1; i < argc; ++i) {
    if (strcmp(argv[i], "--phase") == 0 && i + 1 < argc) phase = argv[++i];
    else if (strcmp(argv[i], "--output") == 0 && i + 1 < argc) out = argv[++i];
  }
  if (!out) {
    fprintf(stderr, "usage: %s --output FILE [--phase hook]\n", argv[0]);
    return 2;
  }
  f = fopen(out, "w");
  if (!f) return 2;
  s.f = f;
  s.first = 1;
  s.fails = 0;
  rw_begin(f, argv[0], phase);

  memset(&err, 0, sizeof err);
  memset(&cfg, 0, sizeof cfg);
  cfg.struct_size = sizeof cfg;

  reader_tts_test_fail_alloc(0);
  st = reader_tts_create(&cfg, &h, &err);
  report(&s, "hook_alloc_fail_create",
         st == READER_TTS_MEMORY && h == NULL && err.code == READER_TTS_MEMORY &&
             err.native_code != 0,
         "status=%d native=%d", (int)st, err.native_code);

  st = reader_tts_create(&cfg, &h, &err);
  report(&s, "hook_create_ready", st == READER_TTS_OK && h != NULL &&
                                      state_of(h) == READER_TTS_READY, "state=%d", state_of(h));
  if (!h) {
    rw_end(f, s.fails);
    fclose(f);
    return 1;
  }

  /* an early callback is buffered while the daemon id is still unknown */
  reader_tts_test_force_msg_id(4242);
  reader_tts_test_early_callback(0); /* begin */
  st = reader_tts_speak(h, 10, "early", 5, NULL, 1.0, &err);
  got = (st == READER_TTS_OK) ? next_event(h, 3000, &ev) : 0;
  report(&s, "hook_early_callback_buffered",
         got == 1 && ev.request_id == 10 && ev.kind == READER_TTS_STARTED && ev.has_range == 0,
         "status=%d id=%llu kind=%d", (int)st, (unsigned long long)ev.request_id, (int)ev.kind);
  /* the daemon's own callbacks carry its id, not the forced one */
  got = next_event(h, 700, &ev);
  report(&s, "hook_forced_id_filters_daemon_callbacks",
         got == 0 && state_of(h) == READER_TTS_SPEAKING, "extra_event=%d state=%d", got,
         state_of(h));
  st = reader_tts_stop(h, 10, &err);
  got = next_event(h, 3000, &ev);
  report(&s, "hook_stop_after_forced_id",
         st == READER_TTS_OK && got == 1 && ev.kind == READER_TTS_STOPPED && ev.request_id == 10,
         "status=%d kind=%d", (int)st, (int)ev.kind);
  got = next_event(h, 300, &ev);
  report(&s, "hook_single_terminal_event", got == 0, "extra_event=%d", got);

  /* an early terminal callback is replayed, so STARTED is not lost */
  reader_tts_test_force_msg_id(4243);
  reader_tts_test_early_callback(1); /* end */
  st = reader_tts_speak(h, 11, "early end", 9, NULL, 1.0, &err);
  {
    int first = (st == READER_TTS_OK) ? next_event(h, 3000, &ev) : 0;
    int first_kind = (int)ev.kind;
    int second = next_event(h, 3000, &ev);
    int second_kind = (int)ev.kind;
    report(&s, "hook_early_terminal_replay",
           first == 1 && first_kind == (int)READER_TTS_STARTED && second == 1 &&
               second_kind == (int)READER_TTS_FINISHED,
           "first=%d second=%d state=%d", first_kind, second_kind, state_of(h));
  }
  settle(h, 800);

  /* the daemon's real synthesis-voice list, measured before the ceiling is used */
  {
    size_t count = reader_tts_test_daemon_voice_count(h);
    report(&s, "hook_voice_count_measured",
           count != (size_t)-1 && count >= 1 && count <= READER_TTS_MAX_VOICES,
           "count=%zu ceiling=%u", count, (unsigned)READER_TTS_MAX_VOICES);
  }
  {
    reader_tts_voice_list list;
    memset(&list, 0, sizeof list);
    st = reader_tts_voices(h, &list, &err);
    report(&s, "hook_voices_listed", st == READER_TTS_OK && list.count >= 1, "status=%d count=%zu",
           (int)st, list.count);
    reader_tts_voice_list_free(&list);
  }

  /* a late callback of an older message must not touch the active request */
  memset(text, 'l', 2000);
  st = reader_tts_speak(h, 12, text, 2000, NULL, 0.5, &err);
  got = (st == READER_TTS_OK) ? next_event(h, 60000, &ev) : 0;
  state_before = state_of(h);
  report(&s, "hook_active_started",
         got == 1 && ev.request_id == 12 && ev.kind == READER_TTS_STARTED, "kind=%d state=%d",
         (int)ev.kind, state_before);
  {
    long real = reader_tts_test_msg_id(h);
    reader_tts_test_inject(h, real + 1000, 1); /* end of some other message */
    got = next_event(h, 500, &ev);
    report(&s, "hook_late_callback_ignored",
           real != 0 && got == 0 && state_of(h) == READER_TTS_SPEAKING,
           "msg=%ld extra_event=%d state=%d", real, got, state_of(h));
    reader_tts_test_inject(h, real, 1); /* the real id must still finish the request */
    got = next_event(h, 3000, &ev);
    report(&s, "hook_inject_real_id_finishes",
           got == 1 && ev.request_id == 12 && ev.kind == READER_TTS_FINISHED &&
               state_of(h) == READER_TTS_READY,
           "kind=%d state=%d", (int)ev.kind, state_of(h));
  }
  settle(h, 3000);

  /* queue ceiling */
  reader_tts_test_fill_queue(h, 200);
  report(&s, "hook_queue_capacity_bounded",
         reader_tts_test_queue_depth(h) == READER_TTS_EVENT_CAPACITY, "depth=%zu capacity=%u",
         reader_tts_test_queue_depth(h), (unsigned)READER_TTS_EVENT_CAPACITY);
  st = reader_tts_speak(h, 13, "a", 1, NULL, 1.0, &err);
  report(&s, "hook_queue_full_speak_limit", st == READER_TTS_LIMIT, "status=%d", (int)st);
  state_before = state_of(h);
  drain_all(h);
  report(&s, "hook_queue_full_state_unchanged", state_before == READER_TTS_READY, "state=%d",
         state_before);
  {
    int ok = run_request(h, 14, "drained", 7, 1.0, 120000, &started, &terminal);
    report(&s, "hook_queue_drained_speak_ok",
           ok && started == 1 && terminal == (int)READER_TTS_FINISHED, "started=%d terminal=%d",
           started, terminal);
  }

  /* allocation failures in speak and voices leave no state behind */
  reader_tts_test_fail_alloc(0);
  st = reader_tts_speak(h, 15, "alloc", 5, NULL, 1.0, &err);
  report(&s, "hook_alloc_fail_speak",
         st == READER_TTS_MEMORY && err.native_code != 0 && state_of(h) == READER_TTS_READY,
         "status=%d state=%d", (int)st, state_of(h));
  {
    int ok = run_request(h, 16, "after alloc", 11, 1.0, 120000, &started, &terminal);
    report(&s, "hook_speak_after_alloc_failure",
           ok && started == 1 && terminal == (int)READER_TTS_FINISHED, "started=%d terminal=%d",
           started, terminal);
  }
  {
    reader_tts_voice_list list;
    memset(&list, 0, sizeof list);
    reader_tts_test_fail_alloc(1); /* the array succeeds, the first string fails */
    st = reader_tts_voices(h, &list, &err);
    report(&s, "hook_alloc_fail_voices",
           st == READER_TTS_MEMORY && list.voices == NULL && list.count == 0 &&
               err.native_code != 0,
           "status=%d count=%zu", (int)st, list.count);
    st = reader_tts_voices(h, &list, &err);
    report(&s, "hook_voices_after_alloc_failure", st == READER_TTS_OK && list.count >= 1,
           "status=%d count=%zu", (int)st, list.count);
    reader_tts_voice_list_free(&list);
  }

  st = reader_tts_request_close(h, &err);
  {
    int closed = 0;
    for (i = 0; i < 1000 && !closed; ++i) {
      closed = state_of(h) == READER_TTS_CLOSED;
      if (!closed) sleep_ms(5);
    }
    report(&s, "hook_close_clean", st == READER_TTS_OK && closed, "status=%d closed=%d", (int)st,
           closed);
  }
  st = reader_tts_destroy(&h, &err);
  report(&s, "hook_destroy_ok", st == READER_TTS_OK && h == NULL, "status=%d", (int)st);

  rw_end(f, s.fails);
  fclose(f);
  fprintf(stdout, "phase %s finished with %d failing case(s)\n", phase, s.fails);
  fflush(stdout);
  return s.fails == 0 ? 0 : 1;
}
