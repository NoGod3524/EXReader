/* SPDX-License-Identifier: GPL-3.0-only */
#include "internal.h"
#include <ctype.h>
#include <expat.h>
#include <miniz.h>
static uint32_t windows1252(unsigned char c) {
  static const uint16_t map[32] = {0x20ac, 0x81,   0x201a, 0x192,  0x201e, 0x2026, 0x2020, 0x2021,
                                   0x2c6,  0x2030, 0x160,  0x2039, 0x152,  0x8d,   0x17d,  0x8f,
                                   0x90,   0x2018, 0x2019, 0x201c, 0x201d, 0x2022, 0x2013, 0x2014,
                                   0x2dc,  0x2122, 0x161,  0x203a, 0x153,  0x9d,   0x17e,  0x178};
  return c >= 128 && c < 160 ? map[c - 128] : c;
}
static int space(unsigned char c) { return c == ' ' || c == '\r' || c == '\n' || c == '\t'; }
static const char *local(const char *name) {
  const char *p = strrchr(name, '|');
  return p ? p + 1 : name;
}
static const char *attribute(const char **a, const char *name) {
  size_t i;
  for (i = 0; a && a[i]; i += 2)
    if (!strcmp(local(a[i]), name))
      return a[i + 1];
  return NULL;
}
static int flush(exr_document *d, exr_buffer *b, unsigned heading) {
  int ok = exr_add_block(d, b->data, b->size, heading);
  b->size = 0;
  if (b->data)
    b->data[0] = 0;
  return ok;
}
static exr_status plain(exr_document *d, const void *data, size_t n, exr_error *e) {
  exr_buffer b = {0};
  size_t i = 0, start = 0;
  exr_status s = exr_decode(data, n, &b, e);
  if (s == EXR_OK && b.size) {
    for (i = 0; i <= b.size; i++)
      if (i == b.size || b.data[i] == '\n') {
        if (!exr_add_block(d, b.data + start, i - start, 0)) {
          s = exr_fail(e, EXR_LIMIT, "Text limit exceeded");
          break;
        }
        start = i + 1;
      }
  }
  free(b.data);
  return s;
}
static int block_tag(const char *s) {
  return !strcmp(s, "p") || !strcmp(s, "div") || !strcmp(s, "li") || !strcmp(s, "br") ||
         !strcmp(s, "tr") || !strcmp(s, "blockquote") || !strcmp(s, "section") ||
         !strcmp(s, "article") || !strcmp(s, "body") ||
         (s[0] == 'h' && s[1] >= '1' && s[1] <= '6' && !s[2]);
}
static exr_status html(exr_document *d, const void *data, size_t n, exr_error *e) {
  exr_buffer input = {0}, out = {0};
  exr_status result;
  size_t i = 0;
  unsigned heading = 0;
  char skip[32] = {0};
  result = exr_decode(data, n, &input, e);
  if (result != EXR_OK)
    goto done;
  while (i < input.size) {
    if (input.data[i] == '<' && i + 1 < input.size &&
        (isalpha((unsigned char)input.data[i + 1]) || strchr("/!?", input.data[i + 1]))) {
      size_t j = i + 1, k = 0;
      char tag[32] = {0};
      int closing = 0, quote = 0;
      if (i + 4 <= input.size && !memcmp(input.data + i, "<!--", 4)) {
        const char *end = strstr(input.data + i + 4, "-->");
        if (!end) {
          result = exr_fail(e, EXR_FORMAT, "Unterminated HTML comment");
          goto done;
        }
        i = (size_t)(end - input.data) + 3;
        continue;
      }
      if (input.data[j] == '/') {
        closing = 1;
        j++;
      }
      while (j < input.size && (isalnum((unsigned char)input.data[j]) || input.data[j] == ':' ||
                                input.data[j] == '-')) {
        if (k < 31)
          tag[k++] = (char)tolower((unsigned char)input.data[j]);
        j++;
      }
      for (; j < input.size; j++) {
        char c = input.data[j];
        if (quote) {
          if (c == quote)
            quote = 0;
        } else if (c == '\'' || c == '"')
          quote = c;
        else if (c == '>')
          break;
      }
      if (j == input.size) {
        result = exr_fail(e, EXR_FORMAT, "Unterminated HTML tag");
        goto done;
      }
      i = j + 1;
      if (skip[0]) {
        if (closing && !strcmp(tag, skip))
          skip[0] = 0;
        continue;
      }
      if (!closing && (!strcmp(tag, "head") || !strcmp(tag, "script") || !strcmp(tag, "style") ||
                       !strcmp(tag, "object"))) {
        snprintf(skip, sizeof(skip), "%s", tag);
        continue;
      }
      if (block_tag(tag)) {
        if (!flush(d, &out, heading)) {
          result = exr_fail(e, EXR_LIMIT, "HTML text limit exceeded");
          goto done;
        }
        heading = !closing && tag[0] == 'h' ? (unsigned)(tag[1] - '0') : 0;
      }
      continue;
    }
    if (skip[0]) {
      i++;
      continue;
    }
    if (input.data[i] == '&') {
      size_t j = i + 1;
      uint32_t cp = 0;
      int valid = 0;
      while (j < input.size && j - i < 16 && input.data[j] != ';' &&
             !space((unsigned char)input.data[j]))
        j++;
      if (j < input.size && input.data[j] == ';') {
        size_t len = j - i - 1;
        const char *a = input.data + i + 1;
        if (len == 3 && !memcmp(a, "amp", 3)) {
          cp = '&';
          valid = 1;
        } else if (len == 2 && !memcmp(a, "lt", 2)) {
          cp = '<';
          valid = 1;
        } else if (len == 2 && !memcmp(a, "gt", 2)) {
          cp = '>';
          valid = 1;
        } else if (len == 4 && !memcmp(a, "quot", 4)) {
          cp = '"';
          valid = 1;
        } else if (len == 4 && !memcmp(a, "apos", 4)) {
          cp = '\'';
          valid = 1;
        } else if (len == 4 && !memcmp(a, "nbsp", 4)) {
          cp = ' ';
          valid = 1;
        } else if (len > 1 && a[0] == '#') {
          size_t x = 1;
          unsigned base = 10;
          valid = 1;
          if (x < len && (a[x] == 'x' || a[x] == 'X')) {
            base = 16;
            x++;
          }
          if (x == len)
            valid = 0;
          for (; x < len && valid; x++) {
            unsigned v;
            if (a[x] >= '0' && a[x] <= '9')
              v = (unsigned)(a[x] - '0');
            else if (base == 16 && a[x] >= 'a' && a[x] <= 'f')
              v = (unsigned)(a[x] - 'a' + 10);
            else if (base == 16 && a[x] >= 'A' && a[x] <= 'F')
              v = (unsigned)(a[x] - 'A' + 10);
            else {
              valid = 0;
              break;
            }
            if (v >= base || cp > (0x10ffff - v) / base) {
              valid = 0;
              break;
            }
            cp = cp * base + v;
          }
        }
        if (valid && cp && exr_codepoint(&out, cp)) {
          i = j + 1;
          continue;
        }
      }
    }
    if (space((unsigned char)input.data[i])) {
      if (out.size && out.data[out.size - 1] != ' ' && !exr_append(&out, " ", 1)) {
        result = EXR_LIMIT;
        goto done;
      }
      i++;
    } else {
      if (!exr_append(&out, input.data + i, 1)) {
        result = EXR_LIMIT;
        goto done;
      }
      i++;
    }
  }
  if (!flush(d, &out, heading))
    result = exr_fail(e, EXR_LIMIT, "HTML text limit exceeded");
done:
  free(input.data);
  free(out.data);
  return result;
}
typedef struct {
  exr_document *doc;
  XML_Parser parser;
  exr_buffer text, title;
  int depth, body, paragraph, title_depth, docx, failed;
  unsigned heading;
} flow_xml;
static void XMLCALL flow_start(void *user, const char *full, const char **attrs) {
  flow_xml *x = user;
  const char *tag = local(full);
  x->depth++;
  if (x->depth > 256) {
    x->failed = 1;
    XML_StopParser(x->parser, XML_FALSE);
    return;
  }
  if (!strcmp(tag, "body"))
    x->body = x->depth;
  if (!strcmp(tag, "book-title") && !x->docx)
    x->title_depth = x->depth;
  if (x->body && (!strcmp(tag, "p") || !strcmp(tag, "v") || !strcmp(tag, "subtitle"))) {
    if (!flush(x->doc, &x->text, x->heading))
      x->failed = 1;
    x->paragraph = x->depth;
  }
  if (x->body && !strcmp(tag, "title"))
    x->heading = 1;
  if (x->docx && !strcmp(tag, "pStyle")) {
    const char *v = attribute(attrs, "val");
    if (v && !strncmp(v, "Heading", 7) && v[7] >= '1' && v[7] <= '6')
      x->heading = (unsigned)(v[7] - '0');
  }
  if (x->paragraph && (!strcmp(tag, "tab") || !strcmp(tag, "br")))
    if (!exr_append(&x->text, " ", 1))
      x->failed = 1;
  if (x->failed)
    XML_StopParser(x->parser, XML_FALSE);
}
static void XMLCALL flow_end(void *user, const char *full) {
  flow_xml *x = user;
  const char *tag = local(full);
  if (x->paragraph == x->depth) {
    if (!flush(x->doc, &x->text, x->heading))
      x->failed = 1;
    x->paragraph = 0;
    if (x->docx)
      x->heading = 0;
  }
  if (x->title_depth == x->depth) {
    if (x->title.size && !x->doc->title)
      x->doc->title = exr_copy(x->title.data, x->title.size);
    x->title_depth = 0;
  }
  if (x->body == x->depth)
    x->body = 0;
  if (!strcmp(tag, "title"))
    x->heading = 0;
  x->depth--;
  if (x->failed)
    XML_StopParser(x->parser, XML_FALSE);
}
static void XMLCALL flow_text(void *user, const XML_Char *s, int n) {
  flow_xml *x = user;
  if (x->paragraph && !exr_append(&x->text, s, (size_t)n))
    x->failed = 1;
  if (x->title_depth && !exr_append(&x->title, s, (size_t)n))
    x->failed = 1;
  if (x->failed)
    XML_StopParser(x->parser, XML_FALSE);
}
static void XMLCALL reject_entity(void *user, const XML_Char *name, int parameter,
                                  const XML_Char *value, int length, const XML_Char *base,
                                  const XML_Char *system, const XML_Char *public_id,
                                  const XML_Char *notation) {
  flow_xml *x = user;
  (void)name;
  (void)parameter;
  (void)value;
  (void)length;
  (void)base;
  (void)system;
  (void)public_id;
  (void)notation;
  x->failed = 1;
  XML_StopParser(x->parser, XML_FALSE);
}
static exr_status xml_flow(exr_document *doc, const void *data, size_t n, int docx, exr_error *e) {
  flow_xml x = {0};
  enum XML_Status result;
  x.doc = doc;
  x.docx = docx;
  x.parser = XML_ParserCreateNS(NULL, '|');
  if (!x.parser)
    return exr_fail(e, EXR_MEMORY, "XML allocation failed");
  XML_SetUserData(x.parser, &x);
  XML_SetElementHandler(x.parser, flow_start, flow_end);
  XML_SetCharacterDataHandler(x.parser, flow_text);
  XML_SetEntityDeclHandler(x.parser, reject_entity);
  XML_SetParamEntityParsing(x.parser, XML_PARAM_ENTITY_PARSING_NEVER);
  result = XML_Parse(x.parser, data, (int)n, XML_TRUE);
  if (result == XML_STATUS_ERROR || x.failed)
    exr_fail(e, EXR_FORMAT, "XML rejected: %s", XML_ErrorString(XML_GetErrorCode(x.parser)));
  XML_ParserFree(x.parser);
  free(x.text.data);
  free(x.title.data);
  return result == XML_STATUS_OK && !x.failed ? EXR_OK : EXR_FORMAT;
}
typedef struct {
  mz_zip_archive archive;
  size_t expanded;
  exr_status status;
} archive;
static void *member(archive *z, const char *name, size_t *size, exr_error *e) {
  int index = mz_zip_reader_locate_file(&z->archive, name, NULL, MZ_ZIP_FLAG_CASE_SENSITIVE);
  mz_zip_archive_file_stat stat;
  void *p;
  if (index < 0 || !mz_zip_reader_file_stat(&z->archive, (mz_uint)index, &stat)) {
    z->status = EXR_FORMAT;
    exr_fail(e, EXR_FORMAT, "ZIP member missing: %s", name);
    return NULL;
  }
  if (stat.m_uncomp_size > 32 * 1024 * 1024 || stat.m_uncomp_size > EXR_MAX_INPUT - z->expanded ||
      stat.m_is_encrypted) {
    z->status = EXR_LIMIT;
    exr_fail(e, EXR_LIMIT, "ZIP member is encrypted or exceeds extraction limit");
    return NULL;
  }
  p = mz_zip_reader_extract_to_heap(&z->archive, (mz_uint)index, size, 0);
  if (!p) {
    z->status = EXR_FORMAT;
    exr_fail(e, EXR_FORMAT, "ZIP member decompression failed");
    return NULL;
  }
  z->expanded += *size;
  return p;
}
typedef struct {
  char *id, *href, *media_type, *properties;
} item;
typedef struct {
  char *id;
  int linear;
} spine_item;
typedef struct {
  XML_Parser parser;
  char *root;
  item *items;
  size_t count, capacity;
  spine_item *spine;
  size_t spine_count, spine_cap;
  exr_buffer title;
  int in_title, failed, depth;
} package;
static void XMLCALL package_start(void *user, const char *full, const char **attrs) {
  package *p = user;
  const char *tag = local(full), *a, *b;
  if (++p->depth > 256) {
    p->failed = 1;
    XML_StopParser(p->parser, XML_FALSE);
    return;
  }
  if (!strcmp(tag, "rootfile") && !p->root) {
    a = attribute(attrs, "full-path");
    if (a)
      p->root = exr_copy(a, strlen(a));
    if (!p->root)
      p->failed = 1;
  }
  if (!strcmp(tag, "item")) {
    a = attribute(attrs, "id");
    b = attribute(attrs, "href");
    if (!a || !b || p->count >= 10000 ||
        !exr_grow((void **)&p->items, &p->capacity, p->count + 1, sizeof(item))) {
      p->failed = 1;
    } else {
      item *v = &p->items[p->count++];
      const char *media = attribute(attrs, "media-type");
      const char *properties = attribute(attrs, "properties");
      v->id = exr_copy(a, strlen(a));
      v->href = exr_copy(b, strlen(b));
      v->media_type = exr_copy(media ? media : "", media ? strlen(media) : 0);
      v->properties = exr_copy(properties ? properties : "", properties ? strlen(properties) : 0);
      if (!v->id || !v->href || !v->media_type || !v->properties)
        p->failed = 1;
    }
  }
  if (!strcmp(tag, "itemref")) {
    a = attribute(attrs, "idref");
    b = attribute(attrs, "linear");
    if (!a || p->spine_count >= 10000 ||
        !exr_grow((void **)&p->spine, &p->spine_cap, p->spine_count + 1, sizeof(spine_item))) {
      p->failed = 1;
    } else {
      p->spine[p->spine_count].id = exr_copy(a, strlen(a));
      p->spine[p->spine_count].linear = !b || strcmp(b, "no");
      if (!p->spine[p->spine_count++].id)
        p->failed = 1;
    }
  }
  if (!strcmp(tag, "title"))
    p->in_title = 1;
  if (p->failed)
    XML_StopParser(p->parser, XML_FALSE);
}
static void XMLCALL package_end(void *user, const char *tag) {
  package *p = user;
  if (!strcmp(local(tag), "title"))
    p->in_title = 0;
  p->depth--;
}
static void XMLCALL package_text(void *user, const XML_Char *s, int n) {
  package *p = user;
  if (p->in_title && !exr_append(&p->title, s, (size_t)n)) {
    p->failed = 1;
    XML_StopParser(p->parser, XML_FALSE);
  }
}
static void XMLCALL package_entity(void *user, const XML_Char *name, int parameter,
                                   const XML_Char *value, int length, const XML_Char *base,
                                   const XML_Char *system, const XML_Char *public_id,
                                   const XML_Char *notation) {
  package *p = user;
  (void)name;
  (void)parameter;
  (void)value;
  (void)length;
  (void)base;
  (void)system;
  (void)public_id;
  (void)notation;
  p->failed = 1;
  XML_StopParser(p->parser, XML_FALSE);
}
static int package_parse(package *p, const void *data, size_t n) {
  enum XML_Status ok;
  p->parser = XML_ParserCreateNS(NULL, '|');
  if (!p->parser)
    return 0;
  XML_SetUserData(p->parser, p);
  XML_SetElementHandler(p->parser, package_start, package_end);
  XML_SetCharacterDataHandler(p->parser, package_text);
  XML_SetEntityDeclHandler(p->parser, package_entity);
  XML_SetParamEntityParsing(p->parser, XML_PARAM_ENTITY_PARSING_NEVER);
  ok = XML_Parse(p->parser, data, (int)n, XML_TRUE);
  XML_ParserFree(p->parser);
  p->parser = NULL;
  return ok == XML_STATUS_OK && !p->failed;
}
static int uri_decode(const char *s, size_t n, char out[2048]) {
  size_t i, used = 0, at = 0;
  uint32_t cp;
  if (n >= 2048)
    return 0;
  for (i = 0; i < n; i++) {
    unsigned char c = (unsigned char)s[i];
    if (c == '%') {
      unsigned a, b;
      if (n - i < 3 || !isxdigit((unsigned char)s[i + 1]) || !isxdigit((unsigned char)s[i + 2]))
        return 0;
      c = (unsigned char)s[++i];
      a = (unsigned)(isdigit(c) ? c - '0' : tolower(c) - 'a' + 10);
      c = (unsigned char)s[++i];
      b = (unsigned)(isdigit(c) ? c - '0' : tolower(c) - 'a' + 10);
      c = (unsigned char)(a * 16 + b);
    }
    if (c < 32 || c == 127)
      return 0;
    out[used++] = (char)c;
  }
  out[used] = 0;
  while (at < used)
    if (!exr_next(out, used, &at, &cp))
      return 0;
  return 1;
}
int exr_resolve_path(const char *base, const char *href, char out[2048]) {
  char joined[2048], decoded[2048];
  size_t len = 0, i, used = 0, segments[256], depth = 0;
  size_t href_size = strcspn(href, "#");
  const char *slash = strrchr(base, '/');
  if (memchr(href, '?', href_size) || !uri_decode(href, href_size, decoded) || decoded[0] == '/' ||
      strchr(decoded, ':') || strchr(decoded, '\\'))
    return 0;
  if (!decoded[0])
    len = strlen(base);
  else if (slash)
    len = (size_t)(slash - base) + 1;
  if (len + strlen(decoded) >= sizeof(joined))
    return 0;
  memcpy(joined, base, len);
  strcpy(joined + len, decoded);
  for (i = 0; joined[i];) {
    size_t start = i, n;
    while (joined[i] && joined[i] != '/')
      i++;
    n = i - start;
    if (joined[i])
      i++;
    if (!n || (n == 1 && joined[start] == '.'))
      continue;
    if (n == 2 && joined[start] == '.' && joined[start + 1] == '.') {
      if (!depth)
        return 0;
      used = segments[--depth];
      continue;
    }
    if (depth >= 256 || used + n + 1 >= 2048)
      return 0;
    segments[depth++] = used;
    if (used)
      out[used++] = '/';
    memcpy(out + used, joined + start, n);
    used += n;
  }
  out[used] = 0;
  return used > 0;
}
exr_status exr_document_resource(const exr_document *d, size_t resource, void **out, size_t *size,
                                 exr_error *e) {
  archive z = {0};
  void *bytes;
  if (!out || !size)
    return exr_fail(e, EXR_ARGUMENT, "Missing resource output");
  *out = NULL;
  *size = 0;
  if (!d || resource >= d->resource_count)
    return exr_fail(e, EXR_ARGUMENT, "Invalid resource index");
  if (d->resource_data) {
    const exr_resource_data *entry = &d->resource_data[resource];
    if (!entry->bytes)
      return exr_fail(e, EXR_FORMAT, "Resource has no encoded bytes");
    *out = malloc(entry->size ? entry->size : 1);
    if (!*out)
      return exr_fail(e, EXR_MEMORY, "Resource allocation failed");
    if (entry->size)
      memcpy(*out, entry->bytes, entry->size);
    *size = entry->size;
    return EXR_OK;
  }
  if (!d->archive)
    return exr_fail(e, EXR_FORMAT, "Resource has no backing data");
  if (!mz_zip_reader_init_mem(&z.archive, d->archive, d->archive_size, 0))
    return exr_fail(e, EXR_FORMAT, "Invalid resource archive");
  bytes = member(&z, d->resources[resource].path, size, e);
  if (bytes) {
    *out = malloc(*size ? *size : 1);
    if (*out)
      memcpy(*out, bytes, *size);
    else
      z.status = exr_fail(e, EXR_MEMORY, "Resource allocation failed");
    mz_free(bytes);
  }
  mz_zip_reader_end(&z.archive);
  if (!*out)
    *size = 0;
  return z.status;
}
exr_status exr_document_resolve(const exr_document *d, size_t chapter, const char *uri,
                                size_t *resource, size_t *node, exr_error *e) {
  char path[2048], fragment[2048];
  const char *hash;
  size_t i, ch = SIZE_MAX;
  if (!resource || !node)
    return exr_fail(e, EXR_ARGUMENT, "Missing link output");
  *resource = *node = SIZE_MAX;
  if (!d || !uri || chapter >= d->chapter_count)
    return exr_fail(e, EXR_ARGUMENT, "Invalid link arguments");
  hash = strchr(uri, '#');
  if (!exr_resolve_path(d->chapters[chapter].path, uri, path) ||
      (hash && !uri_decode(hash + 1, strlen(hash + 1), fragment)))
    return exr_fail(e, EXR_ARGUMENT, "URI is external or invalid");
  for (i = 0; i < d->resource_count; i++)
    if (!strcmp(path, d->resources[i].path)) {
      *resource = i;
      break;
    }
  for (i = 0; i < d->chapter_count; i++)
    if (!strcmp(d->chapters[i].path, path)) {
      ch = i;
      break;
    }
  if (ch == SIZE_MAX)
    return EXR_OK;
  if (!hash || !fragment[0]) {
    *node = d->chapters[ch].root;
    return EXR_OK;
  }
  for (i = d->chapters[ch].root; i < d->node_count && d->nodes[i].chapter == ch; i++) {
    const char *id = exr_node_attribute(&d->nodes[i], "id");
    if (!id)
      id = exr_node_attribute(&d->nodes[i], "http://www.w3.org/XML/1998/namespace|id");
    if (id && !strcmp(id, fragment)) {
      *node = i;
      break;
    }
  }
  return EXR_OK;
}
static void package_free(package *p) {
  size_t i;
  for (i = 0; i < p->count; i++) {
    free(p->items[i].id);
    free(p->items[i].href);
    free(p->items[i].media_type);
    free(p->items[i].properties);
  }
  for (i = 0; i < p->spine_count; i++)
    free(p->spine[i].id);
  free(p->items);
  free(p->spine);
  free(p->root);
  free(p->title.data);
}
static exr_status archive_open(archive *z, const void *data, size_t n, exr_error *e) {
  if (!mz_zip_reader_init_mem(&z->archive, data, n, 0))
    return exr_fail(e, EXR_FORMAT, "Invalid ZIP container");
  if (mz_zip_reader_get_num_files(&z->archive) > 10000) {
    mz_zip_reader_end(&z->archive);
    return exr_fail(e, EXR_LIMIT, "Too many ZIP members");
  }
  return EXR_OK;
}
static exr_status archive_copy(exr_document *d, const void *data, size_t n, exr_error *e) {
  exr_archive_store *store = calloc(1, sizeof(*store));
  if (!store)
    return exr_fail(e, EXR_MEMORY, "Archive allocation failed");
  store->bytes = malloc(n);
  if (!store->bytes) {
    free(store);
    return exr_fail(e, EXR_MEMORY, "Archive allocation failed");
  }
  memcpy(store->bytes, data, n);
  store->size = n;
  store->refs = 1;
  d->shared_archive = store;
  d->archive = store->bytes;
  d->archive_size = store->size;
  return EXR_OK;
}
static exr_status resource_copy(exr_document *d, const exr_resource *source, exr_error *e) {
  exr_resource *r;
  if (!exr_grow((void **)&d->resources, &d->resource_capacity, d->resource_count + 1,
                sizeof(*d->resources)))
    return exr_fail(e, EXR_MEMORY, "Resource allocation failed");
  r = &d->resources[d->resource_count++];
  memset(r, 0, sizeof(*r));
  r->id = exr_model_copy(d, source->id, strlen(source->id));
  r->path = exr_model_copy(d, source->path, strlen(source->path));
  r->media_type = exr_model_copy(d, source->media_type, strlen(source->media_type));
  r->properties = exr_model_copy(d, source->properties, strlen(source->properties));
  if (!r->id || !r->path || !r->media_type || !r->properties)
    return exr_fail(e, EXR_LIMIT, "Resource metadata exceeds limit");
  return EXR_OK;
}
static exr_status epub_chapter(exr_document *d, size_t resource, int in_spine, int linear,
                               exr_error *e) {
  exr_chapter *chapter;
  if (d->chapter_count >= 10000 ||
      !exr_grow((void **)&d->chapters, &d->chapter_capacity, d->chapter_count + 1,
                sizeof(*d->chapters)))
    return exr_fail(e, EXR_LIMIT, "Chapter limit exceeded");
  chapter = &d->chapters[d->chapter_count++];
  chapter->id = d->resources[resource].id;
  chapter->path = d->resources[resource].path;
  chapter->resource = resource;
  chapter->root = SIZE_MAX;
  chapter->in_spine = in_spine;
  chapter->linear = linear;
  return EXR_OK;
}
/* Build the reading order without extracting XHTML. Missing or damaged chapter
   members are reported only when that chapter is requested. */
