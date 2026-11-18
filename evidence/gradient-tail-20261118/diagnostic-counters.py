import sys
p='src/canvas.c'; s=open(p,encoding='utf-8').read()
def rep(a,b,count=1):
    global s
    assert s.count(a)>=count, a
    s=s.replace(a,b) if count==-1 else s.replace(a,b,count)
rep('exr_status exr_canvas_paint(exr_canvas *c,const exr_paint_source *input,const double transform[6],double alpha,exr_error *e) {',
'''#include <windows.h>
static unsigned long long dg_run,dg_single,dg_cached,dg_sampled,dg_generic,dg_rows,dg_aligned_rows,dg_fg,dg_fm,dg_obj;
static double dg_clock(void){LARGE_INTEGER t,f;QueryPerformanceCounter(&t);QueryPerformanceFrequency(&f);return (double)t.QuadPart*1000/(double)f.QuadPart;}
static exr_status canvas_paint_inner(exr_canvas *c,const exr_paint_source *input,const double transform[6],double alpha,exr_error *e);
exr_status exr_canvas_paint(exr_canvas *c,const exr_paint_source *input,const double transform[6],double alpha,exr_error *e) {
  dg_run=dg_single=dg_cached=dg_sampled=dg_generic=dg_rows=dg_aligned_rows=dg_fg=dg_fm=dg_obj=0;
  double t0=dg_clock();exr_status st=canvas_paint_inner(c,input,transform,alpha,e);double t1=dg_clock();
  const exr_shading_paint_source *a=input->context;exr_composite_state *ms=masked_state(c);
  fprintf(stderr,"PAINT ms=%.4f %ux%u clip=%d alpha=%g blend=%d state=%d pix=%d smask=%d knock=%d shape=%d gray=%d cmyk=%d type=%u ux=%g uy=%g rows=%llu alignedrows=%llu fgrows=%llu fmrows=%llu run=%llu single=%llu cached=%llu sampled=%llu generic=%llu obj=%lluBSLASHN",
    t1-t0,c->bitmap.width,c->bitmap.height,c->clip!=NULL,alpha,(int)c->blend,ms!=NULL,ms&&ms->pixels!=NULL,ms&&ms->soft_mask!=NULL,ms?(int)ms->knockout:0,ms&&ms->shape!=NULL,ms?(int)ms->gray:0,c->cmyk_groups,
    a&&a->magic==EXR_SHADING_SOURCE_MAGIC?a->type:99u,a?a->axial_ux:0,a?a->axial_uy:0,dg_rows,dg_aligned_rows,dg_fg,dg_fm,dg_run,dg_single,dg_cached,dg_sampled,dg_generic,dg_obj);
  return st;
}
static exr_status canvas_paint_inner(exr_canvas *c,const exr_paint_source *input,const double transform[6],double alpha,exr_error *e) {''')
rep('''          c->blend==EXR_BLEND_NORMAL && c->bitmap.channels==4 && (size_t)y<state->soft_mask_height;
''','''          c->blend==EXR_BLEND_NORMAL && c->bitmap.channels==4 && (size_t)y<state->soft_mask_height;
        dg_rows++;dg_aligned_rows+=aligned;dg_fg+=fast_group;dg_fm+=fast_mask;
''')
rep('''            *axial->work=budget;
''','''            *axial->work=budget;dg_run+=end-x;
''')
rep('''              if(y>=state->bottom) state->bottom=y+1;
              continue;
            }''','''              if(y>=state->bottom) state->bottom=y+1;
              dg_single++;continue;
            }''')
rep('''              if(m) exr_pixel(&c->bitmap,(int)x,(int)y,(in_color&0xffffff00u)|m,255);
              continue;''','''              if(m) exr_pixel(&c->bitmap,(int)x,(int)y,(in_color&0xffffff00u)|m,255);
              dg_single++;continue;''')
rep('''            row_alpha=in_alpha;row_shape=in_shape;pixel_color=in_color;
''','''            row_alpha=in_alpha;row_shape=in_shape;pixel_color=in_color;dg_cached++;
''')
rep('''            double sum_alpha=0,sum_shape=0;
            for(unsigned sy=0;sy<2;sy++)''','''            double sum_alpha=0,sum_shape=0;dg_sampled++;
            for(unsigned sy=0;sy<2;sy++)''')
rep('''          exr_pixel_alpha_shape(state,x,y,row_alpha,row_shape,alpha,coverage,&object_alpha,&object_shape);
''','''          dg_obj++;exr_pixel_alpha_shape(state,x,y,row_alpha,row_shape,alpha,coverage,&object_alpha,&object_shape);
''')
rep('''      double colors[4]={0},sum_alpha=0,sum_shape=0,object_alpha,object_shape;
      if(!coverage) continue;
''','''      double colors[4]={0},sum_alpha=0,sum_shape=0,object_alpha,object_shape;
      if(!coverage) continue;
      dg_generic++;
''')
s=s.replace('BSLASHN',chr(92)+'n')
open(p,'w',encoding='utf-8',newline='').write(s)
