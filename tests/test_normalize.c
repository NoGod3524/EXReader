/* SPDX-License-Identifier: MIT */
#include "normalize_internal.h"
#include <stdio.h>
static unsigned checks,fixture_line;
static exr_error error;
static unsigned char mentioned[0x110000];
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d (fixture %u): %s (%d: %s)\n",__LINE__,fixture_line,#x,error.code,error.message);exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static size_t sequence(char **text,exr_normal_scalar out[128]) {
  char *p=*text,*end;size_t n=0;
  while(*p && *p!=';') {
    unsigned long cp;while(*p==' ' || *p=='\t') p++;if(*p==';') break;
    cp=strtoul(p,&end,16);CHECK(end!=p && cp<=0x10ffff && n<128);
    out[n]=(exr_normal_scalar){(uint32_t)cp,(unsigned)n,(unsigned)n+1};n++;p=end;
  }
  CHECK(*p==';');*text=p+1;return n;
}
static void conformance(const char *path) {
  FILE *f=fopen(path,"rb");char line[2048];size_t cases=0;CHECK(f);
  while(fgets(line,sizeof(line),f)) {
    exr_normal_scalar values[5][128],out[512],again[2048];size_t counts[5],i,j,n,m;char *p=line;
    fixture_line++;if(line[0]=='#' || line[0]=='@' || line[0]=='\r' || line[0]=='\n') continue;
    for(i=0;i<5;i++) counts[i]=sequence(&p,values[i]);
    if(counts[0]==1) mentioned[values[0][0].cp]=1;
    for(i=0;i<5;i++) {
      size_t target=i<3 ? 1 : 3;unsigned char covered[128]={0};
      OK(exr_normalize_nfc(values[i],counts[i],out,512,&n,NULL,NULL,&error));CHECK(n==counts[target]);
      for(j=0;j<n;j++) {
        size_t k;CHECK(out[j].cp==values[target][j].cp && out[j].first<out[j].last && out[j].last<=counts[i]);
        for(k=out[j].first;k<out[j].last;k++) covered[k]=1;
      }
      for(j=0;j<counts[i];j++) CHECK(covered[j]);
      OK(exr_normalize_nfc(out,n,again,2048,&m,NULL,NULL,&error));CHECK(m==n);
      for(j=0;j<n;j++) CHECK(again[j].cp==out[j].cp && again[j].first==out[j].first && again[j].last==out[j].last);
    }
    cases++;
  }
  CHECK(!ferror(f) && cases==20034);fclose(f);printf("%zu Unicode 17 NFC conformance cases passed\n",cases);
}
static void unlisted(void) {
  uint32_t cp;size_t n,count=0;exr_normal_scalar out[4];
  /* UAX #15: scalars not listed in the conformance corpus must be NFC-stable. */
  for(cp=0;cp<0x110000;cp++) if(!mentioned[cp] && !(cp>=0xd800 && cp<=0xdfff)) {
    exr_normal_scalar in={cp,0,1};OK(exr_normalize_nfc(&in,1,out,4,&n,NULL,NULL,&error));
    CHECK(n==1 && out[0].cp==cp && out[0].first==0 && out[0].last==1);count++;
  }
  printf("%zu unlisted Unicode scalar NFC invariants passed\n",count);
}
static int cancel(void *p) { return ++*(unsigned *)p>=2; }
static void provenance(void) {
  exr_normal_scalar in[]={{'a',0,1},{0x301,1,2},{0x323,2,3},{'b',3,4}},out[1024];size_t n,i;unsigned calls=0;
  exr_control control={cancel,NULL,&calls};exr_normal_scalar hostile[256];
  OK(exr_normalize_nfc(in,4,out,1024,&n,NULL,NULL,&error));CHECK(n==3 && out[0].cp==0x1ea1 && out[0].first==0 && out[0].last==3);
  CHECK(out[1].cp==0x301 && out[1].first==1 && out[1].last==2 && out[2].cp=='b' && out[2].first==3 && out[2].last==4);
  in[0].cp=0x1100;in[1].cp=0x1161;in[2].cp=0x11a8;
  OK(exr_normalize_nfc(in,3,out,1024,&n,NULL,NULL,&error));CHECK(n==1 && out[0].cp==0xac01 && out[0].first==0 && out[0].last==3);
  in[0].cp=0xd800;CHECK(exr_normalize_nfc(in,1,out,1024,&n,NULL,NULL,&error)==EXR_ENCODING && !n);
  in[0].cp='a';CHECK(exr_normalize_nfc(in,1,out,0,&n,NULL,NULL,&error)==EXR_LIMIT && !n);
  CHECK(exr_normalize_nfc(in,1,in,4,&n,NULL,NULL,&error)==EXR_ARGUMENT && !n);
  CHECK(exr_normalize_nfc(in,4097,out,1024,&n,NULL,NULL,&error)==EXR_LIMIT && !n);
  OK(exr_normalize_nfc(NULL,0,NULL,0,&n,NULL,NULL,&error));CHECK(!n);
  { size_t done=64u*1024u*1024u;
    CHECK(exr_normalize_nfc(in,1,out,1024,&n,NULL,&done,&error)==EXR_LIMIT && !n && done==64u*1024u*1024u);
  }
  for(i=0;i<256;i++) hostile[i]=(exr_normal_scalar){i&1 ? 0x323 : 0x301,(unsigned)i,(unsigned)i+1};
  CHECK(exr_normalize_nfc(hostile,256,out,1024,&n,&control,NULL,&error)==EXR_CANCELLED && !n && calls==2);
}
int main(int argc,char **argv) { CHECK(argc==2);conformance(argv[1]);unlisted();provenance();printf("%u canonical normalization checks passed\n",checks);return 0; }
