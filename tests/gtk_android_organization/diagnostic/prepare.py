"""Actions-only authenticated producer reuse. This is NOT final acceptance."""
import base64,hashlib,json,os,subprocess,urllib.request,zipfile
from pathlib import Path
from urllib.parse import urlparse
class SafeRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,req,fp,code,msg,headers,newurl):
  redirected=super().redirect_request(req,fp,code,msg,headers,newurl)
  if redirected is not None and urlparse(req.full_url).netloc!=urlparse(newurl).netloc:
   redirected.remove_header("Authorization")
  return redirected
opener=urllib.request.build_opener(SafeRedirect())
assert os.environ.get('GITHUB_ACTIONS')=='true'
PRODUCER='7408da16333cd64a4e604275565fee4f3459a179'
RUN='40657839896'
repo='NoGod3524/EXReader';out=Path('build/diagnostic');out.mkdir(parents=True,exist_ok=True)
def gh(path):
 req=urllib.request.Request('https://api.github.com/'+path,headers={'Authorization':'Bearer '+os.environ['GH_TOKEN'],'Accept':'application/vnd.github+json'})
 return opener.open(req).read()
run=json.loads(gh(f'repos/{repo}/actions/runs/{RUN}'));assert run['head_sha']==PRODUCER and run['run_attempt']==1
paths=['src','include','apps','examples','extras','tools','CMakeLists.txt','CMakePresets.json','cmake']
subprocess.run(['git','diff','--exit-code',PRODUCER,'HEAD','--',*paths],check=True)
artifacts=json.loads(gh(f'repos/{repo}/actions/runs/{RUN}/artifacts'))['artifacts']
proof={'diagnostic_only':True,'producer_source_sha':PRODUCER,'producer_run':RUN,'diagnostic_test_sha':os.environ['GITHUB_SHA'],'diagnostic_run':os.environ['GITHUB_RUN_ID'],'product_paths_equal':paths,'artifacts':[]}
for prefix,target in [('org-android-runtime','build/wave3'),('org-gtk-first','build/producer-gtk-first'),('org-gtk-package','build/package')]:
 matches=[x for x in artifacts if x['name']==f'{prefix}-{RUN}-1'];assert len(matches)==1
 a=matches[0];assert not a['expired']
 raw=gh(f'repos/{repo}/actions/artifacts/{a["id"]}/zip');digest=hashlib.sha256(raw).hexdigest();assert a['digest']=='sha256:'+digest
 archive=out/(prefix+'.zip');archive.write_bytes(raw)
 with zipfile.ZipFile(archive) as z:
  for n in z.namelist():assert not Path(n).is_absolute() and '..' not in Path(n).parts
  z.extractall(target)
 proof['artifacts'].append({'id':a['id'],'name':a['name'],'zip_sha256':digest,'api_digest':a['digest']})
identity=PRODUCER+'\n'+RUN+'\n1\n'
assert Path('build/wave3/artifacts/runtime-identity.txt').read_text()==identity
assert Path('build/package/relay-identity.txt').read_text()==identity
subprocess.run(['sha256sum','-c','runtime-apks.sha256'],cwd='build/wave3/artifacts',check=True)
subprocess.run(['sha256sum','-c','relay-sha256.txt'],cwd='build/package',check=True)
raw=Path('build/producer-gtk-first/state.json').read_bytes();state=json.loads(raw)
assert state['source_sha']==PRODUCER and state['run_id']==RUN and state['attempt']=='1' and state['phase']=='gtk-first' and state['data']['passed'] is True
for e in state['entries'].values():assert hashlib.sha256(base64.b64decode(e['body'],validate=True)).hexdigest()==e['sha256']
# Adapt ONLY artifact envelope, never any original or application revision bytes.
prior_entries=state['entries'].copy();proof['producer_state_sha256']=hashlib.sha256(raw).hexdigest()
for k,v in [('source_sha','GITHUB_SHA'),('run_id','GITHUB_RUN_ID'),('attempt','GITHUB_RUN_ATTEMPT')]:state[k]=os.environ[v];state['data'][k]=os.environ[v]
state['diagnostic_origin']={'source_sha':PRODUCER,'run_id':RUN,'state_sha256':proof['producer_state_sha256']}
assert state['entries']==prior_entries
Path('build/diagnostic-input').mkdir();Path('build/diagnostic-input/state.json').write_text(json.dumps(state,indent=2))
(out/'producer-proof.json').write_text(json.dumps(proof,indent=2));print(json.dumps(proof,indent=2))
