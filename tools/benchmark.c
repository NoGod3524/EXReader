/* SPDX-License-Identifier: MIT */
#ifndef _WIN32
#define _POSIX_C_SOURCE 200809L
#endif
#ifdef __APPLE__
#define _DARWIN_C_SOURCE
#endif
#include "exreader.h"
#include <errno.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
#include <psapi.h>
#include <io.h>
#include <fcntl.h>
#else
#include <sys/resource.h>
#include <sys/stat.h>
#include <time.h>
#endif

static double now_ms(void) {
#ifdef _WIN32
  LARGE_INTEGER count, frequency;
  if (!QueryPerformanceFrequency(&frequency) || !QueryPerformanceCounter(&count))
    return -1;
  return (double)count.QuadPart * 1000.0 / (double)frequency.QuadPart;
#else
  struct timespec t;
  if (clock_gettime(CLOCK_MONOTONIC, &t))
    return -1;
  return (double)t.tv_sec * 1000.0 + (double)t.tv_nsec / 1000000.0;
#endif
}

/* OS process high-water mark, including font copies and generated input. */
static int peak_rss(uint64_t *bytes) {
#ifdef _WIN32
  PROCESS_MEMORY_COUNTERS memory;
  if (!GetProcessMemoryInfo(GetCurrentProcess(), &memory, sizeof(memory)))
    return 0;
  *bytes = (uint64_t)memory.PeakWorkingSetSize;
#else
  struct rusage usage;
  if (getrusage(RUSAGE_SELF, &usage))
    return 0;
  *bytes = (uint64_t)usage.ru_maxrss;
#ifndef __APPLE__
  *bytes *= 1024;
#endif
#endif
  return 1;
}

static int file_size(const char *path, uint64_t *bytes) {
#ifdef _WIN32
  wchar_t *wide;
  HANDLE file;
  LARGE_INTEGER size;
  int ok, n = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, path, -1, NULL, 0);
  if (!n || !(wide = malloc((size_t)n * sizeof(*wide))))
    return 0;
  if (!MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, path, -1, wide, n)) {
    free(wide);
    return 0;
  }
  file = CreateFileW(wide, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING,
                     FILE_ATTRIBUTE_NORMAL, NULL);
  free(wide);
  if (file == INVALID_HANDLE_VALUE)
    return 0;
  ok = GetFileSizeEx(file, &size) && size.QuadPart >= 0;
  CloseHandle(file);
  if (ok)
    *bytes = (uint64_t)size.QuadPart;
  return ok;
#else
  struct stat info;
  if (stat(path, &info) || info.st_size < 0)
    return 0;
  *bytes = (uint64_t)info.st_size;
  return 1;
#endif
}

static int number(const char *text, size_t *value) {
  char *end;
  unsigned long long parsed;
  if (!text[0] || text[0] == '-' || text[0] == '+')
    return 0;
  errno = 0;
  parsed = strtoull(text, &end, 10);
  if (errno || *end || parsed > SIZE_MAX)
    return 0;
  *value = (size_t)parsed;
  return 1;
}

static void json_string(const char *text) {
  const unsigned char *p = (const unsigned char *)text;
  putchar('"');
  for (; *p; p++) {
    if (*p == '"' || *p == '\\')
      printf("\\%c", *p);
    else if (*p < 32)
      printf("\\u%04x", (unsigned)*p);
    else
      putchar(*p);
  }
  putchar('"');
}

static int compare_double(const void *left, const void *right) {
  double a = *(const double *)left, b = *(const double *)right;
  return (a > b) - (a < b);
}

/* Nearest-rank percentiles: no interpolation or hidden warmup samples. */
static double percentile(const double *sorted, size_t count, unsigned percent) {
  return sorted[((count * percent + 99) / 100) - 1];
}

typedef struct { double layout, render, total; } timing_sample;

static int reserve_sample(timing_sample **samples, size_t *capacity, size_t count) {
  timing_sample *grown;
  size_t next;
  if (count < *capacity)
    return 1;
  next = *capacity ? *capacity * 2 : 64;
  if (next < *capacity || next > SIZE_MAX / sizeof(**samples))
    return 0;
  grown = realloc(*samples, next * sizeof(**samples));
  if (!grown)
    return 0;
  *samples = grown;
  *capacity = next;
  return 1;
}

static void metric_json(const char *name, const timing_sample *samples, size_t count,
                         int field, double *sorted) {
  size_t i;
  for (i = 0; i < count; i++)
    sorted[i] = field == 0 ? samples[i].layout : field == 1 ? samples[i].render : samples[i].total;
  qsort(sorted, count, sizeof(*sorted), compare_double);
  printf(",\"%s_p50_ms\":%.6f,\"%s_p95_ms\":%.6f,\"%s_ms_samples\":[",
         name, percentile(sorted, count, 50), name, percentile(sorted, count, 95), name);
  for (i = 0; i < count; i++) {
    double value = field == 0 ? samples[i].layout : field == 1 ? samples[i].render : samples[i].total;
    printf("%s%.6f", i ? "," : "", value);
  }
  putchar(']');
}

