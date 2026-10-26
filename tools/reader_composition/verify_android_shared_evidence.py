"""Verify immutable Actions evidence from two separately scoped source revisions."""
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import urllib.request
import zipfile
from datetime import datetime, timezone

sys.path.insert(0, 'tests/reader_next_s14')
from cases import ORIGINAL_COMMON, ORIGINAL_POSIX, ORIGINAL_WINDOWS, S14_COMMON, S14_HARNESS

REPO = 'NoGod3524/EXReader'
RUNS = {
    40413221092: ('532b9f0dd6ce3e2ee94ec7b002e57f8a43a3bce9',
                  {f'{s} on {o}' for s in ('font', 'export') for o in ('ubuntu-22.04', 'windows-2022', 'macos-15')}),
    40413886507: ('c9e4b3ac1634748179ae33cba48a0b20df950a22', {'frozen'}),
}
OUTPUT = Path('build/android-shared-evidence-verification.json')
result = {'accepted': False, 'scope': 'two separate source revisions; no same-source acceptance', 'runs': {}, 'failures': []}

def require(value, message):
    if not value:
        raise ValueError(message)

def pairs(items):
    d = {}
    for k, v in items:
        require(k not in d, 'duplicate JSON key: ' + k)
        d[k] = v
    return d

def decode(data):
    return json.loads(data, object_pairs_hook=pairs)

def api(path):
    req = urllib.request.Request('https://api.github.com/' + path, headers={
        'Authorization': 'Bearer ' + os.environ['GH_TOKEN'],
        'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28'})
    with urllib.request.urlopen(req, timeout=180) as response:
        return response.read()

def identity(report, sha, run):
    require(report.get('accepted') is True, 'report not accepted')
    require(report.get('source_sha') == sha and str(report.get('run_id')) == str(run)
            and str(report.get('attempt')) == '1', 'report source/run/attempt mismatch')
    require(not report.get('failures'), 'report contains failures')

def digest(data):
    return hashlib.sha256(data).hexdigest()

def member(z, suffix):
    matches = [n for n in z.namelist() if n == suffix or n.endswith('/' + suffix)]
    require(len(matches) == 1, 'missing or ambiguous member ' + suffix + ': ' + repr(matches))
    return z.read(matches[0])

def cases(report, expected, exact=False):
    found = report['checks']
    require(len(found) == len(set(found)), 'duplicate checks')
    require(set(expected) == set(found) if exact else set(expected) <= set(found), 'required checks mismatch')

