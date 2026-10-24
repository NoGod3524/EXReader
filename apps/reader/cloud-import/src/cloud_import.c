/* SPDX-License-Identifier: MIT */
#include "reader_cloud_import.h"
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#ifdef _WIN32
#include <windows.h>
#include <wchar.h>
#else
#include <unistd.h>
#endif

#define RC_BLOCK 65536u
#define RC_NAME_TRIES 16u

struct reader_cloud_staged {
  char *path;
  char *display_name;
  uint64_t bytes;
  exr_format format;
  char sha256[65];
};

/* ---- small helpers ------------------------------------------------------ */

static void rc_fail(reader_cloud_error *error, reader_cloud_status code, const char *message) {
  if (!error) return;
  memset(error, 0, sizeof(*error));
  error->code = code;
  error->sdk_code = EXR_OK;
  strncpy(error->message, message, sizeof(error->message) - 1);
}

static size_t rc_len(const char *text, size_t limit) {
  size_t i = 0;
  while (i < limit && text[i]) i++;
  return i;
}

static int rc_utf8_valid(const char *text, int allow_controls) {
  const unsigned char *s = (const unsigned char *)text;
  while (*s) {
    unsigned char c = *s++;
    if (c < 0x80) {
      if (!allow_controls && (c < 0x20 || c == 0x7f)) return 0;
      continue;
    }
    if (c < 0xC2) return 0;
    if (c < 0xE0) {
      if ((*s & 0xC0) != 0x80) return 0;
      s++;
    } else if (c < 0xF0) {
      if ((s[0] & 0xC0) != 0x80 || (s[1] & 0xC0) != 0x80) return 0;
      if (c == 0xE0 && s[0] < 0xA0) return 0;
      if (c == 0xED && s[0] >= 0xA0) return 0;
      s += 2;
    } else if (c < 0xF5) {
      if ((s[0] & 0xC0) != 0x80 || (s[1] & 0xC0) != 0x80 || (s[2] & 0xC0) != 0x80) return 0;
      if (c == 0xF0 && s[0] < 0x90) return 0;
      if (c == 0xF4 && s[0] >= 0x90) return 0;
      s += 3;
    } else {
      return 0;
    }
  }
  return 1;
}

static char *rc_dup(const char *text, size_t length) {
  char *copy = malloc(length + 1);
  if (!copy) return NULL;
  memcpy(copy, text, length);
  copy[length] = 0;
  return copy;
}

#ifdef _WIN32
static wchar_t *rc_widen(const char *text) {
  int count = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, text, -1, NULL, 0);
  wchar_t *wide;
  if (count <= 0) return NULL;
  wide = malloc((size_t)count * sizeof(*wide));
  if (!wide) return NULL;
  if (!MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, text, -1, wide, count)) {
    free(wide);
    return NULL;
  }
  return wide;
}
#endif

static FILE *rc_open_read(const char *path) {
#ifdef _WIN32
  wchar_t *wide = rc_widen(path);
  FILE *file;
  if (!wide) return NULL;
  file = _wfopen(wide, L"rb");
  free(wide);
  return file;
#else
  return fopen(path, "rb");
#endif
}

/* Removes only the named staging file; a missing file is not an error. */
static void rc_remove(const char *path) {
#ifdef _WIN32
  wchar_t *wide = rc_widen(path);
  if (!wide) return;
  _wremove(wide);
  free(wide);
#else
  unlink(path);
#endif
}

static char rc_sep(const char *directory) {
#ifdef _WIN32
  (void)directory;
  return '\\';
#else
  (void)directory;
  return '/';
#endif
}

static const char *rc_extension(exr_format format) {
  switch (format) {
    case EXR_TXT: return "txt";
    case EXR_HTML: return "html";
    case EXR_FB2: return "fb2";
    case EXR_EPUB: return "epub";
    case EXR_DOCX: return "docx";
    case EXR_RTF: return "rtf";
    case EXR_MOBI: return "mobi";
    case EXR_PDF: return "pdf";
    case EXR_CBZ: return "cbz";
    default: return NULL;
  }
}

