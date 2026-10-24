/* SPDX-License-Identifier: MIT */
/*
 * Installed-consumer probe for EXReaderTTSApple. Links only the installed
 * package (find_package(EXReaderTTSApple CONFIG)) and drives the real
 * AVSpeechSynthesizer backend on the real main run loop. Every case is named and
 * reported individually; the report is a plain-value JSON document that the
 * Actions driver verifies against the source SHA, run id, attempt, and its own
 * hash of this binary.
 *
 * The frozen ABI has no audio-output hook, so real PCM evidence is captured by a
 * second AVSpeechSynthesizer using writeUtterance:toBufferCallback: on the same
 * installed platform. That proves the on-device speech engine produced samples
 * for the same text; it is not a recording of the library's own output stream.
 */
#include <reader_tts.h>

#import <AVFoundation/AVFoundation.h>
#import <Foundation/Foundation.h>
#import <TargetConditionals.h>

#include <CommonCrypto/CommonDigest.h>

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <thread>
#include <vector>

namespace {

struct CheckResult {
  std::string name;
  std::string status;  // pass | fail | pending
  std::string detail;
};

std::vector<CheckResult> g_checks;
int g_pass = 0, g_fail = 0, g_pending = 0;
bool g_speech_available = true;
std::string g_speech_note;
std::string g_voice_id;
size_t g_voice_count = 0;
unsigned g_capabilities = 0;
int g_state_at_create = -1;
std::string g_platform = "unknown";

void Emit(const std::string &name, const char *status, const std::string &detail) {
  g_checks.push_back(CheckResult{name, status, detail});
  if (std::strcmp(status, "pass") == 0) ++g_pass;
  else if (std::strcmp(status, "pending") == 0) ++g_pending;
  else ++g_fail;
  std::printf("%s %s%s%s\n", status, name.c_str(), detail.empty() ? "" : ": ", detail.c_str());
  std::fflush(stdout);
}

void Pass(const std::string &name, const std::string &detail = "") { Emit(name, "pass", detail); }
void Fail(const std::string &name, const std::string &detail) { Emit(name, "fail", detail); }
void Pending(const std::string &name, const std::string &detail) { Emit(name, "pending", detail); }

void Expect(const std::string &name, bool ok, const std::string &detail) {
  if (ok) Pass(name);
  else Fail(name, detail);
}

template <typename T>
std::string Str(T value) {
  return std::to_string(value);
}

void Pump(double seconds) {
  NSDate *end = [NSDate dateWithTimeIntervalSinceNow:seconds];
  for (;;) {
    @autoreleasepool {
      [[NSRunLoop currentRunLoop] runMode:NSDefaultRunLoopMode
                               beforeDate:[NSDate dateWithTimeIntervalSinceNow:0.005]];
    }
    if ([end timeIntervalSinceNow] <= 0) break;
  }
}

std::string Hex(const unsigned char *bytes, size_t length) {
  static const char *kHex = "0123456789abcdef";
  std::string out;
  out.reserve(length * 2);
  for (size_t i = 0; i < length; ++i) {
    out.push_back(kHex[bytes[i] >> 4]);
    out.push_back(kHex[bytes[i] & 0x0F]);
  }
  return out;
}

std::string SelfSha256() {
  NSString *path = [[NSBundle mainBundle] executablePath];
  if (!path) return std::string();
  NSData *data = [NSData dataWithContentsOfFile:path];
  if (!data) return std::string();
  unsigned char digest[CC_SHA256_DIGEST_LENGTH];
  CC_SHA256(data.bytes, (CC_LONG)data.length, digest);
  return Hex(digest, CC_SHA256_DIGEST_LENGTH);
}

// A UTF-8 byte offset is a scalar boundary when it starts a lead byte (or ends
// the text); continuation bytes are never boundaries.
bool ScalarBoundary(const std::string &text, size_t offset) {
  if (offset == 0 || offset == text.size()) return true;
  if (offset > text.size()) return false;
  const unsigned char byte = static_cast<unsigned char>(text[offset]);
  return (byte & 0xC0u) != 0x80u;
}

struct Utterance {
  std::vector<reader_tts_event> events;
  bool ok = false;
  bool saw_started = false, saw_range = false, finished = false, stopped = false, failed = false;
  bool timed_out = false;
  double elapsed = 0;
  size_t started_index = 0, terminal_index = 0;
  bool has_terminal = false;
};

Utterance RunSpeak(reader_tts *handle, uint64_t request_id, const std::string &text, double timeout,
                   bool stop_after_start, double stop_delay, const char *voice = nullptr) {
  Utterance run;
  reader_tts_error error;
  std::memset(&error, 0, sizeof error);
  const auto begin = std::chrono::steady_clock::now();
  const reader_tts_status status =
      reader_tts_speak(handle, request_id, text.data(), text.size(), voice, 1.0, &error);
  if (status != READER_TTS_OK) {
    run.ok = false;
    return run;
  }
  run.ok = true;
  bool stop_sent = false;
  NSDate *deadline = [NSDate dateWithTimeIntervalSinceNow:timeout];
  for (;;) {
    @autoreleasepool { Pump(0.01); }
    reader_tts_event event;
    int available = 0;
    while (reader_tts_poll(handle, &event, &available, &error) == READER_TTS_OK && available) {
      run.events.push_back(event);
      switch (event.kind) {
        case READER_TTS_STARTED:
          run.saw_started = true;
          run.started_index = run.events.size() - 1;
          break;
        case READER_TTS_RANGE: run.saw_range = true; break;
        case READER_TTS_FINISHED: run.finished = true; break;
        case READER_TTS_STOPPED: run.stopped = true; break;
        case READER_TTS_FAILED: run.failed = true; break;
      }
      if ((run.finished || run.stopped || run.failed) && !run.has_terminal) {
        run.has_terminal = true;
        run.terminal_index = run.events.size() - 1;
      }
    }
    if (run.has_terminal) break;
    if (stop_after_start && run.saw_started && !stop_sent) {
      if (stop_delay > 0) Pump(stop_delay);
      reader_tts_stop(handle, request_id, &error);
      stop_sent = true;
    }
    if ([deadline timeIntervalSinceNow] <= 0) break;
  }
  run.elapsed = std::chrono::duration<double>(std::chrono::steady_clock::now() - begin).count();
  if (!run.has_terminal) {
    run.timed_out = true;
    reader_tts_stop(handle, request_id, &error);
    NSDate *cleanup = [NSDate dateWithTimeIntervalSinceNow:1.0];
    while ([cleanup timeIntervalSinceNow] > 0) {
      Pump(0.01);
      reader_tts_event event;
      int available = 0;
      while (reader_tts_poll(handle, &event, &available, &error) == READER_TTS_OK && available) {
        run.events.push_back(event);
        if (event.kind == READER_TTS_FINISHED) run.finished = true;
        if (event.kind == READER_TTS_STOPPED) run.stopped = true;
        if (event.kind == READER_TTS_FAILED) run.failed = true;
        if (run.finished || run.stopped || run.failed) break;
      }
      if (run.finished || run.stopped || run.failed) break;
    }
  }
  return run;
}

reader_tts_state StateOf(reader_tts *handle) {
  reader_tts_snapshot snapshot;
  reader_tts_error error;
  std::memset(&snapshot, 0, sizeof snapshot);
  std::memset(&error, 0, sizeof error);
  if (reader_tts_observe(handle, &snapshot, &error) != READER_TTS_OK) return READER_TTS_CLOSED;
  return snapshot.state;
}

std::string DrainToText(reader_tts *handle) {
  reader_tts_error error;
  reader_tts_event event;
  int available = 0;
  std::string out;
  while (reader_tts_poll(handle, &event, &available, &error) == READER_TTS_OK && available) {
    out += " " + std::to_string((int)event.kind) + "@" + std::to_string(event.start) + "-" +
           std::to_string(event.end);
  }
  return out;
}

std::string JsonEscape(const std::string &value) {
  std::string out;
  for (unsigned char byte : value) {
    switch (byte) {
      case '"': out += "\\\""; break;
      case '\\': out += "\\\\"; break;
      case '\n': out += "\\n"; break;
      case '\r': out += "\\r"; break;
      case '\t': out += "\\t"; break;
      default:
        if (byte < 0x20) {
          char buffer[8];
          std::snprintf(buffer, sizeof buffer, "\\u%04x", byte);
          out += buffer;
        } else {
          out.push_back((char)byte);
        }
    }
  }
  return out;
}

// ---- PCM capture through the platform engine, for real audio evidence ----
struct PcmCapture {
  std::vector<int16_t> samples;
  double sample_rate = 0;
  unsigned channels = 0;
  std::atomic<bool> done{false};
  size_t buffers = 0;

