/* SPDX-License-Identifier: MIT */
/* OPDS 1.x Atom catalogs: data structures only, no I/O. */
#include "base_internal.h"
#include "exr/opds.h"
#include <ctype.h>
#include <expat.h>
#define OPDS_ATOM "http://www.w3.org/2005/Atom|"
#define OPDS_MAX_INPUT ((size_t)16 * 1024 * 1024)
#define OPDS_MAX_ENTRIES 4096
#define OPDS_MAX_DEPTH 64
#define OPDS_MAX_TEXT ((size_t)64 * 1024)
#define OPDS_MAX_URL 8192

static int has_ci(const char *hay, const char *needle) {
  size_t n = strlen(needle);
  if (!hay) return 0;
  for (; *hay; hay++) {
    size_t i = 0;
    while (i < n && hay[i] && tolower((unsigned char)hay[i]) == tolower((unsigned char)needle[i])) i++;
    if (i == n) return 1;
  }
  return 0;
}
static int starts_ci(const char *s, const char *prefix) {
  if (!s) return 0;
  while (*prefix) {
    if (tolower((unsigned char)*s) != tolower((unsigned char)*prefix)) return 0;
    s++; prefix++;
  }
  return 1;
}
static int ends_ci(const char *s, const char *suffix) {
  size_t a = strlen(s), b = strlen(suffix);
  return a >= b && starts_ci(s + a - b, suffix);
}

/* ---- URL resolution -------------------------------------------------- */
static void remove_dots(char *path) {
  size_t n = strcspn(path, "?#"), i = 0, o = 0;
  char *out = malloc(n + 2);
  if (!out) return;
  while (i < n) {
    if (path[i] == '/') {
      size_t end = i + 1, len;
      while (end < n && path[end] != '/') end++;
      len = end - i - 1;
      if (len == 1 && path[i + 1] == '.') {
        if (end == n) out[o++] = '/';
      } else if (len == 2 && path[i + 1] == '.' && path[i + 2] == '.') {
        while (o > 0 && out[o - 1] != '/') o--;
        if (o > 0) o--;
        if (end == n) out[o++] = '/';
      } else {
        memcpy(out + o, path + i, end - i);
        o += end - i;
      }
      i = end;
    } else out[o++] = path[i++];
  }
  memmove(path + o, path + n, strlen(path + n) + 1);
  memcpy(path, out, o);
  free(out);
}
static int has_scheme(const char *s) {
  if (!isalpha((unsigned char)*s)) return 0;
  while (isalnum((unsigned char)*s) || *s == '+' || *s == '-' || *s == '.') s++;
  return *s == ':';
}
exr_status exr_opds_resolve_url(const char *base, const char *ref, char **out, exr_error *error) {
  size_t scheme_len, auth_end, path_start, base_path_end;
  char *result;
  if (out) *out = NULL;
  if (!out || !ref) return exr_fail(error, EXR_ARGUMENT, "Missing URL reference");
  while (isspace((unsigned char)*ref)) ref++;
  if (strlen(ref) > OPDS_MAX_URL) return exr_fail(error, EXR_LIMIT, "URL exceeds 8 KiB");
  if (has_scheme(ref)) {
    if (!(result = exr_copy(ref, strlen(ref)))) return exr_fail(error, EXR_MEMORY, "URL allocation failed");
    *out = result;
    return EXR_OK;
  }
  if (!base || !has_scheme(base) || !strstr(base, "://"))
    return exr_fail(error, EXR_ARGUMENT, "Relative URL needs an absolute http(s) base");
  scheme_len = strcspn(base, ":");
  path_start = scheme_len + 3;
  auth_end = path_start + strcspn(base + path_start, "/?#");
  base_path_end = auth_end + strcspn(base + auth_end, "?#");
  {
    size_t base_len = strlen(base), ref_len = strlen(ref);
    size_t cap = base_len + ref_len + 8;
    size_t dir = base_path_end;
    result = malloc(cap);
    if (!result) return exr_fail(error, EXR_MEMORY, "URL allocation failed");
    if (ref[0] == '/' && ref[1] == '/') snprintf(result, cap, "%.*s:%s", (int)scheme_len, base, ref);
    else if (ref[0] == '/') snprintf(result, cap, "%.*s%s", (int)auth_end, base, ref);
    else if (ref[0] == '?') snprintf(result, cap, "%.*s%s", (int)base_path_end, base, ref);
    else if (ref[0] == '#') snprintf(result, cap, "%.*s%s", (int)(base_path_end + strcspn(base + base_path_end, "#")), base, ref);
    else if (!ref[0]) snprintf(result, cap, "%.*s", (int)(base_path_end + strcspn(base + base_path_end, "#")), base);
    else {
      while (dir > auth_end && base[dir - 1] != '/') dir--;
      if (dir == auth_end) snprintf(result, cap, "%.*s/%s", (int)auth_end, base, ref);
      else snprintf(result, cap, "%.*s%s", (int)dir, base, ref);
    }
    {
      char *p = result + path_start;
      p += strcspn(p, "/?#");
      if (*p == '/') remove_dots(p);
    }
  }
  *out = result;
  return EXR_OK;
}