static exr_status epub_metadata(exr_document *d, archive *z, exr_error *e) {
  package p = {0};
  void *bytes = NULL;
  size_t size = 0, i, j;
  exr_status result = EXR_FORMAT;
  char path[2048];
  bytes = member(z, "META-INF/container.xml", &size, e);
  if (!bytes)
    goto done;
  if (!package_parse(&p, bytes, size) || !p.root) {
    result = exr_fail(e, EXR_FORMAT, "Invalid EPUB container");
    goto done;
  }
  mz_free(bytes);
  bytes = NULL;
  if (!exr_resolve_path("", p.root, path)) {
    result = exr_fail(e, EXR_FORMAT, "Unsafe EPUB root path");
    goto done;
  }
  free(p.root);
  p.root = exr_copy(path, strlen(path));
  if (!p.root) {
    result = exr_fail(e, EXR_MEMORY, "Package path allocation failed");
    goto done;
  }
  bytes = member(z, p.root, &size, e);
  if (!bytes)
    goto done;
  if (!package_parse(&p, bytes, size) || !p.spine_count) {
    result = exr_fail(e, EXR_FORMAT, "EPUB has no readable spine");
    goto done;
  }
  mz_free(bytes);
  bytes = NULL;
  if (p.title.size) {
    d->title = exr_copy(p.title.data, p.title.size);
    if (!d->title) {
      result = exr_fail(e, EXR_MEMORY, "Title allocation failed");
      goto done;
    }
  }
  for (i = 0; i < p.count; i++) {
    exr_resource r;
    if (!exr_resolve_path(p.root, p.items[i].href, path) || !p.items[i].id[0]) {
      result = exr_fail(e, EXR_FORMAT, "Invalid EPUB manifest resource");
      goto done;
    }
    for (j = 0; j < i; j++)
      if (!strcmp(d->resources[j].id, p.items[i].id) || !strcmp(d->resources[j].path, path)) {
        result = exr_fail(e, EXR_FORMAT, "Duplicate EPUB manifest resource");
        goto done;
      }
    r.id = p.items[i].id;
    r.path = path;
    r.media_type = p.items[i].media_type;
    r.properties = p.items[i].properties;
    result = resource_copy(d, &r, e);
    if (result != EXR_OK)
      goto done;
  }
  for (i = 0; i < p.spine_count; i++) {
    for (j = 0; j < p.count; j++)
      if (!strcmp(p.spine[i].id, p.items[j].id))
        break;
    if (j == p.count ||
        (p.items[j].media_type[0] && strcmp(p.items[j].media_type, "application/xhtml+xml"))) {
      result = exr_fail(e, EXR_FORMAT, "EPUB spine must reference XHTML");
      goto done;
    }
    result = epub_chapter(d, j, 1, p.spine[i].linear, e);
    if (result != EXR_OK)
      goto done;
  }
  /* Auxiliary XHTML remains addressable after the spine, including EPUB 3 nav
     and out-of-spine notes, without entering the main reading text. */
  for (j = 0; j < p.count; j++) {
    if (strcmp(p.items[j].media_type, "application/xhtml+xml"))
      continue;
    for (i = 0; i < d->chapter_count; i++)
      if (d->chapters[i].resource == j)
        break;
    if (i != d->chapter_count)
      continue;
    result = epub_chapter(d, j, 0, 0, e);
    if (result != EXR_OK)
      goto done;
  }
  result = EXR_OK;
done:
  if (bytes)
    mz_free(bytes);
  if (z->status != EXR_OK)
    result = z->status;
  package_free(&p);
  return result;
}
static exr_status epub_parse_chapter(exr_document *d, archive *z, size_t resource,
                                     int in_spine, int linear, exr_error *e) {
  size_t size = 0;
  void *bytes = member(z, d->resources[resource].path, &size, e);
  exr_status result;
  if (!bytes)
    return z->status;
  result = exr_xhtml(d, bytes, size, resource, in_spine, linear, e);
  mz_free(bytes);
  return result;
}
exr_status exr_epub_index(const void *data, size_t n, exr_document **out, exr_error *e) {
  archive z = {0};
  exr_document *d;
  exr_status result;
  if (!out)
    return exr_fail(e, EXR_ARGUMENT, "Missing index output");
  *out = NULL;
  if (e)
    memset(e, 0, sizeof(*e));
  if (!data || !n || n > EXR_MAX_INPUT)
    return exr_fail(e, n > EXR_MAX_INPUT ? EXR_LIMIT : EXR_ARGUMENT, "Invalid EPUB bytes");
  result = archive_open(&z, data, n, e);
  if (result != EXR_OK)
    return result;
  d = calloc(1, sizeof(*d));
  if (!d) {
    mz_zip_reader_end(&z.archive);
    return exr_fail(e, EXR_MEMORY, "Index allocation failed");
  }
  d->format = EXR_EPUB;
  result = epub_metadata(d, &z, e);
  if (result == EXR_OK)
    result = archive_copy(d, data, n, e);
  mz_zip_reader_end(&z.archive);
  if (result != EXR_OK) {
    exr_document_free(d);
    return result;
  }
  *out = d;
  return exr_fail(e, EXR_OK, "");
}
exr_status exr_epub_load(const exr_document *index, size_t part, exr_document **out, exr_error *e) {
  archive z = {0};
  exr_document *d;
  exr_status result;
  size_t i;
  if (!out)
    return exr_fail(e, EXR_ARGUMENT, "Missing chapter output");
  *out = NULL;
  if (e)
    memset(e, 0, sizeof(*e));
  if (!index || index->format != EXR_EPUB || !index->shared_archive ||
      part >= index->chapter_count)
    return exr_fail(e, EXR_ARGUMENT, "Invalid EPUB chapter");
  if (index->shared_archive->refs == SIZE_MAX)
    return exr_fail(e, EXR_LIMIT, "Too many archive references");
  result = archive_open(&z, index->archive, index->archive_size, e);
  if (result != EXR_OK)
    return result;
  d = calloc(1, sizeof(*d));
  if (!d) {
    mz_zip_reader_end(&z.archive);
    return exr_fail(e, EXR_MEMORY, "Chapter allocation failed");
  }
  d->format = EXR_EPUB;
  d->shared_archive = index->shared_archive;
  d->archive = index->archive;
  d->archive_size = index->archive_size;
  d->shared_archive->refs++;
  if (index->title) {
    d->title = exr_copy(index->title, strlen(index->title));
    if (!d->title) {
      result = exr_fail(e, EXR_MEMORY, "Title allocation failed");
      goto done;
    }
  }
  for (i = 0; i < index->resource_count; i++) {
    result = resource_copy(d, &index->resources[i], e);
    if (result != EXR_OK)
      goto done;
  }
  /* A requested auxiliary chapter is an independent reading unit. The index
     retains its original spine/linear flags, while this snapshot can be laid out. */
  result = epub_parse_chapter(d, &z, index->chapters[part].resource, 1, 1, e);
  if (result == EXR_OK)
    result = exr_model_finish(d, e);
done:
  mz_zip_reader_end(&z.archive);
  if (result != EXR_OK) {
    exr_document_free(d);
    return result;
  }
  *out = d;
  return exr_fail(e, EXR_OK, "");
}
static exr_status zip_document(exr_document *d, const void *data, size_t n, exr_error *e) {
  archive z = {0};
  exr_chapter *chapters = NULL;
  size_t count = 0, i;
  exr_status result = archive_open(&z, data, n, e);
  if (result != EXR_OK)
    return result;
  if (d->format == EXR_DOCX) {
    size_t size = 0;
    void *bytes = member(&z, "word/document.xml", &size, e);
    result = bytes ? xml_flow(d, bytes, size, 1, e) : z.status;
    mz_free(bytes);
    goto done;
  }
  result = epub_metadata(d, &z, e);
  if (result != EXR_OK)
    goto done;
  result = archive_copy(d, data, n, e);
  if (result != EXR_OK)
    goto done;
  chapters = d->chapters;
  count = d->chapter_count;
  d->chapters = NULL;
  d->chapter_count = d->chapter_capacity = 0;
  /* Keep one extraction counter for eager reads, including package metadata,
     so the original whole-document expansion limit remains enforced. */
  for (i = 0; i < count; i++) {
    result = epub_parse_chapter(d, &z, chapters[i].resource, chapters[i].in_spine,
                                chapters[i].linear, e);
    if (result != EXR_OK)
      goto done;
  }
done:
  free(chapters);
  mz_zip_reader_end(&z.archive);
  return result;
}
static uint16_t be16(const unsigned char *p) { return (uint16_t)((p[0] << 8) | p[1]); }
static uint32_t be32(const unsigned char *p) {
  return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) | ((uint32_t)p[2] << 8) | p[3];
}
static exr_status mobi(exr_document *d, const void *data, size_t n, exr_error *e) {
  const unsigned char *s = data, *h;
  size_t records, start, stop, i, j, text_records;
  unsigned compression, encoding;
  exr_buffer text = {0}, utf8 = {0};
  exr_status result = EXR_FORMAT;
  if (n < 86 || memcmp(s + 60, "BOOKMOBI", 8))
    return exr_fail(e, EXR_FORMAT, "Not a MOBI container");
  records = be16(s + 76);
  if (records < 2 || records > (n - 78) / 8)
    return exr_fail(e, EXR_FORMAT, "Invalid MOBI record directory");
  start = be32(s + 78);
  stop = be32(s + 86);
  if (start > stop || stop > n || stop - start < 132)
    return exr_fail(e, EXR_FORMAT, "Invalid MOBI header");
  h = s + start;
  compression = be16(h);
  text_records = be16(h + 8);
  if (memcmp(h + 16, "MOBI", 4) || be16(h + 12))
    return exr_fail(e, EXR_FORMAT, "Encrypted or invalid MOBI");
  encoding = be32(h + 28);
  if (be32(h + 36) >= 8)
    return exr_fail(e, EXR_FORMAT, "KF8 reconstruction is not implemented");
  if ((compression != 1 && compression != 2) || !text_records || text_records >= records ||
      (encoding != 65001 && encoding != 1252))
    return exr_fail(e, EXR_FORMAT, "Unsupported MOBI compression or encoding");
  for (i = 1; i <= text_records; i++) {
    start = be32(s + 78 + i * 8);
    stop = i + 1 < records ? be32(s + 78 + (i + 1) * 8) : n;
    if (start > stop || stop > n)
      goto done;
    for (j = start; j < stop; j++) {
      unsigned c = s[j];
      if (compression == 1) {
        if (!exr_append(&text, s + j, 1))
          goto done;
        continue;
      }
      if (c >= 1 && c <= 8) {
        if (c > stop - j - 1 || !exr_append(&text, s + j + 1, c))
          goto done;
        j += c;
      } else if (c <= 0x7f) {
        if (!exr_append(&text, s + j, 1))
          goto done;
      } else if (c >= 0xc0) {
        unsigned char pair[2] = {' ', (unsigned char)(c ^ 0x80)};
        if (!exr_append(&text, pair, 2))
          goto done;
      } else {
        size_t distance, length, k;
        if (++j >= stop)
          goto done;
        c = (c << 8) | s[j];
        distance = (c & 0x3fff) >> 3;
        length = (c & 7) + 3;
        if (!distance || distance > text.size)
          goto done;
        for (k = 0; k < length; k++) {
          char b = text.data[text.size - distance];
          if (!exr_append(&text, &b, 1))
            goto done;
        }
      }
    }
  }
  if (be32(h + 4) > text.size || !be32(h + 4))
    goto done;
  text.size = be32(h + 4);
  text.data[text.size] = 0;
  if (encoding == 1252) {
    for (i = 0; i < text.size; i++)
      if (!exr_codepoint(&utf8, windows1252((unsigned char)text.data[i])))
        goto done;
    result = html(d, utf8.data, utf8.size, e);
  } else
    result = html(d, text.data, text.size, e);
done:
  free(text.data);
  free(utf8.data);
  if (result != EXR_OK)
    exr_fail(e, result, "Invalid or unsupported MOBI text stream");
  return result;
}
typedef struct {
  int skip, uc;
} rtf_state;
static exr_status rtf(exr_document *d, const void *data, size_t n, exr_error *e) {
  const unsigned char *s = data;
  rtf_state states[256] = {{0, 1}};
  size_t depth = 0, i = 0;
  int fallback = 0;
  uint32_t high = 0;
  exr_buffer out = {0};
  exr_status result = EXR_FORMAT;
  static const uint16_t cp1252[32] = {
      0x20ac, 0x81,   0x201a, 0x192,  0x201e, 0x2026, 0x2020, 0x2021, 0x2c6,  0x2030, 0x160,
      0x2039, 0x152,  0x8d,   0x17d,  0x8f,   0x90,   0x2018, 0x2019, 0x201c, 0x201d, 0x2022,
      0x2013, 0x2014, 0x2dc,  0x2122, 0x161,  0x203a, 0x153,  0x9d,   0x17e,  0x178};
  if (n < 5 || memcmp(s, "{\\rtf", 5))
    return exr_fail(e, EXR_FORMAT, "Invalid RTF header");
  while (i < n) {
    unsigned c = s[i++];
    if (c == '{') {
      if (depth + 1 >= 256)
        goto done;
      states[depth + 1] = states[depth];
      depth++;
      continue;
    }
    if (c == '}') {
      if (!depth)
        goto done;
      depth--;
      continue;
    }
    if (c == '\\') {
      char word[40] = {0};
      size_t k = 0;
      long value = 0;
      int negative = 0, has = 0;
      if (i >= n)
        goto done;
      c = s[i++];
      if (c == '*') {
        states[depth].skip = 1;
        continue;
      }
      if (c == '\\' || c == '{' || c == '}') {
        if (fallback) {
          fallback--;
          continue;
        }
        if (!states[depth].skip && !exr_codepoint(&out, c))
          goto done;
        continue;
      }
      if (c == '\'') {
        unsigned a, b;
        if (n - i < 2 || !isxdigit(s[i]) || !isxdigit(s[i + 1]))
          goto done;
        a = (unsigned)(isdigit(s[i]) ? s[i] - '0' : tolower(s[i]) - 'a' + 10);
        b = (unsigned)(isdigit(s[i + 1]) ? s[i + 1] - '0' : tolower(s[i + 1]) - 'a' + 10);
        c = a * 16 + b;
        i += 2;
        if (fallback) {
          fallback--;
          continue;
        }
        if (!states[depth].skip && !exr_codepoint(&out, c >= 128 && c < 160 ? cp1252[c - 128] : c))
          goto done;
        continue;
      }
      if (!isalpha(c))
        continue;
      word[k++] = (char)c;
      while (i < n && isalpha(s[i])) {
        if (k < 39)
          word[k++] = (char)s[i];
        i++;
      }
      if (i < n && s[i] == '-') {
        negative = 1;
        i++;
      }
      while (i < n && isdigit(s[i])) {
        has = 1;
        if (value > 100000000)
          goto done;
        value = value * 10 + s[i++] - '0';
      }
      if (negative)
        value = -value;
      if (i < n && s[i] == ' ')
        i++;
      if (!strcmp(word, "fonttbl") || !strcmp(word, "colortbl") || !strcmp(word, "stylesheet") ||
          !strcmp(word, "info") || !strcmp(word, "pict") || !strcmp(word, "object") ||
          !strcmp(word, "header") || !strcmp(word, "footer")) {
        states[depth].skip = 1;
        continue;
      }
      if (!strcmp(word, "bin")) {
        if (!has || value < 0 || (size_t)value > n - i)
          goto done;
        i += (size_t)value;
        continue;
      }
      if (states[depth].skip)
        continue;
      if (!strcmp(word, "ansicpg") && value != 1252)
        goto done;
      if (!strcmp(word, "uc")) {
        if (!has || value < 0 || value > 16)
          goto done;
        states[depth].uc = (int)value;
      } else if (!strcmp(word, "u")) {
        uint32_t cp;
        if (!has || value < -32768 || value > 65535)
          goto done;
        cp = (uint16_t)value;
        if (cp >= 0xd800 && cp <= 0xdbff) {
          if (high)
            goto done;
          high = cp;
        } else {
          if (cp >= 0xdc00 && cp <= 0xdfff) {
            if (!high)
              goto done;
            cp = 0x10000 + ((high - 0xd800) << 10) + (cp - 0xdc00);
            high = 0;
          } else if (high)
            goto done;
          if (!cp || !exr_codepoint(&out, cp))
            goto done;
        }
        fallback = states[depth].uc;
      } else if (!strcmp(word, "par") || !strcmp(word, "line")) {
        if (!flush(d, &out, 0))
          goto done;
      } else if (!strcmp(word, "tab")) {
        if (!exr_append(&out, " ", 1))
          goto done;
      }
      continue;
    }
    if (c == '\r' || c == '\n' || states[depth].skip)
      continue;
    if (fallback) {
      fallback--;
      continue;
    }
    if (high || !c || !exr_codepoint(&out, c >= 128 && c < 160 ? cp1252[c - 128] : c))
      goto done;
  }
  if (depth || high || !flush(d, &out, 0))
    goto done;
  result = EXR_OK;
done:
  free(out.data);
  return result == EXR_OK ? EXR_OK : exr_fail(e, EXR_FORMAT, "Invalid or unsupported RTF stream");
}
exr_status exr_parse(exr_document *d, const void *data, size_t n, exr_error *e) {
  switch (d->format) {
  case EXR_TXT:
    return plain(d, data, n, e);
  case EXR_HTML:
    return html(d, data, n, e);
  case EXR_FB2:
    return xml_flow(d, data, n, 0, e);
  case EXR_DOCX:
  case EXR_EPUB:
    return zip_document(d, data, n, e);
  case EXR_RTF:
    return rtf(d, data, n, e);
  case EXR_MOBI:
    return mobi(d, data, n, e);
  default:
    return exr_fail(e, EXR_FORMAT, "This format has no native decoder yet");
  }
}
