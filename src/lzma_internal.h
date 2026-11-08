/* SPDX-License-Identifier: MIT */
#ifndef EXR_LZMA_INTERNAL_H
#define EXR_LZMA_INTERNAL_H
#include "base_internal.h"
/* Raw 7Z codec streams, with an already bounded, caller-owned output. */
exr_status exr_lzma_decode(int lzma2,const unsigned char *properties,size_t property_size,
  const unsigned char *input,size_t input_size,unsigned char *output,size_t output_size,
  const exr_control *control,exr_error *error);
#endif
