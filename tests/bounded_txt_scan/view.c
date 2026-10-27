#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
/* Private candidate entry point: deliberately absent from installed headers. */
extern exr_status exr_txt_pager_create_private(const exr_source *,exr_font *,const exr_layout_config *,exr_pager **,exr_error *);
typedef struct { const char *data;size_t size;int fail; } input;
static size_t read_at(void *ctx,uint64_t at,void *buffer,size_t size) {
  input *in=ctx;if(in->fail || at>in->size) return 0;
  if(size>in->size-(size_t)at) size=in->size-(size_t)at;
  if(size>127) size=127;memcpy(buffer,in->data+(size_t)at,size);return size;
}
static void die(const char *what,exr_error *e) { fprintf(stderr,"%s: %d %s\n",what,e->code,e->message);exit(1); }
static void compare(const char *data,size_t size,exr_font *font) {
  input in={data,size,0};exr_source source={0};exr_document *doc=NULL;exr_pager *a=NULL,*b=NULL;
  exr_layout *pa=NULL,*pb=NULL;exr_error e={0};size_t pages=0;
  source.size=size;source.read_at=read_at;source.context=&in;
  if(exr_document_open_memory(EXR_TXT,data,size,&doc,&e)!=EXR_OK) die("resident",&e);
  if(exr_pager_create(doc,font,NULL,&a,&e)!=EXR_OK) die("resident pager",&e);
  if(exr_txt_pager_create_private(&source,font,NULL,&b,&e)!=EXR_OK) die("TXT pager",&e);
  for(;;) {
    size_t na,nb,i;const exr_glyph *ga,*gb;const exr_page *xa,*xb;
    if(exr_pager_next(a,&pa,&e)!=EXR_OK || exr_pager_next(b,&pb,&e)!=EXR_OK) die("page",&e);
    if(!pa || !pb) { if(pa!=pb) die("page count",&e);break; }
    xa=exr_layout_pages(pa,&na);xb=exr_layout_pages(pb,&nb);
    if(na!=nb || (na && (xa[0].start!=xb[0].start || xa[0].end!=xb[0].end))) die("page range",&e);
    ga=exr_layout_glyphs(pa,&na);gb=exr_layout_glyphs(pb,&nb);
    if(na!=nb) die("glyph count",&e);
    for(i=0;i<na;i++) if(ga[i].start!=gb[i].start || ga[i].end!=gb[i].end || ga[i].node!=gb[i].node || ga[i].glyph!=gb[i].glyph || ga[i].x!=gb[i].x || ga[i].baseline!=gb[i].baseline) die("glyph mismatch",&e);
    exr_layout_free(pa);exr_layout_free(pb);pa=pb=NULL;pages++;
  }
  if(pages>3) {
    const exr_layout *x,*y;size_t na,nb;const exr_page *xa,*xb;
    if(exr_pager_get(a,1,&x,&e)!=EXR_OK || exr_pager_get(b,1,&y,&e)!=EXR_OK) die("replay",&e);
    xa=exr_layout_pages(x,&na);xb=exr_layout_pages(y,&nb);
    if(na!=nb || !na || xa[0].start!=xb[0].start || xa[0].end!=xb[0].end) die("replay mismatch",&e);
  }
  printf("compared %zu pages from %zu source bytes\n",pages,size);
  exr_pager_free(a);exr_pager_free(b);exr_document_free(doc);
}
static int cancelled(void *ctx) { (void)ctx;return 1; }
static void errors(exr_font *font) {
  static const char text[]="first paragraph\nsecond paragraph";
  static const char bad[]={(char)0xff,(char)0xfe,0};
  input in={text,sizeof(text)-1,0};exr_source source={0};exr_error e={0};
  exr_pager *pager=NULL;exr_layout *page=NULL;exr_layout_config config=exr_layout_config_defaults();
  source.size=in.size;source.context=&in;source.read_at=read_at;
  config.control.cancelled=cancelled;
  if(exr_txt_pager_create_private(&source,font,&config,&pager,&e)!=EXR_CANCELLED || pager) die("cancel",&e);
  in.data=bad;in.size=sizeof(bad);source.size=in.size;
  if(exr_txt_pager_create_private(&source,font,NULL,&pager,&e)!=EXR_ENCODING || pager) die("encoding",&e);
  in.data=text;in.size=sizeof(text)-1;source.size=in.size;
  if(exr_txt_pager_create_private(&source,font,NULL,&pager,&e)!=EXR_OK) die("IO setup",&e);
  in.fail=1;
  if(exr_pager_next(pager,&page,&e)!=EXR_IO || page) die("IO propagation",&e);
  exr_pager_free(pager);
}
int main(void) {
  static const char text[]="  Alpha \xe4\xb8\xad  \r\n\nBeta \xf0\x9f\x98\x80\rGamma\t\n";
  static const char utf16[]={ (char)0xff,(char)0xfe,'A',0,'\r',0,'\n',0,0x3d,(char)0xd8,0,(char)0xde };
  char *large;size_t i,at=0;exr_font *font=NULL;exr_error e={0};
  if(exr_font_open("C:/Windows/Fonts/arial.ttf",&font,&e)!=EXR_OK) die("font",&e);
  errors(font);compare(text,sizeof(text)-1,font);compare(utf16,sizeof(utf16),font);compare("",0,font);
  large=malloc(200000);if(!large) return 1;
  for(i=0;i<1800;i++) at+=(size_t)sprintf(large+at,"Paragraph %zu: stable positions and continuous pagination across the source.\n",i);
  compare(large,at,font);free(large);exr_font_free(font);return 0;
}
