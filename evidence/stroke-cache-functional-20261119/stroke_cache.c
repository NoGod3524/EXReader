/* SPDX-License-Identifier: MIT */
/* Standalone functional regression for WIP 1beab649c; no timing. */
#include "exreader.h"
#include "canvas_internal.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

enum { W=112, H=88, BYTES=W*H*4, N=8 };
static exr_error err;
#define CHECK(p) do { if (!(p)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#p,err.code,err.message); exit(1); } } while (0)
#define OK(p) CHECK((p)==EXR_OK)
static const double matrix[6]={1,.125,.25,1,5.25,7.5};
static const exr_path_segment shape[]={
  {EXR_PATH_MOVE,{{12,23}}}, {EXR_PATH_CUBIC,{{33,2},{44,63},{62,23}}},
  {EXR_PATH_LINE,{{66,46}}}, {EXR_PATH_LINE,{{22,49}}}, {EXR_PATH_CLOSE,{{0}}}
};
static const exr_path_segment clip_a[]={
  {EXR_PATH_MOVE,{{24,5}}}, {EXR_PATH_LINE,{{97,11}}}, {EXR_PATH_LINE,{{96,73}}},
  {EXR_PATH_LINE,{{21,70}}}, {EXR_PATH_CLOSE,{{0}}}
};
static const exr_path_segment clip_b[]={
  {EXR_PATH_MOVE,{{40,13}}}, {EXR_PATH_LINE,{{94,8}}}, {EXR_PATH_LINE,{{86,68}}},
  {EXR_PATH_LINE,{{38,61}}}, {EXR_PATH_CLOSE,{{0}}}
};
static unsigned callback_calls;
static int never_cancel(void *ctx) { (void)ctx; ++callback_calls; return 0; }
static exr_canvas *make_canvas(int disable) {
  exr_canvas *c=NULL;
  exr_canvas_config cfg={0}; cfg.width=W; cfg.height=H; cfg.background=0xb88e6affu;
  if (disable) cfg.control.cancelled=never_cancel;
  OK(exr_canvas_create(&cfg,&c,&err));
  CHECK(c && c->bitmap.width==W && c->bitmap.height==H && c->bitmap.channels==4);
  return c;
}
static void reset(exr_canvas *c) {
  for (unsigned y=0;y<H;++y) for(unsigned x=0;x<W;++x) {
    unsigned char *p=c->bitmap.pixels+(size_t)y*c->bitmap.stride+4*x;
    p[0]=(unsigned char)(145+x%57); p[1]=(unsigned char)(118+y%53);
    p[2]=(unsigned char)(85+(x+y)%43); p[3]=255;
  }
}
static void capture(exr_canvas *c,unsigned char out[BYTES]) {
  for(unsigned y=0;y<H;++y)
    memcpy(out+(size_t)y*W*4,c->bitmap.pixels+(size_t)y*c->bitmap.stride,W*4);
}
static exr_status draw(exr_canvas *c,const double m[6],const exr_draw_style *s,exr_error *e) {
  return exr_canvas_path(c,shape,sizeof(shape)/sizeof(shape[0]),m,s,e);
}
typedef enum { ADMIT, INSERT, HIT, BYPASS } event;
/* live tick increments only on insert or accepted hit; slots and byte count distinguish them. */
static void paired(exr_canvas *fast,exr_canvas *ref,const exr_draw_style *s,
                   exr_blend_mode blend,int narrow,event expected,unsigned char out[BYTES]) {
  unsigned char uncached[BYTES],before[BYTES];
  exr_canvas *arms[]={fast,ref};
  unsigned tick=fast->path_cache_tick, seen=fast->path_seen_pos;
  size_t bytes=fast->path_cache_bytes;
  exr_path_cache_entry *slots[EXR_PATH_CACHE_SLOTS];
  memcpy(slots,fast->path_cache,sizeof slots);
  for(size_t i=0;i<2;++i) {
    exr_canvas *c=arms[i]; exr_clip_mask *original=c->clip;
    CHECK(original);
    OK(exr_canvas_save(c,&err));
    if(narrow) {
      OK(exr_canvas_clip(c,clip_b,sizeof(clip_b)/sizeof(clip_b[0]),NULL,EXR_FILL_NONZERO,&err));
      CHECK(c->clip && c->clip!=original);
    }
    OK(exr_canvas_blend(c,blend,&err));
    reset(c);
    if(!i) capture(c,before);
    OK(draw(c,matrix,s,&err));
    capture(c,i?uncached:out);
    OK(exr_canvas_restore(c,&err));
    CHECK(c->clip==original);
  }
  CHECK(!memcmp(out,uncached,BYTES));
  CHECK(memcmp(out,before,BYTES));
  CHECK(ref->path_cache_tick==0 && ref->path_seen_pos==0 && ref->path_cache_bytes==0);
  if(expected==INSERT) {
    CHECK(fast->path_cache_tick==tick+1 && fast->path_cache_bytes>bytes);
    CHECK(memcmp(slots,fast->path_cache,sizeof slots));
    CHECK(fast->path_seen_pos==seen);
  } else {
    CHECK(fast->path_cache_tick==tick+(expected==HIT));
    CHECK(fast->path_cache_bytes==bytes && !memcmp(slots,fast->path_cache,sizeof slots));
    CHECK(fast->path_seen_pos==seen+(expected==ADMIT));
  }
}
static void cases(unsigned flags) {
  exr_canvas *fast=make_canvas(0),*ref=make_canvas(1);
  exr_draw_style s=exr_draw_style_defaults();
  unsigned char pixels[BYTES],baseline[BYTES],narrow[BYTES],translucent[BYTES],
                wider[BYTES],multiply[BYTES],combined[BYTES];
  unsigned counts[4]={0};
  s.flags=flags; s.stroke=0x2847abffu; s.fill=0xc049747fu; s.line.width=2.25;
  OK(exr_canvas_clip(fast,clip_a,sizeof(clip_a)/sizeof(clip_a[0]),NULL,EXR_FILL_NONZERO,&err));
  OK(exr_canvas_clip(ref,clip_a,sizeof(clip_a)/sizeof(clip_a[0]),NULL,EXR_FILL_NONZERO,&err));
#define PAIR(mode,clip,ev,out) do { paired(fast,ref,&s,mode,clip,ev,out); ++counts[ev]; } while(0)
  for(int i=0;i<N;++i) PAIR(EXR_BLEND_NORMAL,0,i==0?ADMIT:i==1?INSERT:HIT,baseline);
  PAIR(EXR_BLEND_NORMAL,1,HIT,narrow); CHECK(memcmp(baseline,narrow,BYTES));
  s.stroke=0x2847ab55u;
  PAIR(EXR_BLEND_NORMAL,0,HIT,translucent); CHECK(memcmp(baseline,translucent,BYTES));
  PAIR(EXR_BLEND_NORMAL,1,HIT,combined);
  CHECK(memcmp(narrow,combined,BYTES) && memcmp(translucent,combined,BYTES));
  s.stroke=0x2847abffu;
  s.line.width=4.75;
  PAIR(EXR_BLEND_NORMAL,0,ADMIT,wider); CHECK(memcmp(baseline,wider,BYTES));
  PAIR(EXR_BLEND_NORMAL,0,INSERT,pixels); CHECK(!memcmp(wider,pixels,BYTES));
  PAIR(EXR_BLEND_NORMAL,0,HIT,pixels); CHECK(!memcmp(wider,pixels,BYTES));
  s.line.width=2.25;
  PAIR(EXR_BLEND_NORMAL,0,HIT,pixels); CHECK(!memcmp(baseline,pixels,BYTES));
  PAIR(EXR_BLEND_MULTIPLY,0,flags==EXR_DRAW_STROKE?BYPASS:HIT,multiply);
  CHECK(memcmp(baseline,multiply,BYTES));
  PAIR(EXR_BLEND_MULTIPLY,1,flags==EXR_DRAW_STROKE?BYPASS:HIT,pixels);
  CHECK(memcmp(multiply,pixels,BYTES));
  printf("flags=%u repeat=%u admitted=%u inserted=%u hits=%u bypasses=%u exact_RGBA=PASS\n",
         flags,N,counts[ADMIT],counts[INSERT],counts[HIT],counts[BYPASS]);
#undef PAIR
  exr_canvas_free(fast); exr_canvas_free(ref);
}
static void invalid_matrix(void) {
  exr_draw_style s=exr_draw_style_defaults();
  s.flags=EXR_DRAW_STROKE; s.line.width=2.25;
  for(unsigned k=0;k<6;++k) for(unsigned v=0;v<4;++v) {
    exr_canvas *cold=make_canvas(0),*warm=make_canvas(0),*disabled=make_canvas(1);
    exr_canvas *arms[]={cold,warm,disabled};
    exr_status codes[3]; exr_error errors[3]={{0}};
    double m[6]; memcpy(m,matrix,sizeof m);
    m[k]=v==0?NAN:v==1?INFINITY:v==2?-INFINITY:10000001.0;
    OK(draw(warm,matrix,&s,&err)); OK(draw(warm,matrix,&s,&err));
    CHECK(warm->path_cache_bytes>0 && warm->path_cache_tick==1);
    OK(draw(warm,matrix,&s,&err)); CHECK(warm->path_cache_tick==2);
    for(unsigned i=0;i<3;++i) {
      unsigned tick=arms[i]->path_cache_tick, seen=arms[i]->path_seen_pos;
      size_t bytes=arms[i]->path_cache_bytes;
      unsigned char before[BYTES],after[BYTES];
      reset(arms[i]); capture(arms[i],before);
      codes[i]=draw(arms[i],m,&s,&errors[i]);
      capture(arms[i],after);
      CHECK(!memcmp(before,after,BYTES));
      CHECK(arms[i]->path_cache_tick==tick && arms[i]->path_seen_pos==seen && arms[i]->path_cache_bytes==bytes);
    }
    CHECK(codes[0]!=EXR_OK && codes[0]==codes[1] && codes[1]==codes[2]);
    CHECK(errors[0].code==errors[1].code && errors[1].code==errors[2].code);
    CHECK(!strcmp(errors[0].message,errors[1].message) && !strcmp(errors[1].message,errors[2].message));
    printf("invalid_matrix term=%u case=%u status=%d cold_warm_disabled=PASS\n",k,v,codes[0]);
    for(unsigned i=0;i<3;++i) exr_canvas_free(arms[i]);
  }
}
int main(void) {
  cases(EXR_DRAW_STROKE);
  cases(EXR_DRAW_FILL|EXR_DRAW_STROKE);
  invalid_matrix();
  CHECK(callback_calls>0);
  puts("stroke-cache-functional PASS");
  return 0;
}
