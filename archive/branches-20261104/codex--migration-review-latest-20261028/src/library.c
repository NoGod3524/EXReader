/* SPDX-License-Identifier: MIT */
#include "formats_internal.h"
#include "pdf_internal.h"
#include "exr/library.h"
#include <sqlite3.h>
static exr_status open_fixed(exr_format format,const void *data,size_t size,
  const exr_fixed_open_options *options,exr_fixed_document **out,exr_error *e) {
#ifdef EXR_ENABLE_PDF
  return exr_fixed_open_memory(format,data,size,options,out,e);
#else
  (void)format;(void)data;(void)size;(void)options;
  if(out) *out=NULL;
  return exr_fail(e,EXR_UNSUPPORTED,"Fixed-format import requires the PDF component");
#endif
}
#define FIXED_SCHEMA "CREATE TABLE fixed_notes(id INTEGER PRIMARY KEY,book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE," \
  "page INTEGER NOT NULL CHECK(page>=0),start INTEGER NOT NULL CHECK(start>=0),end INTEGER NOT NULL CHECK(end>=start)," \
  "text TEXT NOT NULL,page_id TEXT NOT NULL,exact BLOB NOT NULL,prefix BLOB NOT NULL,suffix BLOB NOT NULL);" \
  "CREATE INDEX fixed_notes_book ON fixed_notes(book_id,page,start);"
#define AUDIO_SCHEMA "CREATE TABLE audio_resume(audio_id TEXT PRIMARY KEY,track_id TEXT NOT NULL,offset BLOB NOT NULL CHECK(typeof(offset)='blob' AND length(offset)=8),rate REAL NOT NULL CHECK(rate>0 AND rate<=16));" \
  "CREATE TABLE audio_marks(id INTEGER PRIMARY KEY,audio_id TEXT NOT NULL,track_id TEXT NOT NULL,offset BLOB NOT NULL CHECK(typeof(offset)='blob' AND length(offset)=8),rate REAL NOT NULL CHECK(rate>0 AND rate<=16),label TEXT NOT NULL);" \
  "CREATE INDEX audio_marks_key ON audio_marks(audio_id,id);"
#define PROGRESS_SCHEMA "CREATE TABLE book_progress(book_id INTEGER PRIMARY KEY REFERENCES books(id) ON DELETE CASCADE,position INTEGER NOT NULL CHECK(position>=0),state INTEGER NOT NULL CHECK(state BETWEEN 0 AND 3),prefix TEXT,suffix TEXT,chapter TEXT);" \
  "CREATE TRIGGER books_progress_changed AFTER UPDATE OF position ON books WHEN OLD.position<>NEW.position BEGIN DELETE FROM book_progress WHERE book_id=NEW.id;END;"
#define LOCATION_SCHEMA "ALTER TABLE notes ADD COLUMN location_state INTEGER NOT NULL DEFAULT 1 CHECK(location_state BETWEEN 0 AND 3);"
#define EPUB_BOUNDED_SCHEMA "CREATE TABLE epub_bounded_books(book_id INTEGER PRIMARY KEY REFERENCES books(id) ON DELETE CASCADE);" \
  "CREATE TABLE epub_progress(book_id INTEGER PRIMARY KEY REFERENCES books(id) ON DELETE CASCADE," \
  "part INTEGER NOT NULL CHECK(part>=0 AND part<10000),path TEXT NOT NULL," \
  "position INTEGER NOT NULL CHECK(position>=0),prefix TEXT,suffix TEXT,chapter TEXT);" \
  "CREATE TABLE epub_notes(id INTEGER PRIMARY KEY,book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE," \
  "part INTEGER NOT NULL CHECK(part>=0 AND part<10000),path TEXT NOT NULL," \
  "start INTEGER NOT NULL CHECK(start>=0),end INTEGER NOT NULL CHECK(end>start)," \
  "exact TEXT NOT NULL,prefix TEXT,suffix TEXT,chapter TEXT,text TEXT NOT NULL);" \
  "CREATE INDEX epub_notes_book ON epub_notes(book_id,part,start,id);"
#define SCHEMA_FINISH EPUB_BOUNDED_SCHEMA "PRAGMA user_version=7;COMMIT;"
typedef struct library_source library_source;
struct exr_library {
  sqlite3 *db;
  size_t references;
  library_source *sources;
  int migration_transaction;
};
static exr_status database_error(exr_library *l, exr_error *e) {
  return exr_fail(e, EXR_DATABASE, "%s", sqlite3_errmsg(l->db));
}
/* Existing APIs retain their ordinary transactions. In a migration owner, each
   operation uses a savepoint under the outer write transaction. */
static int operation_begin(exr_library *l) {
  return sqlite3_exec(l->db,l->migration_transaction ? "SAVEPOINT exr_operation" : "BEGIN IMMEDIATE",NULL,NULL,NULL);
}
static int operation_commit(exr_library *l) {
  return sqlite3_exec(l->db,l->migration_transaction ? "RELEASE exr_operation" : "COMMIT",NULL,NULL,NULL);
}
static int operation_rollback(exr_library *l) {
  return sqlite3_exec(l->db,l->migration_transaction ? "ROLLBACK TO exr_operation;RELEASE exr_operation" : "ROLLBACK",NULL,NULL,NULL);
}
/* The schema SQL is a complete BEGIN ... COMMIT script. In the migration
   owner it runs in a nested savepoint instead of committing the outer unit. */
static int schema_execute(exr_library *l,const char *sql) {
  static const char begin[]="BEGIN IMMEDIATE;", end[]="COMMIT;";
  size_t n=strlen(sql), a=sizeof(begin)-1, b=sizeof(end)-1;
  char *nested;int result;
  if(!l->migration_transaction) return sqlite3_exec(l->db,sql,NULL,NULL,NULL);
  if(n<a+b || strncmp(sql,begin,a) || strcmp(sql+n-b,end)) return SQLITE_ERROR;
  nested=sqlite3_mprintf("SAVEPOINT exr_schema;%.*sRELEASE exr_schema;",(int)(n-a-b),sql+a);
  if(!nested) return SQLITE_NOMEM;
  result=sqlite3_exec(l->db,nested,NULL,NULL,NULL);sqlite3_free(nested);
  return result;
}
static int prepare(exr_library *l, const char *sql, sqlite3_stmt **s) {
  return sqlite3_prepare_v2(l->db, sql, -1, s, NULL) == SQLITE_OK;
}
static int bind_text(sqlite3_stmt *s, int index, const char *text) {
  return sqlite3_bind_text(s, index, text ? text : "", -1, SQLITE_TRANSIENT) == SQLITE_OK;
}
static exr_status done(exr_library *l, sqlite3_stmt *s, exr_error *e) {
  int result = sqlite3_step(s);
  sqlite3_finalize(s);
  return result == SQLITE_DONE ? EXR_OK : database_error(l, e);
}
static int scalar(sqlite3 *db, const char *sql) {
  sqlite3_stmt *s = NULL;
  int value = -1;
  if (sqlite3_prepare_v2(db, sql, -1, &s, NULL) == SQLITE_OK && sqlite3_step(s) == SQLITE_ROW)
    value = sqlite3_column_int(s, 0);
  sqlite3_finalize(s);
  return value;
}
static exr_status book_storage(exr_library *l,int64_t id,int *format,int *bounded,
                                int missing_ok,exr_error *e) {
  sqlite3_stmt *s=NULL;exr_status status=EXR_OK;int step;sqlite3_int64 value;
  *format=0;*bounded=0;
  if(!prepare(l,"SELECT b.format,b.position,b.text_size,m.book_id FROM books b "
                "LEFT JOIN epub_bounded_books m ON m.book_id=b.id WHERE b.id=?1",&s) ||
     sqlite3_bind_int64(s,1,id)!=SQLITE_OK) { status=database_error(l,e);goto finish; }
  step=sqlite3_step(s);
  if(step!=SQLITE_ROW) {
    status=step==SQLITE_DONE ? (missing_ok ? EXR_OK : exr_fail(e,EXR_ARGUMENT,"Book missing")) : database_error(l,e);
    goto finish;
  }
  value=sqlite3_column_int64(s,0);
  if(sqlite3_column_type(s,0)!=SQLITE_INTEGER || value<EXR_TXT || value>EXR_CBZ) {
    status=exr_fail(e,EXR_DATABASE,"Invalid stored book format");goto finish;
  }
  *format=(int)value;
  if(sqlite3_column_type(s,3)!=SQLITE_NULL) {
    if(sqlite3_column_type(s,3)!=SQLITE_INTEGER || sqlite3_column_int64(s,3)!=id ||
       *format!=EXR_EPUB || sqlite3_column_type(s,1)!=SQLITE_INTEGER || sqlite3_column_int64(s,1)!=0 ||
       sqlite3_column_type(s,2)!=SQLITE_INTEGER || sqlite3_column_int64(s,2)!=0) {
      status=exr_fail(e,EXR_DATABASE,"Invalid bounded EPUB storage mode");goto finish;
    }
    *bounded=1;
  }
finish:
  sqlite3_finalize(s);return status;
}
static exr_status require_global_storage(exr_library *l,int64_t id,exr_error *e) {
  int format,bounded;exr_status status=book_storage(l,id,&format,&bounded,1,e);
  return status==EXR_OK && bounded ?
    exr_fail(e,EXR_UNSUPPORTED,"Bounded EPUB uses chapter-local progress and notes") : status;
}
static exr_status library_open(const char *path, exr_library **out, exr_error *e, int transactional) {
  exr_library *l;
  int result;
  const char *schema = "BEGIN IMMEDIATE;"
                       "CREATE TABLE IF NOT EXISTS books(id INTEGER PRIMARY KEY,format INTEGER "
                       "NOT NULL,title TEXT NOT NULL,author TEXT NOT NULL DEFAULT '',tags TEXT "
                       "NOT NULL DEFAULT '',favorite INTEGER NOT NULL DEFAULT 0 CHECK(favorite "
                       "IN(0,1)),status INTEGER NOT NULL DEFAULT 0 CHECK(status BETWEEN 0 AND "
                       "2),position INTEGER NOT NULL DEFAULT 0 CHECK(position>=0 AND "
                       "position<=text_size),text_size INTEGER NOT NULL,source BLOB NOT "
                       "NULL,cover BLOB);"
                       "CREATE TABLE IF NOT EXISTS notes(id INTEGER PRIMARY KEY,book_id INTEGER "
                       "NOT NULL REFERENCES books(id) ON DELETE CASCADE,start INTEGER NOT NULL "
                       "CHECK(start>=0),end INTEGER NOT NULL CHECK(end>=start),text TEXT NOT "
                       "NULL,anchor_exact TEXT,anchor_prefix TEXT,anchor_suffix TEXT,"
                       "anchor_chapter TEXT,location_state INTEGER NOT NULL DEFAULT 1 CHECK(location_state BETWEEN 0 AND 3));"
                       "CREATE INDEX IF NOT EXISTS notes_book ON notes(book_id);PRAGMA "
                       "application_id=1163416131;" FIXED_SCHEMA AUDIO_SCHEMA PROGRESS_SCHEMA SCHEMA_FINISH;
  if (!path || !out)
    return exr_fail(e, EXR_ARGUMENT, "Invalid library arguments");
  *out = NULL;
  l = calloc(1, sizeof(*l));
  if (!l)
    return exr_fail(e, EXR_MEMORY, "Library allocation failed");
  l->references = 1;
  result = sqlite3_open_v2(
      path, &l->db, SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE | SQLITE_OPEN_FULLMUTEX, NULL);
  if (result != SQLITE_OK) {
    exr_fail(e, EXR_DATABASE, "%s", l->db ? sqlite3_errmsg(l->db) : "Cannot open library");
    exr_library_close(l);
    return EXR_DATABASE;
  }
  sqlite3_busy_timeout(l->db, 3000);
  sqlite3_db_config(l->db, SQLITE_DBCONFIG_DEFENSIVE, 1, NULL);
  if (sqlite3_exec(l->db, "PRAGMA foreign_keys=ON;PRAGMA trusted_schema=OFF;", NULL, NULL, NULL) !=
      SQLITE_OK) {
    database_error(l, e);
    exr_library_close(l);
    return EXR_DATABASE;
  }
  if(transactional) {
    if(operation_begin(l)!=SQLITE_OK) {
      database_error(l,e);exr_library_close(l);return EXR_DATABASE;
    }
    l->migration_transaction=1;
  }
  {
    int app = scalar(l->db, "PRAGMA application_id"),
        version = scalar(l->db, "PRAGMA user_version");
    if(transactional && !((app==1163416131 && (version==6 || version==7)) || (app==0 && version==0))) {
      exr_fail(e,EXR_DATABASE,"Migration requires schema 6 or 7");exr_library_close(l);return EXR_DATABASE;
    }
    if (app == 1163416131 && version == 1) {
      const char *migration =
          "BEGIN IMMEDIATE;ALTER TABLE notes ADD COLUMN anchor_exact TEXT;"
          "ALTER TABLE notes ADD COLUMN anchor_prefix TEXT;"
          "ALTER TABLE notes ADD COLUMN anchor_suffix TEXT;"
          "ALTER TABLE notes ADD COLUMN anchor_chapter TEXT;"
          FIXED_SCHEMA AUDIO_SCHEMA PROGRESS_SCHEMA LOCATION_SCHEMA SCHEMA_FINISH;
      if (schema_execute(l, migration) != SQLITE_OK) {
        database_error(l, e);
        sqlite3_exec(l->db, "ROLLBACK", NULL, NULL, NULL);
        exr_library_close(l);
        return EXR_DATABASE;
      }
      *out = l;
      return EXR_OK;
    }
    if(app==1163416131 && version==2) {
      if(schema_execute(l,"BEGIN IMMEDIATE;" FIXED_SCHEMA AUDIO_SCHEMA PROGRESS_SCHEMA LOCATION_SCHEMA SCHEMA_FINISH)!=SQLITE_OK) {
        database_error(l,e); sqlite3_exec(l->db,"ROLLBACK",NULL,NULL,NULL); exr_library_close(l); return EXR_DATABASE;
      }
      *out=l; return EXR_OK;
    }
    if(app==1163416131 && version==3) {
      if(schema_execute(l,"BEGIN IMMEDIATE;" AUDIO_SCHEMA PROGRESS_SCHEMA LOCATION_SCHEMA SCHEMA_FINISH)!=SQLITE_OK) {
        database_error(l,e); sqlite3_exec(l->db,"ROLLBACK",NULL,NULL,NULL); exr_library_close(l); return EXR_DATABASE;
      }
      *out=l; return EXR_OK;
    }
    if(app==1163416131 && version==4) {
      if(schema_execute(l,"BEGIN IMMEDIATE;" PROGRESS_SCHEMA LOCATION_SCHEMA SCHEMA_FINISH)!=SQLITE_OK) {
        database_error(l,e); sqlite3_exec(l->db,"ROLLBACK",NULL,NULL,NULL); exr_library_close(l); return EXR_DATABASE;
      }
      *out=l; return EXR_OK;
    }
    if(app==1163416131 && version==5) {
      const char *migration="BEGIN IMMEDIATE;DROP TRIGGER books_progress_changed;ALTER TABLE book_progress RENAME TO book_progress_v5;"
        PROGRESS_SCHEMA "INSERT INTO book_progress SELECT * FROM book_progress_v5;DROP TABLE book_progress_v5;" LOCATION_SCHEMA SCHEMA_FINISH;
      if(schema_execute(l,migration)!=SQLITE_OK) { database_error(l,e); sqlite3_exec(l->db,"ROLLBACK",NULL,NULL,NULL); exr_library_close(l); return EXR_DATABASE; }
      *out=l; return EXR_OK;
    }
    if (app == 1163416131 && version == 6) {
      if(schema_execute(l,"BEGIN IMMEDIATE;" SCHEMA_FINISH)!=SQLITE_OK) {
        database_error(l,e);sqlite3_exec(l->db,"ROLLBACK",NULL,NULL,NULL);exr_library_close(l);return EXR_DATABASE;
      }
      *out=l;return EXR_OK;
    }
    if (app == 1163416131 && version == 7) {
      *out = l;
      return EXR_OK;
    }
    if (app != 0 || version != 0 ||
        scalar(l->db, "SELECT count(*) FROM sqlite_master WHERE name NOT LIKE "
                      "'sqlite_%'") != 0) {
      exr_fail(e, EXR_DATABASE, "Not an EXReader library or unsupported schema version");
      exr_library_close(l);
      return EXR_DATABASE;
    }
  }
  if (schema_execute(l, schema) != SQLITE_OK) {
    database_error(l, e);
    sqlite3_exec(l->db, "ROLLBACK", NULL, NULL, NULL);
    exr_library_close(l);
    return EXR_DATABASE;
  }
  *out = l;
  return EXR_OK;
}
exr_status exr_library_open(const char *path,exr_library **out,exr_error *e) {
  return library_open(path,out,e,0);
}
exr_status exr_library_migration_open(const char *path,exr_library **out,exr_error *e) {
  return library_open(path,out,e,1);
}
exr_status exr_library_migration_finish(exr_library *l,int commit,exr_error *e) {
  int rc;
  if(!l || !l->migration_transaction) return exr_fail(e,EXR_ARGUMENT,"No migration transaction");
  rc=sqlite3_exec(l->db,commit ? "COMMIT" : "ROLLBACK",NULL,NULL,NULL);
  if(rc!=SQLITE_OK) return database_error(l,e);
  l->migration_transaction=0;return exr_fail(e,EXR_OK,"");
}
exr_status exr_library_migration_ledger_set(exr_library *l,const void *data,size_t size,exr_error *e) {
  sqlite3_stmt *s=NULL;exr_status status;
  if(!l || !l->migration_transaction || !data || !size || size>256u*1024u*1024u)
    return exr_fail(e,EXR_ARGUMENT,"Invalid migration ledger or transaction");
  if(sqlite3_exec(l->db,"CREATE TABLE IF NOT EXISTS exr_migration_ledger(id INTEGER PRIMARY KEY CHECK(id=1),data BLOB NOT NULL)",NULL,NULL,NULL)!=SQLITE_OK)
    return database_error(l,e);
  if(!prepare(l,"INSERT INTO exr_migration_ledger(id,data) VALUES(1,?1) ON CONFLICT(id) DO UPDATE SET data=excluded.data",&s) ||
     sqlite3_bind_blob(s,1,data,(int)size,SQLITE_TRANSIENT)!=SQLITE_OK) { sqlite3_finalize(s);return database_error(l,e); }
  status=done(l,s,e);return status==EXR_OK ? exr_fail(e,EXR_OK,"") : status;
}
exr_status exr_library_migration_ledger_get(exr_library *l,void **data,size_t *size,int *found,exr_error *e) {
  sqlite3_stmt *s=NULL;int step,n;void *copy;
  if(data) *data=NULL;
  if(size) *size=0;
  if(found) *found=0;
  if(!l || !data || !size || !found) return exr_fail(e,EXR_ARGUMENT,"Invalid migration ledger output");
  if(scalar(l->db,"SELECT count(*) FROM sqlite_master WHERE type='table' AND name='exr_migration_ledger'")==0)
    return exr_fail(e,EXR_OK,"");
  if(!prepare(l,"SELECT data FROM exr_migration_ledger WHERE id=1",&s)) return database_error(l,e);
  step=sqlite3_step(s);
  if(step==SQLITE_DONE) { sqlite3_finalize(s);return exr_fail(e,EXR_OK,""); }
  if(step!=SQLITE_ROW || sqlite3_column_type(s,0)!=SQLITE_BLOB || (n=sqlite3_column_bytes(s,0))<=0 || n>256*1024*1024) {
    sqlite3_finalize(s);return exr_fail(e,EXR_DATABASE,"Invalid migration ledger");
  }
  copy=malloc((size_t)n);if(!copy) { sqlite3_finalize(s);return exr_fail(e,EXR_MEMORY,"Ledger allocation failed"); }
  memcpy(copy,sqlite3_column_blob(s,0),(size_t)n);sqlite3_finalize(s);
  *data=copy;*size=(size_t)n;*found=1;return exr_fail(e,EXR_OK,"");
}
static void library_release(exr_library *l) {
  if (l) {
    sqlite3 *db=l->db;
    sqlite3_mutex *mutex=db ? sqlite3_db_mutex(db) : NULL;
    int last;
    sqlite3_mutex_enter(mutex);
    last=!--l->references;
    sqlite3_mutex_leave(mutex);
    if(last) { if(db) sqlite3_close_v2(db);free(l); }
  }
}
void exr_library_close(exr_library *l) {
  if (l && l->migration_transaction) {
    sqlite3_mutex *mutex=sqlite3_db_mutex(l->db);
    sqlite3_mutex_enter(mutex);
    if(sqlite3_exec(l->db,"ROLLBACK",NULL,NULL,NULL)==SQLITE_OK)
      l->migration_transaction=0;
    sqlite3_mutex_leave(mutex);
  }
  library_release(l);
}

