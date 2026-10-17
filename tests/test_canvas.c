/* SPDX-License-Identifier: GPL-3.0-only */
#include "exreader.h"
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
static void clip_and_ownership(void) {
  exr_canvas *c=create(64); exr_path_segment rect[5]; exr_draw_style style=exr_draw_style_defaults(); exr_bitmap image; size_t before,clipped,i;
  before=exr_canvas_memory_size(c); OK(exr_canvas_save(c,&error)); rectangle(rect,1,1,3,3); OK(exr_canvas_clip(c,rect,5,NULL,EXR_FILL_NONZERO,&error));
  clipped=exr_canvas_memory_size(c); CHECK(clipped>before && clipped-before>=64);
  for(i=0;i<120;i++) OK(exr_canvas_save(c,&error)); CHECK(exr_canvas_memory_size(c)==clipped);
  rectangle(rect,0,0,8,8); style.fill=0xff0000ff; OK(exr_canvas_path(c,rect,5,NULL,&style,&error));
  for(i=0;i<121;i++) OK(exr_canvas_restore(c,&error)); CHECK(exr_canvas_memory_size(c)==before);
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
  rectangle(rect,0,0,8,8); OK(exr_canvas_clip(c,rect,5,NULL,EXR_FILL_NONZERO,&error)); OK(exr_canvas_save(c,&error));
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
int main(void) { clip_and_ownership(); stroke_and_images(); drawing_sink(); failures(); printf("%u native canvas checks passed\n",checks); return 0; }
