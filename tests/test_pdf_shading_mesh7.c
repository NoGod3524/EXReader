/* SPDX-License-Identifier: GPL-3.0-only */
/* WP4: Coons (type 6) and tensor-product (type 7) mesh patches.
   Reference pixels come from MuPDF 1.28.2; DeviceCMYK documents the engine's
   naive DeviceCMYK model, which intentionally differs from a profile renderer. */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static unsigned checks; static exr_error error; static const char *directory;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static exr_bitmap render(const char *name) {
  char path[4096]; exr_fixed_document *d=NULL; exr_bitmap out={0}; exr_fixed_render_options options={0};
  snprintf(path,sizeof(path),"%s/pdf-color/%s",directory,name);
  OK(exr_fixed_open(path,NULL,&d,&error)); CHECK(d);
  options.channels=4; options.background=0xffffffff;
  OK(exr_fixed_render(d,0,1,&options,&out,&error));
  exr_fixed_free(d);
  return out;
}
static const unsigned char *at(const exr_bitmap *b,unsigned x,unsigned y) {
  return b->pixels+(size_t)y*b->stride+(size_t)x*4;
}
/* PDF coordinates are y-up; the bitmap is y-down. */
static int pixel(const exr_bitmap *b,unsigned x,unsigned pdf_y,unsigned char rgb[3]) {
  const unsigned char *p=at(b,x,b->height-1-pdf_y); unsigned k;
  for(k=0;k<3;k++) rgb[k]=p[k];
  return 1;
}
static void near(const exr_bitmap *b,unsigned x,unsigned y,unsigned char r,unsigned char g,unsigned char bl,int tolerance) {
  unsigned char rgb[3];
  pixel(b,x,y,rgb);
  CHECK(abs((int)rgb[0]-r)<=tolerance && abs((int)rgb[1]-g)<=tolerance && abs((int)rgb[2]-bl)<=tolerance);
}
static void planar(const char *name) {
  exr_bitmap b=render(name); unsigned char rgb[3];
  /* MuPDF 1.28.2: (124,127,127) at the centre, saturated corners elsewhere. */
  near(&b,50,50,124,127,127,4);
  near(&b,10,10,226,49,26,4);
  near(&b,90,10,226,207,229,4);
  near(&b,10,90,22,211,25,4);
  near(&b,90,90,22,43,230,4);
  near(&b,25,75,61,160,63,4);
  near(&b,75,25,188,158,191,4);
  pixel(&b,50,50,rgb); exr_bitmap_free(&b);
}
int main(int argc,char **argv) {
  exr_bitmap a,b; unsigned char rgb[3];
  CHECK(argc==2); directory=argv[1];
  planar("shading-mesh6.pdf");
  planar("shading-mesh7.pdf");
  /* A planar tensor patch with regular interior poles is the same surface as the
     Coons patch: both documents must rasterise to identical bytes. */
  a=render("shading-mesh6.pdf"); b=render("shading-mesh7.pdf");
  CHECK(a.width==b.width && a.height==b.height && !memcmp(a.pixels,b.pixels,(size_t)a.stride*a.height));
  exr_bitmap_free(&a); exr_bitmap_free(&b);
  /* Interior poles pulled towards the corners deform the surface; the centre
     moves towards the blue/green side. MuPDF: (107,125,146). */
  a=render("shading-mesh7-bulge.pdf");
  near(&a,50,50,107,125,146,4);
  near(&a,25,75,50,160,75,4);
  near(&a,75,25,178,159,204,4);
  pixel(&a,50,50,rgb); CHECK(rgb[2]>rgb[0]+20);   /* visibly not the planar grey */
  exr_bitmap_free(&a);
  /* DeviceCMYK uses the documented naive conversion: corner colours are red,
     cyan, blue and white, so the centre averages to (127,127,191). */
  a=render("shading-mesh7-cmyk.pdf");
  near(&a,50,50,127,127,191,3);
  { unsigned char corner[3]; pixel(&a,90,90,corner); CHECK(corner[2]>200); }
  exr_bitmap_free(&a);
  printf("%u native PDF type 6/7 mesh shading checks passed\n",checks);
  return 0;
}
