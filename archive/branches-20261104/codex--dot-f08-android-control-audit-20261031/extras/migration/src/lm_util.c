/* SPDX-License-Identifier: MIT */
#ifndef _WIN32
#define _POSIX_C_SOURCE 200809L
#endif
#ifdef __APPLE__
#define _DARWIN_C_SOURCE
#endif
#include "lm.h"
#include <errno.h>
#include <math.h>
#include <stdarg.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
#include <psapi.h>
#include <io.h>
#include <fcntl.h>
#include <sys/stat.h>
#else
#include <sys/resource.h>
#include <sys/stat.h>
#include <unistd.h>
#endif

/* ---- string builder ---- */
void lm_sb_init(lm_sb *b) { memset(b, 0, sizeof(*b)); }
void lm_sb_free(lm_sb *b) { free(b->p); memset(b, 0, sizeof(*b)); }
void lm_sb_add(lm_sb *b, const char *s, size_t n) {
  if (b->oom || !n) return;
  if (b->n + n + 1 > b->cap) {
    size_t cap = b->cap ? b->cap : 256;
    char *p;
    while (cap < b->n + n + 1) {
      if (cap > SIZE_MAX / 2) { b->oom = 1; return; }
      cap *= 2;
    }
    p = realloc(b->p, cap);
    if (!p) { b->oom = 1; return; }
    b->p = p; b->cap = cap;
  }
  memcpy(b->p + b->n, s, n);
  b->n += n;
  b->p[b->n] = 0;
}
void lm_sb_str(lm_sb *b, const char *s) { lm_sb_add(b, s, strlen(s)); }
void lm_sb_fmt(lm_sb *b, const char *fmt, ...) {
  char stack[512], *heap = NULL;
  va_list ap, copy;
  int n;
  va_start(ap, fmt);
  va_copy(copy, ap);
  n = vsnprintf(stack, sizeof(stack), fmt, ap);
  va_end(ap);
  if (n < 0) { b->oom = 1; va_end(copy); return; }
  if ((size_t)n < sizeof(stack)) { lm_sb_add(b, stack, (size_t)n); va_end(copy); return; }
  heap = malloc((size_t)n + 1);
  if (!heap) { b->oom = 1; va_end(copy); return; }
  vsnprintf(heap, (size_t)n + 1, fmt, copy);
  va_end(copy);
  lm_sb_add(b, heap, (size_t)n);
  free(heap);
}
void lm_sb_json(lm_sb *b, const char *s, size_t n) {
  size_t i;
  lm_sb_add(b, "\"", 1);
  for (i = 0; i < n; i++) {
    unsigned char c = (unsigned char)s[i];
    if (c == '"') lm_sb_add(b, "\\\"", 2);
    else if (c == '\\') lm_sb_add(b, "\\\\", 2);
    else if (c == '\n') lm_sb_add(b, "\\n", 2);
    else if (c == '\r') lm_sb_add(b, "\\r", 2);
    else if (c == '\t') lm_sb_add(b, "\\t", 2);
    else if (c < 0x20 || c == 0x7f) lm_sb_fmt(b, "\\u%04x", c);
    else lm_sb_add(b, s + i, 1);
  }
  lm_sb_add(b, "\"", 1);
}

void lm_err_set(lm_err *e, const char *code, const char *fmt, ...) {
  va_list ap;
  if (!e) return;
  snprintf(e->code, sizeof(e->code), "%s", code);
  va_start(ap, fmt);
  vsnprintf(e->message, sizeof(e->message), fmt, ap);
  va_end(ap);
}

/* ---- SHA-256 (FIPS 180-4) ---- */
static const uint32_t K256[64] = {
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
  0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
  0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
  0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
  0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
  0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2};
