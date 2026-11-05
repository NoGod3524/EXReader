// SPDX-License-Identifier: MIT
// Request state machine behind the frozen reader_tts C ABI. Platform neutral:
// all speech goes through rtts::Engine, so the same code is exercised against
// the real AVSpeechSynthesizer backend (installed library) and against a fake
// engine in the logic suite (-DREADER_TTS_TESTING, never installed).
#include "engine.hpp"
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <mutex>
#include <new>
#include <pthread.h>

namespace {

constexpr size_t kEvents = READER_TTS_MAX_EVENTS;
constexpr size_t kEventsPerRequest = 3;  // STARTED, one coalesced RANGE, terminal
int g_close_deadline_ms = READER_TTS_CLOSE_DEADLINE_MS;
#ifdef READER_TTS_TESTING
int g_fail_countdown = 0;
#endif

// Every allocation the library makes is preceded by this point so the logic
// suite can fail the n-th one and prove the state stays unchanged.
void alloc_point() {
#ifdef READER_TTS_TESTING
  if (g_fail_countdown > 0 && --g_fail_countdown == 0) throw std::bad_alloc();
#endif
}

char *dup_string(const std::string &s) {
  alloc_point();
  char *p = static_cast<char *>(std::malloc(s.size() + 1));
  if (!p) throw std::bad_alloc();
  std::memcpy(p, s.data(), s.size());
  p[s.size()] = 0;
  return p;
}

// Strict UTF-8 (RFC 3629): no overlongs, no surrogates, nothing above U+10FFFF,
// no truncation and no embedded NUL.
bool valid_utf8(const unsigned char *s, size_t n) {
  size_t i = 0;
  while (i < n) {
    unsigned char c = s[i];
    if (c == 0) return false;
    if (c < 0x80) { ++i; continue; }
    size_t len;
    uint32_t cp;
    if (c >= 0xC2 && c <= 0xDF) { len = 2; cp = c & 0x1Fu; }
    else if (c >= 0xE0 && c <= 0xEF) { len = 3; cp = c & 0x0Fu; }
    else if (c >= 0xF0 && c <= 0xF4) { len = 4; cp = c & 0x07u; }
    else return false;
    if (n - i < len) return false;
    for (size_t k = 1; k < len; ++k) {
      if ((s[i + k] & 0xC0u) != 0x80u) return false;
      cp = (cp << 6) | (s[i + k] & 0x3Fu);
    }
    if (len == 2 && cp < 0x80) return false;
    if (len == 3 && (cp < 0x800 || (cp >= 0xD800 && cp <= 0xDFFF))) return false;
    if (len == 4 && (cp < 0x10000 || cp > 0x10FFFF)) return false;
    i += len;
  }
  return true;
}

// UTF-16 unit offset -> UTF-8 byte offset of the same scalar boundary. Offsets
// inside a surrogate pair or past the end have no boundary and are refused.
bool utf16_to_utf8(const std::string &s, size_t u16, size_t *out) {
  size_t i = 0, units = 0;
  const unsigned char *p = reinterpret_cast<const unsigned char *>(s.data());
  while (true) {
    if (units == u16) { *out = i; return true; }
    if (i >= s.size() || units > u16) return false;
    unsigned char c = p[i];
    size_t len = c < 0x80 ? 1 : c < 0xE0 ? 2 : c < 0xF0 ? 3 : 4;
    units += len == 4 ? 2 : 1;
    i += len;
  }
}

}  // namespace

#ifdef READER_TTS_TESTING
extern "C" void rtts_test_fail_alloc_after(int n) { g_fail_countdown = n; }
extern "C" void rtts_test_set_close_deadline_ms(int ms) { g_close_deadline_ms = ms; }
#endif

struct reader_tts : rtts::Sink {
  std::recursive_mutex mu;
  pthread_t owner;
  std::unique_ptr<rtts::Engine> engine;
  size_t max_bytes = READER_TTS_MAX_UTF8_BYTES;
  unsigned caps = 0;
  reader_tts_state state = READER_TTS_INITIALIZING;
  reader_tts_status last_status = READER_TTS_OK;
  uint64_t highest_id = 0;  // most recent accepted request
  uint64_t active = 0;      // request without terminal event, or 0
  bool started_emitted = false;
  std::string text;         // copy of the active input, for UTF-16 -> UTF-8
  reader_tts_event ring[kEvents];
  size_t head = 0, count = 0;
  std::chrono::steady_clock::time_point close_deadline, stop_deadline;

