"""Bounded native API smoke on authentic accepted archived host profiles.
This is not full acceptance; the full job chain rebuilds and reauthors same-SHA
profiles and exercises the actual GTK/Windows UI, rather than reusing this seed.
"""
import hashlib,json,os,shutil,sqlite3,subprocess
from pathlib import Path
import identity
identity.guard();root=Path('build/smoke');out=root/'evidence';out.mkdir(parents=True,exist_ok=True)
accepted='40719488176'
run=json.loads(subprocess.check_output(['gh','api','repos/'+os.environ['GITHUB_REPOSITORY']+'/actions/runs/'+accepted],text=True))
assert run['head_sha']==identity.BASE and run['conclusion']=='success'
state=json.loads((root/'conflict/state.json').read_text());assert state['source_sha']==identity.BASE and state['run_id']==accepted and state['attempt']=='1'
seed=json.loads((root/'seed/gtk-first/state.json').read_text());assert seed['source_sha']==identity.BASE and seed['run_id']==accepted
key=state['data']['windows_book'];catalog=root/'conflict/profile/library.sqlite.product.sqlite'
def wires():
    with sqlite3.connect('file:'+str(catalog.resolve())+'?mode=ro',uri=True) as db:return dict(db.execute('SELECT revision_id,body_json FROM reader_revisions'))
before=wires();writer=root/'writer/gtk-preview-writer'
result=subprocess.run([str(writer.resolve()),str((root/'seed/gtk-first/profile/library.sqlite.product.sqlite').resolve()),str(catalog.resolve()),key,str((out/'writer').resolve())],capture_output=True,text=True,timeout=120)
(out/'writer-runtime.log').write_text(result.stdout+'\n'+result.stderr);assert result.returncode==0,result.stderr
actual=json.loads(result.stdout);after=wires();assert all(after.get(k)==v for k,v in before.items()) and len(after)==len(before)+1
assert actual['heads']==3 and actual['metadata_version']=='0.1.0' and actual['commands_version']=='0.1.0' and actual['revisions_version']=='0.3.0'
report=dict(identity.retained.identity(),accepted=True,smoke_only=True,accepted_seed_sha=identity.BASE,accepted_seed_run=accepted,writer_sha256=hashlib.sha256(writer.read_bytes()).hexdigest(),runtime=actual,retained_revisions=len(before),result_revisions=len(after))
(out/'result.json').write_text(json.dumps(report,indent=2));print('GTK_NATIVE_BOUNDED_SMOKE '+json.dumps(report),flush=True)
