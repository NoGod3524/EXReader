/* SPDX-License-Identifier: MIT */
/* HTTP policy layer: redirects, credentials, budgets, crawling, search and downloads. */
#include "opds_internal.h"
#include "opds_fs.h"
#include <ctype.h>
#ifdef _WIN32
#include <process.h>
#define OPDS_GETPID _getpid
#else
#include <unistd.h>
#define OPDS_GETPID getpid
#endif

struct opds_client {
  opds_config cfg;
  const opds_transport *tr;
  char cred_origin[320];
  char *auth;
  unsigned requests, redirects, cred_dropped, pages;
  char **visited; size_t nvisited, cvisited;
  unsigned tmp_counter;
};

void opds_config_defaults(opds_config *c) {
  memset(c, 0, sizeof *c);
  opds_limits_defaults(&c->limits);
}

opds_client *opds_client_create(const opds_config *cfg) {
  opds_client *c = (opds_client *)calloc(1, sizeof *c);
  if (!c) return NULL;
  if (cfg) c->cfg = *cfg; else opds_config_defaults(&c->cfg);
  c->tr = c->cfg.transport ? c->cfg.transport : opds_socket_transport();
  if (c->cfg.authorization && c->cfg.credential_origin) {
    if (!opds_url_origin(c->cfg.credential_origin, c->cred_origin, sizeof c->cred_origin)) { free(c); return NULL; }
    c->auth = (char *)malloc(strlen(c->cfg.authorization) + 1);
    if (!c->auth) { free(c); return NULL; }
    strcpy(c->auth, c->cfg.authorization);
  }
  c->cfg.authorization = NULL; /* never reachable through the stored config */
  return c;
}
void opds_client_begin_crawl(opds_client *c) {
  for (size_t i = 0; i < c->nvisited; i++) free(c->visited[i]);
  c->nvisited = 0; c->pages = 0;
}
void opds_client_free(opds_client *c) {
  if (!c) return;
  opds_client_begin_crawl(c);
  free(c->visited);
  if (c->auth) { memset(c->auth, 0, strlen(c->auth)); free(c->auth); }
  free(c);
}
void opds_client_stats(const opds_client *c, unsigned *req, unsigned *red, unsigned *drop) {
  if (req) *req = c->requests;
  if (red) *red = c->redirects;
  if (drop) *drop = c->cred_dropped;
}

/* ---- one logical GET with redirects ---- */
typedef struct {
  int status;
  char content_type[160], location[OPDS_URL_MAX], www[160];
  int64_t content_length;
  opds_status check_status;
  opds_error *err;
  /* caller hooks */
  opds_status (*check)(void *ctx, int status, const char *content_type, int64_t length, opds_error *err);
  int (*write)(void *ctx, const void *d, size_t n);
  void *ctx;
  opds_status write_status;
} hop;

static int hop_head(void *user, const opds_response *r) {
  hop *h = (hop *)user;
  h->status = r->status;
  h->content_type[0] = h->location[0] = h->www[0] = 0;
  if (r->content_type) snprintf(h->content_type, sizeof h->content_type, "%s", r->content_type);
  if (r->location) snprintf(h->location, sizeof h->location, "%s", r->location);
  if (r->www_authenticate) snprintf(h->www, sizeof h->www, "%s", r->www_authenticate);
  h->content_length = r->content_length;
  if (r->status < 200 || r->status > 299) return 1;
  if (h->check) {
    h->check_status = h->check(h->ctx, r->status, h->content_type, r->content_length, h->err);
    if (h->check_status != OPDS_OK) return 1;
  }
  return 0;
}
static int hop_body(void *user, const void *d, size_t n) {
  hop *h = (hop *)user;
  return h->write(h->ctx, d, n);
}

