#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Sign SHA256SUMS, or Authenticode-sign Windows binaries before packaging."""
import argparse
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

from verify_artifacts import inventory, verify


def find_tool(name):
    found = shutil.which(name)
    if not found and name == 'gpg' and os.name == 'nt':
        bundled = Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'Git/usr/bin/gpg.exe'
        if bundled.is_file():
            found = str(bundled)
    return found


def gpg_path(path, executable):
    # Git for Windows ships an MSYS GPG: C:\\... and C:/... are relative paths
    # to it. Native Gpg4win and Unix GPG use the ordinary filesystem spelling.
    if os.name == 'nt' and Path(executable).with_name('msys-2.0.dll').is_file():
        cygpath = Path(executable).with_name('cygpath.exe')
        return subprocess.check_output([str(cygpath), '-u', str(path)], text=True).strip()
    return str(path)


def commands(args):
    backend = args.backend
    if backend == 'auto':
        backend = next((b for b in ('gpg', 'minisign') if find_tool(b)), 'sha256')
    root = args.directory.resolve()
    if backend == 'authenticode':
        binaries = [str(p) for p in inventory(root).values() if p.suffix.lower() in ('.dll', '.exe')]
        if not binaries:
            raise ValueError('no DLL/EXE artifacts to sign')
        if (root / 'SHA256SUMS').exists():
            raise ValueError('Authenticode signing must precede SHA256SUMS generation')
        tool = find_tool('signtool') or 'signtool'
        key = args.key or '<EV_OR_OV_CERTIFICATE_THUMBPRINT>'
        timestamp = args.timestamp_url or '<RFC3161_TIMESTAMP_URL>'
        result = [[tool, 'sign', '/sha1', key, '/fd', 'SHA256', '/tr', timestamp, '/td', 'SHA256', p]
                  for p in binaries]
        result += [[tool, 'verify', '/pa', '/all', '/v', p] for p in binaries]
        print('Authenticode requires an EV/OV code-signing certificate and its private key.')
        if not args.dry_run and (not args.key or not args.timestamp_url):
            raise ValueError('Authenticode needs --key certificate thumbprint and --timestamp-url')
    else:
        verify(root)
        sums = str(root / 'SHA256SUMS')
        if backend == 'sha256':
            print('UNSIGNED: publish SHA256SUMS with the packages and paste its hashes on the release page.')
            print((root / 'SHA256SUMS').read_text(encoding='utf-8'), end='')
            return []
        if not args.key and not args.dry_run:
            raise ValueError(f'{backend} requires an explicit --key; use --backend sha256 for an unsigned release')
        tool = find_tool(backend) or backend
        if backend == 'gpg':
            sums = gpg_path(root / 'SHA256SUMS', tool)
            prefix = [tool, '--batch']
            if args.gpg_homedir:
                prefix += ['--homedir', gpg_path(args.gpg_homedir.resolve(), tool)]
            result = [prefix + ['--armor', '--detach-sign', '--local-user', args.key or '<GPG_KEY_FINGERPRINT>',
                                '--output', sums + '.asc', sums]]
        else:
            result = [[tool, '-S', '-s', args.key or '<MINISIGN_SECRET_KEY>', '-m', sums, '-x', sums + '.minisig']]
    if not args.dry_run and not find_tool('signtool' if backend == 'authenticode' else backend):
        raise ValueError(f'{backend} executable not found')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--backend', choices=('auto', 'gpg', 'minisign', 'sha256', 'authenticode'), default='auto')
    parser.add_argument('--key', help='GPG fingerprint, minisign secret key path, or certificate thumbprint')
    parser.add_argument('--gpg-homedir', type=Path, help='isolated GPG keyring (optional)')
    parser.add_argument('--timestamp-url', help='Authenticode RFC3161 timestamp service')
    parser.add_argument('--dry-run', action='store_true', help='print commands without signing or creating keys')
    args = parser.parse_args()
    try:
        for command in commands(args):
            rendered = subprocess.list2cmdline(command) if os.name == 'nt' else shlex.join(command)
            print(('DRY-RUN: ' if args.dry_run else 'RUN: ') + rendered, flush=True)
            if not args.dry_run:
                subprocess.run(command, check=True)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f'FAIL: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
