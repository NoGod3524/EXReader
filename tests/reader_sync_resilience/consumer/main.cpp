/* SPDX-License-Identifier: MIT */
/* Independent host process for the installed account-session and immutable
   sync APIs. Two modes only:

     resilience-consumer session URL PRODUCT CACHE ORIGINALS ACCOUNT TIMEOUT_MS
     resilience-consumer step URL PRODUCT CACHE ORIGINALS SHARD AFTER LIMIT TIMEOUT_MS

   The session mode speaks one control line protocol on stdin. "abort" makes
   the process leave abruptly at an externally observable stage without running
   any destructor, close request or database acknowledgement, which is how this
   package reaches the "process exits after the outbox commit" boundary without
   adding a test hook to the shared modules. The step mode performs exactly one
   bounded reader_sync_step and prints its installed public report.

   Nothing here re-implements or patches session, sync, revisions or WebDAV
   behaviour; both modes only call the installed public C API. */
#include <reader_session.h>
#include <reader_sync.h>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <iostream>
#include <string>
#include <vector>
#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <shellapi.h>
#endif
namespace fs = std::filesystem;

namespace {
std::vector<std::string> arguments(int argc, char **argv) {
  std::vector<std::string> values;
#ifdef _WIN32
  int count = 0;
  wchar_t **wide = CommandLineToArgvW(GetCommandLineW(), &count);
  if (!wide) return values;
  for (int n = 0; n < count; n++) {
    int bytes = WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, wide[n], -1, nullptr, 0, nullptr, nullptr);
    if (!bytes) { values.clear(); break; }
    std::vector<char> value((size_t)bytes);
    WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, wide[n], -1, value.data(), bytes, nullptr, nullptr);
    values.emplace_back(value.data());
  }
  LocalFree(wide);
  (void)argc;
  (void)argv;
#else
  for (int n = 0; n < argc; n++) values.emplace_back(argv[n]);
#endif
  return values;
}

void view(int code, const reader_session_snapshot &v) {
  std::cout << "{\"code\":" << code << ",\"state\":" << (int)v.state << ",\"status\":" << (int)v.status
            << ",\"attempt\":" << v.attempt << ",\"sweeps\":" << v.completed_sweeps << ",\"steps\":" << v.steps
            << ",\"shard\":" << v.shard << ",\"completed_shards\":" << v.completed_shards << ",\"after\":\""
            << v.after << "\",\"pushed\":" << v.pushed << ",\"pulled\":" << v.pulled
            << ",\"originals_verified\":" << v.originals_verified
            << ",\"pending_metadata\":" << v.pending_metadata_observations
            << ",\"pending_original\":" << v.pending_original_observations
            << ",\"dav_code\":" << v.error.dav_code << ",\"revision_code\":" << v.error.revision_code
            << ",\"http_status\":" << v.error.http_status
            << ",\"full_library_complete\":" << v.full_library_complete << "}" << std::endl;
}

struct host {
  fs::path originals;
};

int local_original(void *opaque, const char *key, char *path, size_t capacity) {
  auto &value = *(host *)opaque;
  std::string k = key;
  size_t colon = k.find(':');
  if (colon == std::string::npos) return 1;
  std::string staged = (value.originals / fs::u8path(k.substr(colon + 1) + "." + k.substr(0, colon))).u8string();
  if (staged.size() >= capacity || !fs::exists(fs::u8path(staged))) return 1;
  std::memcpy(path, staged.c_str(), staged.size() + 1);
  return 0;
}

void report(int status, int dav_code, int revision_code, int http_status, const reader_sync_report &r) {
  std::cout << "{\"status\":" << status << ",\"dav_code\":" << dav_code << ",\"revision_code\":" << revision_code
            << ",\"http_status\":" << http_status << ",\"pushed\":" << r.pushed << ",\"pulled\":" << r.pulled
            << ",\"originals_verified\":" << r.originals_verified << ",\"pending_metadata\":" << r.pending_metadata
            << ",\"pending_local_original\":" << r.pending_local_original
            << ",\"remaining_in_shard\":" << r.remaining_in_shard << ",\"shard_complete\":" << r.shard_complete
            << ",\"shard\":" << r.shard << ",\"next_shard\":" << r.next_shard << ",\"shard_count\":" << r.shard_count
            << ",\"after\":\"" << r.after << "\",\"full_library_complete\":" << r.full_library_complete << "}"
            << std::endl;
}

