/* SPDX-License-Identifier: MIT */
/* WP4: free-form Gouraud mesh shadings (type 4) match the reference renderer. */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static unsigned checks; static exr_error error;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static const unsigned char *at(const exr_bitmap *b,unsigned x,unsigned y) {
  return b->pixels+(size_t)y*b->stride+(size_t)x*4;
}
int main(int argc,char **argv) {
  char path[4096]; exr_fixed_document *d=NULL; exr_fixed_open_options options={0};
  exr_fixed_render_options render={0}; exr_bitmap page={0};
  CHECK(argc==2);
  snprintf(path,sizeof(path),"%s/pdf-color/shading-mesh4.pdf",argv[1]);
  options.struct_size=sizeof(options); render.channels=4; render.background=0xffffffff;
  OK(exr_fixed_open(path,&options,&d,&error));
  OK(exr_fixed_render(d,0,1,&render,&page,&error));
  CHECK(page.width==100 && page.height==100);
  /* The triangle spans (0,0)-(100,0)-(0,100) in PDF space, so it fills the upper
     left of the rasterised page; the reference renderer gives (66,0,162) at 10,75. */
  { const unsigned char *p=at(&page,10,75);
    CHECK(p[0]>50 && p[0]<90 && p[1]<12 && p[2]>130 && p[2]<200); }
  { const unsigned char *p=at(&page,5,90);
    CHECK(p[2]>40 && p[0]<70); }
  /* Points outside the triangle keep the page background. */
  { const unsigned char *p=at(&page,25,25);
    CHECK(p[0]==255 && p[1]==255 && p[2]==255); }
  { const unsigned char *p=at(&page,90,5);
    CHECK(p[0]==255 && p[1]==255 && p[2]==255); }
  exr_bitmap_free(&page); exr_fixed_free(d);
  printf("%u native PDF mesh shading checks passed\n",checks);
  return 0;
}
