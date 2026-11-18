/* SPDX-License-Identifier: MIT */
/* Diagnostic relink only. Production objects and rendered output are unchanged:
   the original RGB image callback still produces every committed pixel. Around
   it, a generated replica of src/affine_image.c reruns the same call with single
   stages knocked out; those outputs are discarded. */
#include "canvas_internal.h"
#include "pdf_raster_internal.h"
#include "vector_internal.h"
#include "pixels_internal.h"
#include "replica_knobs.h"
#include <emmintrin.h>
#include <malloc.h>
#include <windows.h>

unsigned replica_sink;
int replica_path;
unsigned char *replica_hot_read,*replica_hot_write;
typedef exr_status (*replica_fn)(exr_bitmap *,const exr_vector_texture *,const double *,double,
  const exr_bitmap *,exr_blend_mode,exr_composite_state *,size_t *,const exr_control *,exr_error *);
#define REPLICA_DECL(n) exr_status replica_texture_blend_##n(exr_bitmap *target,const exr_vector_texture *source,const double m[6],double alpha,   const exr_bitmap *clip,exr_blend_mode mode,exr_composite_state *state,size_t *work,const exr_control *control,exr_error *e);
REPLICA_DECL(0)
REPLICA_DECL(1)
REPLICA_DECL(2)
REPLICA_DECL(3)
REPLICA_DECL(4)
REPLICA_DECL(5)
REPLICA_DECL(6)
REPLICA_DECL(7)
REPLICA_DECL(8)
REPLICA_DECL(9)
REPLICA_DECL(10)
REPLICA_DECL(11)
REPLICA_DECL(12)
REPLICA_DECL(13)
REPLICA_DECL(14)
REPLICA_DECL(15)
REPLICA_DECL(16)
REPLICA_DECL(17)
static const replica_fn replicas[REPLICA_COUNT]={replica_texture_blend_0,replica_texture_blend_1,replica_texture_blend_2,replica_texture_blend_3,replica_texture_blend_4,replica_texture_blend_5,replica_texture_blend_6,replica_texture_blend_7,replica_texture_blend_8,replica_texture_blend_9,replica_texture_blend_10,replica_texture_blend_11,replica_texture_blend_12,replica_texture_blend_13,replica_texture_blend_14,replica_texture_blend_15,replica_texture_blend_16,replica_texture_blend_17};
enum { KINDS=3+REPLICA_COUNT,CONDITIONS=2,ARMS=KINDS*CONDITIONS,PATHS=9,STATE_PATH=8 };
/* kind 0 original callback, 1 replica with 64-byte-aligned strides, 2 aligned
   strides plus 64 padding bytes per row, 3+i replica REPLICA_MASK_i.
   condition 0 flushes every input/output line first; condition 1 leaves the cache as-is. */
enum { M_TIME=0,M_CALLS=ARMS*PATHS,M_PIXELS=M_CALLS+PATHS,M_MISMATCH=M_PIXELS+PATHS,M_SKIPPED,M_STATUS,M_SINK,M_FLUSH_MS,M_COUNT };
static exr_draw_image_fn original_image;
static int enabled,rotation,mask_depth;
static unsigned call_index;
static double metrics[M_COUNT];
static double now(void) { LARGE_INTEGER t,f;QueryPerformanceCounter(&t);QueryPerformanceFrequency(&f);return (double)t.QuadPart*1000/f.QuadPart; }
__declspec(dllexport) int split_count(void) { return M_COUNT; }
__declspec(dllexport) void split_begin(int enable,int rotate) { enabled=enable;rotation=rotate;call_index=0;memset(metrics,0,sizeof(metrics)); }
__declspec(dllexport) void split_read(double *out) { memcpy(out,metrics,sizeof(metrics)); }