static void log_line(opds_client *c, const char *what, const char *url, int status) {
  char red[OPDS_URL_MAX + 16], line[OPDS_URL_MAX + 64];
  if (!c->cfg.log) return;
  opds_redact_url(url, red, sizeof red);
  snprintf(line, sizeof line, "%s %s -> %d", what, red, status);
  c->cfg.log(c->cfg.log_context, line);
}

static int is_redirect(int s) { return s == 301 || s == 302 || s == 303 || s == 307 || s == 308; }

/* Performs the GET; on success final_url holds the last URL fetched. */
static opds_status http_get(opds_client *c, const char *url, const char *accept, const opds_control *ctl,
                            opds_status (*check)(void *, int, const char *, int64_t, opds_error *),
                            int (*write)(void *, const void *, size_t), void *wctx,
                            char *final_url, size_t final_cap, char *ctype_out, size_t ctype_cap,
                            opds_error *err) {
  char cur[OPDS_URL_MAX];
  char **seen = (char **)calloc(c->cfg.limits.max_redirects + 2, sizeof(char *));
  size_t nseen = 0;
  opds_status st = OPDS_OK;
  if (!seen) return opds_fail(err, OPDS_MEMORY, "out of memory");
  if (strlen(url) >= sizeof cur) { free(seen); return opds_fail(err, OPDS_LIMIT, "URL too long"); }
  strcpy(cur, url);
  for (size_t n = 0;; n++) {
    hop h;
    opds_request rq;
    char origin[320], req_origin[320];
    int same = 0;
    memset(&h, 0, sizeof h);
    h.check = check; h.write = write; h.ctx = wctx; h.err = err; h.content_length = -1;
    rq.method = "GET"; rq.url = cur; rq.accept = accept; rq.authorization = NULL;
    if (c->auth && opds_url_origin(cur, req_origin, sizeof req_origin)) {
      strcpy(origin, c->cred_origin);
      same = !strcmp(origin, req_origin);
      if (same) rq.authorization = c->auth; else c->cred_dropped += n > 0;
    }
    seen[nseen] = (char *)malloc(strlen(cur) + 1);
    if (!seen[nseen]) { st = opds_fail(err, OPDS_MEMORY, "out of memory"); break; }
    strcpy(seen[nseen++], cur);
    c->requests++;
    st = c->tr->fetch(c->tr->context, &rq, c->cfg.limits.timeout_ms, ctl, hop_head, hop_body, &h, err);
    log_line(c, "GET", cur, h.status);
    if (st == OPDS_ABORTED) { st = h.write_status ? h.write_status : st; break; }
    if (st != OPDS_OK) break;
    if (h.check_status != OPDS_OK) { st = h.check_status; break; }
    if (is_redirect(h.status)) {
      char next[OPDS_URL_MAX];
      if (!h.location[0]) { st = opds_fail(err, OPDS_HTTP, "redirect without Location"); if (err) err->http_status = h.status; break; }
      if (n >= c->cfg.limits.max_redirects) { st = opds_fail(err, OPDS_LIMIT, "more than %zu redirects", c->cfg.limits.max_redirects); break; }
      if (opds_url_resolve(cur, h.location, next, sizeof next) != OPDS_OK) { st = opds_fail(err, OPDS_FORMAT, "bad redirect target"); break; }
      if (strncmp(next, "http://", 7) && strncmp(next, "https://", 8)) { st = opds_fail(err, OPDS_UNSUPPORTED, "redirect to a non-HTTP scheme"); break; }
      if (!strncmp(cur, "https://", 8) && !strncmp(next, "http://", 7)) { st = opds_fail(err, OPDS_ARGUMENT, "redirect downgrades https to http"); break; }
      for (size_t i = 0; i < nseen; i++) if (!strcmp(seen[i], next)) { st = opds_fail(err, OPDS_LIMIT, "redirect loop"); goto out; }
      c->redirects++;
      strcpy(cur, next);
      continue;
    }
    if (h.status >= 200 && h.status <= 299) {
      if (final_url) snprintf(final_url, final_cap, "%s", cur);
      if (ctype_out) snprintf(ctype_out, ctype_cap, "%s", h.content_type);
      st = OPDS_OK;
    } else if (h.status == 401) {
      st = opds_fail(err, OPDS_AUTH_REQUIRED, rq.authorization ? "credentials were rejected (401)" : "authentication required (401)");
      if (err) {
        size_t k = 0;
        err->http_status = 401; err->auth_scheme[0] = 0;
        while (h.www[k] && h.www[k] != ' ' && k + 1 < sizeof err->auth_scheme) { err->auth_scheme[k] = h.www[k]; k++; }
        err->auth_scheme[k] = 0;
      }
    } else {
      st = opds_fail(err, OPDS_HTTP, "HTTP status %d", h.status);
      if (err) err->http_status = h.status;
    }
    break;
  }
out:
  for (size_t i = 0; i < nseen; i++) free(seen[i]);
  free(seen);
  return st;
}

