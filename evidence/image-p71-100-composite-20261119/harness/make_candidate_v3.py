# SPDX-License-Identifier: MIT
"""Write clean compositing-skip candidate variants of src/affine_image.c.

usage: make_candidate_v3.py <src affine_image.c> <out> <variant>
variants:
  s4-opaque   Site 4 opaque fill + zero-alpha skip + constant cov=255 in full span
  s4-full     Site 4 opaque fill + zero-alpha skip + translucent constant-dst run skip
  s3-opaque   Site 3 full-span split + opaque direct store (no Site 4 change)
  s3-full     Site 3 full-span split + opaque direct store + repeat (color,dst) skip
  all-no-s3b  Site 3 opaque + Site 4 full (opaque + translucent constant-dst skip)
  all         Site 3 full (opaque + repeat color/dst) + Site 4 full (opaque + const-dst)
"""
import sys
from pathlib import Path

src, out, variant = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
assert variant in ('s4-opaque', 's4-full', 's3-opaque', 's3-full', 'all-no-s3b', 'all'), variant

use_s3_opaque = variant in ('s3-opaque', 's3-full', 'all-no-s3b', 'all')
use_s3_repeat = variant in ('s3-full', 'all')
use_s4_opaque = variant in ('s4-opaque', 's4-full', 'all-no-s3b', 'all')
use_s4_constdst = variant in ('s4-full', 'all-no-s3b', 'all')

a = src.read_text()

def rep(old, new):
    global a
    assert a.count(old) == 1, old
    a = a.replace(old, new)

# 1. Add full_x0, full_x1 to axis_row
rep(
    '  exr_bitmap *target; const unsigned char *coverage; const axis_layer *color,*mask; double alpha; int y,x0,x1,luminosity,valid[2];',
    '  exr_bitmap *target; const unsigned char *coverage; const axis_layer *color,*mask; double alpha; int y,x0,x1,full_x0,full_x1,luminosity,valid[2];'
)

# 2. Helpers: opaque direct store + SSE2 per-row full-coverage clip span
helpers = ('''/* exr_pixel with effective alpha 255 stores the source bytes on every RGBA
   branch: opaque destination (c*255+127)/255=c; transparent destination;
   partial destination with denominator 255*255, giving c and alpha 255. */
static inline int axis_opaque(uint32_t color,unsigned coverage) { return (color&coverage&255)==255; }
static inline void axis_opaque_store(unsigned char *p,uint32_t color) {
  const unsigned char bytes[4]={(unsigned char)(color>>24),(unsigned char)(color>>16),(unsigned char)(color>>8),255};
  memcpy(p,bytes,4);
}
''' if use_s3_opaque else '') + '''static void axis_clip_full_span(const unsigned char *cov,int x0,int x1,int *full_x0,int *full_x1) {
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
'''

rep('static inline void axis_store(const axis_row *r,int x,const double sums[4],unsigned coverage) {',
    helpers + 'static inline void axis_store(const axis_row *r,int x,const double sums[4],unsigned coverage) {')

# 3. Site 3: axis_store and axis_row_paint
if use_s3_opaque:
    rep(
        '''static inline void axis_store(const axis_row *r,int x,const double sums[4],unsigned coverage) {
  if(!sums[3]) return;
  uint32_t color=image_byte(sums[3]*r->alpha/4);
  for(unsigned k=0;k<3;k++) color|=image_byte(sums[k]/sums[3])<<(24-8*k);
  exr_pixel(r->target,x,r->y,color,coverage);
}
static void axis_row_paint(const axis_row *r,int first,int last) {
  const axis_layer *c=r->color,*m=r->mask;
  for(int x=first;x<last;x++) {
    unsigned coverage=r->coverage ? r->coverage[x] : 255;
    const image_tap *cc=c->columns+2*(size_t)(x-r->x0),*mc=m ? m->columns+2*(size_t)(x-r->x0) : NULL;
    __m128d rg=_mm_setzero_pd(),ba=_mm_setzero_pd();double sums[4];
    if(!coverage) continue;
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
    axis_store(r,x,sums,coverage);
  }
}''',
        ('''static inline void axis_sample_pixel(const axis_row *r,int x,double sums[4]) {
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
  for(unsigned k=0;k<3;k++) color|=image_byte(sums[k]/sums[3])<<(24-8*k);
  if(axis_opaque(color,coverage)) axis_opaque_store(r->target->pixels+(size_t)r->y*r->target->stride+(size_t)x*4,color);
  else exr_pixel(r->target,x,r->y,color,coverage);
}
static void axis_row_paint_clipped(const axis_row *r,int first,int last) {
  for(int x=first;x<last;x++) {
    unsigned coverage=r->coverage ? r->coverage[x] : 255;
    double sums[4];
    if(!coverage) continue;
    axis_sample_pixel(r,x,sums);
    axis_store(r,x,sums,coverage);
  }
}
static void axis_row_paint_full(const axis_row *r,int first,int last) {
  unsigned char *row=r->target->pixels+(size_t)r->y*r->target->stride;''' + ('''
  uint32_t prev_color=0,prev_dst=0,prev_out=0;''' if use_s3_repeat else '') + '''
  for(int x=first;x<last;x++) {
    double sums[4];
    axis_sample_pixel(r,x,sums);
    if(!sums[3]) continue;
    uint32_t color=image_byte(sums[3]*r->alpha/4);
    if(!color) continue;
    for(unsigned k=0;k<3;k++) color|=image_byte(sums[k]/sums[3])<<(24-8*k);
    unsigned char *p=row+(size_t)x*4;
    if((color&255)==255) { axis_opaque_store(p,color); continue; }''' + ('''
    uint32_t dst; memcpy(&dst,p,4);
    if(color==prev_color && dst==prev_dst) { memcpy(p,&prev_out,4); continue; }
    exr_pixel(r->target,x,r->y,color,255);
    prev_color=color; prev_dst=dst; memcpy(&prev_out,p,4);''' if use_s3_repeat else '''
    exr_pixel(r->target,x,r->y,color,255);''') + '''
  }
}
static void axis_row_paint(const axis_row *r,int first,int last) {
  int f0=first>r->full_x0 ? first : r->full_x0;
  int f1=last<r->full_x1 ? last : r->full_x1;
  if(f0>=f1) { axis_row_paint_clipped(r,first,last); return; }
  if(first<f0) axis_row_paint_clipped(r,first,f0);
  axis_row_paint_full(r,f0,f1);
  if(f1<last) axis_row_paint_clipped(r,f1,last);
}''')
    )

