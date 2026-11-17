/* SPDX-License-Identifier: MIT */
#include "vector_internal.h"
#include "pixels_internal.h"
#include <float.h>
typedef struct { double x; int winding; } crossing;
static int compare_crossing(const void *a,const void *b) {
  const crossing *x=a,*y=b; return x->x<y->x ? -1 : x->x>y->x;
}
static int storage(const exr_bitmap *bitmap,unsigned channels) {
  return bitmap && bitmap->pixels && bitmap->width && bitmap->height && bitmap->width<=16384 && bitmap->height<=16384 &&
    bitmap->channels==channels && bitmap->stride>=(size_t)bitmap->width*channels && bitmap->stride<=(size_t)64*1024*1024/bitmap->height;
}
static int overlaps(const exr_bitmap *a,const exr_bitmap *b) {
  uintptr_t first=(uintptr_t)a->pixels,second=(uintptr_t)b->pixels;
  return first<=second ? second-first<(size_t)a->stride*a->height : first-second<(size_t)b->stride*b->height;
}
static void span(float *coverage,int origin,uint32_t width,double left,double right) {
  int x,first,last;
  left=fmax(origin,left); right=fmin(origin+(double)width,right); if(right<=left) return;
  first=(int)floor(left);last=(int)ceil(right)-1;
  if(first==last) { coverage[first-origin]+=(float)(right-left);return; }
  coverage[first-origin]+=(float)(first+1-left);
  /* Interior pixels contribute exactly one sample; only endpoints need min/max. */
  for(x=first+1;x<last;x++) coverage[x-origin]+=1.f;
  coverage[last-origin]+=(float)(right-last);
}
static int axis_rectangle(const exr_vector_edge edges[4],double left,double top,double right,double bottom) {
  /* Tolerate transform roundoff, capped well below a pixel even at large coordinates. */
  double scale=fmax(fmax(fabs(left),fabs(right)),fmax(fabs(top),fabs(bottom)));
  double eps=fmin(1e-6,1e-9*fmax(1,scale));
  unsigned sides=0,previous=0,first=0; size_t i;
  for(i=0;i<4;i++) {
    const exr_vector_edge *edge=&edges[i],*next=&edges[(i+1)%4]; unsigned side=0,vertical;
    if(fabs(edge->x1-next->x0)>eps || fabs(edge->y1-next->y0)>eps) return 0;
    if(fabs(edge->x0-edge->x1)<=eps &&
       ((fabs(edge->y0-top)<=eps && fabs(edge->y1-bottom)<=eps) ||
        (fabs(edge->y0-bottom)<=eps && fabs(edge->y1-top)<=eps)))
      side=fabs(edge->x0-left)<=eps ? 1u : fabs(edge->x0-right)<=eps ? 2u : 0u;
    else if(fabs(edge->y0-edge->y1)<=eps &&
       ((fabs(edge->x0-left)<=eps && fabs(edge->x1-right)<=eps) ||
        (fabs(edge->x0-right)<=eps && fabs(edge->x1-left)<=eps)))
      side=fabs(edge->y0-top)<=eps ? 4u : fabs(edge->y0-bottom)<=eps ? 8u : 0u;
    if(!side || (sides&side)) return 0;
    vertical=side<=2;
    if(i && vertical==previous) return 0;
    if(!i) first=vertical;
    previous=vertical; sides|=side;
  }
  return sides==15 && first!=previous;
}
static int axis_rectangles(const exr_vector_edge *edges,size_t count,exr_vector_rule rule,
                           double left,double top,double right,double bottom) {
  size_t i; int winding=0;
  if(!count || count%4) return 0;
  /* Repeating the same contour must not change its edge coverage. Different
     rectangles and other polygons stay on the ordinary scanline path. */
  for(i=0;i<count;i+=4) {
    const exr_vector_edge *a=&edges[i],*b=&edges[i+1];
    if(!axis_rectangle(a,left,top,right,bottom)) return 0;
    winding+=(a->x1-a->x0)*(b->y1-b->y0)-(a->y1-a->y0)*(b->x1-b->x0)>0 ? 1 : -1;
  }
  return rule==EXR_VECTOR_EVENODD ? (count/4)%2!=0 : winding!=0;
}
static void rectangle_span(exr_bitmap *bitmap,int left,int right,int y,unsigned coverage,uint32_t color,
                           const double *cmyk,double cmyk_alpha,const exr_bitmap *clip,
                           exr_blend_mode mode,exr_composite_state *state) {
  int x;
  const unsigned char *mask=clip ? clip->pixels+(size_t)y*clip->stride : NULL;
  if(!coverage || left>=right) return;
  if(!cmyk && !state && mode==EXR_BLEND_NORMAL && (color&255)==255 && coverage==255) {
    const unsigned char rgba[4]={(unsigned char)(color>>24),(unsigned char)(color>>16),(unsigned char)(color>>8),255};
    const unsigned char gray=(unsigned char)((rgba[0]*77+rgba[1]*150+rgba[2]*29+128)>>8);
    unsigned char *pixel=bitmap->pixels+(size_t)y*bitmap->stride+(size_t)left*bitmap->channels;
    /* Preserve the integer rectangle's bulk stores for every fully covered span. */
    if(!mask && bitmap->channels==1) memset(pixel,gray,(size_t)(right-left));
    else if(!mask && color==0xffffffffu) memset(pixel,255,(size_t)(right-left)*bitmap->channels);
    else if(!mask) for(x=left;x<right;x++,pixel+=4) memcpy(pixel,rgba,4);
    else for(x=left;x<right;x++,pixel+=bitmap->channels) {
      unsigned alpha=mask ? mask[x] : 255;
      if(alpha==255) {
        if(bitmap->channels==1) *pixel=gray;
        else memcpy(pixel,rgba,4);
      } else if(alpha) exr_pixel(bitmap,x,y,color,alpha);
    }
    return;
  }
  for(x=left;x<right;x++) {
    unsigned alpha=mask ? (coverage*mask[x]+127)/255 : coverage;
    if(!alpha) continue;
    if(cmyk) exr_pixel_composite_cmyk(bitmap,x,y,cmyk,cmyk_alpha,alpha,mode,state);
    else if(state) exr_pixel_composite(bitmap,x,y,color,alpha,mode,state);
    else if(mode==EXR_BLEND_NORMAL) exr_pixel(bitmap,x,y,color,alpha);
    else exr_pixel_blend(bitmap,x,y,color,alpha,mode);
  }
}
static exr_status fill_blend(exr_bitmap *bitmap,const exr_vector_edge *edges,size_t count,
                            exr_vector_rule rule,uint32_t color,const double *cmyk,double cmyk_alpha,
                            const exr_bitmap *clip,exr_blend_mode mode,exr_composite_state *state,
                            size_t *work,const exr_control *control,exr_error *error) {
  size_t local_work=0,i; crossing *crossings=NULL; float *coverage=NULL; double low=DBL_MAX,high=-DBL_MAX,left_bound=DBL_MAX,right_bound=-DBL_MAX;
  int y,top,bottom,left,right; uint32_t row_width; exr_status status=EXR_OK;
  if(!storage(bitmap,1) && !storage(bitmap,4)) return exr_fail(error,EXR_ARGUMENT,"Invalid vector target bitmap storage");
  if(mode<EXR_BLEND_NORMAL || mode>EXR_BLEND_LUMINOSITY) return exr_fail(error,EXR_ARGUMENT,"Invalid vector blend mode");
  if((count && !edges) || (rule!=EXR_VECTOR_NONZERO && rule!=EXR_VECTOR_EVENODD) ||
     (clip && (!storage(clip,1) || clip->width!=bitmap->width || clip->height!=bitmap->height || overlaps(clip,bitmap))))
    return exr_fail(error,EXR_ARGUMENT,"Invalid vector edges, fill rule or clip bitmap");
  if(count>1048576) return exr_fail(error,EXR_LIMIT,"Vector edge count exceeds one million");
  if(!work) work=&local_work;
  if(!exr_vector_work(work,count)) goto limit;
  for(i=0;i<count;i++) {
    const exr_vector_edge *edge=&edges[i];
    if(!isfinite(edge->x0) || !isfinite(edge->y0) || !isfinite(edge->x1) || !isfinite(edge->y1) ||
       fabs(edge->x0)>1e7 || fabs(edge->x1)>1e7 || fabs(edge->y0)>1e7 || fabs(edge->y1)>1e7)
      return exr_fail(error,EXR_ARGUMENT,"Invalid vector edge coordinates");
    left_bound=fmin(left_bound,fmin(edge->x0,edge->x1)); right_bound=fmax(right_bound,fmax(edge->x0,edge->x1));
    if(edge->y0!=edge->y1) { low=fmin(low,fmin(edge->y0,edge->y1)); high=fmax(high,fmax(edge->y0,edge->y1)); }
  }
  status=exr_control_cancel(control,error); if(status!=EXR_OK) return status;
  if((!(cmyk ? cmyk_alpha>0 : (color&255)) && (!state || !(state->knockout || state->shape) || (state->alpha_flags&EXR_ALPHA_CONSTANT_SHAPE))) || high<=0 || low>=bitmap->height || low>=high || right_bound<=0 || left_bound>=bitmap->width || left_bound>=right_bound) return exr_fail(error,EXR_OK,"");
  top=(int)fmax(0,floor(low)); bottom=(int)fmin(bitmap->height,ceil(high));
  left=(int)fmax(0,floor(left_bound)); right=(int)fmin(bitmap->width,ceil(right_bound)); row_width=(uint32_t)(right-left);
  /* Exact rectangle/pixel intersection area: bulk interior, at most two edge
     pixels per row and two fractional rows. No crossings/coverage allocation. */
  if(axis_rectangles(edges,count,rule,left_bound,low,right_bound,high)) {
    int inner_left=(int)fmax(left,ceil(left_bound)),inner_right=(int)fmin(right,floor(right_bound));
    double first_width=fmin(right_bound,left+1)-fmax(left_bound,left);
    double last_width=fmin(right_bound,right)-fmax(left_bound,right-1);
    size_t levels=0,scan_work;
    for(i=count/2;i>1;i=(i+1)/2) levels++;
    scan_work=4*(count+(count/2)*(levels+1));
    for(y=top;y<bottom;y++) {
      double height=fmin(high,y+1)-fmax(low,y);
      unsigned alpha=(unsigned)floor(height*255+.5);
      size_t cost=(state ? 20+state->depth*4 : 0)+(mode==EXR_BLEND_NORMAL ? 1 : mode<EXR_BLEND_HUE ? 24 : 64);
      status=exr_control_cancel(control,error); if(status!=EXR_OK) return status;
      /* Keep the scanline path's conservative work budget and row cancellation. */
      if(!exr_vector_work(work,(size_t)row_width*(4+cost)+scan_work)) goto limit;
      rectangle_span(bitmap,inner_left,inner_right,y,alpha,color,cmyk,cmyk_alpha,clip,mode,state);
      if(left<inner_left)
        rectangle_span(bitmap,left,left+1,y,(unsigned)floor(first_width*height*255+.5),color,cmyk,cmyk_alpha,clip,mode,state);
      if(right>inner_right && (right-left>1 || left>=inner_left))
        rectangle_span(bitmap,right-1,right,y,(unsigned)floor(last_width*height*255+.5),color,cmyk,cmyk_alpha,clip,mode,state);
    }
    return exr_fail(error,EXR_OK,"");
  }
  crossings=malloc(count*sizeof(*crossings)); coverage=calloc(row_width,sizeof(*coverage));
  if(!crossings || !coverage) { status=exr_fail(error,EXR_MEMORY,"Vector scanline allocation failed"); goto done; }
  for(y=top;y<bottom;y++) {
    unsigned sample,x;
    status=exr_control_cancel(control,error); if(status!=EXR_OK) goto done;
    memset(coverage,0,(size_t)row_width*sizeof(*coverage));
    for(sample=0;sample<4;sample++) {
      double scan=y+(sample+.5)/4,previous=0; size_t n=0,at=0,sorting=0,levels=0; int winding=0;
      if(!exr_vector_work(work,count)) goto limit;
      for(i=0;i<count;i++) {
        const exr_vector_edge *edge=&edges[i]; double minimum=fmin(edge->y0,edge->y1),maximum=fmax(edge->y0,edge->y1);
        if(scan>=minimum && scan<maximum) crossings[n++]=(crossing){edge->x0+(scan-edge->y0)/(edge->y1-edge->y0)*(edge->x1-edge->x0),edge->y1>edge->y0 ? 1 : -1};
      }
      for(i=n;i>1;i=(i+1)/2) levels++;
      sorting=n*(levels+1);
      if(!exr_vector_work(work,sorting) || !exr_vector_work(work,row_width)) goto limit;
      if(n) qsort(crossings,n,sizeof(*crossings),compare_crossing);
      while(at<n) {
        double current=crossings[at].x; int delta=0;
        if(winding) span(coverage,left,row_width,previous,current);
        do { delta+=rule==EXR_VECTOR_EVENODD ? 1 : crossings[at].winding; at++; } while(at<n && crossings[at].x==current);
        if(rule==EXR_VECTOR_EVENODD) winding=(winding+delta)&1; else winding+=delta;
        previous=current;
      }
    }
    if(!exr_vector_work(work,(size_t)row_width*((state ? 20+state->depth*4 : 0)+(mode==EXR_BLEND_NORMAL ? 1 : mode<EXR_BLEND_HUE ? 24 : 64)))) goto limit;
    /* Clip masks paint opaque white into one channel. Keep the identical
       source-over arithmetic in a row loop without per-pixel paint dispatch. */
    if(bitmap->channels==1 && color==0xffffffffu && !cmyk && !state && mode==EXR_BLEND_NORMAL) {
      unsigned char *target=bitmap->pixels+(size_t)y*bitmap->stride+left;
      const unsigned char *mask=clip ? clip->pixels+(size_t)y*clip->stride+left : NULL;
      for(x=0;x<row_width;x++) {
        unsigned alpha=coverage[x]>=4 ? 255u : (unsigned)(coverage[x]*255/4+.5);
        if(mask) alpha=(alpha*mask[x]+127)/255;
        if(!target[x] || alpha==255) target[x]=(unsigned char)alpha;
        else target[x]=(unsigned char)(target[x]+((255-target[x])*alpha+127)/255);
      }
      continue;
    }
    for(x=0;x<row_width;x++) {
      /* Coverage is nonnegative: truncation after adding .5 equals floor. */
      unsigned alpha=coverage[x]>=4 ? 255u : (unsigned)(coverage[x]*255/4+.5);
      if(clip) alpha=(alpha*clip->pixels[(size_t)y*clip->stride+(unsigned)left+x]+127)/255;
      if(alpha) {
        if(cmyk) exr_pixel_composite_cmyk(bitmap,left+(int)x,y,cmyk,cmyk_alpha,alpha,mode,state);
        else if(state) exr_pixel_composite(bitmap,left+(int)x,y,color,alpha,mode,state);
        else if(mode==EXR_BLEND_NORMAL) exr_pixel(bitmap,left+(int)x,y,color,alpha);
        else exr_pixel_blend(bitmap,left+(int)x,y,color,alpha,mode);
      }
    }
  }
  status=exr_fail(error,EXR_OK,""); goto done;
limit:
  status=exr_fail(error,EXR_LIMIT,"Vector raster work budget exceeded");
done:
  free(crossings); free(coverage); return status;
}

