"""Actions-only shared-install entry; original business judges remain unchanged."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'build/reader-production-foundation/runtime'
EXE = '.exe' if os.name == 'nt' else ''
PY = sys.executable
PROGRAMS = {}


def run(args, label, timeout=2400, okay=True):
    args = list(map(str, args))
    print('RUN', label, flush=True)
    p = subprocess.run(args, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       text=True, encoding='utf-8', errors='replace', timeout=timeout)
    (OUT / 'logs').mkdir(parents=True, exist_ok=True)
    (OUT / 'logs' / (label + '.log')).write_text(' '.join(args) + '\n' + p.stdout, encoding='utf-8')
    print(p.stdout[-5000:], flush=True)
    if okay:
        assert p.returncode == 0, (label, p.returncode)
    return p


def build(source, label, prefix, extra=(), install=True, target=None):
    # FetchContent's SQLite stamp names exceed Windows MAX_PATH under OUT.
    target = target or ROOT / 'build/pfb' / label
    run(['cmake', '-S', source, '-B', target, '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release',
         '-DCMAKE_INSTALL_PREFIX=' + str(prefix), *extra], label + '-configure')
    run(['cmake', '--build', target, '--parallel', '4'], label + '-build')
    if install:
        run(['cmake', '--install', target], label + '-install')
    return target


def exe(build_dir, name):
    path = build_dir / (name + EXE)
    assert path.is_file(), path
    PROGRAMS[str(path.relative_to(ROOT))] = path
    return path


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only'
    from guard import inspect
    source = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    assert source == os.environ['GITHUB_SHA'] and not inspect(source)
    OUT.mkdir(parents=True, exist_ok=True)
    result = {'source_sha': source, 'run_id': os.environ['GITHUB_RUN_ID'],
              'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'platform': os.environ['RUNNER_OS'],
              'runtime_accepted': False, 'legacy_guards_executed': False,
              'complete_product': False, 'foundation_accepted': False,
              'scope': 'shared-install original business replay only',
              'pending_gates': ['full original root artifact-mutation refusal suites',
                                'cross-family already-imported target refusal suites',
                                'product DSO and host adoption'],
              'reports': {}, 'programs': {}}
    try:
        run(['cmake', '--preset', 'reading-library'], 'sdk-configure')
        run(['cmake', '--build', '--preset', 'reading-library'], 'sdk-build', 3600)
        run(['cmake', '--install', 'build/reading-library'], 'sdk-install')
        sdk = ROOT / 'build/reading-library/stage'
        shared = OUT / 'shared-stage'
        for module, path in [('product', 'apps/reader/store/native'), ('dav', 'extras/webdav'),
                             ('sideload', 'extras/sideload')]:
            build(ROOT / path, module, shared, ['-DEXR_SDK=' + str(sdk)])
        prefixes = {'default': ROOT / 'build/s14-stage', 'raw': OUT / 'raw-stage'}
        consumers = {}
        for family, prefix in prefixes.items():
            raw = family == 'raw'
            search = '-DCMAKE_PREFIX_PATH=' + ';'.join(map(str, [prefix, shared, sdk]))
            flags = [search, '-DEXR_SDK=' + str(sdk), '-DEXR_SDK_VERSION=3.41.0',
                     '-DREADER_PRODUCT_PREFIX=' + str(shared),
                     '-DEXR_READER_SELECTOR_BYTES_CANDIDATE=' + ('ON' if raw else 'OFF')]
            for module in ['revisions', 'reading-state', 'commands', 'sync', 'session',
                           'annotation-export', 'annotation-import', 'font-library',
                           'original-export', 'jump-history', 'sync-status-view']:
                build(ROOT / 'apps/reader' / module, family + '-' + module, prefix,
                      [*flags, '-DREADER_ANNOTATION_IMPORT_BUILD=ON', '-DREADER_FONT_LIBRARY_BUILD=ON'])
            # One real consumer imports all five packages into the same CMake graph.
            graph = build(ROOT / 'tests/reader_production_foundation/consumer', family + '-graph', prefix,
                          [*flags, '-DFAMILY_VERSION=' + ('0.2.0' if raw else '0.1.0'),
                           '-DFAMILY_PREFIX=' + str(prefix), '-DSHARED_PREFIX=' + str(shared),
                           '-DSDK_PREFIX=' + str(sdk)], False)
            run([exe(graph, 'foundation-consumer')], family + '-graph-run')
            consumers[family] = {}
            for key, directory, options in [
                ('annotation', 'reader_next_c06', ['-DC06_RAW=' + ('ON' if raw else 'OFF')]),
                ('jump', 'reader_next_s16', ['-DS16_RAW=' + ('ON' if raw else 'OFF')]),
                ('view', 'reader_next_s17' if raw else 'reader_sync_status_view', [])]:
                consumers[family][key] = build(ROOT / 'tests' / directory / 'consumer', family + '-' + key + '-consumer',
                                                  prefix, [search, *options], False)
        default, raw = prefixes['default'], prefixes['raw']
        search = '-DCMAKE_PREFIX_PATH=' + ';'.join(map(str, [default, shared, sdk]))
        # Exact original S14 driver expects these declared build/install paths.
        font = build(ROOT / 'tests/reader_next_s14/consumer', 'font-consumer', default,
                     [search], False, ROOT / 'build/s14-consumer')
        exe(font, 'font-probe'); exe(font, 'font-c')
        run(['cmake', '-S', 'apps/reader/font-library', '-B', 'build/s14-default-off', '-G', 'Ninja'], 'font-default-off')
        os.environ.update(S14_SDK_STAGE=str(sdk), S14_SDK_VERSION='3.41.0')
        run([PY, 'tests/reader_next_s14/run.py'], 'font-full', 1800)
        result['reports']['font'] = 'build/s14-evidence/result.json'
        original = build(ROOT / 'tests/reader_next_s15/consumer', 'original-consumer', default, [search], False)
        graph_report = OUT / 'original-evidence/graph.json'
        run([PY, 'tests/reader_next_s15/check_install_graph.py', '--module-src', 'apps/reader/original-export',
             '--stage', default, '--sdk', sdk, '--work', OUT / 'graph-work',
             '--consumer', ROOT / 'tests/reader_next_s15/consumer', '--output', graph_report], 'original-graph', 1800)
        fixtures = OUT / 'original-fixtures'
        run([PY, 'tests/reader_next_s15/make_fixtures.py', fixtures], 'original-fixtures')
        library = default / 'lib' / ('reader_original_export.lib' if os.name == 'nt' else 'libreader_original_export.a')
        run([PY, 'tests/reader_next_s15/check_export.py', exe(original, 'original-export-probe'),
             exe(original, 'original-export-c-consumer'), fixtures, graph_report.parent, library, sdk, graph_report], 'original-full', 1800)
        result['reports']['original'] = str((graph_report.parent / 'result.json').relative_to(ROOT))
        # C06 exposes pure business phases separately from its old branch guard.
        c06 = load('foundation_c06', 'tests/reader_next_c06/run.py')
        c06.OUT = OUT / 'annotation-evidence'
        c06.OUT.mkdir()
        # Business source invariants from C06.guards(), independent of its old
        # single-package branch/ownership precondition.
        fixed_import = subprocess.check_output(['git', 'show', c06.IMPORT_SOURCE + ':apps/reader/annotation-import/src/annotation_import.cpp'], cwd=ROOT)
        assert (ROOT / 'apps/reader/annotation-import/src/annotation_import.cpp').read_bytes().startswith(fixed_import)
        fixed_header = subprocess.check_output(['git', 'show', c06.IMPORT_SOURCE + ':apps/reader/annotation-import/include/reader_annotation_import.h'], cwd=ROOT)
        assert (ROOT / 'apps/reader/annotation-import/include/reader_annotation_import.h').read_bytes() == fixed_header
        thumbnail = subprocess.check_output(['git', 'show', c06.START + ':apps/reader/thumbnails/src/thumbnails.cpp'], cwd=ROOT)
        copied_sha = (ROOT / 'apps/reader/annotation-import/src/portable_sha256.h').read_bytes()
        def sha_struct(data):
            return data.split(b'struct Sha256 {', 1)[1].split(b'\n};', 1)[0]
        assert sha_struct(thumbnail) == sha_struct(copied_sha)
        run(['git', 'diff', '--exit-code', c06.START, 'HEAD', '--',
             'apps/reader/annotation-export/include/reader_annotation_export.h'], 'annotation-legacy-header')
        old_export = c06.archive(c06.START, 'baseline-export', 'apps/reader/annotation-export')
        old_import = c06.archive(c06.IMPORT_SOURCE, 'baseline-import', 'apps/reader/annotation-import')
        old_prefix = c06.modules('baseline', False, default, shared, sdk,
                                 old_export / 'apps/reader/annotation-export', old_import / 'apps/reader/annotation-import')
        baseline_exe = c06.consumer('baseline-consumer', False, old_prefix, default, shared, sdk)
        PROGRAMS[str(baseline_exe.relative_to(ROOT))] = baseline_exe
        off_exe = exe(consumers['default']['annotation'], 'c06-probe')
        raw_exe = exe(consumers['raw']['annotation'], 'c06-probe')
        hashes = [c06.legacy_phase(label, binary, c06.OUT / label)
                  for label, binary in [('baseline', baseline_exe), ('default', off_exe), ('raw', raw_exe)]]
        assert hashes[0] == hashes[1] == hashes[2], 'legacy annotation bytes differ from fixed baseline'
        pdf = ROOT / 'tests/fixtures/pdf-public-text.pdf'
        assert len(pdf.read_bytes()) == 8845 and hashlib.sha256(pdf.read_bytes()).hexdigest() == c06.PDF_SHA
        c06.raw_phase(raw_exe, off_exe, pdf, c06.OUT / 'raw')
        mac = c06.mac_phase(raw_exe, c06.OUT / 'mac')
        assert not c06.FAILED, c06.FAILED
        annotation = c06.OUT / 'result.json'
        annotation.write_text(json.dumps({'accepted': True, 'checks': c06.CHECKS, 'failed': c06.FAILED,
                                          'mac_records': mac, 'legacy_outputs': hashes[0]}, indent=2), encoding='utf-8')
        result['reports']['annotation'] = str(annotation.relative_to(ROOT))
        jhfixtures = OUT / 'jump-fixtures'
        run([PY, 'tests/reader_jump_history/make_fixtures.py', jhfixtures], 'jump-fixtures')
        s16 = load('foundation_s16', 'tests/reader_next_s16/run.py')
        s16.OUT = OUT / 'jump-baseline-build'
        s16.OUT.mkdir()
        baseline_source = s16.archive(s16.START, 'source', 'apps/reader/jump-history')
        baseline_prefix = OUT / 'jump-baseline-stage'
        build(baseline_source / 'apps/reader/jump-history', 'jump-baseline-module', baseline_prefix,
              ['-DCMAKE_PREFIX_PATH=' + ';'.join(map(str, [default, shared, sdk]))])
        baseline_consumer = build(ROOT / 'tests/reader_jump_history/consumer', 'jump-baseline-consumer', baseline_prefix,
                                  ['-DCMAKE_PREFIX_PATH=' + ';'.join(map(str, [baseline_prefix, default, shared, sdk]))], False)
        run([PY, 'tests/reader_jump_history/check_jump_history.py', '--probe', exe(baseline_consumer, 'jump-history-probe'),
             '--c-consumer', exe(baseline_consumer, 'jump-history-c-consumer'), '--fixtures', jhfixtures,
             '--font', ROOT / 'tests/fixtures/fonts/primary.ttf', '--installed', baseline_prefix,
             '--platform', os.environ['RUNNER_OS'], '--output', OUT / 'jump-original-baseline'], 'jump-original-baseline', 1200)
        for family, prefix in prefixes.items():
            directory = consumers[family]['jump']
            args = [PY, 'tests/reader_next_s16/check_raw.py', '--mode', 'raw' if family == 'raw' else 'default',
                    '--consumer', exe(directory, 's16-c-consumer'), '--fixtures', jhfixtures,
                    '--installed', prefix, '--platform', os.environ['RUNNER_OS'], '--output', OUT / ('jump-' + family)]
            if family == 'raw':
                args += ['--probe', exe(directory, 's16-raw-probe'), '--font', ROOT / 'tests/fixtures/fonts/primary.ttf',
                         '--pdf', pdf, '--pdf-sha', c06.PDF_SHA]
            run(args, 'jump-' + family + '-full', 1200)
            # Original 149-check suite: one declared version-line projection only.
            copied = OUT / ('jump-original-source-' + family)
            shutil.copytree(ROOT / 'tests/reader_jump_history/consumer', copied)
            if family == 'raw':
                cmake = copied / 'CMakeLists.txt'
                text = cmake.read_text(encoding='utf-8')
                before = 'find_package(EXReaderJumpHistory 0.1.0 EXACT CONFIG REQUIRED)'
                assert text.count(before) == 1
                cmake.write_text(text.replace(before, before.replace('0.1.0', '0.2.0')), encoding='utf-8')
            old = build(copied, family + '-jump-original', prefix,
                        ['-DCMAKE_PREFIX_PATH=' + ';'.join(map(str, [prefix, shared, sdk]))], False)
            run([PY, 'tests/reader_jump_history/check_jump_history.py', '--probe', exe(old, 'jump-history-probe'),
                 '--c-consumer', exe(old, 'jump-history-c-consumer'), '--fixtures', jhfixtures,
                 '--font', ROOT / 'tests/fixtures/fonts/primary.ttf', '--installed', prefix,
                 '--platform', os.environ['RUNNER_OS'], '--output', OUT / ('jump-original-' + family)], 'jump-original-' + family, 1200)
            result['reports']['jump-' + family] = str((OUT / ('jump-' + family) / 'summary.json').relative_to(ROOT))
        old_summary = json.loads((OUT / 'jump-original-baseline/summary.json').read_text(encoding='utf-8'))
        off_summary = json.loads((OUT / 'jump-original-default/summary.json').read_text(encoding='utf-8'))
        assert s16.original_projection(old_summary) == s16.original_projection(off_summary)
        revisions = build(ROOT / 'tests/reader_revisions/consumer', 'default-revision-consumer', default, [search], False)
        for family in prefixes:
            directory = consumers[family]['view']
            is_raw = family == 'raw'
            binary = exe(directory, 'raw-view-consumer' if is_raw else 'status-view-consumer')
            c_binary = exe(directory, 'raw-view-c-consumer' if is_raw else 'status-view-c-consumer')
            revision = exe(directory, 'raw-revision') if is_raw else exe(revisions, 'revision-consumer')
            checker = 'tests/reader_next_s17/check_raw_view.py' if is_raw else 'tests/reader_sync_status_view/check_status_view.py'
            output = OUT / ('view-' + family)
            run([PY, checker, '--consumer', binary, '--c-consumer', c_binary, '--revision-consumer', revision,
                 '--output', output], 'view-' + family + '-full', 2400)
            result['reports']['view-' + family] = str((output / 'result.json').relative_to(ROOT))
        for label, name in list(result['reports'].items()):
            report = ROOT / name
            data = json.loads(report.read_text(encoding='utf-8'))
            assert data['accepted'] is True, (label, data)
        shutil.copytree(ROOT / 'build/s14-evidence', OUT / 'font-evidence')
        result['reports']['font'] = str((OUT / 'font-evidence/result.json').relative_to(ROOT))
        result['runtime_accepted'] = True
    finally:
        binary_dir = OUT / 'programs'
        binary_dir.mkdir(exist_ok=True)
        for number, (name, path) in enumerate(PROGRAMS.items()):
            target = binary_dir / (str(number) + '-' + path.name)
            shutil.copyfile(path, target)
            result['programs'][name] = {'member': target.relative_to(OUT).as_posix(), 'bytes': target.stat().st_size,
                                       'sha256': hashlib.sha256(target.read_bytes()).hexdigest()}
        result['files'] = {path.relative_to(OUT).as_posix(): {'bytes': path.stat().st_size,
                           'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
                           for path in sorted(OUT.rglob('*')) if path.is_file() and path != OUT / 'result.json'}
        (OUT / 'result.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
