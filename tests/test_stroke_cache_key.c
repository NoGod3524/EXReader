/* SPDX-License-Identifier: MIT */
/* Stroke/path coverage cache regression (merge precondition for the vector path cache).
   Every scenario runs in lockstep on two canvases: "warm" has the cache enabled and
   "cold" disables it (a never-cancelling control callback makes build_path_key refuse).
   After each draw both canvases must return the same status and identical RGBA; draws
   that are meant to probe the cache also assert that the warm canvas really hit or missed,
   so a scenario cannot pass vacuously. A hit must never skip a validation that the
   uncached draw would perform, and must never return coverage for a different key. */
#include "exreader.h"
#include "../src/canvas_internal.h"
#include <math.h>
#include <setjmp.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

enum { W=160,H=120 };
static jmp_buf fail_jump; static const char *current; static unsigned steps,failures;
#define FAIL(...) do { fprintf(stderr,"FAIL %s: ",current); fprintf(stderr,__VA_ARGS__); fputc('\n',stderr); longjmp(fail_jump,1); } while(0)
#define REQUIRE(x) do { if(!(x)) FAIL("line %d: %s",__LINE__,#x); } while(0)

typedef enum { ANY,HIT,MISS } expect;
typedef struct { exr_canvas *warm,*cold; unsigned draws; } pair;
static int never_cancel(void *context) { (void)context; return 0; }
static exr_canvas *make(int cached) {
  exr_canvas_config config={0}; exr_canvas *c=NULL; exr_error e={0};
  config.width=W; config.height=H; config.background=0xf0e8d8ff;
  if(!cached) config.control.cancelled=never_cancel;
  if(exr_canvas_create(&config,&c,&e)!=EXR_OK || !c) FAIL("canvas create: %s",e.message);
  return c;
}
static pair open_pair(void) { pair p; p.warm=make(1); p.cold=make(0); p.draws=0; return p; }
static void close_pair(pair *p) { exr_canvas_free(p->warm); exr_canvas_free(p->cold); p->warm=p->cold=NULL; }
/* Deterministic opaque backdrop written straight into both bitmaps. */
static void backdrop(pair *p) {
  exr_canvas *both[2]={p->warm,p->cold};
  for(unsigned k=0;k<2;k++) for(unsigned y=0;y<H;y++) for(unsigned x=0;x<W;x++) {
    unsigned char *px=both[k]->bitmap.pixels+(size_t)y*both[k]->bitmap.stride+4*x;
    px[0]=(unsigned char)(150+x%61); px[1]=(unsigned char)(120+y%47); px[2]=(unsigned char)(90+(x+2*y)%53); px[3]=255;
  }
}
static void compare_pixels(const pair *p,const char *what) {
  const exr_bitmap *a=&p->warm->bitmap,*b=&p->cold->bitmap; size_t differ=0; unsigned fx=0,fy=0;
  for(unsigned y=0;y<H;y++) for(unsigned x=0;x<W;x++)
    if(memcmp(a->pixels+(size_t)y*a->stride+4*x,b->pixels+(size_t)y*b->stride+4*x,4)) { if(!differ++) { fx=x; fy=y; } }
  if(differ) {
    const unsigned char *pa=a->pixels+(size_t)fy*a->stride+4*fx,*pb=b->pixels+(size_t)fy*b->stride+4*fx;
    FAIL("%s: cached and uncached RGBA differ in %zu px; first (%u,%u) cached=%u,%u,%u,%u uncached=%u,%u,%u,%u",
         what,differ,fx,fy,pa[0],pa[1],pa[2],pa[3],pb[0],pb[1],pb[2],pb[3]);
  }
}
static void snapshot(const pair *p,unsigned char *out) {
  for(unsigned y=0;y<H;y++) memcpy(out+(size_t)y*W*4,p->cold->bitmap.pixels+(size_t)y*p->cold->bitmap.stride,(size_t)W*4);
}
static size_t differs_from(const pair *p,const unsigned char *ref) {
  size_t n=0;
  for(unsigned y=0;y<H;y++) for(unsigned x=0;x<W;x++)
    if(memcmp(ref+((size_t)y*W+x)*4,p->cold->bitmap.pixels+(size_t)y*p->cold->bitmap.stride+4*x,4)) n++;
  return n;
}
/* One draw on both canvases. want<0 accepts any status as long as both agree. */
static exr_status step(pair *p,const char *what,const exr_path_segment *seg,size_t count,const double *matrix,
                       const exr_draw_style *style,const double *cmyk,int want,expect hit) {
  exr_error ew={0},ec={0}; exr_status sw,sc; unsigned tick=p->warm->path_cache_tick; int was_hit;
  exr_path_cache_entry *slots[EXR_PATH_CACHE_SLOTS];
  memcpy(slots,p->warm->path_cache,sizeof(slots)); steps++; p->draws++;
  sw=cmyk ? exr_canvas_path_cmyk(p->warm,seg,count,matrix,style,cmyk,cmyk+4,&ew) : exr_canvas_path(p->warm,seg,count,matrix,style,&ew);
  sc=cmyk ? exr_canvas_path_cmyk(p->cold,seg,count,matrix,style,cmyk,cmyk+4,&ec) : exr_canvas_path(p->cold,seg,count,matrix,style,&ec);
  /* The live tick advances on an insert or an accepted hit; an insert also replaces a slot pointer. */
  was_hit=p->warm->path_cache_tick==tick+1 && !memcmp(slots,p->warm->path_cache,sizeof(slots));
  if(p->cold->path_cache_tick || p->cold->path_cache_bytes) FAIL("%s: uncached control canvas populated its cache",what);
  if(sw!=sc) FAIL("%s: cached draw returned %d \"%s\" (cache %s) but uncached draw returned %d \"%s\"",
                  what,sw,ew.message,was_hit ? "HIT" : "miss",sc,ec.message);
  if(want>=0 && sc!=(exr_status)want) FAIL("%s: precondition: uncached draw returned %d \"%s\", expected %d",what,sc,ec.message,want);
  if(hit==HIT && !was_hit) FAIL("%s: expected a cache hit (tick %u->%u)",what,tick,p->warm->path_cache_tick);
  if(hit==MISS && was_hit) FAIL("%s: expected a cache miss but the cache hit",what);
  compare_pixels(p,what);
  return sc;
}
/* Shared geometry: an open curve with a corner, so caps, joins and curvature all matter. */
static const exr_path_segment curve[]={
  {EXR_PATH_MOVE,{{22,34}}},{EXR_PATH_CUBIC,{{52,6},{78,96},{112,40}}},{EXR_PATH_LINE,{{136,88}}}
};
static const exr_path_segment closed[]={
  {EXR_PATH_MOVE,{{30,24}}},{EXR_PATH_CUBIC,{{70,4},{110,60},{128,30}}},{EXR_PATH_LINE,{{120,96}}},
  {EXR_PATH_LINE,{{36,90}}},{EXR_PATH_CLOSE,{{0,0}}}
};
#define N(a) (sizeof(a)/sizeof((a)[0]))
static const double ctm[6]={1,.0625,-.125,1,3.25,4.5};
static exr_draw_style stroke_style(void) {
  exr_draw_style s=exr_draw_style_defaults();
  s.flags=EXR_DRAW_STROKE; s.stroke=0x1f4fa8ff; s.line.width=6; s.line.join=EXR_JOIN_ROUND; s.line.cap=EXR_CAP_BUTT;
  return s;
}
static exr_draw_style compound_style(void) {
  exr_draw_style s=stroke_style(); s.flags=EXR_DRAW_FILL|EXR_DRAW_STROKE; s.fill=0xd0603aff; s.line.width=5; return s;
}
static void rect(exr_path_segment r[5],double x,double y,double w,double h) {
  memset(r,0,5*sizeof(*r)); r[0].verb=EXR_PATH_MOVE; r[0].points[0]=(exr_path_point){x,y};
  r[1].verb=EXR_PATH_LINE; r[1].points[0]=(exr_path_point){x+w,y}; r[2].verb=EXR_PATH_LINE; r[2].points[0]=(exr_path_point){x+w,y+h};
  r[3].verb=EXR_PATH_LINE; r[3].points[0]=(exr_path_point){x,y+h}; r[4].verb=EXR_PATH_CLOSE;
}
static void clip_both(pair *p,double x,double y,double w,double h) {
  exr_path_segment r[5]; exr_error e={0}; rect(r,x,y,w,h);
  if(exr_canvas_clip(p->warm,r,5,NULL,EXR_FILL_NONZERO,&e)!=EXR_OK || exr_canvas_clip(p->cold,r,5,NULL,EXR_FILL_NONZERO,&e)!=EXR_OK) FAIL("clip: %s",e.message);
}
static void save_both(pair *p) { exr_error e={0}; if(exr_canvas_save(p->warm,&e)!=EXR_OK || exr_canvas_save(p->cold,&e)!=EXR_OK) FAIL("save: %s",e.message); }
static void restore_both(pair *p) { exr_error e={0}; if(exr_canvas_restore(p->warm,&e)!=EXR_OK || exr_canvas_restore(p->cold,&e)!=EXR_OK) FAIL("restore: %s",e.message); }
static void blend_both(pair *p,exr_blend_mode m) { exr_error e={0}; if(exr_canvas_blend(p->warm,m,&e)!=EXR_OK || exr_canvas_blend(p->cold,m,&e)!=EXR_OK) FAIL("blend: %s",e.message); }
/* First sight is only admitted, the second inserts, the third must hit. */
static void prime(pair *p,const exr_path_segment *seg,size_t count,const double *matrix,const exr_draw_style *s) {
  step(p,"prime: first sight",seg,count,matrix,s,NULL,EXR_OK,MISS);
  step(p,"prime: insert",seg,count,matrix,s,NULL,EXR_OK,MISS);
  if(!p->warm->path_cache_bytes) FAIL("prime: the second identical draw did not insert a cache entry");
  step(p,"prime: replay",seg,count,matrix,s,NULL,EXR_OK,HIT);
}

