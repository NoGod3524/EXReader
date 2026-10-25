/* SPDX-License-Identifier: MIT */
/* C05 FB2 find probe. Links only the installed SDK (EXReader::exreader).
   One process, one document: import, public full-text projection, exact find over
   every supplied query, cancel/retry, anchor capture/resolve and reopen.
   Queries arrive as ASCII hex so the process command line cannot change their
   bytes; the raw argv and Windows wide command-line forms are probed separately
   to attribute the original F5 miss. stdout is one JSON line. */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#ifdef _WIN32
#include <windows.h>
#include <shellapi.h>
#include <direct.h>
#define make_dir(p) _mkdir(p)
#else
#include <sys/stat.h>
#define make_dir(p) mkdir((p), 0777)
#endif

#ifndef C05_SOURCE_UTF8
#define C05_SOURCE_UTF8 1
#endif

enum { MAX_QUERY = 64, MAX_OCC = 100000, REPORT_POS = 16, EXCERPT = 24, HEX_CAP = 128 };

typedef struct { char label[48]; unsigned char *bytes; size_t size; char source[16]; } query_t;
typedef struct { int polls, limit; } cancel_t;
typedef struct { exr_anchor anchor; size_t start, end; int have; } kept_t;

static const char *const status_names[] = {"OK", "ARGUMENT", "MEMORY", "IO", "ENCODING", "FORMAT", "LIMIT",
                                           "DATABASE", "FONT", "CANCELLED", "PASSWORD", "UNSUPPORTED"};
static const char *status_name(exr_status s) {
  return (unsigned)s < sizeof(status_names) / sizeof(*status_names) ? status_names[s] : "UNKNOWN";
}
static const char *state_name(exr_anchor_state s) {
  return s == EXR_ANCHOR_FOUND ? "FOUND" : s == EXR_ANCHOR_AMBIGUOUS ? "AMBIGUOUS" :
         s == EXR_ANCHOR_LEGACY ? "LEGACY" : "MISSING";
}

static int cancel_poll(void *context) {
  cancel_t *c = (cancel_t *)context;
  return ++c->polls >= c->limit;
}

static uint64_t fnv1a(const unsigned char *p, size_t n) {
  uint64_t h = 1469598103934665603ULL;
  for (size_t i = 0; i < n; i++) { h ^= p[i]; h *= 1099511628211ULL; }
  return h;
}

static void json_string(const char *s) {
  putchar('"');
  for (const unsigned char *p = (const unsigned char *)(s ? s : ""); *p; p++) {
    if (*p == '"' || *p == '\\') { putchar('\\'); putchar(*p); }
    else if (*p < 0x20 || *p >= 0x7f) printf("\\u%04x", *p);
    else putchar(*p);
  }
  putchar('"');
}
static void json_hex(const unsigned char *p, size_t n) {
  putchar('"');
  for (size_t i = 0; i < n; i++) printf("%02x", p[i]);
  putchar('"');
}
static void json_pos(size_t v) { if (v == SIZE_MAX) fputs("null", stdout); else printf("%zu", v); }

static int hex_value(int c) {
  return c >= '0' && c <= '9' ? c - '0' : c >= 'a' && c <= 'f' ? c - 'a' + 10 : c >= 'A' && c <= 'F' ? c - 'A' + 10 : -1;
}
static int decode_hex(const char *hex, unsigned char **out, size_t *size) {
  size_t n = strlen(hex);
  unsigned char *b;
  if (!n || (n & 1)) return 0;
  b = (unsigned char *)malloc(n / 2 + 1);
  if (!b) return 0;
  for (size_t i = 0; i < n; i += 2) {
    int hi = hex_value(hex[i]), lo = hex_value(hex[i + 1]);
    if (hi < 0 || lo < 0) { free(b); return 0; }
    b[i / 2] = (unsigned char)(hi * 16 + lo);
  }
  b[n / 2] = 0; *out = b; *size = n / 2;
  return 1;
}

