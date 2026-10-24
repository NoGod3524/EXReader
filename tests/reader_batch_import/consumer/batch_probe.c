/* SPDX-License-Identifier: MIT */
#ifndef _WIN32
#define _POSIX_C_SOURCE 200809L
#endif
#include "reader_batch_import.h"
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
#include <wchar.h>
#endif

typedef struct {
  char *path;
  char *relative;
  exr_format format;
  uint64_t size_hint;
} scan_item;

typedef struct {
  int cancel;
  int cancel_after_calls;
  unsigned long calls;
  int committed;
  int cancel_after_commits;
} cancel_state;

static FILE *probe_fopen(const char *path, const char *mode) {
#ifdef _WIN32
  int count = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, path, -1, NULL, 0);
  int mcount;
  wchar_t *wide, *wmode;
  FILE *file;
  if (count <= 0) return NULL;
  wide = malloc((size_t)count * sizeof(*wide));
  if (!wide) return NULL;
  if (!MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, path, -1, wide, count)) {
    free(wide);
    return NULL;
  }
  mcount = MultiByteToWideChar(CP_UTF8, 0, mode, -1, NULL, 0);
  wmode = malloc((size_t)mcount * sizeof(*wmode));
  if (!wmode) {
    free(wide);
    return NULL;
  }
  MultiByteToWideChar(CP_UTF8, 0, mode, -1, wmode, mcount);
  file = _wfopen(wide, wmode);
  free(wide);
  free(wmode);
  return file;
#else
  return fopen(path, mode);
#endif
}

static const char *arg_value(int argc, char **argv, const char *name) {
  int i;
  for (i = 1; i + 1 < argc; i++)
    if (!strcmp(argv[i], name)) return argv[i + 1];
  return NULL;
}

static int has_flag(int argc, char **argv, const char *name) {
  int i;
  for (i = 1; i < argc; i++)
    if (!strcmp(argv[i], name)) return 1;
  return 0;
}

static unsigned long long arg_u64(int argc, char **argv, const char *name,
    unsigned long long fallback) {
  const char *text = arg_value(argc, argv, name);
  char *end = NULL;
  unsigned long long value;
  if (!text) return fallback;
  value = strtoull(text, &end, 10);
  if (!end || *end) return fallback;
  return value;
}

static int parse_format(const char *name, exr_format *format) {
  if (!strcmp(name, "TXT")) { *format = EXR_TXT; return 0; }
  if (!strcmp(name, "HTML")) { *format = EXR_HTML; return 0; }
  if (!strcmp(name, "FB2")) { *format = EXR_FB2; return 0; }
  if (!strcmp(name, "EPUB")) { *format = EXR_EPUB; return 0; }
  if (!strcmp(name, "DOCX")) { *format = EXR_DOCX; return 0; }
  if (!strcmp(name, "RTF")) { *format = EXR_RTF; return 0; }
  if (!strcmp(name, "MOBI")) { *format = EXR_MOBI; return 0; }
  if (!strcmp(name, "PDF")) { *format = EXR_PDF; return 0; }
  if (!strcmp(name, "CBZ")) { *format = EXR_CBZ; return 0; }
  return -1;
}

static int cancel_callback(void *context) {
  cancel_state *state = context;
  if (state->cancel) return 1;
  if (state->cancel_after_calls > 0) {
    state->calls++;
    if (state->calls >= (unsigned long)state->cancel_after_calls) return 1;
  }
  return 0;
}

static void result_callback(void *context, size_t index,
    const reader_batch_result *result) {
  cancel_state *state = context;
  (void)index;
  if (result->committed) state->committed++;
  if (state->cancel_after_commits > 0 &&
      state->committed >= state->cancel_after_commits)
    state->cancel = 1;
}

