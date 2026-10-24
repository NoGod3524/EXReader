/* SPDX-License-Identifier: MIT */
#include "catalog.h"
#include "catalog_migration.h"
#include <sqlite3.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
typedef DWORD catalog_thread;
static catalog_thread current_thread(void) { return GetCurrentThreadId(); }
static int same_thread(catalog_thread t) { return t == GetCurrentThreadId(); }
#else
#include <pthread.h>
typedef pthread_t catalog_thread;
static catalog_thread current_thread(void) { return pthread_self(); }
static int same_thread(catalog_thread t) { return pthread_equal(t, pthread_self()); }
#endif

struct reader_catalog { sqlite3 *database; catalog_thread owner; int active; };

static int fail(reader_catalog_error *e, int code, const char *message) {
  if(e) { e->code=code; snprintf(e->message,sizeof(e->message),"%s",message); }
  return code;
}
static int db_error(reader_catalog *c, int code, reader_catalog_error *e) {
  return fail(e,code,sqlite3_errmsg(c->database));
}
static int enter(reader_catalog *c, reader_catalog_error *e) {
  if(e) memset(e,0,sizeof(*e));
  if(!c || !same_thread(c->owner) || c->active)
    return fail(e,SQLITE_MISUSE,"Catalog requires its creating worker without reentry");
  c->active=1; return SQLITE_OK;
}
static int execute(reader_catalog *c,const char *sql,reader_catalog_error *e) {
  int status=sqlite3_exec(c->database,sql,NULL,NULL,NULL);
  return status==SQLITE_OK ? SQLITE_OK:db_error(c,status,e);
}
static int prepare(reader_catalog *c,const char *sql,sqlite3_stmt **out,reader_catalog_error *e) {
  int status=sqlite3_prepare_v2(c->database,sql,-1,out,NULL);
  return status==SQLITE_OK ? SQLITE_OK:db_error(c,status,e);
}
static int scalar(reader_catalog *c,const char *sql,int64_t *out,reader_catalog_error *e) {
  sqlite3_stmt *statement=NULL; int status=prepare(c,sql,&statement,e);
  if(status==SQLITE_OK) {
    status=sqlite3_step(statement);
    if(status==SQLITE_ROW && sqlite3_column_type(statement,0)==SQLITE_INTEGER) {
      *out=sqlite3_column_int64(statement,0); status=SQLITE_OK;
    } else status=db_error(c,status==SQLITE_ROW?SQLITE_MISMATCH:status,e);
  }
  sqlite3_finalize(statement); return status;
}
static int done(reader_catalog *c,sqlite3_stmt *s,reader_catalog_error *e) {
  int status=sqlite3_step(s);
  return status==SQLITE_DONE ? SQLITE_OK:db_error(c,status,e);
}
static int bind_text(reader_catalog *c,sqlite3_stmt *s,int index,const char *text,reader_catalog_error *e) {
  int status=sqlite3_bind_text(s,index,text,-1,SQLITE_TRANSIENT);
  return status==SQLITE_OK ? SQLITE_OK:db_error(c,status,e);
}
static int hex(const char *text,size_t size) {
  if(!text || strlen(text)!=size) return 0;
  for(size_t i=0;i<size;i++) if(!((text[i]>='0'&&text[i]<='9')||(text[i]>='a'&&text[i]<='f'))) return 0;
  return 1;
}
static int valid_text(const char *s) {
  size_t bytes=0,scalars=0;
  if(!s) return 0;
  /* Bound each read, including continuation bytes; SQLite's schema limits
   * characters while its bindings and the host allocate bytes. */
  while(bytes<16385 && s[bytes]) bytes++;
  if(bytes>16384) return 0;
  for(size_t i=0;i<bytes;) {
    unsigned char a=(unsigned char)s[i++]; unsigned value; size_t n;
    if(a<0x80) { value=a;n=0; }
    else if(a>=0xc2 && a<=0xdf) { value=a&31;n=1; }
    else if(a>=0xe0 && a<=0xef) { value=a&15;n=2; }
    else if(a>=0xf0 && a<=0xf4) { value=a&7;n=3; }
    else return 0;
    if(n>bytes-i) return 0;
    for(size_t j=0;j<n;j++) {
      unsigned char b=(unsigned char)s[i++]; if((b&0xc0)!=0x80) return 0;
      value=(value<<6)|(b&63);
    }
    if((n==1 && value<128)||(n==2 && value<2048)||(n==3 && value<65536)||
       value>0x10ffff||(value>=0xd800 && value<=0xdfff)||++scalars>4096) return 0;
  }
  return 1;
}
static int valid_format(const char *s) {
  static const char *const formats[]={"epub","pdf","cbz","txt","html","fb2","docx","rtf","mobi"};
  if(!s) return 0;
  for(size_t i=0;i<sizeof(formats)/sizeof(*formats);i++) if(!strcmp(s,formats[i])) return 1;
  return 0;
}

