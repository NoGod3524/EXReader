"""Untimed event lookup census, one process across all fixtures and two sweeps."""
import collections
import ctypes as c
import json
import os
from pathlib import Path
import subprocess
import sys

OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(OUT.parent / 'image-paint-path-20261118'))
from verify_pixels import load, Bitmap, Error

CASES = {'deck': 'pdf-ppt/deck', 'word-5': 'pdf-hybrid-real/word-5',
         'pptx-20': 'pdf-hybrid-real/pptx-20', 'real-mixed-120': 'pdf-large/real-mixed-120',
         'image-heavy-100': 'pdf-large/image-heavy-100'}


def child(dll):
    lib, directory = load(dll)
    error = Error()
    for name, fixture in CASES.items():
        os.write(2, f'PAGE {name} open 0\n'.encode())
        doc, count = c.c_void_p(), c.c_size_t()
        assert not lib.exr_fixed_open(os.fsencode(f'tests/fixtures/{fixture}.pdf'), None, c.byref(doc), c.byref(error))
        pages = lib.exr_fixed_pages(doc, c.byref(count))
        for sweep in ['cold', 'warm']:
            for i in range(1 if name == 'real-mixed-120' else count.value):
                os.write(2, f'PAGE {name} {sweep} {i+1}\n'.encode())
                g = pages[i].geometry
                native = g.bounds[3]-g.bounds[1] if g.rotation % 180 else g.bounds[2]-g.bounds[0]
                bitmap = Bitmap()
                assert not lib.exr_fixed_render(doc, i, 1200/(native*g.unit_scale), None, c.byref(bitmap), c.byref(error)), error.message
                lib.exr_bitmap_free(c.byref(bitmap))
        lib.exr_fixed_free(doc)
    directory.close()


if __name__ == '__main__':
    if sys.argv[1] == 'child':
        child(sys.argv[2])
    else:
        tag = sys.argv[1]
        proc = subprocess.run([sys.executable, __file__, 'child', f'build/diag/{tag}/libexreader.dll'], capture_output=True, text=True, check=True)
        (OUT / f'{tag}-trace.txt').write_text(proc.stderr)
        rows = []
        for line in proc.stderr.splitlines():
            if line.startswith('PAGE '):
                _, fixture, sweep, page = line.split()
                rows.append({'fixture': fixture, 'sweep': sweep, 'page': int(page), 'sites': collections.Counter()})
            elif line.startswith('GETENV '):
                rows[-1]['sites'][line.split()[1]] += 1
        for row in rows:
            row['getenv_calls'] = sum(row['sites'].values())
            row['estimated_lookup_ms_at_1_08_us'] = row['getenv_calls'] * 0.00108
        (OUT / f'{tag}.json').write_text(json.dumps(rows, indent=2) + '\n')
        print(tag, 'total', sum(row['getenv_calls'] for row in rows))
        for name in CASES:
            first = next(row for row in rows if row['fixture'] == name and row['sweep'] == 'cold')
            print(name, first)