static int write_scan(const char *path, reader_batch_scan_options *options,
    unsigned long long cancel_after_batches, int *exit_code) {
  reader_batch_enumerator *enumerator = NULL;
  reader_batch_error error;
  FILE *out;
  size_t total = 0, batches = 0, max_batch = 0;
  int complete = 0, truncated = 0, cancelled = 0;
  reader_batch_status status;
  cancel_state control;
  memset(&control, 0, sizeof(control));
  options->control.cancelled = cancel_callback;
  options->control.context = &control;
  memset(&error, 0, sizeof(error));
  status = reader_batch_enumerate_open(options, &enumerator, &error);
  if (status != READER_BATCH_OK) {
    fprintf(stderr, "enumerate open: %s: %s\n", reader_batch_status_name(status),
        error.message);
    *exit_code = 2;
    return 1;
  }
  out = probe_fopen(path, "wb");
  if (!out) {
    fprintf(stderr, "cannot write %s\n", path);
    reader_batch_enumerate_close(enumerator);
    *exit_code = 2;
    return 1;
  }
  fprintf(out, "# batch-enumerate v1\n");
  while (!complete && !truncated) {
    reader_batch_candidate *items = NULL;
    size_t count = 0, i;
    status = reader_batch_enumerate_next(enumerator, &items, &count, &complete,
        &truncated, &error);
    if (status != READER_BATCH_OK) {
      fprintf(out, "status\t%s\t%s\n", reader_batch_status_name(status),
          error.message);
      reader_batch_candidates_free(items, count);
      if (status == READER_BATCH_CANCELLED) {
        cancelled = 1;
        break;
      }
      fprintf(stderr, "enumerate: %s: %s\n", reader_batch_status_name(status),
          error.message);
      *exit_code = 2;
      fclose(out);
      reader_batch_enumerate_close(enumerator);
      return 1;
    }
    batches++;
    if (count > max_batch) max_batch = count;
    for (i = 0; i < count; i++) {
      fprintf(out, "candidate\t%s\t%llu\t%s\t%s\n",
          reader_batch_format_name(items[i].format),
          (unsigned long long)items[i].size_hint,
          items[i].relative_path, items[i].path);
      total++;
    }
    reader_batch_candidates_free(items, count);
    if (cancel_after_batches && batches >= cancel_after_batches)
      control.cancel = 1;
  }
  fprintf(out, "batches\t%llu\n", (unsigned long long)batches);
  fprintf(out, "max_batch\t%llu\n", (unsigned long long)max_batch);
  fprintf(out, "count\t%llu\n", (unsigned long long)total);
  fprintf(out, "complete\t%d\n", complete);
  fprintf(out, "truncated\t%d\n", truncated);
  fprintf(out, "cancelled\t%d\n", cancelled);
  fclose(out);
  reader_batch_enumerate_close(enumerator);
  *exit_code = 0;
  return 0;
}

static int load_scan(const char *path, scan_item **items_out, size_t *count_out) {
  FILE *file = probe_fopen(path, "rb");
  char line[131072];
  scan_item *items = NULL;
  size_t count = 0, capacity = 0;
  if (!file) return -1;
  while (fgets(line, sizeof(line), file)) {
    char *fields[5];
    char *cursor = line;
    size_t field = 0;
    size_t length;
    exr_format format;
    length = strlen(line);
    while (length && (line[length - 1] == '\n' || line[length - 1] == '\r'))
      line[--length] = 0;
    if (!line[0] || line[0] == '#') continue;
    fields[field++] = cursor;
    while (field < 5 && (cursor = strchr(cursor, '\t')) != NULL) {
      *cursor++ = 0;
      fields[field++] = cursor;
    }
    if (field < 5 || strcmp(fields[0], "candidate")) continue;
    if (parse_format(fields[1], &format) != 0) continue;
    if (count == capacity) {
      size_t next = capacity ? capacity * 2 : 16;
      scan_item *grown = realloc(items, next * sizeof(*grown));
      if (!grown) {
        free(items);
        fclose(file);
        return -1;
      }
      items = grown;
      capacity = next;
    }
    items[count].path = malloc(strlen(fields[4]) + 1);
    items[count].relative = malloc(strlen(fields[3]) + 1);
    if (!items[count].path || !items[count].relative) {
      free(items[count].path);
      free(items[count].relative);
      free(items);
      fclose(file);
      return -1;
    }
    strcpy(items[count].path, fields[4]);
    strcpy(items[count].relative, fields[3]);
    items[count].format = format;
    items[count].size_hint = strtoull(fields[2], NULL, 10);
    count++;
  }
  fclose(file);
  *items_out = items;
  *count_out = count;
  return 0;
}

