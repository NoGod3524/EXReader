/* SPDX-License-Identifier: MIT */
/* WP15 OPDS client acceptance driver. Talks to tests/opds/server.py over real sockets and
   writes one JSON record per named case. Credentials arrive through the environment and
   are never printed or logged. usage:
   opds_test --a URL --b URL --corpus DIR --work DIR --out FILE [--only ID] */
#include "opds.h"
#include "opds_sdk.h"
#include "exreader.h"
#include <ctype.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#ifdef _WIN32
#include <direct.h>
#include <windows.h>
#define MKDIR(p) _mkdir(p)
#else
#include <dirent.h>
#include <sys/stat.h>
#include <unistd.h>
#define MKDIR(p) mkdir(p, 0777)
#endif

/* ---- harness state ---- */
static char A[64], B[64], CORPUS[512], WORK[512];
static char g_note[320];
static const char *g_actual = "";
static char g_input_hash[65];
static int g_input_set;
static char g_req[96][240];
static int g_nreq;
static opds_error E;
static const char *g_basic, *g_bearer;

#define FAIL(...) do { snprintf(g_note, sizeof g_note, __VA_ARGS__); return 1; } while (0)
#define CHECK(c) do { if (!(c)) FAIL("line %d: %s", __LINE__, #c); } while (0)
#define CHECK_ST(call, want) do { \
    opds_status s_ = (call); g_actual = opds_status_name(s_); \
    if (s_ != (want)) FAIL("line %d: %s -> %s, expected %s (%s)", __LINE__, #call, opds_status_name(s_), opds_status_name(want), E.message); } while (0)
#define CHECK_STR(a, b) do { const char *x_ = (a), *y_ = (b); \
    if (!x_ || !y_ || strcmp(x_, y_)) FAIL("line %d: '%s' != '%s'", __LINE__, x_ ? x_ : "(null)", y_ ? y_ : "(null)"); } while (0)

static unsigned long long now_ms(void) {
  struct timespec ts;
  timespec_get(&ts, TIME_UTC);
  return (unsigned long long)ts.tv_sec * 1000ull + (unsigned long long)ts.tv_nsec / 1000000ull;
}
static const char *U(const char *path) {
  static char ring[8][600];
  static int n;
  char *r = ring[n++ & 7];
  snprintf(r, 600, "%s%s", A, path);
  return r;
}
/* Request log: "GET <path?redacted query> -> <status>", host and port stripped. */
static void logcb(void *ctx, const char *line) {
  const char *p = strstr(line, "://"), *arrow = strstr(line, " -> "), *s;
  (void)ctx;
  if (g_nreq >= 96) return;
  if (!p || !arrow) { snprintf(g_req[g_nreq++], sizeof g_req[0], "%s", line); return; }
  s = strchr(p + 3, '/');
  if (!s || s > arrow) { snprintf(g_req[g_nreq++], sizeof g_req[0], "GET /%s", arrow); return; }
  snprintf(g_req[g_nreq++], sizeof g_req[0], "GET %.*s%s", (int)(arrow - s), s, arrow);
}
static opds_config cfg(void) {
  opds_config c;
  opds_config_defaults(&c);
  c.log = logcb;
  return c;
}
static opds_client *mk(const opds_config *c) { return opds_client_create(c); }
static opds_status fetch_path(opds_client *c, const char *path, opds_feed *f) {
  return opds_fetch_feed(c, U(path), NULL, f, &E);
}
static void in_file(const char *rel) {
  char p[700];
  FILE *f;
  unsigned char *buf;
  long n;
  snprintf(p, sizeof p, "%s/%s", CORPUS, rel);
  f = fopen(p, "rb");
  if (!f) return;
  fseek(f, 0, SEEK_END); n = ftell(f); fseek(f, 0, SEEK_SET);
  buf = (unsigned char *)malloc((size_t)n + 1);
  if (buf && fread(buf, 1, (size_t)n, f) == (size_t)n) { opds_sha256_hex(buf, (size_t)n, g_input_hash); g_input_set = 1; }
  free(buf); fclose(f);
}
static const opds_entry *EN(const opds_feed *f, const char *title) {
  for (size_t i = 0; i < f->entry_count; i++) if (!strcmp(f->entries[i].title, title)) return &f->entries[i];
  return NULL;
}
static const opds_link *LK(const opds_entry *e, size_t i) { return i < e->link_count ? &e->links[i] : NULL; }

/* ---- file helpers ---- */
static char CASE_DIR[700];
static void case_dir(const char *id) {
  MKDIR(WORK);
  snprintf(CASE_DIR, sizeof CASE_DIR, "%s/%s", WORK, id);
  MKDIR(CASE_DIR);
}
static int list_dir(const char *dir, char names[][160], int max) {
  int n = 0;
#ifdef _WIN32
  WIN32_FIND_DATAA fd;
  char pat[800];
  HANDLE h;
  snprintf(pat, sizeof pat, "%s\\*", dir);
  h = FindFirstFileA(pat, &fd);
  if (h == INVALID_HANDLE_VALUE) return 0;
  do { if (strcmp(fd.cFileName, ".") && strcmp(fd.cFileName, "..") && n < max) snprintf(names[n++], 160, "%s", fd.cFileName); } while (FindNextFileA(h, &fd));
  FindClose(h);
#else
  DIR *d = opendir(dir);
  struct dirent *e;
  if (!d) return 0;
  while ((e = readdir(d)) != NULL) if (strcmp(e->d_name, ".") && strcmp(e->d_name, "..") && n < max) snprintf(names[n++], 160, "%s", e->d_name);
  closedir(d);
#endif
  return n;
}
static int count_files(void) { char names[16][160]; return list_dir(CASE_DIR, names, 16); }
static char *read_file(const char *path, size_t *n) {
  FILE *f = fopen(path, "rb");
  char *b;
  long len;
  if (!f) return NULL;
  fseek(f, 0, SEEK_END); len = ftell(f); fseek(f, 0, SEEK_SET);
  b = (char *)malloc((size_t)len + 1);
  if (!b || fread(b, 1, (size_t)len, f) != (size_t)len) { fclose(f); free(b); return NULL; }
  b[len] = 0; fclose(f); *n = (size_t)len;
  return b;
}
static int write_file(const char *path, const char *data) {
  FILE *f = fopen(path, "wb");
  if (!f) return 0;
  fputs(data, f); fclose(f);
  return 1;
}
static int file_is(const char *path, const char *want) {
  size_t n; char *b = read_file(path, &n); int ok = b && n == strlen(want) && !memcmp(b, want, n);
  free(b); return ok;
}
static int file_exists(const char *path) { FILE *f = fopen(path, "rb"); if (f) fclose(f); return f != NULL; }
static void dest(char *out, size_t cap, const char *name) { snprintf(out, cap, "%s/%s", CASE_DIR, name); }

/* ---- cancellation ---- */
typedef struct { unsigned long long start; unsigned ms; } deadline;
static int cancel_after(void *c) { deadline *d = (deadline *)c; return now_ms() - d->start >= d->ms; }

