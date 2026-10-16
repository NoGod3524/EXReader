/* SPDX-License-Identifier: GPL-3.0-only */
#include "exreader.h"
#include <sqlite3.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define CHECK(x)                                                                                   \
  do {                                                                                             \
    if (!(x)) {                                                                                    \
      fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #x);                                  \
      exit(1);                                                                                     \
    }                                                                                              \
    checks++;                                                                                      \
  } while (0)
#define OK(x)                                                                                      \
  do {                                                                                             \
    exr_status status = (x);                                                                        \
    if (status != EXR_OK) {                                                                         \
      fprintf(stderr, "FAIL %s:%d: %s (%d: %s)\n", __FILE__, __LINE__, #x, (int)status,               \
              error.message);                                                                      \
      exit(1);                                                                                     \
    }                                                                                              \
    checks++;                                                                                      \
  } while (0)
static unsigned checks;
static exr_error error;
static char database[4096], backup[4096], broken[4096];
static const char sample[] = "First \xE4\xB8\xAD\xE6\x96\x87 last.\nSecond anchor target.\nTail.";
static sqlite3 *open_sql(const char *path) {
  sqlite3 *sql = NULL;
  CHECK(sqlite3_open(path, &sql) == SQLITE_OK);
  return sql;
}
static void execute(sqlite3 *sql, const char *command) {
  char *message = NULL;
  int result = sqlite3_exec(sql, command, NULL, NULL, &message);
  if (result != SQLITE_OK)
    fprintf(stderr, "SQL: %s: %s\n", command, message ? message : "unknown error");
  sqlite3_free(message);
  CHECK(result == SQLITE_OK);
}
static int scalar(sqlite3 *sql, const char *command) {
  sqlite3_stmt *statement = NULL;
  int value;
  CHECK(sqlite3_prepare_v2(sql, command, -1, &statement, NULL) == SQLITE_OK);
  CHECK(sqlite3_step(statement) == SQLITE_ROW);
  value = sqlite3_column_int(statement, 0);
  CHECK(sqlite3_finalize(statement) == SQLITE_OK);
  return value;
}
static void create_v1(const char *path) {
  sqlite3 *sql;
  sqlite3_stmt *statement = NULL;
  remove(path);
  sql = open_sql(path);
  execute(sql, "CREATE TABLE books(id INTEGER PRIMARY KEY,format INTEGER NOT NULL,"
               "title TEXT NOT NULL,author TEXT NOT NULL DEFAULT '',tags TEXT NOT NULL DEFAULT '',"
               "favorite INTEGER NOT NULL DEFAULT 0,status INTEGER NOT NULL DEFAULT 0,"
               "position INTEGER NOT NULL DEFAULT 0,text_size INTEGER NOT NULL,"
               "source BLOB NOT NULL,cover BLOB);"
               "CREATE TABLE notes(id INTEGER PRIMARY KEY,book_id INTEGER NOT NULL REFERENCES "
               "books(id) ON DELETE CASCADE,start INTEGER NOT NULL CHECK(start>=0),"
               "end INTEGER NOT NULL CHECK(end>=start),text TEXT NOT NULL);"
               "CREATE INDEX notes_book ON notes(book_id);"
               "PRAGMA application_id=1163416131;PRAGMA user_version=1;");
  CHECK(sqlite3_prepare_v2(sql, "INSERT INTO books(id,format,title,text_size,source)"
                              "VALUES(1,?1,'Legacy book',?2,?3)", -1, &statement, NULL) == SQLITE_OK);
  CHECK(sqlite3_bind_int(statement, 1, EXR_TXT) == SQLITE_OK);
  CHECK(sqlite3_bind_int64(statement, 2, (sqlite3_int64)strlen(sample)) == SQLITE_OK);
  CHECK(sqlite3_bind_blob(statement, 3, sample, (int)strlen(sample), SQLITE_TRANSIENT) == SQLITE_OK);
  CHECK(sqlite3_step(statement) == SQLITE_DONE);
  CHECK(sqlite3_finalize(statement) == SQLITE_OK);
  execute(sql, "INSERT INTO notes VALUES(1,1,1,4,'Legacy annotation')");
  CHECK(sqlite3_close(sql) == SQLITE_OK);
}
static exr_note *get_notes(exr_library *library, size_t expected) {
  exr_note *notes = NULL;
  size_t count = SIZE_MAX;
  OK(exr_library_notes(library, 1, &notes, &count, &error));
  CHECK(count == expected);
  return notes;
}
static int same_string(const char *a, const char *b) {
  return a && b ? !strcmp(a, b) : a == b;
}
static void same_anchor(const exr_anchor *a, const exr_anchor *b) {
  CHECK(a->start == b->start && a->end == b->end);
  CHECK(same_string(a->exact, b->exact));
  CHECK(same_string(a->prefix, b->prefix));
  CHECK(same_string(a->suffix, b->suffix));
  CHECK(same_string(a->chapter, b->chapter));
}
static void test_migration_and_notes(void) {
  exr_library *library = NULL, *restored = NULL;
  exr_document *doc = NULL;
  exr_note *notes, edit = {0};
  exr_anchor expected = {0};
  exr_anchor_match match;
  const char *text;
  size_t start;
  int64_t id, book;
  sqlite3 *sql;
  create_v1(database);
  OK(exr_library_open(database, &library, &error));
  notes = get_notes(library, 1);
  CHECK(notes[0].id == 1 && notes[0].start == 1 && notes[0].end == 4);
  CHECK(notes[0].anchor.start == 1 && notes[0].anchor.end == 4);
  CHECK(!notes[0].anchor.exact && !notes[0].anchor.prefix && !notes[0].anchor.suffix &&
        !notes[0].anchor.chapter);
  OK(exr_library_document(library, 1, &doc, &error));
  OK(exr_anchor_resolve(doc, &notes[0].anchor, &match, &error));
  CHECK(match.state == EXR_ANCHOR_LEGACY);
  edit.id = 1;
  edit.book_id = 1;
  edit.start = 1;
  edit.end = 4;
  edit.text = "Only annotation text changed";
  OK(exr_library_note(library, &edit, &id, &error));
  CHECK(id == 1);
  exr_notes_free(notes, 1);
  notes = get_notes(library, 1);
  CHECK(!notes[0].anchor.exact && !strcmp(notes[0].text, edit.text));
  exr_notes_free(notes, 1);
  /* Only an explicit selector upgrades unchanged legacy offsets. */
  OK(exr_anchor_create(doc, edit.start, edit.end, &edit.anchor, &error));
  OK(exr_library_note(library, &edit, &id, &error));
  notes = get_notes(library, 1);
  same_anchor(&notes[0].anchor, &edit.anchor);
  CHECK(!strcmp(notes[0].anchor.exact, "irs"));
  exr_notes_free(notes, 1);
  exr_anchor_free(&edit.anchor);
  text = exr_document_text(doc, NULL);
  start = (size_t)(strstr(text, "anchor") - text);
  memset(&edit, 0, sizeof(edit));
  edit.book_id = 1;
  edit.start = start;
  edit.end = start + 6;
  edit.text = "New automatic selector";
  OK(exr_anchor_create(doc, edit.start, edit.end, &expected, &error));
  OK(exr_library_note(library, &edit, &id, &error));
  CHECK(id == 2);
  notes = get_notes(library, 2);
  same_anchor(&notes[1].anchor, &expected);
  CHECK(!strcmp(notes[1].anchor.exact, "anchor"));
  exr_notes_free(notes, 2);
  /* A bare legacy-compatible call preserves all four stored selectors. */
  edit.id = id;
  edit.text = "Edited without passing selector";
  OK(exr_library_note(library, &edit, &id, &error));
  notes = get_notes(library, 2);
  same_anchor(&notes[1].anchor, &expected);
  CHECK(!strcmp(notes[1].text, edit.text));
  exr_notes_free(notes, 2);
  remove(backup);
  OK(exr_library_backup(library, backup, &error));
  exr_library_close(library);
  library = NULL;
  OK(exr_library_open(database, &library, &error));
  notes = get_notes(library, 2);
  same_anchor(&notes[1].anchor, &expected);
  exr_notes_free(notes, 2);
  OK(exr_library_open(backup, &restored, &error));
  notes = get_notes(restored, 2);
  same_anchor(&notes[1].anchor, &expected);
  exr_notes_free(notes, 2);
  exr_library_close(restored);
  /* Moving the range explicitly captures the current document. */
  edit.end = edit.start + 3;
  OK(exr_library_note(library, &edit, &id, &error));
  notes = get_notes(library, 2);
  CHECK(!strcmp(notes[1].anchor.exact, "anc"));
  CHECK(notes[1].anchor.start == edit.start && notes[1].anchor.end == edit.end);
  exr_notes_free(notes, 2);
  /* Point bookmarks also retain context and can be persisted. */
  edit.start = edit.end;
  OK(exr_library_note(library, &edit, &id, &error));
  notes = get_notes(library, 2);
  CHECK(notes[1].anchor.exact && !notes[1].anchor.exact[0]);
  CHECK(notes[1].anchor.prefix && notes[1].anchor.suffix);
  OK(exr_anchor_resolve(doc, &notes[1].anchor, &match, &error));
  CHECK(match.state == EXR_ANCHOR_FOUND && match.start == edit.start && match.end == edit.end);
  exr_notes_free(notes, 2);
  /* Input selectors must agree with the note and satisfy UTF-8/length rules. */
  edit.anchor.start = edit.start;
  edit.anchor.end = edit.end;
  edit.anchor.exact = "wrong length";
  CHECK(exr_library_note(library, &edit, &id, &error) != EXR_OK && id == 0);
  edit.anchor.exact = "";
  edit.anchor.start--;
  CHECK(exr_library_note(library, &edit, &id, &error) == EXR_ARGUMENT);
  memset(&edit.anchor, 0, sizeof(edit.anchor));
  edit.id = 0;
  edit.start = 0;
  edit.end = 1;
  edit.anchor.start = 0;
  edit.anchor.end = 1;
  edit.anchor.exact = "\xff";
  CHECK(exr_library_note(library, &edit, &id, &error) != EXR_OK);
  memset(&edit.anchor, 0, sizeof(edit.anchor));
  edit.start = 7; /* Middle of the first Chinese character. */
  edit.end = 9;
  CHECK(exr_library_note(library, &edit, &id, &error) == EXR_ARGUMENT);
  edit.start = 0;
  edit.end = strlen(sample) + 1;
  CHECK(exr_library_note(library, &edit, &id, &error) == EXR_ARGUMENT);
  edit.start = edit.end = SIZE_MAX;
  CHECK(exr_library_note(library, &edit, &id, &error) == EXR_ARGUMENT);
  CHECK(exr_library_note(library, NULL, &id, &error) == EXR_ARGUMENT);
  OK(exr_library_import(library, EXR_TXT, sample, strlen(sample), "Other", &book, &error));
  memset(&edit, 0, sizeof(edit));
  edit.id = 1;
  edit.book_id = book;
  edit.text = "Wrong book";
  CHECK(exr_library_note(library, &edit, &id, &error) == EXR_ARGUMENT);
  OK(exr_library_remove_note(library, 2, &error));
  notes = get_notes(library, 1);
  exr_notes_free(notes, 1);
  OK(exr_library_delete(library, 1, &error));
  notes = get_notes(library, 0);
  exr_notes_free(notes, 0);
  exr_anchor_free(&expected);
  exr_document_free(doc);
  exr_library_close(library);
  sql = open_sql(database);
  CHECK(scalar(sql, "PRAGMA user_version") == 2);
  CHECK(scalar(sql, "SELECT count(*) FROM notes") == 0);
  CHECK(sqlite3_close(sql) == SQLITE_OK);
}
static void test_corruption(void) {
  const char *damage[] = {
      "start=-1", "end=9223372036854775807", "end=1.5", "start='NaN'",
      "anchor_exact=X'697273'", "anchor_exact=CAST(X'FFFFFF' AS TEXT)",
      "anchor_exact='different length'", "anchor_prefix=CAST(X'FF' AS TEXT)",
      "anchor_suffix=CAST(X'610062' AS TEXT)", "anchor_chapter=X'3432'",
      "anchor_exact=replace(hex(zeroblob(65537)),'00','a')",
      "anchor_prefix=replace(hex(zeroblob(33)),'00','a')",
      "anchor_suffix=replace(hex(zeroblob(129)),'00','a')",
      "anchor_chapter=replace(hex(zeroblob(2047)),'00','a')",
      "anchor_exact=NULL,anchor_prefix='orphan'"};
  size_t i;
  sqlite3 *sql;
  exr_library *library = NULL;
  exr_note *notes = NULL, edit = {0};
  size_t count;
  int64_t id;
  create_v1(broken);
  OK(exr_library_open(broken, &library, &error));
  edit.id = 1;
  edit.book_id = 1;
  edit.start = 1;
  edit.end = 4;
  edit.text = "Upgrade";
  edit.anchor.start = 1;
  edit.anchor.end = 4;
  edit.anchor.exact = "irs";
  OK(exr_library_note(library, &edit, &id, &error));
  exr_library_close(library);
  for (i = 0; i < sizeof(damage) / sizeof(*damage); i++) {
    char command[1024];
    sql = open_sql(broken);
    execute(sql, "PRAGMA ignore_check_constraints=ON;UPDATE notes SET start=1,end=4,"
                 "anchor_exact='irs',anchor_prefix='',anchor_suffix='',anchor_chapter=NULL");
    snprintf(command, sizeof(command), "UPDATE notes SET %s", damage[i]);
    execute(sql, command);
    CHECK(sqlite3_close(sql) == SQLITE_OK);
    OK(exr_library_open(broken, &library, &error));
    notes = NULL;
    count = SIZE_MAX;
    CHECK(exr_library_notes(library, 1, &notes, &count, &error) == EXR_DATABASE);
    CHECK(!notes && count == 0);
    CHECK(exr_library_note(library, &edit, &id, &error) == EXR_DATABASE);
    exr_library_close(library);
  }
}
static void test_migration_rollback(void) {
  sqlite3 *sql;
  exr_library *library = NULL;
  create_v1(broken);
  sql = open_sql(broken);
  /* The third ALTER fails after earlier ALTERs succeed. All must roll back. */
  execute(sql, "ALTER TABLE notes ADD COLUMN anchor_suffix TEXT");
  CHECK(sqlite3_close(sql) == SQLITE_OK);
  CHECK(exr_library_open(broken, &library, &error) == EXR_DATABASE && !library);
  sql = open_sql(broken);
  CHECK(scalar(sql, "PRAGMA user_version") == 1);
  CHECK(scalar(sql, "SELECT count(*) FROM pragma_table_info('notes') "
                    "WHERE name='anchor_exact'") == 0);
  CHECK(scalar(sql, "SELECT count(*) FROM notes WHERE id=1 AND start=1 AND end=4 "
                    "AND text='Legacy annotation'") == 1);
  execute(sql, "PRAGMA user_version=99");
  CHECK(sqlite3_close(sql) == SQLITE_OK);
  CHECK(exr_library_open(broken, &library, &error) == EXR_DATABASE && !library);
  remove(broken);
  OK(exr_library_open(broken, &library, &error));
  exr_library_close(library);
  sql = open_sql(broken);
  CHECK(scalar(sql, "PRAGMA user_version") == 2);
  CHECK(scalar(sql, "SELECT count(*) FROM pragma_table_info('notes') "
                    "WHERE name LIKE 'anchor_%'") == 4);
  CHECK(sqlite3_close(sql) == SQLITE_OK);
}
int main(int argc, char **argv) {
  CHECK(argc == 2);
  snprintf(database, sizeof(database), "%s/anchor-library.sqlite", argv[1]);
  snprintf(backup, sizeof(backup), "%s/anchor-backup.sqlite", argv[1]);
  snprintf(broken, sizeof(broken), "%s/anchor-broken.sqlite", argv[1]);
  test_migration_and_notes();
  test_corruption();
  test_migration_rollback();
  printf("EXReader stable annotation library: %u checks passed\n", checks);
  return 0;
}
