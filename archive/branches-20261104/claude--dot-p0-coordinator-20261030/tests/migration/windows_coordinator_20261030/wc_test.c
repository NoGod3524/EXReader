/* SPDX-License-Identifier: MIT
 * Installed-consumer check of the full49 coordinator. Mock-provider fault
 * matrix + real filesystem provider. Module-level evidence only. */
#include "private/exr_wc_provider.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <direct.h>
#define MKDIR(p) _mkdir(p)
#define RMDIR(p) _rmdir(p)
#else
#include <sys/stat.h>
#include <unistd.h>
#define MKDIR(p) mkdir(p, 0700)
#define RMDIR(p) rmdir(p)
#endif

static unsigned checks, failures;
#define CHECK(c) do { checks++; if (!(c)) { failures++; fprintf(stderr, "FAIL %s:%d %s\n", __FILE__, __LINE__, #c); } } while (0)

#define H64 "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
#define ID_A "000000000000000100000000000000000000000000000001"
#define ID_B "000000000000000100000000000000000000000000000002"
#define ID_S "0000000000000001000000000000000000000000000000ff"
#define ID_L "0000000000000001000000000000000000000000000000ee"

static wc_binding bind_ok(void) {
  wc_binding b; memset(&b, 0, sizeof b);
  const char *run = getenv("GITHUB_RUN_ID"), *attempt = getenv("GITHUB_RUN_ATTEMPT"), *os = getenv("RUNNER_OS");
  strcpy(b.source, CANDIDATE_SOURCE_SHA); strcpy(b.run, "40999999999"); strcpy(b.attempt, "1");
  strcpy(b.artifact, H64); strcpy(b.platform, "test-platform"); strcpy(b.sdk, "sdk-none-standalone"); strcpy(b.provider, H64);
  if (run && strlen(run) < sizeof b.run) strcpy(b.run, run);
  if (attempt && strlen(attempt) < sizeof b.attempt) strcpy(b.attempt, attempt);
  if (os && strlen(os) < sizeof b.platform) strcpy(b.platform, os);
  return b;
}
static wc_gates gates_all(void) {
  wc_gates g; memset(&g, 0, sizeof g);
  strcpy(g.admission, H64); strcpy(g.publisher, H64); strcpy(g.recovery, H64); strcpy(g.observer, H64); strcpy(g.fault, H64);
  return g;
}

/* ---- journal sink ---- */
typedef struct { char l[96][EXR_WC_LINE_MAX]; int n, fail_at; } lj;
static int sink(void *c, const char *line) {
  lj *j = c;
  if (j->fail_at >= 0 && j->n == j->fail_at) return 1;
  if (j->n >= 96) return 1;
  strcpy(j->l[j->n++], line);
  return 0;
}
static void lj_init(lj *j) { memset(j, 0, sizeof *j); j->fail_at = -1; }
static const char *ptrs[96];
static const char *const *lines_of(const lj *j, int n) { int i; for (i = 0; i < n; i++) ptrs[i] = j->l[i]; return ptrs; }