static int export_original(exr_library *library, int64_t book_id,
    const char *directory, FILE *out, int *exit_code) {
  void *data = NULL;
  size_t size = 0;
  exr_error error;
  char path[4096];
  FILE *original;
  snprintf(path, sizeof(path), "%s/%lld.bin", directory, (long long)book_id);
  memset(&error, 0, sizeof(error));
  if (exr_library_blob(library, book_id, 0, &data, &size, &error) != EXR_OK) {
    fprintf(out, "original-error\t%lld\t%s\n", (long long)book_id, error.message);
    *exit_code = 2;
    return 1;
  }
  original = probe_fopen(path, "wb");
  if (!original) {
    free(data);
    fprintf(out, "original-error\t%lld\tcannot write\n", (long long)book_id);
    *exit_code = 2;
    return 1;
  }
  if (size && fwrite(data, 1, size, original) != size) {
    fclose(original);
    free(data);
    fprintf(out, "original-error\t%lld\tcannot write\n", (long long)book_id);
    *exit_code = 2;
    return 1;
  }
  fclose(original);
  free(data);
  fprintf(out, "original\t%lld\t%s\t%llu\n", (long long)book_id, path,
      (unsigned long long)size);
  return 0;
}

static int run_import(int argc, char **argv, int *exit_code) {
  const char *library_path = arg_value(argc, argv, "--library");
  const char *staging = arg_value(argc, argv, "--staging");
  const char *scan_path = arg_value(argc, argv, "--scan");
  const char *out_path = arg_value(argc, argv, "--out");
  const char *export_dir = arg_value(argc, argv, "--export-dir");
  unsigned long long batch = arg_u64(argc, argv, "--batch", 8);
  unsigned long long cancel_commits = arg_u64(argc, argv, "--cancel-after-commits", 0);
  unsigned long long cancel_calls = arg_u64(argc, argv, "--cancel-after-calls", 0);
  exr_library *library = NULL;
  exr_error sdk_error;
  reader_batch_error batch_error;
  reader_batch_import_options options;
  cancel_state control;
  FILE *out;
  scan_item *items = NULL;
  size_t count = 0, offset = 0;
  unsigned long long totals[5] = {0, 0, 0, 0, 0};
  int failed = 0;
  if (!library_path || !staging || !scan_path || !out_path) {
    fprintf(stderr, "import needs --library --staging --scan --out\n");
    *exit_code = 2;
    return 1;
  }
  if (!batch || batch > READER_BATCH_MAX_BATCH) {
    fprintf(stderr, "batch must be 1..%u\n", READER_BATCH_MAX_BATCH);
    *exit_code = 2;
    return 1;
  }
  if (load_scan(scan_path, &items, &count) != 0) {
    fprintf(stderr, "cannot load scan\n");
    *exit_code = 2;
    return 1;
  }
  memset(&sdk_error, 0, sizeof(sdk_error));
  memset(&batch_error, 0, sizeof(batch_error));
  if (exr_library_open(library_path, &library, &sdk_error) != EXR_OK) {
    fprintf(stderr, "cannot open library: %s\n", sdk_error.message);
    *exit_code = 2;
    return 1;
  }
  out = probe_fopen(out_path, "wb");
  if (!out) {
    fprintf(stderr, "cannot write %s\n", out_path);
    *exit_code = 2;
    return 1;
  }
  fprintf(out, "# batch-import v1\n");
  reader_batch_import_options_init(&options);
  options.staging_dir = staging;
  memset(&control, 0, sizeof(control));
  control.cancel_after_commits = (int)cancel_commits;
  control.cancel_after_calls = (int)cancel_calls;
  options.control.cancelled = cancel_callback;
  options.control.context = &control;
  options.on_result = result_callback;
  options.on_result_context = &control;
  while (offset < count) {
    size_t chunk = count - offset;
    reader_batch_item *batch_items;
    reader_batch_result *results = NULL;
    size_t result_count = 0, i;
    reader_batch_status status;
    if (chunk > batch) chunk = (size_t)batch;
    batch_items = calloc(chunk, sizeof(*batch_items));
    if (!batch_items) {
      fprintf(stderr, "cannot allocate batch\n");
      *exit_code = 2;
      failed = 1;
      break;
    }
    for (i = 0; i < chunk; i++) {
      batch_items[i].struct_size = sizeof(batch_items[i]);
      batch_items[i].path = items[offset + i].path;
      batch_items[i].title = NULL;
      batch_items[i].format = items[offset + i].format;
    }
    status = reader_batch_import(library, batch_items, chunk, &options, &results,
        &result_count, &batch_error);
    fprintf(out, "aggregate\t%s\n", reader_batch_status_name(status));
    if (status == READER_BATCH_ARGUMENT || status == READER_BATCH_MEMORY ||
        status == READER_BATCH_INTERNAL) {
      fprintf(stderr, "import: %s\n", batch_error.message);
      free(batch_items);
      reader_batch_results_free(results, result_count);
      *exit_code = 2;
      failed = 1;
      break;
    }
    for (i = 0; i < result_count; i++) {
      fprintf(out, "result\t%llu\t%s\t%d\t%d\t%lld\t%s\t%s\t%d\t%s\n",
          (unsigned long long)(offset + i),
          reader_batch_item_status_name(results[i].status),
          results[i].committed, results[i].created,
          (long long)results[i].book_id,
          reader_batch_format_name(results[i].format),
          items[offset + i].relative,
          (int)results[i].status_code,
          results[i].message);
      if (results[i].status == READER_BATCH_ITEM_IMPORTED) totals[0]++;
      else if (results[i].status == READER_BATCH_ITEM_DUPLICATE) totals[1]++;
      else if (results[i].status == READER_BATCH_ITEM_FAILED) totals[2]++;
      else if (results[i].status == READER_BATCH_ITEM_CANCELLED) totals[3]++;
      else totals[4]++;
      if (export_dir && results[i].committed)
        export_original(library, results[i].book_id, export_dir, out, exit_code);
    }
    reader_batch_results_free(results, result_count);
    free(batch_items);
    offset += chunk;
    if (status == READER_BATCH_CANCELLED) break;
  }
  fprintf(out, "attempted\t%llu\n", (unsigned long long)offset);
  fprintf(out, "imported\t%llu\n", totals[0]);
  fprintf(out, "duplicate\t%llu\n", totals[1]);
  fprintf(out, "failed\t%llu\n", totals[2]);
  fprintf(out, "cancelled\t%llu\n", totals[3]);
  fprintf(out, "not_attempted\t%llu\n", totals[4]);
  fclose(out);
  exr_library_close(library);
  for (offset = 0; offset < count; offset++) {
    free(items[offset].path);
    free(items[offset].relative);
  }
  free(items);
  if (failed) *exit_code = 2;
  return 0;
}

