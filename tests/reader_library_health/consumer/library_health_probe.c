/* SPDX-License-Identifier: MIT */
/* Installed C consumer for the optional library-health package. It builds real
   catalogs and SDK libraries through the public product and SDK APIs, then
   exercises the scanner: the 2202-row catalog, cancellation, step budgets,
   total-row limits, reentry, wrong thread, catalog/source change during a scan,
   argument bounds and bounded-memory streaming reads. */
#include "reader_library_health.h"
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#if defined(_WIN32)
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <psapi.h>
#else
#include <pthread.h>
#include <sys/resource.h>
#endif

#define MAX_PLAN 8192
#define MAX_CHECKS 96
#define MAX_DELETED 64
#define MEMORY_PEAK_BUDGET (4u * 1024u * 1024u)

typedef struct {
  char sort_title[32];
  char format[8];
  char sha256[65];
  uint64_t bytes;
  char file[512];
  char action[16];
} plan_row;

typedef struct {
  plan_row rows[MAX_PLAN];
  size_t count;
} plan_file;

typedef struct {
  char id[64];
  int passed;
  char detail[256];
} check_rec;

static check_rec g_checks[MAX_CHECKS];
static size_t g_check_count;
static size_t g_check_failed;

static void add_check(const char *id, int passed, const char *fmt, ...) {
  check_rec *c;
  va_list ap;
  if (g_check_count >= MAX_CHECKS) return;
  c = &g_checks[g_check_count++];
  snprintf(c->id, sizeof(c->id), "%s", id);
  c->passed = passed ? 1 : 0;
  if (!passed) g_check_failed++;
  va_start(ap, fmt);
  vsnprintf(c->detail, sizeof(c->detail), fmt, ap);
  va_end(ap);
}

static const char *platform_name(void) {
#if defined(_WIN32)
  return "windows";
#elif defined(__APPLE__)
  return "macos";
#else
  return "linux";
#endif
}

static void path_join(char *out, size_t capacity, const char *dir, const char *name) {
  snprintf(out, capacity, "%s/%s", dir, name);
}

static int read_plan(const char *path, plan_file *p) {
  FILE *file = fopen(path, "rb");
  char line[1200];
  if (!file) return 0;
  p->count = 0;
  while (fgets(line, sizeof(line), file)) {
    size_t length = strlen(line);
    plan_row *r;
    char *fields[6];
    size_t count = 0;
    char *at = line;
    unsigned long long bytes = 0;
    while (length && (line[length - 1] == '\n' || line[length - 1] == '\r')) line[--length] = 0;
    if (!length || line[0] == '#') continue;
    if (p->count >= MAX_PLAN) { fclose(file); return 0; }
    while (count < 6) {
      fields[count++] = at;
      at = strchr(at, '\t');
      if (!at) break;
      *at++ = 0;
    }
    if (count != 6) { fclose(file); return 0; }
    if (sscanf(fields[3], "%llu", &bytes) != 1) { fclose(file); return 0; }
    r = &p->rows[p->count];
    snprintf(r->sort_title, sizeof(r->sort_title), "%s", fields[0]);
    snprintf(r->format, sizeof(r->format), "%s", fields[1]);
    snprintf(r->sha256, sizeof(r->sha256), "%s", fields[2]);
    r->bytes = (uint64_t)bytes;
    snprintf(r->file, sizeof(r->file), "%s", fields[4]);
    snprintf(r->action, sizeof(r->action), "%s", fields[5]);
    p->count++;
  }
  fclose(file);
  return p->count > 0;
}

static unsigned char *read_file(const char *path, size_t *size) {
  FILE *file = fopen(path, "rb");
  long length;
  unsigned char *data;
  if (!file) return NULL;
  if (fseek(file, 0, SEEK_END) != 0) { fclose(file); return NULL; }
  length = ftell(file);
  if (length < 0) { fclose(file); return NULL; }
  rewind(file);
  data = (unsigned char *)malloc((size_t)length + 1);
  if (!data) { fclose(file); return NULL; }
  if (fread(data, 1, (size_t)length, file) != (size_t)length) {
    free(data);
    fclose(file);
    return NULL;
  }
  fclose(file);
  *size = (size_t)length;
  return data;
}

static exr_format format_enum(const char *name) {
  if (!strcmp(name, "txt")) return EXR_TXT;
  if (!strcmp(name, "html")) return EXR_HTML;
  if (!strcmp(name, "fb2")) return EXR_FB2;
  if (!strcmp(name, "epub")) return EXR_EPUB;
  if (!strcmp(name, "docx")) return EXR_DOCX;
  if (!strcmp(name, "rtf")) return EXR_RTF;
  if (!strcmp(name, "mobi")) return EXR_MOBI;
  if (!strcmp(name, "pdf")) return EXR_PDF;
  if (!strcmp(name, "cbz")) return EXR_CBZ;
  return EXR_CUSTOM;
}

static const char *location_of(const char *format) {
  if (!strcmp(format, "pdf") || !strcmp(format, "cbz")) return "fixed_page";
  if (!strcmp(format, "epub")) return "epub_chapter";
  return "reflow_global";
}

static reader_health_verdict expected_verdict(const char *action) {
  if (!strcmp(action, "map")) return READER_HEALTH_VERIFIED;
  if (!strcmp(action, "cloud")) return READER_HEALTH_CLOUD_ONLY;
  if (!strcmp(action, "missing")) return READER_HEALTH_MAPPING_MISSING;
  if (!strcmp(action, "hash_bad")) return READER_HEALTH_HASH_MISMATCH;
  if (!strcmp(action, "size_short")) return READER_HEALTH_SIZE_MISMATCH;
  if (!strcmp(action, "size_long")) return READER_HEALTH_SIZE_MISMATCH;
  if (!strcmp(action, "limit")) return READER_HEALTH_LIMIT_SKIPPED;
  return READER_HEALTH_SOURCE_UNAVAILABLE;
}

static uint64_t catalog_bytes(const plan_row *r) {
  if (!strcmp(r->action, "size_short")) return r->bytes + 5;
  if (!strcmp(r->action, "size_long")) return r->bytes - 3;
  return r->bytes;
}

static void catalog_key(const plan_row *r, char out[80]) {
  char sha[65];
  memcpy(sha, r->sha256, sizeof(sha));
  if (!strcmp(r->action, "hash_bad")) sha[63] = sha[63] == '0' ? '1' : '0';
  snprintf(out, 80, "%s:%s", r->format, sha);
}

static int open_pair(const char *dir, reader_catalog **catalog, exr_library **library,
                     char *catalog_path, char *library_path) {
  reader_catalog_error catalog_error;
  exr_error error;
  path_join(catalog_path, 1024, dir, "catalog.db");
  path_join(library_path, 1024, dir, "library.db");
  memset(&catalog_error, 0, sizeof(catalog_error));
  memset(&error, 0, sizeof(error));
  *catalog = NULL;
  *library = NULL;
  if (reader_catalog_open(catalog_path, catalog, &catalog_error) != 0) {
    snprintf(catalog_path, 1024, "catalog open failed: %s", catalog_error.message);
    return 0;
  }
  if (exr_library_open(library_path, library, &error) != EXR_OK) {
    reader_catalog_close(catalog, &catalog_error);
    return 0;
  }
  return 1;
}

static int build_pair(const char *dir, const char *fixtures, const plan_row *rows, size_t count,
                      const char *extra_file, int64_t *ids, int64_t *extra_id, char *why,
                      size_t why_size) {
  reader_catalog *catalog = NULL;
  exr_library *library = NULL;
  reader_catalog_error catalog_error;
  exr_error error;
  char catalog_path[1024], library_path[1024], file_path[1600];
  int64_t deleted[MAX_DELETED];
  size_t deleted_count = 0, i;
  int ok = 1;
  memset(&catalog_error, 0, sizeof(catalog_error));
  memset(&error, 0, sizeof(error));
  if (why && why_size) why[0] = 0;
  if (!open_pair(dir, &catalog, &library, catalog_path, library_path)) {
    if (why) snprintf(why, why_size, "cannot open %s", catalog_path);
    return 0;
  }
  if (extra_id) *extra_id = 0;
  for (i = 0; i < count && ok; i++) {
    const plan_row *r = &rows[i];
    unsigned char *data;
    size_t size = 0;
    int64_t id = 0;
    reader_catalog_book book;
    char key[80];
    path_join(file_path, sizeof(file_path), fixtures, r->file);
    data = read_file(file_path, &size);
    if (!data) {
      if (why) snprintf(why, why_size, "cannot read %s", r->file);
      ok = 0;
      break;
    }
    if (exr_library_import(library, format_enum(r->format), data, size, r->sort_title, &id,
                           &error) != EXR_OK) {
      if (why) snprintf(why, why_size, "import %s: %s", r->file, error.message);
      free(data);
      ok = 0;
      break;
    }
    free(data);
    if (ids) ids[i] = id;
    catalog_key(r, key);
    memset(&book, 0, sizeof(book));
    book.format = r->format;
    book.sha256 = strchr(key, ':') + 1;
    book.title = r->sort_title;
    book.author = "";
    book.sort_title = r->sort_title;
    book.location_kind = location_of(r->format);
    book.source_bytes = catalog_bytes(r);
    book.sdk_book_id = id;
    book.favorite = 0;
    if (reader_catalog_attach(catalog, &book, &catalog_error) != 0) {
      if (why) snprintf(why, why_size, "attach %s: %s", r->sort_title, catalog_error.message);
      ok = 0;
      break;
    }
    if (!strcmp(r->action, "cloud")) {
      if (reader_catalog_remove_local(catalog, id, &catalog_error) != 0) {
        if (why) snprintf(why, why_size, "remove_local: %s", catalog_error.message);
        ok = 0;
        break;
      }
    }
    if (!strcmp(r->action, "missing")) {
      if (deleted_count >= MAX_DELETED) {
        if (why) snprintf(why, why_size, "too many missing-source rows");
        ok = 0;
        break;
      }
      deleted[deleted_count++] = id;
    }
  }
  if (ok && extra_file && extra_id) {
    unsigned char *data;
    size_t size = 0;
    char path[1600];
    path_join(path, sizeof(path), fixtures, extra_file);
    data = read_file(path, &size);
    if (!data) ok = 0;
    else {
      if (exr_library_import(library, EXR_EPUB, data, size, "extra", extra_id, &error) != EXR_OK)
        ok = 0;
      free(data);
    }
    if (why && !ok) snprintf(why, why_size, "extra import %s failed", extra_file);
  }
  for (i = 0; i < deleted_count && ok; i++) {
    if (exr_library_delete(library, deleted[i], &error) != EXR_OK) {
      if (why) snprintf(why, why_size, "delete mapped original: %s", error.message);
      ok = 0;
    }
  }
  exr_library_close(library);
  if (reader_catalog_close(&catalog, &catalog_error) != 0) ok = 0;
  return ok;
}

