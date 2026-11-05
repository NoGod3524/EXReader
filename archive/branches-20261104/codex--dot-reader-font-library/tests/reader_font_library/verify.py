#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Strict same-run evidence verifier with executable rejection cases."""
import copy
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile
import zipfile
from cases import COMMON, POSIX, WINDOWS, NEGATIVE, HARNESS_COMMON
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from check_parallel_integration import download_artifact_zip, fetch, pages, require

PLATFORMS=[('Linux','ubuntu-22.04','Linux'),('Windows','windows-2022','Windows'),('macOS','macos-15','Darwin')]

def strict_json(data):
    def pairs(items):
        out={}
        for k,v in items:
            require(k not in out,'duplicate JSON key');out[k]=v
        return out
    return json.loads(data,object_pairs_hook=pairs)

def validate(run,jobs,artifacts,blobs,source,run_id,attempt,module_tree):
    require(run['head_sha']==source and run['id']==run_id and run['run_attempt']==attempt and run['path']=='.github/workflows/reader-font-library.yml','caller identity')
    require(len({j['id'] for j in jobs})==len(jobs),'duplicate job id')
    require(len({a['id'] for a in artifacts})==len(artifacts) and len({a['name'] for a in artifacts})==len(artifacts),'duplicate artifact id/name')
    accepted=[]
    for platform,runner,system in PLATFORMS:
        job_name=f'font library ({runner})';job=[j for j in jobs if j['name']==job_name]
        require(len(job)==1,'missing/duplicate job');job=job[0]
        require(job['head_sha']==source and job['run_attempt']==attempt and job['status']=='completed' and job['conclusion']=='success','upstream job identity/status')
        name=f'reader-font-library-{platform}-{run_id}-{attempt}';matches=[a for a in artifacts if a['name']==name]
        require(len(matches)==1,'missing/duplicate artifact');a=matches[0]
        require(a['workflow_run']['id']==run_id and a['workflow_run']['head_sha']==source and not a['expired'] and a['size_in_bytes']>0,'artifact identity/size/expiry')
        require(datetime.fromisoformat(a['expires_at'].replace('Z','+00:00'))>datetime.now(timezone.utc),'expired timestamp')
        require(re.fullmatch('sha256:[0-9a-f]{64}',a.get('digest','')) is not None,'missing API digest')
        data=blobs[a['id']];require(len(data)==a['size_in_bytes'] and 'sha256:'+hashlib.sha256(data).hexdigest()==a['digest'],'ZIP size/digest')
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names=z.namelist();require(len(names)==len(set(names)),'duplicate ZIP member')
            require(all(not PurePosixPath(n).is_absolute() and '..' not in PurePosixPath(n).parts and '\\' not in n for n in names),'unsafe ZIP path')
            require(names.count('result.json')==1,'missing original report')
            r=strict_json(z.read('result.json'))
            require(r['accepted'] is True and not r['failures'] and r['source_sha']==source and r['run_id']==run_id and r['attempt']==attempt and r['platform']==system,'report identity/status')
            require(r['module_source_tree']==module_tree,'original module source binding')
            require(r['host_ui_accepted'] is False and r['mobile_accepted'] is False and r['power_loss_accepted'] is False and r['sdk_changed'] is False and r['schema_changed'] is False,'excess claims')
            expected=COMMON+(WINDOWS if system=='Windows' else POSIX)
            require(len(r['checks'])==len(set(r['checks'])) and set(r['checks'])==set(expected),'exact required named cases')
            ids=r['identities'];paths=[i['path'] for i in ids];require(len(paths)==len(set(paths)) and len(paths)>5,'identity list')
            binary='font-probe.exe' if system=='Windows' else 'font-probe';c='font-c.exe' if system=='Windows' else 'font-c'
            module='installed/lib/reader_font_library.lib' if system=='Windows' else 'installed/lib/libreader_font_library.a'
            require({f'binary/{binary}',f'binary/{c}','binary/font-probe.map',module,'installed/include/reader_font_library.h','materials/LICENSE.md','materials/font.ttf','materials/font.otf','materials/font.ttc'}<=set(paths),'missing original module/binary/license/input')
            for i in ids:
                content=z.read(i['path']);require(len(content)==i['bytes']>0 and hashlib.sha256(content).hexdigest()==i['sha256'],'bound file changed: '+i['path'])
            commands=r['commands'];require(len(commands)>20 and [c['number'] for c in commands]==list(range(1,len(commands)+1)),'native command inventory')
            require(len({c['log'] for c in commands})==len(commands) and all(c['log'] in paths for c in commands),'native logs not bound')
            require(sum(not c['expected_success'] for c in commands)==(1 if system=='Windows' else 0),'unexpected native failure inventory')
            for command in commands:
                require(command['returncode']==0 if command['expected_success'] else command['returncode']!=0,'native command exit differs')
            require(commands[0]['arguments'][0].endswith(c) and z.read(commands[0]['log']).decode().strip()=='installed-c-abi-sdk340','original C consumer result')
            require(commands[1]['arguments'][0].endswith(binary) and commands[1]['arguments'][1]=='suite','original C++ consumer binding')
            native=[line.removeprefix('CASE ') for line in z.read(commands[1]['log']).decode().splitlines() if line.startswith('CASE ')]
            native_expected=set(COMMON)-set(HARNESS_COMMON)
            if system!='Windows':native_expected.add('posix-source-and-directory-symlinks-rejected')
            require(len(native)==len(set(native)) and set(native)==native_expected,'original native named cases differ')
            events=r['terminations'];require(len(events)==4 and {e['stage'] for e in events}=={'copy','validated','file-published','committed'},'missing actual termination boundary')
            input_hashes={i['name']:i['sha256'] for i in r['inputs']}
            for event in events:
                require(type(event['pid']) is int and event['pid']>0 and event['returncode']!=0 and event['readiness_file'] in paths,'termination identity/exit')
                require(z.read(event['readiness_file']).decode()==event['stage'],'termination readiness binding')
                expected_hashes=sorted([input_hashes['font.ttf'],input_hashes['font.otf']] if event['stage']=='committed' else [input_hashes['font.ttf']])
                require(event['recovered_hashes']==expected_hashes,'termination recovered set')
            require('reader_font_library' in z.read('binary/font-probe.map').decode(errors='replace') and 'rfl_import_file' in z.read('binary/font-probe.map').decode(errors='replace'),'installed module not linked')
            require(hashlib.sha256(z.read('sdk-font-header.h')).hexdigest()==r['sdk_font_header_sha256'],'installed SDK header binding')
            require({i['name'] for i in r['inputs']}=={'font.ttf','font.otf','font.ttc','LICENSE.md'},'input inventory')
            for i in r['inputs']:
                content=z.read('materials/'+i['name']);require(len(content)==i['bytes'] and hashlib.sha256(content).hexdigest()==i['sha256'] and i['license']=='SIL Open Font License 1.1','font material binding')
            accepted.append({'platform':platform,'job_id':job['id'],'checks':len(r['checks']),'artifact':{k:a[k] for k in ('id','name','size_in_bytes','digest','expires_at')},'identities':ids,'inputs':r['inputs'],'gaps':r['gaps']})
    return accepted

