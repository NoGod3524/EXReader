/* SPDX-License-Identifier: MIT */
#include "opds_internal.h"
#include <ctype.h>

/* ---- arena ---- */
struct opds_arena *arena_new(void) {
  return (struct opds_arena *)calloc(1, sizeof(struct opds_arena));
}
void arena_free(struct opds_arena *a) {
  if (!a) return;
  for (opds_ablock *b = a->head; b;) { opds_ablock *n = b->next; free(b); b = n; }
  free(a);
}
void *arena_alloc(struct opds_arena *a, size_t size) {
  size = (size + 15) & ~(size_t)15;
  if (size == 0) size = 16;
  if (!a->head || a->head->cap - a->head->used < size) {
    size_t cap = size > 65536 ? size : 65536;
    opds_ablock *b = (opds_ablock *)malloc(sizeof(opds_ablock) + cap);
    if (!b) return NULL;
    b->next = a->head; b->used = 0; b->cap = cap; a->head = b;
  }
  void *p = (unsigned char *)(a->head + 1) + a->head->used;
  a->head->used += size; a->total += size;
  return p;
}
char *arena_strndup(struct opds_arena *a, const char *s, size_t n) {
  char *p = (char *)arena_alloc(a, n + 1);
  if (!p) return NULL;
  memcpy(p, s, n); p[n] = 0;
  return p;
}
char *arena_strdup(struct opds_arena *a, const char *s) { return arena_strndup(a, s, strlen(s)); }

/* ---- errors ---- */
void opds_set_error(opds_error *e, opds_status code, const char *fmt, ...) {
  va_list ap;
  if (!e) return;
  e->code = code;
  va_start(ap, fmt);
  vsnprintf(e->message, sizeof e->message, fmt, ap);
  va_end(ap);
}
opds_status opds_fail(opds_error *e, opds_status code, const char *fmt, ...) {
  va_list ap;
  if (e) {
    e->code = code;
    va_start(ap, fmt);
    vsnprintf(e->message, sizeof e->message, fmt, ap);
    va_end(ap);
  }
  return code;
}
const char *opds_status_name(opds_status s) {
  static const char *names[] = {"ok", "argument", "memory", "io", "format", "limit", "cancelled",
    "timeout", "http", "auth_required", "unsupported", "needs_host", "exists", "mismatch",
    "unreadable", "aborted"};
  return (unsigned)s < sizeof names / sizeof *names ? names[s] : "unknown";
}
void opds_limits_defaults(opds_limits *l) {
  l->max_feed_bytes = 4u << 20; l->max_elements = 200000; l->max_entries = 2000;
  l->max_links_per_entry = 128; l->max_depth = 48; l->max_redirects = 5; l->max_pages = 50;
  l->max_download_bytes = 256ull << 20; l->timeout_ms = 10000;
}

int buf_append(opds_buf *b, const void *data, size_t n) {
  if (b->size + n + 1 > b->cap) {
    size_t cap = b->cap ? b->cap : 4096;
    while (cap < b->size + n + 1) cap *= 2;
    unsigned char *p = (unsigned char *)realloc(b->data, cap);
    if (!p) return 0;
    b->data = p; b->cap = cap;
  }
  if (n) memcpy(b->data + b->size, data, n);
  b->size += n; b->data[b->size] = 0;
  return 1;
}
void buf_free(opds_buf *b) { free(b->data); b->data = NULL; b->size = b->cap = 0; }

int opds_ascii_ieq(const char *a, const char *b) {
  for (; *a && *b; a++, b++) if (tolower((unsigned char)*a) != tolower((unsigned char)*b)) return 0;
  return *a == *b;
}
int opds_ascii_iprefix(const char *s, const char *p) {
  for (; *p; s++, p++) if (tolower((unsigned char)*s) != tolower((unsigned char)*p)) return 0;
  return 1;
}

void opds_media_type(const char *v, char *out, size_t cap) {
  size_t n = 0;
  if (!cap) return;
  while (v && (*v == ' ' || *v == '\t')) v++;
  while (v && *v && *v != ';' && *v != ' ' && *v != '\t' && n + 1 < cap)
    out[n++] = (char)tolower((unsigned char)*v++);
  out[n] = 0;
}

/* ---- URLs ---- */
typedef struct {
  const char *s; size_t sn;
  const char *a; size_t an; int has_auth;
  const char *p; size_t pn;
  const char *q; size_t qn; int has_q;
} urlparts;

