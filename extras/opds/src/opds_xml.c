/* SPDX-License-Identifier: MIT */
/* Small bounded XML and JSON parsers. XML: namespaces, entities, CDATA; DTDs are
   refused (no entity expansion, no external resources). Both are iterative or
   depth-limited and count elements against the caller's budget. */
#include "opds_internal.h"
#include <ctype.h>
#include <math.h>

static int is_space(int c) { return c == ' ' || c == '\t' || c == '\r' || c == '\n'; }

static int utf8_put(opds_buf *b, unsigned long cp) {
  unsigned char t[4];
  size_t n;
  if (cp == 0 || cp > 0x10FFFF || (cp >= 0xD800 && cp <= 0xDFFF)) return 0;
  if (cp < 0x80) { t[0] = (unsigned char)cp; n = 1; }
  else if (cp < 0x800) { t[0] = (unsigned char)(0xC0 | cp >> 6); t[1] = (unsigned char)(0x80 | (cp & 63)); n = 2; }
  else if (cp < 0x10000) { t[0] = (unsigned char)(0xE0 | cp >> 12); t[1] = (unsigned char)(0x80 | ((cp >> 6) & 63)); t[2] = (unsigned char)(0x80 | (cp & 63)); n = 3; }
  else { t[0] = (unsigned char)(0xF0 | cp >> 18); t[1] = (unsigned char)(0x80 | ((cp >> 12) & 63)); t[2] = (unsigned char)(0x80 | ((cp >> 6) & 63)); t[3] = (unsigned char)(0x80 | (cp & 63)); n = 4; }
  return buf_append(b, t, n);
}

/* ---- XML ---- */
static opds_status xml_text(const char *s, size_t n, opds_buf *out, opds_error *e) {
  for (size_t i = 0; i < n; i++) {
    if (s[i] != '&') {
      if (!buf_append(out, s + i, 1)) return OPDS_MEMORY;
      continue;
    }
    {
      const char *semi = (const char *)memchr(s + i, ';', n - i);
      size_t l;
      if (!semi) return opds_fail(e, OPDS_FORMAT, "unterminated entity");
      l = (size_t)(semi - (s + i)) - 1;
      if (l == 2 && !memcmp(s + i + 1, "lt", 2)) buf_append(out, "<", 1);
      else if (l == 2 && !memcmp(s + i + 1, "gt", 2)) buf_append(out, ">", 1);
      else if (l == 3 && !memcmp(s + i + 1, "amp", 3)) buf_append(out, "&", 1);
      else if (l == 4 && !memcmp(s + i + 1, "quot", 4)) buf_append(out, "\"", 1);
      else if (l == 4 && !memcmp(s + i + 1, "apos", 4)) buf_append(out, "'", 1);
      else if (l >= 2 && s[i + 1] == '#') {
        unsigned long cp = 0;
        int hex = s[i + 2] == 'x';
        size_t k = hex ? 3 : 2;
        if (k > l) return opds_fail(e, OPDS_FORMAT, "bad character reference");
        for (; k <= l; k++) {
          int c = (unsigned char)s[i + k], d;
          if (c >= '0' && c <= '9') d = c - '0';
          else if (hex && c >= 'a' && c <= 'f') d = c - 'a' + 10;
          else if (hex && c >= 'A' && c <= 'F') d = c - 'A' + 10;
          else return opds_fail(e, OPDS_FORMAT, "bad character reference");
          cp = cp * (hex ? 16 : 10) + (unsigned long)d;
          if (cp > 0x10FFFF) return opds_fail(e, OPDS_FORMAT, "bad character reference");
        }
        if (!utf8_put(out, cp)) return opds_fail(e, OPDS_FORMAT, "invalid character reference");
      } else return opds_fail(e, OPDS_FORMAT, "undefined entity (DTD entities are not supported)");
      i += l + 1;
    }
  }
  return OPDS_OK;
}

typedef struct { opds_xnode *node; const char *qname; opds_buf text; } xframe;

static const char *xml_lookup(const opds_xnode *n, const char *prefix, size_t pl) {
  for (; n; n = n->parent)
    for (size_t i = n->ns_count; i-- > 0;)
      if (strlen(n->ns_prefix[i]) == pl && !memcmp(n->ns_prefix[i], prefix, pl)) return n->ns_uri[i];
  if (pl == 3 && !memcmp(prefix, "xml", 3)) return NS_XML;
  return NULL;
}

