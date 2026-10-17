/* SPDX-License-Identifier: GPL-3.0-only */
#include "internal.h"
#include <sqlite3.h>
struct exr_library {
  sqlite3 *db;
};
void exr_free(void *p) { free(p); }
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
                       "anchor_chapter TEXT);"
                       "CREATE INDEX IF NOT EXISTS notes_book ON notes(book_id);PRAGMA "
                       "application_id=1163416131;PRAGMA user_version=2;COMMIT;";
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
          "PRAGMA user_version=2;COMMIT;";
      if (sqlite3_exec(l->db, migration, NULL, NULL, NULL) != SQLITE_OK) {
        database_error(l, e);
        sqlite3_exec(l->db, "ROLLBACK", NULL, NULL, NULL);
        exr_library_close(l);
        return EXR_DATABASE;
      }
      *out = l;
      return EXR_OK;
    }
    if (app == 1163416131 && version == 2) {
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
  exr_document *d = NULL;
  exr_status result;
  void *cover=NULL; size_t cover_size=0;
  if (!l || !id)
    return exr_fail(e, EXR_ARGUMENT, "Invalid import arguments");
  *id = 0;
  result = exr_document_open_memory(format, data, n, &d, e);
  if (result != EXR_OK)
    return result;
  result=import_cover(d,&cover,&cover_size,e);
  if(result!=EXR_OK) goto cleanup;
  if (!prepare(l, "INSERT INTO books(format,title,text_size,source,cover)VALUES(?1,?2,?3,?4,?5)", &s)) {
    result=database_error(l,e); goto cleanup;
  }
  if(sqlite3_bind_int(s, 1, format)!=SQLITE_OK || !bind_text(s, 2,
            title && title[0] ? title
                              : (exr_document_title(d)[0] ? exr_document_title(d) : "Untitled")) ||
     sqlite3_bind_int64(s, 3, (sqlite3_int64)d->size)!=SQLITE_OK ||
     sqlite3_bind_blob(s, 4, data, (int)n, SQLITE_TRANSIENT)!=SQLITE_OK ||
     (cover ? sqlite3_bind_blob(s,5,cover,(int)cover_size,SQLITE_STATIC) : sqlite3_bind_null(s,5))!=SQLITE_OK) {
    result=database_error(l,e); sqlite3_finalize(s); goto cleanup;
  }
  result = done(l, s, e);
  if (result == EXR_OK)
    *id = sqlite3_last_insert_rowid(l->db);
cleanup:
  free(cover); exr_document_free(d);
  return result;
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
  *out = exr_copy(text, (size_t)bytes);
  return *out ? EXR_OK : exr_fail(e, EXR_MEMORY, "Annotation allocation failed");
}
/* Columns: id, book_id, start, end, text, four selectors, book text_size. */
static exr_status read_note(sqlite3_stmt *s, exr_note *note, exr_error *e) {
  exr_error validation;
  exr_status result;
  size_t text_size;
  memset(note, 0, sizeof(*note));
  if (sqlite3_column_type(s, 0) != SQLITE_INTEGER ||
      sqlite3_column_type(s, 1) != SQLITE_INTEGER ||
      (note->id = sqlite3_column_int64(s, 0)) <= 0 ||
      (note->book_id = sqlite3_column_int64(s, 1)) <= 0 ||
      !offset_column(s, 2, &note->start) || !offset_column(s, 3, &note->end) ||
      !offset_column(s, 9, &text_size) || text_size > EXR_MAX_TEXT ||
      note->start > note->end || note->end > text_size)
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
  return EXR_OK;
}
static int bind_nullable_text(sqlite3_stmt *s, int column, const char *text) {
  return text ? bind_text(s, column, text) : sqlite3_bind_null(s, column) == SQLITE_OK;
}
exr_status exr_library_note(exr_library *l, const exr_note *note, int64_t *id, exr_error *e) {
  sqlite3_stmt *s = NULL;
  exr_document *doc = NULL;
  exr_anchor captured = {0};
  exr_note snapshot;
  const exr_anchor *anchor;
  exr_status result;
  size_t text_size, note_size = 0;
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
  while (note_size <= EXR_MAX_TEXT && note->text[note_size])
    note_size++;
  if (note_size > EXR_MAX_TEXT)
    return exr_fail(e, EXR_LIMIT, "Annotation text exceeds 64 MiB");
  anchor = &note->anchor;
  if (anchor->exact) {
    if (anchor->start != note->start || anchor->end != note->end)
      return exr_fail(e, EXR_ARGUMENT, "Annotation selector and range differ");
    result = exr_anchor_validate(anchor, e);
    if (result != EXR_OK)
      return result;
  }
  if (!prepare(l, "SELECT text_size FROM books WHERE id=?1", &s))
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
                 "n.anchor_suffix,n.anchor_chapter,b.text_size FROM notes n "
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
                                "anchor_prefix=?7,anchor_suffix=?8,anchor_chapter=?9 "
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
               "n.anchor_suffix,n.anchor_chapter,b.text_size FROM notes n JOIN books b "
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
