/* SPDX-License-Identifier: MIT */
/* Deterministic structure-mutating fuzz driver for the memory parsers.
 *
 * No external fuzzing runtime is required: one process mutates seed inputs with
 * a seeded xorshift generator, writes the exact bytes about to be parsed to
 * --save, and then parses them. A crash therefore leaves the triggering input on
 * disk. Runs are reproducible from (seed, corpus, iteration count).
 *
 * Usage:
 *   exreader-fuzz --seed 1 --iterations 100000 --save last.bin a.pdf b.epub c.txt
 */
#include "exreader.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <inttypes.h>

typedef struct { unsigned char *data; size_t size; const char *name; } seed;

static uint64_t state = 0x9E3779B97F4A7C15u;
static uint64_t next_random(void) {
  uint64_t x = state;
  x ^= x << 13; x ^= x >> 7; x ^= x << 17;
  state = x;
  return x;
}
static size_t below(size_t n) { return n ? (size_t)(next_random() % n) : 0; }

static unsigned char *read_file(const char *path, size_t *size) {
  FILE *f = fopen(path, "rb");
  long n; unsigned char *data;
  if (!f) return NULL;
  if (fseek(f, 0, SEEK_END) || (n = ftell(f)) <= 0 || fseek(f, 0, SEEK_SET)) { fclose(f); return NULL; }
  data = malloc((size_t)n);
  if (!data || fread(data, 1, (size_t)n, f) != (size_t)n) { free(data); fclose(f); return NULL; }
  fclose(f); *size = (size_t)n; return data;
}

/* Parsers accept untrusted bytes; a failed open must always be a clean EXR_* status. */
static int parse(const unsigned char *data, size_t size) {
  exr_error error; exr_document *doc = NULL; exr_fixed_document *fixed = NULL;
  size_t count = 0, i; int parsed = 0;
  int pdf = size >= 5 && !memcmp(data, "%PDF-", 5);
  int zip = size >= 4 && data[0] == 'P' && data[1] == 'K' && data[2] == 3 && data[3] == 4;
  if (pdf) {
    if (exr_fixed_open_memory(EXR_PDF, data, size, NULL, &fixed, &error) == EXR_OK && fixed) {
      parsed = 1;
      (void)exr_fixed_title(fixed);
      if (exr_fixed_pages(fixed, &count)) {
        for (i = 0; i < count && i < 4; i++) {
          const exr_fixed_page *page = exr_fixed_pages(fixed, &count) + i;
          (void)page->id; (void)page->geometry.bounds[2];
        }
      }
      exr_fixed_free(fixed);
    }
  } else {
    exr_format format = zip ? EXR_EPUB : (size && data[0] == '<' ? EXR_FB2 : EXR_TXT);
    if (exr_document_open_memory(format, data, size, &doc, &error) == EXR_OK && doc) {
      parsed = 1;
      (void)exr_document_title(doc);
      (void)exr_document_text(doc, &count);
      if (exr_document_chapters(doc, &count)) (void)count;
      if (exr_document_blocks(doc, &count)) (void)count;
      exr_document_free(doc);
    }
  }
  return parsed;
}

