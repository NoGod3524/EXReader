/* SPDX-License-Identifier: GPL-3.0-only */
#ifndef EXR_CANVAS_INTERNAL_H
#define EXR_CANVAS_INTERNAL_H
#include "vector_internal.h"
typedef struct { exr_bitmap bitmap; size_t refs; } exr_clip_mask;
struct exr_canvas {
  exr_bitmap bitmap; exr_control control; exr_error failure;
  exr_clip_mask *clip,*saved[160],*group;
  size_t depth,mask_bytes,mask_count,mask_budget,work;
};
/* Clip-union construction is internal until the generic scene API is settled. */
void exr_canvas_union_abort(exr_canvas *canvas);
exr_status exr_canvas_union_add(exr_canvas *canvas,const exr_path_segment *segments,size_t count,
                                  const double matrix[6],exr_fill_rule rule,exr_error *error);
exr_status exr_canvas_union_commit(exr_canvas *canvas,exr_error *error);
#endif
