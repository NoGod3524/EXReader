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
  config_dir=OUT/'configs';config_dir.mkdir(exist_ok=True)
  configurations={}
  for name in ('raw-host/CMakeCache.txt','raw-host/build.ninja','raw-host/windows-host.map'):
   raw=b.bytes('windows-raw3-host/'+name,64*1024**2)
   (config_dir/name.replace('/','-')).write_bytes(raw)
   configurations[name]={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
  cache=(config_dir/'raw-host-CMakeCache.txt').read_text(encoding='utf-8')
  require('EXR_SDK_VERSION:STRING=3.41.0' in cache and all(k+':BOOL=ON' in cache for k in ('EXR_READER_WINDOWS_RAW3','EXR_READER_WINDOWS_RECORDS','EXR_READER_WINDOWS_COMPACT')),'actual original program configuration')
  lines=(config_dir/'raw-host-build.ninja').read_text(encoding='utf-8').splitlines();definitions={}
  for program in ('EXReaderProduct','EXReaderShelfReview'):
   blocks=[lines[i+1:i+9] for i,line in enumerate(lines) if line.startswith('build CMakeFiles/'+program+'.dir/') and '/reader.c.obj:' in line]
   require(len(blocks)==1,'unique actual program compile edge')
   defs=[line.strip() for line in blocks[0] if line.strip().startswith('DEFINES =')];require(len(defs)==1,'actual compile definitions')
   definitions[program]=defs[0]
   require('-DEXR_READER_WINDOWS_RAW3=1' in defs[0] and '-DEXR_READER_WINDOWS_RECORDS=1' in defs[0],'actual raw records compilation')
   require(('EXR_HOST_WORKER_REVIEW=1' in defs[0])==(program=='EXReaderShelfReview'),'default and review separation')
  installed={}
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
    dest=OUT/'installed'/tail;dest.parent.mkdir(parents=True,exist_ok=True);data=b.zip.read(info);dest.write_bytes(data)
    installed[tail.as_posix()]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
  # Original owner proofs remain historical, not this run's GUI outcome.
  for label in ('first','reopen'):
   original=b.report('windows-raw3-host/mac-network-receive/peer-owner/'+label+'.json')
   (OUT/('original-peer-'+label+'.json')).write_text(json.dumps(original,indent=2),encoding='utf-8')
 finally:b.close()
 proof=dict(harness_source=os.environ['GITHUB_SHA'],target_source=SOURCE,target_run=RUN,target_attempt=1,target_jobs=[j['id'] for j in jobs],artifact=meta,programs=programs,configurations=configurations,compiler_definitions=definitions,installed=installed,sdk_source='edddc463c06ed5731195cdb8f06b2df6dff7699e',accepted=True)
 (OUT/'target-auth.json').write_text(json.dumps(proof,indent=2),encoding='utf-8');print(json.dumps(proof),flush=True)
 subprocess.run([sys.executable,'-c',"from tools.host_font import fetch; fetch('build/host-font-cache')"],cwd=TARGET,check=True)
if __name__=='__main__':main()
