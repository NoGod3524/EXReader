# SPDX-License-Identifier: MIT
"""Actions-only build and acceptance driver for S16 (jump-history raw3).

It builds the default and the explicit raw candidate families from installed
packages only, reruns the unchanged original jump-history suite on the default
install and on the fixed-start baseline, reruns it on the candidate install, runs
the new raw consumer, proves that no default symbol moved, and records every
mixed-install refusal. Nothing here runs on a developer machine.
"""
import difflib
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import io
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'build/reader-next-s16'
START = 'e67d87cbeabb2457e0852f681ef0b27b2c0da4d8'
SDK_SOURCE = 'edddc463c06ed5731195cdb8f06b2df6dff7699e'
FROZEN_SDK = '9854061be331fe603a1822d9b2b36ee357154927'
SCHEMA = 'f32bb8aa18ed3de286900f19ce4230fd93435dd0'
SDK_VERSION = '3.41.0'
PDF = ROOT / 'tests/fixtures/pdf-public-text.pdf'
PDF_SHA = '5627a430fa04cbe11d38eb2682e336ef21e147d445753ed46ed11a7d5e3167cc'
PDF_BYTES = 8845
FONT = ROOT / 'tests/fixtures/fonts/primary.ttf'
OWNED = ('apps/reader/jump-history/', 'tests/reader_next_s16/', '.github/workflows/reader-next-s16.yml',
         'docs/reader-next-s16/', 'HANDOFF-RESULT-S16.md')
SHARED = ('apps/reader/reading-state', 'apps/reader/revisions', 'apps/reader/store', 'apps/reader/sync',
          'apps/reader/commands', 'apps/reader/reading-commands', 'apps/reader/annotation-view')
SDK_PATHS = ('src', 'include', 'cmake', 'CMakeLists.txt', 'tests/fixtures', 'bindings',
             '.github/workflows/native.yml', '.github/workflows/reliability.yml')
SUFFIX = '.exe' if os.name == 'nt' else ''
ENV = dict(os.environ)
STABLE_NO_WRITE = ('revision_rows', 'outbox_rows', 'sdk_progress_records', 'sdk_notes', 'sdk_fixed_notes',
                   'sdk_epub_notes', 'databases_unchanged', 'control_write_changed')
CASE_FIELDS = ('id', 'book', 'mode', 'kind', 'outcome', 'stored_wire_bytes', 'accounted_bytes', 'book_key',
               'entity_kind', 'operation', 'anchor_version', 'start', 'end', 'exact_bytes', 'prefix_bytes',
               'suffix_bytes', 'part', 'part_path', 'page', 'page_id')


def log(message):
    print(message, flush=True)


def run(args, name=None, timeout=2700, check=True):
    args = [str(a) for a in args]
    command = ' '.join(args)
    log('RUN ' + command)
    result = subprocess.run(args, cwd=str(ROOT), env=ENV, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding='utf-8', errors='replace', timeout=timeout)
    if name:
        (OUT / 'logs').mkdir(parents=True, exist_ok=True)
        (OUT / 'logs' / (name + '.log')).write_text('$ ' + command + '\nexit=' + str(result.returncode) + '\n'
                                                    + result.stdout, encoding='utf-8')
    log(result.stdout[-8000:])
    if check and result.returncode:
        raise RuntimeError((command, result.returncode))
    return result


def must_fail(args, name, needle):
    result = run(args, name, check=False)
    output = result.stdout
    assert result.returncode != 0, name + ': the configure unexpectedly succeeded'
    assert needle in output, name + ': the refusal did not name ' + repr(needle) + '\n' + output[-4000:]
    return {'name': name, 'refusal': needle, 'accepted': False}


def archive(sha, name, *paths):
    target = OUT / name
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    raw = subprocess.run(['git', 'archive', sha, *paths], cwd=str(ROOT), capture_output=True, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(raw)) as tar:
        tar.extractall(target, filter='data')
    return target


