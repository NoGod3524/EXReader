/* SPDX-License-Identifier: MIT */
/*
 * Minimal installed-package host example. It shows the lifecycle a reader host
 * needs: create on the main thread, list voices, speak a text chunk, pump the
 * run loop while polling for events, pause/resume/stop, then close and destroy.
 *
 *   reader_tts_example voices [--limit N]
 *   reader_tts_example speak --text TEXT [--voice ID] [--rate R] [--pause-ms N]
 *
 * Output is line oriented JSON so a probe script can parse it.
 */
#include <reader_tts.h>

#import <Foundation/Foundation.h>

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

namespace {

void Pump(double seconds) {
  NSDate *end = [NSDate dateWithTimeIntervalSinceNow:seconds];
  while ([end timeIntervalSinceNow] > 0) {
    @autoreleasepool {
      [[NSRunLoop currentRunLoop] runMode:NSDefaultRunLoopMode
                               beforeDate:[NSDate dateWithTimeIntervalSinceNow:0.005]];
    }
  }
}

const char *KindName(reader_tts_event_kind kind) {
  switch (kind) {
    case READER_TTS_STARTED: return "started";
    case READER_TTS_RANGE: return "range";
    case READER_TTS_FINISHED: return "finished";
    case READER_TTS_STOPPED: return "stopped";
    case READER_TTS_FAILED: return "failed";
  }
  return "unknown";
}

void DrainEvents(reader_tts *handle) {
  for (;;) {
    reader_tts_event event;
    reader_tts_error error;
    int available = 0;
    if (reader_tts_poll(handle, &event, &available, &error) != READER_TTS_OK || !available) return;
    if (event.kind == READER_TTS_RANGE) {
      std::printf("{\"event\":\"range\",\"request_id\":%llu,\"start\":%zu,\"end\":%zu}\n",
                  (unsigned long long)event.request_id, event.start, event.end);
    } else {
      std::printf("{\"event\":\"%s\",\"request_id\":%llu,\"status\":%d}\n", KindName(event.kind),
                  (unsigned long long)event.request_id, (int)event.status);
    }
    std::fflush(stdout);
  }
}

int Fail(const char *step, reader_tts_status status) {
  std::printf("{\"error\":\"%s\",\"status\":%d}\n", step, (int)status);
  return 1;
}

}  // namespace

int main(int argc, char **argv) {
  @autoreleasepool {
    if (argc < 2) {
      std::fprintf(stderr, "usage: reader_tts_example voices|speak [options]\n");
      return 2;
    }
    std::string mode = argv[1];
    std::string text = "EXReader native speech example.";
    std::string voice;
    double rate = 1.0;
    long limit = 40;
    double pause_after = 0;
    for (int i = 2; i < argc; ++i) {
      std::string flag = argv[i];
      const bool has_value = i + 1 < argc;
      if (flag == "--text" && has_value) text = argv[++i];
      else if (flag == "--voice" && has_value) voice = argv[++i];
      else if (flag == "--rate" && has_value) rate = std::atof(argv[++i]);
      else if (flag == "--limit" && has_value) limit = std::atol(argv[++i]);
      else if (flag == "--pause-ms" && has_value) pause_after = std::atof(argv[++i]) / 1000.0;
    }

    reader_tts_error error;
    std::memset(&error, 0, sizeof error);
    reader_tts_config config;
    std::memset(&config, 0, sizeof config);
    config.struct_size = sizeof config;
    reader_tts *handle = nullptr;
    reader_tts_status status = reader_tts_create(&config, &handle, &error);
    if (status != READER_TTS_OK) return Fail("create", status);

    reader_tts_snapshot snapshot;
    reader_tts_observe(handle, &snapshot, &error);
    std::printf("{\"state\":%d,\"capabilities\":%u,\"version\":\"%s\"}\n", (int)snapshot.state,
                snapshot.capabilities, READER_TTS_VERSION);

    int result = 0;
    if (mode == "voices") {
      reader_tts_voice_list list;
      std::memset(&list, 0, sizeof list);
      status = reader_tts_voices(handle, &list, &error);
      if (status != READER_TTS_OK) {
        result = Fail("voices", status);
      } else {
        std::printf("{\"voices\":%zu}\n", list.count);
        for (size_t i = 0; i < list.count && (long)i < limit; ++i) {
          std::printf("{\"voice\":\"%s\",\"name\":\"%s\",\"language\":\"%s\"}\n", list.voices[i].id,
                      list.voices[i].name, list.voices[i].language);
        }
        reader_tts_voice_list_free(&list);
      }
    } else if (mode == "speak") {
      const uint64_t request_id = 1;
      status = reader_tts_speak(handle, request_id, text.c_str(), text.size(), voice.c_str(), rate, &error);
      if (status != READER_TTS_OK) {
        result = Fail("speak", status);
      } else {
        bool done = false;
        bool paused = false;
        NSDate *deadline = [NSDate dateWithTimeIntervalSinceNow:60];
        while (!done && [deadline timeIntervalSinceNow] > 0) {
          Pump(0.02);
          DrainEvents(handle);
          reader_tts_observe(handle, &snapshot, &error);
          if (pause_after > 0 && !paused && snapshot.state == READER_TTS_SPEAKING) {
            paused = true;
            if (reader_tts_pause(handle, request_id, &error) == READER_TTS_OK) {
              std::printf("{\"event\":\"paused\"}\n");
              Pump(pause_after);
              reader_tts_resume(handle, request_id, &error);
              std::printf("{\"event\":\"resumed\"}\n");
            }
          }
          done = snapshot.state != READER_TTS_SPEAKING && snapshot.state != READER_TTS_PAUSED &&
                 snapshot.state != READER_TTS_STOPPING;
        }
        DrainEvents(handle);
        if (!done) result = Fail("speak timeout", READER_TTS_IO);
      }
    } else {
      result = Fail("mode", READER_TTS_ARGUMENT);
    }

    // Close, drain the retained terminal event, then destroy.
    reader_tts_request_close(handle, &error);
    for (int i = 0; i < 200; ++i) {
      reader_tts_snapshot current;
      reader_tts_observe(handle, &current, &error);
      if (current.state == READER_TTS_CLOSED) break;
      Pump(0.02);
    }
    DrainEvents(handle);
    status = reader_tts_destroy(&handle, &error);
    if (status != READER_TTS_OK) return Fail("destroy", status);
    std::printf("{\"closed\":true,\"handle_null\":%s}\n", handle == nullptr ? "true" : "false");
    return result;
  }
}
