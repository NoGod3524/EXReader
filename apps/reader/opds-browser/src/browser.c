/* SPDX-License-Identifier: MIT */
#ifndef _WIN32
#define _POSIX_C_SOURCE 200809L
#endif
#include "reader_opds_browser.h"
#include <errno.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#ifdef _WIN32
#include <windows.h>
#include <bcrypt.h>
#else
#include <sys/stat.h>
#endif

/* ------------------------------------------------------------------ helpers */

static int fail(opds_error *e, int code, const char *fmt, ...) {
  va_list ap;
  if (e) {
    memset(e, 0, sizeof *e);
    e->code = (opds_status)code;
    va_start(ap, fmt);
    vsnprintf(e->message, sizeof e->message, fmt, ap);
    va_end(ap);
  }
  return code;
}

const char *reader_opds_status_name(int status) {
  if (status == READER_OPDS_CURSOR) return "cursor";
  if (status == READER_OPDS_BUSY) return "busy";
  return opds_status_name((opds_status)status);
}

const char *reader_opds_acquire_name(int kind) {
  switch (kind) {
    case READER_OPDS_ACQ_NOT: return "not-acquisition";
    case READER_OPDS_ACQ_FREE: return "free";
    case READER_OPDS_ACQ_SAMPLE: return "sample";
    case READER_OPDS_ACQ_BORROW: return "borrow";
    case READER_OPDS_ACQ_BUY: return "buy";
    case READER_OPDS_ACQ_SUBSCRIBE: return "subscribe";
    case READER_OPDS_ACQ_PRICED: return "priced";
    case READER_OPDS_ACQ_PROTECTED: return "protected";
    case READER_OPDS_ACQ_INDIRECT: return "indirect";
    default: return "unknown";
  }
}

static int ascii_lower(int c) { return (c >= 'A' && c <= 'Z') ? c + 32 : c; }

static int has_ci(const char *haystack, const char *needle) {
  size_t n = strlen(needle);
  for (; *haystack; haystack++) {
    size_t i = 0;
    while (i < n && haystack[i] && ascii_lower((unsigned char)haystack[i]) == needle[i]) i++;
    if (i == n) return 1;
  }
  return 0;
}

static int valid_url(const char *u) {
  size_t n, i;
  if (!u) return 0;
  n = strlen(u);
  if (n == 0 || n >= READER_OPDS_URL_BYTES) return 0;
  if (strncmp(u, "http://", 7) && strncmp(u, "https://", 8)) return 0;
  for (i = 0; i < n; i++)
    if ((unsigned char)u[i] <= 0x20 || (unsigned char)u[i] >= 0x7f) return 0;
  return 1;
}

/* scheme://host:port in lower case, userinfo removed, default port explicit. */
static int origin_of(const char *url, char *out, size_t cap) {
  const char *p, *end, *at = NULL, *colon = NULL, *host;
  char scheme[8];
  size_t sl, hl;
  int port;
  char tmp[300];
  if (!strncmp(url, "http://", 7)) { strcpy(scheme, "http"); sl = 7; port = 80; }
  else if (!strncmp(url, "https://", 8)) { strcpy(scheme, "https"); sl = 8; port = 443; }
  else return 0;
  p = url + sl;
  end = p;
  while (*end && *end != '/' && *end != '?' && *end != '#') end++;
  for (host = p; host < end; host++) if (*host == '@') at = host;
  if (at) p = at + 1;
  if (p < end && *p == '[') {
    const char *rb = (const char *)memchr(p, ']', (size_t)(end - p));
    if (!rb) return 0;
    if (rb + 1 < end && rb[1] == ':') colon = rb + 1;
    hl = (size_t)(rb + 1 - p);
  } else {
    const char *c;
    for (c = end; c > p; c--) if (c[-1] == ':') { colon = c - 1; break; }
    hl = (size_t)((colon ? colon : end) - p);
  }
  if (hl == 0 || hl >= sizeof tmp) return 0;
  {
    size_t i;
    for (i = 0; i < hl; i++) tmp[i] = (char)ascii_lower((unsigned char)p[i]);
    tmp[hl] = 0;
  }
  if (colon) {
    const char *d = colon + 1;
    int v = 0;
    if (d == end) return 0;
    for (; d < end; d++) {
      if (*d < '0' || *d > '9') return 0;
      v = v * 10 + (*d - '0');
      if (v > 65535) return 0;
    }
    port = v;
  }
  if ((size_t)snprintf(out, cap, "%s://%s:%d", scheme, tmp, port) >= cap) return 0;
  return 1;
}

static int valid_terms(const char *t) {
  const unsigned char *p = (const unsigned char *)t;
  size_t n;
  if (!t) return 0;
  n = strlen(t);
  if (n == 0 || n > READER_OPDS_SEARCH_BYTES) return 0;
  while (*p) {
    unsigned c = *p;
    unsigned need = 0, cp;
    if (c < 0x20 || c == 0x7f) return 0;
    if (c < 0x80) { p++; continue; }
    if (c >= 0xc2 && c <= 0xdf) { need = 1; cp = c & 0x1f; }
    else if (c >= 0xe0 && c <= 0xef) { need = 2; cp = c & 0x0f; }
    else if (c >= 0xf0 && c <= 0xf4) { need = 3; cp = c & 0x07; }
    else return 0;
    p++;
    while (need--) {
      if ((*p & 0xc0) != 0x80) return 0;
      cp = (cp << 6) | (*p & 0x3f);
      p++;
    }
    if ((c >= 0xe0 && c <= 0xef && cp < 0x800) || (c >= 0xf0 && cp < 0x10000) || cp > 0x10ffff || (cp >= 0xd800 && cp <= 0xdfff)) return 0;
  }
  return 1;
}

