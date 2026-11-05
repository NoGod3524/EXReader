#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Prove the producer source, the approved SDK source and the installed stage.

Three separate source identities are recorded and never merged: this verifier
branch, the actual macOS producer commit, and the approved 3.41 SDK commit. The
built SDK source tree is compared blob by blob with the approved commit, so the
"single SDK source" claim rests on bytes rather than on a document.
"""
import argparse
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import spec


def command(*arguments, cwd=None):
    done = subprocess.run([str(item) for item in arguments], cwd=str(cwd) if cwd else None,
                          capture_output=True)
    return done.returncode, done.stdout


def command_text(*arguments, cwd=None):
    code, output = command(*arguments, cwd=cwd)
    return output.decode('utf-8', 'replace').strip() if code == 0 else ''


def git(cwd, *arguments):
    code, output = command('git', *arguments, cwd=cwd)
    if code != 0:
        raise RuntimeError('git failed: ' + ' '.join(map(str, arguments)))
    return output


def tree_entries(repo, sha):
    """Every tracked path of one commit with its git object name."""
    entries = {}
    for chunk in git(repo, 'ls-tree', '-r', '-z', sha).split(b'\0'):
        if not chunk:
            continue
        meta, path = chunk.split(b'\t', 1)
        mode, kind, blob = meta.split(b' ')
        entries[path.decode('utf-8')] = {'mode': mode.decode(), 'type': kind.decode(),
                                         'blob': blob.decode()}
    return entries


def local_kinds(root):
    kinds = {}
    for path in sorted(Path(root).rglob('*')):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            kinds[relative] = ('link', os.readlink(path))
        elif path.is_file():
            kinds[relative] = ('file', path)
    return kinds


def tree_problems(root, entries):
    """The extracted tree must be exactly the approved commit, blob by blob."""
    problems = []
    kinds = local_kinds(root)
    for relative in sorted(entries):
        entry = entries[relative]
        if relative not in kinds:
            problems.append('sdk_tree_missing:' + relative)
            continue
        how, value = kinds[relative]
        if entry['mode'] == '120000':
            data = value.encode('utf-8') if how == 'link' else value.read_bytes()
        elif how != 'file':
            problems.append('sdk_tree_kind:' + relative)
            continue
        else:
            data = value.read_bytes()
        observed = spec.git_blob_digest(data)
        if observed != entry['blob']:
            # A checkout may normalise line endings; accept only that difference.
            if spec.git_blob_digest(data.replace(b'\r\n', b'\n')) != entry['blob']:
                problems.append('sdk_tree_blob:' + relative)
    for relative in sorted(set(kinds) - set(entries)):
        problems.append('sdk_tree_extra:' + relative)
    return problems


def stage_identity(stage):
    problems = []
    header = stage / 'include/exr/base.h'
    text = header.read_text(encoding='utf-8') if header.is_file() else ''
    version = re.search(r'#define EXR_VERSION "([^"]+)"', text)
    abi = re.search(r'#define EXR_ABI_VERSION (\S+)', text)
    libraries = []
    for path in sorted((stage / 'lib').glob('libexreader*.dylib')):
        if path.is_file():
            libraries.append({'name': path.name, 'bytes': path.stat().st_size,
                              'sha256': spec.digest(path),
                              'install_name': command_text('otool', '-D', path).splitlines()[-1].strip()
                              if command_text('otool', '-D', path) else ''})
    config = stage / 'lib/cmake/EXReader/EXReaderConfigVersion.cmake'
    config_text = config.read_text(encoding='utf-8') if config.is_file() else ''
    package_version = re.search(r'set\(PACKAGE_VERSION\s+"([^"]+)"\)', config_text)
    manifest_path = stage / 'share/exreader-apple/product.json'
    manifest = None
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        except ValueError:
            problems.append('stage_product_manifest_json')
    if not libraries:
        problems.append('stage_sdk_library_missing')
    if version is None or version[1] != spec.SDK_VERSION:
        problems.append('stage_sdk_version:' + (version[1] if version else 'missing'))
    if abi is None or abi[1] != spec.SDK_ABI:
        problems.append('stage_sdk_abi:' + (abi[1] if abi else 'missing'))
    if package_version is None or package_version[1] != spec.SDK_VERSION:
        problems.append('stage_package_version:' + (package_version[1] if package_version else 'missing'))
    if manifest is None:
        problems.append('stage_product_manifest_missing')
    else:
        if manifest.get('sdk_version') != spec.SDK_VERSION:
            problems.append('stage_product_manifest_sdk')
        if manifest.get('selector_bytes_candidate') is not False:
            problems.append('stage_product_manifest_selector')
        if len(manifest.get('installed_modules') or []) != 12:
            problems.append('stage_product_manifest_modules')
        if manifest.get('sqlite_provider') != 'libreader_catalog_sqlite.a':
            problems.append('stage_product_manifest_sqlite')
    return {'version': version[1] if version else None,
            'abi': abi[1] if abi else None,
            'package_version': package_version[1] if package_version else None,
            'libraries': libraries,
            'product_manifest': manifest,
            'problems': problems}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--producer', type=Path, required=True)
    parser.add_argument('--sdk-source', type=Path, required=True)
    parser.add_argument('--sdk-source-sha', default=spec.SDK_SHA)
    parser.add_argument('--stage', type=Path, required=True)
    parser.add_argument('--archive', type=Path)
    parser.add_argument('--verifier-sha', default=os.environ.get('GITHUB_SHA', ''))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    problems = []
    producer = args.producer.absolute()
    head = command_text('git', 'rev-parse', 'HEAD', cwd=producer)
    branch = command_text('git', 'rev-parse', '--abbrev-ref', 'HEAD', cwd=producer)
    subject = command_text('git', 'log', '-1', '--format=%H %ci %s', cwd=producer)
    if head != spec.PRODUCER_SHA:
        problems.append('producer_head:' + head)
    # The secondary checkout is detached on the pinned commit, so the branch name
    # reads "HEAD"; the pinned branch is recorded from the producer's own evidence.
    required = []
    for relative in spec.PRODUCER_REQUIRED_FILES:
        if not (producer / relative).is_file():
            problems.append('producer_file_missing:' + relative)
        required.append(relative)
    for relative, flag in spec.PRODUCER_REQUIRED_FLAGS:
        path = producer / relative
        if not path.is_file():
            problems.append('producer_tool_missing:' + relative)
            continue
        if flag not in path.read_text(encoding='utf-8'):
            problems.append('producer_tool_flag_missing:' + relative + ':' + flag)
    marker = producer / 'examples/apple/LegacySelfTest.swift'
    if marker.is_file() and spec.SELF_TEST_MINIMUM_MARKER not in marker.read_text(encoding='utf-8'):
        problems.append('producer_self_test_marker_missing')

    sdk_paths = {}
    for relative in spec.SDK_SOURCE_PATHS:
        producer_object = command_text('git', 'rev-parse', 'HEAD:' + relative, cwd=producer)
        sdk_object = command_text('git', 'rev-parse', spec.SDK_SHA + ':' + relative, cwd=producer)
        sdk_paths[relative] = {'producer': producer_object, 'sdk': sdk_object}
        if not producer_object or producer_object != sdk_object:
            problems.append('sdk_source_path:' + relative)

    entries = tree_entries(producer, spec.SDK_SHA)
    tree_findings = tree_problems(args.sdk_source.absolute(), entries)
    problems.extend(tree_findings)
    stage = stage_identity(args.stage.absolute())
    problems.extend(stage['problems'])
    sdk = {'source_sha': spec.SDK_SHA,
           'archive_sha256': spec.digest(args.archive) if args.archive and args.archive.is_file() else None,
           'archive_bytes': args.archive.stat().st_size if args.archive and args.archive.is_file() else None,
           'tree_files': len(entries),
           'paths': sdk_paths,
           'extracted_tree_problems': tree_findings,
           # The installed stage is where the version and ABI of this exact SDK
           # build become observable, so they are recorded in the SDK block that
           # the verifier reads (not only in the stage detail block).
           'version': stage['version'],
           'abi': stage['abi'],
           'package_version': stage['package_version'],
           'installed_libraries': [entry['name'] for entry in stage['libraries']]}
    identity = {
        'schema': 1,
        'verifier_sha': args.verifier_sha,
        'verifier_package': 'tests/reader_final_s03',
        'start_sha': spec.START_SHA,
        'producer': {'branch': spec.PRODUCER_BRANCH, 'detached_branch_name': branch,
                     'sha': head, 'expected_sha': spec.PRODUCER_SHA,
                     'seal_sha': spec.PRODUCER_SEAL_SHA, 'head': subject,
                     'run': spec.PRODUCER_RUN, 'run_attempt': spec.PRODUCER_RUN_ATTEMPT,
                     'jobs': spec.PRODUCER_JOBS, 'artifact': spec.PRODUCER_ARTIFACT,
                     'required_files': required},
        'sdk': sdk,
        'stage': stage,
        'runner': {
            'machine': command_text('uname', '-m') or platform.machine(),
            'platform': platform.platform(),
            'system_version': command_text('sw_vers', '-productVersion'),
            'xcode': command_text('xcodebuild', '-version').splitlines()[0]
            if command_text('xcodebuild', '-version') else '',
            'python': platform.python_version(),
            'cmake': command_text('cmake', '--version').splitlines()[0]
            if command_text('cmake', '--version') else '',
        },
        'problems': problems,
        'accepted': not problems,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(identity, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'accepted': identity['accepted'], 'producer_sha': head,
                      'sdk_source_sha': spec.SDK_SHA, 'sdk_tree_files': len(entries),
                      'runner': identity['runner']['machine'],
                      'problems': problems}, indent=2))
    return 0 if not problems else 1


if __name__ == '__main__':
    sys.exit(main())
