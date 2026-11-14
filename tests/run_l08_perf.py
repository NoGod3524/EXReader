"""Build this checkout and run the native L08 benchmark (no GUI or ctypes)."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--build-dir', type=Path, default=root / 'build/l08-perf')
parser.add_argument('--deps', type=Path, help='optional FetchContent cache containing *-src directories')
parser.add_argument('--font', type=Path, default=root / 'tests/fixtures/fonts/primary.ttf')
options = parser.parse_args()
build = options.build_dir.resolve()
if not shutil.which('cmake') or not shutil.which('ninja'):
    candidates = (Path.home() / 'AppData/Local/Microsoft/WinGet/Packages').glob('BrechtSanders.WinLibs.*/mingw64/bin')
    toolchain = next(candidates)
    os.environ['PATH'] = str(toolchain) + os.pathsep + os.environ['PATH']
args = ['cmake', '-S', str(root), '-B', str(build), '-G', 'Ninja',
        '-DCMAKE_BUILD_TYPE=Release', '-DEXR_BUILD_TESTS=OFF',
        '-DCMAKE_PROJECT_INCLUDE=' + str(root / 'tests/l08_perf.cmake')]
for option in ['PDF', 'PDF_EDIT', 'PDF_CRYPTO', 'PDF_JPX', 'ICC', 'IMAGE_WEBP',
               'IMAGE_TIFF', 'IMAGE_AVIF', 'AUDIO', 'MP3', 'AAC', 'LIBRARY', 'LCP']:
    args.append('-DEXR_ENABLE_' + option + '=OFF')
args += ['-DEXR_BUILD_TEXT_INDEX=OFF', '-DEXR_BUILD_TOOLS=OFF']
if options.deps:
    for dep in options.deps.resolve().glob('*-src'):
        args.append('-DFETCHCONTENT_SOURCE_DIR_' + dep.name[:-4].upper() + '=' + str(dep))
subprocess.run(args, check=True)
subprocess.run(['cmake', '--build', str(build), '--target', 'exreader-l08-perf', '-j', '4'], check=True)
exe = build / ('exreader-l08-perf.exe' if os.name == 'nt' else 'exreader-l08-perf')
subprocess.run([str(exe), str(options.font.resolve())], check=True)
