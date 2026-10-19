/* SPDX-License-Identifier: GPL-3.0-only */
#ifndef EXR_PDF_RASTER_INTERNAL_H
#define EXR_PDF_RASTER_INTERNAL_H
#include "pdf_internal.h"
/* A host program is borrowed through the whole render; embedded fonts win. */
typedef exr_status (*exr_pdf_program_fn)(void *context,const exr_pdf_font_info *font,
                                         exr_font_input *source,exr_error *error);
exr_status exr_pdf_paint_content(exr_pdf_file *file,uint32_t resources,const void *content,size_t size,
                                  const double initial[6],const exr_draw_sink *sink,exr_pdf_program_fn program,void *program_context,
                                  size_t *work,const exr_control *control,exr_error *error);
exr_status exr_pdf_paint_content_ex(exr_pdf_file *file,uint32_t resources,const void *content,size_t size,
  const double initial[6],const exr_draw_sink_ex *sink,exr_pdf_program_fn program,void *context,
  size_t *work,const exr_control *control,exr_error *error);
exr_status exr_pdf_paint_page_ex(exr_pdf_file *file,const exr_pdf_page_info *page,const void *content,size_t size,
  const double initial[6],const exr_draw_sink_ex *sink,exr_pdf_program_fn program,void *context,
  size_t *work,const exr_control *control,exr_error *error);
/* Paint page content, then normal annotation appearances in isolated scopes. */
exr_status exr_pdf_paint_page(exr_pdf_file *file,const exr_pdf_page_info *page,const void *content,size_t size,
                               const double initial[6],const exr_draw_sink *sink,exr_pdf_program_fn program,void *program_context,
                               size_t *work,const exr_control *control,exr_error *error);
typedef struct {
  uint32_t width,height,channels,background;
  size_t mask_budget; /* zero -> 64 MiB, shared immutable clips and text union */
  exr_pdf_program_fn program; void *context;
  const double *initial_clip; /* Optional output-coordinate [x0,y0,x1,y1]. */
} exr_pdf_raster_config;
/* Output is owned and empty on failure. Initial maps PDF user space to pixels.
   Unsupported image filters and non-device/transparency features fail. */
exr_status exr_pdf_raster_content(exr_pdf_file *file,uint32_t resources,const void *content,size_t size,
                                   const double initial[6],const exr_pdf_raster_config *config,
                                   const exr_control *control,exr_bitmap *out,exr_error *error);
exr_status exr_pdf_image_decode(exr_pdf_file *file,uint32_t image,uint32_t resources,uint32_t stencil_color,
                                 exr_bitmap *out,int *interpolate,size_t *work,
                                 const exr_control *control,exr_error *error);
exr_status exr_pdf_image_load(exr_pdf_file *file,uint32_t image,uint32_t resources,uint32_t stencil_color,
                               exr_vector_texture **out,size_t *work,const exr_control *control,exr_error *error);
exr_status exr_pdf_image_load_from(exr_pdf_file *file,uint32_t image,exr_pdf_file *resource_file,uint32_t resources,uint32_t stencil_color,unsigned intent,
                               exr_vector_texture **out,size_t *work,const exr_control *control,exr_error *error);
void exr_pdf_image_release(exr_vector_texture *texture);
exr_status exr_pdf_page_viewport(const exr_pdf_page_info *page,double scale,exr_viewport *out,exr_error *error);
/* Width/height derive from the intersected crop/media box, UserUnit, rotation
   and scale. NULL config defaults to white RGBA; other config fields apply. */
exr_status exr_pdf_raster_page(exr_pdf_file *file,const exr_pdf_page_info *page,double scale,
                                const exr_pdf_raster_config *config,const exr_control *control,
                                exr_bitmap *out,exr_error *error);
#endif
