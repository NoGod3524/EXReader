#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Release trust-boundary checks; fixture bytes are not SDK build evidence."""
import argparse
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/release'))
from verify_artifacts import digest, verify, write_sums
from sign_artifacts import commands


def main():
    checks = []
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary).resolve()
        (root / 'bin').mkdir()
        binary = root / 'bin/example file.dll'
        binary.write_bytes(b'fixture\x00')
        (root / 'SDK.tar.gz').write_bytes(b'package fixture')
        write_sums(root)
        assert verify(root) == 2
        sums = (root / 'SHA256SUMS').read_bytes()
        checks.append('nested-path-and-spaces')

        def reject(name):
            process = subprocess.run([sys.executable, str(ROOT / 'tools/release/verify_artifacts.py'), str(root)],
                                     capture_output=True, text=True)
            assert process.returncode == 1 and 'FAIL:' in process.stderr, process
            checks.append(name)

        binary.write_bytes(b'tampered')
        reject('tampered-file')
        binary.write_bytes(b'fixture\x00')
        (root / 'extra.dll').write_bytes(b'extra')
        reject('unlisted-file')
        (root / 'extra.dll').unlink()
        binary.unlink()
        reject('missing-file')
        binary.write_bytes(b'fixture\x00')
        for name, raw in (
            ('empty-manifest', b''),
            ('malformed-hash', b'BAD  SDK.tar.gz\n'),
            ('duplicate-entry', sums + sums),
            ('parent-traversal', b'0' * 64 + b'  ../escape\n'),
            ('absolute-path', b'0' * 64 + b'  /escape\n'),
            ('windows-drive', b'0' * 64 + b'  C:/escape\n'),
            ('backslash-path', b'0' * 64 + b'  bin\\escape\n'),
            ('case-alias', sums + b'0' * 64 + b'  sdk.tar.gz\n'),
            ('self-checksum', sums + b'0' * 64 + b'  SHA256SUMS\n'),
        ):
            (root / 'SHA256SUMS').write_bytes(raw)
            reject(name)
        (root / 'SHA256SUMS').write_bytes(sums)
        (root / 'SHA256SUMS.asc').write_bytes(b'fixture signature')
        assert verify(root) == 2
        try:
            write_sums(root)
        except ValueError:
            checks.append('refuse-stale-signature')
        else:
            raise AssertionError('overwrote signed checksums')
        (root / 'SHA256SUMS.asc').unlink()
        for backend in ('gpg', 'minisign', 'authenticode', 'sha256', 'auto'):
            args = argparse.Namespace(directory=root, backend=backend, key=None,
                                      timestamp_url=None, dry_run=True, gpg_homedir=None)
            if backend == 'authenticode':
                (root / 'SHA256SUMS').unlink()
            with patch('sign_artifacts.find_tool', return_value=None), contextlib.redirect_stdout(io.StringIO()):
                rendered = commands(args)
            if backend == 'gpg':
                assert '--detach-sign' in rendered[0] and str(root / 'SHA256SUMS') == rendered[0][-1]
            elif backend == 'minisign':
                assert '-S' in rendered[0] and '-m' in rendered[0]
            elif backend == 'authenticode':
                assert '/fd' in rendered[0] and '/td' in rendered[0] and '/tr' in rendered[0]
                assert 'verify' in rendered[-1]
                (root / 'SHA256SUMS').write_bytes(sums)
            else:
                assert rendered == []
            checks.append(backend + '-dry-run')
        args.backend, args.dry_run = 'gpg', False
        try:
            commands(args)
        except ValueError:
            checks.append('refuse-implicit-signing-key')
        else:
            raise AssertionError('selected an implicit private key')

        # The production candidate sealer must carry checksums automatically.
        sys.path.insert(0, str(ROOT / 'tools'))
        from reading_release import seal
        stage = root / 'stage'
        stage.mkdir()
        (stage / 'fixture.dll').write_bytes(b'fixture')
        candidate = root / 'candidate'
        seal(stage, candidate, 'reading-core', 'a' * 40, {'sdk_version': '3.42.0'},
             {'RUNNER_OS': 'Windows', 'RUNNER_ARCH': 'X64'}, 1000, 'Windows', 'X64')
        assert verify(candidate) == 3
        checks.append('candidate-automatically-includes-checksums')
        from build_manifest import fingerprint, source_inputs, tree
        from reproduce import package
        snapshot = tree(stage)
        first, second = root / 'first.tar.gz', root / 'second.tar.gz'
        package(stage, first, 1000)
        os.utime(stage / 'fixture.dll', (2000, 2000))
        package(stage, second, 1000)
        assert digest(first) == digest(second) and tree(stage) == snapshot
        (stage / 'fixture.dll').write_bytes(b'changed')
        assert tree(stage) != snapshot
        checks.append('package-ignores-mtime-input-fingerprint-detects-content')
        (stage / 'builds').mkdir()
        compiler_input = stage / 'builds/input.c'
        compiler_input.write_bytes(b'before')
        snapshot = tree(stage)
        compiler_input.write_bytes(b'after')
        assert tree(stage) != snapshot
        checks.append('dependency-builds-source-directory-is-fingerprinted')
        # Progress written during a build must not change the input snapshot.
        for name in ('OUT.txt', 'SIGN-OUT.txt', 'bin/OUT.txt', 'OUT.txt.c'):
            (root / name).write_bytes(b'progress or source')
        with patch('build_manifest.output', return_value='OUT.txt\0SIGN-OUT.txt\0bin/OUT.txt\0OUT.txt.c\0'):
            assert source_inputs(root) == fingerprint(root, ['bin/OUT.txt', 'OUT.txt.c'])
        checks.append('only-root-progress-logs-excluded-from-build-inputs')
    print(json.dumps({'passed': len(checks), 'checks': checks}))


if __name__ == '__main__':
    main()
