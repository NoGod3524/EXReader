/* SPDX-License-Identifier: MIT
 * Actions-only qualification consumer. Never retires product evidence. */
#ifndef _WIN32
#define _POSIX_C_SOURCE 200809L
#endif
#include "lm.h"
#include "lm_mirror.h"
#include <exreader.h>
#include <sqlite3.h>
#include <errno.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#ifdef _WIN32
#include <windows.h>
#include <io.h>
#else
#include <fcntl.h>
#include <unistd.h>
#include <time.h>
#endif

#define LIMIT (64u*1024u*1024u)
static int failed, last_sqlite, sdk_status=-1, directory_sync;
static int source_retained_control, close_busy_control;
static const char *reason="none", *mode, *target, *root, *catalog, *nonce, *fault;
static char baseline[4096], intent[4096], decision[4096], clonepath[4096], mutexpath[4096], custody[4096];
static lm_mirror_file original, baseline_id, intent_id, catalog_id, mutex_id;
static const char *tables[]={"audio_marks","audio_resume","book_progress","books",
 "epub_bounded_books","epub_notes","epub_progress","exr_migration_ledger","fixed_notes","notes"};
static void reject(const char *why) { if(!failed) reason=why;failed=1; }
static int sqlok(sqlite3 *db,int rc,const char *why) {
  if(rc!=SQLITE_OK) { last_sqlite=db?sqlite3_extended_errcode(db):rc;reject(why);return 0; }return 1;
}
static int execsql(sqlite3 *db,const char *sql) { return sqlok(db,sqlite3_exec(db,sql,NULL,NULL,NULL),"sql-error"); }
static void append(lm_sb *b,const void *p,size_t n) {
  if(n>LIMIT||b->n>LIMIT-n){reject("manifest-budget");return;}
  lm_sb_add(b,p,n);if(b->oom)reject("allocation");
}
static void u64(lm_sb *b,uint64_t x) { unsigned char p[8];int i;for(i=0;i<8;i++)p[i]=(unsigned char)(x>>(8*i));append(b,p,8); }
static void frame(lm_sb *b,char tag,const void *p,size_t n) {
  if(n>LIMIT-9 || b->n>LIMIT-9-n) {reject("manifest-budget");return;}
  append(b,&tag,1);u64(b,n);if(n)append(b,p,n);
}
static int known(const char *s) { size_t i;for(i=0;i<sizeof(tables)/sizeof(*tables);i++)if(!strcmp(s,tables[i]))return 1;return 0; }
static int query(sqlite3 *db,lm_sb *b,const char *label,const char *sql) {
  sqlite3_stmt *s=NULL;int rc=SQLITE_DONE,n,i;
  if(!sql){reject("sql-allocation");return 0;}
  if(!sqlok(db,sqlite3_prepare_v2(db,sql,-1,&s,NULL),"prepare"))return 0;
  frame(b,'Q',label,strlen(label));n=sqlite3_column_count(s);u64(b,(uint64_t)n);
  while(!failed && (rc=sqlite3_step(s))==SQLITE_ROW) {
    append(b,"R",1);
    for(i=0;i<n;i++) {
      int type=sqlite3_column_type(s,i);unsigned char bytes[8];uint64_t bits;int j;
      if(type==SQLITE_NULL)frame(b,'N',NULL,0);
      else if(type==SQLITE_INTEGER || type==SQLITE_FLOAT) {
        if(type==SQLITE_INTEGER)bits=(uint64_t)sqlite3_column_int64(s,i);
        else { double d=sqlite3_column_double(s,i);if(!isfinite(d)){reject("nonfinite-real");break;}memcpy(&bits,&d,8); }
        for(j=0;j<8;j++)bytes[j]=(unsigned char)(bits>>(8*j));
        frame(b,type==SQLITE_INTEGER?'I':'F',bytes,8);
      } else if(type==SQLITE_TEXT) {
        const void *p=sqlite3_column_text(s,i);int sz=sqlite3_column_bytes(s,i);
        if(!p){reject("text-conversion");break;}frame(b,'T',p,(size_t)sz);
      } else if(type==SQLITE_BLOB) {
        const void *p=sqlite3_column_blob(s,i);int sz=sqlite3_column_bytes(s,i);
        if(sz && !p){reject("blob-read");break;}frame(b,'B',p,(size_t)sz);
      } else reject("unknown-storage-class");
    }
  }
  if(!failed && rc!=SQLITE_DONE)sqlok(db,rc,"step");
  if(!failed)append(b,"E",1);
  sqlok(db,sqlite3_finalize(s),"finalize");return !failed;
}
static int scalar(sqlite3 *db,const char *sql,int *value) {
  sqlite3_stmt *s=NULL;int rc;
  if(!sqlok(db,sqlite3_prepare_v2(db,sql,-1,&s,NULL),"scalar-prepare"))return 0;
  rc=sqlite3_step(s);
  if(rc!=SQLITE_ROW || sqlite3_column_type(s,0)!=SQLITE_INTEGER) {last_sqlite=sqlite3_extended_errcode(db);reject("scalar-value");}
  else {*value=sqlite3_column_int(s,0);rc=sqlite3_step(s);if(rc!=SQLITE_DONE)sqlok(db,rc,"scalar-tail");}
  sqlok(db,sqlite3_finalize(s),"scalar-finalize");return !failed;
}
static int configure(sqlite3 *db) {
  int value=-1;
  if(!sqlok(db,sqlite3_extended_result_codes(db,1),"extended-codes")||!sqlok(db,sqlite3_busy_timeout(db,0),"busy-timeout"))return 0;
  if(!sqlok(db,sqlite3_db_config(db,SQLITE_DBCONFIG_DEFENSIVE,1,&value),"defensive") || value!=1){reject("defensive-readback");return 0;}
  if(!sqlok(db,sqlite3_db_config(db,SQLITE_DBCONFIG_TRUSTED_SCHEMA,0,&value),"trusted-schema") || value!=0){reject("trusted-schema-readback");return 0;}
  if(!sqlite3_compileoption_used("OMIT_LOAD_EXTENSION") &&
     (!sqlok(db,sqlite3_db_config(db,SQLITE_DBCONFIG_ENABLE_LOAD_EXTENSION,0,&value),"extensions") || value!=0))return 0;
  if(!sqlok(db,sqlite3_db_config(db,SQLITE_DBCONFIG_NO_CKPT_ON_CLOSE,1,&value),"no-close-checkpoint") || value!=1)return 0;
  if(!execsql(db,"PRAGMA read_uncommitted=OFF;PRAGMA mmap_size=0;"))return 0;
  if(!scalar(db,"PRAGMA read_uncommitted",&value) || value!=0){reject("read-uncommitted");return 0;}
  /* Per-consumer mmap=0 makes the Windows native read-refusal observable.
     It does not configure the frozen SDK's private owner or claim all defaults. */
  if(!scalar(db,"PRAGMA mmap_size",&value) || value!=0){reject("mmap-control");return 0;}
  return 1;
}
static int open_db(const char *path,int write,sqlite3 **out) {
  int rc;if(!strncmp(path,"file:",5) || strchr(path,'?')){reject("uri-not-permitted");return 0;}
  rc=sqlite3_open_v2(path,out,(write?SQLITE_OPEN_READWRITE:SQLITE_OPEN_READONLY)|SQLITE_OPEN_PRIVATECACHE|SQLITE_OPEN_FULLMUTEX,NULL);
  return sqlok(*out,rc,"open") && configure(*out);
}
static int close_db(sqlite3 **db) {
  int rc;if(!*db)return 1;
  rc=sqlite3_close(*db);if(rc==SQLITE_OK){*db=NULL;return 1;}
  sqlok(*db,rc,"close-busy-or-error");return 0;
}
static int tx(sqlite3 *db,int write) {
  if(sqlite3_get_autocommit(db)!=0 || sqlite3_txn_state(db,"main")!=(write?SQLITE_TXN_WRITE:SQLITE_TXN_READ)) {reject("transaction-fence-lost");return 0;}
  return 1;
}
static int snapshot(const char *path,int hash,lm_mirror_file *f) {
  lm_err e={{0},{0}};
  if(!lm_mirror_snapshot(path,hash,LIMIT,f,NULL,NULL,&e)){reject("namespace-unreadable-or-special");return 0;}
  if(f->present) {
#ifndef _WIN32
    struct stat s;if(lstat(path,&s) || s.st_nlink!=1){reject("hardlink-or-stat");return 0;}
#else
    wchar_t w[4096];HANDLE h;BY_HANDLE_FILE_INFORMATION i;
    if(!MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,path,-1,w,4096)){reject("path-encoding");return 0;}
    h=CreateFileW(w,FILE_READ_ATTRIBUTES,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,NULL,OPEN_EXISTING,FILE_FLAG_OPEN_REPARSE_POINT,NULL);
    if(h==INVALID_HANDLE_VALUE){reject("identity-open");return 0;}
    if(!GetFileInformationByHandle(h,&i) || i.nNumberOfLinks!=1){CloseHandle(h);reject("hardlink-or-identity");return 0;}
    if(!CloseHandle(h)){reject("identity-close");return 0;}
#endif
  }
  return 1;
}
static int same(const char *path,const lm_mirror_file *old,int hash) {
  lm_mirror_file now;if(!snapshot(path,hash,&now))return 0;
  if(!lm_mirror_same_file(old,&now) || (hash&&!lm_mirror_same_bytes(old,&now))){reject("ownership-changed");return 0;}return 1;
}
static int namespace_check(void) {
  const char *paths[12];char journal[4096],wal[4096],shm[4096],mirror[4096];lm_mirror_file seen[12];int i,j;
  snprintf(journal,sizeof(journal),"%s-journal",target);snprintf(wal,sizeof(wal),"%s-wal",target);snprintf(shm,sizeof(shm),"%s-shm",target);
  snprintf(mirror,sizeof(mirror),"%s/simulated-mirror.txt",root);
  paths[0]=target;paths[1]=journal;paths[2]=wal;paths[3]=shm;paths[4]=baseline;paths[5]=intent;paths[6]=decision;paths[7]=clonepath;paths[8]=mutexpath;paths[9]=catalog;paths[10]=custody;paths[11]=mirror;
  for(i=0;i<12;i++) {
    if(!snapshot(paths[i],0,&seen[i]))return 0;
    for(j=0;j<i;j++)if(seen[i].present&&seen[j].present&&lm_mirror_same_file(&seen[i],&seen[j])){reject("path-alias");return 0;}
  }
  if(!seen[0].present){reject("target-absent");return 0;}return 1;
}
static int sync_parent(const char *path) {
#ifndef _WIN32
  char p[4096];char *slash;int fd,ok;
  snprintf(p,sizeof(p),"%s",path);slash=strrchr(p,'/');if(slash)*slash=0;else strcpy(p,".");
  fd=open(p,O_RDONLY);if(fd<0){reject("directory-open");return 0;}ok=fsync(fd)==0;if(close(fd))ok=0;
  if(!ok){reject("directory-sync");return 0;}directory_sync=1;
#else
  (void)path;directory_sync=0; /* No claim of durable directory ordering on Windows. */
#endif
  return 1;
}
static int write_new(const char *path,const void *data,size_t size) {
  FILE *f=lm_fopen(path,"wbx");int ok;if(!f){reject("exclusive-file-create");return 0;}
  ok=fwrite(data,1,size,f)==size && lm_sync(f);if(fclose(f))ok=0;
  if(!ok){reject("file-write-sync-close");return 0;}return sync_parent(path);
}
static int stage(const char *name) {
  char ready[4096],go[4096];int i;
  snprintf(ready,sizeof(ready),"%s/%s.ready",root,name);snprintf(go,sizeof(go),"%s/%s.go",root,name);
  if(!write_new(ready,name,strlen(name)))return 0;
  for(i=0;i<1500;i++) {
    if(lm_path_state(go)==1) {
      FILE *f=lm_fopen(go,"rb");char token[9]={0};size_t n=0;int closed=0;
      if(f){n=fread(token,1,8,f);closed=fclose(f)==0;}
      if(n==8&&closed&&!memcmp(token,"continue",8))return 1;
    }
#ifdef _WIN32
    Sleep(20);
#else
    struct timespec t={0,20000000};nanosleep(&t,NULL);
#endif
  }
  reject("rendezvous-timeout");return 0;
}
static int read_bytes(const char *path,char **p,size_t *n) {
  lm_mirror_file f;lm_err e={{0},{0}};
  if(!lm_mirror_snapshot(path,1,LIMIT,&f,p,n,&e)||!f.present){reject("evidence-read");return 0;}return 1;
}
static int catalog_bytes(sqlite3 *db,lm_sb *b) {
  return query(db,b,"catalog","SELECT type,name,tbl_name,sql FROM sqlite_schema ORDER BY type COLLATE BINARY,name COLLATE BINARY");
}
static int check_catalog(sqlite3 *db) {
  lm_sb b;char *expected=NULL;size_t n=0;sqlite3_stmt *s=NULL;int rc;
  lm_sb_init(&b);
  if(!catalog_bytes(db,&b)||!read_bytes(catalog,&expected,&n))goto done;
  if(n!=b.n||memcmp(expected,b.p,n)){reject("schema-catalog-mismatch");goto done;}
  if(!sqlok(db,sqlite3_prepare_v2(db,"SELECT type,name,sql FROM sqlite_schema",-1,&s,NULL),"schema-prepare"))goto done;
  while((rc=sqlite3_step(s))==SQLITE_ROW) {
    const char *type=(const char*)sqlite3_column_text(s,0),*name=(const char*)sqlite3_column_text(s,1),*sql=(const char*)sqlite3_column_text(s,2);
    if(!strcmp(type,"table") && (!known(name)||!sql||strstr(sql,"VIRTUAL")||strstr(sql,"WITHOUT ROWID")))reject("unsupported-table");
    if(strcmp(type,"table")&&strcmp(type,"index")&&strcmp(type,"trigger"))reject("unsupported-schema-object");
    if(!strcmp(type,"trigger")&&strcmp(name,"books_progress_changed"))reject("unsupported-trigger");
  }
  if(rc!=SQLITE_DONE)sqlok(db,rc,"schema-step");
done:
  if(s)sqlok(db,sqlite3_finalize(s),"schema-finalize");free(expected);lm_sb_free(&b);return !failed;
}
static int health(sqlite3 *db) {
  sqlite3_stmt *s=NULL;int rc;
  if(!sqlok(db,sqlite3_prepare_v2(db,"PRAGMA integrity_check",-1,&s,NULL),"integrity-prepare"))return 0;
  rc=sqlite3_step(s);if(rc!=SQLITE_ROW || sqlite3_column_type(s,0)!=SQLITE_TEXT || strcmp((const char*)sqlite3_column_text(s,0),"ok")) {
    if(rc!=SQLITE_ROW)sqlok(db,rc,"integrity-step");else reject("integrity");
  }
  if(!failed && sqlite3_step(s)!=SQLITE_DONE)reject("integrity-extra-result");sqlok(db,sqlite3_finalize(s),"integrity-finalize");s=NULL;
  if(!failed&&sqlok(db,sqlite3_prepare_v2(db,"PRAGMA foreign_key_check",-1,&s,NULL),"fk-prepare")) {
    rc=sqlite3_step(s);if(rc!=SQLITE_DONE){if(rc==SQLITE_ROW)reject("foreign-key");else sqlok(db,rc,"fk-step");}
    sqlok(db,sqlite3_finalize(s),"fk-finalize");
  }
  return !failed;
}
static int canonical(sqlite3 *db,lm_sb *b,int schema_check) {
  sqlite3_stmt *s=NULL;int rc;char *sql;int app=0,version=0;
  append(b,"EXRPF1\n",7);
  if(schema_check&&!check_catalog(db))return 0;
  if(!health(db)||!scalar(db,"PRAGMA application_id",&app)||!scalar(db,"PRAGMA user_version",&version))return 0;
  if(app!=1163416131 || (version!=6&&version!=7)){reject("unsupported-library");return 0;}
  query(db,b,"application_id","PRAGMA application_id");query(db,b,"user_version","PRAGMA user_version");query(db,b,"encoding","PRAGMA encoding");catalog_bytes(db,b);
  if(!sqlok(db,sqlite3_prepare_v2(db,"SELECT name FROM sqlite_schema WHERE type='table' ORDER BY name COLLATE BINARY",-1,&s,NULL),"table-list"))return 0;
  while(!failed&&(rc=sqlite3_step(s))==SQLITE_ROW) {
    const char *name=(const char*)sqlite3_column_text(s,0);char label[512];sqlite3_stmt *ix=NULL;int irc;
    if(!known(name)){reject("unsupported-table");break;}
    snprintf(label,sizeof(label),"xinfo:%s",name);sql=sqlite3_mprintf("PRAGMA table_xinfo(\"%w\")",name);query(db,b,label,sql);sqlite3_free(sql);
    snprintf(label,sizeof(label),"indexes:%s",name);sql=sqlite3_mprintf("PRAGMA index_list(\"%w\")",name);query(db,b,label,sql);sqlite3_free(sql);
    snprintf(label,sizeof(label),"fk:%s",name);sql=sqlite3_mprintf("PRAGMA foreign_key_list(\"%w\")",name);query(db,b,label,sql);sqlite3_free(sql);
    sql=sqlite3_mprintf("SELECT name FROM pragma_index_list(%Q) ORDER BY name COLLATE BINARY",name);
    if(sqlok(db,sqlite3_prepare_v2(db,sql,-1,&ix,NULL),"index-list")) {
      while(!failed&&(irc=sqlite3_step(ix))==SQLITE_ROW) {
        const char *iname=(const char*)sqlite3_column_text(ix,0);char *isql=sqlite3_mprintf("PRAGMA index_xinfo(\"%w\")",iname);
        snprintf(label,sizeof(label),"index-xinfo:%s",iname);query(db,b,label,isql);sqlite3_free(isql);
      }
      if(!failed&&irc!=SQLITE_DONE)sqlok(db,irc,"index-list-step");sqlok(db,sqlite3_finalize(ix),"index-list-finalize");
    }
    sqlite3_free(sql);
    snprintf(label,sizeof(label),"rows:%s",name);sql=sqlite3_mprintf("SELECT _rowid_,* FROM \"%w\" ORDER BY _rowid_",name);query(db,b,label,sql);sqlite3_free(sql);
  }
  if(!failed&&rc!=SQLITE_DONE)sqlok(db,rc,"tables-step");sqlok(db,sqlite3_finalize(s),"tables-finalize");return !failed;
}
static int backup_clone(sqlite3 *reader) {
  sqlite3 *dest=NULL;sqlite3_backup *b=NULL;int rc,fin;
  if(!write_new(clonepath,"",0)||!namespace_check()||!open_db(clonepath,1,&dest))goto done;
  b=sqlite3_backup_init(dest,"main",reader,"main");if(!b){sqlok(dest,sqlite3_errcode(dest),"backup-init");goto done;}
  rc=sqlite3_backup_step(b,-1);fin=sqlite3_backup_finish(b);b=NULL;
  if(rc!=SQLITE_DONE)sqlok(dest,rc,"backup-step");sqlok(dest,fin,"backup-finish");
done:
  if(b)sqlok(dest,sqlite3_backup_finish(b),"backup-cleanup");close_db(&dest);return !failed;
}
/* Public return-value transport, independently checked by the Python driver
   against its pre-owner snapshot before that driver permits baseline publish. */