/* Originals are immutable through this API. Each read holds the owner's mutex
   only for its blob cursor, so progress/metadata writes cannot expire a cursor
   between calls. The source retains the owner, including in-memory databases. */
struct library_source {
  exr_library *owner;
  library_source *next;
  int64_t id;
  uint64_t size;
  int version,valid;
};
static size_t library_source_read(void *context,uint64_t offset,void *buffer,size_t size) {
  library_source *source=context;sqlite3_blob *blob=NULL;sqlite3_mutex *mutex;size_t result=0;
  if(!source || !buffer || !size) return 0;
  mutex=sqlite3_db_mutex(source->owner->db);sqlite3_mutex_enter(mutex);
  if(!source->valid || offset>source->size || size>source->size-offset ||
     offset>INT_MAX || size>INT_MAX) goto finish;
  if(scalar(source->owner->db,"PRAGMA data_version")!=source->version) {
    source->valid=0;goto finish;
  }
  if(sqlite3_blob_open(source->owner->db,"main","books","source",source->id,0,&blob)!=SQLITE_OK ||
     (uint64_t)sqlite3_blob_bytes(blob)!=source->size ||
     sqlite3_blob_read(blob,buffer,(int)size,(int)offset)!=SQLITE_OK) {
    source->valid=0;goto finish;
  }
  result=size;
finish:
  if(blob) sqlite3_blob_close(blob);
  if(result && scalar(source->owner->db,"PRAGMA data_version")!=source->version) {
    source->valid=0;result=0;
  }
  sqlite3_mutex_leave(mutex);return result;
}
static void library_source_release(void *context) {
  library_source *source=context,**at;exr_library *owner;sqlite3_mutex *mutex;
  if(!source) return;
  owner=source->owner;mutex=sqlite3_db_mutex(owner->db);sqlite3_mutex_enter(mutex);
  for(at=&owner->sources;*at && *at!=source;at=&(*at)->next) {}
  if(*at) *at=source->next;
  sqlite3_mutex_leave(mutex);free(source);library_release(owner);
}
exr_status exr_library_source(exr_library *l,int64_t id,exr_source *out,exr_error *e) {
  sqlite3_stmt *statement=NULL;library_source *source=NULL;sqlite3_mutex *mutex;
  exr_status status=EXR_OK;int step,version;sqlite3_int64 size;
  const unsigned char *storage;
  if(out) memset(out,0,sizeof(*out));
  if(!l || id<=0 || !out) return exr_fail(e,EXR_ARGUMENT,"Invalid stored source lookup");
  mutex=sqlite3_db_mutex(l->db);sqlite3_mutex_enter(mutex);
  version=scalar(l->db,"PRAGMA data_version");
  if(version<0 || !prepare(l,"SELECT length(source),typeof(source) FROM books WHERE id=?1",&statement) ||
     sqlite3_bind_int64(statement,1,id)!=SQLITE_OK) { status=database_error(l,e);goto finish; }
  step=sqlite3_step(statement);
  if(step!=SQLITE_ROW) {
    status=step==SQLITE_DONE ? exr_fail(e,EXR_ARGUMENT,"Book missing") : database_error(l,e);goto finish;
  }
  size=sqlite3_column_int64(statement,0);
  storage=sqlite3_column_text(statement,1);
  if(sqlite3_column_type(statement,0)!=SQLITE_INTEGER || size<=0 ||
     !storage || strcmp((const char *)storage,"blob")) {
    status=exr_fail(e,EXR_DATABASE,"Invalid stored source");goto finish;
  }
  if(size>INT_MAX || l->references==SIZE_MAX) {
    status=exr_fail(e,EXR_LIMIT,"Stored source exceeds supported size");goto finish;
  }
  sqlite3_finalize(statement);statement=NULL;
  if(scalar(l->db,"PRAGMA data_version")!=version) {
    status=exr_fail(e,EXR_DATABASE,"Library changed while opening source");goto finish;
  }
  source=calloc(1,sizeof(*source));
  if(!source) { status=exr_fail(e,EXR_MEMORY,"Stored source allocation failed");goto finish; }
  source->owner=l;source->id=id;source->size=(uint64_t)size;source->version=version;source->valid=1;
  source->next=l->sources;l->sources=source;l->references++;
  out->size=source->size;out->context=source;out->read_at=library_source_read;out->release=library_source_release;
finish:
  sqlite3_finalize(statement);sqlite3_mutex_leave(mutex);
  return status==EXR_OK ? exr_fail(e,EXR_OK,"") : status;
}
static exr_status import_cover(const exr_document *doc,void **data,size_t *size,exr_error *e) {
  size_t i; *data=NULL; *size=0;
  for(i=0;i<doc->resource_count;i++) {
    const char *p=doc->resources[i].properties;
    while(p && *p) {
      size_t length;
      p+=strspn(p," \t\r\n"); length=strcspn(p," \t\r\n");
      if(length==11 && !memcmp(p,"cover-image",11)) {
        exr_status status=exr_document_resource(doc,i,data,size,e);
        if(status!=EXR_OK) return status;
        /* A large original stays in source; the quick-access cover column is bounded. */
        if(*size>8*1024*1024) { free(*data); *data=NULL; *size=0; }
        return EXR_OK;
      }
      p+=length;
    }
  }
  return EXR_OK;
}
exr_status exr_library_import(exr_library *l, exr_format format, const void *data, size_t n,
                              const char *title, int64_t *id, exr_error *e) {
  sqlite3_stmt *s = NULL;
  exr_document *d = NULL; exr_fixed_document *fixed=NULL; size_t extent=0;
  exr_metadata_entry *metadata=NULL; size_t metadata_count=0,i;
  const char *source_title="",*source_author=""; exr_buffer authors={0};
  exr_status result;
  void *cover=NULL; size_t cover_size=0;
  if (!l || !id)
    return exr_fail(e, EXR_ARGUMENT, "Invalid import arguments");
  *id = 0;
  if(exr_format_is_fixed(format)) {
    result=open_fixed(format,data,n,NULL,&fixed,e);
    if(result==EXR_OK) { exr_fixed_pages(fixed,&extent); result=exr_fixed_load_metadata(fixed,NULL,&metadata,&metadata_count,e); }
    if(result==EXR_OK) for(i=0;i<metadata_count;i++) {
      if(!strcmp(metadata[i].key,"http://purl.org/dc/terms/title") && !source_title[0]) source_title=metadata[i].value;
      if(!strcmp(metadata[i].key,"http://purl.org/dc/terms/creator") && metadata[i].value[0]) {
        if((authors.size && !exr_append(&authors,"; ",2)) || !exr_append(&authors,metadata[i].value,strlen(metadata[i].value))) { result=exr_fail(e,EXR_MEMORY,"Book author allocation failed"); goto cleanup; }
      }
    }
  } else {
    result=exr_document_open_memory(format,data,n,&d,e);
    if(result==EXR_OK) { extent=d->size; source_title=exr_document_title(d); result=import_cover(d,&cover,&cover_size,e); }
  }
  if(result!=EXR_OK) goto cleanup;
  if(authors.data) source_author=authors.data;
  if (!prepare(l, "INSERT INTO books(format,title,text_size,source,cover,author)VALUES(?1,?2,?3,?4,?5,?6)", &s)) {
    result=database_error(l,e); goto cleanup;
  }
  if(sqlite3_bind_int(s, 1, format)!=SQLITE_OK || !bind_text(s, 2,
            title && title[0] ? title
                              : (source_title[0] ? source_title : "Untitled")) ||
     sqlite3_bind_int64(s, 3, (sqlite3_int64)extent)!=SQLITE_OK ||
     sqlite3_bind_blob(s, 4, data, (int)n, SQLITE_TRANSIENT)!=SQLITE_OK ||
     (cover ? sqlite3_bind_blob(s,5,cover,(int)cover_size,SQLITE_STATIC) : sqlite3_bind_null(s,5))!=SQLITE_OK || !bind_text(s,6,source_author)) {
    result=database_error(l,e); sqlite3_finalize(s); goto cleanup;
  }
  result = done(l, s, e);
  if (result == EXR_OK)
    *id = sqlite3_last_insert_rowid(l->db);
cleanup:
  free(authors.data); exr_metadata_free(metadata,metadata_count); free(cover); exr_document_free(d); exr_fixed_free(fixed);
  return result;
}
/* exact-byte scan, bounded by stored sources of the same size/format.
   Add a digest index only if measured library size makes this scan too costly. */
exr_status exr_library_import_unique(exr_library *l,exr_format format,const void *data,size_t n,
                                       const char *title,int64_t *id,int *created,exr_error *e) {
  sqlite3_stmt *s=NULL; exr_status status=EXR_OK; int step,transaction=0,inserted=0; int64_t found=0;
  if(id) *id=0;
  if(created) *created=0;
  if(!l || !id || !created || !data || !n || format<EXR_TXT || format>EXR_CBZ)
    return exr_fail(e,EXR_ARGUMENT,"Invalid unique import arguments");
  if(n>EXR_MAX_INPUT) return exr_fail(e,EXR_LIMIT,"Unique import exceeds source byte limit");
  sqlite3_mutex_enter(sqlite3_db_mutex(l->db));
  if(operation_begin(l)!=SQLITE_OK) { status=database_error(l,e); goto finish; }
  transaction=1;
  if(!prepare(l,"SELECT id FROM books WHERE format=?1 AND length(source)=?2 AND source=?3 ORDER BY id LIMIT 1",&s) ||
     sqlite3_bind_int(s,1,format)!=SQLITE_OK || sqlite3_bind_int64(s,2,(sqlite3_int64)n)!=SQLITE_OK || sqlite3_bind_blob(s,3,data,(int)n,SQLITE_STATIC)!=SQLITE_OK) {
    status=database_error(l,e); goto finish;
  }
  step=sqlite3_step(s);
  if(step==SQLITE_ROW) {
    if(sqlite3_column_type(s,0)!=SQLITE_INTEGER || (found=sqlite3_column_int64(s,0))<=0) { status=exr_fail(e,EXR_DATABASE,"Invalid duplicate book ID"); goto finish; }
  } else if(step!=SQLITE_DONE) { status=database_error(l,e); goto finish; }
  sqlite3_finalize(s); s=NULL;
  if(!found) { status=exr_library_import(l,format,data,n,title,&found,e); if(status!=EXR_OK) goto finish; inserted=1; }
  if(operation_commit(l)!=SQLITE_OK) { status=database_error(l,e); goto finish; }
  transaction=0; *id=found; *created=inserted;
finish:
  sqlite3_finalize(s);
  if(transaction) operation_rollback(l);
  sqlite3_mutex_leave(sqlite3_db_mutex(l->db));
  return status==EXR_OK ? exr_fail(e,EXR_OK,"") : status;
}
/* Streaming originals: the archive bytes are copied into SQLite in bounded
   chunks instead of being retained as one host/SDK blob. Only CBZ has a
   source-based fixed reader; other formats keep the in-memory API. */