/* ---- feeds ---- */
typedef struct { opds_buf b; size_t max; opds_status st; } fsink;
static opds_status feed_check(void *ctx, int status, const char *ct, int64_t len, opds_error *err) {
  fsink *s = (fsink *)ctx;
  (void)status; (void)ct;
  if (len >= 0 && (uint64_t)len > s->max) return opds_fail(err, OPDS_LIMIT, "feed larger than %zu bytes", s->max);
  return OPDS_OK;
}
static int feed_write(void *ctx, const void *d, size_t n) {
  fsink *s = (fsink *)ctx;
  if (s->b.size + n > s->max) { s->st = OPDS_LIMIT; return 1; }
  if (!buf_append(&s->b, d, n)) { s->st = OPDS_MEMORY; return 1; }
  return 0;
}

#define FEED_ACCEPT "application/atom+xml;profile=opds-catalog, application/opds+json, application/atom+xml;q=0.9, application/json;q=0.8, */*;q=0.1"

static opds_status get_body(opds_client *c, const char *url, const char *accept, const opds_control *ctl,
                            opds_buf *out, char *final_url, size_t final_cap, char *ctype, size_t ctype_cap, opds_error *err) {
  fsink s;
  opds_status st;
  memset(&s, 0, sizeof s);
  s.max = c->cfg.limits.max_feed_bytes;
  /* write_status plumbing: feed_write records its status in the sink, mapped below */
  st = http_get(c, url, accept, ctl, feed_check, feed_write, &s, final_url, final_cap, ctype, ctype_cap, err);
  if (st == OPDS_ABORTED && s.st) st = opds_fail(err, s.st, s.st == OPDS_LIMIT ? "feed larger than %zu bytes" : "out of memory", s.max);
  if (st != OPDS_OK) { buf_free(&s.b); return st; }
  *out = s.b;
  return OPDS_OK;
}

opds_status opds_fetch_feed(opds_client *c, const char *url, const opds_control *ctl, opds_feed *out, opds_error *err) {
  opds_buf body = {0};
  char final_url[OPDS_URL_MAX], ctype[160];
  opds_status st;
  memset(out, 0, sizeof *out);
  if (!c || !url) return opds_fail(err, OPDS_ARGUMENT, "client and URL required");
  if (c->pages >= c->cfg.limits.max_pages) return opds_fail(err, OPDS_LIMIT, "page budget (%zu) exhausted", c->cfg.limits.max_pages);
  for (size_t i = 0; i < c->nvisited; i++)
    if (!strcmp(c->visited[i], url)) return opds_fail(err, OPDS_LIMIT, "feed already fetched in this crawl (loop)");
  if (c->nvisited == c->cvisited) {
    size_t cap = c->cvisited ? c->cvisited * 2 : 16;
    char **p = (char **)realloc(c->visited, cap * sizeof(char *));
    if (!p) return opds_fail(err, OPDS_MEMORY, "out of memory");
    c->visited = p; c->cvisited = cap;
  }
  c->visited[c->nvisited] = (char *)malloc(strlen(url) + 1);
  if (!c->visited[c->nvisited]) return opds_fail(err, OPDS_MEMORY, "out of memory");
  strcpy(c->visited[c->nvisited++], url);
  c->pages++;
  st = get_body(c, url, FEED_ACCEPT, ctl, &body, final_url, sizeof final_url, ctype, sizeof ctype, err);
  if (st != OPDS_OK) return st;
  st = opds_feed_parse(body.data, body.size, ctype, final_url, &c->cfg.limits, out, err);
  buf_free(&body);
  return st;
}

