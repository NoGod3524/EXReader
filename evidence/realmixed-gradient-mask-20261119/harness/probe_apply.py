# SPDX-License-Identifier: MIT
"""Apply (or revert) the rdtsc stage probe for the p1-21 gradient + soft-mask split.

Each edit is an exact, single-occurrence string replacement, so a stale anchor
fails loudly instead of silently probing the wrong code. Revert restores the
five touched sources from git and removes the probe header.

Slots (cycles and counts in exr_probe_cycles / exr_probe_counts):
  0  mask_begin: exr_pdf_soft_mask_build call (inclusive)
  1  build_mask: dictionary parse before rasterising
  2  raster: canvas create (pooled take + background fill)
  3  raster: initial BBox clip
  4  raster: sink + begin_group (inclusive of 14-16)
  5  raster: paint content (FT init, walk, mask shading)
  6  raster: end_layer (group commit)
  7  raster: take bitmap + free canvas
  8  build_mask: transfer load + result buffer take
  9  build_mask: luminosity extraction loop
 10  build_mask: release RGBA bitmap
 11  mask_begin: install mask on the page canvas
 12  mask_end
 13  paint content: FT_Init_FreeType + FT_Done_FreeType inside a mask
 14  begin_group: working buffer takes (zero fill)
 15  begin_group: backdrop copy (exr_composite_initialize)
 16  begin_group: clip bounds scan
 17  clip_path inside a mask
 counts only: 20 extraction rows computed, 21 extraction rows reused,
              22 extraction pixels computed, 23 extraction pixels reused
 Per shading, base 32 (page) or 48 (inside a mask):
 +0 exr_pdf_shading_draw (inclusive)   +1 colour table build (512 samples)
 +2 emit (source_event, inclusive)     +3 canvas paint (inclusive)
 +4 fast span stores                   +5 row prologue (clip scan + charge)
 +6 source_event: mask_begin..mask_end excluded remainder is derived
 counts only: +8 rows, +9 span pixels, +10 span pixels with mask 0,
              +11 single-pixel fast stores, +12 generic sampled pixels
"""
import subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HEADER = ROOT/'src'/'probe_internal.h'
FILES = ['src/pdf_paint.c', 'src/pdf_softmask.c', 'src/pdf_raster.c', 'src/pdf_shading.c', 'src/canvas.c']

HEADER_TEXT = r'''/* SPDX-License-Identifier: MIT */
/* Temporary rdtsc stage probe; never committed. */
#ifndef EXR_PROBE_INTERNAL_H
#define EXR_PROBE_INTERNAL_H
#include <x86intrin.h>
extern unsigned long long exr_probe_cycles[96],exr_probe_counts[96];
extern int exr_probe_in_mask;
#define PROBE_T() __rdtsc()
#define PROBE_ADD(slot,t0) (exr_probe_cycles[slot]+=__rdtsc()-(t0),exr_probe_counts[slot]++)
#define PROBE_BASE() (exr_probe_in_mask ? 48 : 32)
#endif
'''

