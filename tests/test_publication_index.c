/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error;
#define CHECK(x) do {if(!(x)){fprintf(stderr,"line %d: %s (%s)\n",__LINE__,#x,error.message);exit(1);}}while(0)
#define OK(x) CHECK((x)==EXR_OK)
typedef struct {const char *body[3];int loads,fail;} source;
typedef struct {exr_search_result hits[32768];size_t n;} results;
static results linear,indexed;
static exr_status load(void *ctx,size_t part,exr_document **out,exr_error *e) {
  source *s=ctx;s->loads++;if(s->fail) return EXR_IO;
  return exr_document_open_memory(EXR_TXT,s->body[part],strlen(s->body[part]),out,e);
}
static exr_publication *open_source(source *s) {
  exr_publication *p=NULL;exr_part parts[]={{"a","a.txt","",1},{"aux","aux.txt","",0},{"b","b.txt","",1}};
  exr_publication_input in={0};in.parts=parts;in.part_count=3;in.load=load;in.context=s;
  OK(exr_publication_create(&in,&p,&error));return p;
}
static int collect(void *ctx,const exr_search_result *r) {
  results *out=ctx;CHECK(out->n<32768);out->hits[out->n++]=*r;return 1;
}
static int stop(void *ctx,const exr_search_result *r) {collect(ctx,r);return 0;}
static void equal(void) {
  CHECK(linear.n==indexed.n);
  for(size_t i=0;i<linear.n;i++) {
    exr_search_result a=linear.hits[i],b=indexed.hits[i];
    CHECK(a.found==b.found && a.part==b.part && a.offset==b.offset && a.length==b.length);
  }
}
static void compare(exr_publication *p,const char *q,unsigned flags,size_t batch) {
  size_t n,total=0;exr_index_cursor cursor={0};linear.n=indexed.n=0;
  OK(exr_publication_search_all(p,q,flags,collect,&linear,NULL,&n,&error));CHECK(n==linear.n);
  do {OK(exr_publication_index_search(p,q,flags,&cursor,batch,collect,&indexed,NULL,&n,&error));total+=n;} while(!cursor.done);
  CHECK(total==indexed.n);equal();
}
static source sample(void) {
  source s={{"aba ababa Cat cat scatter cat2 cat_cat CAFÉ café cafe\xCC\x81 年的的的寶玉宝玉 𠮷😀 Åå Ðð ×÷ Μμ İı Straße STRASSE 2026 12026 tail",
    "aba auxiliary 寶玉", "head aba cat 的的寶玉 CAFÉ cafe\xCC\x81 end"},0,0};return s;
}
static void equivalence(void) {
  source s=sample();exr_publication *p=open_source(&s);
  const char *queries[]={"aba","ababa","cat","Cat","café","CAFÉ","cafe\xCC\x81","寶玉","宝玉","的","的的","𠮷😀","å","ð","μ","ı","strasse","2026","tailhead","missing"};
  for(size_t i=0;i<20;i++) for(unsigned flags=0;flags<4;flags++) compare(p,queries[i],flags,2);
  CHECK(s.loads==2);exr_publication_free(p);puts("20 queries x 4 flags: complete positions equal");
}
static void boundaries(void) {
  char *body=malloc(60000);CHECK(body);body[0]=0;
  for(int i=0;i<900;i++) strcat(body,"的的寶玉 ababa Cat cafe\xCC\x81 ");
  source s={{body,"ignored",body},0,0};exr_publication *p=open_source(&s);exr_index_stats stats;
  OK(exr_publication_index_build(p,512,0,NULL,&stats,&error));CHECK(stats.memory_bytes<=512 && stats.peak_memory_bytes<=512);
  compare(p,"的的",0,1);compare(p,"寶玉",2,3);compare(p,"aba",0,7);compare(p,"cat",2,17);
  compare(p,"玉 aba",0,0);compare(p,"cafe\xCC\x81",2,19);
  exr_index_cursor cursor={{0,1},0};size_t n=0;
  OK(exr_publication_index_search(p,"的",0,&cursor,1,NULL,NULL,NULL,&n,&error));
  CHECK(n==1 && cursor.next.offset==4); /* rounds forward from UTF-8 continuation */
  exr_publication_free(p);free(body);
}
static void accents(void) {
  source s={{"café CAFÉ cafe\xCC\x81 CAFE Éé Àà Çç Ùù Ýý ÿ ø æ ß", "", "CAFÉ"},0,0};
  exr_publication *p=open_source(&s);size_t n;exr_index_cursor cursor={0};indexed.n=0;
  OK(exr_publication_index_search(p,"cafe",4,&cursor,0,collect,&indexed,NULL,&n,&error));CHECK(n==5);
  CHECK(indexed.hits[0].length==5 && indexed.hits[2].length==6);
  cursor=(exr_index_cursor){0};OK(exr_publication_index_search(p,"cafe",5,&cursor,0,NULL,NULL,NULL,&n,&error));CHECK(n==2);
  cursor=(exr_index_cursor){0};OK(exr_publication_index_search(p,"cafe",6,&cursor,0,NULL,NULL,NULL,&n,&error));CHECK(n==5);
  CHECK(exr_publication_search_all(p,"cafe",4,NULL,NULL,NULL,&n,&error)==EXR_ARGUMENT);
  compare(p,"café",0,1);compare(p,"cafe",0,1);exr_publication_free(p);
}
static int cancelled(void *ctx) {int *ticks=ctx;return --*ticks<=0;}
static void incremental(void) {
  source s=sample();exr_publication *p=open_source(&s);exr_index_stats stats;size_t n;
  OK(exr_publication_index_build(p,4096,1,NULL,&stats,&error));CHECK(stats.indexed_parts==1 && !stats.complete && s.loads==1);
  int ticks=1;exr_control control={cancelled,NULL,&ticks};
  CHECK(exr_publication_index_build(p,4096,0,&control,&stats,&error)==EXR_CANCELLED);
  OK(exr_publication_index_build(p,4096,1,NULL,&stats,&error));CHECK(stats.indexed_parts==2 && s.loads==1);
  OK(exr_publication_index_build(p,4096,1,NULL,&stats,&error));CHECK(stats.complete && s.loads==2);
  exr_index_cursor cursor={0};ticks=2;
  CHECK(exr_publication_index_search(p,"aba",0,&cursor,0,NULL,NULL,&control,&n,&error)==EXR_CANCELLED);
  CHECK(!n && !cursor.next.part && !cursor.next.offset && !cursor.done);
  indexed.n=0;OK(exr_publication_index_search(p,"aba",0,&cursor,0,stop,&indexed,NULL,&n,&error));CHECK(n==1 && !cursor.done);
  OK(exr_publication_index_search(p,"aba",0,&cursor,0,collect,&indexed,NULL,&n,&error));
  linear.n=0;OK(exr_publication_search_all(p,"aba",0,collect,&linear,NULL,&n,&error));equal();
  exr_publication_free(p);
  s.loads=0;p=open_source(&s);s.fail=1;
  CHECK(exr_publication_index_build(p,0,1,NULL,&stats,&error)==EXR_IO);s.fail=0;
  OK(exr_publication_index_build(p,0,0,NULL,&stats,&error));CHECK(stats.complete);compare(p,"aba",0,0);
  exr_publication_free(p);
  char *large=malloc(50001);CHECK(large);memset(large,'x',50000);large[50000]=0;
  source big={{large,"ignored","finish"},0,0};p=open_source(&big);ticks=5;
  CHECK(exr_publication_index_build(p,0,0,&control,&stats,&error)==EXR_CANCELLED);
  CHECK(stats.indexed_parts==0 && stats.text_bytes==0 && stats.memory_bytes<=512);
  OK(exr_publication_index_build(p,0,0,NULL,&stats,&error));CHECK(stats.complete);
  compare(p,large,EXR_SEARCH_WHOLE_WORD,0);exr_publication_free(p);free(large);
}
static void persistence(const char *path) {
  source s=sample();exr_publication *p=open_source(&s);exr_index_stats stats;
  OK(exr_publication_index_build(p,2048,1,NULL,&stats,&error));
  OK(exr_publication_index_save(p,path,"source-v1",NULL,&error));exr_publication_free(p);s.loads=0;p=open_source(&s);
  OK(exr_publication_index_load(p,path,"source-v1",512,NULL,&stats,&error));CHECK(s.loads==0 && stats.indexed_parts==1);
  OK(exr_publication_index_build(p,512,0,NULL,&stats,&error));CHECK(s.loads==1 && stats.complete);
  OK(exr_publication_index_save(p,path,"source-v1",NULL,&error));exr_publication_free(p);s.loads=0;p=open_source(&s);
  OK(exr_publication_index_load(p,path,"source-v1",512,NULL,&stats,&error));CHECK(s.loads==0 && stats.complete);
  OK(exr_publication_index_save(p,path,"source-v1",NULL,&error)); /* same path as loaded cache */
  exr_index_cursor cursor={0};size_t n;
  OK(exr_publication_index_search(p,"aba",0,&cursor,0,NULL,NULL,NULL,&n,&error));CHECK(n==4 && s.loads==0);
  CHECK(exr_publication_index_load(p,path,"source-v2",512,NULL,&stats,&error)==EXR_FORMAT);
  /* A failed replacement keeps the existing loaded index intact. */
  cursor=(exr_index_cursor){0};OK(exr_publication_index_search(p,"aba",0,&cursor,0,NULL,NULL,NULL,&n,&error));CHECK(n==4);
  exr_publication_free(p);p=open_source(&s);
  FILE *file=fopen(path,"r+b");CHECK(file);CHECK(!fseek(file,-1,SEEK_END));fputc(0xff,file);fclose(file);
  CHECK(exr_publication_index_load(p,path,"source-v1",512,NULL,&stats,&error)==EXR_FORMAT);
  file=fopen(path,"wb");CHECK(file);fputs("truncated",file);fclose(file);
  CHECK(exr_publication_index_load(p,path,"source-v1",512,NULL,&stats,&error)==EXR_FORMAT);
  exr_publication_free(p);remove(path);
}
static void errors(void) {
  source s=sample();exr_publication *p=open_source(&s);exr_index_cursor cursor={0};size_t n=999;
  CHECK(exr_publication_index_build(p,128,0,NULL,NULL,&error)==EXR_LIMIT);
  CHECK(exr_publication_index_search(p,"",0,&cursor,0,NULL,NULL,NULL,&n,&error)==EXR_ARGUMENT && n==0);
  CHECK(exr_publication_index_search(p,"\xc0\xaf",0,&cursor,0,NULL,NULL,NULL,&n,&error)==EXR_ENCODING);
  CHECK(exr_publication_index_search(p,"a",8,&cursor,0,NULL,NULL,NULL,&n,&error)==EXR_ARGUMENT);
  CHECK(exr_publication_index_search(p,"\xcc\x81",4,&cursor,0,NULL,NULL,NULL,&n,&error)==EXR_ARGUMENT);
  cursor.next.offset=99999;
  CHECK(exr_publication_index_search(p,"a",0,&cursor,0,NULL,NULL,NULL,&n,&error)==EXR_ARGUMENT);
  exr_publication_free(p);
}
static void anchors(void) {
  source s=sample();exr_publication *p=open_source(&s);exr_index_cursor cursor={0};size_t n;
  indexed.n=0;OK(exr_publication_index_search(p,"的",0,&cursor,0,collect,&indexed,NULL,&n,&error));CHECK(n==5);
  for(size_t i=0;i<n;i++) {
    exr_search_result r=indexed.hits[i];exr_text_range range={{r.part,r.offset},{r.part,r.offset+r.length}};
    exr_content_anchor anchor={0};exr_text_range_match match;
    OK(exr_anchor_from_range(p,&range,NULL,&anchor,&error));OK(exr_range_from_anchor(p,&anchor,NULL,&match,&error));
    CHECK(match.state==EXR_ANCHOR_FOUND && match.range.start.part==r.part && match.range.start.offset==r.offset && match.range.end.offset==r.offset+r.length);
    exr_content_anchor_free(&anchor);
  }
  exr_publication_free(p);
}
int main(int argc,char **argv) {
  CHECK(argc>=2);
  if(!strcmp(argv[1],"equivalence")) equivalence();
  else if(!strcmp(argv[1],"boundaries")) boundaries();
  else if(!strcmp(argv[1],"accents")) accents();
  else if(!strcmp(argv[1],"incremental")) incremental();
  else if(!strcmp(argv[1],"persistence")) {CHECK(argc==3);persistence(argv[2]);}
  else if(!strcmp(argv[1],"errors")) errors();
  else if(!strcmp(argv[1],"anchors")) anchors();
  else CHECK(0);
  printf("publication index %s passed\n",argv[1]);return 0;
}
