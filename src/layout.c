/* SPDX-License-Identifier: MIT */
#include "memory_internal.h"
#include "layout_internal.h"
#include "variable_internal.h"
#include "css_internal.h"
#include <ctype.h>
exr_font *exr_layout_font(const exr_layout *l) { return l ? l->font : NULL; }
exr_writing_mode exr_layout_writing_mode(const exr_layout *l) {
  return l ? l->writing_mode : EXR_WRITING_HORIZONTAL_TB;
}
exr_status exr_glyph_matrix(const exr_glyph *g, double matrix[6], exr_error *e) {
  double scale;
  if (matrix) memset(matrix, 0, 6 * sizeof(*matrix));
  if (!g || !matrix || !isfinite(g->x) || !isfinite(g->baseline) ||
      !isfinite(g->offset_x) || !isfinite(g->offset_y) || !isfinite(g->size) ||
      g->size < 0 || g->size > 4096 || (g->flags & ~(511u|EXR_GLYPH_GENERATED)) ||
      ((g->flags & EXR_GLYPH_SIDEWAYS) && !(g->flags & EXR_GLYPH_VERTICAL)))
    return exr_fail(e, EXR_ARGUMENT, "Invalid glyph transformation input");
  scale = (double)g->size / 1000;
  if (g->flags & EXR_GLYPH_SIDEWAYS) {
    matrix[1] = matrix[2] = scale;
    matrix[4] = (double)g->x + g->offset_y;
    matrix[5] = (double)g->baseline + g->offset_x;
  } else {
    matrix[0] = scale; matrix[3] = -scale;
    matrix[4] = (double)g->x + g->offset_x;
    matrix[5] = (double)g->baseline - g->offset_y;
  }
  return exr_fail(e, EXR_OK, "");
}
exr_layout_options exr_layout_defaults(void) {
  exr_layout_options o = {720, 1040, 48, 24, 1.6f, 12};
  return o;
}
exr_layout_config exr_layout_config_defaults(void) {
  exr_layout_config config = {0};
  config.page = exr_layout_defaults();
  config.document_css = 1;
  config.embedded_fonts = 1;
  return config;
}
exr_status exr_layout_create_ex(const exr_document *d, exr_font *f, const exr_layout_config *config,
                                exr_layout **out, exr_error *e) {
  exr_layout_config defaults = exr_layout_config_defaults();
  return exr_flow_create(d, f, config ? config : &defaults, out, e);
}
exr_status exr_layout_create(const exr_document *d, exr_font *f, const exr_layout_options *o,
                             exr_layout **out, exr_error *e) {
  exr_layout_config config = exr_layout_config_defaults();
  if (o)
    config.page = *o;
  return exr_layout_create_ex(d, f, &config, out, e);
}
void exr_layout_free(exr_layout *l) {
  if (l && l->refs > 1) { l->refs--; return; }
  if (l) {
    free(l->glyphs);
    free(l->lines);
    size_t i;
    free(l->pages);
    free(l->boxes);
    free(l->paints);
    free(l->positioned);
    exr_styles_free(l->styles, l->style_count);
    exr_font_free(l->font);
    for (i = 0; i < l->image_count; i++) {
      exr_cached_image *image = &l->images[i];
      if (!image->refs || !--*image->refs) {
        exr_bitmap_free(&image->bitmap);
        free(image->refs);
      }
    }
    free(l->images);
    free(l);
  }
}
void exr_layout_ref(exr_layout *l) { if (l) l->refs = l->refs ? l->refs + 1 : 2; }
const exr_page *exr_layout_pages(const exr_layout *l, size_t *n) {
  if (n)
    *n = l ? l->page_count : 0;
  return l ? l->pages : NULL;
}
const exr_line *exr_layout_lines(const exr_layout *l, size_t *n) {
  if (n)
    *n = l ? l->line_count : 0;
  return l ? l->lines : NULL;
}
const exr_glyph *exr_layout_glyphs(const exr_layout *l, size_t *n) {
  if (n)
    *n = l ? l->glyph_count : 0;
  return l ? l->glyphs : NULL;
}
const exr_paint *exr_layout_paints(const exr_layout *l,size_t page,size_t *count) {
  if(count) *count=0;
  if(!l || !l->positioned || page>=l->page_count) return NULL;
  if(count) *count=l->positioned[page].paint_count;
  return l->positioned[page].paint_count ? l->paints+l->positioned[page].paint_start : NULL;
}
size_t exr_layout_page_at(const exr_layout *l, size_t offset) {
  size_t lo = 0, hi;
  if (!l || !l->page_count)
    return SIZE_MAX;
  if(l->source_overlaps) {
    /* overlap-only linear lookup; add a range index if host seek profiles need one. */
    size_t i,best=SIZE_MAX,span=SIZE_MAX;
    for(i=0;i<l->glyph_count;i++) {
      const exr_glyph *g=&l->glyphs[i];
      /* A shaped cluster can bridge out-of-flow text in source order. Prefer
         the narrowest actual range, e.g. a float's own glyph over that cluster. */
      if(g->start<=offset && offset<g->end && g->end-g->start<span) {
        best=g->page; span=g->end-g->start;
      }
    }
    if(best!=SIZE_MAX) return best;
    { size_t start=0; int found=0; best=0;
      for(i=0;i<l->page_count;i++) if(l->pages[i].start<=offset && (!found || l->pages[i].start>=start)) {
        best=i; start=l->pages[i].start; found=1;
      }
      return best;
    }
  }
  hi = l->page_count;
  while (lo + 1 < hi) {
    size_t mid = lo + (hi - lo) / 2;
    if (l->pages[mid].start <= offset)
      lo = mid;
    else
      hi = mid;
  }
  return lo;
}
size_t exr_layout_hit_test(const exr_layout *l, size_t p, float x, float y) {
  const exr_page *page;
  const exr_line *line = NULL;
  const exr_glyph *last_visible = NULL;
  size_t i;
  float distance = INFINITY;
  if (!l || p >= l->page_count || !isfinite(x) || !isfinite(y))
    return SIZE_MAX;
  page = &l->pages[p];
  for (i = page->line_start; i < page->line_start + page->line_count; i++) {
    const exr_line *candidate = &l->lines[i];
    float dx = fmaxf(0, fmaxf(candidate->x - x, x - candidate->x - candidate->width));
    float dy = fmaxf(0, fmaxf(candidate->y - y, y - candidate->y - candidate->height));
    float delta = dx * dx + dy * dy;
    if (delta < distance) {
      distance = delta;
      line = candidate;
    }
  }
  if (!line)
    return page->start;
  for (i = line->glyph_start; i < line->glyph_start + line->glyph_count;) {
    const exr_glyph *g = &l->glyphs[i];
    size_t end = i + 1;
    int visible = !(g->flags & EXR_GLYPH_HIDDEN);
    int vertical = !!(g->flags & EXR_GLYPH_VERTICAL);
    float position = vertical ? y : x;
    float left = vertical ? g->baseline : g->x, right = left + g->advance;
    while (end < line->glyph_start + line->glyph_count &&
           l->glyphs[end].cluster_start == g->cluster_start && l->glyphs[end].bidi_level == g->bidi_level) {
      float pen = vertical ? l->glyphs[end].baseline : l->glyphs[end].x;
      left = fminf(left, pen);
      right = fmaxf(right, pen + l->glyphs[end].advance);
      visible |= !(l->glyphs[end].flags & EXR_GLYPH_HIDDEN);
      end++;
    }
    if (visible) last_visible = g;
    if (visible && position <= right)
      return (position < (left + right) / 2) != (g->bidi_level & 1) ?
                 g->cluster_start : g->cluster_end;
    i = end;
  }
  if (last_visible) {
    return last_visible->bidi_level & 1 ? last_visible->cluster_start : last_visible->cluster_end;
  }
  return line->end;
}
const exr_box *exr_layout_boxes(const exr_layout *l, size_t *n) {
  if (n)
    *n = l ? l->box_count : 0;
  return l ? l->boxes : NULL;
}
const exr_bitmap *exr_layout_image(const exr_layout *l, size_t resource) {
  size_t i;
  if (l)
    for (i = 0; i < l->image_count; i++)
      if (l->images[i].resource == resource)
        return &l->images[i].bitmap;
  return NULL;
}