static uint64_t rc_format_ceiling(exr_format format) {
  return format == EXR_EPUB || format == EXR_CBZ || format == EXR_PDF
      ? READER_CLOUD_STREAM_LIMIT : READER_CLOUD_MEMORY_LIMIT;
}

static uint64_t rc_effective_limit(exr_format format, uint64_t requested) {
  uint64_t hard = rc_format_ceiling(format);
  return requested && requested < hard ? requested : hard;
}

static int rc_ieq(const char *a, const char *b) {
  while (*a && *b) {
    char x = *a++, y = *b++;
    if (x >= 'A' && x <= 'Z') x = (char)(x - 'A' + 'a');
    if (y >= 'A' && y <= 'Z') y = (char)(y - 'A' + 'a');
    if (x != y) return 0;
  }
  return *a == *b;
}

exr_format reader_cloud_format_from_name(const char *name) {
  static const struct { const char *ext; exr_format format; } table[] = {
    {"txt", EXR_TXT}, {"html", EXR_HTML}, {"htm", EXR_HTML}, {"fb2", EXR_FB2},
    {"epub", EXR_EPUB}, {"docx", EXR_DOCX}, {"rtf", EXR_RTF}, {"mobi", EXR_MOBI},
    {"azw", EXR_MOBI}, {"azw3", EXR_MOBI}, {"pdf", EXR_PDF}, {"cbz", EXR_CBZ}};
  const char *dot = NULL, *p;
  size_t i;
  if (!name) return EXR_CUSTOM;
  for (p = name; *p; p++)
    if (*p == '.') dot = p;
  if (!dot || !dot[1]) return EXR_CUSTOM;
  for (i = 0; i < sizeof(table) / sizeof(table[0]); i++)
    if (rc_ieq(dot + 1, table[i].ext)) return table[i].format;
  return EXR_CUSTOM;
}

const char *reader_cloud_status_name(reader_cloud_status status) {
  switch (status) {
    case READER_CLOUD_OK: return "ok";
    case READER_CLOUD_ARGUMENT: return "argument";
    case READER_CLOUD_MEMORY: return "memory";
    case READER_CLOUD_IO: return "io";
    case READER_CLOUD_CANCELLED: return "cancelled";
    case READER_CLOUD_REMOTE: return "remote";
    case READER_CLOUD_LENGTH: return "length";
    case READER_CLOUD_LIMIT: return "limit";
    case READER_CLOUD_CORRUPT: return "corrupt";
    case READER_CLOUD_IMPORT: return "import";
  }
  return "unknown";
}

/* ---- SHA-256 ------------------------------------------------------------ */

typedef struct {
  uint32_t state[8];
  uint64_t length;
  unsigned char block[64];
  size_t used;
} rc_sha;

static const uint32_t rc_k[64] = {
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
  0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
  0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
  0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
  0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
  0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2};

#define RC_ROR(x, n) (((x) >> (n)) | ((x) << (32 - (n))))

static void rc_sha_init(rc_sha *s) {
  static const uint32_t init[8] = {0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
      0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19};
  memcpy(s->state, init, sizeof(init));
  s->length = 0;
  s->used = 0;
}

