"""Configure an isolated native performance build using local dependency sources."""
import os
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
toolchain = next((Path.home() / 'AppData/Local/Microsoft/WinGet/Packages').glob('BrechtSanders.WinLibs.*/mingw64/bin'))
os.environ['PATH'] = str(toolchain) + os.pathsep + os.environ['PATH']
build = root / 'build/l08-perf'
if '--archives' in sys.argv:
    # Fast local check: compile the changed engine and model against existing
    # native dependency archives; the default path builds the whole checkout.
    native = root.parent / 'exr-build-cf112'
    build.mkdir(parents=True, exist_ok=True)
    link = next(line.split('=', 1)[1].split() for line in
                (native / 'build.ninja').read_text().splitlines()
                if line.startswith('  LINK_LIBRARIES = libexr_base.a'))
    link = [str(native / p) if p.endswith('.a') else p for p in link]
    subprocess.run([str(toolchain / 'gcc.exe'), '-O3', '-DEXR_STATIC',
                    '-I' + str(root / 'include'),
                    '-I' + str(native / '_deps/freetype-src/include'),
                    str(root / 'tests/test_l08_reflow_perf.c'),
                    str(root / 'src/docx_reflow.c'), str(root / 'src/docx_edit.c'),
                    '-Wl,--start-group', *link, '-Wl,--end-group',
                    '-o', str(build / 'l08-local.exe')], check=True)
    subprocess.run([str(build / 'l08-local.exe'), str(root.parent / 'exr-build-main/Reader.otf')], check=True)
    sys.exit(0)
args = [str(toolchain / 'cmake.exe'), '-S', str(root), '-B', str(build), '-G', 'Ninja',
        '-DCMAKE_BUILD_TYPE=Release', '-DEXR_BUILD_TESTS=OFF',
        '-DCMAKE_PROJECT_INCLUDE=' + str(root / 'tests/l08_perf.cmake')]
for option in ['PDF', 'PDF_EDIT', 'PDF_CRYPTO', 'PDF_JPX', 'ICC', 'IMAGE_WEBP',
               'IMAGE_TIFF', 'IMAGE_AVIF', 'AUDIO', 'MP3', 'AAC', 'LIBRARY', 'LCP']:
    args.append('-DEXR_ENABLE_' + option + '=OFF')
args += ['-DEXR_BUILD_TEXT_INDEX=OFF', '-DEXR_BUILD_TOOLS=OFF']
deps = root.parent / 'exr-build-cf112/_deps'
for dep in deps.glob('*-src'):
    args.append('-DFETCHCONTENT_SOURCE_DIR_' + dep.name[:-4].upper() + '=' + str(dep))
subprocess.run(args, check=True)
subprocess.run([str(toolchain / 'cmake.exe'), '--build', str(build), '--target', 'exreader-l08-perf', '-j', '4'], check=True)
font = root.parent / 'exr-build-main/Reader.otf'
subprocess.run([str(build / 'exreader-l08-perf.exe'), str(font)], check=True)
