/* SPDX-License-Identifier: MIT */
/* Diagnostic knock-outs for the generated replica. Each replica object is
   compiled with one REPLICA_ID, so its mask is a compile-time constant; with
   mask 0 every macro below folds to the production expression it replaced. */
#ifndef REPLICA_KNOBS_H
#define REPLICA_KNOBS_H
#include <stdint.h>
#include <string.h>
#define K_DW 1u     /* destination stores go to a cache-resident scratch row */
#define K_DR 2u     /* destination loads come from a cache-resident snapshot row */
#define K_SRC 4u    /* source/mask texel rows are all row 0 of the same bitmap */
#define K_BLEND 8u  /* source-over arithmetic off: destination byte still loaded, color stored */
#define K_PACK 16u  /* un-premultiply divisions and byte quantization off */
#define K_INTERP 32u/* one bilinear tap instead of four, first tap's weight */
#define K_SS 64u    /* one of the 2x2 subsamples per destination pixel */
#define K_CONV 128u /* converted-row byte->double conversion off, source bytes still loaded */
#define K_ALL 255u
/* Arm 0 is the unmodified replica. 1-7 then 8 remove traffic first, then
   arithmetic (order A); 9-15 then 8 remove arithmetic first (order B); 16 and
   17 restore one destination stream to the otherwise minimal kernel. */
#define REPLICA_COUNT 18
#define REPLICA_MASK_0 0u
#define REPLICA_MASK_1 (K_DW)
#define REPLICA_MASK_2 (K_DW|K_DR)
#define REPLICA_MASK_3 (K_DW|K_DR|K_SRC)
#define REPLICA_MASK_4 (K_DW|K_DR|K_SRC|K_BLEND)
#define REPLICA_MASK_5 (K_DW|K_DR|K_SRC|K_BLEND|K_PACK)
#define REPLICA_MASK_6 (K_DW|K_DR|K_SRC|K_BLEND|K_PACK|K_INTERP)
#define REPLICA_MASK_7 (K_DW|K_DR|K_SRC|K_BLEND|K_PACK|K_INTERP|K_SS)
#define REPLICA_MASK_8 (K_ALL)
#define REPLICA_MASK_9 (K_BLEND)
#define REPLICA_MASK_10 (K_BLEND|K_PACK)
#define REPLICA_MASK_11 (K_BLEND|K_PACK|K_INTERP)
#define REPLICA_MASK_12 (K_BLEND|K_PACK|K_INTERP|K_SS)
#define REPLICA_MASK_13 (K_BLEND|K_PACK|K_INTERP|K_SS|K_CONV)
#define REPLICA_MASK_14 (K_BLEND|K_PACK|K_INTERP|K_SS|K_CONV|K_DW)
#define REPLICA_MASK_15 (K_BLEND|K_PACK|K_INTERP|K_SS|K_CONV|K_DW|K_DR)
#define REPLICA_MASK_16 (K_ALL&~K_DW)
#define REPLICA_MASK_17 (K_ALL&~K_DR)
#define REPLICA_CAT2(a,b) a##b
#define REPLICA_CAT(a,b) REPLICA_CAT2(a,b)
extern unsigned replica_sink;
extern int replica_path;
extern unsigned char *replica_hot_read,*replica_hot_write;
#endif
/* Replica body: only after pixels_internal.h, once per translation unit. */
#if defined(REPLICA_ID) && defined(EXR_PIXELS_INTERNAL_H) && !defined(REPLICA_BODY_H)
#define REPLICA_BODY_H
#define REPLICA_MASK REPLICA_CAT(REPLICA_MASK_,REPLICA_ID)
#define REPLICA_KNOB(k) (REPLICA_MASK&(k))
#define REPLICA_ROW(y) (REPLICA_KNOB(K_SRC) ? 0 : (y))
#define REPLICA_TAPS (REPLICA_KNOB(K_INTERP) ? 1u : 4u)
#define REPLICA_SUBSAMPLES (REPLICA_KNOB(K_SS) ? 1u : 2u)
#define REPLICA_UNPREMULTIPLY(color,sums) do { \
    if(REPLICA_KNOB(K_PACK)) (color)|=0x80808000u; \
    else for(unsigned k_=0;k_<3;k_++) (color)|=image_byte((sums)[k_]/(sums)[3])<<(24-8*k_); \
  } while(0)
static inline void replica_prefill(double *storage,size_t span) {
  for(unsigned s=0;s<4;s++) {
    double *rgb1=storage+s*5*span,*alpha=rgb1+4*span;
    for(size_t i=0;i<span;i++) { rgb1[4*i]=rgb1[4*i+1]=rgb1[4*i+2]=128;rgb1[4*i+3]=1;alpha[i]=255; }
  }
}
/* exr_pixel with separate load and store addresses. */
static inline void replica_pixel(exr_bitmap *bitmap,int x,int y,uint32_t color,unsigned coverage) {
  if(!REPLICA_MASK || bitmap->channels!=4) { exr_pixel(bitmap,x,y,color,coverage); return; }
  unsigned alpha=(color&255)*coverage/255,r=color>>24,g=(color>>16)&255,b=(color>>8)&255;
  unsigned char *real=bitmap->pixels+(size_t)y*bitmap->stride+(size_t)x*4;
  const unsigned char *p=REPLICA_KNOB(K_DR) ? replica_hot_read+(size_t)x*4 : real;
  unsigned char *q=REPLICA_KNOB(K_DW) ? replica_hot_write+(size_t)x*4 : real;
  if(!alpha) return;
  if(REPLICA_KNOB(K_BLEND)) {
    replica_sink+=p[3];
    q[0]=(unsigned char)r;q[1]=(unsigned char)g;q[2]=(unsigned char)b;q[3]=(unsigned char)alpha;return;
  }
  if(p[3]==255) {
    unsigned d0=p[0],d1=p[1],d2=p[2];
    q[0]=(unsigned char)((d0*(255-alpha)+r*alpha+127)/255);
    q[1]=(unsigned char)((d1*(255-alpha)+g*alpha+127)/255);
    q[2]=(unsigned char)((d2*(255-alpha)+b*alpha+127)/255);
    if(q!=p) q[3]=255;
  } else if(!p[3]) {
    q[0]=(unsigned char)r; q[1]=(unsigned char)g; q[2]=(unsigned char)b; q[3]=(unsigned char)alpha;
  } else {
    unsigned source[3]={r,g,b},denominator=alpha*255+p[3]*(255-alpha),k,d[4]={p[0],p[1],p[2],p[3]};
    for(k=0;k<3;k++) q[k]=(unsigned char)((source[k]*alpha*255+d[k]*d[3]*(255-alpha)+denominator/2)/denominator);
    q[3]=(unsigned char)((denominator+127)/255);
  }
}
#endif
