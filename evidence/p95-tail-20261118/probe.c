/* SPDX-License-Identifier: MIT */
/* Single-threaded attribution shim for a MinGW relink of the benchmark objects. */
#include "pdf_raster_internal.h"
#include "pdf_face_internal.h"
#include "canvas_internal.h"
#include "pdf_file_layout.h" /* Generated verbatim from pdf_objects.c by capture.py. */
#include <windows.h>

enum { FULL, IMAGES, PATHS, TEXT, GROUPS, SHADING, CLIP };
typedef struct {
  size_t font_hits, font_misses, font_evictions, font_entries, font_bytes;
  size_t font_opens, face_opens, clip_calls, mask_builds, draw_walks;
  size_t reader_changes, clip_allocations, clip_reuses, clip_fast;
  double mask_ms;
} page_trace;

static int mode, tracing;
static page_trace trace;
static exr_pdf_file *document_file;
static exr_pdf_path_fn original_path;
static exr_pdf_text_fn original_glyph;
static exr_draw_clip_fn original_clip;

__declspec(dllexport) void tail_begin(int variant, int collect) {
  mode=variant;
  tracing=collect;
  memset(&trace,0,sizeof(trace));
}
__declspec(dllexport) void tail_read(page_trace *page,exr_pdf_image_cache_stats *images) {
  *page=trace;
  exr_pdf_image_cache_report(document_file,images);
}
__declspec(dllexport) void tail_document(void) { document_file=NULL; }

static exr_status no_image(void *ctx,exr_pdf_file *f,uint32_t id,exr_pdf_file *rf,uint32_t res,
                           const exr_pdf_paint_state *p,exr_error *e) { return EXR_OK; }
static exr_status no_path(void *ctx,const exr_pdf_path_paint *path,exr_error *e) {
  exr_pdf_path_paint p=*path;
  p.flags&=EXR_PDF_CLIP;
  return p.flags ? original_path(ctx,&p,e) : EXR_OK;
}
static exr_status no_text(void *ctx,const exr_pdf_text_glyph *glyph,exr_error *e) {
  if(glyph->rendering_mode<4) return EXR_OK;
  exr_pdf_text_glyph g=*glyph;
  g.rendering_mode=7;
  return original_glyph(ctx,&g,e);
}
extern __typeof__(exr_pdf_draw_ops) __real_exr_pdf_draw_ops;
exr_status __wrap_exr_pdf_draw_ops(exr_pdf_file *f,uint32_t res,const void *data,size_t size,
                                  const double m[6],const exr_pdf_draw_callbacks *callbacks,void *ctx,
                                  const exr_control *control,exr_error *e) {
  if(tracing) trace.draw_walks++;
  if(mode!=IMAGES && mode!=PATHS && mode!=TEXT)
    return __real_exr_pdf_draw_ops(f,res,data,size,m,callbacks,ctx,control,e);
  exr_pdf_draw_callbacks c=*callbacks;
  exr_pdf_path_fn previous_path=original_path;
  exr_pdf_text_fn previous_glyph=original_glyph;
  if(mode==IMAGES && c.image) c.image=no_image;
  if(mode==PATHS && c.path) { original_path=c.path; c.path=no_path; }
  if(mode==TEXT && c.glyph) { original_glyph=c.glyph; c.glyph=no_text; }
  exr_status status=__real_exr_pdf_draw_ops(f,res,data,size,m,&c,ctx,control,e);
  original_path=previous_path;
  original_glyph=previous_glyph;
  return status;
}
extern __typeof__(exr_pdf_shading_draw) __real_exr_pdf_shading_draw;
exr_status __wrap_exr_pdf_shading_draw(exr_pdf_file *f,exr_pdf_file *rf,uint32_t res,uint32_t id,
  const double m[6],const exr_pdf_paint_state *p,size_t *work,exr_pdf_shading_fn emit,
  exr_pdf_source_fn source,void *ctx,unsigned cmyk,const exr_control *control,exr_error *e) {
  if(mode==SHADING) return EXR_OK;
  return __real_exr_pdf_shading_draw(f,rf,res,id,m,p,work,emit,source,ctx,cmyk,control,e);
}

static exr_status no_group(void *ctx,double opacity,exr_blend_mode blend,unsigned flags,exr_error *e) {
  return EXR_OK;
}
static exr_status no_layer(void *ctx,double opacity,exr_blend_mode blend,exr_error *e) { return EXR_OK; }
static exr_status no_end(void *ctx,unsigned commit,exr_error *e) { return EXR_OK; }

