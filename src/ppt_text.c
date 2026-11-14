/* SPDX-License-Identifier: MIT */
#include "ppt_internal.h"
#include "flow_internal.h"
#include "exr/font_manager.h"

static int text_warning(exr_buffer *list,const char *name) {
  size_t at=0;
  while(at<list->size) {
    if(!strcmp(list->data+at,name)) return 1;
    at+=strlen(list->data+at)+1;
  }
  return list->size<65536 && exr_append(list,name,strlen(name)+1);
}


/* Pick each requested script/style before constructing one bounded engine font
   set. This preserves EA and bold faces that a coverage-compacted chain omits. */
static exr_status text_font(exr_ppt_drawing *d,exr_document *model,exr_style *styles,
                            exr_font **out,const exr_control *control,exr_error *e) {
  exr_ppt_text_font key={0};
  size_t i,j,at,work=0;
  exr_status status;
  exr_font_input inputs[32]={0};
  unsigned char *bytes[32]={0};
  if(!d->font_manager) {
    exr_font_manager_options options={0};
    options.struct_size=sizeof(options); options.flags=EXR_FONT_MANAGER_PLATFORM_DIRECTORIES;
    status=exr_font_manager_create(&options,&d->font_manager,e);
    if(status!=EXR_OK) return status;
  }
  for(i=3;i<model->node_count;i++) {
    const exr_node *node=&model->nodes[i];
    const char *family=styles[i].family;
    exr_font_chain_link *chain=NULL;
    size_t chain_count=0;
    if(node->kind!=EXR_NODE_TEXT) continue;
    if(strcmp(family,"sans-serif") && !exr_font_manager_has_family(d->font_manager,family)) {
      if(!text_warning(&d->font_fallbacks,family)) return exr_fail(e,EXR_LIMIT,"PPT font warnings exceed budget");
      family=exr_font_manager_has_family(d->font_manager,"Segoe UI") ? "Segoe UI" : "sans-serif";
      styles[i].family=family;
    }
    status=exr_font_manager_chain(d->font_manager,family,styles[i].flags&3,&chain,&chain_count,e);
    if(status!=EXR_OK) return status;
    at=node->start;
    while(at<node->end) {
      uint32_t cp;
      exr_font_pick_result pick={0};
      if((++work&1023)==1) {
        status=exr_control_cancel(control,e);if(status!=EXR_OK) { free(chain);return status; }
      }
      if(!exr_next(model->text,model->size,&at,&cp)) { free(chain); return exr_fail(e,EXR_ENCODING,"PPT text is not UTF-8"); }
      pick.struct_size=sizeof(pick);
      pick.face=SIZE_MAX;
      for(j=0;j<chain_count;j++) if(exr_font_manager_face_covers(d->font_manager,chain[j].face,cp)) {
        pick.face=chain[j].face; pick.step=chain[j].step; break;
      }
      if(cp>32 && (pick.face==SIZE_MAX || pick.step>=EXR_FONT_STEP_FALLBACK)) {
        char warning[192];
        snprintf(warning,sizeof(warning),"%s U+%04X%s",family,(unsigned)cp,pick.face==SIZE_MAX ? " missing" : " fallback");
        if(!text_warning(&d->glyph_fallbacks,warning)) { free(chain); return exr_fail(e,EXR_LIMIT,"PPT glyph warnings exceed budget"); }
      }
      if(pick.face==SIZE_MAX) {
        status=exr_font_manager_pick(d->font_manager,"sans-serif",0,'?',&pick,e);
        if(status!=EXR_OK) { free(chain); return status; }
        if(pick.face==SIZE_MAX) { free(chain); return exr_fail(e,EXR_FONT,"PPT has no default font"); }
      }
      for(j=0;j<key.count && key.faces[j]!=pick.face;j++) { }
      if(j==key.count) {
        if(key.count==32) { free(chain); return exr_fail(e,EXR_LIMIT,"PPT paragraph exceeds 32 font faces"); }
        key.faces[key.count++]=pick.face;
      }
    }
    free(chain);
  }
  if(!key.count) { *out=NULL; return EXR_OK; }
  for(i=0;i<d->text_font_count;i++) if(key.count==d->text_fonts[i].count &&
      !memcmp(key.faces,d->text_fonts[i].faces,key.count*sizeof(size_t))) {
    *out=d->text_fonts[i].font; return EXR_OK;
  }
  status=EXR_OK;
  for(i=0;i<key.count && status==EXR_OK;i++) {
    exr_font_face_info info={0}; size_t size=0;
    info.struct_size=sizeof(info);
    status=exr_font_manager_face(d->font_manager,key.faces[i],&info,e);
    if(status==EXR_OK) status=exr_read(info.path,&bytes[i],&size,e);
    if(status==EXR_OK && size>EXR_FONT_MANAGER_MAX_BYTES-d->font_bytes)
      status=exr_fail(e,EXR_LIMIT,"PPT fonts exceed 256 MiB");
    if(status==EXR_OK) { d->font_bytes+=size; inputs[i]=(exr_font_input){bytes[i],size,info.face_index}; }
  }
  if(status==EXR_OK) status=exr_font_create_managed(inputs,key.count,&key.font,e);
  for(i=0;i<key.count;i++) free(bytes[i]);
  if(status!=EXR_OK) return status;
  if(!exr_grow((void **)&d->text_fonts,&d->text_font_capacity,d->text_font_count+1,sizeof(key))) {
    exr_font_free(key.font); return exr_fail(e,EXR_MEMORY,"PPT font directory allocation failed");
  }
  d->text_fonts[d->text_font_count++]=key; *out=key.font;
  return EXR_OK;
}

