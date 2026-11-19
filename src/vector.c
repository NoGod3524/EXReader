/* SPDX-License-Identifier: MIT */
#include "vector_internal.h"
#include "pixels_internal.h"
#include <float.h>
#ifdef _MSC_VER
#include <intrin.h>
#endif

typedef struct { double x; int winding; } crossing;
typedef struct { double x0,y0,dy,dx,min_y,max_y,x_est; int winding,pad; } active_edge;
typedef struct { int32_t first,last; float c_first,c_last; } clamped_span;

static inline unsigned ctz64(uint64_t v) {
#ifdef _MSC_VER
  unsigned long idx;
  _BitScanForward64(&idx,v);
  return (unsigned)idx;
#else
  return (unsigned)__builtin_ctzll(v);
#endif
}
static inline size_t align8(size_t n) { return (n+7)&~(size_t)7; }

void exr_vector_scratch_free(exr_vector_scratch *scratch) {
  if(scratch) { free(scratch->data); scratch->data=NULL; scratch->capacity=0; }
}

static int compare_crossing(const void *a,const void *b) {
  const crossing *x=a,*y=b; return x->x<y->x ? -1 : x->x>y->x;
}
static void sort_crossings(crossing *crossings,size_t n) {
  if(n>64) { qsort(crossings,n,sizeof(*crossings),compare_crossing); return; }
  for(size_t i=1;i<n;i++) {
    crossing next=crossings[i]; size_t j=i;
    while(j && next.x<crossings[j-1].x) { crossings[j]=crossings[j-1]; j--; }
    crossings[j]=next;
  }
}
static double stable_crossings_until(const exr_vector_edge *edges,size_t count,double scan) {
  double next=DBL_MAX;
  for(size_t i=0;i<count;i++) {
    const exr_vector_edge *edge=&edges[i];
    double low=edge->y0<edge->y1 ? edge->y0 : edge->y1;
    double high=edge->y0<edge->y1 ? edge->y1 : edge->y0;
    if(scan>=high || low==high) continue;
    if(scan<low) {
      if(low<next) next=low;
    } else {
      if(edge->x0!=edge->x1) return scan;
      if(high<next) next=high;
    }
  }
  return next;
}
static int storage(const exr_bitmap *bitmap,unsigned channels) {
  return bitmap && bitmap->pixels && bitmap->width && bitmap->height && bitmap->width<=16384 && bitmap->height<=16384 &&
    bitmap->channels==channels && bitmap->stride>=(size_t)bitmap->width*channels && bitmap->stride<=(size_t)64*1024*1024/bitmap->height;
}
static int overlaps(const exr_bitmap *a,const exr_bitmap *b) {
  uintptr_t first=(uintptr_t)a->pixels,second=(uintptr_t)b->pixels;
  return first<=second ? second-first<(size_t)a->stride*a->height : first-second<(size_t)b->stride*b->height;
}

/* 4-pixel coverage blocks tracked in a 64-bit bitset (256 px per word).
   Only pixels actually accumulated into coverage[] are marked; interior runs
   are painted directly at alpha 255 and never enter the coverage bitset. */
#define COVERAGE_SHIFT 2
#define COVERAGE_BLOCK (1u<<COVERAGE_SHIFT)
static inline void mark_touched_px(uint64_t *bits,int32_t x) {
  size_t b=(size_t)x>>COVERAGE_SHIFT;
  bits[b>>6]|=1ULL<<(b&63);
}
static inline void mark_touched(uint64_t *bits,int32_t x0,int32_t x1) {
  size_t b0=(size_t)x0>>COVERAGE_SHIFT,b1=(size_t)x1>>COVERAGE_SHIFT;
  size_t w0=b0>>6,w1=b1>>6;
  uint64_t m0=~0ULL<<(b0&63),m1=~0ULL>>(63-(b1&63));
  if(w0==w1) { bits[w0]|=(m0&m1); return; }
  bits[w0]|=m0;
  for(size_t w=w0+1;w<w1;w++) bits[w]=~0ULL;
  bits[w1]|=m1;
}
static inline int clamp_span(int origin,uint32_t width,double left,double right,clamped_span *out) {
  double end=origin+(double)width;
  int first,last;
  if(left<origin) left=origin;
  if(right>end) right=end;
  if(right<=left) return 0;
  first=(int)left; last=(int)right;
  if(right==last) last--;
  out->first=(int32_t)(first-origin);
  out->last=(int32_t)(last-origin);
  if(first==last) { out->c_first=(float)(right-left); out->c_last=0.f; }
  else { out->c_first=(float)(first+1-left); out->c_last=(float)(right-last); }
  return 1;
}
static inline void accumulate_plain(float *coverage,uint64_t *bits,const clamped_span *s) {
  if(s->first==s->last) {
    coverage[s->first]+=s->c_first;
    mark_touched_px(bits,s->first);
    return;
  }
  coverage[s->first]+=s->c_first;
  for(int32_t x=s->first+1;x<s->last;x++) coverage[x]+=1.f;
  coverage[s->last]+=s->c_last;
  mark_touched(bits,s->first,s->last);
}
static inline void accumulate_runs(float *coverage,uint64_t *bits,const clamped_span *s,
                                   const int32_t *runs,size_t count,size_t *cursor) {
  int32_t x;
  if(s->first==s->last) {
    coverage[s->first]+=s->c_first;
    mark_touched_px(bits,s->first);
    return;
  }
  coverage[s->first]+=s->c_first;
  mark_touched_px(bits,s->first);
  x=s->first+1;
  if(x<s->last) {
    while(*cursor<count && runs[2*(*cursor)+1]<=x) (*cursor)++;
    while(x<s->last) {
      int32_t stop=*cursor<count && runs[2*(*cursor)]<s->last ? runs[2*(*cursor)] : s->last;
      if(x<stop) {
        for(int32_t p=x;p<stop;p++) coverage[p]+=1.f;
        mark_touched(bits,x,stop-1);
        x=stop;
      }
      if(x<s->last) { x=runs[2*(*cursor)+1]; (*cursor)++; }
    }
  }
  coverage[s->last]+=s->c_last;
  mark_touched_px(bits,s->last);
}
/* Intersect the four samples' strict-interior spans [first+1, last) into runs
   whose coverage is guaranteed to be 4.0 (alpha 255). Uses pointer ping-pong
   to avoid intermediate memcpys. */
