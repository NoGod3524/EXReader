/* SPDX-License-Identifier: MIT */
#if defined(__linux__) && !defined(_GNU_SOURCE)
#define _GNU_SOURCE 1
#endif
#ifdef __APPLE__
#define _DARWIN_C_SOURCE 1
#endif
#ifndef _WIN32
#define _POSIX_C_SOURCE 200809L
#define _FILE_OFFSET_BITS 64
#endif
#include "reader_local_downloads.h"
#include <errno.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>
#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <fcntl.h>
#include <io.h>
#else
#include <dirent.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>
#endif

#define LD_CHUNK (64u * 1024u)
#define LD_PATH 1200u
#define LD_INTENT_MAX 2048u

/* ---------------------------------------------------------------- errors */

static reader_ld_status ld_fail(reader_ld_error *e, reader_ld_status code, exr_status sdk,
    int catalog_code, const char *format, ...) {
  va_list args;
  if (e) {
    e->code = code; e->sdk_status = sdk; e->catalog_code = catalog_code;
    va_start(args, format);
    vsnprintf(e->message, sizeof(e->message), format, args);
    va_end(args);
  }
  return code;
}

static reader_ld_status ld_sdk_fail(reader_ld_error *e, exr_status status, const exr_error *sdk,
    const char *what) {
  reader_ld_status code = status == EXR_CANCELLED ? READER_LD_CANCELLED :
    status == EXR_MEMORY ? READER_LD_MEMORY : status == EXR_IO ? READER_LD_IO : READER_LD_SDK;
  return ld_fail(e, code, status, 0, "%s: %s", what, sdk && sdk->message[0] ? sdk->message : "failed");
}

static reader_ld_status ld_catalog_fail(reader_ld_error *e, int status, const reader_catalog_error *c,
    const char *what) {
  return ld_fail(e, READER_LD_CATALOG, EXR_OK, status, "%s: %s", what,
    c && c->message[0] ? c->message : "failed");
}

/* --------------------------------------------------------------- platform */

#ifdef _WIN32
static wchar_t *ld_wide(const char *text) {
  int count = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, text, -1, NULL, 0);
  wchar_t *wide;
  if (count <= 0) return NULL;
  wide = (wchar_t *)malloc((size_t)count * sizeof(wchar_t));
  if (!wide) return NULL;
  if (MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, text, -1, wide, count) != count) {
    free(wide); return NULL;
  }
  return wide;
}
static FILE *ld_fopen(const char *path, int write) {
  wchar_t *wide = ld_wide(path);
  FILE *file;
  if (!wide) return NULL;
  file = _wfopen(wide, write ? L"wb" : L"rb");
  free(wide);
  return file;
}
static int ld_flush(FILE *file) {
  if (fflush(file) != 0) return -1;
  return _commit(_fileno(file)) == 0 ? 0 : -1;
}
static int ld_exists(const char *path) {
  wchar_t *wide = ld_wide(path);
  DWORD attributes;
  if (!wide) return 0;
  attributes = GetFileAttributesW(wide);
  free(wide);
  return attributes != INVALID_FILE_ATTRIBUTES;
}
/* A directory this module owns. Reparse points (junctions and symlinks) are
   refused: clearing files through one would delete another directory's data. */
static int ld_is_dir(const char *path) {
  wchar_t *wide = ld_wide(path);
  DWORD attributes;
  if (!wide) return 0;
  attributes = GetFileAttributesW(wide);
  free(wide);
  return attributes != INVALID_FILE_ATTRIBUTES && (attributes & FILE_ATTRIBUTE_DIRECTORY) != 0 &&
    (attributes & FILE_ATTRIBUTE_REPARSE_POINT) == 0;
}
static int ld_is_regular_nofollow(const char *path) {
  wchar_t *wide = ld_wide(path);
  DWORD attributes;
  if (!wide) return 0;
  attributes = GetFileAttributesW(wide);
  free(wide);
  return attributes != INVALID_FILE_ATTRIBUTES && (attributes & FILE_ATTRIBUTE_DIRECTORY) == 0 &&
    (attributes & FILE_ATTRIBUTE_REPARSE_POINT) == 0;
}
/* CREATE_NEW after the caller removed the entry: no pre-existing name, hard
   link or reparse point can redirect this write. */
static FILE *ld_create_exclusive(const char *path) {
  wchar_t *wide = ld_wide(path);
  HANDLE handle;
  int descriptor;
  FILE *file;
  if (!wide) return NULL;
  handle = CreateFileW(wide, GENERIC_WRITE, 0, NULL, CREATE_NEW, FILE_ATTRIBUTE_NORMAL, NULL);
  free(wide);
  if (handle == INVALID_HANDLE_VALUE) return NULL;
  descriptor = _open_osfhandle((intptr_t)handle, _O_WRONLY | _O_BINARY);
  if (descriptor < 0) { CloseHandle(handle); return NULL; }
  file = _fdopen(descriptor, "wb");
  if (!file) { _close(descriptor); return NULL; }
  return file;
}
static int ld_unlink(const char *path) {
  wchar_t *wide = ld_wide(path);
  DWORD error;
  if (!wide) return -1;
  if (DeleteFileW(wide)) { free(wide); return 0; }
  error = GetLastError();
  free(wide);
  return error == ERROR_FILE_NOT_FOUND || error == ERROR_PATH_NOT_FOUND ? 0 : -1;
}
static int ld_mkdir(const char *path) {
  wchar_t *wide = ld_wide(path);
  int ok;
  if (!wide) return -1;
  ok = CreateDirectoryW(wide, NULL) != 0;
  free(wide);
  return ok || ld_is_dir(path) ? 0 : -1;
}
static int ld_replace(const char *from, const char *to, const char *dir) {
  wchar_t *a = ld_wide(from), *b = ld_wide(to);
  int ok = 0;
  (void)dir;
  if (a && b) ok = MoveFileExW(a, b, MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH) != 0;
  free(a); free(b);
  return ok ? 0 : -1;
}
#else
static FILE *ld_fopen(const char *path, int write) { return fopen(path, write ? "wb" : "rb"); }
static int ld_flush(FILE *file) {
  if (fflush(file) != 0) return -1;
  return fsync(fileno(file)) == 0 ? 0 : -1;
}
static int ld_exists(const char *path) {
  struct stat info;
  return lstat(path, &info) == 0;
}
/* A directory this module owns. A symbolic link is refused: clearing files
   through it would delete another directory's data. */
static int ld_is_dir(const char *path) {
  struct stat info;
  return lstat(path, &info) == 0 && S_ISDIR(info.st_mode);
}
static int ld_is_regular_nofollow(const char *path) {
  struct stat info;
  return lstat(path, &info) == 0 && S_ISREG(info.st_mode);
}
static FILE *ld_create_exclusive(const char *path) {
  int descriptor = open(path, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0600);
  FILE *file;
  if (descriptor < 0) return NULL;
  file = fdopen(descriptor, "wb");
  if (!file) close(descriptor);
  return file;
}
static int ld_unlink(const char *path) {
  return unlink(path) == 0 || errno == ENOENT ? 0 : -1;
}
static int ld_mkdir(const char *path) {
  if (mkdir(path, 0700) == 0) return 0;
  return errno == EEXIST && ld_is_dir(path) ? 0 : -1;
}
static void ld_sync_dir(const char *dir) {
  int fd = open(dir, O_RDONLY);
  if (fd >= 0) { (void)fsync(fd); close(fd); }
}
static int ld_replace(const char *from, const char *to, const char *dir) {
  if (rename(from, to) != 0) return -1;
  ld_sync_dir(dir);
  return 0;
}
#endif

static int ld_join(char *out, size_t capacity, const char *dir, const char *name) {
  int written = snprintf(out, capacity, "%s/%s", dir, name);
  return written > 0 && (size_t)written < capacity ? 0 : -1;
}

/* Deletes one file this module named inside its own directory. Never walks a
   reparse point and never touches another entry. */
static int ld_remove_owned(const char *dir, const char *name) {
  char path[LD_PATH];
  if (strchr(name, '/') || strchr(name, '\\') || !strcmp(name, ".") || !strcmp(name, "..")) return -1;
  if (!ld_is_dir(dir)) return ld_exists(dir) ? -1 : 0;
  if (ld_join(path, sizeof(path), dir, name) != 0) return -1;
  return ld_unlink(path);
}

/* ---------------------------------------------------------------- SHA-256 */

typedef struct {
  uint32_t h[8];
  uint64_t bytes;
  unsigned char block[64];
  size_t used;
} ld_sha;

