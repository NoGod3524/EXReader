/* SPDX-License-Identifier: MIT */
#ifndef EXR_PPT_INTERNAL_H
#define EXR_PPT_INTERNAL_H
#include "base_internal.h"
#include "exr/pdf.h"
#define EXR_PPT_MAX_STREAM ((size_t)256 * 1024 * 1024)
typedef struct {
  unsigned char *document,*summary;
  size_t document_size,summary_size;
} exr_ppt_streams;
typedef struct {
  size_t pages,slide_containers;
  double width,height;
  int mismatch;
} exr_ppt_info;
typedef struct {
  unsigned type;
  double bounds[4]; /* Page points, y down; reversed endpoints preserve flips. */
  exr_draw_style style;
} exr_ppt_shape;
typedef struct { size_t first,count; } exr_ppt_slide;
typedef struct {
  exr_ppt_shape *shapes;
  exr_ppt_slide *slides;
  size_t count,capacity,pages;
  size_t malformed,missing_anchor,depth,zero_extent,unsupported;
} exr_ppt_drawing;
exr_status exr_ppt_cfb(const void *data,size_t size,const exr_control *control,exr_ppt_streams *out,exr_error *e);
void exr_ppt_streams_free(exr_ppt_streams *streams);
exr_status exr_ppt_records(const void *data,size_t size,const exr_control *control,exr_ppt_info *out,exr_error *e);
exr_status exr_ppt_read_drawing(const void *data,size_t size,const exr_ppt_info *info,const exr_control *control,exr_ppt_drawing *out,exr_error *e);
void exr_ppt_drawing_free(exr_ppt_drawing *drawing);
exr_status exr_ppt_open_memory(const void *data,size_t size,const exr_fixed_open_options *options,exr_fixed_document **out,exr_error *e);
exr_status exr_ppt_open_file(const char *path,const exr_fixed_open_options *options,exr_fixed_document **out,exr_error *e);
#endif
