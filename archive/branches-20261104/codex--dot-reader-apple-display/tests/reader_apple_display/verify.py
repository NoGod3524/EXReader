#!/usr/bin/env python3
"""Strict Actions-only provenance verifier. No runtime claims from mocks or source scans."""
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import plistlib
import urllib.error
import urllib.request
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PLATFORMS = ('macos', 'iphone', 'ipad', 'iphoneos')


def require(ok, message):
    if not ok: raise ValueError(message)


def sha(data): return hashlib.sha256(data).hexdigest()


def pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, 'duplicate JSON key: ' + key)
        result[key] = value
    return result


def load(data): return json.loads(data, object_pairs_hook=pairs)


def expected():
    return {k: os.environ[v] for k,v in [('source','GITHUB_SHA'),('run','GITHUB_RUN_ID'),('attempt','GITHUB_RUN_ATTEMPT')]}


def match_identity(value, want, kind):
    for key in ('source','run','attempt'): require(value.get(key) == want[key], 'wrong '+key)
    require(value.get('platform') == kind, 'wrong platform')


def check_cases(report, names, contract):
    rows=report['cases']; actual=[c['name'] for c in rows]
    require(len(actual)==len(set(actual)) and set(actual)==set(names), 'duplicate/missing/extra named case')
    for c in rows:
        require(c['status'] in ('PASS','PENDING'), 'failed/invalid case '+c['name'])
        require(isinstance(c.get('detail'),str) and bool(c['detail']), 'missing case detail')
        if c['status']=='PENDING': require(c['name'] in contract['pending_allowed'], 'unpermitted pending case')
    require(report.get('physicalSleepVerified') is False and report.get('physicalBacklightVerified') is False,
            'physical capability overclaim')
    return rows


