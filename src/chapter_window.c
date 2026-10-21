/* SPDX-License-Identifier: MIT */
#include "chapter_internal.h"
#include <expat.h>

typedef struct { uint32_t global; size_t local; unsigned declaration; exr_node pending; } window_frame;
typedef struct {
  const exr_chapter_index *index;
  exr_document *doc;
  uint32_t *map;
  size_t map_capacity, first, last, global, depth, fed;
  uint32_t ancestors[258], text_global;
  size_t ancestor_count;
  window_frame stack[257];
  exr_buffer text;
  size_t bytes, budget, peak_bytes;
  XML_Parser parser;
  const exr_control *control;
  exr_error *error;
  exr_status failed;
  int projection, finished, limited;
  const exr_chapter_window *declarations;
  exr_chapter_window_consumer_fn consumer;
  void *consumer_context;
  size_t batch_nodes, batch_count;
} window_parser;
static int visit_emit(window_parser *p,int final);
static void account_peak(window_parser *p) { if (p->bytes > p->peak_bytes) p->peak_bytes = p->bytes; }
typedef struct { exr_allocation_alignment alignment; window_parser *owner; size_t bytes; } window_xml_allocation;
#ifdef _MSC_VER
static __declspec(thread) window_parser *window_owner;
#else
static _Thread_local window_parser *window_owner;
#endif

