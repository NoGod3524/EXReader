/* SPDX-License-Identifier: MIT */
#include "vector_internal.h"
#include "pixels_internal.h"
#include <fenv.h>
#if defined(__SSE2__) || defined(_M_X64)
#include <emmintrin.h>
#endif
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
typedef struct {
  double fraction;
  int first, second;
} image_tap;

static inline image_tap bilinear_tap(double coordinate, unsigned length) {
  double pos=coordinate*length-.5,max=length-1;
  pos=pos<=0 ? 0 : pos>max ? max : pos;
  int first=(int)pos;
  return (image_tap){pos-first,first,first+1<(int)length ? first+1 : first};
}

static inline void bilinear_sample(const unsigned char *row0,const unsigned char *row1,image_tap x,double wy,double out[4]) {
  double wx=x.fraction,weights[4]={(1-wx)*(1-wy),wx*(1-wy),(1-wx)*wy,wx*wy};
  const unsigned char *p[4]={row0+x.first*4,row0+x.second*4,row1+x.first*4,row1+x.second*4};
#if defined(__SSE2__) || defined(_M_X64)
  __m128d rg=_mm_setzero_pd(),ba=_mm_setzero_pd();
  for(unsigned i=0;i<4;i++) {
    int rgba;
    memcpy(&rgba,p[i],sizeof(rgba));
    __m128i channels=_mm_cvtsi32_si128(rgba);
    channels=_mm_unpacklo_epi8(channels,_mm_setzero_si128());
    channels=_mm_unpacklo_epi16(channels,_mm_setzero_si128());
    double a=p[i][3]*weights[i];
    rg=_mm_add_pd(rg,_mm_mul_pd(_mm_cvtepi32_pd(channels),_mm_set1_pd(a)));
    __m128d blue=_mm_cvtepi32_pd(_mm_srli_si128(channels,8));
    ba=_mm_add_pd(ba,_mm_unpacklo_pd(_mm_mul_sd(blue,_mm_set_sd(a)),_mm_set_sd(a)));
  }
  _mm_storeu_pd(out,rg);_mm_storeu_pd(out+2,ba);
#else
  double red=0,green=0,blue=0,alpha=0;
  for(unsigned i=0;i<4;i++) {
    double a=p[i][3]*weights[i];
    red+=p[i][0]*a;green+=p[i][1]*a;blue+=p[i][2]*a;alpha+=a;
  }
  out[0]=red;out[1]=green;out[2]=blue;out[3]=alpha;
#endif
}

