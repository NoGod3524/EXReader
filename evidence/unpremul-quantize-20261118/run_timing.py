"""Run production A/B timing serially (A=baseline, B=reciprocal quantize); failed idle gates produce no samples."""
import sys
import time
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
import bench_engine
import bench_real_doc

E = 'evidence/unpremul-quantize-20261118/'
A = os.environ.get('EXR_BENCH_A', 'build/diag/A/libexreader.dll')
B = os.environ.get('EXR_BENCH_B', 'build/diag/B/libexreader.dll')
original_wait = bench_engine.wait_idle


def wait_idle(threshold, timeout):
    last = time.monotonic()
    while True:
        value = original_wait(threshold, min(timeout, 1))
        if value is not None:
            return value
        if time.monotonic() - last >= 60:
            print('CPU idle gate closed; retrying without a sample', flush=True)
            last = time.monotonic()


bench_engine.wait_idle = wait_idle
bench_real_doc.wait_idle = wait_idle


def run(module, args):
    sys.argv = [module.__file__] + args
    module.main()


def main():
    phase = sys.argv[1]
    if True:
        cases = {
            'heavy': ('tests/fixtures/pdf-large/image-heavy-100.pdf', [1200], 3),
            'mixed': ('tests/fixtures/pdf-large/real-mixed-120.pdf', [1200], 3),
            'vector': ('tests/fixtures/pdf-large/vector-heavy-100.pdf', [1200], 3),
            'pptx': ('tests/fixtures/pdf-hybrid-real/pptx-20.pdf', [600, 1200, 2400], 20),
            'deck': ('tests/fixtures/pdf-ppt/deck.pdf', [1200], 20),
            'word': ('tests/fixtures/pdf-hybrid-real/word-5.pdf', [600, 1200], 20),
        }
        pdf, widths, runs = cases[phase]
        run(bench_real_doc, ['--library-a', A, '--library-b', B, '--input', pdf,
            '--widths'] + [str(w) for w in widths] + ['--runs', str(runs), '--repeat', '3',
            '--out', E + f'timing-{phase}-ab.json'])


if __name__ == '__main__':
    phases = sys.argv[1:]
    for phase in phases:
        print('Running ' + phase, flush=True)
        sys.argv = [__file__, phase]
        main()
