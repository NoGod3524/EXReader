/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct { const unsigned char *data;size_t size,chunk,reads,bytes,cancel_after; } input;
static size_t read_at(void *context,uint64_t offset,void *buffer,size_t size) {
  input *in=context;size_t n;
  if(offset>=in->size)return 0;
  n=in->size-(size_t)offset;if(n>size)n=size;if(n>in->chunk)n=in->chunk;
  memcpy(buffer,in->data+(size_t)offset,n);in->reads++;in->bytes+=n;return n;
}
static int cancelled(void *context){input *in=context;return in->cancel_after&&in->reads>=in->cancel_after;}
static void same(exr_document *doc,exr_source *source,const exr_anchor *a) {
  exr_anchor_match reference={0},actual={0};exr_error e={0};exr_status one,two;
  one=exr_anchor_resolve(doc,a,&reference,&e);
  two=exr_txt_anchor_resolve_source(source,a,&actual,&e);
  if(one!=two || reference.state!=actual.state || reference.start!=actual.start || reference.end!=actual.end) {
    fprintf(stderr,"selector mismatch: status %d/%d state %d/%d at %zu/%zu expected %zu/%zu: %s\n",
      (int)one,(int)two,(int)reference.state,(int)actual.state,reference.start,reference.end,actual.start,actual.end,e.message);
    exit(2);
  }
}
static void compare(const unsigned char *from,size_t from_size,const unsigned char *to,size_t to_size,size_t chunk) {
  exr_document *origin=NULL,*target=NULL;exr_error e={0};size_t n=0;
  input in={to,to_size,chunk,0,0,0};exr_source source={0};
  source.size=to_size;source.context=&in;source.read_at=read_at;
  if(exr_document_open_memory(EXR_TXT,from,from_size,&origin,&e)!=EXR_OK ||
     exr_document_open_memory(EXR_TXT,to,to_size,&target,&e)!=EXR_OK) {fprintf(stderr,"open: %s\n",e.message);exit(3);}
  exr_document_text(origin,&n);
  for(size_t start=0;start<=n;start++)for(size_t end=start;end<=n;end++){
    exr_anchor a={0};
    if(exr_anchor_create(origin,start,end,&a,&e)==EXR_OK) {same(target,&source,&a);exr_anchor_free(&a);}
  }
  {
    static const char *exact[]={"","a","ab","z","a\nb","xy"};
    static const char *before[]={"","a","x","aa"};
    static const char *after[]={"","a","y","bb"};
    for(size_t q=0;q<sizeof(exact)/sizeof(*exact);q++)
      for(size_t b=0;b<sizeof(before)/sizeof(*before);b++)
        for(size_t c=0;c<sizeof(after)/sizeof(*after);c++) {
          exr_anchor a={0};a.start=a.end=SIZE_MAX;a.exact=(char *)exact[q];
          a.prefix=(char *)before[b];a.suffix=(char *)after[c];same(target,&source,&a);
        }
  }
  exr_document_free(origin);exr_document_free(target);
}
int main(void) {
  static const unsigned char a[]="a\nb a\nb aa\nxy";
  static const unsigned char b[]="x a\nb a\nb z\nxy";
  static const unsigned char u8[]=" " "\xe4\xb8\xad" " \r\n\n" "\xf0\x9f\x98\x80" "\nx";
  static const unsigned char u16[]={0xff,0xfe,' ',0,0x3d,0xd8,0,0xde,' ',0,'\r',0,'\n',0,'x',0};
  static const unsigned char broken[]={'x',' ',0xff};
  for(size_t chunk=1;chunk<=7;chunk++) {
    compare(a,sizeof(a)-1,a,sizeof(a)-1,chunk);
    compare(a,sizeof(a)-1,b,sizeof(b)-1,chunk);
    compare(u8,sizeof(u8)-1,u8,sizeof(u8)-1,chunk);
    compare(u16,sizeof(u16),u16,sizeof(u16),chunk);
  }
  {
    input in={broken,sizeof(broken),2,0,0,0};exr_source source={0};exr_anchor anchor={0};exr_anchor_match match={0};exr_error e={0};
    source.size=in.size;source.context=&in;source.read_at=read_at;
    anchor.start=anchor.end=SIZE_MAX;anchor.exact="x";anchor.prefix="";anchor.suffix="";
    if(exr_txt_anchor_resolve_source(&source,&anchor,&match,&e)!=EXR_ENCODING ||
       match.state!=EXR_ANCHOR_MISSING || match.start!=SIZE_MAX || match.end!=SIZE_MAX)return 4;
  }
  {
    size_t size=8u*1024u*1024u,pos=size/2+30;unsigned char *data=malloc(size);
    input in;exr_source source={0};exr_anchor anchor={0};exr_anchor_match match={0};exr_error e={0};
    if(!data)return 5;
    for(size_t i=0;i<size;i++)data[i]=(i%1024==1023)?'\n':'a';
    memcpy(data+pos,"UniqueNeedle",12);
    in=(input){data,size,4096,0,0,0};source.size=size;source.context=&in;source.read_at=read_at;
    source.control.context=&in;source.control.cancelled=cancelled;
    anchor.start=anchor.end=SIZE_MAX;anchor.exact="UniqueNeedle";anchor.prefix="aaaa";anchor.suffix="aaaa";
    if(exr_txt_anchor_resolve_source(&source,&anchor,&match,&e)!=EXR_OK ||
       match.state!=EXR_ANCHOR_FOUND || match.start!=pos || match.end!=pos+12 || in.bytes>size+4096) {
      fprintf(stderr,"large resolve: %s offset %zu bytes %zu\n",e.message,match.start,in.bytes);return 6;
    }
    in.reads=in.bytes=0;in.cancel_after=2;match.start=0;match.end=0;
    if(exr_txt_anchor_resolve_source(&source,&anchor,&match,&e)!=EXR_CANCELLED ||
       match.state!=EXR_ANCHOR_MISSING || match.start!=SIZE_MAX || match.end!=SIZE_MAX)return 7;
    free(data);
  }
  puts("TXT anchor matches public resolver, bounded scan and cancellation");
  return 0;
}
