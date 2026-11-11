/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static exr_error error;
static unsigned checks;
static exr_font *font;
static const char *fixtures;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%s)\n",__LINE__,#x,error.message);exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static int near(float a,float b) { return fabsf(a-b)<.1f; }
static exr_layout *layout(const char *name,exr_document **doc) {
  exr_layout *out=NULL;exr_layout_config config=exr_layout_config_defaults();
  exr_publication *p=NULL;char path[4096];
  config.page=(exr_layout_options){320,400,20,20,1.3f,0};
  snprintf(path,sizeof(path),"%s/native-%s.epub",fixtures,name);
  OK(exr_publication_open(path,&p,&error));
  OK(exr_publication_load(p,0,doc,&error));exr_publication_free(p);
  OK(exr_layout_create_ex(*doc,font,&config,&out,&error));return out;
}
static void paragraph(void) {
  const char *names[]={"paragraph-he","paragraph-ar"};
  size_t k;
  for(k=0;k<2;k++) {
    size_t i,count;exr_document *doc=NULL;exr_layout *l;const exr_line *lines;
    l=layout(names[k],&doc);lines=exr_layout_lines(l,&count);CHECK(count>3);
    printf("script %zu: lines=%zu first=(%.3f,%.3f) last=(%.3f,%.3f)\n",k,count,lines[0].x,lines[0].width,lines[count-1].x,lines[count-1].width);
    CHECK(near(lines[0].x,20) && near(lines[0].x+lines[0].width,276));
    for(i=1;i+1<count;i++) CHECK(near(lines[i].x,20) && near(lines[i].width,280));
    CHECK(near(lines[count-1].x+lines[count-1].width,300));
    CHECK(lines[count-1].x>20); /* short final line is ragged on the left */
    exr_layout_free(l);exr_document_free(doc);
  }
  { /* Hard break and semantic heading both obey start in RTL justification. */
    exr_document *doc=NULL;size_t n,i;exr_layout *l=layout("break",&doc);
    const exr_line *lines=exr_layout_lines(l,&n);CHECK(n==3);
    for(i=0;i<n;i++) CHECK(near(lines[i].x+lines[i].width,300));
    exr_layout_free(l);exr_document_free(doc);
  }
}
static void run_order(const char *body,const char *token) {
  exr_document *doc=NULL;exr_layout *l=layout(body,&doc);size_t n,i,seen=0;
  const exr_glyph *g=exr_layout_glyphs(l,&n);float x=-1;
  for(i=0;i<n;i++) if(g[i].codepoint==(unsigned char)token[seen]) {
    CHECK(!(g[i].bidi_level&1) && g[i].x>x && g[i].glyph);
    x=g[i].x;seen++;if(!token[seen]) break;
  }
  CHECK(seen==strlen(token));
  exr_layout_free(l);exr_document_free(doc);
}
static void numbers(void) {
  run_order("numbers-he","0123456789");
  run_order("numbers-ar","0123456789");
  run_order("decimal","12.34");
}
static void mixed(void) {
  run_order("mixed-he","Reader ABC xyz");
  run_order("mixed-ar","Reader ABC xyz");
  run_order("ltr","Reader ABC xyz");
}
static void punctuation(void) {
  exr_document *doc=NULL;size_t n,i,mirrors=0,quotes=0;exr_layout *l;
  const exr_glyph *g;exr_shape_options options=exr_shape_defaults();
  l=layout("punctuation",&doc);
  g=exr_layout_glyphs(l,&n);
  for(i=0;i<n;i++) {
    uint32_t cp=g[i].codepoint,expected=cp;char utf8[4];size_t size=0,count=0;exr_shaped_glyph *shape=NULL;
    if(cp=='(') expected=')';else if(cp==')') expected='(';
    else if(cp=='[') expected=']';else if(cp==']') expected='[';
    else if(cp==0xab) expected=0xbb;else if(cp==0xbb) expected=0xab;
    else if(cp!='"' && cp!=0x201c && cp!=0x201d) continue;
    CHECK(g[i].bidi_level&1);
    if(expected!=cp) mirrors++;else quotes++; /* Quotes have no Unicode mirror mapping. */
    if(expected<128) utf8[size++]=(char)expected;
    else if(expected<2048) { utf8[size++]=(char)(0xc0|(expected>>6));utf8[size++]=(char)(0x80|(expected&63)); }
    else { utf8[size++]=(char)(0xe0|(expected>>12));utf8[size++]=(char)(0x80|((expected>>6)&63));utf8[size++]=(char)(0x80|(expected&63)); }
    options.direction=EXR_DIRECTION_LTR;
    OK(exr_shape(font,0,utf8,size,&options,&shape,&count,&error));
    CHECK(count==1 && shape[0].glyph==g[i].glyph && g[i].glyph);
    exr_free(shape);
  }
  CHECK(mirrors==6 && quotes==4);
  exr_layout_free(l);exr_document_free(doc);
}
static void progression(void) {
  const char *names[]={"arabic-journey","hebrew-journey","progression-ltr","progression-default","progression-absent","progression-invalid"};
  const exr_direction expected[]={EXR_DIRECTION_RTL,EXR_DIRECTION_RTL,EXR_DIRECTION_LTR,EXR_DIRECTION_RTL,EXR_DIRECTION_LTR,EXR_DIRECTION_RTL};
  size_t i;
  CHECK(exr_publication_page_progression(NULL)==EXR_DIRECTION_LTR);
  CHECK(exr_document_page_progression(NULL)==EXR_DIRECTION_LTR);
  for(i=0;i<sizeof(names)/sizeof(*names);i++) {
    char path[4096];exr_publication *p=NULL;exr_document *d=NULL;
    snprintf(path,sizeof(path),"%s/%s.epub",fixtures,names[i]);
    OK(exr_publication_open(path,&p,&error));CHECK(exr_publication_page_progression(p)==expected[i]);
    OK(exr_publication_load(p,0,&d,&error));CHECK(exr_document_page_progression(d)==expected[i]);
    exr_document_free(d);d=NULL;
    OK(exr_document_open(path,&d,&error));CHECK(exr_document_page_progression(d)==expected[i]);
    exr_document_free(d);exr_publication_free(p);
  }
}
int main(int argc,char **argv) {
  const char *path=getenv("EXR_TEST_FONT");CHECK(argc==3);
  fixtures=argv[1];
#ifdef _WIN32
  if(!path) path="C:/Windows/Fonts/arial.ttf";
#elif defined(__APPLE__)
  if(!path) path="/System/Library/Fonts/Supplemental/Arial.ttf";
#else
  if(!path) path="/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf";
#endif
  OK(exr_font_open(path,&font,&error));
  if(!strcmp(argv[2],"paragraph")) paragraph();
  else if(!strcmp(argv[2],"numbers")) numbers();
  else if(!strcmp(argv[2],"punctuation")) punctuation();
  else if(!strcmp(argv[2],"mixed")) mixed();
  else if(!strcmp(argv[2],"progression")) progression();
  else CHECK(0);
  exr_font_free(font);printf("RTL %s: %u checks passed\n",argv[2],checks);return 0;
}
