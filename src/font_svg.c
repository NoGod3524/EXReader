/* SPDX-License-Identifier: MIT */
#include "font_internal.h"
#include "vector_internal.h"
#include <miniz.h>
#include FT_TRUETYPE_TABLES_H

/* OpenType SVG glyph documents. Only the frozen element/attribute subset is
   accepted: shapes with solid fills and strokes, groups, transforms and a
   single viewport mapping. External references, scripts, images, text, paint
   servers, masks and clipping are rejected instead of being ignored. */
#define SVG_MAX_TABLE ((size_t)8*1024*1024)
#define SVG_MAX_DOCUMENT ((size_t)4*1024*1024)
#define SVG_MAX_RECORDS 4096u
#define SVG_MAX_ELEMENTS 2048u
#define SVG_MAX_DEPTH 32u
#define SVG_MAX_ATTRIBUTES 24u
#define SVG_MAX_ATTRIBUTE_BYTES ((size_t)256*1024)
#define SVG_MAX_SEGMENTS 65536u
#define SVG_MAX_REGION 8192u
#define SVG_MAX_PIXELS ((size_t)8*1024*1024)
#define SVG_PI 3.14159265358979323846

typedef struct {
  unsigned start, end;
  uint32_t offset, length;
} svg_record;

struct exr_svg_table {
  FT_ULong size;
  uint32_t list;
  unsigned count;
  svg_record records[];
};

enum {
  SVG_ROOT = 1, SVG_GROUP, SVG_DEFS, SVG_PATH, SVG_RECT, SVG_CIRCLE,
  SVG_ELLIPSE, SVG_LINE, SVG_POLYLINE, SVG_POLYGON
};

typedef struct {
  char *name;
  char *value;
} svg_attribute;

typedef struct svg_node {
  unsigned element;
  struct svg_node *parent, *first, *last, *next;
  svg_attribute *attributes;
  unsigned attribute_count;
  size_t attribute_capacity;
} svg_node;

typedef struct {
  exr_face *face;
  exr_error *error;
  const exr_control *control;
  size_t *work;
  unsigned char *owned;
  const unsigned char *document;
  size_t document_size;
  svg_node *root;
  svg_node **nodes;
  size_t node_count, node_capacity;
  size_t attribute_bytes;
  unsigned segments;
  double view_box[4];
  int has_view_box;
  int has_width, has_height;
  double width, height;
  int preserve_none;
} svg_document;

typedef struct {
  double matrix[6];
  double fill[4], stroke[4], current[3];
  double fill_opacity, stroke_opacity, stroke_width;
  int fill_none, stroke_none, hidden;
  unsigned fill_rule;
  exr_line_cap cap;
  exr_line_join join;
  double miter_limit;
} svg_state;

static int svg_space(int c) {
  return c == ' ' || c == '\t' || c == '\r' || c == '\n' || c == '\f';
}

