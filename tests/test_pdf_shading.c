/* SPDX-License-Identifier: MIT */
/* Work package 4: axial shading (type 2). The gradient is evaluated at pixel
   centres, so these expectations are the analytic values of a red->blue ramp over
   0..16; MuPDF samples at pixel corners and is half a pixel off (see COLOR_MATRIX). */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static unsigned checks; static exr_error error;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static const char *directory;

static exr_bitmap render(const char *name) {
  char path[4096]; exr_fixed_document *d=NULL; exr_bitmap out={0}; exr_fixed_render_options options={0};
  snprintf(path,sizeof(path),"%s/pdf-color/%s",directory,name);
  OK(exr_fixed_open(path,NULL,&d,&error)); CHECK(d);
  options.channels=4; options.background=0xffffffff;
  OK(exr_fixed_render(d,0,1,&options,&out,&error));
  exr_fixed_free(d);
  return out;
}
static void near(const exr_bitmap *b,size_t x,size_t y,unsigned r,unsigned g,unsigned bl,unsigned tolerance,const char *what) {
  const unsigned char *p=b->pixels+y*b->stride+x*4; unsigned k, want[3]={r,g,bl};
  CHECK(p[3]==255);
  for(k=0;k<3;k++) {
    int diff=(int)p[k]-(int)want[k]; if(diff<0) diff=-diff;
    if(diff>(int)tolerance) fprintf(stderr,"%s channel %u got %u want %u\n",what,k,p[k],want[k]);
    CHECK(diff<=(int)tolerance);
  }
}
static void rejected(const char *name,exr_status expected) {
  char path[4096]; exr_fixed_document *d=NULL; exr_bitmap out={0}; exr_fixed_render_options options={0};
  snprintf(path,sizeof(path),"%s/pdf-color/%s",directory,name);
  OK(exr_fixed_open(path,NULL,&d,&error)); CHECK(d);
  options.channels=4; options.background=0xffffffff;
  CHECK(exr_fixed_render(d,0,1,&options,&out,&error)==expected);
  CHECK(!out.pixels);
  exr_fixed_free(d);
}
static void domains(void) {
  unsigned char expected[9][4];char path[4096];FILE *f;unsigned i;
  snprintf(path,sizeof(path),"%s/pdf-color/shading-domain-oracle.bin",directory);f=fopen(path,"rb");CHECK(f);
  CHECK(fread(expected,1,sizeof(expected),f)==sizeof(expected));CHECK(fgetc(f)==EOF);fclose(f);
  for(i=0;i<9;i++) {
    exr_bitmap b;snprintf(path,sizeof(path),"shading-domain-%u.pdf",i);b=render(path);
    near(&b,8,8,expected[i][0],expected[i][1],expected[i][2],1,path);exr_bitmap_free(&b);
  }
  for(i=0;i<11;i++) { snprintf(path,sizeof(path),"shading-domain-bad-%u.pdf",i);rejected(path,EXR_FORMAT); }
}
static void geometry(void) {
  unsigned char probe[8];char path[4096];FILE *f;size_t n;
  snprintf(path,sizeof(path),"%s/pdf-color/shading-geometry-oracle.bin",directory);f=fopen(path,"rb");CHECK(f);
  while((n=fread(probe,1,sizeof(probe),f))!=0) {
    exr_bitmap b;CHECK(n==sizeof(probe));snprintf(path,sizeof(path),"shading-geometry-%u.pdf",probe[0]);b=render(path);
    near(&b,probe[1],probe[2],probe[3],probe[4],probe[5],probe[7],path);exr_bitmap_free(&b);
  }
  CHECK(!ferror(f));fclose(f);
  for(unsigned i=0;i<4;i++) { snprintf(path,sizeof(path),"shading-geometry-bad-%u.pdf",i);rejected(path,EXR_FORMAT); }
}
static void functions(void) {
  unsigned char probe[6];char path[4096];FILE *f;size_t n;
  snprintf(path,sizeof(path),"%s/pdf-color/shading-function-oracle.bin",directory);f=fopen(path,"rb");CHECK(f);
  while((n=fread(probe,1,sizeof(probe),f))!=0) {
    CHECK(n==sizeof(probe));snprintf(path,sizeof(path),"shading-function-%u.pdf",probe[0]);
    if(probe[1]) rejected(path,(exr_status)probe[1]);
    else { exr_bitmap b=render(path);near(&b,8,8,probe[2],probe[3],probe[4],2,path);exr_bitmap_free(&b); }
  }
  CHECK(!ferror(f));fclose(f);
}
static void extents(void) {
  unsigned char expected[16*16*4];char path[4096];FILE *f;size_t n;unsigned index=0;
  snprintf(path,sizeof(path),"%s/pdf-color/shading-extent-oracle.rgba",directory);f=fopen(path,"rb");CHECK(f);
  while((n=fread(expected,1,sizeof(expected),f))!=0) {
    exr_fixed_document *d=NULL;exr_bitmap b={0};exr_fixed_render_options options={0};CHECK(n==sizeof(expected));
    snprintf(path,sizeof(path),"%s/pdf-color/shading-extent-%u.pdf",directory,index++);
    OK(exr_fixed_open(path,NULL,&d,&error));options.channels=4;OK(exr_fixed_render(d,0,1,&options,&b,&error));
    CHECK(b.width==16 && b.height==16);
    for(unsigned y=0;y<16;y++) for(unsigned x=0;x<16;x++) for(unsigned k=0;k<4;k++) {
      unsigned char got=b.pixels[y*b.stride+x*4+k],want=expected[(y*16+x)*4+k];
      if(abs((int)got-want)>2) fprintf(stderr,"%s (%u,%u) channel %u: %u != %u\n",path,x,y,k,got,want);
      CHECK(abs((int)got-want)<=2);
    }
    exr_bitmap_free(&b);exr_fixed_free(d);
  }
  CHECK(index==40 && !ferror(f));fclose(f);
  {
    exr_fixed_document *d=NULL;exr_canvas *c=NULL;exr_canvas_config config={0};exr_draw_sink_ex sink={0};
    snprintf(path,sizeof(path),"%s/pdf-color/shading-extent-5.pdf",directory);OK(exr_fixed_open(path,NULL,&d,&error));
    config.width=config.height=16;OK(exr_canvas_create(&config,&c,&error));
    sink.struct_size=offsetof(exr_draw_sink_ex,paint)+1;
    ((unsigned char *)&sink)[offsetof(exr_draw_sink_ex,paint)]=1;
    CHECK(exr_fixed_draw_ex(d,0,NULL,&sink,NULL,&error)==EXR_ARGUMENT);
    memset(&sink,0,sizeof(sink));sink.struct_size=offsetof(exr_draw_sink_ex,paint);OK(exr_canvas_get_sink_ex(c,&sink,&error));CHECK(!sink.paint);
    OK(exr_fixed_draw_ex(d,0,NULL,&sink,NULL,&error));CHECK(exr_canvas_bitmap(c)->pixels[8*64+8*4+3]==0);
    sink.struct_size=sizeof(sink);OK(exr_canvas_get_sink_ex(c,&sink,&error));
    OK(exr_fixed_draw_ex(d,0,NULL,&sink,NULL,&error));CHECK(exr_canvas_bitmap(c)->pixels[8*64+8*4+3]==255);
    exr_canvas_free(c);exr_fixed_free(d);
  }
}
int main(int argc,char **argv) {
  exr_bitmap page; const unsigned char *p;
  CHECK(argc==2); directory=argv[1];domains();geometry();functions();extents();
  page=render("shading-axial.pdf");
  near(&page,0,8,247,0,8,3,"axial left");
  near(&page,8,8,120,0,135,3,"axial middle");
  near(&page,15,8,8,0,247,3,"axial right");
  exr_bitmap_free(&page);
  page=render("shading-axial-noextend.pdf");
  /* The opaque page background shows through where the segment does not cover. */
  near(&page,0,8,255,255,255,0,"noextend outside");
  near(&page,15,8,255,255,255,0,"noextend right outside");
  near(&page,8,8,112,0,144,3,"noextend middle");
  exr_bitmap_free(&page);
  /* Radial type 3, sampled per texel at pixel centres. */
  page=render("shading-radial.pdf");
  near(&page,8,8,231,0,24,4,"radial centre");
  near(&page,8,2,79,0,176,4,"radial outer");
  exr_bitmap_free(&page);
  rejected("shading-freeform.pdf",EXR_UNSUPPORTED);
  rejected("shading-bad-coords.pdf",EXR_FORMAT);
  rejected("shading-degenerate.pdf",EXR_FORMAT);
  printf("%u native PDF shading checks passed\n",checks);
  return 0;
}
