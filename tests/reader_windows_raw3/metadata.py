"""Build both installed metadata profiles and retain the entire original29-check suite."""
import json
import hashlib
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'build/windows-raw3-metadata'


def run(argv,name,expected=0):
    proc=subprocess.run([str(v) for v in argv],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                        encoding='utf-8',errors='replace',timeout=900)
    (OUT/(name+'.log')).write_text(proc.stdout,encoding='utf-8')
    if (proc.returncode==0)!=(expected==0):
        print(proc.stdout[-16000:],flush=True)
        raise RuntimeError(name+' returned '+str(proc.returncode))
    print(name+' exit='+str(proc.returncode),flush=True)


def main():
    if os.environ.get('GITHUB_ACTIONS')!='true':
        raise RuntimeError('Actions only')
    OUT.mkdir(parents=True,exist_ok=False)
    product=OUT/'product-stage'
    run(['cmake','-S',ROOT/'apps/reader/store/native','-B',OUT/'product-build','-G','Ninja',
         '-DCMAKE_BUILD_TYPE=Release','-DCMAKE_INSTALL_PREFIX='+str(product)],'product-configure')
    run(['cmake','--build',OUT/'product-build','--parallel','4'],'product-build')
    run(['cmake','--install',OUT/'product-build'],'product-install')
    rows=[]
    for raw in (False,True):
        name='raw' if raw else 'legacy'
        stage=OUT/(name+'-stage')
        for module in ('revisions','commands','desktop-metadata'):
            build=OUT/(name+'-'+module)
            run(['cmake','-S',ROOT/'apps/reader'/module,'-B',build,'-G','Ninja',
                 '-DCMAKE_BUILD_TYPE=Release','-DCMAKE_INSTALL_PREFIX='+str(stage),
                 '-DCMAKE_PREFIX_PATH='+str(stage)+';'+str(product),'-DREADER_PRODUCT_PREFIX='+str(product),
                 '-DEXR_READER_SELECTOR_BYTES_CANDIDATE='+('ON' if raw else 'OFF')],name+'-'+module+'-configure')
            run(['cmake','--build',build,'--parallel','4'],name+'-'+module+'-build')
            run(['cmake','--install',build],name+'-'+module+'-install')
        consumer=OUT/(name+'-consumer')
        run(['cmake','-S',ROOT/'tests/reader_windows_raw3/metadata-consumer','-B',consumer,'-G','Ninja',
             '-DCMAKE_BUILD_TYPE=Release','-DCMAKE_PREFIX_PATH='+str(stage)+';'+str(product),
             '-DRAW_METADATA='+('ON' if raw else 'OFF')],name+'-consumer-configure')
        run(['cmake','--build',consumer,'--parallel','4','--verbose'],name+'-consumer-build')
        suffix='.exe' if sys.platform=='win32' else ''
        run([consumer/('metadata-profile'+suffix),OUT/(name+'-profile.sqlite'),OUT/(name+'-profile.pending')],name+'-profile')
        result=OUT/(name+'-original-checks')
        run([sys.executable,ROOT/'tests/reader_metadata/check_metadata.py',
             '--consumer',consumer/('metadata-consumer'+suffix),'--c-consumer',consumer/('metadata-c-consumer'+suffix),
             '--command-consumer',consumer/('command-consumer'+suffix),'--product-prefix',product,
             '--link-map',consumer/'metadata-link.map','--build-log',OUT/(name+'-consumer-build.log'),
             '--output',result],name+'-original29')
        report=json.loads((result/'result.json').read_text(encoding='utf-8'))
        if report['accepted'] is not True or report['count']!=29:
            raise RuntimeError('Original metadata checks incomplete')
        binaries={target:hashlib.sha256((consumer/(target+suffix)).read_bytes()).hexdigest()
                  for target in ('metadata-consumer','metadata-c-consumer','command-consumer','metadata-profile')}
        rows.append(dict(profile=name,original_checks=29,profile_open_passed=True,binaries=binaries))
    # Actual mixed-family configure attempts, never imported-target edits.
    for raw,dependency in ((False,'raw'),(True,'legacy')):
        name='raw-with-legacy' if raw else 'legacy-with-raw'
        run(['cmake','-S',ROOT/'apps/reader/desktop-metadata','-B',OUT/name,'-G','Ninja',
             '-DCMAKE_PREFIX_PATH='+str(OUT/(dependency+'-stage'))+';'+str(product),
             '-DEXR_READER_SELECTOR_BYTES_CANDIDATE='+('ON' if raw else 'OFF')],name,expected=1)
    report=dict(accepted=True,source_sha=os.environ['GITHUB_SHA'],run_id=os.environ['GITHUB_RUN_ID'],
                attempt=os.environ['GITHUB_RUN_ATTEMPT'],profiles=rows,mixed_family_refusals=2,
                host_raw3_accepted=False,scope='installed desktop metadata profiles only')
    (OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report),flush=True)


if __name__=='__main__':
    main()
