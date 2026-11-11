/* SPDX-License-Identifier: MIT */
#include "layout_internal.h"
#include "hyphen_internal.h"
#include <ctype.h>

typedef struct { char *text; size_t size; } search_part;
typedef struct publication_search_index publication_search_index;
static void publication_index_free(publication_search_index *index);
struct exr_publication {
  char *title;
  exr_direction page_progression;
  exr_part *parts;
  size_t count, refs;
  exr_part_load_fn load;
  void *context;
  exr_context_release_fn release;
  exr_navigation *navigation;
  size_t navigation_count, metadata_bytes;
  int navigation_ready, busy;
  exr_toc_entry *toc;
  exr_location *toc_locations;
  size_t toc_count;
  int toc_ready, locations_ready;
  exr_target *missing;
  size_t missing_count, missing_capacity;
  search_part *search;
  int searching;
  publication_search_index *index;
  exr_footnote *footnotes;
  size_t footnote_count, footnote_capacity;
  exr_footnote_reference *references;
  size_t reference_count, reference_capacity;
  int footnotes_ready;
  exr_locate_report locate_report;
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
  publication_index_free(p->index);
  if(p->search) {
    for(i=0;i<p->count;i++) free(p->search[i].text);
    free(p->search);
  }
  exr_navigation_free(p->navigation, p->navigation_count);
  for (i=0;i<p->toc_count;i++) {
    free((void *)p->toc[i].title); free((void *)p->toc[i].target.fragment);
  }
  for (i=0;i<p->missing_count;i++) free((void *)p->missing[i].fragment);
  free(p->missing); free(p->toc); free(p->toc_locations);
  for(i=0;i<p->footnote_count;i++) {
    free((void *)p->footnotes[i].id);free((void *)p->footnotes[i].label);free((void *)p->footnotes[i].text);
  }
  free(p->footnotes);free(p->references);
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
  if (status == EXR_OK) {
    (*out)->navigation_ready = 0;
    (*out)->page_progression=exr_document_page_progression(index);
  }
  free(parts);
  if (status != EXR_OK)
    exr_document_free(index);
  return status;
}
static exr_status publication_book(exr_format format,const void *data,size_t size,exr_publication **out,exr_error *e) {
  exr_format_book *book=NULL; exr_part *parts=NULL; exr_publication_input input={0}; size_t i;
  exr_status status=exr_book_open(format,data,size,&book,e);
  if(status!=EXR_OK) return status;
  parts=calloc(book->index->chapter_count,sizeof(*parts));
  if(!parts) { exr_book_free(book); return exr_fail(e,EXR_MEMORY,"Book part directory allocation failed"); }
  for(i=0;i<book->index->chapter_count;i++) {
    parts[i].id=book->index->chapters[i].id; parts[i].path=book->index->chapters[i].path;
    parts[i].in_reading_order=1;
  }
  input.title=exr_document_title(book->index); input.parts=parts; input.part_count=book->index->chapter_count;
  input.load=exr_book_load; input.context=book; input.release=exr_book_free;
  input.navigation=book->navigation; input.navigation_count=book->navigation_count;
  status=exr_publication_create(&input,out,e); free(parts);
  if(status!=EXR_OK) exr_book_free(book);
  return status;
}
exr_status exr_publication_open_memory(exr_format format, const void *data, size_t size,
                                       exr_publication **out, exr_error *e) {
  return exr_publication_open_memory_ex(format, data, size, NULL, out, e);
}
exr_status exr_publication_open_memory_ex(exr_format format, const void *data, size_t size,
                                          const char *passphrase, exr_publication **out, exr_error *e) {
  exr_document *index = NULL;
  exr_status status;
  if (!out) return exr_fail(e, EXR_ARGUMENT, "Missing publication output");
  *out = NULL;
  if(e) memset(e,0,sizeof(*e));
  if(format==EXR_MOBI || format==EXR_FB2) return publication_book(format,data,size,out,e);
  if (format != EXR_EPUB)
    return exr_fail(e, EXR_FORMAT, "Indexed loading accepts EPUB, MOBI/KF8 and FB2");
  status = exr_epub_index_ex(data, size, passphrase, &index, e);
  return status == EXR_OK ? publication_index(index, out, e) : status;
}
exr_status exr_publication_open_source(const exr_source *source, exr_publication **out, exr_error *e) {
  return exr_publication_open_source_ex(source, NULL, out, e);
}
exr_status exr_publication_open_source_ex(const exr_source *source, const char *passphrase, exr_publication **out, exr_error *e) {
  exr_document *index = NULL;
  exr_status status;
  if (!out) return exr_fail(e, EXR_ARGUMENT, "Missing publication output");
  *out = NULL;
  status = exr_epub_index_source_ex(source, passphrase, &index, e);
  if (status != EXR_OK) return status;
  status = publication_index(index, out, e);
  if (status == EXR_OK) index->shared_archive->source.release = source->release;
  return status;
}

