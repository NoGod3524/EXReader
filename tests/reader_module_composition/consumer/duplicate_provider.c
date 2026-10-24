/* SPDX-License-Identifier: MIT */
/* Negative control only: a second, conflicting definition of the product
   SQLite entry point. Linking this object file into the composed consumer must
   be refused by the linker, so "two SQLite providers" can never pass a gate. */
typedef struct sqlite3 sqlite3;
int sqlite3_open_v2(const char *filename, sqlite3 **database, int flags, const char *vfs) {
  (void)filename;
  (void)database;
  (void)flags;
  (void)vfs;
  return 14; /* SQLITE_CANTOPEN */
}