static int text_script(uint32_t cp) {
  return (cp>=0x2e80 && cp<=0x9fff) || (cp>=0xac00 && cp<=0xd7af) ||
         (cp>=0xf900 && cp<=0xfaff) || (cp>=0xff00 && cp<=0xffef) || cp>=0x20000;
}

typedef struct { exr_ppt_text_style style; const char *family; } ppt_text_span;

/* Binary slide text preserves whitespace. Avoid the HTML model projection's
   whitespace folding while retaining the engine's ordinary text-node ranges. */
static exr_status text_model_finish(exr_document *model,exr_error *e) {
  exr_buffer text={0};
  size_t i;
  for(i=3;i<model->node_count;i++) {
    exr_node *node=&model->nodes[i];
    const char *s=node->kind==EXR_NODE_BREAK ? "\n" : node->text;
    node->start=text.size;
    if(s && !exr_append(&text,s,strlen(s))) {
      free(text.data); return exr_fail(e,EXR_LIMIT,"PPT text projection exceeds 64 MiB");
    }
    node->end=text.size;
  }
  model->text=text.data; model->size=text.size; model->text_capacity=text.capacity;
  for(i=0;i<3;i++) { model->nodes[i].start=0; model->nodes[i].end=text.size; }
  return EXR_OK;
}

static exr_status text_add(exr_document *model,ppt_text_span **spans,size_t *capacity,
                           const char *text,size_t length,const exr_ppt_text_style *style,exr_error *e) {
  size_t at=0,first=0,node;
  int script=-1;
  while(at<length) {
    size_t start=at;
    uint32_t cp;
    int next;
    if(!exr_next(text,length,&at,&cp)) return exr_fail(e,EXR_ENCODING,"PPT text is not UTF-8");
    next=text_script(cp);
    if(script<0) script=next;
    if(next!=script || at==length) {
      size_t end=next!=script ? start : at;
      node=exr_model_node(model,2,0,EXR_NODE_TEXT,NULL,text+first,end-first);
      if(node==SIZE_MAX || !exr_grow((void **)spans,capacity,model->node_count,sizeof(**spans)))
        return exr_fail(e,EXR_LIMIT,"PPT text model exceeds node budget");
      (*spans)[node]=(ppt_text_span){*style,script==1 && style->ea ? style->ea : style->family};
      first=end; script=next;
      if(at==length && first<length) {
        node=exr_model_node(model,2,0,EXR_NODE_TEXT,NULL,text+first,length-first);
        if(node==SIZE_MAX || !exr_grow((void **)spans,capacity,model->node_count,sizeof(**spans)))
          return exr_fail(e,EXR_LIMIT,"PPT text model exceeds node budget");
        (*spans)[node]=(ppt_text_span){*style,script==1 && style->ea ? style->ea : style->family};
      }
    }
  }
  return EXR_OK;
}

