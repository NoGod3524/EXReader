/* SPDX-License-Identifier: MIT */
#include "exr_wc_provider.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* ---- SHA256 ---- */
typedef struct { uint32_t h[8]; uint64_t bits; unsigned char buf[64]; size_t n; } sha;
static const uint32_t K[64] = {
0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2};
#define ROR(x,n) (((x)>>(n))|((x)<<(32-(n))))
static void block(sha *s, const unsigned char *p) {
  uint32_t w[64], a, b, c, d, e, f, g, h, t1, t2; int i;
  for (i = 0; i < 16; i++) w[i] = (uint32_t)p[4*i]<<24 | (uint32_t)p[4*i+1]<<16 | (uint32_t)p[4*i+2]<<8 | p[4*i+3];
  for (i = 16; i < 64; i++) {
    uint32_t s0 = ROR(w[i-15],7) ^ ROR(w[i-15],18) ^ (w[i-15]>>3), s1 = ROR(w[i-2],17) ^ ROR(w[i-2],19) ^ (w[i-2]>>10);
    w[i] = w[i-16] + s0 + w[i-7] + s1;
  }
  a=s->h[0];b=s->h[1];c=s->h[2];d=s->h[3];e=s->h[4];f=s->h[5];g=s->h[6];h=s->h[7];
  for (i = 0; i < 64; i++) {
    t1 = h + (ROR(e,6)^ROR(e,11)^ROR(e,25)) + ((e&f)^(~e&g)) + K[i] + w[i];
    t2 = (ROR(a,2)^ROR(a,13)^ROR(a,22)) + ((a&b)^(a&c)^(b&c));
    h=g;g=f;f=e;e=d+t1;d=c;c=b;b=a;a=t1+t2;
  }
  s->h[0]+=a;s->h[1]+=b;s->h[2]+=c;s->h[3]+=d;s->h[4]+=e;s->h[5]+=f;s->h[6]+=g;s->h[7]+=h;
}
static void sha_init(sha *s) {
  static const uint32_t i0[8] = {0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19};
  memcpy(s->h, i0, sizeof i0); s->bits = 0; s->n = 0;
}
static void sha_add(sha *s, const void *data, size_t n) {
  const unsigned char *p = data; s->bits += (uint64_t)n * 8;
  while (n) {
    size_t k = 64 - s->n; if (k > n) k = n;
    memcpy(s->buf + s->n, p, k); s->n += k; p += k; n -= k;
    if (s->n == 64) { block(s, s->buf); s->n = 0; }
  }
}
static void sha_hex(sha *s, char out[65]) {
  static const char hx[] = "0123456789abcdef"; uint64_t bits = s->bits; unsigned char pad = 0x80, z = 0, len[8]; int i;
  sha_add(s, &pad, 1); while (s->n != 56) sha_add(s, &z, 1);
  for (i = 0; i < 8; i++) len[i] = (unsigned char)(bits >> (56 - 8*i));
  sha_add(s, len, 8);
  for (i = 0; i < 32; i++) { unsigned char v = (unsigned char)(s->h[i/4] >> (24 - 8*(i%4))); out[2*i] = hx[v>>4]; out[2*i+1] = hx[v&15]; }
  out[64] = 0;
}
void wc_sha256_hex(const void *data, size_t size, char out[65]) { sha s; sha_init(&s); sha_add(&s, data, size); sha_hex(&s, out); }

