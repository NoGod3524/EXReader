"""Actions only. Explicit raw install family for the read-only sync status view.

The frozen start, SDK tree, product schema, transport, revisions/sync/session
sources and the original status-view acceptance are reused unchanged. This
script installs both capability families, builds the original C/C++ consumer
against the legacy family and the explicit raw consumer against the raw family,
rejects every mixed install, and leaves the real TLS evidence to
check_raw_view.py.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'build/reader-next-s17'
BASE = 'e67d87cbeabb2457e0852f681ef0b27b2c0da4d8'
FROZEN_SDK = 'edddc463c06ed5731195cdb8f06b2df6dff7699e'
MODULES = ('revisions', 'sync', 'session', 'sync-status-view')
SUFFIX = '.exe' if os.name == 'nt' else ''
ENV = dict(os.environ)


def path(value):
    return Path(value).absolute().as_posix()


def run(args, name=None, timeout=2400):
    args = list(map(str, args))
    print('RUN', ' '.join(args), flush=True)
    process = subprocess.run(args, cwd=ROOT, env=ENV, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, encoding='utf-8', errors='replace', timeout=timeout)
    if name:
        (OUT / (name + '.log')).write_text(process.stdout, encoding='utf-8')
    print(process.stdout[-12000:], flush=True)
    if process.returncode:
        raise RuntimeError((args, process.returncode))
    return process.stdout


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()


def guard():
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only'
    assert git('rev-parse', 'HEAD') == os.environ['GITHUB_SHA']
    subprocess.run(['git', 'merge-base', '--is-ancestor', BASE, 'HEAD'], cwd=ROOT, check=True)
    subprocess.run(['git', 'diff', '--exit-code', FROZEN_SDK, 'HEAD', '--',
                    'src', 'include', 'cmake', 'CMakeLists.txt'], cwd=ROOT, check=True)
    subprocess.run(['git', 'diff', '--exit-code', BASE, 'HEAD', '--',
                    'apps/reader/store', 'apps/reader/revisions', 'apps/reader/sync', 'apps/reader/session',
                    'apps/reader/desktop', 'extras', 'examples', 'tests/reader_sync_status_view',
                    'tests/reader_revisions', 'tests/reader_sync', 'tests/reader_session'], cwd=ROOT, check=True)
    changed = git('diff', '--name-only', BASE, 'HEAD').splitlines()
    allowed = ('apps/reader/sync-status-view/', 'tests/reader_next_s17/', 'docs/reader-next-s17/')
    extra = {'.github/workflows/reader-next-s17.yml', 'HANDOFF-RESULT-S17.md'}
    assert all(item.startswith(allowed) or item in extra for item in changed), changed


def build(source, name, prefix, extra=(), install=True):
    # The build directory must never be a package prefix: configure_package_config_file
    # writes <Name>Config.cmake into the build tree, and CMake would then prefer that
    # half-installed file over lib/cmake/<Name> in the stage.
    target = OUT / 'build' / name
    run(['cmake', '-S', source, '-B', target, '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release',
         '-DCMAKE_INSTALL_PREFIX=' + path(prefix), *extra], name + '-configure')
    run(['cmake', '--build', target, '--parallel', '4'], name + '-build')
    if install:
        run(['cmake', '--install', target], name + '-install')
    return target


def family(label, enabled, product, dav):
    """One complete capability family: revisions -> sync -> session -> view."""
    stages = {}
    prefix = [product, dav]
    for module in MODULES:
        stage = OUT / (label + '-' + module + '-stage')
        build(ROOT / 'apps/reader' / module, label + '-' + module, stage,
              ['-DEXR_READER_SELECTOR_BYTES_CANDIDATE=' + ('ON' if enabled else 'OFF'),
               '-DREADER_PRODUCT_PREFIX=' + path(product),
               '-DCMAKE_PREFIX_PATH=' + ';'.join(map(path, prefix))])
        stages[module] = stage
        prefix.append(stage)
    return stages


def consumer_prefix(stages, product, dav):
    return ';'.join(map(path, [stages['sync-status-view'], stages['session'], stages['sync'],
                               stages['revisions'], product, dav]))


def configure(name, body, prefixes, expected=None):
    source = OUT / (name + '-source')
    source.mkdir()
    (source / 'CMakeLists.txt').write_text(
        'cmake_minimum_required(VERSION 3.24)\nproject(NextS17Mix LANGUAGES C CXX)\n'
        'if(MSVC)\n  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")\nendif()\n' + body)
    (source / 'main.c').write_text('int main(void){return 0;}\n')
    process = subprocess.run(['cmake', '-S', str(source), '-B', str(OUT / name), '-G', 'Ninja',
                              '-DCMAKE_BUILD_TYPE=Release', '-DCMAKE_PREFIX_PATH=' + prefixes],
                             capture_output=True, text=True, encoding='utf-8', errors='replace')
    log = process.stdout + process.stderr
    (OUT / (name + '.log')).write_text(log, encoding='utf-8')
    if expected:
        assert process.returncode and expected in log, (name, process.returncode, log[-4000:])
    else:
        assert process.returncode == 0, (name, log[-4000:])
    return OUT / name, source


def package(package, version, location, components=''):
    return ('find_package(' + package + ' ' + version + ' EXACT CONFIG REQUIRED ' + components
            + ' PATHS "' + path(location / 'lib/cmake' / package) + '" NO_DEFAULT_PATH)\n')


def main():
    guard()
    OUT.mkdir(parents=True)
    product = OUT / 'product-stage'
    build(ROOT / 'apps/reader/store/native', 'product', product)
    run(['ctest', '--test-dir', str(OUT / 'build' / 'product'), '--output-on-failure', '--no-tests=error',
         '--timeout', '180'], 'product-ctest')
    dav = OUT / 'webdav-stage'
    build(ROOT / 'extras/webdav', 'webdav', dav)

    off = family('off', False, product, dav)
    raw = family('raw', True, product, dav)

    # The installed header text is the same file in both families; the compiled
    # capability is what differs, so the archives must disagree on the symbol.
    def archive_bytes(stage):
        return b''.join(entry.read_bytes() for entry in (stage / 'lib').glob('*')
                        if entry.suffix in {'.a', '.lib'})
    assert archive_bytes(off['sync-status-view']) != archive_bytes(raw['sync-status-view'])
    assert b'_raw_v3' not in archive_bytes(off['sync-status-view'])
    assert b'_raw_v3' in archive_bytes(raw['sync-status-view'])

    # Default family: the frozen original consumer and its full acceptance.
    scratch = OUT / 'consumer-stage'
    legacy_consumer = build(ROOT / 'tests/reader_revisions/consumer', 'off-revision-consumer', scratch,
                            ['-DCMAKE_PREFIX_PATH=' + ';'.join(map(path, [
                                off['revisions'], product, dav]))], False)
    frozen_consumer = build(ROOT / 'tests/reader_sync_status_view/consumer', 'off-status-view-consumer', scratch,
                            ['-DCMAKE_PREFIX_PATH=' + consumer_prefix(off, product, dav)], False)
    run([sys.executable, ROOT / 'tests/reader_sync_status_view/check_status_view.py',
         '--consumer', frozen_consumer / ('status-view-consumer' + SUFFIX),
         '--c-consumer', frozen_consumer / ('status-view-c-consumer' + SUFFIX),
         '--revision-consumer', legacy_consumer / ('revision-consumer' + SUFFIX),
         '--output', OUT / 'frozen-legacy-acceptance'], 'frozen-legacy-acceptance', 1800)

    # Explicit raw family: the same command boundary on the raw capability.
    raw_consumer = build(ROOT / 'tests/reader_next_s17/consumer', 'raw-consumers', scratch,
                         ['-DCMAKE_PREFIX_PATH=' + consumer_prefix(raw, product, dav)], False)
    run([sys.executable, ROOT / 'tests/reader_next_s17/check_raw_view.py',
         '--consumer', raw_consumer / ('raw-view-consumer' + SUFFIX),
         '--c-consumer', raw_consumer / ('raw-view-c-consumer' + SUFFIX),
         '--revision-consumer', raw_consumer / ('raw-revision' + SUFFIX),
         '--output', OUT / 'raw-acceptance'], 'raw-acceptance', 2400)

    # Mixed installs must fail in both directions and with imported targets.
    mixed = []
    for name, enabled, stages in [('raw-view-rejects-legacy-session', True, off),
                                  ('legacy-view-rejects-raw-session', False, raw)]:
        process = subprocess.run(['cmake', '-S', str(ROOT / 'apps/reader/sync-status-view'),
                                  '-B', str(OUT / name), '-G', 'Ninja',
                                  '-DEXR_READER_SELECTOR_BYTES_CANDIDATE=' + ('ON' if enabled else 'OFF'),
                                  '-DCMAKE_PREFIX_PATH=' + ';'.join(map(path, [
                                      stages['session'], stages['sync'], stages['revisions'], product, dav]))],
                                 capture_output=True, text=True, encoding='utf-8', errors='replace')
        log = process.stdout + process.stderr
        (OUT / (name + '.log')).write_text(log, encoding='utf-8')
        assert process.returncode and 'EXReaderSession' in log, (name, log[-4000:])
        mixed.append(name)
    # Installed packages must refuse the other family by exact version too.
    configure('installed-legacy-view-refuses-raw',
              package('EXReaderSyncView', '0.1.0', raw['sync-status-view']),
              consumer_prefix(raw, product, dav), 'EXReaderSyncView')
    mixed.append('installed-legacy-view-refuses-raw')
    configure('installed-raw-view-refuses-legacy',
              package('EXReaderSyncView', '0.2.0', raw['sync-status-view']),
              consumer_prefix(off, product, dav), 'EXReaderSession')
    mixed.append('installed-raw-view-refuses-legacy')
    # An already imported legacy target must not be re-labelled by a raw package:
    # the legacy chain is imported first, then every package _DIR is repointed at
    # the raw install so only the live target properties can refuse the mix.
    source = OUT / 'imported-legacy-target-refused-source'
    source.mkdir()
    (source / 'CMakeLists.txt').write_text(
        'cmake_minimum_required(VERSION 3.24)\nproject(NextS17ImportedMix LANGUAGES C CXX)\n'
        + 'set(EXReaderProductCatalog_DIR "' + path(product / 'lib/cmake/EXReaderProductCatalog') + '" CACHE PATH "" FORCE)\n'
        + 'set(EXReaderWebDAV_DIR "' + path(dav / 'lib/cmake/EXReaderWebDAV') + '" CACHE PATH "" FORCE)\n'
        + ''.join('set(' + name + '_DIR "' + path(off[module] / 'lib/cmake' / name) + '" CACHE PATH "" FORCE)\n'
                  for module, name in [('revisions', 'EXReaderRevisions'), ('sync', 'EXReaderSync'),
                                       ('session', 'EXReaderSession')])
        + 'find_package(EXReaderSession 0.1.0 EXACT CONFIG REQUIRED)\n'
        + ''.join('set(' + name + '_DIR "' + path(raw[module] / 'lib/cmake' / name) + '" CACHE PATH "" FORCE)\n'
                  for module, name in [('revisions', 'EXReaderRevisions'), ('sync', 'EXReaderSync'),
                                       ('session', 'EXReaderSession')])
        + package('EXReaderSyncView', '0.2.0', raw['sync-status-view']) + 'add_executable(version main.c)\n')
    (source / 'main.c').write_text('int main(void){return 0;}\n')
    process = subprocess.run(['cmake', '-S', str(source), '-B', str(OUT / 'imported-legacy-target-refused'),
                              '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release',
                              '-DCMAKE_PREFIX_PATH=' + consumer_prefix(raw, product, dav)],
                             capture_output=True, text=True, encoding='utf-8', errors='replace')
    log = process.stdout + process.stderr
    (OUT / 'imported-legacy-target-refused.log').write_text(log, encoding='utf-8')
    assert process.returncode and 'legacy capability family' in log, (process.returncode, log[-4000:])
    mixed.append('imported-legacy-target-refused')

    reports = {}
    for name in ['frozen-legacy-acceptance', 'raw-acceptance']:
        report = json.loads((OUT / name / 'result.json').read_text(encoding='utf-8'))
        assert report['accepted'] is True and report['host_ui_accepted'] is False
        if name == 'frozen-legacy-acceptance':
            # This unchanged report has no adopted field. Validate the actual
            # published contract rather than inventing a missing false value.
            assert report['product_wiring_accepted'] is False
        else:
            assert report['adopted'] is False and report['actual_hosts'] is False
        assert report['count'] == len(report['checks'])
        assert (report['source_sha'], report['run_id'], report['attempt']) == (
            os.environ['GITHUB_SHA'], os.environ['GITHUB_RUN_ID'], os.environ['GITHUB_RUN_ATTEMPT'])
        reports[name] = {'count': report['count'], 'checks': report['checks'],
                         'sha256': hashlib.sha256((OUT / name / 'result.json').read_bytes()).hexdigest()}
    assert reports['raw-acceptance']['count'] == 20
    assert reports['frozen-legacy-acceptance']['count'] == 22

    logs = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(OUT.glob('*.log'))}
    result = {'accepted': True, 'adopted': False, 'source_sha': os.environ['GITHUB_SHA'],
              'run_id': os.environ['GITHUB_RUN_ID'], 'attempt': os.environ['GITHUB_RUN_ATTEMPT'],
              'platform': sys.platform, 'frozen_start': BASE, 'frozen_sdk': FROZEN_SDK,
              'families': {'legacy': {'view': '0.1.0', 'session': '0.1.0', 'sync': '0.1.0', 'revisions': '0.3.0'},
                           'raw': {'view': '0.2.0', 'session': '0.2.0', 'sync': '0.2.0', 'revisions': '0.4.0'}},
              'default_family_unchanged': True, 'raw_symbols_absent_from_default': True,
              'original_consumer_unchanged': True, 'reports': reports, 'mixed_profiles_refused': mixed,
              'programs': {name: hashlib.sha256((raw_consumer / (name + SUFFIX)).read_bytes()).hexdigest()
                           for name in ['raw-view-consumer', 'raw-view-c-consumer', 'raw-revision']},
              'logs': logs, 'actual_hosts': False, 'physical_device': False, 'complete_product': False,
              'scope': 'explicit sync-status-view raw session0.2 family only'}
    (OUT / 'result.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: value for key, value in result.items() if key != 'logs'}), flush=True)


if __name__ == '__main__':
    main()
