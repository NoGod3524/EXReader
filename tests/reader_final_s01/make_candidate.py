#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Assemble the S01 portable Windows candidate archive from the fixed producer build.

Actions only. This script never builds anything: it consumes the stage that the
producer's own unchanged packager (tools/build_windows_host.py, reused as J25)
already produced, authenticates it against that packager's registration and the
installed SDK 3.41 identity, records per-file bytes/hash/license/dependency
provenance, and writes one byte-reproducible archive.

Sources are recorded, not merged: the program comes from the fixed producer
checkout (eab342ef), the SDK from the approved 3.41 tree (edddc463, asserted
byte identical for src/include), and this verifier from the branch head.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from contract import (APPROVED_SDK, FROZEN_SDK, IMPLEMENTATION_START, PRODUCER_HEADER, PRODUCER_SOURCE,
                      PRODUCER_TREE,
                      REFERENCE_DOC, REFERENCE_PROGRAM, REFERENCE_SEAL, REQUIRED_FILES,
                      RETAINED_SOURCES, SDK_ABI, SDK_CORE_VERSION, SDK_INCLUDE_TREE, SDK_SRC_TREE,
                      SDK_VERSION, PACKAGE_NAME, classify_dependencies, dependency_names,
                      dependency_problems, forbidden_package_tokens, license_items, license_problems,
                      load_payload, manifest_problems, non_shipping_files, pe_identity,
                      describe_path_hits, private_path_needles, read_json, require, secret_hits,
                      sha256, verify_payload, write_json, write_zip)
from contract import PACKAGE_ROOT


def git(*arguments, cwd=None):
    return subprocess.check_output(['git', *arguments], cwd=str(cwd), text=True,
                                   encoding='utf-8', errors='replace').strip()


