/* SPDX-License-Identifier: MIT */
/* Test worker built from package source with READER_DIAGNOSTIC_TEST_HOOKS.
   The installed consumers never see this build. Arguments that may carry
   non-ASCII or embedded NUL bytes are passed as "hex:<hexdigits>" and decoded
   here, so the same command line means the same bytes on every platform. */
#if defined(_WIN32)
#define _CRT_SECURE_NO_WARNINGS 1
#include <windows.h>
#else
#include <pthread.h>
#include <time.h>
#endif
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "internal.h"

#define RD_OVER 33u
#define RD_COUNTER_IDS 10u

/* Per-call preset storage. No global entry arrays: the thread case builds in
   several threads at once and must not share mutable state. */
typedef struct {
  reader_diag_counter counters[READER_DIAG_MAX_COUNTER_ENTRIES];
  reader_diag_error_count errors[READER_DIAG_MAX_ERROR_ENTRIES];
} preset_storage;

static long g_cancel_after;
static long g_cancel_calls;
static unsigned g_io_failure;

int rd_test_io_failure(unsigned stage) { return g_io_failure == stage; }

static void usage(void) {
  printf("usage: diagnostic-worker <command> [arguments]\n");
  printf("commands: abi status-names defaults build write write-bad-options\n");
  printf("          build-cancel build-bad-options pause-before pause-after\n");
  printf("          threads lifetime case app-version\n");
}

static long parse_long(const char *text) {
  char *end = NULL;
  long value = strtol(text, &end, 10);
  if (end == text || *end != '\0') {
    fprintf(stderr, "bad number: %s\n", text);
    exit(2);
  }
  return value;
}

static int hex_digit(char character) {
  if (character >= '0' && character <= '9') return character - '0';
  if (character >= 'a' && character <= 'f') return character - 'a' + 10;
  if (character >= 'A' && character <= 'F') return character - 'A' + 10;
  return -1;
}

/* Decodes "hex:<digits>" or copies the literal argument. Returns the byte length
   or (size_t)-1 when the argument does not fit. The buffer is always
   NUL-terminated so it can be handed to the library as a C string. */
static size_t decode(const char *argument, char *buffer, size_t capacity) {
  size_t length = strlen(argument);
  if (length >= 4u && strncmp(argument, "hex:", 4u) == 0) {
    size_t hex_length = length - 4u;
    size_t index;
    if (hex_length % 2u != 0u) return (size_t)-1;
    if (hex_length / 2u + 1u > capacity) return (size_t)-1;
    for (index = 0; index < hex_length / 2u; ++index) {
      int high = hex_digit(argument[4u + index * 2u]);
      int low = hex_digit(argument[5u + index * 2u]);
      if (high < 0 || low < 0) return (size_t)-1;
      buffer[index] = (char)((high << 4) | low);
    }
    buffer[hex_length / 2u] = '\0';
    return hex_length / 2u;
  }
  if (length + 1u > capacity) return (size_t)-1;
  memcpy(buffer, argument, length + 1u);
  return length;
}

