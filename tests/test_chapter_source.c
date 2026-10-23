/* SPDX-License-Identifier: MIT */
#include "formats_internal.h"
#include <miniz.h>
#include <stdio.h>
static unsigned checks;
static exr_error error;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"chapter source line %d: %s (%d)\n",__LINE__,#x,error.code);exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
typedef struct { size_t used,peak,budget,calls,fail_at,rejected; } ledger;
typedef struct { exr_allocation_alignment alignment; size_t size; } allocation;
static void *allocate(void *context,size_t size) {
  ledger *l=context;allocation *a;
  l->calls++;
  if(l->calls==l->fail_at || size>SIZE_MAX-sizeof(*a) || size+sizeof(*a)>l->budget-l->used) { l->rejected++;return NULL; }
  a=malloc(size+sizeof(*a));if(!a) return NULL;
  a->size=size+sizeof(*a);l->used+=a->size;if(l->used>l->peak) l->peak=l->used;return a+1;
}
static void release(void *context,void *data) {
  ledger *l=context;allocation *a;if(!data) return;a=(allocation *)data-1;l->used-=a->size;free(a);
}
static void *resize(void *context,void *data,size_t size) {
  allocation *a;void *replacement;
  if(!data) return allocate(context,size);
  if(!size) { release(context,data);return NULL; }
  a=(allocation *)data-1;replacement=allocate(context,size);
  if(replacement) { size_t old=a->size-sizeof(*a);memcpy(replacement,data,old<size?old:size);release(context,data); }
  return replacement;
}
typedef struct { const unsigned char *bytes;size_t size,chunk,reads;int fail; } source;
static size_t read_source(void *context,uint64_t offset,void *data,size_t size) {
  source *s=context;s->reads++;
  if(s->fail || offset>s->size || size>s->size-offset) return 0;
  if(size>s->chunk) size=s->chunk;
  memcpy(data,s->bytes+(size_t)offset,size);return size;
}
typedef struct { const char *text;size_t size,received,chunks,final;int fail; } sink_state;
static exr_status sink(void *context,const void *data,size_t size,int final,exr_error *e) {
  sink_state *s=context;(void)e;
  CHECK(size<=32768 && s->received<=s->size && size<=s->size-s->received);
  if(size) { CHECK(!memcmp(data,s->text+s->received,size));s->chunks++; }
  s->received+=size;s->final+=(size_t)final;
  return s->fail ? EXR_IO : EXR_OK;
}
static int cancelled(void *context) { (void)context;return 1; }
static void run(int backed) {
  mz_zip_archive zip={0};void *bytes=NULL;size_t length=0,i,total_calls,peak;
  char *text=malloc(256*1024);size_t text_size=256*1024;
  exr_archive_store store={0};exr_document d={0};exr_resource resource={0};exr_chapter chapter={0};
  source src={0};ledger l={0};sink_state out={0};exr_control control={0};
  exr_resource_allocator allocator={&l,allocate,resize,release};
  CHECK(text!=NULL);for(i=0;i<text_size;i++) text[i]=(char)('a'+i%23);
  CHECK(mz_zip_writer_init_heap(&zip,0,0));
  CHECK(mz_zip_writer_add_mem(&zip,"book.xhtml",text,text_size,MZ_DEFAULT_COMPRESSION));
  CHECK(mz_zip_writer_finalize_heap_archive(&zip,&bytes,&length));CHECK(mz_zip_writer_end(&zip));
  d.format=EXR_EPUB;d.shared_archive=&store;d.resources=&resource;d.resource_count=1;d.chapters=&chapter;d.chapter_count=1;
  resource.path="book.xhtml";chapter.resource=0;
  src=(source){bytes,length,13,0,0};
  if(backed) { store.source.size=length;store.source.read_at=read_source;store.source.context=&src; }
  else { d.archive=bytes;d.archive_size=length; }
  l.budget=1024*1024;out=(sink_state){text,text_size,0,0,0,0};
  OK(exr_epub_chapter_feed_bounded(&d,0,sink,&out,&allocator,NULL,&error));
  CHECK(out.received==text_size && out.final==1 && out.chunks>=8 && !l.used && l.calls>0 && l.peak<=l.budget);
  if(backed) CHECK(src.reads>100);
  total_calls=l.calls;peak=l.peak;
  l=(ledger){0};l.budget=peak;out=(sink_state){text,text_size,0,0,0,0};
  OK(exr_epub_chapter_feed_bounded(&d,0,sink,&out,&allocator,NULL,&error));CHECK(!l.used && l.peak==peak);
  l=(ledger){0};l.budget=peak-1;out=(sink_state){text,text_size,0,0,0,0};
  CHECK(exr_epub_chapter_feed_bounded(&d,0,sink,&out,&allocator,NULL,&error)!=EXR_OK);
  CHECK(l.rejected && !l.used && !out.final && l.peak<=l.budget);
  for(i=1;i<=total_calls;i++) {
    l=(ledger){0};l.budget=1024*1024;l.fail_at=i;out=(sink_state){text,text_size,0,0,0,0};
    CHECK(exr_epub_chapter_feed_bounded(&d,0,sink,&out,&allocator,NULL,&error)!=EXR_OK);
    CHECK(l.rejected==1 && !l.used && !out.final);
  }
  l=(ledger){0};l.budget=1024*1024;out=(sink_state){text,text_size,0,0,0,1};
  CHECK(exr_epub_chapter_feed_bounded(&d,0,sink,&out,&allocator,NULL,&error)==EXR_IO);CHECK(!l.used && !out.final);
  out=(sink_state){text,text_size,0,0,0,0};control.cancelled=cancelled;
  CHECK(exr_epub_chapter_feed_bounded(&d,0,sink,&out,&allocator,&control,&error)==EXR_CANCELLED);CHECK(!l.used && !out.final);
  if(backed) {
    void *resource_bytes=(void *)1;size_t size=1;
    l=(ledger){0};l.budget=1024*1024;
    OK(exr_document_resource_bounded(&d,0,&allocator,NULL,&resource_bytes,&size,&error));
    CHECK(size==text_size && !memcmp(resource_bytes,text,size));release(&l,resource_bytes);CHECK(!l.used);
    total_calls=l.calls;
    for(i=1;i<=total_calls;i++) {
      l=(ledger){0};l.budget=1024*1024;l.fail_at=i;resource_bytes=(void *)1;size=1;
      CHECK(exr_document_resource_bounded(&d,0,&allocator,NULL,&resource_bytes,&size,&error)!=EXR_OK);
      CHECK(!resource_bytes && !size && !l.used && l.rejected==1);
    }
    src.fail=1;out=(sink_state){text,text_size,0,0,0,0};
    CHECK(exr_epub_chapter_feed_bounded(&d,0,sink,&out,&allocator,NULL,&error)==EXR_IO);CHECK(!l.used && !out.final);src.fail=0;
  }
  /* A final successful callback is forbidden until ZIP integrity is verified. */
  for(i=0;i+20<length;i++) if(!memcmp((char *)bytes+i,"PK\1\2",4)) { ((unsigned char *)bytes)[i+16]^=1;break; }
  CHECK(i+20<length);l=(ledger){0};l.budget=1024*1024;out=(sink_state){text,text_size,0,0,0,0};
  CHECK(exr_epub_chapter_feed_bounded(&d,0,sink,&out,&allocator,NULL,&error)==EXR_FORMAT);CHECK(!l.used && !out.final);
  mz_free(bytes);free(text);
}
int main(void) { run(0);run(1);printf("%u chapter source checks passed\n",checks);return 0; }
