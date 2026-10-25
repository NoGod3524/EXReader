/* SPDX-License-Identifier: MIT */
#define _CRT_SECURE_NO_WARNINGS
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#define REQUIRE(x) do { if(!(x)){fprintf(stderr,"line %d: %s\n",__LINE__,#x);exit(1);} } while(0)
static size_t alive=0,calls=0;
static long fail_at=-1;
static void *count_malloc(size_t n) {
  size_t call=calls++;void *p;
  if(fail_at>=0&&call==(size_t)fail_at)return NULL;
  p=malloc(n);if(p)alive++;return p;
}
static void count_free(void *p) {if(p){REQUIRE(alive>0);alive--;free(p);}}
#define malloc count_malloc
#define free count_free
#include "reading_capture_bytes.h"
#undef malloc
#undef free

static void dispose(reader_rs_record *r) {
  count_free(r->chapter);count_free(r->part_path);count_free(r->page_id);
  count_free(r->exact);count_free(r->prefix);count_free(r->suffix);count_free(r->note_text);
  memset(r,0,sizeof(*r));
}
static void text_equal(const char *a,const char *b) {REQUIRE((a==NULL)==(b==NULL));if(a)REQUIRE(!strcmp(a,b));}
static void blob_equal(const char *a,const char *b,size_t n) {
  REQUIRE((a==NULL)==(b==NULL));if(a){REQUIRE(b[n]==0);if(n)REQUIRE(!memcmp(a,b,n));}
}
static void roundtrip(const reader_rs_capture *c,size_t part,unsigned writer,unsigned char **bytes,size_t *size) {
  reader_rs_record r;reader_rs_capture reconstructed;exr_anchor a;exr_fixed_anchor f;
  unsigned char *second=NULL;size_t second_size=0;memset(&r,0,sizeof(r));
  REQUIRE(reader_private_capture_encode(c,part,writer,bytes,size)==EXR_OK);
  REQUIRE(reader_private_capture_decode(*bytes,*size,&r)==EXR_OK);
  REQUIRE(r.mode==c->mode&&r.part==part&&r.page==c->page&&r.anchor_version==writer&&r.has_location==1);
  REQUIRE(!r.entity_kind[0]&&!r.operation[0]&&!r.book_key[0]&&!r.annotation_id[0]&&!r.parser_version[0]&&!r.note_text);
  text_equal(c->part_path,r.part_path);memset(&a,0,sizeof(a));memset(&f,0,sizeof(f));memset(&reconstructed,0,sizeof(reconstructed));
  reconstructed.mode=r.mode;reconstructed.page=(size_t)r.page;reconstructed.part_path=r.part_path;
  if(c->mode==READER_RS_FIXED_PAGE) {
    REQUIRE(r.start==c->fixed->start&&r.end==c->fixed->end);text_equal(c->fixed->page_id,r.page_id);REQUIRE(!r.chapter);
    REQUIRE(r.exact_size==c->fixed->exact_size&&r.prefix_size==c->fixed->prefix_size&&r.suffix_size==c->fixed->suffix_size);
    blob_equal(c->fixed->exact,r.exact,r.exact_size);blob_equal(c->fixed->prefix,r.prefix,r.prefix_size);blob_equal(c->fixed->suffix,r.suffix,r.suffix_size);
    f.start=(size_t)r.start;f.end=(size_t)r.end;f.page_id=r.page_id;f.exact=r.exact;f.prefix=r.prefix;f.suffix=r.suffix;
    f.exact_size=r.exact_size;f.prefix_size=r.prefix_size;f.suffix_size=r.suffix_size;reconstructed.fixed=&f;
  } else {
    REQUIRE(r.start==c->anchor->start&&r.end==c->anchor->end);text_equal(c->anchor->chapter,r.chapter);REQUIRE(!r.page_id);
    text_equal(c->anchor->exact,r.exact);text_equal(c->anchor->prefix,r.prefix);text_equal(c->anchor->suffix,r.suffix);
    a.start=(size_t)r.start;a.end=(size_t)r.end;a.chapter=r.chapter;a.exact=r.exact;a.prefix=r.prefix;a.suffix=r.suffix;reconstructed.anchor=&a;
  }
  REQUIRE(reader_private_capture_encode(&reconstructed,(size_t)r.part,(unsigned)r.anchor_version,&second,&second_size)==EXR_OK);
  REQUIRE(second_size==*size&&!memcmp(second,*bytes,*size));reader_private_capture_free(second);dispose(&r);
}
static void vector(const char *directory,const char *name,const reader_rs_capture *c,size_t part,unsigned writer) {
  unsigned char *bytes=NULL;size_t size=0;char path[1024];FILE *file;
  roundtrip(c,part,writer,&bytes,&size);REQUIRE(snprintf(path,sizeof(path),"%s/%s.bin",directory,name)>0);
  file=fopen(path,"wb");REQUIRE(file&&fwrite(bytes,1,size,file)==size);REQUIRE(!fclose(file));reader_private_capture_free(bytes);REQUIRE(alive==0);
}
static void rejected(const unsigned char *bytes,size_t size) {
  reader_rs_record r,before;memset(&r,0xa5,sizeof(r));memcpy(&before,&r,sizeof(r));
  REQUIRE(reader_private_capture_decode(bytes,size,&r)!=EXR_OK);REQUIRE(!memcmp(&r,&before,sizeof(r))&&alive==0);
}
static void put(unsigned char *bytes,size_t at,uint64_t n,unsigned count) {
  unsigned i;for(i=0;i<count;i++){bytes[at+i]=(unsigned char)(n&255u);n>>=8;}
}
static size_t blob_at(const unsigned char *bytes,unsigned field) {
  size_t at=56;unsigned i;for(i=0;i<field;i++){
    size_t n=(size_t)bytes[at+1]|((size_t)bytes[at+2]<<8)|((size_t)bytes[at+3]<<16)|((size_t)bytes[at+4]<<24);at+=5+n;
  }return at;
}
int main(int argc,char **argv) {
  reader_rs_capture c;exr_anchor a;exr_fixed_anchor f;unsigned char *bytes=NULL,*mutated;size_t size=0,i;unsigned w,mask;
  unsigned char exact[4]={'A',0,'B',0xff};char empty[1]={0},zero[1]={0};
  REQUIRE(argc==2);memset(&c,0,sizeof(c));memset(&a,0,sizeof(a));memset(&f,0,sizeof(f));
  c.mode=READER_RS_FIXED_PAGE;c.fixed=&f;c.page=7;f.page_id=(char *)"p7";f.start=11;f.end=15;f.exact=(char *)exact;f.exact_size=4;f.prefix=empty;
  vector(argv[1],"fixed3",&c,3,3);vector(argv[1],"fixed1",&c,3,1);vector(argv[1],"fixed2",&c,3,2);puts("PASS fixed-counted-binary-all-writers");
  f.start=f.end=0;f.exact=NULL;f.exact_size=0;f.suffix=zero;f.suffix_size=1;vector(argv[1],"null-exact",&c,3,2);puts("PASS null-empty-and-binary-suffix");
  memset(&c,0,sizeof(c));c.mode=READER_RS_REFLOW_GLOBAL;c.anchor=&a;a.start=2;a.end=5;a.exact=(char *)"abc";a.suffix=empty;a.chapter=(char *)"chapter1";
  vector(argv[1],"reflow1",&c,0,1);vector(argv[1],"reflow2",&c,0,2);
  c.mode=READER_RS_EPUB_CHAPTER;c.part_path="spine/ch.xhtml";a.chapter=(char *)"ch.xhtml";a.start=1;a.end=8;a.exact=(char *)"\xe6\xb1\x89\xf0\x9f\x98\x80";
  vector(argv[1],"epub2",&c,9,2);puts("PASS text-routes-unicode-and-deterministic-reencode");
  c.mode=READER_RS_FIXED_PAGE;c.anchor=NULL;c.fixed=&f;c.part_path=NULL;c.page=0;memset(&f,0,sizeof(f));
  for(w=1;w<=3;w++)for(mask=0;mask<16;mask++){
    f.page_id=mask&8?empty:NULL;f.exact=mask&1?empty:NULL;f.prefix=mask&2?empty:NULL;f.suffix=mask&4?empty:NULL;
    roundtrip(&c,0,w,&bytes,&size);reader_private_capture_free(bytes);REQUIRE(alive==0);
  }puts("PASS all-null-empty-selector-combinations");
  f.page_id=(char *)"page";f.exact=empty;f.prefix=(char *)"pre";f.prefix_size=3;f.suffix=(char *)"suf";f.suffix_size=3;c.part_path="path";
  REQUIRE(reader_private_capture_encode(&c,0,3,&bytes,&size)==EXR_OK);
  mutated=(unsigned char *)malloc(size+1);REQUIRE(mutated);
  /* Every truncation boundary must fail without changing caller output. */
  for(i=0;i<size;i++){size_t saved_alive=alive;reader_rs_record r,before;memset(&r,0xa5,sizeof(r));memcpy(&before,&r,sizeof(r));REQUIRE(reader_private_capture_decode(bytes,i,&r)!=EXR_OK);REQUIRE(!memcmp(&r,&before,sizeof(r))&&alive==saved_alive);}
  memcpy(mutated,bytes,size);mutated[size]=0;reader_private_capture_free(bytes);bytes=NULL;rejected(mutated,size+1);
  for(i=0;i<8;i++){unsigned char saved=mutated[i];mutated[i]^=0xff;rejected(mutated,size);mutated[i]=saved;}
  memcpy(mutated,"EXRRD001",8);rejected(mutated,size);memcpy(mutated,"EXRPCAP",8);rejected((const unsigned char *)"[pending]\nversion=1\n",20);
  for(i=8;i<=20;i+=4){uint64_t invalid=i==8?2:i==12?4:i==16?4:1;put(mutated,i,invalid,4);rejected(mutated,size);put(mutated,i,i==8?1:i==12?3:i==16?3:0,4);}
  put(mutated,12,0,4);rejected(mutated,size);put(mutated,12,3,4);put(mutated,16,0,4);rejected(mutated,size);put(mutated,16,3,4);
  put(mutated,40,1,8);rejected(mutated,size);put(mutated,40,0,8);
  for(i=0;i<6;i++){
    size_t at=blob_at(mutated,(unsigned)i);unsigned char saved=mutated[at];uint64_t length=(uint64_t)mutated[at+1]|((uint64_t)mutated[at+2]<<8)|((uint64_t)mutated[at+3]<<16)|((uint64_t)mutated[at+4]<<24);
    mutated[at]=2;rejected(mutated,size);mutated[at]=0;put(mutated,at+1,1,4);rejected(mutated,size);mutated[at]=saved;put(mutated,at+1,UINT32_MAX,4);rejected(mutated,size);put(mutated,at+1,length,4);
  }
  {size_t at=blob_at(mutated,2)+5;unsigned char saved=mutated[at];mutated[at]=0;rejected(mutated,size);mutated[at]=saved;}
  rejected(mutated,READER_PRIVATE_CAPTURE_MAX_BYTES+1);puts("PASS truncation-tags-lengths-versions-tail-and-old-format-rejection");
  /* Allocation failure at every partial decoded allocation, then success. */
  for(i=0;i<5;i++){
    reader_rs_record r,before;memset(&r,0xa5,sizeof(r));memcpy(&before,&r,sizeof(r));calls=0;fail_at=(long)i;
    REQUIRE(reader_private_capture_decode(mutated,size,&r)==EXR_MEMORY);REQUIRE(!memcmp(&r,&before,sizeof(r))&&alive==0);fail_at=-1;
  }
  {reader_rs_record r;calls=0;fail_at=5;REQUIRE(reader_private_capture_decode(mutated,size,&r)==EXR_OK);fail_at=-1;dispose(&r);REQUIRE(alive==0);}
  {unsigned char *out=(unsigned char *)(uintptr_t)1;size_t n=123;calls=0;fail_at=0;REQUIRE(reader_private_capture_encode(&c,0,3,&out,&n)==EXR_MEMORY&&out==(unsigned char *)(uintptr_t)1&&n==123);fail_at=-1;}
  puts("PASS malloc-failure-transaction-and-partial-cleanup");
  free(mutated);
  {char nonterminated[4]={'a','b','c','d'};f.exact=nonterminated;f.exact_size=4;f.end=4;roundtrip(&c,0,3,&bytes,&size);reader_private_capture_free(bytes);}
  {char *large=(char *)malloc(65538);REQUIRE(large);memset(large,'x',65537);large[65537]=0;
    f.exact=large;f.exact_size=65536;f.end=65536;roundtrip(&c,0,3,&bytes,&size);reader_private_capture_free(bytes);
    f.exact_size=65537;f.end=65537;REQUIRE(reader_private_capture_encode(&c,0,3,&bytes,&size)==EXR_LIMIT);
    memset(&c,0,sizeof(c));memset(&a,0,sizeof(a));c.mode=READER_RS_REFLOW_GLOBAL;c.anchor=&a;a.exact=large;a.end=65537;REQUIRE(reader_private_capture_encode(&c,0,2,&bytes,&size)==EXR_LIMIT);
    large[65536]=0;a.end=65536;roundtrip(&c,0,2,&bytes,&size);reader_private_capture_free(bytes);free(large);
  }puts("PASS exact-blob-boundary-and-nonterminated-fixed-buffer");
  {char bad[4]={'a',0,'b',0};a.exact=bad;a.start=0;a.end=3;REQUIRE(reader_private_capture_encode(&c,0,2,&bytes,&size)==EXR_ARGUMENT);}
  a.exact=(char *)"abc";a.end=3;REQUIRE(reader_private_capture_encode(&c,0,2,&bytes,&size)==EXR_OK);
  {reader_rs_record r,before;size_t at=blob_at(bytes,3)+5;bytes[at+1]=0;memset(&r,0xa5,sizeof(r));memcpy(&before,&r,sizeof(r));REQUIRE(reader_private_capture_decode(bytes,size,&r)==EXR_FORMAT&&!memcmp(&r,&before,sizeof(r)));}
  reader_private_capture_free(bytes);puts("PASS counted-text-nul-rejected");
#if SIZE_MAX < UINT64_MAX
  a.exact=(char *)"abc";a.end=3;REQUIRE(reader_private_capture_encode(&c,0,2,&bytes,&size)==EXR_OK);
  for(i=24;i<=48;i+=8){reader_rs_record r,before;unsigned char saved[8];memcpy(saved,bytes+i,8);put(bytes,i,(uint64_t)SIZE_MAX+1,8);memset(&r,0xa5,sizeof(r));memcpy(&before,&r,sizeof(r));REQUIRE(reader_private_capture_decode(bytes,size,&r)==EXR_FORMAT&&!memcmp(&r,&before,sizeof(r)));memcpy(bytes+i,saved,8);}
  reader_private_capture_free(bytes);puts("PASS real-size-t-overflow");
#else
  puts("PASS size-t-is-u64-overflow-branch-requires-32bit-job");
#endif
  REQUIRE(reader_private_capture_encode(NULL,0,1,&bytes,&size)==EXR_ARGUMENT);
  REQUIRE(reader_private_capture_decode(NULL,0,(reader_rs_record *)&a)==EXR_ARGUMENT);
  REQUIRE(reader_private_capture_decode("",0,NULL)==EXR_ARGUMENT);
  REQUIRE(reader_private_capture_encode(&c,0,3,&bytes,&size)==EXR_ARGUMENT);
  REQUIRE(alive==0);puts("PASS arguments-and-final-allocation-balance");
  printf("PRIVATE_CAPTURE_OK size_t=%u\n",(unsigned)sizeof(size_t));return 0;
}
