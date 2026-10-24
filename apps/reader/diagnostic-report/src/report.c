/* SPDX-License-Identifier: MIT */
#if defined(_WIN32)
#define _CRT_SECURE_NO_WARNINGS 1
#endif
#include "internal.h"

#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define RD_PLATFORM_MAX 6u
#define RD_OPERATION_MAX 5u
#define RD_DOMAIN_MAX 8u
#define RD_KIND_MAX 13u
#define RD_COUNTER_MAX 10u

static const char *const rd_platform_names[RD_PLATFORM_MAX + 1u] = {
  NULL, "windows", "linux", "macos", "ios", "android", "other"};
static const char *const rd_operation_names[RD_OPERATION_MAX + 1u] = {
  NULL, "import", "sync", "reading", "search", "other"};
static const char *const rd_domain_names[RD_DOMAIN_MAX + 1u] = {
  NULL, "library", "import", "sync", "reading", "search", "storage", "account", "other"};
static const char *const rd_kind_names[RD_KIND_MAX + 1u] = {
  NULL, "ARGUMENT", "IO", "FORMAT", "VERSION", "RANGE", "CANCELLED", "LIMIT", "MEMORY",
  "BUSY", "NOT_FOUND", "CONFLICT", "INTERNAL", "UNKNOWN"};
static const char *const rd_counter_names[RD_COUNTER_MAX + 1u] = {
  NULL, "books_total", "import_attempts", "import_failures", "sync_attempts",
  "sync_failures", "sync_conflicts", "open_failures", "render_failures",
  "search_failures", "pending_changes"};
static const char *const rd_tri_names[3] = {"unknown", "no", "yes"};

#ifdef READER_DIAGNOSTIC_TEST_HOOKS
rd_test_limits rd_test_output_limits = {0u, 0u};
#endif

uint32_t reader_diag_abi_version(void) { return READER_DIAG_ABI_VERSION; }

const char *reader_diag_status_name(reader_diag_status status) {
  switch (status) {
    case READER_DIAG_OK: return "OK";
    case READER_DIAG_ARGUMENT: return "ARGUMENT";
    case READER_DIAG_FIELD: return "FIELD";
    case READER_DIAG_DUPLICATE: return "DUPLICATE";
    case READER_DIAG_LIMIT: return "LIMIT";
    case READER_DIAG_IO: return "IO";
    case READER_DIAG_EXISTS: return "EXISTS";
    case READER_DIAG_CANCELLED: return "CANCELLED";
    case READER_DIAG_MEMORY: return "MEMORY";
  }
  return "UNKNOWN";
}

void reader_diag_error_clear(reader_diag_error *error) {
  if (!error) return;
  memset(error, 0, sizeof(*error));
  error->struct_size = (uint32_t)sizeof(*error);
  error->status = READER_DIAG_OK;
}

void rd_error_set(reader_diag_error *error, reader_diag_status status, int system_error,
                  const char *message) {
  if (!error) return;
  memset(error, 0, sizeof(*error));
  error->struct_size = (uint32_t)sizeof(*error);
  error->status = status;
  error->system_error = system_error;
  /* message is always a static literal naming a field, never caller data. */
  (void)snprintf(error->message, sizeof(error->message), "%s", message ? message : "");
}

int rd_cancel_requested(const reader_diag_control *control) {
  return control && control->cancelled && control->cancelled(control->context) != 0;
}

reader_diag_input reader_diag_input_defaults(void) {
  reader_diag_input input;
  memset(&input, 0, sizeof(input));
  input.struct_size = (uint32_t)sizeof(input);
  input.abi_version = READER_DIAG_ABI_VERSION;
  return input;
}

/* ---- validation ------------------------------------------------------- */

/* Parses 1..max_digits decimal digits without a leading zero (except "0"). */
static int rd_number(const char **cursor, unsigned max_digits) {
  const char *p = *cursor;
  unsigned digits = 0;
  while (*p >= '0' && *p <= '9') {
    ++digits;
    ++p;
  }
  if (digits == 0 || digits > max_digits) return 0;
  if (digits > 1 && **cursor == '0') return 0;
  *cursor = p;
  return 1;
}

