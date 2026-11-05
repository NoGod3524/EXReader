"""Actions-only SDK 3.42 admission, actual installed identity, and final audit.
The original semantic suites and their budgets remain immutable. This package
owns only explicit SDK identity selection, authentication and extra evidence.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / 'tests/windows_gtk_conflict_recovery'
BASE = 'd81e0d6f8bc944baf5d7e1b5c47eb9acde3e980c'
SDK_ANCHOR = '8357eafa28423a7ab93ba08b823af80f01ad1505'
CONFLICT_SOURCE = '0c737428c6a85869f5191a3ed64f9e54beb1138f'
ORIGINALS = {'tests/reader_wave3_c09/build.py': {'blob': 'c004ce5f16ee0ae773855dfb5576a5bca205a86e', 'sha256': '7e0eef6a1554aa78b79fc47003914d53c36c4eb54d4b470df9cf1cb0b539e15d'}, 'tests/reader_windows_raw3/host_build.py': {'blob': '916a97bc688e89e9b24e3b528993e6fcec982027', 'sha256': 'd03f3d69e276566444bc94908d0e755dfe17b9f2fc86b390c5b49a1b26bbe8d2'}, 'tests/reader_windows_raw3/owner-probe/CMakeLists.txt': {'blob': 'c7895c53f2da15888bebbc22a48a28fd8de67dc4', 'sha256': '8e98a2abe253e36f896362ff0689c8a72cb2d35c3fcfd60ff8783cf8c8f51441'}, 'tests/reader_windows_raw3/owner-probe/probe.cpp': {'blob': 'a860af3b63310ce809098ce9892cdf8e60fc761e', 'sha256': '27a42832df4803d1649fff1f5ae7d62e971594ad035523c567ea53fa63263168'}}
IMPORTS = {'apps/reader/desktop-metadata/include/reader_metadata.h': '4af3412e7b3ad39d438a75a63d3dd25f00a3e5e6', 'apps/reader/desktop-metadata/src/metadata.cpp': '2969eebfc4cc35d7ac335319cee062fc2d8151b9', 'apps/reader/desktop/windows_metadata.inc': 'a19479f9fbbef2ce22488e3f428df66dd62afe78', 'apps/reader/desktop/windows_metadata_ui.inc': '0604f41da1b8586f6c78f57d827286a066cda740', 'examples/linux/metadata.inc': '54e61a543588a1e9459322b777dbd0a955dc2b35', 'examples/linux/metadata_ui.inc': 'b9c20c92c86bd94719ca7eb9666f94a414d2db81', 'examples/linux/reading.h': '5fd45835f7ea30353aad7831b7dd7e97f3e35fa8', 'tests/windows_gtk_conflict_recovery/gtk.py': '5abf8570f8c404350f934bf8c46fd61b9e120897', 'tests/windows_gtk_conflict_recovery/retained_gtk.py': 'a0ce6286aabc30c48c16b388a7a6d1b861d3091b', 'tests/windows_gtk_conflict_recovery/safety/CMakeLists.txt': 'e822dbb663e5f03b186340e6e80b1caf68bc34d5', 'tests/windows_gtk_conflict_recovery/safety/main.cpp': '715adef1f42b7cd44b0ea62a0dc2d878ff456619', 'tests/windows_gtk_conflict_recovery/service.py': '19858bb5a629e3a907f788e175cc72927bc72e02', 'tests/windows_gtk_conflict_recovery/verify.py': 'e8228b386cfbf7ad4ee221f2ec3ec7a068f8cec9', 'tests/windows_gtk_conflict_recovery/windows.py': '371d7a088d779769c9b512161a5c1f47b3ae132a'}
OWNER_FUNCTION_SHA256 = '7244627d711d93ceae32098f7531c7392db036b26af874e85356fd7aa15b0fe1'
ADAPTED_FUNCTION_SHA256 = '767e744dbbf3c6026e3bc64a37b594b8d794f258dfee14152f02a0600bb90351'
NEW_PATHS = {
    '.github/workflows/windows-gtk-conflict-sdk342.yml',
    'docs/windows-gtk-conflict-sdk342/STATUS.md',
    'tests/windows_gtk_conflict_recovery/sdk342_adapter.py',
    'tests/windows_gtk_conflict_recovery/sdk342_identity.py',
    'tests/windows_gtk_conflict_recovery/sdk342_owner_probe/CMakeLists.txt',
    'tests/windows_gtk_conflict_recovery/sdk342_owner_probe/probe.cpp',
    'tests/windows_gtk_conflict_recovery/sdk342_identity/CMakeLists.txt',
    'tests/windows_gtk_conflict_recovery/sdk342_identity/main.c',
}
SDK_PATHS = ('src', 'include', 'cmake', 'CMakeLists.txt')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def sha(path):
    return digest(Path(path).read_bytes())


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()


def actions_only():
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise RuntimeError('GitHub Actions only; no local build, test or artifact parsing')
    assert git('rev-parse', 'HEAD') == os.environ['GITHUB_SHA']


def identity():
    return dict(source_sha=os.environ['GITHUB_SHA'], run_id=os.environ['GITHUB_RUN_ID'],
                attempt=os.environ['GITHUB_RUN_ATTEMPT'])


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def authenticate():
    actions_only()
    result = {}
    for path, expected in ORIGINALS.items():
        raw = (ROOT / path).read_bytes()
        actual = dict(blob=git('hash-object', '--no-filters', path), sha256=digest(raw))
        assert actual == expected, ('Immutable original changed', path, actual)
        assert git('rev-parse', 'HEAD:' + path) == expected['blob']
        result[path] = actual
    source = (ROOT / 'tests/reader_windows_raw3/owner-probe/CMakeLists.txt').read_text()
    assert source.count('Installed SDK 3.41.0') == 1
    assert source.count('find_package(EXReader 3.41.0 EXACT') == 1
    cmake = source.replace('Installed SDK 3.41.0', 'Installed SDK 3.42.0').replace(
        'find_package(EXReader 3.41.0 EXACT', 'find_package(EXReader 3.42.0 EXACT')
    source = (ROOT / 'tests/reader_windows_raw3/owner-probe/probe.cpp').read_text()
    old = 'require(!std::strcmp(exr_version(),"3.41.0"),"Exact installed SDK3.41.0")'
    new = 'require(!std::strcmp(exr_version(),"3.42.0"),"Exact installed SDK3.42.0")'
    assert source.count(old) == 1
    probe = source.replace(old, new)
    assert 'exreader-sdk-exreader-sdk-3.41.0' in probe  # retained malformed parser negative case
    assert (PACKAGE / 'sdk342_owner_probe/CMakeLists.txt').read_bytes() == cmake.encode()
    assert (PACKAGE / 'sdk342_owner_probe/probe.cpp').read_bytes() == probe.encode()
    return result


def guard():
    originals = authenticate()
    subprocess.run(['git', 'merge-base', '--is-ancestor', BASE, 'HEAD'], cwd=ROOT, check=True)
    changed = set(git('diff', '--name-only', BASE, 'HEAD').splitlines())
    assert changed <= set(IMPORTS) | NEW_PATHS, ('Unowned changes', sorted(changed - set(IMPORTS) - NEW_PATHS))
    for path, blob in IMPORTS.items():
        assert git('rev-parse', 'HEAD:' + path) == blob, ('Accepted import changed', path)
        assert git('hash-object', '--no-filters', path) == blob
    sdk = {}
    for path in SDK_PATHS:
        sdk[path] = git('rev-parse', 'HEAD:' + path)
        assert sdk[path] == git('rev-parse', SDK_ANCHOR + ':' + path), ('Frozen SDK changed', path)
    # Tracked source bytes must still be exactly those admitted for this run.
    subprocess.run(['git', 'diff', '--exit-code', 'HEAD', '--'], cwd=ROOT, check=True)
    result = dict(identity(), accepted=True, base=BASE, sdk_anchor=SDK_ANCHOR,
                  conflict_source=CONFLICT_SOURCE, sdk_trees=sdk,
                  changed_paths=sorted(changed), originals=originals, accepted_imports=IMPORTS)
    write(ROOT / 'build/sdk342-evidence' / ('guard-' + os.environ['GITHUB_JOB'] + '.json'), result)
    print(json.dumps(result), flush=True)
    return result


def run(command, log, cwd=ROOT):
    process = subprocess.run([str(x) for x in command], cwd=cwd, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, timeout=600)
    Path(log).write_bytes(process.stdout)
    print(process.stdout.decode('utf-8', 'replace'), flush=True)
    assert process.returncode == 0, (command, process.returncode)
    return process.stdout.decode('utf-8')


def cache(path):
    result = {}
    for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
        if line and not line.startswith(('#', '//')) and '=' in line and ':' in line.split('=', 1)[0]:
            left, value = line.split('=', 1)
            result[left.split(':', 1)[0]] = value
    return result


def file_manifest(folder):
    assert folder.is_dir()
    result = {str(p.relative_to(folder)).replace('\\', '/'): dict(sha256=sha(p), bytes=p.stat().st_size)
              for p in sorted(folder.rglob('*')) if p.is_file()}
    assert result
    return result


def collect(platform):
    admitted = guard()
    windows = platform == 'windows'
    assert windows == (sys.platform == 'win32')
    out = ROOT / 'build/sdk342-evidence' / platform
    out.mkdir(parents=True, exist_ok=True)
    sdk = ROOT / ('build/c09/sdk-stage' if windows else 'build/reading-library/stage')
    stages = {'sdk': sdk, 'product': ROOT / ('build/c09/product-stage' if windows else 'build/stage')}
    if windows:
        stages['raw'] = ROOT / 'build/c09/raw-stage'
    package = ROOT / ('build/c09/package/EXReader' if windows else 'build/package/EXReader-Linux')
    program = package / ('EXReader.exe' if windows else 'bin/exreader-linux')
    build = ROOT / ('build/sdk342-probe-' + platform)
    run(['cmake', '-S', PACKAGE / 'sdk342_identity', '-B', build, '-G', 'Ninja',
         '-DCMAKE_BUILD_TYPE=Release', '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON',
         '-DEXR_SDK=' + str(sdk)], out / 'probe-configure.log')
    run(['cmake', '--build', build, '--parallel', '4', '--verbose'], out / 'probe-build.log')
    probe = build / ('sdk342-identity.exe' if windows else 'sdk342-identity')
    actual = json.loads(run([probe], out / 'probe-runtime.log'))
    assert actual == {'sdk_version': '3.42.0', 'abi': 1}
    linked = (build / 'linked-sdk.txt').read_text().splitlines()
    assert len(linked) == 3
    for value in linked:
        assert Path(value).resolve().is_relative_to(sdk.resolve()), ('Not the installed SDK', value)
    assert all(Path(value).is_file() for value in linked[1:])
    actual_cache = cache(build / 'CMakeCache.txt')
    assert Path(actual_cache['EXReader_DIR']).resolve() == Path(linked[0]).resolve()
    assert Path(actual_cache['EXR_SDK']).resolve() == sdk.resolve()
    native = {}
    if windows:
        checks = {
            'c09': ROOT / 'build/c09/report.json',
            'host-selftest': ROOT / 'build/c09/package/report.json',
            'extracted-selftest': ROOT / 'build/c09/extracted-ui/selftest.json',
            'compact22': ROOT / 'build/c09/compact22/report.json',
            'extracted-ui': ROOT / 'build/c09/extracted-ui/native/report.json',
            'owner-suite': ROOT / 'build/c09/raw-owner-suite/report-suite.json',
            'owner-fresh': ROOT / 'build/c09/raw-owner-suite/report-fresh.json',
        }
        for name, path in checks.items():
            value = json.loads(path.read_text(encoding='utf-8'))
            native[name] = value
            write(out / 'retained' / (name + '.json'), value)
        assert native['c09']['accepted'] and native['c09']['program_sha256'] == sha(program)
        assert native['host-selftest']['engine_version'] == '3.42.0'
        assert native['extracted-selftest']['engine_version'] == '3.42.0'
        for name in ('owner-suite', 'owner-fresh'):
            assert native[name]['ok'] and native[name]['sdk_version'] == '3.42.0'
        shutil.copy2(ROOT / 'build/c09/package/application.log', out / 'host-selftest.log')
        shutil.copy2(ROOT / 'build/c09/extracted-ui/selftest.log', out / 'extracted-selftest.log')
    else:
        native['version'] = run([program, '--version'], out / 'host-version.log').strip()
        assert native['version'] == '3.42.0 1'
    manifest_path = ROOT / ('build/c09/package/build.json' if windows else 'build/package/build.json')
    manifest = json.loads(manifest_path.read_text())
    assert manifest['source_sha'] == os.environ['GITHUB_SHA'] and manifest['sdk_version'] == '3.42.0'
    assert manifest['files']['EXReader.exe' if windows else 'bin/exreader-linux'] == sha(program)
    write(out / 'package-manifest.json', manifest)
    source_modules = {}
    for folder in (ROOT / 'apps/reader', ROOT / 'extras'):
        for path in sorted(folder.iterdir()):
            if path.is_dir():
                relative = str(path.relative_to(ROOT)).replace('\\', '/')
                source_modules[relative] = git('rev-parse', 'HEAD:' + relative)
    source_modules['examples/linux'] = git('rev-parse', 'HEAD:examples/linux')
    caches = {}
    for path in (ROOT / 'build').rglob('CMakeCache.txt'):
        if 'sdk342-evidence' in path.parts:
            continue
        values = cache(path)
        relevant = {k: v for k, v in values.items() if k.endswith('_DIR') or k in
                    ('EXR_SDK', 'EXR_SDK_VERSION', 'CMAKE_INSTALL_PREFIX', 'CMAKE_HOME_DIRECTORY',
                     'EXR_READER_SELECTOR_BYTES_CANDIDATE', 'EXR_READER_WINDOWS_RAW3')}
        key = str(path.relative_to(ROOT / 'build')).replace('\\', '/')
        caches[key] = relevant
        destination = out / 'cmake' / key
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
        for name in ('build.ninja', 'compile_commands.json', 'windows-host.map', 'windows-owner-probe.map',
                     'sdk342-identity.map', 'gtk-account-host.map', 'sdk-link.map', 'linked-sdk.txt', 'target-properties.txt'):
            candidate = path.parent / name
            if candidate.is_file():
                shutil.copy2(candidate, destination.parent / name)
    shutil.copytree(PACKAGE / 'sdk342_identity', out / 'probe-source', dirs_exist_ok=True)
    shutil.copy2(probe, out / probe.name)
    if windows:
        shutil.copy2(ROOT / 'build/c09/raw-owner-probe/windows-owner-probe.exe', out / 'windows-owner-probe.exe')
    installed = {name: dict(prefix=str(folder.resolve()), files=file_manifest(folder)) for name, folder in stages.items()}
    installed_packages = {}
    for stage_name, folder in stages.items():
        packages = {}
        for path in folder.rglob('*ConfigVersion.cmake'):
            match = re.search(r'set\(PACKAGE_VERSION\s+"([^"]+)"\)', path.read_text(encoding='utf-8'))
            assert match, ('No actual installed package version', str(path))
            name = path.name.removesuffix('ConfigVersion.cmake')
            assert name not in packages
            packages[name] = dict(version=match[1], config_version_path=str(path.resolve()), sha256=sha(path))
        assert packages
        installed_packages[stage_name] = packages
    assert installed_packages['sdk']['EXReader']['version'] == '3.42.0'
    assert installed_packages['product']['EXReaderProductCatalog']['version'] == '0.1.0'
    product_stage = 'raw' if windows else 'product'
    expected_modules = {name: ('0.2.0' if windows else '0.1.0') for name in
                        ('Commands', 'DesktopMetadata', 'ReadingState', 'Sync', 'Session')}
    expected_modules['Revisions'] = '0.4.0' if windows else '0.3.0'
    for name, version in expected_modules.items():
        assert installed_packages[product_stage]['EXReader' + name]['version'] == version
    required_caches = ('c09/wave3-host/CMakeCache.txt', 'c09/raw-owner-probe/CMakeCache.txt',
                       'cloud-readback/CMakeCache.txt') if windows else (
                       'desktop/CMakeCache.txt', 'reading-state/CMakeCache.txt', 'inspect/CMakeCache.txt')
    for name in required_caches:
        selected = caches[name]
        assert Path(selected['EXReader_DIR']).resolve().is_relative_to(sdk.resolve()), (name, selected)
        if name != 'c09/raw-owner-probe/CMakeCache.txt':
            assert selected['EXR_SDK_VERSION'] == '3.42.0', (name, selected)
    host_cache = caches[required_caches[0]]
    for name in expected_modules:
        assert Path(host_cache['EXReader' + name + '_DIR']).resolve().is_relative_to(stages[product_stage].resolve())
    binaries = {str(p.relative_to(package)).replace('\\', '/'): sha(p) for p in package.rglob('*')
                if p.is_file() and (p.suffix == '.exe' or p.name in ('exreader-linux', 'received-sdk-inspect', 'conflict-safety'))}
    result = dict(identity(), accepted=True, platform=platform, actual_sdk=actual, sdk_trees=admitted['sdk_trees'],
                  sdk_anchor=SDK_ANCHOR, source_modules=source_modules, installed=installed,
                  installed_packages=installed_packages,
                  product_family='raw0.2/revisions0.4' if windows else 'legacy0.1/revisions0.3',
                  package_programs=binaries, program_sha256=sha(program),
                  public_probe=dict(sha256=sha(probe), linked_sdk=linked, cache=actual_cache,
                                    target_properties=(build / 'target-properties.txt').read_text()),
                  caches=caches, native=native, originals=admitted['originals'])
    result['evidence_files'] = file_manifest(out)
    write(out / 'report.json', result)
    print('SDK342_IDENTITY ' + json.dumps(dict(identity(), accepted=True, platform=platform,
          actual_sdk=actual, program_sha256=sha(program), probe_sha256=sha(probe),
          installed_prefixes={name: str(folder.resolve()) for name, folder in stages.items()},
          installed_package_versions={stage: {name: entry['version'] for name, entry in packages.items()}
                                      for stage, packages in installed_packages.items()})), flush=True)


def bound(report):
    assert all(str(report[k]) == value for k, value in identity().items())
    assert report['accepted'] is True


def audit():
    admitted = guard()
    root = ROOT / 'build/sdk342-audit'
    suffix = os.environ['GITHUB_RUN_ID'] + '-' + os.environ['GITHUB_RUN_ATTEMPT']
    reports = {}
    for platform in ('windows', 'gtk'):
        folder = root / ('sdk342-' + platform + '-identity-' + suffix)
        report = json.loads((folder / 'report.json').read_text())
        bound(report)
        assert report['actual_sdk'] == {'sdk_version': '3.42.0', 'abi': 1}
        assert report['sdk_anchor'] == SDK_ANCHOR and report['sdk_trees'] == admitted['sdk_trees']
        assert report['originals'] == ORIGINALS
        for path, value in report['evidence_files'].items():
            actual = folder / path
            assert sha(actual) == value['sha256'] and actual.stat().st_size == value['bytes'], path
        manifest = json.loads((folder / 'package-manifest.json').read_text())
        assert manifest['source_sha'] == os.environ['GITHUB_SHA'] and manifest['sdk_version'] == '3.42.0'
        package = root / (('windows-gtk-package-' if platform == 'windows' else 'gtk-windows-package-') + suffix)
        for path, expected in report['package_programs'].items():
            assert sha(package / path) == expected
        assert report['program_sha256'] == sha(package / ('EXReader.exe' if platform == 'windows' else 'bin/exreader-linux'))
        assert report['installed']['sdk']['files']
        assert report['installed_packages']['sdk']['EXReader']['version'] == '3.42.0'
        reports[platform] = report
    win, gtk = reports['windows'], reports['gtk']
    assert win['source_modules'] == gtk['source_modules']
    for report, stage, module_version, revision_version in ((win, 'raw', '0.2.0', '0.4.0'), (gtk, 'product', '0.1.0', '0.3.0')):
        for name in ('Commands', 'DesktopMetadata', 'ReadingState', 'Sync', 'Session'):
            assert report['installed_packages'][stage]['EXReader' + name]['version'] == module_version
        assert report['installed_packages'][stage]['EXReaderRevisions']['version'] == revision_version
    assert win['product_family'] == 'raw0.2/revisions0.4' and gtk['product_family'] == 'legacy0.1/revisions0.3'
    native = win['native']
    bound(native['c09'])
    assert not native['c09']['failures'] and all(s['passed'] for s in native['c09']['steps'])
    assert native['c09']['compact22_accepted'] and native['c09']['compact22_checks'] == 22
    for key in ('retained26_checks', 'extracted_retained26_checks'):
        assert native['c09'][key] >= 26
    owner_hash = sha(root / ('sdk342-windows-identity-' + suffix) / 'windows-owner-probe.exe')
    for mode in ('suite', 'fresh'):
        owner = native['owner-' + mode]
        assert owner['source_sha'] == os.environ['GITHUB_SHA'] and owner['sdk_version'] == '3.42.0'
        assert owner['program_sha256'] == owner_hash and owner['profile'] == 'raw3'
        assert owner['ok'] and owner['checks'] and all(c['pass'] for c in owner['checks'])
    adapter = json.loads((root / ('sdk342-windows-identity-' + suffix) / 'c09-adapter.json').read_text())
    bound(adapter)
    assert adapter['originals'] == ORIGINALS
    assert adapter['owner_function_sha256'] == OWNER_FUNCTION_SHA256
    assert adapter['adapted_function_sha256'] == ADAPTED_FUNCTION_SHA256
    assert adapter['sdk_argument_changes'] == adapter['expected_sdk_argument_changes']
    assert adapter['owner_source_redirects'] == 1
    baseline = json.loads((root / ('windows-gtk-summary-' + suffix) / 'result.json').read_text())
    conflict = json.loads((ROOT / 'build/conflict-summary/result.json').read_text())
    for report in (baseline, conflict):
        bound(report)
    assert baseline['windows_program_sha256'] == win['program_sha256']
    assert baseline['gtk_program_sha256'] == gtk['program_sha256']
    for phase in conflict['phases']:
        expected = win if phase['phase'].startswith('windows-') else gtk
        assert phase['program_sha256'] == expected['program_sha256']
    for name, count in (('current-account', 48), ('original-account', 46)):
        retained = json.loads((root / ('windows-gtk-gtk-first-' + suffix) / name / 'result.json').read_text())
        bound(retained)
        assert retained['count'] == count and retained['program_sha256'] == gtk['program_sha256']
    api = json.loads(subprocess.check_output(['gh', 'api', 'repos/' + os.environ['GITHUB_REPOSITORY'] +
                    '/actions/runs/' + os.environ['GITHUB_RUN_ID'] + '/artifacts?per_page=100'], text=True))
    names = ['windows-gtk-package-', 'gtk-windows-package-', 'windows-gtk-first-', 'windows-gtk-gtk-first-',
             'windows-gtk-return-', 'windows-gtk-final-', 'windows-gtk-summary-',
             'sdk342-windows-identity-', 'sdk342-gtk-identity-']
    names += ['conflict-' + phase + '-' for phase in ('windows-offline', 'gtk-offline', 'windows-resolve', 'gtk-final', 'windows-final')]
    artifacts = []
    for prefix in names:
        matches = [a for a in api['artifacts'] if a['name'] == prefix + suffix and not a['expired']]
        assert len(matches) == 1
        a = matches[0]
        assert a['size_in_bytes'] > 0 and a['digest'].startswith('sha256:')
        assert a['workflow_run']['head_sha'] == os.environ['GITHUB_SHA']
        artifacts.append({k: a[k] for k in ('id', 'name', 'size_in_bytes', 'digest')})
    by_name = {a['name']: a for a in artifacts}
    for report in (baseline, conflict):
        for original in report['artifacts']:
            assert original == by_name[original['name']]
    result = dict(identity(), accepted=True, sdk_version='3.42.0', abi=1, sdk_anchor=SDK_ANCHOR,
                  sdk_trees=admitted['sdk_trees'], source_modules=win['source_modules'], artifacts=artifacts,
                  windows_program_sha256=win['program_sha256'], gtk_program_sha256=gtk['program_sha256'],
                  original_sha256=conflict['book_original_sha256'], conflict_heads=conflict['conflict_heads'],
                  resolution=conflict['resolution'], retained_compact_checks=22,
                  retained_gtk_checks={'current': 48, 'original': 46},
                  retained_owner_checks={m: len(native['owner-' + m]['checks']) for m in ('suite', 'fresh')},
                  baseline_checks=sum(len(p['checks']) for p in baseline['phases']),
                  conflict_checks=sum(len(p['checks']) for p in conflict['phases']),
                  adaptation='Original semantic suites and budgets with authenticated explicit 3.42 identity adaptation; no version spoofing',
                  scope='Windows raw0.2 and GTK legacy0.1 same-source metadata conflict recovery/tag delete-restore; not six-platform certification')
    write(ROOT / 'build/conflict-summary/sdk342-result.json', result)
    print('SDK342_FINAL_AUDIT ' + json.dumps(result), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('guard', 'collect', 'audit'))
    parser.add_argument('--platform', choices=('windows', 'gtk'))
    args = parser.parse_args()
    actions_only()
    if args.mode == 'guard':
        guard()
    elif args.mode == 'collect':
        assert args.platform
        collect(args.platform)
    else:
        audit()
