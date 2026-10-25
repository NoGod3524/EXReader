"""Authenticate original owner controls and actual upgraded-host evidence in Actions."""
import copy
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))
from check_parallel_integration import fetch, download_artifact_zip, require
sys.path.insert(0, str(ROOT / 'tests/apple_host/reading'))
from reading_contract import NATIVE_CHECKS

EXPECT = {
    'old-produce': ('old-original', 'produce', '3.40.0', 8),
    'old-control': ('old-original', 'consume', '3.40.0', 9),
    'new-original-rejection': ('new-original', 'refuse', '3.40.0', 9),
    'new-upgrade': ('new-compatible', 'consume', '3.40.0', 9),
    'new-produce': ('new-compatible', 'produce', '3.41.0', 8),
    'new-control': ('new-compatible', 'consume', '3.41.0', 9),
    'old-downgrade-rejection': ('old-original', 'refuse', '3.41.0', 9),
    'kill-before': ('old-original', 'kill-before', '3.40.0', None),
    'replay-before': ('new-compatible', 'replay-before', '3.40.0', 1),
    'kill-after': ('old-original', 'kill-after', '3.40.0', None),
    'replay-after': ('new-compatible', 'replay-after', '3.40.0', 1),
    'old-prefixed-produce': ('old-original', 'produce-prefixed', 'exreader-sdk-3.40.0', 8),
    'old-prefixed-accept': ('new-compatible', 'consume', 'exreader-sdk-3.40.0', 9),
    'old-prefixed-original-reject': ('new-original', 'refuse', 'exreader-sdk-3.40.0', 9),
    'old-prefixed-original340-reject': ('old-original', 'refuse', 'exreader-sdk-3.40.0', 9),
    'new-prefixed-produce': ('new-compatible', 'produce-prefixed', 'exreader-sdk-3.41.0', 8),
    'new-prefixed-accept': ('new-compatible', 'consume', 'exreader-sdk-3.41.0', 9),
    'new-prefixed-original-reject': ('new-original', 'refuse', 'exreader-sdk-3.41.0', 9),
}


def identity(value, source, run, attempt):
    require((value.get('source_sha'), str(value.get('run_id')), str(value.get('attempt'))) ==
            (source, str(run), str(attempt)), 'foreign source/run/attempt')


def validate(result, read, source, run, attempt):
    identity(result, source, run, attempt)
    require(result.get('accepted') is True and result.get('host_ui_accepted') is False and
            result.get('physical_device_accepted') is False and result.get('downgrade_accepted') is False and
            result.get('actual_android_host_interop_accepted') is False,
            'invalid acceptance scope')
    java_cases = result.get('java_policy_cases', [])
    observed = [line.removeprefix('CASE ') for line in read('java-policy-check.log').decode().splitlines() if line.startswith('CASE ')]
    require(len(java_cases) == len(set(java_cases)) == 20 and java_cases == observed and
            {'desktop-current-spelling', 'android-old-upgrade', 'old-runtime-no-new-bare-admission',
             'future-prefixed', 'duplicate-prefix'} <= set(java_cases), 'known Android policy cases missing')
    require(result['sdks'] == {'old': ['3.40.0', '9854061be331fe603a1822d9b2b36ee357154927'],
                               'new': ['3.41.0', 'edddc463c06ed5731195cdb8f06b2df6dff7699e']}, 'SDK source pair changed')
    require(set(result['programs']) == {'old-original', 'new-original', 'new-compatible'}, 'missing owner controls')
    require(result['programs']['old-original']['owner_sha256'] == result['programs']['new-original']['owner_sha256'] and
            result['programs']['new-compatible']['owner_sha256'] != result['programs']['new-original']['owner_sha256'],
            'original owner not reused across SDKs or fix not compiled')
    for name, program in result['programs'].items():
        require(hashlib.sha256(read(program['path'])).hexdigest() == program['sha256'], 'program bytes changed')
        product = json.loads(read(program['path'] + '.product.json'))
        require(product['binary_sha256'] == program['sha256'] and product['static_sdk_linked'] is False,
                'actual owner binary/provider identity differs')
    names = [p['name'] for p in result['phases']]
    require(len(names) == len(EXPECT) and set(names) == set(EXPECT), 'missing or repeated actual process phase')
    pids = [p['pid'] for p in result['phases']]
    require(len(pids) == len(set(pids)) and all(type(p) is int and p > 0 for p in pids), 'process isolation missing')
    wire_sets = {}
    for phase in result['phases']:
        name = phase['name']
        program, mode, tag, count = EXPECT[name]
        require((phase['program'], phase['mode'], phase['producer_parser']) == (program, mode, tag), 'phase contract changed')
        require(phase['exit'] == ({'kill-before': 73, 'kill-after': 74}.get(name, 0)), 'real process termination missing')
        if count is None:
            require(phase['report'] is None, 'killed process claimed a report')
            continue
        raw = json.loads(read(phase['report']))
        identity(raw, source, run, attempt)
        require(raw['accepted'] is True and raw['mode'] == mode and raw['producer_parser'] == tag and
                raw['sdk'] == result['programs'][program]['sdk'] and raw['pid'] == phase['pid'] and
                len(raw['checks']) == count and len(set(raw['checks'])) == count, 'actual phase report differs')
        require(raw['public_android_spelling_fixture'] is (mode == 'produce-prefixed'), 'fixture origin misrepresented')
        if mode in ('consume', 'refuse'):
            require(len(raw['records']) == 8 and all(r['parser'] == tag for r in raw['records']), 'retained genuine parser missing')
            wire_sets[name] = {(r['revision'], r['sha256'], r['bytes'], r['book'], r['parser']) for r in raw['records']}
    require(wire_sets['old-control'] == wire_sets['new-original-rejection'] == wire_sets['new-upgrade'],
            'upgrade used substitute records or rewrote wire')
    require(wire_sets['new-control'] == wire_sets['old-downgrade-rejection'], 'downgrade used substitute records')
    require(wire_sets['old-prefixed-accept'] == wire_sets['old-prefixed-original-reject'] ==
            wire_sets['old-prefixed-original340-reject'], 'old prefixed fixture identity differs')
    require(wire_sets['new-prefixed-accept'] == wire_sets['new-prefixed-original-reject'], 'current prefixed fixture identity differs')
    for label in ('old', 'new'):
        raw = json.loads(read('original-' + label + '/consumer/reading-review.json'))
        identity(raw, source, run, attempt)
        require(raw['accepted'] is True and raw['failed'] == raw['skipped'] == 0 and
                len(raw['checks']) == len(NATIVE_CHECKS) and
                {r['id'] for r in raw['checks']} == NATIVE_CHECKS and all(r['passed'] is True for r in raw['checks']),
                'original owner19 suite changed or failed')
    require(result['commands'] and all(c['exit'] == c['expected_exit'] for c in result['commands']), 'failed native command')


