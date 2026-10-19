/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include "../src/bidi_internal.h"
#include <inttypes.h>

static exr_error error;
static unsigned long checks, cases;
static const char *corpus;
static size_t corpus_line;
#define CHECK(x) do { checks++; if (!(x)) { \
  fprintf(stderr, "%s:%zu line %d: %s (%d: %s)\n", corpus ? corpus : "API", \
          corpus_line, __LINE__, #x, (int)error.code, error.message); exit(1); } } while (0)
#define OK(x) CHECK((x) == EXR_OK)
#define LIMIT 2048

static size_t encode(uint32_t cp, char *out) {
  if (cp < 0x80) { out[0] = (char)cp; return 1; }
  if (cp < 0x800) {
    out[0] = (char)(0xc0 | (cp >> 6)); out[1] = (char)(0x80 | (cp & 63)); return 2;
  }
  if (cp < 0x10000) {
    out[0] = (char)(0xe0 | (cp >> 12)); out[1] = (char)(0x80 | ((cp >> 6) & 63));
    out[2] = (char)(0x80 | (cp & 63)); return 3;
  }
  out[0] = (char)(0xf0 | (cp >> 18)); out[1] = (char)(0x80 | ((cp >> 12) & 63));
  out[2] = (char)(0x80 | ((cp >> 6) & 63)); out[3] = (char)(0x80 | (cp & 63)); return 4;
}
static size_t numbers(char *text, unsigned *out, int base, int x) {
  size_t count = 0;
  char *at = text, *end;
  while (*at) {
    while (*at == ' ' || *at == '\t' || *at == '\r' || *at == '\n') at++;
    if (!*at || *at == '#') break;
    CHECK(count < LIMIT);
    if (x && *at == 'x') { out[count++] = UINT_MAX; at++; }
    else {
      unsigned long value = strtoul(at, &end, base);
      CHECK(end != at && value <= UINT_MAX);
      out[count++] = (unsigned)value;
      at = end;
    }
  }
  return count;
}
static void verify(const uint32_t *codepoints, size_t count, exr_direction direction,
                      const unsigned *levels, const unsigned *visual, size_t visual_count,
                      unsigned expected_base) {
  char text[LIMIT * 4];
  exr_bidi *bidi = NULL;
  const exr_bidi_scalar *scalars;
  size_t size = 0, i, n, *order = NULL;
  for (i = 0; i < count; i++) size += encode(codepoints[i], text + size);
  OK(exr_bidi_analyze(text, size, direction, &bidi, &error));
  scalars = exr_bidi_scalars(bidi, &n);
  CHECK(n == count);
  for (i = 0; i < count; i++) {
    if (scalars[i].level != levels[i]) {
      fprintf(stderr, "scalar %zu U+%04" PRIX32 " direction %u: expected %u, got %u\n",
              i, codepoints[i], (unsigned)direction, levels[i], scalars[i].level);
      CHECK(0);
    }
    CHECK(scalars[i].codepoint == codepoints[i]);
    CHECK(scalars[i].start < scalars[i].end && scalars[i].end <= size);
    if (expected_base != UINT_MAX) CHECK(exr_bidi_base_level(bidi, i) == expected_base);
  }
  OK(exr_bidi_reorder(bidi, 0, count, &order, &n, &error));
  CHECK(n == visual_count);
  for (i = 0; i < n; i++) {
    if (order[i] != visual[i]) {
      fprintf(stderr, "visual %zu direction %u: expected %u, got %zu\n",
              i, (unsigned)direction, visual[i], order[i]);
      CHECK(0);
    }
    CHECK(order[i] < count);
  }
  exr_free(order);
  exr_bidi_free(bidi);
  cases++;
}
static FILE *open_corpus(const char *directory, const char *name) {
  char path[4096];
  FILE *file;
  CHECK(snprintf(path, sizeof(path), "%s/%s", directory, name) > 0);
  file = fopen(path, "rb");
  CHECK(file);
  corpus = name;
  corpus_line = 0;
  return file;
}
static void property_tests(const char *directory) {
  static const char *names[] = {"L", "R", "AL", "EN", "ES", "ET", "AN", "CS", "NSM", "BN", "B", "S", "WS", "ON", "LRE", "LRO", "RLE", "RLO", "PDF", "LRI", "RLI", "FSI", "PDI"};
  static const uint32_t representatives[] = {0x41,0x5d0,0x627,0x30,0x2b,0x24,0x660,0x2c,0x300,0xad,0xa,0x9,0x20,0x21,0x202a,0x202d,0x202b,0x202e,0x202c,0x2066,0x2067,0x2068,0x2069};
  FILE *file = open_corpus(directory, "BidiTest.txt");
  char line[16384];
  unsigned levels[LIMIT], visual[LIMIT];
  size_t level_count = 0, visual_count = 0;
  while (fgets(line, sizeof(line), file)) {
    char *at = line, *semicolon, *token;
    uint32_t codepoints[LIMIT];
    size_t count = 0, i;
    unsigned bits, mask;
    corpus_line++;
    if (!strncmp(line, "@Levels:", 8)) { level_count = numbers(line + 8, levels, 10, 1); continue; }
    if (!strncmp(line, "@Reorder:", 9)) { visual_count = numbers(line + 9, visual, 10, 0); continue; }
    if (*line == '#' || *line == '@' || *line == '\r' || *line == '\n') continue;
    semicolon = strchr(line, ';'); CHECK(semicolon); *semicolon++ = 0;
    bits = (unsigned)strtoul(semicolon, NULL, 16);
    token = strtok(at, " \t\r\n");
    while (token) {
      CHECK(count < LIMIT);
      for (i = 0; i < sizeof(names) / sizeof(*names); i++) if (!strcmp(token, names[i])) break;
      CHECK(i < sizeof(names) / sizeof(*names));
      codepoints[count++] = representatives[i];
      token = strtok(NULL, " \t\r\n");
    }
    CHECK(count == level_count);
    for (mask = 1; mask <= 4; mask <<= 1)
      if (bits & mask)
        verify(codepoints, count, mask == 1 ? EXR_DIRECTION_AUTO : mask == 2 ? EXR_DIRECTION_LTR : EXR_DIRECTION_RTL,
                 levels, visual, visual_count, UINT_MAX);
  }
  CHECK(!ferror(file) && !fclose(file));
}
static void character_tests(const char *directory) {
  FILE *file = open_corpus(directory, "BidiCharacterTest.txt");
  char line[16384];
  while (fgets(line, sizeof(line), file)) {
    char *fields[5], *at = line;
    unsigned codepoints[LIMIT], levels[LIMIT], visual[LIMIT], mode, base;
    size_t count, nlevels, nvisual, i;
    corpus_line++;
    if (*line == '#' || *line == '\r' || *line == '\n') continue;
    fields[0] = at;
    for (i = 1; i < 5; i++) { at = strchr(at, ';'); CHECK(at); *at++ = 0; fields[i] = at; }
    count = numbers(fields[0], codepoints, 16, 0);
    mode = (unsigned)strtoul(fields[1], NULL, 10);
    base = (unsigned)strtoul(fields[2], NULL, 10);
    nlevels = numbers(fields[3], levels, 10, 1);
    nvisual = numbers(fields[4], visual, 10, 0);
    CHECK(count == nlevels && mode <= 2 && base <= 1);
    verify(codepoints, count, mode == 2 ? EXR_DIRECTION_AUTO : mode == 1 ? EXR_DIRECTION_RTL : EXR_DIRECTION_LTR,
               levels, visual, nvisual, base);
  }
  CHECK(!ferror(file) && !fclose(file));
}
static void api(void) {
  exr_bidi *bidi = (exr_bidi *)(uintptr_t)1;
  const exr_bidi_scalar *scalars;
  size_t count, *order = (size_t *)(uintptr_t)1;
  const char text[] = "A \xd7\x90\xd7\x91\n\xd7\x92 B\0";
  corpus = NULL; corpus_line = 0;
  CHECK(exr_bidi_analyze(NULL, 0, EXR_DIRECTION_AUTO, &bidi, &error) == EXR_ARGUMENT && !bidi);
  CHECK(exr_bidi_analyze("", 0, (exr_direction)3, &bidi, &error) == EXR_ARGUMENT && !bidi);
  CHECK(exr_bidi_analyze("", (size_t)64 * 1024 * 1024 + 1, EXR_DIRECTION_AUTO, &bidi, &error) == EXR_LIMIT && !bidi);
  CHECK(exr_bidi_analyze("\xc0\xaf", 2, EXR_DIRECTION_LTR, &bidi, &error) == EXR_ENCODING && !bidi);
  CHECK(exr_bidi_analyze("", 0, EXR_DIRECTION_AUTO, NULL, &error) == EXR_ARGUMENT);
  OK(exr_bidi_analyze("", 0, EXR_DIRECTION_AUTO, &bidi, &error));
  CHECK(!exr_bidi_scalars(bidi, &count) && !count);
  OK(exr_bidi_reorder(bidi, 0, 0, &order, &count, &error)); CHECK(!order && !count);
  exr_bidi_free(bidi);
  OK(exr_bidi_analyze(text, sizeof(text) - 1, EXR_DIRECTION_AUTO, &bidi, &error));
  scalars = exr_bidi_scalars(bidi, &count); CHECK(count == 9 && scalars[8].codepoint == 0);
  CHECK(scalars[8].level == UINT_MAX);
  CHECK(exr_bidi_base_level(bidi, 0) == 0 && exr_bidi_base_level(bidi, 5) == 1);
  OK(exr_bidi_reorder(bidi, 0, count, &order, &count, &error));
  CHECK(count == 8 && order[0] == 0 && order[2] == 3 && order[3] == 2);
  CHECK(order[5] == 7 && order[6] == 6 && order[7] == 5);
  exr_free(order);
  OK(exr_bidi_reorder(bidi, 1, 2, &order, &count, &error));
  CHECK(count == 2 && order[0] == 1 && order[1] == 2); exr_free(order);
  order = (size_t *)(uintptr_t)1; count = 99;
  CHECK(exr_bidi_reorder(bidi, SIZE_MAX, 1, &order, &count, &error) == EXR_ARGUMENT && !order && !count);
  CHECK(exr_bidi_reorder(bidi, 0, 1, NULL, &count, &error) == EXR_ARGUMENT && !count);
  CHECK(exr_bidi_reorder(bidi, 0, 1, &order, NULL, &error) == EXR_ARGUMENT && !order);
  exr_bidi_free(bidi); exr_bidi_free(NULL);
  CHECK(!exr_bidi_scalars(NULL, &count) && !count);
  CHECK(exr_bidi_mirror('(') == ')' && exr_bidi_mirror(0x2329) == 0x232a && exr_bidi_mirror('A') == 'A');
}
static void line_slices(void) {
  const char text[] = "\xd7\x90 A B";
  const char segments[] = "\xd7\x90\tA\nA\t\xd7\x90";
  exr_bidi *bidi = NULL;
  const exr_bidi_scalar *scalars;
  size_t *order = NULL, count;
  corpus = NULL; corpus_line = 0;
  OK(exr_bidi_analyze(text, sizeof(text) - 1, EXR_DIRECTION_AUTO, &bidi, &error));
  scalars = exr_bidi_scalars(bidi, &count);
  CHECK(count == 5 && scalars[3].level == 2);
  OK(exr_bidi_reorder(bidi, 2, 2, &order, &count, &error));
  CHECK(count == 2 && order[0] == 3 && order[1] == 2);
  CHECK(scalars[3].level == 2); /* Reordering a line never mutates the analysis. */
  exr_free(order); exr_bidi_free(bidi);
  OK(exr_bidi_analyze(segments, sizeof(segments) - 1, EXR_DIRECTION_AUTO, &bidi, &error));
  scalars = exr_bidi_scalars(bidi, &count);
  CHECK(count == 7 && scalars[1].level == 1 && scalars[5].level == 0);
  CHECK(exr_bidi_base_level(bidi, 2) == 1 && exr_bidi_base_level(bidi, 6) == 0);
  exr_bidi_free(bidi);
  OK(exr_bidi_analyze("\xe2\x80\xaa\xe2\x80\xac\xc2\xad", 8, EXR_DIRECTION_AUTO, &bidi, &error));
  OK(exr_bidi_reorder(bidi, 0, 3, &order, &count, &error));
  CHECK(!order && !count);
  exr_bidi_free(bidi);
}
static void default_properties(void) {
  /* These unassigned code points obtain their properties from @missing ranges. */
  uint32_t cps[] = {0x41, 0x20, 0x86f, 0x30, 0x2c, 0x660};
  char text[32];
  size_t i, size = 0, count;
  exr_bidi *bidi = NULL;
  const exr_bidi_scalar *scalars;
  for (i = 0; i < sizeof(cps) / sizeof(*cps); i++) size += encode(cps[i], text + size);
  OK(exr_bidi_analyze(text, size, EXR_DIRECTION_LTR, &bidi, &error));
  scalars = exr_bidi_scalars(bidi, &count);
  CHECK(count == 6 && scalars[2].level == 1 && scalars[4].level == 2);
  exr_bidi_free(bidi);
  size = encode(0x590, text);
  OK(exr_bidi_analyze(text, size, EXR_DIRECTION_AUTO, &bidi, &error));
  CHECK(exr_bidi_base_level(bidi, 0) == 1);
  exr_bidi_free(bidi);
  size = encode(0x5d0, text);
  text[size++] = '0';
  size += encode(0x20cf, text + size);
  OK(exr_bidi_analyze(text, size, EXR_DIRECTION_LTR, &bidi, &error));
  scalars = exr_bidi_scalars(bidi, &count);
  CHECK(count == 3 && scalars[2].level == 2);
  exr_bidi_free(bidi);
}
static void stress(void) {
  char text[10000];
  char *long_text;
  exr_bidi *bidi = NULL;
  const exr_bidi_scalar *scalars;
  size_t size = 0, i, count, *order = NULL;
  for (i = 0; i < 1000; i++) size += encode(0x202b, text + size);
  text[size++] = 'A';
  for (i = 0; i < 1000; i++) size += encode(0x202c, text + size);
  OK(exr_bidi_analyze(text, size, EXR_DIRECTION_LTR, &bidi, &error));
  scalars = exr_bidi_scalars(bidi, &count);
  CHECK(count == 2001 && scalars[1000].level == 126);
  OK(exr_bidi_reorder(bidi, 0, count, &order, &count, &error));
  CHECK(count == 1 && order[0] == 1000);
  exr_free(order); exr_bidi_free(bidi);
  size = 0;
  for (i = 0; i < 1000; i++) size += encode(0x2066, text + size);
  size += encode(0x5d0, text + size);
  for (i = 0; i < 1000; i++) size += encode(0x2069, text + size);
  OK(exr_bidi_analyze(text, size, EXR_DIRECTION_LTR, &bidi, &error));
  scalars = exr_bidi_scalars(bidi, &count);
  CHECK(count == 2001 && scalars[1000].level == 125);
  for (i = 0; i < count; i++) CHECK(scalars[i].level <= 126);
  exr_bidi_free(bidi);
  long_text = malloc(200001); CHECK(long_text);
  long_text[0] = 'A';
  for (i = 0; i < 100000; i++) encode(0x300, long_text + 1 + 2 * i);
  OK(exr_bidi_analyze(long_text, 200001, EXR_DIRECTION_AUTO, &bidi, &error));
  free(long_text);
  scalars = exr_bidi_scalars(bidi, &count);
  CHECK(count == 100001);
  OK(exr_bidi_reorder(bidi, 0, count, &order, &count, &error));
  for (i = 0; i < count; i++) CHECK(order[i] == i && scalars[i].level == 0);
  exr_free(order); exr_bidi_free(bidi);
  long_text = malloc(4 * 1024 * 1024 + 1); CHECK(long_text);
  memset(long_text, 'A', 4 * 1024 * 1024 + 1);
  CHECK(exr_bidi_analyze(long_text, 4 * 1024 * 1024 + 1, EXR_DIRECTION_AUTO, &bidi, &error) == EXR_LIMIT && !bidi);
  free(long_text);
}
int main(int argc, char **argv) {
  CHECK(argc == 2);
  api(); line_slices(); default_properties(); stress();
  property_tests(argv[1]); character_tests(argv[1]);
  printf("%lu Unicode 17 bidi conformance cases, %lu checks passed\n", cases, checks);
  return 0;
}
