/* SPDX-License-Identifier: MIT */
/* Installed-package C++ consumer: drives the real reader_session with two
 * activation plans and proves a second account cannot borrow the first
 * account's product library. No credential is used or printed. */
#include <reader_account_profiles.h>
#include <reader_session.h>

#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <thread>
#include <vector>

#if defined(_WIN32)
#include <windows.h>
#endif

namespace {

struct session_outcome {
  int create = -1;
  int state = -1;
  int status = -1;
  int closed = -1;
  int destroyed = -1;
};

std::string binding_path(const reader_account_profiles_activation &plan) {
  return std::string(plan.product_path) + ".sync-account";
}

std::string expected_binding(const reader_account_profiles_activation &plan) {
  return std::string("EXReader account v1\n") + plan.profile.account_id + "\n" +
         plan.profile.root_url + "\n";
}

bool read_file(const std::string &path, std::string &out) {
  FILE *file = std::fopen(path.c_str(), "rb");
  char buffer[256];
  size_t got;
  out.clear();
  if (!file) return false;
  while ((got = std::fread(buffer, 1, sizeof(buffer), file)) > 0) out.append(buffer, got);
  std::fclose(file);
  return true;
}

session_outcome run_session(const reader_account_profiles_activation &plan,
                            const std::string &account, const std::string &url,
                            unsigned timeout_ms) {
  session_outcome outcome;
  reader_session_config config;
  reader_session *session = nullptr;
  std::memset(&config, 0, sizeof(config));
  config.product_path = plan.product_path;
  config.private_directory = plan.private_directory;
  config.original_directory = plan.original_directory;
  config.account_id = account.c_str();
  config.dav.root_url = url.c_str();
  config.dav.authorization = nullptr;
  config.dav.timeout_ms = timeout_ms;
  outcome.create = (int)reader_session_create(&config, &session);
  if (outcome.create != READER_SESSION_OK || !session) return outcome;
  if (reader_session_start(session) != READER_SESSION_OK) {
    (void)reader_session_request_close(session);
    for (int attempt = 0; attempt < 1500; ++attempt) {
      reader_session_snapshot snapshot;
      std::memset(&snapshot, 0, sizeof(snapshot));
      (void)reader_session_observe(session, &snapshot);
      if (snapshot.state == READER_SESSION_CLOSED) {
        outcome.closed = 1;
        break;
      }
      std::this_thread::sleep_for(std::chrono::milliseconds(20));
    }
    outcome.destroyed = (int)reader_session_destroy(&session);
    outcome.create = -1;
    return outcome;
  }
  for (int attempt = 0; attempt < 1500; ++attempt) {
    reader_session_snapshot snapshot;
    std::memset(&snapshot, 0, sizeof(snapshot));
    (void)reader_session_observe(session, &snapshot);
    if (snapshot.state == READER_SESSION_FAILED || snapshot.state == READER_SESSION_FINISHED ||
        snapshot.state == READER_SESSION_CANCELLED || snapshot.state == READER_SESSION_CLOSED) {
      outcome.state = (int)snapshot.state;
      outcome.status = (int)snapshot.status;
      break;
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(20));
  }
  (void)reader_session_request_close(session);
  for (int attempt = 0; attempt < 1500; ++attempt) {
    reader_session_snapshot snapshot;
    std::memset(&snapshot, 0, sizeof(snapshot));
    (void)reader_session_observe(session, &snapshot);
    if (snapshot.state == READER_SESSION_CLOSED) {
      outcome.closed = 1;
      break;
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(20));
  }
  outcome.destroyed = (int)reader_session_destroy(&session);
  return outcome;
}

int prepare(const char *store, const char *id, reader_account_profiles_activation &plan) {
  std::memset(&plan, 0, sizeof(plan));
  plan.struct_size = (uint32_t)sizeof(plan);
  reader_account_profiles_error error;
  reader_account_profiles_error_clear(&error);
  return (int)reader_account_profiles_prepare_activation(store, id, nullptr, &plan, &error);
}

int verify(const char *store, const reader_account_profiles_activation &plan) {
  reader_account_profiles_error error;
  reader_account_profiles_error_clear(&error);
  return (int)reader_account_profiles_verify_activation(store, &plan, nullptr, &error);
}

}  // namespace

