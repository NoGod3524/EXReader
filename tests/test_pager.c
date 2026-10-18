/* SPDX-License-Identifier: GPL-3.0-only */
#include "exreader.h"
#include <inttypes.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* Define EXR_PAGER_GOLDEN_ONLY to record the fixture with the installed 0.10.0 SDK.
   The normal test compares both the old engine snapshot and independent page output.
   The old equal-column contract is explicitly requested with standard fixed
   table CSS. Native table-column/intrinsic tests cover the new auto default.
   In 0.18.0 fragment box source ranges were corrected; the 89 pixel baselines
   and other fixed-table geometry fields retain the original values. */
static exr_error error;
static unsigned checks;
static exr_font *font;
static const char *fixtures;
#define CHECK(x) do { checks++; if (!(x)) { \
  fprintf(stderr, "line %d: %s (%d: %s)\n", __LINE__, #x, (int)error.code, error.message); \
  exit(1); } } while (0)
#define OK(x) CHECK((x) == EXR_OK)

typedef struct { uint64_t layout, gray, rgba; } snapshot;
static void hash_byte(uint64_t *h, unsigned char b) { *h = (*h ^ b) * UINT64_C(1099511628211); }
static void hash_number(uint64_t *h, uint64_t n) {
  unsigned i;
  for (i = 0; i < 8; i++) { hash_byte(h, (unsigned char)n); n >>= 8; }
}
static void hash_index(uint64_t *h, size_t n) {
  hash_number(h, n == SIZE_MAX ? UINT64_MAX : (uint64_t)n);
}
/* Geometry is compared to 1/64 px. Hashing fields, rather than structs, excludes padding. */
static void hash_float(uint64_t *h, float n) {
  CHECK(isfinite(n));
  hash_number(h, (uint64_t)(int64_t)llroundf(n * 64));
}
static uint64_t pixels(const exr_layout *lay, size_t p, int color) {
  exr_bitmap bitmap = {0};
  uint64_t h = UINT64_C(14695981039346656037);
  size_t i;
  if (color) OK(exr_render_page_color(lay, font, p, &bitmap, &error));
  else OK(exr_render_page(lay, font, p, &bitmap, &error));
  hash_number(&h, bitmap.width); hash_number(&h, bitmap.height);
  hash_number(&h, bitmap.stride); hash_number(&h, bitmap.channels);
  for (i = 0; i < (size_t)bitmap.stride * bitmap.height; i++) hash_byte(&h, bitmap.pixels[i]);
  exr_bitmap_free(&bitmap);
  return h;
}
static uint64_t geometry(const exr_layout *lay, size_t p) {
  const exr_page *page = &exr_layout_pages(lay, NULL)[p];
  const exr_line *lines = exr_layout_lines(lay, NULL);
  const exr_glyph *glyphs = exr_layout_glyphs(lay, NULL);
  const exr_box *boxes = exr_layout_boxes(lay, NULL);
  uint64_t h = UINT64_C(14695981039346656037);
  size_t i, j, glyph_offset = 0;
  hash_index(&h, page->start); hash_index(&h, page->end);
  hash_index(&h, page->line_count); hash_index(&h, page->box_count);
  for (i = page->line_start; i < page->line_start + page->line_count; i++) {
    const exr_line *l = &lines[i];
    CHECK(l->page == p);
    hash_index(&h, l->start); hash_index(&h, l->end);
    hash_index(&h, glyph_offset); hash_index(&h, l->glyph_count);
    hash_float(&h, l->x); hash_float(&h, l->y);
    hash_float(&h, l->width); hash_float(&h, l->height);
    for (j = l->glyph_start; j < l->glyph_start + l->glyph_count; j++) {
      const exr_glyph *g = &glyphs[j];
      CHECK(g->page == p);
      hash_index(&h, g->start); hash_index(&h, g->end);
      hash_number(&h, g->codepoint); hash_number(&h, g->glyph);
      hash_float(&h, g->x); hash_float(&h, g->baseline);
      hash_float(&h, g->advance); hash_float(&h, g->size);
      hash_index(&h, g->node); hash_number(&h, g->color); hash_number(&h, g->flags);
      hash_float(&h, g->clip_left); hash_float(&h, g->clip_right);
      hash_float(&h, g->line_height);
      hash_index(&h, g->cluster_start); hash_index(&h, g->cluster_end);
      hash_number(&h, g->boundaries); hash_index(&h, g->font_index);
    }
    glyph_offset += l->glyph_count;
  }
  for (i = page->box_start; i < page->box_start + page->box_count; i++) {
    const exr_box *b = &boxes[i];
    CHECK(b->page == p);
    hash_number(&h, b->kind); hash_index(&h, b->node); hash_index(&h, b->resource);
    hash_index(&h, b->start); hash_index(&h, b->end);
    hash_float(&h, b->x); hash_float(&h, b->y);
    hash_float(&h, b->width); hash_float(&h, b->height); hash_float(&h, b->border_width);
    hash_number(&h, b->background); hash_number(&h, b->border_color); hash_number(&h, b->flags);
  }
  return h;
}
static snapshot capture(const exr_layout *lay, size_t p) {
  snapshot s;
  s.layout = geometry(lay, p); s.gray = pixels(lay, p, 0); s.rgba = pixels(lay, p, 1);
  return s;
}
#ifndef EXR_PAGER_GOLDEN_ONLY
static int same(snapshot a, snapshot b) {
  return a.layout == b.layout && a.gray == b.gray && a.rgba == b.rgba;
}
#endif
static void golden(FILE *f, const char *label, size_t p, snapshot actual) {
#ifdef EXR_PAGER_GOLDEN_ONLY
  fprintf(f, "%s %zu %016" PRIx64 " %016" PRIx64 " %016" PRIx64 "\n",
          label, p, actual.layout, actual.gray, actual.rgba);
#else
  snapshot expected;
  char name[80];
  size_t index;
  CHECK(fscanf(f, "%79s %zu %" SCNx64 " %" SCNx64 " %" SCNx64,
               name, &index, &expected.layout, &expected.gray, &expected.rgba) == 5);
  if (strcmp(name, label) || index != p || !same(actual, expected)) {
    fprintf(stderr, "%s page %zu: got %016" PRIx64 " %016" PRIx64 " %016" PRIx64 "\n",
            label, p, actual.layout, actual.gray, actual.rgba);
    CHECK(0);
  }
#endif
}
static exr_document *open_book(const char *name) {
  char path[4096];
  exr_document *doc = NULL;
  snprintf(path, sizeof(path), "%s/%s", fixtures, name);
  OK(exr_document_open(path, &doc, &error));
  return doc;
}
static void load_fonts(const char *directory) {
  const char *names[] = {"primary.ttf", "fallback.ttf"};
  exr_font_input inputs[2];
  size_t i;
  for (i = 0; i < 2; i++) {
    char path[4096];
    FILE *f;
    long size;
    void *data;
    snprintf(path, sizeof(path), "%s/%s", directory, names[i]);
    f = fopen(path, "rb");
    CHECK(f && !fseek(f, 0, SEEK_END)); size = ftell(f);
    CHECK(size > 0 && !fseek(f, 0, SEEK_SET));
    data = malloc((size_t)size); CHECK(data);
    CHECK(fread(data, 1, (size_t)size, f) == (size_t)size && !fclose(f));
    inputs[i] = (exr_font_input){data, (size_t)size, 0};
  }
  OK(exr_font_create(inputs, 2, &font, &error));
  for (i = 0; i < 2; i++) free((void *)inputs[i].data);
}
typedef struct {
  exr_node_input nodes[256];
  exr_attribute attrs[256][3];
  size_t count;
} construction;
static size_t add(construction *c, exr_node_kind kind, size_t parent, const char *text,
                   const char *style) {
  size_t n = c->count++;
  CHECK(n < 256);
  c->nodes[n] = (exr_node_input){kind, parent, NULL, text, c->attrs[n], style ? 1 : 0};
  if (style) c->attrs[n][0] = (exr_attribute){"style", style};
  return n;
}
static exr_document *finish(construction *c) {
  exr_chapter_input chapter = {"pager", "pager.unit", 1, 1};
  exr_document_input input = {"Pager fixture", c->nodes, c->count, &chapter, 1, NULL, 0};
  exr_document *doc = NULL;
  OK(exr_document_create(&input, &doc, &error));
  return doc;
}
static exr_document *host_document(void) {
  construction c = {0};
  size_t section, inner, p, table, row, cell, i;
  char text[1201];
  for (i = 0; i < sizeof(text)-1; i++) text[i] = "AV a aV "[i % 8];
  text[sizeof(text)-1] = 0;
  add(&c, EXR_NODE_DOCUMENT, SIZE_MAX, NULL, NULL);
  add(&c, EXR_NODE_CHAPTER, 0, NULL, "margin:0;padding:0");
  section = add(&c, EXR_NODE_SECTION, 1, NULL,
                "margin:3px 2px;padding:5px 7px 9px;border:2px solid #386a92;"
                "background:#edf3fa");
  inner = add(&c, EXR_NODE_SECTION, section, NULL,
              "margin:2px;padding:3px 4px 7px;border:1px solid #a03960;background:#f6e7ef");
  p = add(&c, EXR_NODE_PARAGRAPH, inner, NULL,
          "margin:1px 0 3px;text-align:justify;text-indent:9px;line-height:22px");
  add(&c, EXR_NODE_TEXT, p, text, NULL);
  p = add(&c, EXR_NODE_PARAGRAPH, inner, NULL, "margin:2px;line-height:24px");
  add(&c, EXR_NODE_TEXT, p, "AV AV a ", NULL);
  i = add(&c, EXR_NODE_ELEMENT, p, NULL, "font-size:24px;font-weight:bold;color:#723451");
  add(&c, EXR_NODE_TEXT, i, "a", NULL);
  i = add(&c, EXR_NODE_ELEMENT, p, NULL, "font-size:18px;color:#215321");
  add(&c, EXR_NODE_TEXT, i, "\xcc\x81 AV a AV a AV a", NULL);
  table = add(&c, EXR_NODE_TABLE, inner, NULL, "margin:4px 0;border:1px solid #304050;table-layout:fixed;width:100%");
  row = add(&c, EXR_NODE_ROW, table, NULL, NULL);
  cell = add(&c, EXR_NODE_CELL, row, NULL,
             "padding:2px;border:1px solid #506070;background:#ddeeff");
  c.attrs[cell][1] = (exr_attribute){"rowspan", "2"}; c.nodes[cell].attribute_count = 2;
  add(&c, EXR_NODE_TEXT, cell, "AV a AV a AV a", NULL);
  cell = add(&c, EXR_NODE_CELL, row, NULL, "padding:3px;border:1px solid #506070");
  add(&c, EXR_NODE_TEXT, cell, "AV a", NULL);
  row = add(&c, EXR_NODE_ROW, table, NULL, NULL);
  cell = add(&c, EXR_NODE_CELL, row, NULL, "padding:2px;border:1px solid #506070");
  add(&c, EXR_NODE_TEXT, cell, "a AV", NULL);
  row = add(&c, EXR_NODE_ROW, table, NULL, NULL);
  cell = add(&c, EXR_NODE_CELL, row, NULL, "padding:4px;border:1px solid #506070");
  c.attrs[cell][1] = (exr_attribute){"colspan", "2"}; c.nodes[cell].attribute_count = 2;
  add(&c, EXR_NODE_TEXT, cell, "AV a AV a AV a", NULL);
  p = add(&c, EXR_NODE_PARAGRAPH, section, NULL,
          "page-break-before:always;page-break-after:always;padding:3px;"
          "border:1px solid #302050;background:#dcefdc");
  add(&c, EXR_NODE_TEXT, p, "AV a AV a", NULL);
  p = add(&c, EXR_NODE_PARAGRAPH, 1, NULL, "text-align:right");
  add(&c, EXR_NODE_TEXT, p, "AV a", NULL);
  return finish(&c);
}
static exr_document *cluster_document(void) {
  static const char *const parts[] = {
      "a", "\xcc\x81", " ", "\xf0\x9f\x98\x80", "\xe2\x80\x8d",
      "\xf0\x9f\x98\x80", " ", "\xf0\x9f\x87\xba", "\xf0\x9f\x87\xb8", " "};
  construction c = {0};
  size_t i, span;
  add(&c, EXR_NODE_DOCUMENT, SIZE_MAX, NULL, NULL);
  add(&c, EXR_NODE_CHAPTER, 0, NULL, NULL);
  add(&c, EXR_NODE_PARAGRAPH, 1, NULL, "width:1px;line-height:34px;margin:0");
  for (i = 0; i < 60; i++) {
    span = add(&c, EXR_NODE_ELEMENT, 2, NULL,
               i % 2 ? "font-size:20px;color:#376251" : "font-size:16px;color:#513762");
    add(&c, EXR_NODE_TEXT, span, parts[i % 10], NULL);
  }
  return finish(&c);
}
static exr_document *text_document(size_t size) {
  exr_document *doc = NULL;
  char *text = malloc(size);
  size_t i;
  CHECK(text);
  for (i = 0; i < size; i++) text[i] = "AV a aV "[i % 8];
  OK(exr_document_open_memory(EXR_TXT, text, size, &doc, &error));
  free(text);
  return doc;
}