static exr_status text_paragraph(exr_ppt_drawing *d,exr_ppt_text *text,exr_ppt_text_paragraph *para,
                                 size_t first_run,double width,double left,double *y,
                                 const exr_control *control,exr_error *e) {
  exr_document *model=calloc(1,sizeof(*model));
  const exr_ppt_text_style *base=&para->style;
  exr_ppt_text_style bullet_style=*base;
  exr_style *styles=NULL;
  ppt_text_span *spans=NULL;
  size_t capacity=0,i,j,bullet_end=3;
  exr_buffer bullet={0};
  exr_shaped_glyph *bullet_glyphs=NULL;
  size_t bullet_count=0,bullet_face=0;
  double text_offset=0;
  exr_font *font=NULL;
  exr_layout *layout=NULL;
  exr_layout_config config=exr_layout_config_defaults();
  exr_status status=EXR_OK;
  flow parent={0};exr_layout viewport={0},assets={0};exr_float_state floats={0};
  float height;
  if(!model) return exr_fail(e,EXR_MEMORY,"PPT paragraph allocation failed");
  model->chapters=calloc(1,sizeof(*model->chapters));
  if(!model->chapters) { status=exr_fail(e,EXR_MEMORY,"PPT chapter allocation failed");goto done; }
  model->chapter_count=1;model->chapters[0].root=1;model->chapters[0].resource=SIZE_MAX;
  model->chapters[0].in_spine=model->chapters[0].linear=1;
  if(exr_model_node(model,SIZE_MAX,0,EXR_NODE_DOCUMENT,NULL,NULL,0)==SIZE_MAX ||
     exr_model_node(model,0,0,EXR_NODE_CHAPTER,NULL,NULL,0)==SIZE_MAX ||
     exr_model_node(model,1,0,EXR_NODE_PARAGRAPH,"p",NULL,0)==SIZE_MAX) {
    status=exr_fail(e,EXR_LIMIT,"PPT paragraph model allocation failed");goto done;
  }
  if(first_run<text->run_count && text->runs[first_run].start<=para->start && text->runs[first_run].end>para->start)
    bullet_style=text->runs[first_run].style;
  if(base->bullet_family) bullet_style.family=bullet_style.ea=base->bullet_family;
  if(base->bullet_color) bullet_style.color=base->bullet_color;
  if(base->bullet_size>0) bullet_style.size=base->bullet_size;
  else if(base->bullet_size<0) bullet_style.size*=-base->bullet_size;
  if(base->bullet) {
    if(!exr_codepoint(&bullet,base->bullet)) { status=exr_fail(e,EXR_MEMORY,"PPT bullet allocation failed");goto done; }
    status=text_add(model,&spans,&capacity,bullet.data,bullet.size,&bullet_style,e);
  }
  bullet_end=model->node_count;
  for(i=first_run;status==EXR_OK && i<text->run_count;i++) {
    const exr_ppt_text_run *run=&text->runs[i];
    size_t at=run->start>para->start ? run->start : para->start;
    size_t end=run->end<para->end ? run->end : para->end,first=at;
    if(run->start>=para->end) break;
    if(at>=end) continue;
    while(at<end) {
      unsigned char ch=(unsigned char)text->value[at];
      if(!(at&4095)) {
        status=exr_control_cancel(control,e);if(status!=EXR_OK) break;
      }
      if(ch=='\v' || ch=='\r' || ch=='\n') {
        size_t node;
        status=text_add(model,&spans,&capacity,text->value+first,at-first,&run->style,e);
        if(status!=EXR_OK) break;
        node=exr_model_node(model,2,0,EXR_NODE_BREAK,"br",NULL,0);
        if(node==SIZE_MAX) { status=exr_fail(e,EXR_LIMIT,"PPT break model allocation failed");break; }
        first=at+1;
      }
      at++;
    }
    if(status==EXR_OK) status=text_add(model,&spans,&capacity,text->value+first,end-first,&run->style,e);
  }
  if(status!=EXR_OK) goto done;
  status=text_model_finish(model,e);if(status!=EXR_OK) goto done;
  styles=calloc(model->node_count,sizeof(*styles));
  if(!styles) { status=exr_fail(e,EXR_MEMORY,"PPT styles allocation failed");goto done; }
  for(i=0;i<model->node_count;i++) {
    exr_style *s=&styles[i];
    const exr_ppt_text_style *t=i>=3 && model->nodes[i].kind==EXR_NODE_TEXT ? &spans[i].style : base;
    s->font_size=(float)t->size;s->leading=1;s->leading_relative=1;
    s->family=i>=3 && model->nodes[i].kind==EXR_NODE_TEXT ? spans[i].family : base->family;
    if(!s->family || !*s->family) s->family="sans-serif";
    s->color=t->color;s->flags=t->flags;s->display=i<3 ? EXR_CSS_BLOCK : EXR_CSS_INLINE;
    s->width.value=s->height.value=s->max_width.value=s->max_height.value=-1;
    s->indent_declared=1;s->hyphens=EXR_HYPHENS_NONE;
    if(i>=3 && i<bullet_end) s->display=EXR_CSS_NONE;
  }
  styles[2].align=text->wrap ? base->align : 0;styles[2].indent=base->bullet ? 0 : (float)base->indent;
  status=text_font(d,model,styles,&font,control,e);if(status!=EXR_OK) goto done;
  if(!font) {
    size_t lines=1;
    double advance=base->line_pct ? base->size*base->line : base->line;
    for(i=3;i<model->node_count;i++) if(model->nodes[i].kind==EXR_NODE_BREAK) lines++;
    *y+=(base->before_pct ? base->before*base->size : base->before)+advance*lines+
        (base->after_pct ? base->after*base->size : base->after);
    goto done;
  }
  if(base->bullet) {
    size_t order[32],count=exr_font_order(font,styles[3].family,bullet_style.flags,0,order);
    exr_shape_options options=exr_shape_defaults();
    double advance=0;
    for(i=0;i<count;i++) if(exr_font_has_glyph(font,order[i],base->bullet)) { bullet_face=order[i];break; }
    options.font_size=(float)bullet_style.size;options.style_flags=bullet_style.flags&3;
    if(control) options.control=*control;
    status=exr_shape(font,bullet_face,bullet.data,bullet.size,&options,&bullet_glyphs,&bullet_count,e);
    if(status!=EXR_OK) goto done;
    for(i=0;i<bullet_count;i++) advance+=bullet_glyphs[i].advance_x;
    text_offset=fmax(0,base->indent+advance+bullet_style.size/4);
  }
  config.page=(exr_layout_options){16384,16384,0,18,1,0};if(control) config.control=*control;
  viewport.options=config.page;assets.font=font;
  parent.layout=&viewport;parent.assets=&assets;parent.doc=model;parent.font=font;
  parent.config=&config;parent.styles=styles;parent.paragraph=&styles[0];parent.error=e;
  parent.floats=&floats;parent.width=(float)fmax(1,width-base->margin-text_offset);
  status=exr_flow_unit(&parent,2,text->wrap ? parent.width : 10000000,&layout,&height);
  if(status!=EXR_OK || !layout) goto done;
  *y+=base->before_pct ? base->before*base->size : base->before;
  for(i=0;i<layout->line_count;i++) {
    exr_line *line=&layout->lines[i];
    double advance=base->line_pct ? line->height*base->line : base->line;
    double shift=0;
    if(!text->wrap && base->align==1) shift=(parent.width-line->width)/2;
    else if(!text->wrap && base->align==2) shift=parent.width-line->width;
    for(j=0;j<line->glyph_count;j++) {
      exr_glyph *g=&layout->glyphs[line->glyph_start+j];
      g->x+=(float)(left+base->margin+text_offset+shift);g->baseline+=(float)(*y-line->y);
    }
    *y+=advance;
  }
  if(base->bullet && layout->line_count && layout->glyph_count) {
    double x=left+base->margin+base->indent;
    float baseline=layout->glyphs[layout->lines[0].glyph_start].baseline;
    if(!exr_grow((void **)&layout->glyphs,&layout->glyph_cap,layout->glyph_count+bullet_count,sizeof(exr_glyph))) {
      status=exr_fail(e,EXR_MEMORY,"PPT bullet glyph allocation failed");goto done;
    }
    for(i=0;i<bullet_count;i++) {
      exr_glyph g={0};
      g.glyph=bullet_glyphs[i].glyph;g.font_index=bullet_face;g.size=(float)bullet_style.size;g.color=bullet_style.color;
      g.x=(float)x;g.baseline=baseline;g.advance=bullet_glyphs[i].advance_x;
      g.offset_x=bullet_glyphs[i].offset_x;g.offset_y=bullet_glyphs[i].offset_y;
      g.flags=bullet_glyphs[i].flags|(bullet_style.flags&EXR_GLYPH_UNDERLINE);
      layout->glyphs[layout->glyph_count++]=g;x+=g.advance;
    }
  }
  *y+=base->after_pct ? base->after*base->size : base->after;
  if(layout->glyph_count>(EXR_MAX_INPUT-d->text_bytes)/sizeof(exr_glyph)) {
    status=exr_fail(e,EXR_LIMIT,"PPT text storage exceeds 128 MiB");goto done;
  }
  d->text_bytes+=layout->glyph_count*sizeof(exr_glyph);para->layout=layout;layout=NULL;
done:
  exr_layout_free(layout);free(styles);free(spans);free(bullet.data);free(bullet_glyphs);exr_document_free(model);
  return status;
}

