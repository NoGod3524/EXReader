"""Windows page-turn evidence. Generated QPC probes do not alter release sources.

Run build, sdk, host in that order for each candidate. Full-book verification uses
tools/regress/run_realbooks.py independently. Times exclude pixel hashing.
"""
import argparse
import csv
import ctypes as c
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/regress'))
from run_realbooks import SDK, Bitmap, Options, Error, FixedOptions, pixel_hash, file_hash

FONT = ROOT.parent / 'exr-demo-2a/Reader.otf'


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def run(args, **kw):
    result = subprocess.run(args, capture_output=True, text=True, encoding='utf-8', errors='replace', **kw)
    if result.returncode:
        raise RuntimeError(str(args) + '\n' + result.stdout[-3000:] + result.stderr[-3000:])
    return result.stdout


def stats(values):
    values = sorted(values)
    return {k: values[math.ceil(q * len(values)) - 1] for k, q in [('p50', .5), ('p95', .95), ('max', 1)]}


def pin():
    kernel = c.windll.kernel32
    kernel.GetCurrentProcess.restype = c.c_void_p
    kernel.SetProcessAffinityMask.argtypes = [c.c_void_p, c.c_size_t]
    kernel.SetPriorityClass.argtypes = [c.c_void_p, c.c_uint]
    process = kernel.GetCurrentProcess()
    assert kernel.SetProcessAffinityMask(process, 1 << 3)
    assert kernel.SetPriorityClass(process, 0x80)


def build(args):
    """Replace selected compilation units only in a second, instrumented DLL."""
    build = args.build.resolve()
    work = args.output.resolve()
    work.mkdir(parents=True, exist_ok=True)
    commands = json.loads(run(['ninja', '-t', 'compdb', '-x'], cwd=build))
    header = '''#include <windows.h>
typedef struct { double shape_ms, inline_ms, load_ms, ft_raster_ms; unsigned long long shapes, loads, rasters, metric_hits, metric_misses, shape_hits, glyph_hits; } perf_data;
extern _Thread_local perf_data perf;
static double perf_now(void) { LARGE_INTEGER t,f; QueryPerformanceCounter(&t); QueryPerformanceFrequency(&f); return 1000.0*(double)t.QuadPart/(double)f.QuadPart; }
'''
    (work / 'perf_trace.h').write_text(header)
    replacements = {}
    for name in ['opentype', 'inline', 'fonts', 'raster']:
        source = (ROOT / f'src/{name}.c').read_text(encoding='utf-8')
        source = '#include "perf_trace.h"\n' + source
        if name == 'opentype':
            source += '''\n_Thread_local perf_data perf;
__declspec(dllexport) void exr_perf_read(perf_data *out) { *out=perf; }
__declspec(dllexport) void exr_perf_reset(void) { memset(&perf,0,sizeof(perf)); }
'''
            source = re.sub(r'return shape\(([^;]+)\);', r'double t=perf_now(); perf.shapes++; exr_status s=shape(\1); perf.shape_ms+=perf_now()-t; return s;', source)
            source = source.replace('if(cached) {\n      result=', 'if(cached) {\n      perf.shape_hits++; result=')
        elif name == 'inline':
            source = source.replace('exr_status exr_inline_shape(', 'static exr_status perf_inline_shape(')
            source += '''\nexr_status exr_inline_shape(flow *f,size_t start,uint32_t before,uint32_t after) {
double t=perf_now(); exr_status s=perf_inline_shape(f,start,before,after); perf.inline_ms+=perf_now()-t; return s; }
'''
        elif name == 'fonts':
            source = source.replace('*advance = font->advances[glyph];', 'perf.metric_hits++; *advance = font->advances[glyph];')
            source = source.replace('  if(font->bitmap_only) {\n    unsigned metrics=', '  perf.metric_misses++;\n  if(font->bitmap_only) {\n    unsigned metrics=')
        if name in ('fonts', 'raster', 'opentype'):
            # The wrapper is defined before the macro, so FreeType itself is unchanged.
            marker = '#include "font_internal.h"' if name == 'fonts' else '#include "layout_internal.h"' if name == 'raster' else '#include "opentype_internal.h"'
            assert marker in source, name
            wrapper = '''
static FT_Error perf_load(FT_Face f,FT_UInt g,FT_Int32 flags) { double t=perf_now(); FT_Error e=FT_Load_Glyph(f,g,flags); perf.load_ms+=perf_now()-t;perf.loads++;return e; }
#define FT_Load_Glyph perf_load
'''
            if name == 'raster':
                source = source.replace('if(cached) {', 'if(cached) { perf.glyph_hits++;')
                wrapper += '''static FT_Error perf_raster(FT_GlyphSlot g,FT_Render_Mode mode) { double t=perf_now(); FT_Error e=FT_Render_Glyph(g,mode);perf.ft_raster_ms+=perf_now()-t;perf.rasters++;return e; }
#define FT_Render_Glyph perf_raster
'''
            source = source.replace(marker, marker + '\n' + wrapper)
        generated = work / f'{name}.c'
        generated.write_text(source, encoding='utf-8')
        command = next(x for x in commands if x.get('file', '').replace('\\', '/').endswith(f'/src/{name}.c'))['command']
        match = re.search(r' -o (\S+) -c (.+)$', command)
        assert match, command
        obj = work / f'{name}.obj'
        replacements[match[1]] = obj.as_posix()
        command = command[:match.start()] + f' -I{ROOT.as_posix()}/src -I{work.as_posix()} -o {obj.as_posix()} -c {generated.as_posix()}'
        run(command, cwd=build, shell=True)
    link = next(x['command'] for x in commands if x.get('output') == 'libexreader.dll')
    for old, new in replacements.items():
        if old not in link:
            old = old.replace('/', '\\')
        assert old in link, old
        link = link.replace(old, new)
    # Keep the baseline import library intact; only the DLL is copied to the probe directory.
    link = link.replace('-o libexreader.dll', '-o ' + (work / 'libexreader.dll').as_posix())
    link = link.replace('--out-implib,libexreader.dll.a', '--out-implib,' + (work / 'libexreader.dll.a').as_posix())
    run(link, cwd=build, shell=True)
    write(work / 'identity.json', {'release_dll': file_hash(build / 'libexreader.dll'),
          'instrumented_dll': file_hash(work / 'libexreader.dll'), 'source': run(['git', 'rev-parse', 'HEAD']).strip()})