/* ---- mock provider ---- */
typedef struct {
  int fail_admit, fail_snapshot, fail_import, fail_verify, fail_release, fail_discard;
  wc_pub publish_result; wc_step publish_step; wc_pub recover_result; wc_step recover_step;
  int published, discarded, released, admitted, imported, calls;
} mock;
static void rows_of(wc_record *r, size_t *n) {
  memset(r, 0, 2 * sizeof *r);
  strcpy(r[0].id, ID_A); strcpy(r[0].path, "a.db"); r[0].size = 3; wc_sha256_hex("abc", 3, r[0].sha);
  strcpy(r[1].id, ID_B); strcpy(r[1].path, "dir/b.bin"); r[1].size = 0; wc_sha256_hex("", 0, r[1].sha);
  *n = 2;
}
static wc_step m_admit(void *c, const wc_binding *b, char *lease) { mock *m = c; (void)b; m->calls++; if (m->fail_admit) return WC_STEP_FAILED; m->admitted = 1; strcpy(lease, ID_L); return WC_STEP_OK; }
static wc_step m_snapshot(void *c, wc_record *r, size_t cap, size_t *n) { mock *m = c; m->calls++; if (m->fail_snapshot) return WC_STEP_FAILED; (void)cap; rows_of(r, n); return WC_STEP_OK; }
static wc_step m_import(void *c, const wc_binding *b, const wc_record *r, size_t n, char *staged) { mock *m = c; (void)b; (void)r; (void)n; m->calls++; if (m->fail_import) return WC_STEP_FAILED; m->imported = 1; strcpy(staged, ID_S); return WC_STEP_OK; }
static wc_step m_verify(void *c, const char *s, const wc_record *r, size_t n) { mock *m = c; (void)s; (void)r; (void)n; m->calls++; return m->fail_verify ? WC_STEP_FAILED : WC_STEP_OK; }
static wc_step m_publish(void *c, const char *s, wc_pub *o) { mock *m = c; (void)s; m->calls++; *o = m->publish_result; if (m->publish_step == WC_STEP_OK && m->publish_result == WC_PUB_YES) m->published = 1; return m->publish_step; }
static wc_step m_recover(void *c, const char *s, wc_pub *o) { mock *m = c; (void)s; m->calls++; *o = m->recover_result; return m->recover_step; }
static wc_step m_discard(void *c, const char *s) { mock *m = c; (void)s; m->calls++; if (m->fail_discard) return WC_STEP_UNCERTAIN; m->discarded = 1; return WC_STEP_OK; }
static wc_step m_release(void *c, const char *l) { mock *m = c; (void)l; m->calls++; if (m->fail_release) return WC_STEP_FAILED; m->released = 1; return WC_STEP_OK; }
static wc_provider mk_provider(mock *m) {
  wc_provider p; memset(&p, 0, sizeof p); p.abi = EXR_WC_ABI; p.identity_sha = H64; p.context = m;
  p.admit = m_admit; p.snapshot = m_snapshot; p.import = m_import; p.verify = m_verify; p.publish = m_publish;
  p.recover = m_recover; p.discard = m_discard; p.release = m_release; return p;
}
static void mock_init(mock *m) { memset(m, 0, sizeof *m); m->publish_result = WC_PUB_YES; m->publish_step = WC_STEP_OK; m->recover_result = WC_PUB_YES; m->recover_step = WC_STEP_OK; }

/* ---- files ---- */
static void put(const char *dir, const char *name, const char *text) {
  char p[1200]; FILE *f; snprintf(p, sizeof p, "%s/%s", dir, name); f = fopen(p, "wb"); if (f) { fwrite(text, 1, strlen(text), f); fclose(f); }
}
static int exists(const char *dir, const char *name) {
  char p[1200]; FILE *f; snprintf(p, sizeof p, "%s/%s", dir, name); f = fopen(p, "rb"); if (f) fclose(f); return f != NULL;
}

static void unit_checks(void) {
  char d[65]; wc_binding b = bind_ok(), b2; wc_record r[2], r2[2]; size_t n; char s1[65], s2[65], c1[65], c2[65];
  wc_sha256_hex("abc", 3, d); CHECK(!strcmp(d, "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"));
  wc_sha256_hex("", 0, d); CHECK(!strcmp(d, "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"));
  CHECK(wc_binding_valid(&b)); b2 = b; b2.source[0] = 'G'; CHECK(!wc_binding_valid(&b2));
  b2 = b; b2.run[0] = 0; CHECK(!wc_binding_valid(&b2)); b2 = b; strcpy(b2.platform, "bad platform"); CHECK(!wc_binding_valid(&b2));
  b2 = b; b2.artifact[63] = 0; CHECK(!wc_binding_valid(&b2)); b2 = b; strcpy(b2.attempt, "1234"); CHECK(!wc_binding_valid(&b2));
  rows_of(r, &n); CHECK(wc_snapshot_valid(r, n));
  memcpy(r2, r, sizeof r); strcpy(r2[0].path, "z.db"); CHECK(!wc_snapshot_valid(r2, 2));            /* unsorted */
  memcpy(r2, r, sizeof r); strcpy(r2[1].path, "a.db"); CHECK(!wc_snapshot_valid(r2, 2));            /* duplicate */
  memcpy(r2, r, sizeof r); strcpy(r2[1].path, "../x"); CHECK(!wc_snapshot_valid(r2, 2));
  memcpy(r2, r, sizeof r); strcpy(r2[1].path, "dir//b"); CHECK(!wc_snapshot_valid(r2, 2));
  memcpy(r2, r, sizeof r); strcpy(r2[1].path, "dir\\b"); CHECK(!wc_snapshot_valid(r2, 2));
  memcpy(r2, r, sizeof r); strcpy(r2[1].path, "dir/b."); CHECK(!wc_snapshot_valid(r2, 2));
  memcpy(r2, r, sizeof r); r2[0].id[47] = 0; CHECK(!wc_snapshot_valid(r2, 2));                      /* 47-char id */
  memcpy(r2, r, sizeof r); r2[0].id[0] = 'A'; CHECK(!wc_snapshot_valid(r2, 2));
  memcpy(r2, r, sizeof r); r2[0].sha[10] = 'Z'; CHECK(!wc_snapshot_valid(r2, 2));
  CHECK(strlen(r[0].id) == 48 && sizeof r[0].id == 49);
  CHECK(wc_snapshot_digest(&b, r, 2, s1) && wc_content_digest(r, 2, c1));
  memcpy(r2, r, sizeof r); strcpy(r2[0].id, ID_B); strcpy(r2[1].id, ID_A);
  CHECK(wc_snapshot_digest(&b, r2, 2, s2) && wc_content_digest(r2, 2, c2));
  CHECK(strcmp(s1, s2) && !strcmp(c1, c2));                                                           /* identity-sensitive vs content-only */
  memcpy(r2, r, sizeof r); r2[0].id[47] = '9'; CHECK(wc_snapshot_digest(&b, r2, 2, s2) && strcmp(s1, s2)); /* last id nibble matters */
  b2 = b; b2.attempt[0] = '2'; CHECK(wc_snapshot_digest(&b2, r, 2, s2) && strcmp(s1, s2));
  memcpy(r2, r, sizeof r); r2[0].size = 4; CHECK(wc_content_digest(r2, 2, c2) && strcmp(c1, c2));
}

