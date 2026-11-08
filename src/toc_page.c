/* SPDX-License-Identifier: MIT */
/* Synthetic table-of-contents pages.
   The text stack does all shaping and line breaking: the entries, labels, headings
   and leader glyphs are first laid out as ordinary paragraphs of a private
   document (exr_layout_create_ex). Only the final row/page assembly is done here:
   leader dots, right-aligned labels, pagination and repeated headings are
   composed into a positioned layout from those glyphs. */
#include "layout_internal.h"
#include <stdio.h>
#include <string.h>

#define TOC_LABEL_MAX 32
#define TOC_MAX_ENTRIES 100000
#define TOC_MAX_INDENT 12

struct exr_toc_meta {
  size_t entries, lines, pages;
  size_t *line_entry;                 /* positioned line -> entry (SIZE_MAX: heading) */
  size_t *title_start, *title_end;    /* per entry, synthetic text offsets */
  size_t *label_start, *label_end;    /* SIZE_MAX when the entry has no label */
  size_t *page_first, *page_count;    /* entries per page */
  char (*roman)[16];
};

void exr_toc_meta_free(struct exr_toc_meta *m) {
  if (!m) return;
  free(m->line_entry); free(m->title_start); free(m->title_end);
  free(m->label_start); free(m->label_end); free(m->page_first); free(m->page_count);
  free(m->roman); free(m);
}

exr_page_kind exr_layout_page_kind(const exr_layout *l, size_t page) {
  return l && l->toc && page < l->page_count ? EXR_PAGE_TOC : EXR_PAGE_BODY;
}
const char *exr_toc_pages_label(const exr_layout *l, size_t page) {
  return l && l->toc && page < l->toc->pages ? l->toc->roman[page] : NULL;
}
exr_status exr_toc_pages_entries(const exr_layout *l, size_t page, size_t *first, size_t *count) {
  if (first) *first = 0;
  if (count) *count = 0;
  if (!l || !l->toc || page >= l->toc->pages) return EXR_ARGUMENT;
  if (first) *first = l->toc->page_first[page];
  if (count) *count = l->toc->page_count[page];
  return EXR_OK;
}
exr_status exr_toc_pages_entry_at(const exr_layout *l, size_t page, float x, float y, size_t *entry) {
  size_t i;
  (void)x;
  if (entry) *entry = SIZE_MAX;
  if (!l || !l->toc || !entry || page >= l->page_count) return EXR_ARGUMENT;
  for (i = l->pages[page].line_start; i < l->pages[page].line_start + l->pages[page].line_count; i++)
    if (l->lines[i].page == page && y >= l->lines[i].y && y < l->lines[i].y + l->lines[i].height) {
      *entry = l->toc->line_entry[i];
      break;
    }
  return EXR_OK;
}
size_t exr_toc_pages_entry_for_offset(const exr_layout *l, size_t offset) {
  size_t lo = 0, hi, mid;
  const struct exr_toc_meta *m;
  if (!l || !l->toc) return SIZE_MAX;
  m = l->toc; hi = m->entries;
  while (lo < hi) { /* Title ranges ascend; the last start <= offset. */
    mid = lo + (hi - lo) / 2;
    if (m->title_start[mid] <= offset) lo = mid + 1; else hi = mid;
  }
  if (lo) {
    size_t i = lo - 1;
    if (offset <= m->title_end[i]) return i;
  }
  for (lo = 0; lo < m->entries; lo++) /* Labels follow the same entry order. */
    if (m->label_start[lo] != SIZE_MAX && offset >= m->label_start[lo] && offset <= m->label_end[lo]) return lo;
  return SIZE_MAX;
}

static int is_cover_name(const char *s) {
  const char *base, *p;
  char lower[256]; size_t n = 0;
  if (!s) return 0;
  base = strrchr(s, '/'); base = base ? base + 1 : s;
  for (p = base; *p && n + 1 < sizeof(lower); p++) lower[n++] = (*p >= 'A' && *p <= 'Z') ? (char)(*p + 32) : *p;
  lower[n] = 0;
  return strstr(lower, "cover") != NULL ||
         strstr(lower, "\xe8\xa1\xa8\xe7\xb4\x99") != NULL || /* U+8868 U+7D19 */
         strstr(lower, "\xe8\xa1\xa8\xe7\xba\xb8") != NULL || /* U+8868 U+7EB8 */
         strstr(lower, "\xe5\xb0\x81\xe9\x9d\xa2") != NULL;   /* U+5C01 U+9762 */
}