/* ====================== OPDS 1 / Atom ====================== */
static int o1_nav_root(void) {
  opds_client *c; opds_feed f; opds_config cf = cfg(); const opds_link *l; const opds_entry *e;
  c = mk(&cf); in_file("o1/root.xml");
  CHECK_ST(fetch_path(c, "/c/o1/root.xml", &f), OPDS_OK);
  CHECK(f.version == 1); CHECK_STR(f.title, "Fixture Catalog"); CHECK(f.entry_count == 3);
  CHECK(!f.declared_type_mismatch);
  l = opds_feed_find(&f, OPDS_REL_START); CHECK(l); CHECK_STR(l->href, U("/c/o1/root.xml"));
  l = opds_feed_find(&f, OPDS_REL_SEARCH); CHECK(l); CHECK_STR(l->type, "application/opensearchdescription+xml");
  CHECK_STR(l->href, U("/o1/opensearch.xml"));
  e = EN(&f, "All Books"); CHECK(e && !e->is_publication); l = LK(e, 0); CHECK(l && l->kind == OPDS_REL_SUBSECTION);
  CHECK_STR(l->href, U("/o1/all?page=1")); CHECK_STR(e->summary, "Everything in the catalog");
  e = EN(&f, "New Releases"); CHECK(e); l = LK(e, 0); CHECK(l && l->kind == OPDS_REL_OTHER);
  CHECK_STR(l->rel, "http://opds-spec.org/sort/new");
  e = EN(&f, "Vendor Shelf"); CHECK(e); l = LK(e, 0); CHECK(l && l->kind == OPDS_REL_OTHER);
  CHECK_STR(l->rel, "x-vendor/shelf"); CHECK_STR(l->type, "application/vnd.vendor+xml"); CHECK_STR(l->raw_href, "shelf.xml");
  CHECK_STR(l->href, U("/c/o1/shelf.xml"));
  opds_feed_free(&f); opds_client_free(c);
  return 0;
}
static int o1_xml_base_relative(void) {
  opds_client *c; opds_feed f; opds_config cf = cfg(); const opds_entry *e; const opds_link *l;
  c = mk(&cf); in_file("o1/xmlbase.xml");
  CHECK_ST(fetch_path(c, "/c/o1/xmlbase.xml", &f), OPDS_OK);
  CHECK_STR(opds_feed_find(&f, OPDS_REL_SELF)->href, U("/c/o1/sub/self.xml"));
  CHECK_STR(opds_feed_find(&f, OPDS_REL_UP)->href, "http://other.example/up.xml");
  CHECK_STR(opds_feed_find(&f, OPDS_REL_START)->href, "http://cdn.example/start.xml");
  CHECK_STR(opds_feed_find(&f, OPDS_REL_FIRST)->href, U("/c/o1/sub/dir/?page=1"));
  e = EN(&f, "E1"); CHECK(e && e->link_count == 5);
  l = LK(e, 0); CHECK_STR(l->href, U("/c/o1/sub/dir/items/a%20b.xml")); CHECK_STR(l->raw_href, "a b.xml");
  l = LK(e, 1); CHECK_STR(l->href, U("/c/o1/sub/dir/items/caf%C3%A9.xml"));
  l = LK(e, 2); CHECK_STR(l->href, U("/c/o1/sub/dir/items/%7Efoo/%2Fx.xml"));
  l = LK(e, 3); CHECK_STR(l->href, U("/z/r.xml"));
  l = LK(e, 4); CHECK_STR(l->href, U("/c/o1/sub/dir/items/x.xml?a=b%20c&d=%41"));
  opds_feed_free(&f); opds_client_free(c);
  return 0;
}
static int o1_atom_namespaces(void) {
  opds_client *c; opds_feed f; opds_config cf = cfg(); const opds_entry *e;
  c = mk(&cf); in_file("o1/ns_prefixed.xml");
  CHECK_ST(fetch_path(c, "/c/o1/ns_prefixed.xml", &f), OPDS_OK);
  e = EN(&f, "Pref Book"); CHECK(e && e->is_publication);
  CHECK_STR(e->identifier, "urn:isbn:1"); CHECK_STR(e->language, "de");
  CHECK(e->author_count == 1); CHECK_STR(e->authors[0], "A. Author");
  CHECK_STR(LK(e, 0)->href, U("/dl/book.epub"));
  opds_feed_free(&f);
  CHECK_ST(fetch_path(c, "/c/o1/bad_ns.xml", &f), OPDS_FORMAT);
  opds_client_free(c);
  return 0;
}
static int o1_pagination_follow(void) {
  opds_client *c; opds_feed f, n; opds_config cf = cfg(); int has = 0; size_t pages = 1, total; const opds_link *l;
  c = mk(&cf); in_file("o1/root.xml");
  CHECK_ST(fetch_path(c, "/o1/all?page=1", &f), OPDS_OK);
  total = f.entry_count; CHECK(opds_feed_find(&f, OPDS_REL_NEXT)); CHECK(!opds_feed_find(&f, OPDS_REL_PREVIOUS));
  for (;;) {
    CHECK_ST(opds_fetch_next(c, &f, NULL, &n, &has, &E), OPDS_OK);
    if (!has) break;
    opds_feed_free(&f); f = n; pages++; total += f.entry_count;
    if (pages == 2) {
      l = opds_feed_find(&f, OPDS_REL_PREVIOUS); CHECK(l); CHECK_STR(l->href, U("/o1/all?page=1"));
      l = opds_feed_find(&f, OPDS_REL_LAST); CHECK(l); CHECK_STR(l->href, U("/o1/all?page=3"));
      CHECK_STR(f.entries[0].title, "Gamma Story");
    }
  }
  CHECK(pages == 3); CHECK(total == 5);
  CHECK(!opds_feed_find(&f, OPDS_REL_NEXT));
  opds_feed_free(&f); opds_client_free(c);
  return 0;
}
static int pagination_budget(const char *first, int atom) {
  opds_client *c; opds_feed f, n; opds_config cf = cfg(); int has;
  (void)atom;
  cf.limits.max_pages = 2; c = mk(&cf);
  CHECK_ST(fetch_path(c, first, &f), OPDS_OK);
  CHECK_ST(opds_fetch_next(c, &f, NULL, &n, &has, &E), OPDS_OK);
  opds_feed_free(&f); f = n;
  CHECK_ST(opds_fetch_next(c, &f, NULL, &n, &has, &E), OPDS_LIMIT);
  CHECK(strstr(E.message, "page budget"));
  opds_feed_free(&f); opds_client_free(c);
  return 0;
}
static int o1_pagination_page_budget(void) { return pagination_budget("/o1/all?page=1", 1); }
static int pagination_loop(const char *first) {
  opds_client *c; opds_feed f, n; opds_config cf = cfg(); int has;
  c = mk(&cf);
  CHECK_ST(fetch_path(c, first, &f), OPDS_OK);
  CHECK_ST(opds_fetch_next(c, &f, NULL, &n, &has, &E), OPDS_OK);
  opds_feed_free(&f); f = n;
  CHECK_ST(opds_fetch_next(c, &f, NULL, &n, &has, &E), OPDS_LIMIT);
  CHECK(strstr(E.message, "loop"));
  opds_feed_free(&f);
  opds_client_begin_crawl(c); /* a new crawl may revisit */
  CHECK_ST(fetch_path(c, first, &f), OPDS_OK);
  opds_feed_free(&f); opds_client_free(c);
  return 0;
}
static int o1_pagination_loop(void) { return pagination_loop("/o1/loop?page=1"); }

static const char UNI_TERMS[] = "caf\xc3\xa9 \xe4\xb8\xad\xe6\x96\x87 & x=1+2";
static int o1_search_opensearch(void) {
  opds_client *c; opds_feed root, r; opds_config cf = cfg(); char url[1024], want[256]; int before;
  c = mk(&cf); in_file("o1/opensearch.xml");
  CHECK_ST(fetch_path(c, "/c/o1/root.xml", &root), OPDS_OK);
  CHECK_ST(opds_search_url(c, &root, "story", 1, NULL, url, sizeof url, &E), OPDS_OK);
  CHECK_STR(url, U("/o1/search?q=story&page=1"));
  CHECK_ST(opds_fetch_feed(c, url, NULL, &r, &E), OPDS_OK);
  CHECK(r.entry_count == 2); CHECK_STR(r.entries[0].title, "Alpha Story"); CHECK(opds_feed_find(&r, OPDS_REL_NEXT));
  CHECK_STR(r.entries[0].authors[0], "Ann Author"); CHECK_STR(r.entries[0].identifier, "urn:opds-test:isbn:0");
  opds_feed_free(&r);
  before = g_nreq;
  CHECK_ST(opds_search_url(c, &root, UNI_TERMS, 1, NULL, url, sizeof url, &E), OPDS_OK);
  CHECK(strstr(url, "caf%C3%A9%20%E4%B8%AD%E6%96%87%20%26%20x%3D1%2B2"));
  CHECK_ST(opds_fetch_feed(c, url, NULL, &r, &E), OPDS_OK);
  snprintf(want, sizeof want, "Results for: %s", UNI_TERMS);
  CHECK_STR(r.title, want); CHECK(r.entry_count == 0);
  CHECK(g_nreq > before);
  opds_feed_free(&r); opds_feed_free(&root); opds_client_free(c);
  return 0;
}
static int o1_search_direct_template(void) {
  opds_client *c; opds_feed root, r; opds_config cf = cfg(); char url[1024];
  c = mk(&cf); in_file("o1/search_direct.xml");
  CHECK_ST(fetch_path(c, "/c/o1/search_direct.xml", &root), OPDS_OK);
  CHECK(opds_feed_find(&root, OPDS_REL_SEARCH)->flags & OPDS_LINK_TEMPLATED);
  CHECK_ST(opds_search_url(c, &root, "alpha", 3, NULL, url, sizeof url, &E), OPDS_OK);
  CHECK_STR(url, U("/o1/search2?query=alpha"));
  CHECK_ST(opds_fetch_feed(c, url, NULL, &r, &E), OPDS_OK);
  CHECK_STR(r.title, "Direct results for: alpha"); CHECK(r.entry_count == 1);
  opds_feed_free(&r); opds_feed_free(&root); opds_client_free(c);
  return 0;
}
static int search_refusals(const char *none, const char *notemplate) {
  opds_client *c; opds_feed f; opds_config cf = cfg(); char url[256];
  c = mk(&cf);
  CHECK_ST(fetch_path(c, none, &f), OPDS_OK);
  CHECK_ST(opds_search_url(c, &f, "x", 1, NULL, url, sizeof url, &E), OPDS_UNSUPPORTED);
  opds_feed_free(&f);
  CHECK_ST(fetch_path(c, notemplate, &f), OPDS_OK);
  CHECK_ST(opds_search_url(c, &f, NULL, 1, NULL, url, sizeof url, &E), OPDS_ARGUMENT);
  CHECK_ST(opds_search_url(c, &f, "x", 1, NULL, url, sizeof url, &E), OPDS_UNSUPPORTED);
  opds_feed_free(&f); opds_client_free(c);
  return 0;
}
static int o1_search_refusals(void) { in_file("o1/search_notemplate.xml"); return search_refusals("/c/o1/xmlbase.xml", "/c/o1/search_notemplate.xml"); }

static int o1_acquisition_selection(void) {
  opds_client *c; opds_feed f; opds_config cf = cfg(); const opds_entry *e; const opds_link *l;
  c = mk(&cf); in_file("o1/acq.xml");
  CHECK_ST(fetch_path(c, "/c/o1/acq.xml", &f), OPDS_OK);
  CHECK(f.entry_count == 9);
  e = EN(&f, "Open Book"); CHECK(e && e->is_publication && e->author_count == 2);
  CHECK_STR(e->identifier, "urn:isbn:9780000000001"); CHECK_STR(e->language, "en"); CHECK_STR(e->publisher, "Pub Co");
  CHECK_STR(e->summary, "An open access book."); CHECK_STR(e->authors[1], "Co Author");
  l = opds_entry_acquisition(e, NULL); CHECK(l && l->acq == OPDS_ACQ_OPEN_ACCESS); CHECK_STR(l->type, "application/pdf");
  l = opds_entry_acquisition(e, "application/epub+zip; charset=x"); CHECK(l); CHECK_STR(l->href, U("/dl/book.epub"));
  CHECK(!opds_entry_acquisition(e, "application/x-mobipocket-ebook"));
  CHECK(LK(e, 2)->kind == OPDS_REL_IMAGE && LK(e, 3)->kind == OPDS_REL_THUMBNAIL);
  e = EN(&f, "Sample Only"); CHECK(e && e->is_publication);
  CHECK(!opds_entry_acquisition(e, NULL));
  l = opds_entry_acquisition(e, "application/epub+zip"); CHECK(l && l->acq == OPDS_ACQ_SAMPLE);
  e = EN(&f, "Future Rel"); l = LK(e, 0); CHECK(l->acq == OPDS_ACQ_GENERIC); CHECK_STR(l->rel, "http://opds-spec.org/acquisition/x-future");
  CHECK_STR(l->type, "application/x-new");
  e = EN(&f, "Navigation Only"); CHECK(e && !e->is_publication);
  CHECK(opds_link_acquirable(opds_entry_acquisition(EN(&f, "Open Book"), "application/epub+zip"), &E) == OPDS_OK);
  g_actual = "ok";
  opds_feed_free(&f); opds_client_free(c);
  return 0;
}
static int needs_host_checks(opds_client *c, opds_feed *f, const char *const *titles, size_t n, const char *dir_name) {
  char dst[800];
  unsigned before, after;
  for (size_t i = 0; i < n; i++) {
    const opds_entry *e = EN(f, titles[i]); const opds_link *l;
    CHECK(e && e->is_publication);
    l = LK(e, 0); CHECK(l);
    CHECK_ST(opds_link_acquirable(l, &E), OPDS_NEEDS_HOST);
  }
  case_dir(dir_name); dest(dst, sizeof dst, "never.epub");
  opds_client_stats(c, &before, NULL, NULL);
  { opds_download_result r; const opds_entry *e = EN(f, titles[0]);
    CHECK_ST(opds_download(c, LK(e, 0), dst, NULL, NULL, &r, &E), OPDS_NEEDS_HOST); }
  opds_client_stats(c, &after, NULL, NULL);
  CHECK(before == after); CHECK(count_files() == 0);
  return 0;
}
static int o1_acquisition_needs_host(void) {
  opds_client *c; opds_feed f; opds_config cf = cfg(); int rc;
  static const char *const t[] = {"Borrow Book", "Buy Book", "Subscribe Book", "Adept Book", "Priced Generic"};
  c = mk(&cf); in_file("o1/acq.xml");
  CHECK_ST(fetch_path(c, "/c/o1/acq.xml", &f), OPDS_OK);
  CHECK(EN(&f, "Adept Book")->links[0].flags & OPDS_LINK_PROTECTED);
  CHECK(EN(&f, "Adept Book")->links[0].flags & OPDS_LINK_INDIRECT);
  CHECK_STR(EN(&f, "Adept Book")->links[0].indirect_type, "application/epub+zip");
  CHECK(EN(&f, "Buy Book")->links[0].flags & OPDS_LINK_PRICED);
  rc = needs_host_checks(c, &f, t, 5, "o1_acquisition_needs_host");
  opds_feed_free(&f); opds_client_free(c);
  return rc;
}