/* ---- search templates ------------------------------------------------ */
exr_status exr_opds_search_url(const char *tmpl, const char *query, char **out, exr_error *error) {
  exr_buffer b = {0};
  int used = 0;
  if (out) *out = NULL;
  if (!out || !tmpl) return exr_fail(error, EXR_ARGUMENT, "Missing search template");
  if (!query || !*query) return exr_fail(error, EXR_ARGUMENT, "Empty search query");
  if (strlen(query) > 1024) return exr_fail(error, EXR_LIMIT, "Search query exceeds 1 KiB");
  for (const char *p = tmpl; *p;) {
    if (*p == '{') {
      const char *end = strchr(p, '}');
      if (end) {
        size_t n = (size_t)(end - p) - 1;
        const char *name = p + 1;
        if (n && name[n - 1] == '?') n--;
        if (n == 11 && !strncmp(name, "searchTerms", 11)) {
          static const char hex[] = "0123456789ABCDEF";
          for (const unsigned char *q = (const unsigned char *)query; *q; q++) {
            char enc[3];
            if (isalnum(*q) && *q < 0x80) { if (!exr_append(&b, q, 1)) goto memory; }
            else if (*q == '-' || *q == '.' || *q == '_' || *q == '~') { if (!exr_append(&b, q, 1)) goto memory; }
            else { enc[0] = '%'; enc[1] = hex[*q >> 4]; enc[2] = hex[*q & 15]; if (!exr_append(&b, enc, 3)) goto memory; }
          }
          used = 1;
        }
        p = end + 1;
        continue;
      }
    }
    if (!exr_append(&b, p, 1)) goto memory;
    p++;
  }
  if (!used) { free(b.data); return exr_fail(error, EXR_FORMAT, "Search template has no {searchTerms}"); }
  if (!exr_append(&b, "", 1)) goto memory;
  *out = b.data;
  return EXR_OK;
memory:
  free(b.data);
  return exr_fail(error, EXR_MEMORY, "Search URL allocation failed");
}

/* ---- Atom parsing ---------------------------------------------------- */
typedef enum { CAP_NONE, CAP_FEED_TITLE, CAP_TITLE, CAP_AUTHOR, CAP_SUMMARY, CAP_CONTENT } capture_kind;
typedef struct {
  char *title, *author, *summary, *content, *cover, *thumb, *detail, *download, *format;
  uint64_t size;
  int rank;
} entry_work;
typedef struct {
  XML_Parser parser;
  exr_error *error;
  exr_status status;
  const char *base;
  exr_opds_feed *feed;
  size_t capacity;
  unsigned depth;
  int in_entry, in_author;
  entry_work work;
  capture_kind kind;
  unsigned cap_depth;
  exr_buffer text;
} reader;

