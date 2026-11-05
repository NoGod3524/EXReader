/* SPDX-License-Identifier: MIT */
/* S11 independent consumer: installed public packages only.
 *
 * One short-lived process per command, driven by a UTF-8 key=value spec file so
 * that Windows code pages never enter the picture. The process prints one JSON
 * object for the operation it performed; the judge owns every assertion.
 *
 * Surfaces (all existing public headers, unchanged):
 *   import   EXReaderSideload  exr_sideload_import_file
 *   batch    EXReaderBatchImport  reader_batch_import
 *   cloud    EXReaderCloudImport  reader_cloud_download + reader_cloud_import
 *   ld       EXReaderLocalDownloads reader_ld_remove/reimport/pending
 *   readback a fresh SDK handle that re-reads every stored original
 */
#define _CRT_SECURE_NO_WARNINGS
#ifndef _WIN32
#define _POSIX_C_SOURCE 200809L
#endif
#include <reader_batch_import.h>
#include <reader_cloud_import.h>
#include <reader_local_downloads.h>
#include <exr_sideload.h>
#include <catalog.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
#endif

#define MAX_KEYS 192

static char *keys[MAX_KEYS], *values[MAX_KEYS];
static int key_count;

static FILE *open_utf8(const char *path, const char *mode) {
#ifdef _WIN32
  wchar_t wide[4096], wmode[8];
  if (MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, path, -1, wide, 4096) <= 0) return NULL;
  if (MultiByteToWideChar(CP_UTF8, 0, mode, -1, wmode, 8) <= 0) return NULL;
  return _wfopen(wide, wmode);
#else
  return fopen(path, mode);
#endif
}

static const char *get(const char *key, const char *fallback) {
  int i;
  for (i = 0; i < key_count; i++)
    if (!strcmp(keys[i], key)) return values[i];
  return fallback;
}

static uint64_t get_u64(const char *key, uint64_t fallback) {
  const char *text = get(key, NULL);
  return text && *text ? (uint64_t)strtoull(text, NULL, 10) : fallback;
}

static char *dup_text(const char *text) {
  size_t n = strlen(text) + 1;
  char *copy = (char *)malloc(n);
  if (copy) memcpy(copy, text, n);
  return copy;
}

static int read_spec(const char *path) {
  FILE *file = open_utf8(path, "rb");
  char line[65536];
  if (!file) return -1;
  while (fgets(line, sizeof(line), file) && key_count < MAX_KEYS) {
    char *eq = strchr(line, '=');
    size_t n = strlen(line);
    while (n && (line[n - 1] == '\n' || line[n - 1] == '\r')) line[--n] = 0;
    if (!eq) continue;
    *eq = 0;
    keys[key_count] = dup_text(line);
    values[key_count] = dup_text(eq + 1);
    if (!keys[key_count] || !values[key_count]) { fclose(file); return -1; }
    key_count++;
  }
  fclose(file);
  return 0;
}

static void quoted(const char *text) {
  const unsigned char *p = (const unsigned char *)text;
  putchar('"');
  for (; *p; p++) {
    if (*p == '"' || *p == '\\') printf("\\%c", *p);
    else if (*p < 32) printf("\\u%04x", *p);
    else putchar(*p);
  }
  putchar('"');
}

static exr_format parse_format(const char *name) {
  if (!name) return EXR_CUSTOM;
  if (!strcmp(name, "TXT")) return EXR_TXT;
  if (!strcmp(name, "HTML")) return EXR_HTML;
  if (!strcmp(name, "FB2")) return EXR_FB2;
  if (!strcmp(name, "EPUB")) return EXR_EPUB;
  if (!strcmp(name, "DOCX")) return EXR_DOCX;
  if (!strcmp(name, "RTF")) return EXR_RTF;
  if (!strcmp(name, "MOBI")) return EXR_MOBI;
  if (!strcmp(name, "PDF")) return EXR_PDF;
  if (!strcmp(name, "CBZ")) return EXR_CBZ;
  return EXR_CUSTOM;
}

