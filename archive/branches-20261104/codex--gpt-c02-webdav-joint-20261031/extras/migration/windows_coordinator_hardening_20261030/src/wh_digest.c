/* SPDX-License-Identifier: MIT */
#include "exr_wh.h"
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
void wh_sha256_hex(const void *data, size_t size, char out[65]) { sha s; sha_init(&s); sha_add(&s, data, size); sha_hex(&s, out); }

/* ---- validation ---- */
static int hexn(const char *s, size_t n) {
  size_t i; if (!s) return 0;
  for (i = 0; i < n; i++) if (!((s[i] >= '0' && s[i] <= '9') || (s[i] >= 'a' && s[i] <= 'f'))) return 0;
  return s[n] == 0;
}
static size_t bounded(const char *s,size_t cap){size_t n=0;while(n<cap&&s[n])n++;return n;}
static int digitsn(const char *s, size_t max) {
  size_t i, n = s ? bounded(s,max+1) : 0; if (!n || n > max) return 0;
  for (i = 0; i < n; i++) if (s[i] < '0' || s[i] > '9') return 0;
  return 1;
}
static int token(const char *s, size_t max) {
  size_t i, n = s ? bounded(s,max+1) : 0; if (!n || n > max) return 0;
  for (i = 0; i < n; i++) { char c = s[i]; if (!((c>='a'&&c<='z')||(c>='A'&&c<='Z')||(c>='0'&&c<='9')||c=='.'||c=='_'||c=='-')) return 0; }
  return 1;
}
int wh_binding_valid(const wh_binding *b) {
  return b && hexn(b->source, 40) && digitsn(b->run, 20) && digitsn(b->attempt, 3) && hexn(b->artifact, 64) &&
         token(b->platform, 31) && token(b->sdk, 63) && hexn(b->provider, 64);
}
int wh_binding_digest(const wh_binding *b, char out[65]) {
  char text[400];
  if (!wh_binding_valid(b)) return 0;
  snprintf(text, sizeof text, "EXRWC-BIND1\nsource=%s\nrun=%s\nattempt=%s\nartifact=%s\nplatform=%s\nsdk=%s\nprovider=%s\n",
           b->source, b->run, b->attempt, b->artifact, b->platform, b->sdk, b->provider);
  wh_sha256_hex(text, strlen(text), out); return 1;
}
static int path_ok(const char *p) {
  size_t i, n = p ? bounded(p,EXR_WH_PATH_MAX) : 0, start = 0;
  if (!n || n >= EXR_WH_PATH_MAX) return 0;
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
int wh_snapshot_valid(const wh_record *r, size_t n) {
  size_t i; if (!r || !n || n > EXR_WH_MAX_RECORDS) return 0;
  for (i = 0; i < n; i++) {
    if (!hexn(r[i].id, 48) || !hexn(r[i].sha, 64) || !path_ok(r[i].path)) return 0;
    if (i && strcmp(r[i-1].path, r[i].path) >= 0) return 0;
  }
  return 1;
}
static void digest_rows(const char *head, const wh_record *r, size_t n, int ids, char out[65]) {
  sha s; size_t i; char line[EXR_WH_PATH_MAX + 200]; int k;
  sha_init(&s); sha_add(&s, head, strlen(head));
  for (i = 0; i < n; i++) {
    k = snprintf(line, sizeof line, "%s%s%s %llu %s %s\n", ids ? r[i].id : "", ids ? " " : "", "f",
                 (unsigned long long)r[i].size, r[i].sha, r[i].path);
    sha_add(&s, line, (size_t)k);
  }
  sha_hex(&s, out);
}
int wh_snapshot_digest(const wh_binding *b, const wh_record *r, size_t n, char out[65]) {
  char head[120], bd[65];
  if (!wh_snapshot_valid(r, n) || !wh_binding_digest(b, bd)) return 0;
  snprintf(head, sizeof head, "EXRWC-SNAP1 %s %zu\n", bd, n); digest_rows(head, r, n, 1, out); return 1;
}
int wh_content_digest(const wh_record *r, size_t n, char out[65]) {
  char head[40]; if (!wh_snapshot_valid(r, n)) return 0;
  snprintf(head, sizeof head, "EXRWC-CONTENT1 %zu\n", n); digest_rows(head, r, n, 0, out); return 1;
}
const char *wh_status_name(wh_status s) {
  static const char *names[] = {"completed","pending","refused","rolled_back","uncertain","lease_retained","internal"};
  return (unsigned)s < 7 ? names[s] : "internal";
}

