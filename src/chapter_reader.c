/* SPDX-License-Identifier: MIT */
#include "chapter_internal.h"
#include "layout_internal.h"

typedef struct { exr_style value; uint64_t hash; } retained_style;
typedef struct {
  exr_publication *publication;
  const exr_pager *pager;
  const exr_document *metadata;
  size_t part;
  exr_chapter_index *index;
  exr_document document;
  exr_chapter chapter;
  exr_document_view view;
  exr_chapter_window window;
  uint32_t *styles;
  uint32_t *text_nodes;
  size_t text_count;
  exr_control active_control;
  retained_style **pool;
  size_t pool_count,pool_capacity,pool_bytes;
  exr_font_rule *font_rules;
  size_t font_count,font_bytes;
  exr_layout_config config;
  exr_chapter_options options;
  size_t scratch_bytes,scratch_budget,visitor_reserve,peak_workspace,windows_loaded,windows_evicted;
  size_t io_bytes,io_peak,io_budget;
  int io_limited;
  exr_status failed;
  exr_style empty_style;
} chapter_reader;

static size_t index_bytes(const chapter_reader *r) {
  return exr_chapter_index_memory(r->index)+
    (r->styles ? exr_chapter_index_count(r->index)*sizeof(*r->styles) : 0)+
    (r->text_nodes ? r->text_count*sizeof(*r->text_nodes) : 0)+exr_publication_index_memory(r->publication);
}
static size_t workspace_bytes(const chapter_reader *r) {
  return sizeof(*r)+exr_pager_continuation_bytes(r->pager)+r->pool_bytes+r->window.memory_bytes+r->scratch_bytes+r->io_bytes+
    r->font_bytes+(r->config.user_css ? strlen(r->config.user_css)+1 : 0);
}
static size_t available_bytes(const chapter_reader *r) {
  size_t used=index_bytes(r)+workspace_bytes(r);
  if(r->io_budget>r->io_bytes) used+=r->io_budget-r->io_bytes;
  if(r->scratch_budget>r->scratch_bytes) used+=r->scratch_budget-r->scratch_bytes;
  return used<r->options.workspace_budget ? r->options.workspace_budget-used : 0;
}
static void peak(chapter_reader *r) {
  size_t bytes=workspace_bytes(r);if(bytes>r->peak_workspace) r->peak_workspace=bytes;
}
typedef struct { exr_allocation_alignment alignment;size_t bytes; } source_allocation;
static void *source_allocate(void *context,size_t size) {
  chapter_reader *r=context;source_allocation *allocation;
  if(size>SIZE_MAX-sizeof(*allocation) || size+sizeof(*allocation)>r->io_budget-r->io_bytes) {
    r->io_limited=1;return NULL;
  }
  allocation=malloc(size+sizeof(*allocation));if(!allocation) return NULL;
  allocation->bytes=size+sizeof(*allocation);r->io_bytes+=allocation->bytes;
  if(r->io_bytes>r->io_peak) r->io_peak=r->io_bytes;
  peak(r);return allocation+1;
}
static void source_release(void *context,void *data) {
  chapter_reader *r=context;source_allocation *allocation;
  if(!data) return;
  allocation=(source_allocation *)data-1;r->io_bytes-=allocation->bytes;free(allocation);
}
static void *source_reallocate(void *context,void *data,size_t size) {
  source_allocation *old;void *replacement;
  if(!data) return source_allocate(context,size);
  if(!size) { source_release(context,data);return NULL; }
  old=(source_allocation *)data-1;replacement=source_allocate(context,size);
  if(!replacement) return NULL;
  memcpy(replacement,data,size<old->bytes-sizeof(*old) ? size : old->bytes-sizeof(*old));
  source_release(context,data);return replacement;
}
static exr_status pump(void *context,exr_chapter_sink_fn sink,void *target,
                        const exr_control *control,exr_error *e) {
  chapter_reader *r=context;
  exr_resource_allocator allocator={r,source_allocate,source_reallocate,source_release};
  exr_status status;
  r->io_limited=0;
  status=exr_epub_chapter_feed_bounded(r->metadata,r->part,sink,target,&allocator,control,e);
  if(status!=EXR_OK && r->io_limited) return exr_fail(e,EXR_LIMIT,"Chapter source workspace exceeds budget");
  return status;
}
static exr_status index_feed(void *context,const void *data,size_t size,int final,exr_error *e) {
  return exr_chapter_index_feed(context,data,size,final,e);
}
static uint64_t style_hash(const exr_style *value,const char *family) {
  const unsigned char *bytes=(const unsigned char *)value;
  uint64_t hash=UINT64_C(14695981039346656037);
  size_t i;
  for(i=0;i<sizeof(*value);i++) { hash^=bytes[i];hash*=UINT64_C(1099511628211); }
  for(i=0;family && family[i];i++) { hash^=(unsigned char)family[i];hash*=UINT64_C(1099511628211); }
  return hash;
}
static exr_status intern_style(chapter_reader *r,const exr_style *style,uint32_t *id,exr_error *e) {
  exr_style comparable=*style;
  uint64_t hash;
  size_t i,length=style->family ? strlen(style->family)+1 : 0;
  retained_style *item;
  comparable.family=NULL;comparable.family_owned=0;
  hash=style_hash(&comparable,style->family);
  for(i=0;i<r->pool_count;i++) if(r->pool[i]->hash==hash) {
    exr_style candidate=r->pool[i]->value;
    const char *family=candidate.family;
    candidate.family=NULL;candidate.family_owned=0;
    if(!memcmp(&candidate,&comparable,sizeof(candidate)) &&
       ((!family && !style->family) || (family && style->family && !strcmp(family,style->family)))) {
      *id=(uint32_t)i;return EXR_OK;
    }
  }
  if(r->pool_count==UINT32_MAX || sizeof(*item)+length>available_bytes(r))
    return exr_fail(e,EXR_LIMIT,"Chapter computed styles exceed workspace budget");
  if(r->pool_count==r->pool_capacity) {
    size_t capacity=r->pool_capacity ? r->pool_capacity*2 : 32;
    size_t extra=(capacity-r->pool_capacity)*sizeof(*r->pool);
    retained_style **grown;
    if(extra+sizeof(*item)+length>available_bytes(r))
      return exr_fail(e,EXR_LIMIT,"Chapter computed styles exceed workspace budget");
    grown=realloc(r->pool,capacity*sizeof(*r->pool));
    if(!grown) return exr_fail(e,EXR_MEMORY,"Chapter style directory allocation failed");
    r->pool=grown;r->pool_capacity=capacity;r->pool_bytes+=extra;
  }
  item=malloc(sizeof(*item));
  if(!item) return exr_fail(e,EXR_MEMORY,"Chapter style allocation failed");
  item->value=comparable;item->hash=hash;
  if(length) {
    item->value.family=exr_copy(style->family,length-1);
    if(!item->value.family) { free(item);return exr_fail(e,EXR_MEMORY,"Chapter style family allocation failed"); }
  }
  r->pool[r->pool_count]=item;*id=(uint32_t)r->pool_count++;
  r->pool_bytes+=sizeof(*item)+length;peak(r);return EXR_OK;
}
static const void *node_style(void *context,size_t node) {
  chapter_reader *r=context;
  if(node<r->document.node_count && r->styles[node]<r->pool_count)
    return &r->pool[r->styles[node]]->value;
  r->failed=EXR_FORMAT;return &r->empty_style;
}
static exr_status set_writing(void *context,size_t node,int mode,exr_error *e) {
  chapter_reader *r=context;
  exr_style style=*(const exr_style *)node_style(r,node);
  if(r->failed) return exr_fail(e,r->failed,"Invalid chapter style index");
  style.writing_mode=(exr_writing_mode)mode;
  return intern_style(r,&style,&r->styles[node],e);
}
static size_t local_node(const chapter_reader *r,size_t global) {
  size_t lo=0,hi=r->window.node_count;
  while(lo<hi) {
    size_t mid=lo+(hi-lo)/2;
    if(r->window.global_nodes[mid]<global) lo=mid+1;else hi=mid;
  }
  return lo<r->window.node_count && r->window.global_nodes[lo]==global ? lo : SIZE_MAX;
}
static size_t coordinate(uint32_t value) { return value==EXR_CHAPTER_NONE ? SIZE_MAX : value; }
static exr_node node_view(void *context,size_t node) {
  chapter_reader *r=context;
  const exr_chapter_entry *n=exr_chapter_index_entry(r->index,node);
  exr_node result={0};
  size_t local;
  result.parent=result.first_child=result.next_sibling=result.start=result.end=SIZE_MAX;
  if(!n) { r->failed=EXR_FORMAT;return result; }
  result.kind=(exr_node_kind)(n->tag_kind&255);
  result.name=exr_chapter_index_name(r->index,node);
  result.parent=coordinate(n->parent);result.first_child=coordinate(n->first_child);
  result.next_sibling=coordinate(n->next_sibling);result.start=coordinate(n->start);result.end=coordinate(n->end);
  local=local_node(r,node);
  if(local!=SIZE_MAX) {
    const exr_node *resident=&r->window.document->nodes[local];
    result.text=resident->text;result.attributes=resident->attributes;result.attribute_count=resident->attribute_count;
  }
  return result;
}
static exr_status prepare(void *context,size_t node,const exr_control *control,exr_error *e);
static const char *text_view(void *context,size_t offset,size_t *available) {
  chapter_reader *r=context;
  size_t lo=0,hi=r->text_count;
  exr_error error={0};
  *available=0;
  if(offset==r->document.size) return "";
  if(offset>r->document.size) { r->failed=EXR_FORMAT;return NULL; }
  if(r->window.document && offset>=r->window.text_base &&
     offset-r->window.text_base<r->window.document->size) {
    size_t local=offset-r->window.text_base;
    *available=r->window.document->size-local;
    return r->window.document->text ? r->window.document->text+local : "";
  }
  while(lo<hi) {
    size_t mid=lo+(hi-lo)/2;
    const exr_chapter_entry *n=exr_chapter_index_entry(r->index,r->text_nodes[mid]);
    if(n->end<=offset) lo=mid+1;else hi=mid;
  }
  if(lo<r->text_count) {
    const exr_chapter_entry *n=exr_chapter_index_entry(r->index,r->text_nodes[lo]);
    if(n->start>offset && n->start-offset==1) { *available=1;return "\n"; }
    if(n->start<=offset && prepare(r,r->text_nodes[lo],&r->active_control,&error)==EXR_OK &&
       offset>=r->window.text_base && offset-r->window.text_base<r->window.document->size) {
      size_t local=offset-r->window.text_base;
      *available=r->window.document->size-local;return r->window.document->text+local;
    }
  }
  if(!r->failed) r->failed=EXR_FORMAT;
  return NULL;
}
static size_t subtree_end(const chapter_reader *r,size_t node) {
  while(node!=SIZE_MAX) {
    const exr_chapter_entry *n=exr_chapter_index_entry(r->index,node);
    if(n->next_sibling!=EXR_CHAPTER_NONE) return n->next_sibling;
    node=coordinate(n->parent);
  }
  return exr_chapter_index_count(r->index);
}
static int atomic(const chapter_reader *r,size_t node) {
  const exr_chapter_entry *n=exr_chapter_index_entry(r->index,node);
  const exr_style *s=node_style((void *)r,node);
  const char *name=exr_chapter_index_name(r->index,node),*tag=name ? strrchr(name,'|') : NULL;
  if(!tag) tag=name;else tag++;
  const exr_style *parent=n->parent==EXR_CHAPTER_NONE ? s : node_style((void *)r,n->parent);
  return (n->tag_kind&255)==EXR_NODE_TABLE || (tag && !strcmp(tag,"ruby")) ||
    s->float_side || s->display==EXR_CSS_TABLE || (node>1 && s->writing_mode!=parent->writing_mode);
}
static size_t unit_root(chapter_reader *r,size_t node) {
  size_t current=node,root=node;
  const exr_style *style=node_style(r,node);
  if(style->display==EXR_CSS_INLINE || (exr_chapter_index_entry(r->index,node)->tag_kind&255)==EXR_NODE_TEXT) {
    while(exr_chapter_index_entry(r->index,root)->parent!=EXR_CHAPTER_NONE) {
      root=exr_chapter_index_entry(r->index,root)->parent;
      if(((const exr_style *)node_style(r,root))->display!=EXR_CSS_INLINE) break;
    }
  }
  while(current!=SIZE_MAX) {
    if(atomic(r,current)) root=current;
    current=coordinate(exr_chapter_index_entry(r->index,current)->parent);
  }
  return root;
}
static exr_status prepare(void *context,size_t node,const exr_control *control,exr_error *e) {
  chapter_reader *r=context;
  const exr_chapter_entry *n;
  size_t first,last,i,target;
  exr_status status;
  if(control) r->active_control=*control;
  control=&r->active_control;
  peak(r);
  if(r->failed) return exr_fail(e,r->failed,"Chapter reader has failed");
  if(node>=r->document.node_count) return exr_fail(e,EXR_FORMAT,"Invalid chapter node");
  if(local_node(r,node)!=SIZE_MAX && (!atomic(r,node) ||
     (node>=r->window.first && subtree_end(r,node)<=r->window.last)))
    return exr_control_cancel(control,e);
  first=unit_root(r,node);
  n=exr_chapter_index_entry(r->index,first);
  /* A container is supplied by the ancestor chain of its first visible unit. */
  if(!atomic(r,first) && n->first_child!=EXR_CHAPTER_NONE &&
     n->source_end-n->source_start>r->options.window_bytes) {
    size_t child=n->first_child;
    while(child!=EXR_CHAPTER_NONE) {
      const exr_chapter_entry *candidate=exr_chapter_index_entry(r->index,child);
      const exr_style *s=node_style(r,child);
      if(s->display!=EXR_CSS_NONE && candidate->start!=EXR_CHAPTER_NONE && candidate->end>candidate->start) break;
      child=candidate->next_sibling;
    }
    /* Inline/text children can map back to this same oversized block. Load
       that complete unit under the workspace budget instead of recursing. */
    if(child!=EXR_CHAPTER_NONE && unit_root(r,child)!=first)
      return prepare(r,child,control,e);
  }
  last=subtree_end(r,first);
  target=n->source_start+r->options.window_bytes;
  /* Extend only through complete real block units, independent of page seals. */
  for(i=last;i<r->document.node_count;i++) {
    const exr_chapter_entry *candidate=exr_chapter_index_entry(r->index,i);
    const char *name=exr_chapter_index_name(r->index,i),*tag=name ? strrchr(name,'|') : NULL;
    size_t end;
    if(candidate->source_start>=target) break;
    if(!tag) tag=name;else tag++;
    if(!tag || !exr_projection_boundary((exr_node_kind)(candidate->tag_kind&255),tag) ||
       candidate->source_end>target || unit_root(r,i)!=i) continue;
    end=subtree_end(r,i);if(end>last) last=end;
  }
  if(r->window.document) { exr_chapter_window_free(&r->window);r->windows_evicted++; }
  status=exr_chapter_window_load(r->index,&r->document,first,last,1,pump,r,
                                available_bytes(r),control,&r->window,e);
  if(status!=EXR_OK) { r->failed=status;return status; }
  r->windows_loaded++;peak(r);
  {
    size_t bound=workspace_bytes(r)-r->window.memory_bytes+r->window.peak_bytes+r->io_peak;
    if(bound>r->peak_workspace) r->peak_workspace=bound;
  }
  if(local_node(r,node)==SIZE_MAX) {
    r->failed=EXR_FORMAT;return exr_fail(e,EXR_FORMAT,"Chapter window omits its requested node");
  }
  return EXR_OK;
}
static exr_status view_status(void *context,exr_error *e) {
  chapter_reader *r=context;
  return r->failed ? exr_fail(e,r->failed,"Chapter view access failed") : EXR_OK;
}
static exr_status style_batch(const exr_chapter_window *window,void *context,exr_error *e) {
    chapter_reader *r=context;
    size_t count=exr_chapter_index_count(r->index),i;
    exr_status status;
    exr_style *styles=NULL;
    exr_font_rule *fonts=NULL;
    size_t font_count=0;
    exr_style_memory memory={0};
    r->scratch_bytes=window->memory_bytes;r->scratch_budget=r->visitor_reserve;
    if(index_bytes(r)>r->options.workspace_budget || workspace_bytes(r)>r->options.workspace_budget-index_bytes(r)) {
      r->scratch_bytes=0;
      return exr_fail(e,EXR_LIMIT,"Chapter style batch exceeds workspace budget");
    }
    status=exr_compute_styles_bounded(window->document,&r->config,available_bytes(r),&styles,&fonts,&font_count,&memory,e);
    r->scratch_bytes=window->memory_bytes+memory.peak_bytes+r->io_peak;peak(r);
    if(status==EXR_OK) {
      r->scratch_bytes=window->memory_bytes+memory.retained_bytes;
      r->scratch_budget=r->visitor_reserve+memory.retained_bytes;
      for(i=0;i<window->node_count && status==EXR_OK;i++) {
        size_t global=window->global_nodes[i];
        if(global<count && r->styles[global]==UINT32_MAX)
          status=intern_style(r,&styles[i],&r->styles[global],e);
      }
      if(status==EXR_OK && !r->font_rules) {
        r->font_rules=fonts;r->font_count=font_count;r->font_bytes=memory.retained_fonts_bytes;fonts=NULL;
        r->scratch_bytes-=r->font_bytes;r->scratch_budget-=r->font_bytes;
      }
    }
    exr_styles_free(styles,window->node_count);free(fonts);
    r->scratch_bytes=r->scratch_budget=0;return status;
}
static exr_status compute_styles(chapter_reader *r,exr_error *e) {
  exr_status status;
  r->visitor_reserve=available_bytes(r)/2;
  status=exr_chapter_windows_visit(r->index,&r->document,4096,pump,r,
    r->visitor_reserve,&r->config.control,style_batch,r,e);
  r->visitor_reserve=0;
  return status;
}
static void reader_free(void *context) {
  chapter_reader *r=context;
  size_t i;
  if(!r) return;
  exr_chapter_window_free(&r->window);
  for(i=0;i<r->pool_count;i++) { free((void *)r->pool[i]->value.family);free(r->pool[i]); }
  free(r->pool);free(r->styles);free(r->text_nodes);free(r->font_rules);free((void *)r->config.user_css);
  exr_chapter_index_free(r->index);exr_publication_free(r->publication);free(r);
}
static exr_chapter_stats statistics(const void *context) {
  const chapter_reader *r=context;
  exr_chapter_stats stats={0};
  stats.book_bytes=r->metadata->archive_size;stats.index_bytes=index_bytes(r);
  stats.node_count=exr_chapter_index_count(r->index);stats.projection_bytes=r->document.size;
  stats.parse_workspace_bytes=workspace_bytes(r);stats.peak_parse_workspace_bytes=r->peak_workspace;
  stats.windows_loaded=r->windows_loaded;stats.windows_evicted=r->windows_evicted;
  return stats;
}
exr_status exr_chapter_cfi_create(void *context,const exr_cfi_point *point,size_t scalars,
  const exr_control *control,char **cfi,exr_error *e) {
  chapter_reader *r=context;
  if(scalars>32) return exr_fail(e,EXR_ARGUMENT,"CFI context exceeds 32 scalars");
  return exr_cfi_create_for_part(r->metadata,r->part,&r->document,0,point,scalars,control,cfi,e);
}
exr_status exr_chapter_cfi_resolve(void *context,const char *cfi,const exr_control *control,
  exr_cfi_point *point,exr_error *e) {
  chapter_reader *r=context;char *local=NULL;size_t part;
  exr_status status=exr_cfi_route(r->metadata,cfi,control,&part,&local,e);
  if(status==EXR_OK && part!=r->part) status=exr_fail(e,EXR_ARGUMENT,"CFI belongs to another publication part");
  if(status==EXR_OK) status=exr_document_cfi_path_resolve(&r->document,0,local,control,point,e);
  free(local);return status;
}
exr_chapter_options exr_chapter_options_defaults(void) {
  return (exr_chapter_options){sizeof(exr_chapter_options),64u*1024*1024,4u*1024*1024};
}
exr_status exr_publication_pager_create(exr_publication *publication,size_t part,
  exr_font *font,const exr_layout_config *config,const exr_chapter_options *options,
  exr_pager **out,exr_error *e) {
  chapter_reader *r;
  exr_chapter_options defaults=exr_chapter_options_defaults();
  exr_layout_config default_config=exr_layout_config_defaults();
  exr_status status;
  size_t count,css_size=0;
  if(!out) return exr_fail(e,EXR_ARGUMENT,"Missing chapter pager output");
  *out=NULL;
  if(!font) return exr_fail(e,EXR_ARGUMENT,"Missing chapter font");
  if(!options) options=&defaults;
  if(options->size<sizeof(*options) || options->workspace_budget<1024*1024 ||
     options->workspace_budget>EXR_MAX_INPUT || !options->window_bytes || options->window_bytes>32u*1024*1024)
    return exr_fail(e,EXR_ARGUMENT,"Invalid chapter workspace or window budget");
  if(!config) config=&default_config;
  status=exr_layout_validate(config,e);if(status!=EXR_OK) return status;
  r=calloc(1,sizeof(*r));
  if(!r) return exr_fail(e,EXR_MEMORY,"Chapter reader allocation failed");
  r->options=*options;r->config=*config;r->config.user_css=NULL;r->part=part;
  r->io_budget=options->workspace_budget/16;
  if(r->io_budget>1024*1024) r->io_budget=1024*1024;
  r->empty_style.display=EXR_CSS_NONE;
  status=exr_publication_retain_epub(publication,&r->metadata,e);
  if(status!=EXR_OK) { reader_free(r);return status; }
  r->publication=publication;
  if(part>=r->metadata->chapter_count) { reader_free(r);return exr_fail(e,EXR_ARGUMENT,"Invalid chapter index"); }
  if(config->user_css) {
    while(css_size<=1024*1024 && config->user_css[css_size]) css_size++;
    if(css_size>1024*1024) { reader_free(r);return exr_fail(e,EXR_LIMIT,"Chapter CSS exceeds 1 MiB"); }
    r->config.user_css=exr_copy(config->user_css,css_size);
    if(!r->config.user_css) { reader_free(r);return exr_fail(e,EXR_MEMORY,"Chapter CSS allocation failed"); }
  }
  status=exr_chapter_index_begin(&config->control,available_bytes(r),&r->index,e);
  if(status==EXR_OK) status=pump(r,index_feed,r->index,&config->control,e);
  if(status!=EXR_OK) { reader_free(r);return status; }
  r->scratch_bytes=exr_chapter_index_peak(r->index)-exr_chapter_index_memory(r->index)+r->io_peak;
  peak(r);r->scratch_bytes=0;
  count=exr_chapter_index_count(r->index);
  if(count>available_bytes(r)/sizeof(*r->styles)) { reader_free(r);return exr_fail(e,EXR_LIMIT,"Chapter style index exceeds budget"); }
  r->styles=malloc(count*sizeof(*r->styles));
  if(!r->styles) { reader_free(r);return exr_fail(e,EXR_MEMORY,"Chapter style index allocation failed"); }
  memset(r->styles,255,count*sizeof(*r->styles));
  {
    size_t i,at=0;
    for(i=0;i<count;i++) {
      const exr_chapter_entry *n=exr_chapter_index_entry(r->index,i);
      if((n->tag_kind&255)==EXR_NODE_TEXT && n->start!=EXR_CHAPTER_NONE && n->end>n->start) r->text_count++;
    }
    if(r->text_count*sizeof(*r->text_nodes)>available_bytes(r)) {
      reader_free(r);return exr_fail(e,EXR_LIMIT,"Chapter text index exceeds workspace budget");
    }
    r->text_nodes=malloc((r->text_count ? r->text_count : 1)*sizeof(*r->text_nodes));
    if(!r->text_nodes) { reader_free(r);return exr_fail(e,EXR_MEMORY,"Chapter text index allocation failed"); }
    for(i=0;i<count;i++) {
      const exr_chapter_entry *n=exr_chapter_index_entry(r->index,i);
      if((n->tag_kind&255)==EXR_NODE_TEXT && n->start!=EXR_CHAPTER_NONE && n->end>n->start) r->text_nodes[at++]=(uint32_t)i;
    }
  }
  r->document.node_count=count;r->document.format=EXR_EPUB;
  r->document.size=exr_chapter_index_text_size(r->index);
  r->document.resources=r->metadata->resources;r->document.resource_count=r->metadata->resource_count;
  r->document.shared_archive=r->metadata->shared_archive;r->document.archive=r->metadata->archive;
  r->document.archive_size=r->metadata->archive_size;r->document.language=r->metadata->language;
  r->chapter=r->metadata->chapters[part];r->chapter.root=1;r->chapter.in_spine=r->chapter.linear=1;
  r->document.chapters=&r->chapter;r->document.chapter_count=1;
  /* The view's single chapter uses the stable synthetic chapter node. */
  status=compute_styles(r,e);
  if(status!=EXR_OK) { reader_free(r);return status; }
  r->view=(exr_document_view){r,node_view,text_view,node_style,set_writing,
    r->font_rules,r->font_count,prepare,view_status};
  r->document.view=&r->view;
  /* Pager chooses and normalizes the viewport axis before the first window. */
  status=exr_pager_create(&r->document,font,config,out,e);
  if(status!=EXR_OK) { reader_free(r);return status; }
  exr_pager_adopt_chapter(*out,r,reader_free,statistics);
  r->pager=*out;peak(r);
  return EXR_OK;
}

