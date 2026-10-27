#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actions-only build and acceptance for product TXT reading positions.

Installs the frozen SDK, the single product catalog/SQLite provider and every
product module the Windows host consumes, builds the real Win32 host with the
TXT original integration and the position module enabled, and runs the native
acceptance. The inherited host suites stay with their own workflow so that a
long 16,792,975-byte acceptance never competes with them on one runner.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'build' / 'txt-progress-host'
MODULES = ('extras/webdav', 'extras/credentials', 'extras/sideload', 'apps/reader/revisions',
           'apps/reader/commands', 'apps/reader/desktop-metadata', 'apps/reader/sync',
           'apps/reader/session', 'apps/reader/reading-state', 'apps/reader/reading-commands',
           'apps/reader/annotation-view', 'apps/reader/search', 'apps/reader/navigation',
           'apps/reader/cloud-import', 'apps/reader/bulk-organization', 'apps/reader/preferences',
           'apps/reader/txt-progress')
RAW_MODULES = {'revisions', 'commands', 'desktop-metadata', 'sync', 'session', 'reading-state',
               'reading-commands', 'annotation-view', 'bulk-organization', 'txt-progress'}


def run(argv, name, timeout=2400):
    out = OUT / 'logs'
    out.mkdir(parents=True, exist_ok=True)
    with (out / (name + '.log')).open('wb') as log:
        proc = subprocess.run([str(value) for value in argv], cwd=ROOT, stdout=log,
                              stderr=subprocess.STDOUT, timeout=timeout)
    if proc.returncode:
        print((out / (name + '.log')).read_text(encoding='utf-8', errors='replace')[-20000:], flush=True)
        raise RuntimeError(name + ' exit=' + str(proc.returncode))
    print(name + ' success', flush=True)


def configure(source, build, options, name):
    run(['cmake', '-S', source, '-B', build, '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release', *options],
        name + '-configure')
    run(['cmake', '--build', build, '--parallel', '4'], name + '-build')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw', action='store_true', help='Explicit raw-v3 capability family')
    args = parser.parse_args()
    if os.environ.get('GITHUB_ACTIONS') != 'true' or sys.platform != 'win32':
        raise RuntimeError('Windows Actions only')
    label = 'raw' if args.raw else 'legacy'
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'logs').mkdir(exist_ok=True)
    # One tree per profile: reusing a configured build directory would make ctest
    # run the previous profile's binaries.
    sdk = OUT / ('sdk-stage-' + label)
    product = OUT / ('product-stage-' + label)
    stage = OUT / ('module-stage-' + label)
    sdk_build = OUT / ('sdk-build-' + label)
    product_build = OUT / ('product-build-' + label)
    run(['cmake', '--preset', 'reading-library', '-B', sdk_build,
         '-DCMAKE_INSTALL_PREFIX=' + str(sdk)], 'sdk-configure')
    run(['cmake', '--build', sdk_build, '--parallel', '4'], 'sdk-build')
    run(['cmake', '--install', sdk_build], 'sdk-install')
    configure(ROOT / 'apps/reader/store/native', product_build,
              ['-DCMAKE_INSTALL_PREFIX=' + str(product)], 'product')
    run(['ctest', '--test-dir', product_build, '--output-on-failure',
         '--no-tests=error', '--timeout', '180'], 'product-tests')
    run(['cmake', '--install', product_build], 'product-install')
    run([sys.executable, '-m', 'pip', 'install', 'uiautomation==2.0.29'], 'native-ui-dependency')
    run([sys.executable, '-c', "from tools.host_font import fetch; fetch('build/host-font-cache')"], 'native-ui-font')
    fixtures = OUT / ('fixtures-' + label)
    run([sys.executable, ROOT / 'tests/reader_windows_preferences/make_fixtures.py',
         '--output', fixtures], 'native-ui-fixtures')
    prefix = ';'.join(map(str, (stage, product, sdk)))
    for module in MODULES:
        options = ['-DCMAKE_INSTALL_PREFIX=' + str(stage), '-DCMAKE_PREFIX_PATH=' + prefix,
                   '-DEXR_SDK=' + str(sdk), '-DEXR_SDK_VERSION=3.41.0',
                   '-DREADER_PRODUCT_PREFIX=' + str(product)]
        if args.raw:
            options.append('-DEXR_READER_SELECTOR_BYTES_CANDIDATE=ON')
        name = label + '-' + Path(module).name
        configure(ROOT / module, OUT / name, options, name)
        run(['cmake', '--install', OUT / name], name + '-install')
    host = OUT / ('host-' + label)
    host_options = ['-DCMAKE_PREFIX_PATH=' + prefix, '-DEXR_SDK=' + str(sdk), '-DEXR_SDK_VERSION=3.41.0',
                    '-DREADER_METADATA_PREFIX=' + str(stage), '-DREADER_ACCOUNT_PREFIX=' + str(stage),
                    '-DEXR_READER_WINDOWS_TXT_RECOVERY=ON', '-DEXR_READER_WINDOWS_TXT_PROGRESS=ON',
                    '-DEXR_READER_WINDOWS_RAW3=' + ('ON' if args.raw else 'OFF'),
                    '-DEXR_READER_WINDOWS_COMPACT=ON']
    configure(ROOT / 'apps/reader/windows-account', host, host_options, label + '-txt-progress-host')
    exe = host / 'EXReaderProduct.exe'
    evidence = OUT / ('acceptance-' + label)
    run([sys.executable, ROOT / 'tests/windows_host/txt/check_progress.py', exe,
         ROOT / 'build/host-font-cache/Reader.otf', evidence, fixtures / 'Fixed page.pdf'],
        label + '-txt-progress-acceptance', 2400)
    report = json.loads((evidence / 'report.json').read_text(encoding='utf-8'))
    summary = dict(source_sha=os.environ['GITHUB_SHA'], profile=label,
                   run_id=os.environ.get('GITHUB_RUN_ID'), attempt=os.environ.get('GITHUB_RUN_ATTEMPT'),
                   host_sha256=hashlib.sha256(exe.read_bytes()).hexdigest(),
                   accepted=report['accepted'], checks=[row['name'] for row in report['checks']],
                   report_sha256=hashlib.sha256((evidence / 'report.json').read_bytes()).hexdigest())
    (OUT / ('evidence-' + label)).mkdir(exist_ok=True)
    (OUT / ('evidence-' + label) / 'evidence.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summary), flush=True)
    if not report['accepted']:
        raise RuntimeError('TXT position acceptance failed: ' + evidence.as_posix())


if __name__ == '__main__':
    main()