#define EXR_STREAM_CHUNK ((size_t)64 * 1024)
#define EXR_STREAM_MAX (UINT64_C(2) * 1024 * 1024 * 1024 - 1)
typedef struct { sqlite3 *db; sqlite3_blob *blob; } stream_blob;
static void stream_blob_release(void *context) {
  stream_blob *b=context;if(!b) return;
  if(b->blob) sqlite3_blob_close(b->blob);
  free(b);
}
static exr_status stream_read(const exr_source *source,uint64_t offset,void *buffer,size_t size,
                              const exr_control *control,exr_error *e) {
  size_t done=0;
  if(offset>source->size || size>source->size-offset) return exr_fail(e,EXR_IO,"Streaming source ended early");
  while(done<size) {
    size_t got;
    if(exr_control_cancel(control,e)!=EXR_OK) return EXR_CANCELLED;
    got=source->read_at(source->context,offset+done,(unsigned char *)buffer+done,size-done);
    if(!got || got>size-done) return exr_fail(e,EXR_IO,"Streaming source returned an invalid read");
    done+=got;
  }
  return EXR_OK;
}
static exr_status stream_metadata(exr_format format,const exr_source *source,char **title,char **author,
                                  size_t *extent,exr_error *e) {
  *title=NULL;*author=NULL;*extent=0;
  if(format==EXR_EPUB) {
    exr_document *index=NULL;exr_status status=exr_epub_index_source(source,&index,e);
    if(status==EXR_OK) {
      const char *name=exr_document_title(index);size_t n=strlen(name);
      if(n>65536) status=exr_fail(e,EXR_LIMIT,"EPUB title exceeds 64 KiB");
      else {
        *title=exr_copy(n ? name : "Untitled",n ? n : 8);
        if(!*title) status=exr_fail(e,EXR_MEMORY,"EPUB title allocation failed");
      }
    }
    exr_document_free(index);return status;
  }
#ifdef EXR_ENABLE_PDF
  exr_fixed_open_options options={0};exr_fixed_document *doc=NULL;exr_metadata_entry *metadata=NULL;
  exr_buffer titlebuf={0},authorbuf={0};size_t count=0,i;exr_status status;
  if(format!=EXR_CBZ) return exr_fail(e,EXR_UNSUPPORTED,"Source import supports EPUB/CBZ; use file import for PDF");
  options.struct_size=sizeof(options);options.control=source->control;
  status=exr_cbz_open_source(source,"",&options,0,&doc,e);
  if(status==EXR_OK) status=exr_fixed_load_metadata(doc,&source->control,&metadata,&count,e);
  if(status==EXR_OK) exr_fixed_pages(doc,extent);
  for(i=0;status==EXR_OK && i<count;i++) {
    if(!strcmp(metadata[i].key,"http://purl.org/dc/terms/title") && !titlebuf.data && metadata[i].value[0]) {
      if(!exr_append(&titlebuf,metadata[i].value,strlen(metadata[i].value))) status=exr_fail(e,EXR_MEMORY,"Book title allocation failed");
    }
    if(!strcmp(metadata[i].key,"http://purl.org/dc/terms/creator") && metadata[i].value[0]) {
      if((authorbuf.size && !exr_append(&authorbuf,"; ",2)) || !exr_append(&authorbuf,metadata[i].value,strlen(metadata[i].value)))
        status=exr_fail(e,EXR_MEMORY,"Book author allocation failed");
    }
  }
  exr_metadata_free(metadata,count);exr_fixed_free(doc);
  if(status==EXR_OK) {
    if(!titlebuf.data) { titlebuf.data=exr_copy("Untitled",8); titlebuf.size=8; if(!titlebuf.data) status=exr_fail(e,EXR_MEMORY,"Book title allocation failed"); }
    if(status==EXR_OK) { *title=titlebuf.data;titlebuf.data=NULL; }
  }
  if(status==EXR_OK) { *author=authorbuf.data;authorbuf.data=NULL; }
  free(titlebuf.data);free(authorbuf.data);
  return status;
#else
  (void)format;(void)source;(void)title;(void)author;(void)extent;
  return exr_fail(e,EXR_UNSUPPORTED,"Streaming import requires the PDF/CBZ component");
#endif
}
static exr_status stream_compare(sqlite3 *db,int64_t id,const exr_source *source,int *equal,exr_error *e) {
  sqlite3_blob *blob=NULL;unsigned char *from_source=NULL,*from_db=NULL;uint64_t at=0;exr_status status=EXR_OK;int result;
  *equal=0;
  result=sqlite3_blob_open(db,"main","books","source",id,0,&blob);
  if(result!=SQLITE_OK) return exr_fail(e,EXR_DATABASE,"Cannot open stored source for comparison");
  if((uint64_t)sqlite3_blob_bytes(blob)!=source->size) { sqlite3_blob_close(blob);return EXR_OK; }
  from_source=malloc(EXR_STREAM_CHUNK);from_db=malloc(EXR_STREAM_CHUNK);
  if(!from_source || !from_db) status=exr_fail(e,EXR_MEMORY,"Streaming compare allocation failed");
  while(status==EXR_OK && at<source->size) {
    size_t n=(size_t)(source->size-at<EXR_STREAM_CHUNK ? source->size-at : EXR_STREAM_CHUNK);
    if(exr_control_cancel(&source->control,e)!=EXR_OK) { status=EXR_CANCELLED; break; }
    status=stream_read(source,at,from_source,n,&source->control,e); if(status!=EXR_OK) break;
    if(sqlite3_blob_read(blob,from_db,(int)n,(int)at)!=SQLITE_OK) { status=exr_fail(e,EXR_DATABASE,"Cannot read stored source for comparison"); break; }
    if(memcmp(from_source,from_db,n)) break;
    at+=n;
  }
  if(status==EXR_OK && at==source->size) *equal=1;
  free(from_source);free(from_db);sqlite3_blob_close(blob);
  return status;
}
/* The caller owns the transaction, including the EPUB storage-mode marker. */
static exr_status stream_insert(exr_library *l,exr_format format,const exr_source *source,size_t extent,
                                const char *title,const char *author,int64_t *id,exr_error *e) {
  sqlite3_stmt *s=NULL;sqlite3_blob *blob=NULL;unsigned char *buffer=NULL;uint64_t at=0;exr_status status=EXR_OK;
  *id=0;
  if(source->size>EXR_STREAM_MAX) return exr_fail(e,EXR_LIMIT,"Streaming import exceeds the 2 GiB blob-I/O limit");
  buffer=malloc(EXR_STREAM_CHUNK);if(!buffer) return exr_fail(e,EXR_MEMORY,"Streaming buffer allocation failed");
  if(!prepare(l,"INSERT INTO books(format,title,text_size,source,cover,author)VALUES(?1,?2,?3,zeroblob(?4),NULL,?5)",&s) ||
     sqlite3_bind_int(s,1,format)!=SQLITE_OK || !bind_text(s,2,title) || sqlite3_bind_int64(s,3,(sqlite3_int64)extent)!=SQLITE_OK ||
     sqlite3_bind_int64(s,4,(sqlite3_int64)source->size)!=SQLITE_OK || !bind_text(s,5,author)) {
    status=database_error(l,e);goto finish;
  }
  status=done(l,s,e);s=NULL;if(status!=EXR_OK) goto finish;
  *id=sqlite3_last_insert_rowid(l->db);
  if(sqlite3_blob_open(l->db,"main","books","source",*id,1,&blob)!=SQLITE_OK) { status=exr_fail(e,EXR_DATABASE,"Cannot open new source blob");goto finish; }
  while(status==EXR_OK && at<source->size) {
    size_t n=(size_t)(source->size-at<EXR_STREAM_CHUNK ? source->size-at : EXR_STREAM_CHUNK);
    if(exr_control_cancel(&source->control,e)!=EXR_OK) { status=EXR_CANCELLED;break; }
    status=stream_read(source,at,buffer,n,&source->control,e);if(status!=EXR_OK) break;
    if(sqlite3_blob_write(blob,buffer,(int)n,(int)at)!=SQLITE_OK) { status=exr_fail(e,EXR_DATABASE,"Cannot write stored source: %s (bytes=%d at=%d n=%d size=%llu)",sqlite3_errmsg(l->db),sqlite3_blob_bytes(blob),(int)at,(int)n,(unsigned long long)source->size);break; }
    at+=n;
  }
  if(blob) { sqlite3_blob_close(blob);blob=NULL; }
  if(status==EXR_OK) status=exr_control_cancel(&source->control,e);
  if(status==EXR_OK && format==EXR_EPUB) {
    if(!prepare(l,"INSERT INTO epub_bounded_books(book_id)VALUES(?1)",&s) ||
       sqlite3_bind_int64(s,1,*id)!=SQLITE_OK) status=database_error(l,e);
    else { status=done(l,s,e);s=NULL; }
  }
finish:
  if(blob) sqlite3_blob_close(blob);
  sqlite3_finalize(s);
  free(buffer);
  if(status!=EXR_OK) *id=0;
  return status;
}
static exr_status stream_import_values(exr_library *l,exr_format format,const exr_source *source,
                                        const char *chosen_title,const char *author,size_t extent,
                                        int unique,int64_t *id,int *created,exr_error *e) {
  exr_status status=EXR_OK;int64_t found=0;int tx=0,inserted=0;
  if(id) *id=0;
  if(created) *created=0;
  if(!l || !id || !source || !source->read_at || !source->size || format<EXR_TXT || format>EXR_CBZ)
    return exr_fail(e,EXR_ARGUMENT,"Invalid streaming import arguments");
  if(source->size>EXR_STREAM_MAX) return exr_fail(e,EXR_LIMIT,"Streaming import exceeds the 2 GiB blob-I/O limit");
  sqlite3_mutex_enter(sqlite3_db_mutex(l->db));
  if(operation_begin(l)!=SQLITE_OK) { status=database_error(l,e);goto unlock; }
  tx=1;
  if(unique) {
    sqlite3_stmt *s=NULL;int step;
    if(!prepare(l,"SELECT id FROM books WHERE format=?1 AND length(source)=?2 ORDER BY id",&s) ||
       sqlite3_bind_int(s,1,format)!=SQLITE_OK || sqlite3_bind_int64(s,2,(sqlite3_int64)source->size)!=SQLITE_OK) {
      sqlite3_finalize(s);status=database_error(l,e);goto unlock;
    }
    while((step=sqlite3_step(s))==SQLITE_ROW) {
      int64_t candidate;
      if(sqlite3_column_type(s,0)!=SQLITE_INTEGER || (candidate=sqlite3_column_int64(s,0))<=0) { sqlite3_finalize(s);status=exr_fail(e,EXR_DATABASE,"Invalid duplicate book ID");goto unlock; }
      { int equal=0;status=stream_compare(l->db,candidate,source,&equal,e);if(status!=EXR_OK) { sqlite3_finalize(s);goto unlock; }if(equal) { found=candidate;break; } }
    }
    if(step!=SQLITE_ROW && step!=SQLITE_DONE && status==EXR_OK) { sqlite3_finalize(s);status=database_error(l,e);goto unlock; }
    sqlite3_finalize(s);
  }
  if(!found) {
    status=stream_insert(l,format,source,extent,chosen_title,author?author:"",id,e);
    if(status!=EXR_OK) goto unlock;
    inserted=1;
  }
  status=exr_control_cancel(&source->control,e);if(status!=EXR_OK) goto unlock;
  if(operation_commit(l)!=SQLITE_OK) { status=database_error(l,e);goto unlock; }
  tx=0;
  *id=found?found:*id;if(created) *created=inserted;
unlock:
  if(tx && operation_rollback(l)!=SQLITE_OK && status==EXR_OK) status=database_error(l,e);
  if(status!=EXR_OK) { *id=0;if(created) *created=0; }
  sqlite3_mutex_leave(sqlite3_db_mutex(l->db));
  return status;
}
static exr_status stream_import(exr_library *l,exr_format format,const exr_source *source,const char *title,
                                int unique,int64_t *id,int *created,exr_error *e) {
  char *source_title=NULL,*author=NULL;size_t extent=0;exr_status status;
  if(id) *id=0;
  if(created) *created=0;
  if(!l || !id || !source || !source->read_at || !source->size || format<EXR_TXT || format>EXR_CBZ)
    return exr_fail(e,EXR_ARGUMENT,"Invalid streaming import arguments");
  status=stream_metadata(format,source,&source_title,&author,&extent,e);
  if(status!=EXR_OK) goto finish;
  status=stream_import_values(l,format,source,title && title[0] ? title : source_title,author,extent,unique,id,created,e);
finish:
  free(source_title);free(author);
  return status;
}
exr_status exr_library_import_source(exr_library *l,exr_format format,const exr_source *source,
                                     const char *title,int64_t *id,exr_error *e) {
  return stream_import(l,format,source,title,0,id,NULL,e);
}
exr_status exr_library_import_source_unique(exr_library *l,exr_format format,const exr_source *source,
                                            const char *title,int64_t *id,int *created,exr_error *e) {
  if(id) *id=0;
  if(!created) return exr_fail(e,EXR_ARGUMENT,"Missing created output");
  return stream_import(l,format,source,title,1,id,created,e);
}
static exr_status import_file_pdf(exr_library *l,exr_format format,const char *path,const char *title,
                                     int unique,int64_t *id,int *created,exr_error *e) {
#ifndef EXR_ENABLE_PDF
  (void)l;(void)format;(void)path;(void)title;(void)unique;(void)id;(void)created;
  return exr_fail(e,EXR_UNSUPPORTED,"PDF streaming import requires the PDF component");
#else
  exr_fixed_open_options options={0};exr_fixed_document *doc=NULL;exr_metadata_entry *metadata=NULL;
  exr_buffer source_title={0},author={0};size_t count=0,pages=0,i;exr_source source;exr_status status;
  options.struct_size=sizeof(options);
  status=exr_fixed_open(path,&options,&doc,e);
  if(status==EXR_OK) { exr_fixed_pages(doc,&pages);status=exr_fixed_load_metadata(doc,NULL,&metadata,&count,e); }
  for(i=0;status==EXR_OK && i<count;i++) {
    if(!strcmp(metadata[i].key,"http://purl.org/dc/terms/title") && !source_title.data && metadata[i].value[0]) {
      if(!exr_append(&source_title,metadata[i].value,strlen(metadata[i].value))) status=exr_fail(e,EXR_MEMORY,"Book title allocation failed");
    }
    if(!strcmp(metadata[i].key,"http://purl.org/dc/terms/creator") && metadata[i].value[0]) {
      if((author.size && !exr_append(&author,"; ",2)) || !exr_append(&author,metadata[i].value,strlen(metadata[i].value)))
        status=exr_fail(e,EXR_MEMORY,"Book author allocation failed");
    }
  }
  exr_metadata_free(metadata,count);exr_fixed_free(doc);doc=NULL;
  if(status==EXR_OK) status=exr_file_source_limit(path,EXR_STREAM_MAX,&source,e);
  if(status==EXR_OK) {
    status=stream_import_values(l,format,&source,title && title[0] ? title : (source_title.data ? source_title.data : "Untitled"),
                                author.data ? author.data : "",pages,unique,id,created,e);
    source.release(source.context);
  }
  free(source_title.data);free(author.data);
  return status;
#endif
}
exr_status exr_library_import_file(exr_library *l,exr_format format,const char *path,const char *title,
                                   int64_t *id,exr_error *e) {
  exr_source source;exr_status status;
  if(id) *id=0;
  if(!l || !id || !path) return exr_fail(e,EXR_ARGUMENT,"Invalid streaming file import arguments");
  if(format==EXR_PDF) return import_file_pdf(l,format,path,title,0,id,NULL,e);
  status=exr_file_source_limit(path,format==EXR_EPUB ? EXR_MAX_INPUT : EXR_STREAM_MAX,&source,e);
  if(status!=EXR_OK) return status;
  status=exr_library_import_source(l,format,&source,title,id,e);
  source.release(source.context);
  return status;
}
exr_status exr_library_import_file_unique(exr_library *l,exr_format format,const char *path,const char *title,
                                          int64_t *id,int *created,exr_error *e) {
  exr_source source;exr_status status;
  if(id) *id=0;
  if(created) *created=0;
  if(!l || !id || !created || !path) return exr_fail(e,EXR_ARGUMENT,"Invalid streaming unique file import arguments");
  if(format==EXR_PDF) return import_file_pdf(l,format,path,title,1,id,created,e);
  status=exr_file_source_limit(path,format==EXR_EPUB ? EXR_MAX_INPUT : EXR_STREAM_MAX,&source,e);
  if(status!=EXR_OK) return status;
  status=exr_library_import_source_unique(l,format,&source,title,id,created,e);
  source.release(source.context);
  return status;
}
exr_status exr_library_fixed_source(exr_library *l,int64_t id,const exr_fixed_open_options *input,
                                    exr_fixed_document **out,exr_error *e) {
  sqlite3_stmt *s=NULL;exr_fixed_open_options options={0};stream_blob *context=NULL;exr_source source;int step,format;int64_t length;
  if(out) *out=NULL;
  if(!l || id<=0 || !out) return exr_fail(e,EXR_ARGUMENT,"Invalid streaming fixed lookup");
#ifndef EXR_ENABLE_PDF
  (void)input;
  return exr_fail(e,EXR_UNSUPPORTED,"Streaming fixed reading requires the PDF component");
#else
  { exr_status status=exr_fixed_open_options_copy(input,&options,e);if(status!=EXR_OK) return status; }
#endif
  options.struct_size=sizeof(options);
  if(!prepare(l,"SELECT format,length(source) FROM books WHERE id=?1",&s) || sqlite3_bind_int64(s,1,id)!=SQLITE_OK) { sqlite3_finalize(s);return database_error(l,e); }
  step=sqlite3_step(s);
  if(step!=SQLITE_ROW) { sqlite3_finalize(s);return step==SQLITE_DONE ? exr_fail(e,EXR_ARGUMENT,"Book missing") : database_error(l,e); }
  format=sqlite3_column_int(s,0);
  length=sqlite3_column_int64(s,1);
  if((format!=EXR_CBZ && format!=EXR_PDF) || sqlite3_column_type(s,1)!=SQLITE_INTEGER || length<=0 || (uint64_t)length>EXR_STREAM_MAX) {
    sqlite3_finalize(s);return exr_fail(e,EXR_UNSUPPORTED,"Streaming fixed reading is available for CBZ and PDF originals");
  }
  if(format==EXR_PDF) {
    exr_mapping mapping={0};uint64_t at=0;exr_status status;
    sqlite3_finalize(s);s=NULL;
    status=exr_map_anonymous((size_t)length,&mapping,e);
    if(status!=EXR_OK) return status;
    context=calloc(1,sizeof(*context));
    if(!context) { exr_unmap(&mapping);return exr_fail(e,EXR_MEMORY,"Streaming source allocation failed"); }
    context->db=l->db;
    if(sqlite3_blob_open(l->db,"main","books","source",id,0,&context->blob)!=SQLITE_OK) { free(context);exr_unmap(&mapping);return exr_fail(e,EXR_DATABASE,"Cannot open stored source blob"); }
    while(at<(uint64_t)length) {
      size_t n=(size_t)((uint64_t)length-at<EXR_STREAM_CHUNK ? (uint64_t)length-at : EXR_STREAM_CHUNK);
      if(exr_control_cancel(&options.control,e)!=EXR_OK) { stream_blob_release(context);exr_unmap(&mapping);return EXR_CANCELLED; }
      if(sqlite3_blob_read(context->blob,(unsigned char *)mapping.address+at,(int)n,(int)at)!=SQLITE_OK) {
        stream_blob_release(context);exr_unmap(&mapping);return exr_fail(e,EXR_DATABASE,"Cannot read stored PDF source");
      }
      at+=n;
    }
    stream_blob_release(context);
    return exr_fixed_open_mapped(EXR_PDF,&mapping,&options,out,e);
  }
  sqlite3_finalize(s);
  { exr_status status=exr_library_source(l,id,&source,e);if(status!=EXR_OK) return status; }
  return exr_cbz_open_source(&source,"",&options,1,out,e);
}

