/* SPDX-License-Identifier: GPL-3.0-only */
#include "layout_internal.h"
#include FT_SYNTHESIS_H
static void pixel(exr_bitmap *b, int x, int y, uint32_t color, unsigned coverage) {
  unsigned alpha = (color & 255) * coverage / 255;
  unsigned r = color >> 24, g = (color >> 16) & 255, blue = (color >> 8) & 255;
  unsigned char *p = b->pixels + (size_t)y * b->stride + (size_t)x * b->channels;
  if (b->channels == 1) {
    unsigned gray = (r * 77 + g * 150 + blue * 29 + 128) >> 8;
    *p = (unsigned char)((*p * (255 - alpha) + gray * alpha + 127) / 255);
  } else {
    p[0] = (unsigned char)((p[0] * (255 - alpha) + r * alpha + 127) / 255);
    p[1] = (unsigned char)((p[1] * (255 - alpha) + g * alpha + 127) / 255);
    p[2] = (unsigned char)((p[2] * (255 - alpha) + blue * alpha + 127) / 255);
  }
}
static void rectangle(exr_bitmap *b, float x, float y, float w, float h, uint32_t color) {
  int left = (int)fmaxf(0, floorf(x)), top = (int)fmaxf(0, floorf(y));
  int right = (int)fminf((float)b->width, ceilf(x + w)),
      bottom = (int)fminf((float)b->height, ceilf(y + h));
  int xx, yy;
  if (!(color & 255) || w <= 0 || h <= 0)
    return;
  for (yy = top; yy < bottom; yy++)
    for (xx = left; xx < right; xx++)
      pixel(b, xx, yy, color, 255);
}
static void picture(exr_bitmap *out, const exr_box *box, const exr_bitmap *src) {
  int left = (int)fmaxf(0, ceilf(box->x)), top = (int)fmaxf(0, ceilf(box->y));
  int right = (int)fminf((float)out->width, ceilf(box->x + box->width));
  int bottom = (int)fminf((float)out->height, ceilf(box->y + box->height));
  int x, y;
  if (box->width <= 0 || box->height <= 0)
    return;
  for (y = top; y < bottom; y++)
    for (x = left; x < right; x++) {
      float sx =
          fmaxf(0, fminf((float)src->width - 1,
                         ((float)x + 0.5f - box->x) / box->width * (float)src->width - 0.5f));
      float sy =
          fmaxf(0, fminf((float)src->height - 1,
                         ((float)y + 0.5f - box->y) / box->height * (float)src->height - 0.5f));
      uint32_t x0 = (uint32_t)sx, y0 = (uint32_t)sy;
      uint32_t x1 = x0 + 1 < src->width ? x0 + 1 : x0, y1 = y0 + 1 < src->height ? y0 + 1 : y0;
      float fx = sx - (float)x0, fy = sy - (float)y0;
      float weights[4] = {(1 - fx) * (1 - fy), fx * (1 - fy), (1 - fx) * fy, fx * fy};
      const unsigned char *samples[4] = {src->pixels + (size_t)y0 * src->stride + x0 * 4,
                                         src->pixels + (size_t)y0 * src->stride + x1 * 4,
                                         src->pixels + (size_t)y1 * src->stride + x0 * 4,
                                         src->pixels + (size_t)y1 * src->stride + x1 * 4};
      float alpha = 0, colors[3] = {0};
      unsigned k, channel;
      uint32_t color = 0;
      for (k = 0; k < 4; k++) {
        float a = weights[k] * (float)samples[k][3];
        alpha += a;
        for (channel = 0; channel < 3; channel++)
          colors[channel] += a * (float)samples[k][channel];
      }
      if (alpha <= 0)
        continue;
      for (channel = 0; channel < 3; channel++)
        color = (color << 8) | (uint32_t)lroundf(colors[channel] / alpha);
      color = (color << 8) | (uint32_t)lroundf(alpha);
      pixel(out, x, y, color, 255);
    }
}
static exr_status render(const exr_layout *l, exr_font *f, size_t page, unsigned channels,
                         exr_bitmap *out, exr_error *e) {
  size_t i, j;
  uint32_t width, height;
  const exr_page *p;
  if (!l || !f || !out || page >= l->page_count)
    return exr_fail(e, EXR_ARGUMENT, "Invalid render arguments");
  memset(out, 0, sizeof(*out));
  width = (uint32_t)ceilf(l->options.width);
  height = (uint32_t)ceilf(l->options.height);
  if ((size_t)width * height * channels > 64 * 1024 * 1024)
    return exr_fail(e, EXR_LIMIT, "Page bitmap exceeds 64 MiB");
  out->pixels = malloc((size_t)width * height * channels);
  if (!out->pixels)
    return EXR_MEMORY;
  out->width = width;
  out->height = height;
  out->stride = width * channels;
  out->channels = channels;
  memset(out->pixels, 255, (size_t)out->stride * height);
  p = &l->pages[page];
  for (i = p->box_start; i < p->box_start + p->box_count; i++) {
    const exr_box *b = &l->boxes[i];
    float bw = fminf(b->border_width, fminf(b->width, b->height) / 2);
    rectangle(out, b->x, b->y, b->width, b->height, b->background);
    if (b->kind == EXR_BOX_IMAGE && !b->flags) {
      for (j = 0; j < l->image_count; j++)
        if (l->images[j].resource == b->resource) {
          picture(out, b, &l->images[j].bitmap);
          break;
        }
    }
    if (bw > 0) {
      rectangle(out, b->x, b->y, b->width, bw, b->border_color);
      rectangle(out, b->x, b->y + b->height - bw, b->width, bw, b->border_color);
      rectangle(out, b->x, b->y, bw, b->height, b->border_color);
      rectangle(out, b->x + b->width - bw, b->y, bw, b->height, b->border_color);
    }
  }
  for (i = p->line_start; i < p->line_start + p->line_count; i++)
    for (j = l->lines[i].glyph_start; j < l->lines[i].glyph_start + l->lines[i].glyph_count; j++) {
      const exr_glyph *g = &l->glyphs[j];
      FT_GlyphSlot slot;
      unsigned by, bx;
      int left, top;
      if (g->flags & EXR_GLYPH_HIDDEN)
        continue;
      if (exr_font_size(f, g->size) || FT_Load_Glyph(f->face, g->glyph, FT_LOAD_DEFAULT))
        goto font_error;
      if (g->flags & 1)
        FT_GlyphSlot_Embolden(f->face->glyph);
      if (g->flags & 2)
        FT_GlyphSlot_Oblique(f->face->glyph);
      if (FT_Render_Glyph(f->face->glyph, FT_RENDER_MODE_NORMAL))
        goto font_error;
      slot = f->face->glyph;
      left = (int)lroundf(g->x) + slot->bitmap_left;
      top = (int)lroundf(g->baseline) - slot->bitmap_top;
      for (by = 0; by < slot->bitmap.rows; by++)
        for (bx = 0; bx < slot->bitmap.width; bx++) {
          int x = left + (int)bx, y = top + (int)by;
          const unsigned char *row;
          unsigned a;
          if (x < 0 || y < 0 || (uint32_t)x >= width || (uint32_t)y >= height ||
              (float)x < g->clip_left || (float)x >= g->clip_right)
            continue;
          row = slot->bitmap.buffer + (ptrdiff_t)by * slot->bitmap.pitch;
          if (slot->bitmap.pixel_mode == FT_PIXEL_MODE_GRAY)
            a = row[bx];
          else if (slot->bitmap.pixel_mode == FT_PIXEL_MODE_MONO)
            a = (row[bx / 8] & (0x80 >> (bx % 8))) ? 255 : 0;
          else
            continue;
          pixel(out, x, y, g->color, a);
        }
    }
  return EXR_OK;
font_error:
  exr_bitmap_free(out);
  return exr_fail(e, EXR_FONT, "Glyph rasterization failed");
}
exr_status exr_render_page(const exr_layout *l, exr_font *f, size_t page, exr_bitmap *out,
                           exr_error *e) {
  return render(l, f, page, 1, out, e);
}
exr_status exr_render_page_color(const exr_layout *l, exr_font *f, size_t page, exr_bitmap *out,
                                 exr_error *e) {
  return render(l, f, page, 4, out, e);
}
