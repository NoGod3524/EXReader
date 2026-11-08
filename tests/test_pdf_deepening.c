/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
static exr_error error;
static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static exr_fixed_document *open_pdf(const char *dir,const char *name,const char *password) {
  char path[8192]; exr_fixed_document *d=NULL; exr_fixed_open_options options={0};
  snprintf(path,sizeof(path),"%s/%s.pdf",dir,name); options.struct_size=sizeof(options);
  options.pdf_password=password; options.pdf_password_size=password ? strlen(password) : 0;
  OK(exr_fixed_open(path,&options,&d,&error)); return d;
}
static int cancel(void *context) { return *(int *)context; }
static void search(const char *dir) {
  const char *words[]={"alpha","beta","gamma","delta","epsilon","zeta","theta","iota","kappa","boundary"};
  const size_t offsets[]={0,6,11,17,23,30,39,45,50,55};
  exr_fixed_document *d=open_pdf(dir,"text-a",NULL); exr_search_match m; size_t i;
  for(i=0;i<10;i++) {
    OK(exr_document_search(d,0,words[i],NULL,&m,&error));
    CHECK(m.start==offsets[i] && m.end==offsets[i]+strlen(words[i]));
    printf("word %s: [%zu,%zu), page %zu byte %zu\n",words[i],m.start,m.end,m.start_page,m.start_offset);
  }
  OK(exr_document_search(d,0,"epsilonzeta",NULL,&m,&error));
  CHECK(m.start==23 && m.end==34 && m.start_page==0 && m.start_offset==23 && m.end_page==1 && m.end_offset==4);
  printf("cross-page: [%zu,%zu), (%zu,%zu)..(%zu,%zu)\n",m.start,m.end,m.start_page,m.start_offset,m.end_page,m.end_offset);
  OK(exr_document_search(d,8,"eta",NULL,&m,&error)); CHECK(m.start==31);
  OK(exr_document_search(d,0,"missing",NULL,&m,&error)); CHECK(m.start==SIZE_MAX && m.end_page==SIZE_MAX);
  OK(exr_document_search(d,SIZE_MAX,"alpha",NULL,&m,&error)); CHECK(m.start==SIZE_MAX);
  exr_fixed_free(d);
  d=open_pdf(dir,"mixed-a",NULL);
  OK(exr_document_search(d,0,"alphabeta",NULL,&m,&error));
  CHECK(m.start_page==0 && m.end_page==2 && m.start_offset==0 && m.end_offset==4);
  OK(exr_document_search(d,5,"beta",NULL,&m,&error)); CHECK(m.start_page==2 && m.start_offset==0);
  exr_fixed_free(d);
  d=open_pdf(dir,"text-b",NULL);
  OK(exr_document_search(d,0,"caf\xc3\xa9",NULL,&m,&error)); CHECK(m.start==0 && m.end==5);
  OK(exr_document_search(d,4,"na\xc3\xafve",NULL,&m,&error)); CHECK(m.start==6);
  OK(exr_document_search(d,0,"repeat",NULL,&m,&error)); i=m.start;
  OK(exr_document_search(d,m.end,"repeat",NULL,&m,&error)); CHECK(m.start==i+7);
  exr_fixed_free(d);
}
static void coordinates(const char *dir) {
  const char *expected="alpha beta gamma del"; size_t i,n; exr_text_region r,*selected=NULL;
  uint32_t cp; exr_fixed_text *t=NULL; exr_fixed_document *d=open_pdf(dir,"text-a",NULL);
  OK(exr_fixed_page_text(d,0,NULL,&t,&error));
  for(i=0;i<20;i++) {
    /* Known Courier width 600/1000 em at 12 pt, baseline (20,90).
       Coordinates come from the input, never from engine output. */
    OK(exr_fixed_character_at(d,0,20+(i+.5)*7.2,92,NULL,&r,&cp,&error));
    CHECK(cp==(unsigned char)expected[i] && r.start==i && r.end==i+1);
    printf("point %.2f,92: U+%04X [%zu,%zu)\n",20+(i+.5)*7.2,(unsigned)cp,r.start,r.end);
    OK(exr_fixed_text_select(t,r.start,r.end,NULL,&selected,&n,&error));
    CHECK(n==1 && fabs(selected[0].quad[0]-(20+i*7.2))<1e-6); exr_free(selected);
  }
  CHECK(exr_fixed_character_at(d,0,290,10,NULL,&r,&cp,&error)==EXR_NO_TEXT_AT_POINT);
  CHECK(cp==0 && r.start==SIZE_MAX && error.code==EXR_NO_TEXT_AT_POINT);
  exr_fixed_text_free(t); exr_fixed_free(d);
  /* Existing original semantic fixture covers a ligature, nested Form,
     invisible text, vertical glyph and a non-BMP mapping. */
}
static void scans(const char *dir) {
  exr_fixed_document *d=open_pdf(dir,"scan-a",NULL); size_t i,n; exr_fixed_text *t=NULL;
  exr_text_region r; uint32_t cp; exr_search_match m; exr_bitmap b={0};
  CHECK(exr_fixed_pages(d,&n) && n==10);
  for(i=0;i<n;i++) {
    CHECK(exr_fixed_page_text(d,i,NULL,&t,&error)==EXR_NO_TEXT_LAYER && !t);
    CHECK(error.code==EXR_NO_TEXT_LAYER && error.message[0]);
    CHECK(exr_fixed_character_at(d,i,25,25,NULL,&r,&cp,&error)==EXR_NO_TEXT_LAYER && cp==0);
    OK(exr_fixed_render(d,i,1,NULL,&b,&error)); CHECK(b.width==300 && b.height==120);
    CHECK(b.pixels[35*b.stride+35*4]==255 && b.pixels[35*b.stride+45*4]==0);
    exr_bitmap_free(&b);
  }
  CHECK(exr_document_search(d,0,"alpha",NULL,&m,&error)==EXR_NO_TEXT_LAYER && m.start==SIZE_MAX);
  exr_fixed_free(d);
}
static void contracts(const char *dir,const char *fixtures) {
  exr_fixed_document *d=open_pdf(dir,"text-a",NULL); exr_search_match m;
  exr_control control={0}; int stop=1; uint32_t cp; exr_text_region r; exr_fixed_text *t=NULL; char *large;
  control.cancelled=cancel; control.context=&stop;
  CHECK(exr_document_search(d,0,"alpha",&control,&m,&error)==EXR_CANCELLED && m.start==SIZE_MAX);
  CHECK(exr_document_search(d,0,"",NULL,&m,&error)==EXR_ARGUMENT && m.end==SIZE_MAX);
  CHECK(exr_document_search(d,0,"\xff",NULL,&m,&error)==EXR_ENCODING);
  CHECK(exr_document_search(NULL,0,"x",NULL,&m,&error)==EXR_ARGUMENT);
  CHECK(exr_fixed_page_text(d,99,NULL,&t,&error)==EXR_ARGUMENT && !t);
  CHECK(exr_fixed_character_at(d,0,NAN,0,NULL,&r,&cp,&error)==EXR_ARGUMENT && cp==0 && r.start==SIZE_MAX);
  CHECK(exr_fixed_character_at(d,0,25,92,&control,&r,&cp,&error)==EXR_CANCELLED && r.end==SIZE_MAX);
  large=malloc(1048578); CHECK(large); memset(large,'a',1048577); large[1048577]=0;
  CHECK(exr_document_search(d,0,large,NULL,&m,&error)==EXR_LIMIT); free(large); exr_fixed_free(d);
  d=open_pdf(fixtures,"pdf-public-text",NULL);
  OK(exr_fixed_character_at(d,0,217,630,NULL,&r,&cp,&error)); CHECK(cp=='f' && r.start==1 && r.end==3);
  OK(exr_fixed_character_at(d,0,16,24,NULL,&r,&cp,&error)); CHECK(cp=='A');
  OK(exr_fixed_character_at(d,0,100,190,NULL,&r,&cp,&error)); CHECK(cp=='A' && (r.flags&EXR_REGION_VERTICAL));
  OK(exr_fixed_character_at(d,0,100,170,NULL,&r,&cp,&error)); CHECK(cp==0x1f600 && r.end-r.start==4);
  OK(exr_fixed_page_text(d,0,NULL,&t,&error)); exr_fixed_text_free(t);
  CHECK(exr_fixed_page_text(d,1,NULL,&t,&error)==EXR_FORMAT && !t);
  CHECK(exr_document_search(d,14,"unfindable",NULL,&m,&error)==EXR_FORMAT && m.start==SIZE_MAX);
  CHECK(exr_fixed_page_text(d,3,NULL,&t,&error)==EXR_NO_TEXT_LAYER && !t);
  OK(exr_fixed_load_text(d,3,NULL,&t,&error)); CHECK(exr_fixed_text_string(t,NULL)); exr_fixed_text_free(t);
  exr_fixed_free(d);
}
static void encrypted(const char *fixtures) {
  char dir[4096],path[4096]; exr_fixed_document *d=NULL; exr_search_match m; exr_fixed_open_options options={0};
  snprintf(dir,sizeof(dir),"%s/pdf-crypto",fixtures);
  /* R4 + R6; empty-password files exercise permissions-only encryption. */
  if(exr_pdf_crypto_available()) {
    const char *names[]={"r4","r6","r4-empty","r6-empty"}; size_t i;
    for(i=0;i<4;i++) {
      snprintf(path,sizeof(path),"%s/pdf-crypto/%s.pdf",fixtures,names[i]);
      if(i<2) {
        CHECK(exr_fixed_open(path,NULL,&d,&error)==EXR_PASSWORD && !d && error.code==EXR_PASSWORD);
        options.struct_size=sizeof(options); options.pdf_password="wrong"; options.pdf_password_size=5;
        CHECK(exr_fixed_open(path,&options,&d,&error)==EXR_PASSWORD && !d);
      }
      d=open_pdf(dir,names[i],i<2 ? "reader" : NULL);
      OK(exr_document_search(d,0,"Secret",NULL,&m,&error)); CHECK(m.start_page==0 && m.start==0);
      exr_fixed_free(d); d=NULL;
    }
  } else {
    snprintf(path,sizeof(path),"%s/pdf-crypto/r6.pdf",fixtures);
    CHECK(exr_fixed_open(path,NULL,&d,&error)==EXR_UNSUPPORTED && !d);
  }
}
int main(int argc,char **argv) {
  CHECK(argc==4);
  if(!strcmp(argv[1],"search")) search(argv[2]);
  else if(!strcmp(argv[1],"coordinates")) coordinates(argv[2]);
  else if(!strcmp(argv[1],"scan")) scans(argv[2]);
  else if(!strcmp(argv[1],"contracts")) contracts(argv[2],argv[3]);
  else if(!strcmp(argv[1],"encryption")) encrypted(argv[3]);
  else CHECK(0);
  printf("%s: %u checks passed\n",argv[1],checks); return 0;
}
