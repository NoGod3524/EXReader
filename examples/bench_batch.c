/* SPDX-License-Identifier: MIT */
/* EXR_BENCH_BASELINE preserves the timed path for SDKs predating telemetry. */
#ifndef _WIN32
#define _POSIX_C_SOURCE 200809L
#endif
#include <exreader.h>
#include <errno.h>
#include <inttypes.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
#else
#include <time.h>
#endif

typedef struct {
  uint64_t glyph_requests, glyph_hits, glyph_misses;
  uint64_t shaping_requests, shaping_hits, shaping_misses;
  uint64_t glyph_evictions, shaping_evictions, shaping_bypasses;
  uint64_t layout_requests, layout_hits, layout_misses;
} counters;
typedef struct { size_t part, page; double layout_ms, render_ms, total_ms; counters cache; } sample;
typedef struct { sample *samples; double setup_ms, warmup_ms, part_setup_ms, p50, p95; counters cache; } batch;

static double now_ms(void) {
#ifdef _WIN32
  LARGE_INTEGER tick;
  static LARGE_INTEGER frequency;
  if (!frequency.QuadPart) QueryPerformanceFrequency(&frequency);
  QueryPerformanceCounter(&tick);
  return 1000.0 * (double)tick.QuadPart / (double)frequency.QuadPart;
#else
  struct timespec tick;
  if (clock_gettime(CLOCK_MONOTONIC, &tick)) { perror("clock_gettime"); exit(1); }
  return 1000.0 * (double)tick.tv_sec + (double)tick.tv_nsec / 1000000.0;
#endif
}
static int number(const char *text, size_t maximum, size_t *out) {
  char *end; unsigned long long n;
  if (!text[0] || text[0] == '-' || text[0] == '+') return 0;
  errno = 0; n = strtoull(text, &end, 10);
  if (errno || *end || n > maximum) return 0;
  *out = (size_t)n; return 1;
}
static int real_number(const char *text, float *out) {
  char *end; double n;
  errno = 0; n = strtod(text, &end);
  if (errno || end == text || *end || !isfinite(n) || n < 0 || n > 100000) return 0;
  *out = (float)n; return 1;
}
static int compare_double(const void *a, const void *b) {
  double x = *(const double *)a, y = *(const double *)b;
  return (x > y) - (x < y);
}
static double percentile(double *sorted, size_t count, unsigned percent) {
  return sorted[(count * percent + 99) / 100 - 1];
}
static void add_counters(counters *a, const counters *b) {
#define ADD(field) a->field += b->field
  ADD(glyph_requests); ADD(glyph_hits); ADD(glyph_misses);
  ADD(shaping_requests); ADD(shaping_hits); ADD(shaping_misses);
  ADD(glyph_evictions); ADD(shaping_evictions); ADD(shaping_bypasses);
  ADD(layout_requests); ADD(layout_hits); ADD(layout_misses);
#undef ADD
}
static counters difference(const counters *a, const counters *b) {
  counters c;
#define SUB(field) c.field = a->field - b->field
  SUB(glyph_requests); SUB(glyph_hits); SUB(glyph_misses);
  SUB(shaping_requests); SUB(shaping_hits); SUB(shaping_misses);
  SUB(glyph_evictions); SUB(shaping_evictions); SUB(shaping_bypasses);
  SUB(layout_requests); SUB(layout_hits); SUB(layout_misses);
#undef SUB
  return c;
}
static exr_status read_counters(exr_font *font, exr_pager *pager, counters *out, exr_error *error) {
  memset(out, 0, sizeof(*out));
#ifndef EXR_BENCH_BASELINE
  exr_font_cache_stats f = {0}; exr_pager_cache_stats p = {0}; exr_status status;
  f.struct_size = sizeof(f); p.struct_size = sizeof(p);
  if (font) { status = exr_font_cache_stats_get(font, &f, error); if (status != EXR_OK) return status; }
  if (pager) { status = exr_pager_cache_stats_get(pager, &p, error); if (status != EXR_OK) return status; }
#define COPY(field) out->field = f.field
  COPY(glyph_requests); COPY(glyph_hits); COPY(glyph_misses);
  COPY(shaping_requests); COPY(shaping_hits); COPY(shaping_misses);
  COPY(glyph_evictions); COPY(shaping_evictions); COPY(shaping_bypasses);
#undef COPY
  out->layout_requests = p.requests; out->layout_hits = p.hits; out->layout_misses = p.misses;
#else
  (void)font; (void)pager; (void)error;
#endif
  return EXR_OK;
}
static exr_status run_batch(const char *book, const char *font_path, const exr_layout_config *config,
    size_t turns, size_t warmup, batch *result, exr_error *error) {
  exr_publication *publication = NULL; exr_document *document = NULL;
  exr_font *font = NULL, *active_font = NULL; exr_pager *pager = NULL;
  exr_layout *page = NULL; exr_bitmap bitmap = {0}; exr_status status;
  size_t parts = 0, part, count = 0;
  const exr_part *directory;
  double started = now_ms();
  status = exr_font_open(font_path, &font, error);
  if (status == EXR_OK) status = exr_publication_open(book, &publication, error);
  if (status != EXR_OK) goto done;
  directory = exr_publication_parts(publication, &parts);
  result->setup_ms = now_ms() - started;
#ifndef EXR_BENCH_BASELINE
  if (warmup) {
    started = now_ms();
    status = exr_publication_warmup(publication, font, config, warmup, error);
    result->warmup_ms = now_ms() - started;
    if (status != EXR_OK) goto done;
  }
#else
  (void)warmup;
#endif
  for (part = 0; part < parts && count <= turns; part++) {
    size_t index = 0;
    if (!directory[part].in_reading_order) continue;
    started = now_ms();
    status = exr_publication_load(publication, part, &document, error);
    if (status == EXR_OK) status = exr_pager_create(document, font, config, &pager, error);
    result->part_setup_ms += now_ms() - started;
    if (status != EXR_OK) goto done;
    active_font = font;
    while (count <= turns) {
      counters before, after;
      double layout_end, rendered;
      sample *s = &result->samples[count];
      status = read_counters(active_font, pager, &before, error);
      if (status != EXR_OK) goto done;
      started = now_ms();
      status = exr_pager_next(pager, &page, error);
      layout_end = now_ms();
      if (status != EXR_OK || !page) break;
      status = exr_render_page_color(page, exr_layout_font(page), 0, &bitmap, error);
      rendered = now_ms();
      if (status != EXR_OK) goto done;
      if (active_font != exr_layout_font(page)) {
        /* Embedded fonts create a new effective set with fresh counters. */
        memset(&before, 0, sizeof(before));
      }
      active_font = exr_layout_font(page);
      status = read_counters(active_font, pager, &after, error);
      if (status != EXR_OK) goto done;
      s->part = part; s->page = index++;
      s->layout_ms = layout_end - started; s->render_ms = rendered - layout_end; s->total_ms = rendered - started;
      s->cache = difference(&after, &before);
      if (count) add_counters(&result->cache, &s->cache);
      count++;
      exr_bitmap_free(&bitmap); exr_layout_free(page); page = NULL;
    }
    if (status != EXR_OK) goto done;
    exr_pager_free(pager); pager = NULL; active_font = NULL;
    exr_document_free(document); document = NULL;
  }
  if (count != turns + 1) {
    status = EXR_ARGUMENT;
    snprintf(error->message, sizeof(error->message), "Book has only %zu pages; need one first page plus %zu turns", count, turns);
  } else {
    double *sorted = malloc(turns * sizeof(*sorted)); size_t i;
    if (!sorted) { status = EXR_MEMORY; goto done; }
    for (i = 0; i < turns; i++) sorted[i] = result->samples[i + 1].total_ms;
    qsort(sorted, turns, sizeof(*sorted), compare_double);
    result->p50 = percentile(sorted, turns, 50); result->p95 = percentile(sorted, turns, 95);
    free(sorted);
  }
done:
  exr_bitmap_free(&bitmap); exr_layout_free(page); exr_pager_free(pager);
  exr_document_free(document); exr_publication_free(publication); exr_font_free(font);
  return status;
}
#ifndef EXR_BENCH_BASELINE
static double hit_rate(uint64_t hits, uint64_t requests) { return requests ? 100.0 * (double)hits / (double)requests : 0; }
#endif
static void json_string(FILE *f, const char *text) {
  const unsigned char *p = (const unsigned char *)text;
  fputc('"', f);
  for (; *p; p++) {
    if (*p == '"' || *p == '\\') fprintf(f, "\\%c", *p);
    else if (*p < 32) fprintf(f, "\\u%04x", (unsigned)*p);
    else fputc(*p, f);
  }
  fputc('"', f);
}
static void json_cache(FILE *f, const counters *c) {
#ifdef EXR_BENCH_BASELINE
  (void)c; fputs("null", f);
#else
  fprintf(f, "{\"glyph\":{\"requests\":%" PRIu64 ",\"hits\":%" PRIu64 ",\"misses\":%" PRIu64 ",\"hit_percent\":%.6f,\"evictions\":%" PRIu64 "},"
      "\"shaping\":{\"requests\":%" PRIu64 ",\"hits\":%" PRIu64 ",\"misses\":%" PRIu64 ",\"hit_percent\":%.6f,\"evictions\":%" PRIu64 ",\"bypasses\":%" PRIu64 "},"
      "\"layout\":{\"requests\":%" PRIu64 ",\"hits\":%" PRIu64 ",\"misses\":%" PRIu64 ",\"hit_percent\":%.6f}}",
      c->glyph_requests, c->glyph_hits, c->glyph_misses, hit_rate(c->glyph_hits, c->glyph_requests), c->glyph_evictions,
      c->shaping_requests, c->shaping_hits, c->shaping_misses, hit_rate(c->shaping_hits, c->shaping_requests), c->shaping_evictions, c->shaping_bypasses,
      c->layout_requests, c->layout_hits, c->layout_misses, hit_rate(c->layout_hits, c->layout_requests));
#endif
}
static void json_sample(FILE *f, const sample *s) {
  fprintf(f, "{\"part\":%zu,\"page\":%zu,\"layout_ms\":%.6f,\"render_ms\":%.6f,\"total_ms\":%.6f,\"cache\":",
      s->part, s->page, s->layout_ms, s->render_ms, s->total_ms);
  json_cache(f, &s->cache); fputc('}', f);
}
static FILE *output_file(const char *path) {
#ifdef _WIN32
  int n = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, path, -1, NULL, 0);
  wchar_t *wide; FILE *f;
  if (!n || !(wide = malloc((size_t)n * sizeof(*wide)))) return NULL;
  if (!MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, path, -1, wide, n)) { free(wide); return NULL; }
  f = _wfopen(wide, L"wb"); free(wide); return f;
