"""Wave3 S18: joint default/raw install and unchanged original business replay.

Every build, install, fixture, program run and report write happens only in GitHub
Actions. The untouched judges of C06 (reader_next_c06), S14, S15, S16 and S17 are
reused as independent validators; their own branch and ownership guards are not
executed. This wave's guard declares the fixed seed and the exact owned paths.
"""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import time
import traceback

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'build/reader-wave3-s18'
RT = OUT / 'runtime'
LOGS = RT / 'logs'
EVIDENCE = RT / 'evidence'
BUILD = ROOT / 'build/s18b'
SEED = 'd263ce5228838ac90c0a0dc13a5193d4a7739681'
SDK_SOURCE = '9d3a3f8bfa06c099ebba0d9e1ba613d276c3af09'
FROZEN_SDK = '9854061be331fe603a1822d9b2b36ee357154927'
LEGACY_START = 'e67d87cbeabb2457e0852f681ef0b27b2c0da4d8'
EXE = '.exe' if os.name == 'nt' else ''
PY = sys.executable
RUNNER = os.environ.get('RUNNER_OS', platform.system())
ENV = dict(os.environ)
MODULES = [
    ('revisions', 'EXReaderRevisions', {'default': '0.3.0', 'raw': '0.4.0'}),
    ('reading-state', 'EXReaderReadingState', {'default': '0.1.0', 'raw': '0.2.0'}),
    ('commands', 'EXReaderCommands', {'default': '0.1.0', 'raw': '0.2.0'}),
    ('sync', 'EXReaderSync', {'default': '0.1.0', 'raw': '0.2.0'}),
    ('session', 'EXReaderSession', {'default': '0.1.0', 'raw': '0.2.0'}),
    ('annotation-export', 'EXReaderAnnotationExport', {'default': '0.1.0', 'raw': '0.2.0'}),
    ('annotation-import', 'EXReaderAnnotationImport', {'default': '0.1.0', 'raw': '0.2.0'}),
    ('font-library', 'EXReaderFontLibrary', {'default': '0.1.0', 'raw': '0.1.0'}),
    ('original-export', 'EXReaderOriginalExport', {'default': '0.1.0', 'raw': '0.1.0'}),
    ('jump-history', 'EXReaderJumpHistory', {'default': '0.1.0', 'raw': '0.2.0'}),
    ('sync-status-view', 'EXReaderSyncView', {'default': '0.1.0', 'raw': '0.2.0'}),
]
FAMILIES = {'default': {'raw': False, 'prefix': ROOT / 'build/s14-stage', 'version': '0.1.0'},
            'raw': {'raw': True, 'prefix': OUT / 'raw-stage', 'version': '0.2.0'}}
PROGRAMS, REPORTS, RESULTS = {}, {}, {}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def identity(path):
    data = Path(path).read_bytes()
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def program(path):
    path = Path(path).resolve()
    assert path.is_file(), path
    PROGRAMS[str(path.relative_to(ROOT))] = path
    return path


def publish(name, path):
    path = Path(path).resolve()
    assert path.is_file(), path
    REPORTS[name] = path


def run(args, label, timeout=2400, check=True, cwd=None, env=None):
    args = [str(a) for a in args]
    print('RUN', label, flush=True)
    started = time.monotonic()
    process = subprocess.run(args, cwd=str(cwd or ROOT), env=env or ENV, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace',
                             timeout=timeout)
    LOGS.mkdir(parents=True, exist_ok=True)
    (LOGS / (label + '.log')).write_text('$ ' + ' '.join(args) + '\nexit=' + str(process.returncode)
                                         + '\n' + process.stdout, encoding='utf-8')
    print(process.stdout[-3000:], flush=True)
    print('EXIT', label, process.returncode, round(time.monotonic() - started, 1), flush=True)
    if check and process.returncode:
        raise RuntimeError((label, process.returncode, process.stdout[-3000:]))
    return process


def build(source, label, prefix, extra=(), install=True, target=None):
    target = Path(target) if target else BUILD / label
    run(['cmake', '-S', str(source), '-B', str(target), '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release',
         '-DCMAKE_INSTALL_PREFIX=' + str(prefix), *extra], label + '-configure')
    run(['cmake', '--build', str(target), '--parallel', '4'], label + '-build')
    if install:
        run(['cmake', '--install', str(target)], label + '-install')
    return target


def archive(commit, target, paths):
    target = Path(target)
    target.mkdir(parents=True, exist_ok=False)
    raw = subprocess.run(['git', 'archive', commit, *paths], cwd=str(ROOT), check=True, capture_output=True).stdout
    with tarfile.open(fileobj=io.BytesIO(raw)) as tar:
        tar.extractall(target, filter='data')
    return target


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def package_version(prefix, package):
    path = Path(prefix) / 'lib/cmake' / package / (package + 'ConfigVersion.cmake')
    if not path.is_file():
        return None
    for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
        line = line.strip()
        if line.startswith('set(PACKAGE_VERSION'):
            return line.split('"')[1]
    return None


def sdk_stage():
    return ROOT / 'build/reading-library/stage'


def sdk340_stage():
    return BUILD / 'sdk340-src/build/reading-library/stage'


def shared_stage():
    return OUT / 'shared-stage'


def search_path(*paths):
    return '-DCMAKE_PREFIX_PATH=' + ';'.join(str(path) for path in paths)


def must_fail(args, label, needle, timeout=1200):
    process = run(args, label, timeout, check=False)
    assert process.returncode != 0, label + ': the configure unexpectedly succeeded'
    assert needle in process.stdout, (label, needle, process.stdout[-3000:])
    return {'name': label, 'refusal': needle, 'refused': True}


def prepare():
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only'
    for directory in (OUT, RT, LOGS, EVIDENCE, BUILD):
        directory.mkdir(parents=True, exist_ok=True)
    source = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=str(ROOT), text=True).strip()
    assert source == os.environ['GITHUB_SHA'], (source, os.environ['GITHUB_SHA'])
    return {'source_sha': source, 'seed': SEED, 'sdk_source': SDK_SOURCE, 'frozen_sdk': FROZEN_SDK,
            'legacy_start': LEGACY_START, 'runner': RUNNER}