static exr_book *find_book(exr_library *library, int64_t id, exr_book **books_out,
    size_t *count_out, exr_error *error) {
  exr_book *books = NULL;
  size_t count = 0, i;
  if (exr_library_books(library, NULL, &books, &count, error) != EXR_OK) return NULL;
  for (i = 0; i < count; i++)
    if (books[i].id == id) {
      *books_out = books;
      *count_out = count;
      return &books[i];
    }
  exr_books_free(books, count);
  return NULL;
}

static int run_list(int argc, char **argv, int *exit_code) {
  const char *library_path = arg_value(argc, argv, "--library");
  const char *out_path = arg_value(argc, argv, "--out");
  exr_library *library = NULL;
  exr_book *books = NULL;
  size_t count = 0, i;
  exr_error error;
  FILE *out;
  if (!library_path || !out_path) {
    fprintf(stderr, "list needs --library --out\n");
    *exit_code = 2;
    return 1;
  }
  memset(&error, 0, sizeof(error));
  if (exr_library_open(library_path, &library, &error) != EXR_OK) {
    fprintf(stderr, "cannot open library: %s\n", error.message);
    *exit_code = 2;
    return 1;
  }
  if (exr_library_books(library, NULL, &books, &count, &error) != EXR_OK) {
    fprintf(stderr, "cannot list books: %s\n", error.message);
    exr_library_close(library);
    *exit_code = 2;
    return 1;
  }
  out = probe_fopen(out_path, "wb");
  if (!out) {
    exr_books_free(books, count);
    exr_library_close(library);
    *exit_code = 2;
    return 1;
  }
  fprintf(out, "# books v1\n");
  for (i = 0; i < count; i++)
    fprintf(out, "book\t%lld\t%s\t%s\t%s\t%d\t%d\t%llu\n",
        (long long)books[i].id, reader_batch_format_name(books[i].format),
        books[i].title ? books[i].title : "",
        books[i].author ? books[i].author : "",
        books[i].favorite, books[i].status,
        (unsigned long long)books[i].position);
  fprintf(out, "count\t%llu\n", (unsigned long long)count);
  fclose(out);
  exr_books_free(books, count);
  exr_library_close(library);
  *exit_code = 0;
  return 0;
}

