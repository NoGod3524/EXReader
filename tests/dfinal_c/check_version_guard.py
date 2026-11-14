# SPDX-License-Identifier: MIT
"""Exercise the installed raw guard with literal/aliased SDK versions and refusals."""
import argparse
from pathlib import Path
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prefixes', required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='raw-version-guard-') as directory:
        root = Path(directory)
        for name, base, version, accepted in [
            ('old-literal', '#define EXR_VERSION "3.42.0"\n', None, True),
            ('current-alias', '#include <exr/version.h>\n#define EXR_VERSION EXR_SDK_VERSION\n', '3.42.0', True),
            ('wrong-version', '#include <exr/version.h>\n#define EXR_VERSION EXR_SDK_VERSION\n', '3.41.0', False),
            ('missing-version', '#include <exr/version.h>\n#define EXR_VERSION EXR_SDK_VERSION\n', None, False),
            ('missing-include', '#define EXR_VERSION EXR_SDK_VERSION\n', '3.42.0', False),
        ]:
            source = root / name
            prefix = source / 'prefix'
            (prefix / 'include/exr').mkdir(parents=True)
            (prefix / 'lib/cmake/Test').mkdir(parents=True)
            (prefix / 'lib/probe.a').write_bytes(b'')
            (prefix / 'include/exr/base.h').write_text(base, encoding='utf-8')
            if version:
                (prefix / 'include/exr/version.h').write_text(f'#define EXR_SDK_VERSION "{version}"\n', encoding='utf-8')
            (source / 'CMakeLists.txt').write_text('''cmake_minimum_required(VERSION 3.24)
project(RawGuard LANGUAGES C)
find_package(EXReaderRevisions 0.4.0 EXACT CONFIG REQUIRED)
add_library(guard_probe STATIC IMPORTED)
set_target_properties(guard_probe PROPERTIES
  IMPORTED_LOCATION "${CMAKE_CURRENT_SOURCE_DIR}/prefix/lib/probe.a"
  INTERFACE_INCLUDE_DIRECTORIES "${CMAKE_CURRENT_SOURCE_DIR}/prefix/include")
_exr_raw_guard_target(guard_probe "${CMAKE_CURRENT_SOURCE_DIR}/prefix/lib/cmake/Test"
  exr/base.h EXR_VERSION "3.42.0" FALSE)
''', encoding='utf-8')
            run = subprocess.run(['cmake', '-S', str(source), '-B', str(source / 'build'),
                                  '-DCMAKE_PREFIX_PATH=' + args.prefixes], capture_output=True, text=True)
            if (run.returncode == 0) != accepted or (not accepted and 'header version mismatch' not in run.stdout + run.stderr):
                raise AssertionError((name, run.returncode, run.stdout, run.stderr))
            print(f'{name}: {"accepted" if accepted else "rejected at version guard"}', flush=True)
    print('5 installed SDK version guard checks passed')


if __name__ == '__main__':
    main()
