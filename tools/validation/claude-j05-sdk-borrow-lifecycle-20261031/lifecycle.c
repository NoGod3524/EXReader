/* SPDX-License-Identifier: MIT
   J05: real installed SDK 3.42 library/source/pager borrow lifecycle (C ABI, Linux).
   Observation of the underlying resource is the OS: open file descriptors of the
   library database (main/-wal/-shm/-journal) read from /proc/self/fd. Actions only. */
#include "exreader.h"
#include <dirent.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static const char *DB;
static const char *FONT;
static int seq, failures;
static char TEXT[400000];
static size_t TEXT_LEN;

static int open_fds(void) {
  DIR *d = opendir("/proc/self/fd"); struct dirent *e; int n = 0; size_t len = strlen(DB);
  if (!d) return -1;
  while ((e = readdir(d))) {
    char link[600], target[1024]; ssize_t r;
    snprintf(link, sizeof link, "/proc/self/fd/%s", e->d_name);
    r = readlink(link, target, sizeof target - 1);
    if (r <= 0) continue;
    target[r] = 0;
    if (!strncmp(target, DB, len) && (target[len] == 0 || target[len] == '-')) n++;
  }
  closedir(d); return n;
}
static void ev(const char *scenario, const char *op, int status, const char *note) {
  printf("{\"seq\":%d,\"scenario\":\"%s\",\"op\":\"%s\",\"status\":%d,\"db_fds\":%d,\"note\":\"%s\"}\n",
         ++seq, scenario, op, status, open_fds(), note);
}
static void check(const char *scenario, const char *what, int ok) {
  printf("{\"seq\":%d,\"scenario\":\"%s\",\"check\":\"%s\",\"pass\":%s,\"db_fds\":%d}\n",
         ++seq, scenario, what, ok ? "true" : "false", open_fds());
  if (!ok) failures++;
}
static void remove_db(void) {
  char p[700]; const char *s[] = {"", "-wal", "-shm", "-journal"};
  for (int i = 0; i < 4; i++) { snprintf(p, sizeof p, "%s%s", DB, s[i]); unlink(p); }
}
static int cancel_now(void *ctx) { return *(int *)ctx; }

typedef struct { exr_library *lib; int64_t id; } fixture;
static int open_fixture(const char *sc, fixture *f, const char *title) {
  exr_error e = {0}; int created = 0;
  remove_db();
  if (exr_library_open(DB, &f->lib, &e) != EXR_OK) return 0;
  if (exr_library_import_unique(f->lib, EXR_TXT, TEXT, TEXT_LEN, title, &f->id, &created, &e) != EXR_OK || !created) return 0;
  ev(sc, "open+import", 0, "library open, original stored");
  return 1;
}
static int read_check(exr_source *s) {
  char b[64]; size_t n = s->size < sizeof b ? (size_t)s->size : sizeof b;
  return s->read_at(s->context, 0, b, n) == n && !memcmp(b, TEXT, n);
}
static int make_pager(exr_library *lib, int64_t id, exr_font *font, exr_pager **p, int *cancel) {
  exr_source s = {0}; exr_error e = {0}; exr_layout_config c = exr_layout_config_defaults();
  exr_control ctl = {cancel_now, NULL, cancel};
  if (exr_library_source(lib, id, &s, &e) != EXR_OK) return 0;
  c.page.width = 360; c.page.height = 480;
  if (exr_txt_pager_create(&s, font, &c, p, &e) != EXR_OK) { s.release(s.context); return 0; }
  if (cancel) exr_pager_set_control(*p, &ctl, &e);
  exr_pager_set_cache(*p, 1, 0, &e);
  return 1;
}
static int page_ok(exr_pager *p, size_t page) {
  const exr_layout *l = NULL; exr_error e = {0};
  return exr_pager_get(p, page, &l, &e) == EXR_OK && l != NULL;
}

/* Items released in a given order: 0 = pager A, 1 = pager B, 2 = raw source. */
static void ordered(exr_font *font, const char *order) {
  char sc[40]; snprintf(sc, sizeof sc, "release_order_%s", order);
  fixture f; exr_pager *pa = NULL, *pb = NULL; exr_source raw = {0}; exr_error e = {0};
  if (!open_fixture(sc, &f, "order")) { check(sc, "fixture", 0); return; }
  check(sc, "pagers_and_source_created", make_pager(f.lib, f.id, font, &pa, NULL) && make_pager(f.lib, f.id, font, &pb, NULL)
        && exr_library_source(f.lib, f.id, &raw, &e) == EXR_OK && read_check(&raw));
  check(sc, "pager_reads_before_close", page_ok(pa, 0) && page_ok(pb, 1));
  int before = open_fds(); check(sc, "db_open_before_close", before > 0);
  exr_library_close(f.lib); ev(sc, "library_close", 0, "close requested with 3 live borrows");
  check(sc, "db_still_open_after_close_request", open_fds() > 0);
  check(sc, "borrowers_still_function", page_ok(pa, 2) && page_ok(pb, 3) && read_check(&raw));
  for (size_t i = 0; order[i]; i++) {
    int last = order[i + 1] == 0;
    if (order[i] == '0') exr_pager_free(pa); else if (order[i] == '1') exr_pager_free(pb); else raw.release(raw.context);
    ev(sc, order[i] == '2' ? "release_source" : "free_pager", 0, last ? "last borrow" : "borrow remains");
    if (!last) {
      int ok = open_fds() > 0;
      if (order[i + 1] != '0' || order[0] == '0') { /* remaining pagers still readable */ }
      check(sc, "db_open_while_borrow_remains", ok);
    }
  }
  check(sc, "db_closed_after_last_release", open_fds() == 0);
}