/* ---- Case 1: same stroke matrix, different clip. Clip is consumed on replay, not keyed. */
static void test_stroke_cache_key_clip(void) {
  pair p=open_pair(); exr_draw_style s=stroke_style(),c=compound_style(); unsigned char base[W*H*4];
  const double boxes[][4]={{0,0,80,120},{60,20,60,70},{0,0,W,40},{45.5,30.25,50.5,41.75}};
  prime(&p,curve,N(curve),ctm,&s); prime(&p,closed,N(closed),ctm,&c);
  backdrop(&p); step(&p,"unclipped stroke",curve,N(curve),ctm,&s,NULL,EXR_OK,HIT); snapshot(&p,base);
  for(size_t i=0;i<N(boxes);i++) {
    backdrop(&p); save_both(&p); clip_both(&p,boxes[i][0],boxes[i][1],boxes[i][2],boxes[i][3]);
    step(&p,"clipped stroke replay",curve,N(curve),ctm,&s,NULL,EXR_OK,HIT);
    if(!differs_from(&p,base)) FAIL("clip %zu did not change the stroke, so the scenario proves nothing",i);
    step(&p,"clipped compound replay",closed,N(closed),ctm,&c,NULL,EXR_OK,HIT);
    restore_both(&p);
  }
  close_pair(&p);
}
/* ---- Case 2: same stroke matrix, different alpha (stroke colour alpha byte). */
static void test_stroke_cache_key_alpha(void) {
  pair p=open_pair(); exr_draw_style s=stroke_style(),c=compound_style(); unsigned char base[W*H*4];
  const unsigned alphas[]={0xff,0x80,0x3c,0x01,0xfe};
  prime(&p,curve,N(curve),ctm,&s); prime(&p,closed,N(closed),ctm,&c);
  backdrop(&p); step(&p,"opaque stroke",curve,N(curve),ctm,&s,NULL,EXR_OK,HIT); snapshot(&p,base);
  for(size_t i=1;i<N(alphas);i++) {
    exr_draw_style a=s,b=c; a.stroke=(s.stroke&~255u)|alphas[i]; b.stroke=(c.stroke&~255u)|alphas[i]; b.fill=(c.fill&~255u)|alphas[N(alphas)-i];
    backdrop(&p); step(&p,"translucent stroke replay",curve,N(curve),ctm,&a,NULL,EXR_OK,HIT);
    if(!differs_from(&p,base)) FAIL("alpha %02x did not change the stroke",alphas[i]);
    step(&p,"translucent compound replay",closed,N(closed),ctm,&b,NULL,EXR_OK,HIT);
  }
  close_pair(&p);
}
/* ---- Case 3: same stroke matrix, different line width. Width is a key field. */
static void test_stroke_cache_key_width(void) {
  pair p=open_pair(); exr_draw_style s=stroke_style(),c=compound_style();
  const double widths[]={9,2,6.000001,0.5};
  prime(&p,curve,N(curve),ctm,&s); prime(&p,closed,N(closed),ctm,&c);
  for(size_t i=0;i<N(widths);i++) {
    exr_draw_style a=s,b=c; a.line.width=widths[i]; b.line.width=widths[i];
    backdrop(&p); step(&p,"stroke with another width",curve,N(curve),ctm,&a,NULL,EXR_OK,MISS);
    backdrop(&p); step(&p,"compound with another width",closed,N(closed),ctm,&b,NULL,EXR_OK,MISS);
  }
  /* Width changes a second time through the cache: entries for both widths now live. */
  for(size_t i=0;i<2;i++) {
    exr_draw_style a=s; a.line.width=widths[i];
    backdrop(&p); step(&p,"stroke width re-admit",curve,N(curve),ctm,&a,NULL,EXR_OK,ANY);
    backdrop(&p); step(&p,"stroke width replay",curve,N(curve),ctm,&a,NULL,EXR_OK,HIT);
  }
  backdrop(&p); step(&p,"original width hits its own entry",curve,N(curve),ctm,&s,NULL,EXR_OK,HIT);
  /* Cap, join, miter and dash are keyed the same way. */
  { exr_draw_style a=s; a.line.cap=EXR_CAP_ROUND; backdrop(&p); step(&p,"cap change",curve,N(curve),ctm,&a,NULL,EXR_OK,MISS); }
  { exr_draw_style a=s; a.line.join=EXR_JOIN_MITER; backdrop(&p); step(&p,"join change",curve,N(curve),ctm,&a,NULL,EXR_OK,MISS); }
  { exr_draw_style a=s; const double d[2]={7,3}; a.dashes=d; a.dash_count=2;
    backdrop(&p); step(&p,"dash change",curve,N(curve),ctm,&a,NULL,EXR_OK,MISS);
    step(&p,"dash insert",curve,N(curve),ctm,&a,NULL,EXR_OK,MISS);
    a.dash_phase=4; backdrop(&p); step(&p,"dash phase change",curve,N(curve),ctm,&a,NULL,EXR_OK,MISS); }
  close_pair(&p);
}
/* ---- Case 4: same stroke matrix, different blend mode. Standalone non-Normal bypasses the
   cache; compound coverage is replayed through the current blend mode. */