/* ---- delivery sink ---- */
typedef struct {
  char sort_title[64];
  char book_key[80];
  char format[8];
  int64_t sdk_book_id;
  int verdict;
  int sdk_status;
  uint64_t expected_bytes;
  uint64_t retained_bytes;
  uint64_t bytes_read;
  int hashed;
  char expected_sha256[65];
  char observed_sha256[65];
} saved_row;

typedef struct {
  saved_row *rows;
  size_t count;
  size_t capacity;
  const plan_row *plan;
  size_t plan_count;
  int strict;
  int order_ok;
  int identity_ok;
} sink;

static int sink_init(sink *s, size_t capacity, const plan_row *rows, size_t count, int strict) {
  memset(s, 0, sizeof(*s));
  s->rows = (saved_row *)calloc(capacity ? capacity : 1, sizeof(*s->rows));
  if (!s->rows) return 0;
  s->capacity = capacity;
  s->plan = rows;
  s->plan_count = count;
  s->strict = strict;
  s->order_ok = 1;
  s->identity_ok = 1;
  return 1;
}
static void sink_free(sink *s) {
  free(s->rows);
  s->rows = NULL;
  s->count = 0;
  s->capacity = 0;
}
static int sink_visit(void *context, const reader_health_row *row) {
  sink *s = (sink *)context;
  saved_row *dst;
  if (s->count >= s->capacity) return 1;
  dst = &s->rows[s->count];
  memset(dst, 0, sizeof(*dst));
  snprintf(dst->sort_title, sizeof(dst->sort_title), "%s", row->sort_title ? row->sort_title : "");
  snprintf(dst->book_key, sizeof(dst->book_key), "%s", row->book_key ? row->book_key : "");
  snprintf(dst->format, sizeof(dst->format), "%s", row->format ? row->format : "");
  dst->sdk_book_id = row->sdk_book_id;
  dst->verdict = (int)row->verdict;
  dst->sdk_status = (int)row->sdk_status;
  dst->expected_bytes = row->expected_bytes;
  dst->retained_bytes = row->retained_bytes;
  dst->bytes_read = row->bytes_read;
  dst->hashed = row->hashed;
  memcpy(dst->expected_sha256, row->expected_sha256, 65);
  memcpy(dst->observed_sha256, row->observed_sha256, 65);
  if (s->count && strcmp(s->rows[s->count - 1].sort_title, dst->sort_title) >= 0) s->order_ok = 0;
  if (s->strict && s->count < s->plan_count) {
    char key[80];
    catalog_key(&s->plan[s->count], key);
    if (strcmp(dst->book_key, key) != 0) s->identity_ok = 0;
    if (strcmp(dst->sort_title, s->plan[s->count].sort_title) != 0) s->identity_ok = 0;
  }
  s->count++;
  return 0;
}

static int noop_visit(void *context, const reader_health_row *row) {
  (void)context;
  (void)row;
  return 0;
}

typedef struct {
  const sink *sink;
  size_t after;
} cancel_state;
static int cancel_after(void *context) {
  const cancel_state *c = (const cancel_state *)context;
  return c->sink->count >= c->after;
}

typedef struct {
  size_t calls;
  size_t after;
} progress_cancel;
static int progress_cancel_poll(void *context) {
  progress_cancel *p = (progress_cancel *)context;
  return p->calls >= p->after;
}
static void progress_cancel_count(void *context, exr_stage stage, uint64_t completed,
                                  uint64_t total) {
  progress_cancel *p = (progress_cancel *)context;
  (void)stage;
  (void)completed;
  (void)total;
  p->calls++;
}

static int run_steps(reader_health_scanner *scanner, reader_health_cursor *cursor, sink *target,
                     size_t *steps, uint64_t *bytes, reader_health_status *status,
                     reader_health_step_info *last, reader_health_error *error) {
  size_t iterations = 0;
  *steps = 0;
  *bytes = 0;
  memset(last, 0, sizeof(*last));
  for (;;) {
    reader_health_step_info info;
    reader_health_status now = reader_health_step(scanner, cursor, sink_visit, target, &info, error);
    *status = now;
    if (now != READER_HEALTH_OK) return 0;
    (*steps)++;
    *bytes += info.bytes_hashed;
    *last = info;
    if (info.done || info.stopped || info.limit_reached) return 1;
    if (!info.budget_reached && info.rows_delivered == 0) return 0;
    if (++iterations > 100000) return 0;
  }
}

/* ---- JSON output ---- */
static void json_string(FILE *out, const char *text) {
  const unsigned char *p = (const unsigned char *)(text ? text : "");
  fputc('"', out);
  for (; *p; p++) {
    if (*p == '"' || *p == '\\') {
      fputc('\\', out);
      fputc(*p, out);
    } else if (*p < 0x20) fprintf(out, "\\u%04x", (unsigned)*p);
    else fputc(*p, out);
  }
  fputc('"', out);
}

static void write_checks(FILE *out) {
  size_t i;
  fputs("[", out);
  for (i = 0; i < g_check_count; i++) {
    if (i) fputs(",", out);
    fputs("{\"id\":", out);
    json_string(out, g_checks[i].id);
    fprintf(out, ",\"passed\":%s,\"detail\":", g_checks[i].passed ? "true" : "false");
    json_string(out, g_checks[i].detail);
    fputs("}", out);
  }
  fputs("]", out);
}

static void count_verdicts(const sink *s, size_t counts[9]) {
  size_t i;
  memset(counts, 0, sizeof(size_t) * 9);
  for (i = 0; i < s->count; i++)
    if (s->rows[i].verdict >= 1 && s->rows[i].verdict <= 8) counts[s->rows[i].verdict]++;
}

static void write_counts(FILE *out, const sink *s) {
  size_t counts[9];
  int v;
  count_verdicts(s, counts);
  fputs("{", out);
  for (v = 1; v <= 8; v++) {
    if (v > 1) fputs(",", out);
    json_string(out, reader_health_verdict_name((reader_health_verdict)v));
    fprintf(out, ":%llu", (unsigned long long)counts[v]);
  }
  fputs("}", out);
}

static int write_json(const char *path, const char *scenario, const sink *rows, size_t steps,
                      uint64_t bytes, int done, int limit, int stopped, double cpu_ms,
                      const char *extra_stats) {
  FILE *out = fopen(path, "wb");
  size_t i;
  if (!out) return 0;
  fputs("{\"probe\":\"library-health-probe\",\"scenario\":", out);
  json_string(out, scenario);
  fputs(",\"platform\":", out);
  json_string(out, platform_name());
  fputs(",\"checks\":", out);
  write_checks(out);
  if (rows) {
    fputs(",\"rows\":[", out);
    for (i = 0; i < rows->count; i++) {
      const saved_row *r = &rows->rows[i];
      if (i) fputs(",", out);
      fputs("{\"sort_title\":", out);
      json_string(out, r->sort_title);
      fputs(",\"book_key\":", out);
      json_string(out, r->book_key);
      fputs(",\"format\":", out);
      json_string(out, r->format);
      fprintf(out, ",\"sdk_book_id\":%lld,\"verdict\":", (long long)r->sdk_book_id);
      json_string(out, reader_health_verdict_name((reader_health_verdict)r->verdict));
      fprintf(out,
              ",\"sdk_status\":%d,\"expected_bytes\":%llu,\"retained_bytes\":%llu,"
              "\"bytes_read\":%llu,\"hashed\":%s,\"expected_sha256\":",
              r->sdk_status, (unsigned long long)r->expected_bytes,
              (unsigned long long)r->retained_bytes, (unsigned long long)r->bytes_read,
              r->hashed ? "true" : "false");
      json_string(out, r->expected_sha256);
      fputs(",\"observed_sha256\":", out);
      json_string(out, r->observed_sha256);
      fputs("}", out);
    }
    fputs("],\"counts\":", out);
    write_counts(out, rows);
  }
  fprintf(out,
          ",\"stats\":{\"steps\":%llu,\"bytes_hashed\":%llu,\"done\":%s,"
          "\"limit_reached\":%s,\"stopped\":%s,\"cpu_ms\":%.3f%s}}",
          (unsigned long long)steps, (unsigned long long)bytes, done ? "true" : "false",
          limit ? "true" : "false", stopped ? "true" : "false", cpu_ms,
          extra_stats ? extra_stats : "");
  fclose(out);
  return 1;
}

