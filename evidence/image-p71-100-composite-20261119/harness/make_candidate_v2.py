# SPDX-License-Identifier: MIT
"""Write v2 candidate of src/affine_image.c:
  - Per-row full-coverage interior span [full_x0, full_x1) when clip is present
  - Site 3 (axis_store): skip exr_pixel when (color & coverage & 255) == 255
  - Site 4 (axis_flat_row_paint): hoist (rgba & 255) == 255 outside the run loop,
    skip exr_pixel completely on opaque runs (branchless fill inside [full_x0, full_x1)),
    and pass constant coverage=255 for non-opaque runs inside [full_x0, full_x1).

usage: make_candidate_v2.py <src affine_image.c> <out>
"""
import sys
from pathlib import Path

src, out = Path(sys.argv[1]), Path(sys.argv[2])
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

# 2. Add helpers + site 3 opaque fast path in axis_store
helper = '''/* exr_pixel with effective alpha 255 stores the source bytes on every RGBA
   branch: opaque destination (c*255+127)/255=c; transparent destination;
   partial destination with denominator 255*255, giving c and alpha 255. */
static inline int axis_opaque(uint32_t color,unsigned coverage) { return (color&coverage&255)==255; }
static inline void axis_opaque_store(unsigned char *p,uint32_t color) {
  const unsigned char bytes[4]={(unsigned char)(color>>24),(unsigned char)(color>>16),(unsigned char)(color>>8),255};
  memcpy(p,bytes,4);
}
static void axis_clip_full_span(const unsigned char *cov,int x0,int x1,int *full_x0,int *full_x1) {
  if(!cov) { *full_x0=x0; *full_x1=x1; return; }
  int a=x0,b=x1;
  while(a<b && cov[a]!=255) a++;
  while(b>a && cov[b-1]!=255) b--;
  int p=a;
  while(p+8<=b) {
    uint64_t v; memcpy(&v,cov+p,8);
    if(v!=~UINT64_C(0)) { *full_x0=0; *full_x1=0; return; }
    p+=8;
  }
  while(p<b) { if(cov[p]!=255) { *full_x0=0; *full_x1=0; return; } p++; }
  *full_x0=a; *full_x1=b;
}
static inline void axis_store(const axis_row *r,int x,const double sums[4],unsigned coverage) {'''

rep('static inline void axis_store(const axis_row *r,int x,const double sums[4],unsigned coverage) {', helper)
rep(
    '''  for(unsigned k=0;k<3;k++) color|=image_byte(sums[k]/sums[3])<<(24-8*k);
  exr_pixel(r->target,x,r->y,color,coverage);''',
    '''  for(unsigned k=0;k<3;k++) color|=image_byte(sums[k]/sums[3])<<(24-8*k);
  if(axis_opaque(color,coverage)) axis_opaque_store(r->target->pixels+(size_t)r->y*r->target->stride+(size_t)x*4,color);
  else exr_pixel(r->target,x,r->y,color,coverage);'''
)

# 3. Site 4 hoisted opaque fast path + full-coverage span
rep(
    '''    uint32_t rgba=((uint32_t)p[0]<<24)|((uint32_t)p[1]<<16)|((uint32_t)p[2]<<8)|(q ? q[0] : 255);
    do {
      unsigned coverage=r->coverage ? r->coverage[x] : 255;
      exr_pixel(r->target,x,r->y,rgba,coverage);
      x++;tap+=2;
    } while(x<r->x1 && tap[1].second>=0 && tap[1].second<next);
    pending=x;''',
    '''    uint32_t rgba=((uint32_t)p[0]<<24)|((uint32_t)p[1]<<16)|((uint32_t)p[2]<<8)|(q ? q[0] : 255);
    if((rgba&255)==255) {
      unsigned char *d=r->target->pixels+(size_t)r->y*r->target->stride+(size_t)x*4;
      const unsigned char bytes[4]={p[0],p[1],p[2],255};
      if(x>=r->full_x0 && x<r->full_x1) {
        do {
          memcpy(d,bytes,4);
          d+=4;x++;tap+=2;
        } while(x<r->full_x1 && tap[1].second>=0 && tap[1].second<next);
      }
      while(x<r->x1 && tap[1].second>=0 && tap[1].second<next) {
        unsigned coverage=r->coverage ? r->coverage[x] : 255;
        if(coverage==255) memcpy(d,bytes,4); else exr_pixel(r->target,x,r->y,rgba,coverage);
        d+=4;x++;tap+=2;
      }
    } else if(x>=r->full_x0 && x<r->full_x1) {
      do {
        exr_pixel(r->target,x,r->y,rgba,255);
        x++;tap+=2;
      } while(x<r->full_x1 && tap[1].second>=0 && tap[1].second<next);
      while(x<r->x1 && tap[1].second>=0 && tap[1].second<next) {
        exr_pixel(r->target,x,r->y,rgba,r->coverage ? r->coverage[x] : 255);
        x++;tap+=2;
      }
    } else {
      do {
        unsigned coverage=r->coverage ? r->coverage[x] : 255;
        exr_pixel(r->target,x,r->y,rgba,coverage);
        x++;tap+=2;
      } while(x<r->x1 && tap[1].second>=0 && tap[1].second<next);
    }
    pending=x;'''
)

# 4. Compute full_x0, full_x1 once per row in axis_paint
rep(
    '    r.alpha=alpha;r.y=y;r.x0=x0;r.x1=x1;r.luminosity=mask_mode==1;',
    '    r.alpha=alpha;r.y=y;r.x0=x0;r.x1=x1;r.luminosity=mask_mode==1;\n    axis_clip_full_span(r.coverage,x0,x1,&r.full_x0,&r.full_x1);'
)

out.write_text(a)
