#!/usr/bin/env python3
"""Hash every real-book page using the compiled host's actual font helper.

The before bridge is compiled from the base revision's reader.c; the after
bridge is examples/windows/check_typography_font.c built as a shared library.
Both link the identical SDK DLL. No legacy lookup is copied into this driver.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import ctypes as c
import json
import os
import shutil
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools/regress'))
import run_realbooks as regression


def render(book, dll, bridge, font, layout):
    original = regression.SDK

    class HostSDK(original):
        def __init__(self, path):
            super().__init__(path)
            self.toolchain = os.add_dll_directory(str(Path(shutil.which("g++")).parent))
            self.host = c.CDLL(bridge)
            self.font_open = self.host.host_check_font_open
            self.font_open.restype = c.c_int
            self.font_open.argtypes = [c.c_char_p, c.POINTER(c.c_void_p), c.POINTER(regression.Error)]

    regression.SDK = HostSDK
    try:
        return regression.render_book(book, dll, font, layout)
    finally:
        regression.SDK = original


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('dll', 'bridge', 'font', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--workers', type=int, default=4)
    args = parser.parse_args()
    books = regression.read_json(ROOT / 'tools/regress/corpus.json')['books']
    layout = regression.read_json(ROOT / 'tools/regress/layout.json')
    start = time.monotonic()
    results = {}
    with ProcessPoolExecutor(args.workers) as pool:
        pending = [pool.submit(render, b, str(args.dll.resolve()), str(args.bridge.resolve()),
                               args.font.resolve(), layout) for b in books]
        for job in as_completed(pending):
            book = job.result()
            results[book['id']] = book
            print(book['id'], book['status'], book['page_count'], book.get('error', ''), flush=True)
    output = dict(schema=1, pixel_contract='sha256/visible-row-major-RGBA8/white/v1',
                  layout=layout, font_sha256=regression.file_hash(args.font),
                  environment=dict(system='Windows', machine='AMD64'),
                  dll_sha256=regression.file_hash(args.dll), bridge_sha256=regression.file_hash(args.bridge),
                  books=[results[b['id']] for b in books], elapsed_seconds=time.monotonic()-start)
    output['content_fingerprint'] = regression.fingerprint(output['books'])
    regression.write_json(args.output, output)
    if args.baseline:
        before = regression.read_json(args.baseline)
        assert before['dll_sha256'] == output['dll_sha256'], 'SDK changed between runs'
        diff = regression.compare(before, output)
        regression.write_json(args.output.with_suffix('.diff.json'), diff)
        assert not diff['needs_review'], json.dumps(diff)
    assert len(results) == 19 and all(b['status'] == 'ok' for b in results.values())


if __name__ == '__main__':
    main()
