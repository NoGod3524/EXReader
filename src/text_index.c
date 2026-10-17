/* SPDX-License-Identifier: GPL-3.0-only */
#include "internal.h"
#include <sqlite3.h>
struct exr_text_index { sqlite3 *db; unsigned refs,query,busy; };
struct exr_text_query {
  exr_text_index *index; sqlite3_stmt *statement; exr_control control;
  char *pattern; uint32_t *prefix; size_t size,at,matched,rows;
  const char *source,*part,*text; size_t text_size; unsigned row,eof,failed;
};
static exr_status db_error(exr_text_index *i,int code,exr_error *e) {
  return exr_fail(e,code==SQLITE_INTERRUPT ? EXR_CANCELLED : EXR_DATABASE,"%s",sqlite3_errmsg(i->db));
}
static int cancelled(void *context) { const exr_control *c=context; return c && c->cancelled && c->cancelled(c->context); }
static exr_status utf8(const void *text,size_t size,const exr_control *control,exr_error *e) {
  const char *s=text; size_t at=0,next=0; uint32_t cp;
  while(at<size) {
    if(at>=next) { exr_status status=exr_control_cancel(control,e); if(status!=EXR_OK) return status; next=at+4096; }
    if(!exr_next(s,size,&at,&cp)) return exr_fail(e,EXR_ENCODING,"Index text is not UTF-8");
  }
  return EXR_OK;
}
static exr_status name(const char *s,int empty,exr_error *e) {
  size_t n=0;
  if(!s || (!empty && !*s)) return exr_fail(e,EXR_ARGUMENT,"Missing index source/part ID");
  while(n<=4096 && s[n]) n++;
  if(n>4096) return exr_fail(e,EXR_LIMIT,"Index ID exceeds 4096 bytes");
  return utf8(s,n,NULL,e);
}
static int scalar(sqlite3 *db,const char *sql) {
  sqlite3_stmt *s=NULL; int value=-1;
  if(sqlite3_prepare_v2(db,sql,-1,&s,NULL)==SQLITE_OK && sqlite3_step(s)==SQLITE_ROW) value=sqlite3_column_int(s,0);
  sqlite3_finalize(s); return value;
}
int exr_text_index_available(void) { return sqlite3_compileoption_used("ENABLE_FTS5")!=0; }
void exr_text_index_close(exr_text_index *i) { if(i && !--i->refs) { sqlite3_close_v2(i->db); free(i); } }
exr_status exr_text_index_open(const char *path,exr_text_index **out,exr_error *e) {
  exr_text_index *i; int code,app,version,transaction=0; exr_status status;
  if(out) *out=NULL;
  if(!out || !path) return exr_fail(e,EXR_ARGUMENT,"Invalid text index open arguments");
  if(!exr_text_index_available()) return exr_fail(e,EXR_FORMAT,"Text index was disabled in this SDK build");
  i=calloc(1,sizeof(*i)); if(!i) return exr_fail(e,EXR_MEMORY,"Text index allocation failed"); i->refs=1;
  code=sqlite3_open_v2(path,&i->db,SQLITE_OPEN_READWRITE|SQLITE_OPEN_CREATE|SQLITE_OPEN_FULLMUTEX,NULL);
  if(code!=SQLITE_OK) { status=db_error(i,code,e); goto failed; }
  sqlite3_busy_timeout(i->db,3000); sqlite3_db_config(i->db,SQLITE_DBCONFIG_DEFENSIVE,1,NULL);
  code=sqlite3_exec(i->db,"PRAGMA foreign_keys=ON;PRAGMA trusted_schema=OFF;",NULL,NULL,NULL);
  if(code!=SQLITE_OK) { status=db_error(i,code,e); goto failed; }
  app=scalar(i->db,"PRAGMA application_id"); version=scalar(i->db,"PRAGMA user_version");
  if(app!=1163416137 || version!=1) {
    code=sqlite3_exec(i->db,"BEGIN IMMEDIATE",NULL,NULL,NULL); if(code!=SQLITE_OK) { status=db_error(i,code,e); goto failed; } transaction=1;
    app=scalar(i->db,"PRAGMA application_id"); version=scalar(i->db,"PRAGMA user_version");
    if(!app && !version && scalar(i->db,"SELECT count(*) FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'")==0) {
      code=sqlite3_exec(i->db,"CREATE TABLE text_items(id INTEGER PRIMARY KEY,source TEXT NOT NULL,part TEXT NOT NULL,body TEXT NOT NULL,has_zero INTEGER NOT NULL CHECK(has_zero IN(0,1)),UNIQUE(source,part));"
        "CREATE VIRTUAL TABLE text_fts USING fts5(body,content='text_items',content_rowid='id',tokenize='trigram case_sensitive 1');"
        "PRAGMA application_id=1163416137;PRAGMA user_version=1;",NULL,NULL,NULL);
      if(code!=SQLITE_OK) { status=db_error(i,code,e); goto failed; }
    } else if(app!=1163416137 || version!=1) { status=exr_fail(e,EXR_DATABASE,"Not an EXReader text index or unsupported schema"); goto failed; }
    code=sqlite3_exec(i->db,"COMMIT",NULL,NULL,NULL); if(code!=SQLITE_OK) { status=db_error(i,code,e); goto failed; } transaction=0;
  }
  code=sqlite3_exec(i->db,"PRAGMA journal_mode=WAL;",NULL,NULL,NULL);
  if(code!=SQLITE_OK) { status=db_error(i,code,e); goto failed; }
  *out=i; return exr_fail(e,EXR_OK,"");
failed:
  if(transaction) sqlite3_exec(i->db,"ROLLBACK",NULL,NULL,NULL);
  exr_text_index_close(i); return status;
}
static exr_status execute(exr_text_index *i,const char *sql,const char *source,const char *part,const void *text,size_t size,exr_error *e) {
  sqlite3_stmt *s=NULL; int code=sqlite3_prepare_v2(i->db,sql,-1,&s,NULL);
  if(code==SQLITE_OK) code=sqlite3_bind_text(s,1,source,-1,SQLITE_STATIC);
  if(code==SQLITE_OK) code=part ? sqlite3_bind_text(s,2,part,-1,SQLITE_STATIC) : sqlite3_bind_null(s,2);
  if(code==SQLITE_OK && sqlite3_bind_parameter_count(s)>2) {
    code=sqlite3_bind_text(s,3,text ? text : "",(int)size,SQLITE_STATIC);
    if(code==SQLITE_OK) code=sqlite3_bind_int(s,4,size && memchr(text,0,size)!=NULL);
  }
  if(code==SQLITE_OK) code=sqlite3_step(s);
  sqlite3_finalize(s); return code==SQLITE_DONE ? EXR_OK : db_error(i,code,e);
}
static exr_status transaction_end(exr_text_index *i,const exr_control *control,exr_status status,int transaction,exr_error *e) {
  if(status==EXR_OK) status=exr_control_cancel(control,e);
  if(status==EXR_OK) { int code=sqlite3_exec(i->db,"COMMIT",NULL,NULL,NULL); if(code==SQLITE_OK) transaction=0; else status=db_error(i,code,e); }
  sqlite3_progress_handler(i->db,0,NULL,NULL);
  if(transaction) sqlite3_exec(i->db,"ROLLBACK",NULL,NULL,NULL);
  i->busy=0; return status==EXR_OK ? exr_fail(e,EXR_OK,"") : status;
}
static exr_status change(exr_text_index *i,const char *source,const char *part,const void *text,size_t size,int remove,const exr_control *control,exr_error *e) {
  exr_status status; int code,transaction=0;
  if(!i || i->busy || i->query || (!text && size) || (!remove && !part)) return exr_fail(e,EXR_ARGUMENT,"Invalid or active text index write");
  status=name(source,0,e); if(status!=EXR_OK) return status;
  if(part) { status=name(part,1,e); if(status!=EXR_OK) return status; }
  if(size>=EXR_MAX_TEXT) return exr_fail(e,EXR_LIMIT,"Indexed part exceeds 64 MiB-1");
  i->busy=1; status=exr_control_cancel(control,e);
  if(status==EXR_OK && !remove) status=utf8(text,size,control,e);
  if(status!=EXR_OK) goto done;
  sqlite3_progress_handler(i->db,1000,cancelled,(void *)control);
  code=sqlite3_exec(i->db,"BEGIN IMMEDIATE",NULL,NULL,NULL); if(code!=SQLITE_OK) { status=db_error(i,code,e); goto done; } transaction=1;
  status=execute(i,"INSERT INTO text_fts(text_fts,rowid,body) SELECT 'delete',id,body FROM text_items WHERE source=?1 AND (?2 IS NULL OR part=?2)",source,part,NULL,0,e);
  if(status==EXR_OK) {
    status=remove ? execute(i,"DELETE FROM text_items WHERE source=?1 AND (?2 IS NULL OR part=?2)",source,part,NULL,0,e) :
      execute(i,"INSERT INTO text_items(source,part,body,has_zero) VALUES(?1,?2,?3,?4) ON CONFLICT(source,part) DO UPDATE SET body=excluded.body,has_zero=excluded.has_zero",source,part,text,size,e);
  }
  if(status==EXR_OK && !remove) status=execute(i,"INSERT INTO text_fts(rowid,body) SELECT id,body FROM text_items WHERE source=?1 AND part=?2",source,part,NULL,0,e);
done:
  return transaction_end(i,control,status,transaction,e);
}
exr_status exr_text_index_put(exr_text_index *i,const char *source,const char *part,const void *text,size_t size,const exr_control *control,exr_error *e) {
  return change(i,source,part,text,size,0,control,e);
}
exr_status exr_text_index_remove(exr_text_index *i,const char *source,const char *part,const exr_control *control,exr_error *e) {
  return change(i,source,part,NULL,0,1,control,e);
}
exr_status exr_text_index_replace(exr_text_index *i,const char *source,exr_text_part_fn provider,void *context,
                                     const exr_control *control,exr_error *e) {
  size_t at=0; int code,transaction=0; exr_status status;
  if(!i || !provider || i->busy || i->query) return exr_fail(e,EXR_ARGUMENT,"Invalid or active text source replacement");
  status=name(source,0,e); if(status!=EXR_OK) return status;
  i->busy=1; status=exr_control_cancel(control,e); if(status!=EXR_OK) goto done;
  sqlite3_progress_handler(i->db,1000,cancelled,(void *)control);
  code=sqlite3_exec(i->db,"BEGIN IMMEDIATE",NULL,NULL,NULL); if(code!=SQLITE_OK) { status=db_error(i,code,e); goto done; } transaction=1;
  status=execute(i,"INSERT INTO text_fts(text_fts,rowid,body) SELECT 'delete',id,body FROM text_items WHERE source=?1 AND (?2 IS NULL OR part=?2)",source,NULL,NULL,0,e);
  if(status==EXR_OK) status=execute(i,"DELETE FROM text_items WHERE source=?1 AND (?2 IS NULL OR part=?2)",source,NULL,NULL,0,e);
  if(status!=EXR_OK) goto done;
  for(;;at++) {
    exr_text_part part={0}; exr_error local={0}; int found=0;
    status=exr_control_poll(control,EXR_STAGE_READ,at,0,e); if(status!=EXR_OK) goto done;
    status=provider(context,at,&part,&found,&local);
    if(status!=EXR_OK || local.code!=EXR_OK) { status=exr_fail(e,status!=EXR_OK ? status : local.code,"%.255s",local.message[0] ? local.message : "Index text provider failed"); goto done; }
    if(found!=0 && found!=1) { status=exr_fail(e,EXR_ARGUMENT,"Index provider returned an invalid found flag"); goto done; }
    if(!found) break;
    if(at==100000 || part.size>=EXR_MAX_TEXT) { status=exr_fail(e,EXR_LIMIT,"Index source exceeds part/count limits"); goto done; }
    if(!part.text && part.size) { status=exr_fail(e,EXR_ARGUMENT,"Index provider returned missing text"); goto done; }
    status=name(part.id,1,e); if(status==EXR_OK) status=utf8(part.text,part.size,control,e); if(status!=EXR_OK) goto done;
    status=execute(i,"INSERT INTO text_items(source,part,body,has_zero) VALUES(?1,?2,?3,?4)",source,part.id,part.text,part.size,e);
    if(status!=EXR_OK && sqlite3_extended_errcode(i->db)==SQLITE_CONSTRAINT_UNIQUE) status=exr_fail(e,EXR_ARGUMENT,"Index provider returned duplicate part IDs");
    if(status!=EXR_OK) goto done;
    status=execute(i,"INSERT INTO text_fts(rowid,body) SELECT id,body FROM text_items WHERE source=?1 AND part=?2",source,part.id,NULL,0,e); if(status!=EXR_OK) goto done;
  }
  status=exr_control_poll(control,EXR_STAGE_READ,at,at,e);
done:
  return transaction_end(i,control,status,transaction,e);
}
void exr_text_query_free(exr_text_query *q) {
  if(!q) return;
  sqlite3_finalize(q->statement); if(q->index) { q->index->query=0; exr_text_index_close(q->index); }
  free(q->pattern); free(q->prefix); free(q);
}
exr_status exr_text_index_query(exr_text_index *i,const char *source,const void *query,size_t size,const exr_control *control,exr_text_query **out,exr_error *e) {
  exr_text_query *q=NULL; exr_buffer phrase={0}; size_t at=0,count=0,k; uint32_t cp; int code,trigram; exr_status status;
  const char *sql;
  if(out) *out=NULL;
  if(!i || !out || i->busy || i->query || !query || !size) return exr_fail(e,EXR_ARGUMENT,"Invalid or active text query");
  if(size>4096) return exr_fail(e,EXR_LIMIT,"Text query exceeds 4096 bytes");
  if(source) { status=name(source,0,e); if(status!=EXR_OK) return status; }
  i->busy=1; status=exr_control_cancel(control,e); if(status!=EXR_OK) goto done;
  while(at<size) { if(!exr_next(query,size,&at,&cp)) { status=exr_fail(e,EXR_ENCODING,"Text query is not UTF-8"); goto done; } count++; }
  trigram=count>=3 && !memchr(query,0,size);
  q=calloc(1,sizeof(*q)); if(!q) { status=exr_fail(e,EXR_MEMORY,"Text query allocation failed"); goto done; }
  q->pattern=exr_copy(query,size); q->size=size; if(control) q->control=*control;
  if(!q->pattern) { status=exr_fail(e,EXR_MEMORY,"Text query pattern allocation failed"); goto done; }
  status=exr_kmp_prefix(q->pattern,size,control,&q->prefix,e); if(status!=EXR_OK) goto done;
  if(trigram) {
    if(!exr_append(&phrase,"\"",1)) goto limit;
    for(k=0;k<size;k++) if((q->pattern[k]=='"' && !exr_append(&phrase,"\"",1)) || !exr_append(&phrase,q->pattern+k,1)) goto limit;
    if(!exr_append(&phrase,"\"",1)) goto limit;
    sql="SELECT source,part,body,has_zero FROM text_items WHERE (?2 IS NULL OR source=?2) AND (id IN(SELECT rowid FROM text_fts WHERE text_fts MATCH ?1) OR has_zero=1) ORDER BY id";
  } else sql="SELECT source,part,body,has_zero FROM text_items WHERE (?2 IS NULL OR source=?2) AND instr(CAST(body AS BLOB),CAST(?1 AS BLOB))>0 ORDER BY id";
  code=sqlite3_prepare_v2(i->db,sql,-1,&q->statement,NULL);
  if(code==SQLITE_OK) code=trigram ? sqlite3_bind_text(q->statement,1,phrase.data,(int)phrase.size,SQLITE_TRANSIENT) : sqlite3_bind_blob(q->statement,1,query,(int)size,SQLITE_TRANSIENT);
  if(code==SQLITE_OK) code=source ? sqlite3_bind_text(q->statement,2,source,-1,SQLITE_TRANSIENT) : sqlite3_bind_null(q->statement,2);
  if(code!=SQLITE_OK) { status=db_error(i,code,e); goto done; }
  q->index=i; i->refs++; i->query=1; *out=q; q=NULL; status=exr_fail(e,EXR_OK,""); goto done;
limit:
  status=exr_fail(e,EXR_LIMIT,"Text query phrase allocation failed");
done:
  free(phrase.data); exr_text_query_free(q); i->busy=0; return status;
}
static exr_status read_row(exr_text_query *q,exr_error *e) {
  sqlite3_stmt *s=q->statement; int a,b,n; exr_status status;
  if(sqlite3_column_type(s,0)!=SQLITE_TEXT || sqlite3_column_type(s,1)!=SQLITE_TEXT || sqlite3_column_type(s,2)!=SQLITE_TEXT || sqlite3_column_type(s,3)!=SQLITE_INTEGER) return exr_fail(e,EXR_DATABASE,"Invalid indexed row types");
  a=sqlite3_column_bytes(s,0); b=sqlite3_column_bytes(s,1); n=sqlite3_column_bytes(s,2);
  q->source=(const char *)sqlite3_column_text(s,0); q->part=(const char *)sqlite3_column_text(s,1); q->text=(const char *)sqlite3_column_text(s,2);
  if(a<=0 || a>4096 || b<0 || b>4096 || n<0 || (size_t)n>=EXR_MAX_TEXT || !q->source || !q->part || !q->text || memchr(q->source,0,(size_t)a) || memchr(q->part,0,(size_t)b)) return exr_fail(e,EXR_DATABASE,"Invalid indexed row lengths/IDs");
  status=utf8(q->source,(size_t)a,&q->control,e); if(status==EXR_OK) status=utf8(q->part,(size_t)b,&q->control,e); if(status==EXR_OK) status=utf8(q->text,(size_t)n,&q->control,e);
  if(status!=EXR_OK) return status==EXR_ENCODING ? exr_fail(e,EXR_DATABASE,"Invalid indexed UTF-8") : status;
  if(sqlite3_column_int(s,3)!=(memchr(q->text,0,(size_t)n)!=NULL)) return exr_fail(e,EXR_DATABASE,"Invalid indexed NUL marker");
  q->text_size=(size_t)n; q->at=q->matched=0; q->row=1; return EXR_OK;
}
exr_status exr_text_query_next(exr_text_query *q,exr_text_hit *out,int *found,exr_error *e) {
  exr_text_index *i; exr_status status=EXR_OK;
  if(out) *out=(exr_text_hit){NULL,NULL,NULL,0,SIZE_MAX,SIZE_MAX};
  if(found) *found=0;
  if(!q || !out || !found || q->failed || q->index->busy) return exr_fail(e,EXR_ARGUMENT,"Invalid or failed/reentrant text query");
  if(q->eof) return exr_fail(e,EXR_OK,"");
  i=q->index; i->busy=1; status=exr_control_cancel(&q->control,e); if(status!=EXR_OK) goto done;
  while(1) {
    if(!q->row) {
      int code; sqlite3_progress_handler(i->db,1000,cancelled,&q->control); code=sqlite3_step(q->statement); sqlite3_progress_handler(i->db,0,NULL,NULL);
      if(code==SQLITE_DONE) { q->eof=1; break; }
      if(code!=SQLITE_ROW) { status=db_error(i,code,e); goto done; }
      status=exr_control_poll(&q->control,EXR_STAGE_READ,++q->rows,0,e); if(status==EXR_OK) status=read_row(q,e); if(status!=EXR_OK) goto done;
    }
    while(q->at<q->text_size) {
      unsigned char c=(unsigned char)q->text[q->at++];
      if(!(q->at&4095)) { status=exr_control_cancel(&q->control,e); if(status!=EXR_OK) goto done; }
      while(q->matched && c!=(unsigned char)q->pattern[q->matched]) q->matched=q->prefix[q->matched-1];
      if(c==(unsigned char)q->pattern[q->matched]) q->matched++;
      if(q->matched==q->size) {
        *out=(exr_text_hit){q->source,q->part,q->text,q->text_size,q->at-q->size,q->at}; *found=1; q->matched=q->prefix[q->matched-1]; goto done;
      }
    }
    q->row=0;
  }
done:
  if(status!=EXR_OK) q->failed=1;
  i->busy=0; return status==EXR_OK ? exr_fail(e,EXR_OK,"") : status;
}
