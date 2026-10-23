/* SPDX-License-Identifier: MIT */
#ifndef EXR_PDF_JPX_INTERNAL_H
#define EXR_PDF_JPX_INTERNAL_H
#include "exr/base.h"
/* Owned row-padded MSB-first samples; PDF applies its explicit colour space.
   Failure always leaves samples NULL and sample_size zero. */
exr_status exr_pdf_jpx_decode(const void *data,size_t size,unsigned width,
  unsigned height,unsigned components,unsigned bits,int indexed,
  const exr_control *control,unsigned char **samples,size_t *sample_size,exr_error *e);
#endif
