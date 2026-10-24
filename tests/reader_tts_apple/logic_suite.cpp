// SPDX-License-Identifier: MIT
// Platform-neutral logic suite: the frozen ABI against a deterministic fake
// engine. Every case is named and reported individually; any failure exits
// non-zero. Compiled only with -DREADER_TTS_TESTING.
#include "engine.hpp"
#include "fake_engine.hpp"

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <functional>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

namespace {

struct Outcome {
  std::string name;
  std::string status;  // pass | fail
  std::string detail;
};

std::vector<Outcome> g_outcomes;
int g_pass = 0;
int g_fail = 0;

void Record(const std::string &name, const char *status, const std::string &detail) {
  g_outcomes.push_back(Outcome{name, status, detail});
  if (std::strcmp(status, "pass") == 0) ++g_pass;
  else ++g_fail;
  if (std::strcmp(status, "pass") != 0) {
    std::printf("FAIL %s: %s\n", name.c_str(), detail.c_str());
  } else {
    std::printf("PASS %s\n", name.c_str());
  }
  std::fflush(stdout);
}

void Need(bool ok, const char *message) {
  if (!ok) throw std::runtime_error(message);
}

std::string Require(bool ok, const char *message) { return ok ? std::string() : std::string(message); }

void Case(const char *name, const std::function<std::string()> &body) {
  try {
    const std::string detail = body();
    if (detail.empty()) Record(name, "pass", "");
    else Record(name, "fail", detail);
  } catch (const std::exception &error) {
    Record(name, "fail", std::string("unexpected: ") + error.what());
  } catch (...) {
    Record(name, "fail", "unexpected non-standard exception");
  }
}

struct Handle {
  reader_tts *h = nullptr;
  reader_tts_error err{};

  Handle() = default;
  Handle(size_t cap, const rtts::test::FakeConfig &config) { Create(cap, config); }

  void Create(size_t cap, const rtts::test::FakeConfig &config) {
    rtts::test::Configure(config);
    reader_tts_config cfg{};
    cfg.struct_size = sizeof cfg;
    cfg.max_utf8_bytes = cap;
    Need(reader_tts_create(&cfg, &h, &err) == READER_TTS_OK, "create");
  }

  ~Handle() { Dispose(); }

  void Dispose() {
    if (!h) return;
    reader_tts_error error{};
    reader_tts_request_close(h, &error);
    rtts_test_set_close_deadline_ms(0);
    reader_tts_snapshot snap{};
    reader_tts_observe(h, &snap, &error);
    rtts_test_set_close_deadline_ms(READER_TTS_CLOSE_DEADLINE_MS);
    for (;;) {
      reader_tts_event event{};
      int available = 0;
      if (reader_tts_poll(h, &event, &available, &error) != READER_TTS_OK || !available) break;
    }
    reader_tts_destroy(&h, &error);
    rtts::test::ClearInstance();
  }

  rtts::test::FakeEngine *fake() const { return rtts::test::Instance(); }
};

bool Poll(reader_tts *h, reader_tts_event *event) {
  reader_tts_error error{};
  int available = 0;
  const reader_tts_status status = reader_tts_poll(h, event, &available, &error);
  Need(status == READER_TTS_OK, "poll failed");
  return available != 0;
}

std::vector<reader_tts_event> Drain(reader_tts *h) {
  std::vector<reader_tts_event> events;
  reader_tts_event event{};
  while (Poll(h, &event)) events.push_back(event);
  return events;
}

const char *kShort = "Read this.";

reader_tts_status Speak(reader_tts *h, uint64_t id, const char *text, double rate = 1.0,
                        const char *voice = nullptr) {
  reader_tts_error error{};
  return reader_tts_speak(h, id, text, std::strlen(text), voice, rate, &error);
}

std::string SpeakOk(reader_tts *h, uint64_t id, const char *text, double rate = 1.0,
                    const char *voice = nullptr) {
  const reader_tts_status status = Speak(h, id, text, rate, voice);
  if (status != READER_TTS_OK) return "speak returned " + std::to_string((int)status);
  return {};
}

reader_tts_state State(reader_tts *h) {
  reader_tts_snapshot snap{};
  reader_tts_error error{};
  Need(reader_tts_observe(h, &snap, &error) == READER_TTS_OK, "observe failed");
  return snap.state;
}

std::string EventsAreOrdered(const std::vector<reader_tts_event> &events, uint64_t request_id) {
  if (events.empty()) return "no events";
  if (events.front().kind != READER_TTS_STARTED) return "first event is not STARTED";
  if (events.size() < 3) return "expected STARTED, RANGE, terminal";
  const reader_tts_event_kind last = events.back().kind;
  if (last != READER_TTS_FINISHED && last != READER_TTS_STOPPED && last != READER_TTS_FAILED)
    return "last event is not terminal";
  size_t terminals = 0;
  for (size_t i = 0; i < events.size(); ++i) {
    if (events[i].request_id != request_id) return "event carries a foreign request id";
    const reader_tts_event_kind kind = events[i].kind;
    if (kind == READER_TTS_FINISHED || kind == READER_TTS_STOPPED || kind == READER_TTS_FAILED) {
      ++terminals;
      if (i + 1 != events.size()) return "terminal is not the last event";
    }
  }
  if (terminals != 1) return "expected exactly one terminal event";
  return {};
}

}  // namespace

