"""Actions-only: build the raw SDK/modules, the wave-3 Windows host, run retained and new native checks, package the ZIP.

Reuses the unchanged installed-host helpers of tests/reader_windows_raw3/host_build.py (module list, cmake runner,
owner probe judge) instead of a second build protocol. Every step is recorded; one failure never hides the others.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
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
EXTRA_FLAGS = {'annotation-import': ['-DREADER_ANNOTATION_IMPORT_BUILD=ON'], 'font-library': ['-DREADER_FONT_LIBRARY_BUILD=ON']}


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
               '-DEXR_READER_WINDOWS_WAVE3=ON'], 'wave3-host-configure')
        H.run(['cmake', '--build', host, '--target', 'EXReaderWave3', '--parallel', '4', '--verbose'], 'wave3-host-build')
        H.run([sys.executable, ROOT / 'tools/build_windows_host.py', '--sdk', sdk, '--binary', host / 'EXReaderWave3.exe',
               '--output', OUT / 'package', '--static-reading'], 'package')
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

        def compact22():
            ui = OUT / 'compact22'
            H.run([sys.executable, ROOT / 'tests/reader_windows_compact/check_ui.py', '--candidate', exe, '--font', font,
                   '--fixtures', fixtures, '--output', ui], 'retained-compact22', 900)
            report = json.loads((ui / 'report.json').read_text(encoding='utf-8'))
            compact_validate(report, os.environ['GITHUB_SHA'], os.environ['GITHUB_RUN_ID'], os.environ['GITHUB_RUN_ATTEMPT'], sha(exe))
            result['compact22_checks'] = report['count']

        def wave3_ui():
            ui = OUT / 'wave3-ui'
            H.run([sys.executable, ROOT / 'tests/reader_wave3_c09/check_ui.py', '--candidate', exe, '--font', font,
                   '--fixtures', fixtures, '--output', ui], 'wave3-ui', 2400)
            report = json.loads((ui / 'report.json').read_text(encoding='utf-8'))
            assert report['accepted'] is True and report['consumer_sha256'] == sha(exe) and not report['problems']
            assert report['source_sha'] == os.environ['GITHUB_SHA']
            result['wave3_ui_checks'] = [row['name'] for row in report['checks']]

        def owner_probe():
            owner = OUT / 'raw-owner-probe'
            H.configure(ROOT / 'tests/reader_windows_raw3/owner-probe', owner,
                        ['-DCMAKE_PREFIX_PATH=' + prefix, '-DEXR_SDK=' + str(sdk), '-DPROBE_RAW=ON'], 'raw-owner-probe')
            pdf = ROOT / 'tests/fixtures/pdf-public-text.pdf'
            H.owner_run(owner / 'windows-owner-probe.exe', 'suite', OUT / 'raw-owner-suite', pdf)
            H.owner_run(owner / 'windows-owner-probe.exe', 'fresh', OUT / 'raw-owner-suite', pdf)

        step('retained-compact22', compact22)
        step('wave3-native-ui', wave3_ui)
        step('retained-raw-owner-suite', owner_probe)

        def package_zip():
            archive = shutil.make_archive(str(OUT / 'EXReader-wave3-windows'), 'zip', OUT / 'package', 'EXReader')
            result['zip'] = dict(name=Path(archive).name, bytes=Path(archive).stat().st_size, sha256=sha(archive))
            check = OUT / 'unzipped'
            shutil.unpack_archive(archive, check)
            assert sha(check / 'EXReader/EXReader.exe') == result['program_sha256']

        step('zip-roundtrip', package_zip)
    result['accepted'] = not result['failures']
    (OUT / 'report.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2), flush=True)
    if not result['accepted']:
        sys.exit(1)


if __name__ == '__main__':
    main()
