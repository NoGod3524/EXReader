/* SPDX-License-Identifier: GPL-3.0-only */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error; static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static void rich(const char *dir) {
  const char *input="{\\rtf1\\ansi\\ansicpg1252\\uc1{\\colortbl;\\red18\\green52\\blue86;}{\\info ignored metadata}\\pard\\qc\\sb60 Normal {\\b bold} {\\i italic} {\\fs36\\cf1 color} normal {\\ul under}{\\strike strike}\\par\\pard\\li120\\fi60 Second\\line third}";
  exr_document *doc=NULL,*copy=NULL; exr_font *font=NULL; exr_layout *a=NULL,*b=NULL;
  exr_layout_config config=exr_layout_config_defaults(); exr_bitmap ba={0},bb={0};
  const exr_node *nodes; const exr_glyph *glyphs; char path[4096];
  size_t count,i,bold=0,italic=0,colored=0,under=0,strike=0,pa,pb,paragraphs=0,breaks=0; void *zip=NULL; size_t size;
  OK(exr_document_open_memory(EXR_RTF,input,strlen(input),&doc,&error));
  CHECK(!strcmp(exr_document_text(doc,NULL),"Normal bold italic color normal understrike\nSecond\nthird"));
  nodes=exr_document_nodes(doc,&count);
  for(i=0;i<count;i++) {
    if(nodes[i].kind==EXR_NODE_PARAGRAPH) paragraphs++;
    if(nodes[i].kind==EXR_NODE_BREAK) breaks++;
    if(nodes[i].name && !strcmp(nodes[i].name,"http://www.w3.org/1999/xhtml|u")) under++;
    if(nodes[i].name && !strcmp(nodes[i].name,"http://www.w3.org/1999/xhtml|s")) strike++;
  }
  CHECK(paragraphs==2 && breaks==1 && under==1 && strike==1);
  snprintf(path,sizeof(path),"%s/fonts/primary.ttf",dir); OK(exr_font_open(path,&font,&error));
  config.page=(exr_layout_options){300,180,8,16,1.2f,4};
  OK(exr_layout_create_ex(doc,font,&config,&a,&error)); glyphs=exr_layout_glyphs(a,&count);
  for(i=0;i<count;i++) {
    if(glyphs[i].codepoint==' ') continue;
    if(glyphs[i].flags&EXR_GLYPH_BOLD) bold++;
    if(glyphs[i].flags&EXR_GLYPH_ITALIC) italic++;
    if(glyphs[i].color==0x123456ff) { CHECK(glyphs[i].size==24); colored++; }
  }
  CHECK(bold==4 && italic==6 && colored==5);
  OK(exr_document_export_epub(doc,NULL,&zip,&size,&error)); OK(exr_document_open_memory(EXR_EPUB,zip,size,&copy,&error)); exr_free(zip);
  CHECK(!strcmp(exr_document_text(doc,NULL),exr_document_text(copy,NULL)));
  OK(exr_layout_create_ex(copy,font,&config,&b,&error)); exr_layout_pages(a,&pa); exr_layout_pages(b,&pb); CHECK(pa==pb);
  for(i=0;i<pa;i++) {
    OK(exr_render_page(a,NULL,i,&ba,&error)); OK(exr_render_page(b,NULL,i,&bb,&error));
    CHECK(ba.stride==bb.stride && ba.height==bb.height && !memcmp(ba.pixels,bb.pixels,(size_t)ba.stride*ba.height));
    exr_bitmap_free(&ba); exr_bitmap_free(&bb);
  }
  exr_layout_free(a); exr_layout_free(b); exr_font_free(font); exr_document_free(doc); exr_document_free(copy);
}
static void invalid(const char *rtf) {
  exr_document *doc=NULL; CHECK(exr_document_open_memory(EXR_RTF,rtf,strlen(rtf),&doc,&error)==EXR_FORMAT); CHECK(!doc);
}
int main(int argc,char **argv) {
  CHECK(argc==2); rich(argv[1]);
  invalid("{\\rtf1{\\colortbl;\\red256\\green0\\blue0;}\\cf1 bad}");
  invalid("{\\rtf1\\cf1 missing color}"); invalid("{\\rtf1\\fs0 invalid size}");
  printf("%u rich RTF checks passed\n",checks); return 0;
}