static void sample(const exr_bitmap *b,double u,double v,int interpolate,double out[4]) {
  if(!interpolate) {
    uint32_t x=(uint32_t)(u*b->width),y=(uint32_t)(v*b->height); const unsigned char *p;
    if(x>=b->width) x=b->width-1;
    if(y>=b->height) y=b->height-1;
    p=b->pixels+(size_t)y*b->stride+x*4; out[3]=p[3]; for(unsigned k=0;k<3;k++) out[k]=p[k]*out[3];
  } else {
    image_tap x=bilinear_tap(u,b->width),y=bilinear_tap(v,b->height);
    bilinear_sample(b->pixels+(size_t)y.first*b->stride,b->pixels+(size_t)y.second*b->stride,x,y.fraction,out);
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
/* Validate the constant color and opaque gray-mask texels before using the
   integer sample sum. Stride padding is outside the sampled image. */
static int solid_with_opaque_mask(const exr_bitmap *color,const exr_bitmap *mask) {
  size_t bytes=(size_t)color->width*4;
  if(color->pixels[3]!=255) return 0;
  for(size_t y=0;y<color->height;y++) {
    const unsigned char *row=color->pixels+y*color->stride;
    const unsigned char *gray=mask->pixels+y*mask->stride;
    unsigned opaque=255;
    if(memcmp(row,color->pixels,4) || memcmp(row,row+4,bytes-4)) return 0;
    for(size_t x=3;x<bytes;x+=4) opaque&=gray[x];
    if(opaque!=255) return 0;
  }
  return 1;
}
static int nearest_index(double coordinate,unsigned extent) {
  unsigned index;
  if(coordinate<0 || coordinate>=1) return -1;
  index=(unsigned)(coordinate*extent);
  return (int)(index<extent ? index : extent-1);
}
#if defined(__GNUC__)
__attribute__((noinline))
#elif defined(_MSC_VER)
__declspec(noinline)
#endif
static exr_status solid_mask_blend(exr_bitmap *target,const exr_bitmap *mask,const double inv[6],
                                  const exr_clip_mask *clip,int x0,int y0,int x1,int y1,int *columns,uint32_t rgb,
                                  size_t cost,exr_raster_work *work,const exr_control *control,exr_error *e) {
  double px0=x0+.25,py0=y0+.25;
#if defined(__SSE2__) || defined(_M_X64)
  const __m128i rgba=_mm_setr_epi16((short)(rgb>>24),(short)((rgb>>16)&255),(short)((rgb>>8)&255),255,0,0,0,0);
#endif
  /* The cross terms are zero. Retain the general sampler's expression so
     multiply-add contraction cannot move a tap across a texel boundary. */
  for(int x=x0;x<x1;x++) {
    columns[2*(x-x0)]=nearest_index(inv[0]*(x+.25)+inv[2]*py0+inv[4],mask->width);
    columns[2*(x-x0)+1]=nearest_index(inv[0]*(x+.75)+inv[2]*py0+inv[4],mask->width);
  }
  for(int y=y0;y<y1;y++) {
    int y_first=nearest_index(inv[1]*px0+inv[3]*(y+.25)+inv[5],mask->height);
    int y_second=nearest_index(inv[1]*px0+inv[3]*(y+.75)+inv[5],mask->height);
    const unsigned char *first=y_first<0 ? NULL : mask->pixels+(size_t)y_first*mask->stride;
    const unsigned char *second=y_second<0 ? NULL : mask->pixels+(size_t)y_second*mask->stride;
    const unsigned char *coverage=exr_clip_row(clip,(size_t)y);
    const int *column=columns;
    if(exr_control_cancel(control,e)!=EXR_OK) return EXR_CANCELLED;
    if(!exr_vector_work(work,(size_t)(x1-x0)*cost)) return exr_fail(e,EXR_LIMIT,"Affine image work budget exceeded");
    if(!first && !second) continue;
    for(int x=x0;x<x1;x++,column+=2) {
      unsigned opacity=0,covered=coverage ? coverage[x] : 255;
      if(!covered) continue;
      for(unsigned tap=0;tap<2;tap++) if(column[tap]>=0) {
        int offset=column[tap]*4;
        if(first) opacity+=first[offset];
        if(second) opacity+=second[offset];
      }
      /* With opaque source and mask texels each quarter sample contributes
         its gray byte exactly. Missing taps contribute zero. Every nonzero
         premultiplied RGB sample has the same straight color. */
      opacity=(opacity+2)/4;
#if defined(__SSE2__) || defined(_M_X64)
      if(opacity && target->channels==4) {
        unsigned char *p=target->pixels+(size_t)y*target->stride+(size_t)x*4;
        if(p[3]==255) {
          unsigned a=opacity*covered/255;int packed;memcpy(&packed,p,4);
          __m128i dst=_mm_unpacklo_epi8(_mm_cvtsi32_si128(packed),_mm_setzero_si128());
          __m128i sum=_mm_add_epi16(_mm_mullo_epi16(dst,_mm_set1_epi16((short)(255-a))),_mm_mullo_epi16(rgba,_mm_set1_epi16((short)a)));
          /* For 0 <= n <= 65025, (n+127)/255 equals (t+(t>>8))>>8,
             t=n+128. All intermediate unsigned lanes fit in 16 bits. */
          sum=_mm_add_epi16(sum,_mm_set1_epi16(128));
          sum=_mm_srli_epi16(_mm_add_epi16(sum,_mm_srli_epi16(sum,8)),8);
          packed=_mm_cvtsi128_si32(_mm_packus_epi16(sum,_mm_setzero_si128()));memcpy(p,&packed,4);
          continue;
        }
      }
#endif
      if(opacity) exr_pixel(target,x,y,rgb|opacity,covered);
    }
  }
  return exr_fail(e,EXR_OK,"");
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
/* Four opaque nearest taps reduce to a rounded byte average. Each 16-bit
   lane holds at most 4*255+2. Pair alternate bytes to keep carries local. */
static inline uint32_t average_four_rgba(uint32_t a,uint32_t b,uint32_t c,uint32_t d) {
  const uint32_t lanes=0x00ff00ffu,round=0x00020002u;
  uint32_t even=((a&lanes)+(b&lanes)+(c&lanes)+(d&lanes)+round)>>2;
  uint32_t odd=(((a>>8)&lanes)+((b>>8)&lanes)+((c>>8)&lanes)+((d>>8)&lanes)+round)>>2;
  return (even&lanes)|((odd&lanes)<<8);
}
/* Axis-aligned, unmasked nearest-neighbor images without a composite state.
   With inv[1] and inv[2] zero, u depends only on the column and v only on the
   row, so the texel of every subsample is tabulated once with the generic
   loop's expressions. Nearest sums are exact integers in the generic double
   path, so integer accumulation followed by the same divisions is identical.
   Returns 0 when the case does not apply; the generic loop then runs. */
static int nearest_axis(exr_bitmap *target,const exr_vector_texture *source,const double inv[6],double alpha,
                        const exr_clip_mask *clip,exr_blend_mode mode,int x0,int y0,int x1,int y1,size_t cost,
                        exr_raster_work *work,const exr_control *control,exr_error *e,exr_status *result) {
  const exr_bitmap *b=&source->bitmap; size_t width=(size_t)(x1-x0),height=(size_t)(y1-y0),k; int32_t *columns,*rows; int x,y;
  if(source->interpolate || source->mask || source->has_matte || target->channels!=4 || inv[1]!=0 || inv[2]!=0 || x1<=x0 || y1<=y0) return 0;
  columns=malloc((2*width+2*height)*sizeof(*columns)); if(!columns) return 0;
  rows=columns+2*width;
  for(k=0;k<2*width;k++) {
    double px=(x0+(int)(k>>1))+.25+.5*(double)(k&1),py=y0+.25,u=inv[0]*px+inv[2]*py+inv[4];
    if(!isfinite(u)) { free(columns); return 0; }
    if(u<0 || u>=1) columns[k]=-1;
    else { uint32_t t=(uint32_t)(u*b->width); columns[k]=(int32_t)(t>=b->width ? b->width-1 : t)*4; }
  }
  for(k=0;k<2*height;k++) {
    double px=x0+.25,py=(y0+(int)(k>>1))+.25+.5*(double)(k&1),v=inv[1]*px+inv[3]*py+inv[5];
    if(!isfinite(v)) { free(columns); return 0; }
    if(v<0 || v>=1) rows[k]=-1;
    else { uint32_t t=(uint32_t)(v*b->height); rows[k]=(int32_t)(t>=b->height ? b->height-1 : t); }
  }
  for(y=y0;y<y1;y++) {
    const int32_t *ry=rows+2*(size_t)(y-y0); const unsigned char *line[2];
    const unsigned char *mask=exr_clip_row(clip,(size_t)y);
    if(exr_control_cancel(control,e)!=EXR_OK) { free(columns); *result=EXR_CANCELLED; return 1; }
    if(!exr_vector_work(work,width*cost)) { free(columns); *result=exr_fail(e,EXR_LIMIT,"Affine image work budget exceeded"); return 1; }
    if(ry[0]<0 && ry[1]<0) continue;
    for(k=0;k<2;k++) line[k]=ry[k]<0 ? NULL : b->pixels+(size_t)ry[k]*b->stride;
    for(x=x0;x<x1;x++) {
      const int32_t *cx=columns+2*(size_t)(x-x0); unsigned coverage=mask ? mask[x] : 255,sy,sx; uint32_t s[4]={0},color=0;
      const unsigned char *first=NULL; int same=1;
      if(!coverage) continue;
      if(alpha==1 && mode==EXR_BLEND_NORMAL && coverage==255 && line[0] && line[1] && cx[0]>=0 && cx[1]>=0) {
        const unsigned char *p0=line[0]+cx[0],*p1=line[0]+cx[1],*p2=line[1]+cx[0],*p3=line[1]+cx[1];
        if((p0[3]&p1[3]&p2[3]&p3[3])==255) {
          uint32_t a,bv,c,d;
          memcpy(&a,p0,4); memcpy(&bv,p1,4); memcpy(&c,p2,4); memcpy(&d,p3,4);
          uint32_t rgba=average_four_rgba(a,bv,c,d);
          memcpy(target->pixels+(size_t)y*target->stride+(size_t)x*4,&rgba,4);
          continue;
        }
      }
      for(sy=0;sy<2;sy++) {
        if(!line[sy]) continue;
        for(sx=0;sx<2;sx++) {
          const unsigned char *p; unsigned a;
          if(cx[sx]<0) continue;
          p=line[sy]+cx[sx]; a=p[3];
          if(!first) first=p; else if(p!=first) same=0;
          s[3]+=a; s[0]+=p[0]*a; s[1]+=p[1]*a; s[2]+=p[2]*a;
        }
      }
      if(!s[3]) continue;
      /* One texel: each quotient is that texel's integer channel exactly. */
      if(same) color=((uint32_t)first[0]<<24)|((uint32_t)first[1]<<16)|((uint32_t)first[2]<<8);
      else for(k=0;k<3;k++) color|=image_byte((double)s[k]/(double)s[3])<<(24-8*k);
      color|=image_byte((double)s[3]*alpha/4);
      if(mode==EXR_BLEND_NORMAL) exr_pixel(target,x,y,color,coverage); else exr_pixel_blend(target,x,y,color,coverage,mode);
    }
  }
  free(columns); *result=exr_fail(e,EXR_OK,""); return 1;
}
#if defined(__SSE2__) || defined(_M_X64)
/* A source row converted once to doubles: {r,g,b,1} per texel plus a separate
   alpha array, covering texels lo..hi. One texel past the last image column
   repeats it, so the clamped right-edge tap (second==first) reads first+1. */
typedef struct { int row; double *rgb1,*alpha; } converted_row;
static void convert_row(const exr_bitmap *source,int row,unsigned lo,unsigned hi,converted_row *out) {
  const unsigned char *line=source->pixels+(size_t)row*source->stride;
  for(unsigned x=lo;x<=hi;x++) {
    const unsigned char *p=line+(size_t)(x<source->width ? x : source->width-1)*4;
    double *q=out->rgb1+4*(size_t)(x-lo);
    q[0]=p[0];q[1]=p[1];q[2]=p[2];q[3]=1;out->alpha[x-lo]=p[3];
  }
  out->row=row;
}
static const converted_row *find_row(converted_row slots[4],const int need[4],unsigned count,int row,
                                     const exr_bitmap *source,unsigned lo,unsigned hi) {
  unsigned s,k;
  for(s=0;s<4;s++) if(slots[s].row==row) return slots+s;
  for(s=0;s<4;s++) {
    for(k=0;k<count && need[k]!=slots[s].row;k++) {}
    if(k==count) break;
  }
  convert_row(source,row,lo,hi,slots+s);
  return slots+s;
}
/* One bilinear sample from converted rows, added to the running sums. With
   w=[1-wx,wx] the weight products, tap alphas, channel products and the
   sequential tap order are the scalar sampler's; 1*a is a exactly, and the
   scalar sampler's 0+x is x for these nonnegative terms. */
static inline void converted_sample(const converted_row *r0,const converted_row *r1,size_t index,
                                    __m128d w,__m128d wy0,__m128d wy1,__m128d *rg,__m128d *ba) {
  const double *t0=r0->rgb1+4*index,*t1=r1->rgb1+4*index;
  __m128d a01=_mm_mul_pd(_mm_loadu_pd(r0->alpha+index),_mm_mul_pd(w,wy0));
  __m128d a23=_mm_mul_pd(_mm_loadu_pd(r1->alpha+index),_mm_mul_pd(w,wy1));
  __m128d a=_mm_unpacklo_pd(a01,a01);
  __m128d red_green=_mm_mul_pd(_mm_loadu_pd(t0),a),blue_alpha=_mm_mul_pd(_mm_loadu_pd(t0+2),a);
  a=_mm_unpackhi_pd(a01,a01);
  red_green=_mm_add_pd(red_green,_mm_mul_pd(_mm_loadu_pd(t0+4),a));
  blue_alpha=_mm_add_pd(blue_alpha,_mm_mul_pd(_mm_loadu_pd(t0+6),a));
  a=_mm_unpacklo_pd(a23,a23);
  red_green=_mm_add_pd(red_green,_mm_mul_pd(_mm_loadu_pd(t1),a));
  blue_alpha=_mm_add_pd(blue_alpha,_mm_mul_pd(_mm_loadu_pd(t1+2),a));
  a=_mm_unpackhi_pd(a23,a23);
  red_green=_mm_add_pd(red_green,_mm_mul_pd(_mm_loadu_pd(t1+4),a));
  blue_alpha=_mm_add_pd(blue_alpha,_mm_mul_pd(_mm_loadu_pd(t1+6),a));
  *rg=_mm_add_pd(*rg,red_green);*ba=_mm_add_pd(*ba,blue_alpha);
}
#endif
#if defined(__SSE2__) || defined(_M_X64)
/* One layer of the axis path: column taps on its own width, and for an
   interpolated layer the converted-row cache over the used span. A nearest
   layer stores the generic sampler's clamped texel in first. */
typedef struct { const exr_bitmap *bitmap; image_tap *columns; double *storage; converted_row slots[4]; unsigned lo,hi; int interpolate; } axis_layer;
static void axis_layer_free(axis_layer *l) { free(l->columns);free(l->storage); }
static int axis_layer_init(axis_layer *l,const exr_bitmap *b,int interpolate,const double inv[6],int x0,int y0,size_t width) {
  memset(l,0,sizeof(*l)); l->bitmap=b; l->interpolate=interpolate; l->lo=b->width;
  l->columns=malloc(2*width*sizeof(*l->columns)); if(!l->columns) return 0;
  for(size_t i=0;i<2*width;i++) {
    double px=(x0+(int)(i>>1))+.25+.5*(i&1),u=inv[0]*px+inv[2]*(y0+.25)+inv[4];
    if(u<0 || u>=1) { l->columns[i]=(image_tap){0,-1,-1}; continue; }
    if(!interpolate) { uint32_t t=(uint32_t)(u*b->width); if(t>=b->width) t=b->width-1; l->columns[i]=(image_tap){0,(int)t,(int)t}; continue; }
    l->columns[i]=bilinear_tap(u,b->width);
    if((unsigned)l->columns[i].first<l->lo) l->lo=(unsigned)l->columns[i].first;
    if((unsigned)l->columns[i].first+1>l->hi) l->hi=(unsigned)l->columns[i].first+1;
  }
  if(!interpolate) return 1;
  /* Convert each source row once when the used span is comparable to the
     destination width; strong minification keeps per-tap conversion. */
  if(l->lo>l->hi || (size_t)(l->hi-l->lo)>4*width) return 0;
  size_t span=(size_t)(l->hi-l->lo+1);
  l->storage=malloc(4*5*span*sizeof(double)); if(!l->storage) return 0;
  for(unsigned s=0;s<4;s++) { l->slots[s].row=-1;l->slots[s].rgb1=l->storage+s*5*span;l->slots[s].alpha=l->slots[s].rgb1+4*span; }
  return 1;
}
/* One destination row of the axis path. */
typedef struct {
  exr_bitmap *target; const unsigned char *coverage; const axis_layer *color,*mask; double alpha; int y,x0,x1,full_x0,full_x1,luminosity,valid[2];
  const converted_row *crows[2][2],*mrows[2][2]; double cwy[2][2],mwy[2][2]; const unsigned char *mline[2];
} axis_row;
/* texture_sample's mask factor: a=(mode 1 ? m0/255 : m3)/255. */
static inline double axis_mask_factor(int luminosity,double m0,double m3) { return (luminosity ? m0/255 : m3)/255; }
/* exr_pixel with effective alpha 255 stores the source bytes on every RGBA
   branch: opaque destination (c*255+127)/255=c; transparent destination;
   partial destination with denominator 255*255, giving c and alpha 255. */
static inline int axis_opaque(uint32_t color,unsigned coverage) { return (color&coverage&255)==255; }
static inline void axis_opaque_store(unsigned char *p,uint32_t color) {
  const unsigned char bytes[4]={(unsigned char)(color>>24),(unsigned char)(color>>16),(unsigned char)(color>>8),255};
  memcpy(p,bytes,4);
}
static inline void axis_fill32(unsigned char *d,uint32_t packed,int n) {
  if(n>=4) {
    __m128i v=_mm_set1_epi32((int)packed);
    while(n>=4) { _mm_storeu_si128((__m128i *)d,v); d+=16; n-=4; }
  }
  while(n--) { memcpy(d,&packed,4); d+=4; }
}
/* Identify the single contiguous full-coverage span [full_x0, full_x1) on a
   clip row; non-convex rows with interior gaps fall back to an empty span. */
static void axis_clip_full_span(const unsigned char *cov,int x0,int x1,int *full_x0,int *full_x1) {
  if(!cov) { *full_x0=x0; *full_x1=x1; return; }
  int a=x0,b=x1;
  while(a<b && cov[a]!=255) a++;
  while(b>a && cov[b-1]!=255) b--;
  int p=a;
  const __m128i ones=_mm_cmpeq_epi32(_mm_setzero_si128(),_mm_setzero_si128());
  while(p+16<=b) {
    __m128i v=_mm_loadu_si128((const __m128i *)(cov+p));
    if(_mm_movemask_epi8(_mm_cmpeq_epi8(v,ones))!=0xFFFF) { *full_x0=0; *full_x1=0; return; }
    p+=16;
  }
  while(p<b) { if(cov[p]!=255) { *full_x0=0; *full_x1=0; return; } p++; }
  *full_x0=a; *full_x1=b;
}
static inline void axis_sample_pixel(const axis_row *r,int x,double sums[4]) {
  const axis_layer *c=r->color,*m=r->mask;
  const image_tap *cc=c->columns+2*(size_t)(x-r->x0),*mc=m ? m->columns+2*(size_t)(x-r->x0) : NULL;
  __m128d rg=_mm_setzero_pd(),ba=_mm_setzero_pd();
  for(unsigned sy=0;sy<2;sy++) if(r->valid[sy]) {
    __m128d cy0=_mm_set1_pd(r->cwy[sy][0]),cy1=_mm_set1_pd(r->cwy[sy][1]);
    for(unsigned sx=0;sx<2;sx++) if(cc[sx].first>=0) {
      __m128d w=_mm_set_pd(cc[sx].fraction,1-cc[sx].fraction);
      size_t index=(size_t)(cc[sx].first-(int)c->lo);
      if(!m) { converted_sample(r->crows[sy][0],r->crows[sy][1],index,w,cy0,cy1,&rg,&ba); continue; }
      __m128d srg=_mm_setzero_pd(),sba=_mm_setzero_pd();double m0,m3;
      converted_sample(r->crows[sy][0],r->crows[sy][1],index,w,cy0,cy1,&srg,&sba);
      if(m->interpolate) {
        __m128d mrg=_mm_setzero_pd(),mba=_mm_setzero_pd();
        converted_sample(r->mrows[sy][0],r->mrows[sy][1],(size_t)(mc[sx].first-(int)m->lo),
          _mm_set_pd(mc[sx].fraction,1-mc[sx].fraction),_mm_set1_pd(r->mwy[sy][0]),_mm_set1_pd(r->mwy[sy][1]),&mrg,&mba);
        m0=_mm_cvtsd_f64(mrg);m3=_mm_cvtsd_f64(_mm_unpackhi_pd(mba,mba));
      } else { const unsigned char *p=r->mline[sy]+(size_t)mc[sx].first*4; m3=p[3];m0=p[0]*m3; }
      __m128d a=_mm_set1_pd(axis_mask_factor(r->luminosity,m0,m3));
      rg=_mm_add_pd(rg,_mm_mul_pd(srg,a));ba=_mm_add_pd(ba,_mm_mul_pd(sba,a));
    }
  }
  _mm_storeu_pd(sums,rg);_mm_storeu_pd(sums+2,ba);
}
static inline void axis_store(const axis_row *r,int x,const double sums[4],unsigned coverage) {
  if(!sums[3]) return;
  uint32_t color=image_byte(sums[3]*r->alpha/4);
  if(!color) return;
  for(unsigned k=0;k<3;k++) color|=image_byte(sums[k]/sums[3])<<(24-8*k);
  if(axis_opaque(color,coverage)) axis_opaque_store(r->target->pixels+(size_t)r->y*r->target->stride+(size_t)x*4,color);
  else exr_pixel(r->target,x,r->y,color,coverage);
}
#if defined(__GNUC__)
__attribute__((noinline))
#elif defined(_MSC_VER)
__declspec(noinline)
#endif
static void axis_row_paint_clipped(const axis_row *r,int first,int last) {
  for(int x=first;x<last;x++) {
    unsigned coverage=r->coverage ? r->coverage[x] : 255;
    double sums[4];
    if(!coverage) continue;
    axis_sample_pixel(r,x,sums);
    axis_store(r,x,sums,coverage);
  }
}
#if defined(__GNUC__)
__attribute__((noinline))
#elif defined(_MSC_VER)
__declspec(noinline)
#endif
static void axis_row_paint_full(const axis_row *r,int first,int last) {
  unsigned char *row=r->target->pixels+(size_t)r->y*r->target->stride;
  for(int x=first;x<last;x++) {
    double sums[4];
    axis_sample_pixel(r,x,sums);
    if(!sums[3]) continue;
    uint32_t color=image_byte(sums[3]*r->alpha/4);
    if(!color) continue;
    for(unsigned k=0;k<3;k++) color|=image_byte(sums[k]/sums[3])<<(24-8*k);
    if((color&255)==255) axis_opaque_store(row+(size_t)x*4,color);
    else exr_pixel(r->target,x,r->y,color,255);
  }
}
static inline void axis_row_paint(const axis_row *r,int first,int last) {
  int f0=first>r->full_x0 ? first : r->full_x0;
  int f1=last<r->full_x1 ? last : r->full_x1;
  if(f0>=f1) { axis_row_paint_clipped(r,first,last); return; }
  if(first<f0) axis_row_paint_clipped(r,first,f0);
  axis_row_paint_full(r,f0,f1);
  if(f1<last) axis_row_paint_clipped(r,f1,last);
}
/* With constant RGBA source and coverage 255, exr_pixel is a pure function of
   the 4-byte destination pixel. Compute once per constant-destination span. */
static inline void axis_flat_blend_run(exr_bitmap *target,int y,int start,int end,uint32_t rgba) {
  unsigned char *d=target->pixels+(size_t)y*target->stride+(size_t)start*4;
  uint32_t last_dst,last_out;
  memcpy(&last_dst,d,4);
  exr_pixel(target,start,y,rgba,255);
  memcpy(&last_out,d,4);
  int k=start+1; d+=4;
  if(k+4<=end) {
    __m128i vdst=_mm_set1_epi32((int)last_dst);
    __m128i vout=_mm_set1_epi32((int)last_out);
    while(k+4<=end) {
      __m128i cur4=_mm_loadu_si128((const __m128i *)d);
      if(_mm_movemask_epi8(_mm_cmpeq_epi32(cur4,vdst))==0xFFFF) {
        _mm_storeu_si128((__m128i *)d,vout);
        k+=4; d+=16;
      } else {
        for(int j=0;j<4;j++,k++,d+=4) {
          uint32_t cur; memcpy(&cur,d,4);
          if(cur==last_dst) memcpy(d,&last_out,4);
          else { exr_pixel(target,k,y,rgba,255); last_dst=cur; memcpy(&last_out,d,4); }
        }
        vdst=_mm_set1_epi32((int)last_dst);
        vout=_mm_set1_epi32((int)last_out);
      }
    }
  }
  for(;k<end;k++,d+=4) {
    uint32_t cur; memcpy(&cur,d,4);
    if(cur==last_dst) memcpy(d,&last_out,4);
    else { exr_pixel(target,k,y,rgba,255); last_dst=cur; memcpy(&last_out,d,4); }
  }
}
static int has_flat_footprints(const exr_bitmap *source) {
  /* A few adjacent pairs keep continuously varying images on the regular path. */
  unsigned matches=0;
  if(source->width<128 || source->height<128) return 0;
  for(unsigned i=1;i<=4;i++) {
    unsigned x=source->width*i/5,y=source->height*i/5;
    const unsigned char *p=source->pixels+(size_t)y*source->stride+(size_t)x*4;
    if(p[3]==255 && !memcmp(p,p+4,4) && !memcmp(p,p+source->stride,4)) matches++;
  }
  return matches>=2;
}
static void axis_flat_row_paint(const axis_row *r,const image_tap ytaps[2]) {
  const exr_bitmap *color=r->color->bitmap,*mask=r->mask ? r->mask->bitmap : NULL;
  int top=ytaps[0].first<ytaps[1].first ? ytaps[0].first : ytaps[1].first;
  int bottom=ytaps[0].second>ytaps[1].second ? ytaps[0].second : ytaps[1].second;
  const unsigned char *rows[4],*masks[4];
  int pending=r->x0,next=0;
  if(!r->valid[0] || !r->valid[1] || bottom-top>=4) {
    axis_row_paint(r,r->x0,r->x1);
    return;
  }
  for(int i=0;i<=bottom-top;i++) {
    rows[i]=color->pixels+(size_t)(top+i)*color->stride;
    masks[i]=mask ? mask->pixels+(size_t)(top+i)*mask->stride : NULL;
  }
  for(int x=r->x0;x<r->x1;) {
    const image_tap *tap=r->color->columns+2*(size_t)(x-r->x0);
    int left=tap[0].first,right=tap[1].second;
    if(left<next || right<0) { x++;continue; }
    const unsigned char *p=rows[0]+(size_t)left*4,*q=mask ? masks[0]+(size_t)left*4 : NULL;
    next=left+1;
    if(p[3]!=255 || (q && q[3]!=255)) { x++;continue; }
    /* All four subsamples lie inside this footprint. Equal opaque texels
       interpolate to their byte values within rounding error. The nearest
       gray mask samples the same footprint, so alpha also rounds to its byte. */
    int limit=r->color->hi<(unsigned)color->width ? (int)r->color->hi : (int)color->width-1;
    int col=left;
    for(;col<=limit;col++) {
      size_t offset=(size_t)col*4;
      int i=0;
      while(i<=bottom-top && !memcmp(rows[i]+offset,p,4) &&
            (!mask || !memcmp(masks[i]+offset,q,4))) i++;
      if(i<=bottom-top) break;
    }
    if(right>=col) { if(col>next) next=col;x++;continue; }
    next=col;
    if(pending<x) axis_row_paint(r,pending,x);
    uint32_t rgba=((uint32_t)p[0]<<24)|((uint32_t)p[1]<<16)|((uint32_t)p[2]<<8)|(q ? q[0] : 255);
    int start=x;
    do { x++;tap+=2; } while(x<r->x1 && tap[1].second>=0 && tap[1].second<next);
    int end=x;
    unsigned alpha_byte=rgba&255;
    if(!alpha_byte) {
      /* Effective alpha 0: exr_pixel is a no-op. */
    } else if(start>=r->full_x0 && end<=r->full_x1) {
      if(alpha_byte==255) {
        unsigned char *d=r->target->pixels+(size_t)r->y*r->target->stride+(size_t)start*4;
        const unsigned char bytes[4]={p[0],p[1],p[2],255};
        uint32_t packed; memcpy(&packed,bytes,4);
        axis_fill32(d,packed,end-start);
      } else {
        axis_flat_blend_run(r->target,r->y,start,end,rgba);
      }
    } else if(alpha_byte==255) {
      unsigned char *d=r->target->pixels+(size_t)r->y*r->target->stride+(size_t)start*4;
      const unsigned char bytes[4]={p[0],p[1],p[2],255};
      for(int k=start;k<end;k++,d+=4) {
        unsigned coverage=r->coverage ? r->coverage[k] : 255;
        if(coverage==255) memcpy(d,bytes,4); else exr_pixel(r->target,k,r->y,rgba,coverage);
      }
    } else {
      for(int k=start;k<end;k++) {
        unsigned coverage=r->coverage ? r->coverage[k] : 255;
        exr_pixel(r->target,k,r->y,rgba,coverage);
      }
    }
    pending=x;
  }
  if(pending<r->x1) axis_row_paint(r,pending,r->x1);
}
/* Axis-aligned interpolated image, optionally with an image soft mask (no
   matte, no nested mask), without composite state. Per subsample this is
   the generic loop's sample/texture_sample: the color sample, the mask
   sample on the mask's own grid, out*=a, then the running sums in the same
   sy/sx order. Unmasked, the sample adds to the sums directly as
   bilinear_axis always did. Returns 0 when the converted-row form does not
   apply. */
static int axis_paint(exr_bitmap *target,const exr_bitmap *source,const exr_vector_texture *mt,unsigned mask_mode,const double inv[6],double alpha,
                      const exr_clip_mask *clip,int x0,int y0,int x1,int y1,size_t cost,
                      exr_raster_work *work,const exr_control *control,exr_error *e,exr_status *result) {
  axis_layer color,mask; size_t width;
  if(target->channels!=4 || inv[1] || inv[2] || x1<=x0 || y1<=y0) return 0;
  if(!isfinite(inv[0]*(x0+.25)+inv[2]*(y0+.25)+inv[4]) || !isfinite(inv[0]*(x1-.25)+inv[2]*(y0+.25)+inv[4]) ||
     !isfinite(inv[1]*(x0+.25)+inv[3]*(y0+.25)+inv[5]) || !isfinite(inv[1]*(x0+.25)+inv[3]*(y1-.25)+inv[5])) return 0;
  width=(size_t)(x1-x0); memset(&mask,0,sizeof(mask));
  if(!axis_layer_init(&color,source,1,inv,x0,y0,width) ||
     (mt && !axis_layer_init(&mask,&mt->bitmap,(int)mt->interpolate,inv,x0,y0,width))) {
    axis_layer_free(&color);axis_layer_free(&mask); return 0;
  }
  /* Equal opaque texels resolve to their bytes at any scale. Up to two texels
     per pixel the footprint check stays short; taller footprints fall back
     per row in axis_flat_row_paint. */
  int flat=alpha==1 && inv[0]>0 && inv[0]*source->width<=2 && fabs(inv[3])*source->height<=2 &&
    (!mt || (mask_mode==1 && !mask.interpolate && mt->bitmap.width==source->width && mt->bitmap.height==source->height)) &&
    has_flat_footprints(source) && fegetround()==FE_TONEAREST;
  *result=EXR_OK;
  for(int y=y0;y<y1;y++) {
    *result=exr_control_cancel(control,e);
    if(*result!=EXR_OK) break;
    if(!exr_vector_work(work,width*cost)) { *result=exr_fail(e,EXR_LIMIT,"Affine image work budget exceeded");break; }
    axis_row r; int cneed[4],mneed[4]; unsigned ccount=0,mcount=0; image_tap ctap[2]={{0,0,0},{0,0,0}},mtap[2]={{0,0,0},{0,0,0}};
    memset(&r,0,sizeof(r));
    r.target=target;r.coverage=exr_clip_row(clip,(size_t)y);r.color=&color;r.mask=mt ? &mask : NULL;
    r.alpha=alpha;r.y=y;r.x0=x0;r.x1=x1;r.luminosity=mask_mode==1;
    axis_clip_full_span(r.coverage,x0,x1,&r.full_x0,&r.full_x1);
    for(unsigned sy=0;sy<2;sy++) {
      double py=y+.25+.5*sy,v=inv[1]*(x0+.25)+inv[3]*py+inv[5];
      if(v<0 || v>=1) continue;
      r.valid[sy]=1; ctap[sy]=bilinear_tap(v,source->height);
      cneed[ccount++]=ctap[sy].first;cneed[ccount++]=ctap[sy].second;
      if(!mt) continue;
      if(mask.interpolate) { mtap[sy]=bilinear_tap(v,mt->bitmap.height);mneed[mcount++]=mtap[sy].first;mneed[mcount++]=mtap[sy].second; }
      else { uint32_t t=(uint32_t)(v*mt->bitmap.height); if(t>=mt->bitmap.height) t=mt->bitmap.height-1; r.mline[sy]=mt->bitmap.pixels+(size_t)t*mt->bitmap.stride; }
    }
    if(!ccount) continue;
    for(unsigned sy=0;sy<2;sy++) if(r.valid[sy]) {
      r.crows[sy][0]=find_row(color.slots,cneed,ccount,ctap[sy].first,source,color.lo,color.hi);
      r.crows[sy][1]=find_row(color.slots,cneed,ccount,ctap[sy].second,source,color.lo,color.hi);
      r.cwy[sy][0]=1-ctap[sy].fraction;r.cwy[sy][1]=ctap[sy].fraction;
      if(mt && mask.interpolate) {
        r.mrows[sy][0]=find_row(mask.slots,mneed,mcount,mtap[sy].first,&mt->bitmap,mask.lo,mask.hi);
        r.mrows[sy][1]=find_row(mask.slots,mneed,mcount,mtap[sy].second,&mt->bitmap,mask.lo,mask.hi);
        r.mwy[sy][0]=1-mtap[sy].fraction;r.mwy[sy][1]=mtap[sy].fraction;
      }
    }
    if(flat) axis_flat_row_paint(&r,ctap);
    else axis_row_paint(&r,r.x0,r.x1);
  }
  axis_layer_free(&color);axis_layer_free(&mask);
  if(*result==EXR_OK) *result=exr_fail(e,EXR_OK,"");
  return 1;
}
#endif
/* A one-axis shear keeps horizontal taps constant down each column. When
   both vertical taps stay on the same source rows across a destination row,
   reuse their converted texels; crossing rows retain the scalar sampler.
   Coordinates, weights and four-sample accumulation keep their original order. */
static int bilinear_shear(exr_bitmap *target,const exr_bitmap *source,const double inv[6],double alpha,
                         const exr_clip_mask *clip,int x0,int y0,int x1,int y1,size_t cost,
                         exr_raster_work *work,const exr_control *control,exr_error *e,exr_status *result) {
  /* The body below is SSE2-only; other targets take the scalar fallback, so
     these parameters must be explicitly discarded to keep -Werror quiet. */
  (void)target;(void)source;(void)inv;(void)alpha;(void)clip;
  (void)x0;(void)y0;(void)x1;(void)y1;(void)cost;(void)work;
  (void)control;(void)e;(void)result;
#if defined(__SSE2__) || defined(_M_X64)
  if(!inv[1] || inv[2] || x1<=x0 || y1<=y0) return 0;
  double first=inv[0]*(x0+.25)+inv[2]*(y0+.25)+inv[4];
  double last=inv[0]*(x1-.25)+inv[2]*(y0+.25)+inv[4];
  if(!isfinite(first) || !isfinite(last)) return 0;
  for(unsigned i=0;i<4;i++) {
    double v=inv[1]*(i&1 ? x1-.25 : x0+.25)+inv[3]*(i&2 ? y1-.25 : y0+.25)+inv[5];
    if(!isfinite(v)) return 0;
  }
  size_t width=(size_t)(x1-x0);unsigned lo=source->width,hi=0;
  image_tap *columns=malloc(2*width*sizeof(*columns));
  if(!columns) return 0;
  for(size_t i=0;i<2*width;i++) {
    double u=inv[0]*((x0+(int)(i>>1))+.25+.5*(i&1))+inv[2]*(y0+.25)+inv[4];
    columns[i]=u<0 || u>=1 ? (image_tap){0,-1,-1} : bilinear_tap(u,source->width);
    if(columns[i].first>=0) {
      if((unsigned)columns[i].first<lo) lo=(unsigned)columns[i].first;
      if((unsigned)columns[i].first+1>hi) hi=(unsigned)columns[i].first+1;
    }
  }
  double *storage_rows=lo<=hi && (size_t)(hi-lo)<=4*width ? malloc(4*5*(size_t)(hi-lo+1)*sizeof(double)) : NULL;
  if(!storage_rows) { free(columns);return 0; }
  converted_row slots[4];size_t span=(size_t)(hi-lo+1);
  for(unsigned i=0;i<4;i++) { slots[i].row=-1;slots[i].rgb1=storage_rows+i*5*span;slots[i].alpha=slots[i].rgb1+4*span; }
  *result=EXR_OK;
  for(int y=y0;y<y1;y++) {
    *result=exr_control_cancel(control,e);if(*result!=EXR_OK) break;
    if(!exr_vector_work(work,width*cost)) { *result=exr_fail(e,EXR_LIMIT,"Affine image work budget exceeded");break; }
    const unsigned char *mask=exr_clip_row(clip,(size_t)y);
    int need[4],stable=1;unsigned count=0;
    const converted_row *rows[2][2];
    for(unsigned sy=0;sy<2;sy++) {
      double py=y+.25+.5*sy;
      double a=inv[1]*(x0+.25)+inv[3]*py+inv[5],b=inv[1]*(x1-.25)+inv[3]*py+inv[5];
      if(a<0 || a>=1 || b<0 || b>=1) { stable=0;break; }
      image_tap ta=bilinear_tap(a,source->height),tb=bilinear_tap(b,source->height);
      if(ta.first!=tb.first || ta.second!=tb.second) { stable=0;break; }
      need[count++]=ta.first;need[count++]=ta.second;
    }
    if(stable) for(unsigned sy=0;sy<2;sy++) for(unsigned k=0;k<2;k++)
      rows[sy][k]=find_row(slots,need,count,need[2*sy+k],source,lo,hi);
    for(int x=x0;x<x1;x++) {
      unsigned coverage=mask ? mask[x] : 255;if(!coverage) continue;
      const image_tap *column=columns+2*(size_t)(x-x0);
      double sums[4]={0};__m128d rg=_mm_setzero_pd(),ba=_mm_setzero_pd();
      for(unsigned sy=0;sy<2;sy++) for(unsigned sx=0;sx<2;sx++) if(column[sx].first>=0) {
        double px=x+.25+.5*sx,py=y+.25+.5*sy;
        double v=inv[1]*px+inv[3]*py+inv[5];
        if(v<0 || v>=1) continue;
        if(stable) {
          double wy=bilinear_tap(v,source->height).fraction,wx=column[sx].fraction;
          converted_sample(rows[sy][0],rows[sy][1],(size_t)(column[sx].first-(int)lo),
            _mm_set_pd(wx,1-wx),_mm_set1_pd(1-wy),_mm_set1_pd(wy),&rg,&ba);
        } else {
          image_tap tap=bilinear_tap(v,source->height);double rgba[4];
          bilinear_sample(source->pixels+(size_t)tap.first*source->stride,source->pixels+(size_t)tap.second*source->stride,column[sx],tap.fraction,rgba);
          for(unsigned k=0;k<4;k++) sums[k]+=rgba[k];
        }
      }
      if(stable) { _mm_storeu_pd(sums,rg);_mm_storeu_pd(sums+2,ba); }
      if(!sums[3]) continue;
      uint32_t color=image_byte(sums[3]*alpha/4);
      for(unsigned k=0;k<3;k++) color|=image_byte(sums[k]/sums[3])<<(24-8*k);
      exr_pixel(target,x,y,color,coverage);
    }
  }
  free(storage_rows);free(columns);
  if(*result==EXR_OK) *result=exr_fail(e,EXR_OK,"");
  return 1;
#else
  return 0;
#endif
}
/* The separable transform gives each column the same two horizontal taps
   on every row. Keep the generic tap, weight and summation order. */
static int bilinear_axis(exr_bitmap *target,const exr_bitmap *source,const double inv[6],double alpha,
                         const exr_clip_mask *clip,int x0,int y0,int x1,int y1,size_t cost,
                         exr_raster_work *work,const exr_control *control,exr_error *e,exr_status *result) {
  if(inv[1] || inv[2] || x1<=x0 || y1<=y0) return 0;
  double x_first=inv[0]*(x0+.25)+inv[2]*(y0+.25)+inv[4],x_last=inv[0]*(x1-.25)+inv[2]*(y0+.25)+inv[4];
  double y_first=inv[1]*(x0+.25)+inv[3]*(y0+.25)+inv[5],y_last=inv[1]*(x0+.25)+inv[3]*(y1-.25)+inv[5];
  if(!isfinite(x_first) || !isfinite(x_last) || !isfinite(y_first) || !isfinite(y_last)) return 0;
#if defined(__SSE2__) || defined(_M_X64)
  if(axis_paint(target,source,NULL,0,inv,alpha,clip,x0,y0,x1,y1,cost,work,control,e,result)) return 1;
#endif
  size_t width=(size_t)(x1-x0);
  image_tap *columns=malloc(2*width*sizeof(*columns));
  if(!columns) return 0;
  unsigned lo=source->width,hi=0;
  for(size_t i=0;i<2*width;i++) {
    double px=(x0+(int)(i>>1))+.25+.5*(i&1);
    double u=inv[0]*px+inv[2]*(y0+.25)+inv[4];
    columns[i]=u<0 || u>=1 ? (image_tap){0,-1,-1} : bilinear_tap(u,source->width);
    if(columns[i].first>=0) {
      if((unsigned)columns[i].first<lo) lo=(unsigned)columns[i].first;
      if((unsigned)columns[i].first+1>hi) hi=(unsigned)columns[i].first+1;
    }
  }
  for(int y=y0;y<y1;y++) {
    *result=exr_control_cancel(control,e);
    if(*result!=EXR_OK) break;
    if(!exr_vector_work(work,width*cost)) {
      *result=exr_fail(e,EXR_LIMIT,"Affine image work budget exceeded");break;
    }
    const unsigned char *mask=exr_clip_row(clip,(size_t)y);
    const unsigned char *rows[2][2]={{NULL,NULL},{NULL,NULL}};
    double wy[2]={0,0};
    for(unsigned sy=0;sy<2;sy++) {
      double py=y+.25+.5*sy,v=inv[1]*(x0+.25)+inv[3]*py+inv[5];
      if(v<0 || v>=1) continue;
      image_tap tap=bilinear_tap(v,source->height);
      rows[sy][0]=source->pixels+(size_t)tap.first*source->stride;
      rows[sy][1]=source->pixels+(size_t)tap.second*source->stride;
      wy[sy]=tap.fraction;
    }
    for(int x=x0;x<x1;x++) {
      unsigned coverage=mask ? mask[x] : 255;
      const image_tap *taps=columns+2*(size_t)(x-x0);
      double sums[4]={0};
      if(!coverage) continue;
      for(unsigned sy=0;sy<2;sy++) if(rows[sy][0]) {
        for(unsigned sx=0;sx<2;sx++) if(taps[sx].first>=0) {
          double rgba[4];
          bilinear_sample(rows[sy][0],rows[sy][1],taps[sx],wy[sy],rgba);
          for(unsigned k=0;k<4;k++) sums[k]+=rgba[k];
        }
      }
      if(!sums[3]) continue;
      uint32_t color=image_byte(sums[3]*alpha/4);
      for(unsigned k=0;k<3;k++) color|=image_byte(sums[k]/sums[3])<<(24-8*k);
      exr_pixel(target,x,y,color,coverage);
    }
  }
  free(columns);
  if(*result==EXR_OK) *result=exr_fail(e,EXR_OK,"");
  return 1;
}

exr_status exr_vector_texture_blend_inks(exr_bitmap *target,const exr_vector_texture *source,const exr_bitmap *inks,const double m[6],double alpha,
                                     const exr_clip_mask *clip,exr_blend_mode mode,exr_composite_state *state,exr_raster_work *work,const exr_control *control,exr_error *e) {
  exr_raster_work local_work={0}; size_t i; double det,inv[6],left=1e7,top=1e7,right=-1e7,bottom=-1e7; int x0,y0,x1,y1,x,y;
  const exr_vector_texture *layers[16],*layer=source; size_t depth=0,cost=0; int paired_nearest;
  if(mode<EXR_BLEND_NORMAL || mode>EXR_BLEND_LUMINOSITY) return exr_fail(e,EXR_ARGUMENT,"Invalid affine image blend mode");
  if(!storage(target) || !source || !m || !isfinite(alpha) || alpha<0 || alpha>1 ||
     (clip && (!storage(&clip->bitmap) || clip->bitmap.channels!=1 || clip->bitmap.width!=target->width || exr_clip_height(clip)!=target->height || overlap(target,&clip->bitmap))))
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
  if(clip && clip->compact_height && clip->solid_is_rect && x0<x1 && y0<y1 &&
     x0>=clip->solid_rect[0] && y0>=clip->solid_rect[1] && x1<=clip->solid_rect[2] && y1<=clip->solid_rect[3])
    clip=NULL;
#ifndef EXR_PROFILE_IMAGE
  if(!inks && !state) {
    exr_status fast;
    if(nearest_axis(target,source,inv,alpha,clip,mode,x0,y0,x1,y1,cost,work,control,e,&fast)) return fast;
    if(source->interpolate && !source->mask && !source->has_matte && mode==EXR_BLEND_NORMAL && target->channels==4 &&
       bilinear_shear(target,&source->bitmap,inv,alpha,clip,x0,y0,x1,y1,cost,work,control,e,&fast)) return fast;
    if(source->interpolate && !source->mask && !source->has_matte && mode==EXR_BLEND_NORMAL && target->channels==4 &&
       bilinear_axis(target,&source->bitmap,inv,alpha,clip,x0,y0,x1,y1,cost,work,control,e,&fast)) return fast;
#if defined(__SSE2__) || defined(_M_X64)
    if(source->interpolate && source->mask && !source->mask->mask && !source->has_matte && mode==EXR_BLEND_NORMAL && target->channels==4 &&
       axis_paint(target,&source->bitmap,source->mask,source->mask_mode,inv,alpha,clip,x0,y0,x1,y1,cost,work,control,e,&fast)) return fast;
#endif
  }
#endif
  /* Bound the validation scan by the destination work. Endpoints ensure the
     separable index calculations stay finite throughout the rectangle. */
  if(paired_nearest && source->mask_mode==1 && !state && mode==EXR_BLEND_NORMAL && alpha==1 &&
     (!control || !control->cancelled) && m[1]==0 && m[2]==0 && x1>x0 && y1>y0 &&
     (size_t)source->bitmap.width*source->bitmap.height<=8*(size_t)(x1-x0)*(y1-y0) &&
     isfinite(inv[0]*(x0+.25)+inv[2]*(y0+.25)+inv[4]) &&
     isfinite(inv[0]*(x1-.25)+inv[2]*(y0+.25)+inv[4]) &&
     isfinite(inv[1]*(x0+.25)+inv[3]*(y0+.25)+inv[5]) &&
     isfinite(inv[1]*(x0+.25)+inv[3]*(y1-.25)+inv[5]) && fegetround()==FE_TONEAREST &&
     solid_with_opaque_mask(&source->bitmap,&source->mask->bitmap)) {
    int *columns=malloc(2*(size_t)(x1-x0)*sizeof(*columns));
    if(columns) {
      const unsigned char *p=source->bitmap.pixels;
      uint32_t color=((uint32_t)p[0]<<24)|((uint32_t)p[1]<<16)|((uint32_t)p[2]<<8);
      exr_status status=solid_mask_blend(target,&source->mask->bitmap,inv,clip,x0,y0,x1,y1,columns,color,cost,work,control,e);
      free(columns);
      return status;
    }
  }
#ifdef EXR_PROFILE_IMAGE
  memset(&image_profile,0,sizeof(image_profile));
  unsigned long long loop_start=image_tick();
#endif
  for(y=y0;y<y1;y++) {
    if(exr_control_cancel(control,e)!=EXR_OK) return EXR_CANCELLED;
    if(!exr_vector_work(work,(size_t)(x1>x0 ? x1-x0 : 0)*cost)) return exr_fail(e,EXR_LIMIT,"Affine image work budget exceeded");
    const unsigned char *mask_row=exr_clip_row(clip,(size_t)y);
    for(x=x0;x<x1;x++) {
      double sums[5]={0},shape_sum=0; unsigned sx,sy,k,coverage=mask_row ? mask_row[x] : 255; uint32_t color=0;
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
#ifndef EXR_PROFILE_IMAGE
        else if(!source->mask) {
          sample(&source->bitmap,u,v,(int)source->interpolate,s);
          sample_shape=state && (state->alpha_flags&EXR_ALPHA_IMAGE_SHAPE) ? s[3]/255. : 1;
        }
#endif
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
    for(y=y0;y<y1;y++) for(x=x0;x<x1;x++) if(!clip || exr_clip_row(clip,(size_t)y)[x]) image_profile.pixels++;
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
  const exr_bitmap *clip,exr_blend_mode mode,exr_composite_state *state,exr_raster_work *work,const exr_control *control,exr_error *e) {
  return exr_vector_texture_blend_inks(target,source,NULL,m,alpha,clip ? &(exr_clip_mask){.bitmap=*clip} : NULL,mode,state,work,control,e);
}
exr_status exr_vector_image(exr_bitmap *target,const exr_bitmap *source,const double m[6],double alpha,
                             int interpolate,const exr_bitmap *clip,exr_raster_work *work,const exr_control *control,exr_error *e) {
  exr_vector_texture texture={0}; if(source) texture.bitmap=*source; texture.interpolate=interpolate!=0;
  return exr_vector_texture_paint(target,&texture,m,alpha,clip,work,control,e);
}

exr_status exr_vector_texture_paint(exr_bitmap *target,const exr_vector_texture *source,const double matrix[6],double alpha,
  const exr_bitmap *clip,exr_raster_work *work,const exr_control *control,exr_error *error) {
  return exr_vector_texture_blend(target,source,matrix,alpha,clip,EXR_BLEND_NORMAL,NULL,work,control,error);
}