class Perf(c.Structure):
    _fields_ = [(k, c.c_double) for k in ('shape_ms', 'inline_ms', 'load_ms', 'ft_raster_ms')] + [
        (k, c.c_ulonglong) for k in ('shapes', 'loads', 'rasters', 'metric_hits', 'metric_misses', 'shape_hits', 'glyph_hits')]


def sdk(args):
    pin()
    library = SDK(args.dll.resolve())
    traced = hasattr(library.dll, 'exr_perf_read')
    perf_read = library.dll.exr_perf_read if traced else lambda _: None
    perf_reset = library.dll.exr_perf_reset if traced else lambda: None
    if traced:
        perf_read.argtypes = [c.POINTER(Perf)]
    books = json.loads(args.manifest.read_text(encoding='utf-8'))['books']
    for book in books:
        book['path'] = str((args.manifest.parent / book['path']).resolve())
    all_results = []
    for book in books:
        font, pub, doc, pager, page = [c.c_void_p() for _ in range(5)]
        error, bitmap = Error(), Bitmap()
        library.check('font_open', str(args.font.resolve()).encode(), c.byref(font))
        config = library.layout_config_defaults()
        config.page = Options(args.width, args.height, 48, 24, 1.5, 10)
        parts = c.c_size_t(1)
        fixed = c.c_void_p()
        suffix = Path(book['path']).suffix.lower()
        if suffix == '.pdf':
            options = FixedOptions()
            options.struct_size, options.fallback_font = c.sizeof(options), font
            library.check('fixed_open', book['path'].encode('utf-8'), c.byref(options), c.byref(fixed))
            library.fixed_pages(fixed, c.byref(parts))
            parts.value = 1
        elif suffix == '.epub':
            library.check('publication_open', book['path'].encode('utf-8'), c.byref(pub))
            library.publication_parts(pub, c.byref(parts))
        else:
            library.check('document_open', book['path'].encode('utf-8'), c.byref(doc))
        samples = []
        try:
            for part in range(parts.value):
                if pub:
                    library.check('publication_load', pub, part, c.byref(doc))
                if not fixed:
                    library.check('pager_create', doc, font, c.byref(config), c.byref(pager))
                index = 0
                while len(samples) < 21:
                    perf_reset()
                    cpu_begin = time.thread_time()
                    begin = time.perf_counter()
                    status = library.pager_next(pager, c.byref(page), c.byref(error)) if not fixed else 0
                    layout_ms = (time.perf_counter() - begin) * 1000
                    layout_cpu_ms = (time.thread_time() - cpu_begin) * 1000
                    if status:
                        raise RuntimeError((status,error.message.decode('utf-8',errors='replace')))
                    if not fixed and not page:
                        break
                    before = Perf()
                    perf_read(c.byref(before))
                    cpu_begin = time.thread_time()
                    begin = time.perf_counter()
                    if fixed:
                        library.check('fixed_render', fixed, index, 1.0, None, c.byref(bitmap))
                    else:
                        library.check('render_page_color', page, library.layout_font(page), 0, c.byref(bitmap))
                    raster_ms = (time.perf_counter() - begin) * 1000
                    raster_cpu_ms = (time.thread_time() - cpu_begin) * 1000
                    after = Perf()
                    perf_read(c.byref(after))
                    samples.append(dict(part=part, page=index, layout_ms=layout_ms-before.inline_ms,
                        shape_ms=before.inline_ms, ot_ms=before.shape_ms, raster_ms=raster_ms,
                        total_ms=layout_ms+raster_ms, total_cpu_ms=layout_cpu_ms+raster_cpu_ms,
                        load_ms=after.load_ms, ft_raster_ms=after.ft_raster_ms,
                        shapes=after.shapes, loads=after.loads, rasters=after.rasters,
                        shape_hits=after.shape_hits, glyph_hits=after.glyph_hits,
                        metric_hits=before.metric_hits, metric_misses=before.metric_misses,
                        pixel_sha256=pixel_hash(bitmap)))
                    library.bitmap_free(c.byref(bitmap))
                    library.layout_free(page)
                    page = c.c_void_p()
                    index += 1
                library.pager_free(pager); pager = c.c_void_p()
                library.document_free(doc); doc = c.c_void_p()
                if len(samples) == 21:
                    break
            assert len(samples) == 21, book['id']
            result = dict(id=book['id'], samples=samples[1:], summary={k: stats([s[k] for s in samples[1:]])
                for k in ('layout_ms', 'shape_ms', 'raster_ms', 'total_ms', 'total_cpu_ms', 'load_ms', 'ft_raster_ms')})
            all_results.append(result)
            print(book['id'], round(result['summary']['total_ms']['p95'], 3), flush=True)
        finally:
            for kind, obj in [('layout', page), ('pager', pager), ('document', doc), ('publication', pub), ('fixed', fixed), ('font', font)]:
                getattr(library, kind + '_free')(obj)
    write(args.output, {'dll_sha256': file_hash(args.dll), 'width': args.width, 'height': args.height,
          'phase_detail': traced, 'books': all_results})


