#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Seal installed reading SDK candidates in CI; never publish a tag or release."""
import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import tarfile
import xml.etree.ElementTree as ET

PROFILES = ('reading-core', 'reading-library')
TESTS = {'installed-core', 'installed-chapter', 'installed-convert'}


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def load(path):
    value = json.loads(Path(path).read_text(encoding='utf-8'))
    require(isinstance(value, dict), 'report must be an object: ' + str(path))
    return value


def version(header):
    text = Path(header).read_text(encoding='utf-8')
    sdk = re.search(r'^#define EXR_VERSION "([0-9]+\.[0-9]+\.[0-9]+)"$', text, re.M)
    abi = re.search(r'^#define EXR_ABI_VERSION ([0-9]+)u?$', text, re.M)
    require(sdk and abi, 'installed SDK version/ABI declaration missing')
    return sdk[1], int(abi[1])


def check_profile(profile, source, stage, evidence, runtime, database=None):
    require(profile in PROFILES, 'unknown reading profile')
    stage, evidence = Path(stage), Path(evidence)
    composition = load(evidence / 'profile.json')
    licenses = load(evidence / 'licenses.json')
    smoke = load(evidence / 'corpus/summary.json')
    for name, report in [('composition', composition), ('licenses', licenses), ('smoke', smoke)]:
        require(report.get('source_sha') == source, name + ': source mismatch')
    require(composition.get('profile') == profile and composition.get('accepted') is True and
            composition.get('problems') == [], 'composition did not strictly accept the profile')
    inventory = composition.get('files', [])
    actual = {p.relative_to(stage).as_posix() for p in stage.rglob('*') if p.is_file()}
    require(inventory and len({f['path'] for f in inventory}) == len(inventory) and
            {f['path'] for f in inventory} == actual, 'composition inventory differs from installed stage')
    for entry in inventory:
        path = stage / entry['path']
        require(path.resolve().is_relative_to(stage.resolve()) and not path.is_symlink() and
                path.stat().st_size == entry['bytes'] and digest(path) == entry['sha256'],
                'installed stage changed after composition check')
    require(licenses.get('profile') == profile and licenses.get('materials_check_passed') is True and
            licenses.get('release_ready') is True and licenses.get('failures') == [] and
            licenses.get('pending') == [] and licenses.get('mandatory_missing') == [],
            'release license materials incomplete')
    require(smoke.get('accepted') is True and smoke.get('source_dirty') is False and
            smoke.get('identities_unchanged') is True and len(smoke.get('results', [])) == 9,
            'complete unchanged nine-format smoke missing')
    suite = ET.parse(evidence / 'consumer-tests.xml').getroot()
    cases = suite.findall('.//testcase')
    names = [case.get('name') for case in cases]
    expected = TESTS | ({'installed-library', 'installed-library-source'} if profile == 'reading-library' else set())
    require(len(names) == len(expected) and set(names) == expected and
            all(not any(case.find(tag) is not None for tag in ('failure', 'error', 'skipped')) for case in cases),
            'installed consumer missing, duplicated, failed or skipped')
    observed = load(runtime)
    sdk, abi = version(stage / 'include/exr/base.h')
    require(observed.get('sdk_version') == sdk and observed.get('abi') == abi,
            'loaded SDK differs from installed headers')
    schema = None
    if profile == 'reading-library':
        require(database is not None and Path(database).is_file(), 'SDK-created library database missing')
        with sqlite3.connect(Path(database).resolve().as_uri() + '?mode=ro', uri=True) as connection:
            schema = connection.execute('PRAGMA user_version').fetchone()[0]
            app_id = connection.execute('PRAGMA application_id').fetchone()[0]
        require(schema == 7 and app_id == 1163416131, 'loaded library schema/application identity mismatch')
        header = (stage / 'include/exr/library.h').read_text(encoding='utf-8')
        declared = re.search(r'^#define EXR_LIBRARY_VERSION "([^"]+)"$', header, re.M)
        require(declared and declared[1] == observed.get('library_header_version'), 'library header identity mismatch')
    else:
        require(observed.get('library_header_version') is None, 'core candidate includes an unexpected library')
    for name in ('LICENSE', 'THIRD_PARTY_NOTICES.md'):
        require((stage / name).is_file() and (stage / name).stat().st_size > 0, 'missing root license material: ' + name)
    return {'sdk_version': sdk, 'abi': abi, 'library_schema': schema,
            'library_header_version': observed.get('library_header_version')}


