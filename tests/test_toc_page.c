/* SPDX-License-Identifier: MIT */
/* Synthetic TOC pages: pagination, indentation, leaders, right-aligned labels,
   hit testing back to exr_publication_locate, no-TOC books, search isolation. */
#include "exreader.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static exr_error error;
static unsigned checks;
static exr_font *font;
#define CHECK(x) do { checks++; if (!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while (0)
#define OK(x) CHECK((x)==EXR_OK)
static int near(float a, float b) { return fabsf(a - b) < 0.02f; }

static exr_layout_config config(float width, float height) {
  exr_layout_config c = exr_layout_config_defaults();
  c.page = (exr_layout_options){width, height, 12, 14, 1.5f, 6};
  return c;
}
static exr_publication *open_book(const char *dir, const char *file) {
  char path[4096]; exr_publication *p = NULL;
  CHECK(snprintf(path, sizeof(path), "%s/%s", dir, file) > 0);
  OK(exr_publication_open(path, &p, &error));
  return p;
}
static char labels_storage[200][8];
static const char *labels[200];
static void make_labels(size_t n) {
  size_t i;
  for (i = 0; i < n; i++) { snprintf(labels_storage[i], sizeof(labels_storage[i]), "%zu", 3 + i * 7); labels[i] = labels_storage[i]; }
}
static const exr_line *entry_line(const exr_layout *l, size_t page, size_t entry, size_t nth) {
  size_t i, count, seen = 0; const exr_line *lines = exr_layout_lines(l, &count); const exr_page *pages = exr_layout_pages(l, &count);
  for (i = pages[page].line_start; i < pages[page].line_start + pages[page].line_count; i++) {
    float cy = lines[i].y + lines[i].height / 2; size_t e = SIZE_MAX;
    OK(exr_toc_pages_entry_at(l, page, 0, cy, &e));
    if (e == entry && seen++ == nth) return &lines[i];
  }
  return NULL;
}

/* Every labelled row: dots are one contiguous grid and the label ends at the right margin. */
static void check_rows(const exr_layout *l, size_t n, float width, float margin) {
  size_t page, pages, entry, total = 0, gcount;
  const exr_glyph *glyphs = exr_layout_glyphs(l, &gcount);
  const exr_page *p = exr_layout_pages(l, &pages);
  (void)p;
  for (page = 0; page < pages; page++) {
    size_t first, count;
    OK(exr_toc_pages_entries(l, page, &first, &count));
    CHECK(count > 0 && first == total);
    total += count;
    for (entry = first; entry < first + count; entry++) {
      size_t nth = 0; const exr_line *line; int saw_label = 0;
      while ((line = entry_line(l, page, entry, nth++)) != NULL) {
        size_t k, dots = 0; float step = 0, prev = 0, last_right = 0, last_dot = -1, baseline = -1;
        for (k = 0; k < line->glyph_count; k++) {
          const exr_glyph *g = &glyphs[line->glyph_start + k];
          if (!(g->flags & EXR_GLYPH_HIDDEN)) { /* title, leaders and label share one baseline inside the line box */
            if (baseline < 0) baseline = g->baseline;
            CHECK(near(g->baseline, baseline));
            CHECK(g->baseline > line->y && g->baseline < line->y + line->height + 0.5f);
          }
          if (g->flags & EXR_GLYPH_GENERATED) {
            if (dots) CHECK(near(g->x - prev, g->advance) && near(g->advance, step));
            step = g->advance; prev = g->x; last_dot = g->x + g->advance; dots++;
          } else if (last_dot >= 0 && !saw_label) {
            /* label glyphs: first one starts after the last leader dot. */
            CHECK(g->x >= last_dot - 0.02f);
          }
          if (last_dot >= 0 && !(g->flags & EXR_GLYPH_GENERATED)) { last_right = g->x + g->advance; saw_label = 1; }
        }
        if (dots) { CHECK(dots >= 3); CHECK(near(last_right, width - margin)); }
      }
      CHECK(saw_label);
    }
  }
  CHECK(total == n);
}

