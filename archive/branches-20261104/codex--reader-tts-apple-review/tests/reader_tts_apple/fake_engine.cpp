// SPDX-License-Identifier: MIT
#include "fake_engine.hpp"

#include <pthread.h>

#include <cstring>

namespace rtts {
namespace test {
namespace {

FakeConfig g_config;
FakeEngine *g_instance = nullptr;
pthread_t g_creator;

}  // namespace

void Configure(const FakeConfig &config) {
  g_config = config;
  g_creator = pthread_self();
}

FakeConfig CurrentConfig() { return g_config; }
FakeEngine *Instance() { return g_instance; }
void ClearInstance() { g_instance = nullptr; }

FakeEngine::FakeEngine(Sink *sink, const FakeConfig &config) : sink_(sink), config_(config) {}

FakeEngine::~FakeEngine() {
  if (g_instance == this) g_instance = nullptr;
}

unsigned FakeEngine::capabilities() {
  unsigned caps = 0;
  if (config_.pause_supported) caps |= READER_TTS_CAN_PAUSE;
  if (config_.range_supported) caps |= READER_TTS_CAN_REPORT_RANGE;
  return caps;
}

bool FakeEngine::voices(std::vector<VoiceInfo> *out) {
  if (!out) return false;
  if (config_.voices_fail) return false;
  for (size_t i = 0; i < config_.voice_count; ++i) {
    VoiceInfo info;
    info.id = "com.example.voice." + std::to_string(i);
    info.name = "Voice " + std::to_string(i);
    info.language = i % 2 ? "zh-CN" : "en-US";
    out->push_back(info);
  }
  return true;
}

bool FakeEngine::voice_exists(const std::string &id) {
  return config_.voice_known && !id.empty();
}

bool FakeEngine::speak(uint64_t request_id, const std::string &utf8, const std::string &voice, double rate,
                       int *native) {
  last_speak.called = true;
  last_speak.request_id = request_id;
  last_speak.text = utf8;
  last_speak.voice = voice;
  last_speak.rate = rate;
  if (config_.speak_fails) {
    if (native) *native = config_.speak_native;
    return false;
  }
  if (config_.speak_starts_inline) DeliverStarted(request_id);
  if (config_.speak_cancels_inline) DeliverCancelled(request_id);
  return true;
}

bool FakeEngine::pause(int *native) {
  if (config_.pause_fails) {
    if (native) *native = 7;
    return false;
  }
  return true;
}

bool FakeEngine::resume(int *native) {
  if (config_.resume_fails) {
    if (native) *native = 8;
    return false;
  }
  return true;
}

bool FakeEngine::stop() {
  ++stop_calls;
  if (!config_.stop_reports) return false;
  if (config_.stop_cancels_inline) DeliverCancelled(last_speak.request_id);
  return true;
}

void FakeEngine::detach() {
  if (detached_.exchange(true)) return;
  ++detach_calls;
  sink_.store(nullptr);
}

void FakeEngine::DeliverStarted(uint64_t request_id) {
  Sink *sink = SinkPtr();
  if (sink) sink->started(request_id);
}

void FakeEngine::DeliverRange(uint64_t request_id, size_t location, size_t length) {
  Sink *sink = SinkPtr();
  if (sink) sink->range16(request_id, location, length);
}

void FakeEngine::DeliverPaused(uint64_t request_id) {
  Sink *sink = SinkPtr();
  if (sink) sink->paused(request_id);
}

void FakeEngine::DeliverResumed(uint64_t request_id) {
  Sink *sink = SinkPtr();
  if (sink) sink->resumed(request_id);
}

void FakeEngine::DeliverFinished(uint64_t request_id) {
  Sink *sink = SinkPtr();
  if (sink) sink->finished(request_id);
}

void FakeEngine::DeliverCancelled(uint64_t request_id) {
  Sink *sink = SinkPtr();
  if (sink) sink->cancelled(request_id);
}

void FakeEngine::DeliverFailed(uint64_t request_id, int native_code) {
  Sink *sink = SinkPtr();
  if (sink) sink->failed(request_id, native_code);
}

}  // namespace test

std::unique_ptr<Engine> make_platform_engine(Sink *sink, reader_tts_status *status, int *native) {
  if (native) *native = 0;
  if (!sink) {
    if (status) *status = READER_TTS_ARGUMENT;
    return nullptr;
  }
  if (test::g_config.require_main_thread && !pthread_equal(test::g_creator, pthread_self())) {
    if (status) *status = READER_TTS_OWNER;
    if (native) *native = 1001;
    return nullptr;
  }
  std::unique_ptr<Engine> engine(new test::FakeEngine(sink, test::g_config));
  test::g_instance = static_cast<test::FakeEngine *>(engine.get());
  if (status) *status = READER_TTS_OK;
  return engine;
}

}  // namespace rtts
