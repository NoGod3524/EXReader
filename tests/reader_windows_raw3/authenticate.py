"""Actions-only independent authentication of one complete Windows owner run."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import zipfile

REPO='repos/NoGod3524/EXReader'


def need(value,message):
    if not value:raise RuntimeError(message)


def api(path):
    return json.loads(subprocess.check_output(['gh','api',REPO+path]))


def main():
    need(os.environ.get('GITHUB_ACTIONS')=='true','Actions only')
    parser=argparse.ArgumentParser()
    parser.add_argument('--run',type=int,required=True)
    parser.add_argument('--source',required=True)
    args=parser.parse_args()
    run=api('/actions/runs/'+str(args.run))
    need(run['head_sha']==args.source and run['status']=='completed' and run['conclusion']=='success','Producer run identity/state')
    need(run['path']=='.github/workflows/reader-windows-raw3-host.yml','Unexpected producer workflow')
    attempt=run['run_attempt']
    jobs=api(f'/actions/runs/{args.run}/attempts/{attempt}/jobs?per_page=100')
    need(jobs['total_count']==1 and len(jobs['jobs'])==1,'Producer job set')
    job=jobs['jobs'][0]
    need(job['name']=='host' and job['conclusion']=='success' and job['head_sha']==args.source,'Producer job')
    listing=api(f'/actions/runs/{args.run}/artifacts?per_page=100')
    artifacts=[a for a in listing['artifacts'] if a['name']==f'windows-installed-raw3-{args.run}-{attempt}']
    need(len(artifacts)==1,'Unique original artifact')
    artifact=artifacts[0]
    need(not artifact['expired'] and datetime.fromisoformat(artifact['expires_at'].replace('Z','+00:00'))>datetime.now(timezone.utc),'Artifact expired')
    need(artifact['workflow_run']['head_sha']==args.source and artifact['workflow_run']['id']==args.run,'Artifact producer')
    out=Path('build/windows-owner-authentication');out.mkdir(parents=True)
    archive=out/'original.zip'
    with archive.open('wb') as stream:
        subprocess.run(['gh','api',REPO+f"/actions/artifacts/{artifact['id']}/zip"],stdout=stream,check=True)
    with archive.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
    need(archive.stat().st_size==artifact['size_in_bytes'] and artifact['digest']=='sha256:'+digest,'Original ZIP bytes/digest')
    with zipfile.ZipFile(archive) as z:
        names=z.namelist()
        need(len(names)==len(set(names)),'Duplicate ZIP names')
        need(all(not n.startswith('/') and '\\' not in n and '..' not in n.split('/') for n in names),'Unsafe ZIP names')
        def member(suffix):
            matches=[n for n in names if n==suffix or n.endswith('/'+suffix)]
            need(len(matches)==1,'Unique member '+suffix)
            return z.read(matches[0])
        def report(suffix):return json.loads(member('windows-raw3-host/'+suffix))
        root=report('report.json')
        need(root['source_sha']==args.source and str(root['run_id'])==str(args.run) and int(root['attempt'])==attempt,'Host report identity')
        for flag in ('installed_host_build_passed','original_bulk_profiles_passed','actual_owner_profiles_passed','actual_owner_process_kill_recovery_passed'):
            need(root[flag] is True,'Missing host result '+flag)
        need(root['host_raw3_accepted'] is False,'Overbroad host grant')
        need([p['profile'] for p in root['profiles']]==['legacy','raw'],'Exact profiles')
        owner_hash=subprocess.check_output(['git','show',args.source+':apps/reader/desktop/windows_records_owner.cpp'])
        owner_hash=hashlib.sha256(owner_hash).hexdigest()
        for profile in root['profiles']:
            name=profile['profile']
            for target,expected in profile['programs'].items():
                need(hashlib.sha256(member(f'windows-raw3-host/{name}-host/{target}.exe')).hexdigest()==expected,'Host program hash')
            compact=report(name+'-compact-ui/report.json')
            need(compact['source_sha']==args.source and compact['accepted'] is True and not compact['problems'],'Original compact UI')
            need(compact['consumer_sha256']==profile['programs']['EXReaderProduct'],'Compact actual program')
            from contract import validate
            validate(compact,args.source,args.run,attempt,profile['programs']['EXReaderProduct'])
            bulk=report(name+'-bulk-evidence/report.json')
            need(bulk['ok'] is True and len(bulk['checks'])==profile['bulk_original_checks']==21,'Original bulk report')
        modes=[('legacy-owner-suite','suite','legacy'),('raw-owner-suite','suite','raw'),('raw-owner-suite','fresh','raw')]
        for phase in (2,3):
            modes += [(f'owner-kill-{phase}','reject-private','legacy'),(f'owner-kill-{phase}','verify-child','raw')]
        modes += [('owner-legacy-kill','reject-legacy-private','raw'),('owner-legacy-kill','legacy-retry','raw')]
        for folder,mode,profile in modes:
            value=report(folder+'/report-'+mode+'.json')
            need(value['ok'] is True and value['source_sha']==args.source and value['owner_source_sha256']==owner_hash,'Owner report/source')
            need(value['mode']==mode and value['profile']==('raw3' if profile=='raw' else 'legacy') and value['sdk_version']=='3.41.0','Owner mode/profile/SDK')
            need(value['checks'] and all(c['pass'] is True for c in value['checks']),'Owner checks')
            need(value['program_sha256']==hashlib.sha256(member(f'windows-raw3-host/{profile}-owner-probe/windows-owner-probe.exe')).hexdigest(),'Owner program hash')
        for folder,phase,magic in [('owner-kill-2',2,'EXRRD002'),('owner-kill-3',3,'EXRRD002'),('owner-legacy-kill',2,'EXRRD001')]:
            killed=report(folder+'/external-kill.json');marker=killed['marker']
            pending=member('windows-raw3-host/'+folder+'/pending-before-retry.bin')
            need(killed['terminated_by_driver'] is True and killed['exit_code']!=0 and marker['phase']==phase and marker['pid']>0,'Actual process termination')
            need(marker['private_magic']==magic and pending[:8]==magic.encode() and len(pending)==marker['pending_bytes'] and hashlib.sha256(pending).hexdigest()==marker['pending_sha256'],'Original killed-process pending bytes')
    archive.unlink()
    result=dict(accepted=True,complete_product=False,source=args.source,producer_run=args.run,attempt=attempt,
                producer_job=job['id'],artifact=artifact,zip_sha256=digest,owner_reports=len(modes),
                scope='installed Windows profiles, original compact22 and bulk21, real owner and process recovery only',
                whole_original_OFF_F3_atomic13=False,network_receive=False,same_source_bidirectional=False)
    (out/'report.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))


if __name__=='__main__':
    import sys
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'reader_windows_compact'))
    main()
