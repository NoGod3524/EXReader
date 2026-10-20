/* SPDX-License-Identifier: MIT */
#include "convert_json.h"
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

void cv_text_init(cv_text *t) { memset(t, 0, sizeof(*t)); }
void cv_text_free(cv_text *t) { free(t->data); memset(t, 0, sizeof(*t)); }
static int reserve(cv_text *t, size_t add) {
  size_t need, capacity;
  char *next;
  if (t->failed) return 0;
  need = t->size + add + 1;
  if (need <= t->capacity) return 1;
  capacity = t->capacity ? t->capacity : 256;
  while (capacity < need) {
    if (capacity > (size_t)-1 / 2) { t->failed = 1; return 0; }
    capacity *= 2;
  }
  next = realloc(t->data, capacity);
  if (!next) { t->failed = 1; return 0; }
  t->data = next;
  t->capacity = capacity;
  return 1;
}
int cv_text_append(cv_text *t, const void *data, size_t size) {
  if (!reserve(t, size)) return 0;
  memcpy(t->data + t->size, data, size);
  t->size += size;
  t->data[t->size] = 0;
  return 1;
}
int cv_text_string(cv_text *t, const char *s) { return cv_text_append(t, s, strlen(s)); }
int cv_text_format(cv_text *t, const char *format, ...) {
  va_list args, copy;
  int n;
  va_start(args, format);
  va_copy(copy, args);
  n = vsnprintf(NULL, 0, format, copy);
  va_end(copy);
  if (n < 0) { t->failed = 1; va_end(args); return 0; }
  if (!reserve(t, (size_t)n)) { va_end(args); return 0; }
  vsnprintf(t->data + t->size, (size_t)n + 1, format, args);
  va_end(args);
  t->size += (size_t)n;
  return 1;
}
static size_t utf8_sequence(const unsigned char *p, unsigned *codepoint) {
  if (p[0] < 0x80) { *codepoint = p[0]; return 1; }
  if ((p[0] & 0xe0) == 0xc0 && (p[1] & 0xc0) == 0x80) {
    *codepoint = ((unsigned)(p[0] & 0x1f) << 6) | (p[1] & 0x3f); return *codepoint >= 0x80 ? 2 : 0;
  }
  if ((p[0] & 0xf0) == 0xe0 && (p[1] & 0xc0) == 0x80 && (p[2] & 0xc0) == 0x80) {
    *codepoint = ((unsigned)(p[0] & 0x0f) << 12) | ((unsigned)(p[1] & 0x3f) << 6) | (p[2] & 0x3f);
    return *codepoint >= 0x800 && (*codepoint < 0xd800 || *codepoint > 0xdfff) ? 3 : 0;
  }
  if ((p[0] & 0xf8) == 0xf0 && (p[1] & 0xc0) == 0x80 && (p[2] & 0xc0) == 0x80 && (p[3] & 0xc0) == 0x80) {
    *codepoint = ((unsigned)(p[0] & 7) << 18) | ((unsigned)(p[1] & 0x3f) << 12) |
                 ((unsigned)(p[2] & 0x3f) << 6) | (p[3] & 0x3f);
    return *codepoint >= 0x10000 && *codepoint <= 0x10ffff ? 4 : 0;
  }
  return 0;
}
int cv_text_json(cv_text *t, const char *s) {
  const unsigned char *p = (const unsigned char *)(s ? s : "");
  if (!cv_text_string(t, "\"")) return 0;
  while (*p) {
    unsigned cp; size_t n;
    char escaped[16];
    if (*p == '"' || *p == '\\') { escaped[0] = '\\'; escaped[1] = (char)*p; if (!cv_text_append(t, escaped, 2)) return 0; p++; continue; }
    if (*p == '\n') { if (!cv_text_string(t, "\\n")) return 0; p++; continue; }
    if (*p == '\r') { if (!cv_text_string(t, "\\r")) return 0; p++; continue; }
    if (*p == '\t') { if (!cv_text_string(t, "\\t")) return 0; p++; continue; }
    if (*p < 0x20) { snprintf(escaped, sizeof(escaped), "\\u%04x", *p); if (!cv_text_string(t, escaped)) return 0; p++; continue; }
    n = utf8_sequence(p, &cp);
    if (!n) { if (!cv_text_string(t, "\\ufffd")) return 0; p++; continue; }
    if (!cv_text_append(t, p, n)) return 0;
    p += n;
  }
  return cv_text_string(t, "\"");
}

