/* SPDX-License-Identifier: MIT */
#ifndef MULTIIMAGE_PROBE_H
#define MULTIIMAGE_PROBE_H
#include "canvas_internal.h"
#include <windows.h>

extern int probe_detailed;
static inline long long tick(void) {
  LARGE_INTEGER counter;
  QueryPerformanceCounter(&counter);
  return counter.QuadPart;
}
void probe_add(unsigned slot,long long start);
void probe_add_sample(unsigned slot,long long start,double v0,double v1);
void probe_count(unsigned slot);
void probe_image(const exr_image_layer *image,const double matrix[6],const exr_clip_mask *clip,int state);
void probe_end_image(void);
#endif