/* ---- the 2202-row catalog scan ---- */
static int scan_main(const char *dir, const plan_file *p, const char *json_path,
                     size_t rows_per_step, size_t buffer_bytes, uint64_t max_book) {
  reader_catalog *catalog = NULL;
  exr_library *library = NULL;
  reader_health_scanner *scanner = NULL;
  reader_health_options options;
  reader_health_cursor cursor;
  reader_health_error error;
  reader_health_step_info last;
  reader_health_status status = READER_HEALTH_OK;
  sink rows;
  size_t steps = 0, expected_steps, i, expected_counts[9], counts[9];
  uint64_t hashed = 0, sum = 0;
  double cpu_ms = 0;
  clock_t started;
  int ok = 1, same = 1, at = 0;
  char detail[256], catalog_path[1024], library_path[1024];
  reader_catalog_error catalog_error;
  memset(&error, 0, sizeof(error));
  memset(&catalog_error, 0, sizeof(catalog_error));
  memset(&last, 0, sizeof(last));
  memset(&rows, 0, sizeof(rows));
  if (!open_pair(dir, &catalog, &library, catalog_path, library_path)) {
    add_check("main_open_pair", 0, "%s", catalog_path);
    return 0;
  }
  add_check("main_open_pair", 1, "opened the built product catalog and SDK library");
  memset(&options, 0, sizeof(options));
  reader_health_options_init(&options);
  options.rows_per_step = rows_per_step;
  options.buffer_bytes = buffer_bytes;
  options.max_book_bytes = max_book;
  if (!sink_init(&rows, p->count + 8, p->rows, p->count, 1)) ok = 0;
  if (ok && reader_health_create(catalog, library, &options, &scanner, &error) != READER_HEALTH_OK)
    ok = 0;
  if (ok) {
    reader_health_cursor_init(&cursor);
    started = clock();
    ok = run_steps(scanner, &cursor, &rows, &steps, &hashed, &status, &last, &error);
    cpu_ms = 1000.0 * (double)(clock() - started) / (double)CLOCKS_PER_SEC;
  }
  add_check("main_rows_delivered", ok && rows.count == p->count, "delivered %llu of %llu rows",
            (unsigned long long)rows.count, (unsigned long long)p->count);
  add_check("main_status_ok", ok && status == READER_HEALTH_OK, "status=%s",
            reader_health_status_name(status));
  add_check("main_done_flag", ok && last.done == 1 && last.limit_reached == 0 && last.stopped == 0,
            "done=%d limit=%d stopped=%d", last.done, last.limit_reached, last.stopped);
  add_check("main_keyset_order", rows.order_ok, "delivered order strictly ascending");
  add_check("main_identity_and_verdicts", rows.identity_ok, "catalog identity per delivered row");
  expected_steps = (p->count + rows_per_step - 1) / rows_per_step;
  add_check("main_step_count", steps == expected_steps, "steps=%llu expected=%llu",
            (unsigned long long)steps, (unsigned long long)expected_steps);
  for (i = 0; i < rows.count; i++) sum += rows.rows[i].bytes_read;
  add_check("main_hashed_bytes_match_rows", sum == hashed, "rows=%llu steps=%llu",
            (unsigned long long)sum, (unsigned long long)hashed);
  count_verdicts(&rows, counts);
  memset(expected_counts, 0, sizeof(expected_counts));
  for (i = 0; i < p->count; i++) expected_counts[(int)expected_verdict(p->rows[i].action)]++;
  detail[0] = 0;
  for (i = 1; i <= 8; i++) {
    if (counts[i] != expected_counts[i]) {
      same = 0;
      if (at < (int)sizeof(detail) - 64)
        at += snprintf(detail + at, sizeof(detail) - (size_t)at, "%s %llu!=%llu ",
                       reader_health_verdict_name((reader_health_verdict)i),
                       (unsigned long long)counts[i], (unsigned long long)expected_counts[i]);
    }
  }
  add_check("main_verdict_distribution", same, "%s", same ? "all verdict counts match" : detail);
  if (ok) {
    reader_health_scanner *second = NULL;
    reader_health_options again;
    reader_health_cursor restart;
    reader_health_status again_status = READER_HEALTH_OK;
    reader_health_step_info again_last;
    sink repeat;
    size_t repeat_steps = 0;
    uint64_t repeat_hashed = 0;
    int repeat_ok = 1;
    memset(&again, 0, sizeof(again));
    memset(&repeat, 0, sizeof(repeat));
    reader_health_options_init(&again);
    again.rows_per_step = 7;
    again.buffer_bytes = READER_HEALTH_MIN_BUFFER_BYTES;
    again.max_book_bytes = max_book;
    if (!sink_init(&repeat, p->count + 8, p->rows, p->count, 1)) repeat_ok = 0;
    if (repeat_ok &&
        reader_health_create(catalog, library, &again, &second, &error) != READER_HEALTH_OK)
      repeat_ok = 0;
    if (repeat_ok) {
      reader_health_cursor_init(&restart);
      repeat_ok = run_steps(second, &restart, &repeat, &repeat_steps, &repeat_hashed,
                            &again_status, &again_last, &error);
      reader_health_destroy(&second, &error);
    }
    add_check("main_repeat_step7",
              repeat_ok && again_status == READER_HEALTH_OK && again_last.done == 1 &&
                  repeat.count == rows.count && rows.count > 0 &&
                  memcmp(rows.rows, repeat.rows, rows.count * sizeof(saved_row)) == 0,
              "rows=%llu/%llu steps=%llu", (unsigned long long)repeat.count,
              (unsigned long long)rows.count, (unsigned long long)repeat_steps);
    sink_free(&repeat);
  } else {
    add_check("main_repeat_step7", 0, "first scan failed");
  }
  if (scanner) reader_health_destroy(&scanner, &error);
  exr_library_close(library);
  reader_catalog_close(&catalog, &catalog_error);
  if (!write_json(json_path, "main", &rows, steps, hashed, last.done, last.limit_reached,
                  last.stopped, cpu_ms, NULL))
    add_check("main_json", 0, "cannot write %s", json_path);
  sink_free(&rows);
  return g_check_failed == 0;
}

/* ---- adversarial scenarios ---- */
#if defined(_WIN32)
struct thread_arg {
  reader_health_scanner *scanner;
  reader_health_status step_status;
  reader_health_status destroy_status;
  size_t delivered;
};
static DWORD WINAPI thread_body(LPVOID raw) {
  struct thread_arg *a = (struct thread_arg *)raw;
  reader_health_cursor cursor;
  reader_health_step_info info;
  reader_health_error error;
  reader_health_scanner *copy;
  sink rows;
  memset(&error, 0, sizeof(error));
  memset(&info, 0, sizeof(info));
  reader_health_cursor_init(&cursor);
  if (!sink_init(&rows, 8, NULL, 0, 0)) return 0;
  a->step_status = reader_health_step(a->scanner, &cursor, sink_visit, &rows, &info, &error);
  a->delivered = rows.count;
  copy = a->scanner;
  a->destroy_status = reader_health_destroy(&copy, &error);
  sink_free(&rows);
  return 0;
}
static int spawn_wrong_thread(struct thread_arg *arg) {
  HANDLE thread = CreateThread(NULL, 0, thread_body, arg, 0, NULL);
  if (!thread) return 0;
  WaitForSingleObject(thread, INFINITE);
  CloseHandle(thread);
  return 1;
}
#else
struct thread_arg {
  reader_health_scanner *scanner;
  reader_health_status step_status;
  reader_health_status destroy_status;
  size_t delivered;
};
static void *thread_body(void *raw) {
  struct thread_arg *a = (struct thread_arg *)raw;
  reader_health_cursor cursor;
  reader_health_step_info info;
  reader_health_error error;
  reader_health_scanner *copy;
  sink rows;
  memset(&error, 0, sizeof(error));
  memset(&info, 0, sizeof(info));
  reader_health_cursor_init(&cursor);
  if (!sink_init(&rows, 8, NULL, 0, 0)) return NULL;
  a->step_status = reader_health_step(a->scanner, &cursor, sink_visit, &rows, &info, &error);
  a->delivered = rows.count;
  copy = a->scanner;
  a->destroy_status = reader_health_destroy(&copy, &error);
  sink_free(&rows);
  return NULL;
}
static int spawn_wrong_thread(struct thread_arg *arg) {
  pthread_t thread;
  if (pthread_create(&thread, NULL, thread_body, arg) != 0) return 0;
  pthread_join(thread, NULL);
  return 1;
}
#endif

typedef struct {
  reader_health_scanner *scanner;
  reader_health_cursor *cursor;
  sink *rows;
  int step_reentry;
  int destroy_reentry;
  int progress_calls;
  int wrong_status;
} reentry_state;

static int reentry_visit(void *context, const reader_health_row *row) {
  reentry_state *state = (reentry_state *)context;
  reader_health_step_info info;
  reader_health_error error;
  reader_health_scanner *copy;
  sink_visit(state->rows, row);
  memset(&error, 0, sizeof(error));
  memset(&info, 0, sizeof(info));
  if (reader_health_step(state->scanner, state->cursor, noop_visit, NULL, &info, &error) ==
      READER_HEALTH_REENTRY)
    state->step_reentry = 1;
  else
    state->wrong_status = 1;
  copy = state->scanner;
  if (reader_health_destroy(&copy, &error) == READER_HEALTH_REENTRY) state->destroy_reentry = 1;
  else state->wrong_status = 1;
  return 0;
}
static void reentry_progress(void *context, exr_stage stage, uint64_t completed, uint64_t total) {
  reentry_state *state = (reentry_state *)context;
  reader_health_step_info info;
  reader_health_error error;
  (void)stage;
  (void)completed;
  (void)total;
  memset(&error, 0, sizeof(error));
  memset(&info, 0, sizeof(info));
  state->progress_calls++;
  if (reader_health_step(state->scanner, state->cursor, noop_visit, NULL, &info, &error) ==
      READER_HEALTH_REENTRY)
    state->step_reentry = 1;
  else state->wrong_status = 1;
}

static int build_slice(const char *dir, const char *fixtures, const plan_file *p, size_t from,
                       size_t count, const char *extra, int64_t *ids, int64_t *extra_id,
                       char *why, size_t why_size) {
  if (from + count > p->count) return 0;
  return build_pair(dir, fixtures, p->rows + from, count, extra, ids, extra_id, why, why_size);
}

