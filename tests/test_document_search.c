/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error;
#define CHECK(x) do {if(!(x)){fprintf(stderr,"line %d: %s (%s)\n",__LINE__,#x,error.message);exit(1);}}while(0)
#define OK(x) CHECK((x)==EXR_OK)
typedef struct {const char *body[3];int loads,fail;} source;
static exr_status load(void *ctx,size_t part,exr_document **out,exr_error *e) {
  source *s=ctx;s->loads++;if(s->fail) return EXR_IO;
  return exr_document_open_memory(EXR_TXT,s->body[part],strlen(s->body[part]),out,e);
}
static exr_publication *open_source(source *s) {
  exr_publication *p=NULL;exr_part parts[]={{"a","a.txt","",1},{"aux","aux.txt","",0},{"b","b.txt","",1}};
  exr_publication_input in={0};in.parts=parts;in.part_count=3;in.load=load;in.context=s;
  OK(exr_publication_create(&in,&p,&error));return p;
}
static size_t count(exr_publication *p,const char *q,unsigned flags) {
  size_t n=999;OK(exr_publication_search_all(p,q,flags,NULL,NULL,NULL,&n,&error));return n;
}
typedef struct {exr_search_result hits[64];size_t n;} results;
static int collect(void *ctx,const exr_search_result *r) {results *a=ctx;CHECK(a->n<64);a->hits[a->n++]=*r;return 1;}
static int stop(void *ctx,const exr_search_result *r) {(void)ctx;(void)r;return 0;}
static int cancel(void *ctx) {(void)ctx;return 1;}
static void basic(void) {
  source s={{"aba ababa 2026 tail","aba ignored","head aba 2026"},0,0};exr_publication *p=open_source(&s);exr_search_result r;
  CHECK(count(p,"aba",0)==4);CHECK(s.loads==2);CHECK(count(p,"2026",0)==2);CHECK(s.loads==2);
  CHECK(count(p,"tailhead",0)==0);CHECK(count(p,"missing",0)==0);
  OK(exr_publication_search(p,(exr_text_position){0,1},"aba",0,NULL,&r,&error));CHECK(r.found && r.part==0 && r.offset==4 && r.length==3);
  OK(exr_publication_search(p,(exr_text_position){0,14},"aba",0,NULL,&r,&error));CHECK(r.found && r.part==2);
  OK(exr_publication_search(p,(exr_text_position){2,8},"aba",0,NULL,&r,&error));CHECK(!r.found && r.offset==SIZE_MAX);
  size_t n;OK(exr_publication_search_all(p,"aba",0,stop,NULL,NULL,&n,&error));CHECK(n==1);
  exr_publication_free(p);
}
static void unicode(void) {
  source s={{"中文寶玉寶玉 𠮷😀 café CAFÉ Åå Ðð ×÷ Μμ İı Straße STRASSE","中文","竖排 日本語 寶玉"},0,0};exr_publication *p=open_source(&s);exr_search_result r;
  CHECK(count(p,"寶玉",0)==3);CHECK(count(p,"𠮷😀",0)==1);CHECK(count(p,"中文",0)==1);
  CHECK(count(p,"café",0)==2);CHECK(count(p,"å",0)==2);CHECK(count(p,"ð",0)==2);
  CHECK(count(p,"μ",0)==1);CHECK(count(p,"ı",0)==1);CHECK(count(p,"strasse",0)==1);
  OK(exr_publication_search(p,(exr_text_position){0,1},"中文",0,NULL,&r,&error));CHECK(!r.found);
  CHECK(count(p,"寶",EXR_SEARCH_WHOLE_WORD)==3);
  exr_publication_free(p);
}
static void flags(void) {
  source s={{"Cat cat scatter cat2 cat_cat cat. CAFÉ café Éé 2026 12026","cat","cat"},0,0};exr_publication *p=open_source(&s);
  CHECK(count(p,"Cat",EXR_SEARCH_CASE_SENSITIVE)==1);
  CHECK(count(p,"CAFÉ",EXR_SEARCH_CASE_SENSITIVE)==1);
  CHECK(count(p,"É",EXR_SEARCH_CASE_SENSITIVE)==2);
  CHECK(count(p,"cat",EXR_SEARCH_WHOLE_WORD)==4);
  CHECK(count(p,"café",EXR_SEARCH_WHOLE_WORD)==2);
  CHECK(count(p,"2026",EXR_SEARCH_WHOLE_WORD)==1);
  CHECK(count(p,"Cat",EXR_SEARCH_WHOLE_WORD|EXR_SEARCH_CASE_SENSITIVE)==1);
  exr_publication_free(p);
}
static void errors(void) {
  source s={{"text","","text"},0,0};exr_publication *p=open_source(&s);size_t n=999;exr_search_result r;exr_control c={cancel,NULL,NULL};
  CHECK(exr_publication_search_all(p,"",0,NULL,NULL,NULL,&n,&error)==EXR_ARGUMENT && n==0);
  CHECK(exr_publication_search_all(p,"\xc0\xaf",0,NULL,NULL,NULL,&n,&error)==EXR_ENCODING);
  CHECK(exr_publication_search_all(p,"t",4,NULL,NULL,NULL,&n,&error)==EXR_ARGUMENT);
  CHECK(exr_publication_search(p,(exr_text_position){9,0},"t",0,NULL,&r,&error)==EXR_ARGUMENT && !r.found);
  CHECK(exr_publication_search(p,(exr_text_position){0,999},"t",0,NULL,&r,&error)==EXR_ARGUMENT);
  CHECK(exr_publication_search_all(p,"t",0,NULL,NULL,&c,&n,&error)==EXR_CANCELLED && n==0);
  CHECK(count(p,"t",0)==4);exr_publication_free(p);
  s.fail=1;p=open_source(&s);CHECK(exr_publication_search_all(p,"t",0,NULL,NULL,NULL,&n,&error)==EXR_IO && n==0);exr_publication_free(p);
}
static void mapping(const char *font_path) {
  source s={{"alpha hit 中文 2026 hit hit hit hit hit hit hit hit hit hit","","beta hit hit hit hit hit hit hit hit hit hit"},0,0};
  exr_publication *p=open_source(&s);exr_font *font=NULL;results a={0};size_t n=0;
  OK(exr_font_open(font_path,&font,&error));OK(exr_publication_search_all(p,"hit",0,collect,&a,NULL,&n,&error));CHECK(n>=20);
  for(size_t i=0;i<20;i++) {
    exr_search_result r=a.hits[i];exr_document *doc=NULL;exr_layout *layout=NULL;exr_anchor anchor={0};exr_anchor_match match;
    exr_target target={r.part,NULL,r.offset};exr_location location;size_t size,ng;
    OK(exr_publication_locate(p,&target,&location,&error));CHECK(location.offset==r.offset && location.part==r.part);
    OK(exr_publication_load(p,r.part,&doc,&error));const char *text=exr_document_text(doc,&size);CHECK(r.offset+r.length<=size && !memcmp(text+r.offset,"hit",3));
    OK(exr_anchor_create(doc,r.offset,r.offset+r.length,&anchor,&error));OK(exr_anchor_resolve(doc,&anchor,&match,&error));CHECK(match.state==EXR_ANCHOR_FOUND && match.start==r.offset);
    exr_layout_config cfg=exr_layout_config_defaults();cfg.page.width=240;cfg.page.height=160;cfg.page.font_size=16;
    if(i%2) cfg.user_css="* { writing-mode: vertical-rl; }";
    OK(exr_layout_create_ex(doc,font,&cfg,&layout,&error));const exr_glyph *gs=exr_layout_glyphs(layout,&ng);int found=0;
    for(size_t g=0;g<ng;g++) if(gs[g].cluster_start<=r.offset && gs[g].cluster_end>r.offset) found=1;
    CHECK(found);exr_layout_free(layout);exr_anchor_free(&anchor);exr_document_free(doc);
  }
  exr_font_free(font);exr_publication_free(p);puts("jump/anchor/glyph mapping 20/20 (10 vertical)");
}
/* 24 parts x 1 MiB exceed the 16 MiB snapshot budget: results stay exact,
   evicted parts reload, and a provider that changes evicted text is rejected. */
