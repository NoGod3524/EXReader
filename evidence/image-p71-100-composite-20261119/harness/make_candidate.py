# SPDX-License-Identifier: MIT
"""Write candidate variants of src/affine_image.c.

usage: make_candidate.py <src affine_image.c> <out> <variant>
  site4   flat-run stores only
  site3   axis_store direct store only
  both    both
"""
import sys
from pathlib import Path
src, out, variant = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
a = src.read_text()
def rep(old, new):
    global a
    assert a.count(old) == 1, old
    a = a.replace(old, new)
helper = '''/* exr_pixel with effective alpha 255 stores the source bytes on every RGBA
   branch: opaque destination (c*255+127)/255=c; transparent destination;
   partial destination with denominator 255*255, giving c and alpha 255. */
static inline int axis_opaque(uint32_t color,unsigned coverage) { return (color&coverage&255)==255; }
static inline void axis_opaque_store(unsigned char *p,uint32_t color) {
  const unsigned char bytes[4]={(unsigned char)(color>>24),(unsigned char)(color>>16),(unsigned char)(color>>8),255};
  memcpy(p,bytes,4);
}
static inline void axis_store(const axis_row *r,int x,const double sums[4],unsigned coverage) {'''
if variant in ('site3', 'both'):
    rep('static inline void axis_store(const axis_row *r,int x,const double sums[4],unsigned coverage) {', helper)
    rep('''  for(unsigned k=0;k<3;k++) color|=image_byte(sums[k]/sums[3])<<(24-8*k);
  exr_pixel(r->target,x,r->y,color,coverage);''', '''  for(unsigned k=0;k<3;k++) color|=image_byte(sums[k]/sums[3])<<(24-8*k);
  if(axis_opaque(color,coverage)) axis_opaque_store(r->target->pixels+(size_t)r->y*r->target->stride+(size_t)x*4,color);
  else exr_pixel(r->target,x,r->y,color,coverage);''')
elif variant == 'site4':
    rep('static inline void axis_store(const axis_row *r,int x,const double sums[4],unsigned coverage) {', helper)
if variant in ('site4', 'both'):
    rep('''    uint32_t rgba=((uint32_t)p[0]<<24)|((uint32_t)p[1]<<16)|((uint32_t)p[2]<<8)|(q ? q[0] : 255);
    do {
      unsigned coverage=r->coverage ? r->coverage[x] : 255;
      exr_pixel(r->target,x,r->y,rgba,coverage);
      x++;tap+=2;
    } while(x<r->x1 && tap[1].second>=0 && tap[1].second<next);
    pending=x;''', '''    uint32_t rgba=((uint32_t)p[0]<<24)|((uint32_t)p[1]<<16)|((uint32_t)p[2]<<8)|(q ? q[0] : 255);
    int start=x;
    /* The run's extent depends only on the column taps, never on the target. */
    do { x++;tap+=2; } while(x<r->x1 && tap[1].second>=0 && tap[1].second<next);
    unsigned char *d=r->target->pixels+(size_t)r->y*r->target->stride+(size_t)start*4;
    if((rgba&255)==255 && !r->coverage) for(int k=start;k<x;k++,d+=4) axis_opaque_store(d,rgba);
    else for(int k=start;k<x;k++,d+=4) {
      unsigned coverage=r->coverage ? r->coverage[k] : 255;
      if(axis_opaque(rgba,coverage)) axis_opaque_store(d,rgba); else exr_pixel(r->target,k,r->y,rgba,coverage);
    }
    pending=x;''')
out.write_text(a)