void exr_books_free(exr_book *books, size_t n) {
  size_t i;
  for (i = 0; i < n; i++) {
    free(books[i].title);
    free(books[i].author);
    free(books[i].tags);
  }
  free(books);
}
exr_status exr_library_books(exr_library *l, const char *query, exr_book **out, size_t *count,
                             exr_error *e) {
  sqlite3_stmt *s = NULL;
  exr_book *books = NULL;
  size_t n = 0, cap = 0, i;
  int result;
  exr_buffer pattern = {0};
  if (!l || !out || !count)
    return exr_fail(e, EXR_ARGUMENT, "Invalid query arguments");
  *out = NULL;
  *count = 0;
  if (!query)
    query = "";
  if (strlen(query) > 4096)
    return exr_fail(e, EXR_LIMIT, "Search query too long");
  if (!exr_append(&pattern, "%", 1))
    goto memory;
  for (i = 0; query[i]; i++) {
    if (strchr("%_!", query[i]) && !exr_append(&pattern, "!", 1))
      goto memory;
    if (!exr_append(&pattern, query + i, 1))
      goto memory;
  }
  if (!exr_append(&pattern, "%", 1))
    goto memory;
  if (!prepare(l,
               "SELECT id,format,title,author,tags,favorite,status,position "
               "FROM books WHERE title LIKE ?1 ESCAPE '!' OR author LIKE ?1 "
               "ESCAPE '!' OR tags LIKE ?1 ESCAPE '!' ORDER BY id DESC",
               &s))
    goto database;
  bind_text(s, 1, pattern.data);
  free(pattern.data);
  pattern.data = NULL;
  while ((result = sqlite3_step(s)) == SQLITE_ROW) {
    exr_book *b;
    if (n >= EXR_MAX_ITEMS || !exr_grow((void **)&books, &cap, n + 1, sizeof(*b)))
      goto memory;
    b = &books[n++];
    memset(b, 0, sizeof(*b));
    b->id = sqlite3_column_int64(s, 0);
    b->format = (exr_format)sqlite3_column_int(s, 1);
    b->title =
        exr_copy((const char *)sqlite3_column_text(s, 2), (size_t)sqlite3_column_bytes(s, 2));
    b->author =
        exr_copy((const char *)sqlite3_column_text(s, 3), (size_t)sqlite3_column_bytes(s, 3));
    b->tags = exr_copy((const char *)sqlite3_column_text(s, 4), (size_t)sqlite3_column_bytes(s, 4));
    b->favorite = sqlite3_column_int(s, 5);
    b->status = sqlite3_column_int(s, 6);
    b->position = (size_t)sqlite3_column_int64(s, 7);
    if (!b->title || !b->author || !b->tags)
      goto memory;
  }
  if (result != SQLITE_DONE)
    goto database;
  sqlite3_finalize(s);
  *out = books;
  *count = n;
  return EXR_OK;
memory:
  if (s)
    sqlite3_finalize(s);
  free(pattern.data);
  exr_books_free(books, n);
  return exr_fail(e, EXR_MEMORY, "Library result allocation failed");
database:
  if (s)
    sqlite3_finalize(s);
  free(pattern.data);
  exr_books_free(books, n);
  return database_error(l, e);
}
exr_status exr_library_update(exr_library *l, const exr_book *b, exr_error *e) {
  sqlite3_stmt *s = NULL;
  exr_status result;int format,bounded;
  if (!l || !b || b->id <= 0 || !b->title || !b->title[0] || b->position > INT64_MAX ||
      (b->favorite != 0 && b->favorite != 1) || b->status < 0 || b->status > 2)
    return exr_fail(e, EXR_ARGUMENT, "Invalid metadata or position");
  result=book_storage(l,b->id,&format,&bounded,1,e);if(result!=EXR_OK) return result;
  if(bounded && b->position) return exr_fail(e,EXR_UNSUPPORTED,"Bounded EPUB position is chapter-local");
  if (!prepare(l,
               "UPDATE books SET "
               "title=?1,author=?2,tags=?3,favorite=?4,status=?5,position=?6 "
               "WHERE id=?7 AND ?6<=text_size",
               &s))
    return database_error(l, e);
  bind_text(s, 1, b->title);
  bind_text(s, 2, b->author);
  bind_text(s, 3, b->tags);
  sqlite3_bind_int(s, 4, b->favorite);
  sqlite3_bind_int(s, 5, b->status);
  sqlite3_bind_int64(s, 6, (sqlite3_int64)b->position);
  sqlite3_bind_int64(s, 7, b->id);
  result = done(l, s, e);
  if (result == EXR_OK && !sqlite3_changes(l->db))
    return exr_fail(e, EXR_ARGUMENT, "Book missing or position outside text");
  return result;
}
exr_status exr_library_blob(exr_library *l, int64_t id, int cover, void **data, size_t *n,
                            exr_error *e) {
  sqlite3_stmt *s = NULL;
  const void *p;
  size_t size;
  void *copy;
  int result;
  if (!l || id <= 0 || !data || !n)
    return exr_fail(e, EXR_ARGUMENT, "Invalid blob arguments");
  *data = NULL;
  *n = 0;
  if (!prepare(
          l, cover ? "SELECT cover FROM books WHERE id=?1" : "SELECT source FROM books WHERE id=?1",
          &s))
    return database_error(l, e);
  sqlite3_bind_int64(s, 1, id);
  result = sqlite3_step(s);
  if (result != SQLITE_ROW) {
    sqlite3_finalize(s);
    return result == SQLITE_DONE ? exr_fail(e, EXR_ARGUMENT, "Book missing") : database_error(l, e);
  }
  p = sqlite3_column_blob(s, 0);
  size = (size_t)sqlite3_column_bytes(s, 0);
  if (!size) {
    sqlite3_finalize(s);
    return EXR_OK;
  }
  if (size > EXR_MAX_INPUT) {
    sqlite3_finalize(s);
    return exr_fail(e, EXR_LIMIT, "Stored blob exceeds limit");
  }
  copy = malloc(size);
  if (!copy) {
    sqlite3_finalize(s);
    return exr_fail(e, EXR_MEMORY, "Blob allocation failed");
  }
  memcpy(copy, p, size);
  sqlite3_finalize(s);
  *data = copy;
  *n = size;
  return EXR_OK;
}
exr_status exr_library_document(exr_library *l, int64_t id, exr_document **doc, exr_error *e) {
  sqlite3_stmt *s = NULL;
  exr_status result;
  if (!l || id <= 0 || !doc)
    return exr_fail(e, EXR_ARGUMENT, "Invalid document lookup");
  *doc = NULL;
  if (!prepare(l, "SELECT format,source FROM books WHERE id=?1", &s))
    return database_error(l, e);
  sqlite3_bind_int64(s, 1, id);
  if (sqlite3_step(s) != SQLITE_ROW) {
    sqlite3_finalize(s);
    return exr_fail(e, EXR_ARGUMENT, "Book missing");
  }
  result = exr_document_open_memory((exr_format)sqlite3_column_int(s, 0), sqlite3_column_blob(s, 1),
                                    (size_t)sqlite3_column_bytes(s, 1), doc, e);
  sqlite3_finalize(s);
  return result;
}
exr_status exr_library_fixed(exr_library *l,int64_t id,const exr_fixed_open_options *options,exr_fixed_document **out,exr_error *e) {
  sqlite3_stmt *s=NULL; exr_status status; int step;
  if(out) *out=NULL;
  if(!l || id<=0 || !out) return exr_fail(e,EXR_ARGUMENT,"Invalid fixed document lookup");
  if(!prepare(l,"SELECT format,source FROM books WHERE id=?1",&s)) return database_error(l,e);
  if(sqlite3_bind_int64(s,1,id)!=SQLITE_OK) { sqlite3_finalize(s); return database_error(l,e); }
  step=sqlite3_step(s);
  if(step!=SQLITE_ROW) { sqlite3_finalize(s); return step==SQLITE_DONE ? exr_fail(e,EXR_ARGUMENT,"Book missing") : database_error(l,e); }
  if(sqlite3_column_type(s,0)!=SQLITE_INTEGER || sqlite3_column_type(s,1)!=SQLITE_BLOB) status=exr_fail(e,EXR_DATABASE,"Invalid stored fixed document");
  else status=open_fixed((exr_format)sqlite3_column_int(s,0),sqlite3_column_blob(s,1),(size_t)sqlite3_column_bytes(s,1),options,out,e);
  sqlite3_finalize(s); return status;
}
exr_status exr_library_cover(exr_library *l, int64_t id, const void *data, size_t n, exr_error *e) {
  sqlite3_stmt *s = NULL;
  exr_status result;
  if (!l || id <= 0 || (!data && n) || n > 8 * 1024 * 1024)
    return exr_fail(e, EXR_ARGUMENT, "Invalid cover or cover exceeds 8 MiB");
  if (!prepare(l, "UPDATE books SET cover=?1 WHERE id=?2", &s))
    return database_error(l, e);
  sqlite3_bind_blob(s, 1, data, (int)n, SQLITE_TRANSIENT);
  sqlite3_bind_int64(s, 2, id);
  result = done(l, s, e);
  if (result == EXR_OK && !sqlite3_changes(l->db))
    return exr_fail(e, EXR_ARGUMENT, "Book missing");
  return result;
}
/* SQLite values are checked before casts so damaged databases cannot wrap offsets. */
static int offset_column(sqlite3_stmt *s, int column, size_t *out) {
  sqlite3_int64 value;
  if (sqlite3_column_type(s, column) != SQLITE_INTEGER)
    return 0;
  value = sqlite3_column_int64(s, column);
  if (value < 0 || (uint64_t)value > SIZE_MAX)
    return 0;
  *out = (size_t)value;
  return 1;
}
static exr_status annotation_input(const char *text,exr_error *e) {
  size_t n=0,at=0; uint32_t cp;
  if(!text) return exr_fail(e,EXR_ARGUMENT,"Missing annotation text");
  while(n<=EXR_MAX_TEXT && text[n]) n++;
  if(n>EXR_MAX_TEXT) return exr_fail(e,EXR_LIMIT,"Annotation text exceeds 64 MiB");
  while(at<n) if(!exr_next(text,n,&at,&cp)) return exr_fail(e,EXR_ENCODING,"Annotation text is not UTF-8");
  return EXR_OK;
}
static exr_status annotation_column(sqlite3_stmt *s, int column, int nullable, char **out,
                                    exr_error *e) {
  const char *text;
  size_t limit = column == 5 ? 65536 : (column == 6 || column == 7) ? 128
                                      : column == 8 ? 2046 : EXR_MAX_TEXT;
  int bytes, type = sqlite3_column_type(s, column);
  *out = NULL;
  if (nullable && type == SQLITE_NULL)
    return EXR_OK;
  if (type != SQLITE_TEXT)
    return exr_fail(e, EXR_DATABASE, "Invalid stored annotation text type");
  text = (const char *)sqlite3_column_text(s, column);
  bytes = sqlite3_column_bytes(s, column);
  if (!text)
    return exr_fail(e, EXR_MEMORY, "Annotation allocation failed");
  if ((size_t)bytes > limit || memchr(text, 0, (size_t)bytes))
    return exr_fail(e, EXR_DATABASE, "Invalid stored annotation text");
  { size_t at=0; uint32_t cp; while(at<(size_t)bytes) if(!exr_next(text,(size_t)bytes,&at,&cp)) return exr_fail(e,EXR_DATABASE,"Invalid stored annotation UTF-8"); }
  *out = exr_copy(text, (size_t)bytes);
  return *out ? EXR_OK : exr_fail(e, EXR_MEMORY, "Annotation allocation failed");
}
/* Columns: id, book_id, start, end, text, four selectors, book text_size, location_state. */
static exr_status read_note(sqlite3_stmt *s, exr_note *note, exr_error *e) {
  exr_error validation;
  exr_status result;
  size_t text_size; int location;
  memset(note, 0, sizeof(*note));
  if (sqlite3_column_type(s, 0) != SQLITE_INTEGER ||
      sqlite3_column_type(s, 1) != SQLITE_INTEGER ||
      (note->id = sqlite3_column_int64(s, 0)) <= 0 ||
      (note->book_id = sqlite3_column_int64(s, 1)) <= 0 ||
      !offset_column(s, 2, &note->start) || !offset_column(s, 3, &note->end) ||
      !offset_column(s, 9, &text_size) || text_size > EXR_MAX_TEXT ||
      sqlite3_column_type(s,10)!=SQLITE_INTEGER || (location=sqlite3_column_int(s,10))<0 || location>EXR_ANCHOR_LEGACY ||
      note->start > note->end || note->end>EXR_MAX_TEXT || (location==EXR_ANCHOR_FOUND && note->end > text_size))
    return exr_fail(e, EXR_DATABASE, "Invalid stored annotation range");
  note->anchor.start = note->start;
  note->anchor.end = note->end;
  result = annotation_column(s, 4, 0, &note->text, e);
  if (result == EXR_OK)
    result = annotation_column(s, 5, 1, &note->anchor.exact, e);
  if (result == EXR_OK)
    result = annotation_column(s, 6, 1, &note->anchor.prefix, e);
  if (result == EXR_OK)
    result = annotation_column(s, 7, 1, &note->anchor.suffix, e);
  if (result == EXR_OK)
    result = annotation_column(s, 8, 1, &note->anchor.chapter, e);
  if (result != EXR_OK)
    return result;
  if ((!note->anchor.exact &&
       (note->anchor.prefix || note->anchor.suffix || note->anchor.chapter)) ||
      exr_anchor_validate(&note->anchor, &validation) != EXR_OK)
    return exr_fail(e, EXR_DATABASE, "Invalid stored annotation selector");
  if(location!=EXR_ANCHOR_FOUND) note->start=note->end=SIZE_MAX;
  return EXR_OK;
}
static int bind_nullable_text(sqlite3_stmt *s, int column, const char *text) {
  return text ? bind_text(s, column, text) : sqlite3_bind_null(s, column) == SQLITE_OK;
}
exr_status exr_library_epub_info_get(exr_library *l,int64_t id,exr_library_epub_info *out,exr_error *e) {
  int format=0,bounded=0;exr_status status;sqlite3_mutex *mutex;
  if(!out || out->struct_size<sizeof(*out))
    return exr_fail(e,EXR_ARGUMENT,"EPUB storage info record is too small");
  if(out) { out->bounded_storage=0;out->global_extent_known=0; }
  if(!l || id<=0)
    return exr_fail(e,EXR_ARGUMENT,"Invalid EPUB storage info query");
  mutex=sqlite3_db_mutex(l->db);sqlite3_mutex_enter(mutex);
  status=book_storage(l,id,&format,&bounded,0,e);
  if(status==EXR_OK && format!=EXR_EPUB) status=exr_fail(e,EXR_FORMAT,"Book is not EPUB");
  if(status==EXR_OK) { out->bounded_storage=bounded;out->global_extent_known=!bounded;status=exr_fail(e,EXR_OK,""); }
  sqlite3_mutex_leave(mutex);return status;
}
void exr_epub_location_free(exr_epub_location *location) {
  if(!location) return;
  free(location->path);exr_anchor_free(&location->selector);memset(location,0,sizeof(*location));
}
static exr_status epub_location_validate(const exr_epub_location *location,int point,exr_error *e) {
  size_t n=0,at=0;uint32_t cp;exr_status status;
  if(!location || location->part>=10000 || !location->path || !location->selector.exact ||
     location->selector.start>location->selector.end || location->selector.end==SIZE_MAX || location->selector.end>INT64_MAX ||
     (point ? (location->selector.exact[0] || location->selector.start!=location->selector.end) :
              (!location->selector.exact[0] || location->selector.start==location->selector.end)))
    return exr_fail(e,EXR_ARGUMENT,"Invalid chapter-local EPUB selector range");
  while(n<=2046 && location->path[n]) n++;
  if(n>2046) return exr_fail(e,EXR_LIMIT,"EPUB part path exceeds its size limit");
  while(at<n) if(!exr_next(location->path,n,&at,&cp)) return exr_fail(e,EXR_ENCODING,"EPUB part path is not UTF-8");
  /* This is the already-decoded package path, not a URI to decode again.
     Exact comparison against the package below supplies canonical validation. */
  if(!n) return exr_fail(e,EXR_ARGUMENT,"Missing EPUB part path");
  status=exr_anchor_validate(&location->selector,e);if(status!=EXR_OK) return status;
  if(location->selector.chapter && strcmp(location->selector.chapter,location->path))
    return exr_fail(e,EXR_ARGUMENT,"EPUB selector chapter differs from its part path");
  return EXR_OK;
}
/* Package-only validation. The index borrows this temporary source; no body
   load, layout dependency, or ownership transfer is needed. */
