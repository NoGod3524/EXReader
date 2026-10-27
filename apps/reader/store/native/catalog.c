/* SPDX-License-Identifier: MIT */
#include "catalog.h"
#include "catalog_migration.h"
#include "originals_migration.h"
#include "staging_migration.h"
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
  if(identity!=1163416144 || (version!=1 && version!=2 && version!=3)) {
    status=scalar(c,"SELECT count(*) FROM sqlite_master WHERE name NOT GLOB 'sqlite_*'",&count,e);
    if(status!=SQLITE_OK) goto failed;
    if(identity!=0 || version!=0 || count!=0) {
      status=fail(e,SQLITE_NOTADB,"Foreign or unsupported product catalog identity/version");goto failed;
    }
    status=execute(c,catalog_migration,e);
    if(status!=SQLITE_OK) goto failed;
  }
  status=scalar(c,"PRAGMA user_version",&version,e);
  if(status==SQLITE_OK && version==1) status=execute(c,originals_migration,e);
  if(status==SQLITE_OK) status=scalar(c,"PRAGMA user_version",&version,e);
  if(status==SQLITE_OK && version==2) status=execute(c,staging_migration,e);
  if(status==SQLITE_OK) status=scalar(c,"PRAGMA application_id",&identity,e);
  if(status==SQLITE_OK) status=scalar(c,"PRAGMA user_version",&version,e);
  if(status==SQLITE_OK) status=scalar(c,"PRAGMA foreign_keys",&foreign_keys,e);
  if(status!=SQLITE_OK) goto failed;
  if(identity!=1163416144 || version!=3 || foreign_keys!=1) {
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

#ifdef _WIN32
static int local_fixed_catalog(sqlite3 *db) {
  const char *path=sqlite3_db_filename(db,"main");
  wchar_t *wide=NULL,*resolved=NULL,volume[MAX_PATH];HANDLE file=INVALID_HANDLE_VALUE;int local=0;
  if(!path) return 0;
  int n=MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,path,-1,NULL,0);
  if(n<=0) return 0;
  wide=malloc((size_t)n*sizeof(*wide));resolved=malloc(32768*sizeof(*resolved));
  if(!wide || !resolved || !MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,path,-1,wide,n)) goto done;
  file=CreateFileW(wide,0,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,NULL,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,NULL);
  if(file==INVALID_HANDLE_VALUE) goto done;
  DWORD length=GetFinalPathNameByHandleW(file,resolved,32768,FILE_NAME_NORMALIZED|VOLUME_NAME_DOS);
  if(length==0 || length>=32768 || !GetVolumePathNameW(resolved,volume,MAX_PATH)) goto done;
  local=GetDriveTypeW(volume)==DRIVE_FIXED;
