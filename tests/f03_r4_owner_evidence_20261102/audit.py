#!/usr/bin/env python3
"""Fixed R4 evidence only; never executes project or archived content."""
import hashlib,json,os,re,stat,subprocess,sys,urllib.request,urllib.error,urllib.parse,zipfile
from pathlib import Path
import xml.etree.ElementTree as ET
C=json.loads(Path(__file__).with_name('contract.json').read_text())
OUT=Path('build/f03-r4-owner-evidence')
OUT.mkdir(parents=True,exist_ok=True)
REPORT={'schema':C['schema'],'accepted':False,'full_f03_accepted':False,
        'provider_fully_authenticated':False,'product_reexecuted':False,
        'evidence_verified':False,'failure_classification':'evidence_not_authenticated_not_product_failure',
        'problems':[],'checks':[]}
def need(ok,message):
    if not ok:raise ValueError(message)
def save(name,value):
    (OUT/name).write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')
def sha(raw):return hashlib.sha256(raw).hexdigest()
def git(*args):
    return subprocess.check_output(['git',*args],text=True).strip()
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args):return None
def api(path):
    request=urllib.request.Request('https://api.github.com/repos/'+C['repository']+'/'+path,
        headers={'Authorization':'Bearer '+os.environ['GH_TOKEN'],'Accept':'application/vnd.github+json',
                 'X-GitHub-Api-Version':'2022-11-28','User-Agent':'f03-fixed-evidence'})
    with urllib.request.build_opener(NoRedirect).open(request,timeout=60) as response:
        raw=response.read(2097153);need(len(raw)<=2097152,'API response cap')
    return json.loads(raw)
def check(name,ok):
    REPORT['checks'].append({'id':name,'passed':bool(ok)})
    need(ok,name)