opds_status opds_fetch_next(opds_client *c, const opds_feed *feed, const opds_control *ctl,
                            opds_feed *out, int *has_next, opds_error *err) {
  const opds_link *n = opds_feed_find(feed, OPDS_REL_NEXT);
  memset(out, 0, sizeof *out);
  if (has_next) *has_next = n != NULL;
  if (!n) return OPDS_OK;
  return opds_fetch_feed(c, n->href, ctl, out, err);
}

opds_status opds_search_url(opds_client *c, const opds_feed *feed, const char *terms, unsigned page,
                            const opds_control *ctl, char *out, size_t cap, opds_error *err) {
  const opds_link *l = opds_feed_find(feed, OPDS_REL_SEARCH);
  char type[96];
  if (!l) return opds_fail(err, OPDS_UNSUPPORTED, "feed declares no search link");
  if (!terms) return opds_fail(err, OPDS_ARGUMENT, "search terms required");
  opds_media_type(l->type ? l->type : "", type, sizeof type);
  if (!strcmp(type, "application/opensearchdescription+xml")) {
    opds_buf body = {0};
    char final_url[OPDS_URL_MAX], ctype[160], tmpl[OPDS_URL_MAX], expanded[OPDS_URL_MAX];
    opds_status st = get_body(c, l->href, "application/opensearchdescription+xml, application/xml;q=0.9, */*;q=0.1", ctl, &body,
                              final_url, sizeof final_url, ctype, sizeof ctype, err);
    if (st != OPDS_OK) return st;
    st = opds_opensearch_template(body.data, body.size, &c->cfg.limits, tmpl, sizeof tmpl, err);
    buf_free(&body);
    if (st != OPDS_OK) return st;
    if ((st = opds_template_expand(tmpl, terms, page, expanded, sizeof expanded, err)) != OPDS_OK) return st;
    st = opds_url_resolve(final_url, expanded, out, cap);
    return st == OPDS_OK ? OPDS_OK : opds_fail(err, OPDS_LIMIT, "search URL too long");
  }
  if (l->flags & OPDS_LINK_TEMPLATED) {
    opds_status st = opds_template_expand(l->href, terms, page, out, cap, err);
    return st;
  }
  return opds_fail(err, OPDS_UNSUPPORTED, "search link is neither an OpenSearch description nor a URI template");
}

/* ---- downloads ---- */
typedef struct {
  FILE *f;
  opds_sha sha;
  uint64_t bytes, max;
  unsigned char head[512];
  size_t head_n;
  const opds_control *ctl;
  opds_status st;
  int io_error;
} dsink;

static opds_status dl_check(void *ctx, int status, const char *ct, int64_t len, opds_error *err) {
  dsink *d = (dsink *)ctx;
  (void)status; (void)ct;
  if (len >= 0 && (uint64_t)len > d->max) return opds_fail(err, OPDS_LIMIT, "download of %lld bytes exceeds the %llu byte budget", (long long)len, (unsigned long long)d->max);
  return OPDS_OK;
}
static int dl_write(void *ctx, const void *data, size_t n) {
  dsink *d = (dsink *)ctx;
  if (d->ctl && d->ctl->cancelled && d->ctl->cancelled(d->ctl->context)) { d->st = OPDS_CANCELLED; return 1; }
  if (d->bytes + n > d->max) { d->st = OPDS_LIMIT; return 1; }
  if (d->head_n < sizeof d->head) {
    size_t k = sizeof d->head - d->head_n;
    if (k > n) k = n;
    memcpy(d->head + d->head_n, data, k); d->head_n += k;
  }
  if (fwrite(data, 1, n, d->f) != n) { d->st = OPDS_IO; return 1; }
  opds_sha_update(&d->sha, data, n);
  d->bytes += n;
  return 0;
}

