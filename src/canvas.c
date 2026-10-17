/* SPDX-License-Identifier: GPL-3.0-only */
#include "canvas_internal.h"
static exr_status finish(exr_canvas *c,exr_status status,exr_error *e) {
  if(c && status!=EXR_OK && c->failure.code==EXR_OK) {
    if(e) c->failure=*e;
    c->failure.code=status;
    if(!c->failure.message[0]) snprintf(c->failure.message,sizeof(c->failure.message),"Canvas operation failed");
  }
  if(c && c->failure.code!=EXR_OK) { if(e) *e=c->failure; return c->failure.code; }
  return status==EXR_OK ? exr_fail(e,EXR_OK,"") : status;
}
static exr_status ready(exr_canvas *c,exr_error *e) {
  if(!c || !c->bitmap.pixels) return exr_fail(e,EXR_ARGUMENT,"Missing or consumed canvas");
  if(c->failure.code!=EXR_OK) { if(e) *e=c->failure; return c->failure.code; }
  return finish(c,exr_control_cancel(&c->control,e),e);
}
static void unref(exr_canvas *c,exr_clip_mask *mask) {
  if(mask && !--mask->refs) { c->mask_bytes-=(size_t)mask->bitmap.stride*mask->bitmap.height; c->mask_count--; free(mask->bitmap.pixels); free(mask); }
}
static exr_status new_mask(exr_canvas *c,exr_clip_mask **out,exr_error *e) {
  size_t bytes=(size_t)c->bitmap.width*c->bitmap.height; exr_clip_mask *mask;
  *out=NULL;
  if(bytes>c->mask_budget-c->mask_bytes) return exr_fail(e,EXR_LIMIT,"Canvas clip masks exceed byte budget");
  mask=calloc(1,sizeof(*mask)); if(!mask) return exr_fail(e,EXR_MEMORY,"Canvas clip mask allocation failed");
  mask->bitmap=c->bitmap; mask->bitmap.channels=1; mask->bitmap.stride=c->bitmap.width; mask->bitmap.pixels=calloc(bytes,1);
  if(!mask->bitmap.pixels) { free(mask); return exr_fail(e,EXR_MEMORY,"Canvas clip pixel allocation failed"); }
  mask->refs=1; c->mask_bytes+=bytes; c->mask_count++; *out=mask; return EXR_OK;
}
static exr_status fill(exr_canvas *c,const exr_vector_polyline *path,exr_fill_rule rule,uint32_t color,
                         exr_bitmap *target,const exr_clip_mask *clip,exr_error *e) {
  exr_vector_edge *edges=NULL; size_t count=0; exr_status status=exr_vector_edges(path,1,&edges,&count,&c->work,&c->control,e);
  if(status==EXR_OK) status=exr_vector_fill(target,edges,count,rule,color,clip ? &clip->bitmap : NULL,&c->work,&c->control,e);
  free(edges); return status;
}
static int inverse(const double *m,double out[6]) {
  double d; size_t i;
  for(i=0;i<6;i++) if(!isfinite(m[i]) || fabs(m[i])>1e7) return 0;
  d=m[0]*m[3]-m[1]*m[2]; if(!d || !isfinite(d)) return 0;
  out[0]=m[3]/d; out[1]=-m[1]/d; out[2]=-m[2]/d; out[3]=m[0]/d;
  out[4]=-(out[0]*m[4]+out[2]*m[5]); out[5]=-(out[1]*m[4]+out[3]*m[5]);
  for(i=0;i<6;i++) if(!isfinite(out[i]) || fabs(out[i])>1e7) return 0;
  return 1;
}
static void multiply(const double a[6],const double b[6],double out[6]) {
  out[0]=a[0]*b[0]+a[2]*b[1]; out[1]=a[1]*b[0]+a[3]*b[1];
  out[2]=a[0]*b[2]+a[2]*b[3]; out[3]=a[1]*b[2]+a[3]*b[3];
  out[4]=a[0]*b[4]+a[2]*b[5]+a[4]; out[5]=a[1]*b[4]+a[3]*b[5]+a[5];
}
exr_draw_style exr_draw_style_defaults(void) {
  exr_draw_style style={0}; style.fill=style.stroke=0x000000ff; style.flags=EXR_DRAW_FILL; style.line.width=1; style.line.miter_limit=10; return style;
}
exr_status exr_canvas_create(const exr_canvas_config *config,exr_canvas **out,exr_error *e) {
  exr_canvas *c; unsigned channels,k; size_t bytes,i;
  if(!out) return exr_fail(e,EXR_ARGUMENT,"Missing canvas output");
  *out=NULL;
  if(!config || !config->width || !config->height || config->width>16384 || config->height>16384 ||
     (config->channels && config->channels!=1 && config->channels!=4)) return exr_fail(e,EXR_ARGUMENT,"Invalid canvas dimensions/channels");
  channels=config->channels ? config->channels : 4;
  if(config->width>(size_t)64*1024*1024/channels/config->height) return exr_fail(e,EXR_LIMIT,"Canvas bitmap exceeds 64 MiB");
  if(exr_control_cancel(&config->control,e)!=EXR_OK) return EXR_CANCELLED;
  c=calloc(1,sizeof(*c)); if(!c) return exr_fail(e,EXR_MEMORY,"Canvas allocation failed");
  c->control=config->control; c->mask_budget=config->mask_budget ? config->mask_budget : (size_t)64*1024*1024;
  c->bitmap.width=config->width; c->bitmap.height=config->height; c->bitmap.channels=channels; c->bitmap.stride=config->width*channels;
  bytes=(size_t)c->bitmap.stride*c->bitmap.height; c->bitmap.pixels=malloc(bytes);
  if(!c->bitmap.pixels) { free(c); return exr_fail(e,EXR_MEMORY,"Canvas bitmap allocation failed"); }
  if(channels==1) {
    unsigned r=config->background>>24,g=(config->background>>16)&255,b=(config->background>>8)&255;
    memset(c->bitmap.pixels,(int)((r*77+g*150+b*29+128)>>8),bytes);
  } else for(i=0;i<bytes;i+=4) for(k=0;k<4;k++) c->bitmap.pixels[i+k]=(unsigned char)(config->background>>(24-8*k));
  *out=c; return exr_fail(e,EXR_OK,"");
}
void exr_canvas_union_abort(exr_canvas *c) { if(c) { unref(c,c->group); c->group=NULL; } }
void exr_canvas_free(exr_canvas *c) {
  if(!c) return;
  unref(c,c->clip); exr_canvas_union_abort(c);
  while(c->group_depth) unref(c,c->groups[--c->group_depth]);
  while(c->depth) unref(c,c->saved[--c->depth]);
  free(c->bitmap.pixels); free(c);
}
size_t exr_canvas_memory_size(const exr_canvas *c) {
  return c ? sizeof(*c)+(c->bitmap.pixels ? (size_t)c->bitmap.stride*c->bitmap.height : 0)+c->mask_bytes+c->mask_count*sizeof(exr_clip_mask) : 0;
}
const exr_bitmap *exr_canvas_bitmap(const exr_canvas *c) { return c && c->bitmap.pixels && c->failure.code==EXR_OK ? &c->bitmap : NULL; }
exr_status exr_canvas_take(exr_canvas *c,exr_bitmap *out,exr_error *e) {
  exr_status status;
  if(out) memset(out,0,sizeof(*out));
  if(!out) return finish(c,exr_fail(e,EXR_ARGUMENT,"Missing canvas bitmap output"),e);
  status=ready(c,e); if(status!=EXR_OK) return status;
  *out=c->bitmap; memset(&c->bitmap,0,sizeof(c->bitmap)); return exr_fail(e,EXR_OK,"");
}
exr_status exr_canvas_save(exr_canvas *c,exr_error *e) {
  exr_status status=ready(c,e); if(status!=EXR_OK) return status;
  if(c->depth==160) return finish(c,exr_fail(e,EXR_LIMIT,"Canvas clip stack exceeds 160"),e);
  c->saved[c->depth++]=c->clip; if(c->clip) c->clip->refs++; return exr_fail(e,EXR_OK,"");
}
exr_status exr_canvas_restore(exr_canvas *c,exr_error *e) {
  exr_status status=ready(c,e); if(status!=EXR_OK) return status;
  if(!c->depth) return finish(c,exr_fail(e,EXR_ARGUMENT,"Canvas clip stack underflow"),e);
  unref(c,c->clip); c->clip=c->saved[--c->depth]; c->saved[c->depth]=NULL; return exr_fail(e,EXR_OK,"");
}
exr_status exr_canvas_path(exr_canvas *c,const exr_path_segment *segments,size_t count,const double transform[6],const exr_draw_style *style,exr_error *e) {
  const double identity[6]={1,0,0,1,0,0}; exr_draw_style defaults=exr_draw_style_defaults();
  exr_vector_polyline flat={0},local={0},dashed={0},outline={0}; exr_status status=ready(c,e);
  if(status!=EXR_OK) return status;
  if(!style) style=&defaults;
  if((style->flags&~3u) || (style->rule!=EXR_FILL_NONZERO && style->rule!=EXR_FILL_EVENODD) || (count && !segments))
    return finish(c,exr_fail(e,EXR_ARGUMENT,"Invalid canvas path flags/rule/input"),e);
  if(style->flags&EXR_DRAW_FILL) status=exr_vector_flatten(segments,count,transform,.125,&flat,&c->work,&c->control,e);
  if(status==EXR_OK && (style->flags&EXR_DRAW_FILL)) status=fill(c,&flat,style->rule,style->fill,&c->bitmap,c->clip,e);
  if(status==EXR_OK && (style->flags&EXR_DRAW_STROKE)) {
    const double *stroke=style->stroke_matrix ? style->stroke_matrix : transform ? transform : identity;
    double inv[6],matrix[6],scale=hypot(stroke[0],stroke[1])+hypot(stroke[2],stroke[3]);
    if(!inverse(stroke,inv)) { status=exr_fail(e,EXR_ARGUMENT,"Invalid or singular canvas stroke matrix"); goto done; }
    if(transform) multiply(inv,transform,matrix); else memcpy(matrix,inv,sizeof(matrix));
    status=exr_vector_flatten(segments,count,matrix,.125/fmax(1,scale),&local,&c->work,&c->control,e);
    if(status==EXR_OK && style->dash_count) status=exr_vector_dash(&local,style->dashes,style->dash_count,style->dash_phase,&dashed,&c->work,&c->control,e);
    if(status==EXR_OK) status=exr_vector_stroke(style->dash_count ? &dashed : &local,&style->line,stroke,.125,&outline,&c->work,&c->control,e);
    if(status==EXR_OK) status=fill(c,&outline,EXR_FILL_NONZERO,style->stroke,&c->bitmap,c->clip,e);
  }
done:
  exr_vector_polyline_free(&flat); exr_vector_polyline_free(&local); exr_vector_polyline_free(&dashed); exr_vector_polyline_free(&outline); return finish(c,status,e);
}
static exr_status clip_path(exr_canvas *c,const exr_path_segment *segments,size_t count,const double matrix[6],exr_fill_rule rule,int group,exr_error *e) {
  exr_vector_polyline flat={0}; exr_clip_mask *mask=NULL; exr_status status=ready(c,e);
  if(status!=EXR_OK) return status;
  status=exr_vector_flatten(segments,count,matrix,.125,&flat,&c->work,&c->control,e);
  if(status==EXR_OK && group) {
    if(!c->group) status=new_mask(c,&c->group,e);
    if(status==EXR_OK) status=fill(c,&flat,rule,0xffffffff,&c->group->bitmap,NULL,e);
  } else if(status==EXR_OK) {
    status=new_mask(c,&mask,e);
    if(status==EXR_OK) status=fill(c,&flat,rule,0xffffffff,&mask->bitmap,c->clip,e);
    if(status==EXR_OK) { unref(c,c->clip); c->clip=mask; mask=NULL; }
  }
  unref(c,mask); exr_vector_polyline_free(&flat); return finish(c,status,e);
}
exr_status exr_canvas_clip(exr_canvas *c,const exr_path_segment *segments,size_t count,const double matrix[6],exr_fill_rule rule,exr_error *e) {
  return clip_path(c,segments,count,matrix,rule,0,e);
}
exr_status exr_canvas_union_add(exr_canvas *c,const exr_path_segment *segments,size_t count,const double matrix[6],exr_fill_rule rule,exr_error *e) {
  return clip_path(c,segments,count,matrix,rule,1,e);
}
exr_status exr_canvas_union_commit(exr_canvas *c,exr_error *e) {
  exr_status status=ready(c,e); uint32_t x,y;
  if(status!=EXR_OK) return status;
  if(c->group && c->clip) for(y=0;y<c->bitmap.height;y++) {
    if(!(y&63) && (status=exr_control_cancel(&c->control,e))!=EXR_OK) return finish(c,status,e);
    if(!exr_vector_work(&c->work,c->bitmap.width)) return finish(c,exr_fail(e,EXR_LIMIT,"Canvas clip union work exceeds budget"),e);
    for(x=0;x<c->bitmap.width;x++) {
      unsigned char *p=c->group->bitmap.pixels+(size_t)y*c->group->bitmap.stride+x;
      *p=(unsigned char)(((unsigned)*p*c->clip->bitmap.pixels[(size_t)y*c->clip->bitmap.stride+x]+127)/255);
    }
  }
  if(c->group) { unref(c,c->clip); c->clip=c->group; c->group=NULL; }
  return exr_fail(e,EXR_OK,"");
}
exr_status exr_canvas_image(exr_canvas *c,const exr_image_layer *image,const double matrix[6],double alpha,exr_error *e) {
  exr_status status=ready(c,e); if(status!=EXR_OK) return status;
  status=exr_vector_texture_paint(&c->bitmap,image,matrix,alpha,c->clip ? &c->clip->bitmap : NULL,&c->work,&c->control,e);
  return finish(c,status,e);
}
static exr_status sink_path(void *context,const exr_path_segment *segments,size_t count,const double matrix[6],const exr_draw_style *style,exr_error *e) {
  return exr_canvas_path(context,segments,count,matrix,style,e);
}
static exr_status sink_image(void *context,const exr_image_layer *image,const double matrix[6],double alpha,exr_error *e) {
  return exr_canvas_image(context,image,matrix,alpha,e);
}
static exr_status sink_clip(void *context,const exr_path_segment *segments,size_t count,const double matrix[6],exr_fill_rule rule,unsigned accumulate,exr_error *e) {
  if(accumulate>1) return finish(context,exr_fail(e,EXR_ARGUMENT,"Invalid clip union operation"),e);
  return clip_path(context,segments,count,matrix,rule,accumulate!=0,e);
}
static exr_status sink_state(void *context,exr_draw_state state,exr_error *e) {
  exr_canvas *c=context; exr_status status;
  if(state==EXR_DRAW_SAVE) return exr_canvas_save(c,e);
  if(state==EXR_DRAW_RESTORE) return exr_canvas_restore(c,e);
  if(state==EXR_DRAW_END_CLIP) {
    status=exr_canvas_union_commit(c,e); if(status!=EXR_OK) return status;
    if(c->group_depth && --c->group_depth) { c->group=c->groups[c->group_depth-1]; c->groups[c->group_depth-1]=NULL; }
    return exr_fail(e,EXR_OK,"");
  }
  status=ready(c,e); if(status!=EXR_OK) return status;
  if(state!=EXR_DRAW_BEGIN_CLIP) return finish(c,exr_fail(e,EXR_ARGUMENT,"Unknown canvas drawing state"),e);
  if(c->group_depth==64) return finish(c,exr_fail(e,EXR_LIMIT,"Canvas nested clip unions exceed 64"),e);
  if(c->group_depth) { c->groups[c->group_depth-1]=c->group; c->group=NULL; }
  else exr_canvas_union_abort(c);
  c->group_depth++; return exr_fail(e,EXR_OK,"");
}
exr_status exr_canvas_get_sink(exr_canvas *c,exr_draw_sink *out,exr_error *e) {
  exr_status status;
  if(out) memset(out,0,sizeof(*out));
  if(!out) return exr_fail(e,EXR_ARGUMENT,"Missing canvas draw sink output");
  status=ready(c,e); if(status!=EXR_OK) return status;
  out->path=sink_path; out->image=sink_image; out->clip=sink_clip; out->state=sink_state; out->context=c; return exr_fail(e,EXR_OK,"");
}
