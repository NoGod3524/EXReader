#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Test absence versus path errors using the production helper."""
import argparse
import os
from pathlib import Path
import subprocess


def state(probe, path):
    p = subprocess.run([probe, str(path)], capture_output=True, text=True, check=True)
    return int(p.stdout)


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    parser = argparse.ArgumentParser()
    parser.add_argument('--probe', required=True)
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=False)
    existing = args.work / 'file'
    existing.write_text('x', encoding='utf-8')
    assert state(args.probe, existing) == 1
    assert state(args.probe, args.work / 'missing') == 0
    assert state(args.probe, existing / 'child') == -1
    if os.name != 'nt':
        broken = args.work / 'dangling'
        broken.symlink_to('absent')
        assert state(args.probe, broken) == 1
        if os.geteuid() != 0:
            blocked = args.work / 'blocked'
            blocked.mkdir()
            blocked.chmod(0)
            try:
                assert state(args.probe, blocked / 'file') == -1
            finally:
                blocked.chmod(0o700)
    print('path state: present, absent, path component and applicable permissions/symlink checks passed')


if __name__ == '__main__':
    main()