static lm_sb projection;
static void pp(const char *s,size_t n) { if(!failed)append(&projection,s,n); }
static void ps(const char *s) {
  const unsigned char *at=(const unsigned char*)s;char escape[7];
  if(!s){pp("null",4);return;}pp("\"",1);
  for(;!failed&&*at;at++) {
    if(*at=='"'||*at=='\\'){pp("\\",1);pp((const char*)at,1);}
    else if(*at<0x20||*at==0x7f){snprintf(escape,sizeof(escape),"\\u%04x",*at);pp(escape,6);}
    else pp((const char*)at,1);
  }
  pp("\"",1);
}
static void pj(const char *s) { pp(",",1);ps(s); }
static void pi(int64_t n) { char b[48];int z=snprintf(b,sizeof(b),",%lld",(long long)n);if(z<0||(size_t)z>=sizeof(b))reject("projection-number");else pp(b,(size_t)z); }
static void px(uint64_t n) { char b[48];int z=snprintf(b,sizeof(b),",%llu",(unsigned long long)n);if(z<0||(size_t)z>=sizeof(b))reject("projection-number");else pp(b,(size_t)z); }
static void pu(size_t n) { if(n==SIZE_MAX)pi(-1);else px(n); }
static void pd(double n) { char b[64];int z;if(!isfinite(n)){reject("projection-nonfinite");return;}z=snprintf(b,sizeof(b),",%.17g",n);if(z<0||(size_t)z>=sizeof(b))reject("projection-number");else pp(b,(size_t)z); }
static void pb(const void *p,size_t n) {
  const unsigned char *bytes=p;const char hex[]="0123456789abcdef";size_t k;char pair[2];
  if(failed)return;
  if(projection.n>LIMIT-3||n>(LIMIT-3-projection.n)/2){reject("projection-hex-budget");return;}
  if(n&&!p){reject("projection-null-binary");return;}
  pp(",\"",2);for(k=0;k<n&&!failed;k++){pair[0]=hex[bytes[k]>>4];pair[1]=hex[bytes[k]&15];pp(pair,2);}pp("\"",1);
}
static void pr(const char *kind) { if(projection.n)pp("\n",1);pp("[",1);ps(kind); }
static void pe(void) { pp("]",1); }
static void pa(const exr_anchor *a) { pu(a->start);pu(a->end);pj(a->exact);pj(a->prefix);pj(a->suffix);pj(a->chapter); }
static void pl(const exr_epub_location *l) { pu(l->part);pj(l->path);pa(&l->selector); }
static void pc(const exr_audio_checkpoint *p) { pj(p->track_id);px(p->offset_ms);pd(p->rate); }
/* Public SDK traversal of the snapshot-bound clone. No original-target ordinary
 * SDK open. SQL canonical equality and independent Python typed oracle are
 * additional checks; SDK OK alone is never the logical comparator. */