static void classify_clip(exr_clip_mask *mask,exr_clip_mask *old,exr_clip_mask *const spare[4]) {
  trace.clip_calls++;
  if(!mask || mask==old) { trace.clip_fast++; return; }
  for(size_t i=0;i<4;i++) {
    if(mask==spare[i]) { trace.clip_reuses++; return; }
  }
  trace.clip_allocations++;
}
static exr_status probe_clip(void *ctx,const exr_path_segment *p,size_t n,const double m[6],
                              exr_fill_rule rule,unsigned accumulate,exr_error *e) {
  if(mode==CLIP) return EXR_OK;
  exr_canvas *c=ctx;
  exr_clip_mask *old=accumulate ? c->group : c->clip;
  exr_clip_mask *spare[4];
  memcpy(spare,c->spare_masks,sizeof(spare));
  exr_status status=original_clip(ctx,p,n,m,rule,accumulate,e);
  if(status==EXR_OK) classify_clip(accumulate ? c->group : c->clip,old,spare);
  return status;
}
extern __typeof__(exr_canvas_clip) __real_exr_canvas_clip;
exr_status __wrap_exr_canvas_clip(exr_canvas *c,const exr_path_segment *p,size_t n,const double m[6],
                                   exr_fill_rule rule,exr_error *e) {
  if(!tracing) return __real_exr_canvas_clip(c,p,n,m,rule,e);
  exr_clip_mask *old=c->clip;
  exr_clip_mask *spare[4];
  memcpy(spare,c->spare_masks,sizeof(spare));
  exr_status status=__real_exr_canvas_clip(c,p,n,m,rule,e);
  if(status==EXR_OK) classify_clip(c->clip,old,spare);
  return status;
}
extern __typeof__(exr_canvas_get_sink_ex) __real_exr_canvas_get_sink_ex;
exr_status __wrap_exr_canvas_get_sink_ex(exr_canvas *c,exr_draw_sink_ex *sink,exr_error *e) {
  exr_status status=__real_exr_canvas_get_sink_ex(c,sink,e);
  if(status!=EXR_OK) return status;
  if(tracing || mode==CLIP) { original_clip=sink->base.clip; sink->base.clip=probe_clip; }
  if(mode==GROUPS) { sink->begin_group=no_group; sink->begin_layer=no_layer; sink->end_layer=no_end; }
  return status;
}

extern __typeof__(exr_pdf_stream_data_retained) __real_exr_pdf_stream_data_retained;
exr_status __wrap_exr_pdf_stream_data_retained(exr_pdf_file *f,uint32_t id,const unsigned char **data,
                                              size_t *size,exr_error *e) {
  uint32_t resolved;
  if(tracing && exr_pdf_resolve(f,id,&resolved,e)==EXR_OK) {
    const exr_pdf_value *value=exr_pdf_value_at(f,resolved);
    if(value && value->kind==EXR_PDF_STREAM && value->u.ref.object<f->stream_count &&
       f->streams[value->u.ref.object].ready) trace.font_hits++;
    else trace.font_misses++;
  }
  return __real_exr_pdf_stream_data_retained(f,id,data,size,e);
}
extern __typeof__(exr_pdf_operation_end) __real_exr_pdf_operation_end;
void __wrap_exr_pdf_operation_end(exr_pdf_file *f) {
  size_t before=0;
  if(document_file && document_file!=f && tracing) trace.reader_changes++;
  document_file=f;
  if(tracing)
    for(size_t i=0;i<f->stream_count;i++) before+=f->streams[i].retain && f->streams[i].ready;
  __real_exr_pdf_operation_end(f);
  if(tracing) {
    for(size_t i=0;i<f->stream_count;i++) trace.font_entries+=f->streams[i].retain && f->streams[i].ready;
    trace.font_bytes=f->decoded_bytes;
    trace.font_evictions+=before-trace.font_entries;
  }
}
extern __typeof__(exr_pdf_font_open) __real_exr_pdf_font_open;
exr_status __wrap_exr_pdf_font_open(exr_pdf_file *f,uint32_t id,const exr_control *control,
                                     exr_pdf_font **font,exr_error *e) {
  if(tracing) trace.font_opens++;
  return __real_exr_pdf_font_open(f,id,control,font,e);
}
extern __typeof__(exr_pdf_face_open_shared) __real_exr_pdf_face_open_shared;
exr_status __wrap_exr_pdf_face_open_shared(FT_Library lib,const exr_pdf_font *font,const exr_font_input *fallback,
  const exr_pdf_face *shared,exr_pdf_face **out,const exr_control *control,exr_error *e) {
  if(tracing) trace.face_opens++;
  return __real_exr_pdf_face_open_shared(lib,font,fallback,shared,out,control,e);
}
extern __typeof__(exr_pdf_soft_mask_build) __real_exr_pdf_soft_mask_build;
exr_status __wrap_exr_pdf_soft_mask_build(exr_pdf_file *f,uint32_t id,const double m[6],unsigned w,
  unsigned h,unsigned char **out,size_t *work,size_t *active,const exr_control *control,exr_error *e) {
  if(!tracing) return __real_exr_pdf_soft_mask_build(f,id,m,w,h,out,work,active,control,e);
  LARGE_INTEGER start,end,freq;
  QueryPerformanceCounter(&start);
  exr_status status=__real_exr_pdf_soft_mask_build(f,id,m,w,h,out,work,active,control,e);
  QueryPerformanceCounter(&end);
  QueryPerformanceFrequency(&freq);
  trace.mask_builds++;
  trace.mask_ms+=(double)(end.QuadPart-start.QuadPart)*1000/(double)freq.QuadPart;
  return status;
}
