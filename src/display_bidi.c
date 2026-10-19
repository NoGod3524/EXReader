/* SPDX-License-Identifier: MIT */
#include "flow_internal.h"
#include "bidi_internal.h"

void exr_display_builder_clear(exr_display_builder *b) {
  free(b->text.data);free(b->sources);free(b->flags);memset(b,0,sizeof(*b));
}
exr_status exr_display_append(exr_display_builder *b,const char *text,size_t size,
                               size_t source,int fixed,int generated,exr_error *e) {
  size_t at=0;uint32_t cp;
  while(at<size) {
    size_t start=at,next;
    if(!exr_next(text,size,&at,&cp)) return exr_fail(e,EXR_ENCODING,"Invalid display UTF-8");
    /* Bound the projected result as well as its temporary builder. */
    if(b->count>=EXR_MAX_ITEMS || b->count>=(EXR_MAX_TEXT-sizeof(exr_display_view))/(sizeof(exr_bidi_scalar)+11))
      return exr_fail(e,EXR_LIMIT,"Display bidi result exceeds 64 MiB");
    if(!(b->count&1023) && exr_control_cancel(b->control,e)!=EXR_OK) return EXR_CANCELLED;
    if(b->count==b->capacity) {
      size_t *sources;unsigned char *flags;
      next=b->capacity ? b->capacity*2 : 64;
      if(next>(EXR_MAX_TEXT-sizeof(exr_display_view))/(sizeof(exr_bidi_scalar)+11))
        next=(EXR_MAX_TEXT-sizeof(exr_display_view))/(sizeof(exr_bidi_scalar)+11);
      sources=realloc(b->sources,next*sizeof(*sources));if(!sources) return exr_fail(e,EXR_MEMORY,"Display source allocation failed");
      b->sources=sources;
      flags=realloc(b->flags,next);if(!flags) return exr_fail(e,EXR_MEMORY,"Display boundary allocation failed");
      b->flags=flags;b->capacity=next;
    }
    if(!exr_codepoint(&b->text,cp)) return exr_fail(e,EXR_MEMORY,"Display text allocation failed");
    b->sources[b->count]=fixed ? source : source+start;
    if(b->count && b->sources[b->count]<b->sources[b->count-1]) return exr_fail(e,EXR_FORMAT,"Nonmonotonic display source map");
    b->flags[b->count++]=generated ? EXR_DISPLAY_GENERATED : 0;
  }
  return EXR_OK;
}
void exr_display_view_free(exr_display_view *v) {
  if(!v) return;
  exr_bidi_free(v->bidi);free(v->sources);free(v->boundaries);free(v);
}
exr_status exr_display_finish(exr_display_builder *b,exr_direction direction,exr_direction first,const exr_bidi_override *overrides,exr_display_view **out,exr_error *e) {
  exr_display_view *v=calloc(1,sizeof(*v));unsigned char *boundaries=NULL;exr_status status;size_t i;
  *out=NULL;if(!v) return exr_fail(e,EXR_MEMORY,"Display bidi allocation failed");
  if(first!=EXR_DIRECTION_AUTO) status=exr_bidi_analyze_first(b->text.data ? b->text.data : "",b->text.size,direction,first,&v->bidi,e);
  else status=exr_bidi_analyze_mapped(b->text.data ? b->text.data : "",b->text.size,direction,b->sources,overrides,&v->bidi,e);
  if(status==EXR_OK) status=exr_text_analyze(b->text.data ? b->text.data : "",b->text.size,&boundaries,e);
  if(status==EXR_OK) {
    const exr_bidi_scalar *s=exr_bidi_scalars(v->bidi,NULL);
    for(i=0;i<b->count;i++) b->flags[i]|=boundaries[s[i].start];
    v->count=b->count;v->capacity=b->capacity;v->sources=b->sources;v->boundaries=b->flags;
    b->sources=NULL;b->flags=NULL;b->count=b->capacity=0;*out=v;
  } else exr_display_view_free(v);
  free(boundaries);return status;
}
exr_status exr_display_apply(const exr_display_view *v,exr_glyph *g,size_t count,size_t first,exr_error *e) {
  const exr_bidi_scalar *s=exr_bidi_scalars(v->bidi,NULL);size_t i;
  for(i=0;i<count;i++) {
    uint32_t cp=g[i].flags&EXR_GLYPH_RUBY_ITEM ? 0xfffc : g[i].codepoint;
    if(g[i].flags&EXR_GLYPH_DELETED) { g[i].page=first;g[i].bidi_level=first<v->count ? s[first].level : 0;g[i].flags|=EXR_GLYPH_DISPLAY_BIDI|EXR_GLYPH_HIDDEN;continue; }
    if(first>=v->count || s[first].codepoint!=cp || v->sources[first]!=g[i].start)
      return exr_fail(e,EXR_FORMAT,"Display glyph/source projection mismatch");
    g[i].page=first;g[i].bidi_level=s[first++].level;g[i].flags|=EXR_GLYPH_DISPLAY_BIDI;
    if(exr_text_hidden(cp) || g[i].bidi_level==UINT_MAX) g[i].flags|=EXR_GLYPH_HIDDEN;
    else g[i].flags&=~EXR_GLYPH_HIDDEN;
  }
  return EXR_OK;
}
size_t exr_display_original(const exr_display_view *v,size_t source) {
  size_t lo=0,hi=v->count;
  while(lo<hi) { size_t mid=lo+(hi-lo)/2;if(v->sources[mid]<source) lo=mid+1;else hi=mid; }
  while(lo<v->count && v->sources[lo]==source) {
    if(!(v->boundaries[lo]&EXR_DISPLAY_GENERATED)) return lo;
    lo++;
  }
  return SIZE_MAX;
}
exr_status exr_display_apply_line(const exr_display_view *v,exr_glyph *g,size_t count,
                                   size_t first,size_t scalars,exr_error *e) {
  unsigned *levels=NULL;size_t i;exr_status status=exr_display_apply(v,g,count,first,e);
  if(status!=EXR_OK || !scalars) return status;
  levels=malloc(scalars*sizeof(*levels));if(!levels) return exr_fail(e,EXR_MEMORY,"Display line levels allocation failed");
  status=exr_bidi_line_levels(v->bidi,first,scalars,levels);
  if(status==EXR_OK) for(i=0;i<count;i++) {
    if((g[i].flags&EXR_GLYPH_DELETED) && (g[i].page<first || g[i].page-first>=scalars)) continue;
    if(g[i].page<first || g[i].page-first>=scalars) { status=exr_fail(e,EXR_FORMAT,"Display glyph outside line levels");break; }
    g[i].bidi_level=levels[g[i].page-first];
  }
  free(levels);return status;
}
static unsigned piece_kind(const exr_document *d,const exr_glyph *g) {
  size_t at=g->start;uint32_t cp;
  if(g->flags&EXR_GLYPH_GENERATED) return 1;
  if(!(g->flags&EXR_GLYPH_RUBY_ITEM) && exr_next(d->text,g->end,&at,&cp) && at==g->end && cp==g->codepoint) return 0;
  return 2;
}
void exr_display_patch_free(exr_display_patch *p) {
  while(p && !--p->refs) { exr_display_patch *previous=p->previous;free(p->pieces);free(p->text);free(p);p=previous; }
}
exr_status exr_display_patch_create(const exr_document *d,const exr_glyph *g,size_t count,
                                     exr_display_patch *previous,exr_display_patch **out,exr_error *e) {
  exr_display_patch *p=calloc(1,sizeof(*p));exr_buffer text={0};size_t i,capacity=count;
  *out=NULL;if(!p) return exr_fail(e,EXR_MEMORY,"Display patch allocation failed");
  p->refs=1;p->start=SIZE_MAX;p->pieces=count ? calloc(count,sizeof(*p->pieces)) : NULL;
  if(count && !p->pieces) goto memory;
  for(i=0;i<count;i++) {
    unsigned kind=piece_kind(d,g+i);exr_display_piece *piece=p->count ? p->pieces+p->count-1 : NULL;
    if(g[i].start<p->start) p->start=g[i].start;
    if(g[i].end>p->end) p->end=g[i].end;
    if(g[i].flags&EXR_GLYPH_DELETED) continue;
    if(!piece || piece->kind!=kind || (kind ? piece->start!=g[i].start || piece->end!=g[i].end : piece->end!=g[i].start)) {
      piece=p->pieces+p->count++;*piece=(exr_display_piece){g[i].start,g[i].end,text.size,0,kind};
    }
    if(!kind) { piece->end=g[i].end;continue; }
    { size_t before=text.size;uint32_t cp=g[i].flags&EXR_GLYPH_RUBY_ITEM ? 0xfffc : g[i].codepoint;
      if(!exr_codepoint(&text,cp)) goto memory;
      piece->size+=text.size-before;
    }
  }
  if(p->start==SIZE_MAX) p->start=p->end=previous ? previous->end : 0;
  if(p->count && p->count<capacity) { void *q=realloc(p->pieces,p->count*sizeof(*p->pieces));if(q) { p->pieces=q;capacity=p->count; } }
  if(!p->count) { free(p->pieces);p->pieces=NULL;capacity=0; }
  if(text.size) { void *q=realloc(text.data,text.size);if(q) { text.data=q;text.capacity=text.size; } }
  else { free(text.data);text.data=NULL;text.capacity=0; }
  p->text=text.data;p->bytes=sizeof(*p)+capacity*sizeof(*p->pieces)+text.capacity;
  p->total=p->bytes+(previous ? previous->total : 0);p->depth=1+(previous ? previous->depth : 0);
  if(p->total>16*1024*1024) { exr_display_patch_free(p);return exr_fail(e,EXR_LIMIT,"Display history exceeds 16 MiB"); }
  p->previous=previous;if(previous) previous->refs++;*out=p;return EXR_OK;
memory:
  free(text.data);exr_display_patch_free(p);return exr_fail(e,EXR_MEMORY,"Display patch allocation failed");
}
exr_status exr_display_patch_append(exr_display_builder *b,const exr_document *d,const exr_display_patch *p,exr_error *e) {
  size_t i;exr_status status;
  for(i=0;i<p->count;i++) {
    const exr_display_piece *v=p->pieces+i;
    status=exr_display_append(b,v->kind ? p->text+v->offset : d->text+v->start,
                               v->kind ? v->size : v->end-v->start,v->start,!!v->kind,v->kind==1,e);
    if(status!=EXR_OK) return status;
  }
  return EXR_OK;
}
void exr_display_state_free(exr_display_state *s) {
  if(!s) return;
  exr_display_patch_free(s->history);exr_display_patch_free(s->pending);
  exr_display_patch_free(s->context);exr_display_patch_free(s->pending_context);
  exr_display_view_free(s->active);exr_display_view_free(s->trial);free(s);
}
exr_display_state *exr_display_state_clone(const exr_display_state *s) {
  exr_display_state *copy;
  if(!s) return NULL;
  copy=malloc(sizeof(*copy));if(!copy) return NULL;*copy=*s;
  copy->active=copy->trial=NULL;if(copy->history) copy->history->refs++;if(copy->pending) copy->pending->refs++;
  if(copy->context) copy->context->refs++;
  if(copy->pending_context) copy->pending_context->refs++;
  return copy;
}
size_t exr_display_state_size(const exr_display_state *s) {
  return s ? sizeof(*s)+(s->history ? s->history->total : 0)+(s->pending ? s->pending->bytes : 0)+
    (s->context ? s->context->total : 0)+(s->pending_context ? s->pending_context->bytes : 0) : 0;
}