static int scenario_cancel(const char *workdir, const char *fixtures, const plan_file *p) {
  char dir[1200], why[256], cp[1024], lp[1024];
  reader_catalog *catalog = NULL;
  exr_library *library = NULL;
  reader_health_scanner *scanner = NULL;
  reader_health_options options;
  reader_health_cursor cursor;
  reader_health_error error;
  reader_health_step_info info;
  reader_health_status status;
  sink rows;
  cancel_state cancel;
  size_t steps = 0;
  uint64_t bytes = 0;
  int ok;
  memset(&error, 0, sizeof(error));
  memset(&info, 0, sizeof(info));
  memset(&rows, 0, sizeof(rows));
  path_join(dir, sizeof(dir), workdir, "cancel");
  ok = build_slice(dir, fixtures, p, 2, 40, NULL, NULL, NULL, why, sizeof(why));
  add_check("cancel_build", ok, "%s", ok ? "40 mapped rows" : why);
  if (!ok) return 0;
  if (!open_pair(dir, &catalog, &library, cp, lp)) {
    add_check("cancel_open", 0, "%s", cp);
    return 0;
  }
  add_check("cancel_open", 1, "opened pair");
  if (!sink_init(&rows, 64, p->rows + 2, 40, 1)) ok = 0;
  memset(&options, 0, sizeof(options));
  reader_health_options_init(&options);
  options.rows_per_step = 8;
  options.buffer_bytes = READER_HEALTH_MIN_BUFFER_BYTES;
  memset(&cancel, 0, sizeof(cancel));
  cancel.sink = &rows;
  cancel.after = 10;
  options.control.cancelled = cancel_after;
  options.control.context = &cancel;
  if (ok && reader_health_create(catalog, library, &options, &scanner, &error) != READER_HEALTH_OK)
    ok = 0;
  if (ok) {
    reader_health_cursor_init(&cursor);
    status = reader_health_step(scanner, &cursor, sink_visit, &rows, &info, &error);
    add_check("cancel_reports_cancelled",
              status == READER_HEALTH_CANCELLED && info.rows_delivered == 10 &&
                  cursor.rows_done == 10 && rows.count == 10,
              "status=%s delivered=%llu cursor=%llu", reader_health_status_name(status),
              (unsigned long long)info.rows_delivered, (unsigned long long)cursor.rows_done);
    add_check("cancel_keeps_delivered_rows_only", rows.identity_ok && rows.order_ok,
              "delivered rows match the first ten catalog rows");
    cancel.after = (size_t)-1;
    ok = run_steps(scanner, &cursor, &rows, &steps, &bytes, &status, &info, &error);
    add_check("cancel_resume_completes",
              ok && status == READER_HEALTH_OK && info.done == 1 && rows.count == 40 &&
                  cursor.rows_done == 40 && rows.identity_ok,
              "rows=%llu cursor=%llu status=%s", (unsigned long long)rows.count,
              (unsigned long long)cursor.rows_done, reader_health_status_name(status));
    reader_health_destroy(&scanner, &error);
  } else {
    add_check("cancel_reports_cancelled", 0, "scanner create failed");
    add_check("cancel_resume_completes", 0, "scanner create failed");
  }
  sink_free(&rows);
  exr_library_close(library);
  reader_catalog_close(&catalog, NULL);
  return g_check_failed == 0;
}

static int scenario_cancel_mid_read(const char *workdir, const char *fixtures, const plan_file *p) {
  char dir[1200], why[256], cp[1024], lp[1024];
  reader_catalog *catalog = NULL;
  exr_library *library = NULL;
  reader_health_scanner *scanner = NULL;
  reader_health_options options;
  reader_health_cursor cursor;
  reader_health_error error;
  reader_health_step_info info;
  reader_health_status status;
  sink rows;
  progress_cancel progress;
  int ok;
  memset(&error, 0, sizeof(error));
  memset(&info, 0, sizeof(info));
  memset(&rows, 0, sizeof(rows));
  memset(&progress, 0, sizeof(progress));
  path_join(dir, sizeof(dir), workdir, "cancel-read");
  ok = build_slice(dir, fixtures, p, 0, 1, NULL, NULL, NULL, why, sizeof(why));
  add_check("cancel_mid_read_build", ok, "%s", ok ? "one 300 KiB row" : why);
  if (!ok) return 0;
  if (!open_pair(dir, &catalog, &library, cp, lp)) {
    add_check("cancel_mid_read_open", 0, "%s", cp);
    return 0;
  }
  if (!sink_init(&rows, 8, p->rows, 1, 1)) ok = 0;
  memset(&options, 0, sizeof(options));
  reader_health_options_init(&options);
  options.rows_per_step = 4;
  options.buffer_bytes = READER_HEALTH_MIN_BUFFER_BYTES;
  progress.after = 2;
  options.control.cancelled = progress_cancel_poll;
  options.control.progress = progress_cancel_count;
  options.control.context = &progress;
  if (ok && reader_health_create(catalog, library, &options, &scanner, &error) != READER_HEALTH_OK)
    ok = 0;
  if (ok) {
    reader_health_cursor_init(&cursor);
    status = reader_health_step(scanner, &cursor, sink_visit, &rows, &info, &error);
    add_check("cancel_mid_read_not_delivered",
              status == READER_HEALTH_CANCELLED && info.rows_delivered == 0 && rows.count == 0 &&
                  cursor.rows_done == 0 && progress.calls == 2,
              "status=%s delivered=%llu rows=%llu chunks=%llu", reader_health_status_name(status),
              (unsigned long long)info.rows_delivered, (unsigned long long)rows.count,
              (unsigned long long)progress.calls);
    reader_health_destroy(&scanner, &error);
    /* Re-run the same row with cancellation disabled. */
    progress.after = (size_t)-1;
    options.control.cancelled = NULL;
    options.control.progress = NULL;
    rows.count = 0;
    rows.order_ok = 1;
    rows.identity_ok = 1;
    if (reader_health_create(catalog, library, &options, &scanner, &error) == READER_HEALTH_OK) {
      reader_health_cursor_init(&cursor);
      status = reader_health_step(scanner, &cursor, sink_visit, &rows, &info, &error);
      reader_health_destroy(&scanner, &error);
      add_check("cancel_mid_read_resume_verified",
                status == READER_HEALTH_OK && rows.count == 1 && info.done == 1 &&
                    rows.rows[0].verdict == (int)READER_HEALTH_VERIFIED &&
                    rows.rows[0].bytes_read == rows.rows[0].expected_bytes &&
                    rows.rows[0].hashed == 1,
                "status=%s rows=%llu bytes=%llu", reader_health_status_name(status),
                (unsigned long long)rows.count, (unsigned long long)rows.rows[0].bytes_read);
    } else {
      add_check("cancel_mid_read_resume_verified", 0, "scanner create failed");
    }
  } else {
    add_check("cancel_mid_read_not_delivered", 0, "scanner create failed");
    add_check("cancel_mid_read_resume_verified", 0, "scanner create failed");
  }
  sink_free(&rows);
  exr_library_close(library);
  reader_catalog_close(&catalog, NULL);
  return g_check_failed == 0;
}

static int scenario_budget(const char *workdir, const char *fixtures, const plan_file *p) {
  char dir[1200], why[256], cp[1024], lp[1024];
  reader_catalog *catalog = NULL;
  exr_library *library = NULL;
  reader_health_scanner *scanner = NULL;
  reader_health_options options;
  reader_health_cursor cursor;
  reader_health_error error;
  reader_health_step_info info;
  reader_health_status status;
  sink rows;
  size_t steps = 0, budget_hits = 0;
  uint64_t bytes = 0;
  int ok, done = 0;
  memset(&error, 0, sizeof(error));
  memset(&info, 0, sizeof(info));
  memset(&rows, 0, sizeof(rows));
  path_join(dir, sizeof(dir), workdir, "budget");
  ok = build_slice(dir, fixtures, p, 2, 40, NULL, NULL, NULL, why, sizeof(why));
  add_check("budget_build", ok, "%s", ok ? "40 mapped rows" : why);
  if (!ok) return 0;
  if (!open_pair(dir, &catalog, &library, cp, lp)) {
    add_check("budget_open", 0, "%s", cp);
    return 0;
  }
  if (!sink_init(&rows, 64, p->rows + 2, 40, 1)) ok = 0;
  memset(&options, 0, sizeof(options));
  reader_health_options_init(&options);
  options.rows_per_step = 40;
  options.buffer_bytes = READER_HEALTH_MIN_BUFFER_BYTES;
  options.max_step_bytes = 4096;
  if (ok && reader_health_create(catalog, library, &options, &scanner, &error) != READER_HEALTH_OK)
    ok = 0;
  if (ok) {
    reader_health_cursor_init(&cursor);
    for (;;) {
      status = reader_health_step(scanner, &cursor, sink_visit, &rows, &info, &error);
      if (status != READER_HEALTH_OK) break;
      steps++;
      bytes += info.bytes_hashed;
      if (info.budget_reached) budget_hits++;
      if (info.done) { done = 1; break; }
      if (info.limit_reached || info.stopped) break;
      if (steps > 1000) break;
    }
    add_check("budget_splits_steps_without_loss",
              status == READER_HEALTH_OK && done == 1 && rows.count == 40 && rows.identity_ok &&
                  budget_hits >= 1 && steps >= 2,
              "status=%s rows=%llu steps=%llu budget=%llu", reader_health_status_name(status),
              (unsigned long long)rows.count, (unsigned long long)steps,
              (unsigned long long)budget_hits);
    reader_health_destroy(&scanner, &error);
  } else {
    add_check("budget_splits_steps_without_loss", 0, "scanner create failed");
  }
  (void)bytes;
  sink_free(&rows);
  exr_library_close(library);
  reader_catalog_close(&catalog, NULL);
  return g_check_failed == 0;
}

