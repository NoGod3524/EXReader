# SPDX-License-Identifier: MIT
"""Run the parity and timing matrix or the fresh-process RSS checks."""
import json
import os
import subprocess
import sys
from pathlib import Path
from paired_sweep import digest_file

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FIXTURES = ROOT / 'tests/fixtures'
LARGE = [(f'pdf-large/{name}.pdf', 1200, n) for name, n in
         [('image-heavy-100', 100), ('real-mixed-120', 120), ('vector-heavy-100', 100)]]
SMALL = [('pdf-hybrid-real/pptx-20.pdf', w, 20) for w in (600,1200,2400)]
SMALL += [('pdf-ppt/deck.pdf', w, 15) for w in (600,1200)]
SMALL += [('pdf-hybrid-real/word-5.pdf', w, 5) for w in (600,1200)]

def paired(a, b):
    builds = {f'{tag}_sha256': digest_file(Path(dll)) for tag, dll in zip('ab', (a, b))}
    for pdf, width, pages in LARGE + SMALL:
        out = HERE / 'paired' / f'{Path(pdf).stem}-{width}.json'
        runs = 0
        if 'image-heavy-100' in pdf:
            runs = 7
        elif pages <= 20 and (width == 1200 or (width == 600 and pages == 20)):
            runs = 15
        if out.exists():
            prior = json.loads(out.read_text())
            if (prior['runs'] == runs and prior['differing_pixels'] == 0
                and prior['pdf_sha256'] == digest_file(FIXTURES / pdf)
                and all(prior[key] == sha for key, sha in builds.items())):
                continue
        cmd = [sys.executable, '-u', str(HERE / 'paired_sweep.py'), a, b,
               str(FIXTURES / pdf), str(width), str(runs), str(out)]
        subprocess.run(cmd, check=True)

def rss(a, b):
    directory = ROOT / 'build' / 'rss'
    results = {}
    for pdf, width, pages in LARGE:
        fixture = Path(pdf).stem
        results[fixture] = []
        for order in ('AB', 'BA', 'AB'):
            row = {}
            for tag in order:
                dll = a if tag == 'A' else b
                out = directory / f'{fixture}-{len(results[fixture])}-{tag}.json'
                cmd = [sys.executable, str(ROOT / 'tools/bench_real_doc.py'), '--library', dll,
                       '--input', str(FIXTURES / pdf), '--expect-pages', str(pages),
                       '--child-width', str(width), '--runs', '1', '--child-out', str(out)]
                subprocess.run(cmd, check=True)
                row[tag] = {'peak_working_set_bytes': json.loads(out.read_text())['peak_rss_bytes']}
            results[fixture].append(row)
            print(fixture, order, row, flush=True)
    (HERE / 'rss.json').write_text(json.dumps(
        {'dll_sha256':{tag:digest_file(Path(dll)) for tag,dll in zip('AB',(a,b))},
         'working_sets':results},indent=2)+'\n')

if __name__ == '__main__':
    mode, a, b = sys.argv[1:]
    for name in tuple(os.environ):
        if name.startswith('EXR_'):
            del os.environ[name]
    {'paired': paired, 'rss': rss}[mode](str(Path(a).resolve()), str(Path(b).resolve()))
