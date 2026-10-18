/* SPDX-License-Identifier: GPL-3.0-only */
#include "pdf_raster_internal.h"
#include "pdf_face_internal.h"
typedef struct { const exr_pdf_font *key; exr_pdf_face *face; } paint_face;
typedef struct {
  exr_draw_sink_ex sink; FT_Library library; exr_pdf_program_fn program; void *program_context; const exr_control *control; size_t *work;
  size_t font_count,font_bytes; paint_face fonts[128];
} pdf_painter;
static uint32_t rgba(const exr_pdf_color *c) {
  unsigned r,g,b,a=(unsigned)floor(c->alpha*255+.5);
  if(c->space==EXR_PDF_DEVICE_GRAY) r=g=b=(unsigned)floor(c->values[0]*255+.5);
  else if(c->space==EXR_PDF_DEVICE_RGB) { r=(unsigned)floor(c->values[0]*255+.5); g=(unsigned)floor(c->values[1]*255+.5); b=(unsigned)floor(c->values[2]*255+.5); }
  else { r=(unsigned)floor((1-fmin(1,c->values[0]+c->values[3]))*255+.5); g=(unsigned)floor((1-fmin(1,c->values[1]+c->values[3]))*255+.5); b=(unsigned)floor((1-fmin(1,c->values[2]+c->values[3]))*255+.5); }
  return (r<<24)|(g<<16)|(b<<8)|a;
}
static void multiply(const double a[6],const double b[6],double out[6]) {
  out[0]=a[0]*b[0]+a[2]*b[1]; out[1]=a[1]*b[0]+a[3]*b[1];
  out[2]=a[0]*b[2]+a[2]*b[3]; out[3]=a[1]*b[2]+a[3]*b[3];
  out[4]=a[0]*b[4]+a[2]*b[5]+a[4]; out[5]=a[1]*b[4]+a[3]*b[5]+a[5];
}
static exr_status blend_state(pdf_painter *r,exr_blend_mode mode,exr_error *e) {
  if(r->sink.blend) {
    exr_status status=r->sink.blend(r->sink.base.context,mode,e);
    return status==EXR_OK && e && e->code!=EXR_OK ? e->code : status;
  }
  return mode==EXR_BLEND_NORMAL ? EXR_OK : exr_fail(e,EXR_FORMAT,"Drawing consumer does not support blend state");
}
static exr_status geometry(pdf_painter *r,const exr_vector_segment *segments,size_t count,const double transform[6],
                             const exr_pdf_paint_state *paint,unsigned flags,exr_vector_rule rule,int text_clip,exr_error *e) {
  exr_draw_style style=exr_draw_style_defaults(); exr_status status=EXR_OK;
  style.fill=rgba(&paint->fill); style.stroke=rgba(&paint->stroke); style.flags=flags&3; style.rule=rule;
  style.line=paint->line; style.dashes=paint->dashes; style.dash_count=paint->dash_count; style.dash_phase=paint->dash_phase; style.stroke_matrix=paint->matrix;
  if(style.flags && r->sink.base.path) status=blend_state(r,paint->blend,e);
  if(status==EXR_OK && style.flags && r->sink.base.path) status=r->sink.base.path(r->sink.base.context,segments,count,transform,&style,e);
  if(status==EXR_OK && (flags&EXR_PDF_CLIP) && r->sink.base.clip) status=r->sink.base.clip(r->sink.base.context,segments,count,transform,rule,text_clip!=0,e);
  return status;
}
static exr_status path_event(void *context,const exr_pdf_path_paint *p,exr_error *e) {
  return geometry(context,p->segments,p->count,NULL,&p->paint,p->flags,p->rule,0,e);
}
static exr_status state_event(void *context,exr_pdf_state_event event,exr_error *e) {
  pdf_painter *r=context;
  exr_draw_state state=event==EXR_PDF_SAVE ? EXR_DRAW_SAVE : event==EXR_PDF_RESTORE ? EXR_DRAW_RESTORE : event==EXR_PDF_BEGIN_TEXT ? EXR_DRAW_BEGIN_CLIP : EXR_DRAW_END_CLIP;
  return r->sink.base.state ? r->sink.base.state(r->sink.base.context,state,e) : EXR_OK;
}
static exr_status glyph_event(void *context,const exr_pdf_text_glyph *g,exr_error *e) {
  pdf_painter *r=context; size_t i,count=0; exr_status status; exr_vector_segment *segments=NULL; unsigned flags=0,mode=g->rendering_mode;
  /* Type3 CharProcs are interpreted by the content walker with the same
     graphics state, resources, recursion guard and operation budget. */
  if(exr_pdf_font_description(g->font)->kind==EXR_PDF_TYPE3) return EXR_OK;
  if(mode==3) return EXR_OK;
  if(mode==0 || mode==2 || mode==4 || mode==6) flags|=EXR_PDF_FILL;
  if(mode==1 || mode==2 || mode==5 || mode==6) flags|=EXR_PDF_STROKE;
  if(mode>=4) flags|=EXR_PDF_CLIP;
  if(!((flags&3) && r->sink.base.path) && !((flags&EXR_PDF_CLIP) && r->sink.base.clip)) return EXR_OK;
  for(i=0;i<r->font_count;i++) if(r->fonts[i].key==g->font) break;
  if(i==r->font_count) {
    const exr_pdf_font_info *info=exr_pdf_font_description(g->font); exr_font_input fallback={0}; size_t bytes,j; const exr_pdf_face *shared=NULL;
    if(i==128) return exr_fail(e,EXR_LIMIT,"PDF paint face cache exceeds 128 fonts");
    if(!info->program && r->program) { status=r->program(r->program_context,info,&fallback,e); if(status!=EXR_OK) return status; }
    for(j=0;j<i;j++) if(exr_pdf_face_matches(r->fonts[j].face,g->font,&fallback)) { shared=r->fonts[j].face; break; }
    status=exr_pdf_face_open_shared(r->library,g->font,&fallback,shared,&r->fonts[i].face,r->control,e); if(status!=EXR_OK) return status;
    r->fonts[i].key=g->font; r->font_count++; bytes=exr_pdf_face_memory(r->fonts[i].face);
    if(bytes>(size_t)32*1024*1024-r->font_bytes) return exr_fail(e,EXR_LIMIT,"PDF paint CID indexes exceed 32 MiB");
    r->font_bytes+=bytes;
  }
  status=exr_pdf_face_outline(r->fonts[i].face,&g->character,&segments,&count,r->work,r->control,e);
  if(status==EXR_OK) status=geometry(r,segments,count,g->transform,&g->paint,flags,EXR_VECTOR_NONZERO,1,e);
  free(segments); return status;
}
static exr_status image_event(void *context,exr_pdf_file *file,uint32_t id,exr_pdf_file *resource_file,uint32_t resources,const exr_pdf_paint_state *paint,exr_error *e) {
  pdf_painter *r=context; exr_vector_texture *image=NULL; double matrix[6]; const double flip[6]={1,0,0,-1,0,1};
  exr_status status; if(!r->sink.base.image) return EXR_OK;
  status=exr_pdf_image_load_from(file,id,resource_file,resources,rgba(&paint->fill),&image,r->work,r->control,e);
  multiply(paint->matrix,flip,matrix);
  if(status==EXR_OK) status=blend_state(r,paint->blend,e);
  if(status==EXR_OK) status=r->sink.base.image(r->sink.base.context,image,matrix,paint->fill.alpha,e);
  exr_pdf_image_release(image); return status;
}
static exr_status begin_layer_event(void *context,double opacity,exr_blend_mode mode,exr_error *e) {
  pdf_painter *r=context;return r->sink.begin_layer ? r->sink.begin_layer(r->sink.base.context,opacity,mode,e) : exr_fail(e,EXR_FORMAT,"Drawing consumer lacks isolated layers");
}
static exr_status end_layer_event(void *context,unsigned commit,exr_error *e) {
  pdf_painter *r=context;return r->sink.end_layer ? r->sink.end_layer(r->sink.base.context,commit,e) : exr_fail(e,EXR_FORMAT,"Drawing consumer lacks isolated layers");
}
exr_status exr_pdf_paint_content_ex(exr_pdf_file *file,uint32_t resources,const void *content,size_t size,
                                  const double initial[6],const exr_draw_sink_ex *sink,exr_pdf_program_fn program,void *program_context,
                                  size_t *work,const exr_control *control,exr_error *e) {
  pdf_painter r={0}; exr_pdf_draw_callbacks callbacks={glyph_event,path_event,state_event,image_event,begin_layer_event,end_layer_event}; size_t i,local_work=0; exr_status status;
  if(!file) return exr_fail(e,EXR_ARGUMENT,"Missing PDF paint input");
  status=exr_draw_sink_snapshot(sink,&r.sink,e);if(status!=EXR_OK) return status;
  if(!r.sink.base.path && !r.sink.base.image && !r.sink.base.clip && !r.sink.base.state) return exr_fail(e,EXR_ARGUMENT,"Missing PDF paint consumer");
  if(exr_control_cancel(control,e)!=EXR_OK) return EXR_CANCELLED;
  r.program=program; r.program_context=program_context; r.control=control; r.work=work ? work : &local_work;
  if(FT_Init_FreeType(&r.library)) return exr_fail(e,EXR_MEMORY,"PDF font library initialization failed");
  status=exr_pdf_draw_ops(file,resources,content,size,initial,&callbacks,&r,control,e);
  for(i=0;i<r.font_count;i++) exr_pdf_face_close(r.fonts[i].face);
  FT_Done_FreeType(r.library); return status;
}

exr_status exr_pdf_paint_content(exr_pdf_file *file,uint32_t resources,const void *content,size_t size,
  const double initial[6],const exr_draw_sink *sink,exr_pdf_program_fn program,void *context,size_t *work,const exr_control *control,exr_error *e) {
  exr_draw_sink_ex extended={0};if(!sink) return exr_fail(e,EXR_ARGUMENT,"Missing PDF paint consumer");
  extended.struct_size=sizeof(extended);extended.base=*sink;
  return exr_pdf_paint_content_ex(file,resources,content,size,initial,&extended,program,context,work,control,e);
}