static void mutate(unsigned char **buf, size_t *size, size_t capacity, const seed *seeds, size_t seed_count) {
  unsigned rounds = 1 + (unsigned)below(8), r;
  for (r = 0; r < rounds; r++) {
    size_t n = *size, at, len;
    unsigned char *b = *buf;
    switch (below(8)) {
      case 0: if (n) b[below(n)] ^= (unsigned char)(1u << below(8)); break;
      case 1: if (n) b[below(n)] = (unsigned char)next_random(); break;
      case 2:
        if (n < capacity) { at = below(n + 1); memmove(b + at + 1, b + at, n - at); b[at] = (unsigned char)next_random(); *size = n + 1; }
        break;
      case 3:
        if (n > 1) { at = below(n); len = 1 + below(n - at); memmove(b + at, b + at + len, n - at - len); *size = n - len; }
        break;
      case 4:
        if (n && n < capacity) { at = below(n); len = 1 + below(n - at); if (len > capacity - n) len = capacity - n;
          memmove(b + at + len, b + at, n - at); memcpy(b + at, b + at + len, len); *size = n + len; }
        break;
      case 5:
        if (n) { at = below(n); len = 1 + below(n - at); memset(b + at, (int)(next_random() & 0xFF), len); }
        break;
      case 6: if (n > 8) *size = 1 + below(n); break;
      default:
        if (seed_count && n) {
          const seed *s = &seeds[below(seed_count)];
          at = below(n); len = s->size ? 1 + below(s->size) : 0;
          if (len > capacity - at) len = capacity - at;
          if (len) memcpy(b + at, s->data + (s->size > len ? below(s->size - len) : 0), len);
        }
        break;
    }
  }
}

int main(int argc, char **argv) {
  seed *seeds; size_t seed_count = 0, capacity = 1u << 20, size, i;
  unsigned char *buf; const char *save = "fuzz-last.bin";
  uint64_t iterations = 10000;
  unsigned parsed_count = 0;
  FILE *sink;
  int a;
  seeds = calloc((size_t)argc + 1, sizeof(*seeds));
  if (!seeds) { fprintf(stderr, "fuzz: allocation failed\n"); return 2; }
  for (a = 1; a < argc; a++) {
    if (!strcmp(argv[a], "--seed") && a + 1 < argc) { state = strtoull(argv[++a], NULL, 10) | 1u; continue; }
    if (!strcmp(argv[a], "--iterations") && a + 1 < argc) { iterations = strtoull(argv[++a], NULL, 10); continue; }
    if (!strcmp(argv[a], "--save") && a + 1 < argc) { save = argv[++a]; continue; }
    if (!strcmp(argv[a], "--max-bytes") && a + 1 < argc) { capacity = strtoull(argv[++a], NULL, 10); continue; }
    if (argv[a][0] == '-') { fprintf(stderr, "fuzz: unknown option %s\n", argv[a]); return 2; }
    seeds[seed_count].name = argv[a];
    seeds[seed_count].data = read_file(argv[a], &seeds[seed_count].size);
    if (!seeds[seed_count].data) { fprintf(stderr, "fuzz: cannot read %s\n", argv[a]); return 2; }
    if (seeds[seed_count].size > capacity) capacity = seeds[seed_count].size;
    seed_count++;
  }
  if (!seed_count || !iterations) { fprintf(stderr, "fuzz: need at least one seed file and non-zero iterations\n"); return 2; }
  buf = malloc(capacity);
  if (!buf) { fprintf(stderr, "fuzz: allocation failed\n"); return 2; }
  sink = fopen(save, "wb");
  if (!sink) { fprintf(stderr, "fuzz: cannot create %s\n", save); return 2; }
  for (i = 0; i < iterations; i++) {
    const seed *base = &seeds[below(seed_count)];
    size = base->size < capacity ? base->size : capacity;
    memcpy(buf, base->data, size);
    mutate(&buf, &size, capacity, seeds, seed_count);
    /* Keep the exact bytes on disk before parsing so a crash is reproducible. */
    rewind(sink); fwrite(buf, 1, size, sink); fflush(sink);
    parsed_count += (unsigned)parse(buf, size);
    if ((i + 1) % 10000 == 0) fprintf(stderr, "fuzz: %" PRIu64 " iterations, %u parsed\n", (uint64_t)(i + 1), parsed_count);
  }
  fclose(sink);
  printf("fuzz: %" PRIu64 " iterations over %zu seeds, %u reached a parsed document, no crash\n",
         iterations, seed_count, parsed_count);
  for (i = 0; i < seed_count; i++) free(seeds[i].data);
  free(seeds); free(buf);
  return 0;
}
