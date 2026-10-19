/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "fixtures/indic/reference.h"
static exr_error error;
static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static int near(float a,float b) { return isfinite(a) && fabsf(a-b)<.016f; }
static exr_font *opened(const char *directory,const char *name) {
  char path[4096]; exr_font *font=NULL; snprintf(path,sizeof(path),"%s/%s",directory,name);
  OK(exr_font_open(path,&font,&error)); return font;
}
static void references(const char *directory) {
  size_t k,i,j;
  for(k=0;k<sizeof(reference)/sizeof(*reference);k++) {
    const indic_reference *r=&reference[k]; exr_font *font=opened(directory,r->font);
    exr_shape_options options=exr_shape_defaults(); exr_shaped_glyph *g=NULL; size_t n=0,previous=0;
    options.font_size=100; options.direction=EXR_DIRECTION_LTR;
    OK(exr_shape(font,0,r->text,strlen(r->text),&options,&g,&n,&error));
    for(i=0,j=0;i<n;i++) {
      CHECK(g[i].start<g[i].end && g[i].end<=strlen(r->text) && g[i].start>=previous); previous=g[i].start;
      if(g[i].flags&EXR_GLYPH_HIDDEN) continue;
      CHECK(j<r->count);
      if(g[i].glyph!=r->glyphs[j].glyph) fprintf(stderr,"reference %zu glyph %zu: got %u want %u\n",k,j,g[i].glyph,r->glyphs[j].glyph);
      CHECK(g[i].glyph==r->glyphs[j].glyph && near(g[i].advance_x,r->glyphs[j].ax) && near(g[i].advance_y,r->glyphs[j].ay) && near(g[i].offset_x,r->glyphs[j].x) && near(g[i].offset_y,r->glyphs[j].y)); j++;
    }
    CHECK(j==r->count); exr_free(g); exr_font_free(font);
  }
}
static int cancel(void *context) { unsigned *calls=context; return ++*calls>4; }
static void controls(const char *directory) {
  exr_font *font=opened(directory,"dev2.ttf"); exr_shape_options o=exr_shape_defaults();
  exr_shaped_glyph *g=(void *)(uintptr_t)1; size_t n=99,i; unsigned calls=0;
  char *long_text=malloc(60001); CHECK(long_text);
  for(i=0;i<20000;i++) memcpy(long_text+3*i,"\xe0\xa4\xbf",3); long_text[60000]=0;
  o.control.cancelled=cancel; o.control.context=&calls;
  CHECK(exr_shape(font,0,long_text,60000,&o,&g,&n,&error)==EXR_CANCELLED && !g && !n && calls>4);
  o=exr_shape_defaults(); g=(void *)(uintptr_t)1; n=99;
  CHECK(exr_shape(font,0,"\xff",1,&o,&g,&n,&error)==EXR_ENCODING && !g && !n);
  free(long_text); exr_font_free(font);
}
static void layout(const char *directory) {
  exr_font *font=opened(directory,"dev2.ttf"); exr_document *doc=NULL; exr_pager *pager=NULL; exr_layout *page=NULL;
  char text[4096]; size_t at=0,i,size,pages=0; exr_layout_config config=exr_layout_config_defaults();
  exr_node_input nodes[]={{EXR_NODE_DOCUMENT,SIZE_MAX,NULL,NULL,NULL,0},{EXR_NODE_CHAPTER,0,NULL,NULL,NULL,0},{EXR_NODE_PARAGRAPH,1,"p",NULL,NULL,0},{EXR_NODE_TEXT,2,NULL,text,NULL,0}};
  exr_chapter_input chapter={"main","main",1,1}; exr_document_input input={"Devanagari",nodes,4,&chapter,1,NULL,0};
  for(i=0;i<100;i++) { const char word[]="\xe0\xa4\xb0\xe0\xa5\x8d\xe0\xa4\x95\xe0\xa4\xbf "; memcpy(text+at,word,sizeof(word)-1); at+=sizeof(word)-1; } text[at]=0;
  OK(exr_document_create(&input,&doc,&error)); exr_document_text(doc,&size);
  config.page.width=100; config.page.height=140; config.page.margin=10; config.page.font_size=20;
  OK(exr_pager_create(doc,font,&config,&pager,&error));
  for(;;) {
    size_t n; const exr_glyph *g; exr_bitmap bitmap={0};
    OK(exr_pager_next(pager,&page,&error)); if(!page) break; pages++;
    g=exr_layout_glyphs(page,&n); CHECK(n);
    for(i=0;i<n;i++) { CHECK(g[i].start<g[i].end && g[i].end<=size && g[i].cluster_start<=g[i].start && g[i].cluster_end>=g[i].end); CHECK(!(g[i].flags&EXR_GLYPH_MISSING)); }
    OK(exr_render_page(page,font,0,&bitmap,&error)); CHECK(bitmap.width==100 && bitmap.height==140); exr_bitmap_free(&bitmap); exr_layout_free(page); page=NULL;
  }
  CHECK(pages>1); exr_pager_free(pager); exr_document_free(doc); exr_font_free(font);
}
int main(int argc,char **argv) { CHECK(argc==2); references(argv[1]); controls(argv[1]); layout(argv[1]); printf("%u native Indic oracle, source, cancellation and pagination checks passed\n",checks); return 0; }