static int svg_name_start(int c) {
  return (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') || c == '_';
}

static int svg_name_char(int c) {
  return svg_name_start(c) || (c >= '0' && c <= '9') || c == '-' || c == '.' || c == ':';
}

static void svg_matrix_multiply(const double a[6], const double b[6], double out[6]) {
  double r0 = a[0]*b[0] + a[2]*b[1];
  double r1 = a[1]*b[0] + a[3]*b[1];
  double r2 = a[0]*b[2] + a[2]*b[3];
  double r3 = a[1]*b[2] + a[3]*b[3];
  double r4 = a[0]*b[4] + a[2]*b[5] + a[4];
  double r5 = a[1]*b[4] + a[3]*b[5] + a[5];
  out[0] = r0; out[1] = r1; out[2] = r2; out[3] = r3; out[4] = r4; out[5] = r5;
}

static void svg_matrix_point(const double m[6], double x, double y, double *ox, double *oy) {
  *ox = m[0]*x + m[2]*y + m[4];
  *oy = m[1]*x + m[3]*y + m[5];
}

/* ---------- SVG table directory ---------- */

static exr_status svg_directory(exr_face *face, size_t *work, const exr_control *control, exr_error *error) {
  FT_ULong size = 0;
  (void)control;
  unsigned char header[12], *records = NULL;
  struct exr_svg_table *table = NULL;
  unsigned count, i;
  uint32_t list;
  if (face->svg_checked) return EXR_OK;
  if (FT_Load_Sfnt_Table(face->face, FT_MAKE_TAG('S','V','G',' '), 0, NULL, &size) || !size) {
    face->svg_checked = 1;
    return EXR_OK;
  }
  if (size > SVG_MAX_TABLE) return exr_fail(error, EXR_LIMIT, "SVG table exceeds 8 MiB");
  if (!exr_vector_work(work, (size_t)size)) return exr_fail(error, EXR_LIMIT, "SVG table read exceeds budget");
  {
    FT_ULong length = sizeof(header);
    if (FT_Load_Sfnt_Table(face->face, FT_MAKE_TAG('S','V','G',' '), 0, header, &length) || length < 12)
      return exr_fail(error, EXR_FONT, "Cannot read SVG table header");
  }
  if ((header[0] | header[1]) != 0) return exr_fail(error, EXR_FONT, "Unsupported SVG table version");
  list = (uint32_t)header[2] << 24 | (uint32_t)header[3] << 16 | (uint32_t)header[4] << 8 | header[5];
  if (header[6] | header[7] | header[8] | header[9]) return exr_fail(error, EXR_FONT, "SVG table reserved field is nonzero");
  if (list > size - 2) return exr_fail(error, EXR_FONT, "Invalid SVG document list offset");
  {
    FT_ULong length = 2;
    if (FT_Load_Sfnt_Table(face->face, FT_MAKE_TAG('S','V','G',' '), (FT_Long)list, header, &length) || length < 2)
      return exr_fail(error, EXR_FONT, "Cannot read SVG document list");
  }
  count = (unsigned)header[0] << 8 | header[1];
  if (!count || count > SVG_MAX_RECORDS)
    return exr_fail(error, count ? EXR_LIMIT : EXR_FONT, count ? "SVG document list exceeds 4096 records" : "SVG table has no documents");
  if ((uint64_t)count*12 > size - list - 2) return exr_fail(error, EXR_FONT, "Truncated SVG document list");
  records = calloc(count, 12);
  if (!records) return exr_fail(error, EXR_MEMORY, "SVG record allocation failed");
  {
    FT_ULong length = (FT_ULong)count*12;
    if (FT_Load_Sfnt_Table(face->face, FT_MAKE_TAG('S','V','G',' '), (FT_Long)(list + 2), records, &length) ||
        length < (FT_ULong)count*12) {
      free(records);
      return exr_fail(error, EXR_FONT, "Cannot read SVG document records");
    }
  }
  table = calloc(1, sizeof(*table) + count*sizeof(*table->records));
  if (!table) { free(records); return exr_fail(error, EXR_MEMORY, "SVG directory allocation failed"); }
  table->size = size;
  table->list = list;
  table->count = count;
  for (i = 0; i < count; i++) {
    const unsigned char *r = records + (size_t)i*12;
    svg_record *record = &table->records[i];
    record->start = (unsigned)r[0] << 8 | r[1];
    record->end = (unsigned)r[2] << 8 | r[3];
    record->offset = (uint32_t)r[4] << 24 | (uint32_t)r[5] << 16 | (uint32_t)r[6] << 8 | r[7];
    record->length = (uint32_t)r[8] << 24 | (uint32_t)r[9] << 16 | (uint32_t)r[10] << 8 | r[11];
    if (record->start > record->end || record->end >= (unsigned)face->face->num_glyphs ||
        (uint64_t)list + record->offset > size || record->length > size - list - record->offset ||
        record->length > SVG_MAX_DOCUMENT ||
        (i && record->start <= table->records[i-1].end)) {
      free(records);
      free(table);
      return exr_fail(error, EXR_FONT, "Invalid SVG document coverage record");
    }
  }
  free(records);
  face->svg = table;
  face->svg_checked = 1;
  return EXR_OK;
}

static svg_record *svg_lookup(exr_face *face, uint32_t glyph) {
  unsigned lo = 0, hi;
  if (!face->svg) return NULL;
  hi = face->svg->count;
  while (lo < hi) {
    unsigned mid = lo + (hi - lo)/2;
    svg_record *record = &face->svg->records[mid];
    if (glyph < record->start) hi = mid;
    else if (glyph > record->end) lo = mid + 1;
    else return record;
  }
  return NULL;
}

/* ---------- XML subset ---------- */

static int svg_element_for(const char *name, size_t length) {
  static const struct { const char *name; unsigned element; } names[] = {
    {"svg", SVG_ROOT}, {"g", SVG_GROUP}, {"defs", SVG_DEFS}, {"path", SVG_PATH},
    {"rect", SVG_RECT}, {"circle", SVG_CIRCLE}, {"ellipse", SVG_ELLIPSE},
    {"line", SVG_LINE}, {"polyline", SVG_POLYLINE}, {"polygon", SVG_POLYGON}
  };
  size_t i;
  for (i = 0; i < sizeof(names)/sizeof(names[0]); i++)
    if (strlen(names[i].name) == length && !memcmp(names[i].name, name, length)) return (int)names[i].element;
  return 0;
}

static int svg_hex(int c) {
  if (c >= '0' && c <= '9') return c - '0';
  if (c >= 'a' && c <= 'f') return c - 'a' + 10;
  if (c >= 'A' && c <= 'F') return c - 'A' + 10;
  return -1;
}

static int svg_utf8_next(const unsigned char **pp, const unsigned char *end, uint32_t *out) {
  const unsigned char *p = *pp;
  uint32_t cp;
  unsigned extra, i;
  if (p >= end) return 0;
  if (*p < 0x80) { *out = *p; *pp = p + 1; return 1; }
  if ((*p & 0xe0) == 0xc0) { cp = *p & 0x1f; extra = 1; }
  else if ((*p & 0xf0) == 0xe0) { cp = *p & 0x0f; extra = 2; }
  else if ((*p & 0xf8) == 0xf0) { cp = *p & 0x07; extra = 3; }
  else return 0;
  if ((size_t)(end - p) <= extra) return 0;
  for (i = 1; i <= extra; i++) {
    if ((p[i] & 0xc0) != 0x80) return 0;
    cp = (cp << 6) | (p[i] & 0x3f);
  }
  if ((extra == 1 && cp < 0x80) || (extra == 2 && cp < 0x800) || (extra == 3 && cp < 0x10000) ||
      cp > 0x10ffff || (cp >= 0xd800 && cp <= 0xdfff)) return 0;
  *out = cp;
  *pp = p + 1 + extra;
  return 1;
}

static exr_status svg_decode_value(svg_document *doc, const unsigned char *p, const unsigned char *end,
                                   char **out) {
  char *value;
  size_t length = 0;
  if ((size_t)(end - p) > 512) return exr_fail(doc->error, EXR_LIMIT, "SVG attribute value exceeds 512 bytes");
  value = malloc((size_t)(end - p) + 1);
  if (!value) return exr_fail(doc->error, EXR_MEMORY, "SVG attribute allocation failed");
  while (p < end) {
    uint32_t cp;
    if (*p == '&') {
      const unsigned char *semi = p + 1;
      while (semi < end && *semi != ';' && semi - p <= 12) semi++;
      if (semi >= end || *semi != ';') { free(value); return exr_fail(doc->error, EXR_FORMAT, "Unterminated SVG entity"); }
      if (semi - p == 4 && !memcmp(p + 1, "amp", 3)) cp = '&';
      else if (semi - p == 3 && !memcmp(p + 1, "lt", 2)) cp = '<';
      else if (semi - p == 3 && !memcmp(p + 1, "gt", 2)) cp = '>';
      else if (semi - p == 5 && !memcmp(p + 1, "quot", 4)) cp = '"';
      else if (semi - p == 5 && !memcmp(p + 1, "apos", 4)) cp = '\'';
      else if (semi - p > 2 && p[1] == '#') {
        uint32_t base = 10, number = 0; const unsigned char *q = p + 2;
        int digits = 0;
        if (q < semi && (*q == 'x' || *q == 'X')) { base = 16; q++; }
        for (; q < semi; q++) {
          int digit = base == 16 ? svg_hex(*q) : (*q >= '0' && *q <= '9' ? *q - '0' : -1);
          if (digit < 0 || digit >= (int)base || number > 0x10ffff/base) { free(value); return exr_fail(doc->error, EXR_FORMAT, "Invalid SVG character reference"); }
          number = number*base + (uint32_t)digit;
          digits = 1;
        }
        if (!digits || number > 0x10ffff || (number >= 0xd800 && number <= 0xdfff)) {
          free(value);
          return exr_fail(doc->error, EXR_FORMAT, "Invalid SVG character reference");
        }
        cp = number;
      } else { free(value); return exr_fail(doc->error, EXR_UNSUPPORTED, "SVG entity is not supported"); }
      p = semi + 1;
    } else {
      if (*p == '<') { free(value); return exr_fail(doc->error, EXR_FORMAT, "Unescaped '<' in SVG attribute"); }
      if (!svg_utf8_next(&p, end, &cp)) { free(value); return exr_fail(doc->error, EXR_FORMAT, "Invalid UTF-8 in SVG document"); }
    }
    if (!cp) { free(value); return exr_fail(doc->error, EXR_FORMAT, "NUL in SVG attribute"); }
    if (cp < 0x80) value[length++] = (char)cp;
    else if (cp < 0x800) { value[length++] = (char)(0xc0 | cp >> 6); value[length++] = (char)(0x80 | (cp & 0x3f)); }
    else if (cp < 0x10000) {
      value[length++] = (char)(0xe0 | cp >> 12); value[length++] = (char)(0x80 | ((cp >> 6) & 0x3f));
      value[length++] = (char)(0x80 | (cp & 0x3f));
    } else {
      value[length++] = (char)(0xf0 | cp >> 18); value[length++] = (char)(0x80 | ((cp >> 12) & 0x3f));
      value[length++] = (char)(0x80 | ((cp >> 6) & 0x3f)); value[length++] = (char)(0x80 | (cp & 0x3f));
    }
  }
  value[length] = 0;
  *out = value;
  return EXR_OK;
}

static svg_node *svg_node_new(svg_document *doc, unsigned element, svg_node *parent) {
  svg_node *node;
  if (doc->node_count >= SVG_MAX_ELEMENTS) return NULL;
  if (!exr_grow((void **)&doc->nodes, &doc->node_capacity, doc->node_count + 1, sizeof(*doc->nodes))) return NULL;
  node = calloc(1, sizeof(*node));
  if (!node) return NULL;
  node->element = element;
  node->parent = parent;
  doc->nodes[doc->node_count++] = node;
  return node;
}

static exr_status svg_parse(svg_document *doc) {
  const unsigned char *p = doc->document, *end = doc->document + doc->document_size;
  svg_node *stack[SVG_MAX_DEPTH];
  unsigned depth = 0;
  int root_seen = 0, root_closed = 0, declaration = 0;
  if (doc->document_size >= 3 && p[0] == 0xef && p[1] == 0xbb && p[2] == 0xbf) p += 3;
  while (p < end) {
    if (svg_space(*p)) { p++; continue; }
    if (*p != '<') {
      if (!root_seen || root_closed) return exr_fail(doc->error, EXR_FORMAT, "SVG text outside the root element");
      while (p < end && *p != '<') {
        if (*p == '&') return exr_fail(doc->error, EXR_UNSUPPORTED, "SVG character data is not supported");
        p++;
      }
      continue;
    }
    if (end - p >= 4 && !memcmp(p, "<!--", 4)) {
      const unsigned char *close = p + 4;
      while (close + 2 < end && memcmp(close, "-->", 3)) close++;
      if (close + 2 >= end) return exr_fail(doc->error, EXR_FORMAT, "Unterminated SVG comment");
      p = close + 3;
      continue;
    }
    if (end - p >= 2 && p[1] == '?') {
      const unsigned char *close = p + 2;
      if (declaration || root_seen) return exr_fail(doc->error, EXR_UNSUPPORTED, "SVG processing instruction is not supported");
      while (close + 1 < end && !(close[0] == '?' && close[1] == '>')) close++;
      if (close + 1 >= end) return exr_fail(doc->error, EXR_FORMAT, "Unterminated SVG XML declaration");
      declaration = 1;
      p = close + 2;
      continue;
    }
    if (end - p >= 2 && p[1] == '!') return exr_fail(doc->error, EXR_UNSUPPORTED, "SVG DOCTYPE or CDATA is not supported");
    if (end - p >= 2 && p[1] == '/') {
      const unsigned char *q = p + 2, *name;
      size_t length;
      while (q < end && svg_space(*q)) q++;
      name = q;
      while (q < end && svg_name_char(*q)) q++;
      length = (size_t)(q - name);
      while (q < end && svg_space(*q)) q++;
      if (q >= end || *q != '>') return exr_fail(doc->error, EXR_FORMAT, "Invalid SVG end tag");
      if (!depth) return exr_fail(doc->error, EXR_FORMAT, "SVG end tag without a start tag");
      {
        static const struct { unsigned element; const char *name; } names[] = {
          {SVG_ROOT, "svg"}, {SVG_GROUP, "g"}, {SVG_DEFS, "defs"}, {SVG_PATH, "path"},
          {SVG_RECT, "rect"}, {SVG_CIRCLE, "circle"}, {SVG_ELLIPSE, "ellipse"},
          {SVG_LINE, "line"}, {SVG_POLYLINE, "polyline"}, {SVG_POLYGON, "polygon"}
        };
        const char *open = NULL;
        unsigned i;
        for (i = 0; i < sizeof(names)/sizeof(names[0]); i++)
          if (names[i].element == stack[depth-1]->element) open = names[i].name;
        if (!open || strlen(open) != length || memcmp(open, name, length))
          return exr_fail(doc->error, EXR_FORMAT, "SVG end tag mismatch");
      }
      depth--;
      if (!depth) root_closed = 1;
      p = q + 1;
      continue;
    }
    {
      const unsigned char *q = p + 1, *name;
      size_t name_length;
      int self_closing = 0, element;
      svg_node *node, *parent;
      if (q >= end || !svg_name_start(*q)) return exr_fail(doc->error, EXR_FORMAT, "Invalid SVG element name");
      name = q;
      while (q < end && svg_name_char(*q)) q++;
      name_length = (size_t)(q - name);
      if (name_length > 64) return exr_fail(doc->error, EXR_LIMIT, "SVG element name exceeds 64 bytes");
      if (memchr(name, ':', name_length)) return exr_fail(doc->error, EXR_UNSUPPORTED, "Namespaced SVG elements are not supported");
      element = svg_element_for((const char *)name, name_length);
      if (!element) return exr_fail(doc->error, EXR_UNSUPPORTED, "SVG element is not supported");
      if (!depth && (element != SVG_ROOT || root_seen)) return exr_fail(doc->error, EXR_FORMAT, "Invalid SVG root element");
      if (depth >= SVG_MAX_DEPTH) return exr_fail(doc->error, EXR_LIMIT, "SVG nesting exceeds 32 levels");
      parent = depth ? stack[depth-1] : NULL;
      if (doc->node_count >= SVG_MAX_ELEMENTS) return exr_fail(doc->error, EXR_LIMIT, "SVG element count exceeds 2048");
      node = svg_node_new(doc, (unsigned)element, parent);
      if (!node) return exr_fail(doc->error, EXR_MEMORY, "SVG element allocation failed");
      for (;;) {
        const unsigned char *aname;
        size_t aname_length;
        char quote;
        while (q < end && svg_space(*q)) q++;
        if (q >= end) return exr_fail(doc->error, EXR_FORMAT, "Unterminated SVG start tag");
        if (*q == '>') { q++; break; }
        if (*q == '/' && q + 1 < end && q[1] == '>') { self_closing = 1; q += 2; break; }
        if (!svg_name_start(*q)) return exr_fail(doc->error, EXR_FORMAT, "Invalid SVG attribute name");
        aname = q;
        while (q < end && svg_name_char(*q)) q++;
        aname_length = (size_t)(q - aname);
        if (!aname_length || aname_length > 64) return exr_fail(doc->error, EXR_LIMIT, "Invalid SVG attribute name length");
        while (q < end && svg_space(*q)) q++;
        if (q >= end || *q != '=') return exr_fail(doc->error, EXR_FORMAT, "SVG attribute lacks a value");
        q++;
        while (q < end && svg_space(*q)) q++;
        if (q >= end || (*q != '"' && *q != '\'')) return exr_fail(doc->error, EXR_FORMAT, "SVG attribute value is not quoted");
        quote = (char)*q++;
        {
          const unsigned char *value_start = q;
          while (q < end && *q != quote) q++;
          if (q >= end) return exr_fail(doc->error, EXR_FORMAT, "Unterminated SVG attribute value");
          if (node->attribute_count == SVG_MAX_ATTRIBUTES) return exr_fail(doc->error, EXR_LIMIT, "SVG element exceeds 24 attributes");
          if (!exr_grow((void **)&node->attributes, &node->attribute_capacity, node->attribute_count + 1, sizeof(*node->attributes)))
            return exr_fail(doc->error, EXR_MEMORY, "SVG attribute list allocation failed");
          {
            svg_attribute *attribute = &node->attributes[node->attribute_count];
            exr_status status;
            memset(attribute, 0, sizeof(*attribute));
            node->attribute_count++;
            attribute->name = malloc(aname_length + 1);
            if (!attribute->name) return exr_fail(doc->error, EXR_MEMORY, "SVG attribute allocation failed");
            memcpy(attribute->name, aname, aname_length);
            attribute->name[aname_length] = 0;
            status = svg_decode_value(doc, value_start, q, &attribute->value);
            if (status != EXR_OK) return status;
            doc->attribute_bytes += aname_length + strlen(attribute->value) + 2;
            if (doc->attribute_bytes > SVG_MAX_ATTRIBUTE_BYTES)
              return exr_fail(doc->error, EXR_LIMIT, "SVG attribute data exceeds 256 KiB");
          }
          q++;
        }
      }
      if (parent) {
        if (!parent->first) parent->first = node;
        else parent->last->next = node;
        parent->last = node;
      }
      if (!root_seen) {
        doc->root = node;
        root_seen = 1;
      }
      if (!self_closing) stack[depth++] = node;
      else if (!depth) root_closed = 1;
      p = q;
      continue;
    }
  }
  if (!root_seen) return exr_fail(doc->error, EXR_FORMAT, "SVG document has no root");
  if (depth) return exr_fail(doc->error, EXR_FORMAT, "Unterminated SVG element");
  return EXR_OK;
}

static void svg_document_free(svg_document *doc) {
  size_t i, j;
  for (i = 0; i < doc->node_count; i++) {
    svg_node *node = doc->nodes[i];
    for (j = 0; j < node->attribute_count; j++) {
      free(node->attributes[j].name);
      free(node->attributes[j].value);
    }
    free(node->attributes);
    free(node);
  }
  free(doc->nodes);
  free(doc->owned);
  memset(doc, 0, sizeof(*doc));
}

static const char *svg_attr(const svg_node *node, const char *name) {
  unsigned i;
  for (i = 0; i < node->attribute_count; i++)
    if (!strcmp(node->attributes[i].name, name)) return node->attributes[i].value;
  return NULL;
}

/* ---------- numbers, colours and transforms ---------- */

static int svg_number(const unsigned char **pp, const unsigned char *end, double *out) {
  const unsigned char *p = *pp, *start;
  int digits = 0;
  while (p < end && svg_space(*p)) p++;
  start = p;
  if (p < end && (*p == '+' || *p == '-')) p++;
  while (p < end && *p >= '0' && *p <= '9') { p++; digits++; }
  if (p < end && *p == '.') {
    p++;
    while (p < end && *p >= '0' && *p <= '9') { p++; digits++; }
  }
  if (!digits) return 0;
  if (p < end && (*p == 'e' || *p == 'E')) {
    const unsigned char *q = p + 1;
    int exponent = 0;
    if (q < end && (*q == '+' || *q == '-')) q++;
    while (q < end && *q >= '0' && *q <= '9') { q++; exponent++; }
    if (!exponent) return 0;
    p = q;
  }
  {
    char buffer[64];
    size_t length = (size_t)(p - start);
    if (length >= sizeof(buffer)) return 0;
    memcpy(buffer, start, length);
    buffer[length] = 0;
    *out = strtod(buffer, NULL);
    if (!isfinite(*out)) return 0;
  }
  *pp = p;
  return 1;
}

static int svg_number_list(const unsigned char *p, const unsigned char *end, double *values, unsigned count) {
  unsigned i;
  for (i = 0; i < count; i++) {
    if (!svg_number(&p, end, &values[i])) return 0;
    if (i + 1 < count) {
      while (p < end && svg_space(*p)) p++;
      if (p < end && *p == ',') p++;
    }
  }
  while (p < end && svg_space(*p)) p++;
  return p == end;
}

static int svg_numbers_text(const char *text, double *values, unsigned count) {
  return svg_number_list((const unsigned char *)text, (const unsigned char *)text + strlen(text), values, count);
}

static int svg_named_color(const char *name, double rgba[4]) {
  static const struct { const char *name; double r, g, b; } colors[] = {
    {"black", 0, 0, 0}, {"white", 1, 1, 1}, {"red", 1, 0, 0}, {"green", 0, 0.5, 0},
    {"lime", 0, 1, 0}, {"blue", 0, 0, 1}, {"yellow", 1, 1, 0}, {"magenta", 1, 0, 1},
    {"fuchsia", 1, 0, 1}, {"cyan", 0, 1, 1}, {"aqua", 0, 1, 1}, {"gray", 0.5, 0.5, 0.5},
    {"grey", 0.5, 0.5, 0.5}, {"silver", 0.75, 0.75, 0.75}, {"purple", 0.5, 0, 0.5},
    {"orange", 1, 0.647, 0}, {"navy", 0, 0, 0.5}, {"teal", 0, 0.5, 0.5}
  };
  size_t i;
  for (i = 0; i < sizeof(colors)/sizeof(colors[0]); i++)
    if (!strcmp(name, colors[i].name)) {
      rgba[0] = colors[i].r; rgba[1] = colors[i].g; rgba[2] = colors[i].b; rgba[3] = 1;
      return 1;
    }
  return 0;
}

/* 0 means "none", 1 a solid colour and -1 an unsupported paint. */
static int svg_color(const char *value, const double current[3], double rgba[4]) {
  if (!value) return -1;
  if (!strcmp(value, "none")) return 0;
  if (!strcmp(value, "currentColor")) {
    rgba[0] = current[0]; rgba[1] = current[1]; rgba[2] = current[2]; rgba[3] = 1;
    return 1;
  }
  if (value[0] == '#') {
    size_t length = strlen(value + 1), i;
    unsigned digits[6];
    if (length != 3 && length != 6) return -1;
    for (i = 0; i < length; i++) {
      int digit = svg_hex((unsigned char)value[1 + i]);
      if (digit < 0) return -1;
      digits[i] = (unsigned)digit;
    }
    if (length == 3) {
      rgba[0] = digits[0]*17/255.0; rgba[1] = digits[1]*17/255.0; rgba[2] = digits[2]*17/255.0;
    } else {
      rgba[0] = (digits[0]*16 + digits[1])/255.0;
      rgba[1] = (digits[2]*16 + digits[3])/255.0;
      rgba[2] = (digits[4]*16 + digits[5])/255.0;
    }
    rgba[3] = 1;
    return 1;
  }
  if (!strncmp(value, "rgb(", 4) && value[strlen(value)-1] == ')') {
    char buffer[128];
    char *comma1, *comma2;
    size_t length = strlen(value);
    if (length >= sizeof(buffer) || length < 6) return -1;
    memcpy(buffer, value + 4, length - 5);
    buffer[length - 5] = 0;
    comma1 = strchr(buffer, ',');
    if (!comma1) return -1;
    comma2 = strchr(comma1 + 1, ',');
    if (!comma2 || strchr(comma2 + 1, ',')) return -1;
    *comma1 = *comma2 = 0;
    for (int i = 0; i < 3; i++) {
      const char *component = i == 0 ? buffer : i == 1 ? comma1 + 1 : comma2 + 1;
      char *stop = NULL;
      double number = strtod(component, &stop);
      if (stop == component) return -1;
      if (*stop == '%') { number = number*255.0/100.0; stop++; }
      while (*stop && svg_space((unsigned char)*stop)) stop++;
      if (*stop || !isfinite(number) || number < 0 || number > 255) return -1;
      rgba[i] = number/255.0;
    }
    rgba[3] = 1;
    return 1;
  }
  if (svg_named_color(value, rgba)) return 1;
  return -1;
}

static int svg_transform_number(const unsigned char **pp, const unsigned char *end, double *out) {
  if (!svg_number(pp, end, out)) return 0;
  while (*pp < end && (svg_space(**pp) || **pp == ',')) (*pp)++;
  return 1;
}

static int svg_transform(const char *value, double matrix[6]) {
  const unsigned char *p = (const unsigned char *)value, *end = p + strlen(value);
  double result[6] = {1, 0, 0, 1, 0, 0};
  while (p < end) {
    const unsigned char *name;
    size_t length;
    double a[6], t[6], next[6];
    unsigned count = 0;
    while (p < end && (svg_space(*p) || *p == ',')) p++;
    if (p >= end) break;
    name = p;
    while (p < end && svg_name_char(*p)) p++;
    length = (size_t)(p - name);
    while (p < end && svg_space(*p)) p++;
    if (p >= end || *p != '(') return 0;
    p++;
    if (length == 6 && !memcmp(name, "matrix", 6)) {
      if (!svg_transform_number(&p, end, &a[0]) || !svg_transform_number(&p, end, &a[1]) ||
          !svg_transform_number(&p, end, &a[2]) || !svg_transform_number(&p, end, &a[3]) ||
          !svg_transform_number(&p, end, &a[4]) || !svg_transform_number(&p, end, &a[5])) return 0;
      t[0]=a[0]; t[1]=a[1]; t[2]=a[2]; t[3]=a[3]; t[4]=a[4]; t[5]=a[5];
    } else if (length == 9 && !memcmp(name, "translate", 9)) {
      if (!svg_transform_number(&p, end, &a[0])) return 0;
      a[1] = 0;
      if (!svg_number(&p, end, &a[1])) a[1] = 0;
      while (p < end && (svg_space(*p) || *p == ',')) p++;
      t[0]=1; t[1]=0; t[2]=0; t[3]=1; t[4]=a[0]; t[5]=a[1];
    } else if (length == 5 && !memcmp(name, "scale", 5)) {
      if (!svg_transform_number(&p, end, &a[0])) return 0;
      a[1] = a[0];
      if (!svg_number(&p, end, &a[1])) a[1] = a[0];
      while (p < end && (svg_space(*p) || *p == ',')) p++;
      t[0]=a[0]; t[1]=0; t[2]=0; t[3]=a[1]; t[4]=0; t[5]=0;
    } else if (length == 6 && !memcmp(name, "rotate", 6)) {
      double angle, cx = 0, cy = 0, cs, sn;
      if (!svg_transform_number(&p, end, &angle)) return 0;
      if (svg_number(&p, end, &cx)) {
        if (!svg_transform_number(&p, end, &cy)) return 0;
        count = 1;
      }
      (void)count;
      angle = angle*SVG_PI/180.0; cs = cos(angle); sn = sin(angle);
      t[0]=cs; t[1]=sn; t[2]=-sn; t[3]=cs;
      t[4]=cx - cs*cx + sn*cy; t[5]=cy - sn*cx - cs*cy;
    } else if (length == 6 && !memcmp(name, "skewX", 5)) {
      double angle;
      if (!svg_transform_number(&p, end, &angle)) return 0;
      t[0]=1; t[1]=0; t[2]=tan(angle*SVG_PI/180.0); t[3]=1; t[4]=0; t[5]=0;
      if (!isfinite(t[2]) || fabs(t[2]) > 1e6) return 0;
    } else if (length == 6 && !memcmp(name, "skewY", 5)) {
      double angle;
      if (!svg_transform_number(&p, end, &angle)) return 0;
      t[0]=1; t[1]=tan(angle*SVG_PI/180.0); t[2]=0; t[3]=1; t[4]=0; t[5]=0;
      if (!isfinite(t[1]) || fabs(t[1]) > 1e6) return 0;
    } else return 0;
    while (p < end && svg_space(*p)) p++;
    if (p >= end || *p != ')') return 0;
    p++;
    svg_matrix_multiply(result, t, next);
    memcpy(result, next, sizeof(result));
  }
  memcpy(matrix, result, sizeof(result));
  return 1;
}

/* ---------- path construction ---------- */

typedef struct {
  svg_document *doc;
  exr_path_segment *segments;
  size_t count, capacity;
  int status;
} svg_path;

static int svg_path_segment(svg_path *path, exr_path_verb verb, double x, double y,
                            double x2, double y2, double x3, double y3) {
  exr_path_segment segment;
  if (path->status) return 0;
  if (path->count >= SVG_MAX_SEGMENTS || path->doc->segments >= SVG_MAX_SEGMENTS) {
    path->status = exr_fail(path->doc->error, EXR_LIMIT, "SVG path exceeds 65536 segments");
    return 0;
  }
  if (!isfinite(x) || !isfinite(y) || !isfinite(x2) || !isfinite(y2) || !isfinite(x3) || !isfinite(y3) ||
      fabs(x) > 1e7 || fabs(y) > 1e7 || fabs(x2) > 1e7 || fabs(y2) > 1e7 ||
      fabs(x3) > 1e7 || fabs(y3) > 1e7) {
    path->status = exr_fail(path->doc->error, EXR_LIMIT, "SVG path coordinate exceeds limits");
    return 0;
  }
  if (!exr_grow((void **)&path->segments, &path->capacity, path->count + 1, sizeof(*path->segments))) {
    path->status = exr_fail(path->doc->error, EXR_MEMORY, "SVG path allocation failed");
    return 0;
  }
  memset(&segment, 0, sizeof(segment));
  segment.verb = verb;
  if (verb == EXR_PATH_QUAD) {
    segment.points[0] = (exr_path_point){x2, y2};
    segment.points[1] = (exr_path_point){x, y};
  } else if (verb == EXR_PATH_CUBIC) {
    segment.points[0] = (exr_path_point){x2, y2};
    segment.points[1] = (exr_path_point){x3, y3};
    segment.points[2] = (exr_path_point){x, y};
  } else {
    segment.points[0] = (exr_path_point){x, y};
  }
  path->segments[path->count++] = segment;
  path->doc->segments++;
  if (!exr_vector_work(path->doc->work, 1)) {
    path->status = exr_fail(path->doc->error, EXR_LIMIT, "SVG path work exceeds budget");
    return 0;
  }
  if (!(path->count & 255)) {
    exr_status status = exr_control_cancel(path->doc->control, path->doc->error);
    if (status != EXR_OK) { path->status = status; return 0; }
  }
  return 1;
}

static int svg_flag(const unsigned char **pp, const unsigned char *end, int *out) {
  const unsigned char *p = *pp;
  while (p < end && (svg_space(*p) || *p == ',')) p++;
  if (p >= end || (*p != '0' && *p != '1')) return 0;
  *out = *p - '0';
  *pp = p + 1;
  return 1;
}

static int svg_arc(svg_path *path, double x1, double y1, double rx, double ry, double angle,
                   int large, int sweep, double x2, double y2) {
  double cs = cos(angle*SVG_PI/180.0), sn = sin(angle*SVG_PI/180.0);
  double dx = (x1 - x2)/2, dy = (y1 - y2)/2, x1p, y1p, lambda, coefficient, cxp, cyp, cx, cy;
  double ux, uy, vx, vy, theta, delta, step;
  int count, i;
  rx = fabs(rx); ry = fabs(ry);
  if (!rx || !ry || (x1 == x2 && y1 == y2)) return svg_path_segment(path, EXR_PATH_LINE, x2, y2, 0, 0, 0, 0);
  x1p = cs*dx + sn*dy; y1p = -sn*dx + cs*dy;
  lambda = (x1p*x1p)/(rx*rx) + (y1p*y1p)/(ry*ry);
  if (lambda > 1) { rx *= sqrt(lambda); ry *= sqrt(lambda); }
  coefficient = (rx*rx*ry*ry - rx*rx*y1p*y1p - ry*ry*x1p*x1p) /
                (rx*rx*y1p*y1p + ry*ry*x1p*x1p);
  if (!(coefficient > 0)) coefficient = 0;
  coefficient = sqrt(coefficient);
  if (large == sweep) coefficient = -coefficient;
  cxp = coefficient*rx*y1p/ry;
  cyp = -coefficient*ry*x1p/rx;
  cx = cs*cxp - sn*cyp + (x1 + x2)/2;
  cy = sn*cxp + cs*cyp + (y1 + y2)/2;
  ux = (x1p - cxp)/rx; uy = (y1p - cyp)/ry;
  vx = (-x1p - cxp)/rx; vy = (-y1p - cyp)/ry;
  theta = atan2(uy, ux);
  delta = atan2(ux*vy - uy*vx, ux*vx + uy*vy);
  if (!sweep && delta > 0) delta -= 2*SVG_PI;
  if (sweep && delta < 0) delta += 2*SVG_PI;
  count = (int)ceil(fabs(delta)/(SVG_PI/2));
  if (count < 1) count = 1;
  if (count > 4) count = 4;
  step = delta/count;
  for (i = 0; i < count; i++) {
    double a1 = theta + i*step, a2 = a1 + step;
    double alpha = sin(step)*(sqrt(4 + 3*tan(step/2)*tan(step/2)) - 1)/3;
    double p1x = cos(a1), p1y = sin(a1), p2x = cos(a2), p2y = sin(a2);
    double q1x = p1x - alpha*p1y, q1y = p1y + alpha*p1x;
    double q2x = p2x + alpha*p2y, q2y = p2y - alpha*p2x;
    double c1x = cx + cs*rx*q1x - sn*ry*q1y, c1y = cy + sn*rx*q1x + cs*ry*q1y;
    double c2x = cx + cs*rx*q2x - sn*ry*q2y, c2y = cy + sn*rx*q2x + cs*ry*q2y;
    double ex = cx + cs*rx*p2x - sn*ry*p2y, ey = cy + sn*rx*p2x + cs*ry*p2y;
    if (i + 1 == count) { ex = x2; ey = y2; }
    if (!svg_path_segment(path, EXR_PATH_CUBIC, ex, ey, c1x, c1y, c2x, c2y)) return 0;
  }
  return 1;
}

static int svg_path_data(svg_path *path, const char *data) {
  const unsigned char *p = (const unsigned char *)data, *end = p + strlen(data);
  double cx = 0, cy = 0, sx = 0, sy = 0, last_cx = 0, last_cy = 0;
  unsigned char command = 0;
  int started = 0;
  while (p < end) {
    unsigned char c;
    while (p < end && (svg_space(*p) || *p == ',')) p++;
    if (p >= end) break;
    c = *p;
    if ((c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z')) { command = c; p++; }
    else if (!command) return 0;
    else if (command == 'M') command = 'L';
    else if (command == 'm') command = 'l';
    switch (command) {
      case 'M': case 'm': {
        double x, y;
        if (!svg_number(&p, end, &x) || !svg_number(&p, end, &y)) return 0;
        if (command == 'm') { x += cx; y += cy; }
        if (!svg_path_segment(path, EXR_PATH_MOVE, x, y, 0, 0, 0, 0)) return 0;
        cx = sx = x; cy = sy = y; started = 1; last_cx = cx; last_cy = cy;
        break;
      }
      case 'L': case 'l': {
        double x, y;
        if (!svg_number(&p, end, &x) || !svg_number(&p, end, &y)) return 0;
        if (command == 'l') { x += cx; y += cy; }
        if (!svg_path_segment(path, EXR_PATH_LINE, x, y, 0, 0, 0, 0)) return 0;
        cx = x; cy = y; last_cx = cx; last_cy = cy;
        break;
      }
      case 'H': case 'h': {
        double x;
        if (!svg_number(&p, end, &x)) return 0;
        if (command == 'h') x += cx;
        if (!svg_path_segment(path, EXR_PATH_LINE, x, cy, 0, 0, 0, 0)) return 0;
        cx = x; last_cx = cx; last_cy = cy;
        break;
      }
      case 'V': case 'v': {
        double y;
        if (!svg_number(&p, end, &y)) return 0;
        if (command == 'v') y += cy;
        if (!svg_path_segment(path, EXR_PATH_LINE, cx, y, 0, 0, 0, 0)) return 0;
        cy = y; last_cx = cx; last_cy = cy;
        break;
      }
      case 'C': case 'c': {
        double x1, y1, x2, y2, x, y;
        if (!svg_number(&p, end, &x1) || !svg_number(&p, end, &y1) ||
            !svg_number(&p, end, &x2) || !svg_number(&p, end, &y2) ||
            !svg_number(&p, end, &x) || !svg_number(&p, end, &y)) return 0;
        if (command == 'c') { x1 += cx; y1 += cy; x2 += cx; y2 += cy; x += cx; y += cy; }
        if (!svg_path_segment(path, EXR_PATH_CUBIC, x, y, x1, y1, x2, y2)) return 0;
        last_cx = x2; last_cy = y2; cx = x; cy = y;
        break;
      }
      case 'S': case 's': {
        double x2, y2, x, y, x1, y1;
        if (!svg_number(&p, end, &x2) || !svg_number(&p, end, &y2) ||
            !svg_number(&p, end, &x) || !svg_number(&p, end, &y)) return 0;
        if (command == 's') { x2 += cx; y2 += cy; x += cx; y += cy; }
        x1 = 2*cx - last_cx; y1 = 2*cy - last_cy;
        if (!svg_path_segment(path, EXR_PATH_CUBIC, x, y, x1, y1, x2, y2)) return 0;
        last_cx = x2; last_cy = y2; cx = x; cy = y;
        break;
      }
      case 'Q': case 'q': {
        double x1, y1, x, y;
        if (!svg_number(&p, end, &x1) || !svg_number(&p, end, &y1) ||
            !svg_number(&p, end, &x) || !svg_number(&p, end, &y)) return 0;
        if (command == 'q') { x1 += cx; y1 += cy; x += cx; y += cy; }
        if (!svg_path_segment(path, EXR_PATH_QUAD, x, y, x1, y1, 0, 0)) return 0;
        last_cx = x1; last_cy = y1; cx = x; cy = y;
        break;
      }
      case 'T': case 't': {
        double x, y, x1, y1;
        if (!svg_number(&p, end, &x) || !svg_number(&p, end, &y)) return 0;
        if (command == 't') { x += cx; y += cy; }
        x1 = 2*cx - last_cx; y1 = 2*cy - last_cy;
        if (!svg_path_segment(path, EXR_PATH_QUAD, x, y, x1, y1, 0, 0)) return 0;
        last_cx = x1; last_cy = y1; cx = x; cy = y;
        break;
      }
      case 'A': case 'a': {
        double rx, ry, angle, x, y;
        int large, sweep;
        if (!svg_number(&p, end, &rx) || !svg_number(&p, end, &ry) || !svg_number(&p, end, &angle) ||
            !svg_flag(&p, end, &large) || !svg_flag(&p, end, &sweep) ||
            !svg_number(&p, end, &x) || !svg_number(&p, end, &y)) return 0;
        if (command == 'a') { x += cx; y += cy; }
        if (!svg_arc(path, cx, cy, rx, ry, angle, large, sweep, x, y)) return 0;
        last_cx = cx = x; last_cy = cy = y;
        break;
      }
      case 'Z': case 'z': {
        if (!svg_path_segment(path, EXR_PATH_CLOSE, sx, sy, 0, 0, 0, 0)) return 0;
        cx = sx; cy = sy; last_cx = cx; last_cy = cy;
        break;
      }
      default: return 0;
    }
  }
  return started;
}

static int svg_add_shape(svg_path *path, const svg_node *node) {
  const char *value;
  switch (node->element) {
    case SVG_PATH:
      value = svg_attr(node, "d");
      return value && *value ? svg_path_data(path, value) : 0;
    case SVG_RECT: {
      double values[4];
      const char *x = svg_attr(node, "x"), *y = svg_attr(node, "y");
      const char *w = svg_attr(node, "width"), *h = svg_attr(node, "height");
      const char *rx = svg_attr(node, "rx"), *ry = svg_attr(node, "ry");
      if (!w || !h) return 0;
      values[0] = values[1] = 0;
      values[2] = values[3] = 0;
      if (x && !svg_numbers_text(x, &values[0], 1)) return 0;
      if (y && !svg_numbers_text(y, &values[1], 1)) return 0;
      if (!svg_numbers_text(w, &values[2], 1) || !svg_numbers_text(h, &values[3], 1)) return 0;
      if ((rx && strcmp(rx, "0")) || (ry && strcmp(ry, "0"))) {
        path->status = exr_fail(path->doc->error, EXR_UNSUPPORTED, "Rounded SVG rectangles are not supported");
        return 0;
      }
      if (!(values[2] > 0) || !(values[3] > 0)) return 0;
      return svg_path_segment(path, EXR_PATH_MOVE, values[0], values[1], 0, 0, 0, 0) &&
             svg_path_segment(path, EXR_PATH_LINE, values[0] + values[2], values[1], 0, 0, 0, 0) &&
             svg_path_segment(path, EXR_PATH_LINE, values[0] + values[2], values[1] + values[3], 0, 0, 0, 0) &&
             svg_path_segment(path, EXR_PATH_LINE, values[0], values[1] + values[3], 0, 0, 0, 0) &&
             svg_path_segment(path, EXR_PATH_CLOSE, values[0], values[1], 0, 0, 0, 0);
    }
    case SVG_CIRCLE:
    case SVG_ELLIPSE: {
      double cx = 0, cy = 0, rx = 0, ry = 0, k = 0.5522847498307936;
      const char *value;
      if ((value = svg_attr(node, "cx")) && !svg_numbers_text(value, &cx, 1)) return 0;
      if ((value = svg_attr(node, "cy")) && !svg_numbers_text(value, &cy, 1)) return 0;
      if (node->element == SVG_CIRCLE) {
        if (!(value = svg_attr(node, "r")) || !svg_numbers_text(value, &rx, 1)) return 0;
        ry = rx;
      } else {
        if ((value = svg_attr(node, "rx")) && !svg_numbers_text(value, &rx, 1)) return 0;
        if ((value = svg_attr(node, "ry")) && !svg_numbers_text(value, &ry, 1)) return 0;
        if (!rx && ry) rx = ry;
        if (!ry && rx) ry = rx;
      }
      if (!(rx > 0) || !(ry > 0)) return 0;
      return svg_path_segment(path, EXR_PATH_MOVE, cx + rx, cy, 0, 0, 0, 0) &&
             svg_path_segment(path, EXR_PATH_CUBIC, cx, cy + ry, cx + rx, cy + k*ry, cx + k*rx, cy + ry) &&
             svg_path_segment(path, EXR_PATH_CUBIC, cx - rx, cy, cx - k*rx, cy + ry, cx - rx, cy + k*ry) &&
             svg_path_segment(path, EXR_PATH_CUBIC, cx, cy - ry, cx - rx, cy - k*ry, cx - k*rx, cy - ry) &&
             svg_path_segment(path, EXR_PATH_CUBIC, cx + rx, cy, cx + k*rx, cy - ry, cx + rx, cy - k*ry) &&
             svg_path_segment(path, EXR_PATH_CLOSE, cx + rx, cy, 0, 0, 0, 0);
    }
    case SVG_LINE: {
      double x1 = 0, y1 = 0, x2 = 0, y2 = 0;
      const char *value;
      if ((value = svg_attr(node, "x1")) && !svg_numbers_text(value, &x1, 1)) return 0;
      if ((value = svg_attr(node, "y1")) && !svg_numbers_text(value, &y1, 1)) return 0;
      if ((value = svg_attr(node, "x2")) && !svg_numbers_text(value, &x2, 1)) return 0;
      if ((value = svg_attr(node, "y2")) && !svg_numbers_text(value, &y2, 1)) return 0;
      return svg_path_segment(path, EXR_PATH_MOVE, x1, y1, 0, 0, 0, 0) &&
             svg_path_segment(path, EXR_PATH_LINE, x2, y2, 0, 0, 0, 0);
    }
    case SVG_POLYLINE:
    case SVG_POLYGON: {
      const unsigned char *p, *end;
      double x, y;
      int first = 1;
      value = svg_attr(node, "points");
      if (!value) return 0;
      p = (const unsigned char *)value; end = p + strlen(value);
      while (p < end) {
        if (!svg_number(&p, end, &x)) return 0;
        while (p < end && (svg_space(*p) || *p == ',')) p++;
        if (!svg_number(&p, end, &y)) return 0;
        if (first) {
          if (!svg_path_segment(path, EXR_PATH_MOVE, x, y, 0, 0, 0, 0)) return 0;
          first = 0;
        } else if (!svg_path_segment(path, EXR_PATH_LINE, x, y, 0, 0, 0, 0)) return 0;
        while (p < end && (svg_space(*p) || *p == ',')) p++;
      }
      if (first) return 0;
      if (node->element == SVG_POLYGON) {
        double sx = 0, sy = 0;
        /* Close to the first point. */
        {
          const unsigned char *q = (const unsigned char *)value;
          svg_number(&q, end, &sx); svg_number(&q, end, &sy);
        }
        if (!svg_path_segment(path, EXR_PATH_CLOSE, sx, sy, 0, 0, 0, 0)) return 0;
      }
      return 1;
    }
    default:
      return 0;
  }
}

/* ---------- document loading ---------- */

static exr_status svg_load_document(svg_document *doc, exr_face *face, uint32_t glyph,
                                    size_t *work, const exr_control *control, exr_error *error) {
  svg_record *record;
  unsigned char *data = NULL;
  exr_status status;
  FT_ULong length;
  memset(doc, 0, sizeof(*doc));
  doc->face = face; doc->work = work; doc->control = control; doc->error = error;
  status = svg_directory(face, work, control, error);
  if (status != EXR_OK) return status;
  record = svg_lookup(face, glyph);
  if (!record) return EXR_OK;
  length = record->length;
  data = malloc(record->length ? record->length : 1);
  if (!data) return exr_fail(error, EXR_MEMORY, "SVG document allocation failed");
  if (FT_Load_Sfnt_Table(face->face, FT_MAKE_TAG('S','V','G',' '),
                         (FT_Long)(face->svg->list + record->offset), data, &length) || length != record->length) {
    free(data);
    return exr_fail(error, EXR_FONT, "Cannot read SVG document");
  }
  if (!record->length) { free(data); return exr_fail(error, EXR_FONT, "Empty SVG document"); }
  doc->document = data;
  doc->document_size = record->length;
  if (record->length >= 2 && data[0] == 0x1f && data[1] == 0x8b) {
    size_t header = 10, trailer = 8, output_size;
    unsigned flags;
    unsigned char *output;
    if (record->length < header + trailer) { free(data); return exr_fail(error, EXR_FONT, "Truncated gzip SVG document"); }
    flags = data[3];
    if (flags & 4) {
      if (header + 2 > record->length) { free(data); return exr_fail(error, EXR_FONT, "Truncated gzip header"); }
      header += 2 + ((size_t)data[header] | (size_t)data[header+1] << 8);
    }
    if (flags & 8) { while (header < record->length && data[header]) header++; header++; }
    if (flags & 16) { while (header < record->length && data[header]) header++; header++; }
    if (flags & 2) header += 2;
    if (header >= record->length || record->length - header < trailer) {
      free(data); return exr_fail(error, EXR_FONT, "Truncated gzip SVG document");
    }
    output_size = (size_t)data[record->length-4] | (size_t)data[record->length-3] << 8 |
                  (size_t)data[record->length-2] << 16 | (size_t)data[record->length-1] << 24;
    if (!output_size || output_size > SVG_MAX_DOCUMENT) { free(data); return exr_fail(error, EXR_LIMIT, "SVG gzip document exceeds 4 MiB"); }
    output = malloc(output_size);
    if (!output) { free(data); return exr_fail(error, EXR_MEMORY, "SVG gzip allocation failed"); }
    {
      size_t produced = tinfl_decompress_mem_to_mem(output, output_size, data + header,
                                                    record->length - header - trailer, 0);
      if (produced == TINFL_DECOMPRESS_MEM_TO_MEM_FAILED || produced != output_size) {
        free(output);
        free(data);
        return exr_fail(error, EXR_FONT, "Cannot decompress gzip SVG document");
      }
    }
    free(data);
    data = NULL;
    doc->owned = output;
    doc->document = output;
    doc->document_size = output_size;
  } else {
    doc->owned = data;
  }
  status = svg_parse(doc);
  if (status != EXR_OK) { svg_document_free(doc); return status; }
  if (doc->root->element != SVG_ROOT) { svg_document_free(doc); return exr_fail(error, EXR_FORMAT, "SVG document root is invalid"); }
  {
    const char *view_box = svg_attr(doc->root, "viewBox");
    const char *width = svg_attr(doc->root, "width");
    const char *height = svg_attr(doc->root, "height");
    const char *preserve = svg_attr(doc->root, "preserveAspectRatio");
    if (view_box) {
      if (!svg_numbers_text(view_box, doc->view_box, 4) ||
          !(doc->view_box[2] > 0) || !(doc->view_box[3] > 0)) {
        svg_document_free(doc);
        return exr_fail(error, EXR_UNSUPPORTED, "SVG viewBox is invalid or unsupported");
      }
      doc->has_view_box = 1;
    }
    if (width) {
      if (!svg_numbers_text(width, &doc->width, 1) || doc->width <= 0) { svg_document_free(doc); return exr_fail(error, EXR_UNSUPPORTED, "SVG width is invalid"); }
      doc->has_width = 1;
    }
    if (height) {
      if (!svg_numbers_text(height, &doc->height, 1) || doc->height <= 0) { svg_document_free(doc); return exr_fail(error, EXR_UNSUPPORTED, "SVG height is invalid"); }
      doc->has_height = 1;
    }
    if (preserve) {
      if (strcmp(preserve, "none")) { svg_document_free(doc); return exr_fail(error, EXR_UNSUPPORTED, "SVG preserveAspectRatio is not supported"); }
      doc->preserve_none = 1;
    }
  }
  return EXR_OK;
}

exr_status exr_font_svg_covers(exr_face *face, uint32_t glyph, int *covers, size_t *work, const exr_control *control, exr_error *error) {
  size_t local = 0;
  exr_status status;
  *covers = 0;
  if (!face) return exr_fail(error, EXR_ARGUMENT, "Missing SVG font face");
  status = svg_directory(face, work ? work : &local, control, error);
  if (status != EXR_OK) return status;
  *covers = svg_lookup(face, glyph) != NULL;
  return EXR_OK;
}

void exr_font_svg_free(exr_face *face) {
  free(face->svg);
  face->svg = NULL;
  face->svg_checked = 0;
}

/* ---------- rendering ---------- */

typedef struct {
  svg_document *doc;
  exr_canvas *canvas;
  double foreground[3];
  double bbox[4];
  int has_bbox;
  unsigned depth;
} svg_render;

static void svg_state_default(svg_state *state) {
  memset(state, 0, sizeof(*state));
  state->matrix[0] = state->matrix[3] = 1;
  state->fill[0] = state->fill[1] = state->fill[2] = 0;
  state->fill[3] = 1;
  state->stroke[3] = 1;
  state->stroke_none = 1;
  state->fill_opacity = state->stroke_opacity = 1;
  state->stroke_width = 1;
  state->fill_rule = EXR_FILL_NONZERO;
  state->cap = EXR_CAP_BUTT;
  state->join = EXR_JOIN_MITER;
  state->miter_limit = 4;
}

static exr_status svg_number_attribute(svg_document *doc, const char *value, double *out) {
  if (!value || !svg_numbers_text(value, out, 1) || !isfinite(*out)) return exr_fail(doc->error, EXR_FORMAT, "Invalid SVG numeric attribute");
  return EXR_OK;
}

static exr_status svg_opacity_attribute(svg_document *doc, const char *value, double *out) {
  const char *end;
  if (!value) return EXR_OK;
  end = value + strlen(value);
  while (end > value && svg_space(end[-1])) end--;
  if (end > value && end[-1] == '%') {
    size_t length = (size_t)(end - value);
    char buffer[64];
    if (length >= sizeof(buffer)) return exr_fail(doc->error, EXR_LIMIT, "SVG opacity is too long");
    memcpy(buffer, value, length - 1);
    buffer[length - 1] = 0;
    if (!svg_numbers_text(buffer, out, 1)) return exr_fail(doc->error, EXR_FORMAT, "Invalid SVG opacity");
    *out /= 100;
  } else if (!svg_numbers_text(value, out, 1)) return exr_fail(doc->error, EXR_FORMAT, "Invalid SVG opacity");
  if (*out < 0 || *out > 1) return exr_fail(doc->error, EXR_FORMAT, "SVG opacity is outside 0..1");
  return EXR_OK;
}

static exr_status svg_apply_attributes(svg_render *render, const svg_node *node, svg_state *state, int *transform_ready) {
  svg_document *doc = render->doc;
  const char *value;
  exr_status status;
  {
    static const char *rejected[] = {
      "style", "mask", "clip-path", "filter", "marker-start", "marker-mid", "marker-end",
      "stroke-dasharray", "stroke-dashoffset", "paint-order", "vector-effect"
    };
    unsigned i;
    for (i = 0; i < sizeof(rejected)/sizeof(rejected[0]); i++)
      if (svg_attr(node, rejected[i]))
        return exr_fail(doc->error, EXR_UNSUPPORTED, "Unsupported SVG presentation attribute");
  }
  if ((value = svg_attr(node, "transform"))) {
    double matrix[6];
    if (!svg_transform(value, matrix)) return exr_fail(doc->error, EXR_UNSUPPORTED, "Unsupported SVG transform");
    svg_matrix_multiply(state->matrix, matrix, state->matrix);
    *transform_ready = 1;
  }
  if ((value = svg_attr(node, "display")) && !strcmp(value, "none")) state->hidden = 1;
  if ((value = svg_attr(node, "visibility")) && !strcmp(value, "hidden")) state->hidden = 1;
  if ((value = svg_attr(node, "color"))) {
    double rgba[4];
    int kind = svg_color(value, state->current, rgba);
    if (kind != 1) return exr_fail(doc->error, EXR_UNSUPPORTED, "Unsupported SVG color property");
    state->current[0] = rgba[0]; state->current[1] = rgba[1]; state->current[2] = rgba[2];
  }
  if ((value = svg_attr(node, "fill"))) {
    double rgba[4];
    int kind = svg_color(value, state->current, rgba);
    if (kind < 0) return exr_fail(doc->error, EXR_UNSUPPORTED, "Unsupported SVG fill paint");
    if (kind == 0) state->fill_none = 1;
    else { memcpy(state->fill, rgba, sizeof(rgba)); state->fill_none = 0; }
  }
  if ((value = svg_attr(node, "stroke"))) {
    double rgba[4];
    int kind = svg_color(value, state->current, rgba);
    if (kind < 0) return exr_fail(doc->error, EXR_UNSUPPORTED, "Unsupported SVG stroke paint");
    if (kind == 0) state->stroke_none = 1;
    else { memcpy(state->stroke, rgba, sizeof(rgba)); state->stroke_none = 0; }
  }
  if ((value = svg_attr(node, "fill-opacity"))) {
    status = svg_opacity_attribute(doc, value, &state->fill_opacity); if (status != EXR_OK) return status;
  }
  if ((value = svg_attr(node, "stroke-opacity"))) {
    status = svg_opacity_attribute(doc, value, &state->stroke_opacity); if (status != EXR_OK) return status;
  }
  if ((value = svg_attr(node, "stroke-width"))) {
    status = svg_number_attribute(doc, value, &state->stroke_width); if (status != EXR_OK) return status;
    if (state->stroke_width < 0) return exr_fail(doc->error, EXR_FORMAT, "Negative SVG stroke width");
  }
  if ((value = svg_attr(node, "fill-rule"))) {
    if (!strcmp(value, "nonzero")) state->fill_rule = EXR_FILL_NONZERO;
    else if (!strcmp(value, "evenodd")) state->fill_rule = EXR_FILL_EVENODD;
    else return exr_fail(doc->error, EXR_UNSUPPORTED, "Unsupported SVG fill rule");
  }
  if ((value = svg_attr(node, "stroke-linecap"))) {
    if (!strcmp(value, "butt")) state->cap = EXR_CAP_BUTT;
    else if (!strcmp(value, "round")) state->cap = EXR_CAP_ROUND;
    else if (!strcmp(value, "square")) state->cap = EXR_CAP_SQUARE;
    else return exr_fail(doc->error, EXR_UNSUPPORTED, "Unsupported SVG line cap");
  }
  if ((value = svg_attr(node, "stroke-linejoin"))) {
    if (!strcmp(value, "miter")) state->join = EXR_JOIN_MITER;
    else if (!strcmp(value, "round")) state->join = EXR_JOIN_ROUND;
    else if (!strcmp(value, "bevel")) state->join = EXR_JOIN_BEVEL;
    else return exr_fail(doc->error, EXR_UNSUPPORTED, "Unsupported SVG line join");
  }
  if ((value = svg_attr(node, "stroke-miterlimit"))) {
    status = svg_number_attribute(doc, value, &state->miter_limit); if (status != EXR_OK) return status;
    if (state->miter_limit < 1) return exr_fail(doc->error, EXR_FORMAT, "Invalid SVG miter limit");
  }
  return EXR_OK;
}

static void svg_bbox_point(svg_render *render, const double m[6], double x, double y) {
  double ox, oy;
  svg_matrix_point(m, x, y, &ox, &oy);
  if (!isfinite(ox) || !isfinite(oy) || fabs(ox) > 1e7 || fabs(oy) > 1e7) {
    render->has_bbox = 2;
    return;
  }
  if (!render->has_bbox) {
    render->bbox[0] = render->bbox[2] = ox;
    render->bbox[1] = render->bbox[3] = oy;
    render->has_bbox = 1;
    return;
  }
  if (ox < render->bbox[0]) render->bbox[0] = ox;
  if (oy < render->bbox[1]) render->bbox[1] = oy;
  if (ox > render->bbox[2]) render->bbox[2] = ox;
  if (oy > render->bbox[3]) render->bbox[3] = oy;
}

static void svg_path_bbox(svg_render *render, const exr_path_segment *segments, size_t count,
                          const svg_state *state, int stroke) {
  size_t i, j;
  unsigned points;
  for (i = 0; i < count; i++) {
    points = segments[i].verb == EXR_PATH_CUBIC ? 3 : segments[i].verb == EXR_PATH_QUAD ? 2 :
             segments[i].verb == EXR_PATH_CLOSE ? 0 : 1;
    for (j = 0; j < points; j++) svg_bbox_point(render, state->matrix, segments[i].points[j].x, segments[i].points[j].y);
  }
  if (stroke && state->stroke_width > 0) {
    double scale = fmax(hypot(state->matrix[0], state->matrix[1]), hypot(state->matrix[2], state->matrix[3]));
    double margin = state->stroke_width*scale;
    if (render->has_bbox == 1) {
      render->bbox[0] -= margin; render->bbox[1] -= margin;
      render->bbox[2] += margin; render->bbox[3] += margin;
    }
  }
}

static uint32_t svg_pack(double rgba[4], double alpha) {
  unsigned r = (unsigned)lround(fmin(1, fmax(0, rgba[0]))*255);
  unsigned g = (unsigned)lround(fmin(1, fmax(0, rgba[1]))*255);
  unsigned b = (unsigned)lround(fmin(1, fmax(0, rgba[2]))*255);
  unsigned a = (unsigned)lround(fmin(1, fmax(0, rgba[3]*alpha))*255);
  return r << 24 | g << 16 | b << 8 | a;
}

static exr_status svg_node_walk(svg_render *render, svg_node *node, const svg_state *parent, svg_node *target);

static exr_status svg_draw_shape(svg_render *render, svg_node *node, const svg_state *state, double opacity) {
  svg_path path;
  exr_status status;
  int is_line = node->element == SVG_LINE;
  memset(&path, 0, sizeof(path));
  path.doc = render->doc;
  if (!svg_add_shape(&path, node)) {
    status = path.status;
    if (!status) status = exr_fail(render->doc->error, EXR_FORMAT, "Invalid or empty SVG shape geometry");
    free(path.segments);
    return status;
  }
  if (render->canvas) {
    exr_draw_style style = exr_draw_style_defaults();
    svg_state current = *state;
    if (is_line) current.fill_none = 1;
    style.fill = svg_pack(current.fill, current.fill_opacity);
    style.stroke = svg_pack(current.stroke, current.stroke_opacity);
    style.flags = 0;
    if (!current.fill_none && (style.fill & 255)) style.flags |= EXR_DRAW_FILL;
    if (!current.stroke_none && current.stroke_width > 0 && (style.stroke & 255)) style.flags |= EXR_DRAW_STROKE;
    style.rule = current.fill_rule;
    style.line.width = current.stroke_width;
    style.line.cap = current.cap;
    style.line.join = current.join;
    style.line.miter_limit = current.miter_limit;
    if (!style.flags) { free(path.segments); return EXR_OK; }
    if (opacity < 1) {
      status = exr_canvas_begin_layer(render->canvas, opacity, EXR_BLEND_NORMAL, render->doc->error);
      if (status != EXR_OK) { free(path.segments); return status; }
    }
    status = exr_canvas_path(render->canvas, path.segments, path.count, current.matrix, &style, render->doc->error);
    if (opacity < 1) {
      exr_status end = exr_canvas_end_layer(render->canvas, status == EXR_OK, render->doc->error);
      if (status == EXR_OK) status = end;
    }
    free(path.segments);
    return status;
  }
  {
    svg_state current = *state;
    if (is_line) current.fill_none = 1;
    svg_path_bbox(render, path.segments, path.count, &current,
                  !current.stroke_none && current.stroke_width > 0);
  }
  free(path.segments);
  return EXR_OK;
}

static exr_status svg_node_walk(svg_render *render, svg_node *node, const svg_state *parent, svg_node *target) {
  svg_state state = *parent;
  int transform_ready = 0;
  double opacity = 1;
  const char *value;
  exr_status status;
  if (render->depth >= SVG_MAX_DEPTH) return exr_fail(render->doc->error, EXR_LIMIT, "SVG render depth exceeds 32");
  render->depth++;
  status = svg_apply_attributes(render, node, &state, &transform_ready);
  if (status != EXR_OK) { render->depth--; return status; }
  (void)transform_ready;
  if ((value = svg_attr(node, "opacity"))) {
    status = svg_opacity_attribute(render->doc, value, &opacity);
    if (status != EXR_OK) { render->depth--; return status; }
  }
  if (state.hidden) { render->depth--; return EXR_OK; }
  if (node->element == SVG_DEFS) { render->depth--; return EXR_OK; }
  if (node == target) target = NULL;
  if (node->element == SVG_GROUP || node->element == SVG_ROOT) {
    svg_node *child, *selected = target;
    /* Walk the selected glyph's ancestors so their state and isolated layers
       apply, without painting siblings from a shared glyph document. */
    while (selected && selected->parent != node) selected = selected->parent;
    if (render->canvas && opacity < 1) {
      status = exr_canvas_begin_layer(render->canvas, opacity, EXR_BLEND_NORMAL, render->doc->error);
      if (status != EXR_OK) { render->depth--; return status; }
    }
    for (child = node->first; child; child = child->next) {
      if (target && child != selected) continue;
      status = svg_node_walk(render, child, &state, target);
      if (status != EXR_OK) {
        if (render->canvas && opacity < 1) exr_canvas_end_layer(render->canvas, 0, render->doc->error);
        render->depth--;
        return status;
      }
      if (render->canvas && exr_control_cancel(render->doc->control, render->doc->error) != EXR_OK) {
        if (opacity < 1) exr_canvas_end_layer(render->canvas, 0, render->doc->error);
        render->depth--;
        return EXR_CANCELLED;
      }
    }
    if (render->canvas && opacity < 1) status = exr_canvas_end_layer(render->canvas, 1, render->doc->error);
    render->depth--;
    return status;
  }
  status = svg_draw_shape(render, node, &state, opacity);
  render->depth--;
  return status;
}

static svg_node *svg_find_id(svg_document *doc, const char *id) {
  size_t i;
  for (i = 0; i < doc->node_count; i++) {
    const char *value = svg_attr(doc->nodes[i], "id");
    if (value && !strcmp(value, id)) return doc->nodes[i];
  }
  return NULL;
}

static exr_status svg_render_document(svg_render *render, uint32_t glyph, double size, int measure) {
  svg_document *doc = render->doc;
  svg_state state;
  svg_node *target = NULL;
  char id[32];
  exr_status status;
  double sx, sy, ox, oy, left, top;
  snprintf(id, sizeof(id), "glyph%u", glyph);
  target = svg_find_id(doc, id);
  svg_state_default(&state);
  state.current[0] = render->foreground[0];
  state.current[1] = render->foreground[1];
  state.current[2] = render->foreground[2];
  if (doc->has_view_box) {
    sx = size/doc->view_box[2];
    sy = size/doc->view_box[3];
    ox = -doc->view_box[0]*sx;
    oy = -size - doc->view_box[1]*sy;
  } else {
    sx = sy = size/(double)doc->face->face->units_per_EM;
    ox = oy = 0;
  }
  state.matrix[0] = sx; state.matrix[1] = 0; state.matrix[2] = 0; state.matrix[3] = sy;
  state.matrix[4] = ox; state.matrix[5] = oy;
  if (measure) {
    render->has_bbox = 0;
    status = svg_node_walk(render, doc->root, &state, target);
    if (status != EXR_OK) return status;
    if (render->has_bbox == 1) {
      left = floor(render->bbox[0]);
      top = floor(render->bbox[1]);
      render->bbox[0] = left; render->bbox[1] = top;
      render->bbox[2] = ceil(render->bbox[2]);
      render->bbox[3] = ceil(render->bbox[3]);
    }
    return EXR_OK;
  }
  left = render->bbox[0];
  top = render->bbox[1];
  state.matrix[4] -= left;
  state.matrix[5] -= top;
  render->depth = 0;
  return svg_node_walk(render, doc->root, &state, target);
}

exr_status exr_font_svg(exr_face *face, uint32_t glyph, float pixels, uint32_t foreground,
                        exr_color_surface *out, size_t *work, const exr_control *control, exr_error *error) {
  svg_document doc;
  svg_render render;
  exr_status status;
  double size = pixels;
  memset(out, 0, sizeof(*out));
  if (!face || !work) return exr_fail(error, EXR_ARGUMENT, "Invalid SVG glyph render input");
  if (!(pixels > 0) || !isfinite(pixels) || pixels > 4096) return exr_fail(error, EXR_ARGUMENT, "Invalid SVG glyph size");
  if (glyph >= (uint32_t)face->face->num_glyphs) return exr_fail(error, EXR_ARGUMENT, "Invalid SVG glyph index");
  if (!face->face->units_per_EM) return exr_fail(error, EXR_FONT, "SVG glyph lacks design units");
  if (exr_control_cancel(control, error) != EXR_OK) return EXR_CANCELLED;
  status = svg_load_document(&doc, face, glyph, work, control, error);
  if (status != EXR_OK) return status;
  if (!doc.root) return EXR_OK;
  memset(&render, 0, sizeof(render));
  render.doc = &doc;
  render.foreground[0] = (double)((foreground >> 24) & 255)/255.0;
  render.foreground[1] = (double)((foreground >> 16) & 255)/255.0;
  render.foreground[2] = (double)((foreground >> 8) & 255)/255.0;
  doc.segments = 0;
  status = svg_render_document(&render, glyph, size, 1);
  if (status != EXR_OK) { svg_document_free(&doc); return status; }
  if (!render.has_bbox) { svg_document_free(&doc); return EXR_OK; }
  if (render.has_bbox == 2) { svg_document_free(&doc); return exr_fail(error, EXR_LIMIT, "SVG glyph bounds exceed precision"); }
  {
    long left = (long)render.bbox[0], top = (long)render.bbox[1];
    long width = (long)render.bbox[2] - left, height = (long)render.bbox[3] - top;
    exr_canvas_config config;
    exr_canvas *canvas = NULL;
    exr_bitmap bitmap = {0};
    if (!(width > 0 && height > 0) || width > (long)SVG_MAX_REGION || height > (long)SVG_MAX_REGION ||
        (uint64_t)width*(uint64_t)height > SVG_MAX_PIXELS) {
      svg_document_free(&doc);
      return exr_fail(error, EXR_LIMIT, "SVG glyph surface exceeds limits");
    }
    if (!exr_vector_work(work, (size_t)width*(size_t)height)) {
      svg_document_free(&doc);
      return exr_fail(error, EXR_LIMIT, "SVG glyph surface exceeds raster budget");
    }
    memset(&config, 0, sizeof(config));
    config.width = (uint32_t)width; config.height = (uint32_t)height; config.channels = 4;
    if (control) config.control = *control;
    status = exr_canvas_create(&config, &canvas, error);
    if (status != EXR_OK) { svg_document_free(&doc); return status; }
    render.canvas = canvas;
    doc.segments = 0;
    status = svg_render_document(&render, glyph, size, 0);
    if (status == EXR_OK) status = exr_canvas_take(canvas, &bitmap, error);
    exr_canvas_free(canvas);
    svg_document_free(&doc);
    if (status != EXR_OK) return status;
    out->bitmap = bitmap;
    out->left = (float)left;
    out->top = (float)top;
  }
  return EXR_OK;
}
