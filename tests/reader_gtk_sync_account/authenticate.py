# SPDX-License-Identifier: MIT
"""Authenticate this run's original ZIP and source-bound GTK host report."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess

assert os.environ.get('GITHUB_ACTIONS') == 'true'
p = argparse.ArgumentParser()
for name in ('artifact', 'archive', 'output'):
    p.add_argument('--' + name, type=Path, required=True)
a = p.parse_args()
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
run, attempt, source = (os.environ[x] for x in ('GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT', 'GITHUB_SHA'))
identity = {'source_sha': source, 'run_id': run, 'attempt': attempt, 'verified': False}
try:
    listing = json.loads(subprocess.check_output(['gh', 'api',
        'repos/%s/actions/runs/%s/artifacts' % (os.environ['GITHUB_REPOSITORY'], run)], text=True))
    name = 'gtk-sync-account-%s-%s' % (run, attempt)
    matches = [item for item in listing['artifacts'] if item['name'] == name]
    assert len(matches) == 1
    item = matches[0]
    assert not item['expired'] and item['size_in_bytes'] == a.archive.stat().st_size
    assert item['digest'] == 'sha256:' + sha(a.archive)
    reports = list(a.artifact.rglob('combined-account/result.json'))
    programs = list(a.artifact.rglob('EXReader-Linux/bin/exreader-linux'))
    assert len(reports) == len(programs) == 1, (reports, programs)
    report = json.loads(reports[0].read_text())
    assert report['source_sha'] == source and str(report['run_id']) == run and str(report['attempt']) == attempt
    assert report['accepted'] is True and report['program_sha256'] == sha(programs[0])
    assert report['count'] == len(report['checks']) == 27 and len(set(report['checks'])) == 27
    baseline = subprocess.check_output(['git', 'show', '8226c43e75178a3b752efc5b981d5b4044ff0f98:tests/reader_gtk_sync_account/check_combined.py'], text=True)
    tree = ast.parse(baseline)
    retained = {node.args[0].value for node in ast.walk(tree) if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name) and node.func.id == 'record'
                and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)}
    retained.update('status_' + phase + '_capture_is_read_only'
                    for phase in ('syncing', 'cancelled', 'failed', 'sweep-complete'))
    assert len(retained) == 27 and set(report['checks']) == retained
    assert report['extra_checks'] == ['live_status_widget_is_noneditable_and_matches_capture',
                                      'closed_session_retained_until_pending_capture_releases']
    assert report['live_widget']['editable'] is False
    assert report['pending_capture']['closed_while_pending'] and report['pending_capture']['retained_until_release'] and report['pending_capture']['reopened']
    assert report['owner_page_limit'] == 50 and report['copy_chunk_limit'] == 65536 and report['original_limit'] == 128 * 1024 * 1024
    identity.update(verified=True, artifact_id=item['id'], archive_sha256=sha(a.archive),
                    program_sha256=sha(programs[0]), report_sha256=sha(reports[0]),
                    retained_checks=27, additional_checks=2)
except Exception as error:
    identity['error'] = repr(error)
finally:
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(identity, indent=2) + '\n')
    print(json.dumps(identity), flush=True)
assert identity['verified'], identity
