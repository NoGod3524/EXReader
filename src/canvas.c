/* SPDX-License-Identifier: GPL-3.0-only */
#include "canvas_internal.h"
#include <stdio.h>
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
static void composite_free(exr_composite_state *state) {
  if(state) { free(state->pixels);free(state); }
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
/* The soft mask rides on the composite state so every pixel writer applies it. */
static exr_composite_state *masked_state(exr_canvas *c) {
  exr_composite_state *s=c->composite ? c->composite : (c->soft_mask ? &c->mask_state : NULL);
  if(!s) return NULL;
  s->soft_mask=c->soft_mask;s->soft_mask_width=c->soft_mask_width;s->soft_mask_height=c->soft_mask_height;
  return s;
}
exr_status exr_canvas_soft_mask(exr_canvas *c,const unsigned char *mask,size_t width,size_t height,exr_error *e) {
  exr_status status=ready(c,e);if(status!=EXR_OK) return status;
  if(c->soft_mask_owned) { free(c->soft_mask_owned); c->soft_mask_owned=NULL; }
  if(mask && (width!=c->bitmap.width || height!=c->bitmap.height)) {
    /* A host builds the mask at the device extent; a region-sized working buffer
       needs the matching sub-rectangle. */
    size_t row,bw=c->bitmap.width,bh=c->bitmap.height;
    unsigned char *crop;
    if(width!=c->canvas_width || height!=c->canvas_height)
      return finish(c,exr_fail(e,EXR_ARGUMENT,"Soft mask size must match the canvas"),e);
    crop=malloc(bw*bh); if(!crop) return finish(c,exr_fail(e,EXR_MEMORY,"Soft mask crop allocation failed"),e);
    for(row=0;row<bh;row++)
      memcpy(crop+row*bw,mask+(row+(size_t)c->offset_y)*width+(size_t)c->offset_x,bw);
    c->soft_mask_owned=crop;c->soft_mask=crop;c->soft_mask_width=bw;c->soft_mask_height=bh;
    return EXR_OK;
  }
  c->soft_mask=mask;c->soft_mask_width=mask ? width : 0;c->soft_mask_height=mask ? height : 0;
  return EXR_OK;
}
static exr_status fill(exr_canvas *c,const exr_vector_polyline *path,exr_fill_rule rule,uint32_t color,
                         exr_bitmap *target,const exr_clip_mask *clip,exr_error *e) {
  exr_vector_edge *edges=NULL; size_t count=0; exr_status status=exr_vector_edges(path,1,&edges,&count,&c->work,&c->control,e);
  if(status==EXR_OK) status=exr_vector_fill_blend(target,edges,count,rule,color,clip ? &clip->bitmap : NULL,target==&c->bitmap ? c->blend : EXR_BLEND_NORMAL,target==&c->bitmap ? masked_state(c) : NULL,&c->work,&c->control,e);
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
/* Region-sized groups draw with canvas coordinates shifted to the buffer origin. */
static const double *shifted(exr_canvas *c,const double transform[6],double out[6]) {
  const double t[6]={1,0,0,1,-(double)c->offset_x,-(double)c->offset_y};
  if(!c->offset_x && !c->offset_y) return transform;
  if(transform) { multiply(t,transform,out); return out; }
  memcpy(out,t,sizeof(t)); return out;
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
  c->layer_budget=64*1024*1024;
  c->control=config->control; c->mask_budget=config->mask_budget ? config->mask_budget : (size_t)64*1024*1024;
  c->bitmap.width=config->width; c->bitmap.height=config->height;
  c->canvas_width=config->width; c->canvas_height=config->height; c->bitmap.channels=channels; c->bitmap.stride=config->width*channels;
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
  while(c->layer_depth) {
    exr_canvas_layer *l=&c->layers[--c->layer_depth];size_t i;
    unref(c,l->clip);unref(c,l->pending);
    for(i=0;i<l->group_depth;i++) unref(c,l->pending_groups[i]);
    free(l->pending_groups);composite_free(l->composite);free(l->bitmap.pixels);
  }
  free(c->layers);composite_free(c->composite);free(c->bitmap.pixels); free(c);
}
static size_t composite_size(const exr_bitmap *b,const exr_composite_state *state) {
  return state ? (size_t)b->width*b->height*5*sizeof(float) : 0;
}
size_t exr_canvas_memory_size(const exr_canvas *c) {
  size_t bytes,i;if(!c) return 0;
  bytes=sizeof(*c)+(c->composite ? sizeof(*c->composite) : 0)+composite_size(&c->bitmap,c->composite)+(c->bitmap.pixels ? (size_t)c->bitmap.stride*c->bitmap.height : 0)+c->mask_bytes+c->mask_count*sizeof(exr_clip_mask)+c->layer_capacity*sizeof(*c->layers);
  for(i=0;i<c->layer_depth;i++) bytes+=(size_t)c->layers[i].bitmap.stride*c->layers[i].bitmap.height+c->layers[i].group_depth*sizeof(exr_clip_mask *)+composite_size(&c->layers[i].bitmap,c->layers[i].composite)+(c->layers[i].composite ? sizeof(*c->layers[i].composite) : 0);
  return bytes;
}

const exr_bitmap *exr_canvas_bitmap(const exr_canvas *c) { return c && c->bitmap.pixels && c->failure.code==EXR_OK ? &c->bitmap : NULL; }
exr_status exr_canvas_take(exr_canvas *c,exr_bitmap *out,exr_error *e) {
  exr_status status;
  if(out) memset(out,0,sizeof(*out));
  if(!out) return finish(c,exr_fail(e,EXR_ARGUMENT,"Missing canvas bitmap output"),e);
  status=ready(c,e); if(status!=EXR_OK) return status;
  if(c->layer_depth) return finish(c,exr_fail(e,EXR_ARGUMENT,"Canvas has unfinished layers"),e);
  *out=c->bitmap; memset(&c->bitmap,0,sizeof(c->bitmap)); return exr_fail(e,EXR_OK,"");
}
exr_status exr_canvas_save(exr_canvas *c,exr_error *e) {
  exr_status status=ready(c,e); if(status!=EXR_OK) return status;
  if(c->depth==160) return finish(c,exr_fail(e,EXR_LIMIT,"Canvas clip stack exceeds 160"),e);
  c->saved_blend[c->depth]=c->blend;
  c->saved[c->depth++]=c->clip; if(c->clip) c->clip->refs++; return exr_fail(e,EXR_OK,"");
}
exr_status exr_canvas_restore(exr_canvas *c,exr_error *e) {
  exr_status status=ready(c,e); if(status!=EXR_OK) return status;
  if(!c->depth || (c->layer_depth && c->depth<=c->layers[c->layer_depth-1].depth)) return finish(c,exr_fail(e,EXR_ARGUMENT,"Canvas clip stack underflow"),e);
  unref(c,c->clip); c->blend=c->saved_blend[c->depth-1];c->clip=c->saved[--c->depth]; c->saved[c->depth]=NULL; return exr_fail(e,EXR_OK,"");
}
exr_status exr_canvas_path(exr_canvas *c,const exr_path_segment *segments,size_t count,const double transform_arg[6],const exr_draw_style *style,exr_error *e) {
  const double identity[6]={1,0,0,1,0,0}; exr_draw_style defaults=exr_draw_style_defaults();
  double offset_matrix[6];const double *transform=transform_arg;
  exr_vector_polyline flat={0},local={0},dashed={0},outline={0}; exr_status status=ready(c,e);
  if(status!=EXR_OK) return status;
  if(!style) style=&defaults;
  transform=shifted(c,transform_arg,offset_matrix);
  if((style->flags&~3u) || (style->rule!=EXR_FILL_NONZERO && style->rule!=EXR_FILL_EVENODD) || (count && !segments))
    return finish(c,exr_fail(e,EXR_ARGUMENT,"Invalid canvas path flags/rule/input"),e);
  if(style->flags&EXR_DRAW_FILL) status=exr_vector_flatten(segments,count,transform,.125,&flat,&c->work,&c->control,e);

  if(status==EXR_OK && (style->flags&EXR_DRAW_STROKE)) {
    const double *stroke=style->stroke_matrix ? style->stroke_matrix : transform ? transform : identity;
    double inv[6],matrix[6],scale=hypot(stroke[0],stroke[1])+hypot(stroke[2],stroke[3]);
    if(!inverse(stroke,inv)) { status=exr_fail(e,EXR_ARGUMENT,"Invalid or singular canvas stroke matrix"); goto done; }
    if(transform) multiply(inv,transform,matrix); else memcpy(matrix,inv,sizeof(matrix));
    status=exr_vector_flatten(segments,count,matrix,.125/fmax(1,scale),&local,&c->work,&c->control,e);
    if(status==EXR_OK && style->dash_count) status=exr_vector_dash(&local,style->dashes,style->dash_count,style->dash_phase,&dashed,&c->work,&c->control,e);
    if(status==EXR_OK) status=exr_vector_stroke(style->dash_count ? &dashed : &local,&style->line,stroke,.125,&outline,&c->work,&c->control,e);

  }
  if(status==EXR_OK && style->flags==(EXR_DRAW_FILL|EXR_DRAW_STROKE)) {
    exr_clip_mask *fm=NULL,*sm=NULL;status=new_mask(c,&fm,e);
    if(status==EXR_OK) status=new_mask(c,&sm,e);
    if(status==EXR_OK) status=fill(c,&flat,style->rule,0xffffffff,&fm->bitmap,NULL,e);
    if(status==EXR_OK) status=fill(c,&outline,EXR_FILL_NONZERO,0xffffffff,&sm->bitmap,NULL,e);
    if(status==EXR_OK) status=exr_composite_compound(&c->bitmap,&fm->bitmap,&sm->bitmap,style->fill,style->stroke,c->blend,c->clip ? &c->clip->bitmap : NULL,masked_state(c),&c->work,&c->control,e);
    unref(c,fm);unref(c,sm);
  } else if(status==EXR_OK && (style->flags&EXR_DRAW_FILL)) status=fill(c,&flat,style->rule,style->fill,&c->bitmap,c->clip,e);
  else if(status==EXR_OK && (style->flags&EXR_DRAW_STROKE)) status=fill(c,&outline,EXR_FILL_NONZERO,style->stroke,&c->bitmap,c->clip,e);

done:
  exr_vector_polyline_free(&flat); exr_vector_polyline_free(&local); exr_vector_polyline_free(&dashed); exr_vector_polyline_free(&outline); return finish(c,status,e);
}
static exr_status clip_path(exr_canvas *c,const exr_path_segment *segments,size_t count,const double matrix[6],exr_fill_rule rule,int group,exr_error *e) {
  exr_vector_polyline flat={0}; exr_clip_mask *mask=NULL; exr_status status=ready(c,e);
  if(status!=EXR_OK) return status;
  { double local[6]; const double *use=shifted(c,matrix,local);
    status=exr_vector_flatten(segments,count,use,.125,&flat,&c->work,&c->control,e); }
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
  double local[6];const double *use;
  exr_status status=ready(c,e); if(status!=EXR_OK) return status;
  use=shifted(c,matrix,local);
  status=exr_vector_texture_blend(&c->bitmap,image,use,alpha,c->clip ? &c->clip->bitmap : NULL,c->blend,masked_state(c),&c->work,&c->control,e);
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

exr_status exr_canvas_blend(exr_canvas *c,exr_blend_mode mode,exr_error *e) {
  exr_status status=ready(c,e);if(status!=EXR_OK) return status;
  if(mode<EXR_BLEND_NORMAL || mode>EXR_BLEND_LUMINOSITY) return finish(c,exr_fail(e,EXR_ARGUMENT,"Invalid canvas blend mode"),e);
  c->blend=mode;return exr_fail(e,EXR_OK,"");
}
static exr_status sink_blend(void *context,exr_blend_mode mode,exr_error *e) { return exr_canvas_blend(context,mode,e); }
exr_status exr_draw_sink_snapshot(const exr_draw_sink_ex *input,exr_draw_sink_ex *out,exr_error *e) {
  size_t i,j,size,offsets[]={offsetof(exr_draw_sink_ex,blend),offsetof(exr_draw_sink_ex,begin_layer),offsetof(exr_draw_sink_ex,end_layer),offsetof(exr_draw_sink_ex,begin_group)};
  size_t sizes[]={sizeof(out->blend),sizeof(out->begin_layer),sizeof(out->end_layer),sizeof(out->begin_group)};
  if(!input || input->struct_size<offsets[0] || input->struct_size>4096) return exr_fail(e,EXR_ARGUMENT,"Invalid extended drawing sink size");
  size=input->struct_size;
  for(i=sizeof(*out);i<size;i++) if(((const unsigned char *)input)[i]) return exr_fail(e,EXR_ARGUMENT,"Unsupported drawing sink extension");
  memset(out,0,sizeof(*out));memcpy(out,input,size<sizeof(*out) ? size : sizeof(*out));
  for(j=0;j<4;j++) if(size>offsets[j] && size<offsets[j]+sizes[j]) {
    for(i=offsets[j];i<size;i++) if(((const unsigned char *)input)[i]) return exr_fail(e,EXR_ARGUMENT,"Truncated drawing effect callback");
    memset((unsigned char *)out+offsets[j],0,sizes[j]);
  }
  if(!!(out->begin_layer || out->begin_group)!=!!out->end_layer) return exr_fail(e,EXR_ARGUMENT,"Drawing layer callbacks require a pair");
  out->struct_size=sizeof(*out);return EXR_OK;
}
static exr_status sink_begin_layer(void *context,double opacity,exr_blend_mode mode,exr_error *e) { return exr_canvas_begin_layer(context,opacity,mode,e); }
exr_status exr_sink_begin_group(const exr_draw_sink_ex *sink,double opacity,exr_blend_mode mode,unsigned flags,exr_error *e) {
  exr_status status;
  if(sink->begin_group) status=sink->begin_group(sink->base.context,opacity,mode,flags,e);
  else if(flags==EXR_GROUP_ISOLATED && sink->begin_layer) status=sink->begin_layer(sink->base.context,opacity,mode,e);
  else return exr_fail(e,flags==EXR_GROUP_ISOLATED ? EXR_FORMAT : EXR_UNSUPPORTED,"Drawing consumer lacks requested group support");
  return status==EXR_OK && e && e->code!=EXR_OK ? e->code : status;
}
static exr_status sink_begin_group(void *context,double opacity,exr_blend_mode mode,unsigned flags,exr_error *e) { return exr_canvas_begin_group(context,opacity,mode,flags,e); }
exr_status exr_sink_soft_mask(const exr_draw_sink_ex *sink,const unsigned char *mask,size_t width,size_t height,exr_error *e) {
  if(!sink->soft_mask) return mask ? exr_fail(e,EXR_UNSUPPORTED,"Drawing consumer lacks soft-mask support") : EXR_OK;
  return sink->soft_mask(sink->base.context,mask,width,height,e);
}
static exr_status sink_soft_mask(void *context,const unsigned char *mask,size_t width,size_t height,exr_error *e) { return exr_canvas_soft_mask(context,mask,width,height,e); }
exr_status exr_sink_extent(const exr_draw_sink_ex *sink,unsigned *width,unsigned *height,exr_error *e) {
  if(!sink->extent) return exr_fail(e,EXR_UNSUPPORTED,"Drawing consumer lacks a device extent");
  return sink->extent(sink->base.context,width,height,e);
}
static exr_status sink_extent(void *context,unsigned *width,unsigned *height,exr_error *e) {
  const exr_canvas *c=context;
  if(!c || !c->bitmap.pixels) return exr_fail(e,EXR_ARGUMENT,"Canvas has no bitmap");
  /* Hosts and appearance painters need the device extent, not the size of a
     region-sized working buffer that happens to be active. */
  *width=(unsigned)c->canvas_width;*height=(unsigned)c->canvas_height;return EXR_OK;
}
static exr_status sink_end_layer(void *context,unsigned commit,exr_error *e) { return exr_canvas_end_layer(context,commit,e); }
exr_status exr_canvas_get_sink_ex(exr_canvas *c,exr_draw_sink_ex *out,exr_error *e) {
  exr_draw_sink_ex sink={0};size_t size;exr_status status;
  if(!out || out->struct_size<offsetof(exr_draw_sink_ex,blend) || out->struct_size>4096) return exr_fail(e,EXR_ARGUMENT,"Invalid extended sink output size");
  size=out->struct_size<sizeof(sink) ? out->struct_size : sizeof(sink);
  if(size>offsetof(exr_draw_sink_ex,extent) && size<offsetof(exr_draw_sink_ex,extent)+sizeof(sink.extent)) size=offsetof(exr_draw_sink_ex,extent);
  if(size>offsetof(exr_draw_sink_ex,soft_mask) && size<offsetof(exr_draw_sink_ex,soft_mask)+sizeof(sink.soft_mask)) size=offsetof(exr_draw_sink_ex,soft_mask);
  if(size>offsetof(exr_draw_sink_ex,begin_group) && size<offsetof(exr_draw_sink_ex,begin_group)+sizeof(sink.begin_group)) size=offsetof(exr_draw_sink_ex,begin_group);
  if(size>offsetof(exr_draw_sink_ex,begin_layer) && size<offsetof(exr_draw_sink_ex,end_layer)+sizeof(sink.end_layer)) size=offsetof(exr_draw_sink_ex,begin_layer);
  if(size>offsetof(exr_draw_sink_ex,blend) && size<offsetof(exr_draw_sink_ex,begin_layer)) size=offsetof(exr_draw_sink_ex,blend);
  status=exr_canvas_get_sink(c,&sink.base,e);if(status!=EXR_OK) return status;
  sink.struct_size=size;sink.blend=sink_blend;sink.begin_layer=sink_begin_layer;sink.end_layer=sink_end_layer;sink.begin_group=sink_begin_group;sink.soft_mask=sink_soft_mask;sink.extent=sink_extent;
  memset(out,0,out->struct_size);memcpy(out,&sink,size);return EXR_OK;
}
exr_status exr_canvas_set_layer_budget(exr_canvas *c,size_t bytes,exr_error *e) {
  exr_status status=ready(c,e);if(status!=EXR_OK) return status;
  if(c->layer_depth) return finish(c,exr_fail(e,EXR_ARGUMENT,"Cannot change an active layer budget"),e);
  c->layer_budget=bytes ? bytes : 64*1024*1024;return EXR_OK;
}
exr_status exr_canvas_begin_layer(exr_canvas *c,double opacity,exr_blend_mode mode,exr_error *e) {
  return exr_canvas_begin_group(c,opacity,mode,EXR_GROUP_ISOLATED,e);
}
exr_status exr_canvas_begin_group(exr_canvas *c,double opacity,exr_blend_mode mode,unsigned flags,exr_error *e) {
  exr_status status=ready(c,e);exr_canvas_layer layer={0};exr_bitmap next;exr_composite_state *state=NULL;unsigned char *pixels;size_t bytes,count;
  size_t region_width,region_height;int region=0,region_x=0,region_y=0;
  if(status!=EXR_OK) return status;
  unsigned needs_state;
  if(!isfinite(opacity) || opacity<0 || opacity>1 || mode<EXR_BLEND_NORMAL || mode>EXR_BLEND_LUMINOSITY ||
     (flags&~(EXR_GROUP_ISOLATED|EXR_GROUP_KNOCKOUT|EXR_GROUP_WHOLE_BUFFER))) return finish(c,exr_fail(e,EXR_ARGUMENT,"Invalid group parameters"),e);
  needs_state=!(flags&EXR_GROUP_ISOLATED) || (flags&EXR_GROUP_KNOCKOUT);
  region_width=c->bitmap.width;region_height=c->bitmap.height;
  if(c->layer_depth==0 && needs_state && c->clip && !c->soft_mask && !(flags&EXR_GROUP_WHOLE_BUFFER)) {
    size_t x0=region_width,y0=region_height,x1=0,y1=0,xx,yy;
    for(yy=0;yy<region_height;yy++) {
      for(xx=0;xx<region_width;xx++) {
        if(!c->clip->bitmap.pixels[yy*c->clip->bitmap.stride+xx]) continue;
        if(xx<x0) x0=xx;
        if(xx>=x1) x1=xx+1;
        if(yy<y0) y0=yy;
        if(yy>=y1) y1=yy+1;
      }
    }
    if(x1>x0 && y1>y0 && (x1-x0)*(y1-y0)<=region_width*region_height/2) {
      region_x=(int)x0;region_y=(int)y0;region_width=x1-x0;region_height=y1-y0;region=1;
    }
  }
  count=region_width*region_height;bytes=count*(needs_state ? 4+5*sizeof(float) : 4);
  if(c->layer_depth==32 || bytes>64*1024*1024 || bytes>c->layer_budget-c->layer_bytes) return finish(c,exr_fail(e,EXR_LIMIT,"Group depth/byte budget exceeded"),e);
  if(!exr_grow((void **)&c->layers,&c->layer_capacity,c->layer_depth+1,sizeof(*c->layers))) return finish(c,exr_fail(e,EXR_MEMORY,"Layer stack allocation failed"),e);
  if(c->group_depth) {
    layer.pending_groups=malloc(c->group_depth*sizeof(*layer.pending_groups));
    if(!layer.pending_groups) return finish(c,exr_fail(e,EXR_MEMORY,"Layer clip state allocation failed"),e);
    memcpy(layer.pending_groups,c->groups,c->group_depth*sizeof(*c->groups));
  }
  pixels=calloc(count,4);if(needs_state) { state=calloc(1,sizeof(*state));if(state) { state->pixels=calloc(count,5*sizeof(float)); } }
  if(!pixels || (needs_state && (!state || !state->pixels))) {
    free(pixels);composite_free(state);free(layer.pending_groups);return finish(c,exr_fail(e,EXR_MEMORY,"Group working buffer allocation failed"),e);
  }
  next=c->bitmap;next.channels=4;next.width=region_width;next.height=region_height;next.stride=region_width*4;next.pixels=pixels;
  if(state) {
    state->knockout=!!(flags&EXR_GROUP_KNOCKOUT);state->isolated=!!(flags&EXR_GROUP_ISOLATED);
    /* Isolated groups start transparent, so the parent backdrop is not copied in.
       Inside a knockout group every element, including a nested group, composites
       with that group's initial backdrop rather than with the accumulated result. */
    if(!state->isolated) {
      const exr_bitmap *parent=&c->bitmap;const exr_composite_state *parent_state=c->composite;
      if(c->composite && c->composite->knockout && !c->composite->isolated) { parent=&c->composite->backdrop;parent_state=c->composite->backdrop_state; }
      status=exr_composite_initialize(&next,state,parent,parent_state,region_x,region_y,&c->work,&c->control,e);
    }
    else state->depth=1;
    state->origin_x=region_x;state->origin_y=region_y;
  }
  if(status!=EXR_OK) { free(pixels);composite_free(state);free(layer.pending_groups);return finish(c,status,e); }
  layer.bitmap=c->bitmap;layer.composite=c->composite;layer.clip=c->clip;layer.pending=c->group;layer.group_depth=c->group_depth;layer.depth=c->depth;
  layer.origin_x=region_x;layer.origin_y=region_y;layer.parent_offset_x=c->offset_x;layer.parent_offset_y=c->offset_y;
  layer.opacity=opacity;layer.blend=mode;layer.parent_blend=c->blend;c->layers[c->layer_depth++]=layer;c->layer_bytes+=bytes;
  c->bitmap=next;c->composite=state;c->clip=c->group=NULL;c->group_depth=0;c->blend=EXR_BLEND_NORMAL;memset(c->groups,0,sizeof(c->groups));
  c->offset_x=region_x;c->offset_y=region_y;
  if(region && layer.clip) {
    /* The inherited clip becomes a region-sized copy in buffer coordinates. */
    exr_clip_mask *crop=NULL;
    if(new_mask(c,&crop,e)==EXR_OK) {
      size_t row;
      for(row=0;row<region_height;row++)
        memcpy(crop->bitmap.pixels+row*region_width,
               layer.clip->bitmap.pixels+(row+(size_t)region_y)*layer.clip->bitmap.stride+(size_t)region_x,region_width);
      unref(c,c->clip);c->clip=crop;
    }
  }
  return EXR_OK;
}
exr_status exr_canvas_end_layer(exr_canvas *c,unsigned commit,exr_error *e) {
  exr_canvas_layer layer;exr_bitmap source;exr_composite_state *source_state;exr_status status;size_t i;
  if(!c || !c->bitmap.pixels || !c->layer_depth) return finish(c,exr_fail(e,EXR_ARGUMENT,"Missing isolated layer"),e);
  if(commit>1) return finish(c,exr_fail(e,EXR_ARGUMENT,"Invalid layer commit flag"),e);
  layer=c->layers[c->layer_depth-1];source=c->bitmap;source_state=c->composite;status=c->failure.code;
  if(commit && status==EXR_OK && (c->depth!=layer.depth || c->group_depth || c->group)) status=exr_fail(e,EXR_ARGUMENT,"Unbalanced isolated layer scopes");
  unref(c,c->clip);exr_canvas_union_abort(c);while(c->group_depth) unref(c,c->groups[--c->group_depth]);
  while(c->depth>layer.depth) { unref(c,c->saved[--c->depth]);c->saved[c->depth]=NULL; }
  c->bitmap=layer.bitmap;c->composite=layer.composite;c->clip=layer.clip;c->group=layer.pending;c->group_depth=layer.group_depth;c->blend=layer.parent_blend;
  c->offset_x=layer.parent_offset_x;c->offset_y=layer.parent_offset_y;
  memset(c->groups,0,sizeof(c->groups));if(layer.group_depth) memcpy(c->groups,layer.pending_groups,layer.group_depth*sizeof(*c->groups));free(layer.pending_groups);
  c->layer_depth--;c->layer_bytes-=(size_t)source.stride*source.height+composite_size(&source,source_state);memset(c->layers+c->layer_depth,0,sizeof(*c->layers));
  if(commit && status==EXR_OK) status=exr_composite_frame(&c->bitmap,&source,layer.opacity,layer.blend,c->clip ? &c->clip->bitmap : NULL,c->composite,source_state,layer.origin_x,layer.origin_y,&c->work,&c->control,e);
  composite_free(source_state);free(source.pixels);for(i=c->depth;i<160;i++) c->saved_blend[i]=EXR_BLEND_NORMAL;
  return finish(c,status,e);
}