static FILE *open_file(const char *path, int write) {
#ifdef _WIN32
  int count = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, path, -1, NULL, 0);
  wchar_t *wide;
  FILE *f;
  if (count <= 0) return NULL;
  wide = (wchar_t *)malloc((size_t)count * sizeof(*wide));
  if (!wide) return NULL;
  if (!MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, path, -1, wide, count)) { free(wide); return NULL; }
  f = _wfopen(wide, write ? L"wb" : L"rb");
  free(wide);
  return f;
#else
  return fopen(path, write ? "wb" : "rb");
#endif
}

static int remove_file(const char *path) {
#ifdef _WIN32
  int count = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, path, -1, NULL, 0);
  wchar_t *wide;
  int r;
  if (count <= 0) { errno = EINVAL; return -1; }
  wide = (wchar_t *)malloc((size_t)count * sizeof(*wide));
  if (!wide) { errno = ENOMEM; return -1; }
  if (!MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, path, -1, wide, count)) { free(wide); errno = EINVAL; return -1; }
  r = _wremove(wide);
  free(wide);
  return r;
#else
  return remove(path);
#endif
}

static int seek_to(FILE *f, uint64_t off) {
#ifdef _WIN32
  return _fseeki64(f, (__int64)off, SEEK_SET);
#else
  return fseeko(f, (off_t)off, SEEK_SET);
#endif
}

static void random_bytes(unsigned char *out, size_t n) {
#ifdef _WIN32
  if (BCryptGenRandom(NULL, out, (ULONG)n, BCRYPT_USE_SYSTEM_PREFERRED_RNG) == 0) return;
#else
  FILE *f = fopen("/dev/urandom", "rb");
  if (f) {
    size_t got = fread(out, 1, n, f);
    fclose(f);
    if (got == n) return;
  }
#endif
  {
    unsigned long long t = (unsigned long long)time(NULL) ^ (unsigned long long)(size_t)out;
    size_t i;
    for (i = 0; i < n; i++) { t = t * 6364136223846793005ULL + 1442695040888963407ULL; out[i] = (unsigned char)(t >> 33); }
  }
}

/* ------------------------------------------------------------------ snapshot arena */

typedef struct sblock {
  struct sblock *next;
  size_t used, cap;
} sblock;
#define SB_HDR ((sizeof(sblock) + 15u) & ~(size_t)15u)
#define SB_STEP (64u * 1024u)

typedef struct {
  sblock *head;
  size_t total;
  int status;
} snap;

typedef struct {
  sblock *head;
  opds_link search;
  int has_search;
} pagepriv;

static void snap_release(sblock *b) {
  while (b) {
    sblock *n = b->next;
    free(b);
    b = n;
  }
}

static void *snap_alloc(snap *s, size_t n) {
  sblock *b;
  void *p;
  n = (n + 15u) & ~(size_t)15u;
  if (s->status) return NULL;
  if (n > READER_OPDS_SNAPSHOT_BYTES || s->total + n > READER_OPDS_SNAPSHOT_BYTES) { s->status = READER_OPDS_LIMIT; return NULL; }
  b = s->head;
  if (!b || b->cap - b->used < n) {
    size_t cap = n > SB_STEP ? n : SB_STEP;
    b = (sblock *)malloc(SB_HDR + cap);
    if (!b) { s->status = READER_OPDS_MEMORY; return NULL; }
    b->next = s->head;
    b->used = 0;
    b->cap = cap;
    s->head = b;
  }
  p = (char *)b + SB_HDR + b->used;
  b->used += n;
  s->total += n;
  memset(p, 0, n);
  return p;
}

static const char *snap_str(snap *s, const char *p) {
  size_t n;
  char *o;
  if (!p) p = "";
  n = strlen(p);
  o = (char *)snap_alloc(s, n + 1);
  if (!o) return "";
  memcpy(o, p, n + 1);
  return o;
}

/* ------------------------------------------------------------------ classification */

/* Order matters and is part of the contract: a DRM licence is refused as protected even when
   its rel is also buy/borrow, a sample stays a sample even with an indirect payload, and only an
   unpriced, unprotected, direct acquisition link is free. */
static int classify(const opds_link *l) {
  if (l->acq == OPDS_ACQ_NONE) return READER_OPDS_ACQ_NOT;
  if (l->flags & OPDS_LINK_PROTECTED) return READER_OPDS_ACQ_PROTECTED;
  if (l->acq == OPDS_ACQ_BUY) return READER_OPDS_ACQ_BUY;
  if (l->acq == OPDS_ACQ_BORROW) return READER_OPDS_ACQ_BORROW;
  if (l->acq == OPDS_ACQ_SUBSCRIBE) return READER_OPDS_ACQ_SUBSCRIBE;
  if (l->acq == OPDS_ACQ_SAMPLE) return READER_OPDS_ACQ_SAMPLE;
  if (l->flags & OPDS_LINK_PRICED) return READER_OPDS_ACQ_PRICED;
  if (l->flags & (OPDS_LINK_INDIRECT | OPDS_LINK_TEMPLATED)) return READER_OPDS_ACQ_INDIRECT;
  return READER_OPDS_ACQ_FREE;
}

static int is_navigation(const opds_link *l, int acquire) {
  if (acquire != READER_OPDS_ACQ_NOT) return 0;
  if (l->kind == OPDS_REL_IMAGE || l->kind == OPDS_REL_THUMBNAIL || l->kind == OPDS_REL_SEARCH) return 0;
  if (l->kind == OPDS_REL_SUBSECTION) return 1;
  if (l->type && (has_ci(l->type, "opds") || has_ci(l->type, "atom+xml"))) return 1;
  return 0;
}

/* Extension of an importable media type, or NULL. */
static const char *type_extension(const char *normalized) {
  if (!strcmp(normalized, "application/epub+zip")) return ".epub";
  if (!strcmp(normalized, "application/pdf")) return ".pdf";
  if (!strcmp(normalized, "application/vnd.comicbook+zip") || !strcmp(normalized, "application/x-cbz")) return ".cbz";
  return NULL;
}

