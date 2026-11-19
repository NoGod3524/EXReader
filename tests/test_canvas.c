/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include "../src/canvas_internal.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error; static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static void rectangle(exr_path_segment p[5],double x,double y,double w,double h) {
  memset(p,0,5*sizeof(*p)); p[0].verb=EXR_PATH_MOVE; p[0].points[0]=(exr_path_point){x,y};
  p[1].verb=EXR_PATH_LINE; p[1].points[0]=(exr_path_point){x+w,y}; p[2].verb=EXR_PATH_LINE; p[2].points[0]=(exr_path_point){x+w,y+h};
  p[3].verb=EXR_PATH_LINE; p[3].points[0]=(exr_path_point){x,y+h}; p[4].verb=EXR_PATH_CLOSE;
}
static void pixel(const exr_bitmap *b,unsigned x,unsigned y,unsigned r,unsigned g,unsigned blue) {
  const unsigned char *p=b->pixels+(size_t)y*b->stride+x*b->channels;
  CHECK(b->channels==4 && p[0]==r && p[1]==g && p[2]==blue && p[3]==255);
}
static exr_canvas *create(size_t budget) {
  exr_canvas_config config={0}; exr_canvas *c=NULL; config.width=config.height=8; config.background=0xffffffff; config.mask_budget=budget;
  OK(exr_canvas_create(&config,&c,&error)); CHECK(c && exr_canvas_bitmap(c)->channels==4); return c;
}
static void backgrounds(void) {
  const uint32_t colors[]={0xffffffff,0,0x7f7f7f7f,0x12345678},channels[]={0,1,4};
  size_t color,channel,i;
  for(color=0;color<sizeof(colors)/sizeof(*colors);color++) for(channel=0;channel<sizeof(channels)/sizeof(*channels);channel++) {
    exr_canvas_config config={0}; exr_canvas *c=NULL; const exr_bitmap *b; unsigned char rgba[4]; unsigned k;
    config.width=3; config.height=2; config.background=colors[color]; config.channels=channels[channel];
    for(k=0;k<4;k++) rgba[k]=(unsigned char)(config.background>>(24-8*k));
    OK(exr_canvas_create(&config,&c,&error)); b=exr_canvas_bitmap(c);
    CHECK(b && b->width==3 && b->height==2 && b->channels==(config.channels ? config.channels : 4));
    CHECK(b->stride==b->width*b->channels);
    for(i=0;i<(size_t)b->stride*b->height;i++)
      CHECK(b->pixels[i]==(b->channels==1 ? (rgba[0]*77+rgba[1]*150+rgba[2]*29+128)>>8 : rgba[i%4]));
    exr_canvas_free(c);
  }
}
static void clip_and_ownership(void) {
  exr_canvas *c=create(64); exr_path_segment rect[5]; exr_draw_style style=exr_draw_style_defaults(); exr_bitmap image; size_t before,clipped,i;
  before=exr_canvas_memory_size(c); OK(exr_canvas_save(c,&error)); rectangle(rect,1,1,3,3); OK(exr_canvas_clip(c,rect,5,NULL,EXR_FILL_NONZERO,&error));
  clipped=exr_canvas_memory_size(c); CHECK(clipped>before && clipped-before>=64);
  for(i=0;i<120;i++) OK(exr_canvas_save(c,&error)); CHECK(exr_canvas_memory_size(c)==clipped);
  rectangle(rect,0,0,8,8); style.fill=0xff0000ff; OK(exr_canvas_path(c,rect,5,NULL,&style,&error));
  /* A released mask is retained (and counted) for reuse until the canvas is freed. */
  for(i=0;i<121;i++) OK(exr_canvas_restore(c,&error)); CHECK(exr_canvas_memory_size(c)==clipped);
  OK(exr_canvas_save(c,&error)); rectangle(rect,1,1,3,3); OK(exr_canvas_clip(c,rect,5,NULL,EXR_FILL_NONZERO,&error));
  CHECK(exr_canvas_memory_size(c)==clipped); OK(exr_canvas_restore(c,&error)); CHECK(exr_canvas_memory_size(c)==clipped);
  rectangle(rect,6,6,1,1); style.fill=0x0000ffff; OK(exr_canvas_path(c,rect,5,NULL,&style,&error));
  pixel(exr_canvas_bitmap(c),2,2,255,0,0); pixel(exr_canvas_bitmap(c),0,0,255,255,255); pixel(exr_canvas_bitmap(c),6,6,0,0,255);
  OK(exr_canvas_take(c,&image,&error)); CHECK(!exr_canvas_bitmap(c)); exr_canvas_free(c); pixel(&image,2,2,255,0,0); exr_bitmap_free(&image); CHECK(!image.pixels);
}
static void stroke_and_images(void) {
  exr_canvas *c=create(0); exr_path_segment line[2]={0}; exr_draw_style style=exr_draw_style_defaults();
  const double transform[6]={2,0,0,2,0,0},identity[6]={1,0,0,1,0,0},dashes[2]={1,1};
  line[0].verb=EXR_PATH_MOVE; line[0].points[0]=(exr_path_point){1,2}; line[1].verb=EXR_PATH_LINE; line[1].points[0]=(exr_path_point){3,2};
  style.flags=EXR_DRAW_STROKE; style.dashes=dashes; style.dash_count=2;
  OK(exr_canvas_path(c,line,2,transform,&style,&error)); pixel(exr_canvas_bitmap(c),2,3,0,0,0); pixel(exr_canvas_bitmap(c),5,3,255,255,255); exr_canvas_free(c);
  c=create(0); style.dash_count=0; style.stroke_matrix=identity;
  OK(exr_canvas_path(c,line,2,transform,&style,&error)); CHECK(exr_canvas_bitmap(c)->pixels[3*32+3*4]>100 && exr_canvas_bitmap(c)->pixels[3*32+3*4]<150); exr_canvas_free(c);
  { unsigned char red[4]={255,0,0,255},mask_pixels[16]={0,0,0,255,85,85,85,255,170,170,170,255,255,255,255,255};
    exr_image_layer image={0},mask={0}; const double matrix[6]={8,0,0,2,0,0};
    image.bitmap.width=image.bitmap.height=1; image.bitmap.channels=image.bitmap.stride=4; image.bitmap.pixels=red;
    mask.bitmap.width=4; mask.bitmap.height=1; mask.bitmap.channels=4; mask.bitmap.stride=16; mask.bitmap.pixels=mask_pixels;
    image.mask=&mask; image.mask_mode=EXR_MASK_GRAY; c=create(0); OK(exr_canvas_image(c,&image,matrix,1,&error));
    memset(red,0,sizeof(red)); memset(mask_pixels,0,sizeof(mask_pixels)); /* Inputs are no longer borrowed. */
    pixel(exr_canvas_bitmap(c),2,0,255,170,170); pixel(exr_canvas_bitmap(c),6,0,255,0,0); exr_canvas_free(c);
  }
}
static int cancel(void *ctx) { return *(int *)ctx; }
static void drawing_sink(void) {
  exr_canvas *c=create(0); exr_draw_sink sink={0}; exr_path_segment p[5]; exr_draw_style style=exr_draw_style_defaults(); exr_bitmap out;
  OK(exr_canvas_get_sink(c,&sink,&error)); CHECK(sink.context==c && sink.path && sink.image && sink.clip && sink.state);
  OK(sink.state(sink.context,EXR_DRAW_BEGIN_CLIP,&error)); rectangle(p,1,1,1,1); OK(sink.clip(sink.context,p,5,NULL,EXR_FILL_NONZERO,1,&error));
  rectangle(p,5,5,1,1); OK(sink.clip(sink.context,p,5,NULL,EXR_FILL_NONZERO,1,&error)); OK(sink.state(sink.context,EXR_DRAW_END_CLIP,&error));
  rectangle(p,0,0,8,8); OK(sink.path(sink.context,p,5,NULL,&style,&error));
  pixel(exr_canvas_bitmap(c),1,1,0,0,0); pixel(exr_canvas_bitmap(c),5,5,0,0,0); pixel(exr_canvas_bitmap(c),3,3,255,255,255);
  OK(sink.state(sink.context,EXR_DRAW_SAVE,&error)); OK(sink.state(sink.context,EXR_DRAW_BEGIN_CLIP,&error)); OK(sink.state(sink.context,EXR_DRAW_END_CLIP,&error)); OK(sink.state(sink.context,EXR_DRAW_RESTORE,&error));
  OK(sink.state(sink.context,EXR_DRAW_BEGIN_CLIP,&error)); OK(sink.clip(sink.context,NULL,0,NULL,EXR_FILL_NONZERO,1,&error)); OK(sink.state(sink.context,EXR_DRAW_END_CLIP,&error));
  style.fill=0xff0000ff; OK(sink.path(sink.context,p,5,NULL,&style,&error)); pixel(exr_canvas_bitmap(c),1,1,0,0,0);
  CHECK(sink.state(sink.context,(exr_draw_state)99,&error)==EXR_ARGUMENT); CHECK(exr_canvas_take(c,&out,&error)==EXR_ARGUMENT && !out.pixels); exr_canvas_free(c);
  c=create(0); OK(exr_canvas_get_sink(c,&sink,&error)); CHECK(sink.clip(sink.context,p,5,NULL,EXR_FILL_NONZERO,2,&error)==EXR_ARGUMENT);
  CHECK(exr_canvas_get_sink(c,&sink,&error)==EXR_ARGUMENT && !sink.path && !sink.context); exr_canvas_free(c);
  CHECK(exr_canvas_get_sink(NULL,&sink,&error)==EXR_ARGUMENT && !sink.path && !sink.context);
}
static void failures(void) {
  exr_canvas *c=create(64); exr_path_segment rect[5]; exr_bitmap out; char message[256]; size_t i;
  /* The first clip has to be a real sub-rectangle: a clip covering the whole canvas
     allocates no mask at all, so it cannot consume the budget the second one exceeds. */
  rectangle(rect,1,1,6,6); OK(exr_canvas_clip(c,rect,5,NULL,EXR_FILL_NONZERO,&error)); OK(exr_canvas_save(c,&error));
  CHECK(exr_canvas_clip(c,rect,5,NULL,EXR_FILL_NONZERO,&error)==EXR_LIMIT); snprintf(message,sizeof(message),"%s",error.message);
  CHECK(!exr_canvas_bitmap(c)); CHECK(exr_canvas_take(c,&out,&error)==EXR_LIMIT && !out.pixels && !strcmp(message,error.message)); exr_canvas_free(c);
  c=create(0); rect[0].points[0].x=NAN; CHECK(exr_canvas_path(c,rect,5,NULL,NULL,&error)==EXR_ARGUMENT); CHECK(exr_canvas_take(c,&out,&error)==EXR_ARGUMENT && !out.width); exr_canvas_free(c);
  c=create(0); CHECK(exr_canvas_restore(c,&error)==EXR_ARGUMENT); exr_canvas_free(c);
  c=create(0); for(i=0;i<160;i++) OK(exr_canvas_save(c,&error)); CHECK(exr_canvas_save(c,&error)==EXR_LIMIT); exr_canvas_free(c);
  { exr_canvas_config config={0}; int stopped=0; config.width=config.height=8; config.control.cancelled=cancel; config.control.context=&stopped;
    OK(exr_canvas_create(&config,&c,&error)); stopped=1; CHECK(exr_canvas_take(c,&out,&error)==EXR_CANCELLED && !out.pixels); exr_canvas_free(c);
    CHECK(exr_canvas_create(&config,&c,&error)==EXR_CANCELLED && !c); stopped=0;
    config.width=config.height=16384; CHECK(exr_canvas_create(&config,&c,&error)==EXR_LIMIT && !c);
  }
  CHECK(!exr_canvas_memory_size(NULL) && !exr_canvas_bitmap(NULL)); exr_canvas_free(NULL);
}
/* Repeated commit/discard reaches a bounded scratch-buffer steady state. */
static void group_churn(void) {
  exr_canvas_config config={0}; exr_canvas *c=NULL; exr_path_segment clip[5],paint[5];
  exr_draw_style style=exr_draw_style_defaults(); size_t baseline=0,allocations=0,i;
  config.width=256; config.height=64; config.background=0xffffffff;
  OK(exr_canvas_create(&config,&c,&error));
  rectangle(clip,32,16,32,32);
  OK(exr_canvas_clip(c,clip,5,NULL,EXR_FILL_NONZERO,&error));
  baseline=exr_canvas_memory_size(c);
  for(i=0;i<1000;i++) {
    rectangle(paint,32,16,32,32);
    OK(exr_canvas_begin_group(c,1,EXR_BLEND_NORMAL,0,&error));
    style.fill=0x3366ccffu; style.flags=EXR_DRAW_FILL;
    OK(exr_canvas_path(c,paint,5,NULL,&style,&error));
    OK(exr_canvas_end_layer(c,i%2,&error));
    if(!i) { baseline=exr_canvas_memory_size(c);allocations=c->pool->allocations; }
    else { CHECK(exr_canvas_memory_size(c)==baseline);CHECK(c->pool->allocations==allocations && c->pool->reuses>0); }
  }
  exr_canvas_free(c);
  /* A discarded painted buffer must be cleared before an empty group reuses it. */
  c=create(0);rectangle(paint,0,0,8,8);style.fill=0xff0000ff;
  OK(exr_canvas_begin_group(c,1,EXR_BLEND_NORMAL,EXR_GROUP_ISOLATED,&error));
  OK(exr_canvas_path(c,paint,5,NULL,&style,&error));OK(exr_canvas_end_layer(c,0,&error));
  OK(exr_canvas_begin_group(c,1,EXR_BLEND_NORMAL,EXR_GROUP_ISOLATED,&error));
  OK(exr_canvas_end_layer(c,1,&error));pixel(exr_canvas_bitmap(c),4,4,255,255,255);
  exr_canvas_free(c);
}
static int never_cancel(void *ctx) { (void)ctx; return 0; }
static void path_cache_and_solid_clip(void) {
  /* Compare cached path reuse + solid-clip elision against an uncached reference canvas
     (control.cancelled != NULL bypasses the within-page path cache). */
  exr_canvas_config cfg={0},ref_cfg={0};
  exr_canvas *fast=NULL,*ref=NULL;
  exr_path_segment clip[5]={{EXR_PATH_MOVE,{{10,12}}},{EXR_PATH_LINE,{{148,8}}},{EXR_PATH_LINE,{{152,110}}},{EXR_PATH_LINE,{{8,112}}},{EXR_PATH_CLOSE,{{0}}}};
  exr_path_segment star[14]={
    {EXR_PATH_MOVE,{{24,12}}},{EXR_PATH_LINE,{{18,15}}},{EXR_PATH_LINE,{{19,21}}},{EXR_PATH_LINE,{{14,17}}},
    {EXR_PATH_LINE,{{9,21}}},{EXR_PATH_LINE,{{10,15}}},{EXR_PATH_LINE,{{4,12}}},{EXR_PATH_LINE,{{10,9}}},
    {EXR_PATH_LINE,{{9,3}}},{EXR_PATH_LINE,{{14,7}}},{EXR_PATH_LINE,{{19,3}}},{EXR_PATH_LINE,{{18,9}}},
    {EXR_PATH_LINE,{{24,12}}},{EXR_PATH_CLOSE,{{0}}}
  };
  exr_path_segment curve[2]={{EXR_PATH_MOVE,{{14,20}}},{EXR_PATH_CUBIC,{{54,32},{96,8},{136,20}}}};
  const double dashes[2]={4,2};
  exr_draw_style style=exr_draw_style_defaults();
  cfg.width=160; cfg.height=120; cfg.background=0xfafaf8ffu;
  ref_cfg=cfg; ref_cfg.control.cancelled=never_cancel;
  OK(exr_canvas_create(&cfg,&fast,&error));
  OK(exr_canvas_create(&ref_cfg,&ref,&error));
  OK(exr_canvas_clip(fast,clip,5,NULL,EXR_FILL_NONZERO,&error));
  OK(exr_canvas_clip(ref,clip,5,NULL,EXR_FILL_NONZERO,&error));
  /* 1. Repeated dashed curves at integer y shifts (strike 1, 2, hits 3..5) and one crossing clip. */
  style.flags=EXR_DRAW_STROKE; style.line.width=1.4; style.dashes=dashes; style.dash_count=2; style.dash_phase=1;
  for(int i=0;i<6;i++) {
    double m[6]={1,0,0,1,0,(double)(i==5 ? -14 : i*13)};
    style.stroke=0x102030ffu+(uint32_t)(i*0x19130d00u);
    OK(exr_canvas_path(fast,curve,2,m,&style,&error));
    OK(exr_canvas_path(ref,curve,2,m,&style,&error));
  }
  /* 2. Repeated compound stars: integer x shifts, subpixel y shift, clip-edge overlap, and border-clip test. */
  style.flags=EXR_DRAW_FILL|EXR_DRAW_STROKE; style.rule=EXR_FILL_EVENODD; style.line.width=0.9; style.dash_count=0; style.dashes=NULL;
  {
    const double shifts[][2]={{12,20},{44,20},{76,20},{108,20},{12,50.333},{44,50.333},{76,50.333},{-6,70},{140,70},{20,70}};
    for(size_t i=0;i<sizeof(shifts)/sizeof(*shifts);i++) {
      double m[6]={1,0,0,1,shifts[i][0],shifts[i][1]};
      style.fill=0x224466ffu+(uint32_t)(i*0x170b1300u); style.stroke=0x333333ffu;
      OK(exr_canvas_path(fast,star,14,m,&style,&error));
      OK(exr_canvas_path(ref,star,14,m,&style,&error));
    }
  }
  CHECK(fast->path_cache_bytes>0 && fast->path_cache_bytes<=512u*1024u);
  CHECK(!memcmp(exr_canvas_bitmap(fast)->pixels,exr_canvas_bitmap(ref)->pixels,(size_t)160*120*4));
  exr_canvas_free(fast); exr_canvas_free(ref);
}
int main(void) { backgrounds(); clip_and_ownership(); stroke_and_images(); drawing_sink(); failures(); group_churn(); path_cache_and_solid_clip(); printf("%u native canvas checks passed\n",checks); return 0; }