static const char *format_key(exr_format format) {
  switch (format) {
    case EXR_TXT: return "txt";
    case EXR_HTML: return "html";
    case EXR_FB2: return "fb2";
    case EXR_EPUB: return "epub";
    case EXR_DOCX: return "docx";
    case EXR_RTF: return "rtf";
    case EXR_MOBI: return "mobi";
    case EXR_PDF: return "pdf";
    case EXR_CBZ: return "cbz";
    default: return "custom";
  }
}

static const char *location_kind(exr_format format) {
  return format == EXR_EPUB ? "epub_chapter"
      : (format == EXR_PDF || format == EXR_CBZ) ? "fixed_page" : "reflow_global";
}

static char *read_all(const char *path, size_t *size) {
  FILE *file = open_utf8(path, "rb");
  char *data;
  long n;
  if (!file) return NULL;
  if (fseek(file, 0, SEEK_END) != 0) { fclose(file); return NULL; }
  n = ftell(file);
  if (n <= 0) { fclose(file); return NULL; }
  if (fseek(file, 0, SEEK_SET) != 0) { fclose(file); return NULL; }
  data = (char *)malloc((size_t)n);
  if (!data || fread(data, 1, (size_t)n, file) != (size_t)n) { free(data); fclose(file); return NULL; }
  fclose(file);
  *size = (size_t)n;
  return data;
}

static int file_exists(const char *path) {
  FILE *file = open_utf8(path, "rb");
  if (!file) return 0;
  fclose(file);
  return 1;
}

typedef struct {
  unsigned long polls;
  unsigned long cancel_at;        /* cancel from this poll on; 0 = never */
  unsigned long commits;
  unsigned long cancel_after_commits;
} control_state;

static int control_cancelled(void *context) {
  control_state *state = (control_state *)context;
  state->polls++;
  if (state->cancel_at && state->polls >= state->cancel_at) return 1;
  return 0;
}

static const char *exr_status_name(int status) {
  switch (status) {
    case EXR_OK: return "OK";
    case EXR_ARGUMENT: return "ARGUMENT";
    case EXR_MEMORY: return "MEMORY";
    case EXR_IO: return "IO";
    case EXR_ENCODING: return "ENCODING";
    case EXR_FORMAT: return "FORMAT";
    case EXR_LIMIT: return "LIMIT";
    case EXR_DATABASE: return "DATABASE";
    case EXR_FONT: return "FONT";
    case EXR_CANCELLED: return "CANCELLED";
    case EXR_PASSWORD: return "PASSWORD";
    case EXR_UNSUPPORTED: return "UNSUPPORTED";
    default: return "OTHER";
  }
}

/* ----------------------------------------------------------------- import */

static int run_import(void) {
  exr_sideload_options options;
  exr_sideload_result result;
  exr_error error;
  exr_library *library = NULL;
  control_state state;
  exr_status status;
  memset(&state, 0, sizeof(state));
  memset(&error, 0, sizeof(error));
  if (exr_library_open(get("library", ""), &library, &error) != EXR_OK) {
    printf("{\"op\":\"import\",\"library_open\":0,\"message\":");
    quoted(error.message);
    printf("}\n");
    return 1;
  }
  memset(&options, 0, sizeof(options));
  options.struct_size = sizeof(options);
  options.max_input_bytes = get_u64("max_input", 0);
  state.cancel_at = (unsigned long)get_u64("cancel_at", 0);
  options.control.cancelled = control_cancelled;
  options.control.context = &state;
  memset(&result, 0, sizeof(result));
  result.struct_size = sizeof(result);
  status = exr_sideload_import_file(library, parse_format(get("format", "")),
      get("file", ""), get("title", NULL), &options, &result, &error);
  printf("{\"op\":\"import\",\"status\":%d,\"status_name\":\"%s\",\"book_id\":%lld,"
      "\"created\":%d,\"polls\":%lu,\"message\":",
      (int)status, exr_status_name((int)status),
      (long long)result.book_id, result.created, state.polls);
  quoted(error.message);
  printf("}\n");
  exr_library_close(library);
  return 0;
}

/* ------------------------------------------------------------------ batch */

static void on_batch_result(void *context, size_t index, const reader_batch_result *result) {
  control_state *state = (control_state *)context;
  (void)index;
  if (result->committed) state->commits++;
  if (state->cancel_after_commits && state->commits >= state->cancel_after_commits) state->cancel_at = 0;
}

