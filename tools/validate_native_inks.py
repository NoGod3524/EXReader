#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Compare known ink arithmetic with MuPDF's native CMYK output (no RGB ICC conversion)."""
import argparse
import hashlib
import json
from pathlib import Path
import pymupdf


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    directory = root / 'tests/fixtures/pdf-color'
    sources = [(180, 120, 80, 90), (0, 0, 0, 200), (128, 128, 128, 0)]
    base = [51, 102, 153, 25.5]
    rows = []
    for kind in ['image', 'axial', 'radial', 'mesh4', 'mesh5', 'mesh6', 'mesh7']:
        for index, source in enumerate(sources):
            for mode in ['normal', 'multiply', 'screen']:
                name = 'native-%s-%d-%s.pdf' % (kind, index, mode)
                path = directory / name
                expected = []
                for b, s in zip(base, source):
                    blend = s if mode == 'normal' else b+s-b*s/255 if mode == 'multiply' else b*s/255
                    expected.append(int((b+blend)/2+.5))
                with pymupdf.open(path) as document:
                    pixmap = document[0].get_pixmap(colorspace=pymupdf.csCMYK, alpha=False)
                    # EXReader's direct draw probe (4,4) is PDF bottom-up;
                    # MuPDF's viewport is top-down on this 16-pixel page.
                    actual = list(pixmap.pixel(4, 11))
                rows.append({'file': name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                             'expected_cmyk': expected, 'mupdf_cmyk': actual,
                             'max_difference': max(abs(a-b) for a, b in zip(actual, expected))})
    report = {'reference': 'MuPDF '+pymupdf.VersionBind,
              'space': 'native DeviceCMYK, four bytes, no RGB conversion',
              'probe_pdf': [4.5, 4.5], 'scenes': rows,
              'max_difference': max(row['max_difference'] for row in rows)}
    args.output.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print('%d native CMYK scenes; MuPDF maximum difference %d/255' % (len(rows), report['max_difference']))
    if report['max_difference'] > 3:
        raise SystemExit('Independent comparison exceeds the existing interior-probe threshold')


if __name__ == '__main__':
    main()