static const uint32_t ld_k[64] = {
  0x428a2f98u,0x71374491u,0xb5c0fbcfu,0xe9b5dba5u,0x3956c25bu,0x59f111f1u,0x923f82a4u,0xab1c5ed5u,
  0xd807aa98u,0x12835b01u,0x243185beu,0x550c7dc3u,0x72be5d74u,0x80deb1feu,0x9bdc06a7u,0xc19bf174u,
  0xe49b69c1u,0xefbe4786u,0x0fc19dc6u,0x240ca1ccu,0x2de92c6fu,0x4a7484aau,0x5cb0a9dcu,0x76f988dau,
  0x983e5152u,0xa831c66du,0xb00327c8u,0xbf597fc7u,0xc6e00bf3u,0xd5a79147u,0x06ca6351u,0x14292967u,
  0x27b70a85u,0x2e1b2138u,0x4d2c6dfcu,0x53380d13u,0x650a7354u,0x766a0abbu,0x81c2c92eu,0x92722c85u,
  0xa2bfe8a1u,0xa81a664bu,0xc24b8b70u,0xc76c51a3u,0xd192e819u,0xd6990624u,0xf40e3585u,0x106aa070u,
  0x19a4c116u,0x1e376c08u,0x2748774cu,0x34b0bcb5u,0x391c0cb3u,0x4ed8aa4au,0x5b9cca4fu,0x682e6ff3u,
  0x748f82eeu,0x78a5636fu,0x84c87814u,0x8cc70208u,0x90befffau,0xa4506cebu,0xbef9a3f7u,0xc67178f2u};

#define LD_ROR(x, n) (((x) >> (n)) | ((x) << (32 - (n))))

static void ld_sha_init(ld_sha *s) {
  static const uint32_t start[8] = {0x6a09e667u,0xbb67ae85u,0x3c6ef372u,0xa54ff53au,
    0x510e527fu,0x9b05688cu,0x1f83d9abu,0x5be0cd19u};
  memcpy(s->h, start, sizeof(start));
  s->bytes = 0; s->used = 0;
}

static void ld_sha_block(ld_sha *s, const unsigned char *p) {
  uint32_t w[64], a, b, c, d, e, f, g, h, t1, t2;
  int i;
  for (i = 0; i < 16; i++)
    w[i] = ((uint32_t)p[i*4] << 24) | ((uint32_t)p[i*4+1] << 16) | ((uint32_t)p[i*4+2] << 8) | (uint32_t)p[i*4+3];
  for (i = 16; i < 64; i++) {
    uint32_t s0 = LD_ROR(w[i-15], 7) ^ LD_ROR(w[i-15], 18) ^ (w[i-15] >> 3);
    uint32_t s1 = LD_ROR(w[i-2], 17) ^ LD_ROR(w[i-2], 19) ^ (w[i-2] >> 10);
    w[i] = w[i-16] + s0 + w[i-7] + s1;
  }
  a = s->h[0]; b = s->h[1]; c = s->h[2]; d = s->h[3];
  e = s->h[4]; f = s->h[5]; g = s->h[6]; h = s->h[7];
  for (i = 0; i < 64; i++) {
    t1 = h + (LD_ROR(e, 6) ^ LD_ROR(e, 11) ^ LD_ROR(e, 25)) + ((e & f) ^ ((~e) & g)) + ld_k[i] + w[i];
    t2 = (LD_ROR(a, 2) ^ LD_ROR(a, 13) ^ LD_ROR(a, 22)) + ((a & b) ^ (a & c) ^ (b & c));
    h = g; g = f; f = e; e = d + t1; d = c; c = b; b = a; a = t1 + t2;
  }
  s->h[0] += a; s->h[1] += b; s->h[2] += c; s->h[3] += d;
  s->h[4] += e; s->h[5] += f; s->h[6] += g; s->h[7] += h;
}

static void ld_sha_update(ld_sha *s, const void *data, size_t size) {
  const unsigned char *p = (const unsigned char *)data;
  s->bytes += size;
  while (size) {
    size_t take = 64 - s->used;
    if (take > size) take = size;
    memcpy(s->block + s->used, p, take);
    s->used += take; p += take; size -= take;
    if (s->used == 64) { ld_sha_block(s, s->block); s->used = 0; }
  }
}

static void ld_sha_hex(ld_sha *s, char out[65]) {
  static const char digits[] = "0123456789abcdef";
  uint64_t bits = s->bytes * 8u;
  unsigned char pad = 0x80, zero = 0, length[8];
  int i;
  ld_sha_update(s, &pad, 1);
  while (s->used != 56) ld_sha_update(s, &zero, 1);
  for (i = 0; i < 8; i++) length[i] = (unsigned char)(bits >> (56 - 8 * i));
  ld_sha_update(s, length, 8);
  for (i = 0; i < 32; i++) {
    unsigned char byte = (unsigned char)(s->h[i / 4] >> (24 - 8 * (i % 4)));
    out[i*2] = digits[byte >> 4]; out[i*2+1] = digits[byte & 15];
  }
  out[64] = 0;
}

/* ------------------------------------------------------------- identities */

typedef struct { const char *name; exr_format format; const char *kind; } ld_format;
static const ld_format ld_formats[] = {
  {"epub", EXR_EPUB, "epub_chapter"}, {"pdf", EXR_PDF, "fixed_page"}, {"cbz", EXR_CBZ, "fixed_page"},
  {"txt", EXR_TXT, "reflow_global"}, {"html", EXR_HTML, "reflow_global"}, {"fb2", EXR_FB2, "reflow_global"},
  {"docx", EXR_DOCX, "reflow_global"}, {"rtf", EXR_RTF, "reflow_global"}, {"mobi", EXR_MOBI, "reflow_global"}};

typedef struct {
  const ld_format *format;
  char sha[65];
  char key[96];
} ld_key;

static int ld_parse_key(const char *text, ld_key *out) {
  size_t i, n = sizeof(ld_formats) / sizeof(ld_formats[0]);
  if (!text) return -1;
  for (i = 0; i < n; i++) {
    size_t name = strlen(ld_formats[i].name);
    if (!strncmp(text, ld_formats[i].name, name) && text[name] == ':') {
      const char *sha = text + name + 1;
      size_t j;
      if (strlen(sha) != 64) return -1;
      for (j = 0; j < 64; j++)
        if (!((sha[j] >= '0' && sha[j] <= '9') || (sha[j] >= 'a' && sha[j] <= 'f'))) return -1;
      out->format = &ld_formats[i];
      memcpy(out->sha, sha, 65);
      snprintf(out->key, sizeof(out->key), "%s", text);
      return 0;
    }
  }
  return -1;
}

static const ld_format *ld_by_exr(exr_format format) {
  size_t i;
  for (i = 0; i < sizeof(ld_formats) / sizeof(ld_formats[0]); i++)
    if (ld_formats[i].format == format) return &ld_formats[i];
  return NULL;
}

/* -------------------------------------------------------- shared helpers */

/* One stateful call at a time. A host callback (stage or busy) that calls back
   into remove/recover/reimport gets BUSY and can never interleave durable
   writes with the call that is running. reader_ld_pending stays read-only. */
static volatile int ld_active;
static int ld_enter(void) {
  if (ld_active) return -1;
  ld_active = 1;
  return 0;
}
static void ld_leave(void) { ld_active = 0; }

static int ld_cancelled(const reader_ld_options *o) {
  return o->control.cancelled && o->control.cancelled(o->control.context) != 0;
}

static void ld_hook(const reader_ld_options *o, reader_ld_stage stage) {
  if (o->after_stage) o->after_stage(o->stage_context, stage);
}

static reader_ld_status ld_check_options(const reader_ld_options *o, int need_library, reader_ld_error *e) {
  if (!o || o->struct_size < sizeof(*o) || !o->catalog || !o->state_dir || !o->state_dir[0] ||
      (need_library && !o->library) || strlen(o->state_dir) > 700 ||
      (o->legacy_policy != READER_LD_LEGACY_REJECT && o->legacy_policy != READER_LD_LEGACY_BACKUP))
    return ld_fail(e, READER_LD_ARGUMENT, EXR_OK, 0, "Invalid local-download options");
  if (!ld_is_dir(o->state_dir))
    return ld_fail(e, READER_LD_IO, EXR_OK, 0, "State directory does not exist");
  return READER_LD_OK;
}

/* Hash a stored original through the bounded public source. */
static reader_ld_status ld_hash_source(const reader_ld_options *o, const exr_source *source,
    char sha[65], reader_ld_error *e) {
  ld_sha state;
  unsigned char *buffer = (unsigned char *)malloc(LD_CHUNK);
  uint64_t offset = 0;
  if (!buffer) return ld_fail(e, READER_LD_MEMORY, EXR_OK, 0, "Hash buffer allocation failed");
  ld_sha_init(&state);
  while (offset < source->size) {
    uint64_t left = source->size - offset;
    size_t want = left > LD_CHUNK ? LD_CHUNK : (size_t)left;
    size_t got;
    if (ld_cancelled(o)) { free(buffer); return ld_fail(e, READER_LD_CANCELLED, EXR_CANCELLED, 0, "Cancelled while verifying"); }
    got = source->read_at(source->context, offset, buffer, want);
    if (got == 0) { free(buffer); return ld_fail(e, READER_LD_IO, EXR_IO, 0, "Stored original could not be read"); }
    ld_sha_update(&state, buffer, got);
    offset += got;
  }
  free(buffer);
  ld_sha_hex(&state, sha);
  return READER_LD_OK;
}

