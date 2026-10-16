/* SPDX-License-Identifier: GPL-3.0-only */
#include "exreader.h"
#include <limits.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static exr_error error;
static unsigned checks;
static exr_font *font;
static const char *scenario;
#define CHECK(x) do { checks++; if (!(x)) { \
  fprintf(stderr, "%s line %d: %s (%d: %s)\n", scenario, __LINE__, #x, \
          (int)error.code, error.message); exit(1); } } while (0)
#define OK(x) CHECK((x) == EXR_OK)

enum { SPACE=1, A=2, V=3, FFI=6, FI=7, SMALL_A=8, ACUTE=15,
       BEH_INIT=20, BEH_MEDI=21, BEH_FINA=22, LAMALEF=31, FATHA=33,
       ALEF=36, BET=37, GIMEL=38, LEFT=39, RIGHT=40 };

static int near(float a, float b) { return isfinite(a) && fabsf(a - b) < 0.02f; }
static exr_layout_config config(void) {
  exr_layout_config c = exr_layout_config_defaults();
  c.page = (exr_layout_options){240, 200, 12, 20, 1.2f, 0};
  return c;
}
static exr_document *paragraph(const char *text, const char *style, const char *dir) {
  exr_attribute attrs[2];
  size_t n = 0;
  exr_node_input nodes[] = {
      {EXR_NODE_DOCUMENT, SIZE_MAX, NULL, NULL, NULL, 0},
      {EXR_NODE_CHAPTER, 0, NULL, NULL, NULL, 0},
      {EXR_NODE_PARAGRAPH, 1, NULL, NULL, attrs, 0},
      {EXR_NODE_TEXT, 2, NULL, text, NULL, 0}};
  exr_chapter_input chapter = {"inline", "inline.unit", 1, 1};
  exr_document_input input = {"Complex text", nodes, 4, &chapter, 1, NULL, 0};
  exr_document *doc = NULL;
  if (style) attrs[n++] = (exr_attribute){"style", style};
  if (dir) attrs[n++] = (exr_attribute){"dir", dir};
  nodes[2].attribute_count = n;
  OK(exr_document_create(&input, &doc, &error));
  return doc;
}
static exr_layout *layout(exr_document *doc, const exr_layout_config *c) {
  exr_layout *l = NULL;
  OK(exr_layout_create_ex(doc, font, c, &l, &error));
  CHECK(l);
  return l;
}
static void ranges(const exr_layout *l, size_t size) {
  const exr_page *pages;
  const exr_line *lines;
  const exr_glyph *g;
  size_t count, i, j, n;
  pages = exr_layout_pages(l, &count);
  lines = exr_layout_lines(l, NULL);
  g = exr_layout_glyphs(l, &n);
  for (i = 0; i < n; i++) {
    CHECK(g[i].start < g[i].end && g[i].end <= size);
    CHECK(g[i].cluster_start <= g[i].start && g[i].cluster_end >= g[i].end);
    CHECK(g[i].cluster_end <= size && g[i].page < count);
  }
  for (i = 0; i < count; i++) {
    size_t low = SIZE_MAX, high = 0;
    CHECK(pages[i].start <= pages[i].end && pages[i].end <= size);
    for (j = pages[i].line_start; j < pages[i].line_start + pages[i].line_count; j++) {
      const exr_line *line = &lines[j];
      size_t k, first = SIZE_MAX, last = 0;
      CHECK(line->page == i && line->glyph_count);
      for (k = line->glyph_start; k < line->glyph_start + line->glyph_count; k++) {
        if (g[k].start < first) first = g[k].start;
        if (g[k].end > last) last = g[k].end;
      }
      CHECK(line->start == first && line->end == last);
      if (first < low) low = first;
      if (last > high) high = last;
    }
    if (low != SIZE_MAX) CHECK(pages[i].start <= low && pages[i].end >= high);
  }
}
static void pixels_equal(const exr_layout *a, size_t ai, const exr_layout *b, size_t bi) {
  exr_bitmap x = {0}, y = {0};
  OK(exr_render_page_color(a, font, ai, &x, &error));
  OK(exr_render_page_color(b, font, bi, &y, &error));
  CHECK(x.width == y.width && x.height == y.height && x.stride == y.stride);
  CHECK(!memcmp(x.pixels, y.pixels, (size_t)x.stride * x.height));
  exr_bitmap_free(&x); exr_bitmap_free(&y);
}
static void compare_page(const exr_layout *all, size_t index, const exr_layout *part) {
  const exr_page *a = &exr_layout_pages(all, NULL)[index], *b;
  const exr_line *al = exr_layout_lines(all, NULL), *bl = exr_layout_lines(part, NULL);
  const exr_glyph *ag = exr_layout_glyphs(all, NULL), *bg = exr_layout_glyphs(part, NULL);
  const exr_box *ab = exr_layout_boxes(all, NULL), *bb = exr_layout_boxes(part, NULL);
  size_t count, i, j;
  b = exr_layout_pages(part, &count);
  CHECK(count == 1 && a->start == b->start && a->end == b->end);
  CHECK(a->line_count == b->line_count && a->box_count == b->box_count);
  for (i = 0; i < a->line_count; i++) {
    const exr_line *x = &al[a->line_start + i], *y = &bl[i];
    CHECK(x->start == y->start && x->end == y->end && x->glyph_count == y->glyph_count);
    CHECK(near(x->x, y->x) && near(x->y, y->y) && near(x->width, y->width) && near(x->height, y->height));
    for (j = 0; j < x->glyph_count; j++) {
      const exr_glyph *u = &ag[x->glyph_start + j], *v = &bg[y->glyph_start + j];
      CHECK(u->glyph == v->glyph && u->start == v->start && u->end == v->end);
      CHECK(u->cluster_start == v->cluster_start && u->cluster_end == v->cluster_end);
      CHECK(u->bidi_level == v->bidi_level && u->flags == v->flags && !v->page);
      CHECK(near(u->x, v->x) && near(u->baseline, v->baseline) && near(u->advance, v->advance));
      CHECK(near(u->offset_x, v->offset_x) && near(u->offset_y, v->offset_y));
    }
  }
  for (i = 0; i < a->box_count; i++) {
    const exr_box *u = &ab[a->box_start + i], *v = &bb[i];
    CHECK(u->kind == v->kind && u->node == v->node && u->start == v->start && u->end == v->end);
    CHECK(near(u->x, v->x) && near(u->y, v->y) && near(u->width, v->width) && near(u->height, v->height));
  }
  pixels_equal(all, index, part, 0);
}
static void glyph_order(const exr_layout *l, const unsigned *ids, const size_t *starts,
                          size_t count) {
  size_t i, n;
  const exr_glyph *g = exr_layout_glyphs(l, &n);
  CHECK(n == count);
  for (i = 0; i < n; i++) {
    CHECK(g[i].glyph == ids[i]);
    if (starts) CHECK(g[i].start == starts[i]);
    CHECK(!(g[i].flags & (EXR_GLYPH_HIDDEN | EXR_GLYPH_MISSING)));
    CHECK(g[i].flags & EXR_GLYPH_SHAPED);
    if (i) CHECK(g[i].x >= g[i - 1].x);
  }
}
static void directions(void) {
  exr_layout_config c = config();
  exr_document *doc;
  exr_layout *l;
  const exr_glyph *g;
  size_t count, i;
  static const unsigned mixed_ids[] = {A, SPACE, BET, ALEF, SPACE, V};
  static const size_t mixed_starts[] = {0, 1, 4, 2, 6, 7};
  static const unsigned rtl_ids[] = {A, SPACE, BET, ALEF};
  static const size_t rtl_starts[] = {5, 4, 2, 0};
  static const unsigned ltr_ids[] = {BET, ALEF, SPACE, A};
  static const size_t ltr_starts[] = {2, 0, 4, 5};
  scenario = "mixed directions";
  doc = paragraph("A \xd7\x90\xd7\x91 V", NULL, NULL);
  l = layout(doc, &c); glyph_order(l, mixed_ids, mixed_starts, 6); ranges(l, 8);
  exr_layout_free(l); exr_document_free(doc);
  for (i = 0; i < 5; i++) {
    const char *dir = i == 3 ? "rtl" : i == 4 ? "ltr" : NULL;
    c.direction = i == 1 || i == 3 ? EXR_DIRECTION_LTR : i == 0 ? EXR_DIRECTION_AUTO : EXR_DIRECTION_RTL;
    doc = paragraph("\xd7\x90\xd7\x91 A", NULL, dir);
    l = layout(doc, &c);
    glyph_order(l, i == 1 || i == 4 ? ltr_ids : rtl_ids,
                   i == 1 || i == 4 ? ltr_starts : rtl_starts, 4);
    exr_layout_free(l); exr_document_free(doc);
  }
  c = config();
  doc = paragraph("(\xd7\x90\xd7\x91)", NULL, NULL);
  l = layout(doc, &c);
  {
    const unsigned ids[] = {LEFT, BET, ALEF, RIGHT};
    const size_t starts[] = {5, 3, 1, 0};
    glyph_order(l, ids, starts, 4);
  }
  exr_layout_free(l); exr_document_free(doc);
  scenario = "Arabic forms and RTL hit testing";
  doc = paragraph("\xd8\xa8\xd8\xa8\xd8\xa8", NULL, NULL);
  l = layout(doc, &c);
  {
    const unsigned ids[] = {BEH_FINA, BEH_MEDI, BEH_INIT};
    const size_t starts[] = {4, 2, 0};
    glyph_order(l, ids, starts, 3);
  }
  g = exr_layout_glyphs(l, &count);
  for (i = 0; i < count; i++) {
    CHECK(g[i].bidi_level & 1);
    CHECK(near(g[i].advance, 12));
    CHECK(exr_layout_hit_test(l, 0, g[i].x + 3, g[i].baseline - 2) == g[i].cluster_end);
    CHECK(exr_layout_hit_test(l, 0, g[i].x + 9, g[i].baseline - 2) == g[i].cluster_start);
  }
  ranges(l, 6);
  exr_layout_free(l); exr_document_free(doc);
  doc = paragraph("\xd9\x84\xd8\xa7", NULL, NULL);
  l = layout(doc, &c); g = exr_layout_glyphs(l, &count);
  CHECK(count == 1 && g[0].glyph == LAMALEF && near(g[0].advance, 14));
  CHECK(!g[0].start && g[0].end == 4 && !g[0].cluster_start && g[0].cluster_end == 4);
  exr_layout_free(l); exr_document_free(doc);
}
static unsigned ink(const exr_bitmap *b, int left, int top, int right, int bottom) {
  int x, y;
  unsigned count = 0;
  for (y = top; y < bottom; y++)
    for (x = left; x < right; x++)
      if (x >= 0 && y >= 0 && (unsigned)x < b->width && (unsigned)y < b->height &&
          b->pixels[(size_t)y * b->stride + (size_t)x * b->channels] < 240)
        count++;
  return count;
}
static void marks_and_controls(void) {
  exr_layout_config c = config();
  exr_document *doc, *plain;
  exr_layout *l, *base;
  exr_bitmap marked = {0}, unmarked = {0};
  const exr_glyph *g;
  size_t count, i, hidden = 0;
  int x, y;
  scenario = "mark offsets and actual pixels";
  doc = paragraph("a\xcc\x81", NULL, NULL); plain = paragraph("a", NULL, NULL);
  l = layout(doc, &c); base = layout(plain, &c);
  g = exr_layout_glyphs(l, &count);
  CHECK(count == 2 && g[0].glyph == SMALL_A && g[1].glyph == ACUTE);
  CHECK(near(g[1].offset_x, -4) && near(g[1].offset_y, 14) && near(g[1].advance, 0));
  CHECK(g[0].cluster_start == g[1].cluster_start && g[0].cluster_end == g[1].cluster_end);
  OK(exr_render_page(l, font, 0, &marked, &error));
  OK(exr_render_page(base, font, 0, &unmarked, &error));
  x = (int)lroundf(g[1].x + g[1].offset_x);
  y = (int)lroundf(g[1].baseline - g[1].offset_y);
  CHECK(ink(&marked, x, y - 10, x + 3, y));
  CHECK(!ink(&unmarked, x, y - 10, x + 3, y));
  exr_bitmap_free(&marked); exr_bitmap_free(&unmarked);
  ranges(l, 3);
  exr_layout_free(l); exr_layout_free(base); exr_document_free(doc); exr_document_free(plain);
  scenario = "invisible directional controls";
  doc = paragraph("a\xe2\x81\xa6" "b\xe2\x81\xa9" "c", NULL, NULL);
  plain = paragraph("abc", NULL, NULL);
  l = layout(doc, &c); base = layout(plain, &c);
  g = exr_layout_glyphs(l, &count);
  for (i = 0; i < count; i++)
    if (g[i].flags & EXR_GLYPH_HIDDEN) { hidden++; CHECK(near(g[i].advance, 0)); }
  CHECK(hidden == 2);
  pixels_equal(l, 0, base, 0);
  exr_layout_free(l); exr_layout_free(base); exr_document_free(doc); exr_document_free(plain);
  {
    const char *controls[] = {"a\xe2\x80\x8d" "b", "a\xc2\xad" "b",
                              "a\xe2\x80\xaa" "b\xe2\x80\xac" "c"};
    const char *visible[] = {"ab", "ab", "abc"};
    const size_t counts[] = {3, 3, 5};
    for (i = 0; i < sizeof(controls) / sizeof(*controls); i++) {
      size_t j, invisible = 0;
      doc = paragraph(controls[i], NULL, NULL); plain = paragraph(visible[i], NULL, NULL);
      l = layout(doc, &c); base = layout(plain, &c);
      g = exr_layout_glyphs(l, &count);
      CHECK(count == counts[i]);
      for (j = 0; j < count; j++)
        if (g[j].flags & EXR_GLYPH_HIDDEN) { invisible++; CHECK(near(g[j].advance, 0)); }
      CHECK(invisible == counts[i] - strlen(visible[i]));
      ranges(l, strlen(controls[i]));
      pixels_equal(l, 0, base, 0);
      exr_layout_free(l); exr_layout_free(base); exr_document_free(doc); exr_document_free(plain);
    }
  }
}
static void ligature_wrap(void) {
  exr_layout_config c = config();
  exr_document *doc;
  exr_layout *l;
  const exr_glyph *g;
  const exr_line *lines;
  size_t n;
  scenario = "shape before width wrapping";
  doc = paragraph("ffiffi", "width:15px;margin:0", NULL);
  l = layout(doc, &c); g = exr_layout_glyphs(l, &n);
  CHECK(n == 2 && g[0].glyph == FFI && g[1].glyph == FFI);
  CHECK(near(g[0].advance, 15) && near(g[1].advance, 15));
  lines = exr_layout_lines(l, &n);
  CHECK(n == 2 && lines[0].glyph_count == 1 && lines[1].glyph_count == 1);
  CHECK(lines[0].start == 0 && lines[0].end == 3 && lines[1].start == 3 && lines[1].end == 6);
  ranges(l, 6);
  exr_layout_free(l); exr_document_free(doc);
  doc = paragraph("AV", "width:22px;margin:0", NULL);
  l = layout(doc, &c); g = exr_layout_glyphs(l, &n);
  CHECK(n == 2 && g[0].glyph == A && g[1].glyph == V);
  CHECK(near(g[0].advance, 10) && near(g[1].advance, 12));
  lines = exr_layout_lines(l, &n); CHECK(n == 1 && near(lines[0].width, 22));
  exr_layout_free(l); exr_document_free(doc);
  scenario = "narrow RTL lines keep cluster groups";
  doc = paragraph("\xd7\x90\xd7\x91\xd7\x92", "width:25px;margin:0", NULL);
  l = layout(doc, &c); g = exr_layout_glyphs(l, &n);
  CHECK(n == 3 && g[0].glyph == BET && g[1].glyph == ALEF && g[2].glyph == GIMEL);
  lines = exr_layout_lines(l, &n);
  CHECK(n == 2 && lines[0].start == 0 && lines[0].end == 4 && lines[1].start == 4 && lines[1].end == 6);
  ranges(l, 6); exr_layout_free(l); exr_document_free(doc);
  doc = paragraph("\xd9\x84\xd8\xa7\xd9\x84\xd8\xa7", "width:10px;margin:0", NULL);
  l = layout(doc, &c); g = exr_layout_glyphs(l, &n);
  CHECK(n == 2 && g[0].glyph == LAMALEF && g[1].glyph == LAMALEF);
  lines = exr_layout_lines(l, &n);
  CHECK(n == 2 && lines[0].start == 0 && lines[0].end == 4 && lines[1].start == 4 && lines[1].end == 8);
  ranges(l, 8); exr_layout_free(l); exr_document_free(doc);
}
static void line_oracle(const exr_document *doc, const exr_layout *l, exr_direction dir) {
  exr_bidi *bidi = NULL;
  const exr_bidi_scalar *scalars;
  const exr_glyph *g = exr_layout_glyphs(l, NULL);
  const exr_line *lines;
  const char *text;
  size_t size, n, count, i, j;
  text = exr_document_text(doc, &size);
  OK(exr_bidi_analyze(text, size, dir, &bidi, &error));
  scalars = exr_bidi_scalars(bidi, &count);
  lines = exr_layout_lines(l, &n);
  for (i = 0; i < n; i++) {
    size_t first = 0, last, *order = NULL, visual;
    while (first < count && scalars[first].start < lines[i].start) first++;
    last = first;
    while (last < count && scalars[last].start < lines[i].end) last++;
    OK(exr_bidi_reorder(bidi, first, last - first, &order, &visual, &error));
    CHECK(visual == lines[i].glyph_count);
    for (j = 0; j < visual; j++)
      CHECK(g[lines[i].glyph_start + j].start == scalars[order[j]].start);
    exr_free(order);
  }
  exr_bidi_free(bidi);
}
static void style_and_l1(void) {
  exr_layout_config c = config();
  exr_document *doc = NULL;
  exr_layout *l;
  const exr_glyph *g;
  const exr_line *lines;
  size_t n;
  exr_attribute red = {"style", "color:#112233"}, blue = {"style", "color:#aa5500"};
  exr_node_input nodes[] = {
      {EXR_NODE_DOCUMENT, SIZE_MAX, NULL, NULL, NULL, 0},
      {EXR_NODE_CHAPTER, 0, NULL, NULL, NULL, 0},
      {EXR_NODE_PARAGRAPH, 1, NULL, NULL, NULL, 0},
      {EXR_NODE_ELEMENT, 2, NULL, NULL, &red, 1},
      {EXR_NODE_TEXT, 3, NULL, "a", NULL, 0},
      {EXR_NODE_ELEMENT, 2, NULL, NULL, &blue, 1},
      {EXR_NODE_TEXT, 5, NULL, "\xcc\x81" "b", NULL, 0}};
  exr_chapter_input chapter = {"colors", "colors.unit", 1, 1};
  exr_document_input input = {"Cluster colors", nodes, 7, &chapter, 1, NULL, 0};
  scenario = "cross-style cluster uses its first style";
  OK(exr_document_create(&input, &doc, &error));
  l = layout(doc, &c); g = exr_layout_glyphs(l, &n);
  CHECK(n == 3 && g[0].glyph == SMALL_A && g[1].glyph == ACUTE);
  CHECK(g[0].color == 0x112233ff && g[1].color == 0x112233ff && g[2].color == 0xaa5500ff);
  CHECK(near(g[1].offset_x, -4) && near(g[1].offset_y, 14));
  ranges(l, 4); exr_layout_free(l); exr_document_free(doc);
  scenario = "wrapped RTL whitespace L1";
  c.direction = EXR_DIRECTION_RTL;
  doc = paragraph("A b c \xd7\x90\xd7\x91", "width:17px;margin:0", NULL);
  l = layout(doc, &c); g = exr_layout_glyphs(l, &n);
  lines = exr_layout_lines(l, &n);
  CHECK(n >= 3 && lines[0].glyph_count == 2 && lines[0].start == 0 && lines[0].end == 2);
  CHECK(g[0].glyph == SPACE && g[0].bidi_level == 1 && g[1].glyph == A && g[1].bidi_level == 2);
  line_oracle(doc, l, EXR_DIRECTION_RTL);
  ranges(l, 10); exr_layout_free(l); exr_document_free(doc);
  doc = paragraph("\xd7\x90\xd7\x91", "text-align:start", NULL);
  l = layout(doc, &c); lines = exr_layout_lines(l, NULL);
  CHECK(near(lines[0].x + lines[0].width, c.page.width - c.page.margin));
  exr_layout_free(l); exr_document_free(doc);
  doc = paragraph("\xd7\x90\xd7\x91", "text-align:end", NULL);
  l = layout(doc, &c); lines = exr_layout_lines(l, NULL);
  CHECK(near(lines[0].x, c.page.margin));
  exr_layout_free(l); exr_document_free(doc);
}
static void pagination(exr_document *doc, const exr_layout_config *c, int oracle) {
  exr_layout *all = layout(doc, c), *page = NULL;
  exr_pager *pager = NULL;
  const exr_layout *cached = NULL;
  size_t n, i, size;
  exr_layout_pages(all, &n); CHECK(n >= 2);
  exr_document_text(doc, &size); ranges(all, size);
  if (oracle) line_oracle(doc, all, c->direction);
  OK(exr_pager_create(doc, font, c, &pager, &error));
  for (i = 0; i < n; i++) {
    OK(exr_pager_next(pager, &page, &error)); CHECK(page);
    compare_page(all, i, page); ranges(page, size);
    exr_layout_free(page);
  }
  OK(exr_pager_next(pager, &page, &error)); CHECK(!page);
  exr_pager_free(pager);
  OK(exr_pager_create(doc, font, c, &pager, &error));
  OK(exr_pager_set_cache(pager, 1, 128 * 1024, &error));
  OK(exr_pager_get(pager, n - 1, &cached, &error)); compare_page(all, n - 1, cached);
  OK(exr_pager_get(pager, 0, &cached, &error)); compare_page(all, 0, cached);
  OK(exr_pager_get(pager, 1, &cached, &error)); compare_page(all, 1, cached);
  exr_pager_free(pager); exr_layout_free(all);
}
static exr_document *table_document(void) {
  exr_node_input nodes[43] = {
      {EXR_NODE_DOCUMENT, SIZE_MAX, NULL, NULL, NULL, 0},
      {EXR_NODE_CHAPTER, 0, NULL, NULL, NULL, 0}};
  exr_attribute table_attrs[] = {{"style", "display:table;width:96px"}, {"dir", "rtl"}};
  exr_attribute cell_attr = {"style", "padding:2px;line-height:24px"};
  exr_chapter_input chapter = {"table", "table.unit", 1, 1};
  exr_document_input input = {"Shaped table", nodes, 0, &chapter, 1, NULL, 0};
  exr_document *doc = NULL;
  size_t n = 3, row, cell, i;
  nodes[2] = (exr_node_input){EXR_NODE_ELEMENT, 1, NULL, NULL, table_attrs, 2};
  for (i = 0; i < 8; i++) {
    row = n; nodes[n++] = (exr_node_input){EXR_NODE_ROW, 2, NULL, NULL, NULL, 0};
    cell = n; nodes[n++] = (exr_node_input){EXR_NODE_CELL, row, NULL, NULL, &cell_attr, 1};
    nodes[n++] = (exr_node_input){EXR_NODE_TEXT, cell, NULL, "fi \xd7\x90\xd7\x91", NULL, 0};
    cell = n; nodes[n++] = (exr_node_input){EXR_NODE_CELL, row, NULL, NULL, &cell_attr, 1};
    nodes[n++] = (exr_node_input){EXR_NODE_TEXT, cell, NULL, "\xd8\xa8\xd9\x8e\xd8\xa8 ffi", NULL, 0};
  }
  CHECK(n == sizeof(nodes) / sizeof(*nodes)); input.node_count = n;
  OK(exr_document_create(&input, &doc, &error));
  return doc;
}
static void pagers_and_tables(void) {
  exr_layout_config c = config();
  exr_document *doc;
  char text[1601];
  const char unit[] = "A \xd7\x90\xd7\x91 ";
  size_t at = 0, i, n;
  exr_layout *l;
  const exr_glyph *g;
  const exr_box *boxes, *left = NULL, *right = NULL;
  int fi = 0, ffi = 0, init = 0, final = 0, mark = 0;
  scenario = "paragraph bidi context through narrow pages";
  for (i = 0; i < 200; i++) { memcpy(text + at, unit, sizeof(unit) - 1); at += sizeof(unit) - 1; }
  text[at] = 0;
  c.page = (exr_layout_options){120, 80, 8, 20, 1.2f, 0};
  doc = paragraph(text, "width:30px;margin:0", NULL);
  pagination(doc, &c, 1); exr_document_free(doc);
  c.direction = EXR_DIRECTION_RTL;
  doc = paragraph(text, "width:30px;margin:0", NULL);
  pagination(doc, &c, 1); exr_document_free(doc);
  scenario = "table cell previews with bidi and shaping";
  c = config(); c.page = (exr_layout_options){200, 100, 8, 20, 1.2f, 0};
  doc = table_document(); l = layout(doc, &c);
  g = exr_layout_glyphs(l, &n);
  for (i = 0; i < n; i++) {
    fi |= g[i].glyph == FI; ffi |= g[i].glyph == FFI;
    init |= g[i].glyph == BEH_INIT; final |= g[i].glyph == BEH_FINA;
    mark |= g[i].glyph == FATHA && near(g[i].offset_x, -6) && near(g[i].offset_y, 12);
  }
  CHECK(fi && ffi && init && final && mark);
  boxes = exr_layout_boxes(l, &n);
  for (i = 0; i < n; i++)
    if (boxes[i].kind == EXR_BOX_CELL) {
      if (boxes[i].node == 4) left = &boxes[i];
      if (boxes[i].node == 6) right = &boxes[i];
    }
  CHECK(left && right && near(left->y, right->y) && right->x - left->x >= 45);
  exr_layout_free(l);
  pagination(doc, &c, 0); exr_document_free(doc);
}
static void write_sample(const char *path) {
  exr_layout_config c = config();
  exr_document *doc;
  exr_layout *l;
  exr_bitmap bitmap = {0};
  scenario = "optional deterministic render";
  c.page = (exr_layout_options){720, 220, 24, 32, 2, 0};
  doc = paragraph("ffi a\xcc\x81 AV \xd7\x90\xd7\x91\xd7\x92 \xd8\xa8\xd8\xa8\xd8\xa8 "
                  "\xd8\xa8\xd9\x8e\xd8\xa8 \xd9\x84\xd8\xa7", "color:#143a5a", NULL);
  l = layout(doc, &c);
  OK(exr_render_page_color(l, font, 0, &bitmap, &error));
  OK(exr_bitmap_write_png(&bitmap, path, &error));
  exr_bitmap_free(&bitmap); exr_layout_free(l); exr_document_free(doc);
}
int main(int argc, char **argv) {
  char path[4096];
  scenario = "setup"; CHECK(argc == 2 || argc == 3);
  CHECK(snprintf(path, sizeof(path), "%s/shaping.ttf", argv[1]) > 0);
  OK(exr_font_open(path, &font, &error));
  directions(); marks_and_controls(); ligature_wrap(); style_and_l1(); pagers_and_tables();
  if (argc == 3) write_sample(argv[2]);
  exr_font_free(font);
  printf("%u complex layout integration checks passed\n", checks);
  return 0;
}