static int rd_version_ok(const char *text) {
  size_t length = 0;
  const char *p;
  int part;
  if (!text) return 0;
  while (length <= READER_DIAG_MAX_APP_VERSION_BYTES && text[length] != '\0') ++length;
  if (length == 0 || length > READER_DIAG_MAX_APP_VERSION_BYTES) return 0;
  p = text;
  for (part = 0; part < 3; ++part) {
    if (!rd_number(&p, 6u)) return 0;
    if (part < 2) {
      if (*p != '.') return 0;
      ++p;
    }
  }
  if (*p == '\0') return 1;
  if (*p != '-') return 0;
  ++p;
  if (strncmp(p, "alpha", 5) == 0) p += 5;
  else if (strncmp(p, "beta", 4) == 0) p += 4;
  else if (strncmp(p, "rc", 2) == 0) p += 2;
  else return 0;
  if (*p == '.') {
    ++p;
    if (!rd_number(&p, 3u)) return 0;
  }
  return *p == '\0';
}

typedef struct {
  uint32_t key; /* sort key */
  uint32_t a;
  uint32_t b;
  uint64_t value;
} rd_entry;

static void rd_sort(rd_entry *entries, size_t count) {
  size_t i, j;
  for (i = 1; i < count; ++i) {
    rd_entry current = entries[i];
    j = i;
    while (j > 0 && entries[j - 1u].key > current.key) {
      entries[j] = entries[j - 1u];
      --j;
    }
    entries[j] = current;
  }
}

static reader_diag_status rd_fail(reader_diag_error *error, reader_diag_status status,
                                  const char *message) {
  rd_error_set(error, status, 0, message);
  return status;
}

