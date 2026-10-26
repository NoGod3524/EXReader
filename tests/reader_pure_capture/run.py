"""Actions-only installed pure-capture candidate business and compatibility run."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import traceback

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'build/reader-pure-capture'
BUILD = ROOT / 'build/reader-pure-capture-build'
STAGE = ROOT / 'build/reader-pure-capture-stages'
FETCH = ROOT / 'build/pc-fc'
BASE = 'c05a4c2c1782872c943b4179c55529bb343b3fbe'
CANDIDATE = 'a911cd0e8405a362dae1bb489190de02c4c81d51'
PUBLIC = 'apps/reader/reading-state/include/reader_reading_state.h'
HEADER = 'reader_reading_state_capture_raw_candidate.h'
SYMBOL = b'reader_rs_encode_capture_raw_candidate'
CHANGED = {'apps/reader/reading-state/CMakeLists.txt',
           'apps/reader/reading-state/include/' + HEADER,
           'apps/reader/reading-state/src/reading_state.cpp'}
EXE = '.exe' if os.name == 'nt' else ''
RESULT = {'accepted': False, 'scope': 'installed public pure raw capture candidate only',
          'full_product_accepted': False, 'host_ui_accepted': False, 'device_tested': False,
          'base': BASE, 'candidate': CANDIDATE, 'consumers': [], 'programs': {}, 'checks': [],
          'negative_controls': [],
          'installs': {}, 'failures': []}


def identity(path):
    data = Path(path).read_bytes()
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def run(args, name, check=True, timeout=2400):
    args = list(map(str, args))
    print('RUN', name, flush=True)
    log = OUT / 'logs' / (name + '.log')
    log.parent.mkdir(parents=True, exist_ok=True)
    try:
        process = subprocess.run(args, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 text=True, encoding='utf-8', errors='replace', timeout=timeout)
    except subprocess.TimeoutExpired as error:
        output = error.stdout or b''
        if isinstance(output, bytes):
            output = output.decode('utf-8', errors='replace')
        log.write_text('$ ' + ' '.join(args) + '\nTIMEOUT\n' + output, encoding='utf-8')
        raise
    log.write_text('$ ' + ' '.join(args) + '\nexit=' + str(process.returncode) + '\n' + process.stdout,
                   encoding='utf-8')
    print(process.stdout[-3000:], flush=True)
    if check and process.returncode:
        raise RuntimeError((name, process.returncode, process.stdout[-3000:]))
    return process


def build(source, label, prefix, flags=(), install=True):
    directory = BUILD / label
    run(['cmake', '-S', source, '-B', directory, '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release',
         '-DCMAKE_INSTALL_PREFIX=' + str(prefix), '-DFETCHCONTENT_BASE_DIR=' + str(FETCH), *flags],
        label + '-configure')
    run(['cmake', '--build', directory, '--parallel', '4'], label + '-build')
    if install:
        run(['cmake', '--install', directory], label + '-install')
    return directory


def paths(*prefixes):
    return '-DCMAKE_PREFIX_PATH=' + ';'.join(map(str, prefixes))


def package_version(prefix, package):
    path = prefix / 'lib/cmake' / package / (package + 'ConfigVersion.cmake')
    for line in path.read_text(encoding='utf-8').splitlines():
        if line.strip().startswith('set(PACKAGE_VERSION '):
            return line.split('"')[1]
    raise ValueError(('missing installed version', path))


def retain(path, member):
    destination = OUT / member
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(path, destination)
    return {'member': destination.relative_to(OUT).as_posix(), **identity(destination)}


def installed_state(mode, prefix, baseline):
    assert package_version(prefix, 'EXReaderReadingState') == ('0.1.0' if mode == 'default' else '0.2.0')
    old_header = prefix / 'include/reader_reading_state.h'
    assert old_header.read_bytes() == baseline, 'old public header bytes changed: ' + mode
    new_header = prefix / 'include' / HEADER
    assert new_header.exists() == (mode == 'on'), 'candidate header installation: ' + mode
    libraries = sorted(path for path in (prefix / 'lib').glob('*')
                       if path.is_file() and 'reader_reading_state' in path.name)
    assert len(libraries) == 2, ('codec and resolver library set', mode, libraries)
    assert any(SYMBOL in path.read_bytes() for path in libraries) == (mode == 'on'), \
        'pure symbol capability: ' + mode
    targets = prefix / 'lib/cmake/EXReaderReadingState/EXReaderReadingStateTargets.cmake'
    assert ('EXR_READER_PURE_CAPTURE_CANDIDATE=1' in targets.read_text(encoding='utf-8')) == (mode == 'on'), \
        'pure exported compile definition: ' + mode
    records = {path.name: retain(path, 'installed/' + mode + '/lib/' + path.name) for path in libraries}
    records['public_header'] = retain(old_header, 'installed/' + mode + '/include/' + old_header.name)
    records['targets'] = retain(targets, 'installed/' + mode + '/' + targets.name)
    if mode == 'on':
        assert new_header.read_bytes() == (ROOT / 'apps/reader/reading-state/include' / HEADER).read_bytes()
        records['candidate_header'] = retain(new_header, 'installed/on/include/' + HEADER)
    return records


def consumer(mode, prefix, revisions, catalog, sdk):
    directory = build(ROOT / 'tests/reader_pure_capture/consumer', 'consumer-' + mode, OUT / 'unused',
                      [paths(prefix, revisions, catalog, sdk), '-DPURE_CAPTURE_MODE=' + mode], install=False)
    for language, target in (('c', 'pure-capture-c'), ('cpp', 'pure-capture-cpp')):
        binary = directory / (target + EXE)
        data = binary.read_bytes()
        magic = data[:4]
        assert (data.startswith(b'MZ') if os.name == 'nt' else
                magic in {b'\x7fELF', b'\xfe\xed\xfa\xcf', b'\xcf\xfa\xed\xfe',
                          b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca'}), ('native program', binary)
        program = retain(binary, 'programs/' + mode + '-' + target + EXE)
        RESULT['programs'][mode + '-' + language] = program
        work = OUT / 'work' / mode / language
        work.mkdir(parents=True, exist_ok=False)
        report_path = OUT / 'reports' / (mode + '-' + language + '.json')
        report_path.parent.mkdir(parents=True, exist_ok=True)
        run([binary, OUT / 'fixtures', work, report_path, ROOT / 'tests/fixtures/fonts/primary.ttf'],
            'consumer-' + mode + '-' + language, timeout=600)
        report = json.loads(report_path.read_text(encoding='utf-8'))
        checks = report.get('checks', [])
        names = [row['name'] for row in checks]
        assert report.get('accepted') is True and report.get('language') == language, report
        assert report.get('count') == len(names) > 0 and len(names) == len(set(names)), report
        assert all(row.get('pass') is True for row in checks), report
        RESULT['checks'].extend({'name': mode + '/' + language + ': ' + row['name'], 'pass': True}
                                for row in checks)
        RESULT['consumers'].append({'mode': mode, 'language': language, 'checks': names,
                                    'report': {'member': report_path.relative_to(OUT).as_posix(),
                                               **identity(report_path)},
                                    'program': program})


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only'
    OUT.mkdir(parents=True, exist_ok=True)
    RESULT.update({key: os.environ[value] for key, value in (
        ('source_sha', 'GITHUB_SHA'), ('run_id', 'GITHUB_RUN_ID'),
        ('attempt', 'GITHUB_RUN_ATTEMPT'), ('platform', 'RUNNER_OS'))})
    RESULT['capability_source'] = os.environ['PURE_CAPTURE_SOURCE']
    assert not STAGE.exists() and not BUILD.exists(), 'fresh independent build/stage roots required'
    assert git('rev-parse', 'HEAD').decode().strip() == RESULT['source_sha']
    assert os.environ['PURE_CAPTURE_SOURCE'] == CANDIDATE
    assert git('rev-list', '--parents', '-1', CANDIDATE).decode().strip().split() == [CANDIDATE, BASE]
    assert set(git('diff', '--name-only', BASE, CANDIDATE).decode().splitlines()) == CHANGED
    run(['git', 'merge-base', '--is-ancestor', CANDIDATE, 'HEAD'], 'candidate-ancestor')
    run(['git', 'diff', '--exit-code', CANDIDATE, 'HEAD', '--', *sorted(CHANGED)], 'candidate-source-binding')
    run(['git', 'diff', '--exit-code', BASE, 'HEAD', '--', 'src', 'include', 'cmake',
         'CMakeLists.txt', 'CMakePresets.json', 'bindings', 'apps/reader/revisions', 'apps/reader/store'],
        'unchanged-sdk-catalog-revisions')
    baseline = git('show', BASE + ':' + PUBLIC)
    assert (ROOT / PUBLIC).read_bytes() == baseline, 'source public header differs from base'
    (OUT / 'baseline-public-header.h').write_bytes(baseline)
    RESULT['public_header_baseline'] = identity(OUT / 'baseline-public-header.h')
    run(['cmake', '--preset', 'reading-library'], 'sdk-configure')
    run(['cmake', '--build', '--preset', 'reading-library', '--parallel', '4'], 'sdk-build', timeout=5400)
    run(['cmake', '--install', 'build/reading-library'], 'sdk-install')
    sdk = ROOT / 'build/reading-library/stage'
    catalog = STAGE / 'catalog'
    build(ROOT / 'apps/reader/store/native', 'catalog', catalog)
    default = STAGE / 'default'
    raw_revisions = STAGE / 'raw-revisions'
    for label, prefix, raw in (('default', default, False), ('raw', raw_revisions, True)):
        build(ROOT / 'apps/reader/revisions', label + '-revisions', prefix,
              ['-DREADER_PRODUCT_PREFIX=' + str(catalog), paths(prefix, catalog),
               '-DEXR_READER_SELECTOR_BYTES_CANDIDATE=' + ('ON' if raw else 'OFF')])
        assert package_version(prefix, 'EXReaderRevisions') == ('0.4.0' if raw else '0.3.0')
    run([sys.executable, 'tests/reader_reading_state/make_fixtures.py', OUT / 'fixtures'], 'fixtures')
    for mode in ('default', 'off', 'on'):
        prefix = default if mode == 'default' else STAGE / mode
        revisions = default if mode == 'default' else raw_revisions
        build(ROOT / 'apps/reader/reading-state', mode + '-reading-state', prefix,
              [paths(prefix, revisions, catalog, sdk), '-DEXR_SDK=' + str(sdk), '-DEXR_SDK_VERSION=3.41.0',
               '-DEXR_READER_SELECTOR_BYTES_CANDIDATE=' + ('OFF' if mode == 'default' else 'ON'),
               '-DEXR_READER_PURE_CAPTURE_CANDIDATE=' + ('ON' if mode == 'on' else 'OFF')])
        RESULT['installs'][mode] = installed_state(mode, prefix, baseline)
        RESULT['checks'].extend({'name': mode + ': ' + name, 'pass': True} for name in (
            'old public header byte-identical to base', 'candidate header capability installation',
            'actual archive pure symbol capability', 'exported pure compile definition capability'))
        consumer(mode, prefix, revisions, catalog, sdk)
    for mode in ('zero', 'undefined', 'raw-zero', 'raw-undefined'):
        directory = BUILD / ('header-' + mode)
        run(['cmake', '-S', ROOT / 'tests/reader_pure_capture/consumer', '-B', directory,
             '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release', '-DPURE_CAPTURE_MODE=on',
             '-DPURE_HEADER_MODE=' + mode,
             paths(STAGE / 'on', raw_revisions, catalog, sdk)], 'header-' + mode + '-configure')
        result = run(['cmake', '--build', directory, '--target', 'pure-header-probe'],
                     'header-' + mode + '-refusal', check=False, timeout=600)
        assert result.returncode != 0 and 'Use the explicitly installed pure raw capture candidate target' in result.stdout, \
            ('wrong macro did not refuse at the candidate header', mode, result.stdout[-2000:])
        RESULT['negative_controls'].append({'mode': mode, 'refused': True,
                                            'log': 'logs/header-' + mode + '-refusal.log'})
        RESULT['checks'].append({'name': 'wrong macro ' + mode + ' refused by candidate header', 'pass': True})
    assert len(RESULT['consumers']) == 6 and len(RESULT['negative_controls']) == 4
    RESULT['accepted'] = True


if __name__ == '__main__':
    try:
        main()
    except BaseException as error:
        RESULT['failures'].append({'error': repr(error), 'traceback': traceback.format_exc()})
    finally:
        if os.environ.get('GITHUB_ACTIONS') == 'true':
            OUT.mkdir(parents=True, exist_ok=True)
            RESULT['files'] = {path.relative_to(OUT).as_posix(): identity(path)
                               for path in sorted(OUT.rglob('*')) if path.is_file() and path != OUT / 'report.json'}
            (OUT / 'report.json').write_text(json.dumps(RESULT, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(RESULT, indent=1), flush=True)
    sys.exit(0 if RESULT['accepted'] else 1)