static void rc_sha_block(rc_sha *s, const unsigned char *p) {
  uint32_t w[64], v[8], t1, t2;
  int i;
  for (i = 0; i < 16; i++)
    w[i] = ((uint32_t)p[i * 4] << 24) | ((uint32_t)p[i * 4 + 1] << 16) |
        ((uint32_t)p[i * 4 + 2] << 8) | (uint32_t)p[i * 4 + 3];
  for (i = 16; i < 64; i++) {
    uint32_t s0 = RC_ROR(w[i - 15], 7) ^ RC_ROR(w[i - 15], 18) ^ (w[i - 15] >> 3);
    uint32_t s1 = RC_ROR(w[i - 2], 17) ^ RC_ROR(w[i - 2], 19) ^ (w[i - 2] >> 10);
    w[i] = w[i - 16] + s0 + w[i - 7] + s1;
  }
  memcpy(v, s->state, sizeof(v));
  for (i = 0; i < 64; i++) {
    t1 = v[7] + (RC_ROR(v[4], 6) ^ RC_ROR(v[4], 11) ^ RC_ROR(v[4], 25)) +
        ((v[4] & v[5]) ^ (~v[4] & v[6])) + rc_k[i] + w[i];
    t2 = (RC_ROR(v[0], 2) ^ RC_ROR(v[0], 13) ^ RC_ROR(v[0], 22)) +
        ((v[0] & v[1]) ^ (v[0] & v[2]) ^ (v[1] & v[2]));
    v[7] = v[6]; v[6] = v[5]; v[5] = v[4]; v[4] = v[3] + t1;
    v[3] = v[2]; v[2] = v[1]; v[1] = v[0]; v[0] = t1 + t2;
  }
  for (i = 0; i < 8; i++) s->state[i] += v[i];
}

static void rc_sha_update(rc_sha *s, const unsigned char *data, size_t size) {
  s->length += size;
  while (size) {
    size_t take = 64 - s->used;
    if (take > size) take = size;
    memcpy(s->block + s->used, data, take);
    s->used += take;
    data += take;
    size -= take;
    if (s->used == 64) {
      rc_sha_block(s, s->block);
      s->used = 0;
    }
  }
}

static void rc_sha_hex(rc_sha *s, char out[65]) {
  static const char digits[] = "0123456789abcdef";
  uint64_t bits = s->length * 8;
  unsigned char pad = 0x80, zero = 0, tail[8];
  int i, j;
  rc_sha_update(s, &pad, 1);
  while (s->used != 56) rc_sha_update(s, &zero, 1);
  for (i = 0; i < 8; i++) tail[i] = (unsigned char)(bits >> (56 - 8 * i));
  rc_sha_update(s, tail, 8);
  for (i = 0; i < 8; i++)
    for (j = 0; j < 4; j++) {
      unsigned char byte = (unsigned char)(s->state[i] >> (24 - 8 * j));
      out[i * 8 + j * 2] = digits[byte >> 4];
      out[i * 8 + j * 2 + 1] = digits[byte & 15];
    }
  out[64] = 0;
}

typedef enum { RC_HASH_OK, RC_HASH_IO, RC_HASH_CANCELLED, RC_HASH_MEMORY } rc_hash_status;

/* Streams the file in 64 KiB blocks; counts bytes independently of any stat. */
static rc_hash_status rc_hash_file(const char *path, const reader_cloud_control *control,
    uint64_t *bytes, char hex[65]) {
  FILE *file = rc_open_read(path);
  unsigned char *buffer;
  rc_sha sha;
  size_t got;
  *bytes = 0;
  if (!file) return RC_HASH_IO;
  buffer = malloc(RC_BLOCK);
  if (!buffer) {
    fclose(file);
    return RC_HASH_MEMORY;
  }
  rc_sha_init(&sha);
  for (;;) {
    if (control && control->cancelled && control->cancelled(control->context)) {
      free(buffer);
      fclose(file);
      return RC_HASH_CANCELLED;
    }
    got = fread(buffer, 1, RC_BLOCK, file);
    if (got) {
      rc_sha_update(&sha, buffer, got);
      *bytes += got;
    }
    if (got < RC_BLOCK) {
      int failed = ferror(file);
      free(buffer);
      fclose(file);
      if (failed) return RC_HASH_IO;
      rc_sha_hex(&sha, hex);
      return RC_HASH_OK;
    }
  }
}

/* ---- staged value ------------------------------------------------------- */

void reader_cloud_request_init(reader_cloud_request *request) {
  if (!request) return;
  memset(request, 0, sizeof(*request));
  request->struct_size = sizeof(*request);
}

void reader_cloud_import_options_init(reader_cloud_import_options *options) {
  if (!options) return;
  memset(options, 0, sizeof(*options));
  options->struct_size = sizeof(*options);
}