static size_t interior_runs(const clamped_span *spans,const size_t ends[4],int32_t *runs_a,int32_t *runs_b,int32_t **out_runs) {
  int32_t *cur=runs_a,*nxt=runs_b;
  size_t count=0;
  for(size_t i=0;i<ends[0];i++) {
    int32_t from=spans[i].first+1,to=spans[i].last;
    if(from<to) { cur[2*count]=from; cur[2*count+1]=to; count++; }
  }
  if(!count) { *out_runs=cur; return 0; }
  for(unsigned sample=1;sample<4;sample++) {
    size_t a=0,kept=0,i=ends[sample-1],end=ends[sample];
    while(i<end && a<count) {
      int32_t from=spans[i].first+1,to=spans[i].last;
      if(from>=to) { i++; continue; }
      if(from<cur[2*a+1] && cur[2*a]<to) {
        nxt[2*kept]=from>cur[2*a] ? from : cur[2*a];
        nxt[2*kept+1]=to<cur[2*a+1] ? to : cur[2*a+1];
        kept++;
      }
      if(to<cur[2*a+1]) i++; else a++;
    }
    { int32_t *tmp=cur; cur=nxt; nxt=tmp; }
    count=kept;
    if(!count) break;
  }
  *out_runs=cur;
  return count;
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
    size_t n=(size_t)(right-left);
    /* Preserve the integer rectangle's bulk stores for every fully covered span. */
    if(!mask && bitmap->channels==1) memset(pixel,gray,n);
    else if(!mask && color==0xffffffffu) memset(pixel,255,n*bitmap->channels);
    else if(!mask) {
      uint32_t packed; memcpy(&packed,rgba,4);
      for(size_t k=0;k<n;k++) memcpy(pixel+k*4,&packed,4);
    } else for(x=left;x<right;x++,pixel+=bitmap->channels) {
      unsigned alpha=mask[x];
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
static inline void record_solid_span(uint16_t *solid_spans,const uint16_t *clip_solid,int y,int r0,int r1) {
  if(!solid_spans || r0>=r1) return;
  if(clip_solid) {
    int c0=clip_solid[2*y],c1=clip_solid[2*y+1];
    if(c0>r0) r0=c0;
    if(c1<r1) r1=c1;
    if(r0>=r1) return;
  }
  solid_spans[2*y]=(uint16_t)r0;
  solid_spans[2*y+1]=(uint16_t)r1;
}

static exr_status fill_blend(exr_bitmap *bitmap,const exr_vector_edge *edges,size_t count,
                            exr_vector_rule rule,uint32_t color,const double *cmyk,double cmyk_alpha,
                            const exr_bitmap *clip,exr_blend_mode mode,exr_composite_state *state,
                            exr_vector_scratch *scratch,uint16_t *solid_spans,const uint16_t *clip_solid,
                            uint32_t clip_solid_top,uint32_t clip_solid_bottom,
                            size_t *work,const exr_control *control,exr_error *error) {
  size_t local_work=0,i;
  double low=DBL_MAX,high=-DBL_MAX,left_bound=DBL_MAX,right_bound=-DBL_MAX;
  double stable_until=-DBL_MAX; size_t stable_work=0;
  int y,top,bottom,left,right,write_mask,reuse_coverage,has_vertical=0,coverage_dirty=0;
  uint32_t row_width; size_t height_rows,blocks,touched_words,active_count=0,run_count=0;
  size_t span_capacity=4*count+4;
  int use_runs,use_batch;
  unsigned char stack_buf[2048];
  unsigned char *mem=NULL,*owned_mem=NULL;
  crossing *crossings=NULL; active_edge *active=NULL; uint32_t *bucketed=NULL,*starts=NULL;
  float *coverage=NULL; uint64_t *touched_bits=NULL; unsigned char *opacity=NULL;
  clamped_span *spans=NULL; int32_t *runs_a=NULL,*runs_b=NULL,*runs=NULL;
  exr_status status=EXR_OK;

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
    if(edge->x0<left_bound) left_bound=edge->x0;
    if(edge->x1<left_bound) left_bound=edge->x1;
    if(edge->x0>right_bound) right_bound=edge->x0;
    if(edge->x1>right_bound) right_bound=edge->x1;
    if(edge->y0!=edge->y1) {
      if(edge->x0==edge->x1) has_vertical=1;
      if(edge->y0<low) low=edge->y0;
      if(edge->y1<low) low=edge->y1;
      if(edge->y0>high) high=edge->y0;
      if(edge->y1>high) high=edge->y1;
    }
  }
  status=exr_control_cancel(control,error); if(status!=EXR_OK) return status;
  if((!(cmyk ? cmyk_alpha>0 : (color&255)) && (!state || !(state->knockout || state->shape) || (state->alpha_flags&EXR_ALPHA_CONSTANT_SHAPE))) ||
     high<=0 || low>=bitmap->height || low>=high || right_bound<=0 || left_bound>=bitmap->width || left_bound>=right_bound)
    return exr_fail(error,EXR_OK,"");
  top=(int)fmax(0,floor(low)); bottom=(int)fmin(bitmap->height,ceil(high));
  left=(int)fmax(0,floor(left_bound)); right=(int)fmin(bitmap->width,ceil(right_bound));
  row_width=(uint32_t)(right-left);
  height_rows=(size_t)(bottom-top);
  /* If the active clip is identically 255 across this draw's integer bbox,
     drop the clip pointer for this draw: (alpha*255+127)/255 == alpha. */
  if(clip && clip_solid && (uint32_t)top>=clip_solid_top && (uint32_t)bottom<=clip_solid_bottom) {
    int covered=1;
    for(int ry=top;ry<bottom;ry++) {
      if(left<(int)clip_solid[2*ry] || right>(int)clip_solid[2*ry+1]) { covered=0; break; }
    }
    if(covered) { clip=NULL; clip_solid=NULL; }
  }
  write_mask=bitmap->channels==1 && color==0xffffffffu && !cmyk && !state && mode==EXR_BLEND_NORMAL;
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
      if(write_mask && solid_spans && alpha==255) record_solid_span(solid_spans,clip_solid,y,inner_left,inner_right);
      if(left<inner_left)
        rectangle_span(bitmap,left,left+1,y,(unsigned)floor(first_width*height*255+.5),color,cmyk,cmyk_alpha,clip,mode,state);
      if(right>inner_right && (right-left>1 || left>=inner_left))
        rectangle_span(bitmap,right-1,right,y,(unsigned)floor(last_width*height*255+.5),color,cmyk,cmyk_alpha,clip,mode,state);
    }
    return exr_fail(error,EXR_OK,"");
  }

  blocks=((size_t)row_width+COVERAGE_BLOCK-1)>>COVERAGE_SHIFT;
  touched_words=(blocks+63)>>6;
  use_runs=count<=16384 && (write_mask || (!cmyk && !state));
  use_batch=count<=4096;
  {
    size_t off=0;
    size_t o_cross=off; off+=align8((use_batch ? 4*count : count)*sizeof(*crossings));
    size_t o_active=off; off+=align8(count*sizeof(*active));
    size_t o_bucket=off; off+=align8(count*sizeof(*bucketed));
    size_t o_starts=off; off+=align8((height_rows+1)*sizeof(*starts));
    size_t o_cov=off; off+=align8((size_t)row_width*sizeof(*coverage));
    size_t o_bits=off; off+=align8(touched_words*sizeof(*touched_bits));
    size_t o_opac=off; if(write_mask) off+=align8((size_t)row_width);
    size_t o_spans=off; if(use_runs) off+=align8(span_capacity*sizeof(*spans));
    size_t o_runs=off; if(use_runs) off+=align8(4*span_capacity*sizeof(*runs_a));
    if(off<=sizeof(stack_buf)) {
      mem=stack_buf;
    } else if(scratch && off<=(size_t)2*1024*1024) {
      if(off>scratch->capacity) {
        size_t cap=off<65536 ? 65536 : off;
        void *next_buf=realloc(scratch->data,cap);
        if(!next_buf) { status=exr_fail(error,EXR_MEMORY,"Vector scanline allocation failed"); goto done; }
        scratch->data=next_buf; scratch->capacity=cap;
      }
      mem=scratch->data;
    } else {
      owned_mem=malloc(off);
      if(!owned_mem) { status=exr_fail(error,EXR_MEMORY,"Vector scanline allocation failed"); goto done; }
      mem=owned_mem;
    }
    crossings=(crossing *)(mem+o_cross);
    active=(active_edge *)(mem+o_active);
    bucketed=(uint32_t *)(mem+o_bucket);
    starts=(uint32_t *)(mem+o_starts);
    coverage=(float *)(mem+o_cov);
    touched_bits=(uint64_t *)(mem+o_bits);
    opacity=write_mask ? (mem+o_opac) : NULL;
    spans=use_runs ? (clamped_span *)(mem+o_spans) : NULL;
    runs_a=use_runs ? (int32_t *)(mem+o_runs) : NULL;
    runs_b=use_runs ? runs_a+2*span_capacity : NULL;
  }
  memset(coverage,0,(size_t)row_width*sizeof(*coverage));
  memset(touched_bits,0,touched_words*sizeof(*touched_bits));

  /* Bucket edges by the first row whose samples [y+0.125, y+0.875] they can
     cross. Edges ending at or above top+0.125 or starting past the last sample
     never produce crossings and are skipped up front. */
  memset(starts,0,(height_rows+1)*sizeof(*starts));
  {
    double first_min=top+0.125,first_max=top+0.875,last_max=(double)(bottom-1)+0.875;
    for(i=0;i<count;i++) {
      const exr_vector_edge *edge=&edges[i];
      if(edge->y0==edge->y1) continue;
      double minimum=edge->y0<edge->y1 ? edge->y0 : edge->y1,maximum=edge->y0<edge->y1 ? edge->y1 : edge->y0;
      if(maximum<=first_min || minimum>last_max) continue;
      size_t row=0;
      if(minimum>first_max) {
        double d=minimum-0.875; size_t ci=(size_t)d;
        row=(d>(double)ci ? ci+1 : ci)-(size_t)top;
      }
      if(row<height_rows) starts[row+1]++;
    }
    for(i=0;i<height_rows;i++) starts[i+1]+=starts[i];
    for(i=0;i<count;i++) {
      const exr_vector_edge *edge=&edges[i];
      if(edge->y0==edge->y1) continue;
      double minimum=edge->y0<edge->y1 ? edge->y0 : edge->y1,maximum=edge->y0<edge->y1 ? edge->y1 : edge->y0;
      if(maximum<=first_min || minimum>last_max) continue;
      size_t row=0;
      if(minimum>first_max) {
        double d=minimum-0.875; size_t ci=(size_t)d;
        row=(d>(double)ci ? ci+1 : ci)-(size_t)top;
      }
      if(row<height_rows) bucketed[starts[row]++]=(uint32_t)i;
    }
  }
  /* starts[row] now ends bucket row; bucket row begins at starts[row-1]. */
  reuse_coverage=write_mask && (!control || !control->cancelled);
  for(y=top;y<bottom;y++) {
    unsigned sample,x;
    int build_coverage,keep_coverage;
    status=exr_control_cancel(control,error); if(status!=EXR_OK) goto done;
    {
      /* Drop edges ending at or above y+0.125, append new edges for row y, and
         maintain active edges roughly in x order so per-sample crossing sorts
         run in near-linear time. Equal crossings are summed as a group, so
         active-list order does not affect results. */
      double drop_y=y+0.125;
      size_t r=(size_t)(y-top),first=r ? starts[r-1] : 0,last=starts[r],kept=0;
      for(i=0;i<active_count;i++) {
        if(active[i].max_y>drop_y) {
          if(kept!=i) active[kept]=active[i];
          kept++;
        }
      }
      active_count=kept;
      for(size_t b=first;b<last;b++) {
        const exr_vector_edge *e=&edges[bucketed[b]];
        int upward=e->y1>e->y0;
        active[active_count++]=(active_edge){
          e->x0,e->y0,e->y1-e->y0,e->x1-e->x0,
          upward ? e->y0 : e->y1,upward ? e->y1 : e->y0,
          upward ? e->x0 : e->x1,upward ? 1 : -1,0
        };
      }
      if(active_count>2 && active_count<=128) {
        for(i=1;i<active_count;i++) {
          if(active[i].x_est<active[i-1].x_est) {
            active_edge tmp=active[i]; size_t j=i;
            do { active[j]=active[j-1]; j--; } while(j && tmp.x_est<active[j-1].x_est);
            active[j]=tmp;
          }
        }
      }
    }
    build_coverage=y+.875>=stable_until || !exr_vector_work(work,stable_work);
    if(build_coverage) {
      size_t work_before=*work;
      size_t span_count=0,ends[4]={0,0,0,0};
      int row_use_runs=use_runs,wide_seen=0;
      run_count=0; runs=runs_a;
      if(coverage_dirty) {
        for(size_t w=0;w<touched_words;w++) {
          uint64_t m=touched_bits[w];
          if(!m) continue;
          touched_bits[w]=0;
          while(m) {
            unsigned bit=ctz64(m); m&=m-1;
            size_t from=((w<<6)+bit)<<COVERAGE_SHIFT;
            size_t to=from+COVERAGE_BLOCK<row_width ? from+COVERAGE_BLOCK : row_width;
            memset(coverage+from,0,(to-from)*sizeof(*coverage));
          }
        }
        coverage_dirty=0;
      }
      /* Fast edge-major 4-sample crossing pass when safely below the work limit. */
      size_t max_row_work=4*(count+active_count*25+row_width);
      int batch_ok=use_batch && max_row_work<=(size_t)256*1024*1024 && *work<=(size_t)256*1024*1024-max_row_work;
      if(batch_ok) {
        double s0=y+0.125,s1=y+0.375,s2=y+0.625,s3=y+0.875;
        crossing *c_arr[4]={crossings,crossings+active_count,crossings+2*active_count,crossings+3*active_count};
        size_t n_arr[4]={0,0,0,0};
        for(i=0;i<active_count;i++) {
          active_edge *e=&active[i];
          int w=e->winding;
          if(e->min_y<=s0 && e->max_y>s3) {
            if(e->dx==0.0) {
              double cx=e->x0;
              c_arr[0][n_arr[0]++]=(crossing){cx,w}; c_arr[1][n_arr[1]++]=(crossing){cx,w};
              c_arr[2][n_arr[2]++]=(crossing){cx,w}; c_arr[3][n_arr[3]++]=(crossing){cx,w};
            } else {
              double x0=e->x0,y0=e->y0,dy=e->dy,dx=e->dx;
              double cx0=x0+(s0-y0)/dy*dx,cx1=x0+(s1-y0)/dy*dx,cx2=x0+(s2-y0)/dy*dx,cx3=x0+(s3-y0)/dy*dx;
              c_arr[0][n_arr[0]++]=(crossing){cx0,w}; c_arr[1][n_arr[1]++]=(crossing){cx1,w};
              c_arr[2][n_arr[2]++]=(crossing){cx2,w}; c_arr[3][n_arr[3]++]=(crossing){cx3,w};
              e->x_est=cx3;
            }
          } else {
            double x0=e->x0,y0=e->y0,dy=e->dy,dx=e->dx,miny=e->min_y,maxy=e->max_y,last_x=e->x_est;
            if(s0>=miny && s0<maxy) { last_x=dx==0.0 ? x0 : x0+(s0-y0)/dy*dx; c_arr[0][n_arr[0]++]=(crossing){last_x,w}; }
            if(s1>=miny && s1<maxy) { last_x=dx==0.0 ? x0 : x0+(s1-y0)/dy*dx; c_arr[1][n_arr[1]++]=(crossing){last_x,w}; }
            if(s2>=miny && s2<maxy) { last_x=dx==0.0 ? x0 : x0+(s2-y0)/dy*dx; c_arr[2][n_arr[2]++]=(crossing){last_x,w}; }
            if(s3>=miny && s3<maxy) { last_x=dx==0.0 ? x0 : x0+(s3-y0)/dy*dx; c_arr[3][n_arr[3]++]=(crossing){last_x,w}; }
            e->x_est=last_x;
          }
        }
        for(sample=0;sample<4;sample++) {
          crossing *cs=c_arr[sample]; size_t n=n_arr[sample],at=0,levels=0; double previous=0; int winding=0;
          for(i=n;i>1;i=(i+1)/2) levels++;
          *work+=count+n*(levels+1)+row_width;
          sort_crossings(cs,n);
          while(at<n) {
            double current=cs[at].x; int delta=0;
            if(winding) {
              clamped_span sp;
              if(clamp_span(left,row_width,previous,current,&sp)) {
                if(row_use_runs) {
                  if(!sample && !wide_seen && sp.first+1>=sp.last) accumulate_plain(coverage,touched_bits,&sp);
                  else { if(!sample && sp.first+1<sp.last) wide_seen=1; spans[span_count++]=sp; }
                } else accumulate_plain(coverage,touched_bits,&sp);
              }
            }
            do { delta+=rule==EXR_VECTOR_EVENODD ? 1 : cs[at].winding; at++; } while(at<n && cs[at].x==current);
            if(rule==EXR_VECTOR_EVENODD) winding=(winding+delta)&1; else winding+=delta;
            previous=current;
          }
          ends[sample]=span_count;
          if(!sample && !wide_seen) row_use_runs=0;
        }
      } else {
        for(sample=0;sample<4;sample++) {
          double scan=y+(sample+.5)/4,previous=0; size_t n=0,at=0,sorting=0,levels=0; int winding=0;
          if(!exr_vector_work(work,count)) goto limit;
          for(i=0;i<active_count;i++) {
            active_edge *e=&active[i];
            if(scan>=e->min_y && scan<e->max_y) {
              double cx=e->dx==0.0 ? e->x0 : e->x0+(scan-e->y0)/e->dy*e->dx;
              crossings[n++]=(crossing){cx,e->winding};
              e->x_est=cx;
            }
          }
          for(i=n;i>1;i=(i+1)/2) levels++;
          sorting=n*(levels+1);
          if(!exr_vector_work(work,sorting) || !exr_vector_work(work,row_width)) goto limit;
          sort_crossings(crossings,n);
          while(at<n) {
            double current=crossings[at].x; int delta=0;
            if(winding) {
              clamped_span sp;
              if(clamp_span(left,row_width,previous,current,&sp)) {
                if(row_use_runs) {
                  if(!sample && !wide_seen && sp.first+1>=sp.last) accumulate_plain(coverage,touched_bits,&sp);
                  else { if(!sample && sp.first+1<sp.last) wide_seen=1; spans[span_count++]=sp; }
                } else accumulate_plain(coverage,touched_bits,&sp);
              }
            }
            do { delta+=rule==EXR_VECTOR_EVENODD ? 1 : crossings[at].winding; at++; } while(at<n && crossings[at].x==current);
            if(rule==EXR_VECTOR_EVENODD) winding=(winding+delta)&1; else winding+=delta;
            previous=current;
          }
          ends[sample]=span_count;
          if(!sample && !wide_seen) row_use_runs=0;
        }
      }
      if(row_use_runs && span_count) {
        size_t cursor=0;
        run_count=interior_runs(spans,ends,runs_a,runs_b,&runs);
        if(run_count) {
          for(sample=0,i=0;sample<4;sample++,cursor=0)
            for(;i<ends[sample];i++) accumulate_runs(coverage,touched_bits,&spans[i],runs,run_count,&cursor);
        } else {
          for(i=0;i<span_count;i++) accumulate_plain(coverage,touched_bits,&spans[i]);
        }
      }
      if(reuse_coverage) {
        int all_vertical=1;
        if(!has_vertical) all_vertical=(active_count==0);
        else for(i=0;i<active_count;i++) if(active[i].dx!=0.0) { all_vertical=0; break; }
        if(all_vertical) {
          double change=stable_crossings_until(edges,count,y+.125);
          stable_until=change>y+.875 ? change : -DBL_MAX;
          stable_work=*work-work_before;
        } else {
          stable_until=-DBL_MAX;
        }
      }
    }
    if(!exr_vector_work(work,(size_t)row_width*((state ? 20+state->depth*4 : 0)+(mode==EXR_BLEND_NORMAL ? 1 : mode<EXR_BLEND_HUE ? 24 : 64)))) goto limit;
    keep_coverage=write_mask && stable_until>y+.875;
    if(keep_coverage) coverage_dirty=1;

    /* Clip masks paint opaque white into one channel. Keep the identical
       source-over arithmetic in a row loop without per-pixel paint dispatch. */
    if(write_mask) {
      unsigned char *target=bitmap->pixels+(size_t)y*bitmap->stride+left;
      const unsigned char *mask=clip ? clip->pixels+(size_t)y*clip->stride+left : NULL;
      if(!keep_coverage && build_coverage) {
        /* Common non-stable row: consume coverage directly without packing into
           opacity[], skipping zero-coverage pixels and zeroing on consume. */
        if(!mask) {
          for(size_t w=0;w<touched_words;w++) {
            uint64_t m=touched_bits[w];
            if(!m) continue;
            touched_bits[w]=0;
            while(m) {
              unsigned bit=ctz64(m); m&=m-1;
              size_t from=((w<<6)+bit)<<COVERAGE_SHIFT;
              size_t to=from+COVERAGE_BLOCK<row_width ? from+COVERAGE_BLOCK : row_width;
              for(x=(unsigned)from;x<to;x++) {
                float cov=coverage[x];
                if(cov==0.0f) continue;
                coverage[x]=0.0f;
                unsigned alpha=cov>=4.0f ? 255u : (unsigned)(cov*255/4+.5);
                if(!alpha) continue;
                if(!target[x] || alpha==255u) target[x]=(unsigned char)alpha;
                else target[x]=(unsigned char)(target[x]+((255u-target[x])*alpha+127)/255);
              }
            }
          }
        } else {
          for(size_t w=0;w<touched_words;w++) {
            uint64_t m=touched_bits[w];
            if(!m) continue;
            touched_bits[w]=0;
            while(m) {
              unsigned bit=ctz64(m); m&=m-1;
              size_t from=((w<<6)+bit)<<COVERAGE_SHIFT;
              size_t to=from+COVERAGE_BLOCK<row_width ? from+COVERAGE_BLOCK : row_width;
              for(x=(unsigned)from;x<to;x++) {
                float cov=coverage[x];
                if(cov==0.0f) continue;
                coverage[x]=0.0f;
                unsigned alpha=cov>=4.0f ? 255u : (unsigned)(cov*255/4+.5);
                if(!alpha) continue;
                alpha=(alpha*mask[x]+127)/255;
                if(!alpha) continue;
                if(!target[x] || alpha==255u) target[x]=(unsigned char)alpha;
                else target[x]=(unsigned char)(target[x]+((255u-target[x])*alpha+127)/255);
              }
            }
          }
        }
      } else {
        /* Stable row: pack touched pixels into opacity[] once and keep bits/coverage. */
        for(size_t w=0;w<touched_words;w++) {
          uint64_t m=touched_bits[w];
          if(!m) continue;
          while(m) {
            unsigned bit=ctz64(m); m&=m-1;
            size_t from=((w<<6)+bit)<<COVERAGE_SHIFT;
            size_t to=from+COVERAGE_BLOCK<row_width ? from+COVERAGE_BLOCK : row_width;
            if(build_coverage) for(x=(unsigned)from;x<to;x++)
              opacity[x]=coverage[x]>=4.0f ? 255 : (unsigned char)(coverage[x]*255/4+.5);
            for(x=(unsigned)from;x<to;x++) {
              unsigned alpha=opacity[x];
              if(!alpha) continue;
              if(mask) { alpha=(alpha*mask[x]+127)/255; if(!alpha) continue; }
              if(!target[x] || alpha==255u) target[x]=(unsigned char)alpha;
              else target[x]=(unsigned char)(target[x]+((255u-target[x])*alpha+127)/255);
            }
          }
        }
      }
      /* Paint interior runs (opacity 255) and track the widest run for solid-clip elision. */
      if(run_count) {
        int best_l=0,best_r=0;
        for(i=0;i<run_count;i++) {
          int32_t r0=runs[2*i],r1=runs[2*i+1];
          if(r1-r0>best_r-best_l) { best_l=r0; best_r=r1; }
          if(!mask) {
            memset(target+r0,255,(size_t)(r1-r0));
          } else {
            for(int32_t px=r0;px<r1;px++) {
              unsigned alpha=mask[px];
              if(!alpha) continue;
              if(!target[px] || alpha==255u) target[px]=(unsigned char)alpha;
              else target[px]=(unsigned char)(target[px]+((255u-target[px])*alpha+127)/255);
            }
          }
        }
        if(solid_spans && best_r>best_l) record_solid_span(solid_spans,clip_solid,y,left+best_l,left+best_r);
      }
      continue;
    }

    if(!cmyk && !state && mode==EXR_BLEND_NORMAL && bitmap->channels==4 && (color&255)==255) {
      unsigned r=color>>24,g=(color>>16)&255,b=(color>>8)&255;
      const unsigned char rgba[4]={(unsigned char)r,(unsigned char)g,(unsigned char)b,255};
      uint32_t packed; memcpy(&packed,rgba,4);
      unsigned char *row_dst=bitmap->pixels+(size_t)y*bitmap->stride+(size_t)left*4;
      if(!clip) {
        for(size_t w=0;w<touched_words;w++) {
          uint64_t m=touched_bits[w];
          if(!m) continue;
          touched_bits[w]=0;
          while(m) {
            unsigned bit=ctz64(m); m&=m-1;
            size_t from=((w<<6)+bit)<<COVERAGE_SHIFT;
            size_t to=from+COVERAGE_BLOCK<row_width ? from+COVERAGE_BLOCK : row_width;
            for(x=(unsigned)from;x<to;x++) {
              float cov=coverage[x];
              if(cov==0.0f) continue;
              coverage[x]=0.0f;
              unsigned alpha=cov>=4.0f ? 255u : (unsigned)(cov*255/4+.5);
              if(!alpha) continue;
              unsigned char *p=row_dst+(size_t)x*4;
              if(alpha==255u) { memcpy(p,&packed,4); }
              else if(p[3]==255u) {
                unsigned inv=255u-alpha;
                p[0]=(unsigned char)((p[0]*inv+r*alpha+127)/255);
                p[1]=(unsigned char)((p[1]*inv+g*alpha+127)/255);
                p[2]=(unsigned char)((p[2]*inv+b*alpha+127)/255);
              } else exr_pixel(bitmap,left+(int)x,y,color,alpha);
            }
          }
        }
      } else {
        const unsigned char *clip_row=clip->pixels+(size_t)y*clip->stride+(unsigned)left;
        for(size_t w=0;w<touched_words;w++) {
          uint64_t m=touched_bits[w];
          if(!m) continue;
          touched_bits[w]=0;
          while(m) {
            unsigned bit=ctz64(m); m&=m-1;
            size_t from=((w<<6)+bit)<<COVERAGE_SHIFT;
            size_t to=from+COVERAGE_BLOCK<row_width ? from+COVERAGE_BLOCK : row_width;
            for(x=(unsigned)from;x<to;x++) {
              float cov=coverage[x];
              if(cov==0.0f) continue;
              coverage[x]=0.0f;
              unsigned cm=clip_row[x];
              if(!cm) continue;
              unsigned alpha=cov>=4.0f ? 255u : (unsigned)(cov*255/4+.5);
              if(cm!=255u) alpha=(alpha*cm+127)/255;
              if(!alpha) continue;
              unsigned char *p=row_dst+(size_t)x*4;
              if(alpha==255u) { memcpy(p,&packed,4); }
              else if(p[3]==255u) {
                unsigned inv=255u-alpha;
                p[0]=(unsigned char)((p[0]*inv+r*alpha+127)/255);
                p[1]=(unsigned char)((p[1]*inv+g*alpha+127)/255);
                p[2]=(unsigned char)((p[2]*inv+b*alpha+127)/255);
              } else exr_pixel(bitmap,left+(int)x,y,color,alpha);
            }
          }
        }
      }
    } else {
      const unsigned char *clip_row=clip ? clip->pixels+(size_t)y*clip->stride+(unsigned)left : NULL;
      for(size_t w=0;w<touched_words;w++) {
        uint64_t m=touched_bits[w];
        if(!m) continue;
        touched_bits[w]=0;
        while(m) {
          unsigned bit=ctz64(m); m&=m-1;
          size_t from=((w<<6)+bit)<<COVERAGE_SHIFT;
          size_t to=from+COVERAGE_BLOCK<row_width ? from+COVERAGE_BLOCK : row_width;
          for(x=(unsigned)from;x<to;x++) {
            float cov=coverage[x];
            if(cov==0.0f) continue;
            coverage[x]=0.0f;
            /* Coverage is nonnegative: truncation after adding .5 equals floor. */
            unsigned alpha=cov>=4.0f ? 255u : (unsigned)(cov*255/4+.5);
            if(clip_row) alpha=(alpha*clip_row[x]+127)/255;
            if(alpha) {
              if(cmyk) exr_pixel_composite_cmyk(bitmap,left+(int)x,y,cmyk,cmyk_alpha,alpha,mode,state);
              else if(state) exr_pixel_composite(bitmap,left+(int)x,y,color,alpha,mode,state);
              else if(mode==EXR_BLEND_NORMAL) exr_pixel(bitmap,left+(int)x,y,color,alpha);
              else exr_pixel_blend(bitmap,left+(int)x,y,color,alpha,mode);
            }
          }
        }
      }
    }
    /* Run pixels kept coverage 0 above; each is painted once at alpha 255. */
    for(i=0;i<run_count;i++) rectangle_span(bitmap,left+runs[2*i],left+runs[2*i+1],y,255,color,cmyk,cmyk_alpha,clip,mode,state);
  }
  status=exr_fail(error,EXR_OK,""); goto done;
