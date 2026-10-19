/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include <sqlite3.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error; static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static void sql(const char *path,const char *query) { sqlite3 *db=NULL; CHECK(sqlite3_open(path,&db)==SQLITE_OK); CHECK(sqlite3_exec(db,query,NULL,NULL,NULL)==SQLITE_OK); CHECK(sqlite3_close(db)==SQLITE_OK); }
static int scalar(const char *path,const char *query) { sqlite3 *db=NULL; sqlite3_stmt *s=NULL; int value; CHECK(sqlite3_open(path,&db)==SQLITE_OK); CHECK(sqlite3_prepare_v2(db,query,-1,&s,NULL)==SQLITE_OK && sqlite3_step(s)==SQLITE_ROW); value=sqlite3_column_int(s,0); sqlite3_finalize(s); CHECK(sqlite3_close(db)==SQLITE_OK); return value; }
static void progress(exr_library *l,int64_t id,exr_document *doc,exr_anchor_state expected,size_t position) {
  exr_anchor a={0}; exr_anchor_state state; exr_anchor_match match;
  OK(exr_library_progress_get(l,id,&a,&state,&error)); CHECK(state==expected && a.start==position && a.end==position);
  if(expected==EXR_ANCHOR_FOUND) { CHECK(a.exact && !*a.exact); OK(exr_anchor_resolve(doc,&a,&match,&error)); CHECK(match.state==EXR_ANCHOR_FOUND && match.start==position); }
  else CHECK(!a.exact);
  exr_anchor_free(&a);
}
int main(int argc,char **argv) {
  const char *text="First paragraph with Unicode 中文. Second paragraph for stable progress.";
  char path[4096],backup[4096],migration[4096]; exr_library *l=NULL,*copy=NULL; exr_document *doc=NULL; exr_anchor a={0},b={0},out={0},bad; exr_anchor_state state; exr_book *books=NULL; size_t n; int64_t book,pdf;
  CHECK(argc==3); snprintf(path,sizeof(path),"%s/progress-library.sqlite",argv[2]); snprintf(backup,sizeof(backup),"%s/progress-backup.sqlite",argv[2]); snprintf(migration,sizeof(migration),"%s/progress-migrate.sqlite",argv[2]); remove(path); remove(backup); remove(migration);
  OK(exr_library_open(path,&l,&error)); CHECK(scalar(path,"PRAGMA user_version")==6); OK(exr_library_import(l,EXR_TXT,text,strlen(text),"Book",&book,&error)); OK(exr_library_document(l,book,&doc,&error)); progress(l,book,doc,EXR_ANCHOR_LEGACY,0);
  OK(exr_anchor_create(doc,5,5,&a,&error)); OK(exr_anchor_create(doc,8,8,&b,&error)); OK(exr_library_progress(l,book,&a,&error)); progress(l,book,doc,EXR_ANCHOR_FOUND,5);
  { int64_t reused; int created; OK(exr_library_import_unique(l,EXR_TXT,text,strlen(text),"Ignored",&reused,&created,&error)); CHECK(reused==book && !created); progress(l,book,doc,EXR_ANCHOR_FOUND,5); }
  OK(exr_library_books(l,"Book",&books,&n,&error)); CHECK(n==1 && books[0].position==5); books[0].favorite=1; books[0].title[0]='L'; OK(exr_library_update(l,&books[0],&error)); progress(l,book,doc,EXR_ANCHOR_FOUND,5);
  books[0].position=6; OK(exr_library_update(l,&books[0],&error)); progress(l,book,doc,EXR_ANCHOR_LEGACY,6); exr_books_free(books,n); OK(exr_library_progress(l,book,&a,&error));
  sql(path,"CREATE TRIGGER fail_progress BEFORE INSERT ON book_progress BEGIN SELECT RAISE(ABORT,'blocked progress');END;");
  CHECK(exr_library_progress(l,book,&b,&error)==EXR_DATABASE); progress(l,book,doc,EXR_ANCHOR_FOUND,5); sql(path,"DROP TRIGGER fail_progress;");
  sql(path,"CREATE TABLE fail_commit(parent INTEGER REFERENCES books(id) DEFERRABLE INITIALLY DEFERRED);CREATE TRIGGER defer_progress AFTER INSERT ON book_progress BEGIN INSERT INTO fail_commit VALUES(999999);END;");
  CHECK(exr_library_progress(l,book,&b,&error)==EXR_DATABASE); progress(l,book,doc,EXR_ANCHOR_FOUND,5); sql(path,"DROP TRIGGER defer_progress;DROP TABLE fail_commit;");
  bad=a; bad.exact="nonempty"; CHECK(exr_library_progress(l,book,&bad,&error)==EXR_ARGUMENT); bad=a; bad.prefix="\xff"; CHECK(exr_library_progress(l,book,&bad,&error)==EXR_ENCODING);
  bad=a; bad.start=bad.end=10000; CHECK(exr_library_progress(l,book,&bad,&error)==EXR_ARGUMENT); CHECK(exr_library_progress(l,999999,&a,&error)==EXR_ARGUMENT);
  CHECK(exr_library_progress_get(l,999999,&out,&state,&error)==EXR_ARGUMENT && !out.exact && state==EXR_ANCHOR_MISSING);
  sql(path,"UPDATE book_progress SET prefix=CAST(x'ff' AS TEXT)"); CHECK(exr_library_progress_get(l,book,&out,&state,&error)==EXR_DATABASE && !out.exact && !out.prefix && state==EXR_ANCHOR_MISSING); OK(exr_library_progress(l,book,&a,&error));
  sql(path,"UPDATE book_progress SET position=1"); CHECK(exr_library_progress_get(l,book,&out,&state,&error)==EXR_DATABASE && !out.exact); OK(exr_library_progress(l,book,&a,&error));
  OK(exr_library_clear_progress(l,book,&error)); progress(l,book,doc,EXR_ANCHOR_LEGACY,5); OK(exr_library_progress(l,book,&a,&error));
  exr_library_close(l); OK(exr_library_open(path,&l,&error)); progress(l,book,doc,EXR_ANCHOR_FOUND,5);
  OK(exr_library_backup(l,backup,&error)); OK(exr_library_open(backup,&copy,&error)); progress(copy,book,doc,EXR_ANCHOR_FOUND,5); exr_library_close(copy);
  OK(exr_library_backup(l,migration,&error));
  sql(migration,"DROP TRIGGER books_progress_changed;DROP TABLE book_progress;ALTER TABLE notes DROP COLUMN location_state;CREATE TRIGGER books_progress_changed AFTER UPDATE OF position ON books BEGIN SELECT 1;END;PRAGMA user_version=4;");
  CHECK(exr_library_open(migration,&copy,&error)==EXR_DATABASE && !copy); CHECK(scalar(migration,"PRAGMA user_version")==4 && !scalar(migration,"SELECT count(*) FROM sqlite_master WHERE name='book_progress'"));
  sql(migration,"DROP TRIGGER books_progress_changed;"); OK(exr_library_open(migration,&copy,&error)); CHECK(scalar(migration,"PRAGMA user_version")==6); progress(copy,book,doc,EXR_ANCHOR_LEGACY,5); exr_library_close(copy);
  { char file[4096]; FILE *f; void *bytes; long length; snprintf(file,sizeof(file),"%s/pdf-public-text.pdf",argv[1]); f=fopen(file,"rb"); CHECK(f && !fseek(f,0,SEEK_END)); length=ftell(f); CHECK(length>0); rewind(f); bytes=malloc((size_t)length); CHECK(bytes && fread(bytes,1,(size_t)length,f)==(size_t)length); fclose(f);
    OK(exr_library_import(l,EXR_PDF,bytes,(size_t)length,NULL,&pdf,&error)); free(bytes); CHECK(exr_library_progress(l,pdf,&a,&error)==EXR_FORMAT); CHECK(exr_library_progress_get(l,pdf,&out,&state,&error)==EXR_FORMAT && !out.exact);
  }
  OK(exr_library_delete(l,book,&error)); CHECK(!scalar(path,"SELECT count(*) FROM book_progress")); CHECK(exr_library_progress_get(l,book,&out,&state,&error)==EXR_ARGUMENT && !out.exact);
  exr_anchor_free(&a); exr_anchor_free(&b); exr_document_free(doc); exr_library_close(l); remove(path); remove(backup); remove(migration); printf("%u stable progress checks passed\n",checks); return 0;
}
