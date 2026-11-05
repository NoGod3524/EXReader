# SPDX-License-Identifier: MIT
"""Actions-only strict verifier for S07.

This job is a separate checkout of the same source SHA. It authenticates the
original platform artifacts of this run and attempt (job conclusion, artifact
id, byte size, digest, expiry), then re-derives every claim from the artifact
bytes instead of trusting this package's summary:

  * the read-only guard still names the fixed start and a zero frozen diff;
  * the frozen capture core, the frozen two-peer raw7 TLS test and both frozen
    G07 reports are inside the same artifact with matching SHA-256 and the same
    source/run/attempt;
  * the eight three-peer items are present, in order, with non-empty
    expected/actual;
  * the wire table (revision ID, exact bytes SHA-256, parent set) and the remote
    object inventory are identical on both platforms.
"""
import hashlib
import io
import json
import os
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
import subprocess
import sys
import zipfile

PACKAGE = Path(__file__).resolve().parent
ROOT = PACKAGE.parents[1]
sys.path.insert(0, str(PACKAGE))
sys.path.insert(0, str(ROOT / 'tests/reader_sync_resilience'))
from checks import CHECKS, EXPECTED, GAPS
from boundaries import NEW_CHECKS, ORIGINAL_SESSION_CHECKS

PLATFORMS = (('Linux', 'ubuntu-22.04'), ('Windows', 'windows-2022'))
START = '0889f7d1e9a537c6c1b05456547e016b26e1cd85'
ALLOWED = ('tests/reader_final_s07/', '.github/workflows/reader-final-s07.yml',
           'docs/reader-final-s07/', 'HANDOFF-RESULT.md')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    repository, run, attempt, source = (os.environ[key] for key in
                                       ('GITHUB_REPOSITORY', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT', 'GITHUB_SHA'))

    def api(path, binary=False):
        data = subprocess.check_output(['gh', 'api', 'repos/' + repository + '/' + path], timeout=300)
        return data if binary else json.loads(data)

    record = api('actions/runs/' + run + '/attempts/' + attempt)
    assert record['head_sha'] == source and record['run_attempt'] == int(attempt)
    jobs = api('actions/runs/' + run + '/attempts/' + attempt + '/jobs?per_page=100')['jobs']
    artifacts = api('actions/runs/' + run + '/artifacts?per_page=100')['artifacts']

    tables, rotations, inventory, platforms = {}, {}, {}, []
    for platform, runner in PLATFORMS:
        name = 'three-peer regression (' + runner + ')'
        job = [item for item in jobs if item['name'] == name]
        assert len(job) == 1 and job[0]['conclusion'] == 'success', (name, [item['name'] for item in jobs])
        found = [item for item in artifacts
                 if item['name'] == 'reader-final-s07-' + platform + '-' + run + '-' + attempt]
        assert len(found) == 1, [item['name'] for item in artifacts]
        artifact = found[0]
        assert not artifact['expired']
        assert datetime.fromisoformat(artifact['expires_at'].replace('Z', '+00:00')) > datetime.now(timezone.utc)
        assert artifact['workflow_run']['head_sha'] == source and artifact['workflow_run']['id'] == int(run)
        raw = api('actions/artifacts/' + str(artifact['id']) + '/zip', True)
        assert len(raw) == artifact['size_in_bytes']
        assert 'sha256:' + digest(raw) == artifact['digest']
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            names = archive.namelist()
            assert len(names) == len(set(names))
            for item in names:
                path = PurePosixPath(item)
                assert not path.is_absolute() and '..' not in path.parts
                assert '\\' not in item and ':' not in item and not item.endswith('.key'), item
            result = json.loads(archive.read('result.json'))
            assert result['accepted'] and result['package'] == 'S07' and not result['adopted']
            assert (result['source_sha'], result['run_id'], result['attempt']) == (source, run, attempt)
            assert not result['actual_hosts'] and not result['complete_product']
            verify_guard(result['guard'])
            verify_preconditions(archive, result['preconditions'], source, run, attempt)
            verify_peers(result['three_peers'])
            tables[platform] = wire_table(result['three_peers'])
            rotations[platform] = {revision_id: body['parents']
                                   for revision_id, body in tables[platform].items()}
            inventory[platform] = result['three_peers']['remote']['revision_objects']
            platforms.append({
                'platform': platform,
                'producer_job': job[0]['id'],
                'artifact': {key: artifact[key] for key in ('id', 'name', 'digest', 'size_in_bytes', 'expires_at')},
                'three_peer_checks': result['three_peers']['count'],
                'wire_count': len(tables[platform]),
                'original_sha256': result['three_peers']['original']['sha256'],
                'preconditions': {key: value.get('count', value.get('protocol_checks'))
                                  for key, value in result['preconditions'].items()},
                'requests': result['three_peers']['remote'].get('requests'),
            })
    assert tables['Linux'] == tables['Windows'], 'wire table differs across platforms'
    assert rotations['Linux'] == rotations['Windows'], 'parent graph differs across platforms'
    assert inventory['Linux'] == inventory['Windows'], 'remote inventory differs across platforms'
    assert len(tables['Linux']) == 15
    summary = {
        'accepted': True,
        'package': 'S07',
        'source_sha': source,
        'run_id': run,
        'attempt': attempt,
        'platforms': platforms,
        'checks': CHECKS,
        'cross_platform_wire_table_equal': True,
        'cross_platform_parent_graph_equal': True,
        'cross_platform_remote_inventory_equal': True,
        'gaps': GAPS,
        'adopted': False,
        'actual_hosts': False,
        'complete_product': False,
    }
    folder = ROOT / 'build/reader-final-s07-summary'
    folder.mkdir(parents=True)
    (folder / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summary), flush=True)


def verify_guard(guard):
    assert guard['start'] == START and guard['frozen_tree_diff'] == 0
    for path in guard['changed_paths']:
        assert any(path.startswith(prefix) for prefix in ALLOWED), path
    assert guard['producer_manifest_rows'] > 0
    for key in ('raw7_run_py_sha256', 'raw7_tls_py_sha256', 'core_run_py_sha256',
                'g07_checker_sha256', 'revisions_header_sha256', 'sync_header_sha256'):
        assert len(guard['frozen_identities'][key]) == 64, key


def verify_preconditions(archive, preconditions, source, run, attempt):
    core = preconditions['capture_core']
    assert core['accepted'] and core['protocol_checks'] >= 20 and core['graph_checks'] >= 10
    assert core['consumer_sha256'] and core['pdf_sha256'] == \
        '5627a430fa04cbe11d38eb2682e336ef21e147d445753ed46ed11a7d5e3167cc'
    tls = preconditions['raw7_two_peer_tls']
    assert tls['accepted'] and tls['count'] == 9 and len(tls['exact_wires']) == 11
    session = preconditions['g07_original_session']
    assert session['accepted'] and session['count'] == 20
    assert sorted(session['checks']) == sorted(ORIGINAL_SESSION_CHECKS)
    boundaries = preconditions['g07_fault_boundaries']
    assert boundaries['accepted'] and boundaries['count'] == 21
    assert boundaries['checks'] == NEW_CHECKS, boundaries['checks']
    assert boundaries['uncovered']
    for key, name in (('capture_core', 'capture-core-result.json'),
                      ('raw7_two_peer_tls', 'raw7-two-peer-tls-result.json'),
                      ('g07_original_session', 'g07-original-session-result.json'),
                      ('g07_fault_boundaries', 'g07-boundaries-result.json')):
        body = archive.read('preconditions/' + name)
        assert digest(body) == preconditions[key]['result_sha256'], name
        report = json.loads(body)
        assert report['accepted'], name
        assert (report['source_sha'], str(report['run_id']), str(report['attempt'])) == \
            (source, run, attempt), name
    exact = sorted(tls['exact_wires'].items())
    assert exact, 'no exact wire identity recorded'


def verify_peers(peers):
    assert peers['accepted'] and peers['count'] == len(CHECKS)
    assert [item['name'] for item in peers['checks']] == CHECKS
    for item in peers['checks']:
        assert item['expected'] == EXPECTED[item['name']]
        assert item['actual'], item['name']
    assert peers['original']['bytes'] == 8845
    assert peers['original']['sha256'] == '5627a430fa04cbe11d38eb2682e336ef21e147d445753ed46ed11a7d5e3167cc'
    assert peers['remote']['all_authenticated']
    assert len(peers['remote']['fault_plan']) == 3
    assert len(peers['remote']['faults']) == 3
    assert peers['gaps'] == GAPS
    table = wire_table(peers)
    assert len(table) == 15, len(table)
    for revision_id, body in table.items():
        assert len(body['sha256']) == 64 and body['bytes'] > 0
        assert body['peers'] == {
            'sender': {'sha256': body['sha256'], 'bytes': body['bytes'], 'equal': True},
            'receiver-one': {'sha256': body['sha256'], 'bytes': body['bytes'], 'equal': True},
            'receiver-two': {'sha256': body['sha256'], 'bytes': body['bytes'], 'equal': True},
        }, revision_id
    exact = peers['checks'][7]['actual']
    assert exact['wire_count'] == 15
    chain = exact['chain']
    assert len(chain) == 5 and len(set(chain)) == 5
    ordered = json.loads(json.dumps(table))
    assert ordered[chain[1]]['parents'] == [chain[0]], 'old request is not parented to the capture head'
    assert ordered[chain[2]]['parents'] == [chain[1]], 'newer head is not parented to the old request'
    assert ordered[chain[3]]['parents'] == [chain[2]], 'parent of the ordered pair'
    assert ordered[chain[4]]['parents'] == [chain[3]], 'child of the ordered pair'


def wire_table(peers):
    return {row['id']: row for row in peers['checks'][7]['actual']['wires']}


if __name__ == '__main__':
    main()
