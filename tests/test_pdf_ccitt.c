/* SPDX-License-Identifier: GPL-3.0-only */
/* WP4a image filters: CCITT Group 4 decoding against a Pillow-produced strip. */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static unsigned checks; static exr_error error;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static const char *directory;

static void path_of(char *out,size_t size,const char *name) { snprintf(out,size,"%s/pdf-color/%s",directory,name); }
int main(int argc,char **argv) {
  char path[4096]; exr_fixed_document *d=NULL; exr_fixed_open_options options={0};
  exr_fixed_render_options render={0}; exr_bitmap page={0}; unsigned x,y;
  CHECK(argc==2); directory=argv[1];
  options.struct_size=sizeof(options); render.channels=4; render.background=0xffffffff;
  /* The same picture is encoded once as Group 4 and once as Group 3; both must
     decode to the reference polarity. */
  { const char *names[]={"ccitt-g4.pdf","ccitt-g3.pdf"}; size_t n;
    for(n=0;n<sizeof(names)/sizeof(*names);n++) {
      path_of(path,sizeof(path),names[n]);
      OK(exr_fixed_open(path,&options,&d,&error));
      OK(exr_fixed_render(d,0,1,&render,&page,&error));
      CHECK(page.width==32 && page.height==8);
      /* A white page with a black rectangle in rows 2..5, columns 4..19. Polarity
         follows the reference renderer: the rectangle is white, the rest black. */
      for(y=0;y<8;y++) for(x=0;x<32;x++) {
        int inside=y>=2 && y<=5 && x>=4 && x<=19;
        const unsigned char *p=page.pixels+(size_t)y*page.stride+x*4;
        int white=p[0]==255 && p[1]==255 && p[2]==255;
        CHECK(white==inside);
      }
      exr_bitmap_free(&page); exr_fixed_free(d);
    }
  }
  /* A truncated Group 4 stream is rejected, not silently drawn. */
  path_of(path,sizeof(path),"ccitt-g4-truncated.pdf");
  OK(exr_fixed_open(path,&options,&d,&error)); CHECK(d);
  CHECK(exr_fixed_render(d,0,1,&render,&page,&error)==EXR_FORMAT && !page.pixels);
  exr_fixed_free(d);
  printf("%u native PDF CCITT checks passed\n",checks);
  return 0;
}
