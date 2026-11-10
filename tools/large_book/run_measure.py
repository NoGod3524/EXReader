#!/usr/bin/env python3
"""Run large_book_probe measure serially N times per book; keep raw runs and medians."""
import argparse
import json
from pathlib import Path
import statistics
import subprocess

KEYS = ('open_first_ms', 'open_second_ms', 'first_screen_ms', 'turn_p50_ms', 'turn_p95_ms', 'jump_p95_ms',
        'toc_load_ms', 'toc_last_jump_ms', 'search_first32_ms', 'sdk_search_first32_ms', 'sdk_search_full_ms')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--probe', type=Path, required=True)
    p.add_argument('--font', type=Path, required=True)
    p.add_argument('--runs', type=int, default=3)
    p.add_argument('--needle', default='之')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('books', nargs='+', help='book.epub (pages file: same stem + .pages.txt)')
    a = p.parse_args()
    report = {'needle': a.needle, 'runs': a.runs, 'books': {}}
    for book in map(Path, a.books):
        runs = []
        for _ in range(a.runs):
            out = subprocess.run([str(a.probe), 'measure', str(book), str(a.font),
                                  str(book.with_suffix('.pages.txt')), a.needle],
                                 capture_output=True, check=True).stdout
            runs.append(json.loads(out))
        median = {k: round(statistics.median(r[k] for r in runs), 3) for k in KEYS}
        median['peak_ws_mb'] = round(statistics.median(r['mem_mb']['peak_ws'] for r in runs), 2)
        median['end_ws_mb'] = round(statistics.median(r['mem_mb']['end_ws'] for r in runs), 2)
        median['after_search_ws_mb'] = round(statistics.median(r['mem_mb']['after_search_ws'] for r in runs), 2)
        for k in ('total_pages', 'parts', 'toc_entries', 'sdk_search_full_hits', 'search_hits'):
            median[k] = runs[0][k]
        report['books'][book.stem] = {'median': median, 'raw': runs}
        print(book.stem, json.dumps(median), flush=True)
        a.output.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')


if __name__ == '__main__':
    main()
