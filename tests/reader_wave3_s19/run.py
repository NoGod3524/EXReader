# SPDX-License-Identifier: MIT
"""Actions only. S19: single SDK and single product store closure for the five
reviewed optional reader packages.

Everything here runs on a GitHub runner: the SDK and every package are built and
installed from this source, the host DSO and its executable are compiled from the
installed packages only, the five modules are driven through real business calls,
the process module set and the binary symbol tables are inspected, and the six
mixed single-SDK/provider graphs must be refused. Nothing is built, parsed or
executed locally.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'build/reader-wave3-s19'
SEED = 'd263ce5228838ac90c0a0dc13a5193d4a7739681'
SDK_SOURCE = 'edddc463c06ed5731195cdb8f06b2df6dff7699e'
SDK_VERSION = '3.41.0'
PACKAGES = (
    ('product', 'apps/reader/store/native', ()),
    ('webdav', 'extras/webdav', ()),
    ('revisions', 'apps/reader/revisions', ()),
    ('reading-state', 'apps/reader/reading-state', ()),
    ('jump-history', 'apps/reader/jump-history', ()),
    ('sync', 'apps/reader/sync', ()),
    ('session', 'apps/reader/session', ()),
    ('sync-status-view', 'apps/reader/sync-status-view', ()),
    ('annotation-import', 'apps/reader/annotation-import', ('-DREADER_ANNOTATION_IMPORT_BUILD=ON',)),
    ('annotation-export', 'apps/reader/annotation-export', ()),
    ('font-library', 'apps/reader/font-library', ('-DREADER_FONT_LIBRARY_BUILD=ON',)),
    ('original-export', 'apps/reader/original-export', ()),
    ('host-feature-link', 'apps/reader/host-feature-link', ()),
)
BOOK_TEXT = 'A real installed host capture needs enough surrounding text for a stable anchor.'
SUFFIX = '.exe' if os.name == 'nt' else ''
SDK_LIBRARY = 'exreader.dll' if os.name == 'nt' else ('libexreader.dylib' if sys.platform == 'darwin' else 'libexreader.so')
FEATURE_LIBRARY = ('reader_host_features.dll' if os.name == 'nt'
                   else ('libreader_host_features.dylib' if sys.platform == 'darwin' else 'libreader_host_features.so'))


def path(value):
    return Path(value).absolute().as_posix()


def sha256(file):
    return hashlib.sha256(Path(file).read_bytes()).hexdigest()


def run(args, name=None, timeout=3600, env=None):
    args = [str(item) for item in args]
    print('RUN', ' '.join(args), flush=True)
    process = subprocess.run(args, cwd=str(ROOT), env=env or os.environ, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace',
                             timeout=timeout)
    if name:
        (OUT / (name + '.log')).write_text(process.stdout, encoding='utf-8')
    print(process.stdout[-8000:], flush=True)
    if process.returncode:
        raise RuntimeError((args, process.returncode))
    return process.stdout


def git(*args):
    return subprocess.check_output(['git', *args], cwd=str(ROOT), text=True).strip()


def guard():
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only'
    assert git('rev-parse', 'HEAD') == os.environ['GITHUB_SHA'], 'tested source is not GITHUB_SHA'
    subprocess.run(['git', 'merge-base', '--is-ancestor', SEED, 'HEAD'], cwd=str(ROOT), check=True)
    subprocess.run(['git', 'merge-base', '--is-ancestor', SDK_SOURCE, 'HEAD'], cwd=str(ROOT), check=True)
    # The SDK tree is the reviewed candidate, unchanged by this package.
    subprocess.run(['git', 'diff', '--exit-code', SDK_SOURCE, 'HEAD', '--',
                    'src', 'include', 'cmake', 'CMakeLists.txt', 'bindings', 'tools/layers.json'],
                   cwd=str(ROOT), check=True)
    # The five packages, their configs, the shared store/catalog chain, the
    # desktop hosts and every older driver stay byte-identical to the seed.
    subprocess.run(['git', 'diff', '--exit-code', SEED, 'HEAD', '--',
                    'apps/reader/store', 'apps/reader/revisions', 'apps/reader/reading-state',
                    'apps/reader/sync', 'apps/reader/session', 'apps/reader/desktop',
                    'apps/reader/commands', 'apps/reader/annotation-view', 'apps/reader/font-library',
                    'apps/reader/original-export', 'apps/reader/jump-history',
                    'apps/reader/sync-status-view', 'apps/reader/annotation-import',
                    'apps/reader/annotation-export', 'extras', 'examples', 'tests/fixtures',
                    'tests/reader_next_s14', 'tests/reader_next_s15', 'tests/reader_next_s16',
                    'tests/reader_next_s17', 'tests/reader_next_c06', 'docs/reader-next-s14',
                    'docs/reader-next-s15', 'docs/reader-next-s16', 'docs/reader-next-s17',
                    'docs/reader-next-c06', 'docs/handoffs'],
                   cwd=str(ROOT), check=True)
    extra = {'.github/workflows/reader-wave3-s19.yml', 'HANDOFF-RESULT-S19.md',
             'tools/reader_host_feature_link.cmake'}
    allowed = ('apps/reader/host-feature-link/', 'tests/reader_wave3_s19/', 'docs/reader-wave3-s19/')
    changed = [item for item in git('diff', '--name-only', SEED, 'HEAD').splitlines() if item]
    bad = [item for item in changed if not (item.startswith(allowed) or item in extra)]
    assert not bad, bad
    return changed


def configure_build_install(source, name, prefix, extra=(), install=True, timeout=3600):
    target = OUT / 'build' / name
    run(['cmake', '-S', str(ROOT / source), '-B', str(target), '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release',
         '-DCMAKE_PREFIX_PATH=' + path(prefix), '-DCMAKE_INSTALL_PREFIX=' + path(prefix), *extra],
        name + '-configure', timeout=timeout)
    run(['cmake', '--build', str(target), '--parallel', '4'], name + '-build', timeout=timeout)
    if install:
        run(['cmake', '--install', str(target)], name + '-install', timeout=timeout)
    return target


def sdk_environment(prefix):
    env = dict(os.environ)
    binary = str(Path(prefix) / 'bin')
    library = str(Path(prefix) / 'lib')
    env['PATH'] = binary + os.pathsep + env.get('PATH', '')
    if os.name == 'nt':
        env['PATH'] = library + os.pathsep + env['PATH']
    elif sys.platform == 'darwin':
        env['DYLD_LIBRARY_PATH'] = library + os.pathsep + env.get('DYLD_LIBRARY_PATH', '')
    else:
        env['LD_LIBRARY_PATH'] = library + os.pathsep + env.get('LD_LIBRARY_PATH', '')
    return env


def pe_reader():
    if str(ROOT / 'tests/reader_wave3_s19') not in sys.path:
        sys.path.insert(0, str(ROOT / 'tests/reader_wave3_s19'))
    from pe import PE
    return PE


def defined_symbols(binary):
    """External symbols the linker actually defined in this image."""
    binary = Path(binary)
    if os.name == 'nt':
        return pe_reader()(binary).exports()
    if sys.platform == 'darwin':
        output = subprocess.check_output(['nm', '-gU', str(binary)], text=True, errors='replace')
    else:
        # The full symbol table, not only the dynamic one: an embedded SDK object
        # keeps its definitions there even when nothing is re-exported.
        output = subprocess.check_output(['nm', '--defined-only', str(binary)], text=True,
                                         errors='replace')
    names = []
    for line in output.splitlines():
        fields = line.split()
        if len(fields) >= 2 and len(fields[-2]) == 1:
            names.append(fields[-1])
    if sys.platform == 'darwin':
        # Mach-O prefixes every C symbol with an underscore.
        names = [name[1:] if name.startswith('_') else name for name in names]
    return names


def needed_libraries(binary):
    binary = str(binary)
    if os.name == 'nt':
        return pe_reader()(Path(binary)).imports()
    if sys.platform == 'darwin':
        output = subprocess.check_output(['otool', '-L', binary], text=True, errors='replace')
        return [line.strip().split(' ')[0] for line in output.splitlines()[1:] if line.strip()]
    output = subprocess.check_output(['readelf', '-d', binary], text=True, errors='replace')
    return [line.split('[')[1].rstrip(']') for line in output.splitlines() if '(NEEDED)' in line]


def write_negative(name, body):
    folder = OUT / 'negatives' / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'empty.cpp').write_text('int main(void){return 0;}\n', encoding='utf-8')
    (folder / 'CMakeLists.txt').write_text(body, encoding='utf-8')
    return folder


def prologue(prefix):
    lines = ['cmake_minimum_required(VERSION 3.24)', 'project(S19Negative LANGUAGES C CXX)',
             'set(CMAKE_CXX_STANDARD 17)',
             'find_package(EXReader ' + SDK_VERSION + ' EXACT CONFIG REQUIRED COMPONENTS core library)',
             'find_package(EXReaderProductCatalog 0.1.0 EXACT CONFIG REQUIRED)']
    for package in ('EXReaderAnnotationImport', 'EXReaderAnnotationExport', 'EXReaderFontLibrary',
                    'EXReaderOriginalExport', 'EXReaderJumpHistory', 'EXReaderSyncView'):
        lines.append('find_package(' + package + ' 0.1.0 EXACT CONFIG REQUIRED)')
    lines.append('find_package(EXReaderHostFeatureLink 1.0.0 EXACT CONFIG REQUIRED)')
    lines.append('set(P "' + path(prefix) + '")')
    return '\n'.join(lines) + '\n'


def declare(name, prefix, sdk_link='shared', package_prefix=None):
    return ('exr_reader_host_feature_link_declare(' + name + ' SDK_PREFIX "${P}" SDK_VERSION ' + SDK_VERSION
            + ' SDK_LINK ' + sdk_link + ' STORE_PREFIX "${P}" PACKAGE_PREFIXES "' +
            (package_prefix or path(prefix)) + '")\n')


def expect_failure(folder, message, prefix, name):
    process = subprocess.run(['cmake', '-S', str(folder), '-B', str(folder / 'build'), '-G', 'Ninja',
                              '-DCMAKE_BUILD_TYPE=Release', '-DCMAKE_PREFIX_PATH=' + path(prefix)],
                             env=sdk_environment(prefix), capture_output=True, text=True,
                             encoding='utf-8', errors='replace')
    log = process.stdout + process.stderr
    (OUT / (name + '.log')).write_text(log, encoding='utf-8')
    assert process.returncode != 0, (name, 'mixed graph was accepted')
    assert message in log, (name, message, log[-3000:])
    print('REFUSED', name, '->', message, flush=True)
    return name


def main():
    changed = guard()
    OUT.mkdir(parents=True, exist_ok=True)
    (ROOT / 'build').mkdir(exist_ok=True)
    prefix = OUT / 'prefix'
    checks = []

    def check(name, detail=''):
        checks.append({'name': name, 'detail': str(detail)[:400]})
        print('PASS', name, detail, flush=True)

    # ---- one installed SDK, one installed graph -----------------------------
    run(['cmake', '--preset', 'reading-library'], 'sdk-configure', 1800)
    run(['cmake', '--build', '--preset', 'reading-library', '--parallel', '4'], 'sdk-build', 3600)
    run(['cmake', '--install', 'build/reading-library', '--prefix', path(prefix)], 'sdk-install', 1800)
    config = (prefix / 'lib/cmake/EXReader/EXReaderConfig.cmake').read_text(encoding='utf-8')
    assert 'set(EXReader_VERSION "' + SDK_VERSION + '")' in config
    check('installed-sdk-is-the-reviewed-candidate', SDK_VERSION)

    for name, source, extra in PACKAGES:
        flags = list(extra)
        if source == 'apps/reader/revisions':
            flags.append('-DREADER_PRODUCT_PREFIX=' + path(prefix))
        if source in ('apps/reader/reading-state', 'apps/reader/font-library', 'apps/reader/original-export'):
            flags += ['-DEXR_SDK=' + path(prefix), '-DEXR_SDK_VERSION=' + SDK_VERSION]
        configure_build_install(source, name, prefix, flags)
    check('installed-five-reviewed-packages',
          'font-library, original-export, jump-history, sync-status-view, annotation-import/export')

    # ---- the host program and its product DSO -------------------------------
    host = configure_build_install('tests/reader_wave3_s19/host', 'host', prefix,
                                   ['-DEXR_SDK=' + path(prefix), '-DEXR_SDK_VERSION=' + SDK_VERSION,
                                    '-DEXR_STORE=' + path(prefix),
                                    '-DEXR_MODULE_PREFIXES=' + path(prefix)], install=False)
    dso = host / FEATURE_LIBRARY
    probe = host / ('reader-host-probe' + SUFFIX)
    assert dso.exists() and probe.exists()
    for report in ('exr-host-feature-link-reader_host_features.txt',
                   'exr-host-feature-link-reader-host-probe.txt'):
        assert (host / report).exists(), report
    check('host-dso-and-executable-built-from-installed-packages', dso.name)

    # ---- six mixed single-SDK/provider graphs must be refused ---------------
    empty = OUT / 'empty-prefix'
    empty.mkdir(parents=True, exist_ok=True)
    negatives = []
    negatives.append(expect_failure(
        write_negative('dso-with-static-sdk', prologue(prefix)
                       + declare('h', prefix, 'static')
                       + 'add_library(features SHARED empty.cpp)\n'
                       + 'exr_reader_host_feature_link_attach(features h ROLE FEATURE_DSO)\n'),
        'a product DSO must not embed a second SDK implementation', prefix, 'negative-dso-static-sdk'))
    negatives.append(expect_failure(
        write_negative('two-feature-dso', prologue(prefix)
                       + declare('h', prefix)
                       + 'add_library(one SHARED empty.cpp)\n'
                       + 'exr_reader_host_feature_link_attach(one h ROLE FEATURE_DSO)\n'
                       + 'add_library(two SHARED empty.cpp)\n'
                       + 'exr_reader_host_feature_link_attach(two h ROLE FEATURE_DSO)\n'),
        'only one FEATURE_DSO may own the five modules', prefix, 'negative-two-feature-dso'))
    negatives.append(expect_failure(
        write_negative('host-links-module', prologue(prefix)
                       + declare('h', prefix)
                       + 'add_library(features SHARED empty.cpp)\n'
                       + 'exr_reader_host_feature_link_attach(features h ROLE FEATURE_DSO)\n'
                       + 'add_executable(host empty.cpp)\n'
                       + 'target_link_libraries(host PRIVATE EXReaderFontLibrary::reader_font_library)\n'
                       + 'exr_reader_host_feature_link_attach(host h ROLE HOST_EXECUTABLE HOST_OF features)\n'),
        'the host executable links module', prefix, 'negative-host-links-module'))
    negatives.append(expect_failure(
        write_negative('module-outside-prefix', prologue(prefix)
                       + declare('h', prefix, package_prefix=path(empty))),
        'resolved outside every declared install prefix', prefix, 'negative-module-outside-prefix'))
    negatives.append(expect_failure(
        write_negative('standalone-alongside-dso', prologue(prefix)
                       + declare('h', prefix)
                       + 'add_library(features SHARED empty.cpp)\n'
                       + 'exr_reader_host_feature_link_attach(features h ROLE FEATURE_DSO)\n'
                       + 'add_executable(standalone empty.cpp)\n'
                       + 'exr_reader_host_feature_link_attach(standalone h ROLE STANDALONE_EXECUTABLE)\n'),
        'already owns the modules', prefix, 'negative-standalone-alongside-dso'))
    negatives.append(expect_failure(
        write_negative('private-second-store', prologue(prefix)
                       + 'add_subdirectory("' + path(ROOT / 'apps/reader/store/native') + '" store-native)\n'
                       + declare('h', prefix)),
        'a private product store build is present', prefix, 'negative-private-store'))
    check('six-mixed-graphs-refused', ','.join(negatives))

    # ---- run the five real business paths ----------------------------------
    fixtures = OUT / 'fixtures'
    fixtures.mkdir(parents=True, exist_ok=True)
    (fixtures / 'book.txt').write_text(BOOK_TEXT, encoding='utf-8')
    shutil.copyfile(ROOT / 'tests/fixtures/fonts/primary.ttf', fixtures / 'font.ttf')
    work = OUT / 'work'
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    sys.path.insert(0, str(ROOT / 'tests/reader_reviewed_composition'))
    from webdav_fixture import WebDAVFixture
    evidence_path = OUT / 'host-evidence.json'
    with WebDAVFixture(OUT / 'dav', roots=('/dav/',), account='s19', secret='s19-fixture-secret') as dav:
        env = sdk_environment(prefix)
        for name in ('exreader.dll',):
            candidate = prefix / 'bin' / name
            if candidate.exists():
                shutil.copyfile(candidate, host / name)
        env['S19_DAV_AUTH'] = dav.authorization
        run([probe, '--work', path(work), '--fixtures', path(fixtures), '--dav-url', dav.root_url(),
             '--dso', path(dso), '--out', path(evidence_path)], 'probe-run', 2400, env=env)
        dav.assert_secret_free(OUT)
        requests = len(dav.redacted())
    evidence = json.loads(evidence_path.read_text(encoding='utf-8'))
    assert evidence['run'] == 0, (evidence['run'], evidence.get('error'))
    report = evidence['report']
    assert report and report['sdk_version'] == SDK_VERSION
    assert report['modules'] == 5 and evidence['modules'] == 5
    fonts = report['font']
    assert fonts['imported'] == 1 and fonts['entries'] == 1 and fonts['bytes'] > 0
    assert fonts['font_count'] >= 1 and fonts['glyph_A'] == 1 and fonts['glyph_0'] == 1
    assert fonts['released'] == 0 and fonts['removed'] == 0
    check('font-library-real-import-lease-and-removal', fonts['hash'][:16])
    originals = report['original']
    assert originals['status'] == 0 and originals['committed'] == 1 and originals['created'] == 1
    assert originals['bytes'] == originals['source_bytes'] and originals['bytes_match'] == 1
    assert len(originals['sha256']) == 64 and originals['path']
    check('original-export-real-original-bytes', originals['sha256'][:16])
    annotations = report['annotations']
    assert annotations['export_status'] == 0 and annotations['import_status'] == 0
    assert annotations['annotations'] == 2 and annotations['head_wires'] == 2
    assert annotations['jsonl_published'] == 1 and annotations['markdown_published'] == 1
    assert annotations['validated'] == 1 and annotations['created'] == 2 and annotations['committed'] == 2
    assert annotations['preview_items'] == 2 and annotations['preview_metadata'] == 1
    check('annotation-export-then-import-round-trip',
          str(annotations['annotations']) + '/' + str(annotations['created']))
    history = report['history']
    assert history['commits'] == 2 and history['count'] == 2 and history['cursor'] == 1
    assert history['peek'] == 0 and history['resolve'] == 1 and history['complete'] == 0
    assert history['cursor_after'] == 0 and history['closed'] == 0
    check('jump-history-real-landing-and-back', history['wire_bytes'])
    sync = report['sync']
    assert sync['create'] == 0 and sync['start'] == 0 and sync['capture'] == 0
    assert sync['summary_status'] == 0 and sync['phase'] >= 0 and sync['phase_text']
    assert sync['mirrored'] == 1, (sync['phase'], sync['observe_state'])
    assert sync['capture_outbox'] == 0 and sync['outbox_included'] == 1
    assert sync['shard_count'] == 256 and sync['close'] == 0
    check('sync-status-real-session-capture', str(sync['phase_text']) + '/' + str(requests))

    # ---- one SDK implementation, one store provider -------------------------
    assert evidence['identity'] == 1, (evidence['exe_pointer'], evidence['dso_pointer'])
    loaded = [item['name'] for item in evidence['loaded']]
    sdk_stem = SDK_LIBRARY.split('.')[0].lower()
    sdk_modules = [name for name in loaded if sdk_stem in name.lower()]
    assert len(sdk_modules) == 1, loaded
    assert loaded.count(FEATURE_LIBRARY) == 1, loaded
    check('one-loaded-sdk-implementation', sdk_modules[0])

    sdk_defined = [name for name in defined_symbols(probe)
                   if name.startswith('exr_') and not name.startswith('exr_host_features')]
    assert not sdk_defined, sdk_defined
    module_prefixes = ('rfl_', 'roe_', 'reader_jh_', 'reader_sync_view_', 'reader_annotation_', 'reader_catalog')
    copies = [name for name in defined_symbols(probe) if name.startswith(module_prefixes)]
    assert not copies, copies
    check('host-executable-holds-no-sdk-module-or-store-copy', probe.name)

    dso_defined = defined_symbols(dso)
    embedded = [name for name in dso_defined
                if name.startswith('exr_') and not name.startswith('exr_host_features')]
    assert not embedded, embedded
    assert 'exr_host_features_run' in dso_defined, dso_defined
    check('product-dso-holds-no-sdk-object-copy', str(len(dso_defined)) + ' defined')

    dso_needed = needed_libraries(dso)
    probe_needed = needed_libraries(probe)
    assert sum(1 for name in dso_needed if sdk_stem in name.lower()) == 1, dso_needed
    assert sum(1 for name in probe_needed if sdk_stem in name.lower()) == 1, probe_needed
    check('one-sdk-shared-lib-per-image', sdk_stem)

    programs = {}
    for name, file in (('reader_host_features', dso), ('reader-host-probe', probe)):
        programs[name] = {'bytes': file.stat().st_size, 'sha256': sha256(file)}
    reports = {}
    for name in ('exr-host-feature-link-reader_host_features.txt',
                 'exr-host-feature-link-reader-host-probe.txt'):
        reports[name] = (host / name).read_text(encoding='utf-8')

    logs = {item.name: hashlib.sha256(item.read_bytes()).hexdigest()
            for item in sorted(OUT.glob('*.log'))}
    result = {
        'accepted': True,
        'source_sha': os.environ['GITHUB_SHA'],
        'run_id': os.environ['GITHUB_RUN_ID'],
        'attempt': os.environ['GITHUB_RUN_ATTEMPT'],
        'platform': sys.platform,
        'runner_os': os.environ.get('RUNNER_OS', ''),
        'seed': SEED,
        'sdk_source': SDK_SOURCE,
        'sdk_version': SDK_VERSION,
        'changed_paths': changed,
        'count': len(checks),
        'checks': checks,
        'programs': programs,
        'closure_reports': reports,
        'modules_loaded': sorted(set(loaded)),
        'single_sdk_module': loaded.count(SDK_LIBRARY) == 1,
        'exr_pointer_identity': evidence['exe_pointer'] == evidence['dso_pointer'],
        'negatives': negatives,
        'dav_requests': requests,
        'report': report,
        'logs': logs,
        'scope': 'installed SDK and five optional packages linked into one product DSO and one host executable',
        'host_ui': False,
        'actual_hosts': False,
        'physical_device': False,
        'complete_product': False,
    }
    (OUT / 'result.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    # Stage exactly what the same-run evidence job re-hashes; build trees stay out.
    staged = OUT / 'artifact'
    if staged.exists():
        shutil.rmtree(staged)
    staged.mkdir(parents=True)
    shutil.copyfile(OUT / 'result.json', staged / 'result.json')
    shutil.copyfile(evidence_path, staged / 'host-evidence.json')
    for item in sorted(OUT.glob('*.log')):
        shutil.copyfile(item, staged / item.name)
    shutil.copyfile(dso, staged / dso.name)
    shutil.copyfile(probe, staged / probe.name)
    for item in (work / 'features-report.json', work / 'annotations.jsonl', work / 'annotations.md'):
        if item.exists():
            shutil.copyfile(item, staged / item.name)
    originals = sorted((work / 'originals').glob('*')) if (work / 'originals').exists() else []
    for item in originals:
        shutil.copyfile(item, staged / item.name)
    print(json.dumps({key: value for key, value in result.items()
                      if key not in ('logs', 'changed_paths', 'closure_reports')}), flush=True)


if __name__ == '__main__':
    main()
