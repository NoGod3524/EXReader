/* SPDX-License-Identifier: GPL-3.0-only */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
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
static void fallback(const char *directory,const char *color_file) {
  exr_font_input inputs[2]={input_font(directory,"primary.ttf"),input_font(directory,color_file)}; exr_font *font=NULL;
  exr_document *doc=NULL; exr_layout *layout=NULL; exr_layout_config config=exr_layout_config_defaults(); exr_bitmap image={0}; const exr_glyph *glyphs; size_t n,i,red=0,blue=0,green=0;
  OK(exr_font_create(inputs,2,&font,&error)); free((void *)inputs[0].data); free((void *)inputs[1].data);
  OK(exr_document_open_memory(EXR_TXT,"\xf0\x9f\x98\x80",4,&doc,&error)); config.page=(exr_layout_options){200,200,0,100,1,0};
  OK(exr_layout_create_ex(doc,font,&config,&layout,&error)); glyphs=exr_layout_glyphs(layout,&n);
  CHECK(n==1 && glyphs[0].font_index==1 && glyphs[0].glyph==2 && glyphs[0].cluster_start==0 && glyphs[0].cluster_end==4 && !(glyphs[0].flags&EXR_GLYPH_MISSING) && fabsf(glyphs[0].advance-90)<.01f);
  exr_font_free(font); exr_document_free(doc); OK(exr_render_page_color(layout,NULL,0,&image,&error));
  for(i=0;i<(size_t)image.width*image.height;i++) { const unsigned char *p=image.pixels+i*4; if(p[0]==255 && !p[1] && !p[2]) red++; if(!p[0] && p[1]==255 && !p[2]) green++; if(p[2]==255 && p[0]==127 && p[1]==127) blue++; }
  CHECK((!strcmp(color_file,"bitmap.ttf") ? green>100 : red>100) && blue>100); exr_bitmap_free(&image); exr_layout_free(layout);
}
static void bitmap_queries(exr_font *font) {
  const float sizes[]={5,10,15,100},scales[]={.5f,1,.75f,5},left[]={.5f,1,1.5f,10},top[]={-3,-6,-9,-60};
  const unsigned widths[]={8,8,16,16}; exr_glyph_image image={0}; size_t i;
  for(i=0;i<4;i++) {
    OK(exr_font_glyph_image(font,0,2,sizes[i],&image,NULL,&error)); CHECK(image.bitmap.width==widths[i] && image.bitmap.height==widths[i] && image.bitmap.channels==4);
    CHECK(fabsf(image.scale-scales[i])<1e-5f && fabsf(image.left-left[i])<1e-5f && fabsf(image.top-top[i])<1e-5f && !image.flags);
    pixel(&image.bitmap,1,1,i<2 ? 0xff0000ff : 0x00ff00ff); exr_bitmap_free(&image.bitmap);
  }
  OK(exr_font_glyph_image(font,0,3,100,&image,NULL,&error)); CHECK(image.bitmap.width==8 && image.scale==10); exr_bitmap_free(&image.bitmap);
  OK(exr_font_glyph_image(font,0,4,5,&image,NULL,&error)); CHECK(image.bitmap.width==16 && image.scale==.25f); exr_bitmap_free(&image.bitmap);
  OK(exr_font_glyph_image(font,0,5,100,&image,NULL,&error)); CHECK(image.left==40 && image.top==-90); exr_bitmap_free(&image.bitmap);
  for(i=7;i<=10;i+=3) { OK(exr_font_glyph_image(font,0,(uint32_t)i,100,&image,NULL,&error)); CHECK(image.bitmap.width==16 && image.left==10 && image.top==-60); exr_bitmap_free(&image.bitmap); }
  OK(exr_font_glyph_image(font,0,6,100,&image,NULL,&error)); CHECK(!image.bitmap.pixels && !image.left && !image.top && !image.scale && !image.flags);
  CHECK(exr_font_glyph_image(font,0,9,100,&image,NULL,&error)==EXR_FONT && !image.bitmap.pixels && !image.flags);
  OK(exr_font_glyph_image(font,0,0,100,&image,NULL,&error)); CHECK(image.bitmap.pixels && image.bitmap.channels==4); exr_bitmap_free(&image.bitmap);
  CHECK(exr_font_glyph_image(font,0,2,0,&image,NULL,&error)==EXR_ARGUMENT && !image.bitmap.pixels);
  CHECK(exr_font_glyph_image(font,0,2,NAN,&image,NULL,&error)==EXR_ARGUMENT && !image.bitmap.pixels);
  CHECK(exr_font_glyph_image(font,0,2,4097,&image,NULL,&error)==EXR_ARGUMENT && !image.bitmap.pixels);
  CHECK(exr_font_glyph_image(font,1,2,100,&image,NULL,&error)==EXR_ARGUMENT && !image.bitmap.pixels);
  CHECK(exr_font_glyph_image(font,0,999,100,&image,NULL,&error)==EXR_ARGUMENT && !image.bitmap.pixels);
  for(i=0;i<=6;i+=3) { cancel_state s={0,(unsigned)i}; exr_control control={0}; control.context=&s; control.cancelled=cancelled;
    CHECK(exr_font_glyph_image(font,0,2,100,&image,&control,&error)==EXR_CANCELLED && !image.bitmap.pixels && !image.flags); }
}
static unsigned u16(const unsigned char *p) { return (unsigned)p[0]<<8|p[1]; }
static uint32_t u32(const unsigned char *p) { return (uint32_t)u16(p)<<16|u16(p+2); }
static void put(unsigned char *p,uint32_t value,unsigned n) { unsigned i; for(i=0;i<n;i++) p[n-i-1]=(unsigned char)(value>>(i*8)); }
static size_t table_at(const exr_font_input *input,const char *name) {
  const unsigned char *p=input->data; unsigned i; for(i=0;i<u16(p+4);i++) if(!memcmp(p+12+i*16,name,4)) return u32(p+12+i*16+8); CHECK(0); return 0;
}
static size_t sbix_at(const exr_font_input *input) { return table_at(input,"sbix"); }
static void bitmap_bad(const char *directory) {
  size_t i;
  for(i=0;i<12;i++) {
    exr_font_input input=input_font(directory,"bitmap.ttf"); unsigned char *p=(void *)input.data; size_t at=sbix_at(&input),strike=at+u32(p+at+12),record=strike+u32(p+strike+4+2*4);
    exr_font *font=NULL; exr_glyph_image image={0}; uint32_t id=2; exr_status expected=EXR_FONT;
    switch(i) {
      case 0: put(p+at,2,2); break;
      case 1: put(p+at+2,0,2); break;
      case 2: put(p+at+4,257,4); expected=EXR_LIMIT; break;
      case 3: put(p+at+8,1,4); break;
      case 4: put(p+strike+4+2*4,UINT32_MAX,4); break;
      case 5: put(p+record+8,0,1); expected=EXR_FORMAT; break;
      case 6: memcpy(p+record+4,"tiff",4); expected=EXR_FORMAT; break;
      case 7: put(p+strike,0,2); break;
      case 8: id=7; record=strike+u32(p+strike+4+id*4); put(p+record+8,65535,2); break;
      case 9: id=7; record=strike+u32(p+strike+4+id*4); put(p+record+8,6,2); break;
      case 10: put(p+record+8+16,9000,4); expected=EXR_LIMIT; break;
      default: put(p+strike+4+3*4,u32(p+strike+4+2*4)+7,4); break;
    }
    OK(exr_font_create(&input,1,&font,&error)); free((void *)input.data);
    CHECK(exr_font_glyph_image(font,0,id,100,&image,NULL,&error)==expected && !image.bitmap.pixels && !image.flags); exr_font_free(font);
  }
}
static void bitmap_raster(const char *directory,const char *output) {
  exr_font *font=open_font(directory,"bitmap.ttf"); exr_glyph g=glyph(2,0xff00ffff,0); exr_layout *layout; exr_bitmap image={0},gray={0}; exr_glyph_image owned={0}; size_t i;
  bitmap_queries(font); layout=page(font,&g,1); OK(exr_render_page_color(layout,NULL,0,&image,&error));
  pixel(&image,35,60,0x00ff00ff); pixel(&image,85,60,0x7f7fffff); pixel(&image,15,25,0xffffffff);
  { char path[4096]; snprintf(path,sizeof(path),"%s/font-bitmap.png",output); OK(exr_bitmap_write_png(&image,path,&error)); }
  OK(exr_render_page(layout,NULL,0,&gray,&error)); for(i=0;i<(size_t)image.width*image.height;i++) { const unsigned char *p=image.pixels+i*4; unsigned luminance=(p[0]*77+p[1]*150+p[2]*29+128)>>8; CHECK(abs((int)luminance-gray.pixels[i])<=1); }
  exr_bitmap_free(&image); exr_bitmap_free(&gray); exr_layout_free(layout);
  g.color=0xff00ff80; layout=page(font,&g,1); OK(exr_render_page_color(layout,NULL,0,&image,&error)); pixel(&image,35,60,0x7fff7fff); pixel(&image,85,60,0xbfbfffff); exr_bitmap_free(&image); exr_layout_free(layout);
  g.flags=EXR_GLYPH_UNDERLINE|EXR_GLYPH_STRIKE; layout=page(font,&g,1); OK(exr_render_page_color(layout,NULL,0,&image,&error)); pixel(&image,15,112,0xff7fffff); exr_bitmap_free(&image); exr_layout_free(layout);
  g.color=0xff00ffff; g.flags=EXR_GLYPH_VERTICAL|EXR_GLYPH_SIDEWAYS; layout=page(font,&g,1); OK(exr_render_page_color(layout,NULL,0,&image,&error)); pixel(&image,30,125,0x00ff00ff); pixel(&image,30,175,0x7f7fffff); exr_bitmap_free(&image); exr_layout_free(layout);
  g.flags=0; g.clip_right=50; layout=page(font,&g,1); OK(exr_render_page_color(layout,NULL,0,&image,&error)); pixel(&image,85,60,0xffffffff); pixel(&image,35,60,0x00ff00ff); exr_bitmap_free(&image); exr_layout_free(layout);
  g.flags=EXR_GLYPH_VERTICAL; g.clip_left=50; g.clip_right=70; layout=page(font,&g,1); OK(exr_render_page_color(layout,NULL,0,&image,&error)); pixel(&image,35,60,0x00ff00ff); pixel(&image,35,45,0xffffffff); exr_bitmap_free(&image); exr_layout_free(layout);
  g=glyph(6,0xff00ffff,0); layout=page(font,&g,1); OK(exr_render_page_color(layout,NULL,0,&image,&error)); pixel(&image,15,25,0xff00ffff); exr_bitmap_free(&image); exr_layout_free(layout);
  g=glyph(9,0xff00ffff,0); layout=page(font,&g,1); CHECK(exr_render_page_color(layout,NULL,0,&image,&error)==EXR_FONT && !image.pixels); exr_layout_free(layout);
  { exr_glyph expensive[26];
    OK(exr_font_glyph_image(font,0,2,4096,&owned,NULL,&error)); exr_bitmap_free(&owned.bitmap);
    for(i=0;i<26;i++) { expensive[i]=glyph(2,0xff00ffff,0); expensive[i].size=4096; expensive[i].x=expensive[i].baseline=1000000; }
    layout=page(font,expensive,26); CHECK(exr_render_page_color(layout,NULL,0,&image,&error)==EXR_LIMIT && !image.pixels); exr_layout_free(layout);
  }
  OK(exr_font_glyph_image(font,0,2,100,&owned,NULL,&error)); exr_font_free(font); pixel(&owned.bitmap,1,1,0x00ff00ff); exr_bitmap_free(&owned.bitmap);
  { exr_font_input input=input_font(directory,"bitmap.ttf"); unsigned char *p=(void *)input.data; put(p+sbix_at(&input)+2,3,2); OK(exr_font_create(&input,1,&font,&error)); free((void *)input.data);
    g=glyph(2,0xff00ffff,0); layout=page(font,&g,1); OK(exr_render_page_color(layout,NULL,0,&image,&error)); pixel(&image,35,60,0xff00ffff); pixel(&image,95,110,0x7f7fffff);
    exr_bitmap_free(&image); exr_layout_free(layout); exr_font_free(font);
  }
  { exr_font_input input=input_font(directory,"bitmap.ttf"); unsigned char *p=(void *)input.data;
    size_t head=table_at(&input,"head"),loca=table_at(&input,"loca"),glyf=table_at(&input,"glyf"),count=u16(p+table_at(&input,"maxp")+4); int wide=u16(p+head+50)!=0;
    for(i=0;i<count;i++) { uint32_t start=wide ? u32(p+loca+i*4) : u16(p+loca+i*2)*2,end=wide ? u32(p+loca+(i+1)*4) : u16(p+loca+(i+1)*2)*2;
      if(start<end) put(p+glyf+start,0,2);
    }
    OK(exr_font_create(&input,1,&font,&error)); free((void *)input.data);
    OK(exr_font_glyph_image(font,0,5,100,&owned,NULL,&error)); CHECK(owned.left==10 && owned.top==-60); exr_bitmap_free(&owned.bitmap);
    g=glyph(2,0xff00ffff,0); layout=page(font,&g,1); exr_font_free(font); OK(exr_render_page_color(layout,NULL,0,&image,&error)); pixel(&image,35,60,0x00ff00ff); exr_bitmap_free(&image); exr_layout_free(layout);
  }
  { exr_font_input input=input_font(directory,"bitmap.ttf"); unsigned char *p=(void *)input.data; size_t at=sbix_at(&input);
    put(p+at+u32(p+at+8),1,2); put(p+at+u32(p+at+12),1,2); OK(exr_font_create(&input,1,&font,&error)); free((void *)input.data);
    CHECK(exr_font_glyph_image(font,0,2,4096,&owned,NULL,&error)==EXR_LIMIT && !owned.bitmap.pixels); exr_font_free(font);
  }
  bitmap_bad(directory);
}
int main(int argc,char **argv) {
  exr_font *font; exr_font_color_layer *owned=NULL; size_t n; CHECK(argc==3); font=open_font(argv[1],"color.ttf"); queries(font,argv[1]); raster(font,argv[2]);
  OK(exr_font_color_layers(font,0,2,1,0x00ff00ff,&owned,&n,NULL,&error)); exr_font_free(font);
  CHECK(n==3 && owned[0].color==0xffff00ff && owned[2].color==0x00ff00ff); exr_free(owned);
  fallback(argv[1],"color.ttf"); fallback(argv[1],"bitmap.ttf"); bitmap_raster(argv[1],argv[2]); printf("%u color-font palette, layers and raster checks passed\n",checks); return 0;
}
