/* SPDX-License-Identifier: MIT */
/* Fault-injection suite for the J19 Linux reader TTS backend. Built from source
   with READER_TTS_BUILD_TEST_HOOKS=ON so the callback-buffering, late-callback
   filtering, queue-ceiling and allocation-failure paths can be driven
   deterministically while the real daemon is connected. */
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
/* Pops one event, waiting up to timeout_ms. */
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
  char text[8192];
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

  /* allocation failures during create */
  reader_tts_test_fail_alloc(0);
  st = reader_tts_create(&cfg, &h, &err);
  report(&s, "hook_alloc_fail_create", st == READER_TTS_MEMORY && h == NULL &&
                                           err.code == READER_TTS_MEMORY && err.native_code != 0,
         "status=%s native=%d", st == READER_TTS_MEMORY ? "MEMORY" : "other", err.native_code);

  st = reader_tts_create(&cfg, &h, &err);
  report(&s, "hook_create_ready", st == READER_TTS_OK && h != NULL &&
                                      state_of(h) == READER_TTS_READY, "state=%d", state_of(h));
  if (!h) {
    rw_end(f, s.fails);
    fclose(f);
    return 1;
  }

  /* early callback buffered while the daemon id is still unknown */
  reader_tts_test_force_msg_id(4242);
  reader_tts_test_early_callback(0); /* begin */
  st = reader_tts_speak(h, 10, "early", 5, NULL, 1.0, &err);
  {
    int got = (st == READER_TTS_OK) ? next_event(h, 3000, &ev) : 0;
    report(&s, "hook_early_callback_buffered",
           got == 1 && ev.request_id == 10 && ev.kind == READER_TTS_STARTED && ev.has_range == 0,
           "status=%d id=%llu kind=%d", st, (unsigned long long)ev.request_id, (int)ev.kind);
    /* the daemon's own callbacks carry its id, not the forced one */
    got = next_event(h, 700, &ev);
    report(&s, "hook_forced_id_filters_daemon_callbacks",
           got == 0 && state_of(h) == READER_TTS_SPEAKING, "extra_event=%d state=%d", got,
           state_of(h));
  }
  st = reader_tts_stop(h, 10, &err);
  {
    int got = next_event(h, 3000, &ev);
    report(&s, "hook_stop_after_forced_id",
           st == READER_TTS_OK && got == 1 && ev.kind == READER_TTS_STOPPED && ev.request_id == 10,
           "status=%d kind=%d", st, (int)ev.kind);
    got = next_event(h, 300, &ev);
    report(&s, "hook_single_terminal_event", got == 0, "extra_event=%d", got);
  }

  /* an early terminal callback is replayed, so STARTED is not lost */
  reader_tts_test_force_msg_id(4243);
  reader_tts_test_early_callback(1); /* end */
  st = reader_tts_speak(h, 11, "early end", 9, NULL, 1.0, &err);
  {
    int a = (st == READER_TTS_OK) ? next_event(h, 3000, &ev) : 0;
    int kind_a = (int)ev.kind;
    int b = next_event(h, 3000, &ev);
    int kind_b = (int)ev.kind;
    report(&s, "hook_early_terminal_replay",
           a == 1 && kind_a == (int)READER_TTS_STARTED && b == 1 &&
               kind_b == (int)READER_TTS_FINISHED,
           "first=%d second=%d state=%d", kind_a, kind_b, state_of(h));
  }

  /* late callback of an older message must not touch the active request */
  memset(text, 'l', sizeof text);
  st = reader_tts_speak(h, 12, text, sizeof text, NULL, 0.5, &err);
  {
    long real = reader_tts_test_msg_id(h);
    reader_tts_test_inject(h, real + 1000, 1); /* end of some other message */
    int got = next_event(h, 500, &ev);
    report(&s, "hook_late_callback_ignored",
           st == READER_TTS_OK && real != 0 && got == 0 && state_of(h) == READER_TTS_SPEAKING,
           "msg=%ld extra_event=%d state=%d", real, got, state_of(h));
    reader_tts_test_inject(h, real, 1); /* the real id must still finish the request */
    got = next_event(h, 3000, &ev);
    report(&s, "hook_inject_real_id_finishes",
           got == 1 && ev.request_id == 12 && ev.kind == READER_TTS_FINISHED && state_of(h) ==
               READER_TTS_READY,
           "kind=%d state=%d", (int)ev.kind, state_of(h));
    drain_all(h);
  }

  /* queue ceiling */
  reader_tts_test_fill_queue(h, 200);
  report(&s, "hook_queue_capacity_bounded", reader_tts_test_queue_depth(h) == READER_TTS_EVENT_CAPACITY,
         "depth=%zu capacity=%u", reader_tts_test_queue_depth(h), (unsigned)READER_TTS_EVENT_CAPACITY);
  st = reader_tts_speak(h, 13, "a", 1, NULL, 1.0, &err);
  report(&s, "hook_queue_full_speak_limit", st == READER_TTS_LIMIT, "status=%d", (int)st);
  {
    int state = state_of(h);
    drain_all(h);
    report(&s, "hook_queue_full_state_unchanged", state == READER_TTS_READY, "state=%d", state);
  }
  {
    int started = 0, finished = 0;
    st = reader_tts_speak(h, 14, "drained", 7, NULL, 1.0, &err);
    if (st == READER_TTS_OK) {
      for (i = 0; i < 4000; ++i) {
        int got = next_event(h, 5, &ev);
        if (got == 1 && ev.request_id == 14) {
          if (ev.kind == READER_TTS_STARTED) ++started;
          if (ev.kind == READER_TTS_FINISHED) { ++finished; break; }
        } else if (got <= 0) {
          sleep_ms(5);
        }
      }
    }
    report(&s, "hook_queue_drained_speak_ok", st == READER_TTS_OK && started == 1 && finished == 1,
           "status=%d started=%d finished=%d", (int)st, started, finished);
  }

  /* allocation failures in speak and voices leave no state behind */
  reader_tts_test_fail_alloc(0);
  st = reader_tts_speak(h, 15, "alloc", 5, NULL, 1.0, &err);
  report(&s, "hook_alloc_fail_speak",
         st == READER_TTS_MEMORY && err.native_code != 0 && state_of(h) == READER_TTS_READY,
         "status=%d state=%d", (int)st, state_of(h));
  {
    int finished = 0, started = 0;
    st = reader_tts_speak(h, 16, "after alloc", 11, NULL, 1.0, &err);
    if (st == READER_TTS_OK) {
      for (i = 0; i < 4000; ++i) {
        int got = next_event(h, 5, &ev);
        if (got == 1 && ev.request_id == 16) {
          if (ev.kind == READER_TTS_STARTED) ++started;
          if (ev.kind == READER_TTS_FINISHED) { ++finished; break; }
        } else if (got <= 0) {
          sleep_ms(5);
        }
      }
    }
    report(&s, "hook_speak_after_alloc_failure", st == READER_TTS_OK && started == 1 &&
                                                     finished == 1,
           "status=%d started=%d finished=%d", (int)st, started, finished);
  }
  {
    reader_tts_voice_list list;
    memset(&list, 0, sizeof list);
    reader_tts_test_fail_alloc(1); /* array succeeds, the first string fails */
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