const char *reader_cloud_staged_path(const reader_cloud_staged *s) { return s ? s->path : NULL; }
const char *reader_cloud_staged_name(const reader_cloud_staged *s) { return s ? s->display_name : NULL; }
uint64_t reader_cloud_staged_bytes(const reader_cloud_staged *s) { return s ? s->bytes : 0; }
exr_format reader_cloud_staged_format(const reader_cloud_staged *s) { return s ? s->format : EXR_CUSTOM; }
const char *reader_cloud_staged_sha256(const reader_cloud_staged *s) { return s ? s->sha256 : NULL; }

static void rc_staged_free(reader_cloud_staged *s) {
  if (!s) return;
  free(s->path);
  free(s->display_name);
  free(s);
}

void reader_cloud_staged_discard(reader_cloud_staged **staged) {
  if (!staged || !*staged) return;
  if ((*staged)->path) rc_remove((*staged)->path);
  rc_staged_free(*staged);
  *staged = NULL;
}

/* ---- phase 1: download -------------------------------------------------- */

typedef struct {
  const reader_cloud_control *user;
  uint64_t limit;
  uint64_t received;
  int limit_hit;
  int user_cancelled;
} rc_net_state;

static int rc_net_cancelled(void *opaque) {
  rc_net_state *s = opaque;
  if (s->limit_hit) return 1;
  if (s->user && s->user->cancelled && s->user->cancelled(s->user->context)) {
    s->user_cancelled = 1;
    return 1;
  }
  return 0;
}

static void rc_net_progress(void *opaque, uint64_t received) {
  rc_net_state *s = opaque;
  s->received = received;
  if (received > s->limit) s->limit_hit = 1;
  if (s->user && s->user->progress) s->user->progress(s->user->context, received);
}

static uint64_t rc_name_counter;

static uint64_t rc_mix(uint64_t x) {
  x += UINT64_C(0x9E3779B97F4A7C15);
  x = (x ^ (x >> 30)) * UINT64_C(0xBF58476D1CE4E5B9);
  x = (x ^ (x >> 27)) * UINT64_C(0x94D049BB133111EB);
  return x ^ (x >> 31);
}

static uint64_t rc_name_seed(const void *address) {
  uint64_t seed = (uint64_t)(uintptr_t)address;
#ifdef _WIN32
  LARGE_INTEGER ticks;
  QueryPerformanceCounter(&ticks);
  seed ^= (uint64_t)ticks.QuadPart ^ ((uint64_t)GetCurrentProcessId() << 32);
  seed += (uint64_t)InterlockedIncrement64((volatile LONG64 *)&rc_name_counter);
#else
  seed ^= ((uint64_t)getpid() << 32) ^ (uint64_t)clock();
  seed += (uint64_t)__sync_add_and_fetch(&rc_name_counter, 1);
#endif
  return rc_mix(seed);
}

static void rc_remote_error(reader_cloud_error *error, const exr_webdav_error *dav) {
  rc_fail(error, READER_CLOUD_REMOTE, dav->message[0] ? dav->message : "WebDAV request failed");
  if (error) {
    error->webdav_code = dav->code;
    error->http_status = dav->http_status;
  }
}