static int scenario_limit(const char *workdir, const char *fixtures, const plan_file *p) {
  char dir[1200], why[256], cp[1024], lp[1024];
  reader_catalog *catalog = NULL;
  exr_library *library = NULL;
  reader_health_options options;
  reader_health_cursor cursor;
  reader_health_error error;
  reader_health_step_info info;
  reader_health_status status;
  sink rows;
  reader_health_scanner *first = NULL, *second = NULL;
  size_t steps = 0;
  uint64_t bytes = 0;
  int ok, hit = 0, done = 0;
  memset(&error, 0, sizeof(error));
  memset(&info, 0, sizeof(info));
  memset(&rows, 0, sizeof(rows));
  path_join(dir, sizeof(dir), workdir, "limit");
  ok = build_slice(dir, fixtures, p, 2, 40, NULL, NULL, NULL, why, sizeof(why));
  add_check("limit_build", ok, "%s", ok ? "40 mapped rows" : why);
  if (!ok) return 0;
  if (!open_pair(dir, &catalog, &library, cp, lp)) {
    add_check("limit_open", 0, "%s", cp);
    return 0;
  }
  if (!sink_init(&rows, 64, p->rows + 2, 40, 1)) ok = 0;
  memset(&options, 0, sizeof(options));
  reader_health_options_init(&options);
  options.rows_per_step = 5;
  options.buffer_bytes = READER_HEALTH_MIN_BUFFER_BYTES;
  options.max_total_rows = 12;
  if (ok && reader_health_create(catalog, library, &options, &first, &error) != READER_HEALTH_OK)
    ok = 0;
  if (ok) {
    reader_health_cursor_init(&cursor);
    for (;;) {
      status = reader_health_step(first, &cursor, sink_visit, &rows, &info, &error);
      if (status != READER_HEALTH_OK) break;
      steps++;
      bytes += info.bytes_hashed;
      if (info.done) { done = 1; break; }
      if (info.limit_reached) { hit = 1; break; }
      if (info.stopped || ++steps > 1000) break;
    }
    add_check("limit_stops_at_max",
              status == READER_HEALTH_OK && hit == 1 && done == 0 && rows.count == 12 &&
                  cursor.rows_done == 12,
              "status=%s rows=%llu cursor=%llu hit=%d", reader_health_status_name(status),
              (unsigned long long)rows.count, (unsigned long long)cursor.rows_done, hit);
    reader_health_destroy(&first, &error);
    options.max_total_rows = 40;
    if (reader_health_create(catalog, library, &options, &second, &error) == READER_HEALTH_OK) {
      ok = run_steps(second, &cursor, &rows, &steps, &bytes, &status, &info, &error);
      reader_health_destroy(&second, &error);
      add_check("limit_continues_to_done",
                ok && status == READER_HEALTH_OK && info.done == 1 && rows.count == 40 &&
                    rows.identity_ok && cursor.rows_done == 40,
                "status=%s rows=%llu cursor=%llu", reader_health_status_name(status),
                (unsigned long long)rows.count, (unsigned long long)cursor.rows_done);
    } else {
      add_check("limit_continues_to_done", 0, "second scanner create failed");
    }
  } else {
    add_check("limit_stops_at_max", 0, "scanner create failed");
    add_check("limit_continues_to_done", 0, "scanner create failed");
  }
  sink_free(&rows);
  exr_library_close(library);
  reader_catalog_close(&catalog, NULL);
  return g_check_failed == 0;
}

static int scenario_reentry(const char *workdir, const char *fixtures, const plan_file *p) {
  char dir[1200], why[256], cp[1024], lp[1024];
  reader_catalog *catalog = NULL;
  exr_library *library = NULL;
  reader_health_scanner *scanner = NULL;
  reader_health_options options;
  reader_health_cursor cursor;
  reader_health_error error;
  reader_health_step_info info;
  reader_health_status status;
  sink rows;
  reentry_state state;
  size_t steps = 0;
  uint64_t bytes = 0;
  int ok;
  memset(&error, 0, sizeof(error));
  memset(&info, 0, sizeof(info));
  memset(&rows, 0, sizeof(rows));
  memset(&state, 0, sizeof(state));
  path_join(dir, sizeof(dir), workdir, "reentry");
  ok = build_slice(dir, fixtures, p, 2, 11, NULL, NULL, NULL, why, sizeof(why));
  add_check("reentry_build", ok, "%s", ok ? "11 mapped rows" : why);
  if (!ok) return 0;
  if (!open_pair(dir, &catalog, &library, cp, lp)) {
    add_check("reentry_open", 0, "%s", cp);
    return 0;
  }
  if (!sink_init(&rows, 32, p->rows + 2, 11, 1)) ok = 0;
  memset(&options, 0, sizeof(options));
  reader_health_options_init(&options);
  options.rows_per_step = 8;
  options.buffer_bytes = READER_HEALTH_MIN_BUFFER_BYTES;
  state.rows = &rows;
  state.cursor = &cursor;
  options.control.progress = reentry_progress;
  options.control.context = &state;
  reader_health_cursor_init(&cursor);
  if (ok && reader_health_create(catalog, library, &options, &scanner, &error) != READER_HEALTH_OK)
    ok = 0;
  if (ok) {
    state.scanner = scanner;
    for (;;) {
      status = reader_health_step(scanner, &cursor, reentry_visit, &state, &info, &error);
      if (status != READER_HEALTH_OK) break;
      steps++;
      bytes += info.bytes_hashed;
      if (info.done || info.limit_reached || info.stopped) break;
      if (steps > 1000) break;
    }
    add_check("reentry_is_rejected",
              status == READER_HEALTH_OK && info.done == 1 && rows.count == 11 &&
                  state.step_reentry == 1 && state.destroy_reentry == 1 &&
                  state.progress_calls > 0 && state.wrong_status == 0,
              "status=%s rows=%llu step=%d destroy=%d progress=%d",
              reader_health_status_name(status), (unsigned long long)rows.count,
              state.step_reentry, state.destroy_reentry, state.progress_calls);
    reader_health_destroy(&scanner, &error);
  } else {
    add_check("reentry_is_rejected", 0, "scanner create failed");
  }
  (void)steps;
  (void)bytes;
  sink_free(&rows);
  exr_library_close(library);
  reader_catalog_close(&catalog, NULL);
  return g_check_failed == 0;
}

static int scenario_wrong_thread(const char *workdir, const char *fixtures, const plan_file *p) {
  char dir[1200], why[256], cp[1024], lp[1024];
  reader_catalog *catalog = NULL;
  exr_library *library = NULL;
  reader_health_scanner *scanner = NULL;
  reader_health_options options;
  reader_health_cursor cursor;
  reader_health_error error;
  reader_health_step_info info;
  reader_health_status status;
  sink rows;
  struct thread_arg arg;
  size_t steps = 0;
  uint64_t bytes = 0;
  int ok, spawned;
  memset(&error, 0, sizeof(error));
  memset(&info, 0, sizeof(info));
  memset(&rows, 0, sizeof(rows));
  memset(&arg, 0, sizeof(arg));
  path_join(dir, sizeof(dir), workdir, "thread");
  ok = build_slice(dir, fixtures, p, 2, 40, NULL, NULL, NULL, why, sizeof(why));
  add_check("thread_build", ok, "%s", ok ? "40 mapped rows" : why);
  if (!ok) return 0;
  if (!open_pair(dir, &catalog, &library, cp, lp)) {
    add_check("thread_open", 0, "%s", cp);
    return 0;
  }
  if (!sink_init(&rows, 64, p->rows + 2, 40, 1)) ok = 0;
  memset(&options, 0, sizeof(options));
  reader_health_options_init(&options);
  options.rows_per_step = 8;
  options.buffer_bytes = READER_HEALTH_MIN_BUFFER_BYTES;
  if (ok && reader_health_create(catalog, library, &options, &scanner, &error) != READER_HEALTH_OK)
    ok = 0;
  spawned = 0;
  if (ok) {
    arg.scanner = scanner;
    spawned = spawn_wrong_thread(&arg);
  }
  add_check("wrong_thread_rejected",
            spawned && arg.step_status == READER_HEALTH_THREAD &&
                arg.destroy_status == READER_HEALTH_THREAD && arg.delivered == 0,
            "spawned=%d step=%s destroy=%s delivered=%llu", spawned,
            reader_health_status_name(arg.step_status),
            reader_health_status_name(arg.destroy_status), (unsigned long long)arg.delivered);
  if (ok) {
    reader_health_cursor_init(&cursor);
    ok = run_steps(scanner, &cursor, &rows, &steps, &bytes, &status, &info, &error);
    add_check("wrong_thread_owner_still_scans",
              ok && status == READER_HEALTH_OK && info.done == 1 && rows.count == 40 &&
                  rows.identity_ok,
              "status=%s rows=%llu", reader_health_status_name(status),
              (unsigned long long)rows.count);
    reader_health_destroy(&scanner, &error);
  } else {
    add_check("wrong_thread_owner_still_scans", 0, "scanner create failed");
  }
  sink_free(&rows);
  exr_library_close(library);
  reader_catalog_close(&catalog, NULL);
  return g_check_failed == 0;
}

