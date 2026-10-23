/* SPDX-License-Identifier: MIT */
/* Independent schema/storage contracts. Run only in cloud CTest; fixtures are
   built here from a frozen OPF and separately declared legacy SQL schemas. */
#include "exreader.h"
#include <miniz.h>
#include <sqlite3.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static exr_error error;
static unsigned checks;
#define CHECK(x) do { checks++;if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message);exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)

static void sql(sqlite3 *db,const char *text) { CHECK(sqlite3_exec(db,text,NULL,NULL,NULL)==SQLITE_OK); }
static sqlite3 *database(const char *path) { sqlite3 *db=NULL;CHECK(sqlite3_open(path,&db)==SQLITE_OK);return db; }
static int scalar(const char *path,const char *query) {
  sqlite3 *db=database(path);sqlite3_stmt *s=NULL;int value;
  CHECK(sqlite3_prepare_v2(db,query,-1,&s,NULL)==SQLITE_OK && sqlite3_step(s)==SQLITE_ROW);
  value=sqlite3_column_int(s,0);CHECK(sqlite3_finalize(s)==SQLITE_OK);CHECK(sqlite3_close(db)==SQLITE_OK);return value;
}
static void execute(const char *path,const char *text) { sqlite3 *db=database(path);sql(db,text);CHECK(sqlite3_close(db)==SQLITE_OK); }
static void write_file(const char *path,const void *bytes,size_t size) {
  FILE *file=fopen(path,"wb");CHECK(file && fwrite(bytes,1,size,file)==size && !fclose(file));
}
static void put(mz_zip_archive *zip,const char *path,const char *text) {
  CHECK(mz_zip_writer_add_mem(zip,path,text,strlen(text),MZ_NO_COMPRESSION));
}
static void *epub_fixture(size_t *size,int broken) {
  mz_zip_archive zip={0};void *bytes=NULL;unsigned char padding[256*1024];
  memset(padding,0x6d,sizeof(padding));CHECK(mz_zip_writer_init_heap(&zip,0,0));
  put(&zip,"mimetype","application/epub+zip");
  put(&zip,"META-INF/container.xml","<container xmlns='urn:oasis:names:tc:opendocument:xmlns:container'><rootfiles><rootfile full-path='OPS/book.opf' media-type='application/oebps-package+xml'/></rootfiles></container>");
  put(&zip,"OPS/book.opf","<package xmlns='http://www.idpf.org/2007/opf' version='3.0' unique-identifier='id'><metadata xmlns:dc='http://purl.org/dc/elements/1.1/'><dc:identifier id='id'>storage-contract</dc:identifier><dc:title>Bounded storage fixture</dc:title></metadata><manifest><item id='one' href='one.xhtml' media-type='application/xhtml+xml'/><item id='two' href='two.xhtml' media-type='application/xhtml+xml'/><item id='padding' href='padding.bin' media-type='application/octet-stream'/></manifest><spine><itemref idref='one'/><itemref idref='two'/><itemref idref='one'/></spine></package>");
  put(&zip,"OPS/one.xhtml",broken ? "<html><body><p>not closed" :
      "<html xmlns='http://www.w3.org/1999/xhtml'><body><p>Alpha chapter contains its own local coordinates.</p></body></html>");
  put(&zip,"OPS/two.xhtml","<html xmlns='http://www.w3.org/1999/xhtml'><body><p>Bravo chapter contains different local coordinates.</p></body></html>");
  CHECK(mz_zip_writer_add_mem(&zip,"OPS/padding.bin",padding,sizeof(padding),MZ_NO_COMPRESSION));
  CHECK(mz_zip_writer_finalize_heap_archive(&zip,&bytes,size));CHECK(mz_zip_writer_end(&zip));
  CHECK(bytes && *size>256*1024);return bytes;
}