static int batch_cancelled(void *context) {
  control_state *state = (control_state *)context;
  state->polls++;
  if (state->cancel_after_commits && state->commits >= state->cancel_after_commits) return 1;
  if (state->cancel_at && state->polls >= state->cancel_at) return 1;
  return 0;
}

static int run_batch(void) {
  reader_batch_import_options options;
  reader_batch_item *items = NULL;
  reader_batch_result *results = NULL;
  size_t count = 0, result_count = 0, i;
  reader_batch_error error;
  reader_batch_status status;
  exr_library *library = NULL;
  exr_error sdk_error;
  control_state state;
  size_t total = (size_t)get_u64("count", 0);
  memset(&state, 0, sizeof(state));
  memset(&error, 0, sizeof(error));
  memset(&sdk_error, 0, sizeof(sdk_error));
  if (!total || total > READER_BATCH_MAX_BATCH) return 2;
  items = (reader_batch_item *)calloc(total, sizeof(*items));
  if (!items) return 2;
  for (i = 0; i < total; i++) {
    char key[32];
    const char *value;
    const char *bar;
    char path[8192], format[32], title[512];
    snprintf(key, sizeof(key), "item%u", (unsigned)i);
    value = get(key, "");
    /* path|FORMAT|title */
    bar = strchr(value, '|');
    if (!bar) { free(items); return 2; }
    memset(path, 0, sizeof(path));
    if ((size_t)(bar - value) >= sizeof(path)) { free(items); return 2; }
    memcpy(path, value, (size_t)(bar - value));
    {
      const char *second = strchr(bar + 1, '|');
      size_t n = second ? (size_t)(second - (bar + 1)) : strlen(bar + 1);
      if (n >= sizeof(format)) { free(items); return 2; }
      memcpy(format, bar + 1, n);
      format[n] = 0;
      title[0] = 0;
      if (second && *second) {
        size_t m = strlen(second + 1);
        if (m >= sizeof(title)) { free(items); return 2; }
        memcpy(title, second + 1, m + 1);
      }
    }
    items[i].struct_size = sizeof(items[i]);
    items[i].path = dup_text(path);
    items[i].title = title[0] ? dup_text(title) : NULL;
    items[i].format = parse_format(format);
    if (!items[i].path) { free(items); return 2; }
  }
  if (exr_library_open(get("library", ""), &library, &sdk_error) != EXR_OK) {
    printf("{\"op\":\"batch\",\"library_open\":0,\"message\":");
    quoted(sdk_error.message);
    printf("}\n");
    for (i = 0; i < total; i++) free((void *)items[i].path);
    free(items);
    return 1;
  }
  reader_batch_import_options_init(&options);
  options.staging_dir = get("staging", NULL);
  options.max_input_bytes = get_u64("max_input", 0);
  state.cancel_at = (unsigned long)get_u64("cancel_at", 0);
  state.cancel_after_commits = (unsigned long)get_u64("cancel_after_commits", 0);
  options.control.cancelled = batch_cancelled;
  options.control.context = &state;
  options.on_result = on_batch_result;
  options.on_result_context = &state;
  status = reader_batch_import(library, items, total, &options, &results, &result_count, &error);
  printf("{\"op\":\"batch\",\"status\":%d,\"status_name\":\"%s\",\"count\":%u,"
      "\"commits\":%lu,\"polls\":%lu,\"error_code\":%d,\"error_message\":",
      (int)status, reader_batch_status_name(status), (unsigned)result_count,
      state.commits, state.polls, (int)error.code);
  quoted(error.message);
  printf(",\"items\":[");
  for (i = 0; i < result_count; i++) {
    if (i) putchar(',');
    printf("{\"index\":%u,\"status\":\"%s\",\"committed\":%d,\"created\":%d,"
        "\"book_id\":%lld,\"sdk_code\":%d,\"message\":",
        (unsigned)i, reader_batch_item_status_name(results[i].status),
        results[i].committed, results[i].created, (long long)results[i].book_id,
        (int)results[i].status_code);
    quoted(results[i].message);
    putchar('}');
  }
  printf("]}\n");
  if (results) reader_batch_results_free(results, result_count);
  exr_library_close(library);
  for (i = 0; i < total; i++) { free((void *)items[i].path); free((void *)items[i].title); }
  free(items);
  return 0;
}

