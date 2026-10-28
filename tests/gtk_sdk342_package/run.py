"""Actions-only explicit SDK 3.42 adapter; original GTK checks stay unchanged."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'build/gtk-sdk342'
BASE = 'd1e6bd072a904150bb292994d0cf7d95ccde5c19'
SDK_SOURCE = '7271829a829bfa6aaa47b73077c493f71af27ad3'
VERSION = '3.42.0'
ALLOWED = {'apps/reader/desktop/CMakeLists.txt', 'apps/reader/desktop/gtk_feature_integration.cmake',
           'tools/build_linux_host.py', '.github/workflows/gtk-sdk342-package.yml'}

def command(*args):
    return subprocess.check_output(list(map(str, args)), cwd=ROOT, text=True)

def save(name, data):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(data, indent=2) + '\n')

def identity():
    return dict(source_sha=os.environ['GITHUB_SHA'], run_id=os.environ['GITHUB_RUN_ID'], attempt=os.environ['GITHUB_RUN_ATTEMPT'])

def load(path, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    obj = importlib.util.module_from_spec(spec); spec.loader.exec_module(obj)
    return obj

def guard():
    assert command('git', 'rev-parse', 'HEAD').strip() == os.environ['GITHUB_SHA']
    command('git', 'merge-base', '--is-ancestor', BASE, 'HEAD')
    changed = command('git', 'diff', '--name-only', BASE, 'HEAD').splitlines()
    assert all(p in ALLOWED or p.startswith('tests/gtk_sdk342_package/') for p in changed), changed
    frozen = {}
    for path in ('src', 'include', 'CMakeLists.txt', 'tests/reader_gtk_raw_wave3', 'tests/reader_gtk_navigation',
                 'tests/reader_gtk_batch_import', 'tests/reader_f06_packages'):
        old = command('git', 'rev-parse', BASE + ':' + path).strip()
        current = command('git', 'rev-parse', 'HEAD:' + path).strip()
        assert old == current, path
        frozen[path] = current
    for path in ('apps/reader/desktop/CMakeLists.txt', 'examples/linux/CMakeLists.txt'):
        text = (ROOT / path).read_text()
        assert 'set(EXR_SDK_VERSION "3.40.0" CACHE STRING' in text
        assert 'find_package(EXReader ${EXR_SDK_VERSION} EXACT CONFIG REQUIRED' in text
    save('source.json', dict(identity(), base_sha=BASE, sdk_origin_sha=SDK_SOURCE, frozen=frozen, changed=changed, passed=True))

def build():
    raw = load('tests/reader_gtk_raw_wave3/run.py', 'gtk342_raw')
    original = raw.run
    # Adapt only the pinned producer's SDK-selection arguments, never assertions.
    def explicit_sdk(label, args, **kwargs):
        args = list(map(str, args))
        args = ['-DEXR_SDK_VERSION=' + VERSION if a == '-DEXR_SDK_VERSION=3.41.0' else a for a in args]
        for i in range(1, len(args)):
            if args[i-1] == '--sdk-version' and args[i] == '3.41.0': args[i] = VERSION
        return original(label, args, **kwargs)
    raw.run = explicit_sdk
    sys.argv = [__file__]
    assert raw.main() == 0, 'original raw/legacy checks failed'
    for label in ('batch-import', 'preferences'):
        raw.cmake('raw-' + label, ROOT / ('apps/reader/' + label), raw.OUT / ('raw-' + label), raw.PREFIX, install=True)
    options = raw.host_options(raw.PREFIX) + ['-DEXR_READER_GTK_RAW3=ON', '-DREADER_GTK_RAW3_PREFIX=' + str(raw.PREFIX),
        '-DEXR_READER_GTK_BATCH_IMPORT=ON', '-DREADER_BATCH_IMPORT_PREFIX=' + str(raw.PREFIX),
        '-DEXR_READER_GTK_PREFERENCES=ON', '-DREADER_PREFERENCES_PREFIX=' + str(raw.PREFIX)]
    raw.cmake('retained-host', ROOT / 'apps/reader/desktop', raw.OUT / 'retained-host', raw.PREFIX, extra=options,
        targets=('exreader-linux', 'reader-gtk-navigation-backend', 'reader-gtk-batch-import-backend', 'reader-gtk-batch-owner-faults'))
    raw.run('retained-package', [sys.executable, 'tools/build_linux_host.py', '--sdk', raw.SDK, '--sdk-version', VERSION,
        '--binary', raw.OUT / 'retained-host/gtk-host/exreader-linux', '--output', raw.OUT / 'retained-package'])
    raw.run('retained-version', [raw.OUT / 'retained-host/gtk-host/exreader-linux', '--version'])
    assert raw.sha(raw.OUT / 'retained-host/gtk-host/exreader-linux') == raw.sha(raw.OUT / 'retained-package/EXReader-Linux/bin/exreader-linux')
    # Same original F06 packaging path with the selected version explicitly forwarded.
    f06 = load('tests/reader_f06_packages/identity.py', 'gtk342_f06')
    old_run = f06.run
    def packaging_run(*args):
        args = list(args)
        if any(str(a).endswith(('assemble.py', 'desktop.py')) for a in args):
            args += ['--sdk-version', VERSION]
        return old_run(*args)
    f06.run = packaging_run
    f06.package('linux', raw.OUT / 'retained-package')
    caches = {}
    for path in (ROOT / 'build').rglob('CMakeCache.txt'):
        lines = path.read_text().splitlines()
        selected = [x for x in lines if x.startswith(('EXR_SDK_VERSION:', 'EXR_SDK:', 'CMAKE_HOME_DIRECTORY:', 'CMAKE_PREFIX_PATH:', 'EXReader_DIR:'))]
        if any(x.startswith('EXR_SDK_VERSION:') for x in selected):
            assert all(x.partition('=')[2] == VERSION for x in selected if x.startswith('EXR_SDK_VERSION:')), (str(path), selected)
        caches[str(path.relative_to(ROOT))] = selected
    installed = {}
    for prefix in (raw.SDK, raw.PREFIX, raw.LEGACY):
        for path in prefix.rglob('*'):
            if path.is_file(): installed[str(path.relative_to(ROOT))] = raw.sha(path)
    save('build.json', dict(identity(), sdk_version=VERSION, caches=caches, installed_sha256=installed,
        program_sha256=raw.sha(raw.OUT / 'retained-host/gtk-host/exreader-linux'), passed=True))

if __name__ == '__main__':
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    {'guard': guard, 'build': build}[sys.argv[1]]()
