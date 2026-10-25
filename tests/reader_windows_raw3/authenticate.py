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
    network_verified=False
    peer_records_verified=False
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
        if root.get('actual_account_window_mac_receive_passed') is True:
            network=report('mac-network-receive/report.json')
            need(network['accepted'] is True and network['source_sha']==args.source and str(network['run_id'])==str(args.run) and int(network['attempt'])==attempt,'Actual account receive report identity')
            need(network['program_sha256']==root['profiles'][1]['programs']['EXReaderProduct'],'Actual receiving host program')
            need(network['same_source_bidirectional'] is False and network['all_reading_records_FOUND'] is False and network['complete_product'] is False,'Network scope overstated')
            proof=network['mac_proof']
            need(proof['source_sha']=='15dab6b2270dc296ed6239db67ced2e22d255e65' and proof['run_id']==40196978163 and proof['attempt']==1,'Original Mac sender identity')
            need(proof['artifact']['id']==12600789926 and proof['artifact']['digest']=='sha256:92be56ffa04d7c334d4811a42821a314089b4f8ae01746f0dfdf456b5eab9bd5','Original Mac sender ZIP')
            need((proof['wire_count'],proof['original_count'],proof['reading_records'])==(15,4,11),'Original Mac packet scope')
            required=['actual-account-window-receives-and-maps-four-Mac-originals',
                'all-fifteen-original-Mac-wires-and-parent-graphs-retained-byte-for-byte',
                'fresh-native-process-reopens-four-mappings-and-unchanged-wire-history',
                'authenticated-native-TLS-completes-all-256-revision-shards',
                'session-only-test-secret-not-persisted-in-profile']
            required += ['native-open-'+kind for kind in ('txt','epub','pdf','cbz')]
            need(len(network['checks'])==9 and set(network['checks'])==set(required),'Complete native receive check set')
            requests=report('mac-network-receive/requests.json')
            need(requests and all(row['authenticated'] is True for row in requests),'Actual request authentication')
            shards={row['path'] for row in requests if row['method']=='PROPFIND' and row['path'].startswith('/dav/exreader-sync-v1/revisions/') and len(row['path'].removeprefix('/dav/exreader-sync-v1/revisions/'))==3}
            need(shards=={'/dav/exreader-sync-v1/revisions/%02x/'%i for i in range(256)},'Complete native shard scan')
            network_verified=True
        if root.get('actual_received_owner_all11_two_processes_passed') is True:
            need(network_verified,'Missing actual network receive before owner proof')
            manifest=json.loads(member('windows-raw3-host/mac-network-receive/mac/sender/manifest.json'))
            records={r['revision_id']:r for r in manifest['reading_records']}
            wire_hashes={r['id']:r['sha256'] for r in manifest['revisions']}
            need(len(records)==11,'Complete original capture set')
            expected=member('windows-raw3-host/mac-network-receive/peer-owner/expected.bin')
            program=member('windows-raw3-host/peer-owner-build/windows-peer-owner.exe')
            pids=set()
            for phase in ('first','reopen'):
                value=report('mac-network-receive/peer-owner/'+phase+'.json')
                need(value['accepted'] is True and not value['failure'] and value['source_sha']==args.source and str(value['run_id'])==str(args.run) and int(value['attempt'])==attempt,'Received owner identity/acceptance')
                need(value['sdk_version']=='3.41.0' and value['owner_source_sha256']==owner_hash and value['program_sha256']==hashlib.sha256(program).hexdigest(),'Received owner actual program/SDK')
                need(value['expected_sha256']==hashlib.sha256(expected).hexdigest() and value['manifest_sha256']==proof['manifest_sha256'],'Original capture expectations')
                need(value['product_before'] and value['product_before']==value['product_after'] and value['sdk_before'] and value['sdk_before']==value['sdk_after'],'Received owner state changed')
                need(value['actual_owner_reads_and_FOUND']==11 and len(value['records'])==11 and {r['revision_id'] for r in value['records']}==set(records),'Complete actual owner resolution set')
                need(value['pid']>0 and value['pid'] not in pids,'Distinct real receiver processes');pids.add(value['pid'])
                for row in value['records']:
                    original=records[row['revision_id']]
                    need(row['wire_sha256']==wire_hashes[row['revision_id']] and row['role']==original['role'] and row['kind']==original['kind'],'Original record identity')
                    need(row['owner_READ_callback_calls']==0 and row['independent_sdk_callback_calls']==1,'READ is not itself FOUND')
                    need(all(row[key] is True for key in ('actual_owner_READ','found','retained_manifest_capture_equal','fresh_capture_equal','NULL_callback_negative_refused')),'Actual independent record results')
                need(value['same_source_bidirectional'] is False and value['complete_product'] is False and value['host_ui_accepted'] is False,'Received owner scope overstated')
            peer_records_verified=True
    archive.unlink()
    result=dict(accepted=True,complete_product=False,source=args.source,producer_run=args.run,attempt=attempt,
                producer_job=job['id'],artifact=artifact,zip_sha256=digest,owner_reports=len(modes),
                scope='installed Windows profiles, original compact22 and bulk21, real owner and process recovery only',
                whole_original_OFF_F3_atomic13=False,network_receive=network_verified,same_source_bidirectional=False,
                all_reading_records_FOUND=peer_records_verified)
    (out/'report.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))


if __name__=='__main__':
    import sys
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'reader_windows_compact'))
    main()