static int scenario_wrong_catalog(const char *workdir, const char *fixtures, const plan_file *p) {
  char dir_a[1200], dir_b[1200], why[256], cp[1024], lp[1024];
  reader_catalog *catalog_a = NULL, *catalog_b = NULL;
  exr_library *library_a = NULL, *library_b = NULL;
  reader_health_scanner *scanner_a = NULL, *scanner_b = NULL;
  reader_health_options options;
  reader_health_cursor cursor;
  reader_health_error error;
  reader_health_step_info info;
  reader_health_status status;
  sink rows;
  int ok;
  memset(&error, 0, sizeof(error));
  memset(&info, 0, sizeof(info));
  memset(&rows, 0, sizeof(rows));
  path_join(dir_a, sizeof(dir_a), workdir, "cursor-a");
  path_join(dir_b, sizeof(dir_b), workdir, "cursor-b");
  ok = build_slice(dir_a, fixtures, p, 2, 2, NULL, NULL, NULL, why, sizeof(why));
  if (ok) ok = build_slice(dir_b, fixtures, p, 6, 2, NULL, NULL, NULL, why, sizeof(why));
  add_check("wrong_catalog_build", ok, "%s", ok ? "two catalogs" : why);
  if (!ok) return 0;
  memset(&options, 0, sizeof(options));
  reader_health_options_init(&options);
  options.rows_per_step = 1;
  options.buffer_bytes = READER_HEALTH_MIN_BUFFER_BYTES;
  if (!open_pair(dir_a, &catalog_a, &library_a, cp, lp)) {
    add_check("wrong_catalog_open", 0, "%s", cp);
    return 0;
  }
  if (!sink_init(&rows, 8, p->rows + 2, 2, 1)) ok = 0;
  if (ok && reader_health_create(catalog_a, library_a, &options, &scanner_a, &error) == READER_HEALTH_OK) {
    reader_health_cursor_init(&cursor);
    status = reader_health_step(scanner_a, &cursor, sink_visit, &rows, &info, &error);
    ok = status == READER_HEALTH_OK && rows.count == 1;
    reader_health_destroy(&scanner_a, &error);
  } else ok = 0;
  exr_library_close(library_a);
  reader_catalog_close(&catalog_a, NULL);
  if (!ok) {
    add_check("wrong_catalog_cursor_rejected", 0, "first catalog scan failed");
    sink_free(&rows);
    return 0;
  }
  if (!open_pair(dir_b, &catalog_b, &library_b, cp, lp)) {
    add_check("wrong_catalog_cursor_rejected", 0, "%s", cp);
    sink_free(&rows);
    return 0;
  }
  if (reader_health_create(catalog_b, library_b, &options, &scanner_b, &error) == READER_HEALTH_OK) {
    reader_health_step_info other;
    memset(&other, 0, sizeof(other));
    status = reader_health_step(scanner_b, &cursor, sink_visit, &rows, &other, &error);
    add_check("wrong_catalog_cursor_rejected",
              status == READER_HEALTH_ARGUMENT && other.rows_delivered == 0,
              "status=%s delivered=%llu", reader_health_status_name(status),
              (unsigned long long)other.rows_delivered);
    {
      reader_health_cursor fresh;
      reader_health_step_info fresh_info;
      size_t repeat_steps = 0;
      uint64_t repeat_bytes = 0;
      reader_health_cursor_init(&fresh);
      for (;;) {
        status = reader_health_step(scanner_b, &fresh, sink_visit, &rows, &fresh_info, &error);
        if (status != READER_HEALTH_OK) break;
        repeat_steps++;
        repeat_bytes += fresh_info.bytes_hashed;
        if (fresh_info.done || fresh_info.limit_reached || fresh_info.stopped) break;
        if (repeat_steps > 100) break;
      }
      (void)repeat_bytes;
      add_check("wrong_catalog_fresh_cursor_works",
                status == READER_HEALTH_OK && fresh_info.done == 1 && rows.count == 3,
                "status=%s rows=%llu", reader_health_status_name(status),
                (unsigned long long)rows.count);
    }
    reader_health_destroy(&scanner_b, &error);
  } else {
    add_check("wrong_catalog_cursor_rejected", 0, "second scanner create failed");
  }
  sink_free(&rows);
  exr_library_close(library_b);
  reader_catalog_close(&catalog_b, NULL);
  return g_check_failed == 0;
}

typedef struct {
  sink *rows;
  int64_t victim;
  char library_path[1024];
  int deleted;
  int delete_ok;
} change_state;

static int change_visit(void *context, const reader_health_row *row) {
  change_state *c = (change_state *)context;
  sink_visit(c->rows, row);
  if (!c->deleted) {
    exr_library *second = NULL;
    exr_error error;
    memset(&error, 0, sizeof(error));
    c->deleted = 1;
    if (exr_library_open(c->library_path, &second, &error) == EXR_OK) {
      if (exr_library_delete(second, c->victim, &error) == EXR_OK) c->delete_ok = 1;
      exr_library_close(second);
    }
  }
  return 0;
}

static int scenario_change_during_scan(const char *workdir, const char *fixtures,
                                       const plan_file *p) {
  char dir[1200], why[256], cp[1024], lp[1024];
  reader_catalog *catalog = NULL;
  exr_library *library = NULL;
  reader_health_scanner *scanner = NULL;
  reader_health_options options;
  reader_health_cursor cursor;
  reader_health_error error;
  reader_health_step_info info;
  reader_health_status status;
  sink rows;
  change_state state;
  int64_t ids[4];
  int ok;
  memset(&error, 0, sizeof(error));
  memset(&info, 0, sizeof(info));
  memset(&rows, 0, sizeof(rows));
  memset(&state, 0, sizeof(state));
  path_join(dir, sizeof(dir), workdir, "change");
  ok = build_slice(dir, fixtures, p, 42, 2, NULL, ids, NULL, why, sizeof(why));
  add_check("change_build", ok, "%s", ok ? "two mapped rows" : why);
  if (!ok) return 0;
  if (!open_pair(dir, &catalog, &library, cp, lp)) {
    add_check("change_open", 0, "%s", cp);
    return 0;
  }
  if (!sink_init(&rows, 8, p->rows + 42, 2, 0)) ok = 0;
  memset(&options, 0, sizeof(options));
  reader_health_options_init(&options);
  options.rows_per_step = 2;
  options.buffer_bytes = READER_HEALTH_MIN_BUFFER_BYTES;
  if (ok && reader_health_create(catalog, library, &options, &scanner, &error) != READER_HEALTH_OK)
    ok = 0;
  if (ok) {
    state.rows = &rows;
    state.victim = ids[1];
    snprintf(state.library_path, sizeof(state.library_path), "%s", lp);
    reader_health_cursor_init(&cursor);
    for (;;) {
      status = reader_health_step(scanner, &cursor, change_visit, &state, &info, &error);
      if (status != READER_HEALTH_OK) break;
      if (info.done || info.limit_reached || info.stopped) break;
    }
    add_check("change_during_scan_reports_missing_source",
              status == READER_HEALTH_OK && info.done == 1 && state.delete_ok == 1 &&
                  rows.count == 2 && rows.rows[0].verdict == (int)READER_HEALTH_VERIFIED &&
                  rows.rows[1].verdict == (int)READER_HEALTH_MAPPING_MISSING &&
                  rows.rows[1].sdk_status == (int)EXR_ARGUMENT,
              "status=%s rows=%llu delete=%d verdicts=%d/%d", reader_health_status_name(status),
              (unsigned long long)rows.count, state.delete_ok, rows.rows[0].verdict,
              rows.rows[1].verdict);
    reader_health_destroy(&scanner, &error);
  } else {
    add_check("change_during_scan_reports_missing_source", 0, "scanner create failed");
  }
  sink_free(&rows);
  exr_library_close(library);
  reader_catalog_close(&catalog, NULL);
  return g_check_failed == 0;
}

typedef struct {
  int64_t extra_id;
  char library_path[1024];
  int fired;
  int delete_ok;
} invalidate_state;

static void invalidate_progress(void *context, exr_stage stage, uint64_t completed,
                                uint64_t total) {
  invalidate_state *state = (invalidate_state *)context;
  (void)stage;
  (void)completed;
  (void)total;
  if (state->fired) return;
  state->fired = 1;
  {
    exr_library *second = NULL;
    exr_error error;
    memset(&error, 0, sizeof(error));
    if (exr_library_open(state->library_path, &second, &error) == EXR_OK) {
      if (exr_library_delete(second, state->extra_id, &error) == EXR_OK) state->delete_ok = 1;
      exr_library_close(second);
    }
  }
}

static int scenario_invalidate(const char *workdir, const char *fixtures, const plan_file *p) {
  char dir[1200], why[256], cp[1024], lp[1024];
  reader_catalog *catalog = NULL;
  exr_library *library = NULL;
  reader_health_scanner *scanner = NULL;
  reader_health_options options;
  reader_health_cursor cursor;
  reader_health_error error;
  reader_health_step_info info;
  reader_health_status status;
  sink rows;
  invalidate_state state;
  int64_t extra_id = 0;
  int ok;
  memset(&error, 0, sizeof(error));
  memset(&info, 0, sizeof(info));
  memset(&rows, 0, sizeof(rows));
  memset(&state, 0, sizeof(state));
  path_join(dir, sizeof(dir), workdir, "invalidate");
  ok = build_slice(dir, fixtures, p, 0, 2, "adversarial/second.epub", NULL, &extra_id, why,
                   sizeof(why));
  add_check("invalidate_build", ok, "%s", ok ? "two rows plus one hidden original" : why);
  if (!ok) return 0;
  if (!open_pair(dir, &catalog, &library, cp, lp)) {
    add_check("invalidate_open", 0, "%s", cp);
    return 0;
  }
  if (!sink_init(&rows, 8, p->rows, 2, 0)) ok = 0;
  memset(&options, 0, sizeof(options));
  reader_health_options_init(&options);
  options.rows_per_step = 4;
  options.buffer_bytes = READER_HEALTH_MIN_BUFFER_BYTES;
  state.extra_id = extra_id;
  snprintf(state.library_path, sizeof(state.library_path), "%s", lp);
  options.control.progress = invalidate_progress;
  options.control.context = &state;
  if (ok && reader_health_create(catalog, library, &options, &scanner, &error) != READER_HEALTH_OK)
    ok = 0;
  if (ok) {
    reader_health_cursor_init(&cursor);
    status = reader_health_step(scanner, &cursor, sink_visit, &rows, &info, &error);
    add_check("invalidate_mid_read_reports_failure",
              status == READER_HEALTH_OK && info.done == 1 && state.fired == 1 &&
                  state.delete_ok == 1 && rows.count == 2 &&
                  rows.rows[0].verdict == (int)READER_HEALTH_READ_FAILED &&
                  rows.rows[0].hashed == 0 &&
                  rows.rows[0].bytes_read > 0 &&
                  rows.rows[0].bytes_read < rows.rows[0].expected_bytes &&
                  rows.rows[1].verdict == (int)READER_HEALTH_VERIFIED,
              "status=%s rows=%llu fired=%d delete=%d read=%llu/%llu verdicts=%d/%d",
              reader_health_status_name(status), (unsigned long long)rows.count, state.fired,
              state.delete_ok, (unsigned long long)rows.rows[0].bytes_read,
              (unsigned long long)rows.rows[0].expected_bytes, rows.rows[0].verdict,
              rows.rows[1].verdict);
    reader_health_destroy(&scanner, &error);
    /* The same originals are healthy again once the library is stable. */
    options.control.progress = NULL;
    rows.count = 0;
    rows.order_ok = 1;
    if (reader_health_create(catalog, library, &options, &scanner, &error) == READER_HEALTH_OK) {
      reader_health_cursor_init(&cursor);
      status = reader_health_step(scanner, &cursor, sink_visit, &rows, &info, &error);
      reader_health_destroy(&scanner, &error);
      add_check("rescan_after_change_verified",
                status == READER_HEALTH_OK && rows.count == 2 &&
                    rows.rows[0].verdict == (int)READER_HEALTH_VERIFIED &&
                    rows.rows[1].verdict == (int)READER_HEALTH_VERIFIED,
                "status=%s rows=%llu", reader_health_status_name(status),
                (unsigned long long)rows.count);
    } else {
      add_check("rescan_after_change_verified", 0, "scanner create failed");
    }
  } else {
    add_check("invalidate_mid_read_reports_failure", 0, "scanner create failed");
    add_check("rescan_after_change_verified", 0, "scanner create failed");
  }
  sink_free(&rows);
  exr_library_close(library);
  reader_catalog_close(&catalog, NULL);
  return g_check_failed == 0;
}

