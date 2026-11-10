#!/usr/bin/env python3
"""Interleaved A/B large_book_probe runs (A=before DLL dir, B=after DLL dir) so machine load hits both equally.
Each side is a directory holding probe.exe and libexreader.dll. Keeps raw runs, median and min per metric."""
import argparse, json, os, statistics, subprocess
from pathlib import Path

KEYS = ('open_first_ms', 'open_second_ms', 'first_screen_ms', 'turn_p50_ms', 'turn_p95_ms', 'jump_p95_ms',
        'toc_load_ms', 'toc_last_jump_ms', 'search_first32_ms', 'sdk_search_first32_ms', 'sdk_search_full_ms')
MEM = ('peak_ws', 'end_ws', 'after_search_ws', 'peak_private', 'end_private')


def run(side, book, font, needle):
    env = dict(os.environ, PATH=str(side) + os.pathsep + os.environ['PATH'])
    out = subprocess.run([str(side / 'probe.exe'), 'measure', str(book), str(font),
                          str(book.with_suffix('.pages.txt')), needle], capture_output=True, check=True, env=env).stdout
    return json.loads(out)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--a', type=Path, required=True); p.add_argument('--b', type=Path, required=True)
    p.add_argument('--font', type=Path, required=True); p.add_argument('--runs', type=int, default=5)
    p.add_argument('--needle', default='之'); p.add_argument('--output', type=Path, required=True)
    p.add_argument('books', nargs='+', type=Path)
    a = p.parse_args()
    report = {}
    for book in a.books:
        raw = {'A': [], 'B': []}
        for i in range(a.runs):
            for tag, side in (('A', a.a), ('B', a.b)) if i % 2 == 0 else (('B', a.b), ('A', a.a)):
                raw[tag].append(run(side, book, a.font, a.needle))
        entry = {}
        for tag in raw:
            s = {}
            for k in KEYS:
                v = [r[k] for r in raw[tag]]; s[k] = {'median': round(statistics.median(v), 3), 'min': round(min(v), 3)}
            for k in MEM:
                v = [r['mem_mb'][k] for r in raw[tag]]; s[k] = {'median': round(statistics.median(v), 2), 'min': round(min(v), 2)}
            for k in ('total_pages', 'parts', 'toc_entries', 'sdk_search_full_hits', 'search_hits'):
                s[k] = raw[tag][0][k]
            entry[tag] = s
        entry['raw'] = raw
        report[book.stem] = entry
        a.output.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
        print(book.stem, 'done', flush=True)


if __name__ == '__main__':
    main()