def verify_artifact(a, sha, run):
    raw = api(f'repos/{REPO}/actions/artifacts/{a["id"]}/zip')
    require(len(raw) == a['size_in_bytes'] and a['digest'] == 'sha256:' + digest(raw), 'ZIP size/digest mismatch')
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        names = z.namelist()
        require(len(names) == len(set(names)), 'duplicate ZIP members')
        name = a['name']
        source = decode(member(z, 'frozen-source.json' if run == 40413886507 else 'shared-source.json'))
        require(source.get('source') == sha and source.get('ok') is True, 'source guard mismatch')
        checked = {}
        if '-font-' in name:
            platform = next(p for p in ('Linux', 'Windows', 'macOS') if f'-{p}-' in name)
            report = decode(member(z, 's14-evidence/result.json'))
            identity(report, sha, run)
            require(report['platform'] == {'Linux':'Linux', 'Windows':'Windows', 'macOS':'Darwin'}[platform], 'font platform mismatch')
            expected = ORIGINAL_COMMON + S14_COMMON + S14_HARNESS + (ORIGINAL_WINDOWS if platform == 'Windows' else ORIGINAL_POSIX)
            cases(report, expected, exact=True)
            require(report['sdk_version'] == '3.41.0' and report['sdk_commit'] == sha, 'font SDK mismatch')
            for item in report['identities']:
                data = member(z, 's14-evidence/' + item['path'])
                require(len(data) == item['bytes'] and digest(data) == item['sha256'], 'font identity mismatch: ' + item['path'])
                if item['path'].startswith('binary/') or ('installed/' in item['path'] and item['path'].endswith(('.a', '.lib'))):
                    checked[item['path']] = digest(data)
            require(len(checked) >= 3, 'font binaries missing')
            preload = decode(member(z, 's14-evidence/preloaded/result.json'))
            identity(preload, sha, run)
            require(len(preload['cases']) == 4 and all(c['passed'] for c in preload['cases']), 'font preload cases')
        elif '-export-' in name:
            platform = next(p for p in ('Linux', 'Windows', 'macOS') if f'-{p}-' in name)
            report = decode(member(z, 's15-evidence/result.json'))
            identity(report, sha, run)
            require(report['platform'] == platform, 'export platform mismatch')
            cases(report, json.loads(Path('tests/reader_next_s15/cases.json').read_text()))
            require(set(report['binary_identities']) == {'probe', 'c_consumer', 'module'}, 'export binaries missing')
            for role, item in report['binary_identities'].items():
                data = member(z, item['member'])
                require(len(data) == item['bytes'] and digest(data) == item['sha256'], 'export binary mismatch: ' + role)
                checked[role] = digest(data)
        else:
            report = decode(member(z, 's15-frozen-work/frozen.json'))
            identity(report, sha, run)
            require(report['platform'] == 'Linux' and report['sdk'] == {'version':'3.40.0','abi':1}, 'frozen SDK mismatch')
            cases(report, ['frozen_sdk_340_install_identity', 'frozen_sdk_default_pin_accepted', 'frozen_sdk_explicit_341_refused', 'frozen_sdk_c_abi_link', 'frozen_sdk_original_byte_identity', 'frozen_sdk_existing_target_not_overwritten'], exact=True)
            data = member(z, 's15-frozen-work/consumer/original-export-c-consumer')
            require(len(data) > 0, 'frozen binary empty')
            # The frozen report records a directory, not a binary hash; record the actual digest without claiming a comparison.
            checked['frozen_c_consumer_observed_only'] = digest(data)
            origin = decode(member(z, 's15-frozen-work/target-provenance/result.json'))
            identity(origin, sha, run)
            require(len(origin['cases']) == 16 and all(c['passed'] for c in origin['cases'].values()), 'origin cases')
        return {'id': a['id'], 'zip_bytes': len(raw), 'zip_sha256': digest(raw), 'binary_sha256': checked}

try:
    for run, (sha, expected_jobs) in RUNS.items():
        base = f'repos/{REPO}/actions/runs/{run}'
        info = decode(api(base + '/attempts/1'))
        require(info['id'] == run and info['run_attempt'] == 1 and info['head_sha'] == sha
                and info['status'] == 'completed' and info['conclusion'] == 'success', 'run mismatch')
        jobs = decode(api(base + '/attempts/1/jobs?per_page=100'))['jobs']
        require(len(jobs) == len(expected_jobs) and {j['name'] for j in jobs} == expected_jobs
                and all(j['status'] == 'completed' and j['conclusion'] == 'success' for j in jobs), 'jobs mismatch')
        artifacts = decode(api(base + '/artifacts?per_page=100'))['artifacts']
        expected_names = ({f'android-shared-{s}-{o}-{run}-1' for s in ('font','export') for o in ('Linux','Windows','macOS')}
                          if len(expected_jobs) == 6 else {f'android-shared-frozen-340-{run}-1'})
        require(len(artifacts) == len(expected_names) and {a['name'] for a in artifacts} == expected_names
                and len({a['id'] for a in artifacts}) == len(artifacts), 'artifact set mismatch')
        entry = {'source': sha, 'attempt': 1, 'jobs': sorted(expected_jobs), 'artifacts': {}}
        result['runs'][str(run)] = entry
        for a in artifacts:
            require(not a['expired'] and datetime.fromisoformat(a['expires_at'].replace('Z','+00:00')) > datetime.now(timezone.utc)
                    and a['size_in_bytes'] > 0 and a['workflow_run']['id'] == run
                    and a['workflow_run']['head_sha'] == sha, 'artifact metadata mismatch')
            entry['artifacts'][a['name']] = verify_artifact(a, sha, run)
    result['accepted'] = True
except Exception as exc:
    result['failures'].append(repr(exc))
finally:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
raise SystemExit(0 if result['accepted'] else 1)