static const char *trim_dup(struct opds_arena *a, const opds_buf *b) {
  size_t s = 0, e = b->size;
  while (s < e && is_space(b->data[s])) s++;
  while (e > s && is_space(b->data[e - 1])) e--;
  return arena_strndup(a, b->data ? (const char *)b->data + s : "", e - s);
}

opds_status opds_xml_parse(struct opds_arena *arena, const char *d, size_t n,
                           const opds_limits *lim, opds_xnode **root, opds_error *err) {
  size_t i = 0, elements = 0, depth = 0, max_depth = lim->max_depth ? lim->max_depth : 48;
  xframe *stack = (xframe *)calloc(max_depth + 2, sizeof(xframe));
  opds_status st = OPDS_OK;
  int seen_root = 0;
  *root = NULL;
  if (!stack) return opds_fail(err, OPDS_MEMORY, "out of memory");
  if (n >= 3 && !memcmp(d, "\xEF\xBB\xBF", 3)) i = 3;
#define BAD(...) do { st = opds_fail(err, OPDS_FORMAT, __VA_ARGS__); goto done; } while (0)
  while (i < n) {
    if (d[i] != '<') {
      size_t j = i;
      while (j < n && d[j] != '<') j++;
      if (depth == 0) {
        for (size_t k = i; k < j; k++) if (!is_space(d[k])) BAD("character data outside the root element");
      } else if ((st = xml_text(d + i, j - i, &stack[depth - 1].text, err)) != OPDS_OK) goto done;
      i = j; continue;
    }
    if (n - i >= 4 && !memcmp(d + i, "<!--", 4)) {
      const char *e = NULL;
      for (size_t k = i + 4; k + 2 < n; k++) if (d[k] == '-' && d[k + 1] == '-' && d[k + 2] == '>') { e = d + k; break; }
      if (!e) BAD("unterminated comment");
      i = (size_t)(e - d) + 3; continue;
    }
    if (n - i >= 9 && !memcmp(d + i, "<![CDATA[", 9)) {
      const char *e = NULL;
      if (depth == 0) BAD("CDATA outside the root element");
      for (size_t k = i + 9; k + 2 < n; k++) if (d[k] == ']' && d[k + 1] == ']' && d[k + 2] == '>') { e = d + k; break; }
      if (!e) BAD("unterminated CDATA");
      if (!buf_append(&stack[depth - 1].text, d + i + 9, (size_t)(e - (d + i + 9)))) { st = OPDS_MEMORY; goto done; }
      i = (size_t)(e - d) + 3; continue;
    }
    if (n - i >= 2 && d[i + 1] == '!') {
      st = opds_fail(err, OPDS_FORMAT, "DOCTYPE/DTD declarations are not allowed"); goto done;
    }
    if (n - i >= 2 && d[i + 1] == '?') {
      const char *e = NULL;
      for (size_t k = i + 2; k + 1 < n; k++) if (d[k] == '?' && d[k + 1] == '>') { e = d + k; break; }
      if (!e) BAD("unterminated processing instruction");
      if (i + 5 < n && !memcmp(d + i, "<?xml", 5) && depth == 0 && !seen_root) {
        const char *enc = NULL;
        for (const char *p = d + i; p + 8 < e; p++) if (!memcmp(p, "encoding", 8)) { enc = p + 8; break; }
        if (enc) {
          while (enc < e && (is_space(*enc) || *enc == '=')) enc++;
          if (enc < e && (*enc == '"' || *enc == '\'')) {
            char q = *enc++;
            const char *v = enc;
            while (enc < e && *enc != q) enc++;
            if (!((size_t)(enc - v) == 5 && opds_ascii_iprefix(v, "utf-8")) &&
                !((size_t)(enc - v) == 8 && opds_ascii_iprefix(v, "us-ascii")) &&
                !((size_t)(enc - v) == 5 && opds_ascii_iprefix(v, "ascii")))
              { st = opds_fail(err, OPDS_UNSUPPORTED, "only UTF-8 XML is supported"); goto done; }
          }
        }
      }
      i = (size_t)(e - d) + 2; continue;
    }
    if (i + 1 < n && d[i + 1] == '/') {
      size_t j = i + 2, ql;
      if (depth == 0) BAD("unexpected closing tag");
      while (j < n && d[j] != '>' && !is_space(d[j])) j++;
      ql = j - (i + 2);
      while (j < n && is_space(d[j])) j++;
      if (j >= n || d[j] != '>') BAD("malformed closing tag");
      if (strlen(stack[depth - 1].qname) != ql || memcmp(stack[depth - 1].qname, d + i + 2, ql)) BAD("mismatched closing tag");
      stack[depth - 1].node->text = trim_dup(arena, &stack[depth - 1].text);
      if (!stack[depth - 1].node->text) { st = OPDS_MEMORY; goto done; }
      buf_free(&stack[depth - 1].text);
      depth--;
      i = j + 1; continue;
    }
    {
      /* start tag */
      size_t j = i + 1, ql;
      opds_xnode *node;
      struct raw_attr { const char *name; size_t nl; const char *val; size_t vl; } attrs[64];
      size_t ac = 0, ncount = 0;
      int empty = 0;
      const char *qname;
      if (seen_root && depth == 0) BAD("multiple root elements");
      if (depth >= max_depth) { st = opds_fail(err, OPDS_LIMIT, "XML nesting exceeds %zu", max_depth); goto done; }
      if (++elements > lim->max_elements) { st = opds_fail(err, OPDS_LIMIT, "XML element budget exceeded"); goto done; }
      while (j < n && !is_space(d[j]) && d[j] != '>' && d[j] != '/') j++;
      ql = j - (i + 1);
      if (ql == 0) BAD("empty element name");
      qname = arena_strndup(arena, d + i + 1, ql);
      for (;;) {
        while (j < n && is_space(d[j])) j++;
        if (j >= n) BAD("unterminated start tag");
        if (d[j] == '>') { j++; break; }
        if (d[j] == '/') { if (j + 1 < n && d[j + 1] == '>') { empty = 1; j += 2; break; } BAD("malformed start tag"); }
        {
          size_t s = j;
          char q;
          size_t vs;
          while (j < n && d[j] != '=' && !is_space(d[j]) && d[j] != '>' && d[j] != '/') j++;
          if (ac >= 64) { st = opds_fail(err, OPDS_LIMIT, "too many attributes"); goto done; }
          attrs[ac].name = d + s; attrs[ac].nl = j - s;
          while (j < n && is_space(d[j])) j++;
          if (j >= n || d[j] != '=' || attrs[ac].nl == 0) BAD("malformed attribute");
          j++;
          while (j < n && is_space(d[j])) j++;
          if (j >= n || (d[j] != '"' && d[j] != '\'')) BAD("unquoted attribute value");
          q = d[j++]; vs = j;
          while (j < n && d[j] != q) { if (d[j] == '<') BAD("'<' in attribute value"); j++; }
          if (j >= n) BAD("unterminated attribute value");
          attrs[ac].val = d + vs; attrs[ac].vl = j - vs; j++;
          for (size_t k = 0; k < ac; k++)
            if (attrs[k].nl == attrs[ac].nl && !memcmp(attrs[k].name, attrs[ac].name, attrs[ac].nl)) BAD("duplicate attribute");
          ac++;
          if (j < n && !is_space(d[j]) && d[j] != '>' && d[j] != '/') BAD("missing space between attributes");
        }
      }
      node = (opds_xnode *)arena_alloc(arena, sizeof *node);
      if (!node) { st = OPDS_MEMORY; goto done; }
      memset(node, 0, sizeof *node);
      node->parent = depth ? stack[depth - 1].node : NULL;
      /* namespace declarations first */
      for (size_t k = 0; k < ac; k++)
        if ((attrs[k].nl == 5 && !memcmp(attrs[k].name, "xmlns", 5)) || (attrs[k].nl > 6 && !memcmp(attrs[k].name, "xmlns:", 6))) ncount++;
      if (ncount) {
        node->ns_prefix = (const char **)arena_alloc(arena, ncount * sizeof(char *));
        node->ns_uri = (const char **)arena_alloc(arena, ncount * sizeof(char *));
        if (!node->ns_prefix || !node->ns_uri) { st = OPDS_MEMORY; goto done; }
        for (size_t k = 0; k < ac; k++) {
          int def = attrs[k].nl == 5 && !memcmp(attrs[k].name, "xmlns", 5);
          if (def || (attrs[k].nl > 6 && !memcmp(attrs[k].name, "xmlns:", 6))) {
            opds_buf v = {0};
            if ((st = xml_text(attrs[k].val, attrs[k].vl, &v, err)) != OPDS_OK) { buf_free(&v); goto done; }
            node->ns_prefix[node->ns_count] = def ? "" : arena_strndup(arena, attrs[k].name + 6, attrs[k].nl - 6);
            node->ns_uri[node->ns_count] = arena_strndup(arena, v.data ? (const char *)v.data : "", v.size);
            node->ns_count++;
            buf_free(&v);
          }
        }
      }
      {
        const char *colon = (const char *)memchr(qname, ':', ql);
        if (colon) {
          const char *u = xml_lookup(node, qname, (size_t)(colon - qname));
          if (!u) BAD("undeclared namespace prefix");
          node->ns = u; node->name = colon + 1;
        } else {
          const char *u = xml_lookup(node, "", 0);
          node->ns = u ? u : ""; node->name = qname;
        }
      }
      node->attrs = (opds_xattr *)arena_alloc(arena, (ac + 1) * sizeof(opds_xattr));
      if (!node->attrs) { st = OPDS_MEMORY; goto done; }
      for (size_t k = 0; k < ac; k++) {
        const char *nm = attrs[k].name; size_t nl = attrs[k].nl;
        const char *colon;
        opds_buf v = {0};
        if ((nl == 5 && !memcmp(nm, "xmlns", 5)) || (nl > 6 && !memcmp(nm, "xmlns:", 6))) continue;
        if ((st = xml_text(attrs[k].val, attrs[k].vl, &v, err)) != OPDS_OK) { buf_free(&v); goto done; }
        colon = (const char *)memchr(nm, ':', nl);
        if (colon) {
          const char *u = xml_lookup(node, nm, (size_t)(colon - nm));
          if (!u) { buf_free(&v); BAD("undeclared attribute prefix"); }
          node->attrs[node->attr_count].ns = u;
          node->attrs[node->attr_count].name = arena_strndup(arena, colon + 1, nl - (size_t)(colon - nm) - 1);
        } else {
          node->attrs[node->attr_count].ns = "";
          node->attrs[node->attr_count].name = arena_strndup(arena, nm, nl);
        }
        node->attrs[node->attr_count].value = arena_strndup(arena, v.data ? (const char *)v.data : "", v.size);
        node->attr_count++;
        buf_free(&v);
      }
      if (node->parent) {
        if (node->parent->last) node->parent->last->next = node; else node->parent->first = node;
        node->parent->last = node;
      } else { *root = node; seen_root = 1; }
      if (empty) node->text = "";
      else { stack[depth].node = node; stack[depth].qname = qname; memset(&stack[depth].text, 0, sizeof(opds_buf)); depth++; }
      i = j;
    }
  }
  if (depth != 0) BAD("unclosed element");
  if (!seen_root) BAD("no root element");
done:
  for (size_t k = 0; k < max_depth + 2; k++) buf_free(&stack[k].text);
  free(stack);
#undef BAD
  if (st != OPDS_OK) *root = NULL;
  return st;
}