static exr_status epub_stored_route(exr_library *l,int64_t id,size_t part,const char *path,exr_error *e) {
  exr_source source={0};exr_document *index=NULL;exr_status status;
  status=exr_library_source(l,id,&source,e);if(status!=EXR_OK) return status;
  status=exr_epub_index_source(&source,&index,e);
  if(status==EXR_OK && (part>=index->chapter_count || strcmp(index->chapters[part].path,path)))
    status=exr_fail(e,EXR_ARGUMENT,"EPUB part and path do not match its package");
  exr_document_free(index);source.release(source.context);return status;
}
exr_status exr_library_epub_progress(exr_library *l,int64_t id,const exr_epub_location *location,exr_error *e) {
  sqlite3_stmt *s=NULL;sqlite3_mutex *mutex;int format=0,bounded=0,transaction=0;exr_status status;
  if(!l || id<=0) return exr_fail(e,EXR_ARGUMENT,"Invalid EPUB progress arguments");
  status=epub_location_validate(location,1,e);if(status!=EXR_OK) return status;
  mutex=sqlite3_db_mutex(l->db);sqlite3_mutex_enter(mutex);
  if(operation_begin(l)!=SQLITE_OK) { status=database_error(l,e);goto finish; }
  transaction=1;
  status=book_storage(l,id,&format,&bounded,0,e);if(status!=EXR_OK) goto finish;
  if(format!=EXR_EPUB) { status=exr_fail(e,EXR_FORMAT,"Book is not EPUB");goto finish; }
  status=epub_stored_route(l,id,location->part,location->path,e);if(status!=EXR_OK) goto finish;
  if(!prepare(l,"INSERT INTO epub_progress(book_id,part,path,position,prefix,suffix,chapter)"
                "VALUES(?1,?2,?3,?4,?5,?6,?7) ON CONFLICT(book_id) DO UPDATE SET "
                "part=excluded.part,path=excluded.path,position=excluded.position,"
                "prefix=excluded.prefix,suffix=excluded.suffix,chapter=excluded.chapter",&s) ||
     sqlite3_bind_int64(s,1,id)!=SQLITE_OK || sqlite3_bind_int64(s,2,(sqlite3_int64)location->part)!=SQLITE_OK ||
     !bind_text(s,3,location->path) || sqlite3_bind_int64(s,4,(sqlite3_int64)location->selector.start)!=SQLITE_OK ||
     !bind_nullable_text(s,5,location->selector.prefix) || !bind_nullable_text(s,6,location->selector.suffix) ||
     !bind_nullable_text(s,7,location->selector.chapter)) { status=database_error(l,e);goto finish; }
  status=done(l,s,e);s=NULL;if(status!=EXR_OK) goto finish;
  if(operation_commit(l)!=SQLITE_OK) { status=database_error(l,e);goto finish; }
  transaction=0;status=exr_fail(e,EXR_OK,"");
finish:
  sqlite3_finalize(s);if(transaction) operation_rollback(l);
  sqlite3_mutex_leave(mutex);return status;
}
static exr_status epub_text_column(sqlite3_stmt *s,int column,size_t limit,int nullable,char **out,exr_error *e) {
  const char *text;int n,type=sqlite3_column_type(s,column);size_t at=0;uint32_t cp;
  *out=NULL;if(nullable && type==SQLITE_NULL) return EXR_OK;
  if(type!=SQLITE_TEXT) return exr_fail(e,EXR_DATABASE,"Invalid stored EPUB selector type");
  text=(const char *)sqlite3_column_text(s,column);n=sqlite3_column_bytes(s,column);
  if(!text) return exr_fail(e,EXR_MEMORY,"Stored EPUB selector allocation failed");
  if((size_t)n>limit || memchr(text,0,(size_t)n)) return exr_fail(e,EXR_DATABASE,"Invalid stored EPUB selector length");
  while(at<(size_t)n) if(!exr_next(text,(size_t)n,&at,&cp)) return exr_fail(e,EXR_DATABASE,"Invalid stored EPUB selector UTF-8");
  *out=exr_copy(text,(size_t)n);return *out ? EXR_OK : exr_fail(e,EXR_MEMORY,"EPUB selector allocation failed");
}
exr_status exr_library_epub_progress_get(exr_library *l,int64_t id,exr_epub_location *out,int *present,exr_error *e) {
  exr_epub_location location={0};exr_error validation={0};sqlite3_stmt *s=NULL;sqlite3_mutex *mutex;
  int format=0,bounded=0,step;exr_status status;
  if(out) memset(out,0,sizeof(*out));
  if(present) *present=0;
  if(!l || id<=0 || !out || !present) return exr_fail(e,EXR_ARGUMENT,"Invalid EPUB progress query");
  mutex=sqlite3_db_mutex(l->db);sqlite3_mutex_enter(mutex);
  status=book_storage(l,id,&format,&bounded,0,e);if(status!=EXR_OK) goto finish;
  if(format!=EXR_EPUB) { status=exr_fail(e,EXR_FORMAT,"Book is not EPUB");goto finish; }
  if(!prepare(l,"SELECT part,path,position,prefix,suffix,chapter FROM epub_progress WHERE book_id=?1",&s) ||
     sqlite3_bind_int64(s,1,id)!=SQLITE_OK) { status=database_error(l,e);goto finish; }
  step=sqlite3_step(s);
  if(step!=SQLITE_ROW) { status=step==SQLITE_DONE ? exr_fail(e,EXR_OK,"") : database_error(l,e);goto finish; }
  if(!offset_column(s,0,&location.part) || !offset_column(s,2,&location.selector.start)) {
    status=exr_fail(e,EXR_DATABASE,"Invalid stored EPUB position");goto finish;
  }
  location.selector.end=location.selector.start;
  location.selector.exact=exr_copy("",0);
  if(!location.selector.exact) { status=exr_fail(e,EXR_MEMORY,"EPUB point allocation failed");goto finish; }
  status=epub_text_column(s,1,2046,0,&location.path,e);
  if(status==EXR_OK) status=epub_text_column(s,3,128,1,&location.selector.prefix,e);
  if(status==EXR_OK) status=epub_text_column(s,4,128,1,&location.selector.suffix,e);
  if(status==EXR_OK) status=epub_text_column(s,5,2046,1,&location.selector.chapter,e);
  if(status!=EXR_OK) goto finish;
  if(epub_location_validate(&location,1,&validation)!=EXR_OK) {
    status=exr_fail(e,EXR_DATABASE,"Invalid stored chapter-local EPUB selector");goto finish;
  }
  sqlite3_finalize(s);s=NULL;
  status=epub_stored_route(l,id,location.part,location.path,e);
  if(status==EXR_ARGUMENT) status=exr_fail(e,EXR_DATABASE,"Stored EPUB route differs from its package");
  if(status!=EXR_OK) goto finish;
  *out=location;memset(&location,0,sizeof(location));*present=1;status=exr_fail(e,EXR_OK,"");
finish:
  sqlite3_finalize(s);exr_epub_location_free(&location);sqlite3_mutex_leave(mutex);return status;
}
exr_status exr_library_epub_note(exr_library *l,const exr_epub_note *input,int64_t *id,exr_error *e) {
  exr_epub_note note;sqlite3_stmt *s=NULL;sqlite3_mutex *mutex;exr_status status;
  int format=0,bounded=0,transaction=0,comment_only;int64_t saved=0;
  if(input) note=*input;
  if(id) *id=0;
  if(!l || !input || !id || note.id<0 || note.book_id<=0 || !note.text)
    return exr_fail(e,EXR_ARGUMENT,"Invalid chapter-local EPUB note");
  comment_only=note.location.selector.exact==NULL;
  if(comment_only && !note.id) return exr_fail(e,EXR_ARGUMENT,"New EPUB note requires an explicit quote");
  status=annotation_input(note.text,e);if(status!=EXR_OK) return status;
  if(!comment_only) { status=epub_location_validate(&note.location,0,e);if(status!=EXR_OK) return status; }
  mutex=sqlite3_db_mutex(l->db);sqlite3_mutex_enter(mutex);
  if(operation_begin(l)!=SQLITE_OK) { status=database_error(l,e);goto finish; }
  transaction=1;
  status=book_storage(l,note.book_id,&format,&bounded,0,e);if(status!=EXR_OK) goto finish;
  if(format!=EXR_EPUB) { status=exr_fail(e,EXR_FORMAT,"Book is not EPUB");goto finish; }
  if(comment_only) {
    if(!prepare(l,"UPDATE epub_notes SET text=?1 WHERE id=?2 AND book_id=?3",&s) ||
       !bind_text(s,1,note.text) || sqlite3_bind_int64(s,2,note.id)!=SQLITE_OK ||
       sqlite3_bind_int64(s,3,note.book_id)!=SQLITE_OK) { status=database_error(l,e);goto finish; }
  } else {
    status=epub_stored_route(l,note.book_id,note.location.part,note.location.path,e);if(status!=EXR_OK) goto finish;
    if(!prepare(l,note.id ?
      "UPDATE epub_notes SET part=?2,path=?3,start=?4,end=?5,exact=?6,prefix=?7,suffix=?8,chapter=?9,text=?10 WHERE book_id=?1 AND id=?11" :
      "INSERT INTO epub_notes(book_id,part,path,start,end,exact,prefix,suffix,chapter,text)VALUES(?1,?2,?3,?4,?5,?6,?7,?8,?9,?10)",&s) ||
       sqlite3_bind_int64(s,1,note.book_id)!=SQLITE_OK || sqlite3_bind_int64(s,2,(sqlite3_int64)note.location.part)!=SQLITE_OK ||
       !bind_text(s,3,note.location.path) || sqlite3_bind_int64(s,4,(sqlite3_int64)note.location.selector.start)!=SQLITE_OK ||
       sqlite3_bind_int64(s,5,(sqlite3_int64)note.location.selector.end)!=SQLITE_OK || !bind_text(s,6,note.location.selector.exact) ||
       !bind_nullable_text(s,7,note.location.selector.prefix) || !bind_nullable_text(s,8,note.location.selector.suffix) ||
       !bind_nullable_text(s,9,note.location.selector.chapter) || !bind_text(s,10,note.text) ||
       (note.id && sqlite3_bind_int64(s,11,note.id)!=SQLITE_OK)) { status=database_error(l,e);goto finish; }
  }
  status=done(l,s,e);s=NULL;if(status!=EXR_OK) goto finish;
  if(note.id && !sqlite3_changes(l->db)) { status=exr_fail(e,EXR_ARGUMENT,"EPUB note missing from this book");goto finish; }
  saved=note.id ? note.id : sqlite3_last_insert_rowid(l->db);
  if(saved<=0) { status=exr_fail(e,EXR_DATABASE,"Invalid stored EPUB note ID");goto finish; }
  if(operation_commit(l)!=SQLITE_OK) { status=database_error(l,e);goto finish; }
  transaction=0;*id=saved;status=exr_fail(e,EXR_OK,"");
finish:
  sqlite3_finalize(s);if(transaction) operation_rollback(l);
  sqlite3_mutex_leave(mutex);return status;
}
void exr_epub_notes_free(exr_epub_note *notes,size_t count) {
  size_t i;for(i=0;i<count;i++) { exr_epub_location_free(&notes[i].location);free(notes[i].text); }
  free(notes);
}
exr_status exr_library_epub_notes(exr_library *l,int64_t book,exr_epub_note **out,size_t *count,exr_error *e) {
  exr_epub_note *notes=NULL;exr_document *index=NULL;exr_source source={0};sqlite3_stmt *s=NULL;
  sqlite3_mutex *mutex;exr_status status;exr_error validation={0};size_t n=0,capacity=0,bytes=0;
  int format=0,bounded=0,step;
  if(out) *out=NULL;
  if(count) *count=0;
  if(!l || book<=0 || !out || !count) return exr_fail(e,EXR_ARGUMENT,"Invalid EPUB notes query");
  mutex=sqlite3_db_mutex(l->db);sqlite3_mutex_enter(mutex);
  status=book_storage(l,book,&format,&bounded,0,e);if(status!=EXR_OK) goto finish;
  if(format!=EXR_EPUB) { status=exr_fail(e,EXR_FORMAT,"Book is not EPUB");goto finish; }
  if(!prepare(l,"SELECT id,book_id,part,path,start,end,exact,prefix,suffix,chapter,text "
                "FROM epub_notes WHERE book_id=?1 ORDER BY part,start,id",&s) ||
     sqlite3_bind_int64(s,1,book)!=SQLITE_OK) { status=database_error(l,e);goto finish; }
  while((step=sqlite3_step(s))==SQLITE_ROW) {
    exr_epub_note *note;size_t payload=sizeof(*notes),i;
    const int columns[]={3,6,7,8,9,10};
    for(i=0;i<sizeof(columns)/sizeof(*columns);i++) {
      size_t length=(size_t)sqlite3_column_bytes(s,columns[i]);
      if(length+1>EXR_MAX_TEXT-payload) { status=exr_fail(e,EXR_LIMIT,"EPUB notes exceed query budget");goto finish; }
      payload+=length+1;
    }
    if(n>=EXR_MAX_ITEMS || payload>EXR_MAX_TEXT-bytes) { status=exr_fail(e,EXR_LIMIT,"EPUB notes exceed query budget");goto finish; }
    if(!index) {
      status=exr_library_source(l,book,&source,e);if(status!=EXR_OK) goto finish;
      status=exr_epub_index_source(&source,&index,e);if(status!=EXR_OK) goto finish;
    }
    if(!exr_grow((void **)&notes,&capacity,n+1,sizeof(*notes))) { status=exr_fail(e,EXR_MEMORY,"EPUB notes allocation failed");goto finish; }
    note=&notes[n++];memset(note,0,sizeof(*note));
    if(sqlite3_column_type(s,0)!=SQLITE_INTEGER || (note->id=sqlite3_column_int64(s,0))<=0 ||
       sqlite3_column_type(s,1)!=SQLITE_INTEGER || (note->book_id=sqlite3_column_int64(s,1))!=book ||
       !offset_column(s,2,&note->location.part) || !offset_column(s,4,&note->location.selector.start) ||
       !offset_column(s,5,&note->location.selector.end)) {
      status=exr_fail(e,EXR_DATABASE,"Invalid stored EPUB note range");goto finish;
    }
    status=epub_text_column(s,3,2046,0,&note->location.path,e);
    if(status==EXR_OK) status=epub_text_column(s,6,65536,0,&note->location.selector.exact,e);
    if(status==EXR_OK) status=epub_text_column(s,7,128,1,&note->location.selector.prefix,e);
    if(status==EXR_OK) status=epub_text_column(s,8,128,1,&note->location.selector.suffix,e);
    if(status==EXR_OK) status=epub_text_column(s,9,2046,1,&note->location.selector.chapter,e);
    if(status==EXR_OK) status=epub_text_column(s,10,EXR_MAX_TEXT,0,&note->text,e);
    if(status!=EXR_OK) goto finish;
    if(epub_location_validate(&note->location,0,&validation)!=EXR_OK ||
       note->location.part>=index->chapter_count ||
       strcmp(index->chapters[note->location.part].path,note->location.path)) {
      status=exr_fail(e,EXR_DATABASE,"Invalid stored EPUB note selector or route");goto finish;
    }
    bytes+=payload;
  }
  if(step!=SQLITE_DONE) { status=database_error(l,e);goto finish; }
  *out=notes;*count=n;notes=NULL;n=0;status=exr_fail(e,EXR_OK,"");
finish:
  sqlite3_finalize(s);exr_document_free(index);if(source.release) source.release(source.context);
  exr_epub_notes_free(notes,n);sqlite3_mutex_leave(mutex);return status;
}
exr_status exr_library_remove_epub_note(exr_library *l,int64_t id,exr_error *e) {
  sqlite3_stmt *s=NULL;sqlite3_mutex *mutex;exr_status status;
  if(!l || id<=0) return exr_fail(e,EXR_ARGUMENT,"Invalid EPUB note deletion");
  mutex=sqlite3_db_mutex(l->db);sqlite3_mutex_enter(mutex);
  if(!prepare(l,"DELETE FROM epub_notes WHERE id=?1",&s) || sqlite3_bind_int64(s,1,id)!=SQLITE_OK) {
    status=database_error(l,e);sqlite3_finalize(s);
  } else {
    status=done(l,s,e);
    if(status==EXR_OK) status=sqlite3_changes(l->db) ? exr_fail(e,EXR_OK,"") : exr_fail(e,EXR_ARGUMENT,"EPUB note missing");
  }
  sqlite3_mutex_leave(mutex);return status;
}
static exr_status store_progress(exr_library *l,int64_t book,const exr_anchor *point,exr_anchor_state state,exr_error *e) {
  sqlite3_stmt *s=NULL;
  if(!prepare(l,"INSERT INTO book_progress(book_id,position,state,prefix,suffix,chapter)VALUES(?1,?2,?3,?4,?5,?6) ON CONFLICT(book_id) DO UPDATE SET position=excluded.position,state=excluded.state,prefix=excluded.prefix,suffix=excluded.suffix,chapter=excluded.chapter",&s) ||
     sqlite3_bind_int64(s,1,book)!=SQLITE_OK || sqlite3_bind_int64(s,2,(sqlite3_int64)point->start)!=SQLITE_OK || sqlite3_bind_int(s,3,state)!=SQLITE_OK || !bind_nullable_text(s,4,point->prefix) || !bind_nullable_text(s,5,point->suffix) || !bind_nullable_text(s,6,point->chapter)) { sqlite3_finalize(s); return database_error(l,e); }
  return done(l,s,e);
}
exr_status exr_library_progress(exr_library *l,int64_t book,const exr_anchor *point,exr_error *e) {
  sqlite3_stmt *s=NULL;sqlite3_mutex *mutex;exr_status status; size_t extent; int step,format,transaction=0;
  if(!l || book<=0 || !point || !point->exact || point->exact[0] || point->start!=point->end || point->start==SIZE_MAX || point->start>INT64_MAX)
    return exr_fail(e,EXR_ARGUMENT,"Reading progress requires a finite point selector");
  status=exr_anchor_validate(point,e); if(status!=EXR_OK) return status;
  mutex=sqlite3_db_mutex(l->db);sqlite3_mutex_enter(mutex);
  if(operation_begin(l)!=SQLITE_OK) { status=database_error(l,e);goto finish; }
  transaction=1;
  status=require_global_storage(l,book,e);if(status!=EXR_OK) goto finish;
  if(!prepare(l,"SELECT format,text_size FROM books WHERE id=?1",&s) || sqlite3_bind_int64(s,1,book)!=SQLITE_OK) { status=database_error(l,e); goto finish; }
  step=sqlite3_step(s); if(step!=SQLITE_ROW) { status=step==SQLITE_DONE ? exr_fail(e,EXR_ARGUMENT,"Book missing") : database_error(l,e); goto finish; }
  if(sqlite3_column_type(s,0)!=SQLITE_INTEGER || !offset_column(s,1,&extent) || extent>EXR_MAX_TEXT) { status=exr_fail(e,EXR_DATABASE,"Invalid stored book extent"); goto finish; }
  format=sqlite3_column_int(s,0);
  if(exr_format_is_fixed(format)) { status=exr_fail(e,EXR_FORMAT,"Text progress selectors do not describe fixed-page positions"); goto finish; }
  if(format<EXR_TXT || format>EXR_MOBI) { status=exr_fail(e,EXR_DATABASE,"Invalid stored book format"); goto finish; }
  if(point->start>extent) { status=exr_fail(e,EXR_ARGUMENT,"Reading progress is outside the stored text extent"); goto finish; }
  sqlite3_finalize(s); s=NULL;
  if(!prepare(l,"UPDATE books SET position=?1 WHERE id=?2",&s) || sqlite3_bind_int64(s,1,(sqlite3_int64)point->start)!=SQLITE_OK || sqlite3_bind_int64(s,2,book)!=SQLITE_OK) { status=database_error(l,e); goto finish; }
  status=done(l,s,e); s=NULL; if(status!=EXR_OK) goto finish;
  status=store_progress(l,book,point,EXR_ANCHOR_FOUND,e); if(status!=EXR_OK) goto finish;
  if(operation_commit(l)!=SQLITE_OK) { status=database_error(l,e); goto finish; }
  transaction=0; status=exr_fail(e,EXR_OK,"");
finish:
  sqlite3_finalize(s);if(transaction) operation_rollback(l);
  sqlite3_mutex_leave(mutex);return status;
}
exr_status exr_library_progress_get(exr_library *l,int64_t book,exr_anchor *out,exr_anchor_state *state,exr_error *e) {
  sqlite3_stmt *s=NULL; exr_anchor a={0}; exr_error local={0}; exr_status status; size_t position,extent; int step,format,value;
  if(out) memset(out,0,sizeof(*out));
  if(state) *state=EXR_ANCHOR_MISSING;
  if(!l || book<=0 || !out || !state) return exr_fail(e,EXR_ARGUMENT,"Invalid reading progress query");
  status=require_global_storage(l,book,e);if(status!=EXR_OK) return status;
  if(!prepare(l,"SELECT b.format,b.position,b.text_size,p.book_id,p.position,p.state,p.prefix,p.suffix,p.chapter FROM books b LEFT JOIN book_progress p ON p.book_id=b.id WHERE b.id=?1",&s) || sqlite3_bind_int64(s,1,book)!=SQLITE_OK) { status=database_error(l,e); goto finish; }
  step=sqlite3_step(s); if(step!=SQLITE_ROW) { status=step==SQLITE_DONE ? exr_fail(e,EXR_ARGUMENT,"Book missing") : database_error(l,e); goto finish; }
  if(sqlite3_column_type(s,0)!=SQLITE_INTEGER || !offset_column(s,1,&position) || !offset_column(s,2,&extent) || position>extent || extent>EXR_MAX_TEXT) { status=exr_fail(e,EXR_DATABASE,"Invalid stored reading position"); goto finish; }
  format=sqlite3_column_int(s,0);
  if(exr_format_is_fixed(format)) { status=exr_fail(e,EXR_FORMAT,"Fixed-page progress uses page positions"); goto finish; }
  if(format<EXR_TXT || format>EXR_MOBI) { status=exr_fail(e,EXR_DATABASE,"Invalid stored book format"); goto finish; }
  if(sqlite3_column_type(s,3)==SQLITE_NULL) { a.start=a.end=position; value=EXR_ANCHOR_LEGACY; goto success; }
  if(sqlite3_column_type(s,3)!=SQLITE_INTEGER || sqlite3_column_int64(s,3)!=book || !offset_column(s,4,&a.start) || sqlite3_column_type(s,5)!=SQLITE_INTEGER || (value=sqlite3_column_int(s,5))<0 || value>EXR_ANCHOR_LEGACY) { status=exr_fail(e,EXR_DATABASE,"Invalid stored reading selector"); goto finish; }
  a.end=a.start; if(value!=EXR_ANCHOR_LEGACY) a.exact=exr_copy("",0); if(value!=EXR_ANCHOR_LEGACY && !a.exact) { status=exr_fail(e,EXR_MEMORY,"Reading selector allocation failed"); goto finish; }
  status=annotation_column(s,6,1,&a.prefix,e); if(status==EXR_OK) status=annotation_column(s,7,1,&a.suffix,e); if(status==EXR_OK) status=annotation_column(s,8,1,&a.chapter,e); if(status!=EXR_OK) goto finish;
  if(exr_anchor_validate(&a,&local)!=EXR_OK || (value==EXR_ANCHOR_LEGACY && (a.prefix || a.suffix || a.chapter)) || (value==EXR_ANCHOR_FOUND && (a.start!=position || a.start>extent))) { status=exr_fail(e,EXR_DATABASE,"Inconsistent stored reading selector"); goto finish; }
success:
  *out=a; memset(&a,0,sizeof(a)); *state=(exr_anchor_state)value; status=exr_fail(e,EXR_OK,"");
finish:
  sqlite3_finalize(s); exr_anchor_free(&a); return status;
}
exr_status exr_library_clear_progress(exr_library *l,int64_t book,exr_error *e) {
  sqlite3_stmt *s=NULL;sqlite3_mutex *mutex;exr_status status;int transaction=0;
  if(!l || book<=0) return exr_fail(e,EXR_ARGUMENT,"Invalid reading selector removal");
  mutex=sqlite3_db_mutex(l->db);sqlite3_mutex_enter(mutex);
  if(operation_begin(l)!=SQLITE_OK) { status=database_error(l,e);goto finish; }
  transaction=1;
  status=require_global_storage(l,book,e);if(status!=EXR_OK) goto finish;
  if(!prepare(l,"DELETE FROM book_progress WHERE book_id=?1",&s) || sqlite3_bind_int64(s,1,book)!=SQLITE_OK) { status=database_error(l,e);goto finish; }
  status=done(l,s,e);s=NULL;if(status!=EXR_OK) goto finish;
  if(operation_commit(l)!=SQLITE_OK) { status=database_error(l,e);goto finish; }
  transaction=0;status=exr_fail(e,EXR_OK,"");
finish:
  sqlite3_finalize(s);if(transaction) operation_rollback(l);
  sqlite3_mutex_leave(mutex);return status;
}
static exr_status library_note(exr_library *l, const exr_note *note, int64_t *id, exr_error *e) {
  sqlite3_stmt *s = NULL;
  exr_document *doc = NULL;
  exr_anchor captured = {0};
  exr_note snapshot;
  const exr_anchor *anchor;
  exr_status result;
  size_t text_size;
  int step, preserve = 0;
  /* The output commonly aliases note->id; retain the input before clearing it. */
  if (note) {
    snapshot = *note;
    note = &snapshot;
  }
  if (id)
    *id = 0;
  if (!l || !note || !id || !note->text || note->id < 0 || note->book_id <= 0 ||
      note->start > note->end || (uint64_t)note->end > INT64_MAX)
    return exr_fail(e, EXR_ARGUMENT, "Invalid annotation");
  result=require_global_storage(l,note->book_id,e);if(result!=EXR_OK) return result;
  result=annotation_input(note->text,e); if(result!=EXR_OK) return result;
  anchor = &note->anchor;
  if (anchor->exact) {
    if (anchor->start != note->start || anchor->end != note->end)
      return exr_fail(e, EXR_ARGUMENT, "Annotation selector and range differ");
    result = exr_anchor_validate(anchor, e);
    if (result != EXR_OK)
      return result;
  }
  if (!prepare(l, "SELECT text_size,format FROM books WHERE id=?1", &s))
    return database_error(l, e);
  if (sqlite3_bind_int64(s, 1, note->book_id) != SQLITE_OK)
    goto database;
  step = sqlite3_step(s);
  if (step != SQLITE_ROW) {
    if (step != SQLITE_DONE)
      goto database;
    sqlite3_finalize(s);
    return exr_fail(e, EXR_ARGUMENT, "Book missing");
  }
  if(exr_format_is_fixed((exr_format)sqlite3_column_int(s,1))) { sqlite3_finalize(s); return exr_fail(e,EXR_FORMAT,"Use fixed-page notes for this book"); }
  if (!offset_column(s, 0, &text_size) || text_size > EXR_MAX_TEXT) {
    sqlite3_finalize(s);
    return exr_fail(e, EXR_DATABASE, "Invalid stored book text size");
  }
  sqlite3_finalize(s);
  s = NULL;
  if (note->end > text_size)
    return exr_fail(e, EXR_ARGUMENT, "Annotation is outside its book");
  if (note->id > 0) {
    exr_note previous = {0};
    if (!prepare(l,
                 "SELECT n.id,n.book_id,n.start,n.end,n.text,n.anchor_exact,n.anchor_prefix,"
                 "n.anchor_suffix,n.anchor_chapter,b.text_size,n.location_state FROM notes n "
                 "JOIN books b ON b.id=n.book_id WHERE n.book_id=?1 AND n.id=?2", &s))
      return database_error(l, e);
    if (sqlite3_bind_int64(s, 1, note->book_id) != SQLITE_OK ||
        sqlite3_bind_int64(s, 2, note->id) != SQLITE_OK)
      goto database;
    step = sqlite3_step(s);
    if (step != SQLITE_ROW) {
      if (step != SQLITE_DONE)
        goto database;
      sqlite3_finalize(s);
      return exr_fail(e, EXR_ARGUMENT, "Annotation missing from book");
    }
    result = read_note(s, &previous, e);
    preserve = !anchor->exact && previous.start == note->start && previous.end == note->end;
    free(previous.text);
    exr_anchor_free(&previous.anchor);
    sqlite3_finalize(s);
    s = NULL;
    if (result != EXR_OK)
      return result;
  }
  if (!preserve && !anchor->exact) {
    result = exr_library_document(l, note->book_id, &doc, e);
    if (result == EXR_OK)
      result = exr_anchor_create(doc, note->start, note->end, &captured, e);
    exr_document_free(doc);
    if (result != EXR_OK)
      return result;
    anchor = &captured;
  }
  if (!prepare(l,
               preserve ? "UPDATE notes SET text=?3 WHERE book_id=?4 AND id=?5"
               : note->id > 0 ? "UPDATE notes SET start=?1,end=?2,text=?3,anchor_exact=?6,"
                                "anchor_prefix=?7,anchor_suffix=?8,anchor_chapter=?9,location_state=1 "
                                "WHERE book_id=?4 AND id=?5"
                              : "INSERT INTO notes(start,end,text,book_id,anchor_exact,"
                                "anchor_prefix,anchor_suffix,anchor_chapter)"
                                "VALUES(?1,?2,?3,?4,?6,?7,?8,?9)", &s))
    goto database;
  if ((!preserve && (sqlite3_bind_int64(s, 1, (sqlite3_int64)note->start) != SQLITE_OK ||
                     sqlite3_bind_int64(s, 2, (sqlite3_int64)note->end) != SQLITE_OK)) ||
      !bind_text(s, 3, note->text) || sqlite3_bind_int64(s, 4, note->book_id) != SQLITE_OK ||
      (note->id > 0 && sqlite3_bind_int64(s, 5, note->id) != SQLITE_OK) ||
      (!preserve && (!bind_nullable_text(s, 6, anchor->exact) ||
                     !bind_nullable_text(s, 7, anchor->prefix) ||
                     !bind_nullable_text(s, 8, anchor->suffix) ||
                     !bind_nullable_text(s, 9, anchor->chapter))))
    goto database;
  result = done(l, s, e);
  exr_anchor_free(&captured);
  if (result == EXR_OK) {
    if (!sqlite3_changes(l->db))
      return exr_fail(e, EXR_ARGUMENT, "Annotation missing from book");
    *id = note->id > 0 ? note->id : sqlite3_last_insert_rowid(l->db);
  }
  return result;
database:
  result = database_error(l, e);
  sqlite3_finalize(s);
  exr_anchor_free(&captured);
  return result;
}
exr_status exr_library_note(exr_library *l,const exr_note *input,int64_t *id,exr_error *e) {
  exr_note note;sqlite3_mutex *mutex;exr_status status;int transaction=0;
  if(input) note=*input;
  if(id) *id=0;
  if(!l || !input || !id || !note.text || note.id<0 || note.book_id<=0 ||
     note.start>note.end || (uint64_t)note.end>INT64_MAX)
    return exr_fail(e,EXR_ARGUMENT,"Invalid annotation");
  mutex=sqlite3_db_mutex(l->db);sqlite3_mutex_enter(mutex);
  if(operation_begin(l)!=SQLITE_OK) { status=database_error(l,e);goto finish; }
  transaction=1;status=library_note(l,&note,id,e);if(status!=EXR_OK) goto finish;
  if(operation_commit(l)!=SQLITE_OK) { status=database_error(l,e);goto finish; }
  transaction=0;
finish:
  if(transaction) operation_rollback(l);
  if(status!=EXR_OK) *id=0;
  sqlite3_mutex_leave(mutex);return status;
}
exr_status exr_library_note_text(exr_library *l,int64_t id,const char *text,exr_error *e) {
  sqlite3_stmt *s=NULL; exr_status status;
  if(!l || id<=0) return exr_fail(e,EXR_ARGUMENT,"Invalid note text update");
  status=annotation_input(text,e); if(status!=EXR_OK) return status;
  if(!prepare(l,"UPDATE notes SET text=?1 WHERE id=?2",&s) || !bind_text(s,1,text) || sqlite3_bind_int64(s,2,id)!=SQLITE_OK) { sqlite3_finalize(s); return database_error(l,e); }
  status=done(l,s,e); if(status!=EXR_OK) return status;
  return sqlite3_changes(l->db) ? exr_fail(e,EXR_OK,"") : exr_fail(e,EXR_ARGUMENT,"Note missing");
}
void exr_notes_free(exr_note *notes, size_t n) {
  size_t i;
  for (i = 0; i < n; i++) {
    free(notes[i].text);
    exr_anchor_free(&notes[i].anchor);
  }
  free(notes);
}
exr_status exr_library_notes(exr_library *l, int64_t book_id, exr_note **out, size_t *count,
                             exr_error *e) {
  sqlite3_stmt *s = NULL;
  exr_note *notes = NULL;
  size_t n = 0, cap = 0;
  int step;
  exr_status result;
  if (!l || !out || !count || book_id <= 0)
    return exr_fail(e, EXR_ARGUMENT, "Invalid annotation query");
  *out = NULL;
  *count = 0;
  result=require_global_storage(l,book_id,e);if(result!=EXR_OK) return result;
  if (!prepare(l,
               "SELECT n.id,n.book_id,n.start,n.end,n.text,n.anchor_exact,n.anchor_prefix,"
               "n.anchor_suffix,n.anchor_chapter,b.text_size,n.location_state FROM notes n JOIN books b "
               "ON b.id=n.book_id WHERE n.book_id=?1 ORDER BY n.start,n.id", &s))
    return database_error(l, e);
  if (sqlite3_bind_int64(s, 1, book_id) != SQLITE_OK) {
    result = database_error(l, e);
    goto failure;
  }
  while ((step = sqlite3_step(s)) == SQLITE_ROW) {
    if (n >= EXR_MAX_ITEMS || !exr_grow((void **)&notes, &cap, n + 1, sizeof(*notes))) {
      result = exr_fail(e, EXR_MEMORY, "Annotation allocation failed");
      goto failure;
    }
    result = read_note(s, &notes[n++], e);
    if (result != EXR_OK)
      goto failure;
  }
  if (step != SQLITE_DONE) {
    result = database_error(l, e);
    goto failure;
  }
  sqlite3_finalize(s);
  *out = notes;
  *count = n;
  return EXR_OK;
failure:
  sqlite3_finalize(s);
  exr_notes_free(notes, n);
  return result;
}
static exr_status remove_id(exr_library *l, int64_t id, int note, exr_error *e) {
  sqlite3_stmt *s = NULL;
  if (!l || id <= 0)
    return exr_fail(e, EXR_ARGUMENT, "Invalid deletion");
  if (!prepare(l, note ? "DELETE FROM notes WHERE id=?1" : "DELETE FROM books WHERE id=?1", &s))
    return database_error(l, e);
  sqlite3_bind_int64(s, 1, id);
  return done(l, s, e);
}
exr_status exr_library_delete(exr_library *l, int64_t id, exr_error *e) {
  exr_status status;sqlite3_mutex *mutex;library_source *source;
  if(!l) return exr_fail(e,EXR_ARGUMENT,"Invalid library");
  mutex=sqlite3_db_mutex(l->db);sqlite3_mutex_enter(mutex);
  status=remove_id(l,id,0,e);
  if(status==EXR_OK) for(source=l->sources;source;source=source->next)
    if(source->id==id) source->valid=0;
  sqlite3_mutex_leave(mutex);return status;
}
exr_status exr_library_remove_note(exr_library *l, int64_t id, exr_error *e) {
  return remove_id(l, id, 1, e);
}
exr_status exr_library_backup(exr_library *l, const char *path, exr_error *e) {
  sqlite3_stmt *s = NULL;
  if (!l || !path || !path[0])
    return exr_fail(e, EXR_ARGUMENT, "Invalid backup path");
  if (!prepare(l, "VACUUM INTO ?1", &s))
    return database_error(l, e);
  bind_text(s, 1, path);
  return done(l, s, e);
}

