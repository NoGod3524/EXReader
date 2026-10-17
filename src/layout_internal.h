/* SPDX-License-Identifier: GPL-3.0-only */
#ifndef EXR_LAYOUT_INTERNAL_H
#define EXR_LAYOUT_INTERNAL_H
#include "internal.h"
#include <ft2build.h>
#include FT_FREETYPE_H
typedef struct {
  FT_Face face;
  unsigned char *bytes;
  size_t bytes_size, scope;
  char family[128];
  unsigned style_flags;
  float *advances;
  unsigned char *measured;
  size_t metric_count;
  FT_F26Dot6 metric_size;
  struct exr_ot_state *ot;
} exr_face;
struct exr_font {
  FT_Library library;
  exr_face *faces;
  size_t count, base_count, refs;
  struct exr_font *fallback;
};
typedef struct {
  size_t resource;
  exr_bitmap bitmap;
  size_t *refs; /* Shared immutable decoded pixels across independent pages. */
} exr_cached_image;
struct exr_layout {
  size_t refs;
  exr_layout_options options;
  exr_glyph *glyphs;
  size_t glyph_count, glyph_cap;
  exr_line *lines;
  size_t line_count, line_cap;
  exr_page *pages;
  size_t page_count, page_cap;
  exr_box *boxes;
  size_t box_count, box_cap;
  exr_cached_image *images;
  size_t image_count, image_cap, image_bytes;
  exr_style *styles;
  size_t style_count;
  size_t work_glyphs;
  size_t shape_work;
  size_t glyph_limit; /* Internal queue allocation limit; zero for ordinary layouts. */
  exr_font *font; /* Retained effective font set, including selected book fonts. */
  exr_paint *paints;
  size_t paint_count;
  exr_positioned_page *positioned;
};
exr_status exr_layout_image_asset(const exr_document *doc, exr_layout *assets,
                                    const exr_layout_config *config, size_t resource,
                                    const exr_bitmap **bitmap, exr_error *error);
void exr_font_ref(exr_font *font);
void exr_layout_ref(exr_layout *layout);
exr_status exr_book_fonts(const exr_document *doc, exr_font *fallback,
                           const exr_style *styles, const exr_font_rule *rules, size_t count,
                           const exr_control *control, exr_font **out, exr_error *error);
size_t exr_font_order(const exr_font *font, const char *family, unsigned flags,
                       size_t chapter, size_t order[32]);
int exr_font_size(exr_face *font, float size);
int exr_measure(exr_face *font, uint32_t glyph, unsigned flags, float *advance);
float exr_kern(exr_face *font, uint32_t left, uint32_t right);
exr_status exr_layout_validate(const exr_layout_config *config, exr_error *error);
exr_status exr_flow_create(const exr_document *doc, exr_font *font, const exr_layout_config *config,
                           exr_layout **out, exr_error *error);
#endif
