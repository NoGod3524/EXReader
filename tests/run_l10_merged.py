"""Build the actual Windows host acceptance using an existing static SDK build.

The unapproved UI integration is applied only to an isolated build copy.
No ctypes, HWND, GUI automation or input injection is used.
"""
from pathlib import Path
import argparse
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--sdk-build', required=True, type=Path)
parser.add_argument('--library-build', type=Path, help='Optional bookshelf/SQLite build when SDK omits library')
parser.add_argument('--integrated', action='store_true', help='Test checked-in UI without the pending patch')
args = parser.parse_args()
build = ROOT / 'build/l10'
build.mkdir(parents=True, exist_ok=True)


def run(command):
    result = subprocess.run([str(x) for x in command], cwd=ROOT, capture_output=True,
                            text=True, encoding='utf-8', errors='replace')
    with (build / 'build.log').open('a', encoding='utf-8') as log:
        log.write(subprocess.list2cmdline([str(x) for x in command]) + '\n' + result.stdout + result.stderr)
    if result.returncode:
        print((result.stdout + result.stderr)[-12000:])
        raise SystemExit(result.returncode)
    return result.stdout


overlay = build / 'overlay'
if args.integrated:
    source = ROOT
else:
    for folder in ('examples', 'src', 'include', 'tools'):
        shutil.copytree(ROOT / folder, overlay / folder, dirs_exist_ok=True)
    for name in ('shell_docedit_paint.inc', 'shell_docedit_table_history.inc'):
        file = overlay / 'examples/windows' / name
        file.write_text(file.read_text(encoding='utf-8'), encoding='utf-8', newline='\n')
    patch = build / 'integration.patch'
    patch.write_text((ROOT / 'examples/windows/l10-merged-integration.patch').read_text(encoding='utf-8'),
                     encoding='utf-8', newline='\n')
    run(['git', 'apply', '--directory=build/l10/overlay', patch])
    source = overlay
sdk = args.sdk_build.resolve()
libraries = sorted(sdk.glob('*.a')) + sorted((sdk / '_deps').rglob('*.a'))
if args.library_build:
    libraries += [args.library_build.resolve() / 'libexr_library.a']
    libraries += sorted(args.library_build.resolve().glob('*sqlite*.a'))
    libraries += sorted((args.library_build.resolve() / '_deps').rglob('*sqlite*.a'))
if not libraries:
    raise SystemExit(f'No static SDK libraries under {sdk}')
flags = ['-O0', '-UNDEBUG', '-DEXR_STATIC', '-DEXR_READER_WINDOWS_SHELL=1',
         '-ffunction-sections', '-fdata-sections', '-I' + str(ROOT / 'include')]
objects = []
sources = [ROOT / 'examples/windows/check_shell_docedit_merged_host.c', ROOT / 'src/docx_edit.c',
           ROOT / 'examples/windows/shell_d2d.cpp', ROOT / 'examples/windows/shell_epub.cpp',
           ROOT / 'examples/windows/shell_speech.cpp']
for file in sources:
    obj = build / (file.stem + '.o')
    extra = ['-DL10_READER_SOURCE="' + (source / 'examples/reader.c').as_posix() + '"'] if file == sources[0] else []
    print('Compiling', file.name, flush=True)
    run(['g++' if file.suffix == '.cpp' else 'gcc',
         '-std=c++17' if file.suffix == '.cpp' else '-std=c11', *flags, *extra, '-c', file, '-o', obj])
    objects.append(obj)
exe = build / 'check_l10_merged_host.exe'
print('Linking real host acceptance', flush=True)
run(['g++', '-static', '-Wl,--gc-sections', *objects, '-Wl,--start-group', *libraries,
     '-Wl,--end-group', '-lcomdlg32', '-lgdi32', '-luiautomationcore', '-lshell32', '-luser32',
     '-lwinhttp', '-lcrypt32', '-ld2d1', '-ldwrite', '-ladvapi32', '-lole32', '-loleaut32', '-luuid',
     '-lwinmm', '-lws2_32', '-lbcrypt', '-o', exe])
print(run([exe, ROOT, build]), end='', flush=True)
print('PASS' if args.integrated else 'PASS with pending UI integration applied in build copy only')
