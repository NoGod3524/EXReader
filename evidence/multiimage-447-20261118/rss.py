# SPDX-License-Identifier: MIT
"""Measure fresh-process peak working sets independently of wall time."""
import json
import subprocess
import sys
from pathlib import Path

from capture import Document, ROOT, digest_file, process_memory_bytes


def child(dll, pdf):
    doc = Document(dll, pdf, 1200, None)
    try:
        for _ in range(2):
            for i in range(len(doc.scales)):
                doc.render(i, False)
        print(process_memory_bytes()[1])
    finally:
        doc.close()


def main(a, b, out):
    dlls = (a.resolve(), b.resolve())
    rows = []
    for name in ('image-heavy-100', 'real-mixed-120', 'vector-heavy-100'):
        pdf = ROOT/f'tests/fixtures/pdf-large/{name}.pdf'
        peaks = []
        for pair in ((0, 1), (1, 0), (0, 1)):
            rss = {}
            for side in pair:
                value = subprocess.check_output([sys.executable, str(Path(__file__).resolve()),
                                                 'child', str(dlls[side]), str(pdf)], text=True)
                rss['AB'[side]] = int(value)
            peaks.append(rss)
        rows.append({'fixture': name, 'pdf_sha256': digest_file(pdf), 'peak_working_set': peaks})
        print(name, peaks, flush=True)
    out.write_text(json.dumps({'dll_sha256': list(map(digest_file, dlls)), 'cases': rows}, indent=2)+'\n')


if __name__ == '__main__':
    if sys.argv[1] == 'child':
        child(*map(Path, sys.argv[2:]))
    else:
        main(*map(Path, sys.argv[1:]))
