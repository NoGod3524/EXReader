# SPDX-License-Identifier: MIT
"""Synthetic K03 books: EPUB and PDF from the repository's existing generators, plus one TXT.
usage: fixtures.py DIR"""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    folder = Path(sys.argv[1])
    folder.mkdir(parents=True)
    sys.path.insert(0, str(ROOT / 'tools'))
    load('tools/run_benchmarks.py', 'k03_bench').make_epub(folder / '示例 Portable.epub', 3, 12000)
    load('tests/linux_host/generate_fixed.py', 'k03_fixed').pdf(folder / 'Pages 页面.pdf')
    (folder / 'Notes 笔记.txt').write_text('中文、café, नमस्ते. Portable update keeps this library.\n' * 400, encoding='utf-8')
    manifest = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.iterdir())}
    (folder.parent / (folder.name + '.json')).write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n')
    print('K03-FIXTURES ' + json.dumps(manifest, ensure_ascii=False))


if __name__ == '__main__':
    main()