#define ROR(x, n) (((x) >> (n)) | ((x) << (32 - (n))))
static void sha_block(lm_sha *s, const unsigned char *p) {
  uint32_t w[64], a, b, c, d, e, f, g, h, t1, t2;
  int i;
  for (i = 0; i < 16; i++)
    w[i] = (uint32_t)p[i * 4] << 24 | (uint32_t)p[i * 4 + 1] << 16 | (uint32_t)p[i * 4 + 2] << 8 | (uint32_t)p[i * 4 + 3];
  for (; i < 64; i++) {
    uint32_t s0 = ROR(w[i - 15], 7) ^ ROR(w[i - 15], 18) ^ (w[i - 15] >> 3);
    uint32_t s1 = ROR(w[i - 2], 17) ^ ROR(w[i - 2], 19) ^ (w[i - 2] >> 10);
    w[i] = w[i - 16] + s0 + w[i - 7] + s1;
  }
  a = s->h[0]; b = s->h[1]; c = s->h[2]; d = s->h[3]; e = s->h[4]; f = s->h[5]; g = s->h[6]; h = s->h[7];
  for (i = 0; i < 64; i++) {
    t1 = h + (ROR(e, 6) ^ ROR(e, 11) ^ ROR(e, 25)) + ((e & f) ^ (~e & g)) + K256[i] + w[i];
    t2 = (ROR(a, 2) ^ ROR(a, 13) ^ ROR(a, 22)) + ((a & b) ^ (a & c) ^ (b & c));
    h = g; g = f; f = e; e = d + t1; d = c; c = b; b = a; a = t1 + t2;
  }
  s->h[0] += a; s->h[1] += b; s->h[2] += c; s->h[3] += d; s->h[4] += e; s->h[5] += f; s->h[6] += g; s->h[7] += h;
}
void lm_sha_init(lm_sha *s) {
  static const uint32_t init[8] = {0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19};
  memcpy(s->h, init, sizeof(init));
  s->len = 0; s->fill = 0;
}
void lm_sha_add(lm_sha *s, const void *data, size_t n) {
  const unsigned char *p = data;
  s->len += n;
  while (n) {
    size_t take = 64 - s->fill;
    if (take > n) take = n;
    memcpy(s->buf + s->fill, p, take);
    s->fill += take; p += take; n -= take;
    if (s->fill == 64) { sha_block(s, s->buf); s->fill = 0; }
  }
}
void lm_sha_hex(lm_sha *s, char out[65]) {
  static const char digits[] = "0123456789abcdef";
  uint64_t bits = s->len * 8;
  unsigned char pad = 0x80, zero = 0, length[8];
  int i;
  lm_sha_add(s, &pad, 1);
  while (s->fill != 56) lm_sha_add(s, &zero, 1);
  for (i = 0; i < 8; i++) length[i] = (unsigned char)(bits >> (56 - i * 8));
  lm_sha_add(s, length, 8);
  for (i = 0; i < 32; i++) {
    unsigned char byte = (unsigned char)(s->h[i / 4] >> (24 - (i % 4) * 8));
    out[i * 2] = digits[byte >> 4];
    out[i * 2 + 1] = digits[byte & 15];
  }
  out[64] = 0;
}
void lm_sha_bytes(const void *data, size_t n, char out[65]) {
  lm_sha s;
  lm_sha_init(&s);
  lm_sha_add(&s, data, n);
  lm_sha_hex(&s, out);
}

/* ---- text ---- */
int lm_utf8_valid(const char *s, size_t n) {
  size_t i = 0;
  while (i < n) {
    unsigned char c = (unsigned char)s[i];
    size_t len;
    uint32_t cp;
    if (c < 0x80) { i++; continue; }
    if (c >= 0xc2 && c <= 0xdf) { len = 2; cp = c & 0x1f; }
    else if (c >= 0xe0 && c <= 0xef) { len = 3; cp = c & 0x0f; }
    else if (c >= 0xf0 && c <= 0xf4) { len = 4; cp = c & 0x07; }
    else return 0;
    if (i + len > n) return 0;
    for (size_t k = 1; k < len; k++) {
      unsigned char t = (unsigned char)s[i + k];
      if ((t & 0xc0) != 0x80) return 0;
      cp = (cp << 6) | (t & 0x3f);
    }
    if ((len == 3 && (cp < 0x800 || (cp >= 0xd800 && cp <= 0xdfff))) || (len == 4 && (cp < 0x10000 || cp > 0x10ffff))) return 0;
    i += len;
  }
  return 1;
}
static int b64_value(unsigned char c) {
  if (c >= 'A' && c <= 'Z') return c - 'A';
  if (c >= 'a' && c <= 'z') return c - 'a' + 26;
  if (c >= '0' && c <= '9') return c - '0' + 52;
  if (c == '+') return 62;
  if (c == '/') return 63;
  return -1;
}
int lm_b64_decode(const char *s, size_t n, unsigned char **out, size_t *outn, size_t max) {
  unsigned char *p;
  size_t i, at = 0;
  uint32_t acc = 0;
  int bits = 0;
  *out = NULL; *outn = 0;
  while (n && s[n - 1] == '=') n--;
  if (n / 4 * 3 + 3 > max + 3) return 0;
  p = malloc(n / 4 * 3 + 4);
  if (!p) return 0;
  for (i = 0; i < n; i++) {
    int v = b64_value((unsigned char)s[i]);
    if (v < 0) { free(p); return 0; }
    acc = (acc << 6) | (uint32_t)v;
    bits += 6;
    if (bits >= 8) { bits -= 8; p[at++] = (unsigned char)(acc >> bits); acc &= (1u << bits) - 1u; }
  }
  if (at > max) { free(p); return 0; }
  *out = p; *outn = at;
  return 1;
}

