#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Verify a real installed Windows host package and reject absent inputs."""
import argparse
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--package', type=Path, required=True)
    args = parser.parse_args()
    sdk, binary = args.sdk.absolute(), args.binary.absolute()
    include = sdk / 'apps/reader/desktop/windows_accessibility.inc'
    assert binary.is_file(), f'EXPECTED built exe at {binary}; got nothing'
    assert include.is_file(), f'EXPECTED installed windows_accessibility.inc at {include}; got nothing'
    assert (args.package / 'EXReader-Windows.zip').is_file(), 'real Windows package ZIP missing'
    print(f'PASS: real package exists; exe={binary}; installed include={include}')
    tool = Path(__file__).resolve().parents[1] / 'tools/build_windows_host.py'
    command = [sys.executable, str(tool), '--sdk', str(sdk), '--binary', str(binary), '--output', str(args.package) + '-negative']
    original = include.read_bytes()
    try:
        include.unlink()
        result = subprocess.run(command, capture_output=True, text=True)
        output = result.stdout + result.stderr
        print(output, end='')
        assert result.returncode != 0, 'control did not fail: missing staged include accepted'
        assert f'EXPECTED installed windows_accessibility.inc at {include}; got nothing' in output, output
        print(f'PASS: missing staged include rejected; actual_exit={result.returncode}')
    finally:
        include.write_bytes(original)
    missing = binary.with_name('deliberately-missing-reader.exe')
    assert not missing.exists()
    command[command.index('--binary') + 1] = str(missing)
    result = subprocess.run(command, capture_output=True, text=True)
    output = result.stdout + result.stderr
    print(output, end='')
    assert result.returncode != 0 and f'EXPECTED built exe at {missing}; got nothing' in output, output
    print(f'PASS: missing exe rejected; actual_exit={result.returncode}')


if __name__ == '__main__':
    main()