/* ------------------------------------------------------------------- scan */

static int run_scan(void) {
  reader_batch_scan_options options;
  reader_batch_enumerator *enumerator = NULL;
  reader_batch_error error;
  reader_batch_status status;
  size_t total = 0, batches = 0, i;
  int complete = 0, truncated = 0;
  memset(&error, 0, sizeof(error));
  reader_batch_scan_options_init(&options);
  options.root = get("root", "");
  options.recursive = (int)get_u64("recursive", 1);
  if (get_u64("batch", 0)) options.batch_size = (size_t)get_u64("batch", 0);
  if (get_u64("max_candidates", 0)) options.max_candidates = (size_t)get_u64("max_candidates", 0);
  status = reader_batch_enumerate_open(&options, &enumerator, &error);
  if (status != READER_BATCH_OK) {
    printf("{\"op\":\"scan\",\"status\":\"%s\",\"open\":0,\"message\":",
        reader_batch_status_name(status));
    quoted(error.message);
    printf("}\n");
    return 0;
  }
  printf("{\"op\":\"scan\",\"status\":\"OK\",\"open\":1,\"candidates\":[");
  while (!complete && !truncated) {
    reader_batch_candidate *items = NULL;
    size_t count = 0;
    status = reader_batch_enumerate_next(enumerator, &items, &count, &complete, &truncated, &error);
    if (status != READER_BATCH_OK) {
      printf("],\"next_status\":\"%s\",\"message\":",
          reader_batch_status_name(status));
      quoted(error.message);
      printf("}\n");
      reader_batch_enumerate_close(enumerator);
      return 0;
    }
    batches++;
    for (i = 0; i < count; i++) {
      if (total) putchar(',');
      printf("{\"path\":");
      quoted(items[i].path ? items[i].path : "");
      printf(",\"relative\":");
      quoted(items[i].relative_path ? items[i].relative_path : "");
      printf(",\"format\":%d,\"format_name\":\"%s\",\"size_hint\":%llu}",
          (int)items[i].format, reader_batch_format_name(items[i].format),
          (unsigned long long)items[i].size_hint);
      total++;
    }
    reader_batch_candidates_free(items, count);
  }
  reader_batch_enumerate_close(enumerator);
  printf("],\"complete\":%d,\"truncated\":%d,\"batches\":%u,\"total\":%u}\n",
      complete, truncated, (unsigned)batches, (unsigned)total);
  return 0;
}

/* ------------------------------------------------------------------ cloud */

static const char *cloud_status_name(reader_cloud_status status) {
  return reader_cloud_status_name(status);
}