static void test_stroke_cache_key_blend(void) {
  pair p=open_pair(); exr_draw_style s=stroke_style(),c=compound_style(); unsigned char base[W*H*4];
  const exr_blend_mode modes[]={EXR_BLEND_MULTIPLY,EXR_BLEND_SCREEN,EXR_BLEND_DIFFERENCE,EXR_BLEND_COLOR_BURN,EXR_BLEND_LUMINOSITY,EXR_BLEND_NORMAL};
  c.fill=(c.fill&~255u)|0xa0; c.stroke=(c.stroke&~255u)|0xc8;
  prime(&p,curve,N(curve),ctm,&s); prime(&p,closed,N(closed),ctm,&c);
  backdrop(&p); step(&p,"normal compound",closed,N(closed),ctm,&c,NULL,EXR_OK,HIT); snapshot(&p,base);
  for(size_t i=0;i<N(modes);i++) {
    blend_both(&p,modes[i]);
    backdrop(&p); step(&p,"standalone stroke under blend",curve,N(curve),ctm,&s,NULL,EXR_OK,modes[i]==EXR_BLEND_NORMAL ? HIT : MISS);
    backdrop(&p); step(&p,"compound replay under blend",closed,N(closed),ctm,&c,NULL,EXR_OK,HIT);
    if(modes[i]!=EXR_BLEND_NORMAL && !differs_from(&p,base)) FAIL("blend %d did not change the compound",(int)modes[i]);
  }
  close_pair(&p);
}
/* ---- Case 5: stroke matrices that differ by one component (1e-6 and a visible change). */
static void test_stroke_cache_key_matrix_epsilon(void) {
  pair p=open_pair(); exr_draw_style s=stroke_style(),c=compound_style();
  const double sm[6]={1.5,0,0,1.5,0,0};
  s.stroke_matrix=sm; c.stroke_matrix=sm;
  prime(&p,curve,N(curve),ctm,&s); prime(&p,closed,N(closed),ctm,&c);
  for(unsigned k=0;k<4;k++) {
    double near[6],far[6]; exr_draw_style a=s,b=c;
    memcpy(near,sm,sizeof(near)); memcpy(far,sm,sizeof(far)); near[k]+=1e-6; far[k]+=k==0||k==3 ? 1.25 : .75;
    a.stroke_matrix=near; b.stroke_matrix=near;
    backdrop(&p); step(&p,"stroke matrix +1e-6",curve,N(curve),ctm,&a,NULL,EXR_OK,MISS);
    backdrop(&p); step(&p,"compound matrix +1e-6",closed,N(closed),ctm,&b,NULL,EXR_OK,MISS);
    a.stroke_matrix=far; b.stroke_matrix=far;
    backdrop(&p); step(&p,"stroke matrix visibly different",curve,N(curve),ctm,&a,NULL,EXR_OK,MISS);
    backdrop(&p); step(&p,"compound matrix visibly different",closed,N(closed),ctm,&b,NULL,EXR_OK,MISS);
  }
  /* The path matrix linear part reaches the key through the transformed points. */
  { double m[6]; memcpy(m,ctm,sizeof(m)); m[1]+=1e-6; backdrop(&p); step(&p,"path matrix +1e-6",curve,N(curve),m,&s,NULL,EXR_OK,MISS); }
  backdrop(&p); step(&p,"original matrix still hits",curve,N(curve),ctm,&s,NULL,EXR_OK,HIT);
  close_pair(&p);
}
/* ---- Case 6: draw, change clip, draw again with the same matrix (and translate by whole pixels). */
static void test_stroke_cache_key_clip_change(void) {
  pair p=open_pair(); exr_draw_style s=stroke_style(),c=compound_style();
  double moved[6]; memcpy(moved,ctm,sizeof(moved)); moved[4]+=7; moved[5]-=3;
  backdrop(&p);
  step(&p,"first stroke",curve,N(curve),ctm,&s,NULL,EXR_OK,MISS);
  save_both(&p); clip_both(&p,10,10,70,90);
  step(&p,"same matrix after clip",curve,N(curve),ctm,&s,NULL,EXR_OK,MISS);
  clip_both(&p,30,0,100,60);
  step(&p,"same matrix after nested clip",curve,N(curve),ctm,&s,NULL,EXR_OK,HIT);
  restore_both(&p);
  step(&p,"same matrix after restore",curve,N(curve),ctm,&s,NULL,EXR_OK,HIT);
  save_both(&p); clip_both(&p,0,50,W,70);
  step(&p,"whole-pixel translated replay under clip",curve,N(curve),moved,&s,NULL,EXR_OK,HIT);
  step(&p,"compound first",closed,N(closed),ctm,&c,NULL,EXR_OK,MISS);
  restore_both(&p);
  step(&p,"compound after clip restore",closed,N(closed),ctm,&c,NULL,EXR_OK,MISS);
  save_both(&p); clip_both(&p,50,0,60,H);
  step(&p,"compound replay under new clip",closed,N(closed),ctm,&c,NULL,EXR_OK,HIT);
  restore_both(&p);
  close_pair(&p);
}

