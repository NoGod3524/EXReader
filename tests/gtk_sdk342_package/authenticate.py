"""Authenticate original artifact on Actions; fail closed on any missing gate."""
import hashlib
import json
import os
from pathlib import Path
import urllib.request
import zipfile

assert os.environ.get('GITHUB_ACTIONS') == 'true'
repo = os.environ['GITHUB_REPOSITORY']; run = os.environ['GITHUB_RUN_ID']; attempt = os.environ['GITHUB_RUN_ATTEMPT']; sha = os.environ['GITHUB_SHA']
out = Path('build/gtk-sdk342-auth'); out.mkdir(parents=True, exist_ok=True)
def get(url):
    request = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + os.environ['GH_TOKEN'], 'Accept': 'application/vnd.github+json'})
    return urllib.request.urlopen(request).read()
api = 'https://api.github.com/repos/' + repo
artifacts = json.loads(get(api + '/actions/runs/' + run + '/artifacts'))['artifacts']
selected = [a for a in artifacts if a['name'] == 'gtk-sdk342-package-' + run + '-' + attempt]
assert len(selected) == 1
artifact = selected[0]
archive = get(artifact['archive_download_url']); (out / 'original.zip').write_bytes(archive)
root = out / 'original'
with zipfile.ZipFile(out / 'original.zip') as zipped: zipped.extractall(root)
def read(path): return json.loads((root / path).read_text())
def digest(path): return hashlib.sha256((root / path).read_bytes()).hexdigest()
checks = {}
for path in ('gtk-sdk342/source.json', 'gtk-sdk342/build.json', 'f06/linux/result.json'):
    data = read(path)
    checks[path] = data.get('passed') is True and data.get('source_sha') == sha and str(data.get('run_id')) == run and str(data.get('attempt')) == attempt
build = read('gtk-sdk342/build.json'); pkg = read('f06/linux/result.json'); raw = read('gtk-raw-wave3/result.json')
checks['raw_legacy'] = raw['accepted'] and raw['source'] == sha and raw['legacy_host']['configured_and_linked']
checks['same_program'] = build['program_sha256'] == pkg['program_sha256'] == digest('gtk-raw-wave3/retained-host/gtk-host/exreader-linux')
nav = read('gtk-navigation-ui/result.json'); batch = read('gtk-batch-ui/report.json')
checks['navigation_gui'] = nav['navigation_scope_passed'] is True
checks['batch_gui'] = batch['batch_import_scope_passed'] is True and batch['checks_failed'] == 0 and batch['source_sha'] == sha and batch['program_sha256'] == build['program_sha256']
checks['producer_sdk'] = read('f06/linux/configuration.json')['producer']['sdk_version'] == '3.42.0'
checks['upstream_job'] = os.environ['PRODUCER_RESULT'] == 'success'
report = dict(source_sha=sha, run_id=run, attempt=attempt, artifact=artifact,
    original_archive_sha256=hashlib.sha256(archive).hexdigest(), checks=checks, accepted=all(checks.values()),
    raw_backend_checks=raw['raw_backend']['check_count'], navigation_checks=nav.get('count'), batch_checks=batch['checks_total'],
    program_sha256=build['program_sha256'], sdk_version='3.42.0', physical_device=False, release=False)
(out / 'identity.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report), flush=True)
assert report['accepted'], checks