static int importable_link(const opds_link *l) {
  char t[96];
  opds_media_type(l->type ? l->type : "", t, sizeof t);
  return type_extension(t) != NULL;
}

/* ------------------------------------------------------------------ snapshot building */

static void copy_link(snap *s, const opds_link *l, reader_opds_link *o) {
  o->rel = snap_str(s, l->rel);
  o->href = snap_str(s, l->href);
  o->raw_href = snap_str(s, l->raw_href);
  o->type = snap_str(s, l->type);
  o->title = snap_str(s, l->title);
  o->indirect_type = snap_str(s, l->indirect_type);
  o->kind = (int)l->kind;
  o->flags = l->flags;
  o->acquire = classify(l);
  o->navigation = is_navigation(l, o->acquire);
}

static reader_opds_link *copy_links(snap *s, const opds_link *src, size_t n) {
  reader_opds_link *out;
  size_t i;
  if (!n) return NULL;
  out = (reader_opds_link *)snap_alloc(s, n * sizeof *out);
  if (!out) return NULL;
  for (i = 0; i < n; i++) copy_link(s, &src[i], &out[i]);
  return out;
}

static int build_page(const opds_feed *feed, reader_opds_page *p, pagepriv *priv, snap *s) {
  size_t i, k, groups = 0;
  reader_opds_entry *ents;
  const opds_facet *fac;
  const opds_link *search;
  p->version = feed->version;
  p->id = snap_str(s, feed->id);
  p->title = snap_str(s, feed->title);
  p->updated = snap_str(s, feed->updated);
  p->base_url = snap_str(s, feed->base_url);
  p->total_results = feed->total_results;
  p->items_per_page = feed->items_per_page;
  p->start_index = feed->start_index;
  p->current_page = feed->current_page;
  p->declared_type_mismatch = feed->declared_type_mismatch;
  p->links = copy_links(s, feed->links, feed->link_count);
  p->link_count = p->links ? feed->link_count : 0;
  if (feed->entry_count) {
    ents = (reader_opds_entry *)snap_alloc(s, feed->entry_count * sizeof *ents);
    if (!ents) return s->status;
    for (i = 0; i < feed->entry_count; i++) {
      const opds_entry *e = &feed->entries[i];
      reader_opds_entry *o = &ents[i];
      o->id = snap_str(s, e->id);
      o->title = snap_str(s, e->title);
      o->updated = snap_str(s, e->updated);
      o->summary = snap_str(s, e->summary);
      o->identifier = snap_str(s, e->identifier);
      o->language = snap_str(s, e->language);
      o->publisher = snap_str(s, e->publisher);
      o->group = snap_str(s, e->group);
      o->is_publication = e->is_publication;
      if (e->author_count) {
        const char **a = (const char **)snap_alloc(s, e->author_count * sizeof *a);
        if (!a) return s->status;
        for (k = 0; k < e->author_count; k++) a[k] = snap_str(s, e->authors[k]);
        o->authors = a;
        o->author_count = e->author_count;
      }
      o->links = copy_links(s, e->links, e->link_count);
      o->link_count = o->links ? e->link_count : 0;
      o->free_link = -1;
      for (k = 0; k < o->link_count; k++) {
        if (o->links[k].acquire == READER_OPDS_ACQ_FREE) {
          if (o->free_link < 0 && importable_link(&e->links[k])) o->free_link = (int)k;
        } else if (o->links[k].acquire != READER_OPDS_ACQ_NOT) {
          o->restricted_links++;
        }
      }
      if (s->status) return s->status;
    }
    p->entries = ents;
    p->entry_count = feed->entry_count;
  }
  fac = opds_feed_facets(feed, &groups);
  if (fac && groups) {
    reader_opds_facet *fo = (reader_opds_facet *)snap_alloc(s, groups * sizeof *fo);
    if (!fo) return s->status;
    for (i = 0; i < groups; i++) {
      reader_opds_facet_choice *c;
      fo[i].title = snap_str(s, fac[i].title);
      if (fac[i].choice_count) {
        c = (reader_opds_facet_choice *)snap_alloc(s, fac[i].choice_count * sizeof *c);
        if (!c) return s->status;
        for (k = 0; k < fac[i].choice_count; k++) {
          c[k].rel = snap_str(s, fac[i].choices[k].link.rel);
          c[k].title = snap_str(s, fac[i].choices[k].link.title);
          c[k].href = snap_str(s, fac[i].choices[k].link.href);
          c[k].type = snap_str(s, fac[i].choices[k].link.type);
          c[k].flags = fac[i].choices[k].link.flags;
          c[k].number_of_items = fac[i].choices[k].number_of_items;
          c[k].active = fac[i].choices[k].active;
        }
        fo[i].choices = c;
        fo[i].choice_count = fac[i].choice_count;
      }
    }
    p->facets = fo;
    p->facet_count = groups;
  }
  search = opds_feed_find(feed, OPDS_REL_SEARCH);
  if (search) {
    priv->has_search = 1;
    priv->search.rel = snap_str(s, search->rel);
    priv->search.href = snap_str(s, search->href);
    priv->search.raw_href = priv->search.href;
    priv->search.type = snap_str(s, search->type);
    priv->search.title = snap_str(s, search->title);
    priv->search.kind = OPDS_REL_SEARCH;
    priv->search.acq = OPDS_ACQ_NONE;
    priv->search.flags = search->flags;
    p->has_search = 1;
  }
  return s->status;
}

void reader_opds_page_free(reader_opds_page *page) {
  pagepriv *priv;
  if (!page) return;
  priv = (pagepriv *)page->storage_;
  if (priv) {
    snap_release(priv->head);
    free(priv);
  }
  free(page);
}

/* ------------------------------------------------------------------ browser */

typedef struct {
  int used;
  unsigned long long stamp;
  char identity[READER_OPDS_IDENTITY_BYTES];
  char origin[320];
  unsigned pages;
  char (*visited)[65];
  size_t nvisited, cvisited;
  char *next_url;
  char cursor[READER_OPDS_CURSOR_BYTES];
} seq;