static void orchestration(const char *tmp) {
  wc_binding b = bind_ok(); wc_gates g = gates_all(); mock m; wc_provider p; lj j; wc_report r; wc_status s; char why[96]; int i, k;
  (void)tmp;
  /* pending: gate and function absence, zero provider calls and journal lines */
  mock_init(&m); p = mk_provider(&m); lj_init(&j); memset(&g, 0, sizeof g);
  s = wc_run(&b, &g, &p, sink, &j, &r); CHECK(s == WC_PENDING && m.calls == 0 && j.n == 0 && strstr(r.pending, "gate:admission") && strstr(r.pending, "gate:fault"));
  g = gates_all(); g.observer[0] = 0; lj_init(&j);
  s = wc_run(&b, &g, &p, sink, &j, &r); CHECK(s == WC_PENDING && !strcmp(r.pending, "gate:observer") && m.calls == 0 && j.n == 0);
  g = gates_all(); p.publish = NULL; s = wc_run(&b, &g, &p, sink, &j, &r); CHECK(s == WC_PENDING && !strcmp(r.pending, "fn:publish") && m.calls == 0);
  p = mk_provider(&m); p.admit = NULL; p.release = NULL; s = wc_run(&b, &g, &p, sink, &j, &r); CHECK(s == WC_PENDING && strstr(r.pending, "fn:admit") && strstr(r.pending, "fn:release"));
  p = mk_provider(&m); strcpy(g.fault, "xyz"); s = wc_run(&b, &g, &p, sink, &j, &r); CHECK(s == WC_REFUSED);
  g = gates_all(); { wc_binding bad = b; bad.source[3] = 'Q'; s = wc_run(&bad, &g, &p, sink, &j, &r); CHECK(s == WC_REFUSED && m.calls == 0); }
  p.identity_sha = "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"; s = wc_run(&b, &g, &p, sink, &j, &r); CHECK(s == WC_REFUSED && m.calls == 0);
  p = mk_provider(&m); s = wc_run(&b, &g, &p, NULL, NULL, &r); CHECK(s == WC_REFUSED && m.calls == 0);

  /* happy path */
  mock_init(&m); p = mk_provider(&m); lj_init(&j);
  s = wc_run(&b, &g, &p, sink, &j, &r);
  CHECK(s == WC_COMPLETED && m.published && m.released && !m.discarded && j.n == 13 && r.records == 2 && strlen(r.snapshot_digest) == 64);
  CHECK(wc_journal_check(&b, lines_of(&j, j.n), (size_t)j.n, why, sizeof why));
  CHECK(strstr(j.l[8], "phase=publish state=begin") && strstr(j.l[12], "phase=complete state=ok"));
  { wc_report r2; mock m2; wc_provider p2; lj j2; mock_init(&m2); p2 = mk_provider(&m2); lj_init(&j2);
    CHECK(wc_recover(&b, &g, &p2, lines_of(&j, j.n), (size_t)j.n, sink, &j2, &r2) == WC_COMPLETED && !m2.discarded && !m2.released); }

  /* clean failures roll back and release; publication never claimed */
  for (i = 0; i < 6; i++) {
    mock_init(&m); lj_init(&j); p = mk_provider(&m);
    m.fail_admit = i == 0; m.fail_snapshot = i == 1; m.fail_import = i == 2; m.fail_verify = i == 3;
    if (i >= 4) m.publish_result = WC_PUB_NO;
    if (i == 5) m.publish_step = WC_STEP_FAILED;
    s = wc_run(&b, &g, &p, sink, &j, &r);
    CHECK(!m.published);
    if (i == 0) CHECK(s == WC_REFUSED && !m.released && !m.discarded);
    else if (i == 1 || i == 2) CHECK(s == WC_ROLLED_BACK && m.released && !m.discarded);   /* import failed before any staged identity */
    else CHECK(s == WC_ROLLED_BACK && m.released && m.discarded);
    CHECK(wc_journal_check(&b, lines_of(&j, j.n), (size_t)j.n, why, sizeof why));
  }
  /* publication unknown: nothing discarded or released */
  mock_init(&m); m.publish_step = WC_STEP_UNCERTAIN; m.publish_result = WC_PUB_UNKNOWN; lj_init(&j); p = mk_provider(&m);
  s = wc_run(&b, &g, &p, sink, &j, &r); CHECK(s == WC_UNCERTAIN && !m.discarded && !m.released);
  mock_init(&m); m.publish_result = WC_PUB_UNKNOWN; lj_init(&j); p = mk_provider(&m);
  s = wc_run(&b, &g, &p, sink, &j, &r); CHECK(s == WC_UNCERTAIN && !m.discarded && !m.released);
  /* published but release failed */
  mock_init(&m); m.fail_release = 1; lj_init(&j); p = mk_provider(&m);
  s = wc_run(&b, &g, &p, sink, &j, &r); CHECK(s == WC_LEASE_RETAINED && m.published && !m.discarded);
  /* rollback whose discard fails */
  mock_init(&m); m.fail_verify = 1; m.fail_discard = 1; lj_init(&j); p = mk_provider(&m);
  s = wc_run(&b, &g, &p, sink, &j, &r); CHECK(s == WC_UNCERTAIN && !m.released);

  /* journal sink failing at every position: never completed-with-failure, never rolled back after publication */
  for (k = 0; k <= 13; k++) {
    mock_init(&m); lj_init(&j); j.fail_at = k; p = mk_provider(&m);
    s = wc_run(&b, &g, &p, sink, &j, &r);
    CHECK(!(s == WC_COMPLETED && k < 13));
    CHECK(!(s == WC_ROLLED_BACK && m.published));
    CHECK(!(m.published && m.discarded));
    CHECK(wc_journal_check(&b, lines_of(&j, j.n), j.n ? (size_t)j.n : 0, why, sizeof why) || j.n == 0);
    if (k <= 8) CHECK(!m.published);   /* publish intent is durable before the publisher is called */
  }

  /* recover from every strict prefix of the happy journal, per publisher answer */
  { int mode; mock_init(&m); lj_init(&j); p = mk_provider(&m); wc_run(&b, &g, &p, sink, &j, &r);
    for (mode = 0; mode < 3; mode++) {
      int n;
      for (n = 1; n <= 13; n++) {
        mock m2; wc_provider p2; lj j2; wc_report r2; wc_status e;
        mock_init(&m2); lj_init(&j2); m2.recover_result = mode == 0 ? WC_PUB_YES : mode == 1 ? WC_PUB_NO : WC_PUB_UNKNOWN;
        if (mode == 2) m2.recover_step = WC_STEP_UNCERTAIN;
        p2 = mk_provider(&m2); e = wc_recover(&b, &g, &p2, lines_of(&j, n), (size_t)n, sink, &j2, &r2);
        if (n == 1 || n == 5) CHECK(e == WC_UNCERTAIN && !m2.released && !m2.discarded);             /* open admit / import */
        else if (n <= 8) CHECK(e == WC_ROLLED_BACK && m2.released && (n < 6 || m2.discarded));
        else if (n == 9) CHECK(mode == 0 ? e == WC_COMPLETED && m2.released : mode == 1 ? e == WC_ROLLED_BACK && m2.discarded : e == WC_UNCERTAIN && !m2.discarded && !m2.released);
        else CHECK(mode == 0 ? e == WC_COMPLETED : e == WC_UNCERTAIN && !m2.discarded);
        CHECK(!(e == WC_ROLLED_BACK && n >= 10));
        if (j2.n) { /* appended lines continue the same chain */
          const char *bl[96]; int q; for (q = 0; q < n; q++) bl[q] = j.l[q]; for (q = 0; q < j2.n; q++) bl[n + q] = j2.l[q];
          CHECK(wc_journal_check(&b, bl, (size_t)(n + j2.n), why, sizeof why));
        }
      }
    }
    /* tamper detection */
    { char save[EXR_WC_LINE_MAX]; mock m2; wc_provider p2; lj j2; wc_report r2; wc_binding other = b; const char *tl[96]; int q;
      mock_init(&m2); p2 = mk_provider(&m2); lj_init(&j2);
      for (q = 0; q < 13; q++) tl[q] = j.l[q];
      strcpy(save, j.l[4]); j.l[4][11] = '7'; CHECK(wc_recover(&b, &g, &p2, tl, 13, sink, &j2, &r2) == WC_REFUSED && m2.calls == 0); strcpy(j.l[4], save);
      tl[3] = j.l[5]; CHECK(wc_recover(&b, &g, &p2, tl, 13, sink, &j2, &r2) == WC_REFUSED); tl[3] = j.l[3];
      { const char *dl[96]; int w = 0; for (q = 0; q < 13; q++) if (q != 6) dl[w++] = j.l[q]; CHECK(wc_recover(&b, &g, &p2, dl, 12, sink, &j2, &r2) == WC_REFUSED); }
      other.run[0] = '5'; CHECK(wc_recover(&other, &g, &p2, tl, 13, sink, &j2, &r2) == WC_REFUSED);
      other = b; other.artifact[0] = 'f'; CHECK(wc_recover(&other, &g, &p2, tl, 13, sink, &j2, &r2) == WC_REFUSED);
      other = b; strcpy(other.platform, "other"); CHECK(wc_recover(&other, &g, &p2, tl, 13, sink, &j2, &r2) == WC_REFUSED);
      other = b; strcpy(other.sdk, "sdk-9"); CHECK(wc_recover(&other, &g, &p2, tl, 13, sink, &j2, &r2) == WC_REFUSED);
      CHECK(m2.calls == 0);
      CHECK(wc_recover(&b, &g, &p2, tl, 0, sink, &j2, &r2) == WC_REFUSED);
      g.publisher[0] = 0; CHECK(wc_recover(&b, &g, &p2, tl, 13, sink, &j2, &r2) == WC_PENDING && m2.calls == 0); g = gates_all();
    } }
}

