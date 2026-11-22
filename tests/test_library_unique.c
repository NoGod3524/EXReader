/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include <sqlite3.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
#define WORKER DWORD WINAPI
#else
#include <pthread.h>
#define WORKER void *
#endif
static exr_error error; static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static void sql(const char *path,const char *text) { sqlite3 *db=NULL; CHECK(sqlite3_open(path,&db)==SQLITE_OK); CHECK(sqlite3_exec(db,text,NULL,NULL,NULL)==SQLITE_OK); CHECK(sqlite3_close(db)==SQLITE_OK); }
static void count_books(exr_library *l,size_t expected) { exr_book *books=NULL; size_t n=0; OK(exr_library_books(l,"",&books,&n,&error)); CHECK(n==expected); exr_books_free(books,n); }
typedef struct { exr_library *library; const char *text; int64_t id; int created; exr_status status; exr_error error; } job;
static WORKER import_worker(void *context) { job *j=context; j->status=exr_library_import_unique(j->library,EXR_TXT,j->text,strlen(j->text),"Concurrent",&j->id,&j->created,&j->error); return 0; }
static void concurrent(exr_library *a,exr_library *b,const char *text) {
  job jobs[2]={{0},{0}}; size_t i;
#ifdef _WIN32
  HANDLE threads[2];
#else
  pthread_t threads[2];
#endif
  jobs[0].library=a; jobs[1].library=b; jobs[0].text=jobs[1].text=text;
  for(i=0;i<2;i++) {
#ifdef _WIN32
    threads[i]=CreateThread(NULL,0,import_worker,&jobs[i],0,NULL); CHECK(threads[i]);
#else
    CHECK(!pthread_create(&threads[i],NULL,import_worker,&jobs[i]));
#endif
  }
  for(i=0;i<2;i++) {
#ifdef _WIN32
    CHECK(WaitForSingleObject(threads[i],INFINITE)==WAIT_OBJECT_0); CloseHandle(threads[i]);
#else
    CHECK(!pthread_join(threads[i],NULL));
#endif
    if(jobs[i].status!=EXR_OK) fprintf(stderr,"worker %zu: %s\n",i,jobs[i].error.message);
    CHECK(jobs[i].status==EXR_OK && jobs[i].id>0);
  }
  CHECK(jobs[0].id==jobs[1].id && jobs[0].created+jobs[1].created==1);
}
typedef struct { const char *path; exr_library *library; exr_status status; exr_error error; } open_job;
static WORKER open_worker(void *context) { open_job *j=context; j->status=exr_library_open(j->path,&j->library,&j->error); return 0; }
static void concurrent_open(const char *dir) {
  char path[4096]; unsigned round; size_t i;
  snprintf(path,sizeof(path),"%s/concurrent-open.sqlite",dir);
  for(round=0;round<8;round++) {
    open_job jobs[4]={{0},{0},{0},{0}};
#ifdef _WIN32
    HANDLE threads[4];
#else
    pthread_t threads[4];
#endif
    remove(path);
    for(i=0;i<4;i++) {
      jobs[i].path=path;
#ifdef _WIN32
      threads[i]=CreateThread(NULL,0,open_worker,&jobs[i],0,NULL); CHECK(threads[i]);
#else
      CHECK(!pthread_create(&threads[i],NULL,open_worker,&jobs[i]));
#endif
    }
    for(i=0;i<4;i++) {
#ifdef _WIN32
      CHECK(WaitForSingleObject(threads[i],INFINITE)==WAIT_OBJECT_0); CloseHandle(threads[i]);
#else
      CHECK(!pthread_join(threads[i],NULL));
#endif
      if(jobs[i].status!=EXR_OK) fprintf(stderr,"open round %u worker %zu: %s\n",round,i,jobs[i].error.message);
      CHECK(jobs[i].status==EXR_OK && jobs[i].library);
      exr_library_close(jobs[i].library);
    }
  }
  /* Concurrent v6->v7 migration on the same file. */
  sql(path,"DROP TABLE epub_notes;DROP TABLE epub_progress;DROP TABLE epub_bounded_books;PRAGMA user_version=6;");
  { open_job jobs[4]={{0},{0},{0},{0}};
#ifdef _WIN32
    HANDLE threads[4];
#else
    pthread_t threads[4];
#endif
    for(i=0;i<4;i++) {
      jobs[i].path=path;
#ifdef _WIN32
      threads[i]=CreateThread(NULL,0,open_worker,&jobs[i],0,NULL); CHECK(threads[i]);
#else
      CHECK(!pthread_create(&threads[i],NULL,open_worker,&jobs[i]));
#endif
    }
    for(i=0;i<4;i++) {
#ifdef _WIN32
      CHECK(WaitForSingleObject(threads[i],INFINITE)==WAIT_OBJECT_0); CloseHandle(threads[i]);
#else
      CHECK(!pthread_join(threads[i],NULL));
#endif
      if(jobs[i].status!=EXR_OK) fprintf(stderr,"migrate worker %zu: %s\n",i,jobs[i].error.message);
      CHECK(jobs[i].status==EXR_OK && jobs[i].library);
      exr_library_close(jobs[i].library);
    }
  }
  remove(path);
}
typedef struct {
  exr_library *library; int mode; int64_t book_id;
  int64_t ids[64]; exr_status failed; exr_error error;
} mutator_job;
static WORKER mutator_worker(void *context) {
  mutator_job *j=context; unsigned i;
  for(i=0;i<64;i++) {
    exr_status st;
    if(j->mode==0) {
      st=exr_library_clear_audio(j->library,i&1 ? "k1" : "k2",&j->error);
      if(st!=EXR_OK) { j->failed=st; return 0; }
    } else if(j->mode==1) {
      char body[32]; snprintf(body,sizeof(body),"row-%p-%u",(void *)j,i);
      st=exr_library_import(j->library,EXR_TXT,body,strlen(body),body,&j->ids[i],&j->error);
      if(st!=EXR_OK || j->ids[i]<=0) { j->failed=st==EXR_OK ? EXR_DATABASE : st; return 0; }
    } else if(j->mode==2) {
      st=exr_library_cover(j->library,j->book_id,"cvr",3,&j->error);
      if(st!=EXR_OK) { j->failed=st; return 0; }
    } else {
      st=exr_library_cover(j->library,99999999,"cvr",3,&j->error);
      if(st!=EXR_ARGUMENT) { j->failed=st==EXR_OK ? EXR_DATABASE : st; return 0; }
    }
  }
  return 0;
}
static void concurrent_mutators(const char *dir) {
  char path[4096]; exr_library *l=NULL; int64_t book_id=0;
  mutator_job jobs[6]={{0}}; size_t i,a,b;
#ifdef _WIN32
  HANDLE threads[6];
#else
  pthread_t threads[6];
#endif
  snprintf(path,sizeof(path),"%s/concurrent-mutators.sqlite",dir); remove(path);
  OK(exr_library_open(path,&l,&error));
  OK(exr_library_import(l,EXR_TXT,"base",4,"Base",&book_id,&error));
  jobs[0].library=l; jobs[0].mode=0;
  jobs[1].library=l; jobs[1].mode=0;
  jobs[2].library=l; jobs[2].mode=1;
  jobs[3].library=l; jobs[3].mode=1;
  jobs[4].library=l; jobs[4].mode=2; jobs[4].book_id=book_id;
  jobs[5].library=l; jobs[5].mode=3;
  for(i=0;i<6;i++) {
#ifdef _WIN32
    threads[i]=CreateThread(NULL,0,mutator_worker,&jobs[i],0,NULL); CHECK(threads[i]);
#else
    CHECK(!pthread_create(&threads[i],NULL,mutator_worker,&jobs[i]));
#endif
  }
  for(i=0;i<6;i++) {
#ifdef _WIN32
    CHECK(WaitForSingleObject(threads[i],INFINITE)==WAIT_OBJECT_0); CloseHandle(threads[i]);
#else
    CHECK(!pthread_join(threads[i],NULL));
#endif
    if(jobs[i].failed!=EXR_OK) fprintf(stderr,"mutator %zu (mode %d): %d %s\n",i,jobs[i].mode,jobs[i].failed,jobs[i].error.message);
    CHECK(jobs[i].failed==EXR_OK);
  }
  /* All 128 concurrent exr_library_import() calls on the shared handle must return distinct row IDs. */
  for(a=0;a<64;a++) for(b=0;b<64;b++) CHECK(jobs[2].ids[a]!=jobs[3].ids[b]);
  exr_library_close(l); remove(path);
}
int main(int argc,char **argv) {
  exr_library *l=NULL,*other=NULL; char path[4096],backup[4096]; int64_t a,b,id,note_id; int created; exr_note note={0},*notes=NULL; size_t n; exr_book *books=NULL; void *cover=NULL;
  const char source[]="Exact text",changed[]="Exact texT"; CHECK(argc==3);
  snprintf(path,sizeof(path),"%s/unique-library.sqlite",argv[2]); snprintf(backup,sizeof(backup),"%s/unique-backup.sqlite",argv[2]); remove(path); remove(backup);
  OK(exr_library_open(path,&l,&error));
  OK(exr_library_import_unique(l,EXR_TXT,source,sizeof(source)-1,"First",&a,&created,&error)); CHECK(a>0 && created==1);
  OK(exr_library_import_unique(l,EXR_TXT,source,sizeof(source)-1,"Ignored title",&id,&created,&error)); CHECK(id==a && !created); count_books(l,1);
  OK(exr_library_books(l,"First",&books,&n,&error)); CHECK(n==1); books[0].position=3; books[0].favorite=1; OK(exr_library_update(l,&books[0],&error)); exr_books_free(books,n);
  OK(exr_library_cover(l,a,"cover",5,&error)); note.book_id=a; note.start=0; note.end=5; note.text="Note"; OK(exr_library_note(l,&note,&note_id,&error));
  OK(exr_library_import(l,EXR_TXT,source,sizeof(source)-1,"Duplicate allowed",&b,&error)); CHECK(b!=a);
  OK(exr_library_import_unique(l,EXR_TXT,source,sizeof(source)-1,NULL,&id,&created,&error)); CHECK(id==a && !created);
  OK(exr_library_books(l,"First",&books,&n,&error)); CHECK(n==1 && books[0].position==3 && books[0].favorite==1); exr_books_free(books,n);
  OK(exr_library_blob(l,a,1,&cover,&n,&error)); CHECK(n==5 && !memcmp(cover,"cover",5)); exr_free(cover);
  OK(exr_library_notes(l,a,&notes,&n,&error)); CHECK(n==1 && notes[0].id==note_id && !strcmp(notes[0].text,"Note")); exr_notes_free(notes,n);
  OK(exr_library_import_unique(l,EXR_TXT,changed,sizeof(changed)-1,NULL,&id,&created,&error)); CHECK(id!=a && created);
  OK(exr_library_import_unique(l,EXR_HTML,source,sizeof(source)-1,NULL,&id,&created,&error)); CHECK(id!=a && created); count_books(l,4);
  CHECK(exr_library_import_unique(l,EXR_PDF,"bad",3,NULL,&id,&created,&error)==EXR_FORMAT && !id && !created); count_books(l,4);
  sql(path,"CREATE TRIGGER fail_import BEFORE INSERT ON books BEGIN SELECT RAISE(ABORT,'forced import failure');END;");
  CHECK(exr_library_import_unique(l,EXR_TXT,"new",3,NULL,&id,&created,&error)==EXR_DATABASE && !id && !created); count_books(l,4);
  sql(path,"DROP TRIGGER fail_import;"); OK(exr_library_import_unique(l,EXR_TXT,"new",3,NULL,&id,&created,&error)); CHECK(created); count_books(l,5);
  sql(path,"CREATE TABLE fail_commit(parent INTEGER REFERENCES books(id) DEFERRABLE INITIALLY DEFERRED);CREATE TRIGGER fail_commit_import AFTER INSERT ON books BEGIN INSERT INTO fail_commit VALUES(999999);END;");
  CHECK(exr_library_import_unique(l,EXR_TXT,"commit",6,NULL,&id,&created,&error)==EXR_DATABASE && !id && !created); count_books(l,5);
  sql(path,"DROP TRIGGER fail_commit_import;DROP TABLE fail_commit;");
  OK(exr_library_open(path,&other,&error)); concurrent(l,other,"Concurrent handles"); concurrent(l,l,"Concurrent shared handle"); count_books(l,7); exr_library_close(other); other=NULL;
  { FILE *f; char file[4096]; unsigned char *pdf; long size;
    snprintf(file,sizeof(file),"%s/pdf-public-text.pdf",argv[1]); f=fopen(file,"rb"); CHECK(f && !fseek(f,0,SEEK_END)); size=ftell(f); CHECK(size>0); rewind(f); pdf=malloc((size_t)size); CHECK(pdf && fread(pdf,1,(size_t)size,f)==(size_t)size); fclose(f);
    OK(exr_library_import_unique(l,EXR_PDF,pdf,(size_t)size,NULL,&a,&created,&error)); CHECK(created);
    OK(exr_library_import_unique(l,EXR_PDF,pdf,(size_t)size,NULL,&id,&created,&error)); CHECK(id==a && !created); free(pdf);
  }
  OK(exr_library_backup(l,backup,&error)); OK(exr_library_open(backup,&other,&error)); OK(exr_library_import_unique(other,EXR_TXT,source,sizeof(source)-1,"Backup",&id,&created,&error)); CHECK(id==1 && !created); count_books(other,8); exr_library_close(other);
  id=5; created=1; CHECK(exr_library_import_unique(NULL,EXR_TXT,source,1,NULL,&id,&created,&error)==EXR_ARGUMENT && !id && !created);
  CHECK(exr_library_import_unique(l,EXR_CUSTOM,source,1,NULL,&id,&created,&error)==EXR_ARGUMENT && !id && !created);
  CHECK(exr_library_import_unique(l,EXR_TXT,NULL,1,NULL,&id,&created,&error)==EXR_ARGUMENT && !id && !created);
  CHECK(exr_library_import_unique(l,EXR_TXT,source,(size_t)129*1024*1024,NULL,&id,&created,&error)==EXR_LIMIT && !id && !created);
  CHECK(exr_library_import_unique(l,EXR_TXT,source,1,NULL,&id,NULL,&error)==EXR_ARGUMENT && !id);
  OK(exr_library_delete(l,1,&error)); OK(exr_library_import_unique(l,EXR_TXT,source,sizeof(source)-1,NULL,&id,&created,&error)); CHECK(id==b && !created); count_books(l,7);
  sql(path,"INSERT INTO books(id,format,title,text_size,source) VALUES(0,1,'Invalid ID',7,x'636f7272757074');");
  CHECK(exr_library_import_unique(l,EXR_TXT,"corrupt",7,NULL,&id,&created,&error)==EXR_DATABASE && !id && !created);
  sql(path,"DELETE FROM books WHERE id=0;");
  exr_library_close(l); remove(path); remove(backup);
  concurrent_open(argv[2]);
  concurrent_mutators(argv[2]);
  printf("%u exact duplicate import checks passed\n",checks); return 0;
}
