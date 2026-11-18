# SPDX-License-Identifier: MIT
"""Relink unchanged MinGW Release objects with the replica and the sink-only probe."""
from pathlib import Path
import hashlib,json,re,subprocess,sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parent.parent
build=Path(sys.argv[1]).resolve()
scratch=ROOT/'build/rgb-sink-arithmetic';scratch.mkdir(parents=True,exist_ok=True)
subprocess.run([sys.executable,str(HERE/'make_replica.py')],check=True)
ninja=(build/'build.ninja').read_text()
rule=re.search(r'^build libexreader.dll .*?Release (.*?) \|.*?^  LINK_LIBRARIES = (.*)$',ninja,re.M|re.S)
objects=rule[1];libraries=rule[2].splitlines()[0]
production=re.search(r'^build CMakeFiles/exr_graphics_objects.dir/src/affine_image.c.obj:.*?^  DEFINES = (.*?)$.*?^  FLAGS = (.*?)$',ninja,re.M|re.S)
defines,flags=production[1].split(),production[2].split()
compiler=next(l.split('=',1)[1] for l in (build/'CMakeCache.txt').read_text().splitlines() if l.startswith('CMAKE_C_COMPILER:'))
includes=['-I'+str(ROOT/'src'),'-I'+str(ROOT/'include'),'-I'+str(HERE),'-I'+str(build/'generated/include'),'-I'+str(build/'generated'),
          '-I'+re.search(r'-isystem ([^\s]+/freetype-src/include)',ninja)[1]]
objs=[]
# Same optimization, language and warning flags as the production affine_image.c object;
# one replica object per knock-out mask, so each mask is a compile-time constant.
for name,extra in [('replica.c',[f'-DREPLICA_ID={i}']) for i in range(18)]+[('probe.c',[])]:
    obj=scratch/(Path(name).stem+(extra[0].split('=')[1] if extra else '')+'.o')
    subprocess.run([compiler,*flags,*defines,*extra,'-c',str(HERE/name),'-o',str(obj),*includes],check=True)
    objs.append(obj)
rsp=scratch/'probe.rsp';rsp.write_text(' '.join(f'"{o.as_posix()}"' for o in objs)+f' {objects} {libraries}')
dll=scratch/'rgb-sink-arithmetic.dll'
subprocess.run([compiler,'-shared','-static-libgcc','-static','exreader.def','-o',str(dll),'-Wl,--wrap=exr_canvas_get_sink_ex','-Wl,--wrap=exr_pdf_soft_mask_build','@'+str(rsp)],cwd=build,check=True)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
files=[build/p for p in objects.split()]+[build/'libexreader.dll',dll,*objs,HERE/'probe.c',HERE/'replica.c',HERE/'replica_knobs.h',ROOT/'src/affine_image.c',build/'CMakeCache.txt',build/'build.ninja']
metadata={'build':str(build),'base_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=build.parent.parent,text=True).strip(),
  'compiler':subprocess.check_output([compiler,'--version'],text=True),'replica_flags':flags+defines,'files':{str(p):sha(p) for p in files},'objects':objects,'libraries':libraries}
(HERE/'build.json').write_text(json.dumps(metadata,indent=2)+'\n')
print(dll)
