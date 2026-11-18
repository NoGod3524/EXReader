"""Sequential independent-process AB/BA trials using the existing benchmark."""
from pathlib import Path
import os
import subprocess
import sys

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]

if __name__ == '__main__':
    assert not any(k in os.environ for k in ['EXR_ATTRIBUTION_SKIP', 'EXR_ATTRIBUTION_TRACE', 'EXR_PDF_IMAGE_CACHE_BYTES', 'EXR_PDF_IMAGE_PROFILE'])
    for name, fixture, runs, pairs in [
        ('deck', 'pdf-ppt/deck', 20, 15),
        ('word', 'pdf-hybrid-real/word-5', 20, 15),
        ('pptx', 'pdf-hybrid-real/pptx-20', 20, 15),
        ('heavy', 'pdf-large/image-heavy-100', 3, 7),
    ]:
        subprocess.run([sys.executable, '-X', 'utf8', 'tools/bench_real_doc.py',
                        '--library-a', 'build/diag/A/libexreader.dll',
                        '--library-b', 'build/diag/B/libexreader.dll',
                        '--input', f'tests/fixtures/{fixture}.pdf', '--widths', '1200',
                        '--runs', str(runs), '--repeat', str(pairs),
                        '--idle-threshold', '15', '--idle-timeout', '60',
                        '--out', str(OUT / f'{name}-ab.json')], cwd=ROOT, check=True)
