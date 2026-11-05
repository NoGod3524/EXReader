// SPDX-License-Identifier: MIT
// AVFoundation backend: one AVSpeechSynthesizer driven from the main thread.
// The synthesizer is created on the main thread, every control call is made on
// the main thread, and the delegate only ever appends plain values to the core's
// bounded queue. No AVAudioSession is configured, no voice is downloaded, no
// network is used.
#include "engine.hpp"

#import <AVFoundation/AVFoundation.h>
#import <Foundation/Foundation.h>

#include <atomic>

namespace {

constexpr int kNativeWrongThread = 1001;
constexpr int kNativeUnknownVoice = 1002;
constexpr int kNativeUnusable = 1003;
constexpr int kNativeSystemRefused = 1004;

// Documented, approximate mapping (see reader_tts.h): the ABI range 0.5..2.0 is
// relative, AVFoundation's own range is 0.0..1.0 around a 0.5 default.
double MapRate(double rate) noexcept {
  if (rate <= 1.0) return 0.25 + (rate - 0.5) * 0.5;
  return 0.5 + (rate - 1.0) * 0.25;
}

std::string ToStd(NSString *value) {
  if (!value) return std::string();
  const char *bytes = [value UTF8String];
  return bytes ? std::string(bytes) : std::string();
}

}  // namespace

// Callback gate: the atomic pointer is the only thing a delegate method reads
// before forwarding, so detach() can silence every callback synchronously from
// any thread while the native teardown finishes on the main queue.
@interface RTTSDelegate : NSObject <AVSpeechSynthesizerDelegate>
- (instancetype)initWithSink:(rtts::Sink *)sink;
- (void)silence;
- (void)remember:(AVSpeechUtterance *)utterance requestId:(uint64_t)requestId;
- (void)forgetAll;
- (uint64_t)requestIdFor:(AVSpeechUtterance *)utterance found:(BOOL *)found;
- (NSMapTable<AVSpeechUtterance *, NSNumber *> *)ids;
@end

@implementation RTTSDelegate {
  std::atomic<rtts::Sink *> _sink;
  NSMapTable<AVSpeechUtterance *, NSNumber *> *_ids;
}

- (instancetype)initWithSink:(rtts::Sink *)sink {
  self = [super init];
  if (self) {
    _sink.store(sink);
    _ids = [NSMapTable weakToStrongObjectsMapTable];
  }
  return self;
}

- (void)silence { _sink.store(nullptr); }
- (NSMapTable<AVSpeechUtterance *, NSNumber *> *)ids { return _ids; }

- (void)remember:(AVSpeechUtterance *)utterance requestId:(uint64_t)requestId {
  if (!utterance) return;
  @synchronized(self) { [_ids setObject:@(requestId) forKey:utterance]; }
}

- (void)forgetAll {
  @synchronized(self) { [_ids removeAllObjects]; }
}

- (uint64_t)requestIdFor:(AVSpeechUtterance *)utterance found:(BOOL *)found {
  if (!utterance) { if (found) *found = NO; return 0; }
  NSNumber *value = nil;
  @synchronized(self) { value = [_ids objectForKey:utterance]; }
  if (found) *found = value != nil;
  return value ? value.unsignedLongLongValue : 0;
}

- (void)speechSynthesizer:(AVSpeechSynthesizer *)synthesizer
    didStartSpeechUtterance:(AVSpeechUtterance *)utterance {
  (void)synthesizer;
  BOOL found = NO;
  const uint64_t requestId = [self requestIdFor:utterance found:&found];
  rtts::Sink *sink = _sink.load();
  if (found && sink) sink->started(requestId);
}

- (void)speechSynthesizer:(AVSpeechSynthesizer *)synthesizer
    willSpeakRangeOfSpeechString:(NSRange)characterRange
                       utterance:(AVSpeechUtterance *)utterance {
  (void)synthesizer;
  BOOL found = NO;
  const uint64_t requestId = [self requestIdFor:utterance found:&found];
  rtts::Sink *sink = _sink.load();
  // UTF-16 units, exactly as the system reports them; the core converts to the
  // UTF-8 byte boundaries of its own copy of the input.
  if (found && sink) sink->range16(requestId, (size_t)characterRange.location, (size_t)characterRange.length);
}

