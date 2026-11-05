"""Actions-only final-product evidence gate: authenticates root-supplied original runs, never splices or rebuilds them."""
import argparse
import copy
from datetime import datetime,timedelta,timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import zipfile

SDK_341='edddc463c06ed5731195cdb8f06b2df6dff7699e'
SDK_340='9854061be331fe603a1822d9b2b36ee357154927'
HEX40=re.compile('[0-9a-f]{40}');HEX64=re.compile('[0-9a-f]{64}')
HOSTS={'windows','gtk','android','macos','ios'}
UI_KINDS={'native_host','emulator'}
BINARY=('.exe','.dll','.so','.dylib','.apk','.aab','.a','.lib')
SLACK=timedelta(seconds=5)
# key = entry field that names the covered cell; kinds = evidence kinds allowed to grant it.
SCOPES={
 'sdk':dict(key='platform',values={'sdk'},kinds={'native_host','static_metadata'}),
 'modules':dict(key='platform',values={'modules'},kinds={'native_host','static_metadata'}),
 'host':dict(key='platform',values=HOSTS,kinds=UI_KINDS,programs=True),
 'bidirectional':dict(key='direction',values={'android_to_apple','apple_to_android'},kinds=UI_KINDS,programs=True),
 'default_ui':dict(key='platform',values=HOSTS,kinds=UI_KINDS,programs=True),
 'performance':dict(key='platform',values=HOSTS,kinds={'native_host'},programs=True,budget=True),
 'packaging':dict(key='platform',values=HOSTS,kinds={'native_host'},programs=True),
 'physical_device':dict(key='platform',values={'android','ios'},kinds={'physical_device'},programs=True)}


class GateError(Exception):pass


def need(condition,message):
    if not condition:raise GateError(message)


def ts(value):return datetime.fromisoformat(value.replace('Z','+00:00'))