exr_status exr_library_fixed_note(exr_library *l,const exr_fixed_note *input,const exr_control *control,int64_t *id,exr_error *e) {
  exr_fixed_note note; exr_fixed_document *doc=NULL; exr_fixed_text *text=NULL; exr_fixed_anchor anchor={0};
  exr_fixed_open_options options={0}; sqlite3_stmt *s=NULL; exr_status status; size_t count,n=0,at=0; uint32_t cp; const exr_fixed_page *pages;
  if(input) note=*input; else memset(&note,0,sizeof(note)); /* Output ID may alias input.id. */
  if(id) *id=0;
  if(!l || !input || !id || note.id<0 || note.book_id<=0 || !note.text || note.start>note.end || note.end>EXR_MAX_TEXT)
    return exr_fail(e,EXR_ARGUMENT,"Invalid fixed note input");
  while(n<=(size_t)1024*1024 && note.text[n]) n++;
  if(n>(size_t)1024*1024) return exr_fail(e,EXR_LIMIT,"Fixed note exceeds 1 MiB");
  while(at<n) if(!exr_next(note.text,n,&at,&cp)) return exr_fail(e,EXR_ENCODING,"Fixed note is not UTF-8");
  options.struct_size=sizeof(options); if(control) options.control=*control;
  status=exr_library_fixed(l,note.book_id,&options,&doc,e); if(status!=EXR_OK) goto finish;
  pages=exr_fixed_pages(doc,&count);
  if(note.page>=count) { status=exr_fail(e,EXR_ARGUMENT,"Fixed note page is out of range"); goto finish; }
  status=exr_fixed_load_text(doc,note.page,control,&text,e);
  if(status==EXR_OK) status=exr_fixed_anchor_create(pages[note.page].id,text,note.start,note.end,&anchor,e);
  if(status!=EXR_OK) goto finish;
  if(!prepare(l,note.id ?
      "UPDATE fixed_notes SET page=?2,start=?3,end=?4,text=?5,page_id=?6,exact=?7,prefix=?8,suffix=?9 WHERE book_id=?1 AND id=?10" :
      "INSERT INTO fixed_notes(book_id,page,start,end,text,page_id,exact,prefix,suffix) VALUES(?1,?2,?3,?4,?5,?6,?7,?8,?9)",&s)) { status=database_error(l,e); goto finish; }
  if(sqlite3_bind_int64(s,1,note.book_id)!=SQLITE_OK || sqlite3_bind_int64(s,2,(sqlite3_int64)note.page)!=SQLITE_OK ||
     sqlite3_bind_int64(s,3,(sqlite3_int64)note.start)!=SQLITE_OK || sqlite3_bind_int64(s,4,(sqlite3_int64)note.end)!=SQLITE_OK ||
     !bind_text(s,5,note.text) || !bind_text(s,6,anchor.page_id) ||
     sqlite3_bind_blob(s,7,anchor.exact,(int)anchor.exact_size,SQLITE_TRANSIENT)!=SQLITE_OK ||
     sqlite3_bind_blob(s,8,anchor.prefix,(int)anchor.prefix_size,SQLITE_TRANSIENT)!=SQLITE_OK ||
     sqlite3_bind_blob(s,9,anchor.suffix,(int)anchor.suffix_size,SQLITE_TRANSIENT)!=SQLITE_OK ||
     (note.id && sqlite3_bind_int64(s,10,note.id)!=SQLITE_OK)) { status=database_error(l,e); goto finish; }
  status=exr_control_cancel(control,e); if(status!=EXR_OK) goto finish;
  status=done(l,s,e); s=NULL;
  if(status==EXR_OK) {
    if(note.id && !sqlite3_changes(l->db)) status=exr_fail(e,EXR_ARGUMENT,"Fixed note missing or belongs to another book");
    else *id=note.id ? note.id : sqlite3_last_insert_rowid(l->db);
  }
finish:
  sqlite3_finalize(s); exr_fixed_anchor_free(&anchor); exr_fixed_text_free(text); exr_fixed_free(doc); return status;
}
void exr_fixed_notes_free(exr_fixed_note *notes,size_t count) {
  size_t i; if(!notes) return;
  for(i=0;i<count;i++) { free(notes[i].text); exr_fixed_anchor_free(&notes[i].anchor); }
  free(notes);
}
static exr_status fixed_column(sqlite3_stmt *s,int col,int type,size_t maximum,char **out,size_t *size,exr_error *e) {
  int n; const void *bytes;
  *out=NULL; *size=0;
  if(sqlite3_column_type(s,col)!=type) return exr_fail(e,EXR_DATABASE,"Invalid stored fixed note value type");
  bytes=type==SQLITE_TEXT ? (const void *)sqlite3_column_text(s,col) : sqlite3_column_blob(s,col); n=sqlite3_column_bytes(s,col);
  if(n<0 || (size_t)n>maximum || (type==SQLITE_TEXT && n && bytes && memchr(bytes,0,(size_t)n)))
    return exr_fail(e,EXR_DATABASE,"Invalid stored fixed note value size");
  if(n && !bytes) return exr_fail(e,EXR_MEMORY,"Fixed note read allocation failed");
  *out=exr_copy(bytes,(size_t)n); if(!*out) return exr_fail(e,EXR_MEMORY,"Fixed note copy allocation failed");
  *size=(size_t)n; return EXR_OK;
}
static exr_status read_fixed_note(sqlite3_stmt *s,exr_fixed_note *note,size_t *bytes,exr_error *e) {
  exr_status status; exr_error local={0}; size_t pages,comment,page_id,at=0; uint32_t cp; exr_fixed_anchor *a=&note->anchor;
  memset(note,0,sizeof(*note));
  if(sqlite3_column_type(s,0)!=SQLITE_INTEGER || (note->id=sqlite3_column_int64(s,0))<=0 ||
     sqlite3_column_type(s,1)!=SQLITE_INTEGER || (note->book_id=sqlite3_column_int64(s,1))<=0 ||
     !offset_column(s,2,&note->page) || !offset_column(s,3,&note->start) || !offset_column(s,4,&note->end) ||
     !offset_column(s,10,&pages) || !pages || pages>10000 || note->page>=pages || note->start>note->end || note->end>EXR_MAX_TEXT ||
     sqlite3_column_type(s,11)!=SQLITE_INTEGER || !exr_format_is_fixed((exr_format)sqlite3_column_int(s,11))) return exr_fail(e,EXR_DATABASE,"Invalid stored fixed note range/book");
  a->start=note->start; a->end=note->end;
  if((status=fixed_column(s,5,SQLITE_TEXT,(size_t)1024*1024,&note->text,&comment,e))!=EXR_OK ||
     (status=fixed_column(s,6,SQLITE_TEXT,65536,&a->page_id,&page_id,e))!=EXR_OK ||
     (status=fixed_column(s,7,SQLITE_BLOB,65536,&a->exact,&a->exact_size,e))!=EXR_OK ||
     (status=fixed_column(s,8,SQLITE_BLOB,128,&a->prefix,&a->prefix_size,e))!=EXR_OK ||
     (status=fixed_column(s,9,SQLITE_BLOB,128,&a->suffix,&a->suffix_size,e))!=EXR_OK) return status;
  while(at<comment) if(!exr_next(note->text,comment,&at,&cp)) return exr_fail(e,EXR_DATABASE,"Invalid stored fixed note UTF-8");
  if(exr_fixed_anchor_validate(a,&local)!=EXR_OK) return exr_fail(e,EXR_DATABASE,"Invalid stored fixed note selector");
  *bytes=sizeof(*note)+comment+page_id+a->exact_size+a->prefix_size+a->suffix_size+5; return EXR_OK;
}
exr_status exr_library_fixed_notes(exr_library *l,int64_t book_id,exr_fixed_note **out,size_t *count,exr_error *e) {
  sqlite3_stmt *s=NULL; exr_fixed_note *notes=NULL; size_t n=0,capacity=0,total=0; int step; exr_status status=EXR_OK;
  if(out) *out=NULL;
  if(count) *count=0;
  if(!l || book_id<=0 || !out || !count) return exr_fail(e,EXR_ARGUMENT,"Invalid fixed note query");
  if(!prepare(l,"SELECT n.id,n.book_id,n.page,n.start,n.end,n.text,n.page_id,n.exact,n.prefix,n.suffix,b.text_size,b.format FROM fixed_notes n JOIN books b ON b.id=n.book_id WHERE n.book_id=?1 ORDER BY n.page,n.start,n.id",&s)) return database_error(l,e);
  if(sqlite3_bind_int64(s,1,book_id)!=SQLITE_OK) { status=database_error(l,e); goto finish; }
  while((step=sqlite3_step(s))==SQLITE_ROW) {
    size_t bytes=0;
    if(n>=100000 || total>=(size_t)64*1024*1024) { status=exr_fail(e,EXR_LIMIT,"Fixed note query exceeds result budget"); goto finish; }
    if(!exr_grow((void **)&notes,&capacity,n+1,sizeof(*notes))) { status=exr_fail(e,EXR_MEMORY,"Fixed note results allocation failed"); goto finish; }
    status=read_fixed_note(s,&notes[n++],&bytes,e); if(status!=EXR_OK) goto finish;
    if(bytes>(size_t)64*1024*1024-total) { status=exr_fail(e,EXR_LIMIT,"Fixed note query exceeds result byte budget"); goto finish; }
    total+=bytes;
  }
  if(step!=SQLITE_DONE) status=database_error(l,e);
finish:
  sqlite3_finalize(s);
  if(status==EXR_OK) { *out=notes; *count=n; } else exr_fixed_notes_free(notes,n);
  return status;
}
exr_status exr_library_remove_fixed_note(exr_library *l,int64_t id,exr_error *e) {
  sqlite3_stmt *s=NULL;
  if(!l || id<=0) return exr_fail(e,EXR_ARGUMENT,"Invalid fixed note deletion");
  if(!prepare(l,"DELETE FROM fixed_notes WHERE id=?1",&s)) return database_error(l,e);
  if(sqlite3_bind_int64(s,1,id)!=SQLITE_OK) { sqlite3_finalize(s); return database_error(l,e); }
  return done(l,s,e);
}

