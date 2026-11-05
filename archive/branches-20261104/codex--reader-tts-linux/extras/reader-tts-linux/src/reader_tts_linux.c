/* SPDX-License-Identifier: MIT */
/* Linux reader TTS backend: system Speech Dispatcher over libspeechd.
   No engine, no daemon, no process-global server: the library only opens the
   local SSIP socket, subscribes to begin/end/cancel, and keeps a bounded queue
   of value events for the owner thread. See include/reader_tts.h for the
   contract; every design decision below refers to it. */
#define _GNU_SOURCE
#include "reader_tts.h"
#include <libspeechd.h>
#include <errno.h>
#include <math.h>
#include <pthread.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <time.h>

#ifdef READER_TTS_TEST_HOOKS
#include "reader_tts_test.h"
#endif

/* Callbacks the daemon may deliver before spd_say() returned its message id. */
#define EARLY_MAX 8
/* Liveness probe period while a request is active. */
#define PROBE_ACTIVE_MS 500
/* connect_conn failure codes (native_code values reported to the host). */
#define CONNECT_NO_CONNECTION 1
#define CONNECT_NO_NOTIFY 2
#define CONNECT_SLOT_BUSY 3

typedef struct {
  long msg;
  int type;
} early_cb;

struct reader_tts {
  pthread_t owner;
  size_t max_bytes;
  pthread_mutex_t mu; /* guards every field below */
  reader_tts_state state;
  reader_tts_status last_status;
  uint64_t active_id;
  uint64_t last_id;
  int active;
  int started;
  int submitting;
  int want_stop; /* the host asked to stop; a pre-BEGIN cancel is then its stop */
  long msg_id;
  long forced_msg; /* test hook: message id to assume instead of the daemon's */
  early_cb early[EARLY_MAX];
  int early_n;
  reader_tts_event q[READER_TTS_EVENT_CAPACITY];
  size_t qh;
  size_t qn;
  uint64_t seen[READER_TTS_ID_MEMORY];
  size_t seen_n;
  size_t seen_next;
  SPDConnection *conn;
  int voice_custom; /* a voice was selected and must be dropped on reconnect */
  struct timespec last_probe;
  pthread_t closer;
  int closer_running;
};

/* libspeechd keeps process-global connection state and reports callbacks on its
   own thread without a handle argument, so the connection is owned by at most
   one handle and callbacks are routed through this single slot. Lock order is
   always g_mu -> handle mu. */
static pthread_mutex_t g_mu = PTHREAD_MUTEX_INITIALIZER;
static reader_tts *g_conn_owner;

#ifdef READER_TTS_TEST_HOOKS
static int g_alloc_budget = -1;
static long g_force_msg;
static int g_early_kind = -1;
/* Real interleaving point for the close handover: the closer blocks here, with the
   connection slot still held and the old event thread still alive, until the test
   opens the gate. */
static pthread_mutex_t g_gate_mu = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t g_gate_cv = PTHREAD_COND_INITIALIZER;
static int g_gate_armed;
static int g_gate_waiting;
static int g_gate_open;

static void hook_close_gate_wait(void) {
  pthread_mutex_lock(&g_gate_mu);
  if (!g_gate_armed) {
    pthread_mutex_unlock(&g_gate_mu);
    return;
  }
  g_gate_waiting = 1;
  pthread_cond_broadcast(&g_gate_cv);
  while (g_gate_armed && !g_gate_open) pthread_cond_wait(&g_gate_cv, &g_gate_mu);
  g_gate_waiting = 0;
  g_gate_armed = 0;
  g_gate_open = 0;
  pthread_mutex_unlock(&g_gate_mu);
}

static void *xcalloc(size_t n, size_t s) {
  if (g_alloc_budget == 0) {
    g_alloc_budget = -1;
    return NULL;
  }
  if (g_alloc_budget > 0) --g_alloc_budget;
  return calloc(n, s);
}
#else
static void *xcalloc(size_t n, size_t s) { return calloc(n, s); }
#endif

static void set_err(reader_tts_error *e, reader_tts_status c, int native) {
  if (e) {
    e->code = c;
    e->native_code = native;
  }
}
static reader_tts_status fail(reader_tts_error *e, reader_tts_status c, int native) {
  set_err(e, c, native);
  return c;
}
static reader_tts_status succeed(reader_tts_error *e) { return fail(e, READER_TTS_OK, 0); }

static void sleep_ms(int ms) {
  struct timespec ts;
  ts.tv_sec = ms / 1000;
  ts.tv_nsec = (long)(ms % 1000) * 1000000L;
  nanosleep(&ts, NULL);
}
static int closing_locked(const reader_tts *h) {
  return h->state == READER_TTS_CLOSING || h->state == READER_TTS_CLOSED;
}
static long elapsed_ms(const struct timespec *since, const struct timespec *now) {
  return (long)((now->tv_sec - since->tv_sec) * 1000L + (now->tv_nsec - since->tv_nsec) / 1000000L);
}