static reader_diag_status rd_validate(const reader_diag_input *in, rd_entry *counters,
                                      rd_entry *errors, reader_diag_error *error) {
  size_t i;
  if (in->struct_size != (uint32_t)sizeof(*in))
    return rd_fail(error, READER_DIAG_ARGUMENT, "input.struct_size");
  if (in->abi_version != READER_DIAG_ABI_VERSION)
    return rd_fail(error, READER_DIAG_ARGUMENT, "input.abi_version");
  for (i = 0; i < 8u; ++i)
    if (in->reserved[i] != 0u) return rd_fail(error, READER_DIAG_ARGUMENT, "input.reserved");
  for (i = 0; i < 5u; ++i)
    if (in->flag_reserved[i] != 0u)
      return rd_fail(error, READER_DIAG_ARGUMENT, "input.flag_reserved");
  if (in->counter_count > READER_DIAG_MAX_COUNTER_ENTRIES)
    return rd_fail(error, READER_DIAG_LIMIT, "input.counter_count");
  if (in->error_count > READER_DIAG_MAX_ERROR_ENTRIES)
    return rd_fail(error, READER_DIAG_LIMIT, "input.error_count");
  if ((in->counter_count && !in->counters) || (in->error_count && !in->errors))
    return rd_fail(error, READER_DIAG_ARGUMENT, "input.entries");
  if (!rd_version_ok(in->app_version))
    return rd_fail(error, READER_DIAG_FIELD, "input.app_version");
  if (in->platform < 1u || in->platform > RD_PLATFORM_MAX)
    return rd_fail(error, READER_DIAG_FIELD, "input.platform");
  if (in->operation < 1u || in->operation > RD_OPERATION_MAX)
    return rd_fail(error, READER_DIAG_FIELD, "input.operation");
  if (in->sdk_abi > 65535u) return rd_fail(error, READER_DIAG_FIELD, "input.sdk_abi");
  if (in->sdk_major > 9999u || in->sdk_minor > 9999u || in->sdk_patch > 9999u)
    return rd_fail(error, READER_DIAG_FIELD, "input.sdk_version");
  if (in->schema_version > 65535u)
    return rd_fail(error, READER_DIAG_FIELD, "input.schema_version");
  if (in->wire_version > 65535u) return rd_fail(error, READER_DIAG_FIELD, "input.wire_version");
  if (in->generated_at_unix > READER_DIAG_MAX_UNIX_TIME)
    return rd_fail(error, READER_DIAG_FIELD, "input.generated_at_unix");
  if (in->account_configured > 2u || in->sync_enabled > 2u || in->offline_mode > 2u)
    return rd_fail(error, READER_DIAG_FIELD, "input.state");
  for (i = 0; i < in->counter_count; ++i) {
    const reader_diag_counter *c = &in->counters[i];
    if (c->id < 1u || c->id > RD_COUNTER_MAX)
      return rd_fail(error, READER_DIAG_FIELD, "counter.id");
    if (c->value > READER_DIAG_MAX_COUNT)
      return rd_fail(error, READER_DIAG_FIELD, "counter.value");
    counters[i].key = c->id;
    counters[i].a = c->id;
    counters[i].b = 0;
    counters[i].value = c->value;
  }
  rd_sort(counters, in->counter_count);
  for (i = 1; i < in->counter_count; ++i)
    if (counters[i].key == counters[i - 1u].key)
      return rd_fail(error, READER_DIAG_DUPLICATE, "counter.id");
  for (i = 0; i < in->error_count; ++i) {
    const reader_diag_error_count *e = &in->errors[i];
    if (e->domain < 1u || e->domain > RD_DOMAIN_MAX)
      return rd_fail(error, READER_DIAG_FIELD, "error.domain");
    if (e->kind < 1u || e->kind > RD_KIND_MAX)
      return rd_fail(error, READER_DIAG_FIELD, "error.kind");
    if (e->count < 1u || e->count > READER_DIAG_MAX_COUNT)
      return rd_fail(error, READER_DIAG_FIELD, "error.count");
    errors[i].key = (e->domain << 8) | e->kind;
    errors[i].a = e->domain;
    errors[i].b = e->kind;
    errors[i].value = e->count;
  }
  rd_sort(errors, in->error_count);
  for (i = 1; i < in->error_count; ++i)
    if (errors[i].key == errors[i - 1u].key)
      return rd_fail(error, READER_DIAG_DUPLICATE, "error.domain_kind");
  return READER_DIAG_OK;
}

/* ---- rendering -------------------------------------------------------- */

static size_t rd_json_capacity(void) {
  size_t capacity = READER_DIAG_MAX_JSON_BYTES;
#ifdef READER_DIAGNOSTIC_TEST_HOOKS
  if (rd_test_output_limits.json != 0u && rd_test_output_limits.json < capacity)
    capacity = rd_test_output_limits.json;
#endif
  return capacity;
}

static size_t rd_summary_capacity(void) {
  size_t capacity = READER_DIAG_MAX_SUMMARY_BYTES;
#ifdef READER_DIAGNOSTIC_TEST_HOOKS
  if (rd_test_output_limits.summary != 0u && rd_test_output_limits.summary < capacity)
    capacity = rd_test_output_limits.summary;
#endif
  return capacity;
}

typedef struct {
  char *data;
  size_t capacity; /* bytes available excluding the terminating NUL */
  size_t length;
  int overflow;
} rd_text;

static void rd_put(rd_text *text, const char *format, ...) {
  va_list arguments;
  int written;
  if (text->overflow) return;
  va_start(arguments, format);
  written = vsnprintf(text->data + text->length, text->capacity + 1u - text->length, format,
                      arguments);
  va_end(arguments);
  if (written < 0 || (size_t)written > text->capacity - text->length) {
    text->overflow = 1;
    return;
  }
  text->length += (size_t)written;
}

