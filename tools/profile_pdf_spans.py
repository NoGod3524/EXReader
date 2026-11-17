#!/usr/bin/env python3
"""Build instrumented graphics objects beside a MinGW build and measure PDF paths.

Production sources/objects are never modified. Timings include instrumentation
overhead and are diagnostic; use benchmark_pdf_rect.py for acceptance timings.
"""
# SPDX-License-Identifier: MIT
import argparse
import ctypes as c
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import statistics
import subprocess
import time

from benchmark_pdf_rect import Bitmap, Error, Page, set_process_controls

NAMES = ['rectangle_opaque', 'rectangle_alpha', 'rectangle_clip',
         'rectangle_complex', 'vector_fill_inclusive', 'group_commit',
         'image_paint', 'sampled_paint', 'canvas_create', 'group_begin',
         'group_end_inclusive', 'clip_bounds']
SUPPORT = r'''
#include <stdint.h>
#include <windows.h>
static uint64_t ticks[12],exclusive[12],calls[12],pixels[12];
static _Thread_local unsigned depth[12],stack_size;
static _Thread_local uint64_t children[64];
uint64_t exr_profile_begin(unsigned id,uint64_t count,unsigned group) {
  LARGE_INTEGER t;
  if(depth[group]++) return 0;
  calls[id]++;pixels[id]+=count;children[stack_size++]=0;QueryPerformanceCounter(&t);return (uint64_t)t.QuadPart;
}
void exr_profile_end(unsigned id,uint64_t start,unsigned group) {
  LARGE_INTEGER t;
  if(start) {
    uint64_t elapsed;QueryPerformanceCounter(&t);elapsed=(uint64_t)t.QuadPart-start;
    ticks[id]+=elapsed;exclusive[id]+=elapsed-children[--stack_size];
    if(stack_size) children[stack_size-1]+=elapsed;
  }
  depth[group]--;
}
__declspec(dllexport) void exr_profile_reset(void) {
  unsigned i;for(i=0;i<12;i++) ticks[i]=exclusive[i]=calls[i]=pixels[i]=0;
}
__declspec(dllexport) void exr_profile_read(uint64_t *out) {
  LARGE_INTEGER f;unsigned i;QueryPerformanceFrequency(&f);
  for(i=0;i<12;i++) {
    out[i*4]=ticks[i]*1000000000/(uint64_t)f.QuadPart;
    out[i*4+1]=exclusive[i]*1000000000/(uint64_t)f.QuadPart;
    out[i*4+2]=calls[i];out[i*4+3]=pixels[i];
  }
}
'''
DECL = '#include <stdint.h>\nuint64_t exr_profile_begin(unsigned,uint64_t,unsigned);\nvoid exr_profile_end(unsigned,uint64_t,unsigned);\n'


def wrap(source, name, arguments, category, pixel_count, group):
    match = re.search(r'(?:static )?(void|exr_status|const exr_clip_bounds \*)\s*' + name + r'\([^;{}]*\)\s*\{', source)
    if not match:
        raise ValueError(f'Function not found: {name}')
    signature = match.group()[:-1].strip()
    end, depth = match.end(), 1
    while depth:
        if source[end] == '{':
            depth += 1
        elif source[end] == '}':
            depth -= 1
        end += 1
    implementation = source[match.start():end].replace(name + '(', name + '_profile_impl(', 1)
    returns = match.group(1) != 'void'
    body = f'''{signature} {{
  unsigned id={category};uint64_t started=exr_profile_begin(id,{pixel_count},{group});
  {match.group(1) + ' result=' if returns else ''}{name}_profile_impl({arguments});
  exr_profile_end(id,started,{group});{'return result;' if returns else ''}
}}
'''
    return source[:match.start()] + signature + ';\n' + implementation + '\n' + body + source[end:]


def words(command):
    return [s[1:-1] if s.startswith('"') and s.endswith('"') else s
            for s in shlex.split(command, posix=False)]


def variant_source(root, filename, baseline, variant):
    source = (root / 'src' / filename).read_text(encoding='utf-8')
    if variant == 'all':
        return source
    old = (baseline / 'src' / filename).read_text(encoding='utf-8')
    marker = 'static exr_status fill_blend('
    if variant == 'baseline':
        return old
    if variant == 'simd':
        if filename == 'vector.c':
            return source[:source.index(marker)] + old[old.index(marker):]
        if filename == 'blend.c':
            marker = 'uint32_t exr_gray_color('
            return source[:source.index(marker)] + old[old.index(marker):]
        return old
    if filename == 'vector.c':
        return old[:old.index(marker)] + source[source.index(marker):]
    return source