def sdk():
    run(['cmake', '--preset', 'reading-library'], 'sdk341-configure', 1800)
    run(['cmake', '--build', '--preset', 'reading-library', '--parallel', '4'], 'sdk341-build', 3600)
    run(['cmake', '--install', 'build/reading-library'], 'sdk341-install', 1800)
    stage = sdk_stage()
    config = (stage / 'lib/cmake/EXReader/EXReaderConfig.cmake').read_text(encoding='utf-8')
    assert 'set(EXReader_VERSION "3.41.0")' in config, 'the installed SDK is not the approved 3.41.0'
    assert '#define EXR_VERSION "3.41.0"' in (stage / 'include/exr/base.h').read_text(encoding='utf-8')
    return {'sdk': str(stage), 'config_sha256': sha(stage / 'lib/cmake/EXReader/EXReaderConfig.cmake')}


def sdk340():
    source = BUILD / 'sdk340-src'
    if source.exists():
        shutil.rmtree(source)
    source.mkdir(parents=True)
    raw = subprocess.run(['git', 'archive', FROZEN_SDK], cwd=str(ROOT), check=True, capture_output=True).stdout
    with tarfile.open(fileobj=io.BytesIO(raw)) as tar:
        tar.extractall(source, filter='data')
    run(['cmake', '--preset', 'reading-library'], 'sdk340-configure', 1800, cwd=source)
    run(['cmake', '--build', '--preset', 'reading-library', '--parallel', '4'], 'sdk340-build', 3600, cwd=source)
    run(['cmake', '--install', 'build/reading-library'], 'sdk340-install', 1800, cwd=source)
    stage = sdk340_stage()
    config = (stage / 'lib/cmake/EXReader/EXReaderConfig.cmake').read_text(encoding='utf-8')
    assert 'set(EXReader_VERSION "3.40.0")' in config, 'the frozen install is not SDK 3.40.0'
    assert '#define EXR_VERSION "3.40.0"' in (stage / 'include/exr/base.h').read_text(encoding='utf-8')
    return {'sdk340': str(stage), 'config_sha256': sha(stage / 'lib/cmake/EXReader/EXReaderConfig.cmake'),
            'archive': FROZEN_SDK}


def shared():
    prefix = shared_stage()
    build(ROOT / 'apps/reader/store/native', 'product', prefix)
    run(['ctest', '--test-dir', str(BUILD / 'product'), '--output-on-failure', '--no-tests=error',
         '--timeout', '180'], 'product-ctest', 900)
    # The documented Apple transport is the native Foundation session, so the fixture CA
    # trusted through the system keychain is honored; Linux and Windows keep the same
    # libcurl and WinHTTP transports their own acceptance already used.
    webdav = ['-DEXR_WEBDAV_APPLE_URLSESSION=ON'] if sys.platform == 'darwin' else []
    build(ROOT / 'extras/webdav', 'webdav', prefix, webdav)
    build(ROOT / 'extras/sideload', 'sideload', prefix, ['-DEXR_SDK=' + str(sdk_stage())])
    packages = sorted(path.name for path in (prefix / 'lib/cmake').iterdir())
    assert {'EXReaderProductCatalog', 'EXReaderWebDAV', 'EXReaderSideload'} <= set(packages), packages
    return {'shared': str(prefix), 'packages': packages}


def families():
    installed = {}
    for label, spec in FAMILIES.items():
        prefix = spec['prefix']
        prefix.mkdir(parents=True, exist_ok=True)
        flags = [search_path(prefix, shared_stage(), sdk_stage()), '-DEXR_SDK=' + str(sdk_stage()),
                 '-DEXR_SDK_VERSION=3.41.0', '-DREADER_PRODUCT_PREFIX=' + str(shared_stage()),
                 '-DREADER_ANNOTATION_IMPORT_BUILD=ON', '-DREADER_FONT_LIBRARY_BUILD=ON',
                 '-DEXR_READER_SELECTOR_BYTES_CANDIDATE=' + ('ON' if spec['raw'] else 'OFF')]
        versions = {}
        for module, package, expected in MODULES:
            build(ROOT / 'apps/reader' / module, label + '-' + module, prefix, flags)
            actual = package_version(prefix, package)
            assert actual == expected[label], (label, package, actual, expected[label])
            versions[package] = actual
        installed[label] = {'prefix': str(prefix), 'family_version': spec['version'], 'packages': versions,
                            'raw': spec['raw']}
    return {'installed': installed}


def graph():
    entries = {}
    controls = []
    control_source = ROOT / 'tests/reader_wave3_s18/consumer/path-controls'
    for case, refusal in (('known', None), ('foreign', 'Foreign imported path:'),
                          ('unknown', 'Unsupported imported path expression:'),
                          ('cycle', 'Cyclic imported path expression:')):
        command = ['cmake', '-S', control_source, '-B', BUILD / ('path-control-' + case),
                   '-G', 'Ninja', '-DCASE=' + case]
        label = 'imported-path-' + case
        if refusal:
            controls.append(must_fail(command, label, refusal))
        else:
            result = run(command, label, 300)
            assert 'S18 known TARGET_PROPERTY source accepted' in result.stdout, result.stdout
            controls.append({'name': label, 'accepted': True})
    for label, spec in FAMILIES.items():
        prefix, shared_prefix, sdk_prefix = (spec['prefix'], shared_stage(), sdk_stage())
        target = build(ROOT / 'tests/reader_wave3_s18/consumer', 'graph-' + label,
                       OUT / ('graph-' + label + '-stage'),
                       [search_path(prefix, shared_prefix, sdk_prefix), '-DFAMILY_VERSION=' + spec['version'],
                        '-DFAMILY_PREFIX=' + str(prefix), '-DSHARED_PREFIX=' + str(shared_prefix),
                        '-DSDK_PREFIX=' + str(sdk_prefix)], install=False)
        binary = program(target / ('foundation-consumer' + EXE))
        result = run([binary], 'graph-' + label + '-run', 600)
        assert result.stdout.strip() == 'FOUNDATION-CONSUMER ' + spec['version'], result.stdout
        origins = target / 'origins.txt'
        lines = [line for line in origins.read_text(encoding='utf-8').splitlines() if line]
        assert len(lines) >= 12, lines
        targets = {line.split('|')[0] for line in lines}
        for package in ('EXReaderAnnotationExport', 'EXReaderAnnotationImport', 'EXReaderFontLibrary',
                        'EXReaderOriginalExport', 'EXReaderJumpHistory', 'EXReaderSyncView'):
            assert any(name.startswith(package + '::') for name in targets), (label, package, sorted(targets))
        assert any(name.startswith('EXReader::') for name in targets), sorted(targets)
        allowed = [Path(prefix).resolve(), Path(shared_prefix).resolve(), Path(sdk_prefix).resolve()]
        for line in lines:
            path = Path(line.split('|')[2]).resolve()
            assert any(path == root or str(path).startswith(str(root) + os.sep) for root in allowed), line
        publish('graph-' + label + '-origins.txt', origins)
        expressions = target / 'genexpr-origins.txt'
        expression_lines = expressions.read_text(encoding='utf-8').splitlines()
        expected_expression = ('EXReaderReadingState::reader_reading_state|INTERFACE_INCLUDE_DIRECTORIES|'
                               '$<TARGET_PROPERTY:EXReader::exr_core,INTERFACE_INCLUDE_DIRECTORIES>|EXReader::exr_core')
        assert expected_expression in expression_lines, (label, expression_lines)
        publish('graph-' + label + '-genexpr-origins.txt', expressions)
        entries[label] = {'binary_sha256': sha(binary), 'origins_sha256': sha(origins),
                          'origins_lines': len(lines), 'targets': sorted(targets),
                          'genexpr_sha256': sha(expressions), 'genexpr_origins': expression_lines}
    return {'graphs': entries, 'path_controls': controls}


