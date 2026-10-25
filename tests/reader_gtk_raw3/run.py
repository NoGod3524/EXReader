"""Actions-only installed raw families and actual GTK worker processes."""
import argparse
import configparser
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'build/gtk-raw3'
RAW={'revisions','commands','desktop-metadata','sync','session','reading-state','reading-commands','annotation-view'}


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(label,args,timeout=900,env=None,expect=0):
    print('RUN '+label,flush=True)
    done=subprocess.run(list(map(str,args)),cwd=ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=timeout,env=env)
    (OUT/(label+'.log')).write_text(done.stdout+'\n'+done.stderr)
    print(done.stdout[-6000:],flush=True)
    if done.returncode!=expect:raise RuntimeError(label+': '+str(done.returncode)+'\n'+done.stderr[-6000:])
    return done


def cmake(label,source,binary,prefix,raw=False,extra=(),targets=(),install=False):
    sdk=ROOT/'build/reading-library/stage'
    options=['-DCMAKE_PREFIX_PATH='+str(prefix)+';'+str(sdk),'-DCMAKE_INSTALL_PREFIX='+str(prefix),
      '-DREADER_PRODUCT_PREFIX='+str(prefix),'-DEXR_SDK='+str(sdk),'-DEXR_SDK_VERSION=3.41.0']
    if raw:options+=['-DEXR_READER_SELECTOR_BYTES_CANDIDATE=ON']
    run(label+'-configure',['cmake','-S',source,'-B',binary,'-G','Ninja','-DCMAKE_BUILD_TYPE=Release',*options,*extra])
    run(label+'-build',['cmake','--build',binary,'--parallel','4',*(['--target',*targets] if targets else [])])
    if install:run(label+'-install',['cmake','--install',binary])


def build():
    run('sdk-configure',['cmake','--preset','reading-library'])
    run('sdk-build',['cmake','--build','--preset','reading-library','--parallel','4'])
    run('sdk-install',['cmake','--install','build/reading-library'])
    for profile in ('raw','legacy'):
        prefix=OUT/(profile+'-stage')
        modules=[('product','apps/reader/store/native'),('webdav','extras/webdav')]+[(m,'apps/reader/'+m) for m in
          ('revisions','commands','desktop-metadata','sync','session')]+[('credentials','extras/credentials'),('sideload','extras/sideload')]+[
          (m,'apps/reader/'+m) for m in ('reading-state','reading-commands','annotation-view')]
        if profile=='raw':modules += [(m,'apps/reader/'+m) for m in ('preferences','search','navigation','batch-import')]+[('drop','extras/desktop-drop')]
        for module,source in modules:
            cmake(profile+'-'+module,ROOT/source,OUT/(profile+'-'+module),prefix,profile=='raw' and module in RAW,install=True)
        extra=['-DHOST_SOURCE='+str(ROOT),'-DMODULE_PREFIX='+str(prefix)]
        if profile=='legacy':extra+=['-DLEGACY_PROFILE=ON']
        else:
            extra+=['-DEXR_READER_PAGE_BACKGROUND=ON']
            for option,name in [('PREFERENCES','PREFERENCES'),('SEARCH','SEARCH'),('NAVIGATION','NAVIGATION'),('BATCH_IMPORT','BATCH_IMPORT'),('DROP_IMPORT','DESKTOP_DROP')]:
                extra+=['-DEXR_READER_GTK_'+option+'=ON','-DREADER_'+name+'_PREFIX='+str(prefix)]
        targets=('gtk-raw3-owner','exreader-linux')
        cmake(profile+'-owner',ROOT/'tests/reader_gtk_raw3',OUT/(profile+'-owner'),prefix,extra=extra,targets=targets)
    run('package',['python3','tools/build_linux_host.py','--sdk','build/reading-library/stage','--sdk-version','3.41.0',
      '--binary',OUT/'raw-owner/actual-owner/gtk-host/exreader-linux','--output',OUT/'package'])


def process(profile,source,mode,label,legacy=False,env=None):
    binary=OUT/(('legacy' if legacy else 'raw')+'-owner/gtk-raw3-owner')
    report=OUT/(label+'.json')
    args=[binary,profile,ROOT/'tests/fixtures/fonts/primary.ttf',source,mode,report,'3.41.0']
    if legacy:args+=['3.41.0']
    run(label,args,timeout=180,env=env)
    value=json.loads(report.read_text());assert value['accepted'] and value['check_count']==len(value['checks']) and all(row['passed'] for row in value['checks'])
    return dict(label=label,program_sha256=sha(binary),report=report.name,report_sha256=sha(report),checks=value['check_count'],mode=mode,legacy=legacy)


