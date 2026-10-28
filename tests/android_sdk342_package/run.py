"""Actions-only Android 3.42 F06 adapter; original build steps stay intact."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'build/f06'
BASE = '6e93411a07cacc3bddabd8d93aa4b763a565b5d2'
VERSION = '3.42.0'

def command(*args):
    return subprocess.check_output(list(map(str, args)), cwd=ROOT, text=True).strip()

def guard():
    assert command('git', 'rev-parse', 'HEAD') == os.environ['GITHUB_SHA']
    command('git', 'merge-base', '--is-ancestor', BASE, 'HEAD')
    changed = command('git', 'diff', '--name-only', BASE, 'HEAD').splitlines()
    allowed = {'tests/reader_f06_packages/identity.py', 'tests/gtk_sdk342_package/run.py',
               'tests/android_sdk342_package/run.py', 'tests/apple_sdk342_package/authenticate.py',
               'tests/sdk342_aggregate/authenticate.py', 'tests/sdk342_aggregate/apple_f06.py', '.github/workflows/sdk342-aggregate.yml',
               '.github/workflows/gtk-sdk342-package.yml', '.github/workflows/f06-windows-sdk342.yml',
               '.github/workflows/android-sdk342-package.yml', '.github/workflows/android-sdk342-record-probe.yml',
               '.github/workflows/apple-sdk342-package.yml'}
    assert all(p in allowed for p in changed), changed
    command('git', 'diff', '--exit-code', '8357eafa28423a7ab93ba08b823af80f01ad1505', 'HEAD', '--',
            'src', 'include', 'cmake', 'CMakeLists.txt', 'bindings')
    frozen = {}
    for path in ('src', 'include', 'CMakeLists.txt', 'tests/reader_f06_packages/build.py',
                 'tests/reader_f06_packages/README.md',
                 '.github/workflows/android-composition-candidate.yml', 'examples/android/app/src/main/java'):
        old = command('git', 'rev-parse', BASE + ':' + path)
        current = command('git', 'rev-parse', 'HEAD:' + path)
        assert old == current, path
        frozen[path] = current
    f06_path = 'tests/reader_f06_packages/identity.py'
    old_identity = subprocess.check_output(['git', 'show', BASE + ':' + f06_path], cwd=ROOT, text=True)
    old_base = "BASE = '503c36e8073c12cd8837184b142b7704da51c961'"
    new_base = "BASE = '6e93411a07cacc3bddabd8d93aa4b763a565b5d2'"
    assert old_identity.count(old_base) == 1
    assert (ROOT / f06_path).read_text() == old_identity.replace(old_base, new_base, 1)
    frozen[f06_path] = command('git', 'rev-parse', 'HEAD:' + f06_path)
    cmake = (ROOT / 'examples/android/app/src/main/cpp/CMakeLists.txt').read_text()
    assert 'set(EXR_HOST_SDK_VERSION "3.41.0" CACHE STRING' in cmake
    assert 'find_package(EXReader ${EXR_HOST_SDK_VERSION} EXACT CONFIG REQUIRED)' in cmake
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'android-source.json').write_text(json.dumps(dict(source_sha=os.environ['GITHUB_SHA'],
        run_id=os.environ['GITHUB_RUN_ID'], attempt=os.environ['GITHUB_RUN_ATTEMPT'], base_sha=BASE,
        sdk_version=VERSION, changed=changed, frozen=frozen, passed=True), indent=2) + '\n')

def build():
    import yaml
    recipe = ROOT / '.github/workflows/android-composition-candidate.yml'
    steps = yaml.safe_load(recipe.read_text())['jobs']['android']['steps']
    names = ['Prepare existing C11 candidate test sources', 'Build and install the frozen 3.41 SDK for x86_64',
             'Install the raw0.2 product and reviewed wave3 packages into one prefix',
             'Author the deterministic fixtures and the bundled font',
             'Build the real wave3 host with search directory reading settings and sync']
    for index, name in enumerate(names):
        matches = [s for s in steps if s.get('name') == name]
        assert len(matches) == 1, name
        body = matches[0]['run']
        if index == 2:
            assert body.count('-DEXR_SDK_VERSION=3.41.0') == 1
            body = body.replace('-DEXR_SDK_VERSION=3.41.0', '-DEXR_SDK_VERSION=' + VERSION)
        if index == 4:
            assert body.count('-PexrSdk=') == 3 and '-PexrSdkVersion=' not in body
            body = body.replace('-PexrSdk=', '-PexrSdkVersion=' + VERSION + ' -PexrSdk=')
        script = OUT / ('android-sdk342-build-step-' + str(index) + '.sh')
        script.write_text(body)
        subprocess.run(['bash', '-e', '-o', 'pipefail', str(script)], cwd=ROOT, check=True)
        for line in Path(os.environ['GITHUB_ENV']).read_text().splitlines():
            key, sep, value = line.partition('=')
            if sep: os.environ[key] = value
    sdk_header = (ROOT / 'build/wave3/sdk-stage/include/exr/base.h').read_text()
    assert '#define EXR_VERSION "' + VERSION + '"' in sdk_header
    caches = {}
    for folder in (ROOT / 'build/wave3', ROOT / 'examples/android/app/.cxx'):
        for cache in folder.rglob('CMakeCache.txt'):
            lines = [line for line in cache.read_text(errors='replace').splitlines()
                     if line.startswith(('EXR_SDK_VERSION:', 'EXR_HOST_SDK_VERSION:'))]
            assert all(line.partition('=')[2] == VERSION for line in lines), (str(cache), lines)
            if lines: caches[str(cache.relative_to(ROOT))] = lines
    assert any(any(line.startswith('EXR_HOST_SDK_VERSION:') for line in lines)
               for lines in caches.values()), 'no Android host SDK selection recorded'
    payload = OUT / 'android-payload'
    (payload / 'artifacts').mkdir(parents=True)
    shutil.copyfile(ROOT / 'build/wave3/artifacts/app-debug.apk', payload / 'artifacts/app-debug.apk')
    for name in ('LICENSE', 'THIRD_PARTY_NOTICES.md'): shutil.copyfile(ROOT / name, payload / name)
    apk = payload / 'artifacts/app-debug.apk'
    producer = dict(source_sha=os.environ['GITHUB_SHA'], sdk_version=VERSION,
        platform='Android API34 x86_64 emulator', signing='debug; not store release',
        recipe=recipe.relative_to(ROOT).as_posix(), recipe_sha256=hashlib.sha256(recipe.read_bytes()).hexdigest(),
        exact_steps=names, sdk_cache_entries=caches,
        adaptations=['module exact SDK selection', 'three Gradle exact SDK selections'],
        files={'artifacts/app-debug.apk': hashlib.sha256(apk.read_bytes()).hexdigest()})
    (payload / 'build.json').write_text(json.dumps(producer, indent=2) + '\n')
    spec = importlib.util.spec_from_file_location('f06', ROOT / 'tests/reader_f06_packages/identity.py')
    f06 = importlib.util.module_from_spec(spec); spec.loader.exec_module(f06)
    original = f06.run
    def explicit_version(*args):
        if any(str(a).endswith('assemble.py') for a in args): args = (*args, '--sdk-version', VERSION)
        return original(*args)
    f06.run = explicit_version
    f06.package('android', payload)

if __name__ == '__main__':
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    {'guard': guard, 'build': build}[sys.argv[1]]()
