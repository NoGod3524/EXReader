/* SPDX-License-Identifier: MIT */
#if !defined(_WIN32) && !defined(_XOPEN_SOURCE)
#define _XOPEN_SOURCE 700
#endif
#if defined(__APPLE__) && !defined(_DARWIN_C_SOURCE)
#define _DARWIN_C_SOURCE
#endif
#include "convert_io.h"
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <wctype.h>
#ifdef __APPLE__
#include <mach/mach.h>
#include <malloc/malloc.h>
#endif
#ifdef _WIN32
#include <windows.h>
#include <psapi.h>
#else
#include <fcntl.h>
#include <sys/resource.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>
#endif

void cv_release_unused_memory(void) {
#ifdef __APPLE__
  (void)malloc_zone_pressure_relief(NULL, 0);
#endif
}

/* Opt-in allocator diagnostics (EXR_CONVERT_MEM_DIAG=1): stderr only, never part of the report. */
void cv_memory_diag(const char *label, size_t index) {
#ifdef __APPLE__
  mach_task_basic_info_data_t info;
  mach_msg_type_number_t count = MACH_TASK_BASIC_INFO_COUNT;
  malloc_statistics_t stats;
  const char *on = getenv("EXR_CONVERT_MEM_DIAG");
  if (!on || !*on || *on == '0') return;
  memset(&stats, 0, sizeof(stats));
  malloc_zone_statistics(NULL, &stats);
  if (task_info(mach_task_self(), MACH_TASK_BASIC_INFO, (task_info_t)&info, &count) != KERN_SUCCESS)
    memset(&info, 0, sizeof(info));
  fprintf(stderr, "mem-diag item=%zu %s resident=%llu peak=%llu malloc_in_use=%zu malloc_allocated=%zu blocks=%u
",
          index, label, (unsigned long long)info.resident_size,
          (unsigned long long)cv_peak_rss(), stats.size_in_use, stats.size_allocated,
          stats.blocks_in_use);
#else
  (void)label; (void)index;
#endif
}

static char *copy_bytes(const char *s, size_t n) {
  char *p = malloc(n + 1);
  if (!p) return NULL;
  memcpy(p, s, n);
  p[n] = 0;
  return p;
}
static char *copy_string(const char *s) { return s ? copy_bytes(s, strlen(s)) : NULL; }
static void set_error(char **error, const char *text) {
  if (error && !*error) *error = copy_string(text);
}
#ifdef _WIN32
static wchar_t *wide(const char *s) {
  int n;
  wchar_t *w;
  if (!s) return NULL;
  n = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, s, -1, NULL, 0);
  if (n <= 0 || !(w = malloc((size_t)n * sizeof(*w)))) return NULL;
  if (!MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, s, -1, w, n)) {
    free(w);
    return NULL;
  }
  return w;
}
static char *narrow(const wchar_t *w) {
  int n;
  char *s;
  if (!w) return NULL;
  n = WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, w, -1, NULL, 0, NULL, NULL);
  if (n <= 0 || !(s = malloc((size_t)n))) return NULL;
  if (!WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, w, -1, s, n, NULL, NULL)) {
    free(s);
    return NULL;
  }
  return s;
}
static char *windows_error(const char *prefix, DWORD code) {
  char text[512], *out;
  DWORD n = FormatMessageA(FORMAT_MESSAGE_FROM_SYSTEM | FORMAT_MESSAGE_IGNORE_INSERTS,
                           NULL, code, 0, text, sizeof(text), NULL);
  if (n) while (n && (text[n - 1] == '\r' || text[n - 1] == '\n')) text[--n] = 0;
  else snprintf(text, sizeof(text), "Windows error %lu", (unsigned long)code);
  out = malloc(strlen(prefix) + n + 4);
  if (out) sprintf(out, "%s: %s", prefix, text);
  return out;
}
static void set_win_error(char **error, const char *prefix, DWORD code) {
  if (error && !*error) *error = windows_error(prefix, code);
}
#endif

