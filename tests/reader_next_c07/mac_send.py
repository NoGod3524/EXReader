"""Actions-only: build the common target SDK and raw host on macOS, run the actual sender phases.

Builds one SDK from this exact source, the independent raw product family, and the C07 copy of
the original raw3 driver; then the actual HostSession sender, NULL/source-version operations and
the actual HostAccountSession HTTPS push (256 shards) run as separate real processes.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests/apple_host/raw3'))
sys.path.insert(0, str(ROOT / 'tools'))
from tls_fixture import Fixture  # noqa: E402  (original TLS fixture, reused unchanged)
from host_font import fetch as host_font  # noqa: E402

OUT = ROOT / 'build/c07-mac'
EVIDENCE = OUT / 'evidence'
COMMON = ROOT / 'build/c07/common-fixtures'
FIXTURE_NAMES = {'txt': 'Records.txt', 'epub': 'Bounded.epub', 'pdf': 'Sample.pdf', 'cbz': 'NavigationPages.cbz'}
PDF = '5627a430fa04cbe11d38eb2682e336ef21e147d445753ed46ed11a7d5e3167cc'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true' and sys.platform == 'darwin'
    EVIDENCE.mkdir(parents=True, exist_ok=False)
    commands, phases = [], []

    def run(argv, name, expected=0, env=None, timeout=3000):
        log = EVIDENCE / (name + '.log')
        with log.open('wb') as stream:
            process = subprocess.Popen(list(map(str, argv)), cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT)
            try:
                code = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait(); raise
        commands.append({'name': name, 'pid': process.pid, 'exit': code, 'expected': expected, 'argv': list(map(str, argv))})
        if code != expected:
            print('\n'.join(log.read_text(errors='replace').splitlines()[-200:]), flush=True)
            raise RuntimeError('Native command failed: ' + name)
        return process.pid

    # One SDK built from this exact target source (guard.py proved the SDK tree equals the approved 3.41).
    sdk = OUT / 'sdk'
    run(['cmake', '-S', ROOT, '-B', OUT / 'sdk-build', '-DCMAKE_BUILD_TYPE=Release', '-DEXR_BUILD_TESTS=OFF',
         '-DEXR_BUILD_TOOLS=OFF', '-DEXR_ENABLE_AAC=OFF'], 'sdk-configure')
    run(['cmake', '--build', OUT / 'sdk-build', '--parallel', '4'], 'sdk-build')
    run(['cmake', '--install', OUT / 'sdk-build', '--prefix', sdk], 'sdk-install')
    raw = OUT / 'raw-products'
    run([sys.executable, 'tools/build_apple_product.py', '--sdk', sdk, '--sdk-version', '3.41.0', '--target', 'macos',
         '--product-prefix', raw, '--selector-bytes-candidate', '--build', OUT / 'raw-build'], 'raw-exact-family-build')

    # Resources: original font/schema plus the four frozen common originals (same bytes as Android).
    resources = OUT / 'resources'
    resources.mkdir()
    font = host_font(ROOT / 'build/host-font-cache')
    shutil.copyfile(font / 'Reader.otf', resources / 'Reader.otf')
    shutil.copyfile(ROOT / 'apps/reader/store/001_catalog.sql', resources / 'reader-catalog-v1.sql')
    common = json.loads((COMMON / 'common.json').read_text())['originals']
    for row in common:
        data = (COMMON / row['file']).read_bytes()
        assert len(data) == row['bytes'] and hashlib.sha256(data).hexdigest() == row['sha256']
        (resources / FIXTURE_NAMES[row['role']]).write_bytes(data)
    assert digest(resources / 'Sample.pdf') == PDF
    shutil.copytree(resources, EVIDENCE / 'inputs')

    sources = ['examples/apple/HostSDK.swift', 'examples/apple/HostModel.swift', 'examples/apple/HostCatalog.swift',
               'examples/apple/SelectableText.swift', 'tests/reader_next_c07/mac/C07Interop.swift']
    program = EVIDENCE / 'actual-c07-host'
    run([sys.executable, 'tools/apple_swift.py', '--sdk', sdk, '--product-prefix', raw, '--selector-bytes-candidate', '--',
         '-swift-version', '5', '-parse-as-library', '-O', '-D', 'EXR_APPLE_HOST_REVIEW', '-I', sdk / 'include',
         '-L', sdk / 'lib', '-lexreader', '-Xlinker', '-rpath', '-Xlinker', sdk / 'lib', *sources, '-o', program], 'c07-compile')
    provider = json.loads(Path(str(program) + '.product.json').read_text())
    assert provider['selector_bytes_candidate'] and not provider['static_sdk_linked']

    bundle = EVIDENCE / 'sender-bundle'
    profiles = EVIDENCE / 'profiles'
    profiles.mkdir()

    def phase(mode, profile, name=None, env=None):
        name = name or mode
        report = EVIDENCE / (name + '.json')
        pid = run([program, mode, resources, profile, bundle, report], name, env=env)
        value = json.loads(report.read_text())
        assert value['accepted'] and value['mode'] == mode and value['pid'] == pid
        assert (value['source_sha'], str(value['run_id']), str(value['attempt'])) == tuple(os.environ[k] for k in ('GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT'))
        phases.append({'name': name, 'mode': mode, 'pid': pid, 'exit': 0, 'report': report.name})
        return value

    sender = profiles / 'fresh-raw-sender'
    phase('send', sender)
    manifest = json.loads((bundle / 'manifest.json').read_text())
    assert len(manifest['reading_records']) == 11 and len(manifest['originals']) == 4
    assert {row['role']: row['sha256'] for row in manifest['originals']} == {row['role']: row['sha256'] for row in common}
    phase('operations', profiles / 'source-version-and-NULL-operations')

    fixture = Fixture(ROOT / 'build/c07-mac-private')
    try:
        env = dict(os.environ, EXR_RAW_DAV_ROOT=fixture.url, EXR_RAW_ACCOUNT=str(uuid.uuid4()), EXR_RAW_AUTH=fixture.auth)
        push = phase('session-push', sender, env=env)
        remote = dict(fixture.entries)
        entries = []
        sent = EVIDENCE / 'https-sent'
        sent.mkdir()
        for index, (path, data) in enumerate(sorted(remote.items())):
            name = '%04d.bin' % index
            (sent / name).write_bytes(data)
            entries.append({'path': path.split('/dav/', 1)[1] if '/dav/' in path else path, 'file': name, 'bytes': len(data),
                            'sha256': hashlib.sha256(data).hexdigest()})
        for row in manifest['revisions']:
            wire = (bundle / row['file']).read_bytes()
            matches = [data for path, data in remote.items() if path.endswith('/' + row['id'] + '-' + row['sha256'] + '.json')]
            assert matches == [wire]
        for row in manifest['originals']:
            assert (bundle / row['file']).read_bytes() in remote.values()
        assert fixture.requests and all(row['authenticated'] for row in fixture.requests)
        assert {'PUT', 'GET', 'PROPFIND', 'MKCOL'} <= {row['method'] for row in fixture.requests}
        session = push['actual_native_session']
        assert session['actual_host_account_session'] and session['completed_shards'] == 256 and session['completed_sweeps'] == 1
        (sent / 'index.json').write_text(json.dumps({
            'actual_host_account_session': True, 'tls_trust_checked': True, 'completed_shards': session['completed_shards'],
            'entries': [{**row, 'path': row['path']} for row in entries],
            'requests': [{'method': row['method'], 'path': row['path'].split('/dav/', 1)[-1], 'authenticated': row['authenticated']} for row in fixture.requests]},
            indent=2) + '\n')
        for file in EVIDENCE.rglob('*'):
            if file.is_file():
                assert fixture.auth.encode() not in file.read_bytes(), 'Authorization leaked into evidence'
    finally:
        fixture.close()
    assert len({row['pid'] for row in phases}) == len(phases)

    sdk_dylibs = sorted(path for path in (sdk / 'lib').glob('libexreader*.dylib') if path.is_file() and not path.is_symlink())
    result = {'accepted': True, 'scope': 'C07 actual macOS raw sender, NULL operations and HTTPS push on the common source only',
              'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'], 'attempt': os.environ['GITHUB_RUN_ATTEMPT'],
              'runner': {'os': 'macos', 'arch': os.uname().machine, 'release': os.uname().release},
              'program_sha256': digest(program), 'sdk_dylibs': {path.name: digest(path) for path in sdk_dylibs}, 'provider': provider,
              'real_reading_records': 11, 'originals': 4, 'common_originals': common, 'phases': phases, 'commands': commands,
              'harness': {'swift': digest(ROOT / 'tests/reader_next_c07/mac/C07Interop.swift'),
                          'original_swift': digest(ROOT / 'tests/apple_host/raw3/RawRecordInterop.swift')}}
    shutil.copyfile(ROOT / 'build/c07/mac-send/guard.json', EVIDENCE / 'guard.json')
    result['files'] = {file.relative_to(EVIDENCE).as_posix(): {'bytes': file.stat().st_size, 'sha256': digest(file)}
                       for file in EVIDENCE.rglob('*') if file.is_file()}
    (EVIDENCE / 'result.json').write_text(json.dumps(result, indent=2) + '\n')

    # Exact executable + SDK + resources for the independent receiver job (same absolute prefix).
    toolchain = OUT / 'toolchain.tar'
    with tarfile.open(toolchain, 'w') as archive:
        archive.add(program, arcname=program.relative_to(ROOT).as_posix())
        archive.add(sdk, arcname=sdk.relative_to(ROOT).as_posix())
        archive.add(resources, arcname=resources.relative_to(ROOT).as_posix())
    print(json.dumps({k: v for k, v in result.items() if k not in ('commands', 'files', 'provider', 'common_originals')}), flush=True)


if __name__ == '__main__':
    main()
