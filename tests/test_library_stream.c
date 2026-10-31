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
typedef struct { const unsigned char *data;size_t size;size_t reads,fail_at,cancel_after,chunk;int overread; } memory_source;
static size_t mem_read(void *context,uint64_t offset,void *buffer,size_t size) {
  memory_source *m=context;size_t n;
  if(m->reads++>=m->fail_at) return 0;
  if(m->overread) return size+1;
  if(offset>m->size || size>m->size-offset) return 0;
  n=size;if(m->chunk && n>m->chunk) n=m->chunk;memcpy(buffer,m->data+(size_t)offset,n);return n;
}
static int mem_cancel(void *context) { memory_source *m=context;return m->cancel_after && m->reads>=m->cancel_after; }
static int always_cancel(void *context) { (void)context;return 1; }
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
static void same_page(exr_fixed_document *doc,const exr_bitmap *expected) {
  exr_bitmap actual={0};OK(exr_fixed_render(doc,0,1,NULL,&actual,&error));
  CHECK(actual.width==expected->width && actual.height==expected->height && actual.stride==expected->stride);
  CHECK(!memcmp(actual.pixels,expected->pixels,(size_t)expected->stride*expected->height));exr_bitmap_free(&actual);
}
static void short_reads(const void *bytes,size_t size) {
  memory_source memory={0};exr_source source={0};exr_library *library=NULL;int64_t id=99;
  memory.data=bytes;memory.size=size;memory.fail_at=(size_t)-1;memory.chunk=7;
  source.size=size;source.read_at=mem_read;source.context=&memory;
  OK(exr_library_open(":memory:",&library,&error));
  OK(exr_library_import_source(library,EXR_CBZ,&source,"Short reads",&id,&error));CHECK(id>0);
  memory.reads=0;memory.fail_at=1;id=99;
  CHECK(exr_library_import_source(library,EXR_CBZ,&source,"Early end",&id,&error)==EXR_IO && !id);
  memory.reads=0;memory.fail_at=(size_t)-1;memory.overread=1;id=99;
  CHECK(exr_library_import_source(library,EXR_CBZ,&source,"Invalid read",&id,&error)==EXR_IO && !id);
  memory.reads=0;memory.overread=0;memory.cancel_after=4;id=99;
  source.control.cancelled=mem_cancel;source.control.context=&memory;
  CHECK(exr_library_import_source(library,EXR_CBZ,&source,"Cancelled read",&id,&error)==EXR_CANCELLED && !id);
  CHECK(count_books(library)==1);exr_library_close(library);
}
int main(int argc,char **argv) {
  char path[4096];void *bytes;size_t size,n=0;int64_t id=0,dup=0;int created=0;
  exr_library *library=NULL;exr_source source={0};memory_source memory={0};exr_fixed_document *doc=NULL;exr_bitmap bitmap={0};
  CHECK(argc==4);
  bytes=archive(argv[1],&size,2*1024*1024);CHECK(bytes && size>1024*1024);
  short_reads(bytes,size);
  snprintf(path,sizeof(path),"%s/stream.sqlite",argv[2]);remove(path);
  OK(exr_library_open(path,&library,&error));
  { char missing[4096];int64_t failed=99;int was_created=1;
    snprintf(missing,sizeof(missing),"%s/missing.cbz",argv[2]);
    CHECK(exr_library_import_file_unique(library,EXR_CBZ,missing,NULL,&failed,&was_created,&error)==EXR_IO);
    CHECK(!failed && !was_created);
    failed=99;was_created=1;
    CHECK(exr_library_import_file_unique(library,EXR_PDF,missing,NULL,&failed,&was_created,&error)==EXR_IO);
    CHECK(!failed && !was_created);
  }
  memory.data=bytes;memory.size=size;memory.fail_at=(size_t)-1;
  source.size=size;source.read_at=mem_read;source.context=&memory;
  OK(exr_library_import_source_unique(library,EXR_CBZ,&source,"Streamed", &id,&created,&error));CHECK(id>0 && created==1);
  CHECK(count_books(library)==1);
  memory.reads=0;OK(exr_library_import_source_unique(library,EXR_CBZ,&source,"Streamed",&dup,&created,&error));CHECK(dup==id && !created);
  CHECK(count_books(library)==1);
  /* Failures during unique comparison and insertion must release their transaction. */
  memory.reads=0;memory.cancel_after=12;source.control.cancelled=mem_cancel;source.control.context=&memory;
  dup=99;created=1;
  CHECK(exr_library_import_source_unique(library,EXR_CBZ,&source,"Cancel unique",&dup,&created,&error)==EXR_CANCELLED);
  CHECK(!dup && !created && count_books(library)==1);
  memory.reads=0;memory.cancel_after=0;source.control.cancelled=NULL;source.control.context=NULL;
  ((unsigned char *)bytes)[8192]^=1;memory.fail_at=16;
  dup=99;created=1;
  CHECK(exr_library_import_source_unique(library,EXR_CBZ,&source,"Broken unique",&dup,&created,&error)==EXR_IO);
  CHECK(!dup && !created && count_books(library)==1);
  ((unsigned char *)bytes)[8192]^=1;memory.reads=0;memory.fail_at=(size_t)-1;
  OK(exr_library_import_source_unique(library,EXR_CBZ,&source,"Streamed",&dup,&created,&error));CHECK(dup==id && !created);
  { struct legacy_options { size_t struct_size;exr_font *font;exr_control control; } *legacy;
    legacy=calloc(1,sizeof(*legacy));CHECK(legacy!=NULL);legacy->struct_size=sizeof(*legacy);
    OK(exr_library_fixed_source(library,id,(const exr_fixed_open_options *)legacy,&doc,&error));
    exr_fixed_free(doc);doc=NULL;free(legacy);
  }
  OK(exr_library_fixed_source(library,id,NULL,&doc,&error));
  { const exr_fixed_page *pages;size_t count2;pages=exr_fixed_pages(doc,&count2);CHECK(count2==1);
    OK(exr_fixed_render(doc,0,1,NULL,&bitmap,&error));CHECK(bitmap.width>0 && bitmap.height>0); }
  /* Metadata updates must not invalidate either active reader's source. */
  { exr_fixed_document *second=NULL;exr_book book={0};void *cover;size_t cover_size;unsigned pass;
    OK(exr_library_fixed_source(library,id,NULL,&second,&error));
    book.id=id;book.title="Streamed";
    for(pass=0;pass<3;pass++) {
      book.position=pass%2;book.favorite=pass%2;
      OK(exr_library_update(library,&book,&error));same_page(doc,&bitmap);same_page(second,&bitmap);
    }
    cover=read_file(argv[1],&cover_size);OK(exr_library_cover(library,id,cover,cover_size,&error));free(cover);
    same_page(doc,&bitmap);same_page(second,&bitmap);exr_fixed_free(second);
  }
  exr_bitmap_free(&bitmap);
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
    OK(exr_library_fixed_source(separate,dup,NULL,&doc,&error));
    OK(exr_library_delete(separate,dup,&error));
    { int64_t replacement=0;
      OK(exr_library_import_source(separate,EXR_CBZ,&source,"Replacement",&replacement,&error));CHECK(replacement==dup);
      CHECK(exr_fixed_render(doc,0,1,NULL,&bitmap,&error)==EXR_IO && !bitmap.pixels);
    }
    exr_fixed_free(doc);doc=NULL;
    exr_library_close(separate);
  }
  exr_library_close(library);
  OK(exr_library_open(path,&library,&error));CHECK(count_books(library)==1);
  OK(exr_library_fixed_source(library,id,NULL,&doc,&error));CHECK(doc && exr_fixed_pages(doc,&n) && n==1);
  { exr_book book={0};book.id=id;book.title="After reopen";book.favorite=1;OK(exr_library_update(library,&book,&error)); }
  exr_library_close(library);
  OK(exr_fixed_render(doc,0,1,NULL,&bitmap,&error));exr_bitmap_free(&bitmap);exr_fixed_free(doc);doc=NULL;
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
    { exr_fixed_open_options cancelled={0};cancelled.struct_size=sizeof(cancelled);cancelled.control.cancelled=always_cancel;
      CHECK(exr_library_fixed_source(pdf,pdfid,&cancelled,&pdoc,&error)==EXR_CANCELLED && !pdoc);
    }
    OK(exr_library_fixed_source(pdf,pdfid,NULL,&pdoc,&error));CHECK(exr_fixed_pages(pdoc,&pdf_pages) && pdf_pages>0);exr_fixed_free(pdoc);
    exr_library_close(pdf);OK(exr_library_open(pdfdb,&pdf,&error));OK(exr_library_fixed_source(pdf,pdfid,NULL,&pdoc,&error));
    CHECK(exr_fixed_pages(pdoc,&pdf_pages) && pdf_pages>0);exr_fixed_free(pdoc);exr_library_close(pdf);
  }
  free(bytes);printf("%u streaming library checks passed\n",checks);return 0;
}
