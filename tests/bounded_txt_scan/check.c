#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct { const unsigned char *data; size_t size, chunk, reads, cancel_after; } input;
typedef struct { char *data; size_t size, capacity; } output;
static size_t read_at(void *ctx,uint64_t at,void *buffer,size_t size) {
  input *in=ctx; size_t n=in->size-(size_t)at; in->reads++;
  if(n>size) n=size; if(n>in->chunk) n=in->chunk;
  memcpy(buffer,in->data+(size_t)at,n);return n;
}
static int cancelled(void *ctx) { input *in=ctx;return in->cancel_after && in->reads>=in->cancel_after; }
static exr_status collect(void *ctx,uint64_t offset,const char *text,size_t size,exr_error *error) {
  output *out=ctx;size_t need=(size_t)offset+size;char *next;(void)error;
  if(offset!=(out->size ? out->size+1 : 0)) return EXR_FORMAT;
  if(need>out->capacity) { next=realloc(out->data,need);if(!next) return EXR_MEMORY;out->data=next;out->capacity=need; }
  if(out->size) out->data[out->size]='\n';memcpy(out->data+(size_t)offset,text,size);out->size=need;return EXR_OK;
}
static void check(const unsigned char *data,size_t size,size_t chunk) {
  input in={data,size,chunk,0,0};output out={0};exr_source source={0};exr_document *doc=NULL;exr_error error={0};
  uint64_t extent=0;size_t expected_size=0;const char *expected;
  source.size=size;source.read_at=read_at;source.context=&in;source.control.cancelled=cancelled;source.control.context=&in;
  if(exr_document_open_memory(EXR_TXT,data,size,&doc,&error)!=EXR_OK) { fprintf(stderr,"snapshot: %s\n",error.message);exit(1); }
  expected=exr_document_text(doc,&expected_size);
  if(exr_txt_scan_source(&source,collect,&out,&extent,&error)!=EXR_OK || extent!=expected_size || out.size!=expected_size || (expected_size && memcmp(expected,out.data,expected_size))) {
    fprintf(stderr,"projection mismatch: %s\n",error.message);exit(1);
  }
  {
    size_t start,end;
    for(start=0;start<=expected_size;start++) for(end=start;end<=expected_size;end++) {
      exr_anchor a={0},b={0};exr_status x,y;
      x=exr_anchor_create(doc,start,end,&a,&error);
      y=exr_txt_anchor_create_source(&source,start,end,&b,&error);
      if(x!=y || (x==EXR_OK && (a.start!=b.start || a.end!=b.end ||
         strcmp(a.exact,b.exact) || strcmp(a.prefix,b.prefix) || strcmp(a.suffix,b.suffix)))) {
        fprintf(stderr,"anchor mismatch at %zu..%zu: %d vs %d %s\n",start,end,x,y,error.message);exit(9);
      }
      exr_anchor_free(&a);exr_anchor_free(&b);
    }
  }
  {
    exr_txt_cursor *cursor=NULL;exr_txt_checkpoint mark;uint64_t at,again;
    const char *text;size_t n,copy_size;char *copy;
    if(exr_txt_cursor_create(&source,&cursor,&error)!=EXR_OK ||
       exr_txt_cursor_next(cursor,&at,&text,&n,&error)!=EXR_OK || !text ||
       exr_txt_cursor_checkpoint(cursor,&mark,&error)!=EXR_OK ||
       exr_txt_cursor_next(cursor,&at,&text,&n,&error)!=EXR_OK || !text) exit(11);
    copy_size=n;copy=malloc(n);if(!copy) exit(12);memcpy(copy,text,n);
    if(exr_txt_cursor_restore(cursor,&mark,&error)!=EXR_OK ||
       exr_txt_cursor_next(cursor,&again,&text,&n,&error)!=EXR_OK ||
       again!=at || n!=copy_size || memcmp(copy,text,n)) exit(13);
    free(copy);exr_txt_cursor_free(cursor);
  }
  free(out.data);exr_document_free(doc);
}
static size_t file_read(void *ctx,uint64_t at,void *buffer,size_t size) {
  FILE *file=ctx;
#ifdef _WIN32
  if(_fseeki64(file,(int64_t)at,SEEK_SET)) return 0;
#else
  if(fseek(file,(long)at,SEEK_SET)) return 0;
#endif
  return fread(buffer,1,size,file);
}
static exr_status count_paragraph(void *ctx,uint64_t offset,const char *text,size_t size,exr_error *error) {
  size_t *count=ctx;(void)offset;(void)text;(void)size;(void)error;(*count)++;return EXR_OK;
}
int main(int argc,char **argv) {
  static const unsigned char utf8[]={0xef,0xbb,0xbf,' ',0xe4,0xb8,0xad,' ', '\r','\n','\n','x','\r','y','\t','\n'};
  static const unsigned char utf16[]={0xff,0xfe,' ',0,0x3d,0xd8,0x00,0xde,' ',0,'\r',0,'\n',0,'x',0};
  static const unsigned char bad[]={0xff,0xfe,0x00};
  input in={bad,sizeof(bad),1,0,0};output out={0};exr_source source={0};exr_error error={0};uint64_t extent=42;size_t i;
  for(i=1;i<=5;i++) { check(utf8,sizeof(utf8),i);check(utf16,sizeof(utf16),i); }
  {
    unsigned char long_text[300];
    for(i=0;i<sizeof(long_text);i+=4) { long_text[i]=0xf0;long_text[i+1]=0x9f;long_text[i+2]=0x98;long_text[i+3]=0x80; }
    {
      input v={long_text,sizeof(long_text),7,0,0};exr_source s={0};exr_document *d=NULL;
      exr_anchor a={0},b={0};
      s.size=v.size;s.read_at=read_at;s.context=&v;
      if(exr_document_open_memory(EXR_TXT,long_text,sizeof(long_text),&d,&error)!=EXR_OK ||
         exr_anchor_create(d,140,144,&a,&error)!=EXR_OK ||
         exr_txt_anchor_create_source(&s,140,144,&b,&error)!=EXR_OK ||
         strcmp(a.exact,b.exact) || strcmp(a.prefix,b.prefix) || strcmp(a.suffix,b.suffix) ||
         strlen(b.prefix)!=128 || strlen(b.suffix)!=128) return 10;
      exr_anchor_free(&a);exr_anchor_free(&b);exr_document_free(d);
    }
  }
  source.size=in.size;source.read_at=read_at;source.context=&in;source.control.cancelled=cancelled;source.control.context=&in;
  if(exr_txt_scan_source(&source,collect,&out,&extent,&error)!=EXR_ENCODING || extent) return 2;
  in.data=utf8;in.size=sizeof(utf8);source.size=in.size;in.reads=0;in.cancel_after=4;extent=42;
  if(exr_txt_scan_source(&source,collect,&out,&extent,&error)!=EXR_CANCELLED || extent) return 3;
  free(out.data);
  {
    static const unsigned char text[]="first line\nsecond line\nthird";
    input search_input={text,sizeof(text)-1,2,0,0};exr_source search_source={0};
    uint64_t start,end;
    search_source.size=search_input.size;search_source.read_at=read_at;search_source.context=&search_input;
    if(exr_txt_find_source(&search_source,"line\nsecond",0,&start,&end,&error)!=EXR_OK || start!=6 || end!=17) return 6;
    if(exr_txt_find_source(&search_source,"line",7,&start,&end,&error)!=EXR_OK || start!=18 || end!=22) return 7;
    if(exr_txt_find_source(&search_source,"missing",0,&start,&end,&error)!=EXR_OK || start!=UINT64_MAX || end!=UINT64_MAX) return 8;
  }
  if(argc>1) {
    FILE *file=fopen(argv[1],"rb");size_t count=0;exr_source large={0};
    if(!file) return 4;
    large.size=16792975;large.read_at=file_read;large.context=file;
    if(exr_txt_scan_source(&large,count_paragraph,&count,&extent,&error)!=EXR_OK || count!=212895) {
      fprintf(stderr,"large scan failed: %s count=%zu\n",error.message,count);fclose(file);return 5;
    }
    {
      exr_txt_cursor *cursor=NULL;exr_txt_checkpoint mark;uint64_t offset,again;
      const char *text;size_t n,j,copy_size;char *copy;
      if(exr_txt_cursor_create(&large,&cursor,&error)!=EXR_OK) return 14;
      for(j=0;j<100000;j++)
        if(exr_txt_cursor_next(cursor,&offset,&text,&n,&error)!=EXR_OK || !text) return 15;
      if(exr_txt_cursor_checkpoint(cursor,&mark,&error)!=EXR_OK ||
         exr_txt_cursor_next(cursor,&offset,&text,&n,&error)!=EXR_OK || !text) return 16;
      copy_size=n;copy=malloc(n);if(!copy) return 17;memcpy(copy,text,n);
      if(exr_txt_cursor_restore(cursor,&mark,&error)!=EXR_OK ||
         exr_txt_cursor_next(cursor,&again,&text,&n,&error)!=EXR_OK ||
         again!=offset || n!=copy_size || memcmp(copy,text,n)) return 18;
      free(copy);exr_txt_cursor_free(cursor);
    }
    fclose(file);printf("large scan and cursor replay: %zu paragraphs, %llu projected bytes\n",count,(unsigned long long)extent);
  }
  puts("bounded TXT projection checks passed");return 0;
}
