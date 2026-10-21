/* SPDX-License-Identifier: MIT */
#if !defined(_WIN32) && !defined(_POSIX_C_SOURCE)
#define _POSIX_C_SOURCE 200809L
#endif
/* WP6 bounded-chapter probe.  Separates the chapter parse workspace from the
   book bytes, the publication index, the page cache and an explicit snapshot,
   then measures first-screen and per-turn cost for one chapter.  The sequential
   pass records a hash per page (0.01 px quantization, the existing tolerance).
   The fixed random plan then asks for those pages in a seeded order through a
   one-page cache with bounded checkpoints, so eviction and restore are real,
   and compares every hash with the sequential reference. */
#include "exreader.h"
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifdef _WIN32
#include <windows.h>
#include <psapi.h>
#else
#include <time.h>
#endif

#define MIB ((size_t)1024 * 1024)

typedef struct {
  const char *book, *font;
  size_t part, turns, random_pages, max_pages, cache_pages, cache_bytes;
  size_t checkpoint_capacity, checkpoint_bytes, checkpoint_interval;
  size_t window_bytes;
  unsigned long long seed;
  int render;
} options;

static double now_ms(void) {
#ifdef _WIN32
  LARGE_INTEGER t, f;
  QueryPerformanceCounter(&t);
  QueryPerformanceFrequency(&f);
  return (double)t.QuadPart * 1000.0 / (double)f.QuadPart;
#else
  struct timespec t;
  clock_gettime(CLOCK_MONOTONIC, &t);
  return (double)t.tv_sec * 1000.0 + (double)t.tv_nsec / 1e6;
#endif
}

/* Resident and high-water working set; zero when the platform cannot report it. */
static void process_memory(size_t *resident, size_t *peak) {
  *resident = *peak = 0;
#ifdef _WIN32
  PROCESS_MEMORY_COUNTERS m;
  if (GetProcessMemoryInfo(GetCurrentProcess(), &m, sizeof(m))) {
    *resident = (size_t)m.WorkingSetSize;
    *peak = (size_t)m.PeakWorkingSetSize;
  }
#else
  FILE *f = fopen("/proc/self/status", "r");
  char line[256];
  if (!f) return;
  while (fgets(line, sizeof(line), f)) {
    unsigned long long value;
    if (sscanf(line, "VmRSS: %llu kB", &value) == 1) *resident = (size_t)value * 1024;
    else if (sscanf(line, "VmHWM: %llu kB", &value) == 1) *peak = (size_t)value * 1024;
  }
  fclose(f);
#endif
}

static size_t file_bytes(const char *path) {
  FILE *f = fopen(path, "rb");
  long size;
  if (!f) return 0;
  if (fseek(f, 0, SEEK_END)) { fclose(f); return 0; }
  size = ftell(f);
  fclose(f);
  return size > 0 ? (size_t)size : 0;
}

static uint64_t fnv(uint64_t h, const void *data, size_t size) {
  const unsigned char *p = data;
  size_t i;
  for (i = 0; i < size; i++) {
    h ^= p[i];
    h *= 1099511628211ULL;
  }
  return h;
}
static uint64_t fnv_u64(uint64_t h, uint64_t value) { return fnv(h, &value, sizeof(value)); }
static uint64_t fnv_scale(uint64_t h, double value) {
  long long q = (long long)llround(value * 100.0);
  return fnv_u64(h, (uint64_t)q);
}

typedef struct {
  uint64_t hash;
  size_t lines, glyphs, boxes, start, end;
} page_sample;

