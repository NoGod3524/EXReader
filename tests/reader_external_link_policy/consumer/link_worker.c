/* SPDX-License-Identifier: MIT */
/* Source-built worker with READER_LINK_POLICY_TEST_HOOKS. Only this target can
   steer allocation failure and observe live allocations; the shipped library
   never defines the macro, which is what makes the memory-failure and commit
   boundary evidence meaningful. */
#include "reader_link_policy.h"
#include "test_hooks.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int failures;

static void verdict(const char* name, int ok) {
  if (!ok) failures++;
  printf("CHK\t%s\t%s\n", name, ok ? "ok" : "bad");
}

static const char* status_name(reader_link_status status) {
  switch (status) {
    case READER_LINK_OK: return "OK";
    case READER_LINK_ARGUMENT: return "ARGUMENT";
    case READER_LINK_MEMORY: return "MEMORY";
    case READER_LINK_CANCELLED: return "CANCELLED";
  }
  return "UNKNOWN";
}

static reader_link_policy* create_default(void) {
  reader_link_policy* policy = NULL;
  if (reader_link_policy_create(NULL, &policy, NULL) != READER_LINK_OK) return NULL;
  return policy;
}

static int zeroed(const reader_link_result* result) {
  return result->action == READER_LINK_ACTION_REJECT && result->reason == READER_LINK_REASON_NONE &&
         result->kind == READER_LINK_KIND_NONE && result->flags == 0u &&
         result->display == NULL && result->display_len == 0 && result->input_bytes == 0 &&
         result->path_len == 0;
}

static int mode_alloc(void) {
  reader_link_policy* policy = NULL;
  reader_link_result result;
  long k;

  rlp_test_begin(1);
  {
    reader_link_status status = reader_link_policy_create(NULL, &policy, NULL);
    printf("CHK\talloc-create-fail1\t%s\t%ld\t%d\n", status_name(status), rlp_test_live(),
           policy == NULL ? 1 : 0);
    if (status != READER_LINK_MEMORY || rlp_test_live() != 0 || policy != NULL) failures++;
  }
  rlp_test_end();

  policy = create_default();
  if (!policy) { fprintf(stderr, "FATAL\tpolicy create failed\n"); return 2; }

  for (k = 1; k <= 3; k++) {
    rlp_test_begin(k);
    memset(&result, 0, sizeof(result));
    result.struct_size = (uint32_t)sizeof(result);
    {
      reader_link_status status =
          reader_link_classify(policy, "ch2.xhtml", 9, "OEBPS/text/ch1.xhtml", NULL, &result,
                               NULL);
      long live = rlp_test_live();
      if (k == 1) {
        printf("CHK\talloc-classify-fail1\t%s\t%ld\t%d\n", status_name(status), live,
               zeroed(&result) ? 1 : 0);
        if (status != READER_LINK_MEMORY || live != 0 || !zeroed(&result)) failures++;
      } else {
        printf("CHK\talloc-classify-no-fail%ld\t%s\t%ld\n", k, status_name(status), live);
        if (status != READER_LINK_OK || live != 1 || result.action != READER_LINK_ACTION_INTERNAL)
          failures++;
        reader_link_result_free(&result);
        if (rlp_test_live() != 0) failures++;
      }
    }
    rlp_test_end();
  }

  rlp_test_begin(0);
  memset(&result, 0, sizeof(result));
  result.struct_size = (uint32_t)sizeof(result);
  {
    reader_link_status status =
        reader_link_classify(policy, "https://example.com/x", 20, NULL, NULL, &result, NULL);
    long allocations = rlp_test_allocations();
    printf("CHK\talloc-count\t%s\t%ld\n", status_name(status), allocations);
    if (status != READER_LINK_OK || allocations != 1 || rlp_test_live() != 1) failures++;
    reader_link_result_free(&result);
    printf("CHK\talloc-released\t%ld\n", rlp_test_live());
    if (rlp_test_live() != 0) failures++;
  }
  rlp_test_end();
  reader_link_policy_destroy(policy);
  return failures ? 1 : 0;
}

