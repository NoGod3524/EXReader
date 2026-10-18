/* SPDX-License-Identifier: GPL-3.0-only */
#include "layout_internal.h"
#include <stddef.h>
static int span(size_t first,size_t count,size_t total) { return first<=total && count<=total-first; }
static int boundary(const exr_document *d,size_t at) {
  return at<=d->size && (at==d->size || !((unsigned char)d->text[at]>=128 && (unsigned char)d->text[at]<192));
}
static int range(const exr_document *d,size_t first,size_t end) {
  return first<=end && boundary(d,first) && boundary(d,end);
}
static int number(float value) { return isfinite(value) && fabsf(value)<=10000000; }
static int nonnegative(float value) { return number(value) && value>=0; }
static int budget(size_t *bytes,size_t count,size_t unit) {
  if(count>(EXR_MAX_INPUT-*bytes)/unit) return 0;
  *bytes+=count*unit; return 1;
}
static void *copy_array(const void *source,size_t count,size_t unit) {
  void *copy;
  if(!count) return NULL;
  copy=malloc(count*unit); if(copy) memcpy(copy,source,count*unit); return copy;
}
static int point(float *value,double scale,double offset) {
  double result=(double)*value*scale+offset;
  if(!isfinite(result) || fabs(result)>10000000) return 0;
  *value=(float)result; return 1;
}
exr_status exr_layout_create_positioned(const exr_document *d,exr_font *font,
                                         const exr_positioned_input *input,
                                         const exr_layout_config *configuration,
                                         exr_layout **out,exr_error *e) {
  exr_layout_config settings=configuration ? *configuration : exr_layout_config_defaults(); const exr_layout_config *config=&settings;
  exr_positioned_input snapshot={0};
  const size_t minimum=offsetof(exr_positioned_input,paint_count)+sizeof(snapshot.paint_count);
  exr_layout *l=NULL; size_t i,j,line=0,box=0,paint=0,glyph=0,end=0,bytes=sizeof(*l);
  exr_status status=EXR_ARGUMENT;
  if(!out) return exr_fail(e,EXR_ARGUMENT,"Missing positioned layout output");
  *out=NULL; if(e) memset(e,0,sizeof(*e));
  if(!d || !input || input->struct_size<minimum || input->struct_size>4096)
    return exr_fail(e,EXR_ARGUMENT,"Invalid positioned layout input size");
  for(i=sizeof(*input);i<input->struct_size;i++) if(((const unsigned char *)input)[i])
    return exr_fail(e,EXR_ARGUMENT,"Unsupported positioned input extension");
  memcpy(&snapshot,input,input->struct_size<sizeof(snapshot) ? input->struct_size : sizeof(snapshot)); input=&snapshot;
  if(!isfinite(config->page.width) || !isfinite(config->page.height) || !isfinite(config->page.margin) ||
     config->page.width<1 || config->page.height<1 || config->page.width>16384 || config->page.height>16384 ||
     config->page.margin<0 || config->page.margin>=fminf(config->page.width,config->page.height)/2 ||
     (config->decode_image && !config->release_image)) return exr_fail(e,EXR_ARGUMENT,"Invalid positioned viewport or image callbacks");
  if(!input->page_count || !input->pages || (input->glyph_count && (!input->glyphs || !font)) ||
     (input->line_count && !input->lines) || (input->box_count && !input->boxes) ||
     (input->paint_count && !input->paints)) return exr_fail(e,EXR_ARGUMENT,"Missing positioned arrays or font");
  if(input->page_count>10000 || input->glyph_count>EXR_MAX_ITEMS || input->line_count>EXR_MAX_ITEMS ||
     input->box_count>EXR_MAX_ITEMS || input->paint_count>EXR_MAX_ITEMS ||
     !budget(&bytes,input->page_count,sizeof(exr_positioned_page)+sizeof(exr_page)) ||
     !budget(&bytes,input->glyph_count,sizeof(exr_glyph)) || !budget(&bytes,input->line_count,sizeof(exr_line)) ||
     !budget(&bytes,input->box_count,sizeof(exr_box)) || !budget(&bytes,input->paint_count,sizeof(exr_paint)))
    return exr_fail(e,EXR_LIMIT,"Positioned arrays exceed item or 128 MiB byte budget");
  l=calloc(1,sizeof(*l)); if(!l) goto memory;
  l->options=config->page; l->font=font; exr_font_ref(font);
  l->page_count=l->page_cap=input->page_count; l->pages=calloc(l->page_count,sizeof(*l->pages));
  l->positioned=copy_array(input->pages,input->page_count,sizeof(*input->pages));
  l->glyph_count=l->glyph_cap=input->glyph_count; l->glyphs=copy_array(input->glyphs,input->glyph_count,sizeof(*input->glyphs));
  l->line_count=l->line_cap=input->line_count; l->lines=copy_array(input->lines,input->line_count,sizeof(*input->lines));
  l->box_count=l->box_cap=input->box_count; l->boxes=copy_array(input->boxes,input->box_count,sizeof(*input->boxes));
  l->paint_count=input->paint_count; l->paints=copy_array(input->paints,input->paint_count,sizeof(*input->paints));
  if(!l->pages || !l->positioned || (l->glyph_count && !l->glyphs) || (l->line_count && !l->lines) ||
     (l->box_count && !l->boxes) || (l->paint_count && !l->paints)) goto memory;
  for(i=0;i<input->page_count;i++) {
    const exr_positioned_page *p=&l->positioned[i]; const exr_page *c=&p->content;
    double scale,dx,dy;
    status=exr_control_poll(&config->control,EXR_STAGE_LAYOUT,i,input->page_count,e); if(status!=EXR_OK) goto failed;
    status=EXR_ARGUMENT;
    if(!number(p->width) || !number(p->height) || p->width<0.001f || p->height<0.001f ||
       !range(d,c->start,c->end) || c->line_start!=line || c->box_start!=box || p->paint_start!=paint ||
       !span(line,c->line_count,l->line_count) || !span(box,c->box_count,l->box_count) || !span(paint,p->paint_count,l->paint_count)) goto invalid;
    scale=fmin(((double)l->options.width-2*l->options.margin)/p->width,
                 ((double)l->options.height-2*l->options.margin)/p->height);
    dx=((double)l->options.width-p->width*scale)/2; dy=((double)l->options.height-p->height*scale)/2;
    l->pages[i]=*c;
    if(i && c->start<end) l->source_overlaps=1;
    for(j=line;j<line+c->line_count;j++) {
      exr_line *v=&l->lines[j]; size_t k;
      if(v->page!=i || v->glyph_start!=glyph || !span(glyph,v->glyph_count,l->glyph_count) ||
         !range(d,v->start,v->end) || v->start<c->start || v->end>c->end || !number(v->x) || !number(v->y) ||
         !nonnegative(v->width) || !nonnegative(v->height)) goto invalid;
      for(k=glyph;k<glyph+v->glyph_count;k++) {
        exr_glyph *g=&l->glyphs[k];
        if(!(k&255)) { status=exr_control_cancel(&config->control,e); if(status!=EXR_OK) goto failed; }
        if(g->page!=i || g->font_index>=font->count || g->glyph>=(uint64_t)font->faces[g->font_index].face->num_glyphs ||
           g->codepoint>0x10ffff || (g->codepoint>=0xd800 && g->codepoint<=0xdfff) ||
           (g->node!=SIZE_MAX && g->node>=d->node_count) || (g->flags&~511u) ||
           ((g->flags&EXR_GLYPH_SIDEWAYS) && !(g->flags&EXR_GLYPH_VERTICAL)) ||
           (g->boundaries&~15u) ||
           (g->bidi_level>127 && !(g->bidi_level==UINT_MAX && (g->flags&EXR_GLYPH_HIDDEN))) ||
           !range(d,g->start,g->end) || !range(d,g->cluster_start,g->cluster_end) ||
           g->cluster_start>g->start || g->cluster_end<g->end || g->cluster_start<v->start || g->cluster_end>v->end ||
           !number(g->x) || !number(g->baseline) || !nonnegative(g->advance) || !nonnegative(g->size) ||
           (!(g->flags&EXR_GLYPH_HIDDEN) && !g->size) || !nonnegative(g->line_height) ||
           !number(g->offset_x) || !number(g->offset_y) || !number(g->clip_left) || !number(g->clip_right) || g->clip_left>g->clip_right ||
           (k>glyph && !!(g->flags&EXR_GLYPH_VERTICAL)!=!!(input->glyphs[k-1].flags&EXR_GLYPH_VERTICAL)) ||
           (k>glyph && g->cluster_start!=l->glyphs[k-1].cluster_start &&
            ((g->flags&EXR_GLYPH_VERTICAL) ? g->baseline<input->glyphs[k-1].baseline : g->x<input->glyphs[k-1].x))) goto invalid;
        if(!point(&g->x,scale,dx) || !point(&g->baseline,scale,dy) || !point(&g->advance,scale,0) ||
           !point(&g->size,scale,0) || g->size>4096 || !point(&g->line_height,scale,0) ||
           !point(&g->offset_x,scale,0) || !point(&g->offset_y,scale,0) ||
           !point(&g->clip_left,scale,(g->flags&EXR_GLYPH_VERTICAL) ? dy : dx) ||
           !point(&g->clip_right,scale,(g->flags&EXR_GLYPH_VERTICAL) ? dy : dx)) goto invalid;
        g->flags|=EXR_GLYPH_SHAPED;
      }
      glyph+=v->glyph_count;
      if(!point(&v->x,scale,dx) || !point(&v->y,scale,dy) || !point(&v->width,scale,0) || !point(&v->height,scale,0)) goto invalid;
    }
    for(j=box;j<box+c->box_count;j++) {
      exr_box *b=&l->boxes[j];
      if(b->page!=i || b->kind<EXR_BOX_BLOCK || b->kind>EXR_BOX_CELL ||
         (b->node!=SIZE_MAX && b->node>=d->node_count) || !range(d,b->start,b->end) || b->start<c->start || b->end>c->end ||
         !number(b->x) || !number(b->y) || !nonnegative(b->width) || !nonnegative(b->height) || !nonnegative(b->border_width) ||
         (b->kind==EXR_BOX_IMAGE ? (b->flags&~1u) : b->kind==EXR_BOX_BLOCK ? (b->flags&~EXR_BOX_BORDER) : b->flags) ||
         ((b->flags&EXR_BOX_BORDER) && b->border_width!=0) ||
         (b->kind==EXR_BOX_IMAGE && !b->flags && b->resource>=d->resource_count)) goto invalid;
      if(!point(&b->x,scale,dx) || !point(&b->y,scale,dy) || !point(&b->width,scale,0) ||
         !point(&b->height,scale,0) || !point(&b->border_width,scale,0)) goto invalid;
    }
    for(j=paint;j<paint+p->paint_count;j++) {
      const exr_paint *v=&l->paints[j];
      if(v->flags || (v->kind==EXR_PAINT_GLYPH ? v->index>=l->glyph_count || l->glyphs[v->index].page!=i :
           v->kind==EXR_PAINT_BOX ? v->index>=l->box_count || l->boxes[v->index].page!=i : 1)) goto invalid;
    }
    line+=c->line_count; box+=c->box_count; paint+=p->paint_count; end=c->end;
  }
  if(line!=l->line_count || box!=l->box_count || paint!=l->paint_count || glyph!=l->glyph_count) goto invalid;
  for(i=0;i<l->paint_count;i++) if(l->paints[i].kind==EXR_PAINT_BOX) {
    const exr_box *b=&l->boxes[l->paints[i].index]; const exr_bitmap *bitmap;
    status=exr_control_poll(&config->control,EXR_STAGE_LAYOUT,i,l->paint_count,e); if(status!=EXR_OK) goto failed;
    if(b->kind==EXR_BOX_IMAGE && !b->flags && b->width && b->height) {
      status=exr_layout_image_asset(d,l,config,b->resource,&bitmap,e); if(status!=EXR_OK) goto failed;
    }
  }
  status=exr_control_poll(&config->control,EXR_STAGE_LAYOUT,input->page_count,input->page_count,e);
  if(status!=EXR_OK) goto failed;
  *out=l; return exr_fail(e,EXR_OK,"");
memory:
  status=exr_fail(e,EXR_MEMORY,"Positioned layout allocation failed"); goto failed;
invalid:
  status=exr_fail(e,EXR_ARGUMENT,"Invalid positioned geometry, source range, ordering or index");
failed:
  exr_layout_free(l); return status;
}