/* Verbatim from src/canvas.c (static there). */
static void multiply(const double a[6],const double b[6],double out[6]) {
  out[0]=a[0]*b[0]+a[2]*b[1]; out[1]=a[1]*b[0]+a[3]*b[1];
  out[2]=a[0]*b[2]+a[2]*b[3]; out[3]=a[1]*b[2]+a[3]*b[3];
  out[4]=a[0]*b[4]+a[2]*b[5]+a[4]; out[5]=a[1]*b[4]+a[3]*b[5]+a[5];
}
static const double *shifted(exr_canvas *c,const double transform[6],double out[6]) {
  const double t[6]={1,0,0,1,-(double)c->offset_x,-(double)c->offset_y};
  if(!c->offset_x && !c->offset_y) return transform;
  if(transform) { multiply(t,transform,out); return out; }
  memcpy(out,t,sizeof(t)); return out;
}
static exr_composite_state *masked_state(exr_canvas *c) {
  exr_composite_state *s=c->composite ? c->composite : ((c->soft_mask || c->gray_groups || (c->alpha_flags&EXR_ALPHA_CONSTANT_SHAPE)) ? &c->mask_state : NULL);
  if(!s) return NULL;
  s->gray=c->gray_groups!=0;s->alpha_flags=c->alpha_flags;
  s->soft_mask=c->soft_mask;s->soft_mask_width=c->soft_mask_width;s->soft_mask_height=c->soft_mask_height;
  return s;
}
static void flush(const void *p,size_t n) {
  if(!p || !n) return;
  const char *a=(const char *)((uintptr_t)p&~(uintptr_t)63),*b=(const char *)p+n;
  for(;a<b;a+=64) _mm_clflush(a);
}
static size_t padded_stride(size_t bytes,int extra) { return ((bytes+63)&~(size_t)63)+(extra ? 64 : 0); }
typedef struct { exr_bitmap dest,clip; exr_image_layer layers[16]; size_t depth; int has_clip; } padded;
static void padded_free(padded *p) {
  _aligned_free(p->dest.pixels);_aligned_free(p->clip.pixels);
  for(size_t i=0;i<p->depth;i++) _aligned_free(p->layers[i].bitmap.pixels);
  memset(p,0,sizeof(*p));
}
static int padded_bitmap(exr_bitmap *out,const exr_bitmap *in,int extra,int copy) {
  *out=*in;out->stride=padded_stride((size_t)in->width*in->channels,extra);
  out->pixels=_aligned_malloc(out->stride*in->height,64);if(!out->pixels) return 0;
  if(copy) for(size_t y=0;y<in->height;y++) memcpy(out->pixels+y*out->stride,in->pixels+y*in->stride,(size_t)in->width*in->channels);
  return 1;
}
static int padded_init(padded *p,exr_canvas *c,const exr_image_layer *image,int extra) {
  memset(p,0,sizeof(*p));
  if(!padded_bitmap(&p->dest,&c->bitmap,extra,0)) return 0;
  if(c->clip) { p->has_clip=1; if(!padded_bitmap(&p->clip,&c->clip->bitmap,extra,1)) return 0; }
  for(const exr_image_layer *l=image;l && p->depth<16;l=l->mask) {
    exr_image_layer *q=p->layers+p->depth++;*q=*l;q->mask=NULL;
    if(p->depth>1) p->layers[p->depth-2].mask=q;
    if(!padded_bitmap(&q->bitmap,&l->bitmap,extra,1)) { q->bitmap.pixels=NULL; return 0; }
  }
  return 1;
}
static void padded_load(padded *p,const exr_bitmap *d,int y0,int y1,const unsigned char *rows) {
  for(int y=y0;y<y1;y++) memcpy(p->dest.pixels+(size_t)y*p->dest.stride,rows+(size_t)(y-y0)*d->stride,(size_t)d->width*4);
}
static void padded_store(const padded *p,const exr_bitmap *d,int y0,int y1,unsigned char *rows,const unsigned char *before) {
  memcpy(rows,before,(size_t)(y1-y0)*d->stride);
  for(int y=y0;y<y1;y++) memcpy(rows+(size_t)(y-y0)*d->stride,p->dest.pixels+(size_t)y*p->dest.stride,(size_t)d->width*4);
}
static void flush_layers(const exr_image_layer *l) {
  for(size_t i=0;l && i<16;i++,l=l->mask) flush(l->bitmap.pixels,l->bitmap.stride*l->bitmap.height);
}
static exr_status image_probe(void *ctx,const exr_image_layer *image,const double m[6],double alpha,exr_error *e) {
  if(!enabled || mask_depth) return original_image(ctx,image,m,alpha,e);
  exr_canvas *c=ctx;
  if(!c || c->bitmap.channels!=4 || !c->bitmap.pixels || c->failure.code!=EXR_OK || !image || !m) { metrics[M_SKIPPED]++;return original_image(ctx,image,m,alpha,e); }
  if(masked_state(c)) {
    /* Composite-state writers also update auxiliary group state: run once, undecomposed. */
    double t=now();exr_status s=original_image(ctx,image,m,alpha,e);
    metrics[M_TIME+(KINDS+0)*PATHS+STATE_PATH]+=now()-t;metrics[M_CALLS+STATE_PATH]++;return s;
  }
  double local[6],left=1e7,top=1e7,right=-1e7,bottom=-1e7;const double *use=shifted(c,m,local);
  for(int i=0;i<4;i++) {
    double px=use[4]+(i&1 ? use[0] : 0)+(i&2 ? use[2] : 0),py=use[5]+(i&1 ? use[1] : 0)+(i&2 ? use[3] : 0);
    left=fmin(left,px);right=fmax(right,px);top=fmin(top,py);bottom=fmax(bottom,py);
  }
  int x0=(int)fmax(0,floor(left)),x1=(int)fmin(c->bitmap.width,ceil(right)),y0=(int)fmax(0,floor(top)),y1=(int)fmin(c->bitmap.height,ceil(bottom));
  if(!(x1>x0 && y1>y0) || !isfinite(left+right+top+bottom)) {
    double t=now();exr_status s=original_image(ctx,image,m,alpha,e);
    metrics[M_TIME+(KINDS+0)*PATHS+0]+=now()-t;metrics[M_CALLS+0]++;return s;
  }
  exr_bitmap *d=&c->bitmap;const exr_bitmap *clip=c->clip ? &c->clip->bitmap : NULL;
  size_t rb=(size_t)(y1-y0)*d->stride,row_bytes=(size_t)d->width*4;unsigned char *rows=d->pixels+(size_t)y0*d->stride;
  /* outs[cond][0] original, [1] aligned replica, [2] padded replica, [3] unmodified replica. */
  unsigned char *before=malloc(rb),*outs[CONDITIONS][4]={{0}};
  padded pads[2];memset(pads,0,sizeof(pads));int ok=before!=NULL;
  for(int k=0;k<CONDITIONS && ok;k++) for(int j=0;j<4 && ok;j++) ok=(outs[k][j]=malloc(rb))!=NULL;
  replica_hot_read=ok ? _aligned_malloc(row_bytes,64) : NULL;replica_hot_write=ok ? _aligned_malloc(row_bytes,64) : NULL;
  ok=ok && replica_hot_read && replica_hot_write && padded_init(pads,c,image,0) && padded_init(pads+1,c,image,1);
  if(!ok) {
    for(int k=0;k<CONDITIONS;k++) for(int j=0;j<4;j++) free(outs[k][j]);
    free(before);_aligned_free(replica_hot_read);_aligned_free(replica_hot_write);replica_hot_read=replica_hot_write=NULL;padded_free(pads);padded_free(pads+1);
    metrics[M_SKIPPED]++;return original_image(ctx,image,m,alpha,e);
  }
  memcpy(before,rows,rb);memcpy(replica_hot_read,before,row_bytes);memset(replica_hot_write,0,row_bytes);
  size_t saved_work=c->work,work_after=saved_work;double times[ARMS];int path=-1;exr_status status=EXR_OK,rs[ARMS];
  unsigned offset=(unsigned)(rotation+5*call_index++)%ARMS;
  for(unsigned j=0;j<ARMS;j++) {
    unsigned a=(offset+j)%ARMS,cond=a/KINDS,kind=a%KINDS;padded *pd=kind==1 || kind==2 ? pads+kind-1 : NULL;
    double flush_start=now();
    memcpy(rows,before,rb);
    if(pd) padded_load(pd,d,y0,y1,before);
    if(cond==0) {
      if(pd) { flush(pd->dest.pixels+(size_t)y0*pd->dest.stride,(size_t)(y1-y0)*pd->dest.stride);
        if(pd->has_clip) flush(pd->clip.pixels+(size_t)y0*pd->clip.stride,(size_t)(y1-y0)*pd->clip.stride);
        flush_layers(pd->layers); }
      else { flush(rows,rb);if(clip) flush(clip->pixels+(size_t)y0*clip->stride,(size_t)(y1-y0)*clip->stride);
        flush_layers(image); }
      flush(replica_hot_read,row_bytes);flush(replica_hot_write,row_bytes);_mm_mfence();
    }
    metrics[M_FLUSH_MS]+=now()-flush_start;
    size_t work=saved_work;exr_error err={0};exr_status s;
    double t=now();
    if(kind==0) { c->work=saved_work;s=original_image(ctx,image,m,alpha,e); }
    else if(pd) s=replicas[0](&pd->dest,pd->layers,use,alpha,pd->has_clip ? &pd->clip : NULL,c->blend,NULL,&work,&c->control,&err);
    else s=replicas[kind-3](d,image,use,alpha,clip,c->blend,NULL,&work,&c->control,&err);
    times[a]=now()-t;rs[a]=s;
    if(kind==0) { work_after=c->work;status=s;memcpy(outs[cond][0],rows,rb); }
    else if(pd) padded_store(pd,d,y0,y1,outs[cond][kind],before);
    else if(kind==3) { path=replica_path;memcpy(outs[cond][3],rows,rb); }
  }
  for(int k=0;k<CONDITIONS;k++) for(int j=0;j<4;j++) if(memcmp(outs[k][j],outs[1][0],rb)) metrics[M_MISMATCH]++;
  memcpy(rows,outs[1][0],rb);c->work=work_after;
  free(before);for(int k=0;k<CONDITIONS;k++) for(int j=0;j<4;j++) free(outs[k][j]);
  _aligned_free(replica_hot_read);_aligned_free(replica_hot_write);replica_hot_read=replica_hot_write=NULL;padded_free(pads);padded_free(pads+1);
  if(path<0) path=0;
  for(unsigned a=0;a<ARMS;a++) { metrics[M_TIME+a*PATHS+(unsigned)path]+=times[a];if(rs[a]!=status) metrics[M_STATUS]++; }
  metrics[M_CALLS+path]++;metrics[M_PIXELS+path]+=(double)(x1-x0)*(y1-y0);metrics[M_SINK]=replica_sink;
  return status;
}
/* Approach B: one opaque, axis-aligned, interpolated RGBA image covering a
   dim x dim opaque destination, source side = dim*ratio_percent/100. which 0
   calls the production exr_vector_texture_blend object, 1 the unmodified
   replica, 2 the all-knobs replica. Each repetition restores the destination
   outside the timed call; flush_each additionally evicts every line first. */