static int has_sep(const char *p) { return strchr(p, '/') || strchr(p, '\\'); }

static int reserved_name(const char *name) {
  char base[16];
  size_t n = 0;
  static const char *dev[] = {"CON", "PRN", "AUX", "NUL"};
  while (name[n] && name[n] != '.' && n + 1 < sizeof base) { base[n] = (char)toupper((unsigned char)name[n]); n++; }
  base[n] = 0;
  if (name[n] && name[n] != '.') return 0;
  for (size_t i = 0; i < 4; i++) if (!strcmp(base, dev[i])) return 1;
  if ((!strncmp(base, "COM", 3) || !strncmp(base, "LPT", 3)) && n == 4 && base[3] >= '1' && base[3] <= '9') return 1;
  return 0;
}

static opds_status check_dest(const char *dest, char *dir, size_t dircap, const char **name, opds_error *err) {
  const char *slash = NULL;
  size_t dl;
  for (const char *p = dest; *p; p++) if (*p == '/' || *p == '\\') slash = p;
  *name = slash ? slash + 1 : dest;
  if (!**name || !strcmp(*name, ".") || !strcmp(*name, "..")) return opds_fail(err, OPDS_ARGUMENT, "destination needs a plain file name");
  for (const char *p = *name; *p; p++)
    if ((unsigned char)*p < 0x20 || strchr("<>:\"|?*", *p)) return opds_fail(err, OPDS_ARGUMENT, "destination file name contains reserved characters");
  { size_t l = strlen(*name); if ((*name)[l - 1] == '.' || (*name)[l - 1] == ' ') return opds_fail(err, OPDS_ARGUMENT, "destination file name ends with a dot or space"); }
  if (reserved_name(*name)) return opds_fail(err, OPDS_ARGUMENT, "destination uses a reserved device name");
  if (strlen(dest) > 900) return opds_fail(err, OPDS_LIMIT, "destination path too long");
  dl = slash ? (size_t)(slash - dest) : 0;
  if (slash && dl == 0) dl = 1; /* root */
  if (!slash) { strcpy(dir, "."); }
  else { if (dl >= dircap) return opds_fail(err, OPDS_LIMIT, "destination path too long"); memcpy(dir, dest, dl); dir[dl] = 0; }
  if (opds_path_kind(dir) != 2) return opds_fail(err, OPDS_ARGUMENT, "destination directory does not exist");
  switch (opds_path_kind(dest)) {
    case 0: case 1: return OPDS_OK;
    case 2: return opds_fail(err, OPDS_ARGUMENT, "destination is a directory");
    default: return opds_fail(err, OPDS_ARGUMENT, "destination is a link or special file");
  }
}

static const char *sniff(const unsigned char *h, size_t n) {
  if (n >= 5 && !memcmp(h, "%PDF-", 5)) return "application/pdf";
  if (n >= 4 && !memcmp(h, "PK\x03\x04", 4)) {
    for (size_t i = 30; i + 28 <= n && i < 100; i++)
      if (!memcmp(h + i, "mimetypeapplication/epub+zip", 28)) return "application/epub+zip";
    return "application/zip";
  }
  for (size_t i = 0; i < n && i < 64; i++) {
    if (h[i] == ' ' || h[i] == '\t' || h[i] == '\r' || h[i] == '\n') continue;
    if (h[i] == '<') {
      if (opds_ascii_iprefix((const char *)h + i, "<!doctype html") || opds_ascii_iprefix((const char *)h + i, "<html")) return "text/html";
    }
    break;
  }
  return "";
}

