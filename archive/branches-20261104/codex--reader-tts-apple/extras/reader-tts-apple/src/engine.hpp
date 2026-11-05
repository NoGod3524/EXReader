// SPDX-License-Identifier: MIT
// Internal seam between the platform-neutral request state machine (core.cpp)
// and the native speech backend (apple_engine.mm). Not installed.
#pragma once
#include "reader_tts.h"
#include <memory>
#include <string>
#include <vector>

namespace rtts {

struct VoiceInfo { std::string id, name, language; };

// Callbacks from the system. They may arrive on any thread and re-entrantly
// from inside an Engine call (AVSpeechSynthesizer can deliver a cancel while
// stopSpeakingAtBoundary: runs); the implementation locks internally and never
// calls the host.
class Sink {
 public:
  virtual ~Sink() {}
  virtual void started(uint64_t id) = 0;
  virtual void range16(uint64_t id, size_t location, size_t length) = 0;  // UTF-16 units
  virtual void paused(uint64_t id) = 0;
  virtual void resumed(uint64_t id) = 0;
  virtual void finished(uint64_t id) = 0;
  virtual void cancelled(uint64_t id) = 0;
  virtual void failed(uint64_t id, int native_code) = 0;
};

class Engine {
 public:
  virtual ~Engine() {}
  virtual bool available() = 0;           // at least one installed voice
  virtual unsigned capabilities() = 0;    // READER_TTS_CAN_*
  virtual bool voices(std::vector<VoiceInfo> *out) = 0;  // at most READER_TTS_MAX_VOICES
  virtual bool voice_exists(const std::string &id) = 0;
  // Starts the utterance. false: refused, *native filled.
  virtual bool speak(uint64_t id, const std::string &utf8, const std::string &voice, double rate, int *native) = 0;
  virtual bool pause(int *native) = 0;    // false: the system refused
  virtual bool resume(int *native) = 0;
  // true: the system had something to cancel and will report cancelled().
  // false: nothing was cancellable, the caller finishes the request itself.
  virtual bool stop() = 0;
  // Stops delivering callbacks and releases system resources. Idempotent. After
  // it returns no sink call can still run: the backend closes its callback gate
  // synchronously even when the remaining native teardown is queued.
  virtual void detach() = 0;
};

// Supplied by the Apple backend, or by the test fake. Returns NULL with *status
// (OWNER when the thread is not allowed to drive the backend, MEMORY, IO).
std::unique_ptr<Engine> make_platform_engine(Sink *sink, reader_tts_status *status, int *native);

}  // namespace rtts

#ifdef READER_TTS_TESTING
// Test-only hooks compiled into the logic suite, never into the installed
// library: fail the n-th allocation point once, and shorten both deadlines so a
// test does not wait two real seconds.
extern "C" {
void rtts_test_fail_alloc_after(int n);
void rtts_test_set_close_deadline_ms(int ms);
}
#endif
