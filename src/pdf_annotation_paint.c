/* SPDX-License-Identifier: MIT */
#include "pdf_raster_internal.h"
typedef struct { const exr_draw_sink_ex *target; size_t depth; unsigned text; } paint_scope;
static exr_status scope_path(void *context,const exr_path_segment *path,size_t count,const double matrix[6],const exr_draw_style *style,exr_error *e) {
  paint_scope *s=context; return s->target->base.path(s->target->base.context,path,count,matrix,style,e);
}
static exr_status scope_path_cmyk(void *context,const exr_path_segment *path,size_t count,const double matrix[6],
  const exr_draw_style *style,const double fill[4],const double stroke[4],exr_error *e) {
  paint_scope *s=context; return s->target->path_cmyk(s->target->base.context,path,count,matrix,style,fill,stroke,e);
}
static exr_status scope_clip(void *context,const exr_path_segment *path,size_t count,const double matrix[6],exr_fill_rule rule,unsigned accumulate,exr_error *e) {
  paint_scope *s=context; return s->target->base.clip(s->target->base.context,path,count,matrix,rule,accumulate,e);
}
static exr_status scope_image(void *context,const exr_image_layer *image,const double matrix[6],double alpha,exr_error *e) {
  paint_scope *s=context; return s->target->base.image(s->target->base.context,image,matrix,alpha,e);
}
static exr_status scope_blend(void *context,exr_blend_mode mode,exr_error *e) {
  paint_scope *s=context;return s->target->blend(s->target->base.context,mode,e);
}
static exr_status scope_begin_layer(void *context,double opacity,exr_blend_mode mode,exr_error *e) {
  paint_scope *s=context;return s->target->begin_layer(s->target->base.context,opacity,mode,e);
}
static exr_status scope_begin_group(void *context,double opacity,exr_blend_mode mode,unsigned flags,exr_error *e) {
  paint_scope *s=context;return s->target->begin_group(s->target->base.context,opacity,mode,flags,e);
}
static exr_status scope_end_layer(void *context,unsigned commit,exr_error *e) {
  paint_scope *s=context;return s->target->end_layer(s->target->base.context,commit,e);
}
static exr_status scope_state(void *context,exr_draw_state state,exr_error *e) {
  paint_scope *s=context; exr_status status=s->target->base.state(s->target->base.context,state,e);
  if(status==EXR_OK) {
    if(state==EXR_DRAW_SAVE) s->depth++;
    else if(state==EXR_DRAW_RESTORE && s->depth) s->depth--;
    else if(state==EXR_DRAW_BEGIN_CLIP) s->text++;
    else if(state==EXR_DRAW_END_CLIP && s->text) s->text--;
  }
  return status;
}
/* A page's final clipping path must not affect its annotations. Unwind even a
   malformed stream's unmatched q/BT callbacks before leaving its outer scope. */
static exr_status scope_soft_mask(void *context,const unsigned char *mask,size_t width,size_t height,exr_error *e) {
  paint_scope *s=context;return s->target->soft_mask(s->target->base.context,mask,width,height,e);
}
static exr_status scope_extent(void *context,unsigned *width,unsigned *height,exr_error *e) {
  paint_scope *s=context;return s->target->extent(s->target->base.context,width,height,e);
}
/* The scope owns the sink context, so every optional callback needs a forwarder
   that unwraps it; copying the target's pointer directly would pass the scope as
   if it were the consumer. */
