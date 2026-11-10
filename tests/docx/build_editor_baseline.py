#!/usr/bin/env python3
"""Build the #124 MinGW control DLL, reusing byte-identical objects/dependencies."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import shlex
import subprocess
from zipfile import ZipFile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('build', type=Path)
parser.add_argument('--ref', default='9841d30bdbfb4d93605f2e612cf1cd7f36f52623')
args = parser.parse_args()
root = Path(__file__).resolve().parents[2]
build = args.build.resolve()
control = build / 'editor-baseline'
(control / 'include/exr').mkdir(parents=True, exist_ok=True)
baseline = ZipFile(io.BytesIO(subprocess.check_output(
    ['git', 'archive', '--format=zip', args.ref, 'src', 'include'], cwd=root)))


def original(name):
    return baseline.read(name)


header = original('include/exr/edit.h')
(control / 'include/exr/edit.h').write_bytes(header)
lines = (build / 'build.ninja').read_text().splitlines()
at = next(i for i, line in enumerate(lines) if line.startswith('build libexreader.dll libexreader.dll.a:'))
objects = lines[at].split(': ', 1)[1].split(' | ', 1)[0].split()[1:]
libraries = next(line.split(' = ', 1)[1].split() for line in lines[at+1:at+20] if line.strip().startswith('LINK_LIBRARIES ='))
compiler = re.search(r'^CMAKE_C_COMPILER:FILEPATH=(.+)$', (build / 'CMakeCache.txt').read_text(), re.M)[1]
replaced = []
recompile = {'docx_edit.c', 'docx_reflow.c', 'pager.c'}
for obj in objects[:]:
    source = Path(obj).name.removesuffix('.obj')
    if not source.endswith('.c'):
        continue
    path = 'src/' + source
    if source in ('docx_edit_io.c', 'docx_edit_table.c', 'docx_edit_image.c'):
        objects.remove(obj)
        continue
    data = original(path)
    if source not in recompile:
        assert data == (root / path).read_bytes(), 'cannot reuse changed source: ' + path
        continue
    saved, output = control / source, control / (source + '.obj')
    saved.write_bytes(data)
    command = subprocess.check_output(['ninja', '-t', 'commands', obj], cwd=build, text=True).splitlines()[-1]
    command = [v[1:-1] if v.startswith('"') and v.endswith('"') else v
               for v in shlex.split(command, posix=False)]
    for flag in ('-MT', '-MF'):
        if flag in command:
            i = command.index(flag)
            del command[i:i+2]
    if '-MD' in command:
        command.remove('-MD')
    command[command.index('-o') + 1] = str(output)
    command[-1] = str(saved)
    # Original header precedes the candidate's includes; local internal headers
    # remain identical and are resolved from the repository source directory.
    command[1:1] = ['-I' + str(control / 'include'), '-I' + str(root / 'src')]
    subprocess.run(command, cwd=build, check=True)
    objects[objects.index(obj)] = str(output)
    replaced.append(source)
symbols = set(re.findall(rb'\b(exr_\w+)\s*\(', header))
exports = [line for line in (build / 'exreader.def').read_text().splitlines()
           if not line.strip().startswith('exr_edit_') or line.strip().encode() in symbols]
(control / 'baseline.def').write_text('\n'.join(exports) + '\n')
dll = control / 'libexreader.dll'
subprocess.run([compiler, '-O3', '-DNDEBUG', '-shared', '-static-libgcc', '-static',
                str(control / 'baseline.def'), '-o', str(dll), *objects, *libraries], cwd=build, check=True)
metadata = dict(ref=args.ref, recompiled=replaced, reused_sources_verified=True,
                method='original #124 sources/header plus byte-identical candidate objects and identical dependencies',
                dll_sha256=hashlib.sha256(dll.read_bytes()).hexdigest())
(control / 'build.json').write_text(json.dumps(metadata, indent=2) + '\n')
print(json.dumps(metadata))