static void plan_feed(exr_plan_builder *b,size_t at) {
  uint32_t cp;
  while(exr_next(b->text.text.data,b->text.text.size,&at,&cp)) {
    unsigned type=exr_bidi_tail_type(cp),original=type,solid=0;
    if(!exr_bidi_window_safe(cp)) b->safe=0;
    if(type>=1 && type<=3) { b->last_strong=type;if(!b->first_strong) b->first_strong=type; }
    if(type==8) continue;
    if(type==6) type=b->previous;
    b->previous=type;
    if(type>=1 && type<=5) {
      solid=type==1 || (type==4 && b->last_strong==1) ? 1 : 2;
      b->tail=b->last_dir=solid;b->ambiguous=0;
    } else if(type!=7 || original==6) { b->tail=0;if(type==9) b->ambiguous=1; }
  }
}
exr_status exr_plan_seed(exr_plan_builder *b,const exr_document *d,const exr_display_patch *prefix,
  exr_direction direction,exr_direction initial,exr_error *e) {
  const exr_display_patch **parts=NULL,*p;size_t n=0,i;exr_status status=EXR_OK;
  b->safe=1;b->direction=direction;b->first_direction=initial;
  b->last_dir=direction==EXR_DIRECTION_LTR || initial==EXR_DIRECTION_LTR ? 1 :
    direction==EXR_DIRECTION_RTL || initial==EXR_DIRECTION_RTL ? 2 : 0;
  if(prefix) {
    parts=malloc(prefix->depth*sizeof(*parts));if(!parts) return exr_fail(e,EXR_MEMORY,"Paragraph prefix allocation failed");
    for(p=prefix;p;p=p->previous) parts[n++]=p;
    for(i=n;i && status==EXR_OK;i--) status=exr_display_patch_append(&b->text,d,parts[i-1],e);
  }
  free(parts);if(status!=EXR_OK) return status;
  b->first=b->text.count;plan_feed(b,0);return EXR_OK;
}
int exr_plan_can_cut(const exr_plan_builder *b) {
  unsigned base=b->direction==EXR_DIRECTION_LTR ? 1 : b->direction==EXR_DIRECTION_RTL ? 2 :
    b->first_direction==EXR_DIRECTION_LTR ? 1 : b->first_direction==EXR_DIRECTION_RTL ? 2 :
    b->first_strong==1 ? 1 : b->first_strong ? 2 : 0;
  if(!b->safe || !base) return 0;
  if(b->tail) return 1;
  return !b->ambiguous && b->last_dir==base;
}
void exr_plan_builder_clear(exr_plan_builder *b) {
  exr_display_builder_clear(&b->text);free(b->lines);memset(b,0,sizeof(*b));
}
static size_t plan_builder_bytes(const exr_plan_builder *b) {
  return sizeof(exr_display_plan)+b->text.text.capacity+b->text.capacity*(sizeof(size_t)+1)+b->line_capacity*sizeof(*b->lines);
}
exr_status exr_plan_append(exr_plan_builder *b,const exr_document *d,const exr_display_patch *line,
  int forced,int final,exr_error *e) {
  size_t old_bytes=b->text.text.size;exr_status status=exr_display_patch_append(&b->text,d,line,e);exr_plan_line *record;
  if(status!=EXR_OK) return status;
  if(!exr_grow((void **)&b->lines,&b->line_capacity,b->line_count+1,sizeof(*b->lines)))
    return exr_fail(e,EXR_MEMORY,"Paragraph line plan allocation failed");
  record=&b->lines[b->line_count++];memset(record,0,sizeof(*record));
  record->end=b->text.count;record->start_source=line->start;record->end_source=line->end;
  record->flags=(!!forced) | ((!!final)<<1);plan_feed(b,old_bytes);
  if(plan_builder_bytes(b)>24*1024*1024) return exr_fail(e,EXR_LIMIT,"Paragraph trial exceeds 24 MiB");
  return EXR_OK;
}
exr_status exr_plan_finish(exr_plan_builder *b,exr_direction direction,exr_display_plan **out,exr_error *e) {
  exr_display_plan *p=calloc(1,sizeof(*p));*out=NULL;
  if(!p) return exr_fail(e,EXR_MEMORY,"Paragraph plan allocation failed");
  { void *q;
    if(b->text.count) {
      int shrunk=1;
      q=realloc(b->text.sources,b->text.count*sizeof(size_t));if(q) b->text.sources=q;else shrunk=0;
      q=realloc(b->text.flags,b->text.count);if(q) b->text.flags=q;else shrunk=0;
      if(shrunk) b->text.capacity=b->text.count;
    }
    if(b->text.text.size) { q=realloc(b->text.text.data,b->text.text.size);if(q) { b->text.text.data=q;b->text.text.capacity=b->text.text.size; } }
    if(b->line_count) { q=realloc(b->lines,b->line_count*sizeof(*b->lines));if(q) { b->lines=q;b->line_capacity=b->line_count; } }
  }
  if(plan_builder_bytes(b)>16*1024*1024) { free(p);return exr_fail(e,EXR_LIMIT,"Paragraph plan exceeds 16 MiB"); }
  p->refs=1;p->direction=direction;p->bytes=plan_builder_bytes(b);p->content=*b;p->first=b->first;p->first_direction=b->first_direction;
  p->content.text.control=NULL;memset(b,0,sizeof(*b));*out=p;return EXR_OK;
}
void exr_plan_free(exr_display_plan *p) {
  if(p && !--p->refs) { exr_plan_builder_clear(&p->content);free(p); }
}
int exr_plan_equal(const exr_display_plan *a,const exr_display_plan *b) {
  const exr_plan_builder *x=&a->content,*y=&b->content;
  return a->direction==b->direction && a->first_direction==b->first_direction && a->first==b->first && a->closed==b->closed && x->text.count==y->text.count && x->text.text.size==y->text.text.size &&
    x->line_count==y->line_count &&
    (!x->text.text.size || !memcmp(x->text.text.data,y->text.text.data,x->text.text.size)) &&
    (!x->text.count || (!memcmp(x->text.sources,y->text.sources,x->text.count*sizeof(size_t)) && !memcmp(x->text.flags,y->text.flags,x->text.count))) &&
    (!x->line_count || !memcmp(x->lines,y->lines,x->line_count*sizeof(*x->lines)));
}
exr_status exr_plan_view(const exr_display_plan *p,const exr_control *control,exr_display_view **out,exr_error *e) {
  const exr_display_builder *source=&p->content.text;exr_display_builder b={0};exr_status status;
  *out=NULL;
  b.control=control;b.text.data=source->text.data;b.text.size=source->text.size;
  if(source->count) {
    b.sources=malloc(source->count*sizeof(size_t));b.flags=malloc(source->count);
    if(!b.sources || !b.flags) { free(b.sources);free(b.flags);return exr_fail(e,EXR_MEMORY,"Paragraph projection allocation failed"); }
    memcpy(b.sources,source->sources,source->count*sizeof(size_t));memcpy(b.flags,source->flags,source->count);
  }
  b.count=b.capacity=source->count;
  status=exr_control_cancel(control,e);
  if(status==EXR_OK) status=exr_display_finish(&b,p->direction,p->first_direction,NULL,out,e);
  b.text.data=NULL;b.text.size=0;exr_display_builder_clear(&b);
  if(status==EXR_OK && exr_control_cancel(control,e)!=EXR_OK) { exr_display_view_free(*out);*out=NULL;status=EXR_CANCELLED; }
  return status;
}
int exr_plan_matches(const exr_display_view *v,const exr_glyph *g,size_t count,size_t first,size_t *scalars) {
  size_t i,at=first;const exr_bidi_scalar *s=exr_bidi_scalars(v->bidi,NULL);
  for(i=0;i<count;i++) {
    uint32_t cp=g[i].flags&EXR_GLYPH_RUBY_ITEM ? 0xfffc : g[i].codepoint;
    if(g[i].flags&EXR_GLYPH_DELETED) continue;
    if(at>=v->count || s[at].codepoint!=cp || v->sources[at]!=g[i].start ||
       !!(v->boundaries[at]&EXR_DISPLAY_GENERATED)!=!!(g[i].flags&EXR_GLYPH_GENERATED)) return 0;
    at++;
  }
  *scalars=at-first;return 1;
}
