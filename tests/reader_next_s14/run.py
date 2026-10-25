#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""All font material, native execution and evidence processing run only in Actions."""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import tempfile
import time
import urllib.request
from fontTools.ttLib import TTCollection, TTFont
from cases import (NATIVE_COMMON, NATIVE_POSIX, ORIGINAL_COMMON, ORIGINAL_POSIX, ORIGINAL_WINDOWS,
                   ROLES_COMMON, ROLES_POSIX, ROLES_WINDOWS, S14_COMMON, S14_HARNESS)

START = 'e67d87cbeabb2457e0852f681ef0b27b2c0da4d8'
MODULE_REF = '1563f4abb85ccd28c3a0aae3e9913f4330536215'
SDK_COMMITS = {'3.40.0': '9854061be331fe603a1822d9b2b36ee357154927',
               '3.41.0': 'edddc463c06ed5731195cdb8f06b2df6dff7699e'}
TAGS = {'3.40.0': 'sdk340', '3.41.0': 'sdk341'}
# Unmodified bytes reused from the pinned library; only the two CMake files differ.
REUSED_MODULE_FILES = ('include/reader_font_library.h', 'src/library.cpp', 'src/sha256.hpp')
# Public font surface must be identical between the frozen 3.40 pin and the 3.41 candidate.
FONT_SURFACE = ('include/exr/text.h', 'include/exr/font.h', 'include/exr/core.h',
                'src/font_bitmap.c', 'src/font_color.c', 'src/font_colr_v1.c', 'src/font_outline.c',
                'src/font_path.c', 'src/font_svg.c', 'src/fonts.c', 'src/pdf_font.c')
COMMIT = '2823e993c53fca27c5c8749f529b56a5a7c77b6b'
INPUTS = [('TTF/SourceSerif4-Regular.ttf', 'font.ttf', '964a2bf8934182485cf4e2348c8443091739334f', 261868),
          ('OTF/SourceSerif4-Regular.otf', 'font.otf', 'fc9f84e94b2537b3cc10aaebcab08a0bc2a0e16b', 241392),
          ('LICENSE.md', 'LICENSE.md', 'ebe298c6b488d68a43ec9b60155fb6b862a46bc1', 4492)]