exr_status exr_publication_toc_insert_before(exr_publication *p, size_t *part, exr_error *e) {
  const exr_part *parts; size_t count, i;
  if (part) *part = SIZE_MAX;
  if (!p || !part) return exr_fail(e, EXR_ARGUMENT, "Missing publication or output");
  parts = exr_publication_parts(p, &count);
  for (i = 0; i < count && !parts[i].in_reading_order; i++);
  if (i == count) return EXR_OK;
  *part = i;
  if (is_cover_name(parts[i].id) || is_cover_name(parts[i].path)) {
    size_t j;
    for (j = i + 1; j < count && !parts[j].in_reading_order; j++);
    *part = j < count ? j : SIZE_MAX;
    return EXR_OK;
  }
  {
    exr_document *d = NULL; size_t n, k, nodes, images = 0; const exr_node *node; const char *text;
    exr_status status = exr_publication_load(p, i, &d, e);
    if (status != EXR_OK) return status;
    text = exr_document_text(d, &n);
    for (k = 0; k < n && (text[k] == ' ' || text[k] == '\n' || text[k] == '\t' || text[k] == '\r'); k++);
    node = exr_document_nodes(d, &nodes);
    for (k = 0; k < nodes; k++) if (node[k].kind == EXR_NODE_IMAGE) images++;
    {
      size_t j = i + 1;
      int cover = images > 0 && (n == 0 || k == n);
      exr_document_free(d);
      if (cover) {
        while (j < count && !parts[j].in_reading_order) j++;
        *part = j < count ? j : SIZE_MAX;
      }
    }
  }
  return EXR_OK;
}

typedef struct { exr_node_input *nodes; exr_attribute *attrs; char (*styles)[160]; size_t count, cap; } doc_builder;
static size_t add_node(doc_builder *b, exr_node_kind kind, size_t parent, const char *name,
                       const char *text, const char *style) {
  size_t i = b->count++;
  b->nodes[i] = (exr_node_input){kind, parent, name, text, NULL, 0};
  if (style) {
    snprintf(b->styles[i], sizeof(b->styles[i]), "%s", style);
    b->attrs[i] = (exr_attribute){"style", b->styles[i]};
    b->nodes[i].attributes = &b->attrs[i]; b->nodes[i].attribute_count = 1;
  }
  return i;
}
static size_t add_block(doc_builder *b, size_t chapter, exr_node_kind kind, const char *name,
                        const char *text, const char *style) {
  size_t block = add_node(b, kind, chapter, name, NULL, NULL);
  if (style) {
    snprintf(b->styles[block], sizeof(b->styles[block]), "%s", style);
    b->attrs[block] = (exr_attribute){"style", b->styles[block]};
    b->nodes[block].attributes = &b->attrs[block]; b->nodes[block].attribute_count = 1;
  }
  add_node(b, EXR_NODE_TEXT, block, NULL, text, NULL);
  return block;
}

static int has_cjk(const exr_toc_entry *toc, size_t count) {
  size_t i, j;
  for (i = 0; i < count && i < 16; i++)
    for (j = 0; toc[i].title && toc[i].title[j]; j++)
      if ((unsigned char)toc[i].title[j] >= 0xe3 && (unsigned char)toc[i].title[j] <= 0xe9) return 1;
  return 0;
}
static void roman(size_t n, char out[16]) {
  static const struct { unsigned v; const char *s; } t[] = {
    {1000, "m"}, {900, "cm"}, {500, "d"}, {400, "cd"}, {100, "c"}, {90, "xc"},
    {50, "l"}, {40, "xl"}, {10, "x"}, {9, "ix"}, {5, "v"}, {4, "iv"}, {1, "i"}};
  size_t i, at = 0;
  if (n == 0 || n > 3999) { snprintf(out, 16, "%u", (unsigned)(n % 1000000000u)); return; }
  for (i = 0; i < sizeof(t) / sizeof(*t); i++)
    while (n >= t[i].v && at + 5 < 16) { size_t k = strlen(t[i].s); memcpy(out + at, t[i].s, k); at += k; n -= t[i].v; }
  out[at] = 0;
}