static int auth_flow(const char *path, const char *good, const char *scheme) {
  opds_client *c; opds_feed f; opds_config cf = cfg();
  c = mk(&cf);
  CHECK_ST(fetch_path(c, path, &f), OPDS_AUTH_REQUIRED);
  CHECK(E.http_status == 401); CHECK_STR(E.auth_scheme, scheme);
  opds_client_free(c);
  cf.credential_origin = A; cf.authorization = good; c = mk(&cf);
  CHECK_ST(fetch_path(c, path, &f), OPDS_OK);
  opds_feed_free(&f); opds_client_free(c);
  cf.authorization = "Basic d3Jvbmc6d3Jvbmc="; c = mk(&cf);
  CHECK_ST(fetch_path(c, path, &f), OPDS_AUTH_REQUIRED);
  CHECK(strstr(E.message, "rejected"));
  opds_client_free(c);
  /* credentials for another origin are never attached */
  cf.credential_origin = B; cf.authorization = good; c = mk(&cf);
  CHECK_ST(fetch_path(c, path, &f), OPDS_AUTH_REQUIRED);
  opds_client_free(c);
  return 0;
}
static int o1_auth_required(void) { CHECK(g_basic); return auth_flow("/auth/o1/root.xml", g_basic, "Basic"); }
static int o1_auth_cross_origin_redirect(void) {
  opds_client *c; opds_feed f; opds_config cf = cfg(); unsigned dropped, redirects; char path[700];
  CHECK(g_basic);
  cf.credential_origin = A; cf.authorization = g_basic; c = mk(&cf);
  snprintf(path, sizeof path, "/r/xorigin?to=%s/b/auth/root.xml", B);
  CHECK_ST(fetch_path(c, path, &f), OPDS_AUTH_REQUIRED);
  opds_client_stats(c, NULL, &redirects, &dropped);
  CHECK(redirects == 1 && dropped == 1);
  snprintf(path, sizeof path, "/r/xorigin?to=%s/b/public/root.xml", B);
  CHECK_ST(fetch_path(c, path, &f), OPDS_OK);
  opds_feed_free(&f);
  CHECK_ST(fetch_path(c, "/r/same-auth", &f), OPDS_OK); /* same origin: credentials survive the redirect */
  opds_feed_free(&f); opds_client_free(c);
  return 0;
}
static int bad_files(const char *const *files, size_t n, opds_status want) {
  opds_client *c; opds_config cf = cfg(); opds_feed f; char path[200];
  c = mk(&cf);
  for (size_t i = 0; i < n; i++) {
    snprintf(path, sizeof path, "/c/%s", files[i]);
    if (!i) in_file(files[i]);
    opds_client_begin_crawl(c);
    CHECK_ST(fetch_path(c, path, &f), want);
  }
  g_actual = opds_status_name(want);
  opds_client_free(c);
  return 0;
}
static int o1_bad_malformed_xml(void) {
  static const char *const f[] = {"o1/bad_malformed.xml", "o1/bad_prefix.xml", "o1/bad_dupattr.xml", "o1/bad_entity.xml"};
  return bad_files(f, 4, OPDS_FORMAT);
}
static int o1_bad_dtd_refused(void) {
  static const char *const f[] = {"o1/bad_dtd.xml"};
  return bad_files(f, 1, OPDS_FORMAT);
}
static int o1_bad_not_atom(void) {
  static const char *const f[] = {"o1/bad_html.xml", "o1/bad_ns.xml"};
  return bad_files(f, 2, OPDS_FORMAT);
}
static int o1_bad_required_fields(void) {
  static const char *const f[] = {"o1/bad_notitle.xml", "o1/bad_entry_notitle.xml", "o1/bad_nohref.xml"};
  return bad_files(f, 3, OPDS_FORMAT);
}
static int o1_encoding_entities(void) {
  opds_client *c; opds_feed f; opds_config cf = cfg();
  c = mk(&cf); in_file("o1/entities.xml");
  CHECK_ST(fetch_path(c, "/c/o1/entities.xml", &f), OPDS_OK);
  CHECK_STR(f.title, "\xe4\xb8\xad\xe6\x96\x87 & <raw> <t>");
  opds_feed_free(&f);
  CHECK_ST(fetch_path(c, "/c/o1/latin1.xml", &f), OPDS_UNSUPPORTED);
  opds_client_free(c);
  return 0;
}
static int budget_structure(const char *kind) {
  opds_client *c; opds_feed f; opds_config cf; char path[100];
  cf = cfg(); cf.limits.max_entries = 10; c = mk(&cf);
  snprintf(path, sizeof path, "/gen/%s/entries?n=50", kind);
  CHECK_ST(fetch_path(c, path, &f), OPDS_LIMIT); CHECK(strstr(E.message, "entry budget"));
  snprintf(path, sizeof path, "/gen/%s/entries?n=9", kind);
  CHECK_ST(fetch_path(c, path, &f), OPDS_OK); opds_feed_free(&f);
  opds_client_free(c);
  cf = cfg(); cf.limits.max_elements = 100; c = mk(&cf);
  snprintf(path, sizeof path, "/gen/%s/entries?n=200", kind);
  CHECK_ST(fetch_path(c, path, &f), OPDS_LIMIT);
  opds_client_free(c);
  cf = cfg(); cf.limits.max_depth = 16; c = mk(&cf);
  snprintf(path, sizeof path, "/gen/%s/deep?n=40", kind);
  CHECK_ST(fetch_path(c, path, &f), OPDS_LIMIT); CHECK(strstr(E.message, "nesting"));
  opds_client_free(c);
  if (!strcmp(kind, "o1")) {
    cf = cfg(); cf.limits.max_links_per_entry = 8; c = mk(&cf);
    CHECK_ST(fetch_path(c, "/gen/o1/links?n=20", &f), OPDS_LIMIT);
    opds_client_free(c);
  }
  return 0;
}
static int o1_budget_structure(void) { return budget_structure("o1"); }
static int budget_bytes(const char *kind, const char *big) {
  opds_client *c; opds_feed f; opds_config cf = cfg(); char path[100];
  cf.limits.max_feed_bytes = 2048; c = mk(&cf);
  CHECK_ST(fetch_path(c, big, &f), OPDS_LIMIT); CHECK(strstr(E.message, "2048"));
  opds_client_free(c);
  cf = cfg(); c = mk(&cf);
  CHECK_ST(fetch_path(c, "/huge-length/feed.xml", &f), OPDS_LIMIT); /* refused from Content-Length alone */
  opds_client_free(c);
  cf = cfg(); cf.limits.max_feed_bytes = 500; c = mk(&cf);
  CHECK_ST(fetch_path(c, "/chunked/feed.xml", &f), OPDS_LIMIT); /* no Content-Length: stopped mid-stream */
  opds_client_free(c);
  (void)kind; (void)path;
  return 0;
}
static int o1_budget_bytes(void) { return budget_bytes("o1", "/gen/o1/bytes?n=5000"); }
static int o1_sdk_budgets_untouched(void) {
  /* the module's budgets are its own: the SDK keeps its identity and ABI */
  CHECK_STR(exr_version(), EXR_VERSION); CHECK(exr_abi_version() == EXR_ABI_VERSION);
  { opds_limits l; opds_limits_defaults(&l); CHECK(l.max_feed_bytes == (4u << 20) && l.max_pages == 50 && l.max_redirects == 5); }
  g_actual = "ok";
  return 0;
}