def main():
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only')
    source, run, attempt = os.environ['GITHUB_SHA'], os.environ['GITHUB_RUN_ID'], os.environ['GITHUB_RUN_ATTEMPT']
    jobs = fetch('actions/runs/%s/attempts/%s/jobs?per_page=100' % (run, attempt))['jobs']
    producer = [j for j in jobs if j['name'] == 'Actual Apple old and upgraded owner processes']
    require(len(producer) == 1 and producer[0]['head_sha'] == source and producer[0]['conclusion'] == 'success' and
            producer[0]['status'] == 'completed', 'producer source or terminal state differs')
    artifacts = fetch('actions/runs/%s/artifacts?per_page=100' % run)['artifacts']
    matches = [a for a in artifacts if a['name'] == 'apple-record-compatibility-%s-%s' % (run, attempt)]
    require(len(matches) == 1, 'missing or repeated artifact')
    artifact = fetch('actions/artifacts/%s' % matches[0]['id'])
    require(artifact['workflow_run']['head_sha'] == source and artifact['workflow_run']['id'] == int(run) and
            artifact['expired'] is False and 0 < artifact['size_in_bytes'] <= 256 * 1024 * 1024 and
            datetime.fromisoformat(artifact['expires_at'].replace('Z', '+00:00')) > datetime.now(timezone.utc), 'artifact identity/expiry/size')
    with tempfile.TemporaryFile() as stream:
        download_artifact_zip(artifact['id'], stream)
        stream.seek(0); data = stream.read()
    require(len(data) == artifact['size_in_bytes'] and artifact['digest'] == 'sha256:' + hashlib.sha256(data).hexdigest(), 'actual ZIP differs')
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        infos = archive.infolist()
        require(len(infos) <= 10000 and len({i.filename for i in infos}) == len(infos) and
                sum(i.file_size for i in infos) <= 512 * 1024 * 1024, 'unbounded or duplicate ZIP')
        for info in infos:
            path = PurePosixPath(info.filename)
            require(not path.is_absolute() and '..' not in path.parts and '\\' not in info.filename and ':' not in info.filename and
                    info.file_size <= 128 * 1024 * 1024 and (info.external_attr >> 16) & 0o170000 != 0o120000, 'unsafe ZIP member')
        def read(name):
            info = archive.getinfo(name)
            require(info.file_size <= 128 * 1024 * 1024, 'member too large')
            return archive.read(info)
        result = json.loads(read('result.json'))
        for name, claim in result['files'].items():
            raw = read(name)
            require(len(raw) == claim['bytes'] and hashlib.sha256(raw).hexdigest() == claim['sha256'], 'bound file differs: ' + name)
        validate(result, read, source, run, attempt)
        mutations = [dict(source_sha='foreign'), dict(attempt='0'), dict(accepted=False),
                     dict(host_ui_accepted=True), dict(downgrade_accepted=True), dict(phases=result['phases'][:-1])]
        for mutation in mutations:
            try:
                validate(result | mutation, read, source, run, attempt)
            except (ValueError, AssertionError):
                continue
            raise ValueError('compatibility verifier accepted a negative control')
    summary = dict(accepted=True, source_sha=source, run_id=run, attempt=attempt, producer_job=producer[0]['id'],
                   artifact={k: artifact[k] for k in ('id', 'name', 'size_in_bytes', 'digest', 'expires_at')},
                   native_phases=len(EXPECT), original_owner_cases_per_sdk=19, protocol_rejections=len(mutations),
                   upgrade_direction='3.40.0-to-3.41.0', host_ui_accepted=False, downgrade_accepted=False,
                   physical_device_accepted=False, android_policy_checks=len(result['java_policy_cases']),
                   actual_android_host_interop_accepted=False)
    output = Path('build/apple-record-summary')
    output.mkdir(parents=True)
    (output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary), flush=True)


if __name__ == '__main__':
    main()
