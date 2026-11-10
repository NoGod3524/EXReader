/* SPDX-License-Identifier: MIT */
/* Oversized-book stress probe on the public SDK only (Windows).
   Mirrors the Windows reader host's bounded EPUB path (examples/reader.c
   bounded_pager): workspace 8 MiB, window 64 KiB, page cache 2 / 32 MiB,
   checkpoints 8 / 4 MiB / every 8 pages, get-mode pages, RGBA render.
   Search mirrors apps/reader/search scan_epub: per-part bounded pager plus
   exr_pager_read_text, first batch of 32 hits (HOST_SEARCH_BATCH).

   usage: large_book_probe count   <book.epub> <font>
          large_book_probe measure <book.epub> <font> <count.json-pages-file>
   count prints per-part page counts (one per line after "parts") and an RSS curve. */
#include "exreader.h"
#include <windows.h>
#include <psapi.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static LARGE_INTEGER freq;
static double now_ms(void) { LARGE_INTEGER t; QueryPerformanceCounter(&t); return (double)t.QuadPart * 1000.0 / (double)freq.QuadPart; }
typedef struct { double ws, peak_ws, private_bytes, peak_private; } mem;
static mem memory(void) {
  PROCESS_MEMORY_COUNTERS_EX c; mem m = {0};
  c.cb = sizeof(c);
  if (GetProcessMemoryInfo(GetCurrentProcess(), (PROCESS_MEMORY_COUNTERS *)&c, sizeof(c))) {
    m.ws = c.WorkingSetSize / 1048576.0; m.peak_ws = c.PeakWorkingSetSize / 1048576.0;
    m.private_bytes = c.PrivateUsage / 1048576.0; m.peak_private = c.PeakPagefileUsage / 1048576.0;
  }
  return m;
}
static void die(const char *what, exr_status s, const exr_error *e) {
  fprintf(stderr, "%s failed: %d %s\n", what, (int)s, e ? e->message : ""); exit(2);
}
#define CHECK(what, call) do { exr_status s_ = (call); if (s_ != EXR_OK) die(what, s_, &error); } while (0)

static exr_font *font;
static exr_layout_config config;
static exr_error error;

static exr_status bounded_pager(exr_publication *p, size_t part, exr_pager **out) {
  exr_chapter_options options = exr_chapter_options_defaults();
  exr_status status;
  options.workspace_budget = 8 * 1024 * 1024; options.window_bytes = 64 * 1024;
  status = exr_publication_pager_create(p, part, font, &config, &options, out, &error);
  if (status == EXR_OK) status = exr_pager_set_cache(*out, 2, 32 * 1024 * 1024, &error);
  if (status == EXR_OK) status = exr_pager_set_checkpoints(*out, 8, 4 * 1024 * 1024, 8, &error);
  if (status != EXR_OK) { exr_pager_free(*out); *out = NULL; }
  return status;
}
static int is_eof(exr_status s) { return s == EXR_ARGUMENT && !strcmp(error.message, "Page index is outside the document"); }
static void render(const exr_layout *layout) {
  exr_bitmap bitmap = {0};
  CHECK("render", exr_render_page_color(layout, exr_layout_font(layout), 0, &bitmap, &error));
  exr_bitmap_free(&bitmap);
}
static exr_publication *open_book(const char *path, double *ms) {
  exr_publication *p = NULL; double t = now_ms();
  CHECK("publication_open", exr_publication_open(path, &p, &error));
  *ms = now_ms() - t; return p;
}
static void setup(const char *font_path) {
  QueryPerformanceFrequency(&freq);
  if (exr_font_open(font_path, &font, &error) != EXR_OK) die("font_open", EXR_IO, &error);
  config = exr_layout_config_defaults();
  config.page.width = 720; config.page.height = 1040; config.page.margin = 36;
  config.page.font_size = 28; config.page.line_height = 1.5f; config.page.paragraph_spacing = 10;
  config.document_css = 1; config.embedded_fonts = 1; config.direction = 0;
}