def file_sha(path):
    digest=hashlib.sha256()
    with open(path,'rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
    return digest.hexdigest()


def member_sha(archive,name):
    digest=hashlib.sha256()
    with archive.open(name) as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
    return digest.hexdigest()


class Live:
    """GitHub REST through the runner's gh; the ZIP is the original bytes, hashed here and then deleted."""
    def __init__(self,repo):self.repo=repo

    def _gh(self,*args):
        return subprocess.run(['gh','api',*args],check=True,capture_output=True,timeout=900).stdout

    def run(self,run_id):return json.loads(self._gh('repos/%s/actions/runs/%d'%(self.repo,run_id)))

    def _rows(self,path,key):
        out=self._gh('--paginate','repos/%s/%s?per_page=100'%(self.repo,path),'--jq','.%s[]'%key).decode()
        return [json.loads(line) for line in out.splitlines() if line.strip()]

    def jobs(self,run_id,attempt):return self._rows('actions/runs/%d/attempts/%d/jobs'%(run_id,attempt),'jobs')

    def artifacts(self,run_id):return self._rows('actions/runs/%d/artifacts'%run_id,'artifacts')

    def zip(self,artifact_id,folder):
        path=Path(folder)/('%d.zip'%artifact_id)
        with open(path,'wb') as out:
            subprocess.run(['gh','api','repos/%s/actions/artifacts/%d/zip'%(self.repo,artifact_id)],check=True,stdout=out,timeout=1800)
        return path


def inspect_zip(path,decl,source,run_id,attempt):
    with zipfile.ZipFile(path) as archive:
        need(archive.testzip() is None,'corrupt ZIP')
        infos={info.filename:info for info in archive.infolist() if not info.is_dir()}
        binaries=[dict(member=name,bytes=info.file_size,sha256=member_sha(archive,name))
                  for name,info in sorted(infos.items()) if name.lower().endswith(BINARY)][:200]
        programs=decl.get('programs',{})
        need(isinstance(programs,dict),'programs must map member to sha256')
        for member,want in programs.items():
            need(member in infos,'program member absent: '+member)
            need(HEX64.fullmatch(str(want)) is not None and member_sha(archive,member)==want,'program hash differs: '+member)
        subs={'$source':source,'$run':str(run_id),'$attempt':str(attempt)}
        for report in decl.get('reports',[]):
            member=report.get('member')
            need(member in infos and infos[member].file_size<=32*1024**2 and isinstance(report.get('equals'),dict),'report member absent/large/malformed')
            document=json.loads(archive.read(member))
            for dotted,want in report['equals'].items():
                current=document
                for part in dotted.split('.'):
                    need(isinstance(current,dict) and part in current,'report field absent: '+dotted)
                    current=current[part]
                want=subs.get(want,want) if isinstance(want,str) else want
                need(current==want or (isinstance(want,str) and str(current)==want),'report identity differs: '+dotted)
        return dict(artifact=decl['name'],members=len(infos),sample=sorted(infos)[:3],binaries=binaries,programs_verified=len(programs))


def authenticate(entry,api,now,folder):
    """Return proof only if one real, completed, same-source same-attempt run and its original ZIP bytes match the declaration."""
    need(isinstance(entry,dict),'entry malformed')
    for field in ('run_id','attempt'):need(type(entry.get(field)) is int and entry[field]>0,field+' invalid')
    source=entry.get('source_sha');need(isinstance(source,str) and HEX40.fullmatch(source) is not None,'source_sha invalid')
    jobs_declared=entry.get('jobs')
    need(isinstance(entry.get('workflow'),str) and isinstance(jobs_declared,list) and jobs_declared and
         all(isinstance(name,str) for name in jobs_declared) and len(set(jobs_declared))==len(jobs_declared),'workflow/jobs declaration invalid')
    need(isinstance(entry.get('artifacts'),list) and entry['artifacts'],'artifact declaration absent')
    run_id,attempt=entry['run_id'],entry['attempt']
    run=api.run(run_id)
    need(run.get('id')==run_id and run.get('head_sha')==source,'run source differs from declared source')
    need(str(run.get('path','')).split('@')[0]==entry['workflow'],'run workflow differs')
    need(run.get('status')=='completed' and run.get('conclusion')=='success','run did not complete successfully')
    need(type(run.get('run_attempt')) is int and attempt<=run['run_attempt'],'declared attempt does not exist')
    jobs=api.jobs(run_id,attempt)
    names=[job['name'] for job in jobs];need(len(names)==len(set(names)),'duplicate job names')
    missing=[name for name in jobs_declared if name not in names];need(not missing,'required jobs missing: '+', '.join(missing))
    for job in jobs:
        need(job.get('head_sha')==source and job.get('run_id')==run_id and job.get('run_attempt')==attempt and
             job.get('status')=='completed','foreign/mixed-attempt/incomplete job: '+job['name'])
        required=job['name'] in jobs_declared
        need(job.get('conclusion')=='success' if required else job.get('conclusion') in ('success','skipped'),'job not successful: '+job['name'])
        need(all(step.get('conclusion') in ('success','skipped') for step in job.get('steps',[])),'hidden failed step in '+job['name'])
    active=[job for job in jobs if job['conclusion']!='skipped']
    need(active and all(job.get('started_at') and job.get('completed_at') for job in active),'job timestamps absent')
    window=(min(ts(job['started_at']) for job in active),max(ts(job['completed_at']) for job in active))
    live={row['id']:row for row in api.artifacts(run_id)}
    seen=set();proofs=[]
    for decl in entry['artifacts']:
        need(isinstance(decl,dict) and type(decl.get('id')) is int and isinstance(decl.get('name'),str) and
             HEX64.fullmatch(str(decl.get('sha256'))) is not None and type(decl.get('bytes')) is int,'artifact declaration malformed')
        need(decl['id'] not in seen,'duplicate artifact declaration');seen.add(decl['id'])
        row=live.get(decl['id']);need(row is not None and row.get('name')==decl['name'],'declared artifact is not in this run')
        need(row.get('expired') is False and ts(row['expires_at'])>now,'artifact ZIP expired: '+decl['name'])
        origin=row.get('workflow_run') or {}
        need(origin.get('id')==run_id and origin.get('head_sha')==source,'artifact source/run differs')
        need(row.get('digest')=='sha256:'+decl['sha256'] and row.get('size_in_bytes')==decl['bytes'],'declared digest/bytes differ from API')
        need(window[0]-SLACK<=ts(row['created_at'])<=window[1]+SLACK,'artifact outside this attempt window (mixed attempt)')
        path=api.zip(decl['id'],folder)
        try:
            need(path.stat().st_size==decl['bytes'] and file_sha(path)==decl['sha256'],'downloaded ZIP bytes/digest differ')
            proofs.append(dict(id=decl['id'],bytes=decl['bytes'],sha256=decl['sha256'],expires_at=row['expires_at'],**inspect_zip(path,decl,source,run_id,attempt)))
        finally:path.unlink()
    return dict(run_id=run_id,attempt=attempt,source_sha=source,jobs=[dict(id=job['id'],name=job['name'],conclusion=job['conclusion']) for job in jobs],
                artifacts=proofs,programs_verified=sum(row['programs_verified'] for row in proofs)>0)


def classify(entry,auth,product):
    """Decide whether an authentic entry may grant its scope cell for the final product source."""
    spec=SCOPES.get(entry.get('scope'))
    if spec is None:return 'refused','unknown scope'
    if entry.get('kind') not in spec['kinds']:return 'refused','evidence kind %r cannot grant %s'%(entry.get('kind'),entry['scope'])
    if entry.get(spec['key']) not in spec['values']:return 'refused','%s %r is not a %s cell'%(spec['key'],entry.get(spec['key']),entry['scope'])
    budget=entry.get('budget')
    if spec.get('budget') and not (isinstance(budget,dict) and budget.get('approved') is True and HEX64.fullmatch(str(budget.get('sha256'))) is not None):
        return 'refused','performance budget is not approved'
    if entry['scope']=='sdk' and (entry.get('sdk_source'),entry.get('frozen_sdk_source'))!=(SDK_341,SDK_340):
        return 'refused','SDK identities are not the approved 3.41 / frozen 3.40 pair'
    if product and entry['source_sha']!=product:return 'refused','source differs from product source'
    pending=[]
    if not product:pending.append('product source not integrated')
    if spec.get('programs') and not auth['programs_verified']:pending.append('actual program hashes not declared')
    return ('authentic_not_counted','; '.join(pending)) if pending else ('counts','')


def evaluate(rows):
    """rows: (entry,status,reason). A scope is verified only when every cell has a counting entry."""
    scopes={}
    for name,spec in SCOPES.items():
        mine=[row for row in rows if row[0].get('scope')==name]
        covered={row[0].get(spec['key']) for row in mine if row[1]=='counts'}
        missing=sorted(spec['values']-covered)
        refused=[row for row in mine if row[1]=='refused']
        scopes[name]=dict(status='verified' if not missing else 'refused' if refused else 'pending',missing=missing,
                          reasons=sorted({row[2] for row in mine if row[1]!='counts' and row[2]}))
    return scopes


def flip(text):return ('0' if text[0]!='0' else '1')+text[1:]


def refused(call):
    try:call()
    except GateError as error:return True,str(error)
    return False,'accepted'


def derived_controls(base,auth,api,now,folder):
    """Mutate one real entry; every mutation must be refused by the same live checks."""
    controls=[];member=auth['artifacts'][0]['sample'][0]
    def mutate(**changes):
        entry=copy.deepcopy(base)
        for key,value in changes.items():entry[key]=value
        return entry
    def with_artifact(**changes):
        entry=copy.deepcopy(base);entry['artifacts'][0].update(changes);return entry
    cases=[('foreign source',lambda:authenticate(mutate(source_sha=flip(base['source_sha'])),api,now,folder)),
           ('mixed attempt',lambda:authenticate(mutate(attempt=base['attempt']+50),api,now,folder)),
           ('missing job',lambda:authenticate(mutate(jobs=[*base['jobs'],'required job that never ran']),api,now,folder)),
           ('wrong digest',lambda:authenticate(with_artifact(sha256=flip(base['artifacts'][0]['sha256'])),api,now,folder)),
           ('wrong program hash',lambda:authenticate(with_artifact(programs={member:'0'*64}),api,now,folder)),
           ('expired ZIP',lambda:authenticate(base,api,now+timedelta(days=4000),folder))]
    for name,call in cases:
        try:ok,reason=refused(call)
        except Exception as error:ok,reason=True,type(error).__name__+': '+str(error)[:200]
        controls.append(dict(name=name,refused=ok,reason=reason))
    fake=dict(programs_verified=True)
    def one(**changes):
        entry=copy.deepcopy(base);entry.update(changes);return classify(entry,fake,base['source_sha'])
    simulator=one(scope='physical_device',platform='android',kind='emulator')
    budget=one(scope='performance',platform='windows',kind='native_host',budget=dict(approved=False,sha256='0'*64))
    one_way=evaluate([(dict(scope='bidirectional',direction='android_to_apple'),'counts','')])['bidirectional']['status']
    controls+= [dict(name='simulator only',refused=simulator[0]=='refused',reason=simulator[1]),
                dict(name='budget not approved',refused=budget[0]=='refused',reason=budget[1]),
                dict(name='one direction only',refused=one_way!='verified',reason='bidirectional '+one_way)]
    return controls


def validate_table(table):
    need(isinstance(table,dict) and table.get('schema')==1 and set(table)<={'schema','product_source','entries','negative_controls'},'run table malformed')
    product=table.get('product_source')
    need(product is None or (isinstance(product,str) and HEX40.fullmatch(product) is not None),'product_source invalid')
    for key in ('entries','negative_controls'):
        need(isinstance(table.get(key,[]),list) and len(table.get(key,[]))<=64,key+' malformed/unbounded')
    return product


def summarize(entry):
    return {key:entry.get(key) for key in ('scope','platform','direction','kind','run_id','attempt','source_sha','workflow') if key in entry}


def collect(table,api,now,folder,with_derived=False):
    result=dict(schema=1,gate_accepted=False,complete_product=False,performance_accepted=False,physical_device_execution=False,
                bidirectional_accepted=False,verifier_source=os.environ.get('GITHUB_SHA'),validation_run_id=os.environ.get('GITHUB_RUN_ID'),
                validation_attempt=os.environ.get('GITHUB_RUN_ATTEMPT'),product_source=None,entries=[],negative_controls=[],
                derived_controls=[],scopes={},problems=[])
    try:product=validate_table(table)
    except GateError as error:
        result['problems'].append(str(error));result['scopes']=evaluate([]);return result
    result['product_source']=product
    rows=[];best=None
    for entry in table.get('entries',[]):
        item=dict(entry=summarize(entry))
        try:
            auth=authenticate(entry,api,now,folder);status,reason=classify(entry,auth,product)
            item.update(authentic=True,proof=auth)
            size=sum(row['bytes'] for row in auth['artifacts'])
            if best is None or size<best[0]:best=(size,entry,auth)
        except Exception as error:
            status,reason='refused',type(error).__name__+': '+str(error)[:300];item.update(authentic=False)
        item.update(status=status,reason=reason);result['entries'].append(item);rows.append((entry,status,reason))
    for entry in table.get('negative_controls',[]):
        try:authenticate(entry,api,now,folder);ok,reason=False,'real negative control was authenticated'
        except Exception as error:ok,reason=True,type(error).__name__+': '+str(error)[:300]
        result['negative_controls'].append(dict(entry=summarize(entry),refused=ok,reason=reason))
        if not ok:result['problems'].append('negative control accepted: '+json.dumps(summarize(entry)))
    if with_derived:
        if best is None:result['problems'].append('no authentic real entry to derive negative controls from')
        else:
            result['derived_controls']=derived_controls(best[1],best[2],api,now,folder)
            result['problems']+=['derived control accepted: '+row['name'] for row in result['derived_controls'] if not row['refused']]
    result['scopes']=evaluate(rows)
    flags=lambda name:result['scopes'][name]['status']=='verified'
    result['performance_accepted']=flags('performance');result['physical_device_execution']=flags('physical_device')
    result['bidirectional_accepted']=flags('bidirectional')
    result['complete_product']=product is not None and all(flags(name) for name in SCOPES) and not result['problems']
    result['gate_accepted']=not result['problems']
    return result


def main():
    need(os.environ.get('GITHUB_ACTIONS')=='true','Actions only')
    parser=argparse.ArgumentParser();parser.add_argument('--self-test',action='store_true');parser.add_argument('--table')
    parser.add_argument('--out',default='build/reader-final-c01');parser.add_argument('--derived-controls',action='store_true')
    parser.add_argument('--require-complete',action='store_true');args=parser.parse_args()
    if args.self_test:
        from test_final_gate import run_tests
        run_tests();return 0
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    table=json.loads(Path(args.table).read_text(encoding='utf-8'))
    with tempfile.TemporaryDirectory() as folder:
        result=collect(table,Live(os.environ['GITHUB_REPOSITORY']),datetime.now(timezone.utc),folder,args.derived_controls)
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result),flush=True)
    return 0 if result['gate_accepted'] and (result['complete_product'] or not args.require_complete) else 1


if __name__=='__main__':raise SystemExit(main())