done:
  if(file!=INVALID_HANDLE_VALUE) CloseHandle(file);
  free(wide);free(resolved);return local;
}
void reader_catalog_prepare_repair(reader_catalog *c) {
  sqlite3_stmt *s=NULL;
  if(enter(c,NULL)!=SQLITE_OK) return;
  /* SQLite WAL requires shared memory on the local host. Unknown and remote
   * volumes keep the original rollback journal. */
  if(!local_fixed_catalog(c->database)) { c->active=0;return; }
  /* Preserve non-default modes and fall back immediately if another worker
   * holds a lock. Durability and the per-book transaction remain unchanged. */
  sqlite3_busy_timeout(c->database,0);
  if(sqlite3_prepare_v2(c->database,"PRAGMA journal_mode",-1,&s,NULL)==SQLITE_OK &&
     sqlite3_step(s)==SQLITE_ROW) {
    const char *mode=(const char *)sqlite3_column_text(s,0);
    int is_delete=mode && !strcmp(mode,"delete");
    sqlite3_finalize(s);s=NULL;
    if(is_delete) sqlite3_exec(c->database,"PRAGMA journal_mode=WAL",NULL,NULL,NULL);
  }
  sqlite3_finalize(s);
  sqlite3_busy_timeout(c->database,5000);
  c->active=0;
}
#endif

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
static int read_book_row(sqlite3_stmt *s,reader_catalog_row *row,reader_catalog_error *e) {
    row->book_key=(const char *)sqlite3_column_text(s,0);row->title=(const char *)sqlite3_column_text(s,1);
    row->format=(const char *)sqlite3_column_text(s,2);row->sort_title=(const char *)sqlite3_column_text(s,3);
    row->source_bytes=(uint64_t)sqlite3_column_int64(s,4);row->favorite=sqlite3_column_int(s,5);
    row->sdk_book_id=sqlite3_column_type(s,6)==SQLITE_NULL ? 0:sqlite3_column_int64(s,6);
    row->location_kind=(const char *)sqlite3_column_text(s,7);
    row->author=(const char *)sqlite3_column_text(s,8);
    row->deleted=0; /* Organization pages only deliver active books. */
    if(!row->book_key||!row->title||!row->format||!row->sort_title||!row->author)
      return fail(e,SQLITE_CORRUPT,"Catalog row lacks required text");
    return SQLITE_OK;
}
static int deliver_rows(reader_catalog *c,sqlite3_stmt *s,reader_catalog_visit visit,
                         void *context,size_t *count,reader_catalog_error *e) {
  int status;if(count) *count=0;
  while((status=sqlite3_step(s))==SQLITE_ROW) {
    reader_catalog_row row;
    if(read_book_row(s,&row,e)!=SQLITE_OK) return SQLITE_CORRUPT;
    row.deleted=sqlite3_column_int(s,9);
    if(count) (*count)++;
    if(visit(context,&row)) { status=SQLITE_DONE;break; }
  }
  return status==SQLITE_DONE ? SQLITE_OK:db_error(c,status,e);
}
static int query_page(reader_catalog *c,const char *title,const char *key,
                              const char *query,const char *alternate,int direction,int inclusive,int local,size_t limit,
                              reader_catalog_visit visit,void *context,reader_catalog_error *e) {
  sqlite3_stmt *s=NULL;int status=enter(c,e);char sql[1024];
  if(status!=SQLITE_OK) return status;
  if(!visit || limit==0 || limit>200 || (direction!=1 && direction!=-1) || (!!title!=!!key) ||
     (title && (!valid_text(title)||!valid_text(key))) || (query && !valid_text(query)) || (alternate && !valid_text(alternate))) {
    status=fail(e,SQLITE_MISUSE,"Invalid bounded catalog query/cursor");goto leave;
  }
  const char *range=!title ? "":direction>0 ?
    inclusive ? " AND (b.sort_title,b.book_key)>=(?1,?2)":" AND (b.sort_title,b.book_key)>(?1,?2)":" AND (b.sort_title,b.book_key)<(?1,?2)";
  const char *filter=query && query[0] ? (alternate ?
    " AND (instr(lower(b.sort_title),lower(?4))>0 OR instr(lower(b.author),lower(?4))>0 OR instr(lower(b.author),lower(?5))>0)":
    " AND (instr(lower(b.title),lower(?4))>0 OR instr(lower(b.author),lower(?4))>0)"):"";
  const char *order=direction>0 ? " ORDER BY b.sort_title,b.book_key":" ORDER BY b.sort_title DESC,b.book_key DESC";
  /* Only constant SQL fragments are interpolated. User strings stay bound.
     Separate first/continuation plans preserve the actual index range. */
  snprintf(sql,sizeof(sql),"SELECT b.book_key,b.title,b.format,b.sort_title,b.source_bytes,b.favorite,l.sdk_book_id,l.location_kind,b.author,b.deleted FROM reader_books b LEFT JOIN reader_local_books l ON l.book_key=b.book_key WHERE b.deleted=0%s%s%s%s LIMIT ?3",local ? " AND (l.sdk_book_id IS NOT NULL OR EXISTS (SELECT 1 FROM reader_originals o WHERE o.book_key=b.book_key AND o.state='ready'))":"",range,filter,order);
  status=prepare(c,sql,&s,e);
  if(status==SQLITE_OK && title) status=bind_text(c,s,1,title,e);
  if(status==SQLITE_OK && key) status=bind_text(c,s,2,key,e);
  if(status==SQLITE_OK) status=sqlite3_bind_int(s,3,(int)limit);
  if(status==SQLITE_OK && query && query[0]) status=bind_text(c,s,4,query,e);
  if(status==SQLITE_OK && query && query[0] && alternate) status=bind_text(c,s,5,alternate,e);
  if(status==SQLITE_OK) status=deliver_rows(c,s,visit,context,NULL,e);
leave:
  sqlite3_finalize(s);c->active=0;return status;
}
int reader_catalog_query_page(reader_catalog *c,const char *title,const char *key,const char *query,int direction,size_t limit,
                              reader_catalog_visit visit,void *context,reader_catalog_error *e) {
  return query_page(c,title,key,query,NULL,direction,0,0,limit,visit,context,e);
}
int reader_catalog_local_page(reader_catalog *c,const char *title,const char *key,const char *query,int direction,size_t limit,
                              reader_catalog_visit visit,void *context,reader_catalog_error *e) {
  return query_page(c,title,key,query,NULL,direction,0,1,limit,visit,context,e);
}
int reader_catalog_local_canonical_page(reader_catalog *c,const char *title,const char *key,const char *nfc,const char *nfd,
    int direction,int inclusive,size_t limit,reader_catalog_visit visit,void *context,reader_catalog_error *e) {
  if(!nfc||!nfd||(inclusive!=0&&inclusive!=1))return fail(e,SQLITE_MISUSE,"Missing canonical local shelf query");
  return query_page(c,title,key,nfc,nfd,direction,inclusive,1,limit,visit,context,e);
}
int reader_catalog_page(reader_catalog *c,const char *title,const char *key,size_t limit,
                        reader_catalog_visit visit,void *context,reader_catalog_error *e) {
  return reader_catalog_query_page(c,title,key,NULL,1,limit,visit,context,e);
}
static int catalog_find(reader_catalog *c,const char *key,const char *query,int local,
                        reader_catalog_visit visit,void *context,int *found,reader_catalog_error *e) {
  sqlite3_stmt *s=NULL;size_t count=0;int status=enter(c,e);char sql[1024];
  if(found) *found=0;
  if(status!=SQLITE_OK) return status;
  if(!found || !visit || !valid_text(key) || !key[0] || (query && !valid_text(query))) {
    status=fail(e,SQLITE_MISUSE,"Invalid stable catalog key/filter");goto leave;
  }
  const char *filter=query && query[0] ?
    " AND (instr(lower(b.title),lower(?2))>0 OR instr(lower(b.author),lower(?2))>0)":"";
  snprintf(sql,sizeof(sql),"SELECT b.book_key,b.title,b.format,b.sort_title,b.source_bytes,b.favorite,l.sdk_book_id,l.location_kind,b.author,b.deleted FROM reader_books b LEFT JOIN reader_local_books l ON l.book_key=b.book_key WHERE b.deleted=0 AND b.book_key=?1%s%s LIMIT 1",local ? " AND (l.sdk_book_id IS NOT NULL OR EXISTS (SELECT 1 FROM reader_originals o WHERE o.book_key=b.book_key AND o.state='ready'))":"",filter);
  status=prepare(c,sql,&s,e);
  if(status==SQLITE_OK) status=bind_text(c,s,1,key,e);
  if(status==SQLITE_OK && query && query[0]) status=bind_text(c,s,2,query,e);
  if(status==SQLITE_OK) status=deliver_rows(c,s,visit,context,&count,e);
  if(status==SQLITE_OK) *found=count!=0;
leave:
  sqlite3_finalize(s);c->active=0;return status;
}