static int count_mode(const char *book) {
  double open_ms, t0 = now_ms(); size_t parts = 0, total = 0, i;
  exr_publication *p = open_book(book, &open_ms);
  const exr_part *list = exr_publication_parts(p, &parts);
  size_t *pages = calloc(parts ? parts : 1, sizeof(size_t)); double *part_ms = calloc(parts ? parts : 1, sizeof(double));
  printf("{\"mode\":\"count\",\"open_ms\":%.3f,\"part_count\":%zu,\"curve\":[\n", open_ms, parts);
  size_t next_mark = 0; int first = 1;
  size_t start = getenv("LB_START_PART") ? (size_t)atoi(getenv("LB_START_PART")) : 0;
  for (i = start; i < parts; i++) {
    exr_pager *pager = NULL; size_t n; double pt = now_ms();
    if (!list[i].in_reading_order) continue;
    CHECK("pager", bounded_pager(p, i, &pager));
    for (n = 0;; n++) {
      const exr_layout *layout; exr_status s = exr_pager_get(pager, n, &layout, &error);
      if (is_eof(s)) break;
      if (s != EXR_OK) die("pager_get", s, &error);
      if (total + n >= next_mark) {
        mem m = memory();
        printf("%s{\"page\":%zu,\"ms\":%.1f,\"ws_mb\":%.2f,\"private_mb\":%.2f}", first ? "" : ",\n",
               total + n, now_ms() - t0, m.ws, m.private_bytes);
        first = 0; next_mark += 500;
      }
    }
    exr_pager_free(pager); pages[i] = n; total += n; part_ms[i] = now_ms() - pt;
  }
  mem m = memory();
  printf("],\n\"total_pages\":%zu,\"elapsed_ms\":%.1f,\"end_ws_mb\":%.2f,\"peak_ws_mb\":%.2f,\"end_private_mb\":%.2f,\"peak_private_mb\":%.2f,\n\"parts\":[",
         total, now_ms() - t0, m.ws, m.peak_ws, m.private_bytes, m.peak_private);
  for (i = 0; i < parts; i++) printf("%s%zu", i ? "," : "", pages[i]);
  printf("],\n\"part_ms\":[");
  for (i = 0; i < parts; i++) printf("%s%.1f", i ? "," : "", part_ms[i]);
  printf("]}\n");
  exr_publication_free(p); free(pages); free(part_ms); return 0;
}

static size_t parts_n, *part_pages, total_pages;
static void read_pages(const char *path) {
  FILE *f = fopen(path, "rb"); size_t cap = 4096, v; part_pages = malloc(cap * sizeof(size_t));
  if (!f) { perror(path); exit(2); }
  while (fscanf(f, "%zu", &v) == 1) {
    if (parts_n == cap) part_pages = realloc(part_pages, (cap *= 2) * sizeof(size_t));
    part_pages[parts_n++] = v; total_pages += v;
  }
  fclose(f);
}
static void locate_global(size_t g, size_t *part, size_t *local) {
  size_t i; for (i = 0; i < parts_n; i++) { if (g < part_pages[i]) { *part = i; *local = g; return; } g -= part_pages[i]; }
  *part = parts_n - 1; *local = part_pages[parts_n - 1] - 1;
}
static int cmp_double(const void *a, const void *b) { double x = *(const double *)a, y = *(const double *)b; return x < y ? -1 : x > y; }
static double pct(double *v, size_t n, double q) {
  /* nearest-rank percentile */
  size_t rank = (size_t)(q * n + 0.999999); if (rank < 1) rank = 1; if (rank > n) rank = n; return v[rank - 1];
}

