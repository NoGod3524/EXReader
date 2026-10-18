/* SPDX-License-Identifier: GPL-3.0-only */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static unsigned checks;
static exr_error error;
#define CHECK(x) do { checks++;if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message);exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static exr_hyphenator *create(const char *rules) {
  exr_hyphen_pattern_input input={sizeof(input),"und",rules,strlen(rules),1,1};exr_hyphenator *h=NULL;
  OK(exr_hyphenator_create_patterns(&input,1,0,NULL,&h,&error));return h;
}
static exr_hyphenation *query(exr_hyphenator *h,const char *word) {
  exr_hyphenation *result=NULL;
  OK(exr_hyphenator_query(h,"und",word,strlen(word),NULL,&result,&error));CHECK(result && exr_hyphenation_memory_size(result)>0);return result;
}
static void one(const char *rules,const char *word,size_t point,size_t first,size_t last,const char *before,const char *after) {
  exr_hyphenator *h=create(rules);exr_hyphenation *result=query(h,word);size_t count,i;unsigned char bitmap[1025];
  const exr_hyphen_break *items=exr_hyphenation_breaks(result,&count);
  CHECK(count==1 && items && items[0].point==point && items[0].start==first && items[0].end==last);
  CHECK(items[0].before_size==strlen(before) && items[0].after_size==strlen(after));
  CHECK(!strcmp(items[0].before,before) && !strcmp(items[0].after,after));
  OK(exr_hyphenator_breaks(h,"und",word,strlen(word),bitmap,NULL,&error));
  for(i=0;i<=strlen(word);i++) CHECK(!bitmap[i]);
  exr_hyphenator_free(h); /* Result owns text and survives dictionary/word lifetime. */
  CHECK(!strcmp(items[0].before,before) && !strcmp(items[0].after,after));exr_hyphenation_free(result);
}
static void count(const char *rules,const char *word,size_t expected,int ordinary) {
  exr_hyphenator *h=create(rules);exr_hyphenation *result=query(h,word);size_t n,i;unsigned char bitmap[1025];
  const exr_hyphen_break *items=exr_hyphenation_breaks(result,&n);CHECK(n==expected);
  OK(exr_hyphenator_breaks(h,"und",word,strlen(word),bitmap,NULL,&error));
  for(i=0;i<n;i++) { CHECK(i==0 || items[i-1].point<items[i].point);CHECK(!!bitmap[items[i].point]==ordinary); }
  exr_hyphenation_free(result);exr_hyphenator_free(h);
}
static void native(void) {
  {
    char *rules=malloc(64),*word=malloc(9);exr_hyphenator *h;exr_hyphenation *result;const exr_hyphen_break *items;size_t n;
    CHECK(rules && word);strcpy(rules,".aaaa1aaaa./aa=aaa,4,2");h=create(rules);
    memset(rules,0xff,strlen(rules));free(rules);strcpy(word,"aaaaaaaa");result=query(h,word);
    memset(word,0xff,8);free(word);exr_hyphenator_free(h);
    items=exr_hyphenation_breaks(result,&n);CHECK(n==1 && items[0].point==4 && items[0].start==3 && items[0].end==5);
    CHECK(!strcmp(items[0].before,"aa") && !strcmp(items[0].after,"aaa"));exr_hyphenation_free(result);
  }
  one("a1a/aa=a","aa",1,0,2,"aa","a");
  one(".aaaa1aaaa./aa=aaa,4,2","aaaaaaaa",4,3,5,"aa","aaa");
  one(".aaaa1aaaa./aa=aaa,4,2","AAAAAAAA",4,3,5,"aa","aaa"); /* Literal dictionary text. */
  one("a1a/=,1,1","aa",1,0,1,"","");
  one("a1a/=x,2,0","aa",1,1,1,"","x");
  one("a1a/x=,2,1","aa",1,1,2,"x","");
  one(".é1té./é=t,1,2","été",3,0,4,"é","t");
  one(".a1ﬃ./aa=ﬃ,1,2","affi",1,0,4,"aa","ﬃ");
  count("a1a/aa=a","aaaaaa",5,0);
  count("a1a/aa=a a2a","aaaaaa",0,0);
  count("a2a a3a/aa=a","aaaaaa",5,0);
  count("a1a/aa=a a1a","aaaaaa",5,1);
  count("a1a a1a/aa=a","aaaaaa",5,1);
  count("a1a/aa=a a1a/ab=a","aaaaaa",0,0);
  count("a1a/aa=a a1a/ab=a a3a/aa=a","aaaaaa",5,0);
  count("a1a/aa=a .aa1/ab=a,1,2","aaaaaa",4,0); /* One conflicting source point. */
  count("a1a/aa=a a1","aaaaaa",5,1);
  count("a1 a1a/aa=a","aaaaaa",5,1);
  count("NOHYPHEN aa\nNEXTLEVEL\na1a/aa=a","aaaaaa",0,0);
  count("aaaa1aaaa/aa=aaa,4,2\nNEXTLEVEL", "aaaaaaaa",1,0);
  count("aaaa1aaaa/aa=aa,4,2\nNEXTLEVEL\n.a1aaa/aa=a,1,2", "aaaaaaaa",3,0);
  count("a1a/x=y,1,2", "áa",0,0); /* No pattern match across an unrelated accent. */
  count(".ﬃ1x./f=fx,1,2", "ﬃx",1,0);
  count(".f1ﬁx./f=f,1,2", "ﬃx",0,0); /* Query's folded interior cannot be a break. */
  count(".a1b́./a=b,1,2", "ab́",0,0); /* Rewrite edge cuts a query grapheme. */
  {
    char rules[4096]="a1a/aa=a\n";size_t used=strlen(rules),i;
    for(i=0;i<150;i++) used+=(size_t)snprintf(rules+used,sizeof(rules)-used,"z%cx%cy\n",'a'+(int)(i/26),'a'+(int)(i%26));
    count(rules,"aaaa",3,0); /* Nodes grow after the final replacement rule. */
  }
}
static void case_one(const char *language,const char *rules,const char *word,size_t point,size_t first,size_t last,const char *before,const char *after) {
  exr_hyphen_pattern_input input={sizeof(input),language,rules,strlen(rules),1,1};exr_hyphenator *h=NULL;exr_hyphenation *r=NULL;const exr_hyphen_break *items;size_t n;
  OK(exr_hyphenator_create_patterns_ex(&input,1,0,EXR_HYPHEN_CASE_WORD,NULL,&h,&error));
  OK(exr_hyphenator_query(h,language,word,strlen(word),NULL,&r,&error));items=exr_hyphenation_breaks(r,&n);
  if(n!=1 || strcmp(items[0].before,before) || strcmp(items[0].after,after)) fprintf(stderr,"case %s %s: %zu results, %s=%s, expected %s=%s\n",language,word,n,n ? items[0].before : "",n ? items[0].after : "",before,after);
  CHECK(n==1 && items[0].point==point && items[0].start==first && items[0].end==last);
  CHECK(items[0].before_size==strlen(before) && items[0].after_size==strlen(after));CHECK(!strcmp(items[0].before,before) && !strcmp(items[0].after,after));
  exr_hyphenation_free(r);exr_hyphenator_free(h);
}
static void casing(void) {
  const char *rules=".aaaa1aaaa./ß=ﬃ,4,2";
  case_one("de",rules,"aaaaaaaa",4,3,5,"ß","ﬃ");case_one("de",rules,"AAAAAAAA",4,3,5,"SS","FFI");
  case_one("de",rules,"Aaaaaaaa",4,3,5,"ß","ﬃ");case_one("de",rules,"AaAAaaaa",4,3,5,"ß","ﬃ");
  case_one("de",".aaaa1aaaa./ß=ﬃ,1,5","Aaaaaaaa",4,0,5,"Ss","ﬃ");
  case_one("de",".aaaa1aaaa./=ß,5,0","AAAAAAAA",4,4,4,"","SS");
  case_one("de",".aaaa1aaaa./=ß,5,0","Aaaaaaaa",4,4,4,"","ß");
  case_one("en",".aaaa1aaaa./=,1,5","Aaaaaaaa",4,0,6,"","A");
  case_one("en",".aaaa1ab́cc./=,1,5","Aaaaab́cc",4,0,8,"","B́");
  case_one("en",".aaaa1中中bb./=,1,5","Aaaa中中bb",4,0,11,"","中B");
  case_one("en",".中1abbbb./x=y,2,0","中Abbbb",3,3,4,"X","ya");
  case_one("tr-TR",".ıııı1ıııı./i=ı,4,2","IIIIIIII",4,3,5,"İ","I");
  case_one("az",".ıııı1ıııı./I=İ,4,2","ıııııııı",8,6,10,"ı","i");
  case_one("lt",".aaaa1aaaa./Í=J,4,2","aaaaaaaa",4,3,5,"i̇́","j");
  case_one("lt-LT",".aaaa1aaaa./i̇=j́,4,2","AAAAAAAA",4,3,5,"I","J́");
  case_one("el",".αααα1αααα./Σ=,4,5","αααααααα",8,6,16,"ς","");
  case_one("el",".αααα1αααα./Σ=β,4,5","αααααααα",8,6,16,"σ","β");
  case_one("en",".𐐨𐐨𐐨𐐨1𐐨𐐨𐐨𐐨./𐐨=ß,4,2","𐐀𐐀𐐀𐐀𐐀𐐀𐐀𐐀",16,12,20,"𐐀","SS");
  {
    char rules[300]=".aaaa1aaaa./",*at=rules+strlen(rules);size_t i,n;exr_hyphenator *h=NULL;exr_hyphenation *r=(exr_hyphenation *)1;
    exr_hyphen_pattern_input input={sizeof(input),"de",rules,0,1,1};
    for(i=0;i<128;i++) { *at++=(char)0xc3;*at++=(char)0x9f; }strcpy(at,"=,4,2");input.size=strlen(rules);
    CHECK(exr_hyphenator_create_patterns_ex(&input,1,0,(exr_hyphen_case_policy)99,NULL,&h,&error)==EXR_ARGUMENT && !h);
    OK(exr_hyphenator_create_patterns_ex(&input,1,0,EXR_HYPHEN_CASE_WORD,NULL,&h,&error));
    CHECK(exr_hyphenator_query(h,"de","AAAAAAAA",8,NULL,&r,&error)==EXR_LIMIT && !r);
    OK(exr_hyphenator_query(h,"de","aaaaaaaa",8,NULL,&r,&error));CHECK(exr_hyphenation_breaks(r,&n) && n==1);
    exr_hyphenation_free(r);exr_hyphenator_free(h);
  }
}
static void limits(void) {
  char rules[256]="a1a/",word[257];size_t i,bytes;exr_hyphenator *h=NULL;exr_hyphenation *result;
  exr_hyphen_pattern_input source={sizeof(source),"und",rules,0,1,1};
  memset(rules+4,'b',128);strcpy(rules+132,"=");source.size=strlen(rules);
  OK(exr_hyphenator_create_patterns(&source,1,0,NULL,&h,&error));bytes=exr_hyphenator_memory_size(h);
  memset(word,'a',256);word[256]=0;result=query(h,word);
  { size_t n;const exr_hyphen_break *items=exr_hyphenation_breaks(result,&n);CHECK(n==255 && exr_hyphenation_memory_size(result)<256*1024);
    for(i=0;i<n;i++) CHECK(items[i].point==i+1 && items[i].start==i && items[i].end==i+2 && items[i].before_size==128 && !items[i].after_size);
  }
  exr_hyphenation_free(result);exr_hyphenator_free(h);h=NULL;
  OK(exr_hyphenator_create_patterns(&source,1,bytes,NULL,&h,&error));exr_hyphenator_free(h);h=NULL;
  CHECK(exr_hyphenator_create_patterns(&source,1,bytes-1,NULL,&h,&error)==EXR_LIMIT && !h);
  rules[132]='b';strcpy(rules+133,"=");source.size=strlen(rules);
  CHECK(exr_hyphenator_create_patterns(&source,1,0,NULL,&h,&error)==EXR_LIMIT && !h);
}
typedef struct { int mode,stop,releases;exr_hyphenator *self; } host;
static void release(void *context) { ((host *)context)->releases++; }
static int cancel(void *context) { return ((host *)context)->stop; }
static exr_status provide(void *context,const char *language,const char *word,size_t size,
  exr_hyphen_emit_fn emit,void *sink,const exr_control *control,exr_error *e) {
  host *h=context;char before[]="XY";exr_hyphen_break item={2,1,3,before,"Z",2,1};exr_status status;
  (void)control;CHECK(!strcmp(language,"und"));CHECK(size>=4 && word[0]=='a');
  if(h->mode==1) item.start=3;
  if(h->mode==2) item.before="\xff",item.before_size=1;
  if(h->mode==3) item.before=NULL;
  if(h->mode==4) item.before="\n",item.before_size=1;
  if(h->mode==5) item.point=item.start=item.end=1,item.before_size=item.after_size=0;
  if(h->mode==6) item.point=3,item.start=0,item.end=3;
  if(h->mode==7) item.before_size=513;
  status=emit(sink,&item,e);before[0]='!';
  if(h->mode==8) status=emit(sink,&item,e);
  if(h->mode==9) return (exr_status)100;
  if(h->mode==10) return EXR_IO;
  if(h->mode==11) h->stop=1;
  if(h->mode==12) {
    exr_hyphenation *inner=(exr_hyphenation *)1;
    CHECK(exr_hyphenator_query(h->self,"und",word,size,NULL,&inner,e)==EXR_ARGUMENT && !inner);
  }
  if(h->mode==13) { item=(exr_hyphen_break){1,1,1,NULL,NULL,0,0};return emit(sink,&item,e); }
  (void)status;return EXR_OK; /* Intentionally ignore emit errors: library must latch. */
}
static void providers(void) {
  host h={0};exr_hyphen_discretionary_provider p={sizeof(p),provide,release,&h};exr_hyphenator *native=NULL;
  exr_hyphenation *result;const exr_hyphen_break *items;size_t n;unsigned char bitmap[8];exr_control c={cancel,NULL,&h};
  p.struct_size=0;CHECK(exr_hyphenator_create_discretionary(&p,&native,&error)==EXR_ARGUMENT && !native && !h.releases);
  p.struct_size=sizeof(p);OK(exr_hyphenator_create_discretionary(&p,&native,&error));h.self=native;
  result=query(native,"abcd");items=exr_hyphenation_breaks(result,&n);CHECK(n==1 && !strcmp(items[0].before,"XY"));exr_hyphenation_free(result);
  OK(exr_hyphenator_breaks(native,"und","abcd",4,bitmap,NULL,&error));CHECK(!bitmap[1] && !bitmap[2] && !bitmap[3]);
  for(h.mode=1;h.mode<=4;h.mode++) { result=(exr_hyphenation *)1;CHECK(exr_hyphenator_query(native,"und","abcd",4,NULL,&result,&error)!=EXR_OK && !result); }
  h.mode=5;result=query(native,"abcd");items=exr_hyphenation_breaks(result,&n);CHECK(n==1 && items[0].point==1 && items[0].before_size==0);exr_hyphenation_free(result);
  h.mode=6;result=(exr_hyphenation *)1;CHECK(exr_hyphenator_query(native,"und","áb",4,NULL,&result,&error)==EXR_OK && result);exr_hyphenation_free(result);
  for(h.mode=7;h.mode<=10;h.mode++) { result=(exr_hyphenation *)1;CHECK(exr_hyphenator_query(native,"und","abcd",4,NULL,&result,&error)!=EXR_OK && !result); }
  h.mode=11;result=(exr_hyphenation *)1;CHECK(exr_hyphenator_query(native,"und","abcd",4,&c,&result,&error)==EXR_CANCELLED && !result);h.stop=0;
  h.mode=12;result=query(native,"abcd");exr_hyphenation_free(result);
  h.mode=13;result=query(native,"abcd");items=exr_hyphenation_breaks(result,&n);CHECK(n==2 && items[0].point==1 && items[1].point==2);exr_hyphenation_free(result);
  h.mode=0;result=(exr_hyphenation *)1;CHECK(exr_hyphenator_query(native,"und","áb",4,NULL,&result,&error)==EXR_FORMAT && !result);
  exr_hyphenator_free(native);CHECK(h.releases==1);
}
static void failures(void) {
  const char *bad[]={"a1a/aa", "a1a/a==a", "a1a/a=a,0,2", "a1a/a=a,1", "a1a/a=a,1,2,3", "a1a/a=a,3,1",
    "a1a/a=a,1,99999999", "a1a/a=a,1,-1", "a1a/a=a,1,0", "a1a/a=a,1,1x", "a1a1a/a=a", "a2a/a=a", "./a=a", ".a1a./a=a,1,3", ".e1́a./x=a,1,2", "a1a/\xff=a"};
  size_t i;exr_hyphenator *h=NULL;exr_hyphenation *r=(exr_hyphenation *)1;
  for(i=0;i<sizeof(bad)/sizeof(*bad);i++) {
    exr_hyphen_pattern_input source={sizeof(source),"und",bad[i],strlen(bad[i]),1,1};
    CHECK(exr_hyphenator_create_patterns(&source,1,0,NULL,&h,&error)!=EXR_OK && !h);
  }
  h=create("a1a/aa=a");
  CHECK(exr_hyphenator_query(h,"und","aaaa",1025,NULL,&r,&error)==EXR_LIMIT && !r);
  CHECK(exr_hyphenator_query(h,"und","\xff",1,NULL,&r,&error)==EXR_ENCODING && !r);
  CHECK(exr_hyphenator_query(NULL,"und","aaaa",4,NULL,&r,&error)==EXR_ARGUMENT && !r);
  { size_t n=1;CHECK(!exr_hyphenation_breaks(NULL,&n) && !n && !exr_hyphenation_memory_size(NULL));exr_hyphenation_free(NULL); }
  exr_hyphenator_free(h);
  { exr_hyphen_pattern_input source={sizeof(source),"und","a1a/aa=a",9,1,1};size_t bytes;
    source.size=strlen(source.patterns);OK(exr_hyphenator_create_patterns(&source,1,0,NULL,&h,&error));bytes=exr_hyphenator_memory_size(h);exr_hyphenator_free(h);h=NULL;
    OK(exr_hyphenator_create_patterns(&source,1,bytes,NULL,&h,&error));exr_hyphenator_free(h);h=NULL;
    CHECK(exr_hyphenator_create_patterns(&source,1,bytes-1,NULL,&h,&error)==EXR_LIMIT && !h);
  }
}
int main(void) { native();casing();limits();providers();failures();printf("%u discretionary hyphenation checks passed\n",checks);return 0; }
