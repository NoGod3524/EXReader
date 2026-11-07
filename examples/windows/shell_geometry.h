/* SPDX-License-Identifier: MIT */
#ifndef EXR_SHELL_GEOMETRY_H
#define EXR_SHELL_GEOMETRY_H
#include "shell_tokens.h"
#include <math.h>
typedef struct {
  int enabled, width, height, vertical;
  unsigned dpi;
  float font;
} shell_geometry;
static inline int shell_px(float dip, unsigned dpi) { return (int)floorf(dip * dpi / 96.0f + 0.5f); }
/* Positions are derived from rounded boundaries, never a sum of rounded gaps. */
static inline shell_geometry shell_geometry_for(int w, int h, unsigned dpi, float font, int vertical) {
  shell_geometry out = {0};
  int top = shell_px(SHELL_TOPBAR_H + SHELL_BODY_TOP, dpi);
  int bottom = h - shell_px(SHELL_PAGE_NUMBER_H + SHELL_BODY_GAP, dpi);
  int available = w - 2 * shell_px(SHELL_SPACE_5, dpi);
  out.enabled = w > 0 && bottom > top && available > 0;
  out.dpi = dpi; out.font = font; out.vertical = vertical;
  out.width = (int)fminf((float)available, (float)shell_px(SHELL_BODY_MAX_EM * font, dpi));
  out.height = bottom - top;
  if (vertical) out.height = (int)fminf((float)out.height, (float)shell_px(SHELL_BODY_MAX_EM * font, dpi));
  if (out.height <= 0) out.enabled = 0;
  return out;
}
/* Origin changes at the 34em cap do not require a new pager. DPI and mode do. */
static inline int shell_geometry_equal(shell_geometry a, shell_geometry b) {
  return a.enabled == b.enabled && (!a.enabled || (a.width == b.width && a.height == b.height &&
    a.font == b.font && a.dpi == b.dpi && a.vertical == b.vertical));
}
/* Page-child coordinates, fitted to today's body rather than the source frame. */
typedef struct { int left,top,width,height; } shell_image_view;
static inline shell_image_view shell_fit_image(int w,int h,unsigned dpi,float font,int iw,int ih) {
  shell_image_view out={0};
  shell_geometry body=shell_geometry_for(w,h+shell_px(SHELL_TOPBAR_H,dpi),dpi,font,0);
  int margin=shell_px(SHELL_SPACE_2,dpi),top=shell_px(SHELL_BODY_TOP,dpi);
  int width=(int)fminf((float)body.width,(float)(w-2*margin));
  int height=(int)fminf((float)body.height,(float)(h-2*margin));
  if(width<=0 || height<=0 || iw<=0 || ih<=0) return out;
  double scale=fmin(1.0,fmin((double)width/iw,(double)height/ih));
  /* Round the shorter side down, then derive the longer side from its ratio. */
  if(iw>=ih) {
    out.height=(int)floor(ih*scale);out.width=(int)floor((double)out.height*iw/ih+.5);
  } else {
    out.width=(int)floor(iw*scale);out.height=(int)floor((double)out.width*ih/iw+.5);
  }
  out.left=(w-out.width)/2;out.top=top+(body.height-out.height)/2;
  return out;
}
#endif