def negative_tests(run,jobs,artifacts,blobs,source,run_id,attempt,module_tree):
    outcomes=[]
    target=next(a for a in artifacts if a['name']==f'reader-font-library-Linux-{run_id}-{attempt}')['id']
    for case in NEGATIVE:
        r,j,a=copy.deepcopy(run),copy.deepcopy(jobs),copy.deepcopy(artifacts);b=dict(blobs)
        first=next(x for x in a if x['id']==target);job=next(x for x in j if x['name']=='font library (ubuntu-22.04)')
        if case=='wrong-source':r['head_sha']='0'*40
        elif case=='wrong-run':r['id']+=1
        elif case=='wrong-attempt':r['run_attempt']+=1
        elif case=='unfinished-job':job['status']='in_progress'
        elif case=='failed-job':job['conclusion']='failure'
        elif case=='duplicate-job':j.append(copy.deepcopy(job))
        elif case=='missing-artifact':a.remove(first)
        elif case=='duplicate-artifact-name':other=copy.deepcopy(first);other['id']+=1000000000;a.append(other)
        elif case=='duplicate-artifact-id':other=copy.deepcopy(first);other['name']+='-other';a.append(other)
        elif case=='empty-artifact':first['size_in_bytes']=0
        elif case=='expired-artifact':first['expired']=True
        elif case=='expired-timestamp':first['expires_at']='2000-01-01T00:00:00Z'
        elif case=='wrong-artifact-source':first['workflow_run']['head_sha']='0'*40
        elif case=='wrong-artifact-run':first['workflow_run']['id']+=1
        elif case=='wrong-zip-size':first['size_in_bytes']+=1
        elif case=='wrong-zip-digest':first['digest']='sha256:'+'0'*64
        else:
            with zipfile.ZipFile(io.BytesIO(b[target])) as z:content={name:z.read(name) for name in z.namelist()}
            report=strict_json(content['result.json'])
            if case=='duplicate-json-key':content['result.json']=content['result.json'].replace(b'{',b'{"accepted": false,',1)
            elif case=='missing-case':report['checks'].pop()
            elif case=='extra-case':report['checks'].append('fabricated-pass')
            elif case=='duplicate-case':report['checks'].append(report['checks'][0])
            elif case=='missing-original-module':report['identities']=[i for i in report['identities'] if not i['path'].endswith('libreader_font_library.a')]
            elif case=='altered-binary':content['binary/font-probe']+=b'changed'
            elif case=='altered-license':content['materials/LICENSE.md']+=b'changed'
            elif case=='wrong-report-source':report['source_sha']='0'*40
            elif case=='wrong-report-attempt':report['attempt']+=1
            elif case=='wrong-report-run':report['run_id']+=1
            elif case=='failed-report':report['accepted']=False
            elif case=='wrong-platform':report['platform']='Windows'
            elif case=='unbound-module-source':report['module_source_tree']='0'*40
            elif case=='altered-native-log':content[report['commands'][1]['log']]+=b'changed'
            elif case=='forged-native-case':
                log=report['commands'][1]['log'];content[log]=content[log].replace(b'CASE empty-library',b'CASE fabricated-native-pass')
                for item in report['identities']:
                    if item['path']==log:item['bytes']=len(content[log]);item['sha256']=hashlib.sha256(content[log]).hexdigest()
            elif case=='missing-native-command':report['commands'].pop(1)
            elif case=='missing-termination':report['terminations'].pop()
            elif case=='zero-termination-exit':report['terminations'][0]['returncode']=0
            if case!='duplicate-json-key':content['result.json']=json.dumps(report).encode()
            stream=io.BytesIO()
            with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as z:
                for name,data in content.items():z.writestr(name,data)
                if case=='duplicate-zip-member':z.writestr('result.json',content['result.json'])
            b[target]=stream.getvalue();first['size_in_bytes']=len(b[target]);first['digest']='sha256:'+hashlib.sha256(b[target]).hexdigest()
        try:validate(r,j,a,b,source,run_id,attempt,module_tree)
        except (ValueError,KeyError,AssertionError,zipfile.BadZipFile) as error:outcomes.append({'case':case,'rejected':True,'reason':str(error)})
        else:raise AssertionError('verifier accepted '+case)
    require(len(outcomes)==len(NEGATIVE),'negative coverage');return outcomes