/* ---- validation ---- */
static int hexn(const char *s, size_t n) {
  size_t i; if (!s) return 0;
  for (i = 0; i < n; i++) if (!((s[i] >= '0' && s[i] <= '9') || (s[i] >= 'a' && s[i] <= 'f'))) return 0;
  return s[n] == 0;
}
static int digitsn(const char *s, size_t max) {
  size_t i, n = s ? strlen(s) : 0; if (!n || n > max) return 0;
  for (i = 0; i < n; i++) if (s[i] < '0' || s[i] > '9') return 0;
  return 1;
}
static int token(const char *s, size_t max) {
  size_t i, n = s ? strlen(s) : 0; if (!n || n > max) return 0;
  for (i = 0; i < n; i++) { char c = s[i]; if (!((c>='a'&&c<='z')||(c>='A'&&c<='Z')||(c>='0'&&c<='9')||c=='.'||c=='_'||c=='-')) return 0; }
  return 1;
}
int wc_binding_valid(const wc_binding *b) {
  return b && hexn(b->source, 40) && digitsn(b->run, 20) && digitsn(b->attempt, 3) && hexn(b->artifact, 64) &&
         token(b->platform, 31) && token(b->sdk, 63) && hexn(b->provider, 64);
}
int wc_binding_digest(const wc_binding *b, char out[65]) {
  char text[400];
  if (!wc_binding_valid(b)) return 0;
  snprintf(text, sizeof text, "EXRWC-BIND1\nsource=%s\nrun=%s\nattempt=%s\nartifact=%s\nplatform=%s\nsdk=%s\nprovider=%s\n",
           b->source, b->run, b->attempt, b->artifact, b->platform, b->sdk, b->provider);
  wc_sha256_hex(text, strlen(text), out); return 1;
}
static int path_ok(const char *p) {
  size_t i, n = p ? strlen(p) : 0, start = 0;
  if (!n || n >= EXR_WC_PATH_MAX) return 0;
  for (i = 0; i <= n; i++) {
    unsigned char c = (unsigned char)p[i];
    if (i < n && (c < 0x20 || c == '\\' || c == ':' || c == '*' || c == '?' || c == '"' || c == '<' || c == '>' || c == '|')) return 0;
    if (i == n || c == '/') {
      size_t len = i - start;
      if (!len || (len == 1 && p[start] == '.') || (len == 2 && p[start] == '.' && p[start+1] == '.') || p[i-1] == '.' || p[i-1] == ' ') return 0;
      start = i + 1;
    }
  }
  return 1;
}
int wc_snapshot_valid(const wc_record *r, size_t n) {
  size_t i; if (!r || !n || n > EXR_WC_MAX_RECORDS) return 0;
  for (i = 0; i < n; i++) {
    if (!hexn(r[i].id, 48) || !hexn(r[i].sha, 64) || !path_ok(r[i].path)) return 0;
    if (i && strcmp(r[i-1].path, r[i].path) >= 0) return 0;
  }
  return 1;
}
static void digest_rows(const char *head, const wc_record *r, size_t n, int ids, char out[65]) {
  sha s; size_t i; char line[EXR_WC_PATH_MAX + 200]; int k;
  sha_init(&s); sha_add(&s, head, strlen(head));
  for (i = 0; i < n; i++) {
    k = snprintf(line, sizeof line, "%s%s%s %llu %s %s\n", ids ? r[i].id : "", ids ? " " : "", "f",
                 (unsigned long long)r[i].size, r[i].sha, r[i].path);
    sha_add(&s, line, (size_t)k);
  }
  sha_hex(&s, out);
}
int wc_snapshot_digest(const wc_binding *b, const wc_record *r, size_t n, char out[65]) {
  char head[120], bd[65];
  if (!wc_snapshot_valid(r, n) || !wc_binding_digest(b, bd)) return 0;
  snprintf(head, sizeof head, "EXRWC-SNAP1 %s %zu\n", bd, n); digest_rows(head, r, n, 1, out); return 1;
}
int wc_content_digest(const wc_record *r, size_t n, char out[65]) {
  char head[40]; if (!wc_snapshot_valid(r, n)) return 0;
  snprintf(head, sizeof head, "EXRWC-CONTENT1 %zu\n", n); digest_rows(head, r, n, 0, out); return 1;
}
const char *wc_status_name(wc_status s) {
  static const char *names[] = {"completed","pending","refused","rolled_back","uncertain","lease_retained","internal"};
  return (unsigned)s < 7 ? names[s] : "internal";
}