static int is_zip_family(const char *m) {
  return !strcmp(m, "application/zip") || !strcmp(m, "application/x-zip-compressed") || !strcmp(m, "application/x-cbz") ||
         !strcmp(m, "application/vnd.comicbook+zip");
}
static int is_signed_type(const char *m) {
  return !strcmp(m, "application/epub+zip") || !strcmp(m, "application/pdf") || is_zip_family(m);
}
static int is_generic(const char *m) { return !strcmp(m, "application/octet-stream") || !strcmp(m, "binary/octet-stream") || !m[0]; }

static int sha_file(const char *path, char hex[65]) {
  FILE *f = opds_fopen_read(path);
  opds_sha s;
  unsigned char buf[16384];
  size_t n;
  if (!f) return 0;
  opds_sha_init(&s);
  while ((n = fread(buf, 1, sizeof buf, f)) > 0) opds_sha_update(&s, buf, n);
  { int bad = ferror(f); fclose(f); if (bad) return 0; }
  opds_sha_final_hex(&s, hex);
  return 1;
}

opds_status opds_download_url(opds_client *c, const char *url, const char *dest, const opds_download_options *opt,
                              const opds_control *ctl, opds_download_result *res, opds_error *err) {
  char dir[1024], tmp[1200], declared[96] = "", header_type[96] = "", ctype[160] = "", final_url[OPDS_URL_MAX];
  const char *name;
  dsink d;
  opds_status st;
  opds_download_options o;
  const char *sn;
  memset(res, 0, sizeof *res);
  if (!c || !url || !dest) return opds_fail(err, OPDS_ARGUMENT, "client, URL and destination required");
  memset(&o, 0, sizeof o);
  if (opt) o = *opt;
  if ((st = check_dest(dest, dir, sizeof dir, &name, err)) != OPDS_OK) return st;
  if (o.media_type) opds_media_type(o.media_type, declared, sizeof declared);
  memset(&d, 0, sizeof d);
  d.max = o.max_bytes && o.max_bytes < c->cfg.limits.max_download_bytes ? o.max_bytes : c->cfg.limits.max_download_bytes;
  d.ctl = ctl;
  opds_sha_init(&d.sha);
  snprintf(tmp, sizeof tmp, "%s/.opds-%lu-%u-%s", dir, (unsigned long)OPDS_GETPID(), ++c->tmp_counter, name);
  d.f = opds_fopen_new(tmp);
  if (!d.f) return opds_fail(err, OPDS_IO, "cannot create the temporary file next to the destination");
  st = http_get(c, url, "*/*", ctl, dl_check, dl_write, &d, final_url, sizeof final_url, ctype, sizeof ctype, err);
  if (st == OPDS_ABORTED && d.st) {
    st = opds_fail(err, d.st, d.st == OPDS_CANCELLED ? "download cancelled" : d.st == OPDS_LIMIT ? "download exceeds the byte budget" : "write failed");
  }
  if (st == OPDS_OK) {
    if (fflush(d.f) != 0 || opds_sync(d.f) != 0) st = opds_fail(err, OPDS_IO, "write failed");
  }
  if (fclose(d.f) != 0 && st == OPDS_OK) st = opds_fail(err, OPDS_IO, "write failed");
  if (st != OPDS_OK) { opds_remove(tmp); return st; }
  if (ctl && ctl->cancelled && ctl->cancelled(ctl->context)) { opds_remove(tmp); return opds_fail(err, OPDS_CANCELLED, "download cancelled"); }
  res->bytes = d.bytes;
  opds_sha_final_hex(&d.sha, res->sha256);
  if (d.bytes == 0) { opds_remove(tmp); return opds_fail(err, OPDS_FORMAT, "server returned an empty body"); }
  sn = sniff(d.head, d.head_n);
  snprintf(res->sniffed_type, sizeof res->sniffed_type, "%s", sn);
  opds_media_type(ctype, header_type, sizeof header_type);
  /* declared vs content: deterministic policy, see docs/WP15-OPDS.md */
  if (declared[0]) {
    int ok = 1;
    if (sn[0]) {
      if (!strcmp(sn, "application/epub+zip")) ok = !strcmp(declared, sn);
      else if (!strcmp(sn, "application/pdf")) ok = !strcmp(declared, sn);
      else if (!strcmp(sn, "application/zip")) ok = is_zip_family(declared);
      else if (!strcmp(sn, "text/html")) ok = !strcmp(declared, "text/html") || !strcmp(declared, "application/xhtml+xml");
    } else {
      ok = !is_signed_type(declared);
      if (ok && header_type[0] && !is_generic(header_type) && strcmp(header_type, declared)) ok = 0;
    }
    if (!ok) {
      opds_remove(tmp);
      return opds_fail(err, OPDS_MISMATCH, "content (%s) does not match the declared type %s", sn[0] ? sn : "unrecognised", declared);
    }
    if (header_type[0] && !is_generic(header_type) && strcmp(header_type, declared)) res->header_type_mismatch = 1;
  }
  if (o.verify) {
    st = o.verify(o.verify_context, tmp, declared[0] ? declared : sn, res->detail, sizeof res->detail);
    if (st == OPDS_UNSUPPORTED) {
      res->readable = OPDS_READ_UNKNOWN; /* verifier cannot judge this type: publish, but never claim readable */
    } else if (st != OPDS_OK) {
      res->readable = OPDS_READ_FAILED;
      opds_remove(tmp);
      return opds_fail(err, OPDS_UNREADABLE, "downloaded file is not a readable book: %s", res->detail);
    }
    else res->readable = OPDS_READ_OK;
  }
  {
    int kind = opds_path_kind(dest);
    int replace = o.existing == OPDS_EXISTING_REPLACE, r;
    if (kind == 2 || kind == 3 || kind < 0) { opds_remove(tmp); return opds_fail(err, OPDS_ARGUMENT, "destination changed into a directory or link"); }
    if (kind == 1) {
      char have[65];
      if (sha_file(dest, have) && !strcmp(have, res->sha256)) {
        opds_remove(tmp);
        res->already_present = 1; res->published = 1;
        return OPDS_OK;
      }
      if (!replace) { opds_remove(tmp); return opds_fail(err, OPDS_EXISTS, "destination exists with different content"); }
    }
    r = opds_publish(tmp, dest, replace);
    if (r == 1) { opds_remove(tmp); return opds_fail(err, OPDS_EXISTS, "destination appeared during the download"); }
    if (r != 0) { opds_remove(tmp); return opds_fail(err, OPDS_IO, "cannot publish the downloaded file"); }
    res->published = 1;
  }
  return OPDS_OK;
}

opds_status opds_download(opds_client *c, const opds_link *link, const char *dest, const opds_download_options *opt,
                          const opds_control *ctl, opds_download_result *res, opds_error *err) {
  opds_download_options o;
  opds_status st;
  memset(res, 0, sizeof *res);
  if (!link || !link->href) return opds_fail(err, OPDS_ARGUMENT, "link required");
  if (link->kind != OPDS_REL_ACQUISITION) return opds_fail(err, OPDS_ARGUMENT, "not an acquisition link");
  if ((st = opds_link_acquirable(link, err)) != OPDS_OK) return st;
  if (link->flags & OPDS_LINK_TEMPLATED) return opds_fail(err, OPDS_UNSUPPORTED, "templated acquisition links are not supported");
  memset(&o, 0, sizeof o);
  if (opt) o = *opt;
  if (!o.media_type) o.media_type = link->type;
  return opds_download_url(c, link->href, dest, &o, ctl, res, err);
}
