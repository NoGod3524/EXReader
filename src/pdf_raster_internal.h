/* SPDX-License-Identifier: GPL-3.0-only */
#ifndef EXR_PDF_RASTER_INTERNAL_H
#define EXR_PDF_RASTER_INTERNAL_H
#include "pdf_internal.h"
/* A host program is borrowed through the whole render; embedded fonts win. */
typedef exr_status (*exr_pdf_program_fn)(void *context,const exr_pdf_font_info *font,
                                         const void **bytes,size_t *size,exr_error *error);
typedef struct {
  uint32_t width,height,channels,background;
  size_t mask_budget; /* zero -> 64 MiB, shared immutable clips and text union */
  exr_pdf_program_fn program; void *context;
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
void exr_pdf_image_release(exr_vector_texture *texture);
#endif
