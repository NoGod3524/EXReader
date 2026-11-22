/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include <math.h>
#include <miniz.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static exr_error error;
static unsigned checks;
#define CHECK(x) do { checks++; if (!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n", \
  __LINE__,#x,(int)error.code,error.message); exit(1); } } while (0)
#define OK(x) CHECK((x)==EXR_OK)
static int near(float a, float b) { return fabsf(a-b)<0.02f; }
static exr_font *font(const char *dir, const char *name) {
  char path[4096]; exr_font *out=NULL;
  CHECK(snprintf(path,sizeof(path),"%s/fonts/%s",dir,name)>0);
  OK(exr_font_open(path,&out,&error)); return out;
}
static exr_document *book(const char *dir) {
  char path[4096]; exr_document *out=NULL;
  CHECK(snprintf(path,sizeof(path),"%s/font-book.epub",dir)>0);
  OK(exr_document_open(path,&out,&error)); return out;
}
static exr_layout_config config(void) {
  exr_layout_config c=exr_layout_config_defaults();
  c.page=(exr_layout_options){180,100,8,20,1.2f,0}; return c;
}
static void embedded(const char *dir) {
  exr_font *host=font(dir,"primary.ttf"), *effective;
  exr_document *doc=book(dir);
  exr_layout_config c=config(); exr_layout *l=NULL;
  const exr_glyph *g; exr_font_input source={0};
  exr_bitmap bitmap={0}, alternate={0}; size_t n, pages, i;
  OK(exr_layout_create_ex(doc,host,&c,&l,&error));
  effective=exr_layout_font(l); CHECK(effective && effective!=host);
  CHECK(exr_font_count(host)==1 && exr_font_count(effective)==5);
  g=exr_layout_glyphs(l,&n); CHECK(n==5);
  CHECK(g[0].font_index==1 && near(g[0].advance,18));
  CHECK(g[1].font_index==2 && near(g[1].advance,10) && !(g[1].flags&EXR_GLYPH_BOLD));
  CHECK(g[2].font_index==3 && near(g[2].advance,18) && !(g[2].flags&EXR_GLYPH_ITALIC));
  CHECK(g[3].font_index==1 && near(g[3].advance,18));
  CHECK(g[4].font_index==4 && near(g[4].advance,10));
  OK(exr_font_source(effective,1,&source,&error));
  CHECK(source.data && source.size>100 && source.face_index==0);
  {
    exr_font *copy=NULL; OK(exr_font_create(&source,1,&copy,&error));
    CHECK(exr_font_has_glyph(copy,0,0x7532)); exr_font_free(copy);
  }
  CHECK(exr_font_source(effective,99,&source,&error)==EXR_ARGUMENT);
  CHECK(!source.data && !source.size && !source.face_index);
  CHECK(!exr_layout_font(NULL));
  exr_layout_pages(l,&pages);
  for(i=0;i<pages;i++) {
    OK(exr_render_page(l,host,i,&bitmap,&error));
    OK(exr_render_page(l,effective,i,&alternate,&error));
    CHECK(bitmap.stride==alternate.stride && bitmap.height==alternate.height);
    CHECK(!memcmp(bitmap.pixels,alternate.pixels,(size_t)bitmap.stride*bitmap.height));
    exr_bitmap_free(&bitmap); exr_bitmap_free(&alternate);
  }
  exr_document_free(doc); exr_font_free(host);
  OK(exr_render_page(l,NULL,0,&bitmap,&error)); exr_bitmap_free(&bitmap);
  exr_layout_free(l);
}
static void controls(const char *dir) {
  exr_font *host=font(dir,"primary.ttf"); exr_document *doc=book(dir);
  exr_layout_config c=config(); exr_layout *l=NULL; const exr_glyph *g; size_t i,n;
  c.embedded_fonts=0;
  OK(exr_layout_create_ex(doc,host,&c,&l,&error));
  CHECK(exr_layout_font(l)==host); g=exr_layout_glyphs(l,&n); CHECK(n==5);
  for(i=0;i<n;i++) CHECK(g[i].font_index==0);
  exr_layout_free(l); c=config(); c.document_css=0;
  OK(exr_layout_create_ex(doc,host,&c,&l,&error)); CHECK(exr_layout_font(l)==host);
  exr_layout_free(l); c=config(); c.user_css="* {font-family:'EXR Test Primary' !important}";
  OK(exr_layout_create_ex(doc,host,&c,&l,&error)); CHECK(exr_layout_font(l)==host);
  exr_layout_free(l); exr_document_free(doc); exr_font_free(host);
}
static void host_matching(const char *dir) {
  exr_font *a=font(dir,"primary.ttf"), *b=font(dir,"fallback.ttf"), *stack=NULL;
  exr_font_input inputs[2]; exr_document *doc=book(dir);
  exr_layout_config c=config(); exr_layout *l=NULL; const exr_glyph *g; size_t n,i,j;
  static const char *css[]={
    "* {font-family:'EXR Test Fallback'}",
    "* {font-family: EXR   Test   Fallback}",
    "* {font-family:'Missing', 'exr test fallback'}",
    "* {font-family:'EXR Test Fall\\62 ack';font-family: invalid(value)}",
    "@font-face {font-family:Remote;src:url(https://invalid.example/a.ttf),url(file:///a.ttf)} *{font-family:Remote}",
  };
  OK(exr_font_source(a,0,&inputs[0],&error)); OK(exr_font_source(b,0,&inputs[1],&error));
  OK(exr_font_create(inputs,2,&stack,&error)); exr_font_free(a); exr_font_free(b);
  c.document_css=0;
  for(i=0;i<sizeof(css)/sizeof(*css);i++) {
    c.user_css=css[i]; OK(exr_layout_create_ex(doc,stack,&c,&l,&error));
    CHECK(exr_layout_font(l)==stack); g=exr_layout_glyphs(l,&n); CHECK(n==5);
    for(j=0;j<n;j++) CHECK(g[j].font_index==(i==4 ? 0u : 1u));
    exr_layout_free(l);
  }
  exr_document_free(doc); exr_font_free(stack);
}
static void continuation(const char *dir) {
  exr_font *host=font(dir,"primary.ttf"); exr_document *doc=book(dir);
  exr_layout_config c=config(); exr_pager *p=NULL; exr_layout *page=NULL;
  const exr_layout *cached=NULL; exr_bitmap bitmap={0}; size_t count=0;
  OK(exr_pager_create(doc,host,&c,&p,&error));
  while(1) {
    OK(exr_pager_next(p,&page,&error)); if(!page) break;
    CHECK(exr_font_count(exr_layout_font(page))==5);
    OK(exr_render_page(page,host,0,&bitmap,&error));
    exr_bitmap_free(&bitmap); exr_layout_free(page); count++;
  }
  CHECK(count>=2); exr_pager_free(p);
  OK(exr_pager_create(doc,host,&c,&p,&error));
  OK(exr_pager_get(p,count-1,&cached,&error)); CHECK(cached);
  OK(exr_render_page(cached,host,0,&bitmap,&error)); exr_bitmap_free(&bitmap);
  OK(exr_pager_get(p,0,&cached,&error)); CHECK(cached);
  OK(exr_render_page(cached,NULL,0,&bitmap,&error)); exr_bitmap_free(&bitmap);
  exr_pager_free(p);
  OK(exr_pager_create(doc,host,&c,&p,&error)); OK(exr_pager_next(p,&page,&error));
  exr_pager_free(p); exr_document_free(doc); exr_font_free(host);
  OK(exr_render_page(page,NULL,0,&bitmap,&error)); exr_bitmap_free(&bitmap); exr_layout_free(page);
}
static void indexed(const char *dir) {
  char path[4096]; exr_publication *publication=NULL; exr_session *session=NULL;
  exr_font *host=font(dir,"primary.ttf"); const exr_document *doc=NULL;
  const exr_layout *l=NULL; const exr_glyph *g; size_t n;
  exr_layout_config c=config();
  CHECK(snprintf(path,sizeof(path),"%s/font-book.epub",dir)>0);
  OK(exr_publication_open(path,&publication,&error));
  OK(exr_session_create(publication,host,&c,1,&session,&error));
  OK(exr_session_get(session,0,&doc,&l,&error)); CHECK(exr_font_count(exr_layout_font(l))==4);
  g=exr_layout_glyphs(l,&n); CHECK(n==4 && g[0].font_index==1 && near(g[0].advance,18));
  OK(exr_session_get(session,1,&doc,&l,&error)); CHECK(exr_font_count(exr_layout_font(l))==2);
  g=exr_layout_glyphs(l,&n); CHECK(n==1 && g[0].font_index==1 && near(g[0].advance,10));
  exr_session_free(session); exr_publication_free(publication); exr_font_free(host);
}
/* WOFF 1.0 with zlib-compressed tables loads and shapes like its TrueType
   source: the FreeType module table keeps the gzip code the sfnt driver uses. */