static int run_metadata(int argc, char **argv, int *exit_code, int set) {
  const char *library_path = arg_value(argc, argv, "--library");
  const char *out_path = arg_value(argc, argv, "--out");
  const char *title = arg_value(argc, argv, "--title");
  unsigned long long id = arg_u64(argc, argv, "--book", 0);
  unsigned long long favorite = arg_u64(argc, argv, "--favorite", 0);
  exr_library *library = NULL;
  exr_book *books = NULL;
  exr_book *book;
  char *replacement = NULL;
  size_t count = 0;
  exr_error error;
  FILE *out;
  if (!library_path || !out_path || !id) {
    fprintf(stderr, "metadata needs --library --book --out\n");
    *exit_code = 2;
    return 1;
  }
  memset(&error, 0, sizeof(error));
  if (exr_library_open(library_path, &library, &error) != EXR_OK) {
    fprintf(stderr, "cannot open library: %s\n", error.message);
    *exit_code = 2;
    return 1;
  }
  book = find_book(library, (int64_t)id, &books, &count, &error);
  if (!book) {
    fprintf(stderr, "book not found: %s\n", error.message);
    exr_library_close(library);
    *exit_code = 2;
    return 1;
  }
  if (set) {
    if (title) {
      size_t length = strlen(title) + 1;
      replacement = malloc(length);
      if (!replacement) {
        exr_books_free(books, count);
        exr_library_close(library);
        *exit_code = 2;
        return 1;
      }
      memcpy(replacement, title, length);
      book->title = replacement;
    }
    book->favorite = favorite ? 1 : 0;
    if (exr_library_update(library, book, &error) != EXR_OK) {
      fprintf(stderr, "cannot update: %s\n", error.message);
      exr_books_free(books, count);
      exr_library_close(library);
      *exit_code = 2;
      return 1;
    }
  }
  out = probe_fopen(out_path, "wb");
  if (!out) {
    exr_books_free(books, count);
    exr_library_close(library);
    *exit_code = 2;
    return 1;
  }
  fprintf(out, "metadata\t%lld\t%s\t%d\n", (long long)book->id,
      book->title ? book->title : "", book->favorite);
  fclose(out);
  exr_books_free(books, count);
  exr_library_close(library);
  *exit_code = 0;
  return 0;
}

static int run_preimport(int argc, char **argv, int *exit_code) {
  const char *library_path = arg_value(argc, argv, "--library");
  const char *format_name = arg_value(argc, argv, "--format");
  const char *path = arg_value(argc, argv, "--path");
  const char *out_path = arg_value(argc, argv, "--out");
  exr_format format;
  exr_library *library = NULL;
  exr_error error;
  FILE *file;
  unsigned char *data = NULL;
  long size;
  int64_t id = 0;
  FILE *out;
  if (!library_path || !format_name || !path || !out_path ||
      parse_format(format_name, &format) != 0) {
    fprintf(stderr, "preimport needs --library --format --path --out\n");
    *exit_code = 2;
    return 1;
  }
  file = probe_fopen(path, "rb");
  if (!file) {
    *exit_code = 2;
    return 1;
  }
  fseek(file, 0, SEEK_END);
  size = ftell(file);
  fseek(file, 0, SEEK_SET);
  if (size <= 0) {
    fclose(file);
    *exit_code = 2;
    return 1;
  }
  data = malloc((size_t)size);
  if (!data || fread(data, 1, (size_t)size, file) != (size_t)size) {
    free(data);
    fclose(file);
    *exit_code = 2;
    return 1;
  }
  fclose(file);
  memset(&error, 0, sizeof(error));
  if (exr_library_open(library_path, &library, &error) != EXR_OK) {
    free(data);
    *exit_code = 2;
    return 1;
  }
  if (exr_library_import(library, format, data, (size_t)size, NULL, &id, &error) != EXR_OK) {
    fprintf(stderr, "preimport: %s\n", error.message);
    free(data);
    exr_library_close(library);
    *exit_code = 2;
    return 1;
  }
  out = probe_fopen(out_path, "wb");
  if (out) {
    fprintf(out, "preimport\t%lld\t%s\n", (long long)id,
        reader_batch_format_name(format));
    fclose(out);
  }
  free(data);
  exr_library_close(library);
  *exit_code = 0;
  return 0;
}

