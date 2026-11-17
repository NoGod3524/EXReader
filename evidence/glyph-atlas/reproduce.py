#!/usr/bin/env python3
"""Repeat the glyph atlas oracle with the retained baseline/Release DLLs."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]


def run(command, log):
    with log.open('w', encoding='utf-8') as handle:
        subprocess.run([str(x) for x in command], cwd=ROOT, stdout=handle,
                       stderr=subprocess.STDOUT, check=True)


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def summarize(output):
    report = {'baseline_commit': '2b24c3ea87144e25b371d227340cd8bc80251bb1',
              'benchmark': 'tools/benchmark_pdf_rect.py', 'runs_per_capture': 5,
              'timing_scope': 'exr_fixed_render wall time; background load uncontrolled',
              'pairs': [], 'protected_sources': {}}
    for label, prefix in [('initial', ''), ('repeat', 'repeat-')]:
        if not (output / (prefix + 'before') / 'summary.json').exists():
            continue
        before = read(output / (prefix + 'before') / 'summary.json')
        after = read(output / (prefix + 'after') / 'summary.json')
        diff = read(output / (prefix + 'comparison') / 'diff.json')
        assert diff['identical'] and diff['different_pixels'] == 0
        assert all(p['max_channel_delta'] == p['rgba_rmse'] == 0 for p in diff['pages'])
        pair = {'label': label, 'before_library_sha256': before['library_sha256'],
                'after_library_sha256': after['library_sha256'],
                'compared_pixels': diff['compared_pixels'], 'different_pixels': 0,
                'max_channel_delta': 0, 'rgba_rmse': 0, 'results': []}
        for width in before['widths']:
            a, b = before['results'][str(width)], after['results'][str(width)]
            dimensions = {tuple(p['dimensions']) for p in a['pages'] + b['pages']}
            assert len(dimensions) == 1
            w, h = dimensions.pop()
            pair['results'].append({'width': width, 'dimensions': [w, h],
                'before_render_p50_ms': a['p50_ms'], 'after_render_p50_ms': b['p50_ms'],
                'before_open_p50_ms': a['open_ms'], 'after_open_p50_ms': b['open_ms'],
                'render_change_percent': (b['p50_ms'] / a['p50_ms'] - 1) * 100,
                'before_render_ns_per_output_pixel': a['p50_ms'] * 1e6 / (w * h),
                'after_render_ns_per_output_pixel': b['p50_ms'] * 1e6 / (w * h)})
        report['pairs'].append(pair)
    for name in ['src/vector.c', 'src/blend.c']:
        current = (ROOT / name).read_bytes()
        original = subprocess.check_output(['git', 'show', 'HEAD:' + name], cwd=ROOT)
        assert current == original
        report['protected_sources'][name] = {'unchanged_from_HEAD': True,
            'sha256': hashlib.sha256(current).hexdigest()}
    suite = ET.parse(output / 'ctest.xml').getroot()
    report['ctest'] = {k: int(suite.get(k, '0')) for k in ['tests', 'failures', 'errors', 'skipped']}
    assert report['ctest']['failures'] == report['ctest']['errors'] == 0
    report['stress'] = read(output / 'stress.json')
    report['fixture_atlas_stats'] = [json.loads(line) for line in
        (output / 'fixture-stats.jsonl').read_text(encoding='utf-8-sig').splitlines() if line]
    report['source_sha256'] = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in [
        'CMakeLists.txt', 'src/canvas.c', 'src/canvas_internal.h', 'src/canvas_glyph.inc',
        'src/glyph_atlas_internal.h', 'src/pdf_paint.c', 'src/pdf_objects.c',
        'src/pdf_font.c', 'src/pdf_internal.h', 'tests/test_glyph_atlas.c', 'tests/test_pdf_glyph_atlas.c']}
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'evidence/glyph-atlas-reproduced')
    parser.add_argument('--before-library', type=Path, default=ROOT / 'build/baseline/libexreader.dll')
    parser.add_argument('--after-library', type=Path, default=ROOT / 'build/perf/libexreader.dll')
    parser.add_argument('--summarize-only', action='store_true')
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT):
        parser.error('Output must stay inside this workspace')
    output.mkdir(parents=True, exist_ok=True)
    if not args.summarize_only:
        for label, library in [('before', args.before_library), ('after', args.after_library)]:
            run([sys.executable, '-X', 'utf8', ROOT / 'tools/benchmark_pdf_rect.py', 'capture',
                 '--library', library.resolve(), '--input', ROOT / 'tests/fixtures/pdf-hybrid-real/pptx-20.pdf',
                 '--expect-pages', 20, '--output', output / label,
                 '--widths', 600, 1200, 2400, '--runs', 5], output / (label + '-capture.log'))
        run([sys.executable, '-X', 'utf8', ROOT / 'tools/benchmark_pdf_rect.py', 'compare',
             '--before', output / 'before', '--after', output / 'after',
             '--output', output / 'comparison'], output / 'comparison.log')
        run(['ctest', '--test-dir', ROOT / 'build/perf', '--output-on-failure', '--parallel', 6,
             '--output-junit', output / 'ctest.xml'], output / 'ctest.log')
        probe = ROOT / 'build/perf/exreader-pdf-glyph-atlas-test.exe'
        run([probe, ROOT / 'tests/fixtures'], output / 'stress.json')
        run([probe, ROOT / 'tests/fixtures', ROOT / 'tests/fixtures/pdf-hybrid-real/pptx-20.pdf'],
            output / 'fixture-stats.jsonl')
    summarize(output)


if __name__ == '__main__':
    main()