static exr_status audio_string(const char *text,size_t maximum,int required,size_t *size,exr_error *e) {
  size_t n=0,at=0; uint32_t cp;
  if(!text || (required && !*text)) return exr_fail(e,EXR_ARGUMENT,"Missing audio persistence identifier");
  while(n<=maximum && text[n]) n++;
  if(n>maximum) return exr_fail(e,EXR_LIMIT,"Audio persistence string exceeds budget");
  while(at<n) if(!exr_next(text,n,&at,&cp)) return exr_fail(e,EXR_ENCODING,"Audio persistence string is not UTF-8");
  if(size) *size=n;
  return EXR_OK;
}
static exr_status checkpoint_valid(const exr_audio_checkpoint *p,exr_error *e) {
  if(!p || !isfinite(p->rate) || p->rate<=0 || p->rate>16) return exr_fail(e,EXR_ARGUMENT,"Invalid audio checkpoint rate");
  return audio_string(p->track_id,65536,1,NULL,e);
}
static int checkpoint_bind(sqlite3_stmt *s,int column,const exr_audio_checkpoint *p) {
  unsigned char offset[8]; unsigned i;
  for(i=0;i<8;i++) offset[i]=(unsigned char)(p->offset_ms>>(i*8));
  return bind_text(s,column,p->track_id) && sqlite3_bind_blob(s,column+1,offset,8,SQLITE_TRANSIENT)==SQLITE_OK && sqlite3_bind_double(s,column+2,p->rate)==SQLITE_OK;
}
static exr_status checkpoint_read(sqlite3_stmt *s,int column,exr_audio_checkpoint *p,exr_error *e) {
  exr_status status; exr_error local={0}; const unsigned char *offset; size_t bytes; unsigned i; int type;
  memset(p,0,sizeof(*p));
  status=fixed_column(s,column,SQLITE_TEXT,65536,&p->track_id,&bytes,e); if(status!=EXR_OK) return status;
  type=sqlite3_column_type(s,column+2);
  if(sqlite3_column_type(s,column+1)!=SQLITE_BLOB || sqlite3_column_bytes(s,column+1)!=8 || (type!=SQLITE_FLOAT && type!=SQLITE_INTEGER)) return exr_fail(e,EXR_DATABASE,"Invalid stored audio checkpoint types");
  offset=sqlite3_column_blob(s,column+1); if(!offset) return exr_fail(e,EXR_MEMORY,"Audio checkpoint allocation failed");
  for(i=0;i<8;i++) p->offset_ms|=(uint64_t)offset[i]<<(8*i);
  p->rate=sqlite3_column_double(s,column+2);
  if(checkpoint_valid(p,&local)!=EXR_OK) return exr_fail(e,EXR_DATABASE,"Invalid stored audio checkpoint");
  return EXR_OK;
}
void exr_audio_checkpoint_free(exr_audio_checkpoint *p) { if(p) { free(p->track_id); memset(p,0,sizeof(*p)); } }
exr_status exr_library_audio_resume(exr_library *l,const char *key,const exr_audio_checkpoint *p,exr_error *e) {
  sqlite3_stmt *s=NULL; exr_status status;
  if(!l) return exr_fail(e,EXR_ARGUMENT,"Missing audio library");
  if((status=audio_string(key,4096,1,NULL,e))!=EXR_OK || (status=checkpoint_valid(p,e))!=EXR_OK) return status;
  if(!prepare(l,"INSERT INTO audio_resume(audio_id,track_id,offset,rate) VALUES(?1,?2,?3,?4) ON CONFLICT(audio_id) DO UPDATE SET track_id=excluded.track_id,offset=excluded.offset,rate=excluded.rate",&s)) return database_error(l,e);
  if(!bind_text(s,1,key) || !checkpoint_bind(s,2,p)) { sqlite3_finalize(s); return database_error(l,e); }
  return done(l,s,e);
}
exr_status exr_library_audio_resume_get(exr_library *l,const char *key,exr_audio_checkpoint *out,int *found,exr_error *e) {
  sqlite3_stmt *s=NULL; exr_audio_checkpoint p={0}; exr_status status; int step;
  if(out) memset(out,0,sizeof(*out));
  if(found) *found=0;
  if(!l || !out || !found) return exr_fail(e,EXR_ARGUMENT,"Invalid audio resume query");
  status=audio_string(key,4096,1,NULL,e); if(status!=EXR_OK) return status;
  if(!prepare(l,"SELECT track_id,offset,rate FROM audio_resume WHERE audio_id=?1",&s)) return database_error(l,e);
  if(!bind_text(s,1,key)) { sqlite3_finalize(s); return database_error(l,e); }
  step=sqlite3_step(s);
  if(step==SQLITE_ROW) { status=checkpoint_read(s,0,&p,e); if(status==EXR_OK) { *out=p; memset(&p,0,sizeof(p)); *found=1; } }
  else status=step==SQLITE_DONE ? exr_fail(e,EXR_OK,"") : database_error(l,e);
  sqlite3_finalize(s); exr_audio_checkpoint_free(&p); return status;
}
exr_status exr_library_audio_bookmark(exr_library *l,const char *key,const exr_audio_bookmark *input,int64_t *id,exr_error *e) {
  sqlite3_stmt *s=NULL; exr_audio_bookmark b; exr_status status;
  if(input) b=*input; else memset(&b,0,sizeof(b));
  if(id) *id=0;
  if(!l || !input || !id || b.id<0) return exr_fail(e,EXR_ARGUMENT,"Invalid audio bookmark input");
  if(!b.label) b.label="";
  if((status=audio_string(key,4096,1,NULL,e))!=EXR_OK || (status=audio_string(b.label,65536,0,NULL,e))!=EXR_OK || (status=checkpoint_valid(&b.position,e))!=EXR_OK) return status;
  if(!prepare(l,b.id ? "UPDATE audio_marks SET track_id=?2,offset=?3,rate=?4,label=?5 WHERE audio_id=?1 AND id=?6" : "INSERT INTO audio_marks(audio_id,track_id,offset,rate,label) VALUES(?1,?2,?3,?4,?5)",&s)) return database_error(l,e);
  if(!bind_text(s,1,key) || !checkpoint_bind(s,2,&b.position) || !bind_text(s,5,b.label) || (b.id && sqlite3_bind_int64(s,6,b.id)!=SQLITE_OK)) { sqlite3_finalize(s); return database_error(l,e); }
  status=done(l,s,e);
  if(status==EXR_OK) {
    if(b.id && !sqlite3_changes(l->db)) return exr_fail(e,EXR_ARGUMENT,"Audio bookmark missing or belongs to another audio key");
    *id=b.id ? b.id : sqlite3_last_insert_rowid(l->db);
  }
  return status;
}
void exr_audio_bookmarks_free(exr_audio_bookmark *marks,size_t count) {
  size_t i; if(!marks) return;
  for(i=0;i<count;i++) { free(marks[i].label); exr_audio_checkpoint_free(&marks[i].position); }
  free(marks);
}
exr_status exr_library_audio_bookmarks(exr_library *l,const char *key,exr_audio_bookmark **out,size_t *count,exr_error *e) {
  sqlite3_stmt *s=NULL; exr_audio_bookmark *marks=NULL; size_t n=0,capacity=0,total=0; int step; exr_status status;
  if(out) *out=NULL;
  if(count) *count=0;
  if(!l || !out || !count) return exr_fail(e,EXR_ARGUMENT,"Invalid audio bookmark query");
  status=audio_string(key,4096,1,NULL,e); if(status!=EXR_OK) return status;
  if(!prepare(l,"SELECT id,track_id,offset,rate,label FROM audio_marks WHERE audio_id=?1 ORDER BY id",&s)) return database_error(l,e);
  if(!bind_text(s,1,key)) { status=database_error(l,e); goto finish; }
  while((step=sqlite3_step(s))==SQLITE_ROW) {
    exr_audio_bookmark *b; size_t bytes; exr_error local={0};
    if(n>=100000 || total>=(size_t)64*1024*1024) { status=exr_fail(e,EXR_LIMIT,"Audio bookmarks exceed result budget"); goto finish; }
    if(!exr_grow((void **)&marks,&capacity,n+1,sizeof(*marks))) { status=exr_fail(e,EXR_MEMORY,"Audio bookmark allocation failed"); goto finish; }
    b=&marks[n++]; memset(b,0,sizeof(*b));
    if(sqlite3_column_type(s,0)!=SQLITE_INTEGER || (b->id=sqlite3_column_int64(s,0))<=0) { status=exr_fail(e,EXR_DATABASE,"Invalid stored audio bookmark ID"); goto finish; }
    status=checkpoint_read(s,1,&b->position,e); if(status!=EXR_OK) goto finish;
    status=fixed_column(s,4,SQLITE_TEXT,65536,&b->label,&bytes,e); if(status!=EXR_OK) goto finish;
    if(audio_string(b->label,65536,0,NULL,&local)!=EXR_OK) { status=exr_fail(e,EXR_DATABASE,"Invalid stored audio bookmark label"); goto finish; }
    bytes+=strlen(b->position.track_id)+2+sizeof(*b);
    if(bytes>(size_t)64*1024*1024-total) { status=exr_fail(e,EXR_LIMIT,"Audio bookmarks exceed result byte budget"); goto finish; }
    total+=bytes;
  }
  if(step!=SQLITE_DONE) status=database_error(l,e);
finish:
  sqlite3_finalize(s);
  if(status==EXR_OK) { *out=marks; *count=n; } else exr_audio_bookmarks_free(marks,n);
  return status;
}
exr_status exr_library_remove_audio_bookmark(exr_library *l,int64_t id,exr_error *e) {
  sqlite3_stmt *s=NULL;
  if(!l || id<=0) return exr_fail(e,EXR_ARGUMENT,"Invalid audio bookmark deletion");
  if(!prepare(l,"DELETE FROM audio_marks WHERE id=?1",&s)) return database_error(l,e);
  if(sqlite3_bind_int64(s,1,id)!=SQLITE_OK) { sqlite3_finalize(s); return database_error(l,e); }
  return done(l,s,e);
}
exr_status exr_library_clear_audio(exr_library *l,const char *key,exr_error *e) {
  sqlite3_stmt *s=NULL; exr_status status; unsigned i;
  const char *queries[2]={"DELETE FROM audio_resume WHERE audio_id=?1","DELETE FROM audio_marks WHERE audio_id=?1"};
  if(!l) return exr_fail(e,EXR_ARGUMENT,"Missing audio library");
  status=audio_string(key,4096,1,NULL,e); if(status!=EXR_OK) return status;
  if(operation_begin(l)!=SQLITE_OK) return database_error(l,e);
  for(i=0;i<2;i++) {
    if(!prepare(l,queries[i],&s) || !bind_text(s,1,key)) { status=database_error(l,e); sqlite3_finalize(s); goto rollback; }
    status=done(l,s,e); if(status!=EXR_OK) goto rollback;
  }
  if(operation_commit(l)==SQLITE_OK) return exr_fail(e,EXR_OK,"");
  status=database_error(l,e);
rollback:
  operation_rollback(l); return status;
}