int cv_path_equal(const char *a, const char *b) {
  if (!a || !b) return a == b;
#ifdef _WIN32
  return _stricmp(a, b) == 0;
#else
  return strcmp(a, b) == 0;
#endif
}
int cv_is_absolute(const char *path) {
  if (!path || !*path) return 0;
#ifdef _WIN32
  if (((path[0] >= 'A' && path[0] <= 'Z') || (path[0] >= 'a' && path[0] <= 'z')) &&
      path[1] == ':')
    return 1;
  if (path[0] == '\\' || path[0] == '/') return 1;
  return 0;
#else
  return path[0] == '/';
#endif
}
char *cv_join(const char *base, const char *path) {
  size_t a, b;
  char *out;
  if (!path) return NULL;
  if (cv_is_absolute(path) || !base || !*base) return copy_string(path);
  a = strlen(base);
  b = strlen(path);
  out = malloc(a + b + 2);
  if (!out) return NULL;
  memcpy(out, base, a);
#ifdef _WIN32
  if (a && base[a - 1] != '\\' && base[a - 1] != '/') out[a++] = '\\';
#else
  if (a && base[a - 1] != '/') out[a++] = '/';
#endif
  memcpy(out + a, path, b + 1);
  return out;
}
char *cv_basename(const char *path) {
  const char *p, *last = path;
  if (!path) return NULL;
  for (p = path; *p; p++)
    if (*p == '/' || *p == '\\') last = p + 1;
  return copy_string(last);
}
char *cv_dirname(const char *path) {
  const char *p, *last = NULL;
  size_t n;
  if (!path) return NULL;
  for (p = path; *p; p++)
    if (*p == '/' || *p == '\\') last = p;
  if (!last) return copy_string(".");
  n = (size_t)(last - path);
  if (!n) n = 1;
#ifdef _WIN32
  if (n == 2 && path[1] == ':') n = 3;
#endif
  return copy_bytes(path, n);
}
const char *cv_extension(const char *path) {
  const char *base = path, *p, *dot = NULL;
  if (!path) return "";
  for (p = path; *p; p++)
    if (*p == '/' || *p == '\\') base = p + 1;
  for (p = base; *p; p++)
    if (*p == '.') dot = p;
  return dot ? dot + 1 : "";
}
char *cv_replace_extension(const char *path, const char *extension) {
  const char *base = path, *p, *dot = NULL;
  size_t n;
  char *out;
  if (!path) return NULL;
  for (p = path; *p; p++)
    if (*p == '/' || *p == '\\') base = p + 1;
  for (p = base; *p; p++)
    if (*p == '.') dot = p;
  n = dot ? (size_t)(dot - path) : strlen(path);
  out = malloc(n + strlen(extension) + 2);
  if (!out) return NULL;
  memcpy(out, path, n);
  out[n] = '.';
  strcpy(out + n + 1, extension);
  return out;
}

