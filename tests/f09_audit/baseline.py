"""F09 baseline: the existing accessibility audits against the shared-source hosts.

The hosts are built exactly as F06 builds its six packages (tests/reader_f06_packages),
so the audited binaries are the product hosts of the shared candidate, not older
audit builds. The audit packages (tests/reader_a11y_*) run unchanged; this script
only wires their inputs and keeps their verdicts. Actions only.
"""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'build/f09'


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


def run(args, log, check=False, env=None):
    """Runs one step, keeps its full output, and returns its exit code."""
    (OUT / 'logs').mkdir(parents=True, exist_ok=True)
    with open(OUT / 'logs' / (log + '.log'), 'w', encoding='utf-8', errors='replace') as out:
        code = subprocess.run([str(a) for a in args], cwd=ROOT, stdout=out, stderr=subprocess.STDOUT, env=env).returncode
    print(log, 'exit', code, flush=True)
    if check and code:
        raise SystemExit(log + ' failed with ' + str(code))
    return code


def record(platform, payload, audit_code, report):
    """The baseline verdict as the audit itself reported it, with the binary identity."""
    data = {'platform': platform, 'source_sha': os.environ.get('GITHUB_SHA'), 'run_id': os.environ.get('GITHUB_RUN_ID'),
            'attempt': os.environ.get('GITHUB_RUN_ATTEMPT'), 'payload': str(payload.relative_to(ROOT)),
            'audit_exit': audit_code, 'report_present': report.is_file()}
    if report.is_file():
        result = json.loads(report.read_text(encoding='utf-8'))
        for key in ('audit_completed', 'accessibility_accepted', 'screen_reader_verified', 'orca_screen_reader_accepted'):
            if key in result:
                data[key] = result[key]
        checks = result.get('checks') or result.get('results') or []
        if isinstance(checks, list):
            data['checks'] = len(checks)
            data['failed'] = sorted({str(c.get('id') or c.get('name')) for c in checks
                                     if isinstance(c, dict) and str(c.get('status', c.get('result', ''))).lower() in ('fail', 'failed', 'error')})
    (OUT / (platform + '-baseline.json')).write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps(data, ensure_ascii=False), flush=True)


def windows():
    F = module('tests/reader_f06_packages/build.py', 'f09_f06')
    F.OUT = ROOT / 'build/f06'
    F.OUT.mkdir(parents=True, exist_ok=True)
    payload = F.windows() / 'EXReader'
    fixtures = OUT / 'windows-fixtures'
    run([sys.executable, 'tests/windows_host/make_fixtures.py', '--output', fixtures], 'windows-fixtures', check=True)
    evidence = OUT / 'windows-audit'
    code = run([sys.executable, 'tests/reader_a11y_windows/run_audit.py', '--payload', payload, '--fixtures', fixtures,
                '--output', evidence, '--verbose'], 'windows-audit')
    report = evidence / 'report.json'
    if report.is_file():
        run([sys.executable, 'tests/reader_a11y_windows/verify_report.py', '--report', report,
             '--output', evidence / 'verification.json'], 'windows-verify')
    record('windows', payload, code, report)


def linux():
    # The GTK product host as the current product work on this base builds it
    # (the F08 performance lane): F06's compact raw0.2 recipe still pins SDK 3.41.
    hash_prefix = os.environ['EXREADER_ORIGINAL_HASH_PREFIX']
    run(['cmake', '--preset', 'reading-library'], 'gtk-sdk-configure', check=True)
    run(['cmake', '--build', '--preset', 'reading-library'], 'gtk-sdk-build', check=True)
    run(['cmake', '--install', 'build/reading-library'], 'gtk-sdk-install', check=True)
    run(['cmake', '-S', 'apps/reader/desktop', '-B', 'build/f09-gtk', '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release',
         '-DEXR_SDK_VERSION=3.42.0', '-DEXR_SDK=' + str(ROOT / 'build/reading-library/stage'), '-DEXR_READER_BUILD_GTK=ON',
         '-DREADER_ORIGINAL_HASH_PREFIX:PATH=' + hash_prefix, '-DEXR_READER_FIXTURES=' + str(ROOT / 'tests/fixtures')],
        'gtk-host-configure', check=True)
    run(['cmake', '--build', 'build/f09-gtk', '--parallel', '4'], 'gtk-host-build', check=True)
    run([sys.executable, 'tools/build_linux_host.py', '--sdk', 'build/reading-library/stage', '--sdk-version', '3.42.0',
         '--binary', 'build/f09-gtk/gtk-host/exreader-linux', '--output', 'build/f09-gtk-package'], 'gtk-package', check=True)
    payload = ROOT / 'build/f09-gtk-package/EXReader-Linux'
    evidence = OUT / 'gtk-audit'
    if evidence.exists():
        shutil.rmtree(evidence)
    code = run([sys.executable, 'tests/reader_a11y_gtk/audit_gtk_a11y.py', '--payload', payload, '--output', evidence], 'gtk-audit')
    report = evidence / 'result.json'
    if report.is_file():
        run([sys.executable, 'tests/reader_a11y_gtk/check_a11y_report.py', '--report', report], 'gtk-gate')
    record('gtk', payload, code, report)