static void fail(reader *r, exr_status status, const char *message) {
  if (r->status == EXR_OK) {
    r->status = exr_fail(r->error, status, "%s", message);
    XML_StopParser(r->parser, XML_FALSE);
  }
}
static const char *attr(const char **a, const char *name) {
  for (; *a; a += 2) if (!strcmp(a[0], name)) return a[1];
  return NULL;
}
static void put(char **dst, char *value) { free(*dst); *dst = value; }
static char *resolved(reader *r, const char *href) {
  char *url = NULL;
  exr_error local = {0};
  if (!href || !*href || starts_ci(href, "data:")) return NULL;
  if (exr_opds_resolve_url(r->base, href, &url, &local) != EXR_OK) {
    if (local.code == EXR_MEMORY) fail(r, EXR_MEMORY, "OPDS URL allocation failed");
    return NULL;
  }
  return url;
}
static const char *local_name(const char *name) {
  const char *bar = strrchr(name, '|');
  return bar ? bar + 1 : name;
}
static int atom(const char *name, const char *local) {
  return !strncmp(name, OPDS_ATOM, sizeof(OPDS_ATOM) - 1) && !strcmp(name + sizeof(OPDS_ATOM) - 1, local);
}
static const char *format_of(const char *type, const char *href, int *rank) {
  static const struct { const char *needle, *name; int rank; } known[] = {
    {"epub", "epub", 0}, {"pdf", "pdf", 1}, {"mobipocket", "mobi", 2}, {"x-mobi", "mobi", 2},
    {"fb2", "fb2", 3}, {"comicbook+zip", "cbz", 4}, {"cbz", "cbz", 4}, {"text/plain", "txt", 5},
    {"rtf", "rtf", 6}, {"wordprocessingml", "docx", 7}};
  static const struct { const char *suffix, *name; int rank; } ext[] = {
    {".epub", "epub", 0}, {".pdf", "pdf", 1}, {".mobi", "mobi", 2}, {".azw3", "mobi", 2},
    {".fb2", "fb2", 3}, {".cbz", "cbz", 4}, {".txt", "txt", 5}, {".rtf", "rtf", 6}, {".docx", "docx", 7}};
  for (size_t i = 0; i < sizeof(known) / sizeof(*known); i++)
    if (has_ci(type, known[i].needle)) { *rank = known[i].rank; return known[i].name; }
  if (href) {
    size_t n = strcspn(href, "?#");
    char *path = exr_copy(href, n);
    if (path) {
      for (size_t i = 0; i < sizeof(ext) / sizeof(*ext); i++)
        if (ends_ci(path, ext[i].suffix)) { free(path); *rank = ext[i].rank; return ext[i].name; }
      free(path);
    }
  }
  /* Landing pages and indirect acquisitions are not files. */
  if (!type || has_ci(type, "html") || has_ci(type, "atom+xml") || has_ci(type, "opds")) return NULL;
  *rank = 8;
  return "other";
}
static void entry_link(reader *r, const char **a) {
  const char *rel = attr(a, "rel"), *type = attr(a, "type"), *href = attr(a, "href");
  entry_work *w = &r->work;
  char *url;
  if (!href) return;
  if (rel && starts_ci(rel, "http://opds-spec.org/acquisition")) {
    int rank = 0;
    const char *format = format_of(type, href, &rank);
    if (!format || (w->download && rank >= w->rank)) return;
    if (!(url = resolved(r, href))) return;
    put(&w->download, url);
    put(&w->format, exr_copy(format, strlen(format)));
    w->rank = rank;
    w->size = 0;
    if (attr(a, "length")) w->size = strtoull(attr(a, "length"), NULL, 10);
    if (!w->format) fail(r, EXR_MEMORY, "OPDS format allocation failed");
  } else if (rel && (!strcmp(rel, "http://opds-spec.org/image") || !strcmp(rel, "x-stanza-cover-image"))) {
    if (!w->cover) w->cover = resolved(r, href);
  } else if (rel && (!strcmp(rel, "http://opds-spec.org/image/thumbnail") || !strcmp(rel, "x-stanza-cover-image-thumbnail"))) {
    if (!w->thumb) w->thumb = resolved(r, href);
  } else if ((!rel || !strcmp(rel, "alternate") || !strcmp(rel, "subsection") ||
              starts_ci(rel, "http://opds-spec.org/sort/") || starts_ci(rel, "http://opds-spec.org/facet")) &&
             has_ci(type, "atom+xml")) {
    if (!w->detail) w->detail = resolved(r, href);
  }
}
static void feed_link(reader *r, const char **a) {
  const char *rel = attr(a, "rel"), *type = attr(a, "type"), *href = attr(a, "href");
  exr_opds_feed *f = r->feed;
  if (!rel || !href) return;
  if (!strcmp(rel, "next")) { if (!f->next_url) f->next_url = resolved(r, href); }
  else if (!strcmp(rel, "search")) {
    if (has_ci(type, "opensearchdescription")) { if (!f->search_description_url) f->search_description_url = resolved(r, href); }
    else if (strstr(href, "{searchTerms") && !f->search_template) f->search_template = resolved(r, href);
  }
}
static void entry_free(entry_work *w) {
  free(w->title); free(w->author); free(w->summary); free(w->content); free(w->cover);
  free(w->thumb); free(w->detail); free(w->download); free(w->format);
  memset(w, 0, sizeof(*w));
}
static void entry_finish(reader *r) {
  entry_work *w = &r->work;
  exr_opds_entry *e;
  if (r->status == EXR_OK && (w->title || w->download || w->detail)) {
    if (r->feed->entry_count == OPDS_MAX_ENTRIES) fail(r, EXR_LIMIT, "OPDS feed exceeds 4096 entries");
    else if (!exr_grow((void **)&r->feed->entries, &r->capacity, r->feed->entry_count + 1, sizeof(*e)))
      fail(r, EXR_MEMORY, "OPDS entries allocation failed");
    else {
      e = &r->feed->entries[r->feed->entry_count++];
      e->title = w->title; e->author = w->author;
      e->summary = w->summary ? w->summary : w->content;
      if (w->summary) free(w->content);
      e->cover_url = w->cover ? w->cover : w->thumb;
      if (w->cover) free(w->thumb);
      e->download_url = w->download; e->format = w->format; e->detail_url = w->detail; e->size = w->size;
      memset(w, 0, sizeof(*w));
    }
  }
  entry_free(w);
  r->in_entry = 0;
}
static void XMLCALL start(void *context, const char *name, const char **a) {
  reader *r = context;
  r->depth++;
  if (r->status != EXR_OK) return;
  if (r->depth > OPDS_MAX_DEPTH) { fail(r, EXR_LIMIT, "OPDS nesting exceeds 64"); return; }
  if (r->kind != CAP_NONE) {
    if (r->depth > r->cap_depth && r->text.size && r->text.data[r->text.size - 1] != '\n' &&
        !exr_append(&r->text, "\n", 1)) fail(r, EXR_MEMORY, "OPDS text allocation failed");
    return;
  }
  if (r->depth == 1) {
    if (!atom(name, "feed")) fail(r, EXR_FORMAT, "Not an OPDS/Atom feed (root element is not atom:feed)");
    return;
  }
  if (r->depth == 2) {
    if (atom(name, "entry")) { r->in_entry = 1; memset(&r->work, 0, sizeof(r->work)); }
    else if (atom(name, "title")) { r->kind = CAP_FEED_TITLE; r->cap_depth = 2; r->text.size = 0; }
    else if (atom(name, "link")) feed_link(r, a);
    return;
  }
  if (!r->in_entry) return;
  if (r->depth == 3) {
    if (atom(name, "title")) { r->kind = CAP_TITLE; }
    else if (atom(name, "summary")) { r->kind = CAP_SUMMARY; }
    else if (atom(name, "content")) { r->kind = CAP_CONTENT; }
    else if (atom(name, "link")) { entry_link(r, a); return; }
    else if (atom(name, "author")) { r->in_author = 1; return; }
    if (r->kind != CAP_NONE) { r->cap_depth = 3; r->text.size = 0; }
  } else if (r->depth == 4 && r->in_author && atom(name, "name")) {
    r->kind = CAP_AUTHOR; r->cap_depth = 4; r->text.size = 0;
  }
}
static void commit(reader *r) {
  char *s, *t;
  size_t n = r->text.size, lead = 0;
  if (!r->text.data) return;
  while (n && isspace((unsigned char)r->text.data[n - 1])) n--;
  while (lead < n && isspace((unsigned char)r->text.data[lead])) lead++;
  if (n == lead) return;
  s = exr_copy(r->text.data + lead, n - lead);
  if (!s) { fail(r, EXR_MEMORY, "OPDS text allocation failed"); return; }
  switch (r->kind) {
    case CAP_FEED_TITLE: if (!r->feed->title) { r->feed->title = s; return; } break;
    case CAP_TITLE: if (!r->work.title) { r->work.title = s; return; } break;
    case CAP_SUMMARY: if (!r->work.summary) { r->work.summary = s; return; } break;
    case CAP_CONTENT: if (!r->work.content) { r->work.content = s; return; } break;
    case CAP_AUTHOR:
      if (!r->work.author) { r->work.author = s; return; }
      t = malloc(strlen(r->work.author) + strlen(s) + 3);
      if (!t) { free(s); fail(r, EXR_MEMORY, "OPDS author allocation failed"); return; }
      sprintf(t, "%s, %s", r->work.author, s);
      put(&r->work.author, t);
      break;
    default: break;
  }
  free(s);
}
static void XMLCALL end(void *context, const char *name) {
  reader *r = context;
  (void)name;
  if (r->status == EXR_OK) {
    if (r->kind != CAP_NONE && r->depth == r->cap_depth) { commit(r); r->kind = CAP_NONE; }
    else if (r->kind == CAP_NONE) {
      if (r->depth == 3 && r->in_author) r->in_author = 0;
      else if (r->depth == 2 && r->in_entry) entry_finish(r);
    }
  }
  r->depth--;
}
static void XMLCALL chars(void *context, const char *s, int n) {
  reader *r = context;
  if (r->kind == CAP_NONE || r->status != EXR_OK) return;
  if (r->text.size + (size_t)n > OPDS_MAX_TEXT) return; /* longer text is cut, not an error */
  if (!exr_append(&r->text, s, (size_t)n)) fail(r, EXR_MEMORY, "OPDS text allocation failed");
}
void exr_opds_feed_free(exr_opds_feed *f) {
  if (!f) return;
  for (size_t i = 0; i < f->entry_count; i++) {
    exr_opds_entry *e = &f->entries[i];
    free(e->title); free(e->author); free(e->summary); free(e->cover_url);
    free(e->download_url); free(e->format); free(e->detail_url);
  }
  free(f->entries); free(f->title); free(f->next_url); free(f->search_template); free(f->search_description_url);
  memset(f, 0, sizeof(*f));
}
static XML_Parser new_parser(reader *r) {
  XML_Parser p = XML_ParserCreateNS(NULL, '|');
  if (p) {
    r->parser = p;
    XML_SetUserData(p, r);
    XML_SetElementHandler(p, start, end);
    XML_SetCharacterDataHandler(p, chars);
  }
  return p;
}
static exr_status run(reader *r, const void *data, size_t size) {
  enum XML_Status st = XML_STATUS_OK;
  size_t offset = 0;
  while (offset < size && st == XML_STATUS_OK) {
    size_t chunk = size - offset > 65536 ? 65536 : size - offset;
    st = XML_Parse(r->parser, (const char *)data + offset, (int)chunk, 0);
    offset += chunk;
  }
  if (st == XML_STATUS_OK) st = XML_Parse(r->parser, "", 0, 1);
  if (r->status == EXR_OK && st != XML_STATUS_OK)
    r->status = exr_fail(r->error, EXR_FORMAT, "Malformed OPDS XML: %s",
                         XML_ErrorString(XML_GetErrorCode(r->parser)));
  return r->status;
}
exr_status exr_opds_parse(const void *data, size_t size, const char *base, exr_opds_feed *out, exr_error *error) {
  reader r;
  if (out) memset(out, 0, sizeof(*out));
  if (!out || (!data && size)) return exr_fail(error, EXR_ARGUMENT, "Missing OPDS input");
  if (size > OPDS_MAX_INPUT) return exr_fail(error, EXR_LIMIT, "OPDS feed exceeds 16 MiB");
  memset(&r, 0, sizeof(r));
  r.error = error; r.base = base; r.feed = out;
  if (!new_parser(&r)) return exr_fail(error, EXR_MEMORY, "XML parser allocation failed");
  if (run(&r, data, size) != EXR_OK) {
    entry_free(&r.work);
    exr_opds_feed_free(out);
  }
  XML_ParserFree(r.parser);
  free(r.text.data);
  return r.status;
}

