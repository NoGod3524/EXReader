/* SPDX-License-Identifier: MIT */
/* Installed public ABI only. Input bytes come from the independent cloud
   checker; no private headers, test hooks or known-secret list is linked. */
#include "reader_diagnostic_report.h"
#include <atomic>
#include <cstdio>
#include <cstring>
#include <string>
#include <thread>
#include <vector>

static int digit(char value) {
  if (value >= '0' && value <= '9') return value - '0';
  if (value >= 'a' && value <= 'f') return value - 'a' + 10;
  return -1;
}

static reader_diag_input input_for(const char *version) {
  reader_diag_input input = reader_diag_input_defaults();
  input.app_version = version;
  input.platform = READER_DIAG_PLATFORM_OTHER;
  input.operation = READER_DIAG_OPERATION_OTHER;
  return input;
}

struct callback_state {
  const reader_diag_report *report;
  const std::string *reference;
  unsigned calls;
  bool ok;
};

static int reenter(void *raw) {
  auto *state = static_cast<callback_state *>(raw);
  ++state->calls;
  size_t size = 0;
  const char *json = reader_diag_report_json(state->report, &size);
  state->ok = state->ok && json && std::string(json, size) == *state->reference;
  reader_diag_input input = input_for("2.3.4");
  reader_diag_report *nested = nullptr;
  state->ok = state->ok &&
      reader_diag_report_build(&input, nullptr, &nested, nullptr) == READER_DIAG_OK;
  reader_diag_report_free(nested);
  return 1;
}

static int snapshot(const char *directory) {
  std::string version = "1.2.3";
  reader_diag_counter counter = {READER_DIAG_COUNTER_BOOKS_TOTAL, 23};
  reader_diag_input input = input_for(version.c_str());
  input.counters = &counter;
  input.counter_count = 1;
  reader_diag_report *report = nullptr;
  if (reader_diag_report_build(&input, nullptr, &report, nullptr) != READER_DIAG_OK)
    return 1;
  size_t size = 0;
  const char *bytes = reader_diag_report_json(report, &size);
  const std::string reference(bytes, size);
  /* Borrowed memory is released/changed only after build returns. */
  version.assign("changed host title");
  counter.value = 99;
  input = input_for("5.6.7");
  std::atomic<unsigned> failures{0};
  std::vector<std::thread> threads;
  for (unsigned i = 0; i < 8; ++i) {
    threads.emplace_back([&]() {
      for (unsigned n = 0; n < 200; ++n) {
        size_t count = 0;
        const char *value = reader_diag_report_json(report, &count);
        if (!value || std::string(value, count) != reference) ++failures;
        reader_diag_report *other = nullptr;
        if (reader_diag_report_build(&input, nullptr, &other, nullptr) != READER_DIAG_OK)
          ++failures;
        reader_diag_report_free(other);
      }
    });
  }
  for (auto &thread : threads) thread.join();
  callback_state state = {report, &reference, 0, true};
  reader_diag_write_options options = {};
  options.struct_size = static_cast<uint32_t>(sizeof(options));
  options.control.cancelled = reenter;
  options.control.context = &state;
  const std::string cancelled = std::string(directory) + "/cancelled.json";
  if (reader_diag_report_write(report, cancelled.c_str(), &options, nullptr) !=
      READER_DIAG_CANCELLED || !state.ok || state.calls != 1) ++failures;
  const std::string path = std::string(directory) + "/snapshot.json";
  if (reader_diag_report_write(report, path.c_str(), nullptr, nullptr) != READER_DIAG_OK)
    ++failures;
  reader_diag_report_free(report);
  std::printf("snapshot_reads=1600\nreentrant_calls=%u\nfailures=%u\n", state.calls,
              failures.load());
  return failures.load() == 0 ? 0 : 1;
}

int main(int argc, char **argv) {
  if (argc == 3 && std::strcmp(argv[1], "snapshot") == 0) return snapshot(argv[2]);
  if (argc != 4 || std::strcmp(argv[1], "inject") != 0) return 2;
  const std::string hex(argv[2]);
  if (hex.size() % 2 != 0 || hex.size() > 4096) return 2;
  std::string value;
  for (size_t i = 0; i < hex.size(); i += 2) {
    const int hi = digit(hex[i]), lo = digit(hex[i + 1]);
    if (hi < 0 || lo < 0) return 2;
    value.push_back(static_cast<char>((hi << 4) | lo));
  }
  reader_diag_input input = input_for(value.c_str());
  reader_diag_report *report = nullptr;
  reader_diag_error error;
  std::memset(&error, 0x5a, sizeof(error));
  const reader_diag_status status = reader_diag_report_build(&input, nullptr, &report, &error);
  std::printf("status=%s\nout_null=%d\nsystem_error=%d\nmessage=%s\n",
              reader_diag_status_name(status), report == nullptr, error.system_error,
              error.message);
  if (report) {
    const std::string path = std::string(argv[3]) + "/report.json";
    const std::string summary = std::string(argv[3]) + "/summary.txt";
    reader_diag_write_options options = {};
    options.struct_size = static_cast<uint32_t>(sizeof(options));
    options.format = READER_DIAG_FORMAT_SUMMARY;
    const bool ok = reader_diag_report_write(report, path.c_str(), nullptr, nullptr) ==
                    READER_DIAG_OK &&
                    reader_diag_report_write(report, summary.c_str(), &options, nullptr) ==
                    READER_DIAG_OK;
    reader_diag_report_free(report);
    if (!ok) return 1;
  }
  return 0;
}
