/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include "graphics_internal.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error;static unsigned checks,maximum;static const char *directory;
#define CHECK(x) do { checks++;if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message);exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static void rectangle(exr_path_segment p[5],double x,double y,double w,double h) {
  memset(p,0,5*sizeof(*p));p[0].verb=EXR_PATH_MOVE;p[0].points[0]=(exr_path_point){x,y};
  p[1].verb=EXR_PATH_LINE;p[1].points[0]=(exr_path_point){x+w,y};p[2].verb=EXR_PATH_LINE;p[2].points[0]=(exr_path_point){x+w,y+h};
  p[3].verb=EXR_PATH_LINE;p[3].points[0]=(exr_path_point){x,y+h};p[4].verb=EXR_PATH_CLOSE;
}
static void oracle(void) {
  char path[4096];unsigned char bytes[128][8];FILE *f;unsigned scene,white,k;
  snprintf(path,sizeof(path),"%s/pdf-blend/nested-oracle.bin",directory);f=fopen(path,"rb");CHECK(f);
  CHECK(fread(bytes,1,sizeof(bytes),f)==sizeof(bytes));CHECK(fgetc(f)==EOF);fclose(f);
  for(scene=0;scene<128;scene++) {
    exr_fixed_document *d=NULL;snprintf(path,sizeof(path),"%s/pdf-blend/nested-%03u.pdf",directory,scene);
    OK(exr_fixed_open(path,NULL,&d,&error));
    for(white=0;white<2;white++) {
      exr_fixed_render_options options={0};exr_bitmap b={0};const unsigned char *p;
      options.channels=4;options.background=white ? 0xffffffff : 0;
      OK(exr_fixed_render(d,0,1,&options,&b,&error));p=b.pixels+8*b.stride+8*4;
      for(k=0;k<4;k++) {
        unsigned actual=white || k==3 ? p[k] : (p[k]*p[3]+127)/255;
        unsigned diff=(unsigned)abs((int)actual-(int)bytes[scene][white*4+k]);
        if(diff>maximum) maximum=diff;
        if(diff>3) fprintf(stderr,"scene %u white %u channel %u got %u want %u\n",scene,white,k,actual,bytes[scene][white*4+k]);
        CHECK(diff<=3);
      }
      exr_bitmap_free(&b);
    }
    exr_fixed_free(d);
  }
}
static exr_canvas *canvas(unsigned size) {
  exr_canvas_config config={0};exr_canvas *c=NULL;config.width=config.height=size;config.background=0x336699c0;
  OK(exr_canvas_create(&config,&c,&error));return c;
}
static void draw(exr_canvas *c,unsigned colour,unsigned cmyk) {
  exr_path_segment p[5];exr_draw_style style=exr_draw_style_defaults();rectangle(p,0,0,256,256);style.fill=colour;
  if(cmyk) { const double inks[4]={.3,.6,.2,.1};OK(exr_canvas_path_cmyk(c,p,5,NULL,&style,inks,inks,&error)); }
  else OK(exr_canvas_path(c,p,5,NULL,&style,&error));
}
static void regions(void) {
  unsigned space,kind,variant;size_t largest=0;
  for(space=0;space<2;space++) for(kind=0;kind<3;kind++) for(variant=0;variant<4;variant++) {
    exr_bitmap result[2]={{0}};unsigned whole;
    for(whole=0;whole<2;whole++) {
      exr_canvas *c=canvas(256);exr_path_segment clip[5];exr_draw_sink_ex sink={0};unsigned char mask[256*256];
      unsigned flags=(kind==0 ? EXR_GROUP_ISOLATED : kind==2 ? EXR_GROUP_KNOCKOUT : 0)|(space ? EXR_GROUP_CMYK : 0);
      const double transform[6]={1,.15,-.1,1,0,0};size_t before,added,full;
      OK(exr_canvas_begin_group(c,1,EXR_BLEND_NORMAL,flags|EXR_GROUP_WHOLE_BUFFER,&error));draw(c,0xaa6633c0,space);
      rectangle(clip,96.25,96.5,48,32);OK(exr_canvas_clip(c,clip,5,variant==1 ? transform : NULL,EXR_FILL_NONZERO,&error));
      before=exr_canvas_memory_size(c);
      OK(exr_canvas_begin_group(c,.625,EXR_BLEND_MULTIPLY,flags|(whole ? EXR_GROUP_WHOLE_BUFFER : 0),&error));
      added=exr_canvas_memory_size(c)-before;full=256*256*(size_t)(4+((flags&EXR_GROUP_ISOLATED) && !space ? 0 : 20)+(space ? 24 : 0));
      if(!whole) { CHECK(added*100<=full*20);if(added*100/full>largest) largest=added*100/full; }
      draw(c,0x20a0e080,space);
      rectangle(clip,104.5,104.25,16,12);OK(exr_canvas_clip(c,clip,5,NULL,EXR_FILL_NONZERO,&error));
      OK(exr_canvas_begin_group(c,.75,EXR_BLEND_SCREEN,flags|(whole ? EXR_GROUP_WHOLE_BUFFER : 0),&error));
      if(variant==2) {
        memset(mask,128,sizeof(mask));sink.struct_size=sizeof(sink);OK(exr_canvas_get_sink_ex(c,&sink,&error));
        OK(sink.soft_mask(c,mask,256,256,&error));
      }
      draw(c,0xff804080,space);
      if(variant==2) OK(sink.soft_mask(c,NULL,0,0,&error));
      OK(exr_canvas_end_layer(c,variant!=3,&error));OK(exr_canvas_end_layer(c,1,&error));OK(exr_canvas_end_layer(c,1,&error));
      OK(exr_canvas_take(c,&result[whole],&error));exr_canvas_free(c);
    }
    CHECK(!memcmp(result[0].pixels,result[1].pixels,(size_t)result[0].stride*result[0].height));
    exr_bitmap_free(&result[0]);exr_bitmap_free(&result[1]);
  }
  printf("24 nested crop scenarios match whole buffers; minimum working allocation reduction %zu%%\n",100-largest);
}
static void churn_and_limits(void) {
  exr_canvas *c=canvas(128);exr_path_segment clip[5];size_t stable=0;unsigned i;
  OK(exr_canvas_begin_group(c,1,EXR_BLEND_NORMAL,EXR_GROUP_KNOCKOUT|EXR_GROUP_WHOLE_BUFFER,&error));
  rectangle(clip,40,40,8,8);OK(exr_canvas_clip(c,clip,5,NULL,EXR_FILL_NONZERO,&error));
  /* Warm the layer stack; every later scope returns to exactly this payload. */
  OK(exr_canvas_begin_group(c,1,EXR_BLEND_NORMAL,0,&error));OK(exr_canvas_end_layer(c,0,&error));stable=exr_canvas_memory_size(c);
  for(i=0;i<1000;i++) {
    OK(exr_canvas_begin_group(c,.5,EXR_BLEND_NORMAL,0,&error));draw(c,0xff336680,0);OK(exr_canvas_end_layer(c,i%2,&error));
    CHECK(exr_canvas_memory_size(c)==stable);
  }
  OK(exr_canvas_end_layer(c,0,&error));exr_canvas_free(c);
  for(i=0;i<2;i++) {
    c=canvas(256);OK(exr_canvas_set_layer_budget(c,2*1024*1024,&error));
    OK(exr_canvas_begin_group(c,1,EXR_BLEND_NORMAL,EXR_GROUP_WHOLE_BUFFER,&error));
    rectangle(clip,100,100,16,16);OK(exr_canvas_clip(c,clip,5,NULL,EXR_FILL_NONZERO,&error));
    if(i) CHECK(exr_canvas_begin_group(c,1,EXR_BLEND_NORMAL,EXR_GROUP_WHOLE_BUFFER,&error)==EXR_LIMIT);
    else { OK(exr_canvas_begin_group(c,1,EXR_BLEND_NORMAL,0,&error));OK(exr_canvas_end_layer(c,0,&error)); }
    exr_canvas_free(c);
  }
  c=canvas(256);rectangle(clip,300,300,5,5);OK(exr_canvas_clip(c,clip,5,NULL,EXR_FILL_NONZERO,&error));
  OK(exr_canvas_begin_group(c,1,EXR_BLEND_NORMAL,0,&error));CHECK(exr_canvas_bitmap(c)->width==1 && exr_canvas_bitmap(c)->height==1);
  OK(exr_canvas_end_layer(c,1,&error));exr_canvas_free(c);
}
static void compound_alpha(void) {
  unsigned space,isolated,compound;
  for(space=0;space<2;space++) for(isolated=0;isolated<2;isolated++) {
    exr_bitmap result[2]={{0}};
    for(compound=0;compound<2;compound++) {
      exr_canvas *c=canvas(16);exr_path_segment p[5];exr_draw_style style=exr_draw_style_defaults();
      unsigned flags=EXR_GROUP_KNOCKOUT|(isolated ? EXR_GROUP_ISOLATED : 0)|(space ? EXR_GROUP_CMYK : 0);
      OK(exr_canvas_begin_group(c,.625,EXR_BLEND_MULTIPLY,flags,&error));draw(c,0xee2233c0,space);
      rectangle(p,0,0,256,256);style.fill=style.stroke=0x22bb6640;style.line.width=2;
      style.flags=EXR_DRAW_FILL|(compound ? EXR_DRAW_STROKE : 0);
      if(space) { const double inks[4]={.3,.6,.2,.1};OK(exr_canvas_path_cmyk(c,p,5,NULL,&style,inks,inks,&error)); }
      else OK(exr_canvas_path(c,p,5,NULL,&style,&error));
      OK(exr_canvas_end_layer(c,1,&error));OK(exr_canvas_take(c,&result[compound],&error));exr_canvas_free(c);
    }
    /* At the interior probe the compound has fill coverage only, so source
       alpha must replace the preceding object exactly as the single fill does. */
    CHECK(!memcmp(result[0].pixels+8*result[0].stride+8*4,result[1].pixels+8*result[1].stride+8*4,4));
    exr_bitmap_free(&result[0]);exr_bitmap_free(&result[1]);
  }
}
int main(int argc,char **argv) {
  CHECK(argc==2);directory=argv[1];oracle();regions();churn_and_limits();compound_alpha();
  printf("%u nested group checks, maximum Decimal probe difference %u/255\n",checks,maximum);return 0;
}
