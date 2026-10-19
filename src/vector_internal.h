/* SPDX-License-Identifier: MIT */
#ifndef EXR_VECTOR_INTERNAL_H
#define EXR_VECTOR_INTERNAL_H
#include "graphics_internal.h"
typedef struct { double x0,y0,x1,y1; } exr_vector_edge;
typedef exr_fill_rule exr_vector_rule;
#define EXR_VECTOR_NONZERO EXR_FILL_NONZERO
#define EXR_VECTOR_EVENODD EXR_FILL_EVENODD
static inline int exr_vector_work(size_t *work,size_t amount) {
  if(*work>(size_t)256*1024*1024 || amount>(size_t)256*1024*1024-*work) return 0;
  *work+=amount; return 1;
}
typedef exr_path_point exr_vector_point;
typedef exr_path_verb exr_vector_verb;
typedef exr_path_segment exr_vector_segment;
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
typedef exr_line_cap exr_vector_cap;
typedef exr_line_join exr_vector_join;
typedef exr_path_stroke exr_vector_stroke_style;
#define EXR_VECTOR_MOVE EXR_PATH_MOVE
#define EXR_VECTOR_LINE EXR_PATH_LINE
#define EXR_VECTOR_QUAD EXR_PATH_QUAD
#define EXR_VECTOR_CUBIC EXR_PATH_CUBIC
#define EXR_VECTOR_CLOSE EXR_PATH_CLOSE
#define EXR_VECTOR_BUTT EXR_CAP_BUTT
#define EXR_VECTOR_ROUND_CAP EXR_CAP_ROUND
#define EXR_VECTOR_SQUARE EXR_CAP_SQUARE
#define EXR_VECTOR_MITER EXR_JOIN_MITER
#define EXR_VECTOR_ROUND_JOIN EXR_JOIN_ROUND
#define EXR_VECTOR_BEVEL EXR_JOIN_BEVEL
/* Positive width is in source units, then transformed. Width zero is a one-pixel
   hairline in target coordinates. Closed positive-winding polygons form a union. */
exr_status exr_vector_stroke(const exr_vector_polyline *path,const exr_vector_stroke_style *style,
                              const double transform[6],double tolerance,exr_vector_polyline *out,
                              size_t *work,const exr_control *control,exr_error *error);
/* Dash lengths/phase use source coordinates and restart per contour. Odd arrays
   repeat twice; zero-length on entries are retained as two-point dot contours. */
exr_status exr_vector_dash(const exr_vector_polyline *path,const double *lengths,size_t length_count,
                            double phase,exr_vector_polyline *out,size_t *work,
                            const exr_control *control,exr_error *error);
/* Edges describe closed contours in bitmap coordinates. Clip is an optional
   matching 8-bit coverage bitmap. Work is a shared 256M-operation counter.
   A failed/cancelled draw may have modified rows; page rendering discards them. */
exr_status exr_vector_fill(exr_bitmap *bitmap,const exr_vector_edge *edges,size_t count,
                            exr_vector_rule rule,uint32_t color,const exr_bitmap *clip,
                            size_t *work,const exr_control *control,exr_error *error);
/* RGBA source normalized [0,1]^2 (first row at v=0) mapped to target pixels.
   Nearest/bilinear sampling, subpixel edge coverage, straight alpha and clip. */
exr_status exr_vector_image(exr_bitmap *target,const exr_bitmap *source,const double matrix[6],
                             double alpha,int interpolate,const exr_bitmap *clip,size_t *work,
                             const exr_control *control,exr_error *error);
typedef exr_image_layer exr_vector_texture;
/* All layers are borrowed; independent resolutions/filters sample in the same
   normalized space. No image-resolution reduction of an opacity mask. */
exr_status exr_vector_texture_paint(exr_bitmap *target,const exr_vector_texture *source,const double matrix[6],
                                     double alpha,const exr_bitmap *clip,size_t *work,
                                     const exr_control *control,exr_error *error);
exr_status exr_vector_fill_blend(exr_bitmap *bitmap,const exr_vector_edge *edges,size_t count,
  exr_vector_rule rule,uint32_t color,const exr_bitmap *clip,exr_blend_mode mode,exr_composite_state *state,
  size_t *work,const exr_control *control,exr_error *error);
exr_status exr_vector_fill_blend_cmyk(exr_bitmap *bitmap,const exr_vector_edge *edges,size_t count,
  exr_vector_rule rule,const double cmyk[4],double alpha,const exr_bitmap *clip,exr_blend_mode mode,
  exr_composite_state *state,size_t *work,const exr_control *control,exr_error *error);
exr_status exr_vector_texture_blend(exr_bitmap *target,const exr_vector_texture *source,const double matrix[6],
  double alpha,const exr_bitmap *clip,exr_blend_mode mode,exr_composite_state *state,size_t *work,const exr_control *control,exr_error *error);
exr_status exr_vector_texture_blend_inks(exr_bitmap *target,const exr_vector_texture *source,const exr_bitmap *inks,const double matrix[6],
  double alpha,const exr_bitmap *clip,exr_blend_mode mode,exr_composite_state *state,size_t *work,const exr_control *control,exr_error *error);
#endif
