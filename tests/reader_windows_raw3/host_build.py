"""Actions-only actual installed Win32 host in separate legacy/raw profiles."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'build/windows-raw3-host'
RAW_MODULES={'revisions','commands','desktop-metadata','sync','session','reading-state','reading-commands','annotation-view','bulk-organization'}
MODULES=('extras/webdav','extras/credentials','extras/sideload','apps/reader/revisions','apps/reader/commands',
         'apps/reader/desktop-metadata','apps/reader/sync','apps/reader/session','apps/reader/reading-state',
         'apps/reader/reading-commands','apps/reader/annotation-view','apps/reader/search','apps/reader/navigation',
         'apps/reader/cloud-import','apps/reader/bulk-organization','apps/reader/preferences')


def run(argv,name,timeout=1800):
    proc=subprocess.run([str(v) for v in argv],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                        encoding='utf-8',errors='replace',timeout=timeout)
    (OUT/'logs'/(name+'.log')).write_text(proc.stdout,encoding='utf-8')
    if proc.returncode:
        print(proc.stdout[-22000:],flush=True)
        raise RuntimeError(name+' exit='+str(proc.returncode))
    print(name+' success',flush=True)


def configure(source,build,options,name):
    run(['cmake','-S',source,'-B',build,'-G','Ninja','-DCMAKE_BUILD_TYPE=Release',*options],name+'-configure')
    run(['cmake','--build',build,'--parallel','4','--verbose'],name+'-build')


def owner_run(exe,mode,work,pdf,*extra):
    run([exe,mode,work,pdf,*extra],'owner-'+work.name+'-'+mode,300)
    report=json.loads((work/('report-'+mode+'.json')).read_text(encoding='utf-8'))
    raw=exe.parent.name=='raw-owner-probe'
    versions={key:('0.2.0' if raw else '0.1.0') for key in
              ('commands','metadata','reading_state','reading_commands','annotation_view','sync','session')}
    versions['revisions']='0.4.0' if raw else '0.3.0'
    if (report.get('ok') is not True or report.get('source_sha')!=os.environ['GITHUB_SHA']
            or report.get('mode')!=mode or report.get('sdk_version')!='3.41.0'
            or report.get('profile')!=('raw3' if raw else 'legacy') or report.get('versions')!=versions
            or report.get('owner_source_sha256')!=hashlib.sha256(
                (ROOT/'apps/reader/desktop/windows_records_owner.cpp').read_bytes()).hexdigest()
            or report.get('program_sha256')!=hashlib.sha256(exe.read_bytes()).hexdigest()
            or not report.get('checks') or any(c.get('pass') is not True for c in report['checks'])):
        raise RuntimeError('Owner evidence rejected: '+str(work)+' '+mode)
    return report


def killed_owner(exe,legacy_exe,work,pdf,phase,legacy=False):
    work.mkdir()
    marker=work/'phase.json'
    args=[exe,'legacy-child' if legacy else 'child',work,pdf]
    if not legacy:args.append(str(phase))
    args.append(marker)
    with (OUT/'logs'/('owner-'+work.name+'-child.log')).open('w',encoding='utf-8') as log:
        child=subprocess.Popen([str(v) for v in args],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
        try:
            deadline=time.monotonic()+180
            evidence=None
            while time.monotonic()<deadline:
                if child.poll() is not None:raise RuntimeError('Owner exited before kill marker')
                try:evidence=json.loads(marker.read_text(encoding='utf-8'))
                except (FileNotFoundError,json.JSONDecodeError):pass
                if evidence is not None:break
                time.sleep(0.1)
            if (not evidence or evidence.get('pid')!=child.pid or evidence.get('phase')!=phase
                    or evidence.get('pending_bytes',0)<=0
                    or len(evidence.get('pending_sha256',''))!=64
                    or evidence.get('private_magic')!=('EXRRD001' if legacy else 'EXRRD002')):
                raise RuntimeError('Missing or invalid flushed owner kill marker')
            pending=(work/'pending.bin').read_bytes()
            if (len(pending)!=evidence['pending_bytes']
                    or hashlib.sha256(pending).hexdigest()!=evidence['pending_sha256']):
                raise RuntimeError('Kill marker differs from actual pending file')
            child.kill()  # Windows TerminateProcess, outside the real owner.
            child.wait(timeout=30)
            if (work/'pending.bin').read_bytes()!=pending:
                raise RuntimeError('Pending bytes changed during actual process termination')
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=30)
    (work/'external-kill.json').write_text(json.dumps(dict(marker=evidence,exit_code=child.returncode,
        terminated_by_driver=True),indent=2)+'\n',encoding='utf-8')
    if legacy:
        owner_run(legacy_exe,'reject-legacy-private',work,pdf)
        if (work/'pending.bin').read_bytes()!=pending:
            raise RuntimeError('Raw writer changed the original legacy pending file')
        owner_run(legacy_exe,'legacy-retry',work,pdf)
    else:
        owner_run(legacy_exe,'reject-private',work,pdf)
        if (work/'pending.bin').read_bytes()!=pending:
            raise RuntimeError('Legacy writer changed the original raw pending file')
        owner_run(exe,'verify-child',work,pdf,str(phase))
    if (work/'pending-before-retry.bin').read_bytes()!=pending or (work/'pending.bin').exists():
        raise RuntimeError('Recovery did not consume exactly the original killed-process request')


def main():
    if os.environ.get('GITHUB_ACTIONS')!='true' or sys.platform!='win32':
        raise RuntimeError('Windows Actions only')
    OUT.mkdir(parents=True,exist_ok=False);(OUT/'logs').mkdir()
    fixture=(ROOT/'tests/fixtures/pdf-public-text.pdf').read_bytes()
    if (len(fixture)!=8845 or hashlib.sha256(fixture).hexdigest()!=
            '5627a430fa04cbe11d38eb2682e336ef21e147d445753ed46ed11a7d5e3167cc'):
        raise RuntimeError('Original NUL PDF identity differs')
    sdk=OUT/'sdk-stage';product=OUT/'product-stage'
    run(['cmake','--preset','reading-library','-B',OUT/'sdk-build','-DCMAKE_INSTALL_PREFIX='+str(sdk)],'sdk-configure')
    run(['cmake','--build',OUT/'sdk-build','--parallel','4'],'sdk-build')
    run(['cmake','--install',OUT/'sdk-build'],'sdk-install')
    configure(ROOT/'apps/reader/store/native',OUT/'product-build',['-DCMAKE_INSTALL_PREFIX='+str(product)],'product')
    run(['ctest','--test-dir',OUT/'product-build','--output-on-failure','--no-tests=error','--timeout','180'],'product-original-tests')
    run(['cmake','--install',OUT/'product-build'],'product-install')
    run([sys.executable,'-m','pip','install','uiautomation==2.0.29'],'native-ui-dependency')
    run([sys.executable,'-c',"from tools.host_font import fetch; fetch('build/host-font-cache')"],'native-ui-font')
    fixtures=OUT/'compact-fixtures'
    run([sys.executable,ROOT/'tests/reader_windows_preferences/make_fixtures.py',
         '--output',fixtures],'native-ui-fixtures')
    profiles=[]
    for raw in (False,True):
        name='raw' if raw else 'legacy'
        stage=OUT/(name+'-stage')
        prefix=';'.join(map(str,(stage,product,sdk)))
        for module in MODULES:
            label=Path(module).name
            options=['-DCMAKE_INSTALL_PREFIX='+str(stage),'-DCMAKE_PREFIX_PATH='+prefix,
                     '-DEXR_SDK='+str(sdk),'-DEXR_SDK_VERSION=3.41.0','-DREADER_PRODUCT_PREFIX='+str(product)]
            if label in RAW_MODULES:
                options+=['-DEXR_READER_SELECTOR_BYTES_CANDIDATE='+('ON' if raw else 'OFF')]
            build=OUT/(name+'-'+label)
            configure(ROOT/module,build,options,name+'-'+label)
            run(['cmake','--install',build],name+'-'+label+'-install')
        host=OUT/(name+'-host')
        options=['-DCMAKE_PREFIX_PATH='+prefix,'-DEXR_SDK='+str(sdk),'-DEXR_SDK_VERSION=3.41.0',
                 '-DREADER_METADATA_PREFIX='+str(stage),'-DREADER_ACCOUNT_PREFIX='+str(stage),
                 '-DEXR_READER_WINDOWS_RAW3='+('ON' if raw else 'OFF'),
                 '-DEXR_READER_WINDOWS_SEARCH=ON','-DEXR_READER_WINDOWS_NAVIGATION=ON',
                 '-DEXR_READER_WINDOWS_RECORDS=ON','-DEXR_READER_WINDOWS_IMPORT_ORGANIZE=ON',
                 '-DEXR_READER_WINDOWS_PREFERENCES=ON','-DEXR_READER_WINDOWS_COMPACT=ON',
                 '-DEXR_READER_PREFS_COMMIT_REVIEW_BUILD=ON']
        configure(ROOT/'apps/reader/windows-account',host,options,name+'-actual-host')
        ui=OUT/(name+'-compact-ui')
        run([sys.executable,ROOT/'tests/reader_windows_compact/check_ui.py',
             '--candidate',host/'EXReaderProduct.exe','--font',ROOT/'build/host-font-cache/Reader.otf',
             '--fixtures',fixtures,'--output',ui],name+'-original-compact-ui',900)
        sys.path.insert(0,str(ROOT/'tests/reader_windows_compact'))
        from contract import validate
        compact=json.loads((ui/'report.json').read_text(encoding='utf-8'))
        validate(compact,os.environ['GITHUB_SHA'],os.environ['GITHUB_RUN_ID'],
                 os.environ['GITHUB_RUN_ATTEMPT'],hashlib.sha256((host/'EXReaderProduct.exe').read_bytes()).hexdigest())
        owner=OUT/(name+'-owner-probe')
        configure(ROOT/'tests/reader_windows_raw3/owner-probe',owner,
                  ['-DCMAKE_PREFIX_PATH='+prefix,'-DEXR_SDK='+str(sdk),
                   '-DPROBE_RAW='+('ON' if raw else 'OFF')],name+'-owner-probe')
        owner_run(owner/'windows-owner-probe.exe','suite',OUT/(name+'-owner-suite'),
                  ROOT/'tests/fixtures/pdf-public-text.pdf')
        if raw:
            owner_run(owner/'windows-owner-probe.exe','fresh',OUT/(name+'-owner-suite'),
                      ROOT/'tests/fixtures/pdf-public-text.pdf')
        bulk=OUT/(name+'-bulk-consumer')
        configure(ROOT/'tests/reader_windows_raw3/bulk-consumer',bulk,
                  ['-DCMAKE_PREFIX_PATH='+prefix,'-DPROBE_RAW='+('ON' if raw else 'OFF')],name+'-bulk-consumer')
        run([sys.executable,ROOT/'tests/reader_bulk_organization/check_bulk.py','--probe',bulk/'bulk-probe.exe',
             '--c-consumer',bulk/'bulk-c-consumer.exe','--link-map',bulk/'bulk-link.map',
             '--output',OUT/(name+'-bulk-evidence')],name+'-original-bulk',1800)
        original=json.loads((OUT/(name+'-bulk-evidence')/'report.json').read_text(encoding='utf-8'))
        if original['ok'] is not True:raise RuntimeError('Original bulk acceptance failed')
        binaries={target:hashlib.sha256((host/(target+'.exe')).read_bytes()).hexdigest()
                  for target in ('EXReaderProduct','EXReaderShelfReview')}
        profiles.append(dict(profile=name,programs=binaries,bulk_original_checks=len(original['checks']),
                             original_compact_ui_checks=compact['count'],
                             original_compact_ui_report=str((ui/'report.json').relative_to(OUT)),
                             bulk_original_report=str((OUT/(name+'-bulk-evidence')/'report.json').relative_to(OUT))))
    raw_exe=OUT/'raw-owner-probe/windows-owner-probe.exe'
    old_exe=OUT/'legacy-owner-probe/windows-owner-probe.exe'
    pdf=ROOT/'tests/fixtures/pdf-public-text.pdf'
    for phase in (2,3):
        killed_owner(raw_exe,old_exe,OUT/('owner-kill-'+str(phase)),pdf,phase)
    killed_owner(old_exe,raw_exe,OUT/'owner-legacy-kill',pdf,2,legacy=True)
    run([sys.executable,ROOT/'tests/reader_windows_raw3/network.py',
         '--candidate',OUT/'raw-host/EXReaderProduct.exe','--font',ROOT/'build/host-font-cache/Reader.otf',
         '--output',OUT/'mac-network-receive'],'actual-account-window-mac-receive',900)
    network=json.loads((OUT/'mac-network-receive/report.json').read_text(encoding='utf-8'))
    if network.get('accepted') is not True:raise RuntimeError('Actual Mac network receive failed')
    result=dict(source_sha=os.environ['GITHUB_SHA'],run_id=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'],
                installed_host_build_passed=True,original_bulk_profiles_passed=True,profiles=profiles,
                actual_owner_profiles_passed=True,actual_owner_process_kill_recovery_passed=True,
                actual_account_window_mac_receive_passed=True,
                host_raw3_accepted=False,scope='actual installed host build/link, original compact UI and bulk regressions, and owner recovery; no complete host/interoperability grant')
    (OUT/'report.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result),flush=True)


if __name__=='__main__':
    main()