static void rd_render_json(rd_text *t, const reader_diag_input *in, const rd_entry *counters,
                           const rd_entry *errors) {
  size_t i;
  rd_put(t, "{\n");
  rd_put(t, "  \"format\": \"exreader-diagnostic-report\",\n");
  rd_put(t, "  \"format_version\": %u,\n", (unsigned)READER_DIAG_FORMAT_VERSION);
  rd_put(t, "  \"app_version\": \"%s\",\n", in->app_version);
  rd_put(t, "  \"platform\": \"%s\",\n", rd_platform_names[in->platform]);
  rd_put(t, "  \"operation\": \"%s\",\n", rd_operation_names[in->operation]);
  rd_put(t, "  \"sdk_abi\": %u,\n", (unsigned)in->sdk_abi);
  rd_put(t, "  \"sdk_version\": \"%u.%u.%u\",\n", (unsigned)in->sdk_major,
         (unsigned)in->sdk_minor, (unsigned)in->sdk_patch);
  rd_put(t, "  \"schema_version\": %u,\n", (unsigned)in->schema_version);
  rd_put(t, "  \"wire_version\": %u,\n", (unsigned)in->wire_version);
  rd_put(t, "  \"generated_at_unix\": %llu,\n", (unsigned long long)in->generated_at_unix);
  rd_put(t, "  \"account_configured\": \"%s\",\n", rd_tri_names[in->account_configured]);
  rd_put(t, "  \"sync_enabled\": \"%s\",\n", rd_tri_names[in->sync_enabled]);
  rd_put(t, "  \"offline_mode\": \"%s\",\n", rd_tri_names[in->offline_mode]);
  if (in->counter_count == 0) {
    rd_put(t, "  \"counters\": [],\n");
  } else {
    rd_put(t, "  \"counters\": [\n");
    for (i = 0; i < in->counter_count; ++i)
      rd_put(t, "    {\"id\": \"%s\", \"value\": %llu}%s\n", rd_counter_names[counters[i].a],
             (unsigned long long)counters[i].value, i + 1u < in->counter_count ? "," : "");
    rd_put(t, "  ],\n");
  }
  if (in->error_count == 0) {
    rd_put(t, "  \"errors\": []\n");
  } else {
    rd_put(t, "  \"errors\": [\n");
    for (i = 0; i < in->error_count; ++i)
      rd_put(t, "    {\"domain\": \"%s\", \"kind\": \"%s\", \"count\": %llu}%s\n",
             rd_domain_names[errors[i].a], rd_kind_names[errors[i].b],
             (unsigned long long)errors[i].value, i + 1u < in->error_count ? "," : "");
    rd_put(t, "  ]\n");
  }
  rd_put(t, "}\n");
}

static void rd_render_summary(rd_text *t, const reader_diag_input *in, const rd_entry *counters,
                              const rd_entry *errors) {
  size_t i;
  unsigned long long total = 0;
  for (i = 0; i < in->error_count; ++i) total += (unsigned long long)errors[i].value;
  rd_put(t, "EXReader diagnostic report (format %u)\n", (unsigned)READER_DIAG_FORMAT_VERSION);
  rd_put(t, "App %s on %s, SDK %u.%u.%u (ABI %u), schema %u, wire %u\n", in->app_version,
         rd_platform_names[in->platform], (unsigned)in->sdk_major, (unsigned)in->sdk_minor,
         (unsigned)in->sdk_patch, (unsigned)in->sdk_abi, (unsigned)in->schema_version,
         (unsigned)in->wire_version);
  rd_put(t, "Operation: %s\n", rd_operation_names[in->operation]);
  rd_put(t, "Account configured: %s, sync enabled: %s, offline mode: %s\n",
         rd_tri_names[in->account_configured], rd_tri_names[in->sync_enabled],
         rd_tri_names[in->offline_mode]);
  rd_put(t, "Generated: %llu\n", (unsigned long long)in->generated_at_unix);
  rd_put(t, "Errors: %u kinds, %llu occurrences\n", (unsigned)in->error_count, total);
  for (i = 0; i < in->error_count; ++i)
    rd_put(t, "  %s %s x%llu\n", rd_domain_names[errors[i].a], rd_kind_names[errors[i].b],
           (unsigned long long)errors[i].value);
  rd_put(t, "Counters: %u\n", (unsigned)in->counter_count);
  for (i = 0; i < in->counter_count; ++i)
    rd_put(t, "  %s = %llu\n", rd_counter_names[counters[i].a],
           (unsigned long long)counters[i].value);
}