static void push_locked(reader_tts *h, uint64_t id, reader_tts_event_kind kind,
                        reader_tts_status st) {
  reader_tts_event *e;
  if (h->qn >= READER_TTS_EVENT_CAPACITY) {
    /* Cannot happen for library-generated events (speak reserves room), but a
       daemon flooding callbacks must not corrupt or grow the queue. */
    h->last_status = READER_TTS_LIMIT;
    return;
  }
  e = &h->q[(h->qh + h->qn) % READER_TTS_EVENT_CAPACITY];
  ++h->qn;
  memset(e, 0, sizeof *e);
  e->request_id = id;
  e->kind = kind;
  e->status = st;
  e->start = 0;
  e->end = 0;
  e->has_range = 0;
}
static void finish_locked(reader_tts *h) {
  h->active = 0;
  h->started = 0;
  h->want_stop = 0;
  if (h->state == READER_TTS_SPEAKING || h->state == READER_TTS_PAUSED ||
      h->state == READER_TTS_STOPPING)
    h->state = READER_TTS_READY;
}
static void apply_locked(reader_tts *h, int type) {
  switch (type) {
  case SPD_EVENT_BEGIN:
    if (!h->started) {
      push_locked(h, h->active_id, READER_TTS_STARTED, READER_TTS_OK);
      h->started = 1;
    }
    break;
  case SPD_EVENT_END:
  case SPD_EVENT_CANCEL:
    /* Three different facts share these two callbacks:
       - the host asked to stop: the terminal event is STOPPED, whether the daemon
         reports the message as ended (espeak-ng does) or as cancelled;
       - the daemon ended the message it had begun: FINISHED;
       - the daemon cancelled a message that never began: the platform refused it,
         so FAILED/IO, because nobody asked to stop it. */
    if (h->want_stop) {
      push_locked(h, h->active_id, READER_TTS_STOPPED, READER_TTS_OK);
    } else if (type == SPD_EVENT_END) {
      if (!h->started) {
        push_locked(h, h->active_id, READER_TTS_STARTED, READER_TTS_OK);
        h->started = 1;
      }
      push_locked(h, h->active_id, READER_TTS_FINISHED, READER_TTS_OK);
    } else if (h->started) {
      push_locked(h, h->active_id, READER_TTS_STOPPED, READER_TTS_OK);
    } else {
      push_locked(h, h->active_id, READER_TTS_FAILED, READER_TTS_IO);
    }
    finish_locked(h);
    break;
  default:
    break;
  }
}

/* One daemon callback. Runs on libspeechd's event thread: it only touches the
   handle under g_mu and the handle mutex, and never calls the host. */
static void record_event(reader_tts *h, long msg, int type) {
  pthread_mutex_lock(&h->mu);
  if (h->active) {
    if (h->submitting && h->msg_id == 0) {
      /* Keep the newest callbacks: the terminal one matters most. */
      if (h->early_n < EARLY_MAX) {
        h->early[h->early_n].msg = msg;
        h->early[h->early_n].type = type;
        ++h->early_n;
      } else {
        memmove(&h->early[0], &h->early[1], sizeof h->early[0] * (EARLY_MAX - 1));
        h->early[EARLY_MAX - 1].msg = msg;
        h->early[EARLY_MAX - 1].type = type;
      }
    } else if (msg == h->msg_id) {
      apply_locked(h, type);
    } /* else: late callback of an earlier message, ignored by design */
  }
  pthread_mutex_unlock(&h->mu);
}
static void spd_event_cb(size_t msg, size_t client, SPDNotificationType state) {
  reader_tts *h;
  (void)client;
  pthread_mutex_lock(&g_mu);
  h = g_conn_owner;
  if (h) record_event(h, (long)msg, (int)state);
  pthread_mutex_unlock(&g_mu);
}

static int slot_acquire(reader_tts *h) {
  int ok;
  pthread_mutex_lock(&g_mu);
  ok = (g_conn_owner == NULL || g_conn_owner == h);
  if (ok) g_conn_owner = h;
  pthread_mutex_unlock(&g_mu);
  return ok;
}
static void slot_release(reader_tts *h) {
  pthread_mutex_lock(&g_mu);
  if (g_conn_owner == h) g_conn_owner = NULL;
  pthread_mutex_unlock(&g_mu);
}

/* A dead daemon closes the SSIP socket. A non-destructive peek is the only
   liveness check that cannot disturb what is being spoken: any SSIP command
   (a setting, a list, a cancel) either changes state or blocks forever on a
   daemon that is already gone. Pending data is left in the queue for
   libspeechd's own thread. */
static int conn_alive(SPDConnection *c) {
  char byte;
  ssize_t n;
  if (!c || c->socket < 0) return 0;
  do {
    n = recv(c->socket, &byte, 1, MSG_PEEK | MSG_DONTWAIT);
  } while (n < 0 && errno == EINTR);
  if (n == 0) return 0; /* orderly shutdown: the daemon is gone */
  if (n > 0) return 1;  /* data waiting, not consumed */
  return (errno == EAGAIN || errno == EWOULDBLOCK) ? 1 : 0;
}

static SPDConnection *conn_of(reader_tts *h) {
  SPDConnection *c;
  pthread_mutex_lock(&h->mu);
  c = h->conn;
  pthread_mutex_unlock(&h->mu);
  return c;
}

/* Releases the connection. Callers must have cleared any active request first so
   that stragglers are dropped.

   The process-wide callback slot is kept until spd_close() has joined
   libspeechd's event thread. Releasing it earlier would let another handle take
   the slot and open a second connection while the old event thread is still
   alive: the shared callback would route that thread's events to the new owner,
   and the module's "one connection per process" rule would be broken. No lock
   the callbacks need (g_mu or the handle mutex) is held across spd_close. */