- (void)speechSynthesizer:(AVSpeechSynthesizer *)synthesizer
    didPauseSpeechUtterance:(AVSpeechUtterance *)utterance {
  (void)synthesizer;
  BOOL found = NO;
  const uint64_t requestId = [self requestIdFor:utterance found:&found];
  rtts::Sink *sink = _sink.load();
  if (found && sink) sink->paused(requestId);
}

- (void)speechSynthesizer:(AVSpeechSynthesizer *)synthesizer
    didContinueSpeechUtterance:(AVSpeechUtterance *)utterance {
  (void)synthesizer;
  BOOL found = NO;
  const uint64_t requestId = [self requestIdFor:utterance found:&found];
  rtts::Sink *sink = _sink.load();
  if (found && sink) sink->resumed(requestId);
}

- (void)speechSynthesizer:(AVSpeechSynthesizer *)synthesizer
    didFinishSpeechUtterance:(AVSpeechUtterance *)utterance {
  (void)synthesizer;
  BOOL found = NO;
  const uint64_t requestId = [self requestIdFor:utterance found:&found];
  rtts::Sink *sink = _sink.load();
  if (found && sink) sink->finished(requestId);
}

- (void)speechSynthesizer:(AVSpeechSynthesizer *)synthesizer
    didCancelSpeechUtterance:(AVSpeechUtterance *)utterance {
  (void)synthesizer;
  BOOL found = NO;
  const uint64_t requestId = [self requestIdFor:utterance found:&found];
  rtts::Sink *sink = _sink.load();
  if (found && sink) sink->cancelled(requestId);
}

@end

namespace {

class AppleEngine final : public rtts::Engine {
 public:
  explicit AppleEngine(rtts::Sink *sink) {
    @autoreleasepool {
      delegate_ = [[RTTSDelegate alloc] initWithSink:sink];
      synthesizer_ = [[AVSpeechSynthesizer alloc] init];
      synthesizer_.delegate = delegate_;
    }
  }

  ~AppleEngine() override { detach(); }

  bool available() override {
    @autoreleasepool { return [AVSpeechSynthesisVoice speechVoices].count > 0; }
  }

  unsigned capabilities() override {
    // AVSpeechSynthesizer reports spoken ranges and can pause/continue. Both
    // bits are only claimed because the calls below exist and are exercised by
    // the installed probe.
    return READER_TTS_CAN_PAUSE | READER_TTS_CAN_REPORT_RANGE;
  }

  bool voices(std::vector<rtts::VoiceInfo> *out) override {
    if (!out) return false;
    @autoreleasepool {
      NSArray<AVSpeechSynthesisVoice *> *installed = [AVSpeechSynthesisVoice speechVoices];
      for (AVSpeechSynthesisVoice *voice in installed) {
        if (out->size() >= READER_TTS_MAX_VOICES) break;
        rtts::VoiceInfo info;
        info.id = ToStd(voice.identifier);
        info.name = ToStd(voice.name);
        info.language = ToStd(voice.language);
        if (info.id.empty()) continue;
        out->push_back(std::move(info));
      }
    }
    return true;
  }

  bool voice_exists(const std::string &id) override {
    @autoreleasepool {
      NSString *identifier = [NSString stringWithUTF8String:id.c_str()];
      if (!identifier) return false;
      return ResolveVoice(identifier) != nil;
    }
  }

  bool speak(uint64_t request_id, const std::string &utf8, const std::string &voice, double rate,
             int *native) override {
    if (!MainThread(native)) return false;
    @autoreleasepool {
      NSString *text = [NSString stringWithUTF8String:utf8.c_str()];
      if (!text) {
        if (native) *native = kNativeUnusable;
        return false;
      }
      AVSpeechUtterance *utterance = [AVSpeechUtterance speechUtteranceWithString:text];
      if (!voice.empty()) {
        NSString *identifier = [NSString stringWithUTF8String:voice.c_str()];
        AVSpeechSynthesisVoice *chosen = identifier ? ResolveVoice(identifier) : nil;
        if (!chosen) {
          if (native) *native = kNativeUnknownVoice;
          return false;
        }
        utterance.voice = chosen;
      }
      utterance.rate = (float)MapRate(rate);
      [delegate_ remember:utterance requestId:request_id];
      [synthesizer_ speakUtterance:utterance];
      // speakUtterance: has no error return; a refusal arrives as a cancel
      // callback (which the core already handles re-entrantly) or as a stall the
      // host resolves with stop/request_close.
      return true;
    }
  }

