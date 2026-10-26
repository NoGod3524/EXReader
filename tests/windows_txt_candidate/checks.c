#include "bounded_txt.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef struct { const unsigned char *bytes; size_t size; int stop; } memory_source;
static size_t read_at(void *p,uint64_t offset,void *out,size_t n) {
  memory_source *m=p; if (offset>=m->size) return 0;
  if (n>m->size-(size_t)offset) n=m->size-(size_t)offset;
  if (n>11) n=11; /* Exercise short-read retry. */
  memcpy(out,m->bytes+(size_t)offset,n); return n;
}
static int cancelled(void *p) { return ((memory_source *)p)->stop; }
#define CHECK(x) do { if (!(x)) { fprintf(stderr,"check failed at %d: %s (%d %s)\n",__LINE__,#x,error.code,error.message); return 1; } } while (0)
int main(void) {
  char input[4096],joined[4096]; size_t used=0,projected=0,i,n,blocks=0,whole_blocks=0;
  memory_source m={0}; exr_source source={0}; exr_document *whole=NULL,*part=NULL;
  exr_error error={0}; uint64_t cursor=0; const char *text;
  for (i=0;i<513;i++) used+=(size_t)snprintf(input+used,sizeof(input)-used,"x%03zu\n",i);
  m.bytes=(const unsigned char *)input; m.size=used;
  source.size=used; source.read_at=read_at; source.context=&m; source.control.cancelled=cancelled; source.control.context=&m;
  CHECK(exr_document_open_memory(EXR_TXT,input,used,&whole,&error)==EXR_OK);
  exr_document_blocks(whole,&whole_blocks); CHECK(whole_blocks==513);
  while (cursor<source.size) {
    CHECK(bounded_txt_next(&source,&cursor,&part,&error)==EXR_OK && part);
    exr_document_blocks(part,&n); blocks+=n;
    text=exr_document_text(part,&n);
    if (projected && n) joined[projected++]='\n';
    memcpy(joined+projected,text,n); projected+=n;
    exr_document_free(part); part=NULL;
  }
  text=exr_document_text(whole,&n); CHECK(n==projected && !memcmp(text,joined,n) && blocks==whole_blocks);
  exr_document_free(whole);
  m.stop=1; cursor=0; CHECK(bounded_txt_next(&source,&cursor,&part,&error)==EXR_CANCELLED && cursor==0 && !part); m.stop=0;
  m.bytes=(const unsigned char *)"a\r\nb"; m.size=source.size=4; cursor=0;
  CHECK(bounded_txt_next(&source,&cursor,&part,&error)==EXR_UNSUPPORTED && cursor==0 && !part);
  m.bytes=(const unsigned char *)"\xff\xfe"; m.size=source.size=2; cursor=0;
  CHECK(bounded_txt_next(&source,&cursor,&part,&error)==EXR_UNSUPPORTED && cursor==0 && !part);
  m.bytes=(const unsigned char *)"\xff"; m.size=source.size=1; cursor=0;
  CHECK(bounded_txt_next(&source,&cursor,&part,&error)==EXR_ENCODING && cursor==0 && !part);
  puts("projection, short reads, cancellation, encoding rejection and legacy snapshot checks passed");
  return 0;
}
