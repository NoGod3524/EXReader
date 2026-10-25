"""Actions-only authentication of the completed root strict ZIP and real regression report."""
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import zipfile

assert os.environ.get('GITHUB_ACTIONS') == 'true'
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
from check_parallel_integration import fetch, download_artifact_zip

source, run = '18f1d1d242185b635ab7d2f863bc47759c164f38', 40236707415
metadata = fetch(f'actions/runs/{run}/attempts/1')
assert metadata['head_sha'] == source and metadata['status'] == 'completed' and metadata['conclusion'] == 'success'
jobs = fetch(f'actions/runs/{run}/attempts/1/jobs?per_page=100')['jobs']
native_jobs = [row for row in jobs if row['name'] != 'contract-inspect']
assert len(native_jobs) == 5 and {row['name'] for row in native_jobs} == {'fixtures', 'mac-send', 'android', 'mac-receive', 'strict'}
assert all(row['head_sha'] == source and row['status'] == 'completed' and row['conclusion'] == 'success' for row in native_jobs)
artifacts = fetch(f'actions/runs/{run}/artifacts?per_page=100')['artifacts']
rows = [row for row in artifacts if row['id'] == 12615871924]
assert len(rows) == 1
row = rows[0]
assert row['name'] == f'c07-strict-{run}-1' and row['workflow_run']['head_sha'] == source and row['workflow_run']['id'] == run and not row['expired']
assert datetime.fromisoformat(row['expires_at'].replace('Z', '+00:00')) > datetime.now(timezone.utc)
raw = download_artifact_zip(row['id'])
assert len(raw) == row['size_in_bytes'] and 'sha256:' + hashlib.sha256(raw).hexdigest() == row['digest']
with zipfile.ZipFile(io.BytesIO(raw)) as archive:
    assert len(archive.namelist()) == len(set(archive.namelist())) and set(archive.namelist()) == {'summary.json', 'capture-contract-regression.json'}
    summary = json.loads(archive.read('summary.json'))
    regression = json.loads(archive.read('capture-contract-regression.json'))
assert summary['source_sha'] == source and int(summary['run_id']) == run and int(summary['attempt']) == 1
assert summary['accepted'] is True and summary['check_count'] == len(summary['checks']) == 81
assert all(row['pass'] for row in summary['checks']) and not summary['pending'] and not summary['failed_checks']
assert summary['directions'] == {'macos->android': True, 'android->macos': True}
assert regression['positives'] == 44 and regression['mutants'] == len(regression['cases']) == 640 and regression['all_rejected']
assert len({(row['phase'], row['revision_id'], row['case']) for row in regression['cases']}) == 640
assert all(row['rejected'] and row['failures'] for row in regression['cases'])
comparisons = summary['artifacts']['transport_vs_reconstruction']
assert len(comparisons) == 4 and sum(len(rows) for rows in comparisons.values()) == 44
assert all(row['numbers_equal'] and row['selectors_equal'] and row['contract_passed'] for rows in comparisons.values() for row in rows)
assert all(row['route_equal'] or row['role'] == 'epub' for rows in comparisons.values() for row in rows)
out = Path('build/c07-contract-inspect')
out.mkdir(parents=True, exist_ok=True)
(out / 'root-strict.original.zip').write_bytes(raw)
result = {'scope': 'authenticate existing scoped root native/protocol acceptance; no new execution grant',
          'audit_source': os.environ['GITHUB_SHA'], 'audit_run_id': int(os.environ['GITHUB_RUN_ID']),
          'full_source': source, 'full_run_id': run, 'full_attempt': 1,
          'checks': 81, 'real_positives': 44, 'rejected_mutants': 640,
          'numbers_selectors_contract_all_equal': True, 'route_contract_all_passed': True,
          'strict_artifact': {key: row[key] for key in ('id', 'name', 'size_in_bytes', 'digest', 'expires_at')}}
(out / 'seal.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
print('C07-ROOT-SEAL ' + json.dumps(result), flush=True)
