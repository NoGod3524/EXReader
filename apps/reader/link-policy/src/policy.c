/* SPDX-License-Identifier: MIT */
#include "reader_link_policy.h"

#include <stdlib.h>
#include <string.h>

#ifdef READER_LINK_POLICY_TEST_HOOKS
#include "test_hooks.h"
static int g_track;
static long g_fail_at, g_allocs, g_live;
void rlp_test_begin(long fail_at) { g_track = 1; g_fail_at = fail_at; g_allocs = 0; g_live = 0; }
void rlp_test_end(void) { g_track = 0; }
long rlp_test_allocations(void) { return g_allocs; }
long rlp_test_live(void) { return g_live; }
#endif

static void *rlp_alloc(size_t n) {
  void *p;
#ifdef READER_LINK_POLICY_TEST_HOOKS
  if (g_track) {
    g_allocs++;
    if (g_fail_at && g_allocs == g_fail_at) return NULL;
  }
#endif
  p = malloc(n ? n : 1);
#ifdef READER_LINK_POLICY_TEST_HOOKS
  if (p && g_track) g_live++;
#endif
  return p;
}

static void rlp_free(void *p) {
  if (!p) return;
#ifdef READER_LINK_POLICY_TEST_HOOKS
  if (g_track) g_live--;
#endif
  free(p);
}

struct reader_link_policy {
  uint32_t max_input;
  size_t scheme_count;
  char schemes[READER_LINK_MAX_SCHEMES][READER_LINK_SCHEME_BYTES];
};

typedef struct {
  reader_link_action action;
  reader_link_reason reason;
  reader_link_kind kind;
  uint32_t flags;
  char scheme[READER_LINK_SCHEME_BYTES];
  size_t path_len, fragment_offset, fragment_len;
} verdict;

static void report(reader_link_error *e, reader_link_status s, size_t offset, const char *message) {
  size_t n;
  if (!e || e->struct_size != sizeof(*e)) return;
  e->status = s;
  e->offset = offset;
  n = strlen(message);
  if (n >= sizeof(e->message)) n = sizeof(e->message) - 1;
  memcpy(e->message, message, n);
  e->message[n] = 0;
}