def verify_payload(files, want, kind):
    contract=load((HERE/'contract.json').read_bytes())
    b=load(files['build-identity.json']); match_identity(b,want,kind)
    require(b['schema']==1, 'build schema')
    for name in ('binary','library','header'):
        data=files[b[name]]
        require(len(data)>0 and sha(data)==b[name+'SHA256'], 'wrong actual '+name+' bytes')
    require(b['binary']==('display-probe' if kind=='macos' else 'DisplayProbe.app/DisplayProbe'), 'wrong executable member')
    require(files[b['binary']][:4] in (b'\xcf\xfa\xed\xfe', b'\xce\xfa\xed\xfe', b'\xca\xfe\xba\xbe'), 'not actual Mach-O binary')
    require(files[b['library']].startswith(b'!<arch>\n'), 'not actual installed static archive')
    if kind!='macos':
        info=files['DisplayProbe.app/Info.plist']
        require(sha(info)==b['appInfoSHA256'], 'app Info.plist identity')
        plist=plistlib.loads(info)
        require(plist['CFBundleIdentifier']=='org.exreader.displayprobe' and plist['CFBundleExecutable']=='DisplayProbe', 'actual app bundle identity')
        require(plist['UIApplicationSceneManifest']['UIApplicationSupportsMultipleScenes'] is True, 'app scenes not configured')
    require(files[b['header']]==(ROOT/'extras/apple-reader-display/include/ADRDisplayLease.h').read_bytes(), 'not original public header')
    require(want['source'].encode() in files[b['library']], 'original module source not embedded')
    require(want['source'].encode() in files[b['binary']], 'source not embedded in actual binary')
    require(b'ADRDisplayLease' in files['library-symbols.log'] and b'ADRDisplayLease' in files['consumer-symbols.log'], 'native class not linked')
    require(b'libAppleReaderDisplay.a' in files['consumer.linkmap'], 'installed module missing from actual link map')
    sourcefile='MacProbe.m' if kind=='macos' else 'IOSProbe.m'
    require(files['fresh-consumer/'+sourcefile]==(HERE/sourcefile).read_bytes(), 'not original native probe source')
    require(b['consumerSourceSHA256']==sha((HERE/sourcefile).read_bytes()), 'wrong consumer source hash')
    require(files['fresh-consumer/ProbeSupport.h']==(HERE/'ProbeSupport.h').read_bytes(), 'not original native support')
    require(b['supportSHA256']==sha((HERE/'ProbeSupport.h').read_bytes()), 'wrong support hash')
    rows=[]
    def native(name, group, stage):
        r=load(files[name]); require(r.get('schema')==1 and r.get('stage')==stage, 'wrong native stage')
        i=r['identity']; match_identity(i,want,kind)
        require(i.get('librarySource')==want['source'], 'wrong original module source')
        for key in ('binarySHA256','librarySHA256','headerSHA256','appInfoSHA256'):
            require(i.get(key)==b[key], 'runtime/build binding mismatch '+key)
        require(i.get('executableName')==('display-probe' if kind=='macos' else 'DisplayProbe'), 'runtime executable name')
        if kind!='macos': require(i.get('bundleIdentifier')=='org.exreader.displayprobe','runtime bundle identity')
        require(type(i.get('pid')) is int and i['pid']>0, 'missing actual native PID')
        rows.extend(check_cases(r,contract[group],contract))
        return r
    if kind=='iphoneos':
        r=load(files['unsigned-build.json'])
        require(b['signing']=='unsigned' and r['codesignVerifyExit'] != 0 and r['status']=='PASS', 'distribution signed or build invalid')
        require(r['runtime']=='NOT_RUN_NO_DEVICE' and r['deviceAcceptance']=='PENDING', 'device build overclaim')
        require(r['binarySHA256']==b['binarySHA256'], 'device binary identity')
    else:
        core=native('raw-core.json','macos' if kind=='macos' else 'ios','complete')
        t=load(files['termination.json']); require(t['status']=='PASS', 'termination missing')
        if kind=='macos':
            held=load(files[t['hold']]); before=load(files[t['before']]); after=load(files[t['after']])
            for r in (held,before,after):
                match_identity(r['identity'],want,kind)
                for key in ('binarySHA256','librarySHA256','headerSHA256'):
                    require(r['identity'][key]==b[key], 'process query binary binding')
            require(held['status']==0 and held['queriedProperties'] is True and held['snapshot']['ownsIdle'] is True,'hold assertion absent')
            require(held['identity']['pid']==t['pid'] and t['exitCode']==-9, 'no real SIGKILL')
            require(before['queriedPID']==after['queriedPID']==t['pid'] and
                    before['displayAssertions']>=1 and after['displayAssertions']==0 and
                    before['returnCode']==after['returnCode']==0, 'IOPM process termination query failed')
        else:
            life=native('raw-lifecycle.json','ios_lifecycle','resumed')
            reopen=native('raw-reopen.json','ios_reopen','complete')
            native('raw-multiscene.json','ios_multiscene','complete')
            active=load(files[t['active']]); background=load(files[t['background']])
            for r,stage in ((active,'active'),(background,'background')):
                match_identity(r['identity'],want,kind)
                require(r['stage']==stage and r['identity']==life['identity'], 'lifecycle not same native process')
                original={c['name']:c for c in life['cases']}
                require(all(c==original.get(c['name']) for c in r['cases']), 'lifecycle original observations altered')
            require(len(active['cases'])==1 and len(background['cases'])==2, 'missing lifecycle phase observations')
            witness=load(files[t['oldWitness']])
            require(witness['status']=='PASS' and witness['psExitCode']!=0 and witness['psOutput']=='','process not actually absent')
            require(t['oldPID']==witness['pid']==life['identity']['pid'] and
                    t['newPID']==reopen['identity']['pid'] and t['newPID']!=t['oldPID'], 'no distinct reopened process')
            sim=load(files['simulator.json'])
            require(sim['device']['isAvailable'] is True and sim['device']['name'].startswith('iPhone' if kind=='iphone' else 'iPad'), 'wrong actual simulator class')
    return {'platform':kind,'source':want['source'],'binary':b['binary'],'binarySHA256':b['binarySHA256'],
            'librarySHA256':b['librarySHA256'],'headerSHA256':b['headerSHA256'],'appInfoSHA256':b['appInfoSHA256'],
            'passed':sum(r['status']=='PASS' for r in rows),'pending':[r['name'] for r in rows if r['status']=='PENDING'],
            'namedCases':rows,'acceptance':'PENDING_PHYSICAL_DEVICE_AND_HOST_INTEGRATION',
            'deviceRuntime':'NOT_RUN' if kind=='iphoneos' else 'actual-native-process'}


