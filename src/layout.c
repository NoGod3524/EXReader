/* SPDX-License-Identifier: GPL-3.0-only */
#include "layout_internal.h"
#include FT_SYNTHESIS_H
exr_status exr_font_open(const char *path, exr_font **out, exr_error *e) {
  exr_font *font;
  exr_status s;
  size_t n;
  if (!path || !out)
    return exr_fail(e, EXR_ARGUMENT, "Invalid font arguments");
  *out = NULL;
  font = calloc(1, sizeof(*font));
  if (!font)
    return exr_fail(e, EXR_MEMORY, "Font allocation failed");
  s = exr_read(path, &font->bytes, &n, e);
  if (s != EXR_OK) {
    free(font);
    return s;
  }
  if (FT_Init_FreeType(&font->library) ||
      FT_New_Memory_Face(font->library, font->bytes, (FT_Long)n, 0, &font->face)) {
    exr_font_free(font);
    return exr_fail(e, EXR_FONT, "Font cannot be loaded");
  }
  if (!FT_IS_SCALABLE(font->face)) {
    exr_font_free(font);
    return exr_fail(e, EXR_FONT, "A scalable font is required");
  }
  if (font->face->num_glyphs > 0 && font->face->num_glyphs <= 65536) {
    font->metric_count = (size_t)font->face->num_glyphs;
    font->advances = calloc(font->metric_count, sizeof(*font->advances));
    font->measured = calloc(font->metric_count, 1);
    if (!font->advances || !font->measured) {
      exr_font_free(font);
      return exr_fail(e, EXR_MEMORY, "Font metrics allocation failed");
    }
  }
  *out = font;
  return EXR_OK;
}
void exr_font_free(exr_font *f) {
  if (f) {
    if (f->face)
      FT_Done_Face(f->face);
    if (f->library)
      FT_Done_FreeType(f->library);
    free(f->advances);
    free(f->measured);
    free(f->bytes);
    free(f);
  }
}
int exr_font_size(exr_font *font, float pixels) {
  FT_F26Dot6 size = (FT_F26Dot6)lroundf(pixels * 64);
  if (font->metric_size == size)
    return 0;
  if (FT_Set_Char_Size(font->face, 0, size, 72, 72))
    return 1;
  font->metric_size = size;
  if (font->measured)
    memset(font->measured, 0, font->metric_count);
  return 0;
}
int exr_measure(exr_font *font, uint32_t glyph, unsigned flags, float *advance) {
  if (glyph < font->metric_count && font->measured[glyph] == flags + 1) {
    *advance = font->advances[glyph];
    return 0;
  }
  if (FT_Load_Glyph(font->face, glyph, FT_LOAD_DEFAULT))
    return 1;
  if (flags & 1)
    FT_GlyphSlot_Embolden(font->face->glyph);
  *advance = (float)font->face->glyph->advance.x / 64;
  if (glyph < font->metric_count) {
    font->advances[glyph] = *advance;
    font->measured[glyph] = (unsigned char)(flags + 1);
  }
  return 0;
}
exr_layout_options exr_layout_defaults(void) {
  exr_layout_options o = {720, 1040, 48, 24, 1.6f, 12};
  return o;
}
float exr_kern(exr_font *f, uint32_t left, uint32_t right) {
  FT_Vector v = {0};
  if (left && right && FT_HAS_KERNING(f->face))
    FT_Get_Kerning(f->face, left, right, FT_KERNING_DEFAULT, &v);
  return (float)v.x / 64;
}
exr_layout_config exr_layout_config_defaults(void) {
  exr_layout_config config = {0};
  config.page = exr_layout_defaults();
  config.document_css = 1;
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
  if (l) {
    free(l->glyphs);
    free(l->lines);
    size_t i;
    free(l->pages);
    free(l->boxes);
    free(l->styles);
    for (i = 0; i < l->image_count; i++)
      exr_bitmap_free(&l->images[i].bitmap);
    free(l->images);
    free(l);
  }
}
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
size_t exr_layout_page_at(const exr_layout *l, size_t offset) {
  size_t lo = 0, hi;
  if (!l || !l->page_count)
    return SIZE_MAX;
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
    float left = g->x, right = g->x + g->advance;
    while (end < line->glyph_start + line->glyph_count &&
           l->glyphs[end].cluster_start == g->cluster_start) {
      left = fminf(left, l->glyphs[end].x);
      right = fmaxf(right, l->glyphs[end].x + l->glyphs[end].advance);
      end++;
    }
    if (x <= right)
      return x < (left + right) / 2 ? g->cluster_start : g->cluster_end;
    i = end;
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
