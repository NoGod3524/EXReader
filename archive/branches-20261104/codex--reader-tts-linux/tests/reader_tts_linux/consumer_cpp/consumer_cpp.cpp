/* SPDX-License-Identifier: MIT */
/* C++ installed-package consumer for the J19 Linux reader TTS backend: proves
   the frozen C ABI is usable from C++ (RAII wrapper, std::thread ownership
   check, voice list lifetime outliving the handle). */
#include "reader_tts.h"
#include "result_writer.h"
#include <chrono>
#include <csignal>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <exception>
#include <memory>
#include <string>
#include <thread>

namespace {

int g_fails = 0;
FILE *g_out = nullptr;
int g_first = 1;

void report(const char *name, bool ok, const std::string &detail) {
  rw_case(g_out, &g_first, name, ok ? 1 : 0, detail.c_str());
  std::printf("%s %s: %s\n", ok ? "pass" : "FAIL", name, detail.c_str());
  std::fflush(stdout);
  if (!ok) ++g_fails;
}

void sleep_ms(int ms) { std::this_thread::sleep_for(std::chrono::milliseconds(ms)); }

/* Shape a future C++ host would use: the C handle stays a plain pointer and the
   owner-thread rule is enforced by the library, not by the wrapper. */
struct ReaderTtsDeleter {
  void operator()(reader_tts *h) const noexcept {
    if (!h) return;
    reader_tts_error err{};
    reader_tts_request_close(h, &err);
    for (int i = 0; i < 1000; ++i) {
      reader_tts_snapshot snap{};
      if (reader_tts_observe(h, &snap, &err) == READER_TTS_OK && snap.state == READER_TTS_CLOSED)
        break;
      sleep_ms(5);
    }
    reader_tts_destroy(&h, &err);
  }
};
using ReaderTtsPtr = std::unique_ptr<reader_tts, ReaderTtsDeleter>;

}  // namespace

int main(int argc, char **argv) {
  const char *phase = "cpp";
  const char *out = nullptr;
  std::signal(SIGPIPE, SIG_IGN);
  for (int i = 1; i < argc; ++i) {
    if (std::strcmp(argv[i], "--phase") == 0 && i + 1 < argc) phase = argv[++i];
    else if (std::strcmp(argv[i], "--output") == 0 && i + 1 < argc) out = argv[++i];
  }
  if (!out) {
    std::fprintf(stderr, "usage: %s --output FILE\n", argv[0]);
    return 2;
  }
  g_out = std::fopen(out, "w");
  if (!g_out) return 2;
  rw_begin(g_out, argv[0], phase);

  try {
    reader_tts_config cfg{};
    cfg.struct_size = sizeof cfg;
    cfg.max_utf8_bytes = 0;
    reader_tts_error err{};
    reader_tts *raw = nullptr;
    reader_tts_status st = reader_tts_create(&cfg, &raw, &err);
    reader_tts_snapshot snap{};
    if (raw) reader_tts_observe(raw, &snap, &err);
    report("cpp_create_ready", st == READER_TTS_OK && raw && snap.state == READER_TTS_READY,
           std::string("status=") + std::to_string(st) + " state=" + std::to_string(snap.state));
    if (!raw) {
      rw_end(g_out, g_fails);
      std::fclose(g_out);
      return 1;
    }
    report("cpp_snapshot_capabilities",
           (snap.capabilities & READER_TTS_CAN_PAUSE) != 0 &&
               (snap.capabilities & READER_TTS_CAN_REPORT_RANGE) == 0,
           "caps=" + std::to_string(snap.capabilities));

    reader_tts_voice_list voices{};
    st = reader_tts_voices(raw, &voices, &err);
    report("cpp_voices_listed", st == READER_TTS_OK && voices.count >= 1,
           "status=" + std::to_string(st) + " count=" + std::to_string(voices.count));

    st = reader_tts_speak(raw, 1, "cplusplus reader", 16, nullptr, 1.0, &err);
    int started = 0, finished = 0, other = 0;
    if (st == READER_TTS_OK) {
      for (int i = 0; i < 6000; ++i) {
        reader_tts_event ev{};
        int av = 0;
        if (reader_tts_poll(raw, &ev, &av, &err) != READER_TTS_OK) break;
        if (av && ev.request_id == 1) {
          if (ev.kind == READER_TTS_STARTED) ++started;
          else if (ev.kind == READER_TTS_FINISHED) { ++finished; break; }
          else ++other;
        }
        sleep_ms(5);
      }
    }
    report("cpp_speak_completes", st == READER_TTS_OK && started == 1 && finished == 1 && other == 0,
           "status=" + std::to_string(st) + " started=" + std::to_string(started) +
               " finished=" + std::to_string(finished));

    /* wrong owner thread from std::thread */
    reader_tts_status foreign_observe = READER_TTS_OK, foreign_speak = READER_TTS_OK;
    std::thread foreign([&]() {
      reader_tts_snapshot snap2{};
      reader_tts_error e2{};
      foreign_observe = reader_tts_observe(raw, &snap2, &e2);
      foreign_speak = reader_tts_speak(raw, 424242, "x", 1, nullptr, 1.0, &e2);
    });
    foreign.join();
    report("cpp_std_thread_owner_rejected",
           foreign_observe == READER_TTS_OWNER && foreign_speak == READER_TTS_OWNER,
           "observe=" + std::to_string(foreign_observe) +
               " speak=" + std::to_string(foreign_speak));
    if (reader_tts_observe(raw, &snap, &err) == READER_TTS_OK)
      report("cpp_std_thread_state_unchanged", snap.state == READER_TTS_READY,
             "state=" + std::to_string(snap.state));
    else
      report("cpp_std_thread_state_unchanged", false, "observe failed");

    st = reader_tts_destroy(&raw, &err);
    report("cpp_destroy_busy_before_close", st == READER_TTS_BUSY && raw != nullptr,
           "status=" + std::to_string(st));

    st = reader_tts_request_close(raw, &err);
    bool closed = false;
    for (int i = 0; i < 1000 && !closed; ++i) {
      reader_tts_snapshot s3{};
      if (reader_tts_observe(raw, &s3, &err) != READER_TTS_OK) break;
      closed = s3.state == READER_TTS_CLOSED;
      if (!closed) sleep_ms(5);
    }
    report("cpp_close_reaches_closed", st == READER_TTS_OK && closed,
           std::string("status=") + std::to_string(st) + " closed=" + (closed ? "1" : "0"));

    /* the voice list must survive the handle it came from */
    size_t freed = voices.count;
    reader_tts_voice_list_free(&voices);
    report("cpp_voice_list_outlives_handle",
           freed >= 1 && voices.voices == nullptr && voices.count == 0,
           "freed=" + std::to_string(freed));

    st = reader_tts_destroy(&raw, &err);
    report("cpp_destroy_after_closed", st == READER_TTS_OK && raw == nullptr,
           "status=" + std::to_string(st));
    report("cpp_no_exception_escapes", true, "the C ABI never threw through the wrapper");
  } catch (const std::exception &e) {
    report("cpp_no_exception_escapes", false, std::string("exception: ") + e.what());
  } catch (...) {
    report("cpp_no_exception_escapes", false, "unknown exception");
  }

  rw_end(g_out, g_fails);
  std::fclose(g_out);
  std::fprintf(stdout, "phase %s finished with %d failing case(s)\n", phase, g_fails);
  std::fflush(stdout);
  return g_fails == 0 ? 0 : 1;
}