  bool pause(int *native) override {
    if (!MainThread(native)) return false;
    @autoreleasepool {
      if (!synthesizer_.isSpeaking) {
        if (native) *native = kNativeSystemRefused;
        return false;
      }
      return [synthesizer_ pauseSpeakingAtBoundary:AVSpeechBoundaryWord] == YES;
    }
  }

  bool resume(int *native) override {
    if (!MainThread(native)) return false;
    @autoreleasepool {
      if (!synthesizer_.isPaused) {
        if (native) *native = kNativeSystemRefused;
        return false;
      }
      return [synthesizer_ continueSpeaking] == YES;
    }
  }

  bool stop() override {
    if (![NSThread isMainThread]) return false;
    @autoreleasepool {
      if (!synthesizer_.isSpeaking && !synthesizer_.isPaused) return false;
      return [synthesizer_ stopSpeakingAtBoundary:AVSpeechBoundaryImmediate] == YES;
    }
  }

  void detach() override {
    bool expected = false;
    if (!detached_.compare_exchange_strong(expected, true)) return;
    AVSpeechSynthesizer *synthesizer = synthesizer_;
    RTTSDelegate *delegate = delegate_;
    synthesizer_ = nil;
    delegate_ = nil;
    if (delegate) [delegate silence];  // no sink call can run after this line
    void (^teardown)(void) = ^{
      if (synthesizer) {
        synthesizer.delegate = nil;
        if (synthesizer.isSpeaking || synthesizer.isPaused) {
          [synthesizer stopSpeakingAtBoundary:AVSpeechBoundaryImmediate];
        }
      }
      if (delegate) [delegate forgetAll];
    };
    if ([NSThread isMainThread]) {
      teardown();
    } else {
      // Only reachable from a system callback while CLOSING; the gate above has
      // already stopped delivery, the remaining AVFoundation work runs on main.
      dispatch_async(dispatch_get_main_queue(), teardown);
    }
  }

 private:
  // The system may answer an unknown identifier with a placeholder voice, so an
  // installed voice is only accepted when its own identifier matches the request
  // exactly. Loading the identifier list is also what makes this independent of
  // any private voice cache.
  AVSpeechSynthesisVoice *ResolveVoice(NSString *identifier) {
    if (!identifier) return nil;
    NSArray<AVSpeechSynthesisVoice *> *installed = [AVSpeechSynthesisVoice speechVoices];
    for (AVSpeechSynthesisVoice *voice in installed) {
      if ([voice.identifier isEqualToString:identifier]) return voice;
    }
    return nil;
  }

  bool MainThread(int *native) {
    if ([NSThread isMainThread]) return true;
    if (native) *native = kNativeWrongThread;
    return false;
  }

  AVSpeechSynthesizer *synthesizer_ = nil;
  RTTSDelegate *delegate_ = nil;
  std::atomic<bool> detached_{false};
};

}  // namespace

namespace rtts {

std::unique_ptr<Engine> make_platform_engine(Sink *sink, reader_tts_status *status, int *native) {
  if (native) *native = 0;
  if (!sink) {
    if (status) *status = READER_TTS_ARGUMENT;
    return nullptr;
  }
  if (![NSThread isMainThread]) {
    if (status) *status = READER_TTS_OWNER;
    if (native) *native = kNativeWrongThread;
    return nullptr;
  }
  std::unique_ptr<Engine> engine(new AppleEngine(sink));  // bad_alloc -> core MEMORY
  if (status) *status = READER_TTS_OK;
  return engine;
}

}  // namespace rtts