const char *reader_catalog_migration(size_t *bytes) {
  if(bytes) *bytes=sizeof(catalog_migration)-1;
  return catalog_migration;
}
int reader_catalog_open(const char *path,reader_catalog **out,reader_catalog_error *e) {
  reader_catalog *c; int status; int64_t identity=0,version=0,count=0,foreign_keys=0;
  if(e) memset(e,0,sizeof(*e));
  if(!out) return fail(e,SQLITE_MISUSE,"Missing catalog output");
  *out=NULL;
  if(!path || !*path) return fail(e,SQLITE_MISUSE,"Missing catalog path");
  c=calloc(1,sizeof(*c)); if(!c) return fail(e,SQLITE_NOMEM,"Catalog allocation failed");
  c->owner=current_thread();
  status=sqlite3_open_v2(path,&c->database,SQLITE_OPEN_READWRITE|SQLITE_OPEN_CREATE|SQLITE_OPEN_FULLMUTEX,NULL);
  if(status!=SQLITE_OK) { db_error(c,status,e);goto failed; }
  status=sqlite3_extended_result_codes(c->database,1);
  if(status==SQLITE_OK) status=sqlite3_busy_timeout(c->database,5000);
  if(status!=SQLITE_OK) { db_error(c,status,e);goto failed; }
  status=execute(c,"PRAGMA foreign_keys=ON; PRAGMA trusted_schema=OFF;",e);
  if(status==SQLITE_OK) status=scalar(c,"PRAGMA application_id",&identity,e);
  if(status==SQLITE_OK) status=scalar(c,"PRAGMA user_version",&version,e);
  if(status!=SQLITE_OK) goto failed;
  if(identity!=1163416144 || version!=1) {
    status=scalar(c,"SELECT count(*) FROM sqlite_master WHERE name NOT GLOB 'sqlite_*'",&count,e);
    if(status!=SQLITE_OK) goto failed;
    if(identity!=0 || version!=0 || count!=0) {
      status=fail(e,SQLITE_NOTADB,"Foreign or unsupported product catalog identity/version");goto failed;
    }
    status=execute(c,catalog_migration,e);
    if(status!=SQLITE_OK) goto failed;
  }
  status=scalar(c,"PRAGMA application_id",&identity,e);
  if(status==SQLITE_OK) status=scalar(c,"PRAGMA user_version",&version,e);
  if(status==SQLITE_OK) status=scalar(c,"PRAGMA foreign_keys",&foreign_keys,e);
  if(status!=SQLITE_OK) goto failed;
  if(identity!=1163416144 || version!=1 || foreign_keys!=1) {
    status=fail(e,SQLITE_NOTADB,"Product catalog contract was not established");goto failed;
  }
  *out=c;return SQLITE_OK;
failed:
  if(c->database) { sqlite3_exec(c->database,"ROLLBACK",NULL,NULL,NULL);sqlite3_close_v2(c->database); }
  free(c);return status;
}
int reader_catalog_close(reader_catalog **catalog,reader_catalog_error *e) {
  int status; reader_catalog *c;
  if(e) memset(e,0,sizeof(*e));
  if(!catalog) return fail(e,SQLITE_MISUSE,"Missing catalog handle");
  c=*catalog; if(!c) return SQLITE_OK;
  status=enter(c,e);if(status!=SQLITE_OK) return status;
  status=sqlite3_close(c->database);
  if(status!=SQLITE_OK) { c->active=0;return db_error(c,status,e); }
  free(c);*catalog=NULL;return SQLITE_OK;
}

