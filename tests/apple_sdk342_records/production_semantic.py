#!/usr/bin/env python3
"""Actions-only production admission proof using genuine old Apple owners."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
OLD_OWNER = 'eea3087c2ef27b9d45e00333ef0a16e586a0ac6e'
SDKS = {'old': ('3.40.0', '9854061be331fe603a1822d9b2b36ee357154927'),
        'mid': ('3.41.0', '5b7a34ee4f1ce38cf3bcd7cf0220575f4ecf7da9'),
        'new': ('3.42.0', '8357eafa28423a7ab93ba08b823af80f01ad1505')}

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true' and sys.platform == 'darwin'
    source = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    assert source == os.environ['GITHUB_SHA']
    out = ROOT / 'build/apple-sdk342-records'; out.mkdir(parents=True, exist_ok=False)
    evidence = out / 'evidence'; evidence.mkdir()
    phases = []
    def run(args, name, expected=0):
        log = evidence / (name + '.log')
        with log.open('wb') as stream:
            process = subprocess.run(list(map(str, args)), cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, timeout=2400)
        print(log.read_text(errors='replace'), flush=True)
        assert process.returncode == expected, (name, process.returncode, expected)
    for commit in (OLD_OWNER, *(s for _, s in SDKS.values())):
        if subprocess.run(['git', 'cat-file', '-e', commit + '^{commit}'], cwd=ROOT).returncode:
            run(['git', 'fetch', '--no-tags', 'origin', commit], 'fetch-' + commit[:8])
    changed = subprocess.check_output(['git', 'diff', '--name-only', SDKS['mid'][1], SDKS['new'][1], '--', 'src', 'include', 'cmake', 'CMakeLists.txt', 'bindings'], cwd=ROOT, text=True).splitlines()
    assert set(changed) == {'CMakeLists.txt', 'cmake/versions.cmake', 'include/exr/base.h', 'include/exr/library.h', 'src/library.c'}
    run(['git', 'diff', '--exit-code', SDKS['new'][1], source, '--', 'src', 'include', 'cmake', 'CMakeLists.txt', 'bindings'], 'source-identity')
    old_owner = out / 'old-owner/HostReadingRecords.swift'; old_owner.parent.mkdir()
    old_owner.write_bytes(subprocess.check_output(['git', 'show', OLD_OWNER + ':examples/apple/HostReadingRecords.swift'], cwd=ROOT))
    (evidence / 'sources').mkdir()
    shutil.copyfile(ROOT / 'examples/apple/HostReadingRecords.swift', evidence / 'sources/current-owner.swift')
    shutil.copyfile(old_owner, evidence / 'sources/old-owner.swift')
    shutil.copyfile(ROOT / 'tests/apple_host/record_compatibility/RecordCompatibility.swift', evidence / 'sources/original-probe.swift')
    shutil.copyfile(ROOT / 'tests/apple_sdk342_records/RecordCompatibility342.swift', evidence / 'sources/probe-342.swift')
    programs = {}
    for label, (version, commit) in SDKS.items():
        src, sdk, build = out / ('source-' + label), out / ('sdk-' + label), out / ('build-' + label)
        src.mkdir()
        archive = out / (label + '.tar')
        with archive.open('wb') as stream: subprocess.run(['git', 'archive', commit], cwd=ROOT, stdout=stream, check=True)
        run(['tar', '-xf', archive, '-C', src], label + '-extract')
        run(['cmake', '-S', src, '-B', build, '-DCMAKE_BUILD_TYPE=Release', '-DEXR_BUILD_TESTS=OFF', '-DEXR_BUILD_TOOLS=OFF', '-DEXR_ENABLE_AAC=OFF'], label + '-configure')
        run(['cmake', '--build', build, '--parallel', '4'], label + '-build')
        run(['cmake', '--install', build, '--prefix', sdk], label + '-install')
        run([sys.executable, 'tools/build_apple_product.py', '--sdk', sdk, '--sdk-version', version, '--target', 'macos', '--build', out / ('products-' + label)], label + '-products')
        run([sys.executable, 'tests/apple_host/reading/run_native.py', '--sdk', sdk, '--resources', out / ('resources-' + label), '--output', evidence / ('original19-' + label)], label + '-original19')
        owners = [('original', old_owner)] if label == 'old' else [('current', ROOT / 'examples/apple/HostReadingRecords.swift')]
        for owner, owner_path in owners:
            name = label + '-' + owner; program = evidence / name
            probe = ROOT / ('tests/apple_sdk342_records/RecordCompatibility342.swift' if label == 'new' else 'tests/apple_host/record_compatibility/RecordCompatibility.swift')
            args = [sys.executable, 'tools/apple_swift.py', '--sdk', sdk, '--', '-swift-version', '5', '-parse-as-library', '-O', '-D', 'EXR_APPLE_HOST_REVIEW', '-I', sdk / 'include', '-L', sdk / 'lib', '-lexreader', '-Xlinker', '-rpath', '-Xlinker', sdk / 'lib', 'examples/apple/HostSDK.swift', 'examples/apple/HostModel.swift', 'examples/apple/HostCatalog.swift', 'examples/apple/SelectableText.swift', probe, owner_path, '-o', program]
            run(args, name + '-compile')
            programs[name] = {'sha256': sha(program), 'sdk': version, 'owner_sha256': sha(owner_path)}
    resources = out / 'resources-old'
    inputs = evidence / 'inputs'; inputs.mkdir()
    for name in ('Records.txt', 'Bounded.epub', 'Sample.pdf', 'NavigationPages.cbz', 'Reader.otf', 'reader-catalog-v1.sql'):
        shutil.copyfile(resources / name, inputs / name)
    profiles = out / 'profiles'; profiles.mkdir()
    def phase(program, mode, profile, tag, name):
        report = evidence / (name + '.json')
        run([evidence / program, mode, resources, profile, report, tag], name)
        value = json.loads(report.read_text())
        assert value['accepted'] and value['sdk'] == programs[program]['sdk'] and value['producer_parser'] == tag
        assert value['source_sha'] == source and str(value['run_id']) == os.environ['GITHUB_RUN_ID'] and str(value['attempt']) == os.environ['GITHUB_RUN_ATTEMPT']
        phases.append({'name': name, 'program': program, 'producer_parser': tag, 'report': report.name})
    for label, program, tag in [('old', 'old-original', '3.40.0'), ('mid', 'mid-current', '3.41.0')]:
        produced = profiles / (label + '-produced')
        phase(program, 'produce', produced, tag, label + '-produce')
        shutil.copytree(produced, evidence / (label + '-genuine-profile'))
        for consumer, mode in [(program, 'consume'), ('new-current', 'consume')]:
            name = label + '-' + consumer + '-' + mode; profile = profiles / name
            shutil.copytree(produced, profile); phase(consumer, mode, profile, tag, name)
        prefixed = 'exreader-sdk-' + tag
        fixture = profiles / (label + '-prefixed-fixture')
        phase(program, 'produce-prefixed', fixture, prefixed, label + '-prefixed-produce')
        shutil.copytree(fixture, evidence / (label + '-prefixed-protocol-fixture'))
        for consumer, mode in [('new-current', 'refuse')]:
            name = label + '-prefixed-' + consumer + '-' + mode; profile = profiles / name
            shutil.copytree(fixture, profile); phase(consumer, mode, profile, prefixed, name)
    for mode, tag, label in [('produce', '3.42.0', 'new'), ('produce-prefixed', 'exreader-sdk-3.42.0', 'new-prefixed')]:
        produced = profiles / (label + '-produced')
        phase('new-current', mode, produced, tag, label + '-produce')
        shutil.copytree(produced, evidence / (label + '-produced-profile'))
        for consumer, action in [('new-current', 'refuse' if label == 'new-prefixed' else 'consume'), ('mid-current', 'refuse')]:
            name = label + '-' + consumer + '-' + action; profile = profiles / name
            shutil.copytree(produced, profile); phase(consumer, action, profile, tag, name)
    result = {'source_sha': source, 'run_id': os.environ['GITHUB_RUN_ID'], 'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'accepted': True,
              'sdk_sources': SDKS, 'sdk_changed_paths': changed, 'test_only_policy': False, 'production_owner': True,
              'programs': programs, 'phases': phases, 'android_real_sender_accepted': False, 'physical_device': False,
              'duplicate_import_accepted': False, 'prefixed_inputs_are_protocol_fixtures': True,
              'files': {p.relative_to(evidence).as_posix(): {'bytes': p.stat().st_size, 'sha256': sha(p)} for p in evidence.rglob('*') if p.is_file()}}
    (evidence / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result), flush=True)

if __name__ == '__main__': main()
