"""Build/run the real Windows host in an isolated integration overlay.

Existing worktree files are never changed. The integration diff is reviewable
at examples/windows/l11_save_integration.patch until L11's file scope is approved.
No ctypes tests are introduced, so no ASan preload registration is needed.
"""
from pathlib import Path
import argparse
import difflib
import json
import shutil
import subprocess

root = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser()
parser.add_argument('--sdk', type=Path, required=True)
args = parser.parse_args()
build = root / 'build/l11-save'
overlay = build / 'source'
overlay.mkdir(parents=True, exist_ok=True)
for folder in ['examples', 'apps']:
    shutil.copytree(root / folder, overlay / folder, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('*.png', '*.jpg', '*.bmp', '*.docx', '*.pdf', '*.epub'))
(overlay / 'tools').mkdir(exist_ok=True)
for name in ['convert_json.c', 'convert_json.h']:
    shutil.copy2(root / 'tools' / name, overlay / 'tools' / name)
changes = {}
name = 'examples/windows/shell_docedit.inc'
source = (root / name).read_text(encoding='utf-8')
start = source.index('static int de_save(void) {')
end = source.index('static int de_open(', start)
changes[name] = source[:start] + '#include "shell_docedit_save.inc"\n' + source[end:]
name = 'examples/windows/shell_docedit_input.inc'
source = (root / name).read_text(encoding='utf-8')
old = "if(key=='S') {de_save();return 1;}"
assert source.count(old) == 1
changes[name] = source.replace(old, "if(key=='S') {if(shift)de_save_as(NULL);else de_save();return 1;}")
patch = []
for name, changed in changes.items():
    original = (root / name).read_text(encoding='utf-8')
    patch.extend(difflib.unified_diff(original.splitlines(True), changed.splitlines(True),
                                    fromfile='a/' + name, tofile='b/' + name))
    (overlay / name).write_text(changed, encoding='utf-8', newline='\n')
(root / 'examples/windows/l11_save_integration.patch').write_text(''.join(patch), encoding='utf-8', newline='\n')
cmake = overlay / 'examples/windows/CMakeLists.txt'
with cmake.open('a', encoding='utf-8') as out:
    out.write('''
add_executable(check_shell_docedit_save check_shell_docedit_save.c shell_d2d.cpp shell_epub.cpp shell_speech.cpp)
target_compile_features(check_shell_docedit_save PRIVATE cxx_std_17)
target_compile_definitions(check_shell_docedit_save PRIVATE EXR_READER_WINDOWS_SHELL=1)
target_compile_options(check_shell_docedit_save PRIVATE -UNDEBUG -finput-charset=UTF-8)
target_link_libraries(check_shell_docedit_save PRIVATE EXReader::exreader comdlg32 gdi32 uiautomationcore shell32 user32 winhttp crypt32 d2d1 dwrite advapi32 ole32 uuid EXReader::vendor_miniz EXReader::vendor_expat m)
target_link_options(check_shell_docedit_save PRIVATE -static)
''')
def run(command):
    print('+', subprocess.list2cmdline(list(map(str, command))), flush=True)
    subprocess.run(list(map(str, command)), cwd=root, check=True)

run(['cmake', '-S', cmake.parent, '-B', build / 'host', '-G', 'Ninja',
     '-DCMAKE_BUILD_TYPE=Release', '-DEXR_SDK=' + args.sdk.resolve().as_posix()])
run(['cmake', '--build', build / 'host', '--target', 'check_shell_docedit_save', '-j', '2'])
for dll in (args.sdk / 'bin').glob('*.dll'):
    shutil.copy2(dll, build / 'host' / dll.name)
evidence = build / 'evidence'
evidence.mkdir(exist_ok=True)
run([build / 'host/check_shell_docedit_save.exe', root / 'tests/fixtures/docx-edit/plain.docx', evidence])
recent = json.loads((evidence / 'recent-books.json').read_text(encoding='utf-8'))
assert Path(recent['books'][0]['path']) == (evidence / 'new document.docx').resolve()
assert not list(evidence.glob('exr*.tmp'))
print('PASS recent JSON destination verified; no temporary files remain', flush=True)