static void fill_preset(reader_diag_input *in, const char *preset, preset_storage *storage) {
  size_t index;
  memset(storage, 0, sizeof(*storage));
  *in = reader_diag_input_defaults();
  if (strcmp(preset, "typical") == 0 || strcmp(preset, "typical-reversed") == 0) {
    int reversed = strcmp(preset, "typical-reversed") == 0;
    in->app_version = "1.4.2";
    in->platform = READER_DIAG_PLATFORM_WINDOWS;
    in->operation = READER_DIAG_OPERATION_IMPORT;
    in->sdk_abi = 1u;
    in->sdk_major = 3u;
    in->sdk_minor = 40u;
    in->sdk_patch = 0u;
    in->schema_version = 1u;
    in->wire_version = 1u;
    in->generated_at_unix = 1761600000ull;
    in->account_configured = READER_DIAG_TRI_YES;
    in->sync_enabled = READER_DIAG_TRI_YES;
    in->offline_mode = READER_DIAG_TRI_NO;
    if (reversed) {
      storage->counters[0].id = READER_DIAG_COUNTER_PENDING_CHANGES;
      storage->counters[0].value = 0u;
      storage->counters[1].id = READER_DIAG_COUNTER_IMPORT_FAILURES;
      storage->counters[1].value = 3u;
      storage->counters[2].id = READER_DIAG_COUNTER_BOOKS_TOTAL;
      storage->counters[2].value = 42u;
      storage->errors[0].domain = READER_DIAG_DOMAIN_SYNC;
      storage->errors[0].kind = READER_DIAG_KIND_CONFLICT;
      storage->errors[0].count = 1u;
      storage->errors[1].domain = READER_DIAG_DOMAIN_IMPORT;
      storage->errors[1].kind = READER_DIAG_KIND_IO;
      storage->errors[1].count = 2u;
    } else {
      storage->counters[0].id = READER_DIAG_COUNTER_BOOKS_TOTAL;
      storage->counters[0].value = 42u;
      storage->counters[1].id = READER_DIAG_COUNTER_IMPORT_FAILURES;
      storage->counters[1].value = 3u;
      storage->counters[2].id = READER_DIAG_COUNTER_PENDING_CHANGES;
      storage->counters[2].value = 0u;
      storage->errors[0].domain = READER_DIAG_DOMAIN_IMPORT;
      storage->errors[0].kind = READER_DIAG_KIND_IO;
      storage->errors[0].count = 2u;
      storage->errors[1].domain = READER_DIAG_DOMAIN_SYNC;
      storage->errors[1].kind = READER_DIAG_KIND_CONFLICT;
      storage->errors[1].count = 1u;
    }
    in->counters = storage->counters;
    in->counter_count = 3u;
    in->errors = storage->errors;
    in->error_count = 2u;
    return;
  }
  if (strcmp(preset, "max") == 0) {
    static const uint32_t kinds[4] = {READER_DIAG_KIND_ARGUMENT, READER_DIAG_KIND_FORMAT,
                                      READER_DIAG_KIND_MEMORY, READER_DIAG_KIND_UNKNOWN};
    size_t slot = 0u;
    in->app_version = "123456.654321.999999-rc.999";
    in->platform = READER_DIAG_PLATFORM_ANDROID;
    in->operation = READER_DIAG_OPERATION_SEARCH;
    in->sdk_abi = 65535u;
    in->sdk_major = 9999u;
    in->sdk_minor = 9999u;
    in->sdk_patch = 9999u;
    in->schema_version = 65535u;
    in->wire_version = 65535u;
    in->generated_at_unix = READER_DIAG_MAX_UNIX_TIME;
    in->account_configured = READER_DIAG_TRI_YES;
    in->sync_enabled = READER_DIAG_TRI_YES;
    in->offline_mode = READER_DIAG_TRI_YES;
    for (index = 0; index < RD_COUNTER_IDS; ++index, ++slot) {
      storage->counters[slot].id = (uint32_t)(index + 1u);
      storage->counters[slot].value = READER_DIAG_MAX_COUNT;
    }
    slot = 0u;
    for (index = 0; index < 8u; ++index) {
      size_t which;
      for (which = 0; which < 4u; ++which, ++slot) {
        storage->errors[slot].domain = (uint32_t)(index + 1u);
        storage->errors[slot].kind = kinds[which];
        storage->errors[slot].count = READER_DIAG_MAX_COUNT;
      }
    }
    in->counters = storage->counters;
    in->counter_count = RD_COUNTER_IDS;
    in->errors = storage->errors;
    in->error_count = READER_DIAG_MAX_ERROR_ENTRIES;
    return;
  }
  /* "minimal" and anything unknown. */
  in->app_version = "0.1.0";
  in->platform = READER_DIAG_PLATFORM_OTHER;
  in->operation = READER_DIAG_OPERATION_OTHER;
}

static int save(const char *path, const void *data, size_t size) {
  FILE *stream = fopen(path, "wb");
  size_t written;
  if (!stream) return 0;
  written = fwrite(data, 1u, size, stream);
  if (fclose(stream) != 0) return 0;
  return written == size;
}