static void immediate_close(void) {
  const char *sc = "no_borrow_close"; fixture f;
  if (!open_fixture(sc, &f, "plain")) { check(sc, "fixture", 0); return; }
  check(sc, "db_open", open_fds() > 0);
  exr_library_close(f.lib);
  check(sc, "db_closed_immediately", open_fds() == 0);
}

static void cancel_case(exr_font *font) {
  const char *sc = "cancel"; fixture f; exr_pager *p = NULL; int cancel = 0; const exr_layout *l = NULL; exr_error e = {0};
  if (!open_fixture(sc, &f, "cancel")) { check(sc, "fixture", 0); return; }
  check(sc, "pager", make_pager(f.lib, f.id, font, &p, &cancel));
  exr_library_close(f.lib);
  check(sc, "db_open_after_close_request", open_fds() > 0);
  cancel = 1;
  exr_status s = exr_pager_get(p, 50, &l, &e);
  ev(sc, "pager_get_cancelled", s, e.message);
  check(sc, "get_returns_cancelled", s == EXR_CANCELLED);
  check(sc, "db_still_open_borrow_alive", open_fds() > 0);
  exr_pager_free(p);
  check(sc, "db_closed_after_free", open_fds() == 0);
}

static void failure_cases(exr_font *font) {
  const char *sc = "create_failure"; fixture f; exr_source s = {0}; exr_pager *p = NULL; exr_error e = {0};
  exr_layout_config c = exr_layout_config_defaults();
  if (!open_fixture(sc, &f, "fail")) { check(sc, "fixture", 0); return; }
  check(sc, "source", exr_library_source(f.lib, f.id, &s, &e) == EXR_OK);
  exr_status st = exr_txt_pager_create(&s, NULL, &c, &p, &e);
  ev(sc, "txt_pager_create_null_font", st, e.message);
  check(sc, "create_fails_and_no_pager", st != EXR_OK && p == NULL);
  check(sc, "caller_keeps_source_ownership", read_check(&s));
  exr_library_close(f.lib);
  check(sc, "db_open_while_caller_source_alive", open_fds() > 0);
  s.release(s.context);
  check(sc, "db_closed_after_manual_release", open_fds() == 0);

  sc = "io_invalidation"; fixture g; exr_library *other = NULL; int64_t id2 = 0; int created = 0;
  const exr_layout *l = NULL; exr_pager *q = NULL;
  if (!open_fixture(sc, &g, "inval")) { check(sc, "fixture", 0); return; }
  check(sc, "pager", make_pager(g.lib, g.id, font, &q, NULL) && page_ok(q, 0));
  check(sc, "second_connection", exr_library_open(DB, &other, &e) == EXR_OK &&
        exr_library_import_unique(other, EXR_TXT, "second book commit\n", 19, "other", &id2, &created, &e) == EXR_OK);
  ev(sc, "other_connection_commit", 0, "real commit through another connection");
  exr_library_close(g.lib);
  exr_status s2 = exr_pager_get(q, 40, &l, &e);
  ev(sc, "pager_get_after_invalidation", s2, e.message);
  check(sc, "pager_reports_failure_not_stale_success", s2 != EXR_OK);
  exr_pager_free(q);
  check(sc, "owner_borrow_gone_other_connection_remains", open_fds() > 0);
  exr_library_close(other);
  check(sc, "db_closed_after_all_released", open_fds() == 0);
}

int main(int argc, char **argv) {
  exr_font *font = NULL; exr_error e = {0};
  if (argc != 3) return 2;
  DB = argv[1]; FONT = argv[2];
  for (size_t i = 0; i < sizeof TEXT - 64; ) i += (size_t)snprintf(TEXT + i, 64, "Paragraph %zu of the J05 lifecycle fixture.\n", i);
  TEXT_LEN = strlen(TEXT);
  printf("{\"sdk_version\":\"%s\",\"expected\":\"3.42.0\",\"text_bytes\":%zu}\n", exr_version(), TEXT_LEN);
  if (strcmp(exr_version(), "3.42.0")) failures++;
  if (exr_font_open(FONT, &font, &e) != EXR_OK) { fprintf(stderr, "font: %s\n", e.message); return 2; }
  immediate_close();
  static const char *orders[] = {"012", "021", "102", "120", "201", "210"};
  for (int i = 0; i < 6; i++) ordered(font, orders[i]);
  cancel_case(font);
  failure_cases(font);
  exr_font_free(font);
  printf("{\"summary\":true,\"failures\":%d}\n", failures);
  return failures ? 1 : 0;
}
