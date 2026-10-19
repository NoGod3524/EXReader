/* SPDX-License-Identifier: MIT */
#ifndef EXR_PIXELS_INTERNAL_H
#define EXR_PIXELS_INTERNAL_H
#include "internal.h"
/* Straight RGBA source-over; callers validate bounds and bitmap storage. */
static inline void exr_pixel(exr_bitmap *bitmap,int x,int y,uint32_t color,unsigned coverage) {
  unsigned alpha=(color&255)*coverage/255,r=color>>24,g=(color>>16)&255,b=(color>>8)&255;
  unsigned char *p=bitmap->pixels+(size_t)y*bitmap->stride+(size_t)x*bitmap->channels;
  if(!alpha) return;
  if(bitmap->channels==1) {
    unsigned gray=(r*77+g*150+b*29+128)>>8;
    *p=(unsigned char)((*p*(255-alpha)+gray*alpha+127)/255);
  } else if(p[3]==255) {
    p[0]=(unsigned char)((p[0]*(255-alpha)+r*alpha+127)/255);
    p[1]=(unsigned char)((p[1]*(255-alpha)+g*alpha+127)/255);
    p[2]=(unsigned char)((p[2]*(255-alpha)+b*alpha+127)/255);
  } else {
    unsigned source[3]={r,g,b},denominator=alpha*255+p[3]*(255-alpha),k;
    for(k=0;k<3;k++) p[k]=(unsigned char)((source[k]*alpha*255+p[k]*p[3]*(255-alpha)+denominator/2)/denominator);
    p[3]=(unsigned char)((denominator+127)/255);
  }
}
void exr_pixel_blend(exr_bitmap *bitmap,int x,int y,uint32_t color,unsigned coverage,exr_blend_mode mode);
void exr_pixel_composite(exr_bitmap *bitmap,int x,int y,uint32_t color,unsigned coverage,exr_blend_mode mode,exr_composite_state *state);
/* DeviceCMYK source into a CMYK group buffer; converts to RGBA when the active
   state is not CMYK. alpha is the source paint alpha (0..1). */
void exr_pixel_composite_cmyk(exr_bitmap *bitmap,int x,int y,const double cmyk[4],double alpha,unsigned coverage,
                              exr_blend_mode mode,exr_composite_state *state);
#endif