def build(source, name, prefix, extra=(), install=True):
    target = OUT / 'build' / name
    run(['cmake', '-S', source, '-B', target, '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release',
         '-DCMAKE_INSTALL_PREFIX=' + str(prefix), *extra], name + '-configure')
    run(['cmake', '--build', target, '--parallel', '4'], name + '-build')
    if install:
        run(['cmake', '--install', target], name + '-install')
    return target


def module_family(source, name, enabled, product, sdk):
    prefix = OUT / 'families' / (name + '-stage')
    flag = '-DEXR_READER_SELECTOR_BYTES_CANDIDATE=' + ('ON' if enabled else 'OFF')
    build(source / 'apps/reader/revisions', name + '-revisions', prefix,
          [flag, '-DREADER_PRODUCT_PREFIX=' + str(product),
           '-DCMAKE_PREFIX_PATH=' + ';'.join(map(str, [prefix, product]))])
    build(source / 'apps/reader/reading-state', name + '-reading-state', prefix,
          [flag, '-DEXR_SDK_VERSION=' + SDK_VERSION, '-DEXR_SDK=' + str(sdk),
           '-DCMAKE_PREFIX_PATH=' + ';'.join(map(str, [prefix, product, sdk]))])
    build(source / 'apps/reader/jump-history', name + '-jump-history', prefix,
          [flag, '-DCMAKE_PREFIX_PATH=' + ';'.join(map(str, [prefix, product, sdk]))])
    return prefix


def installed_header(prefix):
    return Path(prefix) / 'include' / 'reader_jump_history.h'


def package_version(prefix, package):
    path = Path(prefix) / 'lib' / 'cmake' / package / (package + 'ConfigVersion.cmake')
    if not path.exists():
        return None
    for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
        line = line.strip()
        if line.startswith('set(PACKAGE_VERSION'):
            return line.split('"')[1]
    return None


def sha_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def case_projection(cases):
    return [{key: case.get(key) for key in CASE_FIELDS} for case in cases]


def stable_no_write(no_write):
    return {key: (no_write or {}).get(key) for key in STABLE_NO_WRITE}


