#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Offline protocol self-test for the S20 assemble/unpack contract.

It uses a synthetic payload laid out like the Linux delivery only; it never
touches a product build or a platform driver.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).absolute().parents[2]
ASSEMBLE = ROOT / 'tools' / 'reader_wave3_package' / 'assemble.py'
UNPACK = ROOT / 'tools' / 'reader_wave3_package' / 'unpack.py'
SOURCE = 'a' * 40
ENTRY = 'EXReader-Linux/bin/exreader-linux'
FONT = 'EXReader-Linux/Reader.otf'
TEXT = 'EXReader-Linux/sub/data.txt'


def run(argv, expect=0):
    process = subprocess.run([sys.executable, *map(str, argv)], capture_output=True, text=True)
    if process.returncode != expect:
        raise SystemExit('unexpected exit ' + str(process.returncode) + ' for ' + str(argv[1]) +
                         '\nstdout: ' + process.stdout[-2000:] + '\nstderr: ' + process.stderr[-2000:])
    return process


def main():
    checks = []
    workspace = Path(tempfile.mkdtemp(prefix='s20-selftest-'))
    try:
        payload = workspace / 'payload'
        (payload / 'EXReader-Linux' / 'bin').mkdir(parents=True)
        (payload / 'EXReader-Linux' / 'sub').mkdir()
        binary = payload / ENTRY
        binary.write_bytes(bytes(range(256)) * 40)
        os.chmod(binary, 0o755)
        (payload / FONT).write_bytes(bytes(range(128)) * 8)
        (payload / TEXT).write_text('\u4e2d\u6587 payload\n', encoding='utf-8')
        output = workspace / 'output'
        run([ASSEMBLE, '--target', 'linux', '--payload', payload, '--output', output,
             '--source-sha', SOURCE, '--sdk-version', '3.41.0'])
        checks.append('assemble')
        manifest = json.loads((output / 'manifest.json').read_text(encoding='utf-8'))
        archive = output / manifest['archive']['name']
        if not archive.is_file():
            raise SystemExit('archive was not created')
        if manifest['files'].get(ENTRY, {}).get('mode') != 0o755:
            raise SystemExit('executable mode was not recorded')
        if manifest['source_sha'] != SOURCE or manifest['target'] != 'linux' or manifest['entry'] != ENTRY:
            raise SystemExit('manifest identity is wrong')
        if (output / (archive.name + '.sha256')).read_text(encoding='utf-8').split()[0] != manifest['archive']['sha256']:
            raise SystemExit('published archive checksum differs')
        checks.append('manifest')
        with zipfile.ZipFile(archive) as bundle:
            names = set(bundle.namelist())
            sums = bundle.read('SHA256SUMS').decode('utf-8').splitlines()
        required = {ENTRY, FONT, TEXT, 'manifest.json', 'SHA256SUMS', '\u5b89\u88c5\u8bf4\u660e-\u4e2d\u6587.md'}
        if not required <= names:
            raise SystemExit('archive misses ' + str(sorted(required - names)))
        if len([line for line in sums if line.strip()]) != 4:
            raise SystemExit('SHA256SUMS does not cover the three payload files and the notes')
        checks.append('archive-inventory')
        unpacked = workspace / 'fresh'
        run([UNPACK, '--target', 'linux', '--archive', archive, '--manifest', output / 'manifest.json',
             '--into', unpacked, '--report', workspace / 'unpack.json'])
        report = json.loads((workspace / 'unpack.json').read_text(encoding='utf-8'))
        if report['files'] != len(manifest['files']) or report['checksums_checked'] != len(manifest['files']):
            raise SystemExit('unpack report counts differ')
        if report['entry'] != ENTRY or report['entry_sha256'] != manifest['files'][ENTRY]['sha256']:
            raise SystemExit('unpack report entry identity differs')
        if not os.access(unpacked / ENTRY, os.X_OK):
            raise SystemExit('unpacked executable lost its mode')
        if (unpacked / TEXT).read_text(encoding='utf-8') != '\u4e2d\u6587 payload\n':
            raise SystemExit('unpacked bytes differ')
        checks.append('unpack')
        run([UNPACK, '--target', 'linux', '--archive', archive, '--manifest', output / 'manifest.json',
             '--into', unpacked, '--report', workspace / 'repeat.json'], expect=1)
        checks.append('refuse-existing-destination')
        run([ASSEMBLE, '--target', 'linux', '--payload', payload, '--output', workspace / 'short',
             '--source-sha', 'abc'], expect=1)
        checks.append('refuse-short-source')
        altered = dict(manifest)
        altered['target'] = 'windows'
        changed = workspace / 'changed-manifest.json'
        changed.write_text(json.dumps(altered), encoding='utf-8')
        run([UNPACK, '--target', 'linux', '--archive', archive, '--manifest', changed,
             '--into', workspace / 'wrong-target', '--report', workspace / 'wrong.json'], expect=1)
        checks.append('refuse-wrong-target')
        (workspace / 'tampered').mkdir()
        tampered = workspace / 'tampered' / archive.name
        with zipfile.ZipFile(archive) as source_zip, zipfile.ZipFile(tampered, 'w', zipfile.ZIP_DEFLATED) as target_zip:
            for info in source_zip.infolist():
                data = source_zip.read(info)
                if info.filename == ENTRY:
                    data = bytes([data[0] ^ 0xFF]) + data[1:]
                target_zip.writestr(info, data)
        run([UNPACK, '--target', 'linux', '--archive', tampered, '--manifest', output / 'manifest.json',
             '--into', workspace / 'tampered-out', '--report', workspace / 'tampered.json'], expect=1)
        checks.append('refuse-tampered-archive')
        moved = dict(manifest)
        moved['files'] = dict(manifest['files'])
        moved['files'][ENTRY] = dict(moved['files'][ENTRY])
        moved['files'][ENTRY]['sha256'] = '0' * 64
        forged = workspace / 'forged-manifest.json'
        forged.write_text(json.dumps(moved), encoding='utf-8')
        run([UNPACK, '--target', 'linux', '--archive', archive, '--manifest', forged,
             '--into', workspace / 'forged-out', '--report', workspace / 'forged.json'], expect=1)
        checks.append('refuse-forged-digest')
        run([ASSEMBLE, '--target', 'linux', '--payload', payload, '--output', workspace / 'no-producer',
             '--source-sha', SOURCE, '--require-build-identity'], expect=1)
        producer = payload / 'build.json'
        producer.write_text(json.dumps({'source_sha': 'b' * 40, 'sdk_version': '3.41.0'}), encoding='utf-8')
        run([ASSEMBLE, '--target', 'linux', '--payload', payload, '--output', workspace / 'wrong-producer',
             '--source-sha', SOURCE, '--require-build-identity'], expect=1)
        producer.write_text(json.dumps({'source_sha': SOURCE, 'sdk_version': '3.40.0'}), encoding='utf-8')
        run([ASSEMBLE, '--target', 'linux', '--payload', payload, '--output', workspace / 'wrong-sdk',
             '--source-sha', SOURCE, '--require-build-identity'], expect=1)
        producer.write_text(json.dumps({'source_sha': SOURCE, 'sdk_version': '3.41.0'}), encoding='utf-8')
        run([ASSEMBLE, '--target', 'linux', '--payload', payload, '--output', workspace / 'producer',
             '--source-sha', SOURCE, '--require-build-identity'])
        produced = json.loads((workspace / 'producer/manifest.json').read_text(encoding='utf-8'))
        assert produced['producer']['source_sha'] == SOURCE
        assert produced['producer']['build_json_sha256'] == produced['files']['build.json']['sha256']
        checks.append('require-matching-platform-producer-source-and-sdk')
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
    print(json.dumps({'passed': True, 'checks': checks, 'count': len(checks)}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
