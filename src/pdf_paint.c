/* SPDX-License-Identifier: MIT */
#include "pdf_raster_internal.h"
#include "pdf_face_internal.h"
#include "icc_internal.h"
#include <stdio.h>
typedef struct { const exr_pdf_font *key; exr_pdf_face *face; } paint_face;
typedef struct { unsigned char *pixels;size_t bytes; } paint_mask;
typedef struct {
  exr_draw_sink_ex sink; FT_Library library; exr_pdf_program_fn program; void *program_context; const exr_control *control; size_t *work;
  exr_icc *cmyk_profile;
  exr_pdf_file *file; /* mask rendering needs the object arena */
  size_t font_count,font_bytes; paint_face fonts[128];
  paint_mask group_masks[32];size_t group_depth,*mask_bytes;
} pdf_painter;
static uint32_t rgba(pdf_painter *paint,const exr_pdf_color *c,unsigned intent) {
  unsigned r,g,b,a=(unsigned)floor(c->alpha*255+.5);
  if(c->space==EXR_PDF_DEVICE_GRAY) r=g=b=(unsigned)floor(c->values[0]*255+.5);
  else if(c->space==EXR_PDF_DEVICE_RGB) { r=(unsigned)floor(c->values[0]*255+.5); g=(unsigned)floor(c->values[1]*255+.5); b=(unsigned)floor(c->values[2]*255+.5); }
  else { double rgb[3];exr_device_cmyk_rgb(paint->cmyk_profile,c->values,rgb,intent);
    r=(unsigned)floor(rgb[0]*255+.5);g=(unsigned)floor(rgb[1]*255+.5);b=(unsigned)floor(rgb[2]*255+.5); }
  return (r<<24)|(g<<16)|(b<<8)|a;
}
static void cmyk_color(exr_icc *profile,const exr_pdf_color *c,double out[4]) {
  double rgb[3];unsigned k;
  if(c->space==EXR_PDF_DEVICE_CMYK) { for(k=0;k<4;k++) out[k]=c->values[k];return; }
  if(c->space==EXR_PDF_DEVICE_GRAY) rgb[0]=rgb[1]=rgb[2]=c->values[0];
  else if(c->space==EXR_PDF_DEVICE_RGB) { for(k=0;k<3;k++) rgb[k]=c->values[k]; }
  else for(k=0;k<3;k++) rgb[k]=1-fmin(1,c->values[k]+c->values[3]);
  exr_device_cmyk_from_rgb(profile,rgb,out);
}
static void multiply(const double a[6],const double b[6],double out[6]) {
  out[0]=a[0]*b[0]+a[2]*b[1]; out[1]=a[1]*b[0]+a[3]*b[1];
  out[2]=a[0]*b[2]+a[2]*b[3]; out[3]=a[1]*b[2]+a[3]*b[3];
  out[4]=a[0]*b[4]+a[2]*b[5]+a[4]; out[5]=a[1]*b[4]+a[3]*b[5]+a[5];
}
/* ISO 32000-1 11.6.5.2: the mask applies to each painted element. It is rebuilt
   per element for now; caching waits for the scene matrix to settle. */
