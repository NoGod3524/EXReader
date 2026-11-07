/* SPDX-License-Identifier: MIT */
#include "layout_internal.h"
#include "hyphen_internal.h"
#include <ctype.h>

struct exr_publication {
  char *title;
  exr_part *parts;
  size_t count, refs;
  exr_part_load_fn load;
  void *context;
  exr_context_release_fn release;
  exr_navigation *navigation;
  size_t navigation_count, metadata_bytes;
  int navigation_ready, busy;
};
typedef struct {
  size_t part, bytes;
  exr_document *document;
  exr_layout *layout;
} cached_part;
struct exr_session {
  exr_publication *publication;
  exr_font *font;
  exr_hyphenator *hyphenator;
  exr_layout_config config;
  cached_part *cache; /* Most recently used first, at most 64 entries. */
  size_t count, capacity, bytes, budget;
  int busy;
};

static exr_status copy_string(const char *source, size_t limit, size_t *total,
                               const char **out, exr_error *e) {
  size_t n = 0, at = 0;
  uint32_t cp;
  *out = NULL;
  if (!source)
    source = "";
  while (n <= limit && source[n])
    n++;
  if (n > limit || n >= EXR_MAX_TEXT - *total)
    return exr_fail(e, EXR_LIMIT, "Publication metadata or CSS exceeds limit");
  while (at < n)
    if (!exr_next(source, n, &at, &cp))
      return exr_fail(e, EXR_ENCODING, "Publication metadata or CSS is not UTF-8");
  *out = exr_copy(source, n);
  if (!*out)
    return exr_fail(e, EXR_MEMORY, "Publication string allocation failed");
  *total += n + 1;
  return EXR_OK;
}

void exr_publication_free(exr_publication *p) {
  size_t i;
  if (!p || --p->refs)
    return;
  if (p->release)
    p->release(p->context);
  for (i = 0; i < p->count; i++) {
    free((void *)p->parts[i].id);
    free((void *)p->parts[i].path);
    free((void *)p->parts[i].title);
  }
  free(p->parts);
  exr_navigation_free(p->navigation, p->navigation_count);
  free(p->title);
  free(p);
}

exr_status exr_publication_create(const exr_publication_input *input,
                                  exr_publication **out, exr_error *e) {
  exr_publication *p;
  exr_status status;
  const char *title;
  size_t i, total = 0;
  if (!out)
    return exr_fail(e, EXR_ARGUMENT, "Missing publication output");
  *out = NULL;
  if (!input || !input->load || !input->parts || !input->part_count)
    return exr_fail(e, EXR_ARGUMENT, "Missing publication directory or loader");
  if (input->navigation_count && !input->navigation)
    return exr_fail(e, EXR_ARGUMENT, "Missing publication navigation array");
  if (input->navigation_count > 10000)
    return exr_fail(e, EXR_LIMIT, "Navigation exceeds 10000 entries");
  if (input->part_count > 10000)
    return exr_fail(e, EXR_LIMIT, "Publication exceeds 10000 parts");
  p = calloc(1, sizeof(*p));
  if (!p)
    return exr_fail(e, EXR_MEMORY, "Publication allocation failed");
  p->refs = 1;
  p->parts = calloc(input->part_count, sizeof(*p->parts));
  if (!p->parts) {
    exr_publication_free(p);
    return exr_fail(e, EXR_MEMORY, "Publication directory allocation failed");
  }
  p->count = input->part_count;
  status = copy_string(input->title, 65536, &total, &title, e);
  p->title = (char *)title;
  for (i = 0; status == EXR_OK && i < p->count; i++) {
    exr_part *part = &p->parts[i];
    const exr_part *source = &input->parts[i];
    status = copy_string(source->id, 65536, &total, &part->id, e);
    if (status == EXR_OK)
      status = copy_string(source->path, 2046, &total, &part->path, e);
    if (status == EXR_OK)
      status = copy_string(source->title, 65536, &total, &part->title, e);
    part->in_reading_order = source->in_reading_order != 0;
  }
  if (status == EXR_OK && input->navigation_count) {
    p->navigation = calloc(input->navigation_count, sizeof(*p->navigation));
    if (!p->navigation) status = exr_fail(e, EXR_MEMORY, "Navigation allocation failed");
    else p->navigation_count = input->navigation_count;
  }
  for (i = 0; status == EXR_OK && i < p->navigation_count; i++) {
    const exr_navigation *source = &input->navigation[i];
    exr_navigation *v = &p->navigation[i];
    if ((source->parent != SIZE_MAX && source->parent >= i) ||
        (source->part != SIZE_MAX && source->part >= p->count)) {
      status = exr_fail(e, EXR_ARGUMENT, "Invalid navigation parent or part");
      break;
    }
    v->parent = source->parent; v->part = source->part;
    status = copy_string(source->label, 65536, &total, &v->label, e);
    if (status == EXR_OK) status = copy_string(source->href, 2046, &total, &v->href, e);
    if (status == EXR_OK) status = copy_string(source->base, 2046, &total, &v->base, e);
    if (status == EXR_OK) status = copy_string(source->role, 256, &total, &v->role, e);
  }
  if (status != EXR_OK) {
    exr_publication_free(p);
    return status;
  }
  p->load = input->load;
  p->context = input->context;
  p->release = input->release;
  p->metadata_bytes = total;
  p->navigation_ready = 1;
  *out = p;
  return exr_fail(e, EXR_OK, "");
}

