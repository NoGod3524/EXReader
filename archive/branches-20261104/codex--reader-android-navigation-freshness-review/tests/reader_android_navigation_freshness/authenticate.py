"""Actions-only authentication of the failed producer's real baseline/test APKs."""
import hashlib
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import zipfile

BASE = 'bd8c3638019280bea6496b778339abf04629bd27'
RUN, ATTEMPT, JOB = 40229070687, 1, 121276697202
PINS = [
    (12612429508, 'reader-android-raw3-40229070687-1', 113333967,
     'e5e26466dd2fb3960383d3efc29ac150cbe87bbf57409aa0653fa0f6ce7d9e14'),
    (12612434660, 'reader-android-page-theme-40229070687-1', 126519194,
     'de421688f2f61b72f93e305cdf69983c4574f0a78e858c5e4af4681377039228')]
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'build/navigation-freshness'


def need(value, message):
    if not value:
        raise RuntimeError(message)


def api(path, raw=False):
    body = subprocess.check_output(['gh', 'api', 'repos/NoGod3524/EXReader/' + path], timeout=300)
    return body if raw else json.loads(body)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    need(os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only')
    source = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    need(source == os.environ['GITHUB_SHA'], 'actual checkout differs')
    changes = subprocess.check_output(['git', 'diff', '--name-only', BASE, 'HEAD'], text=True).splitlines()
    need(all(path.startswith('tests/reader_android_navigation_freshness/')
             or path == '.github/workflows/reader-android-navigation-freshness.yml' for path in changes), 'unowned source change')
    record = api(f'actions/runs/{RUN}/attempts/{ATTEMPT}')
    need(record['head_sha'] == BASE and record['status'] == 'completed' and record['conclusion'] == 'failure', 'failed producer identity differs')
    jobs = api(f'actions/runs/{RUN}/attempts/{ATTEMPT}/jobs?per_page=100')['jobs']
    job = [item for item in jobs if item['id'] == JOB]
    need(len(job) == 1 and job[0]['name'] == 'android' and job[0]['conclusion'] == 'failure'
         and job[0]['head_sha'] == BASE and job[0]['run_attempt'] == ATTEMPT, 'original failed job differs')
    OUT.mkdir(parents=True, exist_ok=True)
    evidence = OUT / 'evidence'; evidence.mkdir(exist_ok=True)
    found, artifacts = {}, []
    for identifier, name, size, digest in PINS:
        metadata = api(f'actions/artifacts/{identifier}')
        need(metadata['name'] == name and metadata['size_in_bytes'] == size
             and metadata['digest'] == 'sha256:' + digest and not metadata['expired']
             and datetime.fromisoformat(metadata['expires_at'].replace('Z', '+00:00')) > datetime.now(timezone.utc)
             and metadata['workflow_run']['id'] == RUN and metadata['workflow_run']['head_sha'] == BASE,
             'original ZIP metadata differs')
        body = api(f'actions/artifacts/{identifier}/zip', raw=True)
        need(len(body) == size and hashlib.sha256(body).hexdigest() == digest, 'original ZIP bytes differ')
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            names = archive.namelist()
            need(len(names) == len(set(names)) <= 30000 and sum(item.file_size for item in archive.infolist()) < 3 * 1024**3,
                 'duplicate or oversized original ZIP')
            for item in archive.infolist():
                path = PurePosixPath(item.filename)
                need(not path.is_absolute() and '..' not in path.parts and '\\' not in item.filename
                     and (item.external_attr >> 16) & 0o170000 != 0o120000, 'unsafe original ZIP member')
            if identifier == PINS[0][0]:
                hits = [item for item in names if item.endswith('baseline/host-debug.apk')]
                need(len(hits) == 1, 'original ZIP lacks a unique actual baseline/OFF host APK; raw APK will not substitute')
                path = OUT / 'original-baseline.apk'; path.write_bytes(archive.read(hits[0])); found['baseline'] = str(path)
                raw_hits = [item for item in names if item.endswith('apks/host-debug.apk')]
                need(len(raw_hits) == 1 and hashlib.sha256(archive.read(raw_hits[0])).hexdigest() != sha(path),
                     'baseline and raw must be distinct original APKs')
            else:
                # Restore the original installed SDK/modules and fixtures at their
                # recorded paths; no SDK source is rebuilt by this diagnostic.
                tracked = set(subprocess.check_output(['git', 'ls-files'], text=True).splitlines())
                need(not any(name in tracked for name in names), 'original artifact would overwrite tracked source')
                archive.extractall(ROOT)
                hits = [item for item in names if item.endswith('android-navigation/test-apks/navigation-ui.apk')]
                need(len(hits) == 1, 'original navigation instrumentation APK is absent')
                path = OUT / 'original-navigation.apk'; path.write_bytes(archive.read(hits[0])); found['navigation'] = str(path)
            artifacts.append({key: metadata[key] for key in ('id', 'name', 'size_in_bytes', 'digest', 'expires_at')})
    need(set(found) == {'baseline', 'navigation'}, 'actual original APK pair incomplete')
    subprocess.run(['git', 'diff', '--exit-code'], check=True)
    inventory = {'diagnostic_source': source, 'producer_source': BASE, 'producer_run': RUN,
                 'producer_attempt': ATTEMPT, 'producer_job': JOB, 'artifacts': artifacts,
                 'apks': {key: {'path': path, 'sha256': sha(path), 'bytes': Path(path).stat().st_size}
                          for key, path in found.items()}, 'accepted': False, 'complete_product': False}
    (evidence / 'authentication.json').write_text(json.dumps(inventory, indent=2) + '\n')
    print(json.dumps(inventory), flush=True)


if __name__ == '__main__':
    main()