/* ====================== OPDS 2 / JSON ====================== */
static int o2_nav_root(void) {
  opds_client *c; opds_feed f; opds_config cf = cfg(); const opds_entry *e; const opds_link *l;
  c = mk(&cf); in_file("o2/root.json");
  CHECK_ST(fetch_path(c, "/c/o2/root.json", &f), OPDS_OK);
  CHECK(f.version == 2); CHECK_STR(f.title, "Fixture Catalog"); CHECK_STR(f.id, "urn:opds-test:root2"); CHECK(f.entry_count == 4);
  l = opds_feed_find(&f, OPDS_REL_SEARCH); CHECK(l && (l->flags & OPDS_LINK_TEMPLATED)); CHECK_STR(l->href, U("/o2/search{?query,page}"));
  e = EN(&f, "All Books"); l = LK(e, 0); CHECK(l->kind == OPDS_REL_SUBSECTION); CHECK_STR(l->href, U("/o2/all?page=1"));
  e = EN(&f, "New Releases"); l = LK(e, 0); CHECK(l->kind == OPDS_REL_OTHER); CHECK_STR(l->rel, "current http://opds-spec.org/sort/new");
  e = EN(&f, "Vendor Shelf"); l = LK(e, 0); CHECK_STR(l->type, "application/vnd.vendor+json"); CHECK_STR(l->rel, "x-vendor/shelf");
  e = EN(&f, "No Rel"); l = LK(e, 0); CHECK(l->kind == OPDS_REL_SUBSECTION); CHECK_STR(l->href, U("/c/o2/plain.json"));
  opds_feed_free(&f); opds_client_free(c);
  return 0;
}
static int o2_publication_metadata(void) {
  opds_client *c; opds_feed f; opds_config cf = cfg(); const opds_entry *e;
  c = mk(&cf); in_file("o2/pubs.json");
  CHECK_ST(fetch_path(c, "/c/o2/pubs.json", &f), OPDS_OK);
  CHECK(f.entry_count == 3 && f.total_results == 3 && f.items_per_page == 10 && f.current_page == 1);
  e = EN(&f, "Localized Title"); CHECK(e && e->is_publication);
  CHECK(e->author_count == 1); CHECK_STR(e->authors[0], "Plain Author"); CHECK_STR(e->identifier, "urn:isbn:9780000000002");
  CHECK_STR(e->language, "fr"); CHECK_STR(e->publisher, "Pub Co"); CHECK_STR(e->summary, "Described."); CHECK_STR(e->updated, "2026-01-02T00:00:00Z");
  CHECK_STR(LK(e, 0)->href, U("/c/dl/book.epub")); CHECK_STR(LK(e, 1)->type, "application/pdf");
  CHECK(LK(e, 2)->kind == OPDS_REL_IMAGE && LK(e, 3)->kind == OPDS_REL_THUMBNAIL);
  e = EN(&f, "Two Authors"); CHECK(e && e->author_count == 2); CHECK_STR(e->authors[0], "A One"); CHECK_STR(e->authors[1], "B Two"); CHECK_STR(e->language, "en");
  e = EN(&f, "Object Author"); CHECK(e && e->author_count == 1); CHECK_STR(e->authors[0], "Obj Author");
  CHECK(LK(e, 0)->acq == OPDS_ACQ_GENERIC); CHECK_STR(LK(e, 0)->rel, "http://opds-spec.org/acquisition/x-future alternate");
  opds_feed_free(&f); opds_client_free(c);
  return 0;
}
static int o2_groups_facets(void) {
  opds_client *c; opds_feed f; opds_config cf = cfg(); const opds_entry *e;
  const opds_facet *facets; size_t facet_count;
  c = mk(&cf); in_file("o2/groups.json");
  CHECK_ST(fetch_path(c, "/c/o2/groups.json", &f), OPDS_OK);
  CHECK(f.entry_count == 3);
  e = EN(&f, "Top Nav"); CHECK(e && !e->group);
  e = EN(&f, "Featured One"); CHECK(e && e->is_publication); CHECK_STR(e->group, "Featured");
  e = EN(&f, "Group Nav"); CHECK(e && !e->is_publication); CHECK_STR(e->group, "Browse");
  facets = opds_feed_facets(&f, &facet_count);
  CHECK(facets && facet_count == 1 && facets[0].choice_count == 1);
  CHECK_STR(facets[0].title, "Language");
  CHECK_STR(facets[0].choices[0].link.title, "English");
  CHECK(strstr(facets[0].choices[0].link.href, "/o2/all?lang=en") != NULL);
  CHECK(!facets[0].choices[0].active && facets[0].choices[0].number_of_items == -1);
  opds_feed_free(&f); opds_client_free(c);
  return 0;
}
static int o2_pagination_follow(void) {
  opds_client *c; opds_feed f, n; opds_config cf = cfg(); int has = 0; size_t pages = 1, total;
  c = mk(&cf); in_file("o2/root.json");
  CHECK_ST(fetch_path(c, "/o2/all?page=1", &f), OPDS_OK);
  CHECK(f.total_results == 5 && f.items_per_page == 2); total = f.entry_count;
  for (;;) {
    CHECK_ST(opds_fetch_next(c, &f, NULL, &n, &has, &E), OPDS_OK);
    if (!has) break;
    opds_feed_free(&f); f = n; pages++; total += f.entry_count;
    if (pages == 2) { CHECK(f.current_page == 2); CHECK_STR(opds_feed_find(&f, OPDS_REL_PREVIOUS)->href, U("/o2/all?page=1")); }
  }
  CHECK(pages == 3 && total == 5);
  opds_feed_free(&f); opds_client_free(c);
  return 0;
}
static int o2_pagination_page_budget(void) { return pagination_budget("/o2/all?page=1", 0); }
static int o2_pagination_loop(void) { return pagination_loop("/o2/loop?page=1"); }
static int o2_search_template(void) {
  opds_client *c; opds_feed root, r; opds_config cf = cfg(); char url[1024], want[256];
  c = mk(&cf); in_file("o2/root.json");
  CHECK_ST(fetch_path(c, "/c/o2/root.json", &root), OPDS_OK);
  CHECK_ST(opds_search_url(c, &root, "story", 1, NULL, url, sizeof url, &E), OPDS_OK);
  CHECK_STR(url, U("/o2/search?query=story&page=1"));
  CHECK_ST(opds_fetch_feed(c, url, NULL, &r, &E), OPDS_OK);
  CHECK(r.entry_count == 2 && r.total_results == 3); CHECK_STR(r.entries[1].title, "Beta Story"); CHECK(opds_feed_find(&r, OPDS_REL_NEXT));
  opds_feed_free(&r);
  CHECK_ST(opds_search_url(c, &root, "story", 0, NULL, url, sizeof url, &E), OPDS_OK);
  CHECK_STR(url, U("/o2/search?query=story"));
  CHECK_ST(opds_search_url(c, &root, UNI_TERMS, 1, NULL, url, sizeof url, &E), OPDS_OK);
  CHECK_ST(opds_fetch_feed(c, url, NULL, &r, &E), OPDS_OK);
  snprintf(want, sizeof want, "Results for: %s", UNI_TERMS);
  CHECK_STR(r.title, want);
  opds_feed_free(&r); opds_feed_free(&root); opds_client_free(c);
  return 0;
}
static int o2_search_refusals(void) {
  opds_client *c; opds_feed f; opds_config cf = cfg(); char url[256];
  c = mk(&cf); in_file("o2/search_unsupported.json");
  CHECK_ST(fetch_path(c, "/c/o2/search_unsupported.json", &f), OPDS_OK);
  CHECK_ST(opds_search_url(c, &f, "x", 1, NULL, url, sizeof url, &E), OPDS_UNSUPPORTED); CHECK(strstr(E.message, "operator"));
  opds_feed_free(&f);
  CHECK_ST(fetch_path(c, "/c/o2/search_required.json", &f), OPDS_OK);
  CHECK_ST(opds_search_url(c, &f, "x", 1, NULL, url, sizeof url, &E), OPDS_UNSUPPORTED);
  opds_feed_free(&f); opds_client_free(c);
  return search_refusals("/c/o2/pubs.json", "/c/o2/search_notemplate.json");
}
static int o2_acquisition_selection(void) {
  opds_client *c; opds_feed f; opds_config cf = cfg(); const opds_entry *e; const opds_link *l;
  c = mk(&cf); in_file("o2/acq.json");
  CHECK_ST(fetch_path(c, "/c/o2/acq.json", &f), OPDS_OK);
  CHECK(f.entry_count == 7);
  e = EN(&f, "Open Book"); l = opds_entry_acquisition(e, NULL); CHECK(l && l->acq == OPDS_ACQ_OPEN_ACCESS); CHECK_STR(l->type, "application/pdf");
  l = opds_entry_acquisition(e, "application/epub+zip"); CHECK(l); CHECK_STR(l->href, U("/dl/book.epub"));
  CHECK(opds_link_acquirable(l, &E) == OPDS_OK);
  e = EN(&f, "Sample Only"); CHECK(!opds_entry_acquisition(e, NULL)); CHECK(opds_entry_acquisition(e, "application/epub+zip")->acq == OPDS_ACQ_SAMPLE);
  g_actual = "ok";
  opds_feed_free(&f); opds_client_free(c);
  return 0;
}
static int o2_acquisition_needs_host(void) {
  opds_client *c; opds_feed f; opds_config cf = cfg(); int rc;
  static const char *const t[] = {"Borrow Book", "LCP Book", "Adept Book", "Priced Book", "Priced Generic"};
  c = mk(&cf); in_file("o2/acq.json");
  CHECK_ST(fetch_path(c, "/c/o2/acq.json", &f), OPDS_OK);
  CHECK(EN(&f, "LCP Book")->links[0].flags & OPDS_LINK_PROTECTED);
  CHECK(EN(&f, "Adept Book")->links[0].flags & OPDS_LINK_INDIRECT);
  CHECK_STR(EN(&f, "Adept Book")->links[0].indirect_type, "application/epub+zip");
  CHECK(EN(&f, "Priced Book")->links[0].flags & OPDS_LINK_PRICED);
  rc = needs_host_checks(c, &f, t, 5, "o2_acquisition_needs_host");
  opds_feed_free(&f); opds_client_free(c);
  return rc;
}
static int o2_auth_bearer(void) {
  opds_client *c; opds_feed f; opds_config cf = cfg();
  CHECK(g_bearer);
  { int rc = auth_flow("/auth/o2/root.json", g_bearer, "Bearer"); if (rc) return rc; }
  c = mk(&cf);
  CHECK_ST(fetch_path(c, "/status/403", &f), OPDS_HTTP); CHECK(E.http_status == 403); /* forbidden is not "authenticate" */
  opds_client_free(c);
  return 0;
}
static int o2_bad_json_syntax(void) {
  static const char *const f[] = {"o2/bad_trunc.json", "o2/bad_trailing.json", "o2/bad_escape.json", "o2/bad_surrogate.json", "o2/bad_number.json", "o2/bad_array.json"};
  return bad_files(f, 6, OPDS_FORMAT);
}
static int o2_bad_structure(void) {
  static const char *const f[] = {"o2/bad_nometa.json", "o2/bad_nohref.json", "o2/bad_notitle.json", "o2/bad_notopds.json", "o2/bad_links_type.json"};
  return bad_files(f, 5, OPDS_FORMAT);
}
static int o2_budget_structure(void) { return budget_structure("o2"); }
static int o2_budget_bytes(void) { return budget_bytes("o2", "/gen/o2/bytes?n=5000"); }
static int o2_unicode_escapes(void) {
  opds_client *c; opds_feed f; opds_config cf = cfg();
  c = mk(&cf); in_file("o2/unicode.json");
  CHECK_ST(fetch_path(c, "/c/o2/unicode.json", &f), OPDS_OK);
  CHECK_STR(f.title, "Caf\xc3\xa9 \xf0\x9f\x98\x80");
  CHECK_STR(f.entries[0].title, "\xe4\xb8\xad\xe6\x96\x87\xe6\xa0\x87\xe9\xa2\x98 \"quoted\" \\ / \t");
  CHECK_STR(f.entries[0].authors[0], "\xc3\x85ngstr\xc3\xb6m");
  opds_feed_free(&f); opds_client_free(c);
  return 0;
}
static int type_negotiation(void) {
  opds_client *c; opds_feed f; opds_config cf = cfg();
  c = mk(&cf); in_file("o2/root.json");
  CHECK_ST(fetch_path(c, "/c/o1/root.xml?ctype=application%2Fopds%2Bjson", &f), OPDS_OK);
  CHECK(f.version == 1 && f.declared_type_mismatch); opds_feed_free(&f);
  CHECK_ST(fetch_path(c, "/c/o2/root.json?ctype=application%2Fatom%2Bxml", &f), OPDS_OK);
  CHECK(f.version == 2 && f.declared_type_mismatch); opds_feed_free(&f);
  CHECK_ST(fetch_path(c, "/c/o2/root.json", &f), OPDS_OK);
  CHECK(!f.declared_type_mismatch); opds_feed_free(&f);
  opds_client_free(c);
  return 0;
}