int reader_catalog_attach(reader_catalog *c,const reader_catalog_book *b,reader_catalog_error *e) {
  sqlite3_stmt *s=NULL; char key[72]; int exists=0,mapped=0,status=enter(c,e);int64_t old_id=0;
  if(status!=SQLITE_OK) return status;
  if(!b || !valid_format(b->format)||!hex(b->sha256,64)||!valid_text(b->title)||
     !valid_text(b->author)||!valid_text(b->sort_title)||b->sdk_book_id<=0||b->source_bytes==0||
     b->source_bytes>INT64_MAX||(b->favorite!=0 && b->favorite!=1)||!b->location_kind||
     (strcmp(b->location_kind,"epub_chapter") && strcmp(b->location_kind,"reflow_global") &&
      strcmp(b->location_kind,"fixed_page"))) {
    status=fail(e,SQLITE_MISUSE,"Invalid verified product source metadata");goto leave;
  }
  snprintf(key,sizeof(key),"%s:%s",b->format,b->sha256);
  status=execute(c,"BEGIN IMMEDIATE",e);if(status!=SQLITE_OK) goto leave;
  status=prepare(c,"SELECT format,source_sha256,source_bytes FROM reader_books WHERE book_key=?",&s,e);
  if(status==SQLITE_OK) status=bind_text(c,s,1,key,e);
  if(status!=SQLITE_OK) goto rollback;
  status=sqlite3_step(s);
  if(status==SQLITE_ROW) {
    exists=1;
    if(strcmp((const char *)sqlite3_column_text(s,0),b->format)||
       strcmp((const char *)sqlite3_column_text(s,1),b->sha256)||
       sqlite3_column_int64(s,2)!=(int64_t)b->source_bytes) {
      status=fail(e,SQLITE_CONSTRAINT,"Product original identity conflicts with SDK bytes");goto rollback;
    }
  } else if(status!=SQLITE_DONE) { status=db_error(c,status,e);goto rollback; }
  sqlite3_finalize(s);s=NULL;
  if(!exists) {
    status=prepare(c,"INSERT INTO reader_books(book_key,format,source_sha256,source_bytes,title,author,sort_title,favorite) VALUES(?,?,?,?,?,?,?,?)",&s,e);
    const char *values[]={key,b->format,b->sha256,b->title,b->author,b->sort_title};
    const int indexes[]={1,2,3,5,6,7};
    for(size_t i=0;status==SQLITE_OK && i<6;i++) status=bind_text(c,s,indexes[i],values[i],e);
    if(status==SQLITE_OK) status=sqlite3_bind_int64(s,4,(int64_t)b->source_bytes);
    if(status==SQLITE_OK) status=sqlite3_bind_int(s,8,b->favorite);
    if(status==SQLITE_OK) status=done(c,s,e);
    if(status!=SQLITE_OK) goto rollback;
    sqlite3_finalize(s);s=NULL;
  }
  status=prepare(c,"SELECT book_key,location_kind FROM reader_local_books WHERE sdk_book_id=?",&s,e);
  if(status==SQLITE_OK) status=sqlite3_bind_int64(s,1,b->sdk_book_id);
  if(status!=SQLITE_OK) goto rollback;
  status=sqlite3_step(s);
  if(status==SQLITE_ROW) {
    mapped=1;
    if(strcmp((const char *)sqlite3_column_text(s,0),key)||
       strcmp((const char *)sqlite3_column_text(s,1),b->location_kind)) {
      status=fail(e,SQLITE_CONSTRAINT,"SDK ID already maps to another original or storage mode");goto rollback;
    }
  } else if(status!=SQLITE_DONE) { status=db_error(c,status,e);goto rollback; }
  sqlite3_finalize(s);s=NULL;
  if(!mapped) {
    status=prepare(c,"SELECT sdk_book_id FROM reader_local_books WHERE book_key=?",&s,e);
    if(status==SQLITE_OK) status=bind_text(c,s,1,key,e);
    if(status!=SQLITE_OK) goto rollback;
    status=sqlite3_step(s);
    if(status==SQLITE_ROW) old_id=sqlite3_column_int64(s,0);
    else if(status!=SQLITE_DONE) { status=db_error(c,status,e);goto rollback; }
    sqlite3_finalize(s);s=NULL;
    if(old_id==0 || b->sdk_book_id<old_id) {
      const char *sql=old_id==0 ? "INSERT INTO reader_local_books(sdk_book_id,location_kind,book_key) VALUES(?,?,?)":
        "UPDATE reader_local_books SET sdk_book_id=?,location_kind=? WHERE book_key=?";
      status=prepare(c,sql,&s,e);
      if(status==SQLITE_OK) status=sqlite3_bind_int64(s,1,b->sdk_book_id);
      if(status==SQLITE_OK) status=bind_text(c,s,2,b->location_kind,e);
      if(status==SQLITE_OK) status=bind_text(c,s,3,key,e);
      if(status==SQLITE_OK) status=done(c,s,e);
      if(status!=SQLITE_OK) goto rollback;
      sqlite3_finalize(s);s=NULL;
    }
  }
  status=execute(c,"COMMIT",e);
  if(status==SQLITE_OK) goto leave;
rollback:
  sqlite3_finalize(s);s=NULL;
  sqlite3_exec(c->database,"ROLLBACK",NULL,NULL,NULL);
leave:
  sqlite3_finalize(s);c->active=0;return status;
}
int reader_catalog_has_local(reader_catalog *c,int64_t id,int *present,reader_catalog_error *e) {
  sqlite3_stmt *s=NULL;int status=enter(c,e);
  if(status!=SQLITE_OK) return status;
  if(!present || id<=0) { status=fail(e,SQLITE_MISUSE,"Invalid local mapping query");goto leave; }
  *present=0;status=prepare(c,"SELECT 1 FROM reader_local_books WHERE sdk_book_id=?",&s,e);
  if(status==SQLITE_OK) status=sqlite3_bind_int64(s,1,id);
  if(status==SQLITE_OK) {
    status=sqlite3_step(s);
    if(status==SQLITE_ROW) { *present=1;status=SQLITE_OK; }
    else if(status==SQLITE_DONE) status=SQLITE_OK;
    else status=db_error(c,status,e);
  }
leave:
  sqlite3_finalize(s);c->active=0;return status;
}
int reader_catalog_remove_local(reader_catalog *c,int64_t id,reader_catalog_error *e) {
  sqlite3_stmt *s=NULL;int status=enter(c,e);
  if(status!=SQLITE_OK) return status;
  if(id<=0) { status=fail(e,SQLITE_MISUSE,"Invalid local SDK ID");goto leave; }
  status=prepare(c,"DELETE FROM reader_local_books WHERE sdk_book_id=?",&s,e);
  if(status==SQLITE_OK) status=sqlite3_bind_int64(s,1,id);
  if(status==SQLITE_OK) status=done(c,s,e);
leave:
  sqlite3_finalize(s);c->active=0;return status;
}
int reader_catalog_page(reader_catalog *c,const char *title,const char *key,size_t limit,
                        reader_catalog_visit visit,void *context,reader_catalog_error *e) {
  sqlite3_stmt *s=NULL;int status=enter(c,e);
  if(status!=SQLITE_OK) return status;
  if(!visit || limit==0 || limit>200 || (!!title!=!!key) ||
     (title && (!valid_text(title)||!valid_text(key)))) {
    status=fail(e,SQLITE_MISUSE,"Invalid bounded catalog page/cursor");goto leave;
  }
  /* Separate the first page so the continuation has an actual index range,
   * rather than an OR predicate that scans past all preceding titles. */
  const char *sql=title ?
    "SELECT b.book_key,b.title,b.format,b.sort_title,b.source_bytes,b.favorite,l.sdk_book_id,l.location_kind FROM reader_books b LEFT JOIN reader_local_books l ON l.book_key=b.book_key WHERE b.deleted=0 AND (b.sort_title,b.book_key)>(?1,?2) ORDER BY b.sort_title,b.book_key LIMIT ?3":
    "SELECT b.book_key,b.title,b.format,b.sort_title,b.source_bytes,b.favorite,l.sdk_book_id,l.location_kind FROM reader_books b LEFT JOIN reader_local_books l ON l.book_key=b.book_key WHERE b.deleted=0 ORDER BY b.sort_title,b.book_key LIMIT ?3";
  status=prepare(c,sql,&s,e);
  if(status==SQLITE_OK && title) status=bind_text(c,s,1,title,e);
  if(status==SQLITE_OK && key) status=bind_text(c,s,2,key,e);
  if(status==SQLITE_OK) status=sqlite3_bind_int(s,3,(int)limit);
  if(status!=SQLITE_OK) goto leave;
  while((status=sqlite3_step(s))==SQLITE_ROW) {
    reader_catalog_row row;
    row.book_key=(const char *)sqlite3_column_text(s,0);row.title=(const char *)sqlite3_column_text(s,1);
    row.format=(const char *)sqlite3_column_text(s,2);row.sort_title=(const char *)sqlite3_column_text(s,3);
    row.source_bytes=(uint64_t)sqlite3_column_int64(s,4);row.favorite=sqlite3_column_int(s,5);
    row.sdk_book_id=sqlite3_column_type(s,6)==SQLITE_NULL ? 0:sqlite3_column_int64(s,6);
    row.location_kind=(const char *)sqlite3_column_text(s,7);
    if(!row.book_key||!row.title||!row.format||!row.sort_title) {
      status=fail(e,SQLITE_CORRUPT,"Catalog row lacks required text");goto leave;
    }
    if(visit(context,&row)) { status=SQLITE_DONE;break; }
  }
  if(status==SQLITE_DONE) status=SQLITE_OK;else status=db_error(c,status,e);
leave:
  sqlite3_finalize(s);c->active=0;return status;
}