#ifndef EXR_PAGER_GOLDEN_ONLY
static void compare_page(const exr_layout *whole, size_t index, const exr_layout *part) {
  const exr_page *expected = &exr_layout_pages(whole, NULL)[index], *actual;
  size_t n, i, count = 0;
  const exr_glyph *g = exr_layout_glyphs(part, &n);
  const exr_line *lines = exr_layout_lines(part, &i);
  actual = exr_layout_pages(part, &count);
  CHECK(count == 1 && actual->start == expected->start && actual->end == expected->end);
  CHECK(actual->line_start == 0 && actual->box_start == 0);
  CHECK(actual->line_count == expected->line_count && actual->line_count == i);
  exr_layout_boxes(part, &count);
  CHECK(count == actual->box_count && count == expected->box_count);
  count = 0;
  for (i = 0; i < actual->line_count; i++) {
    CHECK(lines[i].page == 0 && lines[i].glyph_start == count);
    count += lines[i].glyph_count;
  }
  CHECK(count == n);
  for (i = 0; i < n; i++) CHECK(!g[i].page);
  CHECK(geometry(part, 0) == geometry(whole, index));
  CHECK(pixels(part, 0, 0) == pixels(whole, index, 0));
  CHECK(pixels(part, 0, 1) == pixels(whole, index, 1));
}
static void validate_clusters(const exr_layout *page, const unsigned char *map, size_t size) {
  const exr_glyph *g;
  const exr_line *lines;
  const exr_page *p = exr_layout_pages(page, NULL);
  size_t i, n;
  CHECK(p->start <= size && p->end <= size);
  CHECK((map[p->start] & EXR_BOUNDARY_GRAPHEME) && (map[p->end] & EXR_BOUNDARY_GRAPHEME));
  g = exr_layout_glyphs(page, &n);
  for (i = 0; i < n; i++) {
    size_t start = g[i].start, end = g[i].end;
    CHECK(start < end && end <= size);
    while (start && !(map[start] & EXR_BOUNDARY_GRAPHEME)) start--;
    while (end < size && !(map[end] & EXR_BOUNDARY_GRAPHEME)) end++;
    CHECK(g[i].cluster_start == start && g[i].cluster_end == end);
  }
  lines = exr_layout_lines(page, &n);
  for (i = 0; i < n; i++) {
    CHECK(map[lines[i].start] & EXR_BOUNDARY_GRAPHEME);
    CHECK(map[lines[i].end] & EXR_BOUNDARY_GRAPHEME);
  }
}
#endif
static void run_document(FILE *records, const char *label, exr_document *doc,
                          const exr_layout_config *config) {
  exr_layout *whole = NULL;
  size_t n, i;
#ifndef EXR_PAGER_GOLDEN_ONLY
  exr_pager *pager = NULL;
  exr_layout **pages;
  snapshot *snapshots;
  size_t position = 0, size;
  const char *text = exr_document_text(doc, &size);
  unsigned char *map = NULL;
  OK(exr_text_analyze(text, size, &map, &error));
  OK(exr_pager_create(doc, font, config, &pager, &error));
  CHECK(pager && !exr_pager_position(pager));
#endif
  OK(exr_layout_create_ex(doc, font, config, &whole, &error));
  exr_layout_pages(whole, &n); CHECK(n);
#ifndef EXR_PAGER_GOLDEN_ONLY
  pages = calloc(n, sizeof(*pages)); snapshots = calloc(n, sizeof(*snapshots));
  CHECK(pages && snapshots);
#endif
  for (i = 0; i < n; i++) {
    snapshot s = capture(whole, i);
    golden(records, label, i, s);
#ifndef EXR_PAGER_GOLDEN_ONLY
    OK(exr_pager_next(pager, &pages[i], &error)); CHECK(pages[i]);
    CHECK(exr_pager_position(pager) >= position && exr_pager_position(pager) <= size);
    position = exr_pager_position(pager);
    compare_page(whole, i, pages[i]);
    validate_clusters(pages[i], map, size);
    snapshots[i] = s;
#endif
  }
#ifndef EXR_PAGER_GOLDEN_ONLY
  for (i = 0; i < 3; i++) {
    exr_layout *page = (exr_layout *)(uintptr_t)1;
    OK(exr_pager_next(pager, &page, &error)); CHECK(!page);
    CHECK(exr_pager_position(pager) == size);
  }
  exr_pager_free(pager);
#endif
  exr_document_free(doc);
#ifndef EXR_PAGER_GOLDEN_ONLY
  /* Retained pages include images and must survive both their document and pager. */
  for (i = 0; i < n; i++) {
    CHECK(same(capture(pages[i], 0), snapshots[i]));
    exr_layout_free(pages[i]);
  }
  free(pages); free(snapshots); exr_free(map);
#endif
  exr_layout_free(whole);
}
#ifndef EXR_PAGER_GOLDEN_ONLY
static void lazy_single_paragraph(void) {
  exr_document *doc = text_document(1024 * 1024);
  exr_layout_config config = exr_layout_config_defaults();
  exr_pager *pager = NULL;
  exr_layout *page = NULL;
  size_t size, n;
  snapshot saved;
  exr_document_text(doc, &size);
  config.page = (exr_layout_options){160, 112, 8, 16, 1.25f, 0};
  OK(exr_pager_create(doc, font, &config, &pager, &error));
  CHECK(exr_pager_position(pager) < 1024);
  OK(exr_pager_next(pager, &page, &error)); CHECK(page);
  CHECK(exr_pager_position(pager) > 0 && exr_pager_position(pager) < size / 64);
  exr_layout_glyphs(page, &n); CHECK(n && n < 1024);
  saved = capture(page, 0);
  exr_pager_free(pager); exr_document_free(doc);
  CHECK(same(saved, capture(page, 0))); exr_layout_free(page);
}
static void zero_border(void) {
  construction c = {0};
  exr_document *doc;
  exr_pager *pager = NULL;
  exr_layout *whole = NULL;
  exr_layout_config config = exr_layout_config_defaults();
  size_t section, paragraph, i, count, pages;
  char text[513];
  for (i = 0; i < sizeof(text)-1; i++) text[i] = "AV a aV "[i % 8];
  text[sizeof(text)-1] = 0;
  add(&c, EXR_NODE_DOCUMENT, SIZE_MAX, NULL, NULL);
  add(&c, EXR_NODE_CHAPTER, 0, NULL, NULL);
  section = add(&c, EXR_NODE_SECTION, 1, NULL, "border:0px solid red");
  paragraph = add(&c, EXR_NODE_PARAGRAPH, section, NULL, "border:0px solid blue");
  add(&c, EXR_NODE_TEXT, paragraph, text, NULL);
  doc = finish(&c);
  config.page = (exr_layout_options){160, 112, 8, 16, 1.25f, 0};
  OK(exr_layout_create_ex(doc, font, &config, &whole, &error));
  exr_layout_pages(whole, &pages); CHECK(pages > 1);
  exr_layout_boxes(whole, &count); CHECK(!count);
  OK(exr_pager_create(doc, font, &config, &pager, &error));
  for (i = 0; i < pages; i++) {
    exr_layout *page = NULL;
    OK(exr_pager_next(pager, &page, &error)); CHECK(page);
    exr_layout_boxes(page, &count); CHECK(!count);
    compare_page(whole, i, page); exr_layout_free(page);
  }
  exr_pager_free(pager); exr_layout_free(whole); exr_document_free(doc);
}
static void table_position(void) {
  construction c = {0};
  exr_document *doc;
  exr_pager *pager = NULL;
  exr_layout *whole = NULL, *page = NULL;
  exr_layout_config config = exr_layout_config_defaults();
  size_t table, row, cell, i, size;
  add(&c, EXR_NODE_DOCUMENT, SIZE_MAX, NULL, NULL);
  add(&c, EXR_NODE_CHAPTER, 0, NULL, NULL);
  table = add(&c, EXR_NODE_TABLE, 1, NULL, NULL);
  for (i = 0; i < 20; i++) {
    row = add(&c, EXR_NODE_ROW, table, NULL, NULL);
    cell = add(&c, EXR_NODE_CELL, row, NULL, "padding:2px");
    add(&c, EXR_NODE_TEXT, cell, "AV a AV a AV a AV a AV a AV a AV a AV a AV a", NULL);
  }
  doc = finish(&c); exr_document_text(doc, &size);
  config.page = (exr_layout_options){160, 112, 8, 16, 1.25f, 0};
  OK(exr_layout_create_ex(doc, font, &config, &whole, &error));
  OK(exr_pager_create(doc, font, &config, &pager, &error));
  CHECK(!exr_pager_position(pager));
  OK(exr_pager_next(pager, &page, &error)); CHECK(page);
  CHECK(exr_pager_position(pager) > 0 && exr_pager_position(pager) < size);
  CHECK(exr_pager_position(pager) >= exr_layout_pages(page, NULL)->end);
  compare_page(whole, 0, page);
  exr_pager_free(pager); exr_document_free(doc);
  CHECK(pixels(page, 0, 0) == pixels(whole, 0, 0));
  exr_layout_free(page); exr_layout_free(whole);
}
static void validation(void) {
  exr_document *doc = text_document(20);
  exr_layout_config config = exr_layout_config_defaults();
  exr_pager *pager = (exr_pager *)(uintptr_t)1;
  exr_layout *page = (exr_layout *)(uintptr_t)1;
  CHECK(exr_pager_create(NULL, font, NULL, &pager, &error) == EXR_ARGUMENT && !pager);
  CHECK(exr_pager_create(doc, NULL, NULL, &pager, &error) == EXR_ARGUMENT && !pager);
  CHECK(exr_pager_create(doc, font, NULL, NULL, &error) == EXR_ARGUMENT);
  config.page.width = 0;
  CHECK(exr_pager_create(doc, font, &config, &pager, &error) == EXR_ARGUMENT && !pager);
  CHECK(exr_pager_next(NULL, &page, &error) == EXR_ARGUMENT && !page);
  OK(exr_pager_create(doc, font, NULL, &pager, &error));
  CHECK(exr_pager_next(pager, NULL, &error) == EXR_ARGUMENT);
  OK(exr_pager_next(pager, &page, &error)); CHECK(page);
  exr_layout_free(page); exr_pager_free(pager); exr_document_free(doc);
  exr_pager_free(NULL);
}
#endif
int main(int argc, char **argv) {
  exr_layout_config config = exr_layout_config_defaults();
  config.user_css="table {table-layout:fixed;width:100%}";
  FILE *records;
  CHECK(argc == 3);
  fixtures = argv[1]; load_fonts(argv[2]);
#ifdef EXR_PAGER_GOLDEN_ONLY
  records = stdout;
  CHECK(!strcmp(exr_version(), "0.10.0"));
#else
  {
    char path[4096];
    snprintf(path, sizeof(path), "%s/pager-golden.txt", fixtures);
    records = fopen(path, "rb"); CHECK(records);
  }
  validation();
#endif
  run_document(records, "layout-epub", open_book("layout.epub"), &config);
  config.page = (exr_layout_options){240, 240, 8, 16, 1.25f, 0};
  run_document(records, "host-nested", host_document(), &config);
  config.page = (exr_layout_options){120, 160, 8, 16, 1.25f, 0};
  run_document(records, "cross-style-clusters", cluster_document(), &config);
  config.page = (exr_layout_options){160, 112, 8, 16, 1.25f, 0};
  run_document(records, "txt-single-paragraph", text_document(4096), &config);
  config.page = (exr_layout_options){400, 320, 20, 24, 1.6f, 12};
  run_document(records, "table-pages", open_book("layout-table.epub"), &config);
  config.page.height = 300;
  run_document(records, "nested-padding", open_book("layout-padding.epub"), &config);
  run_document(records, "explicit-break", open_book("layout-break.epub"), &config);
#ifndef EXR_PAGER_GOLDEN_ONLY
  {
    char extra[2]; CHECK(fscanf(records, "%1s", extra) == EOF);
  }
  CHECK(!fclose(records)); lazy_single_paragraph(); zero_border(); table_position();
  printf("EXReader pager: %u checks passed\n", checks);
#endif
  exr_font_free(font);
  return 0;
}
