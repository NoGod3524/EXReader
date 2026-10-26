"""Explicit D19-only source boundary, not the historical unchanged-owner guard."""
import json
import os
from pathlib import Path
import subprocess
from reuse import ROOT, SEED, SDK
from contract import write, selftest

FILES = {
    '.github/workflows/reader-wave3-d19.yml',
    'tests/reader_wave3_d19/reuse.py',
    'tests/reader_wave3_d19/contract.py',
    'tests/reader_wave3_d19/guard.py',
    'tests/reader_wave3_d19/build.py',
    'tests/reader_wave3_d19/run.py',
    'tests/reader_wave3_d19/gtk.py',
    'tests/reader_wave3_d19/authenticate.py',
    'tests/reader_wave3_d19/CMakeLists.txt',
    'tests/reader_wave3_d19/catalog.c',
    'docs/reader-wave3-d19/README.md',
    'docs/reader-wave3-d19/final-evidence.json',
    'HANDOFF-RESULT-D19.md',
}

def allowed(rows):
    assert all(state in ('A', 'M') and path in FILES for state, path in rows), rows

def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    actual = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    assert actual == os.environ['GITHUB_SHA']
    subprocess.run(['git', 'merge-base', '--is-ancestor', SEED, actual], check=True)
    rows = [line.split('\t', 1) for line in subprocess.check_output(['git', 'diff', '--name-status', SEED, actual], text=True).splitlines()]
    allowed(rows)
    subprocess.run(['git', 'diff', '--exit-code', SDK, actual, '--', 'src', 'include', 'bindings', 'cmake', 'CMakeLists.txt'], check=True)
    rejected = []
    for path in ('examples/linux/reader.c', 'tests/reader_dot_wave2/d14/gtk.py', 'CMakeLists.txt', 'include/exr/base.h', 'tests/reader_perf_gtk/budget.json', 'tests/reader_wave3_d19/unlisted.py'):
        try:
            allowed([('M', path)])
        except AssertionError:
            rejected.append(path)
        else:
            raise AssertionError('boundary negative accepted: ' + path)
    selftest()
    report = dict(accepted=True, source_sha=actual, seed=SEED, sdk=SDK, changed_paths=rows,
                  exact_allowed_paths=sorted(FILES), rejected=rejected, seed_is_accepted_base=False,
                  product_changed=False, historical_acceptance_reused=False)
    write(ROOT / 'evidence/source-boundary.json', report)
    print(json.dumps(report), flush=True)

if __name__ == '__main__':
    main()