#define BIG_PARTS 24
#define BIG_SIZE ((size_t)1024*1024)
typedef struct {char *body[BIG_PARTS];int loads;} big_source;
static exr_status big_load(void *ctx,size_t part,exr_document **out,exr_error *e) {
  big_source *s=ctx;s->loads++;return exr_document_open_memory(EXR_TXT,s->body[part],BIG_SIZE,out,e);
}
static void bounded(void) {
  big_source s={{0},0};exr_part parts[BIG_PARTS];exr_publication_input in={0};exr_publication *p=NULL;size_t i,n=0;
  for(i=0;i<BIG_PARTS;i++) {
    CHECK((s.body[i]=malloc(BIG_SIZE)));memset(s.body[i],'x',BIG_SIZE);
    memcpy(s.body[i]+BIG_SIZE/2,"needle",6);memcpy(s.body[i]+BIG_SIZE-6,"needle",6);
    parts[i]=(exr_part){"p","p.txt","",1};
  }
  in.parts=parts;in.part_count=BIG_PARTS;in.load=big_load;in.context=&s;
  OK(exr_publication_create(&in,&p,&error));
  CHECK(count(p,"needle",0)==2*BIG_PARTS);CHECK(s.loads==BIG_PARTS);
  CHECK(count(p,"needle",0)==2*BIG_PARTS);CHECK(s.loads>BIG_PARTS);
  /* The most recently searched part is still resident; an evicted one reloads. */
  n=s.loads;CHECK(count(p,"xneedle",0)==2*BIG_PARTS);CHECK(s.loads>n);
  s.body[0][10]='y';
  CHECK(exr_publication_search_all(p,"needle",0,NULL,NULL,NULL,&n,&error)==EXR_FORMAT && n==0);
  s.body[0][10]='x';CHECK(count(p,"needle",0)==2*BIG_PARTS);
  exr_publication_free(p);
  for(i=0;i<BIG_PARTS;i++) free(s.body[i]);
}
int main(int argc,char **argv) {
  CHECK(argc>=2);
  if(!strcmp(argv[1],"basic")) basic();else if(!strcmp(argv[1],"unicode")) unicode();else if(!strcmp(argv[1],"flags")) flags();else if(!strcmp(argv[1],"errors")) errors();else if(!strcmp(argv[1],"bounded")) bounded();else {CHECK(argc==3);mapping(argv[2]);}
  printf("search %s passed\n",argv[1]);return 0;
}