static int read_file_bytes(const char *path, unsigned char **data, size_t *size) {
  FILE *f = fopen(path, "rb");
  long n;
  if (!f) return 0;
  if (fseek(f, 0, SEEK_END) != 0 || (n = ftell(f)) < 0 || fseek(f, 0, SEEK_SET) != 0) { fclose(f); return 0; }
  *data = (unsigned char *)malloc((size_t)n + 1);
  if (!*data || fread(*data, 1, (size_t)n, f) != (size_t)n) { free(*data); *data = NULL; fclose(f); return 0; }
  fclose(f); (*data)[n] = 0; *size = (size_t)n;
  return 1;
}
static int write_file_bytes(const char *path, const void *data, size_t size) {
  FILE *f = fopen(path, "wb");
  int ok;
  if (!f) return 0;
  ok = size == 0 || fwrite(data, 1, size, f) == size;
  return fclose(f) == 0 && ok;
}

/* Strict UTF-8 scan; reports the projection features the independent scanner re-derives. */
typedef struct { int valid; size_t scalars, nonbmp, cr, lf, nul, combining; } text_stats;
static void scan_text(const unsigned char *t, size_t n, text_stats *s) {
  size_t i = 0;
  memset(s, 0, sizeof(*s)); s->valid = 1;
  while (i < n) {
    unsigned char c = t[i];
    uint32_t cp; size_t len;
    if (c < 0x80) { cp = c; len = 1; }
    else if (c >= 0xc2 && c <= 0xdf) { len = 2; cp = c & 0x1f; }
    else if (c >= 0xe0 && c <= 0xef) { len = 3; cp = c & 0x0f; }
    else if (c >= 0xf0 && c <= 0xf4) { len = 4; cp = c & 0x07; }
    else { s->valid = 0; return; }
    if (i + len > n) { s->valid = 0; return; }
    for (size_t k = 1; k < len; k++) {
      if ((t[i + k] & 0xc0) != 0x80) { s->valid = 0; return; }
      cp = (cp << 6) | (t[i + k] & 0x3f);
    }
    if ((len == 3 && (cp < 0x800 || (cp >= 0xd800 && cp <= 0xdfff))) || (len == 4 && (cp < 0x10000 || cp > 0x10ffff))) {
      s->valid = 0; return;
    }
    s->scalars++;
    if (cp > 0xffff) s->nonbmp++;
    if (cp == '\r') s->cr++;
    if (cp == '\n') s->lf++;
    if (cp == 0) s->nul++;
    if (cp >= 0x300 && cp <= 0x36f) s->combining++;
    i += len;
  }
}

/* Source literals: the bytes this compiler produced from UTF-8 source text. */
static const unsigned char kBreterUtf8[] = {0xd0, 0x91, 0xd1, 0x80, 0xd0, 0xb5, 0xd1, 0x82, 0xd1, 0x91, 0xd1, 0x80};
static const char kBreterLiteral[] = "\xd0\x91\xd1\x80\xd0\xb5\xd1\x82\xd1\x91\xd1\x80";
static const char kBreterSource[] = "Бретёр";
static const char kBreterU8Source[] = u8"Бретёр";

