# SPDX-License-Identifier: MIT
"""Build current-source optional modules against an installed SDK, then run CTest."""
import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', required=True, type=Path)
    parser.add_argument('--build', required=True, type=Path)
    parser.add_argument('--sqlite-source', type=Path, help='Optional existing pinned SQLite source cache')
    args = parser.parse_args()
    work, sdk = args.build.resolve(), args.sdk.resolve()
    stage = work / 'stage'

    def run(*command):
        print('RUN', *map(str, command), flush=True)
        subprocess.run(list(map(str, command)), cwd=ROOT, check=True)

    common = ['-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release', f'-DCMAKE_INSTALL_PREFIX={stage}',
              f'-DCMAKE_PREFIX_PATH={stage};{sdk}', f'-DREADER_PRODUCT_PREFIX={stage}',
              f'-DEXR_SDK={sdk}', '-DEXR_READER_SELECTOR_BYTES_CANDIDATE=ON',
              '-DREADER_ANNOTATION_IMPORT_BUILD=ON']
    for name, source in [('product', 'apps/reader/store/native'), ('revisions', 'apps/reader/revisions'),
                         ('reading-state', 'apps/reader/reading-state'),
                         ('export', 'apps/reader/annotation-export'), ('import', 'apps/reader/annotation-import')]:
        extra = ([f'-DFETCHCONTENT_SOURCE_DIR_READER_CATALOG_SQLITE_SOURCE={args.sqlite_source.resolve()}']
                 if name == 'product' and args.sqlite_source else [])
        run('cmake', '-S', source, '-B', work / name, *common, *extra)
        run('cmake', '--build', work / name, '--parallel', '4')
        run('cmake', '--install', work / name)
    run('cmake', '-S', 'tests/dfinal_c', '-B', work / 'consumer', *common,
        f'-DPython3_EXECUTABLE={sys.executable}')
    run('cmake', '--build', work / 'consumer', '--parallel', '4')
    run('ctest', '--test-dir', work / 'consumer', '-V', '--no-tests=error',
        '--output-junit', work / 'model-tests.xml')


if __name__ == '__main__':
    main()
