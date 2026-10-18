/* SPDX-License-Identifier: GPL-3.0-only */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static unsigned checks;
static exr_error error;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static exr_hyphen_pattern_input input(const char *language,const char *text,unsigned left,unsigned right) {
  exr_hyphen_pattern_input i={sizeof(i),language,text,strlen(text),left,right}; return i;
}
static exr_hyphenator *create(const char *language,const char *text,unsigned left,unsigned right) {
  exr_hyphen_pattern_input i=input(language,text,left,right); exr_hyphenator *h=NULL;
  OK(exr_hyphenator_create_patterns(&i,1,0,NULL,&h,&error)); CHECK(h && exr_hyphenator_memory_size(h)>0); return h;
}
static void breaks(exr_hyphenator *h,const char *lang,const char *word,size_t first,size_t second) {
  size_t size=strlen(word),i; unsigned char map[1025]; memset(map,0xff,sizeof(map));
  OK(exr_hyphenator_breaks(h,lang,word,size,map,NULL,&error));
  for(i=0;i<=size;i++) { if(map[i]!=(i==first || i==second)) fprintf(stderr,"%s / %s: byte %zu got %u\n",lang ? lang : "",word,i,map[i]); CHECK(map[i]==(i==first || i==second)); }
}
static void basic(void) {
  exr_hyphenator *h=create("en","UTF-8\nLEFTHYPHENMIN 2\nRIGHTHYPHENMIN 2\nhy1phen phen1ation % comment\n# other comment\n",0,0);
  breaks(h,"EN-US","hyphenation",2,6); breaks(h,"en-x-custom","HYPHENATION",2,6); breaks(h,"fr","hyphenation",SIZE_MAX,SIZE_MAX);
  breaks(h,"en","",SIZE_MAX,SIZE_MAX); exr_hyphenator_free(h);
  h=create("en","a1b a2b",1,1); breaks(h,"en","ab",SIZE_MAX,SIZE_MAX); exr_hyphenator_free(h);
  h=create("en",".ab3cd.",1,1); breaks(h,"en","abcd",2,SIZE_MAX); breaks(h,"en","xabcd",SIZE_MAX,SIZE_MAX); exr_hyphenator_free(h);
  h=create("en","ab1cd\nLEFTHYPHENMIN 3",0,1); breaks(h,"en","abcd",SIZE_MAX,SIZE_MAX); exr_hyphenator_free(h);
  h=create("en","ab1cd\nLEFTHYPHENMIN 3",1,1); breaks(h,"en","abcd",2,SIZE_MAX); exr_hyphenator_free(h);
  { exr_hyphen_pattern_input a[]={input("en","ab1cd",1,1),input("de","abc1d",1,1),input(NULL,"a1bcd",1,1)};
    OK(exr_hyphenator_create_patterns(a,3,0,NULL,&h,&error)); breaks(h,"de-DE-1996","abcd",3,SIZE_MAX);
    breaks(h,NULL,"abcd",1,SIZE_MAX); breaks(h,"zh-Hant","abcd",SIZE_MAX,SIZE_MAX); exr_hyphenator_free(h);
  }
}
static void unicode(void) {
  exr_hyphenator *h=create("fr",".é1té.",1,1); breaks(h,"fr-CA","ÉTÉ",2,SIZE_MAX); breaks(h,"fr","ÉTÉ",3,SIZE_MAX); exr_hyphenator_free(h);
  h=create("el",".ο1ς.",1,1); breaks(h,"el","ΟΣ",2,SIZE_MAX); breaks(h,"el","ος",2,SIZE_MAX); exr_hyphenator_free(h);
  h=create("tr",".ı1a. .i1b.",1,1); breaks(h,"tr-TR","Ia",1,SIZE_MAX); breaks(h,"tr","İb",2,SIZE_MAX); exr_hyphenator_free(h);
  h=create("de","mas1se",1,1); breaks(h,"de","Maße",SIZE_MAX,SIZE_MAX); breaks(h,"de","MASSE",3,SIZE_MAX); exr_hyphenator_free(h);
  h=create("de","mass1e",1,1); breaks(h,"de","Maße",4,SIZE_MAX); exr_hyphenator_free(h);
  h=create("he","שָ1לו",1,1); breaks(h,"he-IL","שָלו",4,SIZE_MAX); exr_hyphenator_free(h);
  h=create("he","ש1ָלו",1,1); breaks(h,"he","שָלו",SIZE_MAX,SIZE_MAX); exr_hyphenator_free(h);
  h=create("xx","👩1‍💻",1,1); breaks(h,"xx","👩‍💻",SIZE_MAX,SIZE_MAX); exr_hyphenator_free(h);
}
static void canonical(void) {
  exr_hyphenator *h=create("fr",".é1té.",1,1);
  breaks(h,"fr","été",2,SIZE_MAX);breaks(h,"fr","été",3,SIZE_MAX);exr_hyphenator_free(h);
  h=create("fr",".é1x. .é2x.",1,1);breaks(h,"fr","éx",SIZE_MAX,SIZE_MAX);exr_hyphenator_free(h);
  h=create("fr",".e1́x.",1,1);breaks(h,"fr","éx",SIZE_MAX,SIZE_MAX);breaks(h,"fr","éx",SIZE_MAX,SIZE_MAX);exr_hyphenator_free(h);
  h=create("xx",".ạ́1x.",1,1);breaks(h,"xx","ạ́x",5,SIZE_MAX);exr_hyphenator_free(h);
  h=create("xx",".ạ́1x.",1,1);breaks(h,"xx","ạ́x",5,SIZE_MAX);exr_hyphenator_free(h);
  h=create("ko",".가1나.",1,1);breaks(h,"ko","가나",6,SIZE_MAX);exr_hyphenator_free(h);
  h=create("hi",".क़1x.",1,1);breaks(h,"hi","क़x",3,SIZE_MAX);exr_hyphenator_free(h);
  h=create("tr",".i1b.",1,1);breaks(h,"tr","İb",3,SIZE_MAX);breaks(h,"tr","İb",2,SIZE_MAX);exr_hyphenator_free(h);
  h=create("el",".ΐ1x.",1,1);breaks(h,"el","Ϊ́x",6,SIZE_MAX);exr_hyphenator_free(h);
  h=create("en",".ﬃ1x.",1,1);breaks(h,"en","FFIx",3,SIZE_MAX);breaks(h,"en","ﬃx",3,SIZE_MAX);exr_hyphenator_free(h);
  { char word[769];unsigned char out[769];size_t i;
    h=create("und","ffi1ffi",1,1);
    for(i=0;i<256;i++) memcpy(word+3*i,"ﬃ",3);word[768]=0;
    OK(exr_hyphenator_breaks(h,"und",word,768,out,NULL,&error));
    for(i=0;i<=768;i++) CHECK(out[i]==(i && i<768 && i%3==0));
    for(i=0;i<256;i++) memcpy(word+3*i,"ᾯ",3);
    OK(exr_hyphenator_breaks(h,"und",word,768,out,NULL,&error));for(i=0;i<=768;i++) CHECK(!out[i]);
    exr_hyphenator_free(h);
  }
}