static page_sample hash_layout(const exr_layout *layout) {
  page_sample s;
  const exr_page *pages;
  const exr_line *lines;
  const exr_glyph *glyphs;
  const exr_box *boxes;
  size_t count = 0, i;
  memset(&s, 0, sizeof(s));
  s.hash = 1469598103934665603ULL;
  pages = exr_layout_pages(layout, &count);
  if (!pages || !count) return s;
  s.start = pages[0].start;
  s.end = pages[0].end;
  for (i = 0; i < count; i++) {
    s.hash = fnv_u64(s.hash, pages[i].start);
    s.hash = fnv_u64(s.hash, pages[i].end);
    s.hash = fnv_u64(s.hash, pages[i].line_count);
    s.hash = fnv_u64(s.hash, pages[i].box_count);
  }
  lines = exr_layout_lines(layout, &s.lines);
  for (i = 0; i < s.lines; i++) {
    s.hash = fnv_u64(s.hash, lines[i].start);
    s.hash = fnv_u64(s.hash, lines[i].end);
    s.hash = fnv_u64(s.hash, lines[i].glyph_start);
    s.hash = fnv_u64(s.hash, lines[i].glyph_count);
    s.hash = fnv_scale(s.hash, lines[i].x);
    s.hash = fnv_scale(s.hash, lines[i].y);
    s.hash = fnv_scale(s.hash, lines[i].width);
    s.hash = fnv_scale(s.hash, lines[i].height);
  }
  glyphs = exr_layout_glyphs(layout, &s.glyphs);
  for (i = 0; i < s.glyphs; i++) {
    s.hash = fnv_u64(s.hash, glyphs[i].start);
    s.hash = fnv_u64(s.hash, glyphs[i].end);
    s.hash = fnv_u64(s.hash, glyphs[i].codepoint);
    s.hash = fnv_u64(s.hash, glyphs[i].glyph);
    s.hash = fnv_u64(s.hash, glyphs[i].node);
    s.hash = fnv_u64(s.hash, glyphs[i].font_index);
    s.hash = fnv_u64(s.hash, glyphs[i].color);
    s.hash = fnv_u64(s.hash, glyphs[i].flags);
    s.hash = fnv_u64(s.hash, glyphs[i].cluster_start);
    s.hash = fnv_u64(s.hash, glyphs[i].cluster_end);
    s.hash = fnv_u64(s.hash, glyphs[i].boundaries);
    s.hash = fnv_u64(s.hash, glyphs[i].bidi_level);
    s.hash = fnv_scale(s.hash, glyphs[i].x);
    s.hash = fnv_scale(s.hash, glyphs[i].baseline);
    s.hash = fnv_scale(s.hash, glyphs[i].advance);
    s.hash = fnv_scale(s.hash, glyphs[i].size);
  }
  boxes = exr_layout_boxes(layout, &s.boxes);
  for (i = 0; i < s.boxes; i++) {
    s.hash = fnv_u64(s.hash, (uint64_t)boxes[i].kind);
    s.hash = fnv_u64(s.hash, boxes[i].node);
    s.hash = fnv_u64(s.hash, boxes[i].page);
    s.hash = fnv_u64(s.hash, boxes[i].start);
    s.hash = fnv_u64(s.hash, boxes[i].end);
    s.hash = fnv_u64(s.hash, boxes[i].flags);
    s.hash = fnv_u64(s.hash, boxes[i].background);
    s.hash = fnv_u64(s.hash, boxes[i].border_color);
    s.hash = fnv_scale(s.hash, boxes[i].x);
    s.hash = fnv_scale(s.hash, boxes[i].y);
    s.hash = fnv_scale(s.hash, boxes[i].width);
    s.hash = fnv_scale(s.hash, boxes[i].height);
    s.hash = fnv_scale(s.hash, boxes[i].border_width);
  }
  return s;
}

/* Deterministic LCG: the fixed random plan is part of the evidence record. */
static unsigned long long lcg(unsigned long long *state) {
  *state = *state * 6364136223846793005ULL + 1442695040888963407ULL;
  return *state >> 17;
}

static void print_page(FILE *out, int first, size_t page, const page_sample *s) {
  fprintf(out, "%s{\"page\":%zu,\"hash\":\"%016llx\",\"start\":%zu,\"end\":%zu,"
          "\"lines\":%zu,\"glyphs\":%zu,\"boxes\":%zu}",
          first ? "" : ",", page, (unsigned long long)s->hash, s->start, s->end,
          s->lines, s->glyphs, s->boxes);
}

/* JSON string body: no quotes and forward slashes, so a Windows path or an engine
   message keeps the record parseable without a general escaper. */
static const char *json_text(const char *text, char *buffer, size_t size) {
  size_t i = 0;
  if (!text) return "";
  for (; *text && i + 1 < size; text++) {
    char c = *text;
    buffer[i++] = (c == '"' || c == '\\') ? '/' : c;
  }
  buffer[i] = 0;
  return buffer;
}