static exr_status epub_load(void *context, size_t part, exr_document **out, exr_error *e) {
  return exr_epub_load(context, part, out, e);
}
static void epub_release(void *context) { exr_document_free(context); }
exr_status exr_publication_retain_epub(exr_publication *p,const exr_document **index,exr_error *e) {
  if(!p || !index || p->load!=epub_load)
    return exr_fail(e,EXR_UNSUPPORTED,"Chapter windows require an EPUB publication");
  if(p->refs==SIZE_MAX) return exr_fail(e,EXR_LIMIT,"Too many publication references");
  p->refs++;*index=p->context;return EXR_OK;
}

static exr_status publication_index(exr_document *index, exr_publication **out, exr_error *e) {
  exr_part *parts;
  exr_publication_input input = {0};
  exr_status status;
  size_t i;
  parts = calloc(index->chapter_count, sizeof(*parts));
  if (!parts) {
    exr_document_free(index);
    return exr_fail(e, EXR_MEMORY, "Publication directory allocation failed");
  }
  for (i = 0; i < index->chapter_count; i++) {
    parts[i].id = index->chapters[i].id;
    parts[i].path = index->chapters[i].path;
    parts[i].in_reading_order = index->chapters[i].in_spine && index->chapters[i].linear;
  }
  input.title = exr_document_title(index);
  input.parts = parts;
  input.part_count = index->chapter_count;
  input.load = epub_load;
  input.context = index;
  input.release = epub_release;
  status = exr_publication_create(&input, out, e);
  if (status == EXR_OK) (*out)->navigation_ready = 0;
  free(parts);
  if (status != EXR_OK)
    exr_document_free(index);
  return status;
}
exr_status exr_publication_open_memory(exr_format format, const void *data, size_t size,
                                       exr_publication **out, exr_error *e) {
  exr_document *index = NULL;
  exr_status status;
  if (!out) return exr_fail(e, EXR_ARGUMENT, "Missing publication output");
  *out = NULL;
  if (format != EXR_EPUB)
    return exr_fail(e, EXR_FORMAT, "Built-in indexed loading currently accepts EPUB");
  status = exr_epub_index(data, size, &index, e);
  return status == EXR_OK ? publication_index(index, out, e) : status;
}
exr_status exr_publication_open_source(const exr_source *source, exr_publication **out, exr_error *e) {
  exr_document *index = NULL;
  exr_status status;
  if (!out) return exr_fail(e, EXR_ARGUMENT, "Missing publication output");
  *out = NULL;
  status = exr_epub_index_source(source, &index, e);
  if (status != EXR_OK) return status;
  status = publication_index(index, out, e);
  if (status == EXR_OK) index->shared_archive->source.release = source->release;
  return status;
}