/* Sparse paragraph checkpoints bound retained indexing independently of input
   length. Checkpoints describe the position immediately before a paragraph. */
#define TXT_POINTS 256
typedef struct { size_t paragraph; exr_txt_checkpoint cursor; } txt_point;
typedef struct {
  exr_source source, wrapped;
  exr_control control;
  exr_txt_cursor *cursor;
  txt_point points[TXT_POINTS];
  size_t point_count, stride, count, cached, cached_start, cached_size;
  char *cache;
  exr_document document;
  exr_document_view view;
  exr_chapter chapter;
  exr_style *styles;
  exr_font_rule *fonts;
  size_t font_count;
  exr_error failure;
} txt_view;
static size_t txt_read(void *context,uint64_t offset,void *data,size_t size) {
  txt_view *v=context;
  return v->source.read_at(v->source.context,offset,data,size);
}
static int txt_cancel(void *context) {
  txt_view *v=context;
  return (v->source.control.cancelled && v->source.control.cancelled(v->source.control.context)) ||
    (v->control.cancelled && v->control.cancelled(v->control.context));
}
static exr_status txt_failure(txt_view *v,exr_status status,const exr_error *error) {
  if(status!=EXR_OK && !v->failure.code) {
    if(error) v->failure=*error;
    if(!v->failure.code) v->failure.code=status;
  }
  return status;
}
static exr_status txt_find_paragraph(txt_view *v,size_t paragraph,size_t *start,size_t *length,
                                     const char **text,exr_error *e) {
  size_t i,point=0;uint64_t offset;exr_status status;const char *line;size_t size;
  if(v->failure.code) return exr_fail(e,v->failure.code,v->failure.message);
  if(paragraph>=v->count) return txt_failure(v,exr_fail(e,EXR_FORMAT,"Invalid TXT paragraph"),e);
  for(i=1;i<v->point_count && v->points[i].paragraph<=paragraph;i++) point=i;
  status=exr_txt_cursor_restore(v->cursor,&v->points[point].cursor,e);
  if(status!=EXR_OK) return txt_failure(v,status,e);
  for(i=v->points[point].paragraph;i<=paragraph;i++) {
    status=exr_control_cancel(&v->wrapped.control,e);
    if(status==EXR_OK) status=exr_txt_cursor_next(v->cursor,&offset,&line,&size,e);
    if(status!=EXR_OK) return txt_failure(v,status,e);
    if(!line || offset>SIZE_MAX) return txt_failure(v,exr_fail(e,EXR_FORMAT,"TXT source changed"),e);
  }
  *start=(size_t)offset;*length=size;if(text) *text=line;
  return EXR_OK;
}
static exr_node txt_node(void *context,size_t node) {
  txt_view *v=context;exr_node n={0};size_t paragraph,start,length;exr_error e={0};
  n.parent=n.first_child=n.next_sibling=n.start=n.end=SIZE_MAX;n.chapter=SIZE_MAX;
  if(node>=v->document.node_count) { txt_failure(v,exr_fail(&e,EXR_FORMAT,"Invalid TXT node"),&e);return n; }
  if(node<2) {
    n.kind=node ? EXR_NODE_CHAPTER : EXR_NODE_DOCUMENT;
    n.parent=node ? 0 : SIZE_MAX;n.chapter=node ? 0 : SIZE_MAX;
    n.first_child=node ? 2 : 1;n.start=0;n.end=v->document.size;return n;
  }
  paragraph=(node-2)/2;
  if(txt_find_paragraph(v,paragraph,&start,&length,NULL,&e)!=EXR_OK) return n;
  n.chapter=0;n.start=start;n.end=start+length;
  if(!(node&1)) {
    n.kind=EXR_NODE_PARAGRAPH;n.name="p";n.parent=1;n.first_child=node+1;
    if(paragraph+1<v->count) n.next_sibling=node+2;
  } else {
    n.kind=EXR_NODE_TEXT;n.parent=node-1;
    if(v->cached==paragraph) n.text=v->cache;
  }
  return n;
}
static exr_status txt_prepare(void *context,size_t node,const exr_control *control,exr_error *e) {
  txt_view *v=context;size_t paragraph,start,length;const char *line;char *copy;exr_status status;
  if(control) v->control=*control;
  if(v->failure.code) return exr_fail(e,v->failure.code,v->failure.message);
  status=exr_control_cancel(&v->wrapped.control,e);if(status!=EXR_OK) return txt_failure(v,status,e);
  if(node>=v->document.node_count) return txt_failure(v,exr_fail(e,EXR_FORMAT,"Invalid TXT node"),e);
  if(node<2) return EXR_OK;
  paragraph=(node-2)/2;if(v->cached==paragraph) return EXR_OK;
  status=txt_find_paragraph(v,paragraph,&start,&length,&line,e);if(status!=EXR_OK) return status;
  copy=exr_copy(line,length);if(!copy) return txt_failure(v,exr_fail(e,EXR_MEMORY,"TXT window allocation failed"),e);
  free(v->cache);v->cache=copy;v->cached=paragraph;v->cached_start=start;v->cached_size=length;
  return EXR_OK;
}
static const char *txt_text(void *context,size_t offset,size_t *available) {
  txt_view *v=context;size_t lo=0,hi=v->count,start,length;exr_error e={0};
  *available=0;if(offset==v->document.size) return "";
  if(offset>v->document.size) { txt_failure(v,exr_fail(&e,EXR_FORMAT,"Invalid TXT offset"),&e);return NULL; }
  if(v->cached!=SIZE_MAX && offset>=v->cached_start && offset-v->cached_start<v->cached_size) {
    *available=v->cached_size-(offset-v->cached_start);return v->cache+(offset-v->cached_start);
  }
  while(lo<hi) {
    size_t mid=lo+(hi-lo)/2;
    if(txt_find_paragraph(v,mid,&start,&length,NULL,&e)!=EXR_OK) return NULL;
    if(start+length<=offset) lo=mid+1;else hi=mid;
  }
  if(lo==v->count) { txt_failure(v,exr_fail(&e,EXR_FORMAT,"Missing TXT span"),&e);return NULL; }
  if(txt_find_paragraph(v,lo,&start,&length,NULL,&e)!=EXR_OK) return NULL;
  if(offset<start && start-offset==1) { *available=1;return "\n"; }
  if(offset<start) { txt_failure(v,exr_fail(&e,EXR_FORMAT,"Invalid TXT gap"),&e);return NULL; }
  if(txt_prepare(v,2+2*lo,NULL,&e)!=EXR_OK) return NULL;
  *available=length-(offset-start);return v->cache+(offset-start);
}
static const void *txt_style(void *context,size_t node) {
  txt_view *v=context;
  return &v->styles[node<2 ? node : (node&1 ? 3 : 2)];
}
static exr_status txt_writing(void *context,size_t node,int mode,exr_error *e) {
  txt_view *v=context;
  if(node>=v->document.node_count) return exr_fail(e,EXR_FORMAT,"Invalid TXT style node");
  /* The pager changes only the anonymous wrapper chain. A lone paragraph can
     occur in that chain, so its shared style is safe only when count is one. */
  if(node>=2 && v->count!=1) return exr_fail(e,EXR_UNSUPPORTED,"TXT writing mode requires a unique node");
  v->styles[node<2 ? node : (node&1 ? 3 : 2)].writing_mode=(exr_writing_mode)mode;
  return EXR_OK;
}
static exr_status txt_status(void *context,exr_error *e) {
  txt_view *v=context;return v->failure.code ? exr_fail(e,v->failure.code,v->failure.message) : EXR_OK;
}
static void txt_free(void *context) {
  txt_view *v=context;if(!v) return;
  exr_txt_cursor_free(v->cursor);free(v->cache);exr_styles_free(v->styles,4);free(v->fonts);free(v);
}
exr_status exr_txt_pager_create_private(const exr_source *source,exr_font *font,
  const exr_layout_config *config,exr_pager **out,exr_error *e) {
  txt_view *v;exr_document sample={0};exr_layout_config defaults=exr_layout_config_defaults();
  exr_txt_checkpoint before;exr_status status;uint64_t offset;const char *line;size_t length,i;
  if(out) *out=NULL;
  if(!out || !source || !source->read_at || !font) return exr_fail(e,EXR_ARGUMENT,"Invalid TXT pager arguments");
  if(!source->size) return exr_fail(e,EXR_ARGUMENT,"Invalid document bytes");
  if(!config) config=&defaults;
  /* Arbitrary selectors need per-node computed styles; this first adapter only
     supports the resident default stylesheet. */
  if(config->user_css && *config->user_css) return exr_fail(e,EXR_UNSUPPORTED,"TXT view does not support user CSS");
  v=calloc(1,sizeof(*v));if(!v) return exr_fail(e,EXR_MEMORY,"TXT view allocation failed");
  v->source=*source;v->wrapped=*source;v->wrapped.read_at=txt_read;v->wrapped.context=v;
  v->wrapped.control=(exr_control){txt_cancel,NULL,v};v->control=config->control;v->stride=1;v->cached=SIZE_MAX;
  status=exr_txt_cursor_create(&v->wrapped,&v->cursor,e);
  if(status!=EXR_OK) goto fail;
  for(;;) {
    status=exr_txt_cursor_checkpoint(v->cursor,&before,e);if(status!=EXR_OK) goto fail;
    status=exr_txt_cursor_next(v->cursor,&offset,&line,&length,e);if(status!=EXR_OK) goto fail;
    if(!line) break;
    if(offset>SIZE_MAX || length>SIZE_MAX-(size_t)offset || v->count>(SIZE_MAX-4)/2) {
      status=exr_fail(e,EXR_LIMIT,"TXT view extent exceeds platform limits");goto fail;
    }
    if(v->count%v->stride==0) {
      if(v->point_count==TXT_POINTS) {
        for(i=0;i<TXT_POINTS/2;i++) v->points[i]=v->points[i*2];
        v->point_count=TXT_POINTS/2;
        if(v->stride>SIZE_MAX/2) { status=exr_fail(e,EXR_LIMIT,"TXT checkpoint stride overflow");goto fail; }
        v->stride*=2;
      }
      if(v->count%v->stride==0) v->points[v->point_count++]=(txt_point){v->count,before};
    }
    v->count++;v->document.size=(size_t)offset+length;
  }
  if(!v->count) { status=exr_fail(e,EXR_FORMAT,"Document has no supported text content");goto fail; }
  if(v->count) {
    v->document.node_count=2+2*v->count;v->chapter=(exr_chapter){"","",1,SIZE_MAX,1,1};
    v->document.chapters=&v->chapter;v->document.chapter_count=1;
  }
  v->document.format=EXR_TXT;
  sample.format=EXR_TXT;
  if(!exr_add_block(&sample,"sample",6,0) || exr_model_finish(&sample,e)!=EXR_OK) {
    status=exr_fail(e,EXR_MEMORY,"TXT style sample allocation failed");goto sample_fail;
  }
  status=exr_compute_styles(&sample,config,&v->styles,&v->fonts,&v->font_count,e);
sample_fail:
  free(sample.text);free(sample.blocks);exr_model_free(&sample);
  if(status!=EXR_OK) goto fail;
  v->view=(exr_document_view){v,txt_node,txt_text,txt_style,txt_writing,v->fonts,v->font_count,txt_prepare,txt_status};
  v->document.view=&v->view;
  status=exr_pager_create(&v->document,font,config,out,e);
  if(status!=EXR_OK) goto fail;
  status=txt_status(v,e);
  if(status!=EXR_OK) { exr_pager_free(*out);*out=NULL;goto fail; }
  exr_pager_adopt_view(*out,v,txt_free);return EXR_OK;
fail:
  txt_free(v);return status;
}
