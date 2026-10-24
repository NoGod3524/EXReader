/* SPDX-License-Identifier: MIT */
#define _CRT_SECURE_NO_WARNINGS
#include "catalog.h"
#include <sqlite3.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define CHECK(x) do { if(!(x)) { fprintf(stderr,"FAIL %d %s\n",__LINE__,#x);exit(1); } } while(0)
static const char *names[16];static size_t groups;
#define PASS(name) do { names[groups++]=name;puts("PASS " name); } while(0)
static char forward_sql[1024],reverse_sql[1024];
static int trace(unsigned event,void *context,void *statement,void *unused) {
  (void)context;(void)unused;
  if(event==SQLITE_TRACE_STMT) {
    const char *sql=sqlite3_sql(statement);
    if(sql && !strncmp(sql,"SELECT b.book_key",17)) {
      if(strstr(sql,"AND (b.sort_title,b.book_key)>")) snprintf(forward_sql,sizeof(forward_sql),"%s",sql);
      if(strstr(sql,"AND (b.sort_title,b.book_key)<")) snprintf(reverse_sql,sizeof(reverse_sql),"%s",sql);
    }
  }
  return 0;
}
static int trace_connection(sqlite3 *db,char **message,const sqlite3_api_routines *api) {
  (void)message;(void)api;return sqlite3_trace_v2(db,SQLITE_TRACE_STMT,trace,NULL);
}
static void sql(sqlite3 *db,const char *query) { CHECK(sqlite3_exec(db,query,NULL,NULL,NULL)==SQLITE_OK); }
static void key_for(unsigned n,char key[72]) { snprintf(key,72,"txt:%064x",n); }
typedef struct {
  reader_catalog *catalog;size_t count;int direction,stop,reenter,track;
  unsigned char seen[2501];char title[16385],key[72],author[16385];
} page;
static int receive(void *context,const reader_catalog_row *row) {
  page *p=context;CHECK(row->author && row->book_key && row->sort_title);
  CHECK(row->sdk_book_id==0 && row->location_kind==NULL);
  if(p->key[0]) {
    int order=strcmp(p->title,row->sort_title);if(!order) order=strcmp(p->key,row->book_key);
    CHECK(p->direction>0 ? order<0:order>0);
  }
  snprintf(p->title,sizeof(p->title),"%s",row->sort_title);snprintf(p->key,sizeof(p->key),"%s",row->book_key);
  snprintf(p->author,sizeof(p->author),"%s",row->author);p->count++;
  if(p->track) {
    CHECK(strlen(row->book_key)==68);unsigned n=(unsigned)strtoul(row->book_key+60,NULL,16);
    CHECK(n>0 && n<=2500 && !p->seen[n]);p->seen[n]=1;
  }
  if(p->reenter) {
    int found=-1;CHECK(reader_catalog_find(p->catalog,row->book_key,NULL,receive,p,&found,NULL)==SQLITE_MISUSE && found==0);
    CHECK(reader_catalog_query_page(p->catalog,NULL,NULL,NULL,1,1,receive,p,NULL)==SQLITE_MISUSE);
  }
  return p->stop;
}
static size_t scan(reader_catalog *catalog,const char *query,int direction,int track) {
  page p={0};p.catalog=catalog;p.direction=direction;p.track=track;
  char title[16385]={0},key[72]={0};size_t total=0;
  for(unsigned i=0;i<100;i++) {
    p.count=0;
    CHECK(reader_catalog_query_page(catalog,i?title:NULL,i?key:NULL,query,direction,37,receive,&p,NULL)==SQLITE_OK);
    CHECK(p.count<=37);total+=p.count;if(!p.count) break;
    snprintf(title,sizeof(title),"%s",p.title);snprintf(key,sizeof(key),"%s",p.key);
    CHECK(i<99);
  }
  if(track) for(unsigned i=1;i<=2500;i++) CHECK(p.seen[i]==(i!=2499));
  return total;
}
static void range_plan(sqlite3 *db,const char *query) {
  char text[1200];CHECK(query[0]);CHECK(!strstr(query,"OFFSET"));
  snprintf(text,sizeof(text),"EXPLAIN QUERY PLAN %s",query);sqlite3_stmt *statement=NULL;
  CHECK(sqlite3_prepare_v2(db,text,-1,&statement,NULL)==SQLITE_OK);int found=0,status;
  while((status=sqlite3_step(statement))==SQLITE_ROW) {
    const char *detail=(const char *)sqlite3_column_text(statement,3);puts(detail);
    if(strstr(detail,"SEARCH") && strstr(detail,"reader_books_title") && strstr(detail,"sort_title")) found=1;
  }
  CHECK(status==SQLITE_DONE && found);CHECK(sqlite3_finalize(statement)==SQLITE_OK);
}
int main(int argc,char **argv) {
  CHECK(argc==2 && getenv("GITHUB_ACTIONS") && !strcmp(getenv("GITHUB_ACTIONS"),"true"));
  CHECK(sqlite3_auto_extension((void(*)(void))trace_connection)==SQLITE_OK);
  char path[4096];snprintf(path,sizeof(path),"%s/shelf.db",argv[1]);FILE *prior=fopen(path,"rb");CHECK(!prior);
  reader_catalog *catalog=NULL;CHECK(reader_catalog_open(path,&catalog,NULL)==SQLITE_OK);
  sqlite3 *db=NULL;CHECK(sqlite3_open(path,&db)==SQLITE_OK);sql(db,"PRAGMA foreign_keys=ON;BEGIN IMMEDIATE");
  sqlite3_stmt *insert=NULL;
  CHECK(sqlite3_prepare_v2(db,"INSERT INTO reader_books(book_key,format,source_sha256,source_bytes,title,author,sort_title,deleted) VALUES(?1,'txt',?2,100,?3,?4,?3,?5)",-1,&insert,NULL)==SQLITE_OK);
  for(unsigned i=1;i<=2500;i++) {
    char key[72],title[64];key_for(i,key);
    if(i<=130) snprintf(title,sizeof(title),"Shared title");
    else if(i==131) snprintf(title,sizeof(title),"Literal %%_! title");
    else snprintf(title,sizeof(title),"Title %04u",i);
    CHECK(sqlite3_bind_text(insert,1,key,-1,SQLITE_TRANSIENT)==SQLITE_OK);
    CHECK(sqlite3_bind_text(insert,2,key+4,-1,SQLITE_TRANSIENT)==SQLITE_OK);
    CHECK(sqlite3_bind_text(insert,3,title,-1,SQLITE_TRANSIENT)==SQLITE_OK);
    CHECK(sqlite3_bind_text(insert,4,i%17 ? "Regular author":"Writer_50%! \xE4\xB8\xAD\xE6\x96\x87",-1,SQLITE_STATIC)==SQLITE_OK);
    CHECK(sqlite3_bind_int(insert,5,i==2499)==SQLITE_OK);
    CHECK(sqlite3_step(insert)==SQLITE_DONE);CHECK(sqlite3_reset(insert)==SQLITE_OK);
  }
  CHECK(sqlite3_finalize(insert)==SQLITE_OK);sql(db,"COMMIT");
  CHECK(scan(catalog,NULL,1,1)==2499);PASS("forward_all_visible_stable_keys_no_duplicates");
  CHECK(scan(catalog,NULL,-1,1)==2499);PASS("reverse_all_visible_stable_keys_no_duplicates");
  CHECK(scan(catalog,"Shared title",1,0)==130 && scan(catalog,"Shared title",-1,0)==130);
  PASS("same_title_130_rows_cross_page_boundaries");
  /* 147 seeded authors, one of whom (2499 == 17*147) is tombstoned. */
  CHECK(scan(catalog,"writer_50%!",1,0)==146 && scan(catalog,"%_!",1,0)==1);
  CHECK(scan(catalog,"%!",-1,0)==146 && scan(catalog,"\xE4\xB8\xAD\xE6\x96\x87",1,0)==146);
  PASS("literal_title_author_punctuation_and_utf8_search");
  CHECK(scan(catalog,"",1,0)==2499 && scan(catalog,"no-match-at-all",-1,0)==0);
  PASS("empty_and_missing_filters");
  char key[72];key_for(50,key);page p={0};p.direction=1;int found=-1;
  CHECK(reader_catalog_find(catalog,key,"shared",receive,&p,&found,NULL)==SQLITE_OK && found==1 && p.count==1);
  p.count=0;CHECK(reader_catalog_find(catalog,key,"no-match",receive,&p,&found,NULL)==SQLITE_OK && found==0 && p.count==0);
  key_for(2499,key);CHECK(reader_catalog_find(catalog,key,NULL,receive,&p,&found,NULL)==SQLITE_OK && found==0);
  key_for(9000,key);CHECK(reader_catalog_find(catalog,key,NULL,receive,&p,&found,NULL)==SQLITE_OK && found==0);
  PASS("viewport_key_lookup_respects_filter_delete_and_absence");
  key_for(50,key);char update[256];snprintf(update,sizeof(update),"UPDATE reader_books SET title='Renamed title',sort_title='Renamed title' WHERE book_key='%s'",key);sql(db,update);
  memset(&p,0,sizeof(p));p.direction=1;
  CHECK(reader_catalog_find(catalog,key,NULL,receive,&p,&found,NULL)==SQLITE_OK && found==1 && !strcmp(p.title,"Renamed title"));
  CHECK(reader_catalog_find(catalog,key,"shared",receive,&p,&found,NULL)==SQLITE_OK && found==0);
  PASS("anchor_follows_current_title_without_guessing_old_cursor");
  char oversized[4098];memset(oversized,'x',sizeof(oversized));oversized[sizeof(oversized)-1]=0;
  CHECK(reader_catalog_query_page(catalog,NULL,NULL,NULL,0,50,receive,&p,NULL)==SQLITE_MISUSE);
  CHECK(reader_catalog_query_page(catalog,NULL,NULL,NULL,1,201,receive,&p,NULL)==SQLITE_MISUSE);
  CHECK(reader_catalog_query_page(catalog,"title",NULL,NULL,1,50,receive,&p,NULL)==SQLITE_MISUSE);
  CHECK(reader_catalog_query_page(catalog,NULL,NULL,"\xc0\xaf",1,50,receive,&p,NULL)==SQLITE_MISUSE);
  CHECK(reader_catalog_query_page(catalog,NULL,NULL,oversized,1,50,receive,&p,NULL)==SQLITE_MISUSE);
  CHECK(reader_catalog_find(catalog,"",NULL,receive,&p,&found,NULL)==SQLITE_MISUSE);
  PASS("query_limits_invalid_utf8_and_partial_cursors_refused");
  memset(&p,0,sizeof(p));p.catalog=catalog;p.direction=1;p.stop=p.reenter=1;
  CHECK(reader_catalog_query_page(catalog,NULL,NULL,NULL,1,200,receive,&p,NULL)==SQLITE_OK && p.count==1);
  PASS("callback_stop_and_query_reentry_refused");
  range_plan(db,forward_sql);range_plan(db,reverse_sql);PASS("actual_forward_reverse_sql_uses_index_ranges");
  CHECK(groups==10 && !strcmp(sqlite3_libversion(),"3.54.0"));
  CHECK(sqlite3_close(db)==SQLITE_OK);CHECK(reader_catalog_close(&catalog,NULL)==SQLITE_OK);
  snprintf(path,sizeof(path),"%s/shelf-result.json",argv[1]);FILE *report=fopen(path,"wb");CHECK(report);
  fprintf(report,"{\"accepted\":true,\"source_sha\":\"%s\",\"run_id\":\"%s\",\"attempt\":\"%s\",\"rows\":2500,\"visible\":2499,\"checks\":[",
    getenv("GITHUB_SHA"),getenv("GITHUB_RUN_ID"),getenv("GITHUB_RUN_ATTEMPT"));
  for(size_t i=0;i<groups;i++) fprintf(report,"%s{\"id\":\"%s\",\"passed\":true}",i?",":"",names[i]);
  fprintf(report,"],\"ui_credit\":0,\"problems\":[]}\n");CHECK(!fclose(report));return 0;
}
