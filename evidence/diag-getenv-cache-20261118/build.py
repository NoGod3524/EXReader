"""Build baseline, count-only, or candidate DLLs; never time the count build."""
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
                        for p in (ROOT / 'src').glob('pdf*.[ch]')}}
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
    if tag.startswith('count'):
        files = ['pdf_paint.c', 'pdf_content.c', 'pdf_image.c', 'pdf_objects.c']
        saved = {ROOT / 'src' / f: (ROOT / 'src' / f).read_bytes() for f in files}
        try:
            for p in saved:
                s = p.read_text()
                # Record every actual toggle lookup, with its owning function.
                trace = '(fprintf(stderr,"GETENV %s\\n",__func__),getenv("EXR_ATTRIBUTION_SKIP"))'
                if p.name == 'pdf_paint.c':
                    trace = '(fprintf(stderr,"GETENV paint:%s\\n",name),getenv("EXR_ATTRIBUTION_SKIP"))'
                s = s.replace('getenv("EXR_ATTRIBUTION_SKIP")', trace)
                if s != p.read_text():
                    p.write_text('#include <stdio.h>\n' + s if p.name == 'pdf_objects.c' else s)
            build(tag)
        finally:
            for p, data in saved.items():
                p.write_bytes(data)
    else:
        build(tag)