/* ---- journal ---- */
typedef struct { wc_sink sink; void *ctx; unsigned seq; char prev[65], bind[65]; } jr;
static const char ZERO[65] = "0000000000000000000000000000000000000000000000000000000000000000";
static int jput(jr *j, const char *phase, const char *state, const char *id, const char *shahex) {
  char line[EXR_WC_LINE_MAX], seal[65]; int n;
  n = snprintf(line, sizeof line, "EXRWC1 seq=%u phase=%s state=%s id=%s sha=%s prev=%s bind=%s",
               j->seq, phase, state, id && *id ? id : "-", shahex && *shahex ? shahex : "-", j->prev, j->bind);
  if (n <= 0 || (size_t)n >= sizeof line - 70) return 1;
  wc_sha256_hex(line, (size_t)n, seal); strcat(line, " seal="); strcat(line, seal);
  if (!j->sink || j->sink(j->ctx, line)) return 1;
  memcpy(j->prev, seal, 65); j->seq++; return 0;
}

typedef struct { unsigned seq; char phase[16], state[12], id[49], sha[65], prev[65], bind[65], seal[65]; } jl;
static int field(const char *tok, const char *key, char *out, size_t cap) {
  size_t k = strlen(key); if (strncmp(tok, key, k) || tok[k] != '=') return 0;
  tok += k + 1; if (strlen(tok) >= cap) return 0; strcpy(out, tok); return 1;
}
static int parse_line(const char *line, jl *o) {
  char copy[EXR_WC_LINE_MAX], *t[10], *p; int n = 0; char seqs[12], sealed[EXR_WC_LINE_MAX]; const char *at;
  size_t len = line ? strlen(line) : 0;
  if (!len || len >= sizeof copy) return 0;
  memcpy(copy, line, len + 1);
  for (p = strtok(copy, " "); p && n < 10; p = strtok(NULL, " ")) t[n++] = p;
  if (p || n != 9 || strcmp(t[0], "EXRWC1")) return 0;
  if (!field(t[1], "seq", seqs, sizeof seqs) || !digitsn(seqs, 6) || !field(t[2], "phase", o->phase, sizeof o->phase) ||
      !field(t[3], "state", o->state, sizeof o->state) || !field(t[4], "id", o->id, sizeof o->id) ||
      !field(t[5], "sha", o->sha, sizeof o->sha) || !field(t[6], "prev", o->prev, sizeof o->prev) ||
      !field(t[7], "bind", o->bind, sizeof o->bind) || !field(t[8], "seal", o->seal, sizeof o->seal)) return 0;
  o->seq = (unsigned)strtoul(seqs, NULL, 10);
  if ((strcmp(o->id, "-") && !hexn(o->id, 48)) || (strcmp(o->sha, "-") && !hexn(o->sha, 64)) ||
      !hexn(o->prev, 64) || !hexn(o->bind, 64) || !hexn(o->seal, 64)) return 0;
  at = strstr(line, " seal="); if (!at) return 0;
  memcpy(sealed, line, (size_t)(at - line)); sealed[at - line] = 0;
  wc_sha256_hex(sealed, strlen(sealed), copy);
  return !strcmp(copy, o->seal);
}
static int in_list(const char *v, const char *const *list) { for (; *list; list++) if (!strcmp(v, *list)) return 1; return 0; }
static const char *const PHASES[] = {"admit","snapshot","import","verify","publish","recover","rollback","release","complete",0};
static const char *const STATES[] = {"begin","ok","fail","uncertain",0};

static int load(const wc_binding *b, const char *const *lines, size_t n, jl *rows, char *why, size_t ws) {
  char bd[65], prev[65]; size_t i;
#define BAD(m) do { if (why && ws) snprintf(why, ws, "%s at line %zu", m, i); return 0; } while (0)
  i = 0; if (!wc_binding_digest(b, bd)) BAD("binding");
  memcpy(prev, ZERO, 65);
  if (!lines || !n || n > 256) BAD("journal-size");
  for (i = 0; i < n; i++) {
    if (!parse_line(lines[i], &rows[i])) BAD("line-or-seal");
    if (rows[i].seq != i) BAD("sequence");
    if (strcmp(rows[i].prev, prev)) BAD("chain");
    if (strcmp(rows[i].bind, bd)) BAD("binding-mismatch");
    if (!in_list(rows[i].phase, PHASES) || !in_list(rows[i].state, STATES)) BAD("vocabulary");
    memcpy(prev, rows[i].seal, 65);
  }
  return 1;
#undef BAD
}
int wc_journal_check(const wc_binding *b, const char *const *lines, size_t n, char *why, size_t ws) {
  jl rows[256]; return load(b, lines, n, rows, why, ws);
}

