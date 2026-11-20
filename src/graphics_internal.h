/* SPDX-License-Identifier: MIT */
#ifndef EXR_GRAPHICS_INTERNAL_H
#define EXR_GRAPHICS_INTERNAL_H
#include "base_internal.h"
#include "exr/graphics.h"
/* A zero limit selects the default raster-work budget. */
typedef struct { size_t used,limit; } exr_raster_work;
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
/* A dense clip has one row per device row. Rectangular intersections store
   zero, first, interior and last rows. Only the two boundary rows can differ
   from the interior, even after multiplying previously rounded clip bytes. */
typedef struct {
  exr_bitmap bitmap;
  size_t refs;
  uint32_t dirty_top,dirty_bottom,dirty_left,dirty_right;
  uint32_t compact_height; /* logical height when bitmap.height is four */
  uint8_t full_span; /* compact viewport clip, outside the dense mask budget */
  uint16_t *solid_spans; uint32_t solid_top,solid_bottom;
  uint16_t solid_rect[4]; uint8_t solid_is_rect;
} exr_clip_mask;
static inline const unsigned char *exr_clip_row(const exr_clip_mask *clip,size_t y) {
  if(!clip) return NULL;
  if(clip->compact_height) {
    if(y<clip->dirty_top || y>=clip->dirty_bottom) y=0;
    else if(y==clip->dirty_top) y=1;
    else if(y+1==clip->dirty_bottom) y=3;
    else y=2;
  }
  return clip->bitmap.pixels+y*clip->bitmap.stride;
}
static inline uint32_t exr_clip_height(const exr_clip_mask *clip) {
  return clip->compact_height ? clip->compact_height : clip->bitmap.height;
}
/* bounds = {left,top,right,bottom}: both coverage masks are zero outside it. */
exr_status exr_composite_compound_cmyk(exr_bitmap *target,const exr_bitmap *fill,const exr_bitmap *stroke,const uint32_t bounds[4],
  const double fill_cmyk[4],const double stroke_cmyk[4],double fill_alpha,double stroke_alpha,exr_blend_mode mode,
  const exr_clip_mask *clip,exr_composite_state *state,exr_raster_work *work,const exr_control *control,exr_error *error);
exr_status exr_composite_compound_cmyk_at(exr_bitmap *target,const exr_bitmap *fill,const exr_bitmap *stroke,uint32_t mask_x,uint32_t mask_y,
  const uint32_t bounds[4],const double fill_cmyk[4],const double stroke_cmyk[4],double fill_alpha,double stroke_alpha,exr_blend_mode mode,
  const exr_clip_mask *clip,exr_composite_state *state,exr_raster_work *work,const exr_control *control,exr_error *error);
exr_status exr_composite_initialize(exr_bitmap *child,exr_composite_state *state,const exr_bitmap *parent,
  const exr_composite_state *parent_state,int origin_x,int origin_y,exr_raster_work *work,const exr_control *control,exr_error *error);
exr_status exr_composite_compound(exr_bitmap *target,const exr_bitmap *fill,const exr_bitmap *stroke,const uint32_t bounds[4],
  uint32_t fill_color,uint32_t stroke_color,exr_blend_mode mode,const exr_clip_mask *clip,exr_composite_state *state,
  exr_raster_work *work,const exr_control *control,exr_error *error);
exr_status exr_composite_compound_at(exr_bitmap *target,const exr_bitmap *fill,const exr_bitmap *stroke,uint32_t mask_x,uint32_t mask_y,
  const uint32_t bounds[4],uint32_t fill_color,uint32_t stroke_color,exr_blend_mode mode,const exr_clip_mask *clip,exr_composite_state *state,
  exr_raster_work *work,const exr_control *control,exr_error *error);
exr_status exr_bitmap_to_gray(exr_bitmap *bitmap,const exr_control *control,exr_error *error);
/* Conservative x extents in horizontal bands of an initially transparent layer. */
typedef struct {
  uint32_t band_height;
  struct { uint16_t left,right; } bands[32];
} exr_layer_damage;
exr_status exr_composite_frame(exr_bitmap *target,const exr_bitmap *source,double opacity,exr_blend_mode mode,
  const exr_clip_mask *clip,exr_composite_state *target_state,const exr_composite_state *source_state,
  const exr_layer_damage *damage,int origin_x,int origin_y,exr_raster_work *work,const exr_control *control,exr_error *error);

exr_status exr_draw_sink_snapshot(const exr_draw_sink_ex *input,exr_draw_sink_ex *out,exr_error *error);
exr_status exr_image_dimensions(const void *data,size_t size,uint32_t *width,uint32_t *height,exr_error *error);
/* Multi-page/animated decoding shared by CBZ and public wrappers. page is
   zero-based and preserves source order. Cancellation is page/row granular. */
exr_status exr_image_decode_page_control(const void *data,size_t size,size_t page,
  const exr_control *control,exr_bitmap *out,exr_error *error);
exr_status exr_image_decode_control(const void *data,size_t size,const exr_control *control,
  exr_bitmap *out,exr_error *error);

int exr_image_format_detect(const void *data,size_t size);
#define EXR_SHADING_SOURCE_MAGIC 0x455852415849414cULL
typedef struct {
  exr_paint_sample_fn sample;uint64_t magic;
  double coords[6];const double *rgb;const unsigned char *inks;exr_raster_work *work;
  double axial_scale,axial_x,axial_y,axial_ux,axial_uy,axial_length;
  double cached_coord[2],cached_color[2][4],cached_shape[2];
  unsigned type,extend0,extend1,cached_space,cached_axis,cached_slot;
} exr_shading_paint_source;
#endif
