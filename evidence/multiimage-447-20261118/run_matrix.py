# SPDX-License-Identifier: MIT
"""Run the production fixture matrix and the live-output attribution probes."""
import argparse
import os
import subprocess
import sys
from pathlib import Path

from capture import ROOT

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('baseline', type=Path)
    parser.add_argument('candidate', type=Path)
    parser.add_argument('--probe', type=Path)
    parser.add_argument('--pdfjs-deps', type=Path)
    parser.add_argument('--core', type=int)
    args = parser.parse_args()
    fixture = ROOT / 'tests/fixtures'
    cases = [
        ('production-heavy', fixture/'pdf-large/image-heavy-100.pdf', 1200, 7, 1),
        ('production-pptx', fixture/'pdf-hybrid-real/pptx-20.pdf', 600, 15, 5),
        ('production-pptx', fixture/'pdf-hybrid-real/pptx-20.pdf', 1200, 15, 5),
        ('production-deck', fixture/'pdf-ppt/deck.pdf', 1200, 15, 5),
        ('production-word', fixture/'pdf-hybrid-real/word-5.pdf', 1200, 15, 5),
    ]
    env = os.environ | {'PYTHONDONTWRITEBYTECODE': '1'}
    directory = HERE if args.core is None else HERE/f'core-{args.core}'
    directory.mkdir(exist_ok=True)
    pinned = () if args.core is None else ('--core', args.core)

    def run(script, *opts):
        subprocess.run([sys.executable, str(HERE/script), *map(str, opts)],
                       cwd=ROOT, env=env, check=True)

    for name, pdf, width, runs, batch in cases:
        out = directory/f'{name}-{width}.json.gz'
        if not out.exists():
            run('capture.py', args.baseline, out, '--b', args.candidate, '--pdf', pdf,
                '--width', width, '--runs', runs, '--batch', batch, *pinned)
    if args.probe:
        for detail, name in enumerate(('diagnostic-scopes', 'diagnostic-sampled')):
            out = directory/f'{name}.json.gz'
            if not out.exists():
                run('capture.py', args.baseline, out, '--b', args.probe, '--detail', detail,
                    '--pages', 71, 100, '--runs', 5, *pinned)
    if args.pdfjs_deps:
        out = directory/'diagnostic-pdfjs.json.gz'
        if not out.exists():
            run('pdfjs_scopes.py', args.pdfjs_deps, out, *pinned)


if __name__ == '__main__':
    main()