static reader_ld_status ld_hash_file(const reader_ld_options *o, const char *path, char sha[65],
    uint64_t *size, reader_ld_error *e) {
  ld_sha state;
  unsigned char *buffer;
  FILE *file = ld_fopen(path, 0);
  size_t got;
  *size = 0;
  if (!file) return ld_fail(e, READER_LD_IO, EXR_OK, 0, "File could not be opened");
  buffer = (unsigned char *)malloc(LD_CHUNK);
  if (!buffer) { fclose(file); return ld_fail(e, READER_LD_MEMORY, EXR_OK, 0, "Hash buffer allocation failed"); }
  ld_sha_init(&state);
  while ((got = fread(buffer, 1, LD_CHUNK, file)) > 0) {
    if (ld_cancelled(o)) { free(buffer); fclose(file); return ld_fail(e, READER_LD_CANCELLED, EXR_CANCELLED, 0, "Cancelled while hashing"); }
    ld_sha_update(&state, buffer, got);
    *size += got;
  }
  if (ferror(file)) { free(buffer); fclose(file); return ld_fail(e, READER_LD_IO, EXR_OK, 0, "File read failed"); }
  free(buffer); fclose(file);
  ld_sha_hex(&state, sha);
  return READER_LD_OK;
}

/* Copies one opened source handle into a private staging file while hashing
   the same bytes, so verification and import can never observe two different
   files. The staging name is removed first and created exclusively. */
static reader_ld_status ld_stage_copy(const reader_ld_options *o, const char *source_path,
    const char *stage_path, char sha[65], uint64_t *size, reader_ld_error *e) {
  ld_sha state;
  unsigned char *buffer;
  FILE *input, *output;
  size_t got;
  *size = 0; sha[0] = 0;
  (void)ld_unlink(stage_path);
  input = ld_fopen(source_path, 0);
  if (!input) return ld_fail(e, READER_LD_IO, EXR_OK, 0, "File could not be opened");
  output = ld_create_exclusive(stage_path);
  if (!output) { fclose(input); return ld_fail(e, READER_LD_IO, EXR_OK, 0, "Private staging file could not be created"); }
  buffer = (unsigned char *)malloc(LD_CHUNK);
  if (!buffer) {
    fclose(input); fclose(output); (void)ld_unlink(stage_path);
    return ld_fail(e, READER_LD_MEMORY, EXR_OK, 0, "Hash buffer allocation failed");
  }
  ld_sha_init(&state);
  while ((got = fread(buffer, 1, LD_CHUNK, input)) > 0) {
    if (ld_cancelled(o)) {
      free(buffer); fclose(input); fclose(output); (void)ld_unlink(stage_path);
      return ld_fail(e, READER_LD_CANCELLED, EXR_CANCELLED, 0, "Cancelled while staging");
    }
    if (fwrite(buffer, 1, got, output) != got || ld_flush(output) != 0) {
      free(buffer); fclose(input); fclose(output); (void)ld_unlink(stage_path);
      return ld_fail(e, READER_LD_IO, EXR_OK, 0, "Private staging file could not be written");
    }
    ld_sha_update(&state, buffer, got);
    *size += got;
  }
  free(buffer);
  if (ferror(input)) {
    fclose(input); fclose(output); (void)ld_unlink(stage_path);
    return ld_fail(e, READER_LD_IO, EXR_OK, 0, "File read failed");
  }
  fclose(input);
  if (fclose(output) != 0) { (void)ld_unlink(stage_path); return ld_fail(e, READER_LD_IO, EXR_OK, 0, "Private staging file could not be closed"); }
  ld_sha_hex(&state, sha);
  return READER_LD_OK;
}

typedef struct {
  int found, deleted;
  int64_t sdk_book_id;
  uint64_t bytes;
  int favorite;
  char *format, *title, *author, *sort_title;
} ld_row;

static char *ld_dup(const char *text) {
  size_t n = text ? strlen(text) : 0;
  char *copy = (char *)malloc(n + 1);
  if (!copy) return NULL;
  if (n) memcpy(copy, text, n);
  copy[n] = 0;
  return copy;
}

static void ld_row_free(ld_row *row) {
  free(row->format); free(row->title); free(row->author); free(row->sort_title);
  memset(row, 0, sizeof(*row));
}

static int ld_row_visit(void *context, const reader_catalog_row *source) {
  ld_row *row = (ld_row *)context;
  row->found = 1;
  row->deleted = source->deleted;
  row->sdk_book_id = source->sdk_book_id;
  row->bytes = source->source_bytes;
  row->favorite = source->favorite;
  row->format = ld_dup(source->format);
  row->title = ld_dup(source->title);
  row->author = ld_dup(source->author);
  row->sort_title = ld_dup(source->sort_title);
  return row->format && row->title && row->author && row->sort_title ? 0 : 1;
}

static reader_ld_status ld_metadata(const reader_ld_options *o, const ld_key *key, ld_row *row,
    reader_ld_error *e) {
  reader_catalog_error ce;
  int found = 0, status;
  memset(row, 0, sizeof(*row)); memset(&ce, 0, sizeof(ce));
  status = reader_catalog_metadata(o->catalog, key->key, ld_row_visit, row, &found, &ce);
  if (status != 0) { ld_row_free(row); return ld_catalog_fail(e, status, &ce, "Catalog metadata lookup"); }
  if (!found || !row->found) { ld_row_free(row); return ld_fail(e, READER_LD_NOT_FOUND, EXR_OK, 0, "Unknown book key"); }
  if (!row->format || !row->title || strcmp(row->format, key->format->name)) {
    ld_row_free(row);
    return ld_fail(e, READER_LD_IDENTITY, EXR_OK, 0, "Catalog format differs from book key");
  }
  return READER_LD_OK;
}

static reader_ld_status ld_has_local(const reader_ld_options *o, int64_t id, int *present,
    reader_ld_error *e) {
  reader_catalog_error ce;
  int status;
  memset(&ce, 0, sizeof(ce));
  status = reader_catalog_has_local(o->catalog, id, present, &ce);
  return status == 0 ? READER_LD_OK : ld_catalog_fail(e, status, &ce, "Local mapping lookup");
}

static reader_ld_status ld_attach(const reader_ld_options *o, const ld_key *key, const ld_row *row,
    int64_t id, reader_ld_error *e) {
  reader_catalog_error ce;
  reader_catalog_book book;
  int status;
  memset(&ce, 0, sizeof(ce)); memset(&book, 0, sizeof(book));
  book.format = key->format->name; book.sha256 = key->sha; book.title = row->title;
  book.author = row->author; book.sort_title = row->sort_title; book.location_kind = key->format->kind;
  book.source_bytes = row->bytes; book.sdk_book_id = id; book.favorite = row->favorite;
  status = reader_catalog_attach(o->catalog, &book, &ce);
  return status == 0 ? READER_LD_OK : ld_catalog_fail(e, status, &ce, "Local mapping attach");
}

static const exr_book *ld_find_book(const exr_book *books, size_t count, int64_t id) {
  size_t i;
  for (i = 0; i < count; i++) if (books[i].id == id) return &books[i];
  return NULL;
}

static reader_ld_status ld_list(const reader_ld_options *o, exr_book **books, size_t *count,
    reader_ld_error *e) {
  exr_error se; exr_status status;
  memset(&se, 0, sizeof(se));
  *books = NULL; *count = 0;
  status = exr_library_books(o->library, NULL, books, count, &se);
  return status == EXR_OK ? READER_LD_OK : ld_sdk_fail(e, status, &se, "SDK book listing");
}

/* Verify that an SDK row is exactly the keyed original: format, size, SHA. */
static reader_ld_status ld_verify_row(const reader_ld_options *o, const exr_book *book,
    const ld_key *key, uint64_t bytes, int *matches, reader_ld_error *e) {
  exr_source source;
  exr_error se; exr_status status;
  char sha[65];
  reader_ld_status result = READER_LD_OK;
  *matches = 0;
  if (book->format != key->format->format) return READER_LD_OK;
  memset(&source, 0, sizeof(source)); memset(&se, 0, sizeof(se));
  status = exr_library_source(o->library, book->id, &source, &se);
  if (status != EXR_OK) return ld_sdk_fail(e, status, &se, "SDK source");
  if (source.size == bytes) {
    result = ld_hash_source(o, &source, sha, e);
    if (result == READER_LD_OK && !strcmp(sha, key->sha)) *matches = 1;
  }
  if (source.release) source.release(source.context);
  return result;
}