exr_status exr_vector_fill_blend(exr_bitmap *bitmap,const exr_vector_edge *edges,size_t count,
                            exr_vector_rule rule,uint32_t color,const exr_bitmap *clip,exr_blend_mode mode,exr_composite_state *state,
                            size_t *work,const exr_control *control,exr_error *error) {
  return fill_blend(bitmap,edges,count,rule,color,NULL,0,clip,mode,state,work,control,error);
}
exr_status exr_vector_fill_blend_cmyk(exr_bitmap *bitmap,const exr_vector_edge *edges,size_t count,
                            exr_vector_rule rule,const double cmyk[4],double alpha,const exr_bitmap *clip,exr_blend_mode mode,
                            exr_composite_state *state,size_t *work,const exr_control *control,exr_error *error) {
  return fill_blend(bitmap,edges,count,rule,0,cmyk,alpha,clip,mode,state,work,control,error);
}
exr_status exr_vector_fill(exr_bitmap *bitmap,const exr_vector_edge *edges,size_t count,
  exr_vector_rule rule,uint32_t color,const exr_bitmap *clip,size_t *work,const exr_control *control,exr_error *error) {
  return exr_vector_fill_blend(bitmap,edges,count,rule,color,clip,EXR_BLEND_NORMAL,NULL,work,control,error);
}