exr_status exr_publication_open(const char *path, exr_publication **out, exr_error *e) {
  exr_source source = {0};
  exr_status status;
  if (!out)
    return exr_fail(e, EXR_ARGUMENT, "Missing publication output");
  *out = NULL;
  if (!path)
    return exr_fail(e, EXR_ARGUMENT, "Missing publication path");
  status = exr_file_source(path, &source, e);
  if (status != EXR_OK) return status;
  status = exr_publication_open_source(&source, out, e);
  if (status != EXR_OK) source.release(source.context);
  return status;
}
const char *exr_publication_title(const exr_publication *p) { return p ? p->title : ""; }
size_t exr_publication_index_memory(const exr_publication *p) {
  return p ? sizeof(*p)+p->metadata_bytes+p->count*sizeof(*p->parts)+
    p->navigation_count*sizeof(*p->navigation)+exr_document_memory_size(p->context)+sizeof(exr_archive_store) : 0;
}
const exr_part *exr_publication_parts(const exr_publication *p, size_t *count) {
  if (count)
    *count = p ? p->count : 0;
  return p ? p->parts : NULL;
}
exr_status exr_publication_navigation(exr_publication *p, const exr_navigation **out,
                                       size_t *count, exr_error *e) {
  exr_status status;
  if (out) *out = NULL;
  if (count) *count = 0;
  if (!p || !out || !count || p->busy)
    return exr_fail(e, EXR_ARGUMENT, "Invalid or reentrant navigation request");
  if (!p->navigation_ready) {
    exr_navigation *entries = NULL;
    size_t n = 0;
    p->busy = 1;
    status = exr_epub_navigation(p->context, p->metadata_bytes, &entries, &n, e);
    p->busy = 0;
    if (status != EXR_OK) return status;
    p->navigation = entries; p->navigation_count = n; p->navigation_ready = 1;
  }
  *out = p->navigation; *count = p->navigation_count;
  return exr_fail(e, EXR_OK, "");
}
exr_status exr_publication_load(exr_publication *p, size_t part, exr_document **out, exr_error *e) {
  exr_document *doc = NULL;
  exr_status status;
  if (!out)
    return exr_fail(e, EXR_ARGUMENT, "Missing part document output");
  *out = NULL;
  if (!p || part >= p->count || p->busy)
    return exr_fail(e, EXR_ARGUMENT, "Part is outside the publication");
  p->busy = 1;
  status = p->load(p->context, part, &doc, e);
  if (status == EXR_OK && !doc)
    status = exr_fail(e, EXR_FORMAT, "Part loader returned no document");
  if (status != EXR_OK) {
    exr_document_free(doc);
    p->busy = 0;
    return status;
  }
  p->busy = 0;
  *out = doc;
  return exr_fail(e, EXR_OK, "");
}

static exr_status publication_cfi_create(exr_publication *p,size_t part,const exr_document *d,
                                             const exr_cfi_point *point,size_t context,const exr_control *control,char **out,exr_error *e) {
  exr_status status;
  if(out) *out=NULL;
  if(!p || !out || !d || d->chapter_count!=1 || part>=p->count || p->busy || context>32) return exr_fail(e,EXR_ARGUMENT,"Invalid or reentrant publication CFI create");
  if(p->load!=epub_load) return exr_fail(e,EXR_FORMAT,"Publication has no built-in EPUB CFI provider");
  p->busy=1; status=exr_cfi_create_for_part(p->context,part,d,0,point,context,control,out,e); p->busy=0; return status;
}
exr_status exr_publication_cfi_create(exr_publication *p,size_t part,const exr_document *d,
                                        const exr_cfi_point *point,const exr_control *control,char **out,exr_error *e) {
  return publication_cfi_create(p,part,d,point,0,control,out,e);
}
exr_status exr_publication_cfi_create_quoted(exr_publication *p,size_t part,const exr_document *d,
                                               const exr_cfi_point *point,size_t context,const exr_control *control,char **out,exr_error *e) {
  if(!context) { if(out) *out=NULL; return exr_fail(e,EXR_ARGUMENT,"Quoted CFI requires 1..32 context scalars"); }
  return publication_cfi_create(p,part,d,point,context,control,out,e);
}
exr_status exr_publication_cfi_resolve(exr_publication *p,const char *cfi,const exr_control *control,
                                         size_t *part,exr_document **out,exr_cfi_point *point,exr_error *e) {
  exr_status status; exr_document *doc=NULL; exr_cfi_point result; size_t mapped; char *local=NULL;
  if(part) *part=SIZE_MAX;
  if(out) *out=NULL;
  if(point) *point=(exr_cfi_point){SIZE_MAX,SIZE_MAX,0};
  if(!p || !part || !out || !point || p->busy) return exr_fail(e,EXR_ARGUMENT,"Invalid or reentrant publication CFI resolve");
  if(p->load!=epub_load) return exr_fail(e,EXR_FORMAT,"Publication has no built-in EPUB CFI provider");
  p->busy=1; status=exr_cfi_route(p->context,cfi,control,&mapped,&local,e);
  if(status==EXR_OK) status=exr_control_cancel(control,e);
  if(status==EXR_OK) status=p->load(p->context,mapped,&doc,e);
  if(status==EXR_OK) status=exr_document_cfi_path_resolve(doc,0,local,control,&result,e);
  if(status==EXR_OK) { *part=mapped; *out=doc; *point=result; doc=NULL; }
  exr_document_free(doc); free(local); p->busy=0; return status;
}

