/* SPDX-License-Identifier: MIT */
#include <exr/edit.h>
#include <stdlib.h>
#include <string.h>

typedef struct edit_block {
  size_t refs;
  exr_edit_block view;
} edit_block;
typedef struct { size_t index; edit_block *before,*after; } edit_change;
struct exr_edit_tx {
  exr_edit_doc *doc;
  edit_change *changes;
  size_t count,capacity;
  exr_status failed;
};
struct exr_edit_doc {
  exr_edit_section *sections; size_t section_count;
  exr_edit_part *parts; size_t part_count;
  edit_block **blocks; size_t count,capacity;
  exr_edit_tx *active,**history;
  size_t history_count,cursor,depth,bytes;
  exr_edit_id next_id;
};
typedef union {
  size_t size;
#ifdef _MSC_VER
  /* MSVC's C headers omit max_align_t; same shim as images.c and
     base_internal.h: preserve the 16-byte malloc alignment. */
  __declspec(align(16)) unsigned char alignment[16];
#else
  max_align_t alignment;
#endif
} edit_allocation;

/* Account requested bytes, including retained versions, without platform heap APIs. */
static void *allocate(exr_edit_doc *d,size_t size) {
  edit_allocation *a;
  if (!size || size>SIZE_MAX-sizeof(*a) || size>SIZE_MAX-d->bytes) return NULL;
  a=calloc(1,sizeof(*a)+size);
  if (!a) return NULL;
  a->size=size; d->bytes+=size;
  return a+1;
}
static void release(exr_edit_doc *d,const void *p) {
  if (p) { edit_allocation *a=(edit_allocation *)p-1; d->bytes-=a->size; free(a); }
}
static void *copy_bytes(exr_edit_doc *d,const void *p,size_t n,int terminate) {
  void *q;
  if (n>SIZE_MAX-(size_t)terminate || (n && !p)) return NULL;
  q=allocate(d,n+(size_t)terminate);
  if (q && n) memcpy(q,p,n);
  return q;
}
static int reserve(exr_edit_doc *d,void **array,size_t *capacity,size_t count,size_t item) {
  size_t cap; void *p;
  if (count<=*capacity) return 1;
  cap=*capacity ? *capacity : 8;
  while (cap<count) { if (cap>SIZE_MAX/2) { cap=count; break; } cap*=2; }
  if (cap>SIZE_MAX/item) return 0;
  p=allocate(d,cap*item);
  if (!p) return 0;
  if (*capacity) memcpy(p,*array,*capacity*item);
  release(d,*array); *array=p; *capacity=cap;
  return 1;
}
static int utf8(const char *s,size_t n) {
  size_t i=0;
  if (n && !s) return 0;
  while (i<n) {
    uint32_t c=(unsigned char)s[i++],min=0; unsigned left=0;
    if (c>=0xc2 && c<=0xdf) { left=1; min=0x80; c&=31; }
    else if (c>=0xe0 && c<=0xef) { left=2; min=0x800; c&=15; }
    else if (c>=0xf0 && c<=0xf4) { left=3; min=0x10000; c&=7; }
    else if (c>=0x80) return 0;
    if (left>n-i) return 0;
    while (left--) {
      unsigned char b=(unsigned char)s[i++];
      if ((b&0xc0)!=0x80) return 0;
      c=(c<<6)|(b&63);
    }
    if (c<min || c>0x10ffff || (c>=0xd800 && c<=0xdfff) ||
        (c<32 && c!=9 && c!=10 && c!=13) || c==0xfffe || c==0xffff) return 0;
  }
  return 1;
}
static int string_field(const char *s,size_t cap) {
  const char *end=memchr(s,0,cap);
  return end && utf8(s,(size_t)(end-s));
}
static int run_props_valid(const exr_edit_run_props *p) {
  return p && !(p->present&~31u) && string_field(p->font,sizeof(p->font)) &&
    (!(p->present&EXR_EDIT_SIZE) || (p->size_half_points && p->size_half_points<=1638)) &&
    p->color_rgb<=0xffffff && p->bold<=1 && p->italic<=1;
}
static int para_props_valid(const exr_edit_para_props *p) {
  return p && !(p->present&~127u) && p->alignment>=EXR_EDIT_LEFT &&
    p->alignment<=EXR_EDIT_JUSTIFY && p->line_rule>=EXR_EDIT_LINE_AUTO &&
    p->line_rule<=EXR_EDIT_LINE_AT_LEAST && p->keep_next<=1 && p->keep_lines<=1 &&
    p->page_break_before<=1 && p->numbering_level<=8;
}
static int block_valid(const exr_edit_block *b) {
  size_t i;
  if (b->kind<EXR_EDIT_PARAGRAPH || b->kind>EXR_EDIT_PAGE_BREAK ||
      !para_props_valid(&b->props) || (b->opaque_size && !b->opaque_xml) ||
      b->run_count>SIZE_MAX/sizeof(exr_edit_run) || (b->run_count && !b->runs) ||
      (b->kind!=EXR_EDIT_PARAGRAPH && b->run_count) ||
      (b->kind==EXR_EDIT_TABLE && !b->opaque_size)) return 0;
  for (i=0;i<b->run_count;i++) {
    const exr_edit_run *r=b->runs+i;
    if (!run_props_valid(&r->props) || (r->opaque_size && !r->opaque_xml)) return 0;
    if (r->kind==EXR_EDIT_TEXT) { if (!utf8(r->text,r->text_size)) return 0; }
    else if (r->kind!=EXR_EDIT_OPAQUE_RUN || !r->opaque_size || r->text_size) return 0;
  }
  return 1;
}
static exr_edit_id fresh_id(exr_edit_doc *d) {
  exr_edit_id id=d->next_id;
  if (id) d->next_id=id==UINT64_MAX ? 0 : id+1;
  return id;
}
static void block_unref(exr_edit_doc *d,edit_block *b) {
  size_t i;
  if (!b || --b->refs) return;
  for (i=0;i<b->view.run_count;i++) {
    release(d,b->view.runs[i].text); release(d,b->view.runs[i].opaque_xml);
  }
  release(d,b->view.runs); release(d,b->view.opaque_xml); release(d,b);
}
static edit_block *block_ref(edit_block *b) { if (b) b->refs++; return b; }
static edit_block *block_copy(exr_edit_doc *d,const exr_edit_block *v) {
  size_t i; edit_block *b=allocate(d,sizeof(*b)); exr_edit_run *runs;
  if (!b) return NULL;
  b->refs=1; b->view=*v; b->view.runs=NULL; b->view.run_count=0; b->view.opaque_xml=NULL;
  if (v->opaque_size) {
    b->view.opaque_xml=copy_bytes(d,v->opaque_xml,v->opaque_size,0);
    if (!b->view.opaque_xml) goto fail;
  }
  if (v->run_count) {
    runs=allocate(d,v->run_count*sizeof(*runs));
    if (!runs) goto fail;
    b->view.runs=runs;
    for (i=0;i<v->run_count;i++) {
      runs[i]=v->runs[i]; runs[i].text=NULL; runs[i].opaque_xml=NULL;
      b->view.run_count++;
      if (v->runs[i].kind==EXR_EDIT_TEXT) {
        runs[i].text=copy_bytes(d,v->runs[i].text,v->runs[i].text_size,1);
        if (!runs[i].text) goto fail;
      }
      if (v->runs[i].opaque_size) {
        runs[i].opaque_xml=copy_bytes(d,v->runs[i].opaque_xml,v->runs[i].opaque_size,0);
        if (!runs[i].opaque_xml) goto fail;
      }
    }
  }
  return b;
fail:
  block_unref(d,b); return NULL;
}
static int assign_ids(exr_edit_doc *d,edit_block *b,int all) {
  size_t i; exr_edit_run *r=(exr_edit_run *)b->view.runs;
  if ((all || !b->view.id) && !(b->view.id=fresh_id(d))) return 0;
  for (i=0;i<b->view.run_count;i++)
    if ((all || !r[i].id) && !(r[i].id=fresh_id(d))) return 0;
  return 1;
}
static size_t find_index(const exr_edit_doc *d,exr_edit_id id) {
  size_t i;
  for (i=0;i<d->count;i++) if (d->blocks[i]->view.id==id) return i;
  return SIZE_MAX;
}
/* A splice and its inverse never allocate; capacity is reserved before journalling. */
static void apply(exr_edit_doc *d,const edit_change *c,int forward) {
  edit_block *old=forward ? c->before : c->after,*now=forward ? c->after : c->before;
  size_t i=c->index;
  if (old && now) d->blocks[i]=block_ref(now);
  else if (now) {
    memmove(d->blocks+i+1,d->blocks+i,(d->count-i)*sizeof(*d->blocks));
    d->blocks[i]=block_ref(now); d->count++;
  } else {
    memmove(d->blocks+i,d->blocks+i+1,(d->count-i-1)*sizeof(*d->blocks)); d->count--;
  }
  block_unref(d,old);
}
static void tx_free(exr_edit_tx *t) {
  size_t i; exr_edit_doc *d=t->doc;
  for (i=0;i<t->count;i++) {
    block_unref(d,t->changes[i].before); block_unref(d,t->changes[i].after);
  }
  release(d,t->changes); release(d,t);
}
static exr_status command_failure(exr_edit_doc *d,exr_status status) {
  if (d && d->active) {
    if (!d->active->failed) d->active->failed=status;
    return d->active->failed;
  }
  return status;
}
static exr_status ready(exr_edit_doc *d) {
  return !d ? EXR_ARGUMENT : d->active ? d->active->failed : EXR_OK;
}
static exr_status modify(exr_edit_doc *d,edit_change *changes,size_t count) {
  size_t i; int automatic=!d->active;
  exr_edit_tx *t=d->active ? d->active : exr_edit_begin(d);
  if (!t) return EXR_MEMORY;
  if (count>SIZE_MAX-t->count || d->count==SIZE_MAX ||
      !reserve(d,(void **)&t->changes,&t->capacity,t->count+count,sizeof(*t->changes)) ||
      !reserve(d,(void **)&d->blocks,&d->capacity,d->count+1,sizeof(*d->blocks))) {
    command_failure(d,EXR_MEMORY);
    if (automatic) exr_edit_rollback(t);
    return EXR_MEMORY;
  }
  for (i=0;i<count;i++) {
    t->changes[t->count++]=changes[i];
    block_ref(changes[i].before); block_ref(changes[i].after);
    apply(d,changes+i,1);
  }
  return automatic ? exr_edit_commit(t) : EXR_OK;
}
exr_edit_options exr_edit_defaults(void) { exr_edit_options o={100}; return o; }
exr_edit_tx *exr_edit_begin(exr_edit_doc *d) {
  exr_edit_tx *t;
  if (!d || d->active) return NULL;
  t=allocate(d,sizeof(*t));
  if (t) { t->doc=d; d->active=t; }
  return t;
}
exr_status exr_edit_rollback(exr_edit_tx *t) {
  size_t i; exr_edit_doc *d;
  if (!t || t->doc->active!=t) return EXR_ARGUMENT;
  d=t->doc;
  for (i=t->count;i;i--) apply(d,t->changes+i-1,0);
  d->active=NULL; tx_free(t); return EXR_OK;
}
exr_status exr_edit_commit(exr_edit_tx *t) {
  exr_edit_doc *d; exr_status status;
  if (!t || t->doc->active!=t) return EXR_ARGUMENT;
  d=t->doc; status=t->failed;
  if (status) { exr_edit_rollback(t); return status; }
  d->active=NULL;
  if (!t->count) { tx_free(t); return EXR_OK; }
  while (d->history_count>d->cursor) tx_free(d->history[--d->history_count]);
  if (!d->depth) { tx_free(t); return EXR_OK; }
  if (d->history_count==d->depth) {
    tx_free(d->history[0]); d->history_count--;
    memmove(d->history,d->history+1,d->history_count*sizeof(*d->history));
  }
  d->history[d->history_count++]=t; d->cursor=d->history_count;
  return EXR_OK;
}
exr_status exr_edit_undo(exr_edit_doc *d) {
  size_t i; exr_edit_tx *t;
  if (!d || d->active || !d->cursor) return EXR_ARGUMENT;
  t=d->history[--d->cursor];
  for (i=t->count;i;i--) apply(d,t->changes+i-1,0);
  return EXR_OK;
}
exr_status exr_edit_redo(exr_edit_doc *d) {
  size_t i; exr_edit_tx *t;
  if (!d || d->active || d->cursor==d->history_count) return EXR_ARGUMENT;
  t=d->history[d->cursor++];
  for (i=0;i<t->count;i++) apply(d,t->changes+i,1);
  return EXR_OK;
}
static int compare_ids(const void *a,const void *b) {
  exr_edit_id x=*(const exr_edit_id *)a,y=*(const exr_edit_id *)b;
  return (x>y)-(x<y);
}
exr_status exr_edit_doc_create(const exr_edit_section *sections,size_t ns,
  const exr_edit_block *blocks,size_t nb,const exr_edit_part *parts,size_t np,
  const exr_edit_options *options,exr_edit_doc **out) {
  exr_edit_doc *d; exr_edit_id *ids=NULL; size_t total,i,j,k=0; exr_status status=EXR_MEMORY;
  exr_edit_section default_section={0};
  if (!out) return EXR_ARGUMENT;
  *out=NULL;
  if ((ns && !sections) || (nb && !blocks) || (np && !parts) ||
      ns>SIZE_MAX/sizeof(*sections) || nb>SIZE_MAX/sizeof(*blocks) ||
      np>SIZE_MAX/sizeof(*parts)) return EXR_ARGUMENT;
  if (!ns) {
    default_section.page_width=12240; default_section.page_height=15840;
    default_section.margin_top=default_section.margin_right=1440;
    default_section.margin_bottom=default_section.margin_left=1440;
    default_section.header_distance=default_section.footer_distance=720;
    sections=&default_section; ns=1;
  }
  if (ns>SIZE_MAX-nb || ns+nb>SIZE_MAX-np) return EXR_LIMIT;
  total=ns+nb+np;
  for (i=0;i<nb;i++) {
    if (!block_valid(blocks+i)) return EXR_ARGUMENT;
    if (blocks[i].run_count>SIZE_MAX-total) return EXR_LIMIT;
    total+=blocks[i].run_count;
  }
  if (total>SIZE_MAX/sizeof(*ids)) return EXR_LIMIT;
  d=calloc(1,sizeof(*d));
  if (!d) return EXR_MEMORY;
  d->bytes=sizeof(*d); d->depth=options ? options->undo_depth : 100;
  if (d->depth>SIZE_MAX/sizeof(*d->history)) { status=EXR_LIMIT; goto fail; }
  ids=allocate(d,total*sizeof(*ids));
  if (!ids) goto fail;
  for (i=0;i<ns;i++) ids[k++]=sections[i].id;
  for (i=0;i<nb;i++) {
    ids[k++]=blocks[i].id;
    for (j=0;j<blocks[i].run_count;j++) ids[k++]=blocks[i].runs[j].id;
  }
  for (i=0;i<np;i++) ids[k++]=parts[i].id;
  qsort(ids,total,sizeof(*ids),compare_ids);
  for (i=1;i<total;i++) if (ids[i] && ids[i]==ids[i-1]) { status=EXR_ARGUMENT; goto fail; }
  if (ids[total-1]==UINT64_MAX) { status=EXR_LIMIT; goto fail; }
  d->next_id=ids[total-1]+1; release(d,ids); ids=NULL;
  d->sections=allocate(d,ns*sizeof(*sections));
  if (!d->sections) goto fail;
  memcpy(d->sections,sections,ns*sizeof(*sections)); d->section_count=ns;
  for (i=0;i<ns;i++) {
    exr_edit_section *s=d->sections+i;
    if (s->page_width<=0 || s->page_height<=0 || s->margin_top<0 || s->margin_right<0 ||
        s->margin_bottom<0 || s->margin_left<0 || s->header_distance<0 ||
        s->footer_distance<0 || s->landscape>1) { status=EXR_ARGUMENT; goto fail; }
    for (j=0;j<3;j++) if (!string_field(s->header_refs[j],128) || !string_field(s->footer_refs[j],128)) {
      status=EXR_ARGUMENT; goto fail;
    }
    if (!s->id && !(s->id=fresh_id(d))) { status=EXR_LIMIT; goto fail; }
  }
  if (np) {
    d->parts=allocate(d,np*sizeof(*parts));
    if (!d->parts) goto fail;
    d->part_count=np;
    for (i=0;i<np;i++) {
      if (!parts[i].name || !*parts[i].name || (parts[i].size && !parts[i].data) ||
          !utf8(parts[i].name,strlen(parts[i].name))) { status=EXR_ARGUMENT; goto fail; }
      for (j=0;j<i;j++) if (!strcmp(parts[i].name,parts[j].name)) { status=EXR_ARGUMENT; goto fail; }
      d->parts[i].id=parts[i].id ? parts[i].id : fresh_id(d);
      if (!d->parts[i].id) { status=EXR_LIMIT; goto fail; }
      d->parts[i].name=copy_bytes(d,parts[i].name,strlen(parts[i].name),1);
      d->parts[i].size=parts[i].size;
      if (!d->parts[i].name) goto fail;
      if (parts[i].size) {
        d->parts[i].data=copy_bytes(d,parts[i].data,parts[i].size,0);
        if (!d->parts[i].data) goto fail;
      }
    }
  }
  if (nb && !reserve(d,(void **)&d->blocks,&d->capacity,nb,sizeof(*d->blocks))) goto fail;
  for (i=0;i<nb;i++) {
    exr_edit_block v=blocks[i]; edit_block *b;
    if (!v.section_id) v.section_id=d->sections[0].id;
    for (j=0;j<ns && d->sections[j].id!=v.section_id;j++) {}
    if (j==ns) { status=EXR_ARGUMENT; goto fail; }
    b=block_copy(d,&v);
    if (!b) goto fail;
    d->blocks[d->count++]=b;
    if (!assign_ids(d,b,0)) { status=EXR_LIMIT; goto fail; }
  }
  if (d->depth) {
    d->history=allocate(d,d->depth*sizeof(*d->history));
    if (!d->history) goto fail;
  }
  *out=d; return EXR_OK;
fail:
  release(d,ids); exr_edit_doc_free(d); return status;
}
void exr_edit_doc_free(exr_edit_doc *d) {
  size_t i;
  if (!d) return;
  if (d->active) exr_edit_rollback(d->active);
  for (i=0;i<d->history_count;i++) tx_free(d->history[i]);
  for (i=0;i<d->count;i++) block_unref(d,d->blocks[i]);
  for (i=0;i<d->part_count;i++) { release(d,d->parts[i].name); release(d,d->parts[i].data); }
  release(d,d->history); release(d,d->blocks); release(d,d->sections); release(d,d->parts); free(d);
}
size_t exr_edit_block_count(const exr_edit_doc *d) { return d ? d->count : 0; }
const exr_edit_block *exr_edit_block_at(const exr_edit_doc *d,size_t i) {
  return d && i<d->count ? &d->blocks[i]->view : NULL;
}
const exr_edit_block *exr_edit_find_block(const exr_edit_doc *d,exr_edit_id id) {
  return d ? exr_edit_block_at(d,find_index(d,id)) : NULL;
}
const exr_edit_section *exr_edit_sections(const exr_edit_doc *d,size_t *count) {
  if (count) *count=d ? d->section_count : 0;
  return d ? d->sections : NULL;
}
const exr_edit_part *exr_edit_parts(const exr_edit_doc *d,size_t *count) {
  if (count) *count=d ? d->part_count : 0;
  return d ? d->parts : NULL;
}
size_t exr_edit_memory_bytes(const exr_edit_doc *d) { return d ? d->bytes : 0; }
exr_status exr_edit_insert_paragraph(exr_edit_doc *d,exr_edit_id after,const exr_edit_run *runs,
  size_t count,const exr_edit_para_props *props,exr_edit_id *out) {
  size_t index=0; exr_edit_block v={0}; edit_block *b; edit_change c; exr_status s=ready(d);
  if (out) *out=0;
  if (s) return s;
  if (!out) return command_failure(d,EXR_ARGUMENT);
  if (after) {
    index=find_index(d,after);
    if (index==SIZE_MAX) return command_failure(d,EXR_ARGUMENT);
    v.section_id=d->blocks[index]->view.section_id; index++;
  } else v.section_id=d->sections[0].id;
  v.kind=EXR_EDIT_PARAGRAPH; v.runs=runs; v.run_count=count;
  if (props) v.props=*props;
  if (!block_valid(&v)) return command_failure(d,EXR_ARGUMENT);
  b=block_copy(d,&v);
  if (!b) return command_failure(d,EXR_MEMORY);
  if (!assign_ids(d,b,1)) { block_unref(d,b); return command_failure(d,EXR_LIMIT); }
  c.index=index; c.before=NULL; c.after=b;
  s=modify(d,&c,1);
  if (!s) *out=b->view.id;
  block_unref(d,b); return s;
}
exr_status exr_edit_split_paragraph(exr_edit_doc *d,exr_edit_id id,size_t at,size_t offset) {
  size_t index,i,left_count,right_start; const exr_edit_block *v; exr_edit_block a,b;
  edit_block *left=NULL,*right=NULL; exr_edit_run *temp=NULL;
  edit_change c[2]; exr_status s=ready(d); int divided=0;
  if (s) return s;
  index=find_index(d,id);
  if (index==SIZE_MAX) return command_failure(d,EXR_ARGUMENT);
  v=&d->blocks[index]->view;
  if (v->kind!=EXR_EDIT_PARAGRAPH) return command_failure(d,EXR_UNSUPPORTED);
  if (at>v->run_count || (at==v->run_count && offset)) return command_failure(d,EXR_ARGUMENT);
  left_count=at; right_start=at;
  if (at<v->run_count) {
    const exr_edit_run *r=v->runs+at;
    if (offset>r->text_size || (r->kind==EXR_EDIT_OPAQUE_RUN && offset) ||
        (offset<r->text_size && ((unsigned char)r->text[offset]&0xc0)==0x80))
      return command_failure(d,EXR_ARGUMENT);
    if (offset && offset==r->text_size) { left_count=at+1; right_start=at+1; }
    else if (offset) { left_count=at+1; divided=1; }
  }
  a=*v; b=*v; a.run_count=left_count;
  b.runs=right_start<v->run_count ? v->runs+right_start : NULL;
  b.run_count=v->run_count-right_start;
  if (divided) {
    temp=allocate(d,v->run_count*sizeof(*temp));
    if (!temp) return command_failure(d,EXR_MEMORY);
    memcpy(temp,v->runs,v->run_count*sizeof(*temp));
    temp[at].text_size=offset; a.runs=temp;
  }
  left=block_copy(d,&a);
  if (!left) { s=EXR_MEMORY; goto done; }
  if (divided) {
    temp[at]=v->runs[at]; temp[at].text+=offset; temp[at].text_size-=offset;
    temp[at].id=fresh_id(d);
    if (!temp[at].id) { s=EXR_LIMIT; goto done; }
    b.runs=temp+at;
  }
  right=block_copy(d,&b);
  if (!right) { s=EXR_MEMORY; goto done; }
  right->view.id=fresh_id(d);
  if (!right->view.id) { s=EXR_LIMIT; goto done; }
  /* Whole runs retain their IDs; the divided run's right fragment was assigned above. */
  for (i=0;i<2;i++) { c[i].index=index+i; c[i].before=NULL; }
  c[0].before=d->blocks[index]; c[0].after=left; c[1].after=right;
  s=modify(d,c,2);
done:
  release(d,temp); block_unref(d,left); block_unref(d,right);
  return s ? command_failure(d,s) : EXR_OK;
}
static exr_status set_props(exr_edit_doc *d,exr_edit_id id,size_t run,
  const exr_edit_para_props *para,const exr_edit_run_props *rp) {
  size_t index; edit_block *b; edit_change c; exr_status s=ready(d);
  if (s) return s;
  if ((!para && !rp) || (para && !para_props_valid(para)) || (rp && !run_props_valid(rp)))
    return command_failure(d,EXR_ARGUMENT);
  index=find_index(d,id);
  if (index==SIZE_MAX) return command_failure(d,EXR_ARGUMENT);
  if (d->blocks[index]->view.kind!=EXR_EDIT_PARAGRAPH) return command_failure(d,EXR_UNSUPPORTED);
  if (rp && run>=d->blocks[index]->view.run_count) return command_failure(d,EXR_ARGUMENT);
  if (rp && d->blocks[index]->view.runs[run].kind!=EXR_EDIT_TEXT)
    return command_failure(d,EXR_UNSUPPORTED);
  b=block_copy(d,&d->blocks[index]->view);
  if (!b) return command_failure(d,EXR_MEMORY);
  if (para) b->view.props=*para;
  if (rp) ((exr_edit_run *)b->view.runs)[run].props=*rp;
  c.index=index; c.before=d->blocks[index]; c.after=b;
  s=modify(d,&c,1); block_unref(d,b); return s;
}
exr_status exr_edit_set_paragraph_props(exr_edit_doc *d,exr_edit_id id,const exr_edit_para_props *p) {
  return set_props(d,id,0,p,NULL);
}
exr_status exr_edit_set_run_props(exr_edit_doc *d,exr_edit_id id,size_t run,const exr_edit_run_props *p) {
  return set_props(d,id,run,NULL,p);
}
exr_status exr_edit_delete_block(exr_edit_doc *d,exr_edit_id id) {
  size_t index; edit_change c; exr_status s=ready(d);
  if (s) return s;
  index=find_index(d,id);
  if (index==SIZE_MAX) return command_failure(d,EXR_ARGUMENT);
  if (d->blocks[index]->view.kind==EXR_EDIT_TABLE) return command_failure(d,EXR_UNSUPPORTED);
  c.index=index; c.before=d->blocks[index]; c.after=NULL;
  return modify(d,&c,1);
}