int main() {
  using rtts::test::FakeConfig;
  using rtts::test::Instance;

  // ---------- creation and configuration ----------
  Case("create.default-config", [&]() -> std::string {
    rtts::test::Configure(FakeConfig{});
    reader_tts *h = nullptr;
    reader_tts_error err{};
    Need(reader_tts_create(nullptr, &h, &err) == READER_TTS_OK, "create with NULL config");
    std::string detail = Require(h != nullptr, "handle is NULL");
    reader_tts_snapshot snap{};
    Need(reader_tts_observe(h, &snap, &err) == READER_TTS_OK, "observe");
    detail = Require(snap.state == READER_TTS_READY, "state is not READY");
    detail = Require(snap.request_id == 0, "request_id is not 0");
    detail = Require(snap.last_status == READER_TTS_OK, "last_status is not OK");
    reader_tts_request_close(h, &err);
    rtts_test_set_close_deadline_ms(0);
    reader_tts_observe(h, &snap, &err);
    rtts_test_set_close_deadline_ms(READER_TTS_CLOSE_DEADLINE_MS);
    return Require(reader_tts_destroy(&h, &err) == READER_TTS_OK && h == nullptr, "destroy");
  });

  Case("create.null-out-argument", [&]() -> std::string {
    rtts::test::Configure(FakeConfig{});
    reader_tts_error err{};
    return Require(reader_tts_create(nullptr, nullptr, &err) == READER_TTS_ARGUMENT, "expected ARGUMENT");
  });

  Case("create.short-struct-size", [&]() -> std::string {
    rtts::test::Configure(FakeConfig{});
    reader_tts_config cfg{};
    cfg.struct_size = sizeof(cfg) - 1;
    reader_tts *h = reinterpret_cast<reader_tts *>(0x1);
    reader_tts_error err{};
    const reader_tts_status status = reader_tts_create(&cfg, &h, &err);
    std::string detail = Require(status == READER_TTS_ARGUMENT, "expected ARGUMENT");
    return Require(h == nullptr, "handle not nulled");
  });

  Case("create.cap-above-maximum", [&]() -> std::string {
    rtts::test::Configure(FakeConfig{});
    reader_tts_config cfg{};
    cfg.struct_size = sizeof cfg;
    cfg.max_utf8_bytes = READER_TTS_MAX_UTF8_BYTES + 1;
    reader_tts *h = nullptr;
    reader_tts_error err{};
    return Require(reader_tts_create(&cfg, &h, &err) == READER_TTS_LIMIT && h == nullptr, "expected LIMIT");
  });

  Case("create.lowered-cap-enforced", [&]() -> std::string {
    Handle handle(64, FakeConfig{});
    std::string sixty_four(64, 'a');
    std::string sixty_five(65, 'a');
    reader_tts_error err{};
    std::string detail = Require(reader_tts_speak(handle.h, 1, sixty_five.data(), sixty_five.size(), nullptr, 1.0,
                                                  &err) == READER_TTS_LIMIT,
                                 "65 bytes above a 64 byte cap did not return LIMIT");
    detail = Require(reader_tts_speak(handle.h, 1, sixty_four.data(), sixty_four.size(), nullptr, 1.0, &err) ==
                         READER_TTS_OK,
                     "64 bytes at a 64 byte cap was rejected");
    return detail;
  });

  Case("create.no-installed-voice-is-service-unavailable", [&]() -> std::string {
    FakeConfig config;
    config.available = false;
    Handle handle(0, config);
    std::string detail = Require(State(handle.h) == READER_TTS_SERVICE_UNAVAILABLE, "state is not SERVICE_UNAVAILABLE");
    reader_tts_error err{};
    detail = Require(reader_tts_speak(handle.h, 1, kShort, std::strlen(kShort), nullptr, 1.0, &err) ==
                         READER_TTS_UNAVAILABLE,
                     "speak did not return UNAVAILABLE");
    reader_tts_voice_list list{};
    return Require(reader_tts_voices(handle.h, &list, &err) == READER_TTS_UNAVAILABLE && list.voices == nullptr &&
                       list.count == 0,
                   "voices did not return an empty UNAVAILABLE list");
  });

  Case("create.engine-requires-attached-thread", [&]() -> std::string {
    FakeConfig config;
    config.require_main_thread = true;
    rtts::test::Configure(config);
    std::atomic<int> status{-1};
    std::thread worker([&]() {
      reader_tts_config cfg{};
      cfg.struct_size = sizeof cfg;
      reader_tts *h = nullptr;
      reader_tts_error err{};
      status.store((int)reader_tts_create(&cfg, &h, &err));
    });
    worker.join();
    return Require(status.load() == (int)READER_TTS_OWNER, "expected OWNER from a non-attached thread");
  });

  // ---------- argument validation ----------
  Case("speak.zero-bytes-argument", [&]() -> std::string {
    Handle handle(0, FakeConfig{});
    reader_tts_error err{};
    return Require(reader_tts_speak(handle.h, 1, "", 0, nullptr, 1.0, &err) == READER_TTS_ARGUMENT, "expected ARGUMENT");
  });

  Case("speak.null-text-argument", [&]() -> std::string {
    Handle handle(0, FakeConfig{});
    reader_tts_error err{};
    return Require(reader_tts_speak(handle.h, 1, nullptr, 4, nullptr, 1.0, &err) == READER_TTS_ARGUMENT,
                   "expected ARGUMENT");
  });

  Case("speak.zero-request-id-argument", [&]() -> std::string {
    Handle handle(0, FakeConfig{});
    return Require(Speak(handle.h, 0, kShort) == READER_TTS_ARGUMENT, "expected ARGUMENT");
  });

  Case("speak.reused-request-id-argument", [&]() -> std::string {
    Handle handle(0, FakeConfig{});
    std::string detail = SpeakOk(handle.h, 7, kShort);
    if (!detail.empty()) return detail;
    handle.fake()->DeliverStarted(7);
    handle.fake()->DeliverFinished(7);
    Drain(handle.h);
    return Require(Speak(handle.h, 7, kShort) == READER_TTS_ARGUMENT, "reused id was accepted");
  });

  Case("speak.rate-outside-range-argument", [&]() -> std::string {
    Handle handle(0, FakeConfig{});
    std::string detail = Require(Speak(handle.h, 1, kShort, 0.49) == READER_TTS_ARGUMENT, "rate 0.49 accepted");
    detail = Require(Speak(handle.h, 1, kShort, 2.01) == READER_TTS_ARGUMENT, "rate 2.01 accepted");
    detail = Require(Speak(handle.h, 1, kShort, std::nan("")) == READER_TTS_ARGUMENT, "NaN rate accepted");
    detail = Require(Speak(handle.h, 1, kShort, INFINITY) == READER_TTS_ARGUMENT, "infinite rate accepted");
    return detail;
  });

  Case("speak.rate-edges-accepted", [&]() -> std::string {
    Handle handle(0, FakeConfig{});
    std::string detail = SpeakOk(handle.h, 1, kShort, 0.5);
    if (!detail.empty()) return detail;
    handle.fake()->DeliverStarted(1);
    handle.fake()->DeliverFinished(1);
    Drain(handle.h);
    detail = SpeakOk(handle.h, 2, kShort, 2.0);
    if (!detail.empty()) return detail;
    handle.fake()->DeliverFinished(2);
    return Require(handle.fake()->last_speak.rate == 2.0, "rate not forwarded to the engine");
  });

  Case("speak.invalid-utf8-rejected", [&]() -> std::string {
    Handle handle(0, FakeConfig{});
    reader_tts_error err{};
    const char lone[] = {'a', (char)0x80, 0};
    const char truncated[] = {(char)0xE4, (char)0xB8, 0};
    const char surrogate[] = {(char)0xED, (char)0xA0, (char)0x80, 0};
    const char overlong[] = {(char)0xC0, (char)0xAF, 0};
    const char too_high[] = {(char)0xF4, (char)0x90, (char)0x80, (char)0x80, 0};
    const char with_nul[] = {'a', 0, 'b'};
    for (const char *bad : {lone, truncated, surrogate, overlong, too_high}) {
      const size_t bytes = std::strlen(bad);
      std::string detail = Require(reader_tts_speak(handle.h, 1, bad, bytes, nullptr, 1.0, &err) ==
                                       READER_TTS_ARGUMENT,
                                   "invalid sequence accepted");
      if (!detail.empty()) return detail;
    }
    return Require(reader_tts_speak(handle.h, 1, with_nul, sizeof with_nul, nullptr, 1.0, &err) ==
                       READER_TTS_ARGUMENT,
                   "embedded NUL accepted");
  });

  Case("speak.valid-unicode-accepted", [&]() -> std::string {
    Handle handle(0, FakeConfig{});
    const char *text = "A\u4e2d\U0001F600B\u00e9";  // 1 + 3 + 4 + 1 + 2 bytes
    std::string detail = SpeakOk(handle.h, 1, text);
    if (!detail.empty()) return detail;
    return Require(handle.fake()->last_speak.text == text, "text not copied verbatim");
  });

  Case("speak.over-maximum-bytes-limit", [&]() -> std::string {
    Handle handle(0, FakeConfig{});
    std::string big(READER_TTS_MAX_UTF8_BYTES + 1, 'a');
    reader_tts_error err{};
    return Require(reader_tts_speak(handle.h, 1, big.data(), big.size(), nullptr, 1.0, &err) == READER_TTS_LIMIT,
                   "expected LIMIT");
  });

  Case("speak.unknown-voice-argument", [&]() -> std::string {
    FakeConfig config;
    config.voice_known = false;
    Handle handle(0, config);
    return Require(Speak(handle.h, 1, kShort, 1.0, "com.example.unknown") == READER_TTS_ARGUMENT,
                   "unknown voice accepted");
  });

  Case("speak.engine-refusal-maps-to-io", [&]() -> std::string {
    FakeConfig config;
    config.speak_fails = true;
    config.speak_native = 42;
    Handle handle(0, config);
    reader_tts_error err{};
    const reader_tts_status status = reader_tts_speak(handle.h, 1, kShort, std::strlen(kShort), nullptr, 1.0, &err);
    std::string detail = Require(status == READER_TTS_IO, "expected IO");
    detail = Require(err.native_code == 42, "native code not propagated");
    detail = Require(State(handle.h) == READER_TTS_READY, "state changed by a refused speak");
    detail = Require(Drain(handle.h).empty(), "events were emitted for a refused speak");
    return Require(Speak(handle.h, 1, kShort) == READER_TTS_OK, "refused id was consumed");
  });

  // ---------- lifecycle ----------
  Case("speak.started-range-terminal-ordering", [&]() -> std::string {
    Handle handle(0, FakeConfig{});
    std::string detail = SpeakOk(handle.h, 1, "Hello world.");
    if (!detail.empty()) return detail;
    detail = Require(State(handle.h) == READER_TTS_SPEAKING, "state is not SPEAKING");
    handle.fake()->DeliverStarted(1);
    handle.fake()->DeliverRange(1, 0, 5);
    handle.fake()->DeliverFinished(1);
    const std::vector<reader_tts_event> events = Drain(handle.h);
    detail = EventsAreOrdered(events, 1);
    if (!detail.empty()) return detail;
    detail = Require(events[1].has_range == 1 && events[1].start == 0 && events[1].end == 5, "range bytes wrong");
    return Require(State(handle.h) == READER_TTS_READY, "state is not READY after the terminal event");
  });

  Case("speak.utf16-offsets-convert-to-utf8", [&]() -> std::string {
    Handle handle(0, FakeConfig{});
    const char *text = "A\u4e2d\U0001F600B";  // 9 bytes: 1 + 3 + 4 + 1; 5 UTF-16 units
    std::string detail = SpeakOk(handle.h, 1, text);
    if (!detail.empty()) return detail;
    handle.fake()->DeliverStarted(1);
    handle.fake()->DeliverRange(1, 1, 1);  // U+4E2D -> bytes 1..4
    handle.fake()->DeliverRange(1, 2, 2);  // U+1F600 -> bytes 4..8
    handle.fake()->DeliverRange(1, 4, 1);  // 'B' -> bytes 8..9
    handle.fake()->DeliverFinished(1);
    const std::vector<reader_tts_event> events = Drain(handle.h);
    detail = Require(events.size() == 3, "range events were not coalesced into one");
    if (!detail.empty()) return detail;
    detail = Require(events[1].start == 8 && events[1].end == 9, "last range is not the final scalar");
    return detail;
  });

  Case("speak.range-coalescing-keeps-newest", [&]() -> std::string {
    Handle handle(0, FakeConfig{});
    std::string detail = SpeakOk(handle.h, 1, "abcdefghij");
    if (!detail.empty()) return detail;
    handle.fake()->DeliverStarted(1);
    handle.fake()->DeliverRange(1, 0, 2);
    handle.fake()->DeliverRange(1, 2, 2);
    handle.fake()->DeliverRange(1, 4, 3);
    const std::vector<reader_tts_event> events = Drain(handle.h);
    detail = Require(events.size() == 2, "expected STARTED plus one coalesced RANGE");
    if (!detail.empty()) return detail;
    return Require(events[1].start == 4 && events[1].end == 7, "newest range did not supersede");
  });

  Case("speak.range-drops-unusable-offsets", [&]() -> std::string {
    Handle handle(0, FakeConfig{});
    const char *text = "A\u4e2d\U0001F600B";
    std::string detail = SpeakOk(handle.h, 1, text);
    if (!detail.empty()) return detail;
    handle.fake()->DeliverStarted(1);
    handle.fake()->DeliverRange(1, 2, 1);   // inside the surrogate pair
    handle.fake()->DeliverRange(1, 5, 1);   // past the end
    handle.fake()->DeliverRange(1, 3, 0);   // zero length
    const std::vector<reader_tts_event> events = Drain(handle.h);
    detail = Require(events.size() == 1, "an unusable range produced an event");
    if (!detail.empty()) return detail;
    return Require(events[0].kind == READER_TTS_STARTED, "expected only STARTED");
  });

  Case("speak.range-emits-started-when-system-skips-it", [&]() -> std::string {
    Handle handle(0, FakeConfig{});
    std::string detail = SpeakOk(handle.h, 1, "abcdef");
    if (!detail.empty()) return detail;
    handle.fake()->DeliverRange(1, 0, 3);
    const std::vector<reader_tts_event> events = Drain(handle.h);
    detail = Require(events.size() == 2 && events[0].kind == READER_TTS_STARTED, "STARTED was not synthesized");
    return detail;
  });

  Case("speak.input-is-copied", [&]() -> std::string {
    Handle handle(0, FakeConfig{});
    std::string text = "A\u4e2dB";
    reader_tts_error err{};
    Need(reader_tts_speak(handle.h, 1, text.data(), text.size(), nullptr, 1.0, &err) == READER_TTS_OK, "speak");
    std::fill(text.begin(), text.end(), '\x7f');  // caller reuses its buffer
    handle.fake()->DeliverStarted(1);
    handle.fake()->DeliverRange(1, 1, 1);
    const std::vector<reader_tts_event> events = Drain(handle.h);
    std::string detail = Require(events.size() == 2, "range event lost");
    if (!detail.empty()) return detail;
    return Require(events[1].start == 1 && events[1].end == 4, "conversion used the caller buffer");
  });

  Case("speak.failure-maps-to-failed-event", [&]() -> std::string {
    Handle handle(0, FakeConfig{});
    std::string detail = SpeakOk(handle.h, 1, kShort);
    if (!detail.empty()) return detail;
    handle.fake()->DeliverStarted(1);
    handle.fake()->DeliverFailed(1, 9);
    const std::vector<reader_tts_event> events = Drain(handle.h);
    detail = Require(events.size() == 2 && events[1].kind == READER_TTS_FAILED, "no FAILED event");
    if (!detail.empty()) return detail;
    detail = Require(events[1].status == READER_TTS_IO, "FAILED status is not IO");
    reader_tts_snapshot snap{};
    reader_tts_error err{};
    reader_tts_observe(handle.h, &snap, &err);
    return Require(snap.last_status == READER_TTS_IO && snap.state == READER_TTS_READY, "last_status/state wrong");
  });

  Case("speak.second-request-while-active-is-busy", [&]() -> std::string {
    Handle handle(0, FakeConfig{});
    std::string detail = SpeakOk(handle.h, 1, kShort);
    if (!detail.empty()) return detail;
    detail = Require(Speak(handle.h, 2, kShort) == READER_TTS_BUSY, "replacement was not BUSY");
    if (!detail.empty()) return detail;
    detail = Require(State(handle.h) == READER_TTS_SPEAKING, "state changed by BUSY");
    handle.fake()->DeliverStarted(1);
    handle.fake()->DeliverFinished(1);
    Drain(handle.h);
    return Require(Speak(handle.h, 2, kShort) == READER_TTS_OK, "new id rejected after the terminal event");
  });

  Case("speak.inline-start-and-cancel-callbacks", [&]() -> std::string {
    FakeConfig config;
    config.speak_starts_inline = true;
    config.speak_cancels_inline = true;
    Handle handle(0, config);
    const reader_tts_status status = Speak(handle.h, 1, kShort);
    std::string detail = Require(status == READER_TTS_OK, "speak did not report OK");
    const std::vector<reader_tts_event> events = Drain(handle.h);
    detail = Require(events.size() == 2, "expected STARTED and STOPPED");
    if (!detail.empty()) return detail;
    detail = Require(events[0].kind == READER_TTS_STARTED && events[1].kind == READER_TTS_STOPPED,
                     "inline callbacks were mis-ordered");
    if (!detail.empty()) return detail;
    detail = Require(State(handle.h) == READER_TTS_READY, "state is not READY after an inline terminal");
    return detail;
  });

  // ---------- pause / resume / stop ----------
  Case("pause.resume.state-machine", [&]() -> std::string {
    Handle handle(0, FakeConfig{});
    std::string detail = SpeakOk(handle.h, 1, kShort);
    if (!detail.empty()) return detail;
    handle.fake()->DeliverStarted(1);
    reader_tts_error err{};
    detail = Require(reader_tts_pause(handle.h, 1, &err) == READER_TTS_OK, "pause failed");
    if (!detail.empty()) return detail;
    detail = Require(State(handle.h) == READER_TTS_PAUSED, "state is not PAUSED");
    if (!detail.empty()) return detail;
    detail = Require(reader_tts_pause(handle.h, 1, &err) == READER_TTS_OK, "repeated pause is not idempotent");
    handle.fake()->DeliverPaused(1);
    detail = Require(reader_tts_resume(handle.h, 1, &err) == READER_TTS_OK, "resume failed");
    if (!detail.empty()) return detail;
    detail = Require(State(handle.h) == READER_TTS_SPEAKING, "state is not SPEAKING");
    if (!detail.empty()) return detail;
    detail = Require(reader_tts_resume(handle.h, 1, &err) == READER_TTS_OK, "repeated resume is not idempotent");
    if (!detail.empty()) return detail;
    handle.fake()->DeliverResumed(1);
    return detail;
  });

  Case("pause.unsupported-capability", [&]() -> std::string {
    FakeConfig config;
    config.pause_supported = false;
    Handle handle(0, config);
    std::string detail = SpeakOk(handle.h, 1, kShort);
    if (!detail.empty()) return detail;
    reader_tts_error err{};
    detail = Require(reader_tts_pause(handle.h, 1, &err) == READER_TTS_UNSUPPORTED, "expected UNSUPPORTED");
    if (!detail.empty()) return detail;
    detail = Require(reader_tts_resume(handle.h, 1, &err) == READER_TTS_UNSUPPORTED, "expected UNSUPPORTED");
    handle.fake()->DeliverStarted(1);
    return Require(State(handle.h) == READER_TTS_SPEAKING, "state changed by UNSUPPORTED");
  });

  Case("pause.engine-refusal-is-busy", [&]() -> std::string {
    FakeConfig config;
    config.pause_fails = true;
    Handle handle(0, config);
    std::string detail = SpeakOk(handle.h, 1, kShort);
    if (!detail.empty()) return detail;
    handle.fake()->DeliverStarted(1);
    reader_tts_error err{};
    detail = Require(reader_tts_pause(handle.h, 1, &err) == READER_TTS_BUSY, "expected BUSY");
    return Require(State(handle.h) == READER_TTS_SPEAKING, "state changed by a refused pause");
  });

  Case("pause.stale-request-id-argument", [&]() -> std::string {
    Handle handle(0, FakeConfig{});
    std::string detail = SpeakOk(handle.h, 1, kShort);
    if (!detail.empty()) return detail;
    reader_tts_error err{};
    return Require(reader_tts_pause(handle.h, 2, &err) == READER_TTS_ARGUMENT, "expected ARGUMENT");
  });

  Case("stop.backend-declines-finishes-locally", [&]() -> std::string {
    FakeConfig config;
    config.stop_reports = false;
    Handle handle(0, config);
    std::string detail = SpeakOk(handle.h, 1, kShort);
    if (!detail.empty()) return detail;
    handle.fake()->DeliverStarted(1);
    reader_tts_error err{};
    detail = Require(reader_tts_stop(handle.h, 1, &err) == READER_TTS_OK, "stop failed");
    if (!detail.empty()) return detail;
    const std::vector<reader_tts_event> events = Drain(handle.h);
    detail = Require(events.size() == 2 && events.back().kind == READER_TTS_STOPPED, "no STOPPED terminal");
    if (!detail.empty()) return detail;
    return Require(State(handle.h) == READER_TTS_READY, "state is not READY");
  });

  Case("stop.repeat-while-stopping-is-ok", [&]() -> std::string {
    Handle handle(0, FakeConfig{});
    std::string detail = SpeakOk(handle.h, 1, kShort);
    if (!detail.empty()) return detail;
    handle.fake()->DeliverStarted(1);
    reader_tts_error err{};
    detail = Require(reader_tts_stop(handle.h, 1, &err) == READER_TTS_OK, "first stop failed");
    if (!detail.empty()) return detail;
    detail = Require(State(handle.h) == READER_TTS_STOPPING, "state is not STOPPING");
    if (!detail.empty()) return detail;
    detail = Require(reader_tts_stop(handle.h, 1, &err) == READER_TTS_OK, "second stop is not OK");
    handle.fake()->DeliverCancelled(1);
    return detail;
  });

  Case("stop.deadline-resolves-a-silent-backend", [&]() -> std::string {
    Handle handle(0, FakeConfig{});
    std::string detail = SpeakOk(handle.h, 1, kShort);
    if (!detail.empty()) return detail;
    handle.fake()->DeliverStarted(1);
    reader_tts_error err{};
    rtts_test_set_close_deadline_ms(30);
    Need(reader_tts_stop(handle.h, 1, &err) == READER_TTS_OK, "stop");
    std::this_thread::sleep_for(std::chrono::milliseconds(60));
    const reader_tts_state state = State(handle.h);  // observe evaluates the deadline
    rtts_test_set_close_deadline_ms(READER_TTS_CLOSE_DEADLINE_MS);
    detail = Require(state == READER_TTS_READY, "deadline did not finish the request");
    if (!detail.empty()) return detail;
    const std::vector<reader_tts_event> events = Drain(handle.h);
    detail = Require(events.size() == 2 && events.back().kind == READER_TTS_STOPPED, "no STOPPED terminal");
    return detail;
  });

  Case("stop.after-terminal-is-argument", [&]() -> std::string {
    Handle handle(0, FakeConfig{});
    std::string detail = SpeakOk(handle.h, 1, kShort);
    if (!detail.empty()) return detail;
    handle.fake()->DeliverStarted(1);
    handle.fake()->DeliverFinished(1);
    Drain(handle.h);
    reader_tts_error err{};
    return Require(reader_tts_stop(handle.h, 1, &err) == READER_TTS_ARGUMENT, "expected ARGUMENT");
  });

  // ---------- late callbacks ----------
  Case("events.late-callbacks-cannot-pollute-the-next-request", [&]() -> std::string {
    Handle handle(0, FakeConfig{});
    std::string detail = SpeakOk(handle.h, 1, kShort);
    if (!detail.empty()) return detail;
    handle.fake()->DeliverStarted(1);
    handle.fake()->DeliverFinished(1);
    std::vector<reader_tts_event> first = Drain(handle.h);
    detail = EventsAreOrdered(first, 1);
    if (!detail.empty()) return detail;
    detail = SpeakOk(handle.h, 2, "Second request.");
    if (!detail.empty()) return detail;
    // A stale range/finish for request 1 must be ignored completely.
    handle.fake()->DeliverRange(1, 0, 3);
    handle.fake()->DeliverFinished(1);
    handle.fake()->DeliverCancelled(1);
    const std::vector<reader_tts_event> stale = Drain(handle.h);
    detail = Require(stale.empty(), "a stale callback produced an event");
    if (!detail.empty()) return detail;
    detail = Require(State(handle.h) == READER_TTS_SPEAKING, "a stale callback changed the state");
    if (!detail.empty()) return detail;
    handle.fake()->DeliverStarted(2);
    handle.fake()->DeliverRange(2, 0, 6);
    handle.fake()->DeliverFinished(2);
    const std::vector<reader_tts_event> second = Drain(handle.h);
    return EventsAreOrdered(second, 2);
  });

  Case("events.callbacks-from-another-thread", [&]() -> std::string {
    Handle handle(0, FakeConfig{});
    std::string detail = SpeakOk(handle.h, 1, "Threaded delivery.");
    if (!detail.empty()) return detail;
    rtts::test::FakeEngine *fake = handle.fake();
    std::thread worker([fake]() {
      fake->DeliverStarted(1);
      fake->DeliverRange(1, 0, 4);
      fake->DeliverFinished(1);
    });
    worker.join();
    const std::vector<reader_tts_event> events = Drain(handle.h);
    return EventsAreOrdered(events, 1);
  });

  // ---------- queue accounting ----------
  Case("events.queue-exhaustion-is-limit-then-recovers", [&]() -> std::string {
    Handle handle(0, FakeConfig{});
    rtts::test::FakeEngine *fake = handle.fake();
    uint64_t id = 0;
    for (int i = 0; i < 42; ++i) {  // 42 * 3 events = 126 of 128
      id = (uint64_t)i + 1;
      Need(Speak(handle.h, id, kShort) == READER_TTS_OK, "speak");
      fake->DeliverStarted(id);
      fake->DeliverRange(id, 0, 3);
      fake->DeliverFinished(id);
    }
    std::string detail = Require(Speak(handle.h, id + 1, kShort) == READER_TTS_LIMIT,
                                 "a full queue did not return LIMIT");
    if (!detail.empty()) return detail;
    detail = Require(State(handle.h) == READER_TTS_READY, "state changed by a refused speak");
    if (!detail.empty()) return detail;
    const size_t drained = Drain(handle.h).size();
    detail = Require(drained == 126, "unexpected queued event count");
    if (!detail.empty()) return detail;
    return Require(Speak(handle.h, id + 1, kShort) == READER_TTS_OK, "queue did not recover after polling");
  });

  Case("events.terminal-survives-a-racing-range", [&]() -> std::string {
    Handle handle(0, FakeConfig{});
    std::string detail = SpeakOk(handle.h, 1, "abcdef");
    if (!detail.empty()) return detail;
    handle.fake()->DeliverStarted(1);
    handle.fake()->DeliverRange(1, 0, 2);
    handle.fake()->DeliverFinished(1);
    handle.fake()->DeliverRange(1, 2, 2);  // arrives after the terminal
    const std::vector<reader_tts_event> events = Drain(handle.h);
    return EventsAreOrdered(events, 1);
  });

  Case("poll.empty-queue-zeroes-output", [&]() -> std::string {
    Handle handle(0, FakeConfig{});
    reader_tts_event event;
    std::memset(&event, 0xAB, sizeof event);
    int available = 7;
    reader_tts_error err{};
    std::string detail = Require(reader_tts_poll(handle.h, &event, &available, &err) == READER_TTS_OK, "poll failed");
    detail = Require(available == 0, "available is not 0");
    if (!detail.empty()) return detail;
    reader_tts_event zero;
    std::memset(&zero, 0, sizeof zero);
    return Require(std::memcmp(&event, &zero, sizeof event) == 0, "event was not cleared");
  });

  Case("poll.null-arguments", [&]() -> std::string {
    Handle handle(0, FakeConfig{});
    reader_tts_error err{};
    return Require(reader_tts_poll(handle.h, nullptr, nullptr, &err) == READER_TTS_ARGUMENT, "expected ARGUMENT");
  });

  // ---------- voices ----------
  Case("voices.lists-installed-entries", [&]() -> std::string {
    FakeConfig config;
    config.voice_count = 3;
    Handle handle(0, config);
    reader_tts_voice_list list{};
    reader_tts_error err{};
    std::string detail = Require(reader_tts_voices(handle.h, &list, &err) == READER_TTS_OK, "voices failed");
    if (!detail.empty()) return detail;
    detail = Require(list.count == 3, "wrong voice count");
    if (!detail.empty()) return detail;
    detail = Require(list.voices[0].id && std::strcmp(list.voices[0].id, "com.example.voice.0") == 0, "wrong id");
    detail = Require(list.voices[2].language && std::strcmp(list.voices[2].language, "en-US") == 0, "wrong language");
    reader_tts_voice_list_free(&list);
    return Require(list.voices == nullptr && list.count == 0, "free did not reset the list");
  });

  Case("voices.over-maximum-is-limit", [&]() -> std::string {
    FakeConfig config;
    config.voice_count = READER_TTS_MAX_VOICES + 1;
    Handle handle(0, config);
    reader_tts_voice_list list{};
    reader_tts_error err{};
    std::string detail = Require(reader_tts_voices(handle.h, &list, &err) == READER_TTS_LIMIT, "expected LIMIT");
    if (!detail.empty()) return detail;
    return Require(list.voices == nullptr && list.count == 0, "a failed call published a list");
  });

  Case("voices.empty-list-is-ok", [&]() -> std::string {
    FakeConfig config;
    config.voice_count = 0;
    Handle handle(0, config);
    reader_tts_voice_list list{};
    reader_tts_error err{};
    std::string detail = Require(reader_tts_voices(handle.h, &list, &err) == READER_TTS_OK, "expected OK");
    if (!detail.empty()) return detail;
    return Require(list.voices == nullptr && list.count == 0, "expected an empty list");
  });

  Case("voices.engine-failure-is-unavailable", [&]() -> std::string {
    FakeConfig config;
    config.voices_fail = true;
    Handle handle(0, config);
    reader_tts_voice_list list{};
    reader_tts_error err{};
    return Require(reader_tts_voices(handle.h, &list, &err) == READER_TTS_UNAVAILABLE && list.count == 0,
                   "expected UNAVAILABLE");
  });

  Case("voices.null-list-argument", [&]() -> std::string {
    Handle handle(0, FakeConfig{});
    reader_tts_error err{};
    return Require(reader_tts_voices(handle.h, nullptr, &err) == READER_TTS_ARGUMENT, "expected ARGUMENT");
  });

  Case("voices.free-is-independent-of-the-handle", [&]() -> std::string {
    Handle handle(0, FakeConfig{});
    reader_tts_voice_list list{};
    reader_tts_error err{};
    Need(reader_tts_voices(handle.h, &list, &err) == READER_TTS_OK, "voices");
    handle.Dispose();
    reader_tts_voice_list_free(&list);  // must not touch the freed handle
    reader_tts_voice_list_free(nullptr);
    return {};
  });

  // ---------- ownership ----------
  Case("owner.observe-from-another-thread", [&]() -> std::string {
    Handle handle(0, FakeConfig{});
    std::atomic<int> status{-1};
    std::thread worker([&]() {
      reader_tts_snapshot snap{};
      reader_tts_error err{};
      status.store((int)reader_tts_observe(handle.h, &snap, &err));
    });
    worker.join();
    return Require(status.load() == (int)READER_TTS_OWNER, "expected OWNER");
  });

  Case("owner.speak-from-another-thread-leaves-state", [&]() -> std::string {
    Handle handle(0, FakeConfig{});
    std::string detail = SpeakOk(handle.h, 1, kShort);
    if (!detail.empty()) return detail;
    handle.fake()->DeliverStarted(1);
    std::atomic<int> status{-1};
    std::thread worker([&]() {
      reader_tts_error err{};
      status.store((int)reader_tts_speak(handle.h, 2, kShort, std::strlen(kShort), nullptr, 1.0, &err));
    });
    worker.join();
    detail = Require(status.load() == (int)READER_TTS_OWNER, "expected OWNER");
    if (!detail.empty()) return detail;
    detail = Require(State(handle.h) == READER_TTS_SPEAKING, "state changed by a foreign call");
    if (!detail.empty()) return detail;
    return Require(Drain(handle.h).size() == 1, "a foreign call produced events");
  });

  Case("owner.destroy-from-another-thread-keeps-the-handle", [&]() -> std::string {
    Handle handle(0, FakeConfig{});
    std::atomic<int> status{-1};
    reader_tts *pointer = handle.h;
    std::thread worker([&]() {
      reader_tts_error err{};
      status.store((int)reader_tts_destroy(&pointer, &err));
    });
    worker.join();
    std::string detail = Require(status.load() == (int)READER_TTS_OWNER, "expected OWNER");
    if (!detail.empty()) return detail;
    return Require(pointer == handle.h && handle.h != nullptr, "handle was released by a foreign destroy");
  });

  Case("owner.destroy-null-pointer-is-ok", [&]() -> std::string {
    reader_tts *null_handle = nullptr;
    reader_tts_error err{};
    return Require(reader_tts_destroy(&null_handle, &err) == READER_TTS_OK, "expected OK");
  });

  // ---------- close / destroy ----------
  Case("close.without-an-active-request", [&]() -> std::string {
    Handle handle(0, FakeConfig{});
    reader_tts_error err{};
    std::string detail = Require(reader_tts_request_close(handle.h, &err) == READER_TTS_OK, "close failed");
    if (!detail.empty()) return detail;
    detail = Require(State(handle.h) == READER_TTS_CLOSED, "state is not CLOSED");
    if (!detail.empty()) return detail;
    detail = Require(reader_tts_request_close(handle.h, &err) == READER_TTS_OK, "second close is not OK");
    if (!detail.empty()) return detail;
    detail = Require(handle.fake()->detach_calls == 1, "engine detach was not called exactly once");
    return detail;
  });

  Case("close.retains-the-terminal-event", [&]() -> std::string {
    Handle handle(0, FakeConfig{});
    std::string detail = SpeakOk(handle.h, 1, kShort);
    if (!detail.empty()) return detail;
    handle.fake()->DeliverStarted(1);
    rtts::test::FakeEngine *fake = handle.fake();
    reader_tts_error err{};
    Need(reader_tts_request_close(handle.h, &err) == READER_TTS_OK, "close");
    detail = Require(State(handle.h) == READER_TTS_CLOSING, "state is not CLOSING");
    if (!detail.empty()) return detail;
    fake->DeliverCancelled(1);
    detail = Require(State(handle.h) == READER_TTS_CLOSED, "state is not CLOSED after the cancel");
    if (!detail.empty()) return detail;
    const std::vector<reader_tts_event> events = Drain(handle.h);
    detail = Require(events.size() == 2 && events.back().kind == READER_TTS_STOPPED, "terminal event lost");
    if (!detail.empty()) return detail;
    detail = Require(reader_tts_voices(handle.h, nullptr, &err) == READER_TTS_ARGUMENT, "argument check skipped");
    reader_tts_voice_list list{};
    return Require(reader_tts_voices(handle.h, &list, &err) == READER_TTS_UNAVAILABLE, "voices after close");
  });

  Case("close.deadline-closes-a-silent-backend", [&]() -> std::string {
    Handle handle(0, FakeConfig{});
    std::string detail = SpeakOk(handle.h, 1, kShort);
    if (!detail.empty()) return detail;
    handle.fake()->DeliverStarted(1);
    reader_tts_error err{};
    rtts_test_set_close_deadline_ms(20);
    Need(reader_tts_request_close(handle.h, &err) == READER_TTS_OK, "close");
    std::this_thread::sleep_for(std::chrono::milliseconds(50));
    const reader_tts_state state = State(handle.h);
    rtts_test_set_close_deadline_ms(READER_TTS_CLOSE_DEADLINE_MS);
    detail = Require(state == READER_TTS_CLOSED, "deadline did not close the handle");
    if (!detail.empty()) return detail;
    const std::vector<reader_tts_event> events = Drain(handle.h);
    return Require(events.size() == 2 && events.back().kind == READER_TTS_STOPPED, "STOPPED not retained");
  });

  Case("destroy.before-closed-is-busy", [&]() -> std::string {
    reader_tts *handle_pointer = nullptr;
    rtts::test::Configure(FakeConfig{});
    reader_tts_config cfg{};
    cfg.struct_size = sizeof cfg;
    reader_tts_error err{};
    Need(reader_tts_create(&cfg, &handle_pointer, &err) == READER_TTS_OK, "create");
    std::string detail = Require(reader_tts_destroy(&handle_pointer, &err) == READER_TTS_BUSY, "expected BUSY");
    if (!detail.empty()) return detail;
    detail = Require(handle_pointer != nullptr, "handle was cleared by a BUSY destroy");
    Need(reader_tts_request_close(handle_pointer, &err) == READER_TTS_OK, "close");
    return Require(reader_tts_destroy(&handle_pointer, &err) == READER_TTS_OK && handle_pointer == nullptr, "destroy");
  });

  Case("destroy.after-closed-clears-the-pointer", [&]() -> std::string {
    reader_tts *handle_pointer = nullptr;
    rtts::test::Configure(FakeConfig{});
    reader_tts_config cfg{};
    cfg.struct_size = sizeof cfg;
    reader_tts_error err{};
    Need(reader_tts_create(&cfg, &handle_pointer, &err) == READER_TTS_OK, "create");
    Need(reader_tts_request_close(handle_pointer, &err) == READER_TTS_OK, "close");
    std::string detail = Require(reader_tts_destroy(&handle_pointer, &err) == READER_TTS_OK, "destroy failed");
    if (!detail.empty()) return detail;
    return Require(handle_pointer == nullptr, "pointer was not cleared");
  });

  Case("destroy.null-argument", [&]() -> std::string {
    reader_tts_error err{};
    return Require(reader_tts_destroy(nullptr, &err) == READER_TTS_ARGUMENT, "expected ARGUMENT");
  });

  Case("speak.after-close-is-unavailable", [&]() -> std::string {
    Handle handle(0, FakeConfig{});
    reader_tts_error err{};
    Need(reader_tts_request_close(handle.h, &err) == READER_TTS_OK, "close");
    const reader_tts_status status = Speak(handle.h, 1, kShort);
    std::string detail = Require(status == READER_TTS_UNAVAILABLE, "expected UNAVAILABLE");
    return Require(Drain(handle.h).empty(), "a closed handle emitted an event");
  });

  Case("close.while-speaking-stops-then-closes", [&]() -> std::string {
    FakeConfig config;
    config.stop_cancels_inline = true;
    Handle handle(0, config);
    std::string detail = SpeakOk(handle.h, 1, kShort);
    if (!detail.empty()) return detail;
    handle.fake()->DeliverStarted(1);
    reader_tts_error err{};
    detail = Require(reader_tts_request_close(handle.h, &err) == READER_TTS_OK, "close failed");
    if (!detail.empty()) return detail;
    detail = Require(State(handle.h) == READER_TTS_CLOSED, "inline cancel did not close the handle");
    if (!detail.empty()) return detail;
    const std::vector<reader_tts_event> events = Drain(handle.h);
    return Require(events.size() == 2 && events.back().kind == READER_TTS_STOPPED, "terminal event lost");
  });

  // ---------- observe ----------
  Case("observe.reports-the-highest-accepted-request", [&]() -> std::string {
    Handle handle(0, FakeConfig{});
    std::string detail = SpeakOk(handle.h, 5, kShort);
    if (!detail.empty()) return detail;
    handle.fake()->DeliverStarted(5);
    handle.fake()->DeliverFinished(5);
    Drain(handle.h);
    reader_tts_snapshot snap{};
    reader_tts_error err{};
    Need(reader_tts_observe(handle.h, &snap, &err) == READER_TTS_OK, "observe");
    detail = Require(snap.request_id == 5, "request_id is not the last accepted request");
    if (!detail.empty()) return detail;
    detail = Require(snap.capabilities == (READER_TTS_CAN_PAUSE | READER_TTS_CAN_REPORT_RANGE),
                     "capabilities wrong");
    if (!detail.empty()) return detail;
    return Require(snap.state == READER_TTS_READY && snap.last_status == READER_TTS_OK, "state/last_status wrong");
  });

  Case("observe.null-snapshot-argument", [&]() -> std::string {
    Handle handle(0, FakeConfig{});
    reader_tts_error err{};
    return Require(reader_tts_observe(handle.h, nullptr, &err) == READER_TTS_ARGUMENT, "expected ARGUMENT");
  });

  Case("observe.null-handle-argument", [&]() -> std::string {
    reader_tts_snapshot snap{};
    reader_tts_error err{};
    return Require(reader_tts_observe(nullptr, &snap, &err) == READER_TTS_ARGUMENT, "expected ARGUMENT");
  });

  // ---------- allocation failures ----------
  Case("memory.create-fails-cleanly", [&]() -> std::string {
    for (int n = 1; n <= 4; ++n) {
      rtts::test::Configure(FakeConfig{});
      rtts_test_fail_alloc_after(n);
      reader_tts_config cfg{};
      cfg.struct_size = sizeof cfg;
      reader_tts *handle_pointer = reinterpret_cast<reader_tts *>(0x1);
      reader_tts_error err{};
      const reader_tts_status status = reader_tts_create(&cfg, &handle_pointer, &err);
      rtts_test_fail_alloc_after(0);
      if (status != READER_TTS_MEMORY && status != READER_TTS_OK) return "unexpected status";
      if (status == READER_TTS_MEMORY) {
        if (handle_pointer != nullptr) return "failed create published a handle";
      } else {
        reader_tts_request_close(handle_pointer, &err);
        rtts_test_set_close_deadline_ms(0);
        reader_tts_snapshot snap{};
        reader_tts_observe(handle_pointer, &snap, &err);
        rtts_test_set_close_deadline_ms(READER_TTS_CLOSE_DEADLINE_MS);
        reader_tts_destroy(&handle_pointer, &err);
      }
    }
    return {};
  });

  Case("memory.speak-fails-without-state-change", [&]() -> std::string {
    Handle handle(0, FakeConfig{});
    reader_tts_error err{};
    rtts_test_fail_alloc_after(2);  // the text copy point
    const reader_tts_status status = reader_tts_speak(handle.h, 1, kShort, std::strlen(kShort), nullptr, 1.0, &err);
    rtts_test_fail_alloc_after(0);
    std::string detail = Require(status == READER_TTS_MEMORY || status == READER_TTS_OK, "unexpected status");
    if (!detail.empty()) return detail;
    if (status == READER_TTS_MEMORY) {
      detail = Require(State(handle.h) == READER_TTS_READY, "state changed by a failed speak");
      if (!detail.empty()) return detail;
      detail = Require(Drain(handle.h).empty(), "events emitted by a failed speak");
      if (!detail.empty()) return detail;
      return Require(Speak(handle.h, 1, kShort) == READER_TTS_OK, "id consumed by a failed speak");
    }
    return {};
  });

  Case("memory.voices-fails-without-a-list", [&]() -> std::string {
    FakeConfig config;
    config.voice_count = 4;
    Handle handle(0, config);
    reader_tts_voice_list list{};
    reader_tts_error err{};
    rtts_test_fail_alloc_after(2);
    const reader_tts_status status = reader_tts_voices(handle.h, &list, &err);
    rtts_test_fail_alloc_after(0);
    std::string detail = Require(status == READER_TTS_MEMORY || status == READER_TTS_OK, "unexpected status");
    if (!detail.empty()) return detail;
    if (status == READER_TTS_MEMORY) {
      return Require(list.voices == nullptr && list.count == 0, "failed voices published a list");
    }
    reader_tts_voice_list_free(&list);
    return {};
  });

  std::printf("\nTOTAL pass=%d fail=%d\n", g_pass, g_fail);
  std::printf("RESULT_JSON_BEGIN\n");
  std::printf("{\n  \"suite\": \"reader-tts-apple-logic\",\n  \"checks\": [\n");
  for (size_t i = 0; i < g_outcomes.size(); ++i) {
    const Outcome &outcome = g_outcomes[i];
    std::printf("    {\"name\": \"%s\", \"status\": \"%s\", \"detail\": \"%s\"}%s\n", outcome.name.c_str(),
                outcome.status.c_str(), outcome.detail.c_str(), i + 1 == g_outcomes.size() ? "" : ",");
  }
  std::printf("  ],\n  \"counts\": {\"pass\": %d, \"fail\": %d}\n}\n", g_pass, g_fail);
  std::printf("RESULT_JSON_END\n");
  std::fflush(stdout);
  return g_fail == 0 ? 0 : 1;
}