static int parse(options *o, int argc, char **argv) {
  int i;
  memset(o, 0, sizeof(*o));
  o->part = 0;
  o->turns = 16;
  o->random_pages = 8;
  o->max_pages = 64;
  o->cache_pages = 1;
  o->cache_bytes = 2 * MIB;
  o->checkpoint_capacity = 4;
  o->checkpoint_bytes = 2 * MIB;
  o->checkpoint_interval = 16;
  o->seed = 20261020ULL;
  if (argc < 3) return 0;
  o->book = argv[1];
  o->font = argv[2];
  for (i = 3; i < argc; i++) {
    const char *k = argv[i], *v;
    if (!strcmp(k, "--render")) { o->render = 1; continue; }
    if (i + 1 >= argc) return 0;
    v = argv[++i];
    if (!strcmp(k, "--part")) o->part = (size_t)strtoull(v, NULL, 10);
    else if (!strcmp(k, "--turns")) o->turns = (size_t)strtoull(v, NULL, 10);
    else if (!strcmp(k, "--random")) o->random_pages = (size_t)strtoull(v, NULL, 10);
    else if (!strcmp(k, "--max-pages")) o->max_pages = (size_t)strtoull(v, NULL, 10);
    else if (!strcmp(k, "--cache")) o->cache_pages = (size_t)strtoull(v, NULL, 10);
    else if (!strcmp(k, "--budget")) o->cache_bytes = (size_t)strtoull(v, NULL, 10);
    else if (!strcmp(k, "--checkpoints")) o->checkpoint_capacity = (size_t)strtoull(v, NULL, 10);
    else if (!strcmp(k, "--checkpoint-budget")) o->checkpoint_bytes = (size_t)strtoull(v, NULL, 10);
    else if (!strcmp(k, "--checkpoint-interval")) o->checkpoint_interval = (size_t)strtoull(v, NULL, 10);
    else if (!strcmp(k, "--window-bytes")) o->window_bytes = (size_t)strtoull(v, NULL, 10);
    else if (!strcmp(k, "--seed")) o->seed = strtoull(v, NULL, 10);
    else return 0;
  }
  return o->max_pages > 0 && o->turns <= o->max_pages && o->turns<=64 && o->random_pages<=64;
}