def font():
    sdk_prefix = sdk_stage()
    prefix, shared_prefix = FAMILIES['default']['prefix'], shared_stage()
    build(ROOT / 'tests/reader_next_s14/consumer', 's14-consumer', prefix,
          ['-DEXPECTED_SDK_VERSION=3.41.0', '-DEXPECTED_SDK_TAG=sdk341', search_path(prefix, sdk_prefix)],
          install=False, target=ROOT / 'build/s14-consumer')
    program(ROOT / 'build/s14-consumer' / ('font-probe' + EXE))
    program(ROOT / 'build/s14-consumer' / ('font-c' + EXE))
    default_off = ROOT / 'build/s14-default-off'
    if default_off.exists():
        shutil.rmtree(default_off)
    run(['cmake', '-S', 'apps/reader/font-library', '-B', 'build/s14-default-off', '-G', 'Ninja',
         '-DCMAKE_BUILD_TYPE=Release'], 'font-default-off-configure')
    run(['cmake', '--build', 'build/s14-default-off'], 'font-default-off-build')
    env = dict(ENV, S14_SDK_STAGE=str(sdk_prefix), S14_SDK_VERSION='3.41.0')
    run([PY, 'tests/reader_next_s14/run.py'], 'font-full', 2400, env=env)
    report = json.loads((ROOT / 'build/s14-evidence/result.json').read_text(encoding='utf-8'))
    expected = 61 if os.name == 'nt' else 60
    assert report['accepted'] is True and len(report['checks']) == expected, (report['accepted'], report['failures'])
    assert len(report['checks']) == len(set(report['checks'])), 'duplicate S14 case'
    run([PY, 'tests/reader_next_s14/preloaded.py'], 'font-preloaded', 1200, env=env)
    preloaded = json.loads((ROOT / 'build/s14-evidence/preloaded/result.json').read_text(encoding='utf-8'))
    assert preloaded['accepted'] is True and len(preloaded['cases']) == 4, preloaded
    assert all(row['passed'] for row in preloaded['cases'])
    contract = run([PY, 'tests/reader_next_s14/verify.py', '--self-test'], 'font-negative-contracts', 1200, env=env)
    text = contract.stdout
    negatives = json.loads(text[text.find('{'):]) if '{' in text else {}
    (OUT / 's14-negative-contracts.json').write_text(json.dumps(negatives, indent=2) + '\n', encoding='utf-8')
    assert negatives['self_test'] is True and negatives['negative_cases'] == 42, negatives
    assert negatives['accepted_platforms'] == 4, negatives
    publish('s14-result.json', ROOT / 'build/s14-evidence/result.json')
    publish('s14-preloaded.json', ROOT / 'build/s14-evidence/preloaded/result.json')
    publish('s14-negative-contracts.json', OUT / 's14-negative-contracts.json')
    return {'report': 's14-result.json', 'checks': len(report['checks']),
            'native_commands': len(report['commands']), 'terminations': len(report['terminations']),
            'preloaded_controls': len(preloaded['cases']), 'negative_contracts': negatives['negative_cases'],
            'synthetic_platforms': negatives['accepted_platforms']}