void exr_library_relocation_free(exr_library_relocation *r) { if(r) { free(r->notes); memset(r,0,sizeof(*r)); } }
exr_status exr_library_reanchor(exr_library *l,int64_t book,size_t fallback,const exr_control *control,
                                   exr_library_relocation *out,exr_error *e) {
  exr_library_relocation r={0}; exr_document *doc=NULL; exr_anchor progress={0},captured={0}; exr_anchor_state stored;
  exr_note note={0};sqlite3_mutex *mutex;sqlite3_stmt *read=NULL,*move=NULL,*mark=NULL,*s=NULL; size_t capacity=0,i; int step,transaction=0; exr_status status;
  const size_t maximum=EXR_MAX_TEXT/sizeof(exr_note_relocation); const char *text;
  if(out) memset(out,0,sizeof(*out));
  if(!l || book<=0 || !out) return exr_fail(e,EXR_ARGUMENT,"Invalid book reanchor arguments");
  status=exr_control_cancel(control,e); if(status!=EXR_OK) return status;
  mutex=sqlite3_db_mutex(l->db);sqlite3_mutex_enter(mutex);
  if(operation_begin(l)!=SQLITE_OK) { status=database_error(l,e);goto finish; }
  transaction=1;
  status=require_global_storage(l,book,e);if(status!=EXR_OK) goto finish;
  if(!prepare(l,"SELECT text_size,position FROM books WHERE id=?1",&s) || sqlite3_bind_int64(s,1,book)!=SQLITE_OK) { status=database_error(l,e); goto finish; }
  step=sqlite3_step(s); if(step!=SQLITE_ROW) { status=step==SQLITE_DONE ? exr_fail(e,EXR_ARGUMENT,"Book missing") : database_error(l,e); goto finish; }
  if(!offset_column(s,0,&r.previous_size) || !offset_column(s,1,&r.previous_position) || r.previous_size>EXR_MAX_TEXT || r.previous_position>r.previous_size) { status=exr_fail(e,EXR_DATABASE,"Invalid stored book extent"); goto finish; }
  sqlite3_finalize(s); s=NULL;
  status=exr_library_progress_get(l,book,&progress,&stored,e); if(status!=EXR_OK) goto finish;
  status=exr_library_document(l,book,&doc,e); if(status!=EXR_OK) goto finish;
  text=exr_document_text(doc,&r.text_size);
  if(fallback>r.text_size || (fallback<r.text_size && ((unsigned char)text[fallback]&0xc0)==0x80)) { status=exr_fail(e,EXR_ARGUMENT,"Fallback progress is not a valid UTF-8 boundary"); goto finish; }
  status=exr_anchor_resolve_ex(doc,&progress,control,&r.progress,e); if(status!=EXR_OK) goto finish;
  r.position=r.progress.state==EXR_ANCHOR_FOUND ? r.progress.start : fallback;
  if(!prepare(l,"SELECT id FROM notes WHERE book_id=?1 ORDER BY id",&s) || sqlite3_bind_int64(s,1,book)!=SQLITE_OK) { status=database_error(l,e); goto finish; }
  while((step=sqlite3_step(s))==SQLITE_ROW) {
    exr_note_relocation *entry; int64_t id;
    if(sqlite3_column_type(s,0)!=SQLITE_INTEGER || (id=sqlite3_column_int64(s,0))<=0) { status=exr_fail(e,EXR_DATABASE,"Invalid stored note ID"); goto finish; }
    if(r.note_count==maximum) { status=exr_fail(e,EXR_LIMIT,"Relocation report exceeds 64 MiB"); goto finish; }
    if(r.note_count==capacity) {
      size_t next=capacity ? capacity*2 : 64; exr_note_relocation *copy; if(next>maximum) next=maximum;
      copy=realloc(r.notes,next*sizeof(*copy)); if(!copy) { status=exr_fail(e,EXR_MEMORY,"Relocation report allocation failed"); goto finish; } r.notes=copy; capacity=next;
    }
    entry=&r.notes[r.note_count++]; memset(entry,0,sizeof(*entry)); entry->note_id=id; entry->match=(exr_anchor_match){EXR_ANCHOR_MISSING,SIZE_MAX,SIZE_MAX};
    if(!(r.note_count%256)) { status=exr_control_poll(control,EXR_STAGE_READ,r.note_count,0,e); if(status!=EXR_OK) goto finish; }
  }
  if(step!=SQLITE_DONE) { status=database_error(l,e); goto finish; }
  sqlite3_finalize(s); s=NULL;
  /* Collect IDs first, then fetch only one selector at a time. Comments are not
     copied into migration memory and are never rewritten during relocation. */
  if(!prepare(l,"SELECT n.id,n.book_id,n.start,n.end,'',n.anchor_exact,n.anchor_prefix,n.anchor_suffix,n.anchor_chapter,b.text_size,n.location_state FROM notes n JOIN books b ON b.id=n.book_id WHERE n.book_id=?1 AND n.id=?2",&read) || sqlite3_bind_int64(read,1,book)!=SQLITE_OK ||
     !prepare(l,"UPDATE notes SET start=?1,end=?2,anchor_exact=?3,anchor_prefix=?4,anchor_suffix=?5,anchor_chapter=?6,location_state=1 WHERE id=?7 AND book_id=?8",&move) ||
     !prepare(l,"UPDATE notes SET location_state=?1 WHERE id=?2 AND book_id=?3",&mark)) { status=database_error(l,e); goto finish; }
  for(i=0;i<r.note_count;i++) {
    exr_note_relocation *entry=&r.notes[i];
    status=exr_control_poll(control,EXR_STAGE_READ,i,r.note_count,e); if(status!=EXR_OK) goto finish;
    if(sqlite3_bind_int64(read,2,entry->note_id)!=SQLITE_OK || sqlite3_step(read)!=SQLITE_ROW) { status=database_error(l,e); goto finish; }
    status=read_note(read,&note,e); sqlite3_reset(read); if(status!=EXR_OK) goto finish;
    entry->previous_start=note.anchor.start; entry->previous_end=note.anchor.end;
    status=exr_anchor_resolve_ex(doc,&note.anchor,control,&entry->match,e); if(status!=EXR_OK) goto finish;
    if(entry->match.state==EXR_ANCHOR_FOUND) {
      status=exr_anchor_create(doc,entry->match.start,entry->match.end,&captured,e); if(status!=EXR_OK) goto finish;
      if(sqlite3_bind_int64(move,1,(sqlite3_int64)captured.start)!=SQLITE_OK || sqlite3_bind_int64(move,2,(sqlite3_int64)captured.end)!=SQLITE_OK ||
         !bind_nullable_text(move,3,captured.exact) || !bind_nullable_text(move,4,captured.prefix) || !bind_nullable_text(move,5,captured.suffix) || !bind_nullable_text(move,6,captured.chapter) ||
         sqlite3_bind_int64(move,7,entry->note_id)!=SQLITE_OK || sqlite3_bind_int64(move,8,book)!=SQLITE_OK || sqlite3_step(move)!=SQLITE_DONE) { status=database_error(l,e); goto finish; }
      sqlite3_reset(move); sqlite3_clear_bindings(move); exr_anchor_free(&captured);
    } else {
      if(sqlite3_bind_int(mark,1,entry->match.state)!=SQLITE_OK || sqlite3_bind_int64(mark,2,entry->note_id)!=SQLITE_OK || sqlite3_bind_int64(mark,3,book)!=SQLITE_OK || sqlite3_step(mark)!=SQLITE_DONE) { status=database_error(l,e); goto finish; }
      sqlite3_reset(mark); sqlite3_clear_bindings(mark);
    }
    free(note.text); note.text=NULL; exr_anchor_free(&note.anchor);
  }
  if(!prepare(l,"UPDATE books SET text_size=?1,position=?2 WHERE id=?3",&s) || sqlite3_bind_int64(s,1,(sqlite3_int64)r.text_size)!=SQLITE_OK || sqlite3_bind_int64(s,2,(sqlite3_int64)r.position)!=SQLITE_OK || sqlite3_bind_int64(s,3,book)!=SQLITE_OK) { status=database_error(l,e); goto finish; }
  status=done(l,s,e); s=NULL; if(status!=EXR_OK) goto finish;
  if(r.progress.state==EXR_ANCHOR_FOUND) {
    status=exr_anchor_create(doc,r.position,r.position,&captured,e); if(status==EXR_OK) status=store_progress(l,book,&captured,EXR_ANCHOR_FOUND,e);
  } else status=store_progress(l,book,&progress,r.progress.state,e);
  if(status!=EXR_OK) goto finish;
  status=exr_control_poll(control,EXR_STAGE_READ,r.note_count,r.note_count,e); if(status!=EXR_OK) goto finish;
  if(operation_commit(l)!=SQLITE_OK) { status=database_error(l,e); goto finish; }
  transaction=0; *out=r; memset(&r,0,sizeof(r)); status=exr_fail(e,EXR_OK,"");
finish:
  sqlite3_finalize(s); sqlite3_finalize(read); sqlite3_finalize(move); sqlite3_finalize(mark);
  if(transaction) operation_rollback(l);
  free(note.text); exr_anchor_free(&note.anchor); exr_anchor_free(&captured); exr_anchor_free(&progress); exr_document_free(doc); exr_library_relocation_free(&r);
  sqlite3_mutex_leave(mutex);return status;
}
