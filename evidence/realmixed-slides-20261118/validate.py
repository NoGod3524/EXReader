# SPDX-License-Identifier: MIT
"""Run the matched native validation matrix with the #264 parity runner."""
import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURES = HERE.parents[1] / 'tests/fixtures'
RUNNERS = HERE.parent / 'slides-gradient-20261118'
sys.path.insert(0, str(RUNNERS))
import verify  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('main', type=Path)
    parser.add_argument('candidate', type=Path)
    parser.add_argument('--raw', type=Path, default=HERE / 'raw')
    args = parser.parse_args()
    a, b = [str(path.resolve()) for path in (args.main, args.candidate)]
    raw = args.raw.resolve()
    raw.mkdir(parents=True, exist_ok=True)
    slide_pdf = FIXTURES / 'pdf-large/real-mixed-120.pdf'
    subprocess.run([sys.executable, '-B', '-u', str(RUNNERS / 'paired_sweep.py'), a, b,
                    str(slide_pdf), '1200', '11', str(raw / 'production-slides-1200.json'),
                    '--pages', '21'], check=True)
    for pdf, width, _ in verify.LARGE + verify.SMALL:
        name = Path(pdf).stem
        runs = {('real-mixed-120', 1200): 11, ('pptx-20', 600): 15, ('pptx-20', 1200): 15,
                ('deck', 1200): 15, ('word-5', 1200): 15}.get((name, width), 0)
        capture = raw / f'production-{name}-{width}.json'
        subprocess.run([sys.executable, '-B', '-u', str(RUNNERS / 'paired_sweep.py'), a, b,
                        str(FIXTURES / pdf), str(width), str(runs), str(capture)], check=True)
    # The reused RSS script resolves its output directory from its own location.
    verify.HERE = raw
    verify.rss(a, b)


if __name__ == '__main__':
    main()
