/* SPDX-License-Identifier: MIT */
#include <exr/library.h>
#include <exreader-product/catalog.h>
#include <sqlite3.h>
#include <stdio.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
#endif
#ifdef __APPLE__
#include <mach-o/dyld.h>
#endif

static int visit(void *context, const reader_catalog_row *row) {
    (void)row;
    ++*(int *)context;
    return 0;
}

int main(void) {
    exr_library *sdk = NULL;
    exr_error error = {0};
    reader_catalog *product = NULL;
    reader_catalog_error product_error = {0};
    sqlite3 *db = NULL;
    sqlite3_stmt *stmt = NULL;
    int rows = 0;
    if (strcmp(exr_version(), EXR_VERSION) != 0) return 13;
    if (exr_library_open(":memory:", &sdk, &error) != EXR_OK) return 1;
    if (reader_catalog_open(":memory:", &product, &product_error) != 0) return 2;
    if (sqlite3_open(":memory:", &db) != SQLITE_OK) return 3;
    if (sqlite3_exec(db, "CREATE VIRTUAL TABLE f USING fts5(value);"
        "INSERT INTO f VALUES('one shared implementation');", NULL, NULL, NULL) != SQLITE_OK) return 4;
    exr_library_close(sdk);
    if (reader_catalog_page(product, NULL, NULL, 10, visit, &rows, &product_error) != 0 || rows != 0) return 5;
    if (reader_catalog_close(&product, &product_error) != 0) return 6;
    if (sqlite3_prepare_v2(db, "SELECT value FROM f WHERE f MATCH 'shared'", -1,
                         &stmt, NULL) != SQLITE_OK) return 7;
    if (sqlite3_step(stmt) != SQLITE_ROW ||
        strcmp((const char *)sqlite3_column_text(stmt, 0), "one shared implementation")) return 8;
#ifdef _WIN32
    HMODULE provider = GetModuleHandleW(L"libreader_sqlite3.dll");
    if (!provider) provider = GetModuleHandleW(L"reader_sqlite3.dll");
    if (!provider || (int (*)(void))GetProcAddress(provider, "sqlite3_libversion_number") != sqlite3_libversion_number)
        return 9;
    char provider_path[32768];
    if (!GetModuleFileNameA(provider, provider_path, sizeof(provider_path))) return 11;
    printf("loaded_sqlite_provider=%s\n", provider_path);
#endif
#ifdef __APPLE__
    unsigned providers = 0;
    for (uint32_t i = 0; i < _dyld_image_count(); ++i) {
        const char *name = _dyld_get_image_name(i);
        if (name && (strstr(name, "libreader_sqlite3") || strstr(name, "ReaderSQLite.framework/"))) {
            ++providers;
            printf("loaded_sqlite_provider=%s\n", name);
        }
    }
    if (providers != 1) return 12;
#endif
    if (sqlite3_finalize(stmt) != SQLITE_OK || sqlite3_close(db) != SQLITE_OK) return 10;
    puts("Installed dynamic SDK, ProductCatalog and FTS5 share the public provider");
    return 0;
}
