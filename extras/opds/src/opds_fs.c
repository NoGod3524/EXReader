/* SPDX-License-Identifier: MIT */
/* Small file-system shims (UTF-8 paths on Windows, atomic publication). */
#include "opds_internal.h"
#include "opds_fs.h"
#include <errno.h>

#ifdef _WIN32
#include <windows.h>
#include <io.h>
#include <stdio.h>
static wchar_t *wide(const char *s) {
  int n = MultiByteToWideChar(CP_UTF8, 0, s, -1, NULL, 0);
  wchar_t *w;
  if (n <= 0) return NULL;
  w = (wchar_t *)malloc((size_t)n * sizeof *w);
  if (w) MultiByteToWideChar(CP_UTF8, 0, s, -1, w, n);
  return w;
}
FILE *opds_fopen_new(const char *path) {
  wchar_t *w = wide(path);
  FILE *f = NULL;
  if (!w) return NULL;
  if (_wfopen_s(&f, w, L"wbx") != 0) f = NULL;
  free(w);
  return f;
}
FILE *opds_fopen_read(const char *path) {
  wchar_t *w = wide(path);
  FILE *f = NULL;
  if (!w) return NULL;
  if (_wfopen_s(&f, w, L"rb") != 0) f = NULL;
  free(w);
  return f;
}
int opds_remove(const char *path) {
  wchar_t *w = wide(path);
  int r;
  if (!w) return -1;
  r = DeleteFileW(w) ? 0 : -1;
  free(w);
  return r;
}
int opds_path_kind(const char *path) {
  wchar_t *w = wide(path);
  DWORD a;
  if (!w) return -1;
  a = GetFileAttributesW(w);
  free(w);
  if (a == INVALID_FILE_ATTRIBUTES) return 0;
  if (a & FILE_ATTRIBUTE_REPARSE_POINT) return 3;
  return (a & FILE_ATTRIBUTE_DIRECTORY) ? 2 : 1;
}
int opds_publish(const char *tmp, const char *dest, int replace) {
  wchar_t *a = wide(tmp), *b = wide(dest);
  int r = -1;
  if (a && b) {
    if (MoveFileExW(a, b, replace ? (MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH) : MOVEFILE_WRITE_THROUGH)) r = 0;
    else { DWORD e = GetLastError(); r = (e == ERROR_ALREADY_EXISTS || e == ERROR_FILE_EXISTS) ? 1 : -1; }
  }
  free(a); free(b);
  return r;
}
int opds_sync(FILE *f) { return _commit(_fileno(f)); }
#else
#include <sys/stat.h>
#include <unistd.h>
FILE *opds_fopen_new(const char *path) { return fopen(path, "wbx"); }
FILE *opds_fopen_read(const char *path) { return fopen(path, "rb"); }
int opds_remove(const char *path) { return unlink(path); }
int opds_path_kind(const char *path) {
  struct stat st;
  if (lstat(path, &st) != 0) return errno == ENOENT ? 0 : -1;
  if (S_ISLNK(st.st_mode)) return 3;
  if (S_ISDIR(st.st_mode)) return 2;
  return S_ISREG(st.st_mode) ? 1 : 3;
}
int opds_publish(const char *tmp, const char *dest, int replace) {
  if (replace) return rename(tmp, dest) == 0 ? 0 : -1;
  if (link(tmp, dest) == 0) { unlink(tmp); return 0; }
  if (errno == EEXIST) return 1;
  /* No atomic no-replace operation is available here. A check followed by
     rename could overwrite a file another writer just published. */
  return -1;
}
int opds_sync(FILE *f) { return fsync(fileno(f)); }
#endif
