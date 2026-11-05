/* SPDX-License-Identifier: MIT */
/* C++ consumer of the installed package: proves the installed header is usable
   from C++ (extern "C" block) and that the report lifetime fits RAII. */
#include <cstdio>
#include <cstring>
#include <string>

#include "reader_diagnostic_report.h"

namespace {

struct report_owner {
  reader_diag_report *report = nullptr;
  report_owner() = default;
  report_owner(const report_owner &) = delete;
  report_owner &operator=(const report_owner &) = delete;
  ~report_owner() { reader_diag_report_free(report); }
};

int failures = 0;

void expect(bool condition, const char *what) {
  if (!condition) {
    ++failures;
    std::printf("fail=%s\n", what);
  }
}

}  // namespace

int main(int argc, char **argv) {
  if (argc < 2) {
    std::printf("usage: diagnostic-cpp-consumer <work-directory>\n");
    return 2;
  }
  std::string directory(argv[1]);
  std::string path = directory + "/cpp-report.json";
  std::string summary_path = directory + "/cpp-summary.txt";

  reader_diag_input input = reader_diag_input_defaults();
  input.app_version = "3.0.0-beta";
  input.platform = READER_DIAG_PLATFORM_LINUX;
  input.operation = READER_DIAG_OPERATION_SEARCH;
  input.sdk_abi = 1u;
  input.sdk_major = 3u;
  input.sdk_minor = 40u;
  input.sdk_patch = 0u;
  input.schema_version = 1u;
  input.wire_version = 1u;
  input.account_configured = READER_DIAG_TRI_NO;
  input.sync_enabled = READER_DIAG_TRI_UNKNOWN;
  input.offline_mode = READER_DIAG_TRI_YES;
  reader_diag_counter counter;
  counter.id = READER_DIAG_COUNTER_SEARCH_FAILURES;
  counter.value = 7u;
  input.counters = &counter;
  input.counter_count = 1u;
  reader_diag_error_count problem;
  problem.domain = READER_DIAG_DOMAIN_SEARCH;
  problem.kind = READER_DIAG_KIND_LIMIT;
  problem.count = 4u;
  input.errors = &problem;
  input.error_count = 1u;

  report_owner owner;
  reader_diag_error error;
  reader_diag_error_clear(&error);
  reader_diag_status status = reader_diag_report_build(&input, nullptr, &owner.report, &error);
  expect(status == READER_DIAG_OK, "build");
  expect(owner.report != nullptr, "report");

  size_t json_size = 0u;
  size_t summary_size = 0u;
  const char *json = reader_diag_report_json(owner.report, &json_size);
  const char *summary = reader_diag_report_summary(owner.report, &summary_size);
  expect(json != nullptr && std::strlen(json) == json_size, "json");
  expect(summary != nullptr && std::strlen(summary) == summary_size, "summary");
  expect(json_size > 0u, "json-size");
  expect(std::strstr(summary, "EXReader diagnostic report") != nullptr, "summary-prefix");

  reader_diag_write_options options = {};
  options.struct_size = static_cast<uint32_t>(sizeof(options));
  status = reader_diag_report_write(owner.report, path.c_str(), &options, &error);
  expect(status == READER_DIAG_OK, "write-json");
  options.format = READER_DIAG_FORMAT_SUMMARY;
  status = reader_diag_report_write(owner.report, summary_path.c_str(), &options, &error);
  expect(status == READER_DIAG_OK, "write-summary");

  std::printf("json_size=%zu\n", json_size);
  std::printf("summary_size=%zu\n", summary_size);
  std::printf("failures=%d\n", failures);
  if (failures != 0) return 1;
  std::printf("cpp-consumer-ok\n");
  return 0;
}
