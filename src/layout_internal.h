/* SPDX-License-Identifier: MIT */
#ifndef EXR_LAYOUT_INTERNAL_H
#define EXR_LAYOUT_INTERNAL_H
#include "style_internal.h"
#include "formats_internal.h"
#include "graphics_internal.h"
#include "font_internal.h"
typedef struct {
  size_t resource;
  exr_bitmap bitmap;
  size_t *refs; /* Shared immutable decoded pixels across independent pages. */
  unsigned evictable; /* Unreferenced at the preceding top-level page boundary. */
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
  exr_writing_mode writing_mode;
  float flow_inline, flow_block; /* Private logical extents of a reusable flow fragment. */
  float first_baseline; /* First line's logical block-axis baseline, including ruby. */
  unsigned has_baseline;
  int source_overlaps; /* Page source envelopes overlap; consult actual glyph ranges. */
};
exr_status exr_layout_image_asset(const exr_document *doc, exr_layout *assets,
                                    const exr_layout_config *config, size_t resource,
                                    const exr_bitmap **bitmap, exr_error *error);
void exr_layout_ref(exr_layout *layout);
exr_status exr_publication_retain_epub(exr_publication *publication,const exr_document **index,exr_error *error);
size_t exr_publication_index_memory(const exr_publication *publication);
void exr_pager_adopt_chapter(exr_pager *pager,void *chapter,void (*release)(void *),
                            exr_chapter_stats (*statistics)(const void *));
size_t exr_pager_continuation_bytes(const exr_pager *pager);
exr_status exr_chapter_cfi_create(void *reader,const exr_cfi_point *point,size_t context,
  const exr_control *control,char **cfi,exr_error *error);
exr_status exr_chapter_cfi_resolve(void *reader,const char *cfi,const exr_control *control,
  exr_cfi_point *point,exr_error *error);
exr_status exr_book_fonts(const exr_document *doc, exr_font *fallback,
                           const exr_style *styles, const exr_font_rule *rules, size_t count,
                           const exr_control *control, exr_font **out, exr_error *error);
exr_status exr_layout_validate(const exr_layout_config *config, exr_error *error);
exr_status exr_flow_create(const exr_document *doc, exr_font *font, const exr_layout_config *config,
                           exr_layout **out, exr_error *error);
#endif
