/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error;static unsigned checks,maximum;static const char *directory;
#define CHECK(x) do { checks++;if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message);exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static exr_fixed_document *open_scene(const char *name) {
  char path[4096];exr_fixed_document *d=NULL;snprintf(path,sizeof(path),"%s/pdf-blend/%s",directory,name);
  OK(exr_fixed_open(path,NULL,&d,&error));return d;
}
static void scenes(void) {
  const char *primitives[]={"path","text","group","shading","soft","explicit","key","compound"};
  unsigned i,a,p,r,w,k,row=0;unsigned char expected[166][8];char path[4096];FILE *f;
  snprintf(path,sizeof(path),"%s/pdf-blend/alpha-source-oracle.bin",directory);f=fopen(path,"rb");CHECK(f);
  CHECK(fread(expected,1,sizeof(expected),f)==sizeof(expected));CHECK(fgetc(f)==EOF);fclose(f);
  for(i=0;i<2;i++) for(a=0;a<2;a++) for(p=0;p<8;p++) for(r=64;r<=192;r+=64) {
    exr_fixed_document *d;snprintf(path,sizeof(path),"alpha-source-%s-%s-%s-%u.pdf",i ? "iso" : "noniso",a ? "shape" : "opacity",primitives[p],r);d=open_scene(path);
    for(w=0;w<2;w++) {
      exr_bitmap b={0};exr_fixed_render_options options={0};const unsigned char *pixel;options.channels=4;options.background=w ? 0xffffffff : 0;
      OK(exr_fixed_render(d,0,1,&options,&b,&error));pixel=b.pixels+8*b.stride+8*4;
      for(k=0;k<4;k++) {
        unsigned got=w || k==3 ? pixel[k] : (pixel[k]*pixel[3]+127)/255,diff=(unsigned)abs((int)got-(int)expected[row][4*w+k]);
        if(diff>maximum) maximum=diff;
        if(diff>2) fprintf(stderr,"%s white %u channel %u: %u != %u\n",path,w,k,got,expected[row][4*w+k]);
        CHECK(diff<=2);
      }
      exr_bitmap_free(&b);
    }
    row++;exr_fixed_free(d);
  }
  { const char *names[]={"restore","retain","null"};
    for(a=0;a<2;a++) for(i=0;i<3;i++) {
      exr_fixed_document *d;exr_bitmap b={0};exr_fixed_render_options options={0};options.channels=4;
      snprintf(path,sizeof(path),"alpha-source-state-%s-%s.pdf",a ? "shape" : "opacity",names[i]);d=open_scene(path);
      OK(exr_fixed_render(d,0,1,&options,&b,&error));
      for(k=0;k<4;k++) { const unsigned char *pixel=b.pixels+8*b.stride+8*4;unsigned got=k==3 ? pixel[k] : (pixel[k]*pixel[3]+127)/255;CHECK(abs((int)got-(int)expected[row][k])<=2); }
      row++;exr_bitmap_free(&b);exr_fixed_free(d);
    }
  }
  { const char *modes[]={"Normal","Multiply","Screen","Overlay","Darken","Lighten","ColorDodge","ColorBurn","HardLight","SoftLight","Difference","Exclusion","Hue","Saturation","Color","Luminosity"};
    for(a=0;a<2;a++) for(p=0;p<2;p++) for(i=0;i<16;i++) {
      exr_fixed_document *d;snprintf(path,sizeof(path),"alpha-source-blend-%s-%s-%s.pdf",a ? "shape" : "opacity",p ? "group" : "path",modes[i]);d=open_scene(path);
      for(w=0;w<2;w++) {
        exr_bitmap b={0};exr_fixed_render_options options={0};options.channels=4;options.background=w ? 0xffffffff : 0;
        OK(exr_fixed_render(d,0,1,&options,&b,&error));
        for(k=0;k<4;k++) { const unsigned char *pixel=b.pixels+8*b.stride+8*4;unsigned got=k==3 || w ? pixel[k] : (pixel[k]*pixel[3]+127)/255;unsigned diff=(unsigned)abs((int)got-(int)expected[row][4*w+k]);if(diff>maximum) maximum=diff;CHECK(diff<=2); }
        exr_bitmap_free(&b);
      }
      row++;exr_fixed_free(d);
    }
  }
  CHECK(row==166);
  for(i=0;i<4;i++) {
    exr_fixed_document *d;exr_bitmap b={0};snprintf(path,sizeof(path),"alpha-source-bad-%u.pdf",i);d=open_scene(path);
    CHECK(exr_fixed_render(d,0,1,NULL,&b,&error)==EXR_FORMAT && !b.pixels);exr_fixed_free(d);
  }
}
static exr_canvas *canvas(unsigned size) {
  exr_canvas *c=NULL;exr_canvas_config config={0};config.width=config.height=size;OK(exr_canvas_create(&config,&c,&error));return c;
}
static void state(void) {
  exr_canvas *c=canvas(1);exr_draw_sink_ex sink={0};exr_draw_style style=exr_draw_style_defaults();exr_bitmap b={0};
  exr_path_segment path[5]={0};unsigned i;
  for(i=0;i<4;i++) { path[i].verb=i ? EXR_PATH_LINE : EXR_PATH_MOVE;path[i].points[0]=(exr_path_point){i==1 || i==2 ? 1 : 0,i>=2 ? 1 : 0}; }path[4].verb=EXR_PATH_CLOSE;
  sink.struct_size=sizeof(sink);OK(exr_canvas_get_sink_ex(c,&sink,&error));CHECK(sink.alpha_source);
  OK(exr_canvas_begin_group(c,1,EXR_BLEND_NORMAL,EXR_GROUP_ISOLATED|EXR_GROUP_KNOCKOUT,&error));
  style.fill=0xff0000ff;OK(exr_canvas_path(c,path,5,NULL,&style,&error));
  OK(sink.alpha_source(sink.base.context,EXR_ALPHA_CONSTANT_SHAPE,&error));OK(exr_canvas_save(c,&error));
  OK(sink.alpha_source(sink.base.context,0,&error));OK(exr_canvas_restore(c,&error));
  style.fill=0x0000ff80;OK(exr_canvas_path(c,path,5,NULL,&style,&error));
  OK(exr_canvas_end_layer(c,1,&error));OK(exr_canvas_take(c,&b,&error));
  CHECK(b.pixels[0]>=126 && b.pixels[0]<=128 && b.pixels[1]==0 && b.pixels[2]>=127 && b.pixels[2]<=129 && b.pixels[3]==255);
  exr_bitmap_free(&b);exr_canvas_free(c);
  c=canvas(1);sink.struct_size=sizeof(sink);OK(exr_canvas_get_sink_ex(c,&sink,&error));
  CHECK(sink.alpha_source(sink.base.context,4,&error)==EXR_ARGUMENT);exr_canvas_free(c);
}
static exr_status callback_error(void *context,unsigned flags,exr_error *e) {
  (void)context;(void)flags;e->code=EXR_CANCELLED;snprintf(e->message,sizeof(e->message),"effect cancelled");return EXR_OK;
}
static void prefix(void) {
  exr_canvas *c=canvas(16);exr_draw_sink_ex sink={0};exr_fixed_document *d=open_scene("alpha-source-iso-shape-path-128.pdf");
  sink.struct_size=offsetof(exr_draw_sink_ex,alpha_source);OK(exr_canvas_get_sink_ex(c,&sink,&error));CHECK(!sink.alpha_source);
  CHECK(exr_fixed_draw_ex(d,0,NULL,&sink,NULL,&error)==EXR_UNSUPPORTED);exr_canvas_free(c);
  c=canvas(16);sink.struct_size=sizeof(sink);OK(exr_canvas_get_sink_ex(c,&sink,&error));sink.alpha_source=callback_error;
  CHECK(exr_fixed_draw_ex(d,0,NULL,&sink,NULL,&error)==EXR_CANCELLED);exr_canvas_free(c);
  memset(&sink,0,sizeof(sink));sink.struct_size=offsetof(exr_draw_sink_ex,alpha_source)+1;
  ((unsigned char *)&sink)[offsetof(exr_draw_sink_ex,alpha_source)]=1;
  CHECK(exr_fixed_draw_ex(d,0,NULL,&sink,NULL,&error)==EXR_ARGUMENT);exr_fixed_free(d);
}
int main(int argc,char **argv) {
  CHECK(argc==2);directory=argv[1];scenes();state();prefix();printf("%u alpha source checks; maximum Decimal difference %u/255\n",checks,maximum);return 0;
}
