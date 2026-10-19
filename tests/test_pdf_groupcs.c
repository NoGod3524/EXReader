/* SPDX-License-Identifier: MIT */
/* Transparency group color spaces: DeviceGray uses luminance, DeviceRGB
   preserves RGB, and DeviceCMYK blends native inks before ICC conversion. */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "cmyk_reference.h"
#include <math.h>
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
int main(int argc,char **argv) {
  exr_bitmap page; const unsigned char *p;
  CHECK(argc==2); directory=argv[1];
  page=render("groupgray.pdf");
  p=page.pixels+8*page.stride+8*4;
  CHECK(p[0]==p[1] && p[1]==p[2]);          /* grey, not red */
  CHECK(p[0]>=124 && p[0]<=134);            /* MuPDF renders 129 */
  exr_bitmap_free(&page);
  page=render("grouprgb.pdf");
  p=page.pixels+8*page.stride+8*4;
  CHECK(p[0]==255 && p[1]==0 && p[2]==0);   /* RGB group untouched */
  exr_bitmap_free(&page);
  /* Compare the same inks with an independently constructed ICC transform. */
  page=render("groupcmyk.pdf");
  p=page.pixels+8*page.stride+8*4;
  { unsigned rgb[3],k;cmyk_reference((const double[4]){0,1,1,0},rgb);for(k=0;k<3;k++) CHECK(abs((int)p[k]-(int)rgb[k])<=1); }
  exr_bitmap_free(&page);
  /* Translucent rich black then white, both 50%, blended in DeviceCMYK:
     (1/3,1/3,0,1/3) at alpha 0.75. The blue cast checks the ink-space path. */
  page=render("groupcmyk-blend.pdf");
  p=page.pixels+8*page.stride+8*4;
  { unsigned rgb[3],k;double a=.5,total=a+a-a*a,v=a*(1-a)/total;
    cmyk_reference((const double[4]){v,v,0,v},rgb);for(k=0;k<3;k++) CHECK(abs((int)p[k]-(int)floor(total*rgb[k]+(1-total)*255+.5))<=2); }
  CHECK(p[2]>p[0]+10);
  exr_bitmap_free(&page);
  printf("%u native PDF group colour-space checks passed\n",checks);
  return 0;
}