# 4. Site 4: axis_flat_row_paint
if use_s4_opaque:
    if use_s4_constdst:
        translucent_full_body = '''    } else if(start>=r->full_x0 && end<=r->full_x1) {
      unsigned char *d=r->target->pixels+(size_t)r->y*r->target->stride+(size_t)start*4;
      uint32_t last_dst,last_out;
      memcpy(&last_dst,d,4);
      exr_pixel(r->target,start,r->y,rgba,255);
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
              else { exr_pixel(r->target,k,r->y,rgba,255); last_dst=cur; memcpy(&last_out,d,4); }
            }
            vdst=_mm_set1_epi32((int)last_dst);
            vout=_mm_set1_epi32((int)last_out);
          }
        }
      }
      for(;k<end;k++,d+=4) {
        uint32_t cur; memcpy(&cur,d,4);
        if(cur==last_dst) memcpy(d,&last_out,4);
        else { exr_pixel(r->target,k,r->y,rgba,255); last_dst=cur; memcpy(&last_out,d,4); }
      }'''
    else:
        translucent_full_body = '''    } else if(start>=r->full_x0 && end<=r->full_x1) {
      for(int k=start;k<end;k++) exr_pixel(r->target,k,r->y,rgba,255);'''

    rep(
        '''    uint32_t rgba=((uint32_t)p[0]<<24)|((uint32_t)p[1]<<16)|((uint32_t)p[2]<<8)|(q ? q[0] : 255);
    do {
      unsigned coverage=r->coverage ? r->coverage[x] : 255;
      exr_pixel(r->target,x,r->y,rgba,coverage);
      x++;tap+=2;
    } while(x<r->x1 && tap[1].second>=0 && tap[1].second<next);
    pending=x;''',
        '''    uint32_t rgba=((uint32_t)p[0]<<24)|((uint32_t)p[1]<<16)|((uint32_t)p[2]<<8)|(q ? q[0] : 255);
    int start=x;
    do { x++;tap+=2; } while(x<r->x1 && tap[1].second>=0 && tap[1].second<next);
    int end=x;
    unsigned alpha_byte=rgba&255;
    if(!alpha_byte) {
      /* Effective alpha is 0 for every coverage; exr_pixel is a no-op. */
    } else if(alpha_byte==255) {
      unsigned char *d=r->target->pixels+(size_t)r->y*r->target->stride+(size_t)start*4;
      const unsigned char bytes[4]={p[0],p[1],p[2],255};
      uint32_t packed; memcpy(&packed,bytes,4);
      if(start>=r->full_x0 && end<=r->full_x1) {
        int n=end-start;
        if(n>=4) {
          __m128i v=_mm_set1_epi32((int)packed);
          while(n>=4) { _mm_storeu_si128((__m128i *)d,v); d+=16; n-=4; }
        }
        while(n--) { memcpy(d,&packed,4); d+=4; }
      } else {
        for(int k=start;k<end;k++,d+=4) {
          unsigned coverage=r->coverage ? r->coverage[k] : 255;
          if(coverage==255) memcpy(d,&packed,4); else exr_pixel(r->target,k,r->y,rgba,coverage);
        }
      }
''' + translucent_full_body + '''
    } else {
      for(int k=start;k<end;k++) {
        unsigned coverage=r->coverage ? r->coverage[k] : 255;
        exr_pixel(r->target,k,r->y,rgba,coverage);
      }
    }
    pending=x;'''
    )

# 5. Guard target->channels==4 and compute full_x0, full_x1 once per row in axis_paint
rep(
    '  axis_layer color,mask; size_t width;\n  if(inv[1] || inv[2] || x1<=x0 || y1<=y0) return 0;',
    '  axis_layer color,mask; size_t width;\n  if(target->channels!=4 || inv[1] || inv[2] || x1<=x0 || y1<=y0) return 0;'
)
rep(
    '    r.alpha=alpha;r.y=y;r.x0=x0;r.x1=x1;r.luminosity=mask_mode==1;',
    '    r.alpha=alpha;r.y=y;r.x0=x0;r.x1=x1;r.luminosity=mask_mode==1;\n    axis_clip_full_span(r.coverage,x0,x1,&r.full_x0,&r.full_x1);'
)

out.write_text(a)