struct reader_opds_browser {
  opds_client *client;
  opds_limits limits;
  char staging[READER_OPDS_STAGING_BYTES];
  seq seqs[READER_OPDS_SEQUENCES];
  unsigned long long clock, issued;
  unsigned char nonce[16];
  volatile long busy;
};

static int enter(reader_opds_browser *b) {
#ifdef _WIN32
  return InterlockedCompareExchange(&b->busy, 1, 0) == 0;
#else
  return __sync_bool_compare_and_swap(&b->busy, 0, 1);
#endif
}
static void leave(reader_opds_browser *b) {
#ifdef _WIN32
  InterlockedExchange(&b->busy, 0);
#else
  __sync_lock_release(&b->busy);
#endif
}

void reader_opds_config_defaults(reader_opds_config *c) {
  memset(c, 0, sizeof *c);
  c->struct_size = sizeof *c;
  opds_limits_defaults(&c->limits);
}

static size_t clamp_size(size_t v, size_t def) { return (v == 0 || v > def) ? def : v; }

static int is_directory(const char *path) {
#ifdef _WIN32
  int count = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, path, -1, NULL, 0);
  DWORD attributes;
  wchar_t *wide;
  int ok;
  if (count <= 0) return 0;
  wide = (wchar_t *)malloc((size_t)count * sizeof(*wide));
  if (!wide) return 0;
  ok = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, path, -1, wide, count) > 0;
  attributes = ok ? GetFileAttributesW(wide) : INVALID_FILE_ATTRIBUTES;
  free(wide);
  return ok && attributes != INVALID_FILE_ATTRIBUTES && (attributes & FILE_ATTRIBUTE_DIRECTORY) != 0;
#else
  struct stat st;
  return stat(path, &st) == 0 && S_ISDIR(st.st_mode);
#endif
}

/* Copies the staging directory, dropping a trailing separator but never a drive root. */
static int copy_staging(const char *src, char *out, size_t cap) {
  size_t n = strlen(src);
  if (n == 0 || n > 800 || n >= cap) return 0;
  while (n > 1 && (src[n - 1] == '/' || src[n - 1] == '\\') && !(n == 3 && src[1] == ':')) n--;
  if (n == 0 || n >= cap) return 0;
  memcpy(out, src, n);
  out[n] = 0;
  return 1;
}

reader_opds_browser *reader_opds_browser_create(const reader_opds_config *config, opds_error *error) {
  reader_opds_config local;
  reader_opds_browser *b;
  opds_config oc;
  opds_limits def;
  char staging[READER_OPDS_STAGING_BYTES];
  staging[0] = 0;
  if (config && config->struct_size < sizeof *config) { fail(error, READER_OPDS_ARGUMENT, "reader_opds_config.struct_size is too small"); return NULL; }
  if (config) local = *config; else reader_opds_config_defaults(&local);
  if ((local.credential_origin != NULL) != (local.authorization != NULL)) {
    fail(error, READER_OPDS_ARGUMENT, "credential_origin and authorization must be supplied together");
    return NULL;
  }
  if (local.authorization && (strpbrk(local.authorization, "\r\n") || !local.authorization[0])) {
    fail(error, READER_OPDS_ARGUMENT, "authorization is empty or contains a line break");
    return NULL;
  }
  if (local.staging_dir) {
    if (!copy_staging(local.staging_dir, staging, sizeof staging)) {
      fail(error, READER_OPDS_ARGUMENT, "staging_dir is empty or longer than 800 bytes");
      return NULL;
    }
    if (!is_directory(staging)) {
      fail(error, READER_OPDS_ARGUMENT, "staging_dir is not an existing directory");
      return NULL;
    }
  }
  b = (reader_opds_browser *)calloc(1, sizeof *b);
  if (!b) { fail(error, READER_OPDS_MEMORY, "out of memory"); return NULL; }
  opds_limits_defaults(&def);
  b->limits.max_feed_bytes = clamp_size(local.limits.max_feed_bytes, def.max_feed_bytes);
  b->limits.max_elements = clamp_size(local.limits.max_elements, def.max_elements);
  b->limits.max_entries = clamp_size(local.limits.max_entries, def.max_entries);
  b->limits.max_links_per_entry = clamp_size(local.limits.max_links_per_entry, def.max_links_per_entry);
  b->limits.max_depth = clamp_size(local.limits.max_depth, def.max_depth);
  b->limits.max_redirects = clamp_size(local.limits.max_redirects, def.max_redirects);
  b->limits.max_pages = clamp_size(local.limits.max_pages, def.max_pages);
  b->limits.max_download_bytes = (local.limits.max_download_bytes == 0 || local.limits.max_download_bytes > def.max_download_bytes) ? def.max_download_bytes : local.limits.max_download_bytes;
  b->limits.timeout_ms = (local.limits.timeout_ms == 0 || local.limits.timeout_ms > def.timeout_ms) ? def.timeout_ms : local.limits.timeout_ms;
  opds_config_defaults(&oc);
  oc.transport = local.transport ? local.transport : reader_opds_default_transport();
  oc.limits = b->limits;
  oc.credential_origin = local.credential_origin;
  oc.authorization = local.authorization;
  /* The frozen module's request format fixes the User-Agent; no host value is forwarded. */
  b->client = opds_client_create(&oc);
  if (!b->client) {
    free(b);
    fail(error, READER_OPDS_ARGUMENT, "cannot create the OPDS client (bad credential origin or out of memory)");
    return NULL;
  }
  if (staging[0]) memcpy(b->staging, staging, strlen(staging) + 1);
  random_bytes(b->nonce, sizeof b->nonce);
  return b;
}

static void seq_clear(seq *s) {
  free(s->visited);
  free(s->next_url);
  memset(s, 0, sizeof *s);
}

