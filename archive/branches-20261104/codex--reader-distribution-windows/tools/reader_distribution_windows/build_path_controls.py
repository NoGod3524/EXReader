#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build the three COFF/archive control surfaces with the real MSVC toolchain.

Native tools take an argument list here so git-bash cannot rewrite /Fo, /PATHMAP
or any other switch. Each control is paired with the run-time JSON it produces:
the object is the compile-time half of the proof, the probe output the
run-time half.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import distlib


def run(command, cwd=None):
    done = subprocess.run(command, cwd=str(cwd) if cwd else None, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, text=True)
    distlib.require(done.returncode == 0,
                    'command failed (%d): %s\n%s' % (done.returncode, ' '.join(command),
                                                      done.stdout[-800:]))
    return done.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    source = args.source.resolve()
    distlib.require(source.is_file(), 'control source is missing: ' + str(source))
    for name in ('raw', 'bare', 'nested/a', 'nested/b', 'drective'):
        (root / name).mkdir(parents=True, exist_ok=True)
    log = []

    def compile_object(source_path, output, cwd=None, flags=('/Z7',)):
        command = ['cl', '/nologo', '/c'] + list(flags) + ['/Fo' + str(output), str(source_path)]
        log.append({'command': command, 'cwd': str(cwd) if cwd else None,
                    'output': run(command, cwd=cwd)[-400:]})

    def archive(output, objects):
        command = ['lib', '/nologo', '/OUT:' + str(output)] + [str(item) for item in objects]
        log.append({'command': command, 'output': run(command)[-400:]})

    def link(output, objects):
        # cl drives the real MSVC linker: git-bash resolves a bare "link" to the
        # coreutils utility, which would silently take an unrelated code path.
        command = ['cl', '/nologo', '/Fe:' + str(output)] + [str(item) for item in objects]
        log.append({'command': command, 'output': run(command)[-400:]})

    copy = root / 'path_surface.c'
    shutil.copyfile(source, copy)
    compile_object(copy, root / 'raw' / 'path_surface.obj')
    link(root / 'raw' / 'path_surface.exe', [root / 'raw' / 'path_surface.obj'])
    archive(root / 'raw' / 'path_surface.lib', [root / 'raw' / 'path_surface.obj'])
    compile_object(Path('path_surface.c'), root / 'bare' / 'path_surface.obj', cwd=root)
    link(root / 'bare' / 'path_surface.exe', [root / 'bare' / 'path_surface.obj'])
    archive(root / 'bare' / 'path_surface.lib', [root / 'bare' / 'path_surface.obj'])
    for first, second in (('a', 'first'), ('b', 'second')):
        target = root / 'nested' / first / (second + '.c')
        shutil.copyfile(source, target)
        compile_object(target, root / 'nested' / first / (second + '.obj'))
    archive(root / 'nested' / 'nested.lib',
            [root / 'nested' / 'a' / 'first.obj', root / 'nested' / 'b' / 'second.obj'])
    drective = root / 'drective' / 'drective_surface.c'
    drective.write_text('int reader_distribution_drective_anchor(void) { return 7; }\n'
                        '#pragma comment(lib, "%s")\n' % (root / 'vendor-control.lib').as_posix(),
                        encoding='utf-8')
    compile_object(drective, root / 'drective' / 'drective_surface.obj', cwd=root / 'drective')
    archive(root / 'drective' / 'drective.lib', [root / 'drective' / 'drective_surface.obj'])
    for name, payload in (('raw', 'raw-run.json'), ('bare', 'bare-run.json')):
        done = subprocess.run([str(root / name / 'path_surface.exe'), str(root / payload)],
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        distlib.require(done.returncode == 0, 'control probe failed: ' + name + ' ' + done.stdout[-400:])
    report = {'schema': 'reader-distribution-windows-controls-v1', 'root': str(root),
              'log': log}
    distlib.write_json(root / 'controls.json', report)
    print(json.dumps({'controls': len(log), 'root': str(root)}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