static void url_split(const char *u, urlparts *o) {
  size_t n = strlen(u), i = 0;
  const char *hash = (const char *)memchr(u, '#', n);
  const char *rest, *e;
  size_t rn;
  memset(o, 0, sizeof *o);
  if (hash) n = (size_t)(hash - u);
  if (n && isalpha((unsigned char)u[0])) {
    i = 1;
    while (i < n && (isalnum((unsigned char)u[i]) || u[i] == '+' || u[i] == '-' || u[i] == '.')) i++;
    if (i < n && u[i] == ':') { o->s = u; o->sn = i; i++; } else i = 0;
  }
  rest = u + i; rn = n - i;
  if (rn >= 2 && rest[0] == '/' && rest[1] == '/') {
    size_t k = 2;
    while (k < rn && rest[k] != '/' && rest[k] != '?') k++;
    o->a = rest + 2; o->an = k - 2; o->has_auth = 1;
    rest += k; rn -= k;
  }
  e = (const char *)memchr(rest, '?', rn);
  if (e) { o->p = rest; o->pn = (size_t)(e - rest); o->q = e + 1; o->qn = rn - o->pn - 1; o->has_q = 1; }
  else { o->p = rest; o->pn = rn; }
}

static void remove_dots(char *path) {
  size_t n = strlen(path);
  char *out = (char *)malloc(n + 2), *in = path;
  size_t o = 0;
  if (!out) return;
  while (*in) {
    if (!strncmp(in, "../", 3)) in += 3;
    else if (!strncmp(in, "./", 2)) in += 2;
    else if (!strncmp(in, "/./", 3)) in += 2;
    else if (!strcmp(in, "/.")) { in += 1; *in = '/'; }
    else if (!strncmp(in, "/../", 4) || !strcmp(in, "/..")) {
      int last = in[3] == 0;
      while (o && out[o - 1] != '/') o--;
      if (o) o--;
      if (last) { in += 2; *in = '/'; } else in += 3;
    } else if (!strcmp(in, ".") || !strcmp(in, "..")) in += strlen(in);
    else {
      out[o++] = *in++;
      while (*in && *in != '/') out[o++] = *in++;
    }
  }
  out[o] = 0;
  memcpy(path, out, o + 1);
  free(out);
}

static int xdigit_ok(int c) { return isxdigit((unsigned char)c); }

static int url_encode(const char *in, int keep_braces, char *out, size_t cap) {
  size_t o = 0;
  static const char hex[] = "0123456789ABCDEF";
  for (; *in; in++) {
    unsigned char c = (unsigned char)*in;
    int pass;
    if (c == '%' && xdigit_ok(in[1]) && xdigit_ok(in[2])) pass = 1;
    else if (c == '%') pass = 0;
    else if (c <= 0x20 || c >= 0x7f || strchr("\"<>\\^`|", c)) pass = 0;
    else if ((c == '{' || c == '}') && !keep_braces) pass = 0;
    else pass = 1;
    if (pass) { if (o + 2 > cap) return 0; out[o++] = (char)c; }
    else { if (o + 4 > cap) return 0; out[o++] = '%'; out[o++] = hex[c >> 4]; out[o++] = hex[c & 15]; }
  }
  if (o + 1 > cap) return 0;
  out[o] = 0;
  return 1;
}