/* SDK-only user data that no product revision is assumed to cover. */
static reader_ld_status ld_legacy_scan(const reader_ld_options *o, const exr_book *book,
    size_t *notes, int *progress, reader_ld_error *e) {
  exr_error se; exr_status status;
  int bounded = 0;
  *notes = 0; *progress = book->position > 0 ? 1 : 0;
  memset(&se, 0, sizeof(se));
  if (book->format == EXR_EPUB) {
    exr_library_epub_info info;
    memset(&info, 0, sizeof(info)); info.struct_size = sizeof(info);
    status = exr_library_epub_info_get(o->library, book->id, &info, &se);
    if (status != EXR_OK) return ld_sdk_fail(e, status, &se, "SDK EPUB mode");
    bounded = info.bounded_storage;
    if (bounded) {
      exr_epub_note *list = NULL; size_t count = 0;
      exr_epub_location location; int present = 0;
      status = exr_library_epub_notes(o->library, book->id, &list, &count, &se);
      if (status != EXR_OK) return ld_sdk_fail(e, status, &se, "SDK EPUB notes");
      *notes += count; exr_epub_notes_free(list, count);
      memset(&location, 0, sizeof(location));
      status = exr_library_epub_progress_get(o->library, book->id, &location, &present, &se);
      if (status != EXR_OK) return ld_sdk_fail(e, status, &se, "SDK EPUB progress");
      if (present) *progress = 1;
      exr_epub_location_free(&location);
      return READER_LD_OK; /* Global notes/progress are unsupported there. */
    }
  }
  if (book->format == EXR_PDF || book->format == EXR_CBZ) {
    exr_fixed_note *list = NULL; size_t count = 0;
    status = exr_library_fixed_notes(o->library, book->id, &list, &count, &se);
    if (status != EXR_OK) return ld_sdk_fail(e, status, &se, "SDK fixed-page notes");
    *notes += count; exr_fixed_notes_free(list, count);
    return READER_LD_OK;
  }
  {
    exr_note *list = NULL; size_t count = 0;
    exr_anchor anchor; exr_anchor_state state = EXR_ANCHOR_LEGACY;
    status = exr_library_notes(o->library, book->id, &list, &count, &se);
    if (status != EXR_OK) return ld_sdk_fail(e, status, &se, "SDK notes");
    *notes += count; exr_notes_free(list, count);
    memset(&anchor, 0, sizeof(anchor));
    if (exr_library_progress_get(o->library, book->id, &anchor, &state, &se) == EXR_OK) {
      if (state != EXR_ANCHOR_LEGACY) *progress = 1;
      exr_anchor_free(&anchor);
    }
  }
  return READER_LD_OK;
}

/* ----------------------------------------------------------------- intent */

typedef struct {
  int stage;
  char key[96];
  uint64_t bytes;
  int64_t mapped;
  int64_t ids[READER_LD_MAX_COPIES];
  size_t count;
} ld_intent;

static int ld_paths(const char *state, char *intent, char *tmp, char *originals) {
  return ld_join(intent, LD_PATH, state, "intent.rdi") == 0 && ld_join(tmp, LD_PATH, state, "intent.tmp") == 0 &&
    ld_join(originals, LD_PATH, state, "originals") == 0 ? 0 : -1;
}

static reader_ld_status ld_intent_write(const char *state, const ld_intent *intent, reader_ld_error *e) {
  char path[LD_PATH], tmp[LD_PATH], originals[LD_PATH], body[LD_INTENT_MAX], hex[65], ids[512];
  size_t i, used = 0;
  int length;
  ld_sha sha;
  FILE *file;
  if (ld_paths(state, path, tmp, originals) != 0)
    return ld_fail(e, READER_LD_IO, EXR_OK, 0, "State path is too long");
  ids[0] = 0;
  for (i = 0; i < intent->count; i++) {
    int written = snprintf(ids + used, sizeof(ids) - used, "%s%lld", i ? "," : "", (long long)intent->ids[i]);
    if (written < 0 || (size_t)written >= sizeof(ids) - used)
      return ld_fail(e, READER_LD_IO, EXR_OK, 0, "Intent is too large");
    used += (size_t)written;
  }
  length = snprintf(body, sizeof(body), "EXRLD1\nstage=%d\nkey=%s\nbytes=%llu\nmapped=%lld\nids=%s\n",
    intent->stage, intent->key, (unsigned long long)intent->bytes, (long long)intent->mapped, ids);
  if (length <= 0 || (size_t)length >= sizeof(body))
    return ld_fail(e, READER_LD_IO, EXR_OK, 0, "Intent is too large");
  ld_sha_init(&sha); ld_sha_update(&sha, body, (size_t)length); ld_sha_hex(&sha, hex);
  /* Remove any stale entry first, then create it exclusively so a pre-existing
     name, hard link or reparse point can never be truncated by this write. */
  (void)ld_unlink(tmp);
  file = ld_create_exclusive(tmp);
  if (!file) return ld_fail(e, READER_LD_IO, EXR_OK, 0, "Intent file could not be created");
  if (fwrite(body, 1, (size_t)length, file) != (size_t)length ||
      fprintf(file, "check=%s\n", hex) < 0 || ld_flush(file) != 0) {
    fclose(file); ld_unlink(tmp);
    return ld_fail(e, READER_LD_IO, EXR_OK, 0, "Intent file could not be written");
  }
  if (fclose(file) != 0) { ld_unlink(tmp); return ld_fail(e, READER_LD_IO, EXR_OK, 0, "Intent file could not be closed"); }
  if (ld_replace(tmp, path, state) != 0) {
    ld_unlink(tmp);
    return ld_fail(e, READER_LD_IO, EXR_OK, 0, "Intent file could not be published");
  }
  return READER_LD_OK;
}

/* Strict bounded parser for the private intent record. The exact byte layout
   is: EXRLD1, then stage/key/bytes/mapped/ids/check once each in that order,
   then EOF. No unknown field, duplicate field, trailing byte, non-digit,
   leading plus/minus, empty list element or out-of-range value is accepted. */
static int ld_uint_line(const char *text, size_t size, size_t *pos, const char *prefix,
    uint64_t limit, uint64_t *value) {
  size_t i = *pos, n = strlen(prefix), digits = 0;
  uint64_t result = 0;
  if (size - i < n || memcmp(text + i, prefix, n) != 0) return -1;
  i += n;
  while (i < size && text[i] >= '0' && text[i] <= '9') {
    uint64_t digit = (uint64_t)(text[i] - '0');
    if (result > (UINT64_MAX - digit) / 10) return -1;
    result = result * 10 + digit;
    digits++; i++;
  }
  if (!digits || i >= size || text[i] != '\n' || result < 1 || result > limit) return -1;
  *pos = i + 1;
  *value = result;
  return 0;
}

static int ld_text_line(const char *text, size_t size, size_t *pos, const char *prefix,
    char *out, size_t capacity) {
  size_t i = *pos, n = strlen(prefix), start;
  if (size - i < n || memcmp(text + i, prefix, n) != 0) return -1;
  start = i + n;
  i = start;
  while (i < size && text[i] != '\n') i++;
  if (i >= size || i == start || (i - start) >= capacity) return -1;
  memcpy(out, text + start, i - start);
  out[i - start] = 0;
  *pos = i + 1;
  return 0;
}