def host(args):
    work = args.output.resolve()
    work.mkdir(parents=True, exist_ok=True)
    if (work/'paint.csv').exists() or (work/'d2d.csv').exists():
        raise FileExistsError('Use a fresh output directory for each host run')
    probe_dir=work/'windows'
    probe_dir.mkdir(exist_ok=True)
    probe=(ROOT/'examples/windows/paint_probe.h').read_text(encoding='utf-8')
    (probe_dir/'paint_probe.h').write_text(probe.replace('fflush(trace);',''),encoding='utf-8')
    source = (ROOT / 'examples/reader.c').read_text(encoding='utf-8')
    source=source.replace('shell_color_display(&g.frame);',
        'double theme_start=host_probe_ms();shell_color_display(&g.frame);host_probe_log("theme_ms",host_probe_ms()-theme_start);')
    source=source.replace('if (shell_page_footer(dc, &area)) {',
        'double footer_start=host_probe_ms();int footer=shell_page_footer(dc,&area);host_probe_log("footer_ms",host_probe_ms()-footer_start);if(footer) {')
    source = source.replace('#include "windows/paint_probe.h"', '''#include "windows/paint_probe.h"
typedef struct { double shape_ms, inline_ms, load_ms, ft_raster_ms; unsigned long long shapes, loads, rasters, metric_hits, metric_misses, shape_hits, glyph_hits; } perf_data;
static void perf_host(int reset) {
  HMODULE m=GetModuleHandleW(L"libexreader.dll");
  if(reset) { void (*fn)(void)=(void (*)(void))GetProcAddress(m,"exr_perf_reset");if(fn) fn(); }
  else { void (*fn)(perf_data *)=(void (*)(perf_data *))GetProcAddress(m,"exr_perf_read");
    if(fn) { perf_data p;fn(&p);host_probe_log("shape_ms",p.inline_ms);host_probe_log("ft_load_ms",p.load_ms);host_probe_log("ft_raster_ms",p.ft_raster_ms); } }
}''')
    source = source.replace('host_probe_pager_ms=host_probe_raster_ms=0;', 'host_probe_pager_ms=host_probe_raster_ms=0;perf_host(1);')
    source = source.replace('host_probe_log("stage_anchor_pager_ms",host_probe_pager_ms);', 'perf_host(0);host_probe_log("stage_anchor_pager_ms",host_probe_pager_ms);')
    for name in ('host_update_controls', 'settings_save'):
        marker = f'static void {name}(void) {{'
        assert source.count(marker) == 1
        source = source.replace(marker, f'''static void perf_{name}(void);
static void {name}(void) {{ double t=host_probe_ms();perf_{name}();host_probe_log("{name}_ms",host_probe_ms()-t); }}
static void perf_{name}(void) {{''')
    source = source.replace('static int drive_execute(void) {', '''#include <psapi.h>
static int drive_execute(void) {''')
    source = source.replace('  const char *action = drive_args[0];', '''  const char *action = drive_args[0];
  if(!strcmp(action,"perf_memory")) { PROCESS_MEMORY_COUNTERS_EX m={0};m.cb=sizeof(m);
    GetProcessMemoryInfo(GetCurrentProcess(),(PROCESS_MEMORY_COUNTERS *)&m,sizeof(m));
    host_probe_log("peak_rss",(double)m.PeakWorkingSetSize);host_probe_log("peak_commit",(double)m.PeakPagefileUsage);
    drive_step_finish(1,"memory");return 0; }''')
    generated = work / 'reader.c'
    generated.write_text(source, encoding='utf-8')
    flags = ['-O2', '-I'+str(ROOT/'include'), '-I'+str(ROOT/'examples'), '-I'+str(ROOT/'examples/windows')]
    compile_run = run if not args.host_binary else lambda *a, **kw: None
    compile_run(['gcc', *flags, '-DEXR_READER_WINDOWS_SHELL=1', '-c', generated, '-o', work/'reader.o'])
    components = ['d2d', 'epub']
    if (ROOT/'examples/windows/shell_speech.cpp').exists():
        components.append('speech')
    for name in components:
        cpp = ROOT/f'examples/windows/shell_{name}.cpp'
        if name == 'd2d':
            text = cpp.read_text(encoding='utf-8')
            at = text.index('struct shell_d2d')
            helper = '''#include <stdio.h>
static HRESULT perf_end(ID2D1RenderTarget *target) {
  LARGE_INTEGER a,b,f;QueryPerformanceFrequency(&f);QueryPerformanceCounter(&a);
  HRESULT hr=target->EndDraw();QueryPerformanceCounter(&b);
  wchar_t path[4096];static FILE *trace;
  if(GetEnvironmentVariableW(L"EXR_D2D_TRACE",path,4096)) {
    if(!trace)trace=_wfopen(path,L"ab");
    if(trace) { fprintf(trace,"d2d_end_ms,%.6f,%.6f\\n",1000.0*b.QuadPart/f.QuadPart,1000.0*(b.QuadPart-a.QuadPart)/f.QuadPart); }
  } return hr;
}
'''
            text = re.sub(r'(shell->target|shell->dc_target|s->dc_target)->EndDraw\(\)', r'perf_end(\1)', text)
            text = text[:at] + helper + text[at:]
            cpp = work/'d2d.cpp'
            cpp.write_text(text, encoding='utf-8')
        compile_run(['g++', *flags, '-std=c++17', '-c', cpp, '-o', work/f'{name}.o'])
    compile_run(['g++', work/'reader.o', *[work/f'{name}.o' for name in components], '-o', work/'host.exe',
        '-L'+str(args.build.resolve()), '-lexreader', args.build/'_deps/expat-build/libexpat.a',
        args.build/'_deps/miniz-build/libminiz.a', '-ld2d1', '-ldwrite', '-lgdi32', '-lcomdlg32',
        '-lshell32', '-lole32', '-loleaut32', '-luuid', '-luiautomationcore', '-lpsapi', '-lm', '-ladvapi32'])
    if args.host_binary:
        shutil.copy2(args.host_binary, work/'host.exe')
    shutil.copy2(args.dll, work/'libexreader.dll')
    profile = work/'profile'
    profile.mkdir(exist_ok=True)
    shutil.copy2(args.seed_profile/'library.sqlite', profile/'library.sqlite')
    script = ['delay|0', 'wait_idle', 'shell|on', 'shell_dpi|96', 'shell_font|18',
              'shell_client|1552|928', 'wait_idle', 'open|紅樓夢', 'wait_idle',
              'probe_wait|500', 'probe_mark|keys_begin']
    for _ in range(20):
        script += ['probe_key', 'probe_wait|400', 'wait_idle']
    script += ['probe_mark|keys_end', 'perf_memory', 'shell_measure|layout', 'quit']
    (work/'run.drive').write_text('\n'.join(script)+'\n', encoding='utf-8')
    pin()
    run([work/'host.exe', '--offscreen', '--data', profile, '--font', args.font.resolve(), '--drive', work/'run.drive', '--evidence', work],
        env=dict(os.environ, EXR_PAINT_TRACE=str(work/'paint.csv'), EXR_D2D_TRACE=str(work/'d2d.csv')), creationflags=subprocess.CREATE_NO_WINDOW, timeout=180)
    steps = (work/'drive.log').read_text(encoding='utf-8').splitlines()
    assert all(line.split('\t')[3]=='PASS' for line in steps if line.startswith('STEP\t'))
    rows = [(r[0], float(r[1]), float(r[2])) for r in csv.reader((work/'paint.csv').open())]
    rows += [(r[0], float(r[1]), float(r[2])) for r in csv.reader((work/'d2d.csv').open())]
    rows.sort(key=lambda r:r[1])
    begin = next(r[1] for r in rows if r[0]=='keys_begin')
    end = next(r[1] for r in rows if r[0]=='keys_end')
    inputs = [r for r in rows if r[0]=='input_gen' and begin<r[1]<end]
    assert len(inputs)==20
    samples = []
    for i, inp in enumerate(inputs):
        until = inputs[i+1][1] if i+1<len(inputs) else end
        present = next(r for r in rows if r[0]=='present_gen' and inp[1]<r[1]<until and r[2]!=inp[2])
        events = [r for r in rows if inp[1]<r[1]<=present[1]]
        sums = {k: sum(r[2] for r in events if r[0]==k) for k in
            ('stage_anchor_pager_ms', 'stage_raster_ms', 'compose_ms', 'paint_ms', 'submit_ms', 'pixel_copy_ms', 'shape_ms', 'ft_load_ms', 'ft_raster_ms', 'd2d_end_ms', 'host_update_controls_ms', 'settings_save_ms', 'theme_ms', 'footer_ms')}
        samples.append(dict(total_ms=present[1]-inp[1], **sums))
    layout = json.loads((work/'layout.json').read_text(encoding='utf-8'))
    assert layout['client']==[1552,928] and layout['font']==18
    result = dict(samples=samples, summary={k:stats([s[k] for s in samples]) for k in samples[0]},
        blank_frames=sum(r[2] for r in rows if r[0]=='blank' and begin<r[1]<end),
        peak_rss=next(r[2] for r in rows if r[0]=='peak_rss'),
        peak_commit=next(r[2] for r in rows if r[0]=='peak_commit'),
        trace_flush='per-event in reused binary' if args.host_binary else 'buffered until normal exit',
        geometry={k:layout[k] for k in ('client','page','font','line_height')})
    write(work/'result.json', result)
    print(json.dumps({k:v for k,v in result.items() if k!='samples'}), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['build','sdk','host'])
    p.add_argument('--build', type=Path, default=ROOT/'build/perf')
    p.add_argument('--dll', type=Path, default=ROOT/'build/perf/libexreader.dll')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--width', type=int, default=1552)
    p.add_argument('--height', type=int, default=928)
    p.add_argument('--host-binary', type=Path)
    p.add_argument('--font', type=Path, default=FONT)
    p.add_argument('--manifest', type=Path, default=ROOT/'tools/regress/corpus.json')
    p.add_argument('--seed-profile', type=Path, default=ROOT.parent/'typography-bench-build-20261107/seed-profile')
    a = p.parse_args()
    globals()[a.mode](a)
