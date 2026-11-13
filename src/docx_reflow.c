/* SPDX-License-Identifier: MIT */
#include "reflow_internal.h"
#include <stdio.h>
#ifndef EXR_NO_EDIT_MODEL

typedef struct { size_t refs,count;exr_line lines[]; } line_metrics;
typedef struct {
  exr_edit_block block;
  exr_edit_run *runs;
  char *text;
  size_t *refs; /* Immutable run/text payload shared by adjacent snapshots. */
  size_t size,start;
  uint64_t hash;
  line_metrics *metrics; /* Geometry only; glyph payloads remain in the pager LRU. */
} block_copy;
typedef struct { block_copy *blocks;size_t count,size; } snapshot;
typedef struct { size_t block,line; } cursor;
typedef struct { cursor start,end;size_t source_start,source_end;float remaining; } page_token;
typedef struct {
  exr_edit_doc *doc;
  exr_pager *pager;
  exr_font *font;
  exr_layout_config config;
  snapshot current,previous;
  page_token *pages;size_t count,capacity;
  exr_edit_reflow_stats stats;
} edit_layout;
typedef struct { exr_layout *layout;size_t block; } shape_cache;

static void snapshot_free(snapshot *s) {
  size_t i;for(i=0;i<s->count;i++) {
    line_metrics *m=s->blocks[i].metrics;if(m && !--m->refs) free(m);
    if(!s->blocks[i].refs || !--*s->blocks[i].refs) {
      free(s->blocks[i].runs);free(s->blocks[i].text);free(s->blocks[i].refs);
    }
  }
  free(s->blocks);memset(s,0,sizeof(*s));
}
static void hash_bytes(uint64_t *h,const void *bytes,size_t n) {
  const unsigned char *s=bytes;size_t i;for(i=0;i<n;i++) *h=(*h^s[i])*UINT64_C(1099511628211);
}
static uint64_t block_hash(const exr_edit_block *b) {
  uint64_t h=UINT64_C(14695981039346656037);size_t i;
#define H(v) hash_bytes(&h,&(v),sizeof(v))
  H(b->id);H(b->section_id);H(b->kind);H(b->run_count);
  H(b->props.present);H(b->props.alignment);H(b->props.indent_left);H(b->props.indent_right);
  H(b->props.indent_first_line);H(b->props.space_before);H(b->props.space_after);
  H(b->props.line);H(b->props.line_rule);H(b->props.keep_next);H(b->props.keep_lines);
  H(b->props.page_break_before);H(b->props.numbering_id);H(b->props.numbering_level);
  for(i=0;i<b->run_count;i++) {
    const exr_edit_run *r=&b->runs[i];
    H(r->id);H(r->kind);H(r->props.present);H(r->props.size_half_points);H(r->props.color_rgb);
    H(r->props.bold);H(r->props.italic);hash_bytes(&h,r->props.font,strlen(r->props.font));
    H(r->text_size);hash_bytes(&h,r->text,r->text_size);
  }
#undef H
  return h;
}
static exr_status snapshot_read(exr_edit_doc *doc,const snapshot *old,snapshot *s,exr_error *e) {
  size_t i,j;memset(s,0,sizeof(*s));s->count=exr_edit_block_count(doc);
  if(s->count>EXR_MAX_NODES) return exr_fail(e,EXR_LIMIT,"Too many editing blocks");
  s->blocks=calloc(s->count ? s->count : 1,sizeof(*s->blocks));
  if(!s->blocks) return exr_fail(e,EXR_MEMORY,"Editing snapshot allocation failed");
  for(i=0;i<s->count;i++) {
    const exr_edit_block *b=exr_edit_block_at(doc,i);block_copy *c=&s->blocks[i];size_t at=0;
    if(b->kind==EXR_EDIT_TABLE || b->opaque_size ||
       ((b->props.present&EXR_EDIT_NUMBERING) && b->props.numbering_id)) goto unsupported;
    if((b->props.present&EXR_EDIT_KEEP_NEXT) && b->props.keep_next) goto unsupported;
    c->block=*b;c->hash=block_hash(b);c->start=s->size;
    /* Verify every block rather than trusting a caller's dirty hint: edits,
       undo and replacement models can change several disjoint regions. */
    if(i<old->count && old->blocks[i].block.id==b->id && old->blocks[i].hash==c->hash) {
      size_t start=c->start;*c=old->blocks[i];c->start=start;c->metrics=NULL;
      ++*c->refs;
      if(c->size>=EXR_MAX_TEXT-s->size) goto limit;
      s->size+=c->size+1;continue;
    }
    c->refs=malloc(sizeof(*c->refs));if(!c->refs) goto memory;*c->refs=1;
    if(b->run_count>EXR_MAX_NODES/2-3) goto limit;
    c->runs=calloc(b->run_count ? b->run_count : 1,sizeof(*c->runs));
    if(!c->runs) goto memory;
    for(j=0;j<b->run_count;j++) {
      if(b->runs[j].kind!=EXR_EDIT_TEXT) goto unsupported;
      if(b->runs[j].text_size>EXR_MAX_TEXT-c->size) goto limit;
      c->size+=b->runs[j].text_size;
    }
    if(c->size>=EXR_MAX_TEXT-s->size) goto limit;
    s->size+=c->size+1;c->text=malloc(c->size+1);if(!c->text) goto memory;
    for(j=0;j<b->run_count;j++) {
      c->runs[j]=b->runs[j];c->runs[j].text=c->text+at;
      memcpy(c->text+at,b->runs[j].text,b->runs[j].text_size);at+=b->runs[j].text_size;
    }
    c->text[at]=0;c->block.runs=c->runs;c->block.opaque_xml=NULL;
  }
  return EXR_OK;
unsupported:snapshot_free(s);return exr_fail(e,EXR_UNSUPPORTED,"Reflow supports text paragraphs/breaks; opaque content, numbering and keep-next require a richer projection");
limit:snapshot_free(s);return exr_fail(e,EXR_LIMIT,"Editing snapshot exceeds text/node limits");
memory:snapshot_free(s);return exr_fail(e,EXR_MEMORY,"Editing snapshot allocation failed");
}
static size_t block_index(const snapshot *s,exr_edit_id id) {
  size_t i;for(i=0;i<s->count;i++) if(s->blocks[i].block.id==id) return i;return SIZE_MAX;
}
static exr_status shape(edit_layout *r,const snapshot *s,size_t index,shape_cache *cache,exr_error *e) {
  const block_copy *b=&s->blocks[index];exr_document d={0};exr_chapter chapter={0};
  exr_node *nodes;exr_style *styles;exr_font_rule *rules=NULL;size_t rules_count=0,i,at=0,n=3+2*b->block.run_count;
  exr_status status;exr_layout_config config=r->config;
  if(cache->layout && cache->block==index) return EXR_OK;
  exr_layout_free(cache->layout);cache->layout=NULL;
  nodes=calloc(n,sizeof(*nodes));if(!nodes) return exr_fail(e,EXR_MEMORY,"Paragraph node allocation failed");
  for(i=0;i<n;i++) { nodes[i].first_child=nodes[i].next_sibling=SIZE_MAX;nodes[i].end=b->size; }
  nodes[0].kind=EXR_NODE_DOCUMENT;nodes[0].parent=SIZE_MAX;nodes[0].first_child=1;
  nodes[1].kind=EXR_NODE_CHAPTER;nodes[1].first_child=2;nodes[1].parent=0;
  nodes[2].kind=EXR_NODE_PARAGRAPH;nodes[2].name="p";nodes[2].parent=1;
  if(b->block.run_count) nodes[2].first_child=3;
  for(i=0;i<b->block.run_count;i++) {
    size_t k=3+2*i;nodes[k].kind=EXR_NODE_ELEMENT;nodes[k].name="span";nodes[k].parent=2;
    nodes[k].first_child=k+1;nodes[k].start=at;
    if(i+1<b->block.run_count) nodes[k].next_sibling=k+2;
    nodes[k+1].kind=EXR_NODE_TEXT;nodes[k+1].parent=k;nodes[k+1].start=at;
    at+=b->runs[i].text_size;
    nodes[k].end=nodes[k+1].end=at;
  }
  chapter.root=1;chapter.in_spine=chapter.linear=1;chapter.resource=SIZE_MAX;
  d.text=b->text;d.size=b->size;d.nodes=nodes;d.node_count=n;d.chapters=&chapter;d.chapter_count=1;
  /* Native defaults plus model properties, preserving exact model UTF-8 bytes. */
  config.user_css=NULL;config.document_css=0;
  status=exr_compute_styles(&d,&config,&styles,&rules,&rules_count,e);free(rules);
  if(status==EXR_OK) {
    const exr_edit_para_props *p=&b->block.props;
    styles[2].indent=0;styles[2].indent_declared=1;
    for(i=0;i<4;i++) styles[2].margin[i].value=styles[2].padding[i].value=0;
    if(p->present&EXR_EDIT_ALIGN) styles[2].align=(int)p->alignment;
    if(p->present&EXR_EDIT_INDENT) {
      styles[2].margin[3].value=p->indent_left/15.0f;styles[2].margin[1].value=p->indent_right/15.0f;
      styles[2].indent=p->indent_first_line/15.0f;
    }
    if((p->present&EXR_EDIT_SPACING) && p->line) {
      styles[2].leading_relative=p->line_rule==EXR_EDIT_LINE_AUTO;
      styles[2].leading=p->line_rule==EXR_EDIT_LINE_AUTO ? p->line/240.0f : p->line/15.0f;
    }
    for(i=0;i<b->block.run_count;i++) {
      size_t k=3+2*i;const exr_edit_run_props *p_run=&b->runs[i].props;
      exr_style st=styles[2];st.display=EXR_CSS_INLINE;st.paragraph=0;st.indent=0;
      memset(st.margin,0,sizeof(st.margin));
      if(p_run->present&EXR_EDIT_SIZE) st.font_size=p_run->size_half_points*(2.0f/3.0f);
      if(p_run->present&EXR_EDIT_FONT) st.family=p_run->font;
      if(p_run->present&EXR_EDIT_COLOR) st.color=(p_run->color_rgb<<8)|255u;
      if(p_run->present&EXR_EDIT_BOLD) { st.flags&=~EXR_GLYPH_BOLD;if(p_run->bold) st.flags|=EXR_GLYPH_BOLD; }
      if(p_run->present&EXR_EDIT_ITALIC) { st.flags&=~EXR_GLYPH_ITALIC;if(p_run->italic) st.flags|=EXR_GLYPH_ITALIC; }
      st.family_owned=0;styles[k]=styles[k+1]=st;
    }
    /* Shape through the same paragraph flow used by tables/normal pages. */
    status=exr_edit_shape(&d,r->font,&config,styles,&cache->layout,e);
    exr_styles_free(styles,n);
  }
  if(status==EXR_OK && !b->metrics) {
    size_t count=cache->layout->line_count;
    line_metrics *m=malloc(sizeof(*m)+count*sizeof(*m->lines));
    if(!m) status=exr_fail(e,EXR_MEMORY,"Paragraph metrics allocation failed");
    else {
      m->refs=1;m->count=count;
      if(count) memcpy(m->lines,cache->layout->lines,count*sizeof(*m->lines));
      s->blocks[index].metrics=m;
    }
  }
  free(nodes);cache->block=index;return status;
}
static exr_status append_line(exr_layout *page,const exr_layout *part,size_t line_index,
  const block_copy *b,float y,float margin,exr_error *e) {
  exr_line line=part->lines[line_index];size_t i,glyph_start=page->glyph_count;
  float dy=y-line.y;
  if(!exr_grow((void **)&page->lines,&page->line_cap,page->line_count+1,sizeof(*page->lines)) ||
     !exr_grow((void **)&page->glyphs,&page->glyph_cap,glyph_start+line.glyph_count,sizeof(*page->glyphs)) ||
     !exr_grow((void **)&page->blocks,&page->block_cap,page->block_count+1,sizeof(*page->blocks)))
    return exr_fail(e,EXR_MEMORY,"Editing page allocation failed");
  for(i=0;i<line.glyph_count;i++) {
    exr_glyph g=part->glyphs[line.glyph_start+i];g.page=0;g.node=(size_t)b->block.id;
    g.start+=b->start;g.end+=b->start;g.cluster_start+=b->start;g.cluster_end+=b->start;
    g.x+=margin;g.baseline+=dy;g.clip_left+=margin;g.clip_right+=margin;
    page->glyphs[page->glyph_count++]=g;
  }
  line.start+=b->start;line.end+=b->start;line.glyph_start=glyph_start;
  line.x+=margin;line.y=y;line.page=0;
  if(page->block_count && page->blocks[page->block_count-1].node==(size_t)b->block.id) {
    exr_layout_block *v=&page->blocks[page->block_count-1];v->end=line.end;v->line_count++;
  } else {
    exr_layout_block v={0};v.node=(size_t)b->block.id;v.start=line.start;v.end=line.end;
    v.line_start=page->line_count;v.line_count=1;page->blocks[page->block_count++]=v;
  }
  page->lines[page->line_count++]=line;return EXR_OK;
}
static exr_status make_page(edit_layout *r,const snapshot *s,cursor from,shape_cache *cache,
  page_token *token,exr_layout **out,int paint,exr_error *e) {
  exr_layout *page=calloc(1,sizeof(*page));cursor c=from;
  float y=r->config.page.margin,bottom=r->config.page.height-r->config.page.margin;
  exr_status status=EXR_OK;int occupied=0;
  if(!page) return exr_fail(e,EXR_MEMORY,"Editing page allocation failed");
  page->options=r->config.page;page->font=r->font;exr_font_ref(r->font);
  token->start=from;token->source_start=from.block<s->count ? s->blocks[from.block].start : 0;
  token->source_end=token->source_start;
  while(c.block<s->count) {
    const block_copy *b=&s->blocks[c.block];const exr_edit_para_props *p=&b->block.props;
    float before=(p->present&EXR_EDIT_SPACING) ? p->space_before/15.0f : 0;
    float after=(p->present&EXR_EDIT_SPACING) ? p->space_after/15.0f : r->config.page.paragraph_spacing;
    size_t lines;
    status=exr_control_poll(&r->config.control,EXR_STAGE_LAYOUT,c.block,s->count,e);if(status!=EXR_OK) break;
    if(b->block.kind==EXR_EDIT_PAGE_BREAK) {
      c.block++;c.line=0;
      if(occupied) break;
      continue;
    }
    if(!c.line && occupied && (p->present&EXR_EDIT_PAGE_BEFORE) && p->page_break_before) break;
    if(!b->metrics) { status=shape(r,s,c.block,cache,e);if(status!=EXR_OK) break; }
    lines=b->metrics->count;
    if(!c.line && occupied && (p->present&EXR_EDIT_KEEP_LINES) && p->keep_lines && lines) {
      float height=0;size_t j;for(j=0;j<lines;j++) height+=b->metrics->lines[j].height;
      if(height<=bottom-r->config.page.margin && y+before+height>bottom+.001f) break;
    }
    if(!lines) {
      float height=r->config.page.font_size*r->config.page.line_height;
      if(occupied && y+before+height>bottom+.001f) break;
      y+=before+height+after;occupied=1;token->source_end=b->start+b->size;c.block++;c.line=0;continue;
    }
    if(c.line>=lines) { status=exr_fail(e,EXR_FORMAT,"Invalid editing page continuation");break; }
    while(c.line<lines) {
      const exr_line *line=&b->metrics->lines[c.line];float gap=c.line ? 0 : before;
      if(occupied && y+gap+line->height>bottom+.001f) goto sealed;
      if(!occupied) token->source_start=b->start+line->start;
      y+=gap;
      if(paint) {
        status=shape(r,s,c.block,cache,e);
        if(status==EXR_OK) status=append_line(page,cache->layout,c.line,b,y,r->config.page.margin,e);
        if(status!=EXR_OK) goto sealed;
      }
      y+=line->height;occupied=1;token->source_end=b->start+line->end;c.line++;
    }
    y+=after;c.block++;c.line=0;
  }
sealed:
  if(status==EXR_OK) {
    page->pages=calloc(1,sizeof(*page->pages));
    if(!page->pages) status=exr_fail(e,EXR_MEMORY,"Editing page header allocation failed");
    else {
      page->page_count=page->page_cap=1;
      page->pages[0]=(exr_page){token->source_start,token->source_end,0,page->line_count,0,0};
      token->end=c;token->remaining=fmaxf(0,bottom-y);*out=page;return EXR_OK;
    }
  }
  exr_layout_free(page);return status;
}
static exr_status page_get(void *state,size_t index,exr_layout **out,exr_error *e) {
  edit_layout *r=state;shape_cache cache={0};page_token token;exr_status status;
  r->config.control=exr_pager_edit_config(r->pager)->control;
  if(index>=r->count) return exr_fail(e,EXR_ARGUMENT,"Page index is outside the editing document");
  status=make_page(r,&r->current,r->pages[index].start,&cache,&token,out,1,e);
  exr_layout_free(cache.layout);return status;
}
static int token_add(page_token **pages,size_t *count,size_t *cap,page_token value) {
  if(*count>=EXR_MAX_ITEMS || !exr_grow((void **)pages,cap,*count+1,sizeof(**pages))) return 0;
  (*pages)[(*count)++]=value;return 1;
}
static void release_layout(void *state) {
  edit_layout *r=state;if(!r) return;
  snapshot_free(&r->current);snapshot_free(&r->previous);free(r->pages);
  exr_font_free(r->font);free(r);
}
static size_t page_for_source(const edit_layout *r,size_t offset) {
  size_t lo=0,hi=r->count;
  while(lo<hi) { size_t mid=lo+(hi-lo)/2;if(r->pages[mid].source_start<=offset) lo=mid+1;else hi=mid; }
  return lo ? lo-1 : 0;
}
static int equal_block(const block_copy *a,const block_copy *b) { return a->block.id==b->block.id && a->hash==b->hash; }
static int equal_line(const exr_layout *a,const exr_layout *b,size_t at) {
  const exr_line *x=&a->lines[at],*y=&b->lines[at];size_t i;
  if(x->start!=y->start || x->end!=y->end || x->glyph_count!=y->glyph_count ||
     x->x!=y->x || x->y!=y->y || x->width!=y->width || x->height!=y->height) return 0;
  for(i=0;i<x->glyph_count;i++) {
    const exr_glyph *g=&a->glyphs[x->glyph_start+i],*h=&b->glyphs[y->glyph_start+i];
    if(g->start!=h->start || g->end!=h->end || g->codepoint!=h->codepoint || g->glyph!=h->glyph ||
       g->x!=h->x || g->baseline!=h->baseline || g->advance!=h->advance || g->flags!=h->flags ||
       g->size!=h->size || g->color!=h->color || g->font_index!=h->font_index) return 0;
  }
  return 1;
}
exr_status exr_edit_layout_after(exr_edit_doc *doc,exr_pager *pager,exr_edit_id hint,
  size_t *repaginated,exr_error *e) {
  edit_layout *r=exr_pager_edit_state(pager);snapshot next={0};shape_cache cache={0};
  page_token *pages=NULL;size_t count=0,cap=0,first=0,old_end,new_end,dirty_page=0,old_stop,new_stop;
  size_t i,generated=0,old_base=0,new_base=0;cursor c={0};exr_status status;exr_edit_reflow_stats stats={0};
  (void)hint;
  if(repaginated) *repaginated=0;
  if(!r || !doc || !repaginated) return exr_fail(e,EXR_ARGUMENT,"Missing editing pager/model/output");
  exr_pager_edit_busy(pager,1);
  r->config.control=exr_pager_edit_config(pager)->control;
  status=snapshot_read(doc,&r->current,&next,e);if(status!=EXR_OK) { exr_pager_edit_busy(pager,0);return status; }
  /* ponytail: O(blocks + text bytes) snapshot comparison, no change hooks in X1.
     Add a model mutation journal if profiling larger editable files warrants it. */
  while(first<r->current.count && first<next.count && equal_block(&r->current.blocks[first],&next.blocks[first])) first++;
  if(first==r->current.count && first==next.count && r->count) {
    snapshot_free(&next);r->stats.pages_repaginated=r->stats.cache_invalidated=0;
    r->stats.pages_reused=r->count;r->stats.dirty=(exr_edit_dirty_range){0};exr_pager_edit_busy(pager,0);return exr_fail(e,EXR_OK,"");
  }
  old_end=r->current.count;new_end=next.count;
  while(old_end>first && new_end>first && equal_block(&r->current.blocks[old_end-1],&next.blocks[new_end-1])) { old_end--;new_end--; }
  for(i=0;i<first;i++) {
    next.blocks[i].metrics=r->current.blocks[i].metrics;
    if(next.blocks[i].metrics) next.blocks[i].metrics->refs++;
  }
  for(i=new_end;i<next.count;i++) {
    next.blocks[i].metrics=r->current.blocks[old_end+(i-new_end)].metrics;
    if(next.blocks[i].metrics) next.blocks[i].metrics->refs++;
  }
  if(r->count) {
    size_t offset=first<r->current.count ? r->current.blocks[first].start : r->current.size;
    /* Insertion can fill the preceding page's unused space. */
    if(old_end==first && first) offset=r->current.blocks[first-1].start+r->current.blocks[first-1].size;
    dirty_page=page_for_source(r,offset);
    /* Shape the complete changed paragraph (bidi/ligatures), but retain pages
       containing only identical prefix lines, even for a book-sized paragraph. */
    if(first<r->current.count) {
      size_t changed=r->current.blocks[first].start;
      if(old_end==first+1 && new_end==first+1 && r->current.blocks[first].block.id==next.blocks[first].block.id &&
         page_for_source(r,changed+r->current.blocks[first].size)>dirty_page) {
        shape_cache old_shape={0};size_t line=0;
        status=shape(r,&r->current,first,&old_shape,e);
        if(status==EXR_OK) status=shape(r,&next,first,&cache,e);
        if(status==EXR_OK) {
          while(line<old_shape.layout->line_count && line<cache.layout->line_count && equal_line(old_shape.layout,cache.layout,line)) line++;
          if(line<old_shape.layout->line_count) changed+=old_shape.layout->lines[line].start;
          else changed+=r->current.blocks[first].size;
          /* Paragraph spacing/page-break/keep properties affect its start. */
          if(memcmp(&r->current.blocks[first].block.props,&next.blocks[first].block.props,sizeof(exr_edit_para_props)))
            changed=r->current.blocks[first].start;
        }
        exr_layout_free(old_shape.layout);if(status!=EXR_OK) goto failed;
      }
      if(old_end!=first) dirty_page=page_for_source(r,changed);
    }
    if(old_end==first && first && first<next.count) {
      size_t following=first<r->current.count ? page_for_source(r,r->current.blocks[first].start) : r->count;
      /* A full preceding page cannot accept the insertion: keep its payload
         cached, and at EOF paginate exactly the newly appended pages. */
      if(following>dirty_page) {
        const block_copy *b=&next.blocks[first];float needed;
        status=shape(r,&next,first,&cache,e);if(status!=EXR_OK) goto failed;
        needed=b->metrics->count ? b->metrics->lines[0].height : r->config.page.font_size*r->config.page.line_height;
        if(b->block.props.present&EXR_EDIT_SPACING) needed+=b->block.props.space_before/15.0f;
        if(r->pages[dirty_page].remaining+.001f<needed ||
           ((b->block.props.present&EXR_EDIT_PAGE_BEFORE) && b->block.props.page_break_before)) dirty_page=following;
      }
    }
    c=dirty_page<r->count ? r->pages[dirty_page].start : (cursor){first,0};
    if(c.block>=first && !(c.block==first && first<next.count && first<r->current.count &&
       r->current.blocks[first].block.id==next.blocks[first].block.id)) { c.block=first;c.line=0; }
    for(i=0;i<dirty_page;i++) if(!token_add(&pages,&count,&cap,r->pages[i])) goto memory;
  }
  stats.dirty.old_first=stats.dirty.new_first=first;stats.dirty.old_end=old_end;stats.dirty.new_end=new_end;
  stats.dirty.first_page=dirty_page;
  stats.dirty.end_page=r->count ? page_for_source(r,old_end ? r->current.blocks[old_end-1].start+r->current.blocks[old_end-1].size : 0)+1 : 0;
  if(stats.dirty.end_page<=dirty_page) stats.dirty.end_page=dirty_page<r->count ? dirty_page+1 : r->count;
  if(first<next.count) stats.dirty.first_block_id=next.blocks[first].block.id;
  else if(first<r->current.count) stats.dirty.first_block_id=r->current.blocks[first].block.id;
  if(new_end>first) stats.dirty.last_block_id=next.blocks[new_end-1].block.id;
  else if(old_end>first) stats.dirty.last_block_id=r->current.blocks[old_end-1].block.id;
  old_stop=r->count;
  while(c.block<next.count || (!count && !generated)) {
    page_token token;exr_layout *page=NULL;
    /* Converge only inside the verified unchanged suffix, matching both block
       identity and continuation line. Matching just block ID breaks split paras. */
    if(generated && c.block>=new_end && c.block<next.count) {
      size_t old_block=old_end+(c.block-new_end);
      for(i=dirty_page;i<r->count;i++) if(r->pages[i].start.block==old_block && r->pages[i].start.line==c.line) { old_stop=i;goto converged; }
    }
    status=make_page(r,&next,c,&cache,&token,&page,0,e);if(status!=EXR_OK) goto failed;
    exr_layout_free(page);
    if(token.end.block==c.block && token.end.line==c.line && c.block<next.count) { status=exr_fail(e,EXR_FORMAT,"Editing paginator made no progress");goto failed; }
    if(!token_add(&pages,&count,&cap,token)) goto memory;
    generated++;c=token.end;
    if(c.block>=next.count) break;
  }
converged:
  new_stop=count;
  if(old_stop<r->count) {
    old_base=r->current.blocks[old_end].start;new_base=next.blocks[new_end].start;
    for(i=old_stop;i<r->count;i++) {
      page_token token=r->pages[i];
      token.start.block=new_end+(token.start.block-old_end);
      token.end.block=new_end+(token.end.block-old_end);
      token.source_start=new_base+(token.source_start-old_base);token.source_end=new_base+(token.source_end-old_base);
      if(!token_add(&pages,&count,&cap,token)) goto memory;
    }
  }
  status=exr_control_cancel(&r->config.control,e);if(status!=EXR_OK) goto failed;
  stats.cache_invalidated=exr_pager_edit_commit(pager,dirty_page,old_stop,new_stop,old_base,new_base,generated);
  stats.revision=r->stats.revision+1;stats.page_count=count;stats.pages_repaginated=generated;
  stats.pages_reused=dirty_page+r->count-old_stop;
  snapshot_free(&r->previous);r->previous=r->current;r->current=next;r->doc=doc;
  free(r->pages);r->pages=pages;r->count=count;r->capacity=cap;r->stats=stats;
  exr_layout_free(cache.layout);*repaginated=generated;exr_pager_edit_busy(pager,0);return exr_fail(e,EXR_OK,"");
memory:status=exr_fail(e,EXR_MEMORY,"Editing page directory allocation failed");
failed:free(pages);snapshot_free(&next);exr_layout_free(cache.layout);exr_pager_edit_busy(pager,0);return status;
}
exr_status exr_edit_pager_create(exr_edit_doc *doc,exr_font *font,const exr_layout_config *config,
  exr_pager **out,exr_error *e) {
  edit_layout *r;exr_status status;size_t generated;exr_layout_config defaults=exr_layout_config_defaults();
  if(!out) return exr_fail(e,EXR_ARGUMENT,"Missing editing pager output");
  *out=NULL;if(!doc || !font) return exr_fail(e,EXR_ARGUMENT,"Missing editing model/font");
  if(!config) config=&defaults;
  if(config->user_css && config->user_css[0]) return exr_fail(e,EXR_UNSUPPORTED,"Editing projection uses model properties, not user CSS");
  status=exr_layout_validate(config,e);if(status!=EXR_OK) return status;
  r=calloc(1,sizeof(*r));if(!r) return exr_fail(e,EXR_MEMORY,"Editing layout allocation failed");
  r->doc=doc;r->font=font;exr_font_ref(font);r->config=*config;r->config.user_css=NULL;
  status=exr_pager_edit_create(font,config,r,page_get,release_layout,out,e);
  if(status!=EXR_OK) { release_layout(r);return status; }
  r->pager=*out;
  status=exr_edit_layout_after(doc,*out,0,&generated,e);
  if(status!=EXR_OK) { exr_pager_free(*out);*out=NULL; }
  return status;
}
exr_edit_reflow_stats exr_edit_reflow_statistics(const exr_pager *pager) {
  const edit_layout *r=exr_pager_edit_state(pager);return r ? r->stats : (exr_edit_reflow_stats){0};
}
static exr_status anchor_at(const edit_layout *r,size_t index,size_t offset,exr_edit_view_anchor *out,exr_error *e) {
  const block_copy *b=&r->current.blocks[index];size_t page;
  if(offset>b->size || (offset<b->size && ((unsigned char)b->text[offset]&0xc0)==0x80))
    return exr_fail(e,EXR_ARGUMENT,"Anchor must use a block UTF-8 byte boundary");
  page=page_for_source(r,b->start+offset);
  *out=(exr_edit_view_anchor){page,offset,b->start+offset-r->pages[page].source_start,r->stats.revision,b->block.id};
  return exr_fail(e,EXR_OK,"");
}
exr_status exr_edit_anchor_capture(const exr_pager *pager,size_t page,exr_edit_id id,size_t offset,
  exr_edit_view_anchor *out,exr_error *e) {
  const edit_layout *r=exr_pager_edit_state(pager);size_t index;exr_status status;
  if(out) memset(out,0,sizeof(*out));
  if(!r || !out || page>=r->count || (index=block_index(&r->current,id))==SIZE_MAX)
    return exr_fail(e,EXR_ARGUMENT,"Invalid editing anchor");
  status=anchor_at(r,index,offset,out,e);
  if(status==EXR_OK && out->page_index!=page) { memset(out,0,sizeof(*out));return exr_fail(e,EXR_ARGUMENT,"Anchor text is not on the supplied page"); }
  return status;
}
exr_status exr_edit_anchor_restore(const exr_pager *pager,const exr_edit_view_anchor *before,
  exr_edit_view_anchor *out,exr_error *e) {
  const edit_layout *r=exr_pager_edit_state(pager);const snapshot *old;size_t index,old_index,offset,prefix=0,suffix=0;
  exr_edit_view_anchor input;
  if(!before || !out) return exr_fail(e,EXR_ARGUMENT,"Missing editing anchor input/output");
  input=*before;before=&input;memset(out,0,sizeof(*out));
  if(!r || !before->revision || before->revision>r->stats.revision || r->stats.revision-before->revision>1)
    return exr_fail(e,EXR_ARGUMENT,"Editing anchor revision has expired");
  old=before->revision==r->stats.revision ? &r->current : &r->previous;
  old_index=block_index(old,before->block_id);index=block_index(&r->current,before->block_id);offset=before->byte_offset;
  if(old_index==SIZE_MAX || offset>old->blocks[old_index].size ||
     (offset<old->blocks[old_index].size && ((unsigned char)old->blocks[old_index].text[offset]&0xc0)==0x80))
    return exr_fail(e,EXR_ARGUMENT,"Invalid saved editing anchor");
  if(index==SIZE_MAX) {
    size_t j;
    for(j=old_index+1;j<old->count;j++) if((index=block_index(&r->current,old->blocks[j].block.id))!=SIZE_MAX) return anchor_at(r,index,0,out,e);
    for(j=old_index;j>0;j--) if((index=block_index(&r->current,old->blocks[j-1].block.id))!=SIZE_MAX) return anchor_at(r,index,r->current.blocks[index].size,out,e);
    if(r->current.count) return anchor_at(r,0,0,out,e);
    return exr_fail(e,EXR_ARGUMENT,"The editing document contains no text anchor");
  }
  if(before->revision!=r->stats.revision) {
    const block_copy *a=&old->blocks[old_index],*b=&r->current.blocks[index];
    while(prefix<a->size && prefix<b->size && a->text[prefix]==b->text[prefix]) prefix++;
    while(suffix<a->size-prefix && suffix<b->size-prefix && a->text[a->size-1-suffix]==b->text[b->size-1-suffix]) suffix++;
    /* A split retains the left ID. Locate its surviving right-hand text by
       suffix bytes in the following newly inserted paragraph. */
    if(offset>=b->size && index+1<r->current.count && b->size<a->size && prefix==b->size) {
      const block_copy *right=&r->current.blocks[index+1];size_t tail=a->size-b->size;
      if(right->size>=tail && !memcmp(right->text,a->text+b->size,tail)) return anchor_at(r,index+1,offset-b->size,out,e);
    }
    if(offset>=a->size-suffix) offset=b->size-(a->size-offset);
    else if(offset>=prefix) offset=b->size-suffix;
    while(offset<b->size && ((unsigned char)b->text[offset]&0xc0)==0x80) offset++;
  }
  return anchor_at(r,index,offset,out,e);
}
#else
exr_status exr_edit_pager_create(exr_edit_doc *doc,exr_font *font,const exr_layout_config *config,
  exr_pager **out,exr_error *e) {
  (void)doc;(void)font;(void)config;if(out) *out=NULL;
  return exr_fail(e,EXR_UNSUPPORTED,"Build with the X1 editing model to enable reflow");
}
exr_status exr_edit_layout_after(exr_edit_doc *doc,exr_pager *pager,exr_edit_id hint,size_t *count,exr_error *e) {
  (void)doc;(void)pager;(void)hint;if(count) *count=0;
  return exr_fail(e,EXR_UNSUPPORTED,"Build with the X1 editing model to enable reflow");
}
exr_edit_reflow_stats exr_edit_reflow_statistics(const exr_pager *pager) {
  (void)pager;return (exr_edit_reflow_stats){0};
}
exr_status exr_edit_anchor_capture(const exr_pager *pager,size_t page,exr_edit_id id,size_t offset,
  exr_edit_view_anchor *out,exr_error *e) {
  (void)pager;(void)page;(void)id;(void)offset;if(out) memset(out,0,sizeof(*out));
  return exr_fail(e,EXR_UNSUPPORTED,"Build with the X1 editing model to enable reflow");
}
exr_status exr_edit_anchor_restore(const exr_pager *pager,const exr_edit_view_anchor *before,
  exr_edit_view_anchor *out,exr_error *e) {
  (void)pager;(void)before;if(out) memset(out,0,sizeof(*out));
  return exr_fail(e,EXR_UNSUPPORTED,"Build with the X1 editing model to enable reflow");
}
#endif
