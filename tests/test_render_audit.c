/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include "../src/graphics_internal.h"
#include <math.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static unsigned checks,failures;
static exr_error error;
#define CHECK(x) do { checks++;if(!(x)) { failures++;fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static exr_path_segment rect[5]={
  {.verb=EXR_PATH_MOVE,.points={{0,0}}}, {.verb=EXR_PATH_LINE,.points={{8,0}}},
  {.verb=EXR_PATH_LINE,.points={{8,8}}}, {.verb=EXR_PATH_LINE,.points={{0,8}}}, {.verb=EXR_PATH_CLOSE}
};
static exr_canvas *canvas(uint32_t background) {
  exr_canvas_config cfg={0};exr_canvas *c=NULL;
  cfg.width=cfg.height=8;cfg.channels=4;cfg.background=background;
  OK(exr_canvas_create(&cfg,&c,&error));return c;
}
static void fill(exr_canvas *c,const double values[4],unsigned alpha) {
  exr_draw_style s=exr_draw_style_defaults();s.fill=(s.fill&~255u)|alpha;
  OK(exr_canvas_path_cmyk(c,rect,5,NULL,&s,values,values,&error));
}
static void finish(exr_canvas *c,unsigned char pixel[4]) {
  exr_bitmap b={0};OK(exr_canvas_take(c,&b,&error));
  if(b.pixels) memcpy(pixel,b.pixels+4*b.stride+16,4);
  exr_bitmap_free(&b);exr_canvas_free(c);
}
static void cmyk_modes(void) {
  const double back[4]={.2,.4,.6,.1},source[4]={.5,.7,.3,.2};
  const exr_blend_mode modes[]={EXR_BLEND_MULTIPLY,EXR_BLEND_SCREEN,EXR_BLEND_DARKEN,EXR_BLEND_LIGHTEN,EXR_BLEND_DIFFERENCE};
  size_t i;unsigned k;unsigned char actual[4]={0},expected[4]={0};
  for(i=0;i<sizeof(modes)/sizeof(*modes);i++) {
    double mixed[4];exr_canvas *c=canvas(0);
    for(k=0;k<4;k++) {
      double b=back[k],s=source[k];
      mixed[k]=modes[i]==EXR_BLEND_MULTIPLY ? b+s-b*s : modes[i]==EXR_BLEND_SCREEN ? b*s :
        modes[i]==EXR_BLEND_DARKEN ? fmax(b,s) : modes[i]==EXR_BLEND_LIGHTEN ? fmin(b,s) : 1-fabs(b-s);
    }
    OK(exr_canvas_begin_group(c,1,EXR_BLEND_NORMAL,EXR_GROUP_ISOLATED|EXR_GROUP_CMYK,&error));
    fill(c,back,255);OK(exr_canvas_blend(c,modes[i],&error));fill(c,source,255);
    OK(exr_canvas_end_layer(c,1,&error));finish(c,actual);
    c=canvas(0);fill(c,mixed,255);finish(c,expected);
    for(k=0;k<4;k++) CHECK(abs((int)actual[k]-expected[k])<=1);
  }
  /* Luminosity selects source K, other nonseparable modes select backdrop K.
     Neutral CMY makes the CMY part invariant, independently testing K. */
  for(i=EXR_BLEND_HUE;i<=EXR_BLEND_LUMINOSITY;i++) {
    const double a[4]={.2,.2,.2,.1},b[4]={.2,.2,.2,.7};double m[4]={.2,.2,.2,.1};
    exr_canvas *c=canvas(0);m[3]=i==EXR_BLEND_LUMINOSITY ? .7 : .1;
    OK(exr_canvas_begin_group(c,1,EXR_BLEND_NORMAL,EXR_GROUP_ISOLATED|EXR_GROUP_CMYK,&error));
    fill(c,a,255);OK(exr_canvas_blend(c,(exr_blend_mode)i,&error));fill(c,b,255);
    OK(exr_canvas_end_layer(c,1,&error));finish(c,actual);
    c=canvas(0);fill(c,m,255);finish(c,expected);
    for(k=0;k<4;k++) CHECK(abs((int)actual[k]-expected[k])<=1);
  }
  /* A child has its own group alpha, even when it inherits a painted parent. */
  {
    const double a[4]={.2,.4,.1,.3},b[4]={.1,.2,.4,.1};exr_canvas *c=canvas(0);
    OK(exr_canvas_begin_group(c,1,EXR_BLEND_NORMAL,EXR_GROUP_ISOLATED|EXR_GROUP_CMYK,&error));fill(c,a,128);
    OK(exr_canvas_begin_group(c,.5,EXR_BLEND_NORMAL,0,&error));fill(c,b,128);
    OK(exr_canvas_end_layer(c,1,&error));OK(exr_canvas_end_layer(c,1,&error));finish(c,actual);
    CHECK(abs((int)actual[3]-160)<=1); /* .5 + (.5*.5)*(1-.5) */
  }
}
static void cropped_groups(void) {
  unsigned space,nested,mask;
  for(space=0;space<2;space++) for(nested=0;nested<2;nested++) for(mask=0;mask<2;mask++) {
    exr_bitmap images[2]={{0}};unsigned whole;
    for(whole=0;whole<2;whole++) {
      exr_canvas *c=canvas(0);exr_path_segment clip[5];exr_draw_style style=exr_draw_style_defaults();
      const double shift[6]={1,0,0,1,1.25,2.25};unsigned char coverage[64];exr_draw_sink_ex sink={0};
      unsigned flags=EXR_GROUP_ISOLATED|(space ? EXR_GROUP_CMYK : 0)|(whole ? EXR_GROUP_WHOLE_BUFFER : 0);
      memcpy(clip,rect,sizeof(clip));
      clip[1].points[0].x=clip[2].points[0].x=5;
      clip[2].points[0].y=clip[3].points[0].y=4;
      OK(exr_canvas_clip(c,clip,5,shift,EXR_FILL_NONZERO,&error));
      OK(exr_canvas_begin_group(c,.75,EXR_BLEND_NORMAL,flags,&error));
      if(nested) OK(exr_canvas_begin_group(c,.5,EXR_BLEND_NORMAL,0,&error));
      if(mask) { sink.struct_size=sizeof(sink);OK(exr_canvas_get_sink_ex(c,&sink,&error));memset(coverage,128,sizeof(coverage));OK(sink.soft_mask(sink.base.context,coverage,8,8,&error)); }
      style.fill=0xff000080;
      if(space) fill(c,(const double[4]){0,1,1,0},128);
      else OK(exr_canvas_path(c,rect,5,NULL,&style,&error));
      if(mask) OK(sink.soft_mask(sink.base.context,NULL,0,0,&error));
      if(nested) OK(exr_canvas_end_layer(c,1,&error));
      OK(exr_canvas_end_layer(c,1,&error));OK(exr_canvas_take(c,&images[whole],&error));exr_canvas_free(c);
    }
    CHECK(images[0].stride==images[1].stride && images[0].height==images[1].height);
    if(images[0].pixels && images[1].pixels) CHECK(!memcmp(images[0].pixels,images[1].pixels,images[0].stride*images[0].height));
    exr_bitmap_free(&images[0]);exr_bitmap_free(&images[1]);
  }
}
static void soft_mask_budget(void) {
  unsigned limit;
  for(limit=64;limit<=68;limit+=4) {
    exr_canvas_config cfg={0};exr_canvas *c=NULL;exr_draw_sink_ex sink={0};
    unsigned char mask[64];double matrix[6]={.25,0,0,.25,2,2};size_t before;
    cfg.width=cfg.height=8;cfg.channels=4;cfg.mask_budget=limit;
    OK(exr_canvas_create(&cfg,&c,&error));
    OK(exr_canvas_clip(c,rect,5,matrix,EXR_FILL_NONZERO,&error));
    OK(exr_canvas_begin_layer(c,1,EXR_BLEND_NORMAL,&error));
    before=exr_canvas_memory_size(c);sink.struct_size=sizeof(sink);
    OK(exr_canvas_get_sink_ex(c,&sink,&error));memset(mask,128,sizeof(mask));
    if(limit==64) {
      CHECK(sink.soft_mask(sink.base.context,mask,8,8,&error)==EXR_LIMIT);
      CHECK(exr_canvas_memory_size(c)==before);
    } else {
      OK(sink.soft_mask(sink.base.context,mask,8,8,&error));
      CHECK(exr_canvas_memory_size(c)==before+4);
      OK(sink.soft_mask(sink.base.context,mask,8,8,&error));
      CHECK(exr_canvas_memory_size(c)==before+4);
      OK(sink.soft_mask(sink.base.context,NULL,0,0,&error));
      CHECK(exr_canvas_memory_size(c)==before);
      OK(exr_canvas_end_layer(c,0,&error));
    }
    exr_canvas_free(c);
  }
}
static void prefixes(void) {
  const size_t offsets[]={offsetof(exr_draw_sink_ex,soft_mask),offsetof(exr_draw_sink_ex,extent),
    offsetof(exr_draw_sink_ex,shading),offsetof(exr_draw_sink_ex,path_cmyk),
    offsetof(exr_draw_sink_ex,image_cmyk),offsetof(exr_draw_sink_ex,image_space),offsetof(exr_draw_sink_ex,alpha_source)};
  size_t i;exr_canvas *c=canvas(0);
  for(i=0;i<sizeof(offsets)/sizeof(*offsets);i++) {
    exr_draw_sink_ex s={0};unsigned char *bytes=(unsigned char *)&s;
    s.struct_size=offsets[i]+1;OK(exr_canvas_get_sink_ex(c,&s,&error));
    CHECK(s.struct_size==offsets[i]);CHECK(bytes[offsets[i]]==0);
  }
  exr_canvas_free(c);
}
static exr_status no_path(void *ctx,const exr_path_segment *p,size_t n,const double m[6],const exr_draw_style *s,exr_error *e) {
  (void)ctx;(void)p;(void)n;(void)m;(void)s;(void)e;return EXR_OK;
}
static exr_status no_shading(void *ctx,const exr_bitmap *b,const double m[6],exr_error *e) {
  (void)ctx;(void)b;(void)m;(void)e;return EXR_OK;
}
static int cancel(void *ctx) { unsigned *n=ctx;return ++*n>=40; }
static void pdfs(const char *directory) {
  const char *names[]={"shading-alpha.pdf","shading-blend.pdf","shading-mask.pdf",
    "mesh4-continue.pdf","mesh5.pdf","mesh-function-gray.pdf","mesh6-packed.pdf","gray-image.pdf","page-cmyk.pdf","appearance-cmyk.pdf"};
  unsigned i;char path[4096];
  for(i=0;i<sizeof(names)/sizeof(*names);i++) {
    exr_fixed_document *d=NULL;exr_bitmap b={0};exr_fixed_render_options cfg={0};const unsigned char *p;
    snprintf(path,sizeof(path),"%s/render-audit/%s",directory,names[i]);
    OK(exr_fixed_open(path,NULL,&d,&error));cfg.channels=4;cfg.background=0xffffffff;
    OK(exr_fixed_render(d,0,1,&cfg,&b,&error));
    if(b.pixels) {
      p=b.pixels+70*b.stride+20*4;
      if(i==0 || i==2) CHECK(p[0]>=253 && abs((int)p[1]-191)<=3 && abs((int)p[2]-191)<=3);
      else if(i==1) CHECK(p[0]==0 && p[1]==0 && p[2]==0);
      else if(i>=8) CHECK(p[2]>p[0]+10);
      else if(i==7) CHECK(p[0]==127 && p[1]==127 && p[2]==127);
      else if(i==5) CHECK(abs((int)p[0]-64)<=1 && p[0]==p[1] && p[1]==p[2]);
      else if(i==6) {
        CHECK(p[0]==255 && p[1]==0 && p[2]==0);
        p=b.pixels+70*b.stride+80*4;CHECK(p[0]==0 && p[1]==0 && p[2]==255);
      } else CHECK(abs((int)p[0]-127)<=4 && abs((int)p[1]-52)<=4 && abs((int)p[2]-76)<=4);
    }
    exr_bitmap_free(&b);exr_fixed_free(d);
  }
  {
    exr_fixed_document *d=NULL;exr_draw_sink_ex sink={0};exr_control control={0};unsigned polls=0;
    snprintf(path,sizeof(path),"%s/render-audit/mesh6-packed.pdf",directory);
    OK(exr_fixed_open(path,NULL,&d,&error));sink.struct_size=sizeof(sink);sink.base.path=no_path;sink.shading=no_shading;
    control.cancelled=cancel;control.context=&polls;
    CHECK(exr_fixed_draw_ex(d,0,NULL,&sink,&control,&error)==EXR_CANCELLED);CHECK(polls<=42);
    exr_fixed_free(d);
  }
  {
    exr_fixed_document *d=NULL;exr_bitmap b={0};
    snprintf(path,sizeof(path),"%s/render-audit/mask-cycle.pdf",directory);
    OK(exr_fixed_open(path,NULL,&d,&error));CHECK(exr_fixed_render(d,0,1,NULL,&b,&error)==EXR_LIMIT);CHECK(!b.pixels);
    exr_fixed_free(d);
  }
}
int main(int argc,char **argv) {
  CHECK(argc==2);if(argc!=2) return 1;
  cmyk_modes();cropped_groups();soft_mask_budget();prefixes();pdfs(argv[1]);
  { const double c[4]={0};CHECK(exr_canvas_path_cmyk(NULL,NULL,0,NULL,NULL,c,c,&error)==EXR_ARGUMENT); }
  printf("%u renderer audit checks; %u failures\n",checks,failures);return failures ? 1 : 0;
}