static int run_cloud(void) {
  exr_webdav_config config;
  exr_webdav_error dav_error;
  exr_webdav_client *client = NULL;
  exr_webdav_status dav_status;
  reader_cloud_request request;
  reader_cloud_staged *staged = NULL;
  reader_cloud_error error;
  reader_cloud_status status;
  reader_cloud_import_options options;
  reader_cloud_import_result result;
  exr_library *library = NULL;
  exr_error sdk_error;
  control_state state;
  char staged_path[8192];
  int do_import = (int)get_u64("import", 1);
  int have_path = 0;
  memset(&state, 0, sizeof(state));
  memset(&error, 0, sizeof(error));
  memset(&sdk_error, 0, sizeof(sdk_error));
  memset(&config, 0, sizeof(config));
  memset(&dav_error, 0, sizeof(dav_error));
  config.root_url = get("root", "");
  config.authorization = get("auth", "");
  config.max_download_bytes = get_u64("client_max", 0);
  config.timeout_ms = (unsigned)get_u64("timeout", 0);
  dav_status = exr_webdav_create(&config, &client, &dav_error);
  printf("{\"op\":\"cloud\",\"create\":%d", (int)dav_status);
  if (dav_status != EXR_DAV_OK) {
    printf(",\"create_message\":");
    quoted(dav_error.message);
    printf("}\n");
    return 0;
  }
  reader_cloud_request_init(&request);
  request.resource = get("resource", "");
  request.display_name = get("name", "");
  request.format = parse_format(get("format", ""));
  request.expected_bytes = get_u64("expected", 0);
  request.max_bytes = get_u64("max", 0);
  request.staging_dir = get("staging", "");
  state.cancel_at = (unsigned long)get_u64("cancel_net", 0);
  request.control.cancelled = control_cancelled;
  request.control.context = &state;
  status = reader_cloud_download(client, &request, &staged, &error);
  printf(",\"download\":\"%s\",\"download_code\":%d,\"staged\":%d", cloud_status_name(status),
      (int)status, staged != NULL);
  if (staged) {
    snprintf(staged_path, sizeof(staged_path), "%s", reader_cloud_staged_path(staged));
    have_path = 1;
    printf(",\"staged_bytes\":%llu,\"staged_sha\":\"%s\",\"staged_name\":",
        (unsigned long long)reader_cloud_staged_bytes(staged), reader_cloud_staged_sha256(staged));
    quoted(reader_cloud_staged_name(staged));
  }
  exr_webdav_free(client);
  if (staged && do_import) {
    size_t size = 0;
    const char *tamper = get("tamper", "");
    if (tamper[0] && strcmp(tamper, "none")) {
      char *data = read_all(staged_path, &size);
      int ok = 0;
      if (data) {
        if (!strcmp(tamper, "flip") && size > 16) {
          FILE *file = open_utf8(staged_path, "wb");
          data[size / 2] = (char)(data[size / 2] ^ 0x5a);
          if (file) { ok = fwrite(data, 1, size, file) == size; fclose(file); }
        } else if (!strcmp(tamper, "truncate") && size > 16) {
          FILE *file = open_utf8(staged_path, "wb");
          if (file) { ok = fwrite(data, 1, size / 2, file) == (size_t)(size / 2); fclose(file); }
        } else if (!strcmp(tamper, "append")) {
          FILE *file = open_utf8(staged_path, "ab");
          if (file) { ok = fwrite("X", 1, 1, file) == 1; fclose(file); }
        }
        free(data);
      }
      printf(",\"tamper\":\"%s\",\"tamper_ok\":%d", tamper, ok);
    }
    if (exr_library_open(get("library", ""), &library, &sdk_error) != EXR_OK) {
      printf(",\"library_open\":0,\"message\":");
      quoted(sdk_error.message);
      printf("}\n");
      reader_cloud_staged_discard(&staged);
      return 1;
    }
    reader_cloud_import_options_init(&options);
    options.title = get("title", NULL);
    options.max_input_bytes = get_u64("max_input", 0);
    state.polls = 0;
    state.cancel_at = (unsigned long)get_u64("cancel_import_poll", 0);
    options.control.cancelled = control_cancelled;
    options.control.context = &state;
    memset(&result, 0, sizeof(result));
    result.struct_size = sizeof(result);
    memset(&error, 0, sizeof(error));
    status = reader_cloud_import(library, &staged, &options, &result, &error);
    printf(",\"import\":\"%s\",\"import_code\":%d,\"committed\":%d,\"created\":%d,"
        "\"book_id\":%lld,\"staging_removed\":%d,\"consumed\":%d,\"file_after\":%d,"
        "\"import_polls\":%lu,\"import_message\":",
        cloud_status_name(status), (int)status, result.committed, result.created,
        (long long)result.book_id, result.staging_removed, staged == NULL,
        have_path ? file_exists(staged_path) : -1, state.polls);
    quoted(error.message);
    exr_library_close(library);
  }
  if (staged) reader_cloud_staged_discard(&staged);
  printf("}\n");
  return 0;
}

/* ---------------------------------------------------------- local download */

typedef struct {
  const char *cancel_at;
  int cancel;
  unsigned long polls;
  int stages;
  int stage_count;
  unsigned long poll_limit;
  char stage_names[8][24];
} ld_state;

static void ld_hook(void *context, reader_ld_stage stage) {
  ld_state *state = (ld_state *)context;
  state->stages++;
  if (state->stage_count < 8) {
    snprintf(state->stage_names[state->stage_count], sizeof(state->stage_names[0]), "%s",
        reader_ld_stage_name(stage));
  }
  state->stage_count++;
  if (state->cancel_at && !strcmp(state->cancel_at, reader_ld_stage_name(stage))) state->cancel = 1;
}

static int ld_cancelled(void *context) {
  ld_state *state = (ld_state *)context;
  state->polls++;
  if (state->poll_limit && state->polls >= state->poll_limit) return 1;
  return state->cancel;
}

