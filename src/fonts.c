/* SPDX-License-Identifier: GPL-3.0-only */
#include "layout_internal.h"
#include <ctype.h>

static int ws(unsigned char c) { return c == ' ' || (c >= 9 && c <= 13); }
static int same(const char *s, size_t n, const char *word) {
  size_t i;
  if (strlen(word) != n) return 0;
  for (i = 0; i < n; i++)
    if (tolower((unsigned char)s[i]) != tolower((unsigned char)word[i])) return 0;
  return 1;
}
int exr_family_equal(const char *a, const char *b) { return same(a, strlen(a), b); }
/* Decode CSS escapes without allocating during per-cluster family matching. */
static int unescape(const char *s, size_t n, char *out, size_t capacity) {
  size_t i = 0, used = 0;
  while (i < n) {
    uint32_t cp = (unsigned char)s[i++];
    if (cp == '\\') {
      unsigned digits = 0;
      if (i == n) return 0;
      if (s[i] == '\r' || s[i] == '\n' || s[i] == '\f') {
        if (s[i++] == '\r' && i < n && s[i] == '\n') i++;
        continue;
      }
      cp = 0;
      while (i < n && digits < 6 && isxdigit((unsigned char)s[i])) {
        unsigned ch = (unsigned char)s[i++];
        cp = cp*16 + (isdigit(ch) ? ch - '0' : (unsigned)tolower(ch) - 'a' + 10);
        digits++;
      }
      if (!digits) { cp = (unsigned char)s[i++]; }
      else {
        if (i < n && ws((unsigned char)s[i])) {
          if (s[i++] == '\r' && i < n && s[i] == '\n') i++;
        }
        if (!cp || cp > 0x10ffff || (cp >= 0xd800 && cp <= 0xdfff)) cp = 0xfffd;
        if (used + (cp >= 0x10000 ? 4u : cp >= 0x800 ? 3u : cp >= 0x80 ? 2u : 1u) >= capacity)
          return 0;
        if (cp >= 0x10000) {
          out[used++] = (char)(0xf0 | (cp >> 18));
          out[used++] = (char)(0x80 | ((cp >> 12) & 63));
          out[used++] = (char)(0x80 | ((cp >> 6) & 63));
          out[used++] = (char)(0x80 | (cp & 63));
          continue;
        }
        if (cp >= 0x800) {
          out[used++] = (char)(0xe0 | (cp >> 12));
          out[used++] = (char)(0x80 | ((cp >> 6) & 63));
          out[used++] = (char)(0x80 | (cp & 63));
          continue;
        }
        if (cp >= 0x80) {
          out[used++] = (char)(0xc0 | (cp >> 6));
          out[used++] = (char)(0x80 | (cp & 63));
          continue;
        }
      }
    }
    if (!cp || used + 1 >= capacity) return 0;
    out[used++] = (char)cp;
  }
  out[used] = 0;
  return used != 0;
}
int exr_family_next(const char *s, size_t *at, char out[128]) {
  size_t i = *at, start, end;
  int quote = 0;
  while (ws((unsigned char)s[i])) i++;
  if (!s[i]) return 0;
  if (s[i] == '\'' || s[i] == '"') quote = s[i++];
  start = i;
  while (s[i] && (quote ? s[i] != quote : s[i] != ',')) {
    if (s[i] == '\\' && s[i + 1]) i++;
    else if (!quote && (s[i] == '\'' || s[i] == '"' || s[i] == '(' ||
                       s[i] == ')' || s[i] == ';' || s[i] == '{' || s[i] == '}')) return -1;
    i++;
  }
  end = i;
  if (quote) { if (s[i] != quote) return -1; i++; }
  else while (end > start && ws((unsigned char)s[end - 1])) end--;
  while (ws((unsigned char)s[i])) i++;
  if (s[i] && s[i] != ',') return -1;
  if (!unescape(s + start, end - start, out, 128)) return -1;
  if (!quote) {
    size_t a, b = 0;
    for (a = 0; out[a]; a++) {
      if (ws((unsigned char)out[a])) {
        if (b && out[b - 1] != ' ') out[b++] = ' ';
      } else out[b++] = out[a];
    }
    if (b && out[b - 1] == ' ') b--;
    out[b] = 0;
    if (!b) return -1;
  }
  if (s[i] == ',') {
    i++;
    while (ws((unsigned char)s[i])) i++;
    if (!s[i]) return -1;
  }
  *at = i;
  return 1;
}
int exr_parse_font_rule(const char *s, size_t n, const char *base,
                         size_t chapter, exr_font_rule *out) {
  size_t at = 0;
  memset(out, 0, sizeof(*out));
  out->chapter = chapter;
  if (strlen(base) >= sizeof(out->base)) return 0;
  strcpy(out->base, base);
  while (at < n) {
    size_t end = at + exr_css_delimiter(s + at, n - at, ';');
    size_t colon = at + exr_css_delimiter(s + at, end - at, ':'), a = at, b = colon;
    char value[2048];
    at = end < n ? end + 1 : n;
    while (a < b && ws((unsigned char)s[a])) a++;
    while (b > a && ws((unsigned char)s[b - 1])) b--;
    if (colon == end) continue;
    {
      size_t v = colon + 1, stop = end;
      while (v < stop && ws((unsigned char)s[v])) v++;
      while (stop > v && ws((unsigned char)s[stop - 1])) stop--;
      if (stop == v || stop - v >= sizeof(value)) continue;
      memcpy(value, s + v, stop - v); value[stop - v] = 0;
    }
    if (same(s + a, b - a, "font-family")) {
      size_t position = 0;
      char extra[128];
      if (exr_family_next(value, &position, out->family) != 1 ||
          exr_family_next(value, &position, extra) != 0) return 0;
    } else if (same(s + a, b - a, "src")) strcpy(out->source, value);
    else if (same(s + a, b - a, "font-weight")) {
      char *tail;
      long weight = strtol(value, &tail, 10);
      if (!strcmp(value, "bold")) out->flags |= 1;
      else if (!strcmp(value, "normal")) out->flags &= ~1u;
      else if (*tail || tail == value || weight < 100 || weight > 900) return 0;
      else out->flags = (out->flags & ~1u) | (weight >= 600 ? 1u : 0u);
    } else if (same(s + a, b - a, "font-style")) {
      if (!strcmp(value, "italic") || !strcmp(value, "oblique")) out->flags |= 2;
      else if (!strcmp(value, "normal")) out->flags &= ~2u;
      else return 0;
    }
  }
  return out->family[0] && out->source[0];
}
static int requested(const exr_document *d, const exr_style *styles, const exr_font_rule *r) {
  size_t i;
  for (i = 0; i < d->node_count; i++) {
    size_t at = 0;
    char family[128];
    if (!styles[i].family || styles[i].display == EXR_CSS_NONE ||
        (r->chapter != SIZE_MAX && d->nodes[i].chapter != r->chapter)) continue;
    while (exr_family_next(styles[i].family, &at, family) == 1)
      if (exr_family_equal(family, r->family)) return 1;
  }
  return 0;
}
static exr_status load_font(const exr_document *d, exr_font *font, const exr_font_rule *r,
                              void **out, size_t *size, size_t *read_bytes, exr_error *e) {
  size_t at = 0, n = strlen(r->source), attempts = 0;
  *out = NULL; *size = 0;
  while (at < n) {
    size_t end = at + exr_css_delimiter(r->source + at, n - at, ',');
    size_t a = at, b = end, i;
    char uri[2048], path[2048];
    FT_Face probe = NULL;
    exr_status status;
    at = end < n ? end + 1 : n;
    while (a < b && ws((unsigned char)r->source[a])) a++;
    if (b - a < 5 || !same(r->source + a, 3, "url") || r->source[a + 3] != '(') continue;
    a += 4;
    b = a + exr_css_delimiter(r->source + a, end - a, ')');
    if (b == end) continue;
    while (a < b && ws((unsigned char)r->source[a])) a++;
    while (b > a && ws((unsigned char)r->source[b - 1])) b--;
    if (a < b && (r->source[a] == '\'' || r->source[a] == '"')) {
      if (b - a < 2 || r->source[b - 1] != r->source[a]) continue;
      a++; b--;
    }
    if (!unescape(r->source + a, b - a, uri, sizeof(uri)) ||
        !exr_resolve_path(r->base, uri, path)) continue;
    for (i = 0; i < d->resource_count; i++)
      if (!strcmp(path, d->resources[i].path)) break;
    if (i == d->resource_count) continue;
    if (++attempts > 8) return exr_fail(e, EXR_LIMIT, "Font source retry limit exceeded");
    status = exr_document_resource(d, i, out, size, e);
    if (status == EXR_MEMORY || status == EXR_LIMIT) return status;
    if (status != EXR_OK) continue;
    if (*size > EXR_MAX_INPUT - *read_bytes) {
      exr_free(*out); *out = NULL;
      return exr_fail(e, EXR_LIMIT, "Embedded font reads exceed 128 MiB");
    }
    *read_bytes += *size;
    if (!FT_New_Memory_Face(font->library, *out, (FT_Long)*size, 0, &probe) &&
        FT_IS_SCALABLE(probe) && !FT_Select_Charmap(probe, FT_ENCODING_UNICODE)) {
      FT_Done_Face(probe);
      return EXR_OK;
    }
    if (probe) FT_Done_Face(probe);
    exr_free(*out); *out = NULL; *size = 0;
  }
  return EXR_OK;
}
exr_status exr_book_fonts(const exr_document *d, exr_font *fallback,
                           const exr_style *styles, const exr_font_rule *rules, size_t count,
                           exr_font **out, exr_error *e) {
  exr_font_input inputs[32];
  void *loaded[32] = {0};
  const exr_font_rule *selected[32] = {0};
  size_t i, used = fallback->count, total = 0, reads = 0;
  exr_status status = EXR_OK;
  *out = NULL;
  for (i = 0; i < used; i++) {
    inputs[i] = (exr_font_input){fallback->faces[i].bytes, fallback->faces[i].bytes_size,
                                  (size_t)fallback->faces[i].face->face_index};
    total += inputs[i].size;
  }
  for (i = 0; i < count; i++) {
    void *bytes = NULL;
    size_t size = 0;
    if (!requested(d, styles, &rules[i])) continue;
    status = load_font(d, fallback, &rules[i], &bytes, &size, &reads, e);
    if (status != EXR_OK) goto done;
    if (!bytes) continue;
    if (used == 32 || size > EXR_MAX_INPUT - total) {
      exr_free(bytes);
      status = exr_fail(e, EXR_LIMIT, "Combined font set exceeds 32 faces or 128 MiB");
      goto done;
    }
    total += size;
    selected[used] = &rules[i]; loaded[used] = bytes;
    inputs[used++] = (exr_font_input){bytes, size, 0};
  }
  if (used == fallback->count) { exr_font_ref(fallback); *out = fallback; }
  else {
    status = exr_font_create(inputs, used, out, e);
    if (status != EXR_OK) goto done;
    (*out)->base_count = fallback->count;
    (*out)->fallback = fallback;
    exr_font_ref(fallback);
    for (i = 0; i < used; i++) {
      exr_face *face = &(*out)->faces[i];
      if (selected[i]) {
        strcpy(face->family, selected[i]->family);
        face->style_flags = selected[i]->flags;
        face->scope = selected[i]->chapter;
      } else {
        strcpy(face->family, fallback->faces[i].family);
        face->style_flags = fallback->faces[i].style_flags;
        face->scope = fallback->faces[i].scope;
      }
    }
  }
done:
  for (i = 0; i < 32; i++) exr_free(loaded[i]);
  return status == EXR_OK ? exr_fail(e, EXR_OK, "") : status;
}
size_t exr_font_order(const exr_font *f, const char *list, unsigned flags,
                       size_t chapter, size_t order[32]) {
  char family[128];
  size_t at = 0, count = 0, i;
  uint32_t seen = 0;
  unsigned score;
  while (list && exr_family_next(list, &at, family) == 1) {
    for (score = 0; score < 4; score++) {
      for (i = f->count; i; i--) {
        size_t index = i - 1 < f->base_count ? f->base_count - i : i - 1;
        const exr_face *face = &f->faces[index];
        if ((seen & (UINT32_C(1) << index)) ||
            (face->scope != SIZE_MAX && face->scope != chapter) ||
            !exr_family_equal(family, face->family) || ((flags ^ face->style_flags) & 3) != score)
          continue;
        seen |= UINT32_C(1) << index;
        order[count++] = index;
      }
    }
  }
  for (i = 0; i < f->base_count; i++)
    if (!(seen & (UINT32_C(1) << i))) order[count++] = i;
  return count;
}