static int cancel_callback(void *context) {
  (void)context;
  ++g_cancel_calls;
  return (g_cancel_after > 0 && g_cancel_calls >= g_cancel_after) ? 1 : 0;
}

static void emit(reader_diag_status status, const reader_diag_error *error, int out_null) {
  printf("status=%s\n", reader_diag_status_name(status));
  printf("system_error=%d\n", error ? error->system_error : 0);
  printf("message=%s\n", error ? error->message : "");
  printf("out_null=%d\n", out_null);
}

#ifdef READER_DIAGNOSTIC_TEST_HOOKS
static char g_pause_tag[4096];
static int g_pause_mode; /* 0 none, 1 before the commit, 2 after the commit */

static void sleep_ms(unsigned milliseconds) {
#if defined(_WIN32)
  Sleep(milliseconds);
#else
  struct timespec request;
  request.tv_sec = (time_t)(milliseconds / 1000u);
  request.tv_nsec = (long)(milliseconds % 1000u) * 1000000L;
  (void)nanosleep(&request, NULL);
#endif
}

static int file_exists(const char *path) {
  FILE *stream = fopen(path, "rb");
  if (!stream) return 0;
  fclose(stream);
  return 1;
}

/* The parent creates "<marker>.go" to release the pause; the pause gives up after
   a minute so a paused worker can never hang the job. */
static void pause_wait(int mode, const char *suffix) {
  char ready[4300];
  char go[4300];
  FILE *marker;
  unsigned spins;
  if (g_pause_mode != mode || g_pause_tag[0] == '\0') return;
  (void)snprintf(ready, sizeof(ready), "%s.%s", g_pause_tag, suffix);
  (void)snprintf(go, sizeof(go), "%s.go", g_pause_tag);
  marker = fopen(ready, "wb");
  if (marker) {
    (void)fputs("ready\n", marker);
    (void)fclose(marker);
  }
  for (spins = 0; spins < 6000u; ++spins) {
    if (file_exists(go)) return;
    sleep_ms(10u);
  }
}

void rd_test_pause_before_commit(void) { pause_wait(1, "before"); }
void rd_test_pause_after_commit(void) { pause_wait(2, "after"); }
#endif

typedef struct {
  const char *preset;
  const char *reference;
  size_t size;
  size_t iterations;
  size_t mismatches;
} thread_job;

#if defined(_WIN32)
#define RD_THREAD_RET DWORD WINAPI
#define RD_THREAD_ARG LPVOID
#else
#define RD_THREAD_RET void *
#define RD_THREAD_ARG void *
#endif

static RD_THREAD_RET thread_body(RD_THREAD_ARG raw) {
  thread_job *job = (thread_job *)raw;
  size_t iteration;
  preset_storage storage;
  for (iteration = 0; iteration < job->iterations; ++iteration) {
    reader_diag_input in;
    reader_diag_report *report = NULL;
    const char *json;
    size_t size = 0u;
    fill_preset(&in, job->preset, &storage);
    if (reader_diag_report_build(&in, NULL, &report, NULL) != READER_DIAG_OK) {
      ++job->mismatches;
      continue;
    }
    json = reader_diag_report_json(report, &size);
    if (!json || size != job->size || memcmp(json, job->reference, size) != 0)
      ++job->mismatches;
    reader_diag_report_free(report);
  }
#if defined(_WIN32)
  return 0;
#else
  return NULL;
#endif
}

