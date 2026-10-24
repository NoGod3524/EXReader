// SPDX-License-Identifier: MIT
// Installed C++ consumer: proves the shipped header is usable from C++17, that a
// single immutable policy may be classified from several threads at once, that
// the cancel callback may re-enter the same policy, and that the returned
// display string outlives both the input buffer and the policy.
#include "reader_link_policy.h"

#include <atomic>
#include <cstdio>
#include <cstring>
#include <iterator>
#include <memory>
#include <string>
#include <thread>
#include <vector>

namespace {

int failures;

void verdict(const char* name, bool ok) {
  if (!ok) ++failures;
  std::printf("CHK\t%s\t%s\n", name, ok ? "ok" : "bad");
}

struct PolicyDeleter {
  void operator()(reader_link_policy* policy) const { reader_link_policy_destroy(policy); }
};
using Policy = std::unique_ptr<reader_link_policy, PolicyDeleter>;

Policy make_policy() {
  reader_link_policy* raw = nullptr;
  if (reader_link_policy_create(nullptr, &raw, nullptr) != READER_LINK_OK) return Policy(nullptr);
  return Policy(raw);
}

struct Outcome {
  reader_link_status status = READER_LINK_ARGUMENT;
  reader_link_action action = READER_LINK_ACTION_REJECT;
  reader_link_kind kind = READER_LINK_KIND_NONE;
  std::string display;
};

Outcome classify(const reader_link_policy* policy, const char* text, const char* base) {
  Outcome out;
  reader_link_result result;
  std::memset(&result, 0, sizeof(result));
  result.struct_size = static_cast<uint32_t>(sizeof(result));
  out.status = reader_link_classify(policy, text, std::strlen(text), base, nullptr, &result,
                                    nullptr);
  if (out.status == READER_LINK_OK) {
    out.action = result.action;
    out.kind = result.kind;
    out.display.assign(result.display ? result.display : "", result.display_len);
  }
  reader_link_result_free(&result);
  return out;
}

struct Reentry {
  const reader_link_policy* policy = nullptr;
  std::atomic<int> inner_status{-1};
  std::atomic<int> inner_action{-1};
  std::atomic<int> calls{0};
};

int reentrant_cancel(void* context) {
  Reentry* state = static_cast<Reentry*>(context);
  state->calls.fetch_add(1);
  // Re-entering the same policy from the cancel callback must be safe.
  const Outcome inner = classify(state->policy, "#reentered", nullptr);
  state->inner_status.store(static_cast<int>(inner.status));
  state->inner_action.store(static_cast<int>(inner.action));
  return 1;  // cancel the outer classification
}

const char* const k_thread_inputs[] = {
    "ch2.xhtml#sec-1",
    "https://example.com/a?b=1#frag",
    "javascript:alert(1)",
    "../images/a.png",
};

reader_link_action expected_action(const char* text) {
  if (!std::strncmp(text, "https:", 6)) return READER_LINK_ACTION_NEEDS_HOST;
  if (!std::strncmp(text, "javascript:", 11)) return READER_LINK_ACTION_REJECT;
  return READER_LINK_ACTION_INTERNAL;
}

}  // namespace

int main() {
  verdict("cpp-installed-header",
          std::strcmp(READER_LINK_POLICY_VERSION_STRING, "0.1.0") == 0 &&
              READER_LINK_POLICY_ABI_VERSION == 1u && READER_LINK_ACTION_NEEDS_HOST == 2);

  {
    // RAII lifetime: the display string must survive the policy and the input.
    Policy policy = make_policy();
    static const char kInput[] = "https://example.com/cpp";
    std::vector<char> input(sizeof(kInput));
    std::memcpy(input.data(), kInput, sizeof(kInput));
    Outcome out = classify(policy.get(), input.data(), "OEBPS/text/ch1.xhtml");
    std::memset(input.data(), 0x7f, sizeof(kInput) - 1);
    policy.reset();
    verdict("cpp-raii-lifetime",
            out.status == READER_LINK_OK && out.action == READER_LINK_ACTION_NEEDS_HOST &&
                out.display == "https://example.com/cpp");
  }

  {
    Policy policy = make_policy();
    const int kThreads = 8;
    const int kIterations = 200;
    std::vector<std::thread> threads;
    std::atomic<int> mismatches{0};
    std::vector<Outcome> reference;
    for (const char* text : k_thread_inputs) {
      reference.push_back(classify(policy.get(), text, "OEBPS/text/ch1.xhtml"));
    }
    for (int t = 0; t < kThreads; ++t) {
      threads.emplace_back([&]() {
        for (int i = 0; i < kIterations; ++i) {
          for (std::size_t k = 0; k < std::size(k_thread_inputs); ++k) {
            const Outcome out =
                classify(policy.get(), k_thread_inputs[k], "OEBPS/text/ch1.xhtml");
            const Outcome& want = reference[k];
            if (out.status != want.status || out.action != want.action ||
                out.kind != want.kind || out.display != want.display ||
                out.action != expected_action(k_thread_inputs[k])) {
              mismatches.fetch_add(1);
            }
          }
        }
      });
    }
    for (std::thread& thread : threads) thread.join();
    verdict("cpp-threaded-classify", mismatches.load() == 0);
    verdict("cpp-thread-results-identical",
            reference.size() == std::size(k_thread_inputs) &&
                reference[1].action == READER_LINK_ACTION_NEEDS_HOST &&
                reference[2].action == READER_LINK_ACTION_REJECT);
  }

  {
    Policy policy = make_policy();
    Reentry state;
    state.policy = policy.get();
    reader_link_control control{reentrant_cancel, &state};
    const char* text = "https://example.com/cancel";
    reader_link_result result;
    std::memset(&result, 0, sizeof(result));
    result.struct_size = static_cast<uint32_t>(sizeof(result));
    const reader_link_status status = reader_link_classify(
        policy.get(), text, std::strlen(text), nullptr, &control, &result, nullptr);
    const bool committed = result.display != nullptr || result.display_len != 0;
    reader_link_result_free(&result);
    verdict("cpp-reentrant-cancel",
            status == READER_LINK_CANCELLED && state.calls.load() == 1 && !committed &&
                state.inner_status.load() == READER_LINK_OK &&
                state.inner_action.load() == READER_LINK_ACTION_INTERNAL);
  }

  {
    Policy policy = make_policy();
    bool named = true;
    for (int action = 0; action <= 2; ++action) {
      const char* name = reader_link_action_name(static_cast<reader_link_action>(action));
      named = named && name && *name && std::strcmp(name, "UNKNOWN") != 0;
    }
    for (int reason = 0; reason <= 21; ++reason) {
      const char* name = reader_link_reason_name(static_cast<reader_link_reason>(reason));
      named = named && name && *name && std::strcmp(name, "UNKNOWN") != 0;
    }
    const Outcome rejected = classify(policy.get(), "javascript:alert(1)", nullptr);
    verdict("cpp-reject-keeps-display",
            named && rejected.action == READER_LINK_ACTION_REJECT &&
                rejected.display == "javascript:alert(1)");
  }

  if (failures) {
    std::printf("cpp-consumer-failed %d\n", failures);
    return 1;
  }
  std::printf("cpp-consumer-ok\n");
  return 0;
}
