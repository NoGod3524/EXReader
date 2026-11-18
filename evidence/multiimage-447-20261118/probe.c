/* SPDX-License-Identifier: MIT */
#include "probe.h"

/* The harness serializes all renders. No hooks ship in the renderer. */
enum { SLOTS=9, MAX_IMAGES=96, COLUMNS=33 };
static double rows[MAX_IMAGES+1][COLUMNS];
static unsigned calls, current;
static double ns_per_tick;
static volatile double consumed;
int probe_detailed;

__declspec(dllexport) void probe_start(int detailed) {
  LARGE_INTEGER frequency;
  QueryPerformanceFrequency(&frequency);
  ns_per_tick=1e9/(double)frequency.QuadPart;
  probe_detailed=detailed;
  calls=current=0;
  memset(rows,0,sizeof(rows));
}
__declspec(dllexport) unsigned probe_read(double *out) {
  memcpy(out,rows,(calls+1)*sizeof(rows[0]));
  return calls+1;
}
void probe_add(unsigned slot,long long start) {
  long long elapsed=tick()-start;
  rows[current][slot]+=elapsed*ns_per_tick;
  rows[current][SLOTS+slot]++;
}
void probe_add_sample(unsigned slot,long long start,double v0,double v1) {
  long long elapsed=tick()-start;
  rows[current][slot]+=elapsed*ns_per_tick;
  rows[current][SLOTS+slot]++;
  consumed=v0+v1;
}
void probe_count(unsigned slot) { rows[current][SLOTS+slot]++; }
void probe_image(const exr_image_layer *image,const double m[6],const exr_clip_mask *clip,int state) {
  if(calls==MAX_IMAGES) return;
  current=++calls;
  double *r=rows[current];
  r[18]=image->bitmap.width;
  r[19]=image->bitmap.height;
  r[20]=image->interpolate;
  r[21]=image->mask ? (int)image->mask->interpolate : -1;
  r[22]=image->mask_mode;
  r[23]=state;
  r[24]=image->has_matte;
  for(unsigned i=0;i<6;i++) r[25+i]=m[i];
  r[31]=clip!=NULL;
  r[32]=image->mask!=NULL;
}
void probe_end_image(void) { current=0; }