/* ---- real filesystem provider ---- */
static void fs_checks(const char *tmp) {
  char src[1100], par[1100], stage[1300]; wc_fs *fs = NULL; wc_provider p; wc_binding b = bind_ok(); wc_gates g = gates_all();
  wc_record *rows = calloc(EXR_WC_MAX_RECORDS, sizeof *rows); size_t n = 0, i; char staged[49]; mock m; lj j; wc_report r; wc_status s; char why[96];
  snprintf(src, sizeof src, "%s/src", tmp); snprintf(par, sizeof par, "%s/out", tmp);
  MKDIR(tmp); MKDIR(src); MKDIR(par);
  { char sub[1200]; snprintf(sub, sizeof sub, "%s/deep", src); MKDIR(sub); snprintf(sub, sizeof sub, "%s/deep/er", src); MKDIR(sub); }
  put(src, "library.db", "sqlite-bytes-0123456789"); put(src, "cover.png", "png"); put(src, "deep/note.txt", "hello"); put(src, "deep/er/x.bin", "xyz"); put(src, "empty.dat", "");
  CHECK(wc_fs_open(src, par, H64, &fs, &p));
  /* without attached publisher/admission the run is pending and nothing is staged */
  lj_init(&j); s = wc_run(&b, &g, &p, sink, &j, &r);
  CHECK(s == WC_PENDING && strstr(r.pending, "fn:admit") && strstr(r.pending, "fn:publish") && !strstr(r.pending, "fn:snapshot") && !wc_fs_staging_path(fs));
  wc_fs_close(fs); fs = NULL;
  CHECK(wc_fs_open(src, par, H64, &fs, &p) == 1);                                                      /* second handle for direct steps */
  CHECK(p.snapshot(p.context, rows, EXR_WC_MAX_RECORDS, &n) == WC_STEP_OK && n == 5 && wc_snapshot_valid(rows, n));
  CHECK(!strcmp(rows[0].path, "cover.png") && !strcmp(rows[1].path, "deep/er/x.bin") && !strcmp(rows[2].path, "deep/note.txt") && !strcmp(rows[4].path, "library.db"));
  for (i = 0; i < n; i++) CHECK(strlen(rows[i].id) == 48);
  CHECK(strcmp(rows[0].id, rows[1].id) != 0);
  CHECK(p.import(p.context, &b, rows, n, staged) == WC_STEP_OK && strlen(staged) == 48);
  snprintf(stage, sizeof stage, "%s", wc_fs_staging_path(fs) ? wc_fs_staging_path(fs) : "");
  CHECK(exists(stage, "library.db") && exists(stage, "deep/er/x.bin") && exists(stage, "empty.dat"));
  CHECK(p.verify(p.context, staged, rows, n) == WC_STEP_OK);
  { char other[49]; strcpy(other, staged); other[47] = other[47] == '0' ? '1' : '0'; CHECK(p.verify(p.context, other, rows, n) == WC_STEP_FAILED); }
  put(stage, "library.db", "tampered-bytes-0123456");
  CHECK(p.verify(p.context, staged, rows, n) == WC_STEP_FAILED);
  put(stage, "library.db", "sqlite-bytes-0123456789");
  CHECK(p.verify(p.context, staged, rows, n) == WC_STEP_OK);
  put(stage, "foreign.txt", "not ours");
  CHECK(p.discard(p.context, staged) == WC_STEP_UNCERTAIN && exists(stage, "foreign.txt") && exists(stage, "cover.png") == 0);   /* conservative: foreign content retained */
  { char fp[1400]; snprintf(fp, sizeof fp, "%s/foreign.txt", stage); remove(fp); }
  CHECK(p.discard(p.context, staged) == WC_STEP_OK && !wc_fs_staging_path(fs));
  CHECK(!exists(stage, "library.db"));
  wc_fs_close(fs); fs = NULL;

  /* exclusive: a pre-existing stage is never adopted */
  CHECK(wc_fs_open(src, par, H64, &fs, &p));
  { char pre[1300]; snprintf(pre, sizeof pre, "%s/.exwc-%s-%s", par, b.run, b.attempt); MKDIR(pre); put(pre, "keep.txt", "precious");
    CHECK(p.import(p.context, &b, rows, n, staged) == WC_STEP_FAILED && exists(pre, "keep.txt"));
    { char fp[1400]; snprintf(fp, sizeof fp, "%s/keep.txt", pre); remove(fp); } RMDIR(pre); }
  wc_fs_close(fs); fs = NULL;

  /* source changed after snapshot: import fails, then discard removes only what was created */
  CHECK(wc_fs_open(src, par, H64, &fs, &p));
  put(src, "library.db", "sqlite-bytes-CHANGED!!!!");
  { wc_step e = p.import(p.context, &b, rows, n, staged);
    CHECK(e == WC_STEP_FAILED && strlen(staged) == 48);
    CHECK(p.discard(p.context, staged) == WC_STEP_OK && !wc_fs_staging_path(fs)); }
  put(src, "library.db", "sqlite-bytes-0123456789");
  wc_fs_close(fs); fs = NULL;

  /* full run with delegate admission/publisher supplied by the test (stand-ins for C01/native publisher) */
  CHECK(wc_fs_open(src, par, H64, &fs, &p));
  mock_init(&m);
  { wc_fs_attach(&p, m_admit, m_publish, m_recover, m_release, &m); lj_init(&j);
    s = wc_run(&b, &g, &p, sink, &j, &r);
    CHECK(s == WC_COMPLETED && m.published && m.released && r.records == 5 && wc_fs_staging_path(fs) != NULL);
    CHECK(wc_journal_check(&b, lines_of(&j, j.n), (size_t)j.n, why, sizeof why)); }
  wc_fs_close(fs);
  free(rows);
}

int main(int argc, char **argv) {
  const char *tmp = argc > 1 ? argv[1] : "coordinator-tmp";
  unit_checks(); orchestration(tmp); fs_checks(tmp);
  printf("{\"source\":\"%s\",\"checks\":%u,\"failures\":%u,\"passed\":%s,\"scope\":\"module-only-not-full-p0\",\"identity_bytes\":49}\n",
         CANDIDATE_SOURCE_SHA, checks, failures, failures ? "false" : "true");
  return failures ? 1 : 0;
}
