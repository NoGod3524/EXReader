/* SPDX-License-Identifier: MIT
 * Private production recovery worker: target is READONLY; SDK opens only
 * exclusive private clones/profiles. No test source is included at build time. */
#ifndef _WIN32
#define _POSIX_C_SOURCE 200809L
#define _DARWIN_C_SOURCE 1
#endif
#include "lm.h"
#include "lm_mirror.h"
#include "lm_new_target.h"
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
#include <sys/resource.h>
#include <dirent.h>
#include <signal.h>
#endif

#define LIMIT (64u*1024u*1024u)
static int failed, last_sqlite, sdk_status=-1, directory_sync;
static int source_retained_control, close_busy_control;
static const char *font_path;
static char profilepath[4096];
static lm_sb expected_projection, expected_rows;
static int initial_version;
static unsigned backup_calls,backup_reserved;
static uint64_t explicit_output_bytes;
static unsigned explicit_output_files;
/* Clone main, WAL and rollback journal each have the process file cap.
 * Explicit evidence is a separate cumulative cap, including bounded EPUB
 * diagnostics. The profile is small fixed SDK DDL, not imported user data. */
#define WORKER_EXPLICIT_CAP (3ull*LIMIT)
static double started;
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
  sqlite3_limit(db,SQLITE_LIMIT_LENGTH,LIMIT);
  sqlite3_limit(db,SQLITE_LIMIT_SQL_LENGTH,1048576);
  sqlite3_limit(db,SQLITE_LIMIT_COLUMN,128);
  sqlite3_limit(db,SQLITE_LIMIT_ATTACHED,0);
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
  const char *p[8];lm_mirror_file seen[8];char wal[4096],journal[4096],shm[4096];int i,j;struct stat dir;
  if(lstat(root,&dir)||!S_ISDIR(dir.st_mode)||dir.st_uid!=geteuid()||(dir.st_mode&077)){reject("private-root");return 0;}
  snprintf(wal,sizeof(wal),"%s-wal",target);snprintf(journal,sizeof(journal),"%s-journal",target);snprintf(shm,sizeof(shm),"%s-shm",target);
  p[0]=target;p[1]=wal;p[2]=journal;p[3]=shm;p[4]=baseline;p[5]=clonepath;p[6]=profilepath;p[7]=custody;
  for(i=0;i<8;i++){if(!snapshot(p[i],0,&seen[i]))return 0;for(j=0;j<i;j++)if(seen[i].present&&seen[j].present&&lm_mirror_same_file(&seen[i],&seen[j])){reject("path-alias");return 0;}}
  if(!seen[0].present){reject("target-absent");return 0;}return 1;
}
static int sync_parent(const char *path) {
#ifndef _WIN32
  char p[4096];char *slash;int fd,ok;
  snprintf(p,sizeof(p),"%s",path);slash=strrchr(p,'/');if(slash)*slash=0;else strcpy(p,".");
  fd=open(p,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);if(fd<0){reject("directory-open");return 0;}ok=fsync(fd)==0;if(close(fd))ok=0;
  if(!ok){reject("directory-sync");return 0;}directory_sync=1;
#else
  (void)path;directory_sync=0; /* No claim of durable directory ordering on Windows. */
#endif
  return 1;
}
static int write_new(const char *path,const void *data,size_t size) {
  FILE *f;int ok;
  if(failed||size>LIMIT||explicit_output_bytes>WORKER_EXPLICIT_CAP-size||explicit_output_files>=24){reject("worker-aggregate-output-bound");return 0;}
  explicit_output_bytes+=size;explicit_output_files++;
  f=lm_fopen(path,"wbx");if(!f){reject("exclusive-file-create");return 0;}
  ok=fwrite(data,1,size,f)==size && lm_sync(f);if(fclose(f))ok=0;
  if(!ok){reject("file-write-sync-close");return 0;}return sync_parent(path);
}
static int read_bytes(const char *path,char **p,size_t *n) {
  lm_mirror_file f;lm_err e={{0},{0}};
  if(!lm_mirror_snapshot(path,1,LIMIT,&f,p,n,&e)||!f.present){reject("evidence-read");return 0;}return 1;
}
static int catalog_bytes(sqlite3 *db,lm_sb *b) {
  return query(db,b,"catalog","SELECT type,name,tbl_name,sql FROM sqlite_schema ORDER BY type COLLATE BINARY,name COLLATE BINARY");
}
static int profile_make(void) {
  exr_library *lib=NULL;exr_error e={0};exr_status s;int ok=0;
  if(!write_new(profilepath,"",0))return 0;
  s=exr_library_migration_open(profilepath,&lib,&e);
  if(s==EXR_OK)s=exr_library_migration_ledger_set(lib,"{}",2,&e);
  if(s==EXR_OK)s=exr_library_migration_finish(lib,1,&e);
  sdk_status=s;if(s!=EXR_OK)reject("trusted-profile-sdk");else ok=1;
  if(lib)exr_library_close(lib);return ok&&!failed;
}
static int check_catalog(sqlite3 *db) {
  sqlite3 *profile=NULL;lm_sb actual,want;int version=0,ledger=0;char sql[1024];
  lm_sb_init(&actual);lm_sb_init(&want);
  if(!scalar(db,"PRAGMA user_version",&version)||!scalar(db,"SELECT count(*) FROM sqlite_schema WHERE type='table' AND name='exr_migration_ledger'",&ledger))goto done;
  if(version!=6&&version!=7){reject("unsupported-schema-version");goto done;}
  if(!catalog_bytes(db,&actual)||!open_db(profilepath,0,&profile))goto done;
  snprintf(sql,sizeof(sql),"SELECT type,name,tbl_name,sql FROM sqlite_schema WHERE 1=1 %s %s ORDER BY type COLLATE BINARY,name COLLATE BINARY",
    version==6?"AND name NOT IN('epub_bounded_books','epub_progress','epub_notes','epub_notes_book')":"",
    ledger?"":"AND name<>'exr_migration_ledger'");
  if(!query(profile,&want,"catalog",sql)||actual.n!=want.n||memcmp(actual.p,want.p,actual.n))reject("schema-catalog-mismatch");
 done:close_db(&profile);lm_sb_free(&actual);lm_sb_free(&want);return !failed;
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
static int data_rows(sqlite3 *db,lm_sb *b,int old_version) {
  sqlite3_stmt *s=NULL;int rc=SQLITE_DONE;char *sql;
  if(!sqlok(db,sqlite3_prepare_v2(db,"SELECT name FROM sqlite_schema WHERE type='table' ORDER BY name COLLATE BINARY",-1,&s,NULL),"row-table-list"))return 0;
  while(!failed&&(rc=sqlite3_step(s))==SQLITE_ROW){const char *name=(const char*)sqlite3_column_text(s,0);char label[256];
    if(old_version==6&&!strncmp(name,"epub_",5)){int n=0;sql=sqlite3_mprintf("SELECT count(*) FROM \"%w\"",name);scalar(db,sql,&n);sqlite3_free(sql);if(n)reject("upgrade-added-data");continue;}
    snprintf(label,sizeof(label),"rows:%s",name);sql=sqlite3_mprintf("SELECT _rowid_,* FROM \"%w\" ORDER BY _rowid_",name);query(db,b,label,sql);sqlite3_free(sql);
  }
  if(!failed&&rc!=SQLITE_DONE)sqlok(db,rc,"row-table-step");sqlok(db,sqlite3_finalize(s),"row-table-finalize");return !failed;
}
static double now_seconds(void) {struct timespec t;if(clock_gettime(CLOCK_MONOTONIC,&t)){reject("clock");return 0;}return t.tv_sec+t.tv_nsec/1e9;}
static int worker_progress(void *context) {(void)context;if(now_seconds()-started>30){reject("worker-deadline");return 1;}return 0;}
static int backup_clone(sqlite3 *reader) {
  sqlite3 *dest=NULL;sqlite3_backup *b=NULL;int rc=SQLITE_OK,fin,pages=0,ps=0,prior=-1,remaining;char sql[100];
  if(!scalar(reader,"PRAGMA page_count",&pages)||!scalar(reader,"PRAGMA page_size",&ps)||pages<1||ps<512||ps>65536||(uint64_t)pages*(uint64_t)ps>LIMIT){reject("clone-physical-bound");goto done;}
  if(!write_new(clonepath,"",0)||!namespace_check()||!open_db(clonepath,1,&dest))goto done;
  snprintf(sql,sizeof(sql),"PRAGMA max_page_count=%u",(unsigned)(LIMIT/(unsigned)ps));if(!execsql(dest,sql))goto done;
  b=sqlite3_backup_init(dest,"main",reader,"main");if(!b){sqlok(dest,sqlite3_errcode(dest),"backup-init");goto done;}
  while(!failed){
    if(backup_calls>=4096||backup_reserved>16384-64||worker_progress(NULL)){reject("backup-work-budget");break;}
    backup_calls++;backup_reserved+=64;rc=sqlite3_backup_step(b,64);remaining=sqlite3_backup_remaining(b);
    if(prior>=0&&remaining>prior){reject("backup-restarted");break;}prior=remaining;
    if(rc==SQLITE_DONE)break;if(rc!=SQLITE_OK){sqlok(dest,rc,"backup-step");break;}
    if(!tx(reader,0))break;
  }
  fin=sqlite3_backup_finish(b);b=NULL;if(rc!=SQLITE_DONE)reject("backup-incomplete");sqlok(dest,fin,"backup-finish");
 done:if(b)sqlok(dest,sqlite3_backup_finish(b),"backup-cleanup");close_db(&dest);return !failed;
}
/* Actual public values; compared with a separate SQL projection of the SAME
 * readonly snapshot, and independently checked by Actions fixture expectations. */
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
static int bounded_check(exr_library *lib,int64_t id);
static int sdk_clone_check(void) {
  exr_library *lib=NULL;exr_error e={0};exr_book *books=NULL;size_t count=0,i;exr_status status;
  lm_sb_init(&projection);
  status=exr_library_open(clonepath,&lib,&e);if(status!=EXR_OK){reject("clone-sdk-open");goto done;}
  status=exr_library_books(lib,NULL,&books,&count,&e);if(status!=EXR_OK){reject("clone-books");goto done;}
  for(i=0;i<count&&!failed;i++) {
    exr_source src={0};exr_note *notes=NULL;size_t n=0;void *blob=NULL;size_t size=0;unsigned char block[4096];size_t off=0;
    size_t j;char digest[65];int bounded=0;
    if(books[i].format==EXR_EPUB){exr_library_epub_info info={0};info.struct_size=sizeof(info);if(exr_library_epub_info_get(lib,books[i].id,&info,&e)!=EXR_OK){reject("clone-storage-mode");break;}bounded=info.bounded_storage;}
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
    status=bounded?EXR_OK:exr_library_notes(lib,books[i].id,&notes,&n,&e);if(status!=EXR_OK)reject("clone-notes");
    for(j=0;j<n&&!failed;j++){pr("note");pi(notes[j].id);pi(notes[j].book_id);pu(notes[j].start);pu(notes[j].end);pj(notes[j].text);pa(&notes[j].anchor);pe();}exr_notes_free(notes,n);
    if(books[i].format>=EXR_TXT && books[i].format<=EXR_MOBI && !bounded) {
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
      if(info.bounded_storage&&!bounded_check(lib,books[i].id))reject("bounded-epub-public-validation");
    }
    if(books[i].format==EXR_PDF || books[i].format==EXR_CBZ) {
      exr_fixed_note *fn=NULL;size_t fn_count=0;
      if(exr_library_fixed_notes(lib,books[i].id,&fn,&fn_count,&e)!=EXR_OK)reject("clone-fixed-notes");
      for(j=0;j<fn_count&&!failed;j++){exr_fixed_anchor *a=&fn[j].anchor;pr("fixed-note");pi(fn[j].id);pi(fn[j].book_id);pu(fn[j].page);pu(fn[j].start);pu(fn[j].end);pj(fn[j].text);pu(a->start);pu(a->end);pj(a->page_id);pb(a->exact,a->exact_size);pb(a->prefix,a->prefix_size);pb(a->suffix,a->suffix_size);pe();}exr_fixed_notes_free(fn,fn_count);
    }
    if(books[i].format>=EXR_TXT && books[i].format<=EXR_MOBI && !bounded) {
      exr_document *doc=NULL;status=exr_library_document(lib,books[i].id,&doc,&e);
      if(status!=EXR_OK)reject("clone-reflow-invariant");if(doc)exr_document_free(doc);
    } else if(books[i].format==EXR_PDF || books[i].format==EXR_CBZ) {
      exr_fixed_document *doc=NULL;status=exr_library_fixed(lib,books[i].id,NULL,&doc,&e);
      if(status!=EXR_OK)reject("clone-fixed-invariant");if(doc)exr_fixed_free(doc);
    } else if(!bounded)reject("clone-unsupported-format");
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
  if(!failed&&(projection.n!=expected_projection.n||memcmp(projection.p,expected_projection.p,projection.n)))reject("public-projection-mismatch");
  if(!failed){char path[4096];snprintf(path,sizeof(path),"%s/public-projection.jsonl",root);write_new(path,projection.p,projection.n);}
  lm_sb_free(&projection);return !failed;
}
/* SQL projection is deliberately separate from public getters. It runs while
 * the original READ snapshot is pinned, before any clone SDK upgrade. */
static const char *ct(sqlite3_stmt *s,int i){
  const char *text;int n,type=sqlite3_column_type(s,i);if(type==SQLITE_NULL)return NULL;
  if(type!=SQLITE_TEXT){reject("public-text-storage-class");return NULL;}
  text=(const char*)sqlite3_column_text(s,i);n=sqlite3_column_bytes(s,i);
  if(!text||n<0||strlen(text)!=(size_t)n||!lm_utf8_valid(text,(size_t)n)){reject("public-text-encoding-or-NUL");return NULL;}return text;
}
static uint64_t offset64(sqlite3_stmt *s,int i){const unsigned char *p=sqlite3_column_blob(s,i);uint64_t v=0;int k;if(sqlite3_column_type(s,i)!=SQLITE_BLOB||sqlite3_column_bytes(s,i)!=8){reject("audio-offset-type");return 0;}for(k=0;k<8;k++)v|=(uint64_t)p[k]<<(8*k);return v;}
static sqlite3_stmt *select_id(sqlite3 *db,const char *sql,int64_t id){sqlite3_stmt *s=NULL;if(!sqlok(db,sqlite3_prepare_v2(db,sql,-1,&s,NULL),"projection-prepare"))return NULL;if(sqlite3_bind_parameter_count(s)&&!sqlok(db,sqlite3_bind_int64(s,1,id),"projection-bind")){sqlite3_finalize(s);return NULL;}return s;}
static void projection_end(sqlite3 *db,sqlite3_stmt *s,int rc){if(rc!=SQLITE_DONE&&!failed)sqlok(db,rc,"projection-step");if(s)sqlok(db,sqlite3_finalize(s),"projection-finalize");}
static int sql_projection(sqlite3 *db){
  sqlite3_stmt *b=NULL,*s=NULL;int rc=SQLITE_DONE,x=SQLITE_DONE,version=0;
  lm_sb_init(&projection);if(!scalar(db,"PRAGMA user_version",&version))goto done;
  b=select_id(db,"SELECT id,format,title,author,tags,favorite,status,position,source,cover FROM books ORDER BY id DESC",0);if(!b)goto done;
  while(!failed&&(rc=sqlite3_step(b))==SQLITE_ROW){
    int64_t id=sqlite3_column_int64(b,0);int fmt=sqlite3_column_int(b,1),bounded=0,k;char digest[65];
    if(fmt==EXR_EPUB&&version==7){s=select_id(db,"SELECT count(*) FROM epub_bounded_books WHERE book_id=?1",id);if(!s)break;x=sqlite3_step(s);if(x==SQLITE_ROW){bounded=sqlite3_column_int(s,0);x=sqlite3_step(s);}projection_end(db,s,x);s=NULL;}
    pr("book");pi(id);pi(fmt);for(k=2;k<=4;k++)pj(ct(b,k));for(k=5;k<=7;k++)pi(sqlite3_column_int64(b,k));pe();
    for(k=8;k<=9;k++){const void *blob=sqlite3_column_blob(b,k);int n=sqlite3_column_bytes(b,k);lm_sha_bytes(blob,(size_t)n,digest);pr(k==8?"source":"cover");pi(id);px((uint64_t)n);pj(digest);pe();}
    if(!bounded){
      s=select_id(db,"SELECT id,start,end,text,anchor_exact,anchor_prefix,anchor_suffix,anchor_chapter,location_state FROM notes WHERE book_id=?1 ORDER BY start,id",id);if(!s)break;
      while(!failed&&(x=sqlite3_step(s))==SQLITE_ROW){int st=sqlite3_column_int(s,8);pr("note");pi(sqlite3_column_int64(s,0));pi(id);pi(st==1?sqlite3_column_int64(s,1):-1);pi(st==1?sqlite3_column_int64(s,2):-1);pj(ct(s,3));pi(sqlite3_column_int64(s,1));pi(sqlite3_column_int64(s,2));for(k=4;k<=7;k++)pj(ct(s,k));pe();}projection_end(db,s,x);s=NULL;
    }
    if(fmt>=EXR_TXT&&fmt<=EXR_MOBI&&!bounded){
      s=select_id(db,"SELECT position,state,prefix,suffix,chapter FROM book_progress WHERE book_id=?1",id);if(!s)break;x=sqlite3_step(s);pr("progress");pi(id);
      if(x==SQLITE_ROW){int st=sqlite3_column_int(s,1);pi(st);pi(sqlite3_column_int64(s,0));pi(sqlite3_column_int64(s,0));pj(st==3?NULL:"");for(k=2;k<=4;k++)pj(ct(s,k));x=sqlite3_step(s);}
      else if(x==SQLITE_DONE){pi(3);pi(sqlite3_column_int64(b,7));pi(sqlite3_column_int64(b,7));for(k=0;k<4;k++)pj(NULL);}else sqlok(db,x,"progress-row");pe();projection_end(db,s,x);s=NULL;
    }
    if(fmt==EXR_EPUB){
      pr("epub-info");pi(id);pi(bounded);pi(!bounded);pe();pr("epub-progress");pi(id);
      if(version==7){s=select_id(db,"SELECT part,path,position,prefix,suffix,chapter FROM epub_progress WHERE book_id=?1",id);if(!s)break;x=sqlite3_step(s);if(x==SQLITE_ROW){pi(1);pi(sqlite3_column_int64(s,0));pj(ct(s,1));pi(sqlite3_column_int64(s,2));pi(sqlite3_column_int64(s,2));pj("");for(k=3;k<=5;k++)pj(ct(s,k));x=sqlite3_step(s);}else if(x==SQLITE_DONE)pi(0);else sqlok(db,x,"epub-progress-row");projection_end(db,s,x);s=NULL;}else pi(0);pe();
      if(version==7){s=select_id(db,"SELECT id,part,path,start,end,exact,prefix,suffix,chapter,text FROM epub_notes WHERE book_id=?1 ORDER BY part,start,id",id);if(!s)break;
        while(!failed&&(x=sqlite3_step(s))==SQLITE_ROW){pr("epub-note");pi(sqlite3_column_int64(s,0));pi(id);pi(sqlite3_column_int64(s,1));pj(ct(s,2));pi(sqlite3_column_int64(s,3));pi(sqlite3_column_int64(s,4));for(k=5;k<=9;k++)pj(ct(s,k));pe();}projection_end(db,s,x);s=NULL;}
    }
    if(fmt==EXR_PDF||fmt==EXR_CBZ){s=select_id(db,"SELECT id,page,start,end,text,page_id,exact,prefix,suffix FROM fixed_notes WHERE book_id=?1 ORDER BY page,start,id",id);if(!s)break;
      while(!failed&&(x=sqlite3_step(s))==SQLITE_ROW){pr("fixed-note");pi(sqlite3_column_int64(s,0));pi(id);for(k=1;k<=3;k++)pi(sqlite3_column_int64(s,k));pj(ct(s,4));pi(sqlite3_column_int64(s,2));pi(sqlite3_column_int64(s,3));pj(ct(s,5));for(k=6;k<=8;k++)pb(sqlite3_column_blob(s,k),(size_t)sqlite3_column_bytes(s,k));pe();}projection_end(db,s,x);s=NULL;}
  }
  projection_end(db,b,rc);b=NULL;
  if(failed)goto done;
  b=select_id(db,"SELECT audio_id FROM audio_resume UNION SELECT audio_id FROM audio_marks ORDER BY audio_id",0);if(!b)goto done;
  while(!failed&&(rc=sqlite3_step(b))==SQLITE_ROW){const char *key=ct(b,0);char *sql;
    sql=sqlite3_mprintf("SELECT track_id,offset,rate FROM audio_resume WHERE audio_id=%Q",key);s=select_id(db,sql,0);sqlite3_free(sql);if(!s)break;
    x=sqlite3_step(s);pr("audio-resume");pj(key);if(x==SQLITE_ROW){pi(1);pj(ct(s,0));px(offset64(s,1));pd(sqlite3_column_double(s,2));x=sqlite3_step(s);}else if(x==SQLITE_DONE)pi(0);else sqlok(db,x,"audio-resume-row");pe();projection_end(db,s,x);s=NULL;
    sql=sqlite3_mprintf("SELECT id,label,track_id,offset,rate FROM audio_marks WHERE audio_id=%Q ORDER BY id",key);s=select_id(db,sql,0);sqlite3_free(sql);if(!s)break;
    while(!failed&&(x=sqlite3_step(s))==SQLITE_ROW){pr("audio-mark");pj(key);pi(sqlite3_column_int64(s,0));pj(ct(s,1));pj(ct(s,2));px(offset64(s,3));pd(sqlite3_column_double(s,4));pe();}projection_end(db,s,x);s=NULL;
  }
 done:if(s)projection_end(db,s,x);if(b)projection_end(db,b,rc);expected_projection=projection;memset(&projection,0,sizeof(projection));return !failed;
}
static int bounded_check(exr_library *lib,int64_t id){
  exr_source source={0};exr_publication *publication=NULL;exr_font *font=NULL;exr_error e={0};exr_epub_note *notes=NULL;size_t n=0,parts_n=0,i,j;const exr_part *parts=NULL;exr_epub_location progress={0};int found=0;lm_sb saved=projection;char path[4096];
  lm_sb_init(&projection);
  if(!font_path||!strcmp(font_path,"-")){reject("bounded-epub-requires-recovery-font");goto done;}
  if(exr_font_open(font_path,&font,&e)!=EXR_OK||exr_library_source(lib,id,&source,&e)!=EXR_OK){reject("bounded-font-or-source");goto done;}
  if(exr_publication_open_source(&source,&publication,&e)!=EXR_OK){reject("bounded-publication");goto done;}memset(&source,0,sizeof(source));
  parts=exr_publication_parts(publication,&parts_n);if(!parts||parts_n>10000){reject("bounded-parts");goto done;}
  if(exr_library_epub_notes(lib,id,&notes,&n,&e)!=EXR_OK||exr_library_epub_progress_get(lib,id,&progress,&found,&e)!=EXR_OK){reject("bounded-state");goto done;}
  for(i=0;i<parts_n&&!failed;i++){
    exr_pager *pager=NULL;exr_layout_config config=exr_layout_config_defaults();exr_chapter_options options=exr_chapter_options_defaults();
    pr("part");px(i);pj(parts[i].id);pj(parts[i].path);pj(parts[i].title);pi(parts[i].in_reading_order);pe();
    if(!parts[i].in_reading_order)continue;
    options.workspace_budget=8u*1024u*1024u;config.control.cancelled=worker_progress;
    if(exr_publication_pager_create(publication,i,font,&config,&options,&pager,&e)!=EXR_OK){reject("bounded-pager");break;}
    for(j=0;j<n&&!failed;j++)if(notes[j].location.part==i){exr_anchor_match match={0};
      if(strcmp(notes[j].location.path,parts[i].path)||exr_pager_anchor_resolve(pager,&notes[j].location.selector,&config.control,&match,&e)!=EXR_OK)reject("bounded-note-resolve");
      pr("note-resolution");pi(notes[j].id);pi(match.state);pu(match.start);pu(match.end);pe();}
    if(found&&progress.part==i){exr_anchor_match match={0};if(strcmp(progress.path,parts[i].path)||exr_pager_anchor_resolve(pager,&progress.selector,&config.control,&match,&e)!=EXR_OK)reject("bounded-progress-resolve");pr("progress-resolution");pi(match.state);pu(match.start);pu(match.end);pe();}
    exr_pager_free(pager);if(worker_progress(NULL))break;
  }
  for(j=0;j<n&&!failed;j++)if(notes[j].location.part>=parts_n||!parts[notes[j].location.part].in_reading_order)reject("bounded-note-part");
  if(found&&(progress.part>=parts_n||!parts[progress.part].in_reading_order))reject("bounded-progress-part");
 done:
  exr_epub_notes_free(notes,n);exr_epub_location_free(&progress);if(publication)exr_publication_free(publication);if(source.context)source.release(source.context);if(font)exr_font_free(font);
  if(!failed){snprintf(path,sizeof(path),"%s/bounded-%lld.jsonl",root,(long long)id);write_new(path,projection.p,projection.n);}lm_sb_free(&projection);projection=saved;return !failed;
}
static int ledger_output(sqlite3 *db,int *found){sqlite3_stmt *s=NULL;int present=0,rc;char path[4096];*found=0;
  if(!scalar(db,"SELECT count(*) FROM sqlite_schema WHERE type='table' AND name='exr_migration_ledger'",&present))return 0;
  snprintf(path,sizeof(path),"%s/ledger.bin",root);if(!present)return write_new(path,"",0);
  s=select_id(db,"SELECT data FROM exr_migration_ledger WHERE id=1",0);if(!s)return 0;rc=sqlite3_step(s);
  if(rc==SQLITE_ROW){const void *p=sqlite3_column_blob(s,0);int n=sqlite3_column_bytes(s,0);if(sqlite3_column_type(s,0)!=SQLITE_BLOB||n<=0||(unsigned)n>LIMIT)reject("ledger-shape");else{*found=1;write_new(path,p,(size_t)n);}rc=sqlite3_step(s);}
  else if(rc==SQLITE_DONE)write_new(path,"",0);projection_end(db,s,rc);return !failed;
}
int main(int argc,char **argv){
  sqlite3 *db=NULL,*clone=NULL;lm_sb bytes,copy;int ok=0,found=0;lm_mirror_file after;struct rlimit cap;char expected_sha[65]={0},actual_sha[65]={0};
  if(argc!=7)return 2;mode=argv[1];target=argv[2];root=argv[3];nonce=argv[4];font_path=argv[5];fault=argv[6];
  if(strcmp(mode,"capture")&&strcmp(mode,"scan")&&strcmp(mode,"seal")&&strcmp(mode,"observe")&&strcmp(mode,"create-capture")&&strcmp(mode,"create-scan"))return 2;
  if(strlen(nonce)!=32||strspn(nonce,"0123456789abcdef")!=32)return 2;
  if(strcmp(fault,"none")&&(!getenv("EXR_MIGRATE_TEST_FAULTS")||strcmp(getenv("EXR_MIGRATE_TEST_FAULTS"),"1")))return 2;
  if(SQLITE_VERSION_NUMBER!=3054000||sqlite3_libversion_number()!=3054000||strcmp(SQLITE_SOURCE_ID,sqlite3_sourceid())||strcmp(exr_version(),"3.42.0")||exr_abi_version()!=1)return 2;
  umask(077);cap.rlim_cur=cap.rlim_max=LIMIT;if(setrlimit(RLIMIT_FSIZE,&cap))return 2;cap.rlim_cur=cap.rlim_max=30;if(setrlimit(RLIMIT_CPU,&cap))return 2;
  started=now_seconds();lm_sb_init(&bytes);lm_sb_init(&copy);lm_sb_init(&expected_projection);lm_sb_init(&expected_rows);lm_binary_stdout();
  snprintf(baseline,sizeof(baseline),"%s/baseline.bin",root);snprintf(clonepath,sizeof(clonepath),"%s/clone.sqlite",root);snprintf(profilepath,sizeof(profilepath),"%s/profile.sqlite",root);snprintf(custody,sizeof(custody),"%s/request.json",root);
  if(!strcmp(mode,"seal")||!strcmp(mode,"observe")||!strcmp(mode,"create-capture")||!strcmp(mode,"create-scan")){
    lm_err e={{0},{0}};char p[4096];const char *ends[]={"-wal","-shm","-journal"};unsigned i;
    if(!ln_child_worker_enter(custody,target,font_path,mode,&e)||!ln_child_nonce_matches(nonce)){reject("seal-child-liveness-or-control");goto done;}
    for(i=0;!strcmp(mode,"seal")&&i<3;i++){struct stat st;snprintf(p,sizeof(p),"%s%s",target,ends[i]);if(!lstat(p,&st)||errno!=ENOENT){reject("seal-sidecar-present");goto done;}}
    if(!ln_child_pause(!strcmp(mode,"seal")?"seal-worker-alive":!strcmp(mode,"observe")?"observe-worker-alive":"suffix-worker-alive",&e)){reject("seal-child-liveness-or-control");goto done;}
  }
  if(!namespace_check()||!snapshot(target,0,&original)||!profile_make()||!open_db(target,!strcmp(mode,"seal"),&db))goto done;
  if(!strcmp(mode,"seal")){
    sqlite3_stmt *s=NULL;int rc;
    if(!sqlok(db,sqlite3_prepare_v2(db,"PRAGMA journal_mode",-1,&s,NULL),"seal-mode-prepare"))goto done;
    rc=sqlite3_step(s);if(rc!=SQLITE_ROW||sqlite3_column_type(s,0)!=SQLITE_TEXT||strcmp((const char*)sqlite3_column_text(s,0),"delete"))reject("seal-private-delete-required");
    if(!failed&&sqlite3_step(s)!=SQLITE_DONE)reject("seal-mode-tail");sqlok(db,sqlite3_finalize(s),"seal-mode-finalize");if(failed)goto done;
  }
  sqlite3_progress_handler(db,1000,worker_progress,NULL);
  if(!execsql(db,!strcmp(mode,"seal")?"PRAGMA locking_mode=EXCLUSIVE;BEGIN EXCLUSIVE;COMMIT;BEGIN":"BEGIN")||!canonical(db,&bytes,1)||!tx(db,0)||!ledger_output(db,&found))goto done;
  if(!strcmp(mode,"seal")){
    const char *queries[]={"PRAGMA journal_mode","PRAGMA locking_mode"};const char *want[]={"delete","exclusive"};unsigned i;
    for(i=0;i<2&&!failed;i++){sqlite3_stmt *q=NULL;int rc;if(!sqlok(db,sqlite3_prepare_v2(db,queries[i],-1,&q,NULL),"seal-locked-mode-prepare"))break;rc=sqlite3_step(q);if(rc!=SQLITE_ROW||sqlite3_column_type(q,0)!=SQLITE_TEXT||strcmp((const char*)sqlite3_column_text(q,0),want[i]))reject("seal-locked-mode-readback");if(!failed&&sqlite3_step(q)!=SQLITE_DONE)reject("seal-locked-mode-tail");sqlok(db,sqlite3_finalize(q),"seal-locked-mode-finalize");}
    {lm_err e={{0},{0}};if(!failed&&!ln_child_pause("seal-read-fence",&e))reject("seal-read-fence-control");}if(failed)goto done;
  }
  if(!strcmp(mode,"capture")||!strcmp(mode,"seal")||!strcmp(mode,"observe")||!strcmp(mode,"create-capture")){
    if(!scalar(db,"PRAGMA user_version",&initial_version)||!data_rows(db,&expected_rows,initial_version)||!sql_projection(db)||!backup_clone(db)||!tx(db,0))goto done;
    if(!open_db(clonepath,0,&clone)||!execsql(clone,"BEGIN")||!canonical(clone,&copy,1)||!tx(clone,0)||bytes.n!=copy.n||memcmp(bytes.p,copy.p,bytes.n)){reject("clone-full-parity");goto done;}
    close_db(&clone);if(failed)goto done;
  }
  if(!close_db(&db)||!snapshot(target,0,&after)||!lm_mirror_same_file(&original,&after))goto done;
  if(!strcmp(mode,"capture")||!strcmp(mode,"seal")||!strcmp(mode,"observe")||!strcmp(mode,"create-capture")){
    lm_sb rows;lm_sb_init(&rows);
    if(!sdk_clone_check()||!open_db(clonepath,0,&clone)||!execsql(clone,"BEGIN")||!check_catalog(clone)||!health(clone)||!data_rows(clone,&rows,initial_version)||!tx(clone,0)||rows.n!=expected_rows.n||memcmp(rows.p,expected_rows.p,rows.n))reject("clone-sdk-preservation");
    lm_sb_free(&rows);close_db(&clone);if(failed)goto done;
  }
  if(!strcmp(mode,"seal")){char p[4096];const char *ends[]={"-wal","-shm","-journal"};unsigned i;for(i=0;i<3;i++){struct stat st;snprintf(p,sizeof(p),"%s%s",target,ends[i]);if(!lstat(p,&st)||errno!=ENOENT){reject("seal-sidecar-after-close");goto done;}}}
  if(!write_new(baseline,bytes.p,bytes.n))goto done;
  lm_sha_bytes(bytes.p,bytes.n,actual_sha);if(!strcmp(mode,"capture")||!strcmp(mode,"seal")||!strcmp(mode,"observe")||!strcmp(mode,"create-capture")){lm_sha_bytes(expected_projection.p,expected_projection.n,expected_sha);}
  ok=1;
 done:
  close_db(&clone);close_db(&db);lm_sb_free(&bytes);lm_sb_free(&copy);lm_sb_free(&expected_projection);lm_sb_free(&expected_rows);
  printf("{\"mode\":\"%s\",\"nonce\":\"%s\",\"passed\":%s,\"reason\":\"%s\",\"target_identity\":\"%s\",\"baseline_sha256\":\"%s\",\"projection_sha256\":\"%s\",\"ledger_found\":%s,\"sqlite_extended_code\":%d,\"sdk_status\":%d,\"backup_calls\":%u,\"reserved_page_work\":%u,\"target_sdk_open_attempts\":0,\"physical_cleanup_verified\":false}\n",mode,nonce,ok&&!failed?"true":"false",reason,original.identity,actual_sha,expected_sha,found?"true":"false",last_sqlite,sdk_status,backup_calls,backup_reserved);
  return ok&&!failed?0:3;
}