static reader_ld_status ld_intent_parse(const char *text, size_t size, ld_intent *intent,
    reader_ld_error *e) {
  char key[160], check[65], hex[65];
  uint64_t stage = 0, bytes = 0, mapped = 0;
  size_t pos = 0, i;
  ld_sha sha;
  memset(intent, 0, sizeof(*intent));
  intent->stage = -1; intent->mapped = -1;
  if (size < 7 || memcmp(text, "EXRLD1\n", 7) != 0)
    return ld_fail(e, READER_LD_CORRUPT_INTENT, EXR_OK, 0, "Intent header is invalid");
  pos = 7;
  if (ld_uint_line(text, size, &pos, "stage=", (uint64_t)READER_LD_STAGE_DELETED, &stage) != 0 ||
      ld_text_line(text, size, &pos, "key=", key, sizeof(key)) != 0 ||
      ld_uint_line(text, size, &pos, "bytes=", (uint64_t)INT64_MAX, &bytes) != 0 ||
      ld_uint_line(text, size, &pos, "mapped=", (uint64_t)INT64_MAX, &mapped) != 0)
    return ld_fail(e, READER_LD_CORRUPT_INTENT, EXR_OK, 0, "Intent fields are invalid");
  if (size - pos < 4 || memcmp(text + pos, "ids=", 4) != 0)
    return ld_fail(e, READER_LD_CORRUPT_INTENT, EXR_OK, 0, "Intent ids are invalid");
  pos += 4;
  for (;;) {
    uint64_t id = 0;
    size_t digits = 0;
    while (pos < size && text[pos] >= '0' && text[pos] <= '9') {
      uint64_t digit = (uint64_t)(text[pos] - '0');
      if (id > (UINT64_MAX - digit) / 10) break;
      id = id * 10 + digit;
      digits++; pos++;
    }
    if (!digits || id == 0 || id > (uint64_t)INT64_MAX || intent->count >= READER_LD_MAX_COPIES)
      return ld_fail(e, READER_LD_CORRUPT_INTENT, EXR_OK, 0, "Intent ids are invalid");
    intent->ids[intent->count++] = (int64_t)id;
    if (pos < size && text[pos] == ',') { pos++; continue; }
    break;
  }
  if (pos >= size || text[pos] != '\n')
    return ld_fail(e, READER_LD_CORRUPT_INTENT, EXR_OK, 0, "Intent ids are invalid");
  pos++;
  ld_sha_init(&sha); ld_sha_update(&sha, text, pos); ld_sha_hex(&sha, hex);
  if (size - pos != 6 + 64 + 1 || memcmp(text + pos, "check=", 6) != 0 ||
      text[pos + 70] != '\n')
    return ld_fail(e, READER_LD_CORRUPT_INTENT, EXR_OK, 0, "Intent checksum line is invalid");
  memcpy(check, text + pos + 6, 64);
  check[64] = 0;
  for (i = 0; i < 64; i++)
    if (!((check[i] >= '0' && check[i] <= '9') || (check[i] >= 'a' && check[i] <= 'f')))
      return ld_fail(e, READER_LD_CORRUPT_INTENT, EXR_OK, 0, "Intent checksum is not hexadecimal");
  if (strcmp(check, hex) != 0)
    return ld_fail(e, READER_LD_CORRUPT_INTENT, EXR_OK, 0, "Intent checksum differs");
  pos += 71;
  if (pos != size)
    return ld_fail(e, READER_LD_CORRUPT_INTENT, EXR_OK, 0, "Intent has trailing bytes");
  intent->stage = (int)stage;
  intent->bytes = bytes;
  intent->mapped = (int64_t)mapped;
  if (strlen(key) >= sizeof(intent->key))
    return ld_fail(e, READER_LD_CORRUPT_INTENT, EXR_OK, 0, "Intent key is too long");
  memcpy(intent->key, key, strlen(key) + 1);
  {
    ld_key parsed;
    int has_mapped = 0;
    if (ld_parse_key(intent->key, &parsed) != 0)
      return ld_fail(e, READER_LD_CORRUPT_INTENT, EXR_OK, 0, "Intent key is invalid");
    for (i = 0; i < intent->count; i++) if (intent->ids[i] == intent->mapped) has_mapped = 1;
    if (!has_mapped)
      return ld_fail(e, READER_LD_CORRUPT_INTENT, EXR_OK, 0, "Intent identity is invalid");
  }
  return READER_LD_OK;
}

/* *present is 0 when no intent exists. A damaged record is refused and left
   exactly as it is; nothing is repaired, truncated or deleted here. */
static reader_ld_status ld_intent_read(const char *state, ld_intent *intent, int *present,
    reader_ld_error *e) {
  char path[LD_PATH], tmp[LD_PATH], originals[LD_PATH], text[LD_INTENT_MAX + 2];
  size_t got;
  FILE *file;
  *present = 0;
  if (ld_paths(state, path, tmp, originals) != 0)
    return ld_fail(e, READER_LD_IO, EXR_OK, 0, "State path is too long");
  if (!ld_is_regular_nofollow(path)) {
    if (!ld_exists(path)) return READER_LD_OK;
    return ld_fail(e, READER_LD_CORRUPT_INTENT, EXR_OK, 0, "Intent entry is not a plain file");
  }
  file = ld_fopen(path, 0);
  if (!file) return ld_fail(e, READER_LD_IO, EXR_OK, 0, "Intent file could not be opened");
  got = fread(text, 1, LD_INTENT_MAX + 1, file);
  if (ferror(file)) { fclose(file); return ld_fail(e, READER_LD_IO, EXR_OK, 0, "Intent file could not be read"); }
  if (got > LD_INTENT_MAX || !feof(file)) {
    fclose(file);
    return ld_fail(e, READER_LD_CORRUPT_INTENT, EXR_OK, 0, "Intent file exceeds its byte bound");
  }
  fclose(file);
  text[got] = 0;
  {
    reader_ld_status status = ld_intent_parse(text, got, intent, e);
    if (status != READER_LD_OK) return status;
  }
  *present = 1;
  return READER_LD_OK;
}

static reader_ld_status ld_rollback(const char *state, const char *sha, reader_ld_error *e) {
  char path[LD_PATH], tmp[LD_PATH], originals[LD_PATH], name[160];
  if (ld_paths(state, path, tmp, originals) != 0)
    return ld_fail(e, READER_LD_IO, EXR_OK, 0, "State path is too long");
  /* Only this book's own files: a retained original of another book may still
     be the file the SDK is reading. */
  snprintf(name, sizeof(name), "%s.orig", sha);
  if (ld_remove_owned(originals, name) != 0)
    return ld_fail(e, READER_LD_IO, EXR_OK, 0, "Intent cleanup failed");
  snprintf(name, sizeof(name), "%s.open", sha);
  if (ld_remove_owned(originals, name) != 0)
    return ld_fail(e, READER_LD_IO, EXR_OK, 0, "Intent cleanup failed");
  if (ld_unlink(tmp) != 0 || ld_unlink(path) != 0)
    return ld_fail(e, READER_LD_IO, EXR_OK, 0, "Intent cleanup failed");
  return READER_LD_OK;
}

/* ---------------------------------------------------------------- stages */

static reader_ld_status ld_busy(const reader_ld_options *o, const ld_intent *intent, reader_ld_error *e) {
  size_t i;
  if (!o->is_busy) return READER_LD_OK;
  for (i = 0; i < intent->count; i++)
    if (o->is_busy(o->busy_context, intent->key, intent->ids[i]))
      return ld_fail(e, READER_LD_BUSY, EXR_OK, 0, "The original is still in use; release its sources first");
  return READER_LD_OK;
}

static reader_ld_status ld_backup(const reader_ld_options *o, const ld_key *key, char *path_out,
    reader_ld_error *e) {
  char dir[LD_PATH], name[160], path[LD_PATH];
  exr_error se; exr_status status;
  exr_library *copy = NULL;
  exr_book *books = NULL; size_t count = 0, n;
  if (ld_join(dir, sizeof(dir), o->state_dir, "legacy") != 0 || ld_mkdir(dir) != 0)
    return ld_fail(e, READER_LD_IO, EXR_OK, 0, "Legacy backup directory could not be created");
  for (n = 1; n < 10000; n++) {
    snprintf(name, sizeof(name), "%s-%u.exrbackup", key->sha, (unsigned)n);
    if (ld_join(path, sizeof(path), dir, name) != 0)
      return ld_fail(e, READER_LD_IO, EXR_OK, 0, "Legacy backup path is too long");
    if (!ld_exists(path)) break;
  }
  if (n >= 10000) return ld_fail(e, READER_LD_IO, EXR_OK, 0, "Too many legacy backups");
  memset(&se, 0, sizeof(se));
  status = exr_library_backup(o->library, path, &se);
  if (status != EXR_OK) { ld_unlink(path); return ld_sdk_fail(e, status, &se, "SDK backup"); }
  status = exr_library_open(path, &copy, &se);
  if (status == EXR_OK) status = exr_library_books(copy, NULL, &books, &count, &se);
  if (status == EXR_OK) exr_books_free(books, count);
  if (copy) exr_library_close(copy);
  if (status != EXR_OK || count == 0) {
    ld_unlink(path);
    return status != EXR_OK ? ld_sdk_fail(e, status, &se, "SDK backup verification") :
      ld_fail(e, READER_LD_SDK, EXR_OK, 0, "SDK backup is empty");
  }
  snprintf(path_out, READER_LD_PATH_BYTES, "%s", path);
  return READER_LD_OK;
}

static reader_ld_status ld_set_stage(const reader_ld_options *o, ld_intent *intent, int stage,
    reader_ld_error *e) {
  reader_ld_status status;
  intent->stage = stage;
  status = ld_intent_write(o->state_dir, intent, e);
  if (status == READER_LD_OK) ld_hook(o, (reader_ld_stage)stage);
  return status;
}