opds_status opds_url_resolve_ex(const char *base, const char *ref, int keep_braces,
                                char *out, size_t cap) {
  urlparts r, b = {0};
  size_t need = strlen(ref) + (base ? strlen(base) : 0) + 16;
  char *work = (char *)malloc(need * 2), *path = (char *)malloc(need), *comp;
  opds_status st = OPDS_OK;
  const char *sc, *au, *qy; size_t scn, aun, qyn; int has_auth, has_q;
  size_t w = 0;
  if (!work || !path) { free(work); free(path); return OPDS_MEMORY; }
  comp = work;
  url_split(ref, &r);
  if (base) url_split(base, &b);
  if (r.sn) {
    sc = r.s; scn = r.sn; au = r.a; aun = r.an; has_auth = r.has_auth;
    memcpy(path, r.p, r.pn); path[r.pn] = 0; remove_dots(path);
    qy = r.q; qyn = r.qn; has_q = r.has_q;
  } else if (!base || !b.sn) {
    /* no usable base: keep the reference, only normalise bytes */
    sc = NULL; scn = 0; au = r.a; aun = r.an; has_auth = r.has_auth;
    memcpy(path, r.p, r.pn); path[r.pn] = 0;
    qy = r.q; qyn = r.qn; has_q = r.has_q;
  } else {
    sc = b.s; scn = b.sn;
    if (r.has_auth) {
      au = r.a; aun = r.an; has_auth = 1;
      memcpy(path, r.p, r.pn); path[r.pn] = 0; remove_dots(path);
      qy = r.q; qyn = r.qn; has_q = r.has_q;
    } else {
      au = b.a; aun = b.an; has_auth = b.has_auth;
      if (r.pn == 0) {
        memcpy(path, b.p, b.pn); path[b.pn] = 0;
        if (r.has_q) { qy = r.q; qyn = r.qn; has_q = 1; } else { qy = b.q; qyn = b.qn; has_q = b.has_q; }
      } else {
        if (r.p[0] == '/') { memcpy(path, r.p, r.pn); path[r.pn] = 0; }
        else {
          size_t keep = b.pn;
          if (b.has_auth && b.pn == 0) { path[0] = '/'; keep = 1; memcpy(path + 1, r.p, r.pn); path[1 + r.pn] = 0; }
          else {
            while (keep && b.p[keep - 1] != '/') keep--;
            memcpy(path, b.p, keep); memcpy(path + keep, r.p, r.pn); path[keep + r.pn] = 0;
          }
        }
        remove_dots(path);
        qy = r.q; qyn = r.qn; has_q = r.has_q;
      }
    }
  }
  for (size_t i = 0; i < scn; i++) comp[w++] = (char)tolower((unsigned char)sc[i]);
  if (scn) comp[w++] = ':';
  if (has_auth) { comp[w++] = '/'; comp[w++] = '/'; memcpy(comp + w, au, aun); w += aun; }
  { size_t pl = strlen(path); memcpy(comp + w, path, pl); w += pl; }
  if (has_q) { comp[w++] = '?'; memcpy(comp + w, qy, qyn); w += qyn; }
  comp[w] = 0;
  if (!url_encode(comp, keep_braces, out, cap)) st = OPDS_LIMIT;
  free(work); free(path);
  return st;
}
opds_status opds_url_resolve(const char *base, const char *ref, char *out, size_t cap) {
  return opds_url_resolve_ex(base, ref, 0, out, cap);
}

int opds_url_origin(const char *url, char *out, size_t cap) {
  urlparts u;
  char host[300];
  const char *a, *colon = NULL;
  size_t an, hn, i;
  url_split(url, &u);
  if (!u.sn || !u.has_auth) return 0;
  a = u.a; an = u.an;
  for (i = 0; i < an; i++) if (a[i] == '@') { a += i + 1; an -= i + 1; break; }
  if (an && a[0] == '[') {
    for (i = 0; i < an; i++) if (a[i] == ']') break;
    if (i + 1 < an && a[i + 1] == ':') colon = a + i + 1;
  } else {
    for (i = an; i > 0; i--) if (a[i - 1] == ':') { colon = a + i - 1; break; }
  }
  hn = colon ? (size_t)(colon - a) : an;
  if (hn == 0 || hn >= sizeof host) return 0;
  for (i = 0; i < hn; i++) host[i] = (char)tolower((unsigned char)a[i]);
  host[hn] = 0;
  {
    char scheme[16];
    int port = 0, n;
    if (u.sn >= sizeof scheme) return 0;
    for (i = 0; i < u.sn; i++) scheme[i] = (char)tolower((unsigned char)u.s[i]);
    scheme[u.sn] = 0;
    if (colon) { for (i = 1; i < an - hn; i++) { if (!isdigit((unsigned char)colon[i])) return 0; port = port * 10 + (colon[i] - '0'); if (port > 65535) return 0; } }
    else port = !strcmp(scheme, "https") ? 443 : 80;
    n = snprintf(out, cap, "%s://%s:%d", scheme, host, port);
    return n > 0 && (size_t)n < cap;
  }
}

/* ---- templates ---- */
static int enc_append(char *out, size_t cap, size_t *o, const char *v) {
  static const char hex[] = "0123456789ABCDEF";
  for (; *v; v++) {
    unsigned char c = (unsigned char)*v;
    if (isalnum(c) || c == '-' || c == '.' || c == '_' || c == '~') {
      if (*o + 2 > cap) return 0; out[(*o)++] = (char)c;
    } else {
      if (*o + 4 > cap) return 0;
      out[(*o)++] = '%'; out[(*o)++] = hex[c >> 4]; out[(*o)++] = hex[c & 15];
    }
  }
  return 1;
}
static int is_terms_name(const char *n, size_t l) {
  static const char *names[] = {"searchTerms", "query", "q", "terms", "keyword", "search"};
  for (size_t i = 0; i < sizeof names / sizeof *names; i++)
    if (strlen(names[i]) == l && !strncmp(n, names[i], l)) return 1;
  return 0;
}
static int is_page_name(const char *n, size_t l) {
  return (l == 9 && !strncmp(n, "startPage", 9)) || (l == 4 && !strncmp(n, "page", 4));
}