/* ---- Matrix validation. Each poisoned draw ends its pair, so each variant gets a fresh pair. */
typedef void (*variant_fn)(exr_draw_style *s,double sm[6],double tm[6],exr_path_segment *seg,size_t count);
static void validation(const char *label,const exr_draw_style *base,const double base_sm[6],const double base_tm[6],
                       const exr_path_segment *seg,size_t count,variant_fn change,int want) {
  pair p=open_pair(); exr_draw_style s=*base,v=*base; double sm[6],tm[6],vsm[6],vtm[6]; exr_path_segment vseg[8];
  char what[160];
  memcpy(sm,base_sm,sizeof(sm)); memcpy(tm,base_tm,sizeof(tm)); memcpy(vsm,sm,sizeof(vsm)); memcpy(vtm,tm,sizeof(vtm));
  memcpy(vseg,seg,count*sizeof(*seg)); s.stroke_matrix=sm; v.stroke_matrix=vsm;
  prime(&p,seg,count,tm,&s);
  change(&v,vsm,vtm,vseg,count);
  snprintf(what,sizeof(what),"%s (%s)",label,base->flags==EXR_DRAW_STROKE ? "stroke" : "fill+stroke");
  step(&p,what,vseg,count,vtm,&v,NULL,want,ANY);
  close_pair(&p);
}
static void v_tx_nan(exr_draw_style *s,double sm[6],double tm[6],exr_path_segment *g,size_t n) { (void)s;(void)tm;(void)g;(void)n; sm[4]=NAN; }
static void v_ty_inf(exr_draw_style *s,double sm[6],double tm[6],exr_path_segment *g,size_t n) { (void)s;(void)tm;(void)g;(void)n; sm[5]=-INFINITY; }
static void v_tx_big(exr_draw_style *s,double sm[6],double tm[6],exr_path_segment *g,size_t n) { (void)s;(void)tm;(void)g;(void)n; sm[4]=2e7; }
/* Every term is finite and <=1e7, but the inverse translation is -1.2e7. */
static void v_inv_big(exr_draw_style *s,double sm[6],double tm[6],exr_path_segment *g,size_t n) { (void)s;(void)tm;(void)g;(void)n; sm[4]=6e6; }
static void test_stroke_cache_matrix_translation(void) {
  const double sm[6]={.5,0,0,.5,0,0},tm[6]={1,0,0,1,0,0}; exr_draw_style s=stroke_style(),c=compound_style();
  const variant_fn fns[]={v_tx_nan,v_ty_inf,v_tx_big,v_inv_big};
  const char *names[]={"stroke matrix e=NaN","stroke matrix f=-Inf","stroke matrix e=2e7","stroke matrix inverse e=-1.2e7"};
  for(size_t i=0;i<N(fns);i++) {
    validation(names[i],&s,sm,tm,curve,N(curve),fns[i],EXR_ARGUMENT);
    validation(names[i],&c,sm,tm,closed,N(closed),fns[i],EXR_ARGUMENT);
  }
}
/* The linear terms are compared with a 1e-12 tolerance; 5e-13 must not carry a matrix whose
   inverse is out of range (1/a > 1e7) onto an entry admitted for a matrix whose inverse is in range. */
