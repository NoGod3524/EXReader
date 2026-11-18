# SPDX-License-Identifier: MIT
"""Build a Windows diagnostic DLL from copied sources and Release objects."""
import argparse
import re
import shlex
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BUILD = ROOT / 'build/perf'


def instrument(out, ref, name, replacements):
    source = ((ROOT / 'src' / name).read_text(encoding='utf-8') if ref == 'worktree'
              else subprocess.check_output(['git', 'show', f'{ref}:src/{name}'], cwd=ROOT,
                                           text=True, encoding='utf-8'))
    for old, new in replacements:
        assert source.count(old) == 1, old
        source = source.replace(old, new, 1)
    copy = out / name
    copy.write_text(source, encoding='utf-8')
    return copy


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--ref', default='ad85474161eb6b59600149b7a1e8300758e8dd57')
    parser.add_argument('--coarse', action='store_true', help='Instrument image and clip callbacks only')
    parser.add_argument('--out', type=Path, default=ROOT/'build/multiimage/probe')
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if args.coarse:
        affine = instrument(out, args.ref, 'affine_image.c', [])
    else:
        affine = instrument(out, args.ref, 'affine_image.c', [
        ('#include <fenv.h>', '#include <fenv.h>\n#include "probe.h"'),
        ('  if(!axis_layer_init(&color', '  long long setup = tick();\n  if(!axis_layer_init(&color'),
        ('    axis_layer_free(&color);axis_layer_free(&mask); return 0;\n  }',
         '    axis_layer_free(&color);axis_layer_free(&mask); return 0;\n  }\n  probe_add(2, setup);'),
        ('    axis_row r; int cneed', '    long long prep = tick();\n    axis_row r; int cneed'),
        ('    if(!ccount) continue;', '    if(!ccount) { probe_add(3, prep); continue; }'),
        ('    axis_row_paint(&r);', '    probe_add(3, prep);\n    axis_row_paint(&r);'),
        ('    if(!coverage) continue;\n    for(unsigned sy=0;sy<2;sy++) if(r->valid[sy]) {',
         '''    if(!coverage) continue;
    int sampled = probe_detailed && ((x + 31*r->y) & 127) == 0;
    if(sampled) probe_count(8);
    for(unsigned sy=0;sy<2;sy++) if(r->valid[sy]) {'''),
        ('        if(!m) { converted_sample(r->crows[sy][0],r->crows[sy][1],index,w,cy0,cy1,&rg,&ba); continue; }',
         '''        long long t = sampled ? tick() : 0;
        if(!m) {
          converted_sample(r->crows[sy][0],r->crows[sy][1],index,w,cy0,cy1,&rg,&ba);
          if(sampled) probe_add_sample(4, t, _mm_cvtsd_f64(rg), _mm_cvtsd_f64(ba));
          continue;
        }'''),
        ('        if(m->interpolate) {\n          __m128d mrg', '''        if(sampled) {
          probe_add_sample(4, t, _mm_cvtsd_f64(srg), _mm_cvtsd_f64(sba));
          t = tick();
        }
        if(m->interpolate) {
          __m128d mrg'''),
        ('        rg=_mm_add_pd(rg,_mm_mul_pd(srg,a));ba=_mm_add_pd(ba,_mm_mul_pd(sba,a));',
         '''        rg=_mm_add_pd(rg,_mm_mul_pd(srg,a));ba=_mm_add_pd(ba,_mm_mul_pd(sba,a));
        if(sampled) probe_add_sample(5, t, _mm_cvtsd_f64(rg), _mm_cvtsd_f64(ba));'''),
        ('    axis_store(r,x,sums,coverage);', '''    long long t = sampled ? tick() : 0;
    axis_store(r,x,sums,coverage);
    if(sampled) {
      const unsigned char *p = r->target->pixels + (size_t)r->y*r->target->stride + (size_t)x*4;
      probe_add_sample(6, t, p[0], p[2]);
    }'''),
        ])
    canvas = instrument(out, args.ref, 'canvas.c', [
        ('#include <stdio.h>', '#include <stdio.h>\n#include "probe.h"'),
        ('  return clip_path(context,segments,count,matrix,rule,accumulate!=0,e);', '''
  long long t=tick();
  exr_status status=clip_path(context,segments,count,matrix,rule,accumulate!=0,e);
  probe_add(1,t);
  return status;'''),
        ('  return exr_canvas_image(context,image,matrix,alpha,e);', '''
  const exr_canvas *c=context;
  probe_image(image, matrix, c->clip,
    c->composite || c->soft_mask || c->gray_groups || (c->alpha_flags&EXR_ALPHA_CONSTANT_SHAPE));
  long long t=tick();
  exr_status status=exr_canvas_image(context,image,matrix,alpha,e);
  probe_add(0,t);
  probe_end_image();
  return status;'''),
    ])
    paint = instrument(out, args.ref, 'pdf_paint.c', [
        ('#include "pdf_raster_internal.h"', '#include "pdf_raster_internal.h"\n#include "probe.h"'),
        ('  status=exr_pdf_image_load_inks(file,id,', '  long long load = tick();\n  status=exr_pdf_image_load_inks(file,id,'),
        ('  multiply(paint->matrix,flip,matrix);', '  probe_add(7,load);\n  multiply(paint->matrix,flip,matrix);'),
    ])
    ninja = (BUILD / 'build.ninja').read_text(encoding='utf-8')
    cache = (BUILD / 'CMakeCache.txt').read_text(encoding='utf-8')
    cc = re.search(r'^CMAKE_C_COMPILER:[^=]+=(.*)$', cache, re.M)[1]
    link = re.search(r'^build (?:\S+/)?libexreader\.dll .*?Release (.*?) \|.*?^  LINK_LIBRARIES = ([^\n]*)',
                     ninja, re.M | re.S)
    objects = link[1]
    for source in (affine, canvas, paint, HERE / 'probe.c'):
        obj = out / (source.stem + '.o')
        original = 'canvas' if source.stem == 'probe' else source.stem
        rule = re.search(r'^build (\S+/src/' + original + r'\.c\.obj):[^\n]+\n((?:  [^\n]+\n)+)', ninja, re.M)
        flags = [arg for key in ('DEFINES', 'FLAGS', 'INCLUDES')
                 for arg in shlex.split(re.search(r'^  ' + key + r' = (.*)$', rule[2], re.M)[1])]
        subprocess.run([cc, *flags, '-I' + str(ROOT / 'src'), '-I' + str(HERE),
                        '-c', str(source), '-o', str(obj)], cwd=BUILD, check=True)
        if original == source.stem:
            assert rule[1] in objects
            objects = objects.replace(rule[1], '"' + obj.as_posix() + '"')
        else:
            objects += ' "' + obj.as_posix() + '"'
    rsp = out / 'link.rsp'
    rsp.write_text(objects + ' ' + link[2])
    subprocess.run([cc, '-shared', '-static-libgcc', '-static', 'exreader.def',
                    '-o', str(out / 'libexreader.dll'), '@' + str(rsp)], cwd=BUILD, check=True)


if __name__ == '__main__':
    main()