static void pages_book(const char *dir) {
  exr_publication *p = open_book(dir, "toc-pages.epub");
  exr_layout_config c = config(420, 240); exr_layout *toc = NULL;
  exr_toc_page_options options; const exr_toc_entry *entries; size_t n, pages, i, gcount, lcount;
  const exr_glyph *glyphs; const exr_line *lines; size_t part;
  OK(exr_publication_toc(p, &entries, &n, &error)); CHECK(n == 70);
  make_labels(n);
  memset(&options, 0, sizeof(options));
  options.struct_size = sizeof(options); options.labels = labels; options.label_count = n;
  OK(exr_toc_pages_create(p, font, &c, &options, &toc, &error)); CHECK(toc);
  OK(exr_publication_toc_insert_before(p, &part, &error)); CHECK(part == 1); /* after the cover part */
  exr_layout_pages(toc, &pages);
  CHECK(pages >= 3);
  for (i = 0; i < pages; i++) CHECK(exr_layout_page_kind(toc, i) == EXR_PAGE_TOC);
  CHECK(exr_layout_page_kind(toc, pages) == EXR_PAGE_BODY);
  CHECK(!strcmp(exr_toc_pages_label(toc, 0), "i") && !strcmp(exr_toc_pages_label(toc, 2), "iii"));
  CHECK(exr_toc_pages_label(toc, pages) == NULL);
  check_rows(toc, n, c.page.width, c.page.margin);

  /* Heading on page 1, continued heading on later pages (Latin title for Latin entries). */
  glyphs = exr_layout_glyphs(toc, &gcount); lines = exr_layout_lines(toc, &lcount);
  {
    size_t pi, found_first = 0, found_cont = 0;
    for (pi = 0; pi < pages; pi++) {
      const exr_page *pg = &exr_layout_pages(toc, &i)[pi];
      const exr_line *head = &lines[pg->line_start];
      char text[64]; size_t k, at = 0;
      for (k = 0; k < head->glyph_count && at + 1 < sizeof(text); k++) text[at++] = (char)glyphs[head->glyph_start + k].codepoint;
      text[at] = 0;
      if (pi == 0 && !strcmp(text, "Contents")) found_first = 1;
      if (pi > 0 && !strcmp(text, "Contents (continued)")) found_cont++;
    }
    CHECK(found_first && found_cont == pages - 1);
  }

  /* Indentation: level two is exactly one em right of level one, titles are not paragraph-indented. */
  {
    const exr_line *one = entry_line(toc, 0, 0, 0), *two = entry_line(toc, 0, 1, 0);
    CHECK(one && two);
    CHECK(near(glyphs[two->glyph_start].x - glyphs[one->glyph_start].x, c.page.font_size));
    CHECK(near(glyphs[one->glyph_start].x, c.page.margin));
  }
  /* Single spacing: rows are packed at the font's natural line height, tighter than the 1.5 body pitch. */
  {
    const exr_line *a = entry_line(toc, 0, 0, 0), *b = entry_line(toc, 0, 1, 0), *d = entry_line(toc, 0, 2, 0);
    CHECK(near(b->y - a->y, a->height) && near(d->y - b->y, b->height));
    CHECK(a->height < c.page.font_size * c.page.line_height);
  }
  /* A wrapped title keeps one entry across several lines of the same page. */
  {
    size_t page = SIZE_MAX, k; const exr_line *w;
    for (k = 0; k < pages; k++) { size_t f, cnt; OK(exr_toc_pages_entries(toc, k, &f, &cnt)); if (f <= 5 && 5 < f + cnt) page = k; }
    CHECK(page != SIZE_MAX);
    CHECK(entry_line(toc, page, 5, 1) != NULL);
    w = entry_line(toc, page, 5, 0); CHECK(w);
  }
  /* Hit testing: row geometry and the ordinary offset hit test both resolve to the entry,
     and its target locates through the publication. */
  for (i = 0; i < n; i++) {
    size_t page, f, cnt, found = SIZE_MAX, e, offset; const exr_line *line; exr_location where;
    for (page = 0; page < pages; page++) { OK(exr_toc_pages_entries(toc, page, &f, &cnt)); if (i >= f && i < f + cnt) { found = page; break; } }
    CHECK(found != SIZE_MAX);
    line = entry_line(toc, found, i, 0); CHECK(line);
    OK(exr_toc_pages_entry_at(toc, found, 1, line->y + 1, &e)); CHECK(e == i);
    offset = exr_layout_hit_test(toc, found, line->x + 1, line->y + line->height / 2);
    CHECK(exr_toc_pages_entry_for_offset(toc, offset) == i);
    offset = exr_layout_hit_test(toc, found, c.page.width - c.page.margin - 1, line->y + line->height / 2);
    CHECK(exr_toc_pages_entry_for_offset(toc, offset) == i);
    OK(exr_publication_locate(p, &entries[i].target, &where, &error));
    CHECK(where.state == EXR_LINK_FOUND && where.part == 1);
  }
  {
    size_t e = 0;
    OK(exr_toc_pages_entry_at(toc, 0, 1, 1, &e)); CHECK(e == SIZE_MAX); /* heading */
  }
  /* Synthetic text never reaches the publication: the word exists only in the TOC. */
  {
    size_t part_count, pi, start, end, hits = 0, control = 0; const exr_part *parts = exr_publication_parts(p, &part_count);
    for (pi = 0; pi < part_count; pi++) {
      exr_document *d = NULL;
      if (!parts[pi].in_reading_order) continue; /* the nav document is an auxiliary part, not searched text */
      OK(exr_publication_load(p, pi, &d, &error));
      OK(exr_document_find(d, "Zyxwv", 0, &start, &end, &error)); if (start != SIZE_MAX) hits++;
      OK(exr_document_find(d, "Body paragraph", 0, &start, &end, &error)); if (start != SIZE_MAX) control++;
      exr_document_free(d);
    }
    CHECK(hits == 0 && control > 0); /* the search works, and finds nothing in synthetic pages */
    {
      size_t zcount = 0, k;
      for (k = 0; k + 4 < gcount; k++)
        if (glyphs[k].codepoint == 'Z' && glyphs[k + 1].codepoint == 'y' && glyphs[k + 4].codepoint == 'v') zcount++;
      CHECK(zcount >= n);
    }
  }
  exr_layout_free(toc);

  /* Narrow page: long titles leave no room, so the label gets a leader-only line. */
  {
    exr_layout_config narrow = config(180, 320);
    OK(exr_toc_pages_create(p, font, &narrow, &options, &toc, &error)); CHECK(toc);
    check_rows(toc, n, narrow.page.width, narrow.page.margin);
    exr_layout_free(toc);
  }
  /* Without labels: entries only, no leaders. */
  {
    exr_toc_page_options bare;
    memset(&bare, 0, sizeof(bare)); bare.struct_size = sizeof(bare);
    OK(exr_toc_pages_create(p, font, &c, &bare, &toc, &error)); CHECK(toc);
    glyphs = exr_layout_glyphs(toc, &gcount);
    for (i = 0; i < gcount; i++) CHECK(!(glyphs[i].flags & EXR_GLYPH_GENERATED));
    exr_layout_free(toc);
  }
  /* Argument validation. */
  {
    exr_toc_page_options bad = options;
    bad.label_count = n - 1;
    CHECK(exr_toc_pages_create(p, font, &c, &bad, &toc, &error) == EXR_ARGUMENT && !toc);
    bad = options; bad.struct_size = 1;
    CHECK(exr_toc_pages_create(p, font, &c, &bad, &toc, &error) == EXR_ARGUMENT && !toc);
  }
  exr_publication_free(p);
}