typedef struct {
  const char *table,*id,*members,*index;
  int ordered_group,ordered_member;
} group_table;
static const group_table *group_for(reader_catalog_group_kind kind) {
  static const group_table tables[]={
    {"reader_shelves","shelf_id","reader_book_shelves","reader_book_shelves_page",1,1},
    {"reader_tags","tag_id","reader_book_tags","reader_book_tags_tag",0,0},
    {"reader_series","series_id","reader_book_series","reader_book_series_page",0,1}
  };
  return (unsigned)kind<=READER_CATALOG_SERIES ? &tables[(unsigned)kind]:NULL;
}
static int deliver_groups(reader_catalog *c,sqlite3_stmt *s,reader_catalog_group_visit visit,
                           void *context,int *found,reader_catalog_error *e) {
  int status;
  while((status=sqlite3_step(s))==SQLITE_ROW) {
    reader_catalog_group_row row;
    row.id=(const char *)sqlite3_column_text(s,0);row.name=(const char *)sqlite3_column_text(s,1);
    row.parent_id=(const char *)sqlite3_column_text(s,2);
    row.ordinal=(uint64_t)sqlite3_column_int64(s,3);row.deleted=sqlite3_column_int(s,4);
    if(!row.id || !row.name) return fail(e,SQLITE_CORRUPT,"Catalog group lacks required text");
    if(found) *found=1;
    if(visit(context,&row)) { status=SQLITE_DONE;break; }
  }
  return status==SQLITE_DONE ? SQLITE_OK:db_error(c,status,e);
}
int reader_catalog_group_find(reader_catalog *c,reader_catalog_group_kind kind,const char *id,
  reader_catalog_group_visit visit,void *context,int *found,reader_catalog_error *e) {
  sqlite3_stmt *s=NULL;char sql[512];const group_table *g=group_for(kind);int status=enter(c,e);
  if(found) *found=0;
  if(status!=SQLITE_OK) return status;
  if(!g || !hex(id,32) || !visit || !found) {
    status=fail(e,SQLITE_MISUSE,"Invalid group lookup");goto leave;
  }
  snprintf(sql,sizeof(sql),"SELECT g.%s,g.name,%s,%s,g.deleted FROM %s g WHERE g.%s=?1 LIMIT 1",
    g->id,g->ordered_group?"g.parent_id":"NULL",g->ordered_group?"g.ordinal":"0",g->table,g->id);
  status=prepare(c,sql,&s,e);
  if(status==SQLITE_OK) status=bind_text(c,s,1,id,e);
  if(status==SQLITE_OK) status=deliver_groups(c,s,visit,context,found,e);
leave:
  sqlite3_finalize(s);c->active=0;return status;
}
int reader_catalog_groups_page(reader_catalog *c,reader_catalog_group_kind kind,const char *parent,
  const reader_catalog_group_cursor *cursor,int direction,size_t limit,
  reader_catalog_group_visit visit,void *context,reader_catalog_error *e) {
  sqlite3_stmt *s=NULL;char sql[1024],range[128],order[128];
  const group_table *g=group_for(kind);int status=enter(c,e);
  if(status!=SQLITE_OK) return status;
  if(!g || !visit || !limit || limit>200 || (direction!=1 && direction!=-1) ||
     (parent && (!g->ordered_group || !hex(parent,32))) ||
     (cursor && (!hex(cursor->id,32) || cursor->ordinal>INT64_MAX || (!g->ordered_group && cursor->ordinal)))) {
    status=fail(e,SQLITE_MISUSE,"Invalid bounded group cursor");goto leave;
  }
  const char *compare=direction>0?">":"<",*descending=direction>0?"":" DESC";
  range[0]=0;
  if(cursor) {
    if(g->ordered_group) snprintf(range,sizeof(range)," AND (g.ordinal,g.%s)%s(?2,?3)",g->id,compare);
    else snprintf(range,sizeof(range)," AND g.%s%s?3",g->id,compare);
  }
  if(g->ordered_group) snprintf(order,sizeof(order),"g.ordinal%s,g.%s%s",descending,g->id,descending);
  else snprintf(order,sizeof(order),"g.%s%s",g->id,descending);
  snprintf(sql,sizeof(sql),"SELECT g.%s,g.name,%s,%s,g.deleted FROM %s g WHERE g.deleted=0%s%s ORDER BY %s LIMIT ?4",
    g->id,g->ordered_group?"g.parent_id":"NULL",g->ordered_group?"g.ordinal":"0",g->table,
    g->ordered_group?" AND g.parent_id IS ?1":"",range,order);
  status=prepare(c,sql,&s,e);
  if(status==SQLITE_OK && g->ordered_group) status=bind_text(c,s,1,parent,e);
  if(status==SQLITE_OK && cursor && g->ordered_group) status=sqlite3_bind_int64(s,2,(sqlite3_int64)cursor->ordinal);
  if(status==SQLITE_OK && cursor) status=bind_text(c,s,3,cursor->id,e);
  if(status==SQLITE_OK) status=sqlite3_bind_int(s,4,(int)limit);
  if(status==SQLITE_OK) status=deliver_groups(c,s,visit,context,NULL,e);
leave:
  sqlite3_finalize(s);c->active=0;return status;
}
int reader_catalog_removed_groups_page(reader_catalog *c,reader_catalog_group_kind kind,
  const char *cursor,int direction,size_t limit,reader_catalog_group_visit visit,
  void *context,reader_catalog_error *e) {
  sqlite3_stmt *s=NULL;char sql[640],range[96];const group_table *g=group_for(kind);
  int status=enter(c,e);
  if(status!=SQLITE_OK) return status;
  if(!g || !visit || !limit || limit>200 || (direction!=1 && direction!=-1) ||
     (cursor && !hex(cursor,32))) {
    status=fail(e,SQLITE_MISUSE,"Invalid removed group cursor");goto leave;
  }
  range[0]=0;
  if(cursor) snprintf(range,sizeof(range)," AND g.%s%s?1",g->id,direction>0?">":"<");
  snprintf(sql,sizeof(sql),"SELECT g.%s,g.name,%s,%s,g.deleted FROM %s g WHERE g.deleted=1%s ORDER BY g.%s%s LIMIT ?2",
    g->id,g->ordered_group?"g.parent_id":"NULL",g->ordered_group?"g.ordinal":"0",g->table,
    range,g->id,direction>0?"":" DESC");
  status=prepare(c,sql,&s,e);
  if(status==SQLITE_OK && cursor) status=bind_text(c,s,1,cursor,e);
  if(status==SQLITE_OK) status=sqlite3_bind_int(s,2,(int)limit);
  if(status==SQLITE_OK) status=deliver_groups(c,s,visit,context,NULL,e);
leave:
  sqlite3_finalize(s);c->active=0;return status;
}
int reader_catalog_membership_find(reader_catalog *c,reader_catalog_group_kind kind,const char *id,
  const char *key,reader_catalog_membership_visit visit,void *context,int *found,reader_catalog_error *e) {
  sqlite3_stmt *s=NULL;char sql[768];const group_table *g=group_for(kind);int status=enter(c,e);
  if(found) *found=0;
  if(status!=SQLITE_OK) return status;
  if(!g || !hex(id,32) || !valid_text(key) || !key[0] || !visit || !found) {
    status=fail(e,SQLITE_MISUSE,"Invalid membership lookup");goto leave;
  }
  snprintf(sql,sizeof(sql),"SELECT m.%s,m.book_key,%s,g.deleted,b.deleted FROM %s m JOIN %s g ON g.%s=m.%s JOIN reader_books b ON b.book_key=m.book_key WHERE m.%s=?1 AND m.book_key=?2 LIMIT 1",
    g->id,g->ordered_member?"m.ordinal":"0",g->members,g->table,g->id,g->id,g->id);
  status=prepare(c,sql,&s,e);
  if(status==SQLITE_OK) status=bind_text(c,s,1,id,e);
  if(status==SQLITE_OK) status=bind_text(c,s,2,key,e);
  if(status==SQLITE_OK) {
    status=sqlite3_step(s);
    if(status==SQLITE_ROW) {
      reader_catalog_membership_row row;
      row.group_id=(const char *)sqlite3_column_text(s,0);row.book_key=(const char *)sqlite3_column_text(s,1);
      row.ordinal=(uint64_t)sqlite3_column_int64(s,2);
      row.group_deleted=sqlite3_column_int(s,3);row.book_deleted=sqlite3_column_int(s,4);
      if(!row.group_id || !row.book_key) status=fail(e,SQLITE_CORRUPT,"Membership lacks identity");
      else { *found=1;visit(context,&row);status=SQLITE_OK; }
    } else if(status==SQLITE_DONE) status=SQLITE_OK;
    else status=db_error(c,status,e);
  }
leave:
  sqlite3_finalize(s);c->active=0;return status;
}
int reader_catalog_find(reader_catalog *c,const char *key,const char *query,
                        reader_catalog_visit visit,void *context,int *found,reader_catalog_error *e) {
  return catalog_find(c,key,query,0,visit,context,found,e);
}
int reader_catalog_local_find(reader_catalog *c,const char *key,const char *query,
                        reader_catalog_visit visit,void *context,int *found,reader_catalog_error *e) {
  return catalog_find(c,key,query,1,visit,context,found,e);
}
int reader_catalog_group_books_page(reader_catalog *c,reader_catalog_group_kind kind,const char *id,
  const reader_catalog_member_cursor *cursor,const char *query,int local_only,int direction,size_t limit,
  reader_catalog_group_book_visit visit,void *context,reader_catalog_error *e) {
  sqlite3_stmt *s=NULL;char sql[1800],range[128],order[128];
  const group_table *g=group_for(kind);int status=enter(c,e);
  if(status!=SQLITE_OK) return status;
  if(!g || !hex(id,32) || !visit || !limit || limit>200 || (local_only!=0 && local_only!=1) ||
     (direction!=1 && direction!=-1) || (query && !valid_text(query)) ||
     (cursor && (!valid_text(cursor->book_key) || !cursor->book_key[0] || cursor->ordinal>INT64_MAX ||
                 (!g->ordered_member && cursor->ordinal)))) {
    status=fail(e,SQLITE_MISUSE,"Invalid bounded group membership query");goto leave;
  }
  const char *compare=direction>0?">":"<",*descending=direction>0?"":" DESC";
  range[0]=0;
  if(cursor) {
    if(g->ordered_member) snprintf(range,sizeof(range)," AND (m.ordinal,m.book_key)%s(?2,?3)",compare);
    else snprintf(range,sizeof(range)," AND m.book_key%s?3",compare);
  }
  if(g->ordered_member) snprintf(order,sizeof(order),"m.ordinal%s,m.book_key%s",descending,descending);
  else snprintf(order,sizeof(order),"m.book_key%s",descending);
  /* Identifiers are selected only from group_for's constants; all UI values bind.
   * Use the existing group/ordinal/key index, including during reverse paging. */
  snprintf(sql,sizeof(sql),"SELECT b.book_key,b.title,b.format,b.sort_title,b.source_bytes,b.favorite,l.sdk_book_id,l.location_kind,b.author,%s FROM %s m INDEXED BY %s JOIN %s g ON g.%s=m.%s JOIN reader_books b ON b.book_key=m.book_key LEFT JOIN reader_local_books l ON l.book_key=b.book_key WHERE m.%s=?1 AND g.deleted=0 AND b.deleted=0%s%s%s ORDER BY %s LIMIT ?4",
    g->ordered_member?"m.ordinal":"0",g->members,g->index,g->table,g->id,g->id,g->id,
    local_only?" AND (l.sdk_book_id IS NOT NULL OR EXISTS (SELECT 1 FROM reader_originals o WHERE o.book_key=b.book_key AND o.state='ready'))":"",range,
    query && query[0]?" AND (instr(lower(b.title),lower(?5))>0 OR instr(lower(b.author),lower(?5))>0)":"",order);
  status=prepare(c,sql,&s,e);
  if(status==SQLITE_OK) status=bind_text(c,s,1,id,e);
  if(status==SQLITE_OK && cursor && g->ordered_member) status=sqlite3_bind_int64(s,2,(sqlite3_int64)cursor->ordinal);
  if(status==SQLITE_OK && cursor) status=bind_text(c,s,3,cursor->book_key,e);
  if(status==SQLITE_OK) status=sqlite3_bind_int(s,4,(int)limit);
  if(status==SQLITE_OK && query && query[0]) status=bind_text(c,s,5,query,e);
  if(status!=SQLITE_OK) goto leave;
  while((status=sqlite3_step(s))==SQLITE_ROW) {
    reader_catalog_group_book_row row;
    if(read_book_row(s,&row.book,e)!=SQLITE_OK) { status=SQLITE_CORRUPT;goto leave; }
    row.ordinal=(uint64_t)sqlite3_column_int64(s,9);
    if(visit(context,&row)) { status=SQLITE_DONE;break; }
  }
  status=status==SQLITE_DONE?SQLITE_OK:db_error(c,status,e);
leave:
  sqlite3_finalize(s);c->active=0;return status;
}
static int lookup(reader_catalog *c,int mode,int64_t id,const char *value,
                  reader_catalog_visit visit,void *context,int *found,reader_catalog_error *e) {
  sqlite3_stmt *s=NULL;size_t count=0;int status=enter(c,e);char sql[1024];
  if(found)*found=0;
  if(status!=SQLITE_OK)return status;
  if(!found||!visit||(mode==0?id<=0:!valid_text(value))) {
    status=fail(e,SQLITE_MISUSE,"Invalid typed catalog lookup");goto leave;
  }
  const char *where=mode==0?"b.deleted=0 AND l.sdk_book_id=?1":mode==1?
    "b.deleted=0 AND l.sdk_book_id IS NOT NULL AND b.title=?1":"b.book_key=?1";
  snprintf(sql,sizeof(sql),"SELECT b.book_key,b.title,b.format,b.sort_title,b.source_bytes,b.favorite,l.sdk_book_id,l.location_kind,b.author,b.deleted FROM reader_books b LEFT JOIN reader_local_books l ON l.book_key=b.book_key WHERE %s ORDER BY b.sort_title,b.book_key LIMIT 1",where);
  status=prepare(c,sql,&s,e);
  if(status==SQLITE_OK)status=mode==0?sqlite3_bind_int64(s,1,id):bind_text(c,s,1,value,e);
  if(status==SQLITE_OK)status=deliver_rows(c,s,visit,context,&count,e);
  if(status==SQLITE_OK)*found=count!=0;
leave:
  sqlite3_finalize(s);c->active=0;return status;
}
int reader_catalog_local_lookup(reader_catalog *c,int64_t id,const char *title,
    reader_catalog_visit visit,void *context,int *found,reader_catalog_error *e) {
  if(id<0||(id>0&&title))return fail(e,SQLITE_MISUSE,"Ambiguous local catalog lookup");
  return lookup(c,id>0?0:1,id,title,visit,context,found,e);
}
int reader_catalog_metadata(reader_catalog *c,const char *key,
    reader_catalog_visit visit,void *context,int *found,reader_catalog_error *e) {
  return lookup(c,2,0,key,visit,context,found,e);
}

