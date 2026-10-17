/* SPDX-License-Identifier: GPL-3.0-only */
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
static void span(float *coverage,uint32_t width,double left,double right) {
  int x,end;
  left=fmax(0,left); right=fmin(width,right); if(right<=left) return;
  end=(int)ceil(right);
  for(x=(int)floor(left);x<end;x++) coverage[x]+=(float)(fmin(right,x+1)-fmax(left,x));
}
exr_status exr_vector_fill(exr_bitmap *bitmap,const exr_vector_edge *edges,size_t count,
                            exr_vector_rule rule,uint32_t color,const exr_bitmap *clip,
                            size_t *work,const exr_control *control,exr_error *error) {
  size_t local_work=0,i; crossing *crossings=NULL; float *coverage=NULL; double low=DBL_MAX,high=-DBL_MAX;
  int y,top,bottom; exr_status status=EXR_OK;
  if(!storage(bitmap,1) && !storage(bitmap,4)) return exr_fail(error,EXR_ARGUMENT,"Invalid vector target bitmap storage");
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
    if(edge->y0!=edge->y1) { low=fmin(low,fmin(edge->y0,edge->y1)); high=fmax(high,fmax(edge->y0,edge->y1)); }
  }
  status=exr_control_cancel(control,error); if(status!=EXR_OK) return status;
  if(!(color&255) || high<=0 || low>=bitmap->height || low>=high) return exr_fail(error,EXR_OK,"");
  top=(int)fmax(0,floor(low)); bottom=(int)fmin(bitmap->height,ceil(high));
  crossings=malloc(count*sizeof(*crossings)); coverage=calloc(bitmap->width,sizeof(*coverage));
  if(!crossings || !coverage) { status=exr_fail(error,EXR_MEMORY,"Vector scanline allocation failed"); goto done; }
  for(y=top;y<bottom;y++) {
    unsigned sample,x;
    status=exr_control_cancel(control,error); if(status!=EXR_OK) goto done;
    memset(coverage,0,(size_t)bitmap->width*sizeof(*coverage));
    for(sample=0;sample<4;sample++) {
      double scan=y+(sample+.5)/4,previous=0; size_t n=0,at=0,sorting=0,levels=0; int winding=0;
      if(!exr_vector_work(work,count)) goto limit;
      for(i=0;i<count;i++) {
        const exr_vector_edge *edge=&edges[i]; double minimum=fmin(edge->y0,edge->y1),maximum=fmax(edge->y0,edge->y1);
        if(scan>=minimum && scan<maximum) crossings[n++]=(crossing){edge->x0+(scan-edge->y0)/(edge->y1-edge->y0)*(edge->x1-edge->x0),edge->y1>edge->y0 ? 1 : -1};
      }
      for(i=n;i>1;i=(i+1)/2) levels++;
      sorting=n*(levels+1);
      if(!exr_vector_work(work,sorting) || !exr_vector_work(work,bitmap->width)) goto limit;
      if(n) qsort(crossings,n,sizeof(*crossings),compare_crossing);
      while(at<n) {
        double current=crossings[at].x; int delta=0;
        if(winding) span(coverage,bitmap->width,previous,current);
        do { delta+=rule==EXR_VECTOR_EVENODD ? 1 : crossings[at].winding; at++; } while(at<n && crossings[at].x==current);
        if(rule==EXR_VECTOR_EVENODD) winding=(winding+delta)&1; else winding+=delta;
        previous=current;
      }
    }
    if(!exr_vector_work(work,bitmap->width)) goto limit;
    for(x=0;x<bitmap->width;x++) {
      unsigned alpha=(unsigned)fmin(255,floor(coverage[x]*255/4+.5));
      if(clip) alpha=(alpha*clip->pixels[(size_t)y*clip->stride+x]+127)/255;
      if(alpha) exr_pixel(bitmap,(int)x,y,color,alpha);
    }
  }
  status=exr_fail(error,EXR_OK,""); goto done;
limit:
  status=exr_fail(error,EXR_LIMIT,"Vector raster work budget exceeded");
done:
  free(crossings); free(coverage); return status;
}
