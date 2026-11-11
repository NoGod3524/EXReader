"""Build a read-only control DLL from HEAD's pager and the candidate's other objects.
Run after the candidate is built; all dependencies/options are identical.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('build', type=Path)
a = p.parse_args()
root = Path(__file__).resolve().parents[1]
build = a.build.resolve()
ref = build / 'reference'
ref.mkdir(exist_ok=True)
source = subprocess.check_output(['git', 'show', 'HEAD:src/pager.c'], cwd=root)
(ref / 'pager.c').write_bytes(source)
cache = (build / 'CMakeCache.txt').read_text()
compiler = re.search(r'^CMAKE_C_COMPILER:FILEPATH=(.+)$', cache, re.M)[1]
command = [compiler, '-O3', '-DNDEBUG', '-std=c11', '-DEXR_STATIC', '-Wall', '-Wextra', '-Wpedantic', '-Werror',
           '-I' + str(root / 'include'), '-I' + str(root / 'src'), '-I' + str(build / 'generated/include'),
           '-I' + str(build / '_deps/freetype-build/include')]
# Recover the pinned FreeType source include from the actual compile command.
compiled = subprocess.check_output(['ninja', '-t', 'commands',
    'CMakeFiles/exr_layout_objects.dir/src/pager.c.obj'], cwd=build, text=True).splitlines()[-1]
for include in re.findall(r'-isystem ([^ ]+)', compiled):
    command += ['-isystem', include.strip('"')]
command += ['-c', str(ref / 'pager.c'), '-o', str(ref / 'pager.obj')]
subprocess.run(command, check=True, cwd=build)
lines = (build / 'build.ninja').read_text().splitlines()
at = next(i for i, x in enumerate(lines) if x.startswith('build libexreader.dll libexreader.dll.a:'))
objects = lines[at].split(': ', 1)[1].split(' | ', 1)[0].split()[1:]
objects = [x for x in objects if not x.endswith(('/pager.c.obj', '/docx_reflow.c.obj'))]
libs = next(x.split(' = ', 1)[1].split() for x in lines[at+1:at+20] if x.strip().startswith('LINK_LIBRARIES ='))
exports = (build / 'exreader.def').read_text().splitlines()
exports = [x for x in exports if not x.strip().startswith(('exr_edit_', 'exr_pager_cache_statistics'))]
(ref / 'reference.def').write_text('\n'.join(exports)+'\n')
link = [compiler, '-O3', '-DNDEBUG', '-shared', '-static-libgcc', '-static', str(ref / 'reference.def'),
        '-o', str(ref / 'libexreader.dll'), str(ref / 'pager.obj'), *objects, *libs]
subprocess.run(link, check=True, cwd=build)
metadata = {'head': subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
            'pager_sha256': hashlib.sha256(source).hexdigest(),
            'dll_sha256': hashlib.sha256((ref/'libexreader.dll').read_bytes()).hexdigest(),
            'method': 'HEAD pager.c + identical candidate objects/dependencies, excluding docx_reflow.c',
            'compiler': compiler}
(ref / 'build.json').write_text(json.dumps(metadata,indent=2)+'\n')
print(json.dumps(metadata))