typedef struct {
  const unsigned char *bytes;size_t size,reads,releases,copy_bytes;
  int copying,fail_first,fail_copy,cancel_first,cancel_copy,cancel_end;
} memory;
static size_t read_at(void *context,uint64_t offset,void *buffer,size_t size) {
  memory *m=context;m->reads++;
  if(m->fail_first || offset>m->size || size>m->size-offset) return 0;
  if(offset==0 && size==65536) { m->copying=1;m->copy_bytes=0; }
  if(m->copying && offset==m->copy_bytes) {
    if(m->fail_copy && m->copy_bytes>=65536) return 0;
    m->copy_bytes+=size;
  }
  memcpy(buffer,m->bytes+(size_t)offset,size);return size;
}
static void release(void *context) { ((memory *)context)->releases++; }
static int cancel(void *context) {
  memory *m=context;return m->cancel_first || (m->cancel_copy && m->copy_bytes>=65536) ||
    (m->cancel_end && m->copy_bytes==m->size);
}
static exr_source source_for(memory *m,const void *bytes,size_t size) {
  exr_source source={0};memset(m,0,sizeof(*m));m->bytes=bytes;m->size=size;
  source.size=size;source.read_at=read_at;source.release=release;source.context=m;
  source.control.cancelled=cancel;source.control.context=m;return source;
}
static void original(exr_library *library,int64_t id,const void *bytes,size_t size) {
  exr_source source={0};unsigned char buffer[509];size_t offset=0;
  OK(exr_library_source(library,id,&source,&error));CHECK(source.size==size);
  while(offset<size) {
    size_t n=size-offset;if(n>sizeof(buffer)) n=sizeof(buffer);
    CHECK(source.read_at(source.context,offset,buffer,n)==n && !memcmp(buffer,(const unsigned char *)bytes+offset,n));offset+=n;
  }
  source.release(source.context);
}
static size_t book_count(exr_library *library) {
  exr_book *books=NULL;size_t count=0;OK(exr_library_books(library,NULL,&books,&count,&error));exr_books_free(books,count);return count;
}
static void mode(exr_library *library,int64_t id,int bounded) {
  exr_library_epub_info info={0};info.struct_size=sizeof(info);
  OK(exr_library_epub_info_get(library,id,&info,&error));
  CHECK(info.struct_size==sizeof(info) && info.bounded_storage==bounded && info.global_extent_known==!bounded);
}
static void same_string(const char *actual,const char *expected) {
  CHECK(actual && expected ? !strcmp(actual,expected) : actual==expected);
}
static void same_location(const exr_epub_location *a,const exr_epub_location *b) {
  CHECK(a->part==b->part && a->selector.start==b->selector.start && a->selector.end==b->selector.end);
  same_string(a->path,b->path);same_string(a->selector.exact,b->selector.exact);
  same_string(a->selector.prefix,b->selector.prefix);same_string(a->selector.suffix,b->selector.suffix);
  same_string(a->selector.chapter,b->selector.chapter);
}
static void stored_location(exr_library *library,int64_t id,const exr_epub_location *expected) {
  exr_epub_location out={0};int present=0;
  OK(exr_library_epub_progress_get(library,id,&out,&present,&error));CHECK(present==1);same_location(&out,expected);
  exr_epub_location_free(&out);CHECK(!out.path && !out.selector.exact);
}
static void clear_location(const exr_epub_location *out) {
  CHECK(!out->part && !out->path && !out->selector.start && !out->selector.end &&
        !out->selector.exact && !out->selector.prefix && !out->selector.suffix && !out->selector.chapter);
}
static void stored_note(exr_library *library,int64_t book,int64_t id,
                        const exr_epub_location *location,const char *text) {
  exr_epub_note *notes=NULL;size_t count=0;
  OK(exr_library_epub_notes(library,book,&notes,&count,&error));
  CHECK(count==1 && notes[0].id==id && notes[0].book_id==book);
  same_location(&notes[0].location,location);same_string(notes[0].text,text);exr_epub_notes_free(notes,count);
}