static const exr_path_segment speck[]={{EXR_PATH_MOVE,{{.25,.6}}},{EXR_PATH_LINE,{{.95,.6}}}};
static void v_cond(exr_draw_style *s,double sm[6],double tm[6],exr_path_segment *g,size_t n) {
  (void)s;(void)tm;(void)g;(void)n; sm[0]-=5e-13; sm[3]-=5e-13;
}
static void test_stroke_cache_matrix_conditioning(void) {
  const double a=1.0000000000001e-7,sm[6]={a,0,0,a,0,0},tm[6]={1,0,0,1,0,0};
  exr_draw_style s=stroke_style(); s.line.width=1e7;
  validation("stroke matrix inverse 1/(a-5e-13) > 1e7",&s,sm,tm,speck,N(speck),v_cond,EXR_ARGUMENT);
}
/* The stroke-space flatten matrix is inverse(stroke) x path; its range check depends on the
   path matrix linear part, which only reaches the key through the transformed points. */
#define BIG 2097152.0
static void v_product(exr_draw_style *s,double sm[6],double tm[6],exr_path_segment *g,size_t n) {
  (void)s;(void)sm; tm[0]=tm[3]=BIG;
  for(size_t i=0;i<n;i++) for(unsigned k=0;k<3;k++) { g[i].points[k].x/=BIG; g[i].points[k].y/=BIG; }
}
static void test_stroke_cache_matrix_product(void) {
  const double sm[6]={.125,0,0,.125,0,0},tm[6]={1,0,0,1,0,0};
  exr_draw_style s=stroke_style(),c=compound_style(); s.line.width=48; c.line.width=40;
  static const exr_path_segment line[]={{EXR_PATH_MOVE,{{24,32}}},{EXR_PATH_LINE,{{120,32}}},{EXR_PATH_LINE,{{96,88}}}};
  static const exr_path_segment box[]={{EXR_PATH_MOVE,{{32,24}}},{EXR_PATH_LINE,{{128,24}}},{EXR_PATH_LINE,{{128,96}}},
                                       {EXR_PATH_LINE,{{32,96}}},{EXR_PATH_LINE,{{40,60}}},{EXR_PATH_CLOSE,{{0,0}}}};
  validation("inverse(stroke) x path matrix > 1e7",&s,sm,tm,line,N(line),v_product,EXR_ARGUMENT);
  validation("inverse(stroke) x path matrix > 1e7",&c,sm,tm,box,N(box),v_product,EXR_ARGUMENT);
}
/* Dash lengths are compared with a 1e-12 tolerance; an all-zero pattern is invalid. */
static const exr_path_segment nub[]={{EXR_PATH_MOVE,{{40,40}}},{EXR_PATH_LINE,{{40.0000000001,40}}}};
static const double tiny_dash[1]={1e-13},zero_dash[1]={0};
static void v_zero_dash(exr_draw_style *s,double sm[6],double tm[6],exr_path_segment *g,size_t n) { (void)sm;(void)tm;(void)g;(void)n; s->dashes=zero_dash; }
static void test_stroke_cache_dash_validation(void) {
  const double sm[6]={1,0,0,1,0,0},tm[6]={1,0,0,1,0,0}; exr_draw_style s=stroke_style();
  s.line.cap=EXR_CAP_ROUND; s.dashes=tiny_dash; s.dash_count=1;
  validation("all-zero dash pattern",&s,sm,tm,nub,N(nub),v_zero_dash,EXR_ARGUMENT);
}
/* Width 0 is a one-device-pixel hairline; width 1e-13 is nearly invisible. Both lie within the
   1e-12 width tolerance, so neither may replay the other's coverage. */