reader_sync_report empty_report(const std::string &shard) {
  reader_sync_report r{};
  r.shard = r.next_shard = (unsigned)std::stoul(shard);
  r.shard_count = 256;
  return r;
}

int session_mode(const std::vector<std::string> &mode_arguments) {
  if (mode_arguments.size() != 6) return 2;
  reader_session_config config{};
  config.dav.root_url = mode_arguments[0].c_str();
  config.dav.authorization = std::getenv("READER_TEST_AUTH");
  config.product_path = mode_arguments[1].c_str();
  config.private_directory = mode_arguments[2].c_str();
  config.original_directory = mode_arguments[3].c_str();
  config.account_id = mode_arguments[4].c_str();
  config.dav.timeout_ms = (unsigned)std::stoul(mode_arguments[5]);
  reader_session *session = nullptr;
  int created = reader_session_create(&config, &session);
  std::cout << "{\"create\":" << created << "}" << std::endl;
  if (created) return 0;
  std::string line;
  while (std::getline(std::cin, line)) {
    if (line == "abort") {
      std::cout << "{\"abort\":7}" << std::endl;
      std::_Exit(7);
    }
    int code = 0;
    if (line == "start") code = reader_session_start(session);
    else if (line == "cancel") code = reader_session_cancel(session);
    else if (line == "close") code = reader_session_request_close(session);
    else if (line == "destroy") code = reader_session_destroy(&session);
    else if (line != "observe") return 2;
    reader_session_snapshot snapshot{};
    if (session) reader_session_observe(session, &snapshot);
    view(code, snapshot);
    if (!session) return 0;
  }
  return 3;
}

int step_mode(const std::vector<std::string> &mode_arguments) {
  // URL PRODUCT CACHE ORIGINALS SHARD AFTER LIMIT TIMEOUT_MS (PRODUCT is the
  // product database path in step mode).
  if (mode_arguments.size() != 8) return 2;
  host owner{fs::u8path(mode_arguments[3])};
  exr_webdav_config dav_config{};
  dav_config.root_url = mode_arguments[0].c_str();
  dav_config.authorization = std::getenv("READER_TEST_AUTH");
  dav_config.timeout_ms = (unsigned)std::stoul(mode_arguments[7]);
  exr_webdav_client *dav = nullptr;
  exr_webdav_error dav_error{};
  int dav_status = exr_webdav_create(&dav_config, &dav, &dav_error);
  if (dav_status) {
    report(3, (int)dav_status, 0, dav_error.http_status, empty_report(mode_arguments[4]));
    return 0;
  }
  reader_revisions *revisions = nullptr;
  reader_revision_error revision_error{};
  int revision_status = reader_revisions_open(mode_arguments[1].c_str(), &revisions, &revision_error);
  if (revision_status) {
    exr_webdav_free(dav);
    report(4, 0, (int)revision_status, 0, empty_report(mode_arguments[4]));
    return 0;
  }
  reader_sync_config config{dav, revisions, mode_arguments[2].c_str(), local_original, &owner};
  reader_sync *sync = nullptr;
  reader_sync_error error{};
  int status = reader_sync_create(&config, &sync, &error);
  reader_sync_report result{};
  if (!status) {
    exr_webdav_control control{nullptr, nullptr, nullptr};
    status = reader_sync_step(sync, (unsigned)std::stoul(mode_arguments[4]),
                              mode_arguments[5] == "-" ? "" : mode_arguments[5].c_str(),
                              (size_t)std::stoul(mode_arguments[6]), &control, &result, &error);
  } else {
    result = empty_report(mode_arguments[4]);
  }
  report(status, error.dav_code, error.revision_code, error.http_status, result);
  reader_sync_free(sync);
  reader_revisions_close(&revisions, nullptr);
  exr_webdav_free(dav);
  return 0;
}
}

int main(int argc, char **argv) {
  try {
    std::vector<std::string> values = arguments(argc, argv);
    if (values.size() < 2) return 2;
    std::vector<std::string> rest(values.begin() + 2, values.end());
    if (values[1] == "session") return session_mode(rest);
    if (values[1] == "step") return step_mode(rest);
    return 2;
  } catch (...) {
    std::cerr << "Resilience consumer failed\n";
    return 2;
  }
}
