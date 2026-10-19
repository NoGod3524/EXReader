/* SPDX-License-Identifier: MIT */
#include "formats_internal.h"
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
struct exr_library {
  sqlite3 *db;
};
static exr_status database_error(exr_library *l, exr_error *e) {
  return exr_fail(e, EXR_DATABASE, "%s", sqlite3_errmsg(l->db));
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
exr_status exr_library_open(const char *path, exr_library **out, exr_error *e) {
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
                       "application_id=1163416131;" FIXED_SCHEMA AUDIO_SCHEMA PROGRESS_SCHEMA "PRAGMA user_version=6;COMMIT;";
  if (!path || !out)
    return exr_fail(e, EXR_ARGUMENT, "Invalid library arguments");
  *out = NULL;
  l = calloc(1, sizeof(*l));
  if (!l)
    return exr_fail(e, EXR_MEMORY, "Library allocation failed");
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
  {
    int app = scalar(l->db, "PRAGMA application_id"),
        version = scalar(l->db, "PRAGMA user_version");
    if (app == 1163416131 && version == 1) {
      const char *migration =
          "BEGIN IMMEDIATE;ALTER TABLE notes ADD COLUMN anchor_exact TEXT;"
          "ALTER TABLE notes ADD COLUMN anchor_prefix TEXT;"
          "ALTER TABLE notes ADD COLUMN anchor_suffix TEXT;"
          "ALTER TABLE notes ADD COLUMN anchor_chapter TEXT;"
          FIXED_SCHEMA AUDIO_SCHEMA PROGRESS_SCHEMA LOCATION_SCHEMA "PRAGMA user_version=6;COMMIT;";
      if (sqlite3_exec(l->db, migration, NULL, NULL, NULL) != SQLITE_OK) {
        database_error(l, e);
        sqlite3_exec(l->db, "ROLLBACK", NULL, NULL, NULL);
        exr_library_close(l);
        return EXR_DATABASE;
      }
      *out = l;
      return EXR_OK;
    }
    if(app==1163416131 && version==2) {
      if(sqlite3_exec(l->db,"BEGIN IMMEDIATE;" FIXED_SCHEMA AUDIO_SCHEMA PROGRESS_SCHEMA LOCATION_SCHEMA "PRAGMA user_version=6;COMMIT;",NULL,NULL,NULL)!=SQLITE_OK) {
        database_error(l,e); sqlite3_exec(l->db,"ROLLBACK",NULL,NULL,NULL); exr_library_close(l); return EXR_DATABASE;
      }
      *out=l; return EXR_OK;
    }
    if(app==1163416131 && version==3) {
      if(sqlite3_exec(l->db,"BEGIN IMMEDIATE;" AUDIO_SCHEMA PROGRESS_SCHEMA LOCATION_SCHEMA "PRAGMA user_version=6;COMMIT;",NULL,NULL,NULL)!=SQLITE_OK) {
        database_error(l,e); sqlite3_exec(l->db,"ROLLBACK",NULL,NULL,NULL); exr_library_close(l); return EXR_DATABASE;
      }
      *out=l; return EXR_OK;
    }
    if(app==1163416131 && version==4) {
      if(sqlite3_exec(l->db,"BEGIN IMMEDIATE;" PROGRESS_SCHEMA LOCATION_SCHEMA "PRAGMA user_version=6;COMMIT;",NULL,NULL,NULL)!=SQLITE_OK) {
        database_error(l,e); sqlite3_exec(l->db,"ROLLBACK",NULL,NULL,NULL); exr_library_close(l); return EXR_DATABASE;
      }
      *out=l; return EXR_OK;
    }
    if(app==1163416131 && version==5) {
      const char *migration="BEGIN IMMEDIATE;DROP TRIGGER books_progress_changed;ALTER TABLE book_progress RENAME TO book_progress_v5;"
        PROGRESS_SCHEMA "INSERT INTO book_progress SELECT * FROM book_progress_v5;DROP TABLE book_progress_v5;" LOCATION_SCHEMA "PRAGMA user_version=6;COMMIT;";
      if(sqlite3_exec(l->db,migration,NULL,NULL,NULL)!=SQLITE_OK) { database_error(l,e); sqlite3_exec(l->db,"ROLLBACK",NULL,NULL,NULL); exr_library_close(l); return EXR_DATABASE; }
      *out=l; return EXR_OK;
    }
    if (app == 1163416131 && version == 6) {
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
  if (sqlite3_exec(l->db, schema, NULL, NULL, NULL) != SQLITE_OK) {
    database_error(l, e);
    sqlite3_exec(l->db, "ROLLBACK", NULL, NULL, NULL);
    exr_library_close(l);
    return EXR_DATABASE;
  }
  *out = l;
  return EXR_OK;
}
void exr_library_close(exr_library *l) {
  if (l) {
    if (l->db)
      sqlite3_close_v2(l->db);
    free(l);
  }
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
  if(sqlite3_exec(l->db,"BEGIN IMMEDIATE",NULL,NULL,NULL)!=SQLITE_OK) { status=database_error(l,e); goto finish; }
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
  if(sqlite3_exec(l->db,"COMMIT",NULL,NULL,NULL)!=SQLITE_OK) { status=database_error(l,e); goto finish; }
  transaction=0; *id=found; *created=inserted;
finish:
  sqlite3_finalize(s);
  if(transaction) sqlite3_exec(l->db,"ROLLBACK",NULL,NULL,NULL);
  sqlite3_mutex_leave(sqlite3_db_mutex(l->db));
  return status==EXR_OK ? exr_fail(e,EXR_OK,"") : status;
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
  exr_status result;
  if (!l || !b || b->id <= 0 || !b->title || !b->title[0] || b->position > INT64_MAX ||
      (b->favorite != 0 && b->favorite != 1) || b->status < 0 || b->status > 2)
    return exr_fail(e, EXR_ARGUMENT, "Invalid metadata or position");
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
static exr_status store_progress(exr_library *l,int64_t book,const exr_anchor *point,exr_anchor_state state,exr_error *e) {
  sqlite3_stmt *s=NULL;
  if(!prepare(l,"INSERT INTO book_progress(book_id,position,state,prefix,suffix,chapter)VALUES(?1,?2,?3,?4,?5,?6) ON CONFLICT(book_id) DO UPDATE SET position=excluded.position,state=excluded.state,prefix=excluded.prefix,suffix=excluded.suffix,chapter=excluded.chapter",&s) ||
     sqlite3_bind_int64(s,1,book)!=SQLITE_OK || sqlite3_bind_int64(s,2,(sqlite3_int64)point->start)!=SQLITE_OK || sqlite3_bind_int(s,3,state)!=SQLITE_OK || !bind_nullable_text(s,4,point->prefix) || !bind_nullable_text(s,5,point->suffix) || !bind_nullable_text(s,6,point->chapter)) { sqlite3_finalize(s); return database_error(l,e); }
  return done(l,s,e);
}
exr_status exr_library_progress(exr_library *l,int64_t book,const exr_anchor *point,exr_error *e) {
  sqlite3_stmt *s=NULL; exr_status status; size_t extent; int step,format,transaction=0;
  if(!l || book<=0 || !point || !point->exact || point->exact[0] || point->start!=point->end || point->start==SIZE_MAX || point->start>INT64_MAX)
    return exr_fail(e,EXR_ARGUMENT,"Reading progress requires a finite point selector");
  status=exr_anchor_validate(point,e); if(status!=EXR_OK) return status;
  if(sqlite3_exec(l->db,"BEGIN IMMEDIATE",NULL,NULL,NULL)!=SQLITE_OK) return database_error(l,e);
  transaction=1;
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
  if(sqlite3_exec(l->db,"COMMIT",NULL,NULL,NULL)!=SQLITE_OK) { status=database_error(l,e); goto finish; }
  transaction=0; status=exr_fail(e,EXR_OK,"");
finish:
  sqlite3_finalize(s); if(transaction) sqlite3_exec(l->db,"ROLLBACK",NULL,NULL,NULL); return status;
}
exr_status exr_library_progress_get(exr_library *l,int64_t book,exr_anchor *out,exr_anchor_state *state,exr_error *e) {
  sqlite3_stmt *s=NULL; exr_anchor a={0}; exr_error local={0}; exr_status status; size_t position,extent; int step,format,value;
  if(out) memset(out,0,sizeof(*out));
  if(state) *state=EXR_ANCHOR_MISSING;
  if(!l || book<=0 || !out || !state) return exr_fail(e,EXR_ARGUMENT,"Invalid reading progress query");
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
  sqlite3_stmt *s=NULL;
  if(!l || book<=0) return exr_fail(e,EXR_ARGUMENT,"Invalid reading selector removal");
  if(!prepare(l,"DELETE FROM book_progress WHERE book_id=?1",&s) || sqlite3_bind_int64(s,1,book)!=SQLITE_OK) { sqlite3_finalize(s); return database_error(l,e); }
  return done(l,s,e);
}
exr_status exr_library_note(exr_library *l, const exr_note *note, int64_t *id, exr_error *e) {
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
  return remove_id(l, id, 0, e);
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
  if(sqlite3_exec(l->db,"BEGIN IMMEDIATE",NULL,NULL,NULL)!=SQLITE_OK) return database_error(l,e);
  for(i=0;i<2;i++) {
    if(!prepare(l,queries[i],&s) || !bind_text(s,1,key)) { status=database_error(l,e); sqlite3_finalize(s); goto rollback; }
    status=done(l,s,e); if(status!=EXR_OK) goto rollback;
  }
  if(sqlite3_exec(l->db,"COMMIT",NULL,NULL,NULL)==SQLITE_OK) return exr_fail(e,EXR_OK,"");
  status=database_error(l,e);
rollback:
  sqlite3_exec(l->db,"ROLLBACK",NULL,NULL,NULL); return status;
}

void exr_library_relocation_free(exr_library_relocation *r) { if(r) { free(r->notes); memset(r,0,sizeof(*r)); } }
exr_status exr_library_reanchor(exr_library *l,int64_t book,size_t fallback,const exr_control *control,
                                   exr_library_relocation *out,exr_error *e) {
  exr_library_relocation r={0}; exr_document *doc=NULL; exr_anchor progress={0},captured={0}; exr_anchor_state stored;
  exr_note note={0}; sqlite3_stmt *read=NULL,*move=NULL,*mark=NULL,*s=NULL; size_t capacity=0,i; int step,transaction=0; exr_status status;
  const size_t maximum=EXR_MAX_TEXT/sizeof(exr_note_relocation); const char *text;
  if(out) memset(out,0,sizeof(*out));
  if(!l || book<=0 || !out) return exr_fail(e,EXR_ARGUMENT,"Invalid book reanchor arguments");
  status=exr_control_cancel(control,e); if(status!=EXR_OK) return status;
  if(sqlite3_exec(l->db,"BEGIN IMMEDIATE",NULL,NULL,NULL)!=SQLITE_OK) return database_error(l,e);
  transaction=1;
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
  if(sqlite3_exec(l->db,"COMMIT",NULL,NULL,NULL)!=SQLITE_OK) { status=database_error(l,e); goto finish; }
  transaction=0; *out=r; memset(&r,0,sizeof(r)); status=exr_fail(e,EXR_OK,"");
finish:
  sqlite3_finalize(s); sqlite3_finalize(read); sqlite3_finalize(move); sqlite3_finalize(mark);
  if(transaction) sqlite3_exec(l->db,"ROLLBACK",NULL,NULL,NULL);
  free(note.text); exr_anchor_free(&note.anchor); exr_anchor_free(&captured); exr_anchor_free(&progress); exr_document_free(doc); exr_library_relocation_free(&r); return status;
}
