/* SPDX-License-Identifier: MIT */
#ifndef EXR_PPT_INTERNAL_H
#define EXR_PPT_INTERNAL_H
#include "base_internal.h"
#include "exr/pdf.h"
#include "exr/font_manager.h"
#define EXR_PPT_MAX_STREAM ((size_t)256 * 1024 * 1024)
typedef struct {
  unsigned char *document,*summary,*pictures;
  size_t document_size,summary_size,pictures_size;
} exr_ppt_streams;
typedef struct {
  size_t pages,slide_containers;
  double width,height;
  int mismatch;
} exr_ppt_info;
typedef struct {
  double size,line,before,after,margin,indent;
  const char *family,*ea;
  uint32_t color,bullet;
  unsigned flags;
  int align,line_pct,before_pct,after_pct;
  const char *bullet_family;
  uint32_t bullet_color;
  double bullet_size; /* zero inherits, negative is a ratio, positive points. */
} exr_ppt_text_style;
typedef struct { size_t start,end; exr_ppt_text_style style; } exr_ppt_text_run;
typedef struct { size_t start,end; exr_ppt_text_style style; exr_layout *layout; } exr_ppt_text_paragraph;
typedef struct {
  char *value;
  size_t length;
  exr_ppt_text_run *runs;
  size_t run_count;
  exr_ppt_text_paragraph *paragraphs;
  size_t paragraph_count;
  double inset[4]; /* top, right, bottom, left, in points. */
  int anchor,wrap;
} exr_ppt_text;
typedef struct { size_t faces[32],count; exr_font *font; } exr_ppt_text_font;

typedef struct {
  unsigned type;
  double bounds[4]; /* Page points, y down; reversed endpoints preserve flips. */
  exr_draw_style style;
  size_t blip; /* One-based BStore index; zero means a path fill. */
  uint32_t gradient[2];
  int has_gradient;
  exr_ppt_text *text;
} exr_ppt_shape;

typedef struct {
  const unsigned char *encoded; /* Borrowed only while reading the drawing. */
  size_t size;
  unsigned type,state; /* 0 unread, 1 decoded, 2 damaged, 3 unsupported. */
  exr_bitmap bitmap;
} exr_ppt_blip;
typedef struct { size_t first,count; } exr_ppt_slide;
typedef struct {
  exr_ppt_shape *shapes;
  exr_ppt_slide *slides;
  size_t count,capacity,pages;
  size_t malformed,missing_anchor,depth,zero_extent,unsupported;
  exr_ppt_blip *blips;
  size_t blip_count,blip_capacity,image_bytes;
  size_t bad_pib,unknown_blip,image_decode,gradient_horizontal,gradient_missing,scheme;
  char **fonts;
  size_t font_count,font_capacity;
  size_t text_runs,text_font_index,text_color_index,text_unicode,text_bytes_fallback,text_malformed;
  exr_font_manager *font_manager;
  exr_ppt_text_font *text_fonts;
  size_t text_font_count,text_font_capacity,font_bytes,text_bytes;
  exr_buffer font_fallbacks,glyph_fallbacks;
} exr_ppt_drawing;
exr_status exr_ppt_text_layout(exr_ppt_drawing *drawing,const exr_control *control,exr_error *e);
exr_status exr_ppt_text_draw(const exr_ppt_shape *shape,const double matrix[6],const exr_draw_sink *sink,const exr_control *control,exr_error *e);
void exr_ppt_text_free(exr_ppt_drawing *drawing);
exr_status exr_ppt_cfb(const void *data,size_t size,const exr_control *control,exr_ppt_streams *out,exr_error *e);
void exr_ppt_streams_free(exr_ppt_streams *streams);
exr_status exr_ppt_records(const void *data,size_t size,const exr_control *control,exr_ppt_info *out,exr_error *e);
exr_status exr_ppt_read_drawing(const exr_ppt_streams *streams,const exr_ppt_info *info,const exr_control *control,exr_ppt_drawing *out,exr_error *e);
void exr_ppt_drawing_free(exr_ppt_drawing *drawing);
exr_status exr_ppt_open_memory(const void *data,size_t size,const exr_fixed_open_options *options,exr_fixed_document **out,exr_error *e);
exr_status exr_ppt_open_file(const char *path,const exr_fixed_open_options *options,exr_fixed_document **out,exr_error *e);
#endif
