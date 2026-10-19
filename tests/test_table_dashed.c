/* SPDX-License-Identifier: MIT */
/* WP5: CSS border-style dashed and dotted reach the raster as real gaps. */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error; static unsigned checks; static const char *directory; static exr_font *font;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static exr_layout_config config(void) {
  exr_layout_config c=exr_layout_config_defaults(); c.page=(exr_layout_options){420,180,10,14,1.2f,0}; return c;
}
static exr_layout *layout(const char *name) {
  char path[4096]; exr_document *d=NULL; exr_layout *l=NULL; exr_layout_config c=config();
  snprintf(path,sizeof(path),"%s/%s.epub",directory,name);
  OK(exr_document_open(path,&d,&error));
  OK(exr_layout_create_ex(d,font,&c,&l,&error));
  exr_document_free(d);
  return l;
}
/* The longest run of border-coloured pixels found in any single row. */
static unsigned border_run_row(const exr_bitmap *image,int row) {
  unsigned x,count=0;
  for(x=0;x<image->width;x++) {
    const unsigned char *p=image->pixels+(size_t)row*image->stride+x*4;
    if(p[2]>200 && p[0]<60 && p[1]<60) count++;
  }
  return count;
}
static unsigned border_run(const exr_bitmap *image) {
  unsigned best=0,x; int y;
  for(y=0;y<(int)image->height;y++) {
    unsigned count=0;
    for(x=0;x<image->width;x++) {
      const unsigned char *p=image->pixels+(size_t)y*image->stride+x*4;
      if(p[2]>200 && p[0]<60 && p[1]<60) count++;
    }
    if(count>best) best=count;
  }
  return best;
}
int main(int argc,char **argv) {
  exr_layout *l; exr_bitmap image={0}; unsigned solid,dashed,dotted;
  CHECK(argc==2); directory=argv[1];
  { char path[4096]; snprintf(path,sizeof(path),"%s/fonts/primary.ttf",directory); OK(exr_font_open(path,&font,&error)); }
  l=layout("table-border-solid"); OK(exr_render_page_color(l,NULL,0,&image,&error));
  solid=border_run(&image); exr_bitmap_free(&image); exr_layout_free(l);
  l=layout("table-border-dashed"); OK(exr_render_page_color(l,NULL,0,&image,&error));
  dashed=border_run(&image); exr_bitmap_free(&image); exr_layout_free(l);
  l=layout("table-border-dotted"); OK(exr_render_page_color(l,NULL,0,&image,&error));
  dotted=border_run(&image); exr_bitmap_free(&image); exr_layout_free(l);
  /* Solid covers the whole span; dashed and dotted leave gaps, dotted the most. */
  CHECK(solid>=90 && dashed>10 && dashed<solid-10);
  CHECK(dotted>5 && dotted<dashed);
  { /* A double border is two thin rules with a gap between them: the row in the
       middle of the border leaves the border colour. */
    int y,top=-1;
    l=layout("table-border-double"); OK(exr_render_page_color(l,NULL,0,&image,&error));
    for(y=0;y+2<(int)image.height;y++) { if(border_run_row(&image,y)>=90) { top=y; break; } }
    CHECK(top>=0);
    CHECK(border_run_row(&image,top)>=90);
    CHECK(border_run_row(&image,top+1)<=4); /* only the two vertical rules */
    CHECK(border_run_row(&image,top+2)>=90);
    exr_bitmap_free(&image); exr_layout_free(l);
  }
  { /* Block borders use the raster path; a 6px double border is 2px line, 2px gap,
       2px line, so the third row inside the border is the gap. */
    int y,top=-1;
    l=layout("block-border-double"); OK(exr_render_page_color(l,NULL,0,&image,&error));
    for(y=0;y+4<(int)image.height;y++) if(border_run_row(&image,y)>=90) { top=y; break; }
    CHECK(top>=0);
    CHECK(border_run_row(&image,top)>=90);
    { unsigned gap=border_run_row(&image,top+2);
      if(gap>=20) fprintf(stderr,"gap row count=%u\n",gap);
      CHECK(gap<20); }
    CHECK(border_run_row(&image,top+4)>=90);
    exr_bitmap_free(&image); exr_layout_free(l);
  }
  exr_font_free(font);
  printf("%u native table border-style checks passed (solid %u, dashed %u, dotted %u)\n",checks,solid,dashed,dotted);
  return 0;
}