static void *xml_alloc(size_t size) {
  window_parser *p = window_owner;
  window_xml_allocation *a;
  if (size > SIZE_MAX - sizeof(*a) || size + sizeof(*a) > p->budget - p->bytes) {
    p->limited = 1; return NULL;
  }
  a = malloc(size + sizeof(*a));
  if (!a) return NULL;
  a->owner = p; a->bytes = size + sizeof(*a); p->bytes += a->bytes; account_peak(p);
  return a + 1;
}
static void xml_free(void *data) {
  window_xml_allocation *a;
  if (!data) return;
  a = (window_xml_allocation *)data - 1;
  a->owner->bytes -= a->bytes; free(a);
}
static void *xml_realloc(void *data,size_t size) {
  window_xml_allocation *a, *grown;
  window_parser *p;
  size_t bytes;
  if (!data) return xml_alloc(size);
  if (!size) { xml_free(data); return NULL; }
  a = (window_xml_allocation *)data - 1; p = a->owner;
  if (size > SIZE_MAX - sizeof(*a)) { p->limited = 1; return NULL; }
  bytes = size + sizeof(*a);
  if (bytes > a->bytes && bytes - a->bytes > p->budget - p->bytes) { p->limited = 1; return NULL; }
  grown = realloc(a, bytes);
  if (!grown) return NULL;
  p->bytes = p->bytes - grown->bytes + bytes; grown->bytes = bytes; account_peak(p);
  return grown + 1;
}
static void fail(window_parser *p,exr_status status,const char *message) {
  if (!p->failed) p->failed = exr_fail(p->error,status,"%s",message);
  if (p->parser) XML_StopParser(p->parser,XML_FALSE);
}
static void *allocate(window_parser *p,size_t bytes) {
  void *data;
  if (bytes > p->budget - p->bytes) { fail(p,EXR_LIMIT,"Chapter window exceeds budget"); return NULL; }
  data = calloc(bytes ? bytes : 1,1);
  if (!data) { fail(p,EXR_MEMORY,"Chapter window allocation failed"); return NULL; }
  p->bytes += bytes; account_peak(p); return data;
}
static int grow(window_parser *p,void **data,size_t *capacity,size_t count,size_t unit) {
  size_t next = *capacity ? *capacity : 64, extra;
  void *replacement;
  if (count <= *capacity) return 1;
  while (next < count) {
    if (next > SIZE_MAX / 2) { fail(p,EXR_LIMIT,"Chapter window capacity overflow"); return 0; }
    next *= 2;
  }
  if (next > SIZE_MAX / unit) { fail(p,EXR_LIMIT,"Chapter window capacity overflow"); return 0; }
  extra = (next - *capacity) * unit;
  if (extra > p->budget - p->bytes) { fail(p,EXR_LIMIT,"Chapter window exceeds budget"); return 0; }
  replacement = realloc(*data,next * unit);
  if (!replacement) { fail(p,EXR_MEMORY,"Chapter window allocation failed"); return 0; }
  *data = replacement; *capacity = next; p->bytes += extra; account_peak(p); return 1;
}
static char *copy(window_parser *p,const char *text,size_t size) {
  char *out;
  if (size == SIZE_MAX) { fail(p,EXR_LIMIT,"Chapter window string overflow"); return NULL; }
  out = allocate(p,size + 1);
  if (!out) return NULL;
  memcpy(out,text,size); out[size] = 0; p->doc->model_bytes += size + 1;
  return out;
}
static size_t append(window_parser *p,uint32_t global,size_t parent,exr_node_kind kind,
                     const char *name,const char *text,size_t size) {
  exr_document *d = p->doc;
  exr_node *n;
  size_t id = d->node_count, previous;
  if (!grow(p,(void **)&d->nodes,&d->node_capacity,id + 1,sizeof(*d->nodes)) ||
      !grow(p,(void **)&d->last_children,&d->last_capacity,id + 1,sizeof(*d->last_children)) ||
      !grow(p,(void **)&p->map,&p->map_capacity,id + 1,sizeof(*p->map))) return SIZE_MAX;
  n = &d->nodes[id]; d->node_count++;
  *n = (exr_node){0}; n->kind = kind; n->parent = parent; n->chapter = id ? 0 : SIZE_MAX;
  n->first_child = n->next_sibling = n->start = n->end = SIZE_MAX;
  d->last_children[id] = SIZE_MAX; p->map[id] = global;
  if (name) n->name = copy(p,name,strlen(name));
  if (text) n->text = copy(p,text,size);
  if (p->failed) return SIZE_MAX;
  if (parent != SIZE_MAX) {
    previous = d->last_children[parent];
    if (previous == SIZE_MAX) d->nodes[parent].first_child = id;
    else d->nodes[previous].next_sibling = id;
    d->last_children[parent] = id;
  }
  return id;
}
static size_t existing(const window_parser *p,uint32_t global) {
  size_t i;
  for (i = 0; i < p->doc->node_count; i++) if (p->map[i] == global) return i;
  return SIZE_MAX;
}
static int attributes(window_parser *p,exr_node *node,const char **attrs,size_t count) {
  size_t i;
  exr_attribute *a = count ? allocate(p,count * sizeof(*a)) : NULL;
  if (p->failed) return 0;
  node->attributes = a; node->attribute_count = count;
  for (i = 0; i < count; i++) {
    a[i].name = copy(p,attrs[2*i],strlen(attrs[2*i]));
    a[i].value = copy(p,attrs[2*i + 1],strlen(attrs[2*i + 1]));
    if (p->failed) return 0;
  }
  return 1;
}
static void pending_free(window_parser *p,exr_node *node) {
  size_t i, bytes = node->name ? strlen(node->name) + 1 : 0;
  for (i = 0; i < node->attribute_count; i++) {
    const exr_attribute *a = &node->attributes[i];
    if (a->name) bytes += strlen(a->name) + 1;
    if (a->value) bytes += strlen(a->value) + 1;
    free((void *)a->name); free((void *)a->value);
  }
  free((void *)node->name); free((void *)node->attributes);
  p->doc->model_bytes -= bytes; p->bytes -= bytes + node->attribute_count*sizeof(exr_attribute);
  *node = (exr_node){0};
}
static int retain_ancestors(window_parser *p) {
  size_t i;
  for (i = 1; i <= p->depth; i++) {
    window_frame *f = &p->stack[i];
    if (f->pending.name) {
      size_t id = append(p,f->global,p->stack[i - 1].local,f->pending.kind,NULL,NULL,0);
      if (p->failed) return 0;
      p->doc->nodes[id].name = f->pending.name;
      p->doc->nodes[id].attributes = f->pending.attributes;
      p->doc->nodes[id].attribute_count = f->pending.attribute_count;
      f->pending = (exr_node){0}; f->local = id;
    }
  }
  return 1;
}
static int selected(const window_parser *p,size_t id) { return id >= p->first && id < p->last; }
static int ancestor(const window_parser *p,size_t id) {
  size_t i;
  for (i = 0; i < p->ancestor_count; i++) if (p->ancestors[i] == id) return 1;
  return 0;
}
static const char *local(const char *name) { const char *at = strrchr(name,'|'); return at ? at + 1 : name; }
static int token(const char *text,const char *wanted) {
  size_t size = strlen(wanted);
  while (text && *text) {
    const char *first;
    while (*text && strchr(" \t\r\n",*text)) text++;
    first = text; while (*text && !strchr(" \t\r\n",*text)) text++;
    if ((size_t)(text - first) == size && !memcmp(first,wanted,size)) return 1;
  }
  return 0;
}
static int match(window_parser *p,size_t id,exr_node_kind kind,const char *name,uint32_t parent) {
  const exr_chapter_entry *n = exr_chapter_index_entry(p->index,id);
  const char *expected = exr_chapter_index_name(p->index,id);
  if (!n || (n->tag_kind & 255u) != (unsigned)kind || n->parent != parent ||
      (name && (!expected || strcmp(name,expected)))) {
    fail(p,EXR_FORMAT,"Chapter replay differs from index"); return 0;
  }
  return 1;
}
static void flush(window_parser *p) {
  if (p->text_global == EXR_CHAPTER_NONE || p->failed) return;
  if (p->consumer) {
    if (!p->stack[p->depth].declaration) {
      (void)append(p,p->text_global,p->stack[p->depth].local,EXR_NODE_TEXT,NULL,NULL,0);
      p->batch_count++;
    }
  } else if (selected(p,p->text_global) || p->stack[p->depth].declaration) {
    const char *text = (p->projection || p->stack[p->depth].declaration) ? (p->text.data ? p->text.data : "") : NULL;
    (void)append(p,p->text_global,p->stack[p->depth].local,EXR_NODE_TEXT,NULL,text,p->text.size);
  }
  p->text.size = 0; p->text_global = EXR_CHAPTER_NONE;
}
static void XMLCALL start(void *context,const char *name,const char **attrs) {
  window_parser *p = context;
  exr_node_kind kind = exr_xml_element_kind(name);
  size_t i, count = 0, id, retained = SIZE_MAX;
  unsigned declaration;
  flush(p); if (p->failed) return;
  if (p->consumer && p->batch_count >= p->batch_nodes && !p->stack[p->depth].declaration && !visit_emit(p,0)) return;
  if (p->depth == 256) { fail(p,EXR_LIMIT,"Chapter window depth exceeds limit"); return; }
  if (!p->depth && strcmp(local(name),"html")) { fail(p,EXR_FORMAT,"Chapter root must be html"); return; }
  while (attrs[count * 2]) count++;
  if (count > 256) { fail(p,EXR_LIMIT,"Chapter window attribute count exceeds limit"); return; }
  for (i = 0; i < count; i++) {
    const char *key = attrs[2*i], *value = attrs[2*i + 1];
    if ((!strcmp(key,"http://www.idpf.org/2007/ops|type") && (token(value,"footnote") || token(value,"endnote"))) ||
        (!strcmp(key,"role") && (token(value,"doc-footnote") || token(value,"doc-endnote")))) kind = EXR_NODE_NOTE;
  }
  id = p->global++;
  if (!match(p,id,kind,name,p->stack[p->depth].global)) return;
  declaration = p->stack[p->depth].declaration || !strcmp(local(name),"style") || !strcmp(local(name),"link");
  if (!p->consumer && declaration && !retain_ancestors(p)) return;
  if (p->consumer ? !declaration : selected(p,id) || ancestor(p,id) || declaration) {
    retained = p->consumer ? existing(p,(uint32_t)id) : SIZE_MAX;
    if (retained == SIZE_MAX) {
      retained = append(p,(uint32_t)id,p->stack[p->depth].local,kind,name,NULL,0);
      if (p->failed || !attributes(p,&p->doc->nodes[retained],attrs,count)) return;
    }
    if (p->failed) return;
    if (p->consumer) p->batch_count++;
  }
  {
    int pending = retained == SIZE_MAX && !p->consumer;
    if (retained == SIZE_MAX) retained = p->stack[p->depth].local;
    p->depth++; p->stack[p->depth] = (window_frame){(uint32_t)id,retained,declaration,{0}};
    if (pending) {
      exr_node *node = &p->stack[p->depth].pending;
      node->kind = kind; node->name = copy(p,name,strlen(name));
      (void)attributes(p,node,attrs,count);
    }
  }
}
static void XMLCALL end(void *context,const char *name) {
  window_parser *p = context;
  (void)name; flush(p); if (p->failed) return;
  if (p->depth) { pending_free(p,&p->stack[p->depth].pending); p->depth--; }
  if (p->consumer && p->batch_count >= p->batch_nodes && !p->stack[p->depth].declaration) (void)visit_emit(p,0);
}
static void XMLCALL text(void *context,const char *value,int size) {
  window_parser *p = context;
  if (p->failed || !size) return;
  if (p->text_global == EXR_CHAPTER_NONE) {
    p->text_global = (uint32_t)p->global++;
    if (!match(p,p->text_global,EXR_NODE_TEXT,NULL,p->stack[p->depth].global)) return;
  }
  if (p->consumer) return;
  if ((!p->projection || !selected(p,p->text_global)) && !p->stack[p->depth].declaration) return;
  if ((size_t)size > SIZE_MAX - p->text.size - 1 ||
      !grow(p,(void **)&p->text.data,&p->text.capacity,p->text.size + (size_t)size + 1,1)) return;
  memcpy(p->text.data + p->text.size,value,(size_t)size); p->text.size += (size_t)size;
  p->text.data[p->text.size] = 0;
}
static void XMLCALL entity(void *context,const char *name,int parameter,const char *value,int length,
                           const char *base,const char *system,const char *public_id,const char *notation) {
  (void)name;(void)parameter;(void)value;(void)length;(void)base;(void)system;(void)public_id;(void)notation;
  fail(context,EXR_FORMAT,"Chapter entity declarations are unsupported");
}
static exr_status feed(void *context,const void *data,size_t size,int final,exr_error *error) {
  window_parser *p = context;
  size_t at = 0;
  p->error = error;
  if (p->failed) return p->failed;
  if ((!data && size) || p->finished) return exr_fail(error,EXR_ARGUMENT,"Invalid chapter window feed");
  if (size > EXR_MAX_INPUT - p->fed) return exr_fail(error,EXR_LIMIT,"Chapter source exceeds streaming limit");
  do {
    size_t part = size - at > 32768 ? 32768 : size - at;
    enum XML_Status parsed;
    window_parser *previous;
    exr_status status = exr_control_poll(p->control,EXR_STAGE_READ,p->fed,EXR_MAX_INPUT,error);
    if (status != EXR_OK) return status;
    previous = window_owner; window_owner = p;
    parsed = XML_Parse(p->parser,data ? (const char *)data + at : NULL,(int)part,final && at + part == size);
    window_owner = previous; at += part; p->fed += part;
    if (parsed != XML_STATUS_OK || p->failed) return p->failed ? p->failed : exr_fail(error,
      p->limited ? EXR_LIMIT : XML_GetErrorCode(p->parser) == XML_ERROR_NO_MEMORY ? EXR_MEMORY : EXR_FORMAT,
      "Chapter window XML is invalid or exceeds budget");
  } while (at < size);
  if (final) { flush(p); p->finished = 1; if (p->consumer && !p->failed) (void)visit_emit(p,1); }
  return p->failed;
}
static size_t capacity(size_t count) { size_t n = 64; while (n < count && n <= SIZE_MAX / 2) n *= 2; return n; }
static size_t resident(const window_parser *p) {
  const exr_document *d = p->doc;
  size_t i, bytes = sizeof(*d) + d->node_capacity*sizeof(*d->nodes) +
    d->last_capacity*sizeof(*d->last_children) + p->map_capacity*sizeof(*p->map) +
    d->chapter_capacity*sizeof(*d->chapters) + d->model_bytes +
    d->text_capacity + d->capacity*sizeof(*d->blocks);
  for (i = 0; i < d->node_count; i++) bytes += d->nodes[i].attribute_count*sizeof(exr_attribute);
  return bytes;
}
static int projection_prefix(window_parser *p) {
  exr_document *d = p->doc;
  size_t i, base = SIZE_MAX;
  int needed = 0;
  char *text;
  for (i = 0; i < d->node_count; i++) {
    const exr_node *n = &d->nodes[i];
    const exr_chapter_entry *global = exr_chapter_index_entry(p->index,p->map[i]);
    if (selected(p,p->map[i]) && n->kind == EXR_NODE_TEXT && global->start != EXR_CHAPTER_NONE &&
        n->end > n->start && global->start >= n->start) { base = global->start - n->start; break; }
  }
  if (base == SIZE_MAX || !base) return 1;
  for (i = 0; i < d->node_count; i++) {
    const exr_node *n = &d->nodes[i];
    const exr_chapter_entry *global = exr_chapter_index_entry(p->index,p->map[i]);
    if (selected(p,p->map[i]) && n->kind == EXR_NODE_TEXT && !n->start && !n->end &&
        global->start == global->end && (size_t)global->start + 1 == base) needed = 1;
  }
  if (!needed) return 1;
  /* A block's initial whitespace-only node precedes the projection separator
     inserted by its first visible text. Retain that real leading newline so
     empty and nonempty text ranges share one exact global origin. */
  if (d->size > SIZE_MAX - 2 || resident(p) > p->budget - sizeof(*p) ||
      d->size + 2 > p->budget - sizeof(*p) - resident(p)) {
    fail(p,EXR_LIMIT,"Chapter projection prefix exceeds budget"); return 0;
  }
  text = malloc(d->size + 2);
  if (!text) { fail(p,EXR_MEMORY,"Chapter projection prefix allocation failed"); return 0; }
  text[0] = '\n'; memcpy(text + 1,d->text,d->size + 1); free(d->text);
  d->text = text; d->size++; d->text_capacity = d->size + 1;
  for (i = 0; i < d->node_count; i++) {
    exr_node *n = &d->nodes[i];
    if (n->start == SIZE_MAX) continue;
    if (!i) { n->end++; continue; }
    if (n->start || n->end) { n->start++; n->end++; }
  }
  for (i = 0; i < d->count; i++) { d->blocks[i].start++; d->blocks[i].end++; }
  return 1;
}
static int visit_document(window_parser *p,const exr_document *metadata) {
  p->doc = allocate(p,sizeof(*p->doc));
  if (!p->doc) return 0;
  p->doc->format = metadata->format; p->doc->resources = metadata->resources;
  p->doc->resource_count = metadata->resource_count; p->doc->resource_data = metadata->resource_data;
  p->doc->shared_archive = metadata->shared_archive; p->doc->archive = metadata->archive;
  p->doc->archive_size = metadata->archive_size; p->doc->language = metadata->language; p->doc->title = metadata->title;
  p->doc->load_package = metadata->load_package;
  p->doc->chapters = allocate(p,sizeof(*p->doc->chapters));
  if (!p->doc->chapters) return 0;
  p->doc->chapter_count = p->doc->chapter_capacity = 1;
  if (metadata->chapter_count) p->doc->chapters[0] = metadata->chapters[0];
  p->doc->chapters[0].root = 1; p->doc->chapters[0].in_spine = p->doc->chapters[0].linear = 1;
  (void)append(p,0,SIZE_MAX,EXR_NODE_DOCUMENT,NULL,NULL,0);
  (void)append(p,1,0,EXR_NODE_CHAPTER,NULL,NULL,0);
  return !p->failed;
}
static size_t visit_copy_node(window_parser *p,const exr_node *node,uint32_t global,size_t parent) {
  size_t id = append(p,global,parent,node->kind,node->name,node->text,node->text ? strlen(node->text) : 0), i;
  exr_attribute *attrs;
  if (p->failed) return SIZE_MAX;
  attrs = node->attribute_count ? allocate(p,node->attribute_count*sizeof(*attrs)) : NULL;
  if (p->failed) return SIZE_MAX;
  p->doc->nodes[id].attributes = attrs; p->doc->nodes[id].attribute_count = node->attribute_count;
  for (i = 0; i < node->attribute_count; i++) {
    attrs[i].name = copy(p,node->attributes[i].name,strlen(node->attributes[i].name));
    attrs[i].value = copy(p,node->attributes[i].value,strlen(node->attributes[i].value));
    if (p->failed) return SIZE_MAX;
  }
  return id;
}
static int visit_declarations(window_parser *p) {
  const exr_chapter_window *template = p->declarations;
  size_t i;
  for (i = 2; i < template->node_count; i++) {
    const exr_node *n = &template->document->nodes[i];
    size_t parent = existing(p,template->global_nodes[n->parent]);
    if (existing(p,template->global_nodes[i]) != SIZE_MAX) continue;
    if (parent == SIZE_MAX) { fail(p,EXR_FORMAT,"Chapter declaration ancestor is missing"); return 0; }
    if (visit_copy_node(p,n,template->global_nodes[i],parent) == SIZE_MAX) return 0;
  }
  return 1;
}
static int visit_emit(window_parser *p,int final) {
  exr_chapter_window batch = {0};
  exr_status status;
  window_parser next;
  size_t locals[257], i, previous_bytes, extra = sizeof(next) + sizeof(locals);
  if (!p->batch_count || p->failed) return !p->failed;
  batch.document = p->doc; batch.global_nodes = p->map; batch.node_count = p->doc->node_count;
  /* The high water includes ancestor-copy overlap and parser token buffers,
     so a callback can reserve this visitor's complete transient footprint. */
  account_peak(p); batch.memory_bytes = batch.peak_bytes = p->peak_bytes;
  status = p->consumer(&batch,p->consumer_context,p->error);
  if (status != EXR_OK) { fail(p,status,"Chapter style batch consumer failed"); return 0; }
  if (final) { p->batch_count = 0; return 1; }
  if (extra > p->budget - p->bytes) { fail(p,EXR_LIMIT,"Chapter ancestor copy exceeds budget"); return 0; }
  next = *p; next.doc = NULL; next.map = NULL; next.map_capacity = 0;
  next.bytes += extra; account_peak(&next); previous_bytes = resident(p);
  if (!visit_document(&next,p->doc)) goto failed;
  if (!visit_declarations(&next)) goto failed;
  locals[0] = 1;
  for (i = 1; i <= p->depth; i++) {
    locals[i] = existing(&next,p->stack[i].global);
    if (locals[i] == SIZE_MAX)
      locals[i] = visit_copy_node(&next,&p->doc->nodes[p->stack[i].local],p->stack[i].global,locals[i - 1]);
    if (next.failed) goto failed;
  }
  exr_chapter_window_free(&batch);
  p->doc = next.doc; p->map = next.map; p->map_capacity = next.map_capacity;
  p->bytes = next.bytes - previous_bytes - extra; p->peak_bytes = next.peak_bytes;
  for (i = 0; i <= p->depth; i++) p->stack[i].local = locals[i];
  p->batch_count = 0;
  return 1;
failed:
  batch.document = next.doc; batch.global_nodes = next.map;
  exr_chapter_window_free(&batch);
  p->failed = next.failed; return 0;
}
void exr_chapter_window_free(exr_chapter_window *window) {
  exr_document *d;
  if (!window) return;
  d = window->document;
  if (d) {
    d->resources = NULL; d->resource_count = d->resource_capacity = 0; d->resource_data = NULL;
    d->shared_archive = NULL; d->archive = NULL; d->archive_size = 0;
    d->title = d->language = NULL;
    exr_document_free(d);
  }
  free(window->global_nodes); memset(window,0,sizeof(*window));
}
exr_status exr_chapter_window_load(const exr_chapter_index *index,const exr_document *metadata,
  size_t first,size_t last,int projection,exr_chapter_pump_fn pump,void *source,
  size_t budget,const exr_control *control,exr_chapter_window *out,exr_error *error) {
  const XML_Memory_Handling_Suite allocator = {xml_alloc,xml_realloc,xml_free};
  window_parser *p, *previous;
  exr_status status;
  size_t i, text_bytes = 0;
  exr_chapter_window result = {0};
  if (!out) return exr_fail(error,EXR_ARGUMENT,"Missing chapter window output");
  memset(out,0,sizeof(*out));
  if (!index || !metadata || !pump || first > last || last > exr_chapter_index_count(index))
    return exr_fail(error,EXR_ARGUMENT,"Invalid chapter window input");
  if (budget < sizeof(*p)) return exr_fail(error,EXR_LIMIT,"Chapter window budget is too small");
  p = calloc(1,sizeof(*p));
  if (!p) return exr_fail(error,EXR_MEMORY,"Chapter window state allocation failed");
  p->index = index; p->budget = budget; p->bytes = sizeof(*p); p->error = error; p->control = control;
  p->first = first; p->last = last; p->projection = projection; p->global = 2; p->text_global = EXR_CHAPTER_NONE;
  if (first < last) {
    const exr_chapter_entry *n = exr_chapter_index_entry(index,first);
    uint32_t id = n->parent;
    while (id != EXR_CHAPTER_NONE) {
      if (p->ancestor_count == sizeof(p->ancestors)/sizeof(p->ancestors[0])) { fail(p,EXR_LIMIT,"Chapter ancestor depth exceeds limit"); break; }
      p->ancestors[p->ancestor_count++] = id; id = exr_chapter_index_entry(index,id)->parent;
    }
  }
  p->doc = allocate(p,sizeof(*p->doc));
  if (!p->doc || p->failed) goto done;
  p->doc->format = metadata->format; p->doc->resources = metadata->resources;
  p->doc->resource_count = metadata->resource_count; p->doc->resource_data = metadata->resource_data;
  p->doc->shared_archive = metadata->shared_archive; p->doc->archive = metadata->archive;
  p->doc->archive_size = metadata->archive_size; p->doc->language = metadata->language; p->doc->title = metadata->title;
  p->doc->load_package = metadata->load_package;
  p->doc->chapters = allocate(p,sizeof(*p->doc->chapters));
  if (!p->doc->chapters) goto done;
  p->doc->chapter_count = p->doc->chapter_capacity = 1;
  if (metadata->chapter_count) p->doc->chapters[0] = metadata->chapters[0];
  p->doc->chapters[0].root = 1; p->doc->chapters[0].in_spine = p->doc->chapters[0].linear = 1;
  (void)append(p,0,SIZE_MAX,EXR_NODE_DOCUMENT,NULL,NULL,0);
  (void)append(p,1,0,EXR_NODE_CHAPTER,NULL,NULL,0);
  if (p->failed) goto done;
  p->stack[0] = (window_frame){1,1,0,{0}};
  previous = window_owner; window_owner = p;
  p->parser = XML_ParserCreate_MM(NULL,&allocator,"|"); window_owner = previous;
  if (!p->parser) { fail(p,p->limited ? EXR_LIMIT : EXR_MEMORY,"Chapter window XML allocation failed"); goto done; }
  XML_SetUserData(p->parser,p); XML_SetElementHandler(p->parser,start,end);
  XML_SetCharacterDataHandler(p->parser,text); XML_SetEntityDeclHandler(p->parser,entity);
  XML_SetParamEntityParsing(p->parser,XML_PARAM_ENTITY_PARSING_NEVER);
  status = pump(source,feed,p,control,error);
  if (status != EXR_OK) { p->failed = status; goto done; }
  if (!p->finished || p->global != exr_chapter_index_count(index)) { fail(p,EXR_FORMAT,"Chapter replay is incomplete"); goto done; }
  XML_ParserFree(p->parser); p->parser = NULL;
  free(p->text.data); p->bytes -= p->text.capacity; p->text.data = NULL; p->text.capacity = 0;
  if (projection) {
    size_t upper, blocks, reserve;
    for (i = 0; i < p->doc->node_count; i++) if (p->doc->nodes[i].text) text_bytes += strlen(p->doc->nodes[i].text);
    if (text_bytes > SIZE_MAX - p->doc->node_count - 1) { fail(p,EXR_LIMIT,"Chapter projection size overflow"); goto done; }
    upper = capacity(text_bytes + p->doc->node_count + 1); blocks = capacity(p->doc->node_count);
    if (blocks > SIZE_MAX / sizeof(exr_block) || upper > SIZE_MAX / 2 || blocks*sizeof(exr_block) > (SIZE_MAX - 2*upper)/2) {
      fail(p,EXR_LIMIT,"Chapter projection capacity overflow"); goto done;
    }
    reserve = 2*upper + 2*blocks*sizeof(exr_block);
    if (reserve > p->budget - p->bytes) { fail(p,EXR_LIMIT,"Chapter projection exceeds window budget"); goto done; }
    /* model_finish grows and shrinks arrays internally. This preflight reserve
       is a conservative upper bound including old/new allocation overlap. */
    if(p->bytes+reserve>p->peak_bytes) p->peak_bytes=p->bytes+reserve;
    status = exr_model_finish(p->doc,error);
    if (status != EXR_OK) { p->failed = status; goto done; }
    if (!projection_prefix(p)) goto done;
    result.text_base = SIZE_MAX;
    for (i = 0; i < p->doc->node_count; i++) {
      const exr_node *n = &p->doc->nodes[i];
      const exr_chapter_entry *global = exr_chapter_index_entry(index,p->map[i]);
      size_t base;
      if (!selected(p,p->map[i]) || n->kind != EXR_NODE_TEXT || global->start == EXR_CHAPTER_NONE) continue;
      if (n->start == SIZE_MAX || n->end < n->start || global->start < n->start) {
        fail(p,EXR_FORMAT,"Chapter window projection differs from index"); goto done;
      }
      base = (size_t)global->start - n->start;
      if (result.text_base == SIZE_MAX) result.text_base = base;
      if (base != result.text_base || n->end > SIZE_MAX - base || n->end + base != global->end) {
        fail(p,EXR_FORMAT,"Chapter window projection differs from index"); goto done;
      }
    }
    if (result.text_base == SIZE_MAX) result.text_base = 0;
  }
  status = exr_control_cancel(control,error);
  if (status != EXR_OK) { p->failed = status; goto done; }
done:
  status = p->failed;
  if (p->parser) XML_ParserFree(p->parser);
  for (i = 1; i <= p->depth; i++) pending_free(p,&p->stack[i].pending);
  free(p->text.data);
  result.document = p->doc; result.global_nodes = p->map;
  if (!status) {
    result.node_count = p->doc->node_count; result.memory_bytes = resident(p);result.peak_bytes=p->peak_bytes;
    result.first=first;result.last=last;
    *out = result;
  } else exr_chapter_window_free(&result);
  free(p); return status;
}
exr_status exr_chapter_windows_visit(const exr_chapter_index *index,const exr_document *metadata,
  size_t batch_nodes,exr_chapter_pump_fn pump,void *source,size_t budget,const exr_control *control,
  exr_chapter_window_consumer_fn consumer,void *context,exr_error *error) {
  const XML_Memory_Handling_Suite allocator = {xml_alloc,xml_realloc,xml_free};
  exr_chapter_window declarations = {0}, batch = {0};
  window_parser *p = NULL, *previous;
  exr_status status;
  if (!index || !metadata || !batch_nodes || !pump || !consumer)
    return exr_fail(error,EXR_ARGUMENT,"Invalid chapter style visitor input");
  status = exr_chapter_window_load(index,metadata,0,0,0,pump,source,budget,control,&declarations,error);
  if (status != EXR_OK) return status;
  if (declarations.memory_bytes > budget || sizeof(*p) > budget - declarations.memory_bytes) {
    exr_chapter_window_free(&declarations);
    return exr_fail(error,EXR_LIMIT,"Chapter style visitor exceeds budget");
  }
  p = calloc(1,sizeof(*p));
  if (!p) { exr_chapter_window_free(&declarations); return exr_fail(error,EXR_MEMORY,"Chapter style visitor allocation failed"); }
  p->index = index; p->budget = budget; p->bytes = sizeof(*p) + declarations.memory_bytes;
  p->control = control; p->error = error; p->global = 2; p->text_global = EXR_CHAPTER_NONE;
  p->consumer = consumer; p->consumer_context = context; p->batch_nodes = batch_nodes; p->declarations = &declarations;
  if (!visit_document(p,metadata) || !visit_declarations(p)) goto done;
  p->stack[0] = (window_frame){1,1,0,{0}};
  previous = window_owner; window_owner = p;
  p->parser = XML_ParserCreate_MM(NULL,&allocator,"|"); window_owner = previous;
  if (!p->parser) { fail(p,p->limited ? EXR_LIMIT : EXR_MEMORY,"Chapter visitor XML allocation failed"); goto done; }
  XML_SetUserData(p->parser,p); XML_SetElementHandler(p->parser,start,end);
  XML_SetCharacterDataHandler(p->parser,text); XML_SetEntityDeclHandler(p->parser,entity);
  XML_SetParamEntityParsing(p->parser,XML_PARAM_ENTITY_PARSING_NEVER);
  status = pump(source,feed,p,control,error);
  if (status != EXR_OK) p->failed = status;
  else if (!p->finished || p->global != exr_chapter_index_count(index)) fail(p,EXR_FORMAT,"Chapter style replay is incomplete");
done:
  status = p->failed;
  if (p->parser) XML_ParserFree(p->parser);
  batch.document = p->doc; batch.global_nodes = p->map;
  exr_chapter_window_free(&batch); exr_chapter_window_free(&declarations);
  free(p); return status;
}
