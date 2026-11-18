"""Build the baseline (A), candidate (B) or untimed count Release DLL.

The count build patches a temporary copy of src/affine_image.c so image_rgb
tallies reciprocal-path and quotient-fallback pixels and prints them at
process exit. It is never used for timing; the source is restored afterwards.
"""
from pathlib import Path
import hashlib
import json
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
BUILD = ROOT / 'build/perf'


def build(tag):
    subprocess.run(['cmake', '--build', str(BUILD), '--target', 'exreader', '-j', '4'], check=True)
    dest = ROOT / 'build/diag' / tag / 'libexreader.dll'
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(BUILD / 'libexreader.dll', dest)
    meta = {'tag': tag, 'dll_sha256': hashlib.sha256(dest.read_bytes()).hexdigest(),
            'sources': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in [ROOT / 'src/affine_image.c']}}
    (OUT / f'build-{tag}.json').write_text(json.dumps(meta, indent=2) + '\n')


if __name__ == '__main__':
    tag = sys.argv[1]
    if not BUILD.exists():
        cache = (ROOT.parent / 'EXReader-mainverify/build/perf/CMakeCache.txt').read_text()
        deps = re.findall(r'^(FETCHCONTENT_SOURCE_DIR_\w+):PATH=(.*)$', cache, re.M)
        subprocess.run(['cmake', '-S', str(ROOT), '-B', str(BUILD), '-G', 'Ninja',
                        '-DCMAKE_BUILD_TYPE=Release', '-DEXR_BUILD_TOOLS=OFF',
                        '-DEXR_BUILD_JNI=OFF', '-DEXR_ENABLE_IMAGE_AVIF=OFF'] +
                       [f'-D{k}={v}' for k, v in deps], check=True)
    if tag == 'count':
        path = ROOT / 'src/affine_image.c'
        saved = path.read_bytes()
        try:
            text = saved.decode('utf-8')
            guard = '  if((_mm_movemask_pd(ok)&(_mm_movemask_pd(okb)|2))==3)\n'
            assert text.count(guard) == 1
            text = text.replace(guard, '  unpremul_count[(_mm_movemask_pd(ok)&(_mm_movemask_pd(okb)|2))==3]++;\n' + guard)
            counters = ('#include <stdio.h>\nstatic unsigned long long unpremul_count[2];\n'
                        '__attribute__((destructor)) static void unpremul_report(void) {\n'
                        '  fprintf(stderr,"UNPREMUL fast=%llu fallback=%llu\\n",unpremul_count[1],unpremul_count[0]);\n}\n')
            anchor = '/* Straight RGB of a premultiplied sum'
            text = text.replace(anchor, counters + anchor)
            path.write_bytes(text.encode('utf-8'))
            build(tag)
        finally:
            path.write_bytes(saved)
    else:
        build(tag)