void reader_opds_browser_free(reader_opds_browser *b) {
  size_t i;
  if (!b) return;
  for (i = 0; i < READER_OPDS_SEQUENCES; i++) seq_clear(&b->seqs[i]);
  opds_client_free(b->client);
  memset(b->nonce, 0, sizeof b->nonce);
  free(b);
}

void reader_opds_browser_stats(const reader_opds_browser *b, unsigned *requests, unsigned *redirects,
                               unsigned *credentials_dropped) {
  if (!b) {
    if (requests) *requests = 0;
    if (redirects) *redirects = 0;
    if (credentials_dropped) *credentials_dropped = 0;
    return;
  }
  opds_client_stats(b->client, requests, redirects, credentials_dropped);
}

/* Hashes a|b|c with an explicit length so the digest never depends on snprintf
   truncation or on uninitialised bytes. Callers keep every part below READER_OPDS_URL_BYTES. */
static void hash_hex(const char *a, const char *b2, const char *c, char out[65]) {
  char buf[3 * READER_OPDS_URL_BYTES + 8];
  size_t la = strlen(a), lb = strlen(b2), lc = strlen(c), total = la + 1 + lb + 1 + lc;
  if (total > sizeof buf) {
    /* Deterministic fallback for an out-of-contract part: keep the head of each part. */
    la = la > READER_OPDS_URL_BYTES ? READER_OPDS_URL_BYTES : la;
    lb = lb > READER_OPDS_URL_BYTES ? READER_OPDS_URL_BYTES : lb;
    lc = lc > READER_OPDS_URL_BYTES ? READER_OPDS_URL_BYTES : lc;
    total = la + 1 + lb + 1 + lc;
  }
  memcpy(buf, a, la);
  buf[la] = 0;
  memcpy(buf + la + 1, b2, lb);
  buf[la + 1 + lb] = 0;
  memcpy(buf + la + 1 + lb + 1, c, lc);
  opds_sha256_hex(buf, total, out);
}

static int seen(const seq *s, const char hash[65]) {
  size_t i;
  for (i = 0; i < s->nvisited; i++) if (!memcmp(s->visited[i], hash, 65)) return 1;
  return 0;
}

static int remember(seq *s, const char hash[65]) {
  if (s->nvisited == s->cvisited) {
    size_t cap = s->cvisited ? s->cvisited * 2 : 8;
    char (*p)[65] = (char (*)[65])realloc(s->visited, cap * 65);
    if (!p) return 0;
    s->visited = p;
    s->cvisited = cap;
  }
  memcpy(s->visited[s->nvisited++], hash, 65);
  return 1;
}

/* Fetches url as the next page of `s`. Mutates `s` only on success. */
static int fetch_page(reader_opds_browser *b, seq *s, const char *url, const opds_control *ctl,
                      reader_opds_page **out, opds_error *err) {
  char h[65], next_hash[65], next_origin[320];
  opds_feed feed;
  opds_status st;
  reader_opds_page *p;
  pagepriv *priv;
  snap sn;
  const opds_link *nl;
  char *next_copy = NULL;
  int rc;
  *out = NULL;
  if (s->pages >= b->limits.max_pages) return fail(err, READER_OPDS_LIMIT, "page budget (%zu) of this feed sequence is exhausted", b->limits.max_pages);
  opds_sha256_hex(url, strlen(url), h);
  if (seen(s, h)) return fail(err, READER_OPDS_LIMIT, "page already shown in this feed sequence (loop)");
  opds_client_begin_crawl(b->client);
  memset(&feed, 0, sizeof feed);
  st = opds_fetch_feed(b->client, url, ctl, &feed, err);
  if (st != OPDS_OK) return (int)st;
  p = (reader_opds_page *)calloc(1, sizeof *p);
  priv = (pagepriv *)calloc(1, sizeof *priv);
  if (!p || !priv) { free(p); free(priv); opds_feed_free(&feed); return fail(err, READER_OPDS_MEMORY, "out of memory"); }
  memset(&sn, 0, sizeof sn);
  rc = build_page(&feed, p, priv, &sn);
  priv->head = sn.head;
  p->storage_ = priv;
  if (rc) {
    reader_opds_page_free(p);
    opds_feed_free(&feed);
    return fail(err, rc, rc == READER_OPDS_LIMIT ? "page data exceeds the %u byte snapshot budget" : "out of memory", (unsigned)READER_OPDS_SNAPSHOT_BYTES);
  }
  /* next link: same origin and never a page already shown */
  nl = opds_feed_find(&feed, OPDS_REL_NEXT);
  if (nl && nl->href && *nl->href) {
    if (!valid_url(nl->href) || !origin_of(nl->href, next_origin, sizeof next_origin) || strcmp(next_origin, s->origin)) {
      p->next_refused = 1;
    } else {
      opds_sha256_hex(nl->href, strlen(nl->href), next_hash);
      if (!memcmp(next_hash, h, 65) || seen(s, next_hash)) {
        p->next_refused = 1;
      } else {
        next_copy = (char *)malloc(strlen(nl->href) + 1);
        if (!next_copy) { reader_opds_page_free(p); opds_feed_free(&feed); return fail(err, READER_OPDS_MEMORY, "out of memory"); }
        strcpy(next_copy, nl->href);
      }
    }
  }
  /* The page is recorded as visited only after every allocation of this call succeeded,
     so a failed or cancelled call can be repeated with the same cursor. */
  if (!remember(s, h)) { free(next_copy); reader_opds_page_free(p); opds_feed_free(&feed); return fail(err, READER_OPDS_MEMORY, "out of memory"); }
  opds_feed_free(&feed);
  s->pages++;
  free(s->next_url);
  s->next_url = next_copy;
  s->cursor[0] = 0;
  memcpy(p->identity, s->identity, sizeof p->identity);
  p->page_number = s->pages;
  if (next_copy) {
    char counter[32], digest[65];
    snprintf(counter, sizeof counter, "%llu", ++b->issued);
    {
      unsigned char nonce_hex[40];
      size_t i;
      static const char digits[] = "0123456789abcdef";
      for (i = 0; i < 16; i++) { nonce_hex[i * 2] = (unsigned char)digits[b->nonce[i] >> 4]; nonce_hex[i * 2 + 1] = (unsigned char)digits[b->nonce[i] & 15]; }
      nonce_hex[32] = 0;
      {
        char key[160];
        snprintf(key, sizeof key, "%s%s", (const char *)nonce_hex, counter);
        hash_hex(key, s->identity, next_copy, digest);
      }
    }
    memcpy(s->cursor, "c1-", 3);
    memcpy(s->cursor + 3, digest, 32);
    s->cursor[35] = 0;
    memcpy(p->cursor, s->cursor, sizeof p->cursor);
    p->has_next = 1;
  }
  *out = p;
  return READER_OPDS_OK;
}