typedef struct { const unsigned char *q; size_t qn, at, found, cap; unsigned char tail[64]; size_t tail_n; } scan;
static exr_status sink(void *context, const char *utf8, size_t size, exr_error *e) {
  scan *s = context; size_t i; (void)e;
  /* Overlap previous chunk tail so matches across 32 KiB chunk boundaries are kept. */
  unsigned char buf[64 + 32768 + 1]; size_t n = 0;
  if (size > 32768) size = 32768;
  memcpy(buf, s->tail, s->tail_n); n = s->tail_n; memcpy(buf + n, utf8, size); n += size;
  for (i = 0; i + s->qn <= n; i++) if (!memcmp(buf + i, s->q, s->qn)) {
    if (i + s->qn > s->tail_n) { s->found++; if (s->found >= s->cap) return EXR_CANCELLED; }
  }
  s->tail_n = s->qn > 1 ? (n < s->qn - 1 ? n : s->qn - 1) : 0;
  memcpy(s->tail, buf + n - s->tail_n, s->tail_n);
  s->at += size; return EXR_OK;
}
static void search_first_batch(exr_publication *p, const char *needle, size_t batch, double *ms, size_t *parts_scanned, size_t *hits) {
  size_t count = 0, i; const exr_part *parts = exr_publication_parts(p, &count); scan s = {0}; double t = now_ms();
  s.q = (const unsigned char *)needle; s.qn = strlen(needle); s.cap = batch; *parts_scanned = 0;
  for (i = 0; i < count && s.found < batch; i++) {
    exr_pager *pager = NULL; exr_status st;
    if (!parts[i].in_reading_order) continue;
    CHECK("search pager", bounded_pager(p, i, &pager));
    s.tail_n = 0; (*parts_scanned)++;
    st = exr_pager_read_text(pager, 0, exr_pager_chapter_statistics(pager).projection_bytes, sink, &s, NULL, &error);
    if (st != EXR_OK && s.found < batch) die("read_text", st, &error);
    exr_pager_free(pager);
  }
  *ms = now_ms() - t; *hits = s.found;
}
static int sdk_hits, sdk_cap;
static int sdk_cb(void *c, const exr_search_result *r) { (void)c; (void)r; return ++sdk_hits < sdk_cap; }

