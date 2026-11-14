/* SPDX-License-Identifier: MIT */
#include "docx_edit_model_internal.h"
#include <stdlib.h>
#include <string.h>

typedef struct edit_block {
  size_t refs;
  exr_edit_block view;
} edit_block;
typedef struct { size_t index; edit_block *before,*after; } edit_change;
typedef struct { size_t refs; exr_edit_part part; } edit_part_version;
typedef struct {
  size_t refs,count;
  exr_edit_section *sections;
  signed char *first;
  exr_edit_part *parts;
  edit_part_version **versions;
} edit_package;
struct exr_edit_tx {
  exr_edit_doc *doc;
  edit_change *changes;
  size_t count,capacity;
  exr_status failed;
  edit_package *package_before,*package_after;
};
struct exr_edit_doc {
  exr_edit_section *sections; size_t section_count;
  exr_edit_part *parts; size_t part_count;
  edit_block **blocks; size_t count,capacity;
  exr_edit_tx *active,**history;
  size_t history_count,cursor,depth,bytes;
  exr_edit_id next_id;
  edit_package *package;
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
static edit_package *package_ref(edit_package *p) { if (p) p->refs++; return p; }
static void package_unref(exr_edit_doc *d,edit_package *p) {
  size_t i;
  if (!p || --p->refs) return;
  for (i=0;i<p->count;i++) if (p->versions && p->versions[i] && !--p->versions[i]->refs) {
    edit_part_version *v=p->versions[i];
    release(d,v->part.name); release(d,v->part.data); release(d,v);
  }
  release(d,p->sections); release(d,p->first); release(d,p->parts); release(d,p->versions); release(d,p);
}
static void package_apply(exr_edit_doc *d,edit_package *p) {
  package_ref(p); package_unref(d,d->package); d->package=p;
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
  size_t i,j,k;
  if (b->kind<EXR_EDIT_PARAGRAPH || b->kind>EXR_EDIT_IMAGE ||
      !para_props_valid(&b->props) || (b->opaque_size && !b->opaque_xml) ||
      b->run_count>SIZE_MAX/sizeof(exr_edit_run) || (b->run_count && !b->runs) ||
      (b->kind!=EXR_EDIT_PARAGRAPH && b->run_count) ||
      (b->kind==EXR_EDIT_OPAQUE_BLOCK && !b->opaque_size) ||
      (b->kind==EXR_EDIT_TABLE && !b->table && !b->opaque_size) ||
      (b->table && b->kind!=EXR_EDIT_TABLE) || (b->image && b->kind!=EXR_EDIT_IMAGE)) return 0;
  if (b->kind==EXR_EDIT_IMAGE && (!b->image || !b->image->data || !b->image->size ||
      b->image->width_emu<=0 || b->image->height_emu<=0 || b->image->jpeg>1 || b->image->format>EXR_EDIT_IMAGE_BMP ||
      (b->image->anchor_run_id && !b->opaque_size))) return 0;
  if (b->table) {
    const exr_edit_table *t=b->table;
    if (!t->row_count || !t->rows || t->row_count>SIZE_MAX/sizeof(*t->rows) ||
        !t->column_count || t->column_count>16384 || t->width_twips<0 ||
        t->borders<EXR_EDIT_BORDER_NONE || t->borders>EXR_EDIT_BORDER_DOUBLE || (t->changed&~7u) ||
        ((t->changed&4u) && !t->column_widths)) return 0;
    if (t->column_widths) for (i=0;i<t->column_count;i++) if (t->column_widths[i]<0) return 0;
    for (i=0;i<t->row_count;i++) {
      const exr_edit_row *r=t->rows+i;
      if (!r->cell_count || !r->cells || r->cell_count>SIZE_MAX/sizeof(*r->cells) ||
          (r->opaque_size && !r->opaque_xml)) return 0;
      for (j=0;j<r->cell_count;j++) {
        const exr_edit_cell *c=r->cells+j;
        if (c->block_count>SIZE_MAX/sizeof(*c->blocks) || (c->block_count && !c->blocks) ||
            (c->opaque_size && !c->opaque_xml) || (c->unsupported&~15u)) return 0;
        for (k=0;k<c->block_count;k++) {
          const exr_edit_block *p=c->blocks+k;
          if ((p->kind!=EXR_EDIT_PARAGRAPH && p->kind!=EXR_EDIT_OPAQUE_BLOCK) || !block_valid(p)) return 0;
        }
      }
    }
  }
  for (i=0;i<b->run_count;i++) {
    const exr_edit_run *r=b->runs+i;
    if (!run_props_valid(&r->props) || (r->opaque_size && !r->opaque_xml)) return 0;
    if (r->kind==EXR_EDIT_TEXT || r->kind==EXR_EDIT_FOOTNOTE) { if (!utf8(r->text,r->text_size)) return 0; }
    else if (r->kind!=EXR_EDIT_OPAQUE_RUN || !r->opaque_size || r->text_size) return 0;
  }
  return 1;
}
static exr_edit_id fresh_id(exr_edit_doc *d) {
  exr_edit_id id=d->next_id;
  if (id) d->next_id=id==UINT64_MAX ? 0 : id+1;
  return id;
}
static void view_free(exr_edit_doc *d,exr_edit_block *v) {
  size_t i,j,k;
  for (i=0;i<v->run_count;i++) {
    release(d,v->runs[i].text); release(d,v->runs[i].opaque_xml);
  }
  if (v->table) {
    for (i=0;i<v->table->row_count;i++) {
      const exr_edit_row *r=v->table->rows+i;
      for (j=0;j<r->cell_count;j++) {
        const exr_edit_cell *c=r->cells+j;
        for (k=0;k<c->block_count;k++) view_free(d,(exr_edit_block *)c->blocks+k);
        release(d,c->blocks); release(d,c->opaque_xml);
      }
      release(d,r->cells); release(d,r->opaque_xml);
    }
    release(d,v->table->column_widths); release(d,v->table->rows); release(d,v->table);
  }
  if (v->image) {
    release(d,v->image->data); release(d,v->image);
  }
  release(d,v->runs); release(d,v->opaque_xml);
}
static void block_unref(exr_edit_doc *d,edit_block *b) {
  if (b && !--b->refs) { view_free(d,&b->view); release(d,b); }
}
static edit_block *block_ref(edit_block *b) { if (b) b->refs++; return b; }
static int view_copy(exr_edit_doc *d,exr_edit_block *b,const exr_edit_block *v) {
  size_t i,j,k; exr_edit_run *runs;
  *b=*v; b->runs=NULL; b->run_count=0; b->opaque_xml=NULL; b->table=NULL; b->image=NULL;
  if (v->opaque_size) {
    b->opaque_xml=copy_bytes(d,v->opaque_xml,v->opaque_size,0);
    if (!b->opaque_xml) return 0;
  }
  if (v->run_count) {
    runs=allocate(d,v->run_count*sizeof(*runs));
    if (!runs) return 0;
    b->runs=runs;
    for (i=0;i<v->run_count;i++) {
      runs[i]=v->runs[i]; runs[i].text=NULL; runs[i].opaque_xml=NULL;
      b->run_count++;
      if (v->runs[i].kind==EXR_EDIT_TEXT || v->runs[i].kind==EXR_EDIT_FOOTNOTE) {
        runs[i].text=copy_bytes(d,v->runs[i].text,v->runs[i].text_size,1);
        if (!runs[i].text) return 0;
      }
      if (v->runs[i].opaque_size) {
        runs[i].opaque_xml=copy_bytes(d,v->runs[i].opaque_xml,v->runs[i].opaque_size,0);
        if (!runs[i].opaque_xml) return 0;
      }
    }
  }
  if (v->image) {
    exr_edit_image *im=allocate(d,sizeof(*im));
    if (!im) return 0;
    b->image=im; *im=*v->image;
    im->data=copy_bytes(d,v->image->data,v->image->size,0);
    if (!im->data) return 0;
  }
  if (v->table) {
    exr_edit_table *t=allocate(d,sizeof(*t)); exr_edit_row *rows;
    if (!t) return 0;
    b->table=t; *t=*v->table; t->rows=NULL; t->row_count=0; t->column_widths=NULL;
    if (v->table->column_widths) {
      t->column_widths=copy_bytes(d,v->table->column_widths,t->column_count*sizeof(*t->column_widths),0);
      if (!t->column_widths) return 0;
    }
    rows=allocate(d,v->table->row_count*sizeof(*rows)); if (!rows) return 0;
    t->rows=rows;
    for (i=0;i<v->table->row_count;i++) {
      const exr_edit_row *r=v->table->rows+i; exr_edit_cell *cells;
      rows[i]=*r; rows[i].cells=NULL; rows[i].cell_count=0; rows[i].opaque_xml=NULL; t->row_count++;
      if (r->opaque_size && !(rows[i].opaque_xml=copy_bytes(d,r->opaque_xml,r->opaque_size,0))) return 0;
      cells=allocate(d,r->cell_count*sizeof(*cells)); if (!cells) return 0;
      rows[i].cells=cells;
      for (j=0;j<r->cell_count;j++) {
        const exr_edit_cell *c=r->cells+j; exr_edit_block *ps;
        cells[j]=*c; cells[j].blocks=NULL; cells[j].block_count=0; cells[j].opaque_xml=NULL; rows[i].cell_count++;
        if (c->opaque_size && !(cells[j].opaque_xml=copy_bytes(d,c->opaque_xml,c->opaque_size,0))) return 0;
        if (!c->block_count) continue;
        ps=allocate(d,c->block_count*sizeof(*ps)); if (!ps) return 0;
        cells[j].blocks=ps;
        for (k=0;k<c->block_count;k++) {
          cells[j].block_count++;
          if (!view_copy(d,ps+k,c->blocks+k)) return 0;
        }
      }
    }
  }
  return 1;
}
static edit_block *block_copy(exr_edit_doc *d,const exr_edit_block *v) {
  edit_block *b=allocate(d,sizeof(*b));
  if (!b) return NULL;
  b->refs=1;
  if (!view_copy(d,&b->view,v)) { block_unref(d,b); return NULL; }
  return b;
}
static int view_ids(exr_edit_doc *d,exr_edit_block *b,int all) {
  size_t i,j,k; exr_edit_run *r=(exr_edit_run *)b->runs;
  if ((all || !b->id) && !(b->id=fresh_id(d))) return 0;
  for (i=0;i<b->run_count;i++)
    if ((all || !r[i].id) && !(r[i].id=fresh_id(d))) return 0;
  if (b->table) for (i=0;i<b->table->row_count;i++) {
    exr_edit_row *row=(exr_edit_row *)b->table->rows+i;
    if ((all || !row->id) && !(row->id=fresh_id(d))) return 0;
    for (j=0;j<row->cell_count;j++) {
      exr_edit_cell *c=(exr_edit_cell *)row->cells+j;
      if ((all || !c->id) && !(c->id=fresh_id(d))) return 0;
      for (k=0;k<c->block_count;k++) {
        exr_edit_block *p=(exr_edit_block *)c->blocks+k; p->section_id=b->section_id;
        if (!view_ids(d,p,all)) return 0;
      }
    }
  }
  return 1;
}
static int assign_ids(exr_edit_doc *d,edit_block *b,int all) { return view_ids(d,&b->view,all); }
static size_t find_index(const exr_edit_doc *d,exr_edit_id id) {
  size_t i;
  for (i=0;i<d->count;i++) if (d->blocks[i]->view.id==id) return i;
  return SIZE_MAX;
}
/* Cell blocks are owned and journalled by their top-level table. */
typedef struct {
  size_t index,row,col,block;
  const exr_edit_cell *cell;
} block_location;
static const exr_edit_block *locate_block(const exr_edit_doc *d,exr_edit_id id,block_location *loc) {
  size_t i,j,k,p;
  memset(loc,0,sizeof(*loc));
  if (!d || !id) return NULL;
  loc->index=find_index(d,id);
  if (loc->index!=SIZE_MAX) return &d->blocks[loc->index]->view;
  for (i=0;i<d->count;i++) {
    const exr_edit_table *t=d->blocks[i]->view.table;
    if (!t) continue;
    for (j=0;j<t->row_count;j++) for (k=0;k<t->rows[j].cell_count;k++) {
      const exr_edit_cell *cell=t->rows[j].cells+k;
      for (p=0;p<cell->block_count;p++) if (cell->blocks[p].id==id) {
        loc->index=i; loc->row=j; loc->col=k; loc->block=p; loc->cell=cell;
        return cell->blocks+p;
      }
    }
  }
  return NULL;
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
  package_unref(d,t->package_before); package_unref(d,t->package_after);
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
static int anchor_position(const exr_edit_block *p,const exr_edit_block *image,
    exr_edit_id *paragraph,size_t *run,size_t *offset,size_t occurrence) {
  size_t i,j,k,n; const exr_edit_image *im=image->image;
  for (i=0;i<p->run_count;i++) if (p->runs[i].id==im->anchor_run_id) {
    const exr_edit_run *r=p->runs+i;
    if (!image->opaque_size || r->opaque_size<image->opaque_size) return 0;
    for (n=0;n<=r->opaque_size-image->opaque_size;n++) if (!memcmp((const char *)r->opaque_xml+n,image->opaque_xml,image->opaque_size)) {
      if (occurrence) { occurrence--; continue; }
      *paragraph=p->id; *run=i; *offset=n; return 1;
    }
  }
  if (p->table) for (i=0;i<p->table->row_count;i++) for (j=0;j<p->table->rows[i].cell_count;j++) {
    const exr_edit_cell *c=p->table->rows[i].cells+j;
    for (k=0;k<c->block_count;k++) if (anchor_position(c->blocks+k,image,paragraph,run,offset,occurrence)) return 1;
  }
  return 0;
}
exr_status exr_edit_image_position(const exr_edit_doc *d,const exr_edit_block *b,
    exr_edit_id *paragraph,size_t *run,size_t *offset) {
  size_t i,occurrence=0; int current=0;
  if (paragraph) *paragraph=0;
  if (run) *run=0;
  if (offset) *offset=0;
  if (!d || !b || !paragraph || !run || !offset) return EXR_ARGUMENT;
  for (i=0;i<d->count;i++) if (&d->blocks[i]->view==b) { current=1; break; }
  if (!current || b->kind!=EXR_EDIT_IMAGE || !b->image) return EXR_ARGUMENT;
  if (!b->image->anchor_run_id) return EXR_OK;
  for (i=0;i<d->count;i++) {
    const exr_edit_block *v=&d->blocks[i]->view;
    if (v->image && v->image->anchor_run_id==b->image->anchor_run_id &&
        v->image->anchor_offset<b->image->anchor_offset && v->opaque_size==b->opaque_size &&
        !memcmp(v->opaque_xml,b->opaque_xml,b->opaque_size)) occurrence++;
  }
  for (i=0;i<d->count;i++) if (anchor_position(&d->blocks[i]->view,b,paragraph,run,offset,occurrence)) return EXR_OK;
  return EXR_ARGUMENT;
}
static exr_status modify(exr_edit_doc *d,edit_change *changes,size_t count) {
  size_t i,anchors=0; int automatic=!d->active;
  exr_edit_tx *t=d->active ? d->active : exr_edit_begin(d);
  if (!t) return EXR_MEMORY;
  for (i=0;i<d->count;i++) if (d->blocks[i]->view.image && d->blocks[i]->view.image->anchor_run_id) anchors++;
  if (count>SIZE_MAX-t->count || anchors>SIZE_MAX-t->count-count || d->count==SIZE_MAX ||
      !reserve(d,(void **)&t->changes,&t->capacity,t->count+count+anchors,sizeof(*t->changes)) ||
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
  /* Anchor views leave with their run/drawing, in the same undo journal. */
  for (i=anchors ? d->count : 0;i;i--) {
    const exr_edit_block *b=&d->blocks[i-1]->view; exr_edit_id p; size_t r,o;
    if (b->image && b->image->anchor_run_id && exr_edit_image_position(d,b,&p,&r,&o)) {
      edit_change c={i-1,d->blocks[i-1],NULL};
      t->changes[t->count++]=c; block_ref(c.before); apply(d,&c,1);
    }
  }
  return automatic ? exr_edit_commit(t) : EXR_OK;
}
exr_edit_options exr_edit_defaults(void) { exr_edit_options o={100}; return o; }
exr_edit_tx *exr_edit_begin(exr_edit_doc *d) {
  exr_edit_tx *t;
  if (!d || d->active) return NULL;
  t=allocate(d,sizeof(*t));
  if (t) { t->doc=d; t->package_before=package_ref(d->package); d->active=t; }
  return t;
}
exr_status exr_edit_rollback(exr_edit_tx *t) {
  size_t i; exr_edit_doc *d;
  if (!t || t->doc->active!=t) return EXR_ARGUMENT;
  d=t->doc;
  for (i=t->count;i;i--) apply(d,t->changes+i-1,0);
  package_apply(d,t->package_before);
  d->active=NULL; tx_free(t); return EXR_OK;
}
exr_status exr_edit_commit(exr_edit_tx *t) {
  exr_edit_doc *d; exr_status status;
  if (!t || t->doc->active!=t) return EXR_ARGUMENT;
  d=t->doc; status=t->failed;
  if (status) { exr_edit_rollback(t); return status; }
  t->package_after=package_ref(d->package);
  d->active=NULL;
  if (!t->count && t->package_before==t->package_after) { tx_free(t); return EXR_OK; }
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
  package_apply(d,t->package_before);
  return EXR_OK;
}
exr_status exr_edit_redo(exr_edit_doc *d) {
  size_t i; exr_edit_tx *t;
  if (!d || d->active || d->cursor==d->history_count) return EXR_ARGUMENT;
  t=d->history[d->cursor++];
  for (i=0;i<t->count;i++) apply(d,t->changes+i,1);
  package_apply(d,t->package_after);
  return EXR_OK;
}
static int compare_ids(const void *a,const void *b) {
  exr_edit_id x=*(const exr_edit_id *)a,y=*(const exr_edit_id *)b;
  return (x>y)-(x<y);
}
static size_t collect_ids(const exr_edit_block *b,exr_edit_id *ids,size_t at) {
  size_t i,j,k;
#define ID_ADD(value) do { if (at==SIZE_MAX) return SIZE_MAX; if (ids) ids[at]=(value); at++; } while (0)
  ID_ADD(b->id);
  for (i=0;i<b->run_count;i++) { ID_ADD(b->runs[i].id); }
  if (b->table) for (i=0;i<b->table->row_count;i++) {
    const exr_edit_row *r=b->table->rows+i; ID_ADD(r->id);
    for (j=0;j<r->cell_count;j++) {
      const exr_edit_cell *c=r->cells+j; ID_ADD(c->id);
      for (k=0;k<c->block_count;k++) { at=collect_ids(c->blocks+k,ids,at); if (at==SIZE_MAX) return at; }
    }
  }
#undef ID_ADD
  return at;
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
  total=ns+np;
  for (i=0;i<nb;i++) {
    if (!block_valid(blocks+i)) return EXR_ARGUMENT;
    total=collect_ids(blocks+i,NULL,total);
    if (total==SIZE_MAX) return EXR_LIMIT;
  }
  if (total>SIZE_MAX/sizeof(*ids)) return EXR_LIMIT;
  d=calloc(1,sizeof(*d));
  if (!d) return EXR_MEMORY;
  d->bytes=sizeof(*d); d->depth=options ? options->undo_depth : 100;
  if (d->depth>SIZE_MAX/sizeof(*d->history)) { status=EXR_LIMIT; goto fail; }
  ids=allocate(d,total*sizeof(*ids));
  if (!ids) goto fail;
  for (i=0;i<ns;i++) ids[k++]=sections[i].id;
  for (i=0;i<nb;i++) k=collect_ids(blocks+i,ids,k);
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
    if (s->page_width<=0 || s->page_height<=0 || s->margin_right<0 ||
        s->margin_left<0 || s->header_distance<0 ||
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
  for (i=0;i<d->count;i++) if (d->blocks[i]->view.image && d->blocks[i]->view.image->anchor_run_id) {
    exr_edit_id paragraph; size_t run,offset;
    if (exr_edit_image_position(d,&d->blocks[i]->view,&paragraph,&run,&offset)) { status=EXR_ARGUMENT; goto fail; }
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
  package_unref(d,d->package);
  for (i=0;i<d->count;i++) block_unref(d,d->blocks[i]);
  for (i=0;i<d->part_count;i++) { release(d,d->parts[i].name); release(d,d->parts[i].data); }
  release(d,d->history); release(d,d->blocks); release(d,d->sections); release(d,d->parts); free(d);
}
size_t exr_edit_block_count(const exr_edit_doc *d) { return d ? d->count : 0; }
const exr_edit_block *exr_edit_block_at(const exr_edit_doc *d,size_t i) {
  return d && i<d->count ? &d->blocks[i]->view : NULL;
}
const exr_edit_block *exr_edit_find_block(const exr_edit_doc *d,exr_edit_id id) {
  block_location loc;
  return locate_block(d,id,&loc);
}
const exr_edit_section *exr_edit_sections(const exr_edit_doc *d,size_t *count) {
  if (count) *count=d ? d->section_count : 0;
  return d ? d->package ? d->package->sections : d->sections : NULL;
}
const exr_edit_part *exr_edit_parts(const exr_edit_doc *d,size_t *count) {
  if (count) *count=d ? d->package ? d->package->count : d->part_count : 0;
  return d ? d->package ? d->package->parts : d->parts : NULL;
}
int exr_edit_first_override(const exr_edit_doc *d,size_t section) {
  return d && d->package && section<d->section_count ? d->package->first[section] : -1;
}
int exr_edit_text_valid(const char *text,size_t size) { return utf8(text,size); }
int exr_edit_transaction_active(const exr_edit_doc *d) { return d && d->active!=NULL; }
exr_status exr_edit_package_update(exr_edit_doc *d,size_t section,
    const exr_edit_section *value,const exr_edit_part *parts,size_t count,int first) {
  edit_package *p=NULL; const exr_edit_part *old; const exr_edit_section *sections;
  size_t n,i,j; exr_status s=ready(d); int automatic; exr_edit_tx *t;
  if (s) return s;
  if (section>=d->section_count || (count && !parts) || first < -1 || first>1)
    return command_failure(d,EXR_ARGUMENT);
  old=exr_edit_parts(d,&n); sections=exr_edit_sections(d,NULL);
  if (count>SIZE_MAX-n || n+count>SIZE_MAX/sizeof(*parts)) return command_failure(d,EXR_LIMIT);
  p=allocate(d,sizeof(*p)); if (!p) return command_failure(d,EXR_MEMORY);
  p->refs=1;
  p->sections=copy_bytes(d,sections,d->section_count*sizeof(*sections),0);
  p->first=allocate(d,d->section_count);
  p->parts=allocate(d,(n+count)*sizeof(*parts));
  p->versions=allocate(d,(n+count)*sizeof(*p->versions));
  if (!p->sections || !p->first || ((n+count) && (!p->parts || !p->versions))) { s=EXR_MEMORY; goto done; }
  if (d->package) memcpy(p->first,d->package->first,d->section_count);
  else memset(p->first,-1,d->section_count);
  if (first>=0) p->first[section]=(signed char)first;
  if (value) p->sections[section]=*value;
  if (n) memcpy(p->parts,old,n*sizeof(*old));
  p->count=n;
  if (d->package) for (i=0;i<n;i++) if (d->package->versions[i]) {
    p->versions[i]=d->package->versions[i]; p->versions[i]->refs++;
  }
  for (i=0;i<count;i++) {
    edit_part_version *v;
    if (!parts[i].name || !*parts[i].name || (parts[i].size && !parts[i].data)) { s=EXR_ARGUMENT; goto done; }
    for (j=0;j<p->count && strcmp(p->parts[j].name,parts[i].name);j++) {}
    v=allocate(d,sizeof(*v)); if (!v) { s=EXR_MEMORY; goto done; }
    v->refs=1; v->part=parts[i];
    v->part.id=j<p->count ? p->parts[j].id : fresh_id(d);
    v->part.name=copy_bytes(d,parts[i].name,strlen(parts[i].name),1);
    v->part.data=copy_bytes(d,parts[i].data,parts[i].size,1);
    if (!v->part.name || !v->part.data || !v->part.id) {
      release(d,v->part.name); release(d,v->part.data); release(d,v); s=EXR_MEMORY; goto done;
    }
    if (p->versions[j] && !--p->versions[j]->refs) {
      edit_part_version *previous=p->versions[j];
      release(d,previous->part.name); release(d,previous->part.data); release(d,previous);
    }
    p->versions[j]=v; p->parts[j]=v->part;
    if (j==p->count) p->count++;
  }
  automatic=!d->active; t=d->active ? d->active : exr_edit_begin(d);
  if (!t) { s=EXR_MEMORY; goto done; }
  package_apply(d,p); s=automatic ? exr_edit_commit(t) : EXR_OK;
done:
  package_unref(d,p); return s ? command_failure(d,s) : EXR_OK;
}
size_t exr_edit_memory_bytes(const exr_edit_doc *d) { return d ? d->bytes : 0; }
/* Journal a cell splice through its owning table; all inputs may be borrowed. */
static exr_status cell_splice(exr_edit_doc *d,const block_location *loc,size_t at,
  size_t remove,const exr_edit_block *insert) {
  exr_edit_block table=d->blocks[loc->index]->view;
  exr_edit_table t=*table.table; exr_edit_row *rows=NULL;
  exr_edit_cell *cells=NULL; exr_edit_block *blocks=NULL;
  size_t count=loc->cell->block_count-remove+(insert!=NULL); exr_status s=EXR_MEMORY;
  if (!count) return command_failure(d,EXR_UNSUPPORTED);
  if (count>SIZE_MAX/sizeof(*blocks)) return command_failure(d,EXR_LIMIT);
  rows=copy_bytes(d,t.rows,t.row_count*sizeof(*rows),0);
  cells=copy_bytes(d,t.rows[loc->row].cells,t.rows[loc->row].cell_count*sizeof(*cells),0);
  blocks=allocate(d,count*sizeof(*blocks));
  if (rows && cells && blocks) {
    memcpy(blocks,loc->cell->blocks,at*sizeof(*blocks));
    if (insert) blocks[at]=*insert;
    memcpy(blocks+at+(insert!=NULL),loc->cell->blocks+at+remove,
      (loc->cell->block_count-at-remove)*sizeof(*blocks));
    cells[loc->col].blocks=blocks; cells[loc->col].block_count=count;
    cells[loc->col].changed=(cells[loc->col].changed&~CELL_PATCHED)|CELL_REPLACED;
    rows[loc->row].cells=cells; t.rows=rows; table.table=&t;
    s=exr_edit_replace(d,table.id,&table);
  }
  release(d,blocks); release(d,cells); release(d,rows);
  return s ? command_failure(d,s):EXR_OK;
}
/* Cell paragraph insertion/deletion journals the owning table, just like split. */
static exr_status cell_paragraph_splice(exr_edit_doc *d,const block_location *loc,
    const exr_edit_block *insert,exr_edit_id *out) {
  edit_block *owner;exr_edit_cell *cell;exr_edit_block *blocks;
  edit_change change;exr_status s;size_t at=loc->block+(insert ? 1:0);
  if (!exr_edit_cell_can_split(loc->cell)) return command_failure(d,EXR_UNSUPPORTED);
  if (!insert && loc->cell->block_count==1) return command_failure(d,EXR_UNSUPPORTED);
  owner=block_copy(d,&d->blocks[loc->index]->view);
  if (!owner) return command_failure(d,EXR_MEMORY);
  cell=(exr_edit_cell *)owner->view.table->rows[loc->row].cells+loc->col;
  blocks=(exr_edit_block *)cell->blocks;
  if (insert) {
    exr_edit_block *grown;
    if (cell->block_count>=SIZE_MAX/sizeof(*grown)) { s=EXR_LIMIT; goto fail; }
    grown=allocate(d,(cell->block_count+1)*sizeof(*grown));
    if (!grown) { s=EXR_MEMORY; goto fail; }
    if (!view_copy(d,grown+at,insert)) {
      view_free(d,grown+at);release(d,grown);s=EXR_MEMORY;goto fail;
    }
    grown[at].section_id=owner->view.section_id;
    if (!view_ids(d,grown+at,1)) {
      view_free(d,grown+at);release(d,grown);s=EXR_LIMIT;goto fail;
    }
    memcpy(grown,blocks,at*sizeof(*grown));
    memcpy(grown+at+1,blocks+at,(cell->block_count-at)*sizeof(*grown));
    release(d,blocks);cell->blocks=grown;cell->block_count++;
    if (out) *out=grown[at].id;
  } else {
    view_free(d,blocks+at);
    memmove(blocks+at,blocks+at+1,(cell->block_count-at-1)*sizeof(*blocks));
    cell->block_count--;
  }
  cell->changed=(cell->changed&~CELL_PATCHED)|CELL_REPLACED;
  change=(edit_change){loc->index,d->blocks[loc->index],owner};
  s=modify(d,&change,1);block_unref(d,owner);
  if (s && out) *out=0;
  return s;
fail:
  block_unref(d,owner);return command_failure(d,s);
}
exr_status exr_edit_insert_paragraph(exr_edit_doc *d,exr_edit_id after,const exr_edit_run *runs,
  size_t count,const exr_edit_para_props *props,exr_edit_id *out) {
  size_t index=0; exr_edit_block v={0}; edit_block *b; edit_change c; exr_status s=ready(d);
  if (out) *out=0;
  if (s) return s;
  if (!out) return command_failure(d,EXR_ARGUMENT);
  if (after) {
    index=find_index(d,after);
    if (index==SIZE_MAX) {
      block_location loc;
      if (!locate_block(d,after,&loc) || !loc.cell) return command_failure(d,EXR_ARGUMENT);
      v.kind=EXR_EDIT_PARAGRAPH;v.runs=runs;v.run_count=count;
      if (props) v.props=*props;
      if (!block_valid(&v)) return command_failure(d,EXR_ARGUMENT);
      return cell_paragraph_splice(d,&loc,&v,out);
    }
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
int exr_edit_cell_can_split(const exr_edit_cell *cell) {
  size_t i,j;
  if (cell->unsupported&~EXR_EDIT_CELL_OPAQUE) return 0;
  /* The decoder also marks plain multi-paragraph cells OPAQUE for legacy
     whole-cell replacement. They can still be split without losing content. */
  for (i=0;i<cell->block_count;i++) {
    if (cell->blocks[i].kind!=EXR_EDIT_PARAGRAPH) return 0;
    for (j=0;j<cell->blocks[i].run_count;j++)
      if (cell->blocks[i].runs[j].kind!=EXR_EDIT_TEXT &&
          cell->blocks[i].runs[j].kind!=EXR_EDIT_FOOTNOTE) return 0;
  }
  return 1;
}
exr_status exr_edit_split_paragraph(exr_edit_doc *d,exr_edit_id id,size_t at,size_t offset) {
  size_t index,i,p,row,col,left_count,right_start; const exr_edit_block *v; block_location loc;
  const exr_edit_cell *cell=NULL; exr_edit_block a,b;
  edit_block *left=NULL,*right=NULL; exr_edit_run *temp=NULL;
  edit_change c[2]; exr_status s=ready(d); int divided=0;
  if (s) return s;
  v=locate_block(d,id,&loc);
  if (!v) return command_failure(d,EXR_ARGUMENT);
  index=loc.index; row=loc.row; col=loc.col; p=loc.block; cell=loc.cell;
  if (cell && !exr_edit_cell_can_split(cell)) return command_failure(d,EXR_UNSUPPORTED);
  if (v->kind!=EXR_EDIT_PARAGRAPH) return command_failure(d,EXR_UNSUPPORTED);
  if (at>v->run_count || (at==v->run_count && offset)) return command_failure(d,EXR_ARGUMENT);
  left_count=at; right_start=at;
  if (at<v->run_count) {
    const exr_edit_run *r=v->runs+at;
    if (offset>r->text_size || (r->kind!=EXR_EDIT_TEXT && offset) ||
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
  if (cell) {
    exr_edit_block table=d->blocks[index]->view; exr_edit_table t=*table.table;
    exr_edit_row *rows=NULL; exr_edit_cell *cells=NULL; exr_edit_block *blocks=NULL;
    if (cell->block_count>=SIZE_MAX/sizeof(*blocks)) { s=EXR_LIMIT; goto done; }
    rows=copy_bytes(d,t.rows,t.row_count*sizeof(*rows),0);
    cells=copy_bytes(d,t.rows[row].cells,t.rows[row].cell_count*sizeof(*cells),0);
    blocks=allocate(d,(cell->block_count+1)*sizeof(*blocks));
    if (!rows || !cells || !blocks) s=EXR_MEMORY;
    else {
      memcpy(blocks,cell->blocks,p*sizeof(*blocks));
      blocks[p]=left->view; blocks[p+1]=right->view;
      memcpy(blocks+p+2,cell->blocks+p+1,(cell->block_count-p-1)*sizeof(*blocks));
      cells[col].blocks=blocks; cells[col].block_count++;
      cells[col].changed=(cells[col].changed&~CELL_PATCHED)|CELL_REPLACED;
      rows[row].cells=cells; t.rows=rows; table.table=&t;
      s=exr_edit_replace(d,table.id,&table);
    }
    release(d,blocks); release(d,cells); release(d,rows); goto done;
  }
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
  block_location loc; const exr_edit_block *v=locate_block(d,id,&loc);
  if (v && loc.cell) {
    exr_edit_block changed=*v; exr_edit_run *runs=NULL;
    if (v->kind!=EXR_EDIT_PARAGRAPH || !exr_edit_cell_can_split(loc.cell))
      return command_failure(d,EXR_UNSUPPORTED);
    if (rp && run>=v->run_count) return command_failure(d,EXR_ARGUMENT);
    if (rp && v->runs[run].kind!=EXR_EDIT_TEXT) return command_failure(d,EXR_UNSUPPORTED);
    if (para) changed.props=*para;
    if (rp) {
      runs=copy_bytes(d,v->runs,v->run_count*sizeof(*runs),0);
      if (!runs) return command_failure(d,EXR_MEMORY);
      runs[run].props=*rp; changed.runs=runs;
    }
    s=cell_splice(d,&loc,loc.block,1,&changed);
    release(d,runs); return s;
  }
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
exr_status exr_edit_set_run_text(exr_edit_doc *d,exr_edit_id id,size_t run,const char *text,size_t size) {
  block_location loc; const exr_edit_block *v; exr_edit_block *target;
  edit_block *b; exr_edit_run *r; char *copy; edit_change change; exr_status s=ready(d);
  if (s) return s;
  if (size==SIZE_MAX || !utf8(text,size)) return command_failure(d,EXR_ARGUMENT);
  v=locate_block(d,id,&loc);
  if (!v) return command_failure(d,EXR_ARGUMENT);
  if (v->kind!=EXR_EDIT_PARAGRAPH || (loc.cell && !exr_edit_cell_can_split(loc.cell)))
    return command_failure(d,EXR_UNSUPPORTED);
  if (run>=v->run_count) return command_failure(d,EXR_ARGUMENT);
  if (v->runs[run].kind!=EXR_EDIT_TEXT) return command_failure(d,EXR_UNSUPPORTED);
  b=block_copy(d,&d->blocks[loc.index]->view);
  if (!b) return command_failure(d,EXR_MEMORY);
  target=&b->view;
  if (loc.cell) {
    exr_edit_cell *cell=(exr_edit_cell *)b->view.table->rows[loc.row].cells+loc.col;
    target=(exr_edit_block *)cell->blocks+loc.block;
    if (!(cell->changed&CELL_REPLACED)) cell->changed|=CELL_PATCHED;
  }
  copy=copy_bytes(d,text,size,1);
  if (!copy) { block_unref(d,b); return command_failure(d,EXR_MEMORY); }
  r=(exr_edit_run *)target->runs+run;
  release(d,r->text); r->text=copy; r->text_size=size;
  change.index=loc.index; change.before=d->blocks[loc.index]; change.after=b;
  s=modify(d,&change,1); block_unref(d,b); return s;
}
exr_status exr_edit_insert_run(exr_edit_doc *d,exr_edit_tx *tx,exr_edit_id id,
  size_t at,const char *text,size_t size,const exr_edit_run_props *props) {
  block_location loc; const exr_edit_block *v; exr_edit_block changed;
  exr_edit_run *runs; exr_status s=exr_edit_tx_ready(d,tx);
  if (s) return s;
  v=locate_block(d,id,&loc);
  if (!v || !text || !size || size==SIZE_MAX || !utf8(text,size) || (props && !run_props_valid(props)))
    return command_failure(d,EXR_ARGUMENT);
  if (at>v->run_count) return command_failure(d,EXR_ARGUMENT);
  if (v->kind!=EXR_EDIT_PARAGRAPH || (loc.cell && !exr_edit_cell_can_split(loc.cell)))
    return command_failure(d,EXR_UNSUPPORTED);
  if (v->run_count>=SIZE_MAX/sizeof(*runs)) return command_failure(d,EXR_LIMIT);
  runs=allocate(d,(v->run_count+1)*sizeof(*runs));
  if (!runs) return command_failure(d,EXR_MEMORY);
  if (at) memcpy(runs,v->runs,at*sizeof(*runs));
  runs[at].text=text; runs[at].text_size=size;
  if (props) runs[at].props=*props;
  runs[at].id=fresh_id(d);
  if (v->run_count>at) memcpy(runs+at+1,v->runs+at,(v->run_count-at)*sizeof(*runs));
  changed=*v; changed.runs=runs; changed.run_count++;
  s=!runs[at].id ? command_failure(d,EXR_LIMIT):loc.cell ?
    cell_splice(d,&loc,loc.block,1,&changed):exr_edit_replace(d,id,&changed);
  release(d,runs); return s;
}
static int footnote_scan(const exr_edit_block *b,size_t wanted,exr_edit_id id,
  size_t *number,exr_edit_footnote *out) {
  size_t i,j,k;
  for (i=0;i<b->run_count;i++) if (b->runs[i].kind==EXR_EDIT_FOOTNOTE) {
    const exr_edit_run *r=b->runs+i;
    size_t index=(*number)++;
    if ((id && r->id==id) || (!id && index==wanted)) {
      if (out) *out=(exr_edit_footnote){r->id,b->id,i,index+1,r->text,r->text_size};
      return 1;
    }
  }
  if (b->table) for (i=0;i<b->table->row_count;i++) for (j=0;j<b->table->rows[i].cell_count;j++) {
    const exr_edit_cell *c=b->table->rows[i].cells+j;
    for (k=0;k<c->block_count;k++) if (footnote_scan(c->blocks+k,wanted,id,number,out)) return 1;
  }
  return 0;
}
static int footnote_lookup(const exr_edit_doc *d,size_t wanted,exr_edit_id id,exr_edit_footnote *out) {
  size_t i,number=0;
  if (d) for (i=0;i<d->count;i++)
    if (footnote_scan(&d->blocks[i]->view,wanted,id,&number,out)) return 1;
  return 0;
}
size_t exr_edit_footnote_count(const exr_edit_doc *d) {
  size_t i,number=0;
  if (d) for (i=0;i<d->count;i++) footnote_scan(&d->blocks[i]->view,SIZE_MAX,0,&number,NULL);
  return number;
}
exr_status exr_edit_footnote_at(const exr_edit_doc *d,size_t index,exr_edit_footnote *out) {
  if (out) memset(out,0,sizeof(*out));
  return d && out && footnote_lookup(d,index,0,out) ? EXR_OK:EXR_ARGUMENT;
}
exr_status exr_edit_footnote_insert(exr_edit_doc *d,exr_edit_id id,size_t at,size_t offset,
  const char *text,size_t size,exr_edit_id *out) {
  block_location loc; const exr_edit_block *v; exr_edit_block changed;
  exr_edit_run *runs; exr_edit_id note; size_t note_at,extra=1; exr_status s=ready(d);
  if (out) *out=0;
  if (s) return s;
  if (!out || size==SIZE_MAX || !utf8(text,size)) return command_failure(d,EXR_ARGUMENT);
  v=locate_block(d,id,&loc);
  if (!v || at>v->run_count || (at==v->run_count && offset)) return command_failure(d,EXR_ARGUMENT);
  if (v->kind!=EXR_EDIT_PARAGRAPH || (loc.cell && !exr_edit_cell_can_split(loc.cell)))
    return command_failure(d,EXR_UNSUPPORTED);
  if (at<v->run_count) {
    const exr_edit_run *r=v->runs+at;
    if (offset>r->text_size || (r->kind!=EXR_EDIT_TEXT && offset) ||
        (offset<r->text_size && ((unsigned char)r->text[offset]&0xc0)==0x80))
      return command_failure(d,EXR_ARGUMENT);
    if (offset) { if (offset==r->text_size) at++; else extra++; }
  }
  if (v->run_count>SIZE_MAX/sizeof(*runs)-extra) return command_failure(d,EXR_LIMIT);
  runs=allocate(d,(v->run_count+extra)*sizeof(*runs));
  if (!runs) return command_failure(d,EXR_MEMORY);
  if (at) memcpy(runs,v->runs,at*sizeof(*runs));
  note_at=at+(extra==2);
  if (extra==2) {
    runs[at]=v->runs[at]; runs[at].text_size=offset;
    runs[at+2]=v->runs[at]; runs[at+2].text+=offset; runs[at+2].text_size-=offset;
    runs[at+2].id=fresh_id(d);
    if (!runs[at+2].id) { release(d,runs); return command_failure(d,EXR_LIMIT); }
  }
  note=fresh_id(d); runs[note_at].id=note; runs[note_at].kind=EXR_EDIT_FOOTNOTE;
  runs[note_at].text=text; runs[note_at].text_size=size;
  if (v->run_count>at+(extra==2))
    memcpy(runs+at+extra+(extra==2),v->runs+at+(extra==2),
      (v->run_count-at-(extra==2))*sizeof(*runs));
  changed=*v; changed.runs=runs; changed.run_count+=extra;
  s=!note ? command_failure(d,EXR_LIMIT):loc.cell ?
    cell_splice(d,&loc,loc.block,1,&changed):exr_edit_replace(d,id,&changed);
  if (!s) *out=note;
  release(d,runs); return s;
}
static exr_status footnote_change(exr_edit_doc *d,exr_edit_id id,const char *text,size_t size,int remove) {
  exr_edit_footnote note; block_location loc; const exr_edit_block *v; exr_edit_block changed;
  exr_edit_run *runs; size_t count; exr_status s=ready(d);
  if (s) return s;
  if (!id || (!remove && (size==SIZE_MAX || !utf8(text,size))) ||
      !footnote_lookup(d,SIZE_MAX,id,&note)) return command_failure(d,EXR_ARGUMENT);
  v=locate_block(d,note.paragraph_id,&loc);
  if (loc.cell && !exr_edit_cell_can_split(loc.cell)) return command_failure(d,EXR_UNSUPPORTED);
  count=v->run_count-(remove!=0);
  runs=count ? allocate(d,count*sizeof(*runs)):NULL;
  if (count && !runs) return command_failure(d,EXR_MEMORY);
  if (remove) {
    if (note.run_index) memcpy(runs,v->runs,note.run_index*sizeof(*runs));
    if (v->run_count>note.run_index+1)
      memcpy(runs+note.run_index,v->runs+note.run_index+1,(v->run_count-note.run_index-1)*sizeof(*runs));
  } else {
    memcpy(runs,v->runs,count*sizeof(*runs));
    runs[note.run_index].text=text; runs[note.run_index].text_size=size;
  }
  changed=*v; changed.runs=runs; changed.run_count=count;
  s=loc.cell ? cell_splice(d,&loc,loc.block,1,&changed):exr_edit_replace(d,v->id,&changed);
  release(d,runs); return s;
}
exr_status exr_edit_footnote_set_text(exr_edit_doc *d,exr_edit_id id,const char *text,size_t size) {
  return footnote_change(d,id,text,size,0);
}
exr_status exr_edit_footnote_delete(exr_edit_doc *d,exr_edit_id id) {
  return footnote_change(d,id,NULL,0,1);
}
static exr_edit_run *mutable_anchor(exr_edit_block *b,exr_edit_id paragraph,size_t run) {
  size_t i,j,k;
  if (b->id==paragraph && run<b->run_count) return (exr_edit_run *)b->runs+run;
  if (b->table) for (i=0;i<b->table->row_count;i++) for (j=0;j<b->table->rows[i].cell_count;j++) {
    exr_edit_cell *c=(exr_edit_cell *)b->table->rows[i].cells+j;
    for (k=0;k<c->block_count;k++) {
      exr_edit_run *r=mutable_anchor((exr_edit_block *)c->blocks+k,paragraph,run);
      if (r) { if (!(c->changed&CELL_REPLACED)) c->changed|=CELL_PATCHED; return r; }
    }
  }
  return NULL;
}
static exr_status delete_anchor(exr_edit_doc *d,size_t index) {
  const exr_edit_block *image=&d->blocks[index]->view; exr_edit_id paragraph;
  size_t run,offset,i; exr_status s; edit_block *owner=NULL; exr_edit_run *r=NULL; edit_change changes[2];
  s=exr_edit_image_position(d,image,&paragraph,&run,&offset); if (s) return command_failure(d,s);
  for (i=0;i<d->count;i++) {
    exr_edit_id p; size_t ri,o;
    if (anchor_position(&d->blocks[i]->view,image,&p,&ri,&o,0)) {
      owner=block_copy(d,&d->blocks[i]->view); if (!owner) return command_failure(d,EXR_MEMORY);
      r=mutable_anchor(&owner->view,paragraph,run); break;
    }
  }
  if (!r) { block_unref(d,owner); return command_failure(d,EXR_ARGUMENT); }
  /* The copied XML allocation is private to this version. */
  memmove((char *)r->opaque_xml+offset,(const char *)r->opaque_xml+offset+image->opaque_size,
    r->opaque_size-offset-image->opaque_size); r->opaque_size-=image->opaque_size;
  changes[0]=(edit_change){i,d->blocks[i],owner};
  changes[1]=(edit_change){index,d->blocks[index],NULL};
  s=modify(d,changes,2); block_unref(d,owner); return s;
}
exr_status exr_edit_delete_block(exr_edit_doc *d,exr_edit_id id) {
  size_t index; edit_change c; exr_status s=ready(d);
  if (s) return s;
  index=find_index(d,id);
  if (index==SIZE_MAX) {
    block_location loc;
    if (!locate_block(d,id,&loc) || !loc.cell) return command_failure(d,EXR_ARGUMENT);
    return cell_paragraph_splice(d,&loc,NULL,NULL);
  }
  if (d->blocks[index]->view.kind==EXR_EDIT_TABLE ||
      d->blocks[index]->view.kind==EXR_EDIT_OPAQUE_BLOCK) return command_failure(d,EXR_UNSUPPORTED);
  if (d->blocks[index]->view.image && d->blocks[index]->view.image->anchor_run_id)
    return delete_anchor(d,index);
  c.index=index; c.before=d->blocks[index]; c.after=NULL;
  return modify(d,&c,1);
}
exr_status exr_edit_ready(exr_edit_doc *d) { return ready(d); }
exr_status exr_edit_tx_ready(exr_edit_doc *d,exr_edit_tx *tx) {
  exr_status s=ready(d);
  return s ? s : !tx || d->active!=tx ? command_failure(d,EXR_ARGUMENT) : EXR_OK;
}
exr_status exr_edit_failure(exr_edit_doc *d,exr_status s) { return command_failure(d,s); }
exr_status exr_edit_replace(exr_edit_doc *d,exr_edit_id id,const exr_edit_block *v) {
  size_t index; edit_block *b=NULL; edit_change c; exr_status s=ready(d);
  if (s) return s;
  index=find_index(d,id);
  if (index==SIZE_MAX || (v && (!block_valid(v) || v->id!=id ||
      v->section_id!=d->blocks[index]->view.section_id))) return command_failure(d,EXR_ARGUMENT);
  if (v) {
    b=block_copy(d,v); if (!b) return command_failure(d,EXR_MEMORY);
    if (!assign_ids(d,b,0)) { block_unref(d,b); return command_failure(d,EXR_LIMIT); }
  }
  c.index=index; c.before=d->blocks[index]; c.after=b;
  s=modify(d,&c,1); block_unref(d,b); return s;
}
exr_status exr_edit_insert_block(exr_edit_doc *d,exr_edit_id after,const exr_edit_block *view,exr_edit_id *out) {
  size_t index=0; edit_block *b; edit_change c; exr_edit_block v; exr_status s=ready(d);
  if (out) *out=0;
  if (s) return s;
  if (!out || !view || !block_valid(view)) return command_failure(d,EXR_ARGUMENT);
  v=*view;
  if (after) {
    index=find_index(d,after); if (index==SIZE_MAX) return command_failure(d,EXR_ARGUMENT);
    v.section_id=d->blocks[index++]->view.section_id;
  } else v.section_id=d->sections[0].id;
  b=block_copy(d,&v); if (!b) return command_failure(d,EXR_MEMORY);
  if (!assign_ids(d,b,1)) { block_unref(d,b); return command_failure(d,EXR_LIMIT); }
  c.index=index; c.before=NULL; c.after=b;
  s=modify(d,&c,1); if (!s) *out=b->view.id;
  block_unref(d,b); return s;
}