static exr_library *ld_library(const char *work) {
  char path[8192];
  exr_library *library = NULL;
  exr_error error;
  memset(&error, 0, sizeof(error));
  snprintf(path, sizeof(path), "%s/sdk.db", work);
  if (exr_library_open(path, &library, &error) != EXR_OK) {
    fprintf(stderr, "s11 probe: sdk open failed: %s\n", error.message);
    return NULL;
  }
  return library;
}

static reader_catalog *ld_catalog(const char *work) {
  char path[8192];
  reader_catalog *catalog = NULL;
  reader_catalog_error error;
  memset(&error, 0, sizeof(error));
  snprintf(path, sizeof(path), "%s/catalog.db", work);
  if (reader_catalog_open(path, &catalog, &error) != 0) {
    fprintf(stderr, "s11 probe: catalog open failed: %s\n", error.message);
    return NULL;
  }
  return catalog;
}

static int ld_emit_result(const char *op, reader_ld_status status,
    const reader_ld_result *result, const reader_ld_error *error, ld_state *state) {
  int i, shown;
  printf("{\"op\":\"ld\",\"cmd\":\"%s\",\"status\":\"%s\",\"outcome\":\"%s\","
      "\"id\":%lld,\"removed\":%u,\"skipped\":%u,\"notes\":%u,\"progress\":%u,"
      "\"polls\":%lu,\"stages\":%u,\"stage_list\":[",
      op, reader_ld_status_name(status), reader_ld_outcome_name(result->outcome),
      (long long)result->sdk_book_id, (unsigned)result->copies_removed,
      (unsigned)result->copies_skipped, (unsigned)result->legacy_notes,
      (unsigned)result->legacy_progress, state ? state->polls : 0,
      state ? (unsigned)state->stages : 0);
  shown = state ? state->stage_count : 0;
  if (shown > 8) shown = 8;
  for (i = 0; i < shown; i++) {
    if (i) putchar(',');
    quoted(state->stage_names[i]);
  }
  printf("],\"message\":");
  quoted(error->message);
  printf("}\n");
  return 0;
}

static int ld_setup(void) {
  const char *work = get("work", "");
  const char *file = get("file", "");
  const char *title = get("title", "S11 book");
  const char *sha = get("sha", "");
  exr_format format = parse_format(get("format", ""));
  exr_library *library;
  reader_catalog *catalog;
  reader_catalog_error catalog_error;
  reader_catalog_book book;
  exr_error error;
  int64_t id = 0;
  char sort_title[512];
  size_t size = 0, i;
  char *data = NULL;
  memset(&error, 0, sizeof(error));
  memset(&catalog_error, 0, sizeof(catalog_error));
  library = ld_library(work);
  if (!library) return 2;
  if (format == EXR_EPUB || format == EXR_CBZ || format == EXR_PDF) {
    if (exr_library_import_file(library, format, file, title, &id, &error) != EXR_OK) {
      fprintf(stderr, "s11 probe: import failed: %s\n", error.message);
      exr_library_close(library);
      return 2;
    }
  } else {
    data = read_all(file, &size);
    if (!data) { exr_library_close(library); return 2; }
    if (exr_library_import(library, format, data, size, title, &id, &error) != EXR_OK) {
      fprintf(stderr, "s11 probe: import failed: %s\n", error.message);
      free(data);
      exr_library_close(library);
      return 2;
    }
    free(data);
  }
  exr_library_close(library);
  catalog = ld_catalog(work);
  if (!catalog) return 2;
  if (strlen(title) >= sizeof(sort_title)) return 2;
  memcpy(sort_title, title, strlen(title) + 1);
  for (i = 0; sort_title[i]; i++)
    if (sort_title[i] >= 'A' && sort_title[i] <= 'Z') sort_title[i] = (char)(sort_title[i] + 32);
  memset(&book, 0, sizeof(book));
  book.format = format_key(format);
  book.sha256 = sha;
  book.title = title;
  book.author = "";
  book.sort_title = sort_title;
  book.location_kind = location_kind(format);
  book.source_bytes = get_u64("bytes", 0);
  book.sdk_book_id = id;
  if (reader_catalog_attach(catalog, &book, &catalog_error) != 0) {
    fprintf(stderr, "s11 probe: attach failed: %s\n", catalog_error.message);
    reader_catalog_close(&catalog, &catalog_error);
    return 2;
  }
  reader_catalog_close(&catalog, &catalog_error);
  printf("{\"op\":\"ld\",\"cmd\":\"setup\",\"id\":%lld}\n", (long long)id);
  return 0;
}