static void legacy_schema(const char *path,int version,int conflict) {
  sqlite3 *db;remove(path);db=database(path);
  sql(db,"CREATE TABLE books(id INTEGER PRIMARY KEY,format INTEGER NOT NULL,title TEXT NOT NULL,author TEXT NOT NULL DEFAULT '',tags TEXT NOT NULL DEFAULT '',favorite INTEGER NOT NULL DEFAULT 0,status INTEGER NOT NULL DEFAULT 0,position INTEGER NOT NULL DEFAULT 0,text_size INTEGER NOT NULL,source BLOB NOT NULL,cover BLOB);"
         "CREATE TABLE notes(id INTEGER PRIMARY KEY,book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,start INTEGER NOT NULL CHECK(start>=0),end INTEGER NOT NULL CHECK(end>=start),text TEXT NOT NULL);CREATE INDEX notes_book ON notes(book_id);"
         "INSERT INTO books VALUES(11,1,'Legacy title','Legacy author','old tags',1,2,5,21,x'4c6567616379206f726967696e616c20746578742e',x'636f766572');"
         "INSERT INTO notes VALUES(17,11,1,4,'Legacy comment');PRAGMA application_id=1163416131;PRAGMA user_version=1;");
  if(version==6) {
    sql(db,"ALTER TABLE notes ADD COLUMN anchor_exact TEXT;ALTER TABLE notes ADD COLUMN anchor_prefix TEXT;ALTER TABLE notes ADD COLUMN anchor_suffix TEXT;ALTER TABLE notes ADD COLUMN anchor_chapter TEXT;ALTER TABLE notes ADD COLUMN location_state INTEGER NOT NULL DEFAULT 1 CHECK(location_state BETWEEN 0 AND 3);"
           "CREATE TABLE fixed_notes(id INTEGER PRIMARY KEY,book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,page INTEGER NOT NULL,start INTEGER NOT NULL,end INTEGER NOT NULL,text TEXT NOT NULL,page_id TEXT NOT NULL,exact BLOB NOT NULL,prefix BLOB NOT NULL,suffix BLOB NOT NULL);CREATE INDEX fixed_notes_book ON fixed_notes(book_id,page,start);"
           "CREATE TABLE audio_resume(audio_id TEXT PRIMARY KEY,track_id TEXT NOT NULL,offset BLOB NOT NULL,rate REAL NOT NULL);CREATE TABLE audio_marks(id INTEGER PRIMARY KEY,audio_id TEXT NOT NULL,track_id TEXT NOT NULL,offset BLOB NOT NULL,rate REAL NOT NULL,label TEXT NOT NULL);CREATE INDEX audio_marks_key ON audio_marks(audio_id,id);"
           "CREATE TABLE book_progress(book_id INTEGER PRIMARY KEY REFERENCES books(id) ON DELETE CASCADE,position INTEGER NOT NULL,state INTEGER NOT NULL,prefix TEXT,suffix TEXT,chapter TEXT);"
           "CREATE TRIGGER books_progress_changed AFTER UPDATE OF position ON books WHEN OLD.position<>NEW.position BEGIN DELETE FROM book_progress WHERE book_id=NEW.id;END;"
           "INSERT INTO book_progress VALUES(11,5,1,'Legac','y original text.',NULL);PRAGMA user_version=6;");
  }
  if(conflict) sql(db,"CREATE TABLE epub_notes(conflict INTEGER)");
  CHECK(sqlite3_close(db)==SQLITE_OK);
}
static void legacy_preserved(exr_library *library,const char *path,int old_version) {
  exr_book *books=NULL;exr_note *notes=NULL;size_t count=0;exr_anchor progress={0};exr_anchor_state state;
  OK(exr_library_books(library,NULL,&books,&count,&error));
  CHECK(count==1 && books[0].id==11 && books[0].format==EXR_TXT && books[0].position==5);
  CHECK(!strcmp(books[0].title,"Legacy title") && !strcmp(books[0].author,"Legacy author") &&
        !strcmp(books[0].tags,"old tags") && books[0].favorite==1 && books[0].status==2);exr_books_free(books,count);
  original(library,11,"Legacy original text.",21);
  OK(exr_library_notes(library,11,&notes,&count,&error));
  CHECK(count==1 && notes[0].id==17 && notes[0].start==1 && notes[0].end==4 && !strcmp(notes[0].text,"Legacy comment"));exr_notes_free(notes,count);
  OK(exr_library_progress_get(library,11,&progress,&state,&error));
  CHECK(progress.start==5 && progress.end==5 && state==(old_version==6 ? EXR_ANCHOR_FOUND : EXR_ANCHOR_LEGACY));
  if(old_version==6) { same_string(progress.prefix,"Legac");same_string(progress.suffix,"y original text."); }
  exr_anchor_free(&progress);
  CHECK(scalar(path,"SELECT hex(cover)='636F766572' FROM books WHERE id=11")==1);
  CHECK(scalar(path,"SELECT text_size FROM books WHERE id=11")==21);
  CHECK(scalar(path,"SELECT count(*) FROM epub_bounded_books")==0 && scalar(path,"SELECT count(*) FROM epub_progress")==0 &&
        scalar(path,"SELECT count(*) FROM epub_notes")==0);
}
static void migrations(const char *directory) {
  char path[4096];exr_library *library=NULL;int version;
  for(version=1;version<=6;version+=5) {
    snprintf(path,sizeof(path),"%s/epub-storage-migrate-%d.sqlite",directory,version);legacy_schema(path,version,1);
    CHECK(exr_library_open(path,&library,&error)==EXR_DATABASE && !library);
    CHECK(scalar(path,"PRAGMA user_version")==version);
    CHECK(scalar(path,"SELECT count(*) FROM sqlite_master WHERE name='epub_bounded_books'")==0);
    CHECK(scalar(path,"SELECT count(*) FROM sqlite_master WHERE name='epub_progress'")==0);
    CHECK(scalar(path,"SELECT count(*) FROM books WHERE id=11 AND position=5 AND title='Legacy title'")==1);
    CHECK(scalar(path,"SELECT count(*) FROM notes WHERE id=17 AND text='Legacy comment'")==1);
    if(version==1) CHECK(scalar(path,"SELECT count(*) FROM pragma_table_info('notes') WHERE name='anchor_exact'")==0);
    execute(path,"DROP TABLE epub_notes");OK(exr_library_open(path,&library,&error));
    CHECK(scalar(path,"PRAGMA user_version")==7);legacy_preserved(library,path,version);exr_library_close(library);library=NULL;
    OK(exr_library_open(path,&library,&error));legacy_preserved(library,path,version);exr_library_close(library);library=NULL;remove(path);
  }
}