def profile_refusals():
    sdk=ROOT/'build/reading-library/stage';raw=OUT/'raw-stage';legacy=OUT/'legacy-stage';cases=[]
    def rejected(name,prefix,legacy_profile,needle):
        args=['cmake','-S',ROOT/'tests/reader_gtk_raw3','-B',OUT/('refuse-'+name),'-G','Ninja','-DCMAKE_BUILD_TYPE=Release',
          '-DHOST_SOURCE='+str(ROOT),'-DEXR_SDK='+str(sdk),'-DEXR_SDK_VERSION=3.41.0','-DMODULE_PREFIX='+str(prefix),
          '-DCMAKE_PREFIX_PATH='+str(prefix)+';'+str(sdk),'-DLEGACY_PROFILE='+('ON' if legacy_profile else 'OFF')]
        done=run('refuse-'+name,args,expect=1)
        assert needle in done.stdout+done.stderr,(name,done.stderr)
        cases.append(dict(name=name,rejected=True,exit_code=done.returncode,required_diagnostic=needle))
    rejected('raw-host-old-family',legacy,False,'0.2.0')
    rejected('legacy-host-raw-family',raw,True,'0.1.0')
    for name,relative,needle in [('escaped-header','include/reader_reading_state.h','header origin mismatch'),
                                ('escaped-archive','lib/libreader_revisions.a','archive origin mismatch')]:
        with tempfile.TemporaryDirectory(prefix='gtk-raw-origin-',dir=ROOT/'build') as temporary:
            clone=Path(temporary)/'stage';shutil.copytree(raw,clone)
            changed=clone/relative;changed.unlink();changed.symlink_to(legacy/relative)
            rejected(name,clone,False,needle)
    return cases


def killed(profile,source,label,stage,legacy=False):
    marker=OUT/(label+'.marker');report=OUT/(label+'.partial.json');log=OUT/(label+'.log')
    environment=dict(os.environ,GTK_RECORD_KILL_STAGE=stage,GTK_RECORD_KILL_MARKER=str(marker))
    binary=OUT/(('legacy' if legacy else 'raw')+'-owner/gtk-raw3-owner')
    args=[binary,profile,ROOT/'tests/fixtures/fonts/primary.ttf',source,'pending',report,'3.41.0']
    if legacy:args+=['3.41.0']
    with log.open('w') as stream:
        child=subprocess.Popen(list(map(str,args)),cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,env=environment)
        try:
            end=time.monotonic()+90
            while time.monotonic()<end:
                assert child.poll() is None,'owner exited before durable marker'
                if marker.exists():break
                time.sleep(.02)
            else:raise TimeoutError('actual owner durable marker missing')
            child.kill();assert child.wait(timeout=15)==-signal.SIGKILL
        finally:
            if child.poll() is None:child.kill();child.wait()
    pending=profile/'library.sqlite.product.sqlite.reading.pending'
    data=pending.read_bytes();assert data
    parser=configparser.ConfigParser(interpolation=None);parser.read_string(data.decode());request=parser['request']
    assert request['version']==('1' if legacy else '2')
    return dict(label=label,stage=stage,pid=child.pid,signal='SIGKILL',marker=marker.read_text(),pending_sha256=sha(pending),
      pending_bytes=len(data),version=int(request['version']),revision=request['revision'])