static int example_main(int argc, char **argv) {
  static const char pattern[] =
      "Reading a portable book starts with a small, open C engine. "
      "Every chapter has repeatable words and measurable page rendering.\n\n";
  const char *book = NULL, *font_path = NULL;
  exr_publication *publication = NULL;
  exr_session *session = NULL;
  exr_pager *pager = NULL;
  exr_hyphenator *hyphenator = NULL;
  const char *hyphen_language = NULL;
  exr_hyphen_case_policy case_policy=EXR_HYPHEN_CASE_LITERAL;int saw_case=0;
  unsigned char *hyphen_patterns = NULL;
  size_t hyphen_size = 0, inserted = 0;
  double hyphen_ms = 0;
  exr_document *owned_doc = NULL;
  exr_layout *owned_layout = NULL;
  exr_font *font = NULL;
  const exr_document *document = NULL;
  const exr_layout *layout = NULL;
  const exr_part *parts;
  exr_bitmap bitmap = {0};
  exr_error error = {0};
  exr_status status;
  char *text = NULL;
  timing_sample *samples = NULL;
  double *sorted = NULL;
  double started, at, font_ms, publication_ms = 0, layout_ms, paint_ms, total_ms;
  size_t generated = 0, max_pages = 64, part_count = 1, part = 0, capacity = 0;
  size_t text_bytes = 0, page_count = 0, glyph_count = 0, sample_count = 0, i;
  uint64_t input_bytes = 0, baseline = 0, peak = 0;
  int paging = 0, saw_max = 0, total_pages_known = 1;
  int result = 1, generated_mode = argc > 1 && !strcmp(argv[1], "--text-bytes");
  int base = generated_mode ? 4 : 3, arg;
  if (argc < base)
    goto usage;
  if (generated_mode) {
    if (!number(argv[2], &generated) || !generated || generated > 64u * 1024u * 1024u)
      goto usage;
    font_path = argv[3];
    input_bytes = (uint64_t)generated;
  } else {
    book = argv[1];
    font_path = argv[2];
  }
  for (arg = base; arg < argc; arg++) {
    if (!strcmp(argv[arg], "--paging") && !paging)
      paging = 1;
    else if (!strcmp(argv[arg], "--max-pages") && !saw_max && arg + 1 < argc) {
      if (!number(argv[++arg], &max_pages))
        goto usage;
      saw_max = 1;
    } else if (!strcmp(argv[arg], "--hyphens") && !hyphen_language && arg + 1 < argc)
      hyphen_language = argv[++arg];
    else if (!strcmp(argv[arg], "--hyphen-case") && !saw_case && arg+1<argc) {
      const char *value=argv[++arg];saw_case=1;
      if(!strcmp(value,"word")) case_policy=EXR_HYPHEN_CASE_WORD;
      else if(strcmp(value,"literal")) goto usage;
    } else
      goto usage;
  }
  if ((saw_case && !hyphen_language) || (hyphen_language && generated_mode)) goto usage;
  total_pages_known = !paging;
  if (now_ms() < 0 || !peak_rss(&baseline)) {
    fprintf(stderr, "Monotonic clock or process peak RSS unavailable\n");
    goto done;
  }
  if (generated_mode) {
    text = malloc(generated);
    if (!text) {
      fprintf(stderr, "Generated text allocation failed\n");
      goto done;
    }
    for (i = 0; i < generated;) {
      size_t n = sizeof(pattern) - 1;
      if (n > generated - i)
        n = generated - i;
      memcpy(text + i, pattern, n);
      i += n;
    }
  } else if (!file_size(book, &input_bytes)) {
    fprintf(stderr, "Cannot read input file size\n");
    goto done;
  }
  if (hyphen_language) {
#ifdef _WIN32
    if (_setmode(_fileno(stdin), _O_BINARY) == -1) { fprintf(stderr,"Cannot set binary dictionary stdin\n"); goto done; }
#endif
    /* Grow with actual input: an 8 MiB fread request can inflate Windows pipe
       peak RSS even for a tiny dictionary, obscuring the engine measurement. */
    { size_t reserved = 0;
      for (;;) {
        size_t available, got;
        if (hyphen_size == reserved) {
          size_t next = reserved ? reserved * 2 : 4096;
          unsigned char *grown = realloc(hyphen_patterns, next);
          if (!grown) { fprintf(stderr,"Dictionary input allocation failed\n"); goto done; }
          hyphen_patterns = grown; reserved = next;
        }
        available = reserved - hyphen_size;
        got = fread(hyphen_patterns + hyphen_size, 1, available, stdin); hyphen_size += got;
        if (hyphen_size == 8u * 1024u * 1024u) {
          if (fgetc(stdin) != EOF) { fprintf(stderr,"Hyphenation stdin exceeds 8 MiB\n"); goto done; }
          break;
        }
        if (got < available) break;
      }
    }
    if (ferror(stdin)) { fprintf(stderr,"Dictionary stdin could not be read\n"); goto done; }
  }
  started = at = now_ms();
  status = exr_font_open(font_path, &font, &error);
  font_ms = now_ms() - at;
  if (status != EXR_OK)
    goto engine_error;
  if (hyphen_language) {
    exr_hyphen_pattern_input input = {sizeof(input),hyphen_language,hyphen_patterns,hyphen_size,0,0};
    at = now_ms();
    status = exr_hyphenator_create_patterns_ex(&input,1,0,case_policy,NULL,&hyphenator,&error);
    hyphen_ms = now_ms() - at;
    free(hyphen_patterns); hyphen_patterns = NULL;
    if (status != EXR_OK) goto engine_error;
  }
  if (!generated_mode) {
    at = now_ms();
    status = exr_publication_open(book, &publication, &error);
    publication_ms = now_ms() - at;
    if (status != EXR_OK)
      goto engine_error;
    parts = exr_publication_parts(publication, &part_count);
    while (part < part_count && !parts[part].in_reading_order)
      part++;
    if (part == part_count) {
      fprintf(stderr, "Publication has no reading-order part\n");
      goto done;
    }
    if (!paging) {
      status = exr_session_create(publication, font, NULL, 1, &session, &error);
      if (status == EXR_OK && hyphenator) status = exr_session_set_hyphenator(session,hyphenator,&error);
      if (status != EXR_OK)
        goto engine_error;
    }
  }
  at = now_ms();
  if (generated_mode || paging) {
    status = generated_mode ? exr_document_open_memory(EXR_TXT, text, generated, &owned_doc, &error)
                            : exr_publication_load(publication, part, &owned_doc, &error);
    document = owned_doc;
    if (status == EXR_OK && paging)
      status = exr_pager_create(owned_doc, font, NULL, &pager, &error);
    if (status == EXR_OK && paging && hyphenator) status = exr_pager_set_hyphenator(pager,hyphenator,&error);
    if (status == EXR_OK)
      status = paging ? exr_pager_next(pager, &owned_layout, &error)
                      : exr_layout_create(owned_doc, font, NULL, &owned_layout, &error);
    layout = owned_layout;
  } else {
    status = exr_session_get(session, part, &document, &layout, &error);
  }
  layout_ms = now_ms() - at;
  if (status != EXR_OK)
    goto engine_error;
  if (!layout) {
    fprintf(stderr, "Layout has no pages\n");
    goto done;
  }
  exr_document_text(document, &text_bytes);
  exr_layout_pages(layout, &page_count);
  { const exr_glyph *g = exr_layout_glyphs(layout, &glyph_count);
    for(i=0;i<glyph_count;i++) inserted+=!!(g[i].flags&EXR_GLYPH_GENERATED);
  }
  if (!page_count) {
    fprintf(stderr, "Layout has no pages\n");
    goto done;
  }
  at = now_ms();
  status = exr_render_page(layout, font, 0, &bitmap, &error);
  exr_bitmap_free(&bitmap);
  paint_ms = now_ms() - at;
  total_ms = now_ms() - started;
  if (status != EXR_OK)
    goto engine_error;
  while (!max_pages || sample_count < max_pages) {
    timing_sample sample = {0};
    double turn_started = now_ms();
    size_t render_page = 0;
    int eof = 0;
    if (paging) {
      exr_layout *next = NULL;
      at = now_ms();
      status = exr_pager_next(pager, &next, &error);
      sample.layout = now_ms() - at;
      if (status != EXR_OK)
        goto engine_error;
      if (!next) {
        total_pages_known = eof = 1;
        if (page_count > 1)
          break;
        /* One-page input: retain page 0 for the explicitly marked repaint. */
      } else {
        size_t pages, glyphs;
        exr_layout_free(owned_layout);
        owned_layout = next;
        layout = next;
        exr_layout_pages(layout, &pages);
        { const exr_glyph *g = exr_layout_glyphs(layout, &glyphs);
          for(i=0;i<glyphs;i++) inserted+=!!(g[i].flags&EXR_GLYPH_GENERATED);
        }
        page_count += pages;
        glyph_count += glyphs;
      }
    } else {
      if (page_count > 1) {
        if (sample_count >= page_count - 1)
          break;
        render_page = sample_count + 1;
      } else if (sample_count)
        break;
      /* Eager pages already exist: their per-turn layout cost is exactly zero. */
    }
    at = now_ms();
    status = exr_render_page(layout, font, render_page, &bitmap, &error);
    exr_bitmap_free(&bitmap);
    sample.render = now_ms() - at;
    sample.total = now_ms() - turn_started;
    if (status != EXR_OK)
      goto engine_error;
    if (!reserve_sample(&samples, &capacity, sample_count)) {
      fprintf(stderr, "Timing sample allocation failed\n");
      goto done;
    }
    samples[sample_count++] = sample;
    if (eof)
      break;
  }
  if (!sample_count || sample_count > SIZE_MAX / sizeof(*sorted) ||
      !(sorted = malloc(sample_count * sizeof(*sorted)))) {
    fprintf(stderr, "Timing sample allocation failed\n");
    goto done;
  }
  if (!peak_rss(&peak)) {
    fprintf(stderr, "Process peak RSS unavailable\n");
    goto done;
  }
  printf("{\"schema_version\":2,\"engine_version\":");
  json_string(exr_version());
  printf(",\"mode\":\"%s\",\"layout_mode\":\"%s\",\"layout_scope\":\"%s\",\"input\":",
         generated_mode ? "generated_txt" : "indexed_epub", paging ? "paged" : "eager",
         generated_mode ? "whole_generated_text" : "first_reading_order_part");
  json_string(book ? book : "generated");
  printf(",\"font\":");
  json_string(font_path);
  printf(",\"clock\":\"monotonic\",\"disk_cache\":\"uncontrolled\","
         "\"rss_metric\":\"process_high_water_mark\",\"input_bytes\":%" PRIu64
         ",\"text_bytes\":%zu,\"part_count\":%zu,\"part_index\":%zu,"
         "\"page_count\":%zu,\"total_pages_known\":%s,\"glyph_count\":%zu,\"sample_count\":%zu,"
         "\"sample_first_page\":%u,\"single_page_repaint\":%s,"
         "\"font_open_ms\":%.6f,\"publication_open_ms\":%.6f,"
         "\"first_layout_ms\":%.6f,\"first_paint_ms\":%.6f,"
         "\"first_visible_total_ms\":%.6f,\"baseline_peak_rss_bytes\":%" PRIu64
         ",\"peak_rss_bytes\":%" PRIu64 ",\"incremental_peak_rss_bytes\":%" PRIu64,
         input_bytes, text_bytes, part_count, part, page_count, total_pages_known ? "true" : "false",
         glyph_count, sample_count, page_count > 1 ? 1u : 0u, page_count == 1 ? "true" : "false",
         font_ms, publication_ms, layout_ms, paint_ms, total_ms,
         baseline, peak, peak >= baseline ? peak - baseline : 0);
  printf(",\"hyphenation_enabled\":%s,\"hyphen_dictionary_input_bytes\":%zu,\"hyphen_dictionary_payload_bytes\":%zu,\"hyphen_dictionary_load_ms\":%.6f,\"generated_glyph_count\":%zu",
         hyphenator ? "true" : "false",hyphen_size,exr_hyphenator_memory_size(hyphenator),hyphen_ms,inserted);
  printf(",\"hyphen_case_policy\":\"%s\"",hyphenator && case_policy==EXR_HYPHEN_CASE_WORD ? "word" : "literal");
  metric_json("turn_layout", samples, sample_count, 0, sorted);
  metric_json("turn_render", samples, sample_count, 1, sorted);
  metric_json("turn_total", samples, sample_count, 2, sorted);
  printf("}\n");
  result = 0;
  goto done;
engine_error:
  fprintf(stderr, "EXReader error %d: %s\n", (int)error.code, error.message);
  goto done;
usage:
  fprintf(stderr, "Usage: exreader-benchmark book.epub font.ttf [--max-pages N] [--paging] [--hyphens language] [--hyphen-case literal|word]\n"
                  "       exreader-benchmark --text-bytes N font.ttf [--max-pages N] [--paging]\n"
                  "N samples: default 64, zero renders all pages after the first paint.\n"
                  "--hyphens reads UTF-8 patterns from stdin; EPUB must opt in with CSS hyphens:auto.\n");
  result = 2;
done:
  exr_bitmap_free(&bitmap);
  free(samples);
  free(sorted);
  exr_layout_free(owned_layout);
  exr_pager_free(pager);
  exr_hyphenator_free(hyphenator);
  free(hyphen_patterns);
  exr_document_free(owned_doc);
  exr_session_free(session);
  exr_publication_free(publication);
  exr_font_free(font);
  free(text);
  return result;
}
#include "../examples/entry.h"
