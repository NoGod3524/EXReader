"""Run after run_measurements.py exits; all checks are serial."""
import json
import os
from pathlib import Path
import subprocess
import sys

root = Path('out/deck-decode')
evidence = Path('evidence/pdf-deck-decode-20261117')
python = [sys.executable, '-X', 'utf8']
pptx = 'tests/fixtures/pdf-hybrid-real/pptx-20.pdf'
for name, library in [('baseline', 'out/deck-decode/before/libexreader.dll'),
                      ('candidate', 'build/perf/libexreader.dll')]:
    output = root / f'pptx-confirm-{name}' / 'bench.json'
    subprocess.run(python + [str(evidence / 'bench_engine.py'), '--library', library,
                   '--input', pptx, '--expect-pages', '20', '--widths', '1200',
                   '--runs', '12', '--repeat', '2', '--idle-threshold', '15',
                   '--repo', '.', '--out', str(output)], check=True)
    report = json.loads(output.read_text())
    if report['idle_cpu_percent'] < 0 or report['widths']['1200']['spread_percent'] > 10:
        raise SystemExit(f'Unstable confirmation; retain and inspect {output}')
subprocess.run(python + ['tools/probe_pdf_open.py', '--baseline',
               'out/deck-decode/before/libexreader.dll', '--candidate',
               'build/perf/libexreader.dll', '--input', pptx, '--samples', '1000',
               '--render-width', '1200', '--out', str(root / 'pptx-paired.json')], check=True)
with (root / 'profile-final-1200.jsonl').open('w') as output:
    subprocess.run(['build/perf/exreader-pdf-image-profile.exe',
                   'tests/fixtures/pdf-ppt/deck.pdf', '1200', '6'], stdout=output,
                   env=dict(os.environ, EXR_PDF_IMAGE_PROFILE='1'), check=True)
with (root / 'ctest-final.txt').open('w') as output:
    subprocess.run(['ctest', '--test-dir', 'build/perf', '--output-on-failure',
                    '--parallel', '6'], stdout=output, stderr=subprocess.STDOUT, check=True)
subprocess.run(python + ['tools/probe_pdf_open.py', '--baseline',
               'out/deck-decode/before/libexreader.dll', '--candidate',
               'build/perf/libexreader.dll', '--input', 'tests/fixtures/pdf-ppt/deck.pdf',
               pptx, '--samples', '10000', '--out', str(root / 'open-confirm-10000.json')], check=True)
for name, widths in [('deck', ['600', '1200']), ('pptx', ['600', '1200', '2400'])]:
    subprocess.run(python + [str(evidence / 'verify_pixels.py'), '--before',
                   str(root / f'production-baseline-{name}'), '--after',
                   str(root / f'production-final-v5-{name}'), '--widths', *widths,
                   '--out', str(evidence / f'{name}-pixels.json')], check=True)