static void no_toc(const char *dir) {
  exr_publication *p = open_book(dir, "toc-pages-none.epub");
  exr_layout_config c = config(420, 240); exr_layout *toc = (exr_layout *)1; exr_toc_page_options options;
  size_t part;
  memset(&options, 0, sizeof(options)); options.struct_size = sizeof(options);
  OK(exr_toc_pages_create(p, font, &c, &options, &toc, &error)); CHECK(toc == NULL); /* no page, no empty page */
  OK(exr_publication_toc_insert_before(p, &part, &error)); CHECK(part == 0);
  exr_publication_free(p);
  p = open_book(dir, "toc-nav.epub");
  OK(exr_publication_toc_insert_before(p, &part, &error)); CHECK(part == 0); /* text first part is not a cover */
  exr_publication_free(p);
}

static void body_layouts_have_no_toc_kind(const char *dir) {
  exr_publication *p = open_book(dir, "toc-pages.epub");
  exr_layout_config c = config(420, 240); exr_document *d = NULL; exr_layout *l = NULL;
  OK(exr_publication_load(p, 1, &d, &error));
  OK(exr_layout_create_ex(d, font, &c, &l, &error));
  CHECK(exr_layout_page_kind(l, 0) == EXR_PAGE_BODY);
  CHECK(exr_toc_pages_label(l, 0) == NULL);
  exr_layout_free(l); exr_document_free(d); exr_publication_free(p);
}

int main(int argc, char **argv) {
  char path[4096];
  CHECK(argc == 2);
  snprintf(path, sizeof(path), "%s/fonts/primary.ttf", argv[1]);
  OK(exr_font_open(path, &font, &error));
  pages_book(argv[1]);
  no_toc(argv[1]);
  body_layouts_have_no_toc_kind(argv[1]);
  exr_font_free(font);
  printf("toc pages passed (%u checks)\n", checks);
  return 0;
}
