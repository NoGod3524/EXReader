"""Actions-only real Activity organization relay, never prefilled application DB."""
import argparse,hashlib,json,os,subprocess,sys
from pathlib import Path
from urllib.parse import urlparse
sys.path.insert(0,str(Path(__file__).resolve().parents[1]));import relay
p=argparse.ArgumentParser();p.add_argument('--phase',choices=['android','android-final'],required=True);p.add_argument('--previous',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--fixture',type=Path,required=True);a=p.parse_args()
identity=relay.identity();previous,prior_hash=relay.load(a.previous,'gtk-first' if a.phase=='android' else 'gtk-return')
a.output.mkdir(parents=True,exist_ok=True)
dav,user,password=relay.start(a.output,a.previous,a.fixture/'public/server.crt',a.fixture/'private/server.key')
package='org.exreader.host'
def adb(*parts,data=None,timeout=90):return subprocess.check_output(['adb',*map(str,parts)],input=data,stderr=subprocess.STDOUT,timeout=timeout)
def save(name,body):
    assert password.encode() not in body,'secret leaked';(a.output/name).write_bytes(body)
payload={'root':dav.base+'/dav/','user':user,'password':password,'relay_data':previous['data']['relay_data'],'phase':a.phase}
accepted=False
try:
    assert adb('shell','pm','clear',package).strip()==b'Success'
    adb('shell','am','start','-W','-n',package+'/.MainActivity');port=urlparse(dav.base).port;adb('reverse',f'tcp:{port}',f'tcp:{port}')
    reports=[]
    for restart in ([False,True] if a.phase=='android-final' else [False]):
        if restart:adb('shell','am','force-stop',package);adb('shell','am','start','-W','-n',package+'/.MainActivity')
        adb('shell',f"run-as {package} sh -c 'cat > files/organization-relay-input.json'",data=json.dumps(payload).encode())
        cmd=['shell','am','instrument','-w','-r']
        for k,v in {**identity,'restart':str(restart).lower()}.items():cmd+=['-e',k,v]
        raw=adb(*cmd,package+'.test/'+package+'.OrganizationRelayTest',timeout=900);save('instrumentation-'+str(restart)+'.txt',raw)
        report_raw=adb('exec-out','run-as',package,'cat','files/organization-relay-report.json');save('report-'+str(restart)+'.json',report_raw);report=json.loads(report_raw)
        print(json.dumps(report,indent=2),flush=True)
        for screen in report.get('screens',[]):
            for extension in ['png','txt']:save(str(restart)+'-'+screen+'.'+extension,adb('exec-out','run-as',package,'cat','files/org-'+screen+'.'+extension))
        assert all(report.get(k)==v for k,v in identity.items());assert report['api']==34 and report['passed'] is True,report
        assert b'ORG_RELAY_PASS' in raw and b'INSTRUMENTATION_CODE: -1' in raw
        reports.append(report);payload['relay_data']=report['relay_data']
    if len(reports)==2:assert reports[0]['rows']==reports[1]['rows'],'process restart changed organization'
    apk=adb('shell','pm','path',package).decode().strip();assert apk.startswith('package:/data/app/') and '\n' not in apk
    actual=adb('exec-out','cat',apk[len('package:'):]);expected=Path('build/wave3/artifacts/app-debug.apk').read_bytes();assert actual==expected
    summary={**identity,'passed':True,'checks':[r for report in reports for r in report['checks']],'relay_data':payload['relay_data'],'program_sha256':hashlib.sha256(actual).hexdigest(),'rows':reports[-1]['rows'],'transport':'authenticated staged HTTPS, not simultaneous live hosts'}
    (a.output/'report.json').write_text(json.dumps(summary,indent=2));relay.save(dav,a.output,a.phase,summary);accepted=True
finally:
    for name,cmd in [('logcat.txt',('logcat','-d','-v','threadtime','-t','3000')),('screen.png',('exec-out','screencap','-p'))]:
        try:save(name,adb(*cmd))
        except Exception as e:print('capture',name,type(e).__name__)
    if not accepted:
        (a.output/'failed-requests.json').write_text(json.dumps(dav.requests));dav.server.shutdown();dav.server.server_close();(a.output/'key.pem').unlink(missing_ok=True)
