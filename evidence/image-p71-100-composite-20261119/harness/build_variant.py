# SPDX-License-Identifier: MIT
"""Relink libexreader.dll with one replacement translation unit.

usage: build_variant.py <build dir> <replacement affine_image.c> <out dll>
The replacement is compiled with the exact ninja command line for
src/affine_image.c (only source/output/dependency flags change); every other
object and the link line come from the same build tree.
"""
import re, subprocess, sys
from pathlib import Path
b, src, out = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve(), Path(sys.argv[3]).resolve()
root = b.parents[1]
n = (b/'build.ninja').read_text(encoding='utf8')
rule = re.search(r'^build libexreader.dll .*?Release (.*?) \|.*?^  LINK_LIBRARIES = ([^\n]+)$', n, re.M | re.S)
gcc = next(x.split('=', 1)[1] for x in (b/'CMakeCache.txt').read_text().splitlines() if x.startswith('CMAKE_C_COMPILER:'))
objects = rule[1]
obj = next(x for x in objects.split() if x.endswith('/affine_image.c.obj'))
cmd = subprocess.check_output(['ninja', '-C', str(b), '-t', 'commands', obj], text=True).splitlines()[-1].split()
for opt in ('-MT', '-MF', '-o', '-c'):
    i = cmd.index(opt); del cmd[i:i+2]
cmd.remove('-MD')
cmd = [x.replace(chr(92)+chr(34), chr(34)) for x in cmd]
scratch = out.with_suffix('.affine_image.o')
subprocess.run([*cmd, '-I'+str(root/'src'), '-o', str(scratch), '-c', str(src)], cwd=b, check=True)
objects = objects.replace(obj, '"'+scratch.as_posix()+'"')
rsp = out.with_suffix('.rsp'); rsp.write_text(f'{objects} {rule[2]}')
if out.exists(): out.unlink()
subprocess.run([gcc, '-shared', '-static-libgcc', '-static', 'exreader.def', '-o', str(out), '@'+str(rsp)], cwd=b, check=True)
print(out)
