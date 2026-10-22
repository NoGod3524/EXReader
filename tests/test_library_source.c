/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#ifdef EXR_SOURCE_SQLITE_FIXTURES
#include <sqlite3.h>
#endif
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static exr_error error;
static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message);exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)

static unsigned char *read_file(const char *path,size_t *size) {
  FILE *f=fopen(path,"rb");long n;unsigned char *bytes;
  CHECK(f && !fseek(f,0,SEEK_END));n=ftell(f);CHECK(n>0);rewind(f);
  *size=(size_t)n;bytes=malloc(*size);CHECK(bytes);
  CHECK(fread(bytes,1,*size,f)==*size && !fclose(f));return bytes;
}
static void release_source(exr_source *source) {
  CHECK(source->release);source->release(source->context);memset(source,0,sizeof(*source));
}
static size_t dummy_read(void *context,uint64_t offset,void *buffer,size_t size) {
  (void)context;(void)offset;(void)buffer;(void)size;return 0;
}
static void dummy_release(void *context) { (void)context; }
static int dummy_cancel(void *context) { (void)context;return 0; }
static void dummy_progress(void *context,exr_stage stage,uint64_t done,uint64_t total) {
  (void)context;(void)stage;(void)done;(void)total;
}
static exr_source dirty_output(void) {
  exr_source source={0};source.size=17;source.read_at=dummy_read;source.release=dummy_release;
  source.context=&error;source.control.cancelled=dummy_cancel;
  source.control.progress=dummy_progress;source.control.context=&checks;return source;
}
static void cleared(const exr_source *source) {
  CHECK(!source->size && !source->read_at && !source->release && !source->context);
  CHECK(!source->control.cancelled && !source->control.progress && !source->control.context);
}
static void compare_source(const exr_source *source,const void *bytes,size_t size) {
  const unsigned char *expected=bytes;unsigned char buffer[257];size_t at=0,i;uint32_t random=0x51a7u;
  CHECK(source->size==(uint64_t)size && source->read_at && source->release);
  while(at<size) {
    size_t n=size-at;if(n>sizeof(buffer)) n=sizeof(buffer);
    CHECK(source->read_at(source->context,at,buffer,n)==n);
    CHECK(!memcmp(buffer,expected+at,n));at+=n;
  }
  for(i=0;i<64;i++) {
    size_t n;
    random=random*1664525u+1013904223u;at=random%size;
    random=random*1664525u+1013904223u;n=1+random%sizeof(buffer);if(n>size-at) n=size-at;
    CHECK(source->read_at(source->context,at,buffer,n)==n);
    CHECK(!memcmp(buffer,expected+at,n));
  }
  memset(buffer,0xa5,sizeof(buffer));
  CHECK(source->read_at(source->context,size,buffer,1)==0);
  CHECK(source->read_at(source->context,size+1,buffer,1)==0);
  CHECK(source->read_at(source->context,size-1,buffer,2)==0);
  CHECK(source->read_at(source->context,UINT64_MAX,buffer,1)==0);
  CHECK(source->read_at(source->context,0,buffer,SIZE_MAX)==0);
  CHECK(source->read_at(source->context,0,buffer,0)==0);
  for(i=0;i<sizeof(buffer);i++) CHECK(buffer[i]==0xa5);
  CHECK(source->size==(uint64_t)size);
}
static void invalid_arguments(exr_library *library) {
  exr_source source=dirty_output();
  CHECK(exr_library_source(NULL,1,&source,&error)==EXR_ARGUMENT);cleared(&source);
  source=dirty_output();CHECK(exr_library_source(library,0,&source,&error)==EXR_ARGUMENT);cleared(&source);
  source=dirty_output();CHECK(exr_library_source(library,-1,&source,&error)==EXR_ARGUMENT);cleared(&source);
  source=dirty_output();CHECK(exr_library_source(library,INT64_MAX,&source,&error)==EXR_ARGUMENT);cleared(&source);
  CHECK(exr_library_source(library,1,NULL,&error)==EXR_ARGUMENT);
}
static void lifetime(const char *database,const void *epub,size_t size,int reverse) {
  exr_library *library=NULL;exr_source a={0},b={0};int64_t id=0;
  OK(exr_library_open(database,&library,&error));invalid_arguments(library);
  OK(exr_library_import(library,EXR_EPUB,epub,size,"Source lifetime",&id,&error));
  OK(exr_library_source(library,id,&a,&error));OK(exr_library_source(library,id,&b,&error));
  compare_source(&a,epub,size);compare_source(&b,epub,size);
  exr_library_close(library);library=NULL;
  compare_source(&a,epub,size);compare_source(&b,epub,size);
  if(reverse) { release_source(&b);compare_source(&a,epub,size);release_source(&a); }
  else { release_source(&a);compare_source(&b,epub,size);release_source(&b); }
}
static void owner_writes(const char *database) {
  const char bytes[]="Stored original remains readable.";
  exr_library *library=NULL;exr_source source={0};exr_book *books=NULL;size_t count=0;
  exr_document *document=NULL;exr_anchor anchor={0};int64_t id=0,other=0;
  OK(exr_library_open(database,&library,&error));
  OK(exr_library_import(library,EXR_TXT,bytes,sizeof(bytes)-1,"Owner writes",&id,&error));
  OK(exr_library_source(library,id,&source,&error));compare_source(&source,bytes,sizeof(bytes)-1);
  OK(exr_library_books(library,"Owner writes",&books,&count,&error));CHECK(count==1 && books[0].id==id);
  books[0].favorite=1;books[0].position=2;OK(exr_library_update(library,books,&error));
  exr_books_free(books,count);compare_source(&source,bytes,sizeof(bytes)-1);
  OK(exr_document_open_memory(EXR_TXT,bytes,sizeof(bytes)-1,&document,&error));
  OK(exr_anchor_create(document,3,3,&anchor,&error));
  OK(exr_library_progress(library,id,&anchor,&error));compare_source(&source,bytes,sizeof(bytes)-1);
  exr_anchor_free(&anchor);exr_document_free(document);
  OK(exr_library_cover(library,id,"cover",5,&error));compare_source(&source,bytes,sizeof(bytes)-1);
  OK(exr_library_import(library,EXR_TXT,"Another book",12,NULL,&other,&error));
  CHECK(other!=id);compare_source(&source,bytes,sizeof(bytes)-1);
  OK(exr_library_delete(library,other,&error));compare_source(&source,bytes,sizeof(bytes)-1);
  exr_library_close(library);compare_source(&source,bytes,sizeof(bytes)-1);release_source(&source);
}
static void deletion(const char *database) {
  const char before[]="Old bytes.",after[]="New bytes.";
  exr_library *library=NULL;exr_source a={0},b={0},fresh={0};int64_t old_id=0,new_id=0;
  unsigned char byte=0xa5;
  CHECK(sizeof(before)==sizeof(after) && memcmp(before,after,sizeof(before)));
  OK(exr_library_open(database,&library,&error));
  OK(exr_library_import(library,EXR_TXT,before,sizeof(before)-1,NULL,&old_id,&error));
  OK(exr_library_source(library,old_id,&a,&error));OK(exr_library_source(library,old_id,&b,&error));
  OK(exr_library_delete(library,old_id,&error));
  /* Do not read a until after ID reuse: neither a missing-row read nor a size
     mismatch may stand in for the owner's explicit source invalidation. */
  CHECK(b.read_at(b.context,0,&byte,1)==0 && byte==0xa5);
  OK(exr_library_import(library,EXR_TXT,after,sizeof(after)-1,NULL,&new_id,&error));
  CHECK(new_id==old_id); /* INTEGER PRIMARY KEY reuses the sole deleted row ID. */
  OK(exr_library_source(library,new_id,&fresh,&error));compare_source(&fresh,after,sizeof(after)-1);
  CHECK(a.read_at(a.context,0,&byte,1)==0 && b.read_at(b.context,0,&byte,1)==0);
  CHECK(a.size==sizeof(before)-1 && b.size==sizeof(before)-1);
  exr_library_close(library);release_source(&b);compare_source(&fresh,after,sizeof(after)-1);
  CHECK(a.read_at(a.context,0,&byte,1)==0);release_source(&a);release_source(&fresh);
}
static void external_replacement(const char *database) {
  const char before[]="Old bytes.",after[]="New bytes.";
  exr_library *owner=NULL,*other=NULL;exr_source old={0},fresh={0};
  int64_t old_id=0,new_id=0;unsigned char byte=0xa5;
  CHECK(sizeof(before)==sizeof(after) && memcmp(before,after,sizeof(before)));
  OK(exr_library_open(database,&owner,&error));
  OK(exr_library_import(owner,EXR_TXT,before,sizeof(before)-1,NULL,&old_id,&error));
  OK(exr_library_open(database,&other,&error));
  OK(exr_library_source(owner,old_id,&old,&error));compare_source(&old,before,sizeof(before)-1);
  OK(exr_library_delete(other,old_id,&error));
  /* The owner cannot observe a missing row: both commits finish before the
     next callback, and replacement size and row ID are deliberately equal. */
  OK(exr_library_import(other,EXR_TXT,after,sizeof(after)-1,NULL,&new_id,&error));
  CHECK(new_id==old_id);
  CHECK(old.read_at(old.context,0,&byte,1)==0 && byte==0xa5);
  OK(exr_library_source(owner,new_id,&fresh,&error));compare_source(&fresh,after,sizeof(after)-1);
  exr_library_close(other);exr_library_close(owner);
  CHECK(old.read_at(old.context,0,&byte,1)==0 && old.size==sizeof(before)-1);
  release_source(&old);compare_source(&fresh,after,sizeof(after)-1);release_source(&fresh);
}
static void external_commit(const char *database) {
  const char bytes[]="Separate owner.";exr_library *owner=NULL,*other=NULL;
  exr_source old={0},fresh={0};exr_book *books=NULL;size_t count=0;int64_t id=0;unsigned char byte=0xa5;
  OK(exr_library_open(database,&owner,&error));
  OK(exr_library_import(owner,EXR_TXT,bytes,sizeof(bytes)-1,"Cross connection",&id,&error));
  OK(exr_library_open(database,&other,&error));
  OK(exr_library_source(owner,id,&old,&error));compare_source(&old,bytes,sizeof(bytes)-1);
  OK(exr_library_books(other,"Cross connection",&books,&count,&error));CHECK(count==1);
  books[0].favorite=1;OK(exr_library_update(other,books,&error));exr_books_free(books,count);
  CHECK(old.read_at(old.context,0,&byte,1)==0 && byte==0xa5);
  OK(exr_library_source(owner,id,&fresh,&error));compare_source(&fresh,bytes,sizeof(bytes)-1);
  CHECK(old.read_at(old.context,0,&byte,1)==0);CHECK(old.size==sizeof(bytes)-1);
  exr_library_close(other);exr_library_close(owner);
  compare_source(&fresh,bytes,sizeof(bytes)-1);release_source(&fresh);
  CHECK(old.read_at(old.context,0,&byte,1)==0);release_source(&old);
}
#ifdef EXR_SOURCE_SQLITE_FIXTURES
static void enable_wal(const char *database) {
  exr_library *library=NULL;sqlite3 *db=NULL;sqlite3_stmt *statement=NULL;
  const unsigned char *mode;
  OK(exr_library_open(database,&library,&error));exr_library_close(library);
  CHECK(sqlite3_open(database,&db)==SQLITE_OK);
  CHECK(sqlite3_prepare_v2(db,"PRAGMA journal_mode=WAL",-1,&statement,NULL)==SQLITE_OK);
  CHECK(sqlite3_step(statement)==SQLITE_ROW);mode=sqlite3_column_text(statement,0);
  CHECK(mode && !strcmp((const char *)mode,"wal"));
  CHECK(sqlite3_finalize(statement)==SQLITE_OK);CHECK(sqlite3_close(db)==SQLITE_OK);
}
static void corrupt_rows(const char *database) {
  sqlite3 *db=NULL;exr_library *library=NULL;exr_source source;
  exr_publication *publication=NULL;unsigned char bytes[4]={0};
  OK(exr_library_open(database,&library,&error));exr_library_close(library);
  /* Invalid storage is injected through SQLite, never SDK internals. */
  CHECK(sqlite3_open(database,&db)==SQLITE_OK);
  CHECK(sqlite3_exec(db,"INSERT INTO books(id,format,title,text_size,source) VALUES"
    "(1,1,'Empty',0,x''),(2,1,'Not a blob',4,'text'),(3,4,'Invalid EPUB',4,x'6e6f7065');",
    NULL,NULL,NULL)==SQLITE_OK);
  CHECK(sqlite3_close(db)==SQLITE_OK);
  OK(exr_library_open(database,&library,&error));
  source=dirty_output();CHECK(exr_library_source(library,1,&source,&error)==EXR_DATABASE);cleared(&source);
  source=dirty_output();CHECK(exr_library_source(library,2,&source,&error)==EXR_DATABASE);cleared(&source);
  /* Obtaining original bytes must not parse them, even for an EPUB-tagged row. */
  OK(exr_library_source(library,3,&source,&error));CHECK(source.size==4);
  CHECK(source.read_at(source.context,0,bytes,4)==4 && !memcmp(bytes,"nope",4));
  CHECK(exr_publication_open_source(&source,&publication,&error)!=EXR_OK && !publication);
  exr_library_close(library);release_source(&source);
}
#endif

