/* SPDX-License-Identifier: MIT */
/* Installed-package consumer. Builds against the installed header and static
   library only; it never sees package-private headers or test hooks. */
#if defined(_WIN32)
#define _CRT_SECURE_NO_WARNINGS 1
#endif
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "reader_diagnostic_report.h"

static int failures;

static void expect(int condition, const char *what) {
  if (!condition) {
    ++failures;
    printf("fail=%s\n", what);
  }
}

static char *path_join(const char *directory, const char *name) {
  size_t length = strlen(directory) + strlen(name) + 2u;
  char *joined = (char *)malloc(length);
  if (!joined) return NULL;
  (void)snprintf(joined, length, "%s/%s", directory, name);
  return joined;
}

static int read_file(const char *path, char *buffer, size_t capacity, size_t *size) {
  FILE *stream = fopen(path, "rb");
  size_t used = 0;
  if (!stream) return 0;
  while (used < capacity) {
    size_t got = fread(buffer + used, 1u, capacity - used, stream);
    used += got;
    if (got == 0u) break;
  }
  if (!feof(stream)) {
    fclose(stream);
    return 0;
  }
  fclose(stream);
  *size = used;
  return 1;
}

static int cancel_now(void *context) {
  int *calls = (int *)context;
  ++(*calls);
  return 1;
}

static void fill_typical(reader_diag_input *input, reader_diag_counter *counters,
                         reader_diag_error_count *errors) {
  memset(counters, 0, sizeof(reader_diag_counter) * 3u);
  memset(errors, 0, sizeof(reader_diag_error_count) * 2u);
  *input = reader_diag_input_defaults();
  input->app_version = "2.0.1-rc.7";
  input->platform = READER_DIAG_PLATFORM_MACOS;
  input->operation = READER_DIAG_OPERATION_READING;
  input->sdk_abi = 1u;
  input->sdk_major = 3u;
  input->sdk_minor = 40u;
  input->sdk_patch = 0u;
  input->schema_version = 1u;
  input->wire_version = 1u;
  input->generated_at_unix = 1761600001ull;
  input->account_configured = READER_DIAG_TRI_YES;
  input->sync_enabled = READER_DIAG_TRI_NO;
  input->offline_mode = READER_DIAG_TRI_UNKNOWN;
  counters[0].id = READER_DIAG_COUNTER_BOOKS_TOTAL;
  counters[0].value = 128u;
  counters[1].id = READER_DIAG_COUNTER_IMPORT_FAILURES;
  counters[1].value = 2u;
  counters[2].id = READER_DIAG_COUNTER_SYNC_CONFLICTS;
  counters[2].value = 1u;
  errors[0].domain = READER_DIAG_DOMAIN_IMPORT;
  errors[0].kind = READER_DIAG_KIND_IO;
  errors[0].count = 2u;
  errors[1].domain = READER_DIAG_DOMAIN_READING;
  errors[1].kind = READER_DIAG_KIND_FORMAT;
  errors[1].count = 1u;
  input->counters = counters;
  input->counter_count = 3u;
  input->errors = errors;
  input->error_count = 2u;
}