typedef struct {
  exr_glyph *glyphs; size_t glyph_count, glyph_cap;
  exr_line *lines; size_t line_count, line_cap;
  size_t *line_entry; size_t entry_cap;
  exr_paint *paints; size_t paint_count, paint_cap;
  exr_positioned_page *pages; size_t page_count, page_cap;
  size_t *page_first, *page_entries, page_meta_cap, page_entries_cap;
} assembly;
static int grow(void **array, size_t *cap, size_t count, size_t unit) {
  void *next; size_t cap2;
  if (count < *cap) return 1;
  cap2 = *cap ? *cap * 2 : 256;
  next = realloc(*array, cap2 * unit);
  if (!next) return 0;
  *array = next; *cap = cap2; return 1;
}
static void assembly_free(assembly *a) {
  free(a->glyphs); free(a->lines); free(a->line_entry); free(a->paints); free(a->pages);
  free(a->page_first); free(a->page_entries);
}
typedef struct { size_t first, count; } span;
typedef struct {
  const exr_line *fl; const exr_glyph *fg;
  const span *spans; size_t n;
  const struct exr_toc_meta *meta;
  float margin, Wc, Hc, fs;
  const exr_glyph *dot; float dot_adv;
  assembly a;
  float y;
  size_t src_min, src_max, page_line_start, page_paint_start;
  size_t row_node;
} ctx;
#define HEAD(c) ((c)->spans[0])
#define ROW(c, i) ((c)->spans[1 + (i)])
#define CONT(c) ((c)->spans[1 + (c)->n])
#define LABEL(c, i) ((c)->spans[1 + (c)->n + 3 + (i)])