static void print_program(void) {
  printf("\"program\":{\"sdk_version\":"); json_string(exr_version());
  printf(",\"abi\":%u,\"source_utf8_flag\":%d,\"source_literal_hex\":", (unsigned)exr_abi_version(), C05_SOURCE_UTF8);
  json_hex((const unsigned char *)kBreterSource, strlen(kBreterSource));
  printf(",\"source_literal_utf8\":%s", strlen(kBreterSource) == sizeof(kBreterUtf8) &&
         !memcmp(kBreterSource, kBreterUtf8, sizeof(kBreterUtf8)) ? "true" : "false");
  printf(",\"u8_literal_hex\":"); json_hex((const unsigned char *)kBreterU8Source, strlen(kBreterU8Source));
  printf(",\"escape_literal_ok\":%s", strlen(kBreterLiteral) == sizeof(kBreterUtf8) &&
         !memcmp(kBreterLiteral, kBreterUtf8, sizeof(kBreterUtf8)) ? "true" : "false");
#if defined(_MSC_VER)
  printf(",\"compiler\":\"msvc\",\"compiler_version\":%d", (int)_MSC_VER);
#elif defined(__clang__)
  printf(",\"compiler\":\"clang\",\"compiler_version\":%d", (int)__clang_major__);
#elif defined(__GNUC__)
  printf(",\"compiler\":\"gcc\",\"compiler_version\":%d", (int)__GNUC__);
#else
  printf(",\"compiler\":\"unknown\",\"compiler_version\":0");
#endif
  printf(",\"wchar_size\":%zu", sizeof(wchar_t));
#ifdef _WIN32
  printf(",\"acp\":%u,\"oemcp\":%u,\"console_output_cp\":%u", (unsigned)GetACP(), (unsigned)GetOEMCP(),
         (unsigned)GetConsoleOutputCP());
#endif
  printf("}");
}

#ifdef _WIN32
/* The same command line, but through the wide API: UTF-16 to UTF-8 without the ANSI code page. */
static int wide_option(const char *flag, unsigned char **out, size_t *size) {
  int argc = 0, found = -1;
  wchar_t **argv = CommandLineToArgvW(GetCommandLineW(), &argc);
  wchar_t wflag[64];
  int ok = 0;
  if (!argv || MultiByteToWideChar(CP_UTF8, 0, flag, -1, wflag, 64) <= 0) return 0;
  for (int i = 1; i + 1 < argc; i++) if (!wcscmp(argv[i], wflag)) { found = i + 1; break; }
  if (found >= 0) {
    int n = WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, argv[found], -1, NULL, 0, NULL, NULL);
    if (n > 1) {
      *out = (unsigned char *)malloc((size_t)n);
      if (*out && WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, argv[found], -1, (char *)*out, n, NULL, NULL) == n) {
        *size = (size_t)n - 1; ok = 1;
      }
    }
  }
  LocalFree(argv);
  return ok;
}
#endif

typedef struct { size_t count, pos[REPORT_POS], first, last; int truncated; } scan_t;

/* Overlapping scan through the public document find; also the fixed-text find when ft is set. */
static exr_status scan_all(const exr_document *doc, const exr_fixed_text *ft, const query_t *q, scan_t *s, exr_error *error) {
  size_t from = 0, start, end;
  exr_status status = EXR_OK;
  memset(s, 0, sizeof(*s)); s->first = s->last = SIZE_MAX;
  for (;;) {
    start = end = SIZE_MAX;
    status = ft ? exr_fixed_text_find(ft, (const char *)q->bytes, q->size, from, NULL, &start, &end, error)
                : exr_document_find(doc, (const char *)q->bytes, from, &start, &end, error);
    if (status != EXR_OK || start == SIZE_MAX) break;
    if (s->count < REPORT_POS) s->pos[s->count] = start;
    if (!s->count) s->first = start;
    s->last = start; s->count++;
    if (s->count >= MAX_OCC) { s->truncated = 1; break; }
    from = start + 1;
  }
  return status;
}

static void print_scan(const scan_t *s, exr_status status) {
  printf("{\"status\":\"%s\",\"count\":%zu,\"truncated\":%s,\"first\":", status_name(status), s->count, s->truncated ? "true" : "false");
  json_pos(s->first); printf(",\"last\":"); json_pos(s->last); printf(",\"positions\":[");
  for (size_t i = 0; i < s->count && i < REPORT_POS; i++) printf("%s%zu", i ? "," : "", s->pos[i]);
  printf("]}");
}

