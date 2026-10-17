/* SPDX-License-Identifier: GPL-3.0-only */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error; static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static exr_font *open_font(const char *dir,const char *name) {
  char path[4096]; FILE *f; long n; unsigned char *bytes; exr_font_input input={0}; exr_font *font=NULL;
  snprintf(path,sizeof(path),"%s/fonts/%s",dir,name); f=fopen(path,"rb"); CHECK(f && !fseek(f,0,SEEK_END)); n=ftell(f); CHECK(n>0); rewind(f);
  bytes=malloc((size_t)n); CHECK(bytes && fread(bytes,1,(size_t)n,f)==(size_t)n); fclose(f); input.data=bytes; input.size=(size_t)n;
  OK(exr_font_create_glyphs(&input,1,&font,&error)); memset(bytes,0,(size_t)n); free(bytes); return font;
}
static int cancel(void *ctx) { (void)ctx; return 1; }
int main(int argc,char **argv) {
  exr_font *font; exr_path_segment *path=NULL,*again=NULL; size_t count,n,i; exr_canvas *canvas=NULL; exr_canvas_config config={0};
  const char *names[]={"pdf-names.ttf","pdf-unicode.ttf","pdf-cubic.otf","glyph-only.ttf"};
  CHECK(argc==2);
  for(i=0;i<sizeof(names)/sizeof(*names);i++) {
    exr_control control={0}; font=open_font(argv[1],names[i]);
    OK(exr_font_glyph_outline(font,0,2,&path,&count,NULL,&error)); CHECK(path && count>=5);
    if(i<3) CHECK(path[0].verb==EXR_PATH_MOVE && path[0].points[0].x==500 && path[0].points[0].y==0);
    OK(exr_font_glyph_outline(font,0,2,&again,&n,NULL,&error)); CHECK(n==count);
    { size_t j,k; for(j=0;j<n;j++) { CHECK(path[j].verb==again[j].verb); for(k=0;k<3;k++) CHECK(path[j].points[k].x==again[j].points[k].x && path[j].points[k].y==again[j].points[k].y); } }
    exr_free(again);
    control.cancelled=cancel; CHECK(exr_font_glyph_outline(font,0,2,&again,&n,&control,&error)==EXR_CANCELLED && !again && !n);
    CHECK(exr_font_glyph_outline(font,1,2,&again,&n,NULL,&error)==EXR_ARGUMENT && !again && !n);
    CHECK(exr_font_glyph_outline(font,0,999999,&again,&n,NULL,&error)==EXR_ARGUMENT && !again && !n);
    exr_font_free(font);
    if(i<3) {
      const double matrix[6]={.01,0,0,-.01,0,8}; const exr_bitmap *image;
      config.width=config.height=12; config.background=0xffffffff; OK(exr_canvas_create(&config,&canvas,&error));
      OK(exr_canvas_path(canvas,path,count,matrix,NULL,&error)); image=exr_canvas_bitmap(canvas);
      CHECK(image && image->pixels[6*image->stride+6*4]==0 && image->pixels[6*image->stride+1*4]==255); exr_canvas_free(canvas);
    }
    exr_free(path);
  }
  font=open_font(argv[1],"pdf-names.ttf");
  { exr_shape_options options=exr_shape_defaults(); exr_shaped_glyph *before=NULL,*after=NULL; size_t first,second;
    OK(exr_shape(font,0,"AQ",2,&options,&before,&first,&error)); OK(exr_font_glyph_outline(font,0,3,&path,&count,NULL,&error));
    for(i=0;i<count;i++) if(path[i].verb==EXR_PATH_QUAD) break; CHECK(i<count); exr_free(path);
    OK(exr_shape(font,0,"AQ",2,&options,&after,&second,&error)); CHECK(first==second);
    for(i=0;i<first;i++) CHECK(before[i].glyph==after[i].glyph && before[i].advance_x==after[i].advance_x && before[i].advance_y==after[i].advance_y && before[i].offset_x==after[i].offset_x && before[i].offset_y==after[i].offset_y);
    exr_free(after); after=NULL; options.font_size*=2;
    OK(exr_shape(font,0,"AQ",2,&options,&after,&second,&error)); CHECK(first==second);
    for(i=0;i<first;i++) CHECK(after[i].advance_x==2*before[i].advance_x);
    OK(exr_font_glyph_outline(font,0,3,&path,&count,NULL,&error));
    for(i=0;i<count;i++) if(path[i].verb==EXR_PATH_QUAD) break;
    CHECK(i<count && path[i].points[0].x==400 && path[i].points[0].y==1000); exr_free(path);
    exr_free(before); exr_free(after);
  }
  OK(exr_font_glyph_outline(font,0,4,&path,&count,NULL,&error)); CHECK(!path && !count); exr_font_free(font);
  CHECK(exr_font_glyph_outline(NULL,0,0,&path,&count,NULL,&error)==EXR_ARGUMENT && !path && !count);
  printf("%u native public font path checks passed\n",checks); return 0;
}
