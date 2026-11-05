#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actions-only install chain for the TXT position module and its probe.

Builds and installs the frozen SDK, the single product catalog/SQLite provider,
the product modules the position module depends on, and then builds the
independent installed consumer against the staged prefix only.
"""
import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'build' / 'txt-progress'
MODULES = ('apps/reader/revisions', 'apps/reader/commands', 'apps/reader/reading-state',
           'apps/reader/reading-commands', 'apps/reader/txt-progress')


def run(argv, name, timeout=2400):
    proc = subprocess.run([str(value) for value in argv], cwd=ROOT, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, encoding='utf-8', errors='replace', timeout=timeout)
    log = OUT / 'logs' / (name + '.log')
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(proc.stdout, encoding='utf-8')
    if proc.returncode:
        print(proc.stdout[-20000:], flush=True)
        raise RuntimeError(name + ' exit=' + str(proc.returncode))
    print(name + ' success', flush=True)


def configure(source, build, options, name):
    run(['cmake', '-S', source, '-B', build, '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release', *options], name + '-configure')
    run(['cmake', '--build', build, '--parallel', '4'], name + '-build')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw', action='store_true', help='Explicit raw-v3 capability family')
    args = parser.parse_args()
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise RuntimeError('Actions only')
    label = 'raw' if args.raw else 'legacy'
    sdk = OUT / 'sdk-stage'
    product = OUT / 'product-stage'
    stage = OUT / ('module-stage-' + label)
    sdk_options = ['cmake', '--preset', 'reading-library', '-B', OUT / 'sdk-build',
                   '-DCMAKE_INSTALL_PREFIX=' + str(sdk)]
    if os.name != 'nt':
        # The frozen SDK tree is unchanged; GCC 11 promotes its existing
        # misleading-indentation warning under the SDK's own -Werror. Building the
        # same sources with clang keeps the unmodified SDK tree and every product
        # assertion, instead of relaxing the project's warning policy.
        sdk_options += ['-DCMAKE_C_COMPILER=clang', '-DCMAKE_CXX_COMPILER=clang++']
    run(sdk_options, 'sdk-configure')
    run(['cmake', '--build', OUT / 'sdk-build', '--parallel', '4'], 'sdk-build')
    run(['cmake', '--install', OUT / 'sdk-build'], 'sdk-install')
    configure(ROOT / 'apps/reader/store/native', OUT / 'product-build',
              ['-DCMAKE_INSTALL_PREFIX=' + str(product)], 'product')
    run(['ctest', '--test-dir', OUT / 'product-build', '--output-on-failure',
         '--no-tests=error', '--timeout', '180'], 'product-tests')
    run(['cmake', '--install', OUT / 'product-build'], 'product-install')
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
    probe_build = OUT / ('probe-' + label)
    configure(ROOT / 'tests/reader_txt_progress/consumer', probe_build,
              ['-DCMAKE_PREFIX_PATH=' + prefix], 'probe-' + label)
    probe = probe_build / ('txtp-probe.exe' if os.name == 'nt' else 'txtp-probe')
    work = OUT / ('work-' + label)
    work.mkdir(parents=True, exist_ok=True)
    report = OUT / ('probe-report-' + label + '.json')
    run([probe, work, report, label], 'probe-run-' + label)
    run([sys.executable, ROOT / 'tests/reader_txt_progress/check.py', '--report', report,
         '--db', work / 'txtp.sqlite', '--output', OUT / ('evidence-' + label),
         *(['--raw'] if args.raw else [])], 'probe-check-' + label)
    print(json_summary(OUT / ('evidence-' + label) / 'evidence.json'))


def json_summary(path):
    import json
    data = json.loads(path.read_text(encoding='utf-8'))
    return 'txt-progress ' + data['source_sha'] + ' accepted=' + str(data['accepted'])


if __name__ == '__main__':
    main()
