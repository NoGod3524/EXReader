"""Actions-only: actual macOS receivers consume the same-run actual Android sender, in fresh processes.

Reuses the exact executable, SDK and resources produced by mac_send.py (restored from its tar at
the identical absolute prefix) so sender and receiver program identities can be compared.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / 'tests/reader_android_raw3'))
sys.path.insert(0, str(ROOT / 'tests/apple_host/raw3'))
from bundle import verify, parse  # noqa: E402
from tls_fixture import Fixture  # noqa: E402
import fetch  # noqa: E402

OUT = ROOT / 'build/c07-mac'
EVIDENCE = ROOT / 'build/c07-mac-receive/evidence'
PROGRAM = OUT / 'evidence/actual-c07-host'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def serve(fixture, root, manifest):
    entries = {}
    for row in manifest['originals']:
        entries['/dav/exreader-sync-v1/objects/' + row['sha256'][:2] + '/' + row['sha256'] + '.' + row['format']] = (root / row['file']).read_bytes()
    for row in manifest['revisions']:
        entries['/dav/exreader-sync-v1/revisions/' + row['id'][:2] + '/' + row['id'] + '-' + row['sha256'] + '.json'] = (root / row['file']).read_bytes()
    with fixture.lock:
        fixture.entries = dict(entries)
        fixture.directories = {'/dav/'}
        for path in entries:
            parts = path.strip('/').split('/')[:-1]
            for count in range(1, len(parts) + 1):
                fixture.directories.add('/' + '/'.join(parts[:count]) + '/')
    return entries


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true' and sys.platform == 'darwin'
    EVIDENCE.mkdir(parents=True, exist_ok=False)
    ident = fetch.IDENTITY
    mac_identity, _ = fetch.download('c07-mac-sender', ROOT / 'build/c07/mac-sender')
    mac = parse((ROOT / 'build/c07/mac-sender/result.json').read_bytes())
    assert mac['accepted'] and all(str(mac[k]) == str(v) for k, v in ident.items())
    assert PROGRAM.is_file() and digest(PROGRAM) == mac['program_sha256'], 'restored toolchain is not the exact sender program'
    android_identity, _ = fetch.download('c07-android-sender', ROOT / 'build/c07/android-sender')
    android = ROOT / 'build/c07/android-sender'
    verified = verify(lambda name: (android / 'bundle' / name).read_bytes())
    manifest = verified['manifest']
    sender = manifest['sender']
    assert sender['platform'] == 'android' and verified['originals'] == 4 and verified['reading_records'] == 11 and verified['revisions'] == 19
    assert all(str(sender[k]) == str(v) for k, v in ident.items())
    common = json.loads((ROOT / 'build/c07/common-fixtures/common.json').read_text())['originals']
    assert {row['role']: row['sha256'] for row in common} == {row['role']: row['sha256'] for row in manifest['originals']}
    null_manifest = parse((android / 'null-bundle/manifest.json').read_bytes())
    assert null_manifest['purpose'] == 'authentic-android-null-negative' and null_manifest['sender']['platform'] == 'android'
    assert all(str(null_manifest['sender'][k]) == str(v) for k, v in ident.items())
    assert null_manifest['sender']['apk_sha256'] == sender['apk_sha256'] and null_manifest['sender']['sdk_dso_sha256'] == sender['sdk_dso_sha256']
    resources = OUT / 'resources'
    os.chmod(PROGRAM, 0o755)
    commands, phases = [], []

    def run(argv, name, env=None, timeout=3000):
        log = EVIDENCE / (name + '.log')
        with log.open('wb') as stream:
            process = subprocess.Popen(list(map(str, argv)), cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT)
            try:
                code = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait(); raise
        commands.append({'name': name, 'pid': process.pid, 'exit': code, 'argv': list(map(str, argv))})
        if code != 0:
            print('\n'.join(log.read_text(errors='replace').splitlines()[-200:]), flush=True)
            raise RuntimeError('Native command failed: ' + name)
        return process.pid

    def phase(mode, profile, bundle, name, env=None):
        report = EVIDENCE / (name + '.json')
        pid = run([PROGRAM, mode, resources, profile, bundle, report], name, env=env)
        value = json.loads(report.read_text())
        assert value['accepted'] and value['mode'] == mode and value['pid'] == pid
        assert (value['source_sha'], str(value['run_id']), str(value['attempt'])) == tuple(os.environ[k] for k in ('GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT'))
        assert value['program_sha256'] == mac['program_sha256']
        phases.append({'name': name, 'mode': mode, 'pid': pid, 'exit': 0, 'report': report.name})
        return value

    profiles = EVIDENCE / 'profiles'
    profiles.mkdir()
    bundle = android / 'bundle'
    owner = profiles / 'independent-owner'
    phase('receive', owner, bundle, 'android-receive')
    phase('receive', owner, bundle, 'android-receive-reopen')
    fixture = Fixture(ROOT / 'build/c07-mac-receive-private')
    try:
        env = dict(os.environ, EXR_RAW_DAV_ROOT=fixture.url, EXR_RAW_ACCOUNT=str(uuid.uuid4()), EXR_RAW_AUTH=fixture.auth)
        served = serve(fixture, bundle, manifest)
        session = profiles / 'actual-session-receiver'
        phase('session-receive', session, bundle, 'android-session-receive', env=env)
        phase('session-reopen', session, bundle, 'android-session-reopen', env=env)
        assert set(fixture.entries) == set(served) and all(fixture.entries[path] == body for path, body in served.items())
        assert fixture.requests and all(row['authenticated'] for row in fixture.requests)
        assert {'GET', 'PROPFIND'} <= {row['method'] for row in fixture.requests}
        (EVIDENCE / 'native-https.json').write_text(json.dumps({
            'requests': [{'method': r['method'], 'path': r['path'], 'authenticated': r['authenticated']} for r in fixture.requests],
            'served_sha256': {path.rsplit('/', 1)[-1]: hashlib.sha256(body).hexdigest() for path, body in served.items()},
            'actual_host_account_session': True, 'tls_trust_checked': True}, indent=2) + '\n')
        for file in EVIDENCE.rglob('*'):
            if file.is_file():
                assert fixture.auth.encode() not in file.read_bytes(), 'Authorization leaked into evidence'
    finally:
        fixture.close()
    null_profile = profiles / 'android-null-owner'
    phase('null-receive', null_profile, android / 'null-bundle', 'android-null-receive')
    phase('null-receive', null_profile, android / 'null-bundle', 'android-null-reopen')
    assert len({row['pid'] for row in phases}) == len(phases) == 6
    result = {'accepted': True, 'scope': 'C07 actual macOS receivers of the same-run actual Android sender only',
              'source_sha': ident['source_sha'], 'run_id': ident['run_id'], 'attempt': ident['attempt'],
              'direction': 'android->macos', 'program_sha256': digest(PROGRAM), 'sender_program_sha256': mac['program_sha256'],
              'android_manifest_sha256': verified['manifest_sha256'], 'android_null_manifest_sha256': digest(android / 'null-bundle/manifest.json'),
              'android_sender': sender, 'upstream': {'mac_sender': mac_identity, 'android_sender': android_identity},
              'phases': phases, 'commands': commands}
    shutil.copyfile(ROOT / 'build/c07/mac-receive/guard.json', EVIDENCE / 'guard.json')
    result['files'] = {file.relative_to(EVIDENCE).as_posix(): {'bytes': file.stat().st_size, 'sha256': digest(file)}
                       for file in EVIDENCE.rglob('*') if file.is_file()}
    (EVIDENCE / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k not in ('commands', 'files', 'android_sender')}), flush=True)


if __name__ == '__main__':
    main()
