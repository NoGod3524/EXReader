"""Actions-only actual installed Win32 host in separate legacy/raw profiles."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

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


def main():
    if os.environ.get('GITHUB_ACTIONS')!='true' or sys.platform!='win32':
        raise RuntimeError('Windows Actions only')
    OUT.mkdir(parents=True,exist_ok=False);(OUT/'logs').mkdir()
    sdk=OUT/'sdk-stage';product=OUT/'product-stage'
    run(['cmake','--preset','reading-library','-B',OUT/'sdk-build','-DCMAKE_INSTALL_PREFIX='+str(sdk)],'sdk-configure')
    run(['cmake','--build',OUT/'sdk-build','--parallel','4'],'sdk-build')
    run(['cmake','--install',OUT/'sdk-build'],'sdk-install')
    configure(ROOT/'apps/reader/store/native',OUT/'product-build',['-DCMAKE_INSTALL_PREFIX='+str(product)],'product')
    run(['ctest','--test-dir',OUT/'product-build','--output-on-failure','--no-tests=error','--timeout','180'],'product-original-tests')
    run(['cmake','--install',OUT/'product-build'],'product-install')
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
                             bulk_original_report=str((OUT/(name+'-bulk-evidence')/'report.json').relative_to(OUT))))
    result=dict(source_sha=os.environ['GITHUB_SHA'],run_id=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'],
                installed_host_build_passed=True,original_bulk_profiles_passed=True,profiles=profiles,
                host_raw3_accepted=False,scope='actual installed host build/link and original bulk regressions; no actual host UI/raw record grant')
    (OUT/'report.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result),flush=True)


if __name__=='__main__':
    main()
