/* SPDX-License-Identifier: GPL-3.0-only */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error; static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"color font line %d: %s (%d %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static exr_font *open_font(const char *directory,const char *name) {
  char path[4096]; exr_font *font=NULL; snprintf(path,sizeof(path),"%s/%s",directory,name); OK(exr_font_open(path,&font,&error)); return font;
}
static exr_glyph glyph(uint32_t id,uint32_t color,unsigned flags) {
  exr_glyph g={0}; g.end=g.cluster_end=1; g.codepoint='A'; g.glyph=id; g.x=10; g.baseline=100;
  g.advance=90; g.size=g.line_height=100; g.node=SIZE_MAX; g.color=color; g.flags=flags; g.clip_right=200; return g;
}
static exr_layout *page(exr_font *font,exr_glyph *glyphs,size_t n) {
  exr_document *doc=NULL; exr_layout *layout=NULL; exr_layout_config config=exr_layout_config_defaults();
  exr_positioned_page p={0}; exr_positioned_input in={0}; exr_line line={0}; exr_paint *paints=calloc(n,sizeof(*paints)); size_t i;
  CHECK(paints); OK(exr_document_open_memory(EXR_TXT,"A",1,&doc,&error));
  config.page=(exr_layout_options){200,200,0,100,1,0}; p.width=p.height=200; p.content.end=1; p.content.line_count=1; p.paint_count=n;
  line.end=1; line.glyph_count=n; line.x=line.y=10; line.width=90; line.height=100;
  for(i=0;i<n;i++) paints[i]=(exr_paint){EXR_PAINT_GLYPH,0,i};
  in.struct_size=sizeof(in); in.pages=&p; in.page_count=1; in.glyphs=glyphs; in.glyph_count=n;
  in.lines=&line; in.line_count=1; in.paints=paints; in.paint_count=n;
  OK(exr_layout_create_positioned(doc,font,&in,&config,&layout,&error)); exr_document_free(doc); free(paints); return layout;
}
static void pixel(const exr_bitmap *bitmap,unsigned x,unsigned y,uint32_t rgba) {
  const unsigned char *p=bitmap->pixels+y*bitmap->stride+x*4; unsigned i;
  for(i=0;i<4;i++) CHECK(p[i]==((rgba>>(24-8*i))&255));
}
typedef struct { unsigned calls,after; } cancel_state;
static int cancelled(void *context) { cancel_state *s=context; return ++s->calls>s->after; }
static void queries(exr_font *font,const char *directory) {
  size_t palettes=99,entries=99,n=99; exr_font_color_layer *layers=(void *)1,*owned=NULL; exr_font *plain=open_font(directory,"primary.ttf");
  OK(exr_font_color_palettes(font,0,&palettes,&entries,&error)); CHECK(palettes==2 && entries==3);
  OK(exr_font_color_palettes(plain,0,&palettes,&entries,&error)); CHECK(!palettes && !entries);
  CHECK(exr_font_color_palettes(font,1,&palettes,&entries,&error)==EXR_ARGUMENT && !palettes && !entries);
  OK(exr_font_color_layers(font,0,2,0,0x00ff00ff,&layers,&n,NULL,&error)); CHECK(n==3);
  CHECK(layers[0].glyph==3 && layers[0].color==0xff0000ff && layers[1].glyph==4 && layers[1].color==0x0000ff80 && layers[2].glyph==5 && layers[2].color==0x00ff00ff); exr_free(layers);
  OK(exr_font_color_layers(font,0,2,1,0x00ff0080,&owned,&n,NULL,&error)); CHECK(n==3);
  CHECK(owned[0].color==0xffff0080 && owned[1].color==0x00ffff20 && owned[2].color==0x00ff0080);
  OK(exr_font_color_layers(font,0,2,0,0x00ff0000,&layers,&n,NULL,&error)); CHECK(n==3 && !(layers[0].color&255) && !(layers[1].color&255) && !(layers[2].color&255)); exr_free(layers);
  CHECK(owned[0].color==0xffff0080 && owned[1].color==0x00ffff20); exr_free(owned);
  OK(exr_font_color_layers(font,0,6,0,0,&layers,&n,NULL,&error)); CHECK(!layers && !n);
  OK(exr_font_color_layers(plain,0,0,0,0,&layers,&n,NULL,&error)); CHECK(!layers && !n);
  CHECK(exr_font_color_layers(font,0,2,2,0,&layers,&n,NULL,&error)==EXR_ARGUMENT && !layers && !n);
  CHECK(exr_font_color_layers(plain,0,0,1,0,&layers,&n,NULL,&error)==EXR_ARGUMENT && !layers && !n);
  CHECK(exr_font_color_layers(font,0,999,0,0,&layers,&n,NULL,&error)==EXR_ARGUMENT && !layers && !n);
  CHECK(exr_font_color_layers(font,0,7,0,0,&layers,&n,NULL,&error)==EXR_LIMIT && !layers && !n);
  OK(exr_font_color_layers(font,0,10,0,0x123456ff,&layers,&n,NULL,&error)); CHECK(n==256 && layers[255].color==0x123456ff); exr_free(layers);
  { cancel_state s={0,0}; exr_control control={0}; control.context=&s; control.cancelled=cancelled;
    CHECK(exr_font_color_layers(font,0,2,0,0,&layers,&n,&control,&error)==EXR_CANCELLED && !layers && !n);
    s=(cancel_state){0,1}; CHECK(exr_font_color_layers(font,0,2,0,0,&layers,&n,&control,&error)==EXR_CANCELLED && !layers && !n);
  }
  exr_font_free(plain);
}
static void raster(exr_font *font,const char *directory) {
  exr_glyph g=glyph(2,0x00ff00ff,0); exr_layout *layout=page(font,&g,1); exr_bitmap image={0},gray={0}; size_t n,i;
  { exr_font_color_layer *layers=NULL; OK(exr_font_color_layers(font,0,2,1,g.color,&layers,&n,NULL,&error)); exr_free(layers); }
  OK(exr_render_page_color(layout,NULL,0,&image,&error));
  pixel(&image,15,85,0xff0000ff); pixel(&image,35,65,0x7f0080ff); pixel(&image,45,60,0x00ff00ff); pixel(&image,85,25,0x7f7fffff); pixel(&image,100,5,0xffffffff);
  OK(exr_render_page(layout,NULL,0,&gray,&error));
  for(i=0;i<(size_t)image.width*image.height;i++) {
    const unsigned char *p=image.pixels+i*4; unsigned luminance=(p[0]*77+p[1]*150+p[2]*29+128)>>8;
    CHECK(abs((int)luminance-gray.pixels[i])<=1);
  }
  { char path[4096]; snprintf(path,sizeof(path),"%s/font-color.png",directory); OK(exr_bitmap_write_png(&image,path,&error)); }
  exr_bitmap_free(&image); exr_bitmap_free(&gray); exr_layout_free(layout);
  g.color=0x00ff0080;
  { exr_font_color_layer *layers=NULL; exr_glyph direct[3]; exr_layout *expanded;
    OK(exr_font_color_layers(font,0,2,0,g.color,&layers,&n,NULL,&error)); CHECK(n==3);
    for(i=0;i<n;i++) { direct[i]=g; direct[i].glyph=layers[i].glyph; direct[i].color=layers[i].color; }
    expanded=page(font,direct,n); exr_free(layers); layout=page(font,&g,1);
    OK(exr_render_page_color(layout,NULL,0,&image,&error)); OK(exr_render_page_color(expanded,NULL,0,&gray,&error));
    CHECK(!memcmp(image.pixels,gray.pixels,(size_t)image.stride*image.height));
    exr_bitmap_free(&image); exr_bitmap_free(&gray); exr_layout_free(expanded); exr_layout_free(layout);
  }
  g.flags=EXR_GLYPH_UNDERLINE|EXR_GLYPH_STRIKE; layout=page(font,&g,1); OK(exr_render_page_color(layout,NULL,0,&image,&error));
  pixel(&image,15,112,0x7fff7fff); exr_bitmap_free(&image); exr_layout_free(layout);
  g.color=0x00ff00ff; g.flags=EXR_GLYPH_VERTICAL|EXR_GLYPH_SIDEWAYS; layout=page(font,&g,1);
  OK(exr_render_page_color(layout,NULL,0,&image,&error)); pixel(&image,15,155,0xff0000ff); pixel(&image,35,145,0x7f0080ff); pixel(&image,45,140,0x00ff00ff); pixel(&image,85,125,0x7f7fffff);
  exr_bitmap_free(&image); exr_layout_free(layout);
  g.flags=EXR_GLYPH_VERTICAL; g.clip_left=50; g.clip_right=70; layout=page(font,&g,1);
  OK(exr_render_page_color(layout,NULL,0,&image,&error)); pixel(&image,85,60,0x7f7fffff); pixel(&image,85,25,0xffffffff); exr_bitmap_free(&image); exr_layout_free(layout);
  g=glyph(10,0x00ff00ff,0); layout=page(font,&g,1); OK(exr_render_page_color(layout,NULL,0,&image,&error)); pixel(&image,45,60,0x00ff00ff); exr_bitmap_free(&image); exr_layout_free(layout);
  g=glyph(7,0x00ff00ff,0); layout=page(font,&g,1); CHECK(exr_render_page_color(layout,NULL,0,&image,&error)==EXR_LIMIT && !image.pixels); exr_layout_free(layout);
  g=glyph(9,0xff0000ff,0); g.size=300; layout=page(font,&g,1); CHECK(exr_render_page_color(layout,NULL,0,&image,&error)==EXR_LIMIT && !image.pixels); exr_layout_free(layout);
  g=glyph(2,0x00ff00ff,0); layout=page(font,&g,1);
  { cancel_state s={0,6}; exr_control control={0}; control.context=&s; control.cancelled=cancelled;
    CHECK(exr_render_page_ex(layout,NULL,0,4,&control,&image,&error)==EXR_CANCELLED && !image.pixels && s.calls>6); }
  exr_layout_free(layout);
  { exr_glyph expensive[24];
    for(i=0;i<24;i++) { expensive[i]=glyph(2,0x00ff00ff,0); expensive[i].size=4096; expensive[i].x=expensive[i].baseline=1000000; }
    layout=page(font,expensive,24); CHECK(exr_render_page_color(layout,NULL,0,&image,&error)==EXR_LIMIT && !image.pixels); exr_layout_free(layout);
  }
}
static exr_font_input input_font(const char *directory,const char *name) {
  char path[4096]; FILE *f; long size; exr_font_input input={0}; void *data;
  snprintf(path,sizeof(path),"%s/%s",directory,name); f=fopen(path,"rb"); CHECK(f && !fseek(f,0,SEEK_END)); size=ftell(f); CHECK(size>0); rewind(f);
  data=malloc((size_t)size); CHECK(data && fread(data,1,(size_t)size,f)==(size_t)size && !fclose(f)); input.data=data; input.size=(size_t)size; return input;
}
static void fallback(const char *directory) {
  exr_font_input inputs[2]={input_font(directory,"primary.ttf"),input_font(directory,"color.ttf")}; exr_font *font=NULL;
  exr_document *doc=NULL; exr_layout *layout=NULL; exr_layout_config config=exr_layout_config_defaults(); exr_bitmap image={0}; const exr_glyph *glyphs; size_t n,i,red=0,blue=0;
  OK(exr_font_create(inputs,2,&font,&error)); free((void *)inputs[0].data); free((void *)inputs[1].data);
  OK(exr_document_open_memory(EXR_TXT,"\xf0\x9f\x98\x80",4,&doc,&error)); config.page=(exr_layout_options){200,200,0,100,1,0};
  OK(exr_layout_create_ex(doc,font,&config,&layout,&error)); glyphs=exr_layout_glyphs(layout,&n);
  CHECK(n==1 && glyphs[0].font_index==1 && glyphs[0].glyph==2 && glyphs[0].cluster_start==0 && glyphs[0].cluster_end==4 && !(glyphs[0].flags&EXR_GLYPH_MISSING));
  exr_font_free(font); exr_document_free(doc); OK(exr_render_page_color(layout,NULL,0,&image,&error));
  for(i=0;i<(size_t)image.width*image.height;i++) { const unsigned char *p=image.pixels+i*4; if(p[0]==255 && !p[1] && !p[2]) red++; if(p[2]==255 && p[0]==127 && p[1]==127) blue++; }
  CHECK(red>100 && blue>100); exr_bitmap_free(&image); exr_layout_free(layout);
}
int main(int argc,char **argv) {
  exr_font *font; exr_font_color_layer *owned=NULL; size_t n; CHECK(argc==3); font=open_font(argv[1],"color.ttf"); queries(font,argv[1]); raster(font,argv[2]);
  OK(exr_font_color_layers(font,0,2,1,0x00ff00ff,&owned,&n,NULL,&error)); exr_font_free(font);
  CHECK(n==3 && owned[0].color==0xffff00ff && owned[2].color==0x00ff00ff); exr_free(owned);
  fallback(argv[1]); printf("%u color-font palette, layers and raster checks passed\n",checks); return 0;
}
