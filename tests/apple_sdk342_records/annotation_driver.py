#!/usr/bin/env python3
"""Prepared Actions-only real 3.41 sender -> 3.42 annotation import proof."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from apple_swift import flags

SDK_SOURCES = {'old': ('3.41.0', '5b7a34ee4f1ce38cf3bcd7cf0220575f4ecf7da9'),
               'new': ('3.42.0', '8357eafa28423a7ab93ba08b823af80f01ad1505')}

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true' and sys.platform == 'darwin'
    parser = argparse.ArgumentParser()
    parser.add_argument('--test-only-policy', action='store_true')
    args = parser.parse_args()
    source = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    assert source == os.environ['GITHUB_SHA']
    out = ROOT / 'build/apple-sdk342-annotation'; out.mkdir(parents=True, exist_ok=False)
    evidence = out / 'evidence'; evidence.mkdir()
    owner = ROOT / 'examples/apple/HostReadingRecords.swift'
    if args.test_only_policy:
        original = owner.read_text()
        marker = '        return actual == "3.41.0" &&\n            ["3.40.0", "exreader-sdk-3.40.0", "exreader-sdk-3.41.0"].contains(recorded)'
        assert original.count(marker) == 1
        replacement = ('        return (actual == "3.41.0" &&\n'
                       '            ["3.40.0", "exreader-sdk-3.40.0", "exreader-sdk-3.41.0"].contains(recorded)) ||\n'
                       '            (actual == "3.42.0" && ["3.40.0", "3.41.0", "exreader-sdk-3.40.0", "exreader-sdk-3.41.0", "exreader-sdk-3.42.0"].contains(recorded))')
        owner = out / 'test-only/HostReadingRecords.swift'; owner.parent.mkdir()
        owner.write_text(original.replace(marker, replacement))
    def run(args, name):
        log = evidence / (name + '.log')
        with log.open('wb') as stream:
            value = subprocess.run(list(map(str, args)), cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, timeout=2400)
        print(log.read_text(errors='replace'), flush=True)
        assert value.returncode == 0, (name, value.returncode)
    programs = {}
    for label, (version, commit) in SDK_SOURCES.items():
        if subprocess.run(['git', 'cat-file', '-e', commit + '^{commit}'], cwd=ROOT).returncode:
            run(['git', 'fetch', '--no-tags', 'origin', commit], label + '-fetch')
        if label == 'new':
            run(['git', 'diff', '--exit-code', commit, source, '--', 'src', 'include', 'cmake', 'CMakeLists.txt', 'bindings'], 'sdk-content-identity')
        src, sdk, products = out / ('source-' + label), out / ('sdk-' + label), out / ('products-' + label)
        src.mkdir()
        archive = out / (label + '.tar')
        with archive.open('wb') as stream: subprocess.run(['git', 'archive', commit], cwd=ROOT, stdout=stream, check=True)
        run(['tar', '-xf', archive, '-C', src], label + '-extract')
        build = out / ('build-' + label)
        run(['cmake', '-S', src, '-B', build, '-DCMAKE_BUILD_TYPE=Release', '-DEXR_BUILD_TESTS=OFF', '-DEXR_BUILD_TOOLS=OFF', '-DEXR_ENABLE_AAC=OFF'], label + '-configure')
        run(['cmake', '--build', build, '--parallel', '4'], label + '-sdk-build')
        run(['cmake', '--install', build, '--prefix', sdk], label + '-sdk-install')
        run([sys.executable, 'tools/build_apple_product.py', '--sdk', sdk, '--sdk-version', version,
             '--target', 'macos', '--build', out / ('legacy-products-' + label)], label + '-legacy-products')
        run([sys.executable, 'tests/apple_host/reading/run_native.py', '--sdk', sdk,
             '--resources', out / ('retained-resources-' + label), '--output', evidence / ('original19-' + label)], label + '-original19')
        run([sys.executable, 'tools/build_apple_product.py', '--sdk', sdk, '--sdk-version', version, '--target', 'macos', '--product-prefix', products, '--selector-bytes-candidate', '--wave3', '--build', out / ('product-build-' + label)], label + '-products')
        executable = evidence / ('annotation-' + label)
        sources = [p for p in sorted((ROOT / 'examples/apple').glob('*.swift')) if p.name not in ('ReaderApp.swift', 'HostReadingRecords.swift')]
        sources.append(owner)
        command = ['xcrun', 'swiftc', '-swift-version', '5', '-parse-as-library', '-O', '-D', 'EXR_APPLE_HOST_REVIEW', '-I', sdk / 'include', '-L', sdk / 'lib', '-lexreader', '-Xlinker', '-rpath', '-Xlinker', sdk / 'lib', *flags(sdk, products, True, True), *sources, ROOT / 'tests/apple_sdk342_records/AnnotationInterop.swift', '-o', executable]
        run(command, label + '-compile')
        matrix = evidence / ('matrix-' + label)
        matrix_command = [*command[:-3], ROOT / 'tests/apple_sdk342_records/ParserMatrix.swift', '-o', matrix]
        run(matrix_command, label + '-matrix-compile')
        run([matrix], label + '-matrix-run')
        expected = 'APPLE_PARSER_MATRIX sdk=' + version + ' known=6 invalid=14'
        assert expected in (evidence / (label + '-matrix-run.log')).read_text()
        programs[label] = {'sdk': version, 'source': commit, 'sha256': sha(executable), 'matrix_sha256': sha(matrix)}
    resources = out / 'resources'
    run([sys.executable, 'tests/apple_host/prepare_fixtures.py', '--resources', resources], 'fixtures')
    run([sys.executable, 'tests/apple_host/navigation/prepare_navigation_fixture.py', '--resources', resources], 'navigation-fixtures')
    run([sys.executable, 'tests/apple_host/reading/prepare_reading_fixture.py', '--resources', resources], 'reading-fixtures')
    run([sys.executable, 'tests/apple_sdk342_records/make_fixed_fixtures.py', resources], 'fixed-adversarial-fixtures')
    exchange = evidence / 'exchange'; exchange.mkdir()
    for label, mode in [('old', 'produce'), ('new', 'consume')]:
        result = evidence / (label + '-result.json')
        run([evidence / ('annotation-' + label), mode, resources, out / ('profile-' + label), exchange, result], label + '-run')
        report = json.loads(result.read_text())
        assert report['accepted'] and report['source_sha'] == source and str(report['run_id']) == os.environ['GITHUB_RUN_ID'] and str(report['attempt']) == os.environ['GITHUB_RUN_ATTEMPT']
        assert report['sdk'] == SDK_SOURCES[label][0]
    import shutil
    (evidence / 'sources').mkdir()
    shutil.copyfile(ROOT / 'examples/apple/HostReadingRecords.swift', evidence / 'sources/actual-owner.swift')
    if args.test_only_policy:
        shutil.copyfile(owner, evidence / 'sources/test-only-owner.swift')
    for name in ('AnchorSource.pdf', 'AnchorMissing.pdf', 'AnchorAmbiguous.pdf'):
        shutil.copyfile(resources / name, evidence / name)
    shutil.copytree(out / 'profile-old', evidence / 'profile-old')
    shutil.copytree(out / 'profile-new', evidence / 'profile-new')
    result = {'source_sha': source, 'run_id': os.environ['GITHUB_RUN_ID'], 'attempt': os.environ['GITHUB_RUN_ATTEMPT'],
              'accepted': True, 'sdk_sources': SDK_SOURCES, 'programs': programs,
              'android_sender': False, 'physical_device': False, 'ui_accepted': False,
              'test_only_policy': args.test_only_policy, 'owner_sha256': sha(owner),
              'files': {p.relative_to(evidence).as_posix(): {'bytes': p.stat().st_size, 'sha256': sha(p)} for p in evidence.rglob('*') if p.is_file()}}
    (evidence / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result), flush=True)

if __name__ == '__main__': main()