/* ---- orchestration ---- */
typedef struct {
  const wc_binding *b; const wc_provider *p; jr j; wc_report *r;
  wc_record *rows; size_t n;
} cx;
static wc_status end(cx *c, wc_status s, const char *phase, const char *detail) {
  c->r->status = s; c->r->seq = c->j.seq;
  snprintf(c->r->phase, sizeof c->r->phase, "%s", phase); snprintf(c->r->detail, sizeof c->r->detail, "%s", detail);
  return s;
}
static void pend(char *out, const char *item) {
  size_t n = strlen(out); if (n + strlen(item) + 2 >= 256) return;
  if (n) out[n++] = ','; strcpy(out + n, item);
}
static int preflight(const wc_binding *b, const wc_gates *g, const wc_provider *p, int recover, wc_report *r) {
  if (!b || !g || !p || !r) return 2;
  if (!wc_binding_valid(b)) { snprintf(r->detail, sizeof r->detail, "binding-invalid"); return 2; }
  if (p->abi != EXR_WC_ABI || !p->identity_sha || strcmp(p->identity_sha, b->provider)) {
    snprintf(r->detail, sizeof r->detail, "provider-identity-mismatch"); return 2;
  }
  if (!g->admission[0]) pend(r->pending, "gate:admission");
  if (!g->publisher[0]) pend(r->pending, "gate:publisher");
  if (!g->recovery[0]) pend(r->pending, "gate:recovery");
  if (!g->observer[0]) pend(r->pending, "gate:observer");
  if (!g->fault[0]) pend(r->pending, "gate:fault");
  if (!p->admit) pend(r->pending, "fn:admit");
  if (!p->snapshot) pend(r->pending, "fn:snapshot");
  if (!p->import) pend(r->pending, "fn:import");
  if (!p->verify) pend(r->pending, "fn:verify");
  if (!p->publish) pend(r->pending, "fn:publish");
  if (!p->recover) pend(r->pending, "fn:recover");
  if (!p->discard) pend(r->pending, "fn:discard");
  if (!p->release) pend(r->pending, "fn:release");
  (void)recover;
  return r->pending[0] ? 1 : 0;
}
#define GATEHEX(x) ((x)[0] && !hexn((x), 64))
static int gates_valid(const wc_gates *g) {
  return !GATEHEX(g->admission) && !GATEHEX(g->publisher) && !GATEHEX(g->recovery) && !GATEHEX(g->observer) && !GATEHEX(g->fault);
}

static wc_status rollback(cx *c, const char *why) {
  wc_report *r = c->r; wc_step s;
  if (jput(&c->j, "rollback", "begin", r->staged, r->content_digest))
    return end(c, WC_UNCERTAIN, "rollback", "journal-write-failed-before-rollback");
  if (r->staged[0]) {
    s = c->p->discard(c->p->context, r->staged);
    if (s != WC_STEP_OK) { jput(&c->j, "rollback", "uncertain", r->staged, NULL); return end(c, WC_UNCERTAIN, "rollback", "discard-failed-staged-retained"); }
  }
  if (r->lease[0]) {
    if (c->p->release(c->p->context, r->lease) != WC_STEP_OK) {
      jput(&c->j, "release", "uncertain", r->lease, NULL); return end(c, WC_LEASE_RETAINED, "release", "rolled-back-lease-release-failed");
    }
    jput(&c->j, "release", "ok", r->lease, NULL); r->lease[0] = 0;
  }
  jput(&c->j, "rollback", "ok", NULL, NULL);
  return end(c, WC_ROLLED_BACK, "rollback", why);
}
/* After a proven publication: release lease, journal completion. */
static wc_status finish(cx *c) {
  wc_report *r = c->r;
  if (jput(&c->j, "release", "begin", r->lease, NULL)) return end(c, WC_LEASE_RETAINED, "release", "journal-write-failed-lease-retained");
  if (c->p->release(c->p->context, r->lease) != WC_STEP_OK) {
    jput(&c->j, "release", "uncertain", r->lease, NULL); return end(c, WC_LEASE_RETAINED, "release", "published-lease-release-failed");
  }
  jput(&c->j, "release", "ok", r->lease, NULL); r->lease[0] = 0;
  if (jput(&c->j, "complete", "ok", r->staged, r->content_digest)) return end(c, WC_UNCERTAIN, "complete", "journal-write-failed-after-release");
  return end(c, WC_COMPLETED, "complete", "published-and-released");
}