static int measure_mode(const char *book, const char *pages_file, const char *needle) {
  double open1, open2, t, first_screen, toc_ms, jump_ms, turn[20], jump[20], sorted[20];
  exr_publication *p; exr_pager *pager = NULL; const exr_layout *layout; size_t i;
  read_pages(pages_file);
  mem m0 = memory();
  p = open_book(book, &open1); exr_publication_free(p);
  p = open_book(book, &open2);
  /* First screen: open completed -> first page laid out and rendered. */
  t = now_ms();
  { size_t parts = 0, first = 0; const exr_part *list = exr_publication_parts(p, &parts);
    while (first < parts && !list[first].in_reading_order) first++;
    CHECK("pager", bounded_pager(p, first, &pager));
    CHECK("get", exr_pager_get(pager, 0, &layout, &error)); render(layout); }
  first_screen = now_ms() - t;
  exr_pager_free(pager); pager = NULL;
  mem m_open = memory();
  /* 20 deterministic sample pages spread over the whole book (stratified + LCG jitter). */
  unsigned long long seed = 20261109ULL;
  for (i = 0; i < 20; i++) {
    size_t g, part, local; double t1;
    seed = seed * 6364136223846793005ULL + 1442695040888963407ULL;
    g = (total_pages - 1) * i / 20 + (size_t)((seed >> 33) % ((total_pages - 1) / 20 ? (total_pages - 1) / 20 : 1));
    if (g >= total_pages - 1) g = total_pages - 2;
    locate_global(g, &part, &local);
    t1 = now_ms();  /* jump: reopen the target chapter and lay out to the target page */
    CHECK("pager", bounded_pager(p, part, &pager));
    CHECK("get", exr_pager_get(pager, local, &layout, &error)); render(layout);
    jump[i] = now_ms() - t1;
    t1 = now_ms();  /* turn: next page, crossing into the next chapter when needed */
    if (local + 1 < part_pages[part]) { CHECK("get", exr_pager_get(pager, local + 1, &layout, &error)); }
    else {
      exr_pager_free(pager); pager = NULL; part++;
      while (part < parts_n && !part_pages[part]) part++;
      CHECK("pager", bounded_pager(p, part, &pager)); CHECK("get", exr_pager_get(pager, 0, &layout, &error));
    }
    render(layout); turn[i] = now_ms() - t1;
    exr_pager_free(pager); pager = NULL;
  }
  mem m_turn = memory();
  /* TOC: lazy load (includes body recovery) then jump to the last entry's page. */
  const exr_toc_entry *toc = NULL; size_t toc_n = 0; exr_location where = {0}; size_t target_page = 0;
  t = now_ms(); CHECK("toc", exr_publication_toc(p, &toc, &toc_n, &error)); toc_ms = now_ms() - t;
  if (!toc_n) { fprintf(stderr, "empty toc\n"); return 2; }
  t = now_ms();
  CHECK("locate", exr_publication_locate(p, &toc[toc_n - 1].target, &where, &error));
  CHECK("pager", bounded_pager(p, where.part, &pager));
  for (target_page = 0;; target_page++) {
    size_t n = 0; const exr_page *pg;
    exr_status s = exr_pager_get(pager, target_page, &layout, &error);
    if (is_eof(s)) { target_page--; CHECK("get", exr_pager_get(pager, target_page, &layout, &error)); break; }
    if (s != EXR_OK) die("get", s, &error);
    pg = exr_layout_pages(layout, &n);
    if (n && pg[n - 1].end > where.offset) break;
  }
  render(layout); jump_ms = now_ms() - t;
  exr_pager_free(pager); pager = NULL;
  mem m_toc = memory();
  /* Search: reader path (bounded pager text stream), first batch of 32. */
  double search_ms, sdk_ms; size_t scanned, hits;
  search_first_batch(p, needle, 32, &search_ms, &scanned, &hits);
  mem m_search = memory();
  sdk_hits = 0; sdk_cap = 32; t = now_ms();
  { size_t c = 0; exr_status s = exr_publication_search_all(p, needle, 0, sdk_cb, NULL, NULL, &c, &error); if (s != EXR_OK) die("search_all", s, &error); }
  sdk_ms = now_ms() - t;
  /* Complete SDK search (counts every hit): exposes publication-level text retention. */
  double full_ms; size_t full_hits = 0;
  t = now_ms();
  { exr_status s = exr_publication_search_all(p, needle, 0, NULL, NULL, NULL, &full_hits, &error); if (s != EXR_OK) die("search_all full", s, &error); }
  full_ms = now_ms() - t;
  mem m_end = memory();
  memcpy(sorted, turn, sizeof(turn)); qsort(sorted, 20, sizeof(double), cmp_double);
  printf("{\"mode\":\"measure\",\"total_pages\":%zu,\"parts\":%zu,\"open_first_ms\":%.3f,\"open_second_ms\":%.3f,"
         "\"first_screen_ms\":%.3f,\"turn_p50_ms\":%.3f,\"turn_p95_ms\":%.3f,\"turn_max_ms\":%.3f,",
         total_pages, parts_n, open1, open2, first_screen, pct(sorted, 20, .5), pct(sorted, 20, .95), sorted[19]);
  memcpy(sorted, jump, sizeof(jump)); qsort(sorted, 20, sizeof(double), cmp_double);
  printf("\"jump_p50_ms\":%.3f,\"jump_p95_ms\":%.3f,\"turn_ms\":[", pct(sorted, 20, .5), pct(sorted, 20, .95));
  for (i = 0; i < 20; i++) printf("%s%.3f", i ? "," : "", turn[i]);
  printf("],\"jump_ms\":[");
  for (i = 0; i < 20; i++) printf("%s%.3f", i ? "," : "", jump[i]);
  printf("],\"toc_entries\":%zu,\"toc_load_ms\":%.3f,\"toc_last_jump_ms\":%.3f,\"toc_last_part\":%zu,\"toc_last_page\":%zu,"
         "\"search_needle_bytes\":%zu,\"search_first32_ms\":%.3f,\"search_parts_scanned\":%zu,\"search_hits\":%zu,\"sdk_search_first32_ms\":%.3f,\"sdk_search_full_ms\":%.3f,\"sdk_search_full_hits\":%zu,"
         "\"mem_mb\":{\"start_ws\":%.2f,\"after_open_ws\":%.2f,\"after_turn_ws\":%.2f,\"after_toc_ws\":%.2f,\"after_search_ws\":%.2f,\"end_ws\":%.2f,"
         "\"peak_ws\":%.2f,\"end_private\":%.2f,\"peak_private\":%.2f}}\n",
         toc_n, toc_ms, jump_ms, where.part, target_page, strlen(needle), search_ms, scanned, hits, sdk_ms, full_ms, full_hits,
         m0.ws, m_open.ws, m_turn.ws, m_toc.ws, m_search.ws, m_end.ws, m_end.peak_ws, m_end.private_bytes, m_end.peak_private);
  exr_publication_free(p); return 0;
}

int main(int argc, char **argv) {
  if (argc >= 4 && !strcmp(argv[1], "count")) { setup(argv[3]); return count_mode(argv[2]); }
  if (argc >= 5 && !strcmp(argv[1], "measure")) { setup(argv[3]); return measure_mode(argv[2], argv[4], argc > 5 ? argv[5] : "\xe4\xb9\x8b"); }
  fprintf(stderr, "usage: %s count|measure book font [pages.txt [needle]]\n", argv[0]); return 1;
}