/* ---- OpenSearch description ------------------------------------------ */
typedef struct {
  XML_Parser parser;
  exr_status status;
  exr_error *error;
  char *tmpl;
  int opds_profile;
} search_reader;
static void XMLCALL search_start(void *context, const char *name, const char **a) {
  search_reader *s = context;
  const char *type, *tmpl;
  if (s->status != EXR_OK || strcmp(local_name(name), "Url")) return;
  type = attr(a, "type"); tmpl = attr(a, "template");
  if (!tmpl || !has_ci(type, "atom+xml")) return;
  if (!s->tmpl || (!s->opds_profile && has_ci(type, "opds-catalog"))) {
    char *copy = exr_copy(tmpl, strlen(tmpl));
    if (!copy) { s->status = exr_fail(s->error, EXR_MEMORY, "Search template allocation failed"); XML_StopParser(s->parser, XML_FALSE); return; }
    free(s->tmpl);
    s->tmpl = copy;
    s->opds_profile = has_ci(type, "opds-catalog");
  }
}
exr_status exr_opds_parse_search(const void *data, size_t size, const char *base, char **out, exr_error *error) {
  search_reader s;
  enum XML_Status st;
  char *url = NULL;
  exr_status status;
  if (out) *out = NULL;
  if (!out || (!data && size)) return exr_fail(error, EXR_ARGUMENT, "Missing OpenSearch input");
  if (size > OPDS_MAX_INPUT) return exr_fail(error, EXR_LIMIT, "OpenSearch description exceeds 16 MiB");
  memset(&s, 0, sizeof(s));
  s.error = error;
  s.parser = XML_ParserCreateNS(NULL, '|');
  if (!s.parser) return exr_fail(error, EXR_MEMORY, "XML parser allocation failed");
  XML_SetUserData(s.parser, &s);
  XML_SetStartElementHandler(s.parser, search_start);
  st = XML_Parse(s.parser, (const char *)data, (int)size, 1);
  if (s.status == EXR_OK && st != XML_STATUS_OK)
    s.status = exr_fail(error, EXR_FORMAT, "Malformed OpenSearch XML: %s", XML_ErrorString(XML_GetErrorCode(s.parser)));
  XML_ParserFree(s.parser);
  if (s.status != EXR_OK) { free(s.tmpl); return s.status; }
  if (!s.tmpl) return exr_fail(error, EXR_FORMAT, "OpenSearch description has no Atom result template");
  status = exr_opds_resolve_url(base, s.tmpl, &url, error);
  free(s.tmpl);
  if (status == EXR_OK) *out = url;
  return status;
}
