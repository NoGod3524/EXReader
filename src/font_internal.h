/* SPDX-License-Identifier: MIT */
#ifndef EXR_FONT_INTERNAL_H
#define EXR_FONT_INTERNAL_H
#include "base_internal.h"
#include "exr/text.h"
#include <ft2build.h>
#include FT_FREETYPE_H
#include FT_COLOR_H
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
  FT_Color *color_palette; unsigned palette_index,palette_ready;
  struct exr_sbix *sbix; unsigned sbix_checked;
  struct exr_cblc *cblc; unsigned cblc_checked;
  struct exr_svg_table *svg; unsigned svg_checked;
  unsigned design_units,hmetrics,vmetrics,bitmap_only;
  float bitmap_scale_y;
} exr_face;
struct exr_font {
  FT_Library library;
  exr_face *faces;
  size_t count, base_count, refs;
  struct exr_font *fallback;
};
void exr_font_ref(exr_font *font);
FT_Error exr_font_face_open(FT_Library library,const void *data,size_t size,unsigned face_index,FT_Face *out);
int exr_font_face_supported(FT_Face face);
size_t exr_font_order(const exr_font *font, const char *family, unsigned flags,
                       size_t chapter, size_t order[32]);
int exr_font_size(exr_face *font, float size);
exr_status exr_font_colr(exr_face *face,uint32_t glyph,size_t palette,uint32_t foreground,
                         exr_font_color_layer layers[256],size_t *count,size_t *work);
/* Owned straight-RGBA intrinsic color surface in device pixels. left/top follow
   exr_glyph_image (x right, y down, origin at the glyph origin). */
typedef struct { exr_bitmap bitmap; float left,top; } exr_color_surface;
exr_status exr_font_colrv1(exr_face *face,uint32_t glyph,float pixels,uint32_t foreground,
                           exr_color_surface *out,size_t *work,const exr_control *control,exr_error *error);
exr_status exr_font_svg(exr_face *face,uint32_t glyph,float pixels,uint32_t foreground,
                        exr_color_surface *out,size_t *work,const exr_control *control,exr_error *error);
void exr_font_svg_free(exr_face *face);
int exr_font_svg_covers(exr_face *face,uint32_t glyph,size_t *work,const exr_control *control,exr_error *error);
void exr_font_bitmaps_free(exr_face *face);
exr_status exr_font_image(exr_face *face,uint32_t glyph,float pixels,exr_glyph_image *out,
                               size_t *work,const exr_control *control,exr_error *error);
exr_status exr_font_bitmap_vertical(exr_face *face,uint32_t glyph,float pixels,float *x,float *y,
                                    const exr_control *control,exr_error *error);
static inline float exr_font_ascent(const exr_face *face) { return (float)face->face->size->metrics.ascender/64*face->bitmap_scale_y; }
static inline float exr_font_descent(const exr_face *face) { return -(float)face->face->size->metrics.descender/64*face->bitmap_scale_y; }
int exr_measure(exr_face *font, uint32_t glyph, unsigned flags, float *advance);
int exr_measure_vertical(exr_face *font, uint32_t glyph, unsigned flags, float *advance);
float exr_kern(exr_face *font, uint32_t left, uint32_t right);

int exr_family_next(const char *value,size_t *offset,char out[128]);
int exr_family_equal(const char *a,const char *b);
#endif
