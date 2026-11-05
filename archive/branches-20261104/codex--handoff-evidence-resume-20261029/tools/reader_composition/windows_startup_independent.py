#!/usr/bin/env python3
"""Actions-only independent review of retained Windows startup evidence."""
import argparse
import base64
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import sqlite3
import sys
import tempfile
import zipfile

assert os.environ.get('GITHUB_ACTIONS') == 'true'
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from check_parallel_integration import fetch, download_artifact_zip

p = argparse.ArgumentParser()
for name in ('run', 'job', 'artifact', 'bytes'):
    p.add_argument('--' + name, type=int, required=True)
for name in ('source', 'sha256'):
    p.add_argument('--' + name, required=True)
a = p.parse_args()
out = Path('build/windows-startup-independent') / str(a.run)
out.mkdir(parents=True, exist_ok=True)
result = dict(accepted=False, producer_source=a.source, producer_run=a.run,
              producer_job=a.job, artifact=a.artifact, catalog_changed=False,
              full_p0_acceptance=False, same_source_six_platform_acceptance=False)

def sha(data):
    return hashlib.sha256(data).hexdigest()

def source_file(ref, path):
    item = fetch('contents/' + path + '?ref=' + ref)
    assert item['type'] == 'file' and item['encoding'] == 'base64'
    return base64.b64decode(item['content'])

try:
    assert len(a.source) == 40 and all(c in '0123456789abcdef' for c in a.source)
    assert len(a.sha256) == 64 and all(c in '0123456789abcdef' for c in a.sha256)
    run = fetch(f'actions/runs/{a.run}/attempts/1')
    assert (run['head_sha'], run['run_attempt'], run['status'], run['conclusion']) == (a.source, 1, 'completed', 'success')
    job = fetch(f'actions/jobs/{a.job}')
    assert (job['run_id'], job['head_sha'], job['status'], job['conclusion']) == (a.run, a.source, 'completed', 'success')
    pin = fetch(f'actions/artifacts/{a.artifact}')
    assert not pin['expired'] and pin['name'] == f'windows-migration-startup-gate-{a.run}-1'
    assert (pin['workflow_run']['id'], pin['workflow_run']['head_sha']) == (a.run, a.source)
    assert pin['size_in_bytes'] == a.bytes and pin['digest'] == 'sha256:' + a.sha256
    raw = download_artifact_zip(a.artifact)
    assert len(raw) == a.bytes and sha(raw) == a.sha256
    baseline = '2fff53ff6734ec2b495c841e6669aef562e170d7'
    paths = ['tests/windows_migration_startup/check.py', 'apps/reader/desktop/windows_migration_gate.h',
             'apps/reader/desktop/windows_catalog.inc', 'examples/reader.c']
    identities = {}
    for path in paths:
        original = source_file(baseline, path)
        assert source_file(a.source, path) == original, ('original driver/product gate changed', path)
        identities[path] = sha(original)
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = archive.namelist()
        assert len(names) == len(set(names))
        assert all(not PurePosixPath(n).is_absolute() and '..' not in PurePosixPath(n).parts and '\\' not in n for n in names)
        reports = [n for n in names if n.endswith('startup-gate-evidence/report.json')]
        assert len(reports) == 1
        report_path = reports[0]
        prefix = report_path.removesuffix('report.json')
        report = json.loads(archive.read(report_path))
        assert (report['source'], str(report['run']), str(report['attempt'])) == (a.source, str(a.run), '1')
        assert report['passed'] is True and report['expected'] == 10 and report['full_p0_acceptance'] is False
        cases = report['cases']
        expected = {'recovery-file', 'recovery-directory', 'intent-file', 'intent-directory',
                    'lock-file', 'lock-directory', 'pending-never-creates-target',
                    'clean-library', 'legacy-sidecar-only', 'visible-native-refusal'}
        assert len(cases) == 10 and {c['name'] for c in cases} == expected and all(c['passed'] is True for c in cases)
        programs = [n for n in names if n.endswith('startup-host/EXReaderProduct.exe')]
        assert len(programs) == 1
        binary = archive.read(programs[0])
        assert binary.startswith(b'MZ') and sha(binary) == report['host_sha256']
        for case in cases:
            name = case['name']
            case_prefix = prefix + name + '/'
            if name in ('clean-library', 'legacy-sidecar-only'):
                assert case['exit'] == 0 and case['actual_sdk_schema_upgrade'] is True
                assert case['legacy_sidecar_preserved'] == (name == 'legacy-sidecar-only')
                with tempfile.TemporaryDirectory() as temp:
                    database = Path(temp) / 'library.sqlite'
                    database.write_bytes(archive.read(case_prefix + 'library/library.sqlite'))
                    with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as db:
                        assert db.execute('PRAGMA user_version').fetchone()[0] == 7
            else:
                assert case['exit'] == 2
                stderr = archive.read(case_prefix + 'stderr.txt')
                assert b'[EXReader migration startup gate] blocked' in stderr
                if name == 'visible-native-refusal':
                    dialog = json.loads(archive.read(case_prefix + 'visible-dialog.json'))
                    assert case['visible'] is True and dialog['visible'] is True
                    assert dialog['message'] == case['message'] and dialog['rectangle'] == case['rectangle']
                    assert all(text in dialog['message'] for text in ('迁移状态', '恢复迁移', '现有文件已保留'))
                    rectangle = dialog['rectangle']
                    assert rectangle[2] > rectangle[0] and rectangle[3] > rectangle[1]
                else:
                    before, after = case['before'], case['after']
                    assert all(after.get(k) == value for k, value in before.items())
                    assert set(after) - set(before) <= {'library.sqlite.product.lock'}
                    assert case['suffix'].encode() in stderr
                    for relative, state in after.items():
                        assert not PurePosixPath(relative).is_absolute() and '..' not in PurePosixPath(relative).parts
                        if not state['directory']:
                            retained = archive.read(case_prefix + 'library/' + relative.replace('\\', '/'))
                            assert len(retained) == state['bytes'] and sha(retained) == state['sha256']
                    if case['empty']:
                        assert 'library.sqlite' not in after
        result.update(accepted=True, case_count=10, passing_cases=sorted(expected),
                      archive_bytes=len(raw), archive_sha256=sha(raw), program_sha256=sha(binary),
                      source_file_sha256=identities,
                      scope='retained actual Windows startup refusal and schema6-to-7 fixture evidence; cooperative startup only')
except Exception as error:
    result['error'] = repr(error)
finally:
    (out / 'result.json').write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False), flush=True)
assert result['accepted'], result.get('error')