EDITS = {
'src/pdf_paint.c': [
 ('_Thread_local size_t diag_sources,diag_masks;\n',
  '_Thread_local size_t diag_sources,diag_masks;\n#include "probe_internal.h"\n'
  '__declspec(dllexport) unsigned long long exr_probe_cycles[96],exr_probe_counts[96];\n'
  '__declspec(dllexport) unsigned long long exr_probe_rdtsc(void) { return __rdtsc(); }\n'
  'int exr_probe_in_mask;\n'),
 ('  status=exr_pdf_soft_mask_build(r->file,paint->smask,paint->smask_matrix,width,height,&mask->pixels,r->work,r->mask_bytes,r->control,e);\n'
  '  diag_mask_ms+=diag_ms()-started;diag_masks++;\n'
  '  if(status!=EXR_OK) { *r->mask_bytes-=mask->bytes;mask->bytes=0;return status; }\n'
  '  return exr_sink_soft_mask(&r->sink,mask->pixels,width,height,e);\n',
  '  unsigned long long pt=PROBE_T();exr_probe_in_mask++;\n'
  '  status=exr_pdf_soft_mask_build(r->file,paint->smask,paint->smask_matrix,width,height,&mask->pixels,r->work,r->mask_bytes,r->control,e);\n'
  '  exr_probe_in_mask--;PROBE_ADD(0,pt);\n'
  '  diag_mask_ms+=diag_ms()-started;diag_masks++;\n'
  '  if(status!=EXR_OK) { *r->mask_bytes-=mask->bytes;mask->bytes=0;return status; }\n'
  '  pt=PROBE_T();status=exr_sink_soft_mask(&r->sink,mask->pixels,width,height,e);PROBE_ADD(11,pt);return status;\n'),
 ('  exr_status status=EXR_OK;\n  exr_error cleanup={0};\n  if(mask->pixels) status=exr_sink_soft_mask(&r->sink,NULL,0,0,prior==EXR_OK ? e : &cleanup);\n'
  '  *r->mask_bytes-=mask->bytes;exr_buffer_put(exr_pdf_buffer_pool(r->file),mask->pixels,mask->bytes);memset(mask,0,sizeof(*mask));\n',
  '  exr_status status=EXR_OK;unsigned long long pt=PROBE_T();\n  exr_error cleanup={0};\n  if(mask->pixels) status=exr_sink_soft_mask(&r->sink,NULL,0,0,prior==EXR_OK ? e : &cleanup);\n'
  '  *r->mask_bytes-=mask->bytes;exr_buffer_put(exr_pdf_buffer_pool(r->file),mask->pixels,mask->bytes);memset(mask,0,sizeof(*mask));PROBE_ADD(12,pt);\n'),
 ('  if(FT_Init_FreeType(&r.library)) return exr_fail(e,EXR_MEMORY,"PDF font library initialization failed");\n',
  '  unsigned long long pft=PROBE_T();\n'
  '  if(FT_Init_FreeType(&r.library)) return exr_fail(e,EXR_MEMORY,"PDF font library initialization failed");\n'
  '  if(exr_probe_in_mask) PROBE_ADD(13,pft);\n'),
 ('  exr_icc_free(r.cmyk_profile);FT_Done_FreeType(r.library); return status;\n',
  '  pft=PROBE_T();exr_icc_free(r.cmyk_profile);FT_Done_FreeType(r.library);if(exr_probe_in_mask) PROBE_ADD(13,pft);\n  return status;\n'),
],
'src/pdf_softmask.c': [
 ('#include <stdio.h>\n', '#include <stdio.h>\n#include "probe_internal.h"\n'),
 ('  exr_pdf_function *function=NULL;size_t sample_cost;int group;\n  *out = NULL;\n',
  '  exr_pdf_function *function=NULL;size_t sample_cost;int group;\n  unsigned long long pt=PROBE_T();\n  *out = NULL;\n'),
 ('  config.initial_clip=box;config.initial_clip_transform=matrix;config.mask_budget=0;\n',
  '  config.initial_clip=box;config.initial_clip_transform=matrix;config.mask_budget=0;\n  PROBE_ADD(1,pt);\n'),
 ('  status=load_transfer(file,mask,control,&function,e);\n',
  '  pt=PROBE_T();\n  status=load_transfer(file,mask,control,&function,e);\n'),
 ('  pixels = bitmap.pixels;\n  for(size_t y=0;y<height;y++) {\n',
  '  pixels = bitmap.pixels;\n  PROBE_ADD(8,pt);pt=PROBE_T();\n  for(size_t y=0;y<height;y++) {\n'),
 ('      memcpy(result+y*width,result+(y-1)*width,width);\n      continue;\n    }\n',
  '      memcpy(result+y*width,result+(y-1)*width,width);\n      exr_probe_counts[21]++;\n      continue;\n    }\n    exr_probe_counts[20]++;\n'),
 ('      if(x && !memcmp(pixels+i*4,pixels+(i-1)*4,4)) { result[i]=result[i-1];continue; }\n',
  '      if(x && !memcmp(pixels+i*4,pixels+(i-1)*4,4)) { result[i]=result[i-1];exr_probe_counts[23]++;continue; }\n      exr_probe_counts[22]++;\n'),
 ('  status=EXR_OK;\ndone:\n  exr_pdf_function_free(function);\n',
  '  status=EXR_OK;\n  PROBE_ADD(9,pt);\ndone:\n  exr_pdf_function_free(function);\n'),
 ('  exr_buffer_put(exr_pdf_buffer_pool(file),bitmap.pixels,(size_t)bitmap.stride*bitmap.height);\n  *out = result;\n',
  '  pt=PROBE_T();exr_buffer_put(exr_pdf_buffer_pool(file),bitmap.pixels,(size_t)bitmap.stride*bitmap.height);PROBE_ADD(10,pt);\n  *out = result;\n'),
],
'src/pdf_raster.c': [
 ('#include "canvas_internal.h"\n', '#include "canvas_internal.h"\n#include "probe_internal.h"\n'),
 ('  status=exr_canvas_create_pooled(&settings,exr_pdf_buffer_pool(file),&canvas,e); if(status!=EXR_OK) return status;\n',
  '  unsigned long long pt=PROBE_T();int pm=exr_probe_in_mask;\n'
  '  status=exr_canvas_create_pooled(&settings,exr_pdf_buffer_pool(file),&canvas,e); if(status!=EXR_OK) return status;\n'
  '  if(pm) PROBE_ADD(2,pt);\n'),
 ('    status=exr_canvas_clip(canvas,rect,5,config->initial_clip_transform,EXR_FILL_NONZERO,e); if(status!=EXR_OK) goto done;\n',
  '    pt=PROBE_T();\n'
  '    status=exr_canvas_clip(canvas,rect,5,config->initial_clip_transform,EXR_FILL_NONZERO,e); if(status!=EXR_OK) goto done;\n'
  '    if(pm) PROBE_ADD(3,pt);\n'),
 ('  sink.struct_size=sizeof(sink);status=exr_canvas_get_sink_ex(canvas,&sink,e);\n',
  '  pt=PROBE_T();\n  sink.struct_size=sizeof(sink);status=exr_canvas_get_sink_ex(canvas,&sink,e);\n'),
 ('    exr_error cleanup={0};exr_status ended;\n'
  '    status=exr_pdf_paint_content_ex(file,resources,content,size,initial,&sink,config->program,config->context,&canvas->work,config->active_mask_bytes,control,e);\n'
  '    ended=exr_canvas_end_layer(canvas,status==EXR_OK,&cleanup);\n',
  '    exr_error cleanup={0};exr_status ended;\n    if(pm) PROBE_ADD(4,pt);\n    pt=PROBE_T();\n'
  '    status=exr_pdf_paint_content_ex(file,resources,content,size,initial,&sink,config->program,config->context,&canvas->work,config->active_mask_bytes,control,e);\n'
  '    if(pm) PROBE_ADD(5,pt);\n    pt=PROBE_T();\n'
  '    ended=exr_canvas_end_layer(canvas,status==EXR_OK,&cleanup);\n    if(pm) PROBE_ADD(6,pt);\n    pt=PROBE_T();\n'),
 ('  if(config->work) *config->work=canvas->work;\n  exr_canvas_free(canvas); return status;\n',
  '  if(config->work) *config->work=canvas->work;\n  exr_canvas_free(canvas);\n  if(pm) PROBE_ADD(7,pt);\n  return status;\n'),
],
'src/pdf_shading.c': [
 ('#include <float.h>\n', '#include <float.h>\n#include "probe_internal.h"\n'),
 ('  if(native_cmyk && device!=EXR_PDF_DEVICE_CMYK) status=exr_icc_default_cmyk(control,&profile,e);\n'
  '  for(unsigned i=0;i<AXIAL_SAMPLES && status==EXR_OK;i++) {\n',
  '  if(native_cmyk && device!=EXR_PDF_DEVICE_CMYK) status=exr_icc_default_cmyk(control,&profile,e);\n'
  '  unsigned long long pt=PROBE_T();int pb=PROBE_BASE();\n'
  '  for(unsigned i=0;i<AXIAL_SAMPLES && status==EXR_OK;i++) {\n'),
 ('  if(status==EXR_OK) status=exr_icc_deferred_status(profile,e);\n  if(status==EXR_OK) {\n    memcpy(data.coords,coords,sizeof(data.coords));',
  '  PROBE_ADD(pb+1,pt);\n  if(status==EXR_OK) status=exr_icc_deferred_status(profile,e);\n  if(status==EXR_OK) {\n    memcpy(data.coords,coords,sizeof(data.coords));'),
 ('    data.work=work;data.rgb=rgb;data.inks=inks.pixels;\n    status=emit(context,&source,matrix,paint,e);\n',
  '    data.work=work;data.rgb=rgb;data.inks=inks.pixels;\n    pt=PROBE_T();status=emit(context,&source,matrix,paint,e);PROBE_ADD(pb+2,pt);\n'),
 ('exr_status exr_pdf_shading_draw(exr_pdf_file *file,exr_pdf_file *resource_file,uint32_t resources,\n'
  '                                uint32_t value,const double ctm[6],const exr_pdf_paint_state *paint,size_t *work,\n'
  '                                exr_pdf_shading_fn emit,exr_pdf_source_fn source,void *context,unsigned native_cmyk,\n'
  '                                const exr_control *control,exr_error *e) {\n',
  'static exr_status shading_draw_impl(exr_pdf_file *file,exr_pdf_file *resource_file,uint32_t resources,\n'
  '                                uint32_t value,const double ctm[6],const exr_pdf_paint_state *paint,size_t *work,\n'
  '                                exr_pdf_shading_fn emit,exr_pdf_source_fn source,void *context,unsigned native_cmyk,\n'
  '                                const exr_control *control,exr_error *e);\n'
  'exr_status exr_pdf_shading_draw(exr_pdf_file *file,exr_pdf_file *resource_file,uint32_t resources,\n'
  '                                uint32_t value,const double ctm[6],const exr_pdf_paint_state *paint,size_t *work,\n'
  '                                exr_pdf_shading_fn emit,exr_pdf_source_fn source,void *context,unsigned native_cmyk,\n'
  '                                const exr_control *control,exr_error *e) {\n'
  '  int pb=PROBE_BASE();unsigned long long pt=PROBE_T();\n'
  '  exr_status s=shading_draw_impl(file,resource_file,resources,value,ctm,paint,work,emit,source,context,native_cmyk,control,e);\n'
  '  PROBE_ADD(pb,pt);return s;\n}\n'
  'static exr_status shading_draw_impl(exr_pdf_file *file,exr_pdf_file *resource_file,uint32_t resources,\n'
  '                                uint32_t value,const double ctm[6],const exr_pdf_paint_state *paint,size_t *work,\n'
  '                                exr_pdf_shading_fn emit,exr_pdf_source_fn source,void *context,unsigned native_cmyk,\n'
  '                                const exr_control *control,exr_error *e) {\n'),
],
'src/canvas.c': [
 ('#include <stdio.h>\n', '#include <stdio.h>\n#include "probe_internal.h"\n', 1),
 ('exr_status exr_canvas_paint(exr_canvas *c,const exr_paint_source *input,const double transform[6],double alpha,exr_error *e) {\n',
  'static exr_status canvas_paint_impl(exr_canvas *c,const exr_paint_source *input,const double transform[6],double alpha,exr_error *e);\n'
  'exr_status exr_canvas_paint(exr_canvas *c,const exr_paint_source *input,const double transform[6],double alpha,exr_error *e) {\n'
  '  int pb=PROBE_BASE();unsigned long long pt=PROBE_T();exr_status s=canvas_paint_impl(c,input,transform,alpha,e);PROBE_ADD(pb+3,pt);return s;\n}\n'
  'static exr_status canvas_paint_impl(exr_canvas *c,const exr_paint_source *input,const double transform[6],double alpha,exr_error *e) {\n'
  '  int pb=PROBE_BASE();\n'),
 ('  for(unsigned y=0;y<c->bitmap.height;y++) {\n    const unsigned char *clip_row=NULL;\n    unsigned first=0,last=c->bitmap.width;size_t active=c->bitmap.width;\n',
  '  for(unsigned y=0;y<c->bitmap.height;y++) {\n    const unsigned char *clip_row=NULL;\n    unsigned first=0,last=c->bitmap.width;size_t active=c->bitmap.width;\n'
  '    unsigned long long prow=PROBE_T();exr_probe_counts[pb+8]++;\n'),
 ('    if(!exr_vector_work(&c->work,active*cost+(clip_row ? last-first : 0))) return finish(c,exr_fail(e,EXR_LIMIT,"Paint source work budget exceeded"),e);\n',
  '    if(!exr_vector_work(&c->work,active*cost+(clip_row ? last-first : 0))) return finish(c,exr_fail(e,EXR_LIMIT,"Paint source work budget exceeded"),e);\n'
  '    exr_probe_cycles[pb+5]+=PROBE_T()-prow;\n'),
 ('            if(fast_group) {\n              float *q=state->pixels+((size_t)y*c->bitmap.width+x)*5;\n',
  '            unsigned long long pspan=PROBE_T();\n'
  '            if(fast_group) {\n              float *q=state->pixels+((size_t)y*c->bitmap.width+x)*5;\n'),
 ('              for(unsigned i=x;i<end;i++) if(mask_row[i]) exr_pixel(&target,(int)i,(int)y,(in_color&0xffffff00u)|mask_row[i],255);\n            }\n',
  '              for(unsigned i=x;i<end;i++) if(mask_row[i]) exr_pixel(&target,(int)i,(int)y,(in_color&0xffffff00u)|mask_row[i],255);\n            }\n'
  '            exr_probe_cycles[pb+4]+=PROBE_T()-pspan;exr_probe_counts[pb+4]++;exr_probe_counts[pb+9]+=end-x;\n'
  '            if(!fast_group) { const unsigned char *mr=state->soft_mask+(size_t)y*state->soft_mask_width;for(unsigned i=x;i<end;i++) exr_probe_counts[pb+10]+=!mr[i]; }\n'),
 ('          if(in_scale && have_in) {\n            if(!exr_vector_work(axial->work,4))',
  '          if(in_scale && have_in) {\n            exr_probe_counts[pb+11]++;\n            if(!exr_vector_work(axial->work,4))'),
 ('          } else {\n            double sum_alpha=0,sum_shape=0;\n',
  '          } else {\n            double sum_alpha=0,sum_shape=0;exr_probe_counts[pb+12]++;\n'),
 ('static exr_status clip_path(exr_canvas *c,const exr_path_segment *segments,size_t count,const double matrix[6],exr_fill_rule rule,int group,exr_error *e) {\n',
  'static exr_status clip_path_impl(exr_canvas *c,const exr_path_segment *segments,size_t count,const double matrix[6],exr_fill_rule rule,int group,exr_error *e);\n'
  'static exr_status clip_path(exr_canvas *c,const exr_path_segment *segments,size_t count,const double matrix[6],exr_fill_rule rule,int group,exr_error *e) {\n'
  '  unsigned long long pt=PROBE_T();exr_status s=clip_path_impl(c,segments,count,matrix,rule,group,e);if(exr_probe_in_mask) PROBE_ADD(17,pt);\n  return s;\n}\n'
  'static exr_status clip_path_impl(exr_canvas *c,const exr_path_segment *segments,size_t count,const double matrix[6],exr_fill_rule rule,int group,exr_error *e) {\n'),
 ('  if(c->clip && !c->soft_mask && !(flags&EXR_GROUP_WHOLE_BUFFER)) {\n    size_t x0=region_width,y0=region_height,x1=0,y1=0,yy;\n',
  '  unsigned long long pt=PROBE_T();\n'
  '  if(c->clip && !c->soft_mask && !(flags&EXR_GROUP_WHOLE_BUFFER)) {\n    size_t x0=region_width,y0=region_height,x1=0,y1=0,yy;\n'),
 ('  count=region_width*region_height;bytes=count*(needs_state ? 4+5*sizeof(float) : 4)',
  '  if(exr_probe_in_mask) PROBE_ADD(16,pt);\n  count=region_width*region_height;bytes=count*(needs_state ? 4+5*sizeof(float) : 4)'),
 ('  pixels=exr_buffer_take(c->pool,count*4,1);if(needs_state)',
  '  pt=PROBE_T();\n  pixels=exr_buffer_take(c->pool,count*4,1);if(needs_state)'),
 ('  next=c->bitmap;next.channels=4;next.width=(uint32_t)region_width;',
  '  if(exr_probe_in_mask) PROBE_ADD(14,pt);\n  next=c->bitmap;next.channels=4;next.width=(uint32_t)region_width;'),
 ('      status=exr_composite_initialize(&next,state,parent,parent_state,backdrop_x,backdrop_y,&c->work,&c->control,e);\n',
  '      pt=PROBE_T();\n      status=exr_composite_initialize(&next,state,parent,parent_state,backdrop_x,backdrop_y,&c->work,&c->control,e);\n'
  '      if(exr_probe_in_mask) PROBE_ADD(15,pt);\n'),
],
}


def apply():
    HEADER.write_text(HEADER_TEXT, newline='\n')
    for name, edits in EDITS.items():
        path = ROOT/name
        text = path.read_text(encoding='utf-8')
        for edit in edits:
            old, new = edit[0], edit[1]
            n = text.count(old)
            assert n == (edit[2] if len(edit) > 2 else 1) or (len(edit) > 2 and n >= 1), (name, old[:80], n)
            text = text.replace(old, new, 1)
        path.write_bytes(text.encode('utf-8'))
        print('probed', name)


def revert():
    subprocess.run(['git', '-C', str(ROOT), 'checkout', '--', *FILES], check=True)
    HEADER.unlink(missing_ok=True)
    print('reverted')


if __name__ == '__main__':
    {'apply': apply, 'revert': revert}[sys.argv[1]]()