static int ld_remove(int mode) {
  const char *work = get("work", "");
  const char *key = get("key", "");
  exr_library *library;
  reader_catalog *catalog;
  reader_catalog_error catalog_error;
  reader_ld_options options;
  reader_ld_result result;
  reader_ld_error error;
  reader_ld_status status;
  ld_state state;
  char state_dir[8192];
  memset(&state, 0, sizeof(state));
  memset(&catalog_error, 0, sizeof(catalog_error));
  memset(&error, 0, sizeof(error));
  snprintf(state_dir, sizeof(state_dir), "%s", get("state", ""));
  library = ld_library(work);
  catalog = ld_catalog(work);
  if (!library || !catalog) return 2;
  reader_ld_options_init(&options);
  options.library = library;
  options.catalog = catalog;
  options.state_dir = state_dir;
  options.legacy_policy = READER_LD_LEGACY_REJECT;
  options.max_input_bytes = get_u64("max_input", 0);
  state.cancel_at = get("cancel_at", NULL);
  state.poll_limit = (unsigned long)get_u64("cancel_at_poll", 0);
  options.after_stage = ld_hook;
  options.stage_context = &state;
  options.control.cancelled = ld_cancelled;
  options.control.context = &state;
  reader_ld_result_init(&result);
  if (mode == 2) status = reader_ld_recover(&options, &result, &error);
  else if (mode == 1) status = reader_ld_reimport(&options, key, get("file", ""), &result, &error);
  else status = reader_ld_remove(&options, key, &result, &error);
  ld_emit_result(mode == 2 ? "recover" : mode == 1 ? "reimport" : "remove",
      status, &result, &error, &state);
  exr_library_close(library);
  reader_catalog_close(&catalog, &catalog_error);
  return 0;
}

typedef struct { int64_t id; int deleted; int found; } ld_meta;

static int ld_meta_visit(void *context, const reader_catalog_row *row) {
  ld_meta *meta = (ld_meta *)context;
  meta->id = row->sdk_book_id;
  meta->deleted = row->deleted;
  meta->found = 1;
  return 0;
}

static int ld_query(void) {
  const char *work = get("work", "");
  ld_meta meta;
  reader_catalog *catalog;
  reader_catalog_error catalog_error;
  int found = 0, present = 0;
  memset(&meta, 0, sizeof(meta));
  memset(&catalog_error, 0, sizeof(catalog_error));
  catalog = ld_catalog(work);
  if (!catalog) return 2;
  if (reader_catalog_metadata(catalog, get("key", ""), ld_meta_visit, &meta, &found, &catalog_error) != 0) {
    reader_catalog_close(&catalog, &catalog_error);
    return 2;
  }
  if (found && meta.id > 0 && reader_catalog_has_local(catalog, meta.id, &present, &catalog_error) != 0) {
    reader_catalog_close(&catalog, &catalog_error);
    return 2;
  }
  printf("{\"op\":\"ld\",\"cmd\":\"catalog\",\"found\":%d,\"mapped\":%lld,\"local\":%d,\"deleted\":%d}\n",
      found, (long long)(found ? meta.id : 0), present, found ? meta.deleted : 0);
  reader_catalog_close(&catalog, &catalog_error);
  return 0;
}

static int ld_pending(void) {
  reader_ld_pending_info info;
  reader_ld_error error;
  reader_ld_status status;
  char state_dir[8192];
  memset(&info, 0, sizeof(info));
  info.struct_size = sizeof(info);
  memset(&error, 0, sizeof(error));
  snprintf(state_dir, sizeof(state_dir), "%s", get("state", ""));
  status = reader_ld_pending(state_dir, &info, &error);
  printf("{\"op\":\"ld\",\"cmd\":\"pending\",\"status\":\"%s\",\"pending\":%d,"
      "\"stage\":\"%s\",\"copies\":%u,\"message\":",
      reader_ld_status_name(status), info.pending, reader_ld_stage_name(info.stage),
      (unsigned)info.copies);
  quoted(error.message);
  printf("}\n");
  return 0;
}