static exr_status scope_shading(void *context,const exr_bitmap *bitmap,const double matrix[6],exr_error *e) {
  paint_scope *s=context;return s->target->shading(s->target->base.context,bitmap,matrix,e);
}
static exr_status isolated(exr_pdf_file *file,uint32_t resources,const void *content,size_t size,const double matrix[6],
                             const double *box,unsigned layer,const exr_draw_sink_ex *sink,exr_pdf_program_fn program,void *context,
                             size_t *work,const exr_control *control,exr_error *e) {
  paint_scope scope={sink,0,0}; exr_draw_sink_ex consumer=*sink; exr_status status=EXR_OK;int begun=0;
  consumer.base.context=&scope; consumer.base.path=sink->base.path ? scope_path : NULL; consumer.base.clip=sink->base.clip ? scope_clip : NULL;
  consumer.base.image=sink->base.image ? scope_image : NULL; consumer.base.state=sink->base.state ? scope_state : NULL;
  consumer.blend=sink->blend ? scope_blend : NULL;
  consumer.begin_layer=sink->begin_layer ? scope_begin_layer : NULL;consumer.end_layer=sink->end_layer ? scope_end_layer : NULL;
  consumer.begin_group=sink->begin_group ? scope_begin_group : NULL;
  consumer.soft_mask=sink->soft_mask ? scope_soft_mask : NULL;consumer.extent=sink->extent ? scope_extent : NULL;
  consumer.shading=sink->shading ? scope_shading : NULL;
  consumer.path_cmyk=sink->path_cmyk ? scope_path_cmyk : NULL;
  if(sink->base.state) {
    status=sink->base.state(sink->base.context,EXR_DRAW_SAVE,e);
    if(status==EXR_OK && e && e->code!=EXR_OK) status=e->code;
    if(status!=EXR_OK) return status;
  }
  if(box && sink->base.clip) {
    exr_path_segment boundary[5]={0}; size_t i;
    const double x[4]={box[0],box[2],box[2],box[0]},y[4]={box[1],box[1],box[3],box[3]};
    for(i=0;i<4;i++) { boundary[i].verb=i ? EXR_PATH_LINE : EXR_PATH_MOVE; boundary[i].points[0]=(exr_path_point){x[i],y[i]}; }
    boundary[4].verb=EXR_PATH_CLOSE;
    status=sink->base.clip(sink->base.context,boundary,5,matrix,EXR_FILL_NONZERO,0,e);
    if(status==EXR_OK && e && e->code!=EXR_OK) status=e->code;
  }
  if(status==EXR_OK && layer) {
    /* Appearance groups depend on whole-canvas buffer semantics; keep them out of
       the region-sized working buffers until that path is reworked. */
    status=exr_sink_begin_group(sink,1,EXR_BLEND_NORMAL,
      (layer&EXR_PDF_GROUP_ISOLATED ? EXR_GROUP_ISOLATED : 0)|(layer&EXR_PDF_GROUP_KNOCKOUT ? EXR_GROUP_KNOCKOUT : 0)|
      (layer&EXR_PDF_GROUP_GRAY ? EXR_GROUP_GRAY : 0)|(layer&EXR_PDF_GROUP_CMYK ? EXR_GROUP_CMYK : 0)|
      (layer&EXR_PDF_GROUP_RGB ? EXR_GROUP_RGB : 0)|EXR_GROUP_WHOLE_BUFFER,e);
    if(status==EXR_OK) begun=1;
  }
  if(status==EXR_OK) status=exr_pdf_paint_content_ex(file,resources,content,size,matrix,&consumer,program,context,work,control,e);
  if(sink->base.state) {
    exr_error cleanup={0}; exr_status restored; size_t restore_count=scope.depth;
    while(scope.text--) {
      restored=sink->base.state(sink->base.context,EXR_DRAW_END_CLIP,&cleanup);
      if(restored==EXR_OK && cleanup.code!=EXR_OK) restored=cleanup.code;
      if(status==EXR_OK && restored!=EXR_OK) { status=restored; if(e) *e=cleanup; }
    }
    while(restore_count--) {
      memset(&cleanup,0,sizeof(cleanup));
      restored=sink->base.state(sink->base.context,EXR_DRAW_RESTORE,&cleanup);
      if(restored==EXR_OK && cleanup.code!=EXR_OK) restored=cleanup.code;
      if(status==EXR_OK && restored!=EXR_OK) { status=restored; if(e) *e=cleanup; }
    }
  }
  if(begun) {
    exr_error cleanup={0};exr_status ended=sink->end_layer(sink->base.context,status==EXR_OK,&cleanup);
    if(ended==EXR_OK && cleanup.code!=EXR_OK) ended=cleanup.code;
    if(status==EXR_OK && ended!=EXR_OK) { status=ended;if(e) *e=cleanup; }
  }
  if(sink->base.state) {
    exr_error cleanup={0};exr_status restored=sink->base.state(sink->base.context,EXR_DRAW_RESTORE,&cleanup);
    if(restored==EXR_OK && cleanup.code!=EXR_OK) restored=cleanup.code;
    if(status==EXR_OK && restored!=EXR_OK) { status=restored;if(e) *e=cleanup; }
  }
  return status;
}
static int missing(const exr_pdf_file *file,uint32_t id) {
  const exr_pdf_value *v=exr_pdf_value_at(file,id); return !v || v->kind==EXR_PDF_NULL;
}
static exr_status field(exr_pdf_file *file,uint32_t dict,const char *name,uint32_t *out,exr_error *e) {
  return exr_pdf_resolve(file,exr_pdf_get(file,dict,name),out,e);
}
static int name_is(exr_pdf_file *file,uint32_t id,const char *name) {
  const exr_pdf_value *v=exr_pdf_value_at(file,id); size_t n; const unsigned char *bytes=exr_pdf_bytes(file,id,&n);
  return v && v->kind==EXR_PDF_NAME && bytes && n==strlen(name) && !memcmp(bytes,name,n);
}
static exr_status numbers(exr_pdf_file *file,uint32_t id,double *out,size_t count,exr_error *e) {
  const exr_pdf_value *v=exr_pdf_value_at(file,id); uint32_t at; size_t i;
  if(!v || v->kind!=EXR_PDF_ARRAY) return exr_fail(e,EXR_FORMAT,"PDF annotation rectangle/matrix is not an array");
  at=v->first;
  for(i=0;i<count;i++) {
    uint32_t number,next; exr_status status;
    if(at==EXR_PDF_NONE) break;
    next=exr_pdf_value_at(file,at)->next; status=exr_pdf_resolve(file,at,&number,e); if(status!=EXR_OK) return status;
    v=exr_pdf_value_at(file,number);
    if(!v || (v->kind!=EXR_PDF_INT && v->kind!=EXR_PDF_REAL)) break;
    out[i]=v->kind==EXR_PDF_INT ? (double)v->u.integer : v->u.number;
    if(!isfinite(out[i]) || fabs(out[i])>1e7) return exr_fail(e,EXR_LIMIT,"PDF annotation coordinate exceeds budget");
    at=next;
  }
  return i==count && at==EXR_PDF_NONE ? EXR_OK : exr_fail(e,EXR_FORMAT,"Invalid PDF annotation rectangle/matrix coordinates");
}
static int multiply(double out[6],const double left[6],const double right[6]) {
  double m[6]; size_t i;
  m[0]=left[0]*right[0]+left[2]*right[1]; m[1]=left[1]*right[0]+left[3]*right[1];
  m[2]=left[0]*right[2]+left[2]*right[3]; m[3]=left[1]*right[2]+left[3]*right[3];
  m[4]=left[0]*right[4]+left[2]*right[5]+left[4]; m[5]=left[1]*right[4]+left[3]*right[5]+left[5];
  for(i=0;i<6;i++) if(!isfinite(m[i]) || fabs(m[i])>1e7) return 0;
  memcpy(out,m,sizeof(m)); return 1;
}
static exr_status appearance(exr_pdf_file *file,uint32_t annotation,uint32_t resources,const double initial[6],
                               const exr_draw_sink_ex *sink,exr_pdf_program_fn program,void *context,size_t *bytes,
                               size_t *work,const exr_control *control,exr_error *e) {
  uint32_t id,normal,value,state; const exr_pdf_value *v; exr_status status; unsigned flags=0; size_t i,size;int layer=0;
  double rect[4],box[4],matrix[6]={1,0,0,1,0,0},bounds[4]={0},fit[6]={0},transform[6]; const unsigned char *data;
  status=field(file,annotation,"F",&id,e); if(status!=EXR_OK) return status;
  if(!missing(file,id)) {
    v=exr_pdf_value_at(file,id);
    if(v->kind!=EXR_PDF_INT || v->u.integer<0 || (uint64_t)v->u.integer>UINT32_MAX) return exr_fail(e,EXR_FORMAT,"Invalid PDF annotation flags");
    flags=(unsigned)v->u.integer;
  }
  if(flags&(1u|2u|32u)) return EXR_OK;
  status=field(file,annotation,"AP",&id,e); if(status!=EXR_OK || missing(file,id)) return status;
  if(exr_pdf_value_at(file,id)->kind!=EXR_PDF_DICT) return exr_fail(e,EXR_FORMAT,"PDF annotation AP is not a dictionary");
  status=field(file,id,"N",&normal,e); if(status!=EXR_OK || missing(file,normal)) return status;
  if(exr_pdf_value_at(file,normal)->kind==EXR_PDF_DICT) {
    uint32_t at,selected=EXR_PDF_NONE; const unsigned char *name; size_t n,states=0;
    status=field(file,annotation,"AS",&state,e); if(status!=EXR_OK || missing(file,state)) return status;
    if(exr_pdf_value_at(file,state)->kind!=EXR_PDF_NAME) return exr_fail(e,EXR_FORMAT,"PDF annotation AS is not a name");
    name=exr_pdf_bytes(file,state,&n); at=exr_pdf_value_at(file,normal)->first;
    while(at!=EXR_PDF_NONE) {
      uint32_t target=exr_pdf_value_at(file,at)->next; size_t length; const unsigned char *key=exr_pdf_bytes(file,at,&length);
      if(!(states++&255) && exr_control_cancel(control,e)!=EXR_OK) return EXR_CANCELLED;
      if(target==EXR_PDF_NONE) return exr_fail(e,EXR_FORMAT,"Invalid PDF appearance state dictionary");
      if(key && length==n && !memcmp(key,name,n)) { selected=target; break; }
      at=exr_pdf_value_at(file,target)->next;
    }
    status=exr_pdf_resolve(file,selected,&normal,e); if(status!=EXR_OK || missing(file,normal)) return status;
  }
  if(exr_pdf_value_at(file,normal)->kind!=EXR_PDF_STREAM) return exr_fail(e,EXR_FORMAT,"PDF normal appearance is not a Form stream");
  if(flags&(8u|16u)) return exr_fail(e,EXR_FORMAT,"PDF NoZoom/NoRotate annotation appearances are not implemented yet");
  status=field(file,normal,"Subtype",&value,e); if(status!=EXR_OK) return status;
  if(!missing(file,value) && !name_is(file,value,"Form")) return exr_fail(e,EXR_FORMAT,"PDF appearance subtype is not Form");
  status=field(file,normal,"FormType",&value,e); if(status!=EXR_OK) return status;
  if(!missing(file,value) && (exr_pdf_value_at(file,value)->kind!=EXR_PDF_INT || exr_pdf_value_at(file,value)->u.integer!=1)) return exr_fail(e,EXR_FORMAT,"Invalid PDF appearance FormType");
  status=field(file,normal,"Group",&value,e); if(status!=EXR_OK) return status;
  status=exr_pdf_group_rgb(file,value,0,&layer,e);if(status!=EXR_OK) return status;
  status=field(file,annotation,"Rect",&value,e); if(status==EXR_OK) status=numbers(file,value,rect,4,e); if(status!=EXR_OK) return status;
  for(i=0;i<2;i++) { double a=fmin(rect[i],rect[i+2]),b=fmax(rect[i],rect[i+2]); rect[i]=a; rect[i+2]=b; }
  if(rect[0]==rect[2] || rect[1]==rect[3]) return EXR_OK;
  status=field(file,normal,"BBox",&value,e); if(status==EXR_OK) status=numbers(file,value,box,4,e); if(status!=EXR_OK) return status;
  status=field(file,normal,"Matrix",&value,e); if(status!=EXR_OK) return status;
  if(!missing(file,value)) { status=numbers(file,value,matrix,6,e); if(status!=EXR_OK) return status; }
  for(i=0;i<4;i++) {
    double x=box[i&1 ? 2 : 0],y=box[i&2 ? 3 : 1],a=matrix[0]*x+matrix[2]*y+matrix[4],b=matrix[1]*x+matrix[3]*y+matrix[5];
    if(!isfinite(a) || !isfinite(b) || fabs(a)>1e7 || fabs(b)>1e7) return exr_fail(e,EXR_LIMIT,"PDF appearance transformed bounds exceed budget");
    if(!i) { bounds[0]=bounds[2]=a; bounds[1]=bounds[3]=b; }
    else { bounds[0]=fmin(bounds[0],a); bounds[1]=fmin(bounds[1],b); bounds[2]=fmax(bounds[2],a); bounds[3]=fmax(bounds[3],b); }
  }
  if(bounds[0]==bounds[2] || bounds[1]==bounds[3]) return exr_fail(e,EXR_FORMAT,"PDF appearance has a degenerate bounding box");
  fit[0]=(rect[2]-rect[0])/(bounds[2]-bounds[0]); fit[3]=(rect[3]-rect[1])/(bounds[3]-bounds[1]);
  fit[4]=rect[0]-fit[0]*bounds[0]; fit[5]=rect[1]-fit[3]*bounds[1];
  if(!multiply(transform,fit,matrix) || !multiply(transform,initial,transform)) return exr_fail(e,EXR_LIMIT,"PDF appearance transform exceeds budget");
  status=field(file,normal,"Resources",&value,e); if(status!=EXR_OK) return status;
  if(!missing(file,value)) {
    if(exr_pdf_value_at(file,value)->kind!=EXR_PDF_DICT) return exr_fail(e,EXR_FORMAT,"PDF appearance Resources is not a dictionary");
    resources=value;
  }
  status=exr_pdf_stream_data(file,normal,&data,&size,e); if(status!=EXR_OK) return status;
  if(size>(size_t)64*1024*1024-*bytes) return exr_fail(e,EXR_LIMIT,"PDF page appearance streams exceed 64 MiB");
  *bytes+=size;
  return isolated(file,resources,data,size,transform,box,(unsigned)layer,sink,program,context,work,control,e);
}
exr_status exr_pdf_paint_page_ex(exr_pdf_file *file,const exr_pdf_page_info *page,const void *content,size_t size,
                               const double initial[6],const exr_draw_sink_ex *sink,exr_pdf_program_fn program,void *context,
                               size_t *work,const exr_control *control,exr_error *e) {
  const exr_pdf_value *v; uint32_t id,at; size_t count=0,bytes=0,local_work=0; exr_status status;
  exr_draw_sink_ex consumer;status=exr_draw_sink_snapshot(sink,&consumer,e);if(status!=EXR_OK) return status;sink=&consumer;
  if(!work) work=&local_work;
  unsigned page_flags=EXR_GROUP_ISOLATED;
  { int present;uint32_t group;
    status=exr_pdf_resolve(file,exr_pdf_get(file,page->object,"Group"),&group,e);
    if(status==EXR_OK) status=exr_pdf_group_rgb(file,group,1,&present,e);
    if(status!=EXR_OK) return status;
    page_flags|=(present&EXR_PDF_GROUP_GRAY ? EXR_GROUP_GRAY : 0)|(present&EXR_PDF_GROUP_CMYK ? EXR_GROUP_CMYK : 0)|
      (present&EXR_PDF_GROUP_RGB ? EXR_GROUP_RGB : 0);
  }
  if(sink->blend && !sink->begin_layer && !sink->begin_group) return exr_fail(e,EXR_FORMAT,"PDF blend consumer requires page layer support");
  if(sink->begin_layer || sink->begin_group) {
    status=exr_sink_begin_group(sink,1,EXR_BLEND_NORMAL,page_flags,e);
    if(status==EXR_OK && e && e->code!=EXR_OK) status=e->code;
    if(status!=EXR_OK) return status;
  }
  status=isolated(file,page->resources,content,size,initial,NULL,0,sink,program,context,work,control,e);
  if(sink->end_layer) {
    exr_error cleanup={0};exr_status ended=sink->end_layer(sink->base.context,status==EXR_OK,&cleanup);
    if(ended==EXR_OK && cleanup.code!=EXR_OK) ended=cleanup.code;
    if(status==EXR_OK && ended!=EXR_OK) { status=ended;if(e) *e=cleanup; }
  }
  if(status!=EXR_OK) return status;
  status=exr_pdf_resolve(file,page->annotations,&id,e); if(status!=EXR_OK || missing(file,id)) return status;
  v=exr_pdf_value_at(file,id); if(v->kind!=EXR_PDF_ARRAY) return exr_fail(e,EXR_FORMAT,"PDF Annots is not an array");
  at=v->first;
  while(at!=EXR_PDF_NONE) {
    uint32_t next=exr_pdf_value_at(file,at)->next,annotation;
    if(count++==4096) return exr_fail(e,EXR_LIMIT,"PDF page exceeds 4096 annotations");
    status=exr_control_poll(control,EXR_STAGE_RENDER,count,0,e); if(status!=EXR_OK) return status;
    status=exr_pdf_resolve(file,at,&annotation,e); if(status!=EXR_OK) return status;
    if(!missing(file,annotation)) {
      if(exr_pdf_value_at(file,annotation)->kind!=EXR_PDF_DICT) return exr_fail(e,EXR_FORMAT,"PDF annotation is not a dictionary");
      status=appearance(file,annotation,page->resources,initial,sink,program,context,&bytes,work,control,e); if(status!=EXR_OK) return status;
    }
    at=next;
  }
  return EXR_OK;
}

exr_status exr_pdf_paint_page(exr_pdf_file *file,const exr_pdf_page_info *page,const void *content,size_t size,
  const double initial[6],const exr_draw_sink *sink,exr_pdf_program_fn program,void *context,size_t *work,const exr_control *control,exr_error *e) {
  exr_draw_sink_ex extended={0};if(!sink) return exr_fail(e,EXR_ARGUMENT,"Missing PDF page consumer");
  extended.struct_size=sizeof(extended);extended.base=*sink;
  return exr_pdf_paint_page_ex(file,page,content,size,initial,&extended,program,context,work,control,e);
}