static void drop_conn(reader_tts *h) {
  SPDConnection *c;
  pthread_mutex_lock(&h->mu);
  c = h->conn;
  h->conn = NULL;
  h->voice_custom = 0;
  pthread_mutex_unlock(&h->mu);
#ifdef READER_TTS_TEST_HOOKS
  /* Test-only interleaving point: the slot is still owned here and the old event
     thread is still alive. No lock is held while waiting. */
  hook_close_gate_wait();
#endif
  if (c) spd_close(c); /* joins libspeechd's event thread */
  slot_release(h);     /* only now may another handle take the connection */
}

/* The daemon is gone or refused to talk: end the active request explicitly and
   enter SERVICE_UNAVAILABLE. */
static void go_unavailable(reader_tts *h, int native) {
  pthread_mutex_lock(&h->mu);
  if (h->active) {
    push_locked(h, h->active_id, READER_TTS_FAILED, READER_TTS_UNAVAILABLE);
    h->active = 0;
    h->started = 0;
  }
  if (!closing_locked(h)) h->state = READER_TTS_SERVICE_UNAVAILABLE;
  h->last_status = READER_TTS_UNAVAILABLE;
  pthread_mutex_unlock(&h->mu);
  (void)native;
  drop_conn(h);
}

/* Opens the local socket without spawning a daemon. */
static int connect_conn(reader_tts *h) {
  SPDConnection *c;
  char *err = NULL;
  if (!slot_acquire(h)) return CONNECT_SLOT_BUSY;
  /* address NULL: libspeechd's default address (the local UNIX socket); the
     autospawn argument is 0 so a missing daemon is never started here. */
  c = spd_open2("exreader-reader-tts", "reader", NULL, SPD_MODE_THREADED, NULL, 0, &err);
  free(err);
  if (!c) {
    slot_release(h);
    return CONNECT_NO_CONNECTION;
  }
  c->callback_begin = spd_event_cb;
  c->callback_end = spd_event_cb;
  c->callback_cancel = spd_event_cb;
  if (spd_set_notification_on(c, SPD_BEGIN) != 0 ||
      spd_set_notification_on(c, SPD_END) != 0 ||
      spd_set_notification_on(c, SPD_CANCEL) != 0) {
    spd_close(c);
    slot_release(h);
    return CONNECT_NO_NOTIFY;
  }
  pthread_mutex_lock(&h->mu);
  h->conn = c;
  h->voice_custom = 0;
  clock_gettime(CLOCK_MONOTONIC, &h->last_probe);
  pthread_mutex_unlock(&h->mu);
  return 0;
}

/* 1 when a usable connection exists afterwards, 0 with the error filled. A dead
   connection (write refused) is dropped and one reconnect is attempted. */
static int ensure_live(reader_tts *h, reader_tts_error *e) {
  SPDConnection *c = conn_of(h);
  int r;
  if (c) {
    if (conn_alive(c)) return 1;
    go_unavailable(h, -1);
  }
  r = connect_conn(h);
  pthread_mutex_lock(&h->mu);
  if (r == 0) {
    if (!closing_locked(h)) {
      if (h->state == READER_TTS_SERVICE_UNAVAILABLE || h->state == READER_TTS_INITIALIZING)
        h->state = READER_TTS_READY;
      h->last_status = READER_TTS_OK;
    }
  } else {
    if (!closing_locked(h)) h->state = READER_TTS_SERVICE_UNAVAILABLE;
    h->last_status = READER_TTS_UNAVAILABLE;
  }
  pthread_mutex_unlock(&h->mu);
  if (r) {
    set_err(e, READER_TTS_UNAVAILABLE, r);
    return 0;
  }
  return 1;
}

/* While a request is active the daemon must keep answering; if it does not, the
   request can never end and the host must learn it. */
static void housekeeping(reader_tts *h) {
  struct timespec now;
  SPDConnection *c;
  int active;
  pthread_mutex_lock(&h->mu);
  active = h->active;
  c = h->conn;
  clock_gettime(CLOCK_MONOTONIC, &now);
  if (!active || !c || elapsed_ms(&h->last_probe, &now) < PROBE_ACTIVE_MS) {
    pthread_mutex_unlock(&h->mu);
    return;
  }
  h->last_probe = now;
  pthread_mutex_unlock(&h->mu);
  if (!conn_alive(c)) go_unavailable(h, -1);
}

static int is_owner(const reader_tts *h) { return pthread_equal(h->owner, pthread_self()); }

static reader_tts_status entry(reader_tts *h, reader_tts_error *e) {
  if (!h) return fail(e, READER_TTS_ARGUMENT, 0);
  if (!is_owner(h)) return fail(e, READER_TTS_OWNER, 0);
  return READER_TTS_OK;
}

/* Strict UTF-8: no NUL, no overlong form, no surrogate, no truncated scalar. */
static int utf8_ok(const unsigned char *s, size_t n) {
  size_t i = 0, k, len;
  uint32_t cp;
  while (i < n) {
    unsigned c = s[i];
    if (c == 0) return 0;
    if (c < 0x80) {
      ++i;
      continue;
    }
    if (c >= 0xC2 && c <= 0xDF) {
      len = 2;
      cp = c & 0x1F;
    } else if ((c & 0xF0) == 0xE0) {
      len = 3;
      cp = c & 0x0F;
    } else if (c >= 0xF0 && c <= 0xF4) {
      len = 4;
      cp = c & 0x07;
    } else {
      return 0;
    }
    if (n - i < len) return 0;
    for (k = 1; k < len; ++k) {
      if ((s[i + k] & 0xC0) != 0x80) return 0;
      cp = (cp << 6) | (s[i + k] & 0x3F);
    }
    if (len == 3 && (cp < 0x800 || (cp >= 0xD800 && cp <= 0xDFFF))) return 0;
    if (len == 4 && (cp < 0x10000 || cp > 0x10FFFF)) return 0;
    i += len;
  }
  return 1;
}

