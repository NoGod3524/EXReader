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
        cmake(profile+'-owner',ROOT/'tests/reader_gtk_raw3',OUT/(profile+'-owner'),prefix,
          extra=extra,targets=('gtk-raw3-owner','exreader-linux'))
    run('package',['python3','tools/build_linux_host.py','--sdk','build/reading-library/stage','--sdk-version','3.41.0',
      '--binary',OUT/'raw-owner/actual-owner/gtk-host/exreader-linux','--output',OUT/'package'])


def process(profile,source,mode,label,legacy=False,env=None):
    binary=OUT/(('legacy' if legacy else 'raw')+'-owner/gtk-raw3-owner')
    report=OUT/(label+'.json')
    args=[binary,profile,ROOT/'tests/fixtures/fonts/primary.ttf',source,mode,report,'3.40.0']
    if legacy:args+=['3.40.0']
    run(label,args,timeout=180,env=env)
    value=json.loads(report.read_text());assert value['accepted'] and value['check_count']==len(value['checks']) and all(row['passed'] for row in value['checks'])
    return dict(label=label,program_sha256=sha(binary),report=report.name,report_sha256=sha(report),checks=value['check_count'],mode=mode,legacy=legacy)


def killed(profile,source,label,stage,legacy=False):
    marker=OUT/(label+'.marker');report=OUT/(label+'.partial.json');log=OUT/(label+'.log')
    environment=dict(os.environ,GTK_RECORD_KILL_STAGE=stage,GTK_RECORD_KILL_MARKER=str(marker))
    binary=OUT/(('legacy' if legacy else 'raw')+'-owner/gtk-raw3-owner')
    args=[binary,profile,ROOT/'tests/fixtures/fonts/primary.ttf',source,'pending',report,'3.40.0']
    if legacy:args+=['3.40.0']
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
    phases=[];kills=[];pdf=ROOT/'tests/fixtures/pdf-public-text.pdf'
    assert pdf.stat().st_size==8845 and sha(pdf)=='5627a430fa04cbe11d38eb2682e336ef21e147d445753ed46ed11a7d5e3167cc'
    initial=OUT/'raw-profile';initial.mkdir()
    phases.append(process(initial,pdf,'seed','raw-seed'))
    phases.append(process(initial,pdf,'verify','raw-reopen'))
    for stage in ('before','after'):
        profile=OUT/('kill-'+stage);shutil.copytree(initial,profile)
        kills.append(killed(profile,pdf,'raw-kill-'+stage,stage))
        environment=dict(os.environ,GTK_RECORD_EXPECT_CREATED='1' if stage=='before' else '0')
        phases.append(process(profile,pdf,'retry','raw-retry-'+stage,env=environment))
        phases.append(process(profile,pdf,'verify','raw-verify-'+stage))
    txt=OUT/'Legacy source.txt';txt.write_text('Public original legacy text for exact original requests and independent reading.\n'*20)
    legacy=OUT/'legacy-profile';legacy.mkdir()
    phases.append(process(legacy,txt,'seed','legacy-seed',legacy=True))
    phases.append(process(legacy,txt,'legacy-restore','raw-retained-v1-v2'))
    for stage in ('before','after'):
        profile=OUT/('legacy-kill-'+stage);shutil.copytree(legacy,profile)
        kills.append(killed(profile,txt,'legacy-kill-'+stage,stage,legacy=True))
        environment=dict(os.environ,GTK_RECORD_EXPECT_CREATED='1' if stage=='before' else '0')
        phases.append(process(profile,txt,'retry','legacy-exact-raw-retry-'+stage,env=environment))
    return phases,kills


def main():
    assert os.environ.get('GITHUB_ACTIONS')=='true'
    parser=argparse.ArgumentParser();parser.add_argument('--mode',choices=('build','full'),default='full');args=parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=False)
    report=dict(accepted=False,source_sha=os.environ['GITHUB_SHA'],run_id=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'],
      scope='explicit GTK raw3 actual owner candidate',complete_product=False,performance_accepted=False,six_platform_accepted=False,physical_device_execution=False)
    try:
        build();report['built']=True
        if args.mode=='full':report['phases'],report['kills']=exercise()
    finally:
        report['files']={p.relative_to(OUT).as_posix():dict(bytes=p.stat().st_size,sha256=sha(p)) for p in OUT.rglob('*') if p.is_file() and p.name!='result.json'}
        (OUT/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({key:value for key,value in report.items() if key!='files'}),flush=True)


if __name__=='__main__':main()