opds_status opds_template_expand(const char *t, const char *terms, unsigned page,
                                 char *out, size_t cap, opds_error *error) {
  size_t o = 0;
  while (*t) {
    if (*t != '{') {
      if (*t == '}' ) return opds_fail(error, OPDS_FORMAT, "unbalanced '}' in template");
      if (o + 2 > cap) return opds_fail(error, OPDS_LIMIT, "expanded URL too long");
      out[o++] = *t++; continue;
    }
    {
      const char *end = strchr(t, '}'), *p = t + 1;
      char op = 0;
      int first = 1;
      if (!end) return opds_fail(error, OPDS_FORMAT, "unterminated template expression");
      if (*p == '?' || *p == '&') op = *p++;
      else if (*p == '+' || *p == '#' || *p == '/' || *p == '.' || *p == ';')
        return opds_fail(error, OPDS_UNSUPPORTED, "template operator '%c' is not supported", *p);
      while (p < end) {
        const char *q = p;
        size_t l;
        int optional = 0, defined = 0;
        char valbuf[16];
        const char *val = NULL;
        while (q < end && *q != ',') q++;
        l = (size_t)(q - p);
        if (l && p[l - 1] == '?') { optional = 1; l--; }
        if (l && p[l - 1] == '*') l--;
        for (size_t k = 0; k < l; k++) if (p[k] == ':') { l = k; break; }
        if (l == 0) return opds_fail(error, OPDS_FORMAT, "empty template variable");
        if (is_terms_name(p, l)) {
          if (!terms) return opds_fail(error, OPDS_ARGUMENT, "search terms required");
          val = terms; defined = 1;
        } else if (is_page_name(p, l)) {
          if (page) { snprintf(valbuf, sizeof valbuf, "%u", page); val = valbuf; defined = 1; }
          else if (!op && !optional) { val = "1"; defined = 1; }
        } else if (!op && !optional) {
          return opds_fail(error, OPDS_UNSUPPORTED, "required template variable has no value");
        }
        if (defined) {
          if (op) {
            char sep = first ? (op == '?' && o && memchr(out, '?', o) ? '&' : op) : '&';
            if (o + 2 > cap) return opds_fail(error, OPDS_LIMIT, "expanded URL too long");
            out[o++] = sep;
            for (size_t k = 0; k < l; k++) { if (o + 2 > cap) return opds_fail(error, OPDS_LIMIT, "expanded URL too long"); out[o++] = p[k]; }
            out[o++] = '=';
            first = 0;
          }
          if (!enc_append(out, cap, &o, val)) return opds_fail(error, OPDS_LIMIT, "expanded URL too long");
        }
        p = q < end ? q + 1 : q;
      }
      t = end + 1;
    }
  }
  if (o + 1 > cap) return opds_fail(error, OPDS_LIMIT, "expanded URL too long");
  out[o] = 0;
  return OPDS_OK;
}

/* ---- log redaction ---- */
void opds_redact_url(const char *url, char *out, size_t cap) {
  size_t o = 0;
  const char *p = url, *q = strchr(url, '?'), *auth = strstr(url, "://");
  static const char *secret[] = {"token", "password", "passwd", "secret", "key", "auth", "sig", "session", "credential"};
  if (!cap) return;
  if (auth) {
    const char *host = auth + 3, *slash = host;
    while (*slash && *slash != '/' && *slash != '?') slash++;
    const char *at = NULL;
    for (const char *c = host; c < slash; c++) if (*c == '@') at = c;
    if (at) {
      size_t head = (size_t)(host - url);
      for (size_t i = 0; i < head && o + 1 < cap; i++) out[o++] = url[i];
      p = at + 1;
    }
  }
  {
    const char *stop = q ? q : p + strlen(p);
    while (p < stop && o + 1 < cap) out[o++] = *p++;
  }
  if (q) {
    p = q; if (o + 1 < cap) out[o++] = *p++;
    while (*p && o + 1 < cap) {
      const char *amp = strchr(p, '&'), *eq = strchr(p, '=');
      size_t seg = amp ? (size_t)(amp - p) : strlen(p);
      int hide = 0;
      if (eq && (!amp || eq < amp)) {
        size_t kl = (size_t)(eq - p);
        for (size_t i = 0; i < sizeof secret / sizeof *secret && !hide; i++) {
          size_t sl = strlen(secret[i]);
          for (size_t k = 0; k + sl <= kl; k++) {
            size_t j = 0;
            while (j < sl && tolower((unsigned char)p[k + j]) == secret[i][j]) j++;
            if (j == sl) { hide = 1; break; }
          }
        }
        if (hide) {
          for (size_t i = 0; i <= kl && o + 1 < cap; i++) out[o++] = p[i];
          for (const char *r = "REDACTED"; *r && o + 1 < cap; r++) out[o++] = *r;
        }
      }
      if (!hide) for (size_t i = 0; i < seg && o + 1 < cap; i++) out[o++] = p[i];
      p += seg;
      if (*p == '&') { if (o + 1 < cap) out[o++] = '&'; p++; }
    }
  }
  out[o] = 0;
}