static int run_epub_info(int argc, char **argv, int *exit_code) {
  const char *library_path = arg_value(argc, argv, "--library");
  const char *out_path = arg_value(argc, argv, "--out");
  unsigned long long id = arg_u64(argc, argv, "--book", 0);
  exr_library *library = NULL;
  exr_library_epub_info info;
  exr_error error;
  FILE *out;
  exr_status status;
  if (!library_path || !out_path || !id) {
    *exit_code = 2;
    return 1;
  }
  memset(&error, 0, sizeof(error));
  if (exr_library_open(library_path, &library, &error) != EXR_OK) {
    *exit_code = 2;
    return 1;
  }
  memset(&info, 0, sizeof(info));
  info.struct_size = sizeof(info);
  status = exr_library_epub_info_get(library, (int64_t)id, &info, &error);
  out = probe_fopen(out_path, "wb");
  if (out) {
    fprintf(out, "epub-info\t%llu\t%d\t%d\t%s\t%s\n", id, info.bounded_storage,
        info.global_extent_known, reader_batch_status_name(
            status == EXR_OK ? READER_BATCH_OK : READER_BATCH_IO),
        error.message);
    fclose(out);
  }
  exr_library_close(library);
  *exit_code = status == EXR_OK ? 0 : 2;
  return 0;
}

static int run_limits(int argc, char **argv, int *exit_code) {
  const char *library_path = arg_value(argc, argv, "--library");
  const char *staging = arg_value(argc, argv, "--staging");
  const char *out_path = arg_value(argc, argv, "--out");
  exr_library *library = NULL;
  exr_error error;
  reader_batch_scan_options scan;
  reader_batch_import_options import;
  reader_batch_error batch_error;
  reader_batch_item *items;
  reader_batch_enumerator *enumerator = NULL;
  reader_batch_result *results = NULL;
  size_t result_count = 0;
  FILE *out;
  if (!library_path || !staging || !out_path) {
    *exit_code = 2;
    return 1;
  }
  memset(&error, 0, sizeof(error));
  if (exr_library_open(library_path, &library, &error) != EXR_OK) {
    *exit_code = 2;
    return 1;
  }
  out = probe_fopen(out_path, "wb");
  if (!out) {
    exr_library_close(library);
    *exit_code = 2;
    return 1;
  }
  fprintf(out, "# limits v1\n");
  memset(&batch_error, 0, sizeof(batch_error));
  reader_batch_scan_options_init(&scan);
  scan.root = ".";
  scan.batch_size = 101;
  fprintf(out, "scan-batch-101\t%s\n", reader_batch_status_name(
      reader_batch_enumerate_open(&scan, &enumerator, &batch_error)));
  if (enumerator) { reader_batch_enumerate_close(enumerator); enumerator = NULL; }
  reader_batch_scan_options_init(&scan);
  scan.root = ".";
  scan.max_depth = 17;
  fprintf(out, "scan-depth-17\t%s\n", reader_batch_status_name(
      reader_batch_enumerate_open(&scan, &enumerator, &batch_error)));
  if (enumerator) { reader_batch_enumerate_close(enumerator); enumerator = NULL; }
  reader_batch_scan_options_init(&scan);
  scan.root = ".";
  scan.max_candidates = 10001;
  fprintf(out, "scan-candidates-10001\t%s\n", reader_batch_status_name(
      reader_batch_enumerate_open(&scan, &enumerator, &batch_error)));
  if (enumerator) { reader_batch_enumerate_close(enumerator); enumerator = NULL; }
  reader_batch_import_options_init(&import);
  import.staging_dir = staging;
  items = calloc(101, sizeof(*items));
  if (!items) {
    fclose(out);
    exr_library_close(library);
    *exit_code = 2;
    return 1;
  }
  {
    size_t i;
    for (i = 0; i < 101; i++) {
      items[i].struct_size = sizeof(items[i]);
      items[i].path = "missing.txt";
      items[i].format = EXR_TXT;
    }
  }
  fprintf(out, "import-count-0\t%s\n", reader_batch_status_name(
      reader_batch_import(library, items, 0, &import, &results, &result_count,
          &batch_error)));
  reader_batch_results_free(results, result_count);
  results = NULL;
  fprintf(out, "import-count-101\t%s\n", reader_batch_status_name(
      reader_batch_import(library, items, 101, &import, &results, &result_count,
          &batch_error)));
  reader_batch_results_free(results, result_count);
  free(items);
  fprintf(out, "status-names\t%s\t%s\t%s\n",
      reader_batch_status_name(READER_BATCH_OK),
      reader_batch_item_status_name(READER_BATCH_ITEM_DUPLICATE),
      reader_batch_format_name(EXR_MOBI));
  fclose(out);
  exr_library_close(library);
  *exit_code = 0;
  return 0;
}

