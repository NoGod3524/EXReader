/* SPDX-License-Identifier: GPL-3.0-only */
/* Work package 4: transparency group colour spaces. A DeviceGray group blends
   luminance, so a red fill must come out grey; DeviceRGB stays unchanged. A
   DeviceCMYK group is accepted and composites in device RGB after the engine's
   naive CMYK conversion (no ICC profile is bundled), so `0 1 1 0 k` is pure red
   where a SWOP renderer gives (237, 28, 36). */
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
  /* `0 1 1 0 k` is pure red under the naive DeviceCMYK model; MuPDF's SWOP
     profile renders (237, 28, 36) instead. */
  page=render("groupcmyk.pdf");
  p=page.pixels+8*page.stride+8*4;
  CHECK(p[0]==255 && p[1]==0 && p[2]==0);
  exr_bitmap_free(&page);
  printf("%u native PDF group colour-space checks passed\n",checks);
  return 0;
}