/* ------------------------------------------------------------- readback */

static int dump_source(exr_library *library, int64_t id, const char *out, const char *name) {
  exr_source source;
  exr_error error;
  char path[8192];
  FILE *file;
  unsigned char *buffer;
  uint64_t offset = 0;
  int ok = 1;
  memset(&source, 0, sizeof(source));
  memset(&error, 0, sizeof(error));
  if (exr_library_source(library, id, &source, &error) != EXR_OK) return 0;
  snprintf(path, sizeof(path), "%s/%s", out, name);
  file = open_utf8(path, "wb");
  buffer = (unsigned char *)malloc(65536);
  if (!file || !buffer) { if (file) fclose(file); free(buffer); source.release(source.context); return 0; }
  while (offset < source.size) {
    size_t want = source.size - offset > 65536 ? 65536 : (size_t)(source.size - offset);
    size_t got = source.read_at(source.context, offset, buffer, want);
    if (got != want || fwrite(buffer, 1, got, file) != got) { ok = 0; break; }
    offset += got;
  }
  fclose(file);
  free(buffer);
  source.release(source.context);
  return ok;
}

static int run_readback(void) {
  exr_library *library = NULL;
  exr_error error;
  exr_book *books = NULL;
  size_t count = 0, i;
  const char *out = get("out", ".");
  memset(&error, 0, sizeof(error));
  if (exr_library_open(get("library", ""), &library, &error) != EXR_OK) {
    printf("{\"op\":\"readback\",\"ok\":0,\"message\":");
    quoted(error.message);
    printf("}\n");
    return 1;
  }
  if (exr_library_books(library, NULL, &books, &count, &error) != EXR_OK) {
    printf("{\"op\":\"readback\",\"ok\":0,\"message\":");
    quoted(error.message);
    printf("}\n");
    exr_library_close(library);
    return 1;
  }
  printf("{\"op\":\"readback\",\"ok\":1,\"count\":%u,\"books\":[", (unsigned)count);
  for (i = 0; i < count; i++) {
    char name[128];
    exr_source probe;
    int read_ok = 0;
    uint64_t bytes = 0;
    memset(&probe, 0, sizeof(probe));
    snprintf(name, sizeof(name), "book-%lld.bin", (long long)books[i].id);
    if (i) putchar(',');
    if (exr_library_source(library, books[i].id, &probe, &error) == EXR_OK) {
      bytes = probe.size;
      probe.release(probe.context);
      read_ok = dump_source(library, books[i].id, out, name);
    }
    printf("{\"id\":%lld,\"format\":%d,\"bytes\":%llu,\"read_ok\":%d,\"dump\":\"%s\",\"title\":",
        (long long)books[i].id, (int)books[i].format, (unsigned long long)bytes, read_ok, name);
    quoted(books[i].title ? books[i].title : "");
    putchar('}');
  }
  printf("]}\n");
  exr_books_free(books, count);
  exr_library_close(library);
  return 0;
}

int main(int argc, char **argv) {
  const char *cmd;
  if (argc != 2 || read_spec(argv[1]) != 0) return 2;
  cmd = get("cmd", "");
  if (!strcmp(cmd, "import")) return run_import();
  if (!strcmp(cmd, "scan")) return run_scan();
  if (!strcmp(cmd, "batch")) return run_batch();
  if (!strcmp(cmd, "cloud")) return run_cloud();
  if (!strcmp(cmd, "readback")) return run_readback();
  if (!strcmp(cmd, "ld-setup")) return ld_setup();
  if (!strcmp(cmd, "ld-remove")) return ld_remove(0);
  if (!strcmp(cmd, "ld-reimport")) return ld_remove(1);
  if (!strcmp(cmd, "ld-recover")) return ld_remove(2);
  if (!strcmp(cmd, "ld-query")) return ld_query();
  if (!strcmp(cmd, "ld-pending")) return ld_pending();
  if (!strcmp(cmd, "selftest")) {
    printf("{\"op\":\"selftest\",\"ok\":1}\n");
    return 0;
  }
  return 2;
}
