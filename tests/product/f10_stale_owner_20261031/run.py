# SPDX-License-Identifier: MIT
import argparse,hashlib,json,os,subprocess
from pathlib import Path
CASES=["owned-kill","sealed-kill","active-owner","historical-device","wrong-uuid","corrupt-receipt","residual-receipt-next","wrong-id","wrong-slot","wrong-inode","wrong-state","wrong-bytes","extra-entry","payload-replaced","directory-replaced","payload-symlink","directory-symlink","extra-hardlink","foreign-payload-owner","payload-permissions","directory-permissions","sealed-size","legacy-owned-pending","permission-retry","unregistered-residue","borrow","borrow-replaced","lifetime64","legacy-published","cleanup-kill-payload","cleanup-kill-directory","reserved-refused","intent-refused"]
BOUNDARIES=set(CASES[-4:])
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    a=argparse.ArgumentParser();a.add_argument('--bin',type=Path,required=True);a.add_argument('--output',type=Path,required=True);args=a.parse_args()
    assert os.environ.get('GITHUB_ACTIONS')=='true' and os.geteuid()!=0
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    binaries={k:(args.bin/k).resolve() for k in ['f10-stale-probe','f10-stale-boundary-probe']}
    rows=[]
    for name in CASES:
        d=out/name;d.mkdir()
        work=out.parent/'private-fixtures'/name;work.mkdir(parents=True)
        binary=binaries['f10-stale-boundary-probe' if name in BOUNDARIES else 'f10-stale-probe']
        try:
            p=subprocess.run([str(binary),name],cwd=work,text=True,capture_output=True,timeout=30)
            (d/'stdout.log').write_text(p.stdout);(d/'stderr.log').write_text(p.stderr)
            records=[json.loads(l) for l in p.stdout.splitlines() if l.startswith('{')]
            row={'name':name,'exit':p.returncode,'records':records,'binary':binary.name,'binary_sha256':digest(binary),'timeout':False}
        except subprocess.TimeoutExpired as e:
            (d/'stdout.log').write_bytes(e.stdout or b'');(d/'stderr.log').write_bytes(e.stderr or b'')
            row={'name':name,'timeout':True,'exit':None,'records':[],'binary':binary.name,'binary_sha256':digest(binary)}
        (d/'observation.json').write_text(json.dumps(row,indent=2)+'\n');rows.append(row)
    index={'source':os.environ['GITHUB_SHA'],'run':os.environ['GITHUB_RUN_ID'],'attempt':os.environ['GITHUB_RUN_ATTEMPT'],'cases':CASES,
           'binaries':{k:digest(v) for k,v in binaries.items()},'euid':os.geteuid(),'full_f10_complete':False,
           'scope':'POSIX cleanup additive APIs; installed library plus separately labelled existing-hook boundary binary'}
    (out/'index.json').write_text(json.dumps(index,indent=2)+'\n')
    print(json.dumps({'cases':len(rows),'failed':[r['name'] for r in rows if r['exit']!=0]}))
    from https_fixture import run_suite
    extra=run_suite((args.bin/'f10-sync-probe').resolve(),(args.bin/'f10-old-client').resolve(),(args.bin/'f10-managed-boundary-probe').resolve(),out/'snapshot')
    print(json.dumps({'snapshot_cases':len(extra),'exceptions':[r['name'] for r in extra if 'exception' in r['checks']]}))
    # Preserve fixture namespaces separately from the uploaded raw logs.
    return 0 if all(r['exit']==0 for r in rows) else 1
if __name__=='__main__':raise SystemExit(main())
