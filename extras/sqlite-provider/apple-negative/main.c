/* SPDX-License-Identifier: MIT */
#include <exr/library.h>
#include <sqlite3.h>

int main(void) {
    exr_library *sdk = 0;
    exr_error error = {0};
    sqlite3 *db = 0;
    if (exr_library_open(":memory:", &sdk, &error) != EXR_OK) return 1;
    if (sqlite3_open(":memory:", &db) != SQLITE_OK) return 2;
    sqlite3_close(db);
    exr_library_close(sdk);
    return 0;
}