limit:
  status=exr_fail(error,EXR_LIMIT,"Vector raster work budget exceeded");
done:
  free(owned_mem); return status;
}

exr_status exr_vector_fill_blend_ex(exr_bitmap *bitmap,const exr_vector_edge *edges,size_t count,
  exr_vector_rule rule,uint32_t color,const double *cmyk,double cmyk_alpha,const exr_bitmap *clip,
  exr_blend_mode mode,exr_composite_state *state,exr_vector_scratch *scratch,
  uint16_t *solid_spans,const uint16_t *clip_solid,uint32_t clip_solid_top,uint32_t clip_solid_bottom,
  size_t *work,const exr_control *control,exr_error *error) {
  return fill_blend(bitmap,edges,count,rule,color,cmyk,cmyk_alpha,clip,mode,state,scratch,solid_spans,clip_solid,clip_solid_top,clip_solid_bottom,work,control,error);
}
exr_status exr_vector_fill_blend(exr_bitmap *bitmap,const exr_vector_edge *edges,size_t count,
                            exr_vector_rule rule,uint32_t color,const exr_bitmap *clip,exr_blend_mode mode,exr_composite_state *state,
                            size_t *work,const exr_control *control,exr_error *error) {
  return fill_blend(bitmap,edges,count,rule,color,NULL,0,clip,mode,state,NULL,NULL,NULL,0,0,work,control,error);
}
exr_status exr_vector_fill_blend_cmyk(exr_bitmap *bitmap,const exr_vector_edge *edges,size_t count,
                            exr_vector_rule rule,const double cmyk[4],double alpha,const exr_bitmap *clip,exr_blend_mode mode,
                            exr_composite_state *state,size_t *work,const exr_control *control,exr_error *error) {
  return fill_blend(bitmap,edges,count,rule,0,cmyk,alpha,clip,mode,state,NULL,NULL,NULL,0,0,work,control,error);
}
exr_status exr_vector_fill(exr_bitmap *bitmap,const exr_vector_edge *edges,size_t count,
  exr_vector_rule rule,uint32_t color,const exr_bitmap *clip,size_t *work,const exr_control *control,exr_error *error) {
  return exr_vector_fill_blend(bitmap,edges,count,rule,color,clip,EXR_BLEND_NORMAL,NULL,work,control,error);
}