static seq *find_seq(reader_opds_browser *b, const char *identity) {
  size_t i;
  for (i = 0; i < READER_OPDS_SEQUENCES; i++)
    if (b->seqs[i].used && !strcmp(b->seqs[i].identity, identity)) return &b->seqs[i];
  return NULL;
}

/* Moves a successfully started sequence into a slot, evicting the least recently used. */
static void commit_seq(reader_opds_browser *b, seq *tmp) {
  seq *slot = find_seq(b, tmp->identity);
  size_t i;
  if (!slot) {
    for (i = 0; i < READER_OPDS_SEQUENCES; i++) if (!b->seqs[i].used) { slot = &b->seqs[i]; break; }
  }
  if (!slot) {
    slot = &b->seqs[0];
    for (i = 1; i < READER_OPDS_SEQUENCES; i++) if (b->seqs[i].stamp < slot->stamp) slot = &b->seqs[i];
  }
  seq_clear(slot);
  *slot = *tmp;
  slot->used = 1;
  slot->stamp = ++b->clock;
  memset(tmp, 0, sizeof *tmp);
}

static int start_sequence(reader_opds_browser *b, const char *kind, const char *url, const opds_control *ctl,
                          reader_opds_page **page, opds_error *err) {
  seq tmp;
  int rc;
  memset(&tmp, 0, sizeof tmp);
  if (!origin_of(url, tmp.origin, sizeof tmp.origin)) return fail(err, READER_OPDS_ARGUMENT, "URL has no valid origin");
  hash_hex("reader-opds-seq-1", kind, url, tmp.identity);
  rc = fetch_page(b, &tmp, url, ctl, page, err);
  if (rc != READER_OPDS_OK) { seq_clear(&tmp); return rc; }
  commit_seq(b, &tmp);
  return READER_OPDS_OK;
}

reader_opds_status reader_opds_open(reader_opds_browser *b, const char *url, const opds_control *ctl,
                                    reader_opds_page **page, opds_error *err) {
  int rc;
  if (page) *page = NULL;
  if (!b || !page) return (reader_opds_status)fail(err, READER_OPDS_ARGUMENT, "browser and page output are required");
  if (!valid_url(url)) return (reader_opds_status)fail(err, READER_OPDS_ARGUMENT, "URL must be a plain ASCII http(s) URL below %u bytes", (unsigned)READER_OPDS_URL_BYTES);
  if (!enter(b)) return (reader_opds_status)fail(err, READER_OPDS_BUSY, "another call on this browser is active");
  rc = start_sequence(b, "open", url, ctl, page, err);
  leave(b);
  return (reader_opds_status)rc;
}

reader_opds_status reader_opds_search(reader_opds_browser *b, const reader_opds_page *from, const char *terms,
                                      const opds_control *ctl, reader_opds_page **page, opds_error *err) {
  pagepriv *priv;
  opds_feed stub;
  char url[READER_OPDS_URL_BYTES];
  opds_status st;
  int rc;
  if (page) *page = NULL;
  if (!b || !from || !page || !from->storage_) return (reader_opds_status)fail(err, READER_OPDS_ARGUMENT, "browser, source page and page output are required");
  if (!valid_terms(terms)) return (reader_opds_status)fail(err, READER_OPDS_ARGUMENT, "search terms must be 1..%u bytes of valid UTF-8 without control characters", (unsigned)READER_OPDS_SEARCH_BYTES);
  priv = (pagepriv *)from->storage_;
  if (!priv->has_search) return (reader_opds_status)fail(err, READER_OPDS_UNSUPPORTED, "feed declares no search link");
  if (!enter(b)) return (reader_opds_status)fail(err, READER_OPDS_BUSY, "another call on this browser is active");
  memset(&stub, 0, sizeof stub);
  stub.links = &priv->search;
  stub.link_count = 1;
  opds_client_begin_crawl(b->client);
  st = opds_search_url(b->client, &stub, terms, 1, ctl, url, sizeof url, err);
  if (st != OPDS_OK) { leave(b); return (reader_opds_status)st; }
  if (!valid_url(url)) { leave(b); return (reader_opds_status)fail(err, READER_OPDS_FORMAT, "search link resolved to an unusable URL"); }
  rc = start_sequence(b, "search", url, ctl, page, err);
  leave(b);
  return (reader_opds_status)rc;
}

reader_opds_status reader_opds_resume(reader_opds_browser *b, const char *identity, const char *cursor,
                                      const opds_control *ctl, reader_opds_page **page, opds_error *err) {
  seq *s;
  char *url;
  int rc;
  if (page) *page = NULL;
  if (!b || !page || !identity || !cursor || !*cursor) return (reader_opds_status)fail(err, READER_OPDS_ARGUMENT, "browser, identity, cursor and page output are required");
  if (strlen(identity) != 64 || strlen(cursor) >= READER_OPDS_CURSOR_BYTES) return (reader_opds_status)fail(err, READER_OPDS_CURSOR, "malformed identity or cursor");
  if (!enter(b)) return (reader_opds_status)fail(err, READER_OPDS_BUSY, "another call on this browser is active");
  s = find_seq(b, identity);
  if (!s) { leave(b); return (reader_opds_status)fail(err, READER_OPDS_CURSOR, "unknown or evicted feed identity"); }
  if (!s->next_url || !s->cursor[0] || strcmp(cursor, s->cursor)) {
    leave(b);
    return (reader_opds_status)fail(err, READER_OPDS_CURSOR, "cursor is stale or was not issued for this feed");
  }
  url = (char *)malloc(strlen(s->next_url) + 1);
  if (!url) { leave(b); return (reader_opds_status)fail(err, READER_OPDS_MEMORY, "out of memory"); }
  strcpy(url, s->next_url);
  s->stamp = ++b->clock;
  rc = fetch_page(b, s, url, ctl, page, err);
  free(url);
  leave(b);
  return (reader_opds_status)rc;
}

