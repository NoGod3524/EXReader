/* SPDX-License-Identifier: GPL-3.0-only */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error; static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static exr_document *document(const char *first,const char *second,int nested) {
  exr_attribute none={"style","text-decoration:none"};
  exr_node_input nodes[]={
    {EXR_NODE_DOCUMENT,SIZE_MAX,NULL,NULL,NULL,0},
    {EXR_NODE_CHAPTER,0,NULL,NULL,NULL,0},
    {EXR_NODE_PARAGRAPH,1,"http://www.w3.org/1999/xhtml|p",NULL,NULL,0},
    {EXR_NODE_ELEMENT,2,"http://www.w3.org/1999/xhtml|u",NULL,NULL,0},
    {EXR_NODE_ELEMENT,3,"http://www.w3.org/1999/xhtml|span",NULL,nested ? &none : NULL,nested ? 1 : 0},
    {EXR_NODE_TEXT,4,NULL,first,NULL,0},
    {EXR_NODE_ELEMENT,2,"http://www.w3.org/1999/xhtml|s",NULL,NULL,0},
    {EXR_NODE_TEXT,6,NULL,second,NULL,0}};
  exr_chapter_input chapter={"main","book.xhtml",1,1};
  exr_document_input input={"Decorations",nodes,8,&chapter,1,NULL,0}; exr_document *doc=NULL;
  OK(exr_document_create(&input,&doc,&error)); return doc;
}
static unsigned long ink(const exr_bitmap *b) {
  unsigned long result=0; size_t x,y;
  for(y=0;y<b->height;y++) for(x=0;x<b->width;x++) result+=255-b->pixels[y*b->stride+x];
  return result;
}
static void pixels(exr_font *font) {
  exr_document *doc=document("aa","aa",1); exr_layout *a=NULL,*b=NULL,*both=NULL;
  exr_layout_config c=exr_layout_config_defaults(); exr_bitmap pa={0},pb={0}; const exr_glyph *ga,*gb; size_t na,nb,i;
  c.page=(exr_layout_options){200,100,8,20,1.2f,0};
  OK(exr_layout_create_ex(doc,font,&c,&a,&error));
  ga=exr_layout_glyphs(a,&na); CHECK(na==4);
  for(i=0;i<na;i++) CHECK((ga[i].flags&(EXR_GLYPH_UNDERLINE|EXR_GLYPH_STRIKE))==(i<2 ? EXR_GLYPH_UNDERLINE : EXR_GLYPH_STRIKE));
  c.user_css="*{text-decoration-line:none}";
  OK(exr_layout_create_ex(doc,font,&c,&b,&error)); gb=exr_layout_glyphs(b,&nb); CHECK(na==nb);
  for(i=0;i<na;i++) {
    CHECK(!(gb[i].flags&(EXR_GLYPH_UNDERLINE|EXR_GLYPH_STRIKE)));
    CHECK(ga[i].glyph==gb[i].glyph && ga[i].x==gb[i].x && ga[i].baseline==gb[i].baseline && ga[i].advance==gb[i].advance);
  }
  c.user_css="p{text-decoration-line:underline line-through}";
  OK(exr_layout_create_ex(doc,font,&c,&both,&error));
  gb=exr_layout_glyphs(both,&nb); CHECK(nb==na);
  for(i=0;i<nb;i++) CHECK((gb[i].flags&(EXR_GLYPH_UNDERLINE|EXR_GLYPH_STRIKE))==(EXR_GLYPH_UNDERLINE|EXR_GLYPH_STRIKE));
  OK(exr_render_page(a,NULL,0,&pa,&error)); OK(exr_render_page(b,NULL,0,&pb,&error)); CHECK(ink(&pa)>ink(&pb));
  exr_bitmap_free(&pa); exr_bitmap_free(&pb); exr_layout_free(a); exr_layout_free(b); exr_layout_free(both); exr_document_free(doc);
}
static void shaping(exr_font *font) {
  exr_document *doc=document("f","i",0); exr_layout *a=NULL,*b=NULL; exr_layout_config c=exr_layout_config_defaults();
  const exr_glyph *g; size_t n;
  c.page=(exr_layout_options){200,100,8,20,1.2f,0};
  OK(exr_layout_create_ex(doc,font,&c,&a,&error)); g=exr_layout_glyphs(a,&n); CHECK(n==2);
  CHECK((g[0].flags&EXR_GLYPH_UNDERLINE) && (g[1].flags&EXR_GLYPH_STRIKE));
  CHECK((g[0].flags&EXR_GLYPH_SHAPED) && (g[1].flags&EXR_GLYPH_SHAPED));
  c.user_css="*{text-decoration:none}";
  OK(exr_layout_create_ex(doc,font,&c,&b,&error)); g=exr_layout_glyphs(b,&n); CHECK(n==1 && !(g[0].flags&(EXR_GLYPH_UNDERLINE|EXR_GLYPH_STRIKE)));
  exr_layout_free(a); exr_layout_free(b); exr_document_free(doc);
}
static void joining(exr_font *font) {
  exr_document *doc=document("\xd8\xa8\xd8\xa8","\xd8\xa8",0); exr_layout *a=NULL,*b=NULL;
  exr_layout_config c=exr_layout_config_defaults(); const exr_glyph *ga,*gb; size_t na,nb,i;
  c.page=(exr_layout_options){200,100,8,20,1.2f,0};
  OK(exr_layout_create_ex(doc,font,&c,&a,&error)); c.user_css="*{text-decoration:none}";
  OK(exr_layout_create_ex(doc,font,&c,&b,&error)); ga=exr_layout_glyphs(a,&na); gb=exr_layout_glyphs(b,&nb);
  CHECK(na==nb && na==3);
  for(i=0;i<na;i++) { CHECK(ga[i].glyph==gb[i].glyph); CHECK(ga[i].flags&(EXR_GLYPH_UNDERLINE|EXR_GLYPH_STRIKE)); }
  exr_layout_free(a); exr_layout_free(b); exr_document_free(doc);
}
static void pages(exr_font *font) {
  char text[1001]; size_t i,n,count; exr_document *doc; exr_layout *all=NULL; const exr_layout *page=NULL;
  exr_pager *pager=NULL; exr_layout_config c=exr_layout_config_defaults(); exr_bitmap a={0},b={0}; const exr_glyph *glyphs;
  for(i=0;i<1000;i++) text[i]=i%5==4 ? ' ' : 'a'; text[1000]=0;
  doc=document(text,text,0); c.page=(exr_layout_options){120,80,8,20,1.2f,0};
  OK(exr_layout_create_ex(doc,font,&c,&all,&error)); exr_layout_pages(all,&count); CHECK(count>4);
  OK(exr_pager_create(doc,font,&c,&pager,&error)); OK(exr_pager_set_cache(pager,1,0,&error));
  OK(exr_pager_set_checkpoints(pager,4,1024*1024,2,&error));
  for(i=0;i<count+2;i++) {
    size_t target=i<count ? i : i==count ? 0 : count-1;
    OK(exr_pager_get(pager,target,&page,&error)); glyphs=exr_layout_glyphs(page,&n); CHECK(n>0);
    CHECK(glyphs[0].flags&(EXR_GLYPH_UNDERLINE|EXR_GLYPH_STRIKE));
    OK(exr_render_page(all,NULL,target,&a,&error)); OK(exr_render_page(page,NULL,0,&b,&error));
    CHECK(a.stride==b.stride && a.height==b.height && !memcmp(a.pixels,b.pixels,(size_t)a.stride*a.height));
    exr_bitmap_free(&a); exr_bitmap_free(&b);
  }
  exr_pager_free(pager); exr_layout_free(all); exr_document_free(doc);
}
int main(int argc,char **argv) {
  char path[4096]; exr_font *font=NULL;
  CHECK(argc==2); snprintf(path,sizeof(path),"%s/fonts/primary.ttf",argv[1]); OK(exr_font_open(path,&font,&error));
  pixels(font); pages(font); exr_font_free(font);
  snprintf(path,sizeof(path),"%s/shaping/shaping.ttf",argv[1]); OK(exr_font_open(path,&font,&error));
  pixels(font); shaping(font); joining(font); exr_font_free(font);
  printf("%u text-decoration checks passed\n",checks); return 0;
}
