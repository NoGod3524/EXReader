#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Offline protocol self-test for the S20 assemble/unpack contract.

It uses a synthetic payload only; it never touches a product build or a driver.
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
        (payload / 'sub').mkdir(parents=True)
        (payload / 'app.bin').write_bytes(bytes(range(256)) * 40)
        (payload / 'sub' / 'data.txt').write_text('\u4e2d\u6587 payload\n', encoding='utf-8')
        (payload / 'run.sh').write_text('#!/bin/sh\necho ok\n', encoding='utf-8')
        os.chmod(payload / 'run.sh', 0o755)
        output = workspace / 'output'
        run([ASSEMBLE, '--target', 'linux', '--payload', payload, '--output', output,
             '--source-sha', SOURCE, '--sdk-version', '3.41.0'])
        checks.append('assemble')
        manifest = json.loads((output / 'manifest.json').read_text(encoding='utf-8'))
        archive = output / manifest['archive']['name']
        if not archive.is_file():
            raise SystemExit('archive was not created')
        if manifest['files'].get('run.sh', {}).get('mode') != 0o755:
            raise SystemExit('executable mode was not recorded')
        if manifest['source_sha'] != SOURCE or manifest['target'] != 'linux':
            raise SystemExit('manifest identity is wrong')
        checks.append('manifest')
        with zipfile.ZipFile(archive) as bundle:
            names = set(bundle.namelist())
        required = {'app.bin', 'sub/data.txt', 'run.sh', 'manifest.json', 'SHA256SUMS',
                    '\u5b89\u88c5\u8bf4\u660e-\u4e2d\u6587.md'}
        if not required <= names:
            raise SystemExit('archive misses ' + str(sorted(required - names)))
        checks.append('archive-inventory')
        unpacked = workspace / 'fresh'
        run([UNPACK, '--target', 'linux', '--archive', archive, '--manifest', output / 'manifest.json',
             '--into', unpacked, '--report', workspace / 'unpack.json'])
        report = json.loads((workspace / 'unpack.json').read_text(encoding='utf-8'))
        if report['files'] != len(manifest['files']) or report['checksums_checked'] != len(manifest['files']):
            raise SystemExit('unpack report counts differ')
        if not os.access(unpacked / 'run.sh', os.X_OK):
            raise SystemExit('unpacked executable lost its mode')
        if (unpacked / 'sub' / 'data.txt').read_text(encoding='utf-8') != '\u4e2d\u6587 payload\n':
            raise SystemExit('unpacked bytes differ')
        checks.append('unpack')
        run([UNPACK, '--target', 'linux', '--archive', archive, '--manifest', output / 'manifest.json',
             '--into', unpacked, '--report', workspace / 'repeat.json'], expect=1)
        checks.append('refuse-existing-destination')
        run([ASSEMBLE, '--target', 'linux', '--payload', payload, '--output', workspace / 'short',
             '--source-sha', 'abc'], expect=1)
        checks.append('refuse-short-source')
        changed = workspace / 'changed-manifest.json'
        altered = dict(manifest)
        altered['target'] = 'windows'
        changed.write_text(json.dumps(altered), encoding='utf-8')
        run([UNPACK, '--target', 'linux', '--archive', archive, '--manifest', changed,
             '--into', workspace / 'wrong-target', '--report', workspace / 'wrong.json'], expect=1)
        checks.append('refuse-wrong-target')
        tampered = workspace / 'tampered.zip'
        with zipfile.ZipFile(archive) as source_zip, zipfile.ZipFile(tampered, 'w', zipfile.ZIP_DEFLATED) as target_zip:
            for info in source_zip.infolist():
                data = source_zip.read(info)
                if info.filename == 'app.bin':
                    data = bytes([data[0] ^ 0xFF]) + data[1:]
                target_zip.writestr(info, data)
        run([UNPACK, '--target', 'linux', '--archive', tampered, '--manifest', output / 'manifest.json',
             '--into', workspace / 'tampered', '--report', workspace / 'tampered.json'], expect=1)
        checks.append('refuse-tampered-archive')
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
    print(json.dumps({'passed': True, 'checks': checks, 'count': len(checks)}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