reader_opds_status reader_opds_next(reader_opds_browser *b, const reader_opds_page *page, const opds_control *ctl,
                                    reader_opds_page **out, opds_error *err) {
  if (out) *out = NULL;
  if (!page || !page->has_next) return (reader_opds_status)fail(err, READER_OPDS_ARGUMENT, "page has no next cursor");
  return reader_opds_resume(b, page->identity, page->cursor, ctl, out, err);
}

reader_opds_status reader_opds_follow(reader_opds_browser *b, const reader_opds_link *link, const opds_control *ctl,
                                      reader_opds_page **page, opds_error *err) {
  if (page) *page = NULL;
  if (!link || !link->navigation) return (reader_opds_status)fail(err, READER_OPDS_ARGUMENT, "link is not a navigation link");
  return reader_opds_open(b, link->href, ctl, page, err);
}

/* ------------------------------------------------------------------ acquisition */

static unsigned rd16(const unsigned char *p) { return (unsigned)p[0] | ((unsigned)p[1] << 8); }
static uint32_t rd32(const unsigned char *p) { return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24); }

static uint64_t file_size(FILE *f) {
  long long v;
#ifdef _WIN32
  if (_fseeki64(f, 0, SEEK_END) != 0) return 0;
  v = _ftelli64(f);
#else
  if (fseeko(f, 0, SEEK_END) != 0) return 0;
  v = (long long)ftello(f);
#endif
  return v < 0 ? 0 : (uint64_t)v;
}

static int zip_envelope(FILE *f, uint64_t size, int epub, char *detail, size_t cap) {
  unsigned char head[64];
  unsigned char tail[65557];
  size_t n, i, got;
  if (size < 22) { snprintf(detail, cap, "too short for a ZIP container"); return 0; }
  if (seek_to(f, 0) != 0 || fread(head, 1, sizeof head < size ? sizeof head : (size_t)size, f) < 30) { snprintf(detail, cap, "cannot read the container head"); return 0; }
  if (memcmp(head, "PK\x03\x04", 4)) { snprintf(detail, cap, "missing ZIP local header"); return 0; }
  if (epub && (size < 58 || memcmp(head + 30, "mimetypeapplication/epub+zip", 28))) { snprintf(detail, cap, "EPUB mimetype entry is not first or not stored"); return 0; }
  n = size < sizeof tail ? (size_t)size : sizeof tail;
  if (seek_to(f, size - n) != 0) { snprintf(detail, cap, "cannot seek to the container tail"); return 0; }
  got = fread(tail, 1, n, f);
  if (got != n) { snprintf(detail, cap, "cannot read the container tail"); return 0; }
  for (i = n - 22 + 1; i-- > 0;) {
    if (!memcmp(tail + i, "PK\x05\x06", 4)) {
      unsigned comment = rd16(tail + i + 20);
      uint32_t cd_size = rd32(tail + i + 12), cd_off = rd32(tail + i + 16);
      uint64_t eocd = size - n + i;
      unsigned char sig[4];
      if (i + 22 + comment > n) continue;
      if (cd_size == 0xffffffffu || cd_off == 0xffffffffu) return 1; /* ZIP64: left to the SDK */
      if (rd16(tail + i + 10) == 0 || (uint64_t)cd_off + cd_size > eocd) { snprintf(detail, cap, "central directory lies outside the file"); return 0; }
      if (seek_to(f, cd_off) != 0 || fread(sig, 1, 4, f) != 4 || memcmp(sig, "PK\x01\x02", 4)) { snprintf(detail, cap, "central directory signature missing"); return 0; }
      return 1;
    }
  }
  snprintf(detail, cap, "ZIP end-of-central-directory record not found");
  return 0;
}

static int pdf_envelope(FILE *f, uint64_t size, char *detail, size_t cap) {
  unsigned char head[5], tail[1024];
  size_t n, i;
  if (size < 16) { snprintf(detail, cap, "too short for a PDF"); return 0; }
  if (seek_to(f, 0) != 0 || fread(head, 1, 5, f) != 5 || memcmp(head, "%PDF-", 5)) { snprintf(detail, cap, "missing %%PDF- header"); return 0; }
  n = size < sizeof tail ? (size_t)size : sizeof tail;
  if (seek_to(f, size - n) != 0 || fread(tail, 1, n, f) != n) { snprintf(detail, cap, "cannot read the PDF tail"); return 0; }
  for (i = 0; i + 5 <= n; i++) if (!memcmp(tail + i, "%%EOF", 5)) return 1;
  snprintf(detail, cap, "PDF end marker not found in the last 1024 bytes");
  return 0;
}

/* Runs on the network phase: structure only, never an SDK call. */
static opds_status envelope_verify(void *context, const char *path, const char *media_type, char *detail, size_t cap) {
  FILE *f = open_file(path, 0);
  uint64_t size;
  int ok;
  (void)context;
  if (!f) { snprintf(detail, cap, "cannot reopen the temporary file"); return OPDS_IO; }
  size = file_size(f);
  if (!strcmp(media_type, "application/pdf")) ok = pdf_envelope(f, size, detail, cap);
  else ok = zip_envelope(f, size, !strcmp(media_type, "application/epub+zip"), detail, cap);
  fclose(f);
  return ok ? OPDS_OK : OPDS_FORMAT;
}

