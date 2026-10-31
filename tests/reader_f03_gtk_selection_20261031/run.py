# SPDX-License-Identifier: MIT
"""Actions-only live collection selection evidence; never alters product code."""
import argparse, configparser, hashlib, json, os, re, sqlite3, subprocess, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
from check_linux_host import Session, command
import pyatspi

def main():
    p=argparse.ArgumentParser()
    for n in ('payload','command-consumer','output'): p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();assert os.environ.get('GITHUB_ACTIONS')=='true'
    out=a.output.resolve();out.mkdir()
    src=out/'Selection original.txt';src.write_text('Selection identity proof.\n'*300)
    host=Session((a.payload/'bin/exreader-linux').resolve(),(a.payload/'Reader.otf').resolve(),out)
    dbpath=out/'profile/library.sqlite.product.sqlite'
    checks=[];snapshots=[];calls=[]
    result={'accepted':False,'source':os.environ['GITHUB_SHA'],'run':os.environ['GITHUB_RUN_ID'],
      'attempt':os.environ['GITHUB_RUN_ATTEMPT'],'checks':checks,'snapshots':snapshots,
      'setup_calls':calls,'scope':'live collections only; retained off-page selection allowed',
      'F03_accepted':False,'formal_count':'95/108','product_changed':False}
    def sql(q,v=()):
        with sqlite3.connect('file:'+str(dbpath)+'?mode=ro',uri=True) as c:return c.execute(q,v).fetchall()
    def obs():
        c=configparser.ConfigParser();c.read(host.observe)
        return dict(c['collections']) if c.has_section('collections') else {}
    def ready(pred=lambda s:True):
        host.wait(lambda h:not h.get('busy') and not h.get('shelf_loading') and pred(obs()),timeout=60)
        return obs()
    def win(title,present=True):
        end=time.monotonic()+35
        while time.monotonic()<end:
            assert host.process.poll() is None
            r=subprocess.run(['xdotool','search','--onlyvisible','--all','--pid',str(host.process.pid),'--name','^'+re.escape(title)+'$'],capture_output=True,text=True,timeout=5)
            if bool(r.stdout.strip())==present:
                if present:
                    w=r.stdout.splitlines()[-1];command('xdotool','windowactivate','--sync',w);return w
                return
            time.sleep(.1)
        raise TimeoutError(title+' '+repr(obs()))
    def field(key,value):
        host.key('alt+'+key,'ctrl+a');host.paste(str(value))
    def save(title='Collection details'):
        host.key('Return');win(title,False);return ready(lambda s:s.get('editor')=='0')
    def open_org():
        command('xdotool','windowactivate','--sync',host.window)
        host.key('F2','Home','ctrl+shift+c');win('Library collections');ready(lambda s:s.get('visible')=='1')
    def setkind(k):
        host.key('alt+t','Home');ready(lambda s:s.get('kind')=='0')
        for i in range(k):host.key('Down');ready(lambda s:s.get('kind')==str(i+1))
        host.key('Tab');ready()
    def native(k,name,ordinal):
        f=out/(hashlib.sha256(name.encode()).hexdigest()+'.txt');f.write_text(name)
        cmd=[str(a.command_consumer.resolve()),'group',str(dbpath),'-','-',str(k),'0','-',str(f),'-',str(ordinal)]
        r=subprocess.run(cmd,capture_output=True,text=True,timeout=60)
        assert r.returncode==0,(r.returncode,r.stderr)
        v=json.loads(r.stdout);calls.append({'kind':k,'name':name,'ordinal':ordinal,'result':v})
        assert v['status']==0,v
        return v['key']
    def tree():
        desktop=pyatspi.Registry.getDesktop(0)
        apps=[x for x in desktop if x.get_process_id()==host.process.pid]
        assert len(apps)==1,('AT-SPI process count',len(apps))
        rows=[];nodes=[]
        def walk(n,depth=0,under_groups=False):
            assert len(rows)<5000 and depth<40,'accessibility tree bound'
            st=n.getState();under_groups=under_groups or n.name=='Collection groups'
            row={'name':n.name or '', 'role':n.getRoleName(),'selected':st.contains(pyatspi.STATE_SELECTED),
                 'showing':st.contains(pyatspi.STATE_SHOWING),'depth':depth,'under_groups':under_groups}
            rows.append(row);nodes.append(n)
            for ch in n:walk(ch,depth+1,under_groups)
        walk(apps[0]);return rows,nodes
    def capture(label):
        rows,nodes=tree();state=ready()
        shot=out/(label+'.png');command('import','-window',win('Library collections'),shot)
        snapshots.append({'label':label,'state':state,'accessibility':rows,'screenshot':shot.name})
        return rows,nodes,state
    def visual_groups(nodes):
        choices=[n for n in nodes if n.name=='Collection groups' and n.getRoleName()!='scroll pane']
        lists=[n for n in choices if any(ch.getRoleName() in ('list item','table row') for ch in n)]
        assert len(lists)==1,('ambiguous accessible group list',[(n.getRoleName(),n.childCount) for n in choices])
        entries=list(lists[0])
        return [n.name for n in entries],[n.name for n in entries if n.getState().contains(pyatspi.STATE_SELECTED)]
    def record(n):
        assert n not in checks;checks.append(n);print(json.dumps({'check':n,'pass':True}),flush=True)
    try:
        host.launch();host.dialog(src);host.wait(lambda h:h.get('book',0)>0);host.close()
        for k in range(3):
            for i in range(51):native(k,'F03-%d-group-%02d'%(k,i),i+1 if k==0 else 0)
        assert len(calls)==153
        host.launch();open_org()
        for k,table,keycol in ((0,'reader_shelves','shelf_id'),(1,'reader_tags','tag_id'),(2,'reader_series','series_id')):
            setkind(k)
            order='ordinal,'+keycol if k==0 else keycol
            expected=sql('SELECT '+keycol+',name FROM '+table+' WHERE deleted=0 ORDER BY '+order)
            assert len(expected)==51
            s=ready(lambda s:s.get('group_count')=='50' and s.get('group_after')=='1')
            assert s['group_ids'].split(',')==[x[0] for x in expected[:50]]
            rows,nodes,s=capture('kind%d-first'%k);names,_=visual_groups(nodes)
            assert names==[x[1] for x in expected[:50]],names
            record('kind%d_live_first_page_exact50'%k)
            host.key('ctrl+Page_Down');ready(lambda s:s.get('group_count')=='1')
            host.key('alt+g','Home');target,oldname=expected[-1]
            s=ready(lambda s:s.get('selected_id')==target)
            rows,nodes,s=capture('kind%d-second-selected'%k)
            assert visual_groups(nodes)==([oldname],[oldname])
            record('kind%d_second_page_actual_selected_row'%k)
            # A genuine UI membership provides a distinct right-pane target.
            host.key('alt+a');win('Book classification');save('Book classification')
            ready(lambda s:s.get('member_count')=='1')
            member=obs()['member_keys']
            before=sql('SELECT (SELECT count(*) FROM reader_revisions),(SELECT count(*) FROM reader_outbox)')[0]
            host.key('alt+r');win('Collection details');newname='F03-renamed-kind%d'%k;field('n',newname)
            if k==0:field('p',0)
            save();s=ready(lambda s:s.get('selected_name')==newname and s.get('group_count')=='50')
            assert s['selected_id']==target and s['member_keys']==member and s['removed']=='0'
            assert sql('SELECT name FROM '+table+' WHERE '+keycol+'=?',(target,))==[(newname,)]
            assert sql('SELECT (SELECT count(*) FROM reader_revisions),(SELECT count(*) FROM reader_outbox)')[0]==(before[0]+1,before[1]+1)
            rows,nodes,s=capture('kind%d-after-rename'%k);names,selected=visual_groups(nodes)
            first=sql('SELECT '+keycol+',name FROM '+table+' WHERE deleted=0 ORDER BY '+order+' LIMIT 50')
            assert s['group_ids'].split(',')==[x[0] for x in first]
            assert names==[x[1] for x in first]
            target_visible=target in [x[0] for x in first]
            assert selected==([newname] if target_visible else []),(selected,target_visible)
            assert len([r for r in rows if r['name']==newname and r['role']=='label' and r['showing'] and not r['under_groups']])==1,'right/current title absent or ambiguous'
            record('kind%d_refresh_current_identity_and_visible_selection_consistent'%k)
            # Retained off-page selection is legal only if the next edit resolves that exact group.
            host.key('alt+r');win('Collection details');r,n=tree()
            fields=[x for x in n if x.name=='Collection name']
            assert len(fields)==1 and fields[0].queryText().getText(0,-1)==newname
            snap=out/('kind%d-retained-editor.png'%k);command('import','-window',win('Collection details'),snap)
            draft='F03-UNSAVED-kind%d'%k;field('n',draft)
            dirty_rows,dirty_nodes=tree()
            dirty_fields=[x for x in dirty_nodes if x.name=='Collection name']
            assert len(dirty_fields)==1 and dirty_fields[0].queryText().getText(0,-1)==draft
            snapshots.append({'label':'kind%d-dirty-before-cancel'%k,'accessibility':dirty_rows,'draft':draft})
            host.key('Escape');win('Collection details',False);cancelled=ready()
            assert cancelled['selected_id']==target and cancelled['selected_name']==newname and cancelled['member_keys']==member
            assert sql('SELECT name FROM '+table+' WHERE '+keycol+'=?',(target,))==[(newname,)]
            assert sql('SELECT (SELECT count(*) FROM reader_revisions),(SELECT count(*) FROM reader_outbox)')[0]==(before[0]+1,before[1]+1)
            record('kind%d_retained_target_reopen_and_cancel_no_write'%k)
            if not target_visible:host.key('ctrl+Page_Down');ready(lambda s:s.get('group_count')=='1')
            rows,nodes,s=capture('kind%d-return-target'%k)
            assert s['selected_id']==target and visual_groups(nodes)[1]==[newname]
            record('kind%d_return_page_recovers_same_selected_identity'%k)
        host.key('alt+F4');win('Library collections',False);host.close()
        assert len(checks)==15
        result['accepted']=True
    except Exception as e:
        result['error']=repr(e)
        try: result['failure_state']=obs();result['failure_tree']=tree()[0]
        except Exception as inner:result['diagnostic_error']=repr(inner)
        raise
    finally:
        (out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
        print('F03_SELECTION '+json.dumps({'accepted':result['accepted'],'checks':len(checks),'setup':len(calls),'error':result.get('error')}),flush=True)
        if host.process and host.process.poll() is None:
            host.process.terminate()
            try:host.process.wait(timeout=15)
            except subprocess.TimeoutExpired:host.process.kill();host.process.wait(timeout=15)
if __name__=='__main__':main()