static void woff(const char *dir) {
  char path[4096]; FILE *f; unsigned char *ttf,*out; long size; unsigned count,i; size_t at;
  exr_font *a,*b=NULL; exr_shape_options o=exr_shape_defaults(); exr_shaped_glyph *ga=NULL,*gb=NULL; size_t na=0,nb=0;
  CHECK(snprintf(path,sizeof(path),"%s/fonts/primary.ttf",dir)>0);
  f=fopen(path,"rb"); CHECK(f && !fseek(f,0,SEEK_END) && (size=ftell(f))>12); rewind(f);
  ttf=malloc((size_t)size); CHECK(ttf && fread(ttf,1,(size_t)size,f)==(size_t)size && !fclose(f));
  count=(unsigned)ttf[4]<<8|ttf[5]; at=44+20*(size_t)count;
  out=calloc(1,at+2*(size_t)size+64*count); CHECK(out);
  for(i=0;i<count;i++) {
    const unsigned char *e=ttf+12+16*i; unsigned char *d=out+44+20*i;
    uint32_t offset=(uint32_t)e[8]<<24|(uint32_t)e[9]<<16|(uint32_t)e[10]<<8|e[11];
    uint32_t length=(uint32_t)e[12]<<24|(uint32_t)e[13]<<16|(uint32_t)e[14]<<8|e[15];
    mz_ulong packed=(mz_ulong)(2*(size_t)size+64*count-at);
    CHECK(offset<=(uint32_t)size && length<=(uint32_t)size-offset);
    CHECK(mz_compress2(out+at,&packed,ttf+offset,length,9)==MZ_OK);
    if(packed>=length) { memcpy(out+at,ttf+offset,length); packed=length; }
    memcpy(d,e,4); /* tag */
    d[4]=(unsigned char)(at>>24); d[5]=(unsigned char)(at>>16); d[6]=(unsigned char)(at>>8); d[7]=(unsigned char)at;
    d[8]=(unsigned char)(packed>>24); d[9]=(unsigned char)(packed>>16); d[10]=(unsigned char)(packed>>8); d[11]=(unsigned char)packed;
    memcpy(d+12,e+12,4); memcpy(d+16,e+4,4); /* original length, checksum */
    at+=packed; while(at&3) at++;
  }
  memcpy(out,"wOFF",4); memcpy(out+4,ttf,4);
  out[8]=(unsigned char)(at>>24); out[9]=(unsigned char)(at>>16); out[10]=(unsigned char)(at>>8); out[11]=(unsigned char)at;
  out[12]=ttf[4]; out[13]=ttf[5];
  { uint32_t total=12+16*count; for(i=0;i<count;i++) { const unsigned char *e=ttf+12+16*i; total+=(((uint32_t)e[12]<<24|(uint32_t)e[13]<<16|(uint32_t)e[14]<<8|e[15])+3)&~3u; }
    out[16]=(unsigned char)(total>>24); out[17]=(unsigned char)(total>>16); out[18]=(unsigned char)(total>>8); out[19]=(unsigned char)total; }
  out[20]=0; out[21]=1;
  f=fopen("book-fonts-primary.woff","wb"); CHECK(f && fwrite(out,1,at,f)==at && !fclose(f));
  a=font(dir,"primary.ttf");
  OK(exr_font_open("book-fonts-primary.woff",&b,&error));
  OK(exr_shape(a,0,"Hello",5,&o,&ga,&na,&error)); OK(exr_shape(b,0,"Hello",5,&o,&gb,&nb,&error));
  CHECK(na==nb && na==5);
  for(i=0;i<na;i++) CHECK(ga[i].glyph==gb[i].glyph && near(ga[i].advance_x,gb[i].advance_x));
  exr_free(ga); exr_free(gb); exr_font_free(a); exr_font_free(b); remove("book-fonts-primary.woff"); free(out); free(ttf);
}
int main(int argc,char **argv) {
  CHECK(argc==2); woff(argv[1]); embedded(argv[1]); controls(argv[1]); host_matching(argv[1]);
  continuation(argv[1]); indexed(argv[1]);
  printf("Book fonts: %u checks passed\n",checks); return 0;
}