int run(int argc, char **argv) {
  if (argc != 4) {
    std::fprintf(stderr, "usage: profiles-session-consumer <store> <profile-a> <profile-b>\n");
    return 2;
  }
  const char *store = argv[1];
  reader_account_profiles_activation plan_a;
  reader_account_profiles_activation plan_b;
  int prepare_a = prepare(store, argv[2], plan_a);
  int prepare_b = prepare(store, argv[3], plan_b);
  bool distinct = prepare_a == 0 && prepare_b == 0 &&
                  std::strcmp(plan_a.product_path, plan_b.product_path) != 0;
  session_outcome a = prepare_a == 0
                          ? run_session(plan_a, plan_a.profile.account_id, plan_a.profile.root_url,
                                        2000u)
                          : session_outcome{};
  std::string text;
  bool binding_a = prepare_a == 0 && read_file(binding_path(plan_a), text) &&
                   text == expected_binding(plan_a);
  int verify_a = prepare_a == 0 ? verify(store, plan_a) : -1;
  session_outcome borrow = distinct ? run_session(plan_a, plan_b.profile.account_id,
                                                  plan_b.profile.root_url, 2000u)
                                    : session_outcome{};
  session_outcome own_b = distinct ? run_session(plan_b, plan_b.profile.account_id,
                                                 plan_b.profile.root_url, 2000u)
                                   : session_outcome{};
  std::string text_b;
  bool binding_b = distinct && read_file(binding_path(plan_b), text_b) &&
                   text_b == expected_binding(plan_b);
  int verify_b = distinct ? verify(store, plan_b) : -1;
  std::printf(
      "{\"prepare_a\":%d,\"prepare_b\":%d,\"distinct\":%s,\"create_a\":%d,\"state_a\":%d,"
      "\"status_a\":%d,\"closed_a\":%d,\"destroy_a\":%d,\"binding_a\":%s,\"verify_a\":%d,"
      "\"borrow_create\":%d,\"borrow_state\":%d,\"borrow_status\":%d,\"borrow_closed\":%d,"
      "\"own_b_create\":%d,\"own_b_status\":%d,\"own_b_closed\":%d,\"binding_b\":%s,"
      "\"verify_b\":%d}\n",
      prepare_a, prepare_b, distinct ? "true" : "false", a.create, a.state, a.status, a.closed,
      a.destroyed, binding_a ? "true" : "false", verify_a, borrow.create, borrow.state,
      borrow.status, borrow.closed, own_b.create, own_b.status, own_b.closed,
      binding_b ? "true" : "false", verify_b);
  return 0;
}

#if defined(_WIN32)
static char *wide_to_utf8(const wchar_t *text) {
  int needed = WideCharToMultiByte(CP_UTF8, 0, text, -1, NULL, 0, NULL, NULL);
  char *utf8;
  if (needed <= 0) return NULL;
  utf8 = static_cast<char *>(std::malloc(static_cast<size_t>(needed)));
  if (!utf8) return NULL;
  if (WideCharToMultiByte(CP_UTF8, 0, text, -1, utf8, needed, NULL, NULL) != needed) {
    std::free(utf8);
    return NULL;
  }
  return utf8;
}

int wmain(int argc, wchar_t **argv) {
  std::vector<char *> utf8(static_cast<size_t>(argc) + 1u, nullptr);
  int result;
  for (int index = 0; index < argc; ++index) {
    utf8[static_cast<size_t>(index)] = wide_to_utf8(argv[index]);
    if (!utf8[static_cast<size_t>(index)]) return 2;
  }
  result = run(argc, utf8.data());
  for (int index = 0; index < argc; ++index) std::free(utf8[static_cast<size_t>(index)]);
  return result;
}
#else
int main(int argc, char **argv) { return run(argc, argv); }
#endif
