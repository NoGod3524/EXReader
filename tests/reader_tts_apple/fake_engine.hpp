// SPDX-License-Identifier: MIT
// Deterministic Engine stand-in for the platform-neutral logic suite. Never
// installed: it is compiled only into the -DREADER_TTS_TESTING logic binary.
#pragma once
#include "engine.hpp"

#include <atomic>
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace rtts {
namespace test {

struct FakeConfig {
  bool available = true;               // at least one installed voice
  bool voice_known = true;             // voice_exists() answer
  bool pause_supported = true;         // READER_TTS_CAN_PAUSE bit
  bool range_supported = true;         // READER_TTS_CAN_REPORT_RANGE bit
  bool require_main_thread = false;    // make_platform_engine returns OWNER elsewhere
  bool speak_fails = false;            // speak() refuses with speak_native
  int speak_native = 0;
  bool pause_fails = false;
  bool resume_fails = false;
  bool stop_reports = true;            // stop() true -> caller expects cancelled()
  bool stop_cancels_inline = false;    // cancelled() delivered inside stop()
  bool speak_starts_inline = false;    // started() delivered inside speak()
  bool speak_cancels_inline = false;   // cancelled() delivered inside speak()
  bool voices_fail = false;
  size_t voice_count = 2;
};

class FakeEngine : public Engine {
 public:
  FakeEngine(Sink *sink, const FakeConfig &config);
  ~FakeEngine() override;

  bool available() override { return config_.available; }
  unsigned capabilities() override;
  bool voices(std::vector<VoiceInfo> *out) override;
  bool voice_exists(const std::string &id) override;
  bool speak(uint64_t request_id, const std::string &utf8, const std::string &voice, double rate,
             int *native) override;
  bool pause(int *native) override;
  bool resume(int *native) override;
  bool stop() override;
  void detach() override;

  // Drivers used by the suite. They are the "system" and may be called from any
  // thread, including while a core call is still on the stack.
  void DeliverStarted(uint64_t request_id);
  void DeliverRange(uint64_t request_id, size_t location, size_t length);
  void DeliverPaused(uint64_t request_id);
  void DeliverResumed(uint64_t request_id);
  void DeliverFinished(uint64_t request_id);
  void DeliverCancelled(uint64_t request_id);
  void DeliverFailed(uint64_t request_id, int native_code);

  struct LastSpeak {
    bool called = false;
    uint64_t request_id = 0;
    std::string text;
    std::string voice;
    double rate = 0.0;
  } last_speak;
  int stop_calls = 0;
  int detach_calls = 0;
  int detach_after_last_call = 0;

 private:
  Sink *SinkPtr() const { return sink_.load(); }

  Sink *raw_sink_;  // for identity only; never dereferenced after detach
  std::atomic<Sink *> sink_;
  std::atomic<bool> detached_{false};
  FakeConfig config_;
};

void Configure(const FakeConfig &config);
FakeConfig CurrentConfig();
FakeEngine *Instance();
void ClearInstance();

}  // namespace test
}  // namespace rtts
