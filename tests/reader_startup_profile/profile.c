/* Actions-only public SDK and actual product catalog repair profiling. */
#define _CRT_SECURE_NO_WARNINGS
#include "catalog_sdk.h"
#include <sqlite3.h>
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static unsigned long long sql_ns, commit_ns, commit_count, statement_count;
static int persist_set;
static sqlite3 *product_db;
static int trace(unsigned kind, void *context, void *statement, void *duration) {
  (void)context;
  if (kind == SQLITE_TRACE_PROFILE) {
    sqlite3_stmt *stmt = (sqlite3_stmt *)statement;
    const char *dbpath = sqlite3_db_filename(sqlite3_db_handle(stmt), "main");
    const char *sql = sqlite3_sql(stmt);
    if (dbpath && strstr(dbpath, "product-") && sql) {
      unsigned long long ns = *(sqlite3_uint64 *)duration;
      sql_ns += ns; statement_count++;
      if (!strcmp(sql, "COMMIT")) { commit_ns += ns; commit_count++; }
    }
  }
  return 0;
}
static int instrument(sqlite3 *db, char **message, const sqlite3_api_routines *api) {
  const char *path = sqlite3_db_filename(db, "main");
  (void)message; (void)api;
  if (path && strstr(path, "product-")) product_db = db;
  if (path && strstr(path, "product-") && getenv("EXR_PROFILE_PERSIST")) {
    sqlite3_stmt *stmt = NULL;
    int rc = sqlite3_prepare_v2(db, "PRAGMA journal_mode=PERSIST", -1, &stmt, NULL);
    if (rc == SQLITE_OK && sqlite3_step(stmt) == SQLITE_ROW) {
      const char *mode = (const char *)sqlite3_column_text(stmt, 0);
      persist_set = mode && !strcmp(mode, "persist");
    }
    sqlite3_finalize(stmt);
    if (!persist_set) return SQLITE_ERROR;
  }
  return sqlite3_trace_v2(db, SQLITE_TRACE_PROFILE, trace, NULL);
}
static double millis(void) {
  LARGE_INTEGER counter, frequency;
  QueryPerformanceCounter(&counter); QueryPerformanceFrequency(&frequency);
  return 1000.0 * (double)counter.QuadPart / (double)frequency.QuadPart;
}
#define REQUIRE(x) do { if (!(x)) { fprintf(stderr, "failure line %d: %s\n", __LINE__, #x); exit(1); } } while (0)
int main(int argc, char **argv) {
  exr_library *library = NULL; exr_error error = {0}; reader_catalog *catalog = NULL;
  exr_book *books = NULL; size_t count = 0, failed = 0;
  double begin, opened, listed, repair_start, repaired;
  sqlite3 *verify = NULL; sqlite3_stmt *check = NULL;
  int first, synchronous;
  char journal_mode[32];
  REQUIRE(argc == 4);
  first = !strcmp(argv[3], "first");
  REQUIRE(first || !strcmp(argv[3], "repeat"));
  REQUIRE(sqlite3_auto_extension((void (*)(void))instrument) == SQLITE_OK);
  begin = millis();
  REQUIRE(exr_library_open(argv[1], &library, &error) == EXR_OK);
  REQUIRE(reader_catalog_open(argv[2], &catalog, NULL) == SQLITE_OK);
  REQUIRE(persist_set == (getenv("EXR_PROFILE_PERSIST") != NULL));
  opened = millis();
  REQUIRE(exr_library_books(library, "", &books, &count, &error) == EXR_OK && count == 2202);
  listed = millis();
  sql_ns = commit_ns = commit_count = statement_count = 0;
  repair_start = millis();
  REQUIRE(reader_catalog_sdk_repair(catalog, library, books, count, NULL, &failed, &error) == EXR_OK && failed == 0);
  repaired = millis();
  REQUIRE(statement_count > 0 && commit_count == (first ? 2202 : 0));
  REQUIRE(product_db != NULL);
  REQUIRE(sqlite3_prepare_v2(product_db, "PRAGMA synchronous", -1, &check, NULL) == SQLITE_OK);
  REQUIRE(sqlite3_step(check) == SQLITE_ROW);
  synchronous = sqlite3_column_int(check, 0);
  REQUIRE(sqlite3_finalize(check) == SQLITE_OK);
  REQUIRE(synchronous == 2);
  REQUIRE(sqlite3_prepare_v2(product_db, "PRAGMA journal_mode", -1, &check, NULL) == SQLITE_OK);
  REQUIRE(sqlite3_step(check) == SQLITE_ROW);
  snprintf(journal_mode, sizeof(journal_mode), "%s", (const char *)sqlite3_column_text(check, 0));
  REQUIRE(sqlite3_finalize(check) == SQLITE_OK);
  REQUIRE(!getenv("EXR_EXPECT_MODE") || !strcmp(journal_mode, getenv("EXR_EXPECT_MODE")));
  REQUIRE(reader_catalog_close(&catalog, NULL) == SQLITE_OK);
  REQUIRE(sqlite3_cancel_auto_extension((void (*)(void))instrument) == 1);
  REQUIRE(sqlite3_open_v2(argv[2], &verify, SQLITE_OPEN_READONLY, NULL) == SQLITE_OK);
  REQUIRE(sqlite3_trace_v2(verify, 0, NULL, NULL) == SQLITE_OK);
  REQUIRE(sqlite3_prepare_v2(verify, "SELECT count(*),count(DISTINCT l.sdk_book_id),sum(CASE WHEN b.book_key IS NOT NULL AND b.deleted=0 THEN 1 ELSE 0 END) FROM reader_local_books l LEFT JOIN reader_books b ON b.book_key=l.book_key", -1, &check, NULL) == SQLITE_OK);
  REQUIRE(sqlite3_step(check) == SQLITE_ROW);
  REQUIRE(sqlite3_column_int(check, 0) == 2202 && sqlite3_column_int(check, 1) == 2202 && sqlite3_column_int(check, 2) == 2202);
  REQUIRE(sqlite3_finalize(check) == SQLITE_OK);
  REQUIRE(sqlite3_prepare_v2(verify, "PRAGMA integrity_check", -1, &check, NULL) == SQLITE_OK);
  REQUIRE(sqlite3_step(check) == SQLITE_ROW && !strcmp((const char *)sqlite3_column_text(check, 0), "ok"));
  REQUIRE(sqlite3_finalize(check) == SQLITE_OK);
  REQUIRE(sqlite3_close(verify) == SQLITE_OK);
  printf("{\"books\":%zu,\"persist\":%d,\"journal_mode\":\"%s\",\"synchronous\":%d,\"open_ms\":%.3f,\"enumerate_ms\":%.3f,\"repair_ms\":%.3f,"
         "\"sql_profile_ms\":%.3f,\"commit_profile_ms\":%.3f,\"commit_count\":%llu,\"statement_count\":%llu}\n",
         count, persist_set, journal_mode, synchronous, opened-begin, listed-opened, repaired-repair_start, (double)sql_ns/1000000.0,
         (double)commit_ns/1000000.0, commit_count, statement_count);
  exr_books_free(books,count); exr_library_close(library);
  return 0;
}