typedef struct {
  long threshold;
  long calls;
  const reader_link_policy* policy;
  int reentered;
  int inner_status;
} cancel_state;

static int cancel_after(void* context) {
  cancel_state* state = (cancel_state*)context;
  state->calls++;
  if (state->policy && !state->reentered) {
    reader_link_result inner;
    memset(&inner, 0, sizeof(inner));
    inner.struct_size = (uint32_t)sizeof(inner);
    state->reentered = 1;
    state->inner_status =
        (int)reader_link_classify(state->policy, "#inside", 7, NULL, NULL, &inner, NULL);
    if (state->inner_status == READER_LINK_OK &&
        inner.action == READER_LINK_ACTION_INTERNAL && inner.kind == READER_LINK_KIND_FRAGMENT)
      state->inner_status = 1000; /* mark the reentrant result as correct */
    reader_link_result_free(&inner);
  }
  return (state->threshold > 0 && state->calls >= state->threshold) ? 1 : 0;
}

static int mode_cancel(void) {
  reader_link_policy* policy = create_default();
  reader_link_result result;
  char* big = (char*)malloc(READER_LINK_DEFAULT_INPUT_BYTES + 1);
  long thresholds[] = {1, 2, 3, 4, 0};
  const char* names[] = {"cancel-entry", "cancel-mid", "cancel-late", "cancel-before-commit",
                         "cancel-never"};
  size_t i;

  if (!policy || !big) { fprintf(stderr, "FATAL\tsetup failed\n"); return 2; }
  memset(big, 'a', READER_LINK_DEFAULT_INPUT_BYTES);
  big[READER_LINK_DEFAULT_INPUT_BYTES] = 0;

  for (i = 0; i < sizeof(thresholds) / sizeof(thresholds[0]); i++) {
    cancel_state state;
    reader_link_control control;
    reader_link_status status;
    memset(&state, 0, sizeof(state));
    state.threshold = thresholds[i];
    control.cancelled = cancel_after;
    control.context = &state;
    memset(&result, 0, sizeof(result));
    result.struct_size = (uint32_t)sizeof(result);
    rlp_test_begin(0);
    status = reader_link_classify(policy, big, READER_LINK_DEFAULT_INPUT_BYTES, NULL, &control,
                                  &result, NULL);
    printf("CHK\t%s\t%s\t%ld\t%ld\t%d\n", names[i], status_name(status), state.calls,
           rlp_test_live(), zeroed(&result) ? 1 : 0);
    if (thresholds[i] == 0) {
      /* No cancel: entry plus the two in-scan polls plus the pre-commit poll
         still run, and the link is rejected without any commit of a host action. */
      if (status != READER_LINK_OK || state.calls != 4 || result.action != READER_LINK_ACTION_REJECT ||
          !result.display)
        failures++;
    } else {
      if (status != READER_LINK_CANCELLED || state.calls != thresholds[i] ||
          rlp_test_live() != 0 || !zeroed(&result))
        failures++;
    }
    if (thresholds[i] == 0 && result.display) reader_link_result_free(&result);
    rlp_test_end();
  }

  {
    cancel_state state;
    reader_link_control control;
    reader_link_status status;
    memset(&state, 0, sizeof(state));
    state.threshold = 1;
    state.policy = policy;
    control.cancelled = cancel_after;
    control.context = &state;
    memset(&result, 0, sizeof(result));
    result.struct_size = (uint32_t)sizeof(result);
    rlp_test_begin(0);
    status = reader_link_classify(policy, "https://example.com/a", 21, NULL, &control, &result,
                                  NULL);
    verdict("cancel-reentrant-classify",
            status == READER_LINK_CANCELLED && state.reentered == 1 &&
                state.inner_status == 1000 && rlp_test_live() == 0 && zeroed(&result));
    rlp_test_end();
  }

  free(big);
  reader_link_policy_destroy(policy);
  return failures ? 1 : 0;
}