static int push_glyph(ctx *c, const exr_glyph *source, float dx, float dy) {
  assembly *a = &c->a; exr_glyph g = *source;
  if (!grow((void **)&a->glyphs, &a->glyph_cap, a->glyph_count, sizeof(*a->glyphs)) ||
      !grow((void **)&a->paints, &a->paint_cap, a->paint_count, sizeof(*a->paints))) return 0;
  g.x += dx; g.baseline += dy; g.clip_left += dx; g.clip_right += dx; g.page = a->page_count - 1;
  a->paints[a->paint_count++] = (exr_paint){EXR_PAINT_GLYPH, 0, a->glyph_count};
  a->glyphs[a->glyph_count++] = g;
  return 1;
}
static int push_line(ctx *c, exr_line line, size_t entry) {
  assembly *a = &c->a;
  if (!grow((void **)&a->lines, &a->line_cap, a->line_count, sizeof(*a->lines)) ||
      !grow((void **)&a->line_entry, &a->entry_cap, a->line_count, sizeof(size_t))) return 0;
  line.page = a->page_count - 1;
  if (line.start < c->src_min) c->src_min = line.start;
  if (line.end > c->src_max) c->src_max = line.end;
  a->line_entry[a->line_count] = entry; a->lines[a->line_count++] = line;
  return 1;
}
static void close_page(ctx *c) {
  assembly *a = &c->a; exr_positioned_page *p;
  if (!a->page_count) return;
  p = &a->pages[a->page_count - 1];
  p->content.start = c->src_min == SIZE_MAX ? 0 : c->src_min; p->content.end = c->src_max;
  p->content.line_start = c->page_line_start; p->content.line_count = a->line_count - c->page_line_start;
  p->paint_start = c->page_paint_start; p->paint_count = a->paint_count - c->page_paint_start;
}
/* Heading lines: the flowed glyphs moved to the running y. */
static int emit_plain(ctx *c, span group) {
  size_t k, l;
  for (l = 0; l < group.count; l++) {
    const exr_line *src = &c->fl[group.first + l]; exr_line out = *src; float dy = c->y - src->y; /* glyph baselines are page-absolute, x/y of the new page are content-relative */
    out.x -= c->margin; out.y = c->y; out.glyph_start = c->a.glyph_count;
    for (k = 0; k < src->glyph_count; k++)
      if (!push_glyph(c, &c->fg[src->glyph_start + k], -c->margin, dy)) return 0;
    if (!push_line(c, out, SIZE_MAX)) return 0;
    c->y += src->height;
  }
  c->y += c->fs * 0.5f;
  return 1;
}
static int start_page(ctx *c, span heading, size_t first_entry) {
  assembly *a = &c->a; exr_positioned_page *p;
  if (a->page_count >= 10000 ||
      !grow((void **)&a->pages, &a->page_cap, a->page_count, sizeof(*a->pages)) ||
      !grow((void **)&a->page_first, &a->page_meta_cap, a->page_count, sizeof(size_t)) ||
      !grow((void **)&a->page_entries, &a->page_entries_cap, a->page_count, sizeof(size_t))) return 0;
  a->page_first[a->page_count] = first_entry; a->page_entries[a->page_count] = 0;
  p = &a->pages[a->page_count++]; memset(p, 0, sizeof(*p));
  p->width = c->Wc; p->height = c->Hc;
  c->y = 0; c->src_min = SIZE_MAX; c->src_max = 0;
  c->page_line_start = a->line_count; c->page_paint_start = a->paint_count;
  return emit_plain(c, heading);
}
static float glyph_extent(const exr_glyph *g, size_t count, float *left) {
  float lo = 1e30f, hi = -1e30f; size_t k;
  for (k = 0; k < count; k++) {
    if (g[k].flags & EXR_GLYPH_HIDDEN) continue;
    if (g[k].x < lo) lo = g[k].x;
    if (g[k].x + g[k].advance > hi) hi = g[k].x + g[k].advance;
  }
  if (lo > hi) { lo = hi = 0; }
  if (left) *left = lo;
  return hi;
}
/* Leader dots, ascending x, on a grid ending at zone_right. */
static int push_dots(ctx *c, size_t entry, size_t dots, float zone_right, float top, float base_rel) {
  float x0 = zone_right - (float)dots * c->dot_adv; size_t k;
  for (k = 0; k < dots; k++) {
    exr_glyph d = *c->dot;
    d.start = d.end = d.cluster_start = d.cluster_end = c->meta->title_end[entry]; d.node = c->row_node;
    d.flags |= EXR_GLYPH_GENERATED;
    if (!push_glyph(c, &d, (x0 + (float)k * c->dot_adv) - d.x, (top + base_rel) - d.baseline)) return 0;
  }
  return 1;
}
static int push_label(ctx *c, size_t entry, float label_w, float label_left, float top, float base_rel) {
  span ls = LABEL(c, entry); size_t l, k;
  for (l = 0; l < ls.count; l++) {
    const exr_line *src = &c->fl[ls.first + l];
    for (k = 0; k < src->glyph_count; k++) {
      const exr_glyph *g = &c->fg[src->glyph_start + k];
      if (!push_glyph(c, g, c->Wc - label_w - label_left, (top + base_rel) - g->baseline)) return 0;
    }
  }
  return 1;
}
static int emit_row(ctx *c, size_t i) {
  span rs = ROW(c, i), ls = LABEL(c, i);
  const exr_line *last = &c->fl[rs.first + rs.count - 1];
  const exr_glyph *lg = &c->fg[last->glyph_start];
  const struct exr_toc_meta *m = c->meta;
  float total = 0, gap = c->fs * 0.5f, end_x, indent, label_w = 0, label_left = 0;
  float zone_left = 0, zone_right = 0, base_rel;
  size_t l, k, dots = 0, label_glyphs = 0;
  int extra = 0;
  assembly *a = &c->a;
  for (l = 0; l < rs.count; l++) total += c->fl[rs.first + l].height;
  end_x = glyph_extent(lg, last->glyph_count, NULL) - c->margin;
  {
    float lo; glyph_extent(&c->fg[c->fl[rs.first].glyph_start], c->fl[rs.first].glyph_count, &lo);
    indent = lo - c->margin;
  }
  base_rel = 0;
  for (k = 0; k < last->glyph_count; k++) if (!(lg[k].flags & EXR_GLYPH_HIDDEN)) { base_rel = lg[k].baseline - last->y; break; }
  if (ls.count) {
    for (l = 0; l < ls.count; l++) label_glyphs += c->fl[ls.first + l].glyph_count;
    label_w = glyph_extent(&c->fg[c->fl[ls.first].glyph_start], label_glyphs, &label_left) - label_left;
    zone_right = c->Wc - label_w - gap;
    zone_left = end_x + gap;
    dots = zone_right > zone_left ? (size_t)((zone_right - zone_left) / c->dot_adv) : 0;
    if (dots < 3) {
      extra = 1; zone_left = indent;
      dots = zone_right > zone_left ? (size_t)((zone_right - zone_left) / c->dot_adv) : 0;
    }
  }
  if (c->y + total + (extra ? last->height : 0) > c->Hc && a->page_entries[a->page_count - 1]) {
    close_page(c);
    if (!start_page(c, CONT(c), i)) return 0;
  }
  if (c->y + total + (extra ? last->height : 0) > c->Hc) return 0;
  for (l = 0; l < rs.count; l++) {
    const exr_line *src = &c->fl[rs.first + l]; exr_line out = *src; float dy = c->y - src->y; /* glyph baselines are page-absolute, x/y of the new page are content-relative */
    int tail = l + 1 == rs.count && ls.count && !extra;
    out.x -= c->margin; out.y = c->y; out.glyph_start = a->glyph_count;
    out.width = c->Wc - out.x; /* the whole row is the hit target, not just its text */
    for (k = 0; k < src->glyph_count; k++)
      if (!push_glyph(c, &c->fg[src->glyph_start + k], -c->margin, dy)) return 0;
    if (tail) {
      if (!push_dots(c, i, dots, zone_right, c->y, base_rel) ||
          !push_label(c, i, label_w, label_left, c->y, base_rel)) return 0;
      out.end = m->label_end[i];
    }
    out.glyph_count = a->glyph_count - out.glyph_start;
    if (!push_line(c, out, i)) return 0;
    c->y += src->height;
  }
  if (extra) {
    exr_line out;
    memset(&out, 0, sizeof(out));
    out.glyph_start = a->glyph_count; out.x = indent; out.y = c->y; out.height = last->height; out.width = c->Wc - indent;
    out.start = m->title_end[i]; out.end = m->label_end[i];
    if (!push_dots(c, i, dots, zone_right, c->y, base_rel) ||
        !push_label(c, i, label_w, label_left, c->y, base_rel)) return 0;
    out.glyph_count = a->glyph_count - out.glyph_start;
    if (!push_line(c, out, i)) return 0;
    c->y += last->height;
  }
  a->page_entries[a->page_count - 1]++;
  return 1;
}

