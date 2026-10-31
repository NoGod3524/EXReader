#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Reject a missing PDF core, leaked optional component, or invalid runtime."""
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from check_reading_profile import inspect


def main():
    root = Path(__file__).resolve().parents[1]
    cache = json.loads((root / 'CMakePresets.json').read_text())['configurePresets'][0]['cacheVariables']
    with tempfile.TemporaryDirectory() as name:
        directory = Path(name)
        package = directory / 'lib/cmake/EXReader'
        package.mkdir(parents=True)
        archive = directory / 'lib/libexr_pdf.a'
        archive.write_bytes(b'profile-validator-self-check-only')
        executable = directory / 'reading-document'
        executable.write_bytes(b'profile-validator-self-check-only')
        targets = package / 'EXReaderTargets.cmake'
        targets.write_text('add_library(EXReader::exr_core INTERFACE IMPORTED)\n'
                           'add_library(EXReader::exr_pdf STATIC IMPORTED)\n')
        cache_file = directory / 'CMakeCache.txt'

        def write_cache(values):
            cache_file.write_text(''.join(f'{key}:BOOL={value}\n' for key, value in values.items()))

        write_cache(cache)
        runtime = SimpleNamespace(returncode=0, stdout='libc.so.6 => /lib/libc.so.6\n', stderr='')
        with patch('check_reading_profile.subprocess.run', return_value=runtime):
            if not inspect('reading-core', directory, directory, executable)['accepted']:
                raise RuntimeError('Valid composition rejected')
            for key, value in [('EXR_ENABLE_PDF', 'OFF'), ('EXR_ENABLE_AUDIO', 'ON'),
                               ('EXR_ENABLE_LIBRARY', 'ON')]:
                write_cache(dict(cache, **{key: value}))
                if inspect('reading-core', directory, directory, executable)['accepted']:
                    raise RuntimeError(f'Invalid component selection accepted: {key}')
            write_cache(cache)
            for output in ['libwebkit2gtk.so => /lib/libwebkit2gtk.so', 'libm.so => not found',
                           'libsqlite3.so => /lib/libsqlite3.so']:
                runtime.stdout = output
                if inspect('reading-core', directory, directory, executable)['accepted']:
                    raise RuntimeError('Forbidden/unresolved runtime accepted')
            runtime.stdout = 'libc.so.6 => /lib/libc.so.6\n'
            targets.write_text('add_library(EXReader::exr_core INTERFACE IMPORTED)\n')
            if inspect('reading-core', directory, directory, executable)['accepted']:
                raise RuntimeError('Missing PDF target accepted')
    print(json.dumps({'validator_self_check': True, 'negative_cases': 7,
                      'reading_profile_accepted': False}))


if __name__ == '__main__':
    main()
