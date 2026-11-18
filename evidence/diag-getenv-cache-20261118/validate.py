"""Check concurrent initialization, process lifetime, and all ablation modes."""
import ctypes as c
import json
import os
from pathlib import Path
import re
import subprocess
import sys

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from bench_firstscreen import run_child


def atomic_check():
    header = (ROOT / 'src/pdf_internal.h').read_text()
    enum = re.search(r'typedef enum \{\s*EXR_DIAG_NONE.*?\} exr_pdf_diag_mode;', header, re.S).group()
    source = (ROOT / 'src/pdf_objects.c').read_text()
    function = source[source.index('int exr_pdf_diag_skip('):source.index('\n#define PDF_MAX_OBJECTS')]
    # Compile the exact production enum/function, substituting only counted getenv.
    harness = r'''
#include <assert.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <windows.h>
static atomic_int calls,started;
static int expected;
static const char *counted_getenv(const char *name) {
  atomic_fetch_add(&calls,1); Sleep(10); return getenv(name);
}
#define getenv counted_getenv
'''+enum+'\n'+function+r'''
#undef getenv
static DWORD WINAPI worker(void *unused) {
  (void)unused;
  while(!atomic_load(&started)) { }
  for(int n=0;n<10000;n++) {
    exr_pdf_diag_mode mode=(exr_pdf_diag_mode)(n%9);
    assert(exr_pdf_diag_skip(mode)==(expected==(int)mode));
  }
  return 0;
}
int main(int argc,char **argv) {
  HANDLE threads[32]; assert(argc==2);expected=atoi(argv[1]);
  for(int n=0;n<32;n++) { threads[n]=CreateThread(NULL,0,worker,NULL,0,NULL);assert(threads[n]); }
  atomic_store(&started,1);
  assert(WaitForMultipleObjects(32,threads,TRUE,INFINITE)==WAIT_OBJECT_0);
  for(int n=0;n<32;n++) CloseHandle(threads[n]);
  assert(atomic_load(&calls)==1);
  assert(!_putenv_s("EXR_ATTRIBUTION_SKIP","changed-after-first-use"));
  assert(exr_pdf_diag_skip((exr_pdf_diag_mode)expected));
  assert(atomic_load(&calls)==1);
  printf("threads=32 checks=320001 getenv_calls=%d expected=%d\n",atomic_load(&calls),expected);
  return 0;
}
'''
    path = ROOT / 'build/diag/atomic-check.c'
    path.write_text(harness)
    exe = path.with_suffix('.exe')
    subprocess.run(['gcc', '-O3', '-std=c11', '-Wall', '-Wextra', '-Wpedantic', '-Werror', str(path), '-o', str(exe)], check=True)
    modes = [None, '', 'image', 'image-paint', 'image-decode', 'path', 'glyph', 'group', 'shading', 'softmask', 'invalid']
    known = ['', 'image', 'image-paint', 'image-decode', 'path', 'glyph', 'group', 'shading', 'softmask']
    result = []
    for mode in modes:
        env = dict(os.environ)
        env.pop('EXR_ATTRIBUTION_SKIP', None)
        if mode is not None:
            env['EXR_ATTRIBUTION_SKIP'] = mode
        expected = known.index(mode) if mode in known else 0
        p = subprocess.run([str(exe), str(expected)], env=env, capture_output=True, text=True, check=True)
        result.append({'mode': mode, 'result': p.stdout.strip()})
    return result


def lifecycle(tag):
    import hashlib
    sys.path.insert(0, str(OUT.parent / 'image-paint-path-20261118'))
    from verify_pixels import load, Bitmap, Error
    lib, directory = load(ROOT / f'build/diag/{tag}/libexreader.dll')
    doc, count, error = c.c_void_p(), c.c_size_t(), Error()
    assert not lib.exr_fixed_open(os.fsencode(ROOT / 'tests/fixtures/pdf-large/real-mixed-120.pdf'), None, c.byref(doc), c.byref(error))
    pages = lib.exr_fixed_pages(doc, c.byref(count))
    g = pages[0].geometry
    scale = 1200/((g.bounds[2]-g.bounds[0])*g.unit_scale)
    hashes = []
    for mode in ['', 'image', 'glyph']:
        os.putenv('EXR_ATTRIBUTION_SKIP', mode)
        bitmap = Bitmap()
        assert not lib.exr_fixed_render(doc, 0, scale, None, c.byref(bitmap), c.byref(error))
        h = hashlib.sha256()
        for y in range(bitmap.height):
            h.update(c.string_at(bitmap.pixels+y*bitmap.stride, bitmap.width*4))
        hashes.append(h.hexdigest())
        lib.exr_bitmap_free(c.byref(bitmap))
    lib.exr_fixed_free(doc)
    directory.close()
    assert (len(set(hashes)) == 1) == (tag == 'B')
    print(json.dumps(hashes))


if __name__ == '__main__':
    if len(sys.argv) > 1:
        lifecycle(sys.argv[1])
    else:
        result = {'atomic': atomic_check(), 'modes': {}, 'lifecycle': {}}
        pdf = ROOT / 'tests/fixtures/pdf-large/real-mixed-120.pdf'
        for mode in ['', 'image', 'image-paint', 'image-decode', 'path', 'glyph', 'group', 'shading', 'softmask', 'invalid']:
            env = dict(os.environ, EXR_ATTRIBUTION_SKIP=mode)
            rows = {tag: run_child(ROOT / f'build/diag/{tag}/libexreader.dll', pdf, 1200, env=env) for tag in 'AB'}
            assert rows['A']['rgba_sha256'] == rows['B']['rgba_sha256'], mode
            result['modes'][mode] = {tag: row['rgba_sha256'] for tag, row in rows.items()}
        assert result['modes']['image']['B'] != result['modes']['']['B']
        group_pdf = ROOT / 'tests/fixtures/pdf-blend/alpha-source-blend-opacity-group-Normal.pdf'
        result['group'] = {}
        for mode in ['', 'group']:
            rows = {tag: run_child(ROOT / f'build/diag/{tag}/libexreader.dll', group_pdf, 64,
                                   env=dict(os.environ, EXR_ATTRIBUTION_SKIP=mode)) for tag in 'AB'}
            assert rows['A']['rgba_sha256'] == rows['B']['rgba_sha256']
            result['group'][mode] = rows['B']['rgba_sha256']
        assert result['group'][''] != result['group']['group']
        group_trace = subprocess.run([sys.executable, 'tools/bench_firstscreen.py', 'child',
                                     '--library', str(ROOT / 'build/diag/count-A/libexreader.dll'),
                                     '--input', str(group_pdf), '--width', '64', '--warm', '0', '--page', '1'],
                                    capture_output=True, text=True, check=True)
        (OUT / 'group-count-trace.txt').write_text(group_trace.stderr)
        result['group']['baseline_group_lookups'] = group_trace.stderr.count('GETENV paint:group\n')
        assert result['group']['baseline_group_lookups'] > 0
        for tag in 'AB':
            p = subprocess.run([sys.executable, __file__, tag], capture_output=True, text=True, check=True)
            result['lifecycle'][tag] = json.loads(p.stdout)
        (OUT / 'validation.json').write_text(json.dumps(result, indent=2) + '\n')
        print('All modes match baseline; image changes output; lifetime and 32-thread once checks passed.')