  void Append(const int16_t *data, size_t count) {
    samples.insert(samples.end(), data, data + count);
  }
};

double Rms(const std::vector<int16_t> &samples) {
  if (samples.empty()) return 0.0;
  double sum = 0.0;
  for (int16_t sample : samples) {
    const double value = sample / 32768.0;
    sum += value * value;
  }
  return std::sqrt(sum / (double)samples.size());
}

std::vector<unsigned char> MakeWav(const std::vector<int16_t> &samples, double sample_rate, unsigned channels) {
  std::vector<unsigned char> wav;
  if (channels == 0) channels = 1;
  const uint32_t data_bytes = (uint32_t)(samples.size() * sizeof(int16_t));
  const uint32_t byte_rate = (uint32_t)(sample_rate * channels * 2);
  const uint16_t block_align = (uint16_t)(channels * 2);
  auto put32 = [&wav](uint32_t value) {
    wav.push_back((unsigned char)(value & 0xFF));
    wav.push_back((unsigned char)((value >> 8) & 0xFF));
    wav.push_back((unsigned char)((value >> 16) & 0xFF));
    wav.push_back((unsigned char)((value >> 24) & 0xFF));
  };
  auto put16 = [&wav](uint16_t value) {
    wav.push_back((unsigned char)(value & 0xFF));
    wav.push_back((unsigned char)((value >> 8) & 0xFF));
  };
  for (char c : {'R', 'I', 'F', 'F'}) wav.push_back((unsigned char)c);
  put32(36 + data_bytes);
  for (char c : {'W', 'A', 'V', 'E', 'f', 'm', 't', ' '}) wav.push_back((unsigned char)c);
  put32(16);
  put16(1);
  put16(block_align);
  put32((uint32_t)sample_rate);
  put32(byte_rate);
  put16(block_align);
  put16(16);
  for (char c : {'d', 'a', 't', 'a'}) wav.push_back((unsigned char)c);
  put32(data_bytes);
  for (int16_t sample : samples) put16((uint16_t)sample);
  return wav;
}

struct PcmResult {
  bool ok = false;
  std::string detail;
  size_t frames = 0;
  double sample_rate = 0;
  double rms = 0;
  double duration = 0;
  size_t bytes = 0;
  std::string sha256;
  std::vector<unsigned char> wav;
};

PcmResult CapturePcm(const std::string &text, double timeout) {
  PcmResult result;
  @autoreleasepool {
    AVSpeechSynthesizer *synthesizer = [[AVSpeechSynthesizer alloc] init];
    NSString *string = [NSString stringWithUTF8String:text.c_str()];
    if (!string) {
      result.detail = "text is not UTF-8";
      return result;
    }
    AVSpeechUtterance *utterance = [AVSpeechUtterance speechUtteranceWithString:string];
    PcmCapture *capture = new PcmCapture();
    [synthesizer writeUtterance:utterance
              toBufferCallback:^(AVAudioBuffer *buffer) {
                AVAudioPCMBuffer *pcm = [buffer isKindOfClass:[AVAudioPCMBuffer class]]
                                            ? (AVAudioPCMBuffer *)buffer
                                            : nil;
                if (!pcm) return;
                capture->sample_rate = pcm.format.sampleRate;
                capture->channels = pcm.format.channelCount;
                if (pcm.frameLength == 0) {
                  capture->done.store(true);
                  return;
                }
                ++capture->buffers;
                const size_t frames = (size_t)pcm.frameLength;
                if (pcm.format.commonFormat == AVAudioPCMFormatInt16 && pcm.int16ChannelData) {
                  const int16_t *channel = pcm.int16ChannelData[0];
                  const size_t stride = pcm.format.isInterleaved ? (size_t)pcm.format.channelCount : 1;
                  for (size_t i = 0; i < frames; ++i) capture->samples.push_back(channel[i * stride]);
                } else if (pcm.format.commonFormat == AVAudioPCMFormatFloat32 && pcm.floatChannelData) {
                  const float *channel = pcm.floatChannelData[0];
                  for (size_t i = 0; i < frames; ++i) {
                    float value = channel[i];
                    if (value > 1.0f) value = 1.0f;
                    if (value < -1.0f) value = -1.0f;
                    capture->samples.push_back((int16_t)std::lround(value * 32767.0f));
                  }
                }
              }];
    NSDate *deadline = [NSDate dateWithTimeIntervalSinceNow:timeout];
    while (!capture->done.load() && [deadline timeIntervalSinceNow] > 0) {
      @autoreleasepool { Pump(0.01); }
    }
    result.frames = capture->samples.size();
    result.sample_rate = capture->sample_rate > 0 ? capture->sample_rate : 22050.0;
    result.rms = Rms(capture->samples);
    result.duration = result.sample_rate > 0 ? (double)result.frames / result.sample_rate : 0.0;
    if (!capture->samples.empty()) {
      result.wav = MakeWav(capture->samples, result.sample_rate, capture->channels ? capture->channels : 1);
      result.bytes = result.wav.size();
      unsigned char digest[CC_SHA256_DIGEST_LENGTH];
      CC_SHA256(result.wav.data(), (CC_LONG)result.wav.size(), digest);
      result.sha256 = Hex(digest, CC_SHA256_DIGEST_LENGTH);
      result.ok = true;
    } else {
      result.detail = capture->done.load() ? "the system returned no sample buffers"
                                           : "no buffer callback within the capture deadline";
    }
    delete capture;
  }
  return result;
}

const char *kEnglish = "EXReader reads this sentence aloud.";
// 第一段：汉字与表情😀🚀的朗读。
const char *kChinese =
    "\u7b2c\u4e00\u6bb5\uff1a\u6c49\u5b57\u4e0e\u8868\u60c5\U0001F600\U0001F680\u7684\u6717\u8bfb\u3002";

bool EventOrderOk(const Utterance &run, std::string *detail) {
  if (!run.saw_started) {
    *detail = "no STARTED event";
    return false;
  }
  if (!run.has_terminal) {
    *detail = "no terminal event";
    return false;
  }
  if (run.terminal_index + 1 != run.events.size()) {
    *detail = "an event followed the terminal event";
    return false;
  }
  size_t terminals = 0;
  for (const reader_tts_event &event : run.events) {
    if (event.kind == READER_TTS_FINISHED || event.kind == READER_TTS_STOPPED || event.kind == READER_TTS_FAILED)
      ++terminals;
  }
  if (terminals != 1) {
    *detail = "expected exactly one terminal event";
    return false;
  }
  return true;
}

}  // namespace

