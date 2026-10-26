/* Actions-only public SDK and actual product catalog repair profiling. */
#define _CRT_SECURE_NO_WARNINGS
#include "catalog_sdk.h"
#include <sqlite3.h>
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static unsigned long long sql_ns, commit_ns, commit_count, statement_count;
static int trace(unsigned kind, void *context, void *statement, void *duration) {
  (void)context;
  if (kind == SQLITE_TRACE_PROFILE) {
    sqlite3_stmt *stmt = (sqlite3_stmt *)statement;
    const char *dbpath = sqlite3_db_filename(sqlite3_db_handle(stmt), "main");
    const char *sql = sqlite3_sql(stmt);
    if (dbpath && strstr(dbpath, "product.sqlite") && sql) {
      unsigned long long ns = *(sqlite3_uint64 *)duration;
      sql_ns += ns; statement_count++;
      if (!strcmp(sql, "COMMIT")) { commit_ns += ns; commit_count++; }
    }
  }
  return 0;
}
static int instrument(sqlite3 *db, char **message, const sqlite3_api_routines *api) {
  (void)message; (void)api;
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
  REQUIRE(argc == 3);
  REQUIRE(sqlite3_auto_extension((void (*)(void))instrument) == SQLITE_OK);
  begin = millis();
  REQUIRE(exr_library_open(argv[1], &library, &error) == EXR_OK);
  REQUIRE(reader_catalog_open(argv[2], &catalog, NULL) == SQLITE_OK);
  opened = millis();
  REQUIRE(exr_library_books(library, "", &books, &count, &error) == EXR_OK && count == 2202);
  listed = millis();
  sql_ns = commit_ns = commit_count = statement_count = 0;
  repair_start = millis();
  REQUIRE(reader_catalog_sdk_repair(catalog, library, books, count, NULL, &failed, &error) == EXR_OK && failed == 0);
  repaired = millis();
  printf("{\"books\":%zu,\"open_ms\":%.3f,\"enumerate_ms\":%.3f,\"repair_ms\":%.3f,"
         "\"sql_profile_ms\":%.3f,\"commit_profile_ms\":%.3f,\"commit_count\":%llu,\"statement_count\":%llu}\n",
         count, opened-begin, listed-opened, repaired-repair_start, (double)sql_ns/1000000.0,
         (double)commit_ns/1000000.0, commit_count, statement_count);
  REQUIRE(reader_catalog_close(&catalog, NULL) == SQLITE_OK);
  exr_books_free(books,count); exr_library_close(library);
  return 0;
}