#ifdef _WIN32
static wchar_t *final_handle_path(HANDLE h) {
  DWORD cap = 512, n;
  wchar_t *w = NULL;
  for (;;) {
    wchar_t *next = realloc(w, (size_t)cap * sizeof(*w));
    if (!next) { free(w); return NULL; }
    w = next;
    n = GetFinalPathNameByHandleW(h, w, cap, FILE_NAME_NORMALIZED | VOLUME_NAME_DOS);
    if (!n) { free(w); return NULL; }
    if (n < cap) break;
    cap = n + 1;
  }
  if (n >= 4 && !wcsncmp(w, L"\\\\?\\", 4)) {
    if (!wcsncmp(w + 4, L"UNC\\", 4)) {
      size_t len = wcslen(w + 7);
      memmove(w, w + 7, (len + 1) * sizeof(*w));
      w[0] = L'\\'; w[1] = L'\\';
    } else {
      size_t len = wcslen(w + 4);
      memmove(w, w + 4, (len + 1) * sizeof(*w));
    }
  }
  return w;
}
int cv_identity(const char *path, cv_file_id *id, char **error) {
  wchar_t *w; HANDLE h; BY_HANDLE_FILE_INFORMATION info;
  memset(id, 0, sizeof(*id));
  if (!(w = wide(path))) { set_error(error, "Path is not valid UTF-8"); return 0; }
  /* Follow reparse points: a symlink/junction to the source is the same file. */
  h = CreateFileW(w, 0, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, NULL,
                  OPEN_EXISTING, FILE_FLAG_BACKUP_SEMANTICS, NULL);
  if (h == INVALID_HANDLE_VALUE) {
    DWORD code = GetLastError();
    free(w);
    if (code == ERROR_FILE_NOT_FOUND || code == ERROR_PATH_NOT_FOUND) return 1;
    set_win_error(error, "Cannot inspect path", code);
    return 0;
  }
  free(w);
  if (!GetFileInformationByHandle(h, &info)) {
    set_win_error(error, "Cannot query file identity", GetLastError());
    CloseHandle(h);
    return 0;
  }
  CloseHandle(h);
  id->exists = 1;
  id->is_dir = (info.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) != 0;
  id->is_file = !id->is_dir;
  id->volume = info.dwVolumeSerialNumber;
  id->index = ((uint64_t)info.nFileIndexHigh << 32) | info.nFileIndexLow;
  return 1;
}
char *cv_absolute(const char *path, char **error) {
  wchar_t *w, *full = NULL, *final = NULL;
  DWORD cap, n;
  char *out = NULL;
  HANDLE h;
  if (!(w = wide(path))) { set_error(error, "Path is not valid UTF-8"); return NULL; }
  cap = GetFullPathNameW(w, 0, NULL, NULL);
  if (!cap || !(full = malloc((size_t)cap * sizeof(*full)))) {
    free(w); set_error(error, "Cannot resolve absolute path"); return NULL;
  }
  n = GetFullPathNameW(w, cap, full, NULL);
  free(w);
  if (!n || n >= cap) { free(full); set_error(error, "Cannot resolve absolute path"); return NULL; }
  /* Existing paths are normalized through the filesystem so junctions and
     short names compare equal; missing targets keep their lexical form. */
  h = CreateFileW(full, 0, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, NULL,
                  OPEN_EXISTING, FILE_FLAG_BACKUP_SEMANTICS, NULL);
  if (h != INVALID_HANDLE_VALUE) {
    final = final_handle_path(h);
    CloseHandle(h);
  }
  out = narrow(final ? final : full);
  free(final);
  free(full);
  if (!out) set_error(error, "Cannot encode absolute path");
  return out;
}
int cv_same_file(const char *a, const char *b, int *same, char **error) {
  cv_file_id ia, ib;
  char *na, *nb;
  size_t la, lb;
  *same = 0;
  if (!cv_identity(a, &ia, error) || !cv_identity(b, &ib, error)) return 0;
  if (ia.exists && ib.exists) {
    *same = ia.volume == ib.volume && ia.index == ib.index;
    return 1;
  }
  if (!(na = cv_absolute(a, error))) return 0;
  if (!(nb = cv_absolute(b, error))) { free(na); return 0; }
  /* If a path is missing, its parent may still be an alias of the other
     parent (junction, symlink, 8.3 name). Resolve parent + basename. */
  if (!ia.exists || !ib.exists) {
    char *resolved = NULL;
    if (!ia.exists) {
      char *pa = cv_dirname(na), *ba = cv_basename(na), *fa = cv_absolute(pa, error);
      free(pa); free(na);
      resolved = fa ? cv_join(fa, ba) : NULL;
      free(fa); free(ba); na = resolved;
    }
    if (!ib.exists) {
      char *pb = cv_dirname(nb), *bb = cv_basename(nb), *fb = cv_absolute(pb, error);
      free(pb); free(nb);
      resolved = fb ? cv_join(fb, bb) : NULL;
      free(fb); free(bb); nb = resolved;
    }
    if (!na || !nb) { free(na); free(nb); return 0; }
  }
  la = strlen(na); lb = strlen(nb);
  *same = la == lb && cv_path_equal(na, nb);
  free(na); free(nb);
  return 1;
}
void cv_remove(const char *path) {
  wchar_t *w = wide(path);
  if (w) { DeleteFileW(w); free(w); }
}
int cv_mkdir(const char *path, char **error) {
  wchar_t *w = wide(path);
  if (!w) { set_error(error, "Directory path is not valid UTF-8"); return 0; }
  if (!CreateDirectoryW(w, NULL) && GetLastError() != ERROR_ALREADY_EXISTS) {
    DWORD code = GetLastError();
    free(w);
    set_win_error(error, "Cannot create directory", code);
    return 0;
  }
  free(w);
  return 1;
}
static wchar_t *temp_wide(const wchar_t *target, unsigned attempt) {
  wchar_t *dir = NULL, *name = NULL, *out = NULL, *slash;
  DWORD cap = (DWORD)wcslen(target) + 64;
  size_t dlen;
  name = malloc(cap * sizeof(*name));
  if (!name) return NULL;
  wcscpy(name, target);
  slash = wcsrchr(name, L'\\');
  {
    wchar_t *forward = wcsrchr(name, L'/');
    if (forward && (!slash || forward > slash)) slash = forward;
  }
  if (!slash) { free(name); return NULL; }
  *slash = 0;
  dir = name;
  dlen = wcslen(dir);
  out = malloc((dlen + wcslen(slash + 1) + 48) * sizeof(*out));
  if (out)
    _snwprintf(out, dlen + wcslen(slash + 1) + 48, L"%ls\\.%ls.exreader-%lu-%u.tmp",
               dir, slash + 1, (unsigned long)GetCurrentProcessId(), attempt);
  free(name);
  return out;
}
int cv_write_temp(const char *target, const void *data, size_t size, char **temp, char **error) {
  wchar_t *wt = wide(target);
  unsigned attempt;
  *temp = NULL;
  if (!wt) { set_error(error, "Target path is not valid UTF-8"); return 0; }
  for (attempt = 0; attempt < 1000; attempt++) {
    wchar_t *wtemp = temp_wide(wt, attempt);
    HANDLE h;
    char *utf8;
    if (!wtemp) break;
    h = CreateFileW(wtemp, GENERIC_WRITE, 0, NULL, CREATE_NEW, FILE_ATTRIBUTE_NORMAL, NULL);
    if (h == INVALID_HANDLE_VALUE) {
      DWORD code = GetLastError();
      free(wtemp);
      if (code == ERROR_FILE_EXISTS || code == ERROR_ALREADY_EXISTS) continue;
      set_win_error(error, "Cannot create temporary output", code);
      free(wt);
      return 0;
    }
    utf8 = narrow(wtemp);
    free(wtemp);
    if (!utf8) { CloseHandle(h); set_error(error, "Cannot encode temporary path"); free(wt); return 0; }
    {
      const unsigned char *p = data;
      size_t left = size;
      while (left) {
        DWORD chunk = left > 0x40000000u ? 0x40000000u : (DWORD)left;
        DWORD wrote = 0;
        if (!WriteFile(h, p, chunk, &wrote, NULL) || wrote != chunk) {
          set_win_error(error, "Cannot write temporary output", GetLastError());
          CloseHandle(h); cv_remove(utf8); free(utf8); free(wt); return 0;
        }
        p += wrote; left -= wrote;
      }
      if (!FlushFileBuffers(h)) {
        set_win_error(error, "Cannot flush temporary output", GetLastError());
        CloseHandle(h); cv_remove(utf8); free(utf8); free(wt); return 0;
      }
    }
    if (!CloseHandle(h)) {
      set_win_error(error, "Cannot close temporary output", GetLastError());
      cv_remove(utf8); free(utf8); free(wt); return 0;
    }
    *temp = utf8;
    free(wt);
    return 1;
  }
  free(wt);
  set_error(error, "Cannot allocate a unique temporary output name");
  return 0;
}
int cv_publish(const char *temp, const char *target, int overwrite, char **error) {
  wchar_t *a = wide(temp), *b = wide(target);
  DWORD flags = MOVEFILE_WRITE_THROUGH | (overwrite ? MOVEFILE_REPLACE_EXISTING : 0);
  if (!a || !b) { free(a); free(b); set_error(error, "Publication path is not valid UTF-8"); return 0; }
  if (!MoveFileExW(a, b, flags)) {
    set_win_error(error, overwrite ? "Cannot replace output" : "Output already exists",
                  GetLastError());
    free(a); free(b); return 0;
  }
  free(a); free(b);
  return 1;
}
size_t cv_peak_rss(void) {
  PROCESS_MEMORY_COUNTERS_EX pmc;
  memset(&pmc, 0, sizeof(pmc));
  pmc.cb = sizeof(pmc);
  if (GetProcessMemoryInfo(GetCurrentProcess(), (PROCESS_MEMORY_COUNTERS *)&pmc, sizeof(pmc)))
    return (size_t)pmc.PeakWorkingSetSize;
  return 0;
}
int cv_file_size(const char *path, uint64_t *size, char **error) {
  wchar_t *w = wide(path); WIN32_FILE_ATTRIBUTE_DATA info;
  if (!w) { set_error(error, "Path is not valid UTF-8"); return 0; }
  if (!GetFileAttributesExW(w, GetFileExInfoStandard, &info)) {
    set_win_error(error, "Cannot inspect input", GetLastError());
    free(w); return 0;
  }
  free(w);
  *size = ((uint64_t)info.nFileSizeHigh << 32) | info.nFileSizeLow;
  return 1;
}
int cv_read_prefix(const char *path, void *buffer, size_t capacity, size_t *read, char **error) {
  wchar_t *w = wide(path); HANDLE h; DWORD got = 0;
  *read = 0;
  if (!w) { set_error(error, "Path is not valid UTF-8"); return 0; }
  h = CreateFileW(w, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
                  NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
  free(w);
  if (h == INVALID_HANDLE_VALUE) { set_win_error(error, "Cannot read input", GetLastError()); return 0; }
  if (!ReadFile(h, buffer, (DWORD)(capacity > 0x7fffffff ? 0x7fffffff : capacity), &got, NULL)) {
    set_win_error(error, "Cannot read input", GetLastError());
    CloseHandle(h); return 0;
  }
  CloseHandle(h);
  *read = got;
  return 1;
}
int cv_read_file(const char *path, unsigned char **data, size_t *size, char **error) {
  wchar_t *w = wide(path); HANDLE h; LARGE_INTEGER length; unsigned char *bytes; size_t at = 0;
  *data = NULL; *size = 0;
  if (!w) { set_error(error, "Path is not valid UTF-8"); return 0; }
  h = CreateFileW(w, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
                  NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
  free(w);
  if (h == INVALID_HANDLE_VALUE) { set_win_error(error, "Cannot read file", GetLastError()); return 0; }
  if (!GetFileSizeEx(h, &length) || length.QuadPart < 0 || (uint64_t)length.QuadPart > (uint64_t)SIZE_MAX - 1) {
    set_win_error(error, "Cannot size file", GetLastError());
    CloseHandle(h); return 0;
  }
  bytes = malloc((size_t)length.QuadPart + 1);
  if (!bytes) { CloseHandle(h); set_error(error, "Out of memory"); return 0; }
  while (at < (size_t)length.QuadPart) {
    DWORD chunk = (size_t)length.QuadPart - at > 0x40000000u ? 0x40000000u : (DWORD)((size_t)length.QuadPart - at);
    DWORD got = 0;
    if (!ReadFile(h, bytes + at, chunk, &got, NULL) || !got) {
      set_win_error(error, "Cannot read file", GetLastError());
      CloseHandle(h); free(bytes); return 0;
    }
    at += got;
  }
  CloseHandle(h);
  bytes[at] = 0; *data = bytes; *size = at;
  return 1;
}
void cv_sha256_file_init(void) {}
#else
int cv_identity(const char *path, cv_file_id *id, char **error) {
  struct stat st;
  memset(id, 0, sizeof(*id));
  if (stat(path, &st) != 0) {
    if (errno == ENOENT || errno == ENOTDIR) return 1;
    set_error(error, strerror(errno));
    return 0;
  }
  id->exists = 1;
  id->is_dir = S_ISDIR(st.st_mode);
  id->is_file = S_ISREG(st.st_mode);
  id->volume = (uint64_t)st.st_dev;
  id->index = (uint64_t)st.st_ino;
  return 1;
}
char *cv_absolute(const char *path, char **error) {
  char cwd[4096], *joined, *out;
  if (path[0] == '/') return copy_string(path);
  if (!getcwd(cwd, sizeof(cwd))) { set_error(error, strerror(errno)); return NULL; }
  joined = cv_join(cwd, path);
  if (!joined) { set_error(error, "Cannot allocate path"); return NULL; }
  out = realpath(joined, NULL);
  if (!out) out = copy_string(joined);
  free(joined);
  return out;
}
int cv_same_file(const char *a, const char *b, int *same, char **error) {
  cv_file_id ia, ib;
  char *na, *nb;
  size_t la, lb;
  *same = 0;
  if (!cv_identity(a, &ia, error) || !cv_identity(b, &ib, error)) return 0;
  if (ia.exists && ib.exists) {
    *same = ia.volume == ib.volume && ia.index == ib.index;
    return 1;
  }
  if (!(na = realpath(a, NULL))) na = cv_absolute(a, error);
  if (!(nb = realpath(b, NULL))) nb = cv_absolute(b, error);
  if (!na || !nb) { free(na); free(nb); return 0; }
  if (!ia.exists || !ib.exists) {
    char *resolved = NULL;
    if (!ia.exists) {
      char *pa = cv_dirname(na), *ba = cv_basename(na), *fa = realpath(pa, NULL);
      free(pa); free(na);
      if (!fa) fa = cv_absolute(".", error);
      resolved = fa ? cv_join(fa, ba) : NULL;
      free(fa); free(ba); na = resolved;
    }
    if (!ib.exists) {
      char *pb = cv_dirname(nb), *bb = cv_basename(nb), *fb = realpath(pb, NULL);
      free(pb); free(nb);
      if (!fb) fb = cv_absolute(".", error);
      resolved = fb ? cv_join(fb, bb) : NULL;
      free(fb); free(bb); nb = resolved;
    }
    if (!na || !nb) { free(na); free(nb); return 0; }
  }
  la = strlen(na); lb = strlen(nb);
  *same = la == lb && cv_path_equal(na, nb);
  free(na); free(nb);
  return 1;
}
void cv_remove(const char *path) { unlink(path); }
int cv_mkdir(const char *path, char **error) {
  if (mkdir(path, 0777) != 0 && errno != EEXIST) { set_error(error, strerror(errno)); return 0; }
  return 1;
}
int cv_write_temp(const char *target, const void *data, size_t size, char **temp, char **error) {
  char *dir = cv_dirname(target), *base = cv_basename(target), *name;
  unsigned attempt;
  int fd = -1;
  *temp = NULL;
  if (!dir || !base) { free(dir); free(base); set_error(error, "Cannot allocate path"); return 0; }
  name = malloc(strlen(dir) + strlen(base) + 64);
  if (!name) { free(dir); free(base); set_error(error, "Cannot allocate path"); return 0; }
  for (attempt = 0; attempt < 1000; attempt++) {
    sprintf(name, "%s/.%s.exreader-%lu-%u.tmp", dir, base, (unsigned long)getpid(), attempt);
    fd = open(name, O_WRONLY | O_CREAT | O_EXCL, 0666);
    if (fd >= 0) break;
    if (errno != EEXIST) { set_error(error, strerror(errno)); free(name); free(dir); free(base); return 0; }
  }
  free(dir); free(base);
  if (fd < 0) { set_error(error, "Cannot allocate a unique temporary output name"); free(name); return 0; }
  {
    const unsigned char *p = data;
    size_t left = size;
    while (left) {
      ssize_t n = write(fd, p, left);
      if (n < 0) { if (errno == EINTR) continue; set_error(error, strerror(errno)); close(fd); cv_remove(name); free(name); return 0; }
      p += (size_t)n; left -= (size_t)n;
    }
    if (fsync(fd) != 0) { set_error(error, strerror(errno)); close(fd); cv_remove(name); free(name); return 0; }
  }
  if (close(fd) != 0) { set_error(error, strerror(errno)); cv_remove(name); free(name); return 0; }
  *temp = name;
  return 1;
}
int cv_publish(const char *temp, const char *target, int overwrite, char **error) {
  if (overwrite) {
    if (rename(temp, target) != 0) { set_error(error, strerror(errno)); return 0; }
    return 1;
  }
  if (link(temp, target) != 0) {
    set_error(error, errno == EEXIST ? "Output already exists" : strerror(errno));
    return 0;
  }
  if (unlink(temp) != 0) { set_error(error, strerror(errno)); return 0; }
  return 1;
}
size_t cv_peak_rss(void) {
  struct rusage usage;
  if (getrusage(RUSAGE_SELF, &usage) == 0) {
#ifdef __APPLE__
    return (size_t)usage.ru_maxrss;
#else
    return (size_t)usage.ru_maxrss * 1024u;
#endif
  }
  return 0;
}
int cv_file_size(const char *path, uint64_t *size, char **error) {
  struct stat st;
  if (stat(path, &st) != 0) { set_error(error, strerror(errno)); return 0; }
  *size = (uint64_t)st.st_size;
  return 1;
}
int cv_read_prefix(const char *path, void *buffer, size_t capacity, size_t *read, char **error) {
  FILE *f = fopen(path, "rb");
  size_t n;
  *read = 0;
  if (!f) { set_error(error, strerror(errno)); return 0; }
  n = fread(buffer, 1, capacity, f);
  if (ferror(f)) { set_error(error, strerror(errno)); fclose(f); return 0; }
  fclose(f);
  *read = n;
  return 1;
}
int cv_read_file(const char *path, unsigned char **data, size_t *size, char **error) {
  FILE *f = fopen(path, "rb"); unsigned char *bytes; size_t capacity = 65536, at = 0, n;
  *data = NULL; *size = 0;
  if (!f) { set_error(error, strerror(errno)); return 0; }
  bytes = malloc(capacity + 1);
  if (!bytes) { fclose(f); set_error(error, "Out of memory"); return 0; }
  for (;;) {
    if (at == capacity) {
      unsigned char *next;
      if (capacity > (size_t)-1 / 2) { free(bytes); fclose(f); set_error(error, "File is too large"); return 0; }
      capacity *= 2; next = realloc(bytes, capacity + 1);
      if (!next) { free(bytes); fclose(f); set_error(error, "Out of memory"); return 0; }
      bytes = next;
    }
    n = fread(bytes + at, 1, capacity - at, f);
    at += n;
    if (n == 0) {
      if (ferror(f)) { set_error(error, strerror(errno)); free(bytes); fclose(f); return 0; }
      break;
    }
  }
  fclose(f);
  bytes[at] = 0; *data = bytes; *size = at;
  return 1;
}
#endif

uint64_t cv_now_ms(void) {
#ifdef _WIN32
  return (uint64_t)GetTickCount64();
#else
  struct timespec ts;
  clock_gettime(CLOCK_MONOTONIC, &ts);
  return (uint64_t)ts.tv_sec * 1000u + (uint64_t)ts.tv_nsec / 1000000u;
#endif
}

/* Compact SHA-256 used only for evidence hashes in reports. */
typedef struct { uint32_t h[8]; uint64_t bits; unsigned char block[64]; size_t used; } sha256_ctx;
static uint32_t rotr(uint32_t x, unsigned n) { return (x >> n) | (x << (32 - n)); }
static void sha256_block(sha256_ctx *c, const unsigned char *p) {
  static const uint32_t k[64] = {
      0x428a2f98u,0x71374491u,0xb5c0fbcfu,0xe9b5dba5u,0x3956c25bu,0x59f111f1u,0x923f82a4u,0xab1c5ed5u,
      0xd807aa98u,0x12835b01u,0x243185beu,0x550c7dc3u,0x72be5d74u,0x80deb1feu,0x9bdc06a7u,0xc19bf174u,
      0xe49b69c1u,0xefbe4786u,0x0fc19dc6u,0x240ca1ccu,0x2de92c6fu,0x4a7484aau,0x5cb0a9dcu,0x76f988dau,
      0x983e5152u,0xa831c66du,0xb00327c8u,0xbf597fc7u,0xc6e00bf3u,0xd5a79147u,0x06ca6351u,0x14292967u,
      0x27b70a85u,0x2e1b2138u,0x4d2c6dfcu,0x53380d13u,0x650a7354u,0x766a0abbu,0x81c2c92eu,0x92722c85u,
      0xa2bfe8a1u,0xa81a664bu,0xc24b8b70u,0xc76c51a3u,0xd192e819u,0xd6990624u,0xf40e3585u,0x106aa070u,
      0x19a4c116u,0x1e376c08u,0x2748774cu,0x34b0bcb5u,0x391c0cb3u,0x4ed8aa4au,0x5b9cca4fu,0x682e6ff3u,
      0x748f82eeu,0x78a5636fu,0x84c87814u,0x8cc70208u,0x90befffau,0xa4506cebu,0xbef9a3f7u,0xc67178f2u};
  uint32_t w[64], a, b, cc, d, e, f, g, h;
  unsigned i;
  for (i = 0; i < 16; i++)
    w[i] = ((uint32_t)p[i*4] << 24) | ((uint32_t)p[i*4+1] << 16) |
           ((uint32_t)p[i*4+2] << 8) | p[i*4+3];
  for (i = 16; i < 64; i++) {
    uint32_t s0 = rotr(w[i-15],7) ^ rotr(w[i-15],18) ^ (w[i-15] >> 3);
    uint32_t s1 = rotr(w[i-2],17) ^ rotr(w[i-2],19) ^ (w[i-2] >> 10);
    w[i] = w[i-16] + s0 + w[i-7] + s1;
  }
  a=c->h[0]; b=c->h[1]; cc=c->h[2]; d=c->h[3]; e=c->h[4]; f=c->h[5]; g=c->h[6]; h=c->h[7];
  for (i = 0; i < 64; i++) {
    uint32_t s1 = rotr(e,6) ^ rotr(e,11) ^ rotr(e,25);
    uint32_t ch = (e & f) ^ (~e & g);
    uint32_t t1 = h + s1 + ch + k[i] + w[i];
    uint32_t s0 = rotr(a,2) ^ rotr(a,13) ^ rotr(a,22);
    uint32_t maj = (a & b) ^ (a & cc) ^ (b & cc);
    uint32_t t2 = s0 + maj;
    h=g; g=f; f=e; e=d+t1; d=cc; cc=b; b=a; a=t1+t2;
  }
  c->h[0]+=a; c->h[1]+=b; c->h[2]+=cc; c->h[3]+=d;
  c->h[4]+=e; c->h[5]+=f; c->h[6]+=g; c->h[7]+=h;
}
static void sha256_init(sha256_ctx *c) {
  static const uint32_t init[8] = {0x6a09e667u,0xbb67ae85u,0x3c6ef372u,0xa54ff53au,
                                   0x510e527fu,0x9b05688cu,0x1f83d9abu,0x5be0cd19u};
  memcpy(c->h, init, sizeof(init)); c->bits = 0; c->used = 0;
}
static void sha256_update(sha256_ctx *c, const void *data, size_t n) {
  const unsigned char *p = data;
  c->bits += (uint64_t)n * 8;
  while (n) {
    size_t take = 64 - c->used;
    if (take > n) take = n;
    memcpy(c->block + c->used, p, take);
    c->used += take; p += take; n -= take;
    if (c->used == 64) { sha256_block(c, c->block); c->used = 0; }
  }
}
static void sha256_final(sha256_ctx *c, unsigned char out[32]) {
  unsigned i;
  c->block[c->used++] = 0x80;
  if (c->used > 56) { memset(c->block + c->used, 0, 64 - c->used); sha256_block(c, c->block); c->used = 0; }
  memset(c->block + c->used, 0, 56 - c->used);
  for (i = 0; i < 8; i++) c->block[63-i] = (unsigned char)(c->bits >> (i*8));
  sha256_block(c, c->block);
  for (i = 0; i < 8; i++) {
    out[i*4] = (unsigned char)(c->h[i] >> 24); out[i*4+1] = (unsigned char)(c->h[i] >> 16);
    out[i*4+2] = (unsigned char)(c->h[i] >> 8); out[i*4+3] = (unsigned char)c->h[i];
  }
}
static void hex32(const unsigned char *in, char out[65]) {
  static const char digits[] = "0123456789abcdef";
  unsigned i;
  for (i = 0; i < 32; i++) { out[i*2] = digits[in[i] >> 4]; out[i*2+1] = digits[in[i] & 15]; }
  out[64] = 0;
}
void cv_sha256_hex(const void *data, size_t size, char hex[65]) {
  sha256_ctx c; unsigned char digest[32];
  sha256_init(&c); sha256_update(&c, data, size); sha256_final(&c, digest); hex32(digest, hex);
}
int cv_sha256_file(const char *path, char hex[65], char **error) {
  sha256_ctx c; unsigned char digest[32], buffer[65536];
  FILE *f;
  size_t n;
  sha256_init(&c);
#ifdef _WIN32
  {
    wchar_t *w = wide(path);
    if (!w) { set_error(error, "Path is not valid UTF-8"); return 0; }
    f = _wfopen(w, L"rb");
    free(w);
  }
#else
  f = fopen(path, "rb");
#endif
  if (!f) { set_error(error, strerror(errno)); return 0; }
  while ((n = fread(buffer, 1, sizeof(buffer), f)) != 0) sha256_update(&c, buffer, n);
  if (ferror(f)) { set_error(error, strerror(errno)); fclose(f); return 0; }
  fclose(f);
  sha256_final(&c, digest); hex32(digest, hex);
  return 1;
}
