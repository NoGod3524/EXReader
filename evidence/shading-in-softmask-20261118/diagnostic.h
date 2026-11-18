/* SPDX-License-Identifier: MIT */
/* TEMPORARY diagnostic scoped timers and ablation switches (perf/shading-in-softmask). Remove before PR. */
#ifndef EXR_DIAG_H
#define EXR_DIAG_H
#include <stdint.h>
enum {
  D_MASK_BUILD, D_MASK_RASTER, D_MASK_LUM, D_PAINT_MASK, D_PAINT_PAGE, D_IMG_LOAD, D_IMG_DRAW,
  D_GROUP_BEGIN_MASK, D_GROUP_END_MASK, D_GROUP_BEGIN_PAGE, D_GROUP_END_PAGE, D_SH_TABLE,
  D_CANVAS_CREATE_MASK, D_CANVAS_TAKE_MASK, D_RASTER_PAGE, D_PATH, D_GLYPH, D_CLIP, D_CANVAS_FREE_MASK,
  D_SAMPLE_MASK, D_SAMPLE_PAGE, D_SCALE_MASK, D_SCALE_PAGE, D_LOOKUP_MASK, D_LOOKUP_PAGE, D_SLOTS=32
};
enum { DIAG_SKIP_SH=1, DIAG_SKIP_SMASK=2, DIAG_SKIP_IMAGE=4 };
extern unsigned exr_diag_flags;
extern unsigned exr_diag_mask_depth;
int exr_diag_sample(unsigned slot);
uint64_t exr_diag_now(void);
void exr_diag_add(unsigned slot,uint64_t start);
#define DIAG_T0(name) uint64_t name=exr_diag_now()
#define DIAG_ADD(slot,name) exr_diag_add((slot),(name))
#endif