def build_profile(root, build, output, baseline=None, variant='all', instrument=True):
    records = json.loads(subprocess.check_output(['ninja', '-C', str(build), '-t', 'compdb', '-x']))
    configs = {
        'vector.c': [
            ('rectangle_span', 'bitmap,left,right,y,coverage,color,cmyk,cmyk_alpha,clip,mode,state',
             '(clip ? 2 : !cmyk && !state && mode==EXR_BLEND_NORMAL ? ((color&255)==255 && coverage==255 ? 0 : 1) : 3)',
             '(uint64_t)(right>left ? right-left : 0)', 0),
            ('fill_blend', 'bitmap,edges,count,rule,color,cmyk,cmyk_alpha,clip,mode,state,work,control,error',
             '4', '0', 4)],
        'blend.c': [('exr_composite_frame', 'target,source,opacity,mode,clip,target_state,source_state,origin_x,origin_y,work,control,e',
                     '5', '(uint64_t)source->width*source->height', 5)],
        'affine_image.c': [('exr_vector_texture_blend_inks', 'target,source,inks,m,alpha,clip,mode,state,work,control,e',
                            '6', '0', 6)],
        'canvas.c': [('exr_canvas_paint', 'c,input,transform,alpha,e', '7', '0', 7),
                     ('exr_canvas_create', 'config,out,e', '8', '0', 8),
                     ('exr_canvas_begin_group', 'c,opacity,mode,flags,e', '9', '0', 9),
                     ('exr_canvas_end_layer', 'c,commit,e', '10', '0', 10),
                     ('clip_bounds', 'mask', '11', '0', 11)]}
    objects = {}
    compiler = None
    for filename, wrappers in configs.items():
        record = next(r for r in records if r['file'].replace('\\', '/').endswith('/src/' + filename)
                      and 'exr_graphics_objects.dir' in r['command'])
        command = words(record['command'])
        compiler = command[0]
        source = variant_source(root, filename, baseline, variant)
        if instrument:
            for definition in wrappers:
                if definition[0] != 'clip_bounds' or 'static const exr_clip_bounds *clip_bounds(' in source:
                    source = wrap(source, *definition)
        instrumented = output / filename
        instrumented.write_text((DECL if instrument else '') + source, encoding='utf-8')
        obj = output / (filename + '.obj')
        old_object = command[command.index('-o') + 1]
        objects[old_object.replace('\\', '/')] = str(obj)
        command[command.index('-o') + 1] = str(obj)
        command[command.index('-c') + 1] = str(instrumented)
        command.extend(['-I' + str(root / 'src')])
        subprocess.run(command, cwd=build, check=True, capture_output=True)
    if instrument:
        support = output / 'profile_support.c'
        support.write_text(SUPPORT, encoding='utf-8')
        support_obj = output / 'profile_support.obj'
        subprocess.run([compiler, '-O3', '-std=c11', '-c', str(support), '-o', str(support_obj)], check=True)
    link = next(r['command'] for r in records if ' -shared ' in r['command'] and '-o libexreader.dll ' in r['command'])
    link = link[link.index('&& ') + 3:link.rindex(' &&')]
    command = words(link)
    for i, arg in enumerate(command):
        command[i] = objects.get(arg.replace('\\', '/'), arg)
    dll = output / ('profile.dll' if instrument else 'variant.dll')
    command[command.index('-o') + 1] = str(dll)
    command = [arg for arg in command if not arg.startswith('-Wl,--out-implib,')]
    if instrument:
        command.append(str(support_obj))
    # A response file avoids Windows' command-line length limit.
    response = output / 'link.rsp'
    response.write_text(subprocess.list2cmdline([arg.replace('\\', '/') for arg in command[1:]]), encoding='utf-8')
    subprocess.run([compiler, '@' + str(response)], cwd=build, check=True)
    return dll


