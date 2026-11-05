"""Actions-only exact original failed ZIP readback; never changes past conclusions."""
import hashlib,io,json,os,sys,zipfile
from pathlib import Path
sys.path.insert(0,str(Path('tools').resolve()))
from check_parallel_integration import fetch,download_artifact_zip
assert os.environ.get('GITHUB_ACTIONS')=='true'
SOURCE='5f76251e6ab906740151ed60ca5fc034ce050bbf';RUN=40225172916
run=fetch(f'actions/runs/{RUN}');assert run['head_sha']==SOURCE and run['status']=='completed' and run['run_attempt']==1
for platform,id,sha in [('windows',12610907470,'e78d4ad9a9d36a8472ed722346a466019dc23b1483917f770eae7daa262914ca'),('gtk',12611221601,'2b08cbeadce70e2868c13ff375d6ea7ec05322b2dfb7079670d4d8c2b2600673')]:
    meta=fetch(f'actions/artifacts/{id}');assert not meta['expired'] and meta['workflow_run']['head_sha']==SOURCE and meta['workflow_run']['id']==RUN
    raw=download_artifact_zip(id);assert len(raw)==meta['size_in_bytes'] and hashlib.sha256(raw).hexdigest()==sha
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        report=json.loads(z.read('report.json'));assert report['harness']==SOURCE and report['run']==str(RUN) and report['attempt']=='1'
        print('D14_PREVIOUS '+json.dumps(dict(platform=platform,artifact=id,completed_cycles=report['completed_cycles'],failures=report['failures'],failure_snapshot=json.loads(z.read('failure-snapshot.json')) if 'failure-snapshot.json' in z.namelist() else None)),flush=True)

# CI2 GTK failed at a repeated-book selector; preserve its original tree facts.
meta=fetch('actions/artifacts/12610978837')
assert not meta['expired'] and meta['workflow_run']['head_sha']=='c466aa835b412555cadd5a3734ea766f366b925a' and meta['workflow_run']['id']==40226184382
raw=download_artifact_zip(12610978837)
assert len(raw)==18690847 and hashlib.sha256(raw).hexdigest()=='cf7ef529ac99d7c04b844e46a70a963ebef88c4edf6c9d79e602bdee1c87dae1'
with zipfile.ZipFile(io.BytesIO(raw)) as z:
    value=json.loads(z.read('failure-snapshot.json'))
    print('D14_CI2_NATIVE_TREE '+json.dumps(value),flush=True)