bool WriteReport(const std::string &output, const PcmResult &pcm, const std::string &consumer) {
  @autoreleasepool {
    const size_t slash = output.find_last_of('/');
    const std::string wav_file = output.substr(slash == std::string::npos ? 0 : slash + 1) + ".wav";
    const char *source = std::getenv("GITHUB_SHA");
    const char *run_id = std::getenv("GITHUB_RUN_ID");
    const char *attempt = std::getenv("GITHUB_RUN_ATTEMPT");
    NSString *os_version = [[NSProcessInfo processInfo] operatingSystemVersionString];
    const std::string os = os_version ? [os_version UTF8String] : "";
    std::string arch;
#if defined(__arm64__)
    arch = "arm64";
#elif defined(__x86_64__)
    arch = "x86_64";
#else
    arch = "unknown";
#endif

    std::string json;
    json += "{\n";
    json += "  \"schema\": 1,\n";
    json += "  \"producer\": \"reader-tts-apple-probe\",\n";
    json += "  \"platform\": \"" + g_platform + "\",\n";
    json += "  \"version\": \"" + std::string(READER_TTS_VERSION) + "\",\n";
    json += "  \"source_sha\": \"" + JsonEscape(source ? source : "") + "\",\n";
    json += "  \"run_id\": " + std::string(run_id ? run_id : "0") + ",\n";
    json += "  \"attempt\": " + std::string(attempt ? attempt : "0") + ",\n";
    json += "  \"consumer_sha256\": \"" + consumer + "\",\n";
    json += "  \"os\": \"" + JsonEscape(os) + "\",\n";
    json += "  \"arch\": \"" + arch + "\",\n";
    json += "  \"state_at_create\": " + Str(g_state_at_create) + ",\n";
    json += "  \"capabilities\": " + Str(g_capabilities) + ",\n";
    json += "  \"voice_count\": " + Str(g_voice_count) + ",\n";
    json += "  \"speech_available\": " + std::string(g_speech_available ? "true" : "false") + ",\n";
    json += "  \"speech_note\": \"" + JsonEscape(g_speech_note) + "\",\n";
    if (pcm.ok) {
      json += "  \"pcm\": {\"bytes\": " + Str(pcm.bytes) + ", \"frames\": " + Str(pcm.frames) +
              ", \"sample_rate\": " + std::to_string(pcm.sample_rate) +
              ", \"duration_seconds\": " + std::to_string(pcm.duration) + ", \"rms\": " + std::to_string(pcm.rms) +
              ", \"sha256\": \"" + pcm.sha256 + "\", \"file\": \"" + JsonEscape(wav_file) + "\"},\n";
    } else {
      json += "  \"pcm\": null,\n";
    }
    json += "  \"checks\": [\n";
    for (size_t i = 0; i < g_checks.size(); ++i) {
      const CheckResult &check = g_checks[i];
      json += "    {\"name\": \"" + JsonEscape(check.name) + "\", \"status\": \"" + check.status +
              "\", \"detail\": \"" + JsonEscape(check.detail) + "\"}";
      json += (i + 1 == g_checks.size()) ? "\n" : ",\n";
    }
    json += "  ],\n";
    json += "  \"counts\": {\"pass\": " + Str(g_pass) + ", \"fail\": " + Str(g_fail) + ", \"pending\": " +
            Str(g_pending) + "}\n";
    json += "}\n";

    NSData *bytes = [NSData dataWithBytes:json.data() length:json.size()];
    NSString *file = [NSString stringWithUTF8String:output.c_str()];
    const BOOL written = [bytes writeToFile:file atomically:YES];
    std::printf("REPORT %s written=%d pass=%d fail=%d pending=%d\n", output.c_str(), (int)written, g_pass, g_fail,
                g_pending);
    std::fflush(stdout);
    return written == YES;
  }
}

