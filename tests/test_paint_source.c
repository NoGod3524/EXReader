/* SPDX-License-Identifier: MIT */
#include "canvas_internal.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
static exr_error error;static unsigned checks;
#define CHECK(x) do { checks++;if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message);exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
typedef struct { unsigned mode,calls,space;double first[2],shape,opacity; } sampler;
static exr_status sample(void *context,double x,double y,unsigned space,double color[4],double *shape,double *opacity,exr_error *e) {
  sampler *s=context;if(!s->calls) { s->first[0]=x;s->first[1]=y; }s->calls++;s->space=space;
  *shape=s->shape;*opacity=s->opacity;
  color[0]=s->mode==1 ? x/8 : 0;color[1]=s->mode==1 ? y/8 : 0;color[2]=1;color[3]=0;
  if(s->mode==2) { e->code=EXR_CANCELLED;return EXR_OK; }
  if(s->mode==3) return EXR_IO;
  if(s->mode==4) color[0]=NAN;
  if(s->mode==5) *shape=2;
  if(s->mode==6) *opacity=INFINITY;
  return EXR_OK;
}
static exr_canvas *canvas(unsigned size,unsigned channels,exr_control control) {
  exr_canvas_config cfg={0};exr_canvas *c=NULL;cfg.width=cfg.height=size;cfg.channels=channels;cfg.control=control;
  OK(exr_canvas_create(&cfg,&c,&error));return c;
}
static void rectangle(exr_path_segment p[5],double l,double t,double r,double b) {
  memset(p,0,sizeof(*p)*5);
  for(unsigned i=0;i<4;i++) { p[i].verb=i ? EXR_PATH_LINE : EXR_PATH_MOVE;p[i].points[0]=(exr_path_point){i==1 || i==2 ? r : l,i>=2 ? b : t}; }p[4].verb=EXR_PATH_CLOSE;
}
static void coordinates(void) {
  const double matrix[6]={0,2,-2,0,8,0};exr_path_segment p[5];
  for(unsigned grouped=0;grouped<2;grouped++) {
    sampler s={1,0,0,{0},1,1};exr_paint_source source={sizeof(source),sample,&s};exr_canvas *c=canvas(8,4,(exr_control){0});
    rectangle(p,2,4,4,6);OK(exr_canvas_clip(c,p,5,NULL,EXR_FILL_NONZERO,&error));
    if(grouped) OK(exr_canvas_begin_group(c,1,EXR_BLEND_NORMAL,EXR_GROUP_ISOLATED,&error));
    size_t memory=exr_canvas_memory_size(c);OK(exr_canvas_paint(c,&source,matrix,1,&error));CHECK(memory==exr_canvas_memory_size(c));
    CHECK(s.calls==16 && s.space==EXR_GROUP_RGB);CHECK(fabs(s.first[0]-2.125)<1e-12 && fabs(s.first[1]-2.875)<1e-12);
    if(grouped) OK(exr_canvas_end_layer(c,1,&error));
    const exr_bitmap *b=exr_canvas_bitmap(c);const unsigned char *pixel=b->pixels+4*b->stride+2*4;
    CHECK(pixel[0]==72 && pixel[1]==88 && pixel[2]==255 && pixel[3]==255);CHECK(b->pixels[3]==0);exr_canvas_free(c);
  }
  { sampler s={0,0,0,{0},1,1};exr_paint_source source={sizeof(source),sample,&s};exr_canvas *c=canvas(1,1,(exr_control){0});
    OK(exr_canvas_paint(c,&source,NULL,1,&error));CHECK(exr_canvas_bitmap(c)->pixels[0]==29);exr_canvas_free(c);
  }
}
static void compositing(void) {
  for(unsigned cmyk=0;cmyk<2;cmyk++) for(unsigned ais=0;ais<2;ais++) for(unsigned zero=0;zero<2;zero++) for(unsigned mask=0;mask<2;mask++) {
    sampler s={0,0,0,{0},1,1};exr_paint_source source={sizeof(source),sample,&s};exr_canvas *c=canvas(1,4,(exr_control){0});
    exr_path_segment p[5];exr_draw_style style=exr_draw_style_defaults();exr_draw_sink_ex sink={0};unsigned char value=128;
    sink.struct_size=sizeof(sink);OK(exr_canvas_get_sink_ex(c,&sink,&error));CHECK(sink.paint);
    OK(exr_canvas_begin_group(c,1,EXR_BLEND_NORMAL,EXR_GROUP_ISOLATED|EXR_GROUP_KNOCKOUT|(cmyk ? EXR_GROUP_CMYK : EXR_GROUP_RGB),&error));
    rectangle(p,0,0,1,1);style.fill=0xff0000ff;OK(exr_canvas_path(c,p,5,NULL,&style,&error));
    OK(sink.alpha_source(c,ais ? EXR_ALPHA_CONSTANT_SHAPE : 0,&error));if(mask) OK(sink.soft_mask(c,&value,1,1,&error));
    OK(sink.paint(c,&source,NULL,zero ? 0 : .5,&error));CHECK(s.space== (cmyk ? EXR_GROUP_CMYK : EXR_GROUP_RGB) || (zero && ais));
    OK(exr_canvas_end_layer(c,1,&error));const unsigned char *pixel=exr_canvas_bitmap(c)->pixels;
    if(ais) CHECK(pixel[3]==255);else CHECK(abs((int)pixel[3]-(zero ? 0 : mask ? 64 : 128))<=1);
    exr_canvas_free(c);
  }
  { sampler s={0,0,0,{0},0,1};exr_paint_source source={sizeof(source),sample,&s};exr_canvas *c=canvas(1,4,(exr_control){0});
    OK(exr_canvas_paint(c,&source,NULL,1,&error));CHECK(exr_canvas_bitmap(c)->pixels[3]==0);exr_canvas_free(c);
  }
}
static int cancel(void *context) { return ++*(unsigned *)context>=4; }
static void errors(void) {
  for(unsigned mode=2;mode<=6;mode++) {
    sampler s={mode,0,0,{0},1,1};exr_paint_source source={sizeof(source),sample,&s};exr_canvas *c=canvas(1,4,(exr_control){0});exr_bitmap b={0};
    exr_status expected=mode==2 ? EXR_CANCELLED : mode==3 ? EXR_IO : EXR_ARGUMENT;
    CHECK(exr_canvas_paint(c,&source,NULL,1,&error)==expected);CHECK(s.calls==1);
    CHECK(exr_canvas_take(c,&b,&error)==expected && !b.pixels);exr_canvas_free(c);
  }
  for(unsigned mode=0;mode<9;mode++) {
    sampler s={0,0,0,{0},1,1};struct { exr_paint_source source;unsigned char tail[8]; } input={{sizeof(input),sample,&s},{0}};
    double matrix[6]={1,0,0,1,0,0},alpha=1;exr_canvas *c=canvas(1,4,(exr_control){0});
    if(mode==1) input.tail[0]=1;
    if(mode==2) input.source.struct_size=sizeof(exr_paint_source)-1;
    if(mode==3) input.source.struct_size=4097;
    if(mode==4) input.source.sample=NULL;
    if(mode==5) alpha=NAN;
    if(mode==6) alpha=-1;
    if(mode==7) matrix[0]=INFINITY;
    if(mode==8) matrix[3]=0;
    CHECK(exr_canvas_paint(c,&input.source,matrix,alpha,&error)==(mode==0 || mode==8 ? EXR_OK : EXR_ARGUMENT));
    CHECK(s.calls==(mode==0 ? 4u : 0u));exr_canvas_free(c);
  }
  { unsigned polls=0;exr_control control={0};control.context=&polls;control.cancelled=cancel;
    sampler s={0,0,0,{0},1,1};exr_paint_source source={sizeof(source),sample,&s};exr_canvas *c=canvas(8,4,control);
    CHECK(exr_canvas_paint(c,&source,NULL,1,&error)==EXR_CANCELLED);CHECK(s.calls<=64);exr_canvas_free(c);
  }
  { sampler s={0,0,0,{0},1,1};exr_paint_source source={sizeof(source),sample,&s};exr_canvas *c=canvas(1,4,(exr_control){0});
    c->work=256u*1024u*1024u;CHECK(exr_canvas_paint(c,&source,NULL,1,&error)==EXR_LIMIT);CHECK(!s.calls);exr_canvas_free(c);
  }
}
static void prefixes(void) {
  exr_canvas *c=canvas(1,4,(exr_control){0});exr_draw_sink_ex sink={0};
  for(size_t size=offsetof(exr_draw_sink_ex,paint);size<sizeof(sink);size++) {
    sink.struct_size=size;OK(exr_canvas_get_sink_ex(c,&sink,&error));CHECK(!sink.paint);CHECK(sink.struct_size==offsetof(exr_draw_sink_ex,paint));
  }
  sink.struct_size=sizeof(sink);OK(exr_canvas_get_sink_ex(c,&sink,&error));CHECK(sink.paint);exr_canvas_free(c);
}
static void clipped_budget(int verify) {
  for(unsigned clipped=0;clipped<2;clipped++) {
    const unsigned size=3072;sampler s={0,0,0,{0},1,1};
    exr_paint_source source={sizeof(source),sample,&s};exr_canvas *c=canvas(size,4,(exr_control){0});
    exr_path_segment path[10];exr_status status;clock_t start;double cpu_ms;size_t work;unsigned long long hash=1469598103934665603ULL;
    if(clipped) {
      rectangle(path,100,100,104,104);rectangle(path+5,101,101,103,103);
      OK(exr_canvas_clip(c,path,10,NULL,EXR_FILL_EVENODD,&error));
    }
    c->work=0;start=clock();status=exr_canvas_paint(c,&source,NULL,1,&error);
    cpu_ms=(double)(clock()-start)*1000/CLOCKS_PER_SEC;work=c->work;
    if(c->bitmap.pixels) {
      /* On LIMIT this is diagnostic working memory, never published output. */
      const exr_bitmap *b=&c->bitmap;
      for(size_t i=0;i<(size_t)b->stride*b->height;i++) { hash^=b->pixels[i];hash*=1099511628211ULL; }
    }
    printf("{\"scenario\":\"%s\",\"status\":%d,\"calls\":%u,\"charged_work\":%zu,\"cpu_ms\":%.6f,\"pixel_hash\":\"%016llx\"}\n",
      clipped ? "tiny-clip-with-hole" : "full-canvas",status,s.calls,work,cpu_ms,hash);
    if(verify) {
      if(clipped) {
        const exr_bitmap *b=exr_canvas_bitmap(c);const unsigned char *pixel;
        CHECK(status==EXR_OK && s.calls==12*4);CHECK(work==(size_t)size*size+16+12*48);
        pixel=b->pixels+100*b->stride+100*4;CHECK(pixel[2]==255 && pixel[3]==255);
        pixel=b->pixels+101*b->stride+101*4;CHECK(!pixel[0] && !pixel[1] && !pixel[2] && !pixel[3]);
        CHECK(!b->pixels[3]);
      } else {
        exr_bitmap b={0};CHECK(status==EXR_LIMIT && s.calls>0);
        CHECK(work<=256u*1024u*1024u);CHECK(exr_canvas_take(c,&b,&error)==EXR_LIMIT && !b.pixels);
      }
    }
    exr_canvas_free(c);
  }
}
int main(void) { coordinates();compositing();errors();prefixes();clipped_budget(1);printf("%u procedural paint checks passed\n",checks);return 0; }