void exr_session_clear(exr_session *s) {
  size_t i;
  if (!s)
    return;
  for (i = 0; i < s->count; i++) {
    exr_layout_free(s->cache[i].layout);
    exr_document_free(s->cache[i].document);
  }
  s->count = 0;
  s->bytes = 0;
}
void exr_session_free(exr_session *s) {
  if (!s)
    return;
  exr_session_clear(s);
  free(s->cache);
  free((void *)s->config.user_css);
  exr_hyphenator_free(s->hyphenator);
  exr_publication_free(s->publication);
  free(s);
}
size_t exr_session_cached(const exr_session *s) { return s ? s->count : 0; }
size_t exr_session_cached_bytes(const exr_session *s) { return s ? s->bytes : 0; }

static void evict_last(exr_session *s) {
  cached_part *entry = &s->cache[--s->count];
  s->bytes -= entry->bytes;
  exr_layout_free(entry->layout);
  exr_document_free(entry->document);
}
exr_status exr_session_set_budget(exr_session *s, size_t bytes, exr_error *e) {
  if (!s || s->busy)
    return exr_fail(e, EXR_ARGUMENT, "Invalid or reentrant session access");
  s->budget = bytes;
  while (s->budget && s->bytes > s->budget)
    evict_last(s);
  return exr_fail(e, EXR_OK, "");
}
exr_status exr_session_set_hyphenator(exr_session *s,exr_hyphenator *h,exr_error *e) {
  exr_status status;
  if(!s || s->busy) return exr_fail(e,EXR_ARGUMENT,"Invalid or reentrant session access");
  if(h==s->hyphenator) return exr_fail(e,EXR_OK,"");
  if(h) { status=exr_hyphenator_ref(h,e); if(status!=EXR_OK) return status; }
  exr_session_clear(s); exr_hyphenator_free(s->hyphenator); s->hyphenator=h;
  return exr_fail(e,EXR_OK,"");
}

exr_status exr_session_create(exr_publication *p, exr_font *font,
                              const exr_layout_config *config, size_t capacity,
                              exr_session **out, exr_error *e) {
  exr_layout_config defaults = exr_layout_config_defaults();
  exr_status status;
  exr_session *s;
  size_t total = 0;
  if (!out)
    return exr_fail(e, EXR_ARGUMENT, "Missing session output");
  *out = NULL;
  if (!p || !font || !capacity || capacity > 64)
    return exr_fail(e, EXR_ARGUMENT, "Session requires a publication, font and capacity 1..64");
  if (!config)
    config = &defaults;
  status = exr_layout_validate(config, e);
  if (status != EXR_OK)
    return status;
  if (p->refs == SIZE_MAX)
    return exr_fail(e, EXR_LIMIT, "Too many publication references");
  s = calloc(1, sizeof(*s));
  if (!s)
    return exr_fail(e, EXR_MEMORY, "Session allocation failed");
  s->config = *config;
  s->config.user_css = NULL;
  if (config->user_css) {
    status = copy_string(config->user_css, 1024 * 1024, &total, &s->config.user_css, e);
    if (status != EXR_OK) {
      exr_session_free(s);
      return status;
    }
  }
  s->cache = calloc(capacity, sizeof(*s->cache));
  if (!s->cache) {
    exr_session_free(s);
    return exr_fail(e, EXR_MEMORY, "Session cache allocation failed");
  }
  s->capacity = capacity;
  s->font = font;
  s->publication = p;
  p->refs++;
  *out = s;
  return exr_fail(e, EXR_OK, "");
}