static int scenario_arguments(const char *workdir, const char *fixtures, const plan_file *p) {
  char dir[1200], why[256], cp[1024], lp[1024];
  reader_catalog *catalog = NULL;
  exr_library *library = NULL;
  reader_health_scanner *scanner = NULL;
  reader_health_options options;
  reader_health_cursor cursor;
  reader_health_error error;
  reader_health_step_info info;
  reader_health_scanner *fresh = NULL;
  int ok = 1, failed = 0;
  char first[128];
  memset(&error, 0, sizeof(error));
  memset(&info, 0, sizeof(info));
  first[0] = 0;
  path_join(dir, sizeof(dir), workdir, "arguments");
  ok = build_slice(dir, fixtures, p, 2, 2, NULL, NULL, NULL, why, sizeof(why));
  add_check("arguments_build", ok, "%s", ok ? "two mapped rows" : why);
  if (!ok) return 0;
  if (!open_pair(dir, &catalog, &library, cp, lp)) {
    add_check("arguments_open", 0, "%s", cp);
    return 0;
  }
  reader_health_options_init(&options);
  if (options.rows_per_step != 32 || options.buffer_bytes != 65536 ||
      options.max_step_bytes != (64ull << 20) || options.max_book_bytes != (512ull << 20) ||
      options.max_total_rows != 100000 || options.struct_size != sizeof(options)) {
    failed = 1;
    snprintf(first, sizeof(first), "defaults differ");
  }
  {
    struct {
      size_t rows;
      size_t buffer;
      uint64_t step;
      uint64_t book;
      uint64_t total;
      size_t struct_size;
      const char *id;
    } bad[10];
    size_t i;
    memset(bad, 0, sizeof(bad));
    reader_health_options_init(&options);
    bad[0].rows = 0; bad[0].buffer = options.buffer_bytes; bad[0].step = options.max_step_bytes;
    bad[0].book = options.max_book_bytes; bad[0].total = options.max_total_rows;
    bad[0].struct_size = sizeof(options); bad[0].id = "rows=0";
    bad[1].rows = 201; bad[1].buffer = options.buffer_bytes; bad[1].step = options.max_step_bytes;
    bad[1].book = options.max_book_bytes; bad[1].total = options.max_total_rows;
    bad[1].struct_size = sizeof(options); bad[1].id = "rows=201";
    bad[2].rows = 8; bad[2].buffer = 4095; bad[2].step = options.max_step_bytes;
    bad[2].book = options.max_book_bytes; bad[2].total = options.max_total_rows;
    bad[2].struct_size = sizeof(options); bad[2].id = "buffer=4095";
    bad[3].rows = 8; bad[3].buffer = 1024 * 1024 + 1; bad[3].step = options.max_step_bytes;
    bad[3].book = options.max_book_bytes; bad[3].total = options.max_total_rows;
    bad[3].struct_size = sizeof(options); bad[3].id = "buffer>max";
    bad[4].rows = 8; bad[4].buffer = options.buffer_bytes; bad[4].step = 0;
    bad[4].book = options.max_book_bytes; bad[4].total = options.max_total_rows;
    bad[4].struct_size = sizeof(options); bad[4].id = "step=0";
    bad[5].rows = 8; bad[5].buffer = options.buffer_bytes; bad[5].step = options.max_step_bytes;
    bad[5].book = 0; bad[5].total = options.max_total_rows;
    bad[5].struct_size = sizeof(options); bad[5].id = "book=0";
    bad[6].rows = 8; bad[6].buffer = options.buffer_bytes; bad[6].step = options.max_step_bytes;
    bad[6].book = options.max_book_bytes; bad[6].total = 0;
    bad[6].struct_size = sizeof(options); bad[6].id = "total=0";
    bad[7].rows = 8; bad[7].buffer = options.buffer_bytes; bad[7].step = options.max_step_bytes;
    bad[7].book = options.max_book_bytes; bad[7].total = options.max_total_rows;
    bad[7].struct_size = sizeof(options) - 8; bad[7].id = "struct_size";
    bad[8].rows = 8; bad[8].buffer = options.buffer_bytes; bad[8].step = (1ull << 30) + 1;
    bad[8].book = options.max_book_bytes; bad[8].total = options.max_total_rows;
    bad[8].struct_size = sizeof(options); bad[8].id = "step>max";
    bad[9].rows = 8; bad[9].buffer = options.buffer_bytes; bad[9].step = options.max_step_bytes;
    bad[9].book = 2147483648ull; bad[9].total = options.max_total_rows;
    bad[9].struct_size = sizeof(options); bad[9].id = "book>max";
    for (i = 0; i < 10; i++) {
      reader_health_options probe;
      reader_health_scanner *out = NULL;
      reader_health_error e;
      memset(&probe, 0, sizeof(probe));
      reader_health_options_init(&probe);
      probe.rows_per_step = bad[i].rows;
      probe.buffer_bytes = bad[i].buffer;
      probe.max_step_bytes = bad[i].step;
      probe.max_book_bytes = bad[i].book;
      probe.max_total_rows = bad[i].total;
      probe.struct_size = bad[i].struct_size;
      memset(&e, 0, sizeof(e));
      if (reader_health_create(catalog, library, &probe, &out, &e) != READER_HEALTH_ARGUMENT ||
          out != NULL) {
        failed = 1;
        if (!first[0]) snprintf(first, sizeof(first), "accepted %s", bad[i].id);
      }
    }
  }
  {
    reader_health_error e;
    reader_health_scanner *out = NULL;
    memset(&e, 0, sizeof(e));
    if (reader_health_create(NULL, library, &options, &out, &e) != READER_HEALTH_ARGUMENT ||
        out != NULL) { failed = 1; if (!first[0]) snprintf(first, sizeof(first), "null catalog"); }
    if (reader_health_create(catalog, NULL, &options, &out, &e) != READER_HEALTH_ARGUMENT ||
        out != NULL) { failed = 1; if (!first[0]) snprintf(first, sizeof(first), "null library"); }
    if (reader_health_create(catalog, library, NULL, &out, &e) != READER_HEALTH_ARGUMENT ||
        out != NULL) { failed = 1; if (!first[0]) snprintf(first, sizeof(first), "null options"); }
    if (reader_health_create(catalog, library, &options, NULL, &e) != READER_HEALTH_ARGUMENT) {
      failed = 1; if (!first[0]) snprintf(first, sizeof(first), "null output");
    }
    if (reader_health_destroy(NULL, &e) != READER_HEALTH_ARGUMENT) {
      failed = 1; if (!first[0]) snprintf(first, sizeof(first), "destroy(null)");
    }
    out = NULL;
    if (reader_health_destroy(&out, &e) != READER_HEALTH_OK) {
      failed = 1; if (!first[0]) snprintf(first, sizeof(first), "destroy(empty)");
    }
  }
  if (reader_health_create(catalog, library, &options, &scanner, &error) != READER_HEALTH_OK) {
    failed = 1;
    if (!first[0]) snprintf(first, sizeof(first), "valid create failed");
  }
  if (scanner) {
    reader_health_step_info info2;
    reader_health_cursor zeroed;
    memset(&zeroed, 0, sizeof(zeroed));
    memset(&info2, 0, sizeof(info2));
    reader_health_cursor_init(&cursor);
    if (reader_health_step(NULL, &cursor, sink_visit, NULL, &info2, &error) !=
        READER_HEALTH_ARGUMENT) { failed = 1; if (!first[0]) snprintf(first, sizeof(first), "step(null scanner)"); }
    if (reader_health_step(scanner, NULL, sink_visit, NULL, &info2, &error) !=
        READER_HEALTH_ARGUMENT) { failed = 1; if (!first[0]) snprintf(first, sizeof(first), "step(null cursor)"); }
    if (reader_health_step(scanner, &cursor, NULL, NULL, &info2, &error) !=
        READER_HEALTH_ARGUMENT) { failed = 1; if (!first[0]) snprintf(first, sizeof(first), "step(null visit)"); }
    if (reader_health_step(scanner, &cursor, sink_visit, NULL, NULL, &error) !=
        READER_HEALTH_ARGUMENT) { failed = 1; if (!first[0]) snprintf(first, sizeof(first), "step(null info)"); }
    if (reader_health_step(scanner, &zeroed, sink_visit, NULL, &info2, &error) !=
        READER_HEALTH_ARGUMENT) { failed = 1; if (!first[0]) snprintf(first, sizeof(first), "uninitialized cursor"); }
    if (reader_health_destroy(&scanner, &error) != READER_HEALTH_OK) {
      failed = 1; if (!first[0]) snprintf(first, sizeof(first), "valid destroy failed");
    }
  }
  add_check("argument_bounds_enforced", failed == 0, "%s", failed ? first : "all refusals hold");
  (void)fresh;
  exr_library_close(library);
  reader_catalog_close(&catalog, NULL);
  return g_check_failed == 0;
}

