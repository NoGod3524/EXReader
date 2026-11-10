"""Check diagnostic filtering and reconcile the measured campaign's counters."""
import argparse
from collections import Counter
import json
from pathlib import Path

from run import diagnostics


def check(output):
    sample = ('AUDIT_CONTEXT part=2 page=3 global_page=8 stage=render\n'
              'x.c:4:5: runtime error: signed integer overflow\n'
              '    #0 0x123 in function x.c:4\n'
              '  00 01 book text must not be retained\n'
              'SUMMARY: UndefinedBehaviorSanitizer: undefined-behavior x.c:4\n'
              'AUDIT_RENDERED mode=0\n')
    parsed = diagnostics(sample)
    assert len(parsed) == 1 and len(parsed[0]['lines']) == 3
    assert 'book text' not in str(parsed)
    assert 'page=3' in parsed[0]['context']
    counts = {}
    for group, expected in (('controls',2),('books',19),('malformed',200),('seeds',25)):
        rows = [json.loads(line) for line in (output/(group+'.jsonl')).read_text(encoding='utf-8').splitlines()]
        summary = json.loads((output/(group+'-summary.json')).read_text())
        assert len(rows) == len({r['id'] for r in rows}) == summary['units'] == expected
        assert not any(r['timed_out'] for r in rows), group
        for sanitizer, marker in (('asan','AddressSanitizer'),('ubsan','runtime error:')):
            assert summary[sanitizer] == sum(marker in d['lines'][0] for r in rows for d in r['diagnostics'])
        assert summary['pages'] == sum((r['metrics'] or {}).get('pages',0) for r in rows)
        assert summary['rendered_pages'] == sum(r['rendered_pages'] for r in rows)
        if group == 'books':
            assert all(r['exit_code'] == 0 and r['metrics']['complete'] for r in rows)
            assert all(r['rendered_pages'] == r['metrics']['pages'] > 0 for r in rows)
            assert sum(int(r['writing_mode_pages'].get('1',0)) for r in rows) > 0
        if group == 'malformed':
            assert len({r['sha256'] for r in rows}) == 200
            assert set(Counter(r['category'] for r in rows).values()) == {25}
            assert all(r['metrics'] is not None for r in rows)
        if group == 'seeds':
            assert all(r['exit_code'] == 0 and r['replay'] is not None for r in rows)
        if group == 'controls':
            assert summary['asan'] == summary['ubsan'] == 1
            assert all(sum(line.lstrip().startswith('#') for d in r['diagnostics'] for line in d['lines']) >= 5 for r in rows)
        counts[group] = dict(units=expected,pages=summary['pages'],asan=summary['asan'],ubsan=summary['ubsan'])
    coverage = json.loads((output/'coverage.json').read_text())
    assert {g:c['profile_count'] for g,c in coverage.items()} == dict(books=19,malformed=200,seeds=25,combined=244)
    assert all(c['engine_totals']['lines']['covered'] > 0 for c in coverage.values())
    build = json.loads((output/'build.json').read_text())
    assert build['all_compile_units_instrumented'] and not build['suppressions'] and not build['ignorelists']
    return dict(passed=True,groups=counts,profiles=244)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    print(json.dumps(check(parser.parse_args().output),indent=2))