  void push(const reader_tts_event &e) {
    if (e.kind == READER_TTS_RANGE && count &&
        ring[(head + count - 1) % kEvents].kind == READER_TTS_RANGE &&
        ring[(head + count - 1) % kEvents].request_id == e.request_id) {
      ring[(head + count - 1) % kEvents] = e;  // newest range supersedes
      return;
    }
    if (count == kEvents) {  // unreachable by the speak() reservation; a
      if (e.kind == READER_TTS_RANGE) return;  // terminal is never dropped
      ring[(head + count - 1) % kEvents] = e;
      return;
    }
    ring[(head + count) % kEvents] = e;
    ++count;
  }
  static reader_tts_event make(uint64_t id, reader_tts_event_kind k, reader_tts_status s) {
    reader_tts_event e;
    std::memset(&e, 0, sizeof e);
    e.request_id = id; e.kind = k; e.status = s;
    return e;
  }
  void emit_started() {
    if (started_emitted) return;
    started_emitted = true;
    push(make(active, READER_TTS_STARTED, READER_TTS_OK));
  }
  void terminal(reader_tts_event_kind k, reader_tts_status s, int native) {
    (void)native;
    reader_tts_event e = make(active, k, s);
    push(e);
    active = 0; started_emitted = false; text.clear();
    if (k == READER_TTS_FAILED) last_status = s;
    if (state == READER_TTS_CLOSING) {
      engine->detach();
      state = READER_TTS_CLOSED;
    } else {
      state = READER_TTS_READY;
    }
  }
  // Deadlines are only evaluated on an owner call, so a host that never calls
  // back cannot be woken by the library (no timers, no extra threads).
  void tick() {
    const auto now = std::chrono::steady_clock::now();
    if (state == READER_TTS_STOPPING && now >= stop_deadline) {
      terminal(READER_TTS_STOPPED, READER_TTS_OK, 0);
      return;
    }
    if (state != READER_TTS_CLOSING || now < close_deadline) return;
    if (active) terminal(READER_TTS_STOPPED, READER_TTS_OK, 0);
    else { engine->detach(); state = READER_TTS_CLOSED; }
  }

  // ---- rtts::Sink: system callbacks ----
  void started(uint64_t id) override {
    std::lock_guard<std::recursive_mutex> l(mu);
    if (id == active && state != READER_TTS_CLOSED) emit_started();
  }
  void range16(uint64_t id, size_t loc, size_t len) override {
    std::lock_guard<std::recursive_mutex> l(mu);
    if (id != active || len == 0 || state == READER_TTS_CLOSED) return;
    size_t b0 = 0, b1 = 0;
    if (!utf16_to_utf8(text, loc, &b0) || !utf16_to_utf8(text, loc + len, &b1) || b1 <= b0) return;
    emit_started();
    reader_tts_event e = make(id, READER_TTS_RANGE, READER_TTS_OK);
    e.start = b0; e.end = b1; e.has_range = 1;
    push(e);
  }
  void paused(uint64_t id) override {
    std::lock_guard<std::recursive_mutex> l(mu);
    if (id == active && state == READER_TTS_SPEAKING) state = READER_TTS_PAUSED;
  }
  void resumed(uint64_t id) override {
    std::lock_guard<std::recursive_mutex> l(mu);
    if (id == active && state == READER_TTS_PAUSED) state = READER_TTS_SPEAKING;
  }
  void finished(uint64_t id) override {
    std::lock_guard<std::recursive_mutex> l(mu);
    if (id != active) return;
    emit_started();
    terminal(READER_TTS_FINISHED, READER_TTS_OK, 0);
  }
  void cancelled(uint64_t id) override {
    std::lock_guard<std::recursive_mutex> l(mu);
    if (id == active) terminal(READER_TTS_STOPPED, READER_TTS_OK, 0);
  }
  void failed(uint64_t id, int native) override {
    std::lock_guard<std::recursive_mutex> l(mu);
    if (id != active) return;
    emit_started();
    terminal(READER_TTS_FAILED, READER_TTS_IO, native);
  }
};

