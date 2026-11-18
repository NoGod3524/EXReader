/* SPDX-License-Identifier: MIT */
/* Diagnostic relink only. Production objects and rendered output are unchanged. */
#include "canvas_internal.h"
#include "pdf_raster_internal.h"
#include <windows.h>
static exr_draw_image_fn original_image;
static int enabled, reverse_order, mask_depth;
static double metrics[10];
static double now(void) { LARGE_INTEGER t,f;QueryPerformanceCounter(&t);QueryPerformanceFrequency(&f);return (double)t.QuadPart*1000/f.QuadPart; }
__declspec(dllexport) void split_begin(int enable,int reverse) { enabled=enable;reverse_order=reverse;memset(metrics,0,sizeof(metrics)); }
__declspec(dllexport) void split_read(double *out) { memcpy(out,metrics,sizeof(metrics)); }
/* One nearest source pixel copied per covered destination center. No interpolation,
   alpha, colour conversion, image mask, soft mask or destination read. */
static size_t copy_pixels(exr_canvas *c,const exr_image_layer *image,const double matrix[6]) {
  const exr_bitmap *s=&image->bitmap; exr_bitmap *d=&c->bitmap;
  double m[6];memcpy(m,matrix,sizeof(m));m[4]-=c->offset_x;m[5]-=c->offset_y;
  double det=m[0]*m[3]-m[1]*m[2];if(!det) return 0;
  double a=m[3]/det,b=-m[1]/det,cc=-m[2]/det,dd=m[0]/det;
  double tx=-(a*m[4]+cc*m[5]),ty=-(b*m[4]+dd*m[5]);
  double left=d->width,right=0,top=d->height,bottom=0;
  for(int i=0;i<4;i++) { double x=m[4]+(i&1?m[0]:0)+(i&2?m[2]:0),y=m[5]+(i&1?m[1]:0)+(i&2?m[3]:0);left=fmin(left,x);right=fmax(right,x);top=fmin(top,y);bottom=fmax(bottom,y); }
  int x0=(int)fmax(0,floor(left)),x1=(int)fmin(d->width,ceil(right)),y0=(int)fmax(0,floor(top)),y1=(int)fmin(d->height,ceil(bottom));size_t n=0;
  for(int y=y0;y<y1;y++) for(int x=x0;x<x1;x++) {
    if(c->clip && !c->clip->bitmap.pixels[(size_t)y*c->clip->bitmap.stride+x]) continue;
    double u=a*(x+.5)+cc*(y+.5)+tx,v=b*(x+.5)+dd*(y+.5)+ty;
    if(u<0 || u>=1 || v<0 || v>=1) continue;
    const unsigned char *p=s->pixels+(size_t)(v*s->height)*s->stride+(size_t)(u*s->width)*s->channels;
    unsigned char *q=d->pixels+(size_t)y*d->stride+(size_t)x*4;
    if(s->channels==4) memcpy(q,p,4);
    else if(s->channels==3) { memcpy(q,p,3);q[3]=255; }
    else { q[0]=q[1]=q[2]=p[0];q[3]=s->channels==2?p[1]:255; }
    n++;
  }
  return n;
}
static exr_status image_probe(void *ctx,const exr_image_layer *image,const double m[6],double alpha,exr_error *e) {
  if(!enabled || mask_depth) return original_image(ctx,image,m,alpha,e);
  exr_canvas *c=ctx;size_t size=c->bitmap.stride*c->bitmap.height;
  if(c->bitmap.channels!=4) { metrics[9]++;return original_image(ctx,image,m,alpha,e); }
  unsigned char *before=malloc(size),*after=reverse_order?malloc(size):NULL;
  if(!before || (reverse_order && !after)) { free(before);free(after);metrics[9]++;return original_image(ctx,image,m,alpha,e); }
  memcpy(before,c->bitmap.pixels,size);double t;size_t pixels;exr_status status;
  if(!reverse_order) {
    t=now();pixels=copy_pixels(c,image,m);metrics[1]+=now()-t;
    memcpy(c->bitmap.pixels,before,size);
    t=now();status=original_image(ctx,image,m,alpha,e);metrics[0]+=now()-t;
  } else {
    t=now();status=original_image(ctx,image,m,alpha,e);metrics[0]+=now()-t;
    memcpy(after,c->bitmap.pixels,size);memcpy(c->bitmap.pixels,before,size);
    t=now();pixels=copy_pixels(c,image,m);metrics[1]+=now()-t;
    memcpy(c->bitmap.pixels,after,size);
  }
  metrics[2]++;metrics[3]+=(double)pixels;metrics[4]+=(double)(c->bitmap.stride-c->bitmap.width*4)*c->bitmap.height;
  metrics[5]+=(double)(image->bitmap.stride-image->bitmap.width*image->bitmap.channels)*image->bitmap.height;
  metrics[6]+=(double)c->bitmap.width*c->bitmap.height*4;metrics[7]+=(double)image->bitmap.width*image->bitmap.height*image->bitmap.channels;
  metrics[8]+=(double)pixels*(4+image->bitmap.channels);
  free(before);free(after);return status;
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
