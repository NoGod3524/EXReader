/* SPDX-License-Identifier: GPL-3.0-only */
#include "exreader.h"
#include <ctype.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static exr_error error;
static unsigned checks;
static exr_font *font;
#define CHECK(x)                                                                                   \
  do {                                                                                             \
    checks++;                                                                                      \
    if (!(x)) {                                                                                    \
      fprintf(stderr, "line %d: %s (%d: %s)\n", __LINE__, #x, (int)error.code, error.message);      \
      exit(1);                                                                                     \
    }                                                                                              \
  } while (0)
#define OK(x) CHECK((x) == EXR_OK)

static size_t encode(char *out, uint32_t cp) {
  if (cp < 0x80) {
    out[0] = (char)cp;
    return 1;
  }
  if (cp < 0x800) {
    out[0] = (char)(0xc0 | (cp >> 6));
    out[1] = (char)(0x80 | (cp & 0x3f));
    return 2;
  }
  if (cp < 0x10000) {
    out[0] = (char)(0xe0 | (cp >> 12));
    out[1] = (char)(0x80 | ((cp >> 6) & 0x3f));
    out[2] = (char)(0x80 | (cp & 0x3f));
    return 3;
  }
  out[0] = (char)(0xf0 | (cp >> 18));
  out[1] = (char)(0x80 | ((cp >> 12) & 0x3f));
  out[2] = (char)(0x80 | ((cp >> 6) & 0x3f));
  out[3] = (char)(0x80 | (cp & 0x3f));
  return 4;
}

/* Compare every byte, including continuation bytes, with Unicode's independent oracle. */
static void grapheme_conformance(const char *directory) {
  char path[4096], line[32768], text[8192];
  unsigned char expected[sizeof(text) + 1];
  unsigned cases = 0, source_line = 0;
  FILE *file;
  snprintf(path, sizeof(path), "%s/GraphemeBreakTest.txt", directory);
  file = fopen(path, "rb");
  CHECK(file);
  while (fgets(line, sizeof(line), file)) {
    char *p = line;
    size_t size = 0, i;
    unsigned char *actual = NULL;
    int have_cp = 0;
    source_line++;
    memset(expected, 0, sizeof(expected));
    while (*p && *p != '#') {
      char *end;
      unsigned long cp;
      while (isspace((unsigned char)*p))
        p++;
      if (!*p || *p == '#')
        break;
      if ((unsigned char)p[0] == 0xc3 &&
          ((unsigned char)p[1] == 0xb7 || (unsigned char)p[1] == 0x97)) {
        expected[size] = (unsigned char)p[1] == 0xb7;
        p += 2;
        continue;
      }
      cp = strtoul(p, &end, 16);
      CHECK(end != p && cp <= 0x10ffff && !(cp >= 0xd800 && cp <= 0xdfff));
      CHECK(size + 4 < sizeof(text));
      size += encode(text + size, (uint32_t)cp);
      p = end;
      have_cp = 1;
    }
    if (!have_cp)
      continue;
    text[size] = 0;
    OK(exr_text_analyze(text, size, &actual, &error));
    CHECK(actual);
    for (i = 0; i <= size; i++) {
      if (!!(actual[i] & EXR_BOUNDARY_GRAPHEME) != !!expected[i]) {
        fprintf(stderr, "GraphemeBreakTest.txt:%u byte %zu: expected %u, flags %u\n",
                source_line, i, (unsigned)expected[i], (unsigned)actual[i]);
        CHECK(0);
      }
      CHECK(!(actual[i] & (EXR_BOUNDARY_LINE | EXR_BOUNDARY_MANDATORY)) ||
            (actual[i] & EXR_BOUNDARY_GRAPHEME));
      if (i < size && ((unsigned char)text[i] & 0xc0) == 0x80)
        CHECK(!actual[i]);
    }
    CHECK((actual[0] & EXR_BOUNDARY_GRAPHEME) &&
          (actual[size] & (EXR_BOUNDARY_GRAPHEME | EXR_BOUNDARY_LINE | EXR_BOUNDARY_MANDATORY)) ==
              (EXR_BOUNDARY_GRAPHEME | EXR_BOUNDARY_LINE | EXR_BOUNDARY_MANDATORY));
    exr_free(actual);
    cases++;
  }
  CHECK(!ferror(file));
  CHECK(fclose(file) == 0);
  CHECK(cases > 700);
  printf("%u Unicode grapheme conformance cases passed\n", cases);
}

static unsigned char *analyze(const char *text) {
  unsigned char *map = NULL;
  OK(exr_text_analyze(text, strlen(text), &map, &error));
  CHECK(map);
  return map;
}

static void rejected(const char *text, size_t size, exr_status status) {
  unsigned char *map = (unsigned char *)(uintptr_t)1;
  CHECK(exr_text_analyze(text, size, &map, &error) == status);
  CHECK(!map && error.code == status && error.message[0]);
}

static void validation(void) {
  static const char *const invalid[] = {
      "\x80", "\xc0\xaf", "\xc2", "\xe0\x80\x80", "\xed\xa0\x80",
      "\xe2\x82", "\xf0\x80\x80\x80", "\xf4\x90\x80\x80", "\xf5\x80\x80\x80"};
  const char embedded[] = {'a', 0, 'b'};
  unsigned char *map;
  size_t i;
  rejected(NULL, 0, EXR_ARGUMENT);
  rejected(NULL, 1, EXR_ARGUMENT);
  CHECK(exr_text_analyze("a", 1, NULL, &error) == EXR_ARGUMENT);
  for (i = 0; i < sizeof(invalid) / sizeof(*invalid); i++)
    rejected(invalid[i], strlen(invalid[i]), EXR_ENCODING);
  OK(exr_text_analyze(embedded, sizeof(embedded), &map, &error));
  for (i = 0; i <= sizeof(embedded); i++)
    CHECK(map[i] & EXR_BOUNDARY_GRAPHEME);
  exr_free(map);
  rejected("a", (size_t)64 * 1024 * 1024 + 1, EXR_LIMIT);
  rejected("a", SIZE_MAX, EXR_LIMIT);
  map = analyze("");
  CHECK((map[0] & (EXR_BOUNDARY_GRAPHEME | EXR_BOUNDARY_LINE | EXR_BOUNDARY_MANDATORY)) ==
        (EXR_BOUNDARY_GRAPHEME | EXR_BOUNDARY_LINE | EXR_BOUNDARY_MANDATORY));
  exr_free(map);
  OK(exr_text_analyze("A", 1, &map, NULL));
  CHECK(map);
  exr_free(map);
}

/* The line-break contract is deliberately a subset, independently of UAX #29 conformance. */
static void line_opportunities(void) {
  static const char *const glue[] = {"\xc2\xa0", "\xe2\x80\xaf", "\xe2\x81\xa0",
                                     "\xef\xbb\xbf"};
  static const char *const hard[] = {"\r\n", "\r", "\n", "\xc2\x85", "\xe2\x80\xa8",
                                     "\xe2\x80\xa9"};
  unsigned char *map;
  char text[32];
  size_t i, n;
  map = analyze("\xe7\x94\xb2\xe4\xb9\x99"); /* CJK pair */
  CHECK(map[3] & EXR_BOUNDARY_LINE);
  exr_free(map);
  map = analyze("\xe7\x94\xb2\xef\xbc\x88\xe4\xb9\x99");
  CHECK(!(map[6] & EXR_BOUNDARY_LINE)); /* opening fullwidth parenthesis */
  exr_free(map);
  map = analyze("\xe7\x94\xb2\xef\xbc\x89\xe4\xb9\x99");
  CHECK(!(map[3] & EXR_BOUNDARY_LINE)); /* closing fullwidth parenthesis */
  exr_free(map);
  map = analyze("aa bb");
  CHECK(map[3] & EXR_BOUNDARY_LINE);
  exr_free(map);
  for (i = 0; i < sizeof(glue) / sizeof(*glue); i++) {
    snprintf(text, sizeof(text), "A%sB", glue[i]);
    n = 1 + strlen(glue[i]);
    map = analyze(text);
    CHECK((map[1] & EXR_BOUNDARY_GLUE) && (map[n] & EXR_BOUNDARY_GLUE));
    CHECK(!(map[1] & EXR_BOUNDARY_LINE) && !(map[n] & EXR_BOUNDARY_LINE));
    exr_free(map);
  }
  map = analyze("A\xe2\x80\x8b" "B");
  CHECK(map[4] & EXR_BOUNDARY_LINE);
  exr_free(map);
  map = analyze("A\xc2\xad" "B");
  CHECK(map[3] & EXR_BOUNDARY_LINE);
  exr_free(map);
  map = analyze("A\xe2\x80\x8d" "B");
  CHECK((map[4] & EXR_BOUNDARY_GLUE) && !(map[4] & EXR_BOUNDARY_LINE));
  exr_free(map);
  for (i = 0; i < sizeof(hard) / sizeof(*hard); i++) {
    snprintf(text, sizeof(text), "A%sB", hard[i]);
    n = 1 + strlen(hard[i]);
    map = analyze(text);
    CHECK((map[n] & (EXR_BOUNDARY_GRAPHEME | EXR_BOUNDARY_LINE | EXR_BOUNDARY_MANDATORY)) ==
          (EXR_BOUNDARY_GRAPHEME | EXR_BOUNDARY_LINE | EXR_BOUNDARY_MANDATORY));
    if (i == 0)
      CHECK(!map[2]); /* CRLF is one grapheme, with no interior break. */
    exr_free(map);
  }
}

static exr_document *document(const char *const *parts, size_t count) {
  exr_attribute id = {"id", "body"};
  exr_attribute styles[] = {{"style", "font-size:16px;color:#112233"},
                             {"style", "font-size:20px;color:#334455;font-weight:bold"}};
  exr_node_input nodes[67] = {{EXR_NODE_DOCUMENT, SIZE_MAX, NULL, NULL, NULL, 0},
                              {EXR_NODE_CHAPTER, 0, NULL, NULL, NULL, 0},
                              {EXR_NODE_PARAGRAPH, 1, NULL, NULL, &id, 1}};
  exr_chapter_input chapter = {NULL, "unicode.unit", 1, 1};
  exr_document_input input = {NULL, nodes, 3 + count * 2, &chapter, 1, NULL, 0};
  exr_document *doc = NULL;
  size_t i;
  CHECK(count <= 32);
  for (i = 0; i < count; i++) {
    nodes[3 + i * 2] = (exr_node_input){EXR_NODE_ELEMENT, 2, NULL, NULL, &styles[i % 2], 1};
    nodes[4 + i * 2] = (exr_node_input){EXR_NODE_TEXT, 3 + i * 2, NULL, parts[i], NULL, 0};
  }
  OK(exr_document_create(&input, &doc, &error));
  return doc;
}

static exr_layout *layout(const exr_document *doc, int narrow, float height) {
  exr_layout_config config = exr_layout_config_defaults();
  exr_layout *result = NULL;
  config.page.width = narrow ? 80 : 500;
  config.page.height = height;
  config.page.margin = 8;
  config.page.font_size = 16;
  config.page.line_height = 1.25f;
  config.page.paragraph_spacing = 0;
  if (narrow)
    config.user_css = "#body {width:1px}";
  OK(exr_layout_create_ex(doc, font, &config, &result, &error));
  return result;
}

static void valid_clusters(const exr_document *doc, const exr_layout *lay) {
  size_t size, ng, nl, np, i, j;
  const char *text = exr_document_text(doc, &size);
  const exr_glyph *glyphs = exr_layout_glyphs(lay, &ng);
  const exr_line *lines = exr_layout_lines(lay, &nl);
  const exr_page *pages = exr_layout_pages(lay, &np);
  unsigned char *map = analyze(text);
  CHECK(ng && nl && np);
  for (i = 0; i < ng; i++) {
    const exr_glyph *g = &glyphs[i];
    size_t start = g->start, end = g->end, hit;
    CHECK(start < end && end <= size);
    while (start && !(map[start] & EXR_BOUNDARY_GRAPHEME))
      start--;
    while (end < size && !(map[end] & EXR_BOUNDARY_GRAPHEME))
      end++;
    CHECK(g->cluster_start == start && g->cluster_end == end);
    if ((g->flags & EXR_GLYPH_SHAPED) && i &&
        glyphs[i - 1].cluster_start == g->cluster_start)
      CHECK(!g->boundaries);
    else
      CHECK(g->boundaries == map[g->start]);
    if (i && glyphs[i - 1].cluster_start == start)
      CHECK(g->page == glyphs[i - 1].page &&
            fabsf(g->baseline - glyphs[i - 1].baseline) < 0.01f);
    for (j = 0; j < 3; j++) {
      hit = exr_layout_hit_test(lay, g->page, g->x + g->advance * (float)j / 2,
                                g->baseline - g->size / 3);
      CHECK(hit <= size && (map[hit] & EXR_BOUNDARY_GRAPHEME));
    }
  }
  for (i = 0; i < nl; i++) {
    CHECK(lines[i].start <= size && lines[i].end <= size);
    CHECK((map[lines[i].start] & EXR_BOUNDARY_GRAPHEME) &&
          (map[lines[i].end] & EXR_BOUNDARY_GRAPHEME));
  }
  for (i = 0; i < np; i++) {
    CHECK(pages[i].start <= size && pages[i].end <= size);
    CHECK((map[pages[i].start] & EXR_BOUNDARY_GRAPHEME) &&
          (map[pages[i].end] & EXR_BOUNDARY_GRAPHEME));
  }
  exr_free(map);
}

static void inline_clusters(void) {
  /* Each grapheme straddles differently styled inline nodes. */
  const char *parts[] = {"a", "\xcc\x81", "X", "\xf0\x9f\x91\xa9",
                         "\xe2\x80\x8d", "\xf0\x9f\x92\xbb", "Y",
                         "\xf0\x9f\x87\xba", "\xf0\x9f\x87\xb8", "Z",
                         "\xe0\xa4\x95", "\xe0\xa5\x8d", "\xe0\xa4\xb7", "Q",
                         "\xe1\x84\x80", "\xe1\x85\xa1", "\xe1\x86\xa8", "R"};
  exr_document *doc = document(parts, sizeof(parts) / sizeof(*parts));
  exr_layout *wide = layout(doc, 0, 160), *narrow = layout(doc, 1, 64);
  size_t n;
  valid_clusters(doc, wide);
  valid_clusters(doc, narrow);
  exr_layout_pages(narrow, &n);
  CHECK(n > 1);
  exr_layout_free(wide);
  exr_layout_free(narrow);
  exr_document_free(doc);
}

static void single_cluster_hit(void) {
  const char *clusters[][3] = {{"a", "\xcc\x81", NULL},
                              {"\xf0\x9f\x91\xa9", "\xe2\x80\x8d", "\xf0\x9f\x92\xbb"},
                              {"\xf0\x9f\x87\xba", "\xf0\x9f\x87\xb8", NULL},
                              {"\xe0\xa4\x95", "\xe0\xa5\x8d", "\xe0\xa4\xb7"},
                              {"\xe1\x84\x80", "\xe1\x85\xa1", "\xe1\x86\xa8"}};
  size_t i;
  for (i = 0; i < sizeof(clusters) / sizeof(*clusters); i++) {
    exr_document *doc = document(clusters[i], clusters[i][2] ? 3 : 2);
    exr_layout *lay = layout(doc, 0, 160);
    const exr_glyph *g;
    size_t n, size, j;
    exr_document_text(doc, &size);
    g = exr_layout_glyphs(lay, &n);
    CHECK(n >= 2);
    valid_clusters(doc, lay);
    for (j = 0; j < n; j++) {
      size_t hit = exr_layout_hit_test(lay, g[j].page, g[j].x + g[j].advance / 2,
                                       g[j].baseline - g[j].size / 3);
      CHECK(hit == 0 || hit == size);
    }
    exr_layout_free(lay);
    exr_document_free(doc);
  }
}

static void protected_groups(void) {
  const char *groups[] = {"A\xc2\xa0" "B", "A\xe2\x80\xaf" "B",
                          "A\xe2\x81\xa0" "B", "A\xef\xbb\xbf" "B", "A\xe2\x80\x8d" "B"};
  size_t i, n;
  for (i = 0; i < sizeof(groups) / sizeof(*groups); i++) {
    exr_document *doc = document(&groups[i], 1);
    exr_layout *lay = layout(doc, 1, 64);
    const exr_glyph *g = exr_layout_glyphs(lay, &n);
    size_t j;
    valid_clusters(doc, lay);
    exr_layout_lines(lay, &n);
    CHECK(n == 1); /* Overwide nonbreaking groups clip rather than split. */
    g = exr_layout_glyphs(lay, &n);
    for (j = 0; j < n; j++)
      if (g[j].codepoint == 0xa0 || g[j].codepoint == 0x202f)
        CHECK(g[j].advance > 0);
    exr_layout_free(lay);
    exr_document_free(doc);
  }
  {
    const char *parts[] = {"AB"};
    exr_document *doc = document(parts, 1);
    exr_layout *lay = layout(doc, 1, 64);
    exr_layout_lines(lay, &n);
    CHECK(n == 2); /* Emergency wrap still works at an ordinary grapheme boundary. */
    exr_layout_free(lay);
    exr_document_free(doc);
  }
  {
    const char *parts[] = {"A\xe2\x80\x8b" "B"};
    exr_document *doc = document(parts, 1);
    exr_layout *lay = layout(doc, 1, 64);
    exr_layout_lines(lay, &n);
    CHECK(n == 2);
    valid_clusters(doc, lay);
    exr_layout_free(lay);
    exr_document_free(doc);
  }
}

static void mandatory_lines(void) {
  const char *hard[] = {"A\xc2\x85" "B", "A\xe2\x80\xa8" "B",
                         "A\xe2\x80\xa9" "B"};
  size_t i, n;
  for (i = 0; i < sizeof(hard) / sizeof(*hard); i++) {
    exr_document *doc = document(&hard[i], 1);
    exr_layout *lay = layout(doc, 0, 160);
    exr_layout_lines(lay, &n);
    CHECK(n == 2);
    valid_clusters(doc, lay);
    exr_layout_free(lay);
    exr_document_free(doc);
  }
}

static void protected_marks_and_quotes(void) {
  const char *groups[] = {"A\xe2\x81\xa0\xcc\x81" "B", "A\xef\xbb\xbf\xcc\x81" "B",
                          "\xe2\x80\x9c\xe7\x94\xb2\xe2\x80\x9d",
                          "\xe2\x80\x98\xe7\x94\xb2\xe2\x80\x99"};
  size_t i;
  for (i = 0; i < sizeof(groups) / sizeof(*groups); i++) {
    unsigned char *map = analyze(groups[i]);
    size_t before = i < 2 ? 1 : 3, after = 6, n;
    exr_document *doc = document(&groups[i], 1);
    exr_layout *lay = layout(doc, 1, 64);
    CHECK((map[before] & EXR_BOUNDARY_GLUE) && (map[after] & EXR_BOUNDARY_GLUE));
    CHECK(!(map[before] & EXR_BOUNDARY_LINE) && !(map[after] & EXR_BOUNDARY_LINE));
    exr_layout_lines(lay, &n);
    CHECK(n == 1); /* Marks inherit WJ; opening/closing curly quotes stay with CJK. */
    valid_clusters(doc, lay);
    exr_free(map);
    exr_layout_free(lay);
    exr_document_free(doc);
  }
}

static void invisible_controls(void) {
  const char *parts[] = {"\xe2\x80\x8b\xe2\x81\xa0\xef\xbb\xbf\xc2\xad\xc2\x85"
                         "\xe2\x80\xa8\xe2\x80\xa9"
                         "\xe1\xa0\x8b\xe1\xa0\x8c\xe1\xa0\x8d\xe1\xa0\x8f\xcd\x8f"};
  exr_document *doc = document(parts, 1);
  exr_layout *lay = layout(doc, 0, 160);
  const exr_glyph *glyphs;
  exr_bitmap bitmap = {0};
  size_t n, i, np;
  glyphs = exr_layout_glyphs(lay, &n);
  CHECK(n == 12);
  for (i = 0; i < n; i++)
    CHECK(glyphs[i].advance == 0 && (glyphs[i].flags & EXR_GLYPH_HIDDEN));
  exr_layout_pages(lay, &np);
  CHECK(np > 0);
  for (i = 0; i < np; i++) {
    size_t j;
    OK(exr_render_page(lay, font, i, &bitmap, &error));
    for (j = 0; j < (size_t)bitmap.stride * bitmap.height; j++)
      CHECK(bitmap.pixels[j] == 255);
    exr_bitmap_free(&bitmap);
  }
  exr_layout_free(lay);
  exr_document_free(doc);
}

static void long_runs(void) {
  const size_t count = 60001;
  char *text = malloc(count * 4 + 16);
  unsigned char *map = NULL;
  size_t i, size;
  CHECK(text);
  size = 0;
  for (i = 0; i < count; i++)
    size += encode(text + size, 0x1f1e6 + (uint32_t)(i % 26));
  OK(exr_text_analyze(text, size, &map, &error));
  for (i = 0; i < count; i++) {
    CHECK(!!(map[i * 4] & EXR_BOUNDARY_GRAPHEME) == !(i % 2));
    CHECK(!map[i * 4 + 1] && !map[i * 4 + 2] && !map[i * 4 + 3]);
  }
  CHECK(map[size] & EXR_BOUNDARY_GRAPHEME);
  exr_free(map);
  size = encode(text, 0x1f469);
  for (i = 0; i < count; i++)
    size += encode(text + size, 0x301);
  size += encode(text + size, 0x200d);
  size += encode(text + size, 0x1f4bb);
  OK(exr_text_analyze(text, size, &map, &error));
  CHECK(map[0] & EXR_BOUNDARY_GRAPHEME);
  for (i = 1; i < size; i++)
    CHECK(!map[i]);
  CHECK(map[size] & EXR_BOUNDARY_GRAPHEME);
  exr_free(map);
  free(text);
}

int main(int argc, char **argv) {
  const char *font_path = getenv("EXR_TEST_FONT");
  if (argc < 2 || argc > 3) {
    fprintf(stderr, "usage: test_text unicode_fixtures [font]\n");
    return 2;
  }
  if (argc == 3)
    font_path = argv[2];
#ifdef _WIN32
  if (!font_path)
    font_path = "C:/Windows/Fonts/arial.ttf";
#elif defined(__APPLE__)
  if (!font_path)
    font_path = "/System/Library/Fonts/Supplemental/Arial.ttf";
#else
  if (!font_path)
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf";
#endif
  validation();
  grapheme_conformance(argv[1]);
  line_opportunities();
  long_runs();
  OK(exr_font_open(font_path, &font, &error));
  inline_clusters();
  single_cluster_hit();
  protected_groups();
  protected_marks_and_quotes();
  mandatory_lines();
  invisible_controls();
  exr_font_free(font);
  printf("%u text boundary and cluster layout checks passed\n", checks);
  return 0;
}