/* Relative rate 0.5..2.0 -> Speech Dispatcher's percentage offset.
   Speech Dispatcher's rate is "percent slower/faster than the module default":
   0 leaves it unchanged and +100 asks for twice the speed, so a relative rate r
   maps to round(100 * (r - 1)): 0.5 -> -50, 1.0 -> 0, 2.0 -> +100.
   -100 is never sent: it asks the module for zero speed, and the daemon then
   cancels the message before it starts (measured on speech-dispatcher 0.11.1
   with espeak-ng: SPEAK at -100 produced an immediate CANCEL, no BEGIN). */
static int map_rate(double r) {
  double v = (r - 1.0) * 100.0;
  if (v > 100.0) v = 100.0;
  if (v < -99.0) v = -99.0;
  return (int)(v < 0 ? v - 0.5 : v + 0.5);
}

/* free_spd_voices appeared after 0.8; use it when this libspeechd has it. */
extern void free_spd_voices(SPDVoice **voices) __attribute__((weak));
static void voices_free(SPDVoice **v) {
  size_t i;
  if (!v) return;
  if (free_spd_voices) {
    free_spd_voices(v);
    return;
  }
  for (i = 0; v[i]; ++i) {
    free(v[i]->name);
    free(v[i]->language);
    free(v[i]->variant);
    free(v[i]);
  }
  free(v);
}
static SPDVoice **list_voices(reader_tts *h) {
  SPDConnection *c = conn_of(h);
  if (!c) return NULL;
  return spd_list_synthesis_voices(c);
}
/* 1 known, 0 unknown (with *dead set when the daemon is gone). */
static int voice_known(reader_tts *h, const char *id, int *dead) {
  SPDVoice **v;
  size_t i;
  int found = 0;
  *dead = 0;
  v = list_voices(h);
  if (!v) {
    *dead = 1;
    go_unavailable(h, -1);
    return 0;
  }
  for (i = 0; v[i]; ++i)
    if (v[i]->name && strcmp(v[i]->name, id) == 0) {
      found = 1;
      break;
    }
  voices_free(v);
  return found;
}

reader_tts_status reader_tts_create(const reader_tts_config *cfg, reader_tts **out,
                                    reader_tts_error *e) {
  reader_tts *h;
  size_t max = READER_TTS_DEFAULT_MAX_UTF8;
  int r;
  if (!out) return fail(e, READER_TTS_ARGUMENT, 0);
  *out = NULL;
  if (cfg) {
    if (cfg->struct_size < sizeof *cfg) return fail(e, READER_TTS_ARGUMENT, 0);
    if (cfg->max_utf8_bytes > READER_TTS_DEFAULT_MAX_UTF8) return fail(e, READER_TTS_ARGUMENT, 0);
    if (cfg->max_utf8_bytes) max = cfg->max_utf8_bytes;
  }
  h = (reader_tts *)xcalloc(1, sizeof *h);
  if (!h) return fail(e, READER_TTS_MEMORY, ENOMEM);
  if (pthread_mutex_init(&h->mu, NULL) != 0) {
    free(h);
    return fail(e, READER_TTS_MEMORY, ENOMEM);
  }
  h->owner = pthread_self();
  h->max_bytes = max;
  h->state = READER_TTS_INITIALIZING;
  r = connect_conn(h);
  if (r == 0) {
    h->state = READER_TTS_READY;
    h->last_status = READER_TTS_OK;
  } else {
    h->state = READER_TTS_SERVICE_UNAVAILABLE;
    h->last_status = READER_TTS_UNAVAILABLE;
  }
  *out = h;
  return succeed(e);
}

reader_tts_status reader_tts_voices(reader_tts *h, reader_tts_voice_list *out,
                                    reader_tts_error *e) {
  reader_tts_status s = entry(h, e);
  SPDVoice **v;
  size_t n = 0, i, k = 0;
  int closed;
  if (s) return s;
  if (!out) return fail(e, READER_TTS_ARGUMENT, 0);
  out->voices = NULL;
  out->count = 0;
  pthread_mutex_lock(&h->mu);
  closed = closing_locked(h);
  pthread_mutex_unlock(&h->mu);
  if (closed) return fail(e, READER_TTS_UNAVAILABLE, 0);
  if (!ensure_live(h, e)) return READER_TTS_UNAVAILABLE;
  v = list_voices(h);
  if (!v) {
    int native = 0;
    go_unavailable(h, native);
    set_err(e, READER_TTS_UNAVAILABLE, native);
    return READER_TTS_UNAVAILABLE;
  }
  while (v[n]) {
    if (n >= READER_TTS_MAX_VOICES) {
      voices_free(v);
      return fail(e, READER_TTS_LIMIT, 0);
    }
    ++n;
  }
  if (n) {
    out->voices = (reader_tts_voice *)xcalloc(n, sizeof *out->voices);
    if (!out->voices) {
      voices_free(v);
      return fail(e, READER_TTS_MEMORY, ENOMEM);
    }
  }
  for (i = 0; i < n; ++i) {
    const char *nm = v[i]->name ? v[i]->name : "";
    const char *lg = v[i]->language ? v[i]->language : "";
    size_t nl = strnlen(nm, READER_TTS_MAX_VOICE_FIELD);
    size_t ll = strnlen(lg, READER_TTS_MAX_VOICE_FIELD);
    reader_tts_voice *d;
    if (!nl) continue; /* a voice without a name cannot be selected */
    out->count = k + 1;
    if (nl >= READER_TTS_MAX_VOICE_FIELD || ll >= READER_TTS_MAX_VOICE_FIELD) {
      reader_tts_voice_list_free(out);
      voices_free(v);
      return fail(e, READER_TTS_LIMIT, 0);
    }
    d = &out->voices[k];
    d->id = (char *)xcalloc(nl + 1, 1);
    d->name = (char *)xcalloc(nl + 1, 1);
    d->language = (char *)xcalloc(ll + 1, 1);
    if (!d->id || !d->name || !d->language) {
      reader_tts_voice_list_free(out);
      voices_free(v);
      return fail(e, READER_TTS_MEMORY, ENOMEM);
    }
    memcpy(d->id, nm, nl);
    memcpy(d->name, nm, nl);
    memcpy(d->language, lg, ll);
    ++k;
  }
  out->count = k;
  voices_free(v);
  return succeed(e);
}