static void marked(const char *rules,const char *word,const char *expected) {
  exr_hyphenator *h=create("und",rules,0,0);unsigned char map[1025],wanted[1025]={0};size_t i,at=0,size=strlen(word);
  for(i=0;expected[i];i++) if(expected[i]=='*') wanted[at]=1;else { CHECK(at<size && word[at]==expected[i]);at++; }
  CHECK(at==size);OK(exr_hyphenator_breaks(h,"und",word,size,map,NULL,&error));
  for(i=0;i<=size;i++) { if(map[i]!=wanted[i]) fprintf(stderr,"compound %s: byte %zu got %u\n",word,i,map[i]);CHECK(map[i]==wanted[i]); }
  exr_hyphenator_free(h);
}
static void compounds(void) {
  marked("abcd1efgh\nNEXTLEVEL\n.ab1cd.\n.ef1gh.","abcdefgh","ab*cd*ef*gh");
  marked("abcd1efgh\nNEXTLEVEL\n.abcdefgh2.","abcdefgh","abcd*efgh");
  marked("LEFTHYPHENMIN 1\nRIGHTHYPHENMIN 1\n.abcd1efgh.\n.ab1cd.\nNEXTLEVEL\n.e1fgh.","abcdefgh","ab*cd*e*fgh");
  marked("LEFTHYPHENMIN 1\nRIGHTHYPHENMIN 2\nNEXTLEVEL\na1","ab","ab");
  marked("LEFTHYPHENMIN 1\nRIGHTHYPHENMIN 1\nCOMPOUNDRIGHTHYPHENMIN 2\nabcd1efgh\n.ab1cd.\nNEXTLEVEL\na1\nb1\ne1\nf1\ng1","abcdefgh","ab*cd*e*f*g*h");
  marked("COMPOUNDLEFTHYPHENMIN 3\nCOMPOUNDRIGHTHYPHENMIN 3\nabcd1efgh\nNEXTLEVEL\n.ab1cd.\n.ef1gh.","abcdefgh","abcd*efgh");
  marked("LEFTHYPHENMIN 5\nabcd1efgh\nNEXTLEVEL\n.ab1cd.\n.ef1gh.","abcdefgh","abcdef*gh");
  marked("a1","aaaa'aaaa","aaaa'aaaa");
  marked("LEFTHYPHENMIN 1\nRIGHTHYPHENMIN 1\na1","aaaa'aaaa","a*a*a*a'a*a*a*a");
  marked("LEFTHYPHENMIN 1\nRIGHTHYPHENMIN 1\na1","aaaa-aaaa","a*a*a*a-a*a*a*a");
  marked("LEFTHYPHENMIN 1\nRIGHTHYPHENMIN 1\na1","aaaa–aaaa","a*a*a*a–a*a*a*a");
  marked("LEFTHYPHENMIN 1\nRIGHTHYPHENMIN 1\na1","aaaa’aaaa","a*a*a*a’a*a*a*a");
  marked("LEFTHYPHENMIN 1\nRIGHTHYPHENMIN 1\nNOHYPHEN xy\nNEXTLEVEL\na1\nb1\nx1\ny1\nc1","abxycd","a*bx*yc*d");
  marked("LEFTHYPHENMIN 1\nRIGHTHYPHENMIN 1\nNOHYPHEN aa\nNEXTLEVEL\na1","aaaaaa","aaaaaa");
  marked("LEFTHYPHENMIN 1\nRIGHTHYPHENMIN 1\nNOHYPHEN x\nNOHYPHEN y\nNEXTLEVEL\na1\nb1\nx1\ny1\nc1","abxycd","a*b*xyc*d");
  marked("LEFTHYPHENMIN 1\nRIGHTHYPHENMIN 1\nNEXTLEVEL\nLEFTHYPHENMIN 5\nNOHYPHEN a\na1","aaaaaa","a*a*a*a*a*a");
  marked("LEFTHYPHENMIN 0\nRIGHTHYPHENMIN 0\na1","aaaaaa","aa*a*a*aa");
  marked("LEFTHYPHENMIN 1\nRIGHTHYPHENMIN 1\nNOHYPHEN é\nNEXTLEVEL\na1\né1","aéa","aéa");
}

