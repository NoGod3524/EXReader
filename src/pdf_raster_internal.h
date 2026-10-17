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
   Images and non-device/transparency features are not implemented here yet. */
exr_status exr_pdf_raster_content(exr_pdf_file *file,uint32_t resources,const void *content,size_t size,
                                   const double initial[6],const exr_pdf_raster_config *config,
                                   const exr_control *control,exr_bitmap *out,exr_error *error);
#endif