def main():
    need(os.environ.get('GITHUB_ACTIONS')=='true','Actions only')
    need(os.environ['GITHUB_REPOSITORY']==C['repository'],'controller repository')
    need(os.environ['GITHUB_REF']=='refs/heads/'+C['branch'],'controller branch')
    need(os.environ['GITHUB_EVENT_NAME']=='push' and os.environ['GITHUB_RUN_ATTEMPT']=='1','unique push A1')
    head=git('rev-parse','HEAD')
    need(head==os.environ['GITHUB_SHA'],'checkout identity')
    need(git('show','-s','--format=%P','HEAD')==C['base'],'single fixed parent')
    need(C['marker'] in git('show','-s','--format=%B','HEAD'),'fixed marker')
    changes=git('diff','--name-status',C['base'],'HEAD').splitlines()
    need(sorted(changes)==sorted('A\t'+p for p in C['paths']),'strict three additions')
    REPORT['controller']={'source_sha':head,'run_id':os.environ['GITHUB_RUN_ID'],'attempt':'1'}
    run=api('actions/runs/'+str(C['run_id']))
    job=api('actions/jobs/'+str(C['job_id']))
    artifact=api('actions/artifacts/'+str(C['artifact_id']))
    save('producer-run.json',run);save('producer-job.json',job);save('producer-artifact.json',artifact)
    expected={'source_sha':C['base'],'run_id':str(C['run_id']),'attempt':str(C['attempt'])}
    REPORT['producer']=expected
    check('producer_run',run['id']==C['run_id'] and run['run_attempt']==1 and
          run['head_sha']==C['base'] and run['head_branch']==C['producer_branch'] and
          run['repository']['full_name']==C['repository'] and run['event']=='push' and
          run['status']=='completed' and run['conclusion']=='failure')
    check('producer_job',job['id']==C['job_id'] and job['run_id']==C['run_id'] and
          job['head_sha']==C['base'] and job['run_attempt']==1 and
          job['status']=='completed' and job['conclusion']=='failure')
    ar=artifact['workflow_run']
    check('producer_artifact',artifact['id']==C['artifact_id'] and
          artifact['name']==C['artifact_name'] and artifact['size_in_bytes']==C['artifact_bytes'] and
          artifact['digest']=='sha256:'+C['artifact_sha256'] and not artifact['expired'] and
          ar['id']==C['run_id'] and ar['head_sha']==C['base'] and ar['head_branch']==C['producer_branch'] and
          ar['repository_id']==run['repository']['id'] and ar['head_repository_id']==run['head_repository']['id'])
    request=urllib.request.Request('https://api.github.com/repos/'+C['repository']+
        '/actions/artifacts/'+str(C['artifact_id'])+'/zip',
        headers={'Authorization':'Bearer '+os.environ['GH_TOKEN'],'User-Agent':'f03-fixed-evidence'})
    try:
        urllib.request.build_opener(NoRedirect).open(request,timeout=60)
        raise ValueError('expected authenticated archive redirect')
    except urllib.error.HTTPError as error:
        need(error.code==302,'archive redirect status')
        url=error.headers['Location']
    parsed=urllib.parse.urlparse(url)
    need(parsed.scheme=='https' and parsed.username is None and parsed.password is None and
         (parsed.hostname.endswith('.blob.core.windows.net') or
          parsed.hostname.endswith('.githubusercontent.com') or
          parsed.hostname.endswith('.amazonaws.com')),'archive redirect host')
    # Token never follows the signed redirect. No retries and no archive extraction.
    archive=Path(os.environ['RUNNER_TEMP'])/'f03-fixed-r4-owner.zip'
    need(not archive.exists(),'exclusive archive destination')
    total=0;digest=hashlib.sha256()
    try:
        with urllib.request.build_opener(NoRedirect).open(url,timeout=120) as response,archive.open('xb') as target:
            while True:
                block=response.read(1048576)
                if not block:break
                total+=len(block);need(total<=C['artifact_bytes'],'archive byte cap')
                digest.update(block);target.write(block)
        check('archive_digest',total==C['artifact_bytes'] and digest.hexdigest()==C['artifact_sha256'])
        with zipfile.ZipFile(archive) as z:
            infos=z.infolist();need(len(infos)<=C['index_entries_max'],'index cap')
            index=[];seen=set();declared=0
            for entry in infos:
                name=entry.filename
                need(entry.orig_filename==name and '\x00' not in entry.orig_filename,'truncated archive name')
                need(name not in seen,'duplicate archive path');seen.add(name)
                need(name and not name.startswith('/') and '\\' not in name and
                     '\x00' not in name and ':' not in name and
                     all(v not in ('','..','.') for v in name.rstrip('/').split('/')),'unsafe archive path')
                mode=entry.external_attr>>16
                kind=stat.S_IFMT(mode)
                need(kind in (0,stat.S_IFREG,stat.S_IFDIR),'archive link/special file')
                need(kind==0 or (kind==stat.S_IFDIR)==entry.is_dir(),'directory mode/name mismatch')
                need(not entry.flag_bits&1,'encrypted member')
                need(entry.compress_type in (zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED),'compression method')
                declared+=entry.file_size
                need(declared<=C['archive_declared_bytes_max'],'declared archive cap')
                need(entry.file_size<=max(1,entry.compress_size)*C['compression_ratio_max'],'compression ratio')
                index.append({'path':name,'bytes':entry.file_size,'compressed_bytes':entry.compress_size,'crc32':entry.CRC})
            save('archive-index.json',index)
            roots=[prefix for prefix in ('','build/') if all(prefix+p in seen for p in C['members'])]
            need(len(roots)==1,'missing/ambiguous required members: index only, no fallback')
            prefix=roots[0]
            need(not any(other+p in seen for other in ('','build/') if other!=prefix for p in C['members']),
                 'mixed/duplicate evidence roots')
            selected={}
            for name,limit in C['members'].items():
                entry=z.getinfo(prefix+name)
                need(not entry.is_dir() and stat.S_IFMT(entry.external_attr>>16) in (0,stat.S_IFREG)
                     and entry.file_size<=limit,'selected member type/cap')
                with z.open(entry) as stream:raw=stream.read(limit+1)
                need(len(raw)==entry.file_size and len(raw)<=limit,'member byte count')
                selected[name]=raw
            need(sum(map(len,selected.values()))<=C['selected_bytes_max'],'selected total cap')
            REPORT['selected']={}
            for name,raw in selected.items():
                destination=OUT/'selected'/name;destination.parent.mkdir(parents=True,exist_ok=True)
                destination.write_bytes(raw)
                REPORT['selected'][name]={'archive_path':prefix+name,'bytes':len(raw),'sha256':sha(raw)}
    finally:
        if archive.exists():archive.unlink()
    def raw(name):return selected['owner-android/'+name]
    def text(name):return raw(name).decode('utf-8')
    device=json.loads(raw('device-report.json'))
    check('source_api_abi',text('source.txt').strip()==C['base'] and
          text('device-api.txt').strip()=='34' and text('device-abi.txt').strip()=='x86_64')
    check('device_identity',all(device.get(k)==v for k,v in expected.items()))
    names=C['names'];checks=device['checks']
    check('device_18',device['api']==34 and device['abi']=='x86_64' and device['count']==18 and
          device['failed']==0 and len(checks)==18 and {v['id'] for v in checks}==set(names) and
          all(v['pass'] is True for v in checks))
    manual=text('owner-instrumentation.txt');starts=[];ends=[];status={}
    check('manual_ending',re.findall(r'^INSTRUMENTATION_CODE: (-?\d+)\s*$',manual,re.M)==['-1'] and
          'OK (18 tests)' in manual and 'FAILURES' not in manual and 'shortMsg=' not in manual)
    for line in manual.splitlines():
        if line.startswith('INSTRUMENTATION_STATUS: '):
            key,_,value=line[len('INSTRUMENTATION_STATUS: '):].partition('=');status[key]=value
        elif line.startswith('INSTRUMENTATION_STATUS_CODE: '):
            code=int(line.split(':',1)[1])
            need(code in (0,1) and status.get('class')=='org.exreader.host.ProductOwnerTest' and
                 status.get('numtests')=='18','manual class/count/status')
            (starts if code==1 else ends).append(status.get('test'));status={}
    check('manual_18',len(starts)==len(ends)==18 and starts==ends and set(ends)==set(names))
    xml_name='owner-reports/debug/TEST-emulator-5554 - 14-_app-.xml'
    xml=raw(xml_name);need(b'<!DOCTYPE' not in xml.upper() and b'<!ENTITY' not in xml.upper(),'XML external declarations')
    tree=ET.fromstring(xml);xml_names=[]
    for suite in tree.iter('testsuite'):
        need(not any(int(suite.get(k,'0')) for k in ('failures','errors','skipped')),'XML suite failures')
    for case in tree.iter('testcase'):
        need(case.get('classname')=='org.exreader.host.ProductOwnerTest' and
             not any(case.find(k) is not None for k in ('failure','error','skipped')),'XML case failure/class')
        xml_names.append(case.get('name'))
    check('xml_18',len(xml_names)==18 and set(xml_names)==set(names))
    for phase in ('before','after'):
        seed=text('seed-'+phase+'.txt');recover=text('recover-'+phase+'.txt')
        check('kill_'+phase,'INSTRUMENTATION_RESULT: shortMsg=Process crashed.' in seed and
              'EXR_OWNER_RECOVERED recover-'+phase in recover and
              re.findall(r'^INSTRUMENTATION_CODE: (-?\d+)\s*$',recover,re.M)==['-1'] and
              'EXR_OWNER_PHASE_FAILED' not in recover and
              text('witness-'+phase+'.txt')==('1,1,0' if phase=='before' else '1,1,1'))
    old=json.loads(raw('result.json'))
    check('original_failure_preserved',all(old.get(k)==v for k,v in expected.items()) and
          old['accepted'] is False and 'owner device execution failed' in old['problems'])
    REPORT['observed']={'device_checks':len(checks),'manual_starts':len(starts),'manual_completions':len(ends),
                        'xml_cases':len(xml_names),'typed_kill_phases':['before','after']}
    REPORT['evidence_verified']=True
    REPORT['failure_classification']=None
try:
    main()
except Exception as error:
    REPORT['problems'].append(type(error).__name__+': '+str(error)[:1000])
finally:
    save('result.json',REPORT)
    print(json.dumps(REPORT,sort_keys=True))
if not REPORT['evidence_verified']:sys.exit(1)