def annotation():
    c06 = load('wave3_c06', 'tests/reader_next_c06/run.py')
    c06.OUT.mkdir(parents=True, exist_ok=True)
    sdk_prefix = sdk_stage()
    shared_prefix = shared_stage()
    default = FAMILIES['default']['prefix']
    raw = FAMILIES['raw']['prefix']
    pdf = ROOT / 'tests/fixtures/pdf-public-text.pdf'
    fixed_import = subprocess.check_output(
        ['git', 'show', c06.IMPORT_SOURCE + ':apps/reader/annotation-import/src/annotation_import.cpp'],
        cwd=str(ROOT))
    assert (ROOT / 'apps/reader/annotation-import/src/annotation_import.cpp').read_bytes().startswith(fixed_import)
    fixed_header = subprocess.check_output(
        ['git', 'show', c06.IMPORT_SOURCE + ':apps/reader/annotation-import/include/reader_annotation_import.h'],
        cwd=str(ROOT))
    assert (ROOT / 'apps/reader/annotation-import/include/reader_annotation_import.h').read_bytes() == fixed_header
    thumbnail = subprocess.check_output(
        ['git', 'show', c06.START + ':apps/reader/thumbnails/src/thumbnails.cpp'], cwd=str(ROOT))
    copied = (ROOT / 'apps/reader/annotation-import/src/portable_sha256.h').read_bytes()

    def sha_struct(data):
        return data.split(b'struct Sha256 {', 1)[1].split(b'\n};', 1)[0]

    assert sha_struct(thumbnail) == sha_struct(copied), 'streaming SHA-256 implementation differs'
    assert subprocess.run(['git', 'diff', '--quiet', c06.START, 'HEAD', '--',
                           'apps/reader/annotation-export/include/reader_annotation_export.h'],
                          cwd=str(ROOT)).returncode == 0, 'legacy export header changed'
    assert len(pdf.read_bytes()) == 8845 and sha(pdf) == c06.PDF_SHA, 'the public PDF fixture changed'
    core = c06.core('wave3-core-off', False, shared_prefix, sdk_prefix)
    old_export = c06.archive(c06.START, 'wave3-baseline-export', 'apps/reader/annotation-export')
    old_import = c06.archive(c06.IMPORT_SOURCE, 'wave3-baseline-import', 'apps/reader/annotation-import')
    baseline_prefix = c06.modules('wave3-baseline', False, core, shared_prefix, sdk_prefix,
                                  old_export / 'apps/reader/annotation-export',
                                  old_import / 'apps/reader/annotation-import')
    baseline_exe = program(c06.consumer('wave3-baseline-consumer', False, baseline_prefix, core,
                                        shared_prefix, sdk_prefix))
    off_exe = program(c06.consumer('wave3-off-consumer', False, default, shared_prefix, sdk_prefix))
    raw_exe = program(c06.consumer('wave3-raw-consumer', True, raw, shared_prefix, sdk_prefix))
    consumer_dir = ROOT / 'tests/reader_next_c06/consumer'
    c06.expect(c06.refused_configure(consumer_dir, 'wave3-mixed-raw-on-legacy',
                                     ['-DC06_RAW=ON', c06.paths(default, shared_prefix, sdk_prefix)]),
               'raw consumer refuses the joint legacy install')
    c06.expect(c06.refused_configure(consumer_dir, 'wave3-mixed-legacy-on-raw',
                                     ['-DC06_RAW=OFF', c06.paths(raw, shared_prefix, sdk_prefix)]),
               'legacy consumer refuses the joint raw install')
    c06.expect(c06.refused_configure(ROOT / 'apps/reader/annotation-export', 'wave3-raw-export-on-legacy-core',
                                     ['-DEXR_READER_SELECTOR_BYTES_CANDIDATE=ON',
                                      c06.paths(default, shared_prefix, sdk_prefix)]),
               'raw export refuses the legacy revisions/reading-state family')
    c06.expect(c06.refused_configure(ROOT / 'apps/reader/annotation-import', 'wave3-legacy-import-on-raw-core',
                                     ['-DREADER_ANNOTATION_IMPORT_BUILD=ON',
                                      c06.paths(raw, shared_prefix, sdk_prefix)]),
               'legacy import refuses the raw revisions family')
    hashes = [c06.legacy_phase(label, binary, c06.OUT / ('legacy-' + label))
              for label, binary in [('baseline', baseline_exe), ('off', off_exe), ('raw', raw_exe)]]
    assert hashes[0] == hashes[1] == hashes[2], ('legacy annotation bytes differ', hashes)
    digests, keys = c06.raw_phase(raw_exe, off_exe, pdf, c06.OUT / 'raw')
    assert os.environ.get('GH_TOKEN'), 'GH_TOKEN is required for the certified Mac records'
    mac = c06.mac_phase(raw_exe, c06.OUT / 'mac')
    assert not c06.FAILED, c06.FAILED
    assert mac['totals']['heads'] >= 1, mac
    assert mac['peer']['null_revision_ids'], mac['peer']
    assert mac['totals']['null_heads'] >= 1, mac['totals']
    checks = list(c06.CHECKS)
    for expected_check in ('baseline legacy export OK', 'off legacy export OK', 'raw legacy export OK',
                           'raw seed from the real PDF through the explicit raw encoder',
                           'raw3 export pdf', 'export left the sender store unchanged',
                           'typed NULL exact stays NULL', 'allocated empty stays allocated empty',
                           'raw importer refuses the legacy v1 file with zero writes',
                           'resume from next_index completes the import',
                           'real Mac annotation heads were exported'):
        assert expected_check in checks, (expected_check, len(checks))
    result = {'accepted': True, 'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
              'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'platform': RUNNER,
              'checks': checks, 'failed': c06.FAILED, 'check_count': len(checks),
              'legacy_outputs': hashes[0], 'legacy_all_equal': True, 'raw_outputs': digests,
              'raw_keys': keys, 'mac_records': mac, 'mac_found_claimed': False,
              'mac_found_policy': 'ALREADY_VERIFIED: the certified Mac records have no SDK documents, '
                                  'so found_checked=0 and no FOUND is claimed',
              'scope': 'explicit raw0.2 portable annotation candidate; not adopted',
              'adopted': False, 'host_ui': False, 'physical_device': False}
    (c06.OUT / 'wave3-annotation.json').write_text(json.dumps(result, indent=2, default=list) + '\n',
                                                   encoding='utf-8')
    publish('annotation.json', c06.OUT / 'wave3-annotation.json')
    for label in ('baseline', 'off', 'raw'):
        for name in ('legacy.jsonl', 'legacy.md'):
            publish('annotation-legacy-' + label + '-' + name, c06.OUT / ('legacy-' + label) / name)
    publish('annotation-mac-peer.json', c06.OUT / 'mac/peer/peer.json')
    return {'checks': len(checks), 'legacy_outputs': hashes[0], 'legacy_all_equal': True,
            'raw_books': len(digests), 'mac_heads': mac['totals']['heads'],
            'mac_null_heads': mac['totals']['null_heads'], 'mac_found_claimed': False,
            'mac_anchor_versions': mac['totals']['versions']}