int main(int argc, char **argv) {
  static const char *const expected_status[] = {"OK",     "ARGUMENT", "FIELD",
                                                "DUPLICATE", "LIMIT", "IO",
                                                "EXISTS", "CANCELLED", "MEMORY"};
  reader_diag_input input;
  reader_diag_counter counters[3];
  reader_diag_error_count errors[2];
  reader_diag_report *report = NULL;
  reader_diag_error error;
  reader_diag_write_options write_options;
  reader_diag_build_options build_options;
  const char *json;
  const char *summary;
  size_t json_size = 0u;
  size_t summary_size = 0u;
  char *json_path = NULL;
  char *summary_path = NULL;
  char *missing_path = NULL;
  static char buffer[READER_DIAG_MAX_JSON_BYTES + 1u];
  size_t read_size = 0u;
  size_t index;
  int calls = 0;
  reader_diag_status status;

  if (argc < 2) {
    printf("usage: diagnostic-c-consumer <work-directory>\n");
    return 2;
  }
  json_path = path_join(argv[1], "c-report.json");
  summary_path = path_join(argv[1], "c-summary.txt");
  missing_path = path_join(argv[1], "absent-directory/c-report.json");
  if (!json_path || !summary_path || !missing_path) {
    printf("fail=allocation\n");
    return 1;
  }

  expect(reader_diag_abi_version() == READER_DIAG_ABI_VERSION, "abi");
  for (index = 0u; index < 9u; ++index)
    expect(strcmp(reader_diag_status_name((reader_diag_status)index),
                  expected_status[index]) == 0, "status-name");
  expect(strcmp(reader_diag_status_name((reader_diag_status)99), "UNKNOWN") == 0,
         "status-name-unknown");

  input = reader_diag_input_defaults();
  expect(input.struct_size == (uint32_t)sizeof(input), "defaults-struct-size");
  expect(input.abi_version == READER_DIAG_ABI_VERSION, "defaults-abi");
  expect(input.app_version == NULL && input.counter_count == 0u && input.error_count == 0u,
         "defaults-empty");
  expect(input.platform == 0u && input.operation == 0u && input.generated_at_unix == 0u,
         "defaults-zero");

  fill_typical(&input, counters, errors);
  reader_diag_error_clear(&error);
  status = reader_diag_report_build(&input, NULL, &report, &error);
  expect(status == READER_DIAG_OK, "build-status");
  expect(report != NULL, "build-report");
  expect(error.status == READER_DIAG_OK && error.struct_size == (uint32_t)sizeof(error),
         "build-clears-error");
  json = reader_diag_report_json(report, &json_size);
  summary = reader_diag_report_summary(report, &summary_size);
  expect(json != NULL && summary != NULL, "accessors");
  expect(strlen(json) == json_size && strlen(summary) == summary_size, "sizes-match-strlen");
  expect(json_size > 0u && json_size <= READER_DIAG_MAX_JSON_BYTES, "json-bound");
  expect(summary_size > 0u && summary_size <= READER_DIAG_MAX_SUMMARY_BYTES, "summary-bound");
  expect(json[json_size - 1u] == '\n' && summary[summary_size - 1u] == '\n', "trailing-newline");
  expect(strstr(json, "\"format\": \"exreader-diagnostic-report\"") != NULL, "format-marker");
  expect(reader_diag_report_json(NULL, NULL) == NULL, "null-report-json");
  expect(reader_diag_report_summary(NULL, &read_size) == NULL && read_size == 0u,
         "null-report-summary");

  memset(&write_options, 0, sizeof(write_options));
  write_options.struct_size = (uint32_t)sizeof(write_options);
  status = reader_diag_report_write(report, json_path, &write_options, &error);
  expect(status == READER_DIAG_OK && error.status == READER_DIAG_OK, "write-json");
  expect(read_file(json_path, buffer, sizeof(buffer), &read_size), "read-back");
  expect(read_size == json_size && memcmp(buffer, json, json_size) == 0, "write-bytes-equal");

  status = reader_diag_report_write(report, json_path, NULL, &error);
  expect(status == READER_DIAG_EXISTS, "write-exists");
  expect(read_file(json_path, buffer, sizeof(buffer), &read_size), "read-back-2");
  expect(read_size == json_size && memcmp(buffer, json, json_size) == 0, "exists-keeps-bytes");

  write_options.format = READER_DIAG_FORMAT_SUMMARY;
  status = reader_diag_report_write(report, summary_path, &write_options, &error);
  expect(status == READER_DIAG_OK, "write-summary");
  expect(read_file(summary_path, buffer, sizeof(buffer), &read_size), "read-summary");
  expect(read_size == summary_size && memcmp(buffer, summary, summary_size) == 0,
         "summary-bytes-equal");

  write_options.format = 99u;
  status = reader_diag_report_write(report, summary_path, &write_options, &error);
  expect(status == READER_DIAG_ARGUMENT, "write-bad-format");
  write_options.format = 0u;
  status = reader_diag_report_write(report, NULL, &write_options, &error);
  expect(status == READER_DIAG_ARGUMENT, "write-null-path");
  status = reader_diag_report_write(report, missing_path, NULL, &error);
  expect(status == READER_DIAG_IO && error.system_error != 0, "write-missing-parent");
  write_options.struct_size = 0u;
  status = reader_diag_report_write(report, summary_path, &write_options, &error);
  expect(status == READER_DIAG_ARGUMENT, "write-bad-options-size");
  write_options.struct_size = (uint32_t)sizeof(write_options);

  reader_diag_report_free(report);
  report = NULL;

  memset(&build_options, 0, sizeof(build_options));
  build_options.struct_size = (uint32_t)sizeof(build_options);
  build_options.control.cancelled = cancel_now;
  build_options.control.context = &calls;
  status = reader_diag_report_build(&input, &build_options, &report, &error);
  expect(status == READER_DIAG_CANCELLED, "build-cancelled");
  expect(report == NULL && calls >= 1, "build-cancelled-clears-out");
  build_options.struct_size = 0u;
  status = reader_diag_report_build(&input, &build_options, &report, &error);
  expect(status == READER_DIAG_ARGUMENT, "build-bad-options-size");
  expect(report == NULL, "build-bad-options-out");
  status = reader_diag_report_build(NULL, NULL, &report, &error);
  expect(status == READER_DIAG_ARGUMENT, "build-null-input");
  reader_diag_report_free(NULL);
  reader_diag_report_free(report);

  printf("abi=%u\n", reader_diag_abi_version());
  printf("json_size=%zu\n", json_size);
  printf("summary_size=%zu\n", summary_size);
  printf("failures=%d\n", failures);
  free(json_path);
  free(summary_path);
  free(missing_path);
  if (failures != 0) return 1;
  printf("c-consumer-ok\n");
  return 0;
}