static void test_stroke_cache_key_hairline(void) {
  static const exr_path_segment diag[]={{EXR_PATH_MOVE,{{12,14}}},{EXR_PATH_LINE,{{140,100}}}};
  for(unsigned order=0;order<2;order++) {
    pair p=open_pair(); exr_draw_style s=stroke_style(),t; s.line.width=order ? 0 : 1e-13; t=s; t.line.width=order ? 1e-13 : 0;
    prime(&p,diag,N(diag),NULL,&s);
    backdrop(&p); step(&p,order ? "width 1e-13 after cached hairline" : "hairline after cached width 1e-13",diag,N(diag),NULL,&t,NULL,EXR_OK,ANY);
    close_pair(&p);
  }
}

/* ---- Key fields the six scenarios above do not vary. Each case changes exactly one keyed input
   with everything else fixed, so removing that field from the key turns an expected MISS into a
   stale HIT (and, where the field changes coverage, into different pixels). The "sub-quantum"
   variants differ by 1e-7, below the hash's 1e-6 quantisation, so they also fail when only the
   exact field comparison is removed and the hash alone is left to tell entries apart. */
static const exr_path_segment star[]={
  {EXR_PATH_MOVE,{{80,8}}},{EXR_PATH_LINE,{{110.6,102.1}}},{EXR_PATH_LINE,{{30.5,44.1}}},
  {EXR_PATH_LINE,{{129.5,44.1}}},{EXR_PATH_LINE,{{49.4,102.1}}},{EXR_PATH_CLOSE,{{0,0}}}
};
static void test_stroke_cache_key_miter(void) {
  /* The corner's miter ratio is about 2.3: drawn as a miter at limit 10, beveled at limit 1.5. */
  static const exr_path_segment vee[]={{EXR_PATH_MOVE,{{20,100}}},{EXR_PATH_LINE,{{80,20}}},{EXR_PATH_LINE,{{100,100}}}};
  pair p=open_pair(); exr_draw_style s=stroke_style(),t; unsigned char base[W*H*4];
  s.line.join=EXR_JOIN_MITER; s.line.width=8; s.line.miter_limit=10;
  prime(&p,vee,N(vee),NULL,&s);
  backdrop(&p); step(&p,"miter 10 replay",vee,N(vee),NULL,&s,NULL,EXR_OK,HIT); snapshot(&p,base);
  t=s; t.line.miter_limit=1.5;
  backdrop(&p); step(&p,"miter limit 1.5 (bevels the corner)",vee,N(vee),NULL,&t,NULL,EXR_OK,MISS);
  if(!differs_from(&p,base)) FAIL("miter limit change did not change the stroke");
  t=s; t.line.miter_limit=10+1e-7;
  backdrop(&p); step(&p,"miter limit +1e-7 (sub-quantum)",vee,N(vee),NULL,&t,NULL,EXR_OK,MISS);
  close_pair(&p);
}
static void test_stroke_cache_key_fill_rule(void) {
  pair p=open_pair(); exr_draw_style f=exr_draw_style_defaults(),c=compound_style(),t; unsigned char base[W*H*4];
  f.flags=EXR_DRAW_FILL; f.fill=0x2a7f3cff; f.rule=EXR_FILL_EVENODD; c.rule=EXR_FILL_EVENODD;
  prime(&p,star,N(star),NULL,&f); prime(&p,star,N(star),ctm,&c);
  backdrop(&p); step(&p,"even-odd fill replay",star,N(star),NULL,&f,NULL,EXR_OK,HIT); snapshot(&p,base);
  t=f; t.rule=EXR_FILL_NONZERO;
  backdrop(&p); step(&p,"nonzero fill of the same star",star,N(star),NULL,&t,NULL,EXR_OK,MISS);
  if(!differs_from(&p,base)) FAIL("fill rule change did not change the fill");
  t=c; t.rule=EXR_FILL_NONZERO;
  backdrop(&p); step(&p,"nonzero compound of the same star",star,N(star),ctm,&t,NULL,EXR_OK,MISS);
  close_pair(&p);
}
static void test_stroke_cache_key_verbs(void) {
  /* Same segment count, same point list, different verbs. */
  static const exr_path_segment qa[]={{EXR_PATH_MOVE,{{20,90}}},{EXR_PATH_QUAD,{{60,10},{100,90}}},{EXR_PATH_LINE,{{140,30}}}};
  static const exr_path_segment qb[]={{EXR_PATH_MOVE,{{20,90}}},{EXR_PATH_LINE,{{60,10}}},{EXR_PATH_QUAD,{{100,90},{140,30}}}};
  pair p=open_pair(); exr_draw_style s=stroke_style();
  prime(&p,qa,N(qa),NULL,&s);
  backdrop(&p); step(&p,"line+quad after cached quad+line",qb,N(qb),NULL,&s,NULL,EXR_OK,MISS);
  close_pair(&p);
}
static void test_stroke_cache_key_seg_count(void) {
  /* Same point count, same point list, same prefix verbs; differs only in trailing EXR_PATH_CLOSE (seg_count 3 vs 4). */
  static const exr_path_segment open_tri[]={{EXR_PATH_MOVE,{{24,24}}},{EXR_PATH_LINE,{{128,36}}},{EXR_PATH_LINE,{{64,104}}}};
  static const exr_path_segment closed_tri[]={{EXR_PATH_MOVE,{{24,24}}},{EXR_PATH_LINE,{{128,36}}},{EXR_PATH_LINE,{{64,104}}},{EXR_PATH_CLOSE,{{0,0}}}};
  pair p=open_pair(); exr_draw_style s=stroke_style(); unsigned char base[W*H*4];
  prime(&p,open_tri,N(open_tri),NULL,&s);
  backdrop(&p); step(&p,"open triangle replay",open_tri,N(open_tri),NULL,&s,NULL,EXR_OK,HIT); snapshot(&p,base);
  backdrop(&p); step(&p,"closed triangle after cached open triangle",closed_tri,N(closed_tri),NULL,&s,NULL,EXR_OK,MISS);
  if(!differs_from(&p,base)) FAIL("trailing CLOSE did not change the stroke");
  close_pair(&p);
}
static void test_stroke_cache_key_flags(void) {
  pair p=open_pair(); exr_draw_style s=stroke_style(),f=exr_draw_style_defaults(),c=compound_style();
  f.flags=EXR_DRAW_FILL; f.fill=s.stroke; f.rule=EXR_FILL_NONZERO; c.rule=EXR_FILL_NONZERO; c.fill=s.stroke;
  prime(&p,star,N(star),NULL,&f);
  backdrop(&p); step(&p,"stroke after cached fill",star,N(star),NULL,&s,NULL,EXR_OK,MISS);
  backdrop(&p); step(&p,"fill+stroke after cached fill",star,N(star),NULL,&c,NULL,EXR_OK,MISS);
  close_pair(&p);
}
static void test_stroke_cache_key_dash_pattern(void) {
  pair p=open_pair(); exr_draw_style s=stroke_style(),t; unsigned char base[W*H*4];
  static const double d73[2]={7,3},d37[2]={3,7},d73e[2]={7,3+1e-7},d733[3]={7,3,3};
  s.dashes=d73; s.dash_count=2;
  prime(&p,curve,N(curve),ctm,&s);
  backdrop(&p); step(&p,"dash 7 3 replay",curve,N(curve),ctm,&s,NULL,EXR_OK,HIT); snapshot(&p,base);
  t=s; t.dashes=d37;
  backdrop(&p); step(&p,"dash 3 7",curve,N(curve),ctm,&t,NULL,EXR_OK,MISS);
  if(!differs_from(&p,base)) FAIL("dash pattern change did not change the stroke");
  t=s; t.dashes=d733; t.dash_count=3;
  backdrop(&p); step(&p,"dash 7 3 3",curve,N(curve),ctm,&t,NULL,EXR_OK,MISS);
  t=s; t.dashes=d73e;
  backdrop(&p); step(&p,"dash 7 3+1e-7 (sub-quantum)",curve,N(curve),ctm,&t,NULL,EXR_OK,MISS);
  t=s; t.dash_phase=1e-7;
  backdrop(&p); step(&p,"dash phase 1e-7 (sub-quantum)",curve,N(curve),ctm,&t,NULL,EXR_OK,MISS);
  close_pair(&p);
}
static void test_stroke_cache_key_sub_quantum(void) {
  pair p=open_pair(); exr_draw_style s=stroke_style(),c=compound_style();
  const double sm[6]={1.5,0,0,1.5,0,0};
  s.stroke_matrix=sm; c.stroke_matrix=sm;
  prime(&p,curve,N(curve),ctm,&s); prime(&p,closed,N(closed),ctm,&c);
  for(unsigned k=0;k<4;k++) {
    double near[6]; exr_draw_style a=s,b=c;
    memcpy(near,sm,sizeof(near)); near[k]+=1e-7; a.stroke_matrix=near; b.stroke_matrix=near;
    backdrop(&p); step(&p,"stroke matrix term +1e-7",curve,N(curve),ctm,&a,NULL,EXR_OK,MISS);
    backdrop(&p); step(&p,"compound matrix term +1e-7",closed,N(closed),ctm,&b,NULL,EXR_OK,MISS);
    /* Sub-quantum variants share the original's hash, so they are admitted and inserted;
       replaying the originals keeps them most recently used in the 8-slot LRU. */
    step(&p,"original stroke still hits",curve,N(curve),ctm,&s,NULL,EXR_OK,HIT);
    step(&p,"original compound still hits",closed,N(closed),ctm,&c,NULL,EXR_OK,HIT);
  }
  { exr_draw_style a=s; a.line.width+=1e-7; backdrop(&p); step(&p,"width +1e-7",curve,N(curve),ctm,&a,NULL,EXR_OK,MISS); }
  step(&p,"original stroke still hits",curve,N(curve),ctm,&s,NULL,EXR_OK,HIT);
  { exr_path_segment g[N(curve)]; memcpy(g,curve,sizeof(g)); g[1].points[1].y+=1e-7;
    backdrop(&p); step(&p,"one control point +1e-7",g,N(g),ctm,&s,NULL,EXR_OK,MISS); }
  backdrop(&p); step(&p,"original still hits",curve,N(curve),ctm,&s,NULL,EXR_OK,HIT);
  close_pair(&p);
}