def jump():
    s16 = load('wave3_s16', 'tests/reader_next_s16/run.py')
    sdk_prefix = sdk_stage()
    shared_prefix = shared_stage()
    default, raw = FAMILIES['default']['prefix'], FAMILIES['raw']['prefix']
    work = OUT / 's16'
    work.mkdir(parents=True, exist_ok=True)
    fixtures = work / 'fixtures'
    if fixtures.exists():
        shutil.rmtree(fixtures)
    run([PY, 'tests/reader_jump_history/make_fixtures.py', fixtures], 'jump-fixtures', 600)
    font_path = ROOT / 'tests/fixtures/fonts/primary.ttf'
    pdf = ROOT / 'tests/fixtures/pdf-public-text.pdf'
    baseline_source = archive(LEGACY_START, work / 'baseline-source', ['apps/reader/jump-history'])
    baseline = work / 'baseline-stage'
    build(baseline_source / 'apps/reader/jump-history', 'jump-baseline', baseline,
          [search_path(default, shared_prefix, sdk_prefix)])
    original = work / 'consumers/original'
    if original.exists():
        shutil.rmtree(original)
    original.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ROOT / 'tests/reader_jump_history/consumer', original)
    raw_consumer = work / 'consumers/raw-original'
    if raw_consumer.exists():
        shutil.rmtree(raw_consumer)
    shutil.copytree(ROOT / 'tests/reader_jump_history/consumer', raw_consumer)
    text = (raw_consumer / 'CMakeLists.txt').read_text(encoding='utf-8')
    patched = text.replace('find_package(EXReaderJumpHistory 0.1.0 EXACT CONFIG REQUIRED)',
                           'find_package(EXReaderJumpHistory 0.2.0 EXACT CONFIG REQUIRED)')
    differences = [pair for pair in zip(text.splitlines(), patched.splitlines()) if pair[0] != pair[1]]
    assert len(differences) == 1, differences
    (raw_consumer / 'CMakeLists.txt').write_text(patched, encoding='utf-8')
    suites, archives = {}, {}
    for label, prefix, source, extra in (('baseline', baseline, original, (default,)),
                                         ('default', default, original, ()),
                                         ('raw', raw, raw_consumer, ())):
        consumer = build(source, 'jump-original-' + label, prefix,
                         [search_path(prefix, *extra, shared_prefix, sdk_prefix)], install=False)
        probe = program(consumer / ('jump-history-probe' + EXE))
        c_consumer = program(consumer / ('jump-history-c-consumer' + EXE))
        output = work / ('evidence/original-' + label)
        run([PY, 'tests/reader_jump_history/check_jump_history.py', '--probe', probe, '--c-consumer', c_consumer,
             '--fixtures', fixtures, '--font', font_path, '--installed', prefix, '--platform', RUNNER,
             '--output', output], 'jump-original-' + label, 1800)
        summary = json.loads((output / 'summary.json').read_text(encoding='utf-8'))
        publish('s16-original-' + label + '.json', output / 'summary.json')
        assert summary['jump_history_module_accepted'] is True, (label, summary.get('problems'))
        assert summary['checks_failed'] == 0 and summary['checks_total'] >= 149, (label, summary['checks_total'])
        assert summary['host_wiring_accepted'] is False
        suites[label] = summary
        libraries = [path for path in (Path(prefix) / 'lib').glob('*') if 'jump_history' in path.name]
        assert len(libraries) == 1, (label, libraries)
        archives[label] = {'member': libraries[0].name, **identity(libraries[0])}
    assert s16.original_projection(suites['baseline']) == s16.original_projection(suites['default']), \
        'the default install changed an original jump-history result'
    raw_build = build(ROOT / 'tests/reader_next_s16/consumer', 'jump-raw-consumer', raw,
                      ['-DS16_RAW=ON', search_path(raw, shared_prefix, sdk_prefix)], install=False)
    raw_probe = program(raw_build / ('s16-raw-probe' + EXE))
    raw_c = program(raw_build / ('s16-c-consumer' + EXE))
    run([PY, 'tests/reader_next_s16/check_raw.py', '--mode', 'raw', '--consumer', raw_c, '--probe', raw_probe,
         '--fixtures', fixtures, '--font', font_path, '--pdf', pdf, '--pdf-sha', s16.PDF_SHA,
         '--installed', raw, '--platform', RUNNER, '--output', work / 'evidence/raw'], 'jump-raw-suite', 1800)
    default_build = build(ROOT / 'tests/reader_next_s16/consumer', 'jump-default-consumer', default,
                          ['-DS16_RAW=OFF', search_path(default, shared_prefix, sdk_prefix)], install=False)
    default_c = program(default_build / ('s16-c-consumer' + EXE))
    run([PY, 'tests/reader_next_s16/check_raw.py', '--mode', 'default', '--consumer', default_c,
         '--fixtures', fixtures, '--installed', default, '--platform', RUNNER,
         '--output', work / 'evidence/default'], 'jump-default-suite', 900)
    raw_summary = json.loads((work / 'evidence/raw/summary.json').read_text(encoding='utf-8'))
    default_summary = json.loads((work / 'evidence/default/summary.json').read_text(encoding='utf-8'))
    publish('s16-raw.json', work / 'evidence/raw/summary.json')
    publish('s16-default.json', work / 'evidence/default/summary.json')
    negatives = [
        must_fail(['cmake', '-S', str(ROOT / 'apps/reader/jump-history'), '-B', str(BUILD / 'jump-neg-raw'),
                   '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release', '-DEXR_READER_SELECTOR_BYTES_CANDIDATE=ON',
                   search_path(default, shared_prefix, sdk_prefix)],
                  'jump-negative-raw-against-default', 'requested version "0.2.0"'),
        must_fail(['cmake', '-S', str(ROOT / 'apps/reader/jump-history'), '-B', str(BUILD / 'jump-neg-default'),
                   '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release', '-DEXR_READER_SELECTOR_BYTES_CANDIDATE=OFF',
                   search_path(raw, shared_prefix, sdk_prefix)],
                  'jump-negative-default-against-raw', 'requested version "0.1.0"'),
        must_fail(['cmake', '-S', str(original), '-B', str(BUILD / 'jump-neg-consumer'),
                   '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release', search_path(raw, shared_prefix, sdk_prefix)],
                  'jump-negative-original-consumer-against-raw', 'EXReaderJumpHistory'),
    ]
    fake = work / 'negatives/faked-prefix'
    if fake.exists():
        shutil.rmtree(fake)
    fake.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(default, fake)
    version_file = fake / 'lib/cmake/EXReaderReadingState/EXReaderReadingStateConfigVersion.cmake'
    version_text = version_file.read_text(encoding='utf-8')
    assert 'set(PACKAGE_VERSION "0.1.0")' in version_text
    version_file.write_text(version_text.replace('set(PACKAGE_VERSION "0.1.0")', 'set(PACKAGE_VERSION "0.2.0")'),
                            encoding='utf-8')
    negatives.append(must_fail(
        ['cmake', '-S', str(ROOT / 'apps/reader/jump-history'), '-B', str(BUILD / 'jump-neg-faked'),
         '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release', '-DEXR_READER_SELECTOR_BYTES_CANDIDATE=ON',
         search_path(fake, default, shared_prefix, sdk_prefix)],
        'jump-negative-faked-family-target',
        'Raw candidate jump history requires the raw candidate reading-state target'))
    programs = {}
    for name, path in (('raw_probe', raw_probe), ('raw_c_consumer', raw_c), ('default_c_consumer', default_c),
                       ('original_probe', BUILD / 'jump-original-default' / ('jump-history-probe' + EXE)),
                       ('original_c_consumer', BUILD / 'jump-original-default' / ('jump-history-c-consumer' + EXE)),
                       ('baseline_probe', BUILD / 'jump-original-baseline' / ('jump-history-probe' + EXE)),
                       ('baseline_c_consumer', BUILD / 'jump-original-baseline' / ('jump-history-c-consumer' + EXE)),
                       ('original_raw_probe', BUILD / 'jump-original-raw' / ('jump-history-probe' + EXE)),
                       ('original_raw_c_consumer', BUILD / 'jump-original-raw' / ('jump-history-c-consumer' + EXE))):
        path = program(path)
        programs[name] = {'member': str(Path(path).relative_to(ROOT)), **identity(path)}
    assert len(programs) == 9, programs
    assert raw_summary['accepted'] is True, raw_summary['problems']
    assert default_summary['accepted'] is True, default_summary['problems']
    assert raw_summary['checks_total'] == 162, raw_summary['checks_total']
    assert default_summary['checks_total'] == 21, default_summary['checks_total']
    assert raw_summary['versions'] == {'install': '0.2.0', 'jump_history': '0.1.0', 'reading_state': '0.2.0',
                                       'revisions': '0.4.0', 'sdk': '3.41.0'}, raw_summary['versions']
    # Preserve the original S16 artifact layout. The unchanged complete_bindings
    # can then authenticate actual roles, raw reports and installed archive bytes.
    bound = RT / 's16'
    def retain(source, member):
        destination = bound / member
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        return {'member': member, **identity(destination)}
    stems = {
        'raw_probe': 'build/raw-consumer/s16-raw-probe',
        'raw_c_consumer': 'build/raw-consumer/s16-c-consumer',
        'default_c_consumer': 'build/default-consumer/s16-c-consumer',
        'original_probe': 'build/original-default-consumer/jump-history-probe',
        'original_c_consumer': 'build/original-default-consumer/jump-history-c-consumer',
        'baseline_probe': 'build/original-baseline-consumer/jump-history-probe',
        'baseline_c_consumer': 'build/original-baseline-consumer/jump-history-c-consumer',
        'original_raw_probe': 'build/original-raw-consumer/jump-history-probe',
        'original_raw_c_consumer': 'build/original-raw-consumer/jump-history-c-consumer',
    }
    bindings = {}
    for role, record in programs.items():
        bindings[role] = retain(ROOT / record['member'], stems[role] + EXE)
        assert bindings[role]['sha256'] == record['sha256']
    for label, prefix in (('baseline', baseline), ('default', default), ('raw', raw)):
        retain(prefix / 'include/reader_jump_history.h', 'families/' + label + '-stage/include/reader_jump_history.h')
        library = 'reader_jump_history.lib' if os.name == 'nt' else 'libreader_jump_history.a'
        retain(prefix / 'lib' / library, 'families/' + label + '-stage/lib/' + library)
        for filename in ('summary.json', 'report.json'):
            retain(work / ('evidence/original-' + label) / filename, 'evidence/original-' + label + '/' + filename)
    for filename in ('summary.json', 'report.json'):
        retain(work / 'evidence/raw' / filename, 'evidence/raw/' + filename)
    retain(work / 'evidence/default/summary.json', 'evidence/default/summary.json')
    (bound / 'result.json').write_text(json.dumps({
        'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
        'run_attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'platform': RUNNER,
        'programs': bindings,
    }, indent=2) + '\n', encoding='utf-8')
    return {'original_checks': {label: suites[label]['checks_total'] for label in suites},
            'original_cases': {label: suites[label]['cases_total'] for label in suites},
            'raw_checks': raw_summary['checks_total'], 'default_checks': default_summary['checks_total'],
            'default_equals_baseline': True, 'programs': len(programs), 'archives': archives,
            'mixed_refusals': negatives}