/* ====================== network behaviour ====================== */
static int n_redirect_chain(void) {
  opds_client *c; opds_feed f; opds_config cf = cfg(); unsigned red;
  c = mk(&cf);
  CHECK_ST(fetch_path(c, "/r/chain?n=3", &f), OPDS_OK);
  opds_client_stats(c, NULL, &red, NULL); CHECK(red == 3); CHECK_STR(f.title, "Fixture Catalog");
  opds_feed_free(&f); opds_client_free(c);
  return 0;
}
static int n_redirect_refusals(void) {
  opds_client *c; opds_feed f; opds_config cf = cfg();
  cf.limits.max_redirects = 2; c = mk(&cf);
  CHECK_ST(fetch_path(c, "/r/chain?n=5", &f), OPDS_LIMIT); CHECK(strstr(E.message, "redirects"));
  opds_client_begin_crawl(c);
  CHECK_ST(fetch_path(c, "/r/loop/a", &f), OPDS_LIMIT); CHECK(strstr(E.message, "loop"));
  opds_client_begin_crawl(c);
  CHECK_ST(fetch_path(c, "/r/ftp", &f), OPDS_UNSUPPORTED);
  opds_client_begin_crawl(c);
  CHECK_ST(fetch_path(c, "/r/nolocation", &f), OPDS_HTTP);
  opds_client_free(c);
  return 0;
}
static int n_timeout(void) {
  opds_client *c; opds_feed f; opds_config cf = cfg(); unsigned long long t0;
  cf.limits.timeout_ms = 300; c = mk(&cf); t0 = now_ms();
  CHECK_ST(fetch_path(c, "/slow/feed.xml?delay=3000", &f), OPDS_TIMEOUT);
  CHECK(now_ms() - t0 < 2500);
  opds_client_free(c);
  return 0;
}
static int n_cancel(void) {
  opds_client *c; opds_feed f; opds_config cf = cfg(); deadline d; opds_control ctl; unsigned long long t0;
  c = mk(&cf); t0 = now_ms(); d.start = t0; d.ms = 200; ctl.cancelled = cancel_after; ctl.context = &d;
  g_actual = opds_status_name(opds_fetch_feed(c, U("/slow/feed.xml?delay=3000"), &ctl, &f, &E));
  CHECK(E.code == OPDS_CANCELLED); CHECK(!strcmp(g_actual, "cancelled")); CHECK(now_ms() - t0 < 2500);
  /* cancelled before the first byte is sent */
  d.start = 0; opds_client_begin_crawl(c);
  CHECK_ST(opds_fetch_feed(c, U("/c/o1/root.xml"), &ctl, &f, &E), OPDS_CANCELLED);
  opds_client_free(c);
  return 0;
}
static int n_http_errors(void) {
  opds_client *c; opds_feed f; opds_config cf = cfg();
  c = mk(&cf);
  CHECK_ST(fetch_path(c, "/status/404", &f), OPDS_HTTP); CHECK(E.http_status == 404);
  CHECK_ST(opds_fetch_feed(c, U("/status/500"), NULL, &f, &E), OPDS_HTTP); CHECK(E.http_status == 500);
  CHECK_ST(opds_fetch_feed(c, U("/status/403"), NULL, &f, &E), OPDS_HTTP); CHECK(E.http_status == 403);
  opds_client_free(c);
  return 0;
}
static int n_https_needs_host(void) {
  opds_client *c; opds_feed f; opds_config cf = cfg(); opds_download_result r; char dst[800];
  c = mk(&cf);
  CHECK_ST(opds_fetch_feed(c, "https://127.0.0.1:9/feed", NULL, &f, &E), OPDS_NEEDS_HOST);
  case_dir("n_https_needs_host"); dest(dst, sizeof dst, "x.epub");
  CHECK_ST(opds_download_url(c, "https://127.0.0.1:9/x.epub", dst, NULL, NULL, &r, &E), OPDS_NEEDS_HOST);
  CHECK(count_files() == 0);
  opds_client_free(c);
  return 0;
}
static int n_chunked_truncated_refused(void) {
  opds_client *c; opds_feed f; opds_config cf = cfg();
  c = mk(&cf);
  CHECK_ST(fetch_path(c, "/chunked/feed.xml", &f), OPDS_OK); CHECK(f.entry_count == 3); opds_feed_free(&f);
  CHECK_ST(opds_fetch_feed(c, U("/trunc/feed.xml"), NULL, &f, &E), OPDS_IO);
  CHECK_ST(opds_fetch_feed(c, "http://127.0.0.1:1/refused", NULL, &f, &E), OPDS_IO);
  opds_client_free(c);
  return 0;
}
static int n_report_hygiene(void) {
  opds_client *c; opds_feed f; opds_config cf = cfg(); char red[300]; int leaked = 0;
  CHECK(g_basic);
  cf.credential_origin = A; cf.authorization = g_basic; c = mk(&cf);
  CHECK_ST(fetch_path(c, "/c/o1/root.xml?access_token=SUPERSECRET&page=2", &f), OPDS_OK);
  opds_feed_free(&f); opds_client_free(c);
  for (int i = 0; i < g_nreq; i++) if (strstr(g_req[i], "SUPERSECRET") || strstr(g_req[i], g_basic + 6)) leaked = 1;
  CHECK(!leaked); CHECK(g_nreq >= 1 && strstr(g_req[0], "access_token=REDACTED&page=2"));
  opds_redact_url("http://user:pw@h.example:8080/p?token=abc&x=1&Password=zz", red, sizeof red);
  CHECK_STR(red, "http://h.example:8080/p?token=REDACTED&x=1&Password=REDACTED");
  g_actual = "ok";
  return 0;
}
static int n_url_resolution(void) {
  static const char *const cases[][2] = {
    {"g:h", "g:h"}, {"g", "http://a/b/c/g"}, {"./g", "http://a/b/c/g"}, {"g/", "http://a/b/c/g/"}, {"/g", "http://a/g"},
    {"//g", "http://g"}, {"?y", "http://a/b/c/d;p?y"}, {"g?y", "http://a/b/c/g?y"}, {"#s", "http://a/b/c/d;p?q"},
    {"g#s", "http://a/b/c/g"}, {";x", "http://a/b/c/;x"}, {"", "http://a/b/c/d;p?q"}, {".", "http://a/b/c/"}, {"./", "http://a/b/c/"},
    {"..", "http://a/b/"}, {"../", "http://a/b/"}, {"../g", "http://a/b/g"}, {"../..", "http://a/"}, {"../../g", "http://a/g"},
    {"../../../g", "http://a/g"}, {"/./g", "http://a/g"}, {"g.", "http://a/b/c/g."}, {"./../g", "http://a/b/g"},
    {"g;x=1/./y", "http://a/b/c/g;x=1/y"}, {"g;x=1/../y", "http://a/b/c/y"}, {"a b", "http://a/b/c/a%20b"}, {"%41%zz", "http://a/b/c/%41%25zz"}};
  char out[256];
  for (size_t i = 0; i < sizeof cases / sizeof *cases; i++) {
    CHECK(opds_url_resolve("http://a/b/c/d;p?q", cases[i][0], out, sizeof out) == OPDS_OK);
    if (strcmp(out, cases[i][1])) FAIL("resolve('%s') = '%s', expected '%s'", cases[i][0], out, cases[i][1]);
  }
  g_actual = "ok";
  return 0;
}
static int n_template_expansion(void) {
  char out[256];
  CHECK(opds_template_expand("/s{?query}", "a b", 1, out, sizeof out, &E) == OPDS_OK); CHECK_STR(out, "/s?query=a%20b");
  CHECK(opds_template_expand("/s?x=1{&query}", "q", 1, out, sizeof out, &E) == OPDS_OK); CHECK_STR(out, "/s?x=1&query=q");
  CHECK(opds_template_expand("/s{?query,page}", "q", 0, out, sizeof out, &E) == OPDS_OK); CHECK_STR(out, "/s?query=q");
  CHECK(opds_template_expand("/s{?query,page}", "q", 4, out, sizeof out, &E) == OPDS_OK); CHECK_STR(out, "/s?query=q&page=4");
  CHECK(opds_template_expand("/s/{query}/p", "\xc3\xa9", 1, out, sizeof out, &E) == OPDS_OK); CHECK_STR(out, "/s/%C3%A9/p");
  CHECK(opds_template_expand("/s?q={searchTerms}&p={startPage?}&c={count?}&l={language?}", "t", 0, out, sizeof out, &E) == OPDS_OK);
  CHECK_STR(out, "/s?q=t&p=&c=&l=");
  CHECK(opds_template_expand("/s?q={searchTerms}&p={startPage}", "t", 0, out, sizeof out, &E) == OPDS_OK); CHECK_STR(out, "/s?q=t&p=1");
  CHECK(opds_template_expand("{+path}", "t", 1, out, sizeof out, &E) == OPDS_UNSUPPORTED);
  CHECK(opds_template_expand("/s/{unknown}", "t", 1, out, sizeof out, &E) == OPDS_UNSUPPORTED);
  CHECK(opds_template_expand("/s/{query", "t", 1, out, sizeof out, &E) == OPDS_FORMAT);
  CHECK(opds_template_expand("/s/{query}", NULL, 1, out, sizeof out, &E) == OPDS_ARGUMENT);
  CHECK(opds_template_expand("/s/{query}", "0123456789", 1, out, 8, &E) == OPDS_LIMIT);
  g_actual = "ok";
  return 0;
}