const char *opds_xattr_get(const opds_xnode *n, const char *ns, const char *name) {
  for (size_t i = 0; i < n->attr_count; i++)
    if (!strcmp(n->attrs[i].name, name) && !strcmp(n->attrs[i].ns, ns)) return n->attrs[i].value;
  return NULL;
}
int opds_xis(const opds_xnode *n, const char *ns, const char *name) {
  return !strcmp(n->ns, ns) && !strcmp(n->name, name);
}

/* ---- JSON ---- */
typedef struct {
  struct opds_arena *a; const char *p, *end; size_t nodes, max_nodes, max_depth;
  opds_error *err; opds_status st;
} jctx;

static opds_jnode *j_value(jctx *c, size_t depth);
static void j_ws(jctx *c) { while (c->p < c->end && is_space(*c->p)) c->p++; }
static opds_jnode *j_new(jctx *c, opds_jtype t) {
  opds_jnode *n;
  if (++c->nodes > c->max_nodes) { c->st = opds_fail(c->err, OPDS_LIMIT, "JSON value budget exceeded"); return NULL; }
  n = (opds_jnode *)arena_alloc(c->a, sizeof *n);
  if (!n) { c->st = OPDS_MEMORY; return NULL; }
  memset(n, 0, sizeof *n); n->type = t;
  return n;
}
static int j_hex4(const char *p, unsigned long *out) {
  unsigned long v = 0;
  for (int i = 0; i < 4; i++) {
    int ch = (unsigned char)p[i], d;
    if (ch >= '0' && ch <= '9') d = ch - '0'; else if (ch >= 'a' && ch <= 'f') d = ch - 'a' + 10;
    else if (ch >= 'A' && ch <= 'F') d = ch - 'A' + 10; else return 0;
    v = v * 16 + (unsigned long)d;
  }
  *out = v; return 1;
}
static const char *j_string(jctx *c) {
  opds_buf b = {0};
  const char *r;
  c->p++; /* opening quote */
  for (;;) {
    unsigned char ch;
    if (c->p >= c->end) { c->st = opds_fail(c->err, OPDS_FORMAT, "unterminated JSON string"); buf_free(&b); return NULL; }
    ch = (unsigned char)*c->p++;
    if (ch == '"') break;
    if (ch < 0x20) { c->st = opds_fail(c->err, OPDS_FORMAT, "control character in JSON string"); buf_free(&b); return NULL; }
    if (ch != '\\') { if (!buf_append(&b, &ch, 1)) { c->st = OPDS_MEMORY; buf_free(&b); return NULL; } continue; }
    if (c->p >= c->end) { c->st = opds_fail(c->err, OPDS_FORMAT, "bad JSON escape"); buf_free(&b); return NULL; }
    ch = (unsigned char)*c->p++;
    switch (ch) {
      case '"': case '\\': case '/': buf_append(&b, &ch, 1); break;
      case 'b': buf_append(&b, "\b", 1); break;
      case 'f': buf_append(&b, "\f", 1); break;
      case 'n': buf_append(&b, "\n", 1); break;
      case 'r': buf_append(&b, "\r", 1); break;
      case 't': buf_append(&b, "\t", 1); break;
      case 'u': {
        unsigned long cp, lo;
        if (c->end - c->p < 4 || !j_hex4(c->p, &cp)) { c->st = opds_fail(c->err, OPDS_FORMAT, "bad \\u escape"); buf_free(&b); return NULL; }
        c->p += 4;
        if (cp >= 0xD800 && cp <= 0xDBFF) {
          if (c->end - c->p < 6 || c->p[0] != '\\' || c->p[1] != 'u' || !j_hex4(c->p + 2, &lo) || lo < 0xDC00 || lo > 0xDFFF)
            { c->st = opds_fail(c->err, OPDS_FORMAT, "unpaired surrogate"); buf_free(&b); return NULL; }
          c->p += 6; cp = 0x10000 + ((cp - 0xD800) << 10) + (lo - 0xDC00);
        } else if (cp >= 0xDC00 && cp <= 0xDFFF) { c->st = opds_fail(c->err, OPDS_FORMAT, "unpaired surrogate"); buf_free(&b); return NULL; }
        if (!utf8_put(&b, cp)) { c->st = opds_fail(c->err, OPDS_FORMAT, "invalid \\u escape"); buf_free(&b); return NULL; }
        break;
      }
      default: c->st = opds_fail(c->err, OPDS_FORMAT, "bad JSON escape"); buf_free(&b); return NULL;
    }
  }
  r = arena_strndup(c->a, b.data ? (const char *)b.data : "", b.size);
  buf_free(&b);
  if (!r) c->st = OPDS_MEMORY;
  return r;
}
static opds_jnode *j_value(jctx *c, size_t depth) {
  opds_jnode *n;
  j_ws(c);
  if (c->p >= c->end) { c->st = opds_fail(c->err, OPDS_FORMAT, "unexpected end of JSON"); return NULL; }
  if (depth > c->max_depth) { c->st = opds_fail(c->err, OPDS_LIMIT, "JSON nesting exceeds %zu", c->max_depth); return NULL; }
  switch (*c->p) {
    case '{': case '[': {
      int obj = *c->p == '{';
      char close = obj ? '}' : ']';
      n = j_new(c, obj ? OJ_OBJ : OJ_ARR);
      if (!n) return NULL;
      c->p++; j_ws(c);
      if (c->p < c->end && *c->p == close) { c->p++; return n; }
      for (;;) {
        const char *key = NULL;
        opds_jnode *v;
        j_ws(c);
        if (obj) {
          if (c->p >= c->end || *c->p != '"') { c->st = opds_fail(c->err, OPDS_FORMAT, "object key expected"); return NULL; }
          key = j_string(c); if (!key) return NULL;
          j_ws(c);
          if (c->p >= c->end || *c->p != ':') { c->st = opds_fail(c->err, OPDS_FORMAT, "':' expected"); return NULL; }
          c->p++;
        }
        v = j_value(c, depth + 1); if (!v) return NULL;
        v->key = key;
        if (n->last) n->last->next = v; else n->first = v;
        n->last = v;
        j_ws(c);
        if (c->p < c->end && *c->p == ',') { c->p++; continue; }
        if (c->p < c->end && *c->p == close) { c->p++; return n; }
        c->st = opds_fail(c->err, OPDS_FORMAT, "',' or '%c' expected", close); return NULL;
      }
    }
    case '"':
      n = j_new(c, OJ_STR); if (!n) return NULL;
      n->str = j_string(c); return n->str ? n : NULL;
    case 't': case 'f': case 'n': {
      size_t l = *c->p == 'f' ? 5 : 4;
      const char *lit = *c->p == 't' ? "true" : *c->p == 'f' ? "false" : "null";
      if ((size_t)(c->end - c->p) < l || memcmp(c->p, lit, l)) { c->st = opds_fail(c->err, OPDS_FORMAT, "bad JSON literal"); return NULL; }
      n = j_new(c, *lit == 'n' ? OJ_NULL : OJ_BOOL); if (!n) return NULL;
      n->boolean = *lit == 't'; c->p += l; return n;
    }
    default: {
      const char *s = c->p;
      char tmp[48], *endp;
      size_t l;
      if (*c->p != '-' && !isdigit((unsigned char)*c->p)) { c->st = opds_fail(c->err, OPDS_FORMAT, "unexpected JSON character"); return NULL; }
      while (c->p < c->end && (isdigit((unsigned char)*c->p) || *c->p == '+' || *c->p == '-' || *c->p == '.' || *c->p == 'e' || *c->p == 'E')) c->p++;
      l = (size_t)(c->p - s);
      if (l == 0 || l >= sizeof tmp) { c->st = opds_fail(c->err, OPDS_FORMAT, "bad JSON number"); return NULL; }
      memcpy(tmp, s, l); tmp[l] = 0;
      n = j_new(c, OJ_NUM); if (!n) return NULL;
      n->num = strtod(tmp, &endp);
      if (*endp || !isfinite(n->num)) { c->st = opds_fail(c->err, OPDS_FORMAT, "bad JSON number"); return NULL; }
      n->str = arena_strndup(c->a, tmp, l);
      return n;
    }
  }
}
opds_status opds_json_parse(struct opds_arena *a, const char *d, size_t n, const opds_limits *lim,
                            opds_jnode **root, opds_error *err) {
  jctx c;
  c.a = a; c.p = d; c.end = d + n; c.nodes = 0; c.max_nodes = lim->max_elements;
  c.max_depth = lim->max_depth ? lim->max_depth : 48; c.err = err; c.st = OPDS_OK;
  *root = NULL;
  if (n >= 3 && !memcmp(d, "\xEF\xBB\xBF", 3)) c.p += 3;
  *root = j_value(&c, 0);
  if (!*root) return c.st ? c.st : OPDS_FORMAT;
  j_ws(&c);
  if (c.p != c.end) { *root = NULL; return opds_fail(err, OPDS_FORMAT, "trailing data after JSON value"); }
  return OPDS_OK;
}
opds_jnode *opds_jget(const opds_jnode *o, const char *key) {
  if (!o || o->type != OJ_OBJ) return NULL;
  for (opds_jnode *c = o->first; c; c = c->next) if (c->key && !strcmp(c->key, key)) return c;
  return NULL;
}
const char *opds_jstr(const opds_jnode *n) { return n && n->type == OJ_STR ? n->str : NULL; }
