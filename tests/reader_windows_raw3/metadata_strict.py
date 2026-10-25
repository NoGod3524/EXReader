"""Authenticate both whole installed-profile jobs and actual same-run binaries."""
import datetime
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
from check_parallel_integration import download_artifact_zip,fetch,require


def main():
    require(os.environ.get('GITHUB_ACTIONS')=='true','Actions only')
    source,run,attempt=(os.environ[key] for key in ('GITHUB_SHA','GITHUB_RUN_ID','GITHUB_RUN_ATTEMPT'))
    names={'source-preflight','installed-metadata (windows-2022)','installed-metadata (ubuntu-latest)'}
    jobs=fetch('actions/runs/'+run+'/attempts/'+attempt+'/jobs?per_page=100')
    producers=[row for row in jobs['jobs'] if row['name'] in names]
    require(jobs['total_count']==4 and len(producers)==3 and {r['name'] for r in producers}==names,'incomplete producers')
    require(all(r['status']=='completed' and r['conclusion']=='success' and r['head_sha']==source and
                r['run_attempt']==int(attempt) for r in producers),'source/attempt or complete job differs')
    artifacts=fetch('actions/runs/'+run+'/artifacts?per_page=100')['artifacts']
    expected={'windows-raw3-source-only-'+run+'-'+attempt}
    expected|={'windows-raw3-metadata-'+platform+'-'+run+'-'+attempt for platform in ('Windows','Linux')}
    selected=[row for row in artifacts if row['name'] in expected]
    require(len(selected)==3 and {r['name'] for r in selected}==expected,'missing/duplicate artifact')
    expected_checks=re.findall(r"record\('([^']+)'\)",(ROOT/'tests/reader_metadata/check_metadata.py').read_text())
    require(len(expected_checks)==len(set(expected_checks))==29,'original contract differs')
    now=datetime.datetime.now(datetime.timezone.utc)
    retained=[]
    for item in selected:
        require(not item['expired'] and 0<item['size_in_bytes']<=512*1024**2 and item['workflow_run']['id']==int(run)
                and item['workflow_run']['head_sha']==source and datetime.datetime.fromisoformat(
                    item['expires_at'].replace('Z','+00:00'))>now,'expired or foreign artifact')
        raw=download_artifact_zip(item['id'])
        require(len(raw)==item['size_in_bytes'] and 'sha256:'+hashlib.sha256(raw).hexdigest()==item['digest'],'original ZIP differs')
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            require(len(archive.namelist())==len(set(archive.namelist())),'duplicate member')
            def report(path):
                require(0<archive.getinfo(path).file_size<=16*1024**2,'report size differs')
                value=json.loads(archive.read(path))
                require(value['source_sha']==source and str(value['run_id'])==run and str(value['attempt'])==attempt,'report identity differs')
                return value
            value=report('report.json')
            if item['name'].startswith('windows-raw3-source-only-'):
                require(value['source_preflight_passed'] is True and value['accepted'] is False and
                        value['host_raw3_implemented'] is False,'source-only boundary differs')
            else:
                require(value['accepted'] is True and value['host_raw3_accepted'] is False and value['mixed_family_refusals']==2,
                        'metadata scope differs')
                rows=value['profiles']
                require(len(rows)==2 and {r['profile'] for r in rows}=={'legacy','raw'},'incomplete profiles')
                suffix='.exe' if '-Windows-' in item['name'] else ''
                for row in rows:
                    name=row['profile']
                    original=report(name+'-original-checks/result.json')
                    require(row['original_checks']==29 and row['profile_open_passed'] is True and original['accepted'] is True
                            and original['count']==29 and original['checks']==expected_checks,'original29 incomplete')
                    require(original['desktop_ui_accepted'] is False and original['schema1_changed'] is False and
                            original['wire_changed'] is False and original['sdk_database_writes'] is False,'original scope differs')
                    binaries=row['binaries']
                    require(set(binaries)=={'metadata-consumer','metadata-c-consumer','command-consumer','metadata-profile'},'binaries missing')
                    for target,digest in binaries.items():
                        path=name+'-consumer/'+target+suffix
                        require(0<archive.getinfo(path).file_size<=128*1024**2,'binary size differs')
                        require(hashlib.sha256(archive.read(path)).hexdigest()==digest,'actual binary hash differs')
                    require(original['consumer_sha256']==binaries['metadata-consumer'],'original consumer identity differs')
        retained.append({key:item[key] for key in ('id','name','size_in_bytes','digest','expires_at')})
    out=ROOT/'build/windows-raw3-metadata-summary'
    out.mkdir(parents=True,exist_ok=True)
    value=dict(accepted=True,source_sha=source,run_id=run,attempt=attempt,artifacts=retained,
               jobs=[r['id'] for r in producers],platforms=['Windows','Linux'],profiles=['legacy','raw'],
               original_checks_per_platform_profile=29,host_raw3_accepted=False,
               scope='installed desktop metadata packages only; no SDK, host UI or interchange grant')
    (out/'report.json').write_text(json.dumps(value,indent=2)+'\n')
    print(json.dumps(value),flush=True)


if __name__=='__main__':
    main()
