"""Build/review L07 without changing another lane's existing source files."""
from pathlib import Path
import argparse
import difflib
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def replace_once(text, old, new):
    assert text.count(old) == 1, f"Integration context changed: {old!r}"
    return text.replace(old, new, 1)


def stage(destination):
    destination.mkdir(parents=True, exist_ok=True)
    for relative in ['examples/windows', 'apps/reader/desktop', 'tools']:
        folder = destination / relative
        folder.mkdir(parents=True, exist_ok=True)
        for source in (ROOT / relative).iterdir():
            if source.suffix in {'.inc', '.h', '.c', '.cpp'}:
                shutil.copy2(source, folder / source.name)
    shutil.copy2(ROOT / 'examples/reader.c', destination / 'examples/reader.c')
    shutil.copy2(ROOT / 'tests/docedit_a11y/check_shell_docedit_a11y.c',
                 destination / 'examples/windows/check_shell_docedit_a11y.c')
    changes = {
        'examples/reader.c': [
            ('#include "windows/shell_docedit_input.inc"',
             '#include "windows/shell_docedit_input.inc"\n#include "windows/shell_docedit_a11y.inc"'),
        ],
        'examples/windows/shell_docedit.inc': [
            ('static void de_refresh(int reveal);',
             'static void da_update(void);\nstatic void da_close(void);\nstatic int da_key(WPARAM,int,int);\n'
             'static int da_character(wchar_t);\nstatic int da_translate(const MSG *);\nstatic void de_refresh(int reveal);'),
            ('de_title();de_refresh(1);return 1;', 'de_title();de_refresh(1);da_update();return 1;'),
            ('static void de_close(void) {', 'static void de_close(void) {\n  da_close();'),
            ('EnableWindow(de_button,de_eligible() && !de.doc);',
             'host_a11y_describe(de_button,NULL,L"编辑 DOCX，快捷键 F2；F6 打开编辑命令，Ctrl+T 进入表格");\n'
             '  if(de.doc)host_a11y_describe(g.page,NULL,L"DOCX 正文编辑区；直接输入，F6 命令面板，Ctrl+T 表格，Ctrl+S 保存");\n'
             '  EnableWindow(de_button,de_eligible() && !de.doc);'),
        ],
        'examples/windows/shell_docedit_input.inc': [
            ('static int de_key(WPARAM key,int control,int shift) {',
             'static int de_key(WPARAM key,int control,int shift) {\n  if(da_key(key,control,shift))return 1;'),
            ('static void de_character(wchar_t ch) {',
             'static void de_character(wchar_t ch) {\n  if(da_character(ch))return;'),
            ('static int de_translate(const MSG *message) {',
             'static int de_translate(const MSG *message) {\n  if(da_translate(message))return 1;'),
        ],
    }
    patch = []
    for name, replacements in changes.items():
        original = (ROOT / name).read_text(encoding='utf-8')
        modified = original
        for before, after in replacements:
            modified = replace_once(modified, before, after)
        (destination / name).write_text(modified, encoding='utf-8')
        patch.extend(difflib.unified_diff(original.splitlines(True), modified.splitlines(True),
                                         fromfile='a/' + name, tofile='b/' + name))
    (destination.parent / 'integration.patch').write_text(''.join(patch), encoding='utf-8')
    print('Staged three host integration files; original worktree files unchanged.', flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--build', type=Path, default=ROOT / 'build/l07-a11y')
    parser.add_argument('--dependency-cache', type=Path,
                        help='Optional existing CMakeCache.txt with FetchContent source paths')
    parser.add_argument('--stage-only', action='store_true')
    options = parser.parse_args()
    build = options.build.resolve()
    overlay = build / 'host'
    stage(overlay)
    if options.stage_only:
        return
    args = ['cmake', '-S', str(ROOT / 'tests/docedit_a11y'), '-B', str(build), '-G', 'Ninja',
            '-DCMAKE_BUILD_TYPE=Release', '-DL07_HOST=' + overlay.as_posix()]
    if options.dependency_cache:
        for line in options.dependency_cache.read_text().splitlines():
            if line.startswith('FETCHCONTENT_SOURCE_DIR_') and '=' in line:
                key, value = line.split('=', 1)
                args.append('-D' + key.split(':')[0] + '=' + value)
    subprocess.run(args, check=True)
    subprocess.run(['cmake', '--build', str(build), '--target', 'check_shell_docedit_a11y',
                    'EXReaderL07', '-j', '2'], check=True)
    subprocess.run(['ctest', '--test-dir', str(build), '--output-on-failure'], check=True)


if __name__ == '__main__':
    main()
