"""Final production A/B (main vs this branch) with per-page alternation, sequentially."""
from pathlib import Path
import subprocess, sys
HERE = Path(__file__).resolve().parent; ROOT = HERE.parents[1]
A, B = (ROOT / 'build/ab' / t / 'libexreader.dll' for t in ('A', 'final'))
CASES = [('pdf-large/real-mixed-120.pdf', [1200], 7), ('pdf-large/image-heavy-100.pdf', [1200], 7),
         ('pdf-large/vector-heavy-100.pdf', [1200], 7), ('pdf-hybrid-real/pptx-20.pdf', [600, 1200, 2400], 41),
         ('pdf-ppt/deck.pdf', [600, 1200], 41), ('pdf-hybrid-real/word-5.pdf', [600, 1200], 41)]
for fixture, widths, runs in CASES:
    for w in widths:
        out = HERE / 'paired' / f'{Path(fixture).stem}-{w}.json'
        if out.exists():
            continue
        subprocess.run([sys.executable, '-X', 'utf8', str(HERE / 'paired_sweep.py'), str(A), str(B),
                        str(ROOT / 'tests/fixtures' / fixture), str(w), str(runs), str(out)], check=True, cwd=ROOT)