__declspec(dllexport) int split_synthetic(unsigned dim,unsigned ratio_percent,unsigned reps,int which,int flush_each,double *best_ms,double *total_ms) {
  unsigned side=dim*ratio_percent/100;if(!dim || !side || !reps) return -1;
  exr_bitmap dest={0},init={0};exr_image_layer image;memset(&image,0,sizeof(image));
  dest.width=dest.height=dim;dest.channels=4;dest.stride=(size_t)dim*4;
  image.bitmap.width=image.bitmap.height=side;image.bitmap.channels=4;image.bitmap.stride=(size_t)side*4;image.interpolate=1;
  dest.pixels=_aligned_malloc(dest.stride*dim,64);init.pixels=_aligned_malloc(dest.stride*dim,64);image.bitmap.pixels=_aligned_malloc(image.bitmap.stride*side,64);
  unsigned char *hr=_aligned_malloc(dest.stride,64),*hw=_aligned_malloc(dest.stride,64);
  int status=0;
  if(!dest.pixels || !init.pixels || !image.bitmap.pixels || !hr || !hw) status=-2;
  else {
    for(size_t i=0;i<dest.stride*dim;i++) init.pixels[i]=(i&3)==3 ? 255 : (unsigned char)(i*7);
    for(size_t i=0;i<image.bitmap.stride*side;i++) image.bitmap.pixels[i]=(i&3)==3 ? 255 : (unsigned char)(i*13+(i>>12));
    memcpy(hr,init.pixels,dest.stride);memset(hw,0,dest.stride);replica_hot_read=hr;replica_hot_write=hw;
    const double m[6]={dim,0,0,dim,0,0};*best_ms=1e300;*total_ms=0;
    for(unsigned r=0;r<reps && !status;r++) {
      memcpy(dest.pixels,init.pixels,dest.stride*dim);
      if(flush_each) { flush(dest.pixels,dest.stride*dim);flush(image.bitmap.pixels,image.bitmap.stride*side);flush(hr,dest.stride);flush(hw,dest.stride);_mm_mfence(); }
      size_t work=0;exr_error err={0};exr_status s;double t=now();
      s=which==0 ? exr_vector_texture_blend(&dest,&image,m,1,NULL,EXR_BLEND_NORMAL,NULL,&work,NULL,&err) : replicas[which==1 ? 0 : 8](&dest,&image,m,1,NULL,EXR_BLEND_NORMAL,NULL,&work,NULL,&err);
      t=now()-t;if(s!=EXR_OK) status=(int)s;
      *total_ms+=t;if(t<*best_ms) *best_ms=t;
    }
    replica_hot_read=replica_hot_write=NULL;
  }
  _aligned_free(dest.pixels);_aligned_free(init.pixels);_aligned_free(image.bitmap.pixels);_aligned_free(hr);_aligned_free(hw);
  return status;
}
extern __typeof__(exr_canvas_get_sink_ex) __real_exr_canvas_get_sink_ex;
exr_status __wrap_exr_canvas_get_sink_ex(exr_canvas *c,exr_draw_sink_ex *sink,exr_error *e) {
  exr_status s=__real_exr_canvas_get_sink_ex(c,sink,e);
  if(s==EXR_OK && sink->base.image) { original_image=sink->base.image;sink->base.image=image_probe; }return s;
}
extern __typeof__(exr_pdf_soft_mask_build) __real_exr_pdf_soft_mask_build;
exr_status __wrap_exr_pdf_soft_mask_build(exr_pdf_file *f,uint32_t id,const double m[6],unsigned w,unsigned h,unsigned char **out,size_t *work,size_t *active,const exr_control *control,exr_error *e) {
  mask_depth++;exr_status s=__real_exr_pdf_soft_mask_build(f,id,m,w,h,out,work,active,control,e);mask_depth--;return s;
}
