# SPDX-License-Identifier: MIT
"""Write a counter-only copy of src/affine_image.c (no timers, output unchanged).

Counters, per render (img_count_reset / img_count_read):
  0  site 3 calls reaching exr_pixel (axis_store, sums[3]!=0)
  1  site 3 color alpha byte == 255
  2  site 3 coverage == 255
  3  site 3 P3: alpha byte == 255 and coverage == 255
  4  site 3 destination p[3] == 255 before the store
  5  site 3 target channels == 4
  6  site 3 sums[3]==0 early returns
  8  site 4 pixels (flat-run exr_pixel)
  9  site 4 P4: rgba alpha == 255 and coverage == 255
  10 site 4 runs
  11 site 4 runs with no clip row and rgba alpha == 255 (whole run is P4)
  12 site 4 pixels inside such runs
  13 axis rows with a clip row, 14 axis rows without
  15 axis_paint calls with flat=1, 16 with flat=0
  17 site 4 destination p[3] == 255 before the store
  18 site 4 target channels == 4
  19 site 3 pixels with coverage == 0 skipped before sampling (not a store)
  20 site 4 effective alpha 0 (exr_pixel returns), 21 site 3 effective alpha 0
  22 site 4 partial alpha with source rgb == destination rgb (identity blend)
  23 site 3 partial alpha with source rgb == destination rgb
  25 site 3/4 writes to a pixel an earlier image store already wrote (overdraw)
  26 earlier image stores later replaced by an alpha-255 store (dead work)
  27 site 3/4 writes to a target other than the first one seen this render
"""
import sys
from pathlib import Path
src, out = Path(sys.argv[1]), Path(sys.argv[2])
a = src.read_text()
def rep(old, new, count=1):
    global a
    assert a.count(old) == count, (old, a.count(old))
    a = a.replace(old, new)
prefix = '''
unsigned long long img_cnt[32];
static unsigned char *img_map; static const unsigned char *img_owner; static size_t img_map_size;
__declspec(dllexport) void img_count_reset(void) { for(unsigned i=0;i<32;i++) img_cnt[i]=0; img_owner=0; }
static void img_track(const exr_bitmap *t,int x,int y,int opaque) {
  size_t n=(size_t)t->width*t->height,i=(size_t)y*t->width+(size_t)x;
  if(!img_owner) { if(img_map_size<n) { free(img_map); img_map=calloc(n,1); img_map_size=img_map ? n : 0; } else memset(img_map,0,n); img_owner=t->pixels; }
  if(t->pixels!=img_owner || !img_map) { img_cnt[27]++; return; }
  img_cnt[25]+=img_map[i]>0;
  if(opaque) { img_cnt[26]+=img_map[i]; img_map[i]=1; } else if(img_map[i]<255) img_map[i]++;
}
__declspec(dllexport) void img_count_read(unsigned long long *o) { for(unsigned i=0;i<32;i++) o[i]=img_cnt[i]; }
'''
rep('''  if(!sums[3]) return;
  uint32_t color=image_byte(sums[3]*r->alpha/4);
  for(unsigned k=0;k<3;k++) color|=image_byte(sums[k]/sums[3])<<(24-8*k);
  exr_pixel(r->target,x,r->y,color,coverage);''',
'''  if(!sums[3]) { img_cnt[6]++; return; }
  uint32_t color=image_byte(sums[3]*r->alpha/4);
  for(unsigned k=0;k<3;k++) color|=image_byte(sums[k]/sums[3])<<(24-8*k);
  { const unsigned char *dp=r->target->pixels+(size_t)r->y*r->target->stride+(size_t)x*r->target->channels;
    img_cnt[0]++; img_cnt[1]+=(color&255)==255; img_cnt[2]+=coverage==255; img_cnt[3]+=(color&255)==255 && coverage==255;
    img_cnt[5]+=r->target->channels==4; img_cnt[4]+=r->target->channels==4 && dp[3]==255;
    { unsigned ea=(color&255)*coverage/255; img_cnt[21]+=!ea;
      img_track(r->target,x,r->y,ea==255);
      img_cnt[23]+=ea && ea<255 && dp[0]==(color>>24) && dp[1]==((color>>16)&255) && dp[2]==((color>>8)&255); } }
  exr_pixel(r->target,x,r->y,color,coverage);''')
rep('''    if(!coverage) continue;
    for(unsigned sy=0;sy<2;sy++) if(r->valid[sy]) {''', '''    if(!coverage) { img_cnt[19]++; continue; }
    for(unsigned sy=0;sy<2;sy++) if(r->valid[sy]) {''')
rep('''    uint32_t rgba=((uint32_t)p[0]<<24)|((uint32_t)p[1]<<16)|((uint32_t)p[2]<<8)|(q ? q[0] : 255);
    do {
      unsigned coverage=r->coverage ? r->coverage[x] : 255;
      exr_pixel(r->target,x,r->y,rgba,coverage);''',
'''    uint32_t rgba=((uint32_t)p[0]<<24)|((uint32_t)p[1]<<16)|((uint32_t)p[2]<<8)|(q ? q[0] : 255);
    img_cnt[10]++; img_cnt[11]+=!r->coverage && (rgba&255)==255;
    do {
      unsigned coverage=r->coverage ? r->coverage[x] : 255;
      { const unsigned char *dp=r->target->pixels+(size_t)r->y*r->target->stride+(size_t)x*r->target->channels;
        img_cnt[8]++; img_cnt[9]+=(rgba&255)==255 && coverage==255; img_cnt[12]+=!r->coverage && (rgba&255)==255;
        img_cnt[18]+=r->target->channels==4; img_cnt[17]+=r->target->channels==4 && dp[3]==255;
        { unsigned ea=(rgba&255)*coverage/255; img_cnt[20]+=!ea;
          img_track(r->target,x,r->y,ea==255);
          img_cnt[22]+=ea && ea<255 && dp[0]==(rgba>>24) && dp[1]==((rgba>>16)&255) && dp[2]==((rgba>>8)&255); } }
      exr_pixel(r->target,x,r->y,rgba,coverage);''')
rep('''    if(flat) axis_flat_row_paint(&r,ctap);''', '''    img_cnt[r.coverage ? 13 : 14]++;
    if(flat) axis_flat_row_paint(&r,ctap);''')
rep('''fegetround()==FE_TONEAREST;
  *result=EXR_OK;''', '''fegetround()==FE_TONEAREST;
  *result=EXR_OK; img_cnt[flat ? 15 : 16]++;''')
anchor = 'static int storage(const exr_bitmap *b) {'
assert a.count(anchor) == 1
out.write_text(a.replace(anchor, prefix + anchor))