def original():
    sdk_prefix, sdk340_prefix = sdk_stage(), sdk340_stage()
    default, shared_prefix = FAMILIES['default']['prefix'], shared_stage()
    work = OUT / 's15'
    work.mkdir(parents=True, exist_ok=True)
    fixtures = work / 'fixtures'
    if fixtures.exists():
        shutil.rmtree(fixtures)
    run([PY, 'tests/reader_next_s15/make_fixtures.py', fixtures], 'original-fixtures', 600)
    consumer_source = work / 'consumer-src'
    consumer_source.mkdir(parents=True, exist_ok=True)
    for name in ('CMakeLists.txt', 'api.c', 'probe.cpp'):
        shutil.copyfile(ROOT / 'tests/reader_next_s15/consumer' / name, consumer_source / name)
    consumer = build(consumer_source, 's15-consumer', default,
                     [search_path(default, sdk_prefix, shared_prefix)], install=False)
    probe = program(consumer / ('original-export-probe' + EXE))
    c_consumer = program(consumer / ('original-export-c-consumer' + EXE))
    evidence = work / 'evidence'
    evidence.mkdir(parents=True, exist_ok=True)
    graph_report = evidence / 'graph.json'
    run([PY, 'tests/reader_next_s15/check_install_graph.py', '--module-src', 'apps/reader/original-export',
         '--stage', default, '--sdk', sdk_prefix, '--work', work / 'graph-work', '--consumer', consumer_source,
         '--output', graph_report], 'original-graph', 1800)
    library = default / 'lib' / ('reader_original_export.lib' if os.name == 'nt' else 'libreader_original_export.a')
    run([PY, 'tests/reader_next_s15/check_export.py', probe, c_consumer, fixtures, evidence, library,
         sdk_prefix, graph_report], 'original-full', 1800)
    frozen = work / 'frozen-work'
    run([PY, 'tests/reader_next_s15/check_frozen_sdk.py', '--sdk', sdk340_prefix,
         '--module-src', 'apps/reader/original-export', '--stage', work / 'stage340',
         '--consumer', ROOT / 'tests/reader_next_s15/consumer', '--fixtures', fixtures,
         '--work', frozen, '--output', frozen / 'frozen.json'], 'original-frozen', 1800)
    stage341 = work / 'stage341'
    build(ROOT / 'apps/reader/original-export', 's15-preload-module', stage341,
          ['-DEXR_SDK=' + str(sdk_prefix), '-DEXR_SDK_VERSION=3.41.0', search_path(sdk_prefix)])
    targets = work / 'targets/result.json'
    run([PY, 'tests/reader_next_s15/check_existing_targets.py', '--sdk340', sdk340_prefix,
         '--sdk341', sdk_prefix, '--stage340', work / 'stage340', '--stage341', stage341,
         '--module', ROOT / 'apps/reader/original-export', '--output', targets], 'original-targets', 1800)
    exported = json.loads((evidence / 'result.json').read_text(encoding='utf-8'))
    required = json.loads((ROOT / 'tests/reader_next_s15/cases.json').read_text(encoding='utf-8'))
    assert exported['accepted'] is True and exported['failures'] == [], exported['failures']
    fault = 'windows_actual_locked_cleanup_failure' if os.name == 'nt' else 'posix_real_midstream_write_failure'
    checks = exported['checks']
    assert len(required) == 43 and set(required) <= set(checks), sorted(set(required) - set(checks))
    assert len(checks) == len(set(checks)) == 44, len(checks)
    assert set(checks) - set(required) == {fault}, sorted(set(checks) - set(required))
    frozen_report = json.loads((frozen / 'frozen.json').read_text(encoding='utf-8'))
    assert frozen_report['accepted'] is True and len(frozen_report['checks']) == 6, frozen_report
    target_report = json.loads(targets.read_text(encoding='utf-8'))
    assert target_report['accepted'] is True and len(target_report['cases']) == 16, target_report['cases']
    assert all(row['passed'] for row in target_report['cases'].values())
    publish('s15-export.json', evidence / 'result.json')
    publish('s15-graph.json', graph_report)
    publish('s15-frozen.json', frozen / 'frozen.json')
    publish('s15-targets.json', targets)
    return {'checks': len(checks), 'frozen_checks': len(frozen_report['checks']),
            'target_controls': len(target_report['cases']),
            'target_refusals': len([row for row in target_report['cases'].values() if row['refusal_expected']]),
            'sdk340': str(sdk340_prefix)}