static int ws(unsigned char c) { return c == ' ' || (c >= 9 && c <= 13); }
static int same(const char *s,size_t n,const char *word) {
  size_t i;if(strlen(word)!=n) return 0;
  for(i=0;i<n;i++) if(tolower((unsigned char)s[i])!=tolower((unsigned char)word[i])) return 0;
  return 1;
}
static int requested(const exr_document *d, const exr_style *styles, const exr_font_rule *r) {
  size_t i;
  for (i = 0; i < d->node_count; i++) {
    size_t at = 0;
    char family[128];
    if (!styles[i].family || styles[i].display == EXR_CSS_NONE ||
        (r->chapter != SIZE_MAX && d->nodes[i].chapter != r->chapter)) continue;
    while (exr_family_next(styles[i].family, &at, family) == 1)
      if (exr_family_equal(family, r->family)) return 1;
  }
  return 0;
}
static exr_status load_font(const exr_document *d, exr_font *font, const exr_font_rule *r,
                              const exr_control *control, void **out, size_t *size,
                              size_t *read_bytes, exr_error *e) {
  size_t at = 0, n = strlen(r->source), attempts = 0;
  *out = NULL; *size = 0;
  while (at < n) {
    size_t end = at + exr_css_delimiter(r->source + at, n - at, ',');
    size_t a = at, b = end, i;
    char uri[2048], path[2048];
    FT_Face probe = NULL;
    exr_status status;
    status = exr_control_cancel(control, e);
    if (status != EXR_OK) return status;
    at = end < n ? end + 1 : n;
    while (a < b && ws((unsigned char)r->source[a])) a++;
    if (b - a < 5 || !same(r->source + a, 3, "url") || r->source[a + 3] != '(') continue;
    a += 4;
    b = a + exr_css_delimiter(r->source + a, end - a, ')');
    if (b == end) continue;
    while (a < b && ws((unsigned char)r->source[a])) a++;
    while (b > a && ws((unsigned char)r->source[b - 1])) b--;
    if (a < b && (r->source[a] == '\'' || r->source[a] == '"')) {
      if (b - a < 2 || r->source[b - 1] != r->source[a]) continue;
      a++; b--;
    }
    if (!exr_css_unescape(r->source + a, b - a, uri, sizeof(uri)) ||
        !exr_resolve_path(r->base, uri, path)) continue;
    for (i = 0; i < d->resource_count; i++)
      if (!strcmp(path, d->resources[i].path)) break;
    if (i == d->resource_count) continue;
    if (++attempts > 8) return exr_fail(e, EXR_LIMIT, "Font source retry limit exceeded");
    status = exr_document_resource(d, i, out, size, e);
    if (status == EXR_MEMORY || status == EXR_LIMIT || status == EXR_CANCELLED) return status;
    if (status != EXR_OK) continue;
    status = exr_control_cancel(control, e);
    if (status != EXR_OK) { exr_free(*out); *out = NULL; *size = 0; return status; }
    if (*size > EXR_MAX_INPUT - *read_bytes) {
      exr_free(*out); *out = NULL;
      return exr_fail(e, EXR_LIMIT, "Embedded font reads exceed 128 MiB");
    }
    *read_bytes += *size;
    if (!exr_font_face_open(font->library, *out, *size, 0, &probe) &&
        exr_font_face_supported(probe) && !FT_Select_Charmap(probe, FT_ENCODING_UNICODE)) {
      FT_Done_Face(probe);
      return EXR_OK;
    }
    if (probe) FT_Done_Face(probe);
    exr_free(*out); *out = NULL; *size = 0;
  }
  return EXR_OK;
}
exr_status exr_book_fonts(const exr_document *d, exr_font *fallback,
                           const exr_style *styles, const exr_font_rule *rules, size_t count,
                           const exr_control *control, exr_font **out, exr_error *e) {
  exr_font_input inputs[32];
  void *loaded[32] = {0};
  const exr_font_rule *selected[32] = {0};
  size_t i, used = fallback->count, total = 0, reads = 0;
  exr_status status = EXR_OK;
  *out = NULL;
  status = exr_control_cancel(control, e);
  if (status != EXR_OK) return status;
  for (i = 0; i < used; i++) {
    inputs[i] = (exr_font_input){fallback->faces[i].bytes, fallback->faces[i].bytes_size,
                                  (size_t)fallback->faces[i].face->face_index};
    total += inputs[i].size;
  }
  for (i = 0; i < count; i++) {
    void *bytes = NULL;
    size_t size = 0;
    if (!requested(d, styles, &rules[i])) continue;
    status = load_font(d, fallback, &rules[i], control, &bytes, &size, &reads, e);
    if (status != EXR_OK) goto done;
    if (!bytes) continue;
    if (used == 32 || size > EXR_MAX_INPUT - total) {
      exr_free(bytes);
      status = exr_fail(e, EXR_LIMIT, "Combined font set exceeds 32 faces or 128 MiB");
      goto done;
    }
    total += size;
    selected[used] = &rules[i]; loaded[used] = bytes;
    inputs[used++] = (exr_font_input){bytes, size, 0};
  }
  if (used == fallback->count) { exr_font_ref(fallback); *out = fallback; }
  else {
    status = exr_font_create(inputs, used, out, e);
    if (status != EXR_OK) goto done;
    (*out)->base_count = fallback->count;
    (*out)->fallback = fallback;
    exr_font_ref(fallback);
    for (i = 0; i < used; i++) {
      exr_face *face = &(*out)->faces[i];
      if (selected[i]) {
        strcpy(face->family, selected[i]->family);
        face->style_flags = selected[i]->flags;
        face->scope = selected[i]->chapter;
      } else {
        status=exr_font_copy_variations(*out,i,fallback,i,e);
        if(status!=EXR_OK) { exr_font_free(*out); *out=NULL; goto done; }
        strcpy(face->family, fallback->faces[i].family);
        face->style_flags = fallback->faces[i].style_flags;
        face->scope = fallback->faces[i].scope;
      }
    }
  }
done:
  for (i = 0; i < 32; i++) exr_free(loaded[i]);
  return status == EXR_OK ? exr_fail(e, EXR_OK, "") : status;
}