/* References use a deliberately portable subset; the host still must enforce
 * containment against symlinks and use durable filesystem operations. */
static int original_ref_valid(const char *p) {
  size_t n; const char *part;
  if(!p || !valid_text(p) || !(n=strlen(p)) || n>1024 || p[0]=='/' || p[n-1]=='/') return 0;
  part=p;
  for(const char *q=p;;q++) {
    if(*q=='\\' || *q==':' || ((unsigned char)*q<32 && *q)) return 0;
    if(*q=='/' || !*q) {
      size_t len=(size_t)(q-part);
      if(!len || (len==1 && part[0]=='.') || (len==2 && part[0]=='.' && part[1]=='.')) return 0;
      if(!*q) break;
      part=q+1;
    }
  }
  return 1;
}
int reader_catalog_original_stage(reader_catalog *c,const reader_catalog_book *b,const char *ref,reader_catalog_error *e) {
  sqlite3_stmt *s=NULL; char key[72]; int status=enter(c,e);
  if(status!=SQLITE_OK) return status;
  if(!b || !valid_format(b->format) || !hex(b->sha256,64) || !b->source_bytes || b->source_bytes>INT64_MAX ||
     !valid_text(b->title) || !valid_text(b->author) || !valid_text(b->sort_title) ||
     (b->favorite!=0 && b->favorite!=1) || !original_ref_valid(ref)) {
    status=fail(e,SQLITE_MISUSE,"Invalid product original metadata or reference"); goto leave_original_stage;
  }
  snprintf(key,sizeof(key),"%s:%s",b->format,b->sha256);
  status=execute(c,"BEGIN IMMEDIATE",e); if(status!=SQLITE_OK) goto leave_original_stage;
  status=prepare(c,"SELECT source_bytes FROM reader_books WHERE book_key=?",&s,e);
  if(status==SQLITE_OK) status=bind_text(c,s,1,key,e);
  if(status!=SQLITE_OK) goto rollback_original_stage;
  status=sqlite3_step(s);
  if(status==SQLITE_ROW) {
    if(sqlite3_column_int64(s,0)!=(int64_t)b->source_bytes) { status=fail(e,SQLITE_CONSTRAINT,"Original identity has conflicting size"); goto rollback_original_stage; }
    sqlite3_finalize(s); s=NULL;
  } else if(status==SQLITE_DONE) {
    sqlite3_finalize(s); s=NULL;
  } else { status=db_error(c,status,e); goto rollback_original_stage; }
  /* An existing reservation is not overwritten, even by the same key. */
  status=prepare(c,"INSERT INTO reader_originals(book_key,storage_ref,state) VALUES(?,?,'staged')",&s,e);
  if(status==SQLITE_OK) status=bind_text(c,s,1,key,e);
  if(status==SQLITE_OK) status=bind_text(c,s,2,ref,e);
  if(status==SQLITE_OK) status=done(c,s,e);
  if(status!=SQLITE_OK) goto rollback_original_stage;
  sqlite3_finalize(s); s=NULL;
  /* Retain metadata separately until publication; existing books remain intact. */
  status=prepare(c,"INSERT INTO reader_original_pending(book_key,format,source_sha256,source_bytes,title,author,sort_title,favorite) SELECT ?,?,?,?,?,?,?,? WHERE NOT EXISTS(SELECT 1 FROM reader_books WHERE book_key=?)",&s,e);
  const char *values[]={key,b->format,b->sha256,b->title,b->author,b->sort_title,key};
  const int indexes[]={1,2,3,5,6,7,9};
  for(size_t i=0;status==SQLITE_OK && i<7;i++) status=bind_text(c,s,indexes[i],values[i],e);
  if(status==SQLITE_OK) status=sqlite3_bind_int64(s,4,(int64_t)b->source_bytes);
  if(status==SQLITE_OK) status=sqlite3_bind_int(s,8,b->favorite);
  if(status==SQLITE_OK) status=done(c,s,e);
  if(status!=SQLITE_OK) goto rollback_original_stage;
  sqlite3_finalize(s); s=NULL;
  status=execute(c,"COMMIT",e); if(status==SQLITE_OK) goto leave_original_stage;
rollback_original_stage:
  sqlite3_finalize(s); s=NULL; sqlite3_exec(c->database,"ROLLBACK",NULL,NULL,NULL);
leave_original_stage:
  sqlite3_finalize(s); c->active=0; return status;
}
static int original_read(reader_catalog *c,const char *key,size_t limit,int find,reader_catalog_original_visit visit,void *ctx,int *found,reader_catalog_error *e) {
  sqlite3_stmt *s=NULL; int status=enter(c,e);
  if(status!=SQLITE_OK) return status;
  if(!visit || (find && (!key || !found)) || (key && (!valid_text(key) || strlen(key)>71)) || !limit || limit>200) {
    status=fail(e,SQLITE_MISUSE,"Invalid original query"); goto leave_original_read;
  }
  if(found) *found=0;
  status=prepare(c,find ? "SELECT book_key,storage_ref,state FROM reader_originals WHERE book_key=?1" :
    "SELECT book_key,storage_ref,state FROM reader_originals WHERE (?1 IS NULL OR book_key>?1) ORDER BY book_key LIMIT ?2",&s,e);
  if(status==SQLITE_OK && key) status=bind_text(c,s,1,key,e);
  if(status==SQLITE_OK && !find) status=sqlite3_bind_int(s,2,(int)limit);
  if(status!=SQLITE_OK) goto leave_original_read;
  while((status=sqlite3_step(s))==SQLITE_ROW) {
    reader_catalog_original_row row={(const char *)sqlite3_column_text(s,0),(const char *)sqlite3_column_text(s,1),(const char *)sqlite3_column_text(s,2)};
    if(found) *found=1;
    if(visit(ctx,&row)) { status=SQLITE_DONE; break; }
  }
  status=status==SQLITE_DONE ? SQLITE_OK:db_error(c,status,e);
leave_original_read:
  sqlite3_finalize(s); c->active=0; return status;
}
int reader_catalog_original_find(reader_catalog *c,const char *key,reader_catalog_original_visit visit,void *ctx,int *found,reader_catalog_error *e) {
  return original_read(c,key,1,1,visit,ctx,found,e);
}
int reader_catalog_original_page(reader_catalog *c,const char *key,size_t limit,reader_catalog_original_visit visit,void *ctx,reader_catalog_error *e) {
  return original_read(c,key,limit,0,visit,ctx,NULL,e);
}
int reader_catalog_original_transition(reader_catalog *c,const char *key,const char *expected,const char *next,reader_catalog_error *e) {
  sqlite3_stmt *s=NULL; int status=enter(c,e);
  if(status!=SQLITE_OK) return status;
  if(!key || !valid_text(key) || !expected || !next ||
     !((!strcmp(expected,"staged") && (!strcmp(next,"ready") || !strcmp(next,"deleting"))) ||
       (!strcmp(expected,"ready") && !strcmp(next,"deleting")))) {
    status=fail(e,SQLITE_MISUSE,"Invalid original state transition"); goto leave_original_transition;
  }
  status=execute(c,"BEGIN IMMEDIATE",e); if(status!=SQLITE_OK) goto leave_original_transition;
  status=prepare(c,"UPDATE reader_originals SET state=? WHERE book_key=? AND state=?",&s,e);
  if(status==SQLITE_OK) status=bind_text(c,s,1,next,e);
  if(status==SQLITE_OK) status=bind_text(c,s,2,key,e);
  if(status==SQLITE_OK) status=bind_text(c,s,3,expected,e);
  if(status==SQLITE_OK) status=done(c,s,e);
  if(status==SQLITE_OK && !sqlite3_changes(c->database)) status=fail(e,SQLITE_NOTFOUND,"Original state changed or missing");
  sqlite3_finalize(s); s=NULL;
  if(status!=SQLITE_OK) goto rollback_original_transition;
  if(!strcmp(next,"ready")) {
    /* A verified SDK attach may have won the race since staging. */
    status=prepare(c,"SELECT 1 FROM reader_original_pending p JOIN reader_books b ON b.book_key=p.book_key WHERE p.book_key=? AND p.source_bytes<>b.source_bytes",&s,e);
    if(status==SQLITE_OK) status=bind_text(c,s,1,key,e);
    if(status==SQLITE_OK) { int step=sqlite3_step(s); if(step==SQLITE_ROW) status=fail(e,SQLITE_CONSTRAINT,"Original identity has conflicting size"); else if(step!=SQLITE_DONE) status=db_error(c,step,e); }
    sqlite3_finalize(s); s=NULL;
    if(status!=SQLITE_OK) goto rollback_original_transition;
    status=prepare(c,"INSERT INTO reader_books(book_key,format,source_sha256,source_bytes,title,author,sort_title,favorite) SELECT p.book_key,p.format,p.source_sha256,p.source_bytes,p.title,p.author,p.sort_title,p.favorite FROM reader_original_pending p WHERE p.book_key=? AND NOT EXISTS(SELECT 1 FROM reader_books b WHERE b.book_key=p.book_key)",&s,e);
    if(status==SQLITE_OK) status=bind_text(c,s,1,key,e);
    if(status==SQLITE_OK) status=done(c,s,e);
    sqlite3_finalize(s); s=NULL;
    if(status!=SQLITE_OK) goto rollback_original_transition;
    status=prepare(c,"DELETE FROM reader_original_pending WHERE book_key=?",&s,e);
    if(status==SQLITE_OK) status=bind_text(c,s,1,key,e);
    if(status==SQLITE_OK) status=done(c,s,e);
    sqlite3_finalize(s); s=NULL;
    if(status!=SQLITE_OK) goto rollback_original_transition;
  }
  status=execute(c,"COMMIT",e); if(status==SQLITE_OK) goto leave_original_transition;
rollback_original_transition:
  sqlite3_finalize(s); s=NULL; sqlite3_exec(c->database,"ROLLBACK",NULL,NULL,NULL);
leave_original_transition:
  sqlite3_finalize(s); c->active=0; return status;
}
int reader_catalog_original_forget(reader_catalog *c,const char *key,reader_catalog_error *e) {
  sqlite3_stmt *s=NULL; int status=enter(c,e);
  if(status!=SQLITE_OK) return status;
  if(!key || !valid_text(key)) { status=fail(e,SQLITE_MISUSE,"Invalid original key"); goto leave_original_forget; }
  status=prepare(c,"DELETE FROM reader_originals WHERE book_key=? AND state='deleting'",&s,e);
  if(status==SQLITE_OK) status=bind_text(c,s,1,key,e);
  if(status==SQLITE_OK) status=done(c,s,e);
  if(status==SQLITE_OK && !sqlite3_changes(c->database)) status=fail(e,SQLITE_NOTFOUND,"Deleting original missing");
leave_original_forget:
  sqlite3_finalize(s); c->active=0; return status;
}
