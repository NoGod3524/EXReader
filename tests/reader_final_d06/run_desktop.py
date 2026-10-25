"""Re-execute unchanged real native drivers, never count old reports as new actions."""
import hashlib,json,os,pathlib,subprocess,sys
assert os.environ.get('GITHUB_ACTIONS')=='true'
host=sys.argv[1];root=pathlib.Path.cwd();out=root/'build/d06';producer=out/(host+'-producer')
target=root/'target'; results=[]
def find(suffix):
 matches=[p for p in producer.rglob(pathlib.Path(suffix).name) if p.as_posix().endswith(suffix)]
 assert len(matches)==1,(suffix,matches)
 return matches[0].resolve()
def run(name,script,args):
 command=[sys.executable,str(script),*map(str,args)]
 with (out/(name+'.log')).open('w') as log:
  result=subprocess.run(command,cwd=target,stdout=log,stderr=subprocess.STDOUT)
 results.append(dict(name=name,returncode=result.returncode,command=command))
 print(json.dumps(results[-1]),flush=True)
programs={}
try:
 if host=='windows':
  binary=find('ws-package/EXReader/EXReader.exe');review=find('ws-host/EXReaderShelfReview.exe');font=find('ws-package/EXReader/Reader.otf');compact=find('compact-host/EXReaderProduct.exe')
  programs={name:{'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for name,p in [('default',binary),('compact',compact),('review',review)]}
  run('windows-default-keyboard',target/'tests/reader_windows_search/check_keyboard.py',['--candidate',binary,'--review',review,'--font',font,'--output',out/'windows-default-keyboard'])
  run('windows-text-repeat',root/'tests/reader_final_d06/windows_focus.py',['--target',target,'--candidate',binary,'--font',font,'--output',out/'windows-text-repeat'])
  fixtures=out/'windows-fixtures'
  run('windows-fixtures',target/'tests/reader_windows_preferences/make_fixtures.py',['--output',fixtures])
  run('windows-compact',target/'tests/reader_windows_compact/check_ui.py',['--candidate',compact,'--font',font,'--fixtures',fixtures,'--output',out/'windows-compact'])
 else:
  binary=find('compact-package/EXReader-Linux/bin/exreader-linux');payload=binary.parent.parent
  for p in payload.rglob('*'):
   if p.is_file() and (p.parent.name=='bin' or '.so' in p.name):p.chmod(p.stat().st_mode|0o111)
  programs={'compact':{'path':str(binary),'sha256':hashlib.sha256(binary.read_bytes()).hexdigest()}}
  fixture=find('compact-fixtures/manifest.json').parent
  run('gtk-compact',target/'tests/reader_gtk_compact/check_ui.py',['--payload',payload,'--fixtures',fixture,'--output',out/'gtk-compact'])
finally:
 report=dict(harness_sha=os.environ['GITHUB_SHA'],target_sha=subprocess.check_output(['git','-C',str(target),'rev-parse','HEAD'],text=True).strip(),producer=json.loads((out/(host+'-producer-identity.json')).read_text()),run_id=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'],host=host,programs=programs,executions=results,accepted=bool(results) and all(r['returncode']==0 for r in results),keyboard_accepted=False,complete_product=False,screen_reader_accepted=False)
 report['files']={str(p.relative_to(out)):{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in out.rglob('*') if p.is_file() and '-producer' not in str(p.relative_to(out)) and p.suffix in ('.json','.bmp','.png','.log','.txt')}
 (out/(host+'-execution.json')).write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
assert report['accepted'], 'Real native driver failure retained; product not accepted'