size_t exr_layout_memory_size(const exr_layout *l) {
  size_t total, i;
  if (!l)
    return 0;
  total = sizeof(*l);
  total = exr_memory_array(total, l->glyphs, l->glyph_cap, sizeof(*l->glyphs));
  total = exr_memory_array(total, l->lines, l->line_cap, sizeof(*l->lines));
  total = exr_memory_array(total, l->pages, l->page_cap, sizeof(*l->pages));
  total = exr_memory_array(total, l->boxes, l->box_cap, sizeof(*l->boxes));
  total = exr_memory_array(total, l->paints, l->paint_count, sizeof(*l->paints));
  total = exr_memory_array(total, l->positioned, l->page_count, sizeof(*l->positioned));
  total = exr_memory_array(total, l->images, l->image_cap, sizeof(*l->images));
  total = exr_memory_array(total, l->styles, l->style_count, sizeof(*l->styles));
  for (i = 0; i < l->style_count; i++)
    if (l->styles[i].family_owned) total = exr_memory_add(total, strlen(l->styles[i].family) + 1);
  /* Image bytes and their reference counters are conservatively charged to each
     referencing page, even when another page shares the same immutable pixels. */
  total = exr_memory_array(total, l->images, l->image_count, sizeof(size_t));
  return exr_memory_add(total, l->image_bytes);
}
