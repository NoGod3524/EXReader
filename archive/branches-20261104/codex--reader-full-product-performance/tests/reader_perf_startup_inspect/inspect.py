#!/usr/bin/env python3
"""Authenticate and summarize the retained Windows startup observation in Actions."""
import hashlib
import io
import json
import os
from pathlib import Path
import statistics
import subprocess
import zipfile
repo, run = os.environ['GITHUB_REPOSITORY'], 40399615507
api = lambda suffix: json.loads(subprocess.check_output(['gh', 'api', f'repos/{repo}/{suffix}']))
run_info = api(f'actions/runs/{run}')
items = api(f'actions/runs/{run}/artifacts')['artifacts']
items = [x for x in items if x['name'] == f'full-perf-startup-{run}-1' and not x['expired']]
assert len(items) == 1
artifact = items[0]
assert artifact['workflow_run']['head_sha'] == run_info['head_sha'] and artifact['workflow_run']['id'] == run
raw = subprocess.check_output(['gh', 'api', f'repos/{repo}/actions/artifacts/{artifact["id"]}/zip'])
assert len(raw) == artifact['size_in_bytes'] and 'sha256:' + hashlib.sha256(raw).hexdigest() == artifact['digest']
with zipfile.ZipFile(io.BytesIO(raw)) as archive:
    names = [name for name in archive.namelist() if name.endswith('startup-summary.json')]
    assert len(names) == 1
    summary = json.loads(archive.read(names[0]))
assert summary['observer_source'] == run_info['head_sha'] and str(summary['observer_run']) == str(run)
assert len(summary['results']) == 8 and not any(row['error'] for row in summary['results'])
rows = []
for row in summary['results']:
    complete = [sample for sample in row['catalog_samples'] if sample.get('local_book_count') == 2202]
    first = [sample for sample in row['catalog_samples'] if isinstance(sample.get('local_book_count'), int)]
    rows.append({'index': row['index'], 'catalog_poll': row['catalog_poll'], 'marks_ms': row['marks_ms'],
                 'catalog_first_count': first[0] if first else None,
                 'catalog_first_2202': complete[0] if complete else None,
                 'catalog_sample_count': len(row['catalog_samples']),
                 'catalog_errors': sum('error' in sample for sample in row['catalog_samples'])})
by_group = {}
for flag in (False, True):
    group = [row for row in rows if row['catalog_poll'] == flag]
    for key in ('window_created', 'first_ui_roundtrip', 'first_nonempty_list', 'first_product_snapshot', 'first_metadata_enabled', 'product_shelf_interactive'):
        values = [row['marks_ms'][key] for row in group if key in row['marks_ms']]
        by_group[f'{"catalog_polled" if flag else "unpolled"}_{key}'] = {'n': len(values), 'median_ms': statistics.median(values) if values else None, 'min_ms': min(values) if values else None, 'max_ms': max(values) if values else None}
result = {'source_sha': summary['observer_source'], 'run': run, 'attempt': summary['observer_attempt'],
          'producer': summary['producer'], 'artifact_id': artifact['id'], 'artifact_digest': artifact['digest'],
          'environment': summary['environment'], 'method': summary['method'], 'limitations': summary['limitations'],
          'groups': by_group, 'launches': rows, 'performance_accepted': False}
out = Path('build/startup-inspection'); out.mkdir(parents=True, exist_ok=True)
(out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result))
