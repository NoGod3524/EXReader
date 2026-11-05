"""Download/authenticate original producer ZIPs only inside Actions."""
import datetime, hashlib, json, os, pathlib, sys, urllib.request, urllib.parse, zipfile
assert os.environ.get('GITHUB_ACTIONS') == 'true'
CONFIG = {
 'android': (40207467982,12604537792,'4a04a9cc74dde67f755c87e87b278d63a254a3ac',133598571,'9ea2858145313296d39792d867794db1be687eb70dec38f155dcd1dfe156bf06'),
 'macos': (40203714083,12603310238,'72c6bbdd14ebf3be453fa7f0da81119d52675eb5',21887403,'9d454bb6a9ba9d354562dc5316059b1857277b45ffbf69b74a576fe040dc2150'),
 'iphone': (40203714083,12603156296,'72c6bbdd14ebf3be453fa7f0da81119d52675eb5',21891156,'538d6c2888505d6398e1ce7294f8178de0008d0ddee119d969025cb278845cc1'),
 'ipad': (40203714083,12603156296,'72c6bbdd14ebf3be453fa7f0da81119d52675eb5',21891156,'538d6c2888505d6398e1ce7294f8178de0008d0ddee119d969025cb278845cc1')}
class SafeRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self, req, fp, code, msg, headers, newurl):
  new=super().redirect_request(req,fp,code,msg,headers,newurl)
  if urllib.parse.urlparse(req.full_url).netloc != urllib.parse.urlparse(newurl).netloc:
   new.remove_header('Authorization')
  return new
def request(path):
 req=urllib.request.Request('https://api.github.com/repos/'+os.environ['GITHUB_REPOSITORY']+path,headers={'Authorization':'Bearer '+os.environ['GH_TOKEN'],'Accept':'application/vnd.github+json'})
 return urllib.request.build_opener(SafeRedirect()).open(req).read()
def main():
 host=sys.argv[1]; run,aid,sha,size,digest=CONFIG[host]
 out=pathlib.Path('build/d18');out.mkdir(parents=True,exist_ok=True)
 state=json.loads(request('/actions/runs/'+str(run)));assert state['head_sha']==sha and state['status']=='completed' and state['run_attempt']==1
 jobs=json.loads(request('/actions/runs/'+str(run)+'/attempts/1/jobs?per_page=100'))['jobs'];assert jobs and all(j['status']=='completed' for j in jobs)
 meta=json.loads(request('/actions/artifacts/'+str(aid)))
 meta['producer_attempt']=1;meta['producer_jobs']=[{k:j[k] for k in ('id','name','status','conclusion')} for j in jobs]
 (out/(host+'-producer-metadata.json')).write_text(json.dumps(meta,indent=2))
 assert not meta['expired'] and meta['workflow_run']['id']==run and meta['workflow_run']['head_sha']==sha
 assert meta['size_in_bytes']==size and meta['digest']=='sha256:'+digest
 assert datetime.datetime.fromisoformat(meta['expires_at'].replace('Z','+00:00'))>datetime.datetime.now(datetime.timezone.utc)
 raw=request('/actions/artifacts/'+str(aid)+'/zip');assert len(raw)==size and hashlib.sha256(raw).hexdigest()==digest
 archive=out/(host+'-producer.zip');archive.write_bytes(raw)
 dest=out/(host+'-producer');dest.mkdir()
 with zipfile.ZipFile(archive) as z:
  names=z.namelist();assert len(names)==len(set(names))
  assert all(not pathlib.PurePosixPath(n).is_absolute() and '..' not in pathlib.PurePosixPath(n).parts for n in names)
  z.extractall(dest)
 meta.update(zip_sha256=digest,authenticated_in_run=os.environ['GITHUB_RUN_ID'],harness_sha=os.environ['GITHUB_SHA'],scope='old producer bytes, not new execution')
 (out/(host+'-producer-identity.json')).write_text(json.dumps(meta,indent=2))
 print(json.dumps(meta),flush=True)
if __name__=='__main__':main()