reader_cloud_status reader_cloud_download(exr_webdav_client *client,
    const reader_cloud_request *request, reader_cloud_staged **out,
    reader_cloud_error *error) {
  reader_cloud_staged *staged = NULL;
  rc_net_state state;
  exr_webdav_control control;
  exr_webdav_download download;
  exr_webdav_error dav;
  exr_webdav_status status = EXR_DAV_EXISTS;
  exr_format format;
  const char *ext;
  size_t dir_len, name_len;
  char filename[48];
  uint64_t limit, seed;
  unsigned attempt;
  rc_hash_status hashed;
  uint64_t verified;
  char hex[65];

  if (out) *out = NULL;
  if (!client || !request || !out || request->struct_size < sizeof(*request) ||
      !request->resource || !request->staging_dir || !request->display_name) {
    rc_fail(error, READER_CLOUD_ARGUMENT, "client, request, resource, display name, staging directory and output are required");
    return READER_CLOUD_ARGUMENT;
  }
  name_len = rc_len(request->display_name, READER_CLOUD_MAX_NAME_BYTES + 1);
  dir_len = rc_len(request->staging_dir, 32768);
  if (!request->resource[0] || rc_len(request->resource, READER_CLOUD_MAX_RESOURCE_BYTES + 1) > READER_CLOUD_MAX_RESOURCE_BYTES ||
      !name_len || name_len > READER_CLOUD_MAX_NAME_BYTES || !dir_len || dir_len >= 32768 ||
      !rc_utf8_valid(request->display_name, 1) || !rc_utf8_valid(request->staging_dir, 0)) {
    rc_fail(error, READER_CLOUD_ARGUMENT, "resource, display name or staging directory is empty, too long or not valid UTF-8");
    return READER_CLOUD_ARGUMENT;
  }
  format = request->format ? request->format : reader_cloud_format_from_name(request->display_name);
  ext = rc_extension(format);
  if (!ext) {
    rc_fail(error, READER_CLOUD_ARGUMENT, "not one of the nine importable formats");
    return READER_CLOUD_ARGUMENT;
  }
  limit = rc_effective_limit(format, request->max_bytes);
  if (request->expected_bytes > limit) {
    rc_fail(error, READER_CLOUD_LIMIT, "declared length exceeds the format ceiling");
    return READER_CLOUD_LIMIT;
  }
  if (request->control.cancelled && request->control.cancelled(request->control.context)) {
    rc_fail(error, READER_CLOUD_CANCELLED, "cancelled before the request");
    return READER_CLOUD_CANCELLED;
  }

  memset(&state, 0, sizeof(state));
  state.user = &request->control;
  state.limit = limit;
  control.cancelled = rc_net_cancelled;
  control.progress = rc_net_progress;
  control.context = &state;
  seed = rc_name_seed(request);
  for (attempt = 0; attempt < RC_NAME_TRIES; attempt++) {
    memset(&download, 0, sizeof(download));
    memset(&dav, 0, sizeof(dav));
    seed = rc_mix(seed + attempt);
    snprintf(filename, sizeof(filename), "cloud-%016llx.%s", (unsigned long long)seed, ext);
    status = exr_webdav_download_file(client, request->resource, request->staging_dir, filename,
        &control, &download, &dav);
    if (status != EXR_DAV_EXISTS) break;
  }

  staged = calloc(1, sizeof(*staged));
  if (!staged) {
    /* A published file cannot be tracked without memory; do not leave it behind. */
    status = status == EXR_DAV_OK ? EXR_DAV_MEMORY : status;
  } else {
    staged->path = malloc(dir_len + 1 + strlen(filename) + 1);
    staged->display_name = rc_dup(request->display_name, name_len);
    if (staged->path) {
      memcpy(staged->path, request->staging_dir, dir_len);
      if (staged->path[dir_len - 1] == '/' || staged->path[dir_len - 1] == '\\') dir_len--;
      staged->path[dir_len] = rc_sep(request->staging_dir);
      strcpy(staged->path + dir_len + 1, filename);
    }
    if (!staged->path || !staged->display_name) status = status == EXR_DAV_OK ? EXR_DAV_MEMORY : status;
  }

  if (status != EXR_DAV_OK) {
    /* Nothing was published on failure; on a memory failure after publish the
       file is removed here so no unreferenced staging file remains. */
    if (staged && staged->path && download.published) rc_remove(staged->path);
    else if (!staged && download.published) {
      char *path = malloc(dir_len + 1 + strlen(filename) + 1);
      if (path) {
        snprintf(path, dir_len + 1 + strlen(filename) + 1, "%s%c%s", request->staging_dir, rc_sep(NULL), filename);
        rc_remove(path);
        free(path);
      }
    }
    rc_staged_free(staged);
    if (state.limit_hit || status == EXR_DAV_LIMIT) {
      rc_fail(error, READER_CLOUD_LIMIT, "download exceeds the byte limit");
      return READER_CLOUD_LIMIT;
    }
    if (status == EXR_DAV_CANCELLED || state.user_cancelled) {
      rc_fail(error, READER_CLOUD_CANCELLED, "cancelled during download");
      return READER_CLOUD_CANCELLED;
    }
    if (status == EXR_DAV_MEMORY) {
      rc_fail(error, READER_CLOUD_MEMORY, "out of memory");
      return READER_CLOUD_MEMORY;
    }
    if (status == EXR_DAV_ARGUMENT) {
      rc_remote_error(error, &dav);
      error->code = READER_CLOUD_ARGUMENT;
      return READER_CLOUD_ARGUMENT;
    }
    rc_remote_error(error, &dav);
    return READER_CLOUD_REMOTE;
  }

  /* Published: the file is complete. Fix length, then hash for the handoff. */
  staged->format = format;
  staged->bytes = download.bytes;
  if (request->expected_bytes && download.bytes != request->expected_bytes) {
    reader_cloud_staged_discard(&staged);
    rc_fail(error, READER_CLOUD_LENGTH, "received length differs from the declared length");
    return READER_CLOUD_LENGTH;
  }
  if (download.bytes > limit) {
    reader_cloud_staged_discard(&staged);
    rc_fail(error, READER_CLOUD_LIMIT, "download exceeds the byte limit");
    return READER_CLOUD_LIMIT;
  }
  hashed = rc_hash_file(staged->path, NULL, &verified, hex);
  if (hashed != RC_HASH_OK || verified != download.bytes) {
    reader_cloud_staged_discard(&staged);
    if (hashed == RC_HASH_MEMORY) {
      rc_fail(error, READER_CLOUD_MEMORY, "out of memory");
      return READER_CLOUD_MEMORY;
    }
    rc_fail(error, READER_CLOUD_IO, "published staging file could not be read back");
    return READER_CLOUD_IO;
  }
  memcpy(staged->sha256, hex, sizeof(hex));
  *out = staged;
  if (error) memset(error, 0, sizeof(*error));
  return READER_CLOUD_OK;
}

