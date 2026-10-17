/* SPDX-License-Identifier: GPL-3.0-only */
#ifndef EXR_VECTOR_INTERNAL_H
#define EXR_VECTOR_INTERNAL_H
#include "internal.h"
typedef struct { double x0,y0,x1,y1; } exr_vector_edge;
typedef enum { EXR_VECTOR_NONZERO,EXR_VECTOR_EVENODD } exr_vector_rule;
static inline int exr_vector_work(size_t *work,size_t amount) {
  if(*work>(size_t)256*1024*1024 || amount>(size_t)256*1024*1024-*work) return 0;
  *work+=amount; return 1;
}
typedef struct { double x,y; } exr_vector_point;
typedef enum { EXR_VECTOR_MOVE,EXR_VECTOR_LINE,EXR_VECTOR_QUAD,EXR_VECTOR_CUBIC,EXR_VECTOR_CLOSE } exr_vector_verb;
typedef struct { exr_vector_verb verb; exr_vector_point points[3]; } exr_vector_segment;
typedef struct { size_t start,count; unsigned closed; } exr_vector_contour;
typedef struct {
  exr_vector_point *points; size_t point_count,point_capacity;
  exr_vector_contour *contours; size_t contour_count,contour_capacity;
} exr_vector_polyline;
void exr_vector_polyline_free(exr_vector_polyline *path);
/* Tolerance is in transformed bitmap pixels. All output arrays are owned. */
exr_status exr_vector_flatten(const exr_vector_segment *segments,size_t count,const double transform[6],
                               double tolerance,exr_vector_polyline *out,size_t *work,
                               const exr_control *control,exr_error *error);
exr_status exr_vector_edges(const exr_vector_polyline *path,int close_open,exr_vector_edge **out,
                             size_t *count,size_t *work,const exr_control *control,exr_error *error);
typedef enum { EXR_VECTOR_BUTT,EXR_VECTOR_ROUND_CAP,EXR_VECTOR_SQUARE } exr_vector_cap;
typedef enum { EXR_VECTOR_MITER,EXR_VECTOR_ROUND_JOIN,EXR_VECTOR_BEVEL } exr_vector_join;
typedef struct { double width,miter_limit; exr_vector_cap cap; exr_vector_join join; } exr_vector_stroke_style;
/* Positive width is in source units, then transformed. Width zero is a one-pixel
   hairline in target coordinates. Closed positive-winding polygons form a union. */
exr_status exr_vector_stroke(const exr_vector_polyline *path,const exr_vector_stroke_style *style,
                              const double transform[6],double tolerance,exr_vector_polyline *out,
                              size_t *work,const exr_control *control,exr_error *error);
/* Edges describe closed contours in bitmap coordinates. Clip is an optional
   matching 8-bit coverage bitmap. Work is a shared 256M-operation counter.
   A failed/cancelled draw may have modified rows; page rendering discards them. */
exr_status exr_vector_fill(exr_bitmap *bitmap,const exr_vector_edge *edges,size_t count,
                            exr_vector_rule rule,uint32_t color,const exr_bitmap *clip,
                            size_t *work,const exr_control *control,exr_error *error);
#endif
