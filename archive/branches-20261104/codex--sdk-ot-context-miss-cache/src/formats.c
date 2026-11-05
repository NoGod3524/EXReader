/* SPDX-License-Identifier: MIT */
#include "formats_internal.h"
#include "graphics_internal.h"
#include <ctype.h>
#include <expat.h>
#include <miniz.h>
uint32_t exr_windows1252(unsigned char c) {
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
static int raw_end(const char *text, size_t size, const char *tag) {
  size_t i, length = strlen(tag);
  unsigned char next;
  if (size < length + 3 || text[0] != '<' || text[1] != '/')
    return 0;
  for (i = 0; i < length; i++)
    if (tolower((unsigned char)text[i + 2]) != tag[i])
      return 0;
  next = (unsigned char)text[length + 2];
  return space(next) || next == '\f' || next == '/' || next == '>';
}
static exr_status html(exr_document *d, const void *data, size_t n, exr_error *e) {
  exr_buffer input = {0}, out = {0};
  exr_status result;
  size_t i = 0;
  unsigned heading = 0;
  char skip[32] = {0};
  const char *raw = NULL;
  result = exr_decode(data, n, &input, e);
  if (result != EXR_OK)
    goto done;
  while (i < input.size) {
    if (raw) {
      if (!raw_end(input.data + i, input.size - i, raw)) {
        i++;
        continue;
      }
      raw = NULL;
    }
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
      if (!closing && (!strcmp(tag, "script") || !strcmp(tag, "style")))
        raw = !strcmp(tag, "script") ? "script" : "style";
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
  mz_zip_archive archive;
  size_t expanded;
  exr_status status;
  const exr_source *source;
  size_t read_bytes;
  exr_error *error;
} archive;
static exr_status archive_backing(archive *z, const exr_document *d, exr_error *e);
static size_t source_read(void *context, mz_uint64 offset, void *buffer, size_t size) {
  archive *z = context;
  size_t done = 0;
  if (offset > z->source->size || size > z->source->size - offset) {
    z->status = exr_fail(z->error, EXR_FORMAT, "ZIP read outside the source");
    return 0;
  }
  if (size > EXR_MAX_INPUT - z->read_bytes) {
    z->status = exr_fail(z->error, EXR_LIMIT, "ZIP source reads exceed 128 MiB");
    return 0;
  }
  while (done < size) {
    z->status = exr_control_poll(&z->source->control, EXR_STAGE_READ, z->read_bytes + done, 0,
                                  z->error);
    if (z->status != EXR_OK) return 0;
    size_t got = z->source->read_at(z->source->context, offset + done,
                                    (unsigned char *)buffer + done, size - done);
    if (!got || got > size - done) {
      z->status = exr_fail(z->error, EXR_IO, "Publication source returned an invalid or short read");
      return 0;
    }
    done += got;
  }
  z->read_bytes += done;
  z->status = exr_control_cancel(&z->source->control, z->error);
  if (z->status != EXR_OK) return 0;
  return done;
}
static int member_info(archive *z,const char *name,mz_zip_archive_file_stat *stat,exr_error *e) {
  int index = mz_zip_reader_locate_file(&z->archive, name, NULL, MZ_ZIP_FLAG_CASE_SENSITIVE);
  if (index < 0 || !mz_zip_reader_file_stat(&z->archive, (mz_uint)index, stat)) {
    z->status = EXR_FORMAT;
    exr_fail(e, EXR_FORMAT, "ZIP member missing: %s", name);
    return -1;
  }
  if (stat->m_uncomp_size > 32 * 1024 * 1024 || stat->m_uncomp_size > EXR_MAX_INPUT - z->expanded ||
      stat->m_is_encrypted) {
    z->status = EXR_LIMIT;
    exr_fail(e, EXR_LIMIT, "ZIP member is encrypted or exceeds extraction limit");
    return -1;
  }
  return index;
}
static void *member(archive *z, const char *name, size_t *size, exr_error *e) {
  mz_zip_archive_file_stat stat;
  int index=member_info(z,name,&stat,e);
  void *p;
  if(index<0) return NULL;
  p = mz_zip_reader_extract_to_heap(&z->archive, (mz_uint)index, size, 0);
  if (!p) {
    if (z->status == EXR_OK) z->status = exr_fail(e, EXR_FORMAT, "ZIP member decompression failed");
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
  char *toc_id;
  item *items;
  size_t count, capacity;
  spine_item *spine;
  size_t spine_count, spine_cap;
  exr_buffer title,language;
  int in_title,in_language,have_language,failed,depth;
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
  if (!strcmp(tag, "spine") && !p->toc_id) {
    a = attribute(attrs, "toc");
    if (a && !(p->toc_id = exr_copy(a, strlen(a)))) p->failed = 1;
  }
  if (!strcmp(tag, "title"))
    p->in_title = 1;
  if(!p->have_language && !strcmp(full,"http://purl.org/dc/elements/1.1/|language")) {
    p->language.size=0; p->in_language=p->depth;
  }
  if (p->failed)
    XML_StopParser(p->parser, XML_FALSE);
}
static void XMLCALL package_end(void *user, const char *tag) {
  package *p = user;
  if (!strcmp(local(tag), "title"))
    p->in_title = 0;
  if(p->in_language==p->depth) {
    size_t first=0,last=p->language.size;
    while(first<last && space((unsigned char)p->language.data[first])) first++;
    while(last>first && space((unsigned char)p->language.data[last-1])) last--;
    if(last>first) { memmove(p->language.data,p->language.data+first,last-first); p->language.size=last-first; p->language.data[p->language.size]=0; p->have_language=1; }
    p->in_language=0;
  }
  p->depth--;
}
static void XMLCALL package_text(void *user, const XML_Char *s, int n) {
  package *p = user;
  if (p->in_title && !exr_append(&p->title, s, (size_t)n)) {
    p->failed = 1;
    XML_StopParser(p->parser, XML_FALSE);
  }
  if(p->in_language && ((size_t)n>4096-p->language.size || !exr_append(&p->language,s,(size_t)n))) {
    p->failed=1; XML_StopParser(p->parser,XML_FALSE);
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
  if (!d->archive && !(d->shared_archive && d->shared_archive->source.read_at))
    return exr_fail(e, EXR_FORMAT, "Resource has no backing data");
  z.status = archive_backing(&z, d, e);
  if (z.status != EXR_OK) return z.status;
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
      (hash && !exr_uri_decode(hash + 1, strlen(hash + 1), fragment)))
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
  for (i = d->chapters[ch].root; i < d->node_count && exr_doc_node(d,i).chapter == ch; i++) {
    exr_node value;const char *id;
    if(d->view) {
      exr_status status=d->view->prepare(d->view->context,i,NULL,e);
      if(status!=EXR_OK) { *resource=*node=SIZE_MAX;return status; }
    }
    value=exr_doc_node(d,i);id=exr_node_attribute(&value, "id");
    if (!id)
      id = exr_node_attribute(&value, "http://www.w3.org/XML/1998/namespace|id");
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
  free(p->toc_id);
  free(p->title.data);
  free(p->language.data);
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
static exr_status archive_backing(archive *z, const exr_document *d, exr_error *e) {
  if (!d->shared_archive || !d->shared_archive->source.read_at)
    return archive_open(z, d->archive, d->archive_size, e);
  z->source = &d->shared_archive->source;
  z->error = e;
  z->archive.m_pRead = source_read;
  z->archive.m_pIO_opaque = z;
  if (!mz_zip_reader_init(&z->archive, z->source->size, 0))
    return z->status != EXR_OK ? z->status : exr_fail(e, EXR_FORMAT, "Invalid ZIP source");
  if (mz_zip_reader_get_num_files(&z->archive) > 10000) {
    mz_zip_reader_end(&z->archive);
    return exr_fail(e, EXR_LIMIT, "Too many ZIP members");
  }
  return EXR_OK;
}
/* Read the original package XML only when a full CFI is requested. */
exr_status exr_epub_package_tree(const exr_document *d,const exr_control *control,exr_document **out,exr_error *e) {
  archive z={0}; package p={0}; void *bytes=NULL; size_t n=0; char path[2048]; exr_status status;
  *out=NULL;
  if(!d || d->format!=EXR_EPUB || (!d->archive && !(d->shared_archive && d->shared_archive->source.read_at)))
    return exr_fail(e,EXR_FORMAT,"Full CFI requires an original EPUB package");
  status=exr_control_cancel(control,e); if(status!=EXR_OK) return status;
  status=archive_backing(&z,d,e); if(status!=EXR_OK) return status;
  bytes=member(&z,"META-INF/container.xml",&n,e); if(!bytes) { status=z.status; goto finish; }
  if(!package_parse(&p,bytes,n) || !p.root || !exr_resolve_path("",p.root,path)) { status=exr_fail(e,EXR_FORMAT,"Invalid CFI container package path"); goto finish; }
  mz_free(bytes); bytes=member(&z,path,&n,e); if(!bytes) { status=z.status; goto finish; }
  status=exr_control_cancel(control,e);
  if(status==EXR_OK) status=exr_xml_memory_tree(bytes,n,"package",out,e);
  if(status==EXR_OK) status=exr_control_cancel(control,e);
finish:
  mz_free(bytes); package_free(&p); mz_zip_reader_end(&z.archive);
  if(status!=EXR_OK) { exr_document_free(*out); *out=NULL; }
  return status;
}
/* Package encryption metadata cannot be dropped while copying encoded resources. */
exr_status exr_epub_export_check(const exr_document *d, exr_error *e) {
  archive z = {0}; exr_status status;
  if (!d->archive && !(d->shared_archive && d->shared_archive->source.read_at)) return EXR_OK;
  status = archive_backing(&z, d, e);
  if (status != EXR_OK) return status;
  if (mz_zip_reader_locate_file(&z.archive, "META-INF/encryption.xml", NULL, 0) >= 0 ||
      mz_zip_reader_locate_file(&z.archive, "META-INF/rights.xml", NULL, 0) >= 0)
    status = exr_fail(e, EXR_FORMAT, "Structured export requires unencrypted, unobfuscated resources");
  mz_zip_reader_end(&z.archive); return status;
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
  d->load_package = exr_epub_package_tree;
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
exr_status exr_xml_resource(const exr_document *index, size_t resource, const char *root_name,
                             exr_document **out, exr_error *e) {
  void *bytes = NULL;
  size_t size = 0;
  exr_document *doc;
  exr_status status;
  *out = NULL;
  if (resource >= index->resource_count) return exr_fail(e, EXR_ARGUMENT, "Invalid XML resource");
  status = exr_document_resource(index, resource, &bytes, &size, e);
  if (status != EXR_OK) return status;
  doc = calloc(1, sizeof(*doc));
  if (!doc) { exr_free(bytes); return exr_fail(e, EXR_MEMORY, "XML tree allocation failed"); }
  doc->format = EXR_EPUB;
  status = resource_copy(doc, &index->resources[resource], e);
  if (status == EXR_OK) status = exr_xml_tree(doc, bytes, size, 0, 0, 0, root_name, e);
  exr_free(bytes);
  if (status != EXR_OK) { exr_document_free(doc); return status; }
  *out = doc;
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
  if(p.have_language) {
    d->language=exr_copy(p.language.data,p.language.size);
    if(!d->language) { result=exr_fail(e,EXR_MEMORY,"Publication language allocation failed"); goto done; }
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
  if (p.toc_id) {
    d->has_ncx = 1; d->ncx_resource = SIZE_MAX;
    for (i = 0; i < d->resource_count; i++)
      if (!strcmp(d->resources[i].id, p.toc_id)) { d->ncx_resource = i; break; }
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
typedef struct {
  archive *archive;
  exr_xml_tree_parser *parser;
  exr_error *error;
  size_t fed,size;
  exr_status status;
} chapter_input;
static size_t chapter_feed(void *context,mz_uint64 offset,const void *data,size_t size) {
  chapter_input *input=context;
  size_t at=0;
  if(offset!=input->fed || size>input->size-input->fed) {
    input->status=exr_fail(input->error,EXR_FORMAT,"Inconsistent chapter extraction extent");return 0;
  }
  while(at<size) {
    size_t chunk=size-at>32768 ? 32768 : size-at;
    if(input->archive->source) {
      input->status=exr_control_poll(&input->archive->source->control,EXR_STAGE_READ,
                                     input->fed,input->size,input->error);
      if(input->status!=EXR_OK) return 0;
    }
    input->status=exr_xml_tree_feed(input->parser,(const char *)data+at,chunk,0);
    if(input->status!=EXR_OK) return 0;
    input->fed+=chunk;at+=chunk;
  }
  return size;
}
static exr_status epub_parse_chapter(exr_document *d, archive *z, size_t resource,
                                     int in_spine, int linear, exr_error *e) {
  mz_zip_archive_file_stat stat;
  int index=member_info(z,d->resources[resource].path,&stat,e);
  chapter_input input={0};
  exr_status result;
  if(index<0) return z->status;
  input.archive=z;input.error=e;input.size=(size_t)stat.m_uncomp_size;
  result=exr_xml_tree_begin(d,resource,in_spine,linear,"html",NULL,NULL,&input.parser,e);
  if(result!=EXR_OK) return result;
  if(!mz_zip_reader_extract_to_callback(&z->archive,(mz_uint)index,chapter_feed,&input,0) ||
     input.fed!=input.size) {
    result=z->status!=EXR_OK ? z->status : input.status!=EXR_OK ? input.status :
      exr_fail(e,EXR_FORMAT,"ZIP member decompression failed");
  } else {
    z->expanded+=input.fed;
    result=exr_xml_tree_feed(input.parser,NULL,0,1);
  }
  exr_xml_tree_free(input.parser);
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
exr_status exr_epub_index_source(const exr_source *source, exr_document **out, exr_error *e) {
  exr_document *d;
  archive z = {0};
  exr_status status;
  *out = NULL;
  if (!source || !source->read_at || !source->size || source->size > EXR_MAX_INPUT)
    return exr_fail(e, source && source->size > EXR_MAX_INPUT ? EXR_LIMIT : EXR_ARGUMENT,
                    "Invalid publication source or size exceeds 128 MiB");
  d = calloc(1, sizeof(*d));
  if (!d) return exr_fail(e, EXR_MEMORY, "Index allocation failed");
  d->shared_archive = calloc(1, sizeof(*d->shared_archive));
  if (!d->shared_archive) { free(d); return exr_fail(e, EXR_MEMORY, "Source allocation failed"); }
  d->format = EXR_EPUB;
  d->shared_archive->refs = 1;
  d->load_package = exr_epub_package_tree;
  d->shared_archive->source = *source;
  d->shared_archive->source.release = NULL; /* Transfer only after public open succeeds. */
  d->archive_size = (size_t)source->size;
  status = archive_backing(&z, d, e);
  if (status == EXR_OK) {
    status = epub_metadata(d, &z, e);
    mz_zip_reader_end(&z.archive);
  }
  if (status != EXR_OK) { exr_document_free(d); return status; }
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
  result = archive_backing(&z, index, e);
  if (result != EXR_OK)
    return result;
  d = calloc(1, sizeof(*d));
  if (!d) {
    mz_zip_reader_end(&z.archive);
    return exr_fail(e, EXR_MEMORY, "Chapter allocation failed");
  }
  d->format = EXR_EPUB;
  d->load_package = index->load_package;
  d->shared_archive = index->shared_archive;
  d->archive = index->archive;
  d->archive_size = index->archive_size;
  d->shared_archive->refs++;
  if(index->language) {
    d->language=exr_copy(index->language,strlen(index->language));
    if(!d->language) { result=exr_fail(e,EXR_MEMORY,"Chapter language allocation failed"); goto done; }
  }
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
typedef struct {
  exr_chapter_feed_fn feed;
  void *context;
  const exr_control *control;
  exr_error *error;
  size_t fed,size;
  exr_status status;
} bounded_chapter_input;
static void *resource_allocate(void *context,size_t count,size_t size);
static void *resource_reallocate(void *context,void *data,size_t count,size_t size);
static void resource_release(void *context,void *data);
static size_t bounded_chapter_feed(void *context,mz_uint64 offset,const void *data,size_t size) {
  bounded_chapter_input *input=context;
  size_t at=0;
  if(offset!=input->fed || size>input->size-input->fed) {
    input->status=exr_fail(input->error,EXR_FORMAT,"Inconsistent streaming chapter extent");return 0;
  }
  while(at<size) {
    size_t chunk=size-at>32768 ? 32768 : size-at;
    input->status=exr_control_poll(input->control,EXR_STAGE_READ,input->fed,input->size,input->error);
    if(input->status==EXR_OK)
      input->status=input->feed(input->context,(const char *)data+at,chunk,0,input->error);
    if(input->status!=EXR_OK) return 0;
    input->fed+=chunk;at+=chunk;
  }
  return size;
}
/* Dedicated streaming entry: the old complete-snapshot member cap is unchanged.
   Streamed chapter input is bounded by the existing total expansion limit and
   the consumer independently budgets all retained parser/index/window memory. */
static exr_status chapter_feed_with_allocator(const exr_document *index,size_t part,
  exr_chapter_feed_fn feed,void *context,const exr_resource_allocator *allocator,
  const exr_control *control,exr_error *e) {
  archive z={0};
  mz_zip_archive_file_stat stat;
  bounded_chapter_input input={0};
  exr_status status;
  int member_index;
  const char *path;
  if(!index || index->format!=EXR_EPUB || !index->shared_archive ||
     part>=index->chapter_count || index->chapters[part].resource>=index->resource_count || !feed)
    return exr_fail(e,EXR_ARGUMENT,"Invalid streaming chapter input");
  if(allocator) {
    if(!allocator->allocate || !allocator->reallocate || !allocator->release)
      return exr_fail(e,EXR_ARGUMENT,"Incomplete chapter source allocator");
    z.archive.m_pAlloc=resource_allocate;z.archive.m_pRealloc=resource_reallocate;
    z.archive.m_pFree=resource_release;z.archive.m_pAlloc_opaque=(void *)allocator;
  }
  status=exr_control_cancel(control,e);if(status!=EXR_OK) return status;
  status=archive_backing(&z,index,e);
  if(status!=EXR_OK) { mz_zip_reader_end(&z.archive);return status; }
  path=index->resources[index->chapters[part].resource].path;
  member_index=mz_zip_reader_locate_file(&z.archive,path,NULL,MZ_ZIP_FLAG_CASE_SENSITIVE);
  if(member_index<0 || !mz_zip_reader_file_stat(&z.archive,(mz_uint)member_index,&stat))
    status=exr_fail(e,EXR_FORMAT,"Streaming chapter member is missing");
  else if(stat.m_is_encrypted || stat.m_uncomp_size>EXR_MAX_INPUT)
    status=exr_fail(e,EXR_LIMIT,"Streaming chapter exceeds total expansion limit");
  else {
    input.feed=feed;input.context=context;input.control=control;input.error=e;
    input.size=(size_t)stat.m_uncomp_size;
    if(!mz_zip_reader_extract_to_callback(&z.archive,(mz_uint)member_index,bounded_chapter_feed,&input,0) ||
       input.fed!=input.size)
      status=z.status!=EXR_OK ? z.status : input.status!=EXR_OK ? input.status :
        exr_fail(e,EXR_FORMAT,"Streaming chapter extraction failed");
    else status=feed(context,NULL,0,1,e);
  }
  mz_zip_reader_end(&z.archive);return status;
}
exr_status exr_epub_chapter_feed(const exr_document *index,size_t part,
  exr_chapter_feed_fn feed,void *context,const exr_control *control,exr_error *e) {
  return chapter_feed_with_allocator(index,part,feed,context,NULL,control,e);
}
exr_status exr_epub_chapter_feed_bounded(const exr_document *index,size_t part,
  exr_chapter_feed_fn feed,void *context,const exr_resource_allocator *allocator,
  const exr_control *control,exr_error *e) {
  if(!allocator) return exr_fail(e,EXR_ARGUMENT,"Missing chapter source allocator");
  return chapter_feed_with_allocator(index,part,feed,context,allocator,control,e);
}
static exr_status docx_member(void *context, const char *path, int optional, void **data,
                                size_t *size, exr_error *e) {
  archive *z = context; *data=NULL; *size=0;
  if(optional && mz_zip_reader_locate_file(&z->archive,path,NULL,0)<0) return EXR_OK;
  *data=member(z,path,size,e); return *data ? EXR_OK : z->status;
}
static exr_status zip_document(exr_document *d, const void *data, size_t n, exr_error *e) {
  archive z = {0};
  exr_chapter *chapters = NULL;
  size_t count = 0, i;
  exr_status result = archive_open(&z, data, n, e);
  if (result != EXR_OK)
    return result;
  if (d->format == EXR_DOCX) {
    result = exr_docx(d, docx_member, &z, e);
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
static exr_status mobi_trailer(exr_mobi_record *record,unsigned flags,exr_error *e) {
  unsigned entries=flags>>1;
  while(entries) {
    if(entries&1) {
      size_t value=0,k; int terminated=0;
      for(k=0;k<4 && k<record->size;k++) {
        unsigned byte=record->data[record->size-k-1]; value|=(size_t)(byte&127)<<(7*k);
        if(byte&128) { terminated=1; break; }
      }
      if(!terminated || value<k+1 || value>record->size) return exr_fail(e,EXR_FORMAT,"Invalid MOBI record trailer");
      record->size-=value;
    }
    entries>>=1;
  }
  if(flags&1) {
    size_t overlap;
    if(!record->size) return exr_fail(e,EXR_FORMAT,"Missing MOBI multibyte trailer");
    overlap=(record->data[record->size-1]&3)+1;
    if(overlap>record->size) return exr_fail(e,EXR_FORMAT,"Invalid MOBI multibyte trailer");
    record->size-=overlap;
  }
  return EXR_OK;
}
static exr_status mobi_palmdoc(const exr_mobi_record *record,exr_buffer *out,exr_error *e) {
  size_t i=0,base=out->size;
  while(i<record->size) {
    unsigned byte=record->data[i++];
    if(byte>=1 && byte<=8) {
      if(byte>record->size-i) return exr_fail(e,EXR_FORMAT,"Truncated PalmDOC literal");
      if(!exr_append(out,record->data+i,byte)) goto limit;
      i+=byte;
    } else if(byte<=127) {
      unsigned char c=(unsigned char)byte; if(!exr_append(out,&c,1)) goto limit;
    } else if(byte>=192) {
      unsigned char pair[2]={' ',(unsigned char)(byte^128)};
      if(!exr_append(out,pair,2)) goto limit;
    } else {
      size_t distance,length,k;
      if(i==record->size) return exr_fail(e,EXR_FORMAT,"Truncated PalmDOC back reference");
      byte=(byte<<8)|record->data[i++]; distance=(byte&16383)>>3; length=(byte&7)+3;
      if(!distance || distance>out->size-base) return exr_fail(e,EXR_FORMAT,"PalmDOC reference leaves its record");
      for(k=0;k<length;k++) { char c=out->data[out->size-distance]; if(!exr_append(out,&c,1)) goto limit; }
    }
  }
  return EXR_OK;
limit:
  return exr_fail(e,EXR_LIMIT,"PalmDOC text exceeds allocation or size limit");
}
static int mobi_header(const exr_mobi_record *record,size_t *size) {
  const unsigned char *h=record->data;
  if(record->size<132 || memcmp(h+16,"MOBI",4) || be16(h+12)) return 0;
  *size=be32(h+20);
  return *size>=116 && *size<=record->size-16;
}
typedef struct { size_t boundary,title_size; const unsigned char *title; uint32_t cover; int has_cover; } mobi_meta;
static exr_status mobi_metadata(const exr_mobi_record *record,size_t header_size,
                                  mobi_meta *meta,exr_error *e) {
  const unsigned char *h=record->data,*s; size_t offset=header_size+16,length,count,at=12,i; int found=0;
  size_t title=be32(h+84),title_size=be32(h+88);
  memset(meta,0,sizeof(*meta)); meta->boundary=meta->cover=UINT32_MAX;
  if(title_size) {
    if(title<offset || title>record->size || title_size>record->size-title) goto bad;
    if(title_size>65536) return exr_fail(e,EXR_LIMIT,"MOBI title exceeds 64 KiB");
    while(title_size && !h[title+title_size-1]) title_size--;
    meta->title=h+title; meta->title_size=title_size;
  }
  if(!(be32(h+128)&64)) return EXR_OK;
  if(record->size-offset<12 || memcmp(h+offset,"EXTH",4)) goto bad;
  s=h+offset; length=be32(s+4); count=be32(s+8);
  if(length<12 || length>record->size-offset || count>(length-12)/8) goto bad;
  if(count>EXR_MAX_NODES) return exr_fail(e,EXR_LIMIT,"MOBI EXTH item limit exceeded");
  for(i=0;i<count;i++) {
    size_t item;
    if(length-at<8 || (item=be32(s+at+4))<8 || item>length-at) goto bad;
    if(be32(s+at)==121) {
      if(found++ || item!=12) goto bad;
      meta->boundary=be32(s+at+8);
    } else if(be32(s+at)==201) {
      uint32_t cover;
      if(item!=12) goto bad;
      cover=be32(s+at+8);
      if(meta->has_cover && meta->cover!=cover) goto bad;
      meta->cover=cover; meta->has_cover=1;
    } else if(be32(s+at)==503) {
      size_t size=item-8;
      if(size>65536) return exr_fail(e,EXR_LIMIT,"MOBI updated title exceeds 64 KiB");
      while(size && !s[at+8+size-1]) size--;
      if(size) { meta->title=s+at+8; meta->title_size=size; }
    }
    at+=item;
  }
  while(at<length) if(s[at++]) goto bad;
  return EXR_OK;
bad:
  return exr_fail(e,EXR_FORMAT,"Invalid MOBI title or EXTH metadata");
}
static exr_status mobi_title(exr_document *d,const mobi_meta *meta,unsigned encoding,exr_error *e) {
  exr_buffer title={0}; size_t i; exr_status status=EXR_OK;
  if(!meta->title_size) return EXR_OK;
  if(encoding==1252) {
    for(i=0;i<meta->title_size;i++) if(!exr_codepoint(&title,exr_windows1252(meta->title[i]))) { status=EXR_LIMIT; goto done; }
  } else if(encoding==65001) {
    if(!exr_append(&title,meta->title,meta->title_size)) { status=EXR_LIMIT; goto done; }
  } else { status=EXR_FORMAT; goto done; }
  if(title.size>65536) { status=EXR_LIMIT; goto done; }
  status=exr_xml_text(title.data,title.size,"MOBI title",e); if(status!=EXR_OK) goto done;
  d->title=exr_model_copy(d,title.data,title.size); if(!d->title) status=EXR_LIMIT;
done:
  free(title.data);
  if(status!=EXR_OK && (!e || !e->message[0])) exr_fail(e,status,"MOBI title decoding failed");
  return status;
}
static exr_status mobi(exr_document *d, const void *data, size_t n, exr_error *e) {
  const unsigned char *s=data,*h; exr_mobi_record *records=NULL;
  const exr_mobi_record *view=NULL,*shared=NULL;
  size_t count,start,stop,i,text_count,header_size,shared_count=0; unsigned compression,encoding,flags=0,title_encoding;
  mobi_meta metadata,prefix;
  exr_mobi_huff *huff=NULL; exr_buffer text={0},utf8={0}; exr_status status=EXR_FORMAT;
  if(n<94 || memcmp(s+60,"BOOKMOBI",8)) return exr_fail(e,EXR_FORMAT,"Not a MOBI container");
  count=be16(s+76);
  if(count<2 || count>(n-78)/8) return exr_fail(e,EXR_FORMAT,"Invalid MOBI record directory");
  records=calloc(count,sizeof(*records)); if(!records) return exr_fail(e,EXR_MEMORY,"MOBI directory allocation failed");
  for(i=0;i<count;i++) {
    start=be32(s+78+i*8); stop=i+1<count ? be32(s+78+(i+1)*8) : n;
    if(start<78+count*8 || start>stop || stop>n) goto done;
    records[i]=(exr_mobi_record){s+start,stop-start};
  }
  view=records; h=view[0].data;
  if(!mobi_header(&view[0],&header_size)) goto done;
  status=mobi_metadata(&view[0],header_size,&metadata,e); if(status!=EXR_OK) goto done;
  title_encoding=be32(h+28);
  if(be32(h+36)<8) {
    start=metadata.boundary;
    if(start!=UINT32_MAX) {
      size_t first=be32(h+108),old_count=be16(h+8);
      status=EXR_FORMAT;
      if(!old_count || old_count>=count || start<=old_count+1 || start>=count ||
         records[start-1].size!=8 || memcmp(records[start-1].data,"BOUNDARY",8)) goto done;
      if(first!=UINT32_MAX) {
        if(first<=old_count || first>start-1) goto done;
        shared=records+first; shared_count=start-1-first;
      }
      view=records+start; count-=start; h=view[0].data;
      if(!mobi_header(&view[0],&header_size) || be32(h+36)!=8) goto done;
      prefix=metadata;
      status=mobi_metadata(&view[0],header_size,&metadata,e); if(status!=EXR_OK) goto done;
      if(!metadata.title_size) { metadata.title=prefix.title; metadata.title_size=prefix.title_size; }
      else title_encoding=be32(h+28);
      if(!metadata.has_cover) { metadata.cover=prefix.cover; metadata.has_cover=prefix.has_cover; }
    }
  }
  status=EXR_FORMAT;
  compression=be16(h); text_count=be16(h+8); encoding=be32(h+28);
  if(be32(h+36)>8) { status=exr_fail(e,EXR_FORMAT,"Unsupported MOBI version"); goto done; }
  if(!text_count || text_count>=count || !be32(h+4) || (encoding!=65001 && encoding!=1252)) goto done;
  if(be32(h+4)>EXR_MAX_TEXT) { status=EXR_LIMIT; goto done; }
  status=mobi_title(d,&metadata,title_encoding,e); if(status!=EXR_OK) goto done;
  status=EXR_FORMAT;
  if(header_size>=228 && be32(h+104)>=5) flags=be16(h+242);
  if(compression==0x4448) {
    size_t first=be32(h+112),number=be32(h+116);
    if(first<=text_count || first>=count || number<2 || number>count-first) goto done;
    status=exr_mobi_huff_open(view+first,number,&huff,e); if(status!=EXR_OK) goto done;
  } else if(compression!=1 && compression!=2) goto done;
  for(i=1;i<=text_count;i++) {
    exr_mobi_record record=view[i]; status=mobi_trailer(&record,flags,e); if(status!=EXR_OK) goto done;
    if(compression==0x4448) status=exr_mobi_huff_decode(huff,record.data,record.size,&text,e);
    else if(compression==2) status=mobi_palmdoc(&record,&text,e);
    else if(!exr_append(&text,record.data,record.size)) status=exr_fail(e,EXR_LIMIT,"MOBI text exceeds allocation or size limit");
    if(status!=EXR_OK) goto done;
  }
  if(be32(h+4)>text.size) { status=EXR_FORMAT; goto done; }
  exr_mobi_huff_free(huff); huff=NULL;
  text.size=be32(h+4); text.data[text.size]=0;
  if(be32(h+36)==8) {
    if(encoding!=65001) { status=exr_fail(e,EXR_FORMAT,"KF8 requires UTF-8 encoding"); goto done; }
    status=exr_kf8(d,view,count,shared,shared_count,text.data,text.size,e);
  } else if(encoding==1252) {
    for(i=0;i<text.size;i++) if(!exr_codepoint(&utf8,exr_windows1252((unsigned char)text.data[i]))) { status=EXR_LIMIT; goto done; }
    status=html(d,utf8.data,utf8.size,e);
  } else status=html(d,text.data,text.size,e);
  if(status==EXR_OK && metadata.cover!=UINT32_MAX)
    status=exr_mobi_cover(d,view,count,shared,shared_count,metadata.cover,e);
done:
  exr_mobi_huff_free(huff); free(records); free(text.data); free(utf8.data);
  if(status!=EXR_OK && (!e || !e->message[0])) exr_fail(e,status,"Invalid or unsupported MOBI stream");
  return status;
}
exr_status exr_parse(exr_document *d, const void *data, size_t n, exr_error *e) {
  switch (d->format) {
  case EXR_TXT:
    return plain(d, data, n, e);
  case EXR_HTML:
    return html(d, data, n, e);
  case EXR_FB2:
    return exr_fb2(d, data, n, e);
  case EXR_DOCX:
  case EXR_EPUB:
    return zip_document(d, data, n, e);
  case EXR_RTF:
    return exr_rtf(d, data, n, e);
  case EXR_MOBI:
    return mobi(d, data, n, e);
  default:
    return exr_fail(e, EXR_FORMAT, "This format has no native decoder yet");
  }
}

exr_status exr_document_open_memory(exr_format f, const void *data, size_t n, exr_document **out,
                                    exr_error *e) {
  exr_document *d;
  exr_status status;
  if (!out)
    return exr_fail(e, EXR_ARGUMENT, "Missing output");
  *out = NULL;
  if (e)
    memset(e, 0, sizeof(*e));
  if (!data || !n || n > EXR_MAX_INPUT)
    return exr_fail(e, n > EXR_MAX_INPUT ? EXR_LIMIT : EXR_ARGUMENT, "Invalid document bytes");
  d = calloc(1, sizeof(*d));
  if (!d)
    return exr_fail(e, EXR_MEMORY, "Allocation failed");
  d->format = f;
  status = exr_parse(d, data, n, e);
  if (status == EXR_OK)
    status = exr_model_finish(d, e);
  if (status != EXR_OK) {
    if (e) {
      e->code = status;
      if (!e->message[0])
        snprintf(e->message, sizeof(e->message), "Native parser failed (%d)", (int)status);
    }
    exr_document_free(d);
    return status;
  }
  if (!d->count && !d->chapter_count) {
    exr_document_free(d);
    return exr_fail(e, EXR_FORMAT, "Document has no supported text content");
  }
  *out = d;
  return exr_fail(e, EXR_OK, "");
}
exr_status exr_document_open(const char *path, exr_document **out, exr_error *e) {
  const char *ext;
  unsigned char *data;
  size_t n;
  exr_status s;
  exr_format f = 0;
  char lower[16];
  size_t i;
  if (!path || !out)
    return exr_fail(e, EXR_ARGUMENT, "Invalid path or output");
  *out = NULL;
  ext = strrchr(path, '.');
  if (!ext)
    return exr_fail(e, EXR_FORMAT, "File has no format extension");
  ext++;
  for (i = 0; ext[i] && i < sizeof(lower) - 1; i++)
    lower[i] = (char)((ext[i] >= 'A' && ext[i] <= 'Z') ? ext[i] + 32 : ext[i]);
  lower[i] = 0;
  if (!strcmp(lower, "txt"))
    f = EXR_TXT;
  else if (!strcmp(lower, "html") || !strcmp(lower, "htm") || !strcmp(lower, "xhtml"))
    f = EXR_HTML;
  else if (!strcmp(lower, "epub"))
    f = EXR_EPUB;
  else if (!strcmp(lower, "fb2"))
    f = EXR_FB2;
  else if (!strcmp(lower, "docx"))
    f = EXR_DOCX;
  else if (!strcmp(lower, "rtf"))
    f = EXR_RTF;
  else if (!strcmp(lower, "mobi") || !strcmp(lower, "azw3") || !strcmp(lower, "azw") ||
           !strcmp(lower, "prc") || !strcmp(lower, "kf8"))
    f = EXR_MOBI;
  else if (!strcmp(lower, "pdf"))
    f = EXR_PDF;
  if (!f)
    return exr_fail(e, EXR_FORMAT, "Unsupported format");
  s = exr_read(path, &data, &n, e);
  if (s != EXR_OK)
    return s;
  s = exr_document_open_memory(f, data, n, out, e);
  free(data);
  return s;
}

static void *resource_allocate(void *context,size_t count,size_t size) {
  const exr_resource_allocator *a=context;
  if(size && count>SIZE_MAX/size) return NULL;
  return a->allocate(a->context,count*size);
}
static void *resource_reallocate(void *context,void *data,size_t count,size_t size) {
  const exr_resource_allocator *a=context;
  if(size && count>SIZE_MAX/size) return NULL;
  return a->reallocate(a->context,data,count*size);
}
static void resource_release(void *context,void *data) {
  const exr_resource_allocator *a=context;
  a->release(a->context,data);
}
exr_status exr_document_resource_bounded(const exr_document *d,size_t resource,
  const exr_resource_allocator *allocator,const exr_control *control,void **out,size_t *size,exr_error *e) {
  archive z={0};
  mz_zip_archive_file_stat stat;
  exr_status status;
  int file;
  if(!out || !size) return exr_fail(e,EXR_ARGUMENT,"Missing bounded resource output");
  *out=NULL;*size=0;
  if(!d || resource>=d->resource_count || !allocator || !allocator->allocate ||
     !allocator->reallocate || !allocator->release) return exr_fail(e,EXR_ARGUMENT,"Invalid bounded resource input");
  status=exr_control_cancel(control,e);if(status!=EXR_OK) return status;
  if(d->resource_data) {
    const exr_resource_data *entry=&d->resource_data[resource];
    if(!entry->bytes) return exr_fail(e,EXR_FORMAT,"Resource has no encoded bytes");
    *out=allocator->allocate(allocator->context,entry->size ? entry->size : 1);
    if(!*out) return exr_fail(e,EXR_MEMORY,"Bounded resource allocation rejected");
    memcpy(*out,entry->bytes,entry->size);*size=entry->size;
    return EXR_OK;
  }
  z.archive.m_pAlloc=resource_allocate;z.archive.m_pRealloc=resource_reallocate;
  z.archive.m_pFree=resource_release;z.archive.m_pAlloc_opaque=(void *)allocator;
  status=archive_backing(&z,d,e);
  if(status!=EXR_OK) { mz_zip_reader_end(&z.archive);return status; }
  file=member_info(&z,d->resources[resource].path,&stat,e);
  if(file<0) { status=z.status;goto done; }
  *size=(size_t)stat.m_uncomp_size;
  *out=allocator->allocate(allocator->context,*size ? *size : 1);
  if(!*out) { status=EXR_MEMORY;goto done; }
  if(!mz_zip_reader_extract_to_mem(&z.archive,(mz_uint)file,*out,*size,0)) {
    status=z.status!=EXR_OK ? z.status : EXR_FORMAT;goto done;
  }
  status=exr_control_cancel(control,e);
done:
  mz_zip_reader_end(&z.archive);
  if(status!=EXR_OK) {
    allocator->release(allocator->context,*out);*out=NULL;*size=0;
    return exr_fail(e,status,"Bounded resource decoding failed");
  }
  return EXR_OK;
}

/* Bounded TXT projection primitive. This deliberately does not construct a
   document or reset a pager at arbitrary source boundaries. */
typedef struct {
  const exr_source *source;
  uint64_t next;
  unsigned char bytes[4096];
  size_t pos, size;
} txt_reader;
static exr_status txt_byte(txt_reader *r, unsigned char *out, int *present, exr_error *e) {
  size_t want, got;
  *present=0;
  if(r->pos==r->size) {
    if(r->next==r->source->size) return EXR_OK;
    if(exr_control_cancel(&r->source->control,e)!=EXR_OK) return EXR_CANCELLED;
    want=(size_t)((r->source->size-r->next)<sizeof(r->bytes) ? r->source->size-r->next : sizeof(r->bytes));
    got=r->source->read_at(r->source->context,r->next,r->bytes,want);
    if(!got || got>want) return exr_fail(e,EXR_IO,"Invalid TXT source read");
    r->next+=got;r->pos=0;r->size=got;
  }
  *out=r->bytes[r->pos++];*present=1;return EXR_OK;
}
static exr_status txt_scalar(txt_reader *r, int endian, uint32_t *cp, int *present, exr_error *e) {
  unsigned char b[4];size_t n=1,i=0;int has;exr_status s;
  s=txt_byte(r,&b[0],present,e);if(s!=EXR_OK || !*present) return s;
  if(endian) {
    s=txt_byte(r,&b[1],&has,e);if(s!=EXR_OK) return s;
    if(!has) return exr_fail(e,EXR_ENCODING,"Truncated UTF-16");
    *cp=endian==1 ? (uint32_t)(b[0]|(b[1]<<8)) : (uint32_t)((b[0]<<8)|b[1]);
    if(*cp>=0xd800 && *cp<=0xdbff) {
      uint32_t lo;
      s=txt_byte(r,&b[2],&has,e);if(s!=EXR_OK) return s;
      if(!has) return exr_fail(e,EXR_ENCODING,"Unpaired UTF-16 surrogate");
      s=txt_byte(r,&b[3],&has,e);if(s!=EXR_OK) return s;
      if(!has) return exr_fail(e,EXR_ENCODING,"Unpaired UTF-16 surrogate");
      lo=endian==1 ? (uint32_t)(b[2]|(b[3]<<8)) : (uint32_t)((b[2]<<8)|b[3]);
      if(lo<0xdc00 || lo>0xdfff) return exr_fail(e,EXR_ENCODING,"Unpaired UTF-16 surrogate");
      *cp=0x10000+((*cp-0xd800)<<10)+(lo-0xdc00);
    } else if(*cp>=0xdc00 && *cp<=0xdfff) return exr_fail(e,EXR_ENCODING,"Unpaired UTF-16 surrogate");
  } else {
    if(b[0]>=0xc0 && b[0]<0xe0) n=2;
    else if(b[0]>=0xe0 && b[0]<0xf0) n=3;
    else if(b[0]>=0xf0 && b[0]<0xf8) n=4;
    for(i=1;i<n;i++) {
      s=txt_byte(r,&b[i],&has,e);if(s!=EXR_OK) return s;
      if(!has) return exr_fail(e,EXR_ENCODING,"Truncated UTF-8");
    }
    i=0;if(!exr_next((const char *)b,n,&i,cp) || i!=n) return exr_fail(e,EXR_ENCODING,"Invalid UTF-8");
  }
  if(!*cp) return exr_fail(e,EXR_ENCODING,"NUL is not text");
  return EXR_OK;
}
struct exr_txt_cursor {
  exr_source source;
  txt_reader reader;
  exr_buffer line;
  uint64_t extent;
  int endian, cr, finished, failed;
};
exr_status exr_txt_cursor_create(const exr_source *source,exr_txt_cursor **out,exr_error *e) {
  exr_txt_cursor *c;unsigned char prefix[3];size_t count=0;int has;exr_status s;
  if(out) *out=NULL;
  if(!out || !source || !source->read_at) return exr_fail(e,EXR_ARGUMENT,"Invalid TXT cursor arguments");
  c=calloc(1,sizeof(*c));if(!c) return exr_fail(e,EXR_MEMORY,"TXT cursor allocation failed");
  c->source=*source;c->reader.source=&c->source;
  while(count<3 && count<source->size) {
    s=txt_byte(&c->reader,&prefix[count],&has,e);if(s!=EXR_OK) { free(c);return s; } count++;
  }
  c->reader.next=0;c->reader.pos=c->reader.size=0;
  if(count>=2 && prefix[0]==0xff && prefix[1]==0xfe) { c->endian=1;c->reader.next=2; }
  else if(count>=2 && prefix[0]==0xfe && prefix[1]==0xff) { c->endian=2;c->reader.next=2; }
  else if(count>=3 && prefix[0]==0xef && prefix[1]==0xbb && prefix[2]==0xbf) c->reader.next=3;
  *out=c;return EXR_OK;
}
exr_status exr_txt_cursor_next(exr_txt_cursor *c,uint64_t *offset,const char **text,size_t *size,exr_error *e) {
  uint32_t cp;int has;exr_status s;size_t start,end;
  if(offset) *offset=0;
  if(text) *text=NULL;
  if(size) *size=0;
  if(!c || !offset || !text || !size || c->failed) return exr_fail(e,EXR_ARGUMENT,"Invalid TXT cursor");
  if(c->finished) return EXR_OK;
  c->line.size=0;if(c->line.data) c->line.data[0]=0;
  for(;;) {
    s=txt_scalar(&c->reader,c->endian,&cp,&has,e);
    if(s!=EXR_OK) goto fail;
    if(!has) { c->finished=1;s=exr_control_cancel(&c->source.control,e);if(s!=EXR_OK) goto fail; }
    if(has && cp=='\n' && c->cr) { c->cr=0;continue; }
    if(has) c->cr=cp=='\r';
    if(!has || cp=='\r' || cp=='\n') {
      start=0;end=c->line.size;
      while(start<end && (c->line.data[start]==' ' || c->line.data[start]=='\t')) start++;
      while(end>start && (c->line.data[end-1]==' ' || c->line.data[end-1]=='\t')) end--;
      if(end>start) {
        uint64_t at=c->extent ? c->extent+1 : 0;
        if(at<c->extent || end-start>UINT64_MAX-at) { s=exr_fail(e,EXR_LIMIT,"TXT extent overflow");goto fail; }
        *offset=at;*text=c->line.data+start;*size=end-start;c->extent=at+*size;return EXR_OK;
      }
      c->line.size=0;if(c->line.data) c->line.data[0]=0;
      if(!has) return EXR_OK;
    } else {
      size_t n=cp<0x80 ? 1u : cp<0x800 ? 2u : cp<0x10000 ? 3u : 4u;
      if(c->line.size>65536-n) { s=exr_fail(e,EXR_LIMIT,"TXT paragraph exceeds scan budget");goto fail; }
      if(!exr_codepoint(&c->line,cp)) { s=exr_fail(e,EXR_MEMORY,"TXT paragraph allocation failed");goto fail; }
    }
  }
fail: c->failed=1;return s;
}
exr_status exr_txt_cursor_checkpoint(const exr_txt_cursor *c,exr_txt_checkpoint *point,exr_error *e) {
  if(!c || !point || c->failed) return exr_fail(e,EXR_ARGUMENT,"Invalid TXT checkpoint");
  point->source_offset=c->reader.next-(c->reader.size-c->reader.pos);
  point->projection_offset=c->extent;point->encoding=(unsigned)c->endian;point->pending_cr=(unsigned)c->cr;
  return EXR_OK;
}
exr_status exr_txt_cursor_restore(exr_txt_cursor *c,const exr_txt_checkpoint *point,exr_error *e) {
  if(!c || !point || point->source_offset>c->source.size || point->encoding!=(unsigned)c->endian || point->pending_cr>1)
    return exr_fail(e,EXR_ARGUMENT,"Invalid TXT checkpoint");
  c->reader.next=point->source_offset;c->reader.pos=c->reader.size=0;
  c->extent=point->projection_offset;c->cr=(int)point->pending_cr;c->finished=c->failed=0;
  c->line.size=0;return EXR_OK;
}
void exr_txt_cursor_free(exr_txt_cursor *c) { if(c) { free(c->line.data);free(c); } }
exr_status exr_txt_scan_source(const exr_source *source,exr_txt_paragraph_fn emit,void *context,
                               uint64_t *extent,exr_error *e) {
  exr_txt_cursor *c=NULL;uint64_t offset;const char *text;size_t size;exr_status s;
  if(extent) *extent=0;
  if(!source || !emit || !extent) return exr_fail(e,EXR_ARGUMENT,"Invalid TXT scan arguments");
  s=exr_txt_cursor_create(source,&c,e);if(s!=EXR_OK) return s;
  while((s=exr_txt_cursor_next(c,&offset,&text,&size,e))==EXR_OK && text) {
    s=emit(context,offset,text,size,e);if(s!=EXR_OK) break;
  }
  if(s==EXR_OK) *extent=c->extent;
  exr_txt_cursor_free(c);return s;
}

typedef struct {
  const char *query;size_t length, matched;const uint32_t *prefix;
  uint64_t from,start,end;int found;
} txt_search;
static void txt_match_byte(txt_search *search,unsigned char byte,uint64_t offset) {
  if(search->found || offset<search->from) return;
  while(search->matched && byte!=(unsigned char)search->query[search->matched])
    search->matched=search->prefix[search->matched-1];
  if(byte==(unsigned char)search->query[search->matched]) search->matched++;
  if(search->matched==search->length) {
    search->end=offset+1;search->start=search->end-search->length;search->found=1;
  }
}
static exr_status txt_search_paragraph(void *context,uint64_t offset,const char *text,size_t size,exr_error *e) {
  txt_search *search=context;size_t i;(void)e;
  if(offset) txt_match_byte(search,'\n',offset-1);
  for(i=0;i<size;i++) txt_match_byte(search,(unsigned char)text[i],offset+i);
  return EXR_OK;
}
exr_status exr_txt_find_source(const exr_source *source,const char *query,uint64_t from,
                               uint64_t *start,uint64_t *end,exr_error *e) {
  txt_search search={0};uint32_t *prefix=NULL,cp;size_t at=0,n;uint64_t extent=0;exr_status s;
  if(start) *start=UINT64_MAX;
  if(end) *end=UINT64_MAX;
  if(!source || !query || !start || !end || !(n=strlen(query))) return exr_fail(e,EXR_ARGUMENT,"Invalid TXT search arguments");
  if(n>1024*1024) return exr_fail(e,EXR_LIMIT,"Search query exceeds 1 MiB");
  while(at<n) {
    if(!(at&4095) && exr_control_cancel(&source->control,e)!=EXR_OK) return EXR_CANCELLED;
    if(!exr_next(query,n,&at,&cp)) return exr_fail(e,EXR_ENCODING,"Invalid query UTF-8");
  }
  s=exr_kmp_prefix(query,n,&source->control,&prefix,e);if(s!=EXR_OK) return s;
  search.query=query;search.length=n;search.prefix=prefix;search.from=from;
  s=exr_txt_scan_source(source,txt_search_paragraph,&search,&extent,e);
  free(prefix);
  if(s!=EXR_OK) return s;
  if(from>extent) return exr_fail(e,EXR_ARGUMENT,"TXT search offset beyond extent");
  if(search.found) { *start=search.start;*end=search.end; }
  return EXR_OK;
}

typedef struct {
  uint64_t first,last;
  char *data;
  size_t size;
} txt_anchor_window;
static void txt_anchor_copy(txt_anchor_window *w,uint64_t offset,const char *text,size_t size) {
  uint64_t end=offset+size,lo=offset>w->first ? offset : w->first;
  uint64_t hi=end<w->last ? end : w->last;
  if(lo<hi) { memcpy(w->data+w->size,text+(size_t)(lo-offset),(size_t)(hi-lo));w->size+=(size_t)(hi-lo); }
}
static exr_status txt_anchor_paragraph(void *context,uint64_t offset,const char *text,size_t size,exr_error *e) {
  txt_anchor_window *w=context;(void)e;
  if(offset) txt_anchor_copy(w,offset-1,"\n",1);
  txt_anchor_copy(w,offset,text,size);return EXR_OK;
}
exr_status exr_txt_anchor_create_source(const exr_source *source,size_t start,size_t end,
                                         exr_anchor *anchor,exr_error *e) {
  txt_anchor_window w={0};exr_document doc={0};uint64_t extent=0;size_t skip=0,base,finish;
  exr_status status;
  if(!anchor) return exr_fail(e,EXR_ARGUMENT,"Missing anchor output");
  memset(anchor,0,sizeof(*anchor));
  if(!source || start>end) return exr_fail(e,EXR_ARGUMENT,"Invalid TXT anchor range");
  if(end-start>65536) return exr_fail(e,EXR_LIMIT,"Anchor quote exceeds 64 KiB");
  w.first=start>128 ? start-128 : 0;
  w.last=(uint64_t)end>UINT64_MAX-128 ? UINT64_MAX : (uint64_t)end+128;
  w.data=malloc((end-start)+257);
  if(!w.data) return exr_fail(e,EXR_MEMORY,"TXT anchor allocation failed");
  status=exr_txt_scan_source(source,txt_anchor_paragraph,&w,&extent,e);
  if(status!=EXR_OK) goto done;
  if((uint64_t)end>extent) { status=exr_fail(e,EXR_ARGUMENT,"TXT anchor range beyond extent");goto done; }
  while(skip<w.size && ((unsigned char)w.data[skip]&0xc0)==0x80) skip++;
  base=(size_t)w.first+skip;finish=w.size;
  /* The bounded right edge may cut a scalar. Keep complete final scalars. */
  if(w.last<extent) {
    size_t at=skip,previous;uint32_t cp;
    while(at<finish) { previous=at;if(!exr_next(w.data,finish,&at,&cp)) { finish=previous;break; } }
  }
  if(start<base || end<base || end-base>finish-skip) { status=exr_fail(e,EXR_ARGUMENT,"TXT anchor range is not on UTF-8 boundaries");goto done; }
  doc.text=w.data+skip;doc.size=finish-skip;
  status=exr_anchor_create(&doc,start-base,end-base,anchor,e);
  if(status==EXR_OK) { anchor->start=start;anchor->end=end; }
done:
  free(w.data);return status;
}

/* Bounded selector resolution: three KMP patterns visit the normalized
   projection once. The source is still scanned to EOF after a match. */
typedef struct {
  char *text;
  uint32_t *prefix;
  size_t size, matched;
} txt_resolve_pattern;
typedef struct {
  txt_resolve_pattern left,right,full;
  size_t quote,prefix,suffix;
  uint64_t best,left_last,right_last;
  unsigned score;
  int tied,has_left,has_right;
} txt_resolve_state;

static exr_status txt_resolve_prepare(txt_resolve_pattern *p,
  const char *a,size_t na,const char *b,size_t nb,const char *c,size_t nc,
  const exr_control *control,exr_error *e) {
  exr_status status;
  p->size=na+nb+nc;
  if(!p->size) return EXR_OK;
  p->text=malloc(p->size);
  if(!p->text) return exr_fail(e,EXR_MEMORY,"TXT selector allocation failed");
  if(na) memcpy(p->text,a,na);
  if(nb) memcpy(p->text+na,b,nb);
  if(nc) memcpy(p->text+na+nb,c,nc);
  status=exr_kmp_prefix(p->text,p->size,control,&p->prefix,e);
  return status;
}
static void txt_resolve_pattern_free(txt_resolve_pattern *p) {
  free(p->text);free(p->prefix);
}
static int txt_resolve_feed_pattern(txt_resolve_pattern *p,unsigned char byte) {
  if(!p->size) return 0;
  while(p->matched && byte!=(unsigned char)p->text[p->matched])
    p->matched=p->prefix[p->matched-1];
  if(byte==(unsigned char)p->text[p->matched]) p->matched++;
  if(p->matched==p->size) {
    p->matched=p->prefix[p->matched-1];
    return 1;
  }
  return 0;
}
static void txt_resolve_candidate(txt_resolve_state *s,uint64_t start,unsigned score) {
  if(score>s->score) { s->score=score;s->best=start;s->tied=0; }
  else if(score==s->score && start!=s->best) s->tied=1;
}
static void txt_resolve_byte(txt_resolve_state *s,unsigned char byte,uint64_t at) {
  uint64_t end=at+1,start;
  if(txt_resolve_feed_pattern(&s->left,byte)) {
    start=end-s->quote;
    s->left_last=start;s->has_left=1;
    if(s->prefix || start==0) txt_resolve_candidate(s,start,1);
  }
  if(txt_resolve_feed_pattern(&s->right,byte)) {
    start=end-s->quote-s->suffix;
    if(s->suffix) txt_resolve_candidate(s,start,!s->prefix && start==0 ? 2:1);
    else { s->right_last=start;s->has_right=1; }
  }
  if(txt_resolve_feed_pattern(&s->full,byte)) {
    start=end-s->quote-s->suffix;
    txt_resolve_candidate(s,start,2);
  }
}
static exr_status txt_resolve_paragraph(void *context,uint64_t offset,const char *text,size_t size,exr_error *e) {
  txt_resolve_state *s=context;(void)e;
  if(offset) txt_resolve_byte(s,'\n',offset-1);
  for(size_t i=0;i<size;i++) txt_resolve_byte(s,(unsigned char)text[i],offset+i);
  return EXR_OK;
}
exr_status exr_txt_anchor_resolve_source(const exr_source *source,const exr_anchor *anchor,
  exr_anchor_match *match,exr_error *e) {
  txt_resolve_state s={0};uint64_t extent=0;exr_status status;
  if(!match) return exr_fail(e,EXR_ARGUMENT,"Missing anchor match output");
  match->state=EXR_ANCHOR_MISSING;match->start=match->end=SIZE_MAX;
  if(!source || !anchor) return exr_fail(e,EXR_ARGUMENT,"Missing source or anchor");
  status=exr_anchor_validate(anchor,e);if(status!=EXR_OK) return status;
  status=exr_control_cancel(&source->control,e);if(status!=EXR_OK) return status;
  if(!anchor->exact) { match->state=EXR_ANCHOR_LEGACY;return exr_fail(e,EXR_OK,""); }
  if(anchor->chapter && anchor->chapter[0]) return exr_fail(e,EXR_OK,"");
  s.quote=strlen(anchor->exact);
  s.prefix=anchor->prefix?strlen(anchor->prefix):0;
  s.suffix=anchor->suffix?strlen(anchor->suffix):0;
  status=txt_resolve_prepare(&s.left,anchor->prefix,s.prefix,anchor->exact,s.quote,NULL,0,&source->control,e);
  if(status!=EXR_OK) goto done;
  status=txt_resolve_prepare(&s.right,anchor->exact,s.quote,anchor->suffix,s.suffix,NULL,0,&source->control,e);
  if(status!=EXR_OK) goto done;
  if(s.prefix && s.suffix) {
    status=txt_resolve_prepare(&s.full,anchor->prefix,s.prefix,anchor->exact,s.quote,anchor->suffix,s.suffix,&source->control,e);
    if(status!=EXR_OK) goto done;
  }
  if(!s.quote && !s.prefix && s.suffix) txt_resolve_candidate(&s,0,1);
  status=exr_txt_scan_source(source,txt_resolve_paragraph,&s,&extent,e);
  if(status!=EXR_OK) goto done;
  if(!s.quote && !s.prefix && !s.suffix) {
    if(!extent) txt_resolve_candidate(&s,0,2);
  } else if(!s.suffix) {
    uint64_t start=UINT64_MAX;
    if(!s.quote) start=extent;
    else if(s.has_right && s.right_last<=extent && s.quote==extent-s.right_last) start=s.right_last;
    if(start!=UINT64_MAX) {
      unsigned score=1;
      if(s.prefix ? s.has_left && s.left_last==start : start==0) score=2;
      txt_resolve_candidate(&s,start,score);
    }
  }
  if(s.score) {
    match->state=s.tied?EXR_ANCHOR_AMBIGUOUS:EXR_ANCHOR_FOUND;
    if(!s.tied) {
      if(s.best>SIZE_MAX || s.quote>SIZE_MAX-(size_t)s.best) {
        match->state=EXR_ANCHOR_MISSING;
        status=exr_fail(e,EXR_LIMIT,"TXT anchor offset exceeds platform range");goto done;
      }
      match->start=(size_t)s.best;match->end=(size_t)s.best+s.quote;
    }
  }
  status=exr_fail(e,EXR_OK,"");
done:
  txt_resolve_pattern_free(&s.left);txt_resolve_pattern_free(&s.right);txt_resolve_pattern_free(&s.full);
  return status;
}
