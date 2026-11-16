#!/usr/bin/env python3
"""Build a diagnostic MinGW DLL from timed source copies; keep production untouched."""
# SPDX-License-Identifier: MIT
import argparse
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from benchmark_pdf_blend import measure


def prelude(names):
    labels = ','.join('"' + name + '"' for name in names)
    return r'''
#include <windows.h>
#include <stdio.h>
static struct { size_t calls; double ms; } stage[32];
static size_t cases[256],case_pixels[256];
static double frequency;
static void dump_stages(void) {
  const char *names[]={LABELS};size_t i;
  for(i=0;i<sizeof(names)/sizeof(*names);i++)
    fprintf(stderr,"PDF_STAGE %s calls=%zu ms=%.9f\n",names[i],stage[i].calls,stage[i].ms);
  for(i=0;i<256;i++) if(cases[i])
    fprintf(stderr,"PDF_CASE flags=%zu calls=%zu pixels=%zu\n",i,cases[i],case_pixels[i]);
}
static double now_ms(void) {
  LARGE_INTEGER tick;
  if(!frequency) {
    LARGE_INTEGER f;QueryPerformanceFrequency(&f);frequency=(double)f.QuadPart;atexit(dump_stages);
  }
  QueryPerformanceCounter(&tick);return tick.QuadPart*1000.0/frequency;
}
'''.replace('LABELS', labels)


def wrap_public(source, names, extra=''):
    wrappers = []
    for index, name in enumerate(names):
        match = re.search(r'exr_status\s+' + name + r'\s*\((.*?)\)\s*\{', source, re.S)
        if not match:
            raise ValueError('Missing function ' + name)
        params = match.group(1)
        arguments = [re.search(r'(\w+)\s*$', re.sub(r'\[[^\]]*\]', '', param)).group(1)
                     for param in params.split(',')]
        source = source[:match.start()] + match.group(0).replace(name, 'timed_' + name, 1) + source[match.end():]
        wrappers.append(f'''exr_status {name}({params}) {{
  double before=now_ms();exr_status result=timed_{name}({','.join(arguments)});
  stage[{index}].calls++;stage[{index}].ms+=now_ms()-before;
  {extra}
  return result;
}}''')
    return source + '\n' + '\n'.join(wrappers)


