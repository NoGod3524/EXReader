import sys
from pathlib import Path

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / 'tools'))
import bench_real_doc as bench

fixtures = [
    ('pdf-large/real-mixed-120.pdf', 120, [1200], 5, 3),
    ('pdf-large/image-heavy-100.pdf', 100, [1200], 5, 3),
    ('pdf-large/vector-heavy-100.pdf', 100, [1200], 5, 3),
    ('pdf-hybrid-real/pptx-20.pdf', 20, [600, 1200, 2400], 15, 3),
    ('pdf-ppt/deck.pdf', 15, [600, 1200], 15, 3),
    ('pdf-hybrid-real/word-5.pdf', 5, [600, 1200], 15, 3),
]
a, b, out = map(Path, sys.argv[1:4])
out.mkdir(exist_ok=True, parents=True)
original = bench.run_child_gated

def gated(*args):
    while True:
        try:
            return original(*args)
        except SystemExit as failure:
            if not str(failure).startswith('CPU did not fall to '):
                raise
            print(f'{failure}. Retrying same arm.', flush=True)

bench.run_child_gated = gated
selected = set(sys.argv[4:])
for fixture, count, widths, runs, repeats in fixtures:
    if selected and Path(fixture).stem not in selected:
        continue
    print(fixture, flush=True)
    sys.argv[:] = ['bench_real_doc', '--library-a', str(a), '--library-b', str(b),
                   '--input', str(root/'tests/fixtures'/fixture), '--expect-pages', str(count),
                   '--widths', *map(str,widths), '--runs', str(runs), '--repeat', str(repeats),
                   '--idle-timeout', '45', '--out', str(out / (Path(fixture).stem+'.json'))]
    assert bench.main() == 0