def exercise():
    phases=[];kills=[];refusals=[];pdf=ROOT/'tests/fixtures/pdf-public-text.pdf'
    assert pdf.stat().st_size==8845 and sha(pdf)=='5627a430fa04cbe11d38eb2682e336ef21e147d445753ed46ed11a7d5e3167cc'
    initial=OUT/'raw-profile';initial.mkdir(mode=0o700)
    phases.append(process(initial,pdf,'seed','raw-seed'))
    phases.append(process(initial,pdf,'verify','raw-reopen'))
    for stage in ('before','after'):
        profile=OUT/('kill-'+stage);shutil.copytree(initial,profile)
        kills.append(killed(profile,pdf,'raw-kill-'+stage,stage))
        refused=OUT/('legacy-refuses-native-'+stage);shutil.copytree(profile,refused)
        pending=refused/'library.sqlite.product.sqlite.reading.pending';before=pending.read_bytes()
        import sqlite3
        def inventory():
            connection=sqlite3.connect((refused/'library.sqlite.product.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
            try:return connection.execute('SELECT revision_id,CAST(body_json AS BLOB),body_sha256 FROM reader_revisions ORDER BY revision_id').fetchall()
            finally:connection.close()
        immutable=inventory()
        done=run('legacy-refuses-native-'+stage,[OUT/'legacy-owner/gtk-raw3-owner',refused,
          ROOT/'tests/fixtures/fonts/primary.ttf',pdf,'retry',OUT/('legacy-refuses-native-'+stage+'.partial.json'),'3.41.0','3.41.0'],expect=1)
        assert 'compatibility check failed: original private request retained before explicit retry' in done.stderr
        assert pending.read_bytes()==before and inventory()==immutable
        refusals.append(dict(stage=stage,pending_sha256=sha(pending),pending_bytes=len(before),retained_wire_count=len(immutable),legacy_exit=done.returncode))
        environment=dict(os.environ,GTK_RECORD_EXPECT_CREATED='1' if stage=='before' else '0')
        phases.append(process(profile,pdf,'retry','raw-retry-'+stage,env=environment))
        phases.append(process(profile,pdf,'verify','raw-verify-'+stage))
    txt=OUT/'Legacy source.txt';txt.write_text('Public original legacy text for exact original requests and independent reading.\n'*20)
    legacy=OUT/'legacy-profile';legacy.mkdir(mode=0o700)
    phases.append(process(legacy,txt,'seed','legacy-seed',legacy=True))
    phases.append(process(legacy,txt,'legacy-restore','raw-retained-v1-v2'))
    for stage in ('before','after'):
        profile=OUT/('legacy-kill-'+stage);shutil.copytree(legacy,profile)
        kills.append(killed(profile,txt,'legacy-kill-'+stage,stage,legacy=True))
        environment=dict(os.environ,GTK_RECORD_EXPECT_CREATED='1' if stage=='before' else '0')
        phases.append(process(profile,txt,'retry','legacy-exact-raw-retry-'+stage,env=environment))
    return phases,kills,refusals


def network(phases):
    from peer import load,fixture,populate
    proof,manifest,wires,originals,operations=load(OUT/'mac-peer')
    reports=[]
    def receive(label,selected,books,index,mode):
        server=fixture(ROOT/('build/'+label+'-tls-private'),OUT/(label+'-tls.py'))
        try:
            populate(server,selected,books)
            environment=dict(os.environ,GTK_RAW3_DAV_URL=server.url,GTK_RAW3_DAV_AUTH=server.auth)
            script='openbox > "$2/openbox.log" 2>&1 & wm=$!; trap "kill $wm || true" EXIT; python3 tests/reader_gtk_raw3/account_ui.py --payload "$1" --output "$2/account"'
            # The owner creates its private profile; keep window-manager logs separate.
            container=OUT/(label+'-display');container.mkdir()
            args=['xvfb-run','-a','-s','-screen 0 1440x1200x24','dbus-run-session','--','bash','-euc',script,'gtk-raw3-ui',OUT/'package/EXReader-Linux',container]
            run(label+'-network',args,timeout=240,env=environment)
            ui_output=container/'account';profile=ui_output/'profile';value=json.loads((ui_output/'report.json').read_text())
            assert value['accepted'] and value['completed_shards']==256 and value['session_state']==4 and value['session_attempt']==1 and value['pulled']==len(selected)
            for row,data in books.values():
                cached=profile/'sync-work'/(row['sha256']+'.'+row['format']);assert cached.read_bytes()==data
            phases.append(process(profile,index,mode,label+'-owner'))
            phases.append(process(profile,index,mode,label+'-reopen'))
            import sqlite3
            connection=sqlite3.connect((profile/'library.sqlite.product.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
            try:retained={rid:body for rid,body in connection.execute('SELECT revision_id,CAST(body_json AS BLOB) FROM reader_revisions')}
            finally:connection.close()
            assert len(retained)==len(selected) and all(retained[rid]==data for rid,digest,data in selected)
            assert server.requests and all(row['authenticated'] for row in server.requests)
            request_log=OUT/(label+'-requests.json');request_log.write_text(json.dumps(server.requests,indent=2)+'\n')
            reports.append(dict(label=label,session=value,wire_count=len(selected),originals=len(books),
              immutable_wires_unchanged=True,requests=request_log.name,actual_gtk_ui_executed=True))
        finally:server.close()
    receive('mac11',wires,originals,OUT/'mac-peer/sender/books.tsv','receive')
    retained={rid:(json.loads(data),digest,data) for rid,data,digest in operations}
    null_id=proof['null_revision_ids'][0];null=retained[null_id][0];book=null['payload']['book_key'];needed=set()
    def ancestors(rid):
        if rid in needed:return
        needed.add(rid)
        for parent in retained[rid][0]['parents']:ancestors(parent)
    ancestors(null_id)
    for rid,(wire,digest,data) in retained.items():
        if wire['entity_kind']=='book' and wire['entity_key']==book:ancestors(rid)
    selected=[(rid,retained[rid][1],retained[rid][2]) for rid in sorted(needed)]
    index=OUT/'mac-peer/null-books.tsv';index.write_text(book+' -1\n')
    receive('mac-null',selected,{book:originals[book]},index,'null-receive')
    return dict(peer=proof,phases=reports)


def main():
    assert os.environ.get('GITHUB_ACTIONS')=='true'
    parser=argparse.ArgumentParser();parser.add_argument('--mode',choices=('build','full'),default='full');args=parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=False)
    report=dict(accepted=False,source_sha=os.environ['GITHUB_SHA'],run_id=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'],
      scope='explicit GTK raw3 actual owner candidate',complete_product=False,performance_accepted=False,six_platform_accepted=False,physical_device_execution=False)
    try:
        build();report['built']=True
        report['profile_refusals']=profile_refusals()
        if args.mode=='full':
            report['phases'],report['kills'],report['legacy_native_pending_refusals']=exercise()
            report['network']=network(report['phases'])
            report['accepted']=True
    finally:
        report['files']={p.relative_to(OUT).as_posix():dict(bytes=p.stat().st_size,sha256=sha(p)) for p in OUT.rglob('*') if p.is_file() and p.name!='result.json'}
        (OUT/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({key:value for key,value in report.items() if key!='files'}),flush=True)


if __name__=='__main__':main()