static void deduplication(const void *bytes,size_t size,const char *file) {
  exr_library *library=NULL;exr_document *document=NULL;exr_anchor point={0};exr_note note={0};
  exr_source source;memory m;int64_t legacy=0,bounded=0,again=0,note_id=0;int created=99;
  OK(exr_library_open(":memory:",&library,&error));
  OK(exr_library_import(library,EXR_EPUB,bytes,size,"Legacy EPUB",&legacy,&error));mode(library,legacy,0);
  OK(exr_library_document(library,legacy,&document,&error));OK(exr_anchor_create(document,5,5,&point,&error));
  OK(exr_library_progress(library,legacy,&point,&error));note.book_id=legacy;note.start=1;note.end=4;note.text="Keep old note";
  OK(exr_library_note(library,&note,&note_id,&error));
  source=source_for(&m,bytes,size);
  OK(exr_library_import_source_unique(library,EXR_EPUB,&source,"Do not rename",&again,&created,&error));
  CHECK(again==legacy && created==0 && !m.releases);mode(library,again,0);
  OK(exr_library_import_file_unique(library,EXR_EPUB,file,"Do not rename",&again,&created,&error));CHECK(again==legacy && !created);
  { exr_anchor out={0};exr_anchor_state state;exr_note *notes=NULL;size_t count=0;
    OK(exr_library_progress_get(library,legacy,&out,&state,&error));CHECK(state==EXR_ANCHOR_FOUND && out.start==5);exr_anchor_free(&out);
    OK(exr_library_notes(library,legacy,&notes,&count,&error));CHECK(count==1 && notes[0].id==note_id && !strcmp(notes[0].text,"Keep old note"));exr_notes_free(notes,count); }
  CHECK(book_count(library)==1);exr_document_free(document);exr_anchor_free(&point);exr_library_close(library);
  OK(exr_library_open(":memory:",&library,&error));source=source_for(&m,bytes,size);
  OK(exr_library_import_source_unique(library,EXR_EPUB,&source,"Bounded EPUB",&bounded,&created,&error));CHECK(created==1 && !m.releases);mode(library,bounded,1);
  OK(exr_library_import_file_unique(library,EXR_EPUB,file,NULL,&again,&created,&error));CHECK(again==bounded && !created);
  OK(exr_library_import_unique(library,EXR_EPUB,bytes,size,NULL,&again,&created,&error));CHECK(again==bounded && !created);mode(library,again,1);
  CHECK(book_count(library)==1);original(library,bounded,bytes,size);
  OK(exr_library_import_file(library,EXR_EPUB,file,"Plain file",&again,&error));CHECK(again!=bounded);mode(library,again,1);
  source=source_for(&m,bytes,size);OK(exr_library_import_source(library,EXR_EPUB,&source,"Plain source",&again,&error));CHECK(!m.releases);mode(library,again,1);
  CHECK(book_count(library)==3);exr_library_close(library);
}

