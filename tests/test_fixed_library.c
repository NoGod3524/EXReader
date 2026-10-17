/* SPDX-License-Identifier: GPL-3.0-only */
#include "exreader.h"
#include <sqlite3.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error; static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static void sql(const char *path,const char *query) {
  sqlite3 *db=NULL; CHECK(sqlite3_open(path,&db)==SQLITE_OK); CHECK(sqlite3_exec(db,query,NULL,NULL,NULL)==SQLITE_OK); CHECK(sqlite3_close(db)==SQLITE_OK);
}
static void schema_version(const char *path,int version) {
  sqlite3 *db=NULL; sqlite3_stmt *statement=NULL; CHECK(sqlite3_open(path,&db)==SQLITE_OK);
  CHECK(sqlite3_prepare_v2(db,"PRAGMA user_version",-1,&statement,NULL)==SQLITE_OK && sqlite3_step(statement)==SQLITE_ROW && sqlite3_column_int(statement,0)==version);
  sqlite3_finalize(statement); CHECK(sqlite3_close(db)==SQLITE_OK);
}
static unsigned char *load(const char *dir,size_t *size) {
  char path[4096]; FILE *f; long n; unsigned char *bytes;
  snprintf(path,sizeof(path),"%s/pdf-public-text.pdf",dir); f=fopen(path,"rb"); CHECK(f && !fseek(f,0,SEEK_END)); n=ftell(f); CHECK(n>0); rewind(f);
  *size=(size_t)n; bytes=malloc(*size); CHECK(bytes && fread(bytes,1,*size,f)==*size); fclose(f); return bytes;
}
static int cancel(void *context) { (void)context; return 1; }
static void check_notes(exr_library *library,int64_t book_id) {
  exr_fixed_note *notes=NULL; size_t count; exr_fixed_document *d=NULL; exr_fixed_text *text=NULL; exr_anchor_match match;
  OK(exr_library_fixed_notes(library,book_id,&notes,&count,&error)); CHECK(count==3 && notes[0].start==1 && notes[0].end==3 && notes[0].anchor.exact_size==2);
  CHECK(!strcmp(notes[0].text,"edited") && notes[1].anchor.exact_size==1 && notes[1].anchor.exact[0]==0 && notes[2].page==3 && !notes[2].anchor.exact_size);
  OK(exr_library_fixed(library,book_id,NULL,&d,&error)); OK(exr_fixed_load_text(d,0,NULL,&text,&error));
  OK(exr_fixed_anchor_resolve("page-1",text,&notes[1].anchor,NULL,&match,&error)); CHECK(match.state==EXR_ANCHOR_FOUND && match.start==6 && match.end==7);
  exr_fixed_free(d); exr_fixed_text_free(text); exr_fixed_notes_free(notes,count);
}
int main(int argc,char **argv) {
  char path[4096],backup[4096],migration[4096]; unsigned char *bytes; size_t size,count; int64_t book,other,plain,id; exr_library *l=NULL,*restored=NULL;
  exr_fixed_note input={0},*notes=NULL; exr_fixed_document *d=NULL; exr_document *reflow=NULL; exr_book *books=NULL; exr_control control={0};
  CHECK(argc==3); snprintf(path,sizeof(path),"%s/fixed-library.sqlite",argv[2]); snprintf(backup,sizeof(backup),"%s/fixed-backup.sqlite",argv[2]); snprintf(migration,sizeof(migration),"%s/fixed-migrate.sqlite",argv[2]); remove(path); remove(backup); remove(migration);
  OK(exr_library_open(path,&l,&error)); bytes=load(argv[1],&size);
  CHECK(exr_library_import(l,EXR_PDF,"bad",3,"bad",&book,&error)==EXR_FORMAT && !book);
  OK(exr_library_import(l,EXR_PDF,bytes,size,"PDF title",&book,&error)); OK(exr_library_import(l,EXR_PDF,bytes,size,"Other PDF",&other,&error)); free(bytes);
  OK(exr_library_import(l,EXR_TXT,"text",4,"Plain",&plain,&error));
  CHECK(exr_library_fixed(l,plain,NULL,&d,&error)==EXR_FORMAT && !d);
  CHECK(exr_library_document(l,book,&reflow,&error)==EXR_FORMAT && !reflow);
  OK(exr_library_books(l,"PDF title",&books,&count,&error)); CHECK(count==1 && books[0].format==EXR_PDF);
  books[0].title[0]='X'; books[0].position=3; books[0].favorite=1; OK(exr_library_update(l,&books[0],&error)); books[0].position=5; CHECK(exr_library_update(l,&books[0],&error)==EXR_ARGUMENT); exr_books_free(books,count);
  OK(exr_library_cover(l,book,"cover",5,&error));
  input.book_id=book; input.page=0; input.start=1; input.end=3; input.text="comment";
  control.cancelled=cancel; CHECK(exr_library_fixed_note(l,&input,&control,&id,&error)==EXR_CANCELLED && !id);
  OK(exr_library_fixed_note(l,&input,NULL,&input.id,&error)); CHECK(input.id>0);
  input.text="edited"; OK(exr_library_fixed_note(l,&input,NULL,&input.id,&error));
  { exr_fixed_note wrong=input; wrong.book_id=other; CHECK(exr_library_fixed_note(l,&wrong,NULL,&id,&error)==EXR_ARGUMENT && !id); }
  input.id=0; input.start=6; input.end=7; input.text="NUL quote"; OK(exr_library_fixed_note(l,&input,NULL,&input.id,&error));
  { exr_note wrong={0}; wrong.book_id=book; wrong.text="wrong API"; CHECK(exr_library_note(l,&wrong,&id,&error)==EXR_FORMAT && !id); }
  input.id=0; input.page=3; input.start=input.end=0; input.text="bookmark"; OK(exr_library_fixed_note(l,&input,NULL,&input.id,&error));
  input.id=0; input.page=4; CHECK(exr_library_fixed_note(l,&input,NULL,&id,&error)==EXR_ARGUMENT && !id);
  input.page=1; CHECK(exr_library_fixed_note(l,&input,NULL,&id,&error)==EXR_FORMAT && !id);
  input.page=0;
  input.start=4; input.end=5; CHECK(exr_library_fixed_note(l,&input,NULL,&id,&error)==EXR_ARGUMENT && !id); /* Inside CJK scalar. */
  input.start=input.end=0; input.text="\xc0"; CHECK(exr_library_fixed_note(l,&input,NULL,&id,&error)==EXR_ENCODING && !id);
  exr_library_close(l); l=NULL; OK(exr_library_open(path,&l,&error)); check_notes(l,book);
  OK(exr_library_books(l,"XDF title",&books,&count,&error)); CHECK(count==1 && books[0].position==3 && books[0].favorite); exr_books_free(books,count);
  { void *cover=NULL; size_t cover_size; OK(exr_library_blob(l,book,1,&cover,&cover_size,&error)); CHECK(cover_size==5 && !memcmp(cover,"cover",5)); exr_free(cover); }
  OK(exr_library_backup(l,backup,&error)); OK(exr_library_open(backup,&restored,&error)); check_notes(restored,book); exr_library_close(restored);
  /* Corrupt stored selectors are rejected without exposing a partial array. */
  sql(path,"UPDATE fixed_notes SET exact=CAST(exact AS TEXT) WHERE start=6"); CHECK(exr_library_fixed_notes(l,book,&notes,&count,&error)==EXR_DATABASE && !notes && !count);
  sql(path,"UPDATE fixed_notes SET exact=x'ff' WHERE start=6"); CHECK(exr_library_fixed_notes(l,book,&notes,&count,&error)==EXR_DATABASE && !notes && !count);
  sql(path,"UPDATE fixed_notes SET exact=x'00' WHERE start=6"); check_notes(l,book);
  OK(exr_library_fixed_notes(l,book,&notes,&count,&error)); id=notes[0].id; exr_fixed_notes_free(notes,count);
  OK(exr_library_remove_fixed_note(l,id,&error)); OK(exr_library_fixed_notes(l,book,&notes,&count,&error)); CHECK(count==2); exr_fixed_notes_free(notes,count);
  OK(exr_library_delete(l,book,&error)); OK(exr_library_fixed_notes(l,book,&notes,&count,&error)); CHECK(!count && !notes); exr_library_close(l);
  /* Upgrade v2, preserve reflow rows, and roll back a conflicting migration. */
  OK(exr_library_open(migration,&l,&error)); OK(exr_library_import(l,EXR_TXT,"old",3,"Old",&id,&error)); exr_library_close(l);
  sql(migration,"DROP TABLE fixed_notes; DROP TABLE audio_resume; DROP TABLE audio_marks; PRAGMA user_version=2"); OK(exr_library_open(migration,&l,&error)); schema_version(migration,4); OK(exr_library_books(l,"Old",&books,&count,&error)); CHECK(count==1); exr_books_free(books,count); exr_library_close(l);
  sql(migration,"DROP TABLE fixed_notes; DROP TABLE audio_resume; DROP TABLE audio_marks; CREATE TABLE fixed_notes(conflict INTEGER); PRAGMA user_version=2"); CHECK(exr_library_open(migration,&l,&error)==EXR_DATABASE && !l); schema_version(migration,2);
  sql(migration,"DROP TABLE fixed_notes"); OK(exr_library_open(migration,&l,&error)); exr_library_close(l);
  remove(path); remove(backup); remove(migration); printf("%u fixed library checks passed\n",checks); return 0;
}