#else
  return fopen(path, "wb");
#endif
}
static void usage(void) {
  fputs("usage: bench_batch BOOK FONT [--runs 5] [--turns 20] [--warmup 0]\n"
      "       [--width 1552] [--height 928] [--margin 48] [--font-size 24]\n"
      "       [--line-height 1.5] [--paragraph-spacing 10] [--json FILE|-]\n"
      "       [--cpu N] [--high-priority]\n"
      "Publication formats: EPUB, MOBI/KF8, FB2. Each run opens fresh objects.\n"
      "Times synchronous pager_next + RGBA rendering; setup is reported separately.\n"
      "First page is reported separately, followed by every consecutive turn.\n"
      "No sleep, retries, discarded runs, threads, or prepared bitmap queue.\n"
      "Scheduling flags are explicit Windows process-local controls.\n", stderr);
}
static int example_main(int argc, char **argv) {
  exr_layout_config config = exr_layout_config_defaults(); exr_error error = {0};
  size_t runs = 5, turns = 20, warmup = 0, cpu = SIZE_MAX, r, i;
  int arg, high = 0, result = 1; const char *json_path = NULL;
  batch *batches = NULL; FILE *json = NULL;
  double minimum, maximum, mean = 0, dispersion;
  config.page = (exr_layout_options){1552, 928, 48, 24, 1.5f, 10};
  if (argc == 2 && !strcmp(argv[1], "--self-test")) {
    double values[] = {20, 1, 4, 3, 2}; size_t n;
    qsort(values, 5, sizeof(*values), compare_double);
    if (percentile(values, 5, 50) != 3 || percentile(values, 5, 95) != 20 ||
        number("-1", 10, &n) || number("11", 10, &n) || !number("10", 10, &n)) return 1;
    puts("bench_batch self-test passed"); return 0;
  }
  if (argc < 3) { usage(); return 2; }
  for (arg = 3; arg < argc; arg++) {
    const char *name = argv[arg], *value;
    if (!strcmp(name, "--high-priority")) { high = 1; continue; }
    if (++arg == argc) { usage(); return 2; }
    value = argv[arg];
    if (!strcmp(name, "--json")) json_path = value;
    else if (!strcmp(name, "--runs")) { if (!number(value, 100, &runs) || !runs) return 2; }
    else if (!strcmp(name, "--turns")) { if (!number(value, 10000, &turns) || !turns) return 2; }
    else if (!strcmp(name, "--warmup")) { if (!number(value, 100000, &warmup)) return 2; }
    else if (!strcmp(name, "--cpu")) { if (!number(value, 63, &cpu)) return 2; }
    else {
      float *field = !strcmp(name, "--width") ? &config.page.width : !strcmp(name, "--height") ? &config.page.height :
        !strcmp(name, "--margin") ? &config.page.margin : !strcmp(name, "--font-size") ? &config.page.font_size :
        !strcmp(name, "--line-height") ? &config.page.line_height : !strcmp(name, "--paragraph-spacing") ? &config.page.paragraph_spacing : NULL;
      if (!field || !real_number(value, field)) { usage(); return 2; }
    }
  }
#ifdef EXR_BENCH_BASELINE
  if (warmup) { fputs("This baseline SDK has no warmup API.\n", stderr); return 2; }
#endif
#ifdef _WIN32
  if ((cpu != SIZE_MAX && (cpu >= sizeof(DWORD_PTR) * 8 || !SetProcessAffinityMask(GetCurrentProcess(), (DWORD_PTR)1 << cpu))) ||
      (high && !SetPriorityClass(GetCurrentProcess(), HIGH_PRIORITY_CLASS))) {
    fprintf(stderr, "Cannot apply requested scheduling controls: %lu\n", (unsigned long)GetLastError()); return 1;
  }
#else
  if (cpu != SIZE_MAX || high) { fputs("Scheduling flags require Windows; use taskset/nice externally.\n", stderr); return 2; }
#endif
  batches = calloc(runs, sizeof(*batches)); if (!batches) return 1;
  for (r = 0; r < runs; r++) {
    batches[r].samples = calloc(turns + 1, sizeof(sample)); if (!batches[r].samples) goto done;
    if (run_batch(argv[1], argv[2], &config, turns, warmup, &batches[r], &error) != EXR_OK) {
      fprintf(stderr, "run %zu: %s\n", r + 1, error.message); goto done;
    }
    mean += batches[r].p95;
  }
  mean /= (double)runs; minimum = maximum = batches[0].p95;
  for (r = 1; r < runs; r++) {
    if (batches[r].p95 < minimum) minimum = batches[r].p95;
    if (batches[r].p95 > maximum) maximum = batches[r].p95;
  }
  dispersion = mean ? 100.0 * (maximum - minimum) / mean : 0;
  if (!json_path || strcmp(json_path, "-")) {
    printf("EXReader %s; %zu runs x %zu turns; warmup %zu pages; nearest-rank percentiles\n", exr_version(), runs, turns, warmup);
    for (r = 0; r < runs; r++) {
      batch *b = &batches[r];
      printf("run %zu: first %.6f ms; warmup %.6f ms; p50 %.6f ms; p95 %.6f ms\nsequence_ms:", r + 1, b->samples[0].total_ms, b->warmup_ms, b->p50, b->p95);
      for (i = 1; i <= turns; i++) printf("%s%.6f", i == 1 ? " " : ",", b->samples[i].total_ms);
#ifndef EXR_BENCH_BASELINE
      printf("\ncache hits: glyph %.4f%% (%" PRIu64 "/%" PRIu64 "); shaping %.4f%% (%" PRIu64 "/%" PRIu64 "); layout %.4f%% (%" PRIu64 "/%" PRIu64 ")\n",
          hit_rate(b->cache.glyph_hits, b->cache.glyph_requests), b->cache.glyph_hits, b->cache.glyph_requests,
          hit_rate(b->cache.shaping_hits, b->cache.shaping_requests), b->cache.shaping_hits, b->cache.shaping_requests,
          hit_rate(b->cache.layout_hits, b->cache.layout_requests), b->cache.layout_hits, b->cache.layout_requests);
#else
      puts("\ncache telemetry: unavailable in baseline SDK");
#endif
    }
    printf("p95 range/mean dispersion: %.6f%%; all p95 <=16ms: %s; dispersion <10%%: %s\n", dispersion, maximum <= 16 ? "yes" : "no", dispersion < 10 ? "yes" : "no");
  }
  if (json_path) {
    json = !strcmp(json_path, "-") ? stdout : output_file(json_path);
    if (!json) { perror(json_path); goto done; }
    fputs("{\"schema_version\":1,\"sdk_version\":", json); json_string(json, exr_version());
    fputs(",\"book\":", json); json_string(json, argv[1]); fputs(",\"font\":", json); json_string(json, argv[2]);
    fprintf(json, ",\"contract\":\"synchronous pager_next + RGBA render; first page separate; part setup excluded\","
        "\"percentile\":\"nearest rank\",\"runs\":%zu,\"turns\":%zu,\"warmup_pages\":%zu,\"width\":%.9g,\"height\":%.9g,"
        "\"margin\":%.9g,\"font_size\":%.9g,\"line_height\":%.9g,\"paragraph_spacing\":%.9g,\"cpu\":",
        runs, turns, warmup, (double)config.page.width, (double)config.page.height, (double)config.page.margin,
        (double)config.page.font_size, (double)config.page.line_height, (double)config.page.paragraph_spacing);
    if (cpu == SIZE_MAX) fputs("null", json); else fprintf(json, "%zu", cpu);
    fprintf(json, ",\"high_priority\":%s,\"batches\":[", high ? "true" : "false");
    for (r = 0; r < runs; r++) {
      batch *b = &batches[r];
      fprintf(json, "%s{\"run\":%zu,\"setup_ms\":%.6f,\"warmup_ms\":%.6f,\"part_setup_ms\":%.6f,\"p50_ms\":%.6f,\"p95_ms\":%.6f,\"first_page\":",
          r ? "," : "", r + 1, b->setup_ms, b->warmup_ms, b->part_setup_ms, b->p50, b->p95);
      json_sample(json, &b->samples[0]); fputs(",\"samples\":[", json);
      for (i = 1; i <= turns; i++) { if (i > 1) fputc(',', json); json_sample(json, &b->samples[i]); }
      fputs("],\"cache\":", json); json_cache(json, &b->cache); fputc('}', json);
    }
    fprintf(json, "],\"p95_min_ms\":%.6f,\"p95_max_ms\":%.6f,\"p95_mean_ms\":%.6f,\"p95_range_over_mean_percent\":%.6f,\"passes\":%s}\n",
        minimum, maximum, mean, dispersion, runs >= 5 && turns >= 20 && maximum <= 16 && dispersion < 10 ? "true" : "false");
    if (ferror(json)) goto done;
    if (json != stdout) { int close_status = fclose(json); json = NULL; if (close_status) goto done; }
  }
  result = 0;
done:
  if (json && json != stdout) fclose(json);
  for (r = 0; r < runs; r++) free(batches[r].samples);
  free(batches); return result;
}
#include "entry.h"
