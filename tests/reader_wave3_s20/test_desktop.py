#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actions-only relocation checks for the Linux user launcher and dependency refusal."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).absolute().parents[2]
sys.path.insert(0, str(ROOT / 'tools/reader_wave3_package'))
import desktop


def refuses(call):
    try:
        call()
    except ValueError:
        return
    raise AssertionError('unsafe runtime dependency was accepted')


def main():
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise SystemExit('run desktop protocol checks in GitHub Actions only')
    with tempfile.TemporaryDirectory(prefix='s20 desktop ') as temporary:
        root = Path(temporary)
        payload = root / 'payload with spaces'
        binary = payload / 'EXReader-Linux/bin/exreader-linux'
        binary.parent.mkdir(parents=True)
        binary.write_text('#!/bin/sh\nprintf "argc=%s\\n" "$#"\n', encoding='utf-8')
        binary.chmod(0o755)
        desktop.prepare('linux', payload)
        env = dict(os.environ, XDG_DATA_HOME=str(root / 'user data'),
                   XDG_STATE_HOME=str(root / 'user state'))
        launcher = payload / 'EXReader-Linux/Start-EXReader.sh'
        result = subprocess.check_output([str(launcher)], cwd=root, env=env, text=True)
        assert result == "argc=0\n", result
        refuses(lambda: desktop.linux_dependencies('libexreader.so => not found\n', payload))
        refuses(lambda: desktop.linux_dependencies('libx.so => /build/sdk/libx.so (0x123)\n', payload))
        assert desktop.linux_dependencies('libc.so.6 => /usr/lib/libc.so.6 (0x123)\n', payload)
        frameworks = root / 'Frameworks'
        frameworks.mkdir()
        (frameworks / 'libexreader.dylib').write_bytes(b'runtime')
        assert desktop.macos_dependencies('app:\n @rpath/libexreader.dylib (compatibility version 1)\n', frameworks)
        refuses(lambda: desktop.macos_dependencies('app:\n /build/sdk/libexreader.dylib (version 1)\n', frameworks))
        system = root / 'System32'
        system.mkdir()
        (system / 'KERNEL32.dll').write_bytes(b'OS')
        assert desktop.windows_dependencies('    KERNEL32.dll\n', root, system)
        refuses(lambda: desktop.windows_dependencies('    missing.dll\n', root, system))
    print('desktop relocation launcher and missing/external dependency checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