static void print_excerpt(const unsigned char *t, size_t n, size_t start, size_t qlen) {
  size_t lo = start > 8 ? start - 8 : 0, hi = start + qlen + 8 < n ? start + qlen + 8 : n;
  if (hi - lo > EXCERPT + qlen) hi = lo + EXCERPT + qlen;
  printf("{\"offset\":%zu,\"bytes\":", lo); json_hex(t + lo, hi - lo); printf("}");
}

static int same_pair(size_t a, size_t b, size_t c, size_t d) { return a == c && b == d; }

int main(int argc, char **argv) {
  const char *file = NULL, *outdir = NULL, *queries_file = NULL, *argv_query = NULL, *wide_query = NULL;
  char path[4096];
  query_t queries[MAX_QUERY];
  kept_t kept[MAX_QUERY][2];
  size_t nq = 0, text_size = 0, memory_size = 0, blob_size = 0, text_size2 = 0, text_size3 = 0;
  unsigned char *file_bytes = NULL, *query_listing = NULL, *text_copy = NULL;
  void *blob = NULL;
  const char *text;
  exr_library *library = NULL;
  exr_document *doc = NULL, *memdoc = NULL, *redoc = NULL;
  exr_fixed_text *ft = NULL;
  exr_error error = {0};
  exr_status status;
  int64_t book_id = 0;
  size_t file_size = 0, query_listing_size = 0;
  int import_ok = 0, readback_ok = 0, open_ok = 0;
  text_stats stats;
  uint64_t fnv_a = 0, fnv_b = 0, fnv_c = 0;
  static const int cancel_limits[] = {1, 2, 3, 5, 8};

  memset(kept, 0, sizeof(kept));
  for (int i = 1; i < argc; i++) {
    if (i + 1 >= argc) { fprintf(stderr, "missing value for %s\n", argv[i]); return 2; }
    if (!strcmp(argv[i], "--file")) file = argv[++i];
    else if (!strcmp(argv[i], "--out")) outdir = argv[++i];
    else if (!strcmp(argv[i], "--queries")) queries_file = argv[++i];
    else if (!strcmp(argv[i], "--argv-query")) argv_query = argv[++i];
    else if (!strcmp(argv[i], "--wide-query")) wide_query = argv[++i];
    else { fprintf(stderr, "unknown argument %s\n", argv[i]); return 2; }
  }
  if (!file || !outdir) { fprintf(stderr, "usage: probe --file F --out DIR [--queries FILE] [--argv-query T] [--wide-query T]\n"); return 2; }
  make_dir(outdir);

  if (queries_file) {
    if (!read_file_bytes(queries_file, &query_listing, &query_listing_size)) { fprintf(stderr, "cannot read queries\n"); return 2; }
    for (char *line = strtok((char *)query_listing, "\r\n"); line; line = strtok(NULL, "\r\n")) {
      char *sep = strchr(line, ' ');
      if (!sep || nq >= MAX_QUERY) { fprintf(stderr, "bad query listing\n"); return 2; }
      *sep = 0;
      snprintf(queries[nq].label, sizeof(queries[nq].label), "%s", line);
      snprintf(queries[nq].source, sizeof(queries[nq].source), "hex");
      if (!decode_hex(sep + 1, &queries[nq].bytes, &queries[nq].size)) { fprintf(stderr, "bad hex for %s\n", line); return 2; }
      nq++;
    }
  }
  if (argv_query && nq < MAX_QUERY) {
    queries[nq].size = strlen(argv_query);
    queries[nq].bytes = (unsigned char *)malloc(queries[nq].size + 1);
    memcpy(queries[nq].bytes, argv_query, queries[nq].size + 1);
    snprintf(queries[nq].label, sizeof(queries[nq].label), "argv"); snprintf(queries[nq].source, sizeof(queries[nq].source), "argv"); nq++;
  }
  if (wide_query && nq < MAX_QUERY) {
    int ok = 0;
#ifdef _WIN32
    ok = wide_option("--wide-query", &queries[nq].bytes, &queries[nq].size);
    snprintf(queries[nq].source, sizeof(queries[nq].source), "wide");
#else
    queries[nq].size = strlen(wide_query);
    queries[nq].bytes = (unsigned char *)malloc(queries[nq].size + 1);
    memcpy(queries[nq].bytes, wide_query, queries[nq].size + 1); ok = 1;
    snprintf(queries[nq].source, sizeof(queries[nq].source), "posix-argv");
#endif
    if (!ok) { fprintf(stderr, "wide command line unavailable\n"); return 2; }
    snprintf(queries[nq].label, sizeof(queries[nq].label), "wide"); nq++;
  }
  if (!read_file_bytes(file, &file_bytes, &file_size)) { fprintf(stderr, "cannot read %s\n", file); return 3; }

  printf("{\"schema\":1,"); print_program();
  printf(",\"input\":{\"bytes\":%zu,\"fnv1a64\":\"%016llx\"}", file_size, (unsigned long long)fnv1a(file_bytes, file_size));

  /* 1. Public import, then original-byte readback through the library. */
  snprintf(path, sizeof(path), "%s/library.sqlite", outdir);
  status = exr_library_open(path, &library, &error);
  if (status == EXR_OK) {
    status = exr_library_import(library, EXR_FB2, file_bytes, file_size, NULL, &book_id, &error);
    import_ok = status == EXR_OK;
    if (import_ok && exr_library_blob(library, book_id, 0, &blob, &blob_size, &error) == EXR_OK) {
      snprintf(path, sizeof(path), "%s/readback.bin", outdir);
      readback_ok = write_file_bytes(path, blob, blob_size) && blob_size == file_size && !memcmp(blob, file_bytes, file_size);
    }
  }
  printf(",\"import\":{\"ok\":%s,\"readback_ok\":%s,\"status\":\"%s\",\"error\":", import_ok ? "true" : "false",
         readback_ok ? "true" : "false", status_name(status)); json_string(import_ok ? "" : error.message); printf("}");

  /* 2. Open from the file; project the whole document text. */
  status = exr_document_open(file, &doc, &error);
  open_ok = status == EXR_OK;
  printf(",\"open\":{\"ok\":%s,\"status\":\"%s\",\"error\":", open_ok ? "true" : "false", status_name(status));
  json_string(open_ok ? "" : error.message); printf("}");
  if (!open_ok) { printf("}\n"); return 0; }
  text = exr_document_text(doc, &text_size);
  fnv_a = fnv1a((const unsigned char *)text, text_size);
  text_copy = (unsigned char *)malloc(text_size + 1);
  memcpy(text_copy, text, text_size); text_copy[text_size] = 0;
  snprintf(path, sizeof(path), "%s/text.bin", outdir);
  write_file_bytes(path, text_copy, text_size);
  scan_text(text_copy, text_size, &stats);
  memory_size = exr_document_memory_size(doc);
  printf(",\"projection\":{\"bytes\":%zu,\"fnv1a64\":\"%016llx\",\"valid_utf8\":%s,\"scalars\":%zu,\"nonbmp\":%zu,"
         "\"cr\":%zu,\"lf\":%zu,\"nul\":%zu,\"combining\":%zu,\"memory_bytes\":%zu,\"title_hex\":",
         text_size, (unsigned long long)fnv_a, stats.valid ? "true" : "false", stats.scalars, stats.nonbmp, stats.cr,
         stats.lf, stats.nul, stats.combining, memory_size);
  { const char *title = exr_document_title(doc); json_hex((const unsigned char *)(title ? title : ""), title ? strlen(title) : 0); }
  printf("}");

  /* Second route: the library's returned blob opened from memory must project identically. */
  if (blob && exr_document_open_memory(EXR_FB2, blob, blob_size, &memdoc, &error) == EXR_OK) {
    const char *t2 = exr_document_text(memdoc, &text_size2);
    fnv_b = fnv1a((const unsigned char *)t2, text_size2);
  }
  printf(",\"memory_route\":{\"opened\":%s,\"bytes\":%zu,\"fnv1a64\":\"%016llx\",\"same\":%s}", memdoc ? "true" : "false",
         text_size2, (unsigned long long)fnv_b, memdoc && text_size2 == text_size && fnv_b == fnv_a ? "true" : "false");

  status = exr_fixed_text_create(text, text_size, NULL, 0, NULL, &ft, &error);
  printf(",\"fixed_text\":{\"status\":\"%s\"}", status_name(status));

  /* 3. Queries. */
  printf(",\"queries\":[");
  for (size_t qi = 0; qi < nq; qi++) {
    query_t *q = &queries[qi];
    scan_t sd, sf;
    exr_status stat_d, stat_f;
    size_t bs = SIZE_MAX, be = SIZE_MAX;
    exr_status base_status;
    exr_error e2 = {0};
    stat_d = scan_all(doc, NULL, q, &sd, &e2);
    stat_f = ft ? scan_all(NULL, ft, q, &sf, &e2) : EXR_ARGUMENT;
    if (ft) { bs = sf.first; be = sf.first == SIZE_MAX ? SIZE_MAX : sf.first + q->size; }
    base_status = stat_f;
    printf("%s{\"label\":", qi ? "," : ""); json_string(q->label);
    printf(",\"source\":"); json_string(q->source);
    printf(",\"hex\":"); json_hex(q->bytes, q->size > HEX_CAP ? HEX_CAP : q->size);
    printf(",\"bytes\":%zu,\"document_find\":", q->size); print_scan(&sd, stat_d);
    printf(",\"fixed_find\":"); if (ft) print_scan(&sf, stat_f); else printf("null");
    printf(",\"excerpt\":"); if (sd.first != SIZE_MAX) print_excerpt(text_copy, text_size, sd.first, q->size); else printf("null");

    /* Cancel then retry, several times. A cancelled call must publish a clean miss. */
    printf(",\"cancel\":[");
    for (size_t li = 0; li < sizeof(cancel_limits) / sizeof(*cancel_limits); li++) {
      cancel_t c = {0, cancel_limits[li]};
      exr_control control = {cancel_poll, NULL, &c};
      size_t cs = 0, ce = 0, rs = 0, re = 0;
      exr_status cstat = ft ? exr_fixed_text_find(ft, (const char *)q->bytes, q->size, 0, &control, &cs, &ce, &e2) : EXR_ARGUMENT;
      exr_status rstat = ft ? exr_fixed_text_find(ft, (const char *)q->bytes, q->size, 0, NULL, &rs, &re, &e2) : EXR_ARGUMENT;
      printf("%s{\"limit\":%d,\"polls\":%d,\"status\":\"%s\",\"start\":", li ? "," : "", c.limit, c.polls, status_name(cstat));
      json_pos(cs); printf(",\"end\":"); json_pos(ce);
      printf(",\"retry_status\":\"%s\",\"retry_start\":", status_name(rstat)); json_pos(rs); printf(",\"retry_end\":"); json_pos(re);
      printf(",\"retry_same\":%s}", rstat == base_status && same_pair(rs, re, bs, be) ? "true" : "false");
    }
    printf("]");

    /* Anchors on the first and last occurrence: capture, resolve, cancel, retry. */
    printf(",\"anchors\":[");
    for (int which = 0; which < 2; which++) {
      size_t at = which ? sd.last : sd.first;
      kept_t *k = &kept[qi][which];
      printf("%s{\"which\":\"%s\"", which ? "," : "", which ? "last" : "first");
      if (at == SIZE_MAX || stat_d != EXR_OK) { printf(",\"captured\":false}"); continue; }
      status = exr_anchor_create(doc, at, at + q->size, &k->anchor, &e2);
      if (status != EXR_OK) { printf(",\"captured\":false,\"status\":\"%s\"}", status_name(status)); continue; }
      k->have = 1; k->start = at; k->end = at + q->size;
      {
        exr_anchor_match m = {0};
        exr_status rs = exr_anchor_resolve(doc, &k->anchor, &m, &e2);
        printf(",\"captured\":true,\"exact_bytes\":%zu,\"prefix_bytes\":%zu,\"suffix_bytes\":%zu,\"resolve\":{\"status\":\"%s\",\"state\":\"%s\",\"start\":",
               k->anchor.exact ? strlen(k->anchor.exact) : 0, k->anchor.prefix ? strlen(k->anchor.prefix) : 0,
               k->anchor.suffix ? strlen(k->anchor.suffix) : 0, status_name(rs), state_name(m.state));
        json_pos(m.start); printf(",\"end\":"); json_pos(m.end); printf("},\"cancel\":[");
        for (int li = 0; li < 3; li++) {
          cancel_t c = {0, li + 1};
          exr_control control = {cancel_poll, NULL, &c};
          exr_anchor_match cm = {0}, rm = {0};
          exr_status cs = exr_anchor_resolve_ex(doc, &k->anchor, &control, &cm, &e2);
          exr_status rr = exr_anchor_resolve_ex(doc, &k->anchor, NULL, &rm, &e2);
          printf("%s{\"limit\":%d,\"status\":\"%s\",\"state\":\"%s\",\"start\":", li ? "," : "", c.limit, status_name(cs), state_name(cm.state));
          json_pos(cm.start); printf(",\"retry_status\":\"%s\",\"retry_state\":\"%s\",\"retry_start\":", status_name(rr), state_name(rm.state));
          json_pos(rm.start); printf(",\"retry_end\":"); json_pos(rm.end); printf("}");
        }
        printf("]}");
      }
    }
    printf("]}");
  }
  printf("]");

  /* 4. Reopen from the file and from memory; the kept anchors must still resolve. */
  exr_document_free(doc); doc = NULL;
  status = exr_document_open(file, &redoc, &error);
  printf(",\"reopen\":{\"status\":\"%s\"", status_name(status));
  if (status == EXR_OK) {
    const char *t3 = exr_document_text(redoc, &text_size3);
    fnv_c = fnv1a((const unsigned char *)t3, text_size3);
    printf(",\"bytes\":%zu,\"fnv1a64\":\"%016llx\",\"same\":%s,\"anchors\":[", text_size3, (unsigned long long)fnv_c,
           text_size3 == text_size && fnv_c == fnv_a ? "true" : "false");
    int firstrow = 1;
    for (size_t qi = 0; qi < nq; qi++) for (int which = 0; which < 2; which++) {
      kept_t *k = &kept[qi][which];
      if (!k->have) continue;
      for (int route = 0; route < 2; route++) {
        const exr_document *d = route ? memdoc : redoc;
        exr_anchor_match m = {0};
        exr_status rs;
        if (!d) continue;
        rs = exr_anchor_resolve(d, &k->anchor, &m, &error);
        printf("%s{\"label\":", firstrow ? "" : ","); json_string(queries[qi].label);
        printf(",\"which\":\"%s\",\"route\":\"%s\",\"status\":\"%s\",\"state\":\"%s\",\"start\":%zu,\"end\":%zu,\"expect_start\":%zu,\"expect_end\":%zu}",
               which ? "last" : "first", route ? "memory" : "file", status_name(rs), state_name(m.state),
               m.start, m.end, k->start, k->end);
        firstrow = 0;
      }
    }
    printf("]");
  }
  printf("}}\n");

  for (size_t qi = 0; qi < nq; qi++) {
    for (int w = 0; w < 2; w++) if (kept[qi][w].have) exr_anchor_free(&kept[qi][w].anchor);
    free(queries[qi].bytes);
  }
  exr_fixed_text_free(ft); exr_document_free(redoc); exr_document_free(memdoc);
  exr_free(blob); exr_library_close(library);
  free(text_copy); free(file_bytes); free(query_listing);
  return 0;
}
