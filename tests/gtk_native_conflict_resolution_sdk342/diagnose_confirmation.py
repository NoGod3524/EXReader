"""Actions-only native confirmation selector probe on exact failed-run inputs."""
import hashlib,json,os,re,shutil,sqlite3,subprocess,sys,time,traceback
from pathlib import Path
import pyatspi
assert os.environ.get('GITHUB_ACTIONS')=='true'
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools'))
from check_linux_host import Session,command
RUN='40802418300';SOURCE='60b515ee33125965867ed2f3d6b7496bf8df66a3'
EXPECTED={
 'gtk-native-gtk-'+RUN+'-1':(12868085584,'sha256:31e0b26f5676cd44604ea800154b0f3d8b98d55fbeeda475f8c72307cf02dc4c'),
 'conflict-gtk-offline-'+RUN+'-1':(12867497227,'sha256:7a6c734927ddee11e554d1a9b42ae7609eac762f22c28896ed303bf7d2d662fc'),
 'gtk-windows-package-'+RUN+'-1':(12867406998,'sha256:2f606c8e64c0ba9da2108c9cd661b976675cb4f5f7541ed4ad50b82e7e58b9e1')}
root=ROOT/'build/confirmation-diagnostic';package=root/'package';program=package/'bin/exreader-linux'
api=json.loads(subprocess.check_output(['gh','api','repos/'+os.environ['GITHUB_REPOSITORY']+'/actions/runs/'+RUN+'/artifacts?per_page=100'],text=True))
for name,(artifact_id,digest) in EXPECTED.items():
    matches=[a for a in api['artifacts'] if a['name']==name];assert len(matches)==1
    a=matches[0];assert a['id']==artifact_id and a['digest']==digest and a['workflow_run']['head_sha']==SOURCE and not a['expired']
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
state=json.loads((root/'offline/state.json').read_text());assert state['source_sha']==SOURCE and state['run_id']==RUN and state['attempt']=='1'
data=state['data'];assert sha(program)==data['gtk_program_sha256']=='a871a81e22cd32fb2bda041783183998499312979ad9ac63c562f31f05763a0a'
assert subprocess.check_output([str(program),'--version'],text=True).strip()=='3.42.0 1'
archived=root/'evidence/gtk-native';profile=archived/'profile'
print('GTK_CONFIRMATION_ARCHIVED_INITIAL '+(archived/'01-real-two-head-conflict.json').read_text(),flush=True)
assert all(not p.is_symlink() for p in profile.rglob('*'))
hashes={str(p.relative_to(profile)):sha(p) for p in profile.rglob('*') if p.is_file()}
results=[]
for trial in range(3):
    out=root/('trial-'+str(trial));out.mkdir();shutil.copytree(profile,out/'profile');(out/'profile').chmod(0o700)
    for p in (out/'profile').rglob('*'):p.chmod(0o700 if p.is_dir() else 0o600)
    host=Session(program.resolve(),(package/'Reader.otf').resolve(),out)
    catalog=out/'profile/library.sqlite.product.sqlite';report={'trial':trial,'complete':False,'snapshots':[]}
    def sql(q,args=()):
        with sqlite3.connect('file:'+str(catalog.resolve())+'?mode=ro',uri=True) as db:return db.execute(q,args).fetchall()
    def wires():return dict(sql('SELECT revision_id,body_json FROM reader_revisions'))
    def nodes():
        desktop=pyatspi.Registry.getDesktop(0);apps=[desktop[i] for i in range(desktop.childCount) if desktop[i].get_process_id()==host.process.pid]
        if not apps:return []
        assert len(apps)==1;pending=list(apps);found=[]
        while pending:
            node=pending.pop(0);found.append(node);assert len(found)<3000
            pending.extend(node[i] for i in range(node.childCount))
        return found
    def rows(tree):return [{'name':n.name,'role':n.getRoleName(),'showing':n.getState().contains(pyatspi.STATE_SHOWING),'sensitive':n.getState().contains(pyatspi.STATE_SENSITIVE)} for n in tree]
    def capture(name,tree):
        value={'name':name,'nodes':rows(tree)};report['snapshots'].append(value)
        (out/(name+'.json')).write_text(json.dumps(value,indent=2));print('GTK_CONFIRMATION_TREE '+json.dumps(value),flush=True)
        command('import','-window','root',out/(name+'.png'))
    def wait(predicate):
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            assert host.process.poll() is None
            value=predicate()
            if value:return value
            time.sleep(.1)
        raise TimeoutError('Native confirmation probe exceeded unchanged 30-second action budget')
    def named(name,tree):return [n for n in tree if n.name==name and n.getState().contains(pyatspi.STATE_SHOWING)]
    def buttons(name,tree):return [n for n in named(name,tree) if n.getRole()==pyatspi.ROLE_PUSH_BUTTON]
    def click(button):
        assert button.getState().contains(pyatspi.STATE_SENSITIVE)
        action=button.queryAction();assert action.nActions==1 and action.doAction(0)
    try:
        original=wires();title=sql('SELECT title FROM reader_books WHERE book_key=?',(data['windows_book'],))[0][0]
        host.launch();host.key('F2','ctrl+f','ctrl+a');host.paste(title);host.wait(lambda s:s['books']==1 and not s['shelf_loading'] and not s['shelf_restoring'],timeout=60)
        host.key('F2','Home','ctrl+e')
        wait(lambda:buttons('Resolve versions',nodes()))
        tree=nodes();capture('01-conflict',tree);resolve=buttons('Resolve versions',tree);assert len(resolve)==1
        save=buttons('Save',tree);assert len(save)==1 and not save[0].getState().contains(pyatspi.STATE_SENSITIVE)
        click(resolve[0]);wait(lambda:named('Yes',nodes()))
        tree=nodes();capture('02-confirmation',tree)
        raw=named('Yes',tree);yes=buttons('Yes',tree)
        report['raw_yes_matches']=rows(raw);report['actionable_yes_matches']=rows(yes)
        assert len(yes)==1,'Require one actual Yes push button, never choose a label or guess'
        click(yes[0]);wait(lambda:any(n.getState().contains(pyatspi.STATE_SENSITIVE) for n in buttons('Save',nodes())))
        tree=nodes();capture('03-explicit-preview',tree);cancel=buttons('Cancel',tree);assert len(cancel)==1;click(cancel[0])
        wait(lambda:not buttons('Save',nodes()));assert wires()==original
        assert not Path(str(catalog)+'.commands.pending').exists()
        report.update(complete=True,graph_unchanged=True,program_sha256=sha(program));results.append(report)
    except Exception:
        report['error']=traceback.format_exc()
        try:capture('failure',nodes())
        except Exception:report['capture_error']=traceback.format_exc()
        raise
    finally:
        (out/'result.json').write_text(json.dumps(report,indent=2));print('GTK_CONFIRMATION_TRIAL '+json.dumps(report),flush=True)
        if host.process and host.process.poll() is None:host.process.kill();host.process.wait(timeout=15)
        if host.log and not host.log.closed:host.log.close()
assert hashes=={str(p.relative_to(profile)):sha(p) for p in profile.rglob('*') if p.is_file()}
summary={'diagnostic_only':True,'source_sha':os.environ['GITHUB_SHA'],'run_id':os.environ['GITHUB_RUN_ID'],'attempt':os.environ['GITHUB_RUN_ATTEMPT'],'pinned_source':SOURCE,'pinned_run':RUN,'artifact_identities':EXPECTED,'trials':results}
(root/'summary.json').write_text(json.dumps(summary,indent=2));print('GTK_CONFIRMATION_DIAGNOSTIC '+json.dumps(summary),flush=True)
