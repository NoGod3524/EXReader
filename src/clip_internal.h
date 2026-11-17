/* SPDX-License-Identifier: MIT */
#ifndef EXR_CLIP_INTERNAL_H
#define EXR_CLIP_INTERNAL_H
#include "graphics_internal.h"
#define EXR_CLIP_PROCEDURAL 0xffffffffu
typedef enum { EXR_CLIP_NONE, EXR_CLIP_RECT, EXR_CLIP_MASK } exr_clip_kind;
/* NULL is unrestricted. A rectangle stores the exact quantized coverage of its
   first/interior/last rows and columns, including multiplied clip edges.
   bitmap is first: channels==EXR_CLIP_PROCEDURAL is a private procedural clip view, never pixels. */
typedef struct {
  exr_bitmap bitmap;
  size_t refs;
  exr_clip_kind kind;
  uint32_t left,top,right,bottom;
  unsigned char coverage[9];
} exr_clip_state;
typedef exr_clip_state exr_clip_mask;
static inline const exr_clip_state *exr_clip_rect(const exr_bitmap *clip) {
  return clip && clip->channels==EXR_CLIP_PROCEDURAL ? (const exr_clip_state *)clip : NULL;
}
static inline unsigned exr_clip_coverage(const exr_bitmap *clip,size_t x,size_t y) {
  const exr_clip_state *r=exr_clip_rect(clip);unsigned col,row;
  if(!clip) return 255;
  if(!r) return clip->pixels[y*clip->stride+x];
  if(r->kind==EXR_CLIP_NONE || x<r->left || x>=r->right || y<r->top || y>=r->bottom) return 0;
  col=x==r->left ? 0 : x==r->right-1 ? 2 : 1;
  row=y==r->top ? 0 : y==r->bottom-1 ? 2 : 1;
  return r->coverage[row*3+col];
}
static inline int exr_clip_empty(const exr_clip_state *clip) {
  return clip && clip->kind==EXR_CLIP_NONE;
}
/* Rectangle edge coverage never exceeds interior coverage, including after
   multiplication. Four opaque corners prove this whole draw extent is opaque. */
static inline int exr_clip_opaque(const exr_bitmap *clip,size_t left,size_t top,size_t right,size_t bottom) {
  const exr_clip_state *r=exr_clip_rect(clip);
  return r && r->kind==EXR_CLIP_RECT && left<right && top<bottom &&
    exr_clip_coverage(clip,left,top)==255 && exr_clip_coverage(clip,right-1,top)==255 &&
    exr_clip_coverage(clip,left,bottom-1)==255 && exr_clip_coverage(clip,right-1,bottom-1)==255;
}
#endif
