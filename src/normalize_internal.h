/* SPDX-License-Identifier: MIT */
#ifndef EXR_NORMALIZE_INTERNAL_H
#define EXR_NORMALIZE_INTERNAL_H
#include "internal.h"
/* Scalar with its contributing original scalar interval. Canonical reordering
   may make these intervals nonmonotonic; composition unions the intervals. */
typedef struct { uint32_t cp; unsigned first,last; } exr_normal_scalar;
/* Distinct input/output buffers; <=4096 input / <=16384 output slots.
   Canonical NFC only (not NFKC). No locale, allocation or source text mutation. */
exr_status exr_normalize_nfc(const exr_normal_scalar *input,size_t count,
  exr_normal_scalar *output,size_t capacity,size_t *written,const exr_control *control,size_t *operations,exr_error *error);
#endif