/* UNMAPPED -> DELETED. Verified rows only; anything else is left untouched. */
static reader_ld_status ld_delete_rows(const reader_ld_options *o, const ld_key *key, ld_intent *intent,
    reader_ld_result *result, reader_ld_error *e) {
  exr_book *books = NULL;
  size_t count = 0, i, notes_total = 0, progress_total = 0;
  int verified[READER_LD_MAX_COPIES];
  reader_ld_status status = ld_busy(o, intent, e);
  if (status != READER_LD_OK) return status;
  status = ld_list(o, &books, &count, e);
  if (status != READER_LD_OK) return status;
  memset(verified, 0, sizeof(verified));
  for (i = 0; i < intent->count && status == READER_LD_OK; i++) {
    const exr_book *book = ld_find_book(books, count, intent->ids[i]);
    size_t notes = 0; int progress = 0;
    if (!book) continue;
    status = ld_verify_row(o, book, key, intent->bytes, &verified[i], e);
    if (status == READER_LD_OK && !verified[i]) result->copies_skipped++;
    if (status == READER_LD_OK && verified[i]) {
      status = ld_legacy_scan(o, book, &notes, &progress, e);
      notes_total += notes; progress_total += progress ? 1u : 0u;
    }
  }
  if (status == READER_LD_OK && (notes_total || progress_total)) {
    result->legacy_notes = notes_total; result->legacy_progress = progress_total;
    if (o->legacy_policy == READER_LD_LEGACY_REJECT) {
      status = ld_fail(e, READER_LD_LEGACY_DATA, EXR_OK, 0,
        "SDK-only notes/progress exist: %u notes, %u rows with progress; keep them or use the backup policy",
        (unsigned)notes_total, (unsigned)progress_total);
    } else {
      status = ld_backup(o, key, result->backup_path, e);
    }
  }
  for (i = 0; i < intent->count && status == READER_LD_OK; i++) {
    exr_error se; exr_status sdk;
    memset(&se, 0, sizeof(se));
    if (!verified[i]) continue;
    if (ld_cancelled(o)) { status = ld_fail(e, READER_LD_CANCELLED, EXR_CANCELLED, 0, "Cancelled before deleting"); break; }
    sdk = exr_library_delete(o->library, intent->ids[i], &se);
    if (sdk != EXR_OK) status = ld_sdk_fail(e, sdk, &se, "SDK delete");
    else result->copies_removed++;
  }
  exr_books_free(books, count);
  return status;
}

/* Everything from PREPARED onward. fresh=1: still inside the caller that created
   the intent, so a failure before UNMAPPED undoes the preparation. */
static reader_ld_status ld_forward(const reader_ld_options *o, ld_intent *intent, int fresh,
    reader_ld_result *result, reader_ld_error *e) {
  ld_key key;
  reader_ld_status status = READER_LD_OK;
  char path[LD_PATH], tmp[LD_PATH], originals[LD_PATH];
  if (ld_parse_key(intent->key, &key) != 0 || ld_paths(o->state_dir, path, tmp, originals) != 0)
    return ld_fail(e, READER_LD_CORRUPT_INTENT, EXR_OK, 0, "Intent key is invalid");
  result->sdk_book_id = intent->mapped;
  if (intent->stage < READER_LD_STAGE_UNMAPPED) {
    int present = 0;
    reader_catalog_error ce;
    if (ld_cancelled(o)) status = ld_fail(e, READER_LD_CANCELLED, EXR_CANCELLED, 0, "Cancelled before unmapping");
    if (status == READER_LD_OK) status = ld_busy(o, intent, e);
    if (status == READER_LD_OK) status = ld_has_local(o, intent->mapped, &present, e);
    if (status == READER_LD_OK && present) {
      int code;
      memset(&ce, 0, sizeof(ce));
      code = reader_catalog_remove_local(o->catalog, intent->mapped, &ce);
      if (code != 0) status = ld_catalog_fail(e, code, &ce, "Local mapping removal");
    }
    if (status != READER_LD_OK) {
      if (fresh) { reader_ld_error ignored; (void)ld_rollback(o->state_dir, key.sha, &ignored); }
      return status;
    }
    status = ld_set_stage(o, intent, READER_LD_STAGE_UNMAPPED, e);
    if (status != READER_LD_OK) return status;
  }
  if (intent->stage < READER_LD_STAGE_DELETED) {
    status = ld_delete_rows(o, &key, intent, result, e);
    if (status == READER_LD_LEGACY_DATA) {
      /* Late legacy data: put the mapping back and leave every row. */
      ld_row row;
      reader_ld_error ignored;
      reader_ld_status restore = ld_metadata(o, &key, &row, &ignored);
      if (restore == READER_LD_OK) {
        restore = ld_attach(o, &key, &row, intent->mapped, &ignored);
        ld_row_free(&row);
      }
      if (restore == READER_LD_OK && ld_rollback(o->state_dir, key.sha, &ignored) == READER_LD_OK)
        result->outcome = READER_LD_OUTCOME_RESTORED;
      return status;
    }
    if (status != READER_LD_OK) return status;
    status = ld_set_stage(o, intent, READER_LD_STAGE_DELETED, e);
    if (status != READER_LD_OK) return status;
  }
  {
    char name[160];
    snprintf(name, sizeof(name), "%s.orig", key.sha);
    if (ld_remove_owned(originals, name) != 0)
      return ld_fail(e, READER_LD_IO, EXR_OK, 0, "Verified original export could not be removed");
    snprintf(name, sizeof(name), "%s.open", key.sha);
    if (ld_remove_owned(originals, name) != 0)
      return ld_fail(e, READER_LD_IO, EXR_OK, 0, "Verified original export could not be removed");
  }
  ld_hook(o, READER_LD_STAGE_CLEANED);
  if (ld_unlink(path) != 0 || ld_unlink(tmp) != 0)
    return ld_fail(e, READER_LD_IO, EXR_OK, 0, "Intent could not be removed");
  result->outcome = READER_LD_OUTCOME_REMOVED;
  return READER_LD_OK;
}

/* --------------------------------------------------------------- public */

void reader_ld_options_init(reader_ld_options *options) {
  if (!options) return;
  memset(options, 0, sizeof(*options));
  options->struct_size = sizeof(*options);
}

void reader_ld_result_init(reader_ld_result *result) {
  if (!result) return;
  memset(result, 0, sizeof(*result));
  result->struct_size = sizeof(*result);
}

static reader_ld_status ld_result_check(reader_ld_result *result, reader_ld_error *e) {
  if (!result || result->struct_size < sizeof(*result))
    return ld_fail(e, READER_LD_ARGUMENT, EXR_OK, 0, "Invalid result");
  reader_ld_result_init(result);
  return READER_LD_OK;
}

static exr_status ld_export_status(const reader_ld_options *o, int64_t id, const char *destination,
    uint64_t *written, exr_error *se) {
  exr_sideload_options so;
  memset(&so, 0, sizeof(so));
  so.struct_size = sizeof(so); so.max_input_bytes = o->max_input_bytes; so.control = o->control;
  return exr_sideload_export_original(o->library, id, destination, &so, written, se);
}