static int mode_lifetime(void) {
  reader_link_policy* policy = NULL;
  reader_link_result result;
  char* input = (char*)malloc(24);
  const char expected[] = "ch2.xhtml#sec-1";
  size_t length = strlen(expected);

  if (!input) { fprintf(stderr, "FATAL\tsetup failed\n"); return 2; }
  rlp_test_begin(0);
  policy = create_default();
  if (!policy) { fprintf(stderr, "FATAL\tsetup failed\n"); return 2; }
  memcpy(input, expected, length + 1);
  memset(&result, 0, sizeof(result));
  result.struct_size = (uint32_t)sizeof(result);
  if (reader_link_classify(policy, input, length, "OEBPS/text/ch1.xhtml", NULL, &result, NULL) !=
      READER_LINK_OK) {
    fprintf(stderr, "FATAL\tclassify failed\n");
    return 2;
  }
  reader_link_policy_destroy(policy);
  policy = NULL;
  memset(input, 0, length);
  verdict("worker-lifetime-after-policy",
          result.display && !memcmp(result.display, expected, length) &&
              result.display[length] == 0 && result.display_len == length &&
              result.kind == READER_LINK_KIND_CONTAINER_PATH &&
              result.fragment_offset == 10 && result.fragment_len == 5);
  reader_link_result_free(&result);
  verdict("worker-lifetime-released", rlp_test_live() == 0 && !result.display);
  rlp_test_end();
  free(input);
  return failures ? 1 : 0;
}

static int mode_limits(void) {
  reader_link_policy* policy = NULL;
  reader_link_policy_options options;
  reader_link_result result;
  char* big;
  char* bigger;

  memset(&options, 0, sizeof(options));
  options.struct_size = (uint32_t)sizeof(options);
  options.max_input_bytes = READER_LINK_MAX_INPUT_BYTES;
  if (reader_link_policy_create(&options, &policy, NULL) != READER_LINK_OK) return 2;
  big = (char*)malloc(READER_LINK_MAX_INPUT_BYTES + 1);
  bigger = (char*)malloc(READER_LINK_MAX_INPUT_BYTES + 2);
  if (!big || !bigger) return 2;
  memset(big, 'a', READER_LINK_MAX_INPUT_BYTES);
  big[READER_LINK_MAX_INPUT_BYTES] = 0;
  memset(bigger, 'a', READER_LINK_MAX_INPUT_BYTES + 1);
  bigger[READER_LINK_MAX_INPUT_BYTES + 1] = 0;

  memset(&result, 0, sizeof(result));
  result.struct_size = (uint32_t)sizeof(result);
  printf("CHK\tlimit-ceiling-accepted\t%s\n",
         status_name(reader_link_classify(policy, big, READER_LINK_MAX_INPUT_BYTES, NULL, NULL,
                                          &result, NULL)));
  printf("CHK\tlimit-ceiling-action\t%s\t%d\n",
         reader_link_reason_name(result.reason), result.display ? 1 : 0);
  reader_link_result_free(&result);

  memset(&result, 0, sizeof(result));
  result.struct_size = (uint32_t)sizeof(result);
  {
    reader_link_status status =
        reader_link_classify(policy, bigger, READER_LINK_MAX_INPUT_BYTES + 1, NULL, NULL,
                             &result, NULL);
    printf("CHK\tlimit-over-rejected\t%s\t%s\n", status_name(status),
           reader_link_reason_name(result.reason));
  }
  if (result.display) failures++;
  reader_link_result_free(&result);

  reader_link_policy_destroy(policy);
  free(big);
  free(bigger);
  return failures ? 1 : 0;
}

int main(int argc, char** argv) {
  if (argc < 2) {
    fprintf(stderr, "usage: link-worker alloc|cancel|lifetime|limits\n");
    return 2;
  }
  if (!strcmp(argv[1], "alloc")) {
    if (mode_alloc() != 0) return 1;
  } else if (!strcmp(argv[1], "cancel")) {
    if (mode_cancel() != 0) return 1;
  } else if (!strcmp(argv[1], "lifetime")) {
    if (mode_lifetime() != 0) return 1;
  } else if (!strcmp(argv[1], "limits")) {
    if (mode_limits() != 0) return 1;
  } else {
    fprintf(stderr, "unknown mode %s\n", argv[1]);
    return 2;
  }
  printf("link-worker-ok\n");
  return 0;
}
