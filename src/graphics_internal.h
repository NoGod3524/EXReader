/* SPDX-License-Identifier: MIT */
#ifndef EXR_GRAPHICS_INTERNAL_H
#define EXR_GRAPHICS_INTERNAL_H
#include "base_internal.h"
#include "exr/graphics.h"
/* Internal hint: this group's caller relies on whole-canvas buffer semantics. */
#define EXR_GROUP_WHOLE_BUFFER 0x80u
/* Internal flag: the group blends in DeviceGray, so painted colours are reduced
   to luminance before they reach the raster. */
#define EXR_GROUP_GRAY 0x100u
/* Private four-component JPEG samples, before PDF Decode and color conversion.
   channels==4 stores C/M/Y/K, not RGBA. */
exr_status exr_jpeg_cmyk_decode(const void *data,size_t size,const exr_control *control,
                               exr_bitmap *out,exr_error *error);
/* Non-isolated working pixels: premultiplied RGB, complete alpha, group-only
   alpha. A NULL buffer keeps the original compact 8-bit drawing path. */
typedef struct exr_composite_state {
  struct exr_icc *cmyk_profile;float *pixels;float *cmyk_pixels;exr_bitmap backdrop;const struct exr_composite_state *backdrop_state;
  float *shape; /* Allocated only for groups consumed by a knockout/shape-tracked parent. */
  uint32_t left,top,right,bottom;unsigned depth;unsigned knockout,isolated,gray;
  unsigned alpha_flags;
  unsigned backdrop_transparent; /* Non-isolated child of an isolated knockout. */
  /* Working buffers may cover only a sub-rectangle of the canvas. */
  int origin_x,origin_y;
  /* Graphics-state soft mask: one byte per page pixel, 255 = fully visible. */
  const unsigned char *soft_mask;size_t soft_mask_width,soft_mask_height;
} exr_composite_state;
exr_status exr_sink_begin_group(const exr_draw_sink_ex *sink,double opacity,exr_blend_mode mode,unsigned flags,exr_error *error);
exr_status exr_sink_soft_mask(const exr_draw_sink_ex *sink,const unsigned char *mask,size_t width,size_t height,exr_error *error);
exr_status exr_sink_alpha_source(const exr_draw_sink_ex *sink,unsigned flags,exr_error *error);
exr_status exr_sink_extent(const exr_draw_sink_ex *sink,unsigned *width,unsigned *height,exr_error *error);
/* DeviceCMYK device model shared by page painting, mesh shadings and groups. */
uint32_t exr_gray_color(uint32_t color);
void exr_cmyk_from_rgb(const double rgb[3],double cmyk[4]);
exr_status exr_composite_compound_cmyk(exr_bitmap *target,const exr_bitmap *fill,const exr_bitmap *stroke,
  const double fill_cmyk[4],const double stroke_cmyk[4],double fill_alpha,double stroke_alpha,exr_blend_mode mode,
  const exr_bitmap *clip,exr_composite_state *state,size_t *work,const exr_control *control,exr_error *error);exr_status exr_composite_initialize(exr_bitmap *child,exr_composite_state *state,const exr_bitmap *parent,
  const exr_composite_state *parent_state,int origin_x,int origin_y,size_t *work,const exr_control *control,exr_error *error);
exr_status exr_composite_compound(exr_bitmap *target,const exr_bitmap *fill,const exr_bitmap *stroke,
  uint32_t fill_color,uint32_t stroke_color,exr_blend_mode mode,const exr_bitmap *clip,exr_composite_state *state,
  size_t *work,const exr_control *control,exr_error *error);
exr_status exr_bitmap_to_gray(exr_bitmap *bitmap,const exr_control *control,exr_error *error);
exr_status exr_composite_frame(exr_bitmap *target,const exr_bitmap *source,double opacity,exr_blend_mode mode,
  const exr_bitmap *clip,exr_composite_state *target_state,const exr_composite_state *source_state,
  int origin_x,int origin_y,size_t *work,const exr_control *control,exr_error *error);

exr_status exr_draw_sink_snapshot(const exr_draw_sink_ex *input,exr_draw_sink_ex *out,exr_error *error);
exr_status exr_image_dimensions(const void *data,size_t size,uint32_t *width,uint32_t *height,exr_error *error);

#endif