/* ====================== downloads ====================== */
static opds_download_options epub_opts(opds_existing_policy p) {
  opds_download_options o;
  memset(&o, 0, sizeof o);
  o.media_type = "application/epub+zip"; o.existing = p; o.verify = opds_sdk_verify;
  return o;
}
static int chain_download(int json) {
  opds_client *c; opds_feed root, page, next; opds_config cf = cfg(); char url[1024], dst[800], title[256], detail[200];
  opds_download_result r; opds_download_options o = epub_opts(OPDS_EXISTING_FAIL); const opds_entry *e = NULL; const opds_link *l; int has = 0; size_t parts = 0;
  char names[4][160];
  case_dir(json ? "d_e2e_opds2_epub_chain" : "d_e2e_opds1_epub_chain");
  c = mk(&cf); opds_client_begin_crawl(c);
  CHECK_ST(fetch_path(c, json ? "/c/o2/root.json" : "/c/o1/root.xml", &root), OPDS_OK);
  CHECK_ST(opds_search_url(c, &root, "story", 1, NULL, url, sizeof url, &E), OPDS_OK);
  CHECK_ST(opds_fetch_feed(c, url, NULL, &page, &E), OPDS_OK);
  CHECK(!EN(&page, "Gamma Story"));
  CHECK_ST(opds_fetch_next(c, &page, NULL, &next, &has, &E), OPDS_OK); CHECK(has);
  opds_feed_free(&page); page = next;
  e = EN(&page, "Gamma Story"); CHECK(e && e->is_publication);
  l = opds_entry_acquisition(e, "application/epub+zip"); CHECK(l);
  CHECK(strstr(l->href, "/dl/gamma%20story.epub"));
  dest(dst, sizeof dst, "gamma-story.epub");
  CHECK_ST(opds_download(c, l, dst, &o, NULL, &r, &E), OPDS_OK);
  CHECK(r.published && r.readable == OPDS_READ_OK && !r.already_present && r.bytes > 1000);
  CHECK_STR(r.sniffed_type, "application/epub+zip");
  CHECK(opds_sdk_read_title(dst, title, sizeof title, &parts, detail, sizeof detail) == OPDS_OK && parts > 0);
  CHECK(list_dir(CASE_DIR, names, 4) == 1);
  opds_feed_free(&page); opds_feed_free(&root); opds_client_free(c);
  g_actual = "ok";
  return 0;
}
static int d_e2e_opds1(void) { in_file("o1/root.xml"); return chain_download(0); }
static int d_e2e_opds2(void) { in_file("o2/root.json"); return chain_download(1); }

static int d_existing_policy(void) {
  opds_client *c; opds_config cf = cfg(); char dst[800]; opds_download_result r; opds_download_options o;
  case_dir("d_existing_policy"); dest(dst, sizeof dst, "keep.epub");
  CHECK(write_file(dst, "old contents")); c = mk(&cf);
  o = epub_opts(OPDS_EXISTING_FAIL);
  CHECK_ST(opds_download_url(c, U("/dl/book.epub"), dst, &o, NULL, &r, &E), OPDS_EXISTS);
  CHECK(file_is(dst, "old contents")); CHECK(count_files() == 1); CHECK(!r.published);
  o = epub_opts(OPDS_EXISTING_REPLACE);
  CHECK_ST(opds_download_url(c, U("/dl/book.epub"), dst, &o, NULL, &r, &E), OPDS_OK);
  CHECK(r.published && !r.already_present && !file_is(dst, "old contents")); CHECK(count_files() == 1);
  opds_client_free(c);
  return 0;
}
static int d_repeat_acquisition(void) {
  opds_client *c; opds_config cf = cfg(); char dst[800], first[65]; opds_download_result r; opds_download_options o = epub_opts(OPDS_EXISTING_FAIL);
  case_dir("d_repeat_acquisition"); dest(dst, sizeof dst, "again.epub"); c = mk(&cf);
  CHECK_ST(opds_download_url(c, U("/dl/book.epub"), dst, &o, NULL, &r, &E), OPDS_OK);
  CHECK(r.published && !r.already_present); snprintf(first, sizeof first, "%s", r.sha256);
  CHECK_ST(opds_download_url(c, U("/dl/book.epub"), dst, &o, NULL, &r, &E), OPDS_OK);
  CHECK(r.already_present && r.published); CHECK_STR(r.sha256, first); CHECK(count_files() == 1);
  o = epub_opts(OPDS_EXISTING_REPLACE);
  CHECK_ST(opds_download_url(c, U("/r/dl"), dst, &o, NULL, &r, &E), OPDS_OK); /* same book through a redirect */
  CHECK(r.already_present); CHECK_STR(r.sha256, first);
  /* a different payload with the same name is a conflict under the default policy */
  o = epub_opts(OPDS_EXISTING_FAIL); o.verify = NULL;
  CHECK_ST(opds_download_url(c, U("/dl/different.epub"), dst, &o, NULL, &r, &E), OPDS_EXISTS);
  CHECK(count_files() == 1);
  opds_client_free(c);
  return 0;
}
static int d_cancel_midstream(void) {
  opds_client *c; opds_config cf = cfg(); char dst[800]; opds_download_result r; opds_download_options o = epub_opts(OPDS_EXISTING_FAIL);
  deadline d; opds_control ctl; unsigned long long t0;
  case_dir("d_cancel_midstream"); dest(dst, sizeof dst, "cancel.epub"); c = mk(&cf);
  t0 = now_ms(); d.start = t0; d.ms = 400; ctl.cancelled = cancel_after; ctl.context = &d;
  CHECK_ST(opds_download_url(c, U("/dl/slow.epub?stall=4000"), dst, &o, &ctl, &r, &E), OPDS_CANCELLED);
  CHECK(now_ms() - t0 < 3000); CHECK(!file_exists(dst)); CHECK(count_files() == 0); CHECK(!r.published);
  opds_client_free(c);
  return 0;
}
static int d_failure_leaves_nothing(void) {
  opds_client *c; opds_config cf = cfg(); char dst[800]; opds_download_result r; opds_download_options o = epub_opts(OPDS_EXISTING_FAIL);
  case_dir("d_failure_leaves_nothing"); dest(dst, sizeof dst, "fail.epub"); c = mk(&cf);
  CHECK_ST(opds_download_url(c, U("/dl/trunc.epub"), dst, &o, NULL, &r, &E), OPDS_IO);
  CHECK(!file_exists(dst) && count_files() == 0);
  CHECK_ST(opds_download_url(c, U("/dl/missing.epub"), dst, &o, NULL, &r, &E), OPDS_HTTP);
  CHECK(E.http_status == 404 && count_files() == 0);
  CHECK_ST(opds_download_url(c, U("/dl/empty.epub"), dst, &o, NULL, &r, &E), OPDS_FORMAT);
  CHECK(count_files() == 0);
  opds_client_free(c);
  cf.limits.timeout_ms = 300; c = mk(&cf); /* body stall -> inactivity timeout */
  CHECK_ST(opds_download_url(c, U("/dl/slow.epub?stall=3000"), dst, &o, NULL, &r, &E), OPDS_TIMEOUT);
  CHECK(count_files() == 0);
  opds_client_free(c);
  return 0;
}
static int d_budget_rejected(void) {
  opds_client *c; opds_config cf = cfg(); char dst[800]; opds_download_result r; opds_download_options o = epub_opts(OPDS_EXISTING_FAIL);
  case_dir("d_budget_rejected"); dest(dst, sizeof dst, "big.epub");
  cf.limits.max_download_bytes = 1000; c = mk(&cf);
  CHECK_ST(opds_download_url(c, U("/dl/book.epub"), dst, &o, NULL, &r, &E), OPDS_LIMIT); /* from Content-Length */
  CHECK(count_files() == 0);
  opds_client_free(c);
  cf.limits.max_download_bytes = 100000; c = mk(&cf);
  o.media_type = NULL; o.verify = NULL;
  CHECK_ST(opds_download_url(c, U("/dl/stream.bin"), dst, &o, NULL, &r, &E), OPDS_LIMIT); /* chunked: stopped mid-stream */
  CHECK(count_files() == 0);
  o.max_bytes = 50; CHECK_ST(opds_download_url(c, U("/dl/book.epub"), dst, &o, NULL, &r, &E), OPDS_LIMIT); /* per-call budget */
  CHECK(count_files() == 0);
  opds_client_free(c);
  return 0;
}
static int d_type_mismatch(void) {
  opds_client *c; opds_config cf = cfg(); char dst[800]; opds_download_result r; opds_download_options o = epub_opts(OPDS_EXISTING_FAIL);
  case_dir("d_type_mismatch"); dest(dst, sizeof dst, "m.epub"); c = mk(&cf);
  CHECK_ST(opds_download_url(c, U("/dl/html-as-epub.epub"), dst, &o, NULL, &r, &E), OPDS_MISMATCH);
  CHECK_STR(r.sniffed_type, "text/html"); CHECK(count_files() == 0);
  CHECK_ST(opds_download_url(c, U("/dl/pdf-as-epub.epub"), dst, &o, NULL, &r, &E), OPDS_MISMATCH);
  CHECK_STR(r.sniffed_type, "application/pdf"); CHECK(count_files() == 0);
  o.media_type = "application/pdf";
  CHECK_ST(opds_download_url(c, U("/dl/book.epub"), dst, &o, NULL, &r, &E), OPDS_MISMATCH); /* EPUB declared as PDF */
  CHECK(count_files() == 0);
  opds_client_free(c);
  return 0;
}
static int d_header_type_disagrees(void) {
  opds_client *c; opds_config cf = cfg(); char dst[800]; opds_download_result r; opds_download_options o = epub_opts(OPDS_EXISTING_FAIL);
  case_dir("d_header_type_disagrees"); dest(dst, sizeof dst, "h.epub"); c = mk(&cf);
  CHECK_ST(opds_download_url(c, U("/dl/plain-type.epub"), dst, &o, NULL, &r, &E), OPDS_OK);
  CHECK(r.header_type_mismatch && r.published && r.readable == OPDS_READ_OK); CHECK_STR(r.sniffed_type, "application/epub+zip");
  opds_client_free(c);
  return 0;
}
static int d_corrupt_not_readable(void) {
  opds_client *c; opds_config cf = cfg(); char dst[800]; opds_download_result r; opds_download_options o = epub_opts(OPDS_EXISTING_FAIL);
  case_dir("d_corrupt_not_readable"); dest(dst, sizeof dst, "corrupt.epub"); c = mk(&cf);
  CHECK_ST(opds_download_url(c, U("/dl/corrupt.epub"), dst, &o, NULL, &r, &E), OPDS_UNREADABLE);
  CHECK(r.readable == OPDS_READ_FAILED && !r.published); CHECK(r.bytes > 100); CHECK_STR(r.sniffed_type, "application/epub+zip");
  CHECK(!file_exists(dst) && count_files() == 0);
  o.verify = NULL; /* without a verifier the bytes are kept but never reported as readable */
  CHECK_ST(opds_download_url(c, U("/dl/corrupt.epub"), dst, &o, NULL, &r, &E), OPDS_OK);
  CHECK(r.published && r.readable == OPDS_READ_UNKNOWN);
  opds_client_free(c);
  return 0;
}
static int d_pdf_unverified(void) {
  opds_client *c; opds_config cf = cfg(); char dst[800], head[8] = {0}; opds_download_result r; opds_download_options o = epub_opts(OPDS_EXISTING_FAIL);
  FILE *f;
  case_dir("d_pdf_unverified"); dest(dst, sizeof dst, "book.pdf"); c = mk(&cf);
  o.media_type = "application/pdf";
  CHECK_ST(opds_download_url(c, U("/dl/book.pdf"), dst, &o, NULL, &r, &E), OPDS_OK);
  CHECK(r.published && r.readable == OPDS_READ_UNKNOWN); CHECK_STR(r.sniffed_type, "application/pdf");
  f = fopen(dst, "rb"); CHECK(f); CHECK(fread(head, 1, 5, f) == 5); fclose(f); CHECK(!memcmp(head, "%PDF-", 5));
  CHECK(count_files() == 1);
  opds_client_free(c);
  return 0;
}
static int d_destination_names(void) {
  opds_client *c; opds_config cf = cfg(); char dst[800]; opds_download_result r; opds_download_options o = epub_opts(OPDS_EXISTING_FAIL); unsigned before, after;
  static const char *const bad[] = {"..", "CON.epub", "a:b.epub", "x.", "q?.epub", "nul", "LPT1.txt"};
  case_dir("d_destination_names"); c = mk(&cf);
  opds_client_stats(c, &before, NULL, NULL);
  for (size_t i = 0; i < sizeof bad / sizeof *bad; i++) {
    dest(dst, sizeof dst, bad[i]);
    if (opds_download_url(c, U("/dl/book.epub"), dst, &o, NULL, &r, &E) != OPDS_ARGUMENT) FAIL("name '%s' was not refused", bad[i]);
  }
  snprintf(dst, sizeof dst, "%s", CASE_DIR);
  CHECK_ST(opds_download_url(c, U("/dl/book.epub"), dst, &o, NULL, &r, &E), OPDS_ARGUMENT); /* directory */
  snprintf(dst, sizeof dst, "%s/missing-dir/a.epub", CASE_DIR);
  CHECK_ST(opds_download_url(c, U("/dl/book.epub"), dst, &o, NULL, &r, &E), OPDS_ARGUMENT);
  opds_client_stats(c, &after, NULL, NULL); CHECK(before == after); CHECK(count_files() == 0);
#ifndef _WIN32
  { char target[800], link[800];
    dest(target, sizeof target, "target.epub"); dest(link, sizeof link, "link.epub");
    CHECK(write_file(target, "precious"));
    CHECK(symlink("target.epub", link) == 0);
    o.existing = OPDS_EXISTING_REPLACE;
    CHECK_ST(opds_download_url(c, U("/dl/book.epub"), link, &o, NULL, &r, &E), OPDS_ARGUMENT);
    CHECK(file_is(target, "precious")); CHECK(count_files() == 2); }
#else
  snprintf(g_note, sizeof g_note, "symlink alias sub-case is POSIX-only; names, directory and missing-directory refusals ran");
#endif
  opds_client_free(c);
  return 0;
}
static int d_authenticated_download(void) {
  opds_client *c; opds_config cf = cfg(); char dst[800], to[700]; opds_download_result r; opds_download_options o = epub_opts(OPDS_EXISTING_FAIL); unsigned dropped;
  CHECK(g_basic);
  case_dir("d_authenticated_download"); dest(dst, sizeof dst, "auth.epub");
  c = mk(&cf);
  CHECK_ST(opds_download_url(c, U("/auth/dl/book.epub"), dst, &o, NULL, &r, &E), OPDS_AUTH_REQUIRED);
  CHECK(count_files() == 0); opds_client_free(c);
  cf.credential_origin = A; cf.authorization = g_basic; c = mk(&cf);
  CHECK_ST(opds_download_url(c, U("/auth/dl/book.epub"), dst, &o, NULL, &r, &E), OPDS_OK);
  CHECK(r.published && r.readable == OPDS_READ_OK);
  snprintf(to, sizeof to, "/r/xorigin?to=%s/b/public/book.epub", B);
  dest(dst, sizeof dst, "cross.epub");
  CHECK_ST(opds_download_url(c, U(to), dst, &o, NULL, &r, &E), OPDS_OK);
  opds_client_stats(c, NULL, NULL, &dropped); CHECK(dropped == 1);
  snprintf(to, sizeof to, "/r/xorigin?to=%s/b/auth/root.xml", B);
  dest(dst, sizeof dst, "cross2.epub"); o.media_type = NULL; o.verify = NULL;
  CHECK_ST(opds_download_url(c, U(to), dst, &o, NULL, &r, &E), OPDS_AUTH_REQUIRED); /* foreign origin never sees the credential */
  CHECK(!file_exists(dst)); CHECK(count_files() == 2);
  opds_client_free(c);
  return 0;
}
static int d_redirected_download(void) {
  opds_client *c; opds_config cf = cfg(); char dst[800]; opds_download_result r; opds_download_options o = epub_opts(OPDS_EXISTING_FAIL); unsigned red;
  case_dir("d_redirected_download"); dest(dst, sizeof dst, "redir.epub"); c = mk(&cf);
  CHECK_ST(opds_download_url(c, U("/r/dl"), dst, &o, NULL, &r, &E), OPDS_OK);
  opds_client_stats(c, NULL, &red, NULL); CHECK(red == 1 && r.published && r.readable == OPDS_READ_OK);
  opds_client_free(c);
  return 0;
}