static int sdk_clone_check(void) {
  exr_library *lib=NULL;exr_error e={0};exr_book *books=NULL;size_t count=0,i;exr_status status;
  lm_sb_init(&projection);
  status=exr_library_open(clonepath,&lib,&e);if(status!=EXR_OK){reject("clone-sdk-open");goto done;}
  status=exr_library_books(lib,NULL,&books,&count,&e);if(status!=EXR_OK){reject("clone-books");goto done;}
  for(i=0;i<count&&!failed;i++) {
    exr_source src={0};exr_note *notes=NULL;size_t n=0;void *blob=NULL;size_t size=0;unsigned char block[4096];size_t off=0;
    size_t j;char digest[65];
    pr("book");pi(books[i].id);pi(books[i].format);pj(books[i].title);pj(books[i].author);pj(books[i].tags);pi(books[i].favorite);pi(books[i].status);pu(books[i].position);pe();
    status=exr_library_blob(lib,books[i].id,0,&blob,&size,&e);if(status!=EXR_OK){reject("clone-original");break;}
    lm_sha_bytes(blob,size,digest);pr("source");pi(books[i].id);pu(size);pj(digest);pe();
    status=exr_library_source(lib,books[i].id,&src,&e);
    if(status!=EXR_OK){exr_free(blob);reject("clone-source");break;}
    if(src.size!=size)reject("clone-source-advertised-extent");
    while(!failed&&off<size) {size_t part=size-off;if(part>sizeof(block))part=sizeof(block);
      if(src.read_at(src.context,off,block,part)!=part||memcmp(block,(unsigned char*)blob+off,part)){reject("clone-source-parity");break;}off+=part;}
    src.release(src.context);exr_free(blob);
    blob=NULL;size=0;
    status=exr_library_blob(lib,books[i].id,1,&blob,&size,&e);if(status!=EXR_OK)reject("clone-cover");
    lm_sha_bytes(blob,size,digest);pr("cover");pi(books[i].id);pu(size);pj(digest);pe();exr_free(blob);
    status=exr_library_notes(lib,books[i].id,&notes,&n,&e);if(status!=EXR_OK)reject("clone-notes");
    for(j=0;j<n&&!failed;j++){pr("note");pi(notes[j].id);pi(notes[j].book_id);pu(notes[j].start);pu(notes[j].end);pj(notes[j].text);pa(&notes[j].anchor);pe();}exr_notes_free(notes,n);
    if(books[i].format==EXR_TXT || books[i].format==EXR_EPUB) {
      exr_anchor point={0};exr_anchor_state state;
      if(exr_library_progress_get(lib,books[i].id,&point,&state,&e)!=EXR_OK)reject("clone-progress");
      pr("progress");pi(books[i].id);pi(state);pa(&point);pe();exr_anchor_free(&point);
    }
    if(books[i].format==EXR_EPUB) {
      exr_library_epub_info info={0};exr_epub_note *en=NULL;size_t en_count=0;
      exr_epub_location loc={0};int present=0;info.struct_size=sizeof(info);
      if(exr_library_epub_info_get(lib,books[i].id,&info,&e)!=EXR_OK)reject("clone-epub-info");
      pr("epub-info");pi(books[i].id);pi(info.bounded_storage);pi(info.global_extent_known);pe();
      if(exr_library_epub_progress_get(lib,books[i].id,&loc,&present,&e)!=EXR_OK)reject("clone-epub-progress");
      pr("epub-progress");pi(books[i].id);pi(present);if(present)pl(&loc);pe();exr_epub_location_free(&loc);
      if(exr_library_epub_notes(lib,books[i].id,&en,&en_count,&e)!=EXR_OK)reject("clone-epub-notes");
      for(j=0;j<en_count&&!failed;j++){pr("epub-note");pi(en[j].id);pi(en[j].book_id);pl(&en[j].location);pj(en[j].text);pe();}exr_epub_notes_free(en,en_count);
      if(info.bounded_storage)reject("bounded-epub-public-traversal-not-qualified");
    }
    if(books[i].format==EXR_PDF || books[i].format==EXR_CBZ) {
      exr_fixed_note *fn=NULL;size_t fn_count=0;
      if(exr_library_fixed_notes(lib,books[i].id,&fn,&fn_count,&e)!=EXR_OK)reject("clone-fixed-notes");
      for(j=0;j<fn_count&&!failed;j++){exr_fixed_anchor *a=&fn[j].anchor;pr("fixed-note");pi(fn[j].id);pi(fn[j].book_id);pu(fn[j].page);pu(fn[j].start);pu(fn[j].end);pj(fn[j].text);pu(a->start);pu(a->end);pj(a->page_id);pb(a->exact,a->exact_size);pb(a->prefix,a->prefix_size);pb(a->suffix,a->suffix_size);pe();}exr_fixed_notes_free(fn,fn_count);
    }
    if(books[i].format==EXR_TXT || books[i].format==EXR_EPUB) {
      exr_document *doc=NULL;status=exr_library_document(lib,books[i].id,&doc,&e);
      if(status!=EXR_OK)reject("clone-reflow-invariant");if(doc)exr_document_free(doc);
    } else if(books[i].format==EXR_PDF || books[i].format==EXR_CBZ) {
      exr_fixed_document *doc=NULL;status=exr_library_fixed(lib,books[i].id,NULL,&doc,&e);
      if(status!=EXR_OK)reject("clone-fixed-invariant");if(doc)exr_fixed_free(doc);
    } else reject("clone-unsupported-format");
  }
  if(!failed) {
    sqlite3 *db=NULL;sqlite3_stmt *s=NULL;int rc=SQLITE_DONE;
    if(open_db(clonepath,0,&db)&&sqlok(db,sqlite3_prepare_v2(db,"SELECT audio_id FROM audio_resume UNION SELECT audio_id FROM audio_marks ORDER BY audio_id",-1,&s,NULL),"audio-keys")) {
      while(!failed&&(rc=sqlite3_step(s))==SQLITE_ROW) {
        const char *key=(const char*)sqlite3_column_text(s,0);exr_audio_checkpoint pos={0};exr_audio_bookmark *marks=NULL;size_t n=0,j;int present=0;
        if(exr_library_audio_resume_get(lib,key,&pos,&present,&e)!=EXR_OK)reject("clone-audio-resume");
        pr("audio-resume");pj(key);pi(present);if(present)pc(&pos);pe();exr_audio_checkpoint_free(&pos);
        if(exr_library_audio_bookmarks(lib,key,&marks,&n,&e)!=EXR_OK)reject("clone-audio-marks");
        for(j=0;j<n&&!failed;j++){pr("audio-mark");pj(key);pi(marks[j].id);pj(marks[j].label);pc(&marks[j].position);pe();}exr_audio_bookmarks_free(marks,n);
      }
      if(!failed&&rc!=SQLITE_DONE)sqlok(db,rc,"audio-key-step");sqlok(db,sqlite3_finalize(s),"audio-key-finalize");
    }
    close_db(&db);
  }
done:
  exr_books_free(books,count);if(lib)exr_library_close(lib);
  if(!failed){char path[4096];snprintf(path,sizeof(path),"%s/public-projection.jsonl",root);write_new(path,projection.p,projection.n);}
  lm_sb_free(&projection);return !failed;
}
static void identity_text(const lm_mirror_file *id,char *out,size_t cap) {
  snprintf(out,cap,"%s",id->identity);
}
static int evidence_intent(const lm_sb *bytes) {
  lm_sb b;char digest[65],id[128];lm_sha_bytes(bytes->p,bytes->n,digest);identity_text(&original,id,sizeof(id));
  lm_sb_init(&b);lm_sb_str(&b,"{\"format\":\"EXRPF1\",\"target_id\":");lm_sb_json(&b,id,strlen(id));
  lm_sb_str(&b,",\"nonce\":");lm_sb_json(&b,nonce,strlen(nonce));lm_sb_fmt(&b,",\"baseline_sha\":\"%s\",\"baseline_size\":%llu,\"catalog_sha\":\"%s\",\"baseline_id\":\"%s\",\"catalog_id\":\"%s\",\"mutex_id\":\"%s\",\"product_admission\":false}\n",digest,(unsigned long long)bytes->n,catalog_id.sha,baseline_id.identity,catalog_id.identity,mutex_id.identity);
  if(b.oom){reject("intent-allocation");lm_sb_free(&b);return 0;}
  if(!write_new(intent,b.p,b.n)){lm_sb_free(&b);return 0;}lm_sb_free(&b);
  if(!snapshot(intent,1,&intent_id))return 0;
  /* Test-owned custody witness is not a secret/MAC. Joint tampering is outside
     the explicitly trusted-directory experiment, never production authority. */
  lm_sb_init(&b);lm_sb_fmt(&b,"%s\n%s\n",intent_id.identity,intent_id.sha);
  if(b.oom){reject("custody-allocation");lm_sb_free(&b);return 0;}
  if(!write_new(custody,b.p,b.n)){lm_sb_free(&b);return 0;}lm_sb_free(&b);return 1;
}
static int capture(void) {
  exr_library *owner=NULL;exr_error e={0};sqlite3 *reader=NULL,*check=NULL;lm_sb b,other;int value=0;
  lm_sb_init(&b);lm_sb_init(&other);
  if(!namespace_check()||!snapshot(target,0,&original)||!snapshot(catalog,1,&catalog_id))goto done;
  if(!write_new(mutexpath,nonce,strlen(nonce))||!snapshot(mutexpath,1,&mutex_id))goto done;
  sdk_status=exr_library_migration_open(target,&owner,&e);if(sdk_status!=EXR_OK){reject("sdk-owner-open");goto done;}
  if(!stage("owner-held"))goto done;
  if(!strcmp(fault,"spill")) {
    char *large=malloc(16u*1024u*1024u);if(!large){reject("spill-allocation");goto done;}memset(large,'s',16u*1024u*1024u);
    sdk_status=exr_library_migration_ledger_set(owner,large,16u*1024u*1024u,&e);free(large);
    if(sdk_status!=EXR_OK){reject("spill-sdk-write");goto done;}
  }
  if(!open_db(target,0,&reader)||!execsql(reader,"BEGIN")||!scalar(reader,"PRAGMA user_version",&value)||!tx(reader,0))goto done;
  if(!strcmp(fault,"spill")){reject("spill-did-not-refuse-reader");goto done;}
  if(!canonical(reader,&b,1)||!tx(reader,0))goto done;
  if(!stage("reader-held")||!backup_clone(reader)||!tx(reader,0)||!same(target,&original,0))goto done;
  if(!stage("backup-closed"))goto done;
  if(!open_db(clonepath,0,&check)||!execsql(check,"BEGIN")||!canonical(check,&other,1))goto done;
  if(b.n!=other.n||memcmp(b.p,other.p,b.n)){reject("clone-baseline-mismatch");goto done;}
  if(!close_db(&check)||!close_db(&reader)||!stage("reader-closed"))goto done;
  if(!sdk_clone_check()||!stage("clone-sdk-closed")||!same(target,&original,0))goto done;
  if(!write_new(baseline,b.p,b.n)||!snapshot(baseline,1,&baseline_id)||!stage("baseline-durable"))goto done;
  if(!evidence_intent(&b)||!stage("intent-durable"))goto done;
  {
    char mirror[4096];static const char dirty[]="uncommitted preflight ledger, never a recovery certificate";
    snprintf(mirror,sizeof(mirror),"%s/simulated-mirror.txt",root);
    if(!write_new(mirror,nonce,strlen(nonce))||!stage("mirror-published"))goto done;
    sdk_status=exr_library_migration_ledger_set(owner,dirty,sizeof(dirty)-1,&e);
    if(sdk_status!=EXR_OK){reject("sdk-uncommitted-write");goto done;}
    if(!stage("mutation-held"))goto done;
    sdk_status=exr_library_migration_finish(owner,0,&e);
    if(sdk_status!=EXR_OK)reject("sdk-finish-non-ok");
    exr_library_close(owner);owner=NULL;
    if(!failed)stage("owner-finished");
  }
done:
  close_db(&check);close_db(&reader);
  if(owner){sdk_status=exr_library_migration_finish(owner,0,&e);exr_library_close(owner);owner=NULL;}
  lm_sb_free(&b);lm_sb_free(&other);return !failed;
}
static int interrupt_query(void *context) { sqlite3_interrupt((sqlite3*)context);return 0; }
static int verify(void) {
  sqlite3 *db=NULL;char *raw=NULL,*base=NULL,*witness=NULL;size_t n=0,size=0,wn=0;char error[128],digest[65],id[128],expected_witness[128];jv *v=NULL;const char *expected;uint64_t declared=0;lm_sb b,out;int matched=0;lm_mirror_file custody_id;
  lm_mirror_file decision_id,mirror_id;char mirror[4096];
  lm_sb_init(&b);lm_sb_init(&out);snprintf(mirror,sizeof(mirror),"%s/simulated-mirror.txt",root);
  if(!namespace_check()||!snapshot(target,0,&original)||!snapshot(intent,1,&intent_id)||!snapshot(baseline,1,&baseline_id)||!snapshot(catalog,1,&catalog_id)||!snapshot(mutexpath,1,&mutex_id))goto done;
  if(!intent_id.present||!baseline_id.present||!mutex_id.present){reject("missing-provenance");goto done;}
  if(!snapshot(mirror,1,&mirror_id))goto done;
  { char nonce_sha[65];lm_sha_bytes(nonce,strlen(nonce),nonce_sha);
    if(mutex_id.size!=strlen(nonce)||strcmp(nonce_sha,mutex_id.sha)){reject("mutex-nonce-mismatch");goto done;} }
  if(!snapshot(custody,1,&custody_id)||!read_bytes(custody,&witness,&wn))goto done;
  snprintf(expected_witness,sizeof(expected_witness),"%s\n%s\n",intent_id.identity,intent_id.sha);
  if(wn!=strlen(expected_witness)||memcmp(witness,expected_witness,wn)){reject("intent-custody-mismatch");goto done;}
  if(!read_bytes(intent,&raw,&n))goto done;v=lm_json_parse(raw,n,error,sizeof(error));
  if(!v||v->t!=J_OBJ||v->n!=10){reject("intent-format");goto done;}
  identity_text(&original,id,sizeof(id));
  if(!lm_get_str(v,"format")||strcmp(lm_get_str(v,"format"),"EXRPF1")||!lm_get_str(v,"target_id")||strcmp(lm_get_str(v,"target_id"),id)||!lm_get_str(v,"nonce")||strcmp(lm_get_str(v,"nonce"),nonce)||!lm_get_str(v,"catalog_sha")||strcmp(lm_get_str(v,"catalog_sha"),catalog_id.sha)){reject("intent-binding");goto done;}
  expected=lm_get_str(v,"baseline_sha");if(!expected||strcmp(expected,baseline_id.sha)||!lm_json_uint(lm_get(v,"baseline_size"),&declared)||declared!=baseline_id.size){reject("baseline-binding");goto done;}
  if(!lm_get_str(v,"baseline_id")||strcmp(lm_get_str(v,"baseline_id"),baseline_id.identity)||!lm_get_str(v,"catalog_id")||strcmp(lm_get_str(v,"catalog_id"),catalog_id.identity)||!lm_get_str(v,"mutex_id")||strcmp(lm_get_str(v,"mutex_id"),mutex_id.identity)||!lm_get(v,"product_admission")||lm_get(v,"product_admission")->t!=J_BOOL||lm_get(v,"product_admission")->b){reject("custody-binding");goto done;}
  if(!read_bytes(baseline,&base,&size)||!open_db(target,1,&db)||!execsql(db,"BEGIN IMMEDIATE")||!tx(db,1)||!stage("verify-held"))goto done;
  if(!strcmp(fault,"interrupt")) {
    /* Public progress callback requests a real SQLite interrupt during execution.
       No fabricated result: the actual sqlite3_exec status must latch refusal. */
    int rc;sqlite3_progress_handler(db,1,interrupt_query,db);
    rc=sqlite3_exec(db,"WITH RECURSIVE n(x) AS (VALUES(1) UNION ALL SELECT x+1 FROM n WHERE x<1000000) SELECT sum(x) FROM n",NULL,NULL,NULL);
    sqlite3_progress_handler(db,0,NULL,NULL);
    if(rc==SQLITE_OK)reject("interrupt-not-observed");else sqlok(db,rc,"actual-query-interrupt");
    goto done;
  }
  if(!canonical(db,&b,1)||!tx(db,1))goto done;
  if(size!=b.n||memcmp(base,b.p,size)){reject("baseline-parity-mismatch");goto done;}
  matched=1;if(!stage("compared")||!tx(db,1)||!same(target,&original,0)||!same(intent,&intent_id,1)||!same(baseline,&baseline_id,1)||!same(catalog,&catalog_id,1)||!same(mutexpath,&mutex_id,1)||!same(custody,&custody_id,1)||!same(mirror,&mirror_id,1)||!namespace_check())goto done;
  lm_sha_bytes(b.p,b.n,digest);
  lm_sb_fmt(&out,"{\"format\":\"EXRPF-decision1\",\"baseline_sha\":\"%s\",\"current_parity\":true,\"historical_outcome_proved\":false,\"product_admission\":false,\"nonce\":",digest);lm_sb_json(&out,nonce,strlen(nonce));lm_sb_str(&out,"}\n");
  if(out.oom){reject("decision-allocation");goto done;}
  if(lm_path_state(decision)==0) {if(!write_new(decision,out.p,out.n))goto done;}
  else {char *prior=NULL;size_t ps=0;if(!read_bytes(decision,&prior,&ps))goto done;if(ps!=out.n||memcmp(prior,out.p,ps))reject("foreign-decision");free(prior);if(failed)goto done;}
  if(!snapshot(decision,1,&decision_id)||!stage("decision-durable")||!tx(db,1)||!same(target,&original,0)||!same(intent,&intent_id,1)||!same(baseline,&baseline_id,1)||!same(catalog,&catalog_id,1)||!same(mutexpath,&mutex_id,1)||!same(custody,&custody_id,1)||!same(mirror,&mirror_id,1)||!same(decision,&decision_id,1)||!namespace_check())goto done;
done:
  if(db) { /* No DML: ending this reservation is not a dirty SDK rollback. */
    if(!failed)execsql(db,"COMMIT");
    close_db(&db);
  }
  free(raw);free(base);free(witness);lm_json_free(v);lm_sb_free(&b);lm_sb_free(&out);
  if(matched&&failed)fprintf(stderr,"parity was observed but qualification refused at %s; any decision remains provisional\n",reason);
  return !failed;
}
static int vectors(void) {
  sqlite3 *db=NULL;sqlite3_stmt *s=NULL;lm_sb b;unsigned char large[8193];int ok=0;
  lm_sb_init(&b);memset(large,0xa5,sizeof(large));large[4096]=0;
  if(!sqlok(NULL,sqlite3_open(":memory:",&db),"vector-open")||!execsql(db,"CREATE TABLE v(k,v);INSERT INTO v VALUES(NULL,NULL),(NULL,''),(NULL,x''),('nul','a'||char(0)||'b'),('blob',x'610062'),('number',42),('number',42.0)"))goto done;
  if(!sqlok(db,sqlite3_prepare_v2(db,"INSERT INTO v VALUES('large',?1)",-1,&s,NULL),"vector-prepare"))goto done;
  if(!sqlok(db,sqlite3_bind_blob(s,1,large,sizeof(large),SQLITE_STATIC),"vector-bind"))goto done;
  if(sqlite3_step(s)!=SQLITE_DONE){reject("vector-insert");goto done;}sqlok(db,sqlite3_finalize(s),"vector-finalize");s=NULL;
  if(!strcmp(fault,"rowid"))execsql(db,"UPDATE v SET rowid=20 WHERE rowid=1");
  if(!strcmp(fault,"type"))execsql(db,"UPDATE v SET v=42.0 WHERE rowid=6");
  if(!strcmp(fault,"cell"))execsql(db,"UPDATE v SET v=x'610063' WHERE rowid=5");
  if(query(db,&b,"vectors","SELECT rowid,k,v FROM v ORDER BY rowid"))ok=write_new(baseline,b.p,b.n);
done:
  if(s)sqlok(db,sqlite3_finalize(s),"vector-cleanup");close_db(&db);lm_sb_free(&b);return ok&&!failed;
}
static int lifecycle(void) {
  exr_library *owner=NULL;exr_error e={0};exr_source src={0};exr_book *books=NULL;size_t count=0;unsigned char byte;
  sqlite3 *db=NULL;sqlite3_stmt *s=NULL;int rc;
  if(exr_library_open(target,&owner,&e)!=EXR_OK){reject("lifecycle-sdk-open");goto done;}
  if(exr_library_books(owner,"",&books,&count,&e)!=EXR_OK||!count||exr_library_source(owner,books[0].id,&src,&e)!=EXR_OK){reject("lifecycle-source");goto done;}
  exr_library_close(owner);owner=NULL;
  source_retained_control=src.read_at(src.context,0,&byte,1)==1;
  if(!source_retained_control)reject("source-did-not-retain-owner");src.release(src.context);memset(&src,0,sizeof(src));
  if(!open_db(target,0,&db)||!execsql(db,"BEGIN")||!sqlok(db,sqlite3_prepare_v2(db,"SELECT * FROM books",-1,&s,NULL),"lifecycle-stmt"))goto done;
  rc=sqlite3_step(s);if(rc!=SQLITE_ROW){reject("lifecycle-row");goto done;}
  rc=sqlite3_close(db);close_busy_control=rc==SQLITE_BUSY;
  if(!close_busy_control){if(rc==SQLITE_OK){db=NULL;s=NULL;}reject("close-did-not-report-busy");goto done;}
done:
  if(s)sqlok(db,sqlite3_finalize(s),"lifecycle-finalize");close_db(&db);
  if(src.context)src.release(src.context);exr_books_free(books,count);if(owner)exr_library_close(owner);return !failed;
}
int main(int argc,char **argv) {
  int ok=0;sqlite3 *db=NULL;lm_sb bytes;
  if(!getenv("GITHUB_ACTIONS")||strcmp(getenv("GITHUB_ACTIONS"),"true"))return 2;
  if(argc!=8)return 2;
  mode=argv[1];target=argv[2];root=argv[3];catalog=argv[4];nonce=argv[5];fault=argv[6];
  if(strcmp(argv[7],"qualification-only"))return 2;
  if(SQLITE_VERSION_NUMBER!=3054000||sqlite3_libversion_number()!=3054000||strcmp(SQLITE_SOURCE_ID,sqlite3_sourceid()))return 2;
  snprintf(baseline,sizeof(baseline),"%s/baseline.bin",root);snprintf(intent,sizeof(intent),"%s/intent.json",root);snprintf(decision,sizeof(decision),"%s/decision.json",root);snprintf(clonepath,sizeof(clonepath),"%s/clone.sqlite",root);snprintf(mutexpath,sizeof(mutexpath),"%s/migration.mutex",root);
  snprintf(custody,sizeof(custody),"%s/custody.txt",root);
  lm_binary_stdout();
  if(!strcmp(mode,"capture"))ok=capture();
  else if(!strcmp(mode,"verify"))ok=verify();
  else if(!strcmp(mode,"vectors"))ok=vectors();
  else if(!strcmp(mode,"lifecycle"))ok=lifecycle();
  else if(!strcmp(mode,"writer")) {
    if(open_db(target,1,&db)&&execsql(db,"BEGIN IMMEDIATE")){ok=1;execsql(db,"ROLLBACK");}close_db(&db);
  } else if(!strcmp(mode,"scan")) {
    lm_sb_init(&bytes);if(namespace_check()&&open_db(target,0,&db)&&execsql(db,"BEGIN")&&canonical(db,&bytes,1)&&tx(db,0))ok=write_new(baseline,bytes.p,bytes.n);close_db(&db);lm_sb_free(&bytes);
  } else reject("unknown-mode");
  printf("{\"mode\":\"%s\",\"passed\":%s,\"reason\":\"%s\",\"sqlite_extended_code\":%d,\"sdk_status\":%d,\"directory_sync\":%s,\"source_retained_control\":%s,\"close_busy_control\":%s,\"physical_cleanup_verified\":false,\"product_admission\":false,\"historical_outcome_proved\":false,\"sqlite_version\":\"%s\"}\n",mode,ok&&!failed?"true":"false",reason,last_sqlite,sdk_status,directory_sync?"true":"false",source_retained_control?"true":"false",close_busy_control?"true":"false",sqlite3_libversion());
  return ok&&!failed?0:3;
}
