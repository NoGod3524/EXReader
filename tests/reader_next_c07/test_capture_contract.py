"""Actions-only rejection regressions derived from authenticated REAL C07 ZIPs.

No original artifact is changed: each mutant is a deep copy of one native
receiver's recorded result, checked against the original sender manifest.
"""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import sys
import zipfile

from capture_contract import judge

PHASES = ('android-receive', 'android-receive-reopen', 'android-session-receive', 'android-session-reopen')


def exercise(receive, manifest):
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    expected = {row['revision_id']: row for row in manifest['reading_records']}
    assert len(expected) == 11
    results = []
    positive_count = 0
    for phase in PHASES:
        rows = receive.json(phase + '.json')['records']
        assert len(rows) == len(expected) and {row['revision_id'] for row in rows} == set(expected)
        for original in rows:
            identity = expected[original['revision_id']]
            baseline = judge(original, identity)
            assert not baseline, (phase, original['revision_id'], baseline)
            positive_count += 1
            mutants = {}

            def mutate(name, change):
                row = deepcopy(original)
                change(row)
                mutants[name] = row

            mutate('start_offset', lambda r: r['recapture']['numbers'].__setitem__(2, str(int(r['recapture']['numbers'][2]) + 1)))
            mutate('mode', lambda r: r['recapture']['numbers'].__setitem__(0, '99'))
            mutate('selector_byte', lambda r: r['recapture']['selectors'].__setitem__(0, 'AQ==' if r['recapture']['selectors'][0] != 'AQ==' else 'Ag=='))
            mutate('NULL_vs_allocated_empty', lambda r: r['recapture']['selectors'].__setitem__(0, '' if r['recapture']['selectors'][0] is None else None))
            for index, label in enumerate(('book', 'parser', 'part_path', 'page_id', 'chapter')):
                mutate('route_' + label, lambda r, index=index: r['recapture']['route'].__setitem__(index, str(r['recapture']['route'][index]) + '-changed'))
            mutate('short_route', lambda r: r['recapture']['route'].pop())
            mutate('reconstruction_only', lambda r: r['reconstruction']['selectors'].__setitem__(0, 'AQ==' if r['reconstruction']['selectors'][0] != 'AQ==' else 'Ag=='))
            mutate('record_kind', lambda r: r.__setitem__('kind', 'unregistered-kind'))
            mutate('record_role', lambda r: r.__setitem__('role', 'epub' if r['role'] != 'epub' else 'txt'))

            # An equality-only gate would accept both sides changed together.
            paired = deepcopy(original)
            for key in ('transport_capture', 'recapture', 'reconstruction'):
                paired[key]['numbers'][2] = str(int(paired[key]['numbers'][2]) + 1)
            mutants['both_sides_changed'] = paired
            if identity['role'] == 'epub':
                mutate('EPUB_chapter_not_reconstructed', lambda r: r['recapture']['route'].__setitem__(4, None))
                mutate('EPUB_transport_chapter_nonNULL', lambda r: r['transport_capture']['route'].__setitem__(4, r['transport_capture']['route'][2]))
            for case, row in mutants.items():
                failed = judge(row, identity)
                assert failed, ('mutant accepted', phase, identity['revision_id'], case)
                results.append({'phase': phase, 'revision_id': identity['revision_id'], 'role': identity['role'],
                                'case': case, 'rejected': True, 'failures': failed})
    return {'scope': 'strict capture contract rejection regressions from authenticated real native reports only',
            'positives': positive_count, 'mutants': len(results), 'all_rejected': True, 'cases': results}


class ZipView:
    def __init__(self, raw):
        self.archive = zipfile.ZipFile(io.BytesIO(raw))
        self.names = self.archive.namelist()
        assert len(self.names) == len(set(self.names))
        assert sum(row.file_size for row in self.archive.infolist()) < 64 * 1024 * 1024
        for name in self.names:
            path = PurePosixPath(name)
            assert not path.is_absolute() and '..' not in path.parts and '\\' not in name and ':' not in name

    def json(self, suffix):
        found = [name for name in self.names if name == suffix or name.endswith('/' + suffix)]
        assert len(found) == 1, (suffix, found)
        return json.loads(self.archive.read(found[0]))


def historical():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
    from check_parallel_integration import fetch, download_artifact_zip
    source, run = 'd3f7ec5bb57b372a0b61d13446e7ce8ea2d1ae4f', 40227524890
    metadata = fetch(f'actions/runs/{run}/attempts/1')
    assert metadata['head_sha'] == source and metadata['status'] == 'completed' and metadata['conclusion'] == 'success'
    jobs = fetch(f'actions/runs/{run}/attempts/1/jobs?per_page=100')['jobs']
    assert len(jobs) == 5 and {row['name'] for row in jobs} == {'fixtures', 'mac-send', 'android', 'mac-receive', 'strict'}
    assert all(row['head_sha'] == source and row['conclusion'] == 'success' for row in jobs)
    selected = {12612511498: 'sender', 12612267111: 'receive'}
    artifacts = fetch(f'actions/runs/{run}/artifacts?per_page=100')['artifacts']
    views, authenticated = {}, []
    out = Path('build/c07-contract-inspect')
    out.mkdir(parents=True, exist_ok=True)
    for row in artifacts:
        if row['id'] not in selected:
            continue
        assert row['workflow_run']['id'] == run and row['workflow_run']['head_sha'] == source and not row['expired']
        assert datetime.fromisoformat(row['expires_at'].replace('Z', '+00:00')) > datetime.now(timezone.utc)
        raw = download_artifact_zip(row['id'])
        assert len(raw) == row['size_in_bytes'] and 'sha256:' + hashlib.sha256(raw).hexdigest() == row['digest']
        (out / (selected[row['id']] + '.original.zip')).write_bytes(raw)
        views[selected[row['id']]] = ZipView(raw)
        authenticated.append({key: row[key] for key in ('id', 'name', 'size_in_bytes', 'digest', 'expires_at')})
    assert set(views) == {'sender', 'receive'}
    manifest = views['sender'].json('bundle/manifest.json')
    assert manifest['sender']['source_sha'] == source and int(manifest['sender']['run_id']) == run and int(manifest['sender']['attempt']) == 1
    result = exercise(views['receive'], manifest)
    result.update({'accepted': False, 'historical_source': source, 'historical_run_id': run, 'historical_attempt': 1,
                   'source_sha': os.environ['GITHUB_SHA'], 'run_id': int(os.environ['GITHUB_RUN_ID']),
                   'attempt': int(os.environ['GITHUB_RUN_ATTEMPT']), 'authenticated_artifacts': authenticated})
    (out / 'report.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: value for key, value in result.items() if key != 'cases'}), flush=True)


if __name__ == '__main__':
    historical()