exr_status exr_ppt_text_layout(exr_ppt_drawing *d,const exr_control *control,exr_error *e) {
  size_t i,j,k;
  for(i=0;i<d->count;i++) {
    exr_ppt_shape *shape=&d->shapes[i];exr_ppt_text *text=shape->text;
    double y=0,offset,width;size_t first_run=0;
    exr_status status=exr_control_cancel(control,e);if(status!=EXR_OK) return status;
    if(!text) continue;
    width=fabs(shape->bounds[2]-shape->bounds[0])-text->inset[1]-text->inset[3];
    for(j=0;j<text->paragraph_count;j++) {
      status=exr_control_cancel(control,e);if(status!=EXR_OK) return status;
      while(first_run<text->run_count && text->runs[first_run].end<=text->paragraphs[j].start) first_run++;
      status=text_paragraph(d,text,&text->paragraphs[j],first_run,width,text->inset[3],&y,control,e);
      if(status!=EXR_OK) return status;
    }
    offset=text->inset[0];
    if(text->anchor==1) offset+=(fabs(shape->bounds[3]-shape->bounds[1])-text->inset[0]-text->inset[2]-y)/2;
    else if(text->anchor==2) offset+=fabs(shape->bounds[3]-shape->bounds[1])-text->inset[0]-text->inset[2]-y;
    for(j=0;j<text->paragraph_count;j++) if(text->paragraphs[j].layout) {
      exr_layout *layout=text->paragraphs[j].layout;
      for(k=0;k<layout->glyph_count;k++) layout->glyphs[k].baseline+=(float)offset;
    }
  }
  return EXR_OK;
}