typedef struct { const char *text; size_t size, at; char *error; unsigned depth; } parser;
static void fail(parser *p, const char *message) {
  char buffer[256];
  if (p->error) return;
  snprintf(buffer, sizeof(buffer), "%s at byte %zu", message, p->at);
  p->error = malloc(strlen(buffer) + 1);
  if (p->error) strcpy(p->error, buffer);
}
static void skip(parser *p) {
  while (p->at < p->size) {
    char c = p->text[p->at];
    if (c == ' ' || c == '\t' || c == '\n' || c == '\r') p->at++;
    else break;
  }
}
static int append_utf8(char **out, size_t *used, size_t *capacity, unsigned cp) {
  unsigned char bytes[4]; size_t n;
  char *next;
  if (cp < 0x80) { bytes[0] = (unsigned char)cp; n = 1; }
  else if (cp < 0x800) { bytes[0] = (unsigned char)(0xc0 | (cp >> 6)); bytes[1] = (unsigned char)(0x80 | (cp & 63)); n = 2; }
  else if (cp < 0x10000) { bytes[0] = (unsigned char)(0xe0 | (cp >> 12)); bytes[1] = (unsigned char)(0x80 | ((cp >> 6) & 63)); bytes[2] = (unsigned char)(0x80 | (cp & 63)); n = 3; }
  else { bytes[0] = (unsigned char)(0xf0 | (cp >> 18)); bytes[1] = (unsigned char)(0x80 | ((cp >> 12) & 63)); bytes[2] = (unsigned char)(0x80 | ((cp >> 6) & 63)); bytes[3] = (unsigned char)(0x80 | (cp & 63)); n = 4; }
  if (*used + n + 1 > *capacity) {
    size_t cap = *capacity ? *capacity : 32;
    while (cap < *used + n + 1) cap *= 2;
    next = realloc(*out, cap);
    if (!next) return 0;
    *out = next; *capacity = cap;
  }
  memcpy(*out + *used, bytes, n); *used += n; (*out)[*used] = 0;
  return 1;
}
static int hex4(const char *s, unsigned *value) {
  unsigned v = 0; int i;
  for (i = 0; i < 4; i++) {
    char c = s[i];
    v <<= 4;
    if (c >= '0' && c <= '9') v |= (unsigned)(c - '0');
    else if (c >= 'a' && c <= 'f') v |= (unsigned)(c - 'a' + 10);
    else if (c >= 'A' && c <= 'F') v |= (unsigned)(c - 'A' + 10);
    else return 0;
  }
  *value = v; return 1;
}
static char *parse_string(parser *p) {
  char *out = NULL; size_t used = 0, capacity = 0;
  if (p->at >= p->size || p->text[p->at] != '"') { fail(p, "Expected string"); return NULL; }
  p->at++;
  while (p->at < p->size) {
    unsigned char c = (unsigned char)p->text[p->at++];
    if (c == '"') { if (!out) { out = calloc(1, 1); if (!out) fail(p, "Out of memory"); } return out; }
    if (c < 0x20) { fail(p, "Unescaped control in string"); free(out); return NULL; }
    if (c == '\\') {
      if (p->at >= p->size) { fail(p, "Truncated escape"); free(out); return NULL; }
      c = (unsigned char)p->text[p->at++];
      if (c == '"' || c == '\\' || c == '/') { if (!append_utf8(&out, &used, &capacity, c)) goto memory; }
      else if (c == 'b') { if (!append_utf8(&out, &used, &capacity, 8)) goto memory; }
      else if (c == 'f') { if (!append_utf8(&out, &used, &capacity, 12)) goto memory; }
      else if (c == 'n') { if (!append_utf8(&out, &used, &capacity, 10)) goto memory; }
      else if (c == 'r') { if (!append_utf8(&out, &used, &capacity, 13)) goto memory; }
      else if (c == 't') { if (!append_utf8(&out, &used, &capacity, 9)) goto memory; }
      else if (c == 'u') {
        unsigned cp, low;
        if (p->at + 4 > p->size || !hex4(p->text + p->at, &cp)) { fail(p, "Invalid Unicode escape"); free(out); return NULL; }
        p->at += 4;
        if (cp >= 0xd800 && cp <= 0xdbff) {
          if (p->at + 6 > p->size || p->text[p->at] != '\\' || p->text[p->at+1] != 'u' ||
              !hex4(p->text + p->at + 2, &low) || low < 0xdc00 || low > 0xdfff) {
            fail(p, "Unpaired high surrogate"); free(out); return NULL;
          }
          p->at += 6;
          cp = 0x10000 + ((cp - 0xd800) << 10) + (low - 0xdc00);
        } else if (cp >= 0xdc00 && cp <= 0xdfff) { fail(p, "Unpaired low surrogate"); free(out); return NULL; }
        if (!append_utf8(&out, &used, &capacity, cp)) goto memory;
      } else { fail(p, "Invalid escape"); free(out); return NULL; }
      continue;
    }
    if (c < 0x80) { if (!append_utf8(&out, &used, &capacity, c)) goto memory; continue; }
    {
      unsigned char bytes[4]; size_t n = 0, i; unsigned cp;
      bytes[n++] = c;
      while (n < 4 && p->at < p->size && ((unsigned char)p->text[p->at] & 0xc0) == 0x80) bytes[n++] = (unsigned char)p->text[p->at++];
      n = utf8_sequence(bytes, &cp);
      if (!n) { fail(p, "Invalid UTF-8 in string"); free(out); return NULL; }
      if (!append_utf8(&out, &used, &capacity, cp)) goto memory;
    }
  }
  fail(p, "Unterminated string");
  free(out);
  return NULL;
memory:
  fail(p, "Out of memory");
  free(out);
  return NULL;
}
static cv_json *new_value(parser *p, cv_json_type type) {
  cv_json *v = calloc(1, sizeof(*v));
  if (!v) { fail(p, "Out of memory"); return NULL; }
  v->type = type;
  return v;
}
static cv_json *parse_value(parser *p);
static cv_json *parse_array(parser *p) {
  cv_json *v = new_value(p, CV_JSON_ARRAY);
  if (!v) return NULL;
  p->at++;
  skip(p);
  if (p->at < p->size && p->text[p->at] == ']') { p->at++; return v; }
  for (;;) {
    cv_json *item, **next;
    skip(p);
    if (!(item = parse_value(p))) { cv_json_free(v); return NULL; }
    next = realloc(v->items, (v->count + 1) * sizeof(*next));
    if (!next) { cv_json_free(item); cv_json_free(v); fail(p, "Out of memory"); return NULL; }
    v->items = next; v->items[v->count++] = item;
    skip(p);
    if (p->at >= p->size) break;
    if (p->text[p->at] == ',') { p->at++; continue; }
    if (p->text[p->at] == ']') { p->at++; return v; }
    break;
  }
  fail(p, "Expected ',' or ']' ");
  cv_json_free(v);
  return NULL;
}
static cv_json *parse_object(parser *p) {
  cv_json *v = new_value(p, CV_JSON_OBJECT);
  if (!v) return NULL;
  p->at++;
  skip(p);
  if (p->at < p->size && p->text[p->at] == '}') { p->at++; return v; }
  for (;;) {
    char *key; cv_json *item, **next; char **keys; size_t i;
    skip(p);
    if (!(key = parse_string(p))) { cv_json_free(v); return NULL; }
    for (i = 0; i < v->count; i++) if (!strcmp(v->keys[i], key)) {
      free(key); fail(p, "Duplicate object key"); cv_json_free(v); return NULL;
    }
    skip(p);
    if (p->at >= p->size || p->text[p->at] != ':') { free(key); fail(p, "Expected ':'"); cv_json_free(v); return NULL; }
    p->at++;
    if (!(item = parse_value(p))) { free(key); cv_json_free(v); return NULL; }
    next = realloc(v->items, (v->count + 1) * sizeof(*next));
    keys = realloc(v->keys, (v->count + 1) * sizeof(*keys));
    if (!next || !keys) { free(key); cv_json_free(item); free(next); free(keys); fail(p, "Out of memory"); cv_json_free(v); return NULL; }
    v->items = next; v->keys = keys;
    v->keys[v->count] = key; v->items[v->count] = item; v->count++;
    skip(p);
    if (p->at >= p->size) break;
    if (p->text[p->at] == ',') { p->at++; continue; }
    if (p->text[p->at] == '}') { p->at++; return v; }
    break;
  }
  fail(p, "Expected ',' or '}'");
  cv_json_free(v);
  return NULL;
}
static int literal(parser *p, const char *word) {
  size_t n = strlen(word);
  if (p->at + n > p->size || memcmp(p->text + p->at, word, n)) return 0;
  p->at += n; return 1;
}
static cv_json *parse_value(parser *p) {
  cv_json *v;
  skip(p);
  if (++p->depth > 64) { fail(p, "JSON nesting exceeds 64"); p->depth--; return NULL; }
  if (p->at < p->size) {
    char c = p->text[p->at];
    if (c == '"') { char *s = parse_string(p); p->depth--; if (!s) return NULL; v = new_value(p, CV_JSON_STRING); if (!v) { free(s); return NULL; } v->string = s; return v; }
    if (c == '{') { v = parse_object(p); p->depth--; return v; }
    if (c == '[') { v = parse_array(p); p->depth--; return v; }
    if (literal(p, "null")) { p->depth--; return new_value(p, CV_JSON_NULL); }
    if (literal(p, "true")) { p->depth--; v = new_value(p, CV_JSON_BOOL); if (v) v->boolean = 1; return v; }
    if (literal(p, "false")) { p->depth--; return new_value(p, CV_JSON_BOOL); }
    if (c == '-' || (c >= '0' && c <= '9')) {
      size_t start = p->at; int integral = 1; char *end = NULL;
      if (p->text[p->at] == '-') p->at++;
      while (p->at < p->size && p->text[p->at] >= '0' && p->text[p->at] <= '9') p->at++;
      if (p->at < p->size && p->text[p->at] == '.') { integral = 0; p->at++; while (p->at < p->size && p->text[p->at] >= '0' && p->text[p->at] <= '9') p->at++; }
      if (p->at < p->size && (p->text[p->at] == 'e' || p->text[p->at] == 'E')) {
        integral = 0; p->at++;
        if (p->at < p->size && (p->text[p->at] == '+' || p->text[p->at] == '-')) p->at++;
        while (p->at < p->size && p->text[p->at] >= '0' && p->text[p->at] <= '9') p->at++;
      }
      v = new_value(p, CV_JSON_NUMBER);
      if (!v) { p->depth--; return NULL; }
      {
        char *buffer = malloc(p->at - start + 1);
        if (!buffer) { cv_json_free(v); p->depth--; fail(p, "Out of memory"); return NULL; }
        memcpy(buffer, p->text + start, p->at - start); buffer[p->at - start] = 0;
        v->number = strtod(buffer, &end);
        v->integral = integral;
        v->integer = integral ? strtoll(buffer, &end, 10) : (long long)v->number;
        free(buffer);
      }
      p->depth--;
      return v;
    }
  }
  fail(p, "Unexpected token");
  p->depth--;
  return NULL;
}
cv_json *cv_json_parse(const char *text, size_t size, char **error) {
  parser p; cv_json *value;
  memset(&p, 0, sizeof(p)); p.text = text; p.size = size;
  if (error) *error = NULL;
  if (size >= 3 && (unsigned char)text[0] == 0xef && (unsigned char)text[1] == 0xbb && (unsigned char)text[2] == 0xbf) p.at = 3;
  skip(&p);
  value = parse_value(&p);
  if (!value) { if (error) { *error = p.error; p.error = NULL; } free(p.error); return NULL; }
  skip(&p);
  if (p.at != p.size) {
    fail(&p, "Trailing data");
    cv_json_free(value);
    if (error) { *error = p.error; p.error = NULL; }
    free(p.error);
    return NULL;
  }
  free(p.error);
  return value;
}
void cv_json_free(cv_json *v) {
  size_t i;
  if (!v) return;
  if (v->string) free(v->string);
  for (i = 0; i < v->count; i++) { if (v->keys) free(v->keys[i]); if (v->items) cv_json_free(v->items[i]); }
  free(v->keys); free(v->items); free(v);
}
const cv_json *cv_json_get(const cv_json *object, const char *key) {
  size_t i;
  if (!object || object->type != CV_JSON_OBJECT) return NULL;
  for (i = 0; i < object->count; i++) if (!strcmp(object->keys[i], key)) return object->items[i];
  return NULL;
}
