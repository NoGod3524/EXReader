/* SPDX-License-Identifier: MIT */
#include "vector_internal.h"
#include "pixels_internal.h"
#ifdef EXR_PROFILE_IMAGE
#include <windows.h>
#include <stdio.h>
static struct { unsigned long long ticks[4],pixels,sampled,samples; int active,depth; } image_profile;
static unsigned long long image_tick(void) { LARGE_INTEGER t; QueryPerformanceCounter(&t); return (unsigned long long)t.QuadPart; }
static double image_clock_overhead(void) {
  static double overhead; unsigned i; unsigned long long total=0;
  if(!overhead) { for(i=0;i<100000;i++) { unsigned long long a=image_tick(); total+=image_tick()-a; } overhead=total/100000.; }
  return overhead;
}
#endif
#if defined(EXR_PROFILE_IMAGE) && EXR_PROFILE_IMAGE == 1
#define IMAGE_START(name) unsigned long long name=image_profile.active ? image_tick() : 0
#define IMAGE_STOP(name,bucket) do { if(image_profile.active) image_profile.ticks[bucket]+=image_tick()-name; } while(0)
#else
#define IMAGE_START(name)
#define IMAGE_STOP(name,bucket)
#endif
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
static void texture_sample(const exr_vector_texture *texture,double u,double v,double out[4],double *shape,unsigned flags) {
  unsigned k;
#if defined(EXR_PROFILE_IMAGE) && EXR_PROFILE_IMAGE == 1
  int root=image_profile.depth++==0;
  unsigned long long start=root && image_profile.active ? image_tick() : 0;
#endif
  sample(&texture->bitmap,u,v,(int)texture->interpolate,out);
#if defined(EXR_PROFILE_IMAGE) && EXR_PROFILE_IMAGE == 1
  if(root) { IMAGE_STOP(start,0); if(image_profile.active) image_profile.samples++; }
#endif
  if(shape) *shape=flags&EXR_ALPHA_IMAGE_SHAPE ? out[3]/255. : 1;
  if(texture->mask) {
    double mask[4],a;
    IMAGE_START(mask_start);
    texture_sample(texture->mask,u,v,mask,NULL,0);
    IMAGE_STOP(mask_start,1);
    IMAGE_START(matte_start);
    a=(texture->mask_mode==1 ? mask[0]/255 : mask[3])/255;
    if(texture->has_matte && out[3]) {
      for(k=0;k<3;k++) out[k]=a ? fmax(0,fmin(255,(out[k]/out[3]-(1-a)*texture->matte[k]*255)/a))*out[3]*a : 0;
    } else for(k=0;k<3;k++) out[k]*=a;
    out[3]*=a;
    if(shape && (texture->mask_mode==2 || (flags&EXR_ALPHA_CONSTANT_SHAPE))) *shape*=a;
    IMAGE_STOP(matte_start,2);
  }
#if defined(EXR_PROFILE_IMAGE) && EXR_PROFILE_IMAGE == 1
  image_profile.depth--;
#endif
}
/* Matching nearest-neighbor layers share the texel address. Keep the two mask
   divisions and subsequent products in the same order as texture_sample. */
static void masked_nearest_sample(const exr_vector_texture *texture,double u,double v,double out[4],double *shape,unsigned flags) {
  const exr_bitmap *b=&texture->bitmap,*mask=&texture->mask->bitmap;
  const unsigned char *p,*q; unsigned k; double a;
  IMAGE_START(source_start);
  uint32_t x=(uint32_t)(u*b->width),y=(uint32_t)(v*b->height);
  if(x>=b->width) x=b->width-1;
  if(y>=b->height) y=b->height-1;
  p=b->pixels+(size_t)y*b->stride+x*4;
  out[3]=p[3]; for(k=0;k<3;k++) out[k]=p[k]*out[3];
  IMAGE_STOP(source_start,0);
#if defined(EXR_PROFILE_IMAGE) && EXR_PROFILE_IMAGE == 1
  if(image_profile.active) image_profile.samples++;
#endif
  *shape=flags&EXR_ALPHA_IMAGE_SHAPE ? out[3]/255. : 1;
  IMAGE_START(mask_start);
  q=mask->pixels+(size_t)y*mask->stride+x*4;
  a=texture->mask_mode==1 ? (double)q[0]*q[3] : q[3];
  IMAGE_STOP(mask_start,1);
  IMAGE_START(apply_start);
  a=(texture->mask_mode==1 ? a/255 : a)/255;
  for(k=0;k<3;k++) out[k]*=a;
  out[3]*=a;
  if(texture->mask_mode==2 || (flags&EXR_ALPHA_CONSTANT_SHAPE)) *shape*=a;
  IMAGE_STOP(apply_start,2);
}
/* Sample sums produce finite, nonnegative channel values bounded by 255.
   Truncation after +.5 is the same rounding as floor, including saturation. */
