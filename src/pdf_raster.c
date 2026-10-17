/* SPDX-License-Identifier: GPL-3.0-only */
#include "pdf_raster_internal.h"
#include "pdf_face_internal.h"
#include "canvas_internal.h"
typedef struct { const exr_pdf_font *key; exr_pdf_face *face; } raster_face;
typedef struct {
  exr_canvas *canvas; FT_Library library; const exr_pdf_raster_config *config; const exr_control *control;
  size_t font_count,font_bytes; raster_face fonts[128];
} pdf_raster;
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
static exr_status geometry(pdf_raster *r,const exr_vector_segment *segments,size_t count,const double transform[6],
                             const exr_pdf_paint_state *paint,unsigned flags,exr_vector_rule rule,int text_clip,exr_error *e) {
  exr_draw_style style=exr_draw_style_defaults(); exr_status status=EXR_OK;
  style.fill=rgba(&paint->fill); style.stroke=rgba(&paint->stroke); style.flags=flags&3; style.rule=rule;
  style.line=paint->line; style.dashes=paint->dashes; style.dash_count=paint->dash_count; style.dash_phase=paint->dash_phase; style.stroke_matrix=paint->matrix;
  if(style.flags) status=exr_canvas_path(r->canvas,segments,count,transform,&style,e);
  if(status==EXR_OK && (flags&EXR_PDF_CLIP)) status=text_clip ?
    exr_canvas_union_add(r->canvas,segments,count,transform,rule,e) : exr_canvas_clip(r->canvas,segments,count,transform,rule,e);
  return status;
}
static exr_status path_event(void *context,const exr_pdf_path_paint *p,exr_error *e) {
  return geometry(context,p->segments,p->count,NULL,&p->paint,p->flags,p->rule,0,e);
}
static exr_status state_event(void *context,exr_pdf_state_event event,exr_error *e) {
  pdf_raster *r=context;
  if(event==EXR_PDF_SAVE) return exr_canvas_save(r->canvas,e);
  if(event==EXR_PDF_RESTORE) return exr_canvas_restore(r->canvas,e);
  if(event==EXR_PDF_BEGIN_TEXT) exr_canvas_union_abort(r->canvas);
  if(event==EXR_PDF_END_TEXT) return exr_canvas_union_commit(r->canvas,e);
  return EXR_OK;
}
static exr_status glyph_event(void *context,const exr_pdf_text_glyph *g,exr_error *e) {
  pdf_raster *r=context; size_t i,count=0; exr_status status; exr_vector_segment *segments=NULL; unsigned flags=0,mode=g->rendering_mode;
  if(mode==3) return EXR_OK;
  if(mode==0 || mode==2 || mode==4 || mode==6) flags|=EXR_PDF_FILL;
  if(mode==1 || mode==2 || mode==5 || mode==6) flags|=EXR_PDF_STROKE;
  if(mode>=4) flags|=EXR_PDF_CLIP;
  for(i=0;i<r->font_count;i++) if(r->fonts[i].key==g->font) break;
  if(i==r->font_count) {
    const exr_pdf_font_info *info=exr_pdf_font_description(g->font); const void *fallback=NULL; size_t size=0,bytes;
    if(i==128) return exr_fail(e,EXR_LIMIT,"PDF raster face cache exceeds 128 fonts");
    if(!info->program && r->config->program) { status=r->config->program(r->config->context,info,&fallback,&size,e); if(status!=EXR_OK) return status; }
    status=exr_pdf_face_open(r->library,g->font,fallback,size,&r->fonts[i].face,r->control,e); if(status!=EXR_OK) return status;
    r->fonts[i].key=g->font; r->font_count++; bytes=exr_pdf_face_memory(r->fonts[i].face);
    if(bytes>(size_t)32*1024*1024-r->font_bytes) return exr_fail(e,EXR_LIMIT,"PDF raster CID indexes exceed 32 MiB");
    r->font_bytes+=bytes;
  }
  status=exr_pdf_face_outline(r->fonts[i].face,&g->character,&segments,&count,&r->canvas->work,r->control,e);
  if(status==EXR_OK) status=geometry(r,segments,count,g->transform,&g->paint,flags,EXR_VECTOR_NONZERO,1,e);
  free(segments); return status;
}
static exr_status image_event(void *context,exr_pdf_file *file,uint32_t id,uint32_t resources,const exr_pdf_paint_state *paint,exr_error *e) {
  pdf_raster *r=context; exr_vector_texture *image=NULL; double matrix[6]; const double flip[6]={1,0,0,-1,0,1};
  exr_status status=exr_pdf_image_load(file,id,resources,rgba(&paint->fill),&image,&r->canvas->work,r->control,e);
  multiply(paint->matrix,flip,matrix);
  if(status==EXR_OK) status=exr_canvas_image(r->canvas,image,matrix,paint->fill.alpha,e);
  exr_pdf_image_release(image); return status;
}
exr_status exr_pdf_raster_content(exr_pdf_file *file,uint32_t resources,const void *content,size_t size,
                                   const double initial[6],const exr_pdf_raster_config *config,
                                   const exr_control *control,exr_bitmap *out,exr_error *e) {
  pdf_raster r={0}; exr_canvas_config settings={0}; exr_pdf_draw_callbacks cb={glyph_event,path_event,state_event,image_event}; exr_status status; size_t i;
  if(out) memset(out,0,sizeof(*out));
  if(!out || !file || !config || (!content && size) || !config->width || !config->height || config->width>16384 || config->height>16384 ||
     (config->channels!=1 && config->channels!=4) || config->width>(size_t)64*1024*1024/config->channels/config->height)
    return exr_fail(e,EXR_ARGUMENT,"Invalid PDF raster output configuration");
  if(exr_control_cancel(control,e)!=EXR_OK) return EXR_CANCELLED;
  if(config->initial_clip) {
    const double *b=config->initial_clip;
    for(i=0;i<4;i++) if(!isfinite(b[i]) || fabs(b[i])>1e7) return exr_fail(e,EXR_ARGUMENT,"Invalid initial PDF raster clip");
    if(b[0]>b[2] || b[1]>b[3]) return exr_fail(e,EXR_ARGUMENT,"Inverted initial PDF raster clip");
  }
  r.config=config; r.control=control;
  settings.width=config->width; settings.height=config->height; settings.channels=config->channels; settings.background=config->background; settings.mask_budget=config->mask_budget;
  if(control) settings.control=*control;
  status=exr_canvas_create(&settings,&r.canvas,e); if(status!=EXR_OK) return status;
  if(config->initial_clip) {
    const double *b=config->initial_clip; exr_path_segment rect[5]={0};
    rect[0].verb=EXR_PATH_MOVE; rect[0].points[0]=(exr_path_point){b[0],b[1]};
    rect[1].verb=EXR_PATH_LINE; rect[1].points[0]=(exr_path_point){b[2],b[1]};
    rect[2].verb=EXR_PATH_LINE; rect[2].points[0]=(exr_path_point){b[2],b[3]};
    rect[3].verb=EXR_PATH_LINE; rect[3].points[0]=(exr_path_point){b[0],b[3]}; rect[4].verb=EXR_PATH_CLOSE;
    status=exr_canvas_clip(r.canvas,rect,5,NULL,EXR_FILL_NONZERO,e); if(status!=EXR_OK) goto done;
  }
  if(FT_Init_FreeType(&r.library)) { status=exr_fail(e,EXR_MEMORY,"PDF font library initialization failed"); goto done; }
  status=exr_pdf_draw_ops(file,resources,content,size,initial,&cb,&r,control,e);
  if(status==EXR_OK) status=exr_canvas_take(r.canvas,out,e);
done:
  for(i=0;i<r.font_count;i++) exr_pdf_face_close(r.fonts[i].face);
  if(r.library) FT_Done_FreeType(r.library);
  exr_canvas_free(r.canvas); return status;
}
