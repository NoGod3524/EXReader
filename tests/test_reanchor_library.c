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
static int scalar(const char *path,const char *query) { sqlite3 *db=NULL; sqlite3_stmt *s=NULL; int n; CHECK(sqlite3_open(path,&db)==SQLITE_OK); CHECK(sqlite3_prepare_v2(db,query,-1,&s,NULL)==SQLITE_OK && sqlite3_step(s)==SQLITE_ROW); n=sqlite3_column_int(s,0); sqlite3_finalize(s); CHECK(sqlite3_close(db)==SQLITE_OK); return n; }
/* Substitute a revision without refreshing its old projected extent/positions. */
static void revision(const char *path,int64_t id,const char *text) { sqlite3 *db=NULL; sqlite3_stmt *s=NULL; CHECK(sqlite3_open(path,&db)==SQLITE_OK); CHECK(sqlite3_prepare_v2(db,"UPDATE books SET source=?1 WHERE id=?2",-1,&s,NULL)==SQLITE_OK); CHECK(sqlite3_bind_blob(s,1,text,(int)strlen(text),SQLITE_STATIC)==SQLITE_OK && sqlite3_bind_int64(s,2,id)==SQLITE_OK && sqlite3_step(s)==SQLITE_DONE); sqlite3_finalize(s); CHECK(sqlite3_close(db)==SQLITE_OK); }
static exr_note *note_id(exr_note *notes,size_t n,int64_t id) { size_t i; for(i=0;i<n;i++) if(notes[i].id==id) return &notes[i]; CHECK(0); return NULL; }
static exr_anchor_match match_id(const exr_library_relocation *r,int64_t id) { size_t i; for(i=0;i<r->note_count;i++) if(r->notes[i].note_id==id) return r->notes[i].match; CHECK(0); return (exr_anchor_match){0,0,0}; }
static int cancel(void *context) { return *(int *)context; }
static void final_cancel(void *context,exr_stage stage,uint64_t done,uint64_t total) { (void)stage; if(total && done==total) *(int *)context=1; }
static void old_state(exr_library *l,int64_t book,int64_t keep,size_t position,size_t start) { exr_note *notes=NULL; exr_anchor p={0}; exr_anchor_state state; size_t n; OK(exr_library_progress_get(l,book,&p,&state,&error)); CHECK(state==EXR_ANCHOR_FOUND && p.start==position); exr_anchor_free(&p); OK(exr_library_notes(l,book,&notes,&n,&error)); CHECK(note_id(notes,n,keep)->start==start); exr_notes_free(notes,n); }
int main(int argc,char **argv) {
  char path[4096],backup[4096],migration[4096],old[512],current[512],query[1024],ambiguous[256],twice[512];
  exr_library *l=NULL,*copy=NULL; exr_document *doc=NULL; exr_anchor progress={0},p={0}; exr_anchor_state state; exr_anchor_match match;
  exr_note input={0},*notes=NULL,*selected; exr_library_relocation report={0}; exr_book *books=NULL; int64_t book,keep,lost,legacy,amb,amb_note,raw,invalid_id; void *blob=NULL; size_t blob_size; size_t n,keep_start,lost_start,position,current_start; int stopped=0; exr_control control={cancel,final_cancel,&stopped};
  CHECK(argc==2); snprintf(path,sizeof(path),"%s/reanchor-library.sqlite",argv[1]); snprintf(backup,sizeof(backup),"%s/reanchor-backup.sqlite",argv[1]); snprintf(migration,sizeof(migration),"%s/reanchor-migrate.sqlite",argv[1]); remove(path); remove(backup); remove(migration);
  memset(old,'L',80); strcpy(old+80,"Keep target"); memset(old+91,'R',80); strcpy(old+171,"Gone target"); memset(old+182,'T',80); old[262]=0; snprintf(current,sizeof(current),"Inserted.\n%.*s",171,old);
  OK(exr_library_open(path,&l,&error)); OK(exr_library_import(l,EXR_TXT,old,strlen(old),"Relocate",&book,&error)); OK(exr_library_document(l,book,&doc,&error));
  keep_start=(size_t)(strstr(exr_document_text(doc,NULL),"Keep target")-exr_document_text(doc,NULL)); lost_start=(size_t)(strstr(exr_document_text(doc,NULL),"Gone target")-exr_document_text(doc,NULL)); position=keep_start+14;
  input.book_id=book; input.start=keep_start; input.end=keep_start+11; input.text="kept comment"; OK(exr_library_note(l,&input,&keep,&error)); input.start=lost_start; input.end=lost_start+11; input.text="lost comment"; OK(exr_library_note(l,&input,&lost,&error));
  snprintf(query,sizeof(query),"INSERT INTO notes(book_id,start,end,text)VALUES(%lld,0,1,'legacy comment');",(long long)book); sql(path,query); legacy=scalar(path,"SELECT id FROM notes WHERE text='legacy comment'");
  OK(exr_anchor_create(doc,position,position,&progress,&error)); OK(exr_library_progress(l,book,&progress,&error)); exr_document_free(doc); doc=NULL;
  revision(path,book,current);
  sql(path,"CREATE TRIGGER block_relocation BEFORE UPDATE OF location_state ON notes WHEN NEW.location_state=0 BEGIN SELECT RAISE(ABORT,'blocked relocation');END;");
  CHECK(exr_library_reanchor(l,book,0,NULL,&report,&error)==EXR_DATABASE && !report.notes && !report.note_count); old_state(l,book,keep,position,keep_start); sql(path,"DROP TRIGGER block_relocation;");
  sql(path,"CREATE TABLE defer_relocation(parent INTEGER REFERENCES books(id) DEFERRABLE INITIALLY DEFERRED);CREATE TRIGGER defer_reloc AFTER UPDATE OF text_size ON books BEGIN INSERT INTO defer_relocation VALUES(999999);END;");
  CHECK(exr_library_reanchor(l,book,0,NULL,&report,&error)==EXR_DATABASE && !report.notes); old_state(l,book,keep,position,keep_start); sql(path,"DROP TRIGGER defer_reloc;DROP TABLE defer_relocation;");
  CHECK(exr_library_reanchor(l,book,0,&control,&report,&error)==EXR_CANCELLED && !report.notes); old_state(l,book,keep,position,keep_start);
  CHECK(exr_library_reanchor(l,book,0,&control,&report,&error)==EXR_CANCELLED && !report.notes); stopped=0;
  OK(exr_library_reanchor(l,book,0,NULL,&report,&error)); CHECK(report.previous_size==262 && report.text_size==strlen(current) && report.position==position+10 && report.progress.state==EXR_ANCHOR_FOUND && report.note_count==3);
  CHECK(match_id(&report,keep).state==EXR_ANCHOR_FOUND && match_id(&report,keep).start==keep_start+10 && match_id(&report,lost).state==EXR_ANCHOR_MISSING && match_id(&report,legacy).state==EXR_ANCHOR_LEGACY); current_start=keep_start+10; exr_library_relocation_free(&report);
  OK(exr_library_blob(l,book,0,&blob,&blob_size,&error)); CHECK(blob_size==strlen(current) && !memcmp(blob,current,blob_size)); exr_free(blob);
  OK(exr_library_notes(l,book,&notes,&n,&error)); CHECK(n==3); selected=note_id(notes,n,lost); CHECK(selected->start==SIZE_MAX && selected->end==SIZE_MAX && selected->anchor.start==lost_start && !strcmp(selected->anchor.exact,"Gone target") && !strcmp(selected->text,"lost comment")); selected=note_id(notes,n,legacy); CHECK(selected->start==SIZE_MAX && !selected->anchor.exact && selected->anchor.start==0); exr_notes_free(notes,n);
  OK(exr_library_note_text(l,legacy,"legacy edited",&error)); CHECK(exr_library_note_text(l,legacy,"\xff",&error)==EXR_ENCODING);
  input=(exr_note){0}; input.id=lost; input.book_id=book; input.start=current_start; input.end=current_start+11; input.text="\xff"; CHECK(exr_library_note(l,&input,&invalid_id,&error)==EXR_ENCODING); input.text="recovered comment"; OK(exr_library_note(l,&input,&lost,&error));
  OK(exr_library_notes(l,book,&notes,&n,&error)); CHECK(note_id(notes,n,lost)->start==current_start && !strcmp(note_id(notes,n,legacy)->text,"legacy edited")); exr_notes_free(notes,n);
  OK(exr_library_reanchor(l,book,0,NULL,&report,&error)); CHECK(match_id(&report,lost).state==EXR_ANCHOR_FOUND && match_id(&report,legacy).state==EXR_ANCHOR_LEGACY); exr_library_relocation_free(&report);
  OK(exr_library_backup(l,backup,&error)); OK(exr_library_open(backup,&copy,&error)); OK(exr_library_notes(copy,book,&notes,&n,&error)); CHECK(n==3 && note_id(notes,n,legacy)->start==SIZE_MAX); exr_notes_free(notes,n); exr_library_close(copy);
  /* Downgrade a clean copy to the actual v5 progress layout, then test rollback. */
  OK(exr_library_backup(l,migration,&error));
  sql(migration,"DROP TRIGGER books_progress_changed;ALTER TABLE book_progress RENAME TO saved_progress;CREATE TABLE book_progress(book_id INTEGER PRIMARY KEY REFERENCES books(id) ON DELETE CASCADE,position INTEGER NOT NULL CHECK(position>=0),state INTEGER NOT NULL CHECK(state BETWEEN 0 AND 2),prefix TEXT,suffix TEXT,chapter TEXT);INSERT INTO book_progress SELECT * FROM saved_progress;DROP TABLE saved_progress;CREATE TRIGGER books_progress_changed AFTER UPDATE OF position ON books WHEN OLD.position<>NEW.position BEGIN DELETE FROM book_progress WHERE book_id=NEW.id;END;ALTER TABLE notes DROP COLUMN location_state;PRAGMA user_version=5;CREATE TABLE book_progress_v5(conflict INTEGER);");
  CHECK(exr_library_open(migration,&copy,&error)==EXR_DATABASE && !copy); CHECK(scalar(migration,"PRAGMA user_version")==5 && scalar(migration,"SELECT count(*) FROM sqlite_master WHERE name='books_progress_changed'")==1);
  sql(migration,"DROP TABLE book_progress_v5;"); OK(exr_library_open(migration,&copy,&error)); CHECK(scalar(migration,"PRAGMA user_version")==6); OK(exr_library_progress_get(copy,book,&p,&state,&error)); CHECK(state==EXR_ANCHOR_FOUND && p.start==position+10); exr_anchor_free(&p); exr_library_close(copy);
  /* Equal contexts must not become a nearest-offset guess; unresolved data can recover later. */
  memset(ambiguous,'L',40); strcpy(ambiguous+40,"SAME"); memset(ambiguous+44,'R',40); ambiguous[84]=0; snprintf(twice,sizeof(twice),"%s|%s",ambiguous,ambiguous);
  OK(exr_library_import(l,EXR_TXT,ambiguous,84,"Ambiguous",&amb,&error)); OK(exr_library_document(l,amb,&doc,&error)); input=(exr_note){0}; input.book_id=amb; input.start=40; input.end=44; input.text="ambiguous comment"; OK(exr_library_note(l,&input,&amb_note,&error)); OK(exr_anchor_create(doc,42,42,&p,&error)); OK(exr_library_progress(l,amb,&p,&error)); exr_anchor_free(&p); exr_document_free(doc); doc=NULL;
  revision(path,amb,twice); OK(exr_library_reanchor(l,amb,7,NULL,&report,&error)); CHECK(report.progress.state==EXR_ANCHOR_AMBIGUOUS && report.position==7 && match_id(&report,amb_note).state==EXR_ANCHOR_AMBIGUOUS); exr_library_relocation_free(&report);
  OK(exr_library_progress_get(l,amb,&p,&state,&error)); CHECK(state==EXR_ANCHOR_AMBIGUOUS && p.start==42); exr_anchor_free(&p); revision(path,amb,ambiguous);
  OK(exr_library_reanchor(l,amb,0,NULL,&report,&error)); CHECK(report.progress.state==EXR_ANCHOR_FOUND && report.position==42 && match_id(&report,amb_note).state==EXR_ANCHOR_FOUND); exr_library_relocation_free(&report);
  /* Retain legacy numeric history even if the chosen fallback is inside a shorter revision. */
  OK(exr_library_import(l,EXR_TXT,"old numeric progress",20,"Legacy progress",&raw,&error)); OK(exr_library_books(l,"Legacy progress",&books,&n,&error)); CHECK(n==1); books[0].position=10; OK(exr_library_update(l,&books[0],&error)); exr_books_free(books,n); revision(path,raw,"abc");
  OK(exr_library_reanchor(l,raw,1,NULL,&report,&error)); CHECK(report.progress.state==EXR_ANCHOR_LEGACY && report.position==1); exr_library_relocation_free(&report); OK(exr_library_progress_get(l,raw,&p,&state,&error)); CHECK(state==EXR_ANCHOR_LEGACY && !p.exact && p.start==10); exr_anchor_free(&p);
  revision(path,raw,"a\xc3\xa9"); CHECK(exr_library_reanchor(l,raw,2,NULL,&report,&error)==EXR_ARGUMENT && !report.notes); OK(exr_library_reanchor(l,raw,1,NULL,&report,&error)); exr_library_relocation_free(&report);
  snprintf(query,sizeof(query),"UPDATE notes SET text=CAST(x'ff' AS TEXT) WHERE id=%lld",(long long)legacy); sql(path,query); notes=NULL; n=0; CHECK(exr_library_notes(l,book,&notes,&n,&error)==EXR_DATABASE && !notes && !n); OK(exr_library_note_text(l,legacy,"repaired",&error));
  CHECK(exr_library_reanchor(l,book,10000,NULL,&report,&error)==EXR_ARGUMENT && !report.notes); CHECK(exr_library_reanchor(l,999999,0,NULL,&report,&error)==EXR_ARGUMENT && !report.notes);
  OK(exr_library_document(l,book,&doc,&error)); stopped=1; CHECK(exr_anchor_resolve_ex(doc,&progress,&control,&match,&error)==EXR_CANCELLED && match.start==SIZE_MAX); exr_document_free(doc);
  exr_anchor_free(&progress); exr_library_close(l); remove(path); remove(backup); remove(migration); printf("%u library relocation checks passed\n",checks); return 0;
}