exr_status exr_session_get(exr_session *s, size_t part, const exr_document **document,
                           const exr_layout **layout, exr_error *e) {
  cached_part entry = {0};
  exr_status status;
  size_t i, document_bytes, layout_bytes;
  if (document)
    *document = NULL;
  if (layout)
    *layout = NULL;
  if (!s || !document || !layout || part >= s->publication->count || s->busy)
    return exr_fail(e, EXR_ARGUMENT, "Invalid or reentrant session access");
  for (i = 0; i < s->count; i++)
    if (s->cache[i].part == part) {
      entry = s->cache[i];
      memmove(s->cache + 1, s->cache, i * sizeof(*s->cache));
      s->cache[0] = entry;
      *document = entry.document;
      *layout = entry.layout;
      return exr_fail(e, EXR_OK, "");
    }
  s->busy = 1;
  status = exr_publication_load(s->publication, part, &entry.document, e);
  if (status == EXR_OK)
    status = exr_layout_create_hyphenated(entry.document,s->font,&s->config,s->hyphenator,&entry.layout,e);
  s->busy = 0;
  if (status != EXR_OK) {
    exr_document_free(entry.document);
    exr_layout_free(entry.layout);
    return status;
  }
  document_bytes = exr_document_memory_size(entry.document);
  layout_bytes = exr_layout_memory_size(entry.layout);
  if (document_bytes == SIZE_MAX || layout_bytes >= SIZE_MAX - document_bytes ||
      (s->budget && (document_bytes > s->budget || layout_bytes > s->budget - document_bytes))) {
    exr_document_free(entry.document);
    exr_layout_free(entry.layout);
    return exr_fail(e, EXR_LIMIT, "Part exceeds the session cache byte budget");
  }
  entry.bytes = document_bytes + layout_bytes;
  /* Finish loading and measuring before changing the resident cache. Failures
     leave all previous borrowed pointers and their LRU order intact. */
  while (s->count && (s->count == s->capacity || entry.bytes > SIZE_MAX - s->bytes ||
                      (s->budget && entry.bytes > s->budget - s->bytes)))
    evict_last(s);
  s->count++;
  memmove(s->cache + 1, s->cache, (s->count - 1) * sizeof(*s->cache));
  entry.part = part;
  s->cache[0] = entry;
  s->bytes += entry.bytes;
  *document = entry.document;
  *layout = entry.layout;
  return exr_fail(e, EXR_OK, "");
}