static exr_status mask_begin(pdf_painter *r,const exr_pdf_paint_state *paint,paint_mask *mask,exr_error *e) {
  unsigned width=0,height=0; exr_status status;
  memset(mask,0,sizeof(*mask));
  if(paint->smask==EXR_PDF_NONE) return EXR_OK;
  status=exr_sink_extent(&r->sink,&width,&height,e); if(status!=EXR_OK) return status;
  if(!width || !height || width>(size_t)64*1024*1024/height || *r->mask_bytes>(size_t)64*1024*1024 ||
      (size_t)width*height>(size_t)64*1024*1024-*r->mask_bytes)
    return exr_fail(e,EXR_LIMIT,"PDF active soft masks exceed 64 MiB");
  mask->bytes=(size_t)width*height;*r->mask_bytes+=mask->bytes;
  status=exr_pdf_soft_mask_build(r->file,paint->smask,paint->smask_matrix,width,height,&mask->pixels,r->work,r->mask_bytes,r->control,e);
  if(status!=EXR_OK) { *r->mask_bytes-=mask->bytes;mask->bytes=0;return status; }
  return exr_sink_soft_mask(&r->sink,mask->pixels,width,height,e);
}
static exr_status mask_end(pdf_painter *r,paint_mask *mask,exr_status prior,exr_error *e) {
  exr_status status=EXR_OK;
  exr_error cleanup={0};
  if(mask->pixels) status=exr_sink_soft_mask(&r->sink,NULL,0,0,prior==EXR_OK ? e : &cleanup);
  *r->mask_bytes-=mask->bytes;free(mask->pixels);memset(mask,0,sizeof(*mask));
  return prior==EXR_OK ? status : prior;
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
  exr_draw_style style=exr_draw_style_defaults(); exr_status status=EXR_OK; paint_mask mask={0}; int painting;
  int native_cmyk=paint->fill.space==EXR_PDF_DEVICE_CMYK || paint->stroke.space==EXR_PDF_DEVICE_CMYK;
  if((native_cmyk || (r->sink.path_cmyk && !r->sink.base.path)) && !r->cmyk_profile) {
    status=exr_icc_default_cmyk(r->control,&r->cmyk_profile,e);if(status!=EXR_OK) return status;
  }
  style.fill=rgba(r,&paint->fill,paint->intent); style.stroke=rgba(r,&paint->stroke,paint->intent); style.flags=flags&3; style.rule=rule;
  style.line=paint->line; style.dashes=paint->dashes; style.dash_count=paint->dash_count; style.dash_phase=paint->dash_phase; style.stroke_matrix=paint->matrix;
  painting=(style.flags!=0)&&(r->sink.base.path||r->sink.path_cmyk);
  if(painting) status=blend_state(r,paint->blend,e);
  if(status==EXR_OK && painting) status=mask_begin(r,paint,&mask,e);
  if(status==EXR_OK && painting) {
    if(r->sink.path_cmyk && (native_cmyk || !r->sink.base.path)) {
      double fill[4],stroke[4];cmyk_color(r->cmyk_profile,&paint->fill,fill);cmyk_color(r->cmyk_profile,&paint->stroke,stroke);
      status=r->sink.path_cmyk(r->sink.base.context,segments,count,transform,&style,fill,stroke,e);
    } else status=r->sink.base.path(r->sink.base.context,segments,count,transform,&style,e);
  }
  if(mask.pixels) status=mask_end(r,&mask,status,e);
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
  exr_bitmap inks={0};int native=r->sink.image_cmyk && (!r->sink.image_space || r->sink.image_space(r->sink.base.context)==EXR_GROUP_CMYK);
  exr_pdf_paint_state image_paint=*paint;uint32_t own_mask;const exr_pdf_value *v;
  exr_status status; paint_mask mask={0}; if(!r->sink.base.image && !native) return EXR_OK;
  if(paint->fill.space==EXR_PDF_DEVICE_CMYK && !r->cmyk_profile) { status=exr_icc_default_cmyk(r->control,&r->cmyk_profile,e);if(status!=EXR_OK) return status; }
  status=exr_pdf_image_load_inks(file,id,resource_file,resources,rgba(r,&paint->fill,paint->intent),paint->intent,&image,native ? &inks : NULL,r->work,r->control,e);
  multiply(paint->matrix,flip,matrix);
  if(status==EXR_OK) status=blend_state(r,paint->blend,e);
  /* ISO 32000-1 11.6.4.3: either image mask overrides the graphics-state mask. */
  if(status==EXR_OK) {
    status=exr_pdf_resolve(file,exr_pdf_get(file,id,"SMask"),&own_mask,e);
    v=exr_pdf_value_at(file,own_mask);
    if(status==EXR_OK && v && v->kind==EXR_PDF_STREAM) image_paint.smask=EXR_PDF_NONE;
    else if(status==EXR_OK) {
      status=exr_pdf_resolve(file,exr_pdf_get(file,id,"Mask"),&own_mask,e);
      v=exr_pdf_value_at(file,own_mask);
      if(status==EXR_OK && v && (v->kind==EXR_PDF_STREAM || v->kind==EXR_PDF_ARRAY)) image_paint.smask=EXR_PDF_NONE;
    }
  }
  if(status==EXR_OK) status=mask_begin(r,&image_paint,&mask,e);
  if(status==EXR_OK && inks.pixels) status=r->sink.image_cmyk(r->sink.base.context,image,&inks,matrix,paint->fill.alpha,e);
  else if(status==EXR_OK && r->sink.base.image) status=r->sink.base.image(r->sink.base.context,image,matrix,paint->fill.alpha,e);
  else if(status==EXR_OK) status=exr_fail(e,EXR_UNSUPPORTED,"Drawing consumer lacks RGB image support");
  if(mask.pixels) status=mask_end(r,&mask,status,e);
  exr_pdf_image_release(image);free(inks.pixels); return status;
}
static unsigned image_space(void *context) {
  pdf_painter *r=context;
  return r->sink.image_cmyk && (!r->sink.image_space || r->sink.image_space(r->sink.base.context)==EXR_GROUP_CMYK) ? EXR_GROUP_CMYK : EXR_GROUP_RGB;
}
static exr_status begin_group_event(void *context,const exr_pdf_paint_state *paint,unsigned flags,exr_error *e) {
  pdf_painter *r=context;paint_mask mask={0};exr_status status;
  if(r->group_depth==32) return exr_fail(e,EXR_LIMIT,"PDF paint group mask depth exceeds 32");
  status=mask_begin(r,paint,&mask,e);
  if(status==EXR_OK) status=exr_sink_begin_group(&r->sink,paint->fill.alpha,paint->blend,flags,e);
  if(status==EXR_OK) r->group_masks[r->group_depth++]=mask;
  else if(mask.pixels) status=mask_end(r,&mask,status,e);
  return status;
}
static exr_status shading_event(void *context,const exr_bitmap *bitmap,const exr_bitmap *inks,const double matrix[6],
                               const exr_pdf_paint_state *paint,exr_error *e) {
  pdf_painter *r=context;
  exr_status status;paint_mask mask={0};int begun=0;
  if(!r->sink.shading && !(inks && r->sink.image_cmyk)) return exr_fail(e,EXR_UNSUPPORTED,"Drawing consumer does not support PDF shadings");
  if(paint->fill.alpha!=1) {
    status=exr_sink_begin_group(&r->sink,paint->fill.alpha,paint->blend,EXR_GROUP_ISOLATED,e);
    if(status!=EXR_OK) return status;
    begun=1;
  }
  status=blend_state(r,begun ? EXR_BLEND_NORMAL : paint->blend,e);
  if(status==EXR_OK) status=mask_begin(r,paint,&mask,e);
  if(status==EXR_OK && inks && r->sink.image_cmyk) {
    exr_image_layer layer={0};layer.bitmap=*bitmap;layer.interpolate=1;
    status=r->sink.image_cmyk(r->sink.base.context,&layer,inks,matrix,1,e);
  } else if(status==EXR_OK) status=r->sink.shading(r->sink.base.context,bitmap,matrix,e);
  if(mask.pixels) status=mask_end(r,&mask,status,e);
  if(begun) { exr_error cleanup={0};exr_status closed=r->sink.end_layer(r->sink.base.context,status==EXR_OK,status==EXR_OK ? e : &cleanup);if(status==EXR_OK) status=closed; }
  return status;
}
static exr_status end_layer_event(void *context,unsigned commit,exr_error *e) {
  pdf_painter *r=context;paint_mask mask;exr_status status;
  if(!r->group_depth) return exr_fail(e,EXR_FORMAT,"PDF paint group stack underflow");
  mask=r->group_masks[--r->group_depth];memset(r->group_masks+r->group_depth,0,sizeof(mask));
  status=r->sink.end_layer ? r->sink.end_layer(r->sink.base.context,commit,e) : exr_fail(e,EXR_FORMAT,"Drawing consumer lacks isolated layers");
  return mask.pixels ? mask_end(r,&mask,status,e) : status;
}
exr_status exr_pdf_paint_content_ex(exr_pdf_file *file,uint32_t resources,const void *content,size_t size,
                                  const double initial[6],const exr_draw_sink_ex *sink,exr_pdf_program_fn program,void *program_context,
                                  size_t *work,size_t *mask_bytes,const exr_control *control,exr_error *e) {
  pdf_painter r={0}; exr_pdf_draw_callbacks callbacks={glyph_event,path_event,state_event,image_event,shading_event,begin_group_event,end_layer_event,image_space}; size_t i,local_work=0,local_mask_bytes=0; exr_status status;
  if(!file) return exr_fail(e,EXR_ARGUMENT,"Missing PDF paint input");
  status=exr_draw_sink_snapshot(sink,&r.sink,e);if(status!=EXR_OK) return status;
  if(!r.sink.base.path && !r.sink.base.image && !r.sink.base.clip && !r.sink.base.state && !r.sink.image_cmyk && !r.sink.path_cmyk && !r.sink.shading) return exr_fail(e,EXR_ARGUMENT,"Missing PDF paint consumer");
  if(exr_control_cancel(control,e)!=EXR_OK) return EXR_CANCELLED;
  r.program=program; r.program_context=program_context; r.control=control; r.work=work ? work : &local_work; r.file=file;r.mask_bytes=mask_bytes ? mask_bytes : &local_mask_bytes;
  if(FT_Init_FreeType(&r.library)) return exr_fail(e,EXR_MEMORY,"PDF font library initialization failed");
  status=exr_pdf_draw_ops(file,resources,content,size,initial,&callbacks,&r,control,e);
  while(r.group_depth) { exr_error cleanup={0};exr_status closed=end_layer_event(&r,0,&cleanup);if(status==EXR_OK && closed!=EXR_OK) { status=closed;if(e) *e=cleanup; } }
  for(i=0;i<r.font_count;i++) exr_pdf_face_close(r.fonts[i].face);
  if(status==EXR_OK) status=exr_icc_deferred_status(r.cmyk_profile,e);
  exr_icc_free(r.cmyk_profile);FT_Done_FreeType(r.library); return status;
}

exr_status exr_pdf_paint_content(exr_pdf_file *file,uint32_t resources,const void *content,size_t size,
  const double initial[6],const exr_draw_sink *sink,exr_pdf_program_fn program,void *context,size_t *work,const exr_control *control,exr_error *e) {
  exr_draw_sink_ex extended={0};if(!sink) return exr_fail(e,EXR_ARGUMENT,"Missing PDF paint consumer");
  extended.struct_size=sizeof(extended);extended.base=*sink;
  return exr_pdf_paint_content_ex(file,resources,content,size,initial,&extended,program,context,work,NULL,control,e);
}