static uint32_t image_byte(double value) {
  uint32_t rounded=(uint32_t)(value+.5); return rounded>255 ? 255 : rounded;
}
static void ink_sample(const exr_vector_texture *source,const exr_bitmap *inks,double u,double v,double out[5],double *shape,unsigned flags) {
  double rgba[4],weights[4]={1,0,0,0},a=0;unsigned i,k,n=1;uint32_t xs[4],ys[4];
  texture_sample(source,u,v,rgba,shape,flags);memset(out,0,5*sizeof(*out));
  if(source->interpolate) {
    double x=fmax(0,fmin(inks->width-1,u*inks->width-.5)),y=fmax(0,fmin(inks->height-1,v*inks->height-.5));
    double wx=x-floor(x),wy=y-floor(y);n=4;
    xs[0]=xs[2]=(uint32_t)x;ys[0]=ys[1]=(uint32_t)y;
    xs[1]=xs[3]=xs[0]+1<inks->width ? xs[0]+1 : xs[0];
    ys[2]=ys[3]=ys[0]+1<inks->height ? ys[0]+1 : ys[0];
    weights[0]=(1-wx)*(1-wy);weights[1]=wx*(1-wy);weights[2]=(1-wx)*wy;weights[3]=wx*wy;
  } else { xs[0]=(uint32_t)fmin(inks->width-1,u*inks->width);ys[0]=(uint32_t)fmin(inks->height-1,v*inks->height); }
  for(i=0;i<n;i++) {
    const unsigned char *p=inks->pixels+(size_t)ys[i]*inks->stride+xs[i]*4;
    double w=weights[i]*source->bitmap.pixels[(size_t)ys[i]*source->bitmap.stride+xs[i]*4+3];a+=w;
    for(k=0;k<4;k++) out[k]+=p[k]*w;
  }
  if(a) for(k=0;k<4;k++) out[k]*=rgba[3]/a;
  out[4]=rgba[3];
}
exr_status exr_vector_texture_blend_inks(exr_bitmap *target,const exr_vector_texture *source,const exr_bitmap *inks,const double m[6],double alpha,
                                     const exr_bitmap *clip,exr_blend_mode mode,exr_composite_state *state,size_t *work,const exr_control *control,exr_error *e) {
  size_t local_work=0,i; double det,inv[6],left=1e7,top=1e7,right=-1e7,bottom=-1e7; int x0,y0,x1,y1,x,y;
  const exr_vector_texture *layers[16],*layer=source; size_t depth=0,cost=0; int paired_nearest;
  if(mode<EXR_BLEND_NORMAL || mode>EXR_BLEND_LUMINOSITY) return exr_fail(e,EXR_ARGUMENT,"Invalid affine image blend mode");
  if(!storage(target) || !source || !m || !isfinite(alpha) || alpha<0 || alpha>1 ||
     (clip && (!storage(clip) || clip->channels!=1 || clip->width!=target->width || clip->height!=target->height || overlap(target,clip))))
    return exr_fail(e,EXR_ARGUMENT,"Invalid affine image bitmap, alpha or clip");
  if(inks && (!storage(inks) || inks->channels!=4 || inks->width!=source->bitmap.width ||
      inks->height!=source->bitmap.height || overlap(target,inks) || source->has_matte))
    return exr_fail(e,EXR_ARGUMENT,"Invalid native CMYK image samples");
  if(inks && (!state || !state->cmyk_pixels)) inks=NULL;
  while(layer) {
    if(depth==16) return exr_fail(e,EXR_LIMIT,"Affine image mask depth exceeds 16");
    for(i=0;i<depth;i++) if(layers[i]==layer) return exr_fail(e,EXR_ARGUMENT,"Cyclic affine image mask");
    if(!storage(&layer->bitmap) || layer->bitmap.channels!=4 || overlap(target,&layer->bitmap) ||
       (layer->mask && layer->mask_mode!=1 && layer->mask_mode!=2)) return exr_fail(e,EXR_ARGUMENT,"Invalid affine image layer");
    if(layer->has_matte) for(i=0;i<3;i++) if(!isfinite(layer->matte[i]) || layer->matte[i]<0 || layer->matte[i]>1)
      return exr_fail(e,EXR_ARGUMENT,"Invalid affine image matte");
    cost+=layer->interpolate ? 24 : 12; layers[depth++]=layer; layer=layer->mask;
  }
  cost+=state ? 20+state->depth*4 : 0;
  cost+=inks ? 40 : 0;
  cost+=mode==EXR_BLEND_NORMAL ? 0 : mode<EXR_BLEND_HUE ? 24 : 64;
  paired_nearest=!inks && !source->interpolate && !source->has_matte && source->mask &&
    !source->mask->interpolate && !source->mask->mask && source->bitmap.width==source->mask->bitmap.width &&
    source->bitmap.height==source->mask->bitmap.height;
  for(i=0;i<6;i++) if(!isfinite(m[i]) || fabs(m[i])>1e7) return exr_fail(e,EXR_ARGUMENT,"Invalid affine image transform");
  if(!work) work=&local_work;
  if(exr_control_cancel(control,e)!=EXR_OK) return EXR_CANCELLED;
  det=m[0]*m[3]-m[1]*m[2];
  if(!det || (!alpha && (!state || !(state->knockout || state->shape) || (state->alpha_flags&EXR_ALPHA_CONSTANT_SHAPE)))) return exr_fail(e,EXR_OK,"");
  inv[0]=m[3]/det; inv[1]=-m[1]/det; inv[2]=-m[2]/det; inv[3]=m[0]/det;
  inv[4]=-(inv[0]*m[4]+inv[2]*m[5]); inv[5]=-(inv[1]*m[4]+inv[3]*m[5]);
  for(i=0;i<6;i++) if(!isfinite(inv[i])) return exr_fail(e,EXR_LIMIT,"Affine image inverse exceeds precision");
  for(i=0;i<4;i++) {
    double px=m[4]+(i&1 ? m[0] : 0)+(i&2 ? m[2] : 0),py=m[5]+(i&1 ? m[1] : 0)+(i&2 ? m[3] : 0);
    if(!isfinite(px) || !isfinite(py) || fabs(px)>1e7 || fabs(py)>1e7) return exr_fail(e,EXR_LIMIT,"Affine image bounds exceed coordinate budget");
    left=fmin(left,px); right=fmax(right,px); top=fmin(top,py); bottom=fmax(bottom,py);
  }
  x0=(int)fmax(0,floor(left)); x1=(int)fmin(target->width,ceil(right)); y0=(int)fmax(0,floor(top)); y1=(int)fmin(target->height,ceil(bottom));
#ifdef EXR_PROFILE_IMAGE
  memset(&image_profile,0,sizeof(image_profile));
  unsigned long long loop_start=image_tick();
#endif
  for(y=y0;y<y1;y++) {
    if(exr_control_cancel(control,e)!=EXR_OK) return EXR_CANCELLED;
    if(!exr_vector_work(work,(size_t)(x1>x0 ? x1-x0 : 0)*cost)) return exr_fail(e,EXR_LIMIT,"Affine image work budget exceeded");
    for(x=x0;x<x1;x++) {
      double sums[5]={0},shape_sum=0; unsigned sx,sy,k,coverage=clip ? clip->pixels[(size_t)y*clip->stride+(unsigned)x] : 255; uint32_t color=0;
      if(!coverage) continue;
#if defined(EXR_PROFILE_IMAGE) && EXR_PROFILE_IMAGE == 1
      image_profile.active=(image_profile.pixels++ % 256)==0;
      image_profile.sampled+=image_profile.active;
#endif
      for(sy=0;sy<2;sy++) for(sx=0;sx<2;sx++) {
        double px=x+.25+.5*sx,py=y+.25+.5*sy,u=inv[0]*px+inv[2]*py+inv[4],v=inv[1]*px+inv[3]*py+inv[5],s[5],sample_shape;
        if(!isfinite(u) || !isfinite(v)) return exr_fail(e,EXR_LIMIT,"Affine image sample exceeds precision");
        if(u<0 || u>=1 || v<0 || v>=1) continue;
        if(inks) ink_sample(source,inks,u,v,s,&sample_shape,state ? state->alpha_flags : 0);
        else if(paired_nearest) masked_nearest_sample(source,u,v,s,&sample_shape,state ? state->alpha_flags : 0);
        else texture_sample(source,u,v,s,&sample_shape,state ? state->alpha_flags : 0);
        shape_sum+=sample_shape;
        for(k=0;k<(inks ? 5u : 4u);k++) sums[k]+=s[k];
      }
      IMAGE_START(composite_start);
      if(state && (state->knockout || state->shape)) {
        double object_alpha,shape,source_alpha=sums[inks ? 4 : 3]/(4*255.);
        exr_pixel_alpha_shape(state,(size_t)x,(size_t)y,source_alpha,shape_sum/4,alpha,coverage,&object_alpha,&shape);
        if(!shape) continue;
        if(inks) {
          double cmyk[4];for(k=0;k<4;k++) cmyk[k]=source_alpha ? sums[k]/(255*sums[4]) : 0;
          exr_pixel_object_cmyk(target,x,y,cmyk,object_alpha,shape,mode,state);
        } else {
          if(source_alpha) for(k=0;k<3;k++) color|=image_byte(sums[k]/sums[3])<<(24-8*k);
          exr_pixel_object(target,x,y,color,object_alpha,shape,mode,state);
        }
        IMAGE_STOP(composite_start,3);
        continue;
      }
      if(inks) {
        double cmyk[4];if(!sums[4]) continue;
        for(k=0;k<4;k++) cmyk[k]=sums[k]/(255*sums[4]);
        exr_pixel_composite_cmyk(target,x,y,cmyk,sums[4]*alpha/(4*255),coverage,mode,state);continue;
      }
      if(!sums[3]) { IMAGE_STOP(composite_start,3); continue; }
      for(k=0;k<3;k++) color|=image_byte(sums[k]/sums[3])<<(24-8*k);
      color|=image_byte(sums[3]*alpha/4); if(state) exr_pixel_composite(target,x,y,color,coverage,mode,state);else if(mode==EXR_BLEND_NORMAL) exr_pixel(target,x,y,color,coverage);else exr_pixel_blend(target,x,y,color,coverage,mode);
      IMAGE_STOP(composite_start,3);
    }
  }
#ifdef EXR_PROFILE_IMAGE
  { unsigned long long elapsed=image_tick()-loop_start; LARGE_INTEGER frequency; const char *path=getenv("EXR_PROFILE_IMAGE_OUT");
    QueryPerformanceFrequency(&frequency);
#if EXR_PROFILE_IMAGE == 2
    for(y=y0;y<y1;y++) for(x=x0;x<x1;x++) if(!clip || clip->pixels[(size_t)y*clip->stride+(unsigned)x]) image_profile.pixels++;
#endif
    if(path) { FILE *f=fopen(path,"a"); if(f) {
      fprintf(f,"%u,%u,%u,%u,%u,%u,%u,%u,%llu,%llu,%llu,%llu,%llu,%llu,%llu,%llu,%llu,%.6f,%u,%u,%u,%u\n",target->width,source->bitmap.width,source->bitmap.height,source->interpolate,source->mask!=NULL,source->has_matte,state!=NULL,state ? state->depth : 0,image_profile.pixels,image_profile.sampled,image_profile.samples,image_profile.ticks[0],image_profile.ticks[1],image_profile.ticks[2],image_profile.ticks[3],elapsed,(unsigned long long)frequency.QuadPart,image_clock_overhead(),source->mask ? source->mask->interpolate : 0,source->mask ? source->mask->bitmap.width : 0,source->mask ? source->mask->bitmap.height : 0,(unsigned)mode);
      fclose(f);
    } }
  }
#endif
  return exr_fail(e,EXR_OK,"");
}
exr_status exr_vector_texture_blend(exr_bitmap *target,const exr_vector_texture *source,const double m[6],double alpha,
  const exr_bitmap *clip,exr_blend_mode mode,exr_composite_state *state,size_t *work,const exr_control *control,exr_error *e) {
  return exr_vector_texture_blend_inks(target,source,NULL,m,alpha,clip,mode,state,work,control,e);
}
exr_status exr_vector_image(exr_bitmap *target,const exr_bitmap *source,const double m[6],double alpha,
                             int interpolate,const exr_bitmap *clip,size_t *work,const exr_control *control,exr_error *e) {
  exr_vector_texture texture={0}; if(source) texture.bitmap=*source; texture.interpolate=interpolate!=0;
  return exr_vector_texture_paint(target,&texture,m,alpha,clip,work,control,e);
}

exr_status exr_vector_texture_paint(exr_bitmap *target,const exr_vector_texture *source,const double matrix[6],double alpha,
  const exr_bitmap *clip,size_t *work,const exr_control *control,exr_error *error) {
  return exr_vector_texture_blend(target,source,matrix,alpha,clip,EXR_BLEND_NORMAL,NULL,work,control,error);
}