void reader_tts_voice_list_free(reader_tts_voice_list *l) {
  size_t i;
  if (!l) return;
  for (i = 0; l->voices && i < l->count; ++i) {
    free(l->voices[i].id);
    free(l->voices[i].name);
    free(l->voices[i].language);
  }
  free(l->voices);
  l->voices = NULL;
  l->count = 0;
}

reader_tts_status reader_tts_speak(reader_tts *h, uint64_t id, const char *text, size_t bytes,
                                   const char *voice, double rate, reader_tts_error *e) {
  reader_tts_status s = entry(h, e);
  char *copy;
  SPDConnection *c;
  long msg;
  int i, dead = 0, mapped;
  if (s) return s;
  if (!id) return fail(e, READER_TTS_ARGUMENT, 0);
  if (!text || bytes == 0) return fail(e, READER_TTS_ARGUMENT, 0);
  if (bytes > h->max_bytes) return fail(e, READER_TTS_LIMIT, 0);
  if (!utf8_ok((const unsigned char *)text, bytes)) return fail(e, READER_TTS_ARGUMENT, 0);
  if (voice && strnlen(voice, READER_TTS_MAX_VOICE_FIELD) >= READER_TTS_MAX_VOICE_FIELD)
    return fail(e, READER_TTS_ARGUMENT, 0);
  if (!isfinite(rate) || rate < 0.5 || rate > 2.0) return fail(e, READER_TTS_ARGUMENT, 0);
  mapped = map_rate(rate);
  pthread_mutex_lock(&h->mu);
  if (closing_locked(h)) {
    pthread_mutex_unlock(&h->mu);
    return fail(e, READER_TTS_UNAVAILABLE, 0);
  }
  if (h->active) {
    pthread_mutex_unlock(&h->mu);
    return fail(e, READER_TTS_BUSY, 0);
  }
  for (i = 0; i < (int)h->seen_n; ++i)
    if (h->seen[i] == id) {
      pthread_mutex_unlock(&h->mu);
      return fail(e, READER_TTS_ARGUMENT, 0);
    }
  if (h->qn + 2 > READER_TTS_EVENT_CAPACITY) {
    pthread_mutex_unlock(&h->mu);
    return fail(e, READER_TTS_LIMIT, 0);
  }
  pthread_mutex_unlock(&h->mu);
  copy = (char *)xcalloc(bytes + 1, 1);
  if (!copy) return fail(e, READER_TTS_MEMORY, ENOMEM);
  memcpy(copy, text, bytes);
  if (!ensure_live(h, e)) {
    free(copy);
    return READER_TTS_UNAVAILABLE;
  }
  if (voice && voice[0]) {
    if (voice_known(h, voice, &dead) != 1) {
      free(copy);
      return dead ? fail(e, READER_TTS_UNAVAILABLE, 0) : fail(e, READER_TTS_ARGUMENT, 0);
    }
    c = conn_of(h);
    if (!c || spd_set_synthesis_voice(c, voice) != 0) {
      free(copy);
      if (!c) return fail(e, READER_TTS_UNAVAILABLE, 0);
      if (conn_alive(c)) return fail(e, READER_TTS_IO, 0);
      go_unavailable(h, -1);
      return fail(e, READER_TTS_UNAVAILABLE, 0);
    }
    pthread_mutex_lock(&h->mu);
    h->voice_custom = 1;
    pthread_mutex_unlock(&h->mu);
  } else {
    int custom;
    pthread_mutex_lock(&h->mu);
    custom = h->voice_custom;
    pthread_mutex_unlock(&h->mu);
    if (custom) {
      /* libspeechd has no "restore the daemon default" call: reconnect. */
      drop_conn(h);
      if (!ensure_live(h, e)) {
        free(copy);
        return READER_TTS_UNAVAILABLE;
      }
    }
  }
  c = conn_of(h);
  if (!c) {
    free(copy);
    return fail(e, READER_TTS_UNAVAILABLE, 0);
  }
  if (spd_set_voice_rate(c, mapped) != 0) {
    free(copy);
    go_unavailable(h, -1);
    return fail(e, READER_TTS_UNAVAILABLE, 0);
  }
  pthread_mutex_lock(&h->mu);
  h->active = 1;
  h->active_id = id;
  h->last_id = id;
  h->started = 0;
  h->submitting = 1;
  h->msg_id = 0;
  h->early_n = 0;
  h->state = READER_TTS_SPEAKING;
  h->last_status = READER_TTS_OK;
  if (h->seen_n < READER_TTS_ID_MEMORY) {
    h->seen[h->seen_n++] = id;
  } else {
    h->seen[h->seen_next++] = id;
    if (h->seen_next >= READER_TTS_ID_MEMORY) h->seen_next = 0;
  }
#ifdef READER_TTS_TEST_HOOKS
  h->forced_msg = g_force_msg;
  g_force_msg = 0;
#else
  h->forced_msg = 0;
#endif
  pthread_mutex_unlock(&h->mu);
#ifdef READER_TTS_TEST_HOOKS
  if (g_early_kind >= 0) {
    long synthetic;
    int kind = g_early_kind;
    g_early_kind = -1;
    pthread_mutex_lock(&h->mu);
    synthetic = h->forced_msg;
    pthread_mutex_unlock(&h->mu);
    /* Simulates a callback racing in before the message id is known: msg_id is
       still 0 here, so it must land in the buffer and be replayed below. */
    if (synthetic) record_event(h, synthetic, kind);
  }
#endif
  msg = spd_say(c, SPD_TEXT, copy);
  free(copy);
  pthread_mutex_lock(&h->mu);
  h->submitting = 0;
  if (msg <= 0) {
    h->active = 0;
    h->started = 0;
    if (!closing_locked(h)) h->state = READER_TTS_READY;
    pthread_mutex_unlock(&h->mu);
    go_unavailable(h, (int)msg);
    return fail(e, READER_TTS_UNAVAILABLE, (int)msg);
  }
  if (h->msg_id == 0) h->msg_id = h->forced_msg ? h->forced_msg : msg;
  for (i = 0; i < h->early_n; ++i)
    if (h->early[i].msg == h->msg_id) apply_locked(h, h->early[i].type);
  h->early_n = 0;
  pthread_mutex_unlock(&h->mu);
  return succeed(e);
}

