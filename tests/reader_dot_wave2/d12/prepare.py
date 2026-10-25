"""Authenticate original programs, source and wire evidence; Actions only."""
import hashlib,json,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
TARGET=ROOT/'target'
OUT=ROOT/'build/d12'
SOURCE='9321de84eb9c8d3d57cafbeaa8b0a28fe2a26a08'
RUN=40221234665
sys.path.insert(0,str(TARGET/'tests/reader_hosts_integration'))
from final import Bundle,fetch,require

def main():
 require(os.environ.get('GITHUB_ACTIONS')=='true','Actions only')
 require(subprocess.check_output(['git','rev-parse','HEAD'],cwd=TARGET,text=True).strip()==SOURCE,'target checkout')
 OUT.mkdir(parents=True,exist_ok=True)
 run=fetch('actions/runs/'+str(RUN));require(run['head_sha']==SOURCE and run['run_attempt']==1 and run['conclusion']=='success','target run')
 jobs=fetch(f'actions/runs/{RUN}/attempts/1/jobs?per_page=100')['jobs'];require(len(jobs)==1 and jobs[0]['id']==121253049387 and jobs[0]['conclusion']=='success','target jobs')
 listing=fetch(f'actions/runs/{RUN}/artifacts?per_page=100');require(listing['total_count']==1,'unique target ZIP')
 meta=listing['artifacts'][0];require(meta['id']==12610050539 and meta['size_in_bytes']==234847679 and meta['digest']=='sha256:1271a76418ead98675e24f3406f3240614003c10c15385a3c74867c05e0401a1' and meta['workflow_run']['head_sha']==SOURCE,'target ZIP identity')
 b=Bundle(meta)
 try:
  root=b.report('windows-raw3-host/report.json');require(root['source_sha']==SOURCE and str(root['run_id'])==str(RUN) and str(root['attempt'])=='1','root identity')
  profiles=root['profiles'];require([p['profile'] for p in profiles]==['legacy','raw'],'profiles')
  programs={}
  for name,expected in profiles[1]['programs'].items():
   raw=b.bytes('windows-raw3-host/raw-host/'+name+'.exe',128*1024**2)
   require(hashlib.sha256(raw).hexdigest()==expected,'program hash')
   path=OUT/'programs'/ (name+'.exe');path.parent.mkdir(exist_ok=True);path.write_bytes(raw);programs[name]=expected
  # Retain the actual SDK and module installs without rebuilding target code.
  for info in b.zip.infolist():
   if info.is_dir():continue
   parts=Path(info.filename).parts
   if 'windows-raw3-host' not in parts:continue
   i=parts.index('windows-raw3-host');tail=Path(*parts[i+1:])
   if tail.parts[0] in ('sdk-stage','product-stage','raw-stage'):
    dest=OUT/'installed'/tail;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(b.zip.read(info))
  # Original owner proofs remain historical, not this run's GUI outcome.
  for label in ('first','reopen'):
   original=b.report('windows-raw3-host/mac-network-receive/peer-owner/'+label+'.json')
   (OUT/('original-peer-'+label+'.json')).write_text(json.dumps(original,indent=2),encoding='utf-8')
 finally:b.close()
 proof=dict(harness_source=os.environ['GITHUB_SHA'],target_source=SOURCE,target_run=RUN,target_attempt=1,target_jobs=[j['id'] for j in jobs],artifact=meta,programs=programs,accepted=True)
 (OUT/'target-auth.json').write_text(json.dumps(proof,indent=2),encoding='utf-8');print(json.dumps(proof),flush=True)
 subprocess.run([sys.executable,'-c',"from tools.host_font import fetch; fetch('build/host-font-cache')"],cwd=TARGET,check=True)
if __name__=='__main__':main()
