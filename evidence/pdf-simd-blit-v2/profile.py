#!/usr/bin/env python3
"""Reuse the previous PR's MinGW timer instrumentation for this A/B."""
# SPDX-License-Identifier: MIT
import argparse
import importlib.util
from pathlib import Path
import statistics
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from bench_engine import cpu_busy_percent, cpu_times, wait_idle
from benchmark_pdf_rect import digest, write_json

PRIOR = '3beb466a4440d5ce8ed7afc51c4422ca3fa8ed29'


def measure_kernels(baseline, output):
    prior = subprocess.check_output(['git', 'show', f'{PRIOR}:tools/benchmark_pdf_span_kernels.py'],
                                    cwd=ROOT, encoding='utf-8')
    namespace = {'__name__': 'span_harness'}
    exec(compile(prior, 'benchmark_pdf_span_kernels.py', 'exec'), namespace)
    template = namespace['SOURCE'].replace('samples=7', 'samples=1')
    binaries = {}
    for variant, source_root in [('A', baseline), ('B', ROOT)]:
        source = output / f'kernel-{variant}.c'
        binary = source.with_suffix('.exe')
        source.write_text(template.replace('VECTOR_SOURCE', (source_root / 'src/vector.c').as_posix())
                          .replace('AFFINITY_MASK', '0').replace('PRIORITY_CLASS', '0'), encoding='utf-8')
        subprocess.run(['gcc', '-O3', '-DNDEBUG', '-std=c11', '-I' + str(ROOT / 'src'),
                        '-I' + str(ROOT / 'include'), str(source), str(ROOT / 'src/blend.c'),
                        str(ROOT / 'src/common.c'), str(ROOT / 'src/icc.c'), '-lm', '-o', str(binary)], check=True)
        binaries[variant] = binary
    names = ('opaque_colour', 'alpha_128_opaque_destination', 'alpha_128_constant_clip_128')
    captures = []
    for pair in range(1, 8):
        for variant, binary in binaries.items():
            busy = wait_idle(15, 900)
            if busy is None:
                raise SystemExit(f'Idle gate timed out before kernel pair {pair}, {variant}')
            capture = {'pair': pair, 'variant': variant, 'pre_cpu_percent': busy}
            for line in subprocess.check_output([str(binary)], text=True).splitlines():
                kind, _, ns, _ = line.split()
                capture[names[int(kind)]] = float(ns)
            captures.append(capture)
    result = {'scope': 'Hot-cache ns per visited span pixel', 'span_pixels': 1200,
              'repetitions_per_sample': 20000, 'captures': captures,
              'p50_ns_per_pixel': {variant: {name: statistics.median(
                  r[name] for r in captures if r['variant'] == variant) for name in names}
                  for variant in binaries}}
    write_json(output / 'kernels.json', result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('baseline_source', type=Path)
    parser.add_argument('build', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    source = output / 'profile_pdf_spans.py'
    prior = subprocess.check_output(['git', 'show', f'{PRIOR}:tools/profile_pdf_spans.py'],
                                    cwd=ROOT, encoding='utf-8')
    source.write_text(prior.replace(', set_process_controls', ''), encoding='utf-8')
    spec = importlib.util.spec_from_file_location('profile_pdf_spans', source)
    profile = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(profile)
    baseline = args.baseline_source.resolve()
    libraries = {}
    for variant, source_root in [('A', baseline), ('B', ROOT)]:
        directory = output / variant
        directory.mkdir(exist_ok=True)
        libraries[variant] = profile.build_profile(source_root, args.build.resolve(), directory)
    for relative, name in [('pdf-hybrid-real/pptx-20.pdf', 'profile.json'),
                           ('pdf-ppt/deck.pdf', 'profile-deck.json')]:
        pdf = ROOT / 'tests/fixtures' / relative
        result = {'fixture_sha256': digest(pdf), 'instrumentation_commit': PRIOR,
                  'scope': 'Exclusive ns per output pixel, with instrumentation overhead', 'variants': {}}
        for variant, library in libraries.items():
            busy = wait_idle(15, 900)
            if busy is None:
                raise SystemExit(f'Idle gate timed out before the {variant} {pdf.name} profile')
            start = cpu_times()
            measured = profile.measure(library, pdf, 1200, 5)
            measured.update(library_sha256=digest(library), pre_cpu_percent=busy,
                            capture_cpu_percent=cpu_busy_percent(start, cpu_times()))
            result['variants'][variant] = measured
            write_json(output / name, result)
            print(f'{pdf.name} {variant}: {measured["ns_per_output_pixel"]:.4f} ns/output pixel',
                  flush=True)
    measure_kernels(baseline, output)


if __name__ == '__main__':
    main()
