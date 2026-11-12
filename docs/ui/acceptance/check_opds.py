#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Headless OPDS acceptance. Usage: check_opds.py CHECK_SHELL_OPDS_EXE OUTPUT.
Only the console probe is allowed; the production host is never launched.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('probe', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--timeout-only', action='store_true')
    args = parser.parse_args()
    probe = args.probe.resolve(strict=True)
    if probe.name.lower() not in ('check_shell_opds.exe', 'check_shell_opds'):
        parser.error('expected the check_shell_opds console executable')
    args.output.mkdir(parents=True, exist_ok=True)
    root = '--timeout-test' if args.timeout_only else 'https://www.gutenberg.org/ebooks.opds/'
    result = subprocess.run([str(probe), root, str(args.output.resolve())], timeout=300,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
                            capture_output=True, text=True, encoding='utf-8', errors='replace')
    print(result.stdout, end='')
    print(result.stderr, end='')
    report = json.loads((args.output / 'opds-net.json').read_text(encoding='utf-8'))
    checks = [c for c in report['checks'] if c['check'] != 'end']
    passed = sum(c['pass'] for c in checks)
    print(f'{passed}/{len(checks)} console checks passed', flush=True)
    return result.returncode or int(passed != len(checks))


if __name__ == '__main__':
    raise SystemExit(main())