/* Content ranges deliberately use the same normalized projection as layout. */
static int position_before(exr_text_position a,exr_text_position b) {
  return a.part<b.part || (a.part==b.part && a.offset<b.offset);
}
static void range_clear(exr_text_range *r) {
  r->start.part=r->start.offset=r->end.part=r->end.offset=SIZE_MAX;
}
static int content_boundary(const exr_document *d,size_t at) {
  return at<=d->size && (at==d->size || (exr_doc_byte(d,at)&0xc0)!=0x80);
}
static exr_status content_revision(const exr_document *d,const exr_control *control,uint64_t *out,exr_error *e) {
  size_t at=0;uint64_t hash=UINT64_C(14695981039346656037);
  /* ponytail: one linear part scan per endpoint; cache revisions in a future
     immutable snapshot API if annotation throughput requires it. */
  while(at<d->size) {
    size_t n,i;const char *s=exr_doc_span(d,at,&n);
    exr_status status=exr_control_cancel(control,e);if(status!=EXR_OK) return status;
    if(!s || !n) return exr_fail(e,EXR_FORMAT,"Unavailable content projection");
    if(n>d->size-at) n=d->size-at;
    if(n>4096) n=4096;
    for(i=0;i<n;i++) { hash^=(unsigned char)s[i];hash*=UINT64_C(1099511628211); }
    at+=n;
  }
  *out=hash;return EXR_OK;
}
void exr_content_anchor_free(exr_content_anchor *a) {
  if(a) {
    free(a->start.part_id);free(a->start.part_path);exr_anchor_free(&a->start.selector);
    free(a->end.part_id);free(a->end.part_path);exr_anchor_free(&a->end.selector);
    memset(a,0,sizeof(*a));
  }
}
static exr_anchor_state content_part(const exr_publication *p,const exr_content_endpoint *a,size_t *part) {
  size_t i,count=0,path_count=0,by_id=SIZE_MAX,by_path=SIZE_MAX;
  for(i=0;i<p->count;i++) {
    if(a->part_id && *a->part_id && !strcmp(a->part_id,p->parts[i].id)) {
      count++;by_id=i;
      if(a->part_path && !strcmp(a->part_path,p->parts[i].path)) { path_count++;by_path=i; }
    }
  }
  if(count==1) { *part=by_id;return EXR_ANCHOR_FOUND; }
  if(count>1) {
    if(path_count==1) { *part=by_path;return EXR_ANCHOR_FOUND; }
    return EXR_ANCHOR_AMBIGUOUS;
  }
  /* A nonempty stable ID disappearing denotes a removed part, not permission
     to bind its old path to a different resource. */
  if(a->part_id && *a->part_id) return EXR_ANCHOR_MISSING;
  for(i=0;i<p->count;i++) if(a->part_path && *a->part_path && !strcmp(a->part_path,p->parts[i].path)) {
    path_count++;by_path=i;
  }
  if(path_count==1) { *part=by_path;return EXR_ANCHOR_FOUND; }
  return path_count ? EXR_ANCHOR_AMBIGUOUS : EXR_ANCHOR_MISSING;
}
static exr_status capture_endpoint(exr_publication *p,exr_text_position at,const exr_control *control,
                                    exr_content_endpoint *a,exr_error *e) {
  exr_document *d=NULL;exr_status status;size_t routed=SIZE_MAX;
  if(at.part>=p->count) return exr_fail(e,EXR_ARGUMENT,"Range part is outside publication");
  a->part_id=exr_copy(p->parts[at.part].id,strlen(p->parts[at.part].id));
  a->part_path=exr_copy(p->parts[at.part].path,strlen(p->parts[at.part].path));
  if(!a->part_id || !a->part_path) return exr_fail(e,EXR_MEMORY,"Content identity allocation failed");
  if(content_part(p,a,&routed)!=EXR_ANCHOR_FOUND || routed!=at.part)
    return exr_fail(e,EXR_ARGUMENT,"Content part needs a unique stable ID or path");
  status=exr_publication_load(p,at.part,&d,e);
  if(status==EXR_OK) status=exr_anchor_create(d,at.offset,at.offset,&a->selector,e);
  if(status==EXR_OK) {
    /* Part identity supplies the scope; chapter paths may change between editions. */
    free(a->selector.chapter);a->selector.chapter=NULL;a->text_size=d->size;
    status=content_revision(d,control,&a->text_revision,e);
  }
  exr_document_free(d);return status;
}
exr_status exr_anchor_from_range(exr_publication *p,const exr_text_range *r,const exr_control *control,
                                  exr_content_anchor *out,exr_error *e) {
  exr_content_anchor a={0};exr_status status;
  if(!out) return exr_fail(e,EXR_ARGUMENT,"Missing content anchor output");
  memset(out,0,sizeof(*out));
  if(!p || !r || position_before(r->end,r->start)) return exr_fail(e,EXR_ARGUMENT,"Invalid content range");
  status=exr_control_cancel(control,e);
  if(status==EXR_OK) status=capture_endpoint(p,r->start,control,&a.start,e);
  if(status==EXR_OK) status=capture_endpoint(p,r->end,control,&a.end,e);
  if(status!=EXR_OK) { exr_content_anchor_free(&a);return status; }
  *out=a;return exr_fail(e,EXR_OK,"");
}
static exr_status resolve_endpoint(exr_publication *p,const exr_content_endpoint *a,const exr_control *control,
                                    exr_text_position *at,exr_anchor_state *state,exr_error *e) {
  exr_document *d=NULL;exr_status status;exr_anchor_match match;uint64_t revision;
  size_t part=SIZE_MAX;
  if(!a->selector.exact || a->selector.exact[0] || a->selector.start!=a->selector.end ||
     a->selector.chapter || (!a->part_id && !a->part_path))
    return exr_fail(e,EXR_ARGUMENT,"Invalid content endpoint");
  if((status=exr_anchor_validate(&a->selector,e))!=EXR_OK) return status;
  *state=content_part(p,a,&part);
  if(*state!=EXR_ANCHOR_FOUND) return EXR_OK;
  status=exr_publication_load(p,part,&d,e);
  if(status==EXR_OK) status=content_revision(d,control,&revision,e);
  if(status==EXR_OK && a->text_size==d->size && a->text_revision==revision &&
     a->selector.start!=SIZE_MAX && content_boundary(d,a->selector.start)) {
    exr_anchor check={0};
    status=exr_anchor_create(d,a->selector.start,a->selector.start,&check,e);
    if(status==EXR_OK && a->selector.prefix && a->selector.suffix &&
       !strcmp(check.prefix,a->selector.prefix) && !strcmp(check.suffix,a->selector.suffix)) {
      at->part=part;at->offset=a->selector.start;
      exr_anchor_free(&check);exr_document_free(d);return EXR_OK;
    }
    exr_anchor_free(&check);
  }
  if(status==EXR_OK) {
    status=exr_anchor_resolve_ex(d,&a->selector,control,&match,e);
    if(status==EXR_OK) {
      *state=match.state;
      if(match.state==EXR_ANCHOR_FOUND) { at->part=part;at->offset=match.start; }
    }
  }
  exr_document_free(d);return status;
}
exr_status exr_range_from_anchor(exr_publication *p,const exr_content_anchor *a,const exr_control *control,
                                  exr_text_range_match *out,exr_error *e) {
  exr_text_range r;exr_anchor_state start=EXR_ANCHOR_MISSING,end=EXR_ANCHOR_MISSING;exr_status status;
  if(!out) return exr_fail(e,EXR_ARGUMENT,"Missing content range output");
  out->state=EXR_ANCHOR_MISSING;range_clear(&out->range);range_clear(&r);
  if(!p || !a) return exr_fail(e,EXR_ARGUMENT,"Missing publication or content anchor");
  status=exr_control_cancel(control,e);
  if(status==EXR_OK) status=resolve_endpoint(p,&a->start,control,&r.start,&start,e);
  if(status==EXR_OK) status=resolve_endpoint(p,&a->end,control,&r.end,&end,e);
  if(status!=EXR_OK) return status;
  if(start==EXR_ANCHOR_AMBIGUOUS || end==EXR_ANCHOR_AMBIGUOUS) out->state=EXR_ANCHOR_AMBIGUOUS;
  else if(start==EXR_ANCHOR_FOUND && end==EXR_ANCHOR_FOUND && !position_before(r.end,r.start)) {
    out->state=EXR_ANCHOR_FOUND;out->range=r;
  }
  return exr_fail(e,EXR_OK,"");
}

