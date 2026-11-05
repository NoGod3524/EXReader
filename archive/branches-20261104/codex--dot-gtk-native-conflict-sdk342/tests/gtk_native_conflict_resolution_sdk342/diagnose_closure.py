"""Actions-only inspection of the original retained failure; no app/test rerun."""
import configparser,hashlib,json,os,subprocess
from pathlib import Path
assert os.environ.get('GITHUB_ACTIONS')=='true'
ROOT=Path(__file__).resolve().parents[2]
RUN='40730797378';SOURCE='a121564303cb2844b60487b719e34742645f5cd4'
EXPECTED={'windows-gtk-gtk-first-'+RUN+'-1':(12835947301,'sha256:e38d5c8fe133075a3c49f6165564a846c071ecb5203de3f3def400458fa44050'),
          'sdk342-gtk-identity-'+RUN+'-1':(12836510081,'sha256:4bb5ff311674bddf7181fc998328dee9fce3e13e28cf0562814c56375008f305')}
api=json.loads(subprocess.check_output(['gh','api','repos/'+os.environ['GITHUB_REPOSITORY']+'/actions/runs/'+RUN+'/artifacts?per_page=100'],text=True))
for name,(expected_id,expected_digest) in EXPECTED.items():
    a=[v for v in api['artifacts'] if v['name']==name];assert len(a)==1
    a=a[0];assert a['id']==expected_id and a['digest']==expected_digest and a['workflow_run']['head_sha']==SOURCE and not a['expired']
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
root=ROOT/'build/closure-diagnostic';report=json.loads((root/'identity/report.json').read_text())
assert report['source_sha']==SOURCE and report['run_id']==RUN and report['attempt']=='1' and report['accepted']
results={}
for case in ('current-account','original-account'):
    folder=root/'evidence'/case;value=json.loads((folder/'result.json').read_text())
    assert value['source_sha']==SOURCE and value['run_id']==RUN and value['attempt']=='1'
    assert value['program_sha256']==report['program_sha256']
    state_path=folder/'unavailable/state.ini';parser=configparser.ConfigParser(interpolation=None);parser.read(state_path)
    log=folder/'unavailable/application.log';lines=log.read_text(errors='replace').splitlines()
    statuses=[line for line in lines if line.startswith('STATUS ')][-35:]
    results[case]={'result':value,'last_state':{k:dict(parser[k]) for k in parser.sections()},'last_status_lines':statuses,'state_sha256':sha(state_path),'log_sha256':sha(log)}
    print('GTK_CLOSURE_ARCHIVED_EVIDENCE '+json.dumps({'case':case,**results[case]}),flush=True)
output={'diagnostic_only':True,'source_sha':os.environ['GITHUB_SHA'],'run_id':os.environ['GITHUB_RUN_ID'],'attempt':os.environ['GITHUB_RUN_ATTEMPT'],'failed_source_sha':SOURCE,'failed_run':RUN,'actual_gtk_program_sha256':report['program_sha256'],'artifact_identities':EXPECTED,'cases':results}
(root/'summary.json').write_text(json.dumps(output,indent=2))
