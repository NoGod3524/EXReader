# SPDX-License-Identifier: MIT
"""Record CPU identity and confirm renderer sources match the object-build worktree."""
import hashlib,json,subprocess,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parent.parent
build=Path(json.loads((HERE/'build.json').read_text())['build'])
other=build.parent.parent
files=sorted(p.relative_to(ROOT) for d in ('src','include') for p in (ROOT/d).rglob('*') if p.suffix in ('.c','.h'))
mismatch=[str(f) for f in files if (ROOT/f).read_bytes()!=(other/f).read_bytes()]
cpu=json.loads(subprocess.check_output(['powershell','-NoProfile','-Command','Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors,L2CacheSize,L3CacheSize | ConvertTo-Json'],text=True))
out={'compared_render_and_header_files':len(files),'source_mismatches':mismatch,'base_commit':json.loads((HERE/'build.json').read_text())['base_commit'],
     'worktree_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'cpu':cpu,
     'ninja_log_sha256':hashlib.sha256((build/'.ninja_log').read_bytes()).hexdigest()}
(HERE/'provenance.json').write_text(json.dumps(out,indent=2)+'\n')
print(len(files),'files,',len(mismatch),'mismatches');sys.exit(1 if mismatch else 0)