typedef struct { exr_source inner;unsigned releases; } tracked_source;
static size_t tracked_read(void *context,uint64_t offset,void *buffer,size_t size) {
  tracked_source *tracked=context;
  return tracked->inner.read_at(tracked->inner.context,offset,buffer,size);
}
static void tracked_release(void *context) {
  tracked_source *tracked=context;CHECK(tracked->releases==0);tracked->releases++;
  release_source(&tracked->inner);
}
static exr_source track(tracked_source *tracked) {
  exr_source source=tracked->inner;source.read_at=tracked_read;source.release=tracked_release;source.context=tracked;return source;
}
typedef struct { const char *expected;size_t size,offset,calls; } text_check;
static exr_status text_sink(void *context,const char *text,size_t size,exr_error *e) {
  text_check *check=context;(void)e;
  CHECK(size && size<=32768 && check->offset<=check->size && size<=check->size-check->offset);
  CHECK(((unsigned char)text[0]&0xc0)!=0x80);
  CHECK(!memcmp(text,check->expected+check->offset,size));check->offset+=size;check->calls++;return EXR_OK;
}
static void publication_consumer(const void *epub,size_t size,const char *font_path) {
  exr_library *library=NULL;exr_publication *publication=NULL;exr_font *font=NULL;
  exr_pager *pager=NULL;exr_document *snapshot=NULL;exr_source source;
  tracked_source tracked={0};int64_t id=0;size_t count=0,text_size=0,pages=0;
  const char *text;char *expected;exr_anchor anchor={0};exr_anchor_match match;
  exr_layout_config config=exr_layout_config_defaults();exr_chapter_options options=exr_chapter_options_defaults();
  OK(exr_library_open(":memory:",&library,&error));
  OK(exr_library_import(library,EXR_EPUB,epub,size,"Bounded consumer",&id,&error));
  OK(exr_library_source(library,id,&tracked.inner,&error));source=track(&tracked);
  OK(exr_publication_open_source(&source,&publication,&error));CHECK(!tracked.releases);
  CHECK(exr_publication_parts(publication,&count) && count==2);
  OK(exr_publication_load(publication,0,&snapshot,&error));text=exr_document_text(snapshot,&text_size);
  CHECK(text && text_size>5);expected=malloc(text_size+1);CHECK(expected);
  memcpy(expected,text,text_size);expected[text_size]=0;exr_document_free(snapshot);snapshot=NULL;
  exr_library_close(library);library=NULL;
  OK(exr_font_open(font_path,&font,&error));config.page=(exr_layout_options){360,480,20,24,1.5f,8};
  OK(exr_publication_pager_create(publication,0,font,&config,&options,&pager,&error));
  exr_publication_free(publication);publication=NULL;CHECK(!tracked.releases);
  for(;;) {
    exr_layout *page=NULL;exr_bitmap bitmap={0};const exr_page *range;
    OK(exr_pager_next(pager,&page,&error));if(!page) break;
    range=exr_layout_pages(page,&count);CHECK(range && count==1 && range[0].start<=range[0].end && range[0].end<=text_size);
    OK(exr_render_page_color(page,exr_layout_font(page),0,&bitmap,&error));
    CHECK(bitmap.pixels && bitmap.width==360 && bitmap.height==480 && bitmap.channels==4);
    exr_bitmap_free(&bitmap);exr_layout_free(page);pages++;CHECK(pages<100);
  }
  CHECK(pages>0 && !tracked.releases);
  { text_check check={expected,text_size,0,0};
    OK(exr_pager_read_text(pager,0,text_size,text_sink,&check,NULL,&error));CHECK(check.offset==text_size && check.calls>0); }
  OK(exr_pager_anchor_create(pager,0,5,NULL,&anchor,&error));
  CHECK(anchor.exact && strlen(anchor.exact)==5 && !memcmp(anchor.exact,expected,5));
  OK(exr_pager_anchor_resolve(pager,&anchor,NULL,&match,&error));
  CHECK(match.state==EXR_ANCHOR_FOUND && match.start==0 && match.end==5);exr_anchor_free(&anchor);
  CHECK(exr_pager_chapter_statistics(pager).explicit_snapshot_bytes==0);
  exr_pager_free(pager);CHECK(tracked.releases==1);exr_font_free(font);free(expected);
}
static void failed_publication_consumer(void) {
  const char bytes[]="Not an EPUB";exr_library *library=NULL;exr_publication *publication=NULL;
  tracked_source tracked={0};exr_source source;int64_t id=0;unsigned char buffer[sizeof(bytes)-1];
  OK(exr_library_open(":memory:",&library,&error));
  OK(exr_library_import(library,EXR_TXT,bytes,sizeof(bytes)-1,NULL,&id,&error));
  OK(exr_library_source(library,id,&tracked.inner,&error));source=track(&tracked);
  CHECK(exr_publication_open_source(&source,&publication,&error)!=EXR_OK && !publication);
  CHECK(!tracked.releases);exr_library_close(library);
  CHECK(source.read_at(source.context,0,buffer,sizeof(buffer))==sizeof(buffer) && !memcmp(buffer,bytes,sizeof(buffer)));
  source.release(source.context);CHECK(tracked.releases==1);
}
int main(int argc,char **argv) {
  char path[4096],fixture[4096],font[4096];unsigned char *epub;size_t size;int i;
  CHECK(argc==3);snprintf(fixture,sizeof(fixture),"%s/sample.epub",argv[1]);
  snprintf(font,sizeof(font),"%s/fonts/primary.ttf",argv[1]);epub=read_file(fixture,&size);
  for(i=0;i<2;i++) {
    snprintf(path,sizeof(path),"%s/library-source-lifetime-%d.sqlite",argv[2],i);remove(path);
    lifetime(path,epub,size,i);remove(path);lifetime(":memory:",epub,size,i);
  }
  snprintf(path,sizeof(path),"%s/library-source-writes.sqlite",argv[2]);remove(path);
  owner_writes(path);remove(path);owner_writes(":memory:");
  snprintf(path,sizeof(path),"%s/library-source-delete.sqlite",argv[2]);remove(path);
  deletion(path);remove(path);deletion(":memory:");
  snprintf(path,sizeof(path),"%s/library-source-external.sqlite",argv[2]);remove(path);
  external_commit(path);remove(path);
  snprintf(path,sizeof(path),"%s/library-source-replacement.sqlite",argv[2]);remove(path);
  external_replacement(path);remove(path);
#ifdef EXR_SOURCE_SQLITE_FIXTURES
  snprintf(path,sizeof(path),"%s/library-source-wal-writes.sqlite",argv[2]);remove(path);
  enable_wal(path);owner_writes(path);remove(path);
  snprintf(path,sizeof(path),"%s/library-source-wal-delete.sqlite",argv[2]);remove(path);
  enable_wal(path);deletion(path);remove(path);
  snprintf(path,sizeof(path),"%s/library-source-wal-external.sqlite",argv[2]);remove(path);
  enable_wal(path);external_commit(path);remove(path);
  snprintf(path,sizeof(path),"%s/library-source-wal-replacement.sqlite",argv[2]);remove(path);
  enable_wal(path);external_replacement(path);remove(path);
  snprintf(path,sizeof(path),"%s/library-source-corrupt.sqlite",argv[2]);remove(path);
  corrupt_rows(path);remove(path);
#endif
  publication_consumer(epub,size,font);failed_publication_consumer();free(epub);
  printf("%u public library source checks passed\n",checks);return 0;
}
