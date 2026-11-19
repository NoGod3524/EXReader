# SPDX-License-Identifier: MIT
"""Run the matched native validation matrix with the #264 parity runner."""
import argparse
import json
import os
import subprocess
import sys
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
FIXTURES = HERE.parents[1] / 'tests/fixtures'
RUNNERS = HERE.parent / 'slides-gradient-20261118'
sys.path.insert(0, str(RUNNERS))
import paired_sweep  # noqa: E402
import verify  # noqa: E402
from ablate import gate  # noqa: E402


def chinese(a, b, pdf, out):
    for name in tuple(os.environ):
        if name.startswith('EXR_'):
            del os.environ[name]
    page_indices = (117, 119)
    options = SimpleNamespace(a=Path(a), b=Path(b), pdf=pdf, out=out, width=1200,
                              pages=None, runs=31, trace=False, pdfjs_root=None)
    paired_sweep.gate = lambda: gate()[0]
    with ExitStack() as stack:
        docs = {}
        for tag, dll in zip('AB', (options.a, options.b)):
            doc = paired_sweep.NativeDocument(dll, pdf, options.width)
            stack.callback(doc.close)
            docs[tag] = SimpleNamespace(
                scales=[doc.scales[i] for i in page_indices],
                render=lambda i, verify, height, doc=doc: doc.render(page_indices[i], verify, height),
            )
        data = paired_sweep.capture(options, docs, None)
    assert data['differing_pixels'] == 0, data['mismatched_pages']
    for row, i in zip(data['pages'], page_indices):
        row['page'] = i + 1
    out.write_text(json.dumps(data, indent=1) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('main', type=Path)
    parser.add_argument('candidate', type=Path)
    parser.add_argument('--raw', type=Path, default=HERE / 'raw')
    parser.add_argument('--chinese-only', action='store_true', help='Recheck the two Chinese pages in isolation')
    args = parser.parse_args()
    a, b = [str(path.resolve()) for path in (args.main, args.candidate)]
    raw = args.raw.resolve()
    raw.mkdir(parents=True, exist_ok=True)
    slide_pdf = FIXTURES / 'pdf-large/real-mixed-120.pdf'
    if args.chinese_only:
        chinese(a, b, slide_pdf, raw / 'production-chinese-1200.json')
        return
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