static int compound_cancel(void *context) { return ++*(unsigned *)context>=2; }
static void compound_limits(void) {
  char word[257],rules[512];unsigned char out[257];size_t i,n=0,bytes;unsigned calls=0;exr_hyphenator *h=NULL;
  exr_control control={compound_cancel,NULL,&calls};exr_hyphen_pattern_input source;
  memset(word,'a',256);word[256]=0;
  h=create("und","LEFTHYPHENMIN 1\nRIGHTHYPHENMIN 1\n.a1\nNEXTLEVEL\na1",0,0);
  OK(exr_hyphenator_breaks(h,"und",word,256,out,NULL,&error));for(i=0;i<=256;i++) CHECK(out[i]==(i && i<256));
  CHECK(exr_hyphenator_breaks(h,"und",word,256,out,&control,&error)==EXR_CANCELLED && calls==2);
  for(i=0;i<=256;i++) CHECK(!out[i]);
  OK(exr_hyphenator_breaks(h,"und",word,256,out,NULL,&error));CHECK(out[128]);exr_hyphenator_free(h);
  n=(size_t)snprintf(rules,sizeof(rules),"NOHYPHEN ");
  for(i=0;i<64;i++) { if(i) rules[n++]=',';rules[n++]='a'; }
  strcpy(rules+n,"\nNEXTLEVEL\na1");h=create("und",rules,0,0);bytes=exr_hyphenator_memory_size(h);exr_hyphenator_free(h);h=NULL;
  source=input("und",rules,0,0);OK(exr_hyphenator_create_patterns(&source,1,bytes,NULL,&h,&error));exr_hyphenator_free(h);h=NULL;
  CHECK(exr_hyphenator_create_patterns(&source,1,bytes-1,NULL,&h,&error)==EXR_LIMIT && !h);
  rules[n++]=',';rules[n++]='a';strcpy(rules+n,"\nNEXTLEVEL\na1");source=input("und",rules,0,0);
  CHECK(exr_hyphenator_create_patterns(&source,1,0,NULL,&h,&error)==EXR_LIMIT && !h);
  marked("LEFTHYPHENMIN 1\nRIGHTHYPHENMIN 1\nNOHYPHEN a\nNOHYPHEN\nNEXTLEVEL\na1","aaaa","a*a*a*a");
  source=input("und","UTF-16\na1",1,1);CHECK(exr_hyphenator_create_patterns(&source,1,0,NULL,&h,&error)==EXR_UNSUPPORTED && !h);
  n=(size_t)snprintf(rules,sizeof(rules),"NOHYPHEN ");memset(rules+n,'a',128);strcpy(rules+n+128,"\nNEXTLEVEL\na1");
  h=create("und",rules,1,1);OK(exr_hyphenator_breaks(h,"und",word,256,out,NULL,&error));for(i=0;i<=256;i++) CHECK(!out[i]);exr_hyphenator_free(h);h=NULL;
  memset(rules+n,'a',129);strcpy(rules+n+129,"\nNEXTLEVEL\na1");source=input("und",rules,1,1);
  CHECK(exr_hyphenator_create_patterns(&source,1,0,NULL,&h,&error)==EXR_LIMIT && !h);
  source=input("und","NOHYPHEN \xff\nNEXTLEVEL\na1",1,1);CHECK(exr_hyphenator_create_patterns(&source,1,0,NULL,&h,&error)==EXR_ENCODING && !h);
}