def measure(library, pdf, width, runs):
    directory = os.add_dll_directory(str(library.parent)) if os.name == 'nt' else None
    engine = c.CDLL(str(library))
    engine.exr_fixed_open.argtypes = [c.c_char_p, c.c_void_p, c.POINTER(c.c_void_p), c.POINTER(Error)]
    engine.exr_fixed_pages.argtypes = [c.c_void_p, c.POINTER(c.c_size_t)]
    engine.exr_fixed_pages.restype = c.POINTER(Page)
    engine.exr_fixed_render.argtypes = [c.c_void_p, c.c_size_t, c.c_double, c.c_void_p, c.POINTER(Bitmap), c.POINTER(Error)]
    engine.exr_fixed_free.argtypes = [c.c_void_p]
    engine.exr_bitmap_free.argtypes = [c.POINTER(Bitmap)]
    engine.exr_profile_read.argtypes = [c.POINTER(c.c_uint64)]
    document, error, count = c.c_void_p(), Error(), c.c_size_t()
    def check(status):
        if status:
            raise RuntimeError(error.message.decode('utf-8', errors='replace'))
    check(engine.exr_fixed_open(str(pdf).encode(), None, c.byref(document), c.byref(error)))
    records, total_ns, output_pixels = [], 0, 0
    try:
        pages = engine.exr_fixed_pages(document, c.byref(count))
        for run in range(runs + 1):
            for index in range(count.value):
                geometry = pages[index].geometry
                native = geometry.bounds[3] - geometry.bounds[1] if geometry.rotation % 180 else geometry.bounds[2] - geometry.bounds[0]
                bitmap = Bitmap()
                engine.exr_profile_reset()
                started = time.perf_counter_ns()
                status = engine.exr_fixed_render(document, index, width / (native * geometry.unit_scale), None, c.byref(bitmap), c.byref(error))
                elapsed = time.perf_counter_ns() - started
                counters = (c.c_uint64 * (len(NAMES) * 4))()
                engine.exr_profile_read(counters)
                try:
                    check(status)
                    if run:
                        output_pixels += bitmap.width * bitmap.height
                        total_ns += elapsed
                        records.append({'page': index + 1, 'run': run, 'render_ns': elapsed, 'counters': list(counters)})
                finally:
                    engine.exr_bitmap_free(c.byref(bitmap))
    finally:
        engine.exr_fixed_free(document)
        if directory:
            directory.close()
    paths = {}
    for i, name in enumerate(NAMES):
        ns, exclusive, calls, pixels = (sum(r['counters'][i * 4 + k] for r in records) for k in range(4))
        paths[name] = {'total_ns': ns, 'exclusive_ns': exclusive, 'calls': calls, 'span_pixels': pixels,
                       'ns_per_output_pixel': ns / output_pixels,
                       'exclusive_ns_per_output_pixel': exclusive / output_pixels,
                       'ns_per_span_pixel': ns / pixels if pixels else None}
    span_ns = sum(paths[name]['total_ns'] for name in NAMES[:4])
    vector_ns = paths['vector_fill_inclusive']['total_ns'] - span_ns
    residual_ns = total_ns - sum(path['exclusive_ns'] for path in paths.values())
    return {'width': width, 'runs': runs, 'output_pixels': output_pixels, 'total_render_ns': total_ns,
            'p50_ms': statistics.median(r['render_ns'] for r in records) / 1e6,
            'ns_per_output_pixel': total_ns / output_pixels, 'paths': paths,
            'vector_outside_rectangle_ns_per_output_pixel': vector_ns / output_pixels,
            'residual_ns_per_output_pixel': residual_ns / output_pixels, 'samples': records}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--width', type=int, default=1200)
    parser.add_argument('--runs', type=int, default=5)
    parser.add_argument('--cpu-affinity', type=lambda s: int(s, 0))
    parser.add_argument('--priority', choices=['normal', 'high'])
    parser.add_argument('--source-root', type=Path, help='Snapshot containing src/ for the matching build')
    parser.add_argument('--baseline-source', type=Path, help='Baseline src/ snapshot for ablations, compiled with current headers')
    parser.add_argument('--variant', choices=['baseline', 'simd', 'region', 'all'], default='all')
    parser.add_argument('--build-only', action='store_true', help='Build an uninstrumented DLL for benchmark_pdf_rect.py')
    parser.add_argument('--compile-only', action='store_true', help='Build an instrumented DLL without running measurements')
    parser.add_argument('--measure-library', type=Path, help='Measure an already instrumented DLL')
    args = parser.parse_args()
    root, build, output = Path(__file__).resolve().parents[1], args.build.resolve(), args.output.resolve()
    if args.source_root:
        root = args.source_root.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if args.variant != 'all' and not args.baseline_source:
        parser.error('--baseline-source is required for ablations')
    library = args.measure_library.resolve() if args.measure_library else build_profile(
        root, build, output, args.baseline_source.resolve() if args.baseline_source else None,
        args.variant, not args.build_only)
    if args.build_only or args.compile_only:
        print(library)
        return
    set_process_controls(args.cpu_affinity, args.priority)
    result = measure(library, args.input.resolve(), args.width, args.runs)
    result.update(scope='Instrumented wall time; exclusive times subtract nested timers; inclusive times overlap; residual includes uninstrumented paths and timer overhead',
                  library_sha256=hashlib.sha256(library.read_bytes()).hexdigest(),
                  input_sha256=hashlib.sha256(args.input.read_bytes()).hexdigest(),
                  variant=args.variant,
                  cpu_affinity=args.cpu_affinity, priority=args.priority,
                  source_sha256={name: hashlib.sha256(variant_source(root, name,
                      args.baseline_source.resolve() if args.baseline_source else None, args.variant).encode('utf-8')).hexdigest()
                      for name in ['vector.c', 'blend.c', 'affine_image.c', 'canvas.c']},
                  compiled_source_sha256={name: hashlib.sha256((library.parent / name).read_bytes()).hexdigest()
                      for name in ['vector.c', 'blend.c', 'affine_image.c', 'canvas.c']})
    (output / 'profile.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k != 'samples'}, indent=2))


if __name__ == '__main__':
    main()