reader_diag_status reader_diag_report_build(const reader_diag_input *input,
                                            const reader_diag_build_options *options,
                                            reader_diag_report **out, reader_diag_error *error) {
  rd_entry counters[READER_DIAG_MAX_COUNTER_ENTRIES];
  rd_entry errors[READER_DIAG_MAX_ERROR_ENTRIES];
  reader_diag_report *report;
  reader_diag_status status;
  rd_text text;
  if (out) *out = NULL;
  if (!input || !out) return rd_fail(error, READER_DIAG_ARGUMENT, "null argument");
  if (options && options->struct_size != (uint32_t)sizeof(*options))
    return rd_fail(error, READER_DIAG_ARGUMENT, "options.struct_size");
  if (rd_cancel_requested(options ? &options->control : NULL))
    return rd_fail(error, READER_DIAG_CANCELLED, "build cancelled");
  memset(counters, 0, sizeof(counters));
  memset(errors, 0, sizeof(errors));
  status = rd_validate(input, counters, errors, error);
  if (status != READER_DIAG_OK) return status;
  report = (reader_diag_report *)calloc(1u, sizeof(*report));
  if (!report) {
    rd_error_set(error, READER_DIAG_MEMORY, 0, "out of memory");
    return READER_DIAG_MEMORY;
  }
  text.data = report->json;
  text.capacity = rd_json_capacity();
  text.length = 0;
  text.overflow = 0;
  rd_render_json(&text, input, counters, errors);
  if (text.overflow) {
    free(report);
    return rd_fail(error, READER_DIAG_LIMIT, "json output limit");
  }
  report->json_size = text.length;
  text.data = report->summary;
  text.capacity = rd_summary_capacity();
  text.length = 0;
  text.overflow = 0;
  rd_render_summary(&text, input, counters, errors);
  if (text.overflow) {
    free(report);
    return rd_fail(error, READER_DIAG_LIMIT, "summary output limit");
  }
  report->summary_size = text.length;
  if (rd_cancel_requested(options ? &options->control : NULL)) {
    free(report);
    return rd_fail(error, READER_DIAG_CANCELLED, "build cancelled");
  }
  *out = report;
  if (error) reader_diag_error_clear(error);
  return READER_DIAG_OK;
}

const char *reader_diag_report_json(const reader_diag_report *report, size_t *size) {
  if (size) *size = report ? report->json_size : 0u;
  return report ? report->json : NULL;
}

const char *reader_diag_report_summary(const reader_diag_report *report, size_t *size) {
  if (size) *size = report ? report->summary_size : 0u;
  return report ? report->summary : NULL;
}

void reader_diag_report_free(reader_diag_report *report) { free(report); }

reader_diag_status reader_diag_report_write(const reader_diag_report *report,
                                            const char *utf8_path,
                                            const reader_diag_write_options *options,
                                            reader_diag_error *error) {
  const char *data;
  size_t size;
  const reader_diag_control *control = NULL;
  uint32_t format = READER_DIAG_FORMAT_JSON;
  if (!report || !utf8_path || utf8_path[0] == '\0')
    return rd_fail(error, READER_DIAG_ARGUMENT, "null argument");
  if (options) {
    if (options->struct_size != (uint32_t)sizeof(*options))
      return rd_fail(error, READER_DIAG_ARGUMENT, "options.struct_size");
    if (options->format != 0u) format = options->format;
    control = &options->control;
  }
  if (format == READER_DIAG_FORMAT_JSON) {
    data = report->json;
    size = report->json_size;
  } else if (format == READER_DIAG_FORMAT_SUMMARY) {
    data = report->summary;
    size = report->summary_size;
  } else {
    return rd_fail(error, READER_DIAG_ARGUMENT, "options.format");
  }
  return rd_write_new_file(utf8_path, data, size, control, error);
}