static unsigned char lower(unsigned char c) { return (c >= 'A' && c <= 'Z') ? (unsigned char)(c + 32) : c; }
static int is_alpha(unsigned char c) { return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z'); }
static int is_digit(unsigned char c) { return c >= '0' && c <= '9'; }
static int is_hex(unsigned char c) {
  return is_digit(c) || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F');
}
static unsigned hex_value(unsigned char c) {
  if (is_digit(c)) return (unsigned)(c - '0');
  return (unsigned)(lower(c) - 'a') + 10u;
}

/* Strict UTF-8 decoder (no overlong, surrogate or > U+10FFFF). */
typedef struct { unsigned need; uint32_t cp, min; } u8state;
/* Feeds one byte; returns 0 on invalid. *done is set and *cp filled when a code
   point completed. */
static int u8_feed(u8state *s, unsigned char b, int *done, uint32_t *cp) {
  *done = 0;
  if (s->need) {
    if ((b & 0xC0u) != 0x80u) return 0;
    s->cp = (s->cp << 6) | (uint32_t)(b & 0x3Fu);
    if (--s->need == 0) {
      if (s->cp < s->min || s->cp > 0x10FFFFu || (s->cp >= 0xD800u && s->cp <= 0xDFFFu)) return 0;
      *done = 1;
      *cp = s->cp;
    }
    return 1;
  }
  if (b < 0x80u) { *done = 1; *cp = b; return 1; }
  if (b >= 0xC2u && b <= 0xDFu) { s->need = 1; s->cp = (uint32_t)(b & 0x1Fu); s->min = 0x80u; return 1; }
  if (b >= 0xE0u && b <= 0xEFu) { s->need = 2; s->cp = (uint32_t)(b & 0x0Fu); s->min = 0x800u; return 1; }
  if (b >= 0xF0u && b <= 0xF4u) { s->need = 3; s->cp = (uint32_t)(b & 0x07u); s->min = 0x10000u; return 1; }
  return 0;
}

/* Controls, invisible and bidi-steering code points plus Unicode spaces. */
static int spoof_cp(uint32_t c) {
  return c < 0x20u || c == 0x7Fu || (c >= 0x80u && c <= 0x9Fu) || c == 0xA0u || c == 0x1680u ||
         c == 0x180Eu || (c >= 0x2000u && c <= 0x200Fu) || c == 0x2028u || c == 0x2029u ||
         (c >= 0x202Au && c <= 0x202Fu) || c == 0x205Fu || c == 0x2060u ||
         (c >= 0x2066u && c <= 0x2069u) || c == 0x3000u || c == 0xFEFFu;
}

static const char *const k_denied[] = {
  "javascript", "vbscript", "jscript", "livescript", "mocha", "data", "file", "blob",
  "filesystem", "about", "jar", "view-source", "shell", "search-ms", "search", "wyciwyg",
  "intent", "content", "chrome", "res", "resource", "cmd", "powershell", "wscript",
  "cscript", "mshta", "ssh", "telnet", "smb", "ldap"
};

/* a[0,n) compared case-insensitively with the NUL-terminated b. */
static int equals_ci(const char *a, size_t n, const char *b) {
  size_t i;
  if (strlen(b) != n) return 0;
  for (i = 0; i < n; i++)
    if (lower((unsigned char)a[i]) != lower((unsigned char)b[i])) return 0;
  return 1;
}

static int scheme_syntax(const char *s, size_t n) {
  size_t i;
  if (n == 0 || !is_alpha((unsigned char)s[0])) return 0;
  for (i = 1; i < n; i++) {
    unsigned char c = (unsigned char)s[i];
    if (!is_alpha(c) && !is_digit(c) && c != '+' && c != '-' && c != '.') return 0;
  }
  return 1;
}

static int scheme_denied(const char *s, size_t n) {
  size_t i;
  if (n == 1) return 1; /* drive-letter paths such as C:/ */
  if (n >= 3 && lower((unsigned char)s[0]) == 'm' && lower((unsigned char)s[1]) == 's' && s[2] == '-') return 1;
  for (i = 0; i < sizeof(k_denied) / sizeof(k_denied[0]); i++)
    if (equals_ci(s, n, k_denied[i])) return 1;
  return 0;
}

static int scheme_allowed(const reader_link_policy *p, const char *s, size_t n) {
  size_t i;
  if (equals_ci(s, n, "http") || equals_ci(s, n, "https") || equals_ci(s, n, "mailto")) return 1;
  for (i = 0; i < p->scheme_count; i++)
    if (equals_ci(s, n, p->schemes[i])) return 1;
  return 0;
}

reader_link_status reader_link_policy_create(const reader_link_policy_options *options,
                                             reader_link_policy **out, reader_link_error *error) {
  reader_link_policy *p;
  size_t i;
  if (!out) return READER_LINK_ARGUMENT;
  *out = NULL;
  if (options && (options->struct_size != sizeof(*options) ||
                  options->max_input_bytes > READER_LINK_MAX_INPUT_BYTES ||
                  options->scheme_count > READER_LINK_MAX_SCHEMES ||
                  (options->scheme_count && !options->schemes))) {
    report(error, READER_LINK_ARGUMENT, 0, "invalid policy options");
    return READER_LINK_ARGUMENT;
  }
  p = (reader_link_policy *)rlp_alloc(sizeof(*p));
  if (!p) {
    report(error, READER_LINK_MEMORY, 0, "policy allocation failed");
    return READER_LINK_MEMORY;
  }
  memset(p, 0, sizeof(*p));
  p->max_input = (options && options->max_input_bytes) ? options->max_input_bytes : READER_LINK_DEFAULT_INPUT_BYTES;
  for (i = 0; options && i < options->scheme_count; i++) {
    const char *s = options->schemes[i];
    size_t n = s ? strlen(s) : 0, k;
    if (!s || n >= READER_LINK_SCHEME_BYTES || !scheme_syntax(s, n) || scheme_denied(s, n)) {
      rlp_free(p);
      report(error, READER_LINK_ARGUMENT, i, "scheme is invalid or on the hard deny list");
      return READER_LINK_ARGUMENT;
    }
    for (k = 0; k < n; k++) p->schemes[i][k] = (char)lower((unsigned char)s[k]);
    p->scheme_count = i + 1;
  }
  *out = p;
  return READER_LINK_OK;
}

void reader_link_policy_destroy(reader_link_policy *policy) { rlp_free(policy); }

const char *reader_link_action_name(reader_link_action a) {
  switch (a) {
    case READER_LINK_ACTION_REJECT: return "REJECT";
    case READER_LINK_ACTION_INTERNAL: return "INTERNAL";
    case READER_LINK_ACTION_NEEDS_HOST: return "NEEDS_HOST";
  }
  return "UNKNOWN";
}

const char *reader_link_reason_name(reader_link_reason r) {
  static const char *const names[] = {
    "NONE", "EMPTY", "TOO_LONG", "INVALID_UTF8", "CONTROL", "SPACE", "BACKSLASH", "BAD_ESCAPE",
    "ENCODED_CONTROL", "ENCODED_SEPARATOR", "ENCODED_DOT", "DOUBLE_ESCAPE", "FORBIDDEN_SCHEME",
    "UNKNOWN_SCHEME", "BAD_SCHEME", "PROTOCOL_RELATIVE", "ABSOLUTE_PATH", "PATH_ESCAPE",
    "BAD_AUTHORITY", "USERINFO", "BAD_PATH_CHAR", "MALFORMED"
  };
  if ((unsigned)r < sizeof(names) / sizeof(names[0])) return names[r];
  return "UNKNOWN";
}

static void reject(verdict *v, reader_link_reason why) {
  v->action = READER_LINK_ACTION_REJECT;
  v->reason = why;
  v->kind = READER_LINK_KIND_NONE;
  v->flags = 0;
  v->scheme[0] = 0;
  v->path_len = v->fragment_offset = v->fragment_len = 0;
}

static int should_stop(const reader_link_control *c) { return c && c->cancelled && c->cancelled(c->context); }

/* Directory depth of the containing document's path, or -1 when invalid. */
static long base_depth(const char *base) {
  size_t i = 0, n, depth = 0;
  if (!base) return 0;
  n = strlen(base);
  if (n >= READER_LINK_INTERNAL_PART_LIMIT || (n && base[0] == '/')) return -1;
  for (i = 0; i < n; i++) {
    unsigned char c = (unsigned char)base[i];
    if (c < 0x20u || c == 0x7Fu || c == '\\') return -1;
  }
  i = 0;
  while (i < n) {
    size_t start = i, len;
    while (i < n && base[i] != '/') i++;
    len = i - start;
    if (i >= n) break; /* the last component is the file name, not a directory */
    i++;
    if (len == 2 && base[start] == '.' && base[start + 1] == '.') return -1;
    if (len && !(len == 1 && base[start] == '.')) depth++;
  }
  return (long)depth;
}

/* Validates every %XX in s[0,n). control_ok allows encoded controls other than
   NUL (external query data such as mailto bodies). */
static int check_escapes(const char *s, size_t n, int control_ok, reader_link_reason *why) {
  size_t i;
  for (i = 0; i < n; i++) {
    if (s[i] == '%') {
      unsigned v;
      if (n - i < 3 || !is_hex((unsigned char)s[i + 1]) || !is_hex((unsigned char)s[i + 2])) {
        *why = READER_LINK_REASON_BAD_ESCAPE;
        return 0;
      }
      v = hex_value((unsigned char)s[i + 1]) * 16u + hex_value((unsigned char)s[i + 2]);
      if (v == 0 || (!control_ok && (v < 0x20u || v == 0x7Fu))) {
        *why = READER_LINK_REASON_ENCODED_CONTROL;
        return 0;
      }
      i += 2;
    }
  }
  return 1;
}

static int check_fragment_bytes(const char *s, size_t n, reader_link_reason *why);

static void external(const char *t, size_t n, size_t colon, verdict *v) {
  const char *rest = t + colon + 1;
  size_t rest_len = n - colon - 1, i, hash = SIZE_MAX;
  reader_link_reason why = READER_LINK_REASON_NONE;
  int hier;
  for (i = 0; i < n; i++)
    if (t[i] == ' ') { reject(v, READER_LINK_REASON_SPACE); return; }
  if (!rest_len) { reject(v, READER_LINK_REASON_MALFORMED); return; }
  {
    size_t hash_at = SIZE_MAX, query = SIZE_MAX, head_len, k;
    for (k = 0; k < rest_len; k++)
      if (rest[k] == '#') { hash_at = k; break; }
    head_len = (hash_at == SIZE_MAX) ? rest_len : hash_at;
    /* A '?' only starts query data before the fragment; a '?' inside a
       fragment is literal text. */
    for (k = 0; k < head_len; k++)
      if (rest[k] == '?') { query = k; break; }
    /* Encoded controls are query data only (for example a mailto body), and
       that region ends at the first '#'. The authority, the path and the
       fragment itself must never carry them. */
    if (query == SIZE_MAX) {
      if (!check_escapes(rest, head_len, 0, &why)) { reject(v, why); return; }
    } else {
      if (!check_escapes(rest, query, 0, &why)) { reject(v, why); return; }
      if (!check_escapes(rest + query + 1, head_len - query - 1, 1, &why)) {
        reject(v, why);
        return;
      }
    }
    if (hash_at != SIZE_MAX &&
        !check_fragment_bytes(rest + hash_at + 1, rest_len - hash_at - 1, &why)) {
      reject(v, why);
      return;
    }
  }
  for (i = 0; i < rest_len; i++)
    if (rest[i] == '#') { hash = i; break; }
  if (hash != SIZE_MAX) {
    size_t k;
    for (k = hash + 1; k < rest_len; k++)
      if (rest[k] == '#') { reject(v, READER_LINK_REASON_MALFORMED); return; }
  }
  hier = equals_ci(t, colon, "http") || equals_ci(t, colon, "https");
  if (hier) {
    size_t end, host_end = 0, port_start = 0, alen;
    const char *auth;
    if (rest_len < 2 || rest[0] != '/' || rest[1] != '/') { reject(v, READER_LINK_REASON_MALFORMED); return; }
    end = 2;
    while (end < rest_len && rest[end] != '/' && rest[end] != '?' && rest[end] != '#') end++;
    if (end == 2) { reject(v, READER_LINK_REASON_BAD_AUTHORITY); return; }
    auth = rest + 2;
    alen = end - 2;
    for (i = 0; i < alen; i++)
      if (auth[i] == '@') { reject(v, READER_LINK_REASON_USERINFO); return; }
    for (i = 0; i < alen; i++)
      if (auth[i] == '%') { reject(v, READER_LINK_REASON_BAD_AUTHORITY); return; }
    if (auth[0] == '[') {
      size_t close = 1;
      while (close < alen && auth[close] != ']') {
        unsigned char c = (unsigned char)auth[close];
        if (!is_hex(c) && c != ':' && c != '.') { reject(v, READER_LINK_REASON_BAD_AUTHORITY); return; }
        close++;
      }
      if (close >= alen || close < 3) { reject(v, READER_LINK_REASON_BAD_AUTHORITY); return; }
      host_end = close + 1;
      port_start = host_end;
    } else {
      size_t colon_at = SIZE_MAX, k;
      int non_ascii = 0, prev_dot = 1;
      for (k = 0; k < alen; k++)
        if (auth[k] == ':') { colon_at = k; break; }
      host_end = (colon_at != SIZE_MAX) ? colon_at : alen;
      port_start = host_end;
      if (host_end == 0) { reject(v, READER_LINK_REASON_BAD_AUTHORITY); return; }
      for (k = 0; k < host_end; k++) {
        unsigned char c = (unsigned char)auth[k];
        if (c >= 0x80u) { non_ascii = 1; prev_dot = 0; continue; }
        if (c == '.') {
          if (prev_dot) { reject(v, READER_LINK_REASON_BAD_AUTHORITY); return; }
          prev_dot = 1;
          continue;
        }
        if (!is_alpha(c) && !is_digit(c) && c != '-' && c != '_') { reject(v, READER_LINK_REASON_BAD_AUTHORITY); return; }
        prev_dot = 0;
      }
      if (non_ascii) v->flags |= READER_LINK_FLAG_NON_ASCII_HOST;
    }
    if (port_start < alen) {
      size_t k, digits = 0;
      unsigned long port = 0;
      if (auth[port_start] != ':') { reject(v, READER_LINK_REASON_BAD_AUTHORITY); return; }
      for (k = port_start + 1; k < alen; k++) {
        if (!is_digit((unsigned char)auth[k]) || ++digits > 5) { reject(v, READER_LINK_REASON_BAD_AUTHORITY); return; }
        port = port * 10ul + (unsigned long)(auth[k] - '0');
      }
      if (port > 65535ul) { reject(v, READER_LINK_REASON_BAD_AUTHORITY); return; }
    }
  } else if (rest_len >= 2 && rest[0] == '/' && rest[1] == '/') {
    reject(v, READER_LINK_REASON_MALFORMED);
    return;
  }
  v->action = READER_LINK_ACTION_NEEDS_HOST;
  v->reason = READER_LINK_REASON_NONE;
  v->kind = READER_LINK_KIND_EXTERNAL;
  for (i = 0; i < colon; i++) v->scheme[i] = (char)lower((unsigned char)t[i]);
  v->scheme[colon] = 0;
  if (hash != SIZE_MAX) {
    v->flags |= READER_LINK_FLAG_HAS_FRAGMENT;
    v->fragment_offset = colon + 1 + hash + 1;
    v->fragment_len = rest_len - hash - 1;
  }
}

/* Validates fragment escapes like container paths: hex, no encoded control, and
   the decoded bytes must be valid UTF-8. A fragment keeps literal '/' and ':'
   because ids are opaque text, but a bad UTF-8 escape is a rejected link rather
   than a display string the host would have to escape. */
static int check_fragment_bytes(const char *s, size_t n, reader_link_reason *why) {
  size_t i;
  u8state st;
  memset(&st, 0, sizeof(st));
  for (i = 0; i < n; i++) {
    unsigned char b = (unsigned char)s[i];
    int done;
    uint32_t cp = 0;
    if (b == '%') {
      unsigned v;
      if (n - i < 3 || !is_hex((unsigned char)s[i + 1]) || !is_hex((unsigned char)s[i + 2])) {
        *why = READER_LINK_REASON_BAD_ESCAPE;
        return 0;
      }
      v = hex_value((unsigned char)s[i + 1]) * 16u + hex_value((unsigned char)s[i + 2]);
      if (v == 0 || v < 0x20u || v == 0x7Fu) {
        *why = READER_LINK_REASON_ENCODED_CONTROL;
        return 0;
      }
      b = (unsigned char)v;
      i += 2;
    }
    if (!u8_feed(&st, b, &done, &cp)) { *why = READER_LINK_REASON_BAD_ESCAPE; return 0; }
    if (done && spoof_cp(cp)) { *why = READER_LINK_REASON_ENCODED_CONTROL; return 0; }
  }
  if (st.need) { *why = READER_LINK_REASON_BAD_ESCAPE; return 0; }
  return 1;
}

/* Checks the percent-decoded bytes of a container path. */
static int check_path_bytes(const char *s, size_t n, reader_link_reason *why) {
  size_t i;
  u8state st;
  memset(&st, 0, sizeof(st));
  for (i = 0; i < n; i++) {
    unsigned char b = (unsigned char)s[i];
    int done;
    uint32_t cp = 0;
    if (b == ':') { *why = READER_LINK_REASON_BAD_PATH_CHAR; return 0; }
    if (b == '%') {
      unsigned v;
      if (n - i < 3 || !is_hex((unsigned char)s[i + 1]) || !is_hex((unsigned char)s[i + 2])) {
        *why = READER_LINK_REASON_BAD_ESCAPE;
        return 0;
      }
      v = hex_value((unsigned char)s[i + 1]) * 16u + hex_value((unsigned char)s[i + 2]);
      if (v < 0x20u || v == 0x7Fu) { *why = READER_LINK_REASON_ENCODED_CONTROL; return 0; }
      if (v == '/' || v == '\\') { *why = READER_LINK_REASON_ENCODED_SEPARATOR; return 0; }
      if (v == ':') { *why = READER_LINK_REASON_BAD_PATH_CHAR; return 0; }
      if (v == '%' && n - i >= 5 && is_hex((unsigned char)s[i + 3]) && is_hex((unsigned char)s[i + 4])) {
        *why = READER_LINK_REASON_DOUBLE_ESCAPE;
        return 0;
      }
      b = (unsigned char)v;
      i += 2;
    }
    if (!u8_feed(&st, b, &done, &cp)) { *why = READER_LINK_REASON_BAD_ESCAPE; return 0; }
    if (done && spoof_cp(cp)) { *why = READER_LINK_REASON_ENCODED_CONTROL; return 0; }
  }
  if (st.need) { *why = READER_LINK_REASON_BAD_ESCAPE; return 0; }
  return 1;
}

static void internal(const char *t, size_t n, long base_dirs, verdict *v) {
  size_t i, path_end = n, hash = SIZE_MAX, frag_len = 0, segments = 0;
  reader_link_reason why = READER_LINK_REASON_NONE;
  long depth = base_dirs;
  for (i = 0; i < n; i++) {
    if (t[i] == '#') { hash = i; path_end = i; break; }
    if (t[i] == '?') { reject(v, READER_LINK_REASON_BAD_PATH_CHAR); return; }
  }
  if (n >= 2 && t[0] == '/' && t[1] == '/') { reject(v, READER_LINK_REASON_PROTOCOL_RELATIVE); return; }
  if (n && t[0] == '/') { reject(v, READER_LINK_REASON_ABSOLUTE_PATH); return; }
  if (hash != SIZE_MAX) {
    size_t k;
    frag_len = n - hash - 1;
    for (k = hash + 1; k < n; k++)
      if (t[k] == '#') { reject(v, READER_LINK_REASON_MALFORMED); return; }
    if (frag_len >= READER_LINK_INTERNAL_PART_LIMIT) { reject(v, READER_LINK_REASON_TOO_LONG); return; }
    if (!check_fragment_bytes(t + hash + 1, frag_len, &why)) { reject(v, why); return; }
  }
  if (path_end >= READER_LINK_INTERNAL_PART_LIMIT) { reject(v, READER_LINK_REASON_TOO_LONG); return; }
  if (path_end) {
    size_t start = 0;
    if (!check_path_bytes(t, path_end, &why)) { reject(v, why); return; }
    for (;;) {
      size_t end = start;
      while (end < path_end && t[end] != '/') end++;
      if (end > start) {
        const char *seg = t + start;
        size_t len = end - start;
        int dot = len == 1 && seg[0] == '.';
        int dotdot = len == 2 && seg[0] == '.' && seg[1] == '.';
        if (!dot && !dotdot && len <= 6 && memchr(seg, '%', len)) {
          /* %2e spellings: decode and compare with "." and "..". */
          char dec[8];
          size_t di = 0, k;
          for (k = 0; k < len; k++) {
            if (seg[k] == '%') {
              dec[di++] = (char)(hex_value((unsigned char)seg[k + 1]) * 16u + hex_value((unsigned char)seg[k + 2]));
              k += 2;
            } else {
              dec[di++] = seg[k];
            }
          }
          if ((di == 1 && dec[0] == '.') || (di == 2 && dec[0] == '.' && dec[1] == '.')) {
            reject(v, READER_LINK_REASON_ENCODED_DOT);
            return;
          }
        }
        if (++segments > READER_LINK_MAX_SEGMENTS) { reject(v, READER_LINK_REASON_TOO_LONG); return; }
        if (dotdot) {
          if (depth == 0) { reject(v, READER_LINK_REASON_PATH_ESCAPE); return; }
          depth--;
        } else if (!dot) {
          depth++;
        }
      }
      if (end >= path_end) break;
      start = end + 1;
    }
    if (depth <= 0 || depth > (long)READER_LINK_MAX_SEGMENTS) { reject(v, READER_LINK_REASON_MALFORMED); return; }
  }
  v->action = READER_LINK_ACTION_INTERNAL;
  v->reason = READER_LINK_REASON_NONE;
  v->path_len = path_end;
  v->kind = path_end ? READER_LINK_KIND_CONTAINER_PATH : READER_LINK_KIND_FRAGMENT;
  if (hash != SIZE_MAX) {
    v->flags |= READER_LINK_FLAG_HAS_FRAGMENT;
    v->fragment_offset = hash + 1;
    v->fragment_len = frag_len;
    if (frag_len >= 8 && memcmp(t + hash + 1, "epubcfi(", 8) == 0) {
      if (frag_len < 10 || t[n - 1] != ')') { reject(v, READER_LINK_REASON_MALFORMED); return; }
      v->kind = READER_LINK_KIND_CFI;
    }
  }
}

static reader_link_status core(const reader_link_policy *p, const char *t, size_t n, long base_dirs,
                               const reader_link_control *control, verdict *v, uint32_t *flags) {
  size_t i, colon = SIZE_MAX;
  reader_link_reason first = READER_LINK_REASON_NONE;
  u8state st;
  int unsafe = 0;
  memset(v, 0, sizeof(*v));
  if (n == 0) { reject(v, READER_LINK_REASON_EMPTY); return READER_LINK_OK; }
  if (n > p->max_input) { reject(v, READER_LINK_REASON_TOO_LONG); return READER_LINK_OK; }
  memset(&st, 0, sizeof(st));
  for (i = 0; i < n; i++) {
    int done;
    uint32_t cp = 0;
    unsigned char b = (unsigned char)t[i];
    if ((i & 4095u) == 4095u && should_stop(control)) return READER_LINK_CANCELLED;
    if (!u8_feed(&st, b, &done, &cp)) {
      unsafe = 1;
      if (first == READER_LINK_REASON_NONE) first = READER_LINK_REASON_INVALID_UTF8;
      memset(&st, 0, sizeof(st));
      continue;
    }
    if (done && spoof_cp(cp)) {
      unsafe = 1;
      if (first == READER_LINK_REASON_NONE) first = READER_LINK_REASON_CONTROL;
    }
    if (b == '\\' && first == READER_LINK_REASON_NONE) first = READER_LINK_REASON_BACKSLASH;
  }
  if (st.need) {
    unsafe = 1;
    if (first == READER_LINK_REASON_NONE) first = READER_LINK_REASON_INVALID_UTF8;
  }
  if (unsafe) *flags |= READER_LINK_FLAG_DISPLAY_UNSAFE;
  if (first != READER_LINK_REASON_NONE) { reject(v, first); return READER_LINK_OK; }
  if (t[0] == ' ' || t[n - 1] == ' ') { reject(v, READER_LINK_REASON_SPACE); return READER_LINK_OK; }
  for (i = 0; i < n; i++) {
    if (t[i] == ':') { colon = i; break; }
    if (t[i] == '/' || t[i] == '?' || t[i] == '#') break;
  }
  if (colon != SIZE_MAX) {
    if (colon >= READER_LINK_SCHEME_BYTES || !scheme_syntax(t, colon)) { reject(v, READER_LINK_REASON_BAD_SCHEME); return READER_LINK_OK; }
    if (scheme_denied(t, colon)) { reject(v, READER_LINK_REASON_FORBIDDEN_SCHEME); return READER_LINK_OK; }
    if (!scheme_allowed(p, t, colon)) { reject(v, READER_LINK_REASON_UNKNOWN_SCHEME); return READER_LINK_OK; }
    external(t, n, colon, v);
  } else {
    internal(t, n, base_dirs, v);
  }
  return READER_LINK_OK;
}

reader_link_status reader_link_classify(const reader_link_policy *policy, const char *text,
                                        size_t size, const char *base_path,
                                        const reader_link_control *control,
                                        reader_link_result *result, reader_link_error *error) {
  verdict v;
  uint32_t flags = 0;
  long dirs;
  reader_link_status status;
  char *copy = NULL;
  if (!result) {
    report(error, READER_LINK_ARGUMENT, 0, "result is required");
    return READER_LINK_ARGUMENT;
  }
  if (result->struct_size != sizeof(*result)) {
    report(error, READER_LINK_ARGUMENT, 0, "result struct_size is not set");
    return READER_LINK_ARGUMENT;
  }
  memset(result, 0, sizeof(*result));
  result->struct_size = (uint32_t)sizeof(*result);
  if (!policy || (!text && size)) {
    report(error, READER_LINK_ARGUMENT, 0, "policy and text are required");
    return READER_LINK_ARGUMENT;
  }
  dirs = base_depth(base_path);
  if (dirs < 0) {
    report(error, READER_LINK_ARGUMENT, 0, "invalid base path");
    return READER_LINK_ARGUMENT;
  }
  if (should_stop(control)) {
    report(error, READER_LINK_CANCELLED, 0, "cancelled");
    return READER_LINK_CANCELLED;
  }
  status = core(policy, text, size, dirs, control, &v, &flags);
  if (status != READER_LINK_OK) {
    report(error, status, 0, "cancelled");
    return status;
  }
  if (size <= policy->max_input) {
    copy = (char *)rlp_alloc(size + 1);
    if (!copy) {
      report(error, READER_LINK_MEMORY, 0, "display allocation failed");
      return READER_LINK_MEMORY;
    }
    if (size) memcpy(copy, text, size);
    copy[size] = 0;
  }
  if (should_stop(control)) {
    rlp_free(copy);
    report(error, READER_LINK_CANCELLED, 0, "cancelled before commit");
    return READER_LINK_CANCELLED;
  }
  result->action = v.action;
  result->reason = v.reason;
  result->kind = v.kind;
  result->flags = v.flags | flags;
  memcpy(result->scheme, v.scheme, sizeof(result->scheme));
  result->input_bytes = size;
  result->display = copy;
  result->display_len = copy ? size : 0;
  result->path_len = v.path_len;
  result->fragment_offset = v.fragment_offset;
  result->fragment_len = v.fragment_len;
  report(error, READER_LINK_OK, 0, "");
  return READER_LINK_OK;
}

void reader_link_result_free(reader_link_result *result) {
  if (!result) return;
  rlp_free(result->display);
  result->display = NULL;
  result->display_len = 0;
}
