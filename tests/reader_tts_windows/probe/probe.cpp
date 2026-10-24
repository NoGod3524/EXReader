/* SPDX-License-Identifier: MIT */
/* Independent C++ consumer of the installed package: synthesises one UTF-8 text
   file into a WAV file through the public C ABI and prints one JSON summary line.
   This proves the installed headers are consumable from C++ and that a second,
   separately built application drives the same backend.
   Usage: tts-probe <text-file> <wav-file> [rate] [voice-id] */
#include "reader_tts.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iterator>
#include <string>
#include <vector>
#include <windows.h>

namespace {

const char *status_name(reader_tts_status status) {
  switch (status) {
    case READER_TTS_OK: return "OK";
    case READER_TTS_ARGUMENT: return "ARGUMENT";
    case READER_TTS_OWNER: return "OWNER";
    case READER_TTS_BUSY: return "BUSY";
    case READER_TTS_UNAVAILABLE: return "UNAVAILABLE";
    case READER_TTS_UNSUPPORTED: return "UNSUPPORTED";
    case READER_TTS_IO: return "IO";
    case READER_TTS_MEMORY: return "MEMORY";
    case READER_TTS_LIMIT: return "LIMIT";
  }
  return "UNKNOWN";
}

const char *state_name(reader_tts_state state) {
  switch (state) {
    case READER_TTS_INITIALIZING: return "INITIALIZING";
    case READER_TTS_READY: return "READY";
    case READER_TTS_SPEAKING: return "SPEAKING";
    case READER_TTS_PAUSED: return "PAUSED";
    case READER_TTS_STOPPING: return "STOPPING";
    case READER_TTS_CLOSING: return "CLOSING";
    case READER_TTS_CLOSED: return "CLOSED";
    case READER_TTS_SERVICE_UNAVAILABLE: return "SERVICE_UNAVAILABLE";
  }
  return "UNKNOWN";
}

bool to_wide(const char *utf8, std::vector<wchar_t> &out) {
  int length = MultiByteToWideChar(CP_UTF8, 0, utf8, -1, nullptr, 0);
  if (length <= 0) return false;
  out.assign(static_cast<size_t>(length), L'\0');
  return MultiByteToWideChar(CP_UTF8, 0, utf8, -1, out.data(), length) == length;
}

bool read_text(const char *path, std::string &text) {
  std::ifstream file(path, std::ios::binary);
  if (!file) return false;
  text.assign(std::istreambuf_iterator<char>(file), std::istreambuf_iterator<char>());
  return true;
}

int run(const char *text_path, const char *wav_path, double rate, const char *voice) {
  reader_tts *handle = nullptr;
  reader_tts_snapshot snap{};
  reader_tts_voice_list voices{};
  reader_tts_error error{};
  std::string text;
  std::vector<wchar_t> wide_wav;
  reader_tts_status status;
  int waited = 0;
  int started = 0, ranges = 0, finished = 0, failed = 0, stopped = 0, bad_range = 0;
  size_t last_start = 0, max_end = 0;

  if (!read_text(text_path, text) || text.empty() || text.size() > 16384u) {
    std::printf("{\"result\":\"fail\",\"detail\":\"text_unreadable\"}\n");
    return 1;
  }
  if (!to_wide(wav_path, wide_wav)) {
    std::printf("{\"result\":\"fail\",\"detail\":\"wav_path\"}\n");
    return 1;
  }
  status = reader_tts_create(nullptr, &handle, &error);
  if (status != READER_TTS_OK || handle == nullptr) {
    std::printf("{\"result\":\"fail\",\"detail\":\"create:%s\"}\n", status_name(status));
    return 1;
  }
  for (;;) {
    reader_tts_observe(handle, &snap, &error);
    if (snap.state == READER_TTS_READY) break;
    if (snap.state == READER_TTS_SERVICE_UNAVAILABLE) {
      std::printf("{\"result\":\"fail\",\"detail\":\"speech_service_unavailable\"}\n");
      reader_tts_destroy(&handle, nullptr);
      return 1;
    }
    if (waited > 30000) {
      std::printf("{\"result\":\"fail\",\"detail\":\"init_timeout\"}\n");
      reader_tts_destroy(&handle, nullptr);
      return 1;
    }
    Sleep(10);
    waited += 10;
  }
  status = reader_tts_voices(handle, &voices, &error);
  if (status != READER_TTS_OK || voices.count == 0) {
    std::printf("{\"result\":\"fail\",\"detail\":\"voices:%s\"}\n", status_name(status));
    reader_tts_destroy(&handle, nullptr);
    return 1;
  }
  status = reader_tts_windows_set_wav_output(handle, wide_wav.data(), &error);
  if (status != READER_TTS_OK) {
    std::printf("{\"result\":\"fail\",\"detail\":\"wav_output:%s\"}\n", status_name(status));
    reader_tts_voice_list_free(&voices);
    reader_tts_destroy(&handle, nullptr);
    return 1;
  }
  status = reader_tts_speak(handle, 1, text.c_str(), text.size(), voice, rate, &error);
  if (status != READER_TTS_OK) {
    std::printf("{\"result\":\"fail\",\"detail\":\"speak:%s\"}\n", status_name(status));
    reader_tts_voice_list_free(&voices);
    reader_tts_destroy(&handle, nullptr);
    return 1;
  }
  {
    int polls = 0;
    for (;;) {
      reader_tts_event event{};
      int available = 0;
      reader_tts_poll(handle, &event, &available, &error);
      while (available) {
        switch (event.kind) {
          case READER_TTS_STARTED: started++; break;
          case READER_TTS_FINISHED: finished++; break;
          case READER_TTS_STOPPED: stopped++; break;
          case READER_TTS_FAILED: failed++; break;
          case READER_TTS_RANGE:
            ranges++;
            if (!event.has_range || event.start >= event.end || event.end > text.size()
                || event.start < last_start) {
              bad_range = 1;
            }
            last_start = event.start;
            if (event.end > max_end) max_end = event.end;
            break;
          default: bad_range = 1; break;
        }
        reader_tts_poll(handle, &event, &available, &error);
      }
      if (finished || failed || stopped) break;
      if (polls > 12000) break;
      Sleep(5);
      polls++;
    }
  }
  reader_tts_observe(handle, &snap, &error);
  std::printf("{\"result\":\"%s\",\"voices\":%zu,\"started\":%d,\"ranges\":%d,\"finished\":%d,"
              "\"failed\":%d,\"stopped\":%d,\"text_bytes\":%zu,\"max_end\":%zu,\"bad_range\":%d,"
              "\"state_after\":\"%s\",\"capabilities\":%u,\"rate\":%.3f}\n",
              (started == 1 && finished == 1 && failed == 0 && stopped == 0 && ranges > 0 && bad_range == 0
               && snap.state == READER_TTS_READY) ? "pass" : "fail",
              voices.count, started, ranges, finished, failed, stopped, text.size(), max_end, bad_range,
              state_name(snap.state), snap.capabilities, rate);
  reader_tts_voice_list_free(&voices);
  reader_tts_request_close(handle, &error);
  for (waited = 0;; waited += 10) {
    reader_tts_observe(handle, &snap, &error);
    if (snap.state == READER_TTS_CLOSED || waited > 20000) break;
    Sleep(10);
  }
  status = reader_tts_destroy(&handle, &error);
  return (status == READER_TTS_OK && handle == nullptr && snap.state == READER_TTS_CLOSED) ? 0 : 1;
}

}  // namespace

int main(int argc, char **argv) {
  if (argc < 3) {
    std::fprintf(stderr, "usage: tts-probe <text-file> <wav-file> [rate] [voice-id]\n");
    return 2;
  }
  return run(argv[1], argv[2], argc > 3 ? std::atof(argv[3]) : 1.0, argc > 4 ? argv[4] : nullptr);
}