static int command_build(int argc, char **argv) {
  reader_diag_input in;
  preset_storage storage;
  reader_diag_report *report = NULL;
  reader_diag_error error;
  reader_diag_status status;
  const char *json;
  const char *summary;
  size_t json_size = 0u;
  size_t summary_size = 0u;
  size_t json_limit;
  size_t summary_limit;
  if (argc < 7) return 2;
  fill_preset(&in, argv[2], &storage);
  json_limit = (size_t)parse_long(argv[5]);
  summary_limit = (size_t)parse_long(argv[6]);
#ifdef READER_DIAGNOSTIC_TEST_HOOKS
  rd_test_output_limits.json = json_limit;
  rd_test_output_limits.summary = summary_limit;
#else
  (void)json_limit;
  (void)summary_limit;
#endif
  reader_diag_error_clear(&error);
  status = reader_diag_report_build(&in, NULL, &report, &error);
  emit(status, &error, report == NULL);
  if (!report) return status == READER_DIAG_OK ? 1 : 0;
  json = reader_diag_report_json(report, &json_size);
  summary = reader_diag_report_summary(report, &summary_size);
  printf("json_size=%zu\n", json_size);
  printf("summary_size=%zu\n", summary_size);
  printf("json_strlen=%zu\n", json ? strlen(json) : 0u);
  printf("summary_strlen=%zu\n", summary ? strlen(summary) : 0u);
  if (strcmp(argv[3], "-") != 0 && !save(argv[3], json, json_size)) {
    printf("save=0\n");
    reader_diag_report_free(report);
    return 1;
  }
  if (strcmp(argv[4], "-") != 0 && !save(argv[4], summary, summary_size)) {
    printf("save=0\n");
    reader_diag_report_free(report);
    return 1;
  }
  reader_diag_report_free(report);
  return 0;
}

static int command_write(int argc, char **argv) {
  reader_diag_input in;
  preset_storage storage;
  reader_diag_report *report = NULL;
  reader_diag_error error;
  reader_diag_write_options options;
  reader_diag_status status;
  char path[4096];
  long format;
  long cancel_after;
  if (argc < 6) return 2;
  if (decode(argv[2], path, sizeof(path)) == (size_t)-1) {
    printf("decode=0\n");
    return 2;
  }
  fill_preset(&in, argv[3], &storage);
  format = parse_long(argv[4]);
  cancel_after = parse_long(argv[5]);
  reader_diag_error_clear(&error);
  status = reader_diag_report_build(&in, NULL, &report, &error);
  if (status != READER_DIAG_OK) {
    emit(status, &error, report == NULL);
    reader_diag_report_free(report);
    return 1;
  }
  memset(&options, 0, sizeof(options));
  options.struct_size = (uint32_t)sizeof(options);
  options.format = (uint32_t)format;
  g_cancel_after = cancel_after;
  g_cancel_calls = 0;
  if (cancel_after >= 0) options.control.cancelled = cancel_callback;
  status = reader_diag_report_write(report, path, &options, &error);
  emit(status, &error, 0);
  printf("cancel_calls=%ld\n", g_cancel_calls);
  reader_diag_report_free(report);
  return 0;
}

static int command_write_bad_options(int argc, char **argv) {
  reader_diag_input in;
  preset_storage storage;
  reader_diag_report *report = NULL;
  reader_diag_error error;
  reader_diag_write_options options;
  reader_diag_status status;
  char path[4096];
  if (argc < 4) return 2;
  if (decode(argv[2], path, sizeof(path)) == (size_t)-1) return 2;
  fill_preset(&in, argv[3], &storage);
  reader_diag_error_clear(&error);
  status = reader_diag_report_build(&in, NULL, &report, &error);
  if (status != READER_DIAG_OK) {
    emit(status, &error, report == NULL);
    reader_diag_report_free(report);
    return 1;
  }
  memset(&options, 0, sizeof(options));
  options.struct_size = 0u;
  status = reader_diag_report_write(report, path, &options, &error);
  emit(status, &error, 0);
  reader_diag_report_free(report);
  return 0;
}

static int command_build_cancel(int argc, char **argv) {
  reader_diag_input in;
  preset_storage storage;
  reader_diag_report *report = NULL;
  reader_diag_error error;
  reader_diag_build_options options;
  reader_diag_status status;
  if (argc < 4) return 2;
  fill_preset(&in, argv[2], &storage);
  g_cancel_after = parse_long(argv[3]);
  g_cancel_calls = 0;
  memset(&options, 0, sizeof(options));
  options.struct_size = (uint32_t)sizeof(options);
  options.control.cancelled = cancel_callback;
  reader_diag_error_clear(&error);
  status = reader_diag_report_build(&in, &options, &report, &error);
  emit(status, &error, report == NULL);
  printf("cancel_calls=%ld\n", g_cancel_calls);
  reader_diag_report_free(report);
  return 0;
}