/* ---- SHA-256 ---- */
typedef opds_sha sha_ctx;
static const uint32_t K256[64] = {
  0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
  0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
  0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
  0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
  0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
  0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
  0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
  0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2};
#define ROR(x, n) (((x) >> (n)) | ((x) << (32 - (n))))
static void sha_block(sha_ctx *c, const unsigned char *p) {
  uint32_t w[64], a, b, cc, d, e, f, g, h;
  for (int i = 0; i < 16; i++)
    w[i] = (uint32_t)p[i*4] << 24 | (uint32_t)p[i*4+1] << 16 | (uint32_t)p[i*4+2] << 8 | p[i*4+3];
  for (int i = 16; i < 64; i++) {
    uint32_t s0 = ROR(w[i-15], 7) ^ ROR(w[i-15], 18) ^ (w[i-15] >> 3);
    uint32_t s1 = ROR(w[i-2], 17) ^ ROR(w[i-2], 19) ^ (w[i-2] >> 10);
    w[i] = w[i-16] + s0 + w[i-7] + s1;
  }
  a = c->h[0]; b = c->h[1]; cc = c->h[2]; d = c->h[3]; e = c->h[4]; f = c->h[5]; g = c->h[6]; h = c->h[7];
  for (int i = 0; i < 64; i++) {
    uint32_t t1 = h + (ROR(e, 6) ^ ROR(e, 11) ^ ROR(e, 25)) + ((e & f) ^ (~e & g)) + K256[i] + w[i];
    uint32_t t2 = (ROR(a, 2) ^ ROR(a, 13) ^ ROR(a, 22)) + ((a & b) ^ (a & cc) ^ (b & cc));
    h = g; g = f; f = e; e = d + t1; d = cc; cc = b; b = a; a = t1 + t2;
  }
  c->h[0] += a; c->h[1] += b; c->h[2] += cc; c->h[3] += d; c->h[4] += e; c->h[5] += f; c->h[6] += g; c->h[7] += h;
}
void opds_sha_init(opds_sha *c) {
  static const uint32_t iv[8] = {0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19};
  memcpy(c->h, iv, sizeof iv); c->len = 0; c->n = 0;
}
void opds_sha_update(opds_sha *c, const void *data, size_t size) {
  const unsigned char *p = (const unsigned char *)data;
  c->len += size;
  while (size) {
    size_t k = 64 - c->n;
    if (k > size) k = size;
    memcpy(c->buf + c->n, p, k); c->n += k; p += k; size -= k;
    if (c->n == 64) { sha_block(c, c->buf); c->n = 0; }
  }
}
void opds_sha_final_hex(opds_sha *c, char out[65]) {
  uint64_t bits = c->len * 8;
  unsigned char pad = 0x80, z = 0, lenb[8];
  static const char hex[] = "0123456789abcdef";
  opds_sha_update(c, &pad, 1);
  while (c->n != 56) opds_sha_update(c, &z, 1);
  for (int i = 0; i < 8; i++) lenb[i] = (unsigned char)(bits >> (56 - 8 * i));
  opds_sha_update(c, lenb, 8);
  for (int i = 0; i < 8; i++)
    for (int j = 0; j < 4; j++) {
      unsigned char byte = (unsigned char)(c->h[i] >> (24 - 8 * j));
      out[i * 8 + j * 2] = hex[byte >> 4]; out[i * 8 + j * 2 + 1] = hex[byte & 15];
    }
  out[64] = 0;
}
void opds_sha256_hex(const void *data, size_t size, char out[65]) {
  sha_ctx c;
  opds_sha_init(&c); opds_sha_update(&c, data, size); opds_sha_final_hex(&c, out);
}