exr_status exr_publication_open(const char *path, exr_publication **out, exr_error *e) {
  return exr_publication_open_ex(path, NULL, out, e);
}
exr_status exr_publication_open_ex(const char *path, const char *passphrase, exr_publication **out, exr_error *e) {
  exr_source source = {0};
  exr_status status;
  if (!out)
    return exr_fail(e, EXR_ARGUMENT, "Missing publication output");
  *out = NULL;
  if (!path)
    return exr_fail(e, EXR_ARGUMENT, "Missing publication path");
  {
    const char *ext=strrchr(path,'.'); exr_format format=0;
    if(ext && (exr_link_case_equal(ext,".mobi") || exr_link_case_equal(ext,".azw3") ||
      exr_link_case_equal(ext,".azw") || exr_link_case_equal(ext,".prc") || exr_link_case_equal(ext,".kf8"))) format=EXR_MOBI;
    if(ext && (exr_link_case_equal(ext,".fb2") || exr_link_case_equal(ext,".fbz") || exr_link_case_equal(ext,".zip"))) format=EXR_FB2;
    if(format) {
      unsigned char *data=NULL; size_t size=0;
      status=exr_read(path,&data,&size,e);
      if(status==EXR_OK) status=exr_publication_open_memory(format,data,size,out,e);
      free(data); return status;
    }
  }
  status = exr_file_source(path, &source, e);
  if (status != EXR_OK) return status;
  status = exr_publication_open_source_ex(&source, passphrase, out, e);
  if (status != EXR_OK) source.release(source.context);
  return status;
}
const char *exr_publication_title(const exr_publication *p) { return p ? p->title : ""; }
exr_direction exr_publication_page_progression(const exr_publication *p) {
  return p && p->page_progression==EXR_DIRECTION_RTL ? EXR_DIRECTION_RTL : EXR_DIRECTION_LTR;
}
size_t exr_publication_index_memory(const exr_publication *p) {
  return p ? sizeof(*p)+p->metadata_bytes+p->count*sizeof(*p->parts)+
    p->navigation_count*sizeof(*p->navigation)+(p->load==exr_book_load ? ((exr_format_book *)p->context)->memory :
      p->load==epub_load ? exr_document_memory_size(p->context)+sizeof(exr_archive_store) : 0) : 0;
}
const exr_part *exr_publication_parts(const exr_publication *p, size_t *count) {
  if (count)
    *count = p ? p->count : 0;
  return p ? p->parts : NULL;
}
static const exr_rendition *part_rendition(const exr_publication *p,size_t part) {
  const exr_document *index=p && p->load==epub_load ? p->context : NULL;
  return index && index->renditions && part<index->rendition_count ? &index->renditions[part] : NULL;
}
exr_status exr_publication_rendition(const exr_publication *p,size_t part,exr_part_rendition *out,exr_error *e) {
  const exr_rendition *r;
  if(!out) return exr_fail(e,EXR_ARGUMENT,"Missing rendition output");
  memset(out,0,sizeof(*out));
  if(!p || part>=p->count) return exr_fail(e,EXR_ARGUMENT,"Invalid publication part");
  r=part_rendition(p,part);
  if(r) {
    out->layout=r->fixed ? EXR_RENDITION_PRE_PAGINATED : EXR_RENDITION_REFLOWABLE;
    out->spread=(exr_spread_side)r->spread;
    out->viewport_width=r->viewport_width; out->viewport_height=r->viewport_height;
  }
  return exr_fail(e,EXR_OK,"");
}
exr_status exr_publication_spreads(const exr_publication *p,exr_spread **out,size_t *count,exr_error *e) {
  exr_spread *list,open={SIZE_MAX,SIZE_MAX,0};
  size_t i,n=0; int rtl,previous=0,none;
  if(!out || !count) return exr_fail(e,EXR_ARGUMENT,"Missing spread output");
  *out=NULL; *count=0;
  if(!p) return exr_fail(e,EXR_ARGUMENT,"Missing publication");
  list=calloc(p->count ? p->count : 1,sizeof(*list));
  if(!list) return exr_fail(e,EXR_MEMORY,"Spread allocation failed");
  rtl=exr_publication_page_progression(p)==EXR_DIRECTION_RTL;
  none=p->load==epub_load && ((const exr_document *)p->context)->spread_none;
#define FLUSH() do { if(open.left!=SIZE_MAX || open.right!=SIZE_MAX) list[n++]=open; open.left=open.right=SIZE_MAX; open.flags=0; } while(0)
  for(i=0;i<p->count;i++) {
    const exr_rendition *r=part_rendition(p,i); int side;
    if(!p->parts[i].in_reading_order) continue;
    if(!r || !r->fixed || none || r->spread==EXR_SPREAD_CENTER) {
      FLUSH(); list[n].left=i; list[n].right=SIZE_MAX; list[n++].flags=EXR_SPREAD_SINGLE;
      previous=0; continue;
    }
    side=r->spread ? r->spread : previous ? (previous==EXR_SPREAD_LEFT ? EXR_SPREAD_RIGHT : EXR_SPREAD_LEFT) :
         rtl ? EXR_SPREAD_LEFT : EXR_SPREAD_RIGHT;
    previous=side;
    /* The reading-order first slot opens a screen: left for ltr, right for rtl. */
    if(side==(rtl ? EXR_SPREAD_RIGHT : EXR_SPREAD_LEFT)) {
      FLUSH(); if(rtl) open.right=i; else open.left=i;
    } else if(rtl ? open.right!=SIZE_MAX && open.left==SIZE_MAX : open.left!=SIZE_MAX && open.right==SIZE_MAX) {
      if(rtl) open.left=i; else open.right=i;
      FLUSH();
    } else {
      FLUSH(); if(rtl) open.left=i; else open.right=i; FLUSH();
    }
  }
  FLUSH();
#undef FLUSH
  *out=list; *count=n;
  return exr_fail(e,EXR_OK,"");
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

static int note_token(const char *s,const char *word) {
  size_t n=strlen(word);
  while(s && *s) {
    while(isspace((unsigned char)*s)) s++;
    if(!strncmp(s,word,n) && (!s[n] || isspace((unsigned char)s[n]))) return 1;
    while(*s && !isspace((unsigned char)*s)) s++;
  }
  return 0;
}
static int note_semantic(const exr_node *n) {
  const char *type=exr_node_attribute(n,"http://www.idpf.org/2007/ops|type");
  if(!type) type=exr_node_attribute(n,"epub:type");
  return note_token(type,"footnote") || note_token(type,"endnote") || note_token(type,"rearnote") ||
    note_token(exr_node_attribute(n,"role"),"doc-footnote") || note_token(exr_node_attribute(n,"role"),"doc-endnote");
}
static const char *note_id(const exr_node *n) {
  const char *id=exr_node_attribute(n,"id");
  return id ? id : exr_node_attribute(n,"http://www.w3.org/XML/1998/namespace|id");
}
static size_t note_find(const exr_publication *p,size_t part,const char *id) {
  size_t i;
  for(i=0;i<p->footnote_count;i++)
    if(p->footnotes[i].target_part==part && !strcmp(p->footnotes[i].id,id)) return i;
  return SIZE_MAX;
}
static exr_status note_add(exr_publication *p,const exr_document *d,size_t part,const exr_node *n,
  const char *id,size_t *index,exr_error *e) {
  exr_footnote v={0};size_t total=0;
  *index=note_find(p,part,id);
  if(*index!=SIZE_MAX) return EXR_OK;
  if(n->start==SIZE_MAX || n->end<n->start || n->end>d->size || p->footnote_count>=65536)
    return exr_fail(e,EXR_LIMIT,"Invalid or excessive footnote range");
  if(copy_string(id,2047,&total,&v.id,e)!=EXR_OK) return e ? e->code : EXR_MEMORY;
  v.label=exr_copy(id,strlen(id));v.text=exr_copy(d->text+n->start,n->end-n->start);
  v.target_part=part;v.target_offset=n->start;
  if(!v.label || !v.text || !exr_grow((void **)&p->footnotes,&p->footnote_capacity,p->footnote_count+1,sizeof(v))) {
    free((void *)v.id);free((void *)v.label);free((void *)v.text);
    return exr_fail(e,EXR_MEMORY,"Footnote allocation failed");
  }
  *index=p->footnote_count;p->footnotes[p->footnote_count++]=v;return EXR_OK;
}
exr_status exr_publication_footnotes(exr_publication *p,const exr_footnote **notes,size_t *count,
  const exr_footnote_reference **refs,size_t *ref_count,exr_error *e) {
  exr_status status=EXR_OK;size_t part,i,index;exr_document *doc=NULL,*target_doc=NULL;
  if(notes) *notes=NULL;
  if(count) *count=0;
  if(refs) *refs=NULL;
  if(ref_count) *ref_count=0;
  if(!p || !notes || !count || !refs || !ref_count || p->busy || p->searching)
    return exr_fail(e,EXR_ARGUMENT,"Invalid or reentrant footnote request");
  if(!p->footnotes_ready) {
    /* Scan only on explicit request. Old opens and page hashes are unaffected. */
    for(part=0;part<p->count;part++) {
      status=exr_publication_load(p,part,&doc,e);if(status!=EXR_OK) goto failed;
      for(i=0;i<doc->node_count;i++) {
        const exr_node *n=&doc->nodes[i];const char *id=note_id(n);
        if(id && note_semantic(n)) {
          status=note_add(p,doc,part,n,id,&index,e);if(status!=EXR_OK) goto failed;
        }
      }
      exr_document_free(doc);doc=NULL;
    }
    for(part=0;part<p->count;part++) {
      status=exr_publication_load(p,part,&doc,e);if(status!=EXR_OK) goto failed;
      for(i=0;i<doc->node_count;i++) {
        const exr_node *n=&doc->nodes[i];const char *href=exr_node_attribute(n,"href");
        char fragment[2048];exr_target target;size_t j;
        if(!href || n->start==SIZE_MAX || n->end<=n->start || n->end>doc->size) continue;
        if(exr_publication_resolve_href(p,p->parts[part].path,href,fragment,&target,NULL)!=EXR_OK ||
           target.part==SIZE_MAX || !fragment[0]) continue;
        index=note_find(p,target.part,fragment);
        if(index==SIZE_MAX && !strncmp(fragment,"fn",2)) {
          const exr_document *d=doc;
          if(target.part!=part) {
            status=exr_publication_load(p,target.part,&target_doc,e);if(status!=EXR_OK) goto failed;d=target_doc;
          }
          for(j=0;j<d->node_count;j++) {
            const char *id=note_id(&d->nodes[j]);
            if(id && !strcmp(id,fragment)) {
              status=note_add(p,d,target.part,&d->nodes[j],id,&index,e);break;
            }
          }
          exr_document_free(target_doc);target_doc=NULL;if(status!=EXR_OK) goto failed;
        }
        if(index!=SIZE_MAX) {
          size_t start=n->start,end=n->end;char *label;
          while(start<end && isspace((unsigned char)doc->text[start])) start++;
          while(end>start && isspace((unsigned char)doc->text[end-1])) end--;
          if(start==end) {start=n->start;end=n->end;}
          label=exr_copy(doc->text+start,end-start);
          if(!label || p->reference_count>=262144 || !exr_grow((void **)&p->references,&p->reference_capacity,
              p->reference_count+1,sizeof(*p->references))) {
            free(label);status=exr_fail(e,EXR_MEMORY,"Footnote reference allocation failed");goto failed;
          }
          if(!strcmp(p->footnotes[index].label,p->footnotes[index].id)) {
            free((void *)p->footnotes[index].label);p->footnotes[index].label=label;
          } else free(label);
          p->references[p->reference_count++]=(exr_footnote_reference){part,start,end,index};
        }
      }
      exr_document_free(doc);doc=NULL;
    }
    p->footnotes_ready=1;
  }
  *notes=p->footnotes;*count=p->footnote_count;*refs=p->references;*ref_count=p->reference_count;
  return exr_fail(e,EXR_OK,"");
failed:
  exr_document_free(doc);exr_document_free(target_doc);
  for(i=0;i<p->footnote_count;i++) {
    free((void *)p->footnotes[i].id);free((void *)p->footnotes[i].label);free((void *)p->footnotes[i].text);
  }
  free(p->footnotes);p->footnotes=NULL;p->footnote_count=p->footnote_capacity=0;
  free(p->references);p->references=NULL;p->reference_count=p->reference_capacity=0;
  return status;
}

exr_status exr_publication_resolve_href(const exr_publication *p,const char *base,
  const char *href,char fragment[2048],exr_target *target,exr_error *e) {
  char path[2048]; const char *hash; size_t i, match=SIZE_MAX, matches;
  unsigned pass;
  if (target) *target=(exr_target){SIZE_MAX,NULL,SIZE_MAX};
  if (fragment) fragment[0]=0;
  if (!p || !base || !href || !fragment || !target || p->busy)
    return exr_fail(e,EXR_ARGUMENT,"Invalid internal link request");
  hash=strchr(href,'#');
  if (!exr_resolve_path(base,href,path) ||
      (hash && !exr_uri_decode(hash+1,strlen(hash+1),fragment)))
    return exr_fail(e,EXR_ARGUMENT,"URI is external or invalid");
  target->fragment=fragment;
  for (pass=0;pass<2;pass++) {
    matches=0;
    for (i=0;i<p->count;i++) if (pass ? exr_link_case_equal(path,p->parts[i].path) :
        !strcmp(path,p->parts[i].path)) { match=i; matches++; }
    if (matches) { if (matches==1) target->part=match; break; }
  }
  return exr_fail(e,EXR_OK,"");
}
static exr_status remember_missing(exr_publication *p,const exr_target *target,exr_error *e) {
  size_t i,total=p->metadata_bytes; const char *fragment=target->fragment ? target->fragment : "";
  const char *copy;
  exr_status status;
  for (i=0;i<p->missing_count;i++)
    if (p->missing[i].part==target->part && !strcmp(p->missing[i].fragment,fragment)) return EXR_OK;
  if (p->missing_count>=10000) return exr_fail(e,EXR_LIMIT,"Missing-anchor log exceeds 10000 targets");
  for (i=0;i<p->missing_count;i++) total+=strlen(p->missing[i].fragment)+1;
  if (!exr_grow((void **)&p->missing,&p->missing_capacity,p->missing_count+1,sizeof(*p->missing)))
    return exr_fail(e,EXR_MEMORY,"Missing-anchor log allocation failed");
  status=copy_string(fragment,2046,&total,&copy,e);
  if (status!=EXR_OK) return status;
  p->missing[p->missing_count++]=(exr_target){target->part,copy,SIZE_MAX};
  return EXR_OK;
}
const exr_target *exr_publication_missing_targets(const exr_publication *p,size_t *count) {
  if (count) *count=p ? p->missing_count : 0;
  return p ? p->missing : NULL;
}
static exr_status publication_locate(exr_publication *p,const exr_target *target,
  exr_location *out,exr_error *e) {
  exr_document *d=NULL; exr_status status; exr_location result;
  if (out) *out=(exr_location){SIZE_MAX,SIZE_MAX,EXR_LINK_PART_MISSING};
  if (!p || !target || !out || p->busy) return exr_fail(e,EXR_ARGUMENT,"Invalid link target");
  if (target->part==SIZE_MAX) return exr_fail(e,EXR_OK,"");
  if (target->part>=p->count) return exr_fail(e,EXR_ARGUMENT,"Target part is outside publication");
  status=exr_publication_load(p,target->part,&d,e);
  if (status!=EXR_OK) return status;
  if (target->offset!=SIZE_MAX && (!target->fragment || !*target->fragment)) {
    size_t at=target->offset;
    if (at>d->size || (at<d->size && ((unsigned char)d->text[at]&0xc0)==0x80))
      status=exr_fail(e,EXR_ARGUMENT,"Target offset is outside UTF-8 text");
    result=(exr_location){target->part,at,EXR_LINK_FOUND};
  } else {
    status=exr_document_locate(d,target->fragment,&result,e);
    result.part=target->part;
  }
  exr_document_free(d);
  if (status==EXR_OK && result.state==EXR_LINK_ANCHOR_MISSING) status=remember_missing(p,target,e);
  if (status==EXR_OK) *out=result;
  return status;
}

exr_locate_report exr_publication_locate_report(const exr_publication *p) {
  return p ? p->locate_report : (exr_locate_report){0};
}
void exr_publication_locate_report_reset(exr_publication *p) {
  if(p) memset(&p->locate_report,0,sizeof(p->locate_report));
}
exr_status exr_publication_locate(exr_publication *p,const exr_target *target,
  exr_location *out,exr_error *e) {
  exr_status status;
  if(p) p->locate_report.total_entries++;
  status=publication_locate(p,target,out,e);
  if(p && status==EXR_OK) {
    if(out->state==EXR_LINK_ANCHOR_MISSING) {
      p->locate_report.missing_anchor++; p->locate_report.resolved_part_start++;
    } else if(out->state==EXR_LINK_PART_MISSING) p->locate_report.missing_part++;
    else p->locate_report.resolved_exact++;
  }
  return status;
}

typedef struct {
  exr_toc_entry *items; size_t count,capacity,bytes;
} toc_builder;
static void toc_clear(toc_builder *b) {
  size_t i;
  for (i=0;i<b->count;i++) { free((void *)b->items[i].title); free((void *)b->items[i].target.fragment); }
  free(b->items); memset(b,0,sizeof(*b));
}
static exr_status toc_push(toc_builder *b,const char *title,size_t level,
  exr_target target,exr_toc_source source,size_t order,exr_error *e) {
  exr_toc_entry *v; exr_status status;
  if (b->count>=10000) return exr_fail(e,EXR_LIMIT,"TOC exceeds 10000 entries");
  if (!exr_grow((void **)&b->items,&b->capacity,b->count+1,sizeof(*b->items)))
    return exr_fail(e,EXR_MEMORY,"TOC allocation failed");
  v=&b->items[b->count++]; memset(v,0,sizeof(*v));
  v->level=level; v->source=source; v->play_order=order; v->target=target;
  v->target.fragment=NULL;
  status=copy_string(title,65536,&b->bytes,&v->title,e);
  if (status==EXR_OK) status=copy_string(target.fragment,2046,&b->bytes,&v->target.fragment,e);
  return status;
}
static int toc_role(const char *s) {
  while (s && *s) {
    const char *start;
    while (*s==' ' || *s=='\t' || *s=='\n' || *s=='\r') s++;
    start=s; while (*s && *s!=' ' && *s!='\t' && *s!='\n' && *s!='\r') s++;
    if (s-start==3 && !memcmp(start,"toc",3)) return 1;
  }
  return 0;
}
static int license_label(const char *s) {
  return strstr(s,"LICENSE") || strstr(s,"License") || strstr(s,"license") ||
    strstr(s,"\xe8\xae\xb8\xe5\x8f\xaf\xe8\xaf\x81");
}
static int chapter_number(uint32_t cp) {
  return (cp>='0' && cp<='9') || (cp>=0xff10 && cp<=0xff19) ||
    cp==0x96f6 || cp==0x3007 || cp==0x4e00 || cp==0x4e8c || cp==0x4e09 ||
    cp==0x56db || cp==0x4e94 || cp==0x516d || cp==0x4e03 || cp==0x516b ||
    cp==0x4e5d || cp==0x5341 || cp==0x767e || cp==0x5343 || cp==0x5169 || cp==0x4e24;
}
/* A title must start a source line; a prose sentence such as ç¬¬å››å›žä¸­... fails
   the whitespace boundary. Keep the source line, never synthesize page text. */
static size_t chapter_marker(const char *s,size_t size,size_t *start) {
  size_t at=0,before; uint32_t cp; unsigned digits=0;
  do { before=at; if (!exr_next(s,size,&at,&cp)) return 0; } while (exr_projection_space(cp));
  *start=before;
  if (cp!=0x7b2c) return 0;
  while (exr_next(s,size,&at,&cp)) {
    if (chapter_number(cp)) { if (++digits>16) return 0; continue; }
    if (!digits || (cp!=0x56de && cp!=0x7ae0 && cp!=0x5377 && cp!=0x8282 && cp!=0x7bc0)) return 0;
    before=at;
    if (at<size && (!exr_next(s,size,&at,&cp) || !exr_projection_space(cp))) return 0;
    return before-*start;
  }
  return 0;
}
/* Compare source context, ignoring projection whitespace, so an earlier prose
   mention of the same chapter number cannot steal the heading's byte offset. */
static int heading_context(const char *raw,const exr_document *d,size_t offset,size_t end) {
  size_t at=0,length=strlen(raw); unsigned matched=0; uint32_t a,b;
  while (at<length && matched<64) {
    if (!exr_next(raw,length,&at,&a)) return 0;
    if (exr_projection_space(a)) continue;
    do { if (!exr_next(d->text,end,&offset,&b)) return 0; } while (exr_projection_space(b));
    if (a!=b) return 0;
    matched++;
  }
  return matched>0;
}
static exr_status recover_part(toc_builder *b,const exr_document *d,size_t part,int chinese,exr_error *e) {
  size_t i;
  for (i=0;i<d->node_count;i++) {
    const exr_node *v=&d->nodes[i];
    if (v->start==SIZE_MAX || v->end<=v->start) continue;
    if (!chinese) {
      if (v->kind==EXR_NODE_HEADING && v->end-v->start<=512) {
        char title[513]; const char *tag=exr_html_tag(d,v); size_t level=1;
        memcpy(title,d->text+v->start,v->end-v->start); title[v->end-v->start]=0;
        if (license_label(title) || strstr(title,"Project Gutenberg")) continue;
        if (tag && tag[0]=='h' && tag[1]>='1' && tag[1]<='6') level=(size_t)(tag[1]-'0');
        { exr_status status=toc_push(b,title,level,(exr_target){part,"",v->start},EXR_TOC_RECOVERED,SIZE_MAX,e);
          if (status!=EXR_OK) return status; }
      }
    } else if (v->kind==EXR_NODE_TEXT && v->text) {
      const char *line=v->text; size_t cursor=v->start;
      /* Exclude navigation/link labels, hidden text, head and metadata. */
      size_t parent=v->parent; int body=0,skip=0;
      while (parent!=SIZE_MAX) {
        const exr_node *a=&d->nodes[parent]; const char *tag=exr_html_tag(d,a);
        if (tag && !strcmp(tag,"body")) body=1;
        if (a->kind==EXR_NODE_LINK || exr_node_attribute(a,"hidden") ||
            (tag && (!strcmp(tag,"nav") || !strcmp(tag,"head") || !strcmp(tag,"footer")))) skip=1;
        parent=a->parent;
      }
      if (!body || skip) continue;
      while (*line) {
        const char *end=strchr(line,'\n'); size_t length=end ? (size_t)(end-line) : strlen(line),start=0;
        size_t marker=chapter_marker(line,length,&start);
        if (marker && length-start<=512) {
          char title[513],key[80]; const char *hit; size_t j,offset;
          if (marker>=sizeof(key)) return exr_fail(e,EXR_LIMIT,"Chapter marker exceeds limit");
          memcpy(key,line+start,marker); key[marker]=0;
          hit=strstr(d->text+cursor,key);
          while (hit && (size_t)(hit-d->text)+marker<=v->end &&
              !heading_context(line+start,d,(size_t)(hit-d->text),v->end)) hit=strstr(hit+marker,key);
          if (hit && (size_t)(hit-d->text)+marker<=v->end) {
            size_t used=0,at=start; uint32_t cp; int space=0;
            offset=(size_t)(hit-d->text); cursor=offset+marker;
            while (at<length) {
              size_t before=at;
              if (!exr_next(line,length,&at,&cp)) break;
              if (exr_projection_space(cp)) { if (used) space=1; continue; }
              if (space) title[used++]=' ';
              memcpy(title+used,line+before,at-before); used+=at-before; space=0;
            }
            title[used]=0;
            /* Split EPUBs can repeat the last heading at the next part start.
               Use the later occurrence, where the chapter body continues. */
            j=b->count;
            if (j && b->items[j-1].target.part+1==part && !strcmp(b->items[j-1].title,title)) j--;
            if (j<b->count) b->items[j].target=(exr_target){part,b->items[j].target.fragment,offset};
            else {
              exr_status status=toc_push(b,title,1,(exr_target){part,"",offset},EXR_TOC_RECOVERED,SIZE_MAX,e);
              if (status!=EXR_OK) return status;
            }
          }
        }
        if (!end) break;
        line=end+1;
      }
    }
  }
  return EXR_OK;
}
static exr_status recover_toc(exr_publication *p,toc_builder *b,exr_error *e) {
  unsigned pass; size_t i;
  for (pass=0;pass<2;pass++) {
    for (i=0;i<p->count;i++) if (p->parts[i].in_reading_order) {
      exr_document *d=NULL; exr_status status=exr_publication_load(p,i,&d,e);
      if (status==EXR_OK) status=recover_part(b,d,i,pass==0,e);
      exr_document_free(d);
      if (status!=EXR_OK) return status;
    }
    if (b->count) break;
  }
  return EXR_OK;
}
/* Some split EPUBs link chapter entries to an image-only separator, repeating
   that anchor in the next part containing the title. Canonicalize only this
   verified continuation; ordinary href resolution keeps the original resource. */
static exr_status toc_continuations(exr_publication *p,toc_builder *b,exr_error *e) {
  size_t i;
  for (i=0;i<b->count;i++) {
    exr_target *target=&b->items[i].target; exr_document *d=NULL,*next=NULL;
    exr_location here,there; exr_status status;
    size_t j,part=target->part;
    if (part==SIZE_MAX || part+1>=p->count || target->offset!=SIZE_MAX ||
        !target->fragment || !*target->fragment || !p->parts[part].in_reading_order ||
        !p->parts[part+1].in_reading_order) continue;
    status=exr_publication_load(p,part,&d,e);
    if (status==EXR_OK && !d->size) {
      status=exr_document_locate(d,target->fragment,&here,e);
      if (status==EXR_OK && here.state==EXR_LINK_FOUND) {
        status=exr_publication_load(p,part+1,&next,e);
        if (status==EXR_OK && next->size) {
          status=exr_document_locate(next,target->fragment,&there,e);
          if (status==EXR_OK && there.state==EXR_LINK_FOUND)
            for (j=0;j<next->count;j++) if (next->blocks[j].heading &&
                next->blocks[j].start>=there.offset) { target->part=part+1; break; }
        }
      }
    }
    exr_document_free(d); exr_document_free(next);
    if (status!=EXR_OK) return status;
  }
  return EXR_OK;
}
exr_status exr_publication_toc(exr_publication *p,const exr_toc_entry **out,size_t *count,exr_error *e) {
  toc_builder b={0}; exr_navigation *owned=NULL; const exr_navigation *nav;
  size_t n=0,i,*orders=NULL; exr_toc_source source=EXR_TOC_HOST;
  exr_status status=EXR_OK; int linked=0,only_license=1;
  if (out) *out=NULL;
  if (count) *count=0;
  if (!p || !out || !count || p->busy) return exr_fail(e,EXR_ARGUMENT,"Invalid TOC request");
  if (p->toc_ready) { *out=p->toc; *count=p->toc_count; return exr_fail(e,EXR_OK,""); }
  b.bytes=p->metadata_bytes;
  if (p->load==epub_load) {
    p->busy=1;
    status=exr_epub_navigation_details(p->context,p->metadata_bytes,&owned,&n,&orders,&source,e);
    p->busy=0; nav=owned;
  } else { nav=p->navigation; n=p->navigation_count; }
  for (i=0;status==EXR_OK && i<n;i++) if (toc_role(nav[i].role)) {
    char fragment[2048]; exr_target target; size_t parent=nav[i].parent,level=1;
    while (parent!=SIZE_MAX) { if (toc_role(nav[parent].role)) level++; parent=nav[parent].parent; }
    if (*nav[i].href) {
      linked++; if (!license_label(nav[i].label)) only_license=0;
      status=exr_publication_resolve_href(p,nav[i].base,nav[i].href,fragment,&target,e);
      /* External navigation is retained as an unresolved target. */
      if (status==EXR_ARGUMENT) { target=(exr_target){SIZE_MAX,"",SIZE_MAX}; status=EXR_OK; }
    } else target=(exr_target){nav[i].part,"",SIZE_MAX};
    if (status==EXR_OK) status=toc_push(&b,nav[i].label,level,target,source,orders ? orders[i] : SIZE_MAX,e);
  }
  exr_navigation_free(owned,owned ? n : 0); free(orders);
  if (status==EXR_OK && p->load==epub_load && (!linked || only_license)) {
    toc_builder recovered={0}; recovered.bytes=p->metadata_bytes;
    status=recover_toc(p,&recovered,e);
    if (status==EXR_OK && recovered.count) { toc_clear(&b); b=recovered; }
    else toc_clear(&recovered);
  }
  if (status==EXR_OK && p->load==epub_load) status=toc_continuations(p,&b,e);
  if (status!=EXR_OK) { toc_clear(&b); return status; }
  p->toc=b.items; p->toc_count=b.count; p->toc_ready=1;
  *out=p->toc; *count=p->toc_count;
  return exr_fail(e,EXR_OK,"");
}
exr_status exr_publication_target_at(exr_publication *p,size_t part,size_t offset,size_t *entry,exr_error *e) {
  const exr_toc_entry *toc; size_t count,i,best=SIZE_MAX; exr_document *d=NULL;
  exr_status status;
  if (entry) *entry=SIZE_MAX;
  if (!p || !entry || part>=p->count || p->busy) return exr_fail(e,EXR_ARGUMENT,"Invalid reverse target request");
  status=exr_publication_load(p,part,&d,e);
  if (status!=EXR_OK) return status;
  if (offset>d->size || (offset<d->size && ((unsigned char)d->text[offset]&0xc0)==0x80))
    status=exr_fail(e,EXR_ARGUMENT,"Offset is outside UTF-8 text");
  exr_document_free(d);
  if (status!=EXR_OK) return status;
  status=exr_publication_toc(p,&toc,&count,e); if (status!=EXR_OK) return status;
  if (!p->locations_ready) {
    exr_location *positions=count ? calloc(count,sizeof(*positions)) : NULL;
    if (count && !positions) return exr_fail(e,EXR_MEMORY,"TOC positions allocation failed");
    for (i=0;i<count;i++) {
      status=exr_publication_locate(p,&toc[i].target,&positions[i],e);
      if (status!=EXR_OK) { free(positions); return status; }
    }
    p->toc_locations=positions; p->locations_ready=1;
  }
  for (i=0;i<count;i++) {
    exr_location a=p->toc_locations[i];
    if (a.state!=EXR_LINK_FOUND || a.part>part || (a.part==part && a.offset>offset)) continue;
    if (best==SIZE_MAX || a.part>p->toc_locations[best].part ||
        (a.part==p->toc_locations[best].part && (a.offset>p->toc_locations[best].offset ||
         (a.offset==p->toc_locations[best].offset && toc[i].level>=toc[best].level)))) best=i;
  }
  *entry=best; return exr_fail(e,EXR_OK,"");
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

exr_status exr_range_to_cfi(exr_publication *p,const exr_text_range *r,const exr_control *control,
                             char **out,exr_error *e) {
  exr_document *d=NULL;exr_cfi_point point;exr_status status;char *a=NULL,*b=NULL;unsigned k;
  if(out) *out=NULL;
  if(!p || !out || !r || position_before(r->end,r->start) || r->end.part>=p->count || p->busy)
    return exr_fail(e,EXR_ARGUMENT,"Invalid content range for CFI export");
  if(p->load!=epub_load) return exr_fail(e,EXR_FORMAT,"Publication has no built-in EPUB CFI provider");
  status=exr_control_cancel(control,e);
  for(k=0;k<2 && status==EXR_OK;k++) {
    exr_text_position at=k ? r->end : r->start;
    status=exr_publication_load(p,at.part,&d,e);
    if(status==EXR_OK) status=exr_document_cfi_point_at(d,0,at.offset,control,&point,e);
    if(status==EXR_OK) status=exr_publication_cfi_create(p,at.part,d,&point,control,k ? &b : &a,e);
    exr_document_free(d);d=NULL;
  }
  if(status==EXR_OK) status=exr_control_cancel(control,e);
  if(status==EXR_OK) status=exr_cfi_range_join(a,b,out,e);
  free(a);free(b);return status;
}
exr_status exr_range_from_cfi(exr_publication *p,const char *cfi,const exr_control *control,
                               exr_text_range *out,exr_error *e) {
  exr_cfi *parsed=NULL;char *a=NULL,*b=NULL;exr_document *d=NULL;
  exr_cfi_point point;exr_text_range r;exr_status status;unsigned k;
  if(!out) return exr_fail(e,EXR_ARGUMENT,"Missing CFI content range output");
  range_clear(out);range_clear(&r);
  if(!p || !cfi || p->busy) return exr_fail(e,EXR_ARGUMENT,"Invalid CFI content range input");
  status=exr_control_cancel(control,e);
  if(status==EXR_OK) status=exr_cfi_parse(cfi,&parsed,NULL,e);
  if(status==EXR_OK) status=exr_cfi_endpoints(parsed,&a,&b,e);
  for(k=0;k<2 && status==EXR_OK;k++) {
    exr_text_position *at=k ? &r.end : &r.start;
    status=exr_publication_cfi_resolve(p,k ? b : a,control,&at->part,&d,&point,e);
    if(status==EXR_OK) status=exr_document_cfi_point_offset(d,0,&point,control,&at->offset,e);
    exr_document_free(d);d=NULL;
  }
  if(status==EXR_OK && position_before(r.end,r.start)) status=exr_fail(e,EXR_FORMAT,"Reversed CFI content range");
  if(status==EXR_OK) { *out=r;status=exr_fail(e,EXR_OK,""); }
  exr_cfi_free(parsed);free(a);free(b);return status;
}
exr_status exr_anchor_to_cfi(exr_publication *p,const exr_content_anchor *anchor,const exr_control *control,
                              char **out,exr_error *e) {
  exr_text_range_match match;exr_status status;
  if(!out) return exr_fail(e,EXR_ARGUMENT,"Missing anchor CFI output");
  *out=NULL;
  status=exr_range_from_anchor(p,anchor,control,&match,e);
  if(status==EXR_OK && match.state!=EXR_ANCHOR_FOUND) return exr_fail(e,EXR_FORMAT,"CFI anchor is missing or ambiguous");
  return status==EXR_OK ? exr_range_to_cfi(p,&match.range,control,out,e) : status;
}
exr_status exr_anchor_from_cfi(exr_publication *p,const char *cfi,const exr_control *control,
                                exr_content_anchor *out,exr_error *e) {
  exr_text_range range;exr_status status;
  if(!out) return exr_fail(e,EXR_ARGUMENT,"Missing CFI anchor output");
  memset(out,0,sizeof(*out));
  status=exr_range_from_cfi(p,cfi,control,&range,e);
  return status==EXR_OK ? exr_anchor_from_range(p,&range,control,out,e) : status;
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
  exr_text_range result={0},original={0};exr_document *d=NULL;exr_status status;size_t ignored,at;
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

/* Publication search reads the same normalized projection as anchors/pagers. */
static uint32_t search_fold(uint32_t cp,unsigned flags) {
  if(!(flags&EXR_SEARCH_CASE_SENSITIVE) &&
     ((cp>='A' && cp<='Z') || (cp>=0xc0 && cp<=0xd6) || (cp>=0xd8 && cp<=0xde))) cp+=32;
  return cp;
}
static int search_word(uint32_t cp) {
  if(cp=='_') return 1;
  return cp && !exr_projection_space(cp) && !content_punctuation(cp) && !exr_projection_cjk(cp) &&
    !(cp>=0xa0 && cp<=0xbf) && cp!=0xd7 && cp!=0xf7;
}
static int search_whole(const char *s,size_t n,size_t start,size_t end) {
  size_t at=start;uint32_t before=0,after=0,first=0,last=0;
  if(start) {at=start-1;while(at && ((unsigned char)s[at]&0xc0)==0x80) at--;exr_next(s,n,&at,&before);}
  at=start;exr_next(s,n,&at,&first);
  at=end-1;while(at>start && ((unsigned char)s[at]&0xc0)==0x80) at--;exr_next(s,n,&at,&last);
  at=end;if(at<n) exr_next(s,n,&at,&after);
  return !(search_word(before) && search_word(first)) && !(search_word(last) && search_word(after));
}
static exr_status search_run(exr_publication *p,exr_text_position from,const char *needle,unsigned flags,
  exr_search_fn callback,void *context,const exr_control *control,size_t *count,exr_search_result *first,exr_error *e) {
  uint32_t *pattern=NULL,*prefix=NULL,cp;size_t bytes=0,m=0,at=0,i,j,part,hits=0;exr_status status=EXR_OK;
  if(count) *count=0;
  if(first) *first=(exr_search_result){0,SIZE_MAX,SIZE_MAX,0};
  if(!p || p->busy || p->searching || !needle || (!count && !first) ||
     from.part>=p->count || (flags&~(EXR_SEARCH_CASE_SENSITIVE|EXR_SEARCH_WHOLE_WORD)))
    return exr_fail(e,EXR_ARGUMENT,"Invalid publication search arguments");
  while(bytes<=1024*1024 && needle[bytes]) bytes++;
  if(!bytes) return exr_fail(e,EXR_ARGUMENT,"Empty search needle");
  if(bytes>1024*1024) return exr_fail(e,EXR_LIMIT,"Search needle exceeds 1 MiB");
  pattern=malloc(bytes*sizeof(*pattern));prefix=malloc(bytes*sizeof(*prefix));
  if(!pattern || !prefix) {status=exr_fail(e,EXR_MEMORY,"Search pattern allocation failed");goto done;}
  while(at<bytes) {
    if(!exr_next(needle,bytes,&at,&cp)) {status=exr_fail(e,EXR_ENCODING,"Search needle is not UTF-8");goto done;}
    pattern[m++]=search_fold(cp,flags);
  }
  prefix[0]=0;
  for(i=1,j=0;i<m;i++) {
    while(j && pattern[i]!=pattern[j]) j=prefix[j-1];
    if(pattern[i]==pattern[j]) j++;
    prefix[i]=(uint32_t)j;
  }
  if(!p->search) {
    p->search=calloc(p->count,sizeof(*p->search));
    if(!p->search) {status=exr_fail(e,EXR_MEMORY,"Search snapshot allocation failed");goto done;}
  }
  p->searching=1;
  for(part=from.part;part<p->count;part++) {
    search_part *sp=&p->search[part];size_t next_poll=0;
    status=exr_control_cancel(control,e);if(status!=EXR_OK) break;
    if(!p->parts[part].in_reading_order) continue;
    if(!sp->text) {
      exr_document *doc=NULL;
      status=exr_publication_load(p,part,&doc,e);if(status!=EXR_OK) break;
      const char *text=exr_document_text(doc,&sp->size);
      sp->text=exr_copy(text,sp->size);
      exr_document_free(doc);
      if(!sp->text) {status=exr_fail(e,EXR_MEMORY,"Search text snapshot allocation failed");break;}
    }
    at=part==from.part ? from.offset:0;j=0;
    if(at>sp->size) {status=exr_fail(e,EXR_ARGUMENT,"Search offset exceeds part text");break;}
    while(at<sp->size && ((unsigned char)sp->text[at]&0xc0)==0x80) at++;
    while(at<sp->size) {
      if(at>=next_poll) {status=exr_control_cancel(control,e);if(status!=EXR_OK) break;next_poll=at+4096;}
      if(!exr_next(sp->text,sp->size,&at,&cp)) {status=exr_fail(e,EXR_ENCODING,"Search snapshot is not UTF-8");break;}
      cp=search_fold(cp,flags);
      while(j && cp!=pattern[j]) j=prefix[j-1];
      if(cp==pattern[j]) j++;
      if(j==m) {
        size_t start=at-bytes;
        if(!(flags&EXR_SEARCH_WHOLE_WORD) || search_whole(sp->text,sp->size,start,at)) {
          exr_search_result result={1,part,start,bytes};hits++;
          if(first) {*first=result;goto finished;}
          if(callback) {
            int more;p->busy=1;more=callback(context,&result);p->busy=0;
            if(!more) goto finished;
          }
        }
        j=prefix[j-1];
      }
    }
    if(status!=EXR_OK) break;
  }
finished:
  p->searching=0;
done:
  free(pattern);free(prefix);
  if(status==EXR_OK) {if(count) *count=hits;return exr_fail(e,EXR_OK,"");}
  if(first) *first=(exr_search_result){0,SIZE_MAX,SIZE_MAX,0};
  return status;
}
exr_status exr_publication_search(exr_publication *p,exr_text_position from,const char *needle,unsigned flags,
  const exr_control *control,exr_search_result *result,exr_error *e) {
  if(!result) return exr_fail(e,EXR_ARGUMENT,"Missing search result");
  return search_run(p,from,needle,flags,NULL,NULL,control,NULL,result,e);
}
exr_status exr_publication_search_all(exr_publication *p,const char *needle,unsigned flags,
  exr_search_fn callback,void *context,const exr_control *control,size_t *count,exr_error *e) {
  if(!count) return exr_fail(e,EXR_ARGUMENT,"Missing search count");
  return search_run(p,(exr_text_position){0,0},needle,flags,callback,context,control,count,NULL,e);
}

#include "publication_index.h"
