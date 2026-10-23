/* SPDX-License-Identifier: MIT */
#define _CRT_SECURE_NO_WARNINGS
#define _POSIX_C_SOURCE 200809L
#include "catalog.h"
#include <sqlite3.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#else
#include <pthread.h>
#endif

#define CHECK(x) do { if(!(x)) { fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#x);exit(1); } } while(0)
static const char *checks[24];static size_t check_count;
#define PASSED(name) do { checks[check_count++]=name;puts("PASS " name); } while(0)
static char continuation_sql[4096];
static int trace_statement(unsigned event,void *context,void *statement,void *expanded) {
  (void)context;(void)expanded;
  if(event==SQLITE_TRACE_STMT) {
    const char *sql=sqlite3_sql(statement);
    if(sql && strstr(sql,"SELECT b.book_key") && strstr(sql,"AND (b.sort_title,b.book_key)>"))
      snprintf(continuation_sql,sizeof(continuation_sql),"%s",sql);
  }
  return 0;
}
static int trace_connection(sqlite3 *db,char **message,const sqlite3_api_routines *api) {
  (void)message;(void)api;
  return sqlite3_trace_v2(db,SQLITE_TRACE_STMT,trace_statement,NULL);
}
static void sql(sqlite3 *db,const char *text) {
  char *message=NULL;int code=sqlite3_exec(db,text,NULL,NULL,&message);
  if(code!=SQLITE_OK) { fprintf(stderr,"test SQL: %s\n",message?message:"unknown");sqlite3_free(message);exit(1); }
}
static int64_t scalar(sqlite3 *db,const char *text) {
  sqlite3_stmt *s=NULL;CHECK(sqlite3_prepare_v2(db,text,-1,&s,NULL)==SQLITE_OK);
  CHECK(sqlite3_step(s)==SQLITE_ROW);int64_t result=sqlite3_column_int64(s,0);
  CHECK(sqlite3_finalize(s)==SQLITE_OK);return result;
}
static sqlite3 *external(const char *path) {
  sqlite3 *db=NULL;CHECK(sqlite3_open(path,&db)==SQLITE_OK);
  CHECK(sqlite3_busy_timeout(db,5000)==SQLITE_OK);sql(db,"PRAGMA foreign_keys=ON;");return db;
}
static unsigned char *file_bytes(const char *path,size_t *size) {
  FILE *file=fopen(path,"rb");CHECK(file);CHECK(fseek(file,0,SEEK_END)==0);
  long length=ftell(file);CHECK(length>=0);CHECK(fseek(file,0,SEEK_SET)==0);
  unsigned char *bytes=malloc((size_t)length+1);CHECK(bytes);
  CHECK(fread(bytes,1,(size_t)length,file)==(size_t)length);CHECK(fclose(file)==0);
  *size=(size_t)length;return bytes;
}
static void path(char *out,size_t capacity,const char *folder,const char *name) {
  CHECK(snprintf(out,capacity,"%s/%s",folder,name)>0);
  FILE *old=fopen(out,"rb");CHECK(!old); /* Each CI build must use fresh evidence. */
}
static const char hash_one[]="0000000000000000000000000000000000000000000000000000000000000001";
static const char hash_two[]="0000000000000000000000000000000000000000000000000000000000000002";
static reader_catalog_book book(int64_t id,const char *hash) {
  reader_catalog_book b={"epub",hash,"Book 'quoted' \xE4\xB9\xA6","Author","Book normalized","epub_chapter",100,id,0};
  return b;
}
typedef struct { size_t count;char title[16385],key[72];int stop,reenter;reader_catalog *catalog; } page;
static int receive(void *context,const reader_catalog_row *row) {
  page *p=context;
  if(p->key[0]) CHECK(strcmp(p->title,row->sort_title)<0 ||
    (!strcmp(p->title,row->sort_title) && strcmp(p->key,row->book_key)<0));
  snprintf(p->title,sizeof(p->title),"%s",row->sort_title);
  snprintf(p->key,sizeof(p->key),"%s",row->book_key);p->count++;
  if(p->reenter) { int present=0;CHECK(reader_catalog_has_local(p->catalog,10,&present,NULL)==SQLITE_MISUSE); }
  return p->stop;
}
static void reject_foreign(const char *folder,int number,const char *setup) {
  char file[4096],name[64];reader_catalog *catalog=NULL;reader_catalog_error error;
  snprintf(name,sizeof(name),"foreign-%d.db",number);path(file,sizeof(file),folder,name);
  sqlite3 *db=external(file);sql(db,setup);CHECK(sqlite3_close(db)==SQLITE_OK);
  size_t before_size=0,after_size=0;unsigned char *before=file_bytes(file,&before_size);
  CHECK(reader_catalog_open(file,&catalog,&error)!=SQLITE_OK && catalog==NULL);
  unsigned char *after=file_bytes(file,&after_size);
  CHECK(before_size==after_size && !memcmp(before,after,before_size));free(before);free(after);
}