def matched(pattern, text, message):
    found = re.search(pattern, text)
    require(found is not None, message)
    return found[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--payload', type=Path, required=True, help='packaged EXReader payload directory')
    parser.add_argument('--stage', type=Path, required=True, help='installed SDK 3.41 stage')
    parser.add_argument('--licenses', type=Path, required=True, help='G09 license record for the stage')
    parser.add_argument('--producer-src', type=Path, required=True, help='checkout of the fixed producer source')
    parser.add_argument('--build', type=Path, required=True, help='compact host build directory')
    parser.add_argument('--program', type=Path, required=True, help='built compact program')
    parser.add_argument('--selftest', type=Path, required=True, help='packager self-test report.json')
    parser.add_argument('--build-root', type=Path, required=True, help='directory that holds the producer build tree')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()

    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'assemble the candidate in GitHub Actions only')
    output = args.output.resolve()
    require(not output.exists(), 'choose a new candidate output directory')
    output.mkdir(parents=True)
    producer = args.producer_src.resolve()
    repo = Path(__file__).resolve().parents[2]
    implementation = os.environ.get('GITHUB_SHA', '')
    run = {'run_id': os.environ.get('GITHUB_RUN_ID'), 'attempt': os.environ.get('GITHUB_RUN_ATTEMPT'),
           'job': os.environ.get('GITHUB_JOB')}
    problems = []

    # ---------------------------------------------------------------- sources
    require(git('rev-parse', 'HEAD', cwd=producer) == PRODUCER_SOURCE,
            'producer checkout is not the fixed producer source')
    require(git('rev-parse', 'HEAD^{tree}', cwd=producer) == PRODUCER_TREE,
            'producer checkout tree differs from the fixed producer tree')
    require(git('status', '--porcelain', '--untracked-files=no', cwd=producer) == '',
            'producer checkout has tracked changes')
    require(git('rev-parse', 'HEAD:src', cwd=producer) == SDK_SRC_TREE,
            'producer SDK core source tree differs from the approved 3.41 SDK')
    require(git('rev-parse', 'HEAD:include', cwd=producer) == SDK_INCLUDE_TREE,
            'producer SDK public headers differ from the approved 3.41 SDK')
    require(git('rev-parse', 'HEAD:src', cwd=repo) == SDK_SRC_TREE and
            git('rev-parse', 'HEAD:include', cwd=repo) == SDK_INCLUDE_TREE,
            'implementation source carries a different SDK core tree')
    retained = []
    for relative in RETAINED_SOURCES:
        local = repo / relative
        require(local.is_file(), 'retained source is missing here: ' + relative)
        require(git('rev-parse', 'HEAD:' + relative, cwd=producer) ==
                git('rev-parse', 'HEAD:' + relative, cwd=repo),
                'retained source differs between producer and implementation: ' + relative)
        retained.append({'path': relative, 'blob': git('rev-parse', 'HEAD:' + relative, cwd=producer),
                         'sha256': sha256(local)})
    require(REFERENCE_PROGRAM in (repo / REFERENCE_DOC).read_text(encoding='utf-8'),
            'the sealed document does not carry the published program hash')

    # ---------------------------------------------------------------- payload
    payload = load_payload(args.payload)
    program = args.program.resolve()
    require(program.is_file(), 'the built compact program is missing')
    require(sha256(program) == sha256(payload.get('EXReader.exe', b'')),
            'the packaged program differs from the built program')
    for name in list(payload):
        if name.lower().endswith(('.pdb', '.lib', '.exp', '.obj', '.ilk', '.map', '.idb')):
            problems.append('package carries a build input: ' + name)

    registration = read_json(args.payload.parent / 'build.json')
    require(registration.get('schema') == 1 and registration.get('passed') is True,
            'producer packaging registration did not pass')
    registered_files = registration.get('files') or {}
    if set(registered_files) != set(payload):
        problems.append('the packaging registration does not describe exactly the packaged files')
    for name in sorted(set(registered_files) & set(payload)):
        if registered_files[name] != sha256(payload[name]):
            problems.append('the packaging registration digest differs: ' + name)
    require(registration.get('source_sha') == PRODUCER_SOURCE,
            'producer packaging registration belongs to a different source')
    require(registration.get('linkage') == 'static-reading',
            'producer packaging did not declare the static reading linkage')
    require(isinstance(registration.get('selftest_checks'), int) and
            registration['selftest_checks'] >= 26,
            'producer packaging registered fewer than 26 native self-test checks')

    stage = args.stage.resolve()
    header = (stage / PRODUCER_HEADER).read_text(encoding='utf-8')
    sdk_version = matched(r'#define EXR_VERSION "([^"]+)"', header, 'installed SDK version is missing')
    sdk_abi = matched(r'#define EXR_ABI_VERSION ([0-9]+)u', header, 'installed SDK ABI is missing')
    sdk_core = matched(r'#define EXR_CORE_VERSION "([^"]+)"', header, 'installed SDK core version is missing')
    config = stage / 'lib/cmake/EXReader/EXReaderConfig.cmake'
    config_version = stage / 'lib/cmake/EXReader/EXReaderConfigVersion.cmake'
    require(config.is_file() and config_version.is_file(), 'installed SDK package configuration is missing')
    configured = matched(r'set\(PACKAGE_VERSION "([^"]+)"\)',
                         config_version.read_text(encoding='utf-8'), 'installed SDK version file is unreadable')
    require(sdk_version == SDK_VERSION,
            'installed SDK is not the approved 3.41 release: ' + sdk_version)
    require(sdk_core == SDK_CORE_VERSION and sdk_abi == SDK_ABI,
            'installed SDK core/ABI identity differs from the approved 3.41 SDK')
    require(configured == SDK_VERSION and registration.get('sdk_version') == SDK_VERSION,
            'installed SDK version file and packaging registration disagree')
    sdk = {'version': sdk_version, 'abi': sdk_abi, 'core_version': sdk_core,
           'approved_source': APPROVED_SDK, 'frozen_source': FROZEN_SDK,
           'src_tree': SDK_SRC_TREE, 'include_tree': SDK_INCLUDE_TREE,
           'header_sha256': sha256(stage / PRODUCER_HEADER),
           'config_sha256': sha256(config), 'config_version_sha256': sha256(config_version)}

    cache = read_json_cache(args.build / 'CMakeCache.txt')
    require(cache.get('EXR_READER_WINDOWS_COMPACT:BOOL') == 'ON',
            'the built program was not compiled with the compact interface')
    require(cache.get('EXR_SDK_VERSION:STRING') == SDK_VERSION, 'the built program used a different SDK version')
    require(cache.get('CMAKE_BUILD_TYPE:STRING') == 'Release', 'the built program is not a release build')
    features = sorted(key for key in cache if key.startswith('EXR_READER_WINDOWS_') and cache[key] == 'ON')

    report = read_json(args.selftest.resolve())
    image = args.selftest.resolve().parent / 'page.png'
    require(report.get('passed') is True, 'the packaged native self-test did not pass')
    require(isinstance(report.get('checks'), int) and report['checks'] >= 26,
            'the packaged native self-test reported fewer than 26 checks')
    require(report.get('engine_version') == SDK_VERSION, 'the self-test engine version differs from SDK 3.41')
    require(sha256(args.selftest.resolve()) == registration.get('report_sha256'),
            'the self-test report differs from the packaging registration')
    require(image.is_file() and sha256(image) == registration.get('image_sha256'),
            'the self-test image differs from the packaging registration')

    # ---------------------------------------------------------------- licences
    licenses_doc = read_json(args.licenses.resolve())
    require(licenses_doc.get('profile') == 'reading-library', 'the license record belongs to another profile')
    require(licenses_doc.get('source_sha') == PRODUCER_SOURCE,
            'the license record belongs to a different producer source')
    license_failures, registered = license_problems(payload, licenses_doc)
    problems += license_failures

    # ---------------------------------------------------------------- program body
    identity = pe_identity(payload['EXReader.exe'])
    require(identity['authenticode'] == 'unsigned',
            'the packaged program is not the unsigned build this package declares')
    require(identity['subsystem'] == 'windows-gui', 'the packaged program is not a native GUI image')
    require(identity['machine'] == 'amd64', 'the packaged program is not the amd64 image')

    dumpbin = shutil.which('dumpbin')
    require(dumpbin is not None, 'dumpbin is not on PATH; run inside the MSVC environment')
    completed = subprocess.run([dumpbin, '/NOLOGO', '/DEPENDENTS', str(program)],
                               capture_output=True, text=True, encoding='utf-8', errors='replace',
                               timeout=300)
    require(completed.returncode == 0, 'dumpbin /DEPENDENTS failed: ' + (completed.stderr or '').strip())
    names = dependency_names(completed.stdout)
    require(names, 'dumpbin reported no import table')
    rows = classify_dependencies(names, Path(os.environ.get('SystemRoot', 'C:\\Windows')) / 'System32',
                                 list(payload))
    problems += dependency_problems(rows)
    dependencies = {'command': [dumpbin, '/NOLOGO', '/DEPENDENTS', 'EXReader.exe'],
                    'raw_output': completed.stdout,
                    'raw_output_sha256': sha256(completed.stdout.encode('utf-8')),
                    'raw_output_bytes': len(completed.stdout.encode('utf-8')),
                    'entries': rows}

    # ---------------------------------------------------------------- byte scans
    # A build-machine path inside a shipped byte is a release blocker in the G09
    # sense: recorded per file, needle and byte offset, it sets release_ready
    # false, and it never substitutes for the portability evidence itself
    # (operating-system-only imports plus a run in a directory the build tree
    # never occupied). Test secrets stay a hard refusal.
    needles = private_path_needles([os.environ.get('GITHUB_WORKSPACE'),
                                    producer, args.build_root.resolve(), stage,
                                    args.payload.resolve(), program])
    path_hits = describe_path_hits(payload, needles)
    secret_scan = secret_hits(payload)
    for hit in secret_scan:
        problems.append('%s ships a test secret marker (%s)' % (hit['path'], hit['marker']))
    release_blockers = ['%s ships a build-machine absolute path (%s, %s, byte offset %d)'
                        % (hit['path'], hit['needle'], hit['encoding'], hit['offset'])
                        for hit in path_hits]
    require(not forbidden_package_tokens(payload),
            'package ships a browser runtime: ' + json.dumps(forbidden_package_tokens(payload)))

    # ---------------------------------------------------------------- provenance
    font = {'Reader.otf': 'font', 'OFL.txt': 'font license text'}
    pinned = {}
    for name, (source, digest) in font_assets().items():
        pinned[name] = digest
        require(name in payload, 'the pinned font asset is missing: ' + name)
        require(sha256(payload[name]) == digest, 'the packaged font asset differs from its pin: ' + name)

    upstream = {'Sample.pdf': 'tests/fixtures/pdf-public.pdf',
                'Sample-Text.pdf': 'tests/fixtures/pdf-public-text.pdf'}
    for name, relative in upstream.items():
        require(name in payload, 'the packaged sample is missing: ' + name)
        require(sha256(payload[name]) == sha256(producer / relative),
                'the packaged sample differs from the retained fixture: ' + name)

    files = []
    for name in sorted(payload):
        entry = {'path': name, 'bytes': len(payload[name]), 'sha256': sha256(payload[name])}
        if name == 'EXReader.exe':
            entry['license'] = {'kind': 'MIT', 'component': 'EXReader product host with SDK ' + SDK_VERSION,
                                'material': 'LICENSE.txt', 'notices': 'THIRD_PARTY_NOTICES.md'}
            entry['provenance'] = {'kind': 'native-program', 'producer_source': PRODUCER_SOURCE,
                                   'target': 'EXReaderProduct', 'compact': True,
                                   'linkage': 'static-reading', 'sdk': SDK_VERSION,
                                   'packager': 'tools/build_windows_host.py',
                                   'registration_sha256': sha256(args.payload.parent / 'build.json')}
        elif name in font:
            entry['license'] = {'kind': 'OFL-1.1', 'component': 'Noto Sans CJK SC Regular',
                                'material': 'OFL.txt'}
            entry['provenance'] = {'kind': 'pinned-reference-asset', 'source': 'tools/host_font.py ASSETS',
                                   'pin_sha256': pinned[name]}
        elif name == 'LICENSE.txt':
            entry['license'] = {'kind': 'MIT', 'component': 'EXReader repository license', 'material': 'LICENSE.txt'}
            entry['provenance'] = {'kind': 'repository-file', 'source': 'LICENSE',
                                   'producer_sha256': sha256(producer / 'LICENSE')}
        elif name == 'THIRD_PARTY_NOTICES.md':
            entry['license'] = {'kind': 'MIT', 'component': 'EXReader third party notices',
                                'material': 'THIRD_PARTY_NOTICES.md'}
            entry['provenance'] = {'kind': 'repository-file', 'source': 'THIRD_PARTY_NOTICES.md',
                                   'producer_sha256': sha256(producer / 'THIRD_PARTY_NOTICES.md')}
        elif name in upstream:
            entry['license'] = {'kind': 'MIT', 'component': 'first-party sample document', 'material': 'LICENSE.txt'}
            entry['provenance'] = {'kind': 'retained-fixture-copy', 'source': upstream[name],
                                   'producer_sha256': sha256(producer / upstream[name])}
        elif name.startswith('licenses/'):
            material = registered.get(name) or {}
            entry['license'] = {'kind': 'registered-third-party-material',
                                'component': material.get('component'),
                                'material': name,
                                'record_sha256': licenses_doc_sha256(args.licenses.resolve())}
            entry['provenance'] = {'kind': 'installed-sdk-license-material',
                                   'source': material.get('installed'),
                                   'origin': material.get('origin'),
                                   'pin_sha256': material.get('pinned')}
        else:
            entry['license'] = {'kind': 'MIT', 'component': 'first-party sample document', 'material': 'LICENSE.txt'}
            entry['provenance'] = {'kind': 'generated-by-packager',
                                   'source': 'tools/build_windows_host.py make_epub'}
        files.append(entry)

    expected = {row['path']: {'bytes': row['bytes'], 'sha256': row['sha256']} for row in files}
    problems += verify_payload(payload, expected, REQUIRED_FILES)
    if any(not row.get('provenance', {}).get('kind') for row in files):
        problems.append('a package file has no provenance category')

    # ---------------------------------------------------------------- archive
    archive = output / PACKAGE_NAME
    record = write_zip(payload, archive, PACKAGE_ROOT)
    problems += verify_zip_import(archive, payload)

    manifest = {'schema': 1, 'package': 'S01 portable Windows candidate package',
                'producer_source': PRODUCER_SOURCE, 'producer_tree': PRODUCER_TREE,
                'implementation_source': implementation, 'implementation_start': IMPLEMENTATION_START,
                'sdk': sdk, 'program': {'path': 'EXReader.exe', 'sha256': sha256(payload['EXReader.exe']),
                                        'bytes': len(payload['EXReader.exe']), 'pe': identity,
                                        'authenticode': identity['authenticode'],
                                        'build_features': features,
                                        'reference': {'sha256': REFERENCE_PROGRAM, 'document': REFERENCE_DOC,
                                                      'seal': REFERENCE_SEAL,
                                                      'identical_to_published_program':
                                                          sha256(payload['EXReader.exe']) == REFERENCE_PROGRAM}},
                'packager': {'path': 'tools/build_windows_host.py',
                             'sha256': sha256(repo / 'tools/build_windows_host.py'),
                             'blob': git('rev-parse', 'HEAD:tools/build_windows_host.py', cwd=producer),
                             'registration_sha256': sha256(args.payload.parent / 'build.json'),
                             'selftest': {'passed': True, 'checks': report['checks'],
                                          'engine_version': report['engine_version'],
                                          'report_sha256': sha256(args.selftest.resolve()),
                                          'image_sha256': sha256(image)}},
                'zip': record, 'files': files,
                'licenses': {'record_sha256': licenses_doc_sha256(args.licenses.resolve()),
                             'profile': licenses_doc.get('profile'),
                             'materials_check_passed': licenses_doc.get('materials_check_passed'),
                             'release_ready': licenses_doc.get('release_ready'),
                             'pending': licenses_doc.get('pending') or [],
                             'registered_material': len(registered),
                             'packaged_material': sum(1 for name in payload if name.startswith('licenses/'))},
                'dependencies': dependencies,
                'scans': {'private_paths': {'needles': needles, 'hits': path_hits},
                          'test_secrets': {'hits': secret_scan}},
                'retained': retained,
                'release_blockers': release_blockers,
                'release_ready': not problems and not release_blockers,
                'run': run, 'problems': problems,
                'scope': ('Candidate package assembly only: per-file bytes, license attribution, '
                          'dependency provenance, archive reproducibility. No device, screen-reader, '
                          'performance, signature or release acceptance.')}
    problems += manifest_problems(manifest)
    write_json(output / 'manifest.json', manifest)
    shutil.copyfile(args.licenses.resolve(), output / 'licenses.json')
    shutil.copyfile(args.selftest.resolve(), output / 'selftest-report.json')
    shutil.copyfile(image, output / 'selftest-page.png')
    identity_folder = output / 'identity'
    identity_folder.mkdir()
    shutil.copyfile(stage / PRODUCER_HEADER, identity_folder / 'base.h')
    shutil.copyfile(config, identity_folder / 'EXReaderConfig.cmake')
    shutil.copyfile(config_version, identity_folder / 'EXReaderConfigVersion.cmake')
    shutil.copyfile(args.build / 'CMakeCache.txt', identity_folder / 'compact-host-CMakeCache.txt')
    summary = {'candidate_zip': record, 'program_sha256': sha256(payload['EXReader.exe']),
               'program_bytes': len(payload['EXReader.exe']), 'files': len(files),
               'sdk_version': sdk_version, 'selftest_checks': report['checks'],
               'dependencies': len(rows), 'registered_license_material': len(registered),
               'release_ready': not problems and not release_blockers,
               'release_blockers': release_blockers, 'problems': problems}
    write_json(output / 'assembly.json', summary)
    print(json.dumps(summary), flush=True)
    require(not problems, 'candidate assembly refused: ' + json.dumps(problems))


def font_assets():
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
    import host_font
    return host_font.ASSETS


def licenses_doc_sha256(path):
    return sha256(path)


def read_json_cache(path):
    values = {}
    for line in Path(path).read_text(encoding='utf-8', errors='replace').splitlines():
        if '=' in line and not line.startswith('//') and not line.startswith('#'):
            key, value = line.split('=', 1)
            values[key.strip()] = value.strip()
    return values


def verify_zip_import(archive, payload):
    from contract import verify_zip
    return verify_zip(archive, payload, PACKAGE_ROOT)


if __name__ == '__main__':
    main()