def view():
    sdk_prefix, shared_prefix = sdk_stage(), shared_stage()
    default, raw = FAMILIES['default']['prefix'], FAMILIES['raw']['prefix']
    work = OUT / 's17'
    work.mkdir(parents=True, exist_ok=True)
    revisions = build(ROOT / 'tests/reader_revisions/consumer', 's17-revision-consumer', default,
                      [search_path(default, shared_prefix, sdk_prefix)], install=False)
    revision = program(revisions / ('revision-consumer' + EXE))
    legacy = build(ROOT / 'tests/reader_sync_status_view/consumer', 's17-status-view', default,
                   [search_path(default, shared_prefix, sdk_prefix)], install=False)
    legacy_report = work / 'frozen-legacy-acceptance'
    run([PY, 'tests/reader_sync_status_view/check_status_view.py',
         '--consumer', program(legacy / ('status-view-consumer' + EXE)),
         '--c-consumer', program(legacy / ('status-view-c-consumer' + EXE)),
         '--revision-consumer', revision, '--output', legacy_report], 'view-frozen-legacy', 2400)
    raw_consumer = build(ROOT / 'tests/reader_next_s17/consumer', 's17-raw-consumers', raw,
                         [search_path(raw, shared_prefix, sdk_prefix)], install=False)
    raw_report = work / 'raw-acceptance'
    run([PY, 'tests/reader_next_s17/check_raw_view.py',
         '--consumer', program(raw_consumer / ('raw-view-consumer' + EXE)),
         '--c-consumer', program(raw_consumer / ('raw-view-c-consumer' + EXE)),
         '--revision-consumer', program(raw_consumer / ('raw-revision' + EXE)),
         '--output', raw_report], 'view-raw', 2400)
    frozen = json.loads((legacy_report / 'result.json').read_text(encoding='utf-8'))
    explicit = json.loads((raw_report / 'result.json').read_text(encoding='utf-8'))
    assert frozen['accepted'] is True and frozen['count'] == len(frozen['checks']) == 22, frozen['count']
    assert frozen['host_ui_accepted'] is False and frozen['product_wiring_accepted'] is False
    assert explicit['accepted'] is True and explicit['count'] == len(explicit['checks']) == 20, explicit['count']
    assert explicit['family'] == 'raw' and explicit['adopted'] is False and explicit['actual_hosts'] is False
    assert explicit['profile'] == {'view': '0.2.0', 'session': '0.2.0', 'sync': '0.2.0',
                                   'revisions': '0.4.0', 'raw': 1}, explicit['profile']
    assert len(explicit['mirrored_fields']) == 16
    mixed = []
    for name, enabled, prefix in (('raw-view-rejects-legacy-session', True, default),
                                  ('legacy-view-rejects-raw-session', False, raw)):
        process = run(['cmake', '-S', str(ROOT / 'apps/reader/sync-status-view'),
                       '-B', str(BUILD / ('s17-' + name)), '-G', 'Ninja',
                       '-DEXR_READER_SELECTOR_BYTES_CANDIDATE=' + ('ON' if enabled else 'OFF'),
                       search_path(prefix, shared_prefix, sdk_prefix)], 'view-' + name, 900, check=False)
        assert process.returncode != 0 and 'EXReaderSession' in process.stdout, (name, process.stdout[-3000:])
        mixed.append(name)

    def package_request(package, version, location):
        return ('find_package(' + package + ' ' + version + ' EXACT CONFIG REQUIRED'
                + ' PATHS "' + (Path(location) / 'lib/cmake' / package).as_posix() + '" NO_DEFAULT_PATH)\n')

    def configure(name, body, target_prefix, expected):
        source = work / 'mixed' / name
        source.mkdir(parents=True, exist_ok=False)
        (source / 'CMakeLists.txt').write_text(
            'cmake_minimum_required(VERSION 3.24)\nproject(Wave3S17Mix LANGUAGES C CXX)\n'
            'if(MSVC)\n  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")\nendif()\n'
            + body, encoding='utf-8')
        (source / 'main.c').write_text('int main(void){return 0;}\n', encoding='utf-8')
        process = run(['cmake', '-S', str(source), '-B', str(BUILD / ('s17-' + name)), '-G', 'Ninja',
                       '-DCMAKE_BUILD_TYPE=Release', search_path(*target_prefix)], 'view-' + name, 900,
                      check=False)
        assert process.returncode != 0 and expected in process.stdout, (name, process.returncode,
                                                                       process.stdout[-3000:])
        mixed.append(name)

    configure('installed-legacy-view-refuses-raw', package_request('EXReaderSyncView', '0.1.0', raw),
              (raw, shared_prefix, sdk_prefix), 'EXReaderSyncView')
    configure('installed-raw-view-refuses-legacy', package_request('EXReaderSyncView', '0.2.0', raw),
              (default, shared_prefix, sdk_prefix), 'EXReaderSession')
    source = work / 'mixed/imported-legacy-target-refused'
    source.mkdir(parents=True, exist_ok=False)
    body = ('cmake_minimum_required(VERSION 3.24)\nproject(Wave3S17ImportedMix LANGUAGES C CXX)\n'
            'set(EXReaderProductCatalog_DIR "' + (shared_prefix / 'lib/cmake/EXReaderProductCatalog').as_posix()
            + '" CACHE PATH "" FORCE)\n'
            'set(EXReaderWebDAV_DIR "' + (shared_prefix / 'lib/cmake/EXReaderWebDAV').as_posix()
            + '" CACHE PATH "" FORCE)\n')
    for package in ('EXReaderRevisions', 'EXReaderSync', 'EXReaderSession'):
        body += 'set(' + package + '_DIR "' + (default / 'lib/cmake' / package).as_posix() + '" CACHE PATH "" FORCE)\n'
    body += 'find_package(EXReaderSession 0.1.0 EXACT CONFIG REQUIRED)\n'
    for package in ('EXReaderRevisions', 'EXReaderSync', 'EXReaderSession'):
        body += 'set(' + package + '_DIR "' + (raw / 'lib/cmake' / package).as_posix() + '" CACHE PATH "" FORCE)\n'
    body += package_request('EXReaderSyncView', '0.2.0', raw) + 'add_executable(version main.c)\n'
    (source / 'CMakeLists.txt').write_text(body, encoding='utf-8')
    (source / 'main.c').write_text('int main(void){return 0;}\n', encoding='utf-8')
    process = run(['cmake', '-S', str(source), '-B', str(BUILD / 's17-imported-legacy-target-refused'),
                   '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release', search_path(raw, shared_prefix, sdk_prefix)],
                  'view-imported-legacy-target-refused', 900, check=False)
    assert process.returncode != 0 and 'legacy capability family' in process.stdout, process.stdout[-3000:]
    mixed.append('imported-legacy-target-refused')
    assert len(mixed) == 5, mixed
    publish('s17-frozen-legacy.json', legacy_report / 'result.json')
    publish('s17-raw.json', raw_report / 'result.json')
    return {'frozen_checks': frozen['count'], 'raw_checks': explicit['count'],
            'mixed_refusals': mixed, 'raw_profile': explicit['profile']}