typedef struct { unsigned calls,releases; int mode,stop; exr_hyphenator *self; } host;
static exr_status provider(void *context,const char *language,const char *word,size_t size,unsigned char *out,const exr_control *control,exr_error *e) {
  host *s=context; (void)word; (void)control; (void)e; s->calls++; CHECK(!strcmp(language,"en-us"));
  if(size) out[1]=1;
  if(s->mode==1) return EXR_IO;
  if(s->mode==2) out[1]=2;
  if(s->mode==3) s->stop=1;
  if(s->mode==4) { unsigned char inner[4]={9,9,9,9}; CHECK(exr_hyphenator_breaks(s->self,"en","abc",3,inner,NULL,e)==EXR_ARGUMENT); CHECK(!inner[0] && !inner[1] && !inner[2] && !inner[3]); }
  if(s->mode==5) return (exr_status)100;
  return EXR_OK;
}
static void release(void *context) { ((host *)context)->releases++; }
static int cancelled(void *context) { return ((host *)context)->stop; }
static void progress(void *context,exr_stage stage,uint64_t completed,uint64_t total) {
  host *s=context; (void)stage; (void)completed; (void)total; if(++s->calls==3) s->stop=1;
}
static void providers(void) {
  host s={0}; exr_hyphen_provider p={sizeof(p),provider,release,&s}; exr_hyphenator *h=NULL; unsigned char out[5];
  exr_control c={cancelled,NULL,&s};
  p.struct_size=0; CHECK(exr_hyphenator_create(&p,&h,&error)==EXR_ARGUMENT && !h && !s.releases); p.struct_size=sizeof(p);
  OK(exr_hyphenator_create(&p,&h,&error)); s.self=h; breaks(h,"EN-US","abcd",1,SIZE_MAX); CHECK(s.calls==1);
  { exr_hyphenation *result=NULL;size_t n;const exr_hyphen_break *items;
    OK(exr_hyphenator_query(h,"EN-US","abcd",4,NULL,&result,&error));items=exr_hyphenation_breaks(result,&n);
    CHECK(n==1 && items[0].point==1 && items[0].start==1 && items[0].end==1 && !items[0].before_size && !items[0].after_size);
    exr_hyphenation_free(result);
  }
  s.mode=1; CHECK(exr_hyphenator_breaks(h,"en-US","abcd",4,out,NULL,&error)==EXR_IO); CHECK(!out[0] && !out[1] && !out[2] && !out[3] && !out[4]);
  s.mode=2; CHECK(exr_hyphenator_breaks(h,"en-US","abcd",4,out,NULL,&error)==EXR_FORMAT && !out[1]);
  s.mode=0; CHECK(exr_hyphenator_breaks(h,"en-US","éé",4,out,NULL,&error)==EXR_FORMAT && !out[1]);
  breaks(h,"en-US","áb",SIZE_MAX,SIZE_MAX); /* Provider boundary is inside a grapheme. */
  s.mode=3; CHECK(exr_hyphenator_breaks(h,"en-US","abcd",4,out,&c,&error)==EXR_CANCELLED && !out[1]); s.stop=0;
  s.mode=4; breaks(h,"en-us","abcd",1,SIZE_MAX);
  s.mode=5; CHECK(exr_hyphenator_breaks(h,"en-US","abcd",4,out,NULL,&error)==EXR_FORMAT && !out[1]);
  exr_hyphenator_free(h); CHECK(s.releases==1);
}
static void failures(void) {
  const char *invalid[]={"a11b","12","a/b","\\patterns{a1b}","NEXTLEVEL NEXTLEVEL","COMPOUNDLEFTHYPHENMIN x","NOHYPHEN -,,x","NOHYPHEN -,","LEFTHYPHENMIN","RIGHTHYPHENMIN x","UTF-8\na1\xff"};
  size_t j; exr_hyphenator *h=NULL; exr_hyphen_pattern_input i=input("en","a1b",1,1); unsigned char out[1025]; char large[1026];
  for(j=0;j<sizeof(invalid)/sizeof(*invalid);j++) { i=input("en",invalid[j],1,1); CHECK(exr_hyphenator_create_patterns(&i,1,0,NULL,&h,&error)!=EXR_OK && !h && error.message[0]); }
  i=input("en","a1b",1,1); CHECK(exr_hyphenator_create_patterns(&i,1,1,NULL,&h,&error)==EXR_LIMIT && !h);
  { exr_hyphen_pattern_input a[]={i,input("EN","b1c",1,1)}; CHECK(exr_hyphenator_create_patterns(a,2,0,NULL,&h,&error)==EXR_ARGUMENT && !h); }
  i.size=SIZE_MAX; CHECK(exr_hyphenator_create_patterns(&i,1,0,NULL,&h,&error)==EXR_LIMIT && !h);
  i=input("en_US","a1b",1,1); CHECK(exr_hyphenator_create_patterns(&i,1,0,NULL,&h,&error)==EXR_ARGUMENT && !h);
  memset(large,'a',sizeof(large)); large[129]=0; i=input("en",large,1,1); CHECK(exr_hyphenator_create_patterns(&i,1,0,NULL,&h,&error)==EXR_LIMIT && !h);
  h=create("en","a1b",1,1);
  CHECK(exr_hyphenator_breaks(h,"en","\xff",1,out,NULL,&error)==EXR_ENCODING && !out[0] && !out[1]);
  memset(large,'a',sizeof(large)); CHECK(exr_hyphenator_breaks(h,"en",large,1025,out,NULL,&error)==EXR_LIMIT);
  CHECK(exr_hyphenator_breaks(h,"en",large,257,out,NULL,&error)==EXR_LIMIT && !out[1]);
  exr_hyphenator_free(h); h=NULL;
  { host s={0}; exr_control c={cancelled,progress,&s}; i=input("en","a1b b1c c1d d1e",1,1); CHECK(exr_hyphenator_create_patterns(&i,1,0,&c,&h,&error)==EXR_CANCELLED && !h && s.stop); }
  { char *hostile=malloc(100001); size_t at=0; CHECK(hostile);
    for(j=0;j<20000;j++) { unsigned cp=0x4e00+(unsigned)j; hostile[at++]=(char)(0xe0|(cp>>12)); hostile[at++]=(char)(0x80|((cp>>6)&63)); hostile[at++]=(char)(0x80|(cp&63)); hostile[at++]='1'; hostile[at++]='\n'; }
    hostile[at]=0; i=input("xx",hostile,1,1); CHECK(exr_hyphenator_create_patterns(&i,1,0,NULL,&h,&error)==EXR_LIMIT && !h && strstr(error.message,"work limit")); free(hostile);
  }
}
/* Independent, slow pattern overlay oracle, with no trie or packed edges. */
static uint32_t random_value(uint32_t *s) { *s=*s*1664525u+1013904223u; return *s; }
static void generated(void) {
  uint32_t seed=180324; unsigned round;
  for(round=0;round<100;round++) {
    char patterns[4096]={0},letters[60][8]; unsigned char weights[60][9]; size_t lengths[60],used=0,i,j,k;
    exr_hyphenator *h;
    for(i=0;i<60;i++) {
      lengths[i]=1+random_value(&seed)%7;
      for(j=0;j<=lengths[i];j++) {
        weights[i][j]=(unsigned char)(random_value(&seed)%10); patterns[used++]=(char)('0'+weights[i][j]);
        if(j<lengths[i]) { letters[i][j]=(char)('a'+random_value(&seed)%3); patterns[used++]=letters[i][j]; }
      }
      patterns[used++]='\n';
    }
    h=create("en",patterns,1,1);
    for(i=0;i<300;i++) {
      char word[20]; unsigned char expected[20]={0},actual[20]; size_t n=2+random_value(&seed)%14;
      for(j=0;j<n;j++) word[j]=(char)('a'+random_value(&seed)%3); word[n]=0;
      for(j=0;j<60;j++) for(k=0;k+lengths[j]<=n;k++) if(!memcmp(word+k,letters[j],lengths[j])) {
        size_t m; for(m=0;m<=lengths[j];m++) if(weights[j][m]>expected[k+m]) expected[k+m]=weights[j][m];
      }
      for(j=0;j<=n;j++) expected[j]=(unsigned char)(j && j<n ? expected[j]&1 : 0);
      OK(exr_hyphenator_breaks(h,"EN-US",word,n,actual,NULL,&error)); for(j=0;j<=n;j++) CHECK(expected[j]==actual[j]);
    }
    exr_hyphenator_free(h);
  }
}
int main(void) { basic(); unicode(); canonical(); compounds(); compound_limits(); providers(); failures(); generated(); printf("%u hyphenation dictionary checks passed\n",checks); return 0; }
