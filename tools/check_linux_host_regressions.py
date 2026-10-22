#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Cloud-only negative checks; actual UI acceptance remains a separate 20-case run."""
import argparse,configparser,hashlib,json,os,pathlib,shutil,subprocess,sys
from check_linux_host import Session
def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--payload',type=pathlib.Path,required=True);p.add_argument('--consumer',type=pathlib.Path,required=True)
 p.add_argument('--output',type=pathlib.Path,required=True);args=p.parse_args();root=args.output.resolve()
 if root.exists():p.error('Choose a new evidence directory')
 root.mkdir(parents=True);checks=[]
 # Real already-exited child processes expose the old close() false-pass path.
 for code in (23,0):
  session=Session(None,None,root);session.process=subprocess.Popen([sys.executable,'-c',f'import sys;sys.exit({code})'])
  session.process.wait(timeout=10);rejected=False
  try:session.close()
  except RuntimeError:rejected=True
  assert rejected==(code!=0)
  checks.append({'name':f'already-exited child {code}', 'pass':True})
 font=(args.payload/'Reader.otf').resolve()
 run=subprocess.run([str((args.consumer/'exreader-linux-notes_failure').resolve()),str(font),str(root/'notes-profile')],
                    stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=60)
 (root/'notes-fault.log').write_text(run.stdout+run.stderr)
 assert run.returncode==0
 note_report=json.loads(run.stdout.strip().splitlines()[-1]);assert note_report['passed'] and note_report['checks']>=10
 checks.append({'name':'real GTK/public SDK notes failure recovery','pass':True,'checks':note_report['checks']})
 # Run the real UI verifier against a deliberately broken restore implementation.
 payload=root/'font-mutant-payload';shutil.copytree(args.payload,payload)
 shutil.copyfile(args.consumer/'exreader-linux-font_restore_mutant',payload/'bin/exreader-linux')
 run=subprocess.run([sys.executable,str(pathlib.Path(__file__).with_name('check_linux_host.py')),
                     '--payload',str(payload),'--output',str(root/'font-mutant-evidence')],
                    stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=180)
 (root/'font-mutant-verifier.log').write_text(run.stdout+run.stderr)
 report=json.loads((root/'font-mutant-evidence/report.json').read_text())
 settings=configparser.ConfigParser();settings.read(root/'font-mutant-evidence/profile/reader.ini')
 state=configparser.ConfigParser();state.read(root/'font-mutant-evidence/state.ini')
 assert run.returncode!=0 and report['passed'] is False and len(report['checks'])==12
 assert report['restart_expected']['font']==26 and state.getint('host','font')==24
 checks.append({'name':'nondefault font restore mutant rejected by real UI check 13','pass':True,
                'prior_checks_passed':len(report['checks']),'expected_font_before_restart':26,'incorrect_restored_font':24,
                'persisted_font_after_mutant_restart':settings.getint('reader','font')})
 result={'schema':1,'passed':True,'source_sha':os.environ.get('GITHUB_SHA'),'checks':checks,'real_ui_cases_expected':20,
         'files':{str(f.relative_to(root)):hashlib.sha256(f.read_bytes()).hexdigest() for f in root.rglob('*') if f.is_file()}}
 (root/'regressions.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:result[k] for k in ('passed','source_sha','checks')}))
if __name__=='__main__':main()