static int command_build_bad_options(int argc, char **argv) {
  reader_diag_input in;
  preset_storage storage;
  reader_diag_report *report = NULL;
  reader_diag_error error;
  reader_diag_build_options options;
  reader_diag_status status;
  if (argc < 3) return 2;
  fill_preset(&in, argv[2], &storage);
  memset(&options, 0, sizeof(options));
  options.struct_size = 0u;
  reader_diag_error_clear(&error);
  status = reader_diag_report_build(&in, &options, &report, &error);
  emit(status, &error, report == NULL);
  reader_diag_report_free(report);
  return 0;
}

static int command_pause(int argc, char **argv) {
  reader_diag_input in;
  preset_storage storage;
  reader_diag_report *report = NULL;
  reader_diag_error error;
  reader_diag_write_options options;
  reader_diag_status status;
  char path[4096];
  char marker[4096];
  if (argc < 5) return 2;
  if (decode(argv[2], path, sizeof(path)) == (size_t)-1) return 2;
  if (decode(argv[3], marker, sizeof(marker)) == (size_t)-1) return 2;
  fill_preset(&in, argv[4], &storage);
  reader_diag_error_clear(&error);
  status = reader_diag_report_build(&in, NULL, &report, &error);
  if (status != READER_DIAG_OK) {
    emit(status, &error, report == NULL);
    reader_diag_report_free(report);
    return 1;
  }
#ifdef READER_DIAGNOSTIC_TEST_HOOKS
  (void)snprintf(g_pause_tag, sizeof(g_pause_tag), "%s", marker);
  g_pause_mode = strcmp(argv[1], "pause-before") == 0 ? 1 : 2;
#endif
  memset(&options, 0, sizeof(options));
  options.struct_size = (uint32_t)sizeof(options);
  status = reader_diag_report_write(report, path, &options, &error);
  emit(status, &error, 0);
  reader_diag_report_free(report);
  return 0;
}

static int command_threads(int argc, char **argv) {
  enum { RD_THREADS = 8 };
  reader_diag_input in;
  preset_storage storage;
  reader_diag_report *report = NULL;
  const char *json;
  size_t size = 0u;
  size_t iterations;
  size_t index;
  char *reference;
  thread_job jobs[RD_THREADS];
  if (argc < 4) return 2;
  iterations = (size_t)parse_long(argv[3]);
  fill_preset(&in, argv[2], &storage);
  if (reader_diag_report_build(&in, NULL, &report, NULL) != READER_DIAG_OK) {
    printf("status=BUILD\n");
    return 1;
  }
  json = reader_diag_report_json(report, &size);
  reference = (char *)malloc(size);
  if (!reference) {
    reader_diag_report_free(report);
    return 1;
  }
  memcpy(reference, json, size);
  reader_diag_report_free(report);
  for (index = 0; index < (size_t)RD_THREADS; ++index) {
    jobs[index].preset = argv[2];
    jobs[index].reference = reference;
    jobs[index].size = size;
    jobs[index].iterations = iterations;
    jobs[index].mismatches = 0u;
  }
#if defined(_WIN32)
  {
    HANDLE handles[RD_THREADS];
    for (index = 0; index < (size_t)RD_THREADS; ++index) handles[index] = NULL;
    for (index = 0; index < (size_t)RD_THREADS; ++index) {
      handles[index] = CreateThread(NULL, 0, thread_body, &jobs[index], 0, NULL);
      if (!handles[index]) jobs[index].mismatches = iterations;
    }
    for (index = 0; index < (size_t)RD_THREADS; ++index)
      if (handles[index]) {
        (void)WaitForSingleObject(handles[index], INFINITE);
        (void)CloseHandle(handles[index]);
      }
  }
#else
  {
    pthread_t threads[RD_THREADS];
    int created[RD_THREADS];
    for (index = 0; index < (size_t)RD_THREADS; ++index) {
      created[index] = pthread_create(&threads[index], NULL, thread_body, &jobs[index]) == 0;
      if (!created[index]) jobs[index].mismatches = iterations;
    }
    for (index = 0; index < (size_t)RD_THREADS; ++index)
      if (created[index]) (void)pthread_join(threads[index], NULL);
  }
#endif
  {
    size_t mismatches = 0u;
    for (index = 0; index < (size_t)RD_THREADS; ++index) mismatches += jobs[index].mismatches;
    printf("iterations=%zu\n", iterations * RD_THREADS);
    printf("mismatches=%zu\n", mismatches);
    printf("json_size=%zu\n", size);
  }
  free(reference);
  return 0;
}