def main():
    require(os.environ.get('GITHUB_ACTIONS')=='true','Actions only')
    out=Path('build/font-verified');out.mkdir(parents=True,exist_ok=True)
    source=os.environ['GITHUB_SHA'];run_id=int(os.environ['GITHUB_RUN_ID']);attempt=int(os.environ['GITHUB_RUN_ATTEMPT'])
    summary={'accepted':False,'source_sha':source,'run_id':run_id,'attempt':attempt,'failures':[]}
    try:
        run=fetch(f'actions/runs/{run_id}');jobs=pages(f'actions/runs/{run_id}/attempts/{attempt}/jobs','jobs');artifacts=pages(f'actions/runs/{run_id}/artifacts','artifacts')
        blobs={}
        for a in artifacts:
            if a['name'].startswith('reader-font-library-'):
                with tempfile.TemporaryFile() as stream:download_artifact_zip(a['id'],stream);stream.seek(0);blobs[a['id']]=stream.read()
        module_tree=subprocess.check_output(['git','rev-parse',source+':apps/reader/font-library'],text=True).strip()
        summary['platforms']=validate(run,jobs,artifacts,blobs,source,run_id,attempt,module_tree)
        summary['negative_tests']=negative_tests(run,jobs,artifacts,blobs,source,run_id,attempt,module_tree)
        summary['accepted']=True
    except BaseException as error:summary['failures'].append(repr(error));raise
    finally:(out/'result.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary),flush=True)
if __name__=='__main__':main()