typedef struct {
  reader_catalog *catalog;const char *path;int lock,result;
#ifdef _WIN32
  HANDLE event,thread;
#else
  pthread_mutex_t mutex;pthread_cond_t condition;pthread_t thread;int ready;
#endif
} worker;
static void worker_run(worker *w) {
  if(!w->lock) { int present=0;w->result=reader_catalog_has_local(w->catalog,10,&present,NULL);return; }
  sqlite3 *db=external(w->path);sql(db,"BEGIN IMMEDIATE");
#ifdef _WIN32
  CHECK(SetEvent(w->event));Sleep(200);
#else
  CHECK(pthread_mutex_lock(&w->mutex)==0);w->ready=1;
  CHECK(pthread_cond_signal(&w->condition)==0);CHECK(pthread_mutex_unlock(&w->mutex)==0);
  struct timespec delay={0,200000000};nanosleep(&delay,NULL);
#endif
  sql(db,"COMMIT");CHECK(sqlite3_close(db)==SQLITE_OK);w->result=SQLITE_OK;
}
#ifdef _WIN32
static DWORD WINAPI worker_entry(LPVOID context) { worker_run(context);return 0; }
#else
static void *worker_entry(void *context) { worker_run(context);return NULL; }
#endif
static void worker_start(worker *w) {
#ifdef _WIN32
  w->event=CreateEventW(NULL,FALSE,FALSE,NULL);CHECK(w->event);
  w->thread=CreateThread(NULL,0,worker_entry,w,0,NULL);CHECK(w->thread);
  if(w->lock) CHECK(WaitForSingleObject(w->event,5000)==WAIT_OBJECT_0);
#else
  CHECK(pthread_mutex_init(&w->mutex,NULL)==0);CHECK(pthread_cond_init(&w->condition,NULL)==0);
  CHECK(pthread_create(&w->thread,NULL,worker_entry,w)==0);
  if(w->lock) {
    CHECK(pthread_mutex_lock(&w->mutex)==0);
    while(!w->ready) CHECK(pthread_cond_wait(&w->condition,&w->mutex)==0);
    CHECK(pthread_mutex_unlock(&w->mutex)==0);
  }
#endif
}
static void worker_join(worker *w) {
#ifdef _WIN32
  CHECK(WaitForSingleObject(w->thread,10000)==WAIT_OBJECT_0);CloseHandle(w->thread);CloseHandle(w->event);
#else
  CHECK(pthread_join(w->thread,NULL)==0);CHECK(pthread_mutex_destroy(&w->mutex)==0);
  CHECK(pthread_cond_destroy(&w->condition)==0);
#endif
}
static uint64_t milliseconds(void) {
#ifdef _WIN32
  return GetTickCount64();
#else
  struct timespec now;CHECK(clock_gettime(CLOCK_MONOTONIC,&now)==0);
  return (uint64_t)now.tv_sec*1000+(uint64_t)now.tv_nsec/1000000;
#endif
}