def seal(stage, output, profile, source, identity, ci, epoch):
    """Deterministic file-only archive. Symlinks are rejected instead of followed."""
    stage, output = Path(stage).resolve(strict=True), Path(output)
    require(not output.exists(), 'candidate output already exists')
    files = []
    for path in sorted(stage.rglob('*')):
        require(not path.is_symlink() and path.resolve().is_relative_to(stage), 'stage symlink/path escape')
        if path.is_file():
            files.append({'path': path.relative_to(stage).as_posix(), 'bytes': path.stat().st_size,
                          'sha256': digest(path), 'executable': bool(path.stat().st_mode & 0o111)})
    require(files, 'empty installed stage')
    require(not (stage / 'release-manifest.json').exists(), 'stage contains reserved release manifest')
    manifest = {'schema': 1, 'scope': 'installed reading SDK candidate; quality gates required before release',
                'source_sha': source, 'profile': profile, 'ci': ci, 'identity': identity,
                'files': files, 'published': False}
    raw = (json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + '\n').encode()
    output.mkdir(parents=True)
    (output / 'release-manifest.json').write_bytes(raw)
    prefix = 'EXReader-' + profile + '-' + identity['sdk_version']
    archive = output / (prefix + '.tar.gz')
    with archive.open('xb') as destination, gzip.GzipFile(fileobj=destination, filename='', mtime=epoch) as compressed:
        with tarfile.open(fileobj=compressed, mode='w') as tar:
            for entry in files + [{'path': 'release-manifest.json', 'bytes': len(raw), 'executable': False}]:
                payload = raw if entry['path'] == 'release-manifest.json' else (stage / entry['path']).read_bytes()
                if entry['path'] != 'release-manifest.json':
                    require(hashlib.sha256(payload).hexdigest() == entry['sha256'], 'stage changed during packaging')
                info = tarfile.TarInfo(prefix + '/' + entry['path'])
                info.size, info.mtime, info.mode = len(payload), epoch, 0o755 if entry['executable'] else 0o644
                tar.addfile(info, io.BytesIO(payload))
    record = {'schema': 1, 'accepted': True, 'source_sha': source, 'profile': profile, 'ci': ci,
              'identity': identity, 'archive': archive.name, 'bytes': archive.stat().st_size,
              'sha256': digest(archive), 'manifest_sha256': hashlib.sha256(raw).hexdigest(),
              'file_count': len(files), 'published': False, 'quality_accepted': False}
    (output / 'candidate.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', choices=PROFILES, required=True)
    parser.add_argument('--stage', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--database', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'SDK release candidates are prepared only in cloud CI')
    source = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    require(source == os.environ.get('GITHUB_SHA'), 'checkout and workflow source differ')
    require(subprocess.run(['git', 'diff', '--quiet', 'HEAD']).returncode == 0, 'tracked source changed during build')
    identity = check_profile(args.profile, source, args.stage, args.evidence, args.runtime, args.database)
    require(identity['sdk_version'] == version(Path('include/exr/base.h'))[0], 'source and installed versions differ')
    ci = {name: os.environ[name] for name in ('GITHUB_REPOSITORY', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT', 'GITHUB_JOB')}
    epoch = int(subprocess.check_output(['git', 'show', '-s', '--format=%ct', 'HEAD'], text=True))
    print(json.dumps(seal(args.stage, args.output, args.profile, source, identity, ci, epoch)))


if __name__ == '__main__':
    main()