LICENSE = 'SIL Open Font License 1.1'
NEGATIVE_ROLES = {'configure-invalid-sdk', 'configure-wrong-sdk', 'consumer-wrong-sdk'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def identity(p):
    b = Path(p).read_bytes()
    return {'path': Path(p).as_posix(), 'bytes': len(b), 'sha256': sha(b)}


def git(*args):
    return subprocess.check_output(['git', *args], text=True).strip()


def ensure_commit(commit):
    if subprocess.run(['git', 'cat-file', '-e', commit + '^{commit}'], capture_output=True).returncode == 0:
        return
    subprocess.run(['git', 'fetch', '--no-tags', 'origin', commit], capture_output=True)
    assert subprocess.run(['git', 'cat-file', '-e', commit + '^{commit}'],
                          capture_output=True).returncode == 0, 'missing pinned commit ' + commit


def only(root, name):
    matches = list(Path(root).rglob(name))
    assert len(matches) == 1, (name, matches)
    return matches[0]


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only'
    sdk_version = os.environ['S14_SDK_VERSION']
    assert sdk_version in SDK_COMMITS, 'unregistered SDK selection ' + sdk_version
    tag = TAGS[sdk_version]
    sdk_commit = SDK_COMMITS[sdk_version]
    stage = Path(os.environ['S14_SDK_STAGE']).resolve()
    base = Path('build/s14-evidence').resolve()
    if base.exists():
        shutil.rmtree(base)
    base.mkdir(parents=True)
    materials = base / 'materials'
    materials.mkdir()
    results = {'accepted': False, 'source_sha': os.environ['GITHUB_SHA'], 'run_id': int(os.environ['GITHUB_RUN_ID']),
               'attempt': int(os.environ['GITHUB_RUN_ATTEMPT']), 'platform': platform.system(),
               'start': START, 'sdk_version': sdk_version, 'sdk_tag': tag, 'sdk_commit': sdk_commit,
               'module_ref': MODULE_REF, 'checks': [], 'failures': [], 'identities': [], 'inputs': [],
               'commands': [], 'terminations': [], 'host_ui_accepted': False, 'mobile_accepted': False,
               'power_loss_accepted': False, 'sdk_changed': False, 'schema_changed': False,
               'font_library_api_changed': False,
               'gaps': ['No host font picker or settings wiring; that integration belongs to root',
                        'Process termination, not power-loss hardware testing',
                        'No collection face enumeration; explicit face selection only',
                        'SDK3.41 is an unaccepted candidate until root performs final same-source acceptance']}
    log_number = 0
    exe = '.exe' if os.name == 'nt' else ''
    probe = Path('build/s14-consumer/font-probe' + exe).resolve()
    capi = Path('build/s14-consumer/font-c' + exe).resolve()

    def run(args, role, okay=True, timeout=240):
        nonlocal log_number
        p = subprocess.run([str(x) for x in args], capture_output=True, text=True, encoding='utf-8',
                           errors='replace', timeout=timeout)
        log_number += 1
        log_name = 'command-%02d.log' % log_number
        (base / log_name).write_text(p.stdout + '\n' + p.stderr, encoding='utf-8')
        results['commands'].append({'number': log_number, 'role': role, 'arguments': [str(x) for x in args],
                                    'log': log_name, 'returncode': p.returncode, 'expected_success': okay})
        print(p.stdout, end='')
        print(p.stderr, end='')
        if okay:
            assert p.returncode == 0, (args, p.returncode, p.stdout[-2000:], p.stderr[-2000:])
        return p

    def listed(root):
        return run([probe, 'list', root], 'list').stdout.splitlines()

    def rejected(directory, role, args):
        path = Path(directory)
        if path.exists():
            shutil.rmtree(path)
        return run(args, role, okay=False)

    try:
        for remote, name, git_hash, size in INPUTS:
            url = 'https://raw.githubusercontent.com/adobe-fonts/source-serif/%s/%s' % (COMMIT, remote)
            data = None
            for attempt in range(3):
                try:
                    data = urllib.request.urlopen(url, timeout=60).read()
                    break
                except Exception:
                    if attempt == 2:
                        raise
                    time.sleep(3)
            assert len(data) == size and hashlib.sha1(('blob %d\0' % size).encode() + data).hexdigest() == git_hash, \
                'fixed material mismatch'
            (materials / name).write_bytes(data)
            results['inputs'].append({'name': name, 'url': url, 'commit': COMMIT, 'git_blob': git_hash,
                                      'bytes': size, 'sha256': sha(data), 'license': LICENSE,
                                      'license_spdx': 'OFL-1.1'})
        assert 'SIL OPEN FONT LICENSE Version 1.1' in (materials / 'LICENSE.md').read_text(encoding='utf-8')
        collection = TTCollection()
        collection.fonts = [TTFont(materials / 'font.ttf', recalcTimestamp=False),
                            TTFont(materials / 'font.ttf', recalcTimestamp=False)]
        collection.save(materials / 'font.ttc')
        collection.close()
        results['inputs'].append({'name': 'font.ttc', 'derived_from': 'font.ttf twice; no glyph/name modifications',
                                  'generator': 'fonttools 4.58.0 TTCollection',
                                  'sha256': sha((materials / 'font.ttc').read_bytes()),
                                  'bytes': (materials / 'font.ttc').stat().st_size, 'license': LICENSE,
                                  'license_spdx': 'OFL-1.1'})
        (materials / 'bad.ttf').write_bytes(b'not a font\0' * 20)
        (materials / 'truncated.ttf').write_bytes((materials / 'font.ttf').read_bytes()[:64])

        # Reused module bytes: identical to the pinned library, no second parser or store.
        ensure_commit(MODULE_REF)
        reused = {path: git('hash-object', 'apps/reader/font-library/' + path) for path in REUSED_MODULE_FILES}
        for path, oid in reused.items():
            assert oid == git('rev-parse', MODULE_REF + ':apps/reader/font-library/' + path), 'module bytes differ: ' + path
        results['reused_module_bytes'] = reused
        results['reused_module_header'] = git('rev-parse', MODULE_REF + ':apps/reader/font-library/include/reader_font_library.h')
        diff = subprocess.run(['git', 'diff', '--exit-code', SDK_COMMITS['3.40.0'], SDK_COMMITS['3.41.0'],
                               '--', *FONT_SURFACE], capture_output=True, text=True)
        assert diff.returncode == 0, 'public font surface differs between the frozen and selected SDK'
        results['font_surface_unchanged'] = True
        results['checks'].append('s14-reuses-pinned-module-bytes')

        # Installed package binds exactly the SDK selected for this build.
        config = only(Path('build/s14-stage'), 'EXReaderFontLibraryConfig.cmake')
        text = config.read_text(encoding='utf-8')
        bindings = re.findall(r'find_dependency\(EXReader ([0-9]+\.[0-9]+\.[0-9]+) EXACT CONFIG COMPONENTS core\)', text)
        assert bindings == [sdk_version], ('installed package SDK binding', bindings)
        assert len(re.findall(r'find_dependency\(EXReader ', text)) == 1, 'more than one SDK dependency'
        other = '3.40.0' if sdk_version == '3.41.0' else '3.41.0'
        assert other not in text and '@EXR_SDK_VERSION@' not in text, 'unsubstituted or mixed SDK version'
        results['package_config'] = {'path': 'installed/lib/cmake/EXReaderFontLibrary/EXReaderFontLibraryConfig.cmake',
                                     'bytes': config.stat().st_size, 'sha256': sha(config.read_bytes())}
        results['checks'].append('s14-installed-package-binds-exact-sdk')

        sdk_config = (stage / 'lib/cmake/EXReader/EXReaderConfig.cmake').read_text(encoding='utf-8')
        assert 'set(EXReader_VERSION "%s")' % sdk_version in sdk_config, 'installed SDK identity'
        targets = only(Path('build/s14-stage'), 'EXReaderFontLibraryTargets.cmake').read_text(encoding='utf-8')
        assert 'EXReader::exr_core' in targets and not re.search(r'EXReader::exr_(?!core)', targets), \
            'mixed SDK targets in the installed package'
        results['checks'].append('s14-single-sdk-provider')

        header = (stage / 'include/exr/text.h').read_bytes()
        frozen = subprocess.check_output(['git', 'show', sdk_commit + ':include/exr/text.h'])
        assert header == frozen, 'installed SDK font header differs from the selected pin'
        (base / 'sdk-font-header.h').write_bytes(header)
        results['sdk_font_header_sha256'] = sha(header)
        results['sdk_exreader_config_sha256'] = sha(sdk_config.encode())
        shutil.copyfile(stage / 'lib/cmake/EXReader/EXReaderConfig.cmake', base / 'sdk-exreader-config.cmake')
        results['checks'].append('frozen-installed-font-header')

        c = run([capi], 'c-consumer')
        token = 'installed-c-abi-' + tag
        assert c.stdout.strip() == token, ('installed C consumer token', c.stdout)
        results['c_consumer_token'] = token
        results['checks'].append('installed-c-abi-sdk340')
        results['checks'].append('s14-installed-sdk-version-selected')

        rejected('build/s14-reject-invalid', 'configure-invalid-sdk', ['cmake', '-S', 'apps/reader/font-library', '-B', 'build/s14-reject-invalid',
                                        '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release', '-DREADER_FONT_LIBRARY_BUILD=ON',
                                        '-DEXR_SDK_VERSION=3.42.0', '-DEXR_SDK=%s' % stage])
        invalid_log = (base / results['commands'][-1]['log']).read_text(encoding='utf-8')
        assert 'Unsupported exact reader SDK version' in invalid_log, 'invalid SDK selection not refused'
        results['checks'].append('s14-invalid-sdk-selection-rejected')
        rejected('build/s14-reject-wrong', 'configure-wrong-sdk', ['cmake', '-S', 'apps/reader/font-library', '-B', 'build/s14-reject-wrong',
                                      '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release', '-DREADER_FONT_LIBRARY_BUILD=ON',
                                      '-DEXR_SDK_VERSION=%s' % other, '-DEXR_SDK=%s' % stage])
        results['checks'].append('s14-wrong-sdk-selection-rejected')
        rejected('build/s14-reject-consumer', 'consumer-wrong-sdk', ['cmake', '-S', 'tests/reader_next_s14/consumer', '-B',
                                         'build/s14-reject-consumer', '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release',
                                         '-DEXPECTED_SDK_VERSION=%s' % other,
                                         '-DEXPECTED_SDK_TAG=%s' % TAGS[other],
                                         '-DCMAKE_PREFIX_PATH=%s;%s' % (Path('build/s14-stage').resolve(), stage)])

        suite_root = base / 'suite'
        suite_root.mkdir()
        suite = run([probe, 'suite', suite_root, materials], 'suite')
        results['checks'] += [x[5:] for x in suite.stdout.splitlines() if x.startswith('CASE ')]
        extended = run([probe, 's14', base / 's14-suite', materials], 's14')
        results['checks'] += [x[5:] for x in extended.stdout.splitlines() if x.startswith('CASE ')]

        font_hash = sha((materials / 'font.ttf').read_bytes())
        other_hash = sha((materials / 'font.otf').read_bytes())
        for stage_name in ('copy', 'validated', 'file-published', 'committed'):
            root = base / ('crash-' + stage_name)
            root.mkdir()
            run([probe, 'import', root, materials / 'font.ttf'], 'import')
            ready = base / ('ready-' + stage_name)
            with (base / ('child-' + stage_name + '.log')).open('w', encoding='utf-8') as log:
                p = subprocess.Popen([str(probe), 'pause', str(root), str(materials / 'font.otf'), stage_name,
                                      str(ready)], stdout=log, stderr=log)
                try:
                    until = time.monotonic() + 90
                    while not ready.exists():
                        assert p.poll() is None, 'child ended before stage ' + stage_name
                        assert time.monotonic() < until, 'child stage timeout'
                        time.sleep(.05)
                    assert ready.read_text() == stage_name
                    if stage_name == 'copy':
                        assert run([probe, 'status', root], 'status').stdout.strip() == 'STATUS 8'
                    p.kill()
                    p.wait(timeout=30)
                    assert p.returncode != 0
                finally:
                    if p.poll() is None:
                        p.kill()
                        p.wait(timeout=30)
            expected = sorted([font_hash, other_hash] if stage_name == 'committed' else [font_hash])
            assert listed(root) == expected
            results['terminations'].append({'stage': stage_name, 'pid': p.pid, 'returncode': p.returncode,
                                            'recovered_hashes': expected, 'readiness_file': 'ready-' + stage_name})
            assert not list(root.glob('.rfl-tmp-*'))
            assert sorted(q.stem for q in root.glob('*.font')) == expected
            if stage_name != 'committed':
                run([probe, 'import', root, materials / 'font.otf'], 'import')
            assert listed(root) == sorted([font_hash, other_hash])
            results['checks'].append('crash-' + stage_name + '-recovery')
        results['checks'].append('cross-process-lock-and-kill-release')

        root = base / 'write-failure'
        root.mkdir()
        run([probe, 'import', root, materials / 'font.ttf'], 'import')
        before = (root / 'manifest.rfl').read_bytes()
        if os.name != 'nt':
            run([probe, 'write-full', root, materials / 'font.otf'], 'write-full')
            results['checks'].append('posix-real-short-write-preserves-old')
            assert (root / 'manifest.rfl').read_bytes() == before and listed(root) == [font_hash]
        else:
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p,
                                           ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
            kernel.CreateFileW.restype = ctypes.c_void_p
            kernel.CloseHandle.argtypes = [ctypes.c_void_p]
            handle = kernel.CreateFileW(str(root / 'manifest.rfl'), 0x80000000, 3, None, 3, 0x80, None)
            assert handle not in (None, ctypes.c_void_p(-1).value), ctypes.get_last_error()
            try:
                p = run([probe, 'import', root, materials / 'font.otf'], 'locked-manifest', okay=False)
                assert p.returncode != 0 and '4:' in p.stderr
            finally:
                assert kernel.CloseHandle(handle)
            results['checks'].append('windows-locked-manifest-publish-failure-preserves-old')
            junction = base / 'junction'
            run(['cmd', '/c', 'mklink', '/J', junction, root], 'junction-create')
            assert run([probe, 'status', junction], 'status').stdout.strip() != 'STATUS 0'
            os.rmdir(junction)
            results['checks'].append('windows-junction-rejected')
            removal = base / 'remove-uncertain'
            removal.mkdir()
            run([probe, 'import', removal, materials / 'font.ttf'], 'import')
            handle = kernel.CreateFileW(str(removal / (font_hash + '.font')), 0x80000000, 3, None, 3, 0x80, None)
            assert handle not in (None, ctypes.c_void_p(-1).value), ctypes.get_last_error()
            try:
                assert run([probe, 'remove', removal, font_hash], 'remove').stdout.strip() == 'STATUS 15 COUNT 15'
            finally:
                assert kernel.CloseHandle(handle)
            assert (removal / 'manifest.rfl').read_bytes() == b'RFL1\n'
            assert listed(removal) == [] and not list(removal.glob('*.font'))
            results['checks'].append('windows-removal-commit-uncertain-recovery')
            assert (root / 'manifest.rfl').read_bytes() == before and listed(root) == [font_hash]
        run([probe, 'import', root, materials / 'font.otf'], 'import')
        assert listed(root) == sorted([font_hash, other_hash])

        for entry in results['inputs']:
            assert sha((materials / entry['name']).read_bytes()) == entry['sha256']
        assert (suite_root / 'main' / (font_hash + '.font')).read_bytes() == (materials / 'font.ttf').read_bytes()
        results['checks'].append('recomputed-original-font-hashes')

        installed = Path('build/s14-stage').resolve()
        shutil.copytree(installed, base / 'installed')
        binary = base / 'binary'
        binary.mkdir()
        shutil.copyfile(probe, binary / probe.name)
        shutil.copyfile(capi, binary / capi.name)
        linkmap = Path('build/s14-consumer/font-probe.map')
        assert 'reader_font_library' in linkmap.read_text(errors='replace')
        assert 'rfl_import_file' in linkmap.read_text(errors='replace')
        shutil.copyfile(linkmap, binary / 'font-probe.map')
        libraries = list((base / 'installed').rglob('reader_font_library.lib')) + \
            list((base / 'installed').rglob('libreader_font_library.a'))
        assert len(libraries) == 1 and libraries[0].stat().st_size > 0
        results['module_source_tree'] = git('rev-parse', os.environ['GITHUB_SHA'] + ':apps/reader/font-library')
        for p in sorted((base / 'installed').rglob('*')) + sorted(binary.rglob('*')) + \
                sorted(materials.rglob('*')) + sorted(base.glob('command-*.log')) + \
                sorted(base.glob('ready-*')) + [base / 'sdk-font-header.h', base / 'sdk-exreader-config.cmake']:
            if p.is_file():
                item = identity(p)
                item['path'] = p.relative_to(base).as_posix()
                results['identities'].append(item)
        results['checks'].append('installed-binary-and-package-identities')

        assert not list(Path('build/s14-default-off').rglob('*reader_font_library*')), 'default-off build produced the library'
        results['checks'].append('default-off-no-library')

        roles = {c['role'] for c in results['commands']}
        failures = {c['role'] for c in results['commands'] if not c['expected_success']}
        assert failures == NEGATIVE_ROLES | ({'locked-manifest'} if os.name == 'nt' else set()), failures
        required = set(ROLES_COMMON) | set(ROLES_WINDOWS if os.name == 'nt' else ROLES_POSIX)
        assert required <= roles, required - roles
        expected = ORIGINAL_COMMON + S14_COMMON + S14_HARNESS + (ORIGINAL_WINDOWS if os.name == 'nt' else ORIGINAL_POSIX)
        assert len(results['checks']) == len(set(results['checks'])), 'duplicate case'
        assert set(results['checks']) == set(expected), (set(expected) - set(results['checks']),
                                                         set(results['checks']) - set(expected))
        native = [x[5:] for x in suite.stdout.splitlines() if x.startswith('CASE ')]
        assert set(native) == set(NATIVE_COMMON + ([] if os.name == 'nt' else NATIVE_POSIX)), 'original suite cases changed'
        extended_cases = [x[5:] for x in extended.stdout.splitlines() if x.startswith('CASE ')]
        assert extended_cases == S14_COMMON, extended_cases
        results['accepted'] = True
    except BaseException as error:
        results['failures'].append(repr(error))
        raise
    finally:
        (base / 'result.json').write_text(json.dumps(results, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(results), flush=True)


if __name__ == '__main__':
    main()
