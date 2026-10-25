"""Download/authenticate original producer ZIPs only inside Actions."""
import datetime, hashlib, json, os, pathlib, sys, urllib.request, zipfile
assert os.environ.get('GITHUB_ACTIONS') == 'true'
CONFIG = {
 'windows': (40201283788,12601764928,'eab342ef456be4a8a1811e5249e3c217d906ce8a',169964880,'4e158bdda8c18561b972b85d22ea8e71c6c6dcdc997b3f23a55747fc195954d3'),
 'gtk': (40206458217,12604604561,'57203a52aee439be5194ee0a4b13563a975e8daf',112659381,'8d6c52593dd2017a6e13ffc2cf75fd3fd4546cdf3a5179b0da5afd55ac1fb685')}
def request(path):
 req=urllib.request.Request('https://api.github.com/repos/'+os.environ['GITHUB_REPOSITORY']+path,headers={'Authorization':'Bearer '+os.environ['GH_TOKEN'],'Accept':'application/vnd.github+json'})
 return urllib.request.urlopen(req).read()
def main():
 host=sys.argv[1]; run,aid,sha,size,digest=CONFIG[host]
 out=pathlib.Path('build/d06');out.mkdir(parents=True,exist_ok=True)
 meta=json.loads(request('/actions/artifacts/'+str(aid)))
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