static size_t content_previous(const exr_document *d,size_t at) {
  if(at) { at--;while(at && (exr_doc_byte(d,at)&0xc0)==0x80) at--; }
  return at;
}
static uint32_t content_cp(const exr_document *d,size_t at) {
  uint32_t cp=0;exr_doc_next(d,d->size,&at,&cp);return cp;
}
static int content_punctuation(uint32_t cp) {
  return (cp<128 && ispunct((unsigned char)cp)) || (cp>=0x2000 && cp<=0x206f) ||
         (cp>=0x3000 && cp<=0x303f) || (cp>=0xff01 && cp<=0xff0f) ||
         (cp>=0xff1a && cp<=0xff20) || (cp>=0xff3b && cp<=0xff40) || (cp>=0xff5b && cp<=0xff65);
}
static int content_word_class(uint32_t cp) {
  if(exr_projection_space(cp)) return 0;
  if(content_punctuation(cp) || exr_projection_cjk(cp)) return 1;
  return 2;
}
static int content_sentence_end(uint32_t cp) {
  return cp=='.' || cp=='!' || cp=='?' || cp==0x3002 || cp==0xff01 || cp==0xff1f ||
         cp=='\n' || cp==0x2029;
}
static exr_status content_unit(const exr_document *d,size_t at,exr_range_unit unit,const exr_control *control,
                                size_t *lo,size_t *hi,exr_error *e) {
  unsigned char *map=NULL;exr_status status;const char *text;size_t i,left,right;int kind;
  if(!content_boundary(d,at)) return exr_fail(e,EXR_ARGUMENT,"Range endpoint is not a UTF-8 boundary");
  *lo=*hi=at;
  if(at==d->size) return EXR_OK;
  if(unit==EXR_RANGE_PARAGRAPH) {
    for(i=0;i<d->count;i++) if(at>=d->blocks[i].start && at<d->blocks[i].end) {
      *lo=d->blocks[i].start;*hi=d->blocks[i].end;return EXR_OK;
    }
    /* Projection separators between blocks are single character units. */
    unit=EXR_RANGE_CHAR;
  }
  text=exr_document_text(d,NULL);
  if(!text) return exr_fail(e,EXR_FORMAT,"Missing content text");
  status=exr_text_analyze(text,d->size,&map,e);if(status!=EXR_OK) return status;
  left=at;while(left && !(map[left]&EXR_BOUNDARY_GRAPHEME)) left--;
  right=left+1;while(right<d->size && !(map[right]&EXR_BOUNDARY_GRAPHEME)) right++;
  if(unit==EXR_RANGE_WORD) {
    kind=content_word_class(content_cp(d,left));
    if(kind!=1) {
      while(left) {
        size_t prev=left-1;while(prev && !(map[prev]&EXR_BOUNDARY_GRAPHEME)) prev--;
        if(content_word_class(content_cp(d,prev))!=kind) break;
        left=prev;
      }
      while(right<d->size && content_word_class(content_cp(d,right))==kind) {
        right++;while(right<d->size && !(map[right]&EXR_BOUNDARY_GRAPHEME)) right++;
      }
    }
  } else if(unit==EXR_RANGE_SENTENCE) {
    while(left) {
      size_t prev=content_previous(d,left);
      if(content_sentence_end(content_cp(d,prev))) break;
      left=prev;
    }
    while(right<d->size && !content_sentence_end(content_cp(d,content_previous(d,right)))) {
      uint32_t cp;if(!exr_doc_next(d,d->size,&right,&cp)) break;
    }
  }
  free(map);*lo=left;*hi=right;return exr_control_cancel(control,e);
}
exr_status exr_range_expand(exr_publication *p,const exr_text_range *r,exr_range_unit unit,
                             const exr_control *control,exr_text_range *out,exr_error *e) {
  exr_text_range result,original;exr_document *d=NULL;exr_status status;size_t ignored,at;
  if(!out) return exr_fail(e,EXR_ARGUMENT,"Missing expanded range output");
  /* Permit in-place expansion. */
  if(r) original=result=*r;
  range_clear(out);
  if(!p || !r || unit<EXR_RANGE_CHAR || unit>EXR_RANGE_PARAGRAPH ||
     position_before(result.end,result.start)) return exr_fail(e,EXR_ARGUMENT,"Invalid range expansion");
  status=exr_control_cancel(control,e);
  if(status==EXR_OK) status=exr_publication_load(p,result.start.part,&d,e);
  if(status==EXR_OK) status=content_unit(d,result.start.offset,unit,control,&result.start.offset,&ignored,e);
  exr_document_free(d);d=NULL;
  if(status==EXR_OK) status=exr_publication_load(p,result.end.part,&d,e);
  if(status==EXR_OK) {
    at=result.end.offset;
    if(!content_boundary(d,at)) status=exr_fail(e,EXR_ARGUMENT,"Invalid range end");
    else if(!at && position_before(original.start,original.end)) result.end.offset=0;
    else {
      if(position_before(original.start,original.end) && at) at=content_previous(d,at);
      status=content_unit(d,at,unit,control,&ignored,&result.end.offset,e);
    }
  }
  exr_document_free(d);
  if(status==EXR_OK) *out=result;
  return status==EXR_OK ? exr_fail(e,EXR_OK,"") : status;
}