def original_projection(summary):
    return {
        'originals': summary.get('originals'),
        'cases': case_projection(summary.get('cases', [])),
        'lifecycle': summary.get('lifecycle'),
        'checks': sorted([(c.get('name'), c.get('pass')) for c in summary.get('checks', [])]),
        'no_write': stable_no_write(summary.get('no_write')),
        'moves': summary.get('moves'),
        'cases_total': summary.get('cases_total'),
        'checks_total': summary.get('checks_total'),
        'books': summary.get('books'),
        'versions': {key: summary.get(key) for key in
                     ('jump_history_version', 'reading_state_version', 'revisions_version', 'sdk_version')},
    }


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only'
    problems = []
    OUT.mkdir(parents=True)
    (OUT / 'logs').mkdir(exist_ok=True)

    log('== source identity and ownership ==')
    head = run(['git', 'rev-parse', 'HEAD']).stdout.strip().splitlines()[-1]
    assert head == os.environ['GITHUB_SHA'], (head, os.environ['GITHUB_SHA'])
    run(['git', 'merge-base', '--is-ancestor', START, 'HEAD'])
    run(['git', 'cat-file', '-e', FROZEN_SDK + '^{commit}'])
    run(['git', 'diff', '--exit-code', SDK_SOURCE, 'HEAD', '--', *SDK_PATHS])
    run(['git', 'diff', '--exit-code', SCHEMA, 'HEAD', '--', 'apps/reader/store/001_catalog.sql'])
    run(['git', 'diff', '--exit-code', START, 'HEAD', '--', *SHARED])
    changed = [line for line in run(['git', 'diff', '--name-only', START, 'HEAD']).stdout.splitlines() if line.strip()]
    outside = [path for path in changed if not (path.startswith(OWNED) or path in OWNED)]
    assert not outside, ('files outside the S16 ownership list changed', outside)
    sdk_version = re.search(r'project\(EXReader VERSION ([0-9.]+)', (ROOT / 'CMakeLists.txt').read_text()).group(1)
    assert sdk_version == SDK_VERSION, sdk_version
    assert len(PDF.read_bytes()) == PDF_BYTES and sha_file(PDF) == PDF_SHA

    log('== product provider and the approved SDK ==')
    product = OUT / 'families/product-stage'
    build(ROOT / 'apps/reader/store/native', 'product', product)
    run(['cmake', '--preset', 'reading-library'], 'sdk-configure')
    run(['cmake', '--build', '--preset', 'reading-library'], 'sdk-build', timeout=3000)
    run(['cmake', '--install', 'build/reading-library'], 'sdk-install')
    sdk = ROOT / 'build/reading-library/stage'
    assert '3.41.0' in (sdk / 'include/exr/base.h').read_text(), 'the installed SDK is not 3.41.0'

    log('== default and explicit raw candidate families ==')
    off = module_family(ROOT, 'default', False, product, sdk)
    on = module_family(ROOT, 'raw', True, product, sdk)
    baseline_source = archive(START, 'source', 'apps/reader/jump-history')
    baseline = OUT / 'families/baseline-stage'
    build(baseline_source / 'apps/reader/jump-history', 'baseline-jump-history', baseline,
          ['-DCMAKE_PREFIX_PATH=' + ';'.join(map(str, [off, product, sdk]))])
    versions = {'default': {'jump_history': package_version(off, 'EXReaderJumpHistory'),
                            'reading_state': package_version(off, 'EXReaderReadingState'),
                            'revisions': package_version(off, 'EXReaderRevisions')},
                'raw': {'jump_history': package_version(on, 'EXReaderJumpHistory'),
                        'reading_state': package_version(on, 'EXReaderReadingState'),
                        'revisions': package_version(on, 'EXReaderRevisions')},
                'baseline': {'jump_history': package_version(baseline, 'EXReaderJumpHistory')}}
    assert versions['default'] == {'jump_history': '0.1.0', 'reading_state': '0.1.0', 'revisions': '0.3.0'}, versions
    assert versions['raw'] == {'jump_history': '0.2.0', 'reading_state': '0.2.0', 'revisions': '0.4.0'}, versions
    assert versions['baseline'] == {'jump_history': '0.1.0'}, versions

    log('== no raw symbol or header line moved into the default install ==')
    baseline_header = installed_header(baseline).read_text(encoding='utf-8')
    off_header = installed_header(off).read_text(encoding='utf-8')
    on_header = installed_header(on).read_text(encoding='utf-8')
    baseline_lines = baseline_header.splitlines(keepends=True)
    off_lines = off_header.splitlines(keepends=True)
    matcher = difflib.SequenceMatcher(a=baseline_lines, b=off_lines, autojunk=False)
    inserted = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            continue
        assert tag == 'insert', 'the default header changed a baseline line (' + tag + ')'
        inserted.append(''.join(off_lines[j1:j2]))
    added = ''.join(inserted)
    assert 'EXR_READER_SELECTOR_BYTES_CANDIDATE' in added, 'the inserted header region lacks the candidate guard'
    assert 'reader_jh_commit_fixed_v3' in added, 'the inserted header region lacks the raw entry point'
    assert len(added.splitlines()) <= 70, 'the default header grew by ' + str(len(added.splitlines())) + ' lines'
    # One installed header with one capability guard: the raw declarations exist
    # in both installs and only the package's compile definition exposes them.
    assert off_header == on_header, 'the two installs must ship the same guarded header'
    assert 'EXR_READER_SELECTOR_BYTES_CANDIDATE' in off_header, 'the installed header has no capability guard'
    for symbol in ('reader_jh_commit_fixed_v3', 'reader_jh_commit_wire_raw_v3'):
        assert symbol in on_header, 'the raw header lacks ' + symbol
    def exported_definitions(prefix):
        path = prefix / 'lib/cmake/EXReaderJumpHistory/EXReaderJumpHistoryTargets.cmake'
        return path.read_text(encoding='utf-8')
    assert 'EXR_READER_SELECTOR_BYTES_CANDIDATE=1' not in exported_definitions(off), \
        'the default package exports the raw capability'
    assert 'EXR_READER_SELECTOR_BYTES_CANDIDATE=1' in exported_definitions(on), \
        'the raw package does not export its capability'
    off_archives = [p for p in (off / 'lib').glob('*') if 'jump_history' in p.name]
    on_archives = [p for p in (on / 'lib').glob('*') if 'jump_history' in p.name]
    assert len(off_archives) == 1 and len(on_archives) == 1
    off_bytes = off_archives[0].read_bytes()
    on_bytes = on_archives[0].read_bytes()
    for symbol in (b'reader_jh_commit_fixed_v3', b'reader_jh_commit_wire_raw_v3', b'reader_rs_decode_raw_v3'):
        assert symbol not in off_bytes, 'the default archive carries ' + symbol.decode()
        assert symbol in on_bytes, 'the raw archive lacks ' + symbol.decode()

    log('== the unchanged original suite on the baseline, the default and the raw install ==')
    fixtures = OUT / 'fixtures'
    run([sys.executable, ROOT / 'tests/reader_jump_history/make_fixtures.py', fixtures], 'fixtures')
    evidence = OUT / 'evidence'

    def original_suite(prefix, name, consumer_source, extra_prefixes=()):
        consumer = build(consumer_source, name + '-consumer', prefix,
                         ['-DCMAKE_PREFIX_PATH=' + ';'.join(map(str, [prefix, *extra_prefixes, product, sdk]))],
                         install=False)
        arguments = [sys.executable, ROOT / 'tests/reader_jump_history/check_jump_history.py',
                     '--probe', consumer / ('jump-history-probe' + SUFFIX),
                     '--c-consumer', consumer / ('jump-history-c-consumer' + SUFFIX),
                     '--fixtures', str(fixtures), '--font', str(FONT), '--installed', str(prefix),
                     '--platform', os.environ.get('RUNNER_OS', 'unknown'),
                     '--output', str(evidence / name)]
        # The consumer CMakeLists is copied for the raw install only; the version
        # request is the single changed line and every assertion stays identical.
        return run(arguments, name + '-original-suite', timeout=900)

    original_consumer = OUT / 'consumers/unchanged-original'
    shutil.copytree(ROOT / 'tests/reader_jump_history/consumer', original_consumer)
    baseline_suite = original_suite(baseline, 'original-baseline', original_consumer, extra_prefixes=(off,))
    off_suite = original_suite(off, 'original-default', original_consumer)
    raw_consumer = OUT / 'consumers/raw-original'
    shutil.copytree(ROOT / 'tests/reader_jump_history/consumer', raw_consumer)
    consumer_text = (raw_consumer / 'CMakeLists.txt').read_text(encoding='utf-8')
    patched = consumer_text.replace('find_package(EXReaderJumpHistory 0.1.0 EXACT CONFIG REQUIRED)',
                                    'find_package(EXReaderJumpHistory 0.2.0 EXACT CONFIG REQUIRED)')
    differences = [pair for pair in zip(consumer_text.splitlines(), patched.splitlines()) if pair[0] != pair[1]]
    assert len(differences) == 1, ('the raw consumer copy must change exactly the package version line', differences)
    (raw_consumer / 'CMakeLists.txt').write_text(patched, encoding='utf-8')
    assert (raw_consumer / 'CMakeLists.txt').read_text(encoding='utf-8') == patched
    on_suite = original_suite(on, 'original-raw', raw_consumer)

    baseline_summary = json.loads((evidence / 'original-baseline/summary.json').read_text(encoding='utf-8'))
    off_summary = json.loads((evidence / 'original-default/summary.json').read_text(encoding='utf-8'))
    on_summary = json.loads((evidence / 'original-raw/summary.json').read_text(encoding='utf-8'))
    for name, summary in (('baseline', baseline_summary), ('default', off_summary), ('raw', on_summary)):
        assert summary['jump_history_module_accepted'] is True, (name, summary['problems'])
        assert summary['checks_failed'] == 0 and summary['checks_total'] >= 149, (name, summary['checks_total'])
        assert summary['host_wiring_accepted'] is False
    assert original_projection(baseline_summary) == original_projection(off_summary), \
        'the default install changed an original jump-history result'
    default_equivalence = True

    log('== the raw consumer on the explicit candidate install ==')
    raw_build = build(ROOT / 'tests/reader_next_s16/consumer', 'raw-consumer', on,
                      ['-DS16_RAW=ON', '-DCMAKE_PREFIX_PATH=' + ';'.join(map(str, [on, product, sdk]))],
                      install=False)
    run([sys.executable, ROOT / 'tests/reader_next_s16/check_raw.py', '--mode', 'raw',
         '--consumer', raw_build / ('s16-c-consumer' + SUFFIX), '--probe', raw_build / ('s16-raw-probe' + SUFFIX),
         '--fixtures', str(fixtures), '--font', str(FONT), '--pdf', str(PDF), '--pdf-sha', PDF_SHA,
         '--installed', str(on), '--platform', os.environ.get('RUNNER_OS', 'unknown'),
         '--output', str(evidence / 'raw')], 'raw-check', timeout=900)
    default_build = build(ROOT / 'tests/reader_next_s16/consumer', 'default-consumer', off,
                          ['-DS16_RAW=OFF', '-DCMAKE_PREFIX_PATH=' + ';'.join(map(str, [off, product, sdk]))],
                          install=False)
    run([sys.executable, ROOT / 'tests/reader_next_s16/check_raw.py', '--mode', 'default',
         '--consumer', default_build / ('s16-c-consumer' + SUFFIX), '--fixtures', str(fixtures),
         '--installed', str(off), '--platform', os.environ.get('RUNNER_OS', 'unknown'),
         '--output', str(evidence / 'default')], 'default-check', timeout=600)

    log('== mixed installs are refused ==')
    negatives = []
    negatives.append(must_fail(['cmake', '-S', str(ROOT / 'apps/reader/jump-history'),
                                '-B', str(OUT / 'negatives/raw-against-default'), '-G', 'Ninja',
                                '-DCMAKE_BUILD_TYPE=Release', '-DEXR_READER_SELECTOR_BYTES_CANDIDATE=ON',
                                '-DCMAKE_PREFIX_PATH=' + ';'.join(map(str, [off, product, sdk]))],
                               'negative-raw-against-default', 'requested version "0.2.0"'))
    negatives.append(must_fail(['cmake', '-S', str(ROOT / 'apps/reader/jump-history'),
                                '-B', str(OUT / 'negatives/default-against-raw'), '-G', 'Ninja',
                                '-DCMAKE_BUILD_TYPE=Release', '-DEXR_READER_SELECTOR_BYTES_CANDIDATE=OFF',
                                '-DCMAKE_PREFIX_PATH=' + ';'.join(map(str, [on, product, sdk]))],
                               'negative-default-against-raw', 'requested version "0.1.0"'))
    negatives.append(must_fail(['cmake', '-S', str(original_consumer),
                                '-B', str(OUT / 'negatives/original-consumer-against-raw'), '-G', 'Ninja',
                                '-DCMAKE_BUILD_TYPE=Release',
                                '-DCMAKE_PREFIX_PATH=' + ';'.join(map(str, [on, product, sdk]))],
                               'negative-original-consumer-against-raw', 'EXReaderJumpHistory'))
    fake_prefix = OUT / 'negatives/faked-prefix'
    fake = fake_prefix / 'lib/cmake/EXReaderReadingState'
    fake.parent.mkdir(parents=True)
    shutil.copytree(off / 'lib/cmake/EXReaderReadingState', fake)
    version_file = fake / 'EXReaderReadingStateConfigVersion.cmake'
    text = version_file.read_text(encoding='utf-8')
    assert 'set(PACKAGE_VERSION "0.1.0")' in text
    version_file.write_text(text.replace('set(PACKAGE_VERSION "0.1.0")', 'set(PACKAGE_VERSION "0.2.0")'),
                            encoding='utf-8')
    negatives.append(must_fail(['cmake', '-S', str(ROOT / 'apps/reader/jump-history'),
                                '-B', str(OUT / 'negatives/faked-family-target'), '-G', 'Ninja',
                                '-DCMAKE_BUILD_TYPE=Release', '-DEXR_READER_SELECTOR_BYTES_CANDIDATE=ON',
                                '-DCMAKE_PREFIX_PATH=' + ';'.join(map(str, [fake_prefix, off, product, sdk]))],
                               'negative-faked-family-target',
                               'Raw candidate jump history requires the raw candidate reading-state target'))

    log('== result ==')
    raw_summary = json.loads((evidence / 'raw/summary.json').read_text(encoding='utf-8'))
    default_summary = json.loads((evidence / 'default/summary.json').read_text(encoding='utf-8'))
    programs = {}
    for name, path in (('raw_probe', raw_build / ('s16-raw-probe' + SUFFIX)),
                       ('raw_c_consumer', raw_build / ('s16-c-consumer' + SUFFIX)),
                       ('default_c_consumer', default_build / ('s16-c-consumer' + SUFFIX)),
                       ('original_probe', OUT / 'build' / 'original-default-consumer' / ('jump-history-probe' + SUFFIX)),
                       ('original_c_consumer', OUT / 'build' / 'original-default-consumer' / ('jump-history-c-consumer' + SUFFIX))):
        programs[name] = {'sha256': sha_file(path), 'bytes': Path(path).stat().st_size}
    result = {
        'accepted': not problems and raw_summary['accepted'] and default_summary['accepted'],
        'source_sha': os.environ['GITHUB_SHA'],
        'run_id': os.environ['GITHUB_RUN_ID'],
        'run_attempt': os.environ['GITHUB_RUN_ATTEMPT'],
        'platform': os.environ.get('RUNNER_OS', 'unknown'),
        'start_sha': START,
        'sdk_source_sha': SDK_SOURCE,
        'frozen_sdk_sha': FROZEN_SDK,
        'product_schema_sha': SCHEMA,
        'owned_paths': list(OWNED),
        'changed_paths': changed,
        'versions': versions,
        'installed': {
            'default': {'header_sha256': sha_file(installed_header(off)),
                        'library_sha256': sha_file(off_archives[0])},
            'raw': {'header_sha256': sha_file(installed_header(on)),
                    'library_sha256': sha_file(on_archives[0])},
            'baseline': {'header_sha256': sha_file(installed_header(baseline))},
        },
        'original_suite': {
            'default': {'checks_total': off_summary['checks_total'], 'cases_total': off_summary['cases_total'],
                        'moves': off_summary['moves'], 'accepted': off_summary['jump_history_module_accepted']},
            'raw': {'checks_total': on_summary['checks_total'], 'cases_total': on_summary['cases_total'],
                    'moves': on_summary['moves'], 'accepted': on_summary['jump_history_module_accepted']},
            'baseline': {'checks_total': baseline_summary['checks_total'],
                         'accepted': baseline_summary['jump_history_module_accepted']},
            'default_equals_baseline': default_equivalence,
        },
        'raw_suite': {'checks_total': raw_summary['checks_total'], 'cases_total': raw_summary['cases_total'],
                      'moves': raw_summary['moves'], 'accepted': raw_summary['accepted'],
                      'cases': raw_summary['cases'], 'lifecycle': raw_summary['lifecycle'],
                      'no_write': raw_summary['no_write'], 'raw_semantics': raw_summary['raw_semantics'],
                      'versions': raw_summary['versions'], 'originals': raw_summary['originals'],
                      'pdf_sha256': raw_summary['pdf_sha256']},
        'default_raw_suite': {'checks_total': default_summary['checks_total'], 'accepted': default_summary['accepted']},
        'header_pure_insertions': True,
        'inserted_header_lines': len(added.splitlines()),
        'default_install_has_no_raw_symbol': True,
        'mixed_install_negatives': negatives,
        'programs': programs,
        'host_wiring_accepted': False,
        'gui_accepted': False,
        'adopted': False,
        'scope': 'reader jump-history module only; the raw candidate is an explicit module capability, '
                 'not an accepted SDK, product default or host feature',
        'problems': problems + raw_summary['problems'] + default_summary['problems'],
    }
    (OUT / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: result[key] for key in ('accepted', 'platform', 'versions', 'original_suite',
                                                   'inserted_header_lines', 'problems')}, indent=1))
    return 0 if result['accepted'] else 1


if __name__ == '__main__':
    sys.exit(main())
