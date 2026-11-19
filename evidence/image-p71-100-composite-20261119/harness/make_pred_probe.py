# SPDX-License-Identifier: MIT
"""Counter-only probe for all compositing-skip predicates at Site 3 and Site 4.

Counters (per render):
  0  s3_total
  1  s3_opaque_fullcov        ((color&255)==255 && cov==255)
  2  s3_opaque_in_full_span   ((color&255)==255 && x in [full_x0, full_x1))
  3  s3_nonopaque_fullcov     (0<(color&255)<255 && cov==255)
  4  s3_nonopaque_in_full_span
  5  s3_nonopaque_repeat_color_dst  (in full_span, color==prev_color && dst==prev_dst)
  6  s3_nonopaque_same_color_any_dst
  7  s3_partial_cov           (cov < 255)
  8  s4_total
  9  s4_opaque_fullcov        ((rgba&255)==255 && cov==255)
  10 s4_opaque_in_full_span   ((rgba&255)==255 && x in [full_x0, full_x1))
  11 s4_nonopaque_fullcov     (0<(rgba&255)<255 && cov==255)
  12 s4_nonopaque_in_full_span
  13 s4_nonopaque_repeat_dst_in_run (in full_span, k>0 && dst==prev_dst)
  14 s4_nonopaque_compute_in_run    (in full_span, k==0 || dst!=prev_dst)
  15 s4_nonopaque_repeat_across_runs (k==0 && rgba==last_rgba && dst==last_dst)
  16 s4_partial_cov           (cov < 255)
  17 s4_runs_opaque
  18 s4_runs_nonopaque
  19 s4_nonopaque_vec4_hits   (aligned-to-run 4-pixel chunks where all 4 dst == prev_dst)
  20 rows_total
  21 rows_full_span_nonempty
  22 rows_full_span_pixels
  23 rows_total_pixels
"""
import sys
from pathlib import Path

src, out = Path(sys.argv[1]), Path(sys.argv[2])
a = src.read_text()

def rep(old, new):
    global a
    assert a.count(old) == 1, old
    a = a.replace(old, new)

prefix = '''
unsigned long long pred_cnt[32];
__declspec(dllexport) void pred_reset(void) { for(unsigned i=0;i<32;i++) pred_cnt[i]=0; }
__declspec(dllexport) void pred_read(unsigned long long *o) { for(unsigned i=0;i<32;i++) o[i]=pred_cnt[i]; }
'''

rep('static int storage(const exr_bitmap *b) {', prefix + 'static int storage(const exr_bitmap *b) {')

rep(
    '  exr_bitmap *target; const unsigned char *coverage; const axis_layer *color,*mask; double alpha; int y,x0,x1,luminosity,valid[2];',
    '  exr_bitmap *target; const unsigned char *coverage; const axis_layer *color,*mask; double alpha; int y,x0,x1,full_x0,full_x1,luminosity,valid[2];\n  uint32_t s3_prev_color,s3_prev_dst,s4_prev_rgba,s4_prev_dst; int s3_has_prev,s4_has_prev;'
)