exr_status exr_hit_test(const exr_layout *l,size_t part,size_t page,float x,float y,
                         exr_text_position *out,exr_error *e) {
  const exr_page *p;size_t i;
  if(!out) return exr_fail(e,EXR_ARGUMENT,"Missing hit output");
  out->part=out->offset=SIZE_MAX;
  if(!l || part==SIZE_MAX || page>=l->page_count || !isfinite(x) || !isfinite(y))
    return exr_fail(e,EXR_ARGUMENT,"Invalid content hit coordinates or page");
  p=&l->pages[page];
  for(i=p->box_start;i<p->box_start+p->box_count;i++) {
    const exr_box *b=&l->boxes[i];
    if(b->kind==EXR_BOX_IMAGE && x>=b->x && x<=b->x+b->width && y>=b->y && y<=b->y+b->height)
      return exr_fail(e,EXR_OK,"");
  }
  for(i=p->line_start;i<p->line_start+p->line_count;i++) {
    const exr_line *line=&l->lines[i];size_t j;
    if(x<line->x || x>line->x+line->width || y<line->y || y>line->y+line->height) continue;
    for(j=line->glyph_start;j<line->glyph_start+line->glyph_count;j++)
      if(!(l->glyphs[j].flags&(EXR_GLYPH_HIDDEN|EXR_GLYPH_GENERATED))) {
        out->offset=exr_layout_hit_test(l,page,x,y);
        if(out->offset!=SIZE_MAX) out->part=part;
        return exr_fail(e,EXR_OK,"");
      }
  }
  return exr_fail(e,EXR_OK,"");
}