static reader_ld_status ld_remove_locked(const reader_ld_options *o, const char *book_key,
    reader_ld_result *result, reader_ld_error *e) {
  reader_ld_status status;
  ld_key key;
  ld_row row;
  ld_intent intent, pending;
  exr_book *books = NULL;
  size_t count = 0, i;
  int present = 0, has_row = 0, begun = 0;
  char path[LD_PATH], tmp[LD_PATH], originals[LD_PATH], export_path[LD_PATH], name[96];
  if (e) memset(e, 0, sizeof(*e));
  memset(&row, 0, sizeof(row)); memset(&intent, 0, sizeof(intent));
  status = ld_result_check(result, e);
  if (status != READER_LD_OK) return status;
  status = ld_check_options(o, 1, e);
  if (status != READER_LD_OK) return status;
  if (ld_parse_key(book_key, &key) != 0)
    return ld_fail(e, READER_LD_ARGUMENT, EXR_OK, 0, "Book key must be format:sha256");
  if (ld_paths(o->state_dir, path, tmp, originals) != 0)
    return ld_fail(e, READER_LD_IO, EXR_OK, 0, "State path is too long");
  status = ld_intent_read(o->state_dir, &pending, &present, e);
  if (status != READER_LD_OK) return status;
  if (present)
    return ld_fail(e, READER_LD_PENDING, EXR_OK, 0, "An unfinished removal of %s must be recovered first", pending.key);
  status = ld_metadata(o, &key, &row, e);
  if (status != READER_LD_OK) return status;
  has_row = 1;
  if (row.sdk_book_id <= 0) { result->outcome = READER_LD_OUTCOME_ALREADY_CLOUD; goto done; }
  status = ld_has_local(o, row.sdk_book_id, &present, e);
  if (status != READER_LD_OK) goto done;
  if (!present) { result->outcome = READER_LD_OUTCOME_ALREADY_CLOUD; goto done; }
  memset(&intent, 0, sizeof(intent));
  snprintf(intent.key, sizeof(intent.key), "%s", key.key);
  intent.bytes = row.bytes; intent.mapped = row.sdk_book_id;
  intent.ids[0] = row.sdk_book_id; intent.count = 1;
  if (ld_cancelled(o)) { status = ld_fail(e, READER_LD_CANCELLED, EXR_CANCELLED, 0, "Cancelled before starting"); goto done; }
  status = ld_busy(o, &intent, e);
  if (status != READER_LD_OK) goto done;
  if (ld_mkdir(originals) != 0) {
    status = ld_fail(e, READER_LD_IO, EXR_OK, 0, "Private original directory is unavailable");
    goto done;
  }
  /* Only this book's own files are touched: another book's retained original
     may still be open in the SDK. */
  {
    char stale[160];
    snprintf(stale, sizeof(stale), "%s.orig", key.sha);
    if (ld_remove_owned(originals, stale) != 0) {
      status = ld_fail(e, READER_LD_IO, EXR_OK, 0, "Private original directory is unavailable");
      goto done;
    }
    snprintf(stale, sizeof(stale), "%s.open", key.sha);
    if (ld_remove_owned(originals, stale) != 0) {
      status = ld_fail(e, READER_LD_IO, EXR_OK, 0, "Private original directory is unavailable");
      goto done;
    }
  }
  status = ld_set_stage(o, &intent, READER_LD_STAGE_BEGUN, e);
  if (status != READER_LD_OK) { (void)ld_unlink(tmp); goto done; }
  begun = 1;
  if (ld_cancelled(o)) { status = ld_fail(e, READER_LD_CANCELLED, EXR_CANCELLED, 0, "Cancelled while preparing"); goto done; }
  /* Prepare: identity, verified export, byte-identical copies and legacy data. */
  status = ld_list(o, &books, &count, e);
  if (status != READER_LD_OK) goto done;
  {
    const exr_book *mapped = ld_find_book(books, count, row.sdk_book_id);
    const ld_format *actual = mapped ? ld_by_exr(mapped->format) : NULL;
    size_t notes = 0, notes_total = 0, progress_total = 0;
    int progress = 0, matches = 0;
    char sha[65];
    uint64_t size = 0, written = 0;
    exr_error se;
    exr_status sdk;
    if (!mapped || actual != key.format) {
      status = ld_fail(e, READER_LD_IDENTITY, EXR_OK, 0, "Mapped SDK row is missing or has another format");
      goto done;
    }
    snprintf(name, sizeof(name), "%s.orig", key.sha);
    if (ld_join(export_path, sizeof(export_path), originals, name) != 0) {
      status = ld_fail(e, READER_LD_IO, EXR_OK, 0, "Export path is too long");
      goto done;
    }
    memset(&se, 0, sizeof(se));
    sdk = ld_export_status(o, mapped->id, export_path, &written, &se);
    if (sdk != EXR_OK) { status = ld_sdk_fail(e, sdk, &se, "Original export"); goto done; }
    status = ld_hash_file(o, export_path, sha, &size, e);
    if (status != READER_LD_OK) goto done;
    if (size != row.bytes || written != row.bytes || strcmp(sha, key.sha)) {
      status = ld_fail(e, READER_LD_IDENTITY, EXR_OK, 0, "Stored original differs from its format and SHA-256 identity");
      goto done;
    }
    status = ld_legacy_scan(o, mapped, &notes, &progress, e);
    if (status != READER_LD_OK) goto done;
    notes_total = notes; progress_total = progress ? 1u : 0u;
    for (i = 0; i < count; i++) {
      if (books[i].id == mapped->id || books[i].format != mapped->format) continue;
      status = ld_verify_row(o, &books[i], &key, row.bytes, &matches, e);
      if (status != READER_LD_OK) goto done;
      if (!matches) continue;
      if (intent.count >= READER_LD_MAX_COPIES) {
        status = ld_fail(e, READER_LD_TOO_MANY_COPIES, EXR_OK, 0, "More than %u identical SDK copies", READER_LD_MAX_COPIES);
        goto done;
      }
      intent.ids[intent.count++] = books[i].id;
      status = ld_legacy_scan(o, &books[i], &notes, &progress, e);
      if (status != READER_LD_OK) goto done;
      notes_total += notes; progress_total += progress ? 1u : 0u;
    }
    result->legacy_notes = notes_total; result->legacy_progress = progress_total;
    if ((notes_total || progress_total) && o->legacy_policy == READER_LD_LEGACY_REJECT) {
      status = ld_fail(e, READER_LD_LEGACY_DATA, EXR_OK, 0,
        "SDK-only notes/progress exist: %u notes, %u rows with progress; keep them or use the backup policy",
        (unsigned)notes_total, (unsigned)progress_total);
      goto done;
    }
  }
  exr_books_free(books, count); books = NULL;
  if (ld_cancelled(o)) { status = ld_fail(e, READER_LD_CANCELLED, EXR_CANCELLED, 0, "Cancelled while preparing"); goto done; }
  status = ld_set_stage(o, &intent, READER_LD_STAGE_PREPARED, e);
  if (status != READER_LD_OK) goto done;
  status = ld_forward(o, &intent, 1, result, e);
  begun = status == READER_LD_OK ? 0 : -1; /* forward owns its own cleanup after PREPARED. */
done:
  if (books) exr_books_free(books, count);
  if (has_row) ld_row_free(&row);
  if (begun == 1 && status != READER_LD_OK) { reader_ld_error ignored; (void)ld_rollback(o->state_dir, key.sha, &ignored); }
  if (status != READER_LD_OK && result->outcome != READER_LD_OUTCOME_RESTORED) result->outcome = READER_LD_OUTCOME_NONE;
  return status;
}

static reader_ld_status ld_recover_locked(const reader_ld_options *o, reader_ld_result *result,
    reader_ld_error *e) {
  reader_ld_status status;
  ld_intent intent;
  int present = 0, mapped = 0;
  if (e) memset(e, 0, sizeof(*e));
  status = ld_result_check(result, e);
  if (status != READER_LD_OK) return status;
  status = ld_check_options(o, 1, e);
  if (status != READER_LD_OK) return status;
  status = ld_intent_read(o->state_dir, &intent, &present, e);
  if (status != READER_LD_OK) return status;
  if (!present) { result->outcome = READER_LD_OUTCOME_NOTHING_PENDING; return READER_LD_OK; }
  result->sdk_book_id = intent.mapped;
  {
    ld_key key;
    if (ld_parse_key(intent.key, &key) != 0)
      return ld_fail(e, READER_LD_CORRUPT_INTENT, EXR_OK, 0, "Intent key is invalid");
    if (intent.stage == READER_LD_STAGE_BEGUN) {
      status = ld_rollback(o->state_dir, key.sha, e);
      if (status == READER_LD_OK) result->outcome = READER_LD_OUTCOME_ROLLED_BACK;
      return status;
    }
  }
  if (intent.stage == READER_LD_STAGE_PREPARED) {
    ld_key key;
    status = ld_has_local(o, intent.mapped, &mapped, e);
    if (status != READER_LD_OK) return status;
    if (mapped && ld_parse_key(intent.key, &key) != 0)
      return ld_fail(e, READER_LD_CORRUPT_INTENT, EXR_OK, 0, "Intent key is invalid");
    if (mapped) {
      /* No mapping change happened yet: undo the preparation instead. */
      status = ld_rollback(o->state_dir, key.sha, e);
      if (status == READER_LD_OK) result->outcome = READER_LD_OUTCOME_ROLLED_BACK;
      return status;
    }
  }
  return ld_forward(o, &intent, 0, result, e);
}

reader_ld_status reader_ld_pending(const char *state_dir, reader_ld_pending_info *info,
    reader_ld_error *e) {
  ld_intent intent;
  int present = 0;
  reader_ld_status status;
  if (e) memset(e, 0, sizeof(*e));
  if (!state_dir || !state_dir[0] || strlen(state_dir) > 700 || !info || info->struct_size < sizeof(*info))
    return ld_fail(e, READER_LD_ARGUMENT, EXR_OK, 0, "Invalid pending query");
  memset(info, 0, sizeof(*info)); info->struct_size = sizeof(*info);
  status = ld_intent_read(state_dir, &intent, &present, e);
  if (status != READER_LD_OK || !present) return status;
  info->pending = 1; info->stage = (reader_ld_stage)intent.stage;
  snprintf(info->book_key, sizeof(info->book_key), "%s", intent.key);
  info->sdk_book_id = intent.mapped; info->copies = intent.count;
  return READER_LD_OK;
}

