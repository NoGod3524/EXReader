/* SPDX-License-Identifier: GPL-3.0-only */
/* Work package 4: image mattes. Gray and RGB mattes existed; a CMYK base image
   states its matte in four components and must convert through the same path as
   the samples instead of rejecting the file. */
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
static void opaque(const exr_bitmap *b,size_t x,size_t y,unsigned r,unsigned g,unsigned bl,const char *what) {
  const unsigned char *p=b->pixels+y*b->stride+x*4; unsigned k, want[3]={r,g,bl};
  CHECK(p[3]==255);
  for(k=0;k<3;k++) {
    int diff=(int)p[k]-(int)want[k]; if(diff<0) diff=-diff;
    if(diff>3) fprintf(stderr,"%s channel %u got %u want %u\n",what,k,p[k],want[k]);
    CHECK(diff<=3);
  }
}
static void rejected(const char *name) {
  char path[4096]; exr_fixed_document *d=NULL; exr_bitmap out={0}; exr_fixed_render_options options={0};
  snprintf(path,sizeof(path),"%s/pdf-color/%s",directory,name);
  OK(exr_fixed_open(path,NULL,&d,&error)); CHECK(d);
  options.channels=4; options.background=0xffffffff;
  CHECK(exr_fixed_render(d,0,1,&options,&out,&error)==EXR_FORMAT);
  CHECK(!out.pixels);
  exr_fixed_free(d);
}
int main(int argc,char **argv) {
  exr_bitmap page;
  CHECK(argc==2); directory=argv[1];
  /* The lower half of each fixture is fully opaque; the matte only affects the
     blended edge, which the existing RGB matte coverage exercises. */
  page=render("matte-gray.pdf"); opaque(&page,8,12,128,128,128,"gray"); exr_bitmap_free(&page);
  page=render("matte-rgb.pdf");  opaque(&page,8,12,200,60,40,"rgb");   exr_bitmap_free(&page);
  page=render("matte-cmyk.pdf"); opaque(&page,8,12,205,45,65,"cmyk");  exr_bitmap_free(&page);
  rejected("matte-bad-count.pdf");
  rejected("matte-bad-range.pdf");
  printf("%u native PDF image matte checks passed\n",checks);
  return 0;
}