/* ---- platform files ---- */
#ifdef _WIN32
static wchar_t *widen(const char *s) {
  int n = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, s, -1, NULL, 0);
  wchar_t *w;
  if (n <= 0) return NULL;
  w = malloc((size_t)n * sizeof(*w));
  if (w && !MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, s, -1, w, n)) { free(w); return NULL; }
  return w;
}
#endif
FILE *lm_fopen(const char *path, const char *mode) {
#ifdef _WIN32
  wchar_t *w = widen(path), wm[8];
  FILE *f;
  size_t i;
  if (!w) return NULL;
  for (i = 0; mode[i] && i < 7; i++) wm[i] = (wchar_t)(unsigned char)mode[i];
  wm[i] = 0;
  f = _wfopen(w, wm);
  free(w);
  return f;
#else
  return fopen(path, mode);
#endif
}
int lm_exists(const char *path) {
#ifdef _WIN32
  struct _stat64 st;
  wchar_t *w = widen(path);
  int ok;
  if (!w) return 0;
  ok = _wstat64(w, &st) == 0;
  free(w);
  return ok;
#else
  struct stat st;
  return stat(path, &st) == 0;
#endif
}
int lm_path_state(const char *path) {
#ifdef _WIN32
  wchar_t *w = widen(path);DWORD attr, error;
  if (!w) return -1;
  attr = GetFileAttributesW(w);
  error = attr == INVALID_FILE_ATTRIBUTES ? GetLastError() : ERROR_SUCCESS;
  free(w);
  if (attr != INVALID_FILE_ATTRIBUTES) return 1;
  return error == ERROR_FILE_NOT_FOUND ? 0 : -1;
#else
  struct stat st;
  if (lstat(path, &st) == 0) return 1;
  return errno == ENOENT ? 0 : -1;
#endif
}
int lm_remove(const char *path) {
#ifdef _WIN32
  wchar_t *w = widen(path);
  int ok;
  if (!w) return 0;
  ok = _wremove(w) == 0;
  free(w);
  return ok;
#else
  return remove(path) == 0;
#endif
}
int lm_replace(const char *from, const char *to) {
#ifdef _WIN32
  wchar_t *a = widen(from), *b = widen(to);
  int ok = a && b && MoveFileExW(a, b, MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH);
  free(a); free(b);
  return ok;
#else
  return rename(from, to) == 0;
#endif
}
int lm_publish_new(const char *from, const char *to) {
#ifdef _WIN32
  wchar_t *a = widen(from), *b = widen(to);
  int ok = a && b && MoveFileExW(a, b, MOVEFILE_WRITE_THROUGH);
  free(a); free(b);
  return ok;
#else
  /* Same-directory publication must never replace a destination created meanwhile. */
  if (link(from, to)) return 0;
  (void)unlink(from); /* cleanup() also removes any remaining stage link. */
  return 1;
#endif
}
int lm_seek(FILE *f, uint64_t offset) {
#ifdef _WIN32
  return _fseeki64(f, (long long)offset, SEEK_SET) == 0;
#else
  return fseeko(f, (off_t)offset, SEEK_SET) == 0;
#endif
}
int lm_file_size(FILE *f, uint64_t *size) {
#ifdef _WIN32
  __int64 n;
  if (_fseeki64(f, 0, SEEK_END)) return 0;
  n = _ftelli64(f);
#else
  off_t n;
  if (fseeko(f, 0, SEEK_END)) return 0;
  n = ftello(f);
#endif
  if (n < 0) return 0;
  *size = (uint64_t)n;
  return lm_seek(f, 0);
}
int lm_sync(FILE *f) {
  if (fflush(f)) return 0;
#ifdef _WIN32
  return _commit(_fileno(f)) == 0;
#else
  return fsync(fileno(f)) == 0;
#endif
}
int lm_copy(const char *from, const char *to) {
  FILE *in = lm_fopen(from, "rb"), *out;
  unsigned char *buffer;
  size_t n;
  int ok = 1;
  if (!in) return 0;
  out = lm_fopen(to, "wb");
  buffer = malloc(65536);
  if (!out || !buffer) { if (in) fclose(in); if (out) fclose(out); free(buffer); return 0; }
  while ((n = fread(buffer, 1, 65536, in)) > 0)
    if (fwrite(buffer, 1, n, out) != n) { ok = 0; break; }
  if (ferror(in)) ok = 0;
  if (ok && !lm_sync(out)) ok = 0;
  fclose(in);
  if (fclose(out)) ok = 0;
  free(buffer);
  if (!ok) lm_remove(to);
  return ok;
}
int lm_sha_file(const char *path, char out[65], uint64_t *size) {
  FILE *f = lm_fopen(path, "rb");
  unsigned char *buffer;
  size_t n;
  lm_sha sha;
  uint64_t total = 0;
  if (!f) return 0;
  buffer = malloc(65536);
  if (!buffer) { fclose(f); return 0; }
  lm_sha_init(&sha);
  while ((n = fread(buffer, 1, 65536, f)) > 0) { lm_sha_add(&sha, buffer, n); total += n; }
  free(buffer);
  if (ferror(f)) { fclose(f); return 0; }
  fclose(f);
  lm_sha_hex(&sha, out);
  if (size) *size = total;
  return 1;
}
uint64_t lm_peak_rss(void) {
#ifdef _WIN32
  PROCESS_MEMORY_COUNTERS memory;
  if (!GetProcessMemoryInfo(GetCurrentProcess(), &memory, sizeof(memory))) return 0;
  return (uint64_t)memory.PeakWorkingSetSize;
#else
  struct rusage usage;
  uint64_t bytes;
  if (getrusage(RUSAGE_SELF, &usage)) return 0;
  bytes = (uint64_t)usage.ru_maxrss;
#ifndef __APPLE__
  bytes *= 1024;
#endif
  return bytes;
#endif
}
void lm_binary_stdout(void) {
#ifdef _WIN32
  _setmode(_fileno(stdout), _O_BINARY);
#endif
}