/* Pause/resume gate: validates the request, reports no-ops, refuses while the
   request is being cancelled. */
static reader_tts_status gate(reader_tts *h, uint64_t id, int want_pause, int *noop,
                              reader_tts_error *e) {
  reader_tts_status s = entry(h, e);
  *noop = 0;
  if (s) return s;
  if (!id) return fail(e, READER_TTS_ARGUMENT, 0);
  pthread_mutex_lock(&h->mu);
  if (closing_locked(h)) {
    pthread_mutex_unlock(&h->mu);
    return fail(e, READER_TTS_UNAVAILABLE, 0);
  }
  if (!h->active || h->active_id != id) {
    pthread_mutex_unlock(&h->mu);
    return fail(e, READER_TTS_ARGUMENT, 0);
  }
  if (h->state == READER_TTS_STOPPING) {
    pthread_mutex_unlock(&h->mu);
    return fail(e, READER_TTS_BUSY, 0);
  }
  if ((want_pause && h->state == READER_TTS_PAUSED) ||
      (!want_pause && h->state == READER_TTS_SPEAKING))
    *noop = 1;
  pthread_mutex_unlock(&h->mu);
  return READER_TTS_OK;
}
reader_tts_status reader_tts_pause(reader_tts *h, uint64_t id, reader_tts_error *e) {
  int noop;
  reader_tts_status s = gate(h, id, 1, &noop, e);
  SPDConnection *c;
  if (s) return s;
  if (noop) return succeed(e);
  c = conn_of(h);
  if (!c) return fail(e, READER_TTS_UNAVAILABLE, 0);
  if (spd_pause(c) != 0) {
    if (conn_alive(c)) return fail(e, READER_TTS_UNSUPPORTED, 0);
    go_unavailable(h, -1);
    return fail(e, READER_TTS_UNAVAILABLE, 0);
  }
  pthread_mutex_lock(&h->mu);
  if (h->active && h->state == READER_TTS_SPEAKING) h->state = READER_TTS_PAUSED;
  pthread_mutex_unlock(&h->mu);
  return succeed(e);
}
reader_tts_status reader_tts_resume(reader_tts *h, uint64_t id, reader_tts_error *e) {
  int noop;
  reader_tts_status s = gate(h, id, 0, &noop, e);
  SPDConnection *c;
  if (s) return s;
  if (noop) return succeed(e);
  c = conn_of(h);
  if (!c) return fail(e, READER_TTS_UNAVAILABLE, 0);
  if (spd_resume(c) != 0) {
    if (conn_alive(c)) return fail(e, READER_TTS_UNSUPPORTED, 0);
    go_unavailable(h, -1);
    return fail(e, READER_TTS_UNAVAILABLE, 0);
  }
  pthread_mutex_lock(&h->mu);
  if (h->active && h->state == READER_TTS_PAUSED) h->state = READER_TTS_SPEAKING;
  pthread_mutex_unlock(&h->mu);
  return succeed(e);
}