static int command_lifetime(int argc, char **argv) {
  reader_diag_input in;
  preset_storage storage;
  reader_diag_report *first = NULL;
  reader_diag_report *second = NULL;
  const char *json;
  size_t size = 0u;
  static char copy[READER_DIAG_MAX_JSON_BYTES + 1u];
  int stable = 1;
  if (argc < 3) return 2;
  fill_preset(&in, "typical", &storage);
  if (reader_diag_report_build(&in, NULL, &first, NULL) != READER_DIAG_OK) {
    printf("status=BUILD\n");
    return 1;
  }
  json = reader_diag_report_json(first, &size);
  memcpy(copy, json, size);
  fill_preset(&in, "max", &storage);
  if (reader_diag_report_build(&in, NULL, &second, NULL) != READER_DIAG_OK) {
    printf("status=BUILD2\n");
    reader_diag_report_free(first);
    return 1;
  }
  if (reader_diag_report_json(first, NULL) != json) stable = 0;
  if (reader_diag_report_json(first, &size) == NULL || memcmp(json, copy, size) != 0) stable = 0;
  reader_diag_report_free(second);
  if (memcmp(json, copy, size) != 0) stable = 0;
  if (!save(argv[2], json, size)) stable = 0;
  printf("json_size=%zu\n", size);
  printf("stable=%d\n", stable);
  reader_diag_report_free(first);
  return stable ? 0 : 1;
}