span_fn = '''static void pred_clip_full_span(const unsigned char *cov,int x0,int x1,int *full_x0,int *full_x1) {
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

rep('static inline void axis_store(const axis_row *r,int x,const double sums[4],unsigned coverage) {', span_fn)

# Need mutable pointer for tracking prev state in axis_row_paint/axis_store
rep('static inline void axis_store(const axis_row *r,int x,const double sums[4],unsigned coverage) {',
    'static inline void axis_store(axis_row *r,int x,const double sums[4],unsigned coverage) {')
rep('static void axis_row_paint(const axis_row *r,int first,int last) {',
    'static void axis_row_paint(axis_row *r,int first,int last) {')
rep('static void axis_flat_row_paint(const axis_row *r,const image_tap ytaps[2]) {',
    'static void axis_flat_row_paint(axis_row *r,const image_tap ytaps[2]) {')

rep(
    '''  for(unsigned k=0;k<3;k++) color|=image_byte(sums[k]/sums[3])<<(24-8*k);
  exr_pixel(r->target,x,r->y,color,coverage);''',
    '''  for(unsigned k=0;k<3;k++) color|=image_byte(sums[k]/sums[3])<<(24-8*k);
  {
    const unsigned char *dp=r->target->pixels+(size_t)r->y*r->target->stride+(size_t)x*4;
    uint32_t dst; memcpy(&dst,dp,4);
    int in_full=(x>=r->full_x0 && x<r->full_x1);
    unsigned a=color&255;
    pred_cnt[0]++;
    if(coverage<255) { pred_cnt[7]++; r->s3_has_prev=0; }
    else if(a==255) {
      pred_cnt[1]++; if(in_full) pred_cnt[2]++;
      r->s3_has_prev=0;
    } else if(a>0) {
      pred_cnt[3]++;
      if(in_full) {
        pred_cnt[4]++;
        if(r->s3_has_prev && color==r->s3_prev_color) {
          pred_cnt[6]++;
          if(dst==r->s3_prev_dst) pred_cnt[5]++;
        }
        r->s3_prev_color=color; r->s3_prev_dst=dst; r->s3_has_prev=1;
      } else r->s3_has_prev=0;
    }
  }
  exr_pixel(r->target,x,r->y,color,coverage);'''
)

rep(
    '''    uint32_t rgba=((uint32_t)p[0]<<24)|((uint32_t)p[1]<<16)|((uint32_t)p[2]<<8)|(q ? q[0] : 255);
    do {
      unsigned coverage=r->coverage ? r->coverage[x] : 255;
      exr_pixel(r->target,x,r->y,rgba,coverage);
      x++;tap+=2;
    } while(x<r->x1 && tap[1].second>=0 && tap[1].second<next);''',
    '''    uint32_t rgba=((uint32_t)p[0]<<24)|((uint32_t)p[1]<<16)|((uint32_t)p[2]<<8)|(q ? q[0] : 255);
    unsigned a=rgba&255;
    pred_cnt[a==255 ? 17 : 18]++;
    int run_has_prev=0, run_idx=0;
    uint32_t run_prev_dst=0;
    do {
      unsigned coverage=r->coverage ? r->coverage[x] : 255;
      const unsigned char *dp=r->target->pixels+(size_t)r->y*r->target->stride+(size_t)x*4;
      uint32_t dst; memcpy(&dst,dp,4);
      int in_full=(x>=r->full_x0 && x<r->full_x1);
      pred_cnt[8]++;
      if(coverage<255) { pred_cnt[16]++; run_has_prev=0; }
      else if(a==255) {
        pred_cnt[9]++; if(in_full) pred_cnt[10]++;
      } else if(a>0) {
        pred_cnt[11]++;
        if(in_full) {
          pred_cnt[12]++;
          if(run_idx==0 && r->s4_has_prev && rgba==r->s4_prev_rgba && dst==r->s4_prev_dst) pred_cnt[15]++;
          if(run_has_prev && dst==run_prev_dst) { pred_cnt[13]++; }
          else { pred_cnt[14]++; run_prev_dst=dst; run_has_prev=1; }
          r->s4_prev_rgba=rgba; r->s4_prev_dst=dst; r->s4_has_prev=1;
        } else run_has_prev=0;
      }
      run_idx++;
      exr_pixel(r->target,x,r->y,rgba,coverage);
      x++;tap+=2;
    } while(x<r->x1 && tap[1].second>=0 && tap[1].second<next);'''
)

rep(
    '    r.alpha=alpha;r.y=y;r.x0=x0;r.x1=x1;r.luminosity=mask_mode==1;',
    '''    r.alpha=alpha;r.y=y;r.x0=x0;r.x1=x1;r.luminosity=mask_mode==1;
    pred_clip_full_span(r.coverage,x0,x1,&r.full_x0,&r.full_x1);
    pred_cnt[20]++; pred_cnt[23]+=(unsigned long long)(x1-x0);
    if(r.full_x1>r.full_x0) { pred_cnt[21]++; pred_cnt[22]+=(unsigned long long)(r.full_x1-r.full_x0); }'''
)

out.write_text(a)
