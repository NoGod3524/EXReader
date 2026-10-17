/* SPDX-License-Identifier: GPL-3.0-only */
#include "exreader.h"
#include <miniz.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error;
static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) {fprintf(stderr,"line %d: %s (%d: %s)\n", \
 __LINE__,#x,(int)error.code,error.message);exit(1);} } while(0)
#define OK(x) CHECK((x)==EXR_OK)
typedef struct {
  const unsigned char *bytes; size_t size, reads, total, chunk, released;
  int fail, oversized;
} memory_source;
static size_t read_at(void *context,uint64_t at,void *buffer,size_t size) {
  memory_source *s=context; size_t count=size;
  s->reads++;
  if(s->fail) return 0;
  CHECK(at<=s->size && size<=s->size-(size_t)at);
  if(s->chunk && count>s->chunk) count=s->chunk;
  memcpy(buffer,s->bytes+(size_t)at,count); s->total+=count;
  return s->oversized ? size+1 : count;
}
static void release(void *context) { ((memory_source *)context)->released++; }
static exr_source source(memory_source *memory) {
  return (exr_source){memory->size,read_at,release,memory};
}
static void *padded_book(const char *directory,size_t *size) {
  char path[4096]; mz_zip_archive input={0},output={0}; mz_zip_archive_file_stat stat;
  mz_uint i; void *book,*padding=calloc(1,8*1024*1024);
  CHECK(padding); CHECK(snprintf(path,sizeof(path),"%s/font-book.epub",directory)>0);
  CHECK(mz_zip_reader_init_file(&input,path,0)); CHECK(mz_zip_writer_init_heap(&output,0,0));
  for(i=0;i<mz_zip_reader_get_num_files(&input);i++) {
    size_t length; void *data;
    CHECK(mz_zip_reader_file_stat(&input,i,&stat));
    data=mz_zip_reader_extract_to_heap(&input,i,&length,0); CHECK(data);
    CHECK(mz_zip_writer_add_mem(&output,stat.m_filename,data,length,0)); mz_free(data);
  }
  CHECK(mz_zip_writer_add_mem(&output,"Unused/padding.bin",padding,8*1024*1024,0)); free(padding);
  CHECK(mz_zip_writer_finalize_heap_archive(&output,&book,size));
  mz_zip_writer_end(&output); mz_zip_reader_end(&input); return book;
}
static void lifetime(memory_source *memory,const char *directory) {
  exr_source input=source(memory); exr_publication *pub=NULL; exr_document *doc=NULL;
  exr_font *font=NULL; exr_layout *layout=NULL; exr_bitmap bitmap={0}; char path[4096];
  const exr_part *parts; const exr_resource *resources; void *bytes=NULL; size_t count,i,n;
  OK(exr_publication_open_source(&input,&pub,&error));
  CHECK(memory->reads>0 && memory->total<memory->size/4 && !memory->released);
  memset(&input,0,sizeof(input)); /* The descriptor is copied, its context is retained. */
  parts=exr_publication_parts(pub,&count); CHECK(count==2 && parts[0].path);
  OK(exr_publication_load(pub,0,&doc,&error)); CHECK(!strcmp(exr_document_text(doc,NULL),"A\nA\nA\nA"));
  exr_publication_free(pub); CHECK(!memory->released);
  resources=exr_document_resources(doc,&count);
  for(i=0;i<count;i++) if(!strcmp(resources[i].path,"OPS/Fonts/regular.ttf")) break;
  CHECK(i<count); OK(exr_document_resource(doc,i,&bytes,&n,&error)); CHECK(bytes && n>100); exr_free(bytes);
  CHECK(snprintf(path,sizeof(path),"%s/fonts/primary.ttf",directory)>0);
  OK(exr_font_open(path,&font,&error)); OK(exr_layout_create(doc,font,NULL,&layout,&error));
  CHECK(exr_font_count(exr_layout_font(layout))==4 && memory->total<memory->size/2);
  exr_document_free(doc); CHECK(memory->released==1);
  exr_font_free(font); OK(exr_render_page(layout,NULL,0,&bitmap,&error));
  exr_bitmap_free(&bitmap); exr_layout_free(layout); CHECK(memory->released==1);
}
static void failures(memory_source *memory) {
  exr_source input=source(memory); exr_publication *pub=(exr_publication *)(uintptr_t)1;
  exr_document *doc=(exr_document *)(uintptr_t)1;
  memory->released=0; memory->reads=memory->total=0; memory->fail=1;
  CHECK(exr_publication_open_source(&input,&pub,&error)==EXR_IO && !pub && !memory->released);
  memory->fail=0; memory->oversized=1;
  CHECK(exr_publication_open_source(&input,&pub,&error)==EXR_IO && !pub && !memory->released);
  memory->oversized=0; input.size=(uint64_t)128*1024*1024+1;
  memory->reads=0;
  CHECK(exr_publication_open_source(&input,&pub,&error)==EXR_LIMIT && !pub && !memory->reads);
  input=source(memory); input.read_at=NULL;
  CHECK(exr_publication_open_source(&input,&pub,&error)==EXR_ARGUMENT && !pub);
  CHECK(exr_publication_open_source(NULL,&pub,&error)==EXR_ARGUMENT && !pub);
  input=source(memory);
  CHECK(exr_publication_open_source(&input,NULL,&error)==EXR_ARGUMENT && !memory->released);
  memory->chunk=31; OK(exr_publication_open_source(&input,&pub,&error)); CHECK(memory->reads>100);
  memory->fail=1;
  CHECK(exr_publication_load(pub,0,&doc,&error)==EXR_IO && !doc && !memory->released);
  memory->fail=0; OK(exr_publication_load(pub,0,&doc,&error)); exr_document_free(doc);
  exr_publication_free(pub); CHECK(memory->released==1);
  {
    const char broken[]="not a ZIP"; memory_source bad={0};
    bad.bytes=(const unsigned char *)broken; bad.size=sizeof(broken)-1; input=source(&bad);
    CHECK(exr_publication_open_source(&input,&pub,&error)==EXR_FORMAT && !pub && !bad.released);
  }
}
int main(int argc,char **argv) {
  memory_source memory={0}; void *bytes; CHECK(argc==2);
  bytes=padded_book(argv[1],&memory.size); CHECK(memory.size>8*1024*1024); memory.bytes=bytes;
  lifetime(&memory,argv[1]); failures(&memory); mz_free(bytes);
  printf("Seekable sources: %u checks passed\n",checks); return 0;
}