/* ---- phase 2: SDK import ------------------------------------------------ */

typedef struct {
  const reader_cloud_control *user;
} rc_sdk_state;

static int rc_sdk_cancelled(void *opaque) {
  const reader_cloud_control *c = ((rc_sdk_state *)opaque)->user;
  return c && c->cancelled && c->cancelled(c->context);
}

/* Title: explicit option, else the display name without its extension. */
static char *rc_title(const reader_cloud_import_options *options, const reader_cloud_staged *s,
    reader_cloud_error *error, int *failed) {
  const char *source = options && options->title && options->title[0] ? options->title : NULL;
  size_t length;
  *failed = 0;
  if (source) {
    length = rc_len(source, READER_CLOUD_MAX_NAME_BYTES + 1);
    if (length > READER_CLOUD_MAX_NAME_BYTES || !rc_utf8_valid(source, 0)) {
      rc_fail(error, READER_CLOUD_ARGUMENT, "title is too long, not valid UTF-8 or contains control characters");
      *failed = 1;
      return NULL;
    }
    return rc_dup(source, length);
  }
  source = s->display_name;
  length = strlen(source);
  if (reader_cloud_format_from_name(source) != EXR_CUSTOM) {
    const char *dot = strrchr(source, '.');
    if (dot) length = (size_t)(dot - source);
  }
  if (!length) return NULL;
  {
    char *derived = rc_dup(source, length);
    /* A remote name with control characters is display-only: fall back to
       the book's embedded metadata instead of storing it as a title. */
    if (derived && !rc_utf8_valid(derived, 0)) {
      free(derived);
      return NULL;
    }
    return derived;
  }
}

