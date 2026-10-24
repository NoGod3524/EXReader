/* SPDX-License-Identifier: MIT */
#define _CRT_SECURE_NO_WARNINGS
#include "catalog.h"
#include <sqlite3.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
#else
#include <pthread.h>
#endif

#define CHECK(x) do { if(!(x)) { fprintf(stderr,"FAIL %d %s\n",__LINE__,#x);exit(1); } } while(0)
#define PASS(name) do { names[groups++]=name;puts("PASS " name); } while(0)
static const char *names[20];static unsigned groups,writes;
static const char *tables[]={"reader_shelves","reader_tags","reader_series"};
static const char *joins[]={"reader_book_shelves","reader_book_tags","reader_book_series"};
static char member_forward[1800],member_reverse[1800],group_forward[1024],group_reverse[1024];
static reader_catalog *catalog;
static int authorize(void *unused,int action,const char *a,const char *b,const char *db,const char *trigger) {
  (void)unused;(void)a;(void)b;(void)db;(void)trigger;
  if(action==SQLITE_INSERT || action==SQLITE_UPDATE || action==SQLITE_DELETE) { writes++;return SQLITE_DENY; }
  return SQLITE_OK;
}
static int trace(unsigned event,void *context,void *statement,void *unused) {
  (void)context;(void)unused;
  if(event==SQLITE_TRACE_STMT) {
    const char *q=sqlite3_sql(statement);
    if(q && strstr(q,"FROM reader_book_series m")) {
      if(strstr(q,"(m.ordinal,m.book_key)>(")) snprintf(member_forward,sizeof(member_forward),"%s",q);
      if(strstr(q,"(m.ordinal,m.book_key)<(")) snprintf(member_reverse,sizeof(member_reverse),"%s",q);
    }
    if(q && strstr(q,"FROM reader_shelves g")) {
      if(strstr(q,"(g.ordinal,g.shelf_id)>(")) snprintf(group_forward,sizeof(group_forward),"%s",q);
      if(strstr(q,"(g.ordinal,g.shelf_id)<(")) snprintf(group_reverse,sizeof(group_reverse),"%s",q);
    }
  }
  return 0;
}
static int observe(sqlite3 *db,char **error,const sqlite3_api_routines *api) {
  (void)error;(void)api;
  CHECK(sqlite3_set_authorizer(db,authorize,NULL)==SQLITE_OK);
  return sqlite3_trace_v2(db,SQLITE_TRACE_STMT,trace,NULL);
}
static void sql(sqlite3 *db,const char *q) { CHECK(sqlite3_exec(db,q,NULL,NULL,NULL)==SQLITE_OK); }
static void gid(unsigned n,char out[33]) { snprintf(out,33,"%032x",n); }
static void bid(unsigned n,char out[72]) { snprintf(out,72,"txt:%064x",n); }
static unsigned number(const char *id) { return (unsigned)strtoul(id+strlen(id)-8,NULL,16); }
typedef struct {
  size_t count;unsigned last;int direction,reenter,stop,deleted,parent,book_deleted;
  uint64_t ordinal;char id[72],name[1025];
} capture;
static int receive_group(void *context,const reader_catalog_group_row *row) {
  capture *p=context;unsigned n=number(row->id);
  if(p->last) CHECK(p->direction>0 ? p->last<n:p->last>n);
  p->last=n;p->ordinal=row->ordinal;p->deleted=row->deleted;p->parent=row->parent_id!=NULL;p->count++;
  snprintf(p->id,sizeof(p->id),"%s",row->id);snprintf(p->name,sizeof(p->name),"%s",row->name);
  if(p->reenter) {
    int found=7;
    CHECK(reader_catalog_group_find(catalog,READER_CATALOG_SHELF,row->id,receive_group,p,&found,NULL)==SQLITE_MISUSE && found==0);
    CHECK(reader_catalog_groups_page(catalog,READER_CATALOG_SHELF,NULL,NULL,1,1,receive_group,p,NULL)==SQLITE_MISUSE);
  }
  return p->stop;
}
static int receive_member(void *context,const reader_catalog_group_book_row *row) {
  capture *p=context;unsigned n=number(row->book.book_key);
  if(p->last) CHECK(p->direction>0 ? p->last<n:p->last>n);
  CHECK(row->book.author && row->book.title && row->book.sort_title && row->book.deleted==0);
  p->last=n;p->ordinal=row->ordinal;p->count++;
  snprintf(p->id,sizeof(p->id),"%s",row->book.book_key);
  if(p->reenter) {
    char id[33];gid(1,id);
    CHECK(reader_catalog_group_books_page(catalog,READER_CATALOG_SHELF,id,NULL,NULL,0,1,1,receive_member,p,NULL)==SQLITE_MISUSE);
  }
  return p->stop;
}
static int receive_membership(void *context,const reader_catalog_membership_row *row) {
  capture *p=context;p->count++;p->ordinal=row->ordinal;p->deleted=row->group_deleted;p->book_deleted=row->book_deleted;
  CHECK(row->group_id && row->book_key);return 0;
}
static size_t scan_groups(reader_catalog_group_kind kind,int direction) {
  capture p={0};p.direction=direction;reader_catalog_group_cursor cursor={0};char key[33];size_t total=0;
  for(unsigned i=0;i<100;i++) {
    p.count=0;
    CHECK(reader_catalog_groups_page(catalog,kind,NULL,i?&cursor:NULL,direction,37,receive_group,&p,NULL)==SQLITE_OK);
    CHECK(p.count<=37);total+=p.count;if(!p.count) return total;
    snprintf(key,sizeof(key),"%.32s",p.id);cursor.id=key;cursor.ordinal=p.ordinal;
  }
  CHECK(0);return 0;
}
static size_t scan_members(reader_catalog_group_kind kind,int direction,int local,const char *query) {
  capture p={0};p.direction=direction;reader_catalog_member_cursor cursor={0};char key[72],id[33];size_t total=0;
  gid(1,id);
  for(unsigned i=0;i<100;i++) {
    p.count=0;
    CHECK(reader_catalog_group_books_page(catalog,kind,id,i?&cursor:NULL,query,local,direction,37,receive_member,&p,NULL)==SQLITE_OK);
    CHECK(p.count<=37);total+=p.count;if(!p.count) return total;
    snprintf(key,sizeof(key),"%s",p.id);cursor.book_key=key;cursor.ordinal=p.ordinal;
  }
  CHECK(0);return 0;
}
static void plan(sqlite3 *db,const char *q,const char *index,const char *range) {
  char text[1900];CHECK(q[0] && !strstr(q,"OFFSET"));snprintf(text,sizeof(text),"EXPLAIN QUERY PLAN %s",q);
  sqlite3_stmt *s=NULL;CHECK(sqlite3_prepare_v2(db,text,-1,&s,NULL)==SQLITE_OK);int status,found=0;
  while((status=sqlite3_step(s))==SQLITE_ROW) {
    const char *detail=(const char *)sqlite3_column_text(s,3);
    if(detail && strstr(detail,index) && strstr(detail,range) && strstr(detail,"SEARCH")) found=1;
  }
  CHECK(status==SQLITE_DONE && found);CHECK(sqlite3_finalize(s)==SQLITE_OK);
}
#ifdef _WIN32
static DWORD WINAPI wrong_owner(LPVOID unused) {
#else
static void *wrong_owner(void *unused) {
#endif
  (void)unused;capture p={0};char id[33];gid(1,id);int found=8;
  CHECK(reader_catalog_groups_page(catalog,READER_CATALOG_SHELF,NULL,NULL,1,1,receive_group,&p,NULL)==SQLITE_MISUSE);
  CHECK(reader_catalog_membership_find(catalog,READER_CATALOG_SHELF,id,"txt:any",receive_membership,&p,&found,NULL)==SQLITE_MISUSE && found==0);
  CHECK(!p.count);return 0;
}

int main(int argc,char **argv) {
  CHECK(argc==2);char path[2048];snprintf(path,sizeof(path),"%s/organization.sqlite",argv[1]);
  CHECK(reader_catalog_open(path,&catalog,NULL)==SQLITE_OK);CHECK(reader_catalog_close(&catalog,NULL)==SQLITE_OK);
  sqlite3 *db=NULL;CHECK(sqlite3_open(path,&db)==SQLITE_OK);sql(db,"PRAGMA foreign_keys=ON;BEGIN IMMEDIATE");
  char q[2048];
  for(unsigned n=1;n<=2202;n++) {
    snprintf(q,sizeof(q),"INSERT INTO reader_books VALUES('txt:%064x','txt','%064x',123,'Book %04u','%s','Book %04u',%u,%u)",n,n,n,n==17?"%_!作者":"Author",n,n==17,n==2202);sql(db,q);
    if(n%2) { snprintf(q,sizeof(q),"INSERT INTO reader_local_books VALUES('txt:%064x',%u,'reflow_global')",n,n);sql(db,q); }
    for(unsigned k=0;k<3;k++) {
      if(k==0) snprintf(q,sizeof(q),"INSERT INTO reader_shelves VALUES('%032x',%s,'Group %04u',%u,%u)",n,n==2?"'00000000000000000000000000000001'":"NULL",n,n/7,n==2202);
      else snprintf(q,sizeof(q),"INSERT INTO %s VALUES('%032x','Group %04u',%u)",tables[k],n,n,n==2202);
      sql(db,q);
      if(k==1) snprintf(q,sizeof(q),"INSERT INTO reader_book_tags VALUES('txt:%064x','%032x')",n,1);
      else snprintf(q,sizeof(q),"INSERT INTO %s VALUES('%032x','txt:%064x',%u)",joins[k],1,n,n/7);
      sql(db,q);
    }
  }
  snprintf(q,sizeof(q),"INSERT INTO reader_book_shelves VALUES('%032x','txt:%064x',7);COMMIT",2202,1);sql(db,q);
  CHECK(sqlite3_close(db)==SQLITE_OK);db=NULL;
  CHECK(sqlite3_auto_extension((void (*)(void))observe)==SQLITE_OK);
  CHECK(reader_catalog_open(path,&catalog,NULL)==SQLITE_OK);CHECK(sqlite3_open(path,&db)==SQLITE_OK);
  char id[33],key[72];gid(1,id);bid(1,key);capture p={0};p.direction=1;int found=9;
  CHECK(reader_catalog_groups_page(catalog,READER_CATALOG_SHELF,id,NULL,1,20,receive_group,&p,NULL)==SQLITE_OK && p.count==1 && p.last==2 && p.parent);
  PASS("child_shelves_are_read_through_the_public_parent_view");
  for(unsigned k=0;k<3;k++) for(int direction=-1;direction<=1;direction+=2)
    CHECK(scan_groups((reader_catalog_group_kind)k,direction)==(k==0?2200:2201));
  PASS("three_group_kinds_page_both_directions_without_missing_or_duplicate_ids");
  PASS("shelf_ordinal_ties_cross_37_row_pages_in_stable_id_order");
  gid(2202,id);memset(&p,0,sizeof(p));
  CHECK(reader_catalog_group_find(catalog,READER_CATALOG_SHELF,id,receive_group,&p,&found,NULL)==SQLITE_OK && found && p.deleted);
  gid(9999,id);CHECK(reader_catalog_group_find(catalog,READER_CATALOG_TAG,id,receive_group,&p,&found,NULL)==SQLITE_OK && !found);
  PASS("group_lookup_preserves_tombstoned_metadata_and_distinguishes_missing");
  for(unsigned k=0;k<3;k++) for(int direction=-1;direction<=1;direction+=2)
    CHECK(scan_members((reader_catalog_group_kind)k,direction,0,NULL)==2201);
  PASS("shelf_tag_series_member_keysets_traverse_all_2201_visible_books");
  for(unsigned k=0;k<3;k++) CHECK(scan_members((reader_catalog_group_kind)k,1,1,NULL)==1101);
  PASS("downloaded_filter_keeps_local_mapping_and_global_view_keeps_cloud_books");
  CHECK(scan_members(READER_CATALOG_SERIES,1,0,"%_!")==1 && scan_members(READER_CATALOG_TAG,-1,0,"作者")==1);
  CHECK(scan_members(READER_CATALOG_SHELF,1,0,"missing")==0);
  PASS("member_title_author_filters_are_literal_utf8_and_empty_safe");
  gid(2202,id);memset(&p,0,sizeof(p));
  CHECK(reader_catalog_group_books_page(catalog,READER_CATALOG_SHELF,id,NULL,NULL,0,1,50,receive_member,&p,NULL)==SQLITE_OK && !p.count);
  gid(9999,id);CHECK(reader_catalog_group_books_page(catalog,READER_CATALOG_SERIES,id,NULL,NULL,0,1,50,receive_member,&p,NULL)==SQLITE_OK && !p.count);
  PASS("deleted_and_empty_groups_publish_no_member_rows");
  gid(2202,id);bid(1,key);
  CHECK(reader_catalog_membership_find(catalog,READER_CATALOG_SHELF,id,key,receive_membership,&p,&found,NULL)==SQLITE_OK && found && p.deleted && !p.book_deleted && p.ordinal==7);
  gid(1,id);bid(2202,key);
  CHECK(reader_catalog_membership_find(catalog,READER_CATALOG_TAG,id,key,receive_membership,&p,&found,NULL)==SQLITE_OK && found && !p.deleted && p.book_deleted && !p.ordinal);
  bid(9999,key);CHECK(reader_catalog_membership_find(catalog,READER_CATALOG_TAG,id,key,receive_membership,&p,&found,NULL)==SQLITE_OK && !found);
  PASS("membership_lookup_exposes_deleted_dependencies_without_choosing_history");
  reader_catalog_group_cursor gc={UINT64_MAX,id};reader_catalog_member_cursor mc={UINT64_MAX,key};
  CHECK(reader_catalog_groups_page(catalog,READER_CATALOG_SHELF,NULL,&gc,1,20,receive_group,&p,NULL)==SQLITE_MISUSE);
  CHECK(reader_catalog_group_books_page(catalog,READER_CATALOG_SERIES,id,&mc,NULL,0,1,20,receive_member,&p,NULL)==SQLITE_MISUSE);
  PASS("cursor_integer_overflow_is_rejected_before_binding");
  CHECK(reader_catalog_groups_page(catalog,(reader_catalog_group_kind)3,NULL,NULL,1,20,receive_group,&p,NULL)==SQLITE_MISUSE);
  CHECK(reader_catalog_groups_page(catalog,READER_CATALOG_TAG,id,NULL,1,20,receive_group,&p,NULL)==SQLITE_MISUSE);
  CHECK(reader_catalog_groups_page(catalog,READER_CATALOG_SHELF,NULL,NULL,0,20,receive_group,&p,NULL)==SQLITE_MISUSE);
  CHECK(reader_catalog_group_books_page(catalog,READER_CATALOG_SHELF,id,NULL,"\xc0\x80",0,1,20,receive_member,&p,NULL)==SQLITE_MISUSE);
  CHECK(reader_catalog_group_books_page(catalog,READER_CATALOG_SHELF,id,NULL,NULL,0,1,201,receive_member,&p,NULL)==SQLITE_MISUSE);
  CHECK(reader_catalog_groups_page(catalog,READER_CATALOG_SERIES,NULL,NULL,1,0,receive_group,&p,NULL)==SQLITE_MISUSE);
  PASS("invalid_kind_parent_utf8_direction_and_limits_are_refused");
  memset(&p,0,sizeof(p));p.reenter=p.stop=1;p.direction=1;
  CHECK(reader_catalog_groups_page(catalog,READER_CATALOG_SHELF,NULL,NULL,1,20,receive_group,&p,NULL)==SQLITE_OK && p.count==1);
  memset(&p,0,sizeof(p));p.reenter=p.stop=1;p.direction=1;
  CHECK(reader_catalog_group_books_page(catalog,READER_CATALOG_SHELF,id,NULL,NULL,0,1,20,receive_member,&p,NULL)==SQLITE_OK && p.count==1);
  PASS("callback_stop_and_owner_reentry_follow_existing_catalog_contract");
#ifdef _WIN32
  HANDLE thread=CreateThread(NULL,0,wrong_owner,NULL,0,NULL);CHECK(thread!=NULL);CHECK(WaitForSingleObject(thread,INFINITE)==WAIT_OBJECT_0);CloseHandle(thread);
#else
  pthread_t thread;CHECK(pthread_create(&thread,NULL,wrong_owner,NULL)==0);CHECK(pthread_join(thread,NULL)==0);
#endif
  PASS("organization_reads_refuse_a_different_worker");
  plan(db,member_forward,"reader_book_series_page","(ordinal,book_key)>");plan(db,member_reverse,"reader_book_series_page","(ordinal,book_key)<");
  plan(db,group_forward,"reader_shelves_parent","(ordinal,shelf_id)>");plan(db,group_reverse,"reader_shelves_parent","(ordinal,shelf_id)<");
  PASS("actual_forward_reverse_queries_use_existing_index_ranges_without_offset");
  CHECK(writes==0);CHECK(reader_catalog_close(&catalog,NULL)==SQLITE_OK);CHECK(sqlite3_close(db)==SQLITE_OK);sqlite3_reset_auto_extension();
  PASS("all_organization_reads_execute_without_any_database_write");
  CHECK(groups==15);snprintf(path,sizeof(path),"%s/organization-result.json",argv[1]);FILE *report=fopen(path,"wb");CHECK(report);
  fprintf(report,"{\"accepted\":true,\"source_sha\":\"%s\",\"run_id\":\"%s\",\"attempt\":\"%s\",\"groups_per_kind\":2202,\"books\":2202,\"checks\":[",getenv("GITHUB_SHA"),getenv("GITHUB_RUN_ID"),getenv("GITHUB_RUN_ATTEMPT"));
  for(unsigned i=0;i<groups;i++) fprintf(report,"%s{\"id\":\"%s\",\"passed\":true}",i?",":"",names[i]);
  fprintf(report,"],\"sdk_changed\":false,\"schema_changed\":false,\"ui_accepted\":false,\"problems\":[]}\n");CHECK(!fclose(report));return 0;
}
