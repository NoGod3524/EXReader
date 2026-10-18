/* SPDX-License-Identifier: GPL-3.0-only */
#include "ruby_internal.h"
#include "bidi_internal.h"
#include "opentype_internal.h"
#define RUBY_PARTS 256u
#define RUBY_ROWS 16u
#define RUBY_SCALARS 8192u
typedef struct { size_t first,stop,start,end; } ruby_base;
typedef struct { size_t node,column,span,row; } ruby_annotation;
typedef struct {
  ruby_base bases[RUBY_PARTS]; ruby_annotation annotations[RUBY_PARTS];
  size_t base_count,annotation_count,rows;
  int complex;
} ruby_model;
typedef struct { exr_layout *layout; float width,ascent,descent,height; } ruby_text;
static const char *tag(const flow *f,size_t node) { return exr_html_tag(f->doc,&f->doc->nodes[node]); }
int exr_ruby_node(const exr_document *doc,size_t node) {
  return !strcmp(exr_html_tag(doc,&doc->nodes[node]),"ruby");
}
static exr_status failure(flow *f,exr_status status,const char *message) { return exr_fail(f->error,status,"%s",message); }
static int present(const flow *f,size_t node) {
  return f->styles[node].display!=EXR_CSS_NONE && f->doc->nodes[node].start!=SIZE_MAX;
}
static exr_status base_add(flow *f,ruby_model *m,size_t first,size_t stop) {
  ruby_base *b;
  if(first==SIZE_MAX) return EXR_OK;
  if(m->base_count==RUBY_PARTS) return failure(f,EXR_LIMIT,"Ruby exceeds 256 base segments");
  b=&m->bases[m->base_count++]; b->first=first; b->stop=stop;
  b->start=f->doc->nodes[first].start; b->end=b->start; return EXR_OK;
}
static size_t annotation_span(const exr_node *n) {
  const char *value=exr_node_attribute(n,"rbspan"); char *end; unsigned long span;
  if(!value) return 1;
  span=strtoul(value,&end,10); return end==value || *end || !span ? 1 : span>RUBY_PARTS ? RUBY_PARTS : (size_t)span;
}
static exr_status annotation_add(flow *f,ruby_model *m,size_t node,size_t column,size_t span,size_t row) {
  ruby_annotation *a;
  if(column>=m->base_count) return EXR_OK;
  row=2*row+(unsigned)f->styles[node].ruby_position;
  if(row>=RUBY_ROWS || m->annotation_count==RUBY_PARTS)
    return failure(f,EXR_LIMIT,"Ruby exceeds 8 annotation levels or 256 annotation segments");
  a=&m->annotations[m->annotation_count++];
  *a=(ruby_annotation){node,column,span>m->base_count-column ? m->base_count-column : span,row};
  if(row>=m->rows) m->rows=row+1;
  return EXR_OK;
}
static exr_status parse(flow *f,size_t root,ruby_model *m) {
  size_t child,first=SIZE_MAX,column=0,rtc_row=0,visited=0,i;
  int has_rb=0,has_rt=0;
  exr_status status;
  for(child=f->doc->nodes[root].first_child;child!=SIZE_MAX;child=f->doc->nodes[child].next_sibling) {
    if(++visited>RUBY_SCALARS) return failure(f,EXR_LIMIT,"Ruby direct-child work limit exceeded");
    has_rb|=!strcmp(tag(f,child),"rb");
    if(!strcmp(tag(f,child),"rtc")) m->complex=1;
  }
  m->complex|=has_rb;
  for(child=f->doc->nodes[root].first_child;child!=SIZE_MAX;child=f->doc->nodes[child].next_sibling) {
    const char *name=tag(f,child);
    if(!present(f,child) || !strcmp(name,"rp")) continue;
    if(!strcmp(name,"rb")) {
      status=base_add(f,m,first,child); if(status!=EXR_OK) return status; first=SIZE_MAX;
      status=base_add(f,m,child,f->doc->nodes[child].next_sibling); if(status!=EXR_OK) return status;
    } else if(!strcmp(name,"rt") || !strcmp(name,"rtc")) {
      status=base_add(f,m,first,child); if(status!=EXR_OK) return status; first=SIZE_MAX;
      if(!strcmp(name,"rt")) {
        size_t target=has_rb ? column++ : m->base_count ? m->base_count-1 : SIZE_MAX;
        status=annotation_add(f,m,child,target,annotation_span(&f->doc->nodes[child]),0);
        if(status!=EXR_OK) return status;
        has_rt=1;
      } else {
        size_t rt,at=0,row=rtc_row+++(size_t)has_rt; int found=0;
        for(rt=f->doc->nodes[child].first_child;rt!=SIZE_MAX;rt=f->doc->nodes[rt].next_sibling)
          if(present(f,rt) && !strcmp(tag(f,rt),"rt")) {
            size_t span=annotation_span(&f->doc->nodes[rt]);
            status=annotation_add(f,m,rt,at,span,row); if(status!=EXR_OK) return status;
            at+=span; found=1;
          }
        if(!found) { status=annotation_add(f,m,child,0,m->base_count,row); if(status!=EXR_OK) return status; }
      }
    } else if(first==SIZE_MAX) first=child;
  }
  status=base_add(f,m,first,SIZE_MAX); if(status!=EXR_OK) return status;
  for(i=0;i<m->base_count;i++)
    m->bases[i].end=i+1<m->base_count ? m->bases[i+1].start : f->doc->nodes[root].end;
  return EXR_OK;
}
static exr_status collect(flow *f,size_t node,int base,exr_layout *l,unsigned depth) {
  const exr_node *n=&f->doc->nodes[node]; const exr_style *s=&f->styles[node];
  const char *name=tag(f,node); size_t child,at;
  if(!present(f,node) || !strcmp(name,"rp") || (base && (!strcmp(name,"rt") || !strcmp(name,"rtc")))) return EXR_OK;
  if(depth>=256 || exr_ruby_node(f->doc,node)) return failure(f,EXR_LIMIT,"Nested ruby or ruby tree depth exceeds the supported group model");
  if(n->kind==EXR_NODE_TEXT) {
    for(at=n->start;at<n->end;) {
      size_t start=at; uint32_t cp; exr_glyph *g;
      if(l->glyph_count==RUBY_SCALARS) return failure(f,EXR_LIMIT,"Ruby text exceeds 8192 scalars");
      if(!exr_next(f->doc->text,n->end,&at,&cp)) return failure(f,EXR_ENCODING,"Invalid ruby UTF-8");
      if(!exr_grow((void **)&l->glyphs,&l->glyph_cap,l->glyph_count+1,sizeof(*l->glyphs))) return failure(f,EXR_MEMORY,"Ruby text allocation failed");
      g=&l->glyphs[l->glyph_count++]; *g=(exr_glyph){0};
      g->start=start; g->end=at; g->node=node; g->codepoint=cp; g->size=s->font_size; g->color=s->color;
      g->flags=s->flags|(exr_text_hidden(cp) ? EXR_GLYPH_HIDDEN : 0);
      g->line_height=s->leading_relative ? s->leading*s->font_size : s->leading;
    }
  } else for(child=n->first_child;child!=SIZE_MAX;child=f->doc->nodes[child].next_sibling) {
    exr_status status=collect(f,child,base,l,depth+1); if(status!=EXR_OK) return status;
  }
  return EXR_OK;
}
static float kern(flow *f,const exr_glyph *left,const exr_glyph *g) {
  if(!left || ((left->flags|g->flags)&(EXR_GLYPH_HIDDEN|EXR_GLYPH_SHAPED)) || left->font_index!=g->font_index ||
     left->size!=g->size || (left->flags&3)!=(g->flags&3) || ((g->flags&EXR_GLYPH_VERTICAL) && !(g->flags&EXR_GLYPH_SIDEWAYS))) return 0;
  return exr_kern(&f->font->faces[g->font_index],left->glyph,g->glyph);
}
static exr_status shape(flow *f,size_t first,size_t stop,int base,ruby_text *out) {
  exr_layout *l=calloc(1,sizeof(*l)); exr_inline_bidi bidi={0}; flow child=*f;
  child.display_bidi=NULL;child.auto_bases=NULL;child.auto_probe=NULL;child.plan_probe=NULL;child.plan_resolve=NULL;child.plan_cursor=NULL;
  exr_buffer text={0}; unsigned char *boundaries=NULL; size_t *bytes=NULL,node,i,j,at=0;
  exr_status status=EXR_OK; unsigned orientation=0; exr_line *line;
  if(!l) return failure(f,EXR_MEMORY,"Ruby shaping allocation failed");
  out->layout=l;
  for(node=first;node!=stop && node!=SIZE_MAX;node=f->doc->nodes[node].next_sibling) {
    status=collect(f,node,base,l,0); if(status!=EXR_OK) goto done;
  }
  if(!l->glyph_count) goto done;
  if(l->glyph_count>64000000u-f->assets->shape_work) { status=failure(f,EXR_LIMIT,"Ruby shaping work limit exceeded"); goto done; }
  f->assets->shape_work+=l->glyph_count;
  bytes=malloc(l->glyph_count*sizeof(*bytes)); bidi.offsets=malloc(l->glyph_count*sizeof(*bidi.offsets));
  if(!bytes || !bidi.offsets) { status=failure(f,EXR_MEMORY,"Ruby scalar map allocation failed"); goto done; }
  for(i=0;i<l->glyph_count;i++) {
    bytes[i]=text.size; bidi.offsets[i]=l->glyphs[i].start;
    if(!exr_codepoint(&text,l->glyphs[i].codepoint)) { status=failure(f,EXR_MEMORY,"Ruby text buffer allocation failed"); goto done; }
  }
  status=exr_text_analyze(text.data,text.size,&boundaries,f->error); if(status!=EXR_OK) goto done;
  status=exr_bidi_analyze(text.data,text.size,f->styles[first].direction,&bidi.analysis,f->error); if(status!=EXR_OK) goto done;
  bidi.count=l->glyph_count; child.layout=l; child.bidi=&bidi;
  for(i=0;i<l->glyph_count;i++) {
    exr_glyph *g=&l->glyphs[i];
    g->boundaries=boundaries[bytes[i]]; g->bidi_level=exr_inline_level(&bidi,g->start);
    if(g->bidi_level==UINT_MAX) g->flags|=EXR_GLYPH_HIDDEN;
    if(f->writing_mode!=EXR_WRITING_HORIZONTAL_TB) {
      if(g->boundaries&EXR_BOUNDARY_GRAPHEME) orientation=exr_vertical_flags(g->codepoint,f->styles[g->node].orientation);
      g->flags|=orientation;
    }
  }
  for(i=0;i<l->glyph_count;i=j) {
    for(j=i+1;j<l->glyph_count && !(l->glyphs[j].boundaries&EXR_BOUNDARY_GRAPHEME);j++) {}
    status=exr_flow_cluster(&child,i,j); if(status!=EXR_OK) goto done;
  }
  status=exr_inline_shape(&child,0,0,0); if(status!=EXR_OK) goto done;
  status=exr_inline_reorder(&child,l->glyphs,l->glyph_count); if(status!=EXR_OK) goto done;
  l->lines=calloc(1,sizeof(*l->lines)); if(!l->lines) { status=failure(f,EXR_MEMORY,"Ruby line allocation failed"); goto done; }
  l->line_count=l->line_cap=1; line=l->lines; line->start=SIZE_MAX; line->glyph_count=l->glyph_count;
  for(i=0;i<l->glyph_count;i++) {
    exr_glyph *g=&l->glyphs[i]; exr_face *face=&f->font->faces[g->font_index];
    if(exr_font_size(face,g->size)) { status=failure(f,EXR_FONT,"Cannot size ruby font"); goto done; }
    out->ascent=fmaxf(out->ascent,exr_font_ascent(face));
    out->descent=fmaxf(out->descent,exr_font_descent(face));
    out->height=fmaxf(out->height,g->line_height);
    out->width+=kern(f,i ? &l->glyphs[i-1] : NULL,g); g->x=out->width; out->width+=g->advance;
    if(g->start<line->start) line->start=g->start;
    if(g->end>line->end) line->end=g->end;
    if(!(i&255) && exr_control_cancel(&f->config->control,f->error)!=EXR_OK) { status=EXR_CANCELLED; goto done; }
  }
  out->height=fmaxf(out->height,out->ascent+out->descent);
  line->width=out->width; line->height=out->height;
  for(i=0;i<l->glyph_count;i++) {
    l->glyphs[i].baseline=out->ascent+(out->height-out->ascent-out->descent)/2;
    l->glyphs[i].clip_right=out->width;
  }
done:
  (void)at;
  free(text.data); free(bytes); free(boundaries); exr_inline_clear(&bidi);
  return status;
}
static exr_status place(flow *f,exr_layout *out,ruby_text *text,float x,float y,float width,int align) {
  exr_layout *from=text->layout; size_t i,clusters=0,index=0,offset=out->glyph_count;
  float extra=fmaxf(0,width-text->width),start=align==1 ? 0 : extra/2,gap=0;
  if(!from->line_count) return EXR_OK;
  for(i=0;i<from->glyph_count;i++) if(!i || from->glyphs[i].cluster_start!=from->glyphs[i-1].cluster_start) clusters++;
  if(align==2 && clusters>1) { gap=extra/(float)(clusters-1); start=0; }
  if(align==3 && clusters) { gap=extra/(float)clusters; start=gap/2; }
  if(from->glyph_count>EXR_MAX_ITEMS-offset ||
     !exr_grow((void **)&out->glyphs,&out->glyph_cap,offset+from->glyph_count,sizeof(*out->glyphs)) ||
     !exr_grow((void **)&out->lines,&out->line_cap,out->line_count+1,sizeof(*out->lines)))
    return failure(f,EXR_LIMIT,"Ruby output allocation limit exceeded");
  out->lines[out->line_count]=from->lines[0]; out->lines[out->line_count].glyph_start=offset;
  out->lines[out->line_count].x=x+start; out->lines[out->line_count].y=y;
  if(gap) out->lines[out->line_count].width=width-start;
  out->line_count++;
  for(i=0;i<from->glyph_count;i++) {
    exr_glyph g=from->glyphs[i];
    if(i && g.cluster_start!=from->glyphs[i-1].cluster_start) index++;
    g.x+=x+start+gap*(float)index; g.baseline+=y; g.clip_left=x; g.clip_right=x+width;
    out->glyphs[out->glyph_count++]=g;
  }
  return EXR_OK;
}
static exr_status prepare(flow *f,size_t root,uint32_t selected,ruby_model *m,exr_layout **out,float *baseline) {
  ruby_text *texts=calloc(m->base_count+m->annotation_count,sizeof(*texts));
  exr_layout *result=calloc(1,sizeof(*result));
  float columns[RUBY_PARTS]={0},row_height[RUBY_ROWS]={0},row_ascent[RUBY_ROWS]={0},row_descent[RUBY_ROWS]={0};
  float row_y[RUBY_ROWS]={0},base_ascent=0,base_descent=0,base_height=0,before=0,after=0,gap=fmaxf(1,f->styles[root].font_size*.1f);
  size_t i,j,scalars=0,first=selected==UINT32_MAX ? 0 : selected,last=selected==UINT32_MAX ? m->base_count : selected+1;
  exr_status status=EXR_OK;
  *out=NULL;
  if(!texts || !result) { status=failure(f,EXR_MEMORY,"Ruby group allocation failed"); goto done; }
  for(i=first;i<last;i++) {
    ruby_base *b=&m->bases[i];
    status=shape(f,b->first,b->stop,1,&texts[i]); if(status!=EXR_OK) goto done;
    if(texts[i].layout->glyph_count>RUBY_SCALARS-scalars) { status=failure(f,EXR_LIMIT,"Ruby group exceeds 8192 shaped glyphs"); goto done; }
    scalars+=texts[i].layout->glyph_count;
    columns[i]=texts[i].width; base_ascent=fmaxf(base_ascent,texts[i].ascent);
    base_descent=fmaxf(base_descent,texts[i].descent); base_height=fmaxf(base_height,texts[i].height);
  }
  for(i=0;i<m->annotation_count;i++) {
    ruby_annotation *a=&m->annotations[i]; ruby_text *t=&texts[m->base_count+i]; float width=0;
    if(a->column<first || a->column>=last) continue;
    status=shape(f,a->node,f->doc->nodes[a->node].next_sibling,0,t); if(status!=EXR_OK) goto done;
    if(t->layout->glyph_count>RUBY_SCALARS-scalars) { status=failure(f,EXR_LIMIT,"Ruby group exceeds 8192 shaped glyphs"); goto done; }
    scalars+=t->layout->glyph_count;
    for(j=a->column;j<a->column+a->span;j++) width+=columns[j];
    if(t->width>width) for(j=a->column;j<a->column+a->span;j++) columns[j]+=(t->width-width)/(float)a->span;
    row_height[a->row]=fmaxf(row_height[a->row],t->height);
    row_ascent[a->row]=fmaxf(row_ascent[a->row],t->ascent); row_descent[a->row]=fmaxf(row_descent[a->row],t->descent);
  }
  base_height=fmaxf(base_height,base_ascent+base_descent);
  for(i=0;i<m->rows;i++) if(row_height[i]) {
    int under=(int)(i&1),is_before=f->writing_mode==EXR_WRITING_VERTICAL_LR ? under : !under;
    if(is_before) before+=row_height[i]+gap; else after+=row_height[i]+gap;
  }
  { float prior=before,next=before+base_height;
    for(i=0;i<m->rows;i++) if(row_height[i]) {
      int under=(int)(i&1),is_before=f->writing_mode==EXR_WRITING_VERTICAL_LR ? under : !under;
      if(is_before) { prior-=gap+row_height[i]; row_y[i]=prior; }
      else { next+=gap; row_y[i]=next; next+=row_height[i]; }
    }
  }
  *baseline=before+base_ascent+(base_height-base_ascent-base_descent)/2;
  { float x=0;
    for(i=first;i<last;i++) {
      ruby_text *t=&texts[i]; float y=*baseline-t->ascent-(t->height-t->ascent-t->descent)/2;
      status=place(f,result,t,x,y,columns[i],f->styles[root].ruby_align); if(status!=EXR_OK) goto done;
      x+=columns[i];
    }
    result->flow_inline=x;
  }
  for(i=0;i<m->annotation_count;i++) {
    ruby_annotation *a=&m->annotations[i]; ruby_text *t=&texts[m->base_count+i]; float x=0,width=0,y;
    if(a->column<first || a->column>=last) continue;
    for(j=first;j<a->column;j++) x+=columns[j];
    for(j=a->column;j<a->column+a->span;j++) width+=columns[j];
    y=row_y[a->row]+row_ascent[a->row]+(row_height[a->row]-row_ascent[a->row]-row_descent[a->row])/2-
       t->ascent-(t->height-t->ascent-t->descent)/2;
    status=place(f,result,t,x,y,width,f->styles[a->node].ruby_align); if(status!=EXR_OK) goto done;
  }
  result->flow_block=before+base_height+after;
  *out=result; result=NULL;
done:
  if(texts) for(i=0;i<m->base_count+m->annotation_count;i++) exr_layout_free(texts[i].layout);
  free(texts); exr_layout_free(result); return status;
}
exr_status exr_ruby_item(flow *f,size_t node,size_t part,exr_glyph *item,int *done) {
  ruby_model *m=calloc(1,sizeof(*m)); exr_layout *layout=NULL; exr_status status; float baseline=0;
  *done=0;
  if(!m) return failure(f,EXR_MEMORY,"Ruby model allocation failed");
  status=parse(f,node,m); if(status!=EXR_OK) goto done;
  if(!m->base_count || (m->complex ? part!=0 : part>=m->base_count)) { *done=1; goto done; }
  *item=(exr_glyph){0}; item->node=node; item->glyph=m->complex ? UINT32_MAX : (uint32_t)part;
  status=prepare(f,node,item->glyph,m,&layout,&baseline); if(status!=EXR_OK) goto done;
  item->start=m->complex ? f->doc->nodes[node].start : m->bases[part].start;
  item->end=m->complex ? f->doc->nodes[node].end : m->bases[part].end;
  item->cluster_start=item->start; item->cluster_end=item->end; item->codepoint=0xfffc;
  item->size=f->styles[node].font_size; item->advance=layout->flow_inline; item->line_height=layout->flow_block;
  item->offset_x=baseline; item->offset_y=layout->flow_block-baseline;
  item->flags=EXR_GLYPH_RUBY_ITEM|EXR_GLYPH_SHAPED;
done:
  exr_layout_free(layout); free(m); return status;
}
exr_status exr_ruby_layout(flow *f,const exr_glyph *item,exr_layout **out) {
  ruby_model *m=calloc(1,sizeof(*m)); exr_status status; float baseline;
  *out=NULL;
  if(!m) return failure(f,EXR_MEMORY,"Ruby model allocation failed");
  status=parse(f,item->node,m);
  if(status==EXR_OK) status=prepare(f,item->node,item->glyph,m,out,&baseline);
  free(m); return status;
}