static int command_case(const char *name) {
  reader_diag_input in;
  preset_storage storage;
  reader_diag_report *report = NULL;
  reader_diag_error error;
  reader_diag_status status;
  reader_diag_counter counters[RD_OVER];
  reader_diag_error_count errors[RD_OVER];
  size_t index;
  fill_preset(&in, "typical", &storage);
  memset(counters, 0, sizeof(counters));
  memset(errors, 0, sizeof(errors));
  reader_diag_error_clear(&error);
  if (strcmp(name, "struct-size-zero") == 0) {
    in.struct_size = 0u;
  } else if (strcmp(name, "struct-size-small") == 0) {
    in.struct_size = (uint32_t)sizeof(in) - 1u;
  } else if (strcmp(name, "abi-version") == 0) {
    in.abi_version = READER_DIAG_ABI_VERSION + 1u;
  } else if (strcmp(name, "reserved") == 0) {
    in.reserved[3] = 1u;
  } else if (strcmp(name, "flag-reserved") == 0) {
    in.flag_reserved[4] = 1u;
  } else if (strcmp(name, "counter-limit") == 0) {
    for (index = 0; index < 17u; ++index) {
      counters[index].id = (uint32_t)(index + 1u);
      counters[index].value = (uint64_t)index;
    }
    in.counters = counters;
    in.counter_count = 17u;
  } else if (strcmp(name, "error-limit") == 0) {
    size_t slot = 0u;
    for (index = 0; index < 3u; ++index) {
      size_t which;
      for (which = 0; which < 11u; ++which, ++slot) {
        errors[slot].domain = (uint32_t)(index + 1u);
        errors[slot].kind = (uint32_t)(which + 1u);
        errors[slot].count = 1u;
      }
    }
    in.errors = errors;
    in.error_count = slot;
  } else if (strcmp(name, "duplicate-counter") == 0) {
    counters[0].id = READER_DIAG_COUNTER_BOOKS_TOTAL;
    counters[0].value = 1u;
    counters[1].id = READER_DIAG_COUNTER_BOOKS_TOTAL;
    counters[1].value = 2u;
    in.counters = counters;
    in.counter_count = 2u;
  } else if (strcmp(name, "duplicate-error") == 0) {
    errors[0].domain = READER_DIAG_DOMAIN_IMPORT;
    errors[0].kind = READER_DIAG_KIND_IO;
    errors[0].count = 1u;
    errors[1] = errors[0];
    in.errors = errors;
    in.error_count = 2u;
  } else if (strcmp(name, "entries-null") == 0) {
    in.counters = NULL;
    in.counter_count = 1u;
  } else if (strcmp(name, "errors-null") == 0) {
    in.errors = NULL;
    in.error_count = 1u;
  } else if (strcmp(name, "input-null") == 0) {
    /* handled below */
  } else if (strcmp(name, "counter-value") == 0) {
    counters[0].id = READER_DIAG_COUNTER_BOOKS_TOTAL;
    counters[0].value = READER_DIAG_MAX_COUNT + 1ull;
    in.counters = counters;
    in.counter_count = 1u;
  } else if (strcmp(name, "counter-id-zero") == 0) {
    counters[0].id = 0u;
    in.counters = counters;
    in.counter_count = 1u;
  } else if (strcmp(name, "counter-id-high") == 0) {
    counters[0].id = 11u;
    in.counters = counters;
    in.counter_count = 1u;
  } else if (strcmp(name, "tri-state") == 0) {
    in.account_configured = 3u;
  } else if (strcmp(name, "kind-zero") == 0) {
    errors[0].domain = READER_DIAG_DOMAIN_IMPORT;
    errors[0].kind = 0u;
    errors[0].count = 1u;
    in.errors = errors;
    in.error_count = 1u;
  } else if (strcmp(name, "kind-high") == 0) {
    errors[0].domain = READER_DIAG_DOMAIN_IMPORT;
    errors[0].kind = READER_DIAG_KIND_UNKNOWN + 1u;
    errors[0].count = 1u;
    in.errors = errors;
    in.error_count = 1u;
  } else if (strcmp(name, "domain-zero") == 0) {
    errors[0].domain = 0u;
    errors[0].kind = READER_DIAG_KIND_IO;
    errors[0].count = 1u;
    in.errors = errors;
    in.error_count = 1u;
  } else if (strcmp(name, "domain-high") == 0) {
    errors[0].domain = READER_DIAG_DOMAIN_OTHER + 1u;
    errors[0].kind = READER_DIAG_KIND_IO;
    errors[0].count = 1u;
    in.errors = errors;
    in.error_count = 1u;
  } else if (strcmp(name, "error-count-zero") == 0) {
    errors[0].domain = READER_DIAG_DOMAIN_IMPORT;
    errors[0].kind = READER_DIAG_KIND_IO;
    errors[0].count = 0u;
    in.errors = errors;
    in.error_count = 1u;
  } else if (strcmp(name, "platform-zero") == 0) {
    in.platform = 0u;
  } else if (strcmp(name, "platform-high") == 0) {
    in.platform = READER_DIAG_PLATFORM_OTHER + 1u;
  } else if (strcmp(name, "operation-zero") == 0) {
    in.operation = 0u;
  } else if (strcmp(name, "operation-high") == 0) {
    in.operation = READER_DIAG_OPERATION_OTHER + 1u;
  } else if (strcmp(name, "generated-at") == 0) {
    in.generated_at_unix = READER_DIAG_MAX_UNIX_TIME + 1ull;
  } else if (strcmp(name, "sdk-abi") == 0) {
    in.sdk_abi = 65536u;
  } else if (strcmp(name, "schema") == 0) {
    in.schema_version = 65536u;
  } else if (strcmp(name, "wire") == 0) {
    in.wire_version = 65536u;
  } else if (strcmp(name, "sdk-major") == 0) {
    in.sdk_major = 10000u;
  } else {
    printf("status=UNKNOWN-CASE\n");
    return 2;
  }
  if (strcmp(name, "input-null") == 0)
    status = reader_diag_report_build(NULL, NULL, &report, &error);
  else
    status = reader_diag_report_build(&in, NULL, &report, &error);
  emit(status, &error, report == NULL);
  reader_diag_report_free(report);
  return 0;
}