def phase(name, function, requires=()):
    blocked = [item for item in requires if not RESULTS.get(item, {}).get('passed')]
    if blocked:
        RESULTS[name] = {'passed': False, 'skipped': True, 'reason': 'dependency failed: ' + ', '.join(blocked)}
        print('SKIP', name, RESULTS[name]['reason'], flush=True)
        return
    print('PHASE', name, flush=True)
    started = time.monotonic()
    try:
        value = function() or {}
        RESULTS[name] = dict(value, passed=True, skipped=False, seconds=round(time.monotonic() - started, 1))
        print('PHASE PASS', name, flush=True)
    except BaseException as error:
        RESULTS[name] = {'passed': False, 'skipped': False, 'seconds': round(time.monotonic() - started, 1),
                         'error': repr(error), 'traceback': traceback.format_exc()[-6000:]}
        print('PHASE FAIL', name, repr(error), flush=True)


def finalize(s16_only=False):
    binary_dir = RT / 'programs'
    binary_dir.mkdir(parents=True, exist_ok=True)
    programs = {}
    for number, (name, path) in enumerate(PROGRAMS.items()):
        destination = binary_dir / (str(number) + '-' + Path(name).name)
        shutil.copyfile(path, destination)
        programs[name] = {'member': destination.relative_to(RT).as_posix(), **identity(destination),
                          'origin': name}
    reports = {}
    for name, path in REPORTS.items():
        destination = EVIDENCE / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, destination)
        reports[name] = {'member': destination.relative_to(RT).as_posix(), **identity(destination)}
    result = {'source_sha': os.environ['GITHUB_SHA'], 'seed': SEED, 'run_id': os.environ['GITHUB_RUN_ID'],
              'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'platform': RUNNER,
              'runtime_accepted': all(RESULTS[name]['passed'] for name in RESULTS),
              'legacy_guards_executed': False, 'complete_product': False, 'adopted': False,
               'validation_scope': 's16-bindings-and-imported-paths' if s16_only else 'full-business-replay',
               'full_joint_runtime_accepted': False if s16_only else all(RESULTS[name]['passed'] for name in RESULTS),
              'scope': ('S16 original/raw/default business replay, exact bindings and imported paths'
                        if s16_only else 'wave3 joint default/raw shared install and unchanged original business replay'),
              'production_candidates': {'sdk': SDK_SOURCE, 'frozen_sdk': FROZEN_SDK, 'legacy_start': LEGACY_START},
              'pending_gates': ['product DSO and host adoption', 'delivery, PR, tag, Release and default branch'],
              'phases': RESULTS, 'reports': reports, 'programs': programs}
    result['files'] = {path.relative_to(RT).as_posix(): identity(path)
                       for path in sorted(RT.rglob('*')) if path.is_file() and path != RT / 'result.json'}
    (RT / 'result.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'runtime_accepted': result['runtime_accepted'],
                      'failed': [name for name in RESULTS if not RESULTS[name]['passed']],
                      'programs': len(programs), 'reports': sorted(reports)}, indent=1), flush=True)
    return result


def main():
    s16_only = sys.argv[1:] == ['--s16-only']
    assert s16_only or not sys.argv[1:], 'unknown runtime scope'
    phase('prepare', prepare)
    phase('sdk341', sdk, ('prepare',))
    if not s16_only:
        phase('sdk340', sdk340, ('prepare',))
    phase('shared', shared, ('prepare',))
    phase('families', families, ('shared', 'sdk341'))
    phase('graph', graph, ('families',))
    if not s16_only:
        phase('font', font, ('families', 'sdk341'))
        phase('annotation', annotation, ('families', 'sdk341'))
    phase('jump', jump, ('families', 'sdk341'))
    if not s16_only:
        phase('original', original, ('families', 'sdk340'))
        phase('view', view, ('families', 'sdk341'))
    result = finalize(s16_only)
    return 0 if result['runtime_accepted'] else 1


if __name__ == '__main__':
    sys.exit(main())