static void reject_location(exr_library *library,int64_t id,const exr_epub_location *bad,
                            exr_status expected,const exr_epub_location *saved) {
  CHECK(exr_library_epub_progress(library,id,bad,&error)==expected);stored_location(library,id,saved);
}
static void progress_and_backup(const void *bytes,size_t size,const char *directory) {
  char path[4096],backup[4096];exr_library *library=NULL,*restored=NULL;exr_publication *publication=NULL;
  const exr_part *parts;size_t count=0,i;exr_source source;memory m;int64_t id=0,note_id=0;exr_epub_location points[3]={{0}},out={0},bad,note_location={0};
  int present=99;exr_library_epub_info info={0};
  snprintf(path,sizeof(path),"%s/epub-storage-progress.sqlite",directory);snprintf(backup,sizeof(backup),"%s/epub-storage-backup.sqlite",directory);remove(path);remove(backup);
  OK(exr_library_open(path,&library,&error));source=source_for(&m,bytes,size);
  OK(exr_library_import_source(library,EXR_EPUB,&source,NULL,&id,&error));mode(library,id,1);
  OK(exr_publication_open_memory(EXR_EPUB,bytes,size,&publication,&error));parts=exr_publication_parts(publication,&count);
  CHECK(parts && count==3 && !strcmp(parts[0].path,parts[2].path) && strcmp(parts[0].path,parts[1].path));
  OK(exr_library_epub_progress_get(library,id,&out,&present,&error));CHECK(present==0);clear_location(&out);
  for(i=0;i<3;i++) {
    exr_document *chapter=NULL;points[i].part=i;points[i].path=(char *)parts[i].path;
    OK(exr_publication_load(publication,i,&chapter,&error));OK(exr_anchor_create(chapter,5,5,&points[i].selector,&error));exr_document_free(chapter);
    OK(exr_library_epub_progress(library,id,&points[i],&error));stored_location(library,id,&points[i]);
  }
  bad=points[2];bad.part=SIZE_MAX;reject_location(library,id,&bad,EXR_ARGUMENT,&points[2]);
  bad=points[2];bad.part=3;reject_location(library,id,&bad,EXR_ARGUMENT,&points[2]);
  bad=points[2];bad.path=points[1].path;reject_location(library,id,&bad,EXR_ARGUMENT,&points[2]);
  bad=points[2];bad.path="../escape.xhtml";reject_location(library,id,&bad,EXR_ARGUMENT,&points[2]);
  bad=points[2];bad.selector.exact=NULL;reject_location(library,id,&bad,EXR_ARGUMENT,&points[2]);
  bad=points[2];bad.selector.exact="a";reject_location(library,id,&bad,EXR_ARGUMENT,&points[2]);
  bad=points[2];bad.selector.end++;reject_location(library,id,&bad,EXR_ARGUMENT,&points[2]);
  bad=points[2];bad.selector.start=bad.selector.end=SIZE_MAX;reject_location(library,id,&bad,EXR_ARGUMENT,&points[2]);
  bad=points[2];bad.selector.chapter=points[1].path;reject_location(library,id,&bad,EXR_ARGUMENT,&points[2]);
  bad=points[2];bad.selector.prefix="\xff";reject_location(library,id,&bad,EXR_ENCODING,&points[2]);
  /* Storage checks route/structure, not whether this number resolves in text. */
  bad=points[2];bad.selector.start=bad.selector.end=1000000;
  OK(exr_library_epub_progress(library,id,&bad,&error));stored_location(library,id,&bad);
  OK(exr_library_epub_progress(library,id,&points[2],&error));
  info.struct_size=sizeof(info);info.bounded_storage=info.global_extent_known=99;
  CHECK(exr_library_epub_info_get(library,INT64_MAX,&info,&error)!=EXR_OK && !info.bounded_storage && !info.global_extent_known);
  { size_t prefix_size=sizeof(size_t);unsigned char *short_info=malloc(prefix_size+16);
    CHECK(short_info);memset(short_info,0xa5,prefix_size+16);memcpy(short_info,&prefix_size,sizeof(prefix_size));
    CHECK(exr_library_epub_info_get(library,id,(exr_library_epub_info *)short_info,&error)==EXR_ARGUMENT);
    for(i=prefix_size;i<prefix_size+16;i++) CHECK(short_info[i]==0xa5);
    free(short_info); }
  out.part=99;present=99;CHECK(exr_library_epub_progress_get(library,INT64_MAX,&out,&present,&error)!=EXR_OK && !present);clear_location(&out);
  { exr_book *books=NULL;exr_note note={0},*notes=NULL;exr_anchor global={0};exr_anchor_state state;exr_library_relocation relocation={0};int64_t note_id=99;
    OK(exr_library_books(library,NULL,&books,&count,&error));CHECK(count==1 && books[0].position==0);
    CHECK(scalar(path,"SELECT text_size FROM books")==0);
    books[0].favorite=1;OK(exr_library_update(library,books,&error));books[0].position=1;
    CHECK(exr_library_update(library,books,&error)==EXR_UNSUPPORTED);exr_books_free(books,count);
    CHECK(exr_library_progress(library,id,&points[0].selector,&error)==EXR_UNSUPPORTED);
    CHECK(exr_library_progress_get(library,id,&global,&state,&error)==EXR_UNSUPPORTED);exr_anchor_free(&global);
    CHECK(exr_library_clear_progress(library,id,&error)==EXR_UNSUPPORTED);
    note.book_id=id;note.start=0;note.end=1;note.text="Wrong coordinate domain";
    CHECK(exr_library_note(library,&note,&note_id,&error)==EXR_UNSUPPORTED && !note_id);
    count=99;CHECK(exr_library_notes(library,id,&notes,&count,&error)==EXR_UNSUPPORTED && !notes && !count);
    CHECK(exr_library_reanchor(library,id,0,NULL,&relocation,&error)==EXR_UNSUPPORTED);exr_library_relocation_free(&relocation); }
  stored_location(library,id,&points[2]);original(library,id,bytes,size);
  { exr_document *chapter=NULL;exr_epub_note note={0},change;int64_t changed=99,other_id=0;
    OK(exr_publication_load(publication,2,&chapter,&error));note_location.part=2;note_location.path=points[2].path;
    OK(exr_anchor_create(chapter,1,5,&note_location.selector,&error));exr_document_free(chapter);
    note.book_id=id;note.location=note_location;note.text="Chapter comment";
    OK(exr_library_epub_note(library,&note,&note_id,&error));CHECK(note_id>0);stored_note(library,id,note_id,&note_location,note.text);
    change=note;change.id=note_id;change.text="Edited comment";change.location.part=SIZE_MAX;
    change.location.path="ignored for comment-only";change.location.selector.exact=NULL;
    OK(exr_library_epub_note(library,&change,&changed,&error));CHECK(changed==note_id);
    stored_note(library,id,note_id,&note_location,"Edited comment");
    change=note;change.id=note_id;change.location.selector.exact="wrong length";changed=99;
    CHECK(exr_library_epub_note(library,&change,&changed,&error)==EXR_ARGUMENT && !changed);
    stored_note(library,id,note_id,&note_location,"Edited comment");
    source=source_for(&m,bytes,size);OK(exr_library_import_source(library,EXR_EPUB,&source,"Other note owner",&other_id,&error));
    change=note;change.id=note_id;change.book_id=other_id;changed=99;
    CHECK(exr_library_epub_note(library,&change,&changed,&error)==EXR_ARGUMENT && !changed);
    stored_note(library,id,note_id,&note_location,"Edited comment");
    OK(exr_library_delete(library,other_id,&error));
    /* A legacy note ID operation must not remove a new-coordinate note. */
    OK(exr_library_remove_note(library,note_id,&error));stored_note(library,id,note_id,&note_location,"Edited comment");
    OK(exr_library_remove_epub_note(library,note_id,&error));
    { exr_epub_note *none=NULL;size_t n=99;OK(exr_library_epub_notes(library,id,&none,&n,&error));CHECK(!none && !n); }
    OK(exr_library_epub_note(library,&note,&note_id,&error));stored_note(library,id,note_id,&note_location,"Chapter comment"); }
  OK(exr_library_backup(library,backup,&error));exr_library_close(library);library=NULL;
  OK(exr_library_open(backup,&restored,&error));mode(restored,id,1);stored_location(restored,id,&points[2]);original(restored,id,bytes,size);
  stored_note(restored,id,note_id,&note_location,"Chapter comment");
  CHECK(scalar(backup,"PRAGMA user_version")==7 && scalar(backup,"SELECT count(*) FROM epub_bounded_books")==1);
  exr_library_close(restored);OK(exr_library_open(path,&library,&error));stored_location(library,id,&points[2]);
  stored_note(library,id,note_id,&note_location,"Chapter comment");
  OK(exr_library_delete(library,id,&error));CHECK(book_count(library)==0);
  CHECK(scalar(path,"SELECT count(*) FROM epub_progress")==0 && scalar(path,"SELECT count(*) FROM epub_bounded_books")==0 &&
        scalar(path,"SELECT count(*) FROM epub_notes")==0);exr_library_close(library);
  exr_anchor_free(&note_location.selector);
  for(i=0;i<3;i++) exr_anchor_free(&points[i].selector);
  exr_publication_free(publication);remove(path);remove(backup);
}