int main(int argc, char **argv) {
  int exit_code = 0;
  if (argc < 2) {
    fprintf(stderr,
        "usage: batch-probe enumerate|import|list|set-metadata|get-metadata|"
        "preimport-memory|epub-info|limits ...\n");
    return 2;
  }
  if (!strcmp(argv[1], "enumerate")) {
    const char *root = arg_value(argc, argv, "--root");
    const char *out = arg_value(argc, argv, "--out");
    reader_batch_scan_options options;
    if (!root || !out) {
      fprintf(stderr, "enumerate needs --root --out\n");
      return 2;
    }
    reader_batch_scan_options_init(&options);
    options.root = root;
    options.recursive = has_flag(argc, argv, "--recursive");
    if (arg_value(argc, argv, "--max-depth"))
      options.max_depth = (size_t)arg_u64(argc, argv, "--max-depth", 0);
    if (arg_value(argc, argv, "--max-dirs"))
      options.max_directories = (size_t)arg_u64(argc, argv, "--max-dirs", 0);
    if (arg_value(argc, argv, "--max-candidates"))
      options.max_candidates = (size_t)arg_u64(argc, argv, "--max-candidates", 0);
    if (arg_value(argc, argv, "--max-path"))
      options.max_path_bytes = (size_t)arg_u64(argc, argv, "--max-path", 0);
    if (arg_value(argc, argv, "--max-pending"))
      options.max_pending_bytes = (size_t)arg_u64(argc, argv, "--max-pending", 0);
    if (arg_value(argc, argv, "--batch-size"))
      options.batch_size = (size_t)arg_u64(argc, argv, "--batch-size", 0);
    write_scan(out, &options, arg_u64(argc, argv, "--cancel-after-batches", 0),
        &exit_code);
    return exit_code;
  }
  if (!strcmp(argv[1], "import")) {
    run_import(argc, argv, &exit_code);
    return exit_code;
  }
  if (!strcmp(argv[1], "list")) {
    run_list(argc, argv, &exit_code);
    return exit_code;
  }
  if (!strcmp(argv[1], "set-metadata")) {
    run_metadata(argc, argv, &exit_code, 1);
    return exit_code;
  }
  if (!strcmp(argv[1], "get-metadata")) {
    run_metadata(argc, argv, &exit_code, 0);
    return exit_code;
  }
  if (!strcmp(argv[1], "preimport-memory")) {
    run_preimport(argc, argv, &exit_code);
    return exit_code;
  }
  if (!strcmp(argv[1], "epub-info")) {
    run_epub_info(argc, argv, &exit_code);
    return exit_code;
  }
  if (!strcmp(argv[1], "limits")) {
    run_limits(argc, argv, &exit_code);
    return exit_code;
  }
  fprintf(stderr, "unknown command %s\n", argv[1]);
  return 2;
}