/* Verification arms cancellation after network I/O has completed. */
typedef struct { unsigned checks, cancel_at; int armed; opds_status verifier_status; } late_cancel;
static int late_cancelled(void *context) {
  late_cancel *c = (late_cancel *)context;
  return c->armed && ++c->checks >= c->cancel_at;
}
static opds_status arm_cancel(void *context, const char *path, const char *type, char *detail, size_t cap) {
  late_cancel *c = (late_cancel *)context;
  opds_status st = opds_sdk_verify(NULL, path, type, detail, cap);
  c->armed = 1;c->checks = 0;
  return st == OPDS_OK ? c->verifier_status : st;
}
static int d_cancel_after_verifier(void) {
  opds_config cf = cfg();opds_client *c = mk(&cf);char dst[800];
  opds_download_result r;opds_download_options o = epub_opts(OPDS_EXISTING_FAIL);
  late_cancel late = {0,1,0,OPDS_OK};opds_control ctl = {late_cancelled,&late};
  case_dir("d_cancel_after_verifier");dest(dst,sizeof dst,"absent.epub");
  o.verify = arm_cancel;o.verify_context = &late;
  CHECK_ST(opds_download_url(c,U("/dl/book.epub"),dst,&o,&ctl,&r,&E),OPDS_CANCELLED);
  CHECK(!r.published && !r.already_present && !file_exists(dst) && count_files()==0);
  dest(dst,sizeof dst,"keep.epub");CHECK(write_file(dst,"existing original"));
  o.existing = OPDS_EXISTING_REPLACE;late.armed = 0;
  CHECK_ST(opds_download_url(c,U("/dl/book.epub"),dst,&o,&ctl,&r,&E),OPDS_CANCELLED);
  CHECK(file_is(dst,"existing original") && count_files()==1 && !r.published);
  /* A verifier can itself report cancellation without a control callback. */
  late.armed = 0;late.verifier_status = OPDS_CANCELLED;
  CHECK_ST(opds_download_url(c,U("/dl/book.epub"),dst,&o,NULL,&r,&E),OPDS_CANCELLED);
  CHECK(file_is(dst,"existing original") && count_files()==1 && !r.published);
  opds_client_free(c);return 0;
}
static int d_cancel_existing_comparison(void) {
  opds_config cf = cfg();opds_client *c = mk(&cf);char dst[800],before[65];size_t size;char *data;
  opds_download_result r;opds_download_options o = epub_opts(OPDS_EXISTING_FAIL);
  late_cancel late = {0,3,0,OPDS_OK};opds_control ctl = {late_cancelled,&late};
  case_dir("d_cancel_existing_comparison");dest(dst,sizeof dst,"same.epub");
  CHECK_ST(opds_download_url(c,U("/dl/book.epub"),dst,&o,NULL,&r,&E),OPDS_OK);
  snprintf(before,sizeof before,"%s",r.sha256);o.verify = arm_cancel;o.verify_context = &late;
  CHECK_ST(opds_download_url(c,U("/dl/book.epub"),dst,&o,&ctl,&r,&E),OPDS_CANCELLED);
  CHECK(late.checks==3 && !r.published && !r.already_present && count_files()==1);
  data = read_file(dst,&size);CHECK(data);opds_sha256_hex(data,size,r.sha256);free(data);
  CHECK_STR(before,r.sha256);opds_client_free(c);return 0;
}
static int d_cancel_before_publication(void) {
  opds_config cf = cfg();opds_client *c = mk(&cf);char dst[800];
  opds_download_result r;opds_download_options o = epub_opts(OPDS_EXISTING_FAIL);
  late_cancel late = {0,2,0,OPDS_OK};opds_control ctl = {late_cancelled,&late};
  case_dir("d_cancel_before_publication");dest(dst,sizeof dst,"absent.epub");
  o.verify = arm_cancel;o.verify_context = &late;
  CHECK_ST(opds_download_url(c,U("/dl/book.epub"),dst,&o,&ctl,&r,&E),OPDS_CANCELLED);
  CHECK(late.checks==2 && !r.published && !file_exists(dst) && count_files()==0);
  opds_client_free(c);return 0;
}

/* ---- consumer example (invoked by tools/check_opds.py, not here) ---- */