static void multiply(const double a[6],const double b[6],double out[6]) {
  out[0]=a[0]*b[0]+a[2]*b[1];out[1]=a[1]*b[0]+a[3]*b[1];
  out[2]=a[0]*b[2]+a[2]*b[3];out[3]=a[1]*b[2]+a[3]*b[3];
  out[4]=a[0]*b[4]+a[2]*b[5]+a[4];out[5]=a[1]*b[4]+a[3]*b[5]+a[5];
}

exr_status exr_ppt_text_draw(const exr_ppt_shape *shape,const double matrix[6],const exr_draw_sink *sink,
                            const exr_control *control,exr_error *e) {
  size_t i,j;double position[6]={1,0,0,1,0,0},placed[6];
  if(!shape->text || !sink->path) return EXR_OK;
  position[4]=fmin(shape->bounds[0],shape->bounds[2]);position[5]=fmin(shape->bounds[1],shape->bounds[3]);
  multiply(matrix,position,placed);
  for(i=0;i<shape->text->paragraph_count;i++) {
    const exr_layout *layout=shape->text->paragraphs[i].layout;
    if(!layout) continue;
    for(j=0;j<layout->glyph_count;j++) {
      const exr_glyph *g=&layout->glyphs[j];
      exr_path_segment *path=NULL;size_t count=0;double local[6],combined[6];
      exr_draw_style style=exr_draw_style_defaults();exr_status status=exr_control_cancel(control,e);
      if(status!=EXR_OK) return status;
      if(g->flags&EXR_GLYPH_HIDDEN) continue;
      status=exr_font_glyph_outline(layout->font,g->font_index,g->glyph,&path,&count,control,e);
      if(status==EXR_OK) status=exr_glyph_matrix(g,local,e);
      if(status==EXR_OK) {
        if(g->flags&EXR_GLYPH_ITALIC) local[2]=local[0]*0.2;
        multiply(placed,local,combined);
      }
      style.flags=EXR_DRAW_FILL;style.fill=g->color;
      if(g->flags&EXR_GLYPH_BOLD) { style.flags|=EXR_DRAW_STROKE;style.stroke=g->color;style.line.width=25; }
      if(status==EXR_OK && count) status=sink->path(sink->context,path,count,combined,&style,e);
      free(path);if(status!=EXR_OK) return status;
      if(g->flags&EXR_GLYPH_UNDERLINE) {
        exr_path_segment line[2]={{EXR_PATH_MOVE,{{g->x,g->baseline+g->size*0.1}}},
                                  {EXR_PATH_LINE,{{g->x+g->advance,g->baseline+g->size*0.1}}}};
        style.flags=EXR_DRAW_STROKE;style.stroke=g->color;style.line.width=fmax(0.5,g->size/16);
        status=sink->path(sink->context,line,2,placed,&style,e);if(status!=EXR_OK) return status;
      }
    }
  }
  return EXR_OK;
}

void exr_ppt_text_free(exr_ppt_drawing *d) {
  size_t i,j;
  for(i=0;i<d->count;i++) if(d->shapes[i].text) {
    exr_ppt_text *text=d->shapes[i].text;
    for(j=0;j<text->paragraph_count;j++) exr_layout_free(text->paragraphs[j].layout);
    free(text->value);free(text->runs);free(text->paragraphs);free(text);d->shapes[i].text=NULL;
  }
  for(i=0;i<d->text_font_count;i++) exr_font_free(d->text_fonts[i].font);
  free(d->text_fonts);exr_font_manager_free(d->font_manager);
  free(d->font_fallbacks.data);free(d->glyph_fallbacks.data);
}