reader_cloud_status reader_cloud_import(exr_library *library, reader_cloud_staged **staged,
    const reader_cloud_import_options *options, reader_cloud_import_result *result,
    reader_cloud_error *error) {
  reader_cloud_staged *s;
  reader_cloud_control none, *control;
  rc_sdk_state state;
  exr_sideload_options sdk_options;
  exr_sideload_result sdk_result;
  exr_error sdk_error;
  exr_status sdk_status;
  reader_cloud_status code = READER_CLOUD_OK;
  rc_hash_status hashed;
  uint64_t seen = 0, limit;
  char hex[65];
  char *title = NULL;
  int title_failed = 0;

  if (!library || !staged || !*staged || !result || result->struct_size < sizeof(*result) ||
      (options && options->struct_size < sizeof(*options))) {
    rc_fail(error, READER_CLOUD_ARGUMENT, "library, staged value, result and sized options are required");
    return READER_CLOUD_ARGUMENT;
  }
  s = *staged;
  memset(&none, 0, sizeof(none));
  control = options ? (reader_cloud_control *)&options->control : &none;
  {
    size_t size = result->struct_size;
    memset(result, 0, sizeof(*result));
    result->struct_size = size;
  }
  title = rc_title(options, s, error, &title_failed);
  if (title_failed) return READER_CLOUD_ARGUMENT;
  /* From here the staged value is consumed. */
  limit = rc_effective_limit(s->format, options ? options->max_input_bytes : 0);

  if (control->cancelled && control->cancelled(control->context)) {
    code = READER_CLOUD_CANCELLED;
    rc_fail(error, code, "cancelled before the SDK import");
  } else if (s->bytes > limit) {
    code = READER_CLOUD_LIMIT;
    rc_fail(error, code, "staged book exceeds the import limit");
  } else {
    hashed = rc_hash_file(s->path, control, &seen, hex);
    if (hashed == RC_HASH_CANCELLED) {
      code = READER_CLOUD_CANCELLED;
      rc_fail(error, code, "cancelled while verifying the staged file");
    } else if (hashed == RC_HASH_MEMORY) {
      code = READER_CLOUD_MEMORY;
      rc_fail(error, code, "out of memory");
    } else if (hashed == RC_HASH_IO) {
      code = READER_CLOUD_IO;
      rc_fail(error, code, "staged file is missing or unreadable");
    } else if (seen != s->bytes || strcmp(hex, s->sha256) != 0) {
      code = READER_CLOUD_CORRUPT;
      rc_fail(error, code, "staged bytes changed after download");
    } else {
      memset(&sdk_options, 0, sizeof(sdk_options));
      memset(&sdk_result, 0, sizeof(sdk_result));
      memset(&sdk_error, 0, sizeof(sdk_error));
      sdk_options.struct_size = sizeof(sdk_options);
      sdk_result.struct_size = sizeof(sdk_result);
      sdk_options.max_input_bytes = limit;
      state.user = control;
      sdk_options.control.cancelled = rc_sdk_cancelled;
      sdk_options.control.context = &state;
      sdk_status = exr_sideload_import_file(library, s->format, s->path, title,
          &sdk_options, &sdk_result, &sdk_error);
      if (sdk_status == EXR_OK) {
        /* Commit boundary: a later cancellation request cannot undo this. */
        result->committed = 1;
        result->created = sdk_result.created ? 1 : 0;
        result->book_id = sdk_result.book_id;
        if (error) memset(error, 0, sizeof(*error));
      } else if (sdk_status == EXR_CANCELLED) {
        code = READER_CLOUD_CANCELLED;
        rc_fail(error, code, sdk_error.message[0] ? sdk_error.message : "cancelled by the SDK import");
        if (error) error->sdk_code = sdk_status;
      } else if (sdk_status == EXR_MEMORY) {
        code = READER_CLOUD_MEMORY;
        rc_fail(error, code, "out of memory");
        if (error) error->sdk_code = sdk_status;
      } else {
        code = READER_CLOUD_IMPORT;
        rc_fail(error, code, sdk_error.message[0] ? sdk_error.message : "the SDK rejected the book");
        if (error) error->sdk_code = sdk_status;
      }
    }
  }

  /* Only the staging copy is removed. The SDK row is untouched on every path. */
  rc_remove(s->path);
  result->staging_removed = 1;
  free(title);
  rc_staged_free(s);
  *staged = NULL;
  return code;
}
