/* SPDX-License-Identifier: GPL-3.0-only */
#include "vector_internal.h"
#include "pixels_internal.h"
static int storage(const exr_bitmap *b) {
  return b && b->pixels && b->width && b->height && b->width<=16384 && b->height<=16384 &&
    (b->channels==1 || b->channels==4) && b->stride>=(size_t)b->width*b->channels && b->stride<=(size_t)64*1024*1024/b->height;
}
static int overlap(const exr_bitmap *a,const exr_bitmap *b) {
  uintptr_t x=(uintptr_t)a->pixels,y=(uintptr_t)b->pixels;
  return x<=y ? y-x<(size_t)a->stride*a->height : x-y<(size_t)b->stride*b->height;
}
static void sample(const exr_bitmap *b,double u,double v,int interpolate,double out[4]) {
  unsigned k;
  if(!interpolate) {
    uint32_t x=(uint32_t)(u*b->width),y=(uint32_t)(v*b->height); const unsigned char *p;
    if(x>=b->width) x=b->width-1;
    if(y>=b->height) y=b->height-1;
    p=b->pixels+(size_t)y*b->stride+x*4; out[3]=p[3]; for(k=0;k<3;k++) out[k]=p[k]*out[3];
  } else {
    double x=fmax(0,fmin(b->width-1,u*b->width-.5)),y=fmax(0,fmin(b->height-1,v*b->height-.5));
    uint32_t x0=(uint32_t)x,y0=(uint32_t)y,x1=x0+1<b->width ? x0+1 : x0,y1=y0+1<b->height ? y0+1 : y0;
    double wx=x-x0,wy=y-y0,weights[4]={(1-wx)*(1-wy),wx*(1-wy),(1-wx)*wy,wx*wy};
    const unsigned char *p[4]={b->pixels+(size_t)y0*b->stride+x0*4,b->pixels+(size_t)y0*b->stride+x1*4,
      b->pixels+(size_t)y1*b->stride+x0*4,b->pixels+(size_t)y1*b->stride+x1*4}; unsigned i;
    memset(out,0,4*sizeof(*out));
    for(i=0;i<4;i++) { double a=p[i][3]*weights[i]; out[3]+=a; for(k=0;k<3;k++) out[k]+=p[i][k]*a; }
  }
}
exr_status exr_vector_image(exr_bitmap *target,const exr_bitmap *source,const double m[6],double alpha,
                             int interpolate,const exr_bitmap *clip,size_t *work,const exr_control *control,exr_error *e) {
  size_t local_work=0,i; double det,inv[6],left=1e7,top=1e7,right=-1e7,bottom=-1e7; int x0,y0,x1,y1,x,y;
  if(!storage(target) || !storage(source) || source->channels!=4 || !m || !isfinite(alpha) || alpha<0 || alpha>1 || overlap(target,source) ||
     (clip && (!storage(clip) || clip->channels!=1 || clip->width!=target->width || clip->height!=target->height || overlap(target,clip))))
    return exr_fail(e,EXR_ARGUMENT,"Invalid affine image bitmap, alpha or clip");
  for(i=0;i<6;i++) if(!isfinite(m[i]) || fabs(m[i])>1e7) return exr_fail(e,EXR_ARGUMENT,"Invalid affine image transform");
  if(!work) work=&local_work;
  if(exr_control_cancel(control,e)!=EXR_OK) return EXR_CANCELLED;
  det=m[0]*m[3]-m[1]*m[2];
  if(!det || !alpha) return exr_fail(e,EXR_OK,"");
  inv[0]=m[3]/det; inv[1]=-m[1]/det; inv[2]=-m[2]/det; inv[3]=m[0]/det;
  inv[4]=-(inv[0]*m[4]+inv[2]*m[5]); inv[5]=-(inv[1]*m[4]+inv[3]*m[5]);
  for(i=0;i<6;i++) if(!isfinite(inv[i])) return exr_fail(e,EXR_LIMIT,"Affine image inverse exceeds precision");
  for(i=0;i<4;i++) {
    double px=m[4]+(i&1 ? m[0] : 0)+(i&2 ? m[2] : 0),py=m[5]+(i&1 ? m[1] : 0)+(i&2 ? m[3] : 0);
    if(!isfinite(px) || !isfinite(py) || fabs(px)>1e7 || fabs(py)>1e7) return exr_fail(e,EXR_LIMIT,"Affine image bounds exceed coordinate budget");
    left=fmin(left,px); right=fmax(right,px); top=fmin(top,py); bottom=fmax(bottom,py);
  }
  x0=(int)fmax(0,floor(left)); x1=(int)fmin(target->width,ceil(right)); y0=(int)fmax(0,floor(top)); y1=(int)fmin(target->height,ceil(bottom));
  for(y=y0;y<y1;y++) {
    if(exr_control_cancel(control,e)!=EXR_OK) return EXR_CANCELLED;
    if(!exr_vector_work(work,(size_t)(x1>x0 ? x1-x0 : 0)*(interpolate ? 20 : 8))) return exr_fail(e,EXR_LIMIT,"Affine image work budget exceeded");
    for(x=x0;x<x1;x++) {
      double sums[4]={0}; unsigned sx,sy,k,coverage=clip ? clip->pixels[(size_t)y*clip->stride+(unsigned)x] : 255; uint32_t color=0;
      if(!coverage) continue;
      for(sy=0;sy<2;sy++) for(sx=0;sx<2;sx++) {
        double px=x+.25+.5*sx,py=y+.25+.5*sy,u=inv[0]*px+inv[2]*py+inv[4],v=inv[1]*px+inv[3]*py+inv[5],s[4];
        if(!isfinite(u) || !isfinite(v)) return exr_fail(e,EXR_LIMIT,"Affine image sample exceeds precision");
        if(u<0 || u>=1 || v<0 || v>=1) continue;
        sample(source,u,v,interpolate,s); for(k=0;k<4;k++) sums[k]+=s[k];
      }
      if(!sums[3]) continue;
      for(k=0;k<3;k++) color|=(uint32_t)fmin(255,floor(sums[k]/sums[3]+.5))<<(24-8*k);
      color|=(uint32_t)fmin(255,floor(sums[3]*alpha/4+.5)); exr_pixel(target,x,y,color,coverage);
    }
  }
  return exr_fail(e,EXR_OK,"");
}
