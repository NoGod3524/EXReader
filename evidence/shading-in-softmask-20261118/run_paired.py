"""Run the final production A/B with per-page alternation, sequentially."""
from pathlib import Path
import subprocess,sys
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
CASES=[('pdf-large/real-mixed-120.pdf',[1200],7),('pdf-large/image-heavy-100.pdf',[1200],7),('pdf-large/vector-heavy-100.pdf',[1200],7),('pdf-hybrid-real/pptx-20.pdf',[600,1200,2400],41),('pdf-ppt/deck.pdf',[600,1200],41),('pdf-hybrid-real/word-5.pdf',[600,1200],41)]
for fixture,widths,runs in CASES:
    for w in widths:
        subprocess.run([sys.executable,str(HERE/'paired_sweep.py'),str(ROOT/'out/shading-base/libexreader.dll'),str(ROOT/'out/shading-final/libexreader.dll'),str(ROOT/'tests/fixtures'/fixture),str(w),str(runs),str(HERE/'paired'/f'{Path(fixture).stem}-{w}.json')],check=True,cwd=ROOT)