reader_opds_status reader_opds_acquire(reader_opds_browser *b, const reader_opds_page *page, size_t entry,
                                       size_t link, const reader_opds_acquire_options *options,
                                       const opds_control *ctl, reader_opds_acquired *out, opds_error *err) {
  const reader_opds_entry *e;
  const reader_opds_link *l;
  char media[96], hash[65], dest[READER_OPDS_STAGING_BYTES], name[64];
  const char *ext;
  opds_link dl;
  opds_download_options dopt;
  opds_download_result res;
  opds_status st;
  if (out) { memset(out, 0, sizeof *out); out->struct_size = sizeof *out; }
  if (!b || !page || !out) return (reader_opds_status)fail(err, READER_OPDS_ARGUMENT, "browser, page and result are required");
  if (options && options->struct_size < sizeof *options) return (reader_opds_status)fail(err, READER_OPDS_ARGUMENT, "options.struct_size is too small");
  if (entry >= page->entry_count) return (reader_opds_status)fail(err, READER_OPDS_ARGUMENT, "entry index out of range");
  e = &page->entries[entry];
  if (link >= e->link_count) return (reader_opds_status)fail(err, READER_OPDS_ARGUMENT, "link index out of range");
  l = &e->links[link];
  if (l->acquire == READER_OPDS_ACQ_NOT || l->kind != (int)OPDS_REL_ACQUISITION)
    return (reader_opds_status)fail(err, READER_OPDS_ARGUMENT, "link is not an acquisition link");
  if (l->acquire == READER_OPDS_ACQ_SAMPLE)
    return (reader_opds_status)fail(err, READER_OPDS_UNSUPPORTED, "a sample is not the publication and is not downloaded");
  if (l->acquire != READER_OPDS_ACQ_FREE)
    return (reader_opds_status)fail(err, READER_OPDS_NEEDS_HOST, "%s acquisition needs a host capability and is never treated as a free download", reader_opds_acquire_name(l->acquire));
  opds_media_type(l->type, media, sizeof media);
  ext = type_extension(media);
  if (!ext) return (reader_opds_status)fail(err, READER_OPDS_UNSUPPORTED, "media type '%s' cannot be imported", media);
  if (!valid_url(l->href)) return (reader_opds_status)fail(err, READER_OPDS_ARGUMENT, "acquisition href is not a plain http(s) URL");
  if (!b->staging[0]) return (reader_opds_status)fail(err, READER_OPDS_ARGUMENT, "no staging_dir configured");
  hash_hex("reader-opds-acq-1", l->href, media, hash);
  snprintf(name, sizeof name, "opds-%.24s%s", hash, ext);
  if ((size_t)snprintf(dest, sizeof dest, "%s/%s", b->staging, name) >= sizeof dest) return (reader_opds_status)fail(err, READER_OPDS_LIMIT, "staging path too long");
  if (!enter(b)) return (reader_opds_status)fail(err, READER_OPDS_BUSY, "another call on this browser is active");
  memset(&dl, 0, sizeof dl);
  dl.rel = l->rel;
  dl.href = l->href;
  dl.raw_href = l->href;
  dl.type = l->type;
  dl.title = l->title;
  dl.kind = OPDS_REL_ACQUISITION;
  dl.acq = OPDS_ACQ_GENERIC;
  memset(&dopt, 0, sizeof dopt);
  dopt.media_type = media;
  dopt.existing = (options && options->replace_existing) ? OPDS_EXISTING_REPLACE : OPDS_EXISTING_FAIL;
  dopt.verify = envelope_verify;
  dopt.max_bytes = options ? options->max_bytes : 0;
  opds_client_begin_crawl(b->client);
  st = opds_download(b->client, &dl, dest, &dopt, ctl, &res, err);
  leave(b);
  if (st != OPDS_OK) return (reader_opds_status)st;
  snprintf(out->path, sizeof out->path, "%s", dest);
  snprintf(out->media_type, sizeof out->media_type, "%s", media);
  snprintf(out->sha256, sizeof out->sha256, "%s", res.sha256);
  snprintf(out->sniffed_type, sizeof out->sniffed_type, "%s", res.sniffed_type);
  out->bytes = res.bytes;
  out->already_present = res.already_present;
  out->header_type_mismatch = res.header_type_mismatch;
  return READER_OPDS_OK;
}

reader_opds_status reader_opds_staged_discard(const reader_opds_acquired *staged, opds_error *err) {
  const char *name, *p;
  size_t n, i;
  if (!staged || staged->struct_size < sizeof *staged || !staged->path[0]) return (reader_opds_status)fail(err, READER_OPDS_ARGUMENT, "staged file required");
  name = staged->path;
  for (p = staged->path; *p; p++) if (*p == '/' || *p == '\\') name = p + 1;
  n = strlen(name);
  if (n < 5 + 24 + 4 || strncmp(name, "opds-", 5)) return (reader_opds_status)fail(err, READER_OPDS_ARGUMENT, "not a staged file name");
  for (i = 5; i < 29; i++) if (!((name[i] >= '0' && name[i] <= '9') || (name[i] >= 'a' && name[i] <= 'f'))) return (reader_opds_status)fail(err, READER_OPDS_ARGUMENT, "not a staged file name");
  if (strcmp(name + 29, ".epub") && strcmp(name + 29, ".pdf") && strcmp(name + 29, ".cbz")) return (reader_opds_status)fail(err, READER_OPDS_ARGUMENT, "not a staged file name");
  if (remove_file(staged->path) != 0) {
    /* A failed reopen is not proof of absence: permission or sharing denial
       also prevents reads. Keep the caller's receipt/ownership on every error
       except an explicit missing-file result. */
    if (errno != ENOENT)
      return (reader_opds_status)fail(err, READER_OPDS_IO, "cannot remove the staged file");
  }
  return READER_OPDS_OK;
}
