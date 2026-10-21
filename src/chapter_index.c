/* SPDX-License-Identifier: MIT */
#include "chapter_internal.h"
#include <expat.h>

#define INDEX_CHUNK 4096u
#define INDEX_CHUNKS 256u
typedef struct {
  uint32_t node, last, first, end;
  unsigned hidden, boundary;
} index_frame;
struct exr_chapter_index {
  exr_chapter_entry *chunks[INDEX_CHUNKS];
  size_t count, allocated, budget, bytes, peak_bytes, fed, text_size;
  char **names;
  size_t name_count, name_capacity;
  XML_Parser parser;
  exr_control control;
  exr_error *error;
  exr_status failed;
  index_frame stack[257];
  size_t depth;
  uint32_t text_node;
  int block, pending_space, finished, allocation_limited;
};
static void memory_peak(exr_chapter_index *p) { if(p->bytes>p->peak_bytes) p->peak_bytes=p->bytes; }
typedef struct { max_align_t alignment; exr_chapter_index *owner; size_t bytes; } xml_allocation;
#ifdef _MSC_VER
static __declspec(thread) exr_chapter_index *xml_owner;
#else
static _Thread_local exr_chapter_index *xml_owner;
#endif
static void *xml_alloc(size_t size) {
  exr_chapter_index *p=xml_owner;
  xml_allocation *a;
  if (size>SIZE_MAX-sizeof(*a) || size+sizeof(*a)>p->budget-p->bytes) {
    p->allocation_limited=1;return NULL;
  }
  a=malloc(sizeof(*a)+size);if(!a) return NULL;
  a->owner=p;a->bytes=sizeof(*a)+size;p->bytes+=a->bytes;memory_peak(p);return a+1;
}
static void xml_free(void *data) {
  xml_allocation *a;
  if (!data) return;
  a=(xml_allocation *)data-1;a->owner->bytes-=a->bytes;free(a);
}
static void *xml_realloc(void *data,size_t size) {
  xml_allocation *a,*grown;
  exr_chapter_index *p;
  size_t bytes,previous;
  if (!data) return xml_alloc(size);
  if (!size) { xml_free(data);return NULL; }
  a=(xml_allocation *)data-1;p=a->owner;previous=a->bytes;
  if(size>SIZE_MAX-sizeof(*a)) { p->allocation_limited=1;return NULL; }
  bytes=sizeof(*a)+size;
  if(bytes>previous && bytes-previous>p->budget-p->bytes) { p->allocation_limited=1;return NULL; }
  grown=realloc(a,bytes);if(!grown) return NULL;
  grown->bytes=bytes;p->bytes=p->bytes-previous+bytes;memory_peak(p);return grown+1;
}
static const char *local(const char *name) {
  const char *p = strrchr(name, '|'); return p ? p + 1 : name;
}
static int white(unsigned char c) { return c == ' ' || c == '\n' || c == '\r' || c == '\t'; }
static void stop(exr_chapter_index *p, exr_status status, const char *message) {
  if (!p->failed) p->failed = exr_fail(p->error, status, "%s", message);
  XML_StopParser(p->parser, XML_FALSE);
}
static exr_chapter_entry *entry(exr_chapter_index *p, size_t node) {
  return &p->chunks[node / INDEX_CHUNK][node % INDEX_CHUNK];
}
static uint32_t name_id(exr_chapter_index *p, const char *name) {
  size_t i, length = strlen(name) + 1;
  for (i = 0; i < p->name_count; i++) if (!strcmp(p->names[i], name)) return (uint32_t)i;
  if (p->name_count == 65536 || length > p->budget - p->bytes) {
    stop(p, EXR_LIMIT, "Chapter index names exceed budget"); return 0;
  }
  if (p->name_count == p->name_capacity) {
    size_t capacity = p->name_capacity ? p->name_capacity * 2 : 32;
    size_t extra = (capacity - p->name_capacity) * sizeof(*p->names);
    char **grown;
    if (extra > p->budget - p->bytes) { stop(p, EXR_LIMIT, "Chapter index exceeds budget"); return 0; }
    grown = realloc(p->names, capacity * sizeof(*p->names));
    if (!grown) { stop(p, EXR_MEMORY, "Chapter name allocation failed"); return 0; }
    p->names = grown; p->name_capacity = capacity; p->bytes += extra;memory_peak(p);
  }
  if (length > p->budget - p->bytes) { stop(p, EXR_LIMIT, "Chapter index exceeds budget"); return 0; }
  p->names[p->name_count] = exr_copy(name, length - 1);
  if (!p->names[p->name_count]) { stop(p, EXR_MEMORY, "Chapter name allocation failed"); return 0; }
  p->bytes += length;memory_peak(p);return (uint32_t)p->name_count++;
}
static uint32_t append_node(exr_chapter_index *p, exr_node_kind kind, const char *name,
                            uint32_t source, index_frame *parent) {
  exr_chapter_entry *n;
  uint32_t id, tag = name ? name_id(p, name) : 0;
  if (p->failed) return EXR_CHAPTER_NONE;
  if (p->count == p->allocated) {
    size_t bytes = INDEX_CHUNK * sizeof(*n);
    if (p->count / INDEX_CHUNK == INDEX_CHUNKS || bytes > p->budget - p->bytes) {
      stop(p, EXR_LIMIT, "Chapter index exceeds budget"); return EXR_CHAPTER_NONE;
    }
    p->chunks[p->count / INDEX_CHUNK] = malloc(bytes);
    if (!p->chunks[p->count / INDEX_CHUNK]) { stop(p, EXR_MEMORY, "Chapter index allocation failed"); return EXR_CHAPTER_NONE; }
    p->allocated += INDEX_CHUNK; p->bytes += bytes;memory_peak(p);
  }
  id = (uint32_t)p->count++;
  n = entry(p, id);
  *n = (exr_chapter_entry){parent ? parent->node : EXR_CHAPTER_NONE,
    EXR_CHAPTER_NONE, EXR_CHAPTER_NONE, EXR_CHAPTER_NONE, EXR_CHAPTER_NONE,
    source, source, (tag << 8) | (uint32_t)kind};
  if (parent) {
    if (parent->last == EXR_CHAPTER_NONE) entry(p, parent->node)->first_child = id;
    else entry(p, parent->last)->next_sibling = id;
    parent->last = id;
  }
  return id;
}
static void propagate(exr_chapter_index *p, uint32_t id) {
  index_frame *f = &p->stack[p->depth];
  const exr_chapter_entry *n = entry(p, id);
  if (n->start != EXR_CHAPTER_NONE && n->end > n->start) {
    if (f->first == EXR_CHAPTER_NONE) f->first = n->start;
    f->end = n->end;
  }
}
static void flush_text(exr_chapter_index *p) {
  if (p->text_node == EXR_CHAPTER_NONE) return;
  if (!p->stack[p->depth].hidden) {
    exr_chapter_entry *n = entry(p, p->text_node);
    if (n->start == EXR_CHAPTER_NONE) n->start = (uint32_t)p->text_size;
    n->end = (uint32_t)p->text_size;
    propagate(p, p->text_node);
  }
  p->text_node = EXR_CHAPTER_NONE;
}
static int has_token(const char *s, const char *wanted) {
  size_t length = strlen(wanted);
  while (*s) {
    const char *start;
    while (white((unsigned char)*s)) s++;
    start = s; while (*s && !white((unsigned char)*s)) s++;
    if ((size_t)(s - start) == length && !memcmp(start, wanted, length)) return 1;
  }
  return 0;
}
static void XMLCALL start_element(void *context, const char *name, const char **attrs) {
  exr_chapter_index *p = context;
  exr_node_kind kind = exr_xml_element_kind(name);
  const char *tag = local(name);
  size_t i, count = 0;
  uint32_t id;
  int hidden = p->stack[p->depth].hidden || !strcmp(tag,"head") || !strcmp(tag,"script") ||
    !strcmp(tag,"style") || !strcmp(tag,"object") || !strcmp(tag,"template");
  flush_text(p);
  if (p->depth == 256) { stop(p, EXR_LIMIT, "Chapter XML depth exceeds limit"); return; }
  if (!p->depth && strcmp(tag, "html")) { stop(p, EXR_FORMAT, "Chapter root must be html"); return; }
  while (attrs[count * 2]) count++;
  if (count > 256) { stop(p, EXR_LIMIT, "Chapter attribute count exceeds limit"); return; }
  for (i = 0; i < count; i++) {
    if (!strcmp(attrs[i * 2], "hidden")) hidden = 1;
    if ((!strcmp(attrs[i * 2], "http://www.idpf.org/2007/ops|type") &&
         (has_token(attrs[i * 2 + 1], "footnote") || has_token(attrs[i * 2 + 1], "endnote"))) ||
        (!strcmp(attrs[i * 2], "role") &&
         (has_token(attrs[i * 2 + 1], "doc-footnote") || has_token(attrs[i * 2 + 1], "doc-endnote")))) kind = EXR_NODE_NOTE;
  }
  id = append_node(p, kind, name, (uint32_t)XML_GetCurrentByteIndex64(p->parser), &p->stack[p->depth]);
  if (p->failed) return;
  p->depth++;
  p->stack[p->depth] = (index_frame){id,EXR_CHAPTER_NONE,EXR_CHAPTER_NONE,0,
    (unsigned)hidden,(unsigned)exr_projection_boundary(kind,tag)};
  if (!hidden && p->stack[p->depth].boundary) p->block = p->pending_space = 0;
}
static void XMLCALL end_element(void *context, const char *name) {
  exr_chapter_index *p = context;
  index_frame *f;
  exr_chapter_entry *n;
  (void)name;
  flush_text(p);
  f = &p->stack[p->depth]; n = entry(p, f->node);
  n->source_end = (uint32_t)(XML_GetCurrentByteIndex64(p->parser) + XML_GetCurrentByteCount64(p->parser));
  if (!f->hidden) {
    n->start = f->first == EXR_CHAPTER_NONE ? (uint32_t)p->text_size : f->first;
    n->end = f->first == EXR_CHAPTER_NONE ? (uint32_t)p->text_size : f->end;
    if (f->boundary) p->block = p->pending_space = 0;
  }
  p->depth--; propagate(p, f->node);
}
static void XMLCALL text_data(void *context, const char *text, int size) {
  exr_chapter_index *p = context;
  exr_chapter_entry *n;
  size_t i;
  if (!size || p->failed) return;
  if (p->text_node == EXR_CHAPTER_NONE)
    p->text_node = append_node(p, EXR_NODE_TEXT, NULL,
      (uint32_t)XML_GetCurrentByteIndex64(p->parser), &p->stack[p->depth]);
  if (p->failed) return;
  n = entry(p,p->text_node);
  n->source_end = (uint32_t)(XML_GetCurrentByteIndex64(p->parser) + XML_GetCurrentByteCount64(p->parser));
  if (p->stack[p->depth].hidden) return;
  for (i = 0; i < (size_t)size; i++) {
    if (white((unsigned char)text[i])) { if (p->block) p->pending_space = 1; continue; }
    if (!p->block) {
      if (p->text_size) p->text_size++;
      p->block = 1;
    }
    if (n->start == EXR_CHAPTER_NONE) n->start = (uint32_t)p->text_size;
    if (p->pending_space) p->text_size++;
    p->pending_space = 0;
    if (++p->text_size > EXR_MAX_INPUT) { stop(p, EXR_LIMIT, "Chapter projection exceeds limit"); return; }
  }
}
static void XMLCALL entity_decl(void *context, const char *name, int parameter,
  const char *value, int length, const char *base, const char *system,
  const char *public_id, const char *notation) {
  (void)name;(void)parameter;(void)value;(void)length;(void)base;(void)system;(void)public_id;(void)notation;
  stop(context,EXR_FORMAT,"Chapter entity declarations are unsupported");
}
exr_status exr_chapter_index_begin(const exr_control *control,size_t budget,
                                  exr_chapter_index **out,exr_error *e) {
  exr_chapter_index *p;
  exr_chapter_index *previous;
  const XML_Memory_Handling_Suite allocator={xml_alloc,xml_realloc,xml_free};
  index_frame root;
  if (!out) return exr_fail(e,EXR_ARGUMENT,"Missing chapter index output");
  *out = NULL;
  if (budget < sizeof(*p) + INDEX_CHUNK * sizeof(exr_chapter_entry))
    return exr_fail(e,EXR_LIMIT,"Chapter index budget is too small");
  p = calloc(1,sizeof(*p));
  if (!p) return exr_fail(e,EXR_MEMORY,"Chapter index allocation failed");
  p->budget=budget;p->bytes=sizeof(*p);p->error=e;p->text_node=EXR_CHAPTER_NONE;
  if (control) p->control=*control;
  previous=xml_owner;xml_owner=p;
  p->parser=XML_ParserCreate_MM(NULL,&allocator,"|");
  xml_owner=previous;
  if (!p->parser) { int limited=p->allocation_limited;free(p);return exr_fail(e,limited ? EXR_LIMIT : EXR_MEMORY,"Chapter XML allocation failed"); }
  (void)append_node(p,EXR_NODE_DOCUMENT,NULL,0,NULL);
  root=(index_frame){0,EXR_CHAPTER_NONE,EXR_CHAPTER_NONE,0,0,1};
  (void)append_node(p,EXR_NODE_CHAPTER,NULL,0,&root);
  p->stack[0]=(index_frame){1,EXR_CHAPTER_NONE,EXR_CHAPTER_NONE,0,0,1};
  if (p->failed) { exr_status status=p->failed;exr_chapter_index_free(p);return status; }
  XML_SetUserData(p->parser,p);
  XML_SetElementHandler(p->parser,start_element,end_element);
  XML_SetCharacterDataHandler(p->parser,text_data);
  XML_SetEntityDeclHandler(p->parser,entity_decl);
  XML_SetParamEntityParsing(p->parser,XML_PARAM_ENTITY_PARSING_NEVER);
  *out=p;return exr_fail(e,EXR_OK,"");
}
exr_status exr_chapter_index_feed(exr_chapter_index *p,const void *data,size_t size,int final,exr_error *e) {
  size_t at=0;
  if (!p || (!data && size) || p->finished) return exr_fail(e,EXR_ARGUMENT,"Invalid chapter index feed");
  p->error=e;
  if (p->failed) return p->failed;
  if (size > EXR_MAX_INPUT-p->fed) return p->failed=exr_fail(e,EXR_LIMIT,"Chapter source exceeds streaming limit");
  do {
    size_t chunk=size-at>32768 ? 32768 : size-at;
    enum XML_Status parsed;
    exr_chapter_index *previous;
    p->failed=exr_control_poll(&p->control,EXR_STAGE_READ,p->fed,EXR_MAX_INPUT,e);
    if (p->failed) return p->failed;
    previous=xml_owner;xml_owner=p;
    parsed=XML_Parse(p->parser,data ? (const char *)data+at : NULL,(int)chunk,final && at+chunk==size);
    xml_owner=previous;
    p->fed+=chunk;at+=chunk;
    if (parsed!=XML_STATUS_OK || p->failed)
      return p->failed ? p->failed : (p->failed=exr_fail(e,
        p->allocation_limited ? EXR_LIMIT : XML_GetErrorCode(p->parser)==XML_ERROR_NO_MEMORY ? EXR_MEMORY : EXR_FORMAT,
        "Chapter XML is invalid or exceeds its allocation budget"));
  } while(at<size);
  if (final) {
    flush_text(p);p->finished=1;
    entry(p,0)->start=0;entry(p,0)->end=(uint32_t)p->text_size;
    entry(p,1)->start=p->stack[0].first==EXR_CHAPTER_NONE ? (uint32_t)p->text_size : p->stack[0].first;
    entry(p,1)->end=p->stack[0].first==EXR_CHAPTER_NONE ? (uint32_t)p->text_size : p->stack[0].end;
    entry(p,0)->source_end=entry(p,1)->source_end=(uint32_t)p->fed;
    XML_ParserFree(p->parser);p->parser=NULL;
  }
  return EXR_OK;
}
const exr_chapter_entry *exr_chapter_index_entry(const exr_chapter_index *p,size_t node) {
  return p && node<p->count ? &p->chunks[node/INDEX_CHUNK][node%INDEX_CHUNK] : NULL;
}
const char *exr_chapter_index_name(const exr_chapter_index *p,size_t node) {
  const exr_chapter_entry *n=exr_chapter_index_entry(p,node);
  return n && ((n->tag_kind&255)!=EXR_NODE_TEXT) && node>1 ? p->names[n->tag_kind>>8] : NULL;
}
size_t exr_chapter_index_count(const exr_chapter_index *p) { return p ? p->count : 0; }
size_t exr_chapter_index_text_size(const exr_chapter_index *p) { return p ? p->text_size : 0; }
size_t exr_chapter_index_memory(const exr_chapter_index *p) { return p ? p->bytes : 0; }
size_t exr_chapter_index_peak(const exr_chapter_index *p) { return p ? p->peak_bytes : 0; }
void exr_chapter_index_free(exr_chapter_index *p) {
  size_t i;
  if (!p) return;
  if(p->parser) XML_ParserFree(p->parser);
  for(i=0;i<INDEX_CHUNKS;i++) free(p->chunks[i]);
  for(i=0;i<p->name_count;i++) free(p->names[i]);
  free(p->names);free(p);
}