def build_profile(args):
    build, output = args.build.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    rows = json.loads(subprocess.check_output(['ninja', '-C', str(build), '-t', 'compdb', '-x'], text=True))
    objects = {}
    hashes = {}
    import hashlib
    for unit in ('canvas', 'blend', 'vector', 'fixed'):
        relative = 'src/' + unit + '.c'
        source = (subprocess.check_output(['git', 'show', args.revision + ':' + relative], cwd=ROOT).decode()
                  if args.revision else (ROOT / relative).read_text())
        hashes[relative] = hashlib.sha256(source.encode()).hexdigest()
        if args.plain:
            pass
        elif unit == 'vector':
            source = source.replace('static exr_status fill_blend(', 'static exr_status timed_fill_blend(', 1)
            wrapper = r'''
static exr_status fill_blend(exr_bitmap *bitmap,const exr_vector_edge *edges,size_t count,
  exr_vector_rule rule,uint32_t color,const double *cmyk,double cmyk_alpha,
  const exr_bitmap *clip,exr_blend_mode mode,exr_composite_state *state,
  size_t *work,const exr_control *control,exr_error *error) {
  double before=now_ms();exr_status result=timed_fill_blend(bitmap,edges,count,rule,color,cmyk,cmyk_alpha,clip,mode,state,work,control,error);
  double elapsed=now_ms()-before;size_t category,i;int rectangle=0;
  if(count==4 && edges) {
    double left=DBL_MAX,right=-DBL_MAX,top=DBL_MAX,bottom=-DBL_MAX;
    for(i=0;i<4;i++) {
      left=fmin(left,fmin(edges[i].x0,edges[i].x1));right=fmax(right,fmax(edges[i].x0,edges[i].x1));
      top=fmin(top,fmin(edges[i].y0,edges[i].y1));bottom=fmax(bottom,fmax(edges[i].y0,edges[i].y1));
    }
    rectangle=axis_rectangle(edges,left,top,right,bottom);
  }
  category=rectangle ? (bitmap->channels==1 ? 0 : 1) : bitmap->channels==1 ? 2 : 3;
  stage[category].calls++;stage[category].ms+=elapsed;return result;
}
'''
            source = source.replace('\nexr_status exr_vector_fill_blend(', '\n' + wrapper + '\nexr_status exr_vector_fill_blend(', 1)
            source = '#include "vector_internal.h"\n' + prelude(['rectangle_masks', 'rectangle_rgba', 'general_masks', 'general_rgba']) + source
        elif unit == 'canvas':
            names = ['exr_canvas_create', 'exr_canvas_clip', 'exr_canvas_path', 'exr_canvas_begin_group', 'exr_canvas_end_layer', 'exr_canvas_image', 'exr_canvas_union_add', 'exr_canvas_union_commit']
            source = '#include "canvas_internal.h"\n' + prelude(names) + wrap_public(source, names)
        elif unit == 'blend':
            extra = r'''
  {
    unsigned flags=(opacity!=1) | ((mode!=EXR_BLEND_NORMAL)<<1) | ((clip!=NULL)<<2) |
      ((target_state && target_state->pixels)!=0 ? 8 : 0) |
      ((target_state && (target_state->soft_mask || target_state->shape || target_state->knockout || target_state->gray || target_state->cmyk_pixels)) ? 16 : 0) |
      ((source_state && source_state->pixels && !source_state->isolated) ? 32 : 0) |
      ((source_state && (source_state->shape || source_state->cmyk_pixels)) ? 64 : 0) |
      ((target->channels!=4 || source->channels!=4) ? 128 : 0);
    size_t area=source_state ? (size_t)(source_state->right-source_state->left)*(source_state->bottom-source_state->top) : (size_t)source->width*source->height;
    cases[flags]++;case_pixels[flags]+=area;
  }
'''
            source = '#include "graphics_internal.h"\n' + prelude(['exr_composite_frame']) + wrap_public(source, ['exr_composite_frame'], extra)
        else:
            source = '#include "document_internal.h"\n' + prelude(['exr_fixed_draw_ex']) + wrap_public(source, ['exr_fixed_draw_ex'])
        path = output / (unit + '-profile.c')
        path.write_text(source)
        object_name = 'CMakeFiles/' + ('exr_doc_objects' if unit == 'fixed' else 'exr_graphics_objects') + '.dir/src/' + unit + '.c.obj'
        row = next(row for row in rows if row['output'] == object_name)
        argv = [part.strip('"') for part in shlex.split(row['command'], posix=False)]
        argv[-1] = str(path)
        objects[object_name] = str(output / (unit + '-profile.obj'))
        argv[argv.index('-o') + 1] = objects[object_name]
        argv.insert(1, '-I' + str(ROOT / 'src'))
        subprocess.run(argv, cwd=build, check=True)
    line = next(row['command'] for row in rows if row['output'] == 'libexreader.dll')
    inner = line.split(' && ', 1)[1].rsplit(' && ', 1)[0]
    argv = [part.strip('"') for part in shlex.split(inner, posix=False)]
    argv[argv.index('-o') + 1] = str(output / 'libexreader.dll')
    argv = [objects.get(part, part) for part in argv]
    argv = [('-Wl,--out-implib,' + str(output / 'libexreader.dll.a')) if part.startswith('-Wl,--out-implib,') else part for part in argv]
    subprocess.run(argv, cwd=build, check=True)
    (output / 'sources.json').write_text(json.dumps(hashes, indent=2) + '\n')
    print(output / 'libexreader.dll')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, default=ROOT / 'build/perf')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--revision', help='git revision for the source copies; otherwise working tree')
    parser.add_argument('--plain', action='store_true', help='Rebuild source copies without timers (baseline DLL)')
    parser.add_argument('--library', type=Path)
    parser.add_argument('--input', type=Path, default=ROOT / 'tests/fixtures/pdf-hybrid-real/pptx-20.pdf')
    parser.add_argument('--width', type=int, default=1200)
    parser.add_argument('--child', action='store_true')
    args = parser.parse_args()
    if not args.library:
        build_profile(args)
    elif args.child:
        print(json.dumps(measure(args.library.resolve(), args.input.resolve(), args.width / 960, 8)))
    else:
        result = subprocess.run([sys.executable, __file__, '--library', str(args.library.resolve()), '--input', str(args.input.resolve()),
                                 '--width', str(args.width), '--output', str(args.output), '--child'], capture_output=True, text=True, check=True)
        record = json.loads(result.stdout)
        record['stages'] = {name: {'calls': int(calls), 'total_ms': float(ms)}
                            for name, calls, ms in re.findall(r'PDF_STAGE (\w+) calls=(\d+) ms=([\d.]+)', result.stderr)}
        record['composite_cases'] = [{'flags': int(flags), 'calls': int(calls), 'pixels': int(pixels)}
                                     for flags, calls, pixels in re.findall(r'PDF_CASE flags=(\d+) calls=(\d+) pixels=(\d+)', result.stderr)]
        record['scope'] = 'Diagnostic DLL: page 1, first draw plus eight repaints; inclusive overlapping canvas/vector/compositor timers'
        record['source_hashes'] = json.loads((args.library.parent / 'sources.json').read_text())
        record['total_render_ms'] = record['first_render_ms'] + sum(record['repaint_ms_samples'])
        stages = {name: value['total_ms'] for name, value in record['stages'].items()}
        record['phase_totals_ms'] = {
            'composite': stages['exr_composite_frame'],
            'end_layer_other': stages['exr_canvas_end_layer'] - stages['exr_composite_frame'],
            **{name.removeprefix('exr_canvas_'): stages[name] for name in
               ('exr_canvas_create', 'exr_canvas_clip', 'exr_canvas_path', 'exr_canvas_begin_group', 'exr_canvas_image', 'exr_canvas_union_add', 'exr_canvas_union_commit')},
            'draw_outside_profiled_canvas': stages['exr_fixed_draw_ex'] - sum(stages[name] for name in
                ('exr_canvas_path', 'exr_canvas_begin_group', 'exr_canvas_end_layer', 'exr_canvas_image', 'exr_canvas_union_add', 'exr_canvas_union_commit')),
            'render_setup_finish_other': record['total_render_ms'] - stages['exr_fixed_draw_ex'] - stages['exr_canvas_create'] - stages['exr_canvas_clip']}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.with_suffix('.txt').write_text(result.stderr)
        args.output.write_text(json.dumps(record, indent=2) + '\n')
        print(json.dumps(record, indent=2))


if __name__ == '__main__':
    main()