static int run(options *o) {
  exr_font *font = NULL;
  exr_publication *publication = NULL;
  exr_document *document = NULL;
  exr_pager *pager = NULL;
  exr_layout *page = NULL;
  exr_bitmap bitmap = {0};
  exr_error error = {0};
  exr_layout_config config = exr_layout_config_defaults();
  exr_chapter_options chapter_options=exr_chapter_options_defaults();
  exr_chapter_stats chapter_stats={0};
  exr_status status = EXR_OK;
  const char *stage = "font";
  size_t resident = 0, peak = 0, base_resident = 0, baseline_peak = 0;
  size_t font_resident = 0, font_peak = 0, index_resident = 0, index_peak = 0;
  size_t load_resident = 0, load_peak = 0, first_resident = 0, first_peak = 0;
  size_t parts = 0, text_bytes = 0, nodes = 0, blocks = 0;
  size_t owned = 0, node_text = 0, node_names = 0, attribute_text = 0, attribute_arrays = 0;
  size_t attributes = 0;
  size_t chapters = 0, resources = 0, chapter_strings = 0, resource_strings = 0;
  size_t cache_bytes = 0, restored = 0, generated = 0, enumerated = 0, turns = 0;
  double font_ms=0, open_ms=0, load_ms=0, create_ms = 0, first_page_ms = 0, paint_ms = 0;
  double turn_layout[64]={0}, turn_render[64]={0};
  uint64_t all_pages_hash=1469598103934665603ULL;
  int reached_eof=0;
  page_sample reference[256];
  size_t reference_count = 0, random_total = 0, mismatches = 0;
  long long random_plan[64];
  unsigned long long random_state;
  size_t i, j;
  process_memory(&base_resident, &baseline_peak);
  config.page = (exr_layout_options){720, 1040, 36, 28, 1.5f, 10};
  font_ms = now_ms();
  status = exr_font_open(o->font, &font, &error);
  font_ms = now_ms() - font_ms;
  process_memory(&font_resident, &font_peak);
  if (status != EXR_OK) goto done;
  stage = "open";
  open_ms = now_ms();
  status = exr_publication_open(o->book, &publication, &error);
  open_ms = now_ms() - open_ms;
  process_memory(&index_resident, &index_peak);
  if (status != EXR_OK) goto done;
  (void)exr_publication_parts(publication, &parts);
  if (o->part >= parts) { status = EXR_ARGUMENT; goto done; }
  stage = "load";
  load_ms = now_ms();
  chapter_options.window_bytes=o->window_bytes ? o->window_bytes : chapter_options.window_bytes;
  if(o->window_bytes)
    status=exr_publication_pager_create(publication,o->part,font,&config,&chapter_options,&pager,&error);
  else status = exr_publication_load(publication, o->part, &document, &error);
  load_ms = now_ms() - load_ms;
  process_memory(&load_resident, &load_peak);
  if (status != EXR_OK) goto done;
  if(document) {
    const exr_node *node_list = exr_document_nodes(document, &nodes);
    const exr_chapter *chapter_list = exr_document_chapters(document, &chapters);
    const exr_resource *resource_list = exr_document_resources(document, &resources);
    (void)exr_document_blocks(document, &blocks);
    (void)exr_document_text(document, &text_bytes);
    owned = exr_document_memory_size(document);
    for (i = 0; i < nodes; i++) {
      size_t a;
      attributes += node_list[i].attribute_count;
      if (node_list[i].name) node_names += strlen(node_list[i].name) + 1;
      if (node_list[i].text) node_text += strlen(node_list[i].text) + 1;
      for (a = 0; a < node_list[i].attribute_count; a++) {
        if (node_list[i].attributes[a].name)
          attribute_text += strlen(node_list[i].attributes[a].name) + 1;
        if (node_list[i].attributes[a].value)
          attribute_text += strlen(node_list[i].attributes[a].value) + 1;
      }
    }
    attribute_arrays = attributes * sizeof(exr_attribute);
    for (i = 0; i < chapters; i++) {
      if (chapter_list[i].id) chapter_strings += strlen(chapter_list[i].id) + 1;
      if (chapter_list[i].path) chapter_strings += strlen(chapter_list[i].path) + 1;
    }
    for (i = 0; i < resources; i++) {
      if (resource_list[i].id) resource_strings += strlen(resource_list[i].id) + 1;
      if (resource_list[i].path) resource_strings += strlen(resource_list[i].path) + 1;
      if (resource_list[i].media_type) resource_strings += strlen(resource_list[i].media_type) + 1;
      if (resource_list[i].properties) resource_strings += strlen(resource_list[i].properties) + 1;
    }
  }
  if(o->window_bytes) {
    chapter_stats=exr_pager_chapter_statistics(pager);
    nodes=chapter_stats.node_count;text_bytes=chapter_stats.projection_bytes;
    owned=chapter_stats.parse_workspace_bytes;
  }
  stage = "sequential";
  create_ms = now_ms();
  if(!o->window_bytes) status = exr_pager_create(document, font, &config, &pager, &error);
  create_ms = now_ms() - create_ms;
  if (status != EXR_OK) goto done;
  for (;;) {
    double at = now_ms();
    size_t index = enumerated;
    status = exr_pager_next(pager, &page, &error);
    if (status != EXR_OK) goto done;
    if (!page) { reached_eof=1;break; }
    {
      page_sample s = hash_layout(page);
      all_pages_hash=fnv_u64(all_pages_hash,s.hash);
      double render_ms = 0;
      if (index < o->turns) {
        turn_layout[index] = now_ms() - at;
        turns++;
      }
      if (index < 256) reference[index] = s;
      if (index < 256) reference_count++;
      if (o->render && ((index < o->turns) || index == 0)) {
        double started = now_ms();
        exr_status render = exr_render_page_color(page, exr_layout_font(page), 0, &bitmap, &error);
        render_ms = now_ms() - started;
        if (render != EXR_OK) { status = render; goto done; }
        exr_bitmap_free(&bitmap);
      }
      if (index < o->turns) turn_render[index] = render_ms;
      if (index == 0) { first_page_ms = now_ms()-at-render_ms; paint_ms = render_ms; }
    }
    exr_layout_free(page);
    page = NULL;
    enumerated++;
    if (enumerated >= o->max_pages) break;
  }
  process_memory(&first_resident, &first_peak);
  if(o->window_bytes) chapter_stats=exr_pager_chapter_statistics(pager);
  exr_pager_free(pager);
  pager = NULL;
  stage = "random";
  if (reference_count > 1 && o->random_pages) {
    size_t wanted = o->random_pages < reference_count ? o->random_pages : reference_count;
    random_state = o->seed;
    while (random_total < wanted) {
      size_t candidate = (size_t)(lcg(&random_state) % reference_count);
      int seen = 0;
      for (i = 0; i < random_total; i++)
        if ((size_t)random_plan[i] == candidate) { seen = 1; break; }
      if (!seen) random_plan[random_total++] = (long long)candidate;
    }
    if(o->window_bytes)
      status=exr_publication_pager_create(publication,o->part,font,&config,&chapter_options,&pager,&error);
    else status = exr_pager_create(document, font, &config, &pager, &error);
    if (status != EXR_OK) goto done;
    status = exr_pager_set_cache(pager, o->cache_pages, o->cache_bytes, &error);
    if (status != EXR_OK) goto done;
    status = exr_pager_set_checkpoints(pager, o->checkpoint_capacity, o->checkpoint_bytes,
                                       o->checkpoint_interval, &error);
    if (status != EXR_OK) goto done;
    for (j = 0; j < random_total; j++) {
      const exr_layout *cached = NULL;
      size_t index = (size_t)random_plan[j];
      page_sample s;
      status = exr_pager_get(pager, index, &cached, &error);
      if (status != EXR_OK) goto done;
      s = hash_layout(cached);
      if (s.hash != reference[index].hash) mismatches++;
    }
    cache_bytes = exr_pager_cached_bytes(pager);
    { exr_pager_stats stats = exr_pager_statistics(pager);
      restored = stats.restored_checkpoints;
      generated = stats.generated_pages; }
    if(o->window_bytes) chapter_stats=exr_pager_chapter_statistics(pager);
    exr_pager_free(pager);
    pager = NULL;
  }
  status = EXR_OK;
done:
  process_memory(&resident, &peak);
  {
    char book_path[1024], error_text[512];
    json_text(o->book, book_path, sizeof(book_path));
    json_text(error.message, error_text, sizeof(error_text));
    if (error.message[0]) fprintf(stderr, "%s\n", error.message);
  fprintf(stdout, "{\"schema\":1,\"tool\":\"wp6-chapter-probe\",\"engine_version\":\"%s\",",
          exr_version());
  fprintf(stdout, "\"status\":%d,\"stage\":\"%s\",\"error\":\"%s\",", (int)status, stage,
          error_text);
  fprintf(stdout, "\"book\":\"%s\",\"book_bytes\":%zu,\"part\":%zu,\"parts\":%zu,", book_path,
          file_bytes(o->book), o->part, parts);
  }
  fprintf(stdout, "\"text_bytes\":%zu,\"nodes\":%zu,\"blocks\":%zu,", text_bytes, nodes, blocks);
  if(o->window_bytes) fprintf(stdout,
    "\"bounded\":{\"index_bytes\":%zu,\"parse_workspace_bytes\":%zu,\"peak_parse_workspace_bytes\":%zu,\"windows_loaded\":%zu,\"windows_evicted\":%zu,\"window_bytes\":%zu},",
    chapter_stats.index_bytes,chapter_stats.parse_workspace_bytes,chapter_stats.peak_parse_workspace_bytes,
    chapter_stats.windows_loaded,chapter_stats.windows_evicted,o->window_bytes);
  fprintf(stdout, "\"parse_workspace\":{\"document_owned_bytes\":%zu,\"projection_bytes\":%zu,",
          document ? owned : 0, text_bytes);
  fprintf(stdout, "\"node_array_bytes\":%zu,\"attribute_array_bytes\":%zu,",
          document ? nodes * sizeof(exr_node) : 0, attribute_arrays);
  fprintf(stdout, "\"block_array_bytes\":%zu,", blocks * sizeof(exr_block));
  {
    size_t measured = nodes * sizeof(exr_node) + attribute_arrays + blocks * sizeof(exr_block);
    fprintf(stdout, "\"other_bytes\":%zu},", document && owned > measured ? owned - measured : 0);
  }
  fprintf(stdout, "\"strings\":{\"node_text_bytes\":%zu,\"node_name_bytes\":%zu,",
          node_text, node_names);
  fprintf(stdout, "\"attribute_text_bytes\":%zu,\"chapter_metadata_bytes\":%zu,",
          attribute_text, chapter_strings);
  fprintf(stdout, "\"resource_metadata_bytes\":%zu},", resource_strings);
  fprintf(stdout, "\"categories\":{\"book_bytes\":%zu,\"index_rss_bytes\":%zu,", file_bytes(o->book),
          index_resident > font_resident ? index_resident - font_resident : 0);
  fprintf(stdout, "\"page_cache_bytes\":%zu,\"explicit_snapshot_bytes\":0},", cache_bytes);
  fprintf(stdout, "\"plan\":{\"turns\":%zu,\"max_pages\":%zu,\"random\":%zu,\"seed\":%llu,",
          o->turns, o->max_pages, o->random_pages, o->seed);
  fprintf(stdout, "\"cache_pages\":%zu,\"cache_bytes\":%zu,\"checkpoints\":%zu,", o->cache_pages,
          o->cache_bytes, o->checkpoint_capacity);
  fprintf(stdout, "\"checkpoint_bytes\":%zu,\"checkpoint_interval\":%zu},", o->checkpoint_bytes,
          o->checkpoint_interval);
  fprintf(stdout, "\"timing\":{\"font_open_ms\":%.6f,\"publication_open_ms\":%.6f,", font_ms, open_ms);
  fprintf(stdout, "\"chapter_load_ms\":%.6f,\"pager_create_ms\":%.6f,", load_ms, create_ms);
  fprintf(stdout, "\"first_page_layout_ms\":%.6f,\"first_paint_ms\":%.6f,", first_page_ms, paint_ms);
  fprintf(stdout, "\"first_visible_total_ms\":%.6f},",
          font_ms + open_ms + load_ms + create_ms + first_page_ms + paint_ms);
  fprintf(stdout, "\"sequential\":{\"turns\":%zu,\"enumerated\":%zu,\"reached_eof\":%s,\"all_pages_hash\":\"%016llx\",\"turn_layout_ms\":[", turns,
          enumerated,reached_eof ? "true" : "false",(unsigned long long)all_pages_hash);
  for (j = 0; j < turns; j++) fprintf(stdout, "%s%.6f", j ? "," : "", turn_layout[j]);
  fprintf(stdout, "],\"turn_render_ms\":[");
  for (j = 0; j < turns; j++) fprintf(stdout, "%s%.6f", j ? "," : "", turn_render[j]);
  fprintf(stdout, "],\"page_hashes\":[");
  for (j = 0; j < reference_count; j++) print_page(stdout, j == 0, j, &reference[j]);
  fprintf(stdout, "]},");
  fprintf(stdout, "\"random\":{\"pages\":%zu,\"mismatches\":%zu,\"restored_checkpoints\":%zu,",
          random_total, mismatches, restored);
  fprintf(stdout, "\"generated_pages\":%zu,\"cache_bytes\":%zu,\"plan\":[", generated, cache_bytes);
  for (j = 0; j < random_total; j++) fprintf(stdout, "%s%lld", j ? "," : "", random_plan[j]);
  fprintf(stdout, "]},");
  fprintf(stdout, "\"memory\":{\"baseline_resident_bytes\":%zu,\"font_resident_bytes\":%zu,",
          base_resident, font_resident);
  fprintf(stdout, "\"index_resident_bytes\":%zu,\"load_resident_bytes\":%zu,",
          index_resident, load_resident);
  fprintf(stdout, "\"first_page_resident_bytes\":%zu,\"resident_bytes\":%zu,", first_resident,
          resident);
  fprintf(stdout, "\"peak_rss_bytes\":%zu,\"baseline_peak_rss_bytes\":%zu,", peak, baseline_peak);
  fprintf(stdout, "\"font_peak_rss_bytes\":%zu,\"load_peak_rss_bytes\":%zu,",
          font_peak, load_peak);
  fprintf(stdout, "\"first_page_peak_rss_bytes\":%zu,", first_peak);
  fprintf(stdout, "\"incremental_peak_rss_bytes\":%zu}}\n",
          peak > font_peak ? peak - font_peak : 0);
  exr_bitmap_free(&bitmap);
  exr_layout_free(page);
  exr_pager_free(pager);
  exr_document_free(document);
  exr_publication_free(publication);
  exr_font_free(font);
  return status == EXR_OK ? 0 : 1;
}

int main(int argc, char **argv) {
  options o;
  if (!parse(&o, argc, argv)) return 2;
  return run(&o);
}
