# SPDX-License-Identifier: MIT
"""Relink unchanged MinGW Release objects with a sink-only diagnostic shim."""
from pathlib import Path
import hashlib,json,re,subprocess,sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parent.parent
build=Path(sys.argv[1]).resolve()
scratch=ROOT/'build/rgb-sink-probe';scratch.mkdir(parents=True,exist_ok=True)
source=HERE/'probe.c'
ninja=(build/'build.ninja').read_text()
rule=re.search(r'^build libexreader.dll .*?Release (.*?) \|.*?^  LINK_LIBRARIES = (.*)$',ninja,re.M|re.S)
objects=rule[1];libraries=rule[2].splitlines()[0]
compiler=next(l.split('=',1)[1] for l in (build/'CMakeCache.txt').read_text().splitlines() if l.startswith('CMAKE_C_COMPILER:'))
obj=scratch/'probe.o'
subprocess.run([compiler,'-O3','-Wall','-Wextra','-Werror','-DEXR_STATIC','-c',str(source),'-o',str(obj),'-I'+str(ROOT/'src'),'-I'+str(ROOT/'include'),'-I'+re.search(r'-isystem ([^\s]+/freetype-src/include)',ninja)[1]],check=True)
rsp=scratch/'probe.rsp';rsp.write_text(f'"{obj.as_posix()}" {objects} {libraries}')
dll=scratch/'rgb-sink.dll'
subprocess.run([compiler,'-shared','-static-libgcc','-static','exreader.def','-o',str(dll),'-Wl,--wrap=exr_canvas_get_sink_ex','-Wl,--wrap=exr_pdf_soft_mask_build','@'+str(rsp)],cwd=build,check=True)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
files=[build/p for p in objects.split()]+[build/'libexreader.dll',dll,source,build/'CMakeCache.txt',build/'build.ninja']
metadata={'build':str(build),'base_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=build.parent.parent,text=True).strip(),'compiler':subprocess.check_output([compiler,'--version'],text=True),'files':{str(p):sha(p) for p in files},'objects':objects,'libraries':libraries}
(HERE/'build.json').write_text(json.dumps(metadata,indent=2)+'\n')
print(dll)