namespace {

reader_tts_status done(reader_tts_error *err, reader_tts_status s, int native = 0) {
  if (err) { err->code = s; err->native_code = native; }
  return s;
}

bool is_owner(reader_tts *h) { return pthread_equal(h->owner, pthread_self()) != 0; }

// Common prologue for owner-only calls.
#define ENTER(h, err)                                              \
  if (!(h)) return done(err, READER_TTS_ARGUMENT);                 \
  if (!is_owner(h)) return done(err, READER_TTS_OWNER);            \
  std::lock_guard<std::recursive_mutex> lock_((h)->mu);            \
  (h)->tick();

reader_tts_status remember(reader_tts *h, reader_tts_error *err, reader_tts_status s, int native = 0) {
  h->last_status = s;
  return done(err, s, native);
}

std::chrono::steady_clock::time_point deadline_from_now() {
  return std::chrono::steady_clock::now() + std::chrono::milliseconds(g_close_deadline_ms);
}

reader_tts_status check_active(reader_tts *h, uint64_t id, reader_tts_error *err) {
  if (id == 0 || id != h->active) return remember(h, err, READER_TTS_ARGUMENT);
  return READER_TTS_OK;
}

}  // namespace

extern "C" {

reader_tts_status reader_tts_create(const reader_tts_config *cfg, reader_tts **out, reader_tts_error *err) {
  if (out) *out = nullptr;
  if (!out) return done(err, READER_TTS_ARGUMENT);
  size_t cap = READER_TTS_MAX_UTF8_BYTES;
  if (cfg) {
    if (cfg->struct_size < sizeof(reader_tts_config)) return done(err, READER_TTS_ARGUMENT);
    if (cfg->max_utf8_bytes > READER_TTS_MAX_UTF8_BYTES) return done(err, READER_TTS_LIMIT);
    if (cfg->max_utf8_bytes) cap = cfg->max_utf8_bytes;
  }
  try {
    alloc_point();
    std::unique_ptr<reader_tts> h(new reader_tts());
    h->owner = pthread_self();
    h->max_bytes = cap;
    reader_tts_status st = READER_TTS_OK;
    int native = 0;
    h->engine = rtts::make_platform_engine(h.get(), &st, &native);
    if (!h->engine) return done(err, st == READER_TTS_OK ? READER_TTS_UNAVAILABLE : st, native);
    h->caps = h->engine->capabilities();
    h->state = h->engine->available() ? READER_TTS_READY : READER_TTS_SERVICE_UNAVAILABLE;
    *out = h.release();
    return done(err, READER_TTS_OK);
  } catch (const std::bad_alloc &) {
    return done(err, READER_TTS_MEMORY);
  } catch (...) {
    return done(err, READER_TTS_IO);
  }
}

reader_tts_status reader_tts_voices(reader_tts *h, reader_tts_voice_list *list, reader_tts_error *err) {
  if (list) { list->voices = nullptr; list->count = 0; }
  ENTER(h, err);
  if (!list) return done(err, READER_TTS_ARGUMENT);
  if (h->state == READER_TTS_CLOSING || h->state == READER_TTS_CLOSED ||
      h->state == READER_TTS_SERVICE_UNAVAILABLE)
    return done(err, READER_TTS_UNAVAILABLE);
  std::vector<rtts::VoiceInfo> v;
  try {
    if (!h->engine->voices(&v)) return done(err, READER_TTS_UNAVAILABLE);
    if (v.empty()) return done(err, READER_TTS_OK);
    if (v.size() > READER_TTS_MAX_VOICES) return done(err, READER_TTS_LIMIT);
    alloc_point();
    reader_tts_voice *arr = static_cast<reader_tts_voice *>(std::calloc(v.size(), sizeof *arr));
    if (!arr) throw std::bad_alloc();
    size_t made = 0;
    try {
      for (; made < v.size(); ++made) {
        arr[made].id = dup_string(v[made].id);
        arr[made].name = dup_string(v[made].name);
        arr[made].language = dup_string(v[made].language);
      }
    } catch (...) {
      for (size_t i = 0; i <= made && i < v.size(); ++i) {
        std::free(arr[i].id); std::free(arr[i].name); std::free(arr[i].language);
      }
      std::free(arr);
      throw;
    }
    list->voices = arr; list->count = v.size();
    return done(err, READER_TTS_OK);
  } catch (const std::bad_alloc &) {
    return done(err, READER_TTS_MEMORY);
  } catch (...) {
    return done(err, READER_TTS_IO);
  }
}

void reader_tts_voice_list_free(reader_tts_voice_list *list) {
  if (!list) return;
  for (size_t i = 0; list->voices && i < list->count; ++i) {
    std::free(list->voices[i].id); std::free(list->voices[i].name); std::free(list->voices[i].language);
  }
  std::free(list->voices);
  list->voices = nullptr; list->count = 0;
}

reader_tts_status reader_tts_speak(reader_tts *h, uint64_t id, const char *utf8, size_t bytes,
                                   const char *voice_id, double rate, reader_tts_error *err) {
  ENTER(h, err);
  // Pure argument checks first: they never depend on the current state.
  if (id == 0 || id <= h->highest_id) return remember(h, err, READER_TTS_ARGUMENT);
  if (!utf8 || bytes == 0) return remember(h, err, READER_TTS_ARGUMENT);
  if (!std::isfinite(rate) || rate < 0.5 || rate > 2.0) return remember(h, err, READER_TTS_ARGUMENT);
  if (!valid_utf8(reinterpret_cast<const unsigned char *>(utf8), bytes)) return remember(h, err, READER_TTS_ARGUMENT);
  switch (h->state) {
    case READER_TTS_READY: break;
    case READER_TTS_SPEAKING: case READER_TTS_PAUSED: case READER_TTS_STOPPING:
      return remember(h, err, READER_TTS_BUSY);
    default: return remember(h, err, READER_TTS_UNAVAILABLE);
  }
  if (bytes > h->max_bytes) return remember(h, err, READER_TTS_LIMIT);
  // Reserve room for STARTED + one coalesced RANGE + the terminal event.
  if (h->count + kEventsPerRequest > kEvents) return remember(h, err, READER_TTS_LIMIT);
  try {
    std::string voice = voice_id ? voice_id : "";
    if (!voice.empty() && !h->engine->voice_exists(voice)) return remember(h, err, READER_TTS_ARGUMENT);
    alloc_point();
    std::string copy(utf8, bytes);
    h->text.swap(copy);
    h->active = id; h->started_emitted = false;
    const uint64_t started_id = id;
    int native = 0;
    if (!h->engine->speak(id, h->text, voice, rate, &native)) {
      h->active = 0; h->text.clear();
      return remember(h, err, READER_TTS_IO, native);
    }
    // A synchronous terminal callback inside speak() already finished the request.
    if (h->active == started_id) h->state = READER_TTS_SPEAKING;
    h->highest_id = id;
    return remember(h, err, READER_TTS_OK);
  } catch (const std::bad_alloc &) {
    h->active = 0; h->text.clear();
    return remember(h, err, READER_TTS_MEMORY);
  } catch (...) {
    h->active = 0; h->text.clear();
    return remember(h, err, READER_TTS_IO);
  }
}

reader_tts_status reader_tts_pause(reader_tts *h, uint64_t id, reader_tts_error *err) {
  ENTER(h, err);
  if (!(h->caps & READER_TTS_CAN_PAUSE)) return remember(h, err, READER_TTS_UNSUPPORTED);
  if (h->state == READER_TTS_CLOSING || h->state == READER_TTS_CLOSED) return remember(h, err, READER_TTS_UNAVAILABLE);
  reader_tts_status s = check_active(h, id, err);
  if (s != READER_TTS_OK) return s;
  if (h->state == READER_TTS_PAUSED) return remember(h, err, READER_TTS_OK);
  if (h->state != READER_TTS_SPEAKING) return remember(h, err, READER_TTS_BUSY);
  int native = 0;
  if (!h->engine->pause(&native)) return remember(h, err, READER_TTS_BUSY, native);
  if (h->state == READER_TTS_SPEAKING) h->state = READER_TTS_PAUSED;
  return remember(h, err, READER_TTS_OK);
}

reader_tts_status reader_tts_resume(reader_tts *h, uint64_t id, reader_tts_error *err) {
  ENTER(h, err);
  if (!(h->caps & READER_TTS_CAN_PAUSE)) return remember(h, err, READER_TTS_UNSUPPORTED);
  if (h->state == READER_TTS_CLOSING || h->state == READER_TTS_CLOSED) return remember(h, err, READER_TTS_UNAVAILABLE);
  reader_tts_status s = check_active(h, id, err);
  if (s != READER_TTS_OK) return s;
  if (h->state == READER_TTS_SPEAKING) return remember(h, err, READER_TTS_OK);
  if (h->state != READER_TTS_PAUSED) return remember(h, err, READER_TTS_BUSY);
  int native = 0;
  if (!h->engine->resume(&native)) return remember(h, err, READER_TTS_BUSY, native);
  if (h->state == READER_TTS_PAUSED) h->state = READER_TTS_SPEAKING;
  return remember(h, err, READER_TTS_OK);
}

reader_tts_status reader_tts_stop(reader_tts *h, uint64_t id, reader_tts_error *err) {
  ENTER(h, err);
  if (h->state == READER_TTS_CLOSED) return remember(h, err, READER_TTS_UNAVAILABLE);
  reader_tts_status s = check_active(h, id, err);
  if (s != READER_TTS_OK) return s;
  if (h->state == READER_TTS_STOPPING || h->state == READER_TTS_CLOSING) return remember(h, err, READER_TTS_OK);
  h->state = READER_TTS_STOPPING;
  h->stop_deadline = deadline_from_now();
  if (!h->engine->stop() && h->active == id) h->terminal(READER_TTS_STOPPED, READER_TTS_OK, 0);
  return remember(h, err, READER_TTS_OK);
}

reader_tts_status reader_tts_observe(reader_tts *h, reader_tts_snapshot *snap, reader_tts_error *err) {
  ENTER(h, err);
  if (!snap) return done(err, READER_TTS_ARGUMENT);
  snap->state = h->state;
  snap->last_status = h->last_status;
  snap->request_id = h->highest_id;
  snap->capabilities = h->caps;
  return done(err, READER_TTS_OK);
}

reader_tts_status reader_tts_poll(reader_tts *h, reader_tts_event *ev, int *available, reader_tts_error *err) {
  if (available) *available = 0;
  if (ev) std::memset(ev, 0, sizeof *ev);
  ENTER(h, err);
  if (!ev || !available) return done(err, READER_TTS_ARGUMENT);
  if (h->count) {
    *ev = h->ring[h->head];
    h->head = (h->head + 1) % kEvents;
    --h->count;
    *available = 1;
  }
  return done(err, READER_TTS_OK);
}

reader_tts_status reader_tts_request_close(reader_tts *h, reader_tts_error *err) {
  ENTER(h, err);
  if (h->state == READER_TTS_CLOSING || h->state == READER_TTS_CLOSED) return done(err, READER_TTS_OK);
  h->state = READER_TTS_CLOSING;
  h->close_deadline = deadline_from_now();
  h->stop_deadline = h->close_deadline;
  if (!h->active) {
    h->engine->detach();
    h->state = READER_TTS_CLOSED;
  } else if (!h->engine->stop() && h->active) {
    h->terminal(READER_TTS_STOPPED, READER_TTS_OK, 0);  // moves to CLOSED
  }
  return remember(h, err, READER_TTS_OK);
}

reader_tts_status reader_tts_destroy(reader_tts **hp, reader_tts_error *err) {
  if (!hp) return done(err, READER_TTS_ARGUMENT);
  reader_tts *h = *hp;
  if (!h) return done(err, READER_TTS_OK);
  if (!is_owner(h)) return done(err, READER_TTS_OWNER);
  {
    std::lock_guard<std::recursive_mutex> lock(h->mu);
    h->tick();
    if (h->state != READER_TTS_CLOSED) return done(err, READER_TTS_BUSY);
  }
  delete h;
  *hp = nullptr;
  return done(err, READER_TTS_OK);
}

}  // extern "C"
