"""F06 build-only adapters; execution, fixtures and packaging are Actions-only.

No existing test is modified or substituted. Full behavioral gates are separate
work packages. This job establishes the actual distribution bytes and entry.
"""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'build/f06'

def run(*args):
    subprocess.run([str(a) for a in args], cwd=ROOT, check=True)

def module(path, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj

def windows():
    C = module('tests/reader_wave3_c09/build.py', 'f06_c09')
    H = C.H
    H.OUT = OUT / 'windows-build'
    (H.OUT / 'logs').mkdir(parents=True)
    sdk, product, stage = (H.OUT / n for n in ('sdk-stage', 'product-stage', 'raw-stage'))
    prefix = ';'.join(map(str, (stage, product, sdk)))
    H.run(['cmake', '--preset', 'reading-library', '-B', H.OUT / 'sdk-build', '-DCMAKE_INSTALL_PREFIX=' + str(sdk)], 'sdk-configure')
    H.run(['cmake', '--build', H.OUT / 'sdk-build', '--parallel', '4'], 'sdk-build')
    H.run(['cmake', '--install', H.OUT / 'sdk-build'], 'sdk-install')
    H.configure(ROOT / 'apps/reader/store/native', H.OUT / 'product-build', ['-DCMAKE_INSTALL_PREFIX=' + str(product)], 'product')
    H.run(['cmake', '--install', H.OUT / 'product-build'], 'product-install')
    for source in tuple(H.MODULES) + C.NEW_MODULES:
        label = Path(source).name
        options = ['-DCMAKE_INSTALL_PREFIX=' + str(stage), '-DCMAKE_PREFIX_PATH=' + prefix,
                   '-DEXR_SDK=' + str(sdk), '-DEXR_SDK_VERSION=3.41.0', '-DREADER_PRODUCT_PREFIX=' + str(product)] + C.EXTRA_FLAGS.get(label, [])
        if label in set(H.RAW_MODULES) | C.RAW_NEW:
            options += ['-DEXR_READER_SELECTOR_BYTES_CANDIDATE=ON']
        if label == 'cloud-import': options += ['-DREADER_CLOUD_BUILD_CONTENT_BOUND=ON']
        binary = H.OUT / ('raw-' + label)
        H.configure(ROOT / source, binary, options, 'raw-' + label)
        H.run(['cmake', '--install', binary], 'install-' + label)
    host = H.OUT / 'host'
    H.run(['cmake', '-S', ROOT / 'apps/reader/desktop', '-B', host, '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release',
           '-DCMAKE_PREFIX_PATH=' + prefix, '-DEXR_SDK=' + str(sdk), '-DEXR_SDK_VERSION=3.41.0',
           '-DREADER_METADATA_PREFIX=' + str(stage), '-DREADER_ACCOUNT_PREFIX=' + str(stage),
           '-DEXR_READER_WINDOWS_WAVE3=ON', '-DEXR_READER_WINDOWS_CLOUD_CONTENT_BOUND=ON',
           '-DEXR_READER_WINDOWS_TXT_PROGRESS=ON'], 'host-configure')
    H.run(['cmake', '--build', host, '--target', 'EXReaderWave3', '--parallel', '4'], 'host-build')
    payload = OUT / 'windows-payload'
    run(sys.executable, 'tools/build_windows_host.py', '--sdk', sdk, '--binary', host / 'EXReaderWave3.exe', '--output', payload, '--static-reading')
    original = json.loads((payload / 'report.json').read_text())
    assert original['passed'] is True and original['checks'] >= 26, original
    return payload

def linux():
    G = module('tests/reader_gtk_raw_wave3/run.py', 'f06_gtk')
    G.build_sdk()
    G.install_family('raw', G.PREFIX, True)
    G.installed('raw', G.PREFIX)
    return G.build_compact_host()

def apple(target):
    native = 'macos' if target == 'macos' else 'iphonesimulator'
    folder = OUT / (native + '-build')
    sdk, product = folder / 'sdk', folder / 'product'
    options = ['-DCMAKE_BUILD_TYPE=Release', '-DEXR_BUILD_TESTS=OFF', '-DEXR_BUILD_TOOLS=OFF', '-DEXR_ENABLE_AAC=OFF']
    if native != 'macos':
        options += ['-DCMAKE_SYSTEM_NAME=iOS', '-DCMAKE_OSX_SYSROOT=iphonesimulator', '-DCMAKE_OSX_ARCHITECTURES=arm64',
                    '-DCMAKE_OSX_DEPLOYMENT_TARGET=15.0', '-DCMAKE_XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED=NO']
    run('cmake', '-S', '.', '-B', folder / 'sdk-build', *options)
    run('cmake', '--build', folder / 'sdk-build', '--parallel', '4')
    run('cmake', '--install', folder / 'sdk-build', '--prefix', sdk)
    run(sys.executable, 'tools/build_apple_product.py', '--sdk', sdk, '--target', native, '--build', folder / 'product-build',
        '--product-prefix', product, '--sdk-version', '3.41.0', '--selector-bytes-candidate', '--wave3')
    payload = OUT / (target + '-payload')
    run(sys.executable, 'tools/build_apple_host.py', '--sdk', sdk, '--platform', 'macos' if native == 'macos' else 'simulator',
        '--product-prefix', product, '--output', payload, '--sdk-version', '3.41.0', '--selector-bytes-candidate', '--wave3', '--page-theme')
    return payload

def android():
    # Reuse exact reviewed composition commands, not a simplified fake host.
    # Selected *build* steps are unchanged; old tests are neither edited nor claimed run.
    import yaml
    recipe = ROOT / '.github/workflows/android-composition-candidate.yml'
    steps = yaml.safe_load(recipe.read_text())['jobs']['android']['steps']
    names = [
        'Prepare existing C11 candidate test sources',
        'Build and install the frozen 3.41 SDK for x86_64',
        'Install the raw0.2 product and reviewed wave3 packages into one prefix',
        'Author the deterministic fixtures and the bundled font',
        'Build the real wave3 host with search directory reading settings and sync',
    ]
    env_file = Path(os.environ['GITHUB_ENV'])
    for index, name in enumerate(names):
        matches = [s for s in steps if s.get('name') == name]
        assert len(matches) == 1, name
        script = OUT / ('android-build-step-' + str(index) + '.sh')
        script.write_text(matches[0]['run'])
        run('bash', '-e', '-o', 'pipefail', script)
        # GitHub normally carries these variables across workflow steps.
        for line in env_file.read_text().splitlines():
            key, sep, value = line.partition('=')
            if sep: os.environ[key] = value
    payload = OUT / 'android-payload'
    (payload / 'artifacts').mkdir(parents=True)
    shutil.copyfile(ROOT / 'build/wave3/artifacts/app-debug.apk', payload / 'artifacts/app-debug.apk')
    for name in ('LICENSE', 'THIRD_PARTY_NOTICES.md'):
        shutil.copyfile(ROOT / name, payload / name)
    import hashlib
    build = dict(source_sha=os.environ['GITHUB_SHA'], sdk_version='3.41.0',
                 platform='Android API34 x86_64 emulator', signing='debug; not store release',
                 recipe=recipe.relative_to(ROOT).as_posix(), recipe_sha256=hashlib.sha256(recipe.read_bytes()).hexdigest(),
                 exact_steps=names, files={'artifacts/app-debug.apk': hashlib.sha256((payload / 'artifacts/app-debug.apk').read_bytes()).hexdigest()})
    (payload / 'build.json').write_text(json.dumps(build, indent=2) + '\n')
    return payload

if __name__ == '__main__':
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'GitHub Actions only'
    OUT.mkdir(parents=True, exist_ok=True)
    target = sys.argv[1]
    payload = {'windows': windows, 'linux': linux, 'android': android}.get(target, lambda: apple(target))()
    run(sys.executable, 'tests/reader_f06_packages/identity.py', 'package', target, payload)