/* ---- JSON ---- */
typedef struct { const char *s; size_t n, i; int depth; char *err; size_t errcap; } jp;
static void jfail(jp *p, const char *message) {
  if (p->err && !p->err[0]) snprintf(p->err, p->errcap, "%s at byte %zu", message, p->i);
}
static jv *jnew(jtype t) {
  jv *v = calloc(1, sizeof(*v));
  if (v) v->t = t;
  return v;
}
void lm_json_free(jv *v) {
  size_t i;
  if (!v) return;
  free(v->s);
  for (i = 0; i < v->n && (v->t == J_ARR || v->t == J_OBJ); i++) {
    lm_json_free(v->items[i]);
    if (v->keys) free(v->keys[i]);
  }
  free(v->items);
  free(v->keys);
  free(v);
}
static void jws(jp *p) {
  while (p->i < p->n && (p->s[p->i] == ' ' || p->s[p->i] == '\t' || p->s[p->i] == '\n' || p->s[p->i] == '\r')) p->i++;
}
static int hex4(const char *s, uint32_t *out) {
  uint32_t v = 0;
  int i;
  for (i = 0; i < 4; i++) {
    char c = s[i];
    v <<= 4;
    if (c >= '0' && c <= '9') v |= (uint32_t)(c - '0');
    else if (c >= 'a' && c <= 'f') v |= (uint32_t)(c - 'a' + 10);
    else if (c >= 'A' && c <= 'F') v |= (uint32_t)(c - 'A' + 10);
    else return 0;
  }
  *out = v;
  return 1;
}
static size_t put_utf8(char *d, uint32_t cp) {
  if (cp < 0x80) { d[0] = (char)cp; return 1; }
  if (cp < 0x800) { d[0] = (char)(0xc0 | (cp >> 6)); d[1] = (char)(0x80 | (cp & 0x3f)); return 2; }
  if (cp < 0x10000) { d[0] = (char)(0xe0 | (cp >> 12)); d[1] = (char)(0x80 | ((cp >> 6) & 0x3f)); d[2] = (char)(0x80 | (cp & 0x3f)); return 3; }
  d[0] = (char)(0xf0 | (cp >> 18)); d[1] = (char)(0x80 | ((cp >> 12) & 0x3f)); d[2] = (char)(0x80 | ((cp >> 6) & 0x3f)); d[3] = (char)(0x80 | (cp & 0x3f));
  return 4;
}
static char *jstring(jp *p, size_t *length) {
  char *out = malloc(p->n - p->i + 1);
  size_t at = 0;
  if (!out) { jfail(p, "out of memory"); return NULL; }
  p->i++; /* opening quote */
  for (;;) {
    unsigned char c;
    if (p->i >= p->n) { jfail(p, "unterminated string"); free(out); return NULL; }
    c = (unsigned char)p->s[p->i++];
    if (c == '"') break;
    if (c < 0x20) { jfail(p, "control character in string"); free(out); return NULL; }
    if (c != '\\') { out[at++] = (char)c; continue; }
    if (p->i >= p->n) { jfail(p, "bad escape"); free(out); return NULL; }
    c = (unsigned char)p->s[p->i++];
    switch (c) {
      case '"': out[at++] = '"'; break;
      case '\\': out[at++] = '\\'; break;
      case '/': out[at++] = '/'; break;
      case 'b': out[at++] = '\b'; break;
      case 'f': out[at++] = '\f'; break;
      case 'n': out[at++] = '\n'; break;
      case 'r': out[at++] = '\r'; break;
      case 't': out[at++] = '\t'; break;
      case 'u': {
        uint32_t cp, low;
        if (p->i + 4 > p->n || !hex4(p->s + p->i, &cp)) { jfail(p, "bad unicode escape"); free(out); return NULL; }
        p->i += 4;
        if (cp >= 0xdc00 && cp <= 0xdfff) { jfail(p, "lone low surrogate"); free(out); return NULL; }
        if (cp >= 0xd800 && cp <= 0xdbff) {
          if (p->i + 6 > p->n || p->s[p->i] != '\\' || p->s[p->i + 1] != 'u' || !hex4(p->s + p->i + 2, &low) || low < 0xdc00 || low > 0xdfff) {
            jfail(p, "lone high surrogate"); free(out); return NULL;
          }
          p->i += 6;
          cp = 0x10000 + ((cp - 0xd800) << 10) + (low - 0xdc00);
        }
        at += put_utf8(out + at, cp);
        break;
      }
      default: jfail(p, "bad escape"); free(out); return NULL;
    }
  }
  out[at] = 0;
  if (!lm_utf8_valid(out, at)) { jfail(p, "invalid UTF-8 in string"); free(out); return NULL; }
  *length = at;
  return out;
}
static jv *jvalue(jp *p);
static int jpush(jv *v, jv *item, char *key) {
  if (v->n == v->cap) {
    size_t cap = v->cap ? v->cap * 2 : 8;
    jv **items = realloc(v->items, cap * sizeof(*items));
    char **keys = v->t == J_OBJ ? realloc(v->keys, cap * sizeof(*keys)) : NULL;
    if (items) v->items = items;
    if (keys) v->keys = keys;
    if (!items || (v->t == J_OBJ && !keys)) return 0;
    v->cap = cap;
  }
  v->items[v->n] = item;
  if (v->t == J_OBJ) v->keys[v->n] = key;
  v->n++;
  return 1;
}
static jv *jcontainer(jp *p, jtype t) {
  jv *v = jnew(t);
  char close = t == J_ARR ? ']' : '}';
  if (!v) { jfail(p, "out of memory"); return NULL; }
  if (++p->depth > 100) { jfail(p, "nesting too deep"); lm_json_free(v); return NULL; }
  p->i++;
  jws(p);
  if (p->i < p->n && p->s[p->i] == close) { p->i++; p->depth--; return v; }
  for (;;) {
    char *key = NULL;
    jv *item;
    jws(p);
    if (t == J_OBJ) {
      size_t klen;
      if (p->i >= p->n || p->s[p->i] != '"') { jfail(p, "object key expected"); lm_json_free(v); return NULL; }
      key = jstring(p, &klen);
      if (!key) { lm_json_free(v); return NULL; }
      jws(p);
      if (p->i >= p->n || p->s[p->i] != ':') { jfail(p, "colon expected"); free(key); lm_json_free(v); return NULL; }
      p->i++;
    }
    item = jvalue(p);
    if (!item) { free(key); lm_json_free(v); return NULL; }
    if (!jpush(v, item, key)) { jfail(p, "out of memory"); lm_json_free(item); free(key); lm_json_free(v); return NULL; }
    jws(p);
    if (p->i < p->n && p->s[p->i] == ',') { p->i++; continue; }
    if (p->i < p->n && p->s[p->i] == close) { p->i++; p->depth--; return v; }
    jfail(p, "comma or closing bracket expected");
    lm_json_free(v);
    return NULL;
  }
}
static jv *jvalue(jp *p) {
  jv *v;
  jws(p);
  if (p->i >= p->n) { jfail(p, "unexpected end"); return NULL; }
  switch (p->s[p->i]) {
    case '{': return jcontainer(p, J_OBJ);
    case '[': return jcontainer(p, J_ARR);
    case '"': {
      size_t len;
      char *s = jstring(p, &len);
      if (!s) return NULL;
      v = jnew(J_STR);
      if (!v) { free(s); jfail(p, "out of memory"); return NULL; }
      v->s = s; v->n = len;
      return v;
    }
    case 't': case 'f': case 'n': {
      const char *word = p->s[p->i] == 't' ? "true" : p->s[p->i] == 'f' ? "false" : "null";
      size_t len = strlen(word);
      if (p->i + len > p->n || memcmp(p->s + p->i, word, len)) { jfail(p, "invalid literal"); return NULL; }
      p->i += len;
      v = jnew(word[0] == 'n' ? J_NULL : J_BOOL);
      if (!v) { jfail(p, "out of memory"); return NULL; }
      v->b = word[0] == 't';
      return v;
    }
    default: {
      char token[64], *end;
      size_t k = 0;
      double d;
      while (p->i + k < p->n && k < sizeof(token) - 1) {
        char c = p->s[p->i + k];
        if (!((c >= '0' && c <= '9') || c == '-' || c == '+' || c == '.' || c == 'e' || c == 'E')) break;
        token[k++] = c;
      }
      token[k] = 0;
      if (!k || (token[0] != '-' && (token[0] < '0' || token[0] > '9'))) { jfail(p, "invalid value"); return NULL; }
      d = strtod(token, &end);
      if (*end || !isfinite(d)) { jfail(p, "invalid number"); return NULL; }
      p->i += k;
      v = jnew(J_NUM);
      if (!v) { jfail(p, "out of memory"); return NULL; }
      v->num = d;
      return v;
    }
  }
}
jv *lm_json_parse(const char *s, size_t n, char *err, size_t errcap) {
  jp p = {s, n, 0, 0, err, errcap};
  jv *v;
  if (err && errcap) err[0] = 0;
  v = jvalue(&p);
  if (!v) return NULL;
  jws(&p);
  if (p.i != n) { jfail(&p, "trailing data"); lm_json_free(v); return NULL; }
  return v;
}
const jv *lm_get(const jv *o, const char *key) {
  size_t i;
  if (!o || o->t != J_OBJ) return NULL;
  for (i = 0; i < o->n; i++)
    if (!strcmp(o->keys[i], key)) return o->items[i];
  return NULL;
}
const char *lm_get_str(const jv *o, const char *key) {
  const jv *v = lm_get(o, key);
  return v && v->t == J_STR ? v->s : NULL;
}
int lm_json_uint(const jv *v, uint64_t *out) {
  if (!v || v->t != J_NUM || v->num < 0 || v->num > 9007199254740992.0 || v->num != floor(v->num)) return 0;
  *out = (uint64_t)v->num;
  return 1;
}
void lm_json_write(lm_sb *b, const jv *v) {
  size_t i;
  switch (v->t) {
    case J_NULL: lm_sb_str(b, "null"); break;
    case J_BOOL: lm_sb_str(b, v->b ? "true" : "false"); break;
    case J_NUM:
      if (v->num == floor(v->num) && fabs(v->num) < 9007199254740992.0) lm_sb_fmt(b, "%.0f", v->num);
      else lm_sb_fmt(b, "%.17g", v->num);
      break;
    case J_STR: lm_sb_json(b, v->s, v->n); break;
    case J_ARR:
      lm_sb_str(b, "[");
      for (i = 0; i < v->n; i++) { if (i) lm_sb_str(b, ","); lm_json_write(b, v->items[i]); }
      lm_sb_str(b, "]");
      break;
    case J_OBJ:
      lm_sb_str(b, "{");
      for (i = 0; i < v->n; i++) {
        if (i) lm_sb_str(b, ",");
        lm_sb_json(b, v->keys[i], strlen(v->keys[i]));
        lm_sb_str(b, ":");
        lm_json_write(b, v->items[i]);
      }
      lm_sb_str(b, "}");
      break;
  }
}