static reader_ld_status ld_reimport_locked(const reader_ld_options *o, const char *book_key,
    const char *path, reader_ld_result *result, reader_ld_error *e) {
  reader_ld_status status;
  ld_key key;
  ld_row row;
  ld_intent pending;
  exr_sideload_options so;
  exr_sideload_result sr;
  exr_error se;
  exr_status sdk;
  char sha[65];
  uint64_t size = 0;
  int present = 0, has_row = 0;
  if (e) memset(e, 0, sizeof(*e));
  status = ld_result_check(result, e);
  if (status != READER_LD_OK) return status;
  status = ld_check_options(o, 1, e);
  if (status != READER_LD_OK) return status;
  if (ld_parse_key(book_key, &key) != 0 || !path || !path[0])
    return ld_fail(e, READER_LD_ARGUMENT, EXR_OK, 0, "Book key and file path are required");
  status = ld_intent_read(o->state_dir, &pending, &present, e);
  if (status != READER_LD_OK) return status;
  if (present) return ld_fail(e, READER_LD_PENDING, EXR_OK, 0, "An unfinished removal must be recovered first");
  status = ld_metadata(o, &key, &row, e);
  if (status != READER_LD_OK) return status;
  has_row = 1;
  if (row.deleted) { status = ld_fail(e, READER_LD_NOT_FOUND, EXR_OK, 0, "The book was deleted from the library"); goto done; }
  if (row.sdk_book_id > 0) {
    status = ld_has_local(o, row.sdk_book_id, &present, e);
    if (status != READER_LD_OK) goto done;
    if (present) { result->outcome = READER_LD_OUTCOME_ALREADY_LOCAL; result->sdk_book_id = row.sdk_book_id; goto done; }
  }
  {
    char originals[LD_PATH], stage[LD_PATH], name[160], imported[65];
    exr_source check;
    memset(&check, 0, sizeof(check));
    if (ld_join(originals, sizeof(originals), o->state_dir, "originals") != 0 || ld_mkdir(originals) != 0) {
      status = ld_fail(e, READER_LD_IO, EXR_OK, 0, "Private original directory is unavailable");
      goto done;
    }
    snprintf(name, sizeof(name), "%s.open", key.sha);
    if (ld_join(stage, sizeof(stage), originals, name) != 0) {
      status = ld_fail(e, READER_LD_IO, EXR_OK, 0, "Staging path is too long");
      goto done;
    }
    /* Hash and import consume one private copy of exactly the verified bytes:
       a pathname swapped after hashing cannot change what the SDK stores. */
    status = ld_stage_copy(o, path, stage, sha, &size, e);
    if (status != READER_LD_OK) goto done;
    if (size != row.bytes || strcmp(sha, key.sha)) {
      (void)ld_unlink(stage);
      status = ld_fail(e, READER_LD_IDENTITY, EXR_OK, 0, "File differs from the book's format and SHA-256 identity");
      goto done;
    }
    memset(&so, 0, sizeof(so)); memset(&sr, 0, sizeof(sr)); memset(&se, 0, sizeof(se));
    so.struct_size = sizeof(so); so.max_input_bytes = o->max_input_bytes; so.control = o->control;
    sr.struct_size = sizeof(sr);
    sdk = exr_sideload_import_file(o->library, key.format->format, stage, row.title, &so, &sr, &se);
    if (sdk != EXR_OK) { (void)ld_unlink(stage); status = ld_sdk_fail(e, sdk, &se, "SDK import"); goto done; }
    /* Verify the row the SDK actually created before it is ever mapped. */
    imported[0] = 0;
    sdk = exr_library_source(o->library, sr.book_id, &check, &se);
    if (sdk != EXR_OK) {
      status = ld_sdk_fail(e, sdk, &se, "Imported original");
    } else if (check.size != row.bytes) {
      if (check.release) check.release(check.context);
      status = ld_fail(e, READER_LD_IDENTITY, EXR_OK, 0, "Imported original has another size");
    } else {
      status = ld_hash_source(o, &check, imported, e);
      if (check.release) check.release(check.context);
    }
    if (status != READER_LD_OK || strcmp(imported, key.sha)) {
      if (sr.created) { exr_error ignored; (void)exr_library_delete(o->library, sr.book_id, &ignored); }
      (void)ld_unlink(stage);
      if (status == READER_LD_OK)
        status = ld_fail(e, READER_LD_IDENTITY, EXR_OK, 0, "Imported original differs from the book identity");
      goto done;
    }
    status = ld_attach(o, &key, &row, sr.book_id, e);
    if (status != READER_LD_OK) {
      if (sr.created) { exr_error ignored; (void)exr_library_delete(o->library, sr.book_id, &ignored); }
      (void)ld_unlink(stage);
      goto done;
    }
    /* A PDF original is read through a private stable file, so the verified
       copy outlives this call until the same book is removed again. */
    if (key.format->format == EXR_PDF) {
      char stable[LD_PATH];
      snprintf(name, sizeof(name), "%s.orig", key.sha);
      if (ld_join(stable, sizeof(stable), originals, name) != 0 || ld_replace(stage, stable, originals) != 0) {
        (void)ld_unlink(stage);
        status = ld_fail(e, READER_LD_IO, EXR_OK, 0, "Verified original could not be retained");
        goto done;
      }
    } else {
      (void)ld_unlink(stage);
    }
  }
  result->outcome = READER_LD_OUTCOME_ATTACHED;
  result->sdk_book_id = sr.book_id;
done:
  if (has_row) ld_row_free(&row);
  return status;
}

reader_ld_status reader_ld_remove(const reader_ld_options *o, const char *book_key,
    reader_ld_result *result, reader_ld_error *e) {
  reader_ld_status status;
  if (ld_enter() != 0)
    return ld_fail(e, READER_LD_BUSY, EXR_OK, 0, "A local-download call is already running");
  status = ld_remove_locked(o, book_key, result, e);
  ld_leave();
  return status;
}

reader_ld_status reader_ld_recover(const reader_ld_options *o, reader_ld_result *result,
    reader_ld_error *e) {
  reader_ld_status status;
  if (ld_enter() != 0)
    return ld_fail(e, READER_LD_BUSY, EXR_OK, 0, "A local-download call is already running");
  status = ld_recover_locked(o, result, e);
  ld_leave();
  return status;
}

reader_ld_status reader_ld_reimport(const reader_ld_options *o, const char *book_key,
    const char *path, reader_ld_result *result, reader_ld_error *e) {
  reader_ld_status status;
  if (ld_enter() != 0)
    return ld_fail(e, READER_LD_BUSY, EXR_OK, 0, "A local-download call is already running");
  status = ld_reimport_locked(o, book_key, path, result, e);
  ld_leave();
  return status;
}

const char *reader_ld_status_name(reader_ld_status status) {
  switch (status) {
    case READER_LD_OK: return "ok";
    case READER_LD_CANCELLED: return "cancelled";
    case READER_LD_ARGUMENT: return "argument";
    case READER_LD_MEMORY: return "memory";
    case READER_LD_IO: return "io";
    case READER_LD_CATALOG: return "catalog";
    case READER_LD_SDK: return "sdk";
    case READER_LD_NOT_FOUND: return "not_found";
    case READER_LD_BUSY: return "busy";
    case READER_LD_IDENTITY: return "identity";
    case READER_LD_LEGACY_DATA: return "legacy_data";
    case READER_LD_TOO_MANY_COPIES: return "too_many_copies";
    case READER_LD_PENDING: return "pending";
    case READER_LD_CORRUPT_INTENT: return "corrupt_intent";
  }
  return "unknown";
}

const char *reader_ld_stage_name(reader_ld_stage stage) {
  switch (stage) {
    case READER_LD_STAGE_NONE: return "none";
    case READER_LD_STAGE_BEGUN: return "begun";
    case READER_LD_STAGE_PREPARED: return "prepared";
    case READER_LD_STAGE_UNMAPPED: return "unmapped";
    case READER_LD_STAGE_DELETED: return "deleted";
    case READER_LD_STAGE_CLEANED: return "cleaned";
  }
  return "unknown";
}

const char *reader_ld_outcome_name(reader_ld_outcome outcome) {
  switch (outcome) {
    case READER_LD_OUTCOME_NONE: return "none";
    case READER_LD_OUTCOME_REMOVED: return "removed";
    case READER_LD_OUTCOME_ALREADY_CLOUD: return "already_cloud";
    case READER_LD_OUTCOME_ROLLED_BACK: return "rolled_back";
    case READER_LD_OUTCOME_NOTHING_PENDING: return "nothing_pending";
    case READER_LD_OUTCOME_ATTACHED: return "attached";
    case READER_LD_OUTCOME_ALREADY_LOCAL: return "already_local";
    case READER_LD_OUTCOME_RESTORED: return "restored";
  }
  return "unknown";
}
