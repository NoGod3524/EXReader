/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include <sqlite3.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
static exr_error error; static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static void sql(const char *path,const char *query) {
  sqlite3 *db=NULL; CHECK(sqlite3_open(path,&db)==SQLITE_OK); CHECK(sqlite3_exec(db,query,NULL,NULL,NULL)==SQLITE_OK); CHECK(sqlite3_close(db)==SQLITE_OK);
}
static void scalar(const char *path,const char *query,int value) {
  sqlite3 *db=NULL; sqlite3_stmt *s=NULL; CHECK(sqlite3_open(path,&db)==SQLITE_OK); CHECK(sqlite3_prepare_v2(db,query,-1,&s,NULL)==SQLITE_OK && sqlite3_step(s)==SQLITE_ROW && sqlite3_column_int(s,0)==value); sqlite3_finalize(s); CHECK(sqlite3_close(db)==SQLITE_OK);
}
static void checkpoint(exr_library *l,const char *key,uint64_t offset) {
  exr_audio_checkpoint p={0}; int found=0; OK(exr_library_audio_resume_get(l,key,&p,&found,&error)); CHECK(found && !strcmp(p.track_id,"two") && p.offset_ms==offset && p.rate==1.5); exr_audio_checkpoint_free(&p);
}
int main(int argc,char **argv) {
  char path[4096],backup[4096]; exr_library *l=NULL,*other=NULL; exr_audio_checkpoint input={"two",UINT64_MAX,1.5},p={0}; exr_audio_bookmark b={0},*marks=NULL; int found; size_t count; int64_t id;
  CHECK(argc==2); snprintf(path,sizeof(path),"%s/audio-library.sqlite",argv[1]); snprintf(backup,sizeof(backup),"%s/audio-backup.sqlite",argv[1]); remove(path); remove(backup);
  OK(exr_library_open(path,&l,&error)); scalar(path,"PRAGMA user_version",7);
  OK(exr_library_audio_resume_get(l,"host:book",&p,&found,&error)); CHECK(!found && !p.track_id);
  OK(exr_library_audio_resume(l,"host:book",&input,&error)); checkpoint(l,"host:book",UINT64_MAX);
  input.offset_ms=500; OK(exr_library_audio_resume(l,"host:book",&input,&error)); checkpoint(l,"host:book",500);
  b.position=input; b.label="First"; OK(exr_library_audio_bookmark(l,"host:book",&b,&b.id,&error)); CHECK(b.id>0);
  b.label="Edited"; OK(exr_library_audio_bookmark(l,"host:book",&b,&b.id,&error));
  CHECK(exr_library_audio_bookmark(l,"other",&b,&id,&error)==EXR_ARGUMENT && !id);
  b.id=0; b.label="Second"; b.position.offset_ms=UINT64_MAX; OK(exr_library_audio_bookmark(l,"host:book",&b,&b.id,&error));
  b.id=0; b.label="Other key"; OK(exr_library_audio_bookmark(l,"other",&b,&b.id,&error));
  OK(exr_library_audio_bookmarks(l,"host:book",&marks,&count,&error)); CHECK(count==2 && !strcmp(marks[0].label,"Edited") && marks[1].position.offset_ms==UINT64_MAX); id=marks[0].id; exr_audio_bookmarks_free(marks,count);
  input.rate=NAN; CHECK(exr_library_audio_resume(l,"host:book",&input,&error)==EXR_ARGUMENT); input.rate=1.5;
  CHECK(exr_library_audio_resume(l,"",&input,&error)==EXR_ARGUMENT); CHECK(exr_library_audio_resume(l,"\xff",&input,&error)==EXR_ENCODING);
  input.track_id=""; CHECK(exr_library_audio_resume(l,"host:book",&input,&error)==EXR_ARGUMENT); input.track_id="two";
  exr_library_close(l); OK(exr_library_open(path,&l,&error)); checkpoint(l,"host:book",500);
  OK(exr_library_backup(l,backup,&error)); OK(exr_library_open(backup,&other,&error)); checkpoint(other,"host:book",500);
  OK(exr_library_audio_bookmarks(other,"host:book",&marks,&count,&error)); CHECK(count==2); exr_audio_bookmarks_free(marks,count); exr_library_close(other);
  sql(path,"PRAGMA ignore_check_constraints=ON; UPDATE audio_resume SET offset=x'01' WHERE audio_id='host:book'"); CHECK(exr_library_audio_resume_get(l,"host:book",&p,&found,&error)==EXR_DATABASE && !found && !p.track_id); OK(exr_library_audio_resume(l,"host:book",&input,&error));
  sql(path,"UPDATE audio_resume SET track_id=CAST(x'ff' AS TEXT) WHERE audio_id='host:book'"); CHECK(exr_library_audio_resume_get(l,"host:book",&p,&found,&error)==EXR_DATABASE && !found && !p.track_id); OK(exr_library_audio_resume(l,"host:book",&input,&error));
  sql(path,"UPDATE audio_marks SET label=CAST(x'ff' AS TEXT) WHERE label='Second'"); CHECK(exr_library_audio_bookmarks(l,"host:book",&marks,&count,&error)==EXR_DATABASE && !marks && !count); sql(path,"UPDATE audio_marks SET label='Second' WHERE audio_id='host:book' AND label<> 'Edited'");
  sql(path,"CREATE TRIGGER prevent_audio_clear BEFORE DELETE ON audio_marks BEGIN SELECT RAISE(ABORT,'blocked'); END");
  CHECK(exr_library_clear_audio(l,"host:book",&error)==EXR_DATABASE); checkpoint(l,"host:book",500); OK(exr_library_audio_bookmarks(l,"host:book",&marks,&count,&error)); CHECK(count==2); exr_audio_bookmarks_free(marks,count);
  sql(path,"DROP TRIGGER prevent_audio_clear"); OK(exr_library_remove_audio_bookmark(l,id,&error)); OK(exr_library_audio_bookmarks(l,"host:book",&marks,&count,&error)); CHECK(count==1); exr_audio_bookmarks_free(marks,count);
  OK(exr_library_clear_audio(l,"host:book",&error)); OK(exr_library_audio_resume_get(l,"host:book",&p,&found,&error)); CHECK(!found && !p.track_id); OK(exr_library_audio_bookmarks(l,"host:book",&marks,&count,&error)); CHECK(!count && !marks);
  OK(exr_library_audio_bookmarks(l,"other",&marks,&count,&error)); CHECK(count==1); exr_audio_bookmarks_free(marks,count); exr_library_close(l);
  /* v3 upgrade and rollback after the first new table was created. */
  sql(path,"DROP TABLE epub_notes;DROP TABLE epub_progress;DROP TABLE epub_bounded_books;DROP TRIGGER books_progress_changed;DROP TABLE book_progress;ALTER TABLE notes DROP COLUMN location_state;DROP TABLE audio_resume; PRAGMA user_version=3"); CHECK(exr_library_open(path,&l,&error)==EXR_DATABASE && !l); scalar(path,"PRAGMA user_version",3); scalar(path,"SELECT count(*) FROM sqlite_master WHERE name='audio_resume'",0);
  sql(path,"DROP TABLE audio_marks"); OK(exr_library_open(path,&l,&error)); scalar(path,"PRAGMA user_version",7); OK(exr_library_audio_resume(l,"after-migration",&input,&error)); exr_library_close(l);
  remove(path); remove(backup); exr_audio_checkpoint_free(NULL); exr_audio_bookmarks_free(NULL,0); printf("%u audio persistence checks passed\n",checks); return 0;
}