static int command_app_version(int argc, char **argv) {
  reader_diag_input in;
  preset_storage storage;
  reader_diag_report *report = NULL;
  reader_diag_error error;
  reader_diag_status status;
  static char text[256];
  size_t length;
  if (argc < 3) return 2;
  length = decode(argv[2], text, sizeof(text));
  if (length == (size_t)-1) {
    printf("decode=0\n");
    return 2;
  }
  fill_preset(&in, "typical", &storage);
  in.app_version = text;
  reader_diag_error_clear(&error);
  status = reader_diag_report_build(&in, NULL, &report, &error);
  printf("input_length=%zu\n", length);
  emit(status, &error, report == NULL);
  reader_diag_report_free(report);
  return 0;
}

int main(int argc, char **argv) {
  if (argc < 2) {
    usage();
    return 2;
  }
  if (strcmp(argv[1], "abi") == 0) {
    printf("abi=%u\n", reader_diag_abi_version());
    printf("abi_macro=%u\n", (unsigned)READER_DIAG_ABI_VERSION);
    printf("format_macro=%u\n", (unsigned)READER_DIAG_FORMAT_VERSION);
    return 0;
  }
  if (strcmp(argv[1], "status-names") == 0) {
    long value;
    for (value = 0; value <= 9; ++value)
      printf("name_%ld=%s\n", value, reader_diag_status_name((reader_diag_status)value));
    return 0;
  }
  if (strcmp(argv[1], "defaults") == 0) {
    reader_diag_input in = reader_diag_input_defaults();
    printf("struct_size=%u\n", in.struct_size);
    printf("sizeof_input=%u\n", (unsigned)sizeof(reader_diag_input));
    printf("abi_version=%u\n", in.abi_version);
    printf("app_version_null=%d\n", in.app_version == NULL);
    printf("platform=%u\n", in.platform);
    printf("operation=%u\n", in.operation);
    printf("generated=%llu\n", (unsigned long long)in.generated_at_unix);
    printf("counter_count=%u\n", (unsigned)in.counter_count);
    printf("error_count=%u\n", (unsigned)in.error_count);
    return 0;
  }
  if (strcmp(argv[1], "build") == 0) return command_build(argc, argv);
  if (strcmp(argv[1], "write") == 0) return command_write(argc, argv);
  if (strcmp(argv[1], "write-fail") == 0) {
    if (argc < 7) return 2;
    g_io_failure = (unsigned)parse_long(argv[6]);
    return command_write(argc, argv);
  }
  if (strcmp(argv[1], "write-bad-options") == 0) return command_write_bad_options(argc, argv);
  if (strcmp(argv[1], "build-cancel") == 0) return command_build_cancel(argc, argv);
  if (strcmp(argv[1], "build-bad-options") == 0) return command_build_bad_options(argc, argv);
  if (strcmp(argv[1], "pause-before") == 0 || strcmp(argv[1], "pause-after") == 0)
    return command_pause(argc, argv);
  if (strcmp(argv[1], "threads") == 0) return command_threads(argc, argv);
  if (strcmp(argv[1], "lifetime") == 0) return command_lifetime(argc, argv);
  if (strcmp(argv[1], "case") == 0) {
    if (argc < 3) return 2;
    return command_case(argv[2]);
  }
  if (strcmp(argv[1], "app-version") == 0) return command_app_version(argc, argv);
  usage();
  return 2;
}