typedef struct { const char *name; void (*run)(void); } test_case;
#define T(f) {#f,f}
static const test_case cases[]={
  T(test_stroke_cache_key_clip),T(test_stroke_cache_key_alpha),T(test_stroke_cache_key_width),
  T(test_stroke_cache_key_blend),T(test_stroke_cache_key_matrix_epsilon),T(test_stroke_cache_key_clip_change),
  T(test_stroke_cache_matrix_translation),T(test_stroke_cache_matrix_conditioning),T(test_stroke_cache_matrix_product),
  T(test_stroke_cache_dash_validation),T(test_stroke_cache_key_hairline),
  T(test_stroke_cache_key_miter),T(test_stroke_cache_key_fill_rule),T(test_stroke_cache_key_verbs),
  T(test_stroke_cache_key_seg_count),T(test_stroke_cache_key_flags),T(test_stroke_cache_key_dash_pattern),
  T(test_stroke_cache_key_sub_quantum),
};
int main(int argc,char **argv) {
  for(size_t i=0;i<N(cases);i++) {
    if(argc>1) { int chosen=0; for(int a=1;a<argc;a++) if(!strcmp(argv[a],cases[i].name)) chosen=1; if(!chosen) continue; }
    current=cases[i].name; unsigned before=steps;
    if(!setjmp(fail_jump)) { cases[i].run(); printf("PASS %s (%u draws)\n",current,steps-before); }
    else failures++;
  }
  printf("%u failure(s), %u lockstep draws\n",failures,steps);
  return failures ? 1 : 0;
}