static int scenario_names(void) {
  int v, i, distinct = 1, known = 1;
  const char *seen[8];
  for (v = 1; v <= 8; v++) {
    const char *name = reader_health_verdict_name((reader_health_verdict)v);
    if (!name || !strcmp(name, "unknown")) known = 0;
    for (i = 0; i < v - 1; i++)
      if (!strcmp(seen[i], name)) distinct = 0;
    seen[v - 1] = name;
  }
  add_check("verdict_names_defined", known && distinct, "eight distinct verdict names");
  distinct = 1;
  known = 1;
  for (v = 0; v <= 7; v++) {
    const char *name = reader_health_status_name((reader_health_status)v);
    if (!name || !strcmp(name, "unknown")) known = 0;
    for (i = 0; i < v; i++)
      if (!strcmp(seen[i], name)) distinct = 0;
    seen[v] = name;
  }
  add_check("status_names_defined", known && distinct, "eight distinct status names");
  return g_check_failed == 0;
}

static int adversarial(const char *workdir, const char *fixtures, const plan_file *p,
                       const char *json_path) {
  if (p->count != 44) {
    add_check("adversarial_plan", 0, "plan has %llu rows", (unsigned long long)p->count);
    write_json(json_path, "adversarial", NULL, 0, 0, 0, 0, 0, 0, NULL);
    return 0;
  }
  add_check("adversarial_plan", 1, "44 prepared rows");
  scenario_names();
  scenario_cancel(workdir, fixtures, p);
  scenario_cancel_mid_read(workdir, fixtures, p);
  scenario_budget(workdir, fixtures, p);
  scenario_limit(workdir, fixtures, p);
  scenario_reentry(workdir, fixtures, p);
  scenario_wrong_thread(workdir, fixtures, p);
  scenario_wrong_catalog(workdir, fixtures, p);
  scenario_change_during_scan(workdir, fixtures, p);
  scenario_invalidate(workdir, fixtures, p);
  scenario_arguments(workdir, fixtures, p);
  if (!write_json(json_path, "adversarial", NULL, 0, 0, 0, 0, 0, 0, NULL))
    add_check("adversarial_json", 0, "cannot write %s", json_path);
  return g_check_failed == 0;
}

/* ---- bounded-memory streaming read ---- */
static uint64_t peak_bytes(void) {
#if defined(_WIN32)
  PROCESS_MEMORY_COUNTERS counters;
  if (GetProcessMemoryInfo(GetCurrentProcess(), &counters, sizeof(counters)))
    return (uint64_t)counters.PeakWorkingSetSize;
  return 0;
#elif defined(__APPLE__)
  struct rusage usage;
  if (getrusage(RUSAGE_SELF, &usage) == 0) return (uint64_t)usage.ru_maxrss;
  return 0;
#else
  struct rusage usage;
  if (getrusage(RUSAGE_SELF, &usage) == 0) return (uint64_t)usage.ru_maxrss * 1024u;
  return 0;
#endif
}

static int memory_scan(const char *workdir, const char *fixture, uint64_t bytes, const char *sha,
                       const char *json_path) {
  char dir[1200], cp[1024], lp[1024], extra[1600];
  reader_catalog *catalog = NULL;
  exr_library *library = NULL;
  reader_catalog_error catalog_error;
  exr_error error;
  reader_catalog_book book;
  reader_health_options options;
  reader_health_cursor cursor;
  reader_health_scanner *scanner = NULL;
  reader_health_error health_error;
  reader_health_step_info info;
  reader_health_status status;
  sink rows;
  int64_t id = 0;
  uint64_t before = 0, after = 0;
  int ok = 1;
  char stats[256];
  memset(&catalog_error, 0, sizeof(catalog_error));
  memset(&error, 0, sizeof(error));
  memset(&health_error, 0, sizeof(health_error));
  memset(&info, 0, sizeof(info));
  memset(&rows, 0, sizeof(rows));
  path_join(dir, sizeof(dir), workdir, "memory");
  if (!open_pair(dir, &catalog, &library, cp, lp)) {
    add_check("memory_open", 0, "%s", cp);
    return 0;
  }
  snprintf(extra, sizeof(extra), "%s", fixture);
  if (exr_library_import_file(library, EXR_EPUB, extra, "LH-MEMORY", &id, &error) != EXR_OK) {
    add_check("memory_import", 0, "%s", error.message);
    ok = 0;
  } else {
    add_check("memory_import", 1, "streaming import of a %llu-byte original",
              (unsigned long long)bytes);
  }
  if (ok) {
    char key[80];
    memset(&book, 0, sizeof(book));
    snprintf(key, sizeof(key), "epub:%s", sha);
    book.format = "epub";
    book.sha256 = strchr(key, ':') + 1;
    book.title = "LH-MEMORY";
    book.author = "";
    book.sort_title = "LH-MEMORY";
    book.location_kind = "epub_chapter";
    book.source_bytes = bytes;
    book.sdk_book_id = id;
    book.favorite = 0;
    if (reader_catalog_attach(catalog, &book, &catalog_error) != 0) {
      add_check("memory_attach", 0, "%s", catalog_error.message);
      ok = 0;
    } else add_check("memory_attach", 1, "catalog identity recorded");
  }
  exr_library_close(library);
  reader_catalog_close(&catalog, &catalog_error);
  if (ok && open_pair(dir, &catalog, &library, cp, lp)) {
    if (!sink_init(&rows, 8, NULL, 0, 0)) ok = 0;
    memset(&options, 0, sizeof(options));
    reader_health_options_init(&options);
    options.rows_per_step = 4;
    options.buffer_bytes = READER_HEALTH_MIN_BUFFER_BYTES;
    before = peak_bytes();
    if (ok && reader_health_create(catalog, library, &options, &scanner, &health_error) ==
                  READER_HEALTH_OK) {
      reader_health_cursor_init(&cursor);
      status = reader_health_step(scanner, &cursor, sink_visit, &rows, &info, &health_error);
      reader_health_destroy(&scanner, &health_error);
      after = peak_bytes();
      add_check("memory_bounded_read",
                status == READER_HEALTH_OK && rows.count == 1 && info.done == 1 &&
                    rows.rows[0].verdict == (int)READER_HEALTH_VERIFIED &&
                    rows.rows[0].bytes_read == bytes && rows.rows[0].hashed == 1,
                "status=%s rows=%llu read=%llu/%llu", reader_health_status_name(status),
                (unsigned long long)rows.count, (unsigned long long)rows.rows[0].bytes_read,
                (unsigned long long)bytes);
      add_check("memory_peak_growth_bounded",
                after >= before && after - before <= (uint64_t)MEMORY_PEAK_BUDGET,
                "growth=%llu budget=%llu", (unsigned long long)(after - before),
                (unsigned long long)MEMORY_PEAK_BUDGET);
    } else {
      add_check("memory_bounded_read", 0, "scanner create failed");
      add_check("memory_peak_growth_bounded", 0, "scanner create failed");
    }
    sink_free(&rows);
    exr_library_close(library);
    reader_catalog_close(&catalog, &catalog_error);
  } else {
    add_check("memory_bounded_read", 0, "reopen failed");
    add_check("memory_peak_growth_bounded", 0, "reopen failed");
  }
  snprintf(stats, sizeof(stats), ",\"bytes\":%llu,\"peak_before\":%llu,\"peak_after\":%llu",
           (unsigned long long)bytes, (unsigned long long)before, (unsigned long long)after);
  if (!write_json(json_path, "memory", NULL, 0, 0, 0, 0, 0, 0, stats))
    add_check("memory_json", 0, "cannot write %s", json_path);
  return g_check_failed == 0;
}

int main(int argc, char **argv) {
  static plan_file plan;
  if (argc >= 2 && !strcmp(argv[1], "build")) {
    char why[256];
    if (argc != 5) return 2;
    if (!read_plan(argv[4], &plan)) {
      fprintf(stderr, "cannot read plan %s\n", argv[4]);
      return 1;
    }
    if (!build_pair(argv[2], argv[3], plan.rows, plan.count, NULL, NULL, NULL, why, sizeof(why))) {
      fprintf(stderr, "build failed: %s\n", why);
      return 1;
    }
    printf("{\"built\":%llu}\n", (unsigned long long)plan.count);
    return 0;
  }
  if (argc >= 2 && !strcmp(argv[1], "scan")) {
    if (argc != 9) return 2;
    if (!read_plan(argv[4], &plan)) return 1;
    return scan_main(argv[2], &plan, argv[5], (size_t)strtoul(argv[6], NULL, 10),
                     (size_t)strtoul(argv[7], NULL, 10),
                     (uint64_t)strtoull(argv[8], NULL, 10))
               ? 0
               : 1;
  }
  if (argc >= 2 && !strcmp(argv[1], "adversarial")) {
    if (argc != 6) return 2;
    if (!read_plan(argv[4], &plan)) return 1;
    return adversarial(argv[2], argv[3], &plan, argv[5]) ? 0 : 1;
  }
  if (argc >= 2 && !strcmp(argv[1], "memory")) {
    if (argc != 7) return 2;
    return memory_scan(argv[2], argv[3], (uint64_t)strtoull(argv[4], NULL, 10), argv[5], argv[6])
               ? 0
               : 1;
  }
  fprintf(stderr, "usage: %s build|scan|adversarial|memory ...\n", argv[0]);
  return 2;
}
