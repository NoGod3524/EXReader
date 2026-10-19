/* SPDX-License-Identifier: GPL-3.0-only */
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
int main(int argc,char **argv) {
  exr_bitmap page; const unsigned char *p;
  CHECK(argc==2); directory=argv[1];
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
  rejected("shading-radial.pdf",EXR_UNSUPPORTED);
  rejected("shading-bad-coords.pdf",EXR_FORMAT);
  rejected("shading-degenerate.pdf",EXR_FORMAT);
  printf("%u native PDF shading checks passed\n",checks);
  return 0;
}
