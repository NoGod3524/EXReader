"""Actions-only actual Apple raw sender, owner reopen and native HTTPS Session."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid
from tls_fixture import Fixture

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'build/apple-raw3'
EVIDENCE = OUT / 'evidence'
OLD_SENDER = '8bc248a0ac4f8773ad01917eec3b0a1961daffb2'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true' and sys.platform == 'darwin'
    EVIDENCE.mkdir(parents=True, exist_ok=False)
    commands, phases = [], []

    def run(argv, name, expected=0, env=None, timeout=1800):
        log = EVIDENCE / (name + '.log')
        with log.open('wb') as stream:
            process = subprocess.Popen(list(map(str, argv)), cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT)
            try: code = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait(); raise
        commands.append({'name': name, 'pid': process.pid, 'exit': code, 'expected': expected, 'argv': list(map(str, argv))})
        if (code == 0 if expected == 'failure' else code != expected):
            print('\n'.join(log.read_text(errors='replace').splitlines()[-160:]), flush=True)
            raise RuntimeError('Native command failed: ' + name)
        return process.pid

    # Complete original 18 process phases, Java policy20 and original owner19 on
    # both genuine installed SDKs. All use the default OFF package family.
    run([sys.executable, 'tests/apple_host/record_compatibility/run.py'], 'original-compatible-controls', timeout=3000)
    compatibility = ROOT / 'build/apple-record-compatibility'
    old_result = json.loads((compatibility / 'evidence/result.json').read_text())
    assert old_result['accepted'] and len(old_result['phases']) == 18 and len(old_result['java_policy_cases']) == 20
    shutil.copytree(compatibility / 'evidence', EVIDENCE / 'original-compatibility')
    sdk = compatibility / 'sdk-new'
    resources = compatibility / 'resources-old'
    resources = shutil.copytree(resources, EVIDENCE / 'inputs')
    shutil.copyfile(ROOT / 'tests/fixtures/pdf-public-text.pdf', resources / 'Sample.pdf')
    assert (resources / 'Sample.pdf').stat().st_size == 8845
    assert digest(resources / 'Sample.pdf') == '5627a430fa04cbe11d38eb2682e336ef21e147d445753ed46ed11a7d5e3167cc'
    raw = OUT / 'raw-products'
    run([sys.executable, 'tools/build_apple_product.py', '--sdk', sdk, '--sdk-version', '3.41.0',
         '--target', 'macos', '--product-prefix', raw, '--selector-bytes-candidate', '--build', OUT / 'raw-build'], 'raw-exact-family-build')
    sources = ['examples/apple/HostSDK.swift', 'examples/apple/HostModel.swift',
               'examples/apple/HostCatalog.swift', 'examples/apple/SelectableText.swift']
    old_source = EVIDENCE / 'OriginalSender.swift'
    old_source.write_bytes(subprocess.check_output(['git', 'show', OLD_SENDER + ':tests/apple_host/record_interop/RecordInterop.swift'], cwd=ROOT))
    programs = {}
    for mode, source in [('off', old_source), ('raw', ROOT / 'tests/apple_host/raw3/RawRecordInterop.swift')]:
        program = EVIDENCE / ('actual-' + mode + '-host')
        arguments = [sys.executable, 'tools/apple_swift.py', '--sdk', sdk]
        if mode == 'raw': arguments += ['--product-prefix', raw, '--selector-bytes-candidate']
        arguments += ['--', '-swift-version', '5', '-parse-as-library', '-O', '-D', 'EXR_APPLE_HOST_REVIEW',
                      '-I', sdk / 'include', '-L', sdk / 'lib', '-lexreader', '-Xlinker', '-rpath', '-Xlinker', sdk / 'lib',
                      *sources, source, '-o', program]
        run(arguments, mode + '-compile')
        programs[mode] = program
    default_symbols = subprocess.check_output(['nm', '-g', programs['off']], text=True)
    assert ' T _reader_revisions_open_raw_v3' not in default_symbols and ' T _reader_rc_apply_raw_v3' not in default_symbols
    provider = json.loads(Path(str(programs['raw']) + '.product.json').read_text())
    assert provider['selector_bytes_candidate'] and not provider['static_sdk_linked']

    bundle = EVIDENCE / 'sender-bundle'
    profiles = EVIDENCE / 'profiles'; profiles.mkdir()
    legacy = profiles / 'original-failed-sender'
    run([programs['off'], 'send', resources, legacy, EVIDENCE / 'original-failed-bundle', EVIDENCE / 'original-failed.json'],
        'original-actual-NUL-sender-failure', expected='failure')
    old_pending = legacy / 'reading-requests/request.json'
    old_pending_bytes = old_pending.read_bytes()
    assert json.loads(old_pending_bytes)['version'] == 1

    def phase(mode, profile, name=None, env=None, expected=0):
        name = name or mode
        report = EVIDENCE / (name + '.json')
        pid = run([programs['raw'], mode, resources, profile, bundle, report], name, expected=expected, env=env)
        if expected:
            phases.append({'name': name, 'mode': mode, 'pid': pid, 'exit': expected}); return
        value = json.loads(report.read_text())
        assert value['accepted'] and value['mode'] == mode and value['pid'] == pid
        assert (value['source_sha'], str(value['run_id']), str(value['attempt'])) == tuple(os.environ[k] for k in ('GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT'))
        phases.append({'name': name, 'mode': mode, 'pid': pid, 'exit': 0, 'report': report.name})
        return value

    phase('legacy-replay-refusal', legacy)
    assert old_pending.read_bytes() == old_pending_bytes
    sender = profiles / 'fresh-raw-sender'
    phase('send', sender)
    manifest = json.loads((bundle / 'manifest.json').read_text())
    assert len(manifest['reading_records']) == 11 and len(manifest['originals']) == 4
    assert all(json.loads((bundle / row['file']).read_bytes())['version'] == 1 for row in manifest['revisions'])
    assert all(row['anchor_version'] == (3 if row['mode'] == 3 else 2) for row in manifest['reading_records'])
    assert json.loads(old_pending_bytes)['revision'] not in {row['id'] for row in manifest['revisions']}
    phase('receive', profiles / 'independent-owner')
    phase('receive', profiles / 'independent-owner', 'independent-owner-reopen')
    phase('operations', profiles / 'source-version-and-NULL-operations')
    for boundary in ('before', 'after'):
        profile = profiles / ('raw-pending-' + boundary)
        phase('kill-' + boundary, profile, expected=-9)
        assert (profile / 'kill-boundary.txt').read_text() == boundary
        saved = (profile / 'saved-request.json').read_bytes()
        pending = (profile / 'reading-requests/request.json').read_bytes()
        assert json.loads(saved)['anchor_version'] == json.loads(pending)['anchor_version'] == 3
        phase('replay-' + boundary, profile)
        assert (profile / 'saved-request.json').read_bytes() == saved

    fixture = Fixture(ROOT / 'build/apple-raw3-private')
    try:
        env = dict(os.environ, EXR_RAW_DAV_ROOT=fixture.url, EXR_RAW_ACCOUNT=str(uuid.uuid4()), EXR_RAW_AUTH=fixture.auth)
        phase('session-push', sender, env=env)
        remote = fixture.entries
        for row in manifest['revisions']:
            wire = (bundle / row['file']).read_bytes()
            matches = [data for path, data in remote.items() if path.endswith('/' + row['id'] + '-' + row['sha256'] + '.json')]
            assert matches == [wire]
        for row in manifest['originals']:
            assert (bundle / row['file']).read_bytes() in remote.values()
        phase('session-receive', profiles / 'actual-session-receiver', env=env)
        phase('session-reopen', profiles / 'actual-session-receiver', env=env)
        assert fixture.requests and all(row['authenticated'] for row in fixture.requests)
        assert {'PUT', 'GET', 'PROPFIND', 'MKCOL'} <= {row['method'] for row in fixture.requests}
        (EVIDENCE / 'native-https.json').write_text(json.dumps({'requests': fixture.requests,
            'exact_revision_sha256': {row['id']: row['sha256'] for row in manifest['revisions']},
            'actual_host_session': True, 'tls_trust_checked': True}, indent=2) + '\n')
        for file in EVIDENCE.rglob('*'):
            if file.is_file(): assert fixture.auth.encode() not in file.read_bytes(), 'Authorization leaked into evidence'
    finally:
        fixture.close()
    assert len({row['pid'] for row in phases}) == len(phases)
    shutil.copyfile(OUT / 'guard.json', EVIDENCE / 'guard.json')
    shutil.copytree(raw, EVIDENCE / 'installed-raw-products')
    result = {'accepted': True, 'scope': 'actual macOS raw sender, independent owners and actual raw HTTPS account session only',
              'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'], 'attempt': os.environ['GITHUB_RUN_ATTEMPT'],
              'program_sha256': {name: digest(path) for name, path in programs.items()}, 'provider': provider,
              'original_compatibility_phases': 18, 'original_owner_cases_per_sdk': 19, 'java_policy_cases': 20,
              'real_reading_records': 11, 'originals': 4, 'pending_original_sha256': hashlib.sha256(old_pending_bytes).hexdigest(),
              'phases': phases, 'commands': commands, 'actual_android_interop_accepted': False,
              'physical_device_execution': False, 'complete_product': False}
    result['files'] = {file.relative_to(EVIDENCE).as_posix(): {'bytes': file.stat().st_size, 'sha256': digest(file)}
                       for file in EVIDENCE.rglob('*') if file.is_file()}
    (EVIDENCE / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: value for key, value in result.items() if key not in ('commands', 'files', 'provider')}), flush=True)


if __name__ == '__main__':
    main()
