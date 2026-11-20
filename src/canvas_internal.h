/* SPDX-License-Identifier: MIT */
#ifndef EXR_CANVAS_INTERNAL_H
#define EXR_CANVAS_INTERNAL_H
#include "vector_internal.h"
#include "buffer_pool_internal.h"
typedef struct {
  exr_layer_damage damage;
  int origin_x,origin_y; /* working-buffer origin in canvas coordinates */
  int parent_offset_x,parent_offset_y;
  unsigned parent_gray_groups;
  unsigned parent_cmyk_groups,parent_alpha_flags;
  exr_bitmap bitmap;exr_composite_state *composite;exr_clip_mask *clip,*pending,**pending_groups;
  size_t depth,group_depth;double opacity;exr_blend_mode blend,parent_blend;
  const unsigned char *soft_mask;unsigned char *soft_mask_owned;
  size_t soft_mask_width,soft_mask_height;
} exr_canvas_layer;
typedef struct exr_path_cache_entry exr_path_cache_entry;
#define EXR_PATH_CACHE_SLOTS 8
#define EXR_PATH_CACHE_SEEN 32
struct exr_canvas {
  exr_buffer_pool local_pool,*pool;
  struct exr_icc *cmyk_profile;
  exr_bitmap bitmap;exr_composite_state *composite; exr_control control; exr_error failure;
  exr_clip_mask *clip,*saved[160],*group,*groups[64];
  exr_canvas_layer *layers;size_t layer_depth,layer_capacity,layer_bytes,layer_budget,layer_limit;
  exr_blend_mode blend,saved_blend[160];
  size_t depth,group_depth,mask_bytes,full_span_bytes,mask_count,mask_budget;
  exr_raster_work work;
  const unsigned char *soft_mask;size_t soft_mask_width,soft_mask_height;exr_composite_state mask_state;
  unsigned char *soft_mask_owned; /* cropped copy while a region buffer is active */
  unsigned alpha_flags,saved_alpha_flags[160];
  unsigned gray_groups; /* active group blends in DeviceGray */
  unsigned cmyk_groups; /* active group blends in DeviceCMYK */
  unsigned fixed_bitmap; /* Private canvas owned by fixed_render. */
  int offset_x,offset_y; /* canvas coordinate of the active working buffer's top-left */
  size_t canvas_width,canvas_height; /* device extent, independent of the active buffer */
  exr_clip_mask *spare_masks[4]; /* released masks kept for reuse within this canvas */
  exr_vector_scratch vector_scratch; /* reusable scanline workspace freed with the canvas */
  uint64_t path_seen[EXR_PATH_CACHE_SEEN];
  unsigned path_seen_pos,path_cache_tick;
  exr_path_cache_entry *path_cache[EXR_PATH_CACHE_SLOTS];
  size_t path_cache_bytes;
};
exr_status exr_canvas_create_pooled(const exr_canvas_config *config,exr_buffer_pool *pool,exr_canvas **out,exr_error *error);
/* Sets render-scoped overrides on a newly created canvas. */
void exr_canvas_render_limits(exr_canvas *canvas,size_t layer_budget,size_t work_budget);
/* Returns the canvas for the native sink, or NULL for external consumers. */
exr_canvas *exr_canvas_sink_target(const exr_draw_sink_ex *sink);
exr_status exr_canvas_image_excluding(exr_canvas *canvas,const exr_image_layer *image,
  const double matrix[6],double alpha,const int cover[4],exr_error *error);
/* Graphics-state soft mask: page-space, one byte per pixel; NULL clears it. */
exr_status exr_canvas_soft_mask(exr_canvas *canvas,const unsigned char *mask,size_t width,size_t height,exr_error *error);
/* Clip-union construction is internal until the generic scene API is settled. */
void exr_canvas_union_abort(exr_canvas *canvas);
exr_status exr_canvas_union_add(exr_canvas *canvas,const exr_path_segment *segments,size_t count,
                                  const double matrix[6],exr_fill_rule rule,exr_error *error);
exr_status exr_canvas_union_commit(exr_canvas *canvas,exr_error *error);
#endif