wc_status wc_run(const wc_binding *b, const wc_gates *g, const wc_provider *p, wc_sink sink, void *sctx, wc_report *r) {
  cx c; int pf; wc_step s; wc_pub pub = WC_PUB_UNKNOWN;
  if (!r) return WC_INTERNAL;
  memset(r, 0, sizeof *r); memset(&c, 0, sizeof c);
  if (!sink) { r->status = WC_REFUSED; snprintf(r->detail, sizeof r->detail, "no-journal-sink"); return r->status; }
  pf = preflight(b, g, p, 0, r);
  if (pf == 2 || (pf == 0 && !gates_valid(g))) { r->status = WC_REFUSED; if (!r->detail[0]) snprintf(r->detail, sizeof r->detail, "gate-evidence-invalid"); return r->status; }
  if (pf == 1) { r->status = WC_PENDING; snprintf(r->phase, sizeof r->phase, "preflight"); snprintf(r->detail, sizeof r->detail, "nothing-executed"); return r->status; }
  c.b = b; c.p = p; c.r = r; c.j.sink = sink; c.j.ctx = sctx; memcpy(c.j.prev, ZERO, 65);
  wc_binding_digest(b, c.j.bind);
  c.rows = calloc(EXR_WC_MAX_RECORDS, sizeof *c.rows);
  if (!c.rows) return end(&c, WC_INTERNAL, "init", "out-of-memory");

  if (jput(&c.j, "admit", "begin", NULL, NULL)) { free(c.rows); return end(&c, WC_REFUSED, "admit", "journal-write-failed"); }
  s = p->admit(p->context, b, r->lease);
  if (s != WC_STEP_OK) {
    if (s == WC_STEP_UNCERTAIN) { jput(&c.j, "admit", "uncertain", NULL, NULL); free(c.rows); return end(&c, WC_UNCERTAIN, "admit", "admission-outcome-unknown"); }
    jput(&c.j, "admit", "fail", NULL, NULL); r->lease[0] = 0; free(c.rows); return end(&c, WC_REFUSED, "admit", "admission-refused");
  }
  if (!hexn(r->lease, 48)) { r->lease[0] = 0; jput(&c.j, "admit", "uncertain", NULL, NULL); free(c.rows); return end(&c, WC_UNCERTAIN, "admit", "malformed-lease-identity"); }
  if (jput(&c.j, "admit", "ok", r->lease, NULL)) { c.p->release(p->context, r->lease); r->lease[0] = 0; free(c.rows); return end(&c, WC_UNCERTAIN, "admit", "journal-write-failed-after-admission"); }

  if (jput(&c.j, "snapshot", "begin", NULL, NULL)) { wc_status x = rollback(&c, "journal"); free(c.rows); return x; }
  s = p->snapshot(p->context, c.rows, EXR_WC_MAX_RECORDS, &c.n);
  if (s != WC_STEP_OK || !wc_snapshot_valid(c.rows, c.n) || !wc_snapshot_digest(b, c.rows, c.n, r->snapshot_digest)) {
    wc_status x; jput(&c.j, "snapshot", s == WC_STEP_UNCERTAIN ? "uncertain" : "fail", NULL, NULL);
    x = rollback(&c, s == WC_STEP_OK ? "snapshot-invalid" : "snapshot-failed"); free(c.rows); return x;
  }
  r->records = (unsigned)c.n; wc_content_digest(c.rows, c.n, r->content_digest);
  if (jput(&c.j, "snapshot", "ok", NULL, r->snapshot_digest)) { wc_status x = rollback(&c, "journal"); free(c.rows); return x; }

  if (jput(&c.j, "import", "begin", NULL, r->content_digest)) { wc_status x = rollback(&c, "journal"); free(c.rows); return x; }
  s = p->import(p->context, b, c.rows, c.n, r->staged);
  if (s != WC_STEP_OK) {
    wc_status x; int known = hexn(r->staged, 48);
    if (!known) r->staged[0] = 0;
    if (s == WC_STEP_UNCERTAIN) { jput(&c.j, "import", "uncertain", known ? r->staged : NULL, NULL); free(c.rows); return end(&c, WC_UNCERTAIN, "import", "import-outcome-unknown-staged-retained"); }
    jput(&c.j, "import", "fail", known ? r->staged : NULL, NULL); x = rollback(&c, "import-failed"); free(c.rows); return x;
  }
  if (!hexn(r->staged, 48)) { r->staged[0] = 0; jput(&c.j, "import", "uncertain", NULL, NULL); free(c.rows); return end(&c, WC_UNCERTAIN, "import", "malformed-staged-identity"); }
  if (jput(&c.j, "import", "ok", r->staged, r->content_digest)) { free(c.rows); return end(&c, WC_UNCERTAIN, "import", "journal-write-failed-staged-retained"); }

  if (jput(&c.j, "verify", "begin", r->staged, r->content_digest)) { free(c.rows); return end(&c, WC_UNCERTAIN, "verify", "journal-write-failed-staged-retained"); }
  s = p->verify(p->context, r->staged, c.rows, c.n);
  if (s != WC_STEP_OK) {
    wc_status x; jput(&c.j, "verify", s == WC_STEP_UNCERTAIN ? "uncertain" : "fail", r->staged, NULL);
    if (s == WC_STEP_UNCERTAIN) { free(c.rows); return end(&c, WC_UNCERTAIN, "verify", "verify-outcome-unknown-staged-retained"); }
    x = rollback(&c, "verify-mismatch"); free(c.rows); return x;
  }
  if (jput(&c.j, "verify", "ok", r->staged, r->content_digest)) { free(c.rows); return end(&c, WC_UNCERTAIN, "verify", "journal-write-failed-staged-retained"); }
  free(c.rows); c.rows = NULL;

  /* write-ahead: intent is durable before the publisher is called */
  if (jput(&c.j, "publish", "begin", r->staged, r->content_digest)) return rollback(&c, "journal-before-publish");
  s = p->publish(p->context, r->staged, &pub);
  if (s == WC_STEP_OK && pub == WC_PUB_YES) {
    if (jput(&c.j, "publish", "ok", r->staged, r->content_digest)) return end(&c, WC_UNCERTAIN, "publish", "published-but-journal-write-failed");
    return finish(&c);
  }
  if (s == WC_STEP_FAILED || (s == WC_STEP_OK && pub == WC_PUB_NO)) {
    jput(&c.j, "publish", "fail", r->staged, NULL); return rollback(&c, "publish-refused-nothing-published");
  }
  jput(&c.j, "publish", "uncertain", r->staged, NULL);
  return end(&c, WC_UNCERTAIN, "publish", "publication-state-unknown-everything-retained");
}