reader_tts_status reader_tts_stop(reader_tts *h, uint64_t id, reader_tts_error *e) {
  reader_tts_status s = entry(h, e);
  SPDConnection *c;
  int was_paused, r, i;
  if (s) return s;
  if (!id) return fail(e, READER_TTS_ARGUMENT, 0);
  pthread_mutex_lock(&h->mu);
  if (closing_locked(h)) {
    pthread_mutex_unlock(&h->mu);
    return fail(e, READER_TTS_UNAVAILABLE, 0);
  }
  if (!h->active) {
    s = (id == h->last_id) ? READER_TTS_OK : READER_TTS_ARGUMENT;
    pthread_mutex_unlock(&h->mu);
    return fail(e, s, 0);
  }
  if (h->active_id != id) {
    pthread_mutex_unlock(&h->mu);
    return fail(e, READER_TTS_ARGUMENT, 0);
  }
  was_paused = h->state == READER_TTS_PAUSED;
  h->state = READER_TTS_STOPPING;
  h->want_stop = 1;
  pthread_mutex_unlock(&h->mu);
  c = conn_of(h);
  if (!c) {
    go_unavailable(h, -1);
    return fail(e, READER_TTS_UNAVAILABLE, 0);
  }
  /* CANCEL only drops what is still queued; STOP interrupts the message being
     spoken. On speech-dispatcher 0.11.1 a CANCEL alone leaves the espeak-ng
     module synthesising the long message it was asked to abandon, and every
     later message of that client waits behind it forever (measured: the next two
     requests produced no event at all for 60 s each, and a fresh daemon fixed
     it). Both are issued. */
  if (was_paused) spd_resume(c); /* pause is per client: leave it clean */
  {
    int r_cancel = spd_cancel(c);
    int r_stop = spd_stop(c);
    r = (r_cancel == 0 || r_stop == 0) ? 0 : (r_cancel != 0 ? r_cancel : r_stop);
  }
  if (r != 0) {
    if (conn_alive(c)) {
      /* daemon alive, cancel refused */
      pthread_mutex_lock(&h->mu);
      h->want_stop = 0;
      if (h->active && h->state == READER_TTS_STOPPING)
        h->state = was_paused ? READER_TTS_PAUSED : READER_TTS_SPEAKING;
      pthread_mutex_unlock(&h->mu);
      return fail(e, READER_TTS_IO, r);
    }
    go_unavailable(h, r);
    return fail(e, READER_TTS_UNAVAILABLE, r);
  }
  /* Wait (bounded) for the daemon's own cancel notification. The espeak-ng module
     keeps tearing the message down after SPEAK is cancelled, and a message
     submitted inside that window is cancelled by the daemon before it begins
     (measured: a 0.5-rate SPEAK issued ~200 ms after a cancel came back as an
     immediate CANCEL). Waiting for the notification makes "stop, then speak the
     next paragraph" deterministic; the cap keeps stop bounded when no
     notification arrives. */
  for (i = 0; i < 100; ++i) {
    int still_active;
    pthread_mutex_lock(&h->mu);
    still_active = h->active;
    pthread_mutex_unlock(&h->mu);
    if (!still_active) break;
    sleep_ms(5);
  }
  pthread_mutex_lock(&h->mu);
  h->want_stop = 0;
  if (h->active) {
    push_locked(h, h->active_id, READER_TTS_STOPPED, READER_TTS_OK);
    finish_locked(h);
  }
  pthread_mutex_unlock(&h->mu);
  return succeed(e);
}

reader_tts_status reader_tts_observe(reader_tts *h, reader_tts_snapshot *out, reader_tts_error *e) {
  reader_tts_status s = entry(h, e);
  int closed;
  if (s) return s;
  if (!out) return fail(e, READER_TTS_ARGUMENT, 0);
  pthread_mutex_lock(&h->mu);
  closed = closing_locked(h);
  pthread_mutex_unlock(&h->mu);
  if (!closed) housekeeping(h);
  pthread_mutex_lock(&h->mu);
  out->state = h->state;
  out->last_status = h->last_status;
  out->request_id = h->active ? h->active_id : h->last_id;
  out->capabilities = READER_TTS_CAN_PAUSE;
  pthread_mutex_unlock(&h->mu);
  return succeed(e);
}

reader_tts_status reader_tts_poll(reader_tts *h, reader_tts_event *ev, int *available,
                                  reader_tts_error *e) {
  reader_tts_status s = entry(h, e);
  int closed;
  if (s) return s;
  if (!ev || !available) return fail(e, READER_TTS_ARGUMENT, 0);
  pthread_mutex_lock(&h->mu);
  closed = closing_locked(h);
  pthread_mutex_unlock(&h->mu);
  if (!closed) housekeeping(h);
  pthread_mutex_lock(&h->mu);
  if (h->qn) {
    *ev = h->q[h->qh];
    h->qh = (h->qh + 1) % READER_TTS_EVENT_CAPACITY;
    --h->qn;
    *available = 1;
  } else {
    memset(ev, 0, sizeof *ev);
    *available = 0;
  }
  pthread_mutex_unlock(&h->mu);
  return succeed(e);
}

static void *closer_main(void *arg) {
  reader_tts *h = (reader_tts *)arg;
  pthread_mutex_lock(&h->mu);
  if (h->active) {
    push_locked(h, h->active_id, READER_TTS_STOPPED, READER_TTS_OK);
    h->active = 0;
    h->started = 0;
  }
  pthread_mutex_unlock(&h->mu);
  drop_conn(h);
  pthread_mutex_lock(&h->mu);
  h->state = READER_TTS_CLOSED;
  pthread_mutex_unlock(&h->mu);
  return NULL;
}

