/* SPDX-License-Identifier: MIT */
/* TEMPORARY diagnostic scoped timers (perf/shading-in-softmask). Remove before PR. */
#include "exr_diag.h"
#include <windows.h>
unsigned exr_diag_flags;
unsigned exr_diag_mask_depth;
static uint64_t diag_ticks[D_SLOTS],diag_count[D_SLOTS],diag_calls[D_SLOTS];
int exr_diag_sample(unsigned slot) { diag_calls[slot]++; return 1; }
uint64_t exr_diag_now(void) { LARGE_INTEGER v;QueryPerformanceCounter(&v);return (uint64_t)v.QuadPart; }
void exr_diag_add(unsigned slot,uint64_t start) { diag_ticks[slot]+=exr_diag_now()-start;diag_count[slot]++; }
__declspec(dllexport) void exr_diag_set_flags(unsigned flags) { exr_diag_flags=flags; }
__declspec(dllexport) void exr_diag_reset(void) { for(unsigned i=0;i<D_SLOTS;i++) diag_ticks[i]=diag_count[i]=diag_calls[i]=0; }
/* Writes D_SLOTS milliseconds then D_SLOTS counts. */
__declspec(dllexport) unsigned exr_diag_read(double *ms,double *count) {
  LARGE_INTEGER f;QueryPerformanceFrequency(&f);
  for(unsigned i=0;i<D_SLOTS;i++) { ms[i]=diag_ticks[i]*1000.0/(double)f.QuadPart;count[i]=(double)diag_count[i]; }
  return D_SLOTS;
}