wc_status wc_recover(const wc_binding *b, const wc_gates *g, const wc_provider *p, const char *const *lines, size_t n,
                     wc_sink sink, void *sctx, wc_report *r) {
  jl rows[256]; cx c; char why[96]; int pf; size_t i; wc_pub pub = WC_PUB_UNKNOWN; wc_step s;
  int staged_known = 0, import_open = 0, admit_open = 0, published = 0, released = 0, rolled = 0, complete = 0, pub_open = 0;
  if (!r) return WC_INTERNAL;
  memset(r, 0, sizeof *r); memset(&c, 0, sizeof c);
  if (!sink) { r->status = WC_REFUSED; snprintf(r->detail, sizeof r->detail, "no-journal-sink"); return r->status; }
  pf = preflight(b, g, p, 1, r);
  if (pf == 2 || (pf == 0 && !gates_valid(g))) { r->status = WC_REFUSED; if (!r->detail[0]) snprintf(r->detail, sizeof r->detail, "gate-evidence-invalid"); return r->status; }
  if (pf == 1) { r->status = WC_PENDING; snprintf(r->phase, sizeof r->phase, "preflight"); snprintf(r->detail, sizeof r->detail, "nothing-executed"); return r->status; }
  if (!load(b, lines, n, rows, why, sizeof why)) { r->status = WC_REFUSED; snprintf(r->detail, sizeof r->detail, "journal-rejected:%s", why); return r->status; }
  c.b = b; c.p = p; c.r = r; c.j.sink = sink; c.j.ctx = sctx; c.j.seq = (unsigned)n;
  memcpy(c.j.prev, rows[n-1].seal, 65); memcpy(c.j.bind, rows[0].bind, 65);

  for (i = 0; i < n; i++) {
    const jl *e = &rows[i]; int ok = !strcmp(e->state, "ok"), begin = !strcmp(e->state, "begin");
    if (!strcmp(e->phase, "admit")) {
      admit_open = begin || !strcmp(e->state, "uncertain");
      if (ok) snprintf(r->lease, sizeof r->lease, "%s", e->id);
    } else if (!strcmp(e->phase, "snapshot") && ok) snprintf(r->snapshot_digest, sizeof r->snapshot_digest, "%s", e->sha);
    else if (!strcmp(e->phase, "import")) {
      if (begin) import_open = 1;
      else { import_open = strcmp(e->state, "uncertain") == 0 && !hexn(e->id, 48); if (strcmp(e->id, "-")) { snprintf(r->staged, sizeof r->staged, "%s", e->id); staged_known = 1; } if (strcmp(e->sha, "-")) snprintf(r->content_digest, sizeof r->content_digest, "%s", e->sha); }
    } else if (!strcmp(e->phase, "publish")) {
      pub_open = !ok && strcmp(e->state, "fail"); if (ok) published = 1;
      if (!strcmp(e->state, "fail")) published = 0;
    } else if (!strcmp(e->phase, "release") && ok) released = 1;
    else if (!strcmp(e->phase, "rollback") && ok) rolled = 1;
    else if (!strcmp(e->phase, "complete") && ok) complete = 1;
  }
  r->seq = c.j.seq;

  if (complete) {
    s = p->recover(p->context, r->staged, &pub);
    if (s == WC_STEP_OK && pub == WC_PUB_YES) return end(&c, WC_COMPLETED, "complete", "journal-complete-publisher-confirms");
    jput(&c.j, "recover", "uncertain", r->staged, NULL); return end(&c, WC_UNCERTAIN, "recover", "journal-complete-but-publisher-does-not-confirm");
  }
  if (rolled && (!r->lease[0] || released)) return end(&c, WC_ROLLED_BACK, "rollback", "journal-already-rolled-back");
  if (admit_open || import_open) {
    jput(&c.j, "recover", "uncertain", NULL, NULL);
    return end(&c, WC_UNCERTAIN, "recover", admit_open ? "lease-identity-unknown-retained" : "staged-identity-unknown-retained");
  }
  if (published || pub_open) {
    if (!staged_known) { jput(&c.j, "recover", "uncertain", NULL, NULL); return end(&c, WC_UNCERTAIN, "recover", "staged-identity-unknown-retained"); }
    if (jput(&c.j, "recover", "begin", r->staged, NULL)) return end(&c, WC_UNCERTAIN, "recover", "journal-write-failed");
    s = p->recover(p->context, r->staged, &pub);
    if (s == WC_STEP_OK && pub == WC_PUB_YES) {
      if (jput(&c.j, "publish", "ok", r->staged, r->content_digest)) return end(&c, WC_UNCERTAIN, "recover", "journal-write-failed-after-confirmation");
      if (!released) return finish(&c);
      jput(&c.j, "complete", "ok", r->staged, r->content_digest); return end(&c, WC_COMPLETED, "complete", "recovered-published");
    }
    if (s == WC_STEP_OK && pub == WC_PUB_NO && !published) {
      jput(&c.j, "publish", "fail", r->staged, NULL); return rollback(&c, "recovered-not-published");
    }
    jput(&c.j, "recover", "uncertain", r->staged, NULL);
    return end(&c, WC_UNCERTAIN, "recover", "publisher-cannot-decide-everything-retained");
  }
  if (r->lease[0] || staged_known) {
    if (r->lease[0] && released) r->lease[0] = 0;
    return rollback(&c, "recovered-before-publication");
  }
  return end(&c, WC_ROLLED_BACK, "recover", "nothing-to-recover");
}
