/* SPDX-License-Identifier: GPL-3.0-only */
#include "internal.h"
#include <ft2build.h>
#include FT_FREETYPE_H
struct exr_font {
  FT_Library library;
  FT_Face face;
  unsigned char *bytes;
};
struct exr_layout {
  exr_layout_options options;
  exr_glyph *glyphs;
  size_t glyph_count, glyph_cap;
  exr_line *lines;
  size_t line_count, line_cap;
  exr_page *pages;
  size_t page_count, page_cap;
};
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
      FT_New_Memory_Face(font->library, font->bytes, (FT_Long)n, 0,
                         &font->face)) {
    exr_font_free(font);
    return exr_fail(e, EXR_FONT, "Font cannot be loaded");
  }
  if (!FT_IS_SCALABLE(font->face)) {
    exr_font_free(font);
    return exr_fail(e, EXR_FONT, "A scalable font is required");
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
    free(f->bytes);
    free(f);
  }
}
exr_layout_options exr_layout_defaults(void) {
  exr_layout_options o = {720, 1040, 48, 24, 1.6f, 12};
  return o;
}
static int cjk(uint32_t c) {
  return (c >= 0x2e80 && c <= 0x9fff) || (c >= 0xac00 && c <= 0xd7af) ||
         (c >= 0xf900 && c <= 0xfaff) || (c >= 0x20000 && c <= 0x323af);
}
static int mark(uint32_t c) {
  return (c >= 0x300 && c <= 0x36f) || (c >= 0x1ab0 && c <= 0x1aff) ||
         (c >= 0x1dc0 && c <= 0x1dff) || (c >= 0xfe00 && c <= 0xfe0f) ||
         (c >= 0xfe20 && c <= 0xfe2f) || (c >= 0x1f3fb && c <= 0x1f3ff) ||
         (c >= 0xe0100 && c <= 0xe01ef);
}
static int opening(uint32_t c) {
  return c == '(' || c == '[' || c == '{' || c == 0x2018 || c == 0x201c ||
         c == 0x3008 || c == 0x300a || c == 0x300c || c == 0x300e ||
         c == 0x3010 || c == 0xff08;
}
static int closing(uint32_t c) {
  return c == ')' || c == ']' || c == '}' || c == ',' || c == '.' || c == ';' ||
         c == ':' || c == '!' || c == '?' || c == 0x2019 || c == 0x201d ||
         c == 0x3001 || c == 0x3002 || c == 0x3009 || c == 0x300b ||
         c == 0x300d || c == 0x300f || c == 0x3011 || c == 0xff09 ||
         c == 0xff0c || c == 0xff01 || c == 0xff1f || c == 0xff1a ||
         c == 0xff1b;
}
static int break_before(uint32_t previous, uint32_t next) {
  if (mark(next) || next == 0x200d || previous == 0x200d || opening(previous) ||
      closing(next))
    return 0;
  return previous == ' ' || previous == '\t' || previous == '-' ||
         cjk(previous) || cjk(next);
}
static float kern(exr_font *f, uint32_t left, uint32_t right) {
  FT_Vector v = {0};
  if (left && right && FT_HAS_KERNING(f->face))
    FT_Get_Kerning(f->face, left, right, FT_KERNING_DEFAULT, &v);
  return (float)v.x / 64;
}
static int add_page(exr_layout *l, size_t start) {
  exr_page *p;
  if (!exr_grow((void **)&l->pages, &l->page_cap, l->page_count + 1,
                sizeof(*p)))
    return 0;
  p = &l->pages[l->page_count++];
  p->start = p->end = start;
  p->line_start = l->line_count;
  p->line_count = 0;
  return 1;
}
static exr_status emit_line(exr_layout *l, exr_font *f, size_t start,
                            size_t end, float *y, float height, exr_error *e) {
  exr_line *line;
  exr_page *page;
  size_t i;
  float x = l->options.margin, baseline;
  uint32_t previous = 0;
  if (height > l->options.height - 2 * l->options.margin)
    return exr_fail(e, EXR_ARGUMENT, "Page is shorter than a text line");
  if (!l->page_count || *y + height > l->options.height - l->options.margin) {
    if (!add_page(l, l->glyphs[start].start))
      return exr_fail(e, EXR_MEMORY, "Page allocation failed");
    *y = l->options.margin;
  }
  if (!exr_grow((void **)&l->lines, &l->line_cap, l->line_count + 1,
                sizeof(*line)))
    return exr_fail(e, EXR_MEMORY, "Line allocation failed");
  baseline = *y + (float)f->face->size->metrics.ascender / 64;
  line = &l->lines[l->line_count++];
  line->start = l->glyphs[start].start;
  line->end = l->glyphs[end - 1].end;
  line->glyph_start = start;
  line->glyph_count = end - start;
  line->y = *y;
  line->page = l->page_count - 1;
  page = &l->pages[l->page_count - 1];
  page->end = line->end;
  page->line_count++;
  for (i = start; i < end; i++) {
    exr_glyph *g = &l->glyphs[i];
    x += kern(f, previous, g->glyph);
    g->x = x;
    g->baseline = baseline;
    g->page = l->page_count - 1;
    x += g->advance;
    previous = g->glyph;
  }
  *y += height;
  return EXR_OK;
}
exr_status exr_layout_create(const exr_document *doc, exr_font *font,
                             const exr_layout_options *options,
                             exr_layout **out, exr_error *e) {
  exr_layout *l;
  exr_layout_options o;
  size_t b;
  float y;
  exr_status status = EXR_OK;
  if (!doc || !font || !out)
    return exr_fail(e, EXR_ARGUMENT, "Invalid layout arguments");
  *out = NULL;
  o = options ? *options : exr_layout_defaults();
  if (!isfinite(o.width) || !isfinite(o.height) || !isfinite(o.margin) ||
      !isfinite(o.font_size) || !isfinite(o.line_height) ||
      !isfinite(o.paragraph_spacing) || o.width < 32 || o.height < 32 ||
      o.width > 16384 || o.height > 16384 || o.margin < 0 || o.font_size < 4 ||
      o.font_size > 256 || o.line_height < 1 || o.line_height > 5 ||
      o.paragraph_spacing < 0 || o.paragraph_spacing > 1024 ||
      o.width - 2 * o.margin < o.font_size * 1.5f ||
      o.height - 2 * o.margin < o.font_size * o.line_height)
    return exr_fail(e, EXR_ARGUMENT, "Invalid page geometry");
  l = calloc(1, sizeof(*l));
  if (!l)
    return exr_fail(e, EXR_MEMORY, "Layout allocation failed");
  l->options = o;
  y = o.margin;
  for (b = 0; b < doc->count; b++) {
    size_t pos = doc->blocks[b].start, end = doc->blocks[b].end,
           first = l->glyph_count, start, i, last_break;
    float size = o.font_size * (doc->blocks[b].heading ? 1.35f : 1), height;
    if (FT_Set_Char_Size(font->face, 0, (FT_F26Dot6)lroundf(size * 64), 72,
                         72)) {
      status = exr_fail(e, EXR_FONT, "Cannot size font");
      goto bad;
    }
    height = fmaxf(size * o.line_height,
                   (float)(font->face->size->metrics.ascender -
                           font->face->size->metrics.descender) /
                       64);
    while (pos < end) {
      uint32_t cp;
      size_t at = pos;
      exr_glyph *g;
      if (!exr_next(doc->text, end, &pos, &cp)) {
        status = exr_fail(e, EXR_ENCODING, "Invalid internal text");
        goto bad;
      }
      if (l->glyph_count >= EXR_MAX_ITEMS ||
          !exr_grow((void **)&l->glyphs, &l->glyph_cap, l->glyph_count + 1,
                    sizeof(*g))) {
        status = exr_fail(e, EXR_LIMIT, "Glyph limit exceeded");
        goto bad;
      }
      g = &l->glyphs[l->glyph_count++];
      memset(g, 0, sizeof(*g));
      g->start = at;
      g->end = pos;
      g->codepoint = cp;
      g->size = size;
      g->glyph = FT_Get_Char_Index(font->face, cp == '\t' ? ' ' : cp);
      if (FT_Load_Glyph(font->face, g->glyph, FT_LOAD_DEFAULT)) {
        status = exr_fail(e, EXR_FONT, "Cannot measure glyph");
        goto bad;
      }
      g->advance =
          (float)font->face->glyph->advance.x / 64 * (cp == '\t' ? 4 : 1);
    }
    start = first;
    while (start < l->glyph_count) {
      float width = 0;
      uint32_t previous = 0;
      last_break = SIZE_MAX;
      for (i = start; i < l->glyph_count; i++) {
        exr_glyph *g = &l->glyphs[i];
        float advance = g->advance + kern(font, previous, g->glyph);
        if (i > start && break_before(l->glyphs[i - 1].codepoint, g->codepoint))
          last_break = i;
        if (i > start && width + advance > o.width - 2 * o.margin) {
          size_t split = last_break != SIZE_MAX ? last_break : i;
          if (last_break == SIZE_MAX) {
            while (split > start && (mark(l->glyphs[split].codepoint) ||
                                     l->glyphs[split].codepoint == 0x200d ||
                                     l->glyphs[split - 1].codepoint == 0x200d))
              split--;
            if (split == start) {
              width += advance;
              previous = g->glyph;
              continue;
            }
          }
          i = split;
          break;
        }
        width += advance;
        previous = g->glyph;
      }
      if (i == start) {
        status = exr_fail(e, EXR_FORMAT, "Layout made no progress");
        goto bad;
      }
      status = emit_line(l, font, start, i, &y, height, e);
      if (status != EXR_OK)
        goto bad;
      start = i;
    }
    y += o.paragraph_spacing;
  }
  if (!l->page_count) {
    status = exr_fail(e, EXR_FORMAT, "No layout content");
    goto bad;
  }
  l->pages[l->page_count - 1].end = doc->size;
  *out = l;
  return EXR_OK;
bad:
  exr_layout_free(l);
  return status;
}
void exr_layout_free(exr_layout *l) {
  if (l) {
    free(l->glyphs);
    free(l->lines);
    free(l->pages);
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
    float delta = fabsf(y - candidate->y);
    if (delta < distance) {
      distance = delta;
      line = candidate;
    }
  }
  if (!line)
    return page->start;
  for (i = line->glyph_start; i < line->glyph_start + line->glyph_count; i++) {
    const exr_glyph *g = &l->glyphs[i];
    if (x < g->x + g->advance / 2)
      return g->start;
  }
  return line->end;
}
exr_status exr_render_page(const exr_layout *l, exr_font *f, size_t page,
                           exr_bitmap *out, exr_error *e) {
  size_t i, j;
  uint32_t width, height;
  float last_size = 0;
  const exr_page *p;
  if (!l || !f || !out || page >= l->page_count)
    return exr_fail(e, EXR_ARGUMENT, "Invalid render arguments");
  memset(out, 0, sizeof(*out));
  width = (uint32_t)ceilf(l->options.width);
  height = (uint32_t)ceilf(l->options.height);
  if ((size_t)width * height > 64 * 1024 * 1024)
    return exr_fail(e, EXR_LIMIT, "Page bitmap exceeds 64 MiB");
  out->pixels = malloc((size_t)width * height);
  if (!out->pixels)
    return exr_fail(e, EXR_MEMORY, "Bitmap allocation failed");
  out->width = width;
  out->height = height;
  out->stride = width;
  memset(out->pixels, 255, (size_t)width * height);
  p = &l->pages[page];
  for (i = p->line_start; i < p->line_start + p->line_count; i++)
    for (j = l->lines[i].glyph_start;
         j < l->lines[i].glyph_start + l->lines[i].glyph_count; j++) {
      const exr_glyph *g = &l->glyphs[j];
      FT_GlyphSlot slot;
      unsigned int by, bx;
      int left, top;
      if (last_size != g->size) {
        if (FT_Set_Char_Size(f->face, 0, (FT_F26Dot6)lroundf(g->size * 64), 72,
                             72))
          goto font_error;
        last_size = g->size;
      }
      if (FT_Load_Glyph(f->face, g->glyph, FT_LOAD_DEFAULT) ||
          FT_Render_Glyph(f->face->glyph, FT_RENDER_MODE_NORMAL))
        goto font_error;
      slot = f->face->glyph;
      left = (int)lroundf(g->x) + slot->bitmap_left;
      top = (int)lroundf(g->baseline) - slot->bitmap_top;
      for (by = 0; by < slot->bitmap.rows; by++)
        for (bx = 0; bx < slot->bitmap.width; bx++) {
          int x = left + (int)bx, y = top + (int)by;
          unsigned a;
          const unsigned char *row;
          if (x < 0 || y < 0 || (uint32_t)x >= width || (uint32_t)y >= height)
            continue;
          row = slot->bitmap.buffer + (ptrdiff_t)by * slot->bitmap.pitch;
          if (slot->bitmap.pixel_mode == FT_PIXEL_MODE_GRAY)
            a = row[bx];
          else if (slot->bitmap.pixel_mode == FT_PIXEL_MODE_MONO)
            a = (row[bx / 8] & (0x80 >> (bx % 8))) ? 255 : 0;
          else
            continue;
          out->pixels[(size_t)y * width + (size_t)x] =
              (unsigned char)((unsigned)
                                  out->pixels[(size_t)y * width + (size_t)x] *
                              (255 - a) / 255);
        }
    }
  return EXR_OK;
font_error:
  exr_bitmap_free(out);
  return exr_fail(e, EXR_FONT, "Glyph rasterization failed");
}