def collect(kind, directory):
    files={p.relative_to(directory).as_posix():p.read_bytes() for p in directory.rglob('*') if p.is_file()}
    require('manifest.json' not in files,'manifest already exists')
    summary=verify_payload(files,expected(),kind)
    inventory={p:{'sha256':sha(b),'size':len(b)} for p,b in sorted(files.items())}
    result={'schema':1,**expected(),'platform':kind,'files':inventory,'summary':summary}
    (directory/'manifest.json').write_text(json.dumps(result,indent=2)+'\n')
    print('D06_NATIVE_RESULT='+json.dumps(summary,sort_keys=True))


def check_metadata(metadata, want, kind):
    require(type(metadata.get('id')) is int and metadata['id']>0,'artifact ID missing')
    require(metadata.get('name')==f"reader-apple-display-{kind}-{want['run']}-{want['attempt']}",'wrong artifact name')
    require(metadata.get('expired') is False,'expired artifact')
    require(datetime.fromisoformat(metadata['expires_at'].replace('Z','+00:00'))>datetime.now(timezone.utc),'artifact expiry in past')
    require(type(metadata.get('size_in_bytes')) is int and metadata['size_in_bytes']>0,'empty artifact bytes')
    require(isinstance(metadata.get('digest'),str) and metadata['digest'].startswith('sha256:') and len(metadata['digest'])==71,'API SHA256 digest missing')
    require(str(metadata['workflow_run']['id'])==want['run'] and metadata['workflow_run']['head_sha']==want['source'],'artifact workflow source/run mismatch')


def verify_archive(data, metadata, want, kind):
    check_metadata(metadata,want,kind)
    require(len(data)==metadata['size_in_bytes'],'ZIP API size mismatch')
    require('sha256:'+sha(data)==metadata['digest'],'ZIP API digest mismatch')
    files={}
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        infos=z.infolist(); names=[x.filename for x in infos]
        require(len(names)==len(set(names)),'duplicate ZIP member')
        require(sum(x.file_size for x in infos)<250_000_000,'ZIP expansion limit')
        for info in infos:
            path=PurePosixPath(info.filename)
            require(not path.is_absolute() and '..' not in path.parts and '\\' not in info.filename,'unsafe ZIP path')
            require((info.external_attr>>16)&0o170000 != 0o120000,'ZIP symlink')
            if not info.is_dir(): files[info.filename]=z.read(info)
    manifest=load(files.pop('manifest.json')); match_identity(manifest,want,kind)
    require(manifest['schema']==1 and set(files)==set(manifest['files']),'inventory missing/extra member')
    for path,data in files.items():
        require(manifest['files'][path]=={'sha256':sha(data),'size':len(data)},'inventory bytes mismatch '+path)
    summary=verify_payload(files,want,kind)
    require(manifest['summary']==summary,'summary not derivable from original native results')
    return summary,files


def select_artifacts(artifacts,want):
    selected=[]
    for kind in PLATFORMS:
        name=f"reader-apple-display-{kind}-{want['run']}-{want['attempt']}"
        found=[a for a in artifacts if a['name']==name]
        require(len(found)==1,'missing/duplicate artifact name')
        selected.append(found[0]); check_metadata(found[0],want,kind)
    require(len({a['id'] for a in selected})==4,'duplicate artifact ID')
    return selected


