"""Actions-only: build the raw SDK/modules, the wave-3 Windows host, run retained and new native checks, package the ZIP.

Reuses the unchanged installed-host helpers of tests/reader_windows_raw3/host_build.py (module list, cmake runner,
owner probe judge) instead of a second build protocol. Every step is recorded; one failure never hides the others.
"""
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import traceback

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests/reader_windows_raw3'))
sys.path.insert(0, str(ROOT / 'tests/reader_windows_compact'))
import host_build as H  # noqa: E402
from contract import validate as compact_validate  # noqa: E402

OUT = ROOT / 'build/c09'
NEW_MODULES = ('apps/reader/annotation-export', 'apps/reader/annotation-import', 'apps/reader/font-library',
               'apps/reader/original-export', 'apps/reader/jump-history', 'apps/reader/sync-status-view')
RAW_NEW = {'annotation-export', 'annotation-import', 'jump-history', 'sync-status-view'}
EXTRA_FLAGS = {'reading-state': ['-DEXR_READER_PURE_CAPTURE_CANDIDATE=ON'],
               'annotation-import': ['-DREADER_ANNOTATION_IMPORT_BUILD=ON'], 'font-library': ['-DREADER_FONT_LIBRARY_BUILD=ON']}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    if os.environ.get('GITHUB_ACTIONS') != 'true' or sys.platform != 'win32':
        raise RuntimeError('Windows Actions only')
    H.OUT = OUT
    OUT.mkdir(parents=True, exist_ok=False)
    (OUT / 'logs').mkdir()
    steps = []
    result = dict(accepted=False, source_sha=os.environ['GITHUB_SHA'], run_id=os.environ['GITHUB_RUN_ID'],
                  attempt=os.environ['GITHUB_RUN_ATTEMPT'], steps=steps, failures=[])

    def step(name, function):
        try:
            value = function()
            steps.append(dict(name=name, passed=True))
            return value
        except BaseException as error:  # noqa: BLE001 - recorded, then the run fails at the end
            traceback.print_exc()
            steps.append(dict(name=name, passed=False, error=str(error)[:400]))
            result['failures'].append(name)
            return None

    content_bound = os.environ.get('EXR_COMPOSITION_CONTENT_BOUND') == '1'
    sdk, product, stage = OUT / 'sdk-stage', OUT / 'product-stage', OUT / 'raw-stage'
    prefix = ';'.join(map(str, (stage, product, sdk)))

    def build_sdk():
        H.run(['cmake', '--preset', 'reading-library', '-B', OUT / 'sdk-build', '-DCMAKE_INSTALL_PREFIX=' + str(sdk)], 'sdk-configure')
        H.run(['cmake', '--build', OUT / 'sdk-build', '--parallel', '4'], 'sdk-build')
        H.run(['cmake', '--install', OUT / 'sdk-build'], 'sdk-install')
        H.configure(ROOT / 'apps/reader/store/native', OUT / 'product-build', ['-DCMAKE_INSTALL_PREFIX=' + str(product)], 'product')
        H.run(['cmake', '--install', OUT / 'product-build'], 'product-install')

    def build_modules():
        raw = set(H.RAW_MODULES) | RAW_NEW
        for module in tuple(H.MODULES) + NEW_MODULES:
            label = Path(module).name
            options = ['-DCMAKE_INSTALL_PREFIX=' + str(stage), '-DCMAKE_PREFIX_PATH=' + prefix, '-DEXR_SDK=' + str(sdk),
                       '-DEXR_SDK_VERSION=3.41.0', '-DREADER_PRODUCT_PREFIX=' + str(product)] + EXTRA_FLAGS.get(label, [])
            if label == 'cloud-import' and content_bound:
                options.append('-DREADER_CLOUD_BUILD_CONTENT_BOUND=ON')
            if label in raw:
                options.append('-DEXR_READER_SELECTOR_BYTES_CANDIDATE=ON')
            build = OUT / ('raw-' + label)
            H.configure(ROOT / module, build, options, 'raw-' + label)
            H.run(['cmake', '--install', build], 'raw-' + label + '-install')

    def build_host():
        host = OUT / 'wave3-host'
        H.run(['cmake', '-S', ROOT / 'apps/reader/desktop', '-B', host, '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release',
               '-DCMAKE_PREFIX_PATH=' + prefix, '-DEXR_SDK=' + str(sdk), '-DEXR_SDK_VERSION=3.41.0',
               '-DREADER_METADATA_PREFIX=' + str(stage), '-DREADER_ACCOUNT_PREFIX=' + str(stage),
               '-DEXR_READER_WINDOWS_WAVE3=ON',
               '-DEXR_READER_WINDOWS_CLOUD_CONTENT_BOUND=' + ('ON' if content_bound else 'OFF'),
               '-DEXR_READER_WINDOWS_TXT_PROGRESS=' + ('ON' if os.environ.get('EXR_COMPOSITION_TXT_PROGRESS') == '1' else 'OFF')], 'wave3-host-configure')
        H.run(['cmake', '--build', host, '--target', 'EXReaderWave3', '--parallel', '4', '--verbose'], 'wave3-host-build')
        if content_bound:
            link_map = (host / 'windows-host.map').read_text(encoding='utf-8', errors='replace')
            assert re.search(r'\bexr_webdav_download_observed\b', link_map), 'content-bound transfer missing from Windows host link map'
            result['cloud_content_bound'] = True
        H.run([sys.executable, ROOT / 'tools/build_windows_host.py', '--sdk', sdk, '--binary', host / 'EXReaderWave3.exe',
               '--output', OUT / 'package', '--static-reading'], 'package')
        original = json.loads((OUT / 'package/report.json').read_text(encoding='utf-8'))
        manifest = json.loads((OUT / 'package/build.json').read_text(encoding='utf-8'))
        assert original['passed'] is True and original['checks'] >= 26
        assert manifest['source_sha'] == os.environ['GITHUB_SHA']
        result['retained26_checks'] = original['checks']
        result['package_manifest_sha256'] = sha(OUT / 'package/build.json')
        return OUT / 'package/EXReader/EXReader.exe'

    step('sdk-and-product', build_sdk)
    if not result['failures']:
        step('raw-modules', build_modules)
    exe = step('wave3-host', build_host) if not result['failures'] else None
    font = ROOT / 'build/host-font-cache/Reader.otf'
    if exe:
        result['program_sha256'] = sha(exe)
        step('ui-dependency', lambda: H.run([sys.executable, '-m', 'pip', 'install', 'uiautomation==2.0.29'], 'ui-dependency'))
        step('ui-font', lambda: H.run([sys.executable, '-c', "from tools.host_font import fetch; fetch('build/host-font-cache')"], 'ui-font'))
        fixtures = OUT / 'fixtures'
        step('ui-fixtures', lambda: H.run([sys.executable, ROOT / 'tests/reader_windows_preferences/make_fixtures.py',
                                           '--output', fixtures], 'ui-fixtures'))
        def desktop():
            try:
                H.run([sys.executable, ROOT / 'tests/reader_wave3_c09/desktop.py',
                       '--output', OUT / 'desktop.json'], 'native-desktop-geometry')
            finally:
                if (OUT / 'desktop.json').is_file():
                    result['desktop'] = json.loads((OUT / 'desktop.json').read_text(encoding='utf-8'))

        step('native-desktop-geometry', desktop)
        if os.environ.get('EXR_COMPOSITION_TXT_PROGRESS') == '1':
            def native_txt_progress():
                injector = OUT / 'txt-progress-consumer'
                H.configure(ROOT / 'tests/reader_txt_progress/consumer', injector,
                            ['-DCMAKE_PREFIX_PATH=' + prefix], 'txt-progress-consumer')
                H.run([sys.executable, ROOT / 'tests/windows_host/txt/check_progress.py', exe, font,
                       OUT / 'txt-progress', fixtures / 'Fixed page.pdf', injector / 'txtp-inject.exe', 'raw'],
                      'native-txt-progress', 2400)
            step('native-txt-progress', native_txt_progress)

        def compact22():
            """Gate on the unchanged product compact suite; preserve every failure."""
            ui = OUT / 'compact22'
            try:
                H.run([sys.executable, ROOT / 'tests/reader_windows_compact/check_ui.py', '--candidate', exe, '--font', font,
                       '--fixtures', fixtures, '--output', ui], 'retained-compact22', 900)
                report = json.loads((ui / 'report.json').read_text(encoding='utf-8'))
                compact_validate(report, os.environ['GITHUB_SHA'], os.environ['GITHUB_RUN_ID'], os.environ['GITHUB_RUN_ATTEMPT'], sha(exe))
                result['compact22_checks'] = report['count']
                result['compact22_accepted'] = True
            except BaseException as error:  # noqa: BLE001 - bounded evidence, never a fake pass
                traceback.print_exc()
                path = ui / 'report.json'
                if path.is_file():
                    report = json.loads(path.read_text(encoding='utf-8'))
                    result['compact22_checks'] = report.get('count')
                    result['compact22_problems'] = report.get('problems')
                result['compact22_accepted'] = False
                result['compact22_bound'] = str(error)[:400]
                raise

        def owner_probe():
            owner = OUT / 'raw-owner-probe'
            H.configure(ROOT / 'tests/reader_windows_raw3/owner-probe', owner,
                        ['-DCMAKE_PREFIX_PATH=' + prefix, '-DEXR_SDK=' + str(sdk), '-DPROBE_RAW=ON'], 'raw-owner-probe')
            pdf = ROOT / 'tests/fixtures/pdf-public-text.pdf'
            H.owner_run(owner / 'windows-owner-probe.exe', 'suite', OUT / 'raw-owner-suite', pdf)
            H.owner_run(owner / 'windows-owner-probe.exe', 'fresh', OUT / 'raw-owner-suite', pdf)

        step('retained-compact22', compact22)
        step('retained-raw-owner-suite', owner_probe)

        def package_zip():
            archive = shutil.make_archive(str(OUT / 'EXReader-wave3-windows'), 'zip', OUT / 'package', 'EXReader')
            result['zip'] = dict(name=Path(archive).name, bytes=Path(archive).stat().st_size, sha256=sha(archive))
            check = OUT / 'unzipped'
            shutil.unpack_archive(archive, check)
            extracted = check / 'EXReader'
            assert sha(extracted / 'EXReader.exe') == result['program_sha256']
            manifest = json.loads((OUT / 'package/build.json').read_text(encoding='utf-8'))
            assert {str(p.relative_to(extracted)).replace('\\', '/'): sha(p)
                    for p in extracted.rglob('*') if p.is_file()} == manifest['files']
            # Launch from the extracted directory with its bundled font and books,
            # so a build-tree dependency cannot masquerade as a runnable ZIP.
            evidence = OUT / 'extracted-ui'
            evidence.mkdir()
            with (evidence / 'selftest.log').open('wb') as log:
                checked = subprocess.run([str(extracted / 'EXReader.exe'), '--self-test',
                                          str(extracted / 'Reader.otf'), str(extracted / 'Sample.epub'),
                                          str(extracted / 'Sample.pdf'), str(evidence / 'selftest.json'),
                                          str(evidence / 'page.png')], cwd=extracted, stdout=log,
                                         stderr=subprocess.STDOUT, timeout=120,
                                         creationflags=subprocess.CREATE_NO_WINDOW)
            assert checked.returncode == 0
            retained = json.loads((evidence / 'selftest.json').read_text(encoding='utf-8'))
            assert retained['passed'] is True and retained['checks'] >= 26
            result['extracted_retained26_checks'] = retained['checks']
            H.run([sys.executable, ROOT / 'tests/reader_wave3_c09/check_ui.py', '--candidate', extracted / 'EXReader.exe',
                   '--font', extracted / 'Reader.otf', '--fixtures', fixtures, '--output', evidence / 'native'],
                  'extracted-native-ui', 2400)
            native = json.loads((evidence / 'native/report.json').read_text(encoding='utf-8'))
            assert native['accepted'] is True and native['consumer_sha256'] == result['program_sha256']
            assert not native['problems'] and native['source_sha'] == os.environ['GITHUB_SHA']
            assert str(native['run_id']) == os.environ['GITHUB_RUN_ID']
            assert str(native['attempt']) == os.environ['GITHUB_RUN_ATTEMPT']
            result['wave3_ui_checks'] = [row['name'] for row in native['checks']]
            result['extracted_native_ui_checks'] = [row['name'] for row in native['checks']]

        step('zip-roundtrip', package_zip)
    result['accepted'] = not result['failures']
    (OUT / 'report.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2), flush=True)
    if not result['accepted']:
        sys.exit(1)


if __name__ == '__main__':
    main()
