/* SPDX-License-Identifier: GPL-3.0-only */
#ifndef EXR_VECTOR_INTERNAL_H
#define EXR_VECTOR_INTERNAL_H
#include "internal.h"
typedef struct { double x0,y0,x1,y1; } exr_vector_edge;
typedef enum { EXR_VECTOR_NONZERO,EXR_VECTOR_EVENODD } exr_vector_rule;
/* Edges describe closed contours in bitmap coordinates. Clip is an optional
   matching 8-bit coverage bitmap. Work is a shared 256M-operation counter.
   A failed/cancelled draw may have modified rows; page rendering discards them. */
exr_status exr_vector_fill(exr_bitmap *bitmap,const exr_vector_edge *edges,size_t count,
                            exr_vector_rule rule,uint32_t color,const exr_bitmap *clip,
                            size_t *work,const exr_control *control,exr_error *error);
#endif
