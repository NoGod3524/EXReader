"""Actions-only exact source diffs; retains the original immutable driver identities."""
import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path

assert os.environ.get('GITHUB_ACTIONS') == 'true'
p = argparse.ArgumentParser()
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
a.output.mkdir(parents=True)
root = Path(__file__).resolve().parents[2]
pairs = [('reader_a11y_gtk/audit_gtk_a11y.py', 'audit_current.py'),
         ('reader_a11y_gtk/expectations.py', 'current_expectations.py'),
         ('reader_a11y_gtk/check_a11y_report.py', 'gate_current.py'),
         ('reader_wave3_c10/check_ui.py', 'tools_current.py'),
         ('reader_wave3_c10/identity.py', 'identity_current.py')]
report = dict(source_sha=os.environ['GITHUB_SHA'], run_id=os.environ['GITHUB_RUN_ID'],
              attempt=os.environ['GITHUB_RUN_ATTEMPT'], drivers=[])
for original, current in pairs:
    old = root / 'tests' / original
    new = Path(__file__).parent / current
    diff = ''.join(difflib.unified_diff(old.read_text().splitlines(True), new.read_text().splitlines(True),
                                       fromfile='tests/' + original,
                                       tofile='tests/reader_d26_accessibility/' + current))
    (a.output / (current + '.diff')).write_text(diff)
    report['drivers'].append(dict(original=str(old.relative_to(root)), current=str(new.relative_to(root)),
                                  original_sha256=hashlib.sha256(old.read_bytes()).hexdigest(),
                                  current_sha256=hashlib.sha256(new.read_bytes()).hexdigest()))
(a.output / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report), flush=True)
