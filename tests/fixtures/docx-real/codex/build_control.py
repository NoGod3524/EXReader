#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build an exact #125 MinGW control from Git, verifying every reused source."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import shlex
import subprocess
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[4]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--ref', default='c04560b784bda182b350b9f6faac33a10ed60509')
    parser.add_argument('--stage', choices=('baseline', 'text', 'paragraph', 'final'), default='baseline',
                        help='replay each repair independently; final CMake build is checked separately')
    args = parser.parse_args()
    build, control = args.build.resolve(), args.output.resolve()
    (control / 'include/exr').mkdir(parents=True, exist_ok=True)
    snapshot = ZipFile(io.BytesIO(subprocess.check_output(['git', 'archive', '--format=zip', args.ref, 'src', 'include'], cwd=ROOT)))
    header = snapshot.read('include/exr/edit.h') if args.stage == 'baseline' else (ROOT / 'include/exr/edit.h').read_bytes()
    (control / 'include/exr/edit.h').write_bytes(header)
    lines = (build / 'build.ninja').read_text().splitlines()
    at = next(i for i, line in enumerate(lines) if line.startswith('build libexreader.dll libexreader.dll.a:'))
    objects = lines[at].split(': ', 1)[1].split(' | ', 1)[0].split()[1:]
    libraries = next(line.split(' = ', 1)[1].split() for line in lines[at+1:at+20] if line.strip().startswith('LINK_LIBRARIES ='))
    compiler = re.search(r'^CMAKE_C_COMPILER:FILEPATH=(.+)$', (build / 'CMakeCache.txt').read_text(), re.M)[1]
    rebuilt, verified = [], []
    for i, obj in enumerate(objects):
        name = Path(obj).name.removesuffix('.obj')
        if not name.endswith('.c'):
            continue
        path = 'src/' + name
        data = snapshot.read(path)
        if name not in ('docx_edit.c', 'docx_edit_io.c'):
            assert data == (ROOT / path).read_bytes(), 'cannot reuse changed source: ' + path
            verified.append(dict(path=path, sha256=hashlib.sha256(data).hexdigest()))
            continue
        if name == 'docx_edit.c' and args.stage != 'baseline':
            data = (ROOT / path).read_bytes()
        if name == 'docx_edit_io.c' and args.stage == 'paragraph':
            current = (ROOT / path).read_bytes()
            start, end = b'int exr_edit_xml_paragraph(', b'static int reference_slot('
            data = data[:data.index(start)] + current[current.index(start):current.index(end)] + data[data.index(end):]
        elif name == 'docx_edit_io.c' and args.stage == 'final':
            data = (ROOT / path).read_bytes()
        saved, output = control / name, control / (name + '.obj')
        saved.write_bytes(data)
        command = subprocess.check_output(['ninja', '-t', 'commands', obj], cwd=build, text=True).splitlines()[-1]
        command = [v[1:-1] if v.startswith('"') and v.endswith('"') else v for v in shlex.split(command, posix=False)]
        command = [v.replace(r'\"', '"') for v in command]
        for flag in ('-MT', '-MF'):
            if flag in command:
                pos = command.index(flag)
                del command[pos:pos+2]
        if '-MD' in command:
            command.remove('-MD')
        command[command.index('-o')+1], command[-1] = str(output), str(saved)
        command[1:1] = ['-I' + str(control / 'include'), '-I' + str(ROOT / 'src')]
        subprocess.run(command, cwd=build, check=True)
        objects[i] = str(output)
        rebuilt.append(dict(path=path, sha256=hashlib.sha256(data).hexdigest()))
    symbols = set(re.findall(rb'\b(exr_\w+)\s*\(', header))
    exports = [line for line in (build / 'exreader.def').read_text().splitlines()
        if not line.strip().startswith('exr_edit_') or line.strip().encode() in symbols]
    declared = {line.strip() for line in exports}
    exports.extend('  ' + name.decode() for name in sorted(symbols) if name.decode() not in declared)
    (control / 'baseline.def').write_text('\n'.join(exports) + '\n')
    dll = control / 'libexreader.dll'
    subprocess.run([compiler, '-O3', '-DNDEBUG', '-shared', '-static-libgcc', '-static',
        str(control / 'baseline.def'), '-o', str(dll), *objects, *libraries], cwd=build, check=True)
    metadata = dict(ref=args.ref, stage=args.stage, recompiled=rebuilt, reused_sources=verified,
        method='Git-original #125 sources/header; all reused product source bytes verified; identical dependency objects',
        dll_sha256=hashlib.sha256(dll.read_bytes()).hexdigest())
    (control / 'build.json').write_text(json.dumps(metadata, indent=2) + '\n')
    print('Stage', args.stage, 'built:', metadata['dll_sha256'], len(verified), 'reused sources verified')


if __name__ == '__main__':
    main()
