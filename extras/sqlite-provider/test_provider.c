/* SPDX-License-Identifier: MIT */
#include <sqlite3.h>
#include <stdio.h>
#include <string.h>

int main(void) {
    sqlite3 *db = NULL;
    sqlite3_stmt *stmt = NULL;
    if (!sqlite3_compileoption_used("ENABLE_FTS5") ||
        !sqlite3_compileoption_used("OMIT_LOAD_EXTENSION") || sqlite3_threadsafe() != 1)
        return 1;
    if (sqlite3_open(":memory:", &db) != SQLITE_OK) return 2;
    if (sqlite3_exec(db, "CREATE VIRTUAL TABLE books USING fts5(title);"
        "INSERT INTO books VALUES('shared provider');", NULL, NULL, NULL) != SQLITE_OK)
        return 3;
    if (sqlite3_prepare_v2(db, "SELECT title FROM books WHERE books MATCH 'shared'", -1,
                         &stmt, NULL) != SQLITE_OK) return 4;
    if (sqlite3_step(stmt) != SQLITE_ROW ||
        strcmp((const char *)sqlite3_column_text(stmt, 0), "shared provider") != 0) return 5;
    if (sqlite3_finalize(stmt) != SQLITE_OK || sqlite3_close(db) != SQLITE_OK) return 6;
    puts("Shared SQLite provider: FTS5 and public API passed");
    return 0;
}