int main(int argc,char **argv) {
  CHECK(argc==3 && getenv("GITHUB_ACTIONS") && !strcmp(getenv("GITHUB_ACTIONS"),"true"));
  CHECK(sqlite3_auto_extension((void(*)(void))trace_connection)==SQLITE_OK);
  reader_catalog *catalog=NULL;reader_catalog_error error;char main_path[4096],paged_path[4096];
  path(main_path,sizeof(main_path),argv[1],"catalog-\xE4\xB9\xA6.db");
  size_t schema_size=0,compiled_size=0;unsigned char *schema=file_bytes(argv[2],&schema_size);
  const char *compiled=reader_catalog_migration(&compiled_size);
  CHECK(schema_size==compiled_size && !memcmp(schema,compiled,schema_size));free(schema);
  CHECK(reader_catalog_open(main_path,&catalog,&error)==SQLITE_OK);
  CHECK(reader_catalog_close(&catalog,&error)==SQLITE_OK && catalog==NULL);
  CHECK(reader_catalog_open(main_path,&catalog,&error)==SQLITE_OK);
  sqlite3 *db=external(main_path);
  CHECK(scalar(db,"PRAGMA application_id")==1163416144 && scalar(db,"PRAGMA user_version")==1);
  PASSED("migration_matches_source_and_reopens");

  reject_foreign(argv[1],1,"CREATE TABLE unrelated(value TEXT);INSERT INTO unrelated VALUES('keep');");
  reject_foreign(argv[1],2,"PRAGMA application_id=1163416131;PRAGMA user_version=7;CREATE TABLE books(source BLOB);");
  reject_foreign(argv[1],3,"PRAGMA application_id=1163416144;PRAGMA user_version=2;");
  reject_foreign(argv[1],4,"CREATE TABLE sqliteXbooks(value TEXT);INSERT INTO sqliteXbooks VALUES('keep');");
  PASSED("foreign_identity_preserved");

  reader_catalog_book b=book(10,hash_one);
  sql(db,"CREATE TRIGGER force_mapping_failure BEFORE INSERT ON reader_local_books BEGIN SELECT RAISE(ABORT,'fixture fault'); END;");
  CHECK(reader_catalog_attach(catalog,&b,&error)!=SQLITE_OK);
  CHECK(scalar(db,"SELECT count(*) FROM reader_books")==0);
  sql(db,"DROP TRIGGER force_mapping_failure;");CHECK(reader_catalog_attach(catalog,&b,&error)==SQLITE_OK);
  CHECK(scalar(db,"SELECT count(*) FROM reader_books")==1 && scalar(db,"SELECT count(*) FROM reader_local_books")==1);
  PASSED("atomic_attach_rollback");

  b.source_bytes=101;CHECK(reader_catalog_attach(catalog,&b,&error)!=SQLITE_OK);b.source_bytes=100;
  b.location_kind="reflow_global";CHECK(reader_catalog_attach(catalog,&b,&error)!=SQLITE_OK);b.location_kind="epub_chapter";
  b.sha256=hash_two;CHECK(reader_catalog_attach(catalog,&b,&error)!=SQLITE_OK);
  CHECK(scalar(db,"SELECT count(*) FROM reader_books")==1);
  b.sdk_book_id=20;b.format="pdf";CHECK(reader_catalog_attach(catalog,&b,&error)!=SQLITE_OK);
  CHECK(scalar(db,"SELECT count(*) FROM reader_books")==1);
  b.location_kind="fixed_page";CHECK(reader_catalog_attach(catalog,&b,&error)==SQLITE_OK);
  PASSED("verified_identity_and_mode_refusals");

  b=book(300,"0000000000000000000000000000000000000000000000000000000000000003");
  CHECK(reader_catalog_attach(catalog,&b,&error)==SQLITE_OK);
  b.sdk_book_id=100;b.location_kind="reflow_global";CHECK(reader_catalog_attach(catalog,&b,&error)==SQLITE_OK);
  b.sdk_book_id=200;b.location_kind="epub_chapter";CHECK(reader_catalog_attach(catalog,&b,&error)==SQLITE_OK);
  CHECK(scalar(db,"SELECT count(*) FROM reader_local_books WHERE sdk_book_id=100 AND location_kind='reflow_global'")==1);
  int present=0;CHECK(reader_catalog_has_local(catalog,200,&present,&error)==SQLITE_OK && present==0);
  CHECK(reader_catalog_has_local(catalog,100,&present,&error)==SQLITE_OK && present==1);
  PASSED("oldest_duplicate_keeps_true_mode");

  sql(db,"UPDATE reader_books SET title='User title',favorite=1,deleted=1 WHERE book_key='epub:0000000000000000000000000000000000000000000000000000000000000001';"
    "INSERT INTO reader_revisions VALUES('00000000000000000000000000000001','book','epub:0000000000000000000000000000000000000000000000000000000000000001','delete','{}','44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a');"
    "INSERT INTO reader_outbox(revision_id,attempts,last_error) VALUES('00000000000000000000000000000001',3,'retry');");
  b=book(10,hash_one);b.title="Old SDK title";CHECK(reader_catalog_attach(catalog,&b,&error)==SQLITE_OK);
  CHECK(scalar(db,"SELECT count(*) FROM reader_books WHERE title='User title' AND favorite=1 AND deleted=1")==1);
  CHECK(scalar(db,"SELECT count(*) FROM reader_tombstones")==1);
  CHECK(scalar(db,"SELECT count(*) FROM reader_outbox WHERE attempts=3 AND last_error='retry'")==1);
  PASSED("existing_metadata_and_history_retained");

  CHECK(reader_catalog_remove_local(catalog,10,&error)==SQLITE_OK);
  CHECK(reader_catalog_has_local(catalog,10,&present,&error)==SQLITE_OK && present==0);
  CHECK(scalar(db,"SELECT count(*) FROM reader_books")==3 && scalar(db,"SELECT count(*) FROM reader_tombstones")==1);
  CHECK(reader_catalog_attach(catalog,&b,&error)==SQLITE_OK);
  CHECK(scalar(db,"SELECT count(*) FROM reader_books WHERE deleted=1")==1);
  PASSED("local_removal_retains_global_records");

  CHECK(reader_catalog_page(catalog,NULL,NULL,0,receive,NULL,&error)!=SQLITE_OK);
  CHECK(reader_catalog_page(catalog,NULL,NULL,201,receive,NULL,&error)!=SQLITE_OK);
  CHECK(reader_catalog_page(catalog,"cursor",NULL,20,receive,NULL,&error)!=SQLITE_OK);
  CHECK(reader_catalog_page(catalog,NULL,NULL,20,NULL,NULL,&error)!=SQLITE_OK);
  b=book(999,hash_two);b.title="\xc0\x80";CHECK(reader_catalog_attach(catalog,&b,&error)!=SQLITE_OK);
  b=book(999,hash_two);b.source_bytes=UINT64_MAX;CHECK(reader_catalog_attach(catalog,&b,&error)!=SQLITE_OK);
  b=book(999,hash_two);b.format="unknown";CHECK(reader_catalog_attach(catalog,&b,&error)!=SQLITE_OK);
  b=book(999,hash_two);b.sha256="bad";CHECK(reader_catalog_attach(catalog,&b,&error)!=SQLITE_OK);
  PASSED("rejects_bad_inputs");

  worker w={0};w.catalog=catalog;worker_start(&w);worker_join(&w);CHECK(w.result==SQLITE_MISUSE);
  page p={0};p.catalog=catalog;p.reenter=1;p.stop=1;
  CHECK(reader_catalog_page(catalog,NULL,NULL,200,receive,&p,&error)==SQLITE_OK && p.count==1);
  PASSED("owner_queue_and_no_reentry");

  memset(&w,0,sizeof(w));w.path=main_path;w.lock=1;worker_start(&w);
  b=book(10,hash_one);uint64_t began=milliseconds();CHECK(reader_catalog_attach(catalog,&b,&error)==SQLITE_OK);
  CHECK(milliseconds()-began>=75);worker_join(&w);CHECK(w.result==SQLITE_OK);
  PASSED("busy_writer_retries");

  sql(db,"INSERT INTO reader_shelves(shelf_id,name) VALUES('00000000000000000000000000000001','one');"
    "INSERT INTO reader_shelves(shelf_id,parent_id,name) VALUES('00000000000000000000000000000002','00000000000000000000000000000001','two');");
  CHECK(sqlite3_exec(db,"UPDATE reader_shelves SET parent_id='00000000000000000000000000000002' WHERE shelf_id='00000000000000000000000000000001'",NULL,NULL,NULL)!=SQLITE_OK);
  CHECK(scalar(db,"SELECT count(*) FROM reader_shelves WHERE parent_id IS NULL")==1);
  PASSED("shelf_triggers_still_enforced");
  CHECK(sqlite3_close(db)==SQLITE_OK);CHECK(reader_catalog_close(&catalog,&error)==SQLITE_OK);

  path(paged_path,sizeof(paged_path),argv[1],"paged.db");CHECK(reader_catalog_open(paged_path,&catalog,&error)==SQLITE_OK);
  db=external(paged_path);sql(db,"BEGIN IMMEDIATE");sqlite3_stmt *insert=NULL;
  CHECK(sqlite3_prepare_v2(db,"INSERT INTO reader_books(book_key,format,source_sha256,source_bytes,title,sort_title) VALUES(?,'txt',?,100,?,?)",-1,&insert,NULL)==SQLITE_OK);
  for(unsigned n=0;n<2500;n++) {
    char digest[65],key[72],title[64];snprintf(digest,sizeof(digest),"%064x",n+10000);
    snprintf(key,sizeof(key),"txt:%s",digest);snprintf(title,sizeof(title),"page-%04u",n/5);
    CHECK(sqlite3_bind_text(insert,1,key,-1,SQLITE_TRANSIENT)==SQLITE_OK);
    CHECK(sqlite3_bind_text(insert,2,digest,-1,SQLITE_TRANSIENT)==SQLITE_OK);
    CHECK(sqlite3_bind_text(insert,3,title,-1,SQLITE_TRANSIENT)==SQLITE_OK);
    CHECK(sqlite3_bind_text(insert,4,title,-1,SQLITE_TRANSIENT)==SQLITE_OK);
    CHECK(sqlite3_step(insert)==SQLITE_DONE);CHECK(sqlite3_reset(insert)==SQLITE_OK);
  }
  CHECK(sqlite3_finalize(insert)==SQLITE_OK);sql(db,"COMMIT");
  memset(&p,0,sizeof(p));size_t total=0;char after_title[16385]={0},after_key[72]={0};
  for(unsigned n=0;n<100;n++) {
    p.count=0;CHECK(reader_catalog_page(catalog,n?after_title:NULL,n?after_key:NULL,37,receive,&p,&error)==SQLITE_OK);
    CHECK(p.count<=37);total+=p.count;if(!p.count) break;
    snprintf(after_title,sizeof(after_title),"%s",p.title);snprintf(after_key,sizeof(after_key),"%s",p.key);
  }
  CHECK(total==2500 && continuation_sql[0]);
  char plan_sql[4500];snprintf(plan_sql,sizeof(plan_sql),"EXPLAIN QUERY PLAN %s",continuation_sql);
  sqlite3_stmt *plan=NULL;CHECK(sqlite3_prepare_v2(db,plan_sql,-1,&plan,NULL)==SQLITE_OK);int range=0;
  while(sqlite3_step(plan)==SQLITE_ROW) {
    const char *detail=(const char *)sqlite3_column_text(plan,3);puts(detail);
    if(strstr(detail,"SEARCH") && strstr(detail,"reader_books_title") && strstr(detail,"sort_title")) range=1;
  }
  CHECK(sqlite3_finalize(plan)==SQLITE_OK && range);
  CHECK(sqlite3_close(db)==SQLITE_OK);CHECK(reader_catalog_close(&catalog,&error)==SQLITE_OK);
  CHECK(reader_catalog_has_local(catalog,10,&present,&error)==SQLITE_MISUSE);
  PASSED("bounded_keyset_no_duplicates");

  CHECK(check_count==12);
  char report[4096];snprintf(report,sizeof(report),"%s/result.json",argv[1]);FILE *out=fopen(report,"wb");CHECK(out);
  fprintf(out,"{\"accepted\":true,\"source_sha\":\"%s\",\"run_id\":\"%s\",\"attempt\":\"%s\",\"sqlite_version\":\"%s\",\"checks\":[",
    getenv("GITHUB_SHA"),getenv("GITHUB_RUN_ID"),getenv("GITHUB_RUN_ATTEMPT"),sqlite3_libversion());
  for(size_t i=0;i<check_count;i++) fprintf(out,"%s{\"id\":\"%s\",\"passed\":true}",i?",":"",checks[i]);
  fprintf(out,"],\"problems\":[],\"complete_product\":false,\"ui_performance_credit\":0}\n");CHECK(fclose(out)==0);
  printf("%zu native catalog groups passed\n",check_count);return 0;
}