exr_status exr_toc_pages_create(exr_publication *pub, exr_font *font, const exr_layout_config *config,
                                const exr_toc_page_options *options, exr_layout **out, exr_error *e) {
  const exr_toc_entry *toc = NULL; size_t n = 0, i;
  exr_status status;
  doc_builder b; exr_document *doc = NULL; exr_layout *flow = NULL, *result = NULL;
  exr_layout_config cfg; exr_positioned_input input;
  const char *title, *continued;
  size_t chapter, heading, cont, dot_a, dot_b;
  size_t *row = NULL, *label = NULL, *gid_node = NULL, groups = 0, g;
  span *spans = NULL; const exr_node *nodes; size_t node_count;
  struct exr_toc_meta *meta = NULL; ctx c;
  size_t fl_n, fg_n;
  memset(&c, 0, sizeof(c)); memset(&b, 0, sizeof(b)); memset(&input, 0, sizeof(input));
  if (!out) return exr_fail(e, EXR_ARGUMENT, "Missing TOC layout output");
  *out = NULL;
  if (!pub || !font || !config || !options || options->struct_size < sizeof(*options))
    return exr_fail(e, EXR_ARGUMENT, "Invalid TOC page arguments");
  status = exr_publication_toc(pub, &toc, &n, e);
  if (status != EXR_OK) return status;
  if (!n) return EXR_OK;
  if (n > TOC_MAX_ENTRIES) return exr_fail(e, EXR_LIMIT, "Too many TOC entries for a TOC page");
  if (options->labels && options->label_count != n)
    return exr_fail(e, EXR_ARGUMENT, "TOC label count differs from the TOC entry count");
  for (i = 0; options->labels && i < n; i++)
    if (options->labels[i] && strlen(options->labels[i]) > TOC_LABEL_MAX)
      return exr_fail(e, EXR_ARGUMENT, "TOC label is too long");
  title = options->title ? options->title : has_cjk(toc, n) ? "\xe7\x9b\xae\xe5\xbd\x95" : "Contents";
  continued = options->continued_title ? options->continued_title :
    has_cjk(toc, n) ? "\xe7\x9b\xae\xe5\xbd\x95\xef\xbc\x88\xe7\xbb\xad\xef\xbc\x89" : "Contents (continued)";

  /* Private document: heading, rows, continued heading, two leader candidates, labels. */
  b.cap = 2 + 2 * (n + 4 + n) + 4;
  b.nodes = calloc(b.cap, sizeof(*b.nodes)); b.attrs = calloc(b.cap, sizeof(*b.attrs));
  b.styles = calloc(b.cap, sizeof(*b.styles));
  row = calloc(n, sizeof(*row)); label = calloc(n, sizeof(*label));
  if (!b.nodes || !b.attrs || !b.styles || !row || !label) { status = exr_fail(e, EXR_MEMORY, "TOC allocation failed"); goto done; }
  add_node(&b, EXR_NODE_DOCUMENT, SIZE_MAX, NULL, NULL, NULL);
  chapter = add_node(&b, EXR_NODE_CHAPTER, 0, NULL, NULL, NULL);
  {
    static const char plain[] = "margin:0;text-indent:0;line-height:1;writing-mode:horizontal-tb";
    heading = add_block(&b, chapter, EXR_NODE_HEADING, "h1", title, plain);
    for (i = 0; i < n; i++) {
      char s[160]; size_t level = toc[i].level > 0 ? toc[i].level - 1 : 0;
      float reserve = 0;
      if (level > TOC_MAX_INDENT) level = TOC_MAX_INDENT;
      if (options->labels && options->labels[i] && *options->labels[i]) {
        const unsigned char *u;
        /* Keep the label zone (label + gap + a few leader dots) free so titles wrap before it. */
        for (u = (const unsigned char *)options->labels[i]; *u; u++)
          if ((*u & 0xc0) != 0x80) reserve += *u < 0x80 ? 0.6f : 1.0f;
        reserve += 1.5f;
      }
      snprintf(s, sizeof(s), "margin:0 %.2fem 0 %zuem;text-indent:0;line-height:1;writing-mode:horizontal-tb", (double)reserve, level);
      row[i] = add_block(&b, chapter, EXR_NODE_PARAGRAPH, "p", toc[i].title && *toc[i].title ? toc[i].title : "\xe2\x80\x94", s);
    }
    cont = add_block(&b, chapter, EXR_NODE_HEADING, "h1", continued, plain);
    dot_a = add_block(&b, chapter, EXR_NODE_PARAGRAPH, "p", "\xc2\xb7", plain);
    dot_b = add_block(&b, chapter, EXR_NODE_PARAGRAPH, "p", ".", plain);
    for (i = 0; i < n; i++) {
      label[i] = SIZE_MAX;
      if (options->labels && options->labels[i] && *options->labels[i])
        label[i] = add_block(&b, chapter, EXR_NODE_PARAGRAPH, "p", options->labels[i], plain);
    }
  }
  {
    exr_chapter_input ch = {"toc", "toc.xhtml", 0, 1};
    exr_document_input di;
    ch.root = chapter;
    memset(&di, 0, sizeof(di));
    di.title = "toc"; di.nodes = b.nodes; di.node_count = b.count; di.chapters = &ch; di.chapter_count = 1;
    status = exr_document_create(&di, &doc, e);
    if (status != EXR_OK) goto done;
  }
  cfg = *config; cfg.document_css = 1; cfg.page.height = 16384;
  status = exr_layout_create_ex(doc, font, &cfg, &flow, e);
  if (status != EXR_OK) goto done;

  nodes = exr_document_nodes(doc, &node_count);
  c.fl = exr_layout_lines(flow, &fl_n); c.fg = exr_layout_glyphs(flow, &fg_n);
  c.margin = config->page.margin; c.Wc = config->page.width - 2 * c.margin; c.Hc = config->page.height - 2 * c.margin;
  c.fs = config->page.font_size; c.n = n;

  groups = 1 + n + 3 + n;
  gid_node = malloc(groups * sizeof(*gid_node)); spans = calloc(groups, sizeof(*spans));
  if (!gid_node || !spans) { status = exr_fail(e, EXR_MEMORY, "TOC allocation failed"); goto done; }
  g = 0;
  gid_node[g++] = heading;
  for (i = 0; i < n; i++) gid_node[g++] = row[i];
  gid_node[g++] = cont; gid_node[g++] = dot_a; gid_node[g++] = dot_b;
  for (i = 0; i < n; i++) gid_node[g++] = label[i];
  g = 0;
  for (i = 0; i < fl_n; i++) { /* Groups follow document order, so one forward scan suffices. */
    while (g < groups && (gid_node[g] == SIZE_MAX || c.fl[i].start >= nodes[gid_node[g]].end)) g++;
    if (g >= groups) break;
    if (c.fl[i].start < nodes[gid_node[g]].start) continue;
    if (!spans[g].count) spans[g].first = i;
    spans[g].count++;
  }
  c.spans = spans;
  if (!HEAD(&c).count || !CONT(&c).count || !spans[1 + n + 1].count) { status = exr_fail(e, EXR_LIMIT, "TOC heading did not lay out"); goto done; }
  for (i = 0; i < n; i++) if (!ROW(&c, i).count) { status = exr_fail(e, EXR_LIMIT, "TOC entry did not lay out"); goto done; }

  meta = calloc(1, sizeof(*meta));
  if (!meta) { status = exr_fail(e, EXR_MEMORY, "TOC allocation failed"); goto done; }
  meta->entries = n;
  meta->title_start = malloc(n * sizeof(size_t)); meta->title_end = malloc(n * sizeof(size_t));
  meta->label_start = malloc(n * sizeof(size_t)); meta->label_end = malloc(n * sizeof(size_t));
  if (!meta->title_start || !meta->title_end || !meta->label_start || !meta->label_end) { status = exr_fail(e, EXR_MEMORY, "TOC allocation failed"); goto done; }
  for (i = 0; i < n; i++) {
    meta->title_start[i] = nodes[row[i]].start; meta->title_end[i] = nodes[row[i]].end;
    meta->label_start[i] = label[i] == SIZE_MAX ? SIZE_MAX : nodes[label[i]].start;
    meta->label_end[i] = label[i] == SIZE_MAX ? SIZE_MAX : nodes[label[i]].end;
  }
  c.meta = meta;

  /* Leader glyph: the middle dot unless the font makes it wider than 0.6 em. */
  c.dot = &c.fg[c.fl[spans[1 + n + 1].first].glyph_start];
  if (c.dot->advance > 0.6f * c.fs && spans[1 + n + 2].count) c.dot = &c.fg[c.fl[spans[1 + n + 2].first].glyph_start];
  c.dot_adv = c.dot->advance;
  if (c.dot_adv < 1) { status = exr_fail(e, EXR_LIMIT, "TOC leader glyph has no advance"); goto done; }

  if (!start_page(&c, HEAD(&c), 0)) goto memory;
  for (i = 0; i < n; i++) {
    c.row_node = row[i];
    if (!emit_row(&c, i)) {
      status = c.y > 0 ? exr_fail(e, EXR_LIMIT, "TOC row does not fit a page or allocation failed") : exr_fail(e, EXR_MEMORY, "TOC allocation failed");
      goto done;
    }
  }
  close_page(&c);

  input.struct_size = sizeof(input);
  input.pages = c.a.pages; input.page_count = c.a.page_count;
  input.glyphs = c.a.glyphs; input.glyph_count = c.a.glyph_count;
  input.lines = c.a.lines; input.line_count = c.a.line_count;
  input.paints = c.a.paints; input.paint_count = c.a.paint_count;
  status = exr_layout_create_positioned(doc, exr_layout_font(flow), &input, config, &result, e);
  if (status != EXR_OK) goto done;
  meta->pages = c.a.page_count; meta->lines = c.a.line_count;
  meta->line_entry = c.a.line_entry; c.a.line_entry = NULL;
  meta->page_first = c.a.page_first; c.a.page_first = NULL;
  meta->page_count = c.a.page_entries; c.a.page_entries = NULL;
  meta->roman = malloc(meta->pages * sizeof(*meta->roman));
  if (!meta->roman) { status = exr_fail(e, EXR_MEMORY, "TOC allocation failed"); goto done; }
  for (i = 0; i < meta->pages; i++) roman(i + 1, meta->roman[i]);
  result->toc = meta; meta = NULL;
  *out = result; result = NULL;
  status = exr_fail(e, EXR_OK, "");
  goto done;
memory:
  status = exr_fail(e, EXR_MEMORY, "TOC allocation failed");
done:
  free(b.nodes); free(b.attrs); free(b.styles); free(row); free(label);
  free(gid_node); free(spans); assembly_free(&c.a);
  exr_toc_meta_free(meta);
  exr_document_free(doc); exr_layout_free(flow); exr_layout_free(result);
  return status;
}
