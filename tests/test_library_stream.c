/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include <miniz.h>
#include <sqlite3.h>
#include <stdio.h>
#ifdef _WIN32
#include <windows.h>
#else
#include <sys/stat.h>
#endif
#include <stdlib.h>
#include <string.h>
static exr_error error;static unsigned checks;
#define CHECK(x) do { checks++;if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message);exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static void *read_file(const char *path,size_t *size) {
  FILE *f=fopen(path,"rb");long n;void *data;CHECK(f && !fseek(f,0,SEEK_END));n=ftell(f);CHECK(n>=0);rewind(f);
  *size=(size_t)n;data=malloc(*size ? *size : 1);CHECK(data && fread(data,1,*size,f)==*size && !fclose(f));return data;
}
typedef struct { const unsigned char *data;size_t size;size_t reads,fail_at,cancel_after; } memory_source;
static size_t mem_read(void *context,uint64_t offset,void *buffer,size_t size) {
  memory_source *m=context;size_t n;
  if(m->reads++>=m->fail_at) return 0;
  if(offset>m->size || size>m->size-offset) return 0;
  n=size;memcpy(buffer,m->data+(size_t)offset,n);return n;
}
static int mem_cancel(void *context) { memory_source *m=context;return m->cancel_after && m->reads>=m->cancel_after; }
static void put(mz_zip_archive *zip,const char *name,const void *data,size_t size) { CHECK(mz_zip_writer_add_mem(zip,name,data,size,MZ_NO_COMPRESSION)); }
static void *archive(const char *fixtures,size_t *size,int pad) {
  mz_zip_archive zip;void *out=NULL;unsigned char *png;size_t png_size;void *padding;
  png=read_file(fixtures,&png_size);
  memset(&zip,0,sizeof(zip));CHECK(mz_zip_writer_init_heap(&zip,0,0));
  put(&zip,"pages/1.png",png,png_size);free(png);
  if(pad) { padding=calloc(1,(size_t)pad);CHECK(padding);put(&zip,"notes/padding.bin",padding,(size_t)pad);free(padding); }
  CHECK(mz_zip_writer_finalize_heap_archive(&zip,&out,size));CHECK(mz_zip_writer_end(&zip));return out;
}
static int64_t count_books(exr_library *library) { exr_book *books=NULL;size_t n=0;int64_t id=0;OK(exr_library_books(library,NULL,&books,&n,&error));if(n) id=books[0].id;exr_books_free(books,n);return id; }
int main(int argc,char **argv) {
  char path[4096];void *bytes;size_t size,n=0;int64_t id=0,dup=0;int created=0;
  exr_library *library=NULL;exr_source source={0};memory_source memory={0};exr_fixed_document *doc=NULL;exr_bitmap bitmap={0};
  CHECK(argc==4);
  bytes=archive(argv[1],&size,2*1024*1024);CHECK(bytes && size>1024*1024);
  snprintf(path,sizeof(path),"%s/stream.sqlite",argv[2]);remove(path);
  OK(exr_library_open(path,&library,&error));
  memory.data=bytes;memory.size=size;memory.fail_at=(size_t)-1;
  source.size=size;source.read_at=mem_read;source.context=&memory;
  OK(exr_library_import_source_unique(library,EXR_CBZ,&source,"Streamed", &id,&created,&error));CHECK(id>0 && created==1);
  CHECK(count_books(library)==1);
  memory.reads=0;OK(exr_library_import_source_unique(library,EXR_CBZ,&source,"Streamed",&dup,&created,&error));CHECK(dup==id && !created);
  CHECK(count_books(library)==1);
  OK(exr_library_fixed_source(library,id,NULL,&doc,&error));
  { const exr_fixed_page *pages;size_t count2;pages=exr_fixed_pages(doc,&count2);CHECK(count2==1);
    OK(exr_fixed_render(doc,0,1,NULL,&bitmap,&error));CHECK(bitmap.width>0 && bitmap.height>0);exr_bitmap_free(&bitmap); }
  exr_fixed_free(doc);doc=NULL;
  /* Cancellation in the middle of the chunked blob write rolls back the row. */
  memory.reads=0;memory.cancel_after=12;source.control.cancelled=mem_cancel;source.control.context=&memory;
  CHECK(exr_library_import_source(library,EXR_CBZ,&source,"Cancel",&dup,&error)==EXR_CANCELLED);
  CHECK(count_books(library)==1);
  source.control.cancelled=NULL;source.control.context=NULL;
  /* A source read failure also leaves no partial row. */
  memory.reads=0;memory.cancel_after=0;memory.fail_at=16;
  CHECK(exr_library_import_source(library,EXR_CBZ,&source,"Broken",&dup,&error)==EXR_IO);
  CHECK(count_books(library)==1);
  memory.fail_at=(size_t)-1;
  /* A storage lock makes the insert transaction fail; no partial row remains. */
  { sqlite3 *blocker=NULL;char dbpath[4096];snprintf(dbpath,sizeof(dbpath),"%s/stream.sqlite",argv[2]);
    CHECK(sqlite3_open(dbpath,&blocker)==SQLITE_OK);
    CHECK(sqlite3_exec(blocker,"BEGIN EXCLUSIVE",NULL,NULL,NULL)==SQLITE_OK);
    memory.reads=0;memory.fail_at=(size_t)-1;
    CHECK(exr_library_import_source(library,EXR_CBZ,&source,"Locked",&dup,&error)==EXR_DATABASE);
    CHECK(sqlite3_exec(blocker,"ROLLBACK",NULL,NULL,NULL)==SQLITE_OK);sqlite3_close(blocker);
    CHECK(count_books(library)==1);
  }
  /* A second database opens independently and still imports/reads streaming. */
  { exr_library *separate=NULL;char dbpath[4096];
    snprintf(dbpath,sizeof(dbpath),"%s/storage.sqlite",argv[2]);remove(dbpath);OK(exr_library_open(dbpath,&separate,&error));
    memory.reads=0;
    OK(exr_library_import_source(separate,EXR_CBZ,&source,"Storage",&dup,&error));CHECK(dup>0);
    exr_library_close(separate);
  }
  exr_library_close(library);
  OK(exr_library_open(path,&library,&error));CHECK(count_books(library)==1);
  OK(exr_library_fixed_source(library,id,NULL,&doc,&error));CHECK(doc && exr_fixed_pages(doc,&n) && n==1);exr_fixed_free(doc);doc=NULL;
  exr_library_close(library);
  /* A read-only database is a storage failure: the transaction rolls back. */
  { char dbpath[4096];snprintf(dbpath,sizeof(dbpath),"%s/stream.sqlite",argv[2]);
#ifdef _WIN32
    CHECK(SetFileAttributesA(dbpath,FILE_ATTRIBUTE_READONLY));
#else
    CHECK(chmod(dbpath,0444)==0);
#endif
    OK(exr_library_open(dbpath,&library,&error));
    memory.reads=0;memory.cancel_after=0;memory.fail_at=(size_t)-1;
    CHECK(exr_library_import_source(library,EXR_CBZ,&source,"Readonly",&dup,&error)==EXR_DATABASE);
    exr_library_close(library);
#ifdef _WIN32
    CHECK(SetFileAttributesA(dbpath,FILE_ATTRIBUTE_NORMAL));
#else
    CHECK(chmod(dbpath,0644)==0);
#endif
    OK(exr_library_open(dbpath,&library,&error));CHECK(count_books(library)==1);
  }
  exr_library_close(library);
  /* PDF uses mapped files for metadata and an anonymous pagefile mapping for
     re-reading the stored blob; neither path materializes a heap-sized copy. */
  { char pdfpath[4096],pdfdb[4096];exr_library *pdf=NULL;exr_fixed_document *pdoc=NULL;size_t pdf_pages=0;int64_t pdfid=0,pdfdup=0;int pdf_created=0;
    snprintf(pdfpath,sizeof(pdfpath),"%s",argv[3]);snprintf(pdfdb,sizeof(pdfdb),"%s/pdf-stream.sqlite",argv[2]);remove(pdfdb);
    OK(exr_library_open(pdfdb,&pdf,&error));
    OK(exr_library_import_file_unique(pdf,EXR_PDF,pdfpath,"PDF stream",&pdfid,&pdf_created,&error));CHECK(pdfid>0 && pdf_created);
    OK(exr_library_import_file_unique(pdf,EXR_PDF,pdfpath,"PDF stream",&pdfdup,&created,&error));CHECK(pdfdup==pdfid && !created);
    OK(exr_library_fixed_source(pdf,pdfid,NULL,&pdoc,&error));CHECK(exr_fixed_pages(pdoc,&pdf_pages) && pdf_pages>0);exr_fixed_free(pdoc);
    exr_library_close(pdf);OK(exr_library_open(pdfdb,&pdf,&error));OK(exr_library_fixed_source(pdf,pdfid,NULL,&pdoc,&error));
    CHECK(exr_fixed_pages(pdoc,&pdf_pages) && pdf_pages>0);exr_fixed_free(pdoc);exr_library_close(pdf);
  }
  free(bytes);printf("%u streaming library checks passed\n",checks);return 0;
}
