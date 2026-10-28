"""Actions-only aggregate admission; no platform may borrow another run's proof."""
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from check_parallel_integration import fetch, download_artifact_zip

assert os.environ.get('GITHUB_ACTIONS') == 'true'
source, run, attempt = (os.environ[k] for k in ('GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT'))
out = ROOT / 'build/sdk342-aggregate'
out.mkdir(parents=True, exist_ok=True)
report = dict(source_sha=source, run_id=run, attempt=attempt, accepted=False, artifacts={}, checks={}, failures=[],
              physical_device=False, formal_release=False)

def read_artifact(artifacts, name, member):
    matches = [a for a in artifacts if a['name'] == name and not a['expired']]
    assert len(matches) == 1, 'missing or duplicate artifact: ' + name
    item = matches[0]
    assert item['workflow_run']['id'] == int(run) and item['workflow_run']['head_sha'] == source
    raw = download_artifact_zip(item['id'])
    digest = hashlib.sha256(raw).hexdigest()
    assert len(raw) == item['size_in_bytes'] and item['digest'] == 'sha256:' + digest
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        names = z.namelist()
        assert len(names) == len(set(names))
        assert all(not PurePosixPath(n).is_absolute() and '..' not in PurePosixPath(n).parts and '\\' not in n for n in names)
        data = json.loads(z.read(member))
    report['artifacts'][name] = dict(id=item['id'], sha256=digest,
        url=f"https://github.com/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{run}/artifacts/{item['id']}")
    return data

def same(record):
    assert record['source_sha'] == source and str(record['run_id']) == run and str(record['attempt']) == attempt

try:
    statuses = {name: os.environ['RESULT_' + name.upper()] for name in ('windows','gtk','android','records','apple')}
    report['checks']['upstream_jobs'] = statuses
    assert all(value == 'success' for value in statuses.values()), statuses
    artifacts = fetch(f'actions/runs/{run}/artifacts?per_page=100')['artifacts']
    specs = {
        'windows': (f'f06-windows-sdk342-{run}-{attempt}', 'windows/result.json'),
        'gtk': (f'gtk-sdk342-authentication-{run}-{attempt}', 'identity.json'),
        'android': (f'android-sdk342-package-{run}-{attempt}', 'f06/android/result.json'),
        'records': (f'android-sdk342-record-probe-{run}-{attempt}', 'build/android-sdk342-record/evidence/report.json'),
        'apple': (f'apple-sdk342-authentication-{run}-{attempt}', 'summary.json'),
    }
    records = {key: read_artifact(artifacts, *value) for key,value in specs.items()}
    for record in records.values(): same(record)
    assert records['windows']['passed'] is True and records['windows']['target'] == 'windows'
    assert records['gtk']['accepted'] is True and records['gtk']['sdk_version'] == '3.42.0'
    assert records['android']['passed'] is True and records['android']['target'] == 'android'
    assert records['records']['passed'] is True and records['records']['host_compatibility_accepted'] is True
    assert records['apple']['accepted'] is True
    report['checks']['five_gates_authenticated'] = True
    # This is the original six-target F06 authenticator's output. The Apple
    # simulator archive alone is not an iPhone or iPad installation result.
    assert os.environ['RESULT_F06'] == 'success', 'original six-target F06 authentication did not pass'
    assert os.environ['RESULT_APPLE_F06'] == 'success', 'Apple F06 producer/launch did not pass'
    six = read_artifact(artifacts, f'f06-authenticated-{run}-{attempt}', 'summary.json')
    same(six)
    assert six['accepted'] is True and set(six['targets']) == {'windows','linux','macos','android','iphone','ipad'}
    for name, value in six['targets'].items():
        target = value['result']; same(target)
        assert target['target'] == name and target['passed'] is True
        artifact_name = f'f06-{name}-{run}-{attempt}'
        manifest = read_artifact(artifacts, artifact_name, 'manifest.json')
        assert manifest['source_sha'] == source and manifest['target'] == name
        assert manifest['sdk_version'] == '3.42.0' and manifest['producer']['sdk_version'] == '3.42.0'
        assert manifest['producer']['source_sha'] == source
        assert str(manifest['provenance']['run_id']) == run and str(manifest['provenance']['attempt']) == attempt
        assert value['github_artifact_id'] == report['artifacts'][artifact_name]['id']
        assert value['github_artifact_digest'] == 'sha256:' + report['artifacts'][artifact_name]['sha256']
    mac_launch = read_artifact(artifacts, f'f06-macos-{run}-{attempt}', 'launch.json')
    same(mac_launch)
    assert mac_launch['passed'] is True and mac_launch['executable_sha256'] == six['targets']['macos']['result']['program_sha256']
    report['checks']['original_six_target_f06'] = True
    report['accepted'] = True
except Exception as error:
    report['failures'].append(str(error))
finally:
    (out/'summary.json').write_text(json.dumps(report, indent=2, sort_keys=True)+'\n')
    print(json.dumps(report, indent=2), flush=True)
if not report['accepted']:
    raise SystemExit('SDK 3.42 aggregate admission failed; see retained summary')