def android_prepare():
    """The shared-source APK where the retained audit expects the owner build,
    with the identity record its checker compares the installed APK against."""
    import hashlib
    # The current on-base recipe (product closure lanes after 343bb94e): an
    # Android-ABI OPDSHash prefix, then the five reviewed composition steps with
    # the SDK version raised to 3.42.0.
    import yaml
    env_file = Path(os.environ['GITHUB_ENV'])

    def load_env():
        for line in env_file.read_text().splitlines():
            key, sep, value = line.partition('=')
            if sep:
                os.environ[key] = value

    ndk = Path(os.environ['ANDROID_HOME']) / 'ndk' / os.environ['C11_NDK']
    stage, build = OUT / 'android-hash-stage', OUT / 'android-hash-build'
    run(['cmake', '-S', 'extras/opds', '-B', build, '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release',
         '-DCMAKE_POSITION_INDEPENDENT_CODE=ON', '-DCMAKE_TOOLCHAIN_FILE=' + str(ndk / 'build/cmake/android.toolchain.cmake'),
         '-DANDROID_ABI=x86_64', '-DANDROID_PLATFORM=android-26', '-DANDROID_STL=c++_static',
         '-DEXREADER_OPDS_HASH_ONLY=ON', '-DCMAKE_INSTALL_PREFIX=' + stage.as_posix()], 'android-hash-configure', check=True)
    run(['cmake', '--build', build, '--parallel', '4'], 'android-hash-build', check=True)
    run(['cmake', '--install', build], 'android-hash-install', check=True)
    with env_file.open('a') as f:
        f.write('EXREADER_ORIGINAL_HASH_PREFIX=' + stage.resolve().as_posix() + '\n')
    load_env()
    recipe = ROOT / '.github/workflows/android-composition-candidate.yml'
    steps = yaml.safe_load(recipe.read_text())['jobs']['android']['steps']
    names = ['Prepare existing C11 candidate test sources', 'Build and install the frozen 3.41 SDK for x86_64',
             'Install the raw0.2 product and reviewed wave3 packages into one prefix',
             'Author the deterministic fixtures and the bundled font',
             'Build the real wave3 host with search directory reading settings and sync']
    for index, name in enumerate(names):
        found = [x for x in steps if x.get('name') == name]
        assert len(found) == 1, name
        body = found[0]['run']
        if index == 2:
            assert body.count('-DEXR_SDK_VERSION=3.41.0') == 1
            body = body.replace('-DEXR_SDK_VERSION=3.41.0', '-DEXR_SDK_VERSION=3.42.0')
        if index == 4:
            assert body.count('-PexrSdk=') == 3 and '-PexrSdkVersion=' not in body
            body = body.replace('-PexrSdk=', '-PexrSdkVersion=3.42.0 -PexrSdk=')
        script = OUT / ('android-recipe-step-%d.sh' % index)
        script.write_text(body)
        run(['bash', '-e', '-o', 'pipefail', script], 'android-recipe-step-%d' % index, check=True)
        load_env()
    apk = ROOT / 'build/wave3/artifacts/app-debug.apk'
    host = ROOT / 'build/android-host'
    (host / 'artifacts').mkdir(parents=True, exist_ok=True)
    shutil.copyfile(apk, host / 'artifacts/app-debug.apk')
    raw = (host / 'artifacts/app-debug.apk').read_bytes()
    sys.path.insert(0, str(ROOT / 'tools'))
    B = module('tools/build_android_host.py', 'f09_android_host')
    B.write_fixtures(host / 'fixtures')
    record = {'source_sha': os.environ.get('GITHUB_SHA'), 'recipe': 'tests/reader_f06_packages/build.py android',
              'artifacts': {'app-debug.apk': {'path': str(host / 'artifacts/app-debug.apk'), 'size': len(raw),
                                              'sha256': hashlib.sha256(raw).hexdigest()}}}
    (host / 'build.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(record), flush=True)


if __name__ == '__main__':
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'GitHub Actions only'
    OUT.mkdir(parents=True, exist_ok=True)
    {'windows': windows, 'linux': linux, 'android-prepare': android_prepare}[sys.argv[1]]()