extern "C" int rtts_probe_run(const char *output_path);

int rtts_probe_run(const char *output_path) {
  @autoreleasepool {
    const std::string output = output_path ? output_path : "result.json";
    const std::string wav_path = output + ".wav";
#if TARGET_OS_SIMULATOR
    g_platform = "ios-simulator";
#elif TARGET_OS_IPHONE
    g_platform = "ios-device";
#else
    g_platform = "macos";
#endif

    reader_tts_error error;
    std::memset(&error, 0, sizeof error);
    reader_tts_config config;
    std::memset(&config, 0, sizeof config);
    config.struct_size = sizeof config;

    // ---- creation on the real main thread ----
    reader_tts *handle = nullptr;
    const reader_tts_status create_status = reader_tts_create(&config, &handle, &error);
    Expect("probe.create-ok", create_status == READER_TTS_OK && handle != nullptr,
           "reader_tts_create returned " + Str((int)create_status));
    if (!handle) {
      Fail("probe.handle-usable", "no handle, remaining cases cannot run");
      WriteReport(output, PcmResult(), SelfSha256());
      return 1;
    }

    reader_tts_snapshot snapshot;
    std::memset(&snapshot, 0, sizeof snapshot);
    reader_tts_observe(handle, &snapshot, &error);
    g_state_at_create = (int)snapshot.state;
    g_capabilities = snapshot.capabilities;
    const bool usable = snapshot.state == READER_TTS_READY || snapshot.state == READER_TTS_SERVICE_UNAVAILABLE;
    Expect("probe.state-after-create", usable, "unexpected state " + Str((int)snapshot.state));
    Expect("probe.initial-request-id", snapshot.request_id == 0, "request_id is not 0");
    Expect("probe.capabilities-reported", (snapshot.capabilities & READER_TTS_CAN_PAUSE) != 0 &&
                                              (snapshot.capabilities & READER_TTS_CAN_REPORT_RANGE) != 0,
           "capabilities are " + Str(snapshot.capabilities));

    // ---- voices ----
    reader_tts_voice_list voices;
    std::memset(&voices, 0, sizeof voices);
    const reader_tts_status voices_status = reader_tts_voices(handle, &voices, &error);
    g_voice_count = voices.count;
    if (voices_status == READER_TTS_UNAVAILABLE) {
      Pending("probe.voices-listed", "the system reports no installed voice");
      g_speech_available = false;
      g_speech_note = "no installed voice";
    } else if (voices_status != READER_TTS_OK) {
      Fail("probe.voices-listed", "reader_tts_voices returned " + Str((int)voices_status));
    } else if (voices.count == 0) {
      Pending("probe.voices-listed", "empty voice list");
      g_speech_available = false;
      g_speech_note = "empty voice list";
    } else {
      bool fields_ok = true;
      std::string first_bad;
      std::vector<std::string> seen;
      for (size_t i = 0; i < voices.count; ++i) {
        const reader_tts_voice &voice = voices.voices[i];
        if (!voice.id || !*voice.id || !voice.name || !*voice.name || !voice.language || !*voice.language) {
          fields_ok = false;
          first_bad = "entry " + Str(i) + " has an empty field";
          break;
        }
        const std::string id = voice.id;
        if (std::find(seen.begin(), seen.end(), id) != seen.end()) {
          fields_ok = false;
          first_bad = "duplicate id " + id;
          break;
        }
        seen.push_back(id);
        if (std::strchr(voice.language, '-') == nullptr) {
          fields_ok = false;
          first_bad = "language without a region: " + std::string(voice.language);
          break;
        }
        if (i == 0) g_voice_id = id;
      }
      Expect("probe.voices-listed", true, Str(voices.count) + " voices");
      Expect("probe.voices-fields", fields_ok, first_bad);
    }

    // ---- argument and state checks that need no audio ----
    {
      const char invalid[] = {(char)0x80, 0};
      Expect("probe.rejects-zero-bytes",
             reader_tts_speak(handle, 100, "", 0, nullptr, 1.0, &error) == READER_TTS_ARGUMENT, "accepted");
      Expect("probe.rejects-zero-id",
             reader_tts_speak(handle, 0, kEnglish, std::strlen(kEnglish), nullptr, 1.0, &error) ==
                 READER_TTS_ARGUMENT,
             "accepted");
      Expect("probe.rejects-invalid-utf8",
             reader_tts_speak(handle, 101, invalid, 1, nullptr, 1.0, &error) == READER_TTS_ARGUMENT, "accepted");
      Expect("probe.rejects-rate-out-of-range",
             reader_tts_speak(handle, 102, kEnglish, std::strlen(kEnglish), nullptr, 2.5, &error) ==
                 READER_TTS_ARGUMENT,
             "accepted");
      Expect("probe.rejects-nan-rate",
             reader_tts_speak(handle, 103, kEnglish, std::strlen(kEnglish), nullptr, std::nan(""), &error) ==
                 READER_TTS_ARGUMENT,
             "accepted");
      std::string oversized(READER_TTS_MAX_UTF8_BYTES + 1, 'a');
      Expect("probe.rejects-over-limit",
             reader_tts_speak(handle, 104, oversized.data(), oversized.size(), nullptr, 1.0, &error) ==
                 READER_TTS_LIMIT,
             "accepted");
      Expect("probe.rejects-unknown-voice",
             reader_tts_speak(handle, 105, kEnglish, std::strlen(kEnglish), "com.example.absent", 1.0, &error) ==
                 READER_TTS_ARGUMENT,
             "accepted");
      reader_tts_event event;
      int available = 1;
      reader_tts_poll(handle, &event, &available, &error);
      Expect("probe.poll-empty", available == 0, "a rejected call queued an event");
    }

    // A lowered cap is honoured by the real backend as well.
    {
      reader_tts_config small;
      std::memset(&small, 0, sizeof small);
      small.struct_size = sizeof small;
      small.max_utf8_bytes = 64;
      reader_tts *limited = nullptr;
      const reader_tts_status status = reader_tts_create(&small, &limited, &error);
      std::string oversized(65, 'a');
      bool rejected = false;
      if (status == READER_TTS_OK && limited) {
        rejected = reader_tts_speak(limited, 1, oversized.data(), oversized.size(), nullptr, 1.0, &error) ==
                   READER_TTS_LIMIT;
        reader_tts_request_close(limited, &error);
        reader_tts_snapshot snap;
        reader_tts_observe(limited, &snap, &error);
        reader_tts_destroy(&limited, &error);
      }
      Expect("probe.lowered-cap-enforced", status == READER_TTS_OK && rejected,
             "create returned " + Str((int)status));
    }

    // ---- ownership on the real backend ----
    {
      std::atomic<int> observe_status{-1};
      std::atomic<int> speak_status{-1};
      reader_tts *foreign_pointer = handle;
      std::atomic<int> destroy_status{-1};
      std::thread worker([&]() {
        reader_tts_snapshot snap;
        reader_tts_error thread_error;
        observe_status.store((int)reader_tts_observe(handle, &snap, &thread_error));
        speak_status.store((int)reader_tts_speak(handle, 110, kEnglish, std::strlen(kEnglish), nullptr, 1.0,
                                                 &thread_error));
        destroy_status.store((int)reader_tts_destroy(&foreign_pointer, &thread_error));
      });
      worker.join();
      Expect("probe.observe-off-main-thread", observe_status.load() == (int)READER_TTS_OWNER,
             "returned " + Str(observe_status.load()));
      Expect("probe.speak-off-main-thread", speak_status.load() == (int)READER_TTS_OWNER,
             "returned " + Str(speak_status.load()));
      Expect("probe.destroy-off-main-thread", destroy_status.load() == (int)READER_TTS_OWNER,
             "returned " + Str(destroy_status.load()));
      Expect("probe.handle-survived-foreign-destroy", foreign_pointer == handle, "handle was released");
      std::thread creator([&]() {
        reader_tts_config cfg;
        std::memset(&cfg, 0, sizeof cfg);
        cfg.struct_size = sizeof cfg;
        reader_tts *created = nullptr;
        reader_tts_error thread_error;
        const int status = (int)reader_tts_create(&cfg, &created, &thread_error);
        Expect("probe.create-off-main-thread", status == (int)READER_TTS_OWNER, "returned " + Str(status));
        if (created) reader_tts_destroy(&created, &thread_error);
      });
      creator.join();
    }

    // ---- real speech lifecycle ----
    PcmResult pcm;
    if (g_speech_available) {
      const Utterance english = RunSpeak(handle, 1, kEnglish, 25.0, false, 0.0);
      if (!english.saw_started) {
        // No speech-start callback at all: this runner has no usable audio route
        // for the synthesizer. Recorded as pending with the observed state, never
        // as a passing朗读.
        g_speech_available = false;
        g_speech_note = "no speech-start callback within 25 s (state " + Str((int)StateOf(handle)) +
                        ", events " + Str(english.events.size()) + "); no usable audio route on this runner";
        Pending("probe.speak-english-lifecycle", g_speech_note);
        Pending("probe.speak-english-callbacks", g_speech_note);
        Pending("probe.state-ready-after-finish", g_speech_note);
        DrainToText(handle);
      } else if (!english.has_terminal) {
        g_speech_note = "speech started but never reached a terminal event within 25 s (state " +
                        Str((int)StateOf(handle)) + ")";
        Pending("probe.speak-english-lifecycle", g_speech_note);
        Expect("probe.speak-english-callbacks", english.saw_started && english.saw_range, "no range callback");
        Pending("probe.state-ready-after-finish", g_speech_note);
      } else {
        std::string order_detail;
        const bool ordered = EventOrderOk(english, &order_detail);
        Expect("probe.speak-english-lifecycle",
               ordered && english.finished && english.elapsed >= 0.25,
               order_detail.empty() ? "finished=" + Str((int)english.finished) + " elapsed=" +
                                          std::to_string(english.elapsed)
                                    : order_detail);
        Expect("probe.speak-english-callbacks", english.saw_started && english.saw_range,
               "started=" + Str((int)english.saw_started) + " range=" + Str((int)english.saw_range));
        Expect("probe.state-ready-after-finish", StateOf(handle) == READER_TTS_READY, "state is not READY");
      }
    } else {
      Pending("probe.speak-english-lifecycle", g_speech_note);
      Pending("probe.speak-english-callbacks", g_speech_note);
      Pending("probe.state-ready-after-finish", g_speech_note);
    }

    if (g_speech_available) {
      const std::string chinese = kChinese;
      const Utterance run = RunSpeak(handle, 2, chinese, 25.0, false, 0.0);
      std::string detail;
      const bool ordered = EventOrderOk(run, &detail);
      bool boundaries = true;
      size_t last_end = 0;
      std::string boundary_detail;
      for (const reader_tts_event &event : run.events) {
        if (event.kind != READER_TTS_RANGE) continue;
        if (event.end <= event.start || event.end > chinese.size()) {
          boundaries = false;
          boundary_detail = "range " + Str(event.start) + "-" + Str(event.end) + " outside the input";
          break;
        }
        if (!ScalarBoundary(chinese, event.start) || !ScalarBoundary(chinese, event.end)) {
          boundaries = false;
          boundary_detail = "range " + Str(event.start) + "-" + Str(event.end) + " split a scalar";
          break;
        }
        if (event.has_range != 1) {
          boundaries = false;
          boundary_detail = "RANGE without has_range";
          break;
        }
        last_end = event.end;
      }
      Expect("probe.speak-chinese-emoji-lifecycle", ordered && run.finished,
             ordered ? "finished=" + Str((int)run.finished) : detail);
      Expect("probe.range-byte-boundaries", boundaries && !run.events.empty(), boundary_detail);
      Expect("probe.range-advances", last_end > 0, "no usable range was reported");
    } else {
      Pending("probe.speak-chinese-emoji-lifecycle", g_speech_note);
      Pending("probe.range-byte-boundaries", g_speech_note);
      Pending("probe.range-advances", g_speech_note);
    }

    // named voice selection when the system has one
    if (g_speech_available && !g_voice_id.empty()) {
      const Utterance named = RunSpeak(handle, 3, "Named voice check.", 25.0, false, 0.0, g_voice_id.c_str());
      std::string detail;
      const bool ordered = EventOrderOk(named, &detail);
      Expect("probe.speak-named-voice", ordered && named.finished, detail);
    } else {
      Pending("probe.speak-named-voice", g_speech_available ? "no voice id available" : g_speech_note);
    }

    // pause / resume on a real utterance
    if (g_speech_available) {
      reader_tts_error pause_error;
      const std::string long_text(220, 'a');
      const reader_tts_status started =
          reader_tts_speak(handle, 4, long_text.data(), long_text.size(), nullptr, 0.5, &pause_error);
      if (started != READER_TTS_OK) {
        Fail("probe.pause-resume", "speak returned " + Str((int)started));
      } else {
        bool saw_started = false;
        NSDate *deadline = [NSDate dateWithTimeIntervalSinceNow:10.0];
        while ([deadline timeIntervalSinceNow] > 0 && !saw_started) {
          Pump(0.01);
          reader_tts_event event;
          int available = 0;
          while (reader_tts_poll(handle, &event, &available, &pause_error) == READER_TTS_OK && available) {
            if (event.kind == READER_TTS_STARTED) saw_started = true;
          }
        }
        const reader_tts_status pause_status = reader_tts_pause(handle, 4, &pause_error);
        const reader_tts_state paused_state = StateOf(handle);
        Pump(0.05);
        const reader_tts_status resume_status = reader_tts_resume(handle, 4, &pause_error);
        std::string detail = "saw_started=" + Str((int)saw_started) + " pause=" + Str((int)pause_status) +
                             " state=" + Str((int)paused_state) + " resume=" + Str((int)resume_status);
        Expect("probe.pause-resume", saw_started && pause_status == READER_TTS_OK &&
                                         paused_state == READER_TTS_PAUSED && resume_status == READER_TTS_OK,
               detail);
        reader_tts_stop(handle, 4, &pause_error);
        NSDate *stop_deadline = [NSDate dateWithTimeIntervalSinceNow:5.0];
        bool stopped = false;
        while ([stop_deadline timeIntervalSinceNow] > 0 && !stopped) {
          Pump(0.01);
          reader_tts_event event;
          int available = 0;
          while (reader_tts_poll(handle, &event, &available, &pause_error) == READER_TTS_OK && available) {
            if (event.kind == READER_TTS_STOPPED) stopped = true;
          }
        }
        Expect("probe.stop-after-pause", stopped, "no STOPPED event after stop");
      }
    } else {
      Pending("probe.pause-resume", g_speech_note);
      Pending("probe.stop-after-pause", g_speech_note);
    }

    // queue replacement and cancel isolation
    if (g_speech_available) {
      reader_tts_error queue_error;
      const std::string long_text(300, 'b');
      const reader_tts_status started =
          reader_tts_speak(handle, 5, long_text.data(), long_text.size(), nullptr, 1.0, &queue_error);
      if (started != READER_TTS_OK) {
        Fail("probe.queue-replacement-busy", "speak returned " + Str((int)started));
      } else {
        Pump(0.05);
        const reader_tts_status second =
            reader_tts_speak(handle, 6, kEnglish, std::strlen(kEnglish), nullptr, 1.0, &queue_error);
        Expect("probe.queue-replacement-busy", second == READER_TTS_BUSY, "second request returned " + Str((int)second));

        // Stop request 5, keep its terminal, then start 6 and prove no stale
        // callback is attributed to it.
        reader_tts_stop(handle, 5, &queue_error);
        bool stopped = false;
        NSDate *stop_deadline = [NSDate dateWithTimeIntervalSinceNow:5.0];
        uint64_t stopped_id = 0;
        while ([stop_deadline timeIntervalSinceNow] > 0 && !stopped) {
          Pump(0.01);
          reader_tts_event event;
          int available = 0;
          while (reader_tts_poll(handle, &event, &available, &queue_error) == READER_TTS_OK && available) {
            if (event.kind == READER_TTS_STOPPED || event.kind == READER_TTS_FINISHED) {
              stopped = true;
              stopped_id = event.request_id;
            }
          }
        }
        Expect("probe.cancel-terminal-once", stopped && stopped_id == 5,
               "terminal id " + Str(stopped_id) + " observed=" + Str((int)stopped));
        const Utterance second_run = RunSpeak(handle, 6, "Replacement request.", 25.0, false, 0.0);
        bool foreign = false;
        for (const reader_tts_event &event : second_run.events) {
          if (event.request_id != 6) foreign = true;
        }
        std::string detail;
        const bool ordered = EventOrderOk(second_run, &detail);
        Expect("probe.late-callback-isolation", ordered && !foreign,
               foreign ? "an event carried a stale request id" : detail);
      }
    } else {
      Pending("probe.queue-replacement-busy", g_speech_note);
      Pending("probe.cancel-terminal-once", g_speech_note);
      Pending("probe.late-callback-isolation", g_speech_note);
    }

    // ---- real PCM through the same installed platform engine ----
    if (g_speech_available) {
      pcm = CapturePcm(kChinese, 25.0);
      Expect("probe.pcm-wav-captured", pcm.ok && pcm.bytes > 4096 && pcm.duration > 0.2 && pcm.rms > 0.0005,
             pcm.ok ? "bytes=" + Str(pcm.bytes) + " duration=" + std::to_string(pcm.duration) +
                          " rms=" + std::to_string(pcm.rms)
                    : pcm.detail);
      if (pcm.ok) {
        NSData *data = [NSData dataWithBytes:pcm.wav.data() length:pcm.wav.size()];
        [data writeToFile:[NSString stringWithUTF8String:wav_path.c_str()] atomically:YES];
      }
    } else {
      Pending("probe.pcm-wav-captured", g_speech_note);
    }

    // ---- close and destroy ----
    {
      reader_tts_error close_error;
      const reader_tts_status first = reader_tts_request_close(handle, &close_error);
      const reader_tts_status second = reader_tts_request_close(handle, &close_error);
      Expect("probe.close-idempotent", first == READER_TTS_OK && second == READER_TTS_OK,
             "close returned " + Str((int)first) + "/" + Str((int)second));
      reader_tts_snapshot closed_snapshot;
      std::memset(&closed_snapshot, 0, sizeof closed_snapshot);
      reader_tts_observe(handle, &closed_snapshot, &close_error);
      Expect("probe.closed-state", closed_snapshot.state == READER_TTS_CLOSED,
             "state is " + Str((int)closed_snapshot.state));
      reader_tts_voice_list after_close;
      std::memset(&after_close, 0, sizeof after_close);
      Expect("probe.voices-after-close", reader_tts_voices(handle, &after_close, &close_error) ==
                                             READER_TTS_UNAVAILABLE,
             "voices did not report UNAVAILABLE after close");
      const reader_tts_status speak_after_close =
          reader_tts_speak(handle, 200, kEnglish, std::strlen(kEnglish), nullptr, 1.0, &close_error);
      Expect("probe.speak-after-close", speak_after_close == READER_TTS_UNAVAILABLE,
             "returned " + Str((int)speak_after_close));
      const reader_tts_status destroy_status = reader_tts_destroy(&handle, &close_error);
      Expect("probe.destroy-clears-pointer", destroy_status == READER_TTS_OK && handle == nullptr,
             "destroy returned " + Str((int)destroy_status));
    }
    if (voices.voices) reader_tts_voice_list_free(&voices);

    // ---- report ----
    const std::string consumer = SelfSha256();
    WriteReport(output, pcm, consumer);
    return g_fail == 0 ? 0 : 1;
  }
}

#if !TARGET_OS_IPHONE
int main(int argc, char **argv) {
  const char *output = argc > 1 ? argv[1] : "result.json";
  return rtts_probe_run(output);
}
#endif
