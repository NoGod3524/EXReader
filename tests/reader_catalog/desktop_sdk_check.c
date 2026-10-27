/* SPDX-License-Identifier: MIT */
#define _CRT_SECURE_NO_WARNINGS
#define _POSIX_C_SOURCE 200809L
#include "catalog_sdk.h"
#include <sqlite3.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
#else
#include <time.h>
#endif
#define CHECK(x) do { if(!(x)) { fprintf(stderr,"FAIL %d: %s (%s)\n",__LINE__,#x,error.message);exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static exr_error error;
static const char *checks[16];static size_t count;
#define PASS(name) do { checks[count++]=name;puts("PASS " name); } while(0)
static char sdk_path[4096],catalog_path[4096],fixture[4096];
static exr_library *library;static reader_catalog *catalog;
static void paths(const char *folder) {
  snprintf(sdk_path,sizeof(sdk_path),"%s/sdk.sqlite",folder);
  snprintf(catalog_path,sizeof(catalog_path),"%s/product.sqlite",folder);
}
static void open_both(void) {
  OK(exr_library_open(sdk_path,&library,&error));
  CHECK(reader_catalog_open(catalog_path,&catalog,NULL)==0);
}
static void close_both(void) {
  CHECK(reader_catalog_close(&catalog,NULL)==0);
  exr_library_close(library);library=NULL;
}
static exr_book *books(size_t *n) {
  exr_book *out=NULL;OK(exr_library_books(library,"",&out,n,&error));return out;
}
static exr_book *find(exr_book *all,size_t n,int64_t id) {
  for(size_t i=0;i<n;i++) if(all[i].id==id) return &all[i];
  CHECK(0);return NULL;
}
static sqlite3 *external(void) {
  sqlite3 *db=NULL;CHECK(sqlite3_open(catalog_path,&db)==SQLITE_OK);return db;
}
static void sql(sqlite3 *db,const char *text) {
  char *message=NULL;int result=sqlite3_exec(db,text,NULL,NULL,&message);
  if(result!=SQLITE_OK) fprintf(stderr,"SQL: %s\n",message?message:"");
  sqlite3_free(message);CHECK(result==SQLITE_OK);
}
static int64_t scalar(sqlite3 *db,const char *text) {
  sqlite3_stmt *s=NULL;CHECK(sqlite3_prepare_v2(db,text,-1,&s,NULL)==SQLITE_OK);
  CHECK(sqlite3_step(s)==SQLITE_ROW);int64_t value=sqlite3_column_int64(s,0);
  CHECK(sqlite3_finalize(s)==SQLITE_OK);return value;
}
static void text_is(sqlite3 *db,const char *query,const char *expected) {
  sqlite3_stmt *s=NULL;CHECK(sqlite3_prepare_v2(db,query,-1,&s,NULL)==SQLITE_OK);
  CHECK(sqlite3_step(s)==SQLITE_ROW && !strcmp((const char *)sqlite3_column_text(s,0),expected));
  CHECK(sqlite3_finalize(s)==SQLITE_OK);
}
static void pause_for_kill(void) {
  puts("READY_TO_KILL");fflush(stdout);
  for(;;) {
#ifdef _WIN32
    Sleep(1000);
#else
    struct timespec delay={1,0};nanosleep(&delay,NULL);
#endif
  }
}
static int kill_on_mapping,observe_commit,commit_cancel;
static int trace(unsigned type,void *context,void *statement,void *extra) {
  (void)context;(void)extra;
  if(type==SQLITE_TRACE_STMT) {
    const char *query=sqlite3_sql(statement);
    if(query && kill_on_mapping && strstr(query,"INSERT INTO reader_local_books")) pause_for_kill();
    if(query && observe_commit && !strcmp(query,"COMMIT")) commit_cancel=1;
  }
  return 0;
}
static int instrument(sqlite3 *db,char **message,const sqlite3_api_routines *api) {
  (void)message;(void)api;return sqlite3_trace_v2(db,SQLITE_TRACE_STMT,trace,NULL);
}
static int cancel(void *context) { int *remaining=context;return --*remaining<=0; }
static size_t short_source_read(void *context,uint64_t offset,void *buffer,size_t size) {
  const char *text=context;
  if(offset>=3 || !size) return 0;
  *(char *)buffer=text[(size_t)offset];return 1;
}
static void source_identity_check(void) {
  exr_source source={0};char digest[65];uint64_t size=0;int remaining=1;
  source.context=(void *)"abc";source.size=3;source.read_at=short_source_read;
  OK(reader_catalog_source_identity(&source,NULL,digest,&size,&error));
  CHECK(size==3 && !strcmp(digest,"ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"));
  exr_control control={cancel,NULL,&remaining};
  CHECK(reader_catalog_source_identity(&source,&control,digest,&size,&error)==EXR_CANCELLED);
  CHECK(!digest[0] && !size);
  source.size=4;
  CHECK(reader_catalog_source_identity(&source,NULL,digest,&size,&error)==EXR_IO);
  CHECK(!digest[0] && !size);
}
static int after_commit(void *context) { (void)context;return commit_cancel; }
static unsigned char *load(const char *path,size_t *size) {
  FILE *f=fopen(path,"rb");CHECK(f);CHECK(fseek(f,0,SEEK_END)==0);
  long bytes=ftell(f);CHECK(bytes>0 && fseek(f,0,SEEK_SET)==0);
  unsigned char *data=malloc((size_t)bytes);CHECK(data);
  CHECK(fread(data,1,(size_t)bytes,f)==(size_t)bytes && fclose(f)==0);*size=(size_t)bytes;return data;
}
static void repair(void) {
  size_t n=0,failed=99;exr_book *all=books(&n);
  OK(reader_catalog_sdk_repair(catalog,library,all,n,NULL,&failed,&error));
  CHECK(failed==0);exr_books_free(all,n);
}
static void original(int64_t id,const char *expected,size_t bytes) {
  exr_source source={0};OK(exr_library_source(library,id,&source,&error));
  CHECK(source.size==bytes);char part[3];CHECK(source.read_at(source.context,0,part,3)==3);
  CHECK(!memcmp(part,expected,3));source.release(source.context);
}
int main(int argc,char **argv) {
  CHECK(argc==3 || argc==4);paths(argv[1]);
  if(argc==4) {
    if(!strcmp(argv[3],"transaction")) { kill_on_mapping=1;CHECK(sqlite3_auto_extension((void (*)(void))instrument)==SQLITE_OK); }
    open_both();int64_t id=0;OK(exr_library_import(library,EXR_TXT,"abc",3,"Crash book",&id,&error));
    if(!strcmp(argv[3],"sdk")) pause_for_kill();
    repair();CHECK(0);
  }
  CHECK(sqlite3_auto_extension((void (*)(void))instrument)==SQLITE_OK);
  open_both();
  if(!strcmp(argv[2],"recover")) {
    sqlite3 *db=external();CHECK(scalar(db,"SELECT count(*) FROM reader_books")==0);
    CHECK(scalar(db,"SELECT count(*) FROM reader_local_books")==0);CHECK(sqlite3_close(db)==SQLITE_OK);
    repair();db=external();CHECK(scalar(db,"SELECT count(*) FROM reader_books")==1);
    CHECK(scalar(db,"SELECT count(*) FROM reader_local_books")==1);
    CHECK(sqlite3_close(db)==SQLITE_OK);original(1,"abc",3);close_both();puts("RECOVERED");return 0;
  }
  source_identity_check();
  CHECK(!strcmp(sqlite3_libversion(),"3.54.0"));
  const char *options[]={"THREADSAFE=1","DQS=0","DEFAULT_FOREIGN_KEYS","OMIT_LOAD_EXTENSION","MAX_LENGTH=2147483647"};
  for(size_t i=0;i<sizeof(options)/sizeof(options[0]);i++) CHECK(sqlite3_compileoption_used(options[i]));
  CHECK(!sqlite3_compileoption_used("ENABLE_FTS5"));
  PASS("joint_sqlite_version_and_compile_limits");
  int64_t txt=0,legacy=0,bounded=0,pdf=0,large=0,again=0;int created=0;char key[72];
  OK(exr_library_import_unique(library,EXR_TXT,"abc",3,"Cafe\xCC\x81 'quoted'",&txt,&created,&error));CHECK(created==1);
  size_t n=0;exr_book *all=books(&n);CHECK(n==1);
  OK(reader_catalog_sdk_attach(catalog,library,all,NULL,key,&error));exr_books_free(all,n);
  CHECK(!strcmp(key,"txt:ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"));
  sqlite3 *db=external();text_is(db,"SELECT sort_title FROM reader_books","Caf\xC3\xA9 'quoted'");
  text_is(db,"SELECT location_kind FROM reader_local_books","reflow_global");CHECK(sqlite3_close(db)==SQLITE_OK);
  original(txt,"abc",3);PASS("original_sha256_and_nfc_title");
  OK(exr_library_import_unique(library,EXR_TXT,"abc",3,"ignored",&again,&created,&error));CHECK(!created && again==txt);
  db=external();sql(db,"UPDATE reader_books SET title='User metadata',favorite=1");CHECK(sqlite3_close(db)==SQLITE_OK);
  all=books(&n);OK(reader_catalog_sdk_attach(catalog,library,find(all,n,txt),NULL,NULL,&error));exr_books_free(all,n);
  db=external();text_is(db,"SELECT title FROM reader_books","User metadata");CHECK(scalar(db,"SELECT favorite FROM reader_books")==1);CHECK(sqlite3_close(db)==SQLITE_OK);
  PASS("duplicate_preserves_user_metadata");
  snprintf(fixture,sizeof(fixture),"%s/sample.epub",argv[2]);size_t bytes=0;unsigned char *data=load(fixture,&bytes);
  OK(exr_library_import(library,EXR_EPUB,data,bytes,"Legacy first",&legacy,&error));free(data);
  OK(exr_library_import_file(library,EXR_EPUB,fixture,"Bounded duplicate",&bounded,&error));CHECK(legacy<bounded);
  all=books(&n);OK(reader_catalog_sdk_attach(catalog,library,find(all,n,bounded),NULL,NULL,&error));
  OK(reader_catalog_sdk_attach(catalog,library,find(all,n,legacy),NULL,NULL,&error));exr_books_free(all,n);
  db=external();CHECK(scalar(db,"SELECT sdk_book_id FROM reader_local_books WHERE book_key LIKE 'epub:%'")==legacy);
  text_is(db,"SELECT location_kind FROM reader_local_books WHERE book_key LIKE 'epub:%'","reflow_global");CHECK(sqlite3_close(db)==SQLITE_OK);
  PASS("oldest_duplicate_keeps_real_legacy_mode");
  snprintf(fixture,sizeof(fixture),"%s/font-book.epub",argv[2]);
  OK(exr_library_import_file(library,EXR_EPUB,fixture,"Bounded unique",&again,&error));repair();
  db=external();CHECK(scalar(db,"SELECT count(*) FROM reader_local_books WHERE location_kind='epub_chapter'")==1);CHECK(sqlite3_close(db)==SQLITE_OK);
  PASS("bounded_epub_mode_from_public_api");
  snprintf(fixture,sizeof(fixture),"%s/pdf-public.pdf",argv[2]);
  OK(exr_library_import_file(library,EXR_PDF,fixture,"PDF",&pdf,&error));repair();
  db=external();CHECK(scalar(db,"SELECT count(*) FROM reader_local_books WHERE location_kind='fixed_page'")==1);CHECK(sqlite3_close(db)==SQLITE_OK);
  PASS("pdf_fixed_page_mapping");
  data=malloc(196609);CHECK(data);
  for(size_t i=0;i<196609;i++) data[i]=(unsigned char)('a'+((i*17+i/65536)%26));
  OK(exr_library_import(library,EXR_TXT,data,196609,"Large source",&large,&error));free(data);
  all=books(&n);int remaining=4;exr_control control={cancel,NULL,&remaining};
  CHECK(reader_catalog_sdk_attach(catalog,library,find(all,n,large),&control,key,&error)==EXR_CANCELLED && !key[0]);
  int present=1;CHECK(reader_catalog_has_local(catalog,large,&present,NULL)==0 && !present);
  original(large,"ari",196609);
  OK(reader_catalog_sdk_attach(catalog,library,find(all,n,large),NULL,key,&error));exr_books_free(all,n);
  CHECK(strlen(key)==68);PASS("multichunk_cancel_retains_committed_sdk_source");
  int64_t failed_book=0;OK(exr_library_import(library,EXR_TXT,"repair me",9,"Pending metadata",&failed_book,&error));
  db=external();sql(db,"CREATE TRIGGER injected_failure BEFORE INSERT ON reader_local_books BEGIN SELECT RAISE(ABORT,'injected product failure');END");CHECK(sqlite3_close(db)==SQLITE_OK);
  all=books(&n);CHECK(reader_catalog_sdk_attach(catalog,library,find(all,n,failed_book),NULL,NULL,&error)==EXR_DATABASE);exr_books_free(all,n);
  original(failed_book,"rep",9);db=external();CHECK(scalar(db,"SELECT count(*) FROM reader_books WHERE title='Pending metadata'")==0);
  sql(db,"DROP TRIGGER injected_failure");CHECK(sqlite3_close(db)==SQLITE_OK);
  close_both();open_both();repair();CHECK(reader_catalog_has_local(catalog,failed_book,&present,NULL)==0 && present);
  PASS("postcommit_product_failure_repaired_after_restart");
  int64_t commit_book=0;OK(exr_library_import(library,EXR_TXT,"publication",11,"Commit boundary",&commit_book,&error));
  all=books(&n);exr_control publication_control={after_commit,NULL,NULL};size_t failed=0;observe_commit=1;
  CHECK(reader_catalog_sdk_repair(catalog,library,find(all,n,commit_book),1,&publication_control,&failed,&error)==EXR_CANCELLED);
  observe_commit=0;exr_books_free(all,n);
  CHECK(commit_cancel && reader_catalog_has_local(catalog,commit_book,&present,NULL)==0 && present);
  original(commit_book,"pub",11);PASS("cancel_at_publication_reports_cancel_retains_commit");
  char report[4096];snprintf(report,sizeof(report),"%s/sdk-result.json",argv[1]);FILE *out=fopen(report,"wb");CHECK(out);
  CHECK(count==9);fprintf(out,"{\"accepted\":true,\"source_sha\":\"%s\",\"run_id\":\"%s\",\"attempt\":\"%s\",\"sqlite_version\":\"%s\",\"sqlite_source_id\":\"%s\",\"checks\":[",getenv("GITHUB_SHA"),getenv("GITHUB_RUN_ID"),getenv("GITHUB_RUN_ATTEMPT"),sqlite3_libversion(),sqlite3_sourceid());
  for(size_t i=0;i<count;i++) fprintf(out,"%s{\"id\":\"%s\",\"passed\":true}",i?",":"",checks[i]);
  fprintf(out,"],\"problems\":[],\"complete_product\":false}\n");CHECK(fclose(out)==0);close_both();return 0;
}