typedef struct { const char *id, *protocol, *category, *request_class, *expected; int (*fn)(void); } tcase;
static const tcase CASES[] = {
  {"o1_nav_root", "opds1", "navigation", "feed", "ok", o1_nav_root},
  {"o1_xml_base_relative", "opds1", "navigation", "feed", "ok", o1_xml_base_relative},
  {"o1_atom_namespaces", "opds1", "navigation", "feed", "ok", o1_atom_namespaces},
  {"o1_pagination_follow", "opds1", "pagination", "feed", "ok", o1_pagination_follow},
  {"o1_pagination_page_budget", "opds1", "pagination", "feed", "limit", o1_pagination_page_budget},
  {"o1_pagination_loop", "opds1", "pagination", "feed", "limit", o1_pagination_loop},
  {"o1_search_opensearch", "opds1", "search", "opensearch+feed", "ok", o1_search_opensearch},
  {"o1_search_direct_template", "opds1", "search", "feed", "ok", o1_search_direct_template},
  {"o1_search_refusals", "opds1", "search", "feed", "unsupported", o1_search_refusals},
  {"o1_acquisition_selection", "opds1", "acquisition", "feed", "ok", o1_acquisition_selection},
  {"o1_acquisition_needs_host", "opds1", "acquisition", "feed", "needs_host", o1_acquisition_needs_host},
  {"o1_auth_required", "opds1", "auth", "feed", "auth_required", o1_auth_required},
  {"o1_auth_cross_origin_redirect", "opds1", "auth", "feed", "auth_required", o1_auth_cross_origin_redirect},
  {"o1_bad_malformed_xml", "opds1", "bad_data", "feed", "format", o1_bad_malformed_xml},
  {"o1_bad_dtd_refused", "opds1", "bad_data", "feed", "format", o1_bad_dtd_refused},
  {"o1_bad_not_atom", "opds1", "bad_data", "feed", "format", o1_bad_not_atom},
  {"o1_bad_required_fields", "opds1", "bad_data", "feed", "format", o1_bad_required_fields},
  {"o1_encoding_entities", "opds1", "bad_data", "feed", "unsupported", o1_encoding_entities},
  {"o1_budget_structure", "opds1", "budget", "feed", "limit", o1_budget_structure},
  {"o1_budget_bytes", "opds1", "budget", "feed", "limit", o1_budget_bytes},
  {"o2_nav_root", "opds2", "navigation", "feed", "ok", o2_nav_root},
  {"o2_publication_metadata", "opds2", "navigation", "feed", "ok", o2_publication_metadata},
  {"o2_groups_facets", "opds2", "navigation", "feed", "ok", o2_groups_facets},
  {"o2_pagination_follow", "opds2", "pagination", "feed", "ok", o2_pagination_follow},
  {"o2_pagination_page_budget", "opds2", "pagination", "feed", "limit", o2_pagination_page_budget},
  {"o2_pagination_loop", "opds2", "pagination", "feed", "limit", o2_pagination_loop},
  {"o2_search_template", "opds2", "search", "feed", "ok", o2_search_template},
  {"o2_search_refusals", "opds2", "search", "feed", "unsupported", o2_search_refusals},
  {"o2_acquisition_selection", "opds2", "acquisition", "feed", "ok", o2_acquisition_selection},
  {"o2_acquisition_needs_host", "opds2", "acquisition", "feed", "needs_host", o2_acquisition_needs_host},
  {"o2_auth_bearer", "opds2", "auth", "feed", "auth_required", o2_auth_bearer},
  {"o2_bad_json_syntax", "opds2", "bad_data", "feed", "format", o2_bad_json_syntax},
  {"o2_bad_structure", "opds2", "bad_data", "feed", "format", o2_bad_structure},
  {"o2_unicode_escapes", "opds2", "bad_data", "feed", "ok", o2_unicode_escapes},
  {"o2_budget_structure", "opds2", "budget", "feed", "limit", o2_budget_structure},
  {"o2_budget_bytes", "opds2", "budget", "feed", "limit", o2_budget_bytes},
  {"x_type_negotiation", "both", "bad_data", "feed", "ok", type_negotiation},
  {"x_sdk_budgets_untouched", "both", "budget", "none", "ok", o1_sdk_budgets_untouched},
  {"x_url_resolution", "both", "navigation", "none", "ok", n_url_resolution},
  {"x_template_expansion", "both", "search", "none", "ok", n_template_expansion},
  {"n_redirect_chain", "net", "network", "feed", "ok", n_redirect_chain},
  {"n_redirect_refusals", "net", "network", "feed", "limit", n_redirect_refusals},
  {"n_timeout", "net", "network", "feed", "timeout", n_timeout},
  {"n_cancel", "net", "network", "feed", "cancelled", n_cancel},
  {"n_http_errors", "net", "network", "feed", "http", n_http_errors},
  {"n_https_needs_host", "net", "network", "feed+download", "needs_host", n_https_needs_host},
  {"n_chunked_truncated_refused", "net", "network", "feed", "io", n_chunked_truncated_refused},
  {"n_report_hygiene", "net", "auth", "feed", "ok", n_report_hygiene},
  {"d_e2e_opds1_epub_chain", "opds1", "download", "feed+opensearch+download", "ok", d_e2e_opds1},
  {"d_e2e_opds2_epub_chain", "opds2", "download", "feed+search+download", "ok", d_e2e_opds2},
  {"d_existing_policy", "both", "download", "download", "exists", d_existing_policy},
  {"d_repeat_acquisition", "both", "download", "download", "exists", d_repeat_acquisition},
  {"d_cancel_midstream", "both", "download", "download", "cancelled", d_cancel_midstream},
  {"d_failure_leaves_nothing", "both", "download", "download", "timeout", d_failure_leaves_nothing},
  {"d_budget_rejected", "both", "download", "download", "limit", d_budget_rejected},
  {"d_type_mismatch", "both", "download", "download", "mismatch", d_type_mismatch},
  {"d_header_type_disagrees", "both", "download", "download", "ok", d_header_type_disagrees},
  {"d_corrupt_not_readable", "both", "download", "download", "ok", d_corrupt_not_readable},
  {"d_pdf_unverified", "both", "download", "download", "ok", d_pdf_unverified},
  {"d_destination_names", "both", "download", "none", "argument", d_destination_names},
  {"d_authenticated_download", "both", "download", "download", "auth_required", d_authenticated_download},
  {"d_redirected_download", "both", "download", "download", "ok", d_redirected_download},
  {"d_cancel_after_verifier", "both", "download", "download", "cancelled", d_cancel_after_verifier},
  {"d_cancel_existing_comparison", "both", "download", "download", "cancelled", d_cancel_existing_comparison},
  {"d_cancel_before_publication", "both", "download", "download", "cancelled", d_cancel_before_publication},
};

static void jstr(FILE *f, const char *s) {
  fputc('"', f);
  for (; s && *s; s++) {
    unsigned char c = (unsigned char)*s;
    if (c == '"' || c == '\\') { fputc('\\', f); fputc(c, f); }
    else if (c < 0x20) fprintf(f, "\\u%04x", c);
    else fputc(c, f);
  }
  fputc('"', f);
}

static int test_main(int argc, char **argv) {
  const char *out = NULL, *only = NULL;
  FILE *f;
  size_t n = sizeof CASES / sizeof *CASES, passed = 0, failed = 0;
  for (int i = 1; i + 1 < argc; i += 2) {
    if (!strcmp(argv[i], "--a")) snprintf(A, sizeof A, "%s", argv[i + 1]);
    else if (!strcmp(argv[i], "--b")) snprintf(B, sizeof B, "%s", argv[i + 1]);
    else if (!strcmp(argv[i], "--corpus")) snprintf(CORPUS, sizeof CORPUS, "%s", argv[i + 1]);
    else if (!strcmp(argv[i], "--work")) snprintf(WORK, sizeof WORK, "%s", argv[i + 1]);
    else if (!strcmp(argv[i], "--out")) out = argv[i + 1];
    else if (!strcmp(argv[i], "--only")) only = argv[i + 1];
    else { fprintf(stderr, "unknown option %s\n", argv[i]); return 2; }
  }
  if (!A[0] || !B[0] || !CORPUS[0] || !WORK[0] || !out) { fprintf(stderr, "usage: opds_test --a URL --b URL --corpus DIR --work DIR --out FILE\n"); return 2; }
  g_basic = getenv("OPDS_TEST_BASIC"); g_bearer = getenv("OPDS_TEST_BEARER");
  f = fopen(out, "wb");
  if (!f) { fprintf(stderr, "cannot write %s\n", out); return 2; }
  fprintf(f, "{\"schema\":1,\"module\":\"opds-client\",\"module_version\":\"%s\",\"sdk_version\":\"%s\",\"sdk_abi\":%u,\"platform\":\"%s\",\"cases\":[\n",
          OPDS_MODULE_VERSION, exr_version(), (unsigned)exr_abi_version(),
#ifdef _WIN32
          "windows"
#else
          "posix"
#endif
  );
  for (size_t i = 0; i < n; i++) {
    const tcase *t = &CASES[i];
    int rc;
    char joined[96 * 250];
    unsigned long long t0;
    if (only && strcmp(only, t->id)) continue;
    g_note[0] = 0; g_actual = ""; g_nreq = 0; g_input_set = 0; memset(&E, 0, sizeof E);
    t0 = now_ms();
    rc = t->fn();
    if (!g_input_set) {
      joined[0] = 0;
      for (int k = 0; k < g_nreq; k++) { size_t l = strlen(joined); snprintf(joined + l, sizeof joined - l, "%s\n", g_req[k]); }
      if (!joined[0]) snprintf(joined, sizeof joined, "%s", t->id);
      opds_sha256_hex(joined, strlen(joined), g_input_hash);
    }
    if (rc == 0) passed++; else failed++;
    fprintf(f, "%s  {\"id\":", i && (!only || 1) && (passed + failed) > 1 ? ",\n" : "");
    jstr(f, t->id); fprintf(f, ",\"protocol\":"); jstr(f, t->protocol); fprintf(f, ",\"category\":"); jstr(f, t->category);
    fprintf(f, ",\"request_class\":"); jstr(f, t->request_class); fprintf(f, ",\"input_sha256\":\"%s\",\"expected\":", g_input_hash); jstr(f, t->expected);
    fprintf(f, ",\"last_status\":"); jstr(f, g_actual[0] ? g_actual : (rc == 0 ? t->expected : "check_failed"));
    fprintf(f, ",\"passed\":%s,\"note\":", rc == 0 ? "true" : "false"); jstr(f, g_note);
    fprintf(f, ",\"elapsed_ms\":%llu,\"requests\":[", now_ms() - t0);
    for (int k = 0; k < g_nreq; k++) { if (k) fputc(',', f); jstr(f, g_req[k]); }
    fprintf(f, "]}");
    fflush(f);
    printf("%s %s%s%s\n", rc == 0 ? "PASS" : "FAIL", t->id, rc ? " : " : "", rc ? g_note : "");
  }
  fprintf(f, "\n],\"summary\":{\"total\":%zu,\"passed\":%zu,\"failed\":%zu}}\n", passed + failed, passed, failed);
  fclose(f);
  printf("%zu passed, %zu failed\n", passed, failed);
  return failed ? 1 : 0;
}

#define example_main test_main
#include "../../extras/opds/examples/entry.h"