static void failures(const void *bytes,size_t size,const char *directory) {
  char path[4096];exr_library *library=NULL;exr_source source;memory m;int64_t id=99;int created=99,which;
  snprintf(path,sizeof(path),"%s/epub-storage-failures.sqlite",directory);remove(path);OK(exr_library_open(path,&library,&error));
  for(which=0;which<5;which++) {
    exr_status expected=which<3 ? EXR_CANCELLED : EXR_IO;
    source=source_for(&m,bytes,size);m.cancel_first=which==0;m.cancel_copy=which==1;m.cancel_end=which==2;m.fail_first=which==3;m.fail_copy=which==4;
    id=99;created=99;
    CHECK(exr_library_import_source_unique(library,EXR_EPUB,&source,NULL,&id,&created,&error)==expected);
    CHECK(!id && !created && !m.releases && book_count(library)==0);
    if(which==1 || which==4) CHECK(m.copy_bytes>=65536);
    if(which==2) CHECK(m.copy_bytes==size);
    CHECK(scalar(path,"SELECT count(*) FROM books")==0 && scalar(path,"SELECT count(*) FROM epub_bounded_books")==0);
  }
  /* A marker failure occurs after the original row/blob insert; both ordinary
     and unique imports must roll back the entire book, not just the marker. */
  execute(path,"CREATE TRIGGER reject_epub_marker BEFORE INSERT ON epub_bounded_books BEGIN SELECT RAISE(ABORT,'marker rejected');END");
  source=source_for(&m,bytes,size);id=99;CHECK(exr_library_import_source(library,EXR_EPUB,&source,NULL,&id,&error)==EXR_DATABASE && !id);
  CHECK(!m.releases && book_count(library)==0 && scalar(path,"SELECT count(*) FROM epub_bounded_books")==0);
  source=source_for(&m,bytes,size);id=99;created=99;
  CHECK(exr_library_import_source_unique(library,EXR_EPUB,&source,NULL,&id,&created,&error)==EXR_DATABASE && !id && !created);
  CHECK(!m.releases && book_count(library)==0 && scalar(path,"SELECT count(*) FROM epub_bounded_books")==0);
  execute(path,"DROP TRIGGER reject_epub_marker");source=source_for(&m,bytes,size);
  OK(exr_library_import_source_unique(library,EXR_EPUB,&source,NULL,&id,&created,&error));CHECK(created && !m.releases);mode(library,id,1);
  source=source_for(&m,bytes,size);m.fail_copy=1;id=99;created=99;
  CHECK(exr_library_import_source_unique(library,EXR_EPUB,&source,NULL,&id,&created,&error)==EXR_IO && !id && !created);
  CHECK(m.copy_bytes>=65536 && !m.releases && book_count(library)==1);
  source=source_for(&m,bytes,size);source.size=UINT64_C(128)*1024*1024+1;id=99;
  CHECK(exr_library_import_source(library,EXR_EPUB,&source,NULL,&id,&error)==EXR_LIMIT && !id && !m.reads && !m.releases);
  exr_library_close(library);remove(path);
}
static void index_only(void) {
  exr_library *library=NULL;exr_document *document=NULL;exr_publication *publication=NULL;
  memory m;exr_source source;size_t size=0;void *bytes=epub_fixture(&size,1);int64_t id=0;
  OK(exr_library_open(":memory:",&library,&error));source=source_for(&m,bytes,size);
  OK(exr_library_import_source(library,EXR_EPUB,&source,NULL,&id,&error));CHECK(!m.releases);mode(library,id,1);
  OK(exr_library_source(library,id,&source,&error));OK(exr_publication_open_source(&source,&publication,&error));
  CHECK(exr_publication_load(publication,0,&document,&error)==EXR_FORMAT && !document);
  exr_publication_free(publication);
  CHECK(exr_library_document(library,id,&document,&error)==EXR_FORMAT && !document);mode(library,id,1);
  exr_library_close(library);mz_free(bytes);
}
static void corrupt_format(const void *bytes,size_t size,const char *directory) {
  char path[4096];exr_library *library=NULL;exr_library_epub_info info={0};
  exr_source source;memory m;int64_t id=0;int present=99;
  exr_epub_location saved={0},changed,out={0};
  snprintf(path,sizeof(path),"%s/epub-storage-format.sqlite",directory);remove(path);
  OK(exr_library_open(path,&library,&error));source=source_for(&m,bytes,size);
  OK(exr_library_import_source(library,EXR_EPUB,&source,NULL,&id,&error));
  saved.part=0;saved.path="OPS/one.xhtml";saved.selector.start=saved.selector.end=5;
  saved.selector.exact="";saved.selector.prefix="Alpha";saved.selector.suffix=" chapter";
  saved.selector.chapter=saved.path;OK(exr_library_epub_progress(library,id,&saved,&error));
  /* An INTEGER outside the enum range must not wrap through column_int() to
     EXR_EPUB. This is deliberately malformed persistent storage. */
  execute(path,"UPDATE books SET format=4294967300");
  info.struct_size=sizeof(info);info.bounded_storage=info.global_extent_known=99;
  CHECK(exr_library_epub_info_get(library,id,&info,&error)==EXR_DATABASE);
  CHECK(info.struct_size==sizeof(info) && !info.bounded_storage && !info.global_extent_known);
  changed=saved;changed.selector.start=changed.selector.end=6;
  CHECK(exr_library_epub_progress(library,id,&changed,&error)==EXR_DATABASE);
  CHECK(scalar(path,"SELECT position FROM epub_progress")==5);
  out.part=99;out.path="dirty";out.selector.start=out.selector.end=99;
  out.selector.exact="dirty";out.selector.prefix="dirty";out.selector.suffix="dirty";out.selector.chapter="dirty";
  CHECK(exr_library_epub_progress_get(library,id,&out,&present,&error)==EXR_DATABASE && !present);clear_location(&out);
  exr_library_close(library);remove(path);
}
int main(int argc,char **argv) {
  char file[4096];void *bytes;size_t size=0;
  CHECK(argc==2);snprintf(file,sizeof(file),"%s/epub-storage-fixture.epub",argv[1]);bytes=epub_fixture(&size,0);write_file(file,bytes,size);
  migrations(argv[1]);deduplication(bytes,size,file);progress_and_backup(bytes,size,argv[1]);failures(bytes,size,argv[1]);index_only();corrupt_format(bytes,size,argv[1]);
  remove(file);mz_free(bytes);printf("%u independent EPUB storage checks passed\n",checks);return 0;
}