def check_jobs(jobs, want):
    required=['guard']+['native ('+p+')' for p in PLATFORMS]
    for name in required:
        found=[j for j in jobs if j['name']==name]
        require(len(found)==1,'missing/duplicate upstream job '+name)
        j=found[0]
        require(j['status']=='completed' and j['conclusion']=='success' and j.get('completed_at'), 'upstream not completed/success '+name)
        require(j['head_sha']==want['source'] and str(j['run_id'])==want['run'],'upstream source/run mismatch')
        # attempt-specific REST endpoint binds the attempt even when older API job schemas omit this field.
        if 'run_attempt' in j: require(str(j['run_attempt'])==want['attempt'],'upstream attempt mismatch')


def request(url):
    return urllib.request.Request(url,headers={'Authorization':'Bearer '+os.environ['GH_TOKEN'],
        'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'})


def api(url):
    with urllib.request.urlopen(request(url),timeout=60) as response: return load(response.read())


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): return None


def download(url):
    try:
        with urllib.request.build_opener(NoRedirect).open(request(url),timeout=60) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        require(error.code==302,'artifact download did not redirect')
        location=error.headers['Location']
        require(location.startswith('https://'),'artifact redirect not HTTPS')
        # Signed storage request deliberately has no GitHub Authorization header.
        with urllib.request.urlopen(location,timeout=120) as response: return response.read()


def paged(url,key):
    result=[]; page=1
    while True:
        data=api(url+('?' if '?' not in url else '&')+f'per_page=100&page={page}')
        result.extend(data[key])
        if len(data[key])<100: return result
        page+=1


def aggregate():
    want=expected(); base='https://api.github.com/repos/'+os.environ['GITHUB_REPOSITORY']
    run=api(base+'/actions/runs/'+want['run']+'/attempts/'+want['attempt'])
    require(run['head_sha']==want['source'] and str(run['run_attempt'])==want['attempt'],'authenticated run mismatch')
    require(run['path']=='.github/workflows/reader-apple-display.yml','wrong workflow path')
    jobs=paged(base+'/actions/runs/'+want['run']+'/attempts/'+want['attempt']+'/jobs','jobs')
    check_jobs(jobs,want)
    artifacts=select_artifacts(paged(base+'/actions/runs/'+want['run']+'/artifacts','artifacts'),want)
    originals=[]; summaries=[]
    for kind,metadata in zip(PLATFORMS,artifacts):
        data=download(base+'/actions/artifacts/'+str(metadata['id'])+'/zip')
        summary,files=verify_archive(data,metadata,want,kind)
        originals.append((kind,data,metadata,files)); summaries.append(summary)
    from verifier_negative import reject_mutations
    negatives=reject_mutations(originals,jobs,want)
    proof={'schema':1,**want,'runURL':run['html_url'],'attempt':want['attempt'],
        'authenticatedJobs':[{'id':j['id'],'name':j['name'],'status':j['status'],'conclusion':j['conclusion']} for j in jobs if j['name']!='authenticate'],
        'artifacts':[{'id':a['id'],'name':a['name'],'size':a['size_in_bytes'],'sha256':a['digest'][7:],'expires_at':a['expires_at']} for a in artifacts],
        'results':summaries,'verifierRejections':negatives,'fullProductAcceptance':'PENDING'}
    print('D06_AUTHENTICATED_EVIDENCE='+json.dumps(proof,sort_keys=True),flush=True)
    with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as f:
        f.write('## D06 actual native capability evidence\n\n')
        for s in summaries: f.write(f"- {s['platform']}: {s['passed']} named PASS, {len(s['pending'])} PENDING; binary `{s['binarySHA256']}`\n")
        f.write(f'\n{len(negatives)} verifier rejection cases passed. Physical device/sleep/backlight and host integration remain pending.\n')


def main():
    require(os.environ.get('GITHUB_ACTIONS')=='true','Actions only')
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest='mode',required=True)
    c=sub.add_parser('collect'); c.add_argument('platform',choices=PLATFORMS); c.add_argument('directory',type=Path)
    sub.add_parser('aggregate'); args=p.parse_args()
    if args.mode=='collect': collect(args.platform,args.directory)
    else: aggregate()


if __name__=='__main__': main()