reader_tts_status reader_tts_request_close(reader_tts *h, reader_tts_error *e) {
  reader_tts_status s = entry(h, e);
  reader_tts_state previous;
  int rc;
  if (s) return s;
  pthread_mutex_lock(&h->mu);
  if (closing_locked(h)) {
    pthread_mutex_unlock(&h->mu);
    return succeed(e);
  }
  previous = h->state;
  h->state = READER_TTS_CLOSING;
  h->last_status = READER_TTS_OK;
  pthread_mutex_unlock(&h->mu);
  h->closer_running = 0;

  rc = pthread_create(&h->closer, NULL, closer_main, h);
  if (rc == 0) {
    h->closer_running = 1;
    return succeed(e);
  }

  /* No release thread was created, so nothing would advance CLOSING. Closing on
     this thread would block the owner inside spd_close() and break the promise
     that request_close never blocks, so the call is undone instead: the request,
     its queued events and the connection stay exactly as they were, and the owner
     may retry. The state is restored under the mutex the callbacks take, so a
     terminal event that arrived in this window is neither lost nor able to revive
     a finished request. */
  pthread_mutex_lock(&h->mu);
  if (h->state == READER_TTS_CLOSING) {
    if (h->active) {
      h->state = previous; /* nothing ended meanwhile: put back what was there */
    } else if (previous == READER_TTS_SERVICE_UNAVAILABLE || h->conn == NULL) {
      h->state = READER_TTS_SERVICE_UNAVAILABLE;
    } else {
      h->state = READER_TTS_READY; /* the request ended while the close failed */
    }
  }
  h->last_status = READER_TTS_MEMORY;
  pthread_mutex_unlock(&h->mu);
  return fail(e, READER_TTS_MEMORY, rc);
}

reader_tts_status reader_tts_destroy(reader_tts **handle, reader_tts_error *e) {
  reader_tts *h;
  reader_tts_status s;
  int closed;
  if (!handle || !*handle) return fail(e, READER_TTS_ARGUMENT, 0);
  h = *handle;
  s = entry(h, e);
  if (s) return s;
  pthread_mutex_lock(&h->mu);
  closed = h->state == READER_TTS_CLOSED;
  pthread_mutex_unlock(&h->mu);
  if (!closed) return fail(e, READER_TTS_BUSY, 0);
  if (h->closer_running) pthread_join(h->closer, NULL);
  pthread_mutex_destroy(&h->mu);
  free(h);
  *handle = NULL;
  return succeed(e);
}

#ifdef READER_TTS_TEST_HOOKS
/* Hook kind (0 begin, 1 end, 2 cancel) -> the installed header's enum value, so
   the tests do not depend on SPDNotificationType numbering. */
static int hook_event_type(int kind) {
  switch (kind) {
  case 1: return SPD_EVENT_END;
  case 2: return SPD_EVENT_CANCEL;
  default: return SPD_EVENT_BEGIN;
  }
}
void reader_tts_test_fail_alloc(int nth) { g_alloc_budget = nth; }
int reader_tts_test_conn_present(reader_tts *h) {
  int present;
  pthread_mutex_lock(&h->mu);
  present = h->conn != NULL;
  pthread_mutex_unlock(&h->mu);
  return present;
}
int reader_tts_test_slot_owner(reader_tts *h) {
  int owned;
  pthread_mutex_lock(&g_mu);
  owned = (g_conn_owner == h);
  pthread_mutex_unlock(&g_mu);
  return owned;
}
void reader_tts_test_dispatch_stale(long msg_id, int kind) {
  /* Exactly what libspeechd's event thread does: the shared path, current owner
     only, no per-handle hint. */
  pthread_mutex_lock(&g_mu);
  if (g_conn_owner) record_event(g_conn_owner, msg_id, hook_event_type(kind));
  pthread_mutex_unlock(&g_mu);
}
void reader_tts_test_arm_close_gate(void) {
  pthread_mutex_lock(&g_gate_mu);
  g_gate_armed = 1;
  g_gate_open = 0;
  g_gate_waiting = 0;
  pthread_mutex_unlock(&g_gate_mu);
}
int reader_tts_test_close_gate_waiting(void) {
  int waiting;
  pthread_mutex_lock(&g_gate_mu);
  waiting = g_gate_waiting;
  pthread_mutex_unlock(&g_gate_mu);
  return waiting;
}
void reader_tts_test_open_close_gate(void) {
  pthread_mutex_lock(&g_gate_mu);
  g_gate_open = 1;
  pthread_cond_broadcast(&g_gate_cv);
  pthread_mutex_unlock(&g_gate_mu);
}
void reader_tts_test_inject(reader_tts *h, long msg_id, int kind) {
  record_event(h, msg_id, hook_event_type(kind));
}
void reader_tts_test_force_msg_id(long msg_id) { g_force_msg = msg_id; }
void reader_tts_test_early_callback(int kind) { g_early_kind = kind < 0 ? -1 : hook_event_type(kind); }
long reader_tts_test_msg_id(reader_tts *h) {
  long m;
  pthread_mutex_lock(&h->mu);
  m = h->msg_id;
  pthread_mutex_unlock(&h->mu);
  return m;
}
void reader_tts_test_fill_queue(reader_tts *h, size_t n) {
  size_t i;
  pthread_mutex_lock(&h->mu);
  for (i = 0; i < n; ++i) push_locked(h, 0xFFFFFFFFu, READER_TTS_FINISHED, READER_TTS_OK);
  pthread_mutex_unlock(&h->mu);
}
size_t reader_tts_test_daemon_voice_count(reader_tts *h) {
  SPDVoice **v = list_voices(h);
  size_t n = 0, i;
  if (!v) return (size_t)-1;
  for (i = 0; i < 1000000u; ++i) {
    if (!v[i]) break;
    ++n;
  }
  voices_free(v);
  return n;
}
size_t reader_tts_test_queue_depth(reader_tts *h) {
  size_t d;
  pthread_mutex_lock(&h->mu);
  d = h->qn;
  pthread_mutex_unlock(&h->mu);
  return d;
}
#endif
