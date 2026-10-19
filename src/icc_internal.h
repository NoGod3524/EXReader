/* SPDX-License-Identifier: GPL-3.0-only */
#ifndef EXR_ICC_INTERNAL_H
#define EXR_ICC_INTERNAL_H
#include "internal.h"
typedef struct exr_icc exr_icc;
/* An unusable profile returns OK/NULL for PDF Alternate fallback. */
exr_status exr_icc_open(const void *data,size_t size,unsigned channels,const exr_control *control,exr_icc **out,exr_error *error);
void exr_icc_free(exr_icc *profile);
exr_status exr_icc_rgb(exr_icc *profile,const double *values,double rgb[3],exr_error *error);
exr_status exr_icc_rgb_intent(exr_icc *profile,const double *values,double rgb[3],unsigned intent,exr_error *error);
size_t exr_icc_memory(const exr_icc *profile);
size_t exr_icc_cost(const exr_icc *profile);
#endif
